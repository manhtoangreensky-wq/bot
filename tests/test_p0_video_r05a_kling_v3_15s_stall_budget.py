"""Tests for P0.PRODUCT_VIDEO_R16_10B14N19P Kling V3 15s stall budget correction.

TASK_ID=P0.PRODUCT_VIDEO_R16_10B14N19P_R05A_KLING_V3_15S_CROSS_LAYER_STALL_BUDGET_FAIL_CLOSED_CORRECTION
TRACKER=manhtoangreensky-wq/bot#1155
PARENT_N19O_RECEIPT=6078473628

Verifies 20 required provider-free cases:
01 canonical R05A key4u/kling-v3/15s at 299s -> not stalled
02 canonical R05A key4u/kling-v3/15s at 300s -> not stalled
03 canonical R05A key4u/kling-v3/15s at 340s -> not stalled
04 canonical R05A key4u/kling-v3/15s at 479s -> not stalled
05 canonical R05A key4u/kling-v3/15s at >=480s, no progress/result -> stalled
06 canonical R05A 15s provider result succeeds before 480 -> success dominates stall
07 result URL present -> never converted into stall
08 explicit terminal provider failure before 480 -> fail closed immediately
09 key4u/kling-v3/10s retains baseline threshold
10 key4u other Kling model/15s does not inherit special budget
11 non-key4u provider does not inherit special budget
12 non-R05A product does not inherit special budget
13 connector and provider-health/degradation resolve same effective 480 budget for exact tuple
14 provider-health does NOT degrade exact tuple at ~340s solely for being over old 300s threshold
15 provider-health CAN classify actual no-progress stall after corrected threshold
16 total hard timeout remains bounded and effective
17 no fallback becomes enabled
18 no resubmit becomes enabled
19 no duplicate provider submit is generated
20 existing not-start 60s semantics remain unchanged
"""

from __future__ import annotations

import time
import pytest
from services import video_provider_router, video_real_render_connector


def _canonical_r05a_job(overrides: dict | None = None) -> dict:
    job = {
        "job_id": 54,
        "project_id": 156,
        "product_type": "self_shot_scene_change",
        "provider": "key4u_video",
        "primary_provider": "key4u_video",
        "model": "kling-v3",
        "capability": "image_to_video",
        "engine_route": "controlled_keyframe_image_to_video",
        "engine_adapter": "controlled_keyframe_image_to_video",
        "quality_tier": 700,
        "scene_duration_seconds": 15,
        "duration_seconds": 15,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "provider_order": ["key4u_video"],
        "effective_provider_chain": ["key4u_video"],
        "fallback_chain": [],
        "automatic_fallback_allowed": False,
    }
    if overrides:
        job.update(overrides)
    return job


def _canonical_r05a_scene_task(elapsed: int = 0, progress: int = 30, overrides: dict | None = None) -> dict:
    now = time.time()
    task = {
        "scene_index": 1,
        "provider": "key4u_video",
        "model": "kling-v3",
        "product_type": "self_shot_scene_change",
        "duration_seconds": 15,
        "scene_duration_seconds": 15,
        "status": "provider_running",
        "provider_status_raw": "IN_PROGRESS",
        "active_task_id": "1500069527701954560",
        "provider_task_id": "1500069527701954560",
        "provider_progress_normalized": progress,
        "provider_progress_raw": str(progress),
        "scene_submitted_at_epoch": now - elapsed,
        "submitted_at_epoch": now - elapsed,
        "provider_started_at_epoch": now - elapsed,
        "provider_progress_last_changed_at_epoch": now - elapsed,
        "result_url_valid": False,
        "download_url_present": False,
        "provider_result_url_present": False,
        "artifact_size": 0,
        "clip_valid": False,
        "fallback_count": 0,
    }
    if overrides:
        task.update(overrides)
    return task


def test_01_canonical_r05a_at_299s_not_stalled():
    job = _canonical_r05a_job()
    task = _canonical_r05a_scene_task(elapsed=299)
    policy = video_real_render_connector.product_video_scene_stall_policy(job, task, scene_index=1)
    assert policy["in_progress_stall_threshold"] == 480
    assert policy["provider_scene_stalled"] is False
    assert policy["scene_running_without_result_stalled"] is False
    assert policy["provider_in_progress_stalled"] is False


def test_02_canonical_r05a_at_300s_not_stalled():
    job = _canonical_r05a_job()
    task = _canonical_r05a_scene_task(elapsed=300)
    policy = video_real_render_connector.product_video_scene_stall_policy(job, task, scene_index=1)
    assert policy["in_progress_stall_threshold"] == 480
    assert policy["provider_scene_stalled"] is False
    assert policy["scene_running_without_result_stalled"] is False
    assert policy["provider_in_progress_stalled"] is False


def test_03_canonical_r05a_at_340s_not_stalled():
    job = _canonical_r05a_job()
    task = _canonical_r05a_scene_task(elapsed=340)
    policy = video_real_render_connector.product_video_scene_stall_policy(job, task, scene_index=1)
    assert policy["in_progress_stall_threshold"] == 480
    assert policy["provider_scene_stalled"] is False
    assert policy["scene_running_without_result_stalled"] is False
    assert policy["provider_in_progress_stalled"] is False


def test_04_canonical_r05a_at_479s_not_stalled():
    job = _canonical_r05a_job()
    task = _canonical_r05a_scene_task(elapsed=479)
    policy = video_real_render_connector.product_video_scene_stall_policy(job, task, scene_index=1)
    assert policy["in_progress_stall_threshold"] == 480
    assert policy["provider_scene_stalled"] is False
    assert policy["scene_running_without_result_stalled"] is False


def test_05_canonical_r05a_at_480s_no_progress_stalled():
    job = _canonical_r05a_job()
    task = _canonical_r05a_scene_task(elapsed=480)
    policy = video_real_render_connector.product_video_scene_stall_policy(job, task, scene_index=1)
    assert policy["in_progress_stall_threshold"] == 480
    assert policy["provider_scene_stalled"] is True
    assert policy["scene_running_without_result_stalled"] is True
    assert policy["provider_in_progress_stalled"] is True
    assert policy["stall_threshold"] == 480


def test_06_canonical_r05a_succeeds_before_480_dominates_stall():
    job = _canonical_r05a_job()
    task = _canonical_r05a_scene_task(
        elapsed=340,
        overrides={
            "provider_status_raw": "SUCCESS",
            "result_url_valid": True,
            "provider_result_url_present": True,
            "artifact_size": 2048000,
            "clip_valid": True,
        },
    )
    policy = video_real_render_connector.product_video_scene_stall_policy(job, task, scene_index=1)
    assert policy["provider_scene_stalled"] is False
    assert policy["scene_running_without_result_stalled"] is False


def test_07_result_url_present_never_converted_to_stall():
    job = _canonical_r05a_job()
    task = _canonical_r05a_scene_task(
        elapsed=550,
        overrides={
            "result_url_valid": True,
            "provider_result_url_present": True,
            "artifact_size": 1024,
        },
    )
    policy = video_real_render_connector.product_video_scene_stall_policy(job, task, scene_index=1)
    assert policy["provider_scene_stalled"] is False


def test_08_explicit_terminal_provider_failure_fails_closed():
    attempt = {
        "job_id": 54,
        "scene_index": 1,
        "provider": "key4u_video",
        "model": "kling-v3",
        "product_type": "self_shot_scene_change",
        "duration_seconds": 15,
        "status": "FAILED",
        "provider_status_raw": "FAILED",
        "terminal_state": "failed",
        "created_at_epoch": 1_800_000_000,
        "updated_at_epoch": 1_800_000_100,
    }
    health = video_provider_router.product_video_provider_public_degradation(
        "key4u_video",
        [attempt],
        now_epoch=1_800_000_105,
    )
    assert health["terminal_failure_streak"] >= 1


def test_09_key4u_kling_v3_10s_retains_baseline_threshold():
    job = _canonical_r05a_job({"scene_duration_seconds": 10, "duration_seconds": 10, "quality_tier": 500})
    task = _canonical_r05a_scene_task(elapsed=300, overrides={"duration_seconds": 10, "scene_duration_seconds": 10})
    policy = video_real_render_connector.product_video_scene_stall_policy(job, task, scene_index=1)
    assert policy["in_progress_stall_threshold"] == 300
    assert policy["provider_scene_stalled"] is True


def test_10_key4u_other_kling_model_15s_retains_baseline_threshold():
    job = _canonical_r05a_job({"model": "kling-3.0-turbo"})
    task = _canonical_r05a_scene_task(elapsed=300, overrides={"model": "kling-3.0-turbo"})
    policy = video_real_render_connector.product_video_scene_stall_policy(job, task, scene_index=1)
    assert policy["in_progress_stall_threshold"] == 300
    assert policy["provider_scene_stalled"] is True


def test_11_non_key4u_provider_retains_baseline_threshold():
    job = _canonical_r05a_job({"provider": "shopaikey_video", "primary_provider": "shopaikey_video"})
    task = _canonical_r05a_scene_task(elapsed=300, overrides={"provider": "shopaikey_video"})
    policy = video_real_render_connector.product_video_scene_stall_policy(job, task, scene_index=1)
    assert policy["in_progress_stall_threshold"] == 300
    assert policy["provider_scene_stalled"] is True


def test_12_non_r05a_product_retains_baseline_threshold():
    job = _canonical_r05a_job({"product_type": "video_editing"})
    task = _canonical_r05a_scene_task(elapsed=300, overrides={"product_type": "video_editing"})
    policy = video_real_render_connector.product_video_scene_stall_policy(job, task, scene_index=1)
    assert policy["in_progress_stall_threshold"] == 300
    assert policy["provider_scene_stalled"] is True


def test_13_connector_and_router_resolve_same_effective_budget():
    job = _canonical_r05a_job()
    task = _canonical_r05a_scene_task()
    connector_budget = video_real_render_connector._product_video_in_progress_stall_threshold(job=job, scene_task=task)
    router_budget = video_provider_router.resolve_product_video_in_progress_stall_threshold(job=job, scene_task=task)
    assert connector_budget == 480
    assert router_budget == 480
    assert connector_budget == router_budget


def test_14_provider_health_does_not_degrade_exact_tuple_at_340s():
    now = 1_800_000_340.0
    attempts = [
        {
            "job_id": 54,
            "scene_index": 1,
            "provider": "key4u_video",
            "model": "kling-v3",
            "product_type": "self_shot_scene_change",
            "duration_seconds": 15,
            "status": "IN_PROGRESS",
            "provider_status_raw": "IN_PROGRESS",
            "provider_progress_last_changed_at_epoch": now - 340,
            "created_at_epoch": now - 340,
            "updated_at_epoch": now - 340,
            "result_url_present": False,
            "artifact_size": 0,
            "clip_valid": False,
        },
        {
            "job_id": 54,
            "scene_index": 2,
            "provider": "key4u_video",
            "model": "kling-v3",
            "product_type": "self_shot_scene_change",
            "duration_seconds": 15,
            "status": "IN_PROGRESS",
            "provider_status_raw": "IN_PROGRESS",
            "provider_progress_last_changed_at_epoch": now - 340,
            "created_at_epoch": now - 340,
            "updated_at_epoch": now - 340,
            "result_url_present": False,
            "artifact_size": 0,
            "clip_valid": False,
        },
    ]
    health = video_provider_router.product_video_provider_public_degradation(
        "key4u_video",
        attempts,
        route_ready=True,
        now_epoch=now,
    )
    assert health["in_progress_stall_streak"] == 0
    assert health["provider_degraded_for_product_video_public"] is False


def test_15_provider_health_classifies_stall_after_corrected_threshold():
    now = 1_800_000_500.0
    attempts = [
        {
            "job_id": 54,
            "scene_index": 1,
            "provider": "key4u_video",
            "model": "kling-v3",
            "product_type": "self_shot_scene_change",
            "duration_seconds": 15,
            "status": "IN_PROGRESS",
            "provider_status_raw": "IN_PROGRESS",
            "provider_progress_last_changed_at_epoch": now - 485,
            "created_at_epoch": now - 485,
            "updated_at_epoch": now - 485,
            "result_url_present": False,
            "artifact_size": 0,
            "clip_valid": False,
        },
        {
            "job_id": 54,
            "scene_index": 2,
            "provider": "key4u_video",
            "model": "kling-v3",
            "product_type": "self_shot_scene_change",
            "duration_seconds": 15,
            "status": "IN_PROGRESS",
            "provider_status_raw": "IN_PROGRESS",
            "provider_progress_last_changed_at_epoch": now - 485,
            "created_at_epoch": now - 485,
            "updated_at_epoch": now - 485,
            "result_url_present": False,
            "artifact_size": 0,
            "clip_valid": False,
        },
    ]
    health = video_provider_router.product_video_provider_public_degradation(
        "key4u_video",
        attempts,
        route_ready=True,
        now_epoch=now,
    )
    assert health["in_progress_stall_streak"] >= 2
    assert health["provider_degraded_for_product_video_public"] is True


def test_16_total_hard_timeout_remains_bounded_and_effective():
    job = _canonical_r05a_job()
    now = time.time()
    task = _canonical_r05a_scene_task(
        elapsed=600,
        overrides={
            "provider_progress_last_changed_at_epoch": now - 200,
        },
    )
    policy = video_real_render_connector.product_video_scene_stall_policy(job, task, scene_index=1)
    assert policy["provider_scene_stalled"] is True
    assert policy["stall_threshold"] >= 600


def test_17_no_fallback_becomes_enabled_for_r05a():
    job = _canonical_r05a_job()
    task = _canonical_r05a_scene_task(elapsed=480)
    policy = video_real_render_connector.product_video_scene_stall_policy(job, task, scene_index=1)
    assert policy["provider_scene_stalled"] is True
    assert policy["fallback_allowed"] is False
    assert policy["in_progress_stall_decision"] == "failed_no_charge_no_fallback"


def test_18_no_resubmit_authorized():
    job = _canonical_r05a_job()
    task = _canonical_r05a_scene_task(elapsed=480)
    policy = video_real_render_connector.product_video_scene_stall_policy(job, task, scene_index=1)
    assert policy.get("fallback_idempotency_key") == ""
    assert policy.get("fallback_provider") in (None, "")


def test_19_no_duplicate_provider_submit():
    key1 = video_real_render_connector.product_video_scene_dispatch_idempotency_key(54, 1, "key4u_video")
    key2 = video_real_render_connector.product_video_scene_dispatch_idempotency_key(54, 1, "key4u_video")
    assert key1 == key2
    assert len(key1) == 24


def test_20_existing_not_start_60s_semantics_unchanged():
    job = _canonical_r05a_job()
    task = _canonical_r05a_scene_task(
        elapsed=60,
        progress=0,
        overrides={
            "status": "provider_not_start",
            "provider_status_raw": "NOT_START",
            "active_task_id": "",
            "provider_task_id": "",
        },
    )
    policy = video_real_render_connector.product_video_scene_stall_policy(job, task, scene_index=1)
    assert policy["not_start_threshold_seconds"] == 60
    assert policy["provider_not_start"] is True
    assert policy["provider_stalled_not_start"] is True
    assert policy["provider_scene_stalled"] is True
