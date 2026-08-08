"""Small durable store for an in-progress local Video Edit session.

The Telegram editor used to keep its complete source inspection and current
input owner only in process memory.  A worker restart could therefore release
the next text message to unrelated chat handlers.  This module persists the
already-sanitized editor state beside the configured SQLite database without
creating a table or changing any billing/job schema.
"""

from __future__ import annotations

from contextlib import contextmanager
import errno
import json
import math
import os
from pathlib import Path
import stat
import threading
import time
from typing import Any


STATE_VERSION = 1
DEFAULT_TTL_SECONDS = 30 * 60
MAX_STATE_BYTES = 2 * 1024 * 1024
_LOCK = threading.RLock()
_LOCK_TIMEOUT_SECONDS = 10.0


def _positive_user_id(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("video_editor_state_user_invalid")
    try:
        user_id = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("video_editor_state_user_invalid") from exc
    if user_id <= 0:
        raise ValueError("video_editor_state_user_invalid")
    return user_id


def state_root(root: str | os.PathLike[str] | None = None) -> Path:
    configured = str(root or os.getenv("VIDEO_EDITOR_STATE_DIR") or "").strip()
    if configured:
        return Path(os.path.abspath(os.path.expanduser(configured)))
    db_path = str(
        os.getenv("DB_PATH")
        or os.getenv("DB_FILE")
        or "toandaas_system.db"
    ).strip()
    return (
        Path(os.path.abspath(os.path.expanduser(db_path))).parent
        / "video_editor_sessions"
    )


def state_path(
    user_id: Any,
    *,
    root: str | os.PathLike[str] | None = None,
) -> Path:
    return state_root(root) / f"user-{_positive_user_id(user_id)}.json"


def _delete_path(path: Path) -> bool:
    try:
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        return not path.exists() and not path.is_symlink()
    except OSError:
        return False


def _lock_handle(handle) -> None:
    handle.seek(0, os.SEEK_END)
    if handle.tell() <= 0:
        handle.write(b"\0")
        handle.flush()
        os.fsync(handle.fileno())
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
        while True:
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError as exc:
                if exc.errno != errno.EACCES:
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError("video_editor_state_lock_timeout")
                time.sleep(0.01)
    else:
        import fcntl

        deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(
                    handle.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
                return
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError("video_editor_state_lock_timeout")
                time.sleep(0.01)


def _unlock_handle(handle) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _state_file_lock(path: Path):
    parent = path.parent

    def validated_root_identity(*, create: bool) -> tuple[int, int]:
        lexical = os.path.normcase(os.path.abspath(str(parent)))
        resolved = os.path.normcase(os.path.realpath(str(parent)))
        if lexical != resolved:
            raise OSError("video_editor_state_root_symlink")
        if create:
            parent.mkdir(parents=True, exist_ok=True)
            resolved = os.path.normcase(os.path.realpath(str(parent)))
            if lexical != resolved:
                raise OSError("video_editor_state_root_symlink")
        try:
            metadata = parent.stat()
        except OSError:
            raise
        if not stat.S_ISDIR(metadata.st_mode) or parent.is_symlink():
            raise OSError("video_editor_state_root_symlink")
        return int(metadata.st_dev), int(metadata.st_ino)

    root_identity = validated_root_identity(create=True)
    if parent.is_symlink():
        raise OSError("video_editor_state_root_symlink")
    # One stable lock inode protects every state file.  Keeping it independent
    # from the replaceable per-user JSON prevents split-lock races and avoids
    # leaving one lock artifact for every Telegram user who is not editing.
    lock_path = parent / ".video-editor-state.lock"
    if lock_path.is_symlink():
        raise OSError("video_editor_state_lock_symlink")
    lock_acquired = _LOCK.acquire(timeout=_LOCK_TIMEOUT_SECONDS)
    if not lock_acquired:
        raise TimeoutError("video_editor_state_lock_timeout")
    try:
        if validated_root_identity(create=False) != root_identity:
            raise OSError("video_editor_state_root_changed")
        with lock_path.open("a+b") as handle:
            try:
                os.chmod(lock_path, 0o600)
            except OSError:
                pass
            _lock_handle(handle)
            try:
                if validated_root_identity(create=False) != root_identity:
                    raise OSError("video_editor_state_root_changed")
                yield
            finally:
                _unlock_handle(handle)
    finally:
        _LOCK.release()


def _clean_state(state: dict[str, Any]) -> dict[str, Any]:
    if type(state) is not dict or not state:
        raise ValueError("video_editor_state_invalid")
    return json.loads(json.dumps(state, ensure_ascii=False))


def _encoded_envelope(
    uid: int,
    state: dict[str, Any],
    *,
    ttl_seconds: int,
    now: float | None,
) -> tuple[dict[str, Any], bytes]:
    ttl = int(ttl_seconds or 0)
    if ttl <= 0:
        raise ValueError("video_editor_state_ttl_invalid")
    saved_at = float(time.time() if now is None else now)
    if not math.isfinite(saved_at):
        raise ValueError("video_editor_state_time_invalid")
    clean_state = _clean_state(state)
    envelope = {
        "version": STATE_VERSION,
        "user_id": str(uid),
        "saved_at": saved_at,
        "expires_at": saved_at + ttl,
        "state": clean_state,
    }
    encoded = json.dumps(
        envelope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > MAX_STATE_BYTES:
        raise ValueError("video_editor_state_too_large")
    return clean_state, encoded


def _write_encoded(path: Path, encoded: bytes) -> None:
    parent = path.parent
    temp = parent / (
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        with temp.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        os.replace(temp, path)
    finally:
        _delete_path(temp)


def _load_state_unlocked(
    path: Path,
    uid: int,
    *,
    now: float | None,
) -> dict[str, Any]:
    current_time = float(time.time() if now is None else now)
    if not math.isfinite(current_time):
        raise ValueError("video_editor_state_time_invalid")
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {}
    except OSError:
        raise
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        if not _delete_path(path):
            raise OSError("video_editor_state_invalid_delete_failed")
        return {}
    size = int(metadata.st_size)
    if size <= 0 or size > MAX_STATE_BYTES:
        if not _delete_path(path):
            raise OSError("video_editor_state_invalid_delete_failed")
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        raise
    except UnicodeError:
        if not _delete_path(path):
            raise OSError("video_editor_state_invalid_delete_failed")
        return {}
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        if not _delete_path(path):
            raise OSError("video_editor_state_invalid_delete_failed")
        return {}
    if (
        type(envelope) is not dict
        or envelope.get("version") != STATE_VERSION
        or str(envelope.get("user_id") or "") != str(uid)
    ):
        if not _delete_path(path):
            raise OSError("video_editor_state_invalid_delete_failed")
        return {}
    try:
        expires_at = float(envelope.get("expires_at") or 0)
    except (TypeError, ValueError, OverflowError):
        expires_at = 0
    state = envelope.get("state")
    if (
        not math.isfinite(expires_at)
        or expires_at <= current_time
        or type(state) is not dict
        or not state
    ):
        if not _delete_path(path):
            raise OSError("video_editor_state_invalid_delete_failed")
        return {}
    return json.loads(json.dumps(state, ensure_ascii=False))


def save_state(
    user_id: Any,
    state: dict[str, Any],
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    root: str | os.PathLike[str] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    uid = _positive_user_id(user_id)
    path = state_path(uid, root=root)
    clean_state, encoded = _encoded_envelope(
        uid,
        state,
        ttl_seconds=ttl_seconds,
        now=now,
    )
    with _state_file_lock(path):
        _write_encoded(path, encoded)
    return clean_state


def load_state(
    user_id: Any,
    *,
    root: str | os.PathLike[str] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    uid = _positive_user_id(user_id)
    path = state_path(uid, root=root)
    with _state_file_lock(path):
        return _load_state_unlocked(path, uid, now=now)


def compare_and_swap_state(
    user_id: Any,
    *,
    expected_state: dict[str, Any],
    replacement_state: dict[str, Any] | None,
    expected_exists: bool = True,
    replacement_exists: bool = True,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    root: str | os.PathLike[str] | None = None,
    now: float | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Atomically replace one exact durable state across bot processes."""

    uid = _positive_user_id(user_id)
    expected = (
        _clean_state(expected_state)
        if expected_exists
        else {}
    )
    clean_replacement: dict[str, Any] = {}
    encoded = b""
    if replacement_exists:
        clean_replacement, encoded = _encoded_envelope(
            uid,
            dict(replacement_state or {}),
            ttl_seconds=ttl_seconds,
            now=now,
        )
    path = state_path(uid, root=root)
    with _state_file_lock(path):
        current = _load_state_unlocked(path, uid, now=now)
        current_exists = bool(current)
        if current_exists != bool(expected_exists) or current != expected:
            return False, current
        if replacement_exists:
            _write_encoded(path, encoded)
            return True, clean_replacement
        if current_exists and not _delete_path(path):
            raise OSError("video_editor_state_delete_failed")
        return True, {}


def delete_state(
    user_id: Any,
    *,
    root: str | os.PathLike[str] | None = None,
) -> bool:
    path = state_path(user_id, root=root)
    with _state_file_lock(path):
        existed = path.is_file() or path.is_symlink()
        if existed and not _delete_path(path):
            raise OSError("video_editor_state_delete_failed")
        return existed
