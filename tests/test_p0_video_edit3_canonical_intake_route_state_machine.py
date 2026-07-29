from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import video_edit_state_machine, video_local_editing


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    async_marker = f"async def {name}("
    sync_marker = f"def {name}("
    start = BOT_SOURCE.find(async_marker)
    if start < 0:
        start = BOT_SOURCE.index(sync_marker)
    candidates = [BOT_SOURCE.find("\ndef ", start + 1), BOT_SOURCE.find("\nasync def ", start + 1)]
    ends = [position for position in candidates if position >= 0]
    return BOT_SOURCE[start:min(ends) if ends else len(BOT_SOURCE)]


def _compile_function(name: str, namespace: dict):
    module = ast.parse("from __future__ import annotations\n\n" + _function_source(name))
    exec(compile(module, filename="bot.py", mode="exec"), namespace)
    return namespace[name]


@pytest.mark.parametrize(
    ("mode", "ready"),
    [
        ("manual_edit", "manual_edit"),
        ("ai_edit", "ai_edit"),
        ("quality_enhance", "quality_enhance"),
    ],
)
def test_edit3_lane_state_has_one_canonical_contract(mode: str, ready: str) -> None:
    state = video_edit_state_machine.start_lane(mode)
    assert state == {
        "step": "await_edit_video",
        "edit_mode": mode,
        "current_screen": f"{mode}_upload",
        "return_to": "videoedit|hub",
        "awaiting_media": True,
        "source_file_id": None,
        "last_media_message_id": 0,
        "intake_in_progress": False,
        "probe_count": 0,
    }
    complete = video_edit_state_machine.complete_intake(
        state,
        {"source_file_id": "file-1", "source_file_name": "input.mp4"},
        {"ok": True, "duration": 8.0},
    )
    assert complete["step"] == ready
    assert complete["current_screen"] == ready
    assert complete["awaiting_media"] is False
    assert complete["probe_count"] == 1


def _run_canonical_upload(mode: str, *, valid: bool = True):
    persisted = video_edit_state_machine.start_lane(mode)
    replies: list[dict] = []
    probes: list[str] = []

    class Message:
        message_id = 901
        video = SimpleNamespace(
            file_id="video-file-901",
            file_name="source.mp4",
            mime_type="video/mp4",
            file_size=1_024,
            duration=8,
        )
        document = None

        async def reply_text(self, text: str, **kwargs):
            replies.append({"text": text, **kwargs})
            return True

    update = SimpleNamespace(effective_user=SimpleNamespace(id=78), message=Message())
    context = SimpleNamespace(bot=SimpleNamespace(), user_data={})

    async def inspect(_context, source):
        probes.append(str(source.get("source_file_id") or ""))
        if not valid:
            return {"ok": False, "reason": "invalid_video_metadata"}
        return {
            "ok": True,
            "bytes": 1_024,
            "duration": 8.0,
            "duration_ms": 8_000,
            "width": 1_080,
            "height": 1_920,
            "fps": 30.0,
            "has_audio": True,
            "audio_stream_count": 1,
            "format_name": "mov,mp4",
        }

    def save(_uid: int, state: dict) -> dict:
        persisted.clear()
        persisted.update(state)
        return dict(persisted)

    handler = _compile_function(
        "handle_video_editor_pending_upload",
        {
            "get_video_editor_pending": lambda _uid: dict(persisted),
            "video_edit_state_machine": video_edit_state_machine,
            "safe_int": lambda value, default=0: int(value or default),
            "save_video_edit_canonical_state": save,
            "clear_video_editor_competing_video_states": lambda _uid, _context: {},
            "get_user_language": lambda _uid: "vi",
            "video_editor_source_from_update": lambda _update: {
                "source_file_id": "video-file-901",
                "source_file_name": "source.mp4",
                "source_mime_type": "video/mp4",
                "source_file_size": 1_024,
                "source_duration": 8,
            },
            "inspect_video_editor_source": inspect,
            "video_editor_telegram_probe_fallback": lambda _source, _reason: {},
            "video_local_validation": SimpleNamespace(
                LocalVideoValidationError=RuntimeError,
                safe_display_filename=lambda value: value,
            ),
            "logger": SimpleNamespace(warning=lambda *_args, **_kwargs: None),
            "sanitize_log_text": str,
            "video_local_public_error": lambda reason: f"invalid:{reason}",
            "video_edit_lane_upload_keyboard": lambda lane, _lang: f"upload:{lane}",
            "cache_recent_media_state": lambda _update: "video",
            "video_local_editing": video_local_editing,
            "video_local_manual_options_text": lambda _state, _lang: "manual-screen",
            "video_local_manual_options_keyboard": lambda _lang: "manual-keyboard",
            "video_ai_edit_router": SimpleNamespace(DEFAULT_PRESERVE_CONTROLS={"identity": True}),
            "video_quality_enhance_source_text": lambda _state, _lang: "quality-screen",
            "video_quality_enhance_source_keyboard": lambda _lang: "quality-keyboard",
            "video_ai_edit_source_summary_text": lambda _state, _lang: "ai-screen",
            "video_ai_edit_source_summary_keyboard": lambda _lang, _state: "ai-keyboard",
        },
    )
    first = asyncio.run(handler(update, context))
    second = asyncio.run(handler(update, context))
    return first, second, persisted, replies, probes


@pytest.mark.parametrize(
    ("mode", "screen"),
    [
        ("manual_edit", "manual-screen"),
        ("ai_edit", "ai-screen"),
        ("quality_enhance", "quality-screen"),
    ],
)
def test_edit3_one_upload_probes_once_and_routes_to_exact_lane(mode: str, screen: str) -> None:
    first, second, state, replies, probes = _run_canonical_upload(mode)
    assert first is True and second is True
    assert probes == ["video-file-901"]
    assert len(replies) == 1
    assert replies[0]["text"] == screen
    assert state["edit_mode"] == mode
    assert state["current_screen"] == mode
    assert state["awaiting_media"] is False
    assert state["source_file_id"] == "video-file-901"
    assert state["probe_count"] == 1


def test_edit3_invalid_upload_replies_once_and_keeps_active_lane() -> None:
    first, second, state, replies, probes = _run_canonical_upload("manual_edit", valid=False)
    assert first is True and second is True
    assert probes == ["video-file-901"]
    assert len(replies) == 1
    assert state["edit_mode"] == "manual_edit"
    assert state["step"] == "await_edit_video"
    assert state["awaiting_media"] is True
    assert state["source_file_id"] is None
    assert state["last_error"] == "invalid_video_metadata"


def test_edit3_invalid_text_replies_once_and_keeps_session_for_retry() -> None:
    persisted = video_edit_state_machine.start_lane("ai_edit")
    replies: list[dict] = []

    class Message:
        message_id = 902
        text = "đây không phải video"

        async def reply_text(self, text: str, **kwargs):
            replies.append({"text": text, **kwargs})
            return True

    update = SimpleNamespace(effective_user=SimpleNamespace(id=78), message=Message())

    def save(_uid: int, state: dict) -> dict:
        persisted.clear()
        persisted.update(state)
        return dict(persisted)

    handler = _compile_function(
        "handle_video_editor_invalid_intake_text",
        {
            "get_video_editor_pending": lambda _uid: dict(persisted),
            "video_edit_state_machine": video_edit_state_machine,
            "safe_int": lambda value, default=0: int(value or default),
            "save_video_edit_canonical_state": save,
            "get_user_language": lambda _uid: "vi",
            "video_edit_lane_upload_keyboard": lambda lane, _lang: f"upload:{lane}",
        },
    )
    assert asyncio.run(handler(update, SimpleNamespace())) is True
    assert asyncio.run(handler(update, SimpleNamespace())) is True
    assert len(replies) == 1
    assert persisted["edit_mode"] == "ai_edit"
    assert persisted["awaiting_media"] is True
    assert persisted["source_file_id"] is None
    assert persisted["last_error"] == "video_file_required"


def test_edit3_back_matrix_never_targets_creation_scene3_or_global_help() -> None:
    assert video_edit_state_machine.back_target("manual_edit") == "videoedit|hub"
    assert video_edit_state_machine.back_target("ai_edit") == "videoedit|hub"
    assert video_edit_state_machine.back_target("quality_enhance") == "videoedit|hub"
    assert video_edit_state_machine.back_target("manual_edit", child=True) == "videoedit|manual"
    assert video_edit_state_machine.back_target("ai_edit", child=True) == "videoedit|ai"
    assert video_edit_state_machine.back_target("quality_enhance", child=True) == "videoedit|restore"
    module_source = (ROOT / "services" / "video_edit_state_machine.py").read_text(encoding="utf-8")
    for leaked_route in ("SCENE3", "create_video", "menu|guide", "guide_video_ai"):
        assert leaked_route not in module_source


def test_edit3_single_registered_video_media_gateway_and_read_only_legacy_callbacks() -> None:
    media = _function_source("handle_media_cache_only")
    documents = _function_source("handle_document_cache_only")
    audio = _function_source("handle_media")
    photo = _function_source("handle_photo")
    assert media.count("handle_video_editor_pending_upload(update, context)") == 1
    assert documents.count("handle_video_editor_pending_upload(update, context)") == 1
    assert audio.count("handle_video_editor_pending_upload(update, context)") == 1
    assert photo.count("handle_video_editor_pending_upload(update, context)") == 1
    assert BOT_SOURCE.count("async def handle_video_editor_pending_upload(") == 1

    callback = _function_source("handle_video_editor_callback")
    compatibility_start = callback.index("requested_group = video_edit_state_machine.requested_group(raw_action)")
    compatibility_end = callback.index("if action == \"guide\"")
    compatibility = callback[compatibility_start:compatibility_end]
    assert "canonical_compatibility_action(raw_action)" in compatibility
    assert "set_video_editor_pending" not in compatibility
    assert "update_video_editor_pending" not in compatibility
    assert "clear_video_editor_pending" not in compatibility


def test_edit3_probe_contract_exposes_required_local_metadata_without_side_effects() -> None:
    probe = _function_source("inspect_video_editor_source")
    intake = _function_source("handle_video_editor_pending_upload")
    validation = (ROOT / "services" / "video_local_validation.py").read_text(encoding="utf-8")
    assert "probe_video_file" in probe
    assert "audio_stream_count" in validation
    assert "format_name" in validation
    canonical = intake[:intake.index('step = str(state.get("step") or "")')]
    assert canonical.count("inspect_video_editor_source(context, source)") == 1
    for forbidden in (
        "create_local_worker_job",
        "submit_video_ai_edit_job",
        "submit_local_video_editor_job",
        "spend_fixed_credit_info",
        "wallet",
    ):
        assert forbidden not in canonical
