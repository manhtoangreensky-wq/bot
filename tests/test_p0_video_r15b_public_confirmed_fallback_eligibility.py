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
ROUTER_SOURCE = (ROOT / "services" / "video_provider_router.py").read_text(encoding="utf-8")


class _PrimaryFailedProvider:
    provider_name = "shopaikey_video"

    def __init__(self, *, result_url="", error_code="provider_poll_failed"):
        self.submit_calls = 0
        self.poll_calls = 0
        self.materialize_calls = 0
        self.result_url = result_url
        self.error_code = error_code

    def capabilities(self):
        return {
            "provider": self.provider_name,
            "enabled": True,
            "configured": True,
            "public_enabled": True,
            "credit_ok": True,
            "capabilities": ["text_to_video", "scene_video", "multi_scene_video"],
            "submit_url_configured": True,
            "poll_url_configured": True,
            "auth_configured": True,
            "model_configured": True,
            "provider_payload_model": "veo3.1-fast",
        }

    def submit_video_job(self, request):
        self.submit_calls += 1
        raise AssertionError("existing primary provider task must be polled, not resubmitted")

    def poll_video_job(self, provider_task_id: str):
        self.poll_calls += 1
        return VideoPollResult(
            ok=False,
            status="failed",
            provider_name=self.provider_name,
            provider_task_id=provider_task_id,
            result_url=self.result_url,
            error_code=self.error_code,
            raw_status="FAILURE",
            raw={
                "poll_http_status": 200,
                "provider_status_raw": "FAILURE",
                "result_url_present": bool(self.result_url),
            },
        )

    def materialize_result(self, result, job_id):
        self.materialize_calls += 1
        return VideoArtifactResult(ok=False, error_code="primary_should_not_download")


class _FallbackSuccessProvider:
    provider_name = "key4u_video"

    def __init__(self):
        self.submit_calls = 0
        self.poll_calls = 0
        self.materialize_calls = 0
        self.request_sources = []

    def capabilities(self):
        return {
            "provider": self.provider_name,
            "enabled": True,
            "configured": True,
            "public_enabled": True,
            "credit_ok": True,
            "capabilities": ["text_to_video", "scene_video", "multi_scene_video"],
            "submit_url_configured": True,
            "poll_url_configured": True,
            "auth_configured": True,
            "model_configured": True,
            "provider_payload_model": "veo3.1-fast",
        }

    def submit_video_job(self, request):
        self.submit_calls += 1
        self.request_sources.append(request.metadata.get("submit_source"))
        return VideoSubmitResult(
            ok=True,
            provider_name=self.provider_name,
            provider_task_id="fallback-task-96",
            provider_status="submitted",
            raw={"submit_http_status": 200, "task_id_field_path": "data.id"},
        )

    def poll_video_job(self, provider_task_id: str):
        self.poll_calls += 1
        return VideoPollResult(
            ok=True,
            status="succeeded",
            provider_name=self.provider_name,
            provider_task_id=provider_task_id,
            result_url="https://provider.example/fallback.mp4",
            raw_status="SUCCESS",
            raw={"poll_http_status": 200, "provider_status_raw": "SUCCESS", "result_url_present": True},
        )

    def materialize_result(self, result, job_id):
        self.materialize_calls += 1
        return VideoArtifactResult(
            ok=True,
            local_path=f"/tmp/{job_id}.mp4",
            bytes=8192,
            duration=8.0,
            has_video_stream=True,
            artifact_hash="r15b-fallback",
            content_type="video/mp4",
        )


class _FallbackFailProvider(_FallbackSuccessProvider):
    def materialize_result(self, result, job_id):
        self.materialize_calls += 1
        return VideoArtifactResult(ok=False, error_code="provider_download_failed")


def _request(**metadata):
    base_metadata = {
        "product_video": True,
        "interactive_product": True,
        "allow_provider_pending": True,
        "charge_policy": "after_valid_mp4_delivery",
        "submit_source": "worker_poll_existing_task",
        "provider_submit_source": "worker_poll_existing_task",
        "original_submit_source": "public_user_final_confirm",
        "public_confirm_submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "provider_pending_provider": "shopaikey_video",
        "provider_pending_task_id": "primary-task-96",
        "provider_pending_request_job_id": "r15b-job",
        "provider_submit_accepted_before": True,
        "fallback_count": 0,
        "charged_xu": 0,
        "delivered": False,
    }
    base_metadata.update(metadata)
    return VideoGenerationRequest(
        job_id="r15b-job",
        product_type="video_trend",
        video_flow_type="video_trend",
        prompt="Public confirmed product video",
        ratio="9:16",
        duration_seconds=16,
        required_capability="text_to_video_or_scene_video",
        metadata=base_metadata,
    )


def _env(**updates):
    env = {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
        "PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED": "1",
        "PRODUCT_VIDEO_PAID_RETRY_REQUIRES_CONFIRMATION": "1",
    }
    env.update({key: str(value) for key, value in updates.items()})
    return env


def _run(monkeypatch, tmp_path, primary, fallback, request=None):
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [primary, fallback])
    return video_provider_router.run_provider_generation(
        request or _request(),
        output_dir=str(tmp_path),
        environ=_env(),
        sleep_func=lambda _seconds: None,
    )


def test_public_confirmed_worker_poll_primary_failure_fallbacks_once(monkeypatch, tmp_path):
    primary = _PrimaryFailedProvider()
    fallback = _FallbackSuccessProvider()

    result = _run(monkeypatch, tmp_path, primary, fallback)

    assert primary.submit_calls == 0
    assert primary.poll_calls == 1
    assert fallback.submit_calls == 1
    assert fallback.poll_calls == 1
    assert fallback.materialize_calls == 1
    assert fallback.request_sources == ["public_confirmed_fallback_once"]
    assert result["ok"] is True
    assert result["fallback_used"] is True
    assert result["fallback_submit_source"] == "public_confirmed_fallback_once"
    assert result["fallback_count"] == 1
    assert result["submit_source"] == "public_confirmed_fallback_once"
    assert result["original_submit_source"] == "public_user_final_confirm"
    assert result["public_user_confirmed"] is True
    assert result["invoice_confirmed"] is True
    assert result["provider_submit_accepted_before"] is True
    assert result["provider_submit_allowed"] is True
    assert result.get("charge", 0) == 0


def test_worker_poll_without_persisted_public_confirm_blocks_fallback(monkeypatch, tmp_path):
    primary = _PrimaryFailedProvider()
    fallback = _FallbackSuccessProvider()

    result = _run(
        monkeypatch,
        tmp_path,
        primary,
        fallback,
        _request(
            original_submit_source="",
            public_confirm_submit_source="",
            public_user_confirmed=False,
            invoice_confirmed=False,
            provider_submit_accepted_before=True,
        ),
    )

    assert primary.submit_calls == 0
    assert primary.poll_calls == 1
    assert fallback.submit_calls == 0
    assert result["ok"] is False
    assert result["fallback_allowed"] is False
    assert result["fallback_blocked_reason"] in {
        "source_not_public_confirmed_fallback",
        "public_confirm_missing",
        "paid_fallback_requires_confirmation",
    }
    assert result["no_charge"] is True


def test_debug_recover_status_sources_stay_blocked_even_with_public_confirm():
    for source in ("debug", "recover", "status", "smoke", "codex_test", "background_retry"):
        policy = video_provider_router.product_video_controlled_fallback_policy(
            "provider_poll_failed",
            {
                "submit_source": source,
                "original_submit_source": "public_user_final_confirm",
                "public_user_confirmed": True,
                "invoice_confirmed": True,
                "provider_submit_accepted_before": True,
                "fallback_count": 0,
            },
        )
        assert policy["fallback_allowed"] is False
        assert policy["fallback_blocked_reason"] == "hidden_or_read_only_source"


def test_invalid_primary_result_url_fallbacks_for_public_confirmed_job(monkeypatch, tmp_path):
    primary = _PrimaryFailedProvider(result_url="not-a-real-url", error_code="")
    fallback = _FallbackSuccessProvider()

    result = _run(monkeypatch, tmp_path, primary, fallback)

    assert fallback.submit_calls == 1
    assert result["ok"] is True
    assert result["fallback_used"] is True
    assert result["provider_fallback_reason"] == "provider_failed_result_url_invalid"
    assert any(item["reason"] == "provider_failed_result_url_invalid" for item in result["provider_fallback_attempts"])


def test_fallback_failure_becomes_failed_no_charge(monkeypatch, tmp_path):
    primary = _PrimaryFailedProvider()
    fallback = _FallbackFailProvider()

    result = _run(monkeypatch, tmp_path, primary, fallback)

    assert fallback.submit_calls == 1
    assert fallback.materialize_calls == 1
    assert result["ok"] is False
    assert result["status"] == "failed_no_charge" or result.get("no_charge") is True
    assert result.get("charge", 0) == 0
    assert result.get("charged_xu", 0) == 0
    assert result["no_charge"] is True


def test_fallback_policy_blocks_delivered_charged_or_second_fallback():
    base = {
        "submit_source": "worker_poll_existing_task",
        "original_submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "provider_submit_accepted_before": True,
    }
    assert video_provider_router.product_video_controlled_fallback_allowed("provider_download_failed", base)
    assert not video_provider_router.product_video_controlled_fallback_allowed("provider_download_failed", {**base, "delivered": True})
    assert not video_provider_router.product_video_controlled_fallback_allowed("provider_download_failed", {**base, "charged_xu": 300})
    assert not video_provider_router.product_video_controlled_fallback_allowed("provider_download_failed", {**base, "fallback_count": 1})


def test_connector_preserves_original_source_when_worker_polling_existing_task():
    assert '"original_submit_source": original_submit_source or submit_source' in CONNECTOR_SOURCE
    assert '"public_confirm_submit_source": original_submit_source or submit_source' in CONNECTOR_SOURCE
    assert '"submit_source": submit_source' in CONNECTOR_SOURCE
    assert "PRODUCT_VIDEO_SUBMIT_SOURCE_WORKER_POLL_EXISTING_TASK" in CONNECTOR_SOURCE
    assert '"invoice_confirmed": invoice_confirmed' in CONNECTOR_SOURCE
    assert '"provider_submit_accepted_before": bool(pending_matches_request)' in CONNECTOR_SOURCE


def test_hidden_video_freeze_status_is_separate_from_public_live_submit():
    assert "hidden_video_freeze" in BOT_SOURCE
    assert "public_video_maintenance" in BOT_SOURCE
    assert "public_live_provider_allowed" in BOT_SOURCE
    assert "PRODUCT_VIDEO_PUBLIC_MAINTENANCE" in BOT_SOURCE
    assert "public_live_allowed_hidden_freeze_only" in BOT_SOURCE
    assert "Provider/video freeze is active" in BOT_SOURCE


def test_public_panel_has_fallback_running_copy_without_provider_debug_word():
    assert "Đang dựng bằng hệ thống dự phòng" in BOT_SOURCE
    assert "hệ thống đang chuyển sang kênh dựng dự phòng" in BOT_SOURCE
    public_panel = BOT_SOURCE.split("def video_b14_queue_status_text", 1)[1].split("def video_b14_queue_status_keyboard", 1)[0]
    assert "provider dự phòng" not in public_panel


def test_no_real_provider_calls_in_r15b_tests():
    assert "submit_video_job" in ROUTER_SOURCE
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden_urlopen = "urllib.request." + "urlopen"
    assert forbidden_urlopen not in source
    assert ("Shop" + "AIKey") not in source
    assert ("Key" + "4U") not in source
