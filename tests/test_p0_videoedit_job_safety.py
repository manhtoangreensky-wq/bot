from __future__ import annotations

import sqlite3
from copy import deepcopy

from services import video_editengine1


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
        },
        "tail": {},
        "quality_tier_id": "local-free",
        "price_xu": 0,
        "worker_payload": {
            "local1_contract": 1,
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
        },
    }


def _create(conn: sqlite3.Connection, payload: dict | None = None) -> dict:
    created = video_editengine1.create_job(conn, **(payload or _job_input()))
    conn.commit()
    return created


def _receipt() -> dict:
    return {
        "delivery_message_id": "telegram-message-1",
        "delivery_file_id": "telegram-output-1",
        "source_video_path": "source.mp4",
        "source_sha256": "a" * 64,
        "output_path": "output.mp4",
        "output_sha256": "f" * 64,
        "output_size_bytes": 8_192,
        "ffprobe": {"ok": True, "has_video": True, "video_codec": "h264"},
    }


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


def test_delivery_commit_ambiguity_is_terminal_and_never_retried_or_charged() -> None:
    conn = _conn()
    payload = _job_input()
    payload.update(
        tail={"quality_tier_id": "300", "pricing_snapshot": {"total_xu": 300}},
        quality_tier_id="300",
        price_xu=300,
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
    created = _create(conn, payload)
    row = video_editengine1.get_job_by_worker_id(conn, created["local_worker_job_id"])
    assert row["price_xu"] == 125
    assert row["quality_tier_id"] == "300"
    assert row["tail"] == payload["tail"]


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
