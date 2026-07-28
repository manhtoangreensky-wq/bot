#!/usr/bin/env python3
"""Install and activate one verified Local Bot API infrastructure release."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import secrets
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Callable, NamedTuple, Protocol, Sequence

import release_contract


SERVICE = "toanaas-telegram-bot-api.service"
LEGACY_CLEANUP_TIMER = "toanaas-tgbotapi-cleanup.timer"
LEGACY_DROPIN_NAME = "10-security-hardening.conf"
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


_POSIX_SECURITY_AVAILABLE = os.name == "posix"


class ReleaseRoots:
    def __init__(
        self,
        *,
        release_root: Path,
        systemd_dir: Path,
        incoming_dir: Path,
        bootstrap_backup: Path,
        lock_path: Path,
        snapshot_owner_uid: int | None = None,
    ) -> None:
        self.release_root = Path(release_root)
        self.systemd_dir = Path(systemd_dir)
        self.incoming_dir = Path(incoming_dir)
        self.bootstrap_backup = Path(bootstrap_backup)
        self.lock_path = Path(lock_path)
        geteuid = getattr(os, "geteuid", None)
        self.snapshot_owner_uid = (
            int(snapshot_owner_uid)
            if snapshot_owner_uid is not None
            else (int(geteuid()) if callable(geteuid) else None)
        )

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
            bootstrap_backup=state / "bootstrap-backup" / "snapshot-v2",
            lock_path=Path("/run/lock/toanaas-localbotapi-reconcile.lock"),
            snapshot_owner_uid=0,
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
        if link.exists() and not link.is_symlink():
            raise ApplyError(f"refusing to replace non-symlink managed pointer: {link}")
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


def _release_health_gate(release: Path) -> bool:
    bin_dir = release / "release" / "bin"
    for name in ("toanaas-localbotapi-health", "toanaas-localbotapi-cert-watch"):
        if subprocess.run([str(bin_dir / name)], check=False).returncode != 0:
            return False
    return True


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


def _remove_legacy_dropin(roots: ReleaseRoots) -> None:
    destination = roots.systemd_dir / f"{SERVICE}.d" / LEGACY_DROPIN_NAME
    if not destination.exists() and not destination.is_symlink():
        return
    backup = roots.bootstrap_backup / "drop-ins" / LEGACY_DROPIN_NAME
    if (
        destination.is_symlink()
        or not destination.is_file()
        or backup.is_symlink()
        or not backup.is_file()
    ):
        raise ApplyError("legacy service drop-in is unsafe or was not backed up")
    if hashlib.sha256(destination.read_bytes()).digest() != hashlib.sha256(
        backup.read_bytes()
    ).digest():
        raise ApplyError("legacy service drop-in changed after bootstrap backup")
    destination.unlink()
    try:
        destination.parent.rmdir()
    except OSError:
        pass


def _snapshot_mode(source: Path) -> int:
    mode_file = source.with_name(f"{source.name}.mode")
    if mode_file.is_symlink() or not mode_file.is_file():
        raise ApplyError(f"bootstrap snapshot mode is missing or unsafe: {source.name}")
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(mode_file, flags)
        with os.fdopen(fd, "rb") as handle:
            raw = handle.read()
        if raw not in {b"600\n", b"640\n", b"644\n"}:
            raise ValueError
        return int(raw.strip(), 8)
    except (OSError, ValueError) as exc:
        raise ApplyError(f"bootstrap snapshot mode is invalid: {source.name}") from exc


def _validate_snapshot_storage(
    path: Path,
    expected_mode: int,
    *,
    expected_type: str | None = None,
    owner_uid: int | None = None,
) -> None:
    """Validate the filesystem trust anchor before using a snapshot entry.

    The bootstrap verifier runs as root in production.  Requiring the
    effective owner (root in production, the invoking test user elsewhere)
    prevents an unprivileged account from supplying a recovery snapshot while
    keeping the pure-Python test harness portable on Windows.
    """

    if not _POSIX_SECURITY_AVAILABLE:
        return
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise ApplyError(f"bootstrap snapshot storage is unavailable: {path.name}") from exc
    is_regular = stat.S_ISREG(info.st_mode)
    is_directory = stat.S_ISDIR(info.st_mode)
    if expected_type == "file" and not is_regular:
        raise ApplyError(f"bootstrap snapshot storage type is unsafe: {path.name}")
    if expected_type == "directory" and not is_directory:
        raise ApplyError(f"bootstrap snapshot storage type is unsafe: {path.name}")
    if expected_type is None and not (is_regular or is_directory):
        raise ApplyError(f"bootstrap snapshot storage type is unsafe: {path.name}")
    if stat.S_IMODE(info.st_mode) != expected_mode:
        raise ApplyError(f"bootstrap snapshot storage mode is unsafe: {path.name}")
    if is_regular and info.st_nlink != 1:
        raise ApplyError(f"bootstrap snapshot storage hard link is unsafe: {path.name}")
    if owner_uid is None:
        geteuid = getattr(os, "geteuid", None)
        owner_uid = int(geteuid()) if callable(geteuid) else None
    if owner_uid is not None and info.st_uid != int(owner_uid):
        raise ApplyError(f"bootstrap snapshot storage owner is unsafe: {path.name}")


def _atomic_restore_file(
    source: Path,
    destination: Path,
    mode: int,
    *,
    owner_uid: int | None = None,
) -> None:
    """Copy one trusted snapshot file without exposing a permissive temporary."""

    parent_info = os.lstat(destination.parent)
    if not stat.S_ISDIR(parent_info.st_mode):
        raise ApplyError("bootstrap restore destination parent is unsafe")
    if owner_uid is not None and parent_info.st_uid != int(owner_uid):
        raise ApplyError("bootstrap restore destination parent owner is unsafe")
    if _POSIX_SECURITY_AVAILABLE and stat.S_IMODE(parent_info.st_mode) & 0o022:
        raise ApplyError("bootstrap restore destination parent is writable")
    temporary = destination.with_name(
        f".{destination.name}.bootstrap-{secrets.token_hex(12)}"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd: int | None = None
    try:
        fd = os.open(temporary, flags, 0o600)
        source_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            source_flags |= os.O_NOFOLLOW
        source_fd = os.open(source, source_flags)
        source_info = os.fstat(source_fd)
        if not stat.S_ISREG(source_info.st_mode) or source_info.st_nlink != 1:
            os.close(source_fd)
            raise ApplyError(f"bootstrap snapshot source is unsafe: {source.name}")
        if owner_uid is not None and source_info.st_uid != int(owner_uid):
            os.close(source_fd)
            raise ApplyError(f"bootstrap snapshot source owner is unsafe: {source.name}")
        with os.fdopen(source_fd, "rb") as source_handle, os.fdopen(fd, "wb") as target_handle:
            fd = None
            shutil.copyfileobj(source_handle, target_handle)
            target_handle.flush()
            fchmod = getattr(os, "fchmod", None)
            if callable(fchmod):
                fchmod(target_handle.fileno(), mode)
            else:
                os.chmod(temporary, mode)
            fchown = getattr(os, "fchown", None)
            geteuid = getattr(os, "geteuid", None)
            if callable(fchown) and callable(geteuid) and int(geteuid()) == 0:
                fchown(target_handle.fileno(), 0, 0)
            os.fsync(target_handle.fileno())
        os.replace(temporary, destination)
        if _POSIX_SECURITY_AVAILABLE:
            directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            if hasattr(os, "O_DIRECTORY"):
                directory_flags |= os.O_DIRECTORY
            if hasattr(os, "O_NOFOLLOW"):
                directory_flags |= os.O_NOFOLLOW
            directory_fd = os.open(destination.parent, directory_flags)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if fd is not None:
            os.close(fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _restore_legacy_dropin(roots: ReleaseRoots) -> None:
    backup = roots.bootstrap_backup / "drop-ins" / LEGACY_DROPIN_NAME
    mode_file = backup.with_name(f"{backup.name}.mode")
    if not backup.exists() and not backup.is_symlink():
        if mode_file.exists() or mode_file.is_symlink():
            raise ApplyError("orphaned bootstrap service drop-in mode")
        return
    if backup.is_symlink() or not backup.is_file():
        raise ApplyError("bootstrap service drop-in backup is unsafe")
    destination = roots.systemd_dir / f"{SERVICE}.d" / LEGACY_DROPIN_NAME
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink() or not destination.is_file():
            raise ApplyError("existing bootstrap service drop-in is unsafe")
        # Preserve an explicit admin change made after bootstrap instead of
        # silently overwriting it during emergency recovery.
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    _atomic_restore_file(
        backup,
        destination,
        _snapshot_mode(backup),
        owner_uid=roots.snapshot_owner_uid,
    )


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
    _remove_legacy_dropin(roots)
    command_runner(("systemctl", "daemon-reload"))
    command_runner(("systemctl", "enable", SERVICE))
    command_runner(("systemctl", "restart", SERVICE))


def _enable_timers(command_runner: CommandRunner) -> None:
    command_runner(("systemctl", "enable", "--now", *MANAGED_TIMERS))
    # Older hosts may never have installed the legacy cleanup timer.  Probe
    # first so a missing compatibility unit cannot turn a healthy activation
    # into a rollback.
    try:
        command_runner(("systemctl", "cat", LEGACY_CLEANUP_TIMER))
        command_runner(("systemctl", "disable", "--now", LEGACY_CLEANUP_TIMER))
    except Exception:
        # Compatibility cleanup must never invalidate an otherwise healthy
        # Local Bot API activation on a host with a divergent systemd state.
        pass


def _validate_bootstrap_snapshot(roots: ReleaseRoots) -> Path:
    snapshot = roots.bootstrap_backup
    marker = snapshot / ".complete"
    backup_units = snapshot / "systemd"
    backup_dropins = snapshot / "drop-ins"
    if snapshot.is_symlink() or not snapshot.is_dir():
        raise ApplyError("bootstrap snapshot root is missing or unsafe")
    _validate_snapshot_storage(
        snapshot, 0o700, expected_type="directory", owner_uid=roots.snapshot_owner_uid
    )
    if marker.is_symlink() or not marker.is_file():
        raise ApplyError("no complete bootstrap snapshot is available")
    _validate_snapshot_storage(
        marker, 0o600, expected_type="file", owner_uid=roots.snapshot_owner_uid
    )
    if marker.read_bytes() != b"snapshot-v2\n":
        raise ApplyError("no complete bootstrap snapshot is available")
    for directory in (backup_units, backup_dropins):
        if directory.is_symlink() or not directory.is_dir():
            raise ApplyError("bootstrap snapshot directory is missing or unsafe")
        _validate_snapshot_storage(
            directory,
            0o700,
            expected_type="directory",
            owner_uid=roots.snapshot_owner_uid,
        )

    content_paths = {
        Path("systemd") / unit for unit in MANAGED_UNITS
    } | {Path("drop-ins") / LEGACY_DROPIN_NAME}
    allowed_files = {Path(".complete")}
    for content in content_paths:
        allowed_files.add(content)
        allowed_files.add(content.with_name(f"{content.name}.mode"))

    actual_files: set[Path] = set()
    actual_directories: set[Path] = set()
    for path in snapshot.rglob("*"):
        if path.is_symlink():
            raise ApplyError("bootstrap snapshot contains a symlink")
        if path.is_file():
            actual_files.add(path.relative_to(snapshot))
        elif path.is_dir():
            actual_directories.add(path.relative_to(snapshot))
        else:
            raise ApplyError("bootstrap snapshot contains an unsafe entry")
    if actual_directories != {Path("systemd"), Path("drop-ins")}:
        raise ApplyError("bootstrap snapshot contains an unexpected directory")
    if not actual_files.issubset(allowed_files):
        raise ApplyError("bootstrap snapshot contains an unexpected file")
    for relative in actual_files:
        _validate_snapshot_storage(
            snapshot / relative,
            0o600,
            expected_type="file",
            owner_uid=roots.snapshot_owner_uid,
        )
    for content in content_paths:
        mode = content.with_name(f"{content.name}.mode")
        if (content in actual_files) != (mode in actual_files):
            raise ApplyError("bootstrap snapshot content/mode pair is incomplete")
        if content in actual_files:
            _snapshot_mode(snapshot / content)
    return backup_units


def _restore_bootstrap(
    roots: ReleaseRoots,
    *,
    link_store: LinkStore,
    command_runner: CommandRunner,
) -> None:
    backup_units = _validate_bootstrap_snapshot(roots)
    command_runner(("systemctl", "disable", "--now", *MANAGED_TIMERS))
    roots.systemd_dir.mkdir(parents=True, exist_ok=True)
    for unit in MANAGED_UNITS:
        destination = roots.systemd_dir / unit
        source = backup_units / unit
        if source.is_file() and not source.is_symlink():
            _atomic_restore_file(
                source,
                destination,
                _snapshot_mode(source),
                owner_uid=roots.snapshot_owner_uid,
            )
        else:
            mode_file = source.with_name(f"{source.name}.mode")
            if source.exists() or source.is_symlink() or mode_file.exists() or mode_file.is_symlink():
                raise ApplyError(f"bootstrap unit snapshot is unsafe: {unit}")
            link_store.remove(destination)
    _restore_legacy_dropin(roots)
    command_runner(("systemctl", "daemon-reload"))
    command_runner(("systemctl", "restart", SERVICE))
    command_runner(("systemctl", "enable", "--now", LEGACY_CLEANUP_TIMER))


@contextlib.contextmanager
def _exclusive_lock(path: Path):
    parent = path.parent
    if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
        raise ApplyError("apply lock parent is unsafe")
    parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    if parent.is_symlink() or not parent.is_dir():
        raise ApplyError("apply lock parent is unsafe")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise ApplyError("apply lock is unsafe") from exc
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        os.close(fd)
        raise ApplyError("apply lock is unsafe")
    if _POSIX_SECURITY_AVAILABLE:
        geteuid = getattr(os, "geteuid", None)
        if callable(geteuid) and info.st_uid != int(geteuid()):
            os.close(fd)
            raise ApplyError("apply lock owner is unsafe")
        os.fchmod(fd, 0o600)
    handle = os.fdopen(fd, "a+b")
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
    health_check = health or (lambda: _release_health_gate(roots.current))
    with _exclusive_lock(roots.lock_path):
        release, manifest = _materialize(roots, Path(archive))
        current = links.resolve(roots.current) if links.exists(roots.current) else None
        if current is not None:
            current = _safe_release_target(roots, current)
            validate_release_directory(roots, current)

        # A killed apply service leaves the ready marker in place. If current
        # already points at this candidate, resume it without promoting the
        # half-activated candidate into previous and losing the last-known-good.
        if current == release:
            previous = links.resolve(roots.previous) if links.exists(roots.previous) else None
            if previous is not None:
                previous = _safe_release_target(roots, previous)
                validate_release_directory(roots, previous)
            old_current = previous if previous != release else None
        else:
            old_current = current

        if old_current is None:
            _validate_bootstrap_snapshot(roots)
        if current != release and old_current is not None:
            links.replace(roots.previous, old_current)
        if current != release:
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
            if not health_check():
                raise ApplyError("bootstrap service failed health")
        except Exception as exc:
            raise ApplyError(
                "first release failed and bootstrap service did not recover"
            ) from exc
        finally:
            links.remove(roots.current)
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
    health_check = health or (lambda: _release_health_gate(roots.current))
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


def restore_bootstrap(
    roots: ReleaseRoots,
    service: str,
    *,
    health: Callable[[], bool] | None = None,
    command_runner: CommandRunner = _run,
    link_store: LinkStore | None = None,
) -> ApplyResult:
    if service != SERVICE:
        raise ApplyError("bootstrap restore service is outside the fixed allowlist")
    links = link_store or AtomicSymlinkStore()
    health_release: Path | None = None
    if links.exists(roots.current):
        health_release = _safe_release_target(roots, links.resolve(roots.current))
    health_check = health or (
        lambda: bool(health_release and _release_health_gate(health_release))
    )
    with _exclusive_lock(roots.lock_path):
        _restore_bootstrap(roots, link_store=links, command_runner=command_runner)
        links.remove(roots.current)
        links.remove(roots.previous)
        if not health_check():
            raise ApplyError("bootstrap restore completed but service health failed")
        return ApplyResult("bootstrap_restored", "bootstrap", None)


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
    if result.status != "activated":
        ready.replace(ready.with_suffix(".rolled-back"))
        return result
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
    commands.add_parser("verify-bootstrap-snapshot")
    rollback_parser = commands.add_parser("rollback")
    rollback_parser.add_argument("--service", required=True)
    restore_parser = commands.add_parser("restore-bootstrap")
    restore_parser.add_argument("--service", required=True)
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
        elif args.command == "verify-bootstrap-snapshot":
            _validate_bootstrap_snapshot(roots)
            print("bootstrap_snapshot status=verified schema=snapshot-v2")
            return 0
        elif args.command == "rollback":
            result = rollback(roots, args.service)
        else:
            result = restore_bootstrap(roots, args.service)
    except (ApplyError, OSError, subprocess.SubprocessError, release_contract.ReleaseContractError) as exc:
        print(f"localbotapi_apply status=failed reason={type(exc).__name__}", file=sys.stderr)
        return 1
    if result is None:
        print("localbotapi_apply status=idle")
    else:
        print(f"localbotapi_apply status={result.status} commit={result.commit}")
    if args.command in {"apply", "apply-ready"} and result is not None:
        return 0 if result.status == "activated" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
