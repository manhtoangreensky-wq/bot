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
        plan={"input_video": "", "trim": {"start_ms": 0, "end_ms": 4_000}},
        tail={},
        quality_tier_id="local-free",
        price_xu=0,
        worker_payload={
            "source_file_id": "telegram-source",
            "source_file_name": "source.mp4",
            "manual_edit_plan": {"trim": {"start_ms": 0, "end_ms": 4_000}},
            "price_xu": 0,
            "quoted_price_xu": 0,
            "charge_policy": "free_local_tool",
            "provider_call": False,
        },
    )


def _receipt() -> dict:
    return {
        "delivery_message_id": "delivery-1",
        "delivery_file_id": "telegram-output-1",
        "source_video_path": "source.mp4",
        "source_sha256": "a" * 64,
        "output_path": "output.mp4",
        "output_sha256": "b" * 64,
        "output_size_bytes": 4096,
        "ffprobe": {"ok": True, "has_video": True, "video_codec": "h264", "duration_ms": 4000},
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
