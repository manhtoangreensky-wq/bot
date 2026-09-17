"""Canonical Bot Core customer read model service (P0.BOT.INTERNAL.CUSTOMER.READ.MODEL.API.V1).

Provides read-only queries for customer wallet, ledger history, canonical pricing,
and packages without mutations, wallet deductions, or third-party provider calls.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from typing import Any, Callable

logger = logging.getLogger("customer_read_model_service")

def calculate_canonical_total_paid_vnd(c: sqlite3.Cursor, user_id: str) -> tuple[int | None, int | None]:
    """Query lifetime proven deposited VND and Xu from canonical database tables.

    Returns (total_paid_vnd, total_deposited_vnd).
    Returns (None, None) if tables or user data cannot be proven.
    """
    clean_uid = normalize_target_user_id(user_id)
    if not clean_uid:
        return None, None

    try:
        # 1. PayOS completed orders
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payos_orders'")
        has_payos = c.fetchone() is not None
        payos_vnd = 0
        if has_payos:
            c.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payos_orders "
                "WHERE user_id = ? AND status IN ('PAID', 'completed')",
                (clean_uid,),
            )
            p_row = c.fetchone()
            payos_vnd = int(p_row[0] or 0) if p_row else 0

        # 2. Approved manual topups
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pending_deposits'")
        has_pending_deposits = c.fetchone() is not None
        manual_vnd = 0
        if has_pending_deposits:
            c.execute(
                "SELECT COALESCE(SUM(amount_vnd), 0) FROM pending_deposits "
                "WHERE user_id = ? AND status IN ('approved', 'completed')",
                (clean_uid,),
            )
            m_row = c.fetchone()
            manual_vnd = int(m_row[0] or 0) if m_row else 0

        # 3. Check total_paid_vnd on users if present
        c.execute("PRAGMA table_info(users)")
        user_cols = {r[1] for r in c.fetchall()}
        stored_paid_vnd = 0
        if "total_paid_vnd" in user_cols:
            c.execute("SELECT COALESCE(total_paid_vnd, 0) FROM users WHERE user_id = ?", (clean_uid,))
            row_tp = c.fetchone()
            stored_paid_vnd = int(row_tp[0] or 0) if row_tp else 0

        proven_vnd = max(stored_paid_vnd, payos_vnd + manual_vnd)
        return proven_vnd, proven_vnd
    except Exception as exc:
        logger.warning(f"Could not compute lifetime deposited VND: {exc}")
        return None, None


def normalize_target_user_id(raw_user_id: str | int | None) -> str:
    """Strip telegram- prefix and whitespace to produce canonical user_id."""
    clean = str(raw_user_id or "").strip()
    if clean.startswith("telegram-"):
        clean = clean[len("telegram-"):].strip()
    return clean


def read_canonical_wallet(
    user_id: str | int | None,
    db_path: str,
) -> tuple[bool, dict[str, Any], int]:
    """Read wallet balance and reconcile against credit_events ledger.

    Returns (ok, payload_dict, http_status).
    Guarantees:
    - Zero mutations / zero wallet credit or debit
    - Catches snapshot vs ledger mismatch and fails closed (status='guarded', error_code='WALLET_LEDGER_UNRECONCILED')
    - Returns unverified when user does not exist in users table
    """
    clean_uid = normalize_target_user_id(user_id)
    if not clean_uid:
        return (
            False,
            {
                "ok": False,
                "status": "unlinked",
                "status_name": "unlinked",
                "error_code": "ACCOUNT_TELEGRAM_UNLINKED",
                "message": "Tài khoản chưa liên kết Telegram.",
                "data": None,
            },
            200,
        )

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    except Exception as exc:
        logger.error(f"Cannot connect to wallet database in read-only mode: {exc}")
        return (
            False,
            {
                "ok": False,
                "status": "guarded",
                "status_name": "guarded",
                "error_code": "WALLET_DATABASE_UNAVAILABLE",
                "message": "Cơ sở dữ liệu ví canonical tạm thời không khả dụng.",
                "data": None,
            },
            200,
        )

    try:
        c = conn.cursor()
        c.execute("SELECT credits, is_vip, join_date, username FROM users WHERE user_id = ?", (clean_uid,))
        user_row = c.fetchone()
        if not user_row:
            return (
                False,
                {
                    "ok": False,
                    "status": "unverified",
                    "status_name": "unverified",
                    "error_code": "BOT_USER_NOT_INITIALIZED",
                    "message": "Tài khoản Telegram chưa kích hoạt trong hệ thống Bot.",
                    "data": None,
                },
                200,
            )

        snapshot_credits = int(user_row[0] or 0)
        is_vip = bool(user_row[1])

        # Lifetime proven paid / deposited VND
        total_paid_vnd, total_deposited_vnd = calculate_canonical_total_paid_vnd(c, clean_uid)

        # Query total spent from credit_events ledger (sum of negative deltas)
        c.execute(
            "SELECT COALESCE(SUM(ABS(delta)), 0) FROM credit_events WHERE user_id = ? AND delta < 0",
            (clean_uid,),
        )
        total_spent_row = c.fetchone()
        total_spent_xu = int(total_spent_row[0] or 0) if total_spent_row else 0

        # Real wallet reconciliation: check latest ledger event balance_after
        c.execute(
            "SELECT balance_after FROM credit_events WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (clean_uid,),
        )
        latest_event = c.fetchone()

        if latest_event is None:
            ledger_balance = 0
            is_reconciled = (snapshot_credits == 0)
        else:
            ledger_balance = int(latest_event[0] or 0)
            is_reconciled = (snapshot_credits == ledger_balance)

        discrepancy = snapshot_credits - ledger_balance

        if not is_reconciled:
            return (
                False,
                {
                    "ok": False,
                    "status": "guarded",
                    "status_name": "guarded",
                    "error_code": "WALLET_LEDGER_UNRECONCILED",
                    "message": "Phát hiện sai lệch đối soát giữa số dư ví và sổ cái giao dịch.",
                    "data": {
                        "balance_xu": snapshot_credits,
                        "total_spent_xu": total_spent_xu,
                        "total_paid_vnd": total_paid_vnd,
                        "total_deposited_vnd": total_deposited_vnd,
                        "is_vip": is_vip,
                        "source": "canonical_ledger",
                        "reconciliation": {
                            "reconciled": False,
                            "status": "unreconciled_discrepancy",
                            "snapshot_credits": snapshot_credits,
                            "ledger_credits": ledger_balance,
                            "discrepancy": discrepancy,
                        },
                    },
                },
                200,
            )

        return (
            True,
            {
                "ok": True,
                "status": "read_only",
                "status_name": "read_only",
                "message": "Số dư ví canonical đã sẵn sàng.",
                "data": {
                    "balance_xu": snapshot_credits,
                    "total_spent_xu": total_spent_xu,
                    "total_paid_vnd": total_paid_vnd,
                    "total_deposited_vnd": total_deposited_vnd,
                    "is_vip": is_vip,
                    "source": "canonical_ledger",
                    "reconciliation": {
                        "reconciled": True,
                        "status": "reconciled",
                        "snapshot_credits": snapshot_credits,
                        "ledger_credits": ledger_balance,
                        "discrepancy": 0,
                    },
                },
            },
            200,
        )
    except Exception as exc:
        logger.error(f"Error querying wallet data: {exc}")
        return (
            False,
            {
                "ok": False,
                "status": "guarded",
                "status_name": "guarded",
                "error_code": "WALLET_DATABASE_UNAVAILABLE",
                "message": "Lỗi truy vấn số dư ví canonical.",
                "data": None,
            },
            200,
        )
    finally:
        conn.close()


def read_canonical_wallet_history(
    user_id: str | int | None,
    db_path: str,
    limit: int = 50,
) -> tuple[bool, dict[str, Any], int]:
    """Read wallet credit/debit events from credit_events ledger."""
    clean_uid = normalize_target_user_id(user_id)
    if not clean_uid:
        return (
            False,
            {
                "ok": False,
                "status": "unlinked",
                "status_name": "unlinked",
                "error_code": "ACCOUNT_TELEGRAM_UNLINKED",
                "message": "Tài khoản chưa liên kết Telegram.",
                "data": {"items": []},
            },
            200,
        )

    safe_limit = max(1, min(100, int(limit or 50)))

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    except Exception as exc:
        logger.error(f"Cannot connect to wallet database in read-only mode: {exc}")
        return (
            False,
            {
                "ok": False,
                "status": "guarded",
                "status_name": "guarded",
                "error_code": "WALLET_DATABASE_UNAVAILABLE",
                "message": "Không thể kết nối cơ sở dữ liệu lịch sử ví.",
                "data": {"items": []},
            },
            200,
        )

    try:
        c = conn.cursor()
        c.execute(
            "SELECT created_at, event_type, delta, balance_after "
            "FROM credit_events WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (clean_uid, safe_limit),
        )
        rows = c.fetchall()

        items = [
            {
                "created_at": str(r[0] or "")[:160],
                "event_type": str(r[1] or "")[:160],
                "delta_xu": int(r[2] or 0),
                "balance_after_xu": int(r[3] or 0),
            }
            for r in rows
        ]

        return (
            True,
            {
                "ok": True,
                "status": "read_only",
                "status_name": "read_only",
                "message": "Lịch sử biến động Xu canonical.",
                "data": {"items": items},
            },
            200,
        )
    except Exception as exc:
        logger.error(f"Error querying credit_events: {exc}")
        return (
            False,
            {
                "ok": False,
                "status": "guarded",
                "status_name": "guarded",
                "error_code": "WALLET_HISTORY_UNAVAILABLE",
                "message": "Lỗi đọc lịch sử biến động Xu canonical.",
                "data": {"items": []},
            },
            200,
        )
    finally:
        conn.close()


def read_canonical_pricing_catalog(
    combo_catalog_fn: Callable[[], dict[str, Any]] | None = None,
) -> tuple[bool, dict[str, Any], int]:
    """Read canonical public pricing from Bot reviewed catalog (video_ai_real_pricing)."""
    try:
        from services import video_ai_real_pricing

        image_catalog = video_ai_real_pricing.public_image_quality_catalog()
        video_catalog = video_ai_real_pricing.public_quality_catalog()

        image_tiers = [
            {
                "code": str(item["tier_key"]),
                "label": str(item.get("name") or item["tier_key"]),
                "note": str(item.get("use_case") or item.get("public_detail") or ""),
                "retry_warranty_count": int(item.get("retry_warranty_count") or 0),
                "unit_xu": int(item.get("unit_xu") or 0),
            }
            for item in image_catalog
        ]

        video_tiers = [
            {
                "code": str(item["tier_id"]),
                "label": str(item.get("name") or f"Tier {item['tier_id']}"),
                "note": str(item.get("use_case") or item.get("public_detail") or ""),
                "retry_warranty_count": 0,
                "unit_xu": int(item.get("unit_xu") or 0),
            }
            for item in video_catalog
        ]

        video_combos = []
        if combo_catalog_fn is not None:
            try:
                combos_data = combo_catalog_fn() or {}
                for code, combo in combos_data.items():
                    if isinstance(combo, dict):
                        video_combos.append({
                            "code": str(code),
                            "label": str(combo.get("label") or code),
                            "summary": str(combo.get("note") or ""),
                        })
            except Exception as exc:
                logger.warning(f"Could not load dynamic combos for pricing catalog: {exc}")

        public_sale_items = [
            {
                "code": str(item["tier_key"]),
                "family": "image",
                "label": str(item.get("name") or item["tier_key"]),
                "sale_price_xu": int(item.get("unit_xu") or 0),
                "status": "active",
            }
            for item in image_catalog
        ] + [
            {
                "code": str(item["tier_id"]),
                "family": "video",
                "label": str(item.get("name") or f"Tier {item['tier_id']}"),
                "sale_price_xu": int(item.get("unit_xu") or 0),
                "status": "active",
            }
            for item in video_catalog
        ]

        public_sale_catalog = {
            "available": True,
            "catalog_version": getattr(video_ai_real_pricing, "CATALOG_VERSION", "2026-08-11.video.5"),
            "approval_status": "canonical_approved",
            "items": public_sale_items,
        }

        return (
            True,
            {
                "ok": True,
                "status": "read_only",
                "status_name": "read_only",
                "message": "Bảng giá canonical TOAN AAS.",
                "data": {
                    "available": True,
                    "billing_mode": "prepaid_xu",
                    "price_table_source": "canonical_bot_core",
                    "image_tiers": image_tiers,
                    "video_tiers": video_tiers,
                    "video_combos": video_combos,
                    "public_sale_catalog": public_sale_catalog,
                },
            },
            200,
        )
    except Exception as exc:
        logger.error(f"Error reading pricing catalog: {exc}")
        return (
            False,
            {
                "ok": False,
                "status": "guarded",
                "status_name": "guarded",
                "error_code": "PRICING_CATALOG_UNAVAILABLE",
                "message": "Bảng giá canonical tạm thời không khả dụng.",
                "data": None,
            },
            200,
        )


def read_canonical_packages_catalog(
    plan_catalog: dict[str, Any] | None = None,
    combo_catalog_fn: Callable[[], dict[str, Any]] | None = None,
    payment_packages: dict[str, Any] | None = None,
) -> tuple[bool, dict[str, Any], int]:
    """Read canonical monthly plans, combos, and topup packages."""
    if not plan_catalog or not payment_packages:
        return (
            False,
            {
                "ok": False,
                "status": "guarded",
                "status_name": "guarded",
                "error_code": "PACKAGES_CATALOG_UNAVAILABLE",
                "message": "Danh mục gói canonical chưa được cấu hình hoặc không khả dụng.",
                "data": None,
            },
            200,
        )

    try:
        monthly_rows = [
            {
                "code": str(code),
                "type": "monthly",
                "label": str(plan.get("name") or code),
                "note": str(plan.get("description") or ""),
                "default_days": int(plan.get("duration_days") or 30),
                "manual": False,
                "items": {"xu": int(plan.get("plan_xu") or 0)},
            }
            for code, plan in plan_catalog.items()
            if isinstance(plan, dict)
        ]

        combos_data: dict[str, Any] = {}
        if combo_catalog_fn is not None:
            try:
                combos_data = combo_catalog_fn() or {}
            except Exception as exc:
                logger.warning(f"Could not load dynamic combos: {exc}")

        combo_rows = []
        for code, combo in combos_data.items():
            if not isinstance(combo, dict):
                continue
            raw_items = combo.get("items") if isinstance(combo.get("items"), dict) else {}
            combo_rows.append({
                "code": str(code),
                "type": "combo",
                "label": str(combo.get("label") or code),
                "note": str(combo.get("note") or ""),
                "default_days": int(combo.get("default_days") or 0),
                "manual": bool(combo.get("manual", False)),
                "items": {
                    str(k): int(v)
                    for k, v in raw_items.items()
                    if isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool) and v >= 0
                },
            })

        topup_rows = [
            {
                "code": str(code),
                "amount_vnd": int(pkg.get("amount") or 0),
                "xu": int(pkg.get("xu") or 0),
                "label": str(pkg.get("text") or code),
            }
            for code, pkg in payment_packages.items()
            if isinstance(pkg, dict)
        ]

        return (
            True,
            {
                "ok": True,
                "status": "read_only",
                "status_name": "read_only",
                "message": "Danh mục gói và combo canonical TOAN AAS.",
                "data": {
                    "available": True,
                    "monthly": monthly_rows,
                    "combos": combo_rows,
                    "topup": topup_rows,
                },
            },
            200,
        )
    except Exception as exc:
        logger.error(f"Error reading packages catalog: {exc}")
        return (
            False,
            {
                "ok": False,
                "status": "guarded",
                "status_name": "guarded",
                "error_code": "PACKAGES_CATALOG_UNAVAILABLE",
                "message": "Danh mục gói canonical tạm thời không khả dụng.",
                "data": None,
            },
            200,
        )
