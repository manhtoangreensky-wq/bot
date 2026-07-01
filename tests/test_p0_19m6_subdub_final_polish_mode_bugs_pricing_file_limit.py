import asyncio
from types import SimpleNamespace

import bot


MP4_BYTES = b"\x00\x00\x00\x18ftypmp42-p019m6" + b"x" * 4096
VALID_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n"


class CaptureMessage:
    def __init__(self, *, message_id=True):
        self.calls = []
        self._message_id = message_id

    def _message(self, kind):
        if not self._message_id:
            return SimpleNamespace()
        media = SimpleNamespace(file_id=f"{kind}-file")
        return SimpleNamespace(message_id=len(self.calls), **{kind: media})

    async def reply_video(self, **kwargs):
        self.calls.append(("video", kwargs))
        return self._message("video")

    async def reply_document(self, **kwargs):
        self.calls.append(("document", kwargs))
        return self._message("document")

    async def reply_audio(self, **kwargs):
        self.calls.append(("audio", kwargs))
        return self._message("audio")

    async def reply_text(self, *args, **kwargs):
        self.calls.append(("text", {"args": args, **kwargs}))
        return SimpleNamespace(message_id=len(self.calls))


async def _valid_video(*_args, **_kwargs):
    return {"ok": True, "duration": 12.0, "has_video": True, "has_audio": True, "detail": "ok"}


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def _progress_labels(mode):
    return [item["label"] for item in bot.subdub_progress_steps_for_product(mode)]


def _set_delivery_limits(monkeypatch, *, preview=45, document=50, output=50):
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_SEND_VIDEO_MAX_MB", preview)
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_DOCUMENT_MAX_MB", document)
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_OUTPUT_MAX_MB", output)
    monkeypatch.setattr(bot, "SUBDUB_ENABLE_DOCUMENT_FALLBACK", True)
    monkeypatch.setattr(bot, "subdub_validate_video_output", _valid_video)


def test_subtitle_translate_status_has_no_dub_voice_step():
    labels = _progress_labels(bot.VIDEO_SUBTITLE_MODE_TRANSLATE)
    assert labels == [
        "Nhận video",
        "Đọc phụ đề/lời thoại gốc",
        "Dịch phụ đề",
        "Gắn phụ đề vào video",
        "Kiểm tra file",
        "Gửi kết quả",
    ]
    assert "Tách âm thanh" not in labels
    assert "Tạo giọng lồng tiếng" not in labels
    assert "Ghép giọng vào video" not in labels


def test_subtitle_translate_success_has_no_audio_button():
    keyboard = bot.video_dubbing_receipt_keyboard(
        "vi",
        state={
            "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "final_video_available": "1",
            "final_subtitle_available": "1",
        },
    )
    labels = _labels(keyboard)
    callbacks = _callbacks(keyboard)
    assert "📹 Tải video phụ đề dịch" in labels
    assert "📄 Tải SRT dịch" in labels
    assert all("audio" not in str(callback).lower() for callback in callbacks)
    assert all("lồng tiếng" not in label.lower() for label in labels)


def test_subtitle_translate_delivered_no_late_fail():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE},
        {"video_delivered": True, "terminal_state": "delivered", "charged": 3},
    )
    assert "✅ Đã tạo video phụ đề dịch." in text
    assert "Có lỗi khi xử lý lệnh" not in text
    assert "chưa" not in text.lower()


def test_auto_subtitle_routes_to_asr_srt_render():
    tokens = bot.subdub_progress_stage_tokens_for_product(bot.VIDEO_SUBTITLE_MODE_CREATE)
    assert tokens == (
        "received_video",
        "transcribing",
        "auto_subtitle_ready",
        "rendering_subtitle",
        "checking_file",
        "delivering",
    )


def test_auto_subtitle_status_has_no_dub_steps():
    labels = _progress_labels(bot.VIDEO_SUBTITLE_MODE_CREATE)
    assert "Nhận diện lời thoại" in labels
    assert "Tạo phụ đề tự động" in labels
    assert "Tạo giọng lồng tiếng" not in labels
    assert "Ghép giọng vào video" not in labels


def test_auto_subtitle_success_buttons_video_and_srt():
    keyboard = bot.video_dubbing_receipt_keyboard(
        "vi",
        state={
            "mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
            "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
            "final_video_available": "1",
            "final_subtitle_available": "1",
        },
    )
    labels = _labels(keyboard)
    assert "📹 Tải video phụ đề tự động" in labels
    assert "📄 Tải SRT" in labels
    assert all("audio" not in label.lower() for label in labels)


def test_auto_subtitle_no_speech_clean_no_charge():
    text = bot.subdub_known_failure_text("no_speech_detected", bot.VIDEO_SUBTITLE_MODE_CREATE, "vi")
    assert "chưa nhận diện được lời thoại rõ ràng" in text
    assert "Hệ thống chưa trừ Xu" in text
    assert "provider" not in text.lower()
    assert "ffmpeg" not in text.lower()


def test_dub_video_no_red_fail_after_video_delivery():
    key = "p019m6-dub-terminal"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=1, chat_id=1)
    bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        terminal_artifact_type="video",
        video_delivery_message_id="901",
    )
    message = CaptureMessage()
    result = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_DUB, reason="late_fail"))
    assert result["suppressed"] is True
    assert message.calls == []
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["late_fail_suppressed"] is True


def test_dub_video_does_not_auto_send_mp3_after_mp4():
    message = CaptureMessage()
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            audio_bytes=b"audio",
            video_bytes=MP4_BYTES,
            include_subtitle_outputs=False,
        )
    )
    assert sent["video"] == 1
    assert sent["audio"] == 0
    assert [kind for kind, _payload in message.calls] == ["video"]


def test_dub_audio_sent_only_on_download_button():
    keyboard = bot.video_dubbing_receipt_keyboard(
        "vi",
        state={
            "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
            "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_DUB,
            "final_video_available": "1",
            "final_audio_available": "1",
        },
    )
    labels = _labels(keyboard)
    callbacks = _callbacks(keyboard)
    assert "🎧 Tải audio" in labels
    assert "videodub|download_final_audio" in callbacks


def test_dub_female_voice_resolves_female(monkeypatch):
    monkeypatch.setattr(bot.minimax_voice_adapter, "validate_provider_voice_id", lambda value: bool(value))
    state = {"voice_kind": "default_female", "selected_voice_gender": "female", "voice_style": "Giọng nữ"}
    result = bot.resolve_video_dub_tts_voice(1, state)
    assert result["ok"] is True
    assert result["resolved_gender"] == "female"
    assert state["resolved_gender"] == "female"


def test_dub_exact_voice_id_not_replaced(monkeypatch):
    monkeypatch.setattr(bot.minimax_voice_adapter, "validate_provider_voice_id", lambda value: bool(value))
    state = {"selected_voice_id": "female-real-voice", "selected_voice_gender": "female", "voice_style": "Giọng nữ"}
    assert bot.resolve_video_dub_tts_voice_id(1, state) == "female-real-voice"
    assert state["resolved_voice_id"] == "female-real-voice"
    assert state["voice_fallback_used"] is False


def test_dub_voice_fallback_debugged(monkeypatch):
    monkeypatch.setattr(bot.minimax_voice_adapter, "validate_provider_voice_id", lambda value: bool(value))
    state = {"selected_voice_id": "male-real-voice", "selected_voice_gender": "female", "voice_style": "Giọng nữ"}
    result = bot.resolve_video_dub_tts_voice(1, state)
    assert result["ok"] is False
    assert result["resolved_gender"] == "male"
    assert result["fallback_used"] is False
    assert result["fallback_reason"] == "selected_voice_gender_unavailable"
    assert state["voice_fallback_reason"] == "selected_voice_gender_unavailable"


def test_subtitle_dub_manual_refresh_read_only():
    payload = bot.subdub_status_debug_payload({"terminal_state": "processing"})
    assert payload["manual_refresh_read_only"] is True
    assert payload["reprocess_on_refresh"] is False
    assert payload["provider_call_on_refresh"] is False
    assert payload["send_output_on_refresh"] is False


def test_subtitle_dub_manual_refresh_after_delivered_no_error():
    text = bot.subdub_job_public_status_text(
        {"status": "failed", "terminal_state": "delivered", "output_sent": True, "job_id": "abc"},
        "vi",
    )
    assert "Có lỗi khi xử lý lệnh" not in text
    assert "chưa" not in text.lower()
    assert "Gửi kết quả" in text or "Đã gửi kết quả" in text


def test_subtitle_dub_no_audio_fallback_after_video_delivered():
    message = CaptureMessage()
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            audio_bytes=b"audio",
            video_bytes=MP4_BYTES,
            srt_text=VALID_SRT,
            include_subtitle_outputs=True,
        )
    )
    assert sent["video"] == 1
    assert sent["audio"] == 0
    assert [kind for kind, _payload in message.calls] == ["video"]


def test_subtitle_dub_success_buttons_correct():
    keyboard = bot.video_dubbing_receipt_keyboard(
        "vi",
        state={
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "final_video_available": "1",
            "final_subtitle_available": "1",
            "final_audio_available": "1",
        },
    )
    labels = _labels(keyboard)
    assert "🔁 Làm video khác" in labels
    assert "🏠 Menu chính" in labels


def test_video_without_subtitle_hides_direct_dub():
    keyboard = bot.subtitle_plus_dub_no_subtitle_menu_keyboard("vi")
    labels = _labels(keyboard)
    callbacks = _callbacks(keyboard)
    assert "🎙 Lồng tiếng trực tiếp" not in labels
    assert all(bot.VIDEO_DUBBING_NO_SUBTITLE_DIRECT_DUB not in str(callback) for callback in callbacks)
    assert bot.subdub_direct_dub_public_enabled() is False


def test_video_without_subtitle_keeps_auto_subtitle_then_dub():
    labels = _labels(bot.subtitle_plus_dub_no_subtitle_menu_keyboard("vi"))
    assert "🎬 Tạo phụ đề rồi lồng tiếng" in labels


def test_auto_subtitle_then_dub_routes_correct_mode():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "combo_subpath": bot.VIDEO_DUBBING_NO_SUBTITLE_CREATE_THEN_DUB,
    }
    assert bot.subdub_canonical_mode(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, state) == bot.SUBDUB_CANONICAL_MODE_SUBTITLE_DUB


def test_auto_subtitle_then_dub_has_invoice():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "combo_subpath": bot.VIDEO_DUBBING_NO_SUBTITLE_CREATE_THEN_DUB,
        "billing_chars": 1000,
        "target_language": "Tiếng Việt",
        "voice_style": "Giọng nữ",
    }
    text = bot.video_dubbing_confirm_text(state, "vi")
    for label in ["Phụ đề tự động", "Lồng tiếng", "Tổng trước giảm", "Giảm giá", "Tổng thanh toán"]:
        assert label in text
    assert "VAT" not in text
    assert "TNDN" not in text


def test_auto_subtitle_then_dub_price_is_subtitle_plus_dub():
    invoice = bot.video_dubbing_invoice_breakdown(
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "combo_subpath": bot.VIDEO_DUBBING_NO_SUBTITLE_CREATE_THEN_DUB,
            "billing_chars": 1000,
        }
    )
    assert invoice["auto_subtitle_then_dub"] is True
    assert invoice["subtitle_xu"] > 0
    assert invoice["voice_xu"] > 0
    assert invoice["total_xu"] == invoice["subtitle_xu"] + invoice["voice_xu"]


def test_subdub_x2_base_price_applied():
    payload = bot.subdub_pricing_audit_payload()
    assert payload["voice_subdub_base_x2"] is True
    assert payload["default_voice_rate_xu"] >= 0.10
    assert payload["custom_voice_rate_xu"] >= 0.20


def test_volume_discount_cap_30_percent(monkeypatch):
    monkeypatch.setattr(bot, "finance_volume_discount_percent", lambda _chars: 99)
    quote = bot.calculate_video_only_char_price(1000, 1.0)
    assert quote["discount_percent"] == 30


def test_b2c_no_vat_added_to_price():
    invoice = bot.video_dubbing_invoice_breakdown(
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "combo_subpath": bot.VIDEO_DUBBING_NO_SUBTITLE_CREATE_THEN_DUB,
            "billing_chars": 1000,
        }
    )
    assert invoice["b2c_vat_xu"] == 0
    assert invoice["b2c_cit_xu"] == 0


def test_subdub_accepts_input_under_50mb():
    validation = bot.subdub_validate_input_size_bytes(20 * 1024 * 1024)
    assert validation["ok"] is True
    assert validation["configured_limit_mb"] == 50


def test_subdub_rejects_input_over_configured_limit_cleanly(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_INPUT_MAX_MB", 1)
    validation = bot.subdub_validate_input_size_bytes(2 * 1024 * 1024)
    text = bot.subdub_file_too_large_text(validation["configured_limit_mb"], "vi")
    assert validation["ok"] is False
    assert validation["blocker"] == "file_too_large"
    assert "vượt giới hạn dung lượng" in text
    assert "Hệ thống chưa trừ Xu" in text


def test_subdub_output_under_50mb_sent(monkeypatch):
    _set_delivery_limits(monkeypatch, preview=45, document=50, output=50)
    message = CaptureMessage()
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            video_bytes=b"x" * (2 * 1024 * 1024),
            include_subtitle_outputs=False,
            strict_validation=True,
        )
    )
    assert sent["video"] == 1
    assert sent["output_configured_limit_mb"] == 50


def test_subdub_large_output_uses_document_fallback(monkeypatch):
    _set_delivery_limits(monkeypatch, preview=1, document=50, output=50)
    message = CaptureMessage()
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
            video_bytes=b"x" * (2 * 1024 * 1024),
            include_subtitle_outputs=False,
            strict_validation=True,
        )
    )
    assert [kind for kind, _payload in message.calls] == ["document"]
    assert sent["video_document"] == 1
    assert sent["delivery_method"] == "document"


def test_subdub_file_too_large_no_generic_error():
    text = bot.subdub_known_failure_text("file_too_large", bot.VIDEO_SUBTITLE_MODE_DUB, "vi", limit_mb=50)
    assert "Có lỗi khi xử lý lệnh" not in text
    assert "vượt giới hạn dung lượng" in text


def test_manual_refresh_never_reprocesses():
    payload = bot.subdub_status_debug_payload()
    assert payload["reprocess_on_refresh"] is False
    assert payload["provider_call_on_refresh"] is False


def test_manual_refresh_never_sends_generic_error_after_delivered():
    payload = bot.subdub_status_debug_payload({"terminal_state": "delivered", "video_delivery_message_id": "123"})
    assert payload["late_fail_suppressed"] is True
    assert payload["generic_error_after_delivered"] is False


def test_terminal_lock_blocks_late_fail():
    key = "p019m6-terminal-lock"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=2, chat_id=2)
    bot.mark_subtitle_dub_pipeline_output_sent(key, terminal_state="delivered", terminal_artifact_type="video", video_delivery_message_id="456")
    assert bot.subdub_job_blocks_public_fail(bot.SUBTITLE_DUB_PIPELINE_JOBS[key]) is True


def test_delivery_debug_shows_message_ids():
    text = bot.subtitle_dub_debug_text(
        {
            "internal_job_id": "job1",
            "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
            "status": "completed",
            "pipeline_attempted": True,
            "input_file_size": 123,
            "input_configured_limit_mb": 50,
            "output_bytes": 456,
            "output_configured_limit_mb": 50,
            "delivery_method": "video",
            "telegram_send_method": "video",
            "video_delivery_message_id": "789",
            "terminal_state": "delivered",
            "late_fail_suppressed": True,
        }
    )
    assert "video delivery message id" in text
    assert "789" in text
    assert "input configured limit" in text
    assert "output configured limit" in text
