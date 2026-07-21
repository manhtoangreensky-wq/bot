from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import remote_worker
from services import remote_worker_api, video_project_queue


SHA_NEW = "1fd1feca4a5e1111111111111111111111111111"
SHA_OLD = "73b7d9b56aa02222222222222222222222222222"


def _record(now: datetime, **overrides) -> dict:
    record = {
        "worker_id": "vps-toanaas-01",
        "worker_instance_id": "vps-toanaas-01:host:100",
        "generation_id": "generation-current",
        "service_mode": "owner_product_video",
        "capabilities": [video_project_queue.PRODUCT_VIDEO_CANONICAL_WORKER_CAPABILITY],
        "capability_version": video_project_queue.PRODUCT_VIDEO_CANONICAL_WORKER_CAPABILITY,
        "worker_sha": SHA_NEW,
        "worker_git_sha": SHA_NEW,
        "worker_git_head_sha": SHA_NEW,
        "git_sha": SHA_NEW,
        "runtime_target_sha": SHA_NEW,
        "worker_sha_source": "git_rev_parse_head",
        "worker_cwd": "/opt/toanaas-worker",
        "heartbeat_updated_at": (now - timedelta(seconds=5)).strftime("%Y-%m-%d %H:%M:%S"),
        "lease_expires_at": (now + timedelta(seconds=60)).strftime("%Y-%m-%d %H:%M:%S"),
    }
    record.update(overrides)
    return record


def test_worker_heartbeat_uses_current_checkout_git_head(monkeypatch, tmp_path):
    calls = []
    worker_cwd = str(tmp_path.resolve())

    def fake_run(cmd, cwd, capture_output, text, timeout, check):
        calls.append((cmd, cwd))
        return SimpleNamespace(returncode=0, stdout=SHA_NEW + "\n", stderr="")

    monkeypatch.setattr(remote_worker.os, "getcwd", lambda: worker_cwd)
    monkeypatch.setattr(remote_worker.subprocess, "run", fake_run)

    info = remote_worker.worker_git_head_info()

    assert info == {
        "worker_sha": SHA_NEW,
        "worker_git_sha": SHA_NEW,
        "worker_git_head_sha": SHA_NEW,
        "worker_sha_source": "git_rev_parse_head",
        "worker_cwd": worker_cwd,
    }
    assert calls[0][1] == worker_cwd


def test_git_failure_reports_unknown_and_never_reuses_env_sha(monkeypatch):
    monkeypatch.setenv("GIT_SHA", SHA_OLD)
    monkeypatch.setenv("WORKER_SHA", SHA_OLD)
    monkeypatch.setattr(
        remote_worker.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=128, stdout="", stderr="not a repo"),
    )

    info = remote_worker.worker_git_head_info("/not/a/repo")

    assert info["worker_sha"] == ""
    assert info["worker_git_head_sha"] == ""
    assert info["worker_sha_source"] == "unknown"


def test_identity_payload_contains_fresh_heartbeat_contract(monkeypatch):
    monkeypatch.setattr(
        remote_worker,
        "worker_git_head_info",
        lambda: {
            "worker_sha": SHA_NEW,
            "worker_git_sha": SHA_NEW,
            "worker_git_head_sha": SHA_NEW,
            "worker_sha_source": "git_rev_parse_head",
            "worker_cwd": "/opt/toanaas-worker",
        },
    )

    payload = remote_worker.worker_identity_payload("owner_product_video", ["product_video"])

    assert payload["worker_id"] == remote_worker.WORKER_ID
    assert payload["service_mode"] == "owner_product_video"
    assert payload["worker_sha_source"] == "git_rev_parse_head"
    assert payload["worker_git_head_sha"] == SHA_NEW
    assert payload["worker_cwd"] == "/opt/toanaas-worker"
    assert payload["heartbeat_updated_at"]
    assert payload["heartbeat_at"] == payload["heartbeat_updated_at"]


def test_latest_heartbeat_git_head_wins_and_stale_worker_sha_is_diagnostic_only():
    now = datetime(2026, 7, 13, 12, 0, 0)
    status = remote_worker_api.product_video_worker_compatibility(
        [_record(now, worker_sha=SHA_OLD)],
        runtime_sha=SHA_NEW,
        now=now,
    )

    assert status["worker_git_head_sha"] == SHA_NEW
    assert status["worker_sha"] == SHA_NEW
    assert status["worker_sha_matches_runtime"] is True
    assert status["heartbeat_sha_source_bug"] is True
    assert status["stale_worker_sha_ignored"] is True
    assert status["heartbeat_record_selected_by"] == "latest_active_owner_product_video_generation"


def test_latest_heartbeat_for_same_worker_generation_replaces_stale_sha():
    now = datetime(2026, 7, 13, 12, 0, 0)
    stale = _record(
        now,
        worker_sha=SHA_OLD,
        worker_git_sha=SHA_OLD,
        worker_git_head_sha=SHA_OLD,
        git_sha=SHA_OLD,
        runtime_target_sha=SHA_OLD,
        heartbeat_updated_at=(now - timedelta(seconds=20)).strftime("%Y-%m-%d %H:%M:%S"),
    )
    current = _record(now)

    status = remote_worker_api.product_video_worker_compatibility(
        [stale, current],
        runtime_sha=SHA_NEW,
        now=now,
    )

    assert status["worker_sha"] == SHA_NEW
    assert status["worker_git_head_sha"] == SHA_NEW
    assert status["worker_sha_matches_runtime"] is True
    assert status["heartbeat_records_considered"] == 2


def test_unknown_sha_source_does_not_reuse_stale_worker_sha():
    now = datetime(2026, 7, 13, 12, 0, 0)
    status = remote_worker_api.product_video_worker_compatibility(
        [
            _record(
                now,
                worker_sha=SHA_OLD,
                worker_git_sha="",
                worker_git_head_sha="",
                git_sha="",
                worker_sha_source="unknown",
            )
        ],
        runtime_sha=SHA_NEW,
        now=now,
    )

    assert status["worker_sha"] == ""
    assert status["worker_git_head_sha"] == ""
    assert status["worker_sha_source"] == "unknown"
    assert status["worker_sha_matches_runtime"] is False
    assert status["stale_worker_sha_ignored"] is True


def test_video_status_exposes_worker_source_truth_without_provider_changes():
    root = Path(__file__).resolve().parents[1]
    bot_source = (root / "bot.py").read_text(encoding="utf-8")
    remote_source = (root / "remote_worker.py").read_text(encoding="utf-8")

    assert "owner SHA source" in bot_source
    assert "owner git HEAD" in bot_source
    assert "owner cwd" in bot_source
    assert "heartbeat SHA source bug" in bot_source
    assert '"worker_sha_source": "git_rev_parse_head"' in remote_source
    assert "provider_submit" not in remote_source[remote_source.index("def worker_git_head_info"):remote_source.index("FFMPEG_PATH =")]
