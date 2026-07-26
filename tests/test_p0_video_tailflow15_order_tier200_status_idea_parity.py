from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import video_scene3_flow, video_tail9, video_uifreeze1


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    pattern = re.compile(rf"^(?:async )?def {re.escape(name)}\(", re.MULTILINE)
    match = pattern.search(BOT_SOURCE)
    assert match, f"missing function: {name}"
    next_match = re.search(r"\n(?=@|(?:async )?def [A-Za-z_])", BOT_SOURCE[match.end() :])
    end = match.end() + next_match.start() if next_match else len(BOT_SOURCE)
    return BOT_SOURCE[match.start() : end]


def _load_keyboard(name: str):
    namespace = {
        "video_scene3_keyboard": video_scene3_flow.validate_two_column_rows,
        "video_editengine1": SimpleNamespace(PRODUCT_TYPE="video_local_edit"),
        "VIDEO_TAIL9_AUDIO_LABELS": {
            "source_audio": "Âm thanh gốc",
            "dubbing": "Lồng tiếng",
            "music": "Nhạc nền",
            "sfx": "Hiệu ứng âm thanh",
            "subtitles": "Phụ đề",
        },
    }
    exec("from __future__ import annotations\n" + _function_source(name), namespace)
    return namespace[name]


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _load_invoice_breakdown():
    namespace = {
        "safe_int": _safe_int,
        "video_b14_scene_discount_percent": lambda _count: 0,
    }
    exec("from __future__ import annotations\n" + _function_source("video_b14_invoice_breakdown"), namespace)
    return namespace["video_b14_invoice_breakdown"]


def _callbacks(markup) -> list[str]:
    rows = getattr(markup, "inline_keyboard", markup)
    return [
        str(getattr(button, "callback_data", button[1]))
        for row in rows
        for button in row
    ]


def _idea_tail(scene_count: int = 2) -> dict:
    state = video_tail9.new_state(
        product_type="video_ai_real",
        session_id=f"tailflow15-idea-{scene_count}",
        scene_count=scene_count,
        ratio="16:9",
    )
    return video_tail9.apply_content_contract(
        state,
        {
            "content_source": "idea_catalog",
            "canonical_content_mode": "idea_catalog",
            "selected_prompt_text": "Prompt đã chọn từ Kho Ý tưởng video.",
            "selected_prompt_revision": 3,
            "per_scene_content": [
                {"scene_index": index, "provider_prompt": f"Prompt cảnh {index}"}
                for index in range(1, scene_count + 1)
            ],
            "plan_status": "ready",
        },
    )


def test_exact_idea_tail_order_is_branding_summary_review_audio_quality() -> None:
    state = _idea_tail(2)
    assert video_tail9.next_required_screen(state) == "logo"

    state = video_tail9.mark_branding_skipped(state)
    assert video_tail9.next_required_screen(state) == "summary"

    state = video_tail9.prepare_summary(state)
    assert state["summary_status"] == "ready"
    assert video_tail9.next_required_screen(state) == "review"

    state = video_tail9.mark_review_complete(state)
    assert video_tail9.next_required_screen(state) == "audio"

    state = video_tail9.mark_audio_complete(state, skipped=True)
    assert video_tail9.next_required_screen(state) == ""
    assert state["status_stage"] == "audio_addons"


def test_branding_summary_review_and_audio_buttons_follow_the_exact_order() -> None:
    logo_callbacks = _callbacks(_load_keyboard("video_tail9_logo_keyboard")(_idea_tail(2)))
    summary_callbacks = _callbacks(_load_keyboard("video_tail9_summary_keyboard")(_idea_tail(2)))
    review_callbacks = _callbacks(_load_keyboard("video_tail9_review_keyboard")(_idea_tail(2)))
    audio_callbacks = _callbacks(_load_keyboard("video_tail9_audio_keyboard")(_idea_tail(2)))

    assert "video_tail|logo|done" in logo_callbacks
    assert "video_tail|logo|skip" in logo_callbacks
    assert "video_tail|summary|continue" in summary_callbacks
    assert "video_tail|summary|back" in summary_callbacks
    assert "video_tail|quality|open" not in summary_callbacks
    assert "video_tail|audio|open" not in summary_callbacks
    assert "video_tail|review|audio" in review_callbacks
    assert "video_tail|audio|open" not in review_callbacks
    assert "video_tail|audio|done" in audio_callbacks
    assert "video_tail|audio|skip" in audio_callbacks
    assert "video_tail|review|open" in audio_callbacks
    assert "video_tail|logo|open" not in audio_callbacks
    assert "video_tail|summary|open" not in audio_callbacks


def test_logo_back_uses_the_exact_owner_instead_of_looping_or_leaking() -> None:
    keyboard = _load_keyboard("video_tail9_logo_keyboard")
    edit_callbacks = _callbacks(keyboard({
        "video_product_type": "video_local_edit",
        "branding_return_to": "summary",
    }))
    standard_callbacks = _callbacks(keyboard({
        "video_product_type": "video_ai_real",
        "branding_return_to": "summary",
    }))

    assert "video_tail|review|edit_operation" in edit_callbacks
    assert "video_tail|review|prompts" not in edit_callbacks
    assert "video_tail|review|prompts" in standard_callbacks


def test_tier_200_depends_on_actual_scene_count_and_supports_one_scene_inputs() -> None:
    one_scene_products = (
        ("video_ai_real", "text_to_video"),
        ("video_ai_image", "image_to_video"),
        ("self_shot_scene_change", "video_to_video"),
    )
    for product, capability in one_scene_products:
        report = video_uifreeze1.catalog_report(
            product,
            scene_count=1,
            ratio="9:16",
            required_capability=capability,
        )
        assert report["ok"] is True
        assert 200 in report["tier_ids"]

    multi_scene = video_uifreeze1.catalog_report(
        "video_ai_real",
        scene_count=2,
        ratio="9:16",
        required_capability="text_to_video",
    )
    assert 200 not in multi_scene["tier_ids"]
    assert multi_scene["tier_ids"][0] == 300


def test_pricing_truth_is_200_for_one_scene_and_600_for_two_scene_basic() -> None:
    invoice_breakdown = _load_invoice_breakdown()

    assert invoice_breakdown(200, 1) == {
        "subtotal_xu": 200,
        "discount_percent": 0,
        "discount_xu": 0,
        "total_xu": 200,
    }
    assert invoice_breakdown(300, 2) == {
        "subtotal_xu": 600,
        "discount_percent": 0,
        "discount_xu": 0,
        "total_xu": 600,
    }


def test_stale_tier_200_selection_cannot_replace_a_valid_multi_scene_package() -> None:
    state = _idea_tail(2)
    state = video_tail9.select_package(
        state,
        quality_tier_id="300",
        package_id="product_video_300",
        pricing_snapshot={"quality_xu": 300, "scene_count": 2, "total_xu": 600},
        capability_snapshot={"ok": True, "engine_route": "video_ai_canonical"},
    )
    before = video_tail9.normalize_state(state)

    with pytest.raises(ValueError, match="quality_tier_not_supported"):
        video_tail9.select_package(
            state,
            quality_tier_id="200",
            package_id="product_video_200",
            pricing_snapshot={"quality_xu": 200, "scene_count": 2, "total_xu": 400},
            capability_snapshot={"ok": True, "engine_route": "video_ai_canonical"},
        )

    assert video_tail9.normalize_state(state) == before


def test_content_prompt_and_owner_survive_every_preconfirm_transition() -> None:
    state = _idea_tail(2)
    expected = {
        "video_product_type": state["video_product_type"],
        "video_flow_owner": state["video_flow_owner"],
        "content_source": state["content_source"],
        "selected_prompt": state["selected_prompt"],
        "scene_count": state["scene_count"],
        "ratio": state["ratio"],
        "scene_content": state["scene_content"],
    }

    for transition in (
        video_tail9.mark_branding_skipped,
        video_tail9.prepare_summary,
        video_tail9.mark_review_complete,
        lambda value: video_tail9.mark_audio_complete(value, skipped=True),
    ):
        state = transition(state)
        assert {key: state[key] for key in expected} == expected


def test_live_invoice_migration_keeps_package_pricing_and_current_stage() -> None:
    state = video_tail9.select_package(
        _idea_tail(2),
        quality_tier_id="300",
        package_id="product_video_300",
        pricing_snapshot={"quality_xu": 300, "scene_count": 2, "total_xu": 600},
        capability_snapshot={"ok": True, "engine_route": "video_ai_canonical"},
    )
    state.update({
        "tail_flow_version": 14,
        "review_status": "not_ready",
        "audio_status": "not_configured",
        "logo_status": "not_configured",
        "watermark_status": "not_configured",
        "summary_status": "not_ready",
    })

    migrated = video_tail9.normalize_state(state)

    assert migrated["status_stage"] == "invoice"
    assert migrated["quality_tier_id"] == "300"
    assert migrated["package_id"] == "product_video_300"
    assert migrated["pricing_snapshot"]["total_xu"] == 600
    assert migrated["review_status"] == "ready"
    assert migrated["audio_status"] == "skipped"
    assert migrated["logo_status"] == "skipped"
    assert migrated["watermark_status"] == "skipped"
    assert migrated["summary_status"] == "ready"


def test_all_shared_tail_entries_open_branding_without_touching_framevideo() -> None:
    profile_handler = _function_source("handle_video_profile_studio_callback")
    idea_parent = _function_source("video_idea_render_exact_parent")
    storyboard_handler = _function_source("_handle_storyboard2_callback_impl")
    selfshot_result = _function_source("video_selfshotflow4_handle_result")
    edit_handler = _function_source("handle_video_editor_callback")

    assert 'if action == "video_prompt_done":' in profile_handler
    assert 'video_tail9_render(query, uid, context, "logo")' in profile_handler
    assert 'video_tail9_render(query, user_id, context, "logo")' in idea_parent
    assert 'video_tail9_render(query, uid, context, "logo")' in storyboard_handler
    assert 'video_tail9_render(target, user_id, context, "logo")' in selfshot_result
    assert 'video_tail9_render(query, uid, context, "logo")' in edit_handler
    assert "framevideo" not in "\n".join((profile_handler, idea_parent, storyboard_handler, selfshot_result, edit_handler))


def test_status_panel_has_truthful_steps_and_required_navigation() -> None:
    status_text = _function_source("video_b14_queue_status_text")
    status_keyboard = _function_source("video_b14_queue_status_keyboard")
    constants = BOT_SOURCE[BOT_SOURCE.index("VIDEO_B14_STATUS_STEP_LABELS = (") :]
    constants = constants[: constants.index("\n)\n") + 3]

    for label in (
        "Nhận yêu cầu",
        "Kiểm tra cấu hình",
        "Tạo tác vụ",
        "Dựng video",
        "Kiểm tra file",
        "Gửi kết quả",
    ):
        assert label in constants
    assert "TOAN AAS đang xử lý video" in status_text
    assert "Mã xử lý" in status_text
    assert "vproduct|b14_job_status" in status_keyboard
    assert "Gửi video khác" in status_keyboard
    assert "vproduct|b14_invoice_screen" in status_keyboard
    assert 'callback_data="menu|main"' in status_keyboard


def test_submit_handoff_keeps_confirmation_separate_and_returns_status_owner() -> None:
    handler = _function_source("handle_video_tail_callback")
    confirm = handler[handler.index('if section == "confirm":') :]

    assert confirm.index('if action == "open":') < confirm.index('if action == "submit":')
    assert 'query.data = "vproduct|b14_confirm"' in confirm
    assert "handle_product_video_public_confirm_callback" in confirm
    assert "video_tail9_render_confirmed_status" in handler
    assert 'video_tail9_render(query, uid, context, "quality")' not in confirm


def test_confirmed_tail_blocks_every_stale_preconfirm_callback_before_dispatch() -> None:
    handler = _function_source("handle_video_tail_callback")
    confirmed_guard = 'if tail.get("final_confirmed") and section != "confirm":'

    assert confirmed_guard in handler
    assert handler.index(confirmed_guard) < handler.index('if section == "review":')
    guard = handler[handler.index(confirmed_guard):handler.index('if section == "review":')]
    assert "video_tail9_render_confirmed_status" in guard
