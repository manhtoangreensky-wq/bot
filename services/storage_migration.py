"""Safe migration helpers for existing Railway volume artifacts.

The migration path is deliberately conservative: scan only known generated
asset folders, upload through the artifact storage adapter, verify the remote
copy, record a local-to-remote mapping, and delete local files only after the
verified mapping exists.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from services import artifact_storage, storage_cleanup


MIGRATION_TARGET_DIRS = (
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
    os.path.join("tmp", "cache"),
    "cache",
)
BACKUP_DIR_NAME = "backups"
BACKUP_CLEANUP_EXTENSIONS = {".bak", ".backup", ".zip", ".tar", ".gz", ".tgz", ".7z", ".db", ".sqlite", ".sqlite3"}
TOAN_AAS_DB_BACKUP_PATTERNS = (
    re.compile(r"^toanaas_system_\d{8}_\d{6}(?:_\d+)?\.sqlite3$", re.IGNORECASE),
    re.compile(r"^toandaas_system_\d{8}_\d{6}_[A-Za-z0-9_-]+\.db$", re.IGNORECASE),
)
MIGRATION_TABLE = "storage_artifact_migrations"


@dataclass
class StorageMigrationCandidate:
    path: str
    area: str
    size_bytes: int
    artifact_hash: str
    status: str
    reason: str
    active_reference: bool = False
    remote_target: str = ""


@dataclass
class StorageTargetSummary:
    path: str
    exists: bool
    size_bytes: int = 0
    files: int = 0


@dataclass
class StorageMigrationReport:
    base_dir: str
    backend: str
    dry_run: bool = True
    targets: list[StorageTargetSummary] = field(default_factory=list)
    candidates: list[StorageMigrationCandidate] = field(default_factory=list)
    protected_files: int = 0
    protected_bytes: int = 0
    uploaded_files: int = 0
    uploaded_bytes: int = 0
    verified_files: int = 0
    deleted_files: int = 0
    deleted_bytes: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def candidate_files(self) -> int:
        return sum(1 for item in self.candidates if item.status == "candidate")

    @property
    def candidate_bytes(self) -> int:
        return sum(int(item.size_bytes) for item in self.candidates if item.status == "candidate")


@dataclass
class BackupCleanupFile:
    path: str
    size_bytes: int
    mtime: float
    status: str
    reason: str


@dataclass
class BackupCleanupReport:
    backup_dir: str
    keep: int
    dry_run: bool = True
    files: list[BackupCleanupFile] = field(default_factory=list)
    deleted_files: int = 0
    deleted_bytes: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        return sum(int(item.size_bytes) for item in self.files)

    @property
    def delete_candidates(self) -> int:
        return sum(1 for item in self.files if item.status == "candidate")

    @property
    def delete_candidate_bytes(self) -> int:
        return sum(int(item.size_bytes) for item in self.files if item.status == "candidate")


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
    resolved = _resolve(path)
    return str(resolved or path).replace("\\", "/")


def _dir_size(path: Path) -> tuple[int, int]:
    total = 0
    files = 0
    if not path.exists():
        return 0, 0
    for current, dirnames, filenames in os.walk(path):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        for filename in filenames:
            target = Path(current) / filename
            try:
                stat = target.stat()
            except OSError:
                continue
            files += 1
            total += int(stat.st_size)
    return total, files


def target_summaries(base_dir: str | os.PathLike[str]) -> list[StorageTargetSummary]:
    base = _resolve(base_dir)
    if not base:
        return []
    summaries: list[StorageTargetSummary] = []
    for relative in (*MIGRATION_TARGET_DIRS, BACKUP_DIR_NAME):
        target = (base / relative).resolve()
        size, files = _dir_size(target)
        summaries.append(StorageTargetSummary(str(target), target.exists(), size, files))
    return summaries


def migration_roots(base_dir: str | os.PathLike[str]) -> list[Path]:
    base = _resolve(base_dir)
    if not base:
        return []
    roots: list[Path] = []
    seen: set[str] = set()
    for relative in MIGRATION_TARGET_DIRS:
        target = _resolve(base / relative)
        if not target or not target.exists() or not target.is_dir():
            continue
        if not _is_under(target, base):
            continue
        key = str(target)
        if key not in seen:
            roots.append(target)
            seen.add(key)
    return roots


def _area_for_path(path: Path, base: Path) -> str:
    try:
        first = path.relative_to(base).parts[0]
    except Exception:
        first = "artifacts"
    return artifact_storage.safe_product_area(first)


def scan_migration_candidates(
    base_dir: str | os.PathLike[str],
    *,
    config: artifact_storage.ArtifactStorageConfig,
    protected_paths: Iterable[str] | None = None,
    max_scan_files: int = 10000,
    now: float | None = None,
) -> StorageMigrationReport:
    base = _resolve(base_dir)
    report = StorageMigrationReport(str(base or base_dir), config.backend, dry_run=True)
    if not base:
        report.errors.append("base_dir_invalid")
        return report
    report.targets = target_summaries(base)
    roots = migration_roots(base)
    protected = {_normalized(item) for item in (protected_paths or set())}
    scanned = 0
    root_lookup = {str(root): root for root in roots}
    for root in roots:
        for current, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if not name.startswith(".")]
            current_path = _resolve(current)
            if not current_path:
                continue
            for filename in filenames:
                if scanned >= int(max_scan_files):
                    report.errors.append("max_scan_files_reached")
                    return report
                scanned += 1
                path = current_path / filename
                resolved = _resolve(path)
                if not resolved or not resolved.is_file():
                    continue
                try:
                    stat = resolved.stat()
                except OSError as exc:
                    report.errors.append(f"stat_failed:{type(exc).__name__}:{filename}")
                    continue
                area = _area_for_path(resolved, base)
                active_ref = _normalized(resolved) in protected
                cleanup_item = storage_cleanup.classify_cleanup_file(
                    resolved,
                    roots=list(root_lookup.values()),
                    ttl_seconds=1,
                    tmp_ttl_seconds=1,
                    protected_paths=set(),
                    now=now or (time.time() + 3600),
                )
                if cleanup_item.status == "blocked":
                    candidate = StorageMigrationCandidate(
                        path=str(resolved),
                        area=area,
                        size_bytes=int(stat.st_size),
                        artifact_hash="",
                        status="blocked",
                        reason=cleanup_item.reason,
                        active_reference=active_ref,
                    )
                    report.protected_files += 1
                    report.protected_bytes += int(stat.st_size)
                else:
                    digest = artifact_storage.artifact_sha256(resolved)
                    remote_target = artifact_storage.build_remote_path(
                        resolved,
                        config=config,
                        product_area=area,
                        job_id="legacy",
                    )
                    candidate = StorageMigrationCandidate(
                        path=str(resolved),
                        area=area,
                        size_bytes=int(stat.st_size),
                        artifact_hash=digest,
                        status="candidate",
                        reason="generated_asset",
                        active_reference=active_ref,
                        remote_target=remote_target,
                    )
                report.candidates.append(candidate)
    return report


def ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            local_path TEXT NOT NULL UNIQUE,
            area TEXT NOT NULL,
            size_bytes INTEGER NOT NULL DEFAULT 0,
            artifact_hash TEXT NOT NULL DEFAULT '',
            backend TEXT NOT NULL DEFAULT '',
            remote_path TEXT NOT NULL DEFAULT '',
            public_url TEXT NOT NULL DEFAULT '',
            verified INTEGER NOT NULL DEFAULT 0,
            deleted_local INTEGER NOT NULL DEFAULT 0,
            uploaded_at INTEGER NOT NULL DEFAULT 0,
            deleted_at INTEGER NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT ''
        )
        """
    )


def record_migration_metadata(
    conn: sqlite3.Connection,
    candidate: StorageMigrationCandidate,
    metadata: dict,
    verification: dict,
    *,
    deleted_local: bool = False,
    reason: str = "",
) -> bool:
    ensure_migration_table(conn)
    verified = bool(verification.get("ok") and verification.get("size_matches") and verification.get("hash_matches"))
    conn.execute(
        f"""
        INSERT INTO {MIGRATION_TABLE} (
            local_path, area, size_bytes, artifact_hash, backend, remote_path, public_url,
            verified, deleted_local, uploaded_at, deleted_at, reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(local_path) DO UPDATE SET
            area=excluded.area,
            size_bytes=excluded.size_bytes,
            artifact_hash=excluded.artifact_hash,
            backend=excluded.backend,
            remote_path=excluded.remote_path,
            public_url=excluded.public_url,
            verified=excluded.verified,
            deleted_local=excluded.deleted_local,
            uploaded_at=excluded.uploaded_at,
            deleted_at=excluded.deleted_at,
            reason=excluded.reason
        """,
        (
            candidate.path,
            candidate.area,
            int(candidate.size_bytes),
            str(metadata.get("artifact_hash") or candidate.artifact_hash),
            str(metadata.get("backend") or ""),
            str(metadata.get("remote_path") or ""),
            str(metadata.get("public_url") or ""),
            1 if verified else 0,
            1 if deleted_local else 0,
            int(metadata.get("uploaded_at") or time.time()),
            int(time.time()) if deleted_local else 0,
            reason or str(metadata.get("reason") or ""),
        ),
    )
    conn.commit()
    return verified


def migration_records_for_query(conn: sqlite3.Connection, query: str, *, limit: int = 20) -> list[dict]:
    ensure_migration_table(conn)
    needle = f"%{str(query or '').strip()}%"
    rows = conn.execute(
        f"""
        SELECT local_path, area, size_bytes, artifact_hash, backend, remote_path,
               public_url, verified, deleted_local, uploaded_at, deleted_at, reason
        FROM {MIGRATION_TABLE}
        WHERE local_path LIKE ? OR remote_path LIKE ? OR public_url LIKE ?
        ORDER BY uploaded_at DESC, id DESC
        LIMIT ?
        """,
        (needle, needle, needle, max(1, int(limit))),
    ).fetchall()
    return [dict(row) if hasattr(row, "keys") else _row_to_record(row) for row in rows]


def _row_to_record(row: tuple) -> dict:
    keys = (
        "local_path",
        "area",
        "size_bytes",
        "artifact_hash",
        "backend",
        "remote_path",
        "public_url",
        "verified",
        "deleted_local",
        "uploaded_at",
        "deleted_at",
        "reason",
    )
    return dict(zip(keys, row))


def is_known_toan_aas_db_backup(path: str | os.PathLike[str], backup_dir: str | os.PathLike[str]) -> bool:
    resolved = _resolve(path)
    root = _resolve(backup_dir)
    if not resolved or not root or not _is_under(resolved, root):
        return False
    if resolved.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        return False
    return any(pattern.match(resolved.name) for pattern in TOAN_AAS_DB_BACKUP_PATTERNS)


def classify_backup_cleanup_file(path: str | os.PathLike[str], backup_dir: str | os.PathLike[str]) -> tuple[bool, str]:
    resolved = _resolve(path)
    root = _resolve(backup_dir)
    if not resolved or not root or not _is_under(resolved, root):
        return False, "outside_backup_dir"
    suffix = resolved.suffix.lower()
    if suffix in {".db", ".sqlite", ".sqlite3"}:
        return (True, "known_toan_aas_db_backup") if is_known_toan_aas_db_backup(resolved, root) else (False, "unsupported_backup_name")
    if suffix in BACKUP_CLEANUP_EXTENSIONS:
        return True, "supported_backup_extension"
    return False, "unsupported_backup_extension"


def migrate_existing_assets(
    base_dir: str | os.PathLike[str],
    *,
    config: artifact_storage.ArtifactStorageConfig,
    protected_paths: Iterable[str] | None = None,
    running_paths: Iterable[str] | None = None,
    conn: sqlite3.Connection | None = None,
    delete_local: bool = True,
    confirm: bool = False,
    uploader: Callable[[str, str, artifact_storage.ArtifactStorageConfig], dict] | None = None,
    verifier: Callable[[str, dict, artifact_storage.ArtifactStorageConfig], dict] | None = None,
    max_scan_files: int = 10000,
    max_migrate_files: int = 500,
) -> StorageMigrationReport:
    report = scan_migration_candidates(
        base_dir,
        config=config,
        protected_paths=protected_paths,
        max_scan_files=max_scan_files,
    )
    report.dry_run = not confirm
    if not confirm:
        return report
    running = {_normalized(item) for item in (running_paths or set())}
    migrated = 0
    for candidate in report.candidates:
        if migrated >= int(max_migrate_files):
            report.errors.append("max_migrate_files_reached")
            break
        if candidate.status != "candidate":
            continue
        migrated += 1
        metadata = artifact_storage.store_artifact(
            candidate.path,
            config=config,
            product_area=candidate.area,
            job_id="legacy",
            delete_local_after_upload=False,
            uploader=uploader,
        )
        if not metadata.get("ok"):
            candidate.status = "blocked"
            candidate.reason = str(metadata.get("reason") or "upload_failed")
            report.errors.append(f"upload_failed:{os.path.basename(candidate.path)}:{candidate.reason}")
            continue
        report.uploaded_files += 1
        report.uploaded_bytes += int(candidate.size_bytes)
        verification = artifact_storage.verify_stored_artifact(
            candidate.path,
            metadata,
            config=config,
            verifier=verifier,
        )
        verified = bool(verification.get("ok") and verification.get("size_matches") and verification.get("hash_matches"))
        if verified:
            report.verified_files += 1
        if conn is not None:
            verified = record_migration_metadata(conn, candidate, metadata, verification, deleted_local=False)
        if not verified:
            candidate.status = "blocked"
            candidate.reason = str(verification.get("reason") or "remote_verify_failed")
            continue
        if not delete_local:
            candidate.status = "uploaded"
            candidate.reason = "remote_verified_local_kept"
            continue
        if _normalized(candidate.path) in running:
            candidate.status = "blocked"
            candidate.reason = "active_running_job"
            continue
        if candidate.active_reference and conn is None:
            candidate.status = "blocked"
            candidate.reason = "metadata_record_required"
            continue
        try:
            Path(candidate.path).unlink()
            candidate.status = "deleted"
            candidate.reason = "remote_verified_local_deleted"
            report.deleted_files += 1
            report.deleted_bytes += int(candidate.size_bytes)
            if conn is not None:
                record_migration_metadata(conn, candidate, metadata, verification, deleted_local=True, reason=candidate.reason)
        except OSError as exc:
            candidate.status = "blocked"
            candidate.reason = f"delete_failed:{type(exc).__name__}"
            report.errors.append(f"{candidate.reason}:{os.path.basename(candidate.path)}")
    return report


def backup_cleanup_report(
    base_dir: str | os.PathLike[str],
    *,
    keep: int = 5,
    delete: bool = False,
    confirm: bool = False,
    max_delete_files: int = 200,
) -> BackupCleanupReport:
    base = _resolve(base_dir)
    backup_dir = _resolve((base / BACKUP_DIR_NAME) if base else "")
    report = BackupCleanupReport(str(backup_dir or ""), max(0, int(keep)), dry_run=not (delete and confirm))
    if not backup_dir or not backup_dir.exists() or not backup_dir.is_dir():
        report.errors.append("backup_dir_missing")
        return report
    files: list[Path] = []
    for current, dirnames, filenames in os.walk(backup_dir):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        for filename in filenames:
            path = Path(current) / filename
            resolved = _resolve(path)
            if resolved and resolved.is_file() and _is_under(resolved, backup_dir):
                files.append(resolved)
    files.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
    keep_count = max(0, int(keep))
    valid_files = [path for path in files if classify_backup_cleanup_file(path, backup_dir)[0]]
    kept = set(valid_files[:keep_count])
    deleted_count = 0
    for path in files:
        try:
            stat = path.stat()
        except OSError as exc:
            report.errors.append(f"stat_failed:{type(exc).__name__}:{path.name}")
            continue
        valid_backup, backup_reason = classify_backup_cleanup_file(path, backup_dir)
        if path in kept:
            status, reason = "kept", "latest_backup_kept"
        elif not valid_backup:
            status, reason = "blocked", backup_reason
        elif deleted_count >= int(max_delete_files):
            status, reason = "blocked", "max_delete_files_reached"
        else:
            status, reason = "candidate", "older_backup"
        item = BackupCleanupFile(str(path), int(stat.st_size), float(stat.st_mtime), status, reason)
        if delete and confirm and status == "candidate":
            try:
                path.unlink()
                item.status = "deleted"
                item.reason = "older_backup_deleted"
                report.deleted_files += 1
                report.deleted_bytes += int(stat.st_size)
                deleted_count += 1
            except OSError as exc:
                item.status = "blocked"
                item.reason = f"delete_failed:{type(exc).__name__}"
                report.errors.append(f"{item.reason}:{path.name}")
        report.files.append(item)
    return report
