from __future__ import annotations

import asyncio
import re
from pathlib import Path

from services import video_flow6


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    marker = f"def {name}("
    start = BOT_SOURCE.index(marker)
    next_def = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[start + 1 :])
    end = start + 1 + next_def.start() if next_def else len(BOT_SOURCE)
    return BOT_SOURCE[start:end]


def _restore(state: dict) -> dict:
    namespace = {"video_flow6": video_flow6}
    exec(_function_source("video_ai_realistic_restore_legacy_content_mode"), namespace)
    return namespace["video_ai_realistic_restore_legacy_content_mode"](state)


def _completed_profile_state() -> dict:
    choice = {
        "id": "review_product_story",
        "title": "Mở hộp và hé lộ sản phẩm",
        "concept": "Giới thiệu lợi ích sản phẩm qua hai cảnh liên tiếp.",
    }
    return {
        "source_product_id": "video_ai_real",
        "product_type": "video_ai_real",
        "step": "full_review",
        "scene_count": 2,
        "aspect_ratio": "9:16",
        "ai_input_type": "prompt_video",
        "content_source": "profiles",
        "source_fields": {
            "ai_input_type": "prompt_video",
            "content_source": "profiles",
        },
        "primary_profile_key": "review_demo",
        "content_choice": choice,
        "selected_suggestion": choice,
    }


def test_completed_pre_flow6_profile_plan_regains_only_the_missing_mode() -> None:
    restored = _restore(_completed_profile_state())

    assert restored["content_mode"] == "suggestions"
    assert restored["content_source"] == "profiles"
    assert restored["primary_profile_key"] == "review_demo"
    assert restored["content_choice"]["id"] == "review_product_story"

    result = video_flow6.preflight(
        video_flow6.context_from_scene_state(restored),
        package_available=True,
        engine_ready=True,
        worker_ready=True,
        capability_ready=True,
    )
    assert result["ok"] is True
    assert "content_mode_missing" not in result["blockers"]
    assert result["side_effects"] == {
        "job": 0,
        "outbox": 0,
        "invoice": 0,
        "provider_calls": 0,
        "rendered_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }


def test_completed_manual_plan_keeps_its_manual_branch_and_preflight_truth() -> None:
    state = {
        **_completed_profile_state(),
        "content_source": "manual",
        "source_fields": {"ai_input_type": "prompt_video", "content_source": "manual"},
        "manual_content": "Giới thiệu một sản phẩm theo yêu cầu của khách hàng.",
        "content_mode": "",
    }

    restored = _restore(state)

    assert restored["content_mode"] == "manual"
    assert restored["content_source"] == "manual"
    assert restored["content_choice"] == state["content_choice"]


def test_completed_saved_scene_plan_recovers_the_missing_profile_selection_contract() -> None:
    state = {
        **_completed_profile_state(),
        "content_mode": "",
        "content_source": "",
        "source_fields": {"ai_input_type": "prompt_video"},
        "content_choice": {},
        "selected_suggestion": {},
        "plan": {
            "scenes": [
                {
                    "title": "Mở hộp sản phẩm",
                    "goal": "Mở đầu bằng chi tiết sản phẩm rõ ràng.",
                },
                {
                    "title": "Kết quả sử dụng",
                    "goal": "Khép lại bằng lợi ích đã chứng minh.",
                },
            ]
        },
    }

    restored = _restore(state)

    assert restored["content_mode"] == "suggestions"
    assert restored["content_source"] == "profiles"
    assert restored["primary_profile_key"] == "review_demo"
    assert restored["content_choice"]["id"] == "review_demo"
    assert restored["content_choice"]["title"] == "Mở hộp sản phẩm"

    result = video_flow6.preflight(
        video_flow6.context_from_scene_state(restored),
        package_available=True,
        engine_ready=True,
        worker_ready=True,
        capability_ready=True,
    )
    assert result["ok"] is True
    assert "content_mode_missing" not in result["blockers"]
    assert "content_choice_missing" not in result["blockers"]


def test_incomplete_realistic_plan_is_not_guessed_or_advanced() -> None:
    state = {
        "source_product_id": "video_ai_real",
        "product_type": "video_ai_real",
        "step": "content_source",
        "scene_count": 2,
        "aspect_ratio": "9:16",
        "ai_input_type": "prompt_video",
        "subject": "Một chủ đề chưa được chọn nguồn nội dung.",
    }

    assert _restore(state) == state


def test_restore_does_not_touch_storyboard_or_other_product_owners() -> None:
    state = {
        **_completed_profile_state(),
        "source_product_id": "storyboard_prompt",
        "product_type": "storyboard_prompt",
        "content_mode": "",
    }

    assert _restore(state) == state


def test_existing_mode_is_preserved_instead_of_reselecting_content() -> None:
    state = {**_completed_profile_state(), "content_mode": "suggestions"}

    restored = _restore(state)

    assert restored["content_mode"] == "suggestions"
    assert restored["content_choice"] == state["content_choice"]


def test_tail_context_uses_the_scoped_restore_before_pricing_preflight() -> None:
    source = _function_source("video_tail9_context")

    assert source.count("video_ai_realistic_restore_legacy_content_mode(host)") == 1
    assert "host = save_video_profile_studio_state(context, restored_host)" in source
    assert source.index("video_ai_realistic_restore_legacy_content_mode(host)") < source.index("requested = str(host.get")


def test_realistic_callback_contract_stays_single_owner_with_single_row_prompts() -> None:
    assert BOT_SOURCE.count(
        'CallbackQueryHandler(handle_video_profile_studio_callback, pattern=r"^vprofile\\|")'
    ) == 1
    prompt_keyboard = _function_source("video_scene3_suggestion_keyboard")
    assert "number_buttons," in prompt_keyboard
    assert "number_buttons[:2]" not in prompt_keyboard
    assert "number_buttons[2:4]" not in prompt_keyboard


def test_tail_quality_callback_keeps_failures_in_its_own_route_instead_of_global_error() -> None:
    guard = _function_source("video_tail9_callback_guard")
    handler = _function_source("handle_video_tail_callback")

    assert "@video_tail9_callback_guard" in BOT_SOURCE
    assert "except ApplicationHandlerStop" in guard
    assert "video_tail9_render(query, int(query.from_user.id), context, screen)" in guard
    assert '"quality": "video_tail|quality|open"' in guard
    assert "video_tail_quality_selection_failed" in handler
    assert "video_b14_invoice_for_session" in handler
    assert 'tail["pricing_snapshot"] = {}' in handler
    assert "Có lỗi khi xử lý lệnh" not in guard
    assert "Có lỗi khi xử lý lệnh" not in handler


def test_active_product_video_callbacks_are_all_covered_by_global_dedupe() -> None:
    prefixes = BOT_SOURCE[
        BOT_SOURCE.index("VIDEO_PUBLIC_CALLBACK_PREFIXES = (") : BOT_SOURCE.index("_VIDEO_PUBLIC_CALLBACK_CLAIMS:")
    ]
    handlers = {
        "video_tail|": 'CallbackQueryHandler(handle_video_tail_callback, pattern=r"^video_tail\\|", block=True)',
        "vtrend|": 'CallbackQueryHandler(handle_video_trend2_callback, pattern=r"^vtrend\\|")',
        "vstory|": 'CallbackQueryHandler(handle_storyboard2_callback, pattern=r"^vstory\\|")',
        "vstoryimg|": 'CallbackQueryHandler(handle_storyboard_image_callback, pattern=r"^vstoryimg\\|")',
        "idea_video|": 'CallbackQueryHandler(handle_video_idea_prompt_callback, pattern=r"^idea_video\\|")',
    }

    for prefix, registration in handlers.items():
        assert f'"{prefix}"' in prefixes
        assert BOT_SOURCE.count(registration) == 1


def test_public_video_callbacks_keep_unexpected_errors_out_of_global_generic_x() -> None:
    guard = _function_source("video_public_callback_failure_guard")

    assert "except ApplicationHandlerStop" in guard
    assert "if not _is_video_public_callback(callback_data, context):" in guard
    assert "product_video_callback_failed callback=%s handler=%s" in guard
    assert "Màn hiện tại và kế hoạch vẫn được giữ." in guard
    assert "Có lỗi khi xử lý lệnh" not in guard

    guarded_handlers = (
        "handle_video_prompt_library_callback",
        "handle_video_trend2_callback",
        "handle_storyboard2_callback",
        "handle_video_trend2_legacy_callback",
        "handle_video_product_callback",
        "handle_video_reference_callback",
        "handle_video_idea_prompt_callback",
        "handle_video_idea_dynamic_callback",
        "handle_video_idea_callback",
        "handle_storyboard_pack_callback",
        "handle_video_finalization_callback",
        "handle_video_addon_callback",
        "handle_video_downloader_callback",
        "handle_frame_video_callback",
        "handle_storyboard_callback",
        "handle_storyboard_image_callback",
        "handle_create_media_callback",
        "handle_video_profile_studio_callback",
        "handle_video_editor_callback",
        "handle_video_upload_callback",
        "handle_product_video_public_confirm_callback",
        "handle_prompt_video_callback",
        "handle_image_video_callback",
        "handle_self_scene_ai_callback",
        "handle_long_video_callback",
        "handle_public_video_status_callback",
        "handle_creative_motion_callback",
        "handle_cinematic_ad_callback",
    )
    for handler_name in guarded_handlers:
        assert f"@video_public_callback_failure_guard\nasync def {handler_name}" in BOT_SOURCE

    for non_video_handler in (
        "handle_video_dubbing_callback",
        "handle_marketing_callback",
        "handle_architecture_profile_callback",
    ):
        assert f"@video_public_callback_failure_guard\nasync def {non_video_handler}" not in BOT_SOURCE


def test_public_video_callback_failure_guard_responds_once_without_generic_x() -> None:
    class _Logger:
        def __init__(self) -> None:
            self.entries: list[tuple] = []

        def exception(self, *args) -> None:
            self.entries.append(args)

    class _Query:
        data = "vproduct|content_source|profiles"

        def __init__(self) -> None:
            self.answers: list[tuple[str, bool]] = []

        async def answer(self, text: str, show_alert: bool = False) -> None:
            self.answers.append((text, show_alert))

    class _Update:
        def __init__(self, query: _Query) -> None:
            self.callback_query = query

    class _ApplicationHandlerStop(Exception):
        pass

    logger = _Logger()
    namespace = {
        "ApplicationHandlerStop": _ApplicationHandlerStop,
        "ContextTypes": object,
        "Update": object,
        "logger": logger,
        "_is_video_public_callback": lambda callback_data, _context: callback_data.startswith("vproduct|"),
    }
    exec(_function_source("video_public_callback_failure_guard"), namespace)

    async def failing_callback(_update, _context):
        raise RuntimeError("route failure")

    query = _Query()
    guarded = namespace["video_public_callback_failure_guard"](failing_callback)
    assert asyncio.run(guarded(_Update(query), None)) is True
    assert query.answers == [
        ("Không thể cập nhật lựa chọn này. Màn hiện tại và kế hoạch vẫn được giữ.", True)
    ]
    assert len(logger.entries) == 1

    non_video_query = _Query()
    non_video_query.data = "marketing|menu"
    non_video_guarded = namespace["video_public_callback_failure_guard"](failing_callback)
    try:
        asyncio.run(non_video_guarded(_Update(non_video_query), None))
    except RuntimeError as exc:
        assert str(exc) == "route failure"
    else:
        raise AssertionError("non-Video callbacks must keep their existing error owner")
    assert non_video_query.answers == []
