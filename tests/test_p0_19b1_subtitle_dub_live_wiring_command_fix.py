import asyncio
import inspect
from types import SimpleNamespace

import bot
from services import provider_gate


class FakeMessage:
    chat_id = 901901
    message_id = 1

    def __init__(self, text=""):
        self.text = text
        self.sent = []

    async def reply_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.sent.append(item)
        return SimpleNamespace(**item)


class FakeQuery:
    def __init__(self, user_id: int, data: str):
        self.from_user = SimpleNamespace(id=user_id, first_name="P019B1")
        self.data = data
        self.message = FakeMessage()
        self.answered = False
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.answered = True

    async def edit_message_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.edits.append(item)
        return SimpleNamespace(**item)


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


async def _run_command(handler, text, args=None, user_id=901900):
    message = FakeMessage(text)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=user_id), message=message)
    await handler(update, SimpleNamespace(args=list(args or [])))
    assert message.sent
    return message.sent[-1]["text"]


def _admin(monkeypatch):
    monkeypatch.setattr(bot, "p0_18a_admin_allowed", lambda _uid: True)
    monkeypatch.setattr(bot, "save_tool_test_result", lambda *_args, **_kwargs: None)


def test_tool_subtitle_from_storyboard_command_executes(monkeypatch):
    _admin(monkeypatch)
    text = asyncio.run(_run_command(bot.cmd_tool_test_subtitle_from_storyboard, "/tool_test_subtitle_from_storyboard --fake", args=[]))
    assert "OWNER/ADMIN TEST MODE" in text
    assert "Transcript: <code>YES</code>" in text
    assert "SRT artifact: <code>YES</code>" in text
    assert "Timestamp valid: <code>YES</code>" in text
    assert "Provider: <code>NO</code>" in text
    assert "Result: <code>PASS</code>" in text
    assert "Dùng <code>" not in text


def test_tool_mux_failure_command_executes(monkeypatch):
    _admin(monkeypatch)
    text = asyncio.run(_run_command(bot.cmd_tool_test_subtitle_dub_mux_failure, "/tool_test_subtitle_dub_mux_failure --fake-files", args=[]))
    assert "Transcript/SRT: <code>PASS</code>" in text
    assert "Dub audio: <code>PASS</code>" in text
    assert "Mux MP4: <code>FAIL as expected</code>" in text
    assert "Partial result audio/SRT available: <code>YES</code>" in text
    assert "Provider: <code>NO</code>" in text
    assert "Result: <code>PASS</code>" in text
    assert "Dùng <code>" not in text


def test_tool_uploaded_video_guard_command_executes(monkeypatch):
    _admin(monkeypatch)
    text = asyncio.run(_run_command(bot.cmd_tool_test_uploaded_video_subtitle_guard, "/tool_test_uploaded_video_subtitle_guard --fake", args=[]))
    assert "Uploaded video state: <code>YES</code>" in text
    assert "Language selection route: <code>YES</code>" in text
    assert "Confirm gate: <code>YES</code>" in text
    assert "Provider before confirm: <code>NO</code>" in text
    assert "Charge before confirm: <code>NO</code>" in text
    assert "Public copy safe: <code>YES</code>" in text
    assert "Result: <code>PASS</code>" in text
    assert "Dùng <code>" not in text


def test_tool_commands_do_not_return_usage_when_flags_valid(monkeypatch):
    _admin(monkeypatch)
    cases = [
        (bot.cmd_tool_test_subtitle_from_storyboard, "/tool_test_subtitle_from_storyboard --fake"),
        (bot.cmd_tool_test_subtitle_dub_mux_failure, "/tool_test_subtitle_dub_mux_failure --fake-files"),
        (bot.cmd_tool_test_uploaded_video_subtitle_guard, "/tool_test_uploaded_video_subtitle_guard --fake"),
    ]
    for handler, text in cases:
        output = asyncio.run(_run_command(handler, text, args=[]))
        assert "Dùng <code>" not in output
        assert "Result: <code>PASS</code>" in output


def test_uploaded_video_language_selection_opens_confirm_or_clear_guard(monkeypatch):
    uid = 901910
    bot.clear_video_dubbing_pending(uid)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "video_dubbing_configured_readiness", lambda *_args, **_kwargs: {"missing": ["asr"]})
    bot.set_video_dubbing_pending(
        uid,
        "language",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        process_type=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        source_file_id="tg-video",
        video_file_id="tg-video",
        source_file_name="uploaded.mp4",
        source_mime_type="video/mp4",
        media_kind="video",
        source_kind="media",
        entry_surface="public_type",
    )
    query = FakeQuery(uid, "videodub|language|English")
    result = asyncio.run(bot.handle_video_dubbing_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    text = result.text
    assert "Tính năng dịch phụ đề từ video tải lên đang tạm khóa" in text
    assert "TOAN AAS chưa thể dịch phụ đề lúc này" not in text
    assert state["source_file_id"] == "tg-video"
    assert state["target_language"] == "English"
    assert state["step"] == "preview_guarded"
    assert provider_gate.public_copy_has_technical_terms(text) is False
    bot.clear_video_dubbing_pending(uid)


def test_uploaded_srt_language_selection_enters_translate_confirm(monkeypatch):
    uid = 901911
    bot.clear_video_dubbing_pending(uid)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "video_dubbing_configured_readiness", lambda *_args, **_kwargs: {"missing": ["asr", "translation"]})
    bot.set_video_dubbing_pending(
        uid,
        "language",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        process_type=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        source_file_id="tg-srt",
        source_file_name="captions.srt",
        source_mime_type="application/x-subrip",
        media_kind="subtitle_file",
        source_kind="subtitle_file",
        entry_surface="public_type",
    )
    query = FakeQuery(uid, "videodub|language|English")
    result = asyncio.run(bot.handle_video_dubbing_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert "🌐 <b>Xác nhận dịch phụ đề</b>" in result.text
    assert "File: đã nhận" in result.text
    assert "Ngôn ngữ đích: <b>English</b>" in result.text
    assert "Hình thức: dịch phụ đề, giữ thời gian hiển thị" in result.text
    assert "TOAN AAS chưa thể dịch phụ đề lúc này" not in result.text
    assert state["source_file_id"] == "tg-srt"
    assert state["step"] == "confirm"
    assert "✅ Xuất video phụ đề dịch" in _labels(result.reply_markup)
    bot.clear_video_dubbing_pending(uid)


def test_language_callback_missing_state_recovery(monkeypatch):
    uid = 901912
    bot.clear_video_dubbing_pending(uid)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    query = FakeQuery(uid, "videodub|language|English")
    result = asyncio.run(bot.handle_video_dubbing_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert "TOAN AAS chưa tìm thấy file cần xử lý" in result.text
    labels = _labels(result.reply_markup)
    assert "📎 Gửi lại file" in labels
    assert "⬅️ Quay lại" in labels
    assert "🏠 Menu chính" in labels


def test_no_provider_before_confirm_for_uploaded_language_route():
    source = inspect.getsource(bot.handle_video_dubbing_callback)
    preconfirm = source.split("    confirm_modes = {", 1)[0]
    assert "video_dubbing_transcribe_bytes" not in preconfirm
    assert "translate_subtitle_text" not in preconfirm
    assert "video_dubbing_tts_bytes" not in preconfirm
    assert "spend_fixed_credit_info" not in preconfirm


def test_public_copy_no_raw_ffmpeg_provider_for_live_wiring():
    texts = [
        bot.video_dubbing_uploaded_translate_locked_text("vi"),
        bot.video_dubbing_missing_upload_recovery_text("vi"),
        bot.video_dubbing_confirm_text(
            {
                "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
                "source_file_id": "tg-video",
                "target_language": "English",
            },
            "vi",
        ),
    ]
    assert all(provider_gate.public_copy_has_technical_terms(text) is False for text in texts)


def test_tool_test_subtitle_dub_live_wiring_admin_only(monkeypatch):
    monkeypatch.setattr(bot, "p0_18a_admin_allowed", lambda _uid: False)
    monkeypatch.setattr(bot, "save_tool_test_result", lambda *_args, **_kwargs: None)
    text = asyncio.run(_run_command(bot.cmd_tool_test_subtitle_dub_live_wiring, "/tool_test_subtitle_dub_live_wiring --fake", args=[]))
    assert "chỉ dành cho Admin" in text
    assert "Result: <code>PASS</code>" not in text


def test_tool_test_subtitle_dub_live_wiring_fake_no_charge(monkeypatch):
    _admin(monkeypatch)
    text = asyncio.run(_run_command(bot.cmd_tool_test_subtitle_dub_live_wiring, "/tool_test_subtitle_dub_live_wiring --fake", args=[]))
    assert "Uploaded video state: <code>YES</code>" in text
    assert "Uploaded language route: <code>YES</code>" in text
    assert "Storyboard SRT: <code>PASS</code>" in text
    assert "Mux failure partial: <code>PASS</code>" in text
    assert "Provider before confirm: <code>NO</code>" in text
    assert "Charge before confirm: <code>NO</code>" in text
    assert "Result: <code>PASS</code>" in text
