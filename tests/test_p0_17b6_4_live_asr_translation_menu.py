import asyncio
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class CaptureMessage:
    def __init__(self, file_id="b64-video", *, chat_id=6464):
        self.chat_id = chat_id
        self.message_id = 64
        self.outputs = []
        self.video = SimpleNamespace(
            file_id=file_id,
            file_unique_id=f"{file_id}-unique",
            file_name=f"{file_id}.mp4",
            mime_type="video/mp4",
            duration=12,
            file_size=2048,
            width=720,
            height=1280,
        )
        self.audio = None
        self.voice = None
        self.document = None

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.outputs.append({
            "kind": "text",
            "text": str(text),
            "parse_mode": parse_mode,
            "reply_markup": reply_markup,
            **kwargs,
        })
        return SimpleNamespace(text=text, reply_markup=reply_markup)

    async def reply_document(self, **kwargs):
        self.outputs.append({"kind": "document", **kwargs})

    async def reply_audio(self, **kwargs):
        self.outputs.append({"kind": "audio", **kwargs})


def _update(uid, message):
    return SimpleNamespace(effective_user=SimpleNamespace(id=uid), message=message)


def _seed_upload_monkeypatches(monkeypatch):
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    monkeypatch.setattr(bot, "remember_last_media", lambda _update: None)


def test_translation_menu_hides_auto_translate_stop_by_default(monkeypatch):
    monkeypatch.setattr(bot, "ensure_user_modes", lambda _uid: {})

    labels = _labels(bot.translation_language_hub_keyboard("vi"))
    callbacks = _callbacks(bot.translation_language_hub_keyboard("vi"))

    assert "🌐 Dịch tự động" in labels
    assert "⏹ Tắt dịch tự động" not in labels
    assert "menu|translation_stop_session" not in callbacks


def test_translation_menu_shows_auto_translate_stop_only_when_session_enabled(monkeypatch):
    monkeypatch.setattr(bot, "ensure_user_modes", lambda _uid: {"translate_mode_target": "en"})

    labels = _labels(bot.translation_language_hub_keyboard("vi", user_id=646401))
    callbacks = _callbacks(bot.translation_language_hub_keyboard("vi", user_id=646401))

    assert "⏹ Tắt dịch tự động" in labels
    assert "menu|translation_stop_session" in callbacks


def test_video_prepare_media_ignores_stale_default_source_subtitle(monkeypatch):
    uid = 646402
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_artifact(uid, "source_subtitle", "1\n00:00:00,000 --> 00:00:02,000\nSTALE CACHE")
    state = bot.set_video_dubbing_pending(
        uid,
        "creating_original_subtitle",
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        source_file_id="fresh-video",
        video_file_id="fresh-video",
        source_mime_type="video/mp4",
        media_kind="video",
        source_media_type="video",
        video_duration=12,
    )

    async def fake_download(_context, passed_state):
        assert passed_state["source_file_id"] == "fresh-video"
        return b"fresh-video-bytes", "video/mp4"

    async def fake_resolve(source_bytes, content_type, *_args, **_kwargs):
        assert source_bytes == b"fresh-video-bytes"
        assert content_type == "video/mp4"
        return {
            "subtitle": "1\n00:00:00,000 --> 00:00:02,000\nFresh ASR result",
            "script": "Fresh ASR result",
            "segments": [{"start": 0, "end": 2, "text": "Fresh ASR result"}],
            "asr_provider": "unit",
            "detected_language": "vi",
        }

    monkeypatch.setattr(bot, "video_dubbing_download_source", fake_download)
    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", fake_resolve)

    prepared = asyncio.run(bot.video_dubbing_prepare_subtitles(SimpleNamespace(), state, uid))

    assert "Fresh ASR result" in prepared["source_subtitle"]
    assert "STALE CACHE" not in prepared["source_subtitle"]
    assert bot.get_video_dubbing_pending(uid)["subtitle_ref"]


def test_subtitle_plus_dub_asr_failure_has_clean_retry_buttons(monkeypatch):
    uid = 646403
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "waiting_media",
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
    )
    _seed_upload_monkeypatches(monkeypatch)
    monkeypatch.setattr(bot, "video_dubbing_configured_readiness", lambda *_args, **_kwargs: {"missing": []})
    monkeypatch.setattr(bot, "video_dubbing_asr_missing_for_state", lambda *_args, **_kwargs: False)

    async def failing_prepare(*_args, **_kwargs):
        raise RuntimeError("empty_transcript")

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", failing_prepare)
    message = CaptureMessage("combo-fail", chat_id=uid)

    assert asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace())) is True

    last = message.outputs[-1]
    text = last["text"]
    callbacks = _callbacks(last["reply_markup"])
    assert "TOAN AAS chưa tạo được phụ đề từ file này" in text
    assert "Hệ thống chưa trừ Xu" in text
    assert callbacks == ["videodub|retry_media", "menu|main"]
    assert "videodub|send_subtitle_file" not in callbacks
    assert "videodub|enter_dialogue_text" not in callbacks
    forbidden = ["adapter", "provider", "env", "ffmpeg", "stack", "mode_disabled", "none", "null", "asr"]
    assert not any(word in text.lower() for word in forbidden)
    assert bot.get_video_dubbing_pending(uid)["step"] == "failed"


def test_translate_output_does_not_export_before_translated_subtitle_ready():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "subtitle_ref": "video_dubbing_artifact:source-only",
        "target_language": "English",
    }

    text = bot.video_dubbing_output_text(state, "vi")
    callbacks = _callbacks(bot.video_dubbing_output_keyboard("vi", state))

    assert "Phụ đề dịch chưa sẵn sàng" in text
    assert "videodub|output|srt" not in callbacks
    assert "videodub|final" not in callbacks


def test_subtitle_translate_upload_creates_original_subtitle_then_language(monkeypatch):
    uid = 646404
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "await_video",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        origin="translation",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        entry_surface="studio",
    )
    _seed_upload_monkeypatches(monkeypatch)

    prepare_calls = {"count": 0}

    async def fake_prepare(*_args, **_kwargs):
        prepare_calls["count"] += 1
        raise AssertionError("ASR must wait until final confirmation")

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fake_prepare)
    message = CaptureMessage("translate-video", chat_id=uid)

    assert asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace())) is True

    state = bot.get_video_dubbing_pending(uid)
    joined = "\n".join(item["text"] for item in message.outputs if item["kind"] == "text")
    assert state["step"] == "language"
    assert not state["subtitle_ref"]
    assert "TOAN AAS đang tạo phụ đề gốc" not in joined
    assert "Dịch phụ đề sang ngôn ngữ nào" in message.outputs[-1]["text"]
    assert "videodub|output|srt" not in _callbacks(message.outputs[-1]["reply_markup"])
    assert prepare_calls["count"] == 0


def test_subtitle_translate_language_runs_translation_before_export(monkeypatch):
    uid = 646405
    bot.clear_video_dubbing_pending(uid)
    source_ref = bot.set_video_dubbing_artifact(
        uid,
        "source_subtitle",
        "1\n00:00:00,000 --> 00:00:02,000\nXin chao",
    )
    bot.set_video_dubbing_pending(
        uid,
        "language",
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        subtitle_ref=source_ref,
        source_file_id="translate-video",
        video_file_id="translate-video",
    )

    prepare_calls = {"count": 0}

    async def fake_prepare(*_args, **_kwargs):
        prepare_calls["count"] += 1
        raise AssertionError("translation must wait until final confirmation")

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fake_prepare)
    tts_calls = {"count": 0}
    mux_calls = {"count": 0}

    async def forbidden_tts(*_args, **_kwargs):
        tts_calls["count"] += 1
        raise AssertionError("subtitle translate must not auto-start TTS")

    async def forbidden_mux(*_args, **_kwargs):
        mux_calls["count"] += 1
        raise AssertionError("subtitle translate must not auto-start mux")

    monkeypatch.setattr(bot, "synthesize_dub_segment_chunks", forbidden_tts)
    monkeypatch.setattr(bot, "video_dubbing_render_video", forbidden_mux)
    message = CaptureMessage("language-choice", chat_id=uid)

    state = asyncio.run(
        bot.video_dubbing_translate_current_subtitle_to_output(
            message,
            SimpleNamespace(),
            uid,
            bot.get_video_dubbing_pending(uid),
            "English",
            "vi",
        )
    )

    callbacks = _callbacks(message.outputs[-1]["reply_markup"])
    assert state["step"] == "confirm"
    assert not state.get("translated_subtitle_ref")
    assert "Dịch phụ đề video" in message.outputs[-1]["text"]
    assert "videodub|final" in callbacks
    assert "videodub|output|srt" not in callbacks
    assert "videodub|result_dub_translated" not in callbacks
    assert prepare_calls["count"] == 0
    assert tts_calls["count"] == 0
    assert mux_calls["count"] == 0


def test_auto_subtitle_media_outputs_srt_vtt_txt_after_real_create(monkeypatch):
    uid = 646406
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "await_video",
        mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        video_processing_mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
        origin="translation",
    )
    _seed_upload_monkeypatches(monkeypatch)

    prepare_calls = {"count": 0}

    async def fake_prepare(*_args, **_kwargs):
        prepare_calls["count"] += 1
        raise AssertionError("ASR must wait until final confirmation")

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fake_prepare)
    message = CaptureMessage("auto-subtitle", chat_id=uid)

    assert asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace())) is True

    state = bot.get_video_dubbing_pending(uid)
    labels = _labels(message.outputs[-1]["reply_markup"])
    assert state["step"] == "confirm"
    assert not state["subtitle_ref"]
    assert "✅ Xuất video phụ đề" in labels
    assert "📄 Tải SRT" not in labels
    assert "📄 Tải VTT" not in labels
    assert "🧾 Tải TXT" not in labels
    assert prepare_calls["count"] == 0


def test_public_asr_failure_copy_has_no_internal_terms():
    text = bot.video_dubbing_asr_failure_text("vi")
    forbidden = ["adapter", "provider", "env", "ffmpeg", "stack", "mode_disabled", "none", "null", "asr"]

    assert "TOAN AAS chưa tạo được phụ đề từ file này" in text
    assert not any(word in text.lower() for word in forbidden)
