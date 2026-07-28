from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
BOOTSTRAP = REPO / "deploy" / "localbotapi" / "bootstrap"
RELEASE = REPO / "deploy" / "localbotapi" / "release"


def _load_module(name: str):
    path = BOOTSTRAP / f"{name}.py"
    assert path.is_file(), f"missing Local Bot API bootstrap module: {path}"
    bootstrap_path = str(BOOTSTRAP)
    if bootstrap_path not in sys.path:
        sys.path.insert(0, bootstrap_path)
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _release_text(relative: str) -> str:
    path = RELEASE / relative
    assert path.is_file(), f"missing release file: {path}"
    return path.read_text(encoding="utf-8")


def _archive(
    path: Path,
    *,
    files: dict[str, bytes],
    extra_members: list[tarfile.TarInfo] | None = None,
    digest_override: str = "",
) -> Path:
    digests = {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}
    if digest_override:
        first = next(iter(digests))
        digests[first] = digest_override
    manifest = {
        "schema": "toanaas-localbotapi-release/v1",
        "commit": "1" * 40,
        "files": digests,
        "policy_sha256": digests["release/policy.json"],
    }
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                info = tarfile.TarInfo("manifest.json")
                info.size = len(manifest_bytes)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(manifest_bytes))
                for name, value in files.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(value)
                    info.mode = 0o755 if name.startswith("release/bin/") else 0o644
                    archive.addfile(info, io.BytesIO(value))
                for info in extra_members or []:
                    archive.addfile(info, io.BytesIO(b"x") if info.isreg() else None)
    return path


def test_release_builder_is_deterministic_and_infra_only(tmp_path):
    builder = _load_module("build_release")
    contract = _load_module("release_contract")
    first = builder.build_release(REPO, "1" * 40, tmp_path / "one.tgz")
    second = builder.build_release(REPO, "1" * 40, tmp_path / "two.tgz")

    assert _sha256(first) == _sha256(second)
    validated = contract.validate_archive(first)
    source_files = {
        path.relative_to(REPO / "deploy" / "localbotapi").as_posix()
        for path in RELEASE.rglob("*")
        if path.is_file()
    }
    assert set(validated.manifest["files"]) == source_files
    assert all("bot.py" not in name for name in validated.manifest["files"])
    assert all("product-video" not in name for name in validated.manifest["files"])
    assert all("remote_worker" not in name for name in validated.manifest["files"])
    assert validated.release_id == hashlib.sha256(validated.manifest_bytes).hexdigest()


def test_manifest_rejects_traversal_symlink_and_digest_mismatch(tmp_path):
    contract = _load_module("release_contract")
    policy = b'{"schema":"toanaas-localbotapi-policy/v1"}\n'
    files = {"release/policy.json": policy}

    traversal = tarfile.TarInfo("../outside")
    traversal.size = 1
    traversal.mode = 0o644
    with pytest.raises(contract.ReleaseContractError, match="unsafe|unexpected"):
        contract.validate_archive(
            _archive(tmp_path / "traversal.tgz", files=files, extra_members=[traversal])
        )

    symlink = tarfile.TarInfo("release/link")
    symlink.type = tarfile.SYMTYPE
    symlink.linkname = "/etc/shadow"
    symlink.mode = 0o777
    with pytest.raises(contract.ReleaseContractError, match="regular|link|unexpected"):
        contract.validate_archive(
            _archive(tmp_path / "symlink.tgz", files=files, extra_members=[symlink])
        )

    with pytest.raises(contract.ReleaseContractError, match="digest"):
        contract.validate_archive(
            _archive(tmp_path / "digest.tgz", files=files, digest_override="0" * 64)
        )


def test_cleanup_fails_closed_before_any_remove_when_fuser_is_missing():
    text = _release_text("bin/toanaas-localbotapi-cleanup")
    assert "set -euo pipefail" in text
    assert "require_tool fuser" in text
    assert text.index("require_tool fuser") < text.index("safe_remove()")
    assert "command -v fuser >/dev/null 2>&1 && fuser" not in text
    assert "unexpected_fuser_status" in text
    assert "RETENTION_MINUTES:-120" in text
    assert "MAX_DATA_MIB:-6144" in text
    assert "MINIMUM_FREE_MIB:-3072" in text


def test_reconcile_is_locked_and_rolls_back_only_the_localbot_service():
    text = _release_text("bin/toanaas-localbotapi-reconcile")
    assert "flock -n" in text
    assert "verify-current" in text
    assert "toanaas-telegram-bot-api.service" in text
    assert "restart \"$SERVICE\"" in text
    assert " rollback " in text
    for forbidden in ("product-video", "remote_worker", "local_worker", "git pull", ":latest"):
        assert forbidden not in text


def test_health_checks_real_upstream_external_gate_and_loopback_bind():
    text = _release_text("bin/toanaas-localbotapi-health")
    assert "127.0.0.1:8081" in text
    assert "root_http" in text and '"404"' in text
    assert "dummy_http" in text and '"401"' in text
    assert "missing_secret_status" in text and '"403"' in text
    assert "0.0.0.0:8081" in text and "[::]:8081" in text
    assert "TELEGRAM_TOKEN" not in text
    assert "TELEGRAM_API_HASH" not in text


def test_certificate_watcher_checks_expiry_without_changing_time():
    text = _release_text("bin/toanaas-localbotapi-cert-watch")
    assert "x509 -checkend 1209600" in text
    assert "tg.toanaas.vn:443" in text
    for forbidden in ("date -s", "timedatectl set-time", "hwclock --set"):
        assert forbidden not in text


def test_release_units_are_sandboxed_and_scoped_to_localbot():
    policy = json.loads(_release_text("policy.json"))
    expected_units = {
        "toanaas-telegram-bot-api.service",
        "toanaas-localbotapi-cleanup.service",
        "toanaas-localbotapi-cleanup.timer",
        "toanaas-localbotapi-health.service",
        "toanaas-localbotapi-health.timer",
        "toanaas-localbotapi-reconcile.service",
        "toanaas-localbotapi-reconcile.timer",
        "toanaas-localbotapi-cert-watch.service",
        "toanaas-localbotapi-cert-watch.timer",
    }
    assert set(policy["managed_units"]) == expected_units
    for unit in expected_units:
        text = _release_text(f"systemd/{unit}")
        assert "product-video" not in text
        if unit.endswith(".service"):
            for control in (
                "NoNewPrivileges=true",
                "ProtectSystem=strict",
                "ProtectHome=true",
                "RestrictSUIDSGID=true",
                "LockPersonality=true",
            ):
                assert control in text, f"{unit} lacks {control}"
    service = _release_text("systemd/toanaas-telegram-bot-api.service")
    assert "--publish 127.0.0.1:8081:8081" in service
    assert "--read-only" in service
    assert "--cap-drop ALL" in service
    assert "@sha256:2e93a720f71f82e41a42dc89e258efda09e6791f8d959e6801d15f88408e8eb1" in service
    assert ":latest" not in service
