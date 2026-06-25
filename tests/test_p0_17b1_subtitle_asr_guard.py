import asyncio
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class CaptureMessage:
    def __init__(self, chat_id=171810, video=None, audio=None, voice=None, document=None, text=""):
        self.chat_id = chat_id
        self.message_id = 18
        self.video = video
        self.audio = audio
        self.voice = voice
        self.document = document
        self.text = text
        self.outputs = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.outputs.append({"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs})
        return SimpleNamespace(text=text, reply_markup=reply_markup)


class CaptureQuery:
    def __init__(self, data, user_id=171811):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage(chat_id=user_id)
        self.outputs = self.message.outputs

    async def answer(self, *args, **kwargs):
        self.outputs.append({"answer": args, "answer_kwargs": kwargs})
        return None

    async def edit_message_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.outputs.append({"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs})
        return SimpleNamespace(text=text, reply_markup=reply_markup)


def _missing_asr(monkeypatch):
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TRANSLATE_SUBTITLE_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_DUB_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PLUS_DUB_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TRANSLATE_SUBTITLE_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_DUB_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PLUS_DUB_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "ASR_PROVIDER", "auto")
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "")
    monkeypatch.setattr(bot, "key4u_asr_configured", lambda: False)
    monkeypatch.setattr(bot, "key4u_asr_public_ready", lambda: False)
    monkeypatch.setattr(bot, "shopaikey_stt_public_ready", lambda: False)
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "")
    monkeypatch.setattr(bot, "SHOPAIKEY_AUDIO_TRANSCRIPTION_ENDPOINT", "")


def _ready_deepgram(monkeypatch):
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TRANSLATE_SUBTITLE_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_DUB_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PLUS_DUB_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TRANSLATE_SUBTITLE_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_DUB_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PLUS_DUB_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "ASR_PROVIDER", "auto")
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "configured")
    monkeypatch.setattr(bot, "AgentDeepgram", object)
    monkeypatch.setattr(bot, "key4u_asr_configured", lambda: False)
    monkeypatch.setattr(bot, "key4u_asr_public_ready", lambda: False)
    monkeypatch.setattr(bot, "shopaikey_stt_public_ready", lambda: False)
    monkeypatch.setattr(bot, "asr_smoke_status", lambda: "PASS")


def test_asr_readiness_detects_deepgram_if_configured(monkeypatch):
    _ready_deepgram(monkeypatch)
    monkeypatch.setattr(bot, "video_dubbing_audio_extract_ready", lambda: True)

    readiness = bot.get_asr_adapter_readiness(public=True)

    assert readiness["ready"] is True
    assert readiness["adapter"] == "deepgram"
    assert readiness["supports_audio"] is True
    assert readiness["supports_video"] is True


def test_asr_readiness_detects_existing_transcribe_adapter(monkeypatch):
    _missing_asr(monkeypatch)
    monkeypatch.setattr(bot, "key4u_asr_configured", lambda: True)
    monkeypatch.setattr(bot, "key4u_asr_public_ready", lambda: True)
    monkeypatch.setattr(bot, "asr_smoke_status", lambda: "PASS")

    readiness = bot.get_asr_adapter_readiness(public=True)

    assert readiness["ready"] is True
    assert readiness["adapter"] == "key4u"


def test_asr_readiness_missing_when_no_adapter(monkeypatch):
    _missing_asr(monkeypatch)

    readiness = bot.get_asr_adapter_readiness(public=True)

    assert readiness["ready"] is False
    assert readiness["adapter"] == "none"
    assert readiness["reason"] == "asr_adapter_missing"


def test_asr_readiness_no_provider_call(monkeypatch):
    _ready_deepgram(monkeypatch)

    async def forbidden_provider(*_args, **_kwargs):
        raise AssertionError("readiness must not call provider")

    monkeypatch.setattr(bot, "deepgram_asr_adapter", forbidden_provider)
    monkeypatch.setattr(bot, "video_dubbing_transcribe_bytes", forbidden_provider)

    readiness = bot.get_asr_adapter_readiness(public=True)

    assert readiness["ready"] is True


def test_subtitle_video_requires_asr(monkeypatch):
    _missing_asr(monkeypatch)
    state = {"source_mime_type": "video/mp4", "source_file_name": "input.mp4", "media_kind": "video"}

    assert bot.video_dubbing_state_requires_asr(bot.VIDEO_SUBTITLE_MODE_CREATE, state) is True
    assert bot.video_dubbing_capability(bot.VIDEO_SUBTITLE_MODE_CREATE, state, public=False)["reason"] == "missing_asr"


def test_subtitle_audio_requires_asr(monkeypatch):
    _missing_asr(monkeypatch)
    state = {"source_mime_type": "audio/mpeg", "source_file_name": "input.mp3", "media_kind": "audio"}

    assert bot.video_dubbing_state_requires_asr(bot.VIDEO_SUBTITLE_MODE_CREATE, state) is True
    assert bot.video_dubbing_capability(bot.VIDEO_SUBTITLE_MODE_CREATE, state, public=False)["reason"] == "missing_asr"


def test_subtitle_asr_missing_clean_public_guard():
    text = bot.video_dubbing_asr_missing_guard_text("vi")

    assert "TOAN AAS chưa thể bóc lời từ file này" in text
    assert "chưa xử lý file và chưa trừ Xu" in text
    forbidden = ["asr_adapter_missing", "component kỹ thuật", "Admin test", "provider", "API", "route"]
    assert not any(item in text for item in forbidden)


def test_subtitle_asr_missing_no_confirm_buttons():
    markup = bot.video_dubbing_asr_missing_guard_keyboard("vi")
    labels = _labels(markup)
    callbacks = _callbacks(markup)

    assert not any("Xem thử" in label for label in labels)
    assert not any("Xác nhận tạo đầy đủ" in label for label in labels)
    assert not any(callback.startswith("videodub|confirm") for callback in callbacks)
    assert callbacks == ["videodub|back_type", "menu|main"]


def test_subtitle_asr_missing_no_provider_call(monkeypatch):
    _missing_asr(monkeypatch)

    async def forbidden_provider(*_args, **_kwargs):
        raise AssertionError("provider must not run when ASR is missing")

    monkeypatch.setattr(bot, "video_dubbing_transcribe_bytes", forbidden_provider)
    state = {"source_mime_type": "video/mp4", "source_file_name": "input.mp4", "media_kind": "video"}

    assert bot.video_dubbing_asr_missing_for_state(bot.VIDEO_SUBTITLE_MODE_CREATE, state, public=False) is True


def test_subtitle_asr_missing_no_admin_diagnostic_public(monkeypatch):
    _missing_asr(monkeypatch)
    state = {"source_mime_type": "video/mp4", "source_file_name": "input.mp4", "media_kind": "video"}
    text = bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_CREATE, state, "vi", admin=False)

    assert "Admin blocker" not in text
    assert "asr_adapter_missing" not in text


def test_subtitle_file_translation_does_not_require_asr(monkeypatch):
    _missing_asr(monkeypatch)
    state = {"source_kind": "subtitle_file", "source_file_name": "captions.srt", "source_mime_type": "application/x-subrip"}

    assert bot.video_dubbing_state_requires_asr(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, state) is False
    assert "asr" not in bot.video_dubbing_capability(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, state, public=False)["missing"]


def test_text_translation_does_not_require_asr(monkeypatch):
    _missing_asr(monkeypatch)
    state = {"source_kind": "text", "source_script": "xin chao", "target_language": "English"}

    assert bot.video_dubbing_state_requires_asr(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, state) is False
    assert "asr" not in bot.video_dubbing_capability(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, state, public=False)["missing"]


def test_dub_video_requires_asr_or_transcript(monkeypatch):
    _missing_asr(monkeypatch)
    video_state = {"source_mime_type": "video/mp4", "source_file_name": "input.mp4", "media_kind": "video", "target_language": "English"}
    transcript_state = {**video_state, "subtitle_ref": "video_dubbing_artifact:test:source"}

    assert bot.video_dubbing_state_requires_asr(bot.VIDEO_SUBTITLE_MODE_DUB, video_state) is True
    assert bot.video_dubbing_state_requires_asr(bot.VIDEO_SUBTITLE_MODE_DUB, transcript_state) is False


def test_dub_with_existing_srt_does_not_require_asr(monkeypatch):
    _missing_asr(monkeypatch)
    state = {"source_kind": "subtitle_file", "source_file_name": "captions.srt", "target_language": "English"}

    assert "asr" not in bot.video_dubbing_capability(bot.VIDEO_SUBTITLE_MODE_DUB, state, public=False)["missing"]


def test_dub_asr_missing_clean_guard(monkeypatch):
    _missing_asr(monkeypatch)
    state = {"source_mime_type": "audio/mpeg", "source_file_name": "input.mp3", "media_kind": "audio"}
    text = bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_DUB, state, "vi", admin=False)

    assert "TOAN AAS chưa thể bóc lời từ file này" in text
    assert "asr_adapter_missing" not in text


def test_public_flow_admin_user_still_customer_clean(monkeypatch):
    _missing_asr(monkeypatch)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    uid = 171812
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "confirm",
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        video_file_id="video-file",
        source_file_id="video-file",
        source_mime_type="video/mp4",
        source_file_name="input.mp4",
        media_kind="video",
    )
    query = CaptureQuery("videodub|final", uid)

    asyncio.run(bot.handle_video_dubbing_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    joined = "\n".join(item.get("text", "") for item in query.outputs)

    assert "TOAN AAS chưa thể bóc lời từ file này" in joined
    assert "Admin test" not in joined
    assert "component kỹ thuật" not in joined


def test_subtitle_engine_status_shows_asr_readiness():
    joined = "\n".join(bot.subtitle_engine_status_lines())

    assert "ASR configured" in joined
    assert "ASR smoke" in joined
    assert "Public ASR ready" in joined
    assert "Detected ASR adapter" in joined
    assert "Subtitle from file readiness" in joined


def test_dub_engine_status_shows_asr_dependency():
    joined = "\n".join(bot.dub_engine_status_lines())

    assert "ASR configured" in joined
    assert "ASR smoke" in joined
    assert "Public ASR ready" in joined
    assert "ASR route" in joined


def test_engine_status_no_secret():
    joined = "\n".join(bot.subtitle_engine_status_lines() + bot.translation_engine_status_lines() + bot.dub_engine_status_lines())
    forbidden = ["sk-live", "Bearer ", "Authorization:", "API_KEY=", "SECRET="]

    assert not any(marker in joined for marker in forbidden)
