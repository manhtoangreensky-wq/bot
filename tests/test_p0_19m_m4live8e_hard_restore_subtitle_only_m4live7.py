import asyncio
from pathlib import Path

import bot


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    markers = (f"def {name}(", f"async def {name}(")
    starts = [BOT_SOURCE.find(marker) for marker in markers]
    starts = [start for start in starts if start >= 0]
    assert starts, f"{name} not found"
    start = min(starts)
    next_def = BOT_SOURCE.find("\ndef ", start + 1)
    next_async = BOT_SOURCE.find("\nasync def ", start + 1)
    candidates = [item for item in (next_def, next_async) if item >= 0]
    end = min(candidates) if candidates else len(BOT_SOURCE)
    return BOT_SOURCE[start:end]


class _SentMessage:
    message_id = 8842


class _Message:
    def __init__(self):
        self.texts = []

    async def reply_text(self, text, **kwargs):
        self.texts.append((text, kwargs))
        return _SentMessage()


def test_m4live8e_source_sha_and_failure_copy_source_identified():
    assert bot.SUBDUB_SUBTITLE_ONLY_M4LIVE7_SOURCE_SHA == "0e06469c9c13d4998886dd8f5115c019ed65f24d"
    assert "TOAN AAS chưa dịch được phụ đề lúc này" in bot.video_dubbing_flow_failure_text(
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "vi",
    )

    core = _function_source("_execute_video_dubbing_pipeline_core")
    debug_payload = _function_source("subtitle_dub_debug_job_payload")
    assert "public_failure_copy_source" in core
    assert "subtitle_translate_fail_reason" in core
    assert "public_failure_copy_source" in debug_payload


def test_m4live8e_subtitle_only_duration_fields_match_m4live7_no_chunking():
    gate = bot.subdub_duration_gate_payload({"duration": 60}, {}, is_admin=False)
    assert gate["is_long_media"] is True
    assert "chunking_enabled" in gate

    restored = bot.subdub_m4live7_subtitle_only_duration_fields(gate)
    assert restored["duration_gate_result"] == gate["duration_gate_result"]
    assert restored["is_long_media"] is True
    assert restored["long_media_allowed"] == gate["long_media_allowed"]
    assert restored["chunking_enabled"] is False
    assert restored["chunk_count"] == 0
    assert restored["chunk_ranges"] == []
    assert restored["concat_required"] is False


def test_m4live8e_core_applies_m4live7_duration_only_to_subtitle_translate():
    core = _function_source("_execute_video_dubbing_pipeline_core")
    assert "if mode == VIDEO_SUBTITLE_MODE_TRANSLATE:" in core
    assert "duration_gate = subdub_m4live7_subtitle_only_duration_fields(duration_gate)" in core

    callback = _function_source("handle_video_dubbing_callback")
    assert "mode != VIDEO_SUBTITLE_MODE_TRANSLATE and latest_failure_job" in callback


def test_m4live8e_send_fail_uses_m4live7_public_failure_for_subtitle_only():
    key = "p019m8e-subtitle-active"
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = {
        "job_id": key,
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "status": "processing",
        "progress_stage": "translating_subtitle",
        "progress_percent": 65,
    }
    msg = _Message()

    result = asyncio.run(
        bot.send_subdub_fail_once(
            msg,
            key,
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            reason="SUBTITLE_PREPARE_FAILED",
            lang="vi",
        )
    )

    assert result["sent"] is True
    assert result["suppressed"] is False
    assert msg.texts
    assert "TOAN AAS chưa dịch được phụ đề lúc này" in msg.texts[0][0]
    job = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert job["public_error_sent"] is True
    assert job["terminal_public_outcome_type"] == "failure"


def test_m4live8e_dub_combo_suppress_behavior_left_intact():
    key = "p019m8e-dub-active"
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = {
        "job_id": key,
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "status": "processing",
        "progress_stage": "generating_voice",
        "progress_percent": 65,
    }
    msg = _Message()

    result = asyncio.run(
        bot.send_subdub_fail_once(
            msg,
            key,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            reason="late_generic",
            lang="vi",
        )
    )

    assert result["sent"] is False
    assert result["suppressed"] is True
    assert msg.texts == []
    assert bot.SUBTITLE_DUB_PIPELINE_JOBS[key]["generic_fail_suppressed_while_active_or_delivered"] is True


def test_m4live8e_subtitle_ass_runtime_stays_m4live7_chunked():
    source = _function_source("subdub_generate_ass_from_srt")
    assert "subdub_ass_text_chunks" in source
    assert "total_weight" in source
    assert "chunk_start = block_start + ((block_end - block_start)" in source
    assert "subtitle_timing_preserved: yes" not in source
    assert "subtitle_text_length_duration_split: no" not in source


def test_m4live8e_no_forbidden_modules_touched_by_restore_helpers():
    touched = "\n".join(
        [
            _function_source("subdub_m4live7_subtitle_only_duration_fields"),
            _function_source("send_subdub_fail_once"),
            _function_source("_execute_video_dubbing_pipeline_core"),
        ]
    )
    assert "music_song" not in touched.lower()
    assert "payos" not in touched.lower()
    assert "wallet" not in touched.lower()
    assert "product_video" not in touched.lower()
