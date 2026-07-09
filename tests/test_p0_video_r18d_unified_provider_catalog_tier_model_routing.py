import json
import sqlite3
from pathlib import Path

import pytest

from providers.video_generic_http_provider import build_key4u_video_payload, build_shopaikey_video_payload
from services import remote_worker_api
from services import video_project_queue as queue
from services.video_provider_base import VideoGenerationRequest
from services.video_provider_catalog import (
    CONTRACT_MISSING,
    MODEL_UNKNOWN,
    catalog_status_payload,
    load_product_video_model_routing,
    load_video_provider_catalog,
    resolve_product_video_model,
)


ROOT = Path(__file__).resolve().parents[1]


def _conn(tmp_path: Path):
    conn = sqlite3.connect(tmp_path / "r18d_video_queue.db")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _product_project(conn, *, scene_count: int = 2, tier: int = 300):
    asset_pack = {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "product_type": "video_trend",
        "original_user_prompt": "Video theo trend cho san pham",
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
        "provider_order": "shopaikey_video,key4u_video",
    }
    invoice = {
        **asset_pack,
        "scene_count": scene_count,
        "scene_duration_seconds": 8,
        "duration_seconds": scene_count * 8,
        "package_xu": tier,
        "quality_tier": tier,
        "total_xu": scene_count * 200,
    }
    project = queue.create_video_project(
        conn,
        user_id=1818,
        profile_id="video_trend",
        topic="trend product",
        ratio="9:16",
        asset_pack=asset_pack,
    )
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="draft_invoice",
        invoice_json=invoice,
        scene_count=scene_count,
        prompt_text="make a product trend video",
        total_xu_estimated=scene_count * 200,
        quality_tier=tier,
    )
    return queue.get_video_project(conn, int(project["project_id"]))


def test_catalog_loads_shopaikey_and_key4u_models():
    catalog = load_video_provider_catalog()
    providers = catalog["providers"]
    assert "shopaikey_video" in providers
    assert "key4u_video" in providers
    assert "veo3.1-fast" in providers["shopaikey_video"]["models"]
    assert "veo3.1-pro-4k" in providers["shopaikey_video"]["models"]
    assert "kling-3.0-turbo" in providers["key4u_video"]["models"]
    assert "MiniMax-Hailuo-2.3" in providers["key4u_video"]["models"]


def test_tier_resolution_is_not_single_hardcoded_veo_fast():
    env = {"VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video"}
    low = resolve_product_video_model(tier=200, env=env)
    basic = resolve_product_video_model(tier=300, env=env)
    high = resolve_product_video_model(tier=1500, env=env)
    assert low["ok"] is True
    assert basic["ok"] is True
    assert high["ok"] is True
    assert low["selected_provider"] == "shopaikey_video"
    assert low["selected_model"] in {"grok-video-3", "veo3.1-fast"}
    assert basic["selected_model"] in {"veo3.1-fast-components", "veo3.1-fast"}
    assert high["selected_model"] != "veo3.1-fast"
    assert len({low["selected_model"], basic["selected_model"], high["selected_model"]}) >= 2


def test_env_override_must_exist_and_stay_within_tier_cost_budget():
    env = {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video",
        "SHOPAIKEY_VIDEO_MODEL_BASIC": "veo3.1-pro",
    }
    result = resolve_product_video_model(tier="basic", env=env)
    assert result["ok"] is True
    assert result["selected_provider"] == "shopaikey_video"
    assert result["selected_model"] == "veo3.1-fast"
    assert any(item["reason"] == "model_cost_tier_exceeds_product_tier" for item in result["rejected_models"])


def test_unknown_env_model_is_rejected_and_config_fallback_is_used():
    env = {
        "VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video",
        "SHOPAIKEY_VIDEO_MODEL_BASIC": "unknown-paid-model",
    }
    result = resolve_product_video_model(tier="basic", env=env)
    assert result["ok"] is True
    assert result["selected_model"] != "unknown-paid-model"
    assert any(item["reason"] == MODEL_UNKNOWN for item in result["rejected_models"])


def test_concat_requires_concat_capable_model_then_falls_back():
    catalog = load_video_provider_catalog()
    catalog = json.loads(json.dumps(catalog))
    catalog["providers"]["shopaikey_video"]["models"]["veo3.1-fast"]["supports_concat"] = False
    routing = load_product_video_model_routing()
    routing = json.loads(json.dumps(routing))
    routing["tiers"]["basic"]["preferred"] = [
        {"provider": "shopaikey_video", "model": "veo3.1-fast"},
        {"provider": "key4u_video", "model": "kling-3.0-turbo"},
    ]
    result = resolve_product_video_model(
        tier="basic",
        provider_chain=["shopaikey_video", "key4u_video"],
        catalog=catalog,
        routing=routing,
        env={"KEY4U_KLING_VIDEO_ENDPOINT": "https://api.key4u.shop/kling/v1/videos/text2video"},
        requires_concat=True,
    )
    assert result["ok"] is True
    assert result["selected_provider"] == "key4u_video"
    assert result["selected_model"] == "kling-3.0-turbo"
    assert any(item["reason"] == "model_does_not_support_concat" for item in result["rejected_models"])


def test_payload_uses_persisted_model_and_keeps_8s_small_clip_contract():
    request = VideoGenerationRequest(
        job_id="218-1",
        product_type="video_trend",
        prompt="A polished 8 second product trend clip.",
        scenes=[{"scene_id": 1, "prompt": "scene prompt"}],
        storyboard=[{"scene_id": 1}],
        image_paths=["/tmp/image.png"],
        source_video_path="/tmp/source.mp4",
        ratio="9:16",
        duration_seconds=16,
        metadata={
            "product_video": True,
            "scene_index": 1,
            "clip_index": 1,
            "orchestration_mode": "per_scene_8s",
            "render_pipeline_mode": "historical_multi_clip_concat",
            "selected_provider": "shopaikey_video",
            "selected_model": "veo3.1-pro",
            "provider_model_map": {"shopaikey_video": "veo3.1-pro"},
        },
        required_capability="text_to_video",
    )
    payload = build_shopaikey_video_payload(
        request,
        {
            "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast",
            "SHOPAIKEY_VIDEO_SMALL_CLIP_SECONDS": "8",
        },
    )
    assert payload["model"] == "veo3.1-pro"
    assert payload["duration"] == 8
    assert payload["duration_seconds"] == 8
    assert "scenes" not in payload
    assert "storyboard" not in payload
    assert "image_paths" not in payload
    assert payload["metadata"]["model_used_in_payload"] == "veo3.1-pro"
    assert payload["metadata"]["contract_validation_status"] == "ok"


def test_unknown_direct_payload_model_blocks_before_submit():
    request = VideoGenerationRequest(
        job_id="218-1",
        product_type="video_trend",
        prompt="A polished product trend clip.",
        ratio="9:16",
        duration_seconds=8,
        metadata={"product_video": True, "scene_index": 1, "clip_index": 1},
        required_capability="text_to_video",
    )
    with pytest.raises(Exception) as exc_info:
        build_shopaikey_video_payload(request, {"SHOPAIKEY_VIDEO_MODEL": "unknown-paid-model"})
    assert MODEL_UNKNOWN in str(exc_info.value)


def test_key4u_payload_uses_provider_model_map_and_removes_scene_fields():
    request = VideoGenerationRequest(
        job_id="218-1",
        product_type="video_trend",
        prompt="A polished 8 second product trend clip.",
        scenes=[{"scene_id": 1}],
        storyboard=[{"scene_id": 1}],
        image_paths=["/tmp/image.png"],
        source_video_path="/tmp/source.mp4",
        ratio="9:16",
        duration_seconds=8,
        metadata={
            "product_video": True,
            "scene_index": 1,
            "clip_index": 1,
            "orchestration_mode": "per_scene_8s",
            "render_pipeline_mode": "historical_multi_clip_concat",
            "provider_model_map": {"key4u_video": "kling-3.0-turbo"},
        },
        required_capability="text_to_video",
    )
    payload = build_key4u_video_payload(
        request,
        {
            "KEY4U_VIDEO_MODEL": "veo3.1-pro",
            "KEY4U_KLING_VIDEO_ENDPOINT": "https://api.key4u.shop/kling/v1/videos/text2video",
        },
    )
    assert payload["model"] == "kling-3.0-turbo"
    assert "scenes" not in payload
    assert "storyboard" not in payload
    assert "image_paths" not in payload
    assert payload["metadata"]["selected_family"] == "kling"


def test_confirm_persists_selected_model_into_job_and_scene_tasks(tmp_path):
    conn = _conn(tmp_path)
    project = _product_project(conn, scene_count=2, tier=300)
    result = queue.confirm_video_project_invoice(conn, project_id=int(project["project_id"]), user_id=int(project["user_id"]))
    payload = json.loads(str(result["job"]["result_json"] or "{}"))
    assert payload["model_routing_ok"] is True
    assert payload["selected_provider"] == "shopaikey_video"
    assert payload["selected_model"]
    assert payload["selected_family"]
    assert payload["render_pipeline_mode"] == "historical_multi_clip_concat"
    assert payload["supports_concat"] is True
    assert payload["contract_validation_status"] == "ok"
    assert payload["provider_scene_tasks"][0]["selected_model"] == payload["selected_model"]


def test_worker_payload_preserves_persisted_selected_model():
    persisted = {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "selected_provider": "key4u_video",
        "selected_model": "kling-3.0-turbo",
        "selected_family": "kling",
        "selected_model_source": "config:tier:basic",
        "selected_payload_adapter": "key4u_kling_small_clip",
        "provider_model_map": {"key4u_video": "kling-3.0-turbo"},
        "provider_scene_tasks": [],
        "orchestration_mode": "per_scene_8s",
    }
    hydrated = {
        "id": 218,
        "job_id": 218,
        "job_type": "video_render",
        "status": "queued",
        "result_json": json.dumps(persisted),
        "project": {
            "project_id": 218,
            "user_id": 1818,
            "profile_id": "video_trend",
            "topic": "trend product",
            "prompt_text": "make a product trend video",
            "ratio": "9:16",
            "scene_count": 2,
            "asset_pack_json": json.dumps({"source": "product_video", "render_mode": "real", "provider_call": True, "public_user": True}),
            "invoice_json": json.dumps({"source": "product_video", "render_mode": "real", "provider_call": True, "public_user": True, "scene_count": 2}),
            "addon_plan_json": "{}",
        },
    }
    payload = remote_worker_api.build_worker_job_payload(hydrated)
    assert payload["selected_provider"] == "key4u_video"
    assert payload["selected_model"] == "kling-3.0-turbo"
    assert payload["provider_model_map"]["key4u_video"] == "kling-3.0-turbo"
    assert payload["provider_scene_tasks"][0]["selected_model"] == "kling-3.0-turbo"


def test_catalog_status_exposes_counts_and_degenerated_warning():
    status = catalog_status_payload(
        {
            "VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video",
            "SHOPAIKEY_VIDEO_MODEL_LOW": "veo3.1-fast",
            "SHOPAIKEY_VIDEO_MODEL_BASIC": "veo3.1-fast",
            "SHOPAIKEY_VIDEO_MODEL_COMMON": "veo3.1-fast",
            "SHOPAIKEY_VIDEO_MODEL_ADVANCED": "veo3.1-fast",
            "SHOPAIKEY_VIDEO_MODEL_STANDARD": "veo3.1-fast",
            "SHOPAIKEY_VIDEO_MODEL_HIGH": "veo3.1-fast",
        }
    )
    assert status["catalog_loaded"] is True
    assert status["routing_enabled"] is True
    assert status["model_count"] >= 10
    assert status["warning"] == "MODEL_ROUTING_DEGENERATED_SINGLE_MODEL"


def test_debug_status_and_admin_canary_source_contract():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    assert "Product Video model catalog" in source
    assert "selected model:" in source
    assert "model used in payload:" in source
    assert 'CommandHandler("video_provider_canary", cmd_video_provider_smoke)' in source
    assert "requested_model" in source
    assert "small_8s" in source


def test_no_real_provider_calls_in_r18d_tests():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "run_provider" + "_generation(",
        "submit_video" + "_job(",
    )
    assert all(token not in source for token in forbidden)
