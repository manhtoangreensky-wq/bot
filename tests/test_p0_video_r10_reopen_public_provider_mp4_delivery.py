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
QUEUE_SOURCE = (ROOT / "services" / "video_project_queue.py").read_text(encoding="utf-8")


class _FixtureProvider:
    provider_name = "shopaikey_video"

    def __init__(self, *, result_url="fixture://video.mp4", fail_download=False):
        self.submit_calls = 0
        self.poll_calls = 0
        self.materialize_calls = 0
        self.result_url = result_url
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
            provider_task_id="r10-task",
            provider_status="submitted",
            raw={"http_status": 200},
        )

    def poll_video_job(self, provider_task_id):
        self.poll_calls += 1
        return VideoPollResult(
            ok=True,
            status="completed",
            provider_name=self.provider_name,
            provider_task_id=provider_task_id,
            result_url=self.result_url,
            raw={"poll_http_status": 200, "provider_status_raw": "SUCCESS"},
        )

    def materialize_result(self, result, job_id):
        self.materialize_calls += 1
        if self.fail_download:
            return VideoArtifactResult(ok=False, error_code="provider_download_failed", error_message="fixture failure")
        return VideoArtifactResult(
            ok=True,
            local_path=f"/tmp/{job_id}.mp4",
            bytes=4096,
            duration=8.0,
            has_video_stream=True,
            has_audio_stream=False,
            artifact_hash="r10-fixture-hash",
            content_type="video/mp4",
        )


def _request():
    return VideoGenerationRequest(
        job_id="r10-job",
        product_type="video_trend",
        video_flow_type="video_trend",
        prompt="A real product video",
        ratio="9:16",
        duration_seconds=8,
        required_capability="text_to_video_or_scene_video",
        metadata={
            "product_video": True,
            "interactive_product": True,
            "wallet_charge": False,
        },
    )


def _env(**updates):
    data = {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
        "SHOPAIKEY_PUBLIC_VIDEO_ENABLED": "true",
    }
    data.update({key: str(value) for key, value in updates.items()})
    return data


def _run(monkeypatch, tmp_path, provider, **env_updates):
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [provider])
    return video_provider_router.run_provider_generation(
        _request(),
        output_dir=str(tmp_path),
        environ=_env(**env_updates),
        sleep_func=lambda _seconds: None,
    )


def _confirm_block():
    return BOT_SOURCE.split('if action == "b14_confirm":', 1)[1].split('if action == "b14_job_status":', 1)[0]


def test_wizard_to_invoice_and_confirm_are_not_locked_by_submit_switch():
    block = _confirm_block()
    assert "PRODUCT_VIDEO_R9E_PROVIDER_LOCK_COPY_VI" not in block
    assert "b14_provider_submit_locked" not in block
    assert "product_video_submit_switch_detail()" not in block
    assert "confirm_video_project_invoice(" in block


def test_public_provider_flag_reopens_product_video_submit_when_old_lock_is_false():
    detail = video_provider_router.product_video_submit_switch_detail(
        {
            "PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED": "false",
            "SHOPAIKEY_PUBLIC_VIDEO_ENABLED": "true",
        }
    )
    assert detail["resolved"] is True
    assert detail["override_flag"] == "SHOPAIKEY_PUBLIC_VIDEO_ENABLED"


def test_result_url_fixture_download_validate_contract_delivers_mp4(monkeypatch, tmp_path):
    provider = _FixtureProvider()
    result = _run(monkeypatch, tmp_path, provider)

    assert provider.submit_calls == 1
    assert provider.poll_calls == 1
    assert provider.materialize_calls == 1
    assert result["ok"] is True
    assert result["provider_submit_called"] is True
    assert result["provider_result_url_present"] is True
    assert result["download_status"] == "downloaded"
    assert result["bytes"] > 0
    assert result["has_video_stream"] is True


def test_no_result_url_fails_clean_no_charge(monkeypatch, tmp_path):
    provider = _FixtureProvider(result_url="")
    result = _run(monkeypatch, tmp_path, provider)

    assert provider.submit_calls == 1
    assert provider.poll_calls == 1
    assert provider.materialize_calls == 0
    assert result["ok"] is False
    assert result["blocker"] in {"provider_result_url_missing", "provider_timeout", "provider_in_progress"}
    assert result["provider_result_url_present"] is False
    assert result["no_charge"] is True
    assert result["charge"] == 0
    assert result["charged_xu"] == 0


def test_provider_download_fail_no_charge(monkeypatch, tmp_path):
    provider = _FixtureProvider(fail_download=True)
    result = _run(monkeypatch, tmp_path, provider)

    assert provider.submit_calls == 1
    assert provider.poll_calls == 1
    assert provider.materialize_calls == 1
    assert result["ok"] is False
    assert result["provider_result_url_present"] is True
    assert result["no_charge"] is True
    assert result["charge"] == 0
    assert result["charged_xu"] == 0


def test_no_wallet_charge_before_valid_mp4_delivery_contract():
    block = _confirm_block()
    assert "use_wallet=False" in block
    assert '"xu_charged": 0' in block
    assert '"charge_policy": "after_valid_mp4_delivery"' in block
    assert "validate_final_video_output" in QUEUE_SOURCE
    assert "note_video_delivery_result" in BOT_SOURCE
    assert "video_delivered_at" in QUEUE_SOURCE
