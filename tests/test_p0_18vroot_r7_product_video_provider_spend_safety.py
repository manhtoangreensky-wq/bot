from services import video_provider_router
from services.video_provider_base import VideoArtifactResult, VideoGenerationRequest, VideoPollResult, VideoSubmitResult


class _Provider:
    def __init__(
        self,
        provider_name: str,
        *,
        submit: VideoSubmitResult | None = None,
        poll: VideoPollResult | None = None,
        artifact: VideoArtifactResult | None = None,
    ):
        self.provider_name = provider_name
        self.submit_result = submit
        self.poll_result = poll
        self.artifact_result = artifact
        self.submit_calls = 0
        self.poll_calls = 0
        self.materialize_calls = 0

    def capabilities(self):
        return {
            "provider": self.provider_name,
            "enabled": True,
            "configured": True,
            "missing": [],
            "capabilities": ["text_to_video", "scene_video", "multi_scene_video"],
            "endpoint_configured": True,
            "submit_url_configured": True,
            "poll_url_configured": True,
            "auth_configured": True,
            "model_configured": True,
            "provider_auth_value_present": True,
            "provider_model_present": True,
            "provider_payload_model": "veo3.1-fast",
            "provider_config_source": f"env:{self.provider_name}",
        }

    def submit_video_job(self, request):
        self.submit_calls += 1
        if self.submit_result is not None:
            return self.submit_result
        return VideoSubmitResult(
            ok=True,
            provider_name=self.provider_name,
            provider_task_id=f"{self.provider_name}-task",
            provider_status="MEDIA_GENERATION_STATUS_PENDING",
            raw={"http_status": 200, "task_id_field_path": "data.id_base"},
        )

    def poll_video_job(self, provider_task_id: str):
        self.poll_calls += 1
        if self.poll_result is not None:
            return self.poll_result
        return VideoPollResult(
            ok=True,
            status="MEDIA_GENERATION_STATUS_IN_PROGRESS",
            provider_name=self.provider_name,
            provider_task_id=provider_task_id,
            raw={"poll_http_status": 200, "provider_status_raw": "MEDIA_GENERATION_STATUS_IN_PROGRESS"},
        )

    def materialize_result(self, result, job_id: str):
        self.materialize_calls += 1
        if self.artifact_result is not None:
            return self.artifact_result
        return VideoArtifactResult(ok=False, error_code="provider_download_failed")


def _request(metadata=None):
    base = {"product_video": True, "allow_provider_pending": True, "wallet_charge": False}
    base.update(metadata or {})
    return VideoGenerationRequest(
        job_id="777",
        product_type="video_trend",
        video_flow_type="video_trend",
        prompt="A real product video",
        ratio="9:16",
        duration_seconds=18,
        required_capability="text_to_video_or_scene_video",
        metadata=base,
    )


def _env(**updates):
    data = {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
        "PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED": "1",
    }
    data.update({key: str(value) for key, value in updates.items()})
    return data


def _run(monkeypatch, tmp_path, providers, *, metadata=None, env=None):
    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: providers)
    return video_provider_router.run_provider_generation(
        _request(metadata),
        output_dir=str(tmp_path),
        environ=env or _env(),
        sleep_func=lambda _seconds: None,
    )


def test_kill_switch_blocks_paid_submit_no_charge(monkeypatch, tmp_path):
    shop = _Provider("shopaikey_video")
    result = _run(
        monkeypatch,
        tmp_path,
        [shop],
        env=_env(PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED="0"),
    )

    assert shop.submit_calls == 0
    assert result["provider_submit_blocked_by_kill_switch"] is True
    assert result["external_provider_spend_prevented"] is True
    assert result["paid_submit_allowed"] is False
    assert result["paid_submit_blocked_reason"] == "provider_submit_kill_switch"
    assert result["no_charge"] is True
    assert result["charge"] == 0
    assert "TOAN AAS" in result["public_message"]
    assert "provider" not in result["public_message"].lower()


def test_existing_provider_task_polls_without_duplicate_submit(monkeypatch, tmp_path):
    shop = _Provider("shopaikey_video")
    result = _run(
        monkeypatch,
        tmp_path,
        [shop],
        metadata={
            "provider_pending_provider": "shopaikey_video",
            "provider_pending_task_id": "shop-task-existing",
            "provider_pending_request_job_id": "777",
        },
    )

    assert shop.submit_calls == 0
    assert shop.poll_calls == 1
    assert result["provider_submit_called"] is False
    assert result["provider_submit_already_exists"] is True
    assert result["duplicate_paid_submit_prevented"] is True
    assert result["duplicate_paid_submit_prevented_count"] == 1
    assert result["active_provider_task"] is True
    assert result["submit_attempt_count"] == 0
    assert result["external_provider_spend_prevented"] is True
    assert result["continue_polling"] is True
    assert result["no_charge"] is True


def test_primary_in_progress_does_not_submit_key4u_paid_fallback(monkeypatch, tmp_path):
    shop = _Provider("shopaikey_video")
    key4u = _Provider("key4u_video")
    result = _run(monkeypatch, tmp_path, [shop, key4u])

    assert shop.submit_calls == 1
    assert shop.poll_calls == 1
    assert key4u.submit_calls == 0
    assert result["blocker"] == "provider_in_progress"
    assert result["fallback_allowed"] is False
    assert result["fallback_blocked_reason"] == "primary_provider_in_progress"
    assert result["key4u_submit_suppressed"] is True


def test_submit_failure_requires_confirmation_before_paid_fallback(monkeypatch, tmp_path):
    shop = _Provider(
        "shopaikey_video",
        submit=VideoSubmitResult(
            ok=False,
            provider_name="shopaikey_video",
            error_code="provider_submit_http_error",
            raw={"http_status": 500, "provider_submit_retriable": True},
        ),
    )
    key4u = _Provider("key4u_video")
    result = _run(monkeypatch, tmp_path, [shop, key4u])

    assert shop.submit_calls == 1
    assert key4u.submit_calls == 0
    assert result["blocker"] == "paid_fallback_requires_confirmation"
    assert result["paid_submit_allowed"] is False
    assert result["paid_submit_blocked_reason"] == "paid_fallback_requires_confirmation"
    assert result["external_provider_spend_prevented"] is True
    assert result["no_charge"] is True


def test_explicit_paid_retry_confirmation_allows_fallback(monkeypatch, tmp_path):
    shop = _Provider(
        "shopaikey_video",
        submit=VideoSubmitResult(
            ok=False,
            provider_name="shopaikey_video",
            error_code="provider_submit_http_error",
            raw={"http_status": 500, "provider_submit_retriable": True},
        ),
    )
    key4u = _Provider("key4u_video")
    result = _run(
        monkeypatch,
        tmp_path,
        [shop, key4u],
        metadata={"paid_provider_retry_confirmed": True},
    )

    assert shop.submit_calls == 1
    assert key4u.submit_calls == 1
    assert result["selected_provider"] == "key4u_video"
    assert result["paid_retry_confirmed"] is True


def test_download_failure_does_not_auto_submit_paid_fallback(monkeypatch, tmp_path):
    shop = _Provider(
        "shopaikey_video",
        submit=VideoSubmitResult(
            ok=True,
            provider_name="shopaikey_video",
            provider_task_id="shop-final",
            provider_status="succeeded",
            result_url="https://example.test/final.mp4",
            raw={"http_status": 200, "task_id_field_path": "data.id_base"},
        ),
        artifact=VideoArtifactResult(ok=False, error_code="provider_download_failed", bytes=0),
    )
    key4u = _Provider("key4u_video")
    result = _run(monkeypatch, tmp_path, [shop, key4u])

    assert shop.submit_calls == 1
    assert shop.materialize_calls == 1
    assert key4u.submit_calls == 0
    assert result["blocker"] == "paid_fallback_requires_confirmation"
    assert result["provider_fallback_attempted"] is False
    assert result["no_charge"] is True


def test_provider_failure_cooldown_blocks_new_paid_submit(monkeypatch, tmp_path):
    shop = _Provider("shopaikey_video")
    result = _run(
        monkeypatch,
        tmp_path,
        [shop],
        metadata={"recent_provider_failures": 3},
        env=_env(PRODUCT_VIDEO_PROVIDER_FAILURE_COOLDOWN_THRESHOLD="3"),
    )

    assert shop.submit_calls == 0
    assert result["provider_health_cooldown_active"] is True
    assert result["paid_submit_allowed"] is False
    assert result["paid_submit_blocked_reason"] == "provider_health_cooldown_active"
    assert result["external_provider_spend_prevented"] is True
    assert result["no_charge"] is True


def test_spend_safety_debug_fields_do_not_leak_secret_values(monkeypatch, tmp_path):
    shop = _Provider("shopaikey_video")
    result = _run(
        monkeypatch,
        tmp_path,
        [shop],
        env=_env(PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED="0", SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE="super-secret-token"),
    )

    debug_text = str(result)
    assert "provider_submit_idempotency_key" in result
    assert result["admin_external_spend_warning"].startswith("Creating a Product Video job may spend")
    assert "super-secret-token" not in debug_text
    assert result["charged_xu"] == 0


def test_spend_debug_contract_shows_kill_switch_cooldown_and_no_secrets():
    source = open("bot.py", encoding="utf-8").read()

    assert "provider submit kill switch enabled" in source
    assert "paid submit blocked reason" in source
    assert "provider cooldown active" in source
    assert "duplicate submit prevented" in source
    assert "Creating a Product Video job may spend external provider credits" in source
