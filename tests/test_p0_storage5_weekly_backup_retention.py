import sqlite3
from pathlib import Path

from services import storage_maintenance


def _sqlite_backup(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("create table t (value integer)")
        conn.execute("insert into t values (?)", (value,))


def _config(root: Path) -> storage_maintenance.StorageConfig:
    return storage_maintenance.StorageConfig(
        backend="vps",
        storage_root=root,
        backup_root=root / "backups",
        railway_root=root.parent / "railway",
        vps_root=root,
        max_delete_files=50,
    )


def test_startup_backup_is_validated_and_five_generations_retained(tmp_path):
    root = tmp_path / "vps"
    backup_dir = root / "backups"
    paths = []
    for index in range(7):
        path = backup_dir / f"toandaas_system_202607{7 + index:02d}_033000_startup.db"
        _sqlite_backup(path, index)
        paths.append(path)
    corrupt = backup_dir / "toandaas_system_20260730_033000_startup.db"
    corrupt.write_bytes(b"not sqlite")
    config = _config(root)

    preview = storage_maintenance.plan_weekly(config, keep_backups=5)
    assert preview.dry_run is True
    assert preview.backup["invalid"] == 1
    assert preview.backup["retained"] == 5
    assert preview.backup["delete_candidates"] == 2
    assert corrupt.exists()
    assert all(path.exists() for path in paths)

    executed = storage_maintenance.run_weekly(config, keep_backups=5, execute=True)
    assert executed.status == "completed"
    assert executed.deleted_files == 2
    assert sum(path.exists() for path in paths) == 5
    assert corrupt.exists()


def test_duplicate_hash_counts_as_one_logical_generation_and_last_backup_is_safe(tmp_path):
    root = tmp_path / "vps"
    backup_dir = root / "backups"
    first = backup_dir / "toandaas_system_20260701_033000_startup.db"
    duplicate = backup_dir / "toandaas_system_20260702_033000_startup.db"
    _sqlite_backup(first, 1)
    duplicate.write_bytes(first.read_bytes())
    retained, candidates, invalid, _errors = storage_maintenance.backup_retention_plan(_config(root), keep=5)
    assert not invalid
    assert len(retained) == 2
    assert not candidates
    assert {item.digest for item in retained}.__len__() == 1

    only_root = tmp_path / "only"
    only = only_root / "backups" / "toandaas_system_20260701_033000_startup.db"
    _sqlite_backup(only, 1)
    retained, candidates, invalid, _errors = storage_maintenance.backup_retention_plan(_config(only_root), keep=5)
    assert len(retained) == 1
    assert not candidates
