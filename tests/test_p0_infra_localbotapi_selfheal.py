from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
import stat
import sys
import tarfile
from types import SimpleNamespace
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


def _valid_bundle(tmp_path: Path, commit: str, name: str) -> Path:
    builder = _load_module("build_release")
    return builder.build_release(REPO, commit, tmp_path / name)


class _FakeLinks:
    def __init__(self):
        self.targets: dict[Path, Path] = {}

    def exists(self, link: Path) -> bool:
        return link in self.targets

    def resolve(self, link: Path) -> Path:
        return self.targets[link]

    def replace(self, link: Path, target: Path) -> None:
        self.targets[link] = target.resolve()

    def remove(self, link: Path) -> None:
        self.targets.pop(link, None)


def _empty_bootstrap_snapshot(roots) -> None:
    (roots.bootstrap_backup / "systemd").mkdir(parents=True)
    (roots.bootstrap_backup / "drop-ins").mkdir()
    (roots.bootstrap_backup / ".complete").write_bytes(b"snapshot-v2\n")
    _secure_bootstrap_snapshot_storage(roots)


def _secure_bootstrap_snapshot_storage(roots) -> None:
    """Mirror the root-only snapshot permissions used by the installer."""
    snapshot = roots.bootstrap_backup
    for directory in (snapshot, snapshot / "systemd", snapshot / "drop-ins"):
        directory.chmod(0o700)
    for path in snapshot.rglob("*"):
        if path.is_file():
            path.chmod(0o600)


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
    files = {
        name: (REPO / "deploy" / "localbotapi" / name).read_bytes()
        for name in contract.EXPECTED_RELEASE_FILES
    }

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
    assert 'exec 9<>"$LOCK_FILE"' in text
    assert "O_NOFOLLOW" in text


def test_reconcile_is_locked_and_rolls_back_only_the_localbot_service():
    text = _release_text("bin/toanaas-localbotapi-reconcile")
    assert "flock -n" in text
    assert "verify-current" in text
    assert 'CURRENT="/opt/toanaas-localbotapi/current"' in text
    assert 'RELEASE_HELPER="/usr/local/libexec/toanaas-localbotapi/current/apply-release"' in text
    assert "/opt/toanaas/localbotapi" not in text
    assert "toanaas-telegram-bot-api.service" in text
    assert "restart \"$SERVICE\"" in text
    assert " rollback " in text
    assert "flock -u 9" in text
    assert 'exec 9<>"$LOCK_FILE"' in text
    assert "O_NOFOLLOW" in text
    assert text.index("flock -u 9") < text.index('"$RELEASE_HELPER" rollback')
    assert "readlink -f" in text
    assert "mv -Tf" in text
    for forbidden in ("product-video", "remote_worker", "local_worker", "git pull", ":latest"):
        assert forbidden not in text


def test_health_checks_real_upstream_external_gate_and_loopback_bind():
    text = _release_text("bin/toanaas-localbotapi-health")
    assert "127.0.0.1:8081" in text
    assert "root_http" in text and '"404"' in text
    assert "dummy_http" in text and '"401"' in text
    assert "missing_secret_status" in text and '"403"' in text
    assert "wrong_secret_status" in text and '"403"' in text
    assert "0.0.0.0:8081" in text and "[::]:8081" in text
    assert "--location" not in text
    assert "TELEGRAM_TOKEN" not in text
    assert "TELEGRAM_API_HASH" not in text


def test_certificate_watcher_checks_expiry_without_changing_time():
    text = _release_text("bin/toanaas-localbotapi-cert-watch")
    assert "x509 -checkend 1209600" in text
    assert "tg.toanaas.vn:443" in text
    assert "-verify_return_error" in text
    assert '-verify_hostname "$CERT_HOST"' in text
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
    assert "--env TELEGRAM_API_ID_FILE=/run/secrets/api_id" in service
    assert "--env TELEGRAM_API_HASH_FILE=/run/secrets/api_hash" in service
    assert "target=/tmp/telegram-bot-api" in service
    assert "--read-only" in service
    assert "--cap-drop ALL" in service
    assert "@sha256:2e93a720f71f82e41a42dc89e258efda09e6791f8d959e6801d15f88408e8eb1" in service
    assert ":latest" not in service
    assert "Restart=always" in service
    for preserved_control in (
        "PrivateDevices=true",
        "ProtectHostname=true",
        "ProtectClock=true",
        "ProtectKernelTunables=true",
        "ProtectKernelModules=true",
        "ProtectKernelLogs=true",
        "ProtectControlGroups=true",
        "RestrictNamespaces=true",
        "RestrictRealtime=true",
        "SystemCallArchitectures=native",
        "UMask=0077",
    ):
        assert preserved_control in service


def test_apply_activates_atomically_and_restores_previous_on_failed_health(tmp_path):
    apply_module = _load_module("apply_release")
    roots = apply_module.ReleaseRoots(
        release_root=tmp_path / "opt" / "toanaas-localbotapi",
        systemd_dir=tmp_path / "etc" / "systemd" / "system",
        incoming_dir=tmp_path / "var" / "lib" / "toanaas-localbotapi" / "incoming",
        bootstrap_backup=tmp_path / "var" / "lib" / "toanaas-localbotapi" / "bootstrap-backup",
        lock_path=tmp_path / "run" / "lock" / "toanaas-localbotapi-apply.lock",
    )
    commands: list[tuple[str, ...]] = []
    runner = lambda argv: commands.append(tuple(argv))
    links = _FakeLinks()
    _empty_bootstrap_snapshot(roots)

    first_bundle = _valid_bundle(tmp_path, "1" * 40, "first.tgz")
    first = apply_module.apply_release(
        roots,
        first_bundle,
        health=lambda: True,
        command_runner=runner,
        link_store=links,
    )
    first_target = links.resolve(roots.current)
    assert first.status == "activated"
    assert first_target.is_dir()
    assert (
        "systemctl",
        "disable",
        "--now",
        "toanaas-tgbotapi-cleanup.timer",
    ) in commands

    health_results = iter((False, True))
    second_bundle = _valid_bundle(tmp_path, "2" * 40, "second.tgz")
    second = apply_module.apply_release(
        roots,
        second_bundle,
        health=lambda: next(health_results),
        command_runner=runner,
        link_store=links,
    )

    assert second.status == "rolled_back"
    assert links.resolve(roots.current) == first_target
    assert links.resolve(roots.previous) == first_target
    assert all("product-video" not in " ".join(command) for command in commands)
    assert all("remote_worker" not in " ".join(command) for command in commands)


def test_interrupted_candidate_resume_preserves_last_known_good(tmp_path):
    apply_module = _load_module("apply_release")
    roots = apply_module.ReleaseRoots(
        release_root=tmp_path / "release-root",
        systemd_dir=tmp_path / "systemd",
        incoming_dir=tmp_path / "incoming",
        bootstrap_backup=tmp_path / "bootstrap",
        lock_path=tmp_path / "apply.lock",
    )
    links = _FakeLinks()
    _empty_bootstrap_snapshot(roots)
    known_good_bundle = _valid_bundle(tmp_path, "8" * 40, "known-good-resume.tgz")
    apply_module.apply_release(
        roots,
        known_good_bundle,
        health=lambda: True,
        command_runner=lambda _argv: None,
        link_store=links,
    )
    known_good = links.resolve(roots.current)
    candidate_bundle = _valid_bundle(tmp_path, "9" * 40, "interrupted.tgz")

    with pytest.raises(KeyboardInterrupt):
        apply_module.apply_release(
            roots,
            candidate_bundle,
            health=lambda: True,
            command_runner=lambda _argv: (_ for _ in ()).throw(KeyboardInterrupt()),
            link_store=links,
        )

    interrupted_candidate = links.resolve(roots.current)
    assert interrupted_candidate != known_good
    assert links.resolve(roots.previous) == known_good

    result = apply_module.apply_release(
        roots,
        candidate_bundle,
        health=lambda: True,
        command_runner=lambda _argv: None,
        link_store=links,
    )
    assert result.status == "activated"
    assert links.resolve(roots.current) == interrupted_candidate
    assert links.resolve(roots.previous) == known_good


def test_first_release_failure_restores_bootstrap_units_and_legacy_cleanup(tmp_path):
    apply_module = _load_module("apply_release")
    roots = apply_module.ReleaseRoots(
        release_root=tmp_path / "opt" / "toanaas-localbotapi",
        systemd_dir=tmp_path / "etc" / "systemd" / "system",
        incoming_dir=tmp_path / "incoming",
        bootstrap_backup=tmp_path / "bootstrap-backup",
        lock_path=tmp_path / "apply.lock",
    )
    backup_units = roots.bootstrap_backup / "systemd"
    backup_units.mkdir(parents=True)
    (roots.bootstrap_backup / ".complete").write_bytes(b"snapshot-v2\n")
    (roots.bootstrap_backup / "drop-ins").mkdir()
    (backup_units / apply_module.SERVICE).write_text("legacy-unit\n", encoding="ascii")
    (backup_units / f"{apply_module.SERVICE}.mode").write_bytes(b"644\n")
    _secure_bootstrap_snapshot_storage(roots)
    commands: list[tuple[str, ...]] = []
    health_results = iter((False, True))
    links = _FakeLinks()

    result = apply_module.apply_release(
        roots,
        _valid_bundle(tmp_path, "5" * 40, "first-fails.tgz"),
        health=lambda: next(health_results),
        command_runner=lambda argv: commands.append(tuple(argv)),
        link_store=links,
    )

    assert result.status == "rolled_back"
    assert not links.exists(roots.current)
    assert (roots.systemd_dir / apply_module.SERVICE).read_text(encoding="ascii") == "legacy-unit\n"
    assert (
        "systemctl",
        "enable",
        "--now",
        "toanaas-tgbotapi-cleanup.timer",
    ) in commands


def test_first_release_default_health_runs_before_candidate_pointer_is_removed(
    tmp_path, monkeypatch
):
    apply_module = _load_module("apply_release")
    roots = apply_module.ReleaseRoots(
        release_root=tmp_path / "release-root",
        systemd_dir=tmp_path / "systemd",
        incoming_dir=tmp_path / "incoming",
        bootstrap_backup=tmp_path / "bootstrap",
        lock_path=tmp_path / "apply.lock",
    )
    backup_units = roots.bootstrap_backup / "systemd"
    backup_units.mkdir(parents=True)
    (roots.bootstrap_backup / ".complete").write_bytes(b"snapshot-v2\n")
    (roots.bootstrap_backup / "drop-ins").mkdir()
    (backup_units / apply_module.SERVICE).write_text("legacy\n", encoding="ascii")
    (backup_units / f"{apply_module.SERVICE}.mode").write_bytes(b"644\n")
    _secure_bootstrap_snapshot_storage(roots)
    links = _FakeLinks()
    return_codes = iter((1, 0, 0))
    health_commands: list[str] = []

    class Result:
        def __init__(self, returncode):
            self.returncode = returncode

    def fake_run(argv, *, check):
        assert check is False
        assert links.exists(roots.current)
        health_commands.append(Path(argv[0]).name)
        return Result(next(return_codes))

    monkeypatch.setattr(apply_module.subprocess, "run", fake_run)
    result = apply_module.apply_release(
        roots,
        _valid_bundle(tmp_path, "a" * 40, "default-health-failure.tgz"),
        command_runner=lambda _argv: None,
        link_store=links,
    )
    assert result.status == "rolled_back"
    assert not links.exists(roots.current)
    assert health_commands == [
        "toanaas-localbotapi-health",
        "toanaas-localbotapi-health",
        "toanaas-localbotapi-cert-watch",
    ]


def test_apply_rolls_back_when_activation_command_fails(tmp_path):
    apply_module = _load_module("apply_release")
    roots = apply_module.ReleaseRoots(
        release_root=tmp_path / "releases-root",
        systemd_dir=tmp_path / "systemd",
        incoming_dir=tmp_path / "incoming",
        bootstrap_backup=tmp_path / "backup",
        lock_path=tmp_path / "apply.lock",
    )
    links = _FakeLinks()
    _empty_bootstrap_snapshot(roots)
    apply_module.apply_release(
        roots,
        _valid_bundle(tmp_path, "6" * 40, "known-good.tgz"),
        health=lambda: True,
        command_runner=lambda _argv: None,
        link_store=links,
    )
    known_good = links.resolve(roots.current)
    failed_once = False

    def fail_new_restart_once(argv):
        nonlocal failed_once
        if tuple(argv) == ("systemctl", "restart", apply_module.SERVICE) and not failed_once:
            failed_once = True
            raise RuntimeError("synthetic activation failure")

    result = apply_module.apply_release(
        roots,
        _valid_bundle(tmp_path, "7" * 40, "bad-activation.tgz"),
        health=lambda: True,
        command_runner=fail_new_restart_once,
        link_store=links,
    )

    assert failed_once
    assert result.status == "rolled_back"
    assert links.resolve(roots.current) == known_good


def test_missing_legacy_cleanup_timer_does_not_rollback_activation():
    apply_module = _load_module("apply_release")
    commands: list[tuple[str, ...]] = []

    def runner(argv):
        command = tuple(argv)
        commands.append(command)
        if command == ("systemctl", "cat", apply_module.LEGACY_CLEANUP_TIMER):
            raise RuntimeError("unit not found")

    apply_module._enable_timers(runner)
    assert ("systemctl", "enable", "--now", *apply_module.MANAGED_TIMERS) in commands
    assert ("systemctl", "disable", "--now", apply_module.LEGACY_CLEANUP_TIMER) not in commands


def test_legacy_cleanup_disable_failure_does_not_abort_timer_enablement():
    apply_module = _load_module("apply_release")
    commands: list[tuple[str, ...]] = []

    def runner(argv):
        command = tuple(argv)
        commands.append(command)
        if command == ("systemctl", "disable", "--now", apply_module.LEGACY_CLEANUP_TIMER):
            raise RuntimeError("systemd compatibility operation failed")

    apply_module._enable_timers(runner)
    assert ("systemctl", "enable", "--now", *apply_module.MANAGED_TIMERS) in commands
    assert ("systemctl", "disable", "--now", apply_module.LEGACY_CLEANUP_TIMER) in commands


def test_manual_bootstrap_restore_is_scoped_and_removes_release_pointers(
    tmp_path, monkeypatch
):
    apply_module = _load_module("apply_release")
    roots = apply_module.ReleaseRoots(
        release_root=tmp_path / "release-root",
        systemd_dir=tmp_path / "systemd",
        incoming_dir=tmp_path / "incoming",
        bootstrap_backup=tmp_path / "backup",
        lock_path=tmp_path / "lock",
    )
    backup_units = roots.bootstrap_backup / "systemd"
    backup_units.mkdir(parents=True)
    (roots.bootstrap_backup / ".complete").write_bytes(b"snapshot-v2\n")
    (backup_units / apply_module.SERVICE).write_text("legacy\n", encoding="ascii")
    (backup_units / f"{apply_module.SERVICE}.mode").write_bytes(b"600\n")
    backup_dropins = roots.bootstrap_backup / "drop-ins"
    backup_dropins.mkdir()
    (backup_dropins / "10-security-hardening.conf").write_text(
        "legacy-drop-in\n", encoding="ascii"
    )
    (backup_dropins / "10-security-hardening.conf.mode").write_bytes(b"640\n")
    _secure_bootstrap_snapshot_storage(roots)
    dropin = (
        roots.systemd_dir
        / f"{apply_module.SERVICE}.d"
        / "10-security-hardening.conf"
    )
    dropin.parent.mkdir(parents=True)
    dropin.write_text("legacy-drop-in\n", encoding="ascii")
    links = _FakeLinks()
    apply_module.apply_release(
        roots,
        _valid_bundle(tmp_path, "b" * 40, "active-before-bootstrap.tgz"),
        health=lambda: True,
        command_runner=lambda _argv: None,
        link_store=links,
    )
    assert not dropin.exists()

    with pytest.raises(apply_module.ApplyError, match="allowlist"):
        apply_module.restore_bootstrap(
            roots,
            "product-video.service",
            health=lambda: True,
            command_runner=lambda _argv: None,
            link_store=links,
        )

    chmod_calls: list[tuple[str, int]] = []
    real_chmod = apply_module.os.chmod

    def recording_chmod(path, mode):
        chmod_calls.append((Path(path).name, mode))
        real_chmod(path, mode)

    monkeypatch.setattr(apply_module.os, "chmod", recording_chmod)
    result = apply_module.restore_bootstrap(
        roots,
        apply_module.SERVICE,
        health=lambda: True,
        command_runner=lambda _argv: None,
        link_store=links,
    )
    assert result.status == "bootstrap_restored"
    assert not links.exists(roots.current)
    assert not links.exists(roots.previous)
    assert (roots.systemd_dir / apply_module.SERVICE).read_text(encoding="ascii") == "legacy\n"
    assert dropin.read_text(encoding="ascii") == "legacy-drop-in\n"
    assert any(name.startswith(f".{apply_module.SERVICE}.bootstrap-") and mode == 0o600 for name, mode in chmod_calls)
    assert any(name.startswith(".10-security-hardening.conf.bootstrap-") and mode == 0o640 for name, mode in chmod_calls)


def test_invalid_snapshot_mode_is_rejected_before_restore_mutation(tmp_path):
    apply_module = _load_module("apply_release")
    roots = apply_module.ReleaseRoots(
        release_root=tmp_path / "release-root",
        systemd_dir=tmp_path / "systemd",
        incoming_dir=tmp_path / "incoming",
        bootstrap_backup=tmp_path / "bootstrap",
        lock_path=tmp_path / "lock",
    )
    backup_units = roots.bootstrap_backup / "systemd"
    backup_units.mkdir(parents=True)
    (roots.bootstrap_backup / "drop-ins").mkdir()
    (roots.bootstrap_backup / ".complete").write_bytes(b"snapshot-v2\n")
    (backup_units / apply_module.SERVICE).write_text("snapshot\n", encoding="ascii")
    (backup_units / f"{apply_module.SERVICE}.mode").write_bytes(b"777\n")
    _secure_bootstrap_snapshot_storage(roots)
    roots.systemd_dir.mkdir(parents=True)
    destination = roots.systemd_dir / apply_module.SERVICE
    destination.write_text("live\n", encoding="ascii")
    commands: list[tuple[str, ...]] = []

    with pytest.raises(apply_module.ApplyError, match="mode is invalid"):
        apply_module._restore_bootstrap(
            roots,
            link_store=_FakeLinks(),
            command_runner=lambda argv: commands.append(tuple(argv)),
        )
    assert destination.read_text(encoding="ascii") == "live\n"
    assert commands == []


def test_snapshot_storage_rejects_wrong_mode_and_owner(monkeypatch, tmp_path):
    apply_module = _load_module("apply_release")
    snapshot_file = tmp_path / "snapshot"
    snapshot_file.write_bytes(b"trusted\n")
    monkeypatch.setattr(apply_module, "_POSIX_SECURITY_AVAILABLE", True)
    monkeypatch.setattr(apply_module.os, "geteuid", lambda: 0, raising=False)

    monkeypatch.setattr(
        apply_module.os,
        "lstat",
        lambda _path: SimpleNamespace(st_mode=stat.S_IFREG | 0o640, st_uid=0, st_nlink=1),
    )
    with pytest.raises(apply_module.ApplyError, match="storage mode"):
        apply_module._validate_snapshot_storage(snapshot_file, 0o600)

    monkeypatch.setattr(
        apply_module.os,
        "lstat",
        lambda _path: SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=1000, st_nlink=1),
    )
    with pytest.raises(apply_module.ApplyError, match="owner"):
        apply_module._validate_snapshot_storage(snapshot_file, 0o600)

    monkeypatch.setattr(
        apply_module.os,
        "lstat",
        lambda _path: SimpleNamespace(st_mode=stat.S_IFIFO | 0o600, st_uid=0, st_nlink=1),
    )
    with pytest.raises(apply_module.ApplyError, match="type"):
        apply_module._validate_snapshot_storage(snapshot_file, 0o600)

    monkeypatch.setattr(
        apply_module.os,
        "lstat",
        lambda _path: SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=0, st_nlink=2),
    )
    with pytest.raises(apply_module.ApplyError, match="hard link"):
        apply_module._validate_snapshot_storage(snapshot_file, 0o600)


def test_receiver_rejects_shell_commands_wrong_digest_and_oversize(tmp_path):
    receiver = _load_module("receive_release")
    bundle = _valid_bundle(tmp_path, "3" * 40, "valid.tgz")
    payload = bundle.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    incoming = tmp_path / "incoming"

    with pytest.raises(receiver.ReceiveError, match="command"):
        receiver.receive("bash -i", payload, incoming)
    with pytest.raises(receiver.ReceiveError, match="digest"):
        receiver.receive(f"upload {'3' * 40} {'0' * 64}", payload, incoming)
    with pytest.raises(receiver.ReceiveError, match="2 MiB"):
        receiver.receive(
            f"upload {'3' * 40} {digest}",
            b"x" * (2 * 1024 * 1024 + 1),
            incoming,
        )

    receipt = receiver.receive(f"upload {'3' * 40} {digest}", payload, incoming)
    assert receipt.archive == incoming / f"{digest}.tgz"
    assert receipt.ready == incoming / f"{digest}.ready"
    assert receipt.archive.read_bytes() == payload
    assert receipt.ready.read_text(encoding="ascii") == f"{digest}\n"
    assert receipt.release_id == _load_module("release_contract").validate_archive(bundle).release_id


def test_receiver_waits_for_exact_release_and_detects_rollback_marker(tmp_path):
    receiver = _load_module("receive_release")
    release_id = "a" * 64
    receipt = receiver.ReceiveReceipt(
        archive=tmp_path / "bundle.tgz",
        ready=tmp_path / "bundle.ready",
        commit="9" * 40,
        digest="b" * 64,
        release_id=release_id,
    )
    states = iter((None, ("9" * 40, release_id)))
    assert receiver.wait_for_activation(
        receipt,
        active_release=lambda: next(states),
        attempts=2,
        sleep=lambda _seconds: None,
    ) == ("9" * 40, release_id)

    receipt.ready.with_suffix(".rolled-back").write_text("failed\n", encoding="ascii")
    with pytest.raises(receiver.ReceiveError, match="rolled back"):
        receiver.wait_for_activation(
            receipt,
            active_release=lambda: None,
            attempts=1,
            sleep=lambda _seconds: None,
        )

    receipt.ready.with_suffix(".rolled-back").unlink()
    receipt.ready.write_bytes(f"{receipt.digest}\n".encode("ascii"))
    sleeps = 0

    def finish_apply(_seconds):
        nonlocal sleeps
        sleeps += 1
        receipt.ready.unlink()

    assert receiver.wait_for_activation(
        receipt,
        active_release=lambda: (receipt.commit, receipt.release_id),
        attempts=2,
        sleep=finish_apply,
    ) == (receipt.commit, receipt.release_id)
    assert sleeps == 1


def test_apply_ready_marker_must_match_archive_filename_content_and_digest(tmp_path):
    apply_module = _load_module("apply_release")
    roots = apply_module.ReleaseRoots(
        release_root=tmp_path / "release-root",
        systemd_dir=tmp_path / "systemd",
        incoming_dir=tmp_path / "incoming",
        bootstrap_backup=tmp_path / "backup",
        lock_path=tmp_path / "lock",
    )
    roots.incoming_dir.mkdir()
    bundle = _valid_bundle(tmp_path, "8" * 40, "ready-source.tgz")
    payload = bundle.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    archive = roots.incoming_dir / f"{digest}.tgz"
    archive.write_bytes(payload)
    ready = roots.incoming_dir / f"{digest}.ready"
    ready.write_bytes(f"{'0' * 64}\n".encode("ascii"))

    with pytest.raises(apply_module.ApplyError, match="ready marker"):
        apply_module.validate_ready_marker(roots, ready)

    ready.write_bytes(f"{digest}\n".encode("ascii"))
    assert apply_module.validate_ready_marker(roots, ready) == archive
    archive.write_bytes(payload + b"tampered")
    with pytest.raises(apply_module.ApplyError, match="digest"):
        apply_module.validate_ready_marker(roots, ready)


def test_apply_ready_keeps_forensics_and_marks_rolled_back(tmp_path, monkeypatch):
    apply_module = _load_module("apply_release")
    roots = apply_module.ReleaseRoots(
        release_root=tmp_path / "release-root",
        systemd_dir=tmp_path / "systemd",
        incoming_dir=tmp_path / "incoming",
        bootstrap_backup=tmp_path / "backup",
        lock_path=tmp_path / "lock",
    )
    roots.incoming_dir.mkdir()
    bundle = _valid_bundle(tmp_path, "a" * 40, "rolled-back-source.tgz")
    payload = bundle.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    archive = roots.incoming_dir / f"{digest}.tgz"
    ready = roots.incoming_dir / f"{digest}.ready"
    archive.write_bytes(payload)
    ready.write_bytes(f"{digest}\n".encode("ascii"))
    monkeypatch.setattr(
        apply_module,
        "apply_release",
        lambda _roots, _archive: apply_module.ApplyResult("rolled_back", "a" * 40, None),
    )

    result = apply_module.apply_ready(roots)

    assert result and result.status == "rolled_back"
    assert archive.is_file()
    assert not ready.exists()
    assert ready.with_suffix(".rolled-back").is_file()


def test_apply_rejects_policy_or_file_set_outside_fixed_allowlist(tmp_path):
    contract = _load_module("release_contract")
    expected = {
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
    }
    assert set(contract.EXPECTED_RELEASE_FILES) == expected
    manifest = {
        "schema": contract.SCHEMA,
        "commit": "4" * 40,
        "files": {name: "0" * 64 for name in expected | {"release/bin/evil"}},
        "policy_sha256": "0" * 64,
    }
    with pytest.raises(contract.ReleaseContractError, match="allowlist"):
        contract.validate_manifest(manifest)


def test_bootstrap_installs_forced_command_and_sandboxed_apply_units():
    installer = (BOOTSTRAP / "install_bootstrap.sh").read_text(encoding="utf-8")
    for helper in BOOTSTRAP.glob("*.py"):
        assert b"\r\n" not in helper.read_bytes(), f"bootstrap helper must use LF: {helper}"
    assert 'restrict,command="/usr/local/libexec/toanaas-localbotapi/current/receive-release"' in installer
    assert "/opt/toanaas-localbotapi/releases" in installer
    assert "toanaas-deploy" in installer
    assert "mapfile -t deploy_key_lines" in installer
    assert "${#deploy_key_lines[@]}" in installer
    assert 'ssh-keygen -l -f "$PUBLIC_KEY_FILE"' in installer
    assert "10-security-hardening.conf" in installer
    assert "BOOTSTRAP_SNAPSHOT_ROOT" in installer
    assert "incomplete_bootstrap_snapshot" in installer
    assert "snapshot_file" in installer
    assert 'mv -T -- "$snapshot_tmp" "$BOOTSTRAP_SNAPSHOT_ROOT"' in installer
    assert 'flock -w 30 9' in installer
    snapshot_verify = installer.index(
        'python3 "$SCRIPT_ROOT/apply_release.py" verify-bootstrap-snapshot'
    )
    helper_install = installer.index(
        'install -o root -g root -m 0644 "$SCRIPT_ROOT/release_contract.py"'
    )
    key_install = installer.index(
        'mv -Tf -- "$authorized_tmp" "$DEPLOY_HOME/.ssh/authorized_keys"'
    )
    systemd_enable = installer.index("systemctl enable --now toanaas-localbotapi-apply.path")
    assert snapshot_verify < helper_install < systemd_enable < key_install
    assert 'mktemp "$DEPLOY_HOME/.ssh/.authorized_keys.install.XXXXXXXX"' in installer
    assert (
        'mv -Tf -- "$authorized_tmp" "$DEPLOY_HOME/.ssh/authorized_keys"'
        in installer
    )
    assert 'usermod --home "$DEPLOY_HOME" --gid "$DEPLOY_USER" --groups \'\'' in installer
    assert 'chown root:"$DEPLOY_USER" "$authorized_tmp"' in installer
    assert 'chmod 0640 "$authorized_tmp"' in installer
    assert 'exec 9<>"$LOCK_FILE"' in installer
    assert "O_NOFOLLOW" in installer
    assert "HELPER_GENERATIONS_ROOT" in installer
    assert 'mv -Tf -- "$current_stage/current" "$HELPER_CURRENT"' in installer
    apply_source = (BOOTSTRAP / "apply_release.py").read_text(encoding="utf-8")
    assert "O_EXCL" in apply_source
    assert "O_NOFOLLOW" in apply_source
    assert "fchmod" in apply_source
    assert "fsync" in apply_source
    assert "bootstrap-{os.getpid()}" not in apply_source
    assert "snapshot_owner_uid=0" in apply_source
    assert 'install -d -o root -g "$DEPLOY_USER" -m 0750 "$STATE_ROOT"' in installer
    assert 'install -d -o root -g "$DEPLOY_USER" -m 0750 "$DEPLOY_HOME/.ssh"' in installer
    for guarded_path in (
        "$RELEASE_ROOT",
        "$RELEASES_ROOT",
        "$STATE_ROOT",
        "$STATE_ROOT/incoming",
        "$BOOTSTRAP_BACKUP_ROOT",
        "$BOOTSTRAP_SNAPSHOT_ROOT",
        "$BOOTSTRAP_SNAPSHOT_ROOT/systemd",
        "$BOOTSTRAP_SNAPSHOT_ROOT/drop-ins",
        "$DEPLOY_HOME",
        "$DEPLOY_HOME/.ssh",
        "$LIBEXEC_ROOT",
    ):
        assert f'require_real_directory "{guarded_path}"' in installer
    assert 'require_secure_directory_if_present "$HELPER_GENERATIONS_ROOT" 755' in installer
    assert 'install -d -o root -g root -m 0755 "$HELPER_GENERATIONS_ROOT"' in installer
    assert "product-video" not in installer
    assert "remote_worker" not in installer
    for name in ("toanaas-localbotapi-apply.path", "toanaas-localbotapi-apply.service"):
        text = (BOOTSTRAP / "systemd" / name).read_text(encoding="utf-8")
        assert "product-video" not in text
        if name.endswith(".service"):
            assert "NoNewPrivileges=true" in text
            assert "ProtectSystem=strict" in text
            assert "ProtectHome=true" in text
            if name == "toanaas-localbotapi-apply.service":
                assert "/usr/local/libexec/toanaas-localbotapi/current/apply-release" in text


def test_workflow_is_path_scoped_pinned_and_host_key_strict():
    path = REPO / ".github" / "workflows" / "deploy-localbotapi-vps.yml"
    assert path.is_file(), f"missing Local Bot API deployment workflow: {path}"
    workflow = path.read_text(encoding="utf-8")
    assert "deploy/localbotapi/**" not in workflow
    assert "deploy/localbotapi/release/**" in workflow
    assert "deploy/localbotapi/bootstrap/build_release.py" in workflow
    assert ".github/workflows/deploy-localbotapi-vps.yml" in workflow
    assert "environment: localbotapi-production" in workflow
    assert "branches: [main]" in workflow
    assert "workflow_dispatch:" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5" in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "UserKnownHostsFile=" in workflow
    assert "StrictHostKeyChecking=no" not in workflow
    assert "LOCALBOT_VPS_SSH_KEY" in workflow
    assert "LOCALBOT_VPS_KNOWN_HOSTS" in workflow
    assert "toanaas-deploy@tg.toanaas.vn" in workflow
    assert "build_release.py build" in workflow
    assert "build_release.py verify" in workflow
    assert "upload ${GITHUB_SHA}" in workflow
    assert "if: always()" in workflow
    for forbidden in (
        "git pull",
        ":latest",
        "set -x",
        "bot.py",
        "product-video",
        "remote_worker",
        "local_worker",
    ):
        assert forbidden not in workflow


def test_runbook_documents_trust_anchor_limits_rollback_and_scope():
    path = REPO / "deploy" / "localbotapi" / "README.md"
    assert path.is_file(), f"missing Local Bot API runbook: {path}"
    runbook = path.read_text(encoding="utf-8")
    for required in (
        "500",
        "3600",
        "last-known-good",
        "restore-bootstrap",
        "LOCALBOT_VPS_SSH_KEY",
        "LOCALBOT_VPS_KNOWN_HOSTS",
        "SHA256:xiXs/BXPp12IL8IFBSPQuRE5Jf03Dp6fLAoH+7jSz3o",
        "dual-generation",
        "Product Video",
        "SUBDUB MP4 LIVE PASS = NO",
    ):
        assert required in runbook
    assert "git pull" not in runbook
    assert ":latest" not in runbook
