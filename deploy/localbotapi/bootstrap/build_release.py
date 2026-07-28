#!/usr/bin/env python3
"""Build and verify deterministic Local Bot API infrastructure releases."""

from __future__ import annotations

import argparse
import gzip
import io
import os
import tarfile
from pathlib import Path

import release_contract


def _release_files(repo_root: Path) -> dict[str, tuple[bytes, int]]:
    localbot_root = repo_root / "deploy" / "localbotapi"
    release_root = localbot_root / "release"
    if not release_root.is_dir() or release_root.is_symlink():
        raise release_contract.ReleaseContractError("release directory is missing or unsafe")
    result: dict[str, tuple[bytes, int]] = {}
    for path in sorted(release_root.rglob("*")):
        if path.is_symlink():
            raise release_contract.ReleaseContractError(f"release contains a symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(localbot_root).as_posix()
        release_contract._safe_release_path(relative)
        value = path.read_bytes()
        if len(value) > release_contract.MAX_EXPANDED_BYTES:
            raise release_contract.ReleaseContractError(f"release file is too large: {relative}")
        mode = 0o755 if relative.startswith("release/bin/") else 0o644
        result[relative] = (value, mode)
    if "release/policy.json" not in result:
        raise release_contract.ReleaseContractError("release/policy.json is required")
    return result


def _tar_info(name: str, value: bytes, mode: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=name)
    info.size = len(value)
    info.mode = mode
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def build_release(repo_root: str | Path, commit: str, output: str | Path) -> Path:
    root = Path(repo_root).resolve()
    files = _release_files(root)
    manifest = release_contract.validate_manifest(
        {
            "schema": release_contract.SCHEMA,
            "commit": commit,
            "files": {
                name: release_contract.sha256_bytes(value)
                for name, (value, _mode) in files.items()
            },
            "policy_sha256": release_contract.sha256_bytes(
                files["release/policy.json"][0]
            ),
        }
    )
    manifest_bytes = release_contract.canonical_manifest_bytes(manifest)
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + f".tmp-{os.getpid()}")
    try:
        with temporary.open("wb") as raw:
            with gzip.GzipFile(
                fileobj=raw, mode="wb", filename="", mtime=0, compresslevel=9
            ) as compressed:
                with tarfile.open(
                    fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT
                ) as archive:
                    archive.addfile(
                        _tar_info("manifest.json", manifest_bytes, 0o644),
                        io.BytesIO(manifest_bytes),
                    )
                    for name, (value, mode) in files.items():
                        archive.addfile(_tar_info(name, value, mode), io.BytesIO(value))
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    release_contract.validate_archive(destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--repo-root", type=Path, required=True)
    build.add_argument("--commit", required=True)
    build.add_argument("--output", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build":
        path = build_release(args.repo_root, args.commit, args.output)
        print(path)
    else:
        validated = release_contract.validate_archive(args.archive)
        print(validated.release_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
