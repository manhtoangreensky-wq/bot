from __future__ import annotations

import re
from pathlib import Path

import pytest

from services import video_flow6, video_scene3_flow


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    markers = (f"def {name}(", f"async def {name}(")
    starts = [BOT_SOURCE.find(marker) for marker in markers]
    start = min(position for position in starts if position >= 0)
    next_def = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[start + 1 :])
    end = start + 1 + next_def.start() if next_def else len(BOT_SOURCE)
    return BOT_SOURCE[start:end]


class _Button:
    def __init__(self, text: str, *, callback_data: str):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


def _compile_functions(*names: str, namespace: dict | None = None) -> dict:
    scope = dict(namespace or {})
    for name in names:
        exec(
            compile(
                "from __future__ import annotations\n\n" + _function_source(name),
                f"<flow6:{name}>",
                "exec",
            ),
            scope,
        )
    return scope


def _callbacks(markup) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if getattr(button, "callback_data", None)
    ]


def _assert_two_column_keyboard(markup) -> None:
    assert markup.inline_keyboard
    assert all(len(row) == 2 for row in markup.inline_keyboard)
    callbacks = _callbacks(markup)
    assert len(callbacks) == len(set(callbacks))
    assert markup.inline_keyboard[-1][1].callback_data == "menu|main"


def _context(product_id: str, *, mode: str = "manual", count: int = 2) -> dict:
    context = video_flow6.new_context(product_id=product_id, content_mode=mode)
    context.update(
        {
            "scene_count": count,
            "aspect_ratio": "9:16",
            "primary_profile_key": "character_people",
            "content_choice": {"id": "chosen", "title": "Nội dung đã chọn"},
        }
    )
    return video_flow6.normalize_context(context)


def test_flow6_canonical_order_and_exact_back_contract() -> None:
    assert video_scene3_flow.CANONICAL_STEPS[:6] == (
        "content_mode",
        "scene_count",
        "aspect_ratio",
        "asset_gate",
        "technical_profile",
        "content_choice",
    )
    assert video_scene3_flow.BACK_STEP["scene_count"] == "content_mode"
    assert video_scene3_flow.BACK_STEP["aspect_ratio"] == "scene_count"
    assert video_scene3_flow.BACK_STEP["asset_gate"] == "aspect_ratio"
    assert video_scene3_flow.BACK_STEP["content_choice"] == "technical_profile"


def test_public_entry_and_scene_ratio_keyboards_match_flow6_contract() -> None:
    entry = _function_source("video_scene3_canonical_entry_keyboard")
    count = _function_source("video_profile_scene1_count_keyboard")
    ratio = _function_source("video_scene3_aspect_keyboard")
    assert "✍️ Tự nhập nội dung" in entry
    assert "💡 Gợi ý nội dung" in entry
    assert "Bắt đầu lập kế hoạch" not in entry
    assert "Gợi ý chủ đề" not in entry
    assert "✍️ Nhập số khác" in count
    assert "ℹ️ Lưu ý số cảnh" in count
    assert "Dùng 2 cảnh đề xuất" not in count
    assert "✍️ Tự nhập" in ratio
    assert "💡 Gợi ý phù hợp" in ratio


def test_flow6_public_keyboards_are_two_columns_with_navigation_last() -> None:
    scope = _compile_functions(
        "video_scene3_keyboard",
        "video_scene3_nav_rows",
        "video_scene3_content_mode_keyboard",
        "video_profile_scene1_count_keyboard",
        "video_scene3_aspect_keyboard",
        "video_scene3_asset_gate_keyboard",
        "video_scene3_profile_keyboard",
        "video_scene3_suggestion_keyboard",
        "video_scene3_audio_plan_keyboard",
        "video_scene3_frame_quality_keyboard",
        "video_scene3_frame_invoice_keyboard",
        "video_scene3_canonical_entry_keyboard",
        namespace={
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "video_scene3_flow": video_scene3_flow,
            "video_flow6": video_flow6,
            "safe_int": lambda value, default=0: int(value or default),
            "video_profile_catalog_page_rows": lambda _page: [
                {
                    "icon": "🎯",
                    "short_name": f"Profile {index}",
                    "profile_key": f"profile_{index}",
                }
                for index in range(1, 5)
            ],
            "normalize_user_language": lambda _lang: "vi",
            "ui_text": lambda _lang, _key: "🏠 Menu chính",
        },
    )
    frame_state = video_flow6.sync_scene_state(_context("frame_video_local"))
    suggestion_state = {
        "suggestions": [{"id": f"idea-{index}"} for index in range(1, 6)]
    }
    audio_state = {"postproduction_addons": {}}
    markups = [
        scope["video_scene3_content_mode_keyboard"](),
        scope["video_profile_scene1_count_keyboard"](),
        scope["video_scene3_aspect_keyboard"](),
        scope["video_scene3_asset_gate_keyboard"](frame_state),
        scope["video_scene3_profile_keyboard"]({"profile_page": 1}),
        scope["video_scene3_suggestion_keyboard"](suggestion_state),
        scope["video_scene3_audio_plan_keyboard"](audio_state),
        scope["video_scene3_frame_quality_keyboard"](),
        scope["video_scene3_frame_invoice_keyboard"](),
        scope["video_scene3_canonical_entry_keyboard"]("video_ai_real"),
    ]
    for markup in markups:
        _assert_two_column_keyboard(markup)

    assert _callbacks(markups[5]) == [
        "vprofile|suggest|1",
        "vprofile|suggest|2",
        "vprofile|suggest|3",
        "vprofile|suggest|4",
        "vprofile|suggest|5",
        "vprofile|suggest_refresh",
        "vprofile|suggest_custom",
        "vprofile|suggest_restore",
        "vprofile|back",
        "menu|main",
    ]


def test_all_active_flow6_planning_keyboards_reject_singleton_rows() -> None:
    scope = _compile_functions(
        "video_scene3_keyboard",
        "video_scene3_nav_rows",
        "video_scene3_image_assets_keyboard",
        "video_scene3_image_quote_keyboard",
        "video_scene3_requirements_keyboard",
        "video_scene3_scene_plan_keyboard",
        "video_scene3_scene_detail_keyboard",
        "video_scene3_transitions_keyboard",
        "video_scene3_active_scene",
        "video_scene3_transition_keyboard",
        "video_scene3_automatic_text_keyboard",
        "video_scene3_automatic_text_review_keyboard",
        "video_scene3_automatic_text_position_keyboard",
        "video_scene3_automatic_text_scope_keyboard",
        "video_scene3_automatic_text_timing_keyboard",
        "video_scene3_automatic_text_target_keyboard",
        "video_scene3_automatic_text_duration_keyboard",
        "video_scene3_automatic_text_animation_keyboard",
        "video_scene3_automatic_text_style_keyboard",
        "video_scene3_full_review_keyboard",
        "video_scene3_post_keyboard",
        "video_scene3_post_detail_keyboard",
        "video_scene3_post_volume_keyboard",
        "video_scene3_post_position_keyboard",
        "video_scene3_logo_position_keyboard",
        namespace={
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "video_scene3_flow": video_scene3_flow,
            "safe_int": lambda value, default=0: int(value or default),
        },
    )
    with pytest.raises(
        ValueError,
        match="video_scene3_keyboard_requires_exactly_two_buttons_per_row",
    ):
        scope["video_scene3_keyboard"]([[("Nút lẻ", "flow6|invalid")]])

    base = {
        "scene_count": 2,
        "image_source_mode": "description",
        "postproduction_addons": {},
        "automatic_text_items": [],
    }
    markups = [
        scope["video_scene3_image_assets_keyboard"]({"image_source_mode": "create"}),
        scope["video_scene3_image_assets_keyboard"]({"image_source_mode": "uploaded"}),
        scope["video_scene3_image_quote_keyboard"](),
        scope["video_scene3_requirements_keyboard"](
            {"preservation_requirements": {}}
        ),
        scope["video_scene3_scene_plan_keyboard"](),
        scope["video_scene3_scene_detail_keyboard"](base),
        scope["video_scene3_transitions_keyboard"]({"scene_count": 1}),
        scope["video_scene3_transitions_keyboard"]({"scene_count": 20}),
        scope["video_scene3_transition_keyboard"]({"scene_count": 20, "active_scene_index": 1}),
        scope["video_scene3_automatic_text_keyboard"](),
        scope["video_scene3_automatic_text_position_keyboard"](),
        scope["video_scene3_automatic_text_timing_keyboard"](),
        scope["video_scene3_automatic_text_target_keyboard"](),
        scope["video_scene3_automatic_text_duration_keyboard"](),
        scope["video_scene3_automatic_text_animation_keyboard"](),
        scope["video_scene3_automatic_text_style_keyboard"](),
        scope["video_scene3_full_review_keyboard"](base),
        scope["video_scene3_post_keyboard"](base),
        scope["video_scene3_post_detail_keyboard"](
            {
                **base,
                "active_post_addon": "dubbing",
                "postproduction_addons": {"dubbing": {"enabled": True, "value": {}}},
            }
        ),
        scope["video_scene3_post_detail_keyboard"](
            {
                **base,
                "active_post_addon": "logo_image",
                "postproduction_addons": {"logo_image": {"enabled": True, "value": {}}},
            }
        ),
        scope["video_scene3_post_volume_keyboard"](),
        scope["video_scene3_post_position_keyboard"](),
        scope["video_scene3_logo_position_keyboard"](),
    ]
    for count in (1, 2, 3, 5, 20):
        markups.append(
            scope["video_scene3_automatic_text_scope_keyboard"](
                {
                    "scene_count": count,
                    "automatic_text_items": [],
                    "automatic_text_input_type": "scene_title",
                }
            )
        )
        markups.append(
            scope["video_scene3_automatic_text_scope_keyboard"](
                {
                    "scene_count": count,
                    "automatic_text_items": [],
                    "automatic_text_input_type": "character_intro",
                }
            )
        )
    markups.append(
        scope["video_scene3_automatic_text_review_keyboard"](
            {
                "automatic_text_items": [{"id": "text-1", "type": "scene_title"}],
                "automatic_text_history": [[{"id": "text-old"}]],
            }
        )
    )
    for markup in markups:
        _assert_two_column_keyboard(markup)


def test_public_idea_development_and_long_video_guard_keep_two_column_rows() -> None:
    scope = _compile_functions(
        "video_scene3_keyboard",
        "video_idea_development_keyboard",
        namespace={
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "video_scene3_flow": video_scene3_flow,
            "ui_text": lambda _lang, key: {
                "common.back": "⬅️ Quay lại",
                "common.main_menu": "🏠 Menu chính",
            }[key],
        },
    )
    keyboard = scope["video_idea_development_keyboard"]()
    _assert_two_column_keyboard(keyboard)
    callbacks = _callbacks(keyboard)
    assert "videa|page|1" in callbacks
    assert callbacks[-2:] == ["vproduct|back", "menu|main"]

    guard = BOT_SOURCE[
        BOT_SOURCE.index('if value == "multi_scene_film":'):
        BOT_SOURCE.index('if value in {"image_to_video", "frame_video_local"}:')
    ]
    assert guard.count("InlineKeyboardButton(") == 2
    assert "menu|main_video" in guard
    assert "menu|main" in guard


def test_video_edit_aspect_method_has_no_singleton_action_row() -> None:
    scope = _compile_functions(
        "video_scene3_keyboard",
        "video_ai_edit_aspect_method_keyboard",
        namespace={
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "video_scene3_flow": video_scene3_flow,
            "ui_text": lambda _lang, key: (
                "⬅️ Quay lại" if key == "common.back" else "🏠 Menu chính"
            ),
        },
    )
    markup = scope["video_ai_edit_aspect_method_keyboard"]()
    _assert_two_column_keyboard(markup)
    assert "videoedit|ai_aspect_limits" in _callbacks(markup)
    assert "videoedit|ai_source" in _callbacks(markup)


def test_profile_selection_is_single_and_content_follows_profile() -> None:
    source = _function_source("handle_video_profile_studio_callback")
    profile_branch = source.split('if action == "profile_select":', 1)[1].split(
        'if action == "profile_link_toggle":', 1
    )[0]
    assert '"content_choice"' in profile_branch
    assert '"profile_links"' not in profile_branch
    assert "linked_profiles=[]" in profile_branch


@pytest.mark.parametrize(
    ("product_id", "flow_kind", "requirement", "job_type", "owner"),
    (
        ("video_ai_real", "ai_real", "optional", "product_video", "owner_product_video"),
        ("video_idea", "idea_video", "optional", "product_video", "owner_product_video"),
        ("frame_video_local", "frame_video", "images_required", "frame_video_local", "local_worker"),
        ("storyboard_prompt", "storyboard", "images_required", "storyboard_to_video", "owner_product_video"),
        ("self_shot_scene_change", "self_shot", "video_required", "self_shot_scene_change", "owner_product_video"),
    ),
)
def test_five_public_flows_share_context_but_keep_exact_execution_owner(
    product_id: str,
    flow_kind: str,
    requirement: str,
    job_type: str,
    owner: str,
) -> None:
    context = _context(product_id)
    route = video_flow6.execution_route_for(context)
    assert context["flow_kind"] == flow_kind
    assert context["asset_requirement"] == requirement
    assert route["job_type"] == job_type
    assert route["execution_owner"] == owner
    assert route["preflight"] == "required_before_invoice"


def test_each_profile_has_twenty_suggestions_and_pages_do_not_repeat_early() -> None:
    for profile in ("character_people", "architecture_exterior", "product_3d"):
        context = _context("video_ai_real")
        context["primary_profile_key"] = profile
        catalog = video_flow6.content_suggestion_catalog(context, profile_label=profile)
        assert len(catalog) >= 20
        assert len({item["id"] for item in catalog[:20]}) == 20
        pages = [video_flow6.suggestion_page(context, page=page, profile_label=profile) for page in range(1, 5)]
        assert all(len(page) == 5 for page in pages)
        assert len({item["id"] for page in pages for item in page}) == 20


def test_content_selection_replaces_the_previous_choice() -> None:
    context = _context("video_ai_real", mode="suggestions")
    context["content_choice"] = {"id": "old"}
    selected = video_flow6.select_content(context, 2)
    assert selected["content_choice"]["id"] != "old"
    assert selected["content_choice"] == video_flow6.suggestion_page(selected)[1]


def test_required_asset_gates_block_before_invoice() -> None:
    frame = _context("frame_video_local", count=3)
    storyboard = _context("storyboard_prompt", count=2)
    self_shot = _context("self_shot_scene_change", count=2)
    assert video_flow6.asset_gate_status(frame)["blocker"] == "required_scene_images_missing"
    assert video_flow6.asset_gate_status(storyboard)["blocker"] == "required_scene_images_missing"
    assert video_flow6.asset_gate_status(self_shot)["blocker"] == "source_video_missing"
    for context in (frame, storyboard, self_shot):
        result = video_flow6.preflight(
            context,
            package_available=True,
            engine_ready=True,
            worker_ready=True,
            capability_ready=True,
        )
        assert result["ok"] is False
        assert result["side_effects"] == {
            "job": 0,
            "outbox": 0,
            "invoice": 0,
            "provider_calls": 0,
            "rendered_files": 0,
            "wallet_mutations": 0,
            "xu_charged": 0,
        }


def test_assets_unlock_only_the_matching_flow() -> None:
    frame = _context("frame_video_local", count=2)
    frame["asset_manifest"] = {
        "items": [
            {"file_id": "img-1", "media_kind": "image", "scene_index": 1},
            {"file_id": "img-2", "media_kind": "image", "scene_index": 2},
        ],
        "source_video": {},
        "probe": {},
    }
    self_shot = _context("self_shot_scene_change", count=2)
    self_shot["asset_manifest"] = {
        "items": [],
        "source_video": {"file_id": "video-1"},
        "probe": {"duration": 30, "width": 1080, "height": 1920, "audio_streams": 1},
    }
    assert video_flow6.asset_gate_status(frame)["ok"] is True
    assert video_flow6.asset_gate_status(self_shot)["ok"] is True


def test_unavailable_engine_blocks_before_invoice_and_provider_call() -> None:
    context = _context("video_ai_real")
    result = video_flow6.preflight(
        context,
        package_available=True,
        engine_ready=False,
        worker_ready=False,
        capability_ready=False,
    )
    assert result["ok"] is False
    assert "execution_owner_unavailable" in result["blockers"]
    assert "worker_runtime_unavailable" in result["blockers"]
    assert result["side_effects"]["provider_calls"] == 0
    assert result["side_effects"]["invoice"] == 0


def test_delivery_receipt_is_required_once_before_charge() -> None:
    context = _context("video_ai_real")
    assert video_flow6.charge_allowed(context) is False
    with pytest.raises(ValueError, match="valid_telegram_delivery_receipt_required"):
        video_flow6.record_delivery(context, artifact_message_id=0, receipt_key="")
    delivered = video_flow6.record_delivery(context, artifact_message_id=701, receipt_key="job-7:delivery")
    assert video_flow6.charge_allowed(delivered) is True
    assert video_flow6.record_delivery(delivered, artifact_message_id=701, receipt_key="job-7:delivery") == delivered
    with pytest.raises(ValueError, match="delivery_receipt_already_recorded"):
        video_flow6.record_delivery(delivered, artifact_message_id=702, receipt_key="job-7:delivery-2")


def test_planning_service_has_no_provider_or_wallet_side_effect_code() -> None:
    source = (ROOT / "services" / "video_flow6.py").read_text(encoding="utf-8").lower()
    for forbidden in (
        "requests.",
        "httpx.",
        "shopaikey",
        "key4u",
        "spend_fixed_credit",
        "create_product_video_job",
        "create_local_worker_job",
    ):
        assert forbidden not in source


def test_required_asset_media_has_one_global_dedupe_owner_and_full_probe_metadata() -> None:
    guard = _function_source("video_public_media_dedupe_guard")
    intake = _function_source("handle_video_scene3_pending_media")
    assert '"await_flow6_asset_upload"' in guard
    assert '"await_flow6_asset_upload"' in intake
    assert "processed_media_message_ids" in intake
    for field in (
        "file_size",
        "width",
        "height",
        "duration_seconds",
        "scene_index",
    ):
        assert field in intake


def test_preflight_owns_quality_and_blocks_before_invoice_or_submit() -> None:
    callback = _function_source("handle_video_profile_studio_callback")
    expected_steps_start = BOT_SOURCE.index("VIDEO_SCENE2_ACTION_EXPECTED_STEPS =")
    expected_steps = BOT_SOURCE[
        expected_steps_start : BOT_SOURCE.index("\n\n", expected_steps_start)
    ]
    assert '"frame_quality": {"quality"}' in expected_steps
    assert '"frame_quality_info": {"quality"}' in expected_steps
    assert "video_flow6_preflight_for_state" in callback
    assert "execution_submit_allowed" in callback
    assert "provider_submit_allowed" in callback
    assert "video_flow6_preflight_block_text" in callback
    assert callback.index("video_flow6_preflight_for_state") < callback.index("frame_video_review_text")


def test_frame_video_final_confirm_delivers_receipt_before_charge() -> None:
    source = _function_source("handle_frame_video_final_confirm")
    ordered = (
        "render_frame_video_canonical_from_state",
        "context.bot.send_video",
        "delivery_message_id =",
        "receipt_recorded=1",
        "frame_video_charge_after_delivery",
    )
    positions = [source.index(token) for token in ordered]
    assert positions == sorted(positions)
    assert "failed_no_charge" in source
    assert "wallet_charge_amount_xu=0" in source
