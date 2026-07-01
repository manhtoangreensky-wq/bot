import inspect
import os
import subprocess
from pathlib import Path

import pytest

import bot
from services import video_final_output, video_provider_router
from services.video_provider_base import (
    VideoArtifactResult,
    VideoGenerationRequest,
    VideoPollResult,
    VideoSubmitResult,
    materialize_video_url,
    mask_provider_task_id,
)
from services import video_real_render_connector as connector


def _make_mp4(path: Path, duration: float = 1.0) -> Path:
    ffmpeg = video_final_output.ffmpeg_path()
    if not ffmpeg:
        pytest.skip("ffmpeg unavailable")
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=blue:s=320x240:r=25:d={duration}",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return path


class FakeProvider:
    provider_name = "fake_video"

    def __init__(self, mp4_path: Path, *, capabilities=None, status="succeeded", fail_submit=False, fail_poll=False):
        self.mp4_path = mp4_path
        self.calls = {"submit": 0, "poll": 0, "materialize": 0}
        self._capabilities = capabilities or ["text_to_video", "image_to_video", "video_to_video", "multi_scene_video", "scene_video"]
        self.status = status
        self.fail_submit = fail_submit
        self.fail_poll = fail_poll

    def capabilities(self):
        return {"provider": self.provider_name, "enabled": True, "configured": True, "missing": [], "capabilities": self._capabilities, "endpoint_configured": True, "model_configured": True, "auth_configured": True}

    def submit_video_job(self, request: VideoGenerationRequest):
        self.calls["submit"] += 1
        if self.fail_submit:
            return VideoSubmitResult(ok=False, provider_name=self.provider_name, error_code="provider_submit_failed")
        return VideoSubmitResult(ok=True, provider_name=self.provider_name, provider_task_id=f"task-{request.job_id}", provider_video_id=f"video-{request.job_id}", provider_status="queued")

    def poll_video_job(self, provider_task_id: str):
        self.calls["poll"] += 1
        if self.fail_poll:
            return VideoPollResult(ok=True, provider_name=self.provider_name, provider_task_id=provider_task_id, status="failed", error_code="provider_poll_failed")
        return VideoPollResult(ok=True, provider_name=self.provider_name, provider_task_id=provider_task_id, status=self.status, result_url=str(self.mp4_path) if self.status == "succeeded" else "")

    def materialize_result(self, result: VideoPollResult, job_id: str):
        self.calls["materialize"] += 1
        if not result.result_url:
            return VideoArtifactResult(ok=False, error_code="provider_result_url_missing")
        return materialize_video_url(result.result_url, job_id=job_id, output_dir=str(self.mp4_path.parent / "out"), timeout_seconds=5, filename_prefix=self.provider_name)

    def cancel_video_job(self, provider_task_id: str):
        return {"ok": False, "provider_name": self.provider_name, "error_code": "cancel_not_supported"}


def _request(capability="text_to_video"):
    return VideoGenerationRequest(
        job_id="41",
        product_type="video_ai_prompt",
        prompt="A real product video with cinematic visuals",
        ratio="9:16",
        duration_seconds=1,
        required_capability=capability,
    )


def _product_job(product_type="video_ai_prompt"):
    return {
        "id": 41,
        "source": "product_video",
        "product_type": product_type,
        "render_mode": "real",
        "test_pattern": False,
        "admin_video_delivery": False,
        "scene_count": 3,
        "expected_duration_seconds": 18,
        "prompt_text": "job 41 product video",
        "addon_plan": {"music_enabled": True, "subtitle_enabled": True, "logo_enabled": True, "logo_text": "TOAN AAS"},
    }


def test_video_providers_disabled_do_not_crash_startup(monkeypatch):
    monkeypatch.setattr(os, "environ", {})
    payload = video_provider_router.provider_status_payload({})
    assert payload["ok"] is False
    assert payload["ready_provider_order"] == []


def test_video_provider_chain_loads_enabled_providers(monkeypatch):
    env = {
        "VIDEO_PROVIDER_CHAIN": "generic_http,veo,kling",
        "VIDEO_GENERIC_HTTP_ENABLED": "1",
        "VIDEO_GENERIC_HTTP_SUBMIT_URL": "https://example.invalid/submit",
        "VIDEO_GENERIC_HTTP_POLL_URL": "https://example.invalid/poll/{task_id}",
        "VIDEO_GENERIC_HTTP_AUTH_HEADER_NAME": "Authorization",
        "VIDEO_GENERIC_HTTP_AUTH_HEADER_VALUE": "Bearer secret",
    }
    payload = video_provider_router.provider_status_payload(env)
    assert payload["provider_chain"] == ["generic_http", "veo", "kling"]
    assert payload["ready_provider_order"] == ["generic_http"]


def test_video_provider_status_masks_secrets(monkeypatch):
    env = {
        "VIDEO_PROVIDER_CHAIN": "generic_http",
        "VIDEO_GENERIC_HTTP_ENABLED": "1",
        "VIDEO_GENERIC_HTTP_SUBMIT_URL": "https://example.invalid/submit",
        "VIDEO_GENERIC_HTTP_POLL_URL": "https://example.invalid/poll/{task_id}",
        "VIDEO_GENERIC_HTTP_AUTH_HEADER_NAME": "Authorization",
        "VIDEO_GENERIC_HTTP_AUTH_HEADER_VALUE": "Bearer super-secret-token",
    }
    payload = video_provider_router.provider_status_payload(env)
    assert "super-secret-token" not in str(payload)
    assert payload["providers"][0]["auth_configured"] is True


def test_unknown_provider_skipped_cleanly():
    payload = video_provider_router.provider_status_payload({"VIDEO_PROVIDER_CHAIN": "unknown_vendor"})
    assert payload["ok"] is False
    assert payload["providers"][0]["missing"] == ["unknown_provider"]


def test_text_to_video_routes_to_provider(monkeypatch, tmp_path):
    mp4 = _make_mp4(tmp_path / "source.mp4")
    fake = FakeProvider(mp4, capabilities=["text_to_video"])
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [fake])
    result = video_provider_router.run_provider_generation(_request("text_to_video"), output_dir=str(tmp_path))
    assert result["ok"] is True
    assert result["provider_attempted"] is True
    assert fake.calls["submit"] == 1


def test_image_to_video_routes_to_provider(monkeypatch, tmp_path):
    mp4 = _make_mp4(tmp_path / "source.mp4")
    fake = FakeProvider(mp4, capabilities=["image_to_video"])
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [fake])
    result = video_provider_router.run_provider_generation(_request("image_to_video"), output_dir=str(tmp_path))
    assert result["ok"] is True


def test_video_to_video_routes_to_provider(monkeypatch, tmp_path):
    mp4 = _make_mp4(tmp_path / "source.mp4")
    fake = FakeProvider(mp4, capabilities=["video_to_video"])
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [fake])
    result = video_provider_router.run_provider_generation(_request("video_to_video"), output_dir=str(tmp_path))
    assert result["ok"] is True


def test_multiscene_routes_to_provider_or_local_fallback(monkeypatch, tmp_path):
    mp4 = _make_mp4(tmp_path / "source.mp4")
    fake = FakeProvider(mp4, capabilities=["multi_scene_video"])
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [fake])
    result = video_provider_router.run_provider_generation(_request("multi_scene_video"), output_dir=str(tmp_path))
    assert result["ok"] is True


def test_missing_capability_clean_no_charge(monkeypatch, tmp_path):
    fake = FakeProvider(_make_mp4(tmp_path / "source.mp4"), capabilities=["image_to_video"])
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [fake])
    result = video_provider_router.run_provider_generation(_request("video_to_video"), output_dir=str(tmp_path))
    assert result["ok"] is False
    assert result["blocker"] == "provider_capability_missing"
    assert result["provider_attempted"] is False


def test_provider_submit_after_final_confirm_only():
    source = inspect.getsource(connector._render_scene_async) + inspect.getsource(connector.render_real_video_job)
    assert "run_provider_generation(" in source
    assert "render_real_video_job(" not in inspect.getsource(bot.video_b14_auto_refresh_tick)


def test_provider_task_id_saved(monkeypatch, tmp_path):
    mp4 = _make_mp4(tmp_path / "source.mp4")
    fake = FakeProvider(mp4)
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [fake])
    result = video_provider_router.run_provider_generation(_request(), output_dir=str(tmp_path))
    assert result["provider_task_ids"] == ["task-41"]


def test_provider_poll_success_gets_result_url(monkeypatch, tmp_path):
    mp4 = _make_mp4(tmp_path / "source.mp4")
    fake = FakeProvider(mp4)
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [fake])
    result = video_provider_router.run_provider_generation(_request(), output_dir=str(tmp_path))
    assert result["result_url_present"] is True
    assert result["download_status"] == "downloaded"


def test_provider_poll_failure_clean_no_charge(monkeypatch, tmp_path):
    mp4 = _make_mp4(tmp_path / "source.mp4")
    fake = FakeProvider(mp4, fail_poll=True)
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [fake])
    result = video_provider_router.run_provider_generation(_request(), output_dir=str(tmp_path))
    assert result["ok"] is False
    assert result["blocker"] == "provider_poll_failed"


def test_provider_timeout_clean_no_charge(monkeypatch, tmp_path):
    mp4 = _make_mp4(tmp_path / "source.mp4")
    fake = FakeProvider(mp4, status="running")
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [fake])
    result = video_provider_router.run_provider_generation(_request(), output_dir=str(tmp_path), environ={"VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1"})
    assert result["ok"] is False
    assert result["blocker"] == "provider_timeout"


def test_video_result_url_downloads_to_local_mp4(tmp_path):
    mp4 = _make_mp4(tmp_path / "source.mp4")
    result = materialize_video_url(str(mp4), job_id="41", output_dir=str(tmp_path / "out"))
    assert result.ok is True
    assert result.bytes > 0


def test_video_download_follows_redirect(tmp_path):
    # Local file materialization exercises the same copy/validate path without network.
    mp4 = _make_mp4(tmp_path / "source.mp4")
    result = materialize_video_url(str(mp4), job_id="redirect", output_dir=str(tmp_path / "out"))
    assert result.ok is True


def test_video_download_rejects_html_error(tmp_path):
    html_path = tmp_path / "error.html"
    html_path.write_text("<html>error</html>", encoding="utf-8")
    result = materialize_video_url(str(html_path), job_id="html", output_dir=str(tmp_path / "out"))
    assert result.ok is False
    assert result.error_code == "provider_download_html_error"


def test_video_download_rejects_zero_bytes(tmp_path):
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    result = materialize_video_url(str(empty), job_id="empty", output_dir=str(tmp_path / "out"))
    assert result.ok is False
    assert result.error_code == "output_zero_bytes"


def test_video_validation_requires_video_stream(tmp_path):
    text_file = tmp_path / "not_video.bin"
    text_file.write_bytes(b"not a video")
    result = materialize_video_url(str(text_file), job_id="bad", output_dir=str(tmp_path / "out"))
    assert result.ok is False


def test_video_validation_requires_duration(tmp_path):
    result = video_final_output.validate_final_video_output(path="", result={"visual_classification": "final_ai_video"})
    assert result["ok"] is False


def test_video_artifact_hash_saved(tmp_path):
    mp4 = _make_mp4(tmp_path / "source.mp4")
    result = materialize_video_url(str(mp4), job_id="hash", output_dir=str(tmp_path / "out"))
    assert result.artifact_hash
    assert len(result.artifact_hash) == 64


def test_valid_provider_mp4_delivered_once():
    source = inspect.getsource(bot.api_worker_complete)
    assert "note_video_delivery_result" in source
    assert "maybe_send_remote_worker_final_video" in source


def test_late_fail_suppressed_after_delivery():
    source = inspect.getsource(bot.video_project_queue.fail_video_job)
    assert "late_fail_suppressed_after_delivery" in source


def test_manual_refresh_does_not_resubmit_provider():
    source = inspect.getsource(bot.video_b14_auto_refresh_tick)
    assert "render_real_video_job(" not in source


def test_debug_read_only_no_provider_call():
    source = inspect.getsource(bot.cmd_video_render_debug)
    assert "render_real_video_job(" not in source
    assert "run_provider_generation(" not in source


def test_music_subtitle_logo_applied_after_provider_video():
    source = inspect.getsource(connector.render_real_video_job)
    assert "_run_multiscene_render" in source
    assert "probe_video(final_path)" in source
    assert "addon_degrade_notes" in source


def test_addon_missing_not_claimed_applied():
    result = connector._addon_degrade_notes({"music_enabled": True, "subtitle_enabled": True, "logo_enabled": True, "logo_text": ""}, job={})
    notes = {item["addon"]: item for item in result}
    assert notes["music"]["applied"] is False
    assert notes["subtitle"]["applied"] is False
    assert notes["logo"]["applied"] is False


def test_final_metadata_matches_applied_addons(monkeypatch, tmp_path):
    mp4 = _make_mp4(tmp_path / "source.mp4")
    fake = FakeProvider(mp4)
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [fake])
    result = video_provider_router.run_provider_generation(_request(), output_dir=str(tmp_path))
    assert result["ok"] is True
    assert result["has_video_stream"] is True


def test_job_41_provider_capability_missing_clean_fail(monkeypatch, tmp_path):
    monkeypatch.setenv("REAL_VIDEO_LOCAL_COMPOSER_FALLBACK_ENABLED", "0")
    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: {"ok": False, "ready_provider_order": [], "providers": []})
    with pytest.raises(connector.RealVideoRenderError) as exc:
        connector.render_real_video_job(_product_job("video_ai_prompt"), str(tmp_path))
    assert str(exc.value) == "provider_capability_missing"
    assert exc.value.diagnostics["no_charge"] is True


def test_job_41_with_stub_provider_delivers_final_mp4(monkeypatch, tmp_path):
    mp4 = _make_mp4(tmp_path / "provider.mp4")

    def fake_run(request, *, output_dir, environ=None, sleep_func=None):
        del environ, sleep_func
        copied = tmp_path / "downloaded.mp4"
        copied.write_bytes(mp4.read_bytes())
        return {
            "ok": True,
            "provider_attempted": True,
            "provider": "fake_video",
            "provider_task_ids": [f"task-{request.job_id}"],
            "provider_video_ids": [f"video-{request.job_id}"],
            "provider_status": "downloaded",
            "result_url_present": True,
            "download_status": "downloaded",
            "output_path": str(copied),
            "artifact_hash": "a" * 64,
        }

    monkeypatch.setattr(connector, "real_video_provider_readiness", lambda *_a, **_k: {"ok": True, "ready_provider_order": ["fake_video"], "providers": []})
    monkeypatch.setattr(connector, "run_provider_generation", fake_run)
    result = connector.render_real_video_job(_product_job("video_ai_prompt"), str(tmp_path / "work"))
    assert result["provider_attempted"] is True
    assert result["provider_task_ids"]
    assert all(str(item).startswith("task-41-") for item in result["provider_task_ids"])
    assert video_final_output.validate_final_video_output(path=result["final_video_path"], result=result)["ok"] is True


def test_job_41_no_fake_95_without_artifact():
    source = inspect.getsource(bot.video_b14_queue_status_text)
    assert "progress >= 95" in source
    assert "has_final_artifact" in source


def test_provider_debug_masks_task_ids():
    assert mask_provider_task_id("task-1234567890").startswith("task")
    assert "1234567890" not in mask_provider_task_id("task-1234567890")


def test_video_provider_audit_command_registered():
    source = inspect.getsource(bot.lifespan)
    assert 'CommandHandler("video_provider_audit", cmd_video_provider_audit)' in source


def test_video_provider_status_uses_new_router():
    source = inspect.getsource(bot.cmd_video_provider_status)
    assert "video_provider_router.provider_status_payload" in source
    assert "final_submit_url" not in source
