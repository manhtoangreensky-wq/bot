import pytest
from decimal import Decimal
import math
from services import video_provider_router
from services import video_ai_real_pricing
from services import admin_pricing_service
from services.video_provider_base import (
    VideoArtifactResult,
    VideoGenerationRequest,
    VideoPollResult,
    VideoSubmitResult,
)


class _MockAdapter:
    def __init__(
        self,
        provider_name: str,
        *,
        model: str = "",
        submit: VideoSubmitResult | None = None,
        poll: VideoPollResult | None = None,
    ):
        self.provider_name = provider_name
        self.model = model
        self.submit_result = submit
        self.poll_result = poll
        self.submit_calls = 0
        self.poll_calls = 0

    def capabilities(self):
        return {
            "provider": self.provider_name,
            "enabled": True,
            "configured": True,
            "missing": [],
            "capabilities": ["text_to_video", "scene_video", "multi_scene_video"],
            "endpoint_configured": True,
            "submit_url_configured": True,
            "poll_url_configured": True,
            "auth_configured": True,
            "model_configured": True,
            "provider_auth_value_present": True,
            "provider_model_present": True,
            "provider_payload_model": self.model or "veo3.1-fast",
            "provider_config_source": f"env:{self.provider_name}",
        }

    def submit_video_job(self, request):
        self.submit_calls += 1
        if self.submit_result is not None:
            return self.submit_result
        return VideoSubmitResult(
            ok=True,
            provider_name=self.provider_name,
            provider_task_id=f"{self.provider_name}-task-123",
            provider_status="MEDIA_GENERATION_STATUS_PENDING",
            raw={"http_status": 200, "task_id_field_path": "data.id_base"},
        )

    def poll_video_job(self, provider_task_id: str):
        self.poll_calls += 1
        if self.poll_result is not None:
            return self.poll_result
        return VideoPollResult(
            ok=True,
            status="MEDIA_GENERATION_STATUS_IN_PROGRESS",
            provider_name=self.provider_name,
            provider_task_id=provider_task_id,
            raw={"poll_http_status": 200, "provider_status_raw": "MEDIA_GENERATION_STATUS_IN_PROGRESS"},
        )

    def materialize_result(self, result, job_id: str):
        return VideoArtifactResult(ok=False, error_code="provider_download_failed")


def _make_request(
    *,
    tier_id: int,
    scene_count: int = 1,
    quote_xu: int | None = None,
    product_type: str = "video_trend",
    extra_metadata: dict | None = None,
):
    meta = {
        "product_video": True,
        "interactive_product": True,
        "allow_provider_pending": True,
        "wallet_charge": False,
        "tier_id": tier_id,
        "quality_tier": tier_id,
        "scene_count": scene_count,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "paid_fallback_confirmed": True,
        "submit_source": video_provider_router.PRODUCT_VIDEO_SUBMIT_SOURCE_PUBLIC_FINAL_CONFIRM,
        "provider_submit_allowed": True,
    }
    if quote_xu is not None:
        meta["customer_quote_xu"] = quote_xu
        meta["final_quote_xu"] = quote_xu
        meta["user_visible_price_xu"] = quote_xu
        meta["persisted_quoted_price_xu"] = quote_xu
    if extra_metadata:
        meta.update(extra_metadata)

    return VideoGenerationRequest(
        job_id="999",
        product_type=product_type,
        video_flow_type=product_type,
        prompt="Test product video prompt",
        ratio="9:16",
        duration_seconds=10,
        required_capability="text_to_video",
        metadata=meta,
    )


def _default_env(**updates):
    env = {
        "PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED": "1",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
    }
    env.update(updates)
    return env


# ─────────────────────────────────────────────────────────────────────────────
# 1. CANONICAL PRICING & PUBLIC ORDER CONSISTENCY
# ─────────────────────────────────────────────────────────────────────────────

def test_canonical_fx_rates():
    """Verify canonical exchange rates: ShopAIKey = 3250, Key4U = 3500."""
    assert video_ai_real_pricing.product_video_provider_usd_to_vnd("shopaikey") == Decimal("3250")
    assert video_ai_real_pricing.product_video_provider_usd_to_vnd("key4u") == Decimal("3500")


def test_public_quality_catalog_order_and_prices():
    """Verify public_quality_catalog sorting by effective_unit_xu ASC and canonical base prices."""
    catalog = video_ai_real_pricing.public_quality_catalog()
    tier_order = [item["tier_id"] for item in catalog]
    expected_order = [300, 200, 1000, 400, 500, 600, 1200, 800, 1500, 700]
    assert tier_order == expected_order, f"Public order must be {expected_order}, got {tier_order}"

    expected_prices = {
        300: 221,
        200: 259,
        1000: 337,
        400: 371,
        500: 804,
        600: 804,
        1200: 1261,
        800: 2143,
        1500: 2411,
        700: 3214,
    }
    for item in catalog:
        tid = item["tier_id"]
        assert item["unit_xu"] == expected_prices[tid], f"Tier {tid} unit_xu should be {expected_prices[tid]}"


def test_public_names_capability_based():
    """Verify capability-based names for all 10 tiers."""
    catalog = video_ai_real_pricing.public_quality_catalog()
    name_map = {item["tier_id"]: item["name"] for item in catalog}
    assert name_map[300] == "Video Khởi Đầu Âm Thanh 5s"
    assert name_map[200] == "Video Chuyển Động Xã Hội 5s"
    assert name_map[1000] == "Video Diễn Xuất Nhân Vật 6s"
    assert name_map[400] == "Video Veo Cân Bằng Chi Tiết 8s"
    assert name_map[500] == "Video Chuyển Động Kiểm Soát 5s"
    assert name_map[600] == "Video Chuyển Động Đồng Bộ Âm Thanh 5s"
    assert name_map[1200] == "Video Tham Chiếu Đa Góc Nhìn 8s"
    assert name_map[800] == "Video Chuyển Động Chuyên Nghiệp Kling 10s"
    assert name_map[1500] == "Video Điện Ảnh Đa Phân Cảnh Doubao 10s"
    assert name_map[700] == "Video Toàn Cảnh Chuyển Động Dài Kling 15s"


def test_admin_pricing_consistency():
    """Verify admin pricing service base values match canonical prices."""
    expected_prices = {
        300: 221,
        200: 259,
        1000: 337,
        400: 371,
        500: 804,
        600: 804,
        1200: 1261,
        800: 2143,
        1500: 2411,
        700: 3214,
    }
    for tid, price in expected_prices.items():
        val = admin_pricing_service.get_canonical_effective_price(f"video_tier_{tid}")
        assert val == price, f"Admin price for video_tier_{tid} should be {price}, got {val}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. AUDIO COST AUTHORITY & FORMULA TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_audio_cost_authority_calculation():
    """Verify TTS formula: billable_characters * 0.000015 USD * 3250 FX."""
    assert video_ai_real_pricing.CANONICAL_TTS_MODEL == "tts-1"
    assert video_ai_real_pricing.CANONICAL_TTS_RATE_USD_PER_CHAR == Decimal("0.000015")
    assert video_ai_real_pricing.CANONICAL_TTS_BILLING_UNIT == "characters"

    cost_100 = video_ai_real_pricing.calculate_tts_cost_vnd(100)
    expected_100 = Decimal("100") * Decimal("0.000015") * Decimal("3250")  # 4.875 VND
    assert cost_100 == expected_100

    cost_str = video_ai_real_pricing.calculate_tts_cost_vnd("A" * 200)
    expected_200 = Decimal("200") * Decimal("0.000015") * Decimal("3250")  # 9.75 VND
    assert cost_str == expected_200


# ─────────────────────────────────────────────────────────────────────────────
# 3. POST-FIX FULL-OPEN TESTS: Primary & Fallback Safe across All Scene Bands
# ─────────────────────────────────────────────────────────────────────────────

SCENE_BANDS = [1, 2, 5, 6, 10, 11, 20]

def _verify_all_bands_safe(tier_id: int, provider: str, model: str, is_fallback: bool):
    unit_xu = video_ai_real_pricing.public_quality_by_tier(tier_id)["unit_xu"]
    for scenes in SCENE_BANDS:
        price_info = video_ai_real_pricing.video_multiscene_price(unit_xu, scenes)
        res = video_ai_real_pricing.check_product_video_economics(
            tier_id=tier_id,
            scene_count=scenes,
            provider=provider,
            model=model,
            customer_quote_xu=price_info["total_xu"],
            is_fallback=is_fallback,
        )
        assert res["economics_safe"] is True, (
            f"Tier {tier_id} ({provider}:{model}, fallback={is_fallback}) "
            f"failed at {scenes} scenes: quote={price_info['total_xu']} Xu, "
            f"rev={res['customer_revenue_vnd']}đ, cost={res['provider_total_cost_vnd']}đ"
        )


def test_tier300_price221_primary_and_fallback_all_bands():
    """Tier 300 (221 Xu): ShopAIKey primary and Key4U fallback safe for all scene bands."""
    _verify_all_bands_safe(300, "shopaikey", "grok-video-3", is_fallback=False)
    _verify_all_bands_safe(300, "key4u", "grok-imagine-video", is_fallback=True)


def test_tier200_price259_primary_and_fallback_all_bands():
    """Tier 200 (259 Xu): ShopAIKey primary and Key4U fallback safe for all scene bands."""
    _verify_all_bands_safe(200, "shopaikey", "grok-video-3", is_fallback=False)
    _verify_all_bands_safe(200, "key4u", "pixverse-video", is_fallback=True)


def test_tier400_price371_primary_and_fallback_all_bands():
    """Tier 400 (371 Xu): ShopAIKey primary and Key4U fallback safe for all scene bands."""
    _verify_all_bands_safe(400, "shopaikey", "veo3.1-fast", is_fallback=False)
    _verify_all_bands_safe(400, "key4u", "veo_3_1-fast", is_fallback=True)


def test_tier500_price804_primary_and_fallback_all_bands():
    """Tier 500 (804 Xu): ShopAIKey primary and Key4U Kling fallback safe for all scene bands."""
    _verify_all_bands_safe(500, "shopaikey", "veo3.1-fast", is_fallback=False)
    _verify_all_bands_safe(500, "key4u", "kling-video", is_fallback=True)


def test_tier600_price804_primary_and_fallback_all_bands():
    """Tier 600 (804 Xu): ShopAIKey primary and Key4U Kling fallback safe for all scene bands."""
    _verify_all_bands_safe(600, "shopaikey", "veo3.1-fast", is_fallback=False)
    _verify_all_bands_safe(600, "key4u", "kling-video", is_fallback=True)


def test_tier1200_price1261_primary_and_fallback_all_bands():
    """Tier 1200 (1261 Xu): ShopAIKey primary and Key4U Vidu fallback safe for all scene bands."""
    _verify_all_bands_safe(1200, "shopaikey", "veo3.1-pro-components", is_fallback=False)
    _verify_all_bands_safe(1200, "key4u", "viduq3-mix", is_fallback=True)


def test_tier800_price2143_kling_primary_all_bands():
    """Tier 800 (2143 Xu): Key4U Kling 10s primary safe for all scene bands."""
    _verify_all_bands_safe(800, "key4u", "kling-video", is_fallback=False)


def test_tier700_price3214_kling_primary_all_bands():
    """Tier 700 (3214 Xu): Key4U Kling 15s primary safe for all scene bands."""
    _verify_all_bands_safe(700, "key4u", "kling-video", is_fallback=False)


def test_tier1000_price337_with_audio_cost_all_bands():
    """Tier 1000 (337 Xu): Key4U MiniMax-Hailuo-2.3 safe with total audio cost across all scene bands."""
    _verify_all_bands_safe(1000, "key4u", "MiniMax-Hailuo-2.3", is_fallback=False)


def test_tier1500_price2411_with_audio_cost_all_bands():
    """Tier 1500 (2411 Xu): Key4U Doubao Seedance Pro safe with total audio cost across all scene bands."""
    _verify_all_bands_safe(1500, "key4u", "doubao-seedance-1-0-pro-250528", is_fallback=False)


def test_tier1500_audio_character_boundary_and_economics():
    """Verify exact audio character boundary for Tier 1500 list price and economics safety."""
    video_cost = Decimal("22.95") * Decimal("3500")  # 80325 VND

    # 170 chars:
    tts_170 = video_ai_real_pricing.calculate_tts_cost_vnd(170)
    total_170 = video_cost + tts_170
    price_170 = math.ceil(total_170 * Decimal("3") / Decimal("100"))
    assert price_170 == 2410, f"Expected 2410 for 170 chars, got {price_170}"

    # 171 chars:
    tts_171 = video_ai_real_pricing.calculate_tts_cost_vnd(171)
    total_171 = video_cost + tts_171
    price_171 = math.ceil(total_171 * Decimal("3") / Decimal("100"))
    assert price_171 == 2411, f"Expected 2411 for 171 chars, got {price_171}"

    # 200 chars (max declared bound):
    tts_200 = video_ai_real_pricing.calculate_tts_cost_vnd(200)
    assert tts_200 == Decimal("9.75")
    total_200 = video_cost + tts_200
    assert total_200 == Decimal("80334.75")
    price_200 = math.ceil(total_200 * Decimal("3") / Decimal("100"))
    assert price_200 == 2411, f"Expected 2411 for 200 chars, got {price_200}"

    # Canonical public price:
    pub_price = video_ai_real_pricing.public_quality_by_tier(1500)["unit_xu"]
    assert pub_price == 2411, f"Canonical Tier 1500 public price must be 2411, got {pub_price}"

    # Scene 1 safe:
    res_1 = video_ai_real_pricing.check_product_video_economics(
        tier_id=1500, scene_count=1, provider="key4u", model="doubao-seedance-1-0-pro-250528",
        customer_quote_xu=2411, is_fallback=False, billable_text=200
    )
    assert res_1["economics_safe"] is True

    # Scene 20 discount 20% safe:
    price_20 = video_ai_real_pricing.video_multiscene_price(2411, 20)
    res_20 = video_ai_real_pricing.check_product_video_economics(
        tier_id=1500, scene_count=20, provider="key4u", model="doubao-seedance-1-0-pro-250528",
        customer_quote_xu=price_20["total_xu"], is_fallback=False, billable_text=200
    )
    assert res_20["economics_safe"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. NEGATIVE TESTS: Underpriced Orders Block HTTP Submit
# ─────────────────────────────────────────────────────────────────────────────

def test_underpriced_order_blocks_http_submit_primary(monkeypatch, tmp_path):
    """If final discounted customer revenue < actual selected route cost -> ZERO provider HTTP submit."""
    shopaikey = _MockAdapter("shopaikey_video", model="veo3.1-fast")
    monkeypatch.setattr(
        video_provider_router,
        "load_video_provider_adapters",
        lambda _env=None: [shopaikey],
    )
    # Tier 400 cost is 2,275 VND. If quote is only 20 Xu (2,000 VND), revenue < cost!
    req = _make_request(tier_id=400, scene_count=1, quote_xu=20)
    result = video_provider_router.run_provider_generation(
        req,
        output_dir=str(tmp_path),
        environ=_default_env(VIDEO_PROVIDER_CHAIN="shopaikey_video"),
    )

    assert result.get("ok") is False
    assert result.get("blocker") == "PRODUCT_VIDEO_PROVIDER_ECONOMICS_UNSAFE"
    assert shopaikey.submit_calls == 0, "No provider HTTP submit must be made for underpriced order"


def test_underpriced_order_blocks_http_submit_fallback(monkeypatch, tmp_path):
    """If primary fails and fallback cost > customer revenue -> ZERO fallback HTTP submit."""
    shopaikey = _MockAdapter(
        "shopaikey_video",
        model="veo3.1-fast",
        submit=VideoSubmitResult(ok=False, provider_name="shopaikey_video", error_code="provider_error_503"),
    )
    key4u = _MockAdapter("key4u_video", model="veo_3_1-fast")
    monkeypatch.setattr(
        video_provider_router,
        "load_video_provider_adapters",
        lambda _env=None: [shopaikey, key4u],
    )
    # Tier 400 Key4U fallback cost is 12,337.92 VND. If customer quote is 100 Xu (10,000 VND) -> fallback unsafe!
    req = _make_request(tier_id=400, scene_count=1, quote_xu=100)
    result = video_provider_router.run_provider_generation(
        req,
        output_dir=str(tmp_path),
        environ=_default_env(VIDEO_PROVIDER_CHAIN="shopaikey_video,key4u_video"),
    )

    assert result.get("ok") is False
    assert result.get("blocker") == "PRODUCT_VIDEO_FALLBACK_ECONOMICS_UNSAFE"
    assert key4u.submit_calls == 0, "Fallback submit must NOT be called when economics is unsafe"


def test_tier700_underpriced_fixture_blocked(monkeypatch, tmp_path):
    """Tier 700 with underpriced fixture 220 Xu (revenue 22,000 VND < cost 107,100.86 VND) is blocked."""
    key4u = _MockAdapter("key4u_video", model="kling-video")
    monkeypatch.setattr(
        video_provider_router,
        "load_video_provider_adapters",
        lambda _env=None: [key4u],
    )
    req = _make_request(tier_id=700, scene_count=1, quote_xu=220)
    result = video_provider_router.run_provider_generation(
        req,
        output_dir=str(tmp_path),
        environ=_default_env(VIDEO_PROVIDER_CHAIN="key4u_video"),
    )
    assert result.get("ok") is False
    assert result.get("blocker") == "PRODUCT_VIDEO_PROVIDER_ECONOMICS_UNSAFE"
    assert key4u.submit_calls == 0


def test_tier800_underpriced_fixture_blocked(monkeypatch, tmp_path):
    """Tier 800 with underpriced fixture 370 Xu (revenue 37,000 VND < cost 71,400.57 VND) is blocked."""
    key4u = _MockAdapter("key4u_video", model="kling-video")
    monkeypatch.setattr(
        video_provider_router,
        "load_video_provider_adapters",
        lambda _env=None: [key4u],
    )
    req = _make_request(tier_id=800, scene_count=1, quote_xu=370)
    result = video_provider_router.run_provider_generation(
        req,
        output_dir=str(tmp_path),
        environ=_default_env(VIDEO_PROVIDER_CHAIN="key4u_video"),
    )
    assert result.get("ok") is False
    assert result.get("blocker") == "PRODUCT_VIDEO_PROVIDER_ECONOMICS_UNSAFE"
    assert key4u.submit_calls == 0


def test_canonical_positive_execution_allowed(monkeypatch, tmp_path):
    """Tier 700 with canonical price 3214 Xu is economically safe and allowed to submit."""
    key4u = _MockAdapter("key4u_video", model="kling-video")
    monkeypatch.setattr(
        video_provider_router,
        "load_video_provider_adapters",
        lambda _env=None: [key4u],
    )
    req = _make_request(tier_id=700, scene_count=1, quote_xu=3214)
    result = video_provider_router.run_provider_generation(
        req,
        output_dir=str(tmp_path),
        environ=_default_env(VIDEO_PROVIDER_CHAIN="key4u_video"),
    )
    assert key4u.submit_calls == 1
    assert result.get("provider_task_id_saved") is True or result.get("submit_accepted") is True
