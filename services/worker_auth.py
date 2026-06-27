"""Authentication helpers for remote local worker API endpoints."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class WorkerAuthResult:
    ok: bool
    status_code: int = 200
    reason: str = ""


def extract_bearer_token(authorization_header: str = "") -> str:
    value = str(authorization_header or "").strip()
    if not value.lower().startswith("bearer "):
        return ""
    return value.split(" ", 1)[1].strip()


def verify_worker_bearer_token(authorization_header: str, expected_token: str) -> WorkerAuthResult:
    expected = str(expected_token or "").strip()
    if not expected:
        return WorkerAuthResult(False, 503, "worker_token_not_configured")
    provided = extract_bearer_token(authorization_header)
    if not provided:
        return WorkerAuthResult(False, 401, "missing_token")
    if not hmac.compare_digest(provided, expected):
        return WorkerAuthResult(False, 403, "invalid_token")
    return WorkerAuthResult(True)


def worker_api_runtime_flags(local_worker_token: str, remote_mode_supported: bool = True) -> dict:
    configured = bool(str(local_worker_token or "").strip())
    return {
        "worker_api_enabled": configured,
        "local_worker_token_configured": configured,
        "remote_worker_mode_supported": bool(remote_mode_supported),
    }


def worker_auth_security_event(
    *,
    endpoint: str,
    client_host: str = "",
    user_agent: str = "",
    reason: str = "",
    now: datetime | None = None,
) -> dict:
    moment = now or datetime.now(timezone.utc)
    return {
        "endpoint": str(endpoint or "")[:200],
        "ip": str(client_host or "")[:120],
        "user_agent": str(user_agent or "")[:300],
        "time": moment.isoformat(),
        "reason": str(reason or "")[:120],
    }
