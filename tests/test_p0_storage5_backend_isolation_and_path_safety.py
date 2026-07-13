import os
import time
from pathlib import Path

from services import storage_maintenance


def _config(root: Path, backend: str, other: Path) -> storage_maintenance.StorageConfig:
    return storage_maintenance.StorageConfig(
        backend=backend,
        storage_root=root,
        backup_root=root / "backups",
        railway_root=root if backend == "railway" else other,
        vps_root=other if backend == "railway" else root,
        temp_ttl_seconds=1,
        cache_ttl_seconds=1,
        partial_ttl_seconds=1,
    )


def _old(path: Path, payload: bytes = b"old") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    stamp = time.time() - 10
    os.utime(path, (stamp, stamp))


def test_railway_and_vps_cleanup_are_backend_local(tmp_path):
    railway = tmp_path / "railway"
    vps = tmp_path / "vps"
    railway_file = railway / "tmp" / "railway.tmp"
    vps_file = vps / "tmp" / "vps.tmp"
    _old(railway_file)
    _old(vps_file)

    railway_report = storage_maintenance.run_daily(_config(railway, "railway", vps), execute=True)
    assert railway_report.status == "completed"
    assert not railway_file.exists()
    assert vps_file.exists()

    vps_report = storage_maintenance.run_daily(_config(vps, "vps", railway), execute=True)
    assert vps_report.status == "completed"
    assert not vps_file.exists()


def test_backend_root_mismatch_blocks_deletion(tmp_path):
    railway = tmp_path / "railway"
    vps = tmp_path / "vps"
    candidate = vps / "tmp" / "should-stay.tmp"
    _old(candidate)
    config = storage_maintenance.StorageConfig(
        backend="railway",
        storage_root=vps,
        backup_root=vps / "backups",
        railway_root=railway,
        vps_root=vps,
        temp_ttl_seconds=1,
    )
    report = storage_maintenance.run_daily(config, execute=True)
    assert report.status == "blocked"
    assert "railway_root_matches_vps_root" in report.errors
    assert candidate.exists()


def test_symlink_escape_is_blocked_and_root_is_never_a_candidate(tmp_path):
    root = tmp_path / "storage"
    outside = tmp_path / "outside.tmp"
    _old(outside)
    link = root / "tmp" / "escape.tmp"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        return
    config = storage_maintenance.StorageConfig(
        backend="vps",
        storage_root=root,
        backup_root=root / "backups",
        railway_root=tmp_path / "railway",
        vps_root=root,
        temp_ttl_seconds=1,
    )
    report = storage_maintenance.run_daily(config, execute=True)
    assert outside.exists()
    assert any("symlink" in error for error in report.errors)
    root_report = storage_maintenance.cleanup_job_workspace(root, {"status": "completed"}, execute=True, allowed_roots=[root])
    assert root_report["allowed"] is False
    assert root_report["reason"] == "workspace_outside_allowlist"
