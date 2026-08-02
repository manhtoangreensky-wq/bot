from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from services import video_editengine1


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
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


def _create(conn: sqlite3.Connection, *, session: str = "local-session") -> dict:
    return video_editengine1.create_job(
        conn,
        user_id=77,
        chat_id=88,
        edit_session_id=session,
        source_file_id="telegram-source",
        source_metadata={"ok": True, "duration_ms": 4_000, "has_audio": True},
        plan={"input_video": "", "trim": {"start_ms": 0, "end_ms": 4_000}, "brightness_percent": 110},
        tail={},
        quality_tier_id="local-free",
        price_xu=0,
        worker_payload={
            "source_file_id": "telegram-source",
            "source_file_name": "source.mp4",
            "local1_mode": "manual",
            "manual_edit_plan": {"trim": {"start_ms": 0, "end_ms": 4_000}, "brightness_percent": 110},
            "price_xu": 0,
            "quoted_price_xu": 0,
            "charge_policy": "free_local_tool",
            "provider_call": False,
            "state_revision": 3,
            "rights_confirmation": {
                "confirmed": True,
                "policy": "video_edit_rights_v1",
                "user_id": "77",
                "review_revision": 3,
                "confirmed_at_unix": 1_750_000_000,
            },
        },
    )


def _receipt() -> dict:
    return {
        "delivery_message_id": "1001",
        "delivery_file_id": "telegram-output-1",
        "source_video_path": "source.mp4",
        "source_sha256": "a" * 64,
        "output_path": "output.mp4",
        "output_sha256": "b" * 64,
        "output_size_bytes": 4096,
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


def test_local_free_job_has_exact_zero_price_contract_and_is_idempotent() -> None:
    conn = _conn()
    first = _create(conn)
    conn.commit()
    second = _create(conn)
    conn.commit()

    assert first["created"] is True
    assert second["created"] is False
    assert conn.execute("SELECT COUNT(*) FROM local_worker_jobs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 1
    row = video_editengine1.get_job_by_worker_id(conn, first["local_worker_job_id"])
    assert row["quality_tier_id"] == "local-free"
    assert row["price_xu"] == 0
    assert row["tail"] == {}


def test_split_ranges_are_part_of_the_job_idempotency_identity() -> None:
    conn = _conn()
    common = {
        "user_id": 77,
        "chat_id": 88,
        "edit_session_id": "same-split-session",
        "source_file_id": "telegram-source",
        "source_metadata": {"ok": True, "duration_ms": 6_000, "has_audio": True},
        "plan": {"input_video": "", "trim": {"start_ms": 0, "end_ms": 0}},
        "tail": {},
        "quality_tier_id": "local-free",
        "price_xu": 0,
    }

    def payload(ranges: list[dict]) -> dict:
        return {
            "local1_contract": 1,
            "local1_mode": "split",
            "plan_schema_version": "video-edit-plan-v1",
            "source_file_id": "telegram-source",
            "manual_edit_plan": {},
            "split_mode": "custom",
            "split_ranges": ranges,
            "coverage_required": True,
            "price_xu": 0,
            "quoted_price_xu": 0,
            "charge_policy": "free_local_tool",
            "provider_call": False,
            "state_revision": 3,
            "rights_confirmation": {
                "confirmed": True,
                "policy": "video_edit_rights_v1",
                "user_id": "77",
                "review_revision": 3,
                "confirmed_at_unix": 1_750_000_000,
            },
        }

    first = video_editengine1.create_job(
        conn,
        **common,
        worker_payload=payload([
            {"index": 1, "start_ms": 0, "end_ms": 3_000},
            {"index": 2, "start_ms": 3_000, "end_ms": 6_000},
        ]),
    )
    conn.commit()
    second = video_editengine1.create_job(
        conn,
        **common,
        worker_payload=payload([
            {"index": 1, "start_ms": 0, "end_ms": 2_000},
            {"index": 2, "start_ms": 2_000, "end_ms": 6_000},
        ]),
    )
    conn.commit()

    assert first["created"] is True
    assert second["created"] is True
    assert first["idempotency_key"] != second["idempotency_key"]
    assert conn.execute("SELECT COUNT(*) FROM video_edit_jobs").fetchone()[0] == 2


def test_zero_price_requires_local_free_tier_and_empty_tail() -> None:
    conn = _conn()
    with pytest.raises(ValueError, match="local_free_contract_invalid"):
        video_editengine1.create_job(
            conn,
            user_id=1,
            chat_id=1,
            edit_session_id="bad-tier",
            source_file_id="source",
            source_metadata={"ok": True},
            plan={},
            tail={"pricing_snapshot": {"total_xu": 0}},
            quality_tier_id="0",
            price_xu=0,
            worker_payload={"provider_call": False},
        )


@pytest.mark.parametrize(
    "worker_payload",
    [
        {"provider_call": True, "charge_policy": "free_local_tool", "price_xu": 0, "quoted_price_xu": 0},
        {"provider_call": False, "charge_policy": "after_delivery", "price_xu": 0, "quoted_price_xu": 0},
        {"provider_call": False, "charge_policy": "free_local_tool", "price_xu": 1, "quoted_price_xu": 0},
        {"provider_call": False, "charge_policy": "free_local_tool", "price_xu": 0, "quoted_price_xu": 1},
        {"provider_call": False, "charge_policy": "free_local_tool", "price_xu": "invalid", "quoted_price_xu": 0},
    ],
)
def test_zero_price_rejects_any_provider_or_charge_capable_worker_payload(worker_payload: dict) -> None:
    conn = _conn()
    with pytest.raises(ValueError, match="local_free_contract_invalid"):
        video_editengine1.create_job(
            conn,
            user_id=1,
            chat_id=1,
            edit_session_id="bad-worker-contract",
            source_file_id="source",
            source_metadata={"ok": True},
            plan={},
            tail={},
            quality_tier_id="local-free",
            price_xu=0,
            worker_payload=worker_payload,
        )


@pytest.mark.parametrize(
    ("field", "mismatched"),
    [
        ("user_id", "999"),
        ("chat_id", "999"),
        ("edit_session_id", "another-session"),
        ("source_file_id", "another-source"),
    ],
)
def test_worker_payload_identity_cannot_diverge_from_canonical_job(field: str, mismatched: str) -> None:
    conn = _conn()
    payload = {
        "local1_contract": 1,
        "provider_call": False,
        "charge_policy": "free_local_tool",
        "price_xu": 0,
        "quoted_price_xu": 0,
        field: mismatched,
    }
    with pytest.raises(ValueError, match=f"worker_payload_identity_mismatch:{field}"):
        video_editengine1.create_job(
            conn,
            user_id=77,
            chat_id=88,
            edit_session_id="edit-session-1",
            source_file_id="telegram-source",
            source_metadata={"ok": True, "duration_ms": 4_000},
            plan={"trim": {"start_ms": 0, "end_ms": 3_000}},
            tail={},
            quality_tier_id="local-free",
            price_xu=0,
            worker_payload=payload,
        )


def test_local_free_delivery_keeps_charge_zero_and_cannot_claim_charge() -> None:
    conn = _conn()
    created = _create(conn)
    conn.commit()
    delivered = video_editengine1.record_worker_update(
        conn,
        worker_job_id=created["local_worker_job_id"],
        worker_status="succeeded",
        detail={"validation": "passed", "charge_status": "not_required_free"},
        receipt=_receipt(),
    )
    conn.commit()
    assert delivered["status"] == "delivered"
    assert delivered["charged_xu"] == 0
    assert delivered["charge_state"] == "not_charged"
    assert video_editengine1.claim_charge(conn, worker_job_id=created["local_worker_job_id"]) is False
    unchanged = video_editengine1.mark_charge_result(
        conn,
        worker_job_id=created["local_worker_job_id"],
        ok=True,
        charged_xu=0,
    )
    assert unchanged["status"] == "delivered"
    assert unchanged["charge_state"] == "not_charged"


def test_local_free_worker_payload_has_no_provider_or_tail_side_effects() -> None:
    conn = _conn()
    created = _create(conn)
    conn.commit()
    payload = json.loads(conn.execute("SELECT input_file_id FROM local_worker_jobs").fetchone()[0])
    assert payload["provider_call"] is False
    assert payload["price_xu"] == 0
    assert payload["quoted_price_xu"] == 0
    assert payload["charge_policy"] == "free_local_tool"


def test_local_confirmation_has_one_local_confirm_and_no_shared_tail_callback() -> None:
    start = BOT_SOURCE.index("def video_local_confirmation_keyboard")
    end = BOT_SOURCE.index("def video_editor_menu_text", start)
    source = BOT_SOURCE[start:end]
    assert source.count("videoedit|confirm_local") == 1
    assert "video_tail|" not in source


def test_video_edit_callback_owns_review_and_local_confirm_without_shared_tail() -> None:
    start = BOT_SOURCE.index("async def handle_video_editor_callback")
    end = BOT_SOURCE.index("async def handle_video_upload_callback", start)
    source = BOT_SOURCE[start:end]
    assert "submit_video_edit_local_free_job" in source
    assert 'if action == "confirm_local"' in source
    review_block = source[source.index('if action == "review":'):]
    assert "video_tail9_render(query, uid, context, \"logo\")" not in review_block
