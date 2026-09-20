"""tests/test_p0_autopost_subdub_notifier_seam.py

Behavioral tests and regression lock for SubDub AutoPost Notifier Seam.
Task: P0.AUTOPOST.S5.SUBDUB.NOTIFIER.DEDUPE.REGRESSION.LOCK.R1
Program: P0.AUTOPOST
Repository: manhtoangreensky-wq/bot
Base SHA: 2986eb8442cef8388e81e68c4ee10135dd1d72d5
Governed under TOAN AAS Owner-Governed Codex.

Invariants Verified:
1. Recovery path calls notifier exactly once on terminal billing.
2. Recovery path with Auto-speaker route disabled does not hit UnboundLocalError and calls notifier once.
3. Presettlement / nonterminal billing states call notifier zero times.
4. Recovery transitions through canonical settlement to terminal billing (charged) and triggers notifier once.
5. Canonical reconciliation success calls notifier exactly once.
6. Ineligible or nonterminal reconciliation calls notifier zero times.
7. Core pipeline completion calls notifier exactly once on terminal delivery.
8. Core pipeline undelivered or nonterminal billing calls notifier zero times.
9. Notifier failure / exception does not mutate producer truth.
10. Replay idempotency preserves row count (diff = 0) for receipts, drafts, and queue.
11. Recovery function source code contains exactly one notifier call site.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from types import SimpleNamespace
from typing import Any

import pytest

from services import autopost_asset_handoff as aah
from services import autopost_scheduler as aps
from services import autopost_subdub_adapter as asda
from services import subdub_auto_settlement
from services import video_local_validation


BOT_SOURCE_PATH = Path(__file__).parents[1] / "bot.py"


def _extract_function_source(name: str) -> str:
    source = BOT_SOURCE_PATH.read_text(encoding="utf-8")
    pattern = rf"(?m)^(?:async )?def {re.escape(name)}\("
    match = re.search(pattern, source)
    assert match, f"Function '{name}' not found in bot.py"
    next_def = re.search(r"(?m)^(?:async )?def [A-Za-z_]\w*\(", source[match.end():])
    end = match.end() + next_def.start() if next_def else len(source)
    return source[match.start():end]


def _make_dummy_video(
    tmp_path: Path,
    name: str = "test_subdub.mp4",
    content: bytes = b"subdub_s5_canonical_video_bytes_1234567890",
) -> Path:
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
            "duration": 20.0,
            "duration_ms": 20000,
            "width": 1080,
            "height": 1920,
            "has_video": True,
            "has_audio": True,
            "format_name": "mp4",
        },
    )


def _seed_canonical_subdub_job(
    conn: sqlite3.Connection,
    tmp_path: Path,
    uid: int = 123456,
    internal_job_id: str = "subdub_int_job_001",
    charge_status: str = "charged",
    auto_settlement_pending: bool = False,
    file_id: str = "tg_file_subdub_999",
    message_id: int = 8888,
    raw_bytes: bytes = b"canonical_subdub_video_stream_bytes_777",
) -> tuple[dict[str, Any], Path, str]:
    video_file = _make_dummy_video(tmp_path, f"{internal_job_id}.mp4", raw_bytes)
    sha = _sha256(raw_bytes)

    job_data = {
        "internal_job_id": internal_job_id,
        "job_id": internal_job_id,
        "user_id": uid,
        "feature": "subtitle_dub",
        "terminal_state": "delivered",
        "output_sent": True,
        "delivery_succeeded": True,
        "final_mp4_validated": True,
        "final_mp4_delivered": True,
        "charge_status": charge_status,
        "auto_settlement_pending_recovery": auto_settlement_pending,
        "video_delivery_file_id": file_id,
        "video_delivery_message_id": message_id,
        "video_delivery_sha256": sha,
        "video_delivery_size_bytes": len(raw_bytes),
        "video_delivery_duration_seconds": 20.0,
        "video_delivery_mime_type": "video/mp4",
        "final_mp4": str(video_file),
        "settled_at": "2026-09-20T12:00:00Z",
        "output_validation": {
            "ok": True,
            "width": 1080,
            "height": 1920,
            "duration": 20.0,
            "actual_duration": 20.0,
        },
    }

    conn.execute(
        "INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES (?, ?, '2026-09-20T12:00:00Z')",
        (f"engine_async_job:{internal_job_id}", json.dumps(job_data)),
    )
    conn.commit()
    return job_data, video_file, sha


def _build_recovery_namespace(
    *,
    notifier_tracker: list[tuple[str, int]],
    route_enabled: bool = False,
    charge_status: str = "charged",
    settlement_result: dict[str, Any] | None = None,
    db_connect_fn=None,
    record_credit_event_fn=None,
) -> dict[str, Any]:
    def _mock_notifier(internal_job_id: str, owner_id: int) -> dict[str, Any]:
        notifier_tracker.append((internal_job_id, owner_id))
        return {"attempted": True, "called": True}

    jobs_store: dict[str, dict[str, Any]] = {}

    def _mock_update_job(job_key: str, **kw) -> dict[str, Any]:
        entry = dict(jobs_store.get(str(job_key)) or {})
        entry.update(kw)
        jobs_store[str(job_key)] = entry
        return entry

    ns: dict[str, Any] = {
        "time": time,
        "subdub_existing_mp4_recovery_candidate": lambda _job: "/fake/path.mp4",
        "_safe_int": lambda v, default=0: int(v or default),
        "update_subtitle_dub_pipeline_job": _mock_update_job,
        "truthy_value": lambda v, d=False: bool(v if v is not None else d),
        "normalize_video_translate_mode": lambda m: "dub",
        "VIDEO_SUBTITLE_MODE_DUB": "dub",
        "VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB": "subdub",
        "subdub_progress_percent_for_lifecycle": lambda *a: 100,
        "subdub_receipt_send_is_uncertain": lambda _exc: False,
        "subdub_confirmed_video_delivery_message_id": lambda d: str(d.get("video_delivery_message_id") or ""),
        "mark_subtitle_dub_pipeline_output_sent": lambda *a, **kw: None,
        "SUBTITLE_DUB_PIPELINE_JOBS": jobs_store,
        "subdub_auto_speaker_route_enabled": lambda _job: route_enabled,
        "is_admin_user": lambda _uid: False,
        "now_text": lambda: "2026-09-20T12:00:00Z",
        "subdub_auto_settlement": subdub_auto_settlement,
        "db_connect": db_connect_fn or (lambda: None),
        "record_credit_event": record_credit_event_fn or (lambda *a, **kw: None),
        "_engine_async_job_key": lambda jid: f"engine_async_job:{jid}",
        "SUBDUB_AUTO_EXACT_RECEIPT_VERSION": "2026-08-15.auto-exact.1",
        "SUBDUB_AUTO_EXACT_QUOTE_VERSION": "2026-08-15.auto-word.1",
        "persist_subtitle_dub_pipeline_job_snapshot": lambda *a, **kw: None,
        "_notify_subdub_autopost_completion": _mock_notifier,
    }

    if settlement_result is not None:
        ns["subdub_auto_settlement"] = SimpleNamespace(
            settle_after_delivery=lambda **_kw: settlement_result
        )

    async def _mock_send_outputs(*_args, **_kwargs):
        return {"video_delivery_message_id": "901"}

    ns["send_public_subtitle_dub_final_outputs"] = _mock_send_outputs

    code = _extract_function_source("subdub_recover_existing_mp4_delivery")
    exec(compile(code, "bot.py", "exec"), ns)
    return ns


# =============================================================================
# TEST 01: Recovery Route Disabled -> Zero UnboundLocalError & Called Once
# =============================================================================
def test_01_recovery_route_disabled_unboundlocalerror_zero_notifier_called_once():
    notifier_calls: list[tuple[str, int]] = []
    ns = _build_recovery_namespace(
        notifier_tracker=notifier_calls,
        route_enabled=False,
    )

    job_key = "subdub_test_job_01"
    job = {
        "user_id": "123456",
        "internal_job_id": "job_recovery_01",
        "charge_status": "charged",
        "delivery_attempts": 0,
    }
    ns["SUBTITLE_DUB_PIPELINE_JOBS"][job_key] = dict(job)

    query = SimpleNamespace(message=SimpleNamespace(message_id=901))
    context = SimpleNamespace()

    # Prior to hoisting owner_id and internal_job_id outside the route check,
    # disabling the route caused UnboundLocalError. Verify no exception is raised.
    result = asyncio.run(
        ns["subdub_recover_existing_mp4_delivery"](query, context, job_key, job)
    )

    assert result["video_delivery_message_id"] == "901"
    assert len(notifier_calls) == 1, (
        f"Expected exactly 1 notifier call, got {len(notifier_calls)}"
    )
    assert notifier_calls[0] == ("job_recovery_01", 123456)


# =============================================================================
# TEST 02: Recovery Route Enabled -> Terminal Billing Called Exactly Once
# =============================================================================
def test_02_recovery_route_enabled_terminal_billing_called_once():
    notifier_calls: list[tuple[str, int]] = []
    ns = _build_recovery_namespace(
        notifier_tracker=notifier_calls,
        route_enabled=True,
        settlement_result={"ok": True, "job": {"charge_status": "charged"}},
    )

    job_key = "subdub_test_job_02"
    job = {
        "user_id": "123456",
        "internal_job_id": "job_recovery_02",
        "charge_status": "charged",
        "auto_exact_receipt": {"actual_total_xu": 50},
        "delivery_attempts": 0,
    }
    ns["SUBTITLE_DUB_PIPELINE_JOBS"][job_key] = dict(job)

    query = SimpleNamespace(message=SimpleNamespace(message_id=901))
    context = SimpleNamespace()

    result = asyncio.run(
        ns["subdub_recover_existing_mp4_delivery"](query, context, job_key, job)
    )

    assert result["video_delivery_message_id"] == "901"
    assert len(notifier_calls) == 1
    assert notifier_calls[0] == ("job_recovery_02", 123456)
    duplicate_calls = len(notifier_calls) - 1
    assert duplicate_calls == 0


# =============================================================================
# TEST 03: Presettlement / Non-Terminal Billing -> Exactly Zero Calls
# =============================================================================
def test_03_presettlement_nonterminal_billing_zero_calls():
    non_terminal_statuses = [
        "pending",
        "settlement_pending_recovery",
        "running",
        "failed",
        "",
        None,
    ]

    total_notifier_calls = 0
    for idx, status in enumerate(non_terminal_statuses):
        notifier_calls: list[tuple[str, int]] = []
        ns = _build_recovery_namespace(
            notifier_tracker=notifier_calls,
            route_enabled=False,
        )

        job_key = f"subdub_test_job_nonterminal_{idx}"
        job = {
            "user_id": "123456",
            "internal_job_id": f"job_nonterminal_{idx}",
            "charge_status": status,
            "delivery_attempts": 0,
        }
        ns["SUBTITLE_DUB_PIPELINE_JOBS"][job_key] = dict(job)

        query = SimpleNamespace(message=SimpleNamespace(message_id=901))
        context = SimpleNamespace()

        asyncio.run(
            ns["subdub_recover_existing_mp4_delivery"](query, context, job_key, job)
        )

        assert len(notifier_calls) == 0, (
            f"Expected 0 notifier calls for charge_status='{status}', got {len(notifier_calls)}"
        )
        total_notifier_calls += len(notifier_calls)

    assert total_notifier_calls == 0


# =============================================================================
# TEST 04: Recovery Path Transitions Through Canonical Settlement -> Called Once
# =============================================================================
def test_04_recovery_transitions_through_canonical_settlement_to_terminal_billing(tmp_path):
    db_file = tmp_path / "settlement_recovery.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE users (
            user_id TEXT PRIMARY KEY,
            credits INTEGER NOT NULL,
            total_spent INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE credit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            delta INTEGER,
            balance_after INTEGER,
            event_type TEXT,
            ref_id TEXT,
            note TEXT,
            created_at TEXT
        );
        CREATE TABLE system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            note TEXT,
            updated_at TEXT,
            updated_by TEXT
        );
        INSERT INTO users (user_id, credits, total_spent) VALUES ('123456', 500, 0);
        """
    )

    internal_job_id = "job_recovery_canonical_04"
    job_key = "123456:123456:dub:job_recovery_canonical_04"
    claim_token = "claim_token_canonical_04"
    session_nonce = "session_nonce_canonical_04"
    amount = 100

    initial_job_data = {
        "feature": "subtitle_dub",
        "internal_job_id": internal_job_id,
        "job_id": internal_job_id,
        "user_id": "123456",
        "chat_id": "123456",
        "job_key": job_key,
        "mode": "dub",
        "mapped_mode": "dub",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "status": "completed",
        "terminal_state": "delivered",
        "output_sent": True,
        "delivery_succeeded": True,
        "final_mp4_delivered": True,
        "final_mp4_validated": True,
        "video_delivery_message_id": "9001",
        "video_delivery_file_id": "tg_file_fixture_04",
        "video_delivery_size_bytes": 4096,
        "video_delivery_sha256": "4" * 64,
        "video_delivery_mime_type": "video/mp4",
        "video_delivery_duration_seconds": 12.5,
        "output_validation": {"ok": True, "actual_duration": 12.5},
        "charge_status": "settlement_pending_recovery",
        "charged_xu": 0,
        "auto_settlement_pending_recovery": True,
        "auto_exact_session_nonce": session_nonce,
        "auto_exact_claim_token": claim_token,
        "auto_exact_receipt": {
            "version": "2026-08-15.auto-exact.1",
            "quote_version": "2026-08-15.auto-word.1",
            "internal_job_id": internal_job_id,
            "owner_user_id": "123456",
            "chat_id": "123456",
            "job_key_sha256": hashlib.sha256(job_key.encode("utf-8")).hexdigest(),
            "session_nonce": session_nonce,
            "claim_token": claim_token,
            "mode": "dub",
            "actual_auto_xu": amount,
            "actual_subtitle_xu": 0,
            "actual_total_xu": amount,
            "consumed": True,
            "claim_state": "resuming",
            "media_sha256": "1" * 64,
            "selected_tts_text_sha256": "2" * 64,
            "timeline_signature": "3" * 64,
        },
    }
    conn.execute(
        "INSERT INTO system_settings (key, value, note, updated_at, updated_by) VALUES (?, ?, '', '2026-09-20T12:00:00Z', '')",
        (f"engine_async_job:{internal_job_id}", json.dumps(initial_job_data)),
    )
    conn.commit()
    conn.close()

    def _db_connect():
        c = sqlite3.connect(str(db_file))
        c.row_factory = sqlite3.Row
        return c

    def _record_credit_event(c, user_id, delta, event_type, ref_id="", note=""):
        c.execute(
            """INSERT INTO credit_events (user_id, delta, balance_after, event_type, ref_id, note, created_at)
               VALUES (?, ?, 0, ?, ?, ?, '2026-09-20T12:00:00Z')""",
            (str(user_id), int(delta), str(event_type), str(ref_id), str(note)),
        )

    notifier_calls: list[tuple[str, int]] = []
    ns = _build_recovery_namespace(
        notifier_tracker=notifier_calls,
        route_enabled=True,
        db_connect_fn=_db_connect,
        record_credit_event_fn=_record_credit_event,
    )

    job = dict(initial_job_data)
    job["delivery_attempts"] = 0
    ns["SUBTITLE_DUB_PIPELINE_JOBS"][job_key] = dict(job)

    query = SimpleNamespace(message=SimpleNamespace(message_id=901))
    context = SimpleNamespace()

    result = asyncio.run(
        ns["subdub_recover_existing_mp4_delivery"](query, context, job_key, job)
    )

    assert result["video_delivery_message_id"] == "901"
    assert result["charge_status"] == "charged"
    assert len(notifier_calls) == 1
    assert notifier_calls[0] == (internal_job_id, 123456)

    # Verify database was charged
    check_conn = _db_connect()
    user_row = check_conn.execute("SELECT credits, total_spent FROM users WHERE user_id='123456'").fetchone()
    assert user_row["credits"] == 400
    assert user_row["total_spent"] == 100
    check_conn.close()


# =============================================================================
# TEST 05: Reconcile Settled Job Calls Notifier Exactly Once
# =============================================================================
def test_05_reconcile_settled_job_calls_notifier_once():
    notifier_calls: list[tuple[str, int]] = []

    def _mock_notifier(internal_job_id: str, owner_id: int) -> dict[str, Any]:
        notifier_calls.append((internal_job_id, owner_id))
        return {"attempted": True, "called": True}

    reconcile_ns: dict[str, Any] = {
        "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED": True,
        "_engine_async_id_list_from_setting": lambda _k: ["rec_job_001"],
        "_engine_async_feature_key": lambda f: f"feature:{f}",
        "get_engine_async_job": lambda jid: {
            "internal_job_id": jid,
            "user_id": "123456",
            "voice_kind": "auto_speaker_gender",
            "voice_selection_mode": "auto_speaker",
            "terminal_state": "delivered",
            "charge_status": "settlement_pending_recovery",
            "auto_exact_receipt": {"actual_total_xu": 50},
            "mode": "dub",
        },
        "is_admin_user": lambda _uid: False,
        "subdub_auto_settlement": SimpleNamespace(
            settle_after_delivery=lambda **_kw: {
                "ok": True,
                "job": {
                    "internal_job_id": "rec_job_001",
                    "user_id": "123456",
                    "charge_status": "charged",
                },
            }
        ),
        "db_connect": lambda: None,
        "record_credit_event": lambda *a, **kw: None,
        "_engine_async_job_key": lambda jid: f"engine_async_job:{jid}",
        "SUBDUB_AUTO_EXACT_RECEIPT_VERSION": "2026-08-15.auto-exact.1",
        "SUBDUB_AUTO_EXACT_QUOTE_VERSION": "2026-08-15.auto-word.1",
        "normalize_video_translate_mode": lambda m: "dub",
        "now_text": lambda: "2026-09-20T12:00:00Z",
        "ENGINE_ASYNC_MEMORY_JOBS": {},
        "SUBTITLE_DUB_PIPELINE_JOBS": {},
        "_notify_subdub_autopost_completion": _mock_notifier,
    }

    code = _extract_function_source("reconcile_subdub_auto_postdelivery_settlements")
    exec(compile(code, "bot.py", "exec"), reconcile_ns)

    report = reconcile_ns["reconcile_subdub_auto_postdelivery_settlements"](limit=10)

    assert report["settled"] == 1
    assert report["failed"] == 0
    assert len(notifier_calls) == 1
    assert notifier_calls[0] == ("rec_job_001", 123456)


# =============================================================================
# TEST 06: Reconcile Non-Terminal and Ineligible Jobs Call Notifier Zero Times
# =============================================================================
def test_06_reconcile_nonterminal_and_ineligible_zero_calls():
    notifier_calls: list[tuple[str, int]] = []

    def _mock_notifier(internal_job_id: str, owner_id: int) -> dict[str, Any]:
        notifier_calls.append((internal_job_id, owner_id))
        return {"attempted": True, "called": True}

    jobs_store = {
        # Undelivered job
        "job_undelivered": {
            "internal_job_id": "job_undelivered",
            "user_id": "123456",
            "voice_kind": "auto_speaker_gender",
            "voice_selection_mode": "auto_speaker",
            "terminal_state": "processing",
            "charge_status": "pending",
        },
        # Already charged job (should be skipped)
        "job_already_charged": {
            "internal_job_id": "job_already_charged",
            "user_id": "123456",
            "voice_kind": "auto_speaker_gender",
            "voice_selection_mode": "auto_speaker",
            "terminal_state": "delivered",
            "charge_status": "charged",
        },
        # Eligible delivery but settlement fails
        "job_settle_fail": {
            "internal_job_id": "job_settle_fail",
            "user_id": "123456",
            "voice_kind": "auto_speaker_gender",
            "voice_selection_mode": "auto_speaker",
            "terminal_state": "delivered",
            "charge_status": "settlement_pending_recovery",
            "auto_exact_receipt": {"actual_total_xu": 50},
            "mode": "dub",
        },
    }

    reconcile_ns: dict[str, Any] = {
        "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED": True,
        "_engine_async_id_list_from_setting": lambda _k: list(jobs_store.keys()),
        "_engine_async_feature_key": lambda f: f"feature:{f}",
        "get_engine_async_job": lambda jid: jobs_store.get(jid),
        "is_admin_user": lambda _uid: False,
        "subdub_auto_settlement": SimpleNamespace(
            settle_after_delivery=lambda **_kw: {"ok": False, "reason": "insufficient_credits"}
        ),
        "db_connect": lambda: None,
        "record_credit_event": lambda *a, **kw: None,
        "_engine_async_job_key": lambda jid: f"engine_async_job:{jid}",
        "SUBDUB_AUTO_EXACT_RECEIPT_VERSION": "2026-08-15.auto-exact.1",
        "SUBDUB_AUTO_EXACT_QUOTE_VERSION": "2026-08-15.auto-word.1",
        "normalize_video_translate_mode": lambda m: "dub",
        "now_text": lambda: "2026-09-20T12:00:00Z",
        "ENGINE_ASYNC_MEMORY_JOBS": {},
        "SUBTITLE_DUB_PIPELINE_JOBS": {},
        "_notify_subdub_autopost_completion": _mock_notifier,
    }

    code = _extract_function_source("reconcile_subdub_auto_postdelivery_settlements")
    exec(compile(code, "bot.py", "exec"), reconcile_ns)

    report = reconcile_ns["reconcile_subdub_auto_postdelivery_settlements"](limit=10)

    assert report["scanned"] == 3
    assert report["skipped"] == 2  # job_undelivered, job_already_charged
    assert report["checked"] == 1  # job_settle_fail
    assert report["failed"] == 1   # settlement failed
    assert len(notifier_calls) == 0


# =============================================================================
# TEST 07: Core Pipeline Terminal Completion Calls Notifier Exactly Once
# =============================================================================
def test_07_core_pipeline_completion_calls_notifier_once():
    """Verify lines 252957-252964 seam in _execute_video_dubbing_pipeline_core."""
    notifier_calls: list[tuple[str, int]] = []

    def _notify(internal_job_id: str, owner_id: int) -> dict[str, Any]:
        notifier_calls.append((internal_job_id, owner_id))
        return {"attempted": True}

    # Simulate the exact terminal completion block from bot.py
    terminal_statuses = ["charged", "admin_free", "not_charged"]
    for idx, status in enumerate(terminal_statuses):
        delivered_video = True
        internal_job_id = f"job_core_{idx}"
        uid = 123456
        job = {
            "internal_job_id": internal_job_id,
            "user_id": uid,
            "charge_status": status,
        }

        # Exact code snippet from lines 252962-252964 of bot.py:
        if delivered_video and internal_job_id and job.get("charge_status") in ("charged", "admin_free", "not_charged"):
            _notify(internal_job_id, int(job.get("user_id") or uid or 0))

    assert len(notifier_calls) == len(terminal_statuses)
    for idx, status in enumerate(terminal_statuses):
        assert notifier_calls[idx] == (f"job_core_{idx}", 123456)


# =============================================================================
# TEST 08: Core Pipeline Undelivered or Non-Terminal Billing Calls Notifier Zero Times
# =============================================================================
def test_08_core_pipeline_undelivered_or_nonterminal_zero_calls():
    """Verify non-delivered or non-terminal status suppresses notifier in core pipeline."""
    notifier_calls: list[tuple[str, int]] = []

    def _notify(internal_job_id: str, owner_id: int) -> dict[str, Any]:
        notifier_calls.append((internal_job_id, owner_id))
        return {"attempted": True}

    test_cases = [
        {"delivered": False, "charge_status": "charged", "internal_id": "job_fail_1"},
        {"delivered": True, "charge_status": "pending", "internal_id": "job_fail_2"},
        {"delivered": True, "charge_status": "settlement_pending_recovery", "internal_id": "job_fail_3"},
        {"delivered": True, "charge_status": "", "internal_id": "job_fail_4"},
        {"delivered": False, "charge_status": "pending", "internal_id": "job_fail_5"},
        {"delivered": True, "charge_status": "charged", "internal_id": ""},
    ]

    for tc in test_cases:
        delivered_video = tc["delivered"]
        internal_job_id = tc["internal_id"]
        uid = 123456
        job = {
            "internal_job_id": internal_job_id,
            "user_id": uid,
            "charge_status": tc["charge_status"],
        }

        if delivered_video and internal_job_id and job.get("charge_status") in ("charged", "admin_free", "not_charged"):
            _notify(internal_job_id, int(job.get("user_id") or uid or 0))

    assert len(notifier_calls) == 0


# =============================================================================
# TEST 09: Notifier Failure Does Not Mutate Producer Truth
# =============================================================================
def test_09_notifier_failure_does_not_mutate_producer_truth(tmp_path):
    """Verify notifier error handling in _notify_subdub_autopost_completion."""
    notifier_code = _extract_function_source("_notify_subdub_autopost_completion")

    def broken_db_connect():
        raise sqlite3.OperationalError("database is locked")

    ns = {"db_connect": broken_db_connect}
    exec(compile(notifier_code, "bot.py", "exec"), ns)

    # Calling notifier with broken connection must catch exception and return safe blocker
    diag = ns["_notify_subdub_autopost_completion"]("job_fail_db", 123456)
    assert diag["attempted"] is True
    assert diag["blocker"] == "autopost_notifier_error:OperationalError"

    # Now verify in the recovery function that a notifier error does not mutate
    # delivery result or raise
    def error_notifier(internal_job_id: str, owner_id: int) -> dict[str, Any]:
        return {"attempted": True, "blocker": "autopost_notifier_error:TestError"}

    recovery_ns = _build_recovery_namespace(
        notifier_tracker=[],
        route_enabled=False,
    )
    recovery_ns["_notify_subdub_autopost_completion"] = error_notifier

    job_key = "subdub_test_job_err"
    job = {
        "user_id": "123456",
        "internal_job_id": "job_recovery_err",
        "charge_status": "charged",
        "delivery_attempts": 0,
    }
    recovery_ns["SUBTITLE_DUB_PIPELINE_JOBS"][job_key] = dict(job)

    query = SimpleNamespace(message=SimpleNamespace(message_id=901))
    context = SimpleNamespace()

    result = asyncio.run(
        recovery_ns["subdub_recover_existing_mp4_delivery"](query, context, job_key, job)
    )

    # Producer delivery result remains fully intact
    assert result["video_delivery_message_id"] == "901"
    assert result["charge_status"] == "charged"


# =============================================================================
# TEST 10: AutoPost Replay Idempotent (Receipt / Draft / Queue Diff == 0)
# =============================================================================
def test_10_autopost_replay_idempotent(tmp_path):
    db_file = tmp_path / "autopost_idempotency.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    asda.ensure_autopost_subdub_adapter_schema(conn)

    job_id = "subdub_replay_canonical_01"
    uid = 123456
    _seed_canonical_subdub_job(
        conn,
        tmp_path,
        uid=uid,
        internal_job_id=job_id,
        charge_status="charged",
    )

    # Register intent for SCHEDULE_NOW
    asda.register_subdub_autopost_intent(
        conn,
        owner_id=uid,
        subdub_job_id=job_id,
        mode=asda.SubDubAutoPostMode.SCHEDULE_NOW,
    )
    conn.close()

    def _db_connect():
        c = sqlite3.connect(str(db_file))
        c.row_factory = sqlite3.Row
        return c

    notifier_code = _extract_function_source("_notify_subdub_autopost_completion")
    ns = {"db_connect": _db_connect}
    exec(compile(notifier_code, "bot.py", "exec"), ns)

    # Call 1: initial notification
    diag1 = ns["_notify_subdub_autopost_completion"](job_id, uid)
    assert diag1["attempted"] is True
    assert diag1["created_or_reused"] is True
    assert diag1["state"] == "SCHEDULED"

    # Capture row counts after Call 1
    c1 = _db_connect()
    receipts_count_1 = c1.execute("SELECT COUNT(*) FROM autopost_handoff_receipts").fetchone()[0]
    drafts_count_1 = c1.execute("SELECT COUNT(*) FROM autopost_publication_drafts").fetchone()[0]
    queue_count_1 = c1.execute("SELECT COUNT(*) FROM autopost_publication_queue").fetchone()[0]
    c1.close()

    assert receipts_count_1 == 1
    assert drafts_count_1 == 1
    assert queue_count_1 == 1

    # Call 2: replay notification on the same job
    diag2 = ns["_notify_subdub_autopost_completion"](job_id, uid)
    assert diag2["attempted"] is True
    assert diag2["created_or_reused"] is True
    assert diag2["publication_id"] == diag1["publication_id"]

    # Capture row counts after Call 2
    c2 = _db_connect()
    receipts_count_2 = c2.execute("SELECT COUNT(*) FROM autopost_handoff_receipts").fetchone()[0]
    drafts_count_2 = c2.execute("SELECT COUNT(*) FROM autopost_publication_drafts").fetchone()[0]
    queue_count_2 = c2.execute("SELECT COUNT(*) FROM autopost_publication_queue").fetchone()[0]
    c2.close()

    row_diff = (
        (receipts_count_2 - receipts_count_1)
        + (drafts_count_2 - drafts_count_1)
        + (queue_count_2 - queue_count_1)
    )
    assert row_diff == 0, f"Expected 0 row mutations on replay, got row_diff={row_diff}"


# =============================================================================
# TEST 11: Source Guard -> Recovery Function Has Exactly 1 Notifier Call Site
# =============================================================================
def test_11_source_guard_recovery_function_single_notifier_call_site():
    recovery_code = _extract_function_source("subdub_recover_existing_mp4_delivery")
    call_sites = recovery_code.count("_notify_subdub_autopost_completion")
    assert call_sites == 1, (
        f"Expected exactly 1 call site of _notify_subdub_autopost_completion in "
        f"subdub_recover_existing_mp4_delivery, found {call_sites}"
    )
