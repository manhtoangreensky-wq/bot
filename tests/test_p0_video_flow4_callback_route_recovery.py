from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from services import video_scene3_flow


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    sync_marker = f"\ndef {name}("
    async_marker = f"\nasync def {name}("
    positions = [position for marker in (sync_marker, async_marker) if (position := BOT_SOURCE.find(marker)) >= 0]
    start = min(positions) + 1
    candidates = [
        position
        for marker in ("\ndef ", "\nasync def ")
        if (position := BOT_SOURCE.find(marker, start + 1)) >= 0
    ]
    return BOT_SOURCE[start : min(candidates) if candidates else len(BOT_SOURCE)]


class _Button:
    def __init__(self, text: str, *, callback_data: str):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


def test_manual_editor_options_have_unique_callbacks_and_both_summary_routes_are_handled():
    namespace = {
        "InlineKeyboardButton": _Button,
        "InlineKeyboardMarkup": _Markup,
        "video_scene3_flow": video_scene3_flow,
        "ui_text": lambda _lang, key: "Quay lại" if key == "common.back" else "Menu chính",
    }
    for name in ("video_scene3_keyboard", "video_local_manual_options_keyboard"):
        exec(compile(_function_source(name), f"<flow4:{name}>", "exec"), namespace)

    markup = namespace["video_local_manual_options_keyboard"]("vi")
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert len(callbacks) == len(set(callbacks))
    assert "videoedit|source_info" in callbacks
    assert "videoedit|source_summary" in callbacks

    handler = _function_source("handle_video_editor_callback")
    assert 'if action in {"source_summary", "source_info"}:' in handler
    assert 'reply_markup=video_local_source_summary_keyboard(tool, lang, state)' in handler


def test_scene3_renderer_evaluates_only_the_active_screen():
    calls: list[str] = []

    async def safe_edit(_query, text, **kwargs):
        calls.append("safe_edit")
        return text, kwargs.get("reply_markup")

    def active_text(_state, _lang):
        calls.append("scene_count_text")
        return "scene count"

    def active_keyboard(_lang):
        calls.append("scene_count_keyboard")
        return "scene-count-keyboard"

    def unrelated_failure(*_args, **_kwargs):
        raise AssertionError("an unrelated SCENE3 screen was evaluated")

    namespace = {
        "video_scene3_flow": SimpleNamespace(normalize_state=lambda value: dict(value)),
        "video_profile_scene1_count_text": active_text,
        "video_profile_scene1_count_keyboard": active_keyboard,
        "video_scene3_post_input_text": unrelated_failure,
        "video_scene3_profile_text": unrelated_failure,
        "safe_edit_or_send": safe_edit,
        "safe_edit_or_send_long_html": safe_edit,
    }
    exec(compile(_function_source("video_profile_scene1_render"), "<flow4:scene3-render>", "exec"), namespace)

    result = asyncio.run(namespace["video_profile_scene1_render"](SimpleNamespace(), {"step": "scene_count"}, "vi"))
    assert result == ("scene count", "scene-count-keyboard")
    assert calls == ["scene_count_text", "scene_count_keyboard", "safe_edit"]


def test_video_analysis_button_opens_detailed_upload_flow_without_side_effects():
    intro = _function_source("task3d_product_intro_keyboard")
    legacy = _function_source("video_ai_true_keyboard")
    assert '("📊 Phân tích video", "videoref|analyze")' in intro
    assert '("📊 Phân tích video", "videoref|analyze")' in legacy
    assert '("📊 Phân tích video", "menu|hint_video_status")' not in intro + legacy

    events: list[tuple] = []

    class Query:
        data = "videoref|analyze"
        from_user = SimpleNamespace(id=73)

        async def answer(self):
            events.append(("answer",))

    async def safe_edit(_query, text, **kwargs):
        events.append(("render", text, kwargs.get("reply_markup")))
        return "rendered"

    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "get_user_language": lambda _uid: "vi",
        "clear_developing_video_pending": lambda uid: events.append(("clear", uid)),
        "set_developing_video_pending": lambda uid, flow, step, **fields: events.append(
            ("pending", uid, flow, step, fields)
        ),
        "safe_edit_or_send": safe_edit,
        "video_reference_analysis_start_text": lambda _lang: "analysis upload",
        "video_reference_analysis_start_keyboard": lambda _lang: "analysis-keyboard",
    }
    exec(compile(_function_source("handle_video_reference_callback"), "<flow4:analysis-handler>", "exec"), namespace)

    update = SimpleNamespace(callback_query=Query())
    assert asyncio.run(namespace["handle_video_reference_callback"](update, SimpleNamespace())) == "rendered"
    assert events == [
        ("answer",),
        ("clear", 73),
        ("pending", 73, "videoref", "await_video", {"input_type": "detailed_analysis"}),
        ("render", "analysis upload", "analysis-keyboard"),
    ]
    handler = _function_source("handle_video_reference_callback")
    forbidden = ("shopaikey", "key4u", "create_product_video_job", "wallet", "deduct")
    analyze_branch = handler[handler.index('if action == "analyze":') : handler.index('if action == "hub":')]
    assert all(token not in analyze_branch.lower() for token in forbidden)


def test_detailed_analysis_copy_separates_file_facts_from_confirmed_content():
    text_source = _function_source("video_reference_analysis_start_text")
    direction_source = _function_source("video_reference_direction_text")
    assert "phần mở đầu, chủ thể, hành động, mạch cảnh" in text_source
    assert "không tự nhận đã thấy hoặc nghe được chi tiết chưa kiểm chứng" in text_source
    assert 'detailed = str(state.get("input_type") or "") == "detailed_analysis"' in direction_source
    assert "thông tin file luôn tách riêng với nội dung do anh/chị xác nhận" in direction_source


def test_detailed_analysis_upload_runs_local_probe_and_preserves_analysis_state():
    state = {
        "flow": "videoref",
        "step": "await_video",
        "input_type": "detailed_analysis",
    }
    events: list[tuple] = []

    async def inspect(_context, source):
        events.append(("inspect", source["source_file_id"]))
        return {
            "ok": True,
            "fps": 30.0,
            "video_codec": "h264",
            "has_audio": True,
        }

    def set_pending(_uid, flow, step, **fields):
        state.update({"flow": flow, "step": step, **fields})
        events.append(("pending", step))

    class Message:
        async def reply_text(self, text, **kwargs):
            events.append(("reply", text, kwargs.get("reply_markup")))

    info = {
        "file_id": "telegram-video",
        "file_name": "sample.mp4",
        "mime_type": "video/mp4",
        "duration": 18,
        "file_size": 1024 * 1024,
        "width": 1080,
        "height": 1920,
    }
    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "get_developing_video_pending": lambda _uid: dict(state),
        "video_reference_media_info": lambda _message: dict(info),
        "get_user_language": lambda _uid: "vi",
        "video_reference_analysis_start_keyboard": lambda _lang: "analysis-retry",
        "video_reference_start_keyboard": lambda _lang: "reference-retry",
        "VIDEO_ANALYZE_ENABLED": True,
        "VIDEO_SAMPLE_MAX_SECONDS": 600,
        "VIDEO_SAMPLE_MAX_MB": 100,
        "normalize_user_language": lambda lang: lang,
        "remember_last_media": lambda _update: events.append(("remember",)),
        "cache_recent_media_state": lambda _update: events.append(("cache",)),
        "add_reference_video": lambda *_args, **_kwargs: 0,
        "_safe_int": lambda value, default=0: int(value or default),
        "video_local_validation": SimpleNamespace(MAX_UPLOAD_BYTES=50 * 1024 * 1024),
        "inspect_video_editor_source": inspect,
        "logger": SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        "set_developing_video_pending": set_pending,
        "video_reference_direction_text": lambda current, _lang: f"direction:{current.get('source_fps')}",
        "video_reference_direction_keyboard": lambda _lang: "direction-keyboard",
    }
    exec(compile(_function_source("handle_video_reference_pending_upload"), "<flow4:analysis-upload>", "exec"), namespace)
    update = SimpleNamespace(message=Message(), effective_user=SimpleNamespace(id=73))

    assert asyncio.run(namespace["handle_video_reference_pending_upload"](update, SimpleNamespace())) is True
    assert state["step"] == "direction"
    assert state["input_type"] == "detailed_analysis"
    assert state["source_fps"] == 30.0
    assert state["source_video_codec"] == "h264"
    assert state["source_has_audio"] == "yes"
    assert ("inspect", "telegram-video") in events
    assert events[-1] == ("reply", "direction:30.0", "direction-keyboard")


def test_flow4_scope_keeps_provider_and_wallet_paths_untouched():
    changed_runtime = {"bot.py"}
    assert not changed_runtime & {
        "services/video_provider_router.py",
        "services/video_real_render_connector.py",
        "remote_worker.py",
        "local_worker.py",
        "services/payment.py",
    }
