"""Dedicated draft state for the public AI Video Edit UI.

The store reuses the proven JSON/CAS persistence primitive but writes beneath
its own namespace.  It never creates a job, calls a provider, or mutates Xu.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import threading
from typing import Any

from services import video_edit_state_store


PRODUCT_ID = "video_ai_edit"
DEFAULT_QUALITY = "360p"
MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_SOURCE_DURATION_SECONDS = 30.0
MAX_SOURCE_DIMENSION = 1920
PREUPLOAD_PHASE = "preupload"
DRAFT_PHASE = "draft"
_MEMORY: dict[int, dict[str, Any]] = {}
_LOCK = threading.RLock()
_ALLOWED_UPDATES = frozenset({
    "current_screen",
    "origin_category",
    "origin_page",
    "origin_capability",
    "ai_edit_selected",
    "ai_edit_details",
    "ai_edit_references",
    "quality",
    "pending_input",
    "summary_return",
})


def _new_callback_token() -> str:
    """Return a compact opaque token that fits Telegram callback limits."""

    return secrets.token_hex(4)


def _uid(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("ai_edit_owner_invalid")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("ai_edit_owner_invalid") from exc
    if result <= 0:
        raise ValueError("ai_edit_owner_invalid")
    return result


def _chat_id(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("ai_edit_chat_invalid")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("ai_edit_chat_invalid") from exc
    if result == 0:
        raise ValueError("ai_edit_chat_invalid")
    return result


def _clone(value: dict[str, Any] | None) -> dict[str, Any]:
    return json.loads(json.dumps(dict(value or {}), ensure_ascii=False))


def _memory_only() -> bool:
    configured = str(os.getenv("VIDEO_AI_EDIT_STATE_MEMORY_ONLY") or "").strip().lower()
    return configured in {"1", "true", "yes", "on"} or "PYTEST_CURRENT_TEST" in os.environ


def _state_root(root: str | os.PathLike[str] | None = None) -> Path:
    if root is not None:
        return Path(root)
    return video_edit_state_store.state_root() / "ai_edit"


def source_admission(source: dict[str, Any] | None, metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Public UI admission only; it does not imply provider availability."""

    source_data = dict(source or {})
    metadata_data = dict(metadata or {})
    suffix = Path(str(source_data.get("file_name") or "")).suffix.lower()
    if suffix not in {".mp4", ".mov"}:
        return {"ok": False, "reason": "ai_edit_source_format"}
    if not metadata_data.get("ok") or not metadata_data.get("has_video", False):
        return {"ok": False, "reason": "ai_edit_source_invalid"}
    try:
        size = int(source_data.get("file_size") or metadata_data.get("bytes") or 0)
        duration = float(metadata_data.get("duration") or 0)
        width = int(metadata_data.get("width") or 0)
        height = int(metadata_data.get("height") or 0)
    except (TypeError, ValueError, OverflowError):
        return {"ok": False, "reason": "ai_edit_source_invalid"}
    if size <= 0 or size > MAX_SOURCE_BYTES:
        return {"ok": False, "reason": "ai_edit_source_size"}
    if duration <= 0 or duration > MAX_SOURCE_DURATION_SECONDS:
        return {"ok": False, "reason": "ai_edit_source_duration"}
    if width <= 0 or height <= 0 or max(width, height) > MAX_SOURCE_DIMENSION:
        return {"ok": False, "reason": "ai_edit_source_dimensions"}
    return {"ok": True, "reason": ""}


def load_draft(
    user_id: Any,
    *,
    root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    uid = _uid(user_id)
    if _memory_only() and root is None:
        with _LOCK:
            return _clone(_MEMORY.get(uid))
    return video_edit_state_store.load_state(uid, root=_state_root(root))


def _save_draft(
    user_id: Any,
    state: dict[str, Any],
    *,
    root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    uid = _uid(user_id)
    clean = _clone(state)
    if str(clean.get("product_id") or "") != PRODUCT_ID:
        raise ValueError("ai_edit_product_invalid")
    if str(clean.get("user_id") or "") != str(uid):
        raise ValueError("ai_edit_owner_invalid")
    _chat_id(clean.get("chat_id"))
    if not str(clean.get("draft_id") or "").strip():
        raise ValueError("ai_edit_draft_invalid")
    if _memory_only() and root is None:
        with _LOCK:
            _MEMORY[uid] = clean
        return _clone(clean)
    return video_edit_state_store.save_state(uid, clean, root=_state_root(root))


def clear_draft(
    user_id: Any,
    *,
    root: str | os.PathLike[str] | None = None,
) -> bool:
    uid = _uid(user_id)
    if _memory_only() and root is None:
        with _LOCK:
            return _MEMORY.pop(uid, None) is not None
    return video_edit_state_store.delete_state(uid, root=_state_root(root))


def start_preupload(
    *,
    user_id: Any,
    chat_id: Any,
    draft_id: str,
    root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Create the AI650-owned source-intake state without Video Edit pending."""

    uid = _uid(user_id)
    cid = _chat_id(chat_id)
    clean_draft_id = str(draft_id or "").strip()
    if not clean_draft_id:
        raise ValueError("ai_edit_draft_invalid")
    state = {
        "product_id": PRODUCT_ID,
        "user_id": str(uid),
        "chat_id": str(cid),
        "draft_id": clean_draft_id,
        "callback_token": _new_callback_token(),
        "revision": 1,
        "phase": PREUPLOAD_PHASE,
        "current_screen": "ai650_upload",
        "source": {},
        "source_metadata": {},
        "ai_edit_selected": [],
        "ai_edit_details": {},
        "ai_edit_references": {},
        "quality": DEFAULT_QUALITY,
        "pending_input": {},
        "summary_return": {},
    }
    return _save_draft(uid, state, root=root)


def callback_identity_matches(
    state: dict[str, Any] | None,
    *,
    user_id: Any,
    chat_id: Any,
    callback_token: Any,
    revision: Any,
    phases: tuple[str, ...] = (DRAFT_PHASE,),
) -> bool:
    """Validate one callback against the exact owned AI650 state generation."""

    current = dict(state or {})
    try:
        uid = _uid(user_id)
        cid = _chat_id(chat_id)
        expected_revision = int(revision)
    except (TypeError, ValueError, OverflowError):
        return False
    return bool(
        str(current.get("product_id") or "") == PRODUCT_ID
        and str(current.get("user_id") or "") == str(uid)
        and str(current.get("chat_id") or "") == str(cid)
        and str(current.get("phase") or "") in set(phases)
        and secrets.compare_digest(
            str(current.get("callback_token") or ""),
            str(callback_token or ""),
        )
        and int(current.get("revision") or 0) == expected_revision
    )


def replace_source_draft(
    *,
    user_id: Any,
    chat_id: Any,
    draft_id: str,
    source: dict[str, Any],
    metadata: dict[str, Any],
    expected_callback_token: str | None = None,
    expected_revision: int | None = None,
    root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    uid = _uid(user_id)
    cid = _chat_id(chat_id)
    source_data = _clone(source)
    source_fingerprint = str(source_data.get("fingerprint") or "").strip().lower()
    if len(source_fingerprint) != 64 or any(char not in "0123456789abcdef" for char in source_fingerprint):
        raise ValueError("ai_edit_source_fingerprint_invalid")
    if not str(source_data.get("file_id") or "").strip():
        raise ValueError("ai_edit_source_invalid")
    metadata_data = _clone(metadata)
    if not metadata_data.get("ok") or not metadata_data.get("has_video", True):
        raise ValueError("ai_edit_source_invalid")
    current = load_draft(uid, root=root)
    if expected_callback_token is not None or expected_revision is not None:
        if not callback_identity_matches(
            current,
            user_id=uid,
            chat_id=cid,
            callback_token=expected_callback_token,
            revision=expected_revision,
            phases=(PREUPLOAD_PHASE,),
        ):
            raise ValueError("ai_edit_preupload_stale")
    if current and str(current.get("product_id") or "") == PRODUCT_ID:
        if str(current.get("user_id") or "") != str(uid) or str(current.get("chat_id") or "") != str(cid):
            raise ValueError("ai_edit_owner_invalid")
        resolved_draft_id = str(current.get("draft_id") or "").strip()
        callback_token = str(current.get("callback_token") or "").strip()
        revision = int(current.get("revision") or 0) + 1
    else:
        resolved_draft_id = str(draft_id or "").strip()
        callback_token = _new_callback_token()
        revision = 1
    if not resolved_draft_id:
        raise ValueError("ai_edit_draft_invalid")
    if not callback_token:
        callback_token = _new_callback_token()
    state = {
        "product_id": PRODUCT_ID,
        "user_id": str(uid),
        "chat_id": str(cid),
        "draft_id": resolved_draft_id,
        "callback_token": callback_token,
        "revision": revision,
        "phase": DRAFT_PHASE,
        "current_screen": "ai650_source_summary",
        "source": source_data,
        "source_metadata": metadata_data,
        "ai_edit_selected": [],
        "ai_edit_details": {},
        "ai_edit_references": {},
        "quality": DEFAULT_QUALITY,
        "pending_input": {},
        "summary_return": {},
    }
    return _save_draft(uid, state, root=root)


def update_draft(
    user_id: Any,
    *,
    expected_revision: int | None = None,
    root: str | os.PathLike[str] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    unknown = set(fields) - _ALLOWED_UPDATES
    if unknown:
        raise ValueError("ai_edit_state_field_invalid")
    uid = _uid(user_id)
    current = load_draft(uid, root=root)
    if not current:
        raise ValueError("ai_edit_draft_missing")
    revision = int(current.get("revision") or 0)
    if expected_revision is not None and int(expected_revision) != revision:
        raise ValueError("ai_edit_draft_stale")
    replacement = _clone(current)
    replacement.update(_clone(fields))
    replacement["revision"] = revision + 1
    if _memory_only() and root is None:
        with _LOCK:
            winner = _MEMORY.get(uid)
            if _clone(winner) != current:
                raise ValueError("ai_edit_draft_stale")
            _MEMORY[uid] = replacement
        return _clone(replacement)
    swapped, winner = video_edit_state_store.compare_and_swap_state(
        uid,
        expected_state=current,
        replacement_state=replacement,
        root=_state_root(root),
    )
    if not swapped:
        raise ValueError("ai_edit_draft_stale")
    return winner


def owned_draft(user_id: Any, chat_id: Any) -> dict[str, Any]:
    draft = load_draft(user_id)
    if not draft or str(draft.get("chat_id") or "") != str(_chat_id(chat_id)):
        return {}
    return draft


__all__ = [
    "DEFAULT_QUALITY",
    "PRODUCT_ID",
    "clear_draft",
    "load_draft",
    "owned_draft",
    "replace_source_draft",
    "source_admission",
    "update_draft",
]
