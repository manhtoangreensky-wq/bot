#!/usr/bin/env python3
"""Validation contract for immutable TOAN AAS Local Bot API releases."""

from __future__ import annotations

import hashlib
import json
import re
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple


SCHEMA = "toanaas-localbotapi-release/v1"
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024
MAX_EXPANDED_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_BYTES = 128 * 1024
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_RELEASE_FILES = (
    "release/policy.json",
    "release/bin/toanaas-localbotapi-health",
    "release/bin/toanaas-localbotapi-reconcile",
    "release/bin/toanaas-localbotapi-cleanup",
    "release/bin/toanaas-localbotapi-cert-watch",
    "release/systemd/toanaas-telegram-bot-api.service",
    "release/systemd/toanaas-localbotapi-cleanup.service",
    "release/systemd/toanaas-localbotapi-cleanup.timer",
    "release/systemd/toanaas-localbotapi-health.service",
    "release/systemd/toanaas-localbotapi-health.timer",
    "release/systemd/toanaas-localbotapi-reconcile.service",
    "release/systemd/toanaas-localbotapi-reconcile.timer",
    "release/systemd/toanaas-localbotapi-cert-watch.service",
    "release/systemd/toanaas-localbotapi-cert-watch.timer",
)


class ReleaseContractError(ValueError):
    """Raised when an incoming release violates the immutable contract."""


class ValidatedRelease(NamedTuple):
    manifest: dict[str, Any]
    manifest_bytes: bytes
    release_id: str
    files: dict[str, bytes]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                manifest,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReleaseContractError(f"manifest is not canonical JSON: {exc}") from exc


def _safe_release_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReleaseContractError("unsafe empty release path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or "\x00" in value
        or path.as_posix() != value
        or not value.startswith("release/")
    ):
        raise ReleaseContractError(f"unsafe release path: {value!r}")
    return value


def validate_manifest(manifest: Any) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise ReleaseContractError("manifest must be an object")
    if set(manifest) != {"schema", "commit", "files", "policy_sha256"}:
        raise ReleaseContractError("manifest fields do not match schema")
    if manifest.get("schema") != SCHEMA:
        raise ReleaseContractError("unsupported manifest schema")
    commit = manifest.get("commit")
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise ReleaseContractError("manifest commit must be 40 lowercase hex characters")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ReleaseContractError("manifest files must be a non-empty object")
    normalized: dict[str, str] = {}
    for raw_path, raw_digest in files.items():
        path = _safe_release_path(raw_path)
        if not isinstance(raw_digest, str) or not SHA256_RE.fullmatch(raw_digest):
            raise ReleaseContractError(f"invalid sha256 digest for {path}")
        normalized[path] = raw_digest
    if set(normalized) != set(EXPECTED_RELEASE_FILES):
        missing = sorted(set(EXPECTED_RELEASE_FILES) - set(normalized))
        unexpected = sorted(set(normalized) - set(EXPECTED_RELEASE_FILES))
        raise ReleaseContractError(
            f"release file allowlist mismatch; missing={missing}, unexpected={unexpected}"
        )
    if "release/policy.json" not in normalized:
        raise ReleaseContractError("manifest must include release/policy.json")
    policy_sha256 = manifest.get("policy_sha256")
    if policy_sha256 != normalized["release/policy.json"]:
        raise ReleaseContractError("policy digest does not match file manifest")
    return {
        "schema": SCHEMA,
        "commit": commit,
        "files": dict(sorted(normalized.items())),
        "policy_sha256": policy_sha256,
    }


def validate_archive(path: str | Path) -> ValidatedRelease:
    archive_path = Path(path)
    if not archive_path.is_file() or archive_path.is_symlink():
        raise ReleaseContractError("release archive must be a regular file")
    if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ReleaseContractError("release archive exceeds 2 MiB limit")

    try:
        archive = tarfile.open(archive_path, mode="r:gz")
    except (OSError, tarfile.TarError) as exc:
        raise ReleaseContractError(f"invalid release archive: {exc}") from exc

    members: dict[str, bytes] = {}
    expanded = 0
    with archive:
        for member in archive.getmembers():
            name = member.name
            if name in members:
                raise ReleaseContractError(f"duplicate archive member: {name}")
            if name != "manifest.json":
                _safe_release_path(name)
            if not member.isreg():
                raise ReleaseContractError(f"archive member is not a regular file: {name}")
            if member.size < 0 or member.size > MAX_EXPANDED_BYTES:
                raise ReleaseContractError(f"archive member has unsafe size: {name}")
            expanded += member.size
            if expanded > MAX_EXPANDED_BYTES:
                raise ReleaseContractError("expanded release exceeds 4 MiB limit")
            handle = archive.extractfile(member)
            if handle is None:
                raise ReleaseContractError(f"could not read archive member: {name}")
            value = handle.read(MAX_EXPANDED_BYTES + 1)
            if len(value) != member.size:
                raise ReleaseContractError(f"archive member size changed while reading: {name}")
            members[name] = value

    raw_manifest = members.pop("manifest.json", None)
    if raw_manifest is None or len(raw_manifest) > MAX_MANIFEST_BYTES:
        raise ReleaseContractError("manifest.json is missing or too large")
    try:
        decoded = json.loads(raw_manifest.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseContractError(f"manifest.json is invalid: {exc}") from exc
    manifest = validate_manifest(decoded)
    canonical = canonical_manifest_bytes(manifest)
    if raw_manifest != canonical:
        raise ReleaseContractError("manifest.json is not canonical")
    if set(members) != set(manifest["files"]):
        missing = sorted(set(manifest["files"]) - set(members))
        unexpected = sorted(set(members) - set(manifest["files"]))
        raise ReleaseContractError(
            f"archive member set mismatch; missing={missing}, unexpected={unexpected}"
        )
    for name, value in members.items():
        if sha256_bytes(value) != manifest["files"][name]:
            raise ReleaseContractError(f"digest mismatch for {name}")
    return ValidatedRelease(
        manifest=manifest,
        manifest_bytes=canonical,
        release_id=sha256_bytes(canonical),
        files=members,
    )
