"""Zero-cost Contract Test Suite for Frame Video (image_to_video) at Tier 400 (80 Xu/scene).

Covers Master Task 2: P0.VIDEO.FRAME_VIDEO_LOCAL_80XU
Scenario 2: Thời trang đường phố Hà Nội (3 images / scenes)
- Commercial contract: executor_product_type="image_to_video", engine_route="frame_video_render"
- Pricing: Tier 400 unit price is 80 Xu/scene; 3 scenes = 240 Xu base invoice
- Route contract: local FFmpeg renderer, route_requires_provider=False (PROVIDER_CALLS=0)
- Addon materialization: BGM music ducking (20%), subtitles, watermark logo (TTS/Voice OFF)
- Delivery receipt and exactly-once billing invariants (fail-closed, 240 Xu on delivery)
- Worker transition and terminal receipt immutability
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import bot
from services import (
    video_tail9,
    video_ai_real_pricing,
    video_provider_router,
    video_project_queue as queue,
    product_video_addon_materialization,
    frame_video_public_seam,
)


SCENARIO_2_IMAGES = [
    {"scene_index": 1, "image_name": "ao_so_mi_lua.jpg", "caption": "Áo sơ mi lụa tơ tằm thủ công"},
    {"scene_index": 2, "image_name": "quan_ong_rong.jpg", "caption": "Quần ống rộng cách điệu"},
    {"scene_index": 3, "image_name": "tui_coi_handmade.jpg", "caption": "Phụ kiện túi cói mộc mạc"},
]


def test_scenario2_commercial_contract_and_tier400_pricing():
    """Verify frame_video_local commercial contract and 80 Xu/scene pricing for Tier 400."""
    contract = video_tail9.commercial_contract("frame_video_local")
    assert contract["product_type"] == "frame_video_local"
    assert contract["flow_owner"] == "frame_video"
    assert contract["engine_route"] == "frame_video_render"
    assert contract["executor_product_type"] == "image_to_video"
    assert contract["pricing_mode"] == "frame_video"
    assert contract["worker_owner"] == "frame_video"
    assert contract["required_capability"] == "local_ffmpeg"
    assert 400 in contract["supported_quality_tiers"]

    # Package compatibility for 3 scenes, Tier 400, 9:16
    compat = video_tail9.package_compatibility(
        "frame_video_local",
        scene_count=3,
        ratio="9:16",
        quality_tier_id=400,
        asset_ready=True,
        input_valid=True,
    )
    assert compat["ok"] is True
    assert compat["blockers"] == []

    # Verify Tier 400 customer unit price is 80 Xu
    tier_info = video_ai_real_pricing.product_video_route_by_tier(400)
    assert tier_info["customer_unit_xu"] == 80

    # Base invoice quote: 3 scenes * 80 Xu = 240 Xu
    expected_base_xu = 3 * tier_info["customer_unit_xu"]
    assert expected_base_xu == 240


def test_scenario2_route_contract_local_only_zero_provider_calls():
    """Verify frame_video_local executes locally via FFmpeg with zero paid provider API calls."""
    route_contract = video_provider_router.product_video_route_contract(
        "frame_video_local",
        "frame_video_render",
        "",
    )
    assert route_contract["route_requires_provider"] is False
    assert "local_image_sequence" in route_contract["allowed_execution_modes"]

    engine_contract = queue.product_video_engine_contract("frame_video_local")
    assert engine_contract["public_product_type"] == "frame_video_local"
    assert engine_contract["worker_owner"] == "frame_video"
    assert engine_contract["engine_route"] == "frame_video_render"
    assert engine_contract["required_capability"] == "local_ffmpeg"
    assert engine_contract["execution_enabled"] is True


def test_scenario2_addon_configuration_music_subtitles_watermark_no_tts(tmp_path):
    """Scenario 2: BGM ducking + subtitles + watermark enabled, TTS Voice explicitly disabled."""
    fake_logo = str(tmp_path / "fashion_logo.png")
    with open(fake_logo, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    job = {
        "id": 602,
        "product_type": "frame_video_local",
        "addon_plan": {
            "requested_addons": ["subtitles", "music", "watermark"],
            "voice": {"enabled": False},
            "subtitles": {"enabled": True, "style": "clean_bottom_white", "font_size": 20},
            "music": {"enabled": True, "track_id": "acoustic_chill", "ducking_percent": 20},
            "watermark": {"enabled": True, "file_path": fake_logo, "position": "bottom_right"},
        },
        "project": {
            "id": 502,
            "scene_cards_json": json.dumps([
                {"scene_index": item["scene_index"], "subtitle_line": item["caption"]}
                for item in SCENARIO_2_IMAGES
            ]),
        },
    }

    plan = product_video_addon_materialization.addon_plan(job)
    assert plan["requested_addons"] == ["subtitles", "music", "watermark"]
    assert "voice" not in plan["requested_addons"]
    assert plan["voice"]["enabled"] is False
    assert plan["music"]["enabled"] is True
    assert plan["music"]["ducking_percent"] == 20
    assert plan["subtitles"]["enabled"] is True
    assert plan["watermark"]["enabled"] is True

    # Subtitle script extraction
    sub_text = product_video_addon_materialization._persisted_scene_subtitle_script(job)
    assert "Áo sơ mi lụa tơ tằm" in sub_text
    assert "Phụ kiện túi cói mộc mạc" in sub_text


def test_scenario2_delivery_receipt_and_exactly_once_billing(tmp_path):
    """Verify exactly-once 240 Xu billing upon valid artifact delivery, and fail-closed zero charge."""
    valid_mp4 = str(tmp_path / "hanoi_fashion_final.mp4")
    with open(valid_mp4, "wb") as f:
        f.write(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)

    project = {
        "id": 702,
        "user_id": 8888,
        "product_type": "frame_video_local",
        "final_video_path": valid_mp4,
        "video_delivered_at": "2026-09-15T12:00:00Z",
        "video_delivery_message_id": "67890",
        "quoted_price_xu": 240,
    }
    job = {"id": 802, "project_id": 702, "user_id": 8888}
    result = {
        "final_delivered": True,
        "final_mp4_validated": True,
        "final_video_path": valid_mp4,
    }

    # Successful delivery -> exactly 240 Xu charged
    decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision["ok"] is True
    assert decision["amount_xu"] == 240
    assert decision["already_charged"] is False
    assert decision["charge_idempotency_key"] == "product_video_final_delivery:802:240"

    # Failed delivery -> 0 Xu charged (Fail-closed)
    failed_result = {
        "final_delivered": False,
        "final_mp4_validated": False,
        "error": "ffmpeg_filter_failure",
    }
    fail_decision = queue.product_video_delivery_charge_decision(project, job, failed_result)
    assert fail_decision["ok"] is False
    assert fail_decision["amount_xu"] == 0


def test_scenario2_terminal_receipt_immutability():
    """Verify terminal receipt for frame_video_render cannot be corrupted by replay."""
    receipt_json = json.dumps({"video_url": "https://cdn.toanaas.vn/video.mp4", "duration": 24.0})
    job = {
        "job_type": "frame_video_render",
        "status": "succeeded",
        "output_url": receipt_json,
        "output_file_id": "file_abc_123",
    }

    # Same receipt replay -> no blocker
    blocker = frame_video_public_seam.frame_video_terminal_receipt_replay_blocker(
        job,
        "succeeded",
        output_url=receipt_json,
        output_file_id="file_abc_123",
    )
    assert blocker == ""

    # Conflicting receipt replay -> blocked
    different_receipt = json.dumps({"video_url": "https://cdn.toanaas.vn/corrupted.mp4", "duration": 5.0})
    blocker_conflict = frame_video_public_seam.frame_video_terminal_receipt_replay_blocker(
        job,
        "succeeded",
        output_url=different_receipt,
        output_file_id="file_abc_123",
    )
    assert blocker_conflict == "frame_terminal_receipt_conflict"
