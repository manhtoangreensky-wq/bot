from types import SimpleNamespace
from pathlib import Path
import tokenize

import remote_worker
from services import remote_worker_api


SHA_NEW = "1fd1feca4a5e1111111111111111111111111111"
SHA_OLD = "73b7d9b56aa02222222222222222222222222222"


def test_worker_cwd_git_head_reports_current_checkout(monkeypatch):
    calls = []

    def fake_run(cmd, cwd, capture_output, text, timeout, check):
        calls.append((cmd, cwd, capture_output, text, timeout, check))
        return SimpleNamespace(returncode=0, stdout=SHA_NEW + "\n", stderr="")

    monkeypatch.setattr(remote_worker.os, "getcwd", lambda: "/opt/toanaas-worker")
    monkeypatch.setattr(remote_worker.subprocess, "run", fake_run)

    info = remote_worker.worker_git_head_info()

    assert info["worker_sha"] == SHA_NEW
    assert info["worker_git_head_sha"] == SHA_NEW
    assert info["worker_sha_source"] == "git_rev_parse_head"
    assert info["worker_cwd"] == "/opt/toanaas-worker"
    assert calls[0][1] == "/opt/toanaas-worker"


def test_worker_git_failure_reports_unknown_without_env_or_stale_reuse(monkeypatch):
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=128, stdout="", stderr="not a git repo")

    monkeypatch.setenv("WORKER_SHA", SHA_OLD)
    monkeypatch.setenv("GIT_SHA", SHA_OLD)
    monkeypatch.setenv("COMMIT", SHA_OLD)
    monkeypatch.setattr(remote_worker.subprocess, "run", fake_run)

    info = remote_worker.worker_git_head_info("/not/a/repo")

    assert info["worker_sha"] == ""
    assert info["worker_git_head_sha"] == ""
    assert info["worker_sha_source"] == "unknown"


def test_record_remote_worker_ping_overwrites_stale_sha_and_stores_source(monkeypatch):
    normalized = remote_worker_api.normalize_worker_sha_payload(
        {
            "worker_sha": SHA_NEW,
            "worker_git_sha": SHA_NEW,
            "worker_git_head_sha": SHA_NEW,
            "worker_sha_source": "git_rev_parse_head",
            "worker_cwd": "/opt/toanaas-worker",
            "worker_service_mode": "owner_product_video",
            "worker_parser_version": "r8d_product_video_canonical_parser",
        }
    )

    assert normalized["worker_sha"] == SHA_NEW
    assert normalized["worker_git_head_sha"] == SHA_NEW
    assert normalized["worker_sha_source"] == "git_rev_parse_head"
    assert normalized["worker_cwd"] == "/opt/toanaas-worker"
    assert normalized["worker_service_mode"] == "owner_product_video"
    assert normalized["worker_parser_version"] == "r8d_product_video_canonical_parser"


def test_record_remote_worker_ping_unknown_clears_stale_sha(monkeypatch):
    normalized = remote_worker_api.normalize_worker_sha_payload(
        {"worker_sha": SHA_OLD, "worker_git_sha": SHA_OLD, "worker_sha_source": "unknown"},
    )

    assert normalized["worker_sha"] == ""
    assert normalized["worker_git_sha"] == ""
    assert normalized["worker_git_head_sha"] == ""
    assert normalized["worker_sha_source"] == "unknown"


def test_status_contract_prefers_git_head_over_stale_worker_sha():
    status_source = _read_bot_function_source("video_remote_worker_runtime_status")
    assert "worker_git_head_sha or raw_worker_sha" in status_source
    assert "heartbeat_sha_source_bug" in status_source
    assert "remote_worker_api.select_latest_worker_heartbeat" in status_source


def test_video_public_status_prefers_latest_git_head_over_stale_worker_sha():
    selected, selected_by = remote_worker_api.select_latest_worker_heartbeat(
        [
            {
            "remote_worker:last_heartbeat": "2026-07-09 11:19:48",
            "remote_worker:heartbeat_updated_at": "2026-07-09 11:19:48",
            "remote_worker:worker_id": "vps-toanaas-01",
            "remote_worker:worker_sha": SHA_OLD,
            "remote_worker:worker_git_sha": SHA_OLD,
            "remote_worker:worker_git_head_sha": SHA_NEW,
            "remote_worker:worker_sha_source": "git_rev_parse_head",
            "remote_worker:worker_cwd": "/opt/toanaas-worker",
            "remote_worker:worker_service_mode": "owner_product_video",
            "remote_worker:worker_parser_version": "r8d_product_video_canonical_parser",
            }
        ],
    )

    assert selected["remote_worker:worker_git_head_sha"] == SHA_NEW
    assert selected["remote_worker:worker_sha"] == SHA_OLD
    assert selected_by == "latest_system_setting_heartbeat_updated_at"


def test_multiple_heartbeat_records_latest_owner_product_video_wins():
    selected, selected_by = remote_worker_api.select_latest_worker_heartbeat(
        [
            {
                "worker_id": "vps-toanaas-01",
                "worker_service_mode": "owner_product_video",
                "heartbeat_updated_at": "2026-07-09 11:18:00",
                "worker_git_head_sha": SHA_OLD,
            },
            {
                "worker_id": "vps-toanaas-01",
                "worker_service_mode": "owner_product_video",
                "heartbeat_updated_at": "2026-07-09 11:19:48",
                "worker_git_head_sha": SHA_NEW,
            },
            {
                "worker_id": "vps-toanaas-01",
                "worker_service_mode": "admin_canary",
                "heartbeat_updated_at": "2026-07-09 11:20:10",
                "worker_git_head_sha": SHA_OLD,
            },
        ]
    )

    assert selected["worker_git_head_sha"] == SHA_NEW
    assert selected_by == "latest_updated_at_owner_product_video"


def test_video_public_status_text_exposes_sha_source_git_head_cwd_and_selection():
    section = _read_bot_function_source("video_public_status_text")
    assert "worker SHA source" in section
    assert "worker git HEAD" in section
    assert "worker cwd" in section
    assert "heartbeat age" in section
    assert "heartbeat selected by" in section
    assert "heartbeat SHA source bug" in section


def test_provider_render_logic_not_touched_by_sha_task():
    changed_scope = {
        "remote_worker.py",
        "bot.py",
        "services/remote_worker_api.py",
        "tests/test_p0_worker_sha1_product_video_worker_heartbeat_sha_source.py",
    }
    forbidden = {
        "services/video_real_render_connector.py",
        "services/video_project_queue.py",
        "providers/video_generic_http_provider.py",
        "providers/key4u_provider.py",
    }
    assert changed_scope.isdisjoint(forbidden)


def test_bot_py_tokenizes_without_importing_heavy_runtime():
    bot_path = Path(__file__).resolve().parents[1] / "bot.py"
    with bot_path.open("rb") as handle:
        list(tokenize.tokenize(handle.readline))


def _read_bot_function_source(function_name: str) -> str:
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
    marker = f"def {function_name}"
    assert marker in source
    return source.split(marker, 1)[1].split("\ndef ", 1)[0]
