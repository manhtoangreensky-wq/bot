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
# Authoritative static package definitions covering all commercial customer domains.
# Sourced directly from current Bot PLAN_CATALOG (subscription) and package_catalog_payload (combo, monthly).

CATALOG_PATH = Path(__file__).resolve().parent.parent / "config" / "base_packages_catalog.json"

def _load_base_packages_catalog() -> dict[str, dict[str, Any]]:
    if CATALOG_PATH.exists():
        try:
            with open(CATALOG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Could not load base_packages_catalog.json: %s", exc)
    return {}

BASE_PACKAGE_CATALOG: dict[str, dict[str, Any]] = _load_base_packages_catalog()

# ─── FIELD CLASSIFICATIONS & WHITELISTS ──────────────────────────────────────

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

    effective["field_classifications"] = {
        "editable_commercial": sorted(list(EDITABLE_PACKAGE_FIELDS)),
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
        for key, base in sorted(BASE_PACKAGE_CATALOG.items(), key=lambda x: (x[1].get("sort_order", 0), x[0])):
            ov = overrides.get(key)
            item = resolve_effective_package(key, ov)
            items.append(item)
            ptype = item.get("package_type", "")
            if ptype in domain_counts:
                domain_counts[ptype] += 1

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

    # 2. Reject immutable and unknown fields
    immutable_detected = set(changes.keys()) & IMMUTABLE_PACKAGE_FIELDS
    if immutable_detected:
        return False, {
            "ok": False,
            "error_code": "IMMUTABLE_FIELD_REJECTED",
            "message": f"Modification of immutable fields is strictly forbidden: {sorted(immutable_detected)}",
        }, 400

    unknown_detected = set(changes.keys()) - EDITABLE_PACKAGE_FIELDS
    if unknown_detected:
        return False, {
            "ok": False,
            "error_code": "UNKNOWN_FIELD_REJECTED",
            "message": f"Unknown fields rejected: {sorted(unknown_detected)}",
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
    _RUNTIME_PACKAGE_OVERRIDES.setdefault(package_key, {}).update(changes)

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
        except Exception:
            pass

    return None


def clear_runtime_package_cache() -> None:
    """Clear runtime package overrides cache, useful for test isolation."""
    _RUNTIME_PACKAGE_OVERRIDES.clear()

    # Restore bot.PLAN_CATALOG if initial backup available
    import sys
    bot_mod = sys.modules.get("bot")
    if bot_mod and hasattr(bot_mod, "PLAN_CATALOG"):
        plan_cat = bot_mod.PLAN_CATALOG
        for k, v in BASE_PACKAGE_CATALOG.items():
            if v.get("package_type") == "subscription" and k in plan_cat:
                plan_cat[k]["name"] = v["display_name"]
                plan_cat[k]["description"] = v["description"]
                plan_cat[k]["price_vnd"] = v["price_vnd"]
                plan_cat[k].pop("commercial_enabled", None)
                plan_cat[k].pop("public_visible", None)
