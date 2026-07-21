import os
import time
from pathlib import Path

import bot
from services import storage_cleanup


def _touch_old(path: Path, *, age_seconds: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"artifact")
    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))


def test_storage_cleanup_targets_worker_results_tmp_and_files(tmp_path):
    base = tmp_path / "files"
    roots = storage_cleanup.cleanup_roots(str(base))
    normalized = {str(root).replace("\\", "/") for root in roots}
    assert str(base / "worker_results").replace("\\", "/") in normalized
    assert str(base / "tmp").replace("\\", "/") in normalized
    assert str(base).replace("\\", "/") in normalized


def test_storage_cleanup_dry_run_keeps_old_generated_artifact(tmp_path):
    base = tmp_path / "files"
    target = base / "worker_results" / "worker_job_47_final_output.mp4"
    _touch_old(target, age_seconds=8 * 24 * 3600)

    report = storage_cleanup.audit_storage_cleanup(
        base_dir=str(base),
        ttl_seconds=24 * 3600,
        delete=False,
        confirm_delete=False,
    )

    assert target.exists()
    assert report.files_eligible == 1
    assert report.files_deleted == 0
    assert report.dry_run is True


def test_storage_cleanup_confirm_deletes_only_old_allowlisted_artifacts(tmp_path):
    base = tmp_path / "files"
    old_mp4 = base / "worker_results" / "worker_job_47_final_output.mp4"
    young_mp4 = base / "tmp" / "young.mp4"
    db_file = base / "toandaas_system.sqlite3"
    env_file = base / ".env"
    source_file = base / "bot.py"
    _touch_old(old_mp4, age_seconds=8 * 24 * 3600)
    _touch_old(young_mp4, age_seconds=60)
    _touch_old(db_file, age_seconds=8 * 24 * 3600)
    _touch_old(env_file, age_seconds=8 * 24 * 3600)
    _touch_old(source_file, age_seconds=8 * 24 * 3600)

    report = storage_cleanup.audit_storage_cleanup(
        base_dir=str(base),
        ttl_seconds=24 * 3600,
        delete=True,
        confirm_delete=True,
    )

    assert not old_mp4.exists()
    assert young_mp4.exists()
    assert db_file.exists()
    assert env_file.exists()
    assert source_file.exists()
    assert report.files_deleted == 1
    reasons = {item.reason for item in report.samples}
    assert "protected_extension" in reasons or "protected_name" in reasons
    assert "younger_than_ttl" in reasons


def test_storage_cleanup_never_deletes_db_sqlite_secret_config_or_source(tmp_path):
    base = tmp_path / "files"
    protected = [
        base / "wallet.db",
        base / "finance.sqlite",
        base / "payment.sqlite3",
        base / "secret.key",
        base / "railway.toml",
        base / "settings.json",
        base / "README.md",
        base / "bot.py",
    ]
    for path in protected:
        _touch_old(path, age_seconds=10 * 24 * 3600)

    report = storage_cleanup.audit_storage_cleanup(
        base_dir=str(base),
        ttl_seconds=24 * 3600,
        delete=True,
        confirm_delete=True,
    )

    assert all(path.exists() for path in protected)
    assert report.files_deleted == 0
    assert report.files_blocked == len(protected)


def test_storage_cleanup_keeps_db_referenced_artifact(tmp_path):
    base = tmp_path / "files"
    referenced = base / "worker_results" / "active_job.mp4"
    _touch_old(referenced, age_seconds=10 * 24 * 3600)

    report = storage_cleanup.audit_storage_cleanup(
        base_dir=str(base),
        ttl_seconds=24 * 3600,
        protected_paths={str(referenced.resolve()).replace("\\", "/")},
        delete=True,
        confirm_delete=True,
    )

    assert referenced.exists()
    assert report.files_deleted == 0
    assert any(item.reason == "active_job_reference" for item in report.samples)


def test_storage_cleanup_report_shows_safety_locks_and_confirm_token(tmp_path, monkeypatch):
    base = tmp_path / "files"
    monkeypatch.setattr(bot, "STORAGE_CLEANUP_BASE_DIR", str(base))
    report = storage_cleanup.audit_storage_cleanup(base_dir=str(base), ttl_seconds=3600)

    text = "\n".join(bot.storage_cleanup_report_lines(report, {"ok": False}, mode="confirm_missing"))

    assert "DRY RUN" in text
    assert "CONFIRM_TTL" in text
    assert "Khong xoa DB/sqlite" in text
    assert "Khong xoa file con duoc DB/job tham chieu" in text


def test_storage_cleanup_auto_disabled_by_default(monkeypatch):
    monkeypatch.setattr(bot, "STORAGE_CLEANUP_AUTO_ENABLED", False)
    assert bot.run_storage_cleanup_auto_once() == {"ok": False, "reason": "auto_disabled"}


def test_storage_cleanup_commands_registered():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert 'CommandHandler("storage_audit", cmd_storage_audit)' in source
    assert 'CommandHandler("storage_cleanup_dry_run", cmd_storage_cleanup_dry_run)' in source
    assert 'CommandHandler("storage_cleanup_confirm", cmd_storage_cleanup_confirm)' in source
    assert 'CommandHandler("storage_cleanup_auto_status", cmd_storage_cleanup_auto_status)' in source
