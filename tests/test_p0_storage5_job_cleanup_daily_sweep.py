import os
import sqlite3
import time
from pathlib import Path

from services import storage_maintenance


def _old(path: Path, payload: bytes = b"x", age: int = 10) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))


def _config(root: Path, **kwargs) -> storage_maintenance.StorageConfig:
    return storage_maintenance.StorageConfig(
        backend="railway",
        storage_root=root,
        backup_root=root / "backups",
        railway_root=root,
        vps_root=root.parent / "vps",
        temp_ttl_seconds=5,
        cache_ttl_seconds=5,
        partial_ttl_seconds=5,
        **kwargs,
    )


def test_daily_ttl_cleanup_preserves_new_files_and_backups(tmp_path):
    root = tmp_path / "railway"
    old_temp = root / "tmp" / "old.mp4"
    new_temp = root / "tmp" / "new.mp4"
    old_cache = root / "cache" / "old.json"
    partial = root / "workspaces" / "empty.partial"
    backup = root / "backups" / "toandaas_system_20260713_033000_startup.db"
    _old(old_temp)
    new_temp.parent.mkdir(parents=True, exist_ok=True)
    new_temp.write_bytes(b"new")
    _old(old_cache)
    _old(partial, b"")
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup) as conn:
        conn.execute("create table t (id integer)")

    report = storage_maintenance.run_daily(_config(root), execute=True)
    assert report.status == "completed"
    assert not old_temp.exists()
    assert not old_cache.exists()
    assert not partial.exists()
    assert new_temp.exists()
    assert backup.exists()


def test_active_and_undelivered_paths_are_protected(tmp_path):
    root = tmp_path / "railway"
    running = root / "workspaces" / "running.mp4"
    undelivered = root / "artifacts" / "undelivered.mp4"
    _old(running)
    _old(undelivered)
    report = storage_maintenance.plan_daily(
        _config(root, running_paths=(str(running),), undelivered_paths=(str(undelivered),))
    )
    protected = {item.path: item.reason for item in report.items if item.status == "protected"}
    assert protected[str(running)] == "active_job"
    assert protected[str(undelivered)] == "undelivered_final_artifact"


def test_job_cleanup_requires_delivery_receipt_and_respects_failed_grace(tmp_path):
    root = tmp_path / "storage"
    delivered = root / "workspaces" / "delivered-job"
    _old(delivered / "intermediate.wav")
    result = storage_maintenance.cleanup_job_workspace(
        delivered,
        {
            "status": "completed",
            "delivery_persisted": True,
            "receipt_persisted": True,
            "delivery_message_id": "123",
            "final_artifact_valid": True,
        },
        execute=True,
        allowed_roots=[root / "workspaces"],
    )
    assert result["deleted"] is True
    assert not delivered.exists()

    failed = root / "workspaces" / "failed-job"
    _old(failed / "debug.log")
    recent = storage_maintenance.cleanup_job_workspace(
        failed,
        {"status": "failed", "failed_at": time.time()},
        execute=True,
        allowed_roots=[root / "workspaces"],
    )
    assert recent["reason"] == "failed_job_debug_grace"
    assert failed.exists()

    old_failed = storage_maintenance.cleanup_job_workspace(
        failed,
        {"status": "failed", "failed_at": time.time() - 10},
        execute=True,
        allowed_roots=[root / "workspaces"],
        failed_grace_seconds=5,
    )
    assert old_failed["deleted"] is True


def test_daily_lock_prevents_overlap_and_schedule_uses_vietnam_time(tmp_path):
    root = tmp_path / "railway"
    config = _config(root)
    config.lock_path.parent.mkdir(parents=True, exist_ok=True)
    config.lock_path.write_text("held", encoding="ascii")
    try:
        report = storage_maintenance.run_daily(config, execute=True)
        assert report.status == "skipped_locked"
    finally:
        config.lock_path.unlink(missing_ok=True)
    schedule = storage_maintenance.next_run(config, "daily")
    assert "+07:00" in schedule
    assert storage_maintenance.maintenance_status(config)["timezone"] == "Asia/Ho_Chi_Minh"
