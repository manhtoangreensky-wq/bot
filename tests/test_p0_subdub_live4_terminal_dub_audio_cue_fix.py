import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace

import bot


def _stale_dub_state() -> dict:
    return {
        "source_mime_type": "video/mp4",
        "video_file_id": "video-1",
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "process_type": bot.VIDEO_SUBTITLE_MODE_DUB,
        "active_flow": "subtitle_translate",
        "product": "subtitle_translation",
        "product_type": "subtitle_only",
        "output_type": "burn",
    }


def test_callback_and_pipeline_share_normalized_runtime_job_key():
    state, job_key = bot.subdub_runtime_pipeline_identity(11, 22, _stale_dub_state())

    assert state["active_flow"] == "dub_audio"
    assert state["product_type"] == "dub_only"
    assert state["output_type"] == "video"
    assert job_key == bot.subtitle_dub_pipeline_job_key(11, 22, state)
    assert job_key.endswith("|dub_audio")

    callback_source = inspect.getsource(bot.handle_video_dubbing_callback)
    assert 'result.get("pipeline_job_key")' in callback_source


def test_every_public_video_lane_has_one_stable_runtime_identity():
    cases = (
        (bot.VIDEO_SUBTITLE_MODE_CREATE, "auto_subtitle"),
        (bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "subtitle_translate"),
        (bot.VIDEO_SUBTITLE_MODE_DUB, "dub_audio"),
        (bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "subtitle_plus_dub"),
    )
    for mode, expected_flow in cases:
        state = {
            "source_mime_type": "video/mp4",
            "video_file_id": f"video-{mode}",
            "video_processing_mode": mode,
            "mode": mode,
            "process_type": mode,
            "active_flow": "subtitle_plus_dub" if mode == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB else "stale_flow",
            "product": "stale_product",
            "product_type": "stale_type",
            "output_type": "stale_output",
        }
        normalized, callback_key = bot.subdub_runtime_pipeline_identity(31, 41, state)
        pipeline_state, pipeline_key = bot.subdub_runtime_pipeline_identity(31, 41, state)

        assert normalized["active_flow"] == expected_flow
        assert pipeline_state == normalized
        assert pipeline_key == callback_key


def test_execute_pipeline_returns_actual_runtime_job_key(monkeypatch, tmp_path):
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()

    async def fake_progress(*_args, **_kwargs):
        return None

    async def fake_core(_query, _context, pipeline_state, _lang, **_kwargs):
        return {
            "ok": False,
            "status": "FIXTURE_STOP",
            "state": dict(pipeline_state),
            "workspace_artifacts": {},
            "debug_job": {},
        }

    monkeypatch.setattr(bot, "_prune_subtitle_dub_pipeline_jobs", lambda: None)
    monkeypatch.setattr(bot, "persist_subtitle_dub_pipeline_job_snapshot", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "create_subtitle_dub_pipeline_workspace", lambda _job_id: str(tmp_path))
    monkeypatch.setattr(bot, "write_subtitle_dub_pipeline_manifest", lambda *_args, **_kwargs: str(tmp_path / "manifest.json"))
    monkeypatch.setattr(bot, "subdub_send_progress_update", fake_progress)
    monkeypatch.setattr(bot, "_execute_video_dubbing_pipeline_core", fake_core)

    query = SimpleNamespace(
        from_user=SimpleNamespace(id=11),
        message=SimpleNamespace(chat_id=22),
    )
    result = asyncio.run(
        bot.execute_video_dubbing_pipeline(query, SimpleNamespace(), _stale_dub_state())
    )
    _normalized, expected_key = bot.subdub_runtime_pipeline_identity(11, 22, _stale_dub_state())

    assert result["pipeline_job_key"] == expected_key
    assert expected_key in bot.SUBTITLE_DUB_PIPELINE_JOBS
    assert not any(key.endswith("|subtitle_translate") for key in bot.SUBTITLE_DUB_PIPELINE_JOBS)


def test_timeline_mixer_keeps_each_non_overlapping_cue_at_full_level(monkeypatch):
    captured = {}

    async def fake_run(command, timeout=0):
        captured["command"] = list(command)
        captured["timeout"] = timeout
        Path(command[-1]).write_bytes(b"timeline-audio")
        return True, "fixture"

    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot, "run_subdub_ffmpeg_command", fake_run)
    chunks = [
        {"index": 1, "start": 0.0, "end": 1.0, "audio_duration": 0.8, "audio_bytes": b"one"},
        {"index": 2, "start": 1.2, "end": 2.2, "audio_duration": 0.8, "audio_bytes": b"two"},
        {"index": 3, "start": 2.4, "end": 3.4, "audio_duration": 0.8, "audio_bytes": b"three"},
    ]

    audio, detail = asyncio.run(bot.build_dub_timeline_audio(chunks, 3.5))

    assert audio == b"timeline-audio"
    assert detail == "ffmpeg_timeline_audio"
    filters = captured["command"][captured["command"].index("-filter_complex") + 1]
    assert "amix=inputs=3:duration=longest:dropout_transition=0:normalize=0" in filters


def test_translated_cues_keep_exact_source_index_start_and_end(monkeypatch):
    async def fake_translate(text, _target_language, **_kwargs):
        return {"text": f"Bản dịch rất dài cần xuống dòng: {text}", "provider": "fixture"}

    monkeypatch.setattr(bot, "translate_subtitle_text", fake_translate)
    source = [
        {"index": 4, "start": 0.125, "end": 1.375, "text": "第一句"},
        {"index": 9, "start": 2.750, "end": 4.125, "text": "第二句"},
        {"index": 15, "start": 7.875, "end": 9.500, "text": "第三句"},
    ]

    result = asyncio.run(bot.translate_subtitle_segments(source, "Tiếng Việt"))
    translated = result["segments"]

    assert result["ok"] is True
    assert len(translated) == len(source)
    assert [item["index"] for item in translated] == [item["index"] for item in source]
    assert [item["start"] for item in translated] == [item["start"] for item in source]
    assert [item["end"] for item in translated] == [item["end"] for item in source]
    assert result["subtitle_timing_source"] == "original_cues"
