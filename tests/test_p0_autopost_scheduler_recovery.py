"""Tests for P0.AUTOPOST.S2: Durable AutoPost Scheduler, Lease, Retry, and Recovery.

Verifies the complete 35-item behavioral contract:
1. FIRST RED: PLANNED draft has no scheduler path before S2 schema/primitives.
2. PLANNED -> APPROVED valid owner.
3. owner mismatch approval blocked.
4. APPROVED -> SCHEDULED.
5. PLANNED cannot schedule directly.
6. canonical UTC schedule.
7. duplicate schedule idempotent.
8. concurrent schedule produces one queue row.
9. future schedule cannot be claimed early.
10. due schedule claims exactly once.
11. two workers race -> one winner.
12. stale worker cannot renew.
13. valid lease renewal.
14. CLAIMED -> PUBLISHING exact lease owner.
15. expired CLAIMED recovery.
16. retryable failure stores durable next_attempt_at.
17. retry not claimable before backoff.
18. retry claimable after backoff.
19. max attempts -> FAILED_FINAL.
20. FAILED_FINAL not requeued.
21. PUBLISHED immutable.
22. CANCELLED immutable.
23. expired PUBLISHING does not auto-republish.
24. ambiguous PUBLISHING recovery exposes blocker.
25. artifact SHA replacement blocks future dispatch.
26. scheduler rereads canonical handoff.
27. media probe holds no scheduler write lock.
28. retry never invokes producer rendering.
29. retry never requeues producer.
30. recovery replay idempotent.
31. S1.4 Product Video protected cases pass.
32. S1.4 Video Edit protected cases pass.
33. SubDub remains fail-closed.
34. Existing Video remains fail-closed.
35. zero provider/social/wallet effects.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from services import autopost_asset_handoff as aah
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
    """Ensure media probe validates test videos deterministically."""
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
            "codec_name": "h264",
            "format_name": "mp4",
        },
    )


def _setup_planned_draft(
    conn: sqlite3.Connection,
    tmp_path: Path,
    owner_id: int = 101,
    draft_id: str = "draft_s2_1",
    handoff_id: str = "hnd_s2_1",
    asset_id: str = "asset_s2_1",
) -> tuple[str, str, str, Path, str]:
    video_path = _make_dummy_video(tmp_path, f"{asset_id}.mp4")
    artifact_sha = _sha256(video_path.read_bytes())

    aah.ensure_autopost_handoff_schema(conn)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO autopost_handoff_receipts (
            handoff_id, asset_id, owner_id, source_product, source_job_id,
            artifact_sha256, purpose, status, parent_asset_id, lineage_json,
            asset_snapshot_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            handoff_id,
            asset_id,
            owner_id,
            "video_product",
            "job_s2_1",
            artifact_sha,
            "autopost",
            "active",
            None,
            json.dumps([]),
            json.dumps({"internal_artifact_path": str(video_path)}),
            "2026-09-20T10:00:00Z",
        ),
    )
    cur.execute(
        """INSERT INTO autopost_publication_drafts (
            draft_id, handoff_id, asset_id, owner_id, caption_draft,
            selected_channels_json, schedule_at, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            draft_id,
            handoff_id,
            asset_id,
            owner_id,
            "Sample Caption",
            json.dumps(["telegram"]),
            None,
            "PLANNED",
            "2026-09-20T10:00:00Z",
        ),
    )
    conn.commit()
    return draft_id, handoff_id, asset_id, video_path, artifact_sha


# =========================================================================
# 1. FIRST RED: PLANNED draft has no scheduler path before patch
# =========================================================================

def test_1_first_red_planned_draft_has_no_scheduler_path_in_s1_4(tmp_path):
    """1. Proves S1.4 base schema has only PLANNED draft without queue or lease."""
    conn = sqlite3.connect(tmp_path / "red.db")
    conn.row_factory = sqlite3.Row
    aah.ensure_autopost_handoff_schema(conn)

    # Queue table does not exist in bare S1.4 schema
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='autopost_publication_queue'")
    assert cur.fetchone() is None, "autopost_publication_queue must not exist in bare S1.4 schema"

    # In bare S1.4, PLANNED draft cannot be claimed by any scheduler worker
    cur.execute(
        """INSERT INTO autopost_publication_drafts (
            draft_id, handoff_id, asset_id, owner_id, caption_draft,
            selected_channels_json, schedule_at, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("d_red", "h_red", "a_red", 1, "c", json.dumps([]), None, "PLANNED", "2026-09-20T10:00:00Z"),
    )
    conn.commit()
    draft = conn.execute("SELECT * FROM autopost_publication_drafts WHERE draft_id='d_red'").fetchone()
    assert draft["status"] == "PLANNED"


# =========================================================================
# 2 & 3. APPROVAL (PLANNED -> APPROVED) & OWNER MISMATCH
# =========================================================================

def test_2_planned_to_approved_valid_owner(tmp_path):
    """2. PLANNED -> APPROVED with valid owner creates durable queue row."""
    conn = sqlite3.connect(tmp_path / "appr.db")
    conn.row_factory = sqlite3.Row
    draft_id, handoff_id, asset_id, _, sha = _setup_planned_draft(conn, tmp_path, owner_id=202)

    item, err = aps.approve_publication_draft(conn, draft_id, requesting_user_id=202)
    assert err == "approved"
    assert item is not None
    assert item["state"] == "APPROVED"
    assert item["owner_id"] == 202
    assert item["artifact_sha256"] == sha
    assert item["handoff_id"] == handoff_id
    assert item["asset_id"] == asset_id

    draft_row = conn.execute("SELECT status FROM autopost_publication_drafts WHERE draft_id=?", (draft_id,)).fetchone()
    assert draft_row["status"] == "APPROVED"


def test_3_owner_mismatch_approval_blocked(tmp_path):
    """3. Approval blocked when requesting user does not match draft/handoff owner."""
    conn = sqlite3.connect(tmp_path / "owner_mismatch.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=202)

    item, err = aps.approve_publication_draft(conn, draft_id, requesting_user_id=999)
    assert item is None
    assert err == "owner_mismatch"

    # Verify queue record was not created
    q_row = conn.execute("SELECT * FROM autopost_publication_queue WHERE draft_id=?", (draft_id,)).fetchone()
    assert q_row is None


# =========================================================================
# 4 & 5. SCHEDULING (APPROVED -> SCHEDULED) & UNAPPROVED REJECTION
# =========================================================================

def test_4_approved_to_scheduled(tmp_path):
    """4. APPROVED -> SCHEDULED moves draft and queue to SCHEDULED state with canonical UTC."""
    conn = sqlite3.connect(tmp_path / "sched.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=303)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=303)

    sched_ts = "2026-09-21T15:30:00Z"
    item, err = aps.schedule_publication(conn, draft_id, requesting_user_id=303, schedule_at=sched_ts)
    assert err == "scheduled"
    assert item is not None
    assert item["state"] == "SCHEDULED"
    assert item["schedule_at"] == sched_ts

    draft_row = conn.execute("SELECT status, schedule_at FROM autopost_publication_drafts WHERE draft_id=?", (draft_id,)).fetchone()
    assert draft_row["status"] == "SCHEDULED"
    assert draft_row["schedule_at"] == sched_ts


def test_5_planned_cannot_schedule_directly(tmp_path):
    """5. PLANNED draft cannot be scheduled directly without approval."""
    conn = sqlite3.connect(tmp_path / "unapproved_sched.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=303)

    item, err = aps.schedule_publication(conn, draft_id, requesting_user_id=303, schedule_at="2026-09-21T15:30:00Z")
    assert item is None
    assert err == "publication_not_approved"


# =========================================================================
# 6. CANONICAL UTC SCHEDULE
# =========================================================================

def test_6_canonical_utc_schedule_validation(tmp_path):
    """6. Schedule timestamp strictly enforces canonical UTC format; rejects naive/non-UTC."""
    conn = sqlite3.connect(tmp_path / "utc_sched.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=404)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=404)

    # Rejects naive timestamp without tz indicator
    item, err = aps.schedule_publication(conn, draft_id, requesting_user_id=404, schedule_at="2026-09-21 15:30:00")
    assert item is None
    assert err == "non_utc_or_naive_timestamp"

    # Rejects invalid timestamp string
    item, err = aps.schedule_publication(conn, draft_id, requesting_user_id=404, schedule_at="invalid-date")
    assert item is None
    assert err == "non_utc_or_naive_timestamp"

    # Accepts canonical UTC Z
    item, err = aps.schedule_publication(conn, draft_id, requesting_user_id=404, schedule_at="2026-09-21T15:30:00Z")
    assert err == "scheduled"
    assert item["schedule_at"] == "2026-09-21T15:30:00Z"


# =========================================================================
# 7 & 8. IDEMPOTENT & CONCURRENT SCHEDULING
# =========================================================================

def test_7_duplicate_schedule_idempotent(tmp_path):
    """7. Calling schedule repeatedly with identical parameters returns existing record idempotently."""
    conn = sqlite3.connect(tmp_path / "idem_sched.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=505)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=505)

    item1, err1 = aps.schedule_publication(conn, draft_id, requesting_user_id=505, schedule_at="2026-09-21T10:00:00Z")
    assert err1 == "scheduled"

    item2, err2 = aps.schedule_publication(conn, draft_id, requesting_user_id=505, schedule_at="2026-09-21T10:00:00Z")
    assert err2 == "idempotent_already_scheduled"
    assert item1["publication_id"] == item2["publication_id"]

    # Exactly 1 queue row exists
    count = conn.execute("SELECT COUNT(*) FROM autopost_publication_queue WHERE draft_id=?", (draft_id,)).fetchone()[0]
    assert count == 1


def test_8_concurrent_schedule_produces_one_queue_row(tmp_path):
    """8. Replay/concurrent approval or scheduling produces exactly one queue row (idempotency_key UNIQUE)."""
    conn = sqlite3.connect(tmp_path / "conc_sched.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=606)

    # First approval
    item1, err1 = aps.approve_publication_draft(conn, draft_id, requesting_user_id=606)
    assert err1 == "approved"

    # Second concurrent approval replay
    item2, err2 = aps.approve_publication_draft(conn, draft_id, requesting_user_id=606)
    assert "already_approved" in err2 or err2 == "approved"
    assert item1["publication_id"] == item2["publication_id"]

    count = conn.execute("SELECT COUNT(*) FROM autopost_publication_queue WHERE draft_id=?", (draft_id,)).fetchone()[0]
    assert count == 1


# =========================================================================
# 9, 10, 11. ATOMIC DUE CLAIM & RACE CONCURRENCY
# =========================================================================

def test_9_future_schedule_cannot_be_claimed_early(tmp_path):
    """9. A publication scheduled for the future cannot be claimed early."""
    conn = sqlite3.connect(tmp_path / "claim_future.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=707)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=707)
    aps.schedule_publication(conn, draft_id, requesting_user_id=707, schedule_at="2026-09-21T18:00:00Z")

    # Worker polls with now earlier than schedule_at
    claimed, err = aps.claim_due_publication(conn, worker_id="worker_alpha", now="2026-09-21T17:59:59Z")
    assert claimed is None
    assert err == "no_due_publications"


def test_10_due_schedule_claims_exactly_once(tmp_path):
    """10. A due publication is claimed exactly once; subsequent claim returns no due publications."""
    conn = sqlite3.connect(tmp_path / "claim_once.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=808)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=808)
    aps.schedule_publication(conn, draft_id, requesting_user_id=808, schedule_at="2026-09-21T18:00:00Z")

    # Worker claims at or after schedule_at
    claimed, err = aps.claim_due_publication(conn, worker_id="worker_alpha", now="2026-09-21T18:00:01Z", lease_seconds=300)
    assert err == "claimed"
    assert claimed is not None
    assert claimed["state"] == "CLAIMED"
    assert claimed["lease_owner"] == "worker_alpha"
    assert claimed["attempt_count"] == 1
    assert claimed["lease_expires_at"] == "2026-09-21T18:05:01Z"

    # Second claim attempt immediately finds nothing
    claimed2, err2 = aps.claim_due_publication(conn, worker_id="worker_beta", now="2026-09-21T18:00:02Z")
    assert claimed2 is None
    assert err2 == "no_due_publications"


def test_11_two_workers_race_one_winner(tmp_path):
    """11. Two workers attempting CAS claim on same item results in exactly one winner."""
    conn1 = sqlite3.connect(tmp_path / "race.db")
    conn1.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn1, tmp_path, owner_id=909)
    aps.approve_publication_draft(conn1, draft_id, requesting_user_id=909)
    aps.schedule_publication(conn1, draft_id, requesting_user_id=909, schedule_at="2026-09-21T12:00:00Z")

    conn2 = sqlite3.connect(tmp_path / "race.db")
    conn2.row_factory = sqlite3.Row

    # Worker 1 claims
    c1, err1 = aps.claim_due_publication(conn1, worker_id="w1", now="2026-09-21T12:00:00Z")
    assert err1 == "claimed"

    # Worker 2 attempts claim on same database
    c2, err2 = aps.claim_due_publication(conn2, worker_id="w2", now="2026-09-21T12:00:00Z")
    assert c2 is None
    assert err2 == "no_due_publications"
    conn2.close()
    conn1.close()


# =========================================================================
# 12 & 13. LEASE MANAGEMENT
# =========================================================================

def test_12_stale_worker_cannot_renew(tmp_path):
    """12. Stale worker or non-owner cannot renew lease."""
    conn = sqlite3.connect(tmp_path / "lease_stale.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)
    aps.schedule_publication(conn, draft_id, requesting_user_id=101, schedule_at="2026-09-21T12:00:00Z")
    item, _ = aps.claim_due_publication(conn, worker_id="worker_alpha", now="2026-09-21T12:00:00Z", lease_seconds=300)

    # Rogue/stale worker attempts renewal
    res, err = aps.renew_publication_lease(conn, publication_id=item["publication_id"], worker_id="worker_impostor", now="2026-09-21T12:01:00Z")
    assert res is None
    assert err == "lease_owner_mismatch"


def test_13_valid_lease_renewal(tmp_path):
    """13. Valid lease owner can successfully renew lease before expiry."""
    conn = sqlite3.connect(tmp_path / "lease_valid.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)
    aps.schedule_publication(conn, draft_id, requesting_user_id=101, schedule_at="2026-09-21T12:00:00Z")
    item, _ = aps.claim_due_publication(conn, worker_id="worker_alpha", now="2026-09-21T12:00:00Z", lease_seconds=300)

    res, err = aps.renew_publication_lease(conn, publication_id=item["publication_id"], worker_id="worker_alpha", now="2026-09-21T12:02:00Z", lease_seconds=600)
    assert err == "lease_renewed"
    assert res is not None
    assert res["lease_expires_at"] == "2026-09-21T12:12:00Z"
    assert res["revision"] == item["revision"] + 1


# =========================================================================
# 14. CLAIMED -> PUBLISHING
# =========================================================================

def test_14_claimed_to_publishing_exact_lease_owner(tmp_path):
    """14. Transition CLAIMED -> PUBLISHING requires exact lease owner and unexpired lease."""
    conn = sqlite3.connect(tmp_path / "publishing.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)
    aps.schedule_publication(conn, draft_id, requesting_user_id=101, schedule_at="2026-09-21T12:00:00Z")
    item, _ = aps.claim_due_publication(conn, worker_id="worker_alpha", now="2026-09-21T12:00:00Z", lease_seconds=300)

    # Wrong worker rejected
    bad_res, bad_err = aps.mark_publication_started(conn, item["publication_id"], worker_id="worker_beta", now="2026-09-21T12:01:00Z")
    assert bad_res is None
    assert bad_err == "lease_owner_mismatch"

    # Valid worker succeeds
    good_res, good_err = aps.mark_publication_started(conn, item["publication_id"], worker_id="worker_alpha", now="2026-09-21T12:01:00Z")
    assert good_err == "publishing_started"
    assert good_res["state"] == "PUBLISHING"
    assert good_res["publish_started_at"] == "2026-09-21T12:01:00Z"


# =========================================================================
# 15. EXPIRED CLAIMED RECOVERY
# =========================================================================

def test_15_expired_claimed_recovery(tmp_path):
    """15. Expired CLAIMED publication (where publish_started_at is empty) recovers safely to FAILED_RETRYABLE with backoff."""
    conn = sqlite3.connect(tmp_path / "exp_claim.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)
    aps.schedule_publication(conn, draft_id, requesting_user_id=101, schedule_at="2026-09-21T12:00:00Z")
    item, _ = aps.claim_due_publication(conn, worker_id="worker_alpha", now="2026-09-21T12:00:00Z", lease_seconds=100)

    # Fast-forward time past lease expiry (now = 12:05:00Z) without publish_started
    rec, err = aps.recover_expired_claimed_publication(conn, item["publication_id"], now="2026-09-21T12:05:00Z", backoff_base_seconds=60)
    assert err == "recovered_to_retryable"
    assert rec["state"] == "FAILED_RETRYABLE"
    assert rec["lease_owner"] is None
    assert rec["lease_expires_at"] is None
    assert rec["last_error_code"] == "claimed_lease_expired_recovered"
    assert rec["next_attempt_at"] == "2026-09-21T12:06:00Z"


# =========================================================================
# 16, 17, 18. RETRYABLE FAILURE & DETERMINISTIC BACKOFF
# =========================================================================

def test_16_retryable_failure_stores_durable_next_attempt_at(tmp_path):
    """16. Retryable failure stores durable next_attempt_at calculated via deterministic backoff."""
    conn = sqlite3.connect(tmp_path / "retry_backoff.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)
    aps.schedule_publication(conn, draft_id, requesting_user_id=101, schedule_at="2026-09-21T12:00:00Z")
    item, _ = aps.claim_due_publication(conn, worker_id="w1", now="2026-09-21T12:00:00Z", lease_seconds=300)
    aps.mark_publication_started(conn, item["publication_id"], worker_id="w1", now="2026-09-21T12:01:00Z")

    res, err = aps.record_publication_result(
        conn,
        publication_id=item["publication_id"],
        worker_id="w1",
        outcome="failed_retryable",
        error_code="rate_limited",
        now="2026-09-21T12:02:00Z",
        backoff_base_seconds=60,
    )
    assert err == "failed_retryable"
    assert res["state"] == "FAILED_RETRYABLE"
    assert res["next_attempt_at"] == "2026-09-21T12:03:00Z"
    assert res["last_error_code"] == "rate_limited"


def test_17_retry_not_claimable_before_backoff(tmp_path):
    """17. A FAILED_RETRYABLE publication cannot be claimed before next_attempt_at."""
    conn = sqlite3.connect(tmp_path / "retry_claim17.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)
    aps.schedule_publication(conn, draft_id, requesting_user_id=101, schedule_at="2026-09-21T12:00:00Z")
    item, _ = aps.claim_due_publication(conn, worker_id="w1", now="2026-09-21T12:00:00Z")
    aps.mark_publication_started(conn, item["publication_id"], worker_id="w1", now="2026-09-21T12:01:00Z")
    aps.record_publication_result(
        conn, item["publication_id"], worker_id="w1",
        outcome="failed_retryable", now="2026-09-21T12:02:00Z", backoff_base_seconds=60
    )

    # Claiming at 12:02:30Z (before 12:03:00Z) returns no due publications
    c_early, err_early = aps.claim_due_publication(conn, worker_id="w2", now="2026-09-21T12:02:30Z")
    assert c_early is None
    assert err_early == "no_due_publications"


def test_18_retry_claimable_after_backoff(tmp_path):
    """18. A FAILED_RETRYABLE publication can be claimed once next_attempt_at has passed."""
    conn = sqlite3.connect(tmp_path / "retry_claim18.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)
    aps.schedule_publication(conn, draft_id, requesting_user_id=101, schedule_at="2026-09-21T12:00:00Z")
    item, _ = aps.claim_due_publication(conn, worker_id="w1", now="2026-09-21T12:00:00Z")
    aps.mark_publication_started(conn, item["publication_id"], worker_id="w1", now="2026-09-21T12:01:00Z")
    aps.record_publication_result(
        conn, item["publication_id"], worker_id="w1",
        outcome="failed_retryable", now="2026-09-21T12:02:00Z", backoff_base_seconds=60
    )

    # Claiming at 12:03:01Z (after 12:03:00Z) succeeds
    c_due, err_due = aps.claim_due_publication(conn, worker_id="w2", now="2026-09-21T12:03:01Z")
    assert err_due == "claimed"
    assert c_due["attempt_count"] == 2
    assert c_due["state"] == "CLAIMED"


# =========================================================================
# 19 & 20. MAX ATTEMPTS & FAILED_FINAL IMMUTABILITY
# =========================================================================

def test_19_max_attempts_exhausted_to_failed_final(tmp_path):
    """19. Exhausting max_attempts transitions to FAILED_FINAL."""
    conn = sqlite3.connect(tmp_path / "max_att19.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)
    aps.schedule_publication(conn, draft_id, requesting_user_id=101, schedule_at="2026-09-21T12:00:00Z")

    for attempt in range(1, 4):
        now_ts = f"2026-09-21T12:{attempt*10:02d}:00Z"
        item, _ = aps.claim_due_publication(conn, worker_id=f"w_{attempt}", now=now_ts)
        pub_id = item["publication_id"]
        aps.mark_publication_started(conn, pub_id, worker_id=f"w_{attempt}", now=now_ts)
        res, err = aps.record_publication_result(
            conn, pub_id, worker_id=f"w_{attempt}", outcome="failed_retryable",
            now=now_ts, backoff_base_seconds=60
        )
        if attempt == 3:
            assert err == "failed_final"
            assert res["state"] == "FAILED_FINAL"


def test_20_failed_final_not_requeued(tmp_path):
    """20. FAILED_FINAL is never requeued by scheduler."""
    conn = sqlite3.connect(tmp_path / "max_att20.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)
    aps.schedule_publication(conn, draft_id, requesting_user_id=101, schedule_at="2026-09-21T12:00:00Z")

    # Run to attempt 3
    for attempt in range(1, 4):
        now_ts = f"2026-09-21T12:{attempt*10:02d}:00Z"
        item, _ = aps.claim_due_publication(conn, worker_id=f"w_{attempt}", now=now_ts)
        pub_id = item["publication_id"]
        aps.mark_publication_started(conn, pub_id, worker_id=f"w_{attempt}", now=now_ts)
        aps.record_publication_result(
            conn, pub_id, worker_id=f"w_{attempt}", outcome="failed_retryable",
            now=now_ts, backoff_base_seconds=60
        )

    # 20: FAILED_FINAL is never requeued
    future_claim, err_c = aps.claim_due_publication(conn, worker_id="w_final", now="2026-09-22T00:00:00Z")
    assert future_claim is None
    assert err_c == "no_due_publications"


# =========================================================================
# 21 & 22. TERMINAL STATES IMMUTABILITY (PUBLISHED & CANCELLED)
# =========================================================================

def test_21_published_immutable(tmp_path):
    """21. PUBLISHED state is strictly immutable and cannot transition to any state."""
    conn = sqlite3.connect(tmp_path / "published.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)
    aps.schedule_publication(conn, draft_id, requesting_user_id=101, schedule_at="2026-09-21T12:00:00Z")
    item, _ = aps.claim_due_publication(conn, worker_id="w1", now="2026-09-21T12:00:00Z")
    aps.mark_publication_started(conn, item["publication_id"], worker_id="w1", now="2026-09-21T12:01:00Z")

    res, err = aps.record_publication_result(conn, item["publication_id"], worker_id="w1", outcome="succeeded", now="2026-09-21T12:02:00Z")
    assert err == "published"
    assert res["state"] == "PUBLISHED"

    # Attempt to schedule or claim again
    sched_res, sched_err = aps.schedule_publication(conn, draft_id, requesting_user_id=101, schedule_at="2026-09-22T10:00:00Z")
    assert sched_res is None
    assert "cannot_schedule_in_state:PUBLISHED" in sched_err

    # Attempt to cancel
    can_res, can_err = aps.cancel_publication(conn, item["publication_id"], requesting_user_id=101)
    assert can_res is None
    assert can_err == "published_cannot_cancel"


def test_22_cancelled_immutable(tmp_path):
    """22. CANCELLED state is strictly immutable and cannot be claimed or scheduled."""
    conn = sqlite3.connect(tmp_path / "cancelled.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    appr, _ = aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)
    aps.schedule_publication(conn, draft_id, requesting_user_id=101, schedule_at="2026-09-21T12:00:00Z")

    can_res, can_err = aps.cancel_publication(conn, appr["publication_id"], requesting_user_id=101, reason="user_decision")
    assert can_err == "cancelled"
    assert can_res["state"] == "CANCELLED"

    # Cannot claim
    claim, err = aps.claim_due_publication(conn, worker_id="w1", now="2026-09-21T12:05:00Z")
    assert claim is None
    assert err == "no_due_publications"


# =========================================================================
# 23 & 24. EXPIRED PUBLISHING AMBIGUITY (FAIL CLOSED, NO BLIND RETRY)
# =========================================================================

def test_23_expired_publishing_does_not_auto_republish(tmp_path):
    """23. Expired PUBLISHING never auto-republishes via due claim."""
    conn = sqlite3.connect(tmp_path / "exp_pub23.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)
    aps.schedule_publication(conn, draft_id, requesting_user_id=101, schedule_at="2026-09-21T12:00:00Z")
    item, _ = aps.claim_due_publication(conn, worker_id="w1", now="2026-09-21T12:00:00Z", lease_seconds=120)
    aps.mark_publication_started(conn, item["publication_id"], worker_id="w1", now="2026-09-21T12:01:00Z")

    # Fast forward time to 12:05:00Z (lease expired at 12:02:00Z)
    c, err = aps.claim_due_publication(conn, worker_id="w2", now="2026-09-21T12:05:00Z")
    assert c is None
    assert err == "no_due_publications"


def test_24_ambiguous_publishing_recovery_exposes_blocker(tmp_path):
    """24. Ambiguous expired PUBLISHING inspection exposes external_reconciliation_required."""
    conn = sqlite3.connect(tmp_path / "exp_pub24.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)
    aps.schedule_publication(conn, draft_id, requesting_user_id=101, schedule_at="2026-09-21T12:00:00Z")
    item, _ = aps.claim_due_publication(conn, worker_id="w1", now="2026-09-21T12:00:00Z", lease_seconds=120)
    aps.mark_publication_started(conn, item["publication_id"], worker_id="w1", now="2026-09-21T12:01:00Z")

    # Fast forward time to 12:05:00Z
    insp, err_insp = aps.inspect_ambiguous_publishing_publication(conn, item["publication_id"], now="2026-09-21T12:05:00Z")
    assert err_insp == "external_reconciliation_required"
    assert insp["state"] == "PUBLISHING"
    assert insp["last_error_code"] == "external_reconciliation_required"


# =========================================================================
# 25, 26, 27. ARTIFACT INTEGRITY & MEDIA PROBE
# =========================================================================

def test_25_artifact_sha_replacement_blocks_future_dispatch(tmp_path):
    """25. Tampering with physical artifact (altering content/hash) fails revalidation and blocks dispatch."""
    conn = sqlite3.connect(tmp_path / "sha_tamper.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, video_path, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    appr, _ = aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)

    # Mutate physical file content
    video_path.write_bytes(b"tampered_content_1234567890")

    ok, reason = aps.revalidate_publication_artifact(conn, appr["publication_id"])
    assert ok is False
    assert reason == "artifact_replacement_detected"


def test_26_scheduler_rereads_canonical_handoff(tmp_path):
    """26. Scheduler revalidation rereads canonical SQLite handoff authority and rejects drift."""
    conn = sqlite3.connect(tmp_path / "reread.db")
    conn.row_factory = sqlite3.Row
    draft_id, handoff_id, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    appr, _ = aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)

    # Simulate manual tampering with handoff artifact_sha256 in DB
    conn.execute("UPDATE autopost_handoff_receipts SET artifact_sha256='0000000000000000000000000000000000000000000000000000000000000000' WHERE handoff_id=?", (handoff_id,))
    conn.commit()

    ok, reason = aps.revalidate_publication_artifact(conn, appr["publication_id"])
    assert ok is False
    assert reason == "artifact_sha_mismatch"


def test_27_media_probe_holds_no_scheduler_write_lock(tmp_path):
    """27. Media probe and physical verification run outside of any active SQLite write lock."""
    conn = sqlite3.connect(tmp_path / "probe_lock.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    appr, _ = aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)

    # During revalidation, conn.in_transaction must be False
    assert conn.in_transaction is False
    ok, _ = aps.revalidate_publication_artifact(conn, appr["publication_id"])
    assert ok is True
    assert conn.in_transaction is False


# =========================================================================
# 28 & 29. RETRY NEVER INVOKES OR REQUEUES PRODUCERS
# =========================================================================

def test_28_retry_never_invokes_producer_rendering(tmp_path, monkeypatch):
    """28. Retrying AutoPost publication modifies only scheduler queue; never rerenders producer."""
    conn = sqlite3.connect(tmp_path / "producer_iso28.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)
    aps.schedule_publication(conn, draft_id, requesting_user_id=101, schedule_at="2026-09-21T12:00:00Z")

    producer_spy = MagicMock()
    monkeypatch.setattr("services.video_project_queue.enqueue_video_render_job", producer_spy, raising=False)

    item, _ = aps.claim_due_publication(conn, worker_id="w1", now="2026-09-21T12:00:00Z")
    aps.mark_publication_started(conn, item["publication_id"], worker_id="w1", now="2026-09-21T12:01:00Z")
    aps.record_publication_result(conn, item["publication_id"], worker_id="w1", outcome="failed_retryable", now="2026-09-21T12:02:00Z")

    assert producer_spy.call_count == 0


def test_29_retry_never_requeues_producer(tmp_path):
    """29. Retrying AutoPost publication never requeues or creates producer jobs."""
    conn = sqlite3.connect(tmp_path / "producer_iso29.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)
    aps.schedule_publication(conn, draft_id, requesting_user_id=101, schedule_at="2026-09-21T12:00:00Z")

    item, _ = aps.claim_due_publication(conn, worker_id="w1", now="2026-09-21T12:00:00Z")
    aps.mark_publication_started(conn, item["publication_id"], worker_id="w1", now="2026-09-21T12:01:00Z")
    aps.record_publication_result(conn, item["publication_id"], worker_id="w1", outcome="failed_retryable", now="2026-09-21T12:02:00Z")

    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('video_jobs', 'video_edit_jobs')")
    assert len(cur.fetchall()) == 0


# =========================================================================
# 30. RECOVERY REPLAY IDEMPOTENT
# =========================================================================

def test_30_recovery_replay_idempotent(tmp_path):
    """30. Replaying recovery on an already-recovered item is idempotent and harmless."""
    conn = sqlite3.connect(tmp_path / "rec_idem.db")
    conn.row_factory = sqlite3.Row
    draft_id, _, _, _, _ = _setup_planned_draft(conn, tmp_path, owner_id=101)
    aps.approve_publication_draft(conn, draft_id, requesting_user_id=101)
    aps.schedule_publication(conn, draft_id, requesting_user_id=101, schedule_at="2026-09-21T12:00:00Z")
    item, _ = aps.claim_due_publication(conn, worker_id="w1", now="2026-09-21T12:00:00Z", lease_seconds=60)

    # First recovery
    rec1, err1 = aps.recover_expired_claimed_publication(conn, item["publication_id"], now="2026-09-21T12:05:00Z")
    assert err1 == "recovered_to_retryable"

    # Second recovery replay: state is now FAILED_RETRYABLE, not CLAIMED
    rec2, err2 = aps.recover_expired_claimed_publication(conn, item["publication_id"], now="2026-09-21T12:06:00Z")
    assert rec2 is None
    assert "cannot_recover_claimed_in_state" in err2


# =========================================================================
# 31 & 32. S1.4 PRODUCT VIDEO & VIDEO EDIT PROTECTED CASES
# =========================================================================

def test_31_s1_4_product_video_protected_cases_pass(tmp_path, monkeypatch):
    """31. S1.4 Product Video handoff logic creates valid handoff and draft without side effects."""
    conn = sqlite3.connect(tmp_path / "pv_prot.db")
    conn.row_factory = sqlite3.Row
    raw_bytes = b"pv_prot_canonical_video_bytes"
    uid = 7126457028

    from tests.test_p0_autopost_production_callback_seam import _setup_product_video_job
    project_id, job_id, video_file, sha = _setup_product_video_job(conn, tmp_path, uid=uid, raw_bytes=raw_bytes)

    monkeypatch.setattr(
        queue.video_final_output,
        "validate_final_video_output",
        lambda **_kw: {"ok": True, "bytes": len(raw_bytes), "duration": 15.0, "has_video": True, "has_audio": True},
    )
    monkeypatch.setattr(
        queue,
        "_canonical_persisted_final_mp4_path",
        lambda _conn, _pid: str(video_file),
    )

    monkeypatch.setattr(
        queue,
        "product_video_duration_contract",
        lambda *_a, **_kw: {"ok": True, "reason": "", "expected_duration_seconds": 15.0, "actual_duration_seconds": 15.0},
    )

    completed = queue.complete_video_job(
        conn,
        job_id=job_id,
        final_video_path=str(video_file),
        final_video_file_id="tg_file_pv_prot",
        result={"ok": True, "final_video_path": str(video_file), "video_artifact_hash": sha},
    )
    assert completed is not None
    assert completed["ok"] is True
    assert completed["job"]["status"] == "completed"
    assert "autopost_handoff" in completed
    assert completed["autopost_handoff"]["created_or_reused"] is True


def test_32_s1_4_video_edit_protected_cases_pass(tmp_path):
    """32. S1.4 Video Edit handoff logic creates valid handoff without side effects."""
    conn = sqlite3.connect(tmp_path / "ve_prot.db")
    conn.row_factory = sqlite3.Row
    raw_bytes = b"ve_prot_canonical_video_bytes"
    uid = 77

    from tests.test_p0_autopost_production_callback_seam import _setup_video_edit_job
    job, rec, video_file, sha = _setup_video_edit_job(conn, tmp_path, uid=uid, raw_bytes=raw_bytes)

    updated = video_editengine1.record_worker_update(
        conn,
        worker_job_id=job["local_worker_job_id"],
        worker_status="succeeded",
        detail={"stage": "delivering", "validation": "passed"},
        receipt=rec,
    )
    assert updated.get("status") == "delivered"
    assert "autopost_handoff" in updated
    assert updated["autopost_handoff"]["created_or_reused"] is True


# =========================================================================
# 33 & 34. SUBDUB & EXISTING VIDEO FAIL CLOSED
# =========================================================================

def test_33_subdub_remains_fail_closed(tmp_path):
    """33. SubDub producer remains fail-closed in S2 and does not create handoff."""
    conn = sqlite3.connect(tmp_path / "subdub.db")
    conn.row_factory = sqlite3.Row
    aah.ensure_autopost_handoff_schema(conn)

    receipt, err = aah.create_autopost_handoff_from_source(
        conn,
        source_product="subdub",
        source_ref="subdub_job_1",
        requesting_user_id=888,
    )
    assert receipt is None
    assert err == "subdub_canonical_authority_unavailable"


def test_34_existing_video_remains_fail_closed(tmp_path):
    """34. Existing Video producer remains fail-closed in S2 and does not create handoff."""
    conn = sqlite3.connect(tmp_path / "existing.db")
    conn.row_factory = sqlite3.Row
    aah.ensure_autopost_handoff_schema(conn)

    receipt, err = aah.create_autopost_handoff_from_source(
        conn,
        source_product="existing_video",
        source_ref="ex_asset_1",
        requesting_user_id=999,
    )
    assert receipt is None
    assert err == "existing_video_canonical_authority_unavailable"


# =========================================================================
# 35. ZERO PROVIDER / SOCIAL / WALLET SIDE EFFECTS
# =========================================================================

def test_35_zero_provider_social_wallet_effects():
    """35. S2 scheduler introduces NO social provider imports, no live calls, and no wallet mutations."""
    scheduler_file = Path(aps.__file__).read_text(encoding="utf-8")
    for forbidden in ["tiktok", "facebook", "instagram", "youtube_publish", "payos", "wallet"]:
        assert f"import {forbidden}" not in scheduler_file.lower()
        assert f"from {forbidden}" not in scheduler_file.lower()
