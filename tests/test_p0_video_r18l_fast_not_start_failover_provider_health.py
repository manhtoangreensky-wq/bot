import asyncio
from pathlib import Path

from services import video_project_queue, video_provider_router
from services import video_real_render_connector as connector


ROOT = Path(__file__).resolve().parents[1]


def _job_113(**overrides):
    data = {
        "id": 113,
        "job_id": 113,
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "provider_order": "shopaikey_video,key4u_video",
        "configured_provider_chain": "shopaikey_video,key4u_video",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "provider_elapsed_seconds": 50,
        "provider_wait_elapsed_seconds": 50,
        "selected_provider": "shopaikey_video",
        "selected_model": "veo3.1-fast",
        "provider_model_map": {"shopaikey_video": "veo3.1-fast", "key4u_video": "kling-3.0-turbo"},
    }
    data.update(overrides)
    return data


def _not_start_payload(elapsed=50, **overrides):
    data = {
        "scene_index": 1,
        "request_job_id": "113-1",
        "provider": "shopaikey_video",
        "selected_provider": "shopaikey_video",
        "provider_pending_provider": "shopaikey_video",
        "provider_pending_task_id": "task-113-live",
        "provider_task_id": "task-113-live",
        "provider_task_ids": ["task-113-live"],
        "provider_status_payload_source": "shopaikey.data.status",
        "shopaikey_data_status": "NOT_START",
        "shopaikey_raw_status": "NOT_START",
        "raw_provider_status": "IN_PROGRESS",
        "provider_status_raw": "IN_PROGRESS",
        "normalized_provider_status": "running",
        "provider_elapsed_seconds": elapsed,
        "provider_wait_elapsed_seconds": elapsed,
        "scene_not_start_elapsed": 0,
        "continue_polling": True,
        "provider_task_id_saved": True,
        "provider_result_url_present": False,
        "result_url_present": False,
        "result_url_valid": False,
        "artifact_size": 0,
        "output_bytes": 0,
        "fallback_block_reason": "primary_provider_in_progress",
        "key4u_submit_suppressed": True,
    }
    data.update(overrides)
    return data


def _provider_status(key4u_configured=True):
    return {
        "provider_chain": ["shopaikey_video", "key4u_video"],
        "effective_provider_chain": ["shopaikey_video", "key4u_video"],
        "providers": [
            {"provider": "shopaikey_video", "configured": True, "credit_ok": True, "credit_status": "ok"},
            {"provider": "key4u_video", "configured": bool(key4u_configured), "credit_ok": True, "credit_status": "ok"},
        ],
    }


def _three_recent_not_start_jobs():
    return [
        {"job_id": 1, "provider": "shopaikey_video", "provider_status_raw": "NOT_START", "result_url": "", "artifact_size": 0},
        {"job_id": 2, "provider": "shopaikey_video", "provider_status_raw": "NOT_START", "result_url": "", "artifact_size": 0},
        {"job_id": 3, "provider": "shopaikey_video", "provider_status_raw": "NOT_START", "result_url": "", "artifact_size": 0},
        {"job_id": 4, "provider": "shopaikey_video", "provider_status_raw": "IN_PROGRESS", "result_url": "", "artifact_size": 0},
        {"job_id": 5, "provider": "shopaikey_video", "provider_status_raw": "queued", "result_url": "", "artifact_size": 0},
    ]


def test_default_not_start_threshold_is_60_and_env_override(monkeypatch):
    monkeypatch.delenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", raising=False)
    monkeypatch.delenv("PRODUCT_VIDEO_NOT_START_GRACE_SECONDS", raising=False)

    default_threshold, default_source = connector._product_video_not_start_threshold()
    assert default_threshold == 60
    assert default_source == "default:product_video_not_start_grace"

    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "45")
    env_threshold, env_source = connector._product_video_not_start_threshold()
    assert env_threshold == 45
    assert env_source == "env:VIDEO_PROVIDER_NOT_START_STALL_SECONDS"


def test_job_113_under_60_does_not_fallback_or_fail(monkeypatch):
    monkeypatch.delenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", raising=False)

    result = connector._enforce_shopaikey_not_start_final_invariant(
        _not_start_payload(elapsed=50),
        job=_job_113(provider_elapsed_seconds=50, provider_wait_elapsed_seconds=50),
    )

    assert result["not_start_threshold_seconds"] == 60
    assert result["provider_stalled_not_start"] is False
    assert result["fallback_allowed"] is False
    assert result["fallback_block_reason"] == "not_start_under_threshold"
    assert result["continue_polling"] is True
    assert result.get("terminal_state") != "failed_no_charge"


def test_job_113_over_60_allows_fallback_or_fails_clean(monkeypatch):
    monkeypatch.delenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", raising=False)

    with_fallback = connector._enforce_shopaikey_not_start_final_invariant(
        {**_not_start_payload(elapsed=61), "fallback_provider_order": ["key4u_video"]},
        job=_job_113(provider_elapsed_seconds=61, provider_wait_elapsed_seconds=61),
    )
    assert with_fallback["provider_stalled_not_start"] is True
    assert with_fallback["fallback_allowed"] is True
    assert with_fallback["key4u_submit_suppressed"] is False

    no_fallback = connector._enforce_shopaikey_not_start_final_invariant(
        {**_not_start_payload(elapsed=61), "fallback_provider_order": []},
        job=_job_113(provider_order="shopaikey_video", configured_provider_chain="shopaikey_video"),
    )
    assert no_fallback["terminal_state"] == "failed_no_charge"
    assert no_fallback["continue_polling"] is False
    assert no_fallback["no_charge"] is True


def test_worker_fallback_tick_submits_once_with_idempotency(monkeypatch, tmp_path):
    captured = {}

    def fake_run_provider_generation(request, *, output_dir, environ):
        output_path = Path(output_dir) / "fallback.mp4"
        output_path.write_bytes(b"valid-mp4-fixture")
        captured["chain"] = environ.get("VIDEO_PROVIDER_CHAIN")
        captured["metadata"] = dict(request.metadata or {})
        return {
            "ok": True,
            "provider": "key4u_video",
            "provider_status": "succeeded",
            "provider_task_ids": ["task-key4u"],
            "result_url_present": True,
            "output_path": str(output_path),
        }

    monkeypatch.setattr(connector, "run_provider_generation", fake_run_provider_generation)

    class Scene:
        scene_id = 1
        video_prompt = "demo product video"
        visual_prompt = "demo product video"
        aspect_ratio = "9:16"
        target_duration_sec = 8
        _toan_aas_job = _job_113(
            provider_elapsed_seconds=61,
            provider_wait_elapsed_seconds=61,
            scene_tasks=[
                {
                    "scene_index": 1,
                    "request_job_id": "113-1",
                    "provider": "shopaikey_video",
                    "provider_task_id": "task-shop",
                    "status": "provider_not_start",
                    "raw_provider_status": "NOT_START",
                    "shopaikey_data_status": "NOT_START",
                    "provider_elapsed_seconds": 61,
                    "provider_wait_elapsed_seconds": 61,
                    "fallback_count": 0,
                }
            ],
        )

    result = asyncio.run(connector._render_scene_async(Scene(), str(tmp_path / "raw.mp4"), ["shopaikey_video", "key4u_video"]))

    assert captured["chain"] == "key4u_video"
    assert captured["metadata"]["fallback_execution_tick_called"] is True
    assert captured["metadata"]["fallback_submit_attempted"] is True
    assert captured["metadata"]["fallback_idempotency_key"]
    assert result["fallback_used"] is True
    assert result["fallback_submit_attempted"] is True
    assert result["provider"] == "key4u_video"


def test_health_degraded_after_three_not_start_jobs_and_low_basic_primary_moves():
    degraded = video_provider_router.product_video_provider_public_degradation(
        "shopaikey_video",
        _three_recent_not_start_jobs(),
        environ={},
    )
    assert degraded["provider_degraded_for_product_video_public"] is True
    assert degraded["last_not_start_count"] == 3
    assert degraded["health_window_jobs"] == 5
    assert degraded["degrade_duration_seconds"] == 1800
    assert degraded["degraded_until"]

    decision = video_provider_router.product_video_public_provider_route_decision(
        status=_provider_status(key4u_configured=True),
        degraded_providers={"shopaikey_video": degraded},
    )
    assert decision["ok"] is True
    assert decision["selected_provider"] == "key4u_video"
    assert decision["effective_primary_for_low_basic"] == "key4u_video"
    assert decision["primary_selected_due_to_health"] == "health_aware_degraded_provider_skipped"


def test_no_healthy_provider_blocks_before_confirm_no_charge():
    degraded = video_provider_router.product_video_provider_public_degradation(
        "shopaikey_video",
        _three_recent_not_start_jobs(),
        environ={},
    )
    decision = video_provider_router.product_video_public_provider_route_decision(
        status=_provider_status(key4u_configured=False),
        degraded_providers={"shopaikey_video": degraded},
    )
    assert decision["ok"] is False
    assert decision["selected_provider"] == ""
    assert decision["blocker"] == "no_healthy_video_provider_no_charge"


def test_kickoff_preserves_health_chain_and_quote_semantics():
    project = {
        "scene_count": 2,
        "asset_pack_json": '{"source":"product_video","render_mode":"real","provider_call":true,"provider_chain":["shopaikey_video"],"provider_health_at_submit":{"shopaikey_video":{"health_status":"healthy"}},"primary_selected_due_to_health":"default_order","provider_degraded_reason":""}',
        "invoice_json": '{"source":"product_video","scene_count":2,"tier":300,"provider_chain":["shopaikey_video"],"user_visible_price_xu":300,"persisted_quoted_price_xu":300,"customer_charge_planned_xu":300,"wallet_charge_amount_xu":300}',
    }
    payload = video_project_queue.build_product_video_confirm_kickoff_payload(_job_113(), project)
    assert payload["configured_provider_chain"] == ["shopaikey_video"]
    assert payload["effective_primary_for_low_basic"] == "shopaikey_video"
    assert payload["provider_health_at_submit"]["shopaikey_video"]["health_status"] == "healthy"
    assert payload["customer_charge_planned_xu"] == 300
    assert payload["charge"] == 0


def test_r18l_debug_fields_and_no_hidden_submit_source_contracts():
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
    router_source = (ROOT / "services" / "video_provider_router.py").read_text(encoding="utf-8")
    connector_source = (ROOT / "services" / "video_real_render_connector.py").read_text(encoding="utf-8")
    r18g = (ROOT / "tests" / "test_p0_video_r18g_key4u_family_endpoint_quote_consistency.py").read_text(encoding="utf-8")

    for token in (
        "provider health at submit",
        "primary selected due to health",
        "provider degraded reason",
        "fallback execution tick called",
        "fallback submit attempted",
        "fallback idempotency key",
    ):
        assert token in bot_source
    assert "PRODUCT_VIDEO_PROVIDER_NOT_START_DEGRADE_THRESHOLD_DEFAULT = 3" in router_source
    assert "PRODUCT_VIDEO_PROVIDER_HEALTH_WINDOW_JOBS_DEFAULT = 5" in router_source
    assert "DEFAULT_PRODUCT_VIDEO_FIRST_SCENE_NOT_START_GRACE_SECONDS = 60" in connector_source
    assert 'payload["customer_charge_planned_xu"] == 300' in r18g
    assert "PRODUCT_VIDEO_RENDER_PIPELINE_HISTORICAL_CONCAT" in connector_source
    for name in ("cmd_video_provider_job_debug", "cmd_video_render_debug", "cmd_progress_status_debug"):
        marker = f"async def {name}"
        assert marker in bot_source
        start = bot_source.index(marker)
        next_def = bot_source.find("\nasync def ", start + 1)
        next_sync_def = bot_source.find("\ndef ", start + 1)
        candidates = [idx for idx in (next_def, next_sync_def) if idx != -1]
        end = min(candidates) if candidates else len(bot_source)
        source = bot_source[start:end]
        assert "run_provider_generation(" not in source
        assert "submit_video_job(" not in source


def test_no_real_provider_calls_in_r18l_tests():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "urllib.request." + "urlopen",
        "provider" + "_smoke",
    )
    assert all(token not in source for token in forbidden)
