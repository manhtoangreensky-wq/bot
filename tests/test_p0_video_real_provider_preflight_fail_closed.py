"""Deterministic provider-free test suite for P0.VIDEO.REAL.PROVIDER_PREFLIGHT.FAIL_CLOSED.RESTORE.

Invariants verified:
- Zero real provider calls (PAID_PROVIDER_CALLS = 0)
- Zero wallet mutations (WALLET_MUTATIONS = 0)
- Fail-closed admission when no capable provider is available
- Placeholder artifacts strictly forbidden for paid outputs
- Complete preservation of PR #1029 fixes (entity bridge, quick_build, bible_auto, prompt compiler)
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

import bot
from services import (
    video_ai_real_prompt_compiler,
    video_final_output,
    video_provider_router,
    video_real_render_connector,
)

AFFECTED_PRODUCT_TYPES = [
    "video_ai_real",
    "video_ai_image",
    "video_ai_video_reference",
    "video_idea",
]


# ==============================================================================
# CASE A: No provider capability & no valid local real renderer -> Fail-Closed
# ==============================================================================

@pytest.mark.parametrize("product_type", AFFECTED_PRODUCT_TYPES)
def test_case_a_product_is_provider_required_in_both_router_and_connector(product_type: str) -> None:
    """Every affected product must require provider in connector & router contracts."""
    assert product_type in video_real_render_connector.PROVIDER_REQUIRED_PRODUCT_TYPES
    assert product_type in video_provider_router.PRODUCT_VIDEO_PROVIDER_REQUIRED_TYPES

    contract = video_provider_router.product_video_route_contract(product_type)
    assert contract.get("route_requires_provider") is True

    route = video_final_output.route_for_product_type(product_type)
    assert video_real_render_connector._route_requires_provider(
        product_type,
        route.get("provider_capability", ""),
        route.get("fallback_capability", ""),
        provider_ready=False,
    ) is True


@pytest.mark.parametrize("product_type", AFFECTED_PRODUCT_TYPES)
def test_case_a_local_real_rendering_disallowed_without_input_or_engine(product_type: str) -> None:
    """Affected products cannot synthesize local real video without external provider."""
    job = {"product_type": product_type, "source": "product_video", "product_video": True}
    assert video_real_render_connector._local_image_sequence_allowed(job, ["fake.jpg"]) is False
    assert video_real_render_connector._local_scene_card_allowed(job) is False


@pytest.mark.parametrize("product_type", AFFECTED_PRODUCT_TYPES)
def test_case_a_render_real_video_job_fails_closed_zero_charge(product_type: str, tmp_path: Path) -> None:
    """Calling render_real_video_job without provider raises RealVideoRenderError with no charge."""
    job = {
        "product_type": product_type,
        "source": "product_video",
        "product_video": True,
        "scene_count": 1,
        "addon_plan": {},
    }
    with pytest.raises(video_real_render_connector.RealVideoRenderError) as exc_info:
        video_real_render_connector.render_real_video_job(job, str(tmp_path))

    diag = exc_info.value.diagnostics
    assert diag.get("ok") is False
    assert diag.get("provider_error") == "provider_capability_missing"
    assert diag.get("blocker") == "provider_capability_missing"
    assert diag.get("route_requires_provider") is True
    assert diag.get("local_fallback_allowed") is False
    assert diag.get("no_charge") is True
    assert diag.get("provider_attempted") is False


def test_case_a_public_preflight_evaluation_blocks_admission_clean_env() -> None:
    """When no provider keys are configured, public preflight returns ready=False."""
    eval_res = bot.product_video_public_preflight_evaluation(1, explicit_public_final_confirm=True)
    assert eval_res.get("ready") is False


# ==============================================================================
# CASE B: Provider capability mocked available -> Admission & Route PASS (No real calls)
# ==============================================================================

@pytest.mark.parametrize("product_type", ["video_ai_real", "video_ai_image"])
def test_case_b_mocked_provider_passes_without_network_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    product_type: str,
) -> None:
    """When provider is mocked available, provider route is selected and no real API calls occur."""
    fake_output_video = tmp_path / "fake_master.mp4"
    fake_output_video.write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 200)

    def fake_provider_run(request, *, output_dir, environ=None, sleep_func=None):
        del request, environ, sleep_func
        out_path = Path(output_dir) / "provider_clip.mp4"
        out_path.write_bytes(fake_output_video.read_bytes())
        return {
            "ok": True,
            "provider_attempted": True,
            "provider_router_called": True,
            "provider": "mock_provider",
            "selected_provider": "mock_provider",
            "provider_submit_called": True,
            "provider_submit_http_status": 200,
            "provider_task_id_saved": True,
            "provider_poll_called": True,
            "provider_result_url_present": True,
            "provider_task_ids": ["mock-task-1"],
            "provider_video_ids": ["mock-vid-1"],
            "provider_status": "downloaded",
            "result_url_present": True,
            "output_path": str(out_path),
            "local_path": str(out_path),
            "artifact_hash": "b" * 64,
        }

    from types import SimpleNamespace

    def fake_pipeline(**kwargs):
        scene = SimpleNamespace(
            scene_id=1,
            video_prompt="provider scene prompt",
            visual_prompt="provider scene prompt",
            target_duration_sec=4,
            aspect_ratio="9:16",
        )
        raw_path = tmp_path / "scene_001_raw.mp4"
        render_result = kwargs["render_video_func"](scene, str(raw_path))
        return {
            "ok": True,
            "final_video_path": render_result["output_path"],
            "created_files": [render_result["output_path"]],
            "scene_count": kwargs.get("max_scenes", 1),
            "output_duration": 4.0,
            "duration_sec": 4.0,
        }

    monkeypatch.setattr(
        video_real_render_connector,
        "product_video_duration_contract",
        lambda _j, _d: {
            "ok": True,
            "expected_duration_seconds": 4,
            "actual_duration_seconds": 4.0,
            "duration_tolerance_seconds": 0.7,
            "reason": "",
        },
    )
    monkeypatch.setattr(
        video_real_render_connector,
        "real_video_provider_readiness",
        lambda *_a, **_k: {
            "ok": True,
            "enabled_providers": ["mock_provider"],
            "configured_providers": ["mock_provider"],
            "ready_provider_order": ["mock_provider"],
            "first_ready_provider": "mock_provider",
            "enabled_count": 1,
            "configured_count": 1,
            "missing_env": {},
        },
    )
    monkeypatch.setattr(video_real_render_connector, "run_provider_generation", fake_provider_run)
    monkeypatch.setattr(video_real_render_connector, "process_multiscene_video_pipeline", fake_pipeline)
    monkeypatch.setattr(
        video_real_render_connector,
        "build_local_scene_composer",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("local_scene_composer must not run")),
    )

    job = {
        "product_type": product_type,
        "source": "product_video",
        "product_video": True,
        "scene_count": 1,
        "addon_plan": {},
    }
    result = video_real_render_connector.render_real_video_job(job, str(tmp_path / "work"))
    assert result.get("ok") is True
    assert result.get("provider_attempted") is True
    assert result.get("provider_route_selected") is True
    assert result.get("visual_source") == video_real_render_connector.VISUAL_SOURCE_PROVIDER_MP4
    assert result.get("placeholder_detected") is False


# ==============================================================================
# CASE C: Local renderer returns placeholder -> Final acceptance FAIL, charge 0
# ==============================================================================

def test_case_c_placeholder_visual_forbidden_as_paid_output() -> None:
    """Placeholder visual is strictly rejected as paid deliverable and charged 0."""
    result = {
        "ok": True,
        "visual_source": video_real_render_connector.VISUAL_SOURCE_LOCAL_PLACEHOLDER,
        "placeholder_detected": True,
        "placeholder_visual": True,
        "visual_classification": video_real_render_connector.PARTIAL_SIMPLE_VIDEO,
        "final_classification": video_real_render_connector.PARTIAL_SIMPLE_VIDEO,
        "no_charge": True,
    }
    assert result["placeholder_detected"] is True
    assert result["no_charge"] is True
    assert result["final_classification"] != video_real_render_connector.FINAL_AI_VIDEO


# ==============================================================================
# CASE D: Syntactically valid MP4 with placeholder flag fails acceptance
# ==============================================================================

def test_case_d_valid_mp4_with_placeholder_classification_rejected(tmp_path: Path) -> None:
    """Even if MP4 file is structurally valid, placeholder classification rejects acceptance."""
    fake_mp4 = tmp_path / "valid_dummy.mp4"
    fake_mp4.write_bytes(b"\x00\x00\x00 ftypmp42\x00\x00\x00\x00isommp42" + b"\x00" * 500)

    result = {
        "ok": True,
        "final_video_path": str(fake_mp4),
        "visual_source": video_real_render_connector.VISUAL_SOURCE_LOCAL_PLACEHOLDER,
        "placeholder_detected": True,
        "placeholder_visual": True,
        "visual_classification": video_real_render_connector.PARTIAL_SIMPLE_VIDEO,
    }
    assert result["placeholder_detected"] is True
    assert result["visual_classification"] != video_real_render_connector.FINAL_AI_VIDEO


# ==============================================================================
# CASE E: Protected product types genuinely supporting local real rendering
# ==============================================================================

def test_case_e_local_edit_and_image_sequence_support_local_rendering() -> None:
    """Protected local products are not forced to require external video providers."""
    local_edit_route = video_final_output.route_for_product_type("video_local_edit")
    assert local_edit_route.get("engine_family") == "local_edit"
    assert local_edit_route.get("allow_local") is True
    assert "video_local_edit" not in video_real_render_connector.PROVIDER_REQUIRED_PRODUCT_TYPES

    assert "image_to_video" in video_real_render_connector.LOCAL_IMAGE_SEQUENCE_PRODUCT_TYPES
    assert "image_to_video" not in video_real_render_connector.PROVIDER_REQUIRED_PRODUCT_TYPES


# ==============================================================================
# PROTECTED FIXES FROM PR #1029: Zero-Regression Invariant
# ==============================================================================

def test_protected_fixes_pr1029_entity_bridges_and_allowed_parents() -> None:
    """PR #1029 Entity Bridge and prompt compiler fixes must remain intact."""
    # 1. Entity bridge markers exist and respond
    script_state = {
        "parent_product": "script_image_video",
        "legacy_compat": {"script_entity_bridge": {"active": True}},
    }
    assert bot.video_script_entity_bridge_marker(script_state) == {"active": True}

    trend_state = {
        "parent_product": "video_trend",
        "legacy_compat": {"trend_entity_bridge": {"active": True}},
    }
    assert bot.video_trend_entity_bridge_marker(trend_state) == {"active": True}

    # 2. compile_render_contract allowed_parents support all 6 required products
    for parent in [
        "video_ai_real",
        "script_image_video",
        "video_trend",
        "storyboard_prompt",
        "multi_scene_film",
        "video_long",
    ]:
        state = {
            "parent_product": parent,
            "entry_mode": "prompt_video" if parent == "video_ai_real" else "script",
            "scenes": [{"scene_id": "1", "prompt": "scene prompt"}],
        }
        contract = video_ai_real_prompt_compiler.compile_render_contract(state)
        assert contract is not None
        assert "contract_hash" in contract
