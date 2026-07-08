from pathlib import Path

from services import video_provider_router
from services.video_provider_base import (
    VideoArtifactResult,
    VideoGenerationRequest,
    VideoPollResult,
    VideoSubmitResult,
)


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
CONNECTOR_SOURCE = (ROOT / "services" / "video_real_render_connector.py").read_text(encoding="utf-8")
REMOTE_WORKER_SOURCE = (ROOT / "remote_worker.py").read_text(encoding="utf-8")


class _FixtureProvider:
    provider_name = "shopaikey_video"

    def __init__(self, *, result_url="fixture://video.mp4", status="completed", fail_download=False):
        self.submit_calls = 0
        self.poll_calls = 0
        self.materialize_calls = 0
        self.result_url = result_url
        self.status = status
        self.fail_download = fail_download

    def capabilities(self):
        return {
            "provider": self.provider_name,
            "enabled": True,
            "configured": True,
            "missing": [],
            "capabilities": ["text_to_video", "scene_video", "multi_scene_video"],
            "submit_url_configured": True,
            "poll_url_configured": True,
            "auth_configured": True,
            "model_configured": True,
            "credit_ok": True,
        }

    def submit_video_job(self, request):
        self.submit_calls += 1
        return VideoSubmitResult(
            ok=True,
            provider_name=self.provider_name,
            provider_task_id="r10b-task",
            provider_status="submitted",
            raw={"http_status": 200},
        )

    def poll_video_job(self, provider_task_id):
        self.poll_calls += 1
        return VideoPollResult(
            ok=True,
            status=self.status,
            provider_name=self.provider_name,
            provider_task_id=provider_task_id,
            result_url=self.result_url,
            raw={"poll_http_status": 200, "provider_status_raw": self.status.upper()},
        )

    def materialize_result(self, result, job_id):
        self.materialize_calls += 1
        if self.fail_download:
            return VideoArtifactResult(ok=False, error_code="provider_download_failed")
        return VideoArtifactResult(
            ok=True,
            local_path=f"/tmp/{job_id}.mp4",
            bytes=4096,
            duration=8.0,
            has_video_stream=True,
            has_audio_stream=False,
            artifact_hash="r10b-fixture",
            content_type="video/mp4",
        )


def _request(**metadata):
    base_metadata = {
        "product_video": True,
        "interactive_product": True,
        "wallet_charge": False,
        "charge_policy": "after_valid_mp4_delivery",
    }
    base_metadata.update(metadata)
    return VideoGenerationRequest(
        job_id="r10b-job",
        product_type="video_trend",
        video_flow_type="video_trend",
        prompt="A public live product video",
        ratio="9:16",
        duration_seconds=8,
        required_capability="text_to_video_or_scene_video",
        metadata=base_metadata,
    )


def _env(**updates):
    data = {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
        "PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED": "1",
        "SHOPAIKEY_PUBLIC_VIDEO_ENABLED": "true",
    }
    data.update({key: str(value) for key, value in updates.items()})
    return data


def _run(monkeypatch, tmp_path, provider, request, **env_updates):
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [provider])
    return video_provider_router.run_provider_generation(
        request,
        output_dir=str(tmp_path),
        environ=_env(**env_updates),
        sleep_func=lambda _seconds: None,
    )


def test_public_user_final_confirm_with_public_flag_allows_provider_submit(monkeypatch, tmp_path):
    provider = _FixtureProvider()
    result = _run(
        monkeypatch,
        tmp_path,
        provider,
        _request(submit_source="public_user_final_confirm", public_user_confirmed=True),
    )

    assert provider.submit_calls == 1
    assert provider.poll_calls == 1
    assert result["ok"] is True
    assert result["submit_source"] == "public_user_final_confirm"
    assert result["public_user_confirmed"] is True
    assert result["provider_submit_allowed"] is True
    assert result["provider_submit_block_reason"] == ""
    assert result["provider_result_url_present"] is True
    assert result["bytes"] > 0


def test_hidden_submit_sources_are_blocked_before_provider_submit(monkeypatch, tmp_path):
    for source in ("codex_test", "smoke", "debug", "recover", "status", "background_retry", "fallback"):
        provider = _FixtureProvider()
        result = _run(monkeypatch, tmp_path, provider, _request(submit_source=source))

        assert provider.submit_calls == 0
        assert provider.poll_calls == 0
        assert result["ok"] is False
        assert result["provider_submit_called"] is False
        assert result["provider_submit_allowed"] is False
        assert result["provider_submit_block_reason"] == "hidden_submit_source_blocked"
        assert result["blocker"] == "hidden_submit_source_blocked"
        assert result["charge"] == 0
        assert result["charged_xu"] == 0
        assert result["no_charge"] is True


def test_worker_poll_existing_task_reads_only_and_does_not_submit_new_task(monkeypatch, tmp_path):
    provider = _FixtureProvider()
    result = _run(
        monkeypatch,
        tmp_path,
        provider,
        _request(
            submit_source="worker_poll_existing_task",
            provider_pending_provider="shopaikey_video",
            provider_pending_task_id="existing-r10b-task",
            provider_pending_request_job_id="",
        ),
    )

    assert provider.submit_calls == 0
    assert provider.poll_calls == 1
    assert result["ok"] is True
    assert result["submit_source"] == "worker_poll_existing_task"
    assert result["provider_submit_allowed"] is False
    assert result["provider_submit_block_reason"] == "worker_poll_existing_task_read_only"
    assert result["poll_existing_task_allowed"] is True
    assert result["provider_result_url_present"] is True


def test_public_confirm_source_is_written_to_product_video_project_payload():
    assert '"submit_source": str(draft.get("submit_source")' in BOT_SOURCE
    assert '"provider_submit_source": str(draft.get("provider_submit_source")' in BOT_SOURCE
    assert '"public_user_confirmed": bool(draft.get("public_user_confirmed")' in BOT_SOURCE
    assert '"charge_policy": "after_valid_mp4_delivery"' in BOT_SOURCE
    confirm_block = BOT_SOURCE.split('if action == "b14_confirm":', 1)[1].split('if action == "b14_job_status":', 1)[0]
    assert '"submit_source": "public_user_final_confirm"' in confirm_block
    assert '"public_user_confirmed": True' in confirm_block
    assert "video_b14_prepare_project_for_invoice(uid, session)" in confirm_block


def test_connector_passes_submit_source_to_provider_router_and_poll_existing_source():
    assert '"submit_source": submit_source' in CONNECTOR_SOURCE
    assert '"provider_submit_source": submit_source' in CONNECTOR_SOURCE
    assert '"public_user_confirmed": public_user_confirmed' in CONNECTOR_SOURCE
    assert "PRODUCT_VIDEO_SUBMIT_SOURCE_WORKER_POLL_EXISTING_TASK" in CONNECTOR_SOURCE
    assert "PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM" in CONNECTOR_SOURCE


def test_video_provider_job_debug_exposes_r10b_source_delivery_and_charge_fields():
    debug_source = BOT_SOURCE.split("def video_provider_job_debug_text", 1)[1].split("async def cmd_video_render_debug", 1)[0]
    for expected in (
        "submit source",
        "public user confirmed",
        "provider submit allowed",
        "provider submit block reason",
        "result url present",
        "artifact path",
        "artifact size",
        "delivered",
        "charge policy",
        "worker sync hint",
    ):
        assert expected in debug_source


def test_remote_worker_persists_r10b_debug_fields_from_connector_result():
    for expected in (
        '"submit_source"',
        '"provider_submit_source"',
        '"public_user_confirmed"',
        '"provider_submit_allowed"',
        '"provider_submit_block_reason"',
        '"charge_policy"',
    ):
        assert expected in REMOTE_WORKER_SOURCE


def test_no_result_url_and_invalid_mp4_remain_no_charge(monkeypatch, tmp_path):
    no_url_provider = _FixtureProvider(result_url="")
    no_url = _run(
        monkeypatch,
        tmp_path,
        no_url_provider,
        _request(submit_source="public_user_final_confirm", public_user_confirmed=True),
    )
    assert no_url_provider.submit_calls == 1
    assert no_url["ok"] is False
    assert no_url["no_charge"] is True
    assert no_url["charge"] == 0
    assert no_url["charged_xu"] == 0

    invalid_provider = _FixtureProvider(fail_download=True)
    invalid = _run(
        monkeypatch,
        tmp_path,
        invalid_provider,
        _request(submit_source="public_user_final_confirm", public_user_confirmed=True),
    )
    assert invalid_provider.submit_calls == 1
    assert invalid["ok"] is False
    assert invalid["no_charge"] is True
    assert invalid["charge"] == 0
    assert invalid["charged_xu"] == 0
