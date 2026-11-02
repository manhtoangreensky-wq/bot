from __future__ import annotations

import re
from pathlib import Path

import pytest
import bot

from services import video_tail9, video_uifreeze1


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
    return getattr(bot, name)


def _load_invoice_breakdown():
    return bot.video_b14_invoice_breakdown


def _callbacks(markup) -> list[str]:
    rows = getattr(markup, "inline_keyboard", markup)
    return [
        str(button.callback_data if hasattr(button, "callback_data") else button[1])
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


def test_idea_consumer_tail_enters_addon_then_review_before_quality() -> None:
    state = _idea_tail(2)
    assert video_tail9.next_required_screen(state) == "addon"

    state = video_tail9.mark_addon_complete(state)
    assert video_tail9.next_required_screen(state) == "review"

    state = video_tail9.prepare_review(state)
    assert state["review_status"] == "not_ready"
    state = video_tail9.mark_review_complete(state)
    assert state["review_status"] == "ready"
    assert video_tail9.next_required_screen(state) == ""
    assert state["status_stage"] == "review"


def test_branding_addon_and_review_buttons_keep_the_current_order() -> None:
    logo_callbacks = _callbacks(_load_keyboard("video_tail9_logo_keyboard")(_idea_tail(2)))
    addon_callbacks = _callbacks(_load_keyboard("video_tail9_addon_keyboard")(_idea_tail(2)))
    review_callbacks = _callbacks(_load_keyboard("video_tail9_review_keyboard")(_idea_tail(2)))

    assert "video_tail|logo|done" in logo_callbacks
    assert "video_tail|logo|skip" in logo_callbacks
    assert "video_tail|addon|complete" in addon_callbacks
    assert "video_tail|addon|back" in addon_callbacks
    assert "video_tail|review|complete" in review_callbacks
    assert "video_tail|review|back" in review_callbacks
    assert "video_tail|quality|open" not in addon_callbacks + review_callbacks
    assert not any(item.startswith("video_tail|summary|") for item in addon_callbacks + review_callbacks)


def test_logo_back_uses_the_exact_owner_instead_of_looping_or_leaking() -> None:
    keyboard = _load_keyboard("video_tail9_logo_keyboard")
    edit_callbacks = _callbacks(keyboard({
        "video_product_type": bot.video_editengine1.PRODUCT_TYPE,
        "branding_back_to": "summary",
    }))
    standard_callbacks = _callbacks(keyboard({
        "video_product_type": "video_ai_real",
        "branding_back_to": "summary",
    }))

    assert "video_tail|review|edit_operation" in edit_callbacks
    assert "video_tail|addon|open" in standard_callbacks
    current = _idea_tail(2)
    current["branding_back_to"] = "review"
    review_return = _callbacks(keyboard(current))
    assert "video_tail|review|open" in review_return


def test_tier_200_supports_ai_real_scenes_but_not_selfshot() -> None:
    one_scene_products = (
        ("video_ai_real", "text_to_video"),
        ("video_ai_image", "image_to_video"),
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
    assert 200 in multi_scene["tier_ids"]
    assert multi_scene["tier_ids"][0] == 300
    selfshot = video_uifreeze1.catalog_report("self_shot_scene_change", scene_count=2, ratio="keep")
    assert set(selfshot["tier_ids"]) == {500, 600, 700, 800}
    assert 200 not in selfshot["tier_ids"]


def test_invoice_breakdown_uses_current_prices_and_two_scene_discount() -> None:
    invoice_breakdown = _load_invoice_breakdown()

    assert invoice_breakdown(200, 1) == {
        "subtotal_xu": 259,
        "discount_percent": 0,
        "discount_xu": 0,
        "total_xu": 259,
        "unit_xu": 259,
        "routing_quality_tier": 200,
    }
    assert invoice_breakdown(300, 2) == {
        "subtotal_xu": 442,
        "discount_percent": 10,
        "discount_xu": 44,
        "total_xu": 398,
        "unit_xu": 221,
        "routing_quality_tier": 300,
    }


def test_unknown_tier_cannot_replace_a_valid_multi_scene_package() -> None:
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
            quality_tier_id="9999",
            package_id="product_video_9999",
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
        video_tail9.mark_addon_complete,
        video_tail9.prepare_review,
        video_tail9.mark_review_complete,
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


def test_current_shared_tail_bridges_enter_addon_without_touching_framevideo() -> None:
    profile_handler = _function_source("handle_video_uiflow3_callback")
    script = _function_source("video_profile_scene1_open_selected_tail_invoice")
    storyboard_handler = _function_source("_handle_storyboard2_callback_impl")
    selfshot_result = _function_source("video_selfshotflow4_handle_result")
    assert '"review" if tail_return_screen == "review" else "addon"' in profile_handler
    assert 'video_tail9_render(query, user_id, context, "addon")' in script
    assert "return await video_manual_lane_open_shared_tail(" in storyboard_handler
    assert 'origin_step="storyboard2_assets_done"' in storyboard_handler
    assert '"addon" if return_to_addon else "review"' in selfshot_result
    assert "framevideo" not in "\n".join((script, storyboard_handler, selfshot_result))


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
    assert "Mã yêu cầu" in status_text
    assert "Mã tác vụ" in status_text
    assert "không báo hoàn tất khi chưa có video cuối" in status_text
    callbacks = _callbacks(bot.video_b14_queue_status_keyboard())
    assert "vproduct|b14_job_status" in callbacks
    assert "menu|main_video" in callbacks
    assert "vproduct|b14_invoice_screen" in callbacks
    assert "menu|main" in callbacks
    missing = bot.video_b14_status_step_rows("completed", 100, has_final_artifact=False)
    waiting = bot.video_b14_status_step_rows("completed", 100, has_final_artifact=True, delivery_done=False)
    delivered = bot.video_b14_status_step_rows("completed", 100, has_final_artifact=True, delivery_done=True)
    assert missing[-1][0] != "✅"
    assert waiting[-1][0] == "⏳"
    assert all(icon == "✅" for icon, _label in delivered)


def test_submit_handoff_keeps_confirmation_separate_and_returns_status_owner() -> None:
    handler = _function_source("handle_video_tail_callback")
    confirm = handler[handler.index('if section == "confirm":') :]

    assert confirm.index('if action == "open":') < confirm.index('if action == "submit":')
    assert 'setattr(context, "_product_video_callback_data_override", "vproduct|b14_confirm")' in confirm
    assert 'query.data = "vproduct|b14_confirm"' not in confirm
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
