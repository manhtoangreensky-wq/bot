from pathlib import Path

from services import video_provider_router
from services import video_project_queue as queue
from services import video_real_render_connector as connector


ROOT = Path(__file__).resolve().parents[1]


def _job_122(**overrides):
    job = {
        "id": 122,
        "job_id": 122,
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "provider_order": "shopaikey_video,key4u_video",
        "configured_provider_chain": ["shopaikey_video", "key4u_video"],
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "provider_elapsed_seconds": 608,
        "provider_wait_elapsed_seconds": 608,
        "charged_xu": 0,
        "scene_tasks": [_stuck_scene(1), _stuck_scene(2)],
    }
    job.update(overrides)
    return job


def _stuck_scene(scene_index: int, **overrides):
    scene = {
        "job_id": 122,
        "scene_index": scene_index,
        "request_job_id": f"122-{scene_index}",
        "provider": "shopaikey_video",
        "selected_provider": "shopaikey_video",
        "provider_task_id": f"shop-task-122-{scene_index}",
        "provider_task_id_saved": True,
        "submit_accepted": True,
        "submit_http_status": 200,
        "status": "provider_running",
        "provider_status_payload_source": "shopaikey.data.status",
        "shopaikey_data_status": "IN_PROGRESS",
        "provider_status_raw": "IN_PROGRESS",
        "provider_progress_raw": "30",
        "provider_progress_normalized": 30,
        "provider_elapsed_seconds": 608,
        "provider_wait_elapsed_seconds": 608,
        "provider_progress_last_changed_elapsed_seconds": 608,
        "provider_progress_last_changed_at": "2026-07-10 10:00:00",
        "provider_result_url_present": False,
        "result_url_valid": False,
        "artifact_size": 0,
        "fallback_count": 0,
        "updated_at_epoch": 1_800_000_000,
    }
    scene.update(overrides)
    return scene


def _status_payload():
    return {
        "provider_chain": ["shopaikey_video", "key4u_video"],
        "effective_provider_chain": ["shopaikey_video", "key4u_video"],
        "providers": [
            {"provider": "shopaikey_video", "configured": True, "credit_ok": True},
            {"provider": "key4u_video", "configured": True, "credit_ok": True},
        ],
    }


def _healthy(provider: str):
    return {
        "provider": provider,
        "route_ready": True,
        "live_healthy": True,
        "health_status": "healthy",
        "recent_valid_output": True,
        "last_valid_scene_at": "2026-07-10 09:55:00",
        "provider_degraded_for_product_video_public": False,
    }


def test_job122_fixture_classifies_each_scene_and_wallet_truth(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_IN_PROGRESS_STALL_SECONDS", "300")
    audit = connector.product_video_scene_execution_audit(_job_122())

    assert audit["job_id"] == 122
    assert audit["scene_count"] == 2
    assert audit["wallet_charge"] == 0
    assert audit["root_cause"] == "provider_in_progress_stall"
    assert audit["fallback_evaluated_count"] == 2
    assert audit["terminal_reason"] == "fallback_available_for_stalled_scenes"
    for scene in audit["scenes"]:
        assert scene["task_id_masked"]
        assert scene["submit_accepted"] is True
        assert scene["actual_status"] == "IN_PROGRESS"
        assert scene["progress"] == 30
        assert scene["progress_last_changed_at"] == "2026-07-10 10:00:00"
        assert scene["elapsed_seconds"] == 608
        assert scene["result_available"] is False
        assert scene["fallback_evaluated"] is True
        assert scene["fallback_allowed"] is True


def test_two_stuck_scenes_degrade_route_ready_provider():
    health = video_provider_router.product_video_provider_public_degradation(
        "shopaikey_video",
        [_stuck_scene(1), _stuck_scene(2)],
        environ={"VIDEO_PROVIDER_IN_PROGRESS_STALL_SECONDS": "300"},
        route_ready=True,
        now_epoch=1_800_000_100,
    )

    assert health["route_ready"] is True
    assert health["live_healthy"] is False
    assert health["provider_degraded_for_product_video_public"] is True
    assert health["in_progress_stall_streak"] >= 2
    assert health["no_output_streak"] >= 2
    assert health["recent_stalled_jobs"] == ["122"]
    assert health["degraded_reason"]
    assert health["degraded_until"]


def test_two_not_start_scenes_under_threshold_are_not_counted_as_same_job_stall():
    attempts = [
        _stuck_scene(
            1,
            shopaikey_data_status="NOT_START",
            provider_status_raw="NOT_START",
            provider_elapsed_seconds=20,
            provider_wait_elapsed_seconds=20,
            provider_progress_last_changed_elapsed_seconds=20,
        ),
        _stuck_scene(
            2,
            shopaikey_data_status="NOT_START",
            provider_status_raw="NOT_START",
            provider_elapsed_seconds=20,
            provider_wait_elapsed_seconds=20,
            provider_progress_last_changed_elapsed_seconds=20,
        ),
    ]

    health = video_provider_router.product_video_provider_public_degradation(
        "shopaikey_video",
        attempts,
        environ={"VIDEO_PROVIDER_NOT_START_STALL_SECONDS": "60"},
        route_ready=True,
        now_epoch=1_800_000_100,
    )

    assert health["provider_degraded_for_product_video_public"] is False
    assert health["live_healthy"] is False
    assert health["health_status"] == "unknown"
    assert health["recent_stalled_jobs"] == []
    assert health["no_output_streak"] == 0


def test_route_ready_without_recent_valid_output_is_not_live_healthy():
    health = video_provider_router.product_video_provider_public_degradation(
        "shopaikey_video",
        [],
        environ={},
        route_ready=True,
        now_epoch=1_800_000_100,
    )

    assert health["route_ready"] is True
    assert health["live_healthy"] is False
    assert health["health_status"] == "unknown"
    assert health["recent_valid_output"] is False


def test_recent_valid_scene_resets_streak_and_is_healthy():
    attempts = [
        _stuck_scene(1, updated_at_epoch=1_800_000_000),
        _stuck_scene(
            1,
            job_id=123,
            provider_task_id="shop-task-123-1",
            status="clip_downloaded",
            provider_status_raw="SUCCESS",
            provider_progress_raw="100",
            provider_progress_normalized=100,
            result_url_valid=True,
            provider_result_url_present=True,
            artifact_size=4096,
            clip_valid=True,
            updated_at_epoch=1_800_000_090,
        ),
    ]
    health = video_provider_router.product_video_provider_public_degradation(
        "shopaikey_video",
        attempts,
        environ={},
        route_ready=True,
        now_epoch=1_800_000_100,
    )

    assert health["live_healthy"] is True
    assert health["health_status"] == "healthy"
    assert health["last_valid_scene_at"]
    assert health["no_output_streak"] == 0


def test_recent_progress_change_does_not_trigger_fallback(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_IN_PROGRESS_STALL_SECONDS", "300")
    monkeypatch.setenv("PRODUCT_VIDEO_TOTAL_SCENE_TIMEOUT_SECONDS", "1200")
    policy = connector.product_video_scene_stall_policy(
        _job_122(),
        _stuck_scene(1, provider_progress_raw="45", provider_progress_last_changed_elapsed_seconds=30),
        1,
    )

    assert policy["provider_in_progress_stalled"] is False
    assert policy["fallback_evaluated"] is True
    assert policy["fallback_allowed"] is False
    assert policy["fallback_block_reason"] == "provider_progress_changed_recently"


def test_only_stuck_scene_is_fallback_eligible(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_IN_PROGRESS_STALL_SECONDS", "300")
    success = _stuck_scene(
        1,
        status="clip_downloaded",
        provider_status_raw="SUCCESS",
        provider_result_url_present=True,
        result_url_valid=True,
        clip_valid=True,
        artifact_size=2048,
    )
    stuck = _stuck_scene(2)

    success_policy = connector.product_video_scene_stall_policy(_job_122(), success, 1)
    stuck_policy = connector.product_video_scene_stall_policy(_job_122(), stuck, 2)

    assert success_policy["fallback_allowed"] is False
    assert success_policy["fallback_block_reason"] == "scene_already_has_valid_clip"
    assert stuck_policy["fallback_allowed"] is True


def test_fallback_idempotency_is_per_job_scene_candidate():
    first = connector.product_video_scene_fallback_idempotency_key(122, 1, "key4u_video")
    same = connector.product_video_scene_fallback_idempotency_key(122, 1, "key4u_video")
    other_scene = connector.product_video_scene_fallback_idempotency_key(122, 2, "key4u_video")

    assert first == same
    assert first != other_scene
    assert first


def test_fallback_already_used_cannot_submit_again(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_IN_PROGRESS_STALL_SECONDS", "300")
    policy = connector.product_video_scene_stall_policy(
        _job_122(),
        _stuck_scene(1, fallback_count=1, fallback_provider="key4u_video"),
        1,
    )

    assert policy["fallback_allowed"] is False
    assert policy["fallback_block_reason"] == "scene_fallback_already_used"


def test_primary_and_fallback_late_success_keep_first_valid_winner():
    selection = connector.product_video_select_scene_winner(
        [
            {
                "task_id": "fallback-task",
                "provider": "key4u_video",
                "clip_valid": True,
                "artifact_size": 2048,
                "completed_at_epoch": 200,
            },
            {
                "task_id": "primary-task",
                "provider": "shopaikey_video",
                "clip_valid": True,
                "artifact_size": 4096,
                "completed_at_epoch": 210,
            },
        ]
    )

    assert selection["scene_winner_task"] == "fallback-task"
    assert selection["scene_winner_provider"] == "key4u_video"
    assert selection["duplicate_scene_result_prevented"] is True
    assert selection["late_result_ignored"] == ["primary-task"]


def test_persisted_winner_survives_restart_when_still_valid():
    selection = connector.product_video_select_scene_winner(
        [
            {"task_id": "primary-task", "provider": "shopaikey_video", "clip_valid": True, "artifact_size": 1024, "completed_at_epoch": 100},
            {"task_id": "fallback-task", "provider": "key4u_video", "clip_valid": True, "artifact_size": 2048, "completed_at_epoch": 90},
        ],
        persisted_winner_task="primary-task",
    )

    assert selection["scene_winner_task"] == "primary-task"
    assert selection["winner_source"] == "persisted_winner"


def test_fallback_success_increases_scene_coverage_and_full_coverage_enables_concat():
    one_scene = queue.product_video_scene_coverage_state(
        {"scene_count": 2},
        {"id": 122},
        {
            "scene_count": 2,
            "scene_tasks": [
                {"scene_index": 1, "provider_task_id": "primary-1", "clip_valid": True, "artifact_size": 1024},
                {"scene_index": 2, "provider_task_id": "primary-2", "status": "provider_running"},
            ],
        },
    )
    fallback_completed = queue.product_video_scene_coverage_state(
        {"scene_count": 2},
        {"id": 122},
        {
            "scene_count": 2,
            "scene_tasks": [
                {"scene_index": 1, "provider_task_id": "primary-1", "clip_valid": True, "artifact_size": 1024},
                {
                    "scene_index": 2,
                    "provider_task_id": "fallback-2",
                    "provider": "key4u_video",
                    "clip_valid": True,
                    "artifact_size": 2048,
                    "fallback_used": True,
                },
            ],
        },
    )

    assert one_scene["scene_coverage_count"] == 1
    assert one_scene["concat_waiting_for_scene_coverage"] is True
    assert fallback_completed["scene_coverage_count"] == 2
    assert fallback_completed["missing_scene_indexes"] == []
    assert fallback_completed["missing_scene_action"] == "concat"


def test_full_scene_concat_delivery_allows_one_idempotent_post_delivery_charge(tmp_path):
    final_path = tmp_path / "final.mp4"
    final_path.write_bytes(b"valid-final-video")
    project = {
        "scene_count": 2,
        "video_delivered_at": "2026-07-10 10:30:00",
        "final_video_path": str(final_path),
        "invoice_json": queue._json_dumps(
            {
                "scene_count": 2,
                "user_visible_price_xu": 300,
                "persisted_quoted_price_xu": 300,
                "customer_charge_planned_xu": 300,
            }
        ),
    }
    result = {
        "scene_count": 2,
        "final_video_path": str(final_path),
        "final_mp4_valid": True,
        "final_delivered": True,
        "concat_attempted": True,
        "concat_output_valid": True,
        "concat_status": "completed",
        "scene_clip_validation_by_index": {
            "1": {"ok": True, "bytes": 1024},
            "2": {"ok": True, "bytes": 2048},
        },
    }

    first = queue.product_video_delivery_charge_decision(project, {"id": 122}, result)
    repeated = queue.product_video_delivery_charge_decision(project, {"id": 122}, result)

    assert first["ok"] is True
    assert first["amount_xu"] == 300
    assert first["charge_idempotency_key"] == "product_video_final_delivery:122:300"
    assert repeated["charge_idempotency_key"] == first["charge_idempotency_key"]


def test_no_fallback_candidate_fails_clean_no_charge(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_IN_PROGRESS_STALL_SECONDS", "300")
    job = _job_122(provider_order="shopaikey_video", configured_provider_chain=["shopaikey_video"])
    job["scene_tasks"] = [
        _stuck_scene(1, fallback_provider_order=[]),
        _stuck_scene(2, fallback_provider_order=[]),
    ]
    audit = connector.product_video_scene_execution_audit(job)

    assert audit["terminal_reason"] == "all_scene_providers_exhausted_no_charge"
    assert audit["continue_polling"] is False
    assert audit["wallet_charge"] == 0


def test_health_aware_route_skips_unknown_and_selects_healthy_provider():
    decision = video_provider_router.product_video_public_provider_route_decision(
        status=_status_payload(),
        degraded_providers={
            "shopaikey_video": {
                "route_ready": True,
                "live_healthy": False,
                "health_status": "unknown",
                "provider_degraded_for_product_video_public": False,
            },
            "key4u_video": _healthy("key4u_video"),
        },
    )

    assert decision["ok"] is True
    assert decision["selected_provider"] == "key4u_video"
    assert decision["skipped_providers"][0]["reason"] == "provider_live_health_unknown"


def test_no_healthy_provider_blocks_before_submit():
    health = {
        "shopaikey_video": {"route_ready": True, "live_healthy": False, "health_status": "unknown"},
        "key4u_video": {"route_ready": True, "live_healthy": False, "health_status": "degraded", "provider_degraded_for_product_video_public": True},
    }
    decision = video_provider_router.product_video_public_provider_route_decision(
        status=_status_payload(),
        degraded_providers=health,
    )

    assert decision["ok"] is False
    assert decision["blocker"] == "no_healthy_video_provider_no_charge"
    assert decision["provider_submit_count"] == 0


def test_multi_scene_gate_requires_recent_valid_live_health(monkeypatch):
    monkeypatch.delenv("PRODUCT_VIDEO_MULTI_SCENE_PUBLIC_ENABLED", raising=False)
    unknown = video_provider_router.product_video_multi_scene_public_gate(
        2,
        {"shopaikey_video": {"route_ready": True, "live_healthy": False, "recent_valid_output": False}},
        effective_provider_chain=["shopaikey_video"],
        contract_valid_provider_chain=["shopaikey_video"],
    )
    healthy = video_provider_router.product_video_multi_scene_public_gate(
        2,
        {"shopaikey_video": _healthy("shopaikey_video")},
        effective_provider_chain=["shopaikey_video"],
        contract_valid_provider_chain=["shopaikey_video"],
    )

    assert unknown["ok"] is False
    assert unknown["provider_submit_count"] == 0
    assert unknown["charge"] == 0
    assert healthy["ok"] is True


def test_multi_scene_env_off_blocks_two_scenes_but_single_scene_healthy_works(monkeypatch):
    monkeypatch.setenv("PRODUCT_VIDEO_MULTI_SCENE_PUBLIC_ENABLED", "false")
    health = {"shopaikey_video": _healthy("shopaikey_video")}

    two = video_provider_router.product_video_multi_scene_public_gate(
        2,
        health,
        effective_provider_chain=["shopaikey_video"],
        contract_valid_provider_chain=["shopaikey_video"],
    )
    one = video_provider_router.product_video_multi_scene_public_gate(
        1,
        health,
        effective_provider_chain=["shopaikey_video"],
        contract_valid_provider_chain=["shopaikey_video"],
    )

    assert two["ok"] is False
    assert two["blocker"] == "product_video_multi_scene_public_disabled"
    assert one["ok"] is True


def test_r18s_source_contract_keeps_public_copy_clean_and_debug_read_only():
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
    router_source = (ROOT / "services" / "video_provider_router.py").read_text(encoding="utf-8")

    assert "PRODUCT_VIDEO_MULTI_SCENE_PUBLIC_ENABLED" in router_source
    assert "VIDEO_PROVIDER_IN_PROGRESS_STALL_SECONDS" in router_source
    assert 'metadata.get("fallback_idempotency_key")' in router_source
    assert "Hệ thống tạo video đang bận. TOAN AAS chưa trừ Xu. Anh/chị vui lòng thử lại sau." in bot_source
    assert "product_video_multi_scene_public_gate" in bot_source
    for marker in ("cmd_video_provider_job_debug", "cmd_video_render_debug", "cmd_progress_status_debug"):
        start = bot_source.index(f"async def {marker}")
        end = bot_source.find("\nasync def ", start + 1)
        segment = bot_source[start : end if end != -1 else len(bot_source)]
        assert "run_provider_generation(" not in segment
        assert "submit_video_job(" not in segment


def test_no_real_provider_calls_in_r18s_tests():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "urllib.request." + "urlopen",
        "provider" + "_smoke",
    )
    assert all(token not in source for token in forbidden)
