import json
from pathlib import Path

import pytest

from providers.key4u_provider import config_from_env
from providers.video_generic_http_provider import (
    GenericHttpVideoProvider,
    _key4u_wire_payload,
)
from services import video_ai_real_pricing, video_provider_router
from services.video_provider_base import VideoGenerationRequest
from services.video_provider_catalog import (
    model_metadata_from_resolution,
    resolve_product_video_model,
)


KEY4U_VN = "https://api.key4u.vn"
PRICE_ROUTE_MAP = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "config"
        / "product_video_price_route_map_20260827.json"
    ).read_text(encoding="utf-8")
)


def _clear_key4u_base_env(monkeypatch):
    for name in (
        "KEY4U_API_BASE",
        "KEY4U_BASE_URL",
        "KEY4U_OPENAI_BASE_URL",
        "KEY4U_MINIMAX_BASE",
        "KEY4U_MINIMAX_TTS_BASE",
        "KEY4U_SUNO_BASE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_key4u_active_defaults_and_video_adapter_use_vn(monkeypatch):
    _clear_key4u_base_env(monkeypatch)

    config = config_from_env()
    adapter = video_provider_router._generic_adapter_for(
        "key4u_video",
        {
            "KEY4U_API_KEY": "test-key",
            "KEY4U_VIDEO_MODEL": "veo_3_1-fast",
        },
    )

    assert config.base_url == KEY4U_VN
    assert config.openai_base_url == f"{KEY4U_VN}/v1"
    assert config.minimax_base_url == f"{KEY4U_VN}/minimax"
    assert config.minimax_tts_base_url == f"{KEY4U_VN}/minimax"
    assert config.suno_base_url == f"{KEY4U_VN}/suno"
    assert adapter._submit_url() == f"{KEY4U_VN}/v1/video/create"
    assert adapter._poll_url() == f"{KEY4U_VN}/v1/video/query?id={{task_id}}"


def test_common_tier_uses_new_live_cost_order():
    price_row = next(
        row
        for row in video_ai_real_pricing.model_catalog()
        if row["key"] == "veo31_fast_8"
    )
    costs = {
        item["provider"]: item["usd_per_scene"]
        for item in price_row["provider_costs"]
    }
    result = resolve_product_video_model(
        tier=400,
        provider_chain=["shopaikey_video", "key4u_video"],
        scene_count=2,
        required_capability="text_to_video_or_scene_video",
        requires_concat=True,
        env={
            "KEY4U_VEO_VIDEO_ENDPOINT": f"{KEY4U_VN}/v1/video/create",
            "KEY4U_VEO_VIDEO_POLL_URL": f"{KEY4U_VN}/v1/videos/{{task_id}}",
            "KEY4U_KLING_VIDEO_ENDPOINT": f"{KEY4U_VN}/kling/v1/videos/text2video",
            "KEY4U_KLING_VIDEO_POLL_URL": f"{KEY4U_VN}/kling/v1/videos/text2video/{{task_id}}",
        },
    )

    assert result["ok"] is True
    assert costs["shopaikey"] == 0.7
    assert costs["key4u"] == 3.52512
    assert price_row["provider_priority"] == ["shopaikey", "key4u"]
    assert price_row["legacy_provider_costs_are_runtime_authority"] is False
    assert price_row["runtime_route_source"] == (
        "config/product_video_price_route_map_20260827.json"
    )
    assert result["selected_provider"] == "shopaikey_video"
    assert result["selected_model"] == "veo3.1-fast"
    assert result["selected_cost_tier"] == "low"
    assert result["selected_role"] == "primary"
    assert result["provider_model_map"] == {
        "shopaikey_video": "veo3.1-fast",
        "key4u_video": "veo_3_1-fast",
    }
    candidates = result["candidate_list_compact"]
    assert [(item["provider"], item["role"], item["cost_tier"]) for item in candidates] == [
        ("shopaikey_video", "primary", "low"),
        ("key4u_video", "fallback", "common"),
    ]


def test_saved_price_route_map_matches_current_customer_prices_and_runtime_order():
    assert PRICE_ROUTE_MAP["provider_sources"]["key4u"]["family_endpoint_types"] == {
        "veo": {"id": "gygkmi", "method": "POST", "path": "/v1/videos"},
        "kling_text": {
            "id": "m0kp1x",
            "method": "POST",
            "path": "/kling/v1/videos/text2video",
        },
        "hailuo": {
            "id": "1au654",
            "method": "POST",
            "path": "/minimax/v1/video_generation",
        },
    }
    rows = PRICE_ROUTE_MAP["tiers_sorted_by_customer_price"]
    assert [row["customer_unit_xu"] for row in rows] == sorted(
        row["customer_unit_xu"] for row in rows
    )
    assert [row["customer_unit_xu"] for row in rows] == [
        80,
        110,
        160,
        200,
        220,
        220,
        370,
        370,
        1260,
        2360,
    ]
    assert [row["label"] for row in rows] == [
        "Nhanh gon",
        "Chuyen dong on dinh",
        "Chuyen dong co am thanh",
        "Can bang ro net",
        "Tieu chuan co am thanh",
        "Canh dai co am thanh",
        "Cao cap linh hoat",
        "Dien xuat chan that",
        "Da goc may",
        "Dien anh nhieu canh",
    ]

    quality = {
        row["tier_id"]: row
        for row in video_ai_real_pricing.public_quality_catalog()
    }
    for saved in rows:
        tier_id = saved["tier_id"]
        assert quality[tier_id]["unit_xu"] == saved["customer_unit_xu"]
        quote = video_ai_real_pricing.video_multiscene_price(
            quality[tier_id]["unit_xu"],
            2,
        )
        assert quote["total_xu"] == saved["two_scene_quote"]["total_xu"]

        resolved = resolve_product_video_model(
            tier=tier_id,
            scene_count=2,
            required_capability="text_to_video",
            requires_concat=True,
            env={
                "KEY4U_VIDEO_ENDPOINT": f"{KEY4U_VN}/v1/video/create",
                "KEY4U_VIDEO_POLL_ENDPOINT": f"{KEY4U_VN}/v1/video/query?id={{task_id}}",
                "KEY4U_VEO_VIDEO_ENDPOINT": f"{KEY4U_VN}/v1/videos",
                "KEY4U_VEO_VIDEO_POLL_URL": f"{KEY4U_VN}/v1/videos/{{task_id}}",
                "KEY4U_KLING_VIDEO_ENDPOINT": f"{KEY4U_VN}/kling/v1/videos/text2video",
                "KEY4U_KLING_VIDEO_POLL_URL": f"{KEY4U_VN}/kling/v1/videos/text2video/{{task_id}}",
                "KEY4U_HAILUO_VIDEO_ENDPOINT": f"{KEY4U_VN}/minimax/v1/video_generation",
                "KEY4U_HAILUO_VIDEO_POLL_URL": f"{KEY4U_VN}/minimax/v1/query/video_generation?task_id={{task_id}}",
            },
        )
        assert resolved["ok"] is True
        selected = (
            f'{resolved["selected_provider"]}:{resolved["selected_model"]}'
        )
        assert selected == saved["runtime_order"][0]
        assert list(
            f"{provider}:{model}"
            for provider, model in resolved["provider_model_map"].items()
        ) == saved["runtime_order"]


def _key4u_provider(env):
    return GenericHttpVideoProvider(
        provider_name="key4u_video",
        enabled_env="KEY4U_VIDEO_ENABLED",
        submit_url_env="KEY4U_VIDEO_SUBMIT_URL",
        poll_url_env="KEY4U_VIDEO_POLL_URL",
        auth_header_name_env="KEY4U_VIDEO_AUTH_HEADER_NAME",
        auth_header_value_env="KEY4U_VIDEO_AUTH_HEADER_VALUE",
        result_field_env="KEY4U_VIDEO_RESULT_FIELD",
        model_env="KEY4U_VIDEO_MODEL",
        capabilities_env="KEY4U_VIDEO_CAPABILITIES",
        environ=env,
    )


def _key4u_env(**extra):
    env = {
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_SUBMIT_URL": f"{KEY4U_VN}/v1/video/create",
        "KEY4U_VIDEO_POLL_URL": f"{KEY4U_VN}/v1/video/query?id={{task_id}}",
        "KEY4U_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer test-key",
        "KEY4U_VIDEO_MODEL": "veo_3_1-fast",
        "KEY4U_VIDEO_CAPABILITIES": "text_to_video,scene_video,multi_scene_video",
    }
    env.update(extra)
    return env


def _request_for_resolution(resolution, *, seconds, prompt="Product video scene."):
    return VideoGenerationRequest(
        job_id="pv-price-route-scene",
        product_type="video_trend",
        prompt=prompt,
        ratio="9:16",
        duration_seconds=seconds,
        required_capability="text_to_video",
        metadata=model_metadata_from_resolution(resolution),
    )


def test_key4u_veo_normalizes_legacy_videos_endpoint_to_official_json_contract(monkeypatch):
    env = _key4u_env(
        KEY4U_VEO_VIDEO_ENDPOINT=f"{KEY4U_VN}/v1/videos",
        KEY4U_VEO_VIDEO_POLL_URL=f"{KEY4U_VN}/v1/videos/{{task_id}}",
    )
    resolution = resolve_product_video_model(
        tier=400,
        provider_chain=["key4u_video"],
        scene_count=2,
        required_capability="text_to_video",
        requires_concat=True,
        env=env,
    )
    provider = _key4u_provider(env)
    captured = {}

    def fake_json(url, payload=None, **kwargs):
        captured.update({"url": url, "payload": payload, "method": kwargs.get("method", "POST")})
        return {
            "ok": True,
            "status_code": 200,
            "body": {"id": "video_test_123", "status": "queued"},
            "response_shape": {"type": "dict"},
        }

    monkeypatch.setattr(provider, "_open_json", fake_json)
    monkeypatch.setattr(
        provider,
        "_open_multipart_form",
        lambda *_args, **_kwargs: pytest.fail("legacy /v1/videos must normalize to official JSON contract"),
    )
    result = provider.submit_video_job(_request_for_resolution(resolution, seconds=8))

    assert result.ok is True
    assert resolution["provider_endpoint_source"] == (
        "normalized:KEY4U_VEO_VIDEO_ENDPOINT"
    )
    assert resolution["provider_submit_url_override"] == (
        f"{KEY4U_VN}/v1/videos/generations"
    )
    assert captured == {
        "url": f"{KEY4U_VN}/v1/videos/generations",
        "payload": {
            "model": "veo_3_1-fast",
            "prompt": "Product video scene.",
            "resolution": "1080p",
            "aspect_ratio": "9:16",
            "duration": 8,
        },
        "method": "POST",
    }
    assert result.raw["provider_poll_url_override"] == f"{KEY4U_VN}/v1/videos/{{task_id}}"


def test_key4u_veo_keeps_custom_proxy_videos_endpoint_override(monkeypatch):
    proxy = "https://video-proxy.example.com"
    env = _key4u_env(
        KEY4U_VEO_VIDEO_ENDPOINT=f"{proxy}/v1/videos",
        KEY4U_VEO_VIDEO_POLL_URL=f"{proxy}/v1/videos/{{task_id}}",
    )
    resolution = resolve_product_video_model(
        tier=400,
        provider_chain=["key4u_video"],
        scene_count=2,
        required_capability="text_to_video",
        requires_concat=True,
        env=env,
    )
    provider = _key4u_provider(env)
    captured = {}

    def fake_multipart(url, fields, **_kwargs):
        captured.update({"url": url, "fields": fields})
        return {
            "ok": True,
            "status_code": 200,
            "body": {"id": "custom_proxy_task", "status": "queued"},
            "response_shape": {"type": "dict"},
        }

    monkeypatch.setattr(provider, "_open_multipart_form", fake_multipart)
    result = provider.submit_video_job(
        _request_for_resolution(resolution, seconds=8)
    )

    assert result.ok is True
    assert resolution["provider_endpoint_source"] == "KEY4U_VEO_VIDEO_ENDPOINT"
    assert resolution["provider_submit_url_override"] == f"{proxy}/v1/videos"
    assert captured["url"] == f"{proxy}/v1/videos"
    assert captured["fields"]["model"] == "veo_3_1-fast"


def test_key4u_veo_derives_current_official_generation_contract_without_new_env():
    env = _key4u_env(KEY4U_BASE_URL=KEY4U_VN)

    resolution = resolve_product_video_model(
        tier=400,
        provider_chain=["key4u_video"],
        scene_count=2,
        required_capability="text_to_video",
        requires_concat=True,
        env=env,
    )

    assert resolution["ok"] is True
    assert resolution["selected_provider"] == "key4u_video"
    assert resolution["selected_model"] == "veo_3_1-fast"
    assert resolution["provider_interface"] == "key4u_google_veo_exclusive"
    assert resolution["provider_endpoint_source"] == (
        "derived:key4u_official_videos_generations"
    )
    assert resolution["provider_submit_url_override"] == (
        f"{KEY4U_VN}/v1/videos/generations"
    )
    assert resolution["provider_poll_url_override"] == (
        f"{KEY4U_VN}/v1/videos/{{task_id}}"
    )
    assert resolution["contract_validation_status"] == "ok"
    assert resolution["submit_skipped_due_to_contract"] is False


def test_key4u_veo_does_not_derive_official_endpoint_without_auth():
    resolution = resolve_product_video_model(
        tier=400,
        provider_chain=["key4u_video"],
        scene_count=2,
        required_capability="text_to_video",
        requires_concat=True,
        env={"KEY4U_BASE_URL": KEY4U_VN},
    )

    assert resolution["ok"] is False
    assert resolution.get("provider_submit_url_override", "") == ""
    assert resolution["contract_block_reason"] == (
        "key4u_model_contract_missing_no_charge"
    )


def test_key4u_veo_derived_official_contract_uses_json_wire_payload(monkeypatch):
    env = _key4u_env(KEY4U_BASE_URL=KEY4U_VN)
    resolution = resolve_product_video_model(
        tier=400,
        provider_chain=["key4u_video"],
        scene_count=2,
        required_capability="text_to_video",
        requires_concat=True,
        env=env,
    )
    provider = _key4u_provider(env)
    captured = {}

    def fake_json(url, payload=None, **kwargs):
        captured.update({"url": url, "payload": payload, "method": kwargs.get("method", "POST")})
        return {
            "ok": True,
            "status_code": 200,
            "body": {"id": "video_test_derived_123", "status": "queued"},
            "response_shape": {"type": "dict"},
        }

    monkeypatch.setattr(provider, "_open_json", fake_json)
    monkeypatch.setattr(
        provider,
        "_open_multipart_form",
        lambda *_args, **_kwargs: pytest.fail("derived official contract must use JSON"),
    )

    result = provider.submit_video_job(
        _request_for_resolution(resolution, seconds=8)
    )

    assert result.ok is True
    assert captured == {
        "url": f"{KEY4U_VN}/v1/videos/generations",
        "payload": {
            "model": "veo_3_1-fast",
            "prompt": "Product video scene.",
            "resolution": "1080p",
            "aspect_ratio": "9:16",
            "duration": 8,
        },
        "method": "POST",
    }
    assert result.raw["provider_poll_url_override"] == (
        f"{KEY4U_VN}/v1/videos/{{task_id}}"
    )
    assert result.raw["provider_http_request_sent"] is True
    assert result.raw["submit_http_status"] == 200


def test_key4u_kling_wire_payload_is_family_exact(monkeypatch):
    env = _key4u_env(
        KEY4U_KLING_VIDEO_ENDPOINT=f"{KEY4U_VN}/kling/v1/videos/text2video",
        KEY4U_KLING_VIDEO_POLL_URL=f"{KEY4U_VN}/kling/v1/videos/text2video/{{task_id}}",
    )
    resolution = resolve_product_video_model(
        tier=700,
        provider_chain=["key4u_video"],
        scene_count=2,
        required_capability="text_to_video",
        requires_concat=True,
        env=env,
    )
    provider = _key4u_provider(env)
    captured = {}

    def fake_json(url, payload=None, **kwargs):
        captured.update({"url": url, "payload": payload})
        return {
            "ok": True,
            "status_code": 200,
            "body": {"code": 0, "data": {"task_id": "kling_task_123", "task_status": "submitted"}},
            "response_shape": {"type": "dict"},
        }

    monkeypatch.setattr(provider, "_open_json", fake_json)
    result = provider.submit_video_job(
        _request_for_resolution(
            resolution,
            seconds=15,
            prompt="A continuous cinematic long take with natural dialogue.",
        )
    )

    assert result.ok is True
    assert captured == {
        "url": f"{KEY4U_VN}/kling/v1/videos/text2video",
        "payload": {
            "model_name": "kling-v3",
            "prompt": "A continuous cinematic long take with natural dialogue.",
            "negative_prompt": "",
            "cfg_scale": 0.5,
            "mode": "pro",
            "aspect_ratio": "9:16",
            "duration": 15,
            "callback_url": "",
            "sound": "on",
        },
    }


def test_key4u_kling_wire_payload_maps_disabled_audio_to_vendor_off_enum():
    payload = {
        "prompt": "Silent controlled product rotation.",
        "duration": 5,
        "sound": False,
        "metadata": {
            "selected_family": "kling",
            "selected_request_defaults": {
                "model_name": "kling-v3",
                "mode": "std",
                "sound": False,
            },
        },
    }

    assert _key4u_wire_payload(payload)["sound"] == "off"


def test_key4u_hailuo_wire_payload_and_query_url_are_family_exact(monkeypatch):
    env = _key4u_env(
        KEY4U_HAILUO_VIDEO_ENDPOINT=f"{KEY4U_VN}/minimax/v1/video_generation",
        KEY4U_HAILUO_VIDEO_POLL_URL=f"{KEY4U_VN}/minimax/v1/query/video_generation?task_id={{task_id}}",
    )
    resolution = resolve_product_video_model(
        tier=1000,
        provider_chain=["key4u_video"],
        scene_count=2,
        required_capability="text_to_video",
        requires_concat=True,
        env=env,
    )
    provider = _key4u_provider(env)
    captured = {}

    def fake_json(url, payload=None, **kwargs):
        captured.update({"url": url, "payload": payload})
        return {
            "ok": True,
            "status_code": 200,
            "body": {"task_id": "306792606023824", "base_resp": {"status_code": 0}},
            "response_shape": {"type": "dict"},
        }

    monkeypatch.setattr(provider, "_open_json", fake_json)
    result = provider.submit_video_job(_request_for_resolution(resolution, seconds=6))

    assert result.ok is True
    assert captured == {
        "url": f"{KEY4U_VN}/minimax/v1/video_generation",
        "payload": {
            "model": "MiniMax-Hailuo-2.3",
            "prompt": "Product video scene.",
            "duration": 6,
            "resolution": "768P",
        },
    }
    assert result.raw["provider_poll_url_override"] == (
        f"{KEY4U_VN}/minimax/v1/query/video_generation?task_id={{task_id}}"
    )


def test_key4u_poll_override_is_used_for_family_task(monkeypatch):
    provider = _key4u_provider(_key4u_env())
    captured = {}

    def fake_json(url, payload=None, **kwargs):
        captured["url"] = url
        return {
            "ok": True,
            "status_code": 200,
            "body": {"code": 0, "data": {"task_status": "processing", "progress": "30%"}},
            "response_shape": {"type": "dict"},
        }

    monkeypatch.setattr(provider, "_open_json", fake_json)
    result = provider.poll_video_job(
        "kling_task_123",
        poll_url_override=f"{KEY4U_VN}/kling/v1/videos/text2video/{{task_id}}",
    )

    assert result.ok is True
    assert result.status == "running"
    assert captured["url"] == f"{KEY4U_VN}/kling/v1/videos/text2video/kling_task_123"


def test_shopaikey_terminal_quota_payload_preserves_real_blocker(monkeypatch):
    provider = GenericHttpVideoProvider(
        provider_name="shopaikey_video",
        enabled_env="SHOPAIKEY_VIDEO_ENABLED",
        submit_url_env="SHOPAIKEY_VIDEO_SUBMIT_URL",
        poll_url_env="SHOPAIKEY_VIDEO_POLL_URL",
        auth_header_name_env="SHOPAIKEY_VIDEO_AUTH_HEADER_NAME",
        auth_header_value_env="SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE",
        result_field_env="SHOPAIKEY_VIDEO_RESULT_FIELD",
        model_env="SHOPAIKEY_VIDEO_MODEL",
        capabilities_env="SHOPAIKEY_VIDEO_CAPABILITIES",
        environ={
            "SHOPAIKEY_VIDEO_ENABLED": "1",
            "SHOPAIKEY_VIDEO_SUBMIT_URL": "https://provider.invalid/v1/video/generations",
            "SHOPAIKEY_VIDEO_POLL_URL": "https://provider.invalid/v1/video/generations/{task_id}",
            "SHOPAIKEY_VIDEO_AUTH_HEADER_NAME": "Authorization",
            "SHOPAIKEY_VIDEO_AUTH_HEADER_VALUE": "Bearer test-key",
            "SHOPAIKEY_VIDEO_MODEL": "veo3.1-fast",
        },
    )
    quota_message = json.dumps(
        {
            "error": {
                "code": 429,
                "message": "Quota exceeded: PUBLIC_ERROR_USER_QUOTA_REACHED",
                "status": "RESOURCE_EXHAUSTED",
                "details": [{"reason": "PUBLIC_ERROR_USER_QUOTA_REACHED"}],
            }
        }
    )
    monkeypatch.setattr(
        provider,
        "_open_json",
        lambda *args, **kwargs: {
            "ok": True,
            "status_code": 200,
            "body": {
                "code": "success",
                "data": {
                    "status": "FAILURE",
                    "progress": "100%",
                    "data": {"message": quota_message, "state": "error"},
                },
            },
            "response_shape": {"type": "dict"},
        },
    )

    result = provider.poll_video_job("task-existing")

    assert result.ok is True
    assert result.status == "failed"
    assert result.error_code == "quota_exhausted"
    assert result.raw["provider_terminal_reason"] == "PUBLIC_ERROR_USER_QUOTA_REACHED"
    assert result.raw["provider_terminal_http_code"] == 429
    assert result.raw["provider_error_message_safe"] == "Quota exceeded"


def test_exact_price_confirmation_allows_one_quota_fallback_without_requote():
    policy = video_provider_router.product_video_controlled_fallback_policy(
        "quota_exhausted",
        {
            "submit_source": "public_user_final_confirm",
            "original_submit_source": "public_user_final_confirm",
            "public_user_confirmed": True,
            "invoice_confirmed": True,
            "provider_submit_accepted_before": True,
            "fallback_count": 0,
            "user_visible_price_xu": 144,
            "persisted_quoted_price_xu": 144,
            "customer_charge_planned_xu": 144,
            "provider_budget_xu": 144,
            "fallback_provider_cost_xu": 144,
            "quote_consistent": True,
            "charged_xu": 0,
        },
    )

    assert policy["fallback_allowed"] is True
    assert policy["fallback_within_persisted_budget"] is True
    assert policy["fallback_requires_new_price"] is False
    assert policy["fallback_reason"] == "quota_exhausted"
