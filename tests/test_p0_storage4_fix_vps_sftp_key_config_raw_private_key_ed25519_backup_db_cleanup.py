import base64
import io
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import bot
from services import artifact_storage, storage_migration


REPO = Path(__file__).resolve().parents[1]
RAW_ED25519_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nunit-test-ed25519\n-----END OPENSSH PRIVATE KEY-----\n"


def _write(path: Path, payload: bytes = b"artifact", *, age_seconds: int = 48 * 3600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))


class _FakeKey:
    def __init__(self, kind: str):
        self.kind = kind


class _FakeKeyLoader:
    kind = "ed25519"

    @classmethod
    def from_private_key(cls, stream):
        text = stream.read()
        if "INVALID" in text:
            raise ValueError("invalid key")
        return _FakeKey(cls.kind)

    @classmethod
    def from_private_key_file(cls, path):
        text = Path(path).read_text(encoding="utf-8")
        if "INVALID" in text:
            raise ValueError("invalid key")
        return _FakeKey(cls.kind)


class _FakeRSAKey(_FakeKeyLoader):
    kind = "rsa"


class _FakeECDSAKey(_FakeKeyLoader):
    kind = "ecdsa"


class _FakeTransport:
    def __init__(self, address):
        self.address = address
        self.connected = False

    def connect(self, username=None, pkey=None):
        if username == "auth_fail":
            raise type("AuthenticationException", (Exception,), {})("auth failed")
        self.connected = True
        self.pkey = pkey

    def close(self):
        self.connected = False


class _FakeSFTP:
    uploads = {}

    def mkdir(self, _path):
        return None

    def put(self, local_path, remote_path):
        self.uploads[remote_path] = Path(local_path).read_bytes()

    def stat(self, remote_path):
        return SimpleNamespace(st_size=len(self.uploads[remote_path]))

    def open(self, remote_path, _mode):
        return io.BytesIO(self.uploads[remote_path])

    def close(self):
        return None


class _FakeSFTPClient:
    @staticmethod
    def from_transport(_transport):
        return _FakeSFTP()


def _install_fake_paramiko(monkeypatch):
    _FakeSFTP.uploads = {}
    fake = SimpleNamespace(
        Ed25519Key=_FakeKeyLoader,
        RSAKey=_FakeRSAKey,
        ECDSAKey=_FakeECDSAKey,
        Transport=_FakeTransport,
        SFTPClient=_FakeSFTPClient,
    )
    monkeypatch.setitem(sys.modules, "paramiko", fake)
    return fake


def _cfg(**overrides):
    data = {
        "backend": "vps_sftp",
        "vps_host": "vps.internal",
        "vps_user": "toanaas",
        "vps_base_dir": "/opt/toanaas-storage",
        "public_base_url": "https://cdn.example.com/toanaas",
    }
    data.update(overrides)
    return artifact_storage.ArtifactStorageConfig(**data)


def test_vps_sftp_config_works_with_raw_ed25519_private_key(monkeypatch, tmp_path):
    _install_fake_paramiko(monkeypatch)
    media = tmp_path / "video.mp4"
    media.write_bytes(b"video")

    result = artifact_storage.store_artifact(media, config=_cfg(vps_ssh_private_key=RAW_ED25519_KEY), product_area="video")

    assert result["ok"] is True
    assert result["backend"] == "vps_sftp"
    assert result["remote_path"] in _FakeSFTP.uploads


def test_vps_sftp_config_works_with_private_key_b64(monkeypatch, tmp_path):
    _install_fake_paramiko(monkeypatch)
    media = tmp_path / "audio.mp3"
    media.write_bytes(b"audio")
    encoded = base64.b64encode(RAW_ED25519_KEY.encode("utf-8")).decode("ascii")

    result = artifact_storage.store_artifact(media, config=_cfg(vps_ssh_private_key_b64=encoded), product_area="music")

    assert result["ok"] is True
    assert result["remote_path"] in _FakeSFTP.uploads


def test_vps_sftp_config_works_with_key_path(monkeypatch, tmp_path):
    _install_fake_paramiko(monkeypatch)
    key_path = tmp_path / "id_ed25519"
    key_path.write_text(RAW_ED25519_KEY, encoding="utf-8")
    media = tmp_path / "subtitle.srt"
    media.write_bytes(b"subtitle")

    result = artifact_storage.store_artifact(media, config=_cfg(vps_ssh_key_path=str(key_path)), product_area="subdub")

    assert result["ok"] is True
    assert result["remote_path"] in _FakeSFTP.uploads


def test_missing_vps_sftp_key_returns_key_missing_not_generic_config(tmp_path):
    media = tmp_path / "video.mp4"
    media.write_bytes(b"video")

    result = artifact_storage.store_artifact(media, config=_cfg(), product_area="video")

    assert result["ok"] is False
    assert result["reason"] == "vps_sftp_key_missing"
    assert result["reason"] != "vps_sftp_config_missing"


def test_invalid_vps_sftp_key_returns_key_invalid(monkeypatch, tmp_path):
    _install_fake_paramiko(monkeypatch)
    media = tmp_path / "video.mp4"
    media.write_bytes(b"video")

    result = artifact_storage.store_artifact(media, config=_cfg(vps_ssh_private_key="INVALID"), product_area="video")

    assert result["ok"] is False
    assert result["reason"] == "vps_sftp_key_invalid"


def test_storage_artifact_backend_debug_hides_secrets(monkeypatch):
    _install_fake_paramiko(monkeypatch)
    monkeypatch.setattr(bot, "ARTIFACT_STORAGE_BACKEND", "vps_sftp")
    monkeypatch.setattr(bot, "ARTIFACT_VPS_HOST", "vps.internal")
    monkeypatch.setattr(bot, "ARTIFACT_VPS_USER", "toanaas")
    monkeypatch.setattr(bot, "ARTIFACT_VPS_SSH_KEY_PATH", "")
    monkeypatch.setattr(bot, "ARTIFACT_VPS_SSH_PRIVATE_KEY", RAW_ED25519_KEY)
    monkeypatch.setattr(bot, "ARTIFACT_VPS_SSH_PRIVATE_KEY_B64", "")

    text = "\n".join(bot.storage_artifact_backend_debug_lines())

    assert "Raw private key configured: <code>yes</code>" in text
    assert "unit-test-ed25519" not in text
    assert "BEGIN OPENSSH PRIVATE KEY" not in text
    assert "vps.internal" not in text


def test_migration_upload_verifies_remote_size_hash_before_local_delete(monkeypatch, tmp_path):
    _install_fake_paramiko(monkeypatch)
    base = tmp_path / "data"
    media = base / "dub_assets" / "dub.mp4"
    _write(media, b"dub")

    report = storage_migration.migrate_existing_assets(
        base,
        config=_cfg(vps_ssh_private_key=RAW_ED25519_KEY),
        conn=None,
        delete_local=True,
        confirm=True,
    )

    assert not media.exists()
    assert report.uploaded_files == 1
    assert report.verified_files == 1
    assert report.deleted_files == 1


def test_backup_cleanup_deletes_old_db_backups_inside_backups_keep_latest_5(tmp_path):
    base = tmp_path / "data"
    backups = []
    for index in range(7):
        path = base / "backups" / f"toandaas_system_2026070{index + 1}_033000_startup.db"
        _write(path, f"backup-{index}".encode("utf-8"), age_seconds=(index + 1) * 3600)
        backups.append(path)

    report = storage_migration.backup_cleanup_report(base, keep=5, delete=True, confirm=True)

    assert report.deleted_files == 2
    assert all(path.exists() for path in backups[:5])
    assert not backups[5].exists()
    assert not backups[6].exists()


def test_current_db_wallet_payment_finance_files_are_never_deleted_by_backup_cleanup(tmp_path):
    base = tmp_path / "data"
    current_db = base / "toandaas_system.db"
    wallet = base / "wallet.db"
    payment = base / "payment.sqlite3"
    finance = base / "finance.sqlite"
    for path in (current_db, wallet, payment, finance):
        _write(path, b"protected")
    old_backup = base / "backups" / "toandaas_system_20260701_033000_startup.db"
    _write(old_backup, b"old", age_seconds=10 * 3600)

    report = storage_migration.backup_cleanup_report(base, keep=0, delete=True, confirm=True)

    assert report.deleted_files == 1
    assert not old_backup.exists()
    assert current_db.exists()
    assert wallet.exists()
    assert payment.exists()
    assert finance.exists()


def test_storage4_does_not_touch_payos_wallet_pricing_static():
    service = (REPO / "services" / "artifact_storage.py").read_text(encoding="utf-8").lower()
    migration = (REPO / "services" / "storage_migration.py").read_text(encoding="utf-8").lower()
    assert "payos" not in service
    assert "price" not in service
    assert "payos" not in migration
    assert "price" not in migration
