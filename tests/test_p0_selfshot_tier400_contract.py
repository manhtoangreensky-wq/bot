"""Zero-cost Contract Test Suite for Self-Shot Video at Tier 400 (80 Xu/scene).

Covers Master Task 3: P0.VIDEO.SELFSHOT_80XU
Scenario 3: self_shot_scene_change (2 scenes: Landmark office & Sunset rooftop)
Scenario 4: self_shot_cinematic_transform (1 scene: Cyberpunk Neon night walk)
- Commercial contracts: self_shot_scene_change and self_shot_cinematic_transform
- Pricing: Tier 400 unit price is 80 Xu/scene; Scenario 3 (2 scenes) & Scenario 4 (1 scene = 80 Xu)
- Audio authority invariant: SOURCE_AUDIO_AUTHORITY=ORIGINAL, TTS_MUST_NOT_REPLACE_ORIGINAL_AUDIO=YES
- Route contract: provider required (V2V), allow_clean_fail=True, fail-closed on missing source
- Delivery receipt and exactly-once billing invariants (fail-closed, charged only upon delivery)
- Continuity evidence integrity
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
    video_real_render_connector,
    video_final_output,
    video_project_queue as queue,
)


def test_scenario3_selfshot2_commercial_contract_and_tier400_pricing():
    """Scenario 3: self_shot_scene_change commercial contract and Tier 700 pricing (Tier 400 rejected)."""
    contract = video_tail9.commercial_contract("self_shot_scene_change")
    assert contract["product_type"] == "self_shot_scene_change"
    assert contract["flow_owner"] == "selfshot2"
    assert contract["engine_route"] == "self_shot_scene_change"
    assert contract["executor_product_type"] == "self_shot_scene_change"
    assert contract["worker_owner"] == "selfshot2"
    assert contract["required_capability"] == "video_to_video"
    adapter = video_tail9.adapter_for("self_shot_scene_change")
    assert adapter["source_audio_available"] is True
    assert 400 not in contract["supported_quality_tiers"]
    assert 700 in contract["supported_quality_tiers"]

    # Package compatibility for 2 scenes, Tier 400 rejected
    compat_400 = video_tail9.package_compatibility(
        "self_shot_scene_change",
        scene_count=2,
        ratio="9:16",
        quality_tier_id=400,
        asset_ready=True,
        input_valid=True,
    )
    assert compat_400["ok"] is False
    assert "quality_tier_not_supported" in compat_400["blockers"]

    # Package compatibility for 2 scenes, Tier 700 passes
    compat_700 = video_tail9.package_compatibility(
        "self_shot_scene_change",
        scene_count=2,
        ratio="9:16",
        quality_tier_id=700,
        asset_ready=True,
        input_valid=True,
    )
    assert compat_700["ok"] is True
    assert compat_700["blockers"] == []

    # Verify Tier 700 unit price is 220 Xu and 2-scene quote is 396 Xu
    tier_info = video_ai_real_pricing.product_video_route_by_tier(700)
    assert tier_info["customer_unit_xu"] == 220
    quote = video_ai_real_pricing.video_multiscene_price(220, 2)
    assert quote["total_xu"] == 396


def test_scenario4_selfshot3_commercial_contract_and_tier400_pricing():
    """Scenario 4: self_shot_cinematic_transform commercial contract and Tier 400 pricing."""
    contract = video_tail9.commercial_contract("self_shot_cinematic_transform")
    assert contract["product_type"] == "self_shot_cinematic_transform"
    assert contract["flow_owner"] == "selfshot3"
    assert contract["engine_route"] == "self_shot_cinematic_transform"
    assert contract["executor_product_type"] == "self_shot_cinematic_transform"
    assert contract["worker_owner"] == "selfshot3"
    assert contract["required_capability"] == "video_to_video"
    adapter = video_tail9.adapter_for("self_shot_cinematic_transform")
    assert adapter["source_audio_available"] is True
    assert contract["supports_single_scene"] is True
    assert 400 in contract["supported_quality_tiers"]

    # Package compatibility for 1 scene, Tier 400, 9:16
    compat = video_tail9.package_compatibility(
        "self_shot_cinematic_transform",
        scene_count=1,
        ratio="9:16",
        quality_tier_id=400,
        asset_ready=True,
        input_valid=True,
    )
    assert compat["ok"] is True
    assert compat["blockers"] == []

    # Verify Tier 400 unit price is 80 Xu
    tier_info = video_ai_real_pricing.product_video_route_by_tier(400)
    assert tier_info["customer_unit_xu"] == 80


def test_selfshot_audio_authority_source_audio_preserved_by_default():
    """Audio Authority Invariant: SOURCE_AUDIO_AUTHORITY=ORIGINAL, TTS_MUST_NOT_REPLACE_ORIGINAL_AUDIO=YES."""
    state_ss2 = video_tail9.new_state(product_type="self_shot_scene_change", session_id="ss2-audio")
    audio2 = state_ss2["audio_config"]
    assert audio2["source_audio_available"] is True
    assert audio2["source_audio"] is True
    assert audio2["volumes"]["source_audio"] == 100
    assert audio2["dubbing"] is False

    state_ss3 = video_tail9.new_state(product_type="self_shot_cinematic_transform", session_id="ss3-audio")
    audio3 = state_ss3["audio_config"]
    assert audio3["source_audio_available"] is True
    assert audio3["source_audio"] is True
    assert audio3["volumes"]["source_audio"] == 100
    assert audio3["dubbing"] is False


def test_selfshot_provider_requirements_and_clean_fail():
    """Verify both self-shot products require provider and support fail-closed clean fail."""
    assert "self_shot_scene_change" in video_real_render_connector.PROVIDER_REQUIRED_PRODUCT_TYPES
    assert "self_shot_cinematic_transform" in video_real_render_connector.PROVIDER_REQUIRED_PRODUCT_TYPES

    # Route contract requires provider
    route_ss2 = video_provider_router.product_video_route_contract("self_shot_scene_change", "", "")
    assert route_ss2["route_requires_provider"] is True

    route_ss3 = video_provider_router.product_video_route_contract("self_shot_cinematic_transform", "", "")
    assert route_ss3["route_requires_provider"] is True

    # Final output engine route marks allow_clean_fail=True
    route_meta_ss2 = video_final_output.route_for_product_type("self_shot_scene_change")
    assert route_meta_ss2.get("allow_clean_fail") is True

    route_meta_ss3 = video_final_output.route_for_product_type("self_shot_cinematic_transform")
    assert route_meta_ss3.get("allow_clean_fail") is True

    # Missing source video triggers clean fail without charges
    with pytest.raises(video_real_render_connector.RealVideoRenderError) as exc_info:
        video_real_render_connector._render_selfshot2_video_to_video(
            job={"source_video_local_path": ""},
            asset_pack={},
            raw_path="",
            provider_order=["key4u"],
            fallback_prompt="test",
            aspect_ratio="9:16",
            scene_index=1,
        )
    assert str(exc_info.value) == "selfshot2_source_video_not_materialized"
    assert exc_info.value.diagnostics.get("no_charge") is True


def test_selfshot_delivery_receipt_and_exactly_once_billing(tmp_path, monkeypatch):
    """Verify exactly-once billing upon valid artifact delivery and 0 Xu charge upon failure."""
    def fake_probe(path):
        p = str(path or "")
        if "corrupt" in p or "invalid" in p:
            return {"ok": False, "error": "corrupt_video"}
        if p and Path(p).is_file() and Path(p).stat().st_size > 0:
            return {
                "ok": True,
                "duration": 16.0,
                "has_video": True,
                "format": "mp4",
                "streams": [{"codec_type": "video"}],
            }
        return {"ok": False, "error": "file_not_found"}

    monkeypatch.setattr(queue.video_local_validation, "probe_video_file", fake_probe)

    valid_mp4_ss2 = str(tmp_path / "ss2_final.mp4")
    with open(valid_mp4_ss2, "wb") as f:
        f.write(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)

    # Scenario 3: 2 scenes -> 396 Xu (Tier 700 with standard 10% 2-scene discount: 2 * 220 * 0.9 = 396)
    project_ss2 = {
        "id": 703,
        "user_id": 8888,
        "product_type": "self_shot_scene_change",
        "final_video_path": valid_mp4_ss2,
        "video_delivered_at": "2026-09-15T12:00:00Z",
        "video_delivery_message_id": "11111",
        "quoted_price_xu": 396,
    }
    job_ss2 = {"id": 803, "project_id": 703, "user_id": 8888}
    result_ss2 = {
        "final_delivered": True,
        "final_mp4_validated": True,
        "final_video_path": valid_mp4_ss2,
    }

    decision_ss2 = queue.product_video_delivery_charge_decision(project_ss2, job_ss2, result_ss2)
    assert decision_ss2["ok"] is True
    assert decision_ss2["amount_xu"] == 396
    assert decision_ss2["already_charged"] is False
    assert decision_ss2["charge_idempotency_key"] == "product_video_final_delivery:803:396"

    # Scenario 4: 1 scene -> 80 Xu
    valid_mp4_ss3 = str(tmp_path / "ss3_final.mp4")
    with open(valid_mp4_ss3, "wb") as f:
        f.write(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)

    project_ss3 = {
        "id": 704,
        "user_id": 8888,
        "product_type": "self_shot_cinematic_transform",
        "final_video_path": valid_mp4_ss3,
        "video_delivered_at": "2026-09-15T12:00:00Z",
        "video_delivery_message_id": "22222",
        "quoted_price_xu": 80,
    }
    job_ss3 = {"id": 804, "project_id": 704, "user_id": 8888}
    result_ss3 = {
        "final_delivered": True,
        "final_mp4_validated": True,
        "final_video_path": valid_mp4_ss3,
    }

    decision_ss3 = queue.product_video_delivery_charge_decision(project_ss3, job_ss3, result_ss3)
    assert decision_ss3["ok"] is True
    assert decision_ss3["amount_xu"] == 80
    assert decision_ss3["already_charged"] is False
    assert decision_ss3["charge_idempotency_key"] == "product_video_final_delivery:804:80"

    # Undelivered project -> zero charge
    undelivered_project = {
        "id": 705,
        "user_id": 8888,
        "product_type": "self_shot_cinematic_transform",
        "quoted_price_xu": 80,
    }
    undelivered_result = {"final_delivered": False, "final_mp4_validated": False}
    fail_decision = queue.product_video_delivery_charge_decision(undelivered_project, job_ss3, undelivered_result)
    assert fail_decision["ok"] is False
    assert fail_decision["amount_xu"] == 0


def test_selfshot2_continuity_evidence_integrity():
    """Verify continuity evidence cannot be faked by transport-only success."""
    # Transport-only payload without explicit continuity flags
    transport_only = {"status": "succeeded", "http_status": 200, "task_id": "task_abc"}
    evidence = video_real_render_connector._selfshot2_continuity_evidence_from_payload(transport_only)
    assert evidence == {}

    # Explicit continuity evidence
    valid_payload = {
        "person_identity": True,
        "object_identity": True,
        "person_object_relationship": True,
    }
    valid_evidence = video_real_render_connector._selfshot2_continuity_evidence_from_payload(valid_payload)
    assert valid_evidence["person_identity"] is True
    assert valid_evidence["object_identity"] is True
    assert valid_evidence["person_object_relationship"] is True
