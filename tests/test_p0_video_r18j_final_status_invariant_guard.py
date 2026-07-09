from pathlib import Path

from services import video_real_render_connector as connector


ROOT = Path(__file__).resolve().parents[1]


def _job(elapsed: int = 45, provider_order: str = "shopaikey_video,key4u_video") -> dict:
    return {
        "job_id": "111",
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "product_type": "video_trend",
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "provider_order": provider_order,
        "configured_provider_chain": provider_order,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "provider_elapsed_seconds": elapsed,
        "provider_wait_elapsed_seconds": elapsed,
        "selected_provider": "shopaikey_video",
        "selected_model": "veo3.1-fast",
        "provider_model_map": {"shopaikey_video": "veo3.1-fast", "key4u_video": "kling-3.0-turbo"},
    }


def _job_111_payload(elapsed: int = 45, **overrides) -> dict:
    payload = {
        "scene_index": 1,
        "request_job_id": "111-1",
        "provider": "shopaikey_video",
        "selected_provider": "shopaikey_video",
        "provider_task_id": "task-111",
        "provider_video_id": "video-111",
        "provider_task_ids": ["task-111"],
        "provider_video_ids": ["video-111"],
        "status": "IN_PROGRESS",
        "provider_status": "IN_PROGRESS",
        "normalized_provider_status": "running",
        "provider_status_raw": "IN_PROGRESS",
        "raw_provider_status": "IN_PROGRESS",
        "raw_provider_status_before_source_fix": "IN_PROGRESS",
        "provider_status_payload_source": "shopaikey.data.status",
        "shopaikey_data_status": "NOT_START",
        "shopaikey_raw_status": "NOT_START",
        "shopaikey_data_progress_raw": "0%",
        "nonterminal_provider_status": "IN_PROGRESS",
        "provider_elapsed_seconds": elapsed,
        "provider_wait_elapsed_seconds": elapsed,
        "elapsed_wall_clock_seconds": elapsed,
        "scene_not_start_elapsed": 0,
        "provider_result_url_present": False,
        "result_url_present": False,
        "download_url_present": False,
        "artifact_size": 0,
        "output_bytes": 0,
        "provider_error": "provider_in_progress",
        "blocker": "provider_in_progress",
        "fallback_block_reason": "primary_provider_in_progress",
        "fallback_blocked_reason": "primary_provider_in_progress",
        "key4u_submit_suppressed": True,
        "key4u_submit_suppressed_reason": "scene_not_stalled",
        "continue_polling": True,
    }
    payload.update(overrides)
    return payload


def test_job_111_final_invariant_forces_not_start_under_threshold(monkeypatch):
    monkeypatch.delenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", raising=False)
    monkeypatch.delenv("PRODUCT_VIDEO_NOT_START_GRACE_SECONDS", raising=False)

    result = connector._enforce_shopaikey_not_start_final_invariant(
        _job_111_payload(elapsed=45),
        job=_job(elapsed=45),
    )

    assert result["raw_provider_status"] == "NOT_START"
    assert result["provider_status_raw"] == "NOT_START"
    assert result["normalized_provider_status"] == "not_start"
    assert result["provider_status"] == "not_start"
    assert result["current_scene_status"] == "provider_not_start"
    assert result["not_start_override_applied"] is True
    assert result["provider_error"] == "provider_not_start"
    assert result["blocker"] == "provider_not_start"
    assert result["scene_not_start_elapsed"] >= 45
    assert result["fallback_allowed"] is False
    assert result["fallback_block_reason"] == "not_start_under_threshold"
    assert result["key4u_submit_suppressed"] is True
    assert result["key4u_submit_suppressed_reason"] == "not_start_under_threshold"
    assert result["not_start_threshold_seconds"] == 60
    assert result["not_start_threshold_source"] == "default:product_video_not_start_grace"


def test_safe_in_progress_cannot_overwrite_actual_not_start():
    result = connector._apply_pending_provider_dominance(
        _job_111_payload(
            elapsed=45,
            provider_pending_task_id="",
            provider_pending_video_id="",
            provider_error="provider_in_progress",
            blocker="provider_in_progress",
            normalized_provider_status="running",
        ),
        job=_job(elapsed=45),
    )

    assert result["raw_provider_status"] == "NOT_START"
    assert result["provider_status_raw"] == "NOT_START"
    assert result["provider_error"] == "provider_not_start"
    assert result["fallback_block_reason"] == "not_start_under_threshold"


def test_provider_attempt_blocker_not_start_drives_summary_blocker():
    payload = _job_111_payload(
        elapsed=45,
        provider_status_payload_source="",
        shopaikey_data_status="",
        shopaikey_raw_status="",
        provider_attempts=[
            {
                "provider": "shopaikey_video",
                "provider_task_id": "task-111",
                "blocker": "provider_not_start",
                "provider_error": "provider_not_start",
            }
        ],
    )

    result = connector._enforce_shopaikey_not_start_final_invariant(payload, job=_job(elapsed=45))

    assert result["provider_error"] == "provider_not_start"
    assert result["blocker"] == "provider_not_start"
    assert result["raw_provider_status"] == "NOT_START"


def test_not_start_over_threshold_allows_valid_fallback(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "40")

    result = connector._enforce_shopaikey_not_start_final_invariant(
        _job_111_payload(elapsed=45, fallback_provider_order=["key4u_video"]),
        job=_job(elapsed=45),
    )

    assert result["provider_stalled_not_start"] is True
    assert result["fallback_allowed"] is True
    assert result["fallback_block_reason"] == ""
    assert result["key4u_submit_suppressed"] is False


def test_not_start_over_threshold_without_candidate_fails_no_charge(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "40")

    result = connector._enforce_shopaikey_not_start_final_invariant(
        _job_111_payload(elapsed=45, fallback_provider_order=[]),
        job=_job(elapsed=45, provider_order="shopaikey_video"),
    )

    assert result["terminal_state"] == "failed_no_charge"
    assert result["final_decision"] == "failed_no_charge"
    assert result["continue_polling"] is False
    assert result["next_poll_scheduled"] is False
    assert result["no_charge"] is True


def test_actual_in_progress_remains_running():
    payload = _job_111_payload(
        provider_status_payload_source="shopaikey.data.status",
        shopaikey_data_status="IN_PROGRESS",
        shopaikey_raw_status="IN_PROGRESS",
        raw_provider_status="IN_PROGRESS",
        provider_status_raw="IN_PROGRESS",
    )

    result = connector._enforce_shopaikey_not_start_final_invariant(payload, job=_job())

    assert result["raw_provider_status"] == "IN_PROGRESS"
    assert result["provider_error"] == "provider_in_progress"


def test_threshold_default_and_env_override(monkeypatch):
    monkeypatch.delenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", raising=False)
    monkeypatch.delenv("PRODUCT_VIDEO_NOT_START_GRACE_SECONDS", raising=False)

    default_threshold, default_source = connector._product_video_not_start_threshold()
    assert default_threshold == 60
    assert default_source == "default:product_video_not_start_grace"

    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "33")
    env_threshold, env_source = connector._product_video_not_start_threshold()
    assert env_threshold == 33
    assert env_source == "env:VIDEO_PROVIDER_NOT_START_STALL_SECONDS"


def test_r18g_quote_and_routing_source_contracts_preserved():
    source = (ROOT / "tests" / "test_p0_video_r18g_key4u_family_endpoint_quote_consistency.py").read_text(encoding="utf-8")
    assert 'payload["user_visible_price_xu"] == 300' in source
    assert 'payload["customer_charge_planned_xu"] == 300' in source
    assert "test_low_and_basic_route_shopaikey_primary_key4u_fallback_only" in source


def test_r18c_r18d_source_contracts_preserved():
    connector_source = (ROOT / "services" / "video_real_render_connector.py").read_text(encoding="utf-8")
    catalog_source = (ROOT / "services" / "video_provider_catalog.py").read_text(encoding="utf-8")
    routing_source = (ROOT / "config" / "product_video_model_routing.json").read_text(encoding="utf-8")
    assert "PRODUCT_VIDEO_RENDER_PIPELINE_HISTORICAL_CONCAT" in connector_source
    assert "PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S" in connector_source
    assert "resolve_product_video_model" in catalog_source
    assert "veo3.1-fast" in routing_source


def test_hidden_debug_status_recover_do_not_submit_provider():
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
    assert "cmd_video_provider_job_debug" in bot_source
    assert "provider_submit_block_reason" in bot_source
    assert "debug/recover/status" not in bot_source


def test_no_real_provider_calls_in_r18j_tests():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "urllib.request." + "urlopen",
        "provider" + "_smoke",
    )
    assert all(token not in source for token in forbidden)
