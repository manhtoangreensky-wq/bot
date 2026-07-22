import asyncio
from pathlib import Path
from types import SimpleNamespace

import bot
import pytest


class CaptureBot:
    def __init__(self):
        self.video_sends = []
        self.document_sends = []
        self.message_sends = []
        self.edits = []

    async def send_video(self, **kwargs):
        self.video_sends.append(dict(kwargs))
        return SimpleNamespace(message_id=f"video-{len(self.video_sends)}")

    async def send_document(self, **kwargs):
        self.document_sends.append(dict(kwargs))
        return SimpleNamespace(message_id=f"document-{len(self.document_sends)}")

    async def send_message(self, **kwargs):
        self.message_sends.append(dict(kwargs))
        return SimpleNamespace(message_id=f"receipt-{len(self.message_sends)}")

    async def edit_message_text(self, **kwargs):
        self.edits.append(dict(kwargs))
        return SimpleNamespace(
            message_id=kwargs.get("message_id"),
            chat_id=kwargs.get("chat_id"),
        )


def _setup(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "live9.db"))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(tmp_path / "backups"))
    bot.init_db()
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()


def _make_job(mode=bot.VIDEO_SUBTITLE_MODE_DUB):
    acquired, job = bot.acquire_subtitle_dub_pipeline_job(
        f"live9-{mode}",
        user_id=7070,
        chat_id=7070,
        mode=mode,
        status_panel_message_id="8080",
        status_panel_chat_id="7070",
    )
    assert acquired is True
    return job


def _persisted(job):
    return bot.get_engine_async_job(
        str(job.get("internal_job_id") or job.get("job_id") or "")
    )


def test_live9_persisted_snapshot_survives_ram_registry_loss(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_job()
    updated = bot.subdub_persist_recovery_fields(
        job,
        "test persisted generating voice checkpoint",
        current_stage="generating_voice",
        progress_stage="generating_voice",
        progress_percent=65,
        status_registry_missing_after_restart=True,
        total_tts_cues=4,
        completed_tts_cues=2,
    )
    assert updated["progress_percent"] == 65

    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()
    recovered = bot.subdub_hydrate_registry_from_persisted(_persisted(job))

    assert recovered["current_stage"] == "generating_voice"
    assert recovered["progress_percent"] == 65
    assert recovered["total_tts_cues"] == 4
    assert recovered["completed_tts_cues"] == 2
    assert recovered["status_registry_missing_after_restart"] is True


def test_live9_valid_mp4_is_delivered_once_after_restart_and_receipt_once(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    artifact = Path(tmp_path) / "subdub-final.mp4"
    artifact.write_bytes(b"fixture-mp4-with-audio")
    job = _make_job()
    bot.subdub_persist_recovery_fields(
        job,
        "test valid artifact awaiting delivery",
        artifact_path=str(artifact),
        final_mp4_path=str(artifact),
        artifact_duration=30.0,
        output_duration=30.0,
        current_stage="validating",
        progress_stage="validating",
        progress_percent=95,
        delivery_attempted=False,
        status_registry_missing_after_restart=True,
    )
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()

    async def validate(_payload, *, require_audio=False):
        assert require_audio is True
        return {"ok": True, "duration": 30.0}

    monkeypatch.setattr(bot, "subdub_validate_video_output", validate)
    capture = CaptureBot()
    persisted = _persisted(job)

    first = asyncio.run(
        bot.subdub_recover_persisted_job(
            persisted,
            capture,
            lang="vi",
            source="status_refresh",
        )
    )
    assert first["terminal_state"] == "delivered", {
        key: first.get(key)
        for key in (
            "terminal_state",
            "status",
            "current_stage",
            "output_sent",
            "video_delivery_message_id",
            "status_panel_message_id",
            "status_panel_chat_id",
            "status_panel_terminal_edit_succeeded",
            "status_panel_terminal_edit_error",
            "panel_finalized",
            "panel_final_percent",
            "receipt_sent_once",
            "recovery_result",
        )
    }
    assert first["progress_percent"] == 100
    assert first["video_delivery_message_id"] == "video-1"
    assert len(capture.video_sends) == 1
    assert len(capture.message_sends) == 1
    assert len(capture.edits) == 1

    second = asyncio.run(
        bot.subdub_recover_persisted_job(
            _persisted(job),
            capture,
            lang="vi",
            source="watchdog",
        )
    )
    assert second["terminal_state"] == "delivered"
    assert len(capture.video_sends) == 1
    assert len(capture.document_sends) == 0
    assert len(capture.message_sends) == 1


def test_live9_video_artifact_message_id_blocks_recovery_resend(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    artifact = Path(tmp_path) / "already-delivered.mp4"
    artifact.write_bytes(b"fixture-mp4-with-audio")
    job = _make_job()
    bot.subdub_persist_recovery_fields(
        job,
        "test delivered artifact id survives restart",
        artifact_path=str(artifact),
        final_mp4_path=str(artifact),
        artifact_duration=30.0,
        output_duration=30.0,
        terminal_artifact_type="video",
        final_mp4_delivered=True,
        telegram_artifact_message_id="video-existing",
        current_stage="delivering",
        progress_stage="delivering",
        progress_percent=95,
        delivery_attempted=True,
        status_registry_missing_after_restart=True,
    )
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()
    capture = CaptureBot()

    result = asyncio.run(
        bot.subdub_recover_persisted_job(
            _persisted(job),
            capture,
            lang="vi",
            source="status_refresh",
        )
    )

    assert result["terminal_state"] == "delivered"
    assert result["video_delivery_message_id"] == "video-existing"
    assert len(capture.video_sends) == 0
    assert len(capture.document_sends) == 0
    assert len(capture.message_sends) <= 1


def test_live9_missing_tts_checkpoint_terminalizes_with_exact_blocker(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_job()
    bot.subdub_persist_recovery_fields(
        job,
        "test lost tts worker",
        current_stage="generating_voice",
        progress_stage="generating_voice",
        progress_percent=65,
        stage_started_at=0,
        last_heartbeat_at=0,
        status_registry_missing_after_restart=True,
        total_tts_cues=5,
        completed_tts_cues=0,
        tts_cue_checkpoints=[],
    )
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()

    result = asyncio.run(
        bot.subdub_recover_persisted_job(
            _persisted(job),
            None,
            lang="vi",
            source="boot",
        )
    )

    assert result["terminal_state"] == "failed_no_charge"
    assert result["status"] == "failed_no_charge"
    assert result["pipeline_blocker"] == "tts_checkpoint_unavailable_after_restart"
    assert result["blocker"] == "tts_checkpoint_unavailable_after_restart"
    assert result["charge_status"] == "not_charged"
    assert result["recovery_result"] == "tts_resume_not_possible_no_checkpoint"


def test_live9_delivery_attempt_without_message_id_is_never_retried(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    artifact = Path(tmp_path) / "uncertain-delivery.mp4"
    artifact.write_bytes(b"fixture-mp4")
    job = _make_job()
    bot.subdub_persist_recovery_fields(
        job,
        "test uncertain delivery",
        artifact_path=str(artifact),
        current_stage="delivering",
        progress_stage="delivering",
        progress_percent=99,
        delivery_attempted=True,
        delivery_message_id="",
    )
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()
    capture = CaptureBot()

    result = asyncio.run(
        bot.subdub_recover_persisted_job(
            _persisted(job),
            capture,
            lang="vi",
            source="status_refresh",
        )
    )

    assert result["terminal_state"] == "failed_no_charge"
    assert result["pipeline_blocker"] == "delivery_outcome_uncertain_after_restart"
    assert result["recovery_result"] == "delivery_not_retried_without_message_id"
    assert capture.video_sends == []
    assert capture.document_sends == []
    assert capture.message_sends == []


def test_live9_sqlite_lease_blocks_second_recovery_owner(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_job()
    first = bot.subdub_claim_recovery_lease(job, "recovery")
    assert first["execution_owner"] == bot.SUBDUB_RECOVERY_OWNER
    original_owner = bot.SUBDUB_RECOVERY_OWNER
    monkeypatch.setattr(bot, "SUBDUB_RECOVERY_OWNER", "second-instance")

    second = bot.subdub_claim_recovery_lease(_persisted(job), "recovery")

    assert second == {}
    monkeypatch.setattr(bot, "SUBDUB_RECOVERY_OWNER", original_owner)


@pytest.mark.parametrize(
    "mode",
    [
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    ],
)
@pytest.mark.parametrize(
    ("stage", "progress_percent", "expected_blocker"),
    [
        (
            "received_file",
            5,
            "recovery_checkpoint_unavailable_after_restart:received_file",
        ),
        (
            "generating_voice",
            65,
            "tts_checkpoint_unavailable_after_restart",
        ),
        (
            "validating",
            90,
            "recovery_checkpoint_unavailable_after_restart:validating",
        ),
    ],
)
def test_live9_restart_without_checkpoint_never_stays_running(
    monkeypatch,
    tmp_path,
    mode,
    stage,
    progress_percent,
    expected_blocker,
):
    _setup(monkeypatch, tmp_path)
    job = _make_job(mode)
    bot.subdub_persist_recovery_fields(
        job,
        "test process loss without checkpoint",
        current_stage=stage,
        progress_stage=stage,
        progress_percent=progress_percent,
        status="running",
        terminal_state="",
        status_registry_missing_after_restart=True,
        tts_cue_checkpoints=[],
    )
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()

    result = asyncio.run(
        bot.subdub_recover_persisted_job(
            _persisted(job),
            None,
            lang="vi",
            source="boot",
        )
    )

    assert result["terminal_state"] == "failed_no_charge"
    assert result["status"] == "failed_no_charge"
    assert result["pipeline_blocker"] == expected_blocker
    assert result["charge_status"] == "not_charged"
    assert result["recovered_from_persisted_subdub_job"] is True


@pytest.mark.parametrize(
    "mode",
    [
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    ],
)
def test_live9_restart_at_95_delivers_existing_artifact_once_per_lane(
    monkeypatch,
    tmp_path,
    mode,
):
    _setup(monkeypatch, tmp_path)
    artifact = Path(tmp_path) / f"{mode}-final.mp4"
    artifact.write_bytes(b"fixture-final-mp4")
    job = _make_job(mode)
    bot.subdub_persist_recovery_fields(
        job,
        "test lane artifact awaiting delivery",
        artifact_path=str(artifact),
        final_mp4_path=str(artifact),
        artifact_duration=30.0,
        output_duration=30.0,
        current_stage="validating",
        progress_stage="validating",
        progress_percent=95,
        delivery_attempted=False,
        status_registry_missing_after_restart=True,
    )
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()

    async def validate(_payload, *, require_audio=False):
        assert require_audio is (
            mode in {
                bot.VIDEO_SUBTITLE_MODE_DUB,
                bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            }
        )
        return {"ok": True, "duration": 30.0}

    monkeypatch.setattr(bot, "subdub_validate_video_output", validate)
    capture = CaptureBot()

    first = asyncio.run(
        bot.subdub_recover_persisted_job(
            _persisted(job),
            capture,
            lang="vi",
            source="status_refresh",
        )
    )
    second = asyncio.run(
        bot.subdub_recover_persisted_job(
            _persisted(job),
            capture,
            lang="vi",
            source="watchdog",
        )
    )

    assert first["terminal_state"] == "delivered"
    assert first["progress_percent"] == 100
    assert first["receipt_sent_once"] is True
    assert first["terminal_receipt_count"] == 1
    assert second["terminal_state"] == "delivered"
    assert len(capture.video_sends) == 1
    assert len(capture.message_sends) == 1
    assert len(capture.edits) >= 1


def test_live9_atomic_receipt_claim_blocks_second_instance(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    job = _make_job()
    delivered = bot.subdub_persist_recovery_fields(
        job,
        "test delivered panel before receipt",
        status="completed",
        terminal_state="delivered",
        delivery_message_id="video-42",
        video_delivery_message_id="video-42",
        output_sent=True,
        status_panel_terminal_edit_succeeded=True,
        panel_final_percent=100,
        status_panel_terminalized=True,
        receipt_sent_once=False,
        receipt_send_attempted=False,
    )

    first = bot.subdub_claim_recovery_receipt(delivered)
    assert first["receipt_send_state"] == "claimed"
    assert first["receipt_send_attempted"] is True
    original_owner = bot.SUBDUB_RECOVERY_OWNER
    monkeypatch.setattr(bot, "SUBDUB_RECOVERY_OWNER", "second-instance")

    second = bot.subdub_claim_recovery_receipt(_persisted(job))

    assert second == {}
    monkeypatch.setattr(bot, "SUBDUB_RECOVERY_OWNER", original_owner)
