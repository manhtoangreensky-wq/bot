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
