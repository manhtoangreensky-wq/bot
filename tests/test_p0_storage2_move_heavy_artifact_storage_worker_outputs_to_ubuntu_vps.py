import os
import re
import time
from pathlib import Path

from services import artifact_storage, storage_cleanup
from services import remote_worker_api


REPO = Path(__file__).resolve().parents[1]


def _write_old(path: Path, *, age_seconds: int = 48 * 3600, payload: bytes = b"artifact") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))


def test_local_backend_still_works(tmp_path):
    path = tmp_path / "worker_job_47_final_output.mp4"
    path.write_bytes(b"mp4")
    cfg = artifact_storage.ArtifactStorageConfig(backend="local")

    meta = artifact_storage.store_artifact(path, config=cfg, product_area="worker_results", job_id=47)

    assert meta["ok"] is True
    assert meta["backend"] == "local"
    assert meta["local_path"] == str(path)
    assert meta["remote_path"] == ""
    assert path.exists()
    assert artifact_storage.delivery_reference(meta)["kind"] == "local_path"


def test_vps_backend_uploads_mp4_mp3_srt_metadata(tmp_path):
    cfg = artifact_storage.ArtifactStorageConfig(
        backend="vps_sftp",
        vps_host="10.0.0.5",
        vps_user="toanaas",
        vps_base_dir="/opt/toanaas-storage",
        vps_ssh_key_path="/run/secrets/toanaas_key",
        public_base_url="https://cdn.example.com/toanaas",
        ttl_hours=24,
    )
    uploaded = []

    def fake_uploader(local_path, remote_path, config):
        uploaded.append((local_path, remote_path, config.backend))
        return {"ok": True, "remote_path": remote_path}

    for suffix in (".mp4", ".mp3", ".srt"):
        path = tmp_path / f"worker_job_47_final_output{suffix}"
        path.write_bytes(f"artifact-{suffix}".encode())
        meta = artifact_storage.store_artifact(
            path,
            config=cfg,
            product_area="worker_results",
            job_id=47,
            uploader=fake_uploader,
            now=1_700_000_000,
        )
        public = artifact_storage.public_metadata(meta)
        assert meta["ok"] is True
        assert meta["backend"] == "vps_sftp"
        assert meta["remote_path"].startswith("/opt/toanaas-storage/worker_results/")
        assert meta["public_url"].startswith("https://cdn.example.com/toanaas/worker_results/")
        assert meta["artifact_size"] == path.stat().st_size
        assert len(meta["artifact_hash"]) == 64
        assert public["public_url"] == meta["public_url"]
        assert "10.0.0.5" not in repr(public)
        assert "toanaas_key" not in repr(public)
    assert len(uploaded) == 3


def test_local_temp_copy_deleted_after_vps_upload_when_safe(tmp_path):
    path = tmp_path / "worker_job_48_final_output.mp4"
    path.write_bytes(b"mp4")
    cfg = artifact_storage.ArtifactStorageConfig(
        backend="vps_sftp",
        vps_host="vps.internal",
        vps_base_dir="/opt/toanaas-storage",
        public_base_url="https://cdn.example.com",
    )

    meta = artifact_storage.store_artifact(
        path,
        config=cfg,
        product_area="worker_results",
        job_id=48,
        delete_local_after_upload=True,
        uploader=lambda _local, remote, _cfg: {"ok": True, "remote_path": remote},
    )

    assert meta["ok"] is True
    assert meta["local_deleted_after_upload"] is True
    assert meta["local_path"] == ""
    assert meta["original_local_path"].endswith("worker_job_48_final_output.mp4")
    assert not path.exists()
    assert artifact_storage.delivery_reference(meta)["kind"] == "public_url"


def test_active_job_files_are_not_cleanup_deleted(tmp_path):
    base = tmp_path / "files"
    active = base / "worker_results" / "worker_job_49_final_output.mp4"
    _write_old(active, age_seconds=7 * 24 * 3600)

    report = storage_cleanup.audit_storage_cleanup(
        base_dir=str(base),
        ttl_seconds=24 * 3600,
        protected_paths={str(active.resolve()).replace("\\", "/")},
        delete=True,
        confirm_delete=True,
    )

    assert active.exists()
    assert report.files_deleted == 0
    assert any(item.reason == "active_job_reference" for item in report.samples)


def test_db_sqlite_wallet_payment_finance_files_are_never_deleted(tmp_path):
    base = tmp_path / "files"
    protected = [
        base / "wallet.db",
        base / "payment.sqlite",
        base / "finance.sqlite3",
        base / "user_config.json",
        base / ".env",
        base / "railway.toml",
        base / "bot.py",
    ]
    for path in protected:
        _write_old(path, age_seconds=9 * 24 * 3600)

    report = storage_cleanup.audit_storage_cleanup(
        base_dir=str(base),
        ttl_seconds=24 * 3600,
        delete=True,
        confirm_delete=True,
    )

    assert all(path.exists() for path in protected)
    assert report.files_deleted == 0
    assert report.files_blocked == len(protected)


def test_storage_cleanup_preview_shows_candidates_without_deleting(tmp_path):
    base = tmp_path / "files"
    old_mp4 = base / "worker_results" / "old.mp4"
    young_mp4 = base / "tmp" / "young.mp4"
    _write_old(old_mp4, age_seconds=48 * 3600)
    _write_old(young_mp4, age_seconds=60)

    report = storage_cleanup.audit_storage_cleanup(
        base_dir=str(base),
        ttl_seconds=24 * 3600,
        tmp_ttl_seconds=6 * 3600,
        delete=False,
        confirm_delete=False,
    )

    assert old_mp4.exists()
    assert young_mp4.exists()
    assert report.dry_run is True
    assert report.files_eligible == 1
    assert report.files_young == 1


def test_storage_cleanup_run_confirm_deletes_only_safe_files(tmp_path):
    base = tmp_path / "files"
    old_mp4 = base / "worker_results" / "old.mp4"
    old_db = base / "worker_results" / "wallet.db"
    _write_old(old_mp4, age_seconds=48 * 3600)
    _write_old(old_db, age_seconds=48 * 3600)

    report = storage_cleanup.audit_storage_cleanup(
        base_dir=str(base),
        ttl_seconds=24 * 3600,
        delete=True,
        confirm_delete=True,
    )

    assert not old_mp4.exists()
    assert old_db.exists()
    assert report.files_deleted == 1
    assert report.files_blocked == 1


def test_remote_worker_status_treats_recoverable_artifact_as_output():
    assert remote_worker_api._result_file_exists(  # protected helper, tested for storage regression
        {"final_video_path": "/missing/local.mp4"},
        {"artifact_storage": {"recoverable": True, "public_url": "https://cdn.example.com/a.mp4"}},
    )


def test_bot_worker_complete_records_artifact_metadata_and_cleanup_static():
    source = (REPO / "bot.py").read_text(encoding="utf-8")
    assert 'result_payload["artifact_storage"] = artifact_meta' in source
    assert "store_uploaded_worker_artifact(uploaded_path" in source
    assert "cleanup_worker_local_copy_after_delivery(uploaded_path" in source
    assert "artifact_storage.public_metadata(artifact_meta)" in source


def test_telegram_delivery_can_use_public_url_static():
    source = (REPO / "bot.py").read_text(encoding="utf-8")
    assert "async def send_generated_video_artifact_for_delivery" in source
    assert "bot_client.send_video(chat_id=chat_id, video=public_url" in source
    assert "bot_client.send_document(chat_id=chat_id, document=public_url" in source


def test_storage_commands_registered_static():
    source = (REPO / "bot.py").read_text(encoding="utf-8")
    assert 'CommandHandler("storage_audit", cmd_storage_audit)' in source
    assert 'CommandHandler("storage_cleanup_preview", cmd_storage_cleanup_preview)' in source
    assert 'CommandHandler("storage_cleanup_run", cmd_storage_cleanup_run)' in source
    assert 'CommandHandler("storage_job_artifacts", cmd_storage_job_artifacts)' in source


def test_delivery_helper_does_not_charge_or_deduct_static():
    source = (REPO / "bot.py").read_text(encoding="utf-8")
    match = re.search(r"async def send_generated_video_artifact_for_delivery\(.*?\n\n\ndef _job_artifact_snapshot", source, re.S)
    assert match
    helper = match.group(0).lower()
    assert "deduct" not in helper
    assert "charge" not in helper
    assert "payos" not in helper


def test_vps_cleanup_scripts_are_dry_run_first_and_create_required_dirs():
    cleanup = (REPO / "scripts" / "vps_storage_cleanup.sh").read_text(encoding="utf-8")
    install = (REPO / "scripts" / "install_vps_storage_cleanup_timer.sh").read_text(encoding="utf-8")
    assert "STORAGE_CLEANUP_DRY_RUN" in cleanup
    assert "-delete" in cleanup
    assert "DRY_RUN" in cleanup
    assert "/opt/toanaas-storage/{worker_results,artifacts,tmp,music,subdub,video,cache}" in install
    assert "STORAGE_CLEANUP_DRY_RUN=1" in install
