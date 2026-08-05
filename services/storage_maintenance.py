"""Backend-local storage maintenance with preview-first deletion.

The module deliberately owns only filesystem cleanup. It never opens an SSH
connection, calls an HTTP endpoint, or delegates deletion to a shell command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator, Mapping
from zoneinfo import ZoneInfo


RAILWAY = "railway"
VPS = "vps"
TIMEZONE = "Asia/Ho_Chi_Minh"
DEFAULT_TEMP_TTL_SECONDS = 12 * 3600
DEFAULT_CACHE_TTL_SECONDS = 24 * 3600
DEFAULT_PARTIAL_TTL_SECONDS = 2 * 3600
DEFAULT_FAILED_JOB_GRACE_SECONDS = 2 * 3600
DEFAULT_KEEP_BACKUPS = 3
BACKUP_NAME_RE = re.compile(
    r"^(?P<lineage>toan(?:aas|daas)_system)_(?P<stamp>\d{8}_\d{6})"
    r"(?:_(?P<label>[A-Za-z0-9-]+))?\.(?P<extension>db|sqlite|sqlite3)$",
    re.IGNORECASE,
)
ZIP_BACKUP_RE = re.compile(
    r"^(?P<lineage>toan(?:aas|daas)_system)_(?P<stamp>\d{8}_\d{6})"
    r"(?:_(?P<label>[A-Za-z0-9-]+))?\.(?P<extension>zip)$",
    re.IGNORECASE,
)
TEMP_DIR_NAMES = (
    "tmp",
    "cache",
    "workspaces",
    "worker_results",
    "artifacts",
    "music",
    "subdub",
    "video",
    "voice_assets",
    "subtitle_assets",
    "translation_assets",
    "dub_assets",
)
PROTECTED_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".db-wal",
    ".db-shm",
    ".env",
    ".pem",
    ".key",
}
PROTECTED_NAME_PARTS = {
    "payment",
    "payos",
    "wallet",
    "ledger",
    "finance",
    "secret",
    "token",
    "config",
    "source",
}
PARTIAL_SUFFIXES = {".part", ".partial", ".tmp", ".download", ".failed"}


def _abs(path: str | os.PathLike[str]) -> Path:
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _same_or_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _same_path(left: Path, right: Path) -> bool:
    return _abs(left) == _abs(right)


def _safe_json_value(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    return value


@dataclass
class StorageConfig:
    backend: str
    storage_root: str | os.PathLike[str]
    backup_root: str | os.PathLike[str] | None = None
    live_db: str | os.PathLike[str] | None = None
    railway_root: str | os.PathLike[str] | None = None
    vps_root: str | os.PathLike[str] | None = None
    protected_paths: tuple[str, ...] = ()
    running_paths: tuple[str, ...] = ()
    undelivered_paths: tuple[str, ...] = ()
    extra_temp_roots: tuple[str, ...] = ()
    temp_ttl_seconds: int = DEFAULT_TEMP_TTL_SECONDS
    cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS
    partial_ttl_seconds: int = DEFAULT_PARTIAL_TTL_SECONDS
    failed_job_grace_seconds: int = DEFAULT_FAILED_JOB_GRACE_SECONDS
    max_scan_files: int = 10000
    max_delete_files: int = 500
    timezone_name: str = TIMEZONE

    def __post_init__(self) -> None:
        self.backend = str(self.backend or "").strip().lower()
        self.storage_root = _abs(self.storage_root)
        self.backup_root = _abs(self.backup_root or Path(self.storage_root) / "backups")
        self.live_db = _abs(self.live_db) if self.live_db else None
        self.railway_root = _abs(self.railway_root) if self.railway_root else None
        self.vps_root = _abs(self.vps_root) if self.vps_root else None
        self.protected_paths = tuple(str(_abs(item)) for item in self.protected_paths if str(item).strip())
        self.running_paths = tuple(str(_abs(item)) for item in self.running_paths if str(item).strip())
        self.undelivered_paths = tuple(str(_abs(item)) for item in self.undelivered_paths if str(item).strip())
        self.extra_temp_roots = tuple(str(_abs(item)) for item in self.extra_temp_roots if str(item).strip())
        self.temp_ttl_seconds = max(1, int(self.temp_ttl_seconds))
        self.cache_ttl_seconds = max(1, int(self.cache_ttl_seconds))
        self.partial_ttl_seconds = max(1, int(self.partial_ttl_seconds))
        self.failed_job_grace_seconds = max(1, int(self.failed_job_grace_seconds))
        self.max_scan_files = max(1, int(self.max_scan_files))
        self.max_delete_files = max(1, int(self.max_delete_files))

    @property
    def lock_path(self) -> Path:
        return self.storage_root / f".toanaas-storage-{self.backend}.lock"

    @property
    def state_path(self) -> Path:
        return self.storage_root / f".toanaas-storage-{self.backend}-state.json"


def _env_int(env: Mapping[str, str], name: str, default: int) -> int:
    try:
        return int(str(env.get(name, default)).strip())
    except (TypeError, ValueError):
        return default


def _env_paths(env: Mapping[str, str], name: str) -> tuple[str, ...]:
    raw = str(env.get(name, "") or "")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def config_from_env(backend: str | None = None, env: Mapping[str, str] | None = None) -> StorageConfig:
    values = env or os.environ
    selected = str(backend or values.get("TOANAAS_STORAGE_BACKEND") or "railway").strip().lower()
    if selected not in {RAILWAY, VPS}:
        raise ValueError("unsupported_backend")
    railway_root = str(values.get("STORAGE_RAILWAY_ROOT") or values.get("RAILWAY_STORAGE_ROOT") or "/data")
    vps_root = str(values.get("STORAGE_VPS_ROOT") or values.get("ARTIFACT_VPS_BASE_DIR") or "/opt/toanaas-storage")
    root = railway_root if selected == RAILWAY else vps_root
    backup = (
        values.get("STORAGE_RAILWAY_BACKUP_ROOT")
        or values.get("DB_BACKUP_DIR")
        if selected == RAILWAY
        else values.get("STORAGE_VPS_BACKUP_ROOT")
    ) or str(Path(root) / "backups")
    live_db = values.get("DB_PATH") or values.get("DB_FILE") if selected == RAILWAY else values.get("STORAGE_VPS_LIVE_DB")
    return StorageConfig(
        backend=selected,
        storage_root=root,
        backup_root=backup,
        live_db=live_db,
        railway_root=railway_root,
        vps_root=vps_root,
        protected_paths=_env_paths(values, "STORAGE_PROTECTED_PATHS"),
        running_paths=_env_paths(values, "STORAGE_RUNNING_PATHS"),
        undelivered_paths=_env_paths(values, "STORAGE_UNDELIVERED_PATHS"),
        extra_temp_roots=_env_paths(values, "STORAGE_EXTRA_TEMP_ROOTS"),
        temp_ttl_seconds=_env_int(values, "TEMP_ORPHAN_TTL_HOURS", 12) * 3600,
        cache_ttl_seconds=_env_int(values, "CACHE_TTL_HOURS", 24) * 3600,
        partial_ttl_seconds=_env_int(values, "PARTIAL_FILE_TTL_HOURS", 2) * 3600,
        failed_job_grace_seconds=_env_int(values, "FAILED_JOB_TEMP_GRACE_HOURS", 2) * 3600,
        max_scan_files=_env_int(values, "STORAGE_CLEANUP_MAX_SCAN_FILES", 10000),
        max_delete_files=_env_int(values, "STORAGE_CLEANUP_MAX_DELETE_FILES", 500),
        timezone_name=str(values.get("STORAGE_MAINTENANCE_TIMEZONE") or TIMEZONE),
    )


def _validate_config(config: StorageConfig) -> list[str]:
    errors: list[str] = []
    if config.backend not in {RAILWAY, VPS}:
        errors.append("unsupported_backend")
    root = _abs(config.storage_root)
    if root == Path(root.anchor or os.path.sep):
        errors.append("storage_root_is_filesystem_root")
    if config.backend == RAILWAY and config.vps_root and _same_or_under(root, _abs(config.vps_root)):
        errors.append("railway_root_matches_vps_root")
    if config.backend == VPS and config.railway_root and _same_or_under(root, _abs(config.railway_root)):
        errors.append("vps_root_matches_railway_root")
    backup = _abs(config.backup_root)
    if not _same_or_under(backup, root) or _same_path(backup, root):
        errors.append("backup_root_outside_storage_root")
    if config.live_db and _same_path(config.live_db, backup):
        errors.append("live_db_is_backup_root")
    return errors


def _root_stat(root: Path) -> tuple[os.stat_result | None, str]:
    try:
        if root.is_symlink():
            return None, "root_is_symlink"
        if os.path.realpath(root) != str(root):
            return None, "root_has_symlink_component"
        stat = os.stat(root, follow_symlinks=False)
        if not os.path.isdir(root):
            return None, "root_not_directory"
        return stat, ""
    except OSError as exc:
        return None, f"root_stat_failed:{type(exc).__name__}"


def _safe_file(path: Path, root: Path, root_stat: os.stat_result) -> tuple[os.stat_result | None, str]:
    candidate = _abs(path)
    if candidate == root:
        return None, "candidate_is_root"
    if not _same_or_under(candidate, root):
        return None, "candidate_outside_root"
    current = root
    try:
        for part in candidate.relative_to(root).parts:
            current = current / part
            if current.is_symlink():
                return None, "symlink_escape_blocked"
        stat = os.lstat(candidate)
    except OSError as exc:
        return None, f"candidate_stat_failed:{type(exc).__name__}"
    if os.path.islink(candidate):
        return None, "symlink_candidate_blocked"
    if not os.path.isfile(candidate):
        return None, "candidate_not_regular_file"
    if int(stat.st_dev) != int(root_stat.st_dev):
        return None, "different_device_blocked"
    return stat, ""


def _walk_files(root: Path, max_files: int) -> tuple[list[tuple[Path, os.stat_result]], list[str]]:
    root_stat, reason = _root_stat(root)
    if not root_stat:
        return [], [] if reason == "root_not_directory" else [reason]
    found: list[tuple[Path, os.stat_result]] = []
    errors: list[str] = []
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = _abs(current)
        safe_dirs: list[str] = []
        for name in dirnames:
            directory = current_path / name
            try:
                if directory.is_symlink():
                    errors.append("symlink_directory_skipped")
                    continue
                stat = os.stat(directory, follow_symlinks=False)
                if int(stat.st_dev) != int(root_stat.st_dev):
                    errors.append("different_device_directory_skipped")
                    continue
            except OSError:
                errors.append("directory_stat_failed")
                continue
            safe_dirs.append(name)
        dirnames[:] = safe_dirs
        for name in filenames:
            path = current_path / name
            stat, item_reason = _safe_file(path, root, root_stat)
            if not stat:
                errors.append(item_reason)
                continue
            found.append((path, stat))
            if len(found) >= max_files:
                errors.append("max_scan_files_reached")
                return found, errors
    return found, errors


def _protected_relation(path: Path, values: Iterable[str]) -> bool:
    candidate = _abs(path)
    return any(_same_or_under(candidate, _abs(value)) for value in values if str(value).strip())


def _name_is_durable(path: Path) -> bool:
    lower = path.name.lower()
    if path.suffix.lower() in PROTECTED_SUFFIXES:
        return True
    return any(token in lower for token in PROTECTED_NAME_PARTS)


@dataclass
class MaintenanceItem:
    path: str
    category: str
    size_bytes: int
    age_seconds: int
    status: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MaintenanceReport:
    mode: str
    backend: str
    dry_run: bool
    status: str
    storage_root: str
    backup_root: str
    candidate_files: int = 0
    candidate_bytes: int = 0
    protected_files: int = 0
    protected_bytes: int = 0
    deleted_files: int = 0
    deleted_bytes: int = 0
    scanned_files: int = 0
    errors: list[str] = field(default_factory=list)
    items: list[MaintenanceItem] = field(default_factory=list)
    backup: dict = field(default_factory=dict)
    next_run: str = ""

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["items"] = [item.to_dict() for item in self.items]
        return payload


def _item(path: Path, category: str, stat: os.stat_result, now: float, status: str, reason: str) -> MaintenanceItem:
    return MaintenanceItem(
        path=str(path),
        category=category,
        size_bytes=max(0, int(stat.st_size)),
        age_seconds=max(0, int(now - float(stat.st_mtime))),
        status=status,
        reason=reason,
    )


def _daily_items(config: StorageConfig, now: float | None = None) -> tuple[list[MaintenanceItem], list[str], int]:
    current = float(now if now is not None else time.time())
    protected = set(config.protected_paths) | set(config.running_paths) | set(config.undelivered_paths)
    if config.live_db:
        live = _abs(config.live_db)
        protected.update({str(live), str(live) + "-wal", str(live) + "-shm"})
    backup_root = _abs(config.backup_root)
    items: list[MaintenanceItem] = []
    errors: list[str] = []
    scanned = 0
    seen: set[str] = set()
    roots: list[tuple[str, Path]] = [
        (relative, _abs(config.storage_root) / relative)
        for relative in TEMP_DIR_NAMES
    ]
    roots.extend(("temp", _abs(root)) for root in config.extra_temp_roots)
    for relative, root in roots:
        files, root_errors = _walk_files(root, config.max_scan_files)
        errors.extend(root_errors[:20])
        for path, stat in files:
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            scanned += 1
            if _same_or_under(path, backup_root):
                continue
            normalized = path.name.lower()
            if _protected_relation(path, config.running_paths):
                items.append(_item(path, "protected", stat, current, "protected", "active_job"))
                continue
            if _protected_relation(path, config.undelivered_paths):
                items.append(_item(path, "protected", stat, current, "protected", "undelivered_final_artifact"))
                continue
            if _protected_relation(path, protected) or _name_is_durable(path):
                items.append(_item(path, "protected", stat, current, "protected", "durable_data"))
                continue
            if stat.st_size == 0 or path.suffix.lower() in PARTIAL_SUFFIXES or any(token in normalized for token in (".partial", ".failed", ".part")):
                category, ttl = "partial", config.partial_ttl_seconds
            elif relative == "cache" or "\\cache\\" in str(path).lower() or "/cache/" in str(path).lower():
                category, ttl = "cache", config.cache_ttl_seconds
            else:
                category, ttl = "temp", config.temp_ttl_seconds
            age = max(0, int(current - float(stat.st_mtime)))
            status = "candidate" if age >= ttl else "young"
            reason = "ttl_expired" if status == "candidate" else "younger_than_ttl"
            items.append(_item(path, category, stat, current, status, reason))
    return items, errors, scanned


def _base_report(config: StorageConfig, mode: str, dry_run: bool, status: str = "preview") -> MaintenanceReport:
    return MaintenanceReport(
        mode=mode,
        backend=config.backend,
        dry_run=dry_run,
        status=status,
        storage_root=str(config.storage_root),
        backup_root=str(config.backup_root),
        next_run=next_run(config, mode),
    )


def plan_daily(config: StorageConfig, now: float | None = None) -> MaintenanceReport:
    errors = _validate_config(config)
    report = _base_report(config, "daily", True, "preview")
    if errors:
        report.status = "blocked"
        report.errors.extend(errors)
        return report
    items, scan_errors, scanned = _daily_items(config, now)
    report.items = items
    report.errors.extend(scan_errors)
    report.scanned_files = scanned
    report.candidate_files = sum(1 for item in items if item.status == "candidate")
    report.candidate_bytes = sum(item.size_bytes for item in items if item.status == "candidate")
    report.protected_files = sum(1 for item in items if item.status == "protected")
    report.protected_bytes = sum(item.size_bytes for item in items if item.status == "protected")
    return report


def _lock_acquire(path: Path) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(f"pid={os.getpid()}\nstarted={int(time.time())}\n")
        return True
    except FileExistsError:
        return False
    except OSError:
        return False


def _lock_release(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _state_key(mode: str, now: datetime | None = None) -> str:
    local = _local_now(now)
    if mode == "daily":
        return local.strftime("%Y-%m-%d")
    return f"{local.isocalendar().year}-W{local.isocalendar().week:02d}"


def _read_state(config: StorageConfig) -> dict:
    try:
        return json.loads(config.state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def _write_state(config: StorageConfig, mode: str, key: str, report: MaintenanceReport) -> None:
    try:
        state = _read_state(config)
        state[mode] = {"key": key, "status": report.status, "deleted_files": report.deleted_files, "deleted_bytes": report.deleted_bytes, "at": int(time.time())}
        config.storage_root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=config.storage_root, delete=False) as handle:
            json.dump(state, handle, sort_keys=True)
            temporary = handle.name
        os.replace(temporary, config.state_path)
    except OSError:
        return


def _execute_items(config: StorageConfig, report: MaintenanceReport, now: float | None = None) -> MaintenanceReport:
    current = float(now if now is not None else time.time())
    deleted = 0
    deleted_bytes = 0
    for item in report.items:
        if item.status != "candidate" or item.category == "backup":
            continue
        if deleted >= config.max_delete_files:
            report.errors.append("max_delete_files_reached")
            break
        path = _abs(item.path)
        stat, reason = _safe_file(path, _abs(config.storage_root), _root_stat(_abs(config.storage_root))[0] or os.stat_result((0,) * 10))
        if not stat:
            item.status, item.reason = "protected", f"recheck_{reason}"
            report.protected_files += 1
            continue
        if _protected_relation(path, config.protected_paths) or _protected_relation(path, config.running_paths) or _protected_relation(path, config.undelivered_paths):
            item.status, item.reason = "protected", "recheck_protected_reference"
            report.protected_files += 1
            report.protected_bytes += int(stat.st_size)
            continue
        age = max(0, int(current - float(stat.st_mtime)))
        threshold = config.cache_ttl_seconds if item.category == "cache" else config.partial_ttl_seconds if item.category == "partial" else config.temp_ttl_seconds
        if age < threshold:
            item.status, item.reason = "protected", "recheck_younger_than_ttl"
            report.protected_files += 1
            continue
        try:
            path.unlink()
            item.status, item.reason = "deleted", "deleted_after_recheck"
            deleted += 1
            deleted_bytes += int(stat.st_size)
        except OSError as exc:
            report.errors.append(f"delete_failed:{type(exc).__name__}")
    report.deleted_files += deleted
    report.deleted_bytes += deleted_bytes
    report.candidate_files = sum(1 for item in report.items if item.status == "candidate")
    report.candidate_bytes = sum(item.size_bytes for item in report.items if item.status == "candidate")
    report.dry_run = False
    report.status = "completed"
    return report


def run_daily(config: StorageConfig, *, execute: bool = False, now: datetime | None = None) -> MaintenanceReport:
    if not execute:
        return plan_daily(config, time.time())
    errors = _validate_config(config)
    report = _base_report(config, "daily", False, "starting")
    if errors:
        report.status = "blocked"
        report.errors.extend(errors)
        return report
    if not _lock_acquire(config.lock_path):
        report.status = "skipped_locked"
        report.errors.append("maintenance_lock_active")
        return report
    try:
        key = _state_key("daily", now)
        if _read_state(config).get("daily", {}).get("key") == key:
            report.status = "skipped_already_ran"
            report.errors.append("already_ran_for_local_day")
            return report
        report = plan_daily(config, time.time())
        report.dry_run = False
        report = _execute_items(config, report, time.time())
        _write_state(config, "daily", key, report)
        return report
    finally:
        _lock_release(config.lock_path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class BackupRecord:
    path: str
    lineage: str
    timestamp: str
    digest: str
    size_bytes: int
    valid: bool
    reason: str


def parse_backup_name(path: str | os.PathLike[str]) -> dict | None:
    name = _abs(path).name
    match = BACKUP_NAME_RE.match(name) or ZIP_BACKUP_RE.match(name)
    if not match:
        return None
    payload = match.groupdict()
    return {"lineage": str(payload["lineage"]).lower(), "timestamp": payload["stamp"], "extension": payload["extension"].lower(), "label": payload.get("label") or ""}


def _validate_sqlite(path: Path) -> tuple[bool, str]:
    try:
        with path.open("rb") as handle:
            if handle.read(16) != b"SQLite format 3\x00":
                return False, "invalid_sqlite_header"
        uri = f"file:{path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=3)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if not result or str(result[0]).lower() != "ok":
                return False, "sqlite_integrity_check_failed"
        finally:
            conn.close()
        return True, "valid_sqlite_backup"
    except (OSError, sqlite3.DatabaseError) as exc:
        return False, f"backup_validation_failed:{type(exc).__name__}"


def _validate_archive(path: Path) -> tuple[bool, str]:
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                return False, "archive_crc_failed"
        return True, "valid_archive_backup"
    except (OSError, zipfile.BadZipFile) as exc:
        return False, f"backup_validation_failed:{type(exc).__name__}"


def validate_backup(path: str | os.PathLike[str], backup_root: str | os.PathLike[str]) -> BackupRecord:
    target = _abs(path)
    root = _abs(backup_root)
    parsed = parse_backup_name(target)
    try:
        size = int(target.stat().st_size)
    except OSError:
        size = 0
    if not _same_or_under(target, root):
        return BackupRecord(str(target), "", "", "", size, False, "outside_backup_root")
    if not parsed:
        return BackupRecord(str(target), "", "", "", size, False, "unsupported_backup_name")
    if size <= 0:
        return BackupRecord(str(target), parsed["lineage"], parsed["timestamp"], "", size, False, "empty_backup")
    valid, reason = _validate_archive(target) if parsed["extension"] == "zip" else _validate_sqlite(target)
    digest = ""
    if valid:
        try:
            digest = _sha256(target)
        except OSError as exc:
            return BackupRecord(str(target), parsed["lineage"], parsed["timestamp"], "", size, False, f"hash_failed:{type(exc).__name__}")
    return BackupRecord(str(target), parsed["lineage"], parsed["timestamp"], digest, size, valid, reason)


def _backup_records(config: StorageConfig) -> tuple[list[BackupRecord], list[str]]:
    files, errors = _walk_files(_abs(config.backup_root), config.max_scan_files)
    records: list[BackupRecord] = []
    for path, _stat in files:
        records.append(validate_backup(path, config.backup_root))
    return records, errors


def backup_retention_plan(config: StorageConfig, keep: int = DEFAULT_KEEP_BACKUPS) -> tuple[list[BackupRecord], list[BackupRecord], list[BackupRecord], list[str]]:
    records, errors = _backup_records(config)
    groups: dict[tuple[str, str], list[BackupRecord]] = {}
    for record in records:
        if record.valid:
            groups.setdefault((record.lineage, record.digest), []).append(record)
    ordered = sorted(
        groups.items(),
        key=lambda pair: max((item.timestamp for item in pair[1]), default=""),
        reverse=True,
    )
    retained_keys = {key for key, _items in ordered[: max(1, int(keep))]}
    retained: list[BackupRecord] = []
    candidates: list[BackupRecord] = []
    for key, items in ordered:
        if key in retained_keys:
            retained.extend(items)
        else:
            candidates.extend(items)
    if ordered and not retained:
        retained.extend(ordered[0][1])
        candidates = [item for item in candidates if item not in ordered[0][1]]
    invalid = [record for record in records if not record.valid]
    return retained, candidates, invalid, errors


def _backup_item(record: BackupRecord, status: str, reason: str) -> MaintenanceItem:
    try:
        stat = _abs(record.path).stat()
        age = max(0, int(time.time() - float(stat.st_mtime)))
    except OSError:
        age = 0
    return MaintenanceItem(record.path, "backup", record.size_bytes, age, status, reason)


def plan_weekly(config: StorageConfig, *, keep_backups: int = DEFAULT_KEEP_BACKUPS, now: float | None = None) -> MaintenanceReport:
    report = plan_daily(config, now)
    report.mode = "weekly"
    report.next_run = next_run(config, "weekly")
    retained, candidates, invalid, errors = backup_retention_plan(config, keep_backups)
    report.backup = {
        "valid": len(retained) + len(candidates),
        "invalid": len(invalid),
        "retained": len(retained),
        "delete_candidates": len(candidates),
        "logical_generations": len({(item.lineage, item.digest) for item in retained + candidates}),
        "retained_paths": [item.path for item in retained],
        "invalid_reasons": sorted({item.reason for item in invalid}),
    }
    report.errors.extend(errors)
    report.items.extend(_backup_item(item, "protected", "retained_valid_backup") for item in retained)
    report.items.extend(_backup_item(item, "candidate", "older_valid_backup") for item in candidates)
    report.items.extend(_backup_item(item, "protected", item.reason) for item in invalid)
    report.candidate_files = sum(1 for item in report.items if item.status == "candidate")
    report.candidate_bytes = sum(item.size_bytes for item in report.items if item.status == "candidate")
    report.protected_files = sum(1 for item in report.items if item.status == "protected")
    report.protected_bytes = sum(item.size_bytes for item in report.items if item.status == "protected")
    return report


def _execute_backup_items(config: StorageConfig, report: MaintenanceReport) -> None:
    deleted = 0
    for item in report.items:
        if item.category != "backup" or item.status != "candidate":
            continue
        if deleted >= config.max_delete_files:
            report.errors.append("max_delete_files_reached")
            break
        path = _abs(item.path)
        root_stat, root_reason = _root_stat(_abs(config.backup_root))
        stat, reason = _safe_file(path, _abs(config.backup_root), root_stat) if root_stat else (None, root_reason)
        if not stat:
            item.status, item.reason = "protected", f"recheck_{reason}"
            report.protected_files += 1
            continue
        record = validate_backup(path, config.backup_root)
        if not record.valid or (config.live_db and _same_path(path, config.live_db)):
            item.status, item.reason = "protected", "recheck_backup_no_longer_valid_or_live_db"
            report.protected_files += 1
            report.protected_bytes += int(stat.st_size)
            continue
        try:
            path.unlink()
            item.status, item.reason = "deleted", "deleted_after_retention_recheck"
            report.deleted_files += 1
            report.deleted_bytes += int(stat.st_size)
            deleted += 1
        except OSError as exc:
            report.errors.append(f"backup_delete_failed:{type(exc).__name__}")


def run_weekly(config: StorageConfig, *, keep_backups: int = DEFAULT_KEEP_BACKUPS, execute: bool = False, now: datetime | None = None) -> MaintenanceReport:
    if not execute:
        return plan_weekly(config, keep_backups=keep_backups, now=time.time())
    errors = _validate_config(config)
    report = _base_report(config, "weekly", False, "starting")
    if errors:
        report.status = "blocked"
        report.errors.extend(errors)
        return report
    if not _lock_acquire(config.lock_path):
        report.status = "skipped_locked"
        report.errors.append("maintenance_lock_active")
        return report
    try:
        key = _state_key("weekly", now)
        if _read_state(config).get("weekly", {}).get("key") == key:
            report.status = "skipped_already_ran"
            report.errors.append("already_ran_for_local_week")
            return report
        report = plan_weekly(config, keep_backups=keep_backups, now=time.time())
        report = _execute_items(config, report, time.time())
        _execute_backup_items(config, report)
        report.dry_run = False
        report.status = "completed"
        _write_state(config, "weekly", key, report)
        return report
    finally:
        _lock_release(config.lock_path)


def cleanup_job_workspace(
    workspace: str | os.PathLike[str],
    job: Mapping[str, object] | None = None,
    *,
    execute: bool = False,
    now: float | None = None,
    allowed_roots: Iterable[str | os.PathLike[str]] | None = None,
    failed_grace_seconds: int = DEFAULT_FAILED_JOB_GRACE_SECONDS,
) -> dict:
    record = dict(job or {})
    target = _abs(workspace)
    roots = [_abs(item) for item in (allowed_roots or (target.parent,))]
    root = next((item for item in roots if _same_or_under(target, item) and target != item), None)
    base = {"workspace": str(target), "allowed": False, "deleted": False, "deleted_files": 0, "deleted_bytes": 0, "reason": ""}
    if not root:
        base["reason"] = "workspace_outside_allowlist"
        return base
    if target.is_symlink() or not target.exists() or not target.is_dir():
        base["reason"] = "workspace_missing_or_symlink"
        base["allowed"] = not target.exists()
        return base
    status = str(record.get("status") or record.get("terminal_state") or "").strip().lower()
    active = status in {"queued", "claimed", "running", "processing", "retrying", "retryable", "delivering", "finalizing"}
    retry_pending = bool(record.get("retry_pending") or record.get("recovery_pending") or record.get("delivery_retry_pending"))
    if active or retry_pending:
        base["reason"] = "active_or_retryable_job"
        return base
    current = float(now if now is not None else time.time())
    if status in {"failed", "cancelled", "canceled"}:
        failed_at = float(record.get("failed_at") or record.get("finished_at") or record.get("updated_at") or 0)
        if failed_at <= 0 or current - failed_at < max(1, int(failed_grace_seconds)):
            base["reason"] = "failed_job_debug_grace"
            return base
    delivered = status in {"delivered", "completed", "success", "succeeded"} or bool(record.get("delivery_succeeded"))
    delivery_identity = record.get("delivery_message_id") or record.get("telegram_message_id") or record.get("file_id")
    delivery_persisted = bool(record.get("delivery_persisted") or record.get("receipt_persisted") or delivery_identity)
    artifact_valid = bool(record.get("final_artifact_valid") or record.get("artifact_valid") or record.get("output_bytes", 0))
    if delivered and (not delivery_persisted or not artifact_valid):
        base["reason"] = "delivery_receipt_or_artifact_not_persisted"
        return base
    if status not in {"failed", "cancelled", "canceled", "delivered", "completed", "success", "succeeded"} and not bool(record.get("terminal")):
        base["reason"] = "unknown_non_terminal_state"
        return base
    base["allowed"] = True
    base["reason"] = "terminal_cleanup_allowed"
    if not execute:
        return base
    root_stat, root_reason = _root_stat(root)
    if not root_stat:
        base["allowed"] = False
        base["reason"] = root_reason
        return base
    total_files = 0
    total_bytes = 0
    try:
        for current_dir, dirnames, filenames in os.walk(target, topdown=False, followlinks=False):
            current_path = _abs(current_dir)
            for name in filenames:
                path = current_path / name
                stat, reason = _safe_file(path, root, root_stat)
                if not stat:
                    base["reason"] = f"cleanup_blocked:{reason}"
                    continue
                try:
                    path.unlink()
                    total_files += 1
                    total_bytes += int(stat.st_size)
                except OSError:
                    base["reason"] = "cleanup_partial_failure"
            for name in dirnames:
                path = current_path / name
                if path.is_symlink():
                    continue
                try:
                    path.rmdir()
                except OSError:
                    pass
        if target.exists():
            target.rmdir()
        base["deleted"] = not target.exists()
        base["reason"] = "terminal_workspace_deleted" if base["deleted"] else "cleanup_partial_failure"
        base["deleted_files"] = total_files
        base["deleted_bytes"] = total_bytes
    except OSError as exc:
        base["reason"] = f"cleanup_failed:{type(exc).__name__}"
    return base


def _local_now(now: datetime | None = None, timezone_name: str = TIMEZONE) -> datetime:
    zone = ZoneInfo(timezone_name)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(zone)


def next_run(config: StorageConfig, mode: str, now: datetime | None = None) -> str:
    current = _local_now(now, config.timezone_name)
    if mode == "daily":
        target = current.replace(hour=12, minute=0, second=0, microsecond=0)
        if current >= target:
            target += timedelta(days=1)
    else:
        target = current - timedelta(days=current.weekday())
        target = target.replace(hour=3, minute=30, second=0, microsecond=0) + timedelta(days=6)
        if current >= target:
            target += timedelta(days=7)
    return target.isoformat()


def maintenance_status(config: StorageConfig, now: datetime | None = None) -> dict:
    state = _read_state(config)
    current = _local_now(now, config.timezone_name)
    daily_target = current.replace(hour=12, minute=0, second=0, microsecond=0)
    weekly_target = current - timedelta(days=current.weekday())
    weekly_target = weekly_target.replace(hour=3, minute=30, second=0, microsecond=0) + timedelta(days=6)
    return {
        "backend": config.backend,
        "storage_root": str(config.storage_root),
        "backup_root": str(config.backup_root),
        "timezone": config.timezone_name,
        "daily_schedule": "12:00 Asia/Ho_Chi_Minh",
        "weekly_schedule": "Sunday 03:30 Asia/Ho_Chi_Minh",
        "daily_due": current >= daily_target,
        "weekly_due": current >= weekly_target,
        "daily_current_key": current.strftime("%Y-%m-%d"),
        "weekly_current_key": f"{current.isocalendar().year}-W{current.isocalendar().week:02d}",
        "daily_next_run": next_run(config, "daily", now),
        "weekly_next_run": next_run(config, "weekly", now),
        "lock_active": config.lock_path.exists(),
        "last_daily_run": state.get("daily") or {},
        "last_weekly_run": state.get("weekly") or {},
    }


def _print_report(report: MaintenanceReport) -> None:
    print(json.dumps(report.to_dict(), ensure_ascii=True, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TOAN AAS backend-local storage maintenance")
    parser.add_argument("mode", choices=("daily", "weekly", "status"))
    parser.add_argument("--backend", choices=(RAILWAY, VPS), required=True)
    parser.add_argument("--keep-backups", type=int, default=DEFAULT_KEEP_BACKUPS)
    parser.add_argument("--preview", action="store_true", help="plan only; this is the default")
    parser.add_argument("--execute", action="store_true", help="execute the previously previewed plan")
    args = parser.parse_args(argv)
    if args.preview and args.execute:
        parser.error("choose --preview or --execute")
    try:
        config = config_from_env(args.backend)
        if args.mode == "status":
            print(json.dumps(maintenance_status(config), ensure_ascii=True, sort_keys=True))
            return 0
        report = run_daily(config, execute=args.execute) if args.mode == "daily" else run_weekly(config, keep_backups=max(1, args.keep_backups), execute=args.execute)
        _print_report(report)
        return 0 if report.status not in {"blocked"} else 2
    except ValueError as exc:
        print(json.dumps({"ok": False, "status": "blocked", "reason": str(exc)}, ensure_ascii=True, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
