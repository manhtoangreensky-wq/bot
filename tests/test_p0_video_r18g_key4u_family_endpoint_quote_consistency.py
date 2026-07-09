import json
import sqlite3
from pathlib import Path

import pytest

from providers.video_generic_http_provider import GenericHttpVideoProvider, build_key4u_video_payload
from services import video_project_queue as queue
from services import video_provider_router
from services.video_provider_base import VideoArtifactResult, VideoGenerationRequest, VideoSubmitResult
from services.video_provider_catalog import (
    KEY4U_EXCLUSIVE_ENDPOINT_MISSING,
    KEY4U_MODEL_CONTRACT_MISSING,
    resolve_product_video_model,
)


ROOT = Path(__file__).resolve().parents[1]


def _key4u_env(**extra):
    env = {
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_SUBMIT_URL": "https://api.key4u.shop/v1/video/generations",
        "KEY4U_VIDEO_POLL_URL": "https://api.key4u.shop/v1/video/generations/{task_id}",
        "KEY4U_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer test-token",
        "KEY4U_VIDEO_MODEL": "kling-video",
        "KEY4U_VIDEO_CAPABILITIES": "text_to_video,scene_video,multi_scene_video",
    }
    env.update(extra)
    return env


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


def _request(model="kling-video", provider="key4u_video"):
    return VideoGenerationRequest(
        job_id="108-1",
        product_type="video_trend",
        prompt="A product trend scene, 8 seconds.",
        ratio="9:16",
        duration_seconds=8,
        required_capability="text_to_video_or_scene_video",
        metadata={
            "source": "product_video",
            "product_video": True,
            "scene_index": 1,
            "clip_index": 1,
            "orchestration_mode": "per_scene_8s",
            "render_pipeline_mode": "historical_multi_clip_concat",
            "selected_provider": provider,
            "selected_model": model,
            "provider_model_map": {provider: model},
            "submit_source": "public_user_final_confirm",
            "provider_submit_source": "public_user_final_confirm",
            "original_submit_source": "public_user_final_confirm",
            "public_user_confirmed": True,
            "invoice_confirmed": True,
        },
    )


def test_job_108_key4u_kling_without_exclusive_endpoint_blocks_before_http(monkeypatch):
    provider = _key4u_provider(_key4u_env())
    monkeypatch.setattr(provider, "_open_json", lambda *args, **kwargs: pytest.fail("contract block must happen before HTTP"))

    result = provider.submit_video_job(_request())

    assert result.ok is False
    assert result.error_code == KEY4U_EXCLUSIVE_ENDPOINT_MISSING
    assert result.raw["contract_validation_status"] == "blocked"
    assert result.raw["contract_block_reason"] == KEY4U_EXCLUSIVE_ENDPOINT_MISSING
    assert result.raw["submit_http_status"] == 0
    assert result.raw["submit_skipped_due_to_contract"] is True
    assert result.raw["contract_reject_consumed_fallback"] is False
    assert result.raw["no_charge"] is True


def test_key4u_kling_with_exclusive_endpoint_uses_kling_endpoint(monkeypatch):
    captured = {}
    env = _key4u_env(KEY4U_KLING_VIDEO_ENDPOINT="https://api.key4u.shop/kling/v1/videos/text2video")
    provider = _key4u_provider(env)

    def fake_open(url, payload=None, **kwargs):
        captured["url"] = url
        captured["payload"] = payload
        return {"ok": True, "status_code": 200, "body": {"task_id": "task-r18g"}, "response_shape": {"type": "dict"}}

    monkeypatch.setattr(provider, "_open_json", fake_open)
    result = provider.submit_video_job(_request())

    assert result.ok is True
    assert captured["url"] == "https://api.key4u.shop/kling/v1/videos/text2video"
    assert "/kling/" in captured["url"]
    assert captured["payload"]["model"] == "kling-video"
    assert "scenes" not in captured["payload"]
    assert "storyboard" not in captured["payload"]
    assert "image_paths" not in captured["payload"]
    assert result.raw["provider_interface"] == "key4u_kling_exclusive"
    assert result.raw["provider_endpoint_source"] == "KEY4U_KLING_VIDEO_ENDPOINT"


def test_key4u_hailuo_without_known_contract_blocks_before_http(monkeypatch):
    provider = _key4u_provider(_key4u_env(KEY4U_VIDEO_MODEL="MiniMax-Hailuo-02"))
    monkeypatch.setattr(provider, "_open_json", lambda *args, **kwargs: pytest.fail("hailuo contract must block before HTTP"))

    result = provider.submit_video_job(_request(model="MiniMax-Hailuo-02"))

    assert result.ok is False
    assert result.error_code == KEY4U_MODEL_CONTRACT_MISSING
    assert result.raw["submit_http_status"] == 0
    assert result.raw["submit_skipped_due_to_contract"] is True


def test_low_and_basic_route_shopaikey_primary_key4u_fallback_only():
    env = {"VIDEO_PROVIDER_CHAIN": "shopaikey_video,key4u_video"}

    low = resolve_product_video_model(tier=200, env=env)
    basic = resolve_product_video_model(tier=300, env=env)

    assert low["ok"] is True
    assert low["selected_provider"] == "shopaikey_video"
    assert low["selected_model"] in {"grok-video-3", "veo3.1-fast"}
    assert any(item["provider"] == "key4u_video" for item in low["candidate_list_compact"])
    assert basic["ok"] is True
    assert basic["selected_provider"] == "shopaikey_video"
    assert basic["selected_model"] == "veo3.1-fast"
    key4u_basic = [item for item in basic["candidate_list_compact"] if item["provider"] == "key4u_video"]
    assert key4u_basic and key4u_basic[0]["role"] == "fallback"


def test_key4u_primary_override_on_basic_warns_and_blocks_without_contract():
    result = resolve_product_video_model(tier=300, provider_chain=["key4u_video"], env={"VIDEO_PROVIDER_CHAIN": "key4u_video"})

    assert result["ok"] is False
    assert result["blocker"] == KEY4U_EXCLUSIVE_ENDPOINT_MISSING
    assert result["cost_routing_warning"] == "COST_ROUTING_OVERRIDE_KEY4U_PRIMARY"
    assert result["public_low_tier_primary_provider_warning"] == "PUBLIC_LOW_TIER_PRIMARY_PROVIDER_NOT_COST_OPTIMAL"


def test_contract_reject_falls_through_to_shopaikey_without_consuming_fallback(monkeypatch, tmp_path):
    class Key4UContractBlocked:
        provider_name = "key4u_video"

        def capabilities(self):
            return {"provider": self.provider_name, "enabled": True, "configured": True, "capabilities": ["text_to_video", "scene_video"]}

        def submit_video_job(self, request):
            return VideoSubmitResult(
                ok=False,
                provider_name=self.provider_name,
                provider_status="contract_blocked",
                error_code=KEY4U_EXCLUSIVE_ENDPOINT_MISSING,
                raw={
                    "submit_http_status": 0,
                    "provider_submit_blocker": KEY4U_EXCLUSIVE_ENDPOINT_MISSING,
                    "contract_validation_status": "blocked",
                    "contract_block_reason": KEY4U_EXCLUSIVE_ENDPOINT_MISSING,
                    "submit_skipped_due_to_contract": True,
                    "contract_reject_consumed_fallback": False,
                },
            )

    class ShopAIKeySuccess:
        provider_name = "shopaikey_video"

        def capabilities(self):
            return {"provider": self.provider_name, "enabled": True, "configured": True, "capabilities": ["text_to_video", "scene_video"]}

        def submit_video_job(self, request):
            return VideoSubmitResult(
                ok=True,
                provider_name=self.provider_name,
                provider_task_id="task-shop",
                provider_status="completed",
                result_url="https://cdn.example.test/video.mp4",
                raw={"submit_http_status": 200, "provider_task_id_present": True, "submit_accepted": True},
            )

        def poll_video_job(self, provider_task_id):
            raise AssertionError("result_url from submit should not need poll")

        def materialize_result(self, result, job_id):
            return VideoArtifactResult(ok=True, local_path=str(tmp_path / "final.mp4"), bytes=1234, duration=8.0, has_video_stream=True)

    monkeypatch.setattr(video_provider_router, "load_video_provider_adapters", lambda _env=None: [Key4UContractBlocked(), ShopAIKeySuccess()])
    result = video_provider_router.run_provider_generation(
        _request(model="kling-video", provider="key4u_video"),
        output_dir=str(tmp_path),
        environ={
            "VIDEO_PROVIDER_CHAIN": "key4u_video,shopaikey_video",
            "PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED": "1",
            "PRODUCT_VIDEO_PAID_RETRY_REQUIRES_CONFIRMATION": "1",
        },
        sleep_func=lambda _seconds: None,
    )

    assert result["ok"] is True
    assert result["selected_provider"] == "shopaikey_video"
    assert result["provider_fallback_attempts"][0]["reason"] == KEY4U_EXCLUSIVE_ENDPOINT_MISSING
    assert result["provider_fallback_attempts"][0]["contract_reject_consumed_fallback"] is False
    assert result["fallback_count"] == 0


def test_quote_consistency_basic_300_persists_quoted_300(tmp_path):
    conn = sqlite3.connect(tmp_path / "r18g.db")
    queue.ensure_video_project_queue_schema(conn)
    asset_pack = {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "provider_order": "shopaikey_video,key4u_video",
    }
    invoice = {
        **asset_pack,
        "tier": "basic",
        "package_xu": 300,
        "scene_count": 2,
        "total_xu": 400,
    }
    project = queue.create_video_project(conn, user_id=18, profile_id="video_trend", topic="trend", asset_pack=asset_pack)
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="draft_invoice",
        invoice_json=invoice,
        scene_count=2,
        total_xu_estimated=400,
        quality_tier=300,
    )

    result = queue.confirm_video_project_invoice(conn, project_id=int(project["project_id"]), user_id=18)
    payload = json.loads(result["job"]["result_json"])

    assert payload["selected_tier"] == "basic"
    assert payload["user_visible_price_xu"] == 300
    assert payload["persisted_quoted_price_xu"] == 300
    assert payload["customer_charge_planned_xu"] == 300
    assert payload["wallet_charge_amount_xu"] == 300
    assert payload["charge_amount_planned_xu"] == 300
    assert payload["list_price_xu"] == 400
    assert payload["provider_budget_xu"] == 400
    assert payload["promo_discount_xu"] == 100
    assert payload["quote_consistent"] is True
    assert payload["provider_chain_resolved"] is True


def test_quote_mismatch_blocks_before_submit_no_charge(tmp_path):
    conn = sqlite3.connect(tmp_path / "r18g_mismatch.db")
    queue.ensure_video_project_queue_schema(conn)
    asset_pack = {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "provider_order": "shopaikey_video,key4u_video",
    }
    invoice = {
        **asset_pack,
        "tier": "basic",
        "package_xu": 300,
        "quoted_price_xu": 400,
        "scene_count": 2,
        "total_xu": 400,
    }
    project = queue.create_video_project(conn, user_id=19, profile_id="video_trend", topic="trend", asset_pack=asset_pack)
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="draft_invoice",
        invoice_json=invoice,
        scene_count=2,
        total_xu_estimated=400,
        quality_tier=300,
    )

    result = queue.confirm_video_project_invoice(conn, project_id=int(project["project_id"]), user_id=19)

    assert result["ok"] is False
    assert result["reason"] == "product_video_quote_mismatch_no_charge"
    assert result["quote"]["quote_consistent"] is False
    assert result["quote"]["quote_mismatch_reason"] == "product_video_quote_mismatch_no_charge"
    assert result["quote"]["user_visible_price_xu"] == 300
    assert result["quote"]["persisted_quoted_price_xu"] == 400
    assert result["quote"]["customer_charge_planned_xu"] == 400
    assert result["quote"]["wallet_charge_amount_xu"] == 400


def test_finance_debug_source_contract_exposes_quote_fields():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    assert "user visible price:" in source
    assert "persisted quoted price:" in source
    assert "customer charge planned:" in source
    assert "wallet charge amount:" in source
    assert "list price:" in source
    assert "provider budget:" in source
    assert "quote consistent:" in source
    assert "Product Video default chain:" in source
    assert "Low tier primary:" in source
    assert "Product Video cost routing warning:" in source


def test_no_real_provider_calls_in_r18g_tests():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "urllib.request." + "urlopen",
        "submit_url_th" + "ật",
    )
    assert all(token not in source for token in forbidden)
