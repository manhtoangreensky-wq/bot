from __future__ import annotations

import hashlib
import json
import sqlite3
from copy import deepcopy

import pytest

from services import video_editengine1, video_local_editing


def _conn(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE local_worker_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            command TEXT,
            job_type TEXT,
            status TEXT,
            provider TEXT,
            input_file_id TEXT,
            created_at TEXT,
            xu_cost INTEGER,
            admin_only INTEGER,
            updated_at TEXT
        )"""
    )
    return conn


def _job_input() -> dict:
    return {
        "user_id": 701,
        "chat_id": 702,
        "edit_session_id": "edit-safety-session",
        "source_file_id": "telegram-source-a",
        "source_metadata": {
            "ok": True,
            "duration_ms": 4_000,
            "manifest_revision": "probe-a",
        },
        "plan": {
            "trim": {"start_ms": 0, "end_ms": 4_000},
            "brightness_percent": 100,
            "concat_inputs": ["concat_1.mp4", "concat_2.mp4"],
            "logo_overlay": {"position": "top_right", "opacity": 1.0},
            "subtitle_file": "subtitle.srt",
        },
        "tail": {},
        "quality_tier_id": "local-free",
        "price_xu": 0,
        "worker_payload": {
            "local1_contract": 1,
            "local1_mode": "manual",
            "plan_schema_version": "manual-edit-v1",
            "source_file_id": "telegram-source-a",
            "source_video_hash": "a" * 64,
            "source_manifest": {"sha256": "a" * 64, "size_bytes": 4_096},
            "concat_sources": [
                {"file_id": "concat-a", "sha256": "b" * 64},
                {"file_id": "concat-b", "sha256": "c" * 64},
            ],
            "logo_source": {"file_id": "logo-a", "sha256": "d" * 64},
            "subtitle_source": {"file_id": "subtitle-a", "sha256": "e" * 64},
            "provider_call": False,
            "charge_policy": "free_local_tool",
            "price_xu": 0,
            "quoted_price_xu": 0,
            "state_revision": 3,
            "rights_confirmation": {
                "confirmed": True,
                "policy": "video_edit_rights_v1",
                "user_id": "701",
                "review_revision": 3,
                "confirmed_at_unix": 1_750_000_000,
            },
        },
    }


def _create(conn: sqlite3.Connection, payload: dict | None = None) -> dict:
    created = video_editengine1.create_job(conn, **(payload or _job_input()))
    conn.commit()
    return created


def _receipt() -> dict:
    return {
        "delivery_message_id": "1001",
        "delivery_file_id": "telegram-output-1",
        "source_video_path": "source.mp4",
        "source_sha256": "a" * 64,
        "output_path": "output.mp4",
        "output_sha256": "f" * 64,
        "output_size_bytes": 8_192,
        "ffprobe": {
            "ok": True,
            "has_video": True,
            "video_codec": "h264",
            "duration_ms": 4_000,
            "width": 1_280,
            "height": 720,
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        },
        "output_count": 1,
        "charge_policy": "free_local_tool",
        "charge_status": "not_required_free",
        "charged_xu": 0,
    }


def _artifact(index: int) -> dict:
    return {
        "index": index,
        "message_id": str(1_000 + index),
        "file_id": f"telegram-artifact-{index}",
        "size": 4_096,
        "sha256": f"{index:x}" * 64,
        "ffprobe": deepcopy(_receipt()["ffprobe"]),
    }


def _split_receipt() -> dict:
    artifacts = [_artifact(1), _artifact(2)]
    receipt = _receipt()
    receipt.update(
        delivery_message_id=artifacts[0]["message_id"],
        delivery_file_id=artifacts[0]["file_id"],
        output_path="part-1.mp4,part-2.mp4",
        output_size_bytes=sum(item["size"] for item in artifacts),
        output_count=len(artifacts),
        artifacts=artifacts,
    )
    return receipt


def _historic_v2_token(payload: dict) -> str:
    worker = payload["worker_payload"]
    material = {
        "user_id": str(payload["user_id"]),
        "edit_session_id": str(payload["edit_session_id"]),
        "plan": payload["plan"],
        "quality_tier_id": str(payload["quality_tier_id"]),
        "idempotency_schema_version": "video-edit-job-identity-v2",
        "plan_schema_version": worker["plan_schema_version"],
        "source_file_id": payload["source_file_id"],
        "source_video_hash": worker["source_video_hash"],
        "source_manifest": worker["source_manifest"],
        "concat_sources": worker["concat_sources"],
        "logo_source": worker["logo_source"],
        "subtitle_source": worker["subtitle_source"],
    }
    encoded = json.dumps(
        material,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _rewrite_as_historic_v2(
    conn: sqlite3.Connection,
    created: dict,
    payload: dict,
) -> str:
    token = _historic_v2_token(payload)
    worker_job_id = created["local_worker_job_id"]
    queued = json.loads(
        conn.execute(
            "SELECT input_file_id FROM local_worker_jobs WHERE id=?",
            (worker_job_id,),
        ).fetchone()[0]
    )
    queued["edit_idempotency_key"] = token
    conn.execute(
        "UPDATE local_worker_jobs SET input_file_id=? WHERE id=?",
        (json.dumps(queued, ensure_ascii=False, separators=(",", ":"), sort_keys=True), worker_job_id),
    )
    conn.execute(
        "UPDATE video_edit_jobs SET idempotency_key=? WHERE id=?",
        (token, created["edit_job_id"]),
    )
    conn.commit()
    return token


def test_video_edit_outbox_lease_rejects_live_competitor_and_terminal_update() -> None:
    conn = _conn()
    created = _create(conn)
    worker_job_id = created["local_worker_job_id"]
    acquired_at = "2030-01-02 03:04:05"
    first_expiry = "2030-01-02 03:09:05"

    assert conn.execute(
        "SELECT status,lease_owner,lease_expires_at FROM video_edit_outbox "
        "WHERE local_worker_job_id=?",
        (worker_job_id,),
    ).fetchone() == ("pending", "", "")
    assert video_editengine1.renew_worker_lease(
        conn,
        worker_job_id=worker_job_id,
        lease_owner="worker-a",
        now=acquired_at,
        lease_expires_at=first_expiry,
    ) is True
    assert conn.execute(
        "SELECT lease_owner,lease_expires_at FROM video_edit_outbox WHERE local_worker_job_id=?",
        (worker_job_id,),
    ).fetchone() == ("worker-a", first_expiry)

    assert video_editengine1.renew_worker_lease(
        conn,
        worker_job_id=worker_job_id,
        lease_owner="worker-b",
        now="2030-01-02 03:05:00",
        lease_expires_at="2030-01-02 03:10:00",
    ) is False
    assert conn.execute(
        "SELECT lease_owner,lease_expires_at FROM video_edit_outbox WHERE local_worker_job_id=?",
        (worker_job_id,),
    ).fetchone() == ("worker-a", first_expiry)

    conn.execute(
        "UPDATE video_edit_outbox SET status='running' WHERE local_worker_job_id=?",
        (worker_job_id,),
    )
    renewed_expiry = "2030-01-02 03:12:00"
    assert video_editengine1.renew_worker_lease(
        conn,
        worker_job_id=worker_job_id,
        lease_owner="worker-a",
        now="2030-01-02 03:06:00",
        lease_expires_at=renewed_expiry,
    ) is True
    assert conn.execute(
        "SELECT lease_owner,lease_expires_at FROM video_edit_outbox WHERE local_worker_job_id=?",
        (worker_job_id,),
    ).fetchone() == ("worker-a", renewed_expiry)

    replacement_expiry = "2030-01-02 03:20:00"
    assert video_editengine1.renew_worker_lease(
        conn,
        worker_job_id=worker_job_id,
        lease_owner="worker-b",
        now="2030-01-02 03:12:01",
        lease_expires_at=replacement_expiry,
    ) is True
    assert conn.execute(
        "SELECT lease_owner,lease_expires_at FROM video_edit_outbox WHERE local_worker_job_id=?",
        (worker_job_id,),
    ).fetchone() == ("worker-b", replacement_expiry)

    conn.execute(
        "UPDATE video_edit_jobs SET status='delivered' WHERE id=?",
        (created["edit_job_id"],),
    )
    assert video_editengine1.renew_worker_lease(
        conn,
        worker_job_id=worker_job_id,
        lease_owner="worker-b",
        now="2030-01-02 03:13:00",
        lease_expires_at="2030-01-02 03:25:00",
    ) is False
    assert conn.execute(
        "SELECT lease_owner,lease_expires_at FROM video_edit_outbox WHERE local_worker_job_id=?",
        (worker_job_id,),
    ).fetchone() == ("worker-b", replacement_expiry)

    conn.execute(
        "UPDATE video_edit_jobs SET status='queued' WHERE id=?",
        (created["edit_job_id"],),
    )
    for terminal_status in ("terminal_failed", "terminal_delivery_unknown"):
        conn.execute(
            "UPDATE video_edit_outbox SET status=? WHERE local_worker_job_id=?",
            (terminal_status, worker_job_id),
        )
        assert video_editengine1.renew_worker_lease(
            conn,
            worker_job_id=worker_job_id,
            lease_owner="worker-b",
            now="2030-01-02 03:13:00",
            lease_expires_at="2030-01-02 03:25:00",
        ) is False
        assert conn.execute(
            "SELECT status,lease_owner,lease_expires_at FROM video_edit_outbox "
            "WHERE local_worker_job_id=?",
            (worker_job_id,),
        ).fetchone() == (terminal_status, "worker-b", replacement_expiry)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"worker_job_id": 0, "lease_owner": "worker-a", "lease_expires_at": "2030-01-02 03:09:05"},
        {"worker_job_id": 1, "lease_owner": "", "lease_expires_at": "2030-01-02 03:09:05"},
        {"worker_job_id": 1, "lease_owner": "worker-a", "lease_expires_at": ""},
        {"worker_job_id": 1, "lease_owner": "worker-a", "lease_expires_at": "not-a-timestamp"},
    ],
)
def test_video_edit_outbox_lease_rejects_invalid_inputs_without_mutating_row(kwargs: dict) -> None:
    conn = _conn()
    created = _create(conn)
    kwargs["worker_job_id"] = (
        created["local_worker_job_id"] if kwargs["worker_job_id"] == 1 else kwargs["worker_job_id"]
    )

    assert video_editengine1.renew_worker_lease(
        conn,
        now="2030-01-02 03:04:05",
        **kwargs,
    ) is False
    assert conn.execute(
        "SELECT lease_owner,lease_expires_at FROM video_edit_outbox WHERE local_worker_job_id=?",
        (created["local_worker_job_id"],),
    ).fetchone() == ("", "")


def test_video_edit_stage_update_is_bounded_monotonic_and_terminal_fenced() -> None:
    conn = _conn()
    created = _create(conn)
    worker_job_id = created["local_worker_job_id"]
    edit_job_id = created["edit_job_id"]
    stages = (
        ("inspecting_input", 25),
        ("preparing_plan", 35),
        ("processing_video", 55),
        ("validating_output", 80),
        ("delivering", 90),
    )

    observed_progress = []
    for stage, expected_progress in stages:
        video_editengine1.record_worker_update(
            conn,
            worker_job_id=worker_job_id,
            worker_status="running",
            detail={"stage": stage},
            receipt={},
        )
        persisted = conn.execute(
            "SELECT status,progress_percent FROM video_edit_jobs WHERE id=?",
            (edit_job_id,),
        ).fetchone()
        assert persisted == ("rendering", expected_progress)
        observed_progress.append(persisted[1])
    assert observed_progress == sorted(observed_progress)

    # A replay or an arbitrary stage name must not roll the durable progress back.
    for rejected_stage in ("preparing_plan", "unbounded_worker_stage"):
        video_editengine1.record_worker_update(
            conn,
            worker_job_id=worker_job_id,
            worker_status="running",
            detail={"stage": rejected_stage},
            receipt={},
        )
        assert conn.execute(
            "SELECT status,progress_percent FROM video_edit_jobs WHERE id=?",
            (edit_job_id,),
        ).fetchone() == ("rendering", 90)

    video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="succeeded",
        detail={"stage": "delivering", "validation": "passed"},
        receipt=_receipt(),
    )
    assert conn.execute(
        "SELECT status,progress_percent FROM video_edit_jobs WHERE id=?",
        (edit_job_id,),
    ).fetchone() == ("delivered", 100)


@pytest.mark.parametrize("terminal_status", sorted(video_editengine1.TERMINAL_JOB_STATES))
def test_video_edit_terminal_stages_fence_running_updates(terminal_status: str) -> None:
    conn = _conn()
    created = _create(conn)
    worker_job_id = created["local_worker_job_id"]
    edit_job_id = created["edit_job_id"]
    initial_progress = 73
    initial_outbox_status = f"terminal_{terminal_status}"
    conn.execute(
        "UPDATE video_edit_jobs SET status=?,progress_percent=? WHERE id=?",
        (terminal_status, initial_progress, edit_job_id),
    )
    conn.execute(
        "UPDATE video_edit_outbox SET status=? WHERE local_worker_job_id=?",
        (initial_outbox_status, worker_job_id),
    )
    conn.commit()

    video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="running",
        detail={"stage": "processing_video"},
        receipt={},
    )

    assert conn.execute(
        "SELECT status,progress_percent FROM video_edit_jobs WHERE id=?",
        (edit_job_id,),
    ).fetchone() == (terminal_status, initial_progress)
    assert conn.execute(
        "SELECT status FROM video_edit_outbox WHERE local_worker_job_id=?",
        (worker_job_id,),
    ).fetchone() == (initial_outbox_status,)


def test_job_identity_changes_for_every_supplied_source_asset_and_plan_schema() -> None:
    conn = _conn()
    base = _job_input()
    first = _create(conn, base)
    duplicate = _create(conn, deepcopy(base))
    assert duplicate["created"] is False
    assert duplicate["idempotency_key"] == first["idempotency_key"]

    variants: list[dict] = []

    plan_schema = deepcopy(base)
    plan_schema["worker_payload"]["plan_schema_version"] = "manual-edit-v2"
    variants.append(plan_schema)

    source_file = deepcopy(base)
    source_file["source_file_id"] = "telegram-source-b"
    source_file["worker_payload"]["source_file_id"] = "telegram-source-b"
    variants.append(source_file)

    source_hash = deepcopy(base)
    source_hash["worker_payload"]["source_video_hash"] = "9" * 64
    variants.append(source_hash)

    source_manifest = deepcopy(base)
    source_manifest["worker_payload"]["source_manifest"]["sha256"] = "8" * 64
    variants.append(source_manifest)

    concat_order = deepcopy(base)
    concat_order["worker_payload"]["concat_sources"].reverse()
    variants.append(concat_order)

    logo = deepcopy(base)
    logo["worker_payload"]["logo_source"]["file_id"] = "logo-b"
    variants.append(logo)

    subtitle = deepcopy(base)
    subtitle["worker_payload"]["subtitle_source"]["file_id"] = "subtitle-b"
    variants.append(subtitle)

    created = [_create(conn, variant) for variant in variants]
    assert all(result["created"] is True for result in created)
    assert len({first["idempotency_key"], *(result["idempotency_key"] for result in created)}) == 8
    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 8
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 8


def test_exact_historic_v2_retry_reuses_the_original_job_without_rewriting() -> None:
    conn = _conn()
    payload = _job_input()
    created = _create(conn, payload)
    historic_token = _rewrite_as_historic_v2(conn, created, payload)

    retried = video_editengine1.create_job(conn, **deepcopy(payload))

    assert retried["created"] is False
    assert retried["edit_job_id"] == created["edit_job_id"]
    assert retried["local_worker_job_id"] == created["local_worker_job_id"]
    assert retried["idempotency_key"] == historic_token
    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 1
    assert conn.execute(
        "SELECT idempotency_key FROM video_edit_jobs WHERE id=?",
        (created["edit_job_id"],),
    ).fetchone()[0] == historic_token


def test_historic_v2_candidate_with_changed_v3_identity_fails_closed() -> None:
    conn = _conn()
    payload = _job_input()
    created = _create(conn, payload)
    _rewrite_as_historic_v2(conn, created, payload)
    changed = deepcopy(payload)
    changed["worker_payload"]["coverage_required"] = False

    with pytest.raises(ValueError, match="legacy_idempotency_identity_mismatch"):
        video_editengine1.create_job(conn, **changed)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 1


def test_corrupt_historic_v2_worker_payload_fails_closed_without_new_rows() -> None:
    conn = _conn()
    payload = _job_input()
    created = _create(conn, payload)
    _rewrite_as_historic_v2(conn, created, payload)
    conn.execute(
        "UPDATE local_worker_jobs SET input_file_id='not-json' WHERE id=?",
        (created["local_worker_job_id"],),
    )
    conn.commit()

    with pytest.raises(ValueError, match="legacy_idempotency_identity_unverifiable"):
        video_editengine1.create_job(conn, **deepcopy(payload))

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 1


def test_existing_idempotency_key_cannot_be_reused_for_another_delivery_chat() -> None:
    conn = _conn()
    base = _job_input()
    _create(conn, base)
    changed = deepcopy(base)
    changed["chat_id"] = 999

    with pytest.raises(ValueError, match="idempotency_identity_mismatch:chat_id"):
        video_editengine1.create_job(conn, **changed)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 1


def test_canonical_plan_and_worker_plan_cannot_diverge() -> None:
    conn = _conn()
    payload = _job_input()
    payload["worker_payload"]["manual_edit_plan"] = {
        "trim": {"start_ms": 0, "end_ms": 4_000},
        "brightness_percent": 180,
    }

    with pytest.raises(
        ValueError,
        match="worker_payload_identity_mismatch:manual_edit_plan",
    ):
        video_editengine1.create_job(conn, **payload)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("local1_contract", 2),
        ("quality_tier_id", "stale-tier"),
    ],
)
def test_worker_execution_contract_cannot_diverge_from_canonical_job(
    field: str,
    value,
) -> None:
    conn = _conn()
    payload = _job_input()
    payload["worker_payload"][field] = value

    with pytest.raises(ValueError, match=f"worker_payload_identity_mismatch:{field}"):
        video_editengine1.create_job(conn, **payload)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 0


def test_queued_worker_payload_is_stamped_from_the_canonical_job_contract() -> None:
    conn = _conn()
    payload = _job_input()
    created = _create(conn, payload)
    queued = json.loads(
        conn.execute(
            "SELECT input_file_id FROM local_worker_jobs WHERE id=?",
            (created["local_worker_job_id"],),
        ).fetchone()[0]
    )

    assert queued["manual_edit_plan"] == payload["plan"]
    assert queued["local1_contract"] == 1
    assert queued["quality_tier_id"] == payload["quality_tier_id"]


def test_existing_paid_idempotency_key_cannot_reuse_a_stale_quote_snapshot() -> None:
    conn = _conn()
    base = _job_input()
    base.update(
        tail={"quality_tier_id": "300", "pricing_snapshot": {"total_xu": 125}},
        quality_tier_id="300",
        price_xu=125,
    )
    base["worker_payload"].update(
        price_xu=125,
        quoted_price_xu=125,
        charge_policy="after_valid_mp4_delivery",
    )
    _create(conn, base)
    changed = deepcopy(base)
    changed.update(
        tail={"quality_tier_id": "300", "pricing_snapshot": {"total_xu": 130}},
        price_xu=130,
    )
    changed["worker_payload"].update(price_xu=130, quoted_price_xu=130)

    with pytest.raises(ValueError, match="idempotency_identity_mismatch:price_xu"):
        video_editengine1.create_job(conn, **changed)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 1


def _paid_payload() -> dict:
    payload = _job_input()
    payload.update(
        tail={"quality_tier_id": "300", "pricing_snapshot": {"total_xu": 125}},
        quality_tier_id="300",
        price_xu=125,
    )
    payload["worker_payload"].update(
        price_xu=125,
        quoted_price_xu=125,
        charge_policy="after_valid_mp4_delivery",
    )
    return payload


def test_paid_legacy_writer_without_mode_is_stamped_manual_before_queue() -> None:
    conn = _conn()
    payload = _paid_payload()
    payload["worker_payload"].pop("local1_mode")
    payload["worker_payload"]["split_ranges"] = []

    created = _create(conn, payload)
    queued = json.loads(
        conn.execute(
            "SELECT input_file_id FROM local_worker_jobs WHERE id=?",
            (created["local_worker_job_id"],),
        ).fetchone()[0]
    )

    assert queued["local1_mode"] == "manual"


def test_paid_legacy_writer_without_mode_rejects_split_intent_before_queue() -> None:
    conn = _conn()
    payload = _paid_payload()
    payload["worker_payload"].pop("local1_mode")
    payload["worker_payload"]["split_ranges"] = [
        {"index": 1, "start_ms": 0, "end_ms": 4_000}
    ]

    with pytest.raises(ValueError, match="paid_local_mode_missing_with_split"):
        video_editengine1.create_job(conn, **payload)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 0


def test_paid_legacy_writer_rejects_invalid_mode_before_queue() -> None:
    conn = _conn()
    payload = _paid_payload()
    payload["worker_payload"]["local1_mode"] = "provider_magic"

    with pytest.raises(ValueError, match="paid_local_mode_invalid"):
        video_editengine1.create_job(conn, **payload)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 0


def test_negative_price_is_rejected_instead_of_becoming_a_free_job() -> None:
    conn = _conn()
    payload = _job_input()
    payload["price_xu"] = -1

    with pytest.raises(ValueError, match="price_xu_invalid"):
        video_editengine1.create_job(conn, **payload)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 0


@pytest.mark.parametrize("bad_price", [-0.5, 1.5, "-0.5", "1.5"])
def test_fractional_prices_are_rejected_instead_of_truncated(bad_price) -> None:
    conn = _conn()
    payload = _job_input()
    payload["price_xu"] = bad_price

    with pytest.raises(ValueError, match="price_xu_invalid"):
        video_editengine1.create_job(conn, **payload)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 0


def test_local_free_job_rejects_an_unknown_execution_mode() -> None:
    conn = _conn()
    payload = _job_input()
    payload["worker_payload"]["local1_mode"] = "provider_magic"

    with pytest.raises(ValueError, match="local_free_mode_invalid"):
        video_editengine1.create_job(conn, **payload)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 0


@pytest.mark.parametrize(
    "rights",
    [
        None,
        {},
        {
            "confirmed": False,
            "policy": "video_edit_rights_v1",
            "user_id": "701",
            "review_revision": 3,
            "confirmed_at_unix": 1_750_000_000,
        },
        {
            "confirmed": True,
            "policy": "wrong_policy",
            "user_id": "701",
            "review_revision": 3,
            "confirmed_at_unix": 1_750_000_000,
        },
        {
            "confirmed": True,
            "policy": "video_edit_rights_v1",
            "user_id": "999",
            "review_revision": 3,
            "confirmed_at_unix": 1_750_000_000,
        },
        {
            "confirmed": True,
            "policy": "video_edit_rights_v1",
            "user_id": "701",
            "review_revision": 0,
            "confirmed_at_unix": 1_750_000_000,
        },
        {
            "confirmed": True,
            "policy": "video_edit_rights_v1",
            "user_id": "701",
            "review_revision": 3,
            "confirmed_at_unix": 0,
        },
    ],
)
def test_local_free_job_requires_valid_durable_rights_confirmation(
    rights: dict | None,
) -> None:
    conn = _conn()
    payload = _job_input()
    if rights is None:
        payload["worker_payload"].pop("rights_confirmation")
    else:
        payload["worker_payload"]["rights_confirmation"] = rights

    with pytest.raises(ValueError, match="local_free_rights_confirmation_invalid"):
        video_editengine1.create_job(conn, **payload)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 0


def test_local_free_rights_confirmation_is_bound_to_the_review_revision() -> None:
    conn = _conn()
    payload = _job_input()
    payload["worker_payload"]["state_revision"] = 4

    with pytest.raises(ValueError, match="local_free_rights_confirmation_invalid"):
        video_editengine1.create_job(conn, **payload)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("plan_patch", "asset_patch"),
    [
        ({"brightness_percent": 120}, {}),
        ({}, {"concat_sources": [{"file_id": "concat-only"}]}),
        ({}, {"logo_source": {"file_id": "logo-only"}}),
        ({}, {"subtitle_source": {"file_id": "subtitle-only"}}),
    ],
)
def test_local_free_split_job_rejects_each_manual_operation_or_asset_independently(
    plan_patch: dict,
    asset_patch: dict,
) -> None:
    conn = _conn()
    payload = _job_input()
    payload["plan"] = video_local_editing.neutral_split_manual_plan()
    payload["plan"].update(plan_patch)
    payload["worker_payload"].update(
        local1_mode="split",
        manual_edit_plan=deepcopy(payload["plan"]),
        concat_sources=[],
        logo_source={},
        subtitle_source={},
        split_mode="custom",
        split_ranges=[
            {"index": 1, "start_ms": 0, "end_ms": 2_000},
            {"index": 2, "start_ms": 2_000, "end_ms": 4_000},
        ],
        coverage_required=True,
    )
    payload["worker_payload"].update(asset_patch)

    with pytest.raises(ValueError, match="local_free_split_manual_conflict"):
        video_editengine1.create_job(conn, **payload)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 0


def test_local_free_split_job_rejects_unknown_manual_plan_fields() -> None:
    conn = _conn()
    payload = _job_input()
    payload["plan"] = video_local_editing.neutral_split_manual_plan()
    payload["plan"]["unknown_split_operation"] = True
    payload["worker_payload"].update(
        local1_mode="split",
        manual_edit_plan=deepcopy(payload["plan"]),
        concat_sources=[],
        logo_source={},
        subtitle_source={},
        split_mode="custom",
        split_ranges=[
            {"index": 1, "start_ms": 0, "end_ms": 2_000},
            {"index": 2, "start_ms": 2_000, "end_ms": 4_000},
        ],
        coverage_required=True,
    )

    with pytest.raises(ValueError, match="local_free_split_manual_conflict"):
        video_editengine1.create_job(conn, **payload)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("plan_patch", "asset_patch"),
    [
        ({"concat_inputs": ["video_1"]}, {}),
        (
            {"concat_inputs": ["video_1", "video_2"]},
            {"concat_sources": [{"file_id": "concat-only"}]},
        ),
        ({"logo_overlay": {"position": "top_right", "opacity": 1.0}}, {}),
        ({"subtitle_file": "subtitle.srt"}, {}),
        ({}, {"concat_sources": [{"file_id": "concat-only"}]}),
        ({}, {"logo_source": {"file_id": "logo-only"}}),
        ({}, {"subtitle_source": {"file_id": "subtitle-only"}}),
    ],
)
def test_local_free_manual_job_rejects_unbound_plan_assets(
    plan_patch: dict,
    asset_patch: dict,
) -> None:
    conn = _conn()
    payload = _job_input()
    payload["plan"] = {
        "trim": {"start_ms": 0, "end_ms": 4_000},
        "brightness_percent": 110,
        **plan_patch,
    }
    payload["worker_payload"].update(
        manual_edit_plan=deepcopy(payload["plan"]),
        concat_sources=[],
        logo_source={},
        subtitle_source={},
    )
    payload["worker_payload"].update(asset_patch)

    with pytest.raises(ValueError, match="local_free_asset_contract_invalid"):
        video_editengine1.create_job(conn, **payload)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 0


def test_local_free_manual_job_requires_an_observable_edit() -> None:
    conn = _conn()
    payload = _job_input()
    payload["plan"] = {
        "trim": {"start_ms": 0, "end_ms": 4_000},
        "brightness_percent": 100,
    }
    payload["worker_payload"].update(
        manual_edit_plan=deepcopy(payload["plan"]),
        concat_sources=[],
        logo_source={},
        subtitle_source={},
    )

    with pytest.raises(ValueError, match="local_free_edit_operation_missing"):
        video_editengine1.create_job(conn, **payload)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 0


def test_local_free_job_rejects_unknown_plan_fields_before_queue_insert() -> None:
    conn = _conn()
    payload = _job_input()
    payload["plan"] = {"provider_magic_effect": True}
    payload["worker_payload"].update(
        concat_sources=[],
        logo_source={},
        subtitle_source={},
    )

    with pytest.raises(
        ValueError,
        match="local_free_edit_plan_invalid:unknown_edit_plan_field:provider_magic_effect",
    ):
        video_editengine1.create_job(conn, **payload)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 0


def test_local_free_job_rejects_the_legacy_source_alias() -> None:
    conn = _conn()
    payload = _job_input()
    payload["plan"] = {
        "source": "legacy-source.mp4",
        "trim": {"start_ms": 0, "end_ms": 4_000},
    }
    payload["worker_payload"].update(
        concat_sources=[],
        logo_source={},
        subtitle_source={},
    )

    with pytest.raises(ValueError, match="local_free_legacy_plan_invalid"):
        video_editengine1.create_job(conn, **payload)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 0


def test_local_free_split_job_rejects_malformed_ranges_before_queue_insert() -> None:
    conn = _conn()
    payload = _job_input()
    payload["plan"] = {}
    payload["worker_payload"].update(
        local1_mode="split",
        concat_sources=[],
        logo_source={},
        subtitle_source={},
        split_ranges=[
            {"index": 1, "start_ms": 0, "end_ms": 3_000},
            {"index": 2, "start_ms": 2_500, "end_ms": 4_000},
        ],
        coverage_required=True,
    )

    with pytest.raises(ValueError, match="local_free_split_plan_invalid"):
        video_editengine1.create_job(conn, **payload)

    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 0


def test_delivery_commit_ambiguity_is_terminal_and_never_retried_or_charged() -> None:
    conn = _conn()
    payload = _job_input()
    payload.update(
        tail={"quality_tier_id": "300", "pricing_snapshot": {"total_xu": 300}},
        quality_tier_id="300",
        price_xu=300,
    )
    payload["worker_payload"].update(
        price_xu=300,
        quoted_price_xu=300,
        charge_policy="after_valid_mp4_delivery",
    )
    created = _create(conn, payload)
    worker_job_id = created["local_worker_job_id"]

    uncertain = video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="delivery_unknown",
        detail={"reason": "telegram_delivery_receipt_commit_uncertain"},
        receipt={},
    )
    conn.commit()

    assert uncertain["status"] == "delivery_unknown"
    assert uncertain["receipt_state"] == "delivery_unknown"
    assert uncertain["charge_state"] == "not_charged"
    assert uncertain["charged_xu"] == 0
    assert uncertain["blocker"] == "telegram_delivery_receipt_commit_uncertain"
    assert video_editengine1.claim_charge(conn, worker_job_id=worker_job_id) is False
    assert conn.execute(
        "SELECT status,terminal_reason FROM video_edit_outbox WHERE local_worker_job_id=?",
        (worker_job_id,),
    ).fetchone() == (
        "terminal_delivery_unknown",
        "telegram_delivery_receipt_commit_uncertain",
    )

    late_success = video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="succeeded",
        detail={"validation": "passed"},
        receipt=_receipt(),
    )
    conn.commit()
    assert late_success == uncertain
    assert conn.execute("SELECT COUNT(*) FROM video_edit_outbox WHERE status='pending'").fetchone()[0] == 0


def test_late_worker_failure_cannot_overwrite_a_charged_terminal_job() -> None:
    conn = _conn()
    payload = _job_input()
    payload.update(
        tail={"quality_tier_id": "300", "pricing_snapshot": {"total_xu": 125}},
        quality_tier_id="300",
        price_xu=125,
    )
    payload["worker_payload"].update(
        price_xu=125,
        quoted_price_xu=125,
        charge_policy="after_valid_mp4_delivery",
    )
    created = _create(conn, payload)
    receipt = _receipt()
    receipt.update(
        charge_policy="after_valid_mp4_delivery",
        charge_status="pending_post_delivery",
    )
    delivered = video_editengine1.record_worker_update(
        conn,
        worker_job_id=created["local_worker_job_id"],
        worker_status="succeeded",
        detail={"validation": "passed"},
        receipt=receipt,
    )
    assert delivered["status"] == "delivered"
    assert video_editengine1.claim_charge(
        conn,
        worker_job_id=created["local_worker_job_id"],
    ) is True
    charged = video_editengine1.mark_charge_result(
        conn,
        worker_job_id=created["local_worker_job_id"],
        ok=True,
        charged_xu=125,
    )

    late_failure = video_editengine1.record_worker_update(
        conn,
        worker_job_id=created["local_worker_job_id"],
        worker_status="failed",
        detail={"reason": "stale-worker-failure"},
        receipt={},
    )

    assert late_failure == charged
    assert late_failure["status"] == "charged"
    assert late_failure["charge_state"] == "charged"
    assert late_failure["charged_xu"] == 125
    assert conn.execute(
        "SELECT status FROM video_edit_outbox WHERE local_worker_job_id=?",
        (created["local_worker_job_id"],),
    ).fetchone()[0] == "delivered"


def test_legacy_key_call_and_positive_price_rows_remain_supported() -> None:
    legacy_args = {
        "user_id": 17,
        "edit_session_id": "legacy-session",
        "plan": {"trim": {"start_ms": 0, "end_ms": 1_000}},
        "quality_tier_id": "300",
    }
    assert video_editengine1.stable_idempotency_key(**legacy_args) == video_editengine1.stable_idempotency_key(
        **legacy_args
    )

    conn = _conn()
    payload = _job_input()
    payload.update(
        tail={"quality_tier_id": "300", "pricing_snapshot": {"total_xu": 125}},
        quality_tier_id="300",
        price_xu=125,
    )
    payload["worker_payload"].update(
        price_xu=125,
        quoted_price_xu=125,
        charge_policy="after_valid_mp4_delivery",
    )
    created = _create(conn, payload)
    row = video_editengine1.get_job_by_worker_id(conn, created["local_worker_job_id"])
    assert row["price_xu"] == 125
    assert row["quality_tier_id"] == "300"
    assert row["tail"] == payload["tail"]


@pytest.mark.parametrize(
    "worker_patch",
    [
        {"price_xu": 0, "quoted_price_xu": 0, "charge_policy": "free_local_tool"},
        {"price_xu": 125, "quoted_price_xu": 0, "charge_policy": "after_valid_mp4_delivery"},
        {"price_xu": 125, "quoted_price_xu": 125, "charge_policy": "free_local_tool"},
        {"price_xu": 125, "quoted_price_xu": 125, "charge_policy": "after_valid_mp4_delivery", "provider_call": True},
    ],
)
def test_positive_legacy_writer_rejects_mismatched_worker_billing_truth(worker_patch: dict) -> None:
    conn = _conn()
    payload = _job_input()
    payload.update(
        tail={"quality_tier_id": "300", "pricing_snapshot": {"total_xu": 125}},
        quality_tier_id="300",
        price_xu=125,
    )
    payload["worker_payload"].update(worker_patch)
    with pytest.raises(ValueError, match="paid_local_contract_invalid"):
        video_editengine1.create_job(conn, **payload)


def test_local_free_contract_stays_zero_cost_with_no_tail_or_charge() -> None:
    conn = _conn()
    created = _create(conn)
    row = video_editengine1.get_job_by_worker_id(conn, created["local_worker_job_id"])
    worker_price = conn.execute(
        "SELECT xu_cost FROM local_worker_jobs WHERE id=?",
        (created["local_worker_job_id"],),
    ).fetchone()[0]

    assert row["price_xu"] == 0
    assert row["quality_tier_id"] == "local-free"
    assert row["tail"] == {}
    assert row["charge_state"] == "not_charged"
    assert worker_price == 0


@pytest.mark.parametrize(
    "mutate",
    [
        lambda receipt: receipt.pop("output_count"),
        lambda receipt: receipt.__setitem__("output_count", 0),
        lambda receipt: receipt.__setitem__("output_sha256", "not-a-sha256"),
        lambda receipt: receipt.__setitem__("output_sha256", int("1" * 64)),
        lambda receipt: receipt.__setitem__("source_sha256", "bad-source-hash"),
        lambda receipt: receipt.__setitem__("source_sha256", "9" * 64),
        lambda receipt: receipt.__setitem__("output_path", "output.txt"),
        lambda receipt: receipt.__setitem__("ffprobe", {"ok": True}),
        lambda receipt: receipt.__setitem__("ffprobe", {"ok": True, "has_video": True, "video_codec": "vp9"}),
        lambda receipt: receipt["ffprobe"].__setitem__("duration_ms", 0),
        lambda receipt: receipt["ffprobe"].__setitem__("duration_ms", True),
        lambda receipt: receipt["ffprobe"].__setitem__("width", 0),
        lambda receipt: receipt["ffprobe"].__setitem__("width", True),
        lambda receipt: receipt["ffprobe"].__setitem__("format_name", "matroska,webm"),
        lambda receipt: receipt.__setitem__("output_size_bytes", True),
        lambda receipt: receipt.__setitem__("charge_policy", "after_valid_mp4_delivery"),
        lambda receipt: receipt.__setitem__("charge_status", "pending_post_delivery"),
        lambda receipt: receipt.__setitem__("charged_xu", 1),
        lambda receipt: receipt.__setitem__("artifacts", [{"index": 1, "message_id": "partial"}]),
        lambda receipt: receipt.__setitem__(
            "artifacts",
            [{
                "index": 1,
                "message_id": "message-1",
                "file_id": "file-1",
                "size": 8_192,
                "sha256": "f" * 64,
                "ffprobe": [1],
            }],
        ),
    ],
)
def test_success_receipt_fails_closed_without_exact_mp4_hash_and_probe_evidence(mutate) -> None:
    conn = _conn()
    created = _create(conn)
    receipt = _receipt()
    mutate(receipt)

    result = video_editengine1.record_worker_update(
        conn,
        worker_job_id=created["local_worker_job_id"],
        worker_status="succeeded",
        detail={"validation": "passed"},
        receipt=receipt,
    )
    conn.commit()

    assert result["status"] == "failed_no_charge"
    assert result["blocker"] == "delivery_receipt_invalid"
    assert result["charge_state"] == "not_charged"
    assert result["charged_xu"] == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("delivery_message_id", True),
        ("delivery_message_id", 0),
        ("delivery_message_id", "not-a-message-id"),
        ("delivery_message_id", {"id": 1001}),
        ("delivery_file_id", True),
        ("delivery_file_id", 1001),
        ("delivery_file_id", "   "),
        ("delivery_file_id", "file id with spaces"),
        ("delivery_file_id", "file-id\u200b"),
    ],
)
def test_success_receipt_rejects_malformed_telegram_identity(
    field: str,
    value,
) -> None:
    conn = _conn()
    created = _create(conn)
    receipt = _receipt()
    receipt[field] = value

    result = video_editengine1.record_worker_update(
        conn,
        worker_job_id=created["local_worker_job_id"],
        worker_status="succeeded",
        detail={"validation": "passed"},
        receipt=receipt,
    )
    conn.commit()

    assert result["status"] == "failed_no_charge"
    assert result["blocker"] == "delivery_receipt_invalid"
    assert result["receipt_state"] == "not_created"
    assert result["charge_state"] == "not_charged"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda receipt: receipt["artifacts"][0].__setitem__("message_id", True),
        lambda receipt: receipt["artifacts"][0].__setitem__(
            "message_id", "not-a-message-id"
        ),
        lambda receipt: receipt["artifacts"][0].__setitem__("file_id", True),
        lambda receipt: receipt["artifacts"][0].__setitem__("file_id", "bad file id"),
        lambda receipt: receipt["artifacts"][0].__setitem__("file_id", "file-id\u200b"),
        lambda receipt: receipt["artifacts"][0].__setitem__(
            "delivery_message_id", "9999"
        ),
        lambda receipt: receipt["artifacts"][0].__setitem__(
            "delivery_file_id", "different-file-id"
        ),
        lambda receipt: receipt["artifacts"][1].__setitem__(
            "message_id", receipt["artifacts"][0]["message_id"]
        ),
        lambda receipt: receipt["artifacts"][1].__setitem__(
            "file_id", receipt["artifacts"][0]["file_id"]
        ),
    ],
)
def test_split_receipt_rejects_malformed_or_duplicate_artifact_identity(
    mutate,
) -> None:
    conn = _conn()
    created = _create(conn)
    receipt = _split_receipt()
    mutate(receipt)

    result = video_editengine1.record_worker_update(
        conn,
        worker_job_id=created["local_worker_job_id"],
        worker_status="succeeded",
        detail={"validation": "passed"},
        receipt=receipt,
    )

    assert result["status"] == "failed_no_charge"
    assert result["blocker"] == "delivery_receipt_invalid"
    assert result["receipt_state"] == "not_created"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("delivery_message_id", "1002"),
        ("delivery_message_id", "1001,1002"),
        ("delivery_file_id", "telegram-artifact-2"),
        ("delivery_file_id", "telegram-artifact-1,telegram-artifact-2"),
    ],
)
def test_split_receipt_binds_top_level_identity_to_first_artifact(
    field: str,
    value: str,
) -> None:
    conn = _conn()
    created = _create(conn)
    receipt = _split_receipt()
    receipt[field] = value

    result = video_editengine1.record_worker_update(
        conn,
        worker_job_id=created["local_worker_job_id"],
        worker_status="succeeded",
        detail={"validation": "passed"},
        receipt=receipt,
    )

    assert result["status"] == "failed_no_charge"
    assert result["blocker"] == "delivery_receipt_invalid"


def test_claim_charge_revalidates_persisted_delivery_evidence() -> None:
    conn = _conn()
    payload = _job_input()
    payload.update(
        tail={"quality_tier_id": "300", "pricing_snapshot": {"total_xu": 125}},
        quality_tier_id="300",
        price_xu=125,
    )
    payload["worker_payload"].update(
        price_xu=125,
        quoted_price_xu=125,
        charge_policy="after_valid_mp4_delivery",
    )
    created = _create(conn, payload)
    receipt = _receipt()
    receipt.update(
        charge_policy="after_valid_mp4_delivery",
        charge_status="pending_post_delivery",
    )
    delivered = video_editengine1.record_worker_update(
        conn,
        worker_job_id=created["local_worker_job_id"],
        worker_status="succeeded",
        detail={"validation": "passed"},
        receipt=receipt,
    )
    assert delivered["status"] == "delivered"

    conn.execute(
        "UPDATE video_edit_jobs SET delivery_file_id='corrupt file id' WHERE local_worker_job_id=?",
        (created["local_worker_job_id"],),
    )

    assert video_editengine1.claim_charge(
        conn,
        worker_job_id=created["local_worker_job_id"],
    ) is False
    assert video_editengine1.get_job_by_worker_id(
        conn,
        created["local_worker_job_id"],
    )["charge_state"] == "not_charged"


def test_valid_paid_split_receipt_can_be_claimed_exactly_once() -> None:
    conn = _conn()
    payload = _paid_payload()
    created = _create(conn, payload)
    receipt = _split_receipt()
    receipt.update(
        charge_policy="after_valid_mp4_delivery",
        charge_status="pending_post_delivery",
    )

    delivered = video_editengine1.record_worker_update(
        conn,
        worker_job_id=created["local_worker_job_id"],
        worker_status="succeeded",
        detail={"validation": "passed"},
        receipt=receipt,
    )

    assert delivered["status"] == "delivered"
    assert video_editengine1.claim_charge(
        conn,
        worker_job_id=created["local_worker_job_id"],
    ) is True
    assert video_editengine1.claim_charge(
        conn,
        worker_job_id=created["local_worker_job_id"],
    ) is False


def test_claim_charge_rejects_corrupt_persisted_artifact_json() -> None:
    conn = _conn()
    payload = _paid_payload()
    created = _create(conn, payload)
    receipt = _split_receipt()
    receipt.update(
        charge_policy="after_valid_mp4_delivery",
        charge_status="pending_post_delivery",
    )
    delivered = video_editengine1.record_worker_update(
        conn,
        worker_job_id=created["local_worker_job_id"],
        worker_status="succeeded",
        detail={"validation": "passed"},
        receipt=receipt,
    )
    assert delivered["status"] == "delivered"
    conn.execute(
        "UPDATE video_edit_jobs SET artifact_receipts_json='not-json' WHERE local_worker_job_id=?",
        (created["local_worker_job_id"],),
    )

    assert video_editengine1.claim_charge(
        conn,
        worker_job_id=created["local_worker_job_id"],
    ) is False
