import asyncio
import inspect
from types import SimpleNamespace

import bot


def _label_rows(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def _callback_rows(markup):
    return [[button.callback_data for button in row] for row in markup.inline_keyboard]


class FakeMessage:
    def __init__(self):
        self.chat_id = 919200
        self.message_id = 42
        self.sent = []

    async def reply_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.sent.append(item)
        return SimpleNamespace(**item)

    async def reply_document(self, **kwargs):
        item = {"document": True, **kwargs}
        self.sent.append(item)
        return SimpleNamespace(**item)

    async def reply_audio(self, **kwargs):
        item = {"audio": True, **kwargs}
        self.sent.append(item)
        return SimpleNamespace(**item)

    async def reply_video(self, **kwargs):
        item = {"video": True, **kwargs}
        self.sent.append(item)
        return SimpleNamespace(**item)


class FakeQuery:
    def __init__(self, uid=919201):
        self.from_user = SimpleNamespace(id=uid)
        self.message = FakeMessage()


def test_subtitle_menu_labels_unchanged():
    markup = bot.video_dubbing_menu_keyboard("vi", "translation")
    assert _label_rows(markup) == [
        ["📝 Tạo phụ đề tự động", "🌐 Dịch phụ đề / video"],
        ["🎙 Lồng tiếng / Voice video", "🎬 Phụ đề + Lồng tiếng"],
        ["📄 Dịch file phụ đề", "🧾 Transcript / Bóc lời"],
        ["⬅️ Trung tâm", "🏠 Menu chính"],
    ]
    assert _callback_rows(markup) == [
        ["videodub|type|subtitle_create", "videodub|type|subtitle_translate"],
        ["videodub|type|dub", "videodub|type|subtitle_plus_dub"],
        ["videodub|type|subtitle_file_translate", "videodub|type|transcript_extract"],
        ["menu|translate", "menu|main"],
    ]


def test_subtitle_keyboard_layout_unchanged():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE, "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_CREATE, "origin": "translation"}
    markup = bot.video_dubbing_source_keyboard("vi", state)
    assert _label_rows(markup) == [["📎 Gửi video/audio"], ["⬅️ Dịch video", "🏠 Menu chính"]]
    assert _callback_rows(markup) == [["videodub|source_upload"], ["videodub|back_type", "menu|main"]]


def test_translate_subtitle_keyboard_layout_unchanged():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "origin": "translation"}
    markup = bot.video_dubbing_source_keyboard("vi", state)
    assert _label_rows(markup) == [["📎 Gửi video/audio"], ["⬅️ Dịch video", "🏠 Menu chính"]]
    assert _callback_rows(markup) == [["videodub|source_upload"], ["videodub|back_type", "menu|main"]]


def test_dub_keyboard_layout_unchanged():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_DUB, "origin": "translation"}
    markup = bot.video_dubbing_source_keyboard("vi", state)
    assert _label_rows(markup) == [
        ["📎 Gửi video/audio để tự bóc lời", "📄 Gửi file phụ đề có sẵn"],
        ["🕘 Dùng phụ đề vừa tạo"],
        ["⬅️ Dịch video", "🏠 Menu chính"],
    ]
    assert _callback_rows(markup) == [
        ["videodub|source_upload", "videodub|source_upload"],
        ["videodub|source_recent_subtitle"],
        ["videodub|back_type", "menu|main"],
    ]


def test_no_new_public_buttons_added_for_p0_19b2():
    labels = [label for row in _label_rows(bot.video_dubbing_menu_keyboard("vi", "translation")) for label in row]
    assert labels == [
        "📝 Tạo phụ đề tự động",
        "🌐 Dịch phụ đề / video",
        "🎙 Lồng tiếng / Voice video",
        "🎬 Phụ đề + Lồng tiếng",
        "📄 Dịch file phụ đề",
        "🧾 Transcript / Bóc lời",
        "⬅️ Trung tâm",
        "🏠 Menu chính",
    ]


def test_product_handler_calls_blackbox_not_inline_ffmpeg():
    handler_source = inspect.getsource(bot.handle_video_dubbing_callback)
    pipeline_source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "execute_video_dubbing_pipeline" in handler_source
    assert "subtitle_dub_product_pipeline.process_subtitle_dub_job" in pipeline_source
    assert "subprocess.run" not in handler_source
    assert "ffmpeg" not in handler_source.lower()


def test_product_handler_does_not_call_gemini_directly():
    source = inspect.getsource(bot.handle_video_dubbing_callback)
    assert "gemini" not in source.lower()


def test_product_handler_no_provider_before_confirm():
    source = inspect.getsource(bot.handle_video_dubbing_callback)
    preconfirm = source.split("    confirm_modes = {", 1)[0]
    assert "video_dubbing_transcribe_bytes" not in preconfirm
    assert "translate_subtitle_text" not in preconfirm
    assert "video_dubbing_tts_bytes" not in preconfirm
    assert "spend_fixed_credit_info" not in preconfirm


def test_bot_py_no_large_pipeline_added():
    source = inspect.getsource(bot)
    assert "def process_subtitle_dub_job" not in source
    assert "subtitle_dub_product_pipeline" in source


def test_product_confirm_calls_blackbox_service(monkeypatch):
    uid = 919260
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    srt = "1\n00:00:00,000 --> 00:00:02,000\nXin chào\n"
    calls = {}

    async def fake_blackbox(**kwargs):
        calls["mode"] = kwargs["mode"]
        calls["state"] = dict(kwargs["state"])
        return {
            "ok": True,
            "status": "OK",
            "result_type": "subtitle",
            "state": dict(kwargs["state"]),
            "prepared": {},
            "source_bytes": b"video-bytes",
            "content_type": "video/mp4",
            "asr_provider": "fake_asr",
            "translation_provider": "",
            "tts_provider": "",
            "output_subtitle": srt,
            "output_text": "Xin chào",
            "output_segments": [{"start": 0, "end": 2, "text": "Xin chào"}],
            "srt_text": srt,
            "srt_bytes": srt.encode("utf-8"),
            "subtitle_items": [{"output_type": "srt", "bytes": srt.encode("utf-8"), "filename": "result.srt", "suffix": ".srt", "caption": ""}],
            "tts_chunks": [],
            "audio_bytes": b"",
            "video_output": b"",
            "normalization_detail": "not_requested",
            "selected_tts_voice_id": "",
        }

    async def fake_send(*_args, **_kwargs):
        return {"documents": 1, "audio": 0, "video": 0}

    monkeypatch.setattr(bot.subtitle_dub_product_pipeline, "process_subtitle_dub_job", fake_blackbox)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "video_dubbing_engine_access_decision", lambda *_args, **_kwargs: {"allowed": True})
    monkeypatch.setattr(bot, "apply_member_service_discount", lambda _uid, amount, _event: {"final_cost": amount})
    monkeypatch.setattr(bot, "get_user", lambda _uid: (99999, 0, 0))
    monkeypatch.setattr(bot, "send_public_subtitle_dub_final_outputs", fake_send)
    monkeypatch.setattr(bot, "write_media_asset_bytes", lambda kind, asset_id, data, suffix: f"/tmp/{kind}_{asset_id}{suffix}")
    monkeypatch.setattr(bot, "create_subtitle_asset_record", lambda **kwargs: {"asset_id": kwargs.get("asset_id")})
    monkeypatch.setattr(bot, "create_translation_asset_record", lambda **kwargs: {"asset_id": kwargs.get("asset_id")})
    monkeypatch.setattr(bot, "create_dub_asset_record", lambda **kwargs: {"asset_id": kwargs.get("asset_id")})
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: {"internal_job_id": "job-test", **payload})

    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
        "process_type": bot.VIDEO_SUBTITLE_MODE_CREATE,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
        "source_file_id": "tg-video-file",
        "video_file_id": "tg-video-file",
        "source_file_name": "sample.mp4",
        "source_mime_type": "video/mp4",
        "media_kind": "video",
    }
    result = asyncio.run(bot.execute_video_dubbing_pipeline(FakeQuery(uid), SimpleNamespace(), state, "vi", admin_interactive_confirm=True))
    assert result["ok"] is True
    assert calls["mode"] == bot.VIDEO_SUBTITLE_MODE_CREATE
    assert result["sent_documents"] == 1
    assert result["charged"] == 0
