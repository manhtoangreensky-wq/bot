import asyncio
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import subdub_auto_settlement


RECEIPT_VERSION = "2026-08-15.auto-exact.1"
QUOTE_VERSION = "2026-08-15.auto-word.1"


def _load_bot_functions(*names: str) -> dict:
    source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")
    namespace = {
        "hashlib": hashlib,
        "os": os,
        "time": time,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
    }
    chunks = []
    for name in names:
        match = re.search(rf"(?m)^(?:async )?def {re.escape(name)}\(", source)
        assert match, name
        next_def = re.search(r"(?m)^(?:async )?def [A-Za-z_]\w*\(", source[match.end():])
        end = match.end() + next_def.start() if next_def else len(source)
        chunks.append(source[match.start():end])
    exec(compile("\n\n".join(chunks), "bot.py", "exec"), namespace)
    return namespace


def _create_db(path: Path, *, credits: int = 1_000) -> None:
    conn = sqlite3.connect(str(path))
    try:
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
            """
        )
        conn.execute(
            "INSERT INTO users(user_id, credits, total_spent) VALUES ('42', ?, 0)",
            (credits,),
        )
        conn.commit()
    finally:
        conn.close()


def _job(*, amount: int = 125, delivered: bool = True) -> dict:
    internal_job_id = "auto-settlement-job"
    job_key = "42:42:dub:auto-settlement"
    claim_token = "claim-token-fixture"
    return {
        "feature": "subtitle_dub",
        "internal_job_id": internal_job_id,
        "job_id": internal_job_id,
        "user_id": "42",
        "chat_id": "42",
        "job_key": job_key,
        "mode": "dub",
        "mapped_mode": "dub",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "status": "completed" if delivered else "resuming_auto_exact_confirmation",
        "terminal_state": "delivered" if delivered else "",
        "output_sent": delivered,
        "delivery_succeeded": delivered,
        "final_mp4_delivered": delivered,
        "final_mp4_validated": delivered,
        "video_delivery_message_id": "9001" if delivered else "",
        "video_delivery_file_id": "telegram-file-fixture" if delivered else "",
        "video_delivery_size_bytes": 4_096 if delivered else 0,
        "video_delivery_sha256": "4" * 64 if delivered else "",
        "video_delivery_mime_type": "video/mp4" if delivered else "",
        "video_delivery_duration_seconds": 12.5 if delivered else 0.0,
        "output_validation": {"ok": delivered, "actual_duration": 12.5},
        "charge_status": "not_charged",
        "charged_xu": 0,
        "auto_exact_session_nonce": "session-nonce-fixture",
        "auto_exact_claim_token": claim_token,
        "auto_exact_receipt": {
            "version": RECEIPT_VERSION,
            "quote_version": QUOTE_VERSION,
            "internal_job_id": internal_job_id,
            "owner_user_id": "42",
            "chat_id": "42",
            "job_key_sha256": hashlib.sha256(job_key.encode("utf-8")).hexdigest(),
            "session_nonce": "session-nonce-fixture",
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


def _seed_job(path: Path, job: dict) -> str:
    setting_key = "engine_async_job:" + job["internal_job_id"]
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            "INSERT INTO system_settings(key, value, note, updated_at, updated_by) VALUES (?, ?, '', '', '')",
            (setting_key, json.dumps(job, ensure_ascii=False, separators=(",", ":"))),
        )
        conn.commit()
    finally:
        conn.close()
    return setting_key


def _connection_factory(path: Path):
    def connect():
        conn = sqlite3.connect(str(path), timeout=5.0)
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    return connect


def _record_credit_event(conn, user_id, delta, event_type, ref_id="", note=""):
    balance = conn.execute(
        "SELECT credits FROM users WHERE user_id=?",
        (str(user_id),),
    ).fetchone()[0]
    conn.execute(
        """INSERT INTO credit_events
        (user_id, delta, balance_after, event_type, ref_id, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'fixture')""",
        (str(user_id), int(delta), int(balance), event_type, str(ref_id), note),
    )


def _settle(path: Path, setting_key: str, *, amount: int = 125, recorder=None):
    return subdub_auto_settlement.settle_after_delivery(
        connection_factory=_connection_factory(path),
        record_credit_event=recorder or _record_credit_event,
        setting_key=setting_key,
        internal_job_id="auto-settlement-job",
        user_id="42",
        amount_xu=amount,
        expected_receipt_version=RECEIPT_VERSION,
        expected_quote_version=QUOTE_VERSION,
        event_type="subdub_auto_final_delivery",
        note="fixture Auto SubDub final delivery",
        now_value="fixture-now",
    )


def _wallet_snapshot(path: Path) -> tuple[int, int, list[tuple[int, str]]]:
    conn = sqlite3.connect(str(path))
    try:
        credits, spent = conn.execute(
            "SELECT credits, total_spent FROM users WHERE user_id='42'"
        ).fetchone()
        events = conn.execute(
            "SELECT delta, ref_id FROM credit_events ORDER BY id"
        ).fetchall()
        return int(credits), int(spent), [(int(delta), str(ref_id)) for delta, ref_id in events]
    finally:
        conn.close()


def test_effective_charge_status_keeps_durable_auto_recovery_truth():
    namespace = _load_bot_functions("subdub_auto_effective_charge_status")
    resolve = namespace["subdub_auto_effective_charge_status"]

    pending = {"charge_status": "settlement_pending_recovery"}
    assert resolve(pending, {}, 0) == "settlement_pending_recovery"
    assert resolve({"charge_status": "admin_free"}, {}, 0) == "admin_free"
    assert resolve({"charge_status": "charged"}, {}, 125) == "charged"
    assert resolve({}, {"charge_status": "provider_truth"}, 0) == "provider_truth"
    assert resolve({}, {}, 125) == "charged"
    assert resolve({}, {}, 0) == "not_charged"
    assert resolve({}, {}, 0, partial_audio_delivered=True) == "not_charged_partial_audio"


def _awaiting_expired_job(*, expires_at: float) -> dict:
    job = _job(delivered=False)
    job.update(
        {
            "status": "awaiting_auto_exact_confirmation",
            "terminal_state": "",
            "lifecycle_state": "awaiting_auto_exact_confirmation",
            "current_stage": "awaiting_auto_exact_confirmation",
            "progress_stage": "awaiting_auto_exact_confirmation",
            "workspace": "fixture-workspace",
        }
    )
    receipt = dict(job["auto_exact_receipt"])
    receipt.update(
        {
            "consumed": False,
            "claim_state": "unconsumed",
            "expires_at": float(expires_at),
        }
    )
    job["auto_exact_receipt"] = receipt
    job["auto_exact_claim_token"] = ""
    return job


def _expire(path: Path, setting_key: str, *, now_epoch: float) -> dict:
    return subdub_auto_settlement.expire_exact_receipt(
        connection_factory=_connection_factory(path),
        setting_key=setting_key,
        internal_job_id="auto-settlement-job",
        user_id="42",
        chat_id="42",
        session_nonce="session-nonce-fixture",
        expected_receipt_version=RECEIPT_VERSION,
        expected_quote_version=QUOTE_VERSION,
        now_epoch=now_epoch,
        now_value="fixture-now",
    )


def test_expired_auto_receipt_terminalizes_without_wallet_mutation(tmp_path):
    db_path = tmp_path / "expired-receipt.sqlite3"
    _create_db(db_path)
    setting_key = _seed_job(db_path, _awaiting_expired_job(expires_at=100.5))

    result = _expire(db_path, setting_key, now_epoch=101.0)

    assert result["ok"] is True and result["expired"] is True
    job = result["job"]
    assert job["status"] == "failed_no_charge"
    assert job["terminal_state"] == "failed_no_charge"
    assert job["charge_status"] == "not_charged"
    assert job["charged_xu"] == 0
    assert job["no_charge_reason"] == "auto_exact_confirmation_expired"
    assert job["refresh_stopped_after_terminal"] is True
    receipt = job["auto_exact_receipt"]
    assert receipt["consumed"] is True
    assert receipt["claim_state"] == "expired"
    assert receipt["expired_at"] == 101.0
    assert _wallet_snapshot(db_path) == (1_000, 0, [])


def test_nonexpired_auto_receipt_is_not_terminalized(tmp_path):
    db_path = tmp_path / "current-receipt.sqlite3"
    _create_db(db_path)
    setting_key = _seed_job(db_path, _awaiting_expired_job(expires_at=200.0))

    result = _expire(db_path, setting_key, now_epoch=101.0)

    assert result == {"ok": False, "expired": False, "reason": "receipt_not_expired"}
    assert _wallet_snapshot(db_path) == (1_000, 0, [])


def test_expiry_and_confirmation_claim_cas_have_exactly_one_winner(tmp_path):
    db_path = tmp_path / "expiry-claim-race.sqlite3"
    _create_db(db_path)
    setting_key = _seed_job(db_path, _awaiting_expired_job(expires_at=100.5))
    barrier = threading.Barrier(3)
    expiry_results = []
    claim_results = []
    errors = []
    namespace = _load_bot_functions(
        "_subdub_auto_receipt_transition_matches",
        "_subdub_auto_engine_job_cas",
    )
    namespace.update(
        {
            "db_connect": _connection_factory(db_path),
            "_engine_async_job_key": lambda _job_id: setting_key,
            "normalize_video_translate_mode": lambda value: str(value or ""),
            "SUBDUB_AUTO_EXACT_RECEIPT_VERSION": RECEIPT_VERSION,
            "SUBDUB_AUTO_EXACT_QUOTE_VERSION": QUOTE_VERSION,
            "ENGINE_ASYNC_MEMORY_JOBS": {},
            "hmac": __import__("hmac"),
            "json": json,
            "sqlite3": sqlite3,
            "time": SimpleNamespace(time=lambda: 100.0),
            "uuid": SimpleNamespace(
                uuid4=lambda: SimpleNamespace(hex="claimtokenfixture123456789")
            ),
            "now_text": lambda: "fixture-claim-now",
        }
    )

    def expire():
        try:
            barrier.wait(timeout=5.0)
            expiry_results.append(_expire(db_path, setting_key, now_epoch=101.0))
        except BaseException as exc:
            errors.append(exc)

    def claim():
        try:
            barrier.wait(timeout=5.0)
            claimed, _job = namespace["_subdub_auto_engine_job_cas"](
                "auto-settlement-job",
                user_id="42",
                chat_id="42",
                session_nonce="session-nonce-fixture",
                cancel=False,
            )
            claim_results.append(bool(claimed))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=expire), threading.Thread(target=claim)]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=5.0)
    for thread in threads:
        thread.join(timeout=7.0)

    assert not errors and not any(thread.is_alive() for thread in threads)
    assert len(expiry_results) == 1 and len(claim_results) == 1
    assert int(bool(expiry_results[0].get("ok"))) + int(claim_results[0]) == 1
    assert _wallet_snapshot(db_path) == (1_000, 0, [])


def test_auto_settlement_requires_durable_final_delivery(tmp_path):
    db_path = tmp_path / "no-delivery.sqlite3"
    _create_db(db_path)
    setting_key = _seed_job(db_path, _job(delivered=False))

    result = _settle(db_path, setting_key)

    assert result["ok"] is False
    assert result["reason"] == "durable_delivery_required"
    assert _wallet_snapshot(db_path) == (1_000, 0, [])


def test_auto_settlement_requires_validated_mp4_artifact_receipt(tmp_path):
    db_path = tmp_path / "unvalidated-delivery.sqlite3"
    _create_db(db_path)
    job = _job()
    job["final_mp4_validated"] = False
    setting_key = _seed_job(db_path, job)

    result = _settle(db_path, setting_key)

    assert result["ok"] is False
    assert result["reason"] == "durable_delivery_required"
    assert _wallet_snapshot(db_path) == (1_000, 0, [])


def test_auto_settlement_rejects_manual_job_even_when_video_was_delivered(tmp_path):
    db_path = tmp_path / "manual-delivery.sqlite3"
    _create_db(db_path)
    job = _job()
    job.pop("auto_exact_receipt")
    setting_key = _seed_job(db_path, job)

    result = _settle(db_path, setting_key)

    assert result["ok"] is False
    assert result["reason"] == "auto_receipt_required"
    assert _wallet_snapshot(db_path) == (1_000, 0, [])


def test_auto_settlement_charges_once_and_replay_is_idempotent(tmp_path):
    db_path = tmp_path / "one-charge.sqlite3"
    _create_db(db_path)
    setting_key = _seed_job(db_path, _job())

    first = _settle(db_path, setting_key)
    second = _settle(db_path, setting_key)

    assert first["ok"] is True and first["charged_xu"] == 125
    assert first["already_charged"] is False
    assert second["ok"] is True and second["charged_xu"] == 125
    assert second["already_charged"] is True
    credits, spent, events = _wallet_snapshot(db_path)
    assert (credits, spent) == (875, 125)
    assert len(events) == 1 and events[0][0] == -125 and events[0][1]


def test_auto_settlement_repairs_persisted_job_from_existing_ledger_ref(tmp_path):
    db_path = tmp_path / "ledger-reconcile.sqlite3"
    _create_db(db_path)
    job = _job()
    setting_key = _seed_job(db_path, job)
    ref_id = subdub_auto_settlement._stable_ref_id(
        job["internal_job_id"], job["auto_exact_receipt"]
    )
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE users SET credits=875, total_spent=125 WHERE user_id='42'"
        )
        _record_credit_event(
            conn,
            "42",
            -125,
            "subdub_auto_final_delivery",
            ref_id,
            "fixture committed ledger before stale job overwrite",
        )
        conn.commit()
    finally:
        conn.close()

    result = _settle(db_path, setting_key)

    assert result["ok"] is True
    assert result["already_charged"] is True
    assert _wallet_snapshot(db_path) == (875, 125, [(-125, ref_id)])


def test_auto_settlement_concurrent_replay_has_one_ledger_debit(tmp_path):
    db_path = tmp_path / "race.sqlite3"
    _create_db(db_path)
    setting_key = _seed_job(db_path, _job())
    barrier = threading.Barrier(3)
    outcomes = []
    errors = []

    def run():
        try:
            barrier.wait(timeout=5.0)
            outcomes.append(_settle(db_path, setting_key))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run), threading.Thread(target=run)]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=5.0)
    for thread in threads:
        thread.join(timeout=7.0)

    assert not errors and not any(thread.is_alive() for thread in threads)
    assert len(outcomes) == 2 and all(item["ok"] for item in outcomes)
    assert sum(not item["already_charged"] for item in outcomes) == 1
    assert _wallet_snapshot(db_path)[0:2] == (875, 125)
    assert len(_wallet_snapshot(db_path)[2]) == 1


def test_auto_settlement_insufficient_balance_keeps_ledger_unchanged(tmp_path):
    db_path = tmp_path / "insufficient.sqlite3"
    _create_db(db_path, credits=100)
    setting_key = _seed_job(db_path, _job())

    result = _settle(db_path, setting_key)

    assert result["ok"] is False and result["reason"] == "insufficient_balance"
    assert _wallet_snapshot(db_path) == (100, 0, [])


def test_auto_settlement_rejects_receipt_amount_mismatch(tmp_path):
    db_path = tmp_path / "mismatch.sqlite3"
    _create_db(db_path)
    setting_key = _seed_job(db_path, _job(amount=124))

    result = _settle(db_path, setting_key, amount=125)

    assert result["ok"] is False and result["reason"] == "receipt_identity_mismatch"
    assert _wallet_snapshot(db_path) == (1_000, 0, [])


def test_auto_settlement_rejects_manual_default_job_even_if_delivered(tmp_path):
    db_path = tmp_path / "manual-default.sqlite3"
    _create_db(db_path)
    job = _job()
    job["voice_kind"] = "default_female"
    job.pop("voice_selection_mode", None)
    setting_key = _seed_job(db_path, job)

    result = _settle(db_path, setting_key)

    assert result["ok"] is False
    assert result["reason"] == "auto_identity_required"
    assert _wallet_snapshot(db_path) == (1_000, 0, [])


def test_auto_settlement_rolls_back_when_ledger_write_fails(tmp_path):
    db_path = tmp_path / "rollback.sqlite3"
    _create_db(db_path)
    setting_key = _seed_job(db_path, _job())

    def fail_record(*_args, **_kwargs):
        raise sqlite3.OperationalError("fixture ledger failure")

    with pytest.raises(sqlite3.OperationalError, match="fixture ledger failure"):
        _settle(db_path, setting_key, recorder=fail_record)

    assert _wallet_snapshot(db_path) == (1_000, 0, [])


def test_auto_pipeline_source_defers_charge_until_durable_delivery():
    source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")
    start = source.index("async def _execute_video_dubbing_pipeline_core(")
    end = source.index("\nasync def execute_video_dubbing_pipeline(", start)
    core = source[start:end]

    delivery_at = core.index(
        "delivery = await send_public_subtitle_dub_final_outputs("
    )
    durable_delivery_at = core.index(
        "mark_subtitle_dub_pipeline_output_sent(", delivery_at
    )
    settlement_at = core.index(
        "subdub_auto_settlement.settle_after_delivery(", durable_delivery_at
    )

    assert "if auto_pricing_active:\n        charged = 0" in core
    assert durable_delivery_at < settlement_at
    assert "spend_fixed_credit_info(" in core


def test_auto_postdelivery_settlement_does_not_repass_positional_job_key():
    source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")
    start = source.index("async def _execute_video_dubbing_pipeline_core(")
    end = source.index("\nasync def execute_video_dubbing_pipeline(", start)
    core = source[start:end]
    settlement_start = core.index("auto_settlement_fields: dict = {}")
    settlement_end = core.index("\n    except Exception:\n", settlement_start)
    postdelivery = core[settlement_start:settlement_end]

    assert postdelivery.count("update_subtitle_dub_pipeline_job(") == 3
    assert '"job_key": delivery_job_key' not in postdelivery


def test_bot_auto_branch_settles_only_after_durable_delivery_mark_source_contract():
    bot_path = Path(__file__).resolve().parents[1] / "bot.py"
    source = bot_path.read_text(encoding="utf-8")
    start = source.index("async def _execute_video_dubbing_pipeline_core(")
    end = source.index("\nasync def execute_video_dubbing_pipeline(", start)
    core = source[start:end]
    auto_defer_at = core.index("if auto_pricing_active:\n        charged = 0")
    manual_charge_at = core.index("charge = spend_fixed_credit_info(", auto_defer_at)
    delivery_at = core.index("delivery = await send_public_subtitle_dub_final_outputs(")
    durable_mark_at = core.index("mark_subtitle_dub_pipeline_output_sent(", delivery_at)
    settlement_at = core.index(
        "subdub_auto_settlement.settle_after_delivery(", durable_mark_at
    )

    assert auto_defer_at < manual_charge_at < delivery_at
    assert durable_mark_at < settlement_at
    assert "apply_member_discount_flag=False" not in core[auto_defer_at:delivery_at]


def test_auto_recovery_source_is_bounded_db_only_and_hooked_after_init_db():
    source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")
    start = source.index("def reconcile_subdub_auto_postdelivery_settlements(")
    end = source.index("\ndef ", start + 8)
    recovery = source[start:end]
    lifespan_start = source.index("async def lifespan(")
    lifespan_end = source.index("\nfastapi_app =", lifespan_start)
    lifespan = source[lifespan_start:lifespan_end]

    assert "subdub_auto_settlement.settle_after_delivery(" in recovery
    assert "limit: int = 40" in recovery
    assert "_engine_async_id_list_from_setting(" in recovery
    assert "for offset in range(0, len(candidate_ids), batch_size):" in recovery
    assert '"skipped":' in recovery
    assert '"admin_free":' in recovery
    assert all(
        forbidden not in recovery
        for forbidden in (
            "execute_video_dubbing_pipeline(",
            "send_public_subtitle_dub_final_outputs(",
            "video_dubbing_tts_bytes(",
            "run_auto_speaker_blackbox(",
        )
    )
    init_at = lifespan.index("init_db()")
    recovery_at = lifespan.index(
        "reconcile_subdub_auto_postdelivery_settlements"
    )
    assert init_at < recovery_at


def test_exact_known_auto_quote_claims_and_persists_receipt_before_continue():
    source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")
    start = source.index("async def _subdub_auto_post_prepare_gate(")
    end = source.index("\ndef _subdub_auto_workspace_file(", start)
    gate = source[start:end]

    build_at = gate.index("receipt_bundle = _subdub_auto_build_exact_receipt(")
    exact_known_at = gate.index(
        'if not decision.get("exact_confirmation_required"):', build_at
    )
    claim_at = gate.index('"claim_state": "resuming"', exact_known_at)
    persist_at = gate.index('reason="auto_exact_known_receipt_claimed"', claim_at)
    continue_at = gate.index('return {"continue": True}', persist_at)

    assert build_at < exact_known_at < claim_at < persist_at < continue_at


def test_pending_state_preserves_every_exact_auto_receipt_mirror_field():
    namespace = _load_bot_functions("set_video_dubbing_pending")
    pending = {}
    namespace.update(
        {
            "USER_PENDING": pending,
            "video_dubbing_pending_key": lambda user_id: f"pending:{user_id}",
            "subdub_translation_cache_language_key": lambda value: str(value or ""),
            "_short_pending_text": lambda value: value,
            "normalize_video_translate_mode": lambda value: "",
        }
    )

    state = namespace["set_video_dubbing_pending"](
        "42",
        "auto_exact_confirmation",
        auto_exact_session_nonce="nonce-fixture",
        auto_exact_actual_auto_xu=125,
        auto_exact_actual_subtitle_xu=30,
    )

    assert state["auto_exact_session_nonce"] == "nonce-fixture"
    assert state["auto_exact_actual_auto_xu"] == 125
    assert state["auto_exact_actual_subtitle_xu"] == 30


def test_real_delivery_update_then_terminal_mark_satisfies_auto_settlement(tmp_path):
    db_path = tmp_path / "delivery-chain.sqlite3"
    _create_db(db_path)
    job = _job(delivered=False)
    setting_key = _seed_job(db_path, job)
    namespace = _load_bot_functions(
        "update_subtitle_dub_pipeline_job",
        "mark_subtitle_dub_pipeline_output_sent",
    )
    registry = {job["job_key"]: dict(job)}

    def persist(_job_key, snapshot=None, *, reason=""):
        payload = dict(snapshot or {})
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "UPDATE system_settings SET value=?, note=? WHERE key=?",
                (
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    str(reason or ""),
                    setting_key,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return True

    namespace.update(
        {
            "SUBTITLE_DUB_PIPELINE_JOBS": registry,
            "SUBDUB_TERMINAL_STATES": {
                "delivered",
                "failed_no_charge",
                "failed_refunded",
                "needs_admin_review",
            },
            "SUBDUB_PUBLIC_AUDIO_FALLBACK_ENABLED": False,
            "_safe_int": lambda value, default=0: int(value or default),
            "subdub_normalize_input_save_failed_terminal": lambda value: dict(value or {}),
            "subdub_enrich_job_identity": lambda value, **_kwargs: dict(value or {}),
            "subdub_progress_percent_for_lifecycle": lambda *_args: 100,
            "subdub_completed_steps_for_lifecycle": lambda *_args: ["delivered"],
            "subdub_success_cost_line": lambda value: f"{int(value or 0)} Xu",
            "subdub_video_requires_final_mp4": lambda *_args: True,
            "subdub_public_outcome_allows_success": lambda _job: True,
            "subdub_terminal_state_allows_transition": lambda *_args: True,
            "subdub_job_has_failure_public_outcome": lambda _job: False,
            "subdub_record_duplicate_terminal": lambda *_args, **_kwargs: None,
            "persist_subtitle_dub_pipeline_job_snapshot": persist,
        }
    )
    validation = {"ok": True, "actual_duration": 12.5}
    namespace["update_subtitle_dub_pipeline_job"](
        job["job_key"],
        video_delivery_file_id="telegram-file-fixture",
        video_delivery_size_bytes=4_096,
        video_delivery_sha256="4" * 64,
        video_delivery_mime_type="video/mp4",
        video_delivery_duration_seconds=12.5,
        video_delivery_message_id="9001",
        final_mp4_validated=True,
        final_mp4_delivered=True,
        output_validation=validation,
    )
    marked = namespace["mark_subtitle_dub_pipeline_output_sent"](
        job["job_key"],
        terminal_state="delivered",
        delivery_message_id="9001",
        terminal_artifact_type="video",
        video_delivery_message_id="9001",
    )

    assert marked is True
    result = _settle(db_path, setting_key)
    assert result["ok"] is True
    assert result["charged_xu"] == 125
    assert _wallet_snapshot(db_path)[0:2] == (875, 125)


def test_public_delivery_persists_artifact_receipt_before_terminal_mark():
    source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")
    delivery_start = source.index("async def send_public_subtitle_dub_final_outputs(")
    delivery_end = source.index("\ndef ", delivery_start)
    delivery = source[delivery_start:delivery_end]
    update_at = delivery.index("update_subtitle_dub_pipeline_job(")
    for required in (
        "video_delivery_file_id=",
        "video_delivery_size_bytes=",
        "video_delivery_sha256=",
        "video_delivery_mime_type=",
        "video_delivery_duration_seconds=",
        "output_validation=",
    ):
        assert delivery.index(required, update_at) > update_at

    core_start = source.index("async def _execute_video_dubbing_pipeline_core(")
    core_end = source.index("\nasync def execute_video_dubbing_pipeline(", core_start)
    core = source[core_start:core_end]
    send_at = core.index("delivery = await send_public_subtitle_dub_final_outputs(")
    mark_at = core.index("mark_subtitle_dub_pipeline_output_sent(", send_at)
    settle_at = core.index("subdub_auto_settlement.settle_after_delivery(", mark_at)
    assert send_at < mark_at < settle_at


def test_postdelivery_settlement_failure_stays_delivered_and_recoverable():
    source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")
    start = source.index("async def _execute_video_dubbing_pipeline_core(")
    end = source.index("\nasync def execute_video_dubbing_pipeline(", start)
    core = source[start:end]
    settlement_at = core.index("subdub_auto_settlement.settle_after_delivery(")
    postdelivery = core[settlement_at:]

    assert '"auto_settlement_pending_recovery": True' in postdelivery
    assert '"charge_status": "settlement_pending_recovery"' in postdelivery
    assert "raise RuntimeError(f\"auto settlement blocked:" not in postdelivery
    settlement_branch = postdelivery[: postdelivery.index("\n    except Exception:\n")]
    assert "raise\n" not in settlement_branch


def test_existing_mp4_recovery_immediately_settles_auto_delivery_source_contract():
    source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")
    start = source.index("async def subdub_recover_existing_mp4_delivery(")
    end = source.index("\ndef subdub_video_delivery_message_id(", start)
    recovery = source[start:end]
    mark_at = recovery.index("mark_subtitle_dub_pipeline_output_sent(")
    settle_at = recovery.index("subdub_auto_settlement.settle_after_delivery(")

    assert mark_at < settle_at
    assert "if subdub_auto_speaker_route_enabled(latest):" in recovery
    assert 'charge_status="settlement_pending_recovery"' in recovery


def test_persisted_auto_job_can_recover_one_interrupted_delivery_attempt(tmp_path):
    artifact = tmp_path / "validated.mp4"
    artifact.write_bytes(b"validated-auto-mp4")
    namespace = _load_bot_functions("subdub_existing_mp4_recovery_candidate")
    namespace.update(
        {
            "os": __import__("os"),
            "subdub_terminal_delivery_evidence": lambda _job: {},
            "truthy_value": lambda value, _default=False: bool(value),
            "_safe_int": lambda value, default=0: int(value or default),
        }
    )
    exact_auto = {
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "lookup_store_hit": "engine_async_persisted_scan",
        "delivery_attempted": True,
        "delivery_started": True,
        "delivery_attempts": 1,
        "delivery_attempt_uncertain": False,
        "final_mp4_validated": True,
        "final_mp4_path": str(artifact),
    }

    assert namespace["subdub_existing_mp4_recovery_candidate"](exact_auto) == str(artifact)
    assert namespace["subdub_existing_mp4_recovery_candidate"](
        {**exact_auto, "delivery_attempt_uncertain": True}
    ) == ""
    assert namespace["subdub_existing_mp4_recovery_candidate"](
        {**exact_auto, "delivery_attempts": 2}
    ) == ""
    assert namespace["subdub_existing_mp4_recovery_candidate"](
        {**exact_auto, "voice_kind": "default_female", "voice_selection_mode": ""}
    ) == ""


def test_auto_pricing_uses_readiness_before_receipt_and_durable_identity_after_confirmation():
    source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")

    def function_source(name: str) -> str:
        start = source.index(f"def {name}(")
        next_sync = source.find("\ndef ", start + 5)
        next_async = source.find("\nasync def ", start + 5)
        candidates = [value for value in (next_sync, next_async) if value >= 0]
        return source[start:min(candidates) if candidates else len(source)]

    invoice = function_source("video_dubbing_invoice_breakdown")
    confirm = function_source("video_dubbing_confirm_text")
    exact_gate = function_source("_subdub_auto_post_prepare_gate")
    core = function_source("_execute_video_dubbing_pipeline_core")
    execute = function_source("execute_video_dubbing_pipeline")

    assert "if not subdub_auto_speaker_route_enabled(state):" in invoice
    assert "auto_pricing = subdub_auto_speaker_route_enabled(state)" in confirm
    assert "if not subdub_auto_speaker_route_enabled(state):" in exact_gate
    assert core.count("if subdub_auto_speaker_route_enabled(state):") >= 2
    assert "auto_pricing_active = auto_speaker.is_auto_speaker_state(state)" in core
    assert "if subdub_auto_speaker_route_enabled(state):" in execute


def test_auto_exact_success_finalizes_green_panel_then_sends_one_receipt():
    namespace = _load_bot_functions("handle_subdub_auto_exact_callback")
    calls = []
    job = {
        "job_key": "auto-exact-terminal-panel-receipt",
        "job_id": "auto-exact-job",
        "internal_job_id": "auto-exact-job",
        "public_code": "AUTOEXACT1",
        "mode": "subtitle_plus_dub",
        "status": "resuming_auto_exact_confirmation",
        "auto_exact_resume_state": {
            "mode": "subtitle_plus_dub",
            "origin": "translation",
        },
    }

    async def transition(**_kwargs):
        return True, dict(job)

    async def execute_engine(_feature, _payload, _context):
        return {
            "runner_result": {
                "ok": True,
                "mode": "subtitle_plus_dub",
                "terminal_state": "delivered",
                "final_mp4_delivered": True,
                "video_delivery_message_id": "8188",
                "job_id": "auto-exact-job",
                "charged": 0,
                "charge_status": "admin_free",
                "state": {"origin": "translation"},
            }
        }

    async def finalize_panel(_query, _context, key, job_id, _lang, _result):
        calls.append(("panel", key, job_id))
        return "panel-green"

    async def send_receipt(_message, key, text, **kwargs):
        calls.append(("receipt", key, text, kwargs.get("reply_markup")))
        return "receipt-sent"

    pending = {}

    def set_pending(_uid, step, **fields):
        pending.update({"step": step, **fields})
        return dict(pending)

    def mark_delivered(key, result):
        calls.append(("mark", key, result.get("video_delivery_message_id")))
        return dict(job)

    namespace.update(
        {
            "_subdub_auto_exact_decode_token": lambda _value: ("AUTOEXACT1", "nonce"),
            "subdub_progress_job_for_user": lambda _code, _uid: dict(job),
            "normalize_user_language": lambda value: str(value or "vi"),
            "public_subdub_deep_copy": lambda _lang: {},
            "_subdub_auto_exact_transition": transition,
            "normalize_video_translate_mode": lambda value: str(value or ""),
            "video_dubbing_product_area_for_mode": lambda _mode: "translation",
            "execute_engine": execute_engine,
            "ENGINE_ENTRY_SOURCE_PRODUCT": "product",
            "set_video_dubbing_pending": set_pending,
            "subdub_mark_delivered_terminal": mark_delivered,
            "subdub_finalize_delivered_panel": finalize_panel,
            "video_dubbing_receipt_text": lambda *_args: "receipt",
            "video_dubbing_receipt_keyboard": lambda *_args: "buttons",
            "subdub_send_success_receipt_once": send_receipt,
            "SUBTITLE_DUB_PIPELINE_JOBS": {job["job_key"]: dict(job)},
        }
    )

    query = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(chat_id=42),
    )
    result = asyncio.run(
        namespace["handle_subdub_auto_exact_callback"](
            query,
            SimpleNamespace(),
            action="auto_exact_confirm",
            value="token",
            lang="vi",
        )
    )

    assert result == "receipt-sent"
    assert calls == [
        ("mark", "auto-exact-terminal-panel-receipt", "8188"),
        ("panel", "auto-exact-terminal-panel-receipt", "auto-exact-job"),
        ("receipt", "auto-exact-terminal-panel-receipt", "receipt", "buttons"),
    ]
    assert pending == {
        "step": "completed",
        "processing": "0",
        "terminal_state": "delivered",
    }


def test_subdub_cjk_filter_passes_resolved_font_directory_to_libass():
    namespace = _load_bot_functions(
        "subdub_ffmpeg_filter_path",
        "subdub_subtitle_filter_for_file",
    )
    namespace["ffmpeg_text"] = SimpleNamespace(
        escape_filter_path=lambda value, resolve=False: str(value)
    )

    actual = namespace["subdub_subtitle_filter_for_file"](
        "/tmp/subtitle.ass",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    )

    assert namespace["subdub_subtitle_filter_for_file"]("/tmp/subtitle.srt") == (
        "subtitles=filename='/tmp/subtitle.srt'"
    )
    assert actual == (
        "subtitles=filename='/tmp/subtitle.ass':"
        "fontsdir='/usr/share/fonts/opentype/noto'"
    )
    render_source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")
    assert render_source.count('str(style.get("subtitle_font_path") or "")') >= 2


def test_expired_exact_receipt_never_emits_a_confirm_callback_token():
    namespace = _load_bot_functions("_subdub_auto_exact_callback_token")
    namespace.update(
        {
            "re": re,
            "subdub_existing_public_code": lambda job: str(job.get("public_code") or ""),
        }
    )
    token = namespace["_subdub_auto_exact_callback_token"](
        {
            "status": "awaiting_auto_exact_confirmation",
            "public_code": "ABC12345",
            "auto_exact_receipt": {
                "session_nonce": "nonce12345678",
                "expires_at": time.time() - 1,
                "consumed": False,
                "claim_state": "unconsumed",
            },
        }
    )
    assert token == ""


def test_expiry_terminalization_is_wired_to_callback_status_and_same_key_reentry():
    source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")
    acquire_start = source.index("def acquire_subtitle_dub_pipeline_job(")
    acquire_end = source.index("\ndef update_subtitle_dub_pipeline_job(", acquire_start)
    acquire = source[acquire_start:acquire_end]
    callback_start = source.index("async def handle_subdub_auto_exact_callback(")
    callback_end = source.index("\nSUBDUB_AUTO_PCM_MAX_SECONDS", callback_start)
    callback = source[callback_start:callback_end]
    status_start = source.index('if action == "subdub_status":')
    status_end = source.index('if action == "admin_status":', status_start)
    status = source[status_start:status_end]

    assert "_expire_subdub_auto_exact_job_if_due(" in acquire
    assert "SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)" in acquire
    assert "_expire_subdub_auto_exact_job_if_due(" in callback
    assert "_expire_subdub_auto_exact_job_if_due(" in status
    assert "voice_auto_exact_expired" in callback
    assert "voice_auto_exact_expired" in status


def test_same_key_reentry_acquires_a_new_job_after_durable_expiry():
    namespace = _load_bot_functions("acquire_subtitle_dub_pipeline_job")
    old = {
        "job_key": "same-key",
        "job_id": "old-job",
        "status": "awaiting_auto_exact_confirmation",
        "lifecycle_state": "awaiting_auto_exact_confirmation",
        "current_stage": "awaiting_auto_exact_confirmation",
        "progress_stage": "awaiting_auto_exact_confirmation",
        "terminal_state": "",
    }
    registry = {"same-key": dict(old)}
    namespace.update(
        {
            "SUBTITLE_DUB_PIPELINE_JOBS": registry,
            "SUBDUB_TERMINAL_STATES": {
                "delivered",
                "failed_no_charge",
                "failed_refunded",
                "needs_admin_review",
            },
            "_prune_subtitle_dub_pipeline_jobs": lambda: None,
            "_expire_subdub_auto_exact_job_if_due": lambda _job: (
                True,
                {**old, "status": "failed_no_charge", "terminal_state": "failed_no_charge"},
            ),
            "is_workspace_active_status": lambda value: value
            == "awaiting_auto_exact_confirmation",
            "subdub_lifecycle_debug_fields": lambda _stage: {},
            "subdub_progress_percent_for_lifecycle": lambda _stage: 5,
            "subdub_full_duration_limit_seconds": lambda _admin: 1_800,
            "subdub_terminal_outcome_debug_defaults": lambda: {},
            "subdub_enrich_job_identity": lambda job, **_kwargs: {
                **job,
                "internal_job_id": str(job.get("job_id") or ""),
            },
            "persist_subtitle_dub_pipeline_job_snapshot": lambda *_args, **_kwargs: True,
        }
    )

    acquired, new_job = namespace["acquire_subtitle_dub_pipeline_job"](
        "same-key", user_id="42", chat_id="42", mode="dub"
    )

    assert acquired is True
    assert new_job["job_id"] != "old-job"
    assert registry["same-key"]["job_id"] == new_job["job_id"]
