import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from services import artifact_storage, storage_cleanup, storage_migration, storage_weekly


REPO = Path(__file__).resolve().parents[1]


def _write(path: Path, payload: bytes = b"artifact", *, age_seconds: int = 48 * 3600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))


def _cfg() -> artifact_storage.ArtifactStorageConfig:
    return artifact_storage.ArtifactStorageConfig(
        backend="vps_sftp",
        vps_host="vps.internal",
        vps_base_dir="/opt/toanaas-storage",
        public_base_url="https://cdn.example.com/toanaas",
    )


def _weekly_cfg(base: Path) -> storage_weekly.WeeklyStorageConfig:
    return storage_weekly.WeeklyStorageConfig(
        enabled=True,
        base_dir=str(base),
        day="sunday",
        hour=3,
        minute=30,
        timezone_name="Asia/Ho_Chi_Minh",
        railway_backup_keep=5,
        vps_backup_keep_weeks=12,
        tmp_ttl_seconds=6 * 3600,
        generated_ttl_seconds=24 * 3600,
        max_scan_files=1000,
        max_delete_files=100,
    )


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _ok_uploader(local_path, remote_path, config):
    return {"ok": True, "remote_path": remote_path}


def _fail_uploader(local_path, remote_path, config):
    return {"ok": False, "reason": "upload_failed_for_test"}


def _ok_verifier(local_path, metadata, config):
    return {
        "ok": True,
        "remote_size": Path(local_path).stat().st_size,
        "remote_hash": artifact_storage.artifact_sha256(local_path),
        "size_matches": True,
        "hash_matches": True,
        "reason": "remote_verified",
    }


def _hash_mismatch_verifier(local_path, metadata, config):
    return {
        "ok": False,
        "remote_size": Path(local_path).stat().st_size,
        "remote_hash": "bad-hash",
        "size_matches": True,
        "hash_matches": False,
        "reason": "remote_hash_mismatch",
    }


def test_storage5_classifier_accepts_known_startup_db_backup_only_inside_backups(tmp_path):
    base = tmp_path / "data"
    backup_dir = base / "backups"
    valid = backup_dir / "toandaas_system_20260707_033000_startup.db"
    invalid = backup_dir / "old.db"
    outside = base / "toandaas_system_20260707_033000_startup.db"
    for path in (valid, invalid, outside):
        _write(path, b"db")

    assert storage_migration.classify_backup_cleanup_file(valid, backup_dir) == (True, "known_toan_aas_db_backup")
    assert storage_migration.classify_backup_cleanup_file(invalid, backup_dir) == (False, "unsupported_backup_name")
    assert storage_migration.classify_backup_cleanup_file(outside, backup_dir) == (False, "outside_backup_dir")


def test_storage5_current_db_elsewhere_is_not_backup_cleanup_candidate(tmp_path):
    base = tmp_path / "data"
    current_db = base / "toandaas_system.db"
    arbitrary_db = base / "backups" / "old.db"
    _write(current_db, b"current")
    _write(arbitrary_db, b"old", age_seconds=10 * 3600)

    report = storage_migration.backup_cleanup_report(base, keep=1, delete=True, confirm=True)

    assert report.deleted_files == 0
    assert current_db.exists()
    assert arbitrary_db.exists()
    assert any(item.reason == "unsupported_backup_name" for item in report.files)


def test_storage5_media_uploads_to_vps_verifies_before_railway_delete(tmp_path):
    base = tmp_path / "data"
    media = base / "dub_assets" / "old.mp4"
    _write(media, b"video")
    conn = _conn()

    report = storage_weekly.run_weekly_maintenance(
        config=_weekly_cfg(base),
        artifact_config=_cfg(),
        protected_paths=set(),
        running_paths=set(),
        conn=conn,
        confirm=True,
        uploader=_ok_uploader,
        verifier=_ok_verifier,
        now=datetime(2026, 7, 5, 0, 0, tzinfo=timezone.utc),
    )

    assert report.status == "completed"
    assert report.files_migrated == 1
    assert report.files_verified >= 1
    assert report.railway_copies_deleted == 1
    assert report.bytes_freed >= len(b"video")
    assert not media.exists()


def test_storage5_upload_failure_keeps_railway_media(tmp_path):
    base = tmp_path / "data"
    media = base / "video" / "keep.mp4"
    _write(media, b"video")

    report = storage_weekly.run_weekly_maintenance(
        config=_weekly_cfg(base),
        artifact_config=_cfg(),
        protected_paths=set(),
        running_paths=set(),
        conn=_conn(),
        confirm=True,
        uploader=_fail_uploader,
        verifier=_ok_verifier,
    )

    assert media.exists()
    assert report.railway_copies_deleted == 0
    assert report.failed_uploads >= 1


def test_storage5_hash_mismatch_keeps_railway_media(tmp_path):
    base = tmp_path / "data"
    media = base / "worker_results" / "keep.mp4"
    _write(media, b"video")

    report = storage_weekly.run_weekly_maintenance(
        config=_weekly_cfg(base),
        artifact_config=_cfg(),
        protected_paths=set(),
        running_paths=set(),
        conn=_conn(),
        confirm=True,
        uploader=_ok_uploader,
        verifier=_hash_mismatch_verifier,
    )

    assert media.exists()
    assert report.railway_copies_deleted == 0
    assert report.failed_verifies >= 1


def test_storage5_active_job_reference_keeps_railway_media(tmp_path):
    base = tmp_path / "data"
    media = base / "worker_results" / "active.mp4"
    _write(media, b"active")
    normalized = str(media.resolve()).replace("\\", "/")

    report = storage_weekly.run_weekly_maintenance(
        config=_weekly_cfg(base),
        artifact_config=_cfg(),
        protected_paths={normalized},
        running_paths={normalized},
        conn=_conn(),
        confirm=True,
        uploader=_ok_uploader,
        verifier=_ok_verifier,
    )

    assert media.exists()
    assert report.railway_copies_deleted == 0
    assert report.active_refs_protected >= 1


def test_storage5_weekly_run_is_idempotent_per_week(tmp_path):
    base = tmp_path / "data"
    conn = _conn()
    now = datetime(2026, 7, 5, 0, 0, tzinfo=timezone.utc)

    first = storage_weekly.run_weekly_maintenance(
        config=_weekly_cfg(base),
        artifact_config=_cfg(),
        conn=conn,
        confirm=True,
        uploader=_ok_uploader,
        verifier=_ok_verifier,
        now=now,
    )
    second = storage_weekly.run_weekly_maintenance(
        config=_weekly_cfg(base),
        artifact_config=_cfg(),
        conn=conn,
        confirm=True,
        uploader=_ok_uploader,
        verifier=_ok_verifier,
        now=now,
    )

    assert first.status == "completed"
    assert second.status == "skipped"
    assert second.reason == "already_ran_this_week"


def test_storage5_railway_keeps_latest_5_backups_and_archives_older_first(tmp_path):
    base = tmp_path / "data"
    backups = []
    uploads = []

    def tracking_uploader(local_path, remote_path, config):
        uploads.append((local_path, remote_path))
        return {"ok": True, "remote_path": remote_path}

    for idx in range(7):
        path = base / "backups" / f"toandaas_system_2026070{idx + 1}_033000_startup.db"
        _write(path, f"backup-{idx}".encode("utf-8"), age_seconds=(idx + 1) * 3600)
        backups.append(path)

    report = storage_weekly.archive_old_backups_to_vps(
        base,
        config=_cfg(),
        keep=5,
        confirm=True,
        conn=_conn(),
        week_key_value="2026-W27",
        uploader=tracking_uploader,
        verifier=_ok_verifier,
    )

    assert report.archived_files == 2
    assert report.deleted_files == 2
    assert all(path.exists() for path in backups[:5])
    assert not backups[5].exists()
    assert not backups[6].exists()
    assert len(uploads) == 2
    assert all("/backups/railway/" in remote for _, remote in uploads)


def test_storage5_backup_verify_failure_keeps_local_backup(tmp_path):
    base = tmp_path / "data"
    keep = base / "backups" / "toandaas_system_20260707_033000_startup.db"
    old = base / "backups" / "toandaas_system_20260701_033000_startup.db"
    _write(keep, b"keep", age_seconds=1 * 3600)
    _write(old, b"old", age_seconds=10 * 3600)

    report = storage_weekly.archive_old_backups_to_vps(
        base,
        config=_cfg(),
        keep=1,
        confirm=True,
        conn=_conn(),
        week_key_value="2026-W27",
        uploader=_ok_uploader,
        verifier=_hash_mismatch_verifier,
    )

    assert old.exists()
    assert report.deleted_files == 0
    assert report.failed_verifies == 1


def test_storage5_vps_weekly_retention_keeps_latest_12_week_keys(tmp_path):
    conn = _conn()
    storage_weekly.ensure_weekly_tables(conn)
    for week in range(1, 15):
        storage_weekly.record_backup_archive(
            conn,
            local_path=f"/data/backups/backup-{week}.db",
            remote_path=f"/opt/toanaas-storage/backups/railway/2026/{week:02d}/backup.db",
            size_bytes=week,
            artifact_hash=f"hash-{week}",
            key=f"2026-W{week:02d}",
        )
    deleted = []

    report = storage_weekly.enforce_vps_weekly_retention(
        conn,
        keep_weeks=12,
        config=_cfg(),
        confirm=True,
        deleter=lambda remote_path, config: deleted.append(remote_path) or {"ok": True},
    )

    assert report["candidates"] == 2
    assert report["deleted_remote"] == 2
    assert len(deleted) == 2


def test_storage5_empty_safe_media_dirs_removed_but_backups_root_kept(tmp_path):
    base = tmp_path / "data"
    removable = base / "video" / "empty" / "nested"
    backups = base / "backups" / "empty"
    removable.mkdir(parents=True)
    backups.mkdir(parents=True)

    report = storage_weekly.remove_empty_safe_directories(base, confirm=True)

    assert report["removed"] >= 1
    assert not removable.exists()
    assert (base / "backups").exists()


def test_storage5_cleanup_never_deletes_db_payment_secret_source_files(tmp_path):
    base = tmp_path / "data"
    protected = [
        base / "toandaas_system.db",
        base / "payment.sqlite3",
        base / "wallet.db",
        base / ".env",
        base / "config.yaml",
        base / "bot.py",
    ]
    for path in protected:
        _write(path, b"protected", age_seconds=10 * 24 * 3600)

    report = storage_cleanup.audit_storage_cleanup(
        base_dir=str(base),
        ttl_seconds=1,
        tmp_ttl_seconds=1,
        delete=True,
        confirm_delete=True,
    )

    assert report.files_deleted == 0
    assert all(path.exists() for path in protected)


def test_storage5_commands_env_and_scheduler_registered_static():
    source = (REPO / "bot.py").read_text(encoding="utf-8")
    assert 'CommandHandler("storage_weekly_status", cmd_storage_weekly_status)' in source
    assert 'CommandHandler("storage_weekly_run_preview", cmd_storage_weekly_run_preview)' in source
    assert 'CommandHandler("storage_weekly_run", cmd_storage_weekly_run)' in source
    assert "STORAGE_WEEKLY_MAINTENANCE_ENABLED" in source
    assert "storage_weekly_maintenance_loop" in source
    assert "storage_weekly_task = asyncio.create_task(storage_weekly_maintenance_loop())" in source


def test_storage5_does_not_touch_unrelated_runtime_static():
    service = (REPO / "services" / "storage_weekly.py").read_text(encoding="utf-8").lower()
    migration = (REPO / "services" / "storage_migration.py").read_text(encoding="utf-8").lower()
    combined = service + "\n" + migration
    forbidden = ["payos", "pricing", "subtitle_dub", "suno", "voice_clone", "linkdl", "webapp"]
    assert not any(token in combined for token in forbidden)
