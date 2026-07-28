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


def test_reconcile_is_locked_and_rolls_back_only_the_localbot_service():
    text = _release_text("bin/toanaas-localbotapi-reconcile")
    assert "flock -n" in text
    assert "verify-current" in text
    assert 'CURRENT="/opt/toanaas-localbotapi/current"' in text
    assert 'RELEASE_HELPER="/usr/local/libexec/toanaas-localbotapi/apply-release"' in text
    assert "/opt/toanaas/localbotapi" not in text
    assert "toanaas-telegram-bot-api.service" in text
    assert "restart \"$SERVICE\"" in text
    assert " rollback " in text
    assert "flock -u 9" in text
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
    (roots.bootstrap_backup / ".complete").write_text("ok\n", encoding="ascii")
    (backup_units / apply_module.SERVICE).write_text("legacy-unit\n", encoding="ascii")
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
    assert 'restrict,command="/usr/local/libexec/toanaas-localbotapi/receive-release"' in installer
    assert "/opt/toanaas-localbotapi/releases" in installer
    assert "toanaas-deploy" in installer
    assert "mapfile -t deploy_key_lines" in installer
    assert "${#deploy_key_lines[@]}" in installer
    for guarded_path in (
        "$RELEASE_ROOT",
        "$RELEASES_ROOT",
        "$STATE_ROOT",
        "$STATE_ROOT/incoming",
        "$DEPLOY_HOME",
        "$DEPLOY_HOME/.ssh",
        "$LIBEXEC_ROOT",
    ):
        assert f'require_real_directory "{guarded_path}"' in installer
    assert "product-video" not in installer
    assert "remote_worker" not in installer
    for name in ("toanaas-localbotapi-apply.path", "toanaas-localbotapi-apply.service"):
        text = (BOOTSTRAP / "systemd" / name).read_text(encoding="utf-8")
        assert "product-video" not in text
        if name.endswith(".service"):
            assert "NoNewPrivileges=true" in text
            assert "ProtectSystem=strict" in text
            assert "ProtectHome=true" in text
