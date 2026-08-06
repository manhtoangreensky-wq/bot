"""Durable, audit-only cleanup primitives for canonical Video Edit jobs.

This module owns no Telegram, billing, provider, or FFmpeg behavior.  It keeps
cleanup evidence below the configured Video Edit workspace root and accepts
only server-derived numeric job/claim identities.
"""

from __future__ import annotations

import ctypes
import errno
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, BinaryIO
from ctypes import wintypes


CLEANUP_AUDIT_SCHEMA = "video-edit-cleanup-audit-v1"
CLEANUP_AUDIT_VERSION = 1
PROJECT_CLEANUP_AUDIT_SCHEMA = "video-edit-cleanup-project-audit-v2"
PROJECT_CLEANUP_AUDIT_VERSION = 2
MAX_CLEANUP_ATTEMPTS = 3
SPOOL_DIRECTORY = ".video_edit_cleanup_audit"
ACTIVE_BUCKET = "active"
TOMBSTONE_BUCKET = "tombstones"
ORPHAN_BUCKET = "orphan-retained"
_BUCKETS = frozenset({ACTIVE_BUCKET, TOMBSTONE_BUCKET, ORPHAN_BUCKET})
_REPARSE_POINT = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _strict_positive_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("cleanup_identity_invalid")
    return value


def _delivery_owner(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 120
        or any(ord(char) < 33 or ord(char) > 126 for char in value)
    ):
        raise ValueError("cleanup_owner_invalid")
    return value


def workspace_key(job_id: Any, delivery_claim_attempt: Any) -> str:
    """Return the only valid per-claim workspace/tombstone key."""

    job = _strict_positive_int(job_id)
    attempt = _strict_positive_int(delivery_claim_attempt)
    return f"job_{job}_claim_{attempt}"


def project_workspace_key(job_id: Any) -> str:
    """Return the stable per-job root derived only from server job identity."""

    return f"job_{_strict_positive_int(job_id)}"


def discover_project_workspace(
    workspace_root: str | os.PathLike[str],
    job_id: Any,
) -> Path | None:
    """Return an existing safe stable project without creating any path."""

    key = project_workspace_key(job_id)
    supplied = Path(workspace_root).expanduser()
    if ".." in supplied.parts:
        raise ValueError("cleanup_project_workspace_invalid")
    root = Path(os.path.abspath(supplied))
    if root == Path(root.anchor):
        raise ValueError("cleanup_project_workspace_invalid")

    candidate = Path(root.anchor)
    for part in root.parts[1:]:
        candidate /= part
        if not os.path.lexists(candidate):
            continue
        if _is_reparse_or_link(candidate) or not candidate.is_dir():
            raise ValueError("cleanup_project_workspace_invalid")

    project = root / key
    if not os.path.lexists(project):
        return None
    if _is_reparse_or_link(project) or not project.is_dir():
        raise ValueError("cleanup_project_workspace_invalid")
    return project


def _validate_key(
    key: Any,
    *,
    job_id: Any,
    delivery_claim_attempt: Any,
) -> str:
    expected = workspace_key(job_id, delivery_claim_attempt)
    if not isinstance(key, str) or key != expected:
        raise ValueError("cleanup_key_invalid")
    if any(token in key for token in ("/", "\\", ".")):
        raise ValueError("cleanup_key_invalid")
    return key


def build_cleanup_intent(
    *,
    job_id: Any,
    delivery_claim_attempt: Any,
    delivery_owner: Any,
    workspace_present: Any,
    project_workspace: bool = False,
) -> dict[str, Any]:
    """Build minimal path-free evidence written before terminal persistence."""

    job = _strict_positive_int(job_id)
    attempt = _strict_positive_int(delivery_claim_attempt)
    owner = _delivery_owner(delivery_owner)
    if not isinstance(workspace_present, bool):
        raise ValueError("cleanup_workspace_presence_invalid")
    if not isinstance(project_workspace, bool):
        raise ValueError("cleanup_workspace_scope_invalid")
    key = workspace_key(job, attempt)
    intent = {
        "schema": (
            PROJECT_CLEANUP_AUDIT_SCHEMA
            if project_workspace
            else CLEANUP_AUDIT_SCHEMA
        ),
        "version": (
            PROJECT_CLEANUP_AUDIT_VERSION
            if project_workspace
            else CLEANUP_AUDIT_VERSION
        ),
        "job_id": job,
        "delivery_claim_attempt": attempt,
        "delivery_owner": owner,
        "workspace_key": key,
        "tombstone_key": key,
        "workspace_present": workspace_present,
    }
    if project_workspace:
        intent["target_workspace_key"] = project_workspace_key(job)
    return intent


def normalize_cleanup_intent(value: Any) -> dict[str, Any]:
    legacy_fields = {
        "schema",
        "version",
        "job_id",
        "delivery_claim_attempt",
        "delivery_owner",
        "workspace_key",
        "tombstone_key",
        "workspace_present",
    }
    project_fields = legacy_fields | {"target_workspace_key"}
    if not isinstance(value, dict) or frozenset(value) not in {
        frozenset(legacy_fields),
        frozenset(project_fields),
    }:
        raise ValueError("cleanup_intent_invalid")
    project_workspace = set(value) == project_fields
    expected_schema = (
        PROJECT_CLEANUP_AUDIT_SCHEMA
        if project_workspace
        else CLEANUP_AUDIT_SCHEMA
    )
    expected_version = (
        PROJECT_CLEANUP_AUDIT_VERSION
        if project_workspace
        else CLEANUP_AUDIT_VERSION
    )
    if value.get("schema") != expected_schema or value.get("version") != expected_version:
        raise ValueError("cleanup_intent_invalid")
    normalized = build_cleanup_intent(
        job_id=value.get("job_id"),
        delivery_claim_attempt=value.get("delivery_claim_attempt"),
        delivery_owner=value.get("delivery_owner"),
        workspace_present=value.get("workspace_present"),
        project_workspace=project_workspace,
    )
    if (
        value.get("workspace_key") != normalized["workspace_key"]
        or value.get("tombstone_key") != normalized["tombstone_key"]
        or (
            project_workspace
            and value.get("target_workspace_key")
            != normalized["target_workspace_key"]
        )
    ):
        raise ValueError("cleanup_intent_invalid")
    return normalized


def _is_reparse_or_link(path: Path) -> bool:
    try:
        details = os.lstat(path)
    except FileNotFoundError:
        return False
    return bool(
        stat.S_ISLNK(details.st_mode)
        or int(getattr(details, "st_file_attributes", 0)) & _REPARSE_POINT
    )


def _workspace_root(value: str | os.PathLike[str]) -> Path:
    supplied = Path(value).expanduser()
    if ".." in supplied.parts:
        raise ValueError("cleanup_workspace_root_invalid")
    root = Path(os.path.abspath(supplied))
    if root == Path(root.anchor):
        raise ValueError("cleanup_workspace_root_invalid")

    def validate_existing_ancestors() -> None:
        candidate = Path(root.anchor)
        for part in root.parts[1:]:
            candidate /= part
            if not os.path.lexists(candidate):
                continue
            if _is_reparse_or_link(candidate) or not candidate.is_dir():
                raise ValueError("cleanup_workspace_root_invalid")

    validate_existing_ancestors()
    root.mkdir(parents=True, exist_ok=True)
    validate_existing_ancestors()
    return root


def _spool_directories(
    workspace_root: str | os.PathLike[str],
) -> tuple[Path, Path, Path, Path]:
    root = _workspace_root(workspace_root)
    spool = root / SPOOL_DIRECTORY
    if spool.exists() and (not spool.is_dir() or _is_reparse_or_link(spool)):
        raise ValueError("cleanup_spool_unsafe")
    spool.mkdir(exist_ok=True)
    if _is_reparse_or_link(spool):
        raise ValueError("cleanup_spool_unsafe")
    buckets: list[Path] = []
    for name in (ACTIVE_BUCKET, TOMBSTONE_BUCKET, ORPHAN_BUCKET):
        bucket = spool / name
        if bucket.exists() and (not bucket.is_dir() or _is_reparse_or_link(bucket)):
            raise ValueError("cleanup_spool_unsafe")
        bucket.mkdir(exist_ok=True)
        if _is_reparse_or_link(bucket):
            raise ValueError("cleanup_spool_unsafe")
        buckets.append(bucket)
    return root, buckets[0], buckets[1], buckets[2]


def cleanup_spool_path(
    workspace_root: str | os.PathLike[str],
    *,
    bucket: str,
    key: Any,
    job_id: Any,
    delivery_claim_attempt: Any,
) -> Path:
    if bucket not in _BUCKETS:
        raise ValueError("cleanup_bucket_invalid")
    clean_key = _validate_key(
        key,
        job_id=job_id,
        delivery_claim_attempt=delivery_claim_attempt,
    )
    _root, active, tombstones, orphan = _spool_directories(workspace_root)
    parent = {
        ACTIVE_BUCKET: active,
        TOMBSTONE_BUCKET: tombstones,
        ORPHAN_BUCKET: orphan,
    }[bucket]
    suffix = ".json" if bucket in {ACTIVE_BUCKET, ORPHAN_BUCKET} else ""
    return parent / f"{clean_key}{suffix}"


def _flush_file(handle: BinaryIO) -> None:
    handle.flush()
    os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _durable_replace(source: Path, destination: Path) -> None:
    if os.name == "nt":
        move_file_ex = ctypes.windll.kernel32.MoveFileExW
        move_file_ex.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        move_file_ex.restype = ctypes.c_int
        if not move_file_ex(str(source), str(destination), 0x1 | 0x8):
            raise OSError(ctypes.get_last_error(), "durable replace failed")
        return
    os.replace(source, destination)
    _fsync_directory(destination.parent)


def _durable_move_noreplace(source: Path, destination: Path) -> None:
    """Durably rename one directory while refusing destination replacement."""

    if _present(destination):
        raise FileExistsError(errno.EEXIST, "cleanup destination exists")
    source_parent = source.parent
    destination_parent = destination.parent
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        move_file_ex = kernel32.MoveFileExW
        move_file_ex.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
            ctypes.c_uint,
        ]
        move_file_ex.restype = ctypes.c_int
        if not move_file_ex(str(source), str(destination), 0x8):
            code = ctypes.get_last_error()
            if _present(destination):
                raise FileExistsError(
                    errno.EEXIST,
                    "cleanup destination exists",
                )
            raise OSError(code, "durable no-replace move failed")
        return

    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise OSError(errno.ENOSYS, "atomic no-replace rename unavailable")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        -100,
        os.fsencode(source),
        -100,
        os.fsencode(destination),
        0x1,
    )
    if result != 0:
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            raise FileExistsError(code, "cleanup destination exists")
        raise OSError(code, "durable no-replace move failed")
    _fsync_directory(source_parent)
    if destination_parent != source_parent:
        _fsync_directory(destination_parent)


def write_cleanup_intent(
    workspace_root: str | os.PathLike[str],
    intent: Any,
) -> dict[str, Any]:
    """Best-effort durable write; failures never raise into terminal delivery."""

    temp_path: Path | None = None
    try:
        normalized = normalize_cleanup_intent(intent)
        active_path = cleanup_spool_path(
            workspace_root,
            bucket=ACTIVE_BUCKET,
            key=normalized["workspace_key"],
            job_id=normalized["job_id"],
            delivery_claim_attempt=normalized["delivery_claim_attempt"],
        )
        temp_path = active_path.parent / (
            f".{normalized['workspace_key']}.{secrets.token_hex(8)}.tmp"
        )
        payload = json.dumps(
            normalized,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        with open(temp_path, "xb") as handle:
            handle.write(payload)
            _flush_file(handle)
        _durable_replace(temp_path, active_path)
        temp_path = None
        return {
            "persisted": True,
            "intent_key": active_path.name,
            "workspace_key": normalized["workspace_key"],
            "tombstone_key": normalized["tombstone_key"],
        }
    except Exception as exc:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
        return {
            "persisted": False,
            "reason": f"cleanup_intent_persist_failed:{type(exc).__name__}"[:120],
        }


def load_cleanup_intent(path: str | os.PathLike[str]) -> dict[str, Any]:
    target = Path(path)
    if _is_reparse_or_link(target):
        raise ValueError("cleanup_intent_unsafe")
    try:
        with target.open("rb") as handle:
            raw = handle.read(8 * 1024 + 1)
    except OSError as exc:
        raise ValueError("cleanup_intent_unreadable") from exc
    if not raw or len(raw) > 8 * 1024:
        raise ValueError("cleanup_intent_invalid")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("cleanup_intent_invalid") from exc
    return normalize_cleanup_intent(value)


def list_active_cleanup_intents(
    workspace_root: str | os.PathLike[str],
    *,
    limit: Any = 4,
) -> list[dict[str, Any]]:
    """Return a bounded deterministic set of valid replay intents."""

    bounded = _strict_positive_int(limit)
    if bounded > 64:
        raise ValueError("cleanup_replay_limit_invalid")
    _root, active, _tombstones, _orphan = _spool_directories(workspace_root)
    intents: list[dict[str, Any]] = []
    try:
        candidates = sorted(active.iterdir(), key=lambda item: item.name)
    except OSError:
        return []
    for candidate in candidates:
        if len(intents) >= bounded:
            break
        if candidate.suffix != ".json" or _is_reparse_or_link(candidate):
            continue
        try:
            intent = load_cleanup_intent(candidate)
        except ValueError:
            continue
        if candidate.name != f"{intent['workspace_key']}.json":
            continue
        intents.append(intent)
    return intents


class _CleanupSafetyError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _safe_lstat(path: Path) -> os.stat_result:
    try:
        details = os.lstat(path)
    except FileNotFoundError as exc:
        raise _CleanupSafetyError("cleanup_race_detected") from exc
    if (
        stat.S_ISLNK(details.st_mode)
        or int(getattr(details, "st_file_attributes", 0)) & _REPARSE_POINT
    ):
        raise _CleanupSafetyError("cleanup_unsafe_path")
    return details


def _same_file_identity(path: Path, expected: os.stat_result) -> bool:
    try:
        current = _safe_lstat(path)
    except _CleanupSafetyError:
        return False
    return _stat_identity_matches(current, expected)


def _stat_identity_matches(
    current: os.stat_result,
    expected: os.stat_result,
) -> bool:
    return bool(
        current.st_dev == expected.st_dev
        and current.st_ino == expected.st_ino
        and stat.S_IFMT(current.st_mode) == stat.S_IFMT(expected.st_mode)
        and int(getattr(current, "st_file_attributes", 0))
        == int(getattr(expected, "st_file_attributes", 0))
    )


def _posix_directory_flags() -> int:
    return int(os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)


def _delete_tree_secure_posix_fd(directory_fd: int) -> None:
    try:
        entries = list(os.scandir(directory_fd))
    except OSError as exc:
        raise _CleanupSafetyError("cleanup_scan_failed") from exc
    for entry in entries:
        name = entry.name
        try:
            before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as exc:
            raise _CleanupSafetyError("cleanup_race_detected") from exc
        if stat.S_ISLNK(before.st_mode):
            raise _CleanupSafetyError("cleanup_unsafe_path")
        if stat.S_ISDIR(before.st_mode):
            try:
                child_fd = os.open(
                    name,
                    _posix_directory_flags(),
                    dir_fd=directory_fd,
                )
            except OSError as exc:
                raise _CleanupSafetyError("cleanup_race_detected") from exc
            try:
                if not _stat_identity_matches(os.fstat(child_fd), before):
                    raise _CleanupSafetyError("cleanup_race_detected")
                _delete_tree_secure_posix_fd(child_fd)
                if not _stat_identity_matches(os.fstat(child_fd), before):
                    raise _CleanupSafetyError("cleanup_race_detected")
            finally:
                os.close(child_fd)
            try:
                current = os.stat(
                    name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                if not _stat_identity_matches(current, before):
                    raise _CleanupSafetyError("cleanup_race_detected")
                os.rmdir(name, dir_fd=directory_fd)
            except _CleanupSafetyError:
                raise
            except OSError as exc:
                raise _CleanupSafetyError("cleanup_race_detected") from exc
        elif stat.S_ISREG(before.st_mode):
            try:
                current = os.stat(
                    name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                if not _stat_identity_matches(current, before):
                    raise _CleanupSafetyError("cleanup_race_detected")
                os.unlink(name, dir_fd=directory_fd)
            except _CleanupSafetyError:
                raise
            except OSError as exc:
                raise _CleanupSafetyError("cleanup_race_detected") from exc
        else:
            raise _CleanupSafetyError("cleanup_unsafe_path")


def _delete_tree_secure_posix(path: Path, expected: os.stat_result) -> None:
    parent_fd = os.open(path.parent, _posix_directory_flags())
    try:
        directory_fd = os.open(
            path.name,
            _posix_directory_flags(),
            dir_fd=parent_fd,
        )
        try:
            if not _stat_identity_matches(os.fstat(directory_fd), expected):
                raise _CleanupSafetyError("cleanup_race_detected")
            _delete_tree_secure_posix_fd(directory_fd)
            if not _stat_identity_matches(os.fstat(directory_fd), expected):
                raise _CleanupSafetyError("cleanup_race_detected")
        finally:
            os.close(directory_fd)
        os.rmdir(path.name, dir_fd=parent_fd)
    except _CleanupSafetyError:
        raise
    except OSError as exc:
        raise _CleanupSafetyError("cleanup_race_detected") from exc
    finally:
        os.close(parent_fd)


class _FileDispositionInfo(ctypes.Structure):
    _fields_ = [("DeleteFile", wintypes.BOOL)]


def _windows_kernel32():
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _windows_open_locked(path: Path, *, directory: bool):
    kernel32 = _windows_kernel32()
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    desired_access = 0x00010000 | 0x0080 | (0x0001 if directory else 0)
    flags = 0x00200000 | (0x02000000 if directory else 0)
    handle = create_file(
        str(path),
        desired_access,
        0x00000001,
        None,
        3,
        flags,
        None,
    )
    invalid = ctypes.c_void_p(-1).value
    if ctypes.cast(handle, ctypes.c_void_p).value == invalid:
        raise _CleanupSafetyError("cleanup_race_detected")
    try:
        details = _safe_lstat(path)
        if directory != stat.S_ISDIR(details.st_mode):
            raise _CleanupSafetyError("cleanup_unsafe_path")
    except Exception:
        kernel32.CloseHandle(handle)
        raise
    return kernel32, handle, details


def _windows_mark_delete(kernel32, handle) -> None:
    setter = kernel32.SetFileInformationByHandle
    setter.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    setter.restype = wintypes.BOOL
    disposition = _FileDispositionInfo(True)
    if not setter(
        handle,
        4,
        ctypes.byref(disposition),
        ctypes.sizeof(disposition),
    ):
        raise OSError(ctypes.get_last_error(), "secure delete failed")


def _delete_tree_secure_windows_locked(kernel32, handle, path: Path) -> None:
    try:
        entries = list(os.scandir(path))
    except OSError as exc:
        raise _CleanupSafetyError("cleanup_scan_failed") from exc
    for entry in entries:
        child_path = Path(entry.path)
        before = _safe_lstat(child_path)
        is_directory = stat.S_ISDIR(before.st_mode)
        if not is_directory and not stat.S_ISREG(before.st_mode):
            raise _CleanupSafetyError("cleanup_unsafe_path")
        child_kernel32, child_handle, after = _windows_open_locked(
            child_path,
            directory=is_directory,
        )
        try:
            if not _stat_identity_matches(after, before):
                raise _CleanupSafetyError("cleanup_race_detected")
            if is_directory:
                _delete_tree_secure_windows_locked(
                    child_kernel32,
                    child_handle,
                    child_path,
                )
            _windows_mark_delete(child_kernel32, child_handle)
        finally:
            child_kernel32.CloseHandle(child_handle)
    try:
        if any(True for _entry in os.scandir(path)):
            raise _CleanupSafetyError("cleanup_race_detected")
    except _CleanupSafetyError:
        raise
    except OSError as exc:
        raise _CleanupSafetyError("cleanup_scan_failed") from exc


def _delete_tree_secure_windows_handle(
    path: Path,
    expected: os.stat_result,
) -> None:
    kernel32, handle, current = _windows_open_locked(path, directory=True)
    try:
        if not _stat_identity_matches(current, expected):
            raise _CleanupSafetyError("cleanup_race_detected")
        _delete_tree_secure_windows_locked(kernel32, handle, path)
        _windows_mark_delete(kernel32, handle)
    finally:
        kernel32.CloseHandle(handle)


def _delete_tree_secure_nofollow(
    path: Path,
    expected: os.stat_result,
) -> None:
    if os.name == "nt":
        _delete_tree_secure_windows_handle(path, expected)
        return
    _delete_tree_secure_posix(path, expected)


def _present(path: Path) -> bool:
    return os.path.lexists(path)


def secure_cleanup_workspace(
    workspace_root: str | os.PathLike[str],
    intent: Any,
) -> dict[str, Any]:
    """Rename the exact claim workspace to a tombstone and delete securely."""

    try:
        normalized = normalize_cleanup_intent(intent)
        root, _active_bucket, tombstones, _orphan = _spool_directories(
            workspace_root
        )
        active_workspace = root / normalized.get(
            "target_workspace_key",
            normalized["workspace_key"],
        )
        tombstone = tombstones / normalized["tombstone_key"]
        active_present = _present(active_workspace)
        tombstone_present = _present(tombstone)
        if active_present and tombstone_present:
            return {
                "ok": False,
                "outcome": "failed_retryable",
                "reason": "cleanup_active_and_tombstone_present",
            }
        if not active_present and not tombstone_present:
            return {
                "ok": True,
                "outcome": "already_absent",
                "removed": False,
            }
        if active_present:
            active_identity = _safe_lstat(active_workspace)
            if not stat.S_ISDIR(active_identity.st_mode):
                raise _CleanupSafetyError("cleanup_unsafe_path")
            if not _same_file_identity(active_workspace, active_identity):
                raise _CleanupSafetyError("cleanup_race_detected")
            try:
                _durable_move_noreplace(active_workspace, tombstone)
            except FileExistsError:
                return {
                    "ok": False,
                    "outcome": "failed_retryable",
                    "reason": "cleanup_destination_exists",
                }
            if not _same_file_identity(tombstone, active_identity):
                raise _CleanupSafetyError("cleanup_race_detected")
        tombstone_identity = _safe_lstat(tombstone)
        if not stat.S_ISDIR(tombstone_identity.st_mode):
            raise _CleanupSafetyError("cleanup_unsafe_path")
        _delete_tree_secure_nofollow(tombstone, tombstone_identity)
        _fsync_directory(tombstones)
        return {"ok": True, "outcome": "succeeded", "removed": True}
    except _CleanupSafetyError as exc:
        return {
            "ok": False,
            "outcome": "failed_retryable",
            "reason": exc.reason[:120],
        }
    except Exception as exc:
        return {
            "ok": False,
            "outcome": "failed_retryable",
            "reason": f"cleanup_failed:{type(exc).__name__}"[:120],
        }


def _active_intent_path(
    workspace_root: str | os.PathLike[str],
    intent: dict[str, Any],
) -> Path:
    return cleanup_spool_path(
        workspace_root,
        bucket=ACTIVE_BUCKET,
        key=intent["workspace_key"],
        job_id=intent["job_id"],
        delivery_claim_attempt=intent["delivery_claim_attempt"],
    )


def retain_orphan_intent(
    workspace_root: str | os.PathLike[str],
    intent: Any,
) -> dict[str, Any]:
    """Move an unverifiable intent aside without authorizing any deletion."""

    try:
        normalized = normalize_cleanup_intent(intent)
        source = _active_intent_path(workspace_root, normalized)
        destination = cleanup_spool_path(
            workspace_root,
            bucket=ORPHAN_BUCKET,
            key=normalized["workspace_key"],
            job_id=normalized["job_id"],
            delivery_claim_attempt=normalized["delivery_claim_attempt"],
        )
        source_present = _present(source)
        destination_present = _present(destination)
        if source_present and destination_present:
            return {
                "ok": False,
                "outcome": "failed_retryable",
                "reason": "cleanup_active_and_orphan_present",
            }
        if source_present:
            if _is_reparse_or_link(source) or not source.is_file():
                raise _CleanupSafetyError("cleanup_intent_unsafe")
            _durable_replace(source, destination)
        elif not destination_present:
            return {
                "ok": False,
                "outcome": "failed_retryable",
                "reason": "cleanup_intent_missing",
            }
        load_cleanup_intent(destination)
        return {"ok": True, "outcome": "orphan_retained"}
    except _CleanupSafetyError as exc:
        return {
            "ok": False,
            "outcome": "failed_retryable",
            "reason": exc.reason[:120],
        }
    except Exception as exc:
        return {
            "ok": False,
            "outcome": "failed_retryable",
            "reason": f"cleanup_orphan_move_failed:{type(exc).__name__}"[:120],
        }


def remove_active_intent(
    workspace_root: str | os.PathLike[str],
    intent: Any,
) -> dict[str, Any]:
    """Remove only the active intent after the canonical audit ACK succeeds."""

    try:
        normalized = normalize_cleanup_intent(intent)
        target = _active_intent_path(workspace_root, normalized)
        if not _present(target):
            return {"ok": True, "removed": False}
        details = _safe_lstat(target)
        if not stat.S_ISREG(details.st_mode) or not _same_file_identity(
            target, details
        ):
            raise _CleanupSafetyError("cleanup_intent_unsafe")
        target.unlink()
        _fsync_directory(target.parent)
        return {"ok": True, "removed": True}
    except _CleanupSafetyError as exc:
        return {"ok": False, "removed": False, "reason": exc.reason[:120]}
    except Exception as exc:
        return {
            "ok": False,
            "removed": False,
            "reason": f"cleanup_intent_remove_failed:{type(exc).__name__}"[:120],
        }
