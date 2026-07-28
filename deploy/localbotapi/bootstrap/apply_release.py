#!/usr/bin/env python3
"""Install and activate one verified Local Bot API infrastructure release."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, NamedTuple, Protocol, Sequence

import release_contract


SERVICE = "toanaas-telegram-bot-api.service"
LEGACY_CLEANUP_TIMER = "toanaas-tgbotapi-cleanup.timer"
MANAGED_UNITS = (
    SERVICE,
    "toanaas-localbotapi-cleanup.service",
    "toanaas-localbotapi-cleanup.timer",
    "toanaas-localbotapi-health.service",
    "toanaas-localbotapi-health.timer",
    "toanaas-localbotapi-reconcile.service",
    "toanaas-localbotapi-reconcile.timer",
    "toanaas-localbotapi-cert-watch.service",
    "toanaas-localbotapi-cert-watch.timer",
)
MANAGED_TIMERS = tuple(unit for unit in MANAGED_UNITS if unit.endswith(".timer"))
EXPECTED_POLICY = {
    "schema": "toanaas-localbotapi-policy/v1",
    "service": SERVICE,
    "container_image": (
        "aiogram/telegram-bot-api@sha256:"
        "2e93a720f71f82e41a42dc89e258efda09e6791f8d959e6801d15f88408e8eb1"
    ),
    "upstream_host": "127.0.0.1",
    "upstream_port": 8081,
    "forbidden_public_ports": [8081, 8082],
    "data_dir": "/opt/toanaas-telegram-bot-api/data",
    "temp_dir": "/opt/toanaas-telegram-bot-api/temp",
    "retention_minutes": 120,
    "max_data_mib": 6144,
    "minimum_free_mib": 3072,
    "managed_units": list(MANAGED_UNITS),
}


class ApplyError(RuntimeError):
    """Raised when release materialization, activation, or rollback is unsafe."""


class ReleaseRoots:
    def __init__(
        self,
        *,
        release_root: Path,
        systemd_dir: Path,
        incoming_dir: Path,
        bootstrap_backup: Path,
        lock_path: Path,
    ) -> None:
        self.release_root = Path(release_root)
        self.systemd_dir = Path(systemd_dir)
        self.incoming_dir = Path(incoming_dir)
        self.bootstrap_backup = Path(bootstrap_backup)
        self.lock_path = Path(lock_path)

    @property
    def releases(self) -> Path:
        return self.release_root / "releases"

    @property
    def current(self) -> Path:
        return self.release_root / "current"

    @property
    def previous(self) -> Path:
        return self.release_root / "previous"

    @classmethod
    def production(cls) -> "ReleaseRoots":
        state = Path("/var/lib/toanaas-localbotapi")
        return cls(
            release_root=Path("/opt/toanaas-localbotapi"),
            systemd_dir=Path("/etc/systemd/system"),
            incoming_dir=state / "incoming",
            bootstrap_backup=state / "bootstrap-backup",
            lock_path=Path("/run/lock/toanaas-localbotapi-reconcile.lock"),
        )


class ApplyResult(NamedTuple):
    status: str
    commit: str
    active_release: Path | None


class LinkStore(Protocol):
    def exists(self, link: Path) -> bool: ...

    def resolve(self, link: Path) -> Path: ...

    def replace(self, link: Path, target: Path) -> None: ...

    def remove(self, link: Path) -> None: ...


class AtomicSymlinkStore:
    """Atomic Linux symlink replacement used by the fixed root helper."""

    def exists(self, link: Path) -> bool:
        return link.is_symlink()

    def resolve(self, link: Path) -> Path:
        if not link.is_symlink():
            raise ApplyError(f"managed pointer is not a symlink: {link}")
        try:
            return link.resolve(strict=True)
        except OSError as exc:
            raise ApplyError(f"managed pointer is broken: {link}") from exc

    def replace(self, link: Path, target: Path) -> None:
        link.parent.mkdir(parents=True, exist_ok=True)
        target = target.resolve(strict=True)
        temporary = link.with_name(f".{link.name}.tmp-{os.getpid()}")
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()
        try:
            os.symlink(target, temporary, target_is_directory=target.is_dir())
            os.replace(temporary, link)
        finally:
            if temporary.exists() or temporary.is_symlink():
                temporary.unlink()

    def remove(self, link: Path) -> None:
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            raise ApplyError(f"refusing to remove non-symlink managed pointer: {link}")


CommandRunner = Callable[[Sequence[str]], None]


def _run(argv: Sequence[str]) -> None:
    subprocess.run(list(argv), check=True)


def _validate_policy_bytes(value: bytes) -> dict:
    try:
        policy = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApplyError(f"release policy is invalid JSON: {exc}") from exc
    if policy != EXPECTED_POLICY:
        raise ApplyError("release policy differs from the fixed bootstrap allowlist")
    return policy


def _safe_release_target(roots: ReleaseRoots, target: Path) -> Path:
    releases = roots.releases.resolve(strict=True)
    resolved = target.resolve(strict=True)
    if resolved.parent != releases or resolved.name.startswith("."):
        raise ApplyError(f"release pointer escapes immutable release root: {resolved}")
    return resolved


def validate_release_directory(roots: ReleaseRoots, directory: Path) -> dict:
    directory = _safe_release_target(roots, directory)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ApplyError("active release manifest is missing or unsafe")
    try:
        raw_manifest = manifest_path.read_bytes()
        manifest = release_contract.validate_manifest(json.loads(raw_manifest.decode("utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, release_contract.ReleaseContractError) as exc:
        raise ApplyError(f"active release manifest is invalid: {exc}") from exc
    canonical = release_contract.canonical_manifest_bytes(manifest)
    if raw_manifest != canonical:
        raise ApplyError("active release manifest is not canonical")
    if hashlib.sha256(canonical).hexdigest() != directory.name:
        raise ApplyError("active release directory does not match manifest digest")
    actual_files: set[str] = set()
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ApplyError(f"active release contains a symlink: {path}")
        if path.is_file() and path != manifest_path:
            actual_files.add(path.relative_to(directory).as_posix())
    if actual_files != set(manifest["files"]):
        raise ApplyError("active release file set differs from manifest")
    for relative, digest in manifest["files"].items():
        path = directory / relative
        if not path.is_file() or path.is_symlink():
            raise ApplyError(f"active release file is missing or unsafe: {relative}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ApplyError(f"active release digest mismatch: {relative}")
    _validate_policy_bytes((directory / "release" / "policy.json").read_bytes())
    return manifest


def _materialize(roots: ReleaseRoots, archive: Path) -> tuple[Path, dict]:
    validated = release_contract.validate_archive(archive)
    _validate_policy_bytes(validated.files["release/policy.json"])
    roots.releases.mkdir(parents=True, exist_ok=True, mode=0o755)
    destination = roots.releases / validated.release_id
    if destination.exists():
        manifest = validate_release_directory(roots, destination)
        if manifest["commit"] != validated.manifest["commit"]:
            raise ApplyError("existing release commit differs from incoming release")
        return destination, manifest

    staging = roots.releases / f".staging-{validated.release_id}-{os.getpid()}"
    if staging.exists() or staging.is_symlink():
        raise ApplyError("release staging path already exists")
    try:
        staging.mkdir(mode=0o755)
        manifest_path = staging / "manifest.json"
        manifest_path.write_bytes(validated.manifest_bytes)
        os.chmod(manifest_path, 0o644)
        for relative, value in validated.files.items():
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            path.write_bytes(value)
            os.chmod(path, 0o755 if relative.startswith("release/bin/") else 0o644)
        staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    validate_release_directory(roots, destination)
    return destination, validated.manifest


def _link_units(
    roots: ReleaseRoots,
    release: Path,
    *,
    link_store: LinkStore,
    command_runner: CommandRunner,
) -> None:
    validate_release_directory(roots, release)
    roots.systemd_dir.mkdir(parents=True, exist_ok=True)
    for unit in MANAGED_UNITS:
        source = release / "release" / "systemd" / unit
        if not source.is_file() or source.is_symlink():
            raise ApplyError(f"managed unit is missing or unsafe: {unit}")
        link_store.replace(roots.systemd_dir / unit, source)
    command_runner(("systemctl", "daemon-reload"))
    command_runner(("systemctl", "enable", SERVICE))
    command_runner(("systemctl", "restart", SERVICE))


def _enable_timers(command_runner: CommandRunner) -> None:
    command_runner(("systemctl", "enable", "--now", *MANAGED_TIMERS))
    command_runner(("systemctl", "disable", "--now", LEGACY_CLEANUP_TIMER))


def _restore_bootstrap(
    roots: ReleaseRoots,
    *,
    link_store: LinkStore,
    command_runner: CommandRunner,
) -> None:
    marker = roots.bootstrap_backup / ".complete"
    backup_units = roots.bootstrap_backup / "systemd"
    if not marker.is_file() or not backup_units.is_dir():
        raise ApplyError("no complete bootstrap backup is available")
    command_runner(("systemctl", "disable", "--now", *MANAGED_TIMERS))
    roots.systemd_dir.mkdir(parents=True, exist_ok=True)
    for unit in MANAGED_UNITS:
        destination = roots.systemd_dir / unit
        source = backup_units / unit
        if source.is_file() and not source.is_symlink():
            temporary = destination.with_name(f".{destination.name}.bootstrap-{os.getpid()}")
            shutil.copyfile(source, temporary)
            os.chmod(temporary, 0o644)
            os.replace(temporary, destination)
        else:
            link_store.remove(destination)
    command_runner(("systemctl", "daemon-reload"))
    command_runner(("systemctl", "restart", SERVICE))
    command_runner(("systemctl", "enable", "--now", LEGACY_CLEANUP_TIMER))


@contextlib.contextmanager
def _exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if os.name != "nt":
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if os.name != "nt":
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def apply_release(
    roots: ReleaseRoots,
    archive: str | Path,
    *,
    health: Callable[[], bool] | None = None,
    command_runner: CommandRunner = _run,
    link_store: LinkStore | None = None,
) -> ApplyResult:
    links = link_store or AtomicSymlinkStore()
    health_check = health or (
        lambda: subprocess.run(
            [str(roots.current / "release" / "bin" / "toanaas-localbotapi-health")],
            check=False,
        ).returncode
        == 0
    )
    with _exclusive_lock(roots.lock_path):
        release, manifest = _materialize(roots, Path(archive))
        old_current = links.resolve(roots.current) if links.exists(roots.current) else None
        if old_current is not None:
            old_current = _safe_release_target(roots, old_current)
            validate_release_directory(roots, old_current)
            links.replace(roots.previous, old_current)
        links.replace(roots.current, release)
        activation_ok = False
        try:
            _link_units(roots, release, link_store=links, command_runner=command_runner)
            if not health_check():
                raise ApplyError("new release failed its health gate")
            _enable_timers(command_runner)
            activation_ok = True
        except Exception:
            # Any link, reload, restart, timer, or health failure enters the same
            # last-known-good recovery path. Never leave a half-activated release.
            activation_ok = False

        if activation_ok:
            if old_current is None:
                links.replace(roots.previous, release)
            return ApplyResult("activated", manifest["commit"], release)

        if old_current is not None:
            try:
                links.replace(roots.current, old_current)
                _link_units(
                    roots,
                    old_current,
                    link_store=links,
                    command_runner=command_runner,
                )
                if not health_check():
                    raise ApplyError("previous release failed health")
                _enable_timers(command_runner)
            except Exception as exc:
                raise ApplyError(
                    "release activation failed and previous release did not recover"
                ) from exc
            return ApplyResult("rolled_back", manifest["commit"], old_current)

        try:
            _restore_bootstrap(roots, link_store=links, command_runner=command_runner)
            links.remove(roots.current)
            if not health_check():
                raise ApplyError("bootstrap service failed health")
        except Exception as exc:
            raise ApplyError(
                "first release failed and bootstrap service did not recover"
            ) from exc
        return ApplyResult("rolled_back", manifest["commit"], None)


def verify_current(
    roots: ReleaseRoots, *, link_store: LinkStore | None = None
) -> dict:
    links = link_store or AtomicSymlinkStore()
    if not links.exists(roots.current):
        raise ApplyError("current release pointer is missing")
    return validate_release_directory(roots, links.resolve(roots.current))


def rollback(
    roots: ReleaseRoots,
    service: str,
    *,
    health: Callable[[], bool] | None = None,
    command_runner: CommandRunner = _run,
    link_store: LinkStore | None = None,
) -> ApplyResult:
    if service != SERVICE:
        raise ApplyError("rollback service is outside the fixed allowlist")
    links = link_store or AtomicSymlinkStore()
    health_check = health or (
        lambda: subprocess.run(
            [str(roots.current / "release" / "bin" / "toanaas-localbotapi-health")],
            check=False,
        ).returncode
        == 0
    )
    with _exclusive_lock(roots.lock_path):
        if not links.exists(roots.previous):
            raise ApplyError("previous release pointer is missing")
        target = _safe_release_target(roots, links.resolve(roots.previous))
        manifest = validate_release_directory(roots, target)
        links.replace(roots.current, target)
        _link_units(roots, target, link_store=links, command_runner=command_runner)
        if not health_check():
            raise ApplyError("manual rollback target failed health")
        return ApplyResult("rolled_back", manifest["commit"], target)


def validate_ready_marker(roots: ReleaseRoots, ready: Path) -> Path:
    incoming = roots.incoming_dir.resolve(strict=True)
    ready = Path(ready)
    if ready.parent.resolve(strict=True) != incoming:
        raise ApplyError("ready marker escapes incoming directory")
    if not ready.is_file() or ready.is_symlink() or ready.suffix != ".ready":
        raise ApplyError("ready marker is not a safe regular file")
    digest = ready.stem
    if not release_contract.SHA256_RE.fullmatch(digest):
        raise ApplyError("ready marker filename has an invalid digest")
    if ready.read_bytes() != f"{digest}\n".encode("ascii"):
        raise ApplyError("ready marker content does not match its filename")
    archive = incoming / f"{digest}.tgz"
    if not archive.is_file() or archive.is_symlink():
        raise ApplyError("ready archive is missing or unsafe")
    if archive.stat().st_size > release_contract.MAX_ARCHIVE_BYTES:
        raise ApplyError("ready archive exceeds the fixed size limit")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise ApplyError("ready archive digest does not match marker")
    return archive


def apply_ready(roots: ReleaseRoots) -> ApplyResult | None:
    roots.incoming_dir.mkdir(parents=True, exist_ok=True)
    ready_files = sorted(roots.incoming_dir.glob("*.ready"))
    if not ready_files:
        return None
    ready = ready_files[0]
    try:
        archive = validate_ready_marker(roots, ready)
        result = apply_release(roots, archive)
    except Exception:
        ready.replace(ready.with_suffix(".failed"))
        raise
    ready.unlink(missing_ok=True)
    archive.unlink(missing_ok=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("--archive", type=Path, required=True)
    commands.add_parser("apply-ready")
    commands.add_parser("verify-current")
    rollback_parser = commands.add_parser("rollback")
    rollback_parser.add_argument("--service", required=True)
    args = parser.parse_args()
    roots = ReleaseRoots.production()
    try:
        if args.command == "apply":
            result = apply_release(roots, args.archive)
        elif args.command == "apply-ready":
            result = apply_ready(roots)
        elif args.command == "verify-current":
            manifest = verify_current(roots)
            print(f"verified commit={manifest['commit']}")
            return 0
        else:
            result = rollback(roots, args.service)
    except (ApplyError, OSError, subprocess.SubprocessError, release_contract.ReleaseContractError) as exc:
        print(f"localbotapi_apply status=failed reason={type(exc).__name__}", file=sys.stderr)
        return 1
    if result is None:
        print("localbotapi_apply status=idle")
    else:
        print(f"localbotapi_apply status={result.status} commit={result.commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
