import os
import sqlite3
import time
from pathlib import Path

import bot
from services import artifact_storage, storage_cleanup, storage_migration


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


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _ok_uploader(local_path, remote_path, config):
    return {"ok": True, "remote_path": remote_path}


def _ok_verifier(local_path, metadata, config):
    return {
        "ok": True,
        "remote_size": Path(local_path).stat().st_size,
        "remote_hash": artifact_storage.artifact_sha256(local_path),
        "size_matches": True,
        "hash_matches": True,
        "reason": "remote_verified",
    }


def test_storage_migrate_preview_detects_dub_assets_and_backups_sizes(tmp_path):
    base = tmp_path / "data"
    dub = base / "dub_assets" / "old-dub.mp4"
    backup = base / "backups" / "backup-1.zip"
    _write(dub, b"x" * 120)
    _write(backup, b"y" * 117)

    report = storage_migration.scan_migration_candidates(base, config=_cfg())
    targets = {Path(item.path).name: item for item in report.targets}

    assert targets["dub_assets"].files == 1
    assert targets["dub_assets"].size_bytes == 120
    assert targets["backups"].files == 1
    assert targets["backups"].size_bytes == 117
    assert report.candidate_files == 1
    assert "/dub_assets/" in report.candidates[0].remote_target.replace("\\", "/")


def test_storage_migrate_uploads_media_to_vps_and_verifies_hash_size(tmp_path):
    base = tmp_path / "data"
    media = base / "voice_assets" / "voice.wav"
    _write(media, b"voice")
    conn = _conn()

    report = storage_migration.migrate_existing_assets(
        base,
        config=_cfg(),
        conn=conn,
        delete_local=False,
        confirm=True,
        uploader=_ok_uploader,
        verifier=_ok_verifier,
    )

    assert media.exists()
    assert report.uploaded_files == 1
    assert report.verified_files == 1
    rows = storage_migration.migration_records_for_query(conn, "voice.wav")
    assert rows and rows[0]["verified"] == 1
    assert rows[0]["remote_path"].endswith("/voice.wav")


def test_storage_migrate_local_delete_blocked_when_remote_missing(tmp_path):
    base = tmp_path / "data"
    media = base / "translation_assets" / "translate.srt"
    _write(media, b"subtitle")

    report = storage_migration.migrate_existing_assets(
        base,
        config=_cfg(),
        conn=_conn(),
        delete_local=True,
        confirm=True,
        uploader=_ok_uploader,
        verifier=lambda *_args: {"ok": False, "size_matches": False, "hash_matches": False, "reason": "remote_missing"},
    )

    assert media.exists()
    assert report.deleted_files == 0
    assert any(item.reason == "remote_missing" for item in report.candidates)


def test_storage_migrate_local_delete_allowed_only_after_verified_remote(tmp_path):
    base = tmp_path / "data"
    media = base / "subtitle_assets" / "subtitle.vtt"
    _write(media, b"subtitle")

    report = storage_migration.migrate_existing_assets(
        base,
        config=_cfg(),
        conn=_conn(),
        delete_local=True,
        confirm=True,
        uploader=_ok_uploader,
        verifier=_ok_verifier,
    )

    assert not media.exists()
    assert report.verified_files == 1
    assert report.deleted_files == 1


def test_storage_migrate_db_sqlite_never_deleted_or_uploaded(tmp_path):
    base = tmp_path / "data"
    db_file = base / "dub_assets" / "wallet.db"
    sqlite_file = base / "voice_assets" / "finance.sqlite3"
    _write(db_file, b"db")
    _write(sqlite_file, b"sqlite")

    report = storage_migration.migrate_existing_assets(
        base,
        config=_cfg(),
        conn=_conn(),
        delete_local=True,
        confirm=True,
        uploader=lambda *_args: (_ for _ in ()).throw(AssertionError("protected DB must not upload")),
        verifier=_ok_verifier,
    )

    assert db_file.exists()
    assert sqlite_file.exists()
    assert report.uploaded_files == 0
    assert report.protected_files == 2


def test_storage_backup_cleanup_keep_5_deletes_only_older_backups(tmp_path):
    base = tmp_path / "data"
    backups = []
    for idx in range(7):
        path = base / "backups" / f"backup-{idx}.zip"
        _write(path, f"backup-{idx}".encode(), age_seconds=(idx + 1) * 3600)
        backups.append(path)

    report = storage_migration.backup_cleanup_report(base, keep=5, delete=True, confirm=True)

    assert report.deleted_files == 2
    assert all(path.exists() for path in backups[:5])
    assert not backups[5].exists()
    assert not backups[6].exists()


def test_storage_active_job_reference_protection_preserved_without_metadata_conn(tmp_path):
    base = tmp_path / "data"
    active = base / "worker_results" / "active.mp4"
    _write(active, b"active")

    report = storage_migration.migrate_existing_assets(
        base,
        config=_cfg(),
        protected_paths={str(active.resolve()).replace("\\", "/")},
        conn=None,
        delete_local=True,
        confirm=True,
        uploader=_ok_uploader,
        verifier=_ok_verifier,
    )

    assert active.exists()
    assert report.deleted_files == 0
    assert any(item.active_reference and item.reason == "metadata_record_required" for item in report.candidates)
    cleanup = storage_cleanup.audit_storage_cleanup(
        base_dir=str(base),
        ttl_seconds=1,
        protected_paths={str(active.resolve()).replace("\\", "/")},
        delete=True,
        confirm_delete=True,
    )
    assert active.exists()
    assert any(item.reason == "active_job_reference" for item in cleanup.samples)


def test_storage_audit_and_storage3_commands_registered():
    source = (REPO / "bot.py").read_text(encoding="utf-8")
    assert 'CommandHandler("storage_audit", cmd_storage_audit)' in source
    assert 'CommandHandler("storage_migrate_preview", cmd_storage_migrate_preview)' in source
    assert 'CommandHandler("storage_migrate_run", cmd_storage_migrate_run)' in source
    assert 'CommandHandler("storage_backup_cleanup_preview", cmd_storage_backup_cleanup_preview)' in source
    assert 'CommandHandler("storage_backup_cleanup_run", cmd_storage_backup_cleanup_run)' in source
    assert 'CommandHandler("storage_asset_refs", cmd_storage_asset_refs)' in source


def test_storage_migration_commands_do_not_block_the_telegram_webhook_event_loop():
    source = (REPO / "bot.py").read_text(encoding="utf-8")
    preview = source[
        source.index("async def cmd_storage_migrate_preview"):
        source.index("async def cmd_storage_migrate_run")
    ]
    run = source[
        source.index("async def cmd_storage_migrate_run"):
        source.index("async def cmd_storage_backup_cleanup_preview")
    ]
    assert "async def _run_storage_migration_background" in source
    background_start = source.index("async def _run_storage_migration_background")
    background = source[
        background_start:
        source.index("async def cmd_storage_migrate_preview", background_start)
    ]

    assert "await asyncio.to_thread(run_storage_migration_preview_report)" in preview
    assert "STORAGE_MIGRATION_BACKGROUND_TASK" in run
    assert "_run_storage_migration_background(update)" in run
    assert "asyncio.create_task" in run or "create_task(runner" in run
    assert "await _run_storage_migration_background" not in run
    assert "await asyncio.to_thread(run_storage_migration_report, confirm=True)" in background
    assert "report = run_storage_migration_report(confirm=True)" not in run


def test_storage3_does_not_touch_payos_wallet_pricing_static():
    service = (REPO / "services" / "storage_migration.py").read_text(encoding="utf-8").lower()
    assert "payos" not in service
    assert "wallet" not in service
    assert "price" not in service
