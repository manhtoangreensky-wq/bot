import asyncio
import inspect
from types import SimpleNamespace

import bot


PUBLIC_CODE = "E6AE42579B"
JOB_ID = "e6ae42579bf737480ecf"


class CaptureMessage:
    def __init__(self, chat_id=21021):
        self.chat_id = chat_id
        self.texts = []

    async def reply_text(self, text, **kwargs):
        self.texts.append(str(text))
        return SimpleNamespace(message_id=21022, chat_id=self.chat_id)


class CaptureQuery:
    def __init__(self):
        self.message = CaptureMessage()
        self.edits = []

    async def edit_message_text(self, text, **kwargs):
        self.edits.append(str(text))
        return SimpleNamespace(message_id=21023, chat_id=self.message.chat_id)


def _saved_input():
    return {
        "ok": True,
        "file_saved": True,
        "exists": True,
        "size": 4096,
        "path": __file__,
        "content_type": "video/mp4",
    }


def _lane_state(mode):
    return {
        "active_flow": "subdub",
        "mode": mode,
        "process_type": mode,
        "video_processing_mode": mode,
        "source_mime_type": "video/mp4",
    }


def _terminal_job(**extra):
    job = {
        "feature": "subtitle_dub",
        "internal_job_id": JOB_ID,
        "job_id": JOB_ID,
        "public_code": PUBLIC_CODE,
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "product_type": bot.SUBDUB_PRODUCT_TYPE_DUB_ONLY,
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "lifecycle_state": "saved_input",
        "current_stage": "saved_input",
        "progress_stage": "saved_input",
        "progress_percent": 15,
        "input_save_attempted": True,
        "input_save_success": True,
        "input_save_blocker": "",
        "pipeline_blocker": "ffmpeg_missing",
        "pipeline_started": True,
        "asr_started": False,
        "translation_started": False,
        "tts_started": False,
        "mux_started": False,
        "final_mp4_exists": False,
        "delivery_attempted": False,
        "charge_status": "not_charged",
        "public_error_sent_count": 0,
        "status_panel_terminalized": True,
        "refresh_stopped_after_terminal": True,
        "updated_at": 100.0,
    }
    job.update(extra)
    return job


def test_media_binary_resolver_prefers_valid_explicit_path(monkeypatch):
    monkeypatch.setenv("FFMPEG_BINARY", "/configured/ffmpeg")
    monkeypatch.setattr(bot.shutil, "which", lambda _name: "/path/ffmpeg")
    monkeypatch.setattr(
        bot,
        "probe_media_binary_candidate",
        lambda path, name: {
            "name": name,
            "resolved_path": path,
            "executable": True,
            "version_probe_ok": path == "/configured/ffmpeg",
            "version_summary": "ffmpeg version fixture",
            "blocker": "" if path == "/configured/ffmpeg" else "version_probe_failed",
        },
    )

    status = bot.resolve_media_binary("ffmpeg")

    assert status["resolved_path"] == "/configured/ffmpeg"
    assert status["source"] == "configured"
    assert status["version_probe_ok"] is True


def test_invalid_configured_binary_does_not_hide_valid_path(monkeypatch):
    monkeypatch.setenv("FFMPEG_BINARY", r"D:\missing\ffmpeg.exe")
    monkeypatch.setattr(bot.shutil, "which", lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None)

    def probe(path, name):
        ok = path == "/usr/bin/ffmpeg"
        return {
            "name": name,
            "resolved_path": path if ok else "",
            "executable": ok,
            "version_probe_ok": ok,
            "version_summary": "ffmpeg version fixture" if ok else "",
            "blocker": "" if ok else "binary_not_executable",
        }

    monkeypatch.setattr(bot, "probe_media_binary_candidate", probe)

    status = bot.resolve_media_binary("ffmpeg")

    assert status["resolved_path"] == "/usr/bin/ffmpeg"
    assert status["source"] == "PATH"
    assert status["configured_path_present"] is True


def test_missing_media_binary_returns_structured_unavailable(monkeypatch):
    for key in ("FFPROBE_BINARY", "FFPROBE_PATH", "LOCAL_FFPROBE_PATH"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(bot.shutil, "which", lambda _name: None)

    status = bot.resolve_media_binary("ffprobe")

    assert status["resolved_path"] == ""
    assert status["version_probe_ok"] is False
    assert status["blocker"] == "ffprobe_missing"


def test_version_probe_failure_is_not_ready(monkeypatch):
    monkeypatch.setattr(bot.os.path, "isfile", lambda _path: True)
    monkeypatch.setattr(bot.os, "access", lambda _path, _mode: True)
    monkeypatch.setattr(
        bot.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout="", stderr="probe failed"),
    )

    status = bot.probe_media_binary_candidate("/usr/bin/ffmpeg", "ffmpeg")

    assert status["version_probe_ok"] is False
    assert status["blocker"] == "ffmpeg_version_probe_failed"


def test_resolver_never_uses_shell_or_runtime_download():
    source = inspect.getsource(bot.probe_media_binary_candidate) + inspect.getsource(bot.resolve_media_binary)

    assert "shell=True" not in source
    assert "curl" not in source
    assert "wget" not in source
    assert "pip install" not in source


def test_four_video_lanes_share_ffmpeg_and_ffprobe_preflight(monkeypatch):
    calls = []

    def resolve(name):
        calls.append(name)
        return {
            "name": name,
            "resolved_path": f"/usr/bin/{name}",
            "version_probe_ok": True,
            "blocker": "",
        }

    monkeypatch.setattr(bot, "resolve_media_binary", resolve)
    modes = (
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    )

    for mode in modes:
        matrix = bot.video_dubbing_product_gate_matrix(
            21021,
            mode,
            _lane_state(mode),
            access={"allowed": True, "status": "ready", "readiness": {"public_blockers": []}},
            input_save=_saved_input(),
        )
        assert matrix["media_prerequisites_ready"] is True
        assert matrix["ffmpeg_version_probe_ok"] is True
        assert matrix["ffprobe_version_probe_ok"] is True

    assert calls.count("ffmpeg") == 4
    assert calls.count("ffprobe") == 4


def test_missing_binary_blocks_before_any_provider_lane(monkeypatch):
    def resolve(name):
        return {
            "name": name,
            "resolved_path": "",
            "version_probe_ok": False,
            "blocker": f"{name}_missing",
        }

    monkeypatch.setattr(bot, "resolve_media_binary", resolve)
    for mode in (
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    ):
        matrix = bot.video_dubbing_product_gate_matrix(
            21021,
            mode,
            _lane_state(mode),
            access={"allowed": True, "status": "ready", "readiness": {"public_blockers": []}},
            input_save=_saved_input(),
        )
        assert bot.video_dubbing_product_gate_allows_pipeline({}, matrix) is False
        assert matrix["media_prerequisites_ready"] is False


def test_audio_extract_failure_is_not_misreported_as_missing_binary():
    blocker = bot.video_dubbing_pipeline_blocker(
        input_save=_saved_input(),
        gate_matrix={"product_route_allowed": True, "gate_blockers": []},
        detail="audio_extract_failed:invalid_input_stream",
        pipeline_attempted=True,
    )

    assert blocker == "audio_extract_failed"


def test_asr_progress_is_emitted_only_at_real_asr_seam(monkeypatch):
    events = []

    async def extract(*_args, **_kwargs):
        assert events == []
        return b"audio", "audio/mpeg", "fixture_extract"

    async def transcribe(*_args, **_kwargs):
        assert events == ["transcribing"]
        return {
            "ok": True,
            "provider": "fixture",
            "text": "hello world",
            "segments": [{"start": 0.0, "end": 1.0, "text": "hello world"}],
        }

    monkeypatch.setattr(bot, "video_dubbing_audio_extract_ready", lambda: True)
    monkeypatch.setattr(bot, "video_dubbing_extract_audio", extract)
    monkeypatch.setattr(bot, "asr_transcribe_audio", transcribe)

    result = asyncio.run(
        bot.transcribe_media_to_segments(
            {"bytes": b"video", "content_type": "video/mp4", "media_kind": "video", "duration_seconds": 2},
            progress_callback=lambda stage: events.append(stage),
        )
    )

    assert result["output_valid"] is True
    assert events == ["transcribing"]


def test_terminal_failure_keeps_last_truthful_progress_not_95():
    assert bot.subdub_progress_percent_for_lifecycle("saved_input", "failed_no_charge") == 15
    assert bot.subdub_progress_percent_for_lifecycle("extracting_audio", "failed_no_charge") == 25


def test_e6ae_terminal_failure_edits_panel_and_sends_once_after_terminalization():
    key = "live21-e6ae"
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = _terminal_job(job_key=key, status_panel_message_id="panel-21021")
    query = CaptureQuery()

    first = asyncio.run(
        bot.send_subdub_fail_once(
            query,
            key,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            reason="ffmpeg_missing",
            lang="vi",
        )
    )
    second = asyncio.run(
        bot.send_subdub_fail_once(
            query,
            key,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            reason="ffmpeg_missing",
            lang="vi",
        )
    )

    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert first["sent"] is True
    assert second["sent"] is False
    assert len(query.edits) == 1
    assert "chưa thể xử lý video lúc này" in query.edits[0]
    assert "ffmpeg" not in query.edits[0].lower()
    assert stored["public_error_sent_count"] == 1
    assert stored["panel_final_message_id"] == "21023"
    assert stored["charge_status"] == "not_charged"


def test_definitive_runner_failure_terminalizes_active_job_instead_of_staying_at_90():
    key = "live21-active-runner-failure"
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = {
        **_terminal_job(job_key=key),
        "status": "running",
        "terminal_state": "",
        "lifecycle_state": "validating_output",
        "current_stage": "validating_output",
        "progress_stage": "validating_output",
        "progress_percent": 90,
        "public_error_sent_count": 0,
        "terminal_public_outcome_type": "",
    }
    query = CaptureQuery()

    result = asyncio.run(
        bot.send_subdub_fail_once(
            query,
            key,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            reason="validation_failed",
            lang="vi",
            terminalize_active=True,
        )
    )

    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert result["sent"] is True
    assert stored["terminal_state"] == "failed_no_charge"
    assert stored["progress_percent"] == 90
    assert stored["public_error_sent_count"] == 1
    assert len(query.edits) == 1


def test_persisted_terminal_beats_newer_stale_memory(monkeypatch):
    key = "live21-stale-memory"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = {
        **_terminal_job(),
        "job_key": key,
        "status": "running",
        "terminal_state": "",
        "progress_stage": "transcribing",
        "progress_percent": 35,
        "updated_at": 200.0,
    }
    persisted = _terminal_job(job_key=key, updated_at=100.0)
    monkeypatch.setattr(bot, "get_engine_async_job", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(bot, "list_engine_async_jobs", lambda *_args, **_kwargs: [persisted])
    monkeypatch.setattr(bot, "subdub_engine_async_persisted_scan", lambda limit=240: [persisted])

    found = bot.subdub_progress_job_for_user(PUBLIC_CODE, 0)

    assert found["terminal_state"] == "failed_no_charge"
    assert found["progress_percent"] == 15
    assert found["lookup_store_hit"] in {"engine_async_feature_index", "engine_async_persisted_scan"}


def test_progress_debug_marks_direct_persisted_recovery(monkeypatch):
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    persisted = _terminal_job()
    monkeypatch.setattr(bot, "get_engine_async_job", lambda *_args, **_kwargs: persisted)
    monkeypatch.setattr(bot, "list_engine_async_jobs", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(bot, "subdub_engine_async_persisted_scan", lambda limit=240: [])

    text = bot.product_progress_debug_text(PUBLIC_CODE)

    assert "Terminal: <code>failed_no_charge</code>" in text
    assert "Percent: <code>15%</code>" in text
    assert "recovered_from_persisted_subdub_job: <code>yes</code>" in text


def test_root_terminal_fields_override_stale_nested_debug_payload():
    merged = bot.subdub_merge_debug_job(
        {
            **_terminal_job(),
            "debug_job": {
                "status": "running",
                "terminal_state": "",
                "progress_stage": "transcribing",
                "progress_percent": 35,
            },
        }
    )

    assert merged["status"] == "failed_no_charge"
    assert merged["terminal_state"] == "failed_no_charge"
    assert merged["progress_percent"] == 15


def test_31_60_120_seconds_are_not_rejected_by_duration_alone():
    for duration in (31, 60, 120):
        gate = bot.subdub_duration_gate_payload(
            {"duration": duration, "size": 1024},
            {"video_duration": duration},
        )
        assert gate["duration_gate_result"] != "fail_over_limit"
        assert gate["duration_limit_blocker"] == ""
        assert gate["input_size_bytes"] == 1024


def test_chunk_plan_has_absolute_timeline_fields_and_balanced_tail():
    plan = bot.subdub_long_video_chunk_plan(31)
    metadata = plan["chunk_metadata"]

    assert plan["chunking_enabled"] is True
    assert [item["duration_ms"] for item in metadata] == [16000, 15000]
    assert metadata[0]["source_start_ms"] == 0
    assert metadata[1]["source_end_ms"] == 31000
    assert all("overlap_left_ms" in item and "overlap_right_ms" in item for item in metadata)


def test_subdub_runtime_status_is_admin_safe(monkeypatch):
    monkeypatch.setattr(
        bot,
        "resolve_media_binary",
        lambda name: {
            "name": name,
            "configured": True,
            "configured_path_present": True,
            "resolved_path": f"/usr/bin/{name}",
            "executable": True,
            "version_probe_ok": True,
            "version_summary": f"{name} version fixture",
            "blocker": "",
        },
    )

    payload = bot.subdub_runtime_status_payload()
    text = bot.subdub_runtime_status_text(payload)

    assert payload["media_preprocessing_ready"] is True
    assert "FFmpeg version probe: <code>PASS</code>" in text
    assert "FFprobe version probe: <code>PASS</code>" in text
    assert "TELEGRAM_TOKEN" not in text
    assert "PATH=" not in text


def test_subdub_scope_has_no_shortest_or_shell_true():
    source = "\n".join(
        inspect.getsource(item)
        for item in (
            bot.video_dubbing_extract_audio,
            bot.build_dub_timeline_audio,
            bot.video_dubbing_render_video,
            bot.run_subdub_ffmpeg_command,
        )
    )

    assert "-shortest" not in source
    assert "shell=True" not in source
