"""Safe Railway volume audit and TTL cleanup helpers.

This module is intentionally conservative. It only cleans generated artifact
extensions inside configured file-volume targets and blocks databases, config,
secrets, source files, hidden files, and paths referenced by active jobs.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


GENERATED_ARTIFACT_EXTENSIONS = {
    ".aac",
    ".ass",
    ".bin",
    ".gif",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".mov",
    ".mp3",
    ".mp4",
    ".png",
    ".srt",
    ".tmp",
    ".vtt",
    ".wav",
    ".webm",
    ".webp",
    ".zip",
}
PROTECTED_EXTENSIONS = {
    ".cfg",
    ".conf",
    ".db",
    ".env",
    ".ini",
    ".json",
    ".key",
    ".log",
    ".md",
    ".pem",
    ".py",
    ".sqlite",
    ".sqlite3",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
PROTECTED_NAME_TOKENS = {
    ".env",
    "account",
    "alembic",
    "config",
    "database",
    "finance",
    "ledger",
    "payos",
    "payment",
    "procfile",
    "railway",
    "secret",
    "setting",
    "sqlite",
    "token",
    "user",
    "wallet",
}


@dataclass
class StorageCleanupFile:
    path: str
    root: str
    size_bytes: int
    age_seconds: int
    status: str
    reason: str


@dataclass
class StorageCleanupReport:
    base_dir: str
    roots: list[str]
    ttl_seconds: int
    dry_run: bool = True
    files_scanned: int = 0
    bytes_scanned: int = 0
    files_eligible: int = 0
    bytes_eligible: int = 0
    files_deleted: int = 0
    bytes_deleted: int = 0
    files_blocked: int = 0
    files_young: int = 0
    errors: list[str] = field(default_factory=list)
    samples: list[StorageCleanupFile] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "base_dir": self.base_dir,
            "roots": list(self.roots),
            "ttl_seconds": int(self.ttl_seconds),
            "dry_run": bool(self.dry_run),
            "files_scanned": int(self.files_scanned),
            "bytes_scanned": int(self.bytes_scanned),
            "files_eligible": int(self.files_eligible),
            "bytes_eligible": int(self.bytes_eligible),
            "files_deleted": int(self.files_deleted),
            "bytes_deleted": int(self.bytes_deleted),
            "files_blocked": int(self.files_blocked),
            "files_young": int(self.files_young),
            "errors": list(self.errors),
            "samples": [item.__dict__ for item in self.samples],
        }


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


def cleanup_roots(base_dir: str, extra_targets: Iterable[str] | None = None) -> list[Path]:
    base = _resolve(base_dir)
    if not base:
        return []
    candidates = [base / "worker_results", base / "tmp", base]
    for target in extra_targets or []:
        target_path = _resolve(target)
        if target_path:
            candidates.append(target_path)
    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = _resolve(candidate)
        if not resolved or str(resolved) in seen:
            continue
        if resolved == base or _is_under(resolved, base):
            roots.append(resolved)
            seen.add(str(resolved))
    return roots


def _path_has_protected_name(path: Path) -> bool:
    parts = [part.lower() for part in path.parts]
    name = path.name.lower()
    if name.startswith("."):
        return True
    return any(token in name or token in parts for token in PROTECTED_NAME_TOKENS)


def classify_cleanup_file(
    path: Path,
    *,
    roots: list[Path],
    ttl_seconds: int,
    protected_paths: set[str] | None = None,
    now: float | None = None,
) -> StorageCleanupFile:
    now_ts = float(now if now is not None else time.time())
    resolved = _resolve(path)
    root = next((item for item in roots if resolved and _is_under(resolved, item)), None)
    if not resolved or not root:
        return StorageCleanupFile(str(path), "", 0, 0, "blocked", "outside_cleanup_targets")
    try:
        stat = resolved.stat()
    except OSError as exc:
        return StorageCleanupFile(str(resolved), str(root), 0, 0, "blocked", f"stat_failed:{type(exc).__name__}")
    age = max(0, int(now_ts - float(stat.st_mtime)))
    size = max(0, int(stat.st_size))
    lower_suffix = resolved.suffix.lower()
    normalized = str(resolved).replace("\\", "/")
    protected = {str(item).replace("\\", "/") for item in (protected_paths or set())}
    if normalized in protected:
        status, reason = "blocked", "active_job_reference"
    elif _path_has_protected_name(resolved):
        status, reason = "blocked", "protected_name"
    elif lower_suffix in PROTECTED_EXTENSIONS:
        status, reason = "blocked", "protected_extension"
    elif lower_suffix not in GENERATED_ARTIFACT_EXTENSIONS:
        status, reason = "blocked", "unsupported_extension"
    elif age < int(ttl_seconds):
        status, reason = "young", "younger_than_ttl"
    else:
        status, reason = "eligible", "ttl_expired_generated_artifact"
    return StorageCleanupFile(str(resolved), str(root), size, age, status, reason)


def audit_storage_cleanup(
    *,
    base_dir: str,
    ttl_seconds: int,
    protected_paths: set[str] | None = None,
    delete: bool = False,
    confirm_delete: bool = False,
    max_scan_files: int = 10000,
    max_delete_files: int = 500,
    now: float | None = None,
) -> StorageCleanupReport:
    roots = cleanup_roots(base_dir)
    report = StorageCleanupReport(
        base_dir=str(_resolve(base_dir) or base_dir),
        roots=[str(root) for root in roots],
        ttl_seconds=max(1, int(ttl_seconds)),
        dry_run=not (delete and confirm_delete),
    )
    if not roots:
        report.errors.append("no_cleanup_roots")
        return report
    scanned_paths: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for current, dirnames, filenames in os.walk(root):
            current_path = _resolve(current)
            if not current_path:
                continue
            dirnames[:] = [name for name in dirnames if not name.startswith(".")]
            for filename in filenames:
                path = current_path / filename
                normalized = str(_resolve(path) or path)
                if normalized in scanned_paths:
                    continue
                scanned_paths.add(normalized)
                if report.files_scanned >= int(max_scan_files):
                    report.errors.append("max_scan_files_reached")
                    return report
                item = classify_cleanup_file(
                    path,
                    roots=roots,
                    ttl_seconds=report.ttl_seconds,
                    protected_paths=protected_paths or set(),
                    now=now,
                )
                report.files_scanned += 1
                report.bytes_scanned += int(item.size_bytes)
                if item.status == "eligible":
                    report.files_eligible += 1
                    report.bytes_eligible += int(item.size_bytes)
                elif item.status == "young":
                    report.files_young += 1
                else:
                    report.files_blocked += 1
                if len(report.samples) < 20 and item.status in {"eligible", "blocked", "young"}:
                    report.samples.append(item)
                if delete and confirm_delete and item.status == "eligible":
                    if report.files_deleted >= int(max_delete_files):
                        report.errors.append("max_delete_files_reached")
                        continue
                    try:
                        Path(item.path).unlink()
                        report.files_deleted += 1
                        report.bytes_deleted += int(item.size_bytes)
                    except OSError as exc:
                        report.errors.append(f"delete_failed:{type(exc).__name__}:{os.path.basename(item.path)}")
    return report


def disk_usage_for_path(path: str) -> dict:
    resolved = _resolve(path)
    if not resolved or not resolved.exists():
        return {"ok": False, "path": str(path or ""), "reason": "missing"}
    try:
        usage = shutil.disk_usage(str(resolved))
        return {
            "ok": True,
            "path": str(resolved),
            "total": int(usage.total),
            "used": int(usage.used),
            "free": int(usage.free),
            "used_percent": round((float(usage.used) / float(usage.total)) * 100, 2) if usage.total else 0,
        }
    except OSError as exc:
        return {"ok": False, "path": str(resolved), "reason": type(exc).__name__}
