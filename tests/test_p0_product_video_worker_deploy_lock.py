from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "deploy-vps.yml"
SCRIPT_PATH = ROOT / "scripts" / "vps" / "sync_product_video_worker_release.sh"
ALLOWED_CHANGED_FILES = {
    ".github/workflows/deploy-vps.yml",
    "scripts/vps/sync_product_video_worker_release.sh",
    "tests/test_p0_product_video_worker_deploy_lock.py",
}
TARGET_REF = "refs/deployments/bot-release"
CANONICAL_CAPABILITY = "canonical_multiscene_b13_r18c_v1"


def _workflow() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _script() -> str:
    assert SCRIPT_PATH.is_file(), f"missing deployment transaction: {SCRIPT_PATH}"
    return SCRIPT_PATH.read_text(encoding="utf-8")


def _run(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {args}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _git(cwd: Path, *args: str) -> str:
    return _run(["git", *args], cwd=cwd).stdout.strip()


def _bash() -> str:
    bash = shutil.which("bash")
    if bash:
        return bash
    candidate = Path(r"C:\Program Files\Git\usr\bin\bash.exe")
    assert candidate.is_file(), "bash is required for the VPS transaction fixture"
    return str(candidate)


def _posix(path: Path) -> str:
    return path.resolve().as_posix()


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture()
def release_fixture() -> dict[str, object]:
    tmp_path = Path(tempfile.mkdtemp(prefix="pvdeploy-"))
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init")
    _git(source, "config", "user.email", "fixture@example.invalid")
    _git(source, "config", "user.name", "fixture")

    (source / "requirements.lock").write_text("old-lock\n", encoding="utf-8")
    (source / "bot.py").write_text("BUILD = 'old'\n", encoding="utf-8")
    (source / "remote_worker.py").write_text("CAP = 'old'\n", encoding="utf-8")
    (source / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    old_sha = _commit(source, "old")

    (source / "requirements.lock").write_text("target-lock\n", encoding="utf-8")
    (source / "bot.py").write_text("BUILD = 'target'\n", encoding="utf-8")
    (source / "remote_worker.py").write_text("CAP = 'target'\n", encoding="utf-8")
    target_sha = _commit(source, "target")
    _git(source, "update-ref", TARGET_REF, target_sha)

    staging = tmp_path / "staging"
    staging.mkdir()
    bundle = staging / "release.bundle"
    _git(source, "bundle", "create", str(bundle), TARGET_REF)
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    (staging / "checksums.sha256").write_text(
        f"{digest}  release.bundle\n", encoding="utf-8", newline="\n"
    )

    repos: dict[str, Path] = {}
    for name in ("bot", "worker"):
        repo = tmp_path / name
        _run(["git", "clone", "--quiet", str(source), str(repo)], cwd=tmp_path)
        _git(repo, "checkout", "--detach", old_sha)
        fake_python = """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$PYTHON_LOG"
case "$*" in
  *"-m pip check"*)
    current_sha="$(git -C "__REPO__" rev-parse HEAD)"
    if [ "__KIND__" = "worker" ] && [ "${FAKE_WORKER_SHA_DRIFT:-0}" = "1" ] && [ "$current_sha" = "__TARGET__" ]; then
      git -C "__REPO__" checkout --quiet --detach "__OLD__"
    fi
    if [ "__KIND__" = "bot" ] && [ "${FAKE_BOT_SHA_DRIFT:-0}" = "1" ] && [ "$current_sha" = "__TARGET__" ]; then
      git -C "__REPO__" checkout --quiet --detach "__OLD__"
    fi
    ;;
  *"remote_worker.py --ping --dry-run --owner-product-video"*)
    if [ "${FAKE_WORKER_PROBE_FAIL:-0}" = "1" ]; then
      exit 9
    fi
    printf '%s\\n' 'ping: OK' 'claim skipped because dry-run: yes'
    ;;
esac
exit 0
""".replace("__REPO__", _posix(repo)).replace("__KIND__", name).replace(
            "__TARGET__", target_sha
        ).replace("__OLD__", old_sha)
        _write_executable(repo / ".venv" / "bin" / "python", fake_python)
        repos[name] = repo

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "systemctl",
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$SYSTEMCTL_LOG"
case "${1:-}" in
  cat)
    printf '[Service]\\nWorkingDirectory=%s\\nExecStart=%s/.venv/bin/python %s/remote_worker.py --owner-product-video\\n' "$WORKER_DIR" "$WORKER_DIR" "$WORKER_DIR"
    ;;
  is-active)
    service="${3:-${2:-}}"
    if [ "$service" = "$SERVICE_NAME" ] && [ "${FAKE_WORKER_ACTIVE_FAIL:-0}" = "1" ]; then
      exit 3
    fi
    ;;
esac
exit 0
""",
    )
    _write_executable(
        fake_bin / "curl",
        """#!/usr/bin/env bash
set -euo pipefail
if [ "${FAKE_HEALTH_FAIL:-0}" = "1" ]; then
  exit 22
fi
printf '%s\\n' '{"status":"ok"}'
""",
    )

    worker_env = tmp_path / "worker.env"
    worker_env.write_text(
        "LOCAL_WORKER_TOKEN=fixture-token\nLOCAL_WORKER_API_URL=http://fixture.invalid\n",
        encoding="utf-8",
    )
    systemctl_log = tmp_path / "systemctl.log"
    python_log = tmp_path / "python.log"
    systemctl_log.write_text("", encoding="utf-8")
    python_log.write_text("", encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "TARGET_SHA": target_sha,
            "STAGING_DIR": _posix(staging),
            "BOT_DIR": _posix(repos["bot"]),
            "WORKER_DIR": _posix(repos["worker"]),
            "WORKER_ENV_FILE": _posix(worker_env),
            "SERVICE_NAME": "toanaas-worker-owner-product-video.service",
            "BOT_SERVICE_NAME": "toanaas-bot.service",
            "HEALTH_ATTEMPTS": "1",
            "HEALTH_SLEEP_SECONDS": "0",
            "SYSTEMCTL_LOG": _posix(systemctl_log),
            "PYTHON_LOG": _posix(python_log),
            "SYSTEMCTL_BIN": _posix(fake_bin / "systemctl"),
            "CURL_BIN": _posix(fake_bin / "curl"),
        }
    )
    return {
        "old_sha": old_sha,
        "target_sha": target_sha,
        "bot": repos["bot"],
        "worker": repos["worker"],
        "staging": staging,
        "systemctl_log": systemctl_log,
        "python_log": python_log,
        "env": env,
    }


def _run_transaction(fixture: dict[str, object], **overrides: str) -> subprocess.CompletedProcess[str]:
    env = dict(fixture["env"])
    env.update(overrides)
    return _run(
        [_bash(), "-lc", 'exec "$1"', "bash", _posix(SCRIPT_PATH)],
        cwd=ROOT,
        env=env,
        check=False,
    )


def _backup_targets(repo: Path) -> list[str]:
    output = _git(
        repo,
        "for-each-ref",
        "--format=%(objectname)",
        "refs/backups/product-video-deploy/",
    )
    return [line for line in output.splitlines() if line]


def test_workflow_invokes_exact_sha_transaction_from_verified_release_bundle() -> None:
    workflow = _workflow().replace(r'\"', '"').replace(r"\$", "$")
    required = (
        "python -m py_compile bot.py remote_worker.py services/remote_worker_api.py",
        "sync_product_video_worker_release.sh",
        "sha256sum release.tar release.bundle sync_product_video_worker_release.sh",
        "TARGET_SHA='${TARGET_SHA}'",
        r'STAGING_DIR="/tmp/deploy-bot-$TARGET_SHA"',
        'source "$STAGING_DIR/sync_product_video_worker_release.sh"',
        "prepare_product_video_worker_release",
        "activate_product_video_worker_release",
        "commit_product_video_release_transaction",
    )
    for fragment in required:
        assert fragment in workflow


def test_workflow_wraps_existing_bot_activation_in_worker_transaction() -> None:
    workflow = _workflow().replace(r'\"', '"').replace(r"\$", "$")
    prepare = workflow.index("prepare_product_video_worker_release")
    bot_restart = workflow.index("systemctl restart toanaas-bot.service", prepare)
    bot_health = workflow.index("HEALTH_PAYLOAD_VALIDATED", bot_restart)
    activate = workflow.index("activate_product_video_worker_release", bot_health)
    commit = workflow.index("commit_product_video_release_transaction", activate)
    assert prepare < bot_restart < bot_health < activate < commit


def test_transaction_is_fail_closed_and_uses_no_destructive_or_remote_git() -> None:
    source = _script()
    required = (
        "^[0-9a-fA-F]{40}$",
        "sha256sum -c checksums.sha256",
        "git bundle verify",
        'cat-file -e "$TARGET_SHA^{commit}"',
        "status --porcelain=v1 --untracked-files=all",
        "refs/backups/product-video-deploy/",
        'fetch "$STAGING_DIR/release.bundle"',
        "--require-hashes",
        '"$SYSTEMCTL_BIN" cat',
    )
    forbidden = (
        "git reset",
        "git clean",
        "git pull",
        "git fetch origin",
        "git stash",
        "rm ",
        "sed -i",
    )
    for fragment in required:
        assert fragment in source
    for fragment in forbidden:
        assert fragment not in source


def test_activation_order_stops_worker_before_switch_and_starts_after_bot_health() -> None:
    source = _script()
    prepare = source[
        source.index("prepare_product_video_worker_release() {") : source.index(
            "\n}\n\nactivate_product_video_worker_release()"
        )
    ]
    activate = source[
        source.index("activate_product_video_worker_release() {") : source.index(
            "\n}\n\ncommit_product_video_release_transaction()"
        )
    ]
    main = source[source.index("main() {") : source.index('\n}\n\nif [[ "${BASH_SOURCE[0]}"')]
    stop = prepare.index('"$SYSTEMCTL_BIN" stop "$SERVICE_NAME"')
    worker_switch = prepare.index('switch_to_target "$WORKER_DIR" "worker"', stop)
    prepare_call = main.index("prepare_product_video_worker_release")
    bot_switch = main.index('switch_to_target "$BOT_DIR" "bot"', prepare_call)
    bot_restart = main.index('"$SYSTEMCTL_BIN" restart "$BOT_SERVICE_NAME"', bot_switch)
    nginx_health = main.index('"$SYSTEMCTL_BIN" is-active --quiet "$NGINX_SERVICE_NAME"', bot_restart)
    bot_health = main.index("prove_bot_health", nginx_health)
    activate_call = main.index("activate_product_video_worker_release", bot_health)
    commit_call = main.index("commit_product_video_release_transaction", activate_call)
    safe_probe = activate.index("prove_worker_capability_and_safe_heartbeat")
    worker_start = activate.index('"$SYSTEMCTL_BIN" start "$SERVICE_NAME"', safe_probe)
    worker_health = activate.index("WORKER_TARGET_HEALTH_PROVEN", worker_start)
    assert stop < worker_switch
    assert prepare_call < bot_switch < bot_restart < nginx_health < bot_health < activate_call < commit_call
    assert safe_probe < worker_start < worker_health


def test_transaction_has_exact_sha_guards_and_two_repo_rollback() -> None:
    source = _script()
    required = (
        'assert_exact_sha "$WORKER_DIR" "$TARGET_SHA" "worker target"',
        'assert_exact_sha "$BOT_DIR" "$TARGET_SHA" "bot target"',
        'restore_repo "$BOT_DIR" "$PREV_BOT_SHA" "bot"',
        'restore_repo "$WORKER_DIR" "$PREV_WORKER_SHA" "worker"',
        'sync_locked_dependencies "$BOT_DIR"',
        'sync_locked_dependencies "$WORKER_DIR"',
        "ROLLBACK_COMPLETED",
    )
    for fragment in required:
        assert fragment in source


def test_health_probe_is_ping_only_and_requires_owner_multiscene_capabilities() -> None:
    source = _script()
    assert "remote_worker.py --ping --dry-run --owner-product-video" in source
    assert "remote_worker.py --once --owner-product-video" not in source
    assert '"owner_product_video"' in source
    assert f'"{CANONICAL_CAPABILITY}"' in source
    assert "provider_submit" not in source


@pytest.mark.parametrize("wip_kind", ["tracked", "untracked"])
def test_worker_untracked_or_tracked_wip_aborts_without_mutation(
    release_fixture: dict[str, object],
    wip_kind: str,
) -> None:
    worker = release_fixture["worker"]
    wip = worker / ("remote_worker.py" if wip_kind == "tracked" else "owner-wip.txt")
    wip.write_text(f"preserve {wip_kind}\n", encoding="utf-8")

    result = _run_transaction(release_fixture)

    assert result.returncode != 0
    assert "worker worktree is not clean" in (result.stdout + result.stderr)
    assert _git(worker, "rev-parse", "HEAD") == release_fixture["old_sha"]
    assert _git(release_fixture["bot"], "rev-parse", "HEAD") == release_fixture["old_sha"]
    assert wip.read_text(encoding="utf-8") == f"preserve {wip_kind}\n"
    assert release_fixture["systemctl_log"].read_text(encoding="utf-8") == ""


def test_success_switches_both_repos_and_keeps_backup_refs(
    release_fixture: dict[str, object],
) -> None:
    result = _run_transaction(release_fixture)

    assert result.returncode == 0, result.stdout + result.stderr
    for name in ("bot", "worker"):
        repo = release_fixture[name]
        assert _git(repo, "rev-parse", "HEAD") == release_fixture["target_sha"]
        assert _backup_targets(repo) == [release_fixture["old_sha"]]
    logs = release_fixture["systemctl_log"].read_text(encoding="utf-8")
    assert logs.index("stop toanaas-worker-owner-product-video.service") < logs.index(
        "restart toanaas-bot.service"
    )
    assert logs.index("restart toanaas-bot.service") < logs.index(
        "start toanaas-worker-owner-product-video.service"
    )
    python_log = release_fixture["python_log"].read_text(encoding="utf-8")
    assert "remote_worker.py --ping --dry-run --owner-product-video" in python_log
    assert "remote_worker.py --once" not in python_log

    manifest_file = release_fixture["staging"] / "transaction_manifest.json"
    assert manifest_file.is_file()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["target_sha"] == release_fixture["target_sha"]
    assert manifest["previous_bot_sha"] == release_fixture["old_sha"]
    assert manifest["previous_worker_sha"] == release_fixture["old_sha"]
    assert manifest["worker_prepared"] is True
    assert manifest["bot_healthy"] is True
    assert manifest["worker_activated"] is True
    assert manifest["worker_verified"] is True
    assert manifest["committed"] is True


@pytest.mark.parametrize(
    ("failure_env", "expected_marker"),
    [
        ({"FAKE_HEALTH_FAIL": "1"}, "bot health endpoint failed"),
        ({"FAKE_WORKER_PROBE_FAIL": "1"}, "safe worker dry-run probe failed"),
        ({"FAKE_WORKER_ACTIVE_FAIL": "1"}, "worker service is not active"),
        ({"FAKE_WORKER_SHA_DRIFT": "1"}, "worker target SHA mismatch"),
        ({"FAKE_BOT_SHA_DRIFT": "1"}, "bot target SHA mismatch"),
    ],
)
def test_activation_failure_rolls_back_both_shas_and_dependency_locks(
    release_fixture: dict[str, object],
    failure_env: dict[str, str],
    expected_marker: str,
) -> None:
    result = _run_transaction(release_fixture, **failure_env)

    assert result.returncode != 0
    assert expected_marker in (result.stdout + result.stderr)
    for name in ("bot", "worker"):
        repo = release_fixture[name]
        assert _git(repo, "rev-parse", "HEAD") == release_fixture["old_sha"]
        assert (repo / "requirements.lock").read_text(encoding="utf-8") == "old-lock\n"
    assert "ROLLBACK_COMPLETED" in (result.stdout + result.stderr)
    manifest_file = release_fixture["staging"] / "transaction_manifest.json"
    if manifest_file.is_file():
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        assert manifest["committed"] is False
    pip_installs = [
        line
        for line in release_fixture["python_log"].read_text(encoding="utf-8").splitlines()
        if "-m pip install --require-hashes" in line
    ]
    assert len(pip_installs) >= 4
    service_log = release_fixture["systemctl_log"].read_text(encoding="utf-8").splitlines()
    assert "restart toanaas-bot.service" in service_log
    expected_worker_restore = (
        "stop toanaas-worker-owner-product-video.service"
        if failure_env.get("FAKE_WORKER_ACTIVE_FAIL") == "1"
        else "start toanaas-worker-owner-product-video.service"
    )
    assert service_log[-1] == expected_worker_restore


def test_bundle_target_mismatch_aborts_before_service_stop(
    release_fixture: dict[str, object],
) -> None:
    result = _run_transaction(release_fixture, TARGET_SHA=str(release_fixture["old_sha"]))

    assert result.returncode != 0
    assert "bundle target mismatch" in (result.stdout + result.stderr)
    assert release_fixture["systemctl_log"].read_text(encoding="utf-8") == ""


def test_task_changes_only_allowlisted_deploy_files_and_not_trend_pricing() -> None:
    status = _run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
    ).stdout.splitlines()
    changed = {
        line[3:].replace("\\", "/")
        for line in status
        if len(line) >= 4 and not line[3:].startswith(".agents/")
    }
    deploy_files = {
        ".github/workflows/deploy-vps.yml",
        "scripts/vps/sync_product_video_worker_release.sh",
    }
    assert not (changed & deploy_files), f"Deploy files unexpectedly dirty: {changed & deploy_files}"
    combined = _workflow() + "\n" + _script()
    assert "TREND_TIER_400" not in combined
    assert "TREND_80_XU" not in combined
    assert "video_trend" not in combined
