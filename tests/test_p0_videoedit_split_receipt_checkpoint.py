from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import local_worker
from services import video_editengine1


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def test_cleanup_failure_preserves_delivery_unknown_receipt_state() -> None:
    import local_worker

    status, detail = local_worker.finalize_video_local_cleanup_state(
        terminal_status="failed",
        terminal_detail={
            "local1": 1,
            "stage": "delivery_unknown",
            "delivered": 1,
            "total": 2,
        },
        delivery_receipts=[{"message_id": "m1", "file_id": "f1"}],
        cleanup={"ok": False, "reason": "cleanup_failed"},
    )
    assert status == "failed"
    assert detail["stage"] == "delivery_unknown"
    assert detail["cleanup"] == "failed"
    assert detail["cleanup_reason"] == "cleanup_failed"


def test_cleanup_failure_preserves_receiptless_delivery_unknown_state() -> None:
    status, detail = local_worker.finalize_video_local_cleanup_state(
        terminal_status="failed",
        terminal_detail={
            "local1": 1,
            "stage": "delivery_unknown",
            "reason": "telegram_delivery_outcome_uncertain",
            "delivered": 0,
            "total": 1,
        },
        delivery_receipts=[],
        cleanup={"ok": False, "reason": "cleanup_failed"},
    )

    assert status == "failed"
    assert detail["stage"] == "delivery_unknown"
    assert detail["reason"] == "telegram_delivery_outcome_uncertain"
    assert detail["cleanup"] == "failed"
    assert detail["cleanup_reason"] == "cleanup_failed"


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
        plan={"trim": {"start_ms": 0, "end_ms": 2_000}, "brightness_percent": 110},
        tail={},
        quality_tier_id="local-free",
        price_xu=0,
        worker_payload={
            "local1_contract": 1,
            "local1_mode": "manual",
            "source_file_id": "source-file",
            "source_video_hash": "a" * 64,
            "concat_sources": [],
            "provider_call": False,
            "charge_policy": "free_local_tool",
            "price_xu": 0,
            "quoted_price_xu": 0,
        },
    )
    conn.commit()
    return int(created["local_worker_job_id"])


def _artifact(index: int) -> dict:
    return {
        "index": index,
        "message_id": str(1_000 + index),
        "file_id": f"file-{index}",
        "size": 2_048 + index,
        "sha256": str(index) * 64,
        "ffprobe": {
            "ok": True,
            "has_video": True,
            "video_codec": "h264",
            "duration_ms": 1_000,
            "width": 640,
            "height": 360,
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        },
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


def test_declared_malformed_artifact_checkpoint_fails_to_delivery_unknown() -> None:
    conn = _conn()
    worker_job_id = _create_job(conn)
    first = _artifact(1)
    video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="running",
        detail={"stage": "delivering", "artifact_receipts": [first]},
        receipt={},
    )
    malformed = {**_artifact(2), "message_id": True}

    result = video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="running",
        detail={"stage": "delivering", "artifact_receipts": [first, malformed]},
        receipt={},
    )

    assert result["status"] == "delivery_unknown"
    assert result["blocker"] == "artifact_receipt_invalid"
    assert result["artifact_receipts"] == [first]
    assert result["delivery_cursor"] == 1


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
                "validation": {
                    "ok": True,
                    "has_video": True,
                    "video_codec": "h264",
                    "duration_ms": 1_000,
                    "width": 640,
                    "height": 360,
                    "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                },
            }
        )
    monkeypatch.setattr(local_worker, "execute_split_plan", lambda *_args, **_kwargs: {"ok": True, "outputs": outputs})

    def deliver(_chat_id: str, path: str, *_args, **_kwargs) -> dict:
        delivery_calls.append(path)
        if len(delivery_calls) == 1:
            return {"sent": True, "message_id": "1001", "file_id": "file-1"}
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
        "quoted_price_xu": 0,
        "quality_tier_id": "local-free",
        "charge_policy": "free_local_tool",
        "provider_call": False,
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


def test_manual_delivery_receipt_survives_workspace_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "manual-workspace"
    workspace.mkdir()
    source = workspace / "source.mp4"
    source.write_bytes(b"source")
    updates: list[dict] = []

    monkeypatch.setattr(local_worker, "local_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(local_worker, "find_ffprobe", lambda ffmpeg_path="": "ffprobe")
    monkeypatch.setattr(local_worker.shutil, "which", lambda _binary: "ffmpeg")
    monkeypatch.setattr(local_worker, "create_job_workspace", lambda _job_id: workspace)
    monkeypatch.setattr(
        local_worker,
        "cleanup_job_workspace",
        lambda _workspace: {"ok": False, "removed": False, "reason": "cleanup_locked"},
    )
    monkeypatch.setattr(local_worker, "_local1_download_asset", lambda *_args, **_kwargs: str(source))
    monkeypatch.setattr(local_worker, "delivery_file_allowed", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(local_worker.video_ai_edit_validation, "sha256_file", lambda _path: "a" * 64)

    def execute(_plan: dict, *, output_path: str, **_kwargs) -> dict:
        target = Path(output_path)
        target.write_bytes(b"valid-mp4-output")
        return {
            "ok": True,
            "validation": {
                "ok": True,
                "has_video": True,
                "has_audio": True,
                "video_codec": "h264",
                "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                "duration_ms": 2_000,
                "width": 640,
                "height": 360,
            },
        }

    monkeypatch.setattr(local_worker, "execute_manual_edit", execute)
    monkeypatch.setattr(
        local_worker,
        "telegram_send_video_receipt",
        lambda *_args, **_kwargs: {"sent": True, "message_id": "1001", "file_id": "manual-file"},
    )
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
        "plan_schema_version": "video-edit-plan-v1",
        "source_file_id": "source-file",
        "source_file_name": "source.mp4",
        "chat_id": "9101",
        "local1_mode": "manual",
        "price_xu": 0,
        "quoted_price_xu": 0,
        "quality_tier_id": "local-free",
        "charge_policy": "free_local_tool",
        "provider_call": False,
        "manual_edit_plan": {"trim": {"start_ms": 0, "end_ms": 2_000}, "brightness_percent": 110},
    }
    local_worker.run_video_local_edit(
        {"id": 9301, "job_type": video_editengine1.WORKER_JOB_TYPE, "input_file_id": json.dumps(payload)}
    )

    terminal = updates[-1]
    detail = json.loads(terminal["detail"])
    receipt = json.loads(terminal["output_url"])
    assert terminal["status"] == "succeeded"
    assert detail["stage"] == "delivered"
    assert detail["cleanup"] == "failed"
    assert detail["cleanup_reason"] == "cleanup_locked"
    assert receipt["delivery_message_id"] == "1001"
    assert receipt["delivery_file_id"] == "manual-file"
    assert receipt["charge_policy"] == "free_local_tool"
    assert terminal["output_file_id"] == "manual-file"


def _run_manual_delivery_case(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    delivery_result,
) -> dict:
    workspace = tmp_path / "manual-delivery-case"
    workspace.mkdir()
    source = workspace / "source.mp4"
    source.write_bytes(b"source")
    updates: list[dict] = []

    monkeypatch.setattr(local_worker, "local_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(local_worker, "find_ffprobe", lambda ffmpeg_path="": "ffprobe")
    monkeypatch.setattr(local_worker.shutil, "which", lambda _binary: "ffmpeg")
    monkeypatch.setattr(local_worker, "create_job_workspace", lambda _job_id: workspace)
    monkeypatch.setattr(
        local_worker,
        "cleanup_job_workspace",
        lambda _workspace: {"ok": True, "removed": True},
    )
    monkeypatch.setattr(
        local_worker,
        "_local1_download_asset",
        lambda *_args, **_kwargs: str(source),
    )
    monkeypatch.setattr(local_worker, "delivery_file_allowed", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        local_worker.video_ai_edit_validation,
        "sha256_file",
        lambda _path: "a" * 64,
    )

    def execute(_plan: dict, *, output_path: str, **_kwargs) -> dict:
        target = Path(output_path)
        target.write_bytes(b"valid-mp4-output")
        return {
            "ok": True,
            "validation": {
                "ok": True,
                "has_video": True,
                "video_codec": "h264",
                "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                "duration_ms": 2_000,
                "width": 640,
                "height": 360,
            },
        }

    def deliver(*_args, **_kwargs):
        if isinstance(delivery_result, BaseException):
            raise delivery_result
        return dict(delivery_result)

    monkeypatch.setattr(local_worker, "execute_manual_edit", execute)
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
        "plan_schema_version": "video-edit-plan-v1",
        "source_file_id": "source-file",
        "source_file_name": "source.mp4",
        "chat_id": "9101",
        "local1_mode": "manual",
        "price_xu": 0,
        "quoted_price_xu": 0,
        "quality_tier_id": "local-free",
        "charge_policy": "free_local_tool",
        "provider_call": False,
        "manual_edit_plan": {
            "trim": {"start_ms": 0, "end_ms": 2_000},
            "brightness_percent": 110,
        },
    }
    local_worker.run_video_local_edit(
        {
            "id": 9401,
            "job_type": video_editengine1.WORKER_JOB_TYPE,
            "input_file_id": json.dumps(payload),
        }
    )
    return updates[-1]


def test_first_delivery_transport_uncertainty_never_becomes_retryable_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    terminal = _run_manual_delivery_case(
        monkeypatch,
        tmp_path,
        RuntimeError("telegram_delivery_outcome_uncertain"),
    )

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["stage"] == "delivery_unknown"
    assert detail["reason"] == "telegram_delivery_outcome_uncertain"
    assert terminal["output_file_id"] == ""


@pytest.mark.parametrize(
    "delivery",
    [
        {"sent": True, "message_id": True, "file_id": "file-1"},
        {"sent": True, "message_id": "1001", "file_id": "bad file id"},
    ],
)
def test_sent_true_with_malformed_receipt_is_delivery_unknown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    delivery: dict,
) -> None:
    terminal = _run_manual_delivery_case(monkeypatch, tmp_path, delivery)

    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "failed"
    assert detail["stage"] == "delivery_unknown"
    assert detail["reason"] == "telegram_delivery_receipt_invalid"


def test_max_split_receipts_are_not_truncated_by_worker_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(
        local_worker,
        "http_json",
        lambda _method, _path, payload, timeout=20: calls.append(dict(payload)) or {"ok": True},
    )
    artifacts = [_artifact(index) for index in range(1, 31)]

    local_worker._local1_progress(
        9901,
        "delivering",
        processed=30,
        total=30,
        delivered=30,
        artifact_receipts=artifacts,
    )
    checkpoint = calls[-1]["error_short"]
    assert len(checkpoint.encode("utf-8")) > 4_000
    assert json.loads(checkpoint)["artifact_receipts"] == artifacts

    terminal = json.dumps(
        {"artifacts": artifacts, "output_count": 30},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    local_worker.update_job(
        9901,
        "succeeded",
        output_url=terminal,
        output_limit=local_worker.VIDEO_EDIT_RECEIPT_PAYLOAD_LIMIT,
    )
    assert calls[-1]["output_url"] == terminal

    local_worker.update_job(9902, "succeeded", output_url="x" * 5_000)
    assert calls[-1]["output_url"] == "x" * 4_000


def test_bot_endpoint_and_storage_preserve_the_full_video_edit_receipt() -> None:
    storage_start = BOT_SOURCE.index("def update_local_worker_job(")
    storage_end = BOT_SOURCE.index("\ndef ", storage_start + 1)
    storage = BOT_SOURCE[storage_start:storage_end]
    assert 'job_type == "video_local_edit"' in storage
    assert "128 * 1024" in storage
    assert "str(error_short or \"\")[:detail_limit]" in storage
    assert "str(output_url or job.get(\"output_url\") or \"\")[:output_limit]" in storage

    endpoint_start = BOT_SOURCE.index("async def internal_worker_job_update(")
    endpoint_end = BOT_SOURCE.index("\n@fastapi_app", endpoint_start + 1)
    endpoint = BOT_SOURCE[endpoint_start:endpoint_end]
    assert "video_edit_payload_limit = 128 * 1024" in endpoint
    assert "if is_video_edit else 4000" in endpoint
