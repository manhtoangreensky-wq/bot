import asyncio
import inspect
import subprocess
from pathlib import Path
from types import SimpleNamespace

import bot
from services import subtitle_dub_product_pipeline


VALID_SRT = "1\n00:00:00,000 --> 00:00:03,000\nTrước tiên, hãy xem cô gái siêu đáng yêu này rốt cuộc là ai\n"
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42-p019m6x" + b"x" * 2048
REPO_ROOT = Path(__file__).resolve().parents[1]


class CaptureMessage:
    def __init__(self, chat_id=19680):
        self.chat_id = chat_id
        self.texts = []
        self.audios = []
        self.documents = []
        self.videos = []

    async def reply_text(self, text, **kwargs):
        self.texts.append(str(text))
        return SimpleNamespace(message_id=100 + len(self.texts), chat_id=self.chat_id)

    async def reply_audio(self, **kwargs):
        self.audios.append(kwargs)
        return SimpleNamespace(message_id=200 + len(self.audios), chat_id=self.chat_id)

    async def reply_document(self, **kwargs):
        self.documents.append(kwargs)
        return SimpleNamespace(message_id=300 + len(self.documents), chat_id=self.chat_id)

    async def reply_video(self, **kwargs):
        self.videos.append(kwargs)
        return SimpleNamespace(message_id=400 + len(self.videos), chat_id=self.chat_id)


def _changed_files() -> set[str]:
    output = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True)
    return {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}


def _subtitle_items():
    return bot.video_dubbing_subtitle_output_items(
        VALID_SRT,
        "srt",
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    )


def test_subdub_does_not_auto_send_srt_file(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_PUBLIC_SRT_FALLBACK_ENABLED", False)

    async def fake_send(_message, _payload, **_kwargs):
        return {"sent": True, "delivery_method": "video", "telegram_message_id": "901"}

    monkeypatch.setattr(bot, "send_generated_video_bytes_for_delivery", fake_send)
    message = CaptureMessage()

    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            subtitle_items=_subtitle_items(),
            srt_text=VALID_SRT,
            video_bytes=MP4_BYTES,
            include_subtitle_outputs=True,
        )
    )

    assert message.documents == []
    assert sent["video"] == 1
    assert sent["srt_artifact_exists"] is True
    assert sent["srt_public_auto_send_enabled"] is False
    assert sent["srt_auto_send_suppressed"] is True


def test_srt_can_be_sent_only_by_explicit_download_button(monkeypatch):
    monkeypatch.setattr(bot, "get_video_dubbing_artifact", lambda *_args, **_kwargs: VALID_SRT)
    message = CaptureMessage()
    state = {"translated_subtitle_ref": "translated-sub"}

    ok = asyncio.run(
        bot.subtitle_plus_dub_send_subtitle_document(
            message,
            19680,
            state,
            translated=True,
            output_type="srt",
        )
    )

    assert ok is True
    assert len(message.documents) == 1
    assert state["srt_sent_by_explicit_user_request"] is True
    assert "SRT" in message.documents[0]["caption"]


def test_final_video_success_does_not_send_srt_before_video(monkeypatch):
    order = []

    async def fake_send(_message, _payload, **_kwargs):
        order.append("video")
        return {"sent": True, "delivery_method": "video", "telegram_message_id": "902"}

    monkeypatch.setattr(bot, "SUBDUB_PUBLIC_SRT_FALLBACK_ENABLED", False)
    monkeypatch.setattr(bot, "send_generated_video_bytes_for_delivery", fake_send)
    message = CaptureMessage()

    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            subtitle_items=_subtitle_items(),
            srt_text=VALID_SRT,
            audio_bytes=b"audio",
            video_bytes=MP4_BYTES,
            include_subtitle_outputs=True,
        )
    )

    assert order == ["video"]
    assert message.documents == []
    assert sent["srt_delivery_message_id"] == ""


def test_srt_fallback_disabled_by_default():
    assert bot.SUBDUB_PUBLIC_SRT_FALLBACK_ENABLED is False


def test_no_partial_subtitle_file_copy_in_normal_flow():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE},
        {"has_subtitle": True, "has_video": False, "terminal_public_outcome_type": "failure"},
        "vi",
    )

    assert "gửi file phụ đề trước" not in text
    assert "đã tạo file phụ đề" not in text
    assert "tải về" not in text


def test_terminal_video_failure_copy_no_srt_fallback_terms():
    text = bot.subdub_subtitle_fallback_text(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "vi")

    assert "file phụ đề" not in text
    assert "SRT" not in text
    assert "chưa trừ Xu" in text


def test_processing_state_does_not_send_partial_copy():
    job = {"job_id": "M6XJOB", "terminal_state": "", "progress_stage": "validating_output", "progress_percent": 90}
    text = bot.subdub_job_public_status_text(job, "vi")

    assert "đã tạo file phụ đề" not in text
    assert "gửi file phụ đề trước" not in text


def test_subtitle_font_reduced_from_current_huge_live_size():
    style = bot.subdub_normalize_style({"subtitle_style_preset": "cover_original", "video_width": 1280, "video_height": 720})

    assert style["subtitle_font_size_reduced_one_level"] is True
    assert style["render_size"] <= 48
    assert style["translated_font_size_final"] == style["render_size"]


def test_subtitle_position_bottom_center():
    style = bot.subdub_normalize_style({"subtitle_style_preset": "cover_original", "video_width": 1280, "video_height": 720})
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, style)

    assert style["subtitle_alignment"] == "bottom_center"
    assert ",2,54,54," in ass
    assert style["subtitle_margin_v"] <= 46


def test_subtitle_max_two_lines():
    style = bot.subdub_normalize_style({"subtitle_style_preset": "cover_original", "video_width": 1280, "video_height": 720})
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, style)
    dialogue = next(line for line in ass.splitlines() if line.startswith("Dialogue:"))

    assert style["max_lines"] == 2
    assert dialogue.count("\\N") <= 1


def test_subtitle_does_not_cover_middle_screen():
    style = bot.subdub_normalize_style({"subtitle_style_preset": "cover_original", "video_width": 1280, "video_height": 720})

    assert style["position"] == "bottom"
    assert style["subtitle_margin_v"] < 60
    assert style["render_size"] < 60


def test_no_huge_black_bar():
    style = bot.subdub_normalize_style({"subtitle_style_preset": "cover_original", "video_width": 1280, "video_height": 720})
    drawbox = bot.subdub_cover_filter(style)

    assert style["black_bar_used"] is False
    assert "h=ih*0.24" not in drawbox
    assert style["cover_height_ratio"] <= 0.06


def test_vietnamese_glyphs_supported():
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, {"subtitle_style_preset": "cover_original", "video_width": 1280, "video_height": 720})

    assert "Trước tiên" in ass
    assert "đáng" in ass
    assert "yêu" in ass


def test_subdub_tts_speed_default_slower_than_current_fast_rate():
    assert bot.SUBDUB_DUB_SPEECH_RATE < 1.0
    assert bot.SUBDUB_DUB_MAX_SPEECH_RATE <= 1.15


def test_dub_audio_speed_factor_applied():
    recorded = {}

    async def prepare(_state):
        return {
            "source_bytes": b"video",
            "content_type": "video/mp4",
            "output_subtitle": VALID_SRT,
            "output_script": "Xin chào",
            "output_segments": [{"index": 1, "start": 0, "end": 3, "text": "Xin chào"}],
        }

    async def synthesize_segments(_segments, **kwargs):
        recorded.update(kwargs)
        return {"provider": "fake", "chunks": [{"start": 0, "end": 3, "audio_bytes": b"audio", "audio_duration": 2.5}]}

    result = asyncio.run(
        subtitle_dub_product_pipeline.run_subdub_pipeline(
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            state={"source_bytes": b"video", "content_type": "video/mp4", "voice_speed": "1.0"},
            user_id=19680,
            prepare_subtitles=prepare,
            srt_from_text=bot.video_dubbing_srt_from_text,
            segments_from_text=bot.video_dubbing_segments_from_text,
            segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
            subtitle_output_items=bot.video_dubbing_subtitle_output_items,
            resolve_voice_id=lambda *_args: "female-voice",
            parse_voice_speed=bot.parse_video_dubbing_voice_speed,
            synthesize_segments=synthesize_segments,
            build_timeline_audio=lambda *_args, **_kwargs: (b"audio", "ok"),
            normalize_audio=lambda audio, **_kwargs: (audio, "ok"),
            render_video=lambda *_args, **_kwargs: (MP4_BYTES, "ok"),
            video_render_ready=lambda _output_type: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
            is_admin=True,
        )
    )

    assert result["ok"] is True
    assert recorded["base_speed"] == bot.SUBDUB_DUB_SPEECH_RATE
    assert recorded["max_speed"] <= bot.SUBDUB_DUB_MAX_SPEECH_RATE
    assert result["applied_tts_speed"] == bot.SUBDUB_DUB_SPEECH_RATE


def test_subdub_female_voice_uses_voice_engine_default(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "female-real-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "voice_kind": "default_female",
        "voice_style": "Giọng nữ mặc định",
        "selected_voice_gender": "female",
    }

    resolution = bot.resolve_video_dub_tts_voice(19680, state)

    assert resolution["ok"] is True
    assert resolution["provider_voice_id"] == "female-real-voice"
    assert resolution["resolved_gender"] == "female"
    assert resolution["fallback_used"] is False
    assert state["tts_payload_voice_id"] == "female-real-voice"
    assert state["voice_fallback_used"] is False


def test_subdub_pipeline_passes_female_voice_to_tts(monkeypatch):
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "female-real-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    recorded = {}

    async def prepare(_state):
        return {
            "source_bytes": b"video",
            "content_type": "video/mp4",
            "output_subtitle": VALID_SRT,
            "output_script": "Xin chào",
            "output_segments": [{"index": 1, "start": 0, "end": 3, "text": "Xin chào"}],
        }

    async def synthesize_segments(_segments, **kwargs):
        recorded.update(kwargs)
        return {"provider": "fake", "chunks": [{"start": 0, "end": 3, "audio_bytes": b"audio", "audio_duration": 2.5}]}

    state = {
        "source_bytes": b"video",
        "content_type": "video/mp4",
        "voice_speed": "1.0",
        "voice_kind": "default_female",
        "voice_style": "Giọng nữ mặc định",
        "selected_voice_gender": "female",
    }

    result = asyncio.run(
        subtitle_dub_product_pipeline.run_subdub_pipeline(
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            state=state,
            user_id=19680,
            prepare_subtitles=prepare,
            srt_from_text=bot.video_dubbing_srt_from_text,
            segments_from_text=bot.video_dubbing_segments_from_text,
            segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
            subtitle_output_items=bot.video_dubbing_subtitle_output_items,
            resolve_voice_id=bot.resolve_video_dub_tts_voice_id,
            parse_voice_speed=bot.parse_video_dubbing_voice_speed,
            synthesize_segments=synthesize_segments,
            build_timeline_audio=lambda *_args, **_kwargs: (b"audio", "ok"),
            normalize_audio=lambda audio, **_kwargs: (audio, "ok"),
            render_video=lambda *_args, **_kwargs: (MP4_BYTES, "ok"),
            video_render_ready=lambda _output_type: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
            is_admin=True,
        )
    )

    assert result["ok"] is True
    assert recorded["voice_id"] == "female-real-voice"
    assert recorded["voice_id"] != "male-real-voice"


def test_dub_audio_aligns_to_segment_without_extreme_speedup():
    source = inspect.getsource(bot.synthesize_dub_segment_chunks)

    assert "max(1.35" not in source
    assert "compact_text" not in source
    assert "Keep translated dialogue intact" in source


def test_dub_speed_debug_fields_present():
    source = inspect.getsource(subtitle_dub_product_pipeline.process_subtitle_dub_job)

    for field in (
        "requested_tts_speed",
        "applied_tts_speed",
        "speed_adjustment_method",
        "dub_timing_alignment_applied",
        "dub_speed_blocker",
    ):
        assert field in source


def test_no_public_failure_before_final_video_still_possible():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB},
        {"has_subtitle": True, "has_video": False, "terminal_public_outcome_type": ""},
        "vi",
    )

    assert "đã tạo file phụ đề" not in text
    assert "gửi file phụ đề trước" not in text


def test_no_failure_after_success():
    source = inspect.getsource(bot.execute_video_dubbing_pipeline)

    assert "subdub_job_blocks_public_fail(current_job)" in source
    assert "late_error_suppressed" in source


def test_no_success_after_public_failure():
    source = inspect.getsource(bot.mark_subtitle_dub_pipeline_output_sent)

    assert "not subdub_public_outcome_allows_success(job)" in source
    assert "success_after_error_prevented" in source


def test_final_report_sent_once_after_video_delivery():
    source = (REPO_ROOT / "bot.py").read_text(encoding="utf-8")

    assert "success_sent_count=max(1" in source
    assert "subdub_success_message_id" in source


def test_terminal_lock_persisted():
    source = inspect.getsource(bot.mark_subtitle_dub_pipeline_output_sent)

    assert "terminal_locked_at" in source
    assert "status_panel_terminalized" in source


def test_international_subtitle_translation_still_delivers_video(monkeypatch):
    async def fake_send(_message, _payload, **_kwargs):
        return {"sent": True, "delivery_method": "video", "telegram_message_id": "904"}

    monkeypatch.setattr(bot, "send_generated_video_bytes_for_delivery", fake_send)
    message = CaptureMessage()
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            subtitle_items=_subtitle_items(),
            srt_text=VALID_SRT,
            video_bytes=MP4_BYTES,
            include_subtitle_outputs=True,
        )
    )

    assert sent["video_delivery_message_id"] == "904"
    assert message.documents == []


def test_international_subtitle_explicit_srt_download_still_works(monkeypatch):
    monkeypatch.setattr(bot, "get_video_dubbing_artifact", lambda *_args, **_kwargs: VALID_SRT)
    message = CaptureMessage()

    assert asyncio.run(bot.subtitle_plus_dub_send_subtitle_document(message, 19680, {"translated_subtitle_ref": "x"}, translated=True)) is True
    assert message.documents


def test_subtitle_only_flow_no_public_srt_auto_fallback(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_PUBLIC_SRT_FALLBACK_ENABLED", False)
    message = CaptureMessage()

    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            subtitle_items=_subtitle_items(),
            srt_text=VALID_SRT,
            video_bytes=b"",
            include_subtitle_outputs=True,
        )
    )

    assert sent["documents"] == 0
    assert message.documents == []
    assert sent["srt_auto_send_suppressed"] is True


def test_no_product_video_music_payos_pricing_db_changes():
    changed = _changed_files()
    allowed = {
        "bot.py",
        "services/subtitle_dub_product_pipeline.py",
        "tests/test_p0_17b_subtitle_translation_dubbing.py",
        "tests/test_p0_17b6_2_final_product_pipeline.py",
        "tests/test_p0_19d_live_subtitle_dub_blackbox_engine_fix_only.py",
        "tests/test_p0_19m5_complete_subdub_status_style_dub_voice_audio_delivery_sync.py",
        "tests/test_p0_19m6a_subdub_one_terminal_public_outcome_late_error_duplicate_fix.py",
        "tests/test_p0_19m6t_subdub_final_video_only_delivery_no_public_audio_fallback.py",
        "tests/test_p0_19m6v_subdub_final_delivery_report_font2x_female_voice_fix.py",
        "tests/test_p0_19m6w_subdub_emergency_rollback_pipeline_font_volume_ui.py",
        "tests/test_p0_19m6x_subdub_remove_public_srt_fallback_subtitle_style_dub_speed.py",
        "tests/test_task2_1_translation_product_logic_cleanup.py",
    }

    assert changed <= allowed
    forbidden = ("payos", "wallet", "pricing", "finance", "music", "suno", "video_provider", "remote_worker.py", "local_worker.py")
    assert not any(any(token in path.lower() for token in forbidden) for path in changed)


def test_no_large_telegram_duration_gate_changes():
    changed = _changed_files()

    assert not any("duration_gate" in path.lower() or "large_telegram" in path.lower() for path in changed if not path.startswith("tests/"))
