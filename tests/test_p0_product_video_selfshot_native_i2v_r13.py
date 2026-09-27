# -*- coding: utf-8 -*-
"""
Tests for P0 Product Video SelfShot Native Image-to-Video Architecture Closure (R13).

Strict Invariants:
1. Public product IDs preserved: self_shot_scene_change, self_shot_cinematic_transform
2. Engine route: controlled_keyframe_image_to_video
3. Required capability: image_to_video
4. Fal is 100% unreachable (FAL_PROVIDER_ELIGIBLE=NO)
5. Approved native providers:
   - key4u_video (kling-v3, grok-imagine-video)
   - shopaikey_video (veo3.1-fast)
6. Source video local reference only (never sent on wire)
7. Fresh legacy V2V fails closed: selfshot_legacy_v2v_route_forbidden_no_charge
8. No text-to-video fallback allowed
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock

from services import video_tail9, video_final_output, video_project_queue, video_provider_catalog
from services import video_real_render_connector
from services.video_real_render_connector import RealVideoRenderError
from providers import video_generic_http_provider


# ==============================================================================
# FIRST RED MATRIX: Proves defects exist prior to source modification
# ==============================================================================

def test_first_red_a1_selfshot2_public_queue_contract_persists_i2v():
    """FIRST RED A1: SelfShot2 public queue contract must persist controlled_keyframe_image_to_video / image_to_video."""
    contract = video_project_queue.product_video_engine_contract("self_shot_scene_change")
    assert contract["engine_route"] == "controlled_keyframe_image_to_video"
    assert contract["required_capability"] == "image_to_video"
    assert contract["package_capability"] == "image_to_video"

    comm = video_tail9.commercial_contract("self_shot_scene_change")
    assert comm["engine_route"] == "controlled_keyframe_image_to_video"
    assert comm["required_capability"] == "image_to_video"

    route = video_final_output.route_for_product_type("self_shot_scene_change")
    assert route["provider_capability"] == "image_to_video"
    assert route["engine_adapter"] == "controlled_keyframe_image_to_video"


def test_first_red_a2_selfshot3_public_queue_contract_persists_i2v():
    """FIRST RED A2: SelfShot3 public queue contract must persist controlled_keyframe_image_to_video / image_to_video."""
    contract = video_project_queue.product_video_engine_contract("self_shot_cinematic_transform")
    assert contract["engine_route"] == "controlled_keyframe_image_to_video"
    assert contract["required_capability"] == "image_to_video"
    assert contract["package_capability"] == "image_to_video"

    comm = video_tail9.commercial_contract("self_shot_cinematic_transform")
    assert comm["engine_route"] == "controlled_keyframe_image_to_video"
    assert comm["required_capability"] == "image_to_video"

    route = video_final_output.route_for_product_type("self_shot_cinematic_transform")
    assert route["provider_capability"] == "image_to_video"
    assert route["engine_adapter"] == "controlled_keyframe_image_to_video"


def test_first_red_b1_shopaikey_selfshot_i2v_payload_contract(tmp_path):
    """FIRST RED B1: ShopAIKey veo3.1-fast must support image_to_video capability and payload serialization without path leak."""
    model_cfg = video_provider_catalog.provider_model_config("shopaikey_video", "veo3.1-fast")
    assert model_cfg is not None, "shopaikey_video veo3.1-fast must exist in catalog"
    caps = model_cfg.get("capabilities", [])
    assert "image_to_video" in caps, "veo3.1-fast must support image_to_video"

    # Field validation for image_to_video
    payload_contract = video_provider_catalog.payload_contract_for_model("shopaikey_video", "veo3.1-fast")
    assert "image" in payload_contract.get("allowed_fields", [])
    assert "image_paths" in payload_contract.get("allowed_fields", [])
    by_cap = payload_contract.get("allowed_fields_by_capability", {})
    assert "image" in by_cap.get("image_to_video", [])
    assert "image_paths" in by_cap.get("image_to_video", [])

    # Test wire payload serialization: local image converted to base64, raw paths popped
    dummy_img = tmp_path / "keyframe.jpg"
    dummy_img.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 32)

    raw_payload = {
        "model": "veo3.1-fast",
        "prompt": "smooth cinematic motion",
        "image": str(dummy_img),
        "image_paths": [str(dummy_img)],
        "storyboard": [str(dummy_img)],
        "aspect_ratio": "9:16",
        "duration": 8,
    }
    wire = video_generic_http_provider._shopaikey_wire_payload(raw_payload)
    assert wire["image"].startswith("data:image/jpeg;base64,") or len(wire["image"]) > 30
    assert not os.path.exists(wire["image"])
    assert "image_paths" not in wire
    assert "storyboard" not in wire


def test_first_red_b2_selfshot_i2v_model_resolver_is_provider_aware():
    """FIRST RED B2: Shared SelfShot I2V resolver must be provider-aware and validate allowed models per provider."""
    environ = {
        "KEY4U_API_KEY": "test_k4u",
        "KEY4U_KLING_VIDEO_ENDPOINT": "https://api.key4u.vn/kling/v1/videos/image2video",
        "SHOPAIKEY_API_KEY": "test_sak",
        "SHOPAIKEY_BASE_URL": "https://api.shopaikey.com",
    }
    # ShopAIKey provider-aware resolution
    model, family = video_real_render_connector._resolve_selfshot_i2v_model(
        job={"selected_model": "veo3.1-fast"},
        asset_pack={},
        environ=environ,
        provider="shopaikey_video",
    )
    assert model == "veo3.1-fast"
    assert family == "google_veo"

    # Key4U provider-aware resolution
    model_k4u, family_k4u = video_real_render_connector._resolve_selfshot_i2v_model(
        job={"selected_model": "kling-v3"},
        asset_pack={},
        environ=environ,
        provider="key4u_video",
    )
    assert model_k4u == "kling-v3"
    assert family_k4u == "kling"

    # Reject cross-provider model
    with pytest.raises(RealVideoRenderError) as exc_info:
        video_real_render_connector._resolve_selfshot_i2v_model(
            job={"selected_model": "kling-v3"},
            asset_pack={},
            environ=environ,
            provider="shopaikey_video",
        )
    assert "selfshot_i2v_model_not_proven_no_charge" in str(exc_info.value)


def test_first_red_c1_fal_unreachable_and_legacy_v2v_forbidden(tmp_path):
    """FIRST RED C1: Fal must be unreachable even under selfshot2, and fresh legacy V2V must fail-closed."""
    fake_environ = {
        "FAL_KEY": "test_fal_key",
        "KEY4U_API_KEY": "test_key4u_key",
        "SHOPAIKEY_API_KEY": "test_shopaikey_key",
    }
    with patch.dict(os.environ, fake_environ, clear=False):
        configs = video_real_render_connector._resolve_v2v_provider_configs(
            flow="selfshot2",
            provider_order=["fal_video", "key4u_video", "shopaikey_video"],
            duration_seconds=5,
        )
        provider_names = [c.provider_name for c in configs]
        assert "fal_video" not in provider_names, f"Fal must NEVER be eligible: {provider_names}"
        assert "fal.ai" not in provider_names

    # Fresh legacy V2V must fail closed without charge
    dummy_video = tmp_path / "source.mp4"
    dummy_video.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 64)

    fresh_job = {
        "job_id": "test_fresh_legacy",
        "source_video_local_path": str(dummy_video),
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "quality_tier": 500,
        "route": "video_to_video",  # Legacy route
        "required_capability": "video_to_video",
    }
    fresh_asset_pack = {
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "quality_tier": 500,
        "source_segment": {"start_seconds": 0.0, "duration_seconds": 5.0},
    }

    with pytest.raises(RealVideoRenderError) as exc_info2:
        video_real_render_connector._render_selfshot2_video_to_video(
            job=fresh_job,
            asset_pack=fresh_asset_pack,
            raw_path=str(tmp_path / "out2.mp4"),
            fallback_prompt="test",
            aspect_ratio="9:16",
            scene_index=0,
        )
    assert "selfshot_legacy_v2v_route_forbidden_no_charge" in str(exc_info2.value)

    with pytest.raises(RealVideoRenderError) as exc_info3:
        video_real_render_connector._render_selfshot3_video_to_video(
            job=fresh_job,
            asset_pack=fresh_asset_pack,
            raw_path=str(tmp_path / "out3.mp4"),
            fallback_prompt="test",
            aspect_ratio="9:16",
        )
    assert "selfshot_legacy_v2v_route_forbidden_no_charge" in str(exc_info3.value)


# ==============================================================================
# ADDITIONAL INVARIANT VERIFICATIONS: Native I2V continuity & wire safety
# ==============================================================================

def test_source_video_never_sent_on_wire_in_controlled_keyframe(tmp_path):
    """Invariant: Source video is local reference only; never present in wire payload."""
    dummy_img = tmp_path / "keyframe.png"
    dummy_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    dummy_video = tmp_path / "source.mp4"
    dummy_video.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 32)

    # When building payload for shopaikey or key4u, source_video_path must not be sent on wire
    payload = {
        "model": "veo3.1-fast",
        "prompt": "transform scene",
        "image": str(dummy_img),
        "source_video_path": str(dummy_video),
        "aspect_ratio": "9:16",
        "duration": 8,
    }
    wire = video_generic_http_provider._shopaikey_wire_payload(payload)
    assert "source_video_path" not in wire
    assert str(dummy_video) not in json.dumps(wire)


def test_selfshot_text_to_video_fallback_forbidden():
    """Invariant: Text-to-video fallback is strictly forbidden for SelfShot2/3."""
    comm2 = video_tail9.commercial_contract("self_shot_scene_change")
    comm3 = video_tail9.commercial_contract("self_shot_cinematic_transform")

    assert "text_to_video" not in comm2.get("fallback_capabilities", ())
    assert "text_to_video" not in comm3.get("fallback_capabilities", ())
    assert comm2.get("required_capability") != "text_to_video"
    assert comm3.get("required_capability") != "text_to_video"


# ==============================================================================
# REMEDIATION TEST MATRIX (A - M)
# ==============================================================================

def test_matrix_a_selfshot2_active_provider_task_is_poll_only(tmp_path):
    """A: SelfShot2 genuine active provider task = poll-only (NEW_SUBMIT=NO, POLL_ONLY=YES)."""
    from services import video_ai_edit_provider

    dummy_video = tmp_path / "source.mp4"
    dummy_video.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 64)
    out_mp4 = tmp_path / "out_ss2.mp4"

    legacy_job = {
        "job_id": "legacy_ss2_job",
        "provider_task_id": "ext-task-ss2-12345",
        "provider": "key4u_video",
        "source_video_local_path": str(dummy_video),
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "quality_tier": 500,
        "route": "video_to_video",
        "required_capability": "video_to_video",
    }
    legacy_asset_pack = {
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "quality_tier": 500,
        "scene_duration_seconds": 5,
        "source_segment": {"start_seconds": 0.0, "duration_seconds": 5.0},
    }

    mock_cfg = MagicMock()
    mock_cfg.provider_name = "key4u_video"
    mock_cfg.model = "kling-v3"

    def fake_download(url, dest, **kwargs):
        with open(dest, "wb") as f:
            f.write(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 64)
        return {"ok": True, "path": str(dest), "bytes": 96, "download_http_status": 200}

    with patch.object(video_real_render_connector, "_selfshot2_provider_configs", return_value=[mock_cfg]), \
         patch.object(video_real_render_connector, "_selfshot2_scene_source_segment", return_value={"start_seconds": 0.0, "end_seconds": 5.0, "duration_seconds": 5.0}), \
         patch.object(video_ai_edit_provider, "submit_video_edit") as spy_submit, \
         patch.object(video_ai_edit_provider, "wait_for_result", return_value={"status": "completed", "result_url": "https://cdn.example.com/ss2.mp4", "result_url_present": True}) as spy_poll, \
         patch.object(video_ai_edit_provider, "download_result", side_effect=fake_download), \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity", return_value={
             "ok": True,
             "evidence_source": "local_vision_validator",
             "independent_visual_validation": "LOCAL_MODEL",
             "person_required": True,
             "object_required": False,
         }):
        res = video_real_render_connector._render_selfshot2_video_to_video(
            job=legacy_job,
            asset_pack=legacy_asset_pack,
            raw_path=str(out_mp4),
            provider_order=["key4u_video"],
            fallback_prompt="test",
            aspect_ratio="9:16",
            scene_index=0,
        )
        assert res["ok"] is True
        assert res["poll_only"] is True
        assert res["provider_submit_called"] is False
        assert spy_submit.call_count == 0, "submit_video_edit MUST NOT be called during active task recovery"
        assert spy_poll.call_count == 1, "wait_for_result MUST be called once for active task recovery"


def test_matrix_b_selfshot3_active_provider_task_is_poll_only(tmp_path):
    """B: SelfShot3 genuine active provider task = poll-only (NEW_SUBMIT=NO, POLL_ONLY=YES)."""
    from services import video_ai_edit_provider

    dummy_video = tmp_path / "source3.mp4"
    dummy_video.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 64)
    out_mp4 = tmp_path / "out_ss3.mp4"

    legacy_job = {
        "job_id": "legacy_ss3_job",
        "provider_task_id": "ext-task-ss3-67890",
        "provider": "key4u_video",
        "source_video_local_path": str(dummy_video),
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "quality_tier": 500,
        "route": "video_to_video",
        "required_capability": "video_to_video",
    }
    legacy_asset_pack = {
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "quality_tier": 500,
    }

    mock_cfg = MagicMock()
    mock_cfg.provider_name = "key4u_video"
    mock_cfg.model = "kling-v3"

    def fake_download(url, dest, **kwargs):
        with open(dest, "wb") as f:
            f.write(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 64)
        return {"ok": True, "path": str(dest), "bytes": 96, "download_http_status": 200}

    with patch.object(video_real_render_connector, "_selfshot3_provider_configs", return_value=[mock_cfg]), \
         patch.object(video_ai_edit_provider, "submit_video_edit") as spy_submit, \
         patch.object(video_ai_edit_provider, "wait_for_result", return_value={"status": "completed", "result_url": "https://cdn.example.com/ss3.mp4", "result_url_present": True}) as spy_poll, \
         patch.object(video_ai_edit_provider, "download_result", side_effect=fake_download):
        res = video_real_render_connector._render_selfshot3_video_to_video(
            job=legacy_job,
            asset_pack=legacy_asset_pack,
            raw_path=str(out_mp4),
            provider_order=["key4u_video"],
            fallback_prompt="test",
            aspect_ratio="9:16",
        )
        assert res["ok"] is True
        assert res["poll_only"] is True
        assert res["provider_submit_called"] is False
        assert spy_submit.call_count == 0, "submit_video_edit MUST NOT be called during active task recovery"
        assert spy_poll.call_count == 1, "wait_for_result MUST be called once for active task recovery"


def test_matrix_c_generic_internal_task_id_rejected_as_provider_recovery(tmp_path):
    """C: generic/internal task_id alone does not qualify as provider recovery identity."""
    from services import video_ai_edit_provider

    dummy_video = tmp_path / "source_c.mp4"
    dummy_video.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 64)

    job_with_only_internal_id = {
        "job_id": "job_internal_1",
        "task_id": "internal_worker_token_abc123",  # Internal token, NOT provider_task_id
        "source_video_local_path": str(dummy_video),
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "route": "video_to_video",
        "required_capability": "video_to_video",
    }
    asset_pack = {
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "scene_duration_seconds": 5,
        "source_segment": {"start_seconds": 0.0, "duration_seconds": 5.0},
    }

    with patch.object(video_real_render_connector, "_selfshot2_scene_source_segment", return_value={"start_seconds": 0.0, "end_seconds": 5.0, "duration_seconds": 5.0}), \
         patch.object(video_ai_edit_provider, "submit_video_edit") as spy_submit, \
         patch.object(video_ai_edit_provider, "wait_for_result") as spy_poll:
        with pytest.raises(RealVideoRenderError) as exc2:
            video_real_render_connector._render_selfshot2_video_to_video(
                job=job_with_only_internal_id,
                asset_pack=asset_pack,
                raw_path=str(tmp_path / "c2.mp4"),
                provider_order=["key4u_video"],
                fallback_prompt="test",
                aspect_ratio="9:16",
                scene_index=0,
            )
        assert "selfshot_legacy_v2v_route_forbidden_no_charge" in str(exc2.value)

        with pytest.raises(RealVideoRenderError) as exc3:
            video_real_render_connector._render_selfshot3_video_to_video(
                job=job_with_only_internal_id,
                asset_pack=asset_pack,
                raw_path=str(tmp_path / "c3.mp4"),
                provider_order=["key4u_video"],
                fallback_prompt="test",
                aspect_ratio="9:16",
            )
        assert "selfshot_legacy_v2v_route_forbidden_no_charge" in str(exc3.value)

        assert spy_submit.call_count == 0
        assert spy_poll.call_count == 0


def test_matrix_d_e_f_g_provider_order_and_model_authority(tmp_path):
    """D, E, F, G: Provider order authority preserved (no hidden Key4U reorder) and provider-specific model resolved."""
    dummy_video = tmp_path / "src.mp4"
    dummy_video.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 64)
    dummy_kf = tmp_path / "kf.jpg"
    dummy_kf.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 32)
    out_mp4 = tmp_path / "out.mp4"
    out_mp4.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 64)

    fake_env = {
        "KEY4U_API_KEY": "k4u_secret",
        "KEY4U_KLING_VIDEO_ENDPOINT": "https://api.key4u.vn/kling/v1/videos/image2video",
        "SHOPAIKEY_API_KEY": "sak_secret",
        "SHOPAIKEY_BASE_URL": "https://api.shopaikey.com",
    }

    captured_calls = []

    def fake_run_gen(req, output_dir=None, environ=None, **kwargs):
        captured_calls.append((req, dict(environ or {})))
        return {
            "ok": True,
            "provider_used": req.metadata.get("primary_provider"),
            "model_used": req.metadata.get("model"),
            "provider_task_id": "task-mock-1",
            "provider_task_ids": ["task-mock-1"],
            "file_path": str(out_mp4),
            "result_url_present": True,
        }

    with patch.dict(os.environ, fake_env, clear=False), \
         patch.object(video_real_render_connector, "_materialize_selfshot2_source_segment", return_value=str(dummy_video)), \
         patch.object(video_real_render_connector, "_extract_selfshot_keyframe", return_value=str(dummy_kf)), \
         patch.object(video_real_render_connector, "run_provider_generation", side_effect=fake_run_gen), \
         patch("services.video_selfshot_continuity_validator.validate_selfshot_scene_continuity", return_value={
             "ok": True,
             "evidence_source": "local_vision_validator",
             "independent_visual_validation": "LOCAL_MODEL",
             "person_required": False,
             "object_required": False,
         }):
        # D & F: ShopAIKey-first order remains ShopAIKey-first and resolves veo3.1-fast
        captured_calls.clear()
        video_real_render_connector._render_selfshot2_controlled_keyframe_image_to_video(
            job={"job_id": "ss2_sak"},
            asset_pack={},
            raw_path=str(out_mp4),
            provider_order=["shopaikey_video", "key4u_video"],
            fallback_prompt="test",
            aspect_ratio="9:16",
            scene_index=0,
            source_path=str(dummy_video),
            target_duration=5,
            segment={"start_seconds": 0.0, "duration_seconds": 5.0},
        )
        req_ss2_sak, env_ss2_sak = captured_calls[0]
        assert req_ss2_sak.metadata["primary_provider"] == "shopaikey_video"
        assert env_ss2_sak["VIDEO_PROVIDER_CHAIN"].split(",")[0] == "shopaikey_video"
        assert req_ss2_sak.metadata["model"] == "veo3.1-fast"
        assert env_ss2_sak["SHOPAIKEY_VIDEO_MODEL"] == "veo3.1-fast"

        captured_calls.clear()
        video_real_render_connector._render_selfshot3_controlled_keyframe_image_to_video(
            job={"job_id": "ss3_sak"},
            asset_pack={},
            raw_path=str(out_mp4),
            provider_order=["shopaikey_video", "key4u_video"],
            fallback_prompt="test",
            aspect_ratio="9:16",
            source_path=str(dummy_video),
            duration_seconds=5,
        )
        req_ss3_sak, env_ss3_sak = captured_calls[0]
        assert req_ss3_sak.metadata["primary_provider"] == "shopaikey_video"
        assert env_ss3_sak["VIDEO_PROVIDER_CHAIN"].split(",")[0] == "shopaikey_video"
        assert req_ss3_sak.metadata["model"] == "veo3.1-fast"
        assert env_ss3_sak["SHOPAIKEY_VIDEO_MODEL"] == "veo3.1-fast"

        # E & G: Key4U-first order remains Key4U-first and resolves kling-v3
        captured_calls.clear()
        video_real_render_connector._render_selfshot2_controlled_keyframe_image_to_video(
            job={"job_id": "ss2_k4u"},
            asset_pack={},
            raw_path=str(out_mp4),
            provider_order=["key4u_video", "shopaikey_video"],
            fallback_prompt="test",
            aspect_ratio="9:16",
            scene_index=0,
            source_path=str(dummy_video),
            target_duration=5,
            segment={"start_seconds": 0.0, "duration_seconds": 5.0},
        )
        req_ss2_k4u, env_ss2_k4u = captured_calls[0]
        assert req_ss2_k4u.metadata["primary_provider"] == "key4u_video"
        assert env_ss2_k4u["VIDEO_PROVIDER_CHAIN"].split(",")[0] == "key4u_video"
        assert req_ss2_k4u.metadata["model"] in {"kling-v3", "grok-imagine-video"}
        assert env_ss2_k4u["KEY4U_VIDEO_MODEL"] == "kling-v3"


def test_matrix_h_i_post_submit_and_ambiguous_submit_forbid_fallback(tmp_path):
    """H & I: Post-submit failure and ambiguous submit cannot switch provider or auto-resubmit."""
    from services import video_provider_router
    from services.video_provider_base import VideoGenerationRequest, VideoSubmitResult

    dummy_kf = tmp_path / "kf_hi.jpg"
    dummy_kf.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 32)

    class FakeAdapter:
        def __init__(self, name, submit_fn):
            self.provider_name = name
            self._submit_fn = submit_fn
            self.submit_calls = 0

        def capabilities(self):
            return {
                "provider": self.provider_name,
                "enabled": True,
                "configured": True,
                "capabilities": ["image_to_video"],
                "submit_url_configured": True,
                "poll_url_configured": True,
                "auth_configured": True,
                "auth_present": True,
                "model_configured": True,
                "model_present": True,
            }

        def submit_video_job(self, req):
            self.submit_calls += 1
            return self._submit_fn(req)

    # H: Post-submit HTTP failure on primary (Key4U) -> must NOT call secondary (ShopAIKey)
    primary_h = FakeAdapter(
        "key4u_video",
        lambda r: VideoSubmitResult(
            ok=False,
            provider_name="key4u_video",
            error_code="provider_submit_failed",
            provider_status="failed",
            raw={"http_status": 500, "provider_http_request_sent": True},
        ),
    )
    secondary_h = FakeAdapter(
        "shopaikey_video",
        lambda r: VideoSubmitResult(ok=True, provider_name="shopaikey_video", provider_task_id="sak-1"),
    )

    req_h = VideoGenerationRequest(
        job_id="job_h",
        product_type="self_shot_scene_change",
        video_flow_type="selfshot2",
        prompt="test",
        image_paths=[str(dummy_kf)],
        required_capability="image_to_video",
        metadata={
            "product_video": True,
            "is_controlled_keyframe_i2v": True,
            "route": "controlled_keyframe_image_to_video",
            "public_user_confirmed": True,
            "invoice_confirmed": True,
            "submit_source": "public_user_final_confirm",
            "worker_compatible": True,
        },
    )

    env_h = {
        "VIDEO_PROVIDER_CHAIN": "key4u_video,shopaikey_video",
        "PRODUCT_VIDEO_PUBLIC_SUBMIT_ENABLED": "1",
    }
    with patch.object(video_provider_router, "provider_candidate_adapters", return_value=[primary_h, secondary_h]):
        res_h = video_provider_router.run_provider_generation(req_h, output_dir=str(tmp_path), environ=env_h)
        assert res_h["ok"] is False
        assert primary_h.submit_calls == 1
        assert secondary_h.submit_calls == 0, "OTHER_PROVIDER_SUBMIT must be 0 after physical submit failure"
        assert res_h.get("fallback_used") is False

    # I: Ambiguous submit timeout on primary (ShopAIKey) -> AUTO_RESUBMIT=NO, PROVIDER_FALLBACK=NO, TOTAL_GENERATION_SUBMITS=1
    def raise_timeout(r):
        raise TimeoutError("read timed out during submit")

    primary_i = FakeAdapter("shopaikey_video", raise_timeout)
    secondary_i = FakeAdapter(
        "key4u_video",
        lambda r: VideoSubmitResult(ok=True, provider_name="key4u_video", provider_task_id="k4u-1"),
    )

    req_i = VideoGenerationRequest(
        job_id="job_i",
        product_type="self_shot_cinematic_transform",
        video_flow_type="selfshot3",
        prompt="test",
        image_paths=[str(dummy_kf)],
        required_capability="image_to_video",
        metadata={
            "product_video": True,
            "is_controlled_keyframe_i2v": True,
            "route": "controlled_keyframe_image_to_video",
            "public_user_confirmed": True,
            "invoice_confirmed": True,
            "submit_source": "public_user_final_confirm",
            "worker_compatible": True,
        },
    )

    env_i = {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video",
        "PRODUCT_VIDEO_PUBLIC_SUBMIT_ENABLED": "1",
    }
    with patch.object(video_provider_router, "provider_candidate_adapters", return_value=[primary_i, secondary_i]):
        res_i = video_provider_router.run_provider_generation(req_i, output_dir=str(tmp_path), environ=env_i)
        assert res_i["ok"] is False
        assert res_i["blocker"] == "provider_submit_outcome_ambiguous_no_charge"
        assert res_i.get("auto_resubmit_allowed") is False
        assert res_i.get("fallback_allowed") is False
        assert res_i.get("no_charge") is True
        assert primary_i.submit_calls == 1
        assert secondary_i.submit_calls == 0, "No second paid provider attempt allowed after ambiguous submit"


def test_matrix_j_k_l_public_confirm_kickoff_to_worker_seam(tmp_path):
    """J, K, L: build_product_video_confirm_kickoff_payload preserves SelfShot2/3 I2V contract and worker naturally selects controlled I2V renderer."""
    import asyncio
    from types import SimpleNamespace

    dummy_video = tmp_path / "seam_src.mp4"
    dummy_video.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 2048)
    raw_out = tmp_path / "seam_out.mp4"
    raw_out.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 2048)

    # J: SelfShot2 kickoff payload
    project_ss2 = {
        "id": "proj_ss2",
        "product_type": "self_shot_scene_change",
        "quality_tier": 500,
        "invoice_json": json.dumps({"quality_tier": 500, "scene_count": 1, "total_price_xu": 500}),
        "asset_pack_json": json.dumps({
            "product_type": "self_shot_scene_change",
            "source_video_local_path": str(dummy_video),
            "scene_source_segments": [{"scene_index": 1, "start_seconds": 0.0, "end_seconds": 5.0, "duration_seconds": 5.0}],
        }),
    }
    kickoff_ss2 = video_project_queue.build_product_video_confirm_kickoff_payload(
        job={"id": "job_ss2", "job_id": "job_ss2"},
        project=project_ss2,
        provider_chain=["key4u_video", "shopaikey_video"],
    )
    assert kickoff_ss2["public_product_type"] == "self_shot_scene_change"
    assert kickoff_ss2["engine_route"] == "controlled_keyframe_image_to_video"
    assert kickoff_ss2["required_capability"] == "image_to_video"

    # K: SelfShot3 kickoff payload
    project_ss3 = {
        "id": "proj_ss3",
        "product_type": "self_shot_cinematic_transform",
        "quality_tier": 500,
        "invoice_json": json.dumps({"quality_tier": 500, "scene_count": 1, "total_price_xu": 500}),
        "asset_pack_json": json.dumps({
            "product_type": "self_shot_cinematic_transform",
            "source_video_local_path": str(dummy_video),
        }),
    }
    kickoff_ss3 = video_project_queue.build_product_video_confirm_kickoff_payload(
        job={"id": "job_ss3", "job_id": "job_ss3"},
        project=project_ss3,
        provider_chain=["shopaikey_video", "key4u_video"],
    )
    assert kickoff_ss3["public_product_type"] == "self_shot_cinematic_transform"
    assert kickoff_ss3["engine_route"] == "controlled_keyframe_image_to_video"
    assert kickoff_ss3["required_capability"] == "image_to_video"

    # L: Feed hydrated kickoff payload through actual worker entry seam (_render_scene_async)
    hydrated_job_ss2 = {
        **kickoff_ss2,
        "id": "job_ss2",
        "job_id": "job_ss2",
        "product_type": "self_shot_scene_change",
        "source_video_local_path": str(dummy_video),
        "project": project_ss2,
    }
    scene_obj_ss2 = SimpleNamespace(
        scene_id=1,
        video_prompt="scene change",
        aspect_ratio="9:16",
        target_duration_sec=5.0,
        _toan_aas_job=hydrated_job_ss2,
    )

    with patch.object(
        video_real_render_connector,
        "_render_selfshot2_controlled_keyframe_image_to_video",
        return_value={
            "ok": True,
            "output_path": str(raw_out),
            "engine_route": "controlled_keyframe_image_to_video",
            "selected_capability": "image_to_video",
        },
    ) as spy_ss2_i2v, patch.object(video_real_render_connector, "ensure_video_output", side_effect=lambda p: p):
        res_worker_ss2 = asyncio.run(
            video_real_render_connector._render_scene_async(
                scene_obj_ss2,
                str(raw_out),
                ["key4u_video", "shopaikey_video"],
            )
        )
        assert spy_ss2_i2v.call_count == 1, "Worker must naturally select _render_selfshot2_controlled_keyframe_image_to_video"
        assert res_worker_ss2["engine_route"] == "controlled_keyframe_image_to_video"

    hydrated_job_ss3 = {
        **kickoff_ss3,
        "id": "job_ss3",
        "job_id": "job_ss3",
        "product_type": "self_shot_cinematic_transform",
        "source_video_local_path": str(dummy_video),
        "project": project_ss3,
    }
    scene_obj_ss3 = SimpleNamespace(
        scene_id=1,
        video_prompt="cinematic transform",
        aspect_ratio="9:16",
        target_duration_sec=5.0,
        _toan_aas_job=hydrated_job_ss3,
    )

    with patch.object(
        video_real_render_connector,
        "_render_selfshot3_controlled_keyframe_image_to_video",
        return_value={
            "ok": True,
            "output_path": str(raw_out),
            "engine_route": "controlled_keyframe_image_to_video",
            "selected_capability": "image_to_video",
        },
    ) as spy_ss3_i2v, patch.object(video_real_render_connector, "ensure_video_output", side_effect=lambda p: p):
        res_worker_ss3 = asyncio.run(
            video_real_render_connector._render_scene_async(
                scene_obj_ss3,
                str(raw_out),
                ["shopaikey_video", "key4u_video"],
            )
        )
        assert spy_ss3_i2v.call_count == 1, "Worker must naturally select _render_selfshot3_controlled_keyframe_image_to_video"
        assert res_worker_ss3["engine_route"] == "controlled_keyframe_image_to_video"


def test_matrix_m_shopaikey_i2v_missing_image_fails_closed_before_http():
    """M: ShopAIKey I2V missing image fails before HTTP (PROVIDER_CALLS=0, NO_CHARGE=True)."""
    from services.video_provider_base import VideoGenerationRequest
    from providers.video_generic_http_provider import (
        VideoProviderContractError,
        build_shopaikey_video_payload,
        GenericHttpVideoProvider,
    )

    req_missing_img = VideoGenerationRequest(
        job_id="job_missing_img",
        product_type="self_shot_scene_change",
        video_flow_type="selfshot2",
        prompt="transform scene",
        image_paths=[],  # Missing image!
        required_capability="image_to_video",
        metadata={
            "selected_model": "veo3.1-fast",
            "required_capability": "image_to_video",
        },
    )
    fake_env = {
        "SHOPAIKEY_VIDEO_ENABLED": "1",
        "SHOPAIKEY_AUTH_HEADER_NAME": "Authorization",
        "SHOPAIKEY_API_KEY": "Bearer sak_test_key",
        "SHOPAIKEY_BASE_URL": "https://api.shopaikey.com",
        "SHOPAIKEY_VIDEO_SUBMIT_URL": "https://api.shopaikey.com/v1/video/create",
        "SHOPAIKEY_VIDEO_STATUS_URL": "https://api.shopaikey.com/v1/video/status/{task_id}",
        "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast",
    }

    with pytest.raises(VideoProviderContractError) as exc_info:
        build_shopaikey_video_payload(req_missing_img, env=fake_env)
    assert exc_info.value.blocker == "provider_image_input_missing_no_charge"
    assert exc_info.value.debug.get("no_charge") is True

    # Also verify via adapter submit_video_job that 0 HTTP calls are made
    adapter = GenericHttpVideoProvider(
        provider_name="shopaikey_video",
        enabled_env="SHOPAIKEY_VIDEO_ENABLED",
        submit_url_env="SHOPAIKEY_VIDEO_SUBMIT_URL",
        poll_url_env="SHOPAIKEY_VIDEO_STATUS_URL",
        auth_header_name_env="SHOPAIKEY_AUTH_HEADER_NAME",
        auth_header_value_env="SHOPAIKEY_API_KEY",
        model_env="SHOPAIKEY_VIDEO_MODEL",
        env=fake_env,
    )
    with patch("urllib.request.urlopen") as spy_http:
        submit_res = adapter.submit_video_job(req_missing_img)
        assert submit_res.ok is False
        assert submit_res.error_code == "provider_image_input_missing_no_charge"
        assert submit_res.raw.get("no_charge") is True
        assert spy_http.call_count == 0, "PROVIDER_CALLS must be 0 when image input is missing"



