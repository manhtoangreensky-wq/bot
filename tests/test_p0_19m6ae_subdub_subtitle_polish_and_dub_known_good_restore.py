import asyncio
import inspect
import os
import subprocess

import pytest

import bot
from services import product_progress_status, subtitle_dub_product_pipeline


VALID_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao ca nha\n"


class _Sent:
    def __init__(self, message_id):
        self.message_id = message_id


class _Message:
    def __init__(self):
        self.videos = []
        self.documents = []
        self.audios = []

    async def reply_video(self, **kwargs):
        self.videos.append(kwargs)
        return _Sent(901)

    async def reply_document(self, **kwargs):
        self.documents.append(kwargs)
        return _Sent(902)

    async def reply_audio(self, **kwargs):
        self.audios.append(kwargs)
        return _Sent(903)


def _changed_files() -> set[str]:
    output = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True)
    return {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}


def _skip_unless_m6ae_scope() -> None:
    branch = os.getenv("GITHUB_HEAD_REF") or ""
    if not branch:
        try:
            branch = subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
        except Exception:
            branch = ""
    if "m6ae" not in branch.lower():
        pytest.skip("M6AE scope guard only applies on M6AE branches")


def test_subtitle_only_video_delivery_sets_100_and_all_steps_green():
    key = "m6ae-subtitle-delivered"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    acquired, _job = bot.acquire_subtitle_dub_pipeline_job(
        key,
        user_id=196601,
        chat_id=196601,
        mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    )
    assert acquired is True

    ok = bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="901",
        terminal_artifact_type="video",
        video_delivery_message_id="901",
    )
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    panel = product_progress_status.render_product_progress_panel(
        "subdub",
        stored["job_id"],
        stored["current_stage"],
        stored["progress_percent"],
        stored["terminal_state"],
        completed_steps=stored["completed_steps"],
    )

    assert ok is True
    assert stored["terminal_state"] == "delivered"
    assert stored["progress_percent"] == 100
    assert stored["status_panel_terminalized"] is True
    assert stored["refresh_stopped_after_terminal"] is True
    assert "Tiến độ: 100%" in panel
    assert "✅ Gửi kết quả" in panel
    assert "⬜" not in panel


def test_no_auto_srt_when_subtitle_video_delivered():
    message = _Message()
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            active_flow="subtitle_translate",
            subtitle_items=[{
                "output_type": "srt",
                "filename": "toan_aas_subtitle_translate.srt",
                "bytes": VALID_SRT.encode("utf-8"),
            }],
            srt_text=VALID_SRT,
            video_bytes=b"mp4-bytes",
            lang="vi",
        )
    )

    assert sent["final_mp4_delivered"] is True
    assert sent["srt_auto_send_suppressed"] is True
    assert sent["srt_suppress_reason"] == "video_delivered"
    assert sent["explicit_srt_download_available"] is True
    assert len(message.videos) == 1
    assert len(message.documents) == 0


def test_no_partial_copy_when_subtitle_video_delivered():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "target_language": "Tiếng Việt", "video_duration": 30},
        {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "video_delivery_message_id": "901", "charged": 0},
        "vi",
    )

    assert "Đã tạo video phụ đề thành công" in text
    assert "chưa tạo được video hoàn chỉnh" not in text
    assert "chưa dịch được phụ đề" not in text


def test_explicit_srt_download_still_available_if_supported():
    labels = [
        button.text
        for row in bot.video_dubbing_receipt_keyboard(
            "vi",
            "translation",
            {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "active_flow": "subtitle_translate"},
        ).inline_keyboard
        for button in row
    ]

    assert "📄 Tải SRT dịch" in labels


def test_true_subtitle_failure_can_send_clean_no_charge_message():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE},
        {"terminal_public_outcome_type": "failure"},
        "vi",
    )

    assert "Hệ thống chưa trừ Xu" in text
    assert "provider" not in text.lower()
    assert "ffmpeg" not in text.lower()


def test_subtitle_font_reduced_by_two_from_current_formula():
    style_720 = bot.subdub_normalize_style({
        "subtitle_style_preset": "cover_original",
        "video_width": 1280,
        "video_height": 720,
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    })
    style_1080 = bot.subdub_normalize_style({
        "subtitle_style_preset": "cover_original",
        "video_width": 1920,
        "video_height": 1080,
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    })

    assert style_720["render_size"] == style_720["size"] + 2
    assert style_1080["render_size"] == style_1080["size"] + 2
    assert style_720["translated_font_size_final"] == style_720["render_size"]


def test_subtitle_bottom_center_closer_to_bottom_and_no_giant_bar():
    ass = bot.subdub_generate_ass_from_srt(
        VALID_SRT,
        {
            "subtitle_style_preset": "cover_original",
            "video_width": 1280,
            "video_height": 720,
            "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        },
    )
    style = bot.subdub_normalize_style({
        "subtitle_style_preset": "cover_original",
        "video_width": 1280,
        "video_height": 720,
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    })

    assert ",2,54,54," in ass
    assert style["text_margin_bottom_ratio"] <= 0.05
    assert style["cover_height_ratio"] <= 0.06
    assert style["cover_y_ratio"] >= 0.90


def test_subtitle_wraps_without_losing_text():
    words = "mot hai ba bon nam sau bay tam chin muoi muoi mot muoi hai muoi ba muoi bon"
    style = bot.subdub_normalize_style({
        "subtitle_style_preset": "cover_original",
        "video_width": 720,
        "video_height": 1280,
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    })
    wrapped = bot.subdub_ass_wrap_text(words, style, 2)

    assert "\\N" in wrapped
    normalized_wrapped = wrapped.replace("\\N", " ")
    for word in words.split():
        assert word in normalized_wrapped


def test_subtitle_only_31_60_90s_allowed_full_mode():
    for seconds in (31, 60, 90):
        payload = bot.subdub_duration_gate_payload({"ok": True, "duration": seconds}, {}, is_admin=False)
        assert payload["duration_limit_seconds"] >= 300
        assert payload["duration_gate_result"] == "pass_long"
        assert payload["long_media_allowed"] is True


def test_preview_mode_30s_limit_remains_preview_only():
    assert bot.subdub_preview_duration_seconds() == 30
    assert bot.subdub_full_duration_limit_seconds(False) > bot.subdub_preview_duration_seconds()
    source = inspect.getsource(bot.video_dubbing_prepare_subtitles)
    assert "SUBDUB_PREVIEW_DURATION_SECONDS" not in source


def test_dub_only_uses_known_good_shared_path_and_sends_mp4():
    async def prepare_subtitles(state):
        return {
            "state": {**state, "video_duration": 2},
            "source_bytes": b"source-video",
            "content_type": "video/mp4",
            "output_subtitle": VALID_SRT,
            "output_script": "Xin chao ca nha",
            "output_segments": [{"start": 0, "end": 2, "text": "Xin chao ca nha"}],
            "asr_provider": "fake_asr",
        }

    async def synthesize_segments(*args, **kwargs):
        return {"provider": "fake_tts", "chunks": [{"start": 0, "end": 2, "audio": b"voice"}]}

    async def build_timeline_audio(chunks, duration):
        return b"raw-audio", "ok"

    async def normalize_audio(raw):
        return b"dub-audio", "ok"

    async def render_video(*args, **kwargs):
        return b"final-mp4", "ffmpeg_video_render_basic:validated"

    result = asyncio.run(
        subtitle_dub_product_pipeline.run_subdub_pipeline(
            job_id="m6ae-dub",
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            state={"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "output_type": "video", "voice_speed": "1.0"},
            user_id=196602,
            prepare_subtitles=prepare_subtitles,
            srt_from_text=bot.video_dubbing_srt_from_text,
            segments_from_text=bot.video_dubbing_segments_from_text,
            segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
            subtitle_output_items=bot.video_dubbing_subtitle_output_items,
            resolve_voice_id=lambda _uid, _state: "female-shaonv",
            parse_voice_speed=bot.parse_video_dubbing_voice_speed,
            synthesize_segments=synthesize_segments,
            build_timeline_audio=build_timeline_audio,
            normalize_audio=normalize_audio,
            render_video=render_video,
            video_render_ready=lambda _output_type: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
            is_admin=True,
        )
    )

    assert result["ok"] is True
    assert result["product_type"] == "dub_only"
    assert result["video_output"] == b"final-mp4"
    assert result["result_type"] == "mp4"
    assert result["route_attempts"]["shared_core"] is True
    assert result["route_attempts"]["tts"] is True
    assert result["route_attempts"]["render"] is True


def test_subtitle_dub_no_auto_srt_after_mp4():
    message = _Message()
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            active_flow=bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
            subtitle_items=[{"output_type": "srt", "filename": "x.srt", "bytes": VALID_SRT.encode("utf-8")}],
            srt_text=VALID_SRT,
            audio_bytes=b"dub-audio",
            video_bytes=b"mp4-bytes",
            lang="vi",
        )
    )

    assert sent["final_mp4_delivered"] is True
    assert sent["documents"] == 0
    assert sent["srt_auto_send_suppressed"] is True


def test_subdub_public_ui_no_internal_terms_in_touched_receipt():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "target_language": "English"},
        {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "video_delivery_message_id": "901"},
        "vi",
    ).lower()

    for term in ("provider", "api", "ffmpeg", "handler", "callback", "traceback"):
        assert term not in text


def test_m6ae_no_product_video_music_voice_payos_pricing_db_changes():
    _skip_unless_m6ae_scope()
    changed = _changed_files()
    allowed = {
        "bot.py",
        "tests/test_p0_19m6ae_subdub_subtitle_polish_and_dub_known_good_restore.py",
        "tests/test_p0_19m5_complete_subdub_status_style_dub_voice_audio_delivery_sync.py",
        "tests/test_p0_19m6a_subdub_one_terminal_public_outcome_late_error_duplicate_fix.py",
        "tests/test_p0_19m6ab_subdub_suppress_late_fail_x_after_success_only.py",
        "tests/test_p0_19m6v_subdub_final_delivery_report_font2x_female_voice_fix.py",
        "tests/test_p0_19m6w_subdub_emergency_rollback_pipeline_font_volume_ui.py",
        "tests/test_p0_23h14m_music_delivery_lock_no_duplicate_mp3_no_late_x.py",
        "tests/test_p0_public_media_real_qa_subdub_voice_long_video.py",
    }

    assert changed <= allowed


def test_m6ae_no_asr_tts_provider_core_rewrite():
    _skip_unless_m6ae_scope()
    changed = _changed_files()

    assert not any(path.startswith("providers/") for path in changed)
    assert "services/provider_gate.py" not in changed


def test_m6ae_no_webhook_change():
    diff = subprocess.check_output(["git", "diff", "origin/main", "--", "bot.py"], text=True)

    assert "set_webhook" not in diff
    assert "delete_webhook" not in diff
