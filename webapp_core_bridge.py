"""Private COPYFAST bridge mounted by ``bot.py``.

The bridge is deliberately a small adapter around existing bot state.  It
never owns a wallet, payment webhook, or provider credential.  Browser traffic
must go through the standalone Web App; this router only accepts an HMAC signed
server-to-server request from that application.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
from collections import defaultdict, deque
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from typing import Any, Callable

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute


PUBLIC_GUARD = "Hệ thống đang bảo trì/nâng cấp. TOAN AAS chưa xử lý và chưa trừ Xu. Vui lòng thử lại sau."
BRIDGE_TABLE_IDEMPOTENCY = "webapp_core_bridge_idempotency"
BRIDGE_TABLE_AUDIT = "webapp_core_bridge_audit"
BRIDGE_TABLE_UPLOADS = "webapp_core_bridge_uploads"
_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")
_JOB_ID_PATTERN = re.compile(r"^([a-z_]+):(\d+)$")
_WEB_LINK_CODE_PATTERN = re.compile(r"^[A-Za-z0-9]{8,128}$")
_UPLOAD_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm",
    ".mp3", ".wav", ".m4a", ".ogg", ".pdf", ".txt", ".srt", ".vtt",
    ".docx",
})
_UPLOAD_MIME_TYPES = frozenset({
    "image/jpeg", "image/png", "image/webp", "video/mp4", "video/quicktime", "video/webm",
    "audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/ogg", "application/ogg",
    "application/pdf", "text/plain", "text/vtt", "application/x-subrip", "application/octet-stream",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
})
_rate_windows: dict[str, deque[float]] = defaultdict(deque)
_request_nonces: dict[str, float] = {}

_FEATURE_TEXT_KEYS = (
    "request", "prompt", "brief", "script", "text", "topic", "description",
    "instructions", "notes",
)


class BridgeRoute(APIRoute):
    """Keep every private bridge response in the public envelope contract."""

    def get_route_handler(self):  # type: ignore[override]
        handler = super().get_route_handler()

        async def guarded_handler(request: Request):
            try:
                return await handler(request)
            except HTTPException as exc:
                status_code = int(exc.status_code)
                code = {
                    401: "CORE_BRIDGE_UNAUTHORIZED",
                    403: "CORE_BRIDGE_FORBIDDEN",
                    404: "CORE_BRIDGE_NOT_FOUND",
                    409: "CORE_BRIDGE_REPLAYED_REQUEST",
                    422: "CORE_BRIDGE_INVALID_REQUEST",
                    429: "CORE_BRIDGE_RATE_LIMITED",
                    503: "CORE_BRIDGE_NOT_CONFIGURED",
                }.get(status_code, "CORE_BRIDGE_REQUEST_FAILED")
                message = _safe_text(exc.detail, 300) if status_code < 500 else PUBLIC_GUARD
                return JSONResponse(response(False, "failed", message, error_code=code), status_code=status_code)
            except Exception:
                return JSONResponse(response(False, "failed", PUBLIC_GUARD, error_code="CORE_BRIDGE_INTERNAL_ERROR"), status_code=500)

        return guarded_handler


def response(ok: bool, status_name: str, message: str, *, data: dict | None = None, error_code: str | None = None) -> dict:
    return {
        "ok": bool(ok),
        "status": status_name,
        "message": str(message or "")[:500],
        "data": data or {},
        "error_code": error_code,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _bool_env(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default).lower()).strip().lower() in {"1", "true", "yes", "on"}


def _upload_max_bytes() -> int:
    """Bound Web staging uploads without reading any provider configuration."""
    raw_bytes = os.environ.get("WEBAPP_UPLOAD_MAX_BYTES", "").strip()
    raw_mb = os.environ.get("WEBAPP_UPLOAD_MAX_MB", "12").strip()
    try:
        requested = int(raw_bytes) if raw_bytes else int(raw_mb) * 1024 * 1024
    except ValueError:
        requested = 12 * 1024 * 1024
    return max(1 * 1024 * 1024, min(requested, 50 * 1024 * 1024))


def _safe_text(value: Any, limit: int = 300) -> str:
    return str(value or "").replace("\n", " ").replace("\r", " ")[:limit]


def _validated_upload_name(value: Any) -> tuple[str, str]:
    name = str(value or "").strip()
    if not name or len(name) > 180 or "\x00" in name or "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(status_code=422, detail="invalid upload filename")
    extension = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in _UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=415, detail="unsupported upload file type")
    return name, extension


def _feature_input_text(input_data: dict) -> str:
    """Extract the user's principal text without guessing a provider schema."""
    for key in _FEATURE_TEXT_KEYS:
        value = input_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:4000]
    return ""


def _validate_upload_content(name: str, extension: str, content_type: Any, content: bytes) -> str:
    media_type = str(content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    if media_type not in _UPLOAD_MIME_TYPES:
        raise HTTPException(status_code=415, detail="unsupported upload media type")
    if not content:
        raise HTTPException(status_code=422, detail="empty upload")
    if len(content) > _upload_max_bytes():
        raise HTTPException(status_code=413, detail="upload exceeds configured limit")
    # Lightweight signatures prevent a browser from relabelling an executable
    # as the most common binary media/doc types. Other safe text/container
    # formats are validated by their extension and canonical size/MIME gate.
    if extension == ".pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=422, detail="invalid PDF upload")
    if extension == ".png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=422, detail="invalid PNG upload")
    if extension in {".jpg", ".jpeg"} and not content.startswith(b"\xff\xd8\xff"):
        raise HTTPException(status_code=422, detail="invalid JPEG upload")
    if extension == ".webp" and not (len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"):
        raise HTTPException(status_code=422, detail="invalid WEBP upload")
    if extension == ".wav" and not (len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WAVE"):
        raise HTTPException(status_code=422, detail="invalid WAV upload")
    return media_type


def _upload_metadata_from_row(row: Any) -> dict:
    return {
        "id": str(row[0]),
        "file_name": _safe_text(row[1], 180),
        "content_type": _safe_text(row[2], 120),
        "content_size": int(row[3] or 0),
        "sha256": _safe_text(row[4], 80),
        "created_at": _safe_text(row[5], 80),
    }


def _web_link_callback_headers(callback_url: str, callback_token: str, callback_secret: str, body: bytes, *, request_id: str | None = None, timestamp: str | None = None) -> dict[str, str]:
    """Sign the bot-to-Web link callback with its own directional secret."""
    request_id = request_id or str(uuid.uuid4())
    timestamp = timestamp or str(int(time.time()))
    callback_path = str(httpx.URL(callback_url).path or "/")
    digest = hashlib.sha256(body).hexdigest()
    material = f"{timestamp}.{request_id}.POST.{callback_path}.{digest}".encode("utf-8")
    signature = hmac.new(callback_secret.encode("utf-8"), material, hashlib.sha256).hexdigest()
    return {
        "X-TOAN-AAS-BRIDGE-TOKEN": callback_token,
        "X-TOAN-AAS-Timestamp": timestamp,
        "X-TOAN-AAS-Request-ID": request_id,
        "X-TOAN-AAS-Signature": signature,
        "Content-Type": "application/json",
    }


def _sanitize_data(value: Any) -> Any:
    """Remove credentials, tracebacks, raw provider ids and local paths."""
    forbidden = {
        "token", "secret", "api_key", "authorization", "headers", "traceback", "stack",
        "raw_response", "provider_task_id", "task_id", "output_path", "file_path", "filesystem_path",
        "provider_message", "debug", "detail",
    }
    if isinstance(value, dict):
        return {str(key): _sanitize_data(item) for key, item in value.items() if str(key).lower() not in forbidden}
    if isinstance(value, list):
        return [_sanitize_data(item) for item in value[:100]]
    if isinstance(value, (bytes, bytearray)):
        return {"bytes": len(value)}
    if isinstance(value, str):
        return value[:500]
    return value


class BotCoreBridge:
    """A thin, dependency-injected view of globals defined by bot.py."""

    def __init__(self, core: dict[str, Any]):
        self.core = core

    def fn(self, name: str) -> Callable | None:
        candidate = self.core.get(name)
        return candidate if callable(candidate) else None

    def db(self):
        connector = self.fn("db_connect")
        if not connector:
            raise RuntimeError("canonical database adapter unavailable")
        return connector()

    def table_exists(self, conn, table: str) -> bool:
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return bool(row)

    def columns(self, conn, table: str) -> set[str]:
        if not self.table_exists(conn, table):
            return set()
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def ensure_bridge_tables(self) -> None:
        conn = self.db()
        try:
            conn.execute(
                f"""CREATE TABLE IF NOT EXISTS {BRIDGE_TABLE_IDEMPOTENCY} (
                    scope TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(scope, idempotency_key)
                )"""
            )
            conn.execute(
                f"""CREATE TABLE IF NOT EXISTS {BRIDGE_TABLE_AUDIT} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT DEFAULT '',
                    outcome TEXT NOT NULL,
                    note TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )"""
            )
            conn.execute(
                f"""CREATE TABLE IF NOT EXISTS {BRIDGE_TABLE_UPLOADS} (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    content_size INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    content BLOB NOT NULL,
                    idempotency_key TEXT,
                    created_at TEXT NOT NULL
                )"""
            )
            upload_columns = self.columns(conn, BRIDGE_TABLE_UPLOADS)
            if "idempotency_key" not in upload_columns:
                conn.execute(f"ALTER TABLE {BRIDGE_TABLE_UPLOADS} ADD COLUMN idempotency_key TEXT")
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{BRIDGE_TABLE_UPLOADS}_user_created ON {BRIDGE_TABLE_UPLOADS}(user_id, created_at DESC)"
            )
            conn.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{BRIDGE_TABLE_UPLOADS}_user_idempotency ON {BRIDGE_TABLE_UPLOADS}(user_id, idempotency_key) WHERE idempotency_key IS NOT NULL"
            )
            conn.commit()
        finally:
            conn.close()

    def audit(self, actor_id: str, action: str, request_id: str, *, target: str = "", outcome: str = "ok", note: str = "") -> None:
        self.ensure_bridge_tables()
        conn = self.db()
        try:
            conn.execute(
                f"INSERT INTO {BRIDGE_TABLE_AUDIT} (request_id, actor_id, action, target, outcome, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (request_id, str(actor_id), action, target[:160], outcome[:40], _safe_text(note, 300), _now()),
            )
            conn.commit()
        finally:
            conn.close()

    def idempotency_get(self, scope: str, key: str) -> dict | None:
        self.ensure_bridge_tables()
        conn = self.db()
        try:
            row = conn.execute(f"SELECT response_json FROM {BRIDGE_TABLE_IDEMPOTENCY} WHERE scope=? AND idempotency_key=?", (scope, key)).fetchone()
            return json.loads(row[0]) if row else None
        except (ValueError, TypeError):
            return None
        finally:
            conn.close()

    def idempotency_put(self, scope: str, key: str, value: dict) -> None:
        self.ensure_bridge_tables()
        conn = self.db()
        try:
            conn.execute(
                f"INSERT OR IGNORE INTO {BRIDGE_TABLE_IDEMPOTENCY} (scope, idempotency_key, response_json, created_at) VALUES (?, ?, ?, ?)",
                (scope, key, json.dumps(value, ensure_ascii=False, separators=(",", ":")), _now()),
            )
            conn.commit()
        finally:
            conn.close()

    def create_upload(self, user_id: str, payload: dict) -> dict:
        """Store a validated Web upload in bot-owned staging, never in Web DB."""
        if self.identity(user_id) is None:
            return response(False, "failed", "Không tìm thấy tài khoản Telegram canonical.", error_code="USER_NOT_FOUND")
        key = _validate_idempotency(payload.get("idempotency_key"))
        scope = f"upload:{user_id}"
        if existing := self.idempotency_get(scope, key):
            return existing
        name, extension = _validated_upload_name(payload.get("file_name"))
        encoded = str(payload.get("content_base64") or "")
        max_encoded = ((_upload_max_bytes() + 2) // 3) * 4 + 8
        if not encoded or len(encoded) > max_encoded:
            raise HTTPException(status_code=413, detail="upload exceeds configured limit")
        try:
            content = base64.b64decode(encoded.encode("ascii"), validate=True)
        except (UnicodeEncodeError, ValueError, binascii.Error):
            raise HTTPException(status_code=422, detail="invalid upload encoding")
        media_type = _validate_upload_content(name, extension, payload.get("content_type"), content)
        actual_hash = hashlib.sha256(content).hexdigest()
        supplied_hash = str(payload.get("sha256") or "").strip().lower()
        if supplied_hash and not hmac.compare_digest(supplied_hash, actual_hash):
            raise HTTPException(status_code=422, detail="upload checksum mismatch")
        upload_id = str(uuid.uuid4())
        created_at = _now()
        self.ensure_bridge_tables()
        conn = self.db()
        try:
            conn.execute(
                f"""INSERT INTO {BRIDGE_TABLE_UPLOADS}
                (id, user_id, file_name, content_type, content_size, sha256, content, idempotency_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (upload_id, str(user_id), name, media_type, len(content), actual_hash, content, key, created_at),
            )
            conn.commit()
            metadata = {
                "id": upload_id,
                "file_name": name,
                "content_type": media_type,
                "content_size": len(content),
                "sha256": actual_hash,
                "created_at": created_at,
            }
        except Exception as exc:
            # The unique user/idempotency index is the concurrency boundary
            # for duplicate browser retries.  Return the first canonical row;
            # do not create a second blob or silently credit anything.
            if "UNIQUE constraint failed" not in str(exc):
                raise
            row = conn.execute(
                f"SELECT id, file_name, content_type, content_size, sha256, created_at FROM {BRIDGE_TABLE_UPLOADS} WHERE user_id=? AND idempotency_key=?",
                (str(user_id), key),
            ).fetchone()
            if not row:
                raise
            metadata = _upload_metadata_from_row(row)
        finally:
            conn.close()
        result = response(True, "completed", "Tệp đã được lưu tại staging canonical của bot.", data={
            **metadata,
        })
        self.idempotency_put(scope, key, result)
        return result

    def uploads_for_ids(self, user_id: str, values: Any) -> tuple[list[dict], list[str]]:
        """Return only metadata for staging files owned by the requesting user."""
        if values in (None, "", []):
            return [], []
        if not isinstance(values, (str, list, tuple)):
            return [], ["invalid"]
        raw_values = [values] if isinstance(values, str) else list(values)
        ids: list[str] = []
        for item in raw_values:
            candidate = str(item.get("id") if isinstance(item, dict) else item or "").strip()
            if not _ID_PATTERN.fullmatch(candidate):
                return [], [candidate or "invalid"]
            if candidate not in ids:
                ids.append(candidate)
        if len(ids) > 8:
            return [], ["too_many_uploads"]
        self.ensure_bridge_tables()
        conn = self.db()
        try:
            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"SELECT id, file_name, content_type, content_size, sha256, created_at FROM {BRIDGE_TABLE_UPLOADS} WHERE user_id=? AND id IN ({placeholders})",
                (str(user_id), *ids),
            ).fetchall()
            by_id = {str(row[0]): _upload_metadata_from_row(row) for row in rows}
            missing = [item for item in ids if item not in by_id]
            return [by_id[item] for item in ids if item in by_id], missing
        finally:
            conn.close()

    def is_admin(self, user_id: str) -> bool:
        checker = self.fn("is_admin_user")
        try:
            return bool(checker(user_id)) if checker else False
        except Exception:
            return False

    def identity(self, user_id: str) -> dict | None:
        conn = self.db()
        try:
            columns = self.columns(conn, "users")
            if "user_id" not in columns:
                return None
            names = [name for name in ("user_id", "username", "credits", "total_spent", "is_vip", "join_date") if name in columns]
            row = conn.execute(f"SELECT {','.join(names)} FROM users WHERE user_id=?", (str(user_id),)).fetchone()
            if not row:
                return None
            value = dict(zip(names, row))
            return {
                "user_id": str(value.get("user_id") or user_id),
                "username": _safe_text(value.get("username") or "", 120),
                "role": "admin" if self.is_admin(user_id) else "user",
                "is_vip": bool(value.get("is_vip")),
                "created_at": _safe_text(value.get("join_date") or "", 80),
            }
        finally:
            conn.close()

    def wallet(self, user_id: str) -> dict | None:
        identity = self.identity(user_id)
        if not identity:
            return None
        conn = self.db()
        try:
            columns = self.columns(conn, "users")
            fields = [name for name in ("credits", "total_spent", "is_vip") if name in columns]
            row = conn.execute(f"SELECT {','.join(fields)} FROM users WHERE user_id=?", (str(user_id),)).fetchone() if fields else None
            values = dict(zip(fields, row or ()))
            plan = {}
            if self.table_exists(conn, "user_plans"):
                plan_columns = self.columns(conn, "user_plans")
                selected = [name for name in ("current_plan", "plan_name", "plan_status", "plan_expires_at", "plan_xu_remaining") if name in plan_columns]
                plan_row = conn.execute(f"SELECT {','.join(selected)} FROM user_plans WHERE user_id=?", (str(user_id),)).fetchone() if selected else None
                plan = dict(zip(selected, plan_row)) if plan_row else {}
            return {
                "user": identity,
                "balance_xu": int(values.get("credits") or 0),
                "total_spent_xu": int(values.get("total_spent") or 0),
                "is_vip": bool(values.get("is_vip")),
                "plan": _sanitize_data(plan),
                "source": "canonical_bot",
            }
        finally:
            conn.close()

    def pricing_catalog(self) -> dict:
        """Expose a redacted, read-only view of bot pricing helpers."""
        payload_fn = self.fn("media_workflow_pricing_payload")
        if not payload_fn:
            return {"available": False, "groups": []}
        try:
            raw = dict(payload_fn() or {})
        except Exception:
            return {"available": False, "groups": []}

        def tiers(kind: str) -> list[dict]:
            values = raw.get(kind) if isinstance(raw.get(kind), dict) else {}
            return [
                {
                    "code": _safe_text(code, 80),
                    "label": _safe_text(item.get("label"), 160),
                    "cost_xu": max(0, int(item.get("cost") or 0)),
                    "note": _safe_text(item.get("note"), 300),
                    "retry_warranty_count": max(0, int(item.get("retry_warranty_count") or 0)),
                }
                for code, item in values.items() if isinstance(item, dict)
            ]

        combos = []
        for item in raw.get("video_combos") or []:
            if not isinstance(item, dict):
                continue
            combos.append({
                "code": _safe_text(item.get("code"), 80),
                "label": _safe_text(item.get("label"), 160),
                "price_vnd": max(0, int(item.get("price_vnd") or 0)),
                "display_price": _safe_text(item.get("display_price"), 40),
                "summary": _safe_text(item.get("summary"), 300),
            })
        return {
            "available": True,
            "billing_mode": _safe_text(raw.get("billing_mode"), 80),
            "price_table_source": _safe_text(raw.get("price_table_source"), 120),
            "image_tiers": tiers("image_tiers"),
            "video_tiers": tiers("video_tiers"),
            "video_combos": combos,
            "trend_workflow_content_total_cost_xu": max(0, int(raw.get("workflow_content_total_cost") or 0)),
        }

    def packages_catalog(self) -> dict:
        """Read bot package definitions without exposing a payment writer."""
        catalog_fn = self.fn("package_catalog_payload")
        price_fn = self.fn("package_purchase_price_vnd")
        if not catalog_fn:
            return {"available": False, "combos": [], "monthly": []}
        try:
            raw = dict(catalog_fn() or {})
        except Exception:
            return {"available": False, "combos": [], "monthly": []}

        def entries(group: str) -> list[dict]:
            values = raw.get(group) if isinstance(raw.get(group), dict) else {}
            package_type = "monthly" if group == "monthly" else "combo"
            result = []
            for code, item in values.items():
                if not isinstance(item, dict):
                    continue
                try:
                    price = max(0, int(price_fn(package_type, code) or 0)) if price_fn else 0
                except Exception:
                    price = 0
                safe_items = {
                    _safe_text(key, 80): max(0, int(value or 0))
                    for key, value in (item.get("items") or {}).items()
                }
                result.append({
                    "code": _safe_text(code, 80),
                    "type": package_type,
                    "label": _safe_text(item.get("label"), 180),
                    "note": _safe_text(item.get("note"), 300),
                    "items": safe_items,
                    "default_days": max(0, int(item.get("default_days") or 0)),
                    "price_vnd": price,
                    "manual": bool(item.get("manual")),
                })
            return result
        return {"available": True, "combos": entries("combos"), "monthly": entries("monthly")}

    def feature_draft_payload(self, feature: str, input_data: dict) -> dict:
        """Build provider-free drafts with the same pure helpers used by bot.py.

        These adapters are intentionally limited to deterministic planning
        helpers.  They never invoke an AI/provider function, create a job or
        charge Xu.  Features without a verified pure helper remain a validated
        input draft instead of receiving invented output.
        """
        feature = str(feature or "").strip()
        input_data = dict(input_data or {})
        text = _feature_input_text(input_data)
        if not text:
            return {
                "available": False,
                "feature": feature,
                "source": "validated_input_only",
                "reason": "text_input_required_for_canonical_draft",
            }

        helper_name = ""
        helper_args: tuple[Any, ...] = (text,)
        if feature == "prompt_studio":
            helper_name = "free_hub_meta_prompt_pack"
        elif feature in {"caption", "hashtag"}:
            helper_name = "free_hub_caption_pack"
        elif feature in {"hook", "script"}:
            helper_name = "hook_script_pack"
        elif feature in {"image_create", "image_transform"}:
            helper_name = "free_hub_image_video_prompt_pack"
        elif feature in {"video_single", "video_product", "video_trend", "video_text_to_video", "video_quick", "video_image_to_video"}:
            helper_name = "generate_contextual_prompt"
            helper_args = (text, {
                "platform": str(input_data.get("platform") or "")[:80],
                "aspect_ratio": str(input_data.get("format") or input_data.get("ratio") or "")[:20],
                "duration_seconds": str(input_data.get("duration_seconds") or input_data.get("duration") or "")[:40],
                "goal": str(input_data.get("goal") or "")[:100],
            })
        elif feature in {"storyboard", "video_multiscene", "video_long"}:
            helper_name = "storyboard_pack_build_payload"
            helper_args = ({
                "selected_topic": text,
                "reference_template": str(input_data.get("template") or "product_ad")[:80],
                "platform": str(input_data.get("platform") or "")[:80],
                "preferred_aspect_ratio": str(input_data.get("format") or input_data.get("ratio") or "")[:20],
                "duration": str(input_data.get("duration") or "")[:20],
                "selected_style": str(input_data.get("style") or "")[:100],
                "goal": str(input_data.get("goal") or "")[:100],
                "note": str(input_data.get("notes") or input_data.get("instructions") or "")[:500],
                "selected_suggestion_index": 1,
            }, "vi")
        elif feature == "content_pack":
            helpers = {
                "ideas": self.fn("free_hub_content_ideas_pack"),
                "captions": self.fn("free_hub_caption_pack"),
                "prompts": self.fn("free_hub_image_video_prompt_pack"),
            }
            if not all(helpers.values()):
                return {"available": False, "feature": feature, "source": "canonical_bot", "reason": "content_pack_helpers_unavailable"}
            try:
                content = {name: helper(text) for name, helper in helpers.items() if helper}
            except Exception:
                return {"available": False, "feature": feature, "source": "canonical_bot", "reason": "content_pack_helper_failed"}
            return {
                "available": True,
                "feature": feature,
                "source": "bot.free_hub_content_pack",
                "provider_called": False,
                "charged_xu": 0,
                "content": _sanitize_data(content),
            }
        else:
            return {
                "available": False,
                "feature": feature,
                "source": "validated_input_only",
                "reason": "canonical_draft_helper_not_mapped",
            }

        helper = self.fn(helper_name)
        if not helper:
            return {"available": False, "feature": feature, "source": f"bot.{helper_name}", "reason": "canonical_draft_helper_unavailable"}
        try:
            content = helper(*helper_args)
        except Exception:
            return {"available": False, "feature": feature, "source": f"bot.{helper_name}", "reason": "canonical_draft_helper_failed"}
        return {
            "available": True,
            "feature": feature,
            "source": f"bot.{helper_name}",
            "provider_called": False,
            "charged_xu": 0,
            "content": _sanitize_data(content),
        }

    def feature_estimate_payload(self, feature: str, input_data: dict) -> dict:
        """Quote only values returned by canonical bot pricing helpers."""
        feature = str(feature or "").strip()
        input_data = dict(input_data or {})
        text = _feature_input_text(input_data)
        base = {
            "feature": feature,
            "source": "canonical_bot",
            "currency": "Xu",
            "provider_called": False,
            "charged_xu": 0,
            "requires_confirm": True,
        }
        if feature in {"prompt_studio", "caption", "hashtag", "hook"}:
            return {**base, "available": True, "estimated_xu": 0, "pricing_rule": "provider_free_bot_helper"}
        if feature == "chat":
            calculator = self.fn("calculate_chat_cost")
            if not calculator or not text:
                return {**base, "available": False, "reason": "chat_cost_helper_or_input_unavailable"}
            try:
                return {**base, "available": True, "estimated_xu": max(0, int(calculator(len(text)) or 0)), "pricing_rule": "bot.calculate_chat_cost"}
            except Exception:
                return {**base, "available": False, "reason": "chat_cost_helper_failed"}
        cost_helpers = {
            "script": "workflow_script_storyboard_cost_xu",
            "storyboard": "workflow_script_storyboard_cost_xu",
            "content_pack": "workflow_content_cost_xu",
        }
        if feature in cost_helpers:
            helper_name = cost_helpers[feature]
            helper = self.fn(helper_name)
            if not helper:
                return {**base, "available": False, "reason": f"{helper_name}_unavailable"}
            try:
                return {**base, "available": True, "estimated_xu": max(0, int(helper() or 0)), "pricing_rule": f"bot.{helper_name}"}
            except Exception:
                return {**base, "available": False, "reason": f"{helper_name}_failed"}
        if feature.startswith("image_"):
            pricing = self.pricing_catalog()
            choices = list(pricing.get("image_tiers") or []) if pricing.get("available") else []
            requested_tier = str(input_data.get("tier") or "").strip()
            selected = next((item for item in choices if str(item.get("code")) == requested_tier), None)
            return {
                **base,
                "available": bool(choices),
                "estimated_xu": int(selected.get("cost_xu") or 0) if selected else None,
                "selected_tier": selected or {},
                "tier_required": selected is None,
                "choices": choices,
                "pricing_rule": "bot.media_workflow_pricing_payload.image_tiers",
            }
        video_features = {
            "video_single", "video_product", "video_trend", "video_text_to_video", "video_quick",
            "video_image_to_video", "video_multiscene", "video_long",
        }
        if feature in video_features:
            pricing = self.pricing_catalog()
            choices = list(pricing.get("video_tiers") or []) if pricing.get("available") else []
            requested_tier = str(input_data.get("tier") or input_data.get("video_tier") or "").strip()
            selected = next((item for item in choices if str(item.get("code")) == requested_tier), None)
            raw_scenes = str(input_data.get("scene_count") or input_data.get("scenes") or "").strip()
            scene_match = re.search(r"\d+", raw_scenes)
            scene_count = int(scene_match.group(0)) if scene_match else 0
            if selected and scene_count:
                scene_price = self.fn("calculate_scene_video_price")
                discount = self.fn("video_scene_discount_percent")
                if scene_price and discount:
                    try:
                        total = max(0, int(scene_price(int(selected.get("cost_xu") or 0), scene_count) or 0))
                        return {
                            **base,
                            "available": True,
                            "estimated_xu": total,
                            "tier": selected,
                            "scene_count": max(1, min(20, scene_count)),
                            "scene_discount_percent": max(0, min(100, int(discount(scene_count) or 0))),
                            "pricing_rule": "bot.calculate_scene_video_price",
                        }
                    except Exception:
                        pass
            return {
                **base,
                "available": bool(choices),
                "estimated_xu": None,
                "tier": selected or {},
                "tier_required": selected is None,
                "scene_count_required": not bool(scene_count),
                "choices": choices,
                "pricing_rule": "bot.media_workflow_pricing_payload.video_tiers",
            }
        return {**base, "available": False, "reason": "canonical_estimate_not_mapped"}

    def wallet_history(self, user_id: str, limit: int = 50) -> list[dict]:
        conn = self.db()
        try:
            columns = self.columns(conn, "credit_events")
            if not columns:
                return []
            selected = [name for name in ("id", "delta", "balance_after", "event_type", "ref_id", "note", "created_at") if name in columns]
            order = "id DESC" if "id" in columns else "created_at DESC"
            rows = conn.execute(f"SELECT {','.join(selected)} FROM credit_events WHERE user_id=? ORDER BY {order} LIMIT ?", (str(user_id), max(1, min(int(limit), 100)))).fetchall()
            result = []
            for row in rows:
                item = dict(zip(selected, row))
                result.append({
                    "id": str(item.get("id") or ""),
                    "delta_xu": int(item.get("delta") or 0),
                    "balance_after_xu": int(item.get("balance_after") or 0),
                    "event_type": _safe_text(item.get("event_type"), 80),
                    "reference": _safe_text(item.get("ref_id"), 120),
                    "note": _safe_text(item.get("note"), 200),
                    "created_at": _safe_text(item.get("created_at"), 80),
                })
            return result
        finally:
            conn.close()

    def _job_rows(self, user_id: str, *, admin: bool = False, limit: int = 100) -> list[dict]:
        table_map = {
            "shopaikey_jobs": ("job_type", "status", "created_at", "updated_at", "finished_at", "xu_cost_planned", "xu_deducted", "refund_status", "result_url", "output_file_id", "error_class"),
            "local_worker_jobs": ("job_type", "status", "created_at", "updated_at", "finished_at", "xu_cost", "output_url", "output_file_id", "error_short"),
            "music_generation_jobs": ("status", "created_at", "updated_at", "finished_at", "cost_xu", "charged_xu", "refund_status", "output_url", "output_file_id", "error_class"),
            "video_jobs": ("status", "created_at", "updated_at", "finished_at", "cost_xu", "output_url", "output_file_id"),
            "media_factory_jobs": ("mode", "status", "created_at", "updated_at", "cost_xu", "output_url"),
        }
        conn = self.db()
        try:
            result: list[dict] = []
            per_table = max(1, min(100, limit))
            for table, candidates in table_map.items():
                columns = self.columns(conn, table)
                if not columns or "id" not in columns or "user_id" not in columns:
                    continue
                selected = [name for name in ("id", "user_id", *candidates) if name in columns]
                order = "created_at DESC" if "created_at" in columns else "id DESC"
                if admin:
                    rows = conn.execute(f"SELECT {','.join(selected)} FROM {table} ORDER BY {order} LIMIT ?", (per_table,)).fetchall()
                else:
                    rows = conn.execute(f"SELECT {','.join(selected)} FROM {table} WHERE user_id=? ORDER BY {order} LIMIT ?", (str(user_id), per_table)).fetchall()
                for row in rows:
                    item = dict(zip(selected, row))
                    raw_status = str(item.get("status") or "").lower()
                    if raw_status in {"completed", "success", "done", "pass", "delivered", "sent"}:
                        status_name = "completed"
                    elif raw_status in {"queued", "pending", "quoted", "awaiting_confirm"}:
                        status_name = "queued" if raw_status != "quoted" else "awaiting_confirm"
                    elif raw_status in {"processing", "running", "submitted", "in_progress"}:
                        status_name = "processing"
                    elif raw_status in {"refunded"}:
                        status_name = "refunded"
                    elif raw_status in {"cancelled", "canceled"}:
                        status_name = "cancelled"
                    else:
                        status_name = "failed" if raw_status else "draft"
                    output_available = bool(item.get("result_url") or item.get("output_url") or item.get("output_file_id"))
                    result.append({
                        "id": f"{table}:{item.get('id')}",
                        "user_id": str(item.get("user_id") or "") if admin else None,
                        "feature": _safe_text(item.get("job_type") or item.get("mode") or table, 100),
                        "status": status_name,
                        "created_at": _safe_text(item.get("created_at"), 80),
                        "updated_at": _safe_text(item.get("updated_at") or item.get("finished_at"), 80),
                        "estimated_xu": int(item.get("xu_cost_planned") or item.get("xu_cost") or item.get("cost_xu") or 0),
                        "charged_xu": int(item.get("xu_deducted") or item.get("charged_xu") or 0),
                        "refund_status": _safe_text(item.get("refund_status"), 60),
                        "output_available": output_available,
                        "error_category": _safe_text(item.get("error_class") or item.get("error_short"), 100),
                    })
            result.sort(key=lambda item: item.get("created_at") or "", reverse=True)
            return result[:limit]
        finally:
            conn.close()

    def jobs(self, user_id: str, *, admin: bool = False) -> list[dict]:
        return self._job_rows(user_id, admin=admin)

    def job(self, user_id: str, job_id: str, *, admin: bool = False) -> dict | None:
        match = _JOB_ID_PATTERN.fullmatch(str(job_id or ""))
        if not match:
            return None
        for item in self._job_rows(user_id, admin=admin, limit=250):
            if item["id"] == f"{match.group(1)}:{match.group(2)}":
                return item
        return None

    def assets(self, user_id: str) -> list[dict]:
        """Expose only validated/owned output metadata; never filesystem paths or raw URLs."""
        return [
            {
                "id": item["id"],
                "feature": item["feature"],
                "status": item["status"],
                "created_at": item["created_at"],
                "download_ready": bool(item["output_available"] and item["status"] == "completed"),
            }
            for item in self.jobs(user_id)
            if item.get("output_available")
        ]

    def asset_download(self, user_id: str, asset_id: str) -> dict:
        """Validate ownership without ever returning a raw provider URL/path.

        The frozen bot baseline does not expose a canonical signed-download
        issuer to the Web App yet. Returning `guarded` here is intentional: a
        completed provider job is not permission to leak its result URL.
        """
        item = self.job(user_id, asset_id)
        if not item:
            return response(False, "failed", "Không tìm thấy tài sản hoặc bạn không có quyền truy cập.", error_code="ASSET_NOT_FOUND")
        if item.get("status") != "completed" or not item.get("output_available"):
            return response(False, "guarded", "Tài sản chưa có output hợp lệ để giao riêng tư.", error_code="ASSET_NOT_DELIVERABLE")
        return response(False, "guarded", "Tài sản đã hoàn tất nhưng URL tải riêng tư đang chờ adapter canonical được ký tạm thời.", error_code="SIGNED_DELIVERY_ADAPTER_REQUIRED")

    def tickets(self, user_id: str, *, admin: bool = False, limit: int = 100) -> list[dict]:
        conn = self.db()
        try:
            columns = self.columns(conn, "feedback")
            if not columns:
                return []
            selected = [name for name in ("id", "user_id", "username", "category", "content", "context", "status", "timestamp", "reviewed_at", "resolved_at") if name in columns]
            order = "timestamp DESC" if "timestamp" in columns else "id DESC"
            if admin:
                rows = conn.execute(f"SELECT {','.join(selected)} FROM feedback ORDER BY {order} LIMIT ?", (max(1, min(limit, 200)),)).fetchall()
            else:
                rows = conn.execute(f"SELECT {','.join(selected)} FROM feedback WHERE user_id=? ORDER BY {order} LIMIT ?", (str(user_id), max(1, min(limit, 100)))).fetchall()
            result = []
            for row in rows:
                item = dict(zip(selected, row))
                result.append({
                    "id": str(item.get("id") or ""),
                    "user_id": str(item.get("user_id") or "") if admin else None,
                    "category": _safe_text(item.get("category") or "support", 80),
                    "subject": _safe_text(item.get("context") or "Hỗ trợ TOAN AAS", 180),
                    "content": _safe_text(item.get("content"), 1200),
                    "status": _safe_text(item.get("status") or "new", 40),
                    "created_at": _safe_text(item.get("timestamp"), 80),
                    "updated_at": _safe_text(item.get("resolved_at") or item.get("reviewed_at") or item.get("timestamp"), 80),
                })
            return result
        finally:
            conn.close()

    def create_ticket(self, user_id: str, subject: str, content: str) -> dict:
        if not self.identity(user_id):
            return response(False, "failed", "Không tìm thấy tài khoản canonical.", error_code="USER_NOT_FOUND")
        subject = _safe_text(subject, 180)
        content = _safe_text(content, 4000)
        if not subject or not content:
            return response(False, "failed", "Vui lòng nhập chủ đề và nội dung hỗ trợ.", error_code="TICKET_INPUT_REQUIRED")
        conn = self.db()
        try:
            columns = self.columns(conn, "feedback")
            if not columns:
                return response(False, "guarded", "Kênh hỗ trợ canonical chưa sẵn sàng.", error_code="SUPPORT_STORE_UNAVAILABLE")
            identity = self.identity(user_id) or {}
            values = {
                "user_id": str(user_id), "username": identity.get("username") or "", "category": "web_ticket",
                "content": content, "context": subject, "status": "new", "timestamp": _now(),
            }
            fields = [name for name in values if name in columns]
            placeholders = ",".join("?" for _ in fields)
            cursor = conn.execute(f"INSERT INTO feedback ({','.join(fields)}) VALUES ({placeholders})", tuple(values[name] for name in fields))
            conn.commit()
            return response(True, "queued", "Đã tạo ticket hỗ trợ.", data={"id": str(cursor.lastrowid), "status": "new"})
        finally:
            conn.close()

    def readiness(self) -> dict[str, dict]:
        registry = self.fn("engine_readiness_registry")
        try:
            raw = registry() if registry else {}
        except Exception:
            raw = {}
        safe: dict[str, dict] = {}
        for key, value in dict(raw or {}).items():
            item = dict(value or {})
            safe[str(key)] = {
                "configured": bool(item.get("configured")),
                "public_ready": bool(item.get("public_ready")),
                "guarded": not bool(item.get("public_ready")),
                "reason": _safe_text(item.get("reason"), 160),
                "missing": [_safe_text(part, 80) for part in list(item.get("missing") or [])[:20]],
                "adapter": _safe_text(item.get("adapter"), 80),
            }
        aliases = {
            "voice_saved_tts": "voice_tts", "music_library": None, "sfx_library": None,
            "image_create": None, "image_edit": None, "image_upscale": None,
            "image_transform": None, "image_remove_background": None, "image_history": None,
            "chat": None, "prompt_studio": None, "caption": None, "hashtag": None, "hook": None,
            "script": None, "storyboard": None, "content_pack": None, "documents": None,
            "documents_pdf": None, "documents_ocr": None, "documents_merge": None, "documents_split": None,
            "documents_compress": None, "documents_translate": None,
            "video_image_to_video": "video_single", "video_product": "video_single", "video_trend": "video_single",
            "video_text_to_video": "video_single", "video_quick": "video_single", "video_progress": "video_single",
            "video_preview": "video_single", "video_export": "video_single", "video_addons": "video_single", "video_mux": "video_single",
            "video_long": "video_long", "voice_vault": None, "voice_preview": None, "voice_outputs": None,
            "music_sfx": None, "music_upload": None, "subtitle_create": "subtitle_asr", "asr": "subtitle_asr", "subtitle_formats": "subtitle_asr",
        }
        for key, source in aliases.items():
            if key not in safe:
                if source and source in safe:
                    safe[key] = {**safe[source], "alias_of": source}
                else:
                    safe[key] = {"configured": False, "public_ready": False, "guarded": True, "reason": "bridge_adapter_not_mapped", "missing": ["core_bridge_adapter"], "adapter": ""}
        return safe

    def admin_summary(self) -> dict:
        conn = self.db()
        try:
            counts = {}
            for table, label in (("users", "users"), ("payos_orders", "payments"), ("shopaikey_jobs", "engine_jobs"), ("local_worker_jobs", "worker_jobs")):
                counts[label] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) if self.table_exists(conn, table) else 0
            return {"counts": counts, "readiness": self.readiness(), "source": "canonical_bot"}
        finally:
            conn.close()

    def admin_users(self, limit: int = 100) -> list[dict]:
        conn = self.db()
        try:
            columns = self.columns(conn, "users")
            names = [name for name in ("user_id", "username", "credits", "total_spent", "is_vip", "join_date") if name in columns]
            if not names:
                return []
            rows = conn.execute(f"SELECT {','.join(names)} FROM users ORDER BY rowid DESC LIMIT ?", (max(1, min(limit, 200)),)).fetchall()
            return [{
                "user_id": str(item.get("user_id") or ""),
                "username": _safe_text(item.get("username"), 100),
                "balance_xu": int(item.get("credits") or 0),
                "total_spent_xu": int(item.get("total_spent") or 0),
                "is_vip": bool(item.get("is_vip")),
                "created_at": _safe_text(item.get("join_date"), 80),
            } for item in (dict(zip(names, row)) for row in rows)]
        finally:
            conn.close()

    def admin_payments(self, limit: int = 100) -> list[dict]:
        conn = self.db()
        try:
            columns = self.columns(conn, "payos_orders")
            names = [name for name in ("order_code", "user_id", "amount", "xu", "order_type", "status", "created_at", "paid_at") if name in columns]
            if not names:
                return []
            rows = conn.execute(f"SELECT {','.join(names)} FROM payos_orders ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 200)),)).fetchall()
            return [{
                "order_code": _safe_text(item.get("order_code"), 100),
                "user_id": str(item.get("user_id") or ""),
                "amount_vnd": int(item.get("amount") or 0),
                "xu": int(item.get("xu") or 0),
                "type": _safe_text(item.get("order_type"), 80),
                "status": _safe_text(item.get("status"), 50),
                "created_at": _safe_text(item.get("created_at"), 80),
                "paid_at": _safe_text(item.get("paid_at"), 80),
            } for item in (dict(zip(names, row)) for row in rows)]
        finally:
            conn.close()

    def admin_audit_events(self, limit: int = 100) -> list[dict]:
        self.ensure_bridge_tables()
        conn = self.db()
        try:
            rows = conn.execute(
                f"SELECT request_id, actor_id, action, target, outcome, note, created_at FROM {BRIDGE_TABLE_AUDIT} ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
            return [{
                "id": _safe_text(row[0], 120), "user_id": _safe_text(row[1], 120), "action": _safe_text(row[2], 160),
                "target": _safe_text(row[3], 160), "status": _safe_text(row[4], 40), "note": _safe_text(row[5], 300),
                "created_at": _safe_text(row[6], 80),
            } for row in rows]
        finally:
            conn.close()

    def admin_module(self, module: str, *, record_id: str = "") -> dict:
        """Read-only Admin ERP adapters, mapped deliberately to bot-owned data."""
        key = str(module or "").strip().lower().replace("_", "-")
        record = str(record_id or "").strip()
        if record and not _ID_PATTERN.fullmatch(record):
            return {"module": key, "items": [], "read_only": True, "message": "ID bản ghi không hợp lệ."}
        if key in {"overview", "summary"}:
            return {"module": "overview", "items": [], "counts": self.admin_summary().get("counts") or {}, "read_only": True}
        if key in {"users", "user", "wallet"}:
            items = self.admin_users()
            if record:
                items = [item for item in items if str(item.get("user_id")) == record]
            return {"module": key, "items": items, "read_only": True}
        if key in {"payments", "topups", "revenue", "refunds"}:
            items = self.admin_payments()
            if key == "topups":
                items = [item for item in items if "topup" in str(item.get("type") or "").lower()]
            elif key == "refunds":
                items = [item for item in items if "refund" in str(item.get("type") or "").lower() or "refund" in str(item.get("status") or "").lower()]
            return {"module": key, "items": items, "read_only": True}
        if key in {"jobs", "failed-jobs", "workers", "runtime"}:
            items = self.jobs("", admin=True)
            if key == "failed-jobs":
                items = [item for item in items if str(item.get("status") or "").lower() in {"failed", "error", "cancelled"}]
            if key == "workers":
                items = [item for item in items if "worker" in str(item.get("source") or "").lower() or "worker" in str(item.get("id") or "").lower()]
            return {"module": key, "items": items, "read_only": True}
        if key in {"providers", "provider-cost", "features", "freezes", "pricing", "promos"}:
            items = []
            for feature, state in self.readiness().items():
                items.append({
                    "id": feature,
                    "feature": feature,
                    "status": "ready" if state.get("public_ready") else "guarded",
                    "reason": _safe_text(state.get("reason"), 160),
                    "updated_at": "",
                })
            return {"module": key, "items": items, "read_only": True}
        if key in {"tickets", "support"}:
            return {"module": key, "items": self.tickets("", admin=True), "read_only": True}
        if key in {"audit", "security"}:
            return {"module": key, "items": self.admin_audit_events(), "read_only": True}
        if key in {"reports", "system", "backups", "leads"}:
            # These modules deliberately remain report/read-only surfaces until
            # a bot-specific exporter or storage adapter is verified. No
            # browser action is offered as a substitute.
            return {
                "module": key,
                "items": [],
                "read_only": True,
                "message": "Module đang chờ adapter canonical read-only của bot; không có thao tác giả lập.",
            }
        return {"module": key, "items": [], "read_only": True, "message": "Module admin chưa có adapter canonical."}


async def _authorize(request: Request) -> str:
    token = os.environ.get("CORE_BRIDGE_TOKEN", "").strip()
    secret = os.environ.get("CORE_BRIDGE_HMAC_SECRET", "").strip()
    if not token or not secret:
        raise HTTPException(status_code=503, detail="core bridge is not configured")
    authorization = request.headers.get("authorization", "")
    supplied_token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not supplied_token or not hmac.compare_digest(supplied_token, token):
        raise HTTPException(status_code=401, detail="invalid core bridge token")
    timestamp = request.headers.get("x-toan-aas-timestamp", "")
    request_id = request.headers.get("x-toan-aas-request-id", "")
    signature = request.headers.get("x-toan-aas-signature", "")
    actor_id = request.headers.get("x-toan-aas-actor-id", "")
    if not timestamp.isdigit() or not _ID_PATTERN.fullmatch(request_id) or not _ID_PATTERN.fullmatch(actor_id):
        raise HTTPException(status_code=401, detail="invalid core bridge signature metadata")
    if abs(int(time.time()) - int(timestamp)) > 300:
        raise HTTPException(status_code=401, detail="stale core bridge request")
    body = await request.body()
    digest = hashlib.sha256(body).hexdigest()
    material = f"{timestamp}.{request_id}.{request.method.upper()}.{request.url.path}.{digest}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), material, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="invalid core bridge signature")
    # Request IDs double as signed nonces.  Rejecting a duplicate prevents a
    # captured private request from being replayed within the timestamp window
    # while still allowing normal idempotent retries to use a fresh request ID.
    now_wall = time.time()
    expiry = now_wall - 305
    for nonce, seen_at in list(_request_nonces.items()):
        if seen_at < expiry:
            _request_nonces.pop(nonce, None)
    if request_id in _request_nonces:
        raise HTTPException(status_code=409, detail="replayed core bridge request")
    _request_nonces[request_id] = now_wall
    now = time.monotonic()
    window = _rate_windows[actor_id]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= 120:
        raise HTTPException(status_code=429, detail="core bridge rate limit")
    window.append(now)
    request.state.bridge_actor_id = actor_id
    request.state.bridge_request_id = request_id
    return actor_id


async def _payload(request: Request) -> dict:
    try:
        value = await request.json()
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _target_user(request: Request, payload: dict, actor_id: str) -> str:
    target = str(payload.get("user_id") or request.query_params.get("user_id") or "").strip()
    if not target or target != actor_id:
        raise HTTPException(status_code=403, detail="bridge actor does not match target user")
    return target


def _validate_idempotency(value: Any) -> str:
    key = str(value or "")
    if not re.fullmatch(r"[A-Za-z0-9._:-]{12,160}", key):
        raise HTTPException(status_code=422, detail="invalid idempotency key")
    return key


def _feature_readiness(bridge: BotCoreBridge, feature: str) -> dict:
    return bridge.readiness().get(feature) or {
        "configured": False,
        "public_ready": False,
        "guarded": True,
        "reason": "bridge_adapter_not_mapped",
        "missing": ["core_bridge_adapter"],
        "adapter": "",
    }


def _feature_draft_or_estimate(bridge: BotCoreBridge, feature: str, user_id: str, action: str, input_data: dict) -> dict:
    readiness = _feature_readiness(bridge, feature)
    if bridge.identity(user_id) is None:
        return response(False, "failed", "Không tìm thấy tài khoản Telegram canonical.", error_code="USER_NOT_FOUND")
    uploads, missing_uploads = bridge.uploads_for_ids(user_id, input_data.get("upload_ids"))
    if missing_uploads:
        return response(False, "failed", "Tệp đính kèm không hợp lệ hoặc không thuộc tài khoản này.", error_code="UPLOAD_NOT_FOUND")
    # Draft/estimate deliberately remain open for guarded public features. The
    # payload below comes only from pure bot.py planning/pricing helpers and
    # never invokes a provider or ledger writer.
    canonical = bridge.feature_draft_payload(feature, input_data) if action == "draft" else bridge.feature_estimate_payload(feature, input_data)
    if action == "draft" and canonical.get("available"):
        message = "Bản nháp canonical từ bot đã sẵn sàng để xem xét."
    elif action == "estimate" and canonical.get("available"):
        message = "Ước tính canonical đã sẵn sàng; chưa trừ Xu và vẫn cần xác nhận."
    else:
        message = "Yêu cầu đã được kiểm tra nhưng adapter canonical chi tiết vẫn đang được bảo vệ."
    status_name = "draft" if action == "draft" else "awaiting_confirm"
    return response(True, status_name, message, data={
        "feature": feature,
        "readiness": readiness,
        "input_accepted": bool(input_data),
        "uploads": uploads,
        action: canonical,
        "requires_confirm": True,
        "provider_called": False,
        "charged_xu": 0,
    })


async def _feature_confirm(bridge: BotCoreBridge, feature: str, user_id: str, payload: dict, request: Request) -> dict:
    key = _validate_idempotency(payload.get("idempotency_key"))
    scope = f"feature:{user_id}:{feature}:confirm"
    if existing := bridge.idempotency_get(scope, key):
        return existing
    readiness = _feature_readiness(bridge, feature)
    input_data = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    uploads, missing_uploads = bridge.uploads_for_ids(user_id, input_data.get("upload_ids"))
    if missing_uploads:
        result = response(False, "failed", "Tệp đính kèm không hợp lệ hoặc không thuộc tài khoản này.", data={"feature": feature}, error_code="UPLOAD_NOT_FOUND")
        bridge.idempotency_put(scope, key, result)
        bridge.audit(user_id, "feature.confirm", getattr(request.state, "bridge_request_id", ""), target=feature, outcome="failed", note="invalid upload reference")
        return result
    if not _bool_env("WEBAPP_PROVIDER_CALLS_ENABLED", False):
        result = response(False, "guarded", "Tính năng đang ở chế độ an toàn và chưa gọi engine từ Web.", data={"feature": feature, "readiness": readiness, "uploads": uploads}, error_code="WEBAPP_PROVIDER_CALLS_DISABLED")
        bridge.idempotency_put(scope, key, result)
        bridge.audit(user_id, "feature.confirm", getattr(request.state, "bridge_request_id", ""), target=feature, outcome="guarded", note="provider calls disabled")
        return result
    executable = {"voice_tts", "voice_clone", "voice_saved_tts", "music_background", "music_song", "subtitle_asr", "subtitle_translate", "video_dub", "video_single", "video_multiscene", "video_long"}
    if feature not in executable:
        result = response(False, "guarded", PUBLIC_GUARD, data={"feature": feature, "readiness": readiness}, error_code="BOT_FEATURE_NOT_BRIDGED")
        bridge.idempotency_put(scope, key, result)
        bridge.audit(user_id, "feature.confirm", getattr(request.state, "bridge_request_id", ""), target=feature, outcome="guarded", note="no safe executor mapping")
        return result
    executor = bridge.fn("execute_engine")
    if not executor:
        result = response(False, "guarded", PUBLIC_GUARD, data={"feature": feature, "readiness": readiness}, error_code="ENGINE_EXECUTOR_UNAVAILABLE")
        bridge.idempotency_put(scope, key, result)
        return result
    # Never accept a callable/runner or privileged context from an HTTP client.
    safe_input = _sanitize_data(input_data)
    context = {
        "user_id": user_id,
        "entry_source": bridge.core.get("ENGINE_ENTRY_SOURCE_PRODUCT", "interactive_product"),
        "confirm_paid": True,
        "admin_interactive_confirm": bridge.is_admin(user_id),
        "allow_admin": bridge.is_admin(user_id),
    }
    try:
        raw = await executor(feature, safe_input, context)
    except Exception:
        raw = {"ok": False, "status": "EXECUTOR_FAILED"}
    raw = dict(raw or {})
    output_bytes = b""
    bytes_fn = bridge.fn("engine_output_bytes")
    task_fn = bridge.fn("engine_provider_task_id")
    try:
        output_bytes = bytes_fn(raw) if bytes_fn else b""
    except Exception:
        output_bytes = b""
    try:
        task_id = str(task_fn(raw) or "") if task_fn else ""
    except Exception:
        task_id = ""
    if raw.get("ok") and output_bytes:
        result = response(True, "completed", "Engine đã tạo đầu ra hợp lệ.", data={"feature": feature, "output_available": True, "output_bytes": len(output_bytes), "readiness": readiness})
        outcome = "completed"
    elif raw.get("ok") and task_id:
        result = response(True, "queued", "Yêu cầu đã được core tiếp nhận và đang theo dõi trạng thái.", data={"feature": feature, "job_accepted": True, "readiness": readiness})
        outcome = "queued"
    elif str(raw.get("status") or "").upper() == "GATE_BLOCKED":
        result = response(False, "guarded", _safe_text(raw.get("message") or PUBLIC_GUARD, 300), data={"feature": feature, "readiness": readiness}, error_code="FEATURE_GUARDED")
        outcome = "guarded"
    else:
        result = response(False, "failed", "TOAN AAS chưa tạo được đầu ra hợp lệ và chưa xác nhận thành công.", data={"feature": feature, "readiness": readiness}, error_code="ENGINE_NO_VALID_OUTPUT")
        outcome = "failed"
    bridge.idempotency_put(scope, key, result)
    bridge.audit(user_id, "feature.confirm", getattr(request.state, "bridge_request_id", ""), target=feature, outcome=outcome)
    return result


async def confirm_web_link_from_telegram(core: dict[str, Any], user_id: str, code: str) -> dict:
    """Confirm a one-time Web linking code for the currently authenticated TG user.

    This is called by `/start web_<code>` and `/linkweb <code>` after Telegram
    has established the caller identity. It never accepts a browser-provided
    Telegram ID and it does not touch wallet, PayOS, jobs or providers.
    """
    code = str(code or "").strip()
    if not _WEB_LINK_CODE_PATTERN.fullmatch(code):
        return response(False, "failed", "Mã liên kết Web không hợp lệ.", error_code="LINK_CODE_INVALID")
    callback_url = os.environ.get("WEBAPP_LINK_CALLBACK_URL", "").strip()
    callback_token = os.environ.get("WEBAPP_LINK_CALLBACK_TOKEN", "").strip()
    callback_secret = os.environ.get("WEBAPP_LINK_CALLBACK_HMAC_SECRET", "").strip()
    if not callback_url or not callback_token or not callback_secret:
        return response(False, "guarded", "Liên kết Telegram chưa được cấu hình ở private bridge.", error_code="TELEGRAM_LINK_CALLBACK_NOT_CONFIGURED")
    bridge = BotCoreBridge(core)
    identity = bridge.identity(user_id)
    if not identity:
        return response(False, "failed", "Không tìm thấy tài khoản Telegram canonical.", error_code="USER_NOT_FOUND")
    callback_payload = {
        "code": code,
        "canonical_user_id": str(user_id),
        "role": identity["role"],
        "display_name": identity["username"],
    }
    callback_body = json.dumps(callback_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            result = await client.post(
                callback_url,
                headers=_web_link_callback_headers(callback_url, callback_token, callback_secret, callback_body),
                content=callback_body,
            )
        if result.status_code >= 300:
            return response(False, "failed", "Không thể xác nhận mã liên kết Web.", error_code="TELEGRAM_LINK_CALLBACK_FAILED")
    except (httpx.HTTPError, ValueError):
        return response(False, "failed", "Không thể xác nhận mã liên kết Web.", error_code="TELEGRAM_LINK_CALLBACK_FAILED")
    return response(True, "completed", "Đã xác nhận liên kết Telegram.")


def build_core_bridge_router(core: dict[str, Any]) -> APIRouter:
    bridge = BotCoreBridge(core)
    router = APIRouter(prefix="/internal/v1", tags=["Web App Private Core Bridge"], route_class=BridgeRoute)

    @router.get("/me")
    async def me(request: Request):
        actor = await _authorize(request)
        user_id = _target_user(request, {}, actor)
        value = bridge.identity(user_id)
        return response(True, "completed", "Thông tin tài khoản", data=value) if value else response(False, "failed", "Không tìm thấy tài khoản canonical.", error_code="USER_NOT_FOUND")

    @router.get("/wallet")
    async def wallet(request: Request):
        actor = await _authorize(request)
        user_id = _target_user(request, {}, actor)
        value = bridge.wallet(user_id)
        return response(True, "completed", "Số dư canonical", data=value) if value else response(False, "failed", "Không tìm thấy ví canonical.", error_code="USER_NOT_FOUND")

    @router.get("/wallet/history")
    async def wallet_history(request: Request):
        actor = await _authorize(request)
        user_id = _target_user(request, {}, actor)
        if not bridge.identity(user_id):
            return response(False, "failed", "Không tìm thấy tài khoản canonical.", error_code="USER_NOT_FOUND")
        return response(True, "completed", "Lịch sử Xu canonical", data={"items": bridge.wallet_history(user_id)})

    @router.get("/pricing")
    async def pricing(request: Request):
        actor = await _authorize(request)
        user_id = _target_user(request, {}, actor)
        if not bridge.identity(user_id):
            return response(False, "failed", "Không tìm thấy tài khoản canonical.", error_code="USER_NOT_FOUND")
        return response(True, "completed", "Bảng giá canonical", data=bridge.pricing_catalog())

    @router.get("/packages")
    async def packages(request: Request):
        actor = await _authorize(request)
        user_id = _target_user(request, {}, actor)
        if not bridge.identity(user_id):
            return response(False, "failed", "Không tìm thấy tài khoản canonical.", error_code="USER_NOT_FOUND")
        return response(True, "completed", "Danh mục gói canonical", data=bridge.packages_catalog())

    @router.post("/payments/create")
    async def payment_create(request: Request):
        actor = await _authorize(request)
        payload = await _payload(request)
        _target_user(request, payload, actor)
        # Explicitly avoid a second PayOS creation path until deployment topology is verified.
        bridge.audit(actor, "payment.create", getattr(request.state, "bridge_request_id", ""), outcome="guarded", note="canonical payment flow not exposed by bridge")
        return response(False, "guarded", "Thanh toán Web đang chờ kết nối canonical PayOS đã được xác minh.", error_code="PAYMENT_CORE_BRIDGE_REQUIRED")

    @router.get("/payments/{payment_id}")
    async def payment_status(payment_id: str, request: Request):
        actor = await _authorize(request)
        user_id = _target_user(request, {}, actor)
        conn = bridge.db()
        try:
            if not bridge.table_exists(conn, "payos_orders"):
                return response(False, "failed", "Không tìm thấy payment store canonical.", error_code="PAYMENT_NOT_FOUND")
            columns = bridge.columns(conn, "payos_orders")
            selected = [name for name in ("order_code", "amount", "xu", "status", "created_at", "paid_at") if name in columns]
            row = conn.execute(f"SELECT {','.join(selected)} FROM payos_orders WHERE order_code=? AND user_id=?", (str(payment_id), user_id)).fetchone()
            if not row:
                return response(False, "failed", "Không tìm thấy giao dịch.", error_code="PAYMENT_NOT_FOUND")
            item = dict(zip(selected, row))
            return response(True, "completed", "Trạng thái thanh toán canonical", data={"order_code": _safe_text(item.get("order_code"), 100), "amount_vnd": int(item.get("amount") or 0), "xu": int(item.get("xu") or 0), "status": _safe_text(item.get("status"), 60), "created_at": _safe_text(item.get("created_at"), 80), "paid_at": _safe_text(item.get("paid_at"), 80)})
        finally:
            conn.close()

    @router.get("/jobs")
    async def jobs(request: Request):
        actor = await _authorize(request)
        user_id = _target_user(request, {}, actor)
        return response(True, "completed", "Danh sách job canonical", data={"items": bridge.jobs(user_id)})

    @router.get("/jobs/{job_id}")
    async def job(job_id: str, request: Request):
        actor = await _authorize(request)
        user_id = _target_user(request, {}, actor)
        value = bridge.job(user_id, job_id)
        return response(True, "completed", "Chi tiết job canonical", data=value) if value else response(False, "failed", "Không tìm thấy job hoặc bạn không có quyền truy cập.", error_code="JOB_NOT_FOUND")

    @router.get("/assets")
    async def assets(request: Request):
        actor = await _authorize(request)
        user_id = _target_user(request, {}, actor)
        return response(True, "completed", "Tài sản canonical", data={"items": bridge.assets(user_id)})

    @router.get("/assets/{asset_id}/download")
    async def asset_download(asset_id: str, request: Request):
        actor = await _authorize(request)
        user_id = _target_user(request, {}, actor)
        result = bridge.asset_download(user_id, asset_id)
        bridge.audit(user_id, "asset.download.request", getattr(request.state, "bridge_request_id", ""), target=asset_id, outcome=result["status"])
        return result

    @router.post("/uploads")
    async def upload_create(request: Request):
        """Accept a Web-validated file into bot-owned canonical staging."""
        actor = await _authorize(request)
        payload = await _payload(request)
        user_id = _target_user(request, payload, actor)
        result = bridge.create_upload(user_id, payload)
        bridge.audit(user_id, "upload.create", getattr(request.state, "bridge_request_id", ""), target=str((result.get("data") or {}).get("id") or ""), outcome=result["status"])
        return result

    @router.get("/support/tickets")
    async def support_tickets(request: Request):
        actor = await _authorize(request)
        user_id = _target_user(request, {}, actor)
        return response(True, "completed", "Tickets canonical", data={"items": bridge.tickets(user_id)})

    @router.post("/support/tickets")
    async def support_ticket_create(request: Request):
        actor = await _authorize(request)
        payload = await _payload(request)
        user_id = _target_user(request, payload, actor)
        key = _validate_idempotency(payload.get("idempotency_key"))
        scope = f"ticket:{user_id}"
        if existing := bridge.idempotency_get(scope, key):
            return existing
        result = bridge.create_ticket(user_id, str(payload.get("subject") or ""), str(payload.get("detail") or ""))
        bridge.idempotency_put(scope, key, result)
        bridge.audit(user_id, "support.ticket.create", getattr(request.state, "bridge_request_id", ""), target=str(result.get("data", {}).get("id") or ""), outcome=result["status"])
        return result

    @router.get("/features/status")
    async def features_status(request: Request):
        actor = await _authorize(request)
        _target_user(request, {}, actor)
        return response(True, "completed", "Readiness canonical", data={"features": bridge.readiness()})

    @router.post("/features/{feature}/draft")
    async def feature_draft(feature: str, request: Request):
        actor = await _authorize(request)
        payload = await _payload(request)
        user_id = _target_user(request, payload, actor)
        result = _feature_draft_or_estimate(bridge, feature, user_id, "draft", payload.get("input") if isinstance(payload.get("input"), dict) else {})
        bridge.audit(actor, "feature.draft", getattr(request.state, "bridge_request_id", ""), target=feature, outcome=result["status"])
        return result

    @router.post("/features/{feature}/estimate")
    async def feature_estimate(feature: str, request: Request):
        actor = await _authorize(request)
        payload = await _payload(request)
        user_id = _target_user(request, payload, actor)
        result = _feature_draft_or_estimate(bridge, feature, user_id, "estimate", payload.get("input") if isinstance(payload.get("input"), dict) else {})
        bridge.audit(actor, "feature.estimate", getattr(request.state, "bridge_request_id", ""), target=feature, outcome=result["status"])
        return result

    @router.post("/features/{feature}/confirm")
    async def feature_confirm(feature: str, request: Request):
        actor = await _authorize(request)
        payload = await _payload(request)
        user_id = _target_user(request, payload, actor)
        return await _feature_confirm(bridge, feature, user_id, payload, request)

    @router.get("/admin/summary")
    async def admin_summary(request: Request):
        actor = await _authorize(request)
        _target_user(request, {}, actor)
        if not bridge.is_admin(actor):
            raise HTTPException(status_code=403, detail="admin role required")
        return response(True, "completed", "Tổng quan canonical", data=bridge.admin_summary())

    @router.get("/admin/users")
    async def admin_users(request: Request):
        actor = await _authorize(request)
        _target_user(request, {}, actor)
        if not bridge.is_admin(actor):
            raise HTTPException(status_code=403, detail="admin role required")
        return response(True, "completed", "Người dùng canonical", data={"items": bridge.admin_users()})

    @router.get("/admin/jobs")
    async def admin_jobs(request: Request):
        actor = await _authorize(request)
        _target_user(request, {}, actor)
        if not bridge.is_admin(actor):
            raise HTTPException(status_code=403, detail="admin role required")
        return response(True, "completed", "Jobs canonical", data={"items": bridge.jobs(actor, admin=True)})

    @router.get("/admin/payments")
    async def admin_payments(request: Request):
        actor = await _authorize(request)
        _target_user(request, {}, actor)
        if not bridge.is_admin(actor):
            raise HTTPException(status_code=403, detail="admin role required")
        return response(True, "completed", "Thanh toán canonical", data={"items": bridge.admin_payments()})

    @router.get("/admin/providers")
    async def admin_providers(request: Request):
        actor = await _authorize(request)
        _target_user(request, {}, actor)
        if not bridge.is_admin(actor):
            raise HTTPException(status_code=403, detail="admin role required")
        return response(True, "completed", "Provider readiness canonical", data={"features": bridge.readiness()})

    @router.get("/admin/tickets")
    async def admin_tickets(request: Request):
        actor = await _authorize(request)
        _target_user(request, {}, actor)
        if not bridge.is_admin(actor):
            raise HTTPException(status_code=403, detail="admin role required")
        return response(True, "completed", "Tickets canonical", data={"items": bridge.tickets(actor, admin=True)})

    @router.get("/admin/modules/{module}")
    async def admin_module(module: str, request: Request):
        actor = await _authorize(request)
        _target_user(request, {}, actor)
        if not bridge.is_admin(actor):
            raise HTTPException(status_code=403, detail="admin role required")
        return response(
            True,
            "read_only",
            "Dữ liệu Admin ERP canonical",
            data=bridge.admin_module(module, record_id=str(request.query_params.get("record_id") or "")),
        )

    @router.post("/admin/jobs/{job_id}/retry")
    async def admin_retry(job_id: str, request: Request):
        actor = await _authorize(request)
        payload = await _payload(request)
        _target_user(request, payload, actor)
        if not bridge.is_admin(actor):
            raise HTTPException(status_code=403, detail="admin role required")
        _validate_idempotency(payload.get("idempotency_key"))
        bridge.audit(actor, "admin.job.retry", getattr(request.state, "bridge_request_id", ""), target=job_id, outcome="guarded", note="requires canonical Telegram action")
        return response(False, "guarded", "Retry phải đi qua action canonical của bot cho đến khi adapter job tương ứng được xác minh.", error_code="CANONICAL_JOB_ACTION_REQUIRED")

    @router.post("/admin/jobs/{job_id}/refund")
    async def admin_refund(job_id: str, request: Request):
        actor = await _authorize(request)
        payload = await _payload(request)
        _target_user(request, payload, actor)
        if not bridge.is_admin(actor):
            raise HTTPException(status_code=403, detail="admin role required")
        _validate_idempotency(payload.get("idempotency_key"))
        bridge.audit(actor, "admin.job.refund", getattr(request.state, "bridge_request_id", ""), target=job_id, outcome="guarded", note="wallet action intentionally delegated to Telegram")
        return response(False, "guarded", "Hoàn Xu phải đi qua workflow canonical của bot để bảo toàn ledger.", error_code="CANONICAL_WALLET_ACTION_REQUIRED")

    @router.post("/admin/features/{feature}/freeze")
    async def admin_freeze(feature: str, request: Request):
        actor = await _authorize(request)
        payload = await _payload(request)
        _target_user(request, payload, actor)
        if not bridge.is_admin(actor):
            raise HTTPException(status_code=403, detail="admin role required")
        _validate_idempotency(payload.get("idempotency_key"))
        bridge.audit(actor, "admin.feature.freeze", getattr(request.state, "bridge_request_id", ""), target=feature, outcome="guarded", note="requires existing bot admin workflow")
        return response(False, "guarded", "Freeze phải đi qua workflow admin canonical của bot cho đến khi adapter được xác minh.", error_code="CANONICAL_ADMIN_ACTION_REQUIRED")

    @router.post("/auth/link/verify")
    async def verify_web_link(request: Request):
        """Bot-side helper: a verified Telegram user can confirm a web code privately."""
        actor = await _authorize(request)
        payload = await _payload(request)
        user_id = _target_user(request, payload, actor)
        result = await confirm_web_link_from_telegram(core, user_id, str(payload.get("code") or ""))
        bridge.audit(user_id, "auth.telegram_link_confirm", getattr(request.state, "bridge_request_id", ""), outcome=result["status"])
        return result

    return router
