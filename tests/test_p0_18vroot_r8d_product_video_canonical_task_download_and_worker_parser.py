import json
import os

import pytest

import bot
import remote_worker
from services import video_final_output
from services.video_provider_base import VideoArtifactResult, VideoPollResult, materialize_video_url


class _CanonicalProvider:
    provider_name = "shopaikey_video"

    def __init__(self):
        self.poll_calls = []

    def poll_video_job(self, task_id):
        self.poll_calls.append(task_id)
        if task_id == "task-success":
            return VideoPollResult(
                ok=True,
                status="succeeded",
                provider_name=self.provider_name,
                provider_task_id=task_id,
                raw_status="SUCCESS",
                progress_percent=100,
                result_url="https://cdn.example/video/final.mp4?token=secret",
                file_url="https://cdn.example/video/final.mp4?token=secret",
                raw={
                    "poll_http_status": 200,
                    "shopaikey_status_endpoint_exact": True,
                    "shopaikey_status_http_code": 200,
                    "shopaikey_raw_status": "SUCCESS",
                    "shopaikey_normalized_status": "succeeded",
                    "shopaikey_data_progress_raw": "100%",
                    "shopaikey_progress_source": "data.progress",
                    "shopaikey_result_url_from_data": True,
                    "shopaikey_data_result_url_present": True,
                    "result_url_source_path": "data.result_url",
                    "result_url_primary_path_checked": True,
                    "provider_progress_raw": "100%",
                    "provider_progress_raw_number": 100,
                    "provider_progress_source": "data.progress",
                    "http_200_not_used_as_progress": True,
                },
            )
        return VideoPollResult(
            ok=True,
            status="running",
            provider_name=self.provider_name,
            provider_task_id=task_id,
            raw_status="IN_PROGRESS",
            raw={
                "poll_http_status": 200,
                "shopaikey_status_endpoint_exact": True,
                "shopaikey_status_http_code": 200,
                "shopaikey_raw_status": "IN_PROGRESS",
                "shopaikey_normalized_status": "running",
                "provider_progress_source": "none",
                "http_200_not_used_as_progress": True,
            },
        )


class _DownloadProvider(_CanonicalProvider):
    def materialize_result(self, poll_result, job_id):
        return VideoArtifactResult(
            ok=True,
            local_path="/tmp/recovered.mp4",
            bytes=2048,
            duration=6.0,
            has_video_stream=True,
            artifact_hash="abc",
            content_type="video/mp4",
            diagnostics={
                "download_http_status": 200,
                "result_url_host": "cdn.example",
                "result_url_scheme": "https",
                "result_url_ext": ".mp4",
                "result_url_query_present": True,
                "download_redirect_count": 1,
                "download_content_type": "video/mp4",
                "download_content_length": 2048,
                "download_bytes": 2048,
                "mp4_validator_result": "valid_mp4",
                "first_bytes_hex_safe": "0000001866747970",
            },
        )


def _job(result):
    return {
        "id": 82,
        "project_id": 820,
        "status": "processing",
        "progress_percent": 20,
        "result_json": json.dumps(result),
        "updated_at": "2026-07-06 10:00:00",
    }


def _project():
    return {
        "project_id": 820,
        "asset_pack_json": "{}",
        "story_bible_json": "{}",
        "addon_plan_json": "{}",
        "invoice_json": "{}",
    }


def _two_task_result():
    return {
        "selected_provider": "shopaikey_video",
        "provider_pending_provider": "shopaikey_video",
        "provider_pending_task_id": "task-pending",
        "provider_task_ids": ["task-pending", "task-success"],
        "provider_progress_raw": 200,
        "provider_progress_raw_number": 200,
        "provider_attempts": [
            {
                "provider": "shopaikey_video",
                "task_id": "task-pending",
                "poll_called": True,
                "poll_http_status": 200,
                "poll_raw_status": "IN_PROGRESS",
                "normalized_status": "running",
                "continue_polling": True,
            },
            {
                "provider": "shopaikey_video",
                "task_id": "task-success",
                "poll_called": True,
                "poll_http_status": 200,
                "poll_raw_status": "SUCCESS",
                "normalized_status": "succeeded",
                "result_url": "https://cdn.example/video/final.mp4?token=secret",
            },
        ],
    }


def test_canonical_resolver_prefers_success_result_url_over_in_progress(monkeypatch):
    provider = _CanonicalProvider()
    monkeypatch.setattr(bot, "_video_provider_recover_adapter", lambda name: provider)

    canonical = bot.resolve_canonical_video_provider_task(
        82,
        job=_job(_two_task_result()),
        project=_project(),
        result=_two_task_result(),
        poll_candidates=True,
    )

    assert canonical["canonical_provider"] == "shopaikey_video"
    assert canonical["canonical_task_id"] == "task-success"
    assert canonical["selected_reason"] == "success_result_url_wins"
    assert canonical["canonical_status"] == "succeeded"
    assert canonical["canonical_result_url"].startswith("https://cdn.example/video/final.mp4")
    assert canonical["task_count"] == 2
    assert provider.poll_calls == ["task-pending", "task-success"]


def test_reconciled_debug_uses_canonical_parser_and_removes_http_200_progress(monkeypatch):
    monkeypatch.setattr(bot, "_video_provider_recover_adapter", lambda name: _CanonicalProvider())

    debug = bot.video_b14_reconciled_provider_debug(
        _job(_two_task_result()),
        _project(),
        _two_task_result(),
        refresh_source="video_render_debug",
    )

    assert debug["canonical_task_selected_reason"] == "success_result_url_wins"
    assert debug["canonical_status"] == "succeeded"
    assert debug["provider_progress_raw"] == "100%"
    assert debug["provider_progress_raw_number"] == 100
    assert debug["http_200_not_used_as_progress"] is True
    assert debug["shopaikey_status_endpoint_exact"] is True
    assert debug["result_url_source_path"] == "data.result_url"


def test_progress_debug_recovery_uses_same_canonical_reconciler(monkeypatch):
    monkeypatch.setattr(bot, "_video_provider_recover_adapter", lambda name: _CanonicalProvider())

    class _Conn:
        def close(self):
            return None

    monkeypatch.setattr(bot, "db_connect", lambda: _Conn())
    monkeypatch.setattr(bot.video_project_queue, "get_video_render_job", lambda _conn, _jid: _job(_two_task_result()))
    monkeypatch.setattr(bot.video_project_queue, "get_video_project", lambda _conn, _pid: _project())

    recovered, product_type = bot._video_progress_debug_recover_job_from_db("82")

    assert product_type
    assert recovered["canonical_task_selected_reason"] == "success_result_url_wins"
    assert recovered["provider_progress_raw"] == "100%"
    assert recovered["shopaikey_status_endpoint_exact"] is True


def test_recovery_download_uses_canonical_success_task_once(monkeypatch):
    provider = _DownloadProvider()
    updates = []

    class _Conn:
        def close(self):
            return None

    monkeypatch.setattr(bot, "db_connect", lambda: _Conn())
    monkeypatch.setattr(bot.video_project_queue, "get_video_render_job", lambda _conn, _jid: _job(_two_task_result()))
    monkeypatch.setattr(bot.video_project_queue, "get_video_project", lambda _conn, _pid: _project())
    monkeypatch.setattr(bot, "_video_provider_recover_adapter", lambda name: provider)
    monkeypatch.setattr(bot, "_video_provider_update_job_result", lambda _conn, jid, patch: updates.append((jid, patch)))

    result = bot.video_provider_recover_existing_task(82, download=True)

    assert result["ok"] is True
    assert result["provider"] == "shopaikey_video"
    assert result["task_id_masked"] != "task-success"
    assert result["debug"]["canonical_task_selected_reason"] == "success_result_url_wins"
    assert result["debug"]["download_http_status"] == 200
    assert result["debug"]["result_url_query_present"] is True
    assert result["debug"]["mp4_validator_result"] == "valid_mp4"
    assert result["charge"] == 0
    assert provider.poll_calls == ["task-pending", "task-success"]
    assert updates[-1][1]["no_new_paid_submit"] is True
    assert updates[-1][1]["paid_fallback_not_used"] is True


def test_materialize_video_url_records_safe_download_diagnostics(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"0" * 2048)
    monkeypatch.setenv("VIDEO_PROVIDER_MIN_VIDEO_BYTES", "1")
    monkeypatch.setattr(video_final_output, "probe_video", lambda _path: {"ok": True, "duration": 6.0, "has_video": True, "has_audio": False})

    artifact = materialize_video_url(str(source), output_dir=str(tmp_path / "out"), job_id="job-82")

    assert artifact.ok is True
    assert artifact.diagnostics["download_http_status"] == 200
    assert artifact.diagnostics["download_final_url_host"] == "local_file"
    assert artifact.diagnostics["mp4_validator_result"] == "valid_mp4"
    assert artifact.diagnostics["first_bytes_hex_safe"].startswith("00000018")


def test_worker_trace_exposes_parser_version_and_git_sha(monkeypatch):
    monkeypatch.setenv("GIT_COMMIT_SHA", "abc123456789")
    remote = remote_worker.worker_process_trace({}, service_mode="owner_product_video", claim_status="claimed")

    assert remote["worker_parser_version"] == "r8d_product_video_canonical_parser"
    assert remote["worker_git_sha"].startswith("abc123")
    assert remote["worker_started_at"]


def test_scope_does_not_touch_locked_modules():
    touched = os.popen("git diff --name-only origin/main").read().splitlines()
    forbidden_prefixes = (
        "providers/key4u_provider.py",
        "services/subtitle_dub",
        "services/music",
        "services/payos",
        "services/wallet",
        "services/finance",
    )

    assert not [path for path in touched if path.startswith(forbidden_prefixes)]
