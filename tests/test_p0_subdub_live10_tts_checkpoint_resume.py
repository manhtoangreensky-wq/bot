import asyncio
from pathlib import Path

import bot


def _cue(index: int, start_ms: int, end_ms: int, text: str) -> dict:
    return {
        "source_index": index,
        "source_start_ms": start_ms,
        "source_end_ms": end_ms,
        "source_text": text,
        "translated_text": text,
        "source_language": "zh",
        "target_language": "vi",
    }


def _setup_persisted_job(monkeypatch, tmp_path: Path) -> dict:
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "live10.db"))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(tmp_path / "backups"))
    bot.init_db()
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()
    acquired, job = bot.acquire_subtitle_dub_pipeline_job(
        "live10-resume",
        user_id=91010,
        chat_id=91010,
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
    )
    assert acquired is True
    return job


class _Message:
    def __init__(self, text: str):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return self


class _User:
    id = 91010


class _Update:
    def __init__(self, text: str):
        self.message = _Message(text)
        self.effective_user = _User()


def test_live10_dub_volume_numbers_are_owned_only_by_subdub(monkeypatch):
    state = {
        "step": "subdub_dub_volume_input",
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "audio_mix_return_step": "confirm",
    }
    mutations = []

    monkeypatch.setattr(bot, "get_video_dubbing_pending", lambda _uid: dict(state))
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "subdub_audio_layer_text", lambda *_args: "dub-volume")
    monkeypatch.setattr(bot, "subdub_audio_layer_keyboard", lambda *_args: "keyboard")

    def fake_set(_uid, step, **fields):
        mutations.append((step, dict(fields)))
        return {**state, "step": step, **fields}

    monkeypatch.setattr(bot, "set_video_dubbing_pending", fake_set)

    for value in (0, 100, 150, 200):
        update = _Update(str(value))
        handled = asyncio.run(bot.handle_video_dubbing_pending_text(update, None))
        assert handled is True
        assert mutations[-1][0] == "audio_dub"
        assert mutations[-1][1]["dubbed_voice_volume_percent"] == value
        assert mutations[-1][1]["volume_config_source"] == "user_numeric_audio_mix"

    mutation_count = len(mutations)
    update = _Update("201")
    handled = asyncio.run(bot.handle_video_dubbing_pending_text(update, None))
    assert handled is True
    assert len(mutations) == mutation_count
    assert "0 đến 200" in update.message.replies[-1][0]


def test_live10_cue_checkpoints_are_reused_without_tts_replay(monkeypatch, tmp_path):
    tts_calls = []

    async def fake_tts(text, *_args, **_kwargs):
        tts_calls.append(text)
        return "fixture_tts", f"audio:{text}".encode(), "fixture"

    async def fake_duration(_audio):
        return 0.75

    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", fake_tts)
    monkeypatch.setattr(bot, "video_dubbing_audio_duration_seconds", fake_duration)
    cues = [_cue(1, 0, 1000, "Xin chao"), _cue(2, 1000, 2000, "Tam biet")]
    checkpoint_dir = tmp_path / "tts"

    first = asyncio.run(
        bot.synthesize_canonical_dub_segment_chunks(
            cues,
            voice_id="female-vi",
            checkpoint_dir=str(checkpoint_dir),
            cue_timeout_seconds=15,
            max_attempts=2,
        )
    )

    assert tts_calls == ["Xin chao", "Tam biet"]
    assert first["completed_tts_cues"] == 2
    assert len(first["tts_cue_checkpoints"]) == 2
    assert all(Path(item["artifact_path"]).is_file() for item in first["tts_cue_checkpoints"])

    async def tts_must_not_run(*_args, **_kwargs):
        raise AssertionError("completed TTS cue was replayed")

    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", tts_must_not_run)
    second = asyncio.run(
        bot.synthesize_canonical_dub_segment_chunks(
            cues,
            voice_id="female-vi",
            checkpoint_dir=str(checkpoint_dir),
            checkpoint_entries=first["tts_cue_checkpoints"],
            cue_timeout_seconds=15,
            max_attempts=2,
        )
    )

    assert second["completed_tts_cues"] == 2
    assert all(chunk["checkpoint_reused"] is True for chunk in second["chunks"])


def test_live10_restart_at_65_resumes_only_missing_cue_then_builds_mp4(monkeypatch, tmp_path):
    job = _setup_persisted_job(monkeypatch, tmp_path)
    workspace = tmp_path / "workspace"
    checkpoint_dir = workspace / "tts_checkpoints"
    checkpoint_dir.mkdir(parents=True)
    source_path = workspace / "source.mp4"
    source_path.write_bytes(b"source-video")
    cue_one_audio = checkpoint_dir / "cue_0001.mp3"
    cue_one_audio.write_bytes(b"completed-cue-one")
    cues = [_cue(1, 0, 1000, "Mot"), _cue(2, 1000, 2000, "Hai")]
    canonical = bot.subdub_canonical_cues.canonicalize_segments(
        cues,
        extraction_source="fixture",
        source_language="zh",
        target_language="vi",
    )
    first_cue = canonical[0]
    checkpoint = {
        "index": 1,
        "source_index": 1,
        "cue_id": first_cue["cue_id"],
        "artifact_path": str(cue_one_audio),
        "artifact_hash": bot.hashlib.sha256(cue_one_audio.read_bytes()).hexdigest(),
        "audio_duration": 0.75,
        "attempt_count": 1,
        "provider": "fixture_tts",
        "completed": True,
    }
    bot.subdub_persist_recovery_fields(
        job,
        "fixture lost at generating voice",
        current_stage="generating_voice",
        progress_stage="generating_voice",
        progress_percent=65,
        status_registry_missing_after_restart=True,
        workspace=str(workspace),
        source=str(source_path),
        total_tts_cues=2,
        completed_tts_cues=1,
        tts_cue_checkpoints=[checkpoint],
        tts_resume_context={
            "version": 1,
            "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
            "workspace": str(workspace),
            "source_path": str(source_path),
            "source_duration": 2.0,
            "source_language": "zh",
            "target_language": "vi",
            "canonical_cues": canonical,
            "voice_id": "female-vi",
            "voice_style": "female",
            "base_speed": 1.0,
            "keep_original_audio": False,
            "original_audio_mode": "mute",
            "original_audio_volume_percent": 0,
            "dubbed_voice_volume_percent": 100,
        },
    )
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()
    persisted = bot.get_engine_async_job(str(job.get("internal_job_id") or job.get("job_id")))
    tts_calls = []

    async def fake_tts(text, *_args, **_kwargs):
        tts_calls.append(text)
        return "fixture_tts", b"missing-cue-two", "fixture"

    async def fake_duration(_audio):
        return 0.75

    async def fake_timeline(chunks, total_duration=0):
        assert len(chunks) == 2
        assert total_duration == 2.0
        return b"timeline-audio", "timeline-ok"

    async def fake_normalize(_audio):
        return b"normalized-audio", "normalize-ok"

    async def fake_render(source_bytes, **kwargs):
        assert source_bytes == b"source-video"
        assert kwargs["preserve_source_duration"] is True
        assert kwargs["require_audio"] is True
        return b"final-mp4", "source_duration_preserved=2.000;output_duration=2.000"

    async def fake_validate(payload, *, require_audio=False):
        assert payload == b"final-mp4"
        assert require_audio is True
        return {"ok": True, "duration": 2.0}

    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", fake_tts)
    monkeypatch.setattr(bot, "video_dubbing_audio_duration_seconds", fake_duration)
    monkeypatch.setattr(bot, "build_canonical_dub_timeline_audio", fake_timeline)
    monkeypatch.setattr(bot, "normalize_dub_audio_bytes", fake_normalize)
    monkeypatch.setattr(bot, "video_dubbing_render_video", fake_render)
    monkeypatch.setattr(bot, "subdub_validate_video_output", fake_validate)

    recovered = asyncio.run(bot.subdub_resume_generating_voice_from_checkpoint(persisted))

    assert tts_calls == ["Hai"]
    assert recovered["current_stage"] == "delivering"
    assert recovered["progress_percent"] == 95
    assert recovered["completed_tts_cues"] == 2
    assert recovered["total_tts_cues"] == 2
    assert recovered["delivery_attempted"] is False
    assert recovered["final_mp4_valid"] is True
    assert Path(recovered["final_mp4_path"]).read_bytes() == b"final-mp4"
    assert recovered["charge_status"] == "not_charged"


def test_live10_missing_checkpoint_still_terminalizes_instead_of_sticking(monkeypatch, tmp_path):
    job = _setup_persisted_job(monkeypatch, tmp_path)
    bot.subdub_persist_recovery_fields(
        job,
        "fixture missing checkpoint",
        current_stage="generating_voice",
        progress_stage="generating_voice",
        progress_percent=65,
        status_registry_missing_after_restart=True,
        tts_cue_checkpoints=[],
    )
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()
    persisted = bot.get_engine_async_job(str(job.get("internal_job_id") or job.get("job_id")))

    result = asyncio.run(bot.subdub_recover_persisted_job(persisted, None, source="boot"))

    assert result["terminal_state"] == "failed_no_charge"
    assert result["pipeline_blocker"] == "tts_checkpoint_unavailable_after_restart"
    assert result["charge_status"] == "not_charged"


def test_live10_same_runtime_cannot_claim_the_same_recovery_twice(monkeypatch, tmp_path):
    job = _setup_persisted_job(monkeypatch, tmp_path)

    first = bot.subdub_claim_recovery_lease(job, "tts_resume")
    second = bot.subdub_claim_recovery_lease(first, "tts_resume")

    assert first["execution_owner"] == bot.SUBDUB_RECOVERY_OWNER
    assert second == {}


def test_live10_tts_retry_is_bounded_and_records_exact_cue(monkeypatch, tmp_path):
    attempts = []

    async def failing_tts(text, *_args, **_kwargs):
        attempts.append(text)
        raise RuntimeError("fixture_provider_down")

    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", failing_tts)

    try:
        asyncio.run(
            bot.synthesize_canonical_dub_segment_chunks(
                [_cue(1, 0, 1000, "Mot")],
                voice_id="female-vi",
                checkpoint_dir=str(tmp_path / "tts"),
                cue_timeout_seconds=15,
                max_attempts=2,
            )
        )
    except RuntimeError as exc:
        blocker = str(exc)
    else:
        raise AssertionError("bounded TTS failure did not terminalize")

    assert attempts == ["Mot", "Mot"]
    assert blocker.startswith("canonical_tts_cue_failed:")
    assert blocker.endswith(":RuntimeError:attempt=2")


def test_live10_real_mux_stage_name_resumes_from_complete_checkpoint(monkeypatch, tmp_path):
    job = _setup_persisted_job(monkeypatch, tmp_path)
    workspace = tmp_path / "workspace"
    checkpoint_dir = workspace / "tts_checkpoints"
    checkpoint_dir.mkdir(parents=True)
    source_path = workspace / "source.mp4"
    source_path.write_bytes(b"source-video")
    audio_path = checkpoint_dir / "cue_0001.mp3"
    audio_path.write_bytes(b"completed-cue")
    canonical = bot.subdub_canonical_cues.canonicalize_segments(
        [_cue(1, 0, 1000, "Mot")],
        extraction_source="fixture",
        source_language="zh",
        target_language="vi",
    )
    checkpoint = {
        "source_index": 1,
        "cue_id": canonical[0]["cue_id"],
        "artifact_path": str(audio_path),
        "artifact_hash": bot.hashlib.sha256(audio_path.read_bytes()).hexdigest(),
        "audio_duration": 0.75,
        "attempt_count": 1,
        "provider": "fixture_tts",
        "completed": True,
    }
    bot.subdub_persist_recovery_fields(
        job,
        "fixture lost at real mux stage",
        current_stage="muxing_video",
        progress_stage="muxing_video",
        progress_percent=80,
        status_registry_missing_after_restart=True,
        workspace=str(workspace),
        source=str(source_path),
        total_tts_cues=1,
        completed_tts_cues=1,
        tts_cue_checkpoints=[checkpoint],
        tts_resume_context={
            "version": 1,
            "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
            "workspace": str(workspace),
            "source_path": str(source_path),
            "source_duration": 1.0,
            "source_language": "zh",
            "target_language": "vi",
            "canonical_cues": canonical,
            "voice_id": "female-vi",
            "voice_style": "female",
            "base_speed": 1.0,
            "keep_original_audio": False,
            "original_audio_mode": "mute",
            "original_audio_volume_percent": 0,
            "dubbed_voice_volume_percent": 100,
        },
    )
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()
    persisted = bot.get_engine_async_job(str(job.get("internal_job_id") or job.get("job_id")))

    async def tts_must_not_run(*_args, **_kwargs):
        raise AssertionError("complete checkpoint was replayed at mux recovery")

    async def fake_timeline(chunks, total_duration=0):
        assert len(chunks) == 1
        assert chunks[0]["checkpoint_reused"] is True
        return b"timeline-audio", "timeline-ok"

    async def fake_normalize(_audio):
        return b"normalized-audio", "normalize-ok"

    async def fake_render(_source_bytes, **kwargs):
        assert kwargs["preserve_source_duration"] is True
        return b"final-mp4", "source_duration_preserved=1.000;output_duration=1.000"

    async def fake_validate(payload, *, require_audio=False):
        assert payload == b"final-mp4"
        assert require_audio is True
        return {"ok": True, "duration": 1.0}

    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", tts_must_not_run)
    monkeypatch.setattr(bot, "build_canonical_dub_timeline_audio", fake_timeline)
    monkeypatch.setattr(bot, "normalize_dub_audio_bytes", fake_normalize)
    monkeypatch.setattr(bot, "video_dubbing_render_video", fake_render)
    monkeypatch.setattr(bot, "subdub_validate_video_output", fake_validate)

    recovered = asyncio.run(bot.subdub_recover_persisted_job(persisted, None, source="boot"))

    assert recovered["current_stage"] == "delivering"
    assert recovered["final_mp4_valid"] is True
    assert recovered["completed_tts_cues"] == 1
