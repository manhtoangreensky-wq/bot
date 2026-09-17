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

# Canonical topup packages fallback in case caller doesn't supply them
CANONICAL_PAYMENT_PACKAGES = {
    "10k": {"amount": 10000, "xu": 100, "text": "Mệnh giá 10k: 10.000đ ➔ 100 Xu"},
    "20k": {"amount": 20000, "xu": 200, "text": "Mệnh giá 20k: 20.000đ ➔ 200 Xu"},
    "50k": {"amount": 50000, "xu": 500, "text": "Mệnh giá 50k: 50.000đ ➔ 500 Xu"},
    "100k": {"amount": 100000, "xu": 1000, "text": "Mệnh giá 100k: 100.000đ ➔ 1.000 Xu"},
    "200k": {"amount": 200000, "xu": 2000, "text": "Mệnh giá 200k: 200.000đ ➔ 2.000 Xu"},
    "500k": {"amount": 500000, "xu": 5000, "text": "Mệnh giá 500k: 500.000đ ➔ 5.000 Xu"},
}

CANONICAL_PLAN_CATALOG = {
    "starter": {
        "name": "Starter",
        "price_vnd": 49000,
        "duration_days": 30,
        "required_member_tier": "silver",
        "plan_xu": 600,
        "description": "Dành cho người mới làm content: chat thường, dịch ngắn, PDF cơ bản, prompt ảnh/video và workflow nhỏ",
    },
    "creator": {
        "name": "Creator",
        "price_vnd": 99000,
        "duration_days": 30,
        "required_member_tier": "silver",
        "plan_xu": 1300,
        "description": "Dành cho creator, affiliate hoặc shop nhỏ cần prompt/content/ảnh đều đặn",
    },
    "pro": {
        "name": "Pro",
        "price_vnd": 199000,
        "duration_days": 30,
        "required_member_tier": "gold",
        "plan_xu": 3000,
        "description": "Dành cho người dùng thường xuyên, có thể ưu tiên queue/tác vụ file/audio vừa khi công cụ mở",
    },
    "business": {
        "name": "Business",
        "price_vnd": 499000,
        "duration_days": 30,
        "required_member_tier": "gold_or_admin_approve",
        "plan_xu": 8000,
        "description": "Dành cho team nhỏ, shop hoặc affiliate team cần workflow content + ảnh + voice/audio",
    },
}


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
    except Exception:
        try:
            conn = sqlite3.connect(db_path, timeout=10)
        except Exception as exc:
            logger.error(f"Cannot connect to wallet database: {exc}")
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
    except Exception:
        try:
            conn = sqlite3.connect(db_path, timeout=10)
        except Exception as exc:
            logger.error(f"Cannot connect to wallet database: {exc}")
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


def read_canonical_pricing_catalog() -> tuple[bool, dict[str, Any], int]:
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

        video_combos = [
            {
                "code": "combo_product_video_3scene",
                "label": "Combo 3 phân cảnh",
                "summary": "Tối ưu cho quảng cáo TikTok / Reels 15-20s",
            },
            {
                "code": "combo_product_video_5scene",
                "label": "Combo 5 phân cảnh",
                "summary": "Tối ưu cho video sản phẩm chi tiết 30-45s",
            },
        ]

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
    try:
        active_plans = plan_catalog or CANONICAL_PLAN_CATALOG
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
            for code, plan in active_plans.items()
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

        active_topup = payment_packages or CANONICAL_PAYMENT_PACKAGES
        topup_rows = [
            {
                "code": str(code),
                "amount_vnd": int(pkg.get("amount") or 0),
                "xu": int(pkg.get("xu") or 0),
                "label": str(pkg.get("text") or code),
            }
            for code, pkg in active_topup.items()
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
