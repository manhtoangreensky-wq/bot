from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from types import SimpleNamespace
from pathlib import Path

import pytest

import local_worker
from services import video_edit_long_media, video_edit_media_transport, video_editengine1


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
REAL_WRITE_CHECKPOINT_ATOMIC = video_edit_long_media.write_checkpoint_atomic


class _EndpointHTTPException(Exception):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _EndpointRequest:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


MUTATION_EVENT_PREFIX = "mutation:"


class _EndpointConnection:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.commit_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0
        self.canonical_updates: list[dict] = []

    def commit(self) -> None:
        self.commit_calls += 1
        self._events.append("db_commit")

    def close(self) -> None:
        self.close_calls += 1
        self._events.append("db_close")

    def rollback(self) -> None:
        self.rollback_calls += 1
        self._events.append("db_rollback")


def _mutation_events(events: list[str]) -> list[str]:
    return [event for event in events if event.startswith(MUTATION_EVENT_PREFIX)]


def _compiled_video_edit_job_update_endpoint(
    *,
    payload: dict,
    previous_job: dict,
    lease_renewed: bool,
    canonical_failure: BaseException | None = None,
    canonical_result: dict | None = None,
) -> tuple[object, list[str], list[dict], _EndpointConnection, list[tuple[tuple, dict]]]:
    """Compile the endpoint alone so its mutation fence stays executable in isolation."""

    source_tree = ast.parse(BOT_SOURCE)
    endpoint = next(
        node
        for node in source_tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "internal_worker_job_update"
    )
    endpoint.decorator_list = []
    events: list[str] = []
    updates: list[dict] = []
    renew_calls: list[tuple[tuple, dict]] = []
    connection = _EndpointConnection(events)

    async def read_json_body(_request):
        events.append("read_json")
        return dict(payload)

    def update_local_worker_job(job_id, **kwargs):
        events.append(f"{MUTATION_EVENT_PREFIX}update_local_worker_job")
        updated = {"id": job_id, **kwargs}
        updates.append(updated)
        return updated

    def downstream(name: str):
        return lambda *_args, **_kwargs: events.append(f"{MUTATION_EVENT_PREFIX}{name}")

    def renew_worker_lease(*args, **kwargs):
        events.append("renew_worker_lease")
        renew_calls.append((args, kwargs))
        return lease_renewed

    def record_worker_update(_conn, **kwargs):
        events.append(f"{MUTATION_EVENT_PREFIX}record_worker_update")
        if canonical_failure is not None:
            raise canonical_failure
        canonical = {"id": 7001, **kwargs, **dict(canonical_result or {})}
        connection.canonical_updates.append(canonical)
        return canonical

    namespace = {
        "Request": object,
        "HTTPException": _EndpointHTTPException,
        "json": json,
        "verify_local_worker_access": lambda _request: events.append("token_auth"),
        "read_json_body": read_json_body,
        "get_local_worker_job": lambda _job_id: dict(previous_job),
        "update_local_worker_job": update_local_worker_job,
        "handle_frame_video_worker_job_update": downstream("frame_handler"),
        "handle_paid_video_preview_worker_job_update": downstream("paid_preview_handler"),
        "handle_video_ai_edit_worker_job_update": downstream("ai_edit_handler"),
        "handle_video_local_edit_worker_job_update": downstream("video_edit_handler"),
        "handle_social_link_import_worker_job_update": downstream("social_import_handler"),
        "video_editengine1": SimpleNamespace(
            WORKER_JOB_TYPE="video_local_edit",
            renew_worker_lease=renew_worker_lease,
            record_worker_update=record_worker_update,
        ),
        "db_connect": lambda: (events.append("db_connect") or connection),
        "now_text": lambda: "2030-01-02 03:04:05",
        "datetime": datetime,
        "timedelta": timedelta,
        "safe_int": lambda value, default=0: int(value or default),
        "LOCAL_WORKER_MAX_JOB_SECONDS": 600,
    }
    compiled = compile(
        ast.fix_missing_locations(ast.Module(body=[endpoint], type_ignores=[])),
        str(ROOT / "bot.py"),
        "exec",
    )
    exec(compiled, namespace)
    return namespace["internal_worker_job_update"], events, updates, connection, renew_calls


class _PollRequest:
    def __init__(self, query_params: dict[str, str], headers: dict[str, str] | None = None) -> None:
        self.query_params = query_params
        self.headers = dict(headers or {})


class _PollCursor:
    def __init__(self, events: list[str], legacy_job: dict | None) -> None:
        self._events = events
        self._legacy_job = legacy_job
        self.rowcount = 0

    def execute(self, statement: str, _params=()) -> _PollCursor:
        if "SELECT" in statement:
            self._events.append("legacy_queue_select")
        elif "UPDATE local_worker_jobs" in statement:
            self._events.append("legacy_queue_claim")
            self.rowcount = 1 if self._legacy_job else 0
        return self

    def fetchone(self) -> dict | None:
        return dict(self._legacy_job) if self._legacy_job else None


class _PollConnection:
    def __init__(self, events: list[str], legacy_job: dict | None) -> None:
        self._events = events
        self._legacy_job = legacy_job
        self.commit_calls = 0
        self.close_calls = 0

    def cursor(self) -> _PollCursor:
        return _PollCursor(self._events, self._legacy_job)

    def commit(self) -> None:
        self.commit_calls += 1
        self._events.append("legacy_db_commit")

    def close(self) -> None:
        self.close_calls += 1
        self._events.append("db_close")


def _compiled_worker_poll_endpoint(
    *,
    canonical_job: dict | None,
    legacy_job: dict | None,
) -> tuple[object, list[str], _PollConnection, list[tuple[tuple, dict]]]:
    """Compile the public poll seam and observe canonical-vs-legacy ownership."""

    source_tree = ast.parse(BOT_SOURCE)
    endpoint = next(
        node
        for node in source_tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "internal_worker_poll"
    )
    endpoint.decorator_list = []
    events: list[str] = []
    connection = _PollConnection(events, legacy_job)
    claim_calls: list[tuple[tuple, dict]] = []

    def claim_next_video_local_edit(*args, **kwargs):
        events.append("canonical_claim")
        claim_calls.append((args, kwargs))
        return dict(canonical_job) if canonical_job else {}

    namespace = {
        "Request": object,
        "verify_local_worker_access": lambda _request: events.append("token_auth"),
        "set_system_setting": lambda *_args, **_kwargs: events.append("worker_heartbeat"),
        "now_text": lambda: "2030-01-02 03:04:05",
        "LOCAL_WORKER_ENABLED": True,
        "LOCAL_WORKER_POLL_ENABLED": True,
        "LOCAL_WORKER_MAX_JOB_SECONDS": 600,
        "safe_int": lambda value, default=0: int(value or default),
        "datetime": datetime,
        "timedelta": timedelta,
        "db_connect": lambda: connection,
        "local_worker_job_from_row": lambda row: dict(row),
        "get_local_worker_job": lambda _job_id: dict(legacy_job or {}),
        "frame_video_commercial": SimpleNamespace(WORKER_JOB_TYPE="frame_video_render"),
        "update_frame_video_job": lambda *_args, **_kwargs: events.append("frame_update"),
        "update_frame_video_job_config": lambda *_args, **_kwargs: events.append("frame_config"),
        "video_editengine1": SimpleNamespace(
            WORKER_JOB_TYPE="video_local_edit",
            VIDEO_LOCAL_EDIT_RESUME_VERSION=1,
            claim_next_video_local_edit=claim_next_video_local_edit,
        ),
    }
    compiled = compile(
        ast.fix_missing_locations(ast.Module(body=[endpoint], type_ignores=[])),
        str(ROOT / "bot.py"),
        "exec",
    )
    exec(compiled, namespace)
    return namespace["internal_worker_poll"], events, connection, claim_calls


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
            output_file_id TEXT DEFAULT '', output_url TEXT DEFAULT '',
            error_short TEXT DEFAULT '', started_at TEXT DEFAULT '',
            finished_at TEXT DEFAULT '', worker_id TEXT DEFAULT '',
            xu_cost INTEGER, admin_only INTEGER, updated_at TEXT
        )"""
    )
    return conn


def _create_job(
    conn: sqlite3.Connection,
    *,
    edit_session_id: str = "split-session",
) -> int:
    created = video_editengine1.create_job(
        conn,
        user_id=9101,
        chat_id="9101",
        edit_session_id=edit_session_id,
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
            "state_revision": 3,
            "rights_confirmation": {
                "confirmed": True,
                "policy": "video_edit_rights_v1",
                "user_id": "9101",
                "review_revision": 3,
                "confirmed_at_unix": 1_750_000_000,
            },
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


def _terminal_receipt(
    artifacts: list[dict],
    *,
    identity: dict | None = None,
) -> dict:
    identity = dict(identity or artifacts[-1])
    return {
        "delivery_message_id": identity["message_id"],
        "delivery_file_id": identity["file_id"],
        "source_video_path": "source.mp4",
        "source_sha256": "a" * 64,
        "output_path": ",".join(
            f"part-{index}.mp4" for index in range(1, len(artifacts) + 1)
        ),
        "output_size_bytes": sum(int(item["size"]) for item in artifacts),
        "output_sha256": "f" * 64,
        "ffprobe": dict(artifacts[0]["ffprobe"]),
        "output_count": len(artifacts),
        "artifacts": artifacts,
        "charge_policy": "free_local_tool",
        "charge_status": "not_required_free",
        "charged_xu": 0,
    }


def _strict_cursor(
    state: str,
    *,
    output_index: int = 1,
    attempt_id: str = "attempt-1",
    artifact: dict | None = None,
) -> video_edit_long_media.DeliveryCursor:
    fields = {
        "state": state,
        "output_index": output_index,
        "attempt_id": attempt_id,
    }
    if state == "rejected":
        fields.update(deterministic=True, rejection_code="delivery_rejected")
    elif state in {"accepted", "delivered"}:
        evidence = dict(artifact or _artifact(output_index))
        fields.update(
            message_id=evidence["message_id"],
            file_id=evidence["file_id"],
        )
    return video_edit_long_media.DeliveryCursor(**fields)


@pytest.mark.parametrize(
    "optional_evidence",
    [
        {"delivery_method": "sendVideo"},
        {"bytes_sent": 2_049},
        {"delivery_method": "sendDocument", "bytes_sent": 2_049},
    ],
)
def test_engine_retains_valid_optional_artifact_transport_evidence(
    optional_evidence: dict,
) -> None:
    artifact = {**_artifact(1), **optional_evidence}

    assert video_editengine1._artifact_receipts([artifact]) == [artifact]


@pytest.mark.parametrize(
    "optional_evidence",
    [
        {"delivery_method": "sendPhoto"},
        {"delivery_method": True},
        {"bytes_sent": True},
        {"bytes_sent": 2_050},
    ],
)
def test_engine_rejects_invalid_optional_artifact_transport_evidence(
    optional_evidence: dict,
) -> None:
    artifact = {**_artifact(1), **optional_evidence}

    assert video_editengine1._artifact_receipts([artifact]) == []


def _valid_source_probe() -> dict:
    return {
        "ok": True,
        "reason": "",
        "duration": 2.0,
        "duration_ms": 2_000,
        "width": 640,
        "height": 360,
        "fps": 25.0,
        "has_video": True,
        "has_audio": True,
        "audio_stream_count": 1,
        "format_name": "mp4",
        "bytes": 6,
    }


def _rights_confirmation() -> dict:
    return {
        "confirmed": True,
        "policy": "video_edit_rights_v1",
        "user_id": "9101",
        "review_revision": 3,
        "confirmed_at_unix": 1_750_000_000,
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


@pytest.mark.parametrize(
    "incoming_cursor",
    [
        video_edit_long_media.DeliveryCursor(
            state="accepted",
            output_index=1,
            attempt_id="attempt-1",
            message_id="1001",
            file_id="file-1",
        ),
        video_edit_long_media.DeliveryCursor(
            state="rejected",
            output_index=1,
            attempt_id="attempt-1",
            deterministic=True,
            rejection_code="unsupported",
        ),
        video_edit_long_media.DeliveryCursor(
            state="unknown",
            output_index=1,
            attempt_id="attempt-1",
        ),
        video_edit_long_media.DeliveryCursor(
            state="delivered",
            output_index=1,
            attempt_id="attempt-1",
            message_id="1001",
            file_id="file-1",
        ),
    ],
    ids=["accepted", "rejected", "unknown", "delivered"],
)
def test_first_strict_delivery_cursor_rejects_non_sending_state_without_canonical_mutation(
    incoming_cursor: video_edit_long_media.DeliveryCursor,
) -> None:
    conn = _conn()
    worker_job_id = _create_job(conn)
    before = video_editengine1.get_job_by_worker_id(conn, worker_job_id)

    with pytest.raises(ValueError, match="delivery_cursor_invalid"):
        video_editengine1.record_worker_update(
            conn,
            worker_job_id=worker_job_id,
            worker_status="running",
            detail={
                "stage": "delivering",
                "delivery_cursor": incoming_cursor.to_mapping(),
            },
            receipt={},
        )

    assert video_editengine1.get_job_by_worker_id(conn, worker_job_id) == before


def test_first_sending_cursor_rejects_output_gap_without_canonical_mutation() -> None:
    conn = _conn()
    worker_job_id = _create_job(conn)
    before = video_editengine1.get_job_by_worker_id(conn, worker_job_id)
    gap = video_edit_long_media.DeliveryCursor(
        state="sending",
        output_index=2,
        attempt_id="attempt-2",
    )

    with pytest.raises(ValueError, match="delivery_cursor_invalid"):
        video_editengine1.record_worker_update(
            conn,
            worker_job_id=worker_job_id,
            worker_status="running",
            detail={"stage": "delivering", "delivery_cursor": gap.to_mapping()},
            receipt={},
        )

    assert video_editengine1.get_job_by_worker_id(conn, worker_job_id) == before


def test_cursor_prefix_binding_rejects_sending_cursor_with_own_receipt() -> None:
    conn = _conn()
    worker_job_id = _create_job(conn, edit_session_id="sending-own-receipt")
    before = video_editengine1.get_job_by_worker_id(conn, worker_job_id)

    with pytest.raises(ValueError, match="delivery_cursor_invalid"):
        video_editengine1.record_worker_update(
            conn,
            worker_job_id=worker_job_id,
            worker_status="running",
            detail={
                "stage": "delivering",
                "artifact_receipts": [_artifact(1)],
                "delivery_cursor": _strict_cursor("sending").to_mapping(),
            },
            receipt={},
        )

    assert video_editengine1.get_job_by_worker_id(conn, worker_job_id) == before


def test_cursor_prefix_binding_rejects_accepted_or_delivered_identity_mismatch() -> None:
    first = _artifact(1)
    wrong = {**first, "message_id": "9001", "file_id": "wrong-file-1"}

    accepted_conn = _conn()
    accepted_job = _create_job(
        accepted_conn,
        edit_session_id="accepted-identity-mismatch",
    )
    video_editengine1.record_worker_update(
        accepted_conn,
        worker_job_id=accepted_job,
        worker_status="running",
        detail={
            "stage": "delivering",
            "delivery_cursor": _strict_cursor("sending").to_mapping(),
        },
        receipt={},
    )
    accepted_before = video_editengine1.get_job_by_worker_id(
        accepted_conn,
        accepted_job,
    )
    with pytest.raises(ValueError, match="delivery_cursor_invalid"):
        video_editengine1.record_worker_update(
            accepted_conn,
            worker_job_id=accepted_job,
            worker_status="running",
            detail={
                "stage": "delivering",
                "artifact_receipts": [first],
                "delivery_cursor": _strict_cursor(
                    "accepted",
                    artifact=wrong,
                ).to_mapping(),
            },
            receipt={},
        )
    assert (
        video_editengine1.get_job_by_worker_id(accepted_conn, accepted_job)
        == accepted_before
    )

    delivered_conn = _conn()
    delivered_job = _create_job(
        delivered_conn,
        edit_session_id="delivered-identity-mismatch",
    )
    corrupt_accepted = _strict_cursor("accepted", artifact=wrong)
    delivered_conn.execute(
        """UPDATE video_edit_jobs
              SET status='rendering',artifact_receipts_json=?,delivery_cursor=1,
                  tail_json=?
            WHERE local_worker_job_id=?""",
        (
            json.dumps([first], separators=(",", ":")),
            json.dumps(
                {"delivery_cursor": corrupt_accepted.to_mapping()},
                separators=(",", ":"),
            ),
            delivered_job,
        ),
    )
    delivered_conn.commit()
    delivered_before = video_editengine1.get_job_by_worker_id(
        delivered_conn,
        delivered_job,
    )
    with pytest.raises(ValueError, match="delivery_cursor_invalid"):
        video_editengine1.record_worker_update(
            delivered_conn,
            worker_job_id=delivered_job,
            worker_status="running",
            detail={
                "stage": "delivering",
                "artifact_receipts": [first],
                "delivery_cursor": _strict_cursor(
                    "delivered",
                    artifact=wrong,
                ).to_mapping(),
            },
            receipt={},
        )
    assert (
        video_editengine1.get_job_by_worker_id(delivered_conn, delivered_job)
        == delivered_before
    )


def test_cursor_prefix_binding_rejects_unbound_strict_terminal_success() -> None:
    first = _artifact(1)

    sending_conn = _conn()
    sending_job = _create_job(
        sending_conn,
        edit_session_id="terminal-sending-cursor",
    )
    video_editengine1.record_worker_update(
        sending_conn,
        worker_job_id=sending_job,
        worker_status="running",
        detail={
            "stage": "delivering",
            "delivery_cursor": _strict_cursor("sending").to_mapping(),
        },
        receipt={},
    )
    sending_before = video_editengine1.get_job_by_worker_id(sending_conn, sending_job)
    with pytest.raises(ValueError, match="delivery_cursor_invalid"):
        video_editengine1.record_worker_update(
            sending_conn,
            worker_job_id=sending_job,
            worker_status="succeeded",
            detail={"stage": "delivered", "validation": "passed"},
            receipt=_terminal_receipt([first]),
        )
    assert video_editengine1.get_job_by_worker_id(sending_conn, sending_job) == sending_before

    delivered_conn = _conn()
    delivered_job = _create_job(
        delivered_conn,
        edit_session_id="terminal-identity-contradiction",
    )
    sending = _strict_cursor("sending")
    accepted = _strict_cursor("accepted", artifact=first)
    delivered = _strict_cursor("delivered", artifact=first)
    for cursor, artifacts in (
        (sending, []),
        (accepted, [first]),
        (delivered, [first]),
    ):
        video_editengine1.record_worker_update(
            delivered_conn,
            worker_job_id=delivered_job,
            worker_status="running",
            detail={
                "stage": "delivering",
                "artifact_receipts": artifacts,
                "delivery_cursor": cursor.to_mapping(),
            },
            receipt={},
        )
    delivered_before = video_editengine1.get_job_by_worker_id(
        delivered_conn,
        delivered_job,
    )
    contradictory_identity = {**first, "message_id": "9001", "file_id": "wrong-file-1"}
    with pytest.raises(ValueError, match="delivery_cursor_invalid"):
        video_editengine1.record_worker_update(
            delivered_conn,
            worker_job_id=delivered_job,
            worker_status="succeeded",
            detail={
                "stage": "delivered",
                "validation": "passed",
                "delivery_cursor": delivered.to_mapping(),
            },
            receipt=_terminal_receipt(
                [first],
                identity=contradictory_identity,
            ),
        )
    assert (
        video_editengine1.get_job_by_worker_id(delivered_conn, delivered_job)
        == delivered_before
    )


def test_cursor_prefix_binding_allows_sending_accepted_delivered_sequence() -> None:
    conn = _conn()
    worker_job_id = _create_job(conn, edit_session_id="valid-strict-sequence")
    first = _artifact(1)
    cursors = (
        (_strict_cursor("sending"), []),
        (_strict_cursor("accepted", artifact=first), [first]),
        (_strict_cursor("delivered", artifact=first), [first]),
    )

    for cursor, artifacts in cursors:
        result = video_editengine1.record_worker_update(
            conn,
            worker_job_id=worker_job_id,
            worker_status="running",
            detail={
                "stage": "delivering",
                "artifact_receipts": artifacts,
                "delivery_cursor": cursor.to_mapping(),
            },
            receipt={},
        )
        assert result["delivery_cursor"] == len(artifacts)
        assert result["tail"]["delivery_cursor"] == cursor.to_mapping()

    terminal = video_editengine1.record_worker_update(
        conn,
        worker_job_id=worker_job_id,
        worker_status="succeeded",
        detail={
            "stage": "delivered",
            "validation": "passed",
            "delivery_cursor": cursors[-1][0].to_mapping(),
        },
        receipt=_terminal_receipt([first]),
    )

    assert terminal["status"] == "delivered"
    assert terminal["delivery_cursor"] == 1
    assert terminal["tail"]["delivery_cursor"] == cursors[-1][0].to_mapping()


def test_expired_rejected_cursor_terminalizes_without_reclaim_and_scan_continues() -> None:
    conn = _conn()
    rejected_job = _create_job(conn, edit_session_id="expired-rejected")
    next_job = _create_job(conn, edit_session_id="queued-after-rejected")
    first_claim = video_editengine1.claim_next_video_local_edit(
        conn,
        lease_owner="worker-a:host-a:100",
        now="2099-01-01 00:00:00",
        lease_seconds=30,
    )
    assert first_claim["id"] == rejected_job
    assert first_claim["claim_attempt"] == 1

    sending = _strict_cursor("sending", attempt_id="delivery-reject-attempt")
    rejected = _strict_cursor("rejected", attempt_id="delivery-reject-attempt")
    video_editengine1.record_worker_update(
        conn,
        worker_job_id=rejected_job,
        worker_status="running",
        detail={
            "stage": "delivering",
            "artifact_receipts": [],
            "delivery_cursor": sending.to_mapping(),
        },
        receipt={},
    )
    video_editengine1.record_worker_update(
        conn,
        worker_job_id=rejected_job,
        worker_status="running",
        detail={
            "stage": "delivering",
            "artifact_receipts": [],
            "delivery_cursor": rejected.to_mapping(),
        },
        receipt={},
    )
    conn.commit()

    claimed = video_editengine1.claim_next_video_local_edit(
        conn,
        lease_owner="worker-b:host-b:200",
        now="2099-01-01 00:00:31",
        lease_seconds=30,
    )
    terminal = video_editengine1.get_job_by_worker_id(conn, rejected_job)
    outbox = conn.execute(
        """SELECT status,attempt_count,terminal_reason
             FROM video_edit_outbox WHERE local_worker_job_id=?""",
        (rejected_job,),
    ).fetchone()
    local = conn.execute(
        "SELECT status,error_short FROM local_worker_jobs WHERE id=?",
        (rejected_job,),
    ).fetchone()

    assert claimed["id"] == next_job
    assert claimed["claim_attempt"] == 1
    assert local[0] == "failed"
    assert json.loads(local[1])["delivery_cursor"] == rejected.to_mapping()
    assert terminal["status"] == "failed_no_charge"
    assert terminal["charge_state"] == "not_charged"
    assert terminal["charged_xu"] == 0
    assert terminal["tail"]["delivery_cursor"] == rejected.to_mapping()
    assert outbox == ("terminal_failed", 1, "delivery_rejected")


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
    project_workspace = tmp_path / "workspace"
    workspace = project_workspace / "claim_1"
    workspace.mkdir(parents=True)
    source = workspace / "source.mp4"
    source.write_bytes(b"source")
    updates: list[dict] = []
    delivery_calls: list[str] = []
    cleanup_calls: list[Path] = []
    events: list[str] = []
    checkpoints: list[tuple[Path, video_edit_long_media.LongMediaCheckpoint]] = []

    def cleanup(_workspace: Path) -> dict:
        cleanup_calls.append(_workspace)
        return {"ok": True, "removed": True}

    monkeypatch.setattr(local_worker, "local_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(local_worker, "find_ffprobe", lambda ffmpeg_path="": "ffprobe")
    monkeypatch.setattr(local_worker.shutil, "which", lambda _binary: "ffmpeg")
    monkeypatch.setattr(local_worker, "create_job_workspace", lambda _job_id: workspace)
    monkeypatch.setattr(
        local_worker,
        "create_video_edit_claim_workspace",
        lambda _job_id, _claim_attempt: (project_workspace, workspace),
    )
    monkeypatch.setattr(local_worker, "cleanup_job_workspace", cleanup)
    monkeypatch.setattr(
        local_worker,
        "prepare_video_edit_cleanup_intent",
        lambda **kwargs: (
            {
                "job_id": kwargs["job_id"],
                "workspace_key": project_workspace.name,
            },
            {
                "persisted": True,
                "workspace_present": True,
                "workspace_key": project_workspace.name,
            },
        ),
    )
    monkeypatch.setattr(
        local_worker,
        "reconcile_video_edit_cleanup_intent",
        lambda _intent: {"ok": True, "removed": True},
    )
    monkeypatch.setattr(local_worker, "TELEGRAM_BOT_TOKEN", "123:test-token")
    monkeypatch.setattr(local_worker, "_video_edit_download_asset", lambda *_args, **_kwargs: str(source))
    monkeypatch.setattr(local_worker, "delivery_file_allowed", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(local_worker.video_ai_edit_validation, "sha256_file", lambda path: "a" * 64)
    monkeypatch.setattr(
        local_worker.video_local_validation,
        "probe_video_file",
        lambda *_args, **_kwargs: _valid_source_probe(),
    )

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

    def write_checkpoint(destination, checkpoint) -> None:
        events.append("checkpoint")
        checkpoints.append((Path(destination), checkpoint))

    monkeypatch.setattr(
        video_edit_long_media,
        "write_checkpoint_atomic",
        write_checkpoint,
    )

    def deliver(*, artifact, **_kwargs):
        path = str(artifact)
        events.append("transport")
        delivery_calls.append(path)
        if len(delivery_calls) == 1:
            return video_edit_media_transport.DeliveryReceipt(
                message_id="1001",
                file_id="file-1",
                delivery_method="sendVideo",
                bytes_sent=Path(path).stat().st_size,
                sha256="a" * 64,
            )
        raise video_edit_media_transport.MediaTransferError("delivery_unknown")

    monkeypatch.setattr(
        video_edit_media_transport,
        "send_artifact_from_path",
        deliver,
    )
    def update_job(
        job_id,
        status,
        error_short="",
        output_url="",
        output_file_id="",
        **_kwargs,
    ) -> dict:
        updates.append(
            {
                "job_id": job_id,
                "status": status,
                "detail": error_short,
                "output_url": output_url,
                "output_file_id": output_file_id,
            }
        )
        return {"ok": True}

    monkeypatch.setattr(local_worker, "update_job", update_job)

    payload = {
        "local1_contract": 1,
        "product_type": video_editengine1.PRODUCT_TYPE,
        "engine_route": video_editengine1.ENGINE_ROUTE,
        "worker_owner": video_editengine1.OUTBOX_OWNER,
        "worker_capability": video_editengine1.WORKER_CAPABILITY,
        "source_file_id": "source-file",
        "source_file_name": "source.mp4",
        "source_metadata": _valid_source_probe(),
        "user_id": "9101",
        "chat_id": "9101",
        "local1_mode": "split",
        "price_xu": 0,
        "quoted_price_xu": 0,
        "quality_tier_id": "local-free",
        "charge_policy": "free_local_tool",
        "provider_call": False,
        "state_revision": 3,
        "manual_edit_plan": {},
        "rights_confirmation": _rights_confirmation(),
        "split_ranges": [
            {"index": 1, "start_ms": 0, "end_ms": 1_000},
            {"index": 2, "start_ms": 1_000, "end_ms": 2_000},
        ],
    }
    local_worker.run_video_local_edit(
        {
            "id": 9201,
            "claim_attempt": 1,
            "user_id": 9101,
            "job_type": video_editengine1.WORKER_JOB_TYPE,
            "input_file_id": json.dumps(payload),
        }
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
    expected_artifact["delivery_method"] = "sendVideo"
    expected_artifact["bytes_sent"] = expected_artifact["size"]
    assert receipt["artifacts"] == [expected_artifact]
    assert terminal["output_file_id"] == "file-1"
    assert len(delivery_calls) == 2
    assert len(checkpoints) == 2
    assert [item.output_index for _path, item in checkpoints] == [1, 2]
    assert [item.stage for _path, item in checkpoints] == [
        "delivery_ready",
        "delivery_ready",
    ]
    assert all(path.parent == project_workspace for path, _item in checkpoints)
    assert events[:2] == ["checkpoint", "checkpoint"]
    assert events[2] == "transport"
    assert cleanup_calls == []
    assert project_workspace.exists()
    assert all(Path(output["path"]).exists() for output in outputs)


def test_manual_delivery_receipt_survives_workspace_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_workspace = tmp_path / "manual-project"
    workspace = project_workspace / "claim_1"
    workspace.mkdir(parents=True)
    source = workspace / "source.mp4"
    source.write_bytes(b"source")
    updates: list[dict] = []
    cleanup_calls: list[Path] = []
    output = workspace / "toan_aas_video_edit_9301.mp4"
    monkeypatch.setattr(
        local_worker,
        "create_video_edit_claim_workspace",
        lambda _job_id, _claim_attempt: (project_workspace, workspace),
    )

    def prepare_cleanup_intent(**kwargs) -> tuple[dict, dict]:
        key = f"job_{kwargs['job_id']}_claim_{kwargs['claim_attempt']}"
        return (
            {"job_id": kwargs["job_id"], "workspace_key": key},
            {
                "persisted": True,
                "workspace_present": True,
                "intent_key": f"{key}.json",
                "workspace_key": key,
                "tombstone_key": key,
            },
        )

    def reconcile_cleanup(_intent: dict) -> dict:
        cleanup_calls.append(workspace)
        return {"ok": False, "removed": False, "reason": "cleanup_locked"}

    monkeypatch.setattr(local_worker, "local_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(local_worker, "find_ffprobe", lambda ffmpeg_path="": "ffprobe")
    monkeypatch.setattr(local_worker.shutil, "which", lambda _binary: "ffmpeg")
    monkeypatch.setattr(local_worker, "create_job_workspace", lambda _job_id: workspace)
    monkeypatch.setattr(
        local_worker,
        "prepare_video_edit_cleanup_intent",
        prepare_cleanup_intent,
    )
    monkeypatch.setattr(
        local_worker,
        "reconcile_video_edit_cleanup_intent",
        reconcile_cleanup,
    )
    monkeypatch.setattr(local_worker, "TELEGRAM_BOT_TOKEN", "123:test-token")
    monkeypatch.setattr(local_worker, "_video_edit_download_asset", lambda *_args, **_kwargs: str(source))
    monkeypatch.setattr(local_worker, "delivery_file_allowed", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(local_worker.video_ai_edit_validation, "sha256_file", lambda _path: "a" * 64)
    monkeypatch.setattr(
        local_worker.video_local_validation,
        "probe_video_file",
        lambda *_args, **_kwargs: _valid_source_probe(),
    )

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
        video_edit_media_transport,
        "send_artifact_from_path",
        lambda *, artifact, **_kwargs: video_edit_media_transport.DeliveryReceipt(
            message_id="1001",
            file_id="manual-file",
            delivery_method="sendVideo",
            bytes_sent=Path(artifact).stat().st_size,
            sha256="a" * 64,
        ),
    )
    def update_job(
        job_id,
        status,
        error_short="",
        output_url="",
        output_file_id="",
        **_kwargs,
    ) -> dict:
        updates.append(
            {
                "job_id": job_id,
                "status": status,
                "detail": error_short,
                "output_url": output_url,
                "output_file_id": output_file_id,
            }
        )
        return {"ok": True}

    monkeypatch.setattr(local_worker, "update_job", update_job)

    payload = {
        "local1_contract": 1,
        "product_type": video_editengine1.PRODUCT_TYPE,
        "engine_route": video_editengine1.ENGINE_ROUTE,
        "worker_owner": video_editengine1.OUTBOX_OWNER,
        "worker_capability": video_editengine1.WORKER_CAPABILITY,
        "plan_schema_version": "video-edit-plan-v1",
        "source_file_id": "source-file",
        "source_file_name": "source.mp4",
        "source_metadata": _valid_source_probe(),
        "user_id": "9101",
        "chat_id": "9101",
        "local1_mode": "manual",
        "price_xu": 0,
        "quoted_price_xu": 0,
        "quality_tier_id": "local-free",
        "charge_policy": "free_local_tool",
        "provider_call": False,
        "state_revision": 3,
        "rights_confirmation": _rights_confirmation(),
        "manual_edit_plan": {"trim": {"start_ms": 0, "end_ms": 2_000}, "brightness_percent": 110},
    }
    local_worker.run_video_local_edit(
        {
            "id": 9301,
            "claim_attempt": 1,
            "user_id": 9101,
            "job_type": video_editengine1.WORKER_JOB_TYPE,
            "input_file_id": json.dumps(payload),
        }
    )

    terminal = updates[-1]
    detail = json.loads(terminal["detail"])
    receipt = json.loads(terminal["output_url"])
    assert terminal["status"] == "succeeded"
    assert detail["stage"] == "delivered"
    assert detail["cleanup"] == "pending"
    assert "cleanup_reason" not in detail
    assert receipt["delivery_message_id"] == "1001"
    assert receipt["delivery_file_id"] == "manual-file"
    assert receipt["charge_policy"] == "free_local_tool"
    assert terminal["output_file_id"] == "manual-file"
    assert cleanup_calls == [workspace]
    assert project_workspace.exists()
    assert output.exists()


def _run_manual_delivery_case(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    delivery_result,
    *,
    pre_send_update_result: object = None,
    rejected_update_result: object = None,
    terminal_update_result: object = None,
    record_events: bool = False,
    claim_attempt: int = 1,
    workspace_name: str = "manual-delivery-case",
    persist_checkpoints: bool = False,
    source_bytes: bytes = b"source",
    manual_plan: dict | None = None,
    logo_bytes: bytes | None = None,
    output_probe_patch: dict | None = None,
) -> dict:
    project_workspace = tmp_path / workspace_name
    workspace = project_workspace / f"claim_{claim_attempt}"
    workspace.mkdir(parents=True)
    source = workspace / "source.mp4"
    source.write_bytes(source_bytes)
    logo = workspace / "logo-input.png"
    if logo_bytes is not None:
        logo.write_bytes(logo_bytes)
    updates: list[dict] = []
    events: list[object] = []
    checkpoints: list[tuple[Path, video_edit_long_media.LongMediaCheckpoint]] = []
    output = workspace / "toan_aas_video_edit_9401.mp4"

    monkeypatch.setattr(local_worker, "local_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(local_worker, "find_ffprobe", lambda ffmpeg_path="": "ffprobe")
    monkeypatch.setattr(local_worker.shutil, "which", lambda _binary: "ffmpeg")
    monkeypatch.setattr(local_worker, "create_job_workspace", lambda _job_id: workspace)
    monkeypatch.setattr(
        local_worker,
        "create_video_edit_claim_workspace",
        lambda _job_id, _claim_attempt: (project_workspace, workspace),
        raising=False,
    )
    def prepare_cleanup_intent(**kwargs) -> tuple[dict, dict]:
        key = f"job_{kwargs['job_id']}_claim_{kwargs['claim_attempt']}"
        return (
            {"job_id": kwargs["job_id"], "workspace_key": key},
            {
                "persisted": True,
                "workspace_present": True,
                "intent_key": f"{key}.json",
                "workspace_key": key,
                "tombstone_key": key,
            },
        )

    def reconcile_cleanup(_intent: dict) -> dict:
        events.append("cleanup")
        if record_events:
            local_worker.shutil.rmtree(project_workspace)
        return {"ok": True, "removed": True}

    monkeypatch.setattr(
        local_worker,
        "prepare_video_edit_cleanup_intent",
        prepare_cleanup_intent,
    )
    monkeypatch.setattr(
        local_worker,
        "reconcile_video_edit_cleanup_intent",
        reconcile_cleanup,
    )
    def download_asset(*args, **_kwargs):
        stem = str(args[4] if len(args) > 4 else "")
        return str(logo if stem == "logo" else source)

    monkeypatch.setattr(
        local_worker,
        "_video_edit_download_asset",
        download_asset,
    )
    monkeypatch.setattr(local_worker, "TELEGRAM_BOT_TOKEN", "123:test-token")
    monkeypatch.setattr(local_worker, "delivery_file_allowed", lambda *_args, **_kwargs: True)
    if not persist_checkpoints:
        monkeypatch.setattr(
            local_worker.video_ai_edit_validation,
            "sha256_file",
            lambda _path: "a" * 64,
        )
    def probe_video(path, **_kwargs) -> dict:
        probe = _valid_source_probe()
        artifact = Path(path)
        if artifact.name.startswith("toan_aas_video_edit_"):
            probe["video_codec"] = "h264"
            probe["bytes"] = artifact.stat().st_size
            probe.update(dict(output_probe_patch or {}))
        return probe

    monkeypatch.setattr(
        local_worker.video_local_validation,
        "probe_video_file",
        probe_video,
    )

    def write_checkpoint(
        destination: str | Path,
        checkpoint: video_edit_long_media.LongMediaCheckpoint,
    ) -> Path | None:
        events.append("checkpoint")
        checkpoints.append((Path(destination), checkpoint))
        if persist_checkpoints:
            return REAL_WRITE_CHECKPOINT_ATOMIC(destination, checkpoint)
        return None

    monkeypatch.setattr(
        video_edit_long_media,
        "write_checkpoint_atomic",
        write_checkpoint,
    )

    def execute(_plan: dict, *, output_path: str, **_kwargs) -> dict:
        events.append("render")
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
        events.append("transport")
        if callable(delivery_result):
            return delivery_result(*_args, **_kwargs)
        if isinstance(delivery_result, BaseException):
            raise delivery_result
        if isinstance(delivery_result, video_edit_media_transport.DeliveryReceipt):
            return delivery_result
        return dict(delivery_result)

    monkeypatch.setattr(local_worker, "execute_manual_edit", execute)
    monkeypatch.setattr(
        video_edit_media_transport,
        "send_artifact_from_path",
        deliver,
    )
    def update_job(
        job_id,
        status,
        error_short="",
        output_url="",
        output_file_id="",
        **_kwargs,
    ):
        update = {
            "job_id": job_id,
            "status": status,
            "detail": error_short,
            "output_url": output_url,
            "output_file_id": output_file_id,
        }
        updates.append(update)
        try:
            detail = json.loads(error_short or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            detail = {}
        cursor = detail.get("delivery_cursor") if isinstance(detail, dict) else None
        cursor_state = cursor.get("state") if isinstance(cursor, dict) else ""
        is_pre_send = cursor_state == "sending"
        is_rejected = cursor_state == "rejected" and status == "running"
        is_terminal = status != "running"
        if is_pre_send:
            events.append("pre_send_ack")
            outcome = pre_send_update_result
        elif is_rejected:
            events.append("rejected_ack")
            outcome = rejected_update_result
        elif is_terminal:
            events.append("terminal_ack")
            outcome = terminal_update_result
        else:
            outcome = None
        if isinstance(outcome, BaseException):
            raise outcome
        return {"ok": True} if outcome is None else outcome

    monkeypatch.setattr(local_worker, "update_job", update_job)

    submitted_plan = dict(
        manual_plan
        or {
            "trim": {"start_ms": 0, "end_ms": 2_000},
            "brightness_percent": 110,
        }
    )
    source_metadata = _valid_source_probe()
    source_metadata["bytes"] = len(source_bytes)
    payload = {
        "local1_contract": 1,
        "product_type": video_editengine1.PRODUCT_TYPE,
        "engine_route": video_editengine1.ENGINE_ROUTE,
        "worker_owner": video_editengine1.OUTBOX_OWNER,
        "worker_capability": video_editengine1.WORKER_CAPABILITY,
        "plan_schema_version": "video-edit-plan-v1",
        "source_file_id": "source-file",
        "source_file_name": "source.mp4",
        "source_metadata": source_metadata,
        "user_id": "9101",
        "chat_id": "9101",
        "local1_mode": "manual",
        "price_xu": 0,
        "quoted_price_xu": 0,
        "quality_tier_id": "local-free",
        "charge_policy": "free_local_tool",
        "provider_call": False,
        "state_revision": 3,
        "rights_confirmation": _rights_confirmation(),
        "manual_edit_plan": submitted_plan,
    }
    if logo_bytes is not None:
        payload["logo_source"] = {
            "file_id": "logo-file",
            "file_name": "logo.png",
            "file_size": len(logo_bytes),
        }
    run_error: BaseException | None = None
    try:
        local_worker.run_video_local_edit(
            {
                "id": 9401,
                "claim_attempt": claim_attempt,
                "user_id": 9101,
                "job_type": video_editengine1.WORKER_JOB_TYPE,
                "input_file_id": json.dumps(payload),
            }
        )
    except BaseException as exc:
        run_error = exc
    if record_events:
        return {
            "terminal": updates[-1],
            "updates": updates,
            "events": events,
            "workspace": workspace,
            "project_workspace": project_workspace,
            "evidence": output,
            "checkpoints": checkpoints,
            "run_error": run_error,
        }
    if run_error is not None:
        raise run_error
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


def test_manual_delivery_persists_strict_sending_cursor_before_transport(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = _run_manual_delivery_case(
        monkeypatch,
        tmp_path,
        video_edit_media_transport.DeliveryReceipt(
            message_id="1001",
            file_id="manual-file",
            delivery_method="sendVideo",
            bytes_sent=len(b"valid-mp4-output"),
            sha256="a" * 64,
        ),
        record_events=True,
        claim_attempt=7,
        workspace_name="manual-delivery-first",
    )
    second = _run_manual_delivery_case(
        monkeypatch,
        tmp_path,
        video_edit_media_transport.DeliveryReceipt(
            message_id="1002",
            file_id="manual-file-2",
            delivery_method="sendVideo",
            bytes_sent=len(b"valid-mp4-output"),
            sha256="a" * 64,
        ),
        record_events=True,
        claim_attempt=8,
        workspace_name="manual-delivery-second",
    )

    def sending_updates(result: dict) -> list[dict]:
        updates = []
        for update in result["updates"]:
            try:
                detail = json.loads(update["detail"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            cursor_value = detail.get("delivery_cursor") if isinstance(detail, dict) else None
            if isinstance(cursor_value, dict) and cursor_value.get("state") == "sending":
                updates.append(cursor_value)
        return updates

    first_updates = sending_updates(first)
    second_updates = sending_updates(second)
    assert len(first_updates) == 1
    assert len(second_updates) == 1
    cursor = video_edit_long_media.DeliveryCursor.from_mapping(first_updates[0])
    second_cursor = video_edit_long_media.DeliveryCursor.from_mapping(second_updates[0])
    assert video_edit_long_media.advance_delivery_cursor(
        video_edit_long_media.DeliveryCursor(output_index=cursor.output_index),
        cursor,
    ) == cursor
    assert cursor.output_index == 1
    assert "7" in cursor.attempt_id
    assert "8" in second_cursor.attempt_id
    assert cursor.attempt_id != second_cursor.attempt_id
    assert first["events"].index("pre_send_ack") < first["events"].index("transport")


def test_worker_persists_manual_canonical_checkpoint_before_first_delivery_attempt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = _run_manual_delivery_case(
        monkeypatch,
        tmp_path,
        video_edit_media_transport.DeliveryReceipt(
            message_id="1001",
            file_id="manual-file",
            delivery_method="sendVideo",
            bytes_sent=len(b"valid-mp4-output"),
            sha256="a" * 64,
        ),
        record_events=True,
        claim_attempt=9,
        workspace_name="manual-checkpoint-before-delivery",
    )

    assert result["run_error"] is None
    assert len(result["checkpoints"]) == 1
    checkpoint_path, checkpoint = result["checkpoints"][0]
    assert checkpoint_path.parent == result["project_workspace"]
    assert checkpoint.stage == "delivery_ready"
    assert checkpoint.output_index == 1
    assert checkpoint.source_sha256 == "a" * 64
    assert checkpoint.revision == 3
    assert checkpoint.delivery.state == "not_started"
    assert checkpoint.canonical is not None
    assert checkpoint.canonical.relative_path == "claim_9/toan_aas_video_edit_9401.mp4"
    assert checkpoint.canonical.byte_count == len(b"valid-mp4-output")
    assert checkpoint.canonical.sha256 == "a" * 64
    assert checkpoint.canonical.duration_ms == 2_000
    assert checkpoint.canonical.width == 640
    assert checkpoint.canonical.height == 360
    assert result["events"].index("render") < result["events"].index("checkpoint")
    assert result["events"].index("checkpoint") < result["events"].index("pre_send_ack")
    assert result["events"].index("checkpoint") < result["events"].index("transport")


def test_valid_manual_checkpoint_reclaim_skips_executor_and_delivers_original_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = _run_manual_delivery_case(
        monkeypatch,
        tmp_path,
        AssertionError("transport must not start without sending ACK"),
        pre_send_update_result={"ok": False},
        terminal_update_result={"ok": False},
        record_events=True,
        claim_attempt=1,
        workspace_name="manual-reclaim-stable-project",
        persist_checkpoints=True,
    )

    assert first["run_error"] is not None
    assert first["events"].count("render") == 1
    assert first["events"].count("transport") == 0
    assert first["events"].count("pre_send_ack") == 1
    assert first["project_workspace"].exists()
    assert len(first["checkpoints"]) == 1
    first_checkpoint_path, first_checkpoint = first["checkpoints"][0]
    assert first_checkpoint_path.exists()
    loaded = video_edit_long_media.try_load_checkpoint(
        first_checkpoint_path,
        project_key=first_checkpoint.project_key,
        source_sha256=first_checkpoint.source_sha256,
        plan_hash=first_checkpoint.plan_hash,
        revision=first_checkpoint.revision,
        output_index=first_checkpoint.output_index,
    )
    assert loaded == first_checkpoint
    artifact_path = (
        first["project_workspace"]
        / first_checkpoint.canonical.relative_path
    )
    assert artifact_path.exists()
    assert artifact_path.stat().st_size == first_checkpoint.canonical.byte_count
    assert (
        hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        == first_checkpoint.canonical.sha256
    )
    recovered = video_edit_long_media.recover_canonical_output(
        loaded,
        workspace=first["project_workspace"],
        ffprobe_evidence={
            "duration_ms": 2_000,
            "width": 640,
            "height": 360,
            "container": "mp4",
        },
        project_key=first_checkpoint.project_key,
        source_sha256=first_checkpoint.source_sha256,
        plan_hash=first_checkpoint.plan_hash,
        revision=first_checkpoint.revision,
        output_index=first_checkpoint.output_index,
    )
    assert recovered.allowed is True

    delivered_paths: list[Path] = []

    def deliver_recovered(*_args, **kwargs):
        artifact = Path(kwargs["artifact"])
        delivered_paths.append(artifact)
        payload = artifact.read_bytes()
        return video_edit_media_transport.DeliveryReceipt(
            message_id="1002",
            file_id="manual-recovered-file",
            delivery_method="sendVideo",
            bytes_sent=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )

    checkpoint_loads: list[tuple[dict, object]] = []
    real_try_load_checkpoint = video_edit_long_media.try_load_checkpoint

    def observe_checkpoint_load(source, **identity):
        loaded_checkpoint = real_try_load_checkpoint(source, **identity)
        checkpoint_loads.append((dict(identity), loaded_checkpoint))
        return loaded_checkpoint

    monkeypatch.setattr(
        video_edit_long_media,
        "try_load_checkpoint",
        observe_checkpoint_load,
    )

    second = _run_manual_delivery_case(
        monkeypatch,
        tmp_path,
        deliver_recovered,
        record_events=True,
        claim_attempt=2,
        workspace_name="manual-reclaim-stable-project",
        persist_checkpoints=True,
    )

    assert second["run_error"] is None
    assert len(checkpoint_loads) == 1
    assert checkpoint_loads[0][1] is not None
    assert second["events"].count("render") == 0
    assert second["events"].count("transport") == 1
    assert len(delivered_paths) == 1
    assert delivered_paths[0].parent.name == "claim_1"
    terminal = second["terminal"]
    detail = json.loads(terminal["detail"])
    assert terminal["status"] == "succeeded"
    assert detail["stage"] == "delivered"


@pytest.mark.parametrize(
    "mismatch",
    ["source_hash", "plan", "artifact", "ffprobe", "logo_asset"],
)
def test_manual_checkpoint_mismatch_rerenders_before_delivery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mismatch: str,
) -> None:
    base_plan = {
        "trim": {"start_ms": 0, "end_ms": 2_000},
        "brightness_percent": 110,
    }
    first_kwargs: dict = {}
    second_kwargs: dict = {}
    if mismatch == "plan":
        second_kwargs["manual_plan"] = {
            **base_plan,
            "brightness_percent": 120,
        }
    elif mismatch == "source_hash":
        second_kwargs["source_bytes"] = b"different-source"
    elif mismatch == "ffprobe":
        second_kwargs["output_probe_patch"] = {
            "duration": 3.0,
            "duration_ms": 3_000,
        }
    elif mismatch == "logo_asset":
        logo_plan = {
            **base_plan,
            "logo_overlay": {
                "position": "top_right",
                "path": "queued-logo.png",
            },
        }
        first_kwargs.update(
            manual_plan=logo_plan,
            logo_bytes=b"logo-a",
        )
        second_kwargs.update(
            manual_plan=logo_plan,
            logo_bytes=b"logo-b",
        )

    first_case = {"manual_plan": base_plan, **first_kwargs}
    second_case = {"manual_plan": base_plan, **second_kwargs}
    first = _run_manual_delivery_case(
        monkeypatch,
        tmp_path,
        AssertionError("transport must not start without sending ACK"),
        pre_send_update_result={"ok": False},
        terminal_update_result={"ok": False},
        record_events=True,
        claim_attempt=1,
        workspace_name=f"manual-mismatch-{mismatch}",
        persist_checkpoints=True,
        **first_case,
    )
    assert first["events"].count("render") == 1
    assert first["events"].count("transport") == 0
    checkpoint_path, checkpoint = first["checkpoints"][0]
    artifact_path = first["project_workspace"] / checkpoint.canonical.relative_path
    if mismatch == "artifact":
        artifact_path.write_bytes(b"corrupt-artifact")

    delivered_paths: list[Path] = []

    def deliver_rerendered(*_args, **kwargs):
        artifact = Path(kwargs["artifact"])
        delivered_paths.append(artifact)
        payload = artifact.read_bytes()
        return video_edit_media_transport.DeliveryReceipt(
            message_id="1003",
            file_id=f"rerendered-{mismatch}",
            delivery_method="sendVideo",
            bytes_sent=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )

    second = _run_manual_delivery_case(
        monkeypatch,
        tmp_path,
        deliver_rerendered,
        record_events=True,
        claim_attempt=2,
        workspace_name=f"manual-mismatch-{mismatch}",
        persist_checkpoints=True,
        **second_case,
    )

    assert second["run_error"] is None
    assert second["events"].count("render") == 1
    assert second["events"].count("transport") == 1
    assert len(delivered_paths) == 1
    assert delivered_paths[0].parent.name == "claim_2"
    assert not checkpoint_path.exists()


def _run_split_checkpoint_case(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    delivery_result,
    *,
    claim_attempt: int,
    project_name: str,
    pre_send_update_result: object = None,
    terminal_update_result: object = None,
) -> dict:
    project_workspace = tmp_path / project_name
    workspace = project_workspace / f"claim_{claim_attempt}"
    workspace.mkdir(parents=True)
    source = workspace / "source.mp4"
    source.write_bytes(b"source")
    events: list[str] = []
    updates: list[dict] = []
    checkpoints: list[tuple[Path, video_edit_long_media.LongMediaCheckpoint]] = []
    rendered_ranges: list[list[tuple[int, int]]] = []

    monkeypatch.setattr(local_worker, "local_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(local_worker, "find_ffprobe", lambda ffmpeg_path="": "ffprobe")
    monkeypatch.setattr(local_worker.shutil, "which", lambda _binary: "ffmpeg")
    monkeypatch.setattr(local_worker, "create_job_workspace", lambda _job_id: workspace)
    monkeypatch.setattr(
        local_worker,
        "create_video_edit_claim_workspace",
        lambda _job_id, _claim_attempt: (project_workspace, workspace),
    )
    monkeypatch.setattr(
        local_worker,
        "prepare_video_edit_cleanup_intent",
        lambda **kwargs: (
            {
                "job_id": kwargs["job_id"],
                "workspace_key": project_workspace.name,
            },
            {
                "persisted": True,
                "workspace_present": True,
                "workspace_key": project_workspace.name,
            },
        ),
    )

    def reconcile_cleanup(_intent: dict) -> dict:
        events.append("cleanup")
        local_worker.shutil.rmtree(project_workspace)
        return {"ok": True, "removed": True}

    monkeypatch.setattr(
        local_worker,
        "reconcile_video_edit_cleanup_intent",
        reconcile_cleanup,
    )
    monkeypatch.setattr(local_worker, "TELEGRAM_BOT_TOKEN", "123:test-token")
    monkeypatch.setattr(
        local_worker,
        "_video_edit_download_asset",
        lambda *_args, **_kwargs: str(source),
    )
    monkeypatch.setattr(
        local_worker,
        "delivery_file_allowed",
        lambda *_args, **_kwargs: True,
    )

    def probe_video(path, **_kwargs) -> dict:
        artifact = Path(path)
        if artifact.name == "source.mp4":
            return {
                **_valid_source_probe(),
                "duration": 3.0,
                "duration_ms": 3_000,
                "bytes": artifact.stat().st_size,
            }
        return {
            **_valid_source_probe(),
            "duration": 1.0,
            "duration_ms": 1_000,
            "video_codec": "h264",
            "bytes": artifact.stat().st_size,
        }

    monkeypatch.setattr(
        local_worker.video_local_validation,
        "probe_video_file",
        probe_video,
    )

    def execute_split(_source, ranges, *, workspace, **_kwargs) -> dict:
        items = list(ranges)
        rendered_ranges.append(
            [(int(item.start_ms), int(item.end_ms)) for item in items]
        )
        outputs = []
        for item in items:
            path = Path(workspace) / local_worker.split_output_name(
                item.index,
                len(items),
            )
            path.write_bytes(
                f"part:{item.start_ms}:{item.end_ms}".encode("ascii")
            )
            outputs.append(
                {
                    "index": item.index,
                    "path": str(path),
                    "duration_ms": item.end_ms - item.start_ms,
                    "validation": probe_video(path),
                }
            )
        return {"ok": True, "outputs": outputs}

    monkeypatch.setattr(local_worker, "execute_split_plan", execute_split)

    def write_checkpoint(destination, checkpoint):
        events.append("checkpoint")
        checkpoints.append((Path(destination), checkpoint))
        return REAL_WRITE_CHECKPOINT_ATOMIC(destination, checkpoint)

    monkeypatch.setattr(
        video_edit_long_media,
        "write_checkpoint_atomic",
        write_checkpoint,
    )

    def deliver(*_args, **kwargs):
        events.append("transport")
        if callable(delivery_result):
            return delivery_result(*_args, **kwargs)
        if isinstance(delivery_result, BaseException):
            raise delivery_result
        return delivery_result

    monkeypatch.setattr(
        video_edit_media_transport,
        "send_artifact_from_path",
        deliver,
    )

    def update_job(
        job_id,
        status,
        error_short="",
        output_url="",
        output_file_id="",
        **_kwargs,
    ) -> dict:
        update = {
            "job_id": job_id,
            "status": status,
            "detail": error_short,
            "output_url": output_url,
            "output_file_id": output_file_id,
        }
        updates.append(update)
        try:
            detail = json.loads(error_short or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            detail = {}
        cursor = detail.get("delivery_cursor") if isinstance(detail, dict) else None
        is_pre_send = (
            status == "running"
            and isinstance(cursor, dict)
            and cursor.get("state") == "sending"
        )
        is_terminal = status != "running"
        outcome = (
            pre_send_update_result
            if is_pre_send
            else terminal_update_result if is_terminal else None
        )
        if is_pre_send:
            events.append("pre_send_ack")
        elif is_terminal:
            events.append("terminal_ack")
        if isinstance(outcome, BaseException):
            raise outcome
        return {"ok": True} if outcome is None else outcome

    monkeypatch.setattr(local_worker, "update_job", update_job)

    source_metadata = {
        **_valid_source_probe(),
        "duration": 3.0,
        "duration_ms": 3_000,
        "bytes": len(b"source"),
    }
    payload = {
        "local1_contract": 1,
        "product_type": video_editengine1.PRODUCT_TYPE,
        "engine_route": video_editengine1.ENGINE_ROUTE,
        "worker_owner": video_editengine1.OUTBOX_OWNER,
        "worker_capability": video_editengine1.WORKER_CAPABILITY,
        "source_file_id": "source-file",
        "source_file_name": "source.mp4",
        "source_metadata": source_metadata,
        "user_id": "9101",
        "chat_id": "9101",
        "local1_mode": "split",
        "price_xu": 0,
        "quoted_price_xu": 0,
        "quality_tier_id": "local-free",
        "charge_policy": "free_local_tool",
        "provider_call": False,
        "state_revision": 3,
        "manual_edit_plan": {},
        "rights_confirmation": _rights_confirmation(),
        "coverage_required": True,
        "split_ranges": [
            {"index": 1, "start_ms": 0, "end_ms": 1_000},
            {"index": 2, "start_ms": 1_000, "end_ms": 2_000},
            {"index": 3, "start_ms": 2_000, "end_ms": 3_000},
        ],
    }
    run_error: BaseException | None = None
    try:
        local_worker.run_video_local_edit(
            {
                "id": 9501,
                "claim_attempt": claim_attempt,
                "user_id": 9101,
                "job_type": video_editengine1.WORKER_JOB_TYPE,
                "input_file_id": json.dumps(payload),
            }
        )
    except BaseException as exc:
        run_error = exc
    return {
        "terminal": updates[-1],
        "updates": updates,
        "events": events,
        "checkpoints": checkpoints,
        "rendered_ranges": rendered_ranges,
        "project_workspace": project_workspace,
        "workspace": workspace,
        "run_error": run_error,
    }


def test_split_reclaim_reuses_valid_parts_and_renders_only_corrupt_part(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = _run_split_checkpoint_case(
        monkeypatch,
        tmp_path,
        AssertionError("transport must not start without sending ACK"),
        claim_attempt=1,
        project_name="split-reclaim-project",
        pre_send_update_result={"ok": False},
        terminal_update_result={"ok": False},
    )

    assert first["rendered_ranges"] == [[(0, 1_000), (1_000, 2_000), (2_000, 3_000)]]
    assert first["events"].count("transport") == 0
    assert len(first["checkpoints"]) == 3
    second_checkpoint = first["checkpoints"][1][1]
    corrupt_part = (
        first["project_workspace"]
        / second_checkpoint.canonical.relative_path
    )
    corrupt_part.write_bytes(b"corrupt-part-two")

    delivered_paths: list[Path] = []

    def deliver_parts(*_args, **kwargs):
        artifact = Path(kwargs["artifact"])
        delivered_paths.append(artifact)
        payload = artifact.read_bytes()
        return video_edit_media_transport.DeliveryReceipt(
            message_id=str(2000 + len(delivered_paths)),
            file_id=f"split-file-{len(delivered_paths)}",
            delivery_method="sendVideo",
            bytes_sent=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )

    second = _run_split_checkpoint_case(
        monkeypatch,
        tmp_path,
        deliver_parts,
        claim_attempt=2,
        project_name="split-reclaim-project",
    )

    assert second["run_error"] is None
    assert second["rendered_ranges"] == [[(1_000, 2_000)]]
    assert [path.parent.name for path in delivered_paths] == [
        "claim_1",
        "claim_2",
        "claim_1",
    ]
    assert second["events"].count("transport") == 3
    terminal_detail = json.loads(second["terminal"]["detail"])
    assert second["terminal"]["status"] == "succeeded"
    assert terminal_detail["stage"] == "delivered"


@pytest.mark.parametrize(
    "pre_send_ack",
    [
        {"ok": False},
        {},
        RuntimeError("delivery_cursor_persistence_unavailable"),
    ],
    ids=["false", "malformed", "exception"],
)
def test_manual_delivery_does_not_call_transport_without_true_sending_cursor_ack(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    pre_send_ack: object,
) -> None:
    result = _run_manual_delivery_case(
        monkeypatch,
        tmp_path,
        video_edit_media_transport.DeliveryReceipt(
            message_id="1001",
            file_id="manual-file",
            delivery_method="sendVideo",
            bytes_sent=len(b"valid-mp4-output"),
            sha256="a" * 64,
        ),
        pre_send_update_result=pre_send_ack,
        record_events=True,
    )

    assert result["events"].count("transport") == 0


def test_manual_delivery_acknowledges_terminal_state_before_workspace_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = _run_manual_delivery_case(
        monkeypatch,
        tmp_path,
        video_edit_media_transport.DeliveryReceipt(
            message_id="1001",
            file_id="manual-file",
            delivery_method="sendVideo",
            bytes_sent=len(b"valid-mp4-output"),
            sha256="a" * 64,
        ),
        record_events=True,
    )

    assert result["events"].index("terminal_ack") < result["events"].index("cleanup")


def test_deterministic_transport_rejection_persists_rejected_before_terminal_ack_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result = _run_manual_delivery_case(
        monkeypatch,
        tmp_path,
        video_edit_media_transport.MediaTransferError("delivery_rejected"),
        record_events=True,
        claim_attempt=11,
        workspace_name="deterministic-rejection",
    )

    checkpoint_states = []
    for update in result["updates"]:
        detail = json.loads(update["detail"] or "{}")
        cursor = detail.get("delivery_cursor") if isinstance(detail, dict) else None
        if update["status"] == "running" and isinstance(cursor, dict):
            checkpoint_states.append(cursor["state"])
    terminal_detail = json.loads(result["terminal"]["detail"])
    terminal_cursor = video_edit_long_media.DeliveryCursor.from_mapping(
        terminal_detail["delivery_cursor"]
    )

    assert result["run_error"] is None
    assert checkpoint_states == ["sending", "rejected"]
    assert result["terminal"]["status"] == "failed"
    assert terminal_detail["stage"] == "failed_no_charge"
    assert terminal_cursor.state == "rejected"
    assert terminal_cursor.output_index == 1
    assert terminal_cursor.deterministic is True
    assert terminal_cursor.rejection_code == "delivery_rejected"
    assert result["events"].index("pre_send_ack") < result["events"].index("transport")
    assert result["events"].index("transport") < result["events"].index("rejected_ack")
    assert result["events"].index("rejected_ack") < result["events"].index("terminal_ack")
    assert result["events"].index("terminal_ack") < result["events"].index("cleanup")
    assert not result["workspace"].exists()
    assert not result["evidence"].exists()


def test_deterministic_transport_rejection_checkpoint_failure_is_unknown_and_preserves_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    failures = (
        ("false", {"ok": False}),
        ("malformed", {}),
        ("exception", RuntimeError("rejected_checkpoint_unavailable")),
    )

    for name, rejected_ack in failures:
        result = _run_manual_delivery_case(
            monkeypatch,
            tmp_path,
            video_edit_media_transport.MediaTransferError("delivery_rejected"),
            rejected_update_result=rejected_ack,
            record_events=True,
            claim_attempt=12,
            workspace_name=f"deterministic-rejection-{name}",
        )
        detail = json.loads(result["terminal"]["detail"])
        cursor = video_edit_long_media.DeliveryCursor.from_mapping(
            detail["delivery_cursor"]
        )

        assert result["run_error"] is None
        assert result["terminal"]["status"] == "failed"
        assert detail["stage"] == "delivery_unknown"
        assert cursor.state == "unknown"
        assert result["events"].count("rejected_ack") == 1
        assert result["events"].count("terminal_ack") == 1
        assert result["events"].count("cleanup") == 0
        assert result["workspace"].exists()
        assert result["evidence"].exists()


@pytest.mark.parametrize(
    "terminal_ack",
    [
        {"ok": False},
        {},
        RuntimeError("terminal_delivery_ack_unavailable"),
    ],
    ids=["false", "malformed", "exception"],
)
def test_delivery_unknown_keeps_workspace_when_terminal_ack_is_not_true(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    terminal_ack: object,
) -> None:
    result = _run_manual_delivery_case(
        monkeypatch,
        tmp_path,
        RuntimeError("telegram_delivery_outcome_uncertain"),
        terminal_update_result=terminal_ack,
        record_events=True,
    )

    detail = json.loads(result["terminal"]["detail"])
    assert detail["stage"] == "delivery_unknown"
    assert result["events"].count("cleanup") == 0
    assert result["workspace"].exists()
    assert result["evidence"].exists()


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


def test_video_edit_job_update_returns_409_before_local_state_mutation_for_stale_owner() -> None:
    endpoint, events, updates, connection, renew_calls = _compiled_video_edit_job_update_endpoint(
        payload={"id": 77, "status": "running", "worker_id": "worker-b"},
        previous_job={
            "id": 77,
            "job_type": video_editengine1.WORKER_JOB_TYPE,
            "worker_id": "worker-a",
        },
        lease_renewed=False,
    )

    with pytest.raises(_EndpointHTTPException) as failure:
        asyncio.run(endpoint(_EndpointRequest({"x-worker-id": "worker-b"})))

    assert failure.value.status_code == 409
    assert updates == []
    assert renew_calls == []
    assert _mutation_events(events) == []
    assert connection.commit_calls == 0
    assert connection.close_calls == 0


def test_video_edit_job_update_binds_reporter_to_claimed_worker_before_mutation() -> None:
    previous_job = {
        "id": 78,
        "job_type": video_editengine1.WORKER_JOB_TYPE,
        "worker_id": "worker-a:host-a:78",
        "worker_instance_id": "worker-a:host-a:78",
        "claim_attempt": 1,
    }
    endpoint, rejected_events, rejected_updates, rejected_connection, rejected_renew_calls = _compiled_video_edit_job_update_endpoint(
        payload={"id": 78, "status": "running", "worker_id": "worker-b"},
        previous_job=previous_job,
        lease_renewed=True,
    )

    # Shared-token authentication cannot make payload.worker_id authoritative.
    with pytest.raises(_EndpointHTTPException) as failure:
        asyncio.run(endpoint(_EndpointRequest({"x-worker-id": "worker-a"})))
    assert failure.value.status_code == 409
    assert "token_auth" in rejected_events
    assert rejected_updates == []
    assert rejected_renew_calls == []
    assert _mutation_events(rejected_events) == []
    assert rejected_connection.commit_calls == 0
    assert rejected_connection.close_calls == 0

    endpoint, accepted_events, accepted_updates, accepted_connection, accepted_renew_calls = _compiled_video_edit_job_update_endpoint(
        payload={
            "id": 78,
            "status": "running",
            "worker_id": "worker-a",
            "worker_instance_id": "worker-a:host-a:78",
            "claim_attempt": 1,
            "stage": "processing_video",
        },
        previous_job=previous_job,
        lease_renewed=True,
    )
    response = asyncio.run(endpoint(_EndpointRequest({"x-worker-id": "worker-a"})))

    assert response["ok"] is True
    assert len(accepted_updates) == 1
    assert accepted_updates[0]["worker_id"] == "worker-a:host-a:78"
    assert len(accepted_renew_calls) == 1
    assert accepted_events.index("renew_worker_lease") < accepted_events.index(
        f"{MUTATION_EVENT_PREFIX}update_local_worker_job"
    )
    assert accepted_connection.commit_calls == 1
    assert accepted_connection.close_calls == 1


def test_video_edit_job_update_rejects_exact_owner_when_lease_renewal_fails_before_mutation() -> None:
    endpoint, events, updates, connection, renew_calls = _compiled_video_edit_job_update_endpoint(
        payload={
            "id": 79,
            "status": "running",
            "worker_id": "worker-a",
            "worker_instance_id": "worker-a:host-a:79",
            "claim_attempt": 1,
            "stage": "processing_video",
        },
        previous_job={
            "id": 79,
            "job_type": video_editengine1.WORKER_JOB_TYPE,
            "worker_id": "worker-a:host-a:79",
            "worker_instance_id": "worker-a:host-a:79",
            "claim_attempt": 1,
        },
        lease_renewed=False,
    )

    with pytest.raises(_EndpointHTTPException) as failure:
        asyncio.run(endpoint(_EndpointRequest({"x-worker-id": "worker-a"})))

    assert failure.value.status_code == 409
    assert len(renew_calls) == 1
    assert _mutation_events(events) == []
    assert connection.commit_calls == 0
    assert connection.close_calls == 1


@pytest.mark.parametrize(
    ("requested_lease_seconds", "expected_lease_seconds"),
    [(1, 30), (99_999, 3_600)],
)
def test_video_edit_endpoint_scopes_bounded_lease_and_stage_to_video_edit(
    requested_lease_seconds: int,
    expected_lease_seconds: int,
) -> None:
    endpoint, events, updates, connection, renew_calls = _compiled_video_edit_job_update_endpoint(
        payload={
            "id": 80,
            "status": "running",
            "worker_id": "worker-a",
            "worker_instance_id": "worker-a:host-a:80",
            "claim_attempt": 1,
            "lease_seconds": requested_lease_seconds,
            "stage": "processing_video",
        },
        previous_job={
            "id": 80,
            "job_type": video_editengine1.WORKER_JOB_TYPE,
            "worker_id": "worker-a:host-a:80",
            "worker_instance_id": "worker-a:host-a:80",
            "claim_attempt": 1,
        },
        lease_renewed=True,
    )

    response = asyncio.run(endpoint(_EndpointRequest({"x-worker-id": "worker-a"})))

    assert response["ok"] is True
    assert len(renew_calls) == 1
    renew_args, renew_kwargs = renew_calls[0]
    assert renew_args == (connection,)
    assert renew_kwargs["worker_job_id"] == 80
    assert renew_kwargs["lease_owner"] == "worker-a:host-a:80"
    assert renew_kwargs["claim_attempt"] == 1
    lease_start = datetime.strptime(renew_kwargs["now"], "%Y-%m-%d %H:%M:%S")
    lease_end = datetime.strptime(renew_kwargs["lease_expires_at"], "%Y-%m-%d %H:%M:%S")
    assert int((lease_end - lease_start).total_seconds()) == expected_lease_seconds
    assert json.loads(updates[0]["error_short"])["stage"] == "processing_video"
    assert events.index("renew_worker_lease") < events.index(
        f"{MUTATION_EVENT_PREFIX}update_local_worker_job"
    )
    assert connection.commit_calls == 1
    assert connection.close_calls == 1


@pytest.mark.parametrize(
    ("worker_status", "terminal_stage"),
    [("succeeded", "delivered"), ("failed", "failed_no_charge")],
)
def test_video_edit_endpoint_accepts_truthful_terminal_worker_stages(
    worker_status: str,
    terminal_stage: str,
) -> None:
    endpoint, _events, updates, connection, renew_calls = (
        _compiled_video_edit_job_update_endpoint(
            payload={
                "id": 82,
                "status": worker_status,
                "worker_id": "worker-a",
                "worker_instance_id": "worker-a:host-a:82",
                "claim_attempt": 1,
                "stage": terminal_stage,
            },
            previous_job={
                "id": 82,
                "job_type": video_editengine1.WORKER_JOB_TYPE,
                "worker_id": "worker-a:host-a:82",
                "worker_instance_id": "worker-a:host-a:82",
                "claim_attempt": 1,
            },
            lease_renewed=True,
        )
    )

    response = asyncio.run(endpoint(_EndpointRequest({"x-worker-id": "worker-a"})))

    assert response["ok"] is True
    assert len(renew_calls) == 1
    assert json.loads(updates[0]["error_short"])["stage"] == terminal_stage
    assert connection.commit_calls == 1
    assert connection.close_calls == 1


def test_non_video_job_update_never_renews_or_receives_video_edit_stage_handling() -> None:
    endpoint, events, updates, _connection, renew_calls = _compiled_video_edit_job_update_endpoint(
        payload={
            "id": 81,
            "status": "running",
            "worker_id": "worker-a",
            "lease_seconds": 99_999,
            "stage": "processing_video",
        },
        previous_job={"id": 81, "job_type": "other_local_job", "worker_id": "worker-a"},
        lease_renewed=True,
    )

    response = asyncio.run(endpoint(_EndpointRequest({"x-worker-id": "worker-a"})))

    assert response["ok"] is True
    assert renew_calls == []
    assert "renew_worker_lease" not in events
    assert updates[0]["error_short"] == ""


def test_worker_poll_claims_video_edit_canonically_with_process_instance_owner() -> None:
    canonical_job = {
        "id": 91,
        "job_type": video_editengine1.WORKER_JOB_TYPE,
        "worker_id": "worker-a:host-a:99",
        "claim_attempt": 4,
        "artifact_receipt_prefix": [_artifact(1)],
        "delivery_cursor": 1,
        "source_sha256": "a" * 64,
    }
    endpoint, events, connection, claim_calls = _compiled_worker_poll_endpoint(
        canonical_job=canonical_job,
        legacy_job=None,
    )

    response = asyncio.run(
        endpoint(
            _PollRequest(
                {
                    "worker_id": "worker-a",
                    "worker_instance_id": "worker-a:host-a:99",
                    "lease_seconds": "99999",
                    "video_edit_resume_version": "1",
                }
            )
        )
    )

    assert response["ok"] is True
    assert response["job"] == canonical_job
    assert len(claim_calls) == 1
    claim_args, claim_kwargs = claim_calls[0]
    assert claim_args == (connection,)
    assert claim_kwargs["lease_owner"] == "worker-a:host-a:99"
    assert claim_kwargs["lease_seconds"] == 3600
    assert claim_kwargs["supports_receipt_prefix_resume"] is True
    assert "now" in claim_kwargs
    assert "legacy_queue_select" not in events
    assert "legacy_queue_claim" not in events
    assert connection.commit_calls == 1
    assert events.index("canonical_claim") < events.index("legacy_db_commit")
    assert canonical_job["claim_attempt"] == 4
    assert canonical_job["artifact_receipt_prefix"] == [_artifact(1)]
    assert canonical_job["delivery_cursor"] == 1
    assert canonical_job["source_sha256"] == "a" * 64


def test_worker_poll_keeps_non_video_jobs_on_the_legacy_queue_path() -> None:
    legacy_job = {
        "id": 92,
        "job_type": "other_local_job",
        "status": "queued",
        "worker_id": "",
    }
    endpoint, events, connection, claim_calls = _compiled_worker_poll_endpoint(
        canonical_job=None,
        legacy_job=legacy_job,
    )

    response = asyncio.run(
        endpoint(
            _PollRequest(
                {
                    "worker_id": "worker-a",
                    "worker_instance_id": "worker-a:host-a:99",
                    "lease_seconds": "600",
                }
            )
        )
    )

    assert response["ok"] is True
    assert response["job"]["id"] == 92
    assert response["job"]["job_type"] == "other_local_job"
    assert len(claim_calls) == 1
    assert claim_calls[0][1]["supports_receipt_prefix_resume"] is False
    assert "legacy_queue_select" in events
    assert "legacy_queue_claim" in events
    assert connection.commit_calls == 1


def test_video_edit_update_requires_exact_instance_and_claim_attempt_before_mutation() -> None:
    previous_job = {
        "id": 93,
        "job_type": video_editengine1.WORKER_JOB_TYPE,
        "worker_id": "worker-a:host-a:99",
        "worker_instance_id": "worker-a:host-a:99",
        "claim_attempt": 8,
    }
    for payload in (
        {
            "id": 93,
            "status": "running",
            "worker_id": "worker-a",
            "worker_instance_id": "worker-a:host-b:101",
            "claim_attempt": 8,
            "stage": "processing_video",
        },
        {
            "id": 93,
            "status": "running",
            "worker_id": "worker-a",
            "worker_instance_id": "worker-a:host-a:99",
            "claim_attempt": 7,
            "stage": "processing_video",
        },
    ):
        endpoint, events, updates, connection, renew_calls = _compiled_video_edit_job_update_endpoint(
            payload=payload,
            previous_job=previous_job,
            lease_renewed=True,
        )

        with pytest.raises(_EndpointHTTPException) as failure:
            asyncio.run(endpoint(_EndpointRequest({"x-worker-id": "worker-a"})))

        assert failure.value.status_code == 409
        assert renew_calls == []
        assert updates == []
        assert _mutation_events(events) == []
        assert connection.commit_calls == 0
        assert connection.rollback_calls == 0


def test_video_edit_update_renews_and_persists_local_and_canonical_state_in_one_transaction() -> None:
    endpoint, events, updates, connection, renew_calls = _compiled_video_edit_job_update_endpoint(
        payload={
            "id": 94,
            "status": "running",
            "worker_id": "worker-a",
            "worker_instance_id": "worker-a:host-a:99",
            "claim_attempt": 9,
            "stage": "processing_video",
        },
        previous_job={
            "id": 94,
            "job_type": video_editengine1.WORKER_JOB_TYPE,
            "worker_id": "worker-a:host-a:99",
            "worker_instance_id": "worker-a:host-a:99",
            "claim_attempt": 9,
        },
        lease_renewed=True,
    )

    response = asyncio.run(endpoint(_EndpointRequest({"x-worker-id": "worker-a"})))

    assert response["ok"] is True
    assert len(renew_calls) == 1
    _renew_args, renew_kwargs = renew_calls[0]
    assert renew_kwargs["lease_owner"] == "worker-a:host-a:99"
    assert renew_kwargs["claim_attempt"] == 9
    assert len(updates) == 1
    assert connection in updates[0].values()
    assert len(connection.canonical_updates) == 1
    assert connection.canonical_updates[0]["worker_job_id"] == 94
    assert connection.canonical_updates[0]["worker_status"] == "running"
    assert events.index("renew_worker_lease") < events.index(
        f"{MUTATION_EVENT_PREFIX}update_local_worker_job"
    )
    assert events.index(f"{MUTATION_EVENT_PREFIX}update_local_worker_job") < events.index(
        f"{MUTATION_EVENT_PREFIX}record_worker_update"
    )
    assert events.index(f"{MUTATION_EVENT_PREFIX}record_worker_update") < events.index("db_commit")
    assert connection.commit_calls == 1
    assert connection.rollback_calls == 0


def test_video_edit_delivery_unknown_stage_maps_raw_running_to_local_failed() -> None:
    endpoint, events, updates, connection, _renew_calls = (
        _compiled_video_edit_job_update_endpoint(
            payload={
                "id": 97,
                "status": "running",
                "worker_id": "worker-a",
                "worker_instance_id": "worker-a:host-a:99",
                "claim_attempt": 12,
                "stage": "delivery_unknown",
            },
            previous_job={
                "id": 97,
                "job_type": video_editengine1.WORKER_JOB_TYPE,
                "worker_id": "worker-a:host-a:99",
                "worker_instance_id": "worker-a:host-a:99",
                "claim_attempt": 12,
            },
            lease_renewed=True,
            canonical_result={
                "status": "delivery_unknown",
                "blocker": "telegram_delivery_receipt_commit_uncertain",
            },
        )
    )

    response = asyncio.run(endpoint(_EndpointRequest({"x-worker-id": "worker-a"})))

    assert response["job"]["status"] == "failed"
    assert updates[-1]["status"] == "failed"
    assert events.index(f"{MUTATION_EVENT_PREFIX}update_local_worker_job") < events.index(
        f"{MUTATION_EVENT_PREFIX}record_worker_update"
    )
    assert events.index(f"{MUTATION_EVENT_PREFIX}record_worker_update") < events.index(
        "db_commit"
    )
    assert connection.commit_calls == 1


def test_video_edit_reconciles_raw_success_to_canonical_delivery_unknown_before_commit() -> None:
    canonical_blocker = "telegram_delivery_receipt_invalid"
    endpoint, events, updates, connection, _renew_calls = (
        _compiled_video_edit_job_update_endpoint(
            payload={
                "id": 98,
                "status": "succeeded",
                "worker_id": "worker-a",
                "worker_instance_id": "worker-a:host-a:99",
                "claim_attempt": 13,
                "stage": "delivered",
            },
            previous_job={
                "id": 98,
                "job_type": video_editengine1.WORKER_JOB_TYPE,
                "worker_id": "worker-a:host-a:99",
                "worker_instance_id": "worker-a:host-a:99",
                "claim_attempt": 13,
            },
            lease_renewed=True,
            canonical_result={
                "status": "delivery_unknown",
                "blocker": canonical_blocker,
            },
        )
    )

    response = asyncio.run(endpoint(_EndpointRequest({"x-worker-id": "worker-a"})))

    assert [update["status"] for update in updates] == ["succeeded", "failed"]
    reconciled_detail = json.loads(updates[-1]["error_short"])
    assert reconciled_detail["stage"] == "delivery_unknown"
    assert reconciled_detail["reason"] == canonical_blocker
    assert response["job"] == updates[-1]
    canonical_mutation_events = [
        event
        for event in _mutation_events(events)
        if event
        in {
            f"{MUTATION_EVENT_PREFIX}update_local_worker_job",
            f"{MUTATION_EVENT_PREFIX}record_worker_update",
        }
    ]
    assert canonical_mutation_events == [
        f"{MUTATION_EVENT_PREFIX}update_local_worker_job",
        f"{MUTATION_EVENT_PREFIX}record_worker_update",
        f"{MUTATION_EVENT_PREFIX}update_local_worker_job",
    ]
    assert events.index(
        canonical_mutation_events[-1],
        events.index(canonical_mutation_events[1]) + 1,
    ) < events.index("db_commit")
    assert connection.commit_calls == 1


def test_video_edit_canonical_persistence_failure_rolls_back_local_mutation_and_never_acknowledges() -> None:
    endpoint, events, updates, connection, renew_calls = _compiled_video_edit_job_update_endpoint(
        payload={
            "id": 95,
            "status": "running",
            "worker_id": "worker-a",
            "worker_instance_id": "worker-a:host-a:99",
            "claim_attempt": 10,
            "stage": "processing_video",
        },
        previous_job={
            "id": 95,
            "job_type": video_editengine1.WORKER_JOB_TYPE,
            "worker_id": "worker-a:host-a:99",
            "worker_instance_id": "worker-a:host-a:99",
            "claim_attempt": 10,
        },
        lease_renewed=True,
        canonical_failure=sqlite3.OperationalError("canonical write failed"),
    )

    with pytest.raises(_EndpointHTTPException) as failure:
        asyncio.run(endpoint(_EndpointRequest({"x-worker-id": "worker-a"})))

    assert failure.value.status_code == 500
    assert len(renew_calls) == 1
    assert len(updates) == 1
    assert f"{MUTATION_EVENT_PREFIX}record_worker_update" in events
    assert events.index("renew_worker_lease") < events.index(
        f"{MUTATION_EVENT_PREFIX}update_local_worker_job"
    )
    assert events.index(f"{MUTATION_EVENT_PREFIX}record_worker_update") < events.index("db_rollback")
    assert events.index("db_rollback") < events.index("db_close")
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 1


def test_stage_only_liveness_update_preserves_allowlisted_durable_checkpoint_fields() -> None:
    durable_receipts = [_artifact(1)]
    endpoint, _events, updates, _connection, _renew_calls = _compiled_video_edit_job_update_endpoint(
        payload={
            "id": 96,
            "status": "running",
            "worker_id": "worker-a",
            "worker_instance_id": "worker-a:host-a:99",
            "claim_attempt": 11,
            "stage": "processing_video",
        },
        previous_job={
            "id": 96,
            "job_type": video_editengine1.WORKER_JOB_TYPE,
            "worker_id": "worker-a:host-a:99",
            "worker_instance_id": "worker-a:host-a:99",
            "claim_attempt": 11,
            "error_short": json.dumps(
                {
                    "stage": "delivering",
                    "artifact_receipts": durable_receipts,
                    "delivery_attempt": 2,
                    "source_sha256": "a" * 64,
                    "expected_output_count": 2,
                    "untrusted_worker_note": "must not become durable",
                }
            ),
        },
        lease_renewed=True,
    )

    response = asyncio.run(endpoint(_EndpointRequest({"x-worker-id": "worker-a"})))

    assert response["ok"] is True
    assert len(updates) == 1
    checkpoint = json.loads(updates[0]["error_short"])
    assert checkpoint == {
        "stage": "processing_video",
        "artifact_receipts": durable_receipts,
        "delivery_attempt": 2,
        "source_sha256": "a" * 64,
        "expected_output_count": 2,
    }
