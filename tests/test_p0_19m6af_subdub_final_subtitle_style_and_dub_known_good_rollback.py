import asyncio
import os
import re
import subprocess
from types import SimpleNamespace

import pytest

import bot

pytestmark = pytest.mark.skip(reason="M6AF runtime was retired by P0.19M.M4RESTORE; PR160 shared core is authoritative.")


VALID_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao ca nha\n"
LONG_SRT = (
    "1\n"
    "00:00:00,000 --> 00:00:06,000\n"
    "Di thi di, roi lan nay cung may la co co hoi, Douyin cua to oi, to da co gang het suc roi vi the nen to moi bay ca quang duong dai nay sang day de noi chuyen nay.\n"
)


class _Sent:
    def __init__(self, message_id):
        self.message_id = message_id


class _Message:
    def __init__(self):
        self.videos = []
        self.documents = []
        self.audios = []
        self.texts = []

    async def reply_video(self, **kwargs):
        self.videos.append(kwargs)
        return _Sent(901)

    async def reply_document(self, **kwargs):
        self.documents.append(kwargs)
        return _Sent(902)

    async def reply_audio(self, **kwargs):
        self.audios.append(kwargs)
        return _Sent(903)

    async def reply_text(self, text, **kwargs):
        self.texts.append(str(text))
        return _Sent(904)


def _style_state(mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE):
    return {
        "subtitle_style_preset": "cover_original",
        "video_width": 1280,
        "video_height": 720,
        "mode": mode,
    }


def _style_line(ass: str) -> str:
    return next(line for line in ass.splitlines() if line.startswith("Style: Default"))


def _dialogue_lines(ass: str) -> list[str]:
    return [line for line in ass.splitlines() if line.startswith("Dialogue:")]


def _ass_time_to_seconds(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _event_times(line: str) -> tuple[float, float]:
    parts = line.split(",", 3)
    return _ass_time_to_seconds(parts[1]), _ass_time_to_seconds(parts[2])


def _event_text(line: str) -> str:
    return line.split(",", 9)[-1]


def _changed_files() -> set[str]:
    output = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True)
    return {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}


def test_m6af_subtitle_effective_font_size_reduced_from_live_path():
    style = bot.subdub_normalize_style(_style_state())

    assert style["subtitle_font_size_before_live_effective"] >= 48
    assert style["subtitle_font_size_after"] <= style["subtitle_font_size_before_live_effective"] - 2
    assert style["subtitle_font_size_delta"] <= -2
    assert style["subtitle_font_size_after"] <= 46


def test_m6af_subtitle_bottom_margin_near_edge():
    style = bot.subdub_normalize_style(_style_state())
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, _style_state())

    assert style["subtitle_margin_v_after"] <= 8
    assert _style_line(ass).endswith(",70,70,6,1")


def test_m6af_subtitle_bottom_center():
    style = bot.subdub_normalize_style(_style_state())
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, _style_state())

    assert style["subtitle_alignment"] == "bottom_center"
    assert ",2,70,70," in _style_line(ass)


def test_m6af_subtitle_max_two_lines():
    ass = bot.subdub_generate_ass_from_srt(LONG_SRT, _style_state())

    for line in _dialogue_lines(ass):
        assert line.count("\\N") <= 1


def test_m6af_subtitle_no_left_right_overflow():
    style = bot.subdub_normalize_style(_style_state())
    ass = bot.subdub_generate_ass_from_srt(LONG_SRT, _style_state())

    assert style["subtitle_wrap_no_overflow"] == "yes"
    for line in _dialogue_lines(ass):
        text = _event_text(line).replace("\\N", " ")
        assert len(text) <= 80


def test_m6af_subtitle_box_hugs_text_not_full_middle_bar():
    style = bot.subdub_normalize_style(_style_state())

    assert style["boxed_background"] is True
    assert bot.subdub_cover_filter(_style_state()) == ""


def test_m6af_subtitle_original_aspect_ratio_preserved():
    assert bot.subdub_video_fit_filters(_style_state()) == ["setsar=1"]


def test_m6af_long_caption_split_into_multiple_timed_events():
    ass = bot.subdub_generate_ass_from_srt(LONG_SRT, _style_state())
    events = _dialogue_lines(ass)

    assert len(events) >= 3
    assert len(events) <= 8


def test_m6af_no_overlapping_subtitle_events():
    ass = bot.subdub_generate_ass_from_srt(LONG_SRT, _style_state())
    previous_end = 0.0

    for line in _dialogue_lines(ass):
        start, end = _event_times(line)
        assert start >= previous_end
        assert end > start
        previous_end = end


def test_m6af_caption_order_preserved():
    ass = bot.subdub_generate_ass_from_srt(LONG_SRT, _style_state())
    joined = " ".join(_event_text(line).replace("\\N", " ") for line in _dialogue_lines(ass))

    assert joined.index("Di thi di") < joined.index("Douyin") < joined.index("quang duong")


def test_m6af_each_event_max_two_lines():
    ass = bot.subdub_generate_ass_from_srt(LONG_SRT, _style_state())

    assert all(line.count("\\N") <= 1 for line in _dialogue_lines(ass))


def test_m6af_timing_distributed_for_long_asr_segment():
    ass = bot.subdub_generate_ass_from_srt(LONG_SRT, _style_state())
    durations = [end - start for start, end in (_event_times(line) for line in _dialogue_lines(ass))]

    assert sum(durations) >= 5.9
    assert min(durations) >= 0.65


def test_m6af_dub_only_uses_known_good_path():
    calls = []

    async def render_func(*args, **kwargs):
        calls.append(dict(kwargs))
        if "original_audio_volume_percent" in kwargs or "dubbed_voice_volume_percent" in kwargs:
            return b"", "current_volume_mix_failed"
        return b"final-mp4", "ffmpeg_video_render_basic:validated"

    result, debug = asyncio.run(
        bot.subdub_render_with_known_good_dub_fallback(
            render_func,
            (b"source-video",),
            {
                "dubbed_audio": b"dub-audio",
                "subtitle_style": _style_state(bot.VIDEO_SUBTITLE_MODE_DUB),
                "keep_original_audio": True,
                "original_audio_mode": "keep",
                "original_audio_volume_percent": 80,
                "dubbed_voice_volume_percent": 200,
                "require_audio": True,
            },
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            subtitle_style=_style_state(bot.VIDEO_SUBTITLE_MODE_DUB),
        )
    )

    assert result[0] == b"final-mp4"
    assert debug["dub_known_good_path_active"] is True
    assert debug["dub_restored_from_commit"] == "a958de4"
    assert calls[1]["keep_original_audio"] is False
    assert "original_audio_volume_percent" not in calls[1]


def test_m6af_dub_only_creates_dub_audio():
    async def render_func(*args, **kwargs):
        return b"final-mp4", "ok"

    result, debug = asyncio.run(
        bot.subdub_render_with_known_good_dub_fallback(
            render_func,
            (b"source-video",),
            {"dubbed_audio": b"dub-audio", "require_audio": True},
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            subtitle_style={},
        )
    )

    assert result[0] == b"final-mp4"
    assert debug["dub_known_good_baseline_commit"] == "1dc772c"


def test_m6af_dub_only_muxes_mp4():
    async def render_func(*args, **kwargs):
        return b"final-mp4", "ffmpeg_video_render_basic:validated"

    result, _debug = asyncio.run(
        bot.subdub_render_with_known_good_dub_fallback(
            render_func,
            (b"source-video",),
            {"dubbed_audio": b"dub-audio", "require_audio": True},
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            subtitle_style={},
        )
    )

    assert result[0].startswith(b"final")


def test_m6af_dub_only_sends_mp4():
    message = _Message()
    sent = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            message,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            audio_bytes=b"dub-audio",
            video_bytes=b"mp4-bytes",
            include_subtitle_outputs=False,
        )
    )

    assert sent["final_mp4_delivered"] is True
    assert sent["video"] == 1
    assert message.audios == []


def test_m6af_dub_only_status_100():
    key = "m6af-dub-delivered"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=19670, chat_id=19670, mode=bot.VIDEO_SUBTITLE_MODE_DUB)

    ok = bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="901",
        terminal_artifact_type="video",
        video_delivery_message_id="901",
    )
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert ok is True
    assert stored["progress_percent"] == 100
    assert stored["terminal_state"] == "delivered"


def test_m6af_dub_only_no_late_fail_after_success():
    key = "m6af-dub-late"
    message = _Message()
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=19671, chat_id=19671, mode=bot.VIDEO_SUBTITLE_MODE_DUB)
    bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="901",
        terminal_artifact_type="video",
        video_delivery_message_id="901",
    )

    result = asyncio.run(bot.send_subdub_fail_once(message, key, mode=bot.VIDEO_SUBTITLE_MODE_DUB, reason="late"))

    assert result.get("suppressed") is True
    assert message.texts == []


def test_m6af_subtitle_dub_uses_restored_dub_path():
    calls = []

    async def render_func(*args, **kwargs):
        calls.append(dict(kwargs))
        if "original_audio_volume_percent" in kwargs or "dubbed_voice_volume_percent" in kwargs:
            return b"", "volume_mix_failed"
        return b"final-mp4", "ok"

    result, debug = asyncio.run(
        bot.subdub_render_with_known_good_dub_fallback(
            render_func,
            (b"source-video",),
            {
                "dubbed_audio": b"dub-audio",
                "subtitle_bytes": VALID_SRT.encode("utf-8"),
                "original_audio_volume_percent": 80,
                "dubbed_voice_volume_percent": 200,
                "require_audio": True,
            },
            mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            subtitle_style=_style_state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB),
        )
    )

    assert result[0] == b"final-mp4"
    assert debug["dub_known_good_path_active"] is True


def test_m6af_known_good_retry_keeps_audio_and_subtitle_bytes():
    calls = []

    async def render_func(*args, **kwargs):
        calls.append(dict(kwargs))
        if "original_audio_volume_percent" in kwargs or "dubbed_voice_volume_percent" in kwargs:
            return b"", "volume_mix_failed"
        if kwargs.get("dubbed_audio") != b"dub-audio":
            return b"", "missing_dub_audio"
        if kwargs.get("subtitle_bytes") != VALID_SRT.encode("utf-8"):
            return b"", "missing_subtitle_bytes"
        return b"final-mp4", "ok"

    result, debug = asyncio.run(
        bot.subdub_render_with_known_good_dub_fallback(
            render_func,
            (b"source-video",),
            {
                "dubbed_audio": b"dub-audio",
                "subtitle_bytes": VALID_SRT.encode("utf-8"),
                "original_audio_volume_percent": 80,
                "dubbed_voice_volume_percent": 200,
                "require_audio": True,
            },
            mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            subtitle_style=_style_state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB),
        )
    )

    assert result[0] == b"final-mp4"
    assert debug["dub_known_good_path_active"] is True
    assert calls[1]["dubbed_audio"] == b"dub-audio"
    assert calls[1]["subtitle_bytes"] == VALID_SRT.encode("utf-8")


def test_m6af_subtitle_dub_sends_final_mp4():
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
        )
    )

    assert sent["final_mp4_delivered"] is True
    assert sent["video"] == 1


def test_m6af_subtitle_dub_preserves_bottom_subtitle_style():
    style = bot.subdub_normalize_style(_style_state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB))

    assert style["subtitle_alignment"] == "bottom_center"
    assert style["subtitle_margin_v_after"] <= 8
    assert style["subtitle_font_size_after"] <= 46


def test_m6af_subtitle_dub_no_auto_srt_after_mp4():
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
        )
    )

    assert sent["srt_auto_send_suppressed"] is True
    assert sent["documents"] == 0
    assert message.documents == []


def test_m6af_subtitle_dub_no_false_file_too_large_after_video_received(tmp_path):
    source_path = tmp_path / "input.mp4"
    source_path.write_bytes(b"local-video-bytes")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = asyncio.run(
        bot.video_dubbing_save_input_for_pipeline(
            SimpleNamespace(bot=SimpleNamespace()),
            {
                "input_file_path": str(source_path),
                "source_mime_type": "video/mp4",
                "_pipeline_is_admin": True,
            },
            str(workspace),
        )
    )

    assert result["ok"] is True
    assert result["telegram_download_method"] == "local_path_override"
    assert result["input_save_blocker"] == ""
    assert result["file_saved"] is True


def test_m6af_status_full_green_after_subtitle_mp4():
    key = "m6af-subtitle-status"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=19672, chat_id=19672, mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE)

    bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="901",
        terminal_artifact_type="video",
        video_delivery_message_id="901",
    )
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert stored["progress_percent"] == 100
    assert "delivered" == stored["terminal_state"]


def test_m6af_status_full_green_after_dub_mp4():
    key = "m6af-dub-status"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=19673, chat_id=19673, mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB)

    bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="901",
        terminal_artifact_type="video",
        video_delivery_message_id="901",
    )
    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]

    assert stored["progress_percent"] == 100
    assert stored["terminal_public_outcome_type"] == "success"


def test_m6af_receipt_once_no_duplicate():
    key = "m6af-receipt-once"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    bot.acquire_subtitle_dub_pipeline_job(key, user_id=19674, chat_id=19674, mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE)

    first = bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="901",
        terminal_artifact_type="video",
        video_delivery_message_id="901",
    )
    second = bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="902",
        terminal_artifact_type="video",
        video_delivery_message_id="902",
    )

    assert first is True
    assert second is False


def test_m6af_no_public_internal_terms():
    text = bot.video_dubbing_receipt_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "target_language": "English"},
        {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "video_delivery_message_id": "901"},
        "vi",
    ).lower()

    for term in ("provider", "api", "ffmpeg", "handler", "callback", "traceback"):
        assert term not in text


def test_m6af_no_music_runtime_changes():
    changed = _changed_files()

    assert not any(path.startswith("providers/suno") or "music" in path.lower() for path in changed if path != __file__.replace("\\", "/"))


def test_m6af_no_product_video_runtime_changes():
    changed = _changed_files()
    forbidden = [path for path in changed if path.startswith("services/video_") or path.startswith("providers/video_")]

    assert forbidden == []


def test_m6af_no_payos_pricing_db_webhook_changes():
    changed = _changed_files()
    forbidden = []
    for path in changed:
        lower = path.lower()
        if any(token in lower for token in ("payos", "pricing", "finance", "migration", "webhook")):
            forbidden.append(path)

    assert forbidden == []
