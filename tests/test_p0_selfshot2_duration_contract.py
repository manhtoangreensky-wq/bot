"""Provider-free tests for Self-shot Scene Change duration contract end-to-end.

Task: P0.PRODUCT_VIDEO.SELF_SHOT_SCENE_CHANGE.DURATION_CONTRACT.CORRECTION.R1
Bug: SELFSHOT2_TIER_500_600_5S_RUNTIME_8S_MISMATCH
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from services import (
    video_ai_real_pricing,
    video_project_queue,
    video_real_render_connector,
    video_selfshot2,
    video_tail9,
    video_uifreeze1,
)


def _capture_v2v_submit_duration(tier_id: int) -> int:
    mock_cfg = MagicMock(provider_name="key4u_video", model="kling-video")
    captured: dict[str, int] = {}

    def spy_submit(cfg, **kw):
        captured["duration_seconds"] = kw.get("duration_seconds")
        return {
            "status": "completed",
            "result_url": "http://fake/out.mp4",
            "result_url_present": True,
        }

    with patch(
        "services.video_real_render_connector._selfshot3_provider_configs",
        return_value=[mock_cfg],
    ), patch(
        "services.video_ai_edit_provider.submit_video_edit",
        side_effect=spy_submit,
    ), patch(
        "services.video_real_render_connector._materialize_selfshot2_source_segment",
        return_value="dummy.mp4",
    ), patch(
        "services.video_ai_edit_provider.download_result",
        return_value={"path": "dummy.mp4"},
    ), patch(
        "os.path.isfile",
        return_value=True,
    ):
        video_real_render_connector._render_selfshot2_video_to_video(
            job={
                "source_video_local_path": "test.mp4",
                "quality_tier": tier_id,
                "public_user_confirmed": True,
                "submit_source": "public_user_final_confirm",
            },
            asset_pack={},
            raw_path="out.mp4",
            provider_order=["key4u"],
            fallback_prompt="prompt",
            aspect_ratio="9:16",
            scene_index=1,
        )

    return int(captured.get("duration_seconds") or 0)


def test_tier_500_duration_contract_end_to_end():
    """Point 1, 2, 3: Tier 500 public/draft=5s, queue/runtime=5s, V2V submit=5s."""
    # 1. Public catalog
    public_spec = video_uifreeze1.tier_spec(500)
    assert public_spec["seconds"] == 5

    # Canonical route
    canonical_route = video_ai_real_pricing.product_video_route_by_tier(500)
    assert canonical_route["seconds_per_scene"] == 5

    # Tail contract
    compat = video_tail9.package_compatibility(
        "self_shot_scene_change",
        scene_count=1,
        ratio="9:16",
        quality_tier_id=500,
    )
    assert compat["scene_duration_seconds"] == 5

    # Selfshot2 draft helper
    assert video_selfshot2.canonical_scene_seconds(500) == 5

    # Selfshot2 scene plan build
    plan = video_selfshot2.build_scene_plan(
        analysis={"duration_seconds": 10.0},
        subject_manifest={},
        constraints={},
        scene_count=1,
        content={},
        direction={},
        quality_tier=500,
    )
    assert plan[0]["duration"] == 5

    # 2. Queue kickoff payload
    queue_payload = video_project_queue.build_product_video_confirm_kickoff_payload(
        job={"id": "job-500"},
        project={
            "product_type": "self_shot_scene_change",
            "quality_tier": 500,
            "scene_count": 1,
            "invoice_json": '{"quality_tier": 500, "scene_count": 1}',
            "asset_pack_json": '{"quality_tier": 500, "scene_count": 1}',
        },
    )
    assert queue_payload["scene_duration_seconds"] == 5
    assert queue_payload["duration_seconds"] == 5

    # Connector runtime duration
    runtime_dur = video_real_render_connector.product_video_scene_duration_seconds({
        "product_type": "self_shot_scene_change",
        "quality_tier": 500,
    })
    assert runtime_dur == 5

    # 3. V2V Submit receives exact 5s
    v2v_submit_duration = _capture_v2v_submit_duration(500)
    assert v2v_submit_duration == 5


def test_tier_600_duration_contract_end_to_end():
    """Point 4, 5, 6: Tier 600 public/draft=5s, queue/runtime=5s, V2V submit=5s."""
    # 4. Public catalog
    public_spec = video_uifreeze1.tier_spec(600)
    assert public_spec["seconds"] == 5

    # Canonical route
    canonical_route = video_ai_real_pricing.product_video_route_by_tier(600)
    assert canonical_route["seconds_per_scene"] == 5

    # Tail contract
    compat = video_tail9.package_compatibility(
        "self_shot_scene_change",
        scene_count=1,
        ratio="9:16",
        quality_tier_id=600,
    )
    assert compat["scene_duration_seconds"] == 5

    # Selfshot2 draft helper
    assert video_selfshot2.canonical_scene_seconds(600) == 5

    # Selfshot2 scene plan build
    plan = video_selfshot2.build_scene_plan(
        analysis={"duration_seconds": 10.0},
        subject_manifest={},
        constraints={},
        scene_count=1,
        content={},
        direction={},
        quality_tier=600,
    )
    assert plan[0]["duration"] == 5

    # 5. Queue kickoff payload
    queue_payload = video_project_queue.build_product_video_confirm_kickoff_payload(
        job={"id": "job-600"},
        project={
            "product_type": "self_shot_scene_change",
            "quality_tier": 600,
            "scene_count": 1,
            "invoice_json": '{"quality_tier": 600, "scene_count": 1}',
            "asset_pack_json": '{"quality_tier": 600, "scene_count": 1}',
        },
    )
    assert queue_payload["scene_duration_seconds"] == 5
    assert queue_payload["duration_seconds"] == 5

    # Connector runtime duration
    runtime_dur = video_real_render_connector.product_video_scene_duration_seconds({
        "product_type": "self_shot_scene_change",
        "quality_tier": 600,
    })
    assert runtime_dur == 5

    # 6. V2V Submit receives exact 5s
    v2v_submit_duration = _capture_v2v_submit_duration(600)
    assert v2v_submit_duration == 5


def test_tier_800_duration_contract_end_to_end():
    """Point 7: Tier 800 remains 10s end-to-end."""
    public_spec = video_uifreeze1.tier_spec(800)
    assert public_spec["seconds"] == 10

    canonical_route = video_ai_real_pricing.product_video_route_by_tier(800)
    assert canonical_route["seconds_per_scene"] == 10

    compat = video_tail9.package_compatibility(
        "self_shot_scene_change",
        scene_count=1,
        ratio="9:16",
        quality_tier_id=800,
    )
    assert compat["scene_duration_seconds"] == 10

    assert video_selfshot2.canonical_scene_seconds(800) == 10

    queue_payload = video_project_queue.build_product_video_confirm_kickoff_payload(
        job={"id": "job-800"},
        project={
            "product_type": "self_shot_scene_change",
            "quality_tier": 800,
            "scene_count": 1,
            "invoice_json": '{"quality_tier": 800, "scene_count": 1}',
            "asset_pack_json": '{"quality_tier": 800, "scene_count": 1}',
        },
    )
    assert queue_payload["scene_duration_seconds"] == 10
    assert queue_payload["duration_seconds"] == 10

    runtime_dur = video_real_render_connector.product_video_scene_duration_seconds({
        "product_type": "self_shot_scene_change",
        "quality_tier": 800,
    })
    assert runtime_dur == 10

    v2v_submit_duration = _capture_v2v_submit_duration(800)
    assert v2v_submit_duration == 10


def test_tier_700_duration_contract_end_to_end():
    """Point 8: Tier 700 remains 15s end-to-end."""
    public_spec = video_uifreeze1.tier_spec(700)
    assert public_spec["seconds"] == 15

    canonical_route = video_ai_real_pricing.product_video_route_by_tier(700)
    assert canonical_route["seconds_per_scene"] == 15

    compat = video_tail9.package_compatibility(
        "self_shot_scene_change",
        scene_count=1,
        ratio="9:16",
        quality_tier_id=700,
    )
    assert compat["scene_duration_seconds"] == 15

    assert video_selfshot2.canonical_scene_seconds(700) == 15

    queue_payload = video_project_queue.build_product_video_confirm_kickoff_payload(
        job={"id": "job-700"},
        project={
            "product_type": "self_shot_scene_change",
            "quality_tier": 700,
            "scene_count": 1,
            "invoice_json": '{"quality_tier": 700, "scene_count": 1}',
            "asset_pack_json": '{"quality_tier": 700, "scene_count": 1}',
        },
    )
    assert queue_payload["scene_duration_seconds"] == 15
    assert queue_payload["duration_seconds"] == 15

    runtime_dur = video_real_render_connector.product_video_scene_duration_seconds({
        "product_type": "self_shot_scene_change",
        "quality_tier": 700,
    })
    assert runtime_dur == 15

    v2v_submit_duration = _capture_v2v_submit_duration(700)
    assert v2v_submit_duration == 15


def test_two_scene_tier_500_total_duration():
    """Point 9: 2-scene Tier 500 total generated duration = 10s (NOT 16s)."""
    queue_payload = video_project_queue.build_product_video_confirm_kickoff_payload(
        job={"id": "job-500-2scene"},
        project={
            "source": "product_video",
            "product_video": True,
            "product_type": "self_shot_scene_change",
            "quality_tier": 500,
            "scene_count": 2,
            "invoice_json": '{"source": "product_video", "quality_tier": 500, "scene_count": 2}',
            "asset_pack_json": '{"source": "product_video", "quality_tier": 500, "scene_count": 2}',
        },
    )
    assert queue_payload["scene_duration_seconds"] == 5
    assert queue_payload["target_duration_seconds"] == 10
    assert queue_payload["expected_duration_seconds"] == 10
    assert queue_payload["duration_seconds"] == 10
    assert len(queue_payload["scene_tasks"]) == 2
    for task in queue_payload["scene_tasks"]:
        assert task["scene_duration_seconds"] == 5


def test_two_scene_tier_600_total_duration():
    """Point 10: 2-scene Tier 600 total generated duration = 10s (NOT 16s)."""
    queue_payload = video_project_queue.build_product_video_confirm_kickoff_payload(
        job={"id": "job-600-2scene"},
        project={
            "source": "product_video",
            "product_video": True,
            "product_type": "self_shot_scene_change",
            "quality_tier": 600,
            "scene_count": 2,
            "invoice_json": '{"source": "product_video", "quality_tier": 600, "scene_count": 2}',
            "asset_pack_json": '{"source": "product_video", "quality_tier": 600, "scene_count": 2}',
        },
    )
    assert queue_payload["scene_duration_seconds"] == 5
    assert queue_payload["target_duration_seconds"] == 10
    assert queue_payload["expected_duration_seconds"] == 10
    assert queue_payload["duration_seconds"] == 10
    assert len(queue_payload["scene_tasks"]) == 2
    for task in queue_payload["scene_tasks"]:
        assert task["scene_duration_seconds"] == 5
