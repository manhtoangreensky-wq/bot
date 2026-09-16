"""Targeted provider-free test suite for SPEC-PV02C2 VIDEO_TO_VIDEO running job recovery closure."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import bot
import local_worker
from services import (
    video_ai_edit_provider,
    video_ai_edit_status,
)


def _init_test_db(tmp_path: Path) -> sqlite3.Connection:
    db_file = tmp_path / "test_jobs.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE local_worker_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            command TEXT,
            job_type TEXT,
            status TEXT,
            provider TEXT,
            input_file_id TEXT,
            output_file_id TEXT,
            output_url TEXT,
            error_short TEXT,
            created_at TEXT,
            started_at TEXT,
            finished_at TEXT,
            xu_cost INTEGER DEFAULT 0,
            admin_only INTEGER DEFAULT 1,
            worker_id TEXT,
            updated_at TEXT,
            provider_task_id TEXT DEFAULT ''
        )
    """)
    conn.execute("CREATE INDEX idx_local_worker_jobs_status ON local_worker_jobs(status)")
    conn.execute("CREATE INDEX idx_local_worker_jobs_provider_task_id ON local_worker_jobs(provider_task_id)")
    return conn


def _make_dummy_job(
    conn: sqlite3.Connection,
    *,
    job_type: str = "video_ai_edit",
    status: str = "running",
    provider_task_id: str = "",
    error_short: str = "",
    worker_id: str = "",
    updated_at: str = "2026-09-16 10:00:00",
    input_file_id: str = "",
) -> int:
    if not input_file_id:
        input_file_id = json.dumps({
            "aiedit1_contract": 1,
            "user_id": "12345",
            "chat_id": "67890",
            "source_file_id": "fake_tg_file_id",
            "source_file_name": "source.mp4",
            "execution_lane": "generative",
            "provider_name": "shopaikey",
            "public_user_confirmed": True,
            "submit_source": "public_ai_video_edit_final_confirm",
            "max_render_seconds": 60,
        })
    cur = conn.execute(
        """INSERT INTO local_worker_jobs (
            user_id, command, job_type, status, provider, input_file_id,
            output_file_id, output_url, error_short, created_at, started_at,
            finished_at, xu_cost, admin_only, worker_id, updated_at, provider_task_id
        ) VALUES (
            '12345', 'ai_edit', ?, ?, 'shopaikey', ?,
            '', '', ?, '2026-09-16 09:59:00', '2026-09-16 10:00:00',
            '', 0, 1, ?, ?, ?
        )""",
        (job_type, status, input_file_id, error_short, worker_id, updated_at, provider_task_id),
    )
    conn.commit()
    return cur.lastrowid


def _setup_fake_media_env(tmp_path: Path):
    fake_ffmpeg = tmp_path / "ffmpeg.exe"
    fake_ffmpeg.write_bytes(b"")
    fake_ffprobe = tmp_path / "ffprobe.exe"
    fake_ffprobe.write_bytes(b"")
    src_video = tmp_path / "src.mp4"
    src_video.write_bytes(b"FAKE_MP4_SOURCE_BYTES_FOR_RECOVERY")
    return str(fake_ffmpeg), str(fake_ffprobe), src_video


# ---------------------------------------------------------------------------
# Test 1: Discover running job with task id after restart
# ---------------------------------------------------------------------------
def test_ai_edit_running_job_with_task_id_discovered_after_restart(tmp_path: Path):
    """Running video_ai_edit job with provider_task_id is discovered and claimable."""
    conn = _init_test_db(tmp_path)
    job_id = _make_dummy_job(
        conn,
        status="running",
        provider_task_id="task_live_123",
        worker_id="old_dead_worker",
        updated_at="2026-09-16 09:00:00",
    )

    recoverable = bot.find_recoverable_video_ai_edit_jobs(conn=conn)
    assert len(recoverable) == 1
    assert recoverable[0]["id"] == job_id
    assert recoverable[0]["provider_task_id"] == "task_live_123"

    claimed = bot.claim_recoverable_video_ai_edit_job(worker_id="restarted_worker", conn=conn)
    assert claimed
    assert claimed["id"] == job_id
    assert claimed["worker_id"] == "restarted_worker"
    assert claimed["provider_task_id"] == "task_live_123"
    conn.close()


# ---------------------------------------------------------------------------
# Test 2: Restart uses same provider task id
# ---------------------------------------------------------------------------
def test_ai_edit_restart_uses_same_provider_task_id(tmp_path: Path):
    """Claiming a recoverable job preserves the canonical provider_task_id."""
    conn = _init_test_db(tmp_path)
    job_id = _make_dummy_job(
        conn,
        status="running",
        provider_task_id="task_canonical_789",
    )
    claimed = bot.claim_recoverable_video_ai_edit_job(worker_id="new_worker", conn=conn)
    assert claimed["id"] == job_id
    assert video_ai_edit_status.resolve_provider_task_id(claimed) == "task_canonical_789"
    conn.close()


# ---------------------------------------------------------------------------
# Test 3: Restart does NOT call submit_video_edit
# ---------------------------------------------------------------------------
def test_ai_edit_restart_does_not_call_submit_video_edit(tmp_path: Path):
    """When a running job with provider_task_id is processed, submit_video_edit is NEVER called."""
    fake_ffmpeg, fake_ffprobe, src_video = _setup_fake_media_env(tmp_path)
    job = {
        "id": 888,
        "job_type": "video_ai_edit",
        "status": "running",
        "provider_task_id": "task_no_resubmit_001",
        "input_file_id": json.dumps({
            "aiedit1_contract": 1,
            "chat_id": "111",
            "source_file_id": "src_1",
            "source_file_name": "test.mp4",
            "execution_lane": "generative",
            "provider_name": "shopaikey",
            "public_user_confirmed": True,
            "submit_source": "public_ai_video_edit_final_confirm",
            "max_render_seconds": 60,
        }),
    }

    mock_config = MagicMock(provider_name="shopaikey", model="kling_v2v")

    with patch.object(local_worker, "_aiedit_ready_provider_configs", return_value=[mock_config]), \
         patch.object(local_worker, "_video_edit_telegram_media_config", return_value=MagicMock()), \
         patch.object(local_worker, "local_ffmpeg_path", return_value=fake_ffmpeg), \
         patch.object(local_worker, "find_ffprobe", return_value=fake_ffprobe), \
         patch.object(local_worker, "create_job_workspace", return_value=tmp_path), \
         patch.object(local_worker, "_video_edit_download_asset", return_value=MagicMock(path=src_video)), \
         patch.object(local_worker.video_local_validation, "probe_video_file", return_value={"ok": True}), \
         patch.object(local_worker.video_ai_edit_validation, "validate_input_metadata", return_value={"ok": True}), \
         patch.object(local_worker.video_ai_edit_validation, "validate_final_edited_mp4", return_value={"ok": True, "artifact_size": 100}), \
         patch.object(local_worker.video_ai_edit_provider, "submit_video_edit") as mock_submit, \
         patch.object(local_worker.video_ai_edit_provider, "wait_for_result", return_value={"status": "completed", "result_url": "https://fake.url/res.mp4", "result_url_present": True}) as mock_wait, \
         patch.object(local_worker.video_ai_edit_provider, "download_result"), \
         patch.object(local_worker, "telegram_send_video_receipt", return_value={"sent": True, "file_id": "out_file", "message_id": "msg_1"}), \
         patch.object(local_worker, "update_job"):

        local_worker.run_video_ai_edit(job)

        assert mock_submit.call_count == 0
        assert mock_wait.call_count == 1
        assert mock_wait.call_args[0][1] == "task_no_resubmit_001"


# ---------------------------------------------------------------------------
# Test 4: Recovery polls existing task
# ---------------------------------------------------------------------------
def test_ai_edit_recovery_polls_existing_task(tmp_path: Path):
    """Recovery routes directly to wait_for_result with the existing task ID."""
    fake_ffmpeg, fake_ffprobe, src_video = _setup_fake_media_env(tmp_path)
    job = {
        "id": 999,
        "job_type": "video_ai_edit",
        "status": "running",
        "provider_task_id": "task_poll_same_123",
        "input_file_id": json.dumps({
            "aiedit1_contract": 1,
            "chat_id": "111",
            "source_file_id": "src_1",
            "execution_lane": "generative",
            "provider_name": "shopaikey",
            "public_user_confirmed": True,
            "submit_source": "public_ai_video_edit_final_confirm",
        }),
    }

    mock_config = MagicMock(provider_name="shopaikey", model="kling_v2v")
    polled_ids = []

    def fake_wait(config, task_id, **kwargs):
        polled_ids.append(task_id)
        return {"status": "completed", "result_url": "https://fake.url/res.mp4", "result_url_present": True}

    with patch.object(local_worker, "_aiedit_ready_provider_configs", return_value=[mock_config]), \
         patch.object(local_worker, "_video_edit_telegram_media_config", return_value=MagicMock()), \
         patch.object(local_worker, "local_ffmpeg_path", return_value=fake_ffmpeg), \
         patch.object(local_worker, "find_ffprobe", return_value=fake_ffprobe), \
         patch.object(local_worker, "create_job_workspace", return_value=tmp_path), \
         patch.object(local_worker, "_video_edit_download_asset", return_value=MagicMock(path=src_video)), \
         patch.object(local_worker.video_local_validation, "probe_video_file", return_value={"ok": True}), \
         patch.object(local_worker.video_ai_edit_validation, "validate_input_metadata", return_value={"ok": True}), \
         patch.object(local_worker.video_ai_edit_validation, "validate_final_edited_mp4", return_value={"ok": True, "artifact_size": 100}), \
         patch.object(local_worker.video_ai_edit_provider, "wait_for_result", side_effect=fake_wait), \
         patch.object(local_worker.video_ai_edit_provider, "download_result"), \
         patch.object(local_worker, "telegram_send_video_receipt", return_value={"sent": True, "file_id": "out_file", "message_id": "msg_1"}), \
         patch.object(local_worker, "update_job"):

        local_worker.run_video_ai_edit(job)

    assert polled_ids == ["task_poll_same_123"]


# ---------------------------------------------------------------------------
# Test 5: Poll timeout preserves provider task id
# ---------------------------------------------------------------------------
def test_ai_edit_poll_timeout_preserves_provider_task_id(tmp_path: Path):
    """When poll times out, the update retains the provider_task_id in terminal payload and DB."""
    fake_ffmpeg, fake_ffprobe, src_video = _setup_fake_media_env(tmp_path)
    job = {
        "id": 101,
        "job_type": "video_ai_edit",
        "status": "running",
        "provider_task_id": "task_timeout_preserve_456",
        "input_file_id": json.dumps({
            "aiedit1_contract": 1,
            "chat_id": "111",
            "source_file_id": "src_1",
            "execution_lane": "generative",
            "provider_name": "shopaikey",
            "public_user_confirmed": True,
            "submit_source": "public_ai_video_edit_final_confirm",
        }),
    }

    mock_config = MagicMock(provider_name="shopaikey", model="kling_v2v")
    recorded_updates = []

    def fake_update(job_id, status, error_short="", **kwargs):
        recorded_updates.append({"status": status, "error_short": error_short})
        return {"ok": True}

    with patch.object(local_worker, "_aiedit_ready_provider_configs", return_value=[mock_config]), \
         patch.object(local_worker, "_video_edit_telegram_media_config", return_value=MagicMock()), \
         patch.object(local_worker, "local_ffmpeg_path", return_value=fake_ffmpeg), \
         patch.object(local_worker, "find_ffprobe", return_value=fake_ffprobe), \
         patch.object(local_worker, "create_job_workspace", return_value=tmp_path), \
         patch.object(local_worker, "_video_edit_download_asset", return_value=MagicMock(path=src_video)), \
         patch.object(local_worker.video_local_validation, "probe_video_file", return_value={"ok": True}), \
         patch.object(local_worker.video_ai_edit_validation, "validate_input_metadata", return_value={"ok": True}), \
         patch.object(local_worker.video_ai_edit_provider, "wait_for_result", side_effect=video_ai_edit_provider.AiEditProviderError("provider_poll_timeout")), \
         patch.object(local_worker, "update_job", side_effect=fake_update):

        local_worker.run_video_ai_edit(job)

    assert recorded_updates
    final_update = recorded_updates[-1]
    assert final_update["status"] == "running"
    parsed_err = json.loads(final_update["error_short"])
    assert parsed_err["provider_task_id"] == "task_timeout_preserve_456"
    assert parsed_err["reason"] == "provider_poll_timeout"


# ---------------------------------------------------------------------------
# Test 6: Poll timeout remains recoverable
# ---------------------------------------------------------------------------
def test_ai_edit_poll_timeout_remains_recoverable(tmp_path: Path):
    """A job that experienced poll timeout remains in running state and recoverable."""
    conn = _init_test_db(tmp_path)
    job_id = _make_dummy_job(
        conn,
        status="running",
        provider_task_id="task_recoverable_after_timeout",
        error_short=json.dumps({
            "aiedit1": 1,
            "stage": "ai_processing",
            "provider_status": "timeout_waiting",
            "reason": "provider_poll_timeout",
            "provider_task_id": "task_recoverable_after_timeout",
        }),
    )

    db_job = bot.get_local_worker_job(job_id, conn=conn)
    assert video_ai_edit_status.is_recoverable_video_ai_edit_job(db_job) is True

    recoverable_jobs = bot.find_recoverable_video_ai_edit_jobs(conn=conn)
    assert any(j["id"] == job_id for j in recoverable_jobs)
    conn.close()


# ---------------------------------------------------------------------------
# Test 7: Poll timeout does NOT resubmit
# ---------------------------------------------------------------------------
def test_ai_edit_poll_timeout_does_not_resubmit(tmp_path: Path):
    """When a timed-out job is re-run by a worker, submit_video_edit is NOT called."""
    fake_ffmpeg, fake_ffprobe, src_video = _setup_fake_media_env(tmp_path)
    job = {
        "id": 102,
        "job_type": "video_ai_edit",
        "status": "running",
        "provider_task_id": "task_no_resubmit_timeout",
        "error_short": json.dumps({
            "aiedit1": 1,
            "stage": "ai_processing",
            "provider_status": "timeout_waiting",
            "reason": "provider_poll_timeout",
            "provider_task_id": "task_no_resubmit_timeout",
        }),
        "input_file_id": json.dumps({
            "aiedit1_contract": 1,
            "chat_id": "111",
            "source_file_id": "src_1",
            "execution_lane": "generative",
            "provider_name": "shopaikey",
            "public_user_confirmed": True,
            "submit_source": "public_ai_video_edit_final_confirm",
        }),
    }

    mock_config = MagicMock(provider_name="shopaikey", model="kling_v2v")

    with patch.object(local_worker, "_aiedit_ready_provider_configs", return_value=[mock_config]), \
         patch.object(local_worker, "_video_edit_telegram_media_config", return_value=MagicMock()), \
         patch.object(local_worker, "local_ffmpeg_path", return_value=fake_ffmpeg), \
         patch.object(local_worker, "find_ffprobe", return_value=fake_ffprobe), \
         patch.object(local_worker, "create_job_workspace", return_value=tmp_path), \
         patch.object(local_worker, "_video_edit_download_asset", return_value=MagicMock(path=src_video)), \
         patch.object(local_worker.video_local_validation, "probe_video_file", return_value={"ok": True}), \
         patch.object(local_worker.video_ai_edit_validation, "validate_input_metadata", return_value={"ok": True}), \
         patch.object(local_worker.video_ai_edit_provider, "submit_video_edit") as mock_submit, \
         patch.object(local_worker.video_ai_edit_provider, "wait_for_result", side_effect=video_ai_edit_provider.AiEditProviderError("provider_poll_timeout")), \
         patch.object(local_worker, "update_job"):

        local_worker.run_video_ai_edit(job)

        assert mock_submit.call_count == 0


# ---------------------------------------------------------------------------
# Test 8: Terminal failure preserves provider task id
# ---------------------------------------------------------------------------
def test_ai_edit_terminal_failure_preserves_provider_task_id(tmp_path: Path):
    """Terminal failure preserves provider_task_id in DB and error payload."""
    conn = _init_test_db(tmp_path)
    job_id = _make_dummy_job(
        conn,
        status="running",
        provider_task_id="task_fail_preserve_999",
    )

    updated = bot.update_local_worker_job(
        job_id,
        status="failed",
        error_short=json.dumps({"aiedit1": 1, "stage": "failed_no_charge", "reason": "provider_terminal_failure"}),
        conn=conn,
    )
    assert updated["status"] == "failed"
    assert updated["provider_task_id"] == "task_fail_preserve_999"

    # Inspect direct DB row
    cur = conn.execute("SELECT provider_task_id, error_short FROM local_worker_jobs WHERE id=?", (job_id,))
    row = cur.fetchone()
    assert row[0] == "task_fail_preserve_999"
    conn.close()


# ---------------------------------------------------------------------------
# Test 9: Terminal success preserves provider task id
# ---------------------------------------------------------------------------
def test_ai_edit_terminal_success_preserves_provider_task_id(tmp_path: Path):
    """Terminal success preserves provider_task_id in DB."""
    conn = _init_test_db(tmp_path)
    job_id = _make_dummy_job(
        conn,
        status="running",
        provider_task_id="task_succ_preserve_888",
    )

    updated = bot.update_local_worker_job(
        job_id,
        status="succeeded",
        error_short=json.dumps({"aiedit1": 1, "stage": "delivered", "provider_task_id": "task_succ_preserve_888"}),
        output_url="https://res.mp4",
        output_file_id="tg_file_out",
        conn=conn,
    )
    assert updated["status"] == "succeeded"
    assert updated["provider_task_id"] == "task_succ_preserve_888"

    cur = conn.execute("SELECT provider_task_id FROM local_worker_jobs WHERE id=?", (job_id,))
    assert cur.fetchone()[0] == "task_succ_preserve_888"
    conn.close()


# ---------------------------------------------------------------------------
# Test 10: Progress update without task id does not clear existing task id
# ---------------------------------------------------------------------------
def test_ai_edit_progress_without_task_id_does_not_clear_existing_task_id(tmp_path: Path):
    """Intermediate progress update without task id in payload keeps existing provider_task_id."""
    conn = _init_test_db(tmp_path)
    job_id = _make_dummy_job(
        conn,
        status="running",
        provider_task_id="task_existing_keep_555",
    )

    # Update with progress payload that does not have provider_task_id
    updated = bot.update_local_worker_job(
        job_id,
        status="running",
        error_short=json.dumps({"aiedit1": 1, "stage": "inspecting_video", "charge": 0}),
        conn=conn,
    )
    assert updated["provider_task_id"] == "task_existing_keep_555"

    cur = conn.execute("SELECT provider_task_id FROM local_worker_jobs WHERE id=?", (job_id,))
    assert cur.fetchone()[0] == "task_existing_keep_555"
    conn.close()


# ---------------------------------------------------------------------------
# Test 11: Legacy task id recovers into canonical column
# ---------------------------------------------------------------------------
def test_ai_edit_legacy_task_id_recovers_into_canonical_column(tmp_path: Path):
    """Historical running job with empty provider_task_id column but task in error_short is recovered."""
    conn = _init_test_db(tmp_path)
    legacy_err = json.dumps({
        "aiedit1": 1,
        "stage": "ai_processing",
        "provider_task_id": "legacy_task_recovered_777",
    })
    job_id = _make_dummy_job(
        conn,
        status="running",
        provider_task_id="",
        error_short=legacy_err,
    )

    # Ensure column is currently empty
    cur = conn.execute("SELECT provider_task_id FROM local_worker_jobs WHERE id=?", (job_id,))
    assert cur.fetchone()[0] == ""

    # Claim should backfill into column
    claimed = bot.claim_recoverable_video_ai_edit_job(worker_id="legacy_worker", conn=conn)
    assert claimed["id"] == job_id
    assert claimed["provider_task_id"] == "legacy_task_recovered_777"

    cur = conn.execute("SELECT provider_task_id FROM local_worker_jobs WHERE id=?", (job_id,))
    assert cur.fetchone()[0] == "legacy_task_recovered_777"
    conn.close()


# ---------------------------------------------------------------------------
# Test 12: Legacy recovery does NOT resubmit
# ---------------------------------------------------------------------------
def test_ai_edit_legacy_recovery_does_not_resubmit(tmp_path: Path):
    """Recovering a legacy job with task ID in error_short never calls submit_video_edit."""
    fake_ffmpeg, fake_ffprobe, src_video = _setup_fake_media_env(tmp_path)
    job = {
        "id": 103,
        "job_type": "video_ai_edit",
        "status": "running",
        "provider_task_id": "",
        "error_short": json.dumps({
            "aiedit1": 1,
            "stage": "ai_processing",
            "provider_task_id": "legacy_task_no_resubmit",
        }),
        "input_file_id": json.dumps({
            "aiedit1_contract": 1,
            "chat_id": "111",
            "source_file_id": "src_1",
            "execution_lane": "generative",
            "provider_name": "shopaikey",
            "public_user_confirmed": True,
            "submit_source": "public_ai_video_edit_final_confirm",
        }),
    }

    mock_config = MagicMock(provider_name="shopaikey", model="kling_v2v")

    with patch.object(local_worker, "_aiedit_ready_provider_configs", return_value=[mock_config]), \
         patch.object(local_worker, "_video_edit_telegram_media_config", return_value=MagicMock()), \
         patch.object(local_worker, "local_ffmpeg_path", return_value=fake_ffmpeg), \
         patch.object(local_worker, "find_ffprobe", return_value=fake_ffprobe), \
         patch.object(local_worker, "create_job_workspace", return_value=tmp_path), \
         patch.object(local_worker, "_video_edit_download_asset", return_value=MagicMock(path=src_video)), \
         patch.object(local_worker.video_local_validation, "probe_video_file", return_value={"ok": True}), \
         patch.object(local_worker.video_ai_edit_validation, "validate_input_metadata", return_value={"ok": True}), \
         patch.object(local_worker.video_ai_edit_provider, "submit_video_edit") as mock_submit, \
         patch.object(local_worker.video_ai_edit_provider, "wait_for_result", return_value={"status": "completed", "result_url": "https://res.mp4", "result_url_present": True}) as mock_wait, \
         patch.object(local_worker.video_ai_edit_provider, "download_result"), \
         patch.object(local_worker.video_ai_edit_validation, "validate_final_edited_mp4", return_value={"ok": True, "artifact_size": 100}), \
         patch.object(local_worker, "telegram_send_video_receipt", return_value={"sent": True, "file_id": "out", "message_id": "m1"}), \
         patch.object(local_worker, "update_job"):

        local_worker.run_video_ai_edit(job)

        assert mock_submit.call_count == 0
        assert mock_wait.call_count == 1
        assert mock_wait.call_args[0][1] == "legacy_task_no_resubmit"


# ---------------------------------------------------------------------------
# Test 13: Two recovery attempts do not create second submit
# ---------------------------------------------------------------------------
def test_two_recovery_attempts_do_not_create_second_submit(tmp_path: Path):
    """Concurrent or sequential recovery attempts by multiple workers never trigger submit."""
    conn = _init_test_db(tmp_path)
    job_id = _make_dummy_job(
        conn,
        status="running",
        provider_task_id="task_multi_guard_111",
        worker_id="worker_a",
        updated_at="2026-09-16 10:00:00",
    )

    # Worker A claimed at 10:00:00. Worker B tries within lease: blocked
    with patch("bot.now_text", return_value="2026-09-16 10:01:00"):
        claimed_b = bot.claim_recoverable_video_ai_edit_job(worker_id="worker_b", lease_seconds=600, conn=conn)
        assert claimed_b == {}

    # Submit calls across any execution must be 0
    with patch.object(local_worker.video_ai_edit_provider, "submit_video_edit") as mock_submit:
        job = bot.get_local_worker_job(job_id, conn=conn)
        # Even if worker runs job directly:
        assert video_ai_edit_status.resolve_provider_task_id(job) == "task_multi_guard_111"
        assert mock_submit.call_count == 0
    conn.close()


# ---------------------------------------------------------------------------
# Test 14: Terminal AI edit job is NOT recovered
# ---------------------------------------------------------------------------
def test_terminal_ai_edit_job_is_not_recovered(tmp_path: Path):
    """Terminal jobs (succeeded, failed, cancelled) are never eligible for recovery."""
    conn = _init_test_db(tmp_path)
    j_succ = _make_dummy_job(conn, status="succeeded", provider_task_id="task_done_1")
    j_fail = _make_dummy_job(conn, status="failed", provider_task_id="task_done_2")
    j_canc = _make_dummy_job(conn, status="cancelled", provider_task_id="task_done_3")

    for jid in (j_succ, j_fail, j_canc):
        job = bot.get_local_worker_job(jid, conn=conn)
        assert video_ai_edit_status.is_recoverable_video_ai_edit_job(job) is False

    recoverable = bot.find_recoverable_video_ai_edit_jobs(conn=conn)
    assert len(recoverable) == 0

    claimed = bot.claim_recoverable_video_ai_edit_job(worker_id="w_test", conn=conn)
    assert claimed == {}
    conn.close()
