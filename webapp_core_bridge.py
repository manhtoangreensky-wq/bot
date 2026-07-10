"""Private COPYFAST bridge mounted by ``bot.py``.

The bridge is deliberately a small adapter around existing bot state.  It
never owns a wallet, payment webhook, or provider credential.  Browser traffic
must go through the standalone Web App; this router only accepts an HMAC signed
server-to-server request from that application.
"""

from __future__ import annotations

import asyncio
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
_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")
_JOB_ID_PATTERN = re.compile(r"^([a-z_]+):(\d+)$")
_WEB_LINK_CODE_PATTERN = re.compile(r"^[A-Za-z0-9]{8,128}$")
_rate_windows: dict[str, deque[float]] = defaultdict(deque)
_request_nonces: dict[str, float] = {}


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


def _safe_text(value: Any, limit: int = 300) -> str:
    return str(value or "").replace("\n", " ").replace("\r", " ")[:limit]


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
    # Draft/estimate deliberately remain open for guarded public features. They never call a provider.
    message = "Bản nháp đã sẵn sàng để xem xét." if action == "draft" else "Ước tính sẽ được xác nhận bởi core trước khi chạy."
    status_name = "draft" if action == "draft" else "awaiting_confirm"
    return response(True, status_name, message, data={
        "feature": feature,
        "readiness": readiness,
        "input_accepted": bool(input_data),
        "requires_confirm": True,
        "provider_called": False,
    })


async def _feature_confirm(bridge: BotCoreBridge, feature: str, user_id: str, payload: dict, request: Request) -> dict:
    key = _validate_idempotency(payload.get("idempotency_key"))
    scope = f"feature:{user_id}:{feature}:confirm"
    if existing := bridge.idempotency_get(scope, key):
        return existing
    readiness = _feature_readiness(bridge, feature)
    if not _bool_env("WEBAPP_PROVIDER_CALLS_ENABLED", False):
        result = response(False, "guarded", "Tính năng đang ở chế độ an toàn và chưa gọi engine từ Web.", data={"feature": feature, "readiness": readiness}, error_code="WEBAPP_PROVIDER_CALLS_DISABLED")
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
    input_data = payload.get("input") if isinstance(payload.get("input"), dict) else {}
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
    if not callback_url or not callback_token:
        return response(False, "guarded", "Liên kết Telegram chưa được cấu hình ở private bridge.", error_code="TELEGRAM_LINK_CALLBACK_NOT_CONFIGURED")
    bridge = BotCoreBridge(core)
    identity = bridge.identity(user_id)
    if not identity:
        return response(False, "failed", "Không tìm thấy tài khoản Telegram canonical.", error_code="USER_NOT_FOUND")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            result = await client.post(
                callback_url,
                headers={"X-TOAN-AAS-BRIDGE-TOKEN": callback_token},
                json={"code": code, "canonical_user_id": str(user_id), "role": identity["role"], "display_name": identity["username"]},
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
