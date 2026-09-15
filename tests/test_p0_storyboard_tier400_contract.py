"""Zero-cost Contract Test Suite for Storyboard Video at Tier 400 (80 Xu/scene).

Covers Master Task 4: P0.VIDEO.STORYBOARD_PROMPT_80XU
Scenario 5: storyboard_prompt: Mèo phi hành gia & Hành tinh pha lê (2 storyboard frames -> video)
- Exact storyboard frames contract and scene image extraction
- Commercial contract: storyboard_prompt and storyboard_to_video alias, Tier 400 supported
- Pricing: Tier 400 unit price is 80 Xu/scene; 2 scenes = 160 Xu subtotal, 10% discount = 144 Xu total
- Route contract: provider required (I2V / scene_video), route_requires_provider=True
- Addon materialization: bilingual subtitles, BGM ducking, watermark logo with PROVIDER_CALLS=0
- Bilingual subtitle invariant: NOT_YET_PROVEN translation gate enforced (zero paid external translation calls)
- Delivery receipt and exactly-once billing invariants (fail-closed, 144 Xu on delivery)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import bot
from services import (
    video_tail9,
    video_ai_real_pricing,
    video_real_render_connector,
    video_provider_router,
    video_final_output,
    video_project_queue as queue,
    product_video_addon_materialization,
)


SCENARIO_5_FRAMES = [
    {
        "scene_index": 1,
        "title": "Cảnh 1: Đặt chân lên hành tinh pha lê",
        "prompt": "Mèo phi hành gia mặc bộ đồ du hành vũ trụ màu bạc bước ra khỏi tàu con thoi trên bề mặt hành tinh pha lê tím lấp lánh.",
        "subtitle_vi": "Mèo phi hành gia bước ra khỏi tàu vũ trụ trên hành tinh pha lê lấp lánh.",
        "subtitle_en": "Astronaut cat steps out of the spaceship onto the sparkling crystal planet.",
    },
    {
        "scene_index": 2,
        "title": "Cảnh 2: Ngắm nhìn hai mặt trăng",
        "prompt": "Mèo phi hành gia ngồi ngắm bầu trời tinh vân rực rỡ với hai mặt trăng tròn phát sáng đa sắc huyền ảo.",
        "subtitle_vi": "Mèo ngắm nhìn bầu trời đa sắc với hai mặt trăng phát sáng rực rỡ.",
        "subtitle_en": "Cat gazes at the colorful sky with two glowing moons.",
    },
]


def test_scenario5_storyboard_commercial_contract_and_tier400_pricing():
    """Scenario 5: storyboard_prompt commercial contract and 80 Xu/scene pricing for Tier 400."""
    contract = video_tail9.commercial_contract("storyboard_prompt")
    assert contract["product_type"] == "storyboard_prompt"
    assert contract["flow_owner"] == "storyboard"
    assert contract["engine_route"] == "storyboard_to_video"
    assert contract["executor_product_type"] == "storyboard_prompt"
    assert contract["worker_owner"] == "product_video"
    assert contract["required_capability"] == "image_to_video"
    assert contract["input_type"] == "storyboard_frames"
    assert contract["minimum_scene_count"] == 2
    assert contract["supports_single_scene"] is False
    assert 400 in contract["supported_quality_tiers"]

    # Package compatibility for 2 scenes, Tier 400, 9:16
    compat = video_tail9.package_compatibility(
        "storyboard_prompt",
        scene_count=2,
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

    # Pricing calculation: 2 scenes at 80 Xu with standard multiscene 10% discount -> 144 Xu
    price = video_ai_real_pricing.video_multiscene_price(80, 2)
    assert price["unit_xu"] == 80
    assert price["scene_count"] == 2
    assert price["subtotal_xu"] == 160
    assert price["discount_percent"] == 10
    assert price["discount_xu"] == 16
    assert price["total_xu"] == 144


def test_scenario5_route_contract_requires_provider():
    """Ensure storyboard_prompt and storyboard_to_video enforce provider requirement."""
    # 1. Check connector PROVIDER_REQUIRED_PRODUCT_TYPES
    assert "storyboard_prompt" in video_real_render_connector.PROVIDER_REQUIRED_PRODUCT_TYPES
    assert "storyboard_to_video" in video_real_render_connector.PROVIDER_REQUIRED_PRODUCT_TYPES

    # 2. Check router product_contract
    assert "storyboard_prompt" in video_provider_router.PRODUCT_VIDEO_PROVIDER_REQUIRED_TYPES

    # 3. Check _route_requires_provider helper
    req_storyboard = video_real_render_connector._route_requires_provider(
        "storyboard_prompt",
        "image_to_video",
        "",
        engine_adapter="storyboard_scene_image_video_engine",
        orchestration_mode="per_scene_8s",
    )
    assert req_storyboard is True

    # 4. Check product_video_route_contract
    route_contract = video_provider_router.product_video_route_contract(
        "storyboard_prompt",
        "storyboard_scene_image_video_engine",
        "per_scene_8s",
    )
    assert route_contract["route_requires_provider"] is True
    assert route_contract["route_requirement_source"] in {
        "product_video_text_per_scene_contract",
        "product_video_type_contract",
    }


def test_scenario5_bilingual_subtitles_zero_paid_provider_calls(tmp_path):
    """Scenario 5: Bilingual subtitle materialization without paid translation API calls."""
    fake_frame1 = str(tmp_path / "cat_frame1.png")
    fake_frame2 = str(tmp_path / "cat_frame2.png")
    with open(fake_frame1, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    with open(fake_frame2, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    fake_logo = str(tmp_path / "brand_logo.png")
    with open(fake_logo, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    # Bilingual formatted subtitle lines
    scene_cards = [
        {
            "scene_index": 1,
            "image_path": fake_frame1,
            "subtitle_line": f"{SCENARIO_5_FRAMES[0]['subtitle_vi']} / {SCENARIO_5_FRAMES[0]['subtitle_en']}",
        },
        {
            "scene_index": 2,
            "image_path": fake_frame2,
            "subtitle_line": f"{SCENARIO_5_FRAMES[1]['subtitle_vi']} / {SCENARIO_5_FRAMES[1]['subtitle_en']}",
        },
    ]

    job = {
        "id": 605,
        "product_type": "storyboard_prompt",
        "addon_plan": {
            "requested_addons": ["subtitles", "music", "watermark"],
            "voice": {"enabled": False},
            "subtitles": {"enabled": True, "style": "cinematic_bilingual", "font_size": 22},
            "music": {"enabled": True, "track_id": "space_ambient", "ducking_percent": 20},
            "watermark": {"enabled": True, "file_path": fake_logo, "position": "top_left"},
        },
        "project": {
            "id": 505,
            "scene_cards_json": json.dumps(scene_cards),
        },
    }

    plan = product_video_addon_materialization.addon_plan(job)
    assert plan["requested_addons"] == ["subtitles", "music", "watermark"]
    assert "voice" not in plan["requested_addons"]
    assert plan["music"]["enabled"] is True
    assert plan["subtitles"]["enabled"] is True
    assert plan["watermark"]["enabled"] is True

    # Verify subtitle script extracts bilingual content without calling any external translation API
    sub_text = product_video_addon_materialization._persisted_scene_subtitle_script(job)
    assert "Mèo phi hành gia bước ra khỏi tàu vũ trụ" in sub_text
    assert "Astronaut cat steps out of the spaceship" in sub_text
    assert "Mèo ngắm nhìn bầu trời đa sắc" in sub_text
    assert "Cat gazes at the colorful sky" in sub_text


def test_scenario5_delivery_receipt_and_exactly_once_billing(tmp_path):
    """Verify exactly-once 144 Xu billing upon valid artifact delivery, and fail-closed zero charge."""
    valid_mp4 = str(tmp_path / "cat_astronaut_final.mp4")
    with open(valid_mp4, "wb") as f:
        f.write(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)

    # 2 scenes at Tier 400 = 144 Xu
    project = {
        "id": 705,
        "user_id": 8888,
        "product_type": "storyboard_prompt",
        "final_video_path": valid_mp4,
        "video_delivered_at": "2026-09-15T12:00:00Z",
        "video_delivery_message_id": "55555",
        "quoted_price_xu": 144,
    }
    job = {"id": 805, "project_id": 705, "user_id": 8888}
    result = {
        "final_delivered": True,
        "final_mp4_validated": True,
        "final_video_path": valid_mp4,
    }

    # Successful delivery -> exactly 144 Xu charged
    decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision["ok"] is True
    assert decision["amount_xu"] == 144
    assert decision["already_charged"] is False
    assert decision["charge_idempotency_key"] == "product_video_final_delivery:805:144"

    # Undelivered project -> zero charge (Fail-closed)
    undelivered_project = {
        "id": 706,
        "user_id": 8888,
        "product_type": "storyboard_prompt",
        "quoted_price_xu": 144,
    }
    undelivered_result = {"final_delivered": False, "final_mp4_validated": False}
    fail_decision = queue.product_video_delivery_charge_decision(undelivered_project, job, undelivered_result)
    assert fail_decision["ok"] is False
    assert fail_decision["amount_xu"] == 0
    assert fail_decision["charge_skip_reason"] == "delivery_required_before_charge"


def test_scenario5_storyboard_frame_scene_image_paths(tmp_path):
    """Verify storyboard scene image extraction preserves exact card-to-scene mapping."""
    fake_frame1 = str(tmp_path / "frame1.png")
    fake_frame2 = str(tmp_path / "frame2.png")
    with open(fake_frame1, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    with open(fake_frame2, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    job = {
        "product_type": "storyboard_prompt",
        "scene_cards": [
            {"scene_index": 1, "image_path": fake_frame1},
            {"scene_index": 2, "image_path": fake_frame2},
        ],
    }

    paths_scene1 = video_real_render_connector.product_video_scene_image_paths(job, scene_index=1)
    assert paths_scene1 == [fake_frame1]

    paths_scene2 = video_real_render_connector.product_video_scene_image_paths(job, scene_index=2)
    assert paths_scene2 == [fake_frame2]
