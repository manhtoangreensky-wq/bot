#!/usr/bin/env python3
"""Forced-command receiver for immutable Local Bot API release archives."""

from __future__ import annotations

import hashlib
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

import release_contract


UPLOAD_RE = re.compile(r"^upload ([0-9a-f]{40}) ([0-9a-f]{64})$")


class ReceiveError(RuntimeError):
    """Raised when a forced-command upload does not meet the receiver contract."""


class ReceiveReceipt(NamedTuple):
    archive: Path
    ready: Path
    commit: str
    digest: str


def _safe_incoming(directory: str | Path) -> Path:
    incoming = Path(directory)
    incoming.mkdir(parents=True, exist_ok=True, mode=0o750)
    if incoming.is_symlink() or not incoming.is_dir():
        raise ReceiveError("incoming directory is unsafe")
    return incoming.resolve(strict=True)


def _atomic_ready(path: Path, digest: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        with os.fdopen(fd, "wb") as handle:
            handle.write(f"{digest}\n".encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()


def receive(command: str, payload: bytes, incoming_dir: str | Path) -> ReceiveReceipt:
    match = UPLOAD_RE.fullmatch(str(command or ""))
    if match is None:
        raise ReceiveError("forced command is not an allowed upload command")
    commit, expected_digest = match.groups()
    if not isinstance(payload, bytes):
        raise ReceiveError("release payload must be bytes")
    if len(payload) > release_contract.MAX_ARCHIVE_BYTES:
        raise ReceiveError("release payload exceeds the 2 MiB receiver limit")
    actual_digest = hashlib.sha256(payload).hexdigest()
    if actual_digest != expected_digest:
        raise ReceiveError("release archive digest does not match command")

    incoming = _safe_incoming(incoming_dir)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".upload-", suffix=".tgz", dir=incoming, delete=False
        ) as handle:
            temporary_name = handle.name
            os.chmod(temporary_name, 0o640)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary = Path(temporary_name)
        validated = release_contract.validate_archive(temporary)
        if validated.manifest["commit"] != commit:
            raise ReceiveError("release manifest commit does not match command")
        archive = incoming / f"{actual_digest}.tgz"
        if archive.exists() or archive.is_symlink():
            if (
                archive.is_symlink()
                or not archive.is_file()
                or hashlib.sha256(archive.read_bytes()).hexdigest() != actual_digest
            ):
                raise ReceiveError("existing archive path is unsafe or has another digest")
            temporary.unlink()
        else:
            os.replace(temporary, archive)
        ready = incoming / f"{actual_digest}.ready"
        if ready.exists() or ready.is_symlink():
            if ready.is_symlink() or ready.read_bytes() != f"{actual_digest}\n".encode("ascii"):
                raise ReceiveError("existing ready path is unsafe or inconsistent")
        else:
            _atomic_ready(ready, actual_digest)
        return ReceiveReceipt(archive, ready, commit, actual_digest)
    except release_contract.ReleaseContractError as exc:
        raise ReceiveError(f"release archive failed validation: {exc}") from exc
    finally:
        if temporary_name:
            temporary = Path(temporary_name)
            if temporary.exists() and not temporary.is_symlink():
                temporary.unlink()


def main() -> int:
    command = os.environ.get("SSH_ORIGINAL_COMMAND", "")
    payload = sys.stdin.buffer.read(release_contract.MAX_ARCHIVE_BYTES + 1)
    try:
        receipt = receive(
            command,
            payload,
            Path("/var/lib/toanaas-localbotapi/incoming"),
        )
    except (OSError, ReceiveError) as exc:
        print(f"localbotapi_receive status=rejected reason={type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"localbotapi_receive status=accepted digest={receipt.digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
