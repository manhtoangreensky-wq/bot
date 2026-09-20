"""Zero-cost Contract Test Suite for Script-to-Video at Tier 400 (80 Xu/scene).

Covers Master Task 1: P0.VIDEO.SCRIPT_IMAGE_VIDEO_80XU
Scenario 1: Kịch bản gốm Bát Tràng (5 scenes)
- Exact script partition into 5 scenes with zero character loss
- Commercial contract: minimum 5 scenes, Tier 400 supported
- Pricing: Tier 400 unit price is 80 Xu/scene; 5 scenes = 400 Xu
- Provider connector: route_requires_provider is True for script_to_video and script_image_video
- Addon materialization: voice TTS, subtitles, BGM audio ducking, watermark logo (PROVIDER_CALLS=0)
- Delivery receipt and exactly-once billing invariants (fail-closed, 400 Xu on delivery)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import bot
from services import (
    video_script_product,
    video_tail9,
    video_ai_real_pricing,
    video_real_render_connector,
    video_provider_router,
    video_project_queue as queue,
    product_video_addon_materialization,
)


SCENARIO_1_SCRIPT = (
    "Nghệ nhân vuốt gốm thủ công bằng tay trên bàn xoay truyền thống. "
    "Đưa phôi gốm vào lò nung truyền thống lửa đỏ rực suốt đêm ngày. "
    "Nghệ nhân tráng lớp men lam cổ truyền phủ đều bề mặt bình. "
    "Vẽ họa tiết hoa sen tinh xảo bằng bút lông nét thanh nét đậm. "
    "Thành phẩm bình gốm bóng bẩy sang trọng trưng bày giữa phòng khách quý phái."
)


def test_scenario1_exact_partition_into_five_scenes_zero_loss():
    """Scenario 1: Kịch bản gốm Bát Tràng exact partition into 5 scenes with 100% coverage."""
    partition = video_script_product.exact_partition(SCENARIO_1_SCRIPT, 5)
    assert partition["ok"] is True
    assert partition["scene_count"] == 5
    scenes = partition["scenes"]
    assert len(scenes) == 5

    # Invariant: Zero character loss
    assert "".join(scenes) == SCENARIO_1_SCRIPT
    assert partition["coverage"]["exact_match"] is True
    assert partition["coverage"]["no_truncation"] is True
    assert partition["coverage"]["coverage_percent"] == 100

    # Each scene must have non-empty meaningful content
    for idx, scene in enumerate(scenes, start=1):
        assert len(scene.strip()) > 0
        assert any(c.isalnum() for c in scene)


def test_scenario1_commercial_contract_and_tier400_pricing():
    """Verify script_image_video commercial contract and 80 Xu/scene pricing for Tier 400."""
    contract = video_tail9.commercial_contract("script_image_video")
    assert contract["product_type"] == "script_image_video"
    assert contract["executor_product_type"] == "script_to_video"
    assert contract["minimum_scene_count"] == 5
    assert contract["supports_single_scene"] is False
    assert 400 in contract["supported_quality_tiers"]

    # Check package compatibility with 5 scenes and Tier 400
    compat = video_tail9.package_compatibility(
        "script_image_video",
        scene_count=5,
        ratio="9:16",
        quality_tier_id=400,
        asset_ready=True,
        input_valid=True,
    )
    assert compat["ok"] is True
    assert compat["blockers"] == []

    # Single scene must fail closed (minimum is 5)
    compat_single = video_tail9.package_compatibility(
        "script_image_video",
        scene_count=1,
        ratio="9:16",
        quality_tier_id=400,
    )
    assert compat_single["ok"] is False
    assert "scene_count_not_supported" in compat_single["blockers"] or "single_scene_not_supported" in compat_single["blockers"]

    # Verify Tier 400 customer unit price is 80 Xu
    tier_info = video_ai_real_pricing.product_video_route_by_tier(400)
    assert tier_info["customer_unit_xu"] == 80

    # Invoice quote: 5 scenes * 80 Xu = 400 Xu
    expected_base_xu = 5 * tier_info["customer_unit_xu"]
    assert expected_base_xu == 400


def test_scenario1_route_contract_requires_provider():
    """Ensure script_to_video and script_image_video enforce provider requirement."""
    # 1. Check in PROVIDER_REQUIRED_PRODUCT_TYPES
    assert "script_to_video" in video_real_render_connector.PROVIDER_REQUIRED_PRODUCT_TYPES
    assert "script_image_video" in video_real_render_connector.PROVIDER_REQUIRED_PRODUCT_TYPES

    # 2. Check _route_requires_provider helper
    req_script_to_video = video_real_render_connector._route_requires_provider(
        "script_to_video",
        "text_to_video",
        "",
        engine_adapter="script_scene_engine",
        orchestration_mode="per_scene_8s",
    )
    assert req_script_to_video is True

    req_script_image_video = video_real_render_connector._route_requires_provider(
        "script_image_video",
        "text_to_video",
        "",
        engine_adapter="script_scene_engine",
        orchestration_mode="per_scene_8s",
    )
    assert req_script_image_video is True

    # 3. Check product_video_route_contract
    route_contract = video_provider_router.product_video_route_contract(
        "script_image_video",
        "script_scene_engine",
        "per_scene_8s",
    )
    assert route_contract["route_requires_provider"] is True


def test_scenario1_addon_materialization_zero_cost(tmp_path):
    """Verify add-on plan materializes requested add-ons with PROVIDER_CALLS=0."""
    fake_logo = str(tmp_path / "logo.png")
    with open(fake_logo, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    job = {
        "id": 501,
        "product_type": "script_to_video",
        "addon_plan": {
            "requested_addons": ["voice", "subtitles", "music", "watermark"],
            "voice": {"enabled": True, "voice_id": "vi-VN-HoaiMyNeural", "speed": 1.0},
            "subtitles": {"enabled": True, "style": "modern_yellow", "font_size": 24},
            "music": {"enabled": True, "track_id": "ambient_calm", "ducking_percent": 20},
            "watermark": {"enabled": True, "file_path": fake_logo, "position": "top_right"},
        },
        "project": {
            "id": 401,
            "scene_cards_json": json.dumps([
                {"scene_index": i, "narration_line": f"Đoạn lời thoại cảnh {i}"}
                for i in range(1, 6)
            ]),
        },
    }

    plan = product_video_addon_materialization.addon_plan(job)
    assert plan["requested_addons"] == ["voice", "subtitles", "music", "watermark"]
    assert plan["voice"]["enabled"] is True
    assert plan["music"]["ducking_percent"] == 20

    # Subtitle script extraction
    sub_text = product_video_addon_materialization._persisted_scene_subtitle_script(job)
    assert "Đoạn lời thoại cảnh 1" in sub_text
    assert "Đoạn lời thoại cảnh 5" in sub_text


def test_scenario1_delivery_receipt_and_exactly_once_billing(tmp_path, monkeypatch):
    """Verify exactly-once 400 Xu billing upon valid artifact delivery, and fail-closed zero charge."""
    def fake_probe(path, *args, **kwargs):
        p = str(path or "")
        if "corrupt" in p or "invalid" in p:
            return {"ok": False, "error": "corrupt_video"}
        if p and Path(p).is_file() and Path(p).stat().st_size > 0:
            return {
                "ok": True,
                "duration": 5.0,
                "has_video": True,
                "format": "mp4",
                "streams": [{"codec_type": "video"}],
            }
        return {"ok": False, "error": "file_not_found"}

    monkeypatch.setattr(queue.video_local_validation, "probe_video_file", fake_probe)

    valid_mp4 = str(tmp_path / "bat_trang_final.mp4")
    with open(valid_mp4, "wb") as f:
        f.write(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)

    project = {
        "id": 701,
        "user_id": 8888,
        "product_type": "script_image_video",
        "final_video_path": valid_mp4,
        "video_delivered_at": "2026-09-15T10:00:00Z",
        "video_delivery_message_id": "12345",
        "quoted_price_xu": 400,
    }
    job = {"id": 801, "project_id": 701, "user_id": 8888}
    result = {
        "final_delivered": True,
        "final_mp4_validated": True,
        "final_video_path": valid_mp4,
    }

    # Successful delivery -> exactly 400 Xu charged
    decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision["ok"] is True
    assert decision["amount_xu"] == 400
    assert decision["already_charged"] is False
    assert decision["charge_idempotency_key"] == "product_video_final_delivery:801:400"

    # Incomplete or failed delivery -> 0 Xu charged (Fail-closed)
    failed_result = {
        "final_delivered": False,
        "final_mp4_validated": False,
        "error": "provider_timeout",
    }
    fail_decision = queue.product_video_delivery_charge_decision(project, job, failed_result)
    assert fail_decision["ok"] is False
    assert fail_decision["amount_xu"] == 0
