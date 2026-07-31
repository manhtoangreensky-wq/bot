from __future__ import annotations

import asyncio
from pathlib import Path
import re
from types import SimpleNamespace

from services import video_edit_state_machine
from services import video_flow6
from services import video_idea_handoff
from services import video_idea_prompt
from services import video_local_editing
from services import video_tail9


CANONICAL_POSITIONS = {
    "top_left", "top_center", "top_right",
    "center_left", "center", "center_right",
    "bottom_left", "bottom_center", "bottom_right",
}
ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _base_plan() -> dict:
    return {
        "input_video": "source.mp4",
        "trim": {"start_ms": 0, "end_ms": 8_000},
        "text_overlay": {
            "content": "Watermark TOAN AAS",
            "position": "bottom_center",
            "start_ms": 0,
            "end_ms": 8_000,
        },
        "logo_overlay": {
            "path": "logo.png",
            "position": "top_right",
            "scale": 0.12,
            "opacity": 1.0,
        },
    }


def test_tail_logo_and_watermark_share_the_full_nine_position_grid() -> None:
    start = BOT_SOURCE.index("PRODUCT_VIDEO_LOGO_POSITIONS =")
    end = BOT_SOURCE.index("PRODUCT_VIDEO_LOGO_DEFAULT_WIDTH_RATIO", start)
    catalog = BOT_SOURCE[start:end]
    assert all(f'"{position}"' in catalog for position in CANONICAL_POSITIONS)
    keyboard_start = BOT_SOURCE.index("def video_tail9_position_keyboard")
    keyboard_end = BOT_SOURCE.index("def video_tail9_catalog_report", keyboard_start)
    keyboard = BOT_SOURCE[keyboard_start:keyboard_end]
    for position in CANONICAL_POSITIONS:
        assert f'"{position}"' in keyboard
    assert "video_tail|logo|setpos|{target}|{position}" in keyboard
    assert "labels[0:3]" in keyboard
    assert "labels[3:6]" in keyboard
    assert "labels[6:9]" in keyboard
    assert "video_tail|logo|open" in keyboard
    assert "menu|main" in keyboard


def test_logo_hub_starts_each_branding_flow_before_the_nine_position_grid() -> None:
    start = BOT_SOURCE.index("def video_tail9_logo_keyboard")
    end = BOT_SOURCE.index("def video_tail9_position_text", start)
    keyboard = BOT_SOURCE[start:end]
    assert "video_tail|logo|upload" in keyboard
    assert "video_tail|logo|watermark" in keyboard
    assert "video_tail|logo|position|logo" not in keyboard
    assert "video_tail|logo|position|watermark" not in keyboard
    assert "video_tail|review|prompts" in keyboard
    assert "video_tail|summary|open" in keyboard
    assert "video_tail|review|open" not in keyboard


def test_local_editor_preserves_each_canonical_overlay_position() -> None:
    for position in CANONICAL_POSITIONS:
        plan = _base_plan()
        plan["text_overlay"]["position"] = position
        plan["logo_overlay"]["position"] = position
        normalized = video_local_editing.normalize_manual_edit_plan(
            plan,
            source_duration_ms=8_000,
        )
        assert normalized["text_overlay"]["position"] == position
        assert normalized["logo_overlay"]["position"] == position
        command = video_local_editing.build_manual_ffmpeg_command(
            normalized,
            output_path="output.mp4",
            source_probe={"width": 1280, "height": 720, "has_audio": True},
            ffmpeg_path="ffmpeg",
        )
        complex_filter = command[command.index("-filter_complex") + 1]
        assert "overlay=" in complex_filter
        assert "drawtext=" in complex_filter


def test_tail_audio_completion_routes_to_unified_summary_and_back_to_branding() -> None:
    start = BOT_SOURCE.index("async def handle_video_tail_callback")
    end = BOT_SOURCE.index("async def handle_video_tail9_pending_text", start)
    handler = BOT_SOURCE[start:end]
    audio = handler[handler.index('if section == "audio":'):handler.index('if section == "logo":')]
    assert audio.count('video_tail9_render(query, uid, context, "summary")') == 1
    assert "video_tail9_open_planning_audio" in audio
    assert 'video_tail9_render(query, uid, context, "quality")' not in audio
    assert 'video_tail9_render(query, uid, context, "logo")' not in audio
    assert 'action in {"back", "done", "skip"}' in audio


def test_scene3_audio_callbacks_are_the_canonical_audio_owner() -> None:
    handler = _async_function_source("handle_video_profile_studio_callback")
    assert 'if action == "audio_open":' in handler
    assert 'post_return_step="audio_plan"' in handler
    assert 'if action == "audio_review":' in handler
    assert 'if action in {"audio_done", "audio_skip"}:' in handler
    assert 'return_step == "summary"' in handler
    assert 'video_tail9_render(query, uid, context, "audio")' not in handler


def test_legacy_review_and_logo_callbacks_do_not_skip_the_canonical_tail() -> None:
    handler = _async_function_source("handle_video_profile_studio_callback")
    review = handler[handler.index('if action == "review_post":'):handler.index('if action == "review_summary":')]
    assert 'video_tail9_render(query, uid, context, "logo")' in review

    post_skip = handler[handler.index('if action == "post_skip":'):handler.index('if action == "post_suggest":')]
    post_done = handler[handler.index('if action == "post_done":'):handler.index('if action == "ratio":')]
    assert 'video_tail9_render(query, uid, context, "summary")' in post_skip
    assert 'video_tail9_render(query, uid, context, "summary")' in post_done

    review_done = handler[handler.index('if action in {"review_done", "review_continue"}:'):handler.index('if action == "post_toggle":')]
    assert 'video_tail9_render(query, uid, context, "logo")' in review_done
    assert 'video_tail9_render(query, uid, context, "audio")' not in review_done


def test_logo_and_watermark_need_a_nine_position_confirmation_before_enable() -> None:
    handler = _async_function_source("handle_video_tail_callback")
    logo = handler[handler.index('if section == "logo":'):handler.index('if section == "quality":')]
    assert 'if action == "setpos":' in logo
    assert 'if action == "confirm":' in logo
    assert logo.index('if action == "setpos":') < logo.index('if action == "confirm":')
    assert 'tail["brand_pending_target"] = argument' in logo
    assert 'tail["brand_pending_position"] = extra' in logo
    assert 'video_tail9_render(query, uid, context, "logo_confirm")' in logo
    assert 'config["enabled"] = True' in logo


def test_tail_logo_and_watermark_intakes_wait_for_position_confirmation() -> None:
    watermark_input = _async_function_source("handle_video_tail9_pending_text")
    assert 'watermark.update({"enabled": False, "text": text[:120], "position": ""})' in watermark_input
    assert 'tail["brand_pending_target"] = "watermark"' in watermark_input
    assert 'video_tail9_position_keyboard("watermark")' in watermark_input

    public_media = _async_function_source("handle_video_product_pending_media")
    assert 'tail["brand_pending_target"] = "logo"' in public_media
    assert '"enabled": False' in public_media[public_media.index('if current_step == "awaiting_video_tail9_logo":'):]
    assert 'video_tail9_position_keyboard("logo")' in public_media

    edit_media = _async_function_source("handle_video_editor_pending_upload")
    assert 'tail["brand_pending_target"] = "logo"' in edit_media
    assert 'video_tail9_position_keyboard("logo")' in edit_media


def test_tail_summary_is_a_valid_canonical_stage() -> None:
    state = video_tail9.normalize_state({"status_stage": "summary"})
    assert state["status_stage"] == "summary"
    assert video_tail9.public_progress(state) == 5


def test_watermark_submission_keeps_the_exact_three_by_three_position() -> None:
    start = BOT_SOURCE.index("async def submit_local_video_editor_job")
    end = BOT_SOURCE.index("async def", start + 1)
    submission = BOT_SOURCE[start:end]
    assert "logo_watermark_normalize_position" in submission
    assert '"position": position' in submission
    assert "text_position =" not in submission


def _function_source(name: str) -> str:
    match = re.search(rf"^def {re.escape(name)}\(", BOT_SOURCE, re.MULTILINE)
    assert match, f"missing function: {name}"
    next_match = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[match.end() :])
    end = match.end() + next_match.start() if next_match else len(BOT_SOURCE)
    return BOT_SOURCE[match.start() : end]


def _async_function_source(name: str) -> str:
    match = re.search(rf"^async def {re.escape(name)}\(", BOT_SOURCE, re.MULTILINE)
    assert match, f"missing async function: {name}"
    next_match = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[match.end() :])
    end = match.end() + next_match.start() if next_match else len(BOT_SOURCE)
    return BOT_SOURCE[match.start() : end]


def test_scene3_handoff_keeps_the_completed_content_contract_for_tail_preflight() -> None:
    saved: dict = {}

    def compile_contract(_state: dict, *, product_type: str) -> dict:
        return {
            "product_type": product_type,
            "content_mode": "suggestions",
            "canonical_content_mode": "idea_catalog",
            "content_source": "idea_catalog",
            "content_choice": {"id": "idea-demo", "title": "Mở hộp và hé lộ sản phẩm"},
            "idea_preset_id": "idea-demo",
            "selected_prompt": "Mạch kể rõ, chuyển cảnh tự nhiên.",
            "per_scene_content": [{"scene_number": 1, "goal": "Mở đầu"}],
            "content_revision": 3,
            "flow_owner": "scene3",
            "parent_session_id": "parent-session",
        }

    namespace = {
        "default_video_session": lambda _uid: {},
        "video_profile_scene1_storyboard_payload": lambda _state: {"profile": {"profile_id": "storytelling"}},
        "safe_int": lambda value, default=0: int(value) if str(value or "").isdigit() else default,
        "video_b14_default_addon_plan": lambda _profile: {},
        "video_b14_lock_product_video_addons": lambda addons: dict(addons),
        "video_flow6_product_id": lambda _state: "video_ai_real",
        "video_tail12_compile_content_contract": compile_contract,
        "video_flow6": SimpleNamespace(
            context_from_scene_state=lambda contract: {"flow_kind": "ai_real", "content_mode": contract["content_mode"]},
            execution_route_for=lambda _context: {"job_type": "product_video"},
        ),
        "video_b14_prompt_bundle_from_plan_payload": lambda _storyboard: {},
        "video_profile_catalog": SimpleNamespace(SCHEMA_VERSION=1),
        "save_video_session": lambda _uid, session: saved.setdefault("session", session),
    }
    exec(_function_source("video_profile_scene1_handoff"), namespace)

    result = namespace["video_profile_scene1_handoff"](
        7,
        {"scene_count": 2, "subject": "Demo", "plan": {"scenes": []}},
    )

    draft = result["draft"]
    assert draft["content_mode"] == "suggestions"
    assert draft["content_source"] == "idea_catalog"
    assert draft["content_choice"]["id"] == "idea-demo"
    assert draft["selected_prompt"]
    assert draft["per_scene_content"] == [{"scene_number": 1, "goal": "Mở đầu"}]
    assert draft["scene3_data_contract"]["content_mode"] == "suggestions"
    assert draft["scene3_data_contract"]["selected_prompt"] == draft["selected_prompt"]


def test_tail_hydrates_missing_scene3_content_from_its_persisted_handoff_only() -> None:
    namespace: dict = {}
    exec(_function_source("video_tail9_hydrate_scene3_host"), namespace)

    hydrate = namespace["video_tail9_hydrate_scene3_host"]
    result = hydrate(
        {
            "product_type": "video_ai_real",
            "scene_count": 2,
            "content_source": "",
            "selected_prompt": "",
            "content_choice": {},
        },
        {
            "draft": {
                "content_source": "idea_catalog",
                "selected_profile": "product_review",
                "content_choice": {"id": "idea-demo", "title": "Mở hộp"},
                "selected_prompt": "Mạch kể rõ và khép bằng kết quả.",
                "scene3_data_contract": {
                    "content_mode": "suggestions",
                    "canonical_content_mode": "idea_catalog",
                    "per_scene_content": [{"scene_number": 1, "goal": "Mở đầu"}],
                    "content_revision": 2,
                },
            },
        },
    )

    assert result["content_mode"] == "suggestions"
    assert result["canonical_content_mode"] == "idea_catalog"
    assert result["content_source"] == "idea_catalog"
    assert result["selected_profile"] == "product_review"
    assert result["content_choice"]["id"] == "idea-demo"
    assert result["selected_prompt"] == "Mạch kể rõ và khép bằng kết quả."
    assert result["per_scene_content"] == [{"scene_number": 1, "goal": "Mở đầu"}]

    newer = hydrate(
        {"content_source": "manual", "selected_prompt": "Prompt khách vừa sửa"},
        {"draft": {"content_source": "idea_catalog", "selected_prompt": "Prompt cũ"}},
    )
    assert newer["content_source"] == "manual"
    assert newer["selected_prompt"] == "Prompt khách vừa sửa"


def test_idea_parent_handoff_keeps_the_preset_profile_for_video_ai_preflight() -> None:
    parent = video_idea_handoff.build_parent_handoff(
        {
            "flow_session_id": "idea-parent-7",
            "flow_revision": 2,
            "scene_count": 2,
            "aspect_ratio": "9:16",
            "selected_profile": "product_review",
        },
        product_id="video_ai_real",
        return_callback="vproduct|content_source|video_ai_real",
    )
    state = {
        "idea_parent_product": "video_ai_real",
        "idea_parent_session_id": parent["idea_parent_session_id"],
        "idea_parent_revision": parent["idea_parent_revision"],
        "scene_count": 2,
        "aspect_ratio": "9:16",
        "idea_id": "review-demo",
        "idea_preset_id": 14,
        "idea_selected_prompt": "Giới thiệu rõ, hành động trọn vẹn và kết cảnh tự nhiên.",
        "idea_preset_content": {
            "preset_key": "review-demo",
            "title": "Review demo sản phẩm",
            "recommended_profile_id": "product_review",
        },
        "scene_drafts": [
            {"scene_index": 1, "content": "Mở vấn đề và sản phẩm."},
            {"scene_index": 2, "content": "Trải nghiệm, kết quả và lời mời."},
        ],
    }

    hydrated = video_idea_prompt.hydrate_parent_state(state, parent)

    assert hydrated["selected_profile"] == "product_review"
    assert hydrated["primary_profile"] == "product_review"
    assert hydrated["primary_profile_key"] == "product_review"

    context = video_flow6.context_from_scene_state({
        "product_type": "video_ai_real",
        "content_mode": "suggestions",
        "content_source": "idea_catalog",
        "scene_count": 2,
        "aspect_ratio": "9:16",
        "selected_profile": hydrated["selected_profile"],
        "content_choice": {"id": "review-demo", "title": "Review demo sản phẩm"},
        "idea_preset_id": "review-demo",
    })
    preflight = video_flow6.preflight(
        context,
        package_available=True,
        engine_ready=True,
        worker_ready=True,
        capability_ready=True,
        duration_seconds=16,
    )

    assert context["primary_profile_key"] == "product_review"
    assert preflight["ok"] is True


def test_idea_scene3_and_parent_return_keep_the_selected_profile_contract() -> None:
    scene3 = _function_source("video_idea_dynamic_scene3_state")
    parent_render = _async_function_source("video_idea_render_exact_parent")
    continuation = _async_function_source("video_idea_continue_to_exact_parent")

    assert 'preset_content.get("recommended_profile_id")' in scene3
    assert '"primary_profile_key": selected_profile' in scene3
    assert '"primary_profile": selected_profile' in scene3
    assert 'preset_content.get("recommended_profile_id")' in parent_render
    assert '"primary_profile_key": selected_profile' in parent_render
    assert 'preset_content.get("recommended_profile_id")' in continuation
    assert '"primary_profile_key": selected_profile' in continuation


def test_tail_context_hydrates_handoff_before_compiling_the_commercial_contract() -> None:
    start = BOT_SOURCE.index("def video_tail9_context")
    end = BOT_SOURCE.index("def save_video_tail9_state", start)
    context = BOT_SOURCE[start:end]
    hydrate_at = context.index("video_tail9_hydrate_scene3_host(host, session)")
    compile_at = context.index("video_tail12_compile_content_contract(host")
    assert hydrate_at < compile_at


def test_product_media_intake_failures_stay_inside_their_own_product_owner() -> None:
    assert "async def recover_product_video_media_failure(" in BOT_SOURCE
    assert "def product_video_media_failure_guard(media_handler):" in BOT_SOURCE
    assert (
        "@product_video_media_failure_guard\n@video_editor_message_state_guard\n"
        "async def handle_video_editor_pending_upload"
    ) in BOT_SOURCE
    assert "@product_video_media_failure_guard\nasync def handle_frame_video_pending_media" in BOT_SOURCE

    recovery_start = BOT_SOURCE.index("async def recover_product_video_media_failure(")
    recovery_end = BOT_SOURCE.index("def product_video_media_failure_guard", recovery_start)
    recovery = BOT_SOURCE[recovery_start:recovery_end]
    assert 'handler_name == "handle_video_editor_pending_upload"' in recovery
    assert 'handler_name == "handle_frame_video_pending_media"' in recovery
    assert "video_edit_lane_upload_keyboard(mode, lang)" in recovery
    assert "video_local_manual_options_keyboard(lang, current)" in recovery
    assert "frame_video3_current_screen(state, lang)" in recovery
    assert "last_recovery_message_id" in recovery
    assert "last_media_recovery_message_id" in recovery


def test_recovery_keeps_logo_intake_and_never_routes_media_to_another_product() -> None:
    recovery_start = BOT_SOURCE.index("async def recover_product_video_media_failure(")
    recovery_end = BOT_SOURCE.index("def product_video_media_failure_guard", recovery_start)
    recovery = BOT_SOURCE[recovery_start:recovery_end]
    assert 'step == "awaiting_video_tail9_logo"' in recovery
    assert "video_tail|logo|open" in recovery
    assert "menu|main" in recovery
    assert "video_tail9_render" not in recovery
    assert "framevideo|" not in recovery.split('handler_name == "handle_video_editor_pending_upload"', 1)[1].split('handler_name == "handle_frame_video_pending_media"', 1)[0]


def test_video_edit_upload_recovery_keeps_the_lane_and_replies_once() -> None:
    start = BOT_SOURCE.index("def video_edit_recovery_mode")
    end = BOT_SOURCE.index("def product_video_media_failure_guard", start)
    namespace = {
        "video_edit_state_machine": video_edit_state_machine,
        "get_user_language": lambda _uid: "vi",
        "safe_int": lambda value, default=0: int(value) if str(value or "").isdigit() else default,
        "video_edit_lane_upload_keyboard": lambda mode, _lang: f"upload:{mode}",
    }
    exec("from __future__ import annotations\n" + BOT_SOURCE[start:end], namespace)

    persisted = video_edit_state_machine.start_lane("manual_edit")
    persisted["step"] = "await_edit_video"
    replies: list[dict] = []

    class Message:
        message_id = 991

        async def reply_text(self, text: str, **kwargs):
            replies.append({"text": text, **kwargs})
            return True

    def save(_uid: int, state: dict) -> dict:
        persisted.clear()
        persisted.update(state)
        return dict(persisted)

    namespace.update({
        "get_video_editor_pending": lambda _uid: dict(persisted),
        "save_video_edit_canonical_state": save,
    })
    update = SimpleNamespace(effective_user=SimpleNamespace(id=77), message=Message())
    recover = namespace["recover_product_video_media_failure"]

    assert asyncio.run(recover(update, SimpleNamespace(), handler_name="handle_video_editor_pending_upload")) is True
    assert asyncio.run(recover(update, SimpleNamespace(), handler_name="handle_video_editor_pending_upload")) is True
    assert len(replies) == 1
    assert persisted["edit_mode"] == "manual_edit"
    assert persisted["awaiting_media"] is True
    assert persisted["source_file_id"] is None
    assert persisted["last_error"] == "video_edit_intake_runtime_error"
    assert replies[0]["reply_markup"] == "upload:manual_edit"


def test_framevideo_assets_done_opens_duration_once_after_exact_image_count() -> None:
    persisted: dict = {}
    rendered: list[dict] = []

    async def safe_edit_or_send(_query, text: str, **kwargs):
        rendered.append({"text": text, **kwargs})
        return True

    namespace = {
        "normalize_frame_video_state": lambda value: dict(value or {}),
        "_safe_int": lambda value, default=0: int(value) if str(value or "").isdigit() else default,
        "ivf": SimpleNamespace(frame_video_image_count_text=lambda _count, _lang: "count"),
        "frame_video_duration_menu_text": lambda value: f"duration:{len(value.get('photos') or [])}",
        "frame_video_duration_menu_keyboard": lambda _per_image, _state: "duration-menu",
        "set_frame_video_state": lambda _uid, value: persisted.update(value),
        "safe_edit_or_send": safe_edit_or_send,
    }
    exec("from __future__ import annotations\n" + _async_function_source("handle_frame_video_assets_done"), namespace)

    state = {"image_count": 2, "photos": [{"id": "one"}, {"id": "two"}]}
    result = asyncio.run(
        namespace["handle_frame_video_assets_done"](
            SimpleNamespace(),
            SimpleNamespace(),
            18,
            "vi",
            state,
        )
    )

    assert result is True
    assert persisted["step"] == "duration"
    assert rendered == [{"text": "duration:2", "parse_mode": "HTML", "reply_markup": "duration-menu"}]
