import asyncio
import inspect
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _ui_text(*surfaces):
    parts = []
    for surface in surfaces:
        if isinstance(surface, str):
            parts.append(surface)
        else:
            parts.extend(_labels(surface))
    return "\n".join(parts)


class Media:
    def __init__(self, file_id="video-file", file_name="clip.mp4", mime_type="video/mp4", duration=30):
        self.file_id = file_id
        self.file_unique_id = file_id + "-unique"
        self.file_name = file_name
        self.mime_type = mime_type
        self.duration = duration
        self.file_size = 1024
        self.width = 1280
        self.height = 720


class CaptureMessage:
    def __init__(self, *, video=None, audio=None, document=None):
        self.chat_id = 919400
        self.message_id = 9
        self.video = video
        self.audio = audio
        self.document = document
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(**item)

    async def reply_audio(self, **kwargs):
        item = {"audio": True, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(**item)

    async def reply_document(self, **kwargs):
        item = {"document": True, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(**item)

    async def reply_video(self, **kwargs):
        item = {"video": True, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(**item)


def _update(uid, message):
    return SimpleNamespace(effective_user=SimpleNamespace(id=uid), message=message)


def _seed(uid, mode, step="await_video", **fields):
    bot.clear_video_dubbing_pending(uid)
    return bot.set_video_dubbing_pending(
        uid,
        step,
        mode=mode,
        process_type=mode,
        video_processing_mode=mode,
        requested_mode=mode,
        origin="translation",
        **fields,
    )


def _patch_upload_basics(monkeypatch):
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    monkeypatch.setattr(bot, "remember_last_media", lambda _update: None)


def test_video_translate_main_has_four_video_buttons():
    labels = _labels(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert labels == [
        "🎬 Tạo phụ đề tự động",
        "🌐 Dịch phụ đề video",
        "🎙 Lồng tiếng video",
        "🎞 Phụ đề + Lồng tiếng",
        "📄 Dịch file",
        "🎧 Dịch audio",
        "⬅️ Trung tâm dịch",
        "🏠 Menu chính",
    ]


def test_video_translate_main_has_no_file_audio_prompt():
    ui = _ui_text(bot.translation_menu_text("vi"), bot.translation_menu_keyboard("vi"))
    for forbidden in ["SRT/VTT/TXT", "Dịch file", "Bóc lời thoại", "audio", "âm thanh"]:
        assert forbidden not in ui


def test_each_button_routes_to_own_flow():
    callbacks = _callbacks(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert callbacks[:4] == [
        "videodub|type|subtitle_create",
        "videodub|type|subtitle_translate",
        "videodub|type|dub",
        "videodub|type|subtitle_plus_dub",
    ]


def test_auto_subtitle_accepts_video_only(monkeypatch):
    uid = 919401
    _patch_upload_basics(monkeypatch)
    _seed(uid, bot.VIDEO_SUBTITLE_MODE_CREATE)
    message = CaptureMessage(video=Media())
    assert asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace())) is True
    assert bot.get_video_dubbing_pending(uid)["step"] == "confirm"
    audio_message = CaptureMessage(audio=Media(file_name="audio.mp3", mime_type="audio/mpeg"))
    _seed(uid, bot.VIDEO_SUBTITLE_MODE_CREATE)
    assert asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, audio_message), SimpleNamespace())) is True
    assert "chỉ xử lý video" in audio_message.outputs[-1]["text"]


def test_auto_subtitle_description_says_free_original_subtitle():
    text = bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}, "vi")
    assert "tạo phụ đề gốc" in text
    assert "miễn phí" in text.lower()


def test_auto_subtitle_confirm_before_asr(monkeypatch):
    uid = 919402
    _patch_upload_basics(monkeypatch)
    _seed(uid, bot.VIDEO_SUBTITLE_MODE_CREATE)

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("ASR must wait for final confirm")

    monkeypatch.setattr(bot, "video_dubbing_create_original_subtitle_then_output", forbidden)
    message = CaptureMessage(video=Media())
    asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace()))
    assert bot.get_video_dubbing_pending(uid)["step"] == "confirm"
    assert "Xác nhận tạo phụ đề gốc" in message.outputs[-1]["text"]


def test_auto_subtitle_outputs_original_srt_or_video():
    labels = _labels(bot.video_dubbing_output_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE, "subtitle_ref": "ref"}))
    assert "📹 Tải video phụ đề" in labels
    assert "📄 Tải SRT" in labels


def test_translate_subtitle_accepts_video_with_existing_subtitle(monkeypatch):
    uid = 919403
    _patch_upload_basics(monkeypatch)
    _seed(uid, bot.VIDEO_SUBTITLE_MODE_TRANSLATE, source_has_subtitle="1")
    message = CaptureMessage(video=Media())
    asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "language"
    assert state["flow_type"] == bot.VIDEO_DUBBING_FLOW_HAS_SUBTITLE


def test_translate_subtitle_rejects_video_without_subtitle_with_switch_buttons(monkeypatch):
    uid = 919404
    _patch_upload_basics(monkeypatch)
    _seed(uid, bot.VIDEO_SUBTITLE_MODE_TRANSLATE, source_has_subtitle="0")
    message = CaptureMessage(video=Media())
    asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace()))
    assert "chưa tìm thấy phụ đề có sẵn" in message.outputs[-1]["text"]
    assert "🎬 Tạo phụ đề tự động" in _labels(message.outputs[-1]["reply_markup"])


def test_translate_subtitle_never_runs_create_original_subtitle(monkeypatch):
    uid = 919405
    _patch_upload_basics(monkeypatch)
    _seed(uid, bot.VIDEO_SUBTITLE_MODE_TRANSLATE)

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("translate subtitle must not create original subtitles automatically")

    monkeypatch.setattr(bot, "video_dubbing_create_original_subtitle_for_next_step", forbidden)
    message = CaptureMessage(video=Media())
    asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace()))
    assert bot.get_video_dubbing_pending(uid)["step"] == "language"


def test_translate_subtitle_price_0_1_per_char():
    price = bot.calculate_video_only_char_price(1000, bot.VIDEO_ONLY_SUBTITLE_TRANSLATE_RATE_XU)
    assert price["total_xu"] == 100


def test_translate_subtitle_discount_over_1000():
    price = bot.calculate_video_only_char_price(2000, bot.VIDEO_ONLY_SUBTITLE_TRANSLATE_RATE_XU)
    assert price["discount_percent"] == 10
    assert price["total_xu"] == 180


def test_translate_subtitle_discount_over_10000():
    price = bot.calculate_video_only_char_price(12000, bot.VIDEO_ONLY_SUBTITLE_TRANSLATE_RATE_XU)
    assert price["discount_percent"] == 20
    assert price["total_xu"] == 960


def test_translate_subtitle_outputs_video_with_translated_subtitle():
    message = CaptureMessage()
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            subtitle_items=[{"output_type": "srt", "bytes": b"srt", "filename": "translated.srt"}],
            video_bytes=b"video-bytes",
            lang="vi",
        )
    )
    assert sent == {"documents": 0, "audio": 0, "video": 1}


def test_dub_menu_is_closed_video_flow():
    labels = _labels(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}))
    assert labels[0] == "📤 Gửi video cần lồng tiếng"
    assert "🎞 Video đã có phụ đề" not in labels
    assert "🎧 Video chỉ có tiếng" not in labels


def test_dub_existing_subtitle_path_never_runs_auto_subtitle(monkeypatch):
    uid = 919406
    _patch_upload_basics(monkeypatch)
    _seed(uid, bot.VIDEO_SUBTITLE_MODE_DUB, flow_type=bot.VIDEO_DUBBING_FLOW_HAS_SUBTITLE, source_has_subtitle="1")

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("existing subtitle path must not auto-create original subtitles")

    monkeypatch.setattr(bot, "video_dubbing_create_original_subtitle_for_next_step", forbidden)
    message = CaptureMessage(video=Media())
    asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace()))
    assert bot.get_video_dubbing_pending(uid)["step"] == "language"


def test_dub_speech_only_path_transcribes_internally_after_confirm(monkeypatch):
    uid = 919407
    _patch_upload_basics(monkeypatch)
    _seed(uid, bot.VIDEO_SUBTITLE_MODE_DUB, flow_type=bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE)

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("speech-only dub must wait until final confirm")

    monkeypatch.setattr(bot, "video_dubbing_create_dub_source_subtitle_then_next", forbidden)
    message = CaptureMessage(video=Media())
    asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace()))
    assert bot.get_video_dubbing_pending(uid)["step"] == "language"


def test_dub_requires_voice_selection():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "source_file_id": "video", "target_language": "Tiếng Việt"}
    routed, text, markup = bot.video_dubbing_next_screen_after_source(919408, state, "vi")
    assert routed["step"] == "voice"
    assert "Chọn giọng lồng tiếng" in text
    assert "👩 Giọng nữ mặc định" in _labels(markup)


def test_dub_default_female_uses_female_voice(monkeypatch):
    monkeypatch.setattr(bot, "get_tts_voice_id", lambda key: {"default_female": "female-id", "default_male": "male-id"}[key])
    payload = bot.video_dubbing_voice_payload("default_female", None, "vi")
    assert payload["voice_kind"] == "default_female"
    assert payload["voice_id"] == "female-id"


def test_dub_default_male_uses_male_voice(monkeypatch):
    monkeypatch.setattr(bot, "get_tts_voice_id", lambda key: {"default_female": "female-id", "default_male": "male-id"}[key])
    payload = bot.video_dubbing_voice_payload("default_male", None, "vi")
    assert payload["voice_kind"] == "default_male"
    assert payload["voice_id"] == "male-id"


def test_dub_custom_voice_uses_provider_voice_id():
    payload = bot.video_dubbing_voice_payload("", {"id": 5, "display_name": "Voice riêng", "provider_voice_id": "provider-voice-5"}, "vi")
    assert payload["voice_kind"] == "saved_voice"
    assert payload["voice_id"] == "provider-voice-5"
    assert payload["voice_profile_id"] == 5


def test_dub_does_not_use_sample_audio():
    source = inspect.getsource(bot.send_public_subtitle_dub_final_outputs)
    assert "sample" not in source.lower()


def test_dub_outputs_final_mp4_when_source_video_exists():
    message = CaptureMessage()
    sent = asyncio.run(bot.send_public_subtitle_dub_final_outputs(message, mode=bot.VIDEO_SUBTITLE_MODE_DUB, audio_bytes=b"audio", video_bytes=b"video", lang="vi"))
    assert sent["video"] == 1
    assert not any(item.get("audio") for item in message.outputs)


def test_dub_partial_result_not_marked_full_success():
    message = CaptureMessage()
    sent = asyncio.run(bot.send_public_subtitle_dub_final_outputs(message, mode=bot.VIDEO_SUBTITLE_MODE_DUB, audio_bytes=b"audio", video_bytes=b"", lang="vi"))
    assert sent["audio"] == 1
    assert "chưa ghép được thành video hoàn chỉnh" in message.outputs[-1]["caption"]
    assert not message.outputs[-1]["caption"].startswith("✅")


def test_combo_menu_has_two_paths():
    labels = _labels(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}))
    assert "🎞 Video đã có phụ đề" in labels
    assert "🎧 Video chưa có phụ đề" in labels


def test_combo_existing_subtitle_translates_then_dubs(monkeypatch):
    uid = 919409
    _patch_upload_basics(monkeypatch)
    _seed(uid, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB, flow_type=bot.VIDEO_DUBBING_FLOW_HAS_SUBTITLE, source_has_subtitle="1")
    message = CaptureMessage(video=Media())
    asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "language"
    assert state["active_flow"] == bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB


def test_combo_speech_only_transcribes_translates_dubs(monkeypatch):
    uid = 919410
    _patch_upload_basics(monkeypatch)
    _seed(uid, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB, flow_type=bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE)
    message = CaptureMessage(video=Media())
    asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace()))
    state = bot.get_video_dubbing_pending(uid)
    assert state["step"] == "language"
    assert state["flow_type"] == bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE


def test_combo_price_summary_adds_subtitle_and_dub():
    text = bot.video_dubbing_confirm_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "target_language": "English", "voice_style": "Nữ mặc định", "billing_chars": 2000},
        "vi",
    )
    assert "Dịch phụ đề: <b>180 Xu</b>" in text
    assert "Lồng tiếng: <b>90 Xu</b>" in text
    assert "Tổng cộng: <b>270 Xu</b>" in text


def test_combo_outputs_final_mp4_srt_mp3():
    message = CaptureMessage()
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            subtitle_items=[{"output_type": "srt", "bytes": b"srt", "filename": "translated.srt"}],
            audio_bytes=b"audio",
            video_bytes=b"video",
            lang="vi",
        )
    )
    assert sent["video"] == 1


def test_combo_mux_retry_uses_existing_real_artifacts():
    labels = _labels(bot.subtitle_plus_dub_completed_keyboard("vi", {"final_video_available": "0"}))
    assert "🔁 Thử ghép lại video" in labels
    assert "🎧 Tải audio" in labels
    assert "📄 Tải phụ đề" in labels


def test_subtitle_price_counts_all_chars():
    assert bot.calculate_video_only_char_price(len("a b c"), bot.VIDEO_ONLY_SUBTITLE_TRANSLATE_RATE_XU)["chars"] == 5


def test_dub_default_price_0_05_per_char():
    assert bot.calculate_video_only_char_price(1000, bot.VIDEO_ONLY_DUB_DEFAULT_RATE_XU)["total_xu"] == 50


def test_dub_custom_price_0_1_per_char():
    assert bot.calculate_video_only_char_price(1000, bot.VIDEO_ONLY_DUB_CUSTOM_RATE_XU)["total_xu"] == 100


def test_discount_threshold_1000_10_percent():
    assert bot.video_only_price_discount_percent(1001) == 10


def test_discount_threshold_10000_20_percent():
    assert bot.video_only_price_discount_percent(10001) == 20


def test_min_charge_1_xu():
    assert bot.calculate_video_only_char_price(1, bot.VIDEO_ONLY_DUB_DEFAULT_RATE_XU)["total_xu"] == 1


def test_no_xu_before_confirm(monkeypatch):
    uid = 919411
    _patch_upload_basics(monkeypatch)
    _seed(uid, bot.VIDEO_SUBTITLE_MODE_CREATE)
    called = {"charge": 0}
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *_args, **_kwargs: called.__setitem__("charge", called["charge"] + 1))
    message = CaptureMessage(video=Media())
    asyncio.run(bot.handle_video_dubbing_pending_upload(_update(uid, message), SimpleNamespace()))
    assert called["charge"] == 0


def test_no_charge_on_fail():
    text = bot.video_dubbing_flow_failure_text(bot.VIDEO_SUBTITLE_MODE_DUB, "vi")
    assert "chưa trừ Xu" in text


def test_back_from_auto_subtitle_returns_auto_subtitle_menu():
    assert bot.video_dubbing_back_route({"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}, "back_confirm") == "output"


def test_back_from_translate_returns_translate_menu():
    assert bot.video_dubbing_back_route({"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "target_language": "English"}, "back_confirm") == "language"


def test_back_from_dub_returns_dub_menu():
    assert bot.video_dubbing_back_route({"mode": bot.VIDEO_SUBTITLE_MODE_DUB}, "back_confirm") == "voice"


def test_back_from_combo_returns_combo_menu():
    assert bot.video_dubbing_back_route({"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}, "back_voice") == "language"


def test_video_routes_do_not_jump_to_file_audio_flows():
    ui = _ui_text(
        bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE}),
        bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}),
        bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}),
    )
    for forbidden in ["SRT/VTT/TXT", "Dịch file", "Bóc lời thoại", "video/audio", "source_recent_subtitle"]:
        assert forbidden not in ui


def test_no_provider_api_ffmpeg_asr_tts_mux_words_in_product_ui():
    ui = _ui_text(
        bot.video_dubbing_menu_text("vi", "translation"),
        bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE}, "vi"),
        bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_DUB}, "vi"),
        bot.video_dubbing_confirm_text({"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "target_language": "English", "voice_style": "Nữ mặc định", "billing_chars": 1200}, "vi"),
        bot.video_dubbing_pricing_text("vi"),
    )
    for forbidden in ["provider", "API", "FFmpeg", "ASR", "TTS", "mux", "traceback", "debug", "fake", "sample", "RuntimeError", "redacted", "route", "payload"]:
        assert forbidden not in ui


def test_no_generic_error_for_expected_guard():
    text = bot.video_dubbing_missing_existing_subtitle_text("vi")
    assert "lỗi" not in text.lower()
    assert "chưa tìm thấy phụ đề" in text


def test_no_fake_success_copy():
    text = bot.subtitle_plus_dub_completed_text({}, {"has_video": False, "has_audio": True}, "vi")
    assert "✅" not in text
    assert "chưa ghép được thành video hoàn chỉnh" in text
