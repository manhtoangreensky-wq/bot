from __future__ import annotations

from pathlib import Path
import subprocess

from services import remote_worker_api


def test_bot_runtime_sha_falls_back_to_current_checkout_when_deploy_env_missing():
    root = Path(__file__).resolve().parents[1]
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=3,
        check=True,
    ).stdout.strip()

    assert remote_worker_api.resolve_runtime_sha({}, cwd=root) == expected
