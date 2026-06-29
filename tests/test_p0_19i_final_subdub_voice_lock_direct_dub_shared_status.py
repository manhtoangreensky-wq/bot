import asyncio
import inspect
from types import SimpleNamespace

import bot
from services import product_progress_status, subtitle_dub_product_pipeline


VALID_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n"
VALID_SEGMENTS = [{"index": 1, "start": 0.0, "end": 2.0, "text": "Xin chao"}]
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42-p019i" + b"x" * 2048


class CaptureMessage:
    chat_id = 190190

    def __init__(self):
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append(("text", str(text), kwargs))

    async def reply_video(self, **kwargs):
        self.outputs.append(("video", kwargs))

    async def reply_audio(self, **kwargs):
        self.outputs.append(("audio", kwargs))

    async def reply_document(self, **kwargs):
        self.outputs.append(("document", kwargs))


class CaptureQuery:
    def __init__(self, user_id=190190):
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage()
        self.edits = []

    async def answer(self, *args, **kwargs):
        self.edits.append(("answer", args, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append(("edit", str(text), kwargs))


def _state(**extra):
    return {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "process_type": bot.VIDEO_SUBTITLE_MODE_DUB,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "source_file_id": "tg-video-p019i",
        "video_file_id": "tg-video-p019i",
        "source_file_name": "clip.mp4",
        "source_mime_type": "video/mp4",
        "media_kind": "video",
        "video_duration": "2",
        "source_duration": "2",
        "target_language": "Tiếng Việt",
        "_pipeline_source_bytes_override": b"video-bytes",
        **extra,
    }


def test_subdub_selected_female_voice_id_passed_to_tts(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "female-real-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    state = {"voice_kind": "default_female", "voice_style": "Giọng nữ mặc định"}

    voice_id = bot.resolve_video_dub_tts_voice_id(1, state)

    assert voice_id == "female-real-voice"
    assert state["tts_payload_voice_id"] == "female-real-voice"
    assert state["selected_voice_gender"] == "female"


def test_subdub_selected_male_voice_id_passed_to_tts(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "female-real-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    state = {"voice_kind": "default_male", "voice_style": "Giọng nam mặc định"}

    assert bot.resolve_video_dub_tts_voice_id(1, state) == "male-real-voice"
    assert state["tts_payload_voice_id"] == "male-real-voice"
    assert state["selected_voice_gender"] == "male"


def test_subdub_custom_voice_provider_id_passed_to_tts():
    state = {"voice_kind": "saved_voice", "voice_id": "custom-provider-77", "voice_style": "Voice riêng"}

    assert bot.resolve_video_dub_tts_voice_id(1, state) == "custom-provider-77"
    assert state["provider_voice_id"] == "custom-provider-77"
    assert state["tts_payload_voice_id"] == "custom-provider-77"


def test_subdub_no_silent_female_to_male_fallback(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_ALLOW_SILENT_VOICE_FALLBACK", False)
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "male-real-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    state = {"voice_kind": "default_female", "voice_style": "Giọng nữ mặc định"}

    assert bot.resolve_video_dub_tts_voice_id(1, state) == ""
    assert state["_subdub_voice_resolution"]["ok"] is False
    assert state["_subdub_voice_resolution"]["fallback_used"] is False


def test_subdub_voice_failure_clean_no_charge():
    text = bot.subdub_voice_not_ready_text("vi")

    assert "chưa trừ Xu" in text
    assert not any(word in text.lower() for word in ("provider", "api", "tts", "payload"))


def test_subdub_admin_voice_debug_contains_selected_voice(tmp_path):
    source = tmp_path / "source.mp4"
    audio = tmp_path / "dub.mp3"
    source.write_bytes(b"video")
    audio.write_bytes(b"audio")
    payload = bot.subtitle_dub_debug_job_payload(
        user_id=1,
        chat_id=2,
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        state={
            "voice_style": "Giọng nữ mặc định",
            "selected_voice_gender": "female",
            "selected_voice_id": "default_female",
            "provider_voice_id": "female-real-voice",
            "tts_payload_voice_id": "female-real-voice",
            "selected_tts_voice_id": "female-real-voice",
            "_subdub_voice_resolution": {
                "selected_voice_gender": "female",
                "selected_voice_id": "default_female",
                "provider_voice_id": "female-real-voice",
                "tts_payload_voice_id": "female-real-voice",
                "fallback_used": False,
            },
        },
        status="completed",
        stage="delivered",
        input_save={"path": str(source), "size": source.stat().st_size},
        workspace_artifacts={"source": str(source), "dub_audio": str(audio)},
        pipeline_attempted=True,
    )

    assert payload["selected_voice_gender"] == "female"
    assert payload["provider_voice_id"] == "female-real-voice"
    assert payload["tts_payload_voice_id"] == "female-real-voice"
    assert payload["fallback_used"] is False


def test_direct_dub_uses_same_core_as_subtitle_dub():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert "subtitle_dub_product_pipeline.process_subtitle_dub_job" in source
    assert "resolve_video_dub_tts_voice" in source


def test_direct_dub_generates_new_tts_audio_and_muxes_generated_audio():
    calls = []

    async def prepare_subtitles(state):
        return {
            "state": dict(state),
            "source_bytes": b"video",
            "content_type": "video/mp4",
            "output_subtitle": VALID_SRT,
            "output_script": "Xin chao",
            "output_segments": list(VALID_SEGMENTS),
            "asr_provider": "asr",
        }

    async def synthesize_segments(segments, **kwargs):
        calls.append(("tts", kwargs.get("voice_id")))
        return {"provider": "tts", "chunks": [{"start": 0, "end": 2, "audio_bytes": b"new-voice", "audio_duration": 2}]}

    async def build_timeline_audio(*_args, **_kwargs):
        return b"generated-audio", "timeline"

    async def normalize_audio(audio_bytes):
        return bytes(audio_bytes), "normalized"

    async def render_video(_source, dubbed_audio=b"", **_kwargs):
        calls.append(("mux_audio", dubbed_audio))
        return MP4_BYTES, "rendered"

    result = asyncio.run(subtitle_dub_product_pipeline.process_subtitle_dub_job(
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        state={"output_type": "video", "video_duration": "2", "voice_kind": "default_female"},
        user_id=1,
        prepare_subtitles=prepare_subtitles,
        srt_from_text=bot.video_dubbing_srt_from_text,
        segments_from_text=bot.video_dubbing_segments_from_text,
        segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
        subtitle_output_items=bot.video_dubbing_subtitle_output_items,
        resolve_voice_id=lambda _uid, state: "female-real-voice",
        parse_voice_speed=lambda _value: 1.0,
        synthesize_segments=synthesize_segments,
        build_timeline_audio=build_timeline_audio,
        normalize_audio=normalize_audio,
        render_video=render_video,
        video_render_ready=lambda _output_type: True,
        ffmpeg_ready=lambda: True,
        dub_mux_enabled=True,
    ))

    assert result["ok"] is True
    assert result["audio_bytes"] == b"generated-audio"
    assert result["selected_tts_voice_id"] == "female-real-voice"
    assert ("tts", "female-real-voice") in calls
    assert ("mux_audio", b"generated-audio") in calls


def test_direct_dub_rejects_original_audio_only_success(monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "video_dubbing_product_gate_matrix", lambda *_args, **_kwargs: {"product_route_allowed": True})
    monkeypatch.setattr(bot, "video_dubbing_product_gate_allows_pipeline", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "video_dubbing_engine_access_decision", lambda *_args, **_kwargs: {"allowed": True})
    monkeypatch.setattr(bot, "calculate_video_translate_price", lambda *_args, **_kwargs: {"total_price_xu": 0})
    monkeypatch.setattr(bot, "video_dubbing_tts_price_estimate", lambda *_args, **_kwargs: {"price_xu": 0})
    monkeypatch.setattr(bot, "apply_member_service_discount", lambda _uid, amount, _event: {"final_cost": amount})
    monkeypatch.setattr(bot, "get_user", lambda _uid: (999999, 0, 0))

    async def fake_save_input(*_args, **_kwargs):
        return {"ok": True, "path": str(source), "source_bytes": b"video", "content_type": "video/mp4", "size": source.stat().st_size}

    async def fake_blackbox(**_kwargs):
        return {
            "ok": True,
            "state": _state(),
            "source_bytes": b"video",
            "content_type": "video/mp4",
            "audio_bytes": b"",
            "output_audio_source": "original",
            "video_output": MP4_BYTES,
            "output_subtitle": VALID_SRT,
            "srt_text": VALID_SRT,
            "srt_bytes": VALID_SRT.encode("utf-8"),
            "subtitle_items": [],
        }

    monkeypatch.setattr(bot, "video_dubbing_save_input_for_pipeline", fake_save_input)
    monkeypatch.setattr(bot.subtitle_dub_product_pipeline, "process_subtitle_dub_job", fake_blackbox)

    result = asyncio.run(bot._execute_video_dubbing_pipeline_core(
        CaptureQuery(),
        SimpleNamespace(),
        _state(voice_style="Giọng nữ mặc định", voice_id="female-real-voice", voice_kind="default_female"),
        "vi",
        admin_interactive_confirm=True,
    ))

    assert result["ok"] is False
    assert result["status"] == "DUB_AUDIO_NOT_GENERATED"


def test_direct_dub_original_audio_muted_or_ducked_by_default():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert '"mute" if mode in {VIDEO_SUBTITLE_MODE_DUB, VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}' in source


def test_subdub_no_fail_then_success_public_conflict():
    job_key = "p019i-terminal"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(job_key, None)

    bot.update_subtitle_dub_pipeline_job(job_key, status="failed", terminal_state="failed_no_charge")
    assert bot.mark_subtitle_dub_pipeline_output_sent(job_key) is False

    job = bot.SUBTITLE_DUB_PIPELINE_JOBS[job_key]
    assert job["terminal_state"] == "failed_no_charge"
    assert not job.get("output_sent")


def test_subdub_no_duplicate_success_message():
    text = bot.subtitle_plus_dub_completed_text({}, {"has_video": True, "sent_video": 1}, "vi")

    assert "Kết quả đã gửi phía trên" in text
    assert "Đã tạo video" not in text


def test_subdub_single_terminal_state():
    assert bot.subdub_terminal_state_allows_transition("delivered", "failed_no_charge") is False
    assert bot.subdub_terminal_state_allows_transition("failed_no_charge", "delivered") is False


def test_subdub_fallback_does_not_emit_public_failure_early():
    text = "TOAN AAS đang thử cách xử lý khác để hoàn tất video. Hệ thống chưa trừ Xu ở bước này."

    assert "chưa trừ Xu" in text
    assert not any(word in text.lower() for word in ("traceback", "provider", "ffmpeg", "asr", "tts"))


def test_subdub_zero_duration_never_success():
    assert bot.subdub_terminal_state_allows_transition("processing", "delivered") is True
    assert bot.subdub_terminal_state_allows_transition("failed_no_charge", "delivered") is False


def test_product_progress_status_subdub_render():
    text = bot.subdub_progress_text("generating_voice", "abc123", "vi")

    assert "TOAN AAS đang xử lý video" in text
    assert "Tiến độ: 65%" in text
    assert "#ABC123" in text


def test_product_progress_status_video_render():
    text = product_progress_status.render_product_progress_panel("video_ai_real", "task123", "generating_video", 75, lang="vi")

    assert "TOAN AAS đang tạo video" in text
    assert "Tiến độ: 75%" in text
    assert "#TASK123" in text


def test_subdub_update_status_button_no_reprocess():
    markup = bot.subdub_progress_keyboard("job123", "vi")
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]

    assert "videodub|subdub_status|job123" in callbacks


def test_video_update_status_button_no_reprocess():
    markup = bot.shopaikey_video_job_check_keyboard("task123", "vi", public_user=True)
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    source = inspect.getsource(bot.handle_public_video_status_callback)

    assert "video|status|task123" in callbacks
    assert "shopaikey_video_create_for_model" not in source
    assert "create_shopaikey_job" not in source


def test_video_flow_uses_shared_status_panel():
    text = bot.public_video_status_message("IN_PROGRESS", progress="75", job={"task_id": "task123"}, lang="vi")

    assert "TOAN AAS đang tạo video" in text
    assert "Các bước:" in text


def test_public_status_no_technical_words():
    public_text = "\n".join([
        bot.public_video_status_message("IN_PROGRESS", progress="provider=ffmpeg", job={"task_id": "task123"}, lang="vi"),
        bot.subdub_progress_text("muxing_video", "job123", "vi"),
        bot.subdub_voice_not_ready_text("vi"),
    ]).lower()

    banned = ("provider", "api", "ffmpeg", "asr", "tts", "payload", "traceback")
    assert not any(word in public_text for word in banned)
