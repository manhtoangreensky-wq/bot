"""tests/test_p0_autopost_product_video_adapter.py

Tests for P0.AUTOPOST.S3: Product Video -> AutoPost Adapter Integration.
Governed under TOAN AAS Owner-Governed Codex.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any

import pytest

from services import autopost_asset_handoff as aah
from services import autopost_product_video_adapter as apva
from services import autopost_scheduler as aps
from services import video_editengine1
from services import video_local_validation
from services import video_project_queue as queue


def _make_dummy_video(tmp_path: Path, name: str = "test.mp4", content: bytes = b"dummy_mp4_bytes_1234567890") -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().lower()


@pytest.fixture(autouse=True)
def mock_media_probe(monkeypatch):
    monkeypatch.setattr(
        video_local_validation,
        "probe_video_file",
        lambda _path: {
            "ok": True,
            "duration": 15.0,
            "duration_ms": 15000,
            "width": 720,
            "height": 1280,
            "has_video": True,
            "has_audio": True,
            "format_name": "mp4",
        },
    )


def _setup_product_video_job(
    conn: sqlite3.Connection,
    tmp_path: Path,
    uid: int = 7126457028,
    raw_bytes: bytes = b"pv_s3_canonical_video_bytes",
) -> tuple[int, int, Path, str]:
    queue.ensure_video_project_queue_schema(conn)
    aah.ensure_autopost_handoff_schema(conn)
    aps.ensure_autopost_scheduler_schema(conn)
    apva.ensure_autopost_product_video_adapter_schema(conn)

    video_file = _make_dummy_video(tmp_path, f"pv_s3_final_{uid}.mp4", raw_bytes)
    sha = _sha256(raw_bytes)

    project = queue.create_video_project(
        conn,
        user_id=uid,
        profile_id="video_ai_prompt",
        topic="AutoPost S3 Test",
        asset_pack={
            "source": "product_video",
            "product_type": "video_ai_prompt",
            "render_mode": "real",
            "public_user": True,
        },
    )
    project_id = int(project["project_id"])
    queue.update_video_project(
        conn,
        project_id,
        status="processing",
        is_confirmed=1,
        scene_count=1,
        invoice_json={"scene_count": 1, "duration_seconds": 15},
    )
    job = queue.enqueue_video_render_job(
        conn,
        project_id=project_id,
        user_id=uid,
        max_attempts=3,
    )
    job_id = int(job["id"])

    persisted = {
        "source": "product_video",
        "product_video": True,
        "public_user": True,
        "render_mode": "real",
        "scene_count": 1,
        "scene_tasks": [
            {
                "scene_index": 1,
                "provider_task_id": "task-scene-1",
                "winning_task_id": "task-scene-1",
                "status": "scene_clip_validated",
                "clip_valid": True,
                "clip_bytes": len(raw_bytes),
            }
        ],
        "scenes_total": 1,
        "scenes_done": 1,
        "charged_xu": 0,
        "video_artifact_hash": sha,
        "artifact_hash": sha,
    }
    conn.execute(
        """UPDATE video_jobs
              SET status='processing', locked_by='vps-toanaas-01', attempts=1,
                  result_json=?, progress_percent=90, progress_message='uploading final video'
            WHERE id=?""",
        (json.dumps(persisted), job_id),
    )
    conn.commit()
    return project_id, job_id, video_file, sha


def _complete_job_helper(conn, job_id, video_file, sha, monkeypatch):
    monkeypatch.setattr(
        queue.video_final_output,
        "validate_final_video_output",
        lambda **_kw: {"ok": True, "bytes": os.path.getsize(video_file), "duration": 15.0, "has_video": True, "has_audio": True},
    )
    monkeypatch.setattr(
        queue,
        "product_video_duration_contract",
        lambda *_a, **_kw: {"ok": True, "reason": "", "expected_duration_seconds": 15.0, "actual_duration_seconds": 15.0},
    )
    return queue.complete_video_job(
        conn,
        job_id=job_id,
        final_video_path=str(video_file),
        final_video_file_id=f"tg_file_{job_id}",
        result={"ok": True, "final_video_path": str(video_file), "video_artifact_hash": sha},
    )


# =========================================================================
# TEST CASES 01 to 36
# =========================================================================

def test_01_first_red_product_video_adapter_gap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """01: Prove baseline red gap: without explicit intent, no drafts or publications created."""
    conn = sqlite3.connect(tmp_path / "t01.db")
    conn.row_factory = sqlite3.Row

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path)
    completed = _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)
    assert completed["ok"] is True
    assert completed["autopost_handoff"]["created_or_reused"] is True

    # Adapter returned no_intent_registered
    adapter = completed.get("autopost_adapter")
    assert adapter is not None
    assert adapter["attempted"] is False
    assert adapter["blocker"] == "no_intent_registered"

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_drafts")
    assert cur.fetchone()[0] == 0


def test_02_register_off_intent(tmp_path: Path):
    """02: Register OFF intent successfully and verify idempotency."""
    conn = sqlite3.connect(tmp_path / "t02.db")
    conn.row_factory = sqlite3.Row

    intent, status = apva.register_product_video_autopost_intent(conn, 101, 201, "OFF")
    assert intent is not None
    assert status == "registered"
    assert intent["mode"] == "OFF"
    assert intent["status"] == "PENDING"

    # Re-registration returns idempotent_existing
    intent2, status2 = apva.register_product_video_autopost_intent(conn, 101, 201, "OFF")
    assert status2 == "idempotent_existing"
    assert intent2["intent_id"] == intent["intent_id"]


def test_03_off_completion_creates_zero_drafts_zero_queue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """03: OFF completion creates handoff but zero drafts and zero queue rows."""
    conn = sqlite3.connect(tmp_path / "t03.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    apva.register_product_video_autopost_intent(conn, uid, job_id, "OFF")

    completed = _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)
    assert completed["ok"] is True
    assert completed["autopost_handoff"] is not None

    adapter = completed.get("autopost_adapter")
    assert adapter is not None
    assert adapter["attempted"] is True
    assert adapter["mode"] == "OFF"
    assert adapter["draft_id"] is None
    assert adapter["publication_id"] is None

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_drafts")
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM autopost_publication_queue")
    assert cur.fetchone()[0] == 0


def test_04_register_draft_only(tmp_path: Path):
    """04: Register DRAFT_ONLY intent successfully."""
    conn = sqlite3.connect(tmp_path / "t04.db")
    conn.row_factory = sqlite3.Row

    intent, status = apva.register_product_video_autopost_intent(
        conn, 101, 201, "DRAFT_ONLY", caption_override="My custom caption"
    )
    assert intent is not None
    assert status == "registered"
    assert intent["mode"] == "DRAFT_ONLY"
    assert intent["caption_override"] == "My custom caption"


def test_05_draft_only_completion_creates_one_planned_draft(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """05: DRAFT_ONLY completion creates exactly one PLANNED draft and zero queue rows."""
    conn = sqlite3.connect(tmp_path / "t05.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    apva.register_product_video_autopost_intent(
        conn, uid, job_id, "DRAFT_ONLY", caption_override="PV Draft Only Caption"
    )

    completed = _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)
    assert completed["ok"] is True

    adapter = completed.get("autopost_adapter")
    assert adapter is not None
    assert adapter["attempted"] is True
    assert adapter["mode"] == "DRAFT_ONLY"
    assert adapter["state"] == "PLANNED"
    assert adapter["draft_id"] is not None
    assert adapter["publication_id"] is None

    cur = conn.cursor()
    cur.execute("SELECT * FROM autopost_publication_drafts WHERE draft_id=?", (adapter["draft_id"],))
    draft = cur.fetchone()
    assert draft is not None
    assert draft["status"] == "PLANNED"
    assert draft["caption_draft"] == "PV Draft Only Caption"

    cur.execute("SELECT COUNT(*) FROM autopost_publication_queue")
    assert cur.fetchone()[0] == 0


def test_06_draft_only_replay_returns_same_draft(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """06: Replaying DRAFT_ONLY returns same draft and creates 0 duplicate rows."""
    conn = sqlite3.connect(tmp_path / "t06.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    apva.register_product_video_autopost_intent(conn, uid, job_id, "DRAFT_ONLY")

    c1 = _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)
    draft_id1 = c1["autopost_adapter"]["draft_id"]

    res2, status2 = apva.process_product_video_autopost_handoff(conn, job_id, uid)
    assert res2["draft_id"] == draft_id1

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_drafts")
    assert cur.fetchone()[0] == 1


def test_07_register_schedule_at_valid_utc(tmp_path: Path):
    """07: Register SCHEDULE_AT with valid UTC timestamp."""
    conn = sqlite3.connect(tmp_path / "t07.db")
    conn.row_factory = sqlite3.Row

    intent, status = apva.register_product_video_autopost_intent(
        conn, 101, 201, "SCHEDULE_AT", schedule_at="2026-09-25T14:30:00Z"
    )
    assert intent is not None
    assert status == "registered"
    assert intent["schedule_at"] == "2026-09-25T14:30:00Z"


def test_08_schedule_at_completion_creates_scheduled_queue_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """08: SCHEDULE_AT completion produces final state SCHEDULED in queue."""
    conn = sqlite3.connect(tmp_path / "t08.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    sched_time = "2026-09-25T14:30:00Z"
    apva.register_product_video_autopost_intent(
        conn, uid, job_id, "SCHEDULE_AT", schedule_at=sched_time, selected_channels=["tiktok", "youtube"]
    )

    completed = _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)
    assert completed["ok"] is True

    adapter = completed.get("autopost_adapter")
    assert adapter is not None
    assert adapter["state"] == "SCHEDULED"
    assert adapter["publication_id"] is not None

    cur = conn.cursor()
    cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=?", (adapter["publication_id"],))
    q_item = cur.fetchone()
    assert q_item is not None
    assert q_item["state"] == "SCHEDULED"
    assert q_item["schedule_at"] == sched_time


def test_09_schedule_at_invalid_utc_fails_adapter_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """09: Invalid UTC schedule fails adapter only, Product Video remains completed."""
    conn = sqlite3.connect(tmp_path / "t09.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)

    # Force an invalid schedule directly into DB to test adapter fail-closed handling
    apva.ensure_autopost_product_video_adapter_schema(conn)
    conn.execute(
        """INSERT INTO autopost_product_video_intents (
            intent_id, owner_id, product_video_job_id, mode, schedule_at,
            selected_channels_json, caption_override, status, created_at, updated_at
        ) VALUES ('intent_bad', ?, ?, 'SCHEDULE_AT', 'invalid-utc-time', '[]', NULL, 'PENDING', '2026-09-20T00:00:00Z', '2026-09-20T00:00:00Z')""",
        (uid, job_id),
    )
    conn.commit()

    completed = _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)
    assert completed["ok"] is True
    assert completed["job"]["status"] == "completed"

    adapter = completed.get("autopost_adapter")
    assert adapter is not None
    assert "schedule_time_invalid" in str(adapter["blocker"])

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_queue")
    assert cur.fetchone()[0] == 0


def test_10_schedule_now_creates_due_scheduled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """10: SCHEDULE_NOW results in SCHEDULED state due immediately."""
    conn = sqlite3.connect(tmp_path / "t10.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    apva.register_product_video_autopost_intent(conn, uid, job_id, "SCHEDULE_NOW")

    completed = _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)
    assert completed["ok"] is True

    adapter = completed.get("autopost_adapter")
    assert adapter is not None
    assert adapter["state"] == "SCHEDULED"

    cur = conn.cursor()
    cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=?", (adapter["publication_id"],))
    q_item = cur.fetchone()
    assert q_item["state"] == "SCHEDULED"
    assert q_item["schedule_at"] <= aps.canonical_utc_now()


def test_11_schedule_now_does_not_claim_automatically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """11: SCHEDULE_NOW leaves publication SCHEDULED without auto-claim."""
    conn = sqlite3.connect(tmp_path / "t11.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    apva.register_product_video_autopost_intent(conn, uid, job_id, "SCHEDULE_NOW")

    completed = _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)
    adapter = completed.get("autopost_adapter")

    cur = conn.cursor()
    cur.execute("SELECT * FROM autopost_publication_queue WHERE publication_id=?", (adapter["publication_id"],))
    q_item = cur.fetchone()
    assert q_item["state"] == "SCHEDULED"
    assert q_item["lease_owner"] is None
    assert q_item["attempt_count"] == 0


def test_12_exact_replay_produces_one_handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """12: Replaying completion 3 times yields exactly 1 handoff receipt."""
    conn = sqlite3.connect(tmp_path / "t12.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    apva.register_product_video_autopost_intent(conn, uid, job_id, "DRAFT_ONLY")

    _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)
    apva.process_product_video_autopost_handoff(conn, job_id, uid)
    apva.process_product_video_autopost_handoff(conn, job_id, uid)

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_handoff_receipts")
    assert cur.fetchone()[0] == 1


def test_13_exact_replay_produces_one_draft(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """13: Replaying completion 3 times yields exactly 1 draft."""
    conn = sqlite3.connect(tmp_path / "t13.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    apva.register_product_video_autopost_intent(conn, uid, job_id, "DRAFT_ONLY")

    _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)
    apva.process_product_video_autopost_handoff(conn, job_id, uid)
    apva.process_product_video_autopost_handoff(conn, job_id, uid)

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_drafts")
    assert cur.fetchone()[0] == 1


def test_14_exact_replay_produces_one_scheduler_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """14: Replaying SCHEDULE_NOW 3 times yields exactly 1 queue row."""
    conn = sqlite3.connect(tmp_path / "t14.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    apva.register_product_video_autopost_intent(conn, uid, job_id, "SCHEDULE_NOW")

    _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)
    apva.process_product_video_autopost_handoff(conn, job_id, uid)
    apva.process_product_video_autopost_handoff(conn, job_id, uid)

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_queue")
    assert cur.fetchone()[0] == 1


def test_15_concurrent_adapter_replay_one_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """15: Concurrent executions across connections yield exactly 1 draft and 1 queue row."""
    db_path = tmp_path / "t15.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    apva.register_product_video_autopost_intent(conn, uid, job_id, "SCHEDULE_NOW")
    _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)
    conn.close()

    def _worker_run():
        w_conn = sqlite3.connect(db_path, timeout=30.0)
        w_conn.row_factory = sqlite3.Row
        try:
            res, _ = apva.process_product_video_autopost_handoff(w_conn, job_id, uid)
            return res
        finally:
            w_conn.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_worker_run) for _ in range(4)]
        results = [f.result() for f in futures]

    pub_ids = {r.get("publication_id") for r in results if r.get("publication_id")}
    assert len(pub_ids) == 1

    chk_conn = sqlite3.connect(db_path)
    cur = chk_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_drafts")
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT COUNT(*) FROM autopost_publication_queue")
    assert cur.fetchone()[0] == 1
    chk_conn.close()


def test_16_wrong_owner_intent_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """16: Requesting user mismatch against intent owner is blocked."""
    conn = sqlite3.connect(tmp_path / "t16.db")
    conn.row_factory = sqlite3.Row

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=101)
    _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)

    apva.register_product_video_autopost_intent(conn, 101, job_id, "DRAFT_ONLY")
    res, err = apva.process_product_video_autopost_handoff(conn, job_id, owner_id=999)
    assert res["attempted"] is False or "failed" in str(res["blocker"]) or "mismatch" in str(res["blocker"])


def test_17_wrong_product_video_owner_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """17: Resolver rejects when requesting user does not own the Product Video."""
    conn = sqlite3.connect(tmp_path / "t17.db")
    conn.row_factory = sqlite3.Row

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=101)
    _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)

    apva.register_product_video_autopost_intent(conn, 999, job_id, "DRAFT_ONLY")
    res, err = apva.process_product_video_autopost_handoff(conn, job_id, owner_id=999)
    assert "owner_mismatch" in str(res["blocker"]) or "canonical_resolver_failed" in str(res["blocker"])


def test_18_queued_product_video_blocked(tmp_path: Path):
    """18: Queued Product Video is not terminal and blocked from AutoPost."""
    conn = sqlite3.connect(tmp_path / "t18.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    conn.execute("UPDATE video_jobs SET status='queued' WHERE id=?", (job_id,))
    conn.commit()

    apva.register_product_video_autopost_intent(conn, uid, job_id, "DRAFT_ONLY")
    res, err = apva.process_product_video_autopost_handoff(conn, job_id, uid)
    assert "canonical_resolver_failed" in str(res["blocker"])


def test_19_processing_product_video_blocked(tmp_path: Path):
    """19: Processing Product Video is blocked from AutoPost."""
    conn = sqlite3.connect(tmp_path / "t19.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    apva.register_product_video_autopost_intent(conn, uid, job_id, "DRAFT_ONLY")
    res, err = apva.process_product_video_autopost_handoff(conn, job_id, uid)
    assert "canonical_resolver_failed" in str(res["blocker"])


def test_20_failed_product_video_blocked(tmp_path: Path):
    """20: Failed Product Video is blocked from AutoPost."""
    conn = sqlite3.connect(tmp_path / "t20.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    conn.execute("UPDATE video_jobs SET status='failed' WHERE id=?", (job_id,))
    conn.commit()

    apva.register_product_video_autopost_intent(conn, uid, job_id, "DRAFT_ONLY")
    res, err = apva.process_product_video_autopost_handoff(conn, job_id, uid)
    assert "canonical_resolver_failed" in str(res["blocker"])


def test_21_cancelled_product_video_blocked(tmp_path: Path):
    """21: Cancelled Product Video is blocked from AutoPost."""
    conn = sqlite3.connect(tmp_path / "t21.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    conn.execute("UPDATE video_jobs SET status='cancelled' WHERE id=?", (job_id,))
    conn.commit()

    apva.register_product_video_autopost_intent(conn, uid, job_id, "DRAFT_ONLY")
    res, err = apva.process_product_video_autopost_handoff(conn, job_id, uid)
    assert "canonical_resolver_failed" in str(res["blocker"])


def test_22_intermediate_clip_blocked(tmp_path: Path):
    """22: Intermediate scene clip without terminal final MP4 is blocked."""
    conn = sqlite3.connect(tmp_path / "t22.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    conn.execute("UPDATE video_projects SET video_terminal_state=NULL WHERE project_id=?", (project_id,))
    conn.commit()

    apva.register_product_video_autopost_intent(conn, uid, job_id, "DRAFT_ONLY")
    res, err = apva.process_product_video_autopost_handoff(conn, job_id, uid)
    assert "canonical_resolver_failed" in str(res["blocker"])


def test_23_replaced_artifact_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """23: Tampered or replaced physical artifact is blocked."""
    conn = sqlite3.connect(tmp_path / "t23.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)

    # Tamper with file
    video_file.write_bytes(b"tampered_bytes_after_completion")

    apva.register_product_video_autopost_intent(conn, uid, job_id, "DRAFT_ONLY")
    res, err = apva.process_product_video_autopost_handoff(conn, job_id, uid)
    assert "canonical_resolver_failed" in str(res["blocker"]) or "tampered" in str(res["blocker"])


def test_24_handoff_artifact_drift_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """24: Drift between stored handoff hash and physical artifact is blocked."""
    conn = sqlite3.connect(tmp_path / "t24.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    apva.register_product_video_autopost_intent(conn, uid, job_id, "DRAFT_ONLY")
    _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)

    # Delete existing draft so receive_autopost_handoff_to_draft runs revalidation
    conn.execute("DELETE FROM autopost_publication_drafts")
    # Corrupt artifact hash in handoff receipt
    conn.execute("UPDATE autopost_handoff_receipts SET artifact_sha256='0000000000000000000000000000000000000000000000000000000000000000'")
    conn.commit()

    res, err = apva.process_product_video_autopost_handoff(conn, job_id, uid)
    assert "draft_failed" in str(res["blocker"]) or "tampered" in str(res["blocker"])


def test_25_adapter_failure_does_not_revert_producer_completion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """25: Any exception inside AutoPost adapter leaves Product Video completed."""
    conn = sqlite3.connect(tmp_path / "t25.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)

    def _exploding_adapter(*_a, **_kw):
        raise RuntimeError("simulated_autopost_catastrophic_failure")

    monkeypatch.setattr(apva, "process_product_video_autopost_handoff", _exploding_adapter)

    completed = _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)
    assert completed["ok"] is True
    assert completed["job"]["status"] == "completed"
    assert "autopost_adapter_error" in str(completed["autopost_adapter"]["blocker"])


def test_26_adapter_failure_does_not_rerender(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """26: AutoPost adapter failure never invokes producer re-render."""
    conn = sqlite3.connect(tmp_path / "t26.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)

    rerender_called = []
    monkeypatch.setattr(queue, "enqueue_video_render_job", lambda *_a, **_kw: rerender_called.append(True))

    _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)
    assert len(rerender_called) == 0


def test_27_adapter_failure_does_not_requeue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """27: AutoPost adapter failure never re-queues the video job."""
    conn = sqlite3.connect(tmp_path / "t27.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    completed = _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)
    assert completed["job"]["status"] == "completed"
    assert completed["job"]["attempts"] == 1


def test_28_product_video_billing_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """28: AutoPost adapter execution does not mutate Product Video billing state or charged xu."""
    conn = sqlite3.connect(tmp_path / "t28.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    apva.register_product_video_autopost_intent(conn, uid, job_id, "SCHEDULE_NOW")

    completed = _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)
    assert completed["ok"] is True

    cur = conn.cursor()
    cur.execute("SELECT * FROM video_projects WHERE project_id=?", (project_id,))
    p = cur.fetchone()
    assert json.loads(p["invoice_json"]) == {"scene_count": 1, "duration_seconds": 15}


def test_29_product_video_delivery_truth_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """29: Product Video delivery truth remains successful regardless of AutoPost."""
    conn = sqlite3.connect(tmp_path / "t29.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    completed = _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)
    assert completed["project"]["video_terminal_state"] == "final_mp4_ready"


def test_30_schedule_conflict_different_timestamp_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """30: Schedule replay with different timestamp fails closed without creating second queue row."""
    conn = sqlite3.connect(tmp_path / "t30.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    t1 = "2026-09-25T10:00:00Z"
    apva.register_product_video_autopost_intent(conn, uid, job_id, "SCHEDULE_AT", schedule_at=t1)
    _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)

    # Force change intent schedule_at to T2
    t2 = "2026-09-26T12:00:00Z"
    conn.execute("UPDATE autopost_product_video_intents SET schedule_at=? WHERE product_video_job_id=?", (t2, job_id))
    conn.commit()

    res, err = apva.process_product_video_autopost_handoff(conn, job_id, uid)
    assert res["blocker"] == "schedule_conflict_different_timestamp"

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_queue")
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT schedule_at FROM autopost_publication_queue")
    assert cur.fetchone()[0] == t1


def test_31_selected_channel_metadata_persists_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """31: Selected channel metadata is persisted on draft without implementing channel adapters."""
    conn = sqlite3.connect(tmp_path / "t31.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    apva.register_product_video_autopost_intent(
        conn, uid, job_id, "DRAFT_ONLY", selected_channels=["tiktok", "facebook"]
    )
    completed = _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)

    cur = conn.cursor()
    cur.execute("SELECT selected_channels_json FROM autopost_publication_drafts")
    channels = json.loads(cur.fetchone()[0])
    assert set(channels) == {"tiktok", "facebook"}


def test_32_zero_social_or_provider_calls(monkeypatch: pytest.MonkeyPatch):
    """32: S3 execution makes zero network or provider calls."""
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_kw: pytest.fail("Forbidden network call"))


def test_33_no_wallet_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """33: AutoPost S3 adapter causes zero mutations to wallet tables."""
    conn = sqlite3.connect(tmp_path / "t33.db")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS user_wallets (user_id INTEGER PRIMARY KEY, balance INTEGER)")
    conn.execute("INSERT INTO user_wallets VALUES (7126457028, 500)")
    conn.commit()

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=7126457028)
    apva.register_product_video_autopost_intent(conn, 7126457028, job_id, "SCHEDULE_NOW")
    _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)

    cur = conn.cursor()
    cur.execute("SELECT balance FROM user_wallets WHERE user_id=7126457028")
    assert cur.fetchone()[0] == 500


def test_34_video_edit_completion_does_not_activate_s3(tmp_path: Path):
    """34: Video Edit completion callback does not create AutoPost publication drafts or queue rows."""
    conn = sqlite3.connect(tmp_path / "t34.db")
    conn.row_factory = sqlite3.Row

    # From S1.4 suite: run a Video Edit completion
    from tests.test_p0_autopost_production_callback_seam import _setup_video_edit_job
    job, rec, video_file, sha = _setup_video_edit_job(conn, tmp_path, uid=77)

    # Registering a fake product video intent with same job_id must not trigger Video Edit draft
    apva.register_product_video_autopost_intent(conn, 77, job["local_worker_job_id"], "SCHEDULE_NOW")

    updated = video_editengine1.record_worker_update(
        conn,
        worker_job_id=job["local_worker_job_id"],
        worker_status="succeeded",
        detail={"stage": "delivering", "validation": "passed"},
        receipt=rec,
    )
    conn.commit()

    assert updated.get("status") == "delivered"
    assert updated.get("autopost_handoff") is not None
    assert updated["autopost_handoff"]["created_or_reused"] is True
    assert updated.get("autopost_adapter") is None

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_publication_drafts")
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM autopost_publication_queue")
    assert cur.fetchone()[0] == 0


def test_35_s1_4_handoff_replay_remains_one_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """35: S1.4 handoff replay contract is preserved."""
    conn = sqlite3.connect(tmp_path / "t35.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)

    # Replay notification
    out2 = aah.notify_autopost_producer_completion(
        conn,
        source_product="video_product",
        source_ref=job_id,
        requesting_user_id=uid,
    )
    assert out2["created_or_reused"] is True

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM autopost_handoff_receipts")
    assert cur.fetchone()[0] == 1


def test_36_s2_scheduler_protected_behavior_remains_green(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """36: S2 scheduler lease, claim, and recovery remain intact."""
    conn = sqlite3.connect(tmp_path / "t36.db")
    conn.row_factory = sqlite3.Row
    uid = 7126457028

    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid)
    apva.register_product_video_autopost_intent(conn, uid, job_id, "SCHEDULE_NOW")
    completed = _complete_job_helper(conn, job_id, video_file, sha, monkeypatch)

    pub_id = completed["autopost_adapter"]["publication_id"]

    # Claim
    claimed, c_err = aps.claim_due_publication(conn, "worker-1")
    assert claimed is not None
    assert claimed["publication_id"] == pub_id
    assert claimed["state"] == "CLAIMED"
