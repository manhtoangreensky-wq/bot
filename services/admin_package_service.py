"""Canonical Bot Core Admin Packages Commercial Authority Service (B03).

Implements the single canonical Bot-owned package configuration and commercial override authority.
Guarantees:
- Single source of truth for Bot membership plans, service combos, and monthly packages
- Clean separation: Top-up packages / PayOS denomination packs remain strictly in B05 (TOPUP_PACKAGE_KEYS_IN_B03=0)
- Zero invented package models: exact runtime identities proven from PLAN_CATALOG and package_catalog_payload
- Durable, versioned, append-only audit trail with cryptographic mutation digest
- Optimistic concurrency control via expected_version CAS (stale -> 409 Conflict)
- Strict field whitelist: display_name, description, price_vnd, public_visible, commercial_enabled, sort_order
- Hard immutability: package_key, package_type, duration_days, benefits/items, plan_xu, member tier
- Idempotent request replay via request_id: deduplicated without double version increment or duplicate audit
- Atomic persistence with immediate fresh canonical readback and customer runtime propagation
- Zero mutations to wallet balances, user credits, payment records, or external provider calls
"""

from __future__ import annotations

from copy import deepcopy
import datetime
import hashlib
import json
import logging
from pathlib import Path
import sqlite3
import time
from typing import Any

logger = logging.getLogger("admin_package_service")

DEFAULT_ADMIN_ID = "7126457028"

# ─── CANONICAL BASE PACKAGES CATALOG ──────────────────────────────────────────
# Authoritative single canonical package definitions covering all commercial customer domains.
# Sourced dynamically from runtime base resolvers:
# - Subscription: bot.BASE_PLAN_CATALOG (fallback bot.PLAN_CATALOG)
# - Combo: bot.p0_21d_combo_catalog_base(include_legacy=True)
# - Service Monthly: bot.p0_21d_task_package_base()
# Metadata is attached from config/base_packages_catalog.json (non-authoritative).

CATALOG_PATH = Path(__file__).resolve().parent.parent / "config" / "base_packages_catalog.json"


def _load_base_packages_metadata() -> dict[str, dict[str, Any]]:
    """Load non-authoritative metadata from JSON."""
    if CATALOG_PATH.exists():
        try:
            with open(CATALOG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Could not load base_packages_catalog.json: %s", exc)
    return {}


def derive_canonical_base_packages_catalog() -> dict[str, dict[str, Any]]:
    """Dynamically derive full base package definitions from runtime base authorities.

    Commercial fields (display_name, description, price_vnd, duration_days, benefits,
    public_visible, commercial_enabled) are derived directly from the canonical runtime base:
    - subscription: bot.BASE_PLAN_CATALOG (fallback bot.PLAN_CATALOG)
    - combo: bot.p0_21d_combo_catalog_base(include_legacy=True)
    - service_monthly: bot.p0_21d_task_package_base()

    Metadata (sort_order, group, read_authority, quote_authority, entitlement_authority)
    is attached from config/base_packages_catalog.json.

    Guarantees:
    - CANONICAL_BASE_SOURCE_COUNT_PER_PACKAGE = 1
    - PACKAGE_PRICE_DUAL_AUTHORITY_COUNT = 0
    - DUAL_BASE_AUTHORITY_COUNT = 0
    """
    metadata_cat = _load_base_packages_metadata()

    import sys
    bot_mod = sys.modules.get("bot")
    if not bot_mod:
        try:
            import bot as bot_mod
        except Exception:
            bot_mod = None

    subs = getattr(bot_mod, "BASE_PLAN_CATALOG", None) if bot_mod else None
    if not subs and bot_mod:
        subs = getattr(bot_mod, "PLAN_CATALOG", {})
    subs = subs or {}

    combo_resolver = getattr(bot_mod, "p0_21d_combo_catalog_base", None) if bot_mod else None
    combos = combo_resolver(include_legacy=True) if callable(combo_resolver) else {}

    monthly_resolver = getattr(bot_mod, "p0_21d_task_package_base", None) if bot_mod else None
    monthlies = monthly_resolver() if callable(monthly_resolver) else {}

    catalog: dict[str, dict[str, Any]] = {}

    # 1. Subscription packages (4)
    for key, r in subs.items():
        meta = metadata_cat.get(key, {})
        catalog[key] = {
            "package_key": key,
            "package_type": "subscription",
            "display_name": r.get("name", key),
            "description": r.get("description", ""),
            "price_vnd": int(r.get("price_vnd", 0)),
            "duration_days": int(r.get("duration_days", 30)),
            "benefits": {"xu": int(r.get("plan_xu", 0))},
            "public_visible": bool(r.get("public_visible", True)),
            "commercial_enabled": bool(r.get("commercial_enabled", True)),
            "sort_order": int(meta.get("sort_order", 10)),
            "group": str(meta.get("group", "subscription")),
            "read_authority": str(meta.get("read_authority", "bot.PLAN_CATALOG")),
            "quote_authority": str(meta.get("quote_authority", "bot.purchase_plan_payos_checkout")),
            "entitlement_authority": str(meta.get("entitlement_authority", "bot.purchase_plan_payos_checkout")),
        }

    # 2. Combo packages (20)
    for key, r in combos.items():
        meta = metadata_cat.get(key, {})
        catalog[key] = {
            "package_key": key,
            "package_type": "combo",
            "display_name": r.get("label", key),
            "description": r.get("note", ""),
            "price_vnd": int(r.get("price_vnd", 0)),
            "duration_days": int(r.get("default_days") or 30),
            "benefits": deepcopy(r.get("items", {})),
            "public_visible": bool(r.get("public", True)),
            "commercial_enabled": bool(r.get("commercial_enabled", True)),
            "sort_order": int(meta.get("sort_order", 50)),
            "group": str(meta.get("group", r.get("group", "combo"))),
            "read_authority": str(meta.get("read_authority", 'bot.package_catalog_payload["combos"]')),
            "quote_authority": str(meta.get("quote_authority", "bot.package_price_quote")),
            "entitlement_authority": str(meta.get("entitlement_authority", "bot.grant_user_package_conn")),
        }

    # 3. Service monthly packages (34)
    for key, r in monthlies.items():
        meta = metadata_cat.get(key, {})
        catalog[key] = {
            "package_key": key,
            "package_type": "service_monthly",
            "display_name": r.get("label", key),
            "description": r.get("note", ""),
            "price_vnd": int(r.get("price_vnd", 0)),
            "duration_days": int(r.get("default_days") or 30),
            "benefits": deepcopy(r.get("items", {})),
            "public_visible": bool(r.get("public", True)),
            "commercial_enabled": bool(r.get("commercial_enabled", True)),
            "sort_order": int(meta.get("sort_order", 300)),
            "group": str(meta.get("group", r.get("group", "monthly"))),
            "read_authority": str(meta.get("read_authority", 'bot.package_catalog_payload["monthly"]')),
            "quote_authority": str(meta.get("quote_authority", "bot.package_price_quote")),
            "entitlement_authority": str(meta.get("entitlement_authority", "bot.grant_user_package_conn")),
        }

    return catalog


class CanonicalBasePackagesCatalog(dict):
    """Dynamic dict proxy providing single canonical package authority.
    Always resolves commercial fields dynamically from runtime base resolvers."""
    _cached_catalog: dict[str, dict[str, Any]] | None = None

    @classmethod
    def invalidate_cache(cls) -> None:
        cls._cached_catalog = None

    def _get_catalog(self) -> dict[str, dict[str, Any]]:
        if CanonicalBasePackagesCatalog._cached_catalog is None:
            CanonicalBasePackagesCatalog._cached_catalog = derive_canonical_base_packages_catalog()
        return CanonicalBasePackagesCatalog._cached_catalog

    def __getitem__(self, key: str) -> dict[str, Any]:
        cat = self._get_catalog()
        if key not in cat:
            raise KeyError(key)
        return cat[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._get_catalog().get(key, default)

    def __contains__(self, key: object) -> bool:
        return key in self._get_catalog()

    def __iter__(self):
        return iter(self._get_catalog())

    def __len__(self) -> int:
        return len(self._get_catalog())

    def items(self):
        return self._get_catalog().items()

    def values(self):
        return self._get_catalog().values()

    def keys(self):
        return self._get_catalog().keys()

    def __copy__(self):
        return self._get_catalog()

    def __deepcopy__(self, memo):
        return deepcopy(self._get_catalog(), memo)


BASE_PACKAGE_CATALOG: dict[str, dict[str, Any]] = CanonicalBasePackagesCatalog()

# ─── FIELD CLASSIFICATIONS & WHITELISTS ──────────────────────────────────────

EFFECT_SCOPE_CUSTOMER_DISPLAY = "CUSTOMER_DISPLAY"
EFFECT_SCOPE_CUSTOMER_PRICE = "CUSTOMER_PRICE"
EFFECT_SCOPE_CUSTOMER_VISIBILITY = "CUSTOMER_VISIBILITY"
EFFECT_SCOPE_CUSTOMER_PURCHASE_GATE = "CUSTOMER_PURCHASE_GATE"
EFFECT_SCOPE_ADMIN_ORDER_ONLY = "ADMIN_ORDER_ONLY"
EFFECT_SCOPE_IMMUTABLE = "IMMUTABLE"

# Field classification and effect scopes per package type
PACKAGE_TYPE_FIELD_EFFECT_SCOPES: dict[str, dict[str, str]] = {
    "subscription": {
        "display_name": EFFECT_SCOPE_CUSTOMER_DISPLAY,
        "description": EFFECT_SCOPE_CUSTOMER_DISPLAY,
        "price_vnd": EFFECT_SCOPE_CUSTOMER_PRICE,
        "commercial_enabled": EFFECT_SCOPE_CUSTOMER_PURCHASE_GATE,
        "sort_order": EFFECT_SCOPE_ADMIN_ORDER_ONLY,
        "public_visible": EFFECT_SCOPE_IMMUTABLE,  # Non-editable: no customer listing consumer exists
    },
    "combo": {
        "display_name": EFFECT_SCOPE_CUSTOMER_DISPLAY,
        "description": EFFECT_SCOPE_CUSTOMER_DISPLAY,
        "price_vnd": EFFECT_SCOPE_CUSTOMER_PRICE,
        "public_visible": EFFECT_SCOPE_CUSTOMER_VISIBILITY,
        "commercial_enabled": EFFECT_SCOPE_CUSTOMER_PURCHASE_GATE,
        "sort_order": EFFECT_SCOPE_ADMIN_ORDER_ONLY,
    },
    "service_monthly": {
        "display_name": EFFECT_SCOPE_CUSTOMER_DISPLAY,
        "description": EFFECT_SCOPE_CUSTOMER_DISPLAY,
        "price_vnd": EFFECT_SCOPE_CUSTOMER_PRICE,
        "public_visible": EFFECT_SCOPE_CUSTOMER_VISIBILITY,
        "commercial_enabled": EFFECT_SCOPE_CUSTOMER_PURCHASE_GATE,
        "sort_order": EFFECT_SCOPE_ADMIN_ORDER_ONLY,
    },
}

def get_editable_fields_for_type(package_type: str) -> set[str]:
    """Return set of editable fields for a given package type."""
    scopes = PACKAGE_TYPE_FIELD_EFFECT_SCOPES.get(package_type, {})
    return {f for f, scope in scopes.items() if scope != EFFECT_SCOPE_IMMUTABLE}


EDITABLE_PACKAGE_FIELDS: set[str] = {
    "display_name",
    "description",
    "price_vnd",
    "public_visible",
    "commercial_enabled",
    "sort_order",
}

IMMUTABLE_PACKAGE_FIELDS: set[str] = {
    "package_key",
    "package_type",
    "duration_days",
    "benefits",
    "items",
    "plan_xu",
    "required_member_tier",
    "group",
    "read_authority",
    "quote_authority",
    "entitlement_authority",
    "wallet_mutations",
    "ledger",
    "historical_purchases",
    "balance",
    "credits",
}

# In-memory runtime override cache for fast customer resolution
_RUNTIME_PACKAGE_OVERRIDES: dict[str, dict[str, Any]] = {}
_INITIAL_PLAN_CATALOG_BACKUP: dict[str, dict[str, Any]] = {}



def utc_now_text() -> str:
    """Format current UTC time as YYYY-MM-DD HH:MM:SS."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def ensure_admin_package_schema(conn: sqlite3.Connection) -> None:
    """Ensure durable admin package overrides and audit tables exist."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS admin_package_overrides (
            package_key TEXT PRIMARY KEY,
            display_name TEXT,
            description TEXT,
            price_vnd INTEGER,
            public_visible INTEGER DEFAULT 1,
            commercial_enabled INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 10,
            version INTEGER NOT NULL DEFAULT 1,
            updated_at DATETIME NOT NULL,
            updated_by TEXT NOT NULL DEFAULT '',
            update_reason TEXT NOT NULL DEFAULT ''
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS admin_package_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            package_key TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            request_id TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL,
            previous_version INTEGER NOT NULL,
            new_version INTEGER NOT NULL,
            previous_values TEXT NOT NULL,
            new_values TEXT NOT NULL,
            mutation_digest TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            created_at DATETIME NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_package_audit_key ON admin_package_audit(package_key)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_package_audit_key_req ON admin_package_audit(package_key, request_id)"
    )


def compute_package_mutation_digest(
    package_key: str,
    new_version: int,
    accepted_changes: dict[str, Any],
    request_id: str,
    actor_id: str,
) -> str:
    """Compute sha256 mutation digest over canonical JSON."""
    payload = {
        "package_key": package_key,
        "new_version": new_version,
        "accepted_changes": accepted_changes,
        "request_id": request_id,
        "actor_id": actor_id,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve_effective_package(
    package_key: str,
    override_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve single package effective read model combining base definition and override."""
    if package_key not in BASE_PACKAGE_CATALOG:
        raise KeyError(f"Unknown package key: {package_key}")

    base = deepcopy(BASE_PACKAGE_CATALOG[package_key])
    effective = deepcopy(base)

    if override_row:
        if override_row.get("display_name") is not None:
            effective["display_name"] = str(override_row["display_name"])
        if override_row.get("description") is not None:
            effective["description"] = str(override_row["description"])
        if override_row.get("price_vnd") is not None:
            effective["price_vnd"] = int(override_row["price_vnd"])
        if override_row.get("public_visible") is not None:
            effective["public_visible"] = bool(override_row["public_visible"])
        if override_row.get("commercial_enabled") is not None:
            effective["commercial_enabled"] = bool(override_row["commercial_enabled"])
        if override_row.get("sort_order") is not None:
            effective["sort_order"] = int(override_row["sort_order"])

        effective["version"] = int(override_row.get("version", 1))
        effective["updated_at"] = override_row.get("updated_at")
        effective["updated_by"] = override_row.get("updated_by")
        effective["update_reason"] = override_row.get("update_reason")
        effective["has_override"] = True
    else:
        effective["version"] = 1
        effective["updated_at"] = None
        effective["updated_by"] = None
        effective["update_reason"] = None
        effective["has_override"] = False

    package_type = base.get("package_type", "")
    type_scopes = PACKAGE_TYPE_FIELD_EFFECT_SCOPES.get(package_type, {})
    editable_fields = sorted(list(get_editable_fields_for_type(package_type)))

    effective["field_classifications"] = {
        "editable_commercial": editable_fields,
        "field_effect_scopes": type_scopes,
        "immutable_identity": ["package_key", "package_type"],
        "immutable_execution": ["benefits", "duration_days", "required_member_tier", "group"],
        "immutable_financial_history": ["wallet_mutations", "historical_purchases"],
    }
    return effective


def get_canonical_package_collection(db_path: str) -> tuple[bool, dict[str, Any], int]:
    """Return all canonical packages with effective values and metadata."""
    try:
        conn = sqlite3.connect(db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        ensure_admin_package_schema(conn)

        cur = conn.cursor()
        cur.execute("SELECT * FROM admin_package_overrides")
        overrides = {row["package_key"]: dict(row) for row in cur.fetchall()}
        conn.close()

        items = []
        domain_counts = {"subscription": 0, "combo": 0, "service_monthly": 0}
        for key in sorted(BASE_PACKAGE_CATALOG.keys()):
            ov = overrides.get(key)
            item = resolve_effective_package(key, ov)
            items.append(item)
            ptype = item.get("package_type", "")
            if ptype in domain_counts:
                domain_counts[ptype] += 1

        # Effective sort_order is consumed by Admin collection order (effect_scope=ADMIN_ORDER_ONLY)
        items.sort(key=lambda x: (x.get("sort_order", 0), x.get("package_key", "")))

        return True, {
            "ok": True,
            "total_packages": len(items),
            "packages": items,
            "proven_domains": domain_counts,
            "catalog_version": "2026.09.b03.canonical",
        }, 200
    except Exception as exc:
        logger.exception("Error getting canonical package collection: %s", exc)
        return False, {
            "ok": False,
            "error_code": "INTERNAL_PACKAGE_ERROR",
            "message": str(exc),
        }, 500


def get_canonical_package_single(package_key: str, db_path: str) -> tuple[bool, dict[str, Any], int]:
    """Return a single canonical package with effective values and version."""
    if package_key not in BASE_PACKAGE_CATALOG:
        return False, {
            "ok": False,
            "error_code": "PACKAGE_NOT_FOUND",
            "message": f"Package '{package_key}' does not exist in canonical authority.",
        }, 404

    try:
        conn = sqlite3.connect(db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        ensure_admin_package_schema(conn)

        cur = conn.cursor()
        cur.execute("SELECT * FROM admin_package_overrides WHERE package_key = ?", (package_key,))
        row = cur.fetchone()
        ov = dict(row) if row else None
        conn.close()

        item = resolve_effective_package(package_key, ov)
        return True, {"ok": True, "package": item}, 200
    except Exception as exc:
        logger.exception("Error getting single package %s: %s", package_key, exc)
        return False, {
            "ok": False,
            "error_code": "INTERNAL_PACKAGE_ERROR",
            "message": str(exc),
        }, 500


def get_package_admin_detail(package_key: str, db_path: str | None = None) -> dict[str, Any] | None:
    """Convenience helper returning single admin package detail dictionary."""
    if not db_path:
        import sys
        import os
        bot_mod = sys.modules.get("bot")
        db_path = getattr(bot_mod, "DB_FILE", None) if bot_mod else None
        if not db_path:
            db_path = os.getenv("TOANAAS_DB_FILE") or ""
    ok, data, _ = get_canonical_package_single(package_key, db_path)
    if ok:
        return data.get("package")
    return None


def update_canonical_package(
    package_key: str,
    payload: dict[str, Any],
    actor_id: str,
    request_id: str,
    db_path: str,
) -> tuple[bool, dict[str, Any], int]:
    """Execute CAS mutation on a single package and append immutable audit event."""
    if package_key not in BASE_PACKAGE_CATALOG:
        return False, {
            "ok": False,
            "error_code": "PACKAGE_NOT_FOUND",
            "message": f"Package '{package_key}' does not exist in canonical authority.",
        }, 404

    base = BASE_PACKAGE_CATALOG[package_key]

    # 1. Validate payload structure
    if not isinstance(payload, dict):
        return False, {
            "ok": False,
            "error_code": "INVALID_PAYLOAD",
            "message": "Payload must be a JSON object.",
        }, 400

    if "expected_version" not in payload:
        return False, {
            "ok": False,
            "error_code": "EXPECTED_VERSION_MANDATORY",
            "message": "Missing mandatory field 'expected_version' for optimistic concurrency control (CAS).",
        }, 400

    try:
        expected_version = int(payload["expected_version"])
    except (ValueError, TypeError):
        return False, {
            "ok": False,
            "error_code": "INVALID_EXPECTED_VERSION",
            "message": "'expected_version' must be an integer.",
        }, 400

    changes = payload.get("changes")
    if not isinstance(changes, dict) or not changes:
        return False, {
            "ok": False,
            "error_code": "CHANGES_MANDATORY",
            "message": "'changes' dictionary must be provided and non-empty.",
        }, 400

    # 2. Reject immutable, unclassified, or non-editable fields per package type
    package_type = base.get("package_type", "")
    type_scopes = PACKAGE_TYPE_FIELD_EFFECT_SCOPES.get(package_type, {})
    allowed_editable = get_editable_fields_for_type(package_type)

    for fld in sorted(changes.keys()):
        if fld in IMMUTABLE_PACKAGE_FIELDS or type_scopes.get(fld) == EFFECT_SCOPE_IMMUTABLE:
            return False, {
                "ok": False,
                "error_code": "IMMUTABLE_FIELD_REJECTED",
                "message": f"Modification of immutable field '{fld}' is strictly forbidden for package type '{package_type}'.",
            }, 400
        if fld not in allowed_editable:
            if fld in EDITABLE_PACKAGE_FIELDS:
                return False, {
                    "ok": False,
                    "error_code": "FIELD_NOT_EDITABLE_FOR_TYPE",
                    "message": f"Field '{fld}' is not editable for package type '{package_type}'.",
                }, 400
            return False, {
                "ok": False,
                "error_code": "UNKNOWN_FIELD_REJECTED",
                "message": f"Unknown fields rejected: {[fld]}",
            }, 400

    # 3. Validate values in changes
    validated_changes: dict[str, Any] = {}
    if "display_name" in changes:
        val = str(changes["display_name"]).strip()
        if not val or len(val) > 160:
            return False, {
                "ok": False,
                "error_code": "INVALID_DISPLAY_NAME",
                "message": "'display_name' must be a non-empty string of at most 160 characters.",
            }, 400
        validated_changes["display_name"] = val

    if "description" in changes:
        val = str(changes["description"]).strip()
        if len(val) > 500:
            return False, {
                "ok": False,
                "error_code": "INVALID_DESCRIPTION",
                "message": "'description' cannot exceed 500 characters.",
            }, 400
        validated_changes["description"] = val

    if "price_vnd" in changes:
        try:
            val = int(changes["price_vnd"])
        except (ValueError, TypeError):
            return False, {
                "ok": False,
                "error_code": "INVALID_PRICE_VND",
                "message": "'price_vnd' must be an integer.",
            }, 400
        if val < 0 or val > 100_000_000:
            return False, {
                "ok": False,
                "error_code": "PRICE_VND_OUT_OF_BOUNDS",
                "message": "'price_vnd' must be between 0 and 100,000,000.",
            }, 400
        validated_changes["price_vnd"] = val

    if "public_visible" in changes:
        if not isinstance(changes["public_visible"], bool):
            return False, {
                "ok": False,
                "error_code": "INVALID_PUBLIC_VISIBLE",
                "message": "'public_visible' must be a boolean.",
            }, 400
        validated_changes["public_visible"] = bool(changes["public_visible"])

    if "commercial_enabled" in changes:
        if not isinstance(changes["commercial_enabled"], bool):
            return False, {
                "ok": False,
                "error_code": "INVALID_COMMERCIAL_ENABLED",
                "message": "'commercial_enabled' must be a boolean.",
            }, 400
        validated_changes["commercial_enabled"] = bool(changes["commercial_enabled"])

    if "sort_order" in changes:
        try:
            val = int(changes["sort_order"])
        except (ValueError, TypeError):
            return False, {
                "ok": False,
                "error_code": "INVALID_SORT_ORDER",
                "message": "'sort_order' must be an integer.",
            }, 400
        if val < 0 or val > 100_000:
            return False, {
                "ok": False,
                "error_code": "SORT_ORDER_OUT_OF_BOUNDS",
                "message": "'sort_order' must be between 0 and 100,000.",
            }, 400
        validated_changes["sort_order"] = val

    reason = str(payload.get("reason") or "").strip()
    if not reason:
        return False, {
            "ok": False,
            "error_code": "REASON_MANDATORY",
            "message": "A non-empty 'reason' is required for audit recording.",
        }, 400

    clean_actor = str(actor_id or DEFAULT_ADMIN_ID).strip()
    clean_req = str(request_id or "").strip()

    # 4. Database Transaction: Check idempotency, check CAS, commit update & audit
    try:
        conn = sqlite3.connect(db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        ensure_admin_package_schema(conn)

        cur = conn.cursor()

        # Idempotency check: same request_id previously applied to this package
        if clean_req:
            cur.execute(
                "SELECT * FROM admin_package_audit WHERE package_key = ? AND request_id = ? ORDER BY id DESC LIMIT 1",
                (package_key, clean_req),
            )
            existing_audit = cur.fetchone()
            if existing_audit:
                # Return previously committed receipt
                cur.execute("SELECT * FROM admin_package_overrides WHERE package_key = ?", (package_key,))
                cur_ov = cur.fetchone()
                fresh = resolve_effective_package(package_key, dict(cur_ov) if cur_ov else None)
                conn.close()
                return True, {
                    "ok": True,
                    "receipt_id": f"rcpt_pkg_{package_key}_{existing_audit['new_version']}_{clean_req[:8]}",
                    "package_key": package_key,
                    "previous_version": int(existing_audit["previous_version"]),
                    "new_version": int(existing_audit["new_version"]),
                    "accepted_changes": json.loads(existing_audit["new_values"]),
                    "mutation_digest": existing_audit["mutation_digest"],
                    "request_id": clean_req,
                    "actor_id": existing_audit["actor_id"],
                    "timestamp": existing_audit["timestamp"],
                    "idempotent_replay": True,
                    "package": fresh,
                }, 200

        # Read current state
        cur.execute("SELECT * FROM admin_package_overrides WHERE package_key = ?", (package_key,))
        row = cur.fetchone()
        current_version = int(row["version"]) if row else 1

        # CAS verification
        if expected_version != current_version:
            conn.close()
            return False, {
                "ok": False,
                "error_code": "VERSION_CONFLICT",
                "message": f"Stale version for package '{package_key}': expected {expected_version}, current {current_version}.",
                "current_version": current_version,
                "expected_version": expected_version,
            }, 409

        # Prepare new values
        previous_effective = resolve_effective_package(package_key, dict(row) if row else None)
        new_version = current_version + 1
        now_ts = utc_now_text()

        # Merge validated changes onto current effective state
        merged_display_name = validated_changes.get("display_name", previous_effective["display_name"])
        merged_description = validated_changes.get("description", previous_effective["description"])
        merged_price_vnd = validated_changes.get("price_vnd", previous_effective["price_vnd"])
        merged_public_visible = validated_changes.get("public_visible", previous_effective["public_visible"])
        merged_commercial_enabled = validated_changes.get("commercial_enabled", previous_effective["commercial_enabled"])
        merged_sort_order = validated_changes.get("sort_order", previous_effective["sort_order"])

        # Compute mutation digest
        mutation_digest = compute_package_mutation_digest(
            package_key=package_key,
            new_version=new_version,
            accepted_changes=validated_changes,
            request_id=clean_req,
            actor_id=clean_actor,
        )

        previous_values_json = json.dumps({k: previous_effective.get(k) for k in validated_changes}, sort_keys=True)
        new_values_json = json.dumps(validated_changes, sort_keys=True)

        # Upsert override
        cur.execute(
            """INSERT INTO admin_package_overrides (
                package_key, display_name, description, price_vnd,
                public_visible, commercial_enabled, sort_order,
                version, updated_at, updated_by, update_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(package_key) DO UPDATE SET
                display_name = excluded.display_name,
                description = excluded.description,
                price_vnd = excluded.price_vnd,
                public_visible = excluded.public_visible,
                commercial_enabled = excluded.commercial_enabled,
                sort_order = excluded.sort_order,
                version = excluded.version,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by,
                update_reason = excluded.update_reason
            """,
            (
                package_key,
                merged_display_name,
                merged_description,
                merged_price_vnd,
                1 if merged_public_visible else 0,
                1 if merged_commercial_enabled else 0,
                merged_sort_order,
                new_version,
                now_ts,
                clean_actor,
                reason,
            ),
        )

        # Append audit
        cur.execute(
            """INSERT INTO admin_package_audit (
                package_key, actor_id, request_id, reason,
                previous_version, new_version, previous_values, new_values,
                mutation_digest, timestamp, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                package_key,
                clean_actor,
                clean_req,
                reason,
                current_version,
                new_version,
                previous_values_json,
                new_values_json,
                mutation_digest,
                now_ts,
                now_ts,
            ),
        )
        conn.commit()

        # 5. Immediate fresh canonical readback
        cur.execute("SELECT * FROM admin_package_overrides WHERE package_key = ?", (package_key,))
        fresh_row = cur.fetchone()
        conn.close()

        if not fresh_row or int(fresh_row["version"]) != new_version:
            return False, {
                "ok": False,
                "error_code": "READBACK_VERSION_MISMATCH",
                "message": "Fresh readback failed: durable version does not match committed new_version.",
            }, 500

        fresh_package = resolve_effective_package(package_key, dict(fresh_row))

        # Verify all accepted values match stored values
        for k, v in validated_changes.items():
            if fresh_package.get(k) != v:
                return False, {
                    "ok": False,
                    "error_code": "READBACK_VALUE_MISMATCH",
                    "message": f"Fresh readback value mismatch for field '{k}': expected {v}, got {fresh_package.get(k)}",
                }, 500

        # 6. Propagate to in-memory runtime consumers
        apply_package_override_to_runtime(package_key, validated_changes)

        receipt_id = f"rcpt_pkg_{package_key}_{new_version}_{clean_req[:8] if clean_req else 'direct'}"
        return True, {
            "ok": True,
            "receipt_id": receipt_id,
            "package_key": package_key,
            "previous_version": current_version,
            "new_version": new_version,
            "accepted_changes": validated_changes,
            "mutation_digest": mutation_digest,
            "request_id": clean_req,
            "actor_id": clean_actor,
            "timestamp": now_ts,
            "idempotent_replay": False,
            "package": fresh_package,
        }, 200

    except Exception as exc:
        logger.exception("Error updating canonical package %s: %s", package_key, exc)
        return False, {
            "ok": False,
            "error_code": "INTERNAL_PACKAGE_MUTATION_ERROR",
            "message": str(exc),
        }, 500


# ─── RUNTIME PROPAGATION HOOKS ───────────────────────────────────────────────

def apply_package_override_to_runtime(package_key: str, changes: dict[str, Any]) -> None:
    """Propagate changes to active in-memory runtime catalogs in bot."""
    existing = _RUNTIME_PACKAGE_OVERRIDES.get(package_key)
    if existing is None:
        _RUNTIME_PACKAGE_OVERRIDES[package_key] = dict(changes)
    else:
        existing.update(changes)

    import sys
    bot_mod = sys.modules.get("bot")
    if not bot_mod:
        return

    # 1. If subscription plan, update bot.PLAN_CATALOG
    plan_cat = getattr(bot_mod, "PLAN_CATALOG", None)
    if isinstance(plan_cat, dict) and package_key in plan_cat:
        if "display_name" in changes:
            plan_cat[package_key]["name"] = changes["display_name"]
        if "description" in changes:
            plan_cat[package_key]["description"] = changes["description"]
        if "price_vnd" in changes:
            plan_cat[package_key]["price_vnd"] = changes["price_vnd"]
        if "commercial_enabled" in changes:
            plan_cat[package_key]["commercial_enabled"] = changes["commercial_enabled"]
        if "public_visible" in changes:
            plan_cat[package_key]["public_visible"] = changes["public_visible"]


def apply_active_package_overrides(db_path: str) -> None:
    """Load all durable package overrides from SQLite and apply to runtime."""
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        ensure_admin_package_schema(conn)
        cur = conn.cursor()
        cur.execute("SELECT * FROM admin_package_overrides")
        rows = cur.fetchall()
        conn.close()

        for row in rows:
            pkg_key = row["package_key"]
            changes: dict[str, Any] = {}
            if row["display_name"] is not None:
                changes["display_name"] = str(row["display_name"])
            if row["description"] is not None:
                changes["description"] = str(row["description"])
            if row["price_vnd"] is not None:
                changes["price_vnd"] = int(row["price_vnd"])
            if row["public_visible"] is not None:
                changes["public_visible"] = bool(row["public_visible"])
            if row["commercial_enabled"] is not None:
                changes["commercial_enabled"] = bool(row["commercial_enabled"])
            if row["sort_order"] is not None:
                changes["sort_order"] = int(row["sort_order"])
            apply_package_override_to_runtime(pkg_key, changes)
    except Exception as exc:
        logger.warning("Could not apply active package overrides: %s", exc)


apply_active_package_overrides_to_runtime = apply_active_package_overrides



def get_runtime_package_override(package_key: str, db_path: str | None = None) -> dict[str, Any] | None:
    """Return runtime package override if active."""
    if package_key in _RUNTIME_PACKAGE_OVERRIDES:
        return _RUNTIME_PACKAGE_OVERRIDES[package_key]

    resolved_db = db_path
    if not resolved_db:
        import sys
        import os
        bot_mod = sys.modules.get("bot")
        if bot_mod:
            resolved_db = getattr(bot_mod, "DB_FILE", None)
        if not resolved_db:
            resolved_db = os.getenv("TOANAAS_DB_FILE")

    if resolved_db:
        try:
            conn = sqlite3.connect(resolved_db, timeout=5.0)
            conn.row_factory = sqlite3.Row
            ensure_admin_package_schema(conn)
            cur = conn.cursor()
            cur.execute("SELECT * FROM admin_package_overrides WHERE package_key = ?", (package_key,))
            row = cur.fetchone()
            conn.close()
            if row:
                changes: dict[str, Any] = {}
                if row["display_name"] is not None:
                    changes["display_name"] = str(row["display_name"])
                if row["description"] is not None:
                    changes["description"] = str(row["description"])
                if row["price_vnd"] is not None:
                    changes["price_vnd"] = int(row["price_vnd"])
                if row["public_visible"] is not None:
                    changes["public_visible"] = bool(row["public_visible"])
                if row["commercial_enabled"] is not None:
                    changes["commercial_enabled"] = bool(row["commercial_enabled"])
                if row["sort_order"] is not None:
                    changes["sort_order"] = int(row["sort_order"])
                _RUNTIME_PACKAGE_OVERRIDES[package_key] = changes
                return changes
            else:
                _RUNTIME_PACKAGE_OVERRIDES[package_key] = None
                return None
        except Exception:
            pass

    return None


def clear_runtime_package_cache() -> None:
    """Clear runtime package overrides cache and restore runtime state from immutable runtime base truth.
    RESET_USES_RUNTIME_BASE_TRUTH=YES.
    """
    _RUNTIME_PACKAGE_OVERRIDES.clear()
    CanonicalBasePackagesCatalog.invalidate_cache()

    import sys
    bot_mod = sys.modules.get("bot")
    if bot_mod and hasattr(bot_mod, "BASE_PLAN_CATALOG") and hasattr(bot_mod, "PLAN_CATALOG"):
        from copy import deepcopy
        bot_mod.PLAN_CATALOG.clear()
        bot_mod.PLAN_CATALOG.update(deepcopy(bot_mod.BASE_PLAN_CATALOG))


def compare_all_packages_against_runtime() -> dict[str, Any]:
    """Dynamically verify every package in canonical authority against runtime base resolvers.
    Returns:
    - BASE_PACKAGE_KEY_GAPS: list[str] (0 gaps required)
    - BASE_DISPLAY_NAME_GAPS: list[tuple] (0 gaps required)
    - BASE_PRICE_GAPS: list[tuple] (0 gaps required)
    - BASE_DURATION_GAPS: list[tuple] (0 gaps required)
    - BASE_BENEFIT_GAPS: list[tuple] (0 gaps required)
    - PACKAGE_PRICE_DUAL_AUTHORITY_COUNT: int (0 required)
    - CANONICAL_BASE_SOURCE_COUNT_PER_PACKAGE: int (1 required)
    - ADMIN_ONLY_PACKAGE_KEYS: list[str] (0 required)
    - RUNTIME_PACKAGE_MISSING_FROM_ADMIN: list[str] (0 required)
    - TOPUP_PACKAGE_KEYS_IN_B03: list[str] (0 required)
    """
    import sys
    bot_mod = sys.modules.get("bot")
    if not bot_mod:
        import bot as bot_mod

    subs = getattr(bot_mod, "BASE_PLAN_CATALOG", {}) or {}
    combo_res = getattr(bot_mod, "p0_21d_combo_catalog_base", None)
    combos = combo_res(include_legacy=True) if callable(combo_res) else {}
    monthly_res = getattr(bot_mod, "p0_21d_task_package_base", None)
    monthlies = monthly_res() if callable(monthly_res) else {}

    runtime_keys = set(subs.keys()) | set(combos.keys()) | set(monthlies.keys())
    admin_keys = set(BASE_PACKAGE_CATALOG.keys())

    key_gaps = sorted(list(runtime_keys ^ admin_keys))
    admin_only = sorted(list(admin_keys - runtime_keys))
    runtime_missing = sorted(list(runtime_keys - admin_keys))
    topup_in_b03 = [k for k in admin_keys if "topup" in k.lower()]

    display_gaps = []
    price_gaps = []
    duration_gaps = []
    benefit_gaps = []

    for k in admin_keys:
        pkg = BASE_PACKAGE_CATALOG[k]
        ptype = pkg["package_type"]
        if ptype == "subscription":
            r = subs[k]
            expected_name = r.get("name", k)
            expected_price = int(r.get("price_vnd", 0))
            expected_duration = int(r.get("duration_days", 30))
            expected_benefits = {"xu": int(r.get("plan_xu", 0))}
        elif ptype == "combo":
            r = combos[k]
            expected_name = r.get("label", k)
            expected_price = int(r.get("price_vnd", 0))
            expected_duration = int(r.get("default_days") or 30)
            expected_benefits = r.get("items", {})
        else:
            r = monthlies[k]
            expected_name = r.get("label", k)
            expected_price = int(r.get("price_vnd", 0))
            expected_duration = int(r.get("default_days") or 30)
            expected_benefits = r.get("items", {})

        if pkg["display_name"] != expected_name:
            display_gaps.append((k, pkg["display_name"], expected_name))
        if pkg["price_vnd"] != expected_price:
            price_gaps.append((k, pkg["price_vnd"], expected_price))
        if pkg["duration_days"] != expected_duration:
            duration_gaps.append((k, pkg["duration_days"], expected_duration))
        if pkg["benefits"] != expected_benefits:
            benefit_gaps.append((k, pkg["benefits"], expected_benefits))

    # Dynamically derive PACKAGE_PRICE_DUAL_AUTHORITY_COUNT:
    # Check if metadata JSON contains price_vnd, and check if multiple runtime authorities define price_vnd
    metadata_cat = _load_base_packages_metadata()
    price_dual_count = sum(1 for k, meta in metadata_cat.items() if "price_vnd" in meta)
    for k in admin_keys:
        runtime_price_defs = (
            (1 if (k in subs and "price_vnd" in subs[k]) else 0)
            + (1 if (k in combos and "price_vnd" in combos[k]) else 0)
            + (1 if (k in monthlies and "price_vnd" in monthlies[k]) else 0)
        )
        if runtime_price_defs > 1:
            price_dual_count += 1
    package_price_dual_authority_count = price_dual_count

    # Dynamically derive CANONICAL_BASE_SOURCE_COUNT_PER_PACKAGE:
    # Must be exactly 1 source authority per package
    source_counts = {
        k: (1 if k in subs else 0) + (1 if k in combos else 0) + (1 if k in monthlies else 0)
        for k in admin_keys
    }
    canonical_base_source_count_per_package = (
        1 if (source_counts and all(c == 1 for c in source_counts.values())) else 0
    )

    return {
        "BASE_PACKAGE_KEY_GAPS": key_gaps,
        "BASE_DISPLAY_NAME_GAPS": display_gaps,
        "BASE_PRICE_GAPS": price_gaps,
        "BASE_DURATION_GAPS": duration_gaps,
        "BASE_BENEFIT_GAPS": benefit_gaps,
        "PACKAGE_PRICE_DUAL_AUTHORITY_COUNT": package_price_dual_authority_count,
        "CANONICAL_BASE_SOURCE_COUNT_PER_PACKAGE": canonical_base_source_count_per_package,
        "ADMIN_ONLY_PACKAGE_KEYS": admin_only,
        "RUNTIME_PACKAGE_MISSING_FROM_ADMIN": runtime_missing,
        "TOPUP_PACKAGE_KEYS_IN_B03": topup_in_b03,
    }


def generate_package_propagation_matrix() -> list[dict[str, Any]]:
    """Build dynamic matrix specification for every editable field/package combination.
    Guarantees:
    - EDITABLE_FIELD_WITHOUT_MATRIX_ROW = 0
    - EDITABLE_BUT_RUNTIME_UNWIRED = 0
    Returns ONLY structural specification (PACKAGE_KEY, PACKAGE_TYPE, FIELD, EFFECT_SCOPE).
    Execution and empirical proof evaluation belong exclusively to the test harness.
    """
    matrix: list[dict[str, Any]] = []
    for pkg_key in sorted(BASE_PACKAGE_CATALOG.keys()):
        base = BASE_PACKAGE_CATALOG[pkg_key]
        ptype = base.get("package_type", "")
        editable_fields = sorted(list(get_editable_fields_for_type(ptype)))
        scopes = PACKAGE_TYPE_FIELD_EFFECT_SCOPES.get(ptype, {})
        for field in editable_fields:
            scope = scopes.get(field, EFFECT_SCOPE_IMMUTABLE)
            matrix.append({
                "PACKAGE_KEY": pkg_key,
                "PACKAGE_TYPE": ptype,
                "FIELD": field,
                "EFFECT_SCOPE": scope,
            })
    return matrix
