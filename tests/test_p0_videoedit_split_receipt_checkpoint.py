from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import local_worker
from services import video_editengine1


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE local_worker_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, command TEXT, job_type TEXT, status TEXT,
            provider TEXT, input_file_id TEXT, created_at TEXT,
            xu_cost INTEGER, admin_only INTEGER, updated_at TEXT
        )"""
    )
    return conn


def _create_job(conn: sqlite3.Connection) -> int:
    created = video_editengine1.create_job(
        conn,
        user_id=9101,
        chat_id="9101",
        edit_session_id="split-session",
        source_file_id="source-file",
        source_metadata={"ok": True, "duration_ms": 2_000},
        plan={"trim": {"start_ms": 0, "end_ms": 2_000}},
        tail={},
        quality_tier_id="local-free",
        price_xu=0,
        worker_payload={
            "local1_contract": 1,
            "source_file_id": "source-file",
            "source_video_hash": "a" * 64,
            "concat_sources": [],
        },
    )
    conn.commit()
    return int(created["local_worker_job_id"])


def _artifact(index: int) -> dict:
    return {
        "index": index,
        "message_id": f"message-{index}",
        "file_id": f"file-{index}",
        "size": 2_048 + index,
        "sha256": str(index) * 64,
        "ffprobe": {"ok": True, "has_video": True, "video_codec": "h264"},
    }


def test_split_delivery_progress_persists_each_artifact_idempotently() -> None:
    conn = _conn()
    worker_job_id = _create_job(conn)
    first = _artifact(1)

    current = video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="running",
        detail={
            "stage": "delivering",
            "delivered": 1,
            "total": 2,
            "artifact_receipts": [first],
        },
        receipt={},
    )
    duplicate = video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="running",
        detail={
            "stage": "delivering",
            "delivered": 1,
            "total": 2,
            "artifact_receipts": [first],
        },
        receipt={},
    )
    conn.commit()

    assert current["artifact_receipts"] == [first]
    assert current["delivery_cursor"] == 1
    assert duplicate["artifact_receipts"] == [first]
    assert duplicate["delivery_cursor"] == 1


def test_split_partial_delivery_unknown_preserves_receipts_and_never_reopens_outbox() -> None:
    conn = _conn()
    worker_job_id = _create_job(conn)
    first = _artifact(1)

    uncertain = video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="delivery_unknown",
        detail={"reason": "split_delivery_partial_unknown", "delivered": 1, "total": 2},
        receipt={"artifacts": [first]},
    )
    conn.commit()

    assert uncertain["status"] == "delivery_unknown"
    assert uncertain["artifact_receipts"] == [first]
    assert uncertain["delivery_cursor"] == 1
    assert uncertain["charge_state"] == "not_charged"
    assert conn.execute(
        "SELECT status FROM video_edit_outbox WHERE local_worker_job_id=?",
        (worker_job_id,),
    ).fetchone()[0] == "terminal_delivery_unknown"


def test_split_worker_marks_partial_delivery_unknown_with_artifact_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "source.mp4"
    source.write_bytes(b"source")
    updates: list[dict] = []
    delivery_calls: list[str] = []

    monkeypatch.setattr(local_worker, "local_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(local_worker, "find_ffprobe", lambda ffmpeg_path="": "ffprobe")
    monkeypatch.setattr(local_worker.shutil, "which", lambda _binary: "ffmpeg")
    monkeypatch.setattr(local_worker, "create_job_workspace", lambda _job_id: workspace)
    monkeypatch.setattr(local_worker, "cleanup_job_workspace", lambda _workspace: {"ok": True, "removed": True})
    monkeypatch.setattr(local_worker, "_local1_download_asset", lambda *_args, **_kwargs: str(source))
    monkeypatch.setattr(local_worker, "delivery_file_allowed", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(local_worker.video_ai_edit_validation, "sha256_file", lambda path: "a" * 64)

    outputs = []
    for index in range(1, 3):
        path = workspace / f"part-{index}.mp4"
        path.write_bytes(b"x" * (2_048 + index))
        outputs.append(
            {
                "path": str(path),
                "duration_ms": 1_000,
                "validation": {"ok": True, "has_video": True, "video_codec": "h264"},
            }
        )
    monkeypatch.setattr(local_worker, "execute_split_plan", lambda *_args, **_kwargs: {"ok": True, "outputs": outputs})

    def deliver(_chat_id: str, path: str, *_args, **_kwargs) -> dict:
        delivery_calls.append(path)
        if len(delivery_calls) == 1:
            return {"sent": True, "message_id": "message-1", "file_id": "file-1"}
        return {"sent": False, "message_id": "", "file_id": ""}

    monkeypatch.setattr(local_worker, "telegram_send_video_receipt", deliver)
    monkeypatch.setattr(
        local_worker,
        "update_job",
        lambda job_id, status, error_short="", output_url="", output_file_id="", **_kwargs: updates.append(
            {
                "job_id": job_id,
                "status": status,
                "detail": error_short,
                "output_url": output_url,
                "output_file_id": output_file_id,
            }
        ),
    )

    payload = {
        "local1_contract": 1,
        "product_type": video_editengine1.PRODUCT_TYPE,
        "engine_route": video_editengine1.ENGINE_ROUTE,
        "worker_owner": video_editengine1.OUTBOX_OWNER,
        "worker_capability": video_editengine1.WORKER_CAPABILITY,
        "source_file_id": "source-file",
        "source_file_name": "source.mp4",
        "chat_id": "9101",
        "local1_mode": "split",
        "price_xu": 0,
        "split_ranges": [
            {"index": 1, "start_ms": 0, "end_ms": 1_000},
            {"index": 2, "start_ms": 1_000, "end_ms": 2_000},
        ],
    }
    local_worker.run_video_local_edit(
        {"id": 9201, "job_type": video_editengine1.WORKER_JOB_TYPE, "input_file_id": json.dumps(payload)}
    )

    terminal = updates[-1]
    detail = json.loads(terminal["detail"])
    receipt = json.loads(terminal["output_url"])
    assert terminal["status"] == "failed"
    assert detail["stage"] == "delivery_unknown"
    assert detail["delivered"] == 1
    assert detail["total"] == 2
    expected_artifact = _artifact(1)
    expected_artifact["sha256"] = "a" * 64
    assert receipt["artifacts"] == [expected_artifact]
    assert terminal["output_file_id"] == "file-1"
    assert len(delivery_calls) == 2
