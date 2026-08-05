"""Weekly Railway-to-VPS storage maintenance.

This module is intentionally conservative: local Railway copies are deleted
only after the remote copy verifies size/hash and metadata is persisted.
"""

from __future__ import annotations

import json
import os
import posixpath
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

from services import artifact_storage, storage_cleanup, storage_migration


WEEKLY_RUN_TABLE = "storage_weekly_maintenance_runs"
WEEKLY_BACKUP_TABLE = "storage_weekly_backup_archives"
DAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
SAFE_EMPTY_DIRS = (
    "dub_assets",
    "voice_assets",
    "translation_assets",
    "subtitle_assets",
    "music",
    "video",
    "subdub",
    "artifacts",
    "worker_results",
    "tmp",
    "cache",
)


@dataclass(frozen=True)
class WeeklyStorageConfig:
    enabled: bool = True
    base_dir: str = "/data"
    day: str = "sunday"
    hour: int = 3
    minute: int = 30
    timezone_name: str = "Asia/Ho_Chi_Minh"
    railway_backup_keep: int = 3
    vps_backup_keep_weeks: int = 12
    tmp_ttl_seconds: int = 6 * 3600
    generated_ttl_seconds: int = 24 * 3600
    max_scan_files: int = 10000
    max_delete_files: int = 500


@dataclass
class BackupArchiveFile:
    path: str
    remote_path: str
    size_bytes: int
    mtime: float
    status: str
    reason: str


@dataclass
class BackupArchiveReport:
    backup_dir: str
    keep: int
    dry_run: bool = True
    files: list[BackupArchiveFile] = field(default_factory=list)
    kept_files: int = 0
    archive_candidates: int = 0
    archived_files: int = 0
    verified_files: int = 0
    deleted_files: int = 0
    deleted_bytes: int = 0
    failed_uploads: int = 0
    failed_verifies: int = 0
    errors: list[str] = field(default_factory=list)
    vps_retention: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "files": [asdict(item) for item in self.files],
        }


@dataclass
class WeeklyMaintenanceReport:
    ok: bool
    dry_run: bool
    status: str
    week_key: str
    reason: str = ""
    railway_used_before: int = 0
    railway_used_after: int = 0
    bytes_freed: int = 0
    files_migrated: int = 0
    files_verified: int = 0
    railway_copies_deleted: int = 0
    backups_archived_to_vps: int = 0
    backups_deleted_from_railway: int = 0
    current_railway_backups_kept: int = 0
    temp_cache_deleted: int = 0
    active_refs_protected: int = 0
    failed_uploads: int = 0
    failed_verifies: int = 0
    empty_dirs_removed: int = 0
    next_weekly_run: str = ""
    last_weekly_run: dict = field(default_factory=dict)
    lock_status: str = ""
    migration: dict = field(default_factory=dict)
    backup_archive: dict = field(default_factory=dict)
    cleanup: dict = field(default_factory=dict)
    empty_dirs: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _resolve(path: str | os.PathLike[str]) -> Path | None:
    try:
        return Path(path).expanduser().resolve()
    except Exception:
        return None


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _normalized(path: str | os.PathLike[str]) -> str:
    return str(_resolve(path) or path).replace("\\", "/")


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or "Asia/Ho_Chi_Minh"))
    except Exception:
        return ZoneInfo("Asia/Ho_Chi_Minh")


def localized_now(config: WeeklyStorageConfig, now: datetime | None = None) -> datetime:
    zone = _tz(config.timezone_name)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(zone)


def weekly_key(config: WeeklyStorageConfig, now: datetime | None = None) -> str:
    current = localized_now(config, now)
    iso = current.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def scheduled_time_for_week(config: WeeklyStorageConfig, now: datetime | None = None) -> datetime:
    current = localized_now(config, now)
    target_day = DAY_INDEX.get(str(config.day or "sunday").lower(), 6)
    start = current - timedelta(days=current.weekday())
    scheduled = start.replace(
        hour=max(0, min(int(config.hour), 23)),
        minute=max(0, min(int(config.minute), 59)),
        second=0,
        microsecond=0,
    ) + timedelta(days=target_day)
    return scheduled


def next_weekly_run(config: WeeklyStorageConfig, now: datetime | None = None) -> str:
    current = localized_now(config, now)
    scheduled = scheduled_time_for_week(config, current)
    if current >= scheduled:
        scheduled = scheduled + timedelta(days=7)
    return scheduled.isoformat()


def is_due(config: WeeklyStorageConfig, now: datetime | None = None) -> bool:
    if not config.enabled:
        return False
    current = localized_now(config, now)
    return current >= scheduled_time_for_week(config, current)


def ensure_weekly_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {WEEKLY_RUN_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'started',
            started_at INTEGER NOT NULL DEFAULT 0,
            finished_at INTEGER NOT NULL DEFAULT 0,
            report_json TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {WEEKLY_BACKUP_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            local_path TEXT NOT NULL,
            remote_path TEXT NOT NULL UNIQUE,
            size_bytes INTEGER NOT NULL DEFAULT 0,
            artifact_hash TEXT NOT NULL DEFAULT '',
            week_key TEXT NOT NULL DEFAULT '',
            archived_at INTEGER NOT NULL DEFAULT 0,
            deleted_remote INTEGER NOT NULL DEFAULT 0,
            deleted_remote_at INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()


def last_weekly_run(conn: sqlite3.Connection | None = None) -> dict:
    if conn is None:
        return {}
    ensure_weekly_tables(conn)
    row = conn.execute(
        f"SELECT week_key, status, started_at, finished_at, reason FROM {WEEKLY_RUN_TABLE} ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return {}
    keys = ("week_key", "status", "started_at", "finished_at", "reason")
    return dict(row) if hasattr(row, "keys") else dict(zip(keys, row))


def start_weekly_run(conn: sqlite3.Connection, key: str, now_ts: int | None = None) -> tuple[bool, str]:
    ensure_weekly_tables(conn)
    try:
        conn.execute(
            f"INSERT INTO {WEEKLY_RUN_TABLE} (week_key, status, started_at) VALUES (?, 'started', ?)",
            (key, int(now_ts or time.time())),
        )
        conn.commit()
        return True, "lock_acquired"
    except sqlite3.IntegrityError:
        return False, "already_ran_this_week"
    except sqlite3.OperationalError:
        return False, "db_busy"


def finish_weekly_run(conn: sqlite3.Connection, key: str, report: WeeklyMaintenanceReport) -> None:
    ensure_weekly_tables(conn)
    conn.execute(
        f"UPDATE {WEEKLY_RUN_TABLE} SET status=?, finished_at=?, report_json=?, reason=? WHERE week_key=?",
        (
            report.status,
            int(time.time()),
            json.dumps(report.to_dict(), ensure_ascii=False, separators=(",", ":"))[:200000],
            report.reason[:500],
            key,
        ),
    )
    conn.commit()


def remote_backup_path(path: Path, config: artifact_storage.ArtifactStorageConfig, *, now: datetime | None = None) -> str:
    current = now or datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    base = str(config.vps_base_dir or "/opt/toanaas-storage").replace("\\", "/").rstrip("/")
    return posixpath.normpath(posixpath.join(base, "backups", "railway", f"{current.year:04d}", f"{current.month:02d}", path.name))


def _default_vps_uploader(local_path: str, remote_path: str, config: artifact_storage.ArtifactStorageConfig) -> dict:
    uploader = getattr(artifact_storage, "_upload_vps_sftp", None)
    if not callable(uploader):
        return {"ok": False, "reason": "vps_sftp_uploader_missing"}
    return uploader(local_path, remote_path, config)


def _default_vps_deleter(remote_path: str, config: artifact_storage.ArtifactStorageConfig) -> dict:
    opener = getattr(artifact_storage, "_open_vps_sftp", None)
    if not callable(opener):
        return {"ok": False, "reason": "vps_sftp_delete_missing"}
    opened = opener(config)
    if not opened.get("ok"):
        return {"ok": False, "reason": opened.get("reason") or "vps_sftp_connect_failed"}
    sftp = opened.get("sftp")
    transport = opened.get("transport")
    try:
        sftp.remove(remote_path)
        return {"ok": True, "reason": "remote_deleted"}
    except Exception as exc:
        return {"ok": False, "reason": f"remote_delete_failed:{type(exc).__name__}"}
    finally:
        try:
            if sftp:
                sftp.close()
        finally:
            if transport:
                transport.close()


def record_backup_archive(conn: sqlite3.Connection | None, *, local_path: str, remote_path: str, size_bytes: int, artifact_hash: str, key: str) -> None:
    if conn is None:
        return
    ensure_weekly_tables(conn)
    conn.execute(
        f"""
        INSERT INTO {WEEKLY_BACKUP_TABLE} (local_path, remote_path, size_bytes, artifact_hash, week_key, archived_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(remote_path) DO UPDATE SET
            local_path=excluded.local_path,
            size_bytes=excluded.size_bytes,
            artifact_hash=excluded.artifact_hash,
            week_key=excluded.week_key,
            archived_at=excluded.archived_at,
            deleted_remote=0,
            deleted_remote_at=0
        """,
        (local_path, remote_path, int(size_bytes), artifact_hash, key, int(time.time())),
    )
    conn.commit()


def enforce_vps_weekly_retention(
    conn: sqlite3.Connection | None,
    *,
    keep_weeks: int,
    config: artifact_storage.ArtifactStorageConfig,
    confirm: bool,
    deleter: Callable[[str, artifact_storage.ArtifactStorageConfig], dict] | None = None,
) -> dict:
    if conn is None:
        return {"ok": True, "reason": "metadata_conn_missing", "candidates": 0, "deleted_remote": 0}
    ensure_weekly_tables(conn)
    rows = conn.execute(
        f"""
        SELECT id, remote_path, week_key FROM {WEEKLY_BACKUP_TABLE}
        WHERE deleted_remote=0
        ORDER BY week_key DESC, archived_at DESC, id DESC
        """
    ).fetchall()
    records = [dict(row) if hasattr(row, "keys") else {"id": row[0], "remote_path": row[1], "week_key": row[2]} for row in rows]
    keep_count = max(1, int(keep_weeks or 12))
    kept_weeks: list[str] = []
    for record in records:
        week = str(record.get("week_key") or "")
        if week and week not in kept_weeks:
            kept_weeks.append(week)
        if len(kept_weeks) >= keep_count:
            break
    delete_records = [record for record in records if str(record.get("week_key") or "") not in set(kept_weeks)]
    deleted = 0
    errors: list[str] = []
    if confirm:
        remote_deleter = deleter or _default_vps_deleter
        for record in delete_records:
            result = remote_deleter(str(record.get("remote_path") or ""), config)
            if result.get("ok"):
                conn.execute(
                    f"UPDATE {WEEKLY_BACKUP_TABLE} SET deleted_remote=1, deleted_remote_at=? WHERE id=?",
                    (int(time.time()), int(record.get("id") or 0)),
                )
                deleted += 1
            else:
                errors.append(str(result.get("reason") or "remote_delete_failed"))
        conn.commit()
    return {
        "ok": not errors,
        "keep_weeks": keep_count,
        "kept_week_keys": kept_weeks,
        "candidates": len(delete_records),
        "deleted_remote": deleted,
        "errors": errors,
    }


def archive_old_backups_to_vps(
    base_dir: str | os.PathLike[str],
    *,
    config: artifact_storage.ArtifactStorageConfig,
    keep: int = 5,
    confirm: bool = False,
    conn: sqlite3.Connection | None = None,
    week_key_value: str = "",
    uploader: Callable[[str, str, artifact_storage.ArtifactStorageConfig], dict] | None = None,
    verifier: Callable[[str, dict, artifact_storage.ArtifactStorageConfig], dict] | None = None,
    remote_deleter: Callable[[str, artifact_storage.ArtifactStorageConfig], dict] | None = None,
    vps_keep_weeks: int = 12,
    now: datetime | None = None,
) -> BackupArchiveReport:
    base = _resolve(base_dir)
    backup_dir = _resolve((base / storage_migration.BACKUP_DIR_NAME) if base else "")
    report = BackupArchiveReport(str(backup_dir or ""), max(1, int(keep or 3)), dry_run=not confirm)
    if not backup_dir or not backup_dir.is_dir():
        report.errors.append("backup_dir_missing")
        return report
    files = [path for path in backup_dir.rglob("*") if path.is_file() and _is_under(path.resolve(), backup_dir)]
    files.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
    valid_files = [path for path in files if storage_migration.classify_backup_cleanup_file(path, backup_dir)[0]]
    kept = set(valid_files[: report.keep])
    for path in files:
        try:
            stat = path.stat()
        except OSError as exc:
            report.errors.append(f"stat_failed:{type(exc).__name__}:{path.name}")
            continue
        valid_backup, backup_reason = storage_migration.classify_backup_cleanup_file(path, backup_dir)
        remote_path = remote_backup_path(path, config, now=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc))
        if path in kept:
            item = BackupArchiveFile(str(path), remote_path, int(stat.st_size), float(stat.st_mtime), "kept", "latest_backup_kept")
            report.kept_files += 1
        elif not valid_backup:
            item = BackupArchiveFile(str(path), remote_path, int(stat.st_size), float(stat.st_mtime), "blocked", backup_reason)
        elif not confirm:
            item = BackupArchiveFile(str(path), remote_path, int(stat.st_size), float(stat.st_mtime), "candidate", "would_archive_to_vps")
            report.archive_candidates += 1
        elif config.backend != "vps_sftp":
            item = BackupArchiveFile(str(path), remote_path, int(stat.st_size), float(stat.st_mtime), "blocked", "backup_archive_backend_not_vps_sftp")
            report.failed_uploads += 1
        else:
            upload_result = (uploader or _default_vps_uploader)(str(path), remote_path, config)
            if not upload_result.get("ok"):
                item = BackupArchiveFile(str(path), remote_path, int(stat.st_size), float(stat.st_mtime), "blocked", str(upload_result.get("reason") or "upload_failed"))
                report.failed_uploads += 1
            else:
                metadata = {
                    "backend": config.backend,
                    "remote_path": str(upload_result.get("remote_path") or remote_path),
                    "artifact_size": int(stat.st_size),
                    "artifact_hash": artifact_storage.artifact_sha256(path),
                }
                verification = artifact_storage.verify_stored_artifact(path, metadata, config=config, verifier=verifier)
                verified = bool(verification.get("ok") and verification.get("size_matches") and verification.get("hash_matches"))
                if not verified:
                    item = BackupArchiveFile(str(path), metadata["remote_path"], int(stat.st_size), float(stat.st_mtime), "blocked", str(verification.get("reason") or "remote_verify_failed"))
                    report.failed_verifies += 1
                else:
                    report.archived_files += 1
                    report.verified_files += 1
                    record_backup_archive(
                        conn,
                        local_path=str(path),
                        remote_path=metadata["remote_path"],
                        size_bytes=int(stat.st_size),
                        artifact_hash=str(metadata["artifact_hash"]),
                        key=week_key_value,
                    )
                    try:
                        path.unlink()
                        item = BackupArchiveFile(str(path), metadata["remote_path"], int(stat.st_size), float(stat.st_mtime), "deleted", "remote_verified_backup_deleted")
                        report.deleted_files += 1
                        report.deleted_bytes += int(stat.st_size)
                    except OSError as exc:
                        item = BackupArchiveFile(str(path), metadata["remote_path"], int(stat.st_size), float(stat.st_mtime), "blocked", f"delete_failed:{type(exc).__name__}")
                        report.errors.append(item.reason)
        report.files.append(item)
    report.vps_retention = enforce_vps_weekly_retention(
        conn,
        keep_weeks=vps_keep_weeks,
        config=config,
        confirm=confirm,
        deleter=remote_deleter,
    )
    return report


def remove_empty_safe_directories(base_dir: str | os.PathLike[str], *, confirm: bool = False) -> dict:
    base = _resolve(base_dir)
    if not base:
        return {"ok": False, "reason": "base_dir_invalid", "removed": 0, "candidates": 0, "paths": []}
    candidates: list[Path] = []
    for relative in SAFE_EMPTY_DIRS:
        root = _resolve(base / relative)
        if not root or not root.exists() or not root.is_dir() or not _is_under(root, base):
            continue
        for current, dirnames, filenames in os.walk(root, topdown=False):
            path = _resolve(current)
            if not path or path == base or path.name == storage_migration.BACKUP_DIR_NAME:
                continue
            if filenames:
                continue
            try:
                if any(path.iterdir()):
                    continue
            except OSError:
                continue
            candidates.append(path)
    removed = 0
    paths: list[str] = []
    for path in candidates:
        paths.append(str(path))
        if confirm:
            try:
                path.rmdir()
                removed += 1
            except OSError:
                pass
    return {"ok": True, "removed": removed, "candidates": len(candidates), "paths": paths[:50]}


def run_weekly_maintenance(
    *,
    config: WeeklyStorageConfig,
    artifact_config: artifact_storage.ArtifactStorageConfig,
    protected_paths: Iterable[str] | None = None,
    running_paths: Iterable[str] | None = None,
    conn: sqlite3.Connection | None = None,
    confirm: bool = False,
    now: datetime | None = None,
    uploader: Callable[[str, str, artifact_storage.ArtifactStorageConfig], dict] | None = None,
    verifier: Callable[[str, dict, artifact_storage.ArtifactStorageConfig], dict] | None = None,
    remote_deleter: Callable[[str, artifact_storage.ArtifactStorageConfig], dict] | None = None,
) -> WeeklyMaintenanceReport:
    key = weekly_key(config, now)
    last_run = last_weekly_run(conn)
    if confirm and conn is not None:
        acquired, lock_reason = start_weekly_run(conn, key)
        if not acquired:
            return WeeklyMaintenanceReport(
                ok=False,
                dry_run=False,
                status="skipped",
                week_key=key,
                reason=lock_reason,
                next_weekly_run=next_weekly_run(config, now),
                last_weekly_run=last_run,
                lock_status=lock_reason,
            )
    else:
        lock_reason = "preview_no_lock"

    before = storage_cleanup.disk_usage_for_path(config.base_dir)
    migration = storage_migration.migrate_existing_assets(
        config.base_dir,
        config=artifact_config,
        protected_paths=protected_paths,
        running_paths=running_paths,
        conn=conn,
        delete_local=True,
        confirm=confirm,
        uploader=uploader,
        verifier=verifier,
        max_scan_files=config.max_scan_files,
        max_migrate_files=config.max_delete_files,
    )
    backup = archive_old_backups_to_vps(
        config.base_dir,
        config=artifact_config,
        keep=config.railway_backup_keep,
        confirm=confirm,
        conn=conn,
        week_key_value=key,
        uploader=uploader,
        verifier=verifier,
        remote_deleter=remote_deleter,
        vps_keep_weeks=config.vps_backup_keep_weeks,
        now=now,
    )
    cleanup_protected = {str(item).replace("\\", "/") for item in (protected_paths or set())}
    for candidate in migration.candidates:
        if candidate.status == "deleted":
            continue
        reason = str(candidate.reason or "")
        if reason in {"upload_failed", "remote_verify_failed", "remote_hash_mismatch", "remote_size_mismatch"}:
            cleanup_protected.add(_normalized(candidate.path))
        elif candidate.status == "blocked" and (
            reason.startswith("upload_")
            or reason.startswith("remote_")
            or "verify" in reason
            or "mismatch" in reason
        ):
            cleanup_protected.add(_normalized(candidate.path))
    cleanup = storage_cleanup.audit_storage_cleanup(
        base_dir=config.base_dir,
        ttl_seconds=config.generated_ttl_seconds,
        tmp_ttl_seconds=config.tmp_ttl_seconds,
        protected_paths=cleanup_protected,
        delete=confirm,
        confirm_delete=confirm,
        max_scan_files=config.max_scan_files,
        max_delete_files=config.max_delete_files,
    )
    empty_dirs = remove_empty_safe_directories(config.base_dir, confirm=confirm)
    after = storage_cleanup.disk_usage_for_path(config.base_dir)
    used_before = int(before.get("used") or 0) if before.get("ok") else 0
    used_after = int(after.get("used") or 0) if after.get("ok") else 0
    deleted_bytes = int(migration.deleted_bytes) + int(backup.deleted_bytes) + int(cleanup.bytes_deleted)
    volume_bytes_freed = max(0, used_before - used_after) if used_before and used_after else 0
    report = WeeklyMaintenanceReport(
        ok=True,
        dry_run=not confirm,
        status="completed" if confirm else "preview",
        week_key=key,
        reason="ok",
        railway_used_before=used_before,
        railway_used_after=used_after,
        bytes_freed=max(volume_bytes_freed, deleted_bytes),
        files_migrated=int(migration.uploaded_files),
        files_verified=int(migration.verified_files) + int(backup.verified_files),
        railway_copies_deleted=int(migration.deleted_files),
        backups_archived_to_vps=int(backup.archived_files),
        backups_deleted_from_railway=int(backup.deleted_files),
        current_railway_backups_kept=int(backup.kept_files),
        temp_cache_deleted=int(cleanup.files_deleted),
        active_refs_protected=int(migration.protected_files) + int(cleanup.files_blocked),
        failed_uploads=len([error for error in migration.errors if "upload_failed" in error]) + int(backup.failed_uploads),
        failed_verifies=len([
            item
            for item in migration.candidates
            if item.status == "blocked"
            and (
                str(item.reason or "").startswith("remote_")
                or "verify" in str(item.reason or "")
                or "mismatch" in str(item.reason or "")
            )
        ]) + int(backup.failed_verifies),
        empty_dirs_removed=int(empty_dirs.get("removed") or 0),
        next_weekly_run=next_weekly_run(config, now),
        last_weekly_run=last_run,
        lock_status=lock_reason,
        migration={
            "candidate_files": migration.candidate_files,
            "candidate_bytes": migration.candidate_bytes,
            "uploaded_files": migration.uploaded_files,
            "verified_files": migration.verified_files,
            "deleted_files": migration.deleted_files,
            "deleted_bytes": migration.deleted_bytes,
            "errors": list(migration.errors),
        },
        backup_archive=backup.to_dict(),
        cleanup=cleanup.to_dict(),
        empty_dirs=empty_dirs,
        errors=list(migration.errors) + list(backup.errors) + list(cleanup.errors),
    )
    if confirm and conn is not None:
        finish_weekly_run(conn, key, report)
    return report


def weekly_status(config: WeeklyStorageConfig, conn: sqlite3.Connection | None = None, now: datetime | None = None) -> dict:
    key = weekly_key(config, now)
    last = last_weekly_run(conn)
    already = bool(last.get("week_key") == key and last.get("status") == "completed")
    return {
        "enabled": bool(config.enabled),
        "base_dir": config.base_dir,
        "day": config.day,
        "hour": int(config.hour),
        "minute": int(config.minute),
        "timezone": config.timezone_name,
        "week_key": key,
        "due": is_due(config, now) and not already,
        "already_ran_this_week": already,
        "last_weekly_run": last,
        "next_weekly_run": next_weekly_run(config, now),
        "railway_backup_keep": int(config.railway_backup_keep),
        "vps_backup_keep_weeks": int(config.vps_backup_keep_weeks),
    }
