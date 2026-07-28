import asyncio
from types import SimpleNamespace

import bot


def _patch_public_product_runtime(monkeypatch):
    prefix = bot.SUBDUB_PUBLIC_OVERRIDE_PREFIX
    overrides = {
        f"{prefix}:PUBLIC_FORCE": "true",
        f"{prefix}:PROVIDER_FREEZE": "false",
        f"{prefix}:VIDEO_SUBTITLE_PUBLIC_ENABLED": "true",
        f"{prefix}:VIDEO_TRANSLATE_SUBTITLE_PUBLIC_ENABLED": "true",
        f"{prefix}:VIDEO_DUB_PUBLIC_ENABLED": "true",
        f"{prefix}:VIDEO_SUBTITLE_PLUS_DUB_PUBLIC_ENABLED": "true",
        f"{prefix}:VIDEO_ASR_ENABLED": "true",
        f"{prefix}:VIDEO_DUB_TTS_ENABLED": "true",
    }
    monkeypatch.setattr(bot, "get_system_setting", lambda key, default="": overrides.get(str(key), default))
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "APP_BUILD_SHA", "new-runtime-sha")
    monkeypatch.setattr(bot, "PROVIDER_FREEZE", True)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE_ENABLED", False)
    monkeypatch.setattr(bot, "TRANSLATION_DUB_MAINTENANCE", False)
    monkeypatch.setattr(bot, "ASR_PROVIDER", "deepgram")
    monkeypatch.setattr(bot, "TRANSLATE_PROVIDER", "deepl")
    monkeypatch.setattr(bot, "TTS_PROVIDER", "key4u_minimax")
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "configured")
    monkeypatch.setattr(bot, "DEEPL_API_KEY", "configured")
    monkeypatch.setattr(bot, "KEY4U_ENABLED", True)
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "configured")
    monkeypatch.setattr(bot, "KEY4U_TTS_ENDPOINT", "/v1/t2a_v2")
    monkeypatch.setattr(bot, "KEY4U_TTS_MODEL", "speech-02-hd")
    monkeypatch.setattr(bot, "KEY4U_PUBLIC_ENABLED", False)
    monkeypatch.setattr(
        bot,
        "subdub_runtime_status_payload",
        lambda: {
            "ffmpeg_ready": True,
            "ffprobe_ready": True,
            "subtitle_rendering_ready": True,
            "media_preprocessing_ready": True,
        },
    )
    monkeypatch.setattr(
        bot,
        "get_asr_adapter_readiness",
        lambda public=False, audio_extract_ready=None: {
            "configured": True,
            "ready": True,
            "supports_audio": True,
            "supports_video": True,
        },
    )
    monkeypatch.setattr(
        bot,
        "get_tool_test_result",
        lambda _name: {
            "status": "PASS",
            "tested_at": "before-deploy",
            "detail": "runtime_sha=old-runtime-sha",
        },
    )
    monkeypatch.setattr(
        bot,
        "resolve_media_binary",
        lambda name: {
            "resolved_path": f"/usr/bin/{name}",
            "version_probe_ok": True,
            "source": "test",
        },
    )


def test_real_product_gate_honors_public_force_open_after_unrelated_deploy(monkeypatch, tmp_path):
    _patch_public_product_runtime(monkeypatch)
    source = tmp_path / "input.mp4"
    source.write_bytes(b"real-video-input")
    mode = bot.VIDEO_SUBTITLE_MODE_DUB
    state = {
        "active_flow": "video_dub",
        "mode": mode,
        "process_type": mode,
        "video_processing_mode": mode,
        "video_file_id": "telegram-file-id",
        "source_file_name": "input.mp4",
        "source_mime_type": "video/mp4",
        "target_language": "vi",
        "translate_requested": "0",
    }
    access = bot.video_dubbing_engine_access_decision(77, mode, state)
    assert access["allowed"] is True

    matrix = bot.video_dubbing_product_gate_matrix(
        77,
        mode,
        state,
        access=access,
        input_save={
            "ok": True,
            "file_saved": True,
            "exists": True,
            "size": source.stat().st_size,
            "path": str(source),
            "content_type": "video/mp4",
            "file_id": "telegram-file-id",
        },
    )

    assert matrix["product_config_ready"] is True, matrix
    assert matrix["gate_blockers"] == []
    assert bot.video_dubbing_product_gate_allows_pipeline(access, matrix) is True


class _FakeQuery:
    def __init__(self):
        self.edits = []

    async def edit_message_text(self, text, **_kwargs):
        self.edits.append(str(text))
        return SimpleNamespace(message_id=901)


def test_terminal_failure_updates_current_job_not_older_delivered_job(monkeypatch):
    current_key = "77|77|current-source|video_dub"
    current_job = {
        "job_key": current_key,
        "job_id": "current-job",
        "internal_job_id": "current-job",
        "user_id": 77,
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "progress_stage": "received_file",
        "progress_percent": 5,
        "public_error_sent_count": 0,
        "status_panel_terminalized": False,
    }
    old_job = {
        "job_key": "77|77|old-source|video_dub",
        "job_id": "old-job",
        "internal_job_id": "old-job",
        "user_id": 77,
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "status": "completed",
        "terminal_state": "delivered",
        "final_mp4_delivered": True,
        "delivery_succeeded": True,
        "video_delivery_message_id": "501",
    }
    jobs = {current_key: dict(current_job), old_job["job_key"]: dict(old_job)}
    persisted = []
    monkeypatch.setattr(bot, "SUBTITLE_DUB_PIPELINE_JOBS", jobs)
    monkeypatch.setattr(bot, "subtitle_dub_find_latest_dub_job_for_user_mode", lambda *_args, **_kwargs: dict(old_job))
    monkeypatch.setattr(
        bot,
        "persist_subtitle_dub_pipeline_job_snapshot",
        lambda key, job, reason="": persisted.append((str(key), dict(job), str(reason))) or True,
    )

    query = _FakeQuery()
    result = asyncio.run(
        bot.send_subdub_fail_once(
            query,
            current_key,
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            reason="provider_key_missing",
            terminalize_active=True,
        )
    )

    assert result["sent"] is True
    assert len(query.edits) == 1
    assert jobs[current_key]["terminal_state"] == "failed_no_charge"
    assert jobs[current_key]["terminal_public_outcome_type"] == "failure"
    assert jobs[current_key]["public_error_sent_count"] == 1
    assert jobs[current_key]["status_panel_terminalized"] is True
    assert jobs[current_key]["refresh_stopped_after_terminal"] is True
    assert jobs[old_job["job_key"]] == old_job
    assert persisted[-1][0] == current_key
