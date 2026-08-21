"""Durable, Auto-only SubDub settlement after confirmed video delivery."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
from typing import Callable


def expire_exact_receipt(
    *,
    connection_factory: Callable[[], sqlite3.Connection],
    setting_key: str,
    internal_job_id: str,
    user_id,
    chat_id,
    session_nonce: str,
    expected_receipt_version: str,
    expected_quote_version: str,
    now_epoch: float,
    now_value: str = "",
) -> dict:
    """Atomically terminalize one expired, unclaimed Auto receipt without charging."""

    safe_setting_key = str(setting_key or "").strip()
    safe_job_id = str(internal_job_id or "").strip()
    safe_user_id = str(user_id or "").strip()
    safe_chat_id = str(chat_id or "").strip()
    safe_nonce = str(session_nonce or "").strip()
    try:
        current_epoch = float(now_epoch)
    except (TypeError, ValueError, OverflowError):
        current_epoch = 0.0
    if not all(
        (
            safe_setting_key,
            safe_job_id,
            safe_user_id,
            safe_chat_id,
            safe_nonce,
            str(expected_receipt_version or ""),
            str(expected_quote_version or ""),
        )
    ) or current_epoch <= 0:
        return {"ok": False, "expired": False, "reason": "invalid_expiry_request"}

    conn = connection_factory()
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key=? LIMIT 1",
            (safe_setting_key,),
        ).fetchone()
        if not row:
            conn.rollback()
            return {"ok": False, "expired": False, "reason": "durable_job_missing"}
        old_value = str(row[0] or "")
        try:
            job = json.loads(old_value)
        except (TypeError, ValueError, json.JSONDecodeError):
            conn.rollback()
            return {"ok": False, "expired": False, "reason": "durable_job_invalid"}
        if not isinstance(job, dict):
            conn.rollback()
            return {"ok": False, "expired": False, "reason": "durable_job_invalid"}
        receipt = dict(job.get("auto_exact_receipt") or {})
        job_key = str(job.get("job_key") or "").strip()
        job_id = str(job.get("internal_job_id") or job.get("job_id") or "").strip()
        job_mode = str(job.get("mode") or job.get("mapped_mode") or "").strip()
        identity_matches = all(
            (
                str(job.get("voice_kind") or "") == "auto_speaker_gender",
                str(job.get("voice_selection_mode") or "") == "auto_speaker",
                str(job.get("status") or "") == "awaiting_auto_exact_confirmation",
                not str(job.get("terminal_state") or ""),
                job_id == safe_job_id,
                str(job.get("user_id") or "") == safe_user_id,
                str(job.get("chat_id") or "") == safe_chat_id,
                bool(job_key),
                bool(job_mode),
                str(receipt.get("internal_job_id") or "") == safe_job_id,
                str(receipt.get("owner_user_id") or "") == safe_user_id,
                str(receipt.get("chat_id") or "") == safe_chat_id,
                str(receipt.get("job_key_sha256") or "")
                == hashlib.sha256(job_key.encode("utf-8")).hexdigest(),
                str(receipt.get("mode") or "") == job_mode,
                str(receipt.get("version") or "")
                == str(expected_receipt_version or ""),
                str(receipt.get("quote_version") or "")
                == str(expected_quote_version or ""),
                receipt.get("consumed") is False,
                str(receipt.get("claim_state") or "") == "unconsumed",
                hmac.compare_digest(
                    str(receipt.get("session_nonce") or ""), safe_nonce
                ),
            )
        )
        if not identity_matches:
            conn.rollback()
            return {
                "ok": False,
                "expired": False,
                "reason": "receipt_transition_mismatch",
            }
        try:
            expires_at = float(receipt.get("expires_at") or 0.0)
        except (TypeError, ValueError, OverflowError):
            expires_at = 0.0
        if expires_at > current_epoch:
            conn.rollback()
            return {"ok": False, "expired": False, "reason": "receipt_not_expired"}
        if expires_at <= 0:
            conn.rollback()
            return {
                "ok": False,
                "expired": False,
                "reason": "receipt_expiry_invalid",
            }

        receipt.update(
            {
                "consumed": True,
                "claim_state": "expired",
                "expired_at": current_epoch,
                "expires_at": min(expires_at, current_epoch),
            }
        )
        job.update(
            {
                "auto_exact_receipt": receipt,
                "status": "failed_no_charge",
                "terminal_state": "failed_no_charge",
                "lifecycle_state": "failed_no_charge",
                "current_stage": "failed_no_charge",
                "progress_stage": "failed_no_charge",
                "charge_status": "not_charged",
                "charged_xu": 0,
                "no_charge_reason": "auto_exact_confirmation_expired",
                "auto_exact_expired": True,
                "refresh_stopped_after_terminal": True,
                "status_panel_terminalized": True,
                "updated_at": current_epoch,
            }
        )
        new_value = json.dumps(job, ensure_ascii=False, separators=(",", ":"))
        cursor = conn.execute(
            """UPDATE system_settings
            SET value=?, note=?, updated_at=?, updated_by=?
            WHERE key=? AND value=?""",
            (
                new_value,
                "subdub auto exact receipt expired",
                str(now_value or ""),
                safe_user_id,
                safe_setting_key,
                old_value,
            ),
        )
        if int(cursor.rowcount or 0) != 1:
            conn.rollback()
            return {"ok": False, "expired": False, "reason": "expiry_cas_conflict"}
        conn.commit()
        return {"ok": True, "expired": True, "job": job}
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def _stable_ref_id(internal_job_id: str, receipt: dict) -> str:
    identity = {
        "internal_job_id": str(internal_job_id),
        "owner_user_id": str(receipt.get("owner_user_id") or ""),
        "chat_id": str(receipt.get("chat_id") or ""),
        "mode": str(receipt.get("mode") or ""),
        "version": str(receipt.get("version") or ""),
        "quote_version": str(receipt.get("quote_version") or ""),
        "job_key_sha256": str(receipt.get("job_key_sha256") or ""),
        "session_nonce": str(receipt.get("session_nonce") or ""),
        "claim_token": str(receipt.get("claim_token") or ""),
        "media_sha256": str(receipt.get("media_sha256") or ""),
        "selected_tts_text_sha256": str(receipt.get("selected_tts_text_sha256") or ""),
        "timeline_signature": str(receipt.get("timeline_signature") or ""),
        "actual_auto_xu": int(receipt.get("actual_auto_xu") or 0),
        "actual_subtitle_xu": int(receipt.get("actual_subtitle_xu") or 0),
        "actual_total_xu": int(receipt.get("actual_total_xu") or 0),
    }
    digest = hashlib.sha256(
        json.dumps(
            identity,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:32]
    return f"subdub:auto:{internal_job_id}:{digest}"


def _durable_video_delivery(job: dict) -> bool:
    terminal = str(job.get("terminal_state") or "").strip().lower()
    message_id = str(
        job.get("video_delivery_message_id")
        or job.get("final_video_message_id")
        or job.get("delivery_message_id")
        or ""
    ).strip()
    file_id = str(job.get("video_delivery_file_id") or "").strip()
    size_bytes = int(job.get("video_delivery_size_bytes") or 0)
    sha256 = str(job.get("video_delivery_sha256") or "").strip().lower()
    mime_type = str(job.get("video_delivery_mime_type") or "").strip().lower()
    validation = dict(job.get("output_validation") or {})
    try:
        duration_seconds = float(
            job.get("video_delivery_duration_seconds")
            or validation.get("actual_duration")
            or validation.get("duration")
            or 0.0
        )
    except (TypeError, ValueError, OverflowError):
        duration_seconds = 0.0
    return bool(
        terminal == "delivered"
        and job.get("output_sent") is True
        and job.get("delivery_succeeded") is True
        and job.get("final_mp4_validated") is True
        and job.get("final_mp4_delivered") is True
        and message_id
        and file_id
        and size_bytes > 0
        and re.fullmatch(r"[0-9a-f]{64}", sha256)
        and mime_type == "video/mp4"
        and duration_seconds > 0
        and validation.get("ok") is True
    )


def _identity_reason(
    job: dict,
    receipt: dict,
    *,
    internal_job_id: str,
    user_id: str,
    amount_xu: int,
    expected_receipt_version: str,
    expected_quote_version: str,
) -> str:
    if not (
        str(job.get("voice_kind") or "") == "auto_speaker_gender"
        and str(job.get("voice_selection_mode") or "") == "auto_speaker"
    ):
        return "auto_identity_required"
    if not receipt:
        return "auto_receipt_required"
    job_mode = str(job.get("mode") or job.get("mapped_mode") or "").strip()
    job_key = str(job.get("job_key") or "").strip()
    chat_id = str(job.get("chat_id") or "").strip()
    session_nonce = str(job.get("auto_exact_session_nonce") or "").strip()
    claim_token = str(job.get("auto_exact_claim_token") or "").strip()
    actual_auto_xu = int(receipt.get("actual_auto_xu") or 0)
    actual_subtitle_xu = int(receipt.get("actual_subtitle_xu") or 0)
    required_hashes = (
        str(receipt.get("media_sha256") or ""),
        str(receipt.get("selected_tts_text_sha256") or ""),
        str(receipt.get("timeline_signature") or ""),
    )
    if not all(len(value) == 64 for value in required_hashes):
        return "receipt_identity_mismatch"
    if not all(
        (
            str(job.get("feature") or "") == "subtitle_dub",
            str(job.get("internal_job_id") or job.get("job_id") or "") == internal_job_id,
            str(job.get("user_id") or "") == user_id,
            bool(job_mode),
            bool(job_key),
            bool(chat_id),
            bool(session_nonce),
            bool(claim_token),
            str(receipt.get("internal_job_id") or "") == internal_job_id,
            str(receipt.get("owner_user_id") or "") == user_id,
            str(receipt.get("chat_id") or "") == chat_id,
            str(receipt.get("job_key_sha256") or "")
            == hashlib.sha256(job_key.encode("utf-8")).hexdigest(),
            str(receipt.get("session_nonce") or "") == session_nonce,
            str(receipt.get("claim_token") or "") == claim_token,
            str(receipt.get("mode") or "") == job_mode,
            str(receipt.get("version") or "") == expected_receipt_version,
            str(receipt.get("quote_version") or "") == expected_quote_version,
            int(receipt.get("actual_total_xu") or 0) == amount_xu,
            actual_auto_xu >= 0,
            actual_subtitle_xu >= 0,
            actual_auto_xu + actual_subtitle_xu == amount_xu,
            receipt.get("consumed") is True,
            str(receipt.get("claim_state") or "") in {"resuming", "charged"},
        )
    ):
        return "receipt_identity_mismatch"
    return ""


def settle_after_delivery(
    *,
    connection_factory: Callable[[], sqlite3.Connection],
    record_credit_event: Callable[..., object],
    setting_key: str,
    internal_job_id: str,
    user_id,
    amount_xu: int,
    expected_receipt_version: str,
    expected_quote_version: str,
    event_type: str,
    note: str = "",
    now_value: str = "",
) -> dict:
    """Debit once inside the same transaction that marks an Auto job charged."""

    safe_job_id = str(internal_job_id or "").strip()
    safe_user_id = str(user_id or "").strip()
    safe_setting_key = str(setting_key or "").strip()
    amount = int(amount_xu or 0)
    if not safe_job_id or not safe_user_id or not safe_setting_key or amount <= 0:
        return {"ok": False, "reason": "invalid_settlement_request"}

    conn = connection_factory()
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key=? LIMIT 1",
            (safe_setting_key,),
        ).fetchone()
        if not row:
            conn.rollback()
            return {"ok": False, "reason": "durable_job_missing"}
        old_value = str(row[0] or "")
        try:
            job = json.loads(old_value)
        except (TypeError, ValueError, json.JSONDecodeError):
            conn.rollback()
            return {"ok": False, "reason": "durable_job_invalid"}
        if not isinstance(job, dict):
            conn.rollback()
            return {"ok": False, "reason": "durable_job_invalid"}
        if not _durable_video_delivery(job):
            conn.rollback()
            return {"ok": False, "reason": "durable_delivery_required"}

        receipt = dict(job.get("auto_exact_receipt") or {})
        identity_reason = _identity_reason(
            job,
            receipt,
            internal_job_id=safe_job_id,
            user_id=safe_user_id,
            amount_xu=amount,
            expected_receipt_version=str(expected_receipt_version or ""),
            expected_quote_version=str(expected_quote_version or ""),
        )
        if identity_reason:
            conn.rollback()
            return {"ok": False, "reason": identity_reason}

        ref_id = _stable_ref_id(safe_job_id, receipt)
        ledger_rows = conn.execute(
            "SELECT delta FROM credit_events WHERE ref_id=? ORDER BY id",
            (ref_id,),
        ).fetchall()
        if len(ledger_rows) > 1 or (
            ledger_rows and int(ledger_rows[0][0] or 0) != -amount
        ):
            conn.rollback()
            return {"ok": False, "reason": "ledger_ref_conflict"}
        ledger_committed = bool(ledger_rows)

        def persist_charged_job(balance_after: int) -> None:
            receipt.update(
                {
                    "claim_state": "charged",
                    "settled_at": str(now_value or ""),
                    "settlement_ref_id": ref_id,
                }
            )
            job.update(
                {
                    "auto_exact_receipt": receipt,
                    "charge_status": "charged",
                    "charged_xu": amount,
                    "settlement_ref_id": ref_id,
                    "settled_at": str(now_value or ""),
                    "account_balance_xu": int(balance_after),
                }
            )
            new_value = json.dumps(job, ensure_ascii=False, separators=(",", ":"))
            updated = conn.execute(
                """UPDATE system_settings
                SET value=?, note=?, updated_at=?, updated_by=?
                WHERE key=? AND value=?""",
                (
                    new_value,
                    "subdub auto post-delivery settlement",
                    str(now_value or ""),
                    safe_user_id,
                    safe_setting_key,
                    old_value,
                ),
            )
            if int(updated.rowcount or 0) != 1:
                raise sqlite3.OperationalError(
                    "durable settlement compare-and-swap failed"
                )

        already_charged = str(job.get("charge_status") or "") == "charged"
        if already_charged:
            if (
                not ledger_committed
                or
                int(job.get("charged_xu") or 0) != amount
                or str(job.get("settlement_ref_id") or "") != ref_id
                or str(receipt.get("claim_state") or "") != "charged"
            ):
                conn.rollback()
                return {"ok": False, "reason": "settlement_identity_conflict"}
            balance_row = conn.execute(
                "SELECT credits FROM users WHERE user_id=? LIMIT 1",
                (safe_user_id,),
            ).fetchone()
            conn.rollback()
            return {
                "ok": True,
                "already_charged": True,
                "charged_xu": amount,
                "balance_after": int(balance_row[0] or 0) if balance_row else 0,
                "ref_id": ref_id,
                "job": job,
            }

        if ledger_committed:
            balance_row = conn.execute(
                "SELECT credits FROM users WHERE user_id=? LIMIT 1",
                (safe_user_id,),
            ).fetchone()
            balance_after = int(balance_row[0] or 0) if balance_row else 0
            persist_charged_job(balance_after)
            conn.commit()
            return {
                "ok": True,
                "already_charged": True,
                "charged_xu": amount,
                "balance_after": balance_after,
                "ref_id": ref_id,
                "job": job,
            }

        cursor = conn.execute(
            """UPDATE users
            SET credits=credits-?, total_spent=total_spent+?
            WHERE user_id=? AND credits>=?""",
            (amount, amount, safe_user_id, amount),
        )
        if int(cursor.rowcount or 0) != 1:
            conn.rollback()
            return {"ok": False, "reason": "insufficient_balance"}

        record_credit_event(
            conn,
            safe_user_id,
            -amount,
            str(event_type or "subdub_auto_final_delivery"),
            ref_id,
            str(note or ""),
        )
        balance_row = conn.execute(
            "SELECT credits FROM users WHERE user_id=? LIMIT 1",
            (safe_user_id,),
        ).fetchone()
        balance_after = int(balance_row[0] or 0) if balance_row else 0
        persist_charged_job(balance_after)
        conn.commit()
        return {
            "ok": True,
            "already_charged": False,
            "charged_xu": amount,
            "balance_after": balance_after,
            "ref_id": ref_id,
            "job": job,
        }
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()
