from decimal import Decimal
import json
from pathlib import Path

import video_product_system
from providers.video_generic_http_provider import build_key4u_video_payload
from services import video_ai_real_pricing as pricing
from services import (
    aas_shared_knowledge,
    pricing_guide_content,
    remote_worker_api,
    video_project_queue,
    video_provider_catalog,
    video_tail9,
)
from services.video_provider_base import VideoGenerationRequest


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _source_between(start: str, end: str) -> str:
    return BOT_SOURCE.split(start, 1)[1].split(end, 1)[0]


def test_provider_exchange_rates_are_provider_specific_with_owner_default():
    rows = {
        row["provider_key"]: row
        for row in pricing.provider_exchange_rate_catalog()
    }

    assert pricing.DEFAULT_PROVIDER_USD_TO_VND == Decimal("3500")
    assert pricing.provider_usd_to_vnd("shopaikey") == Decimal("3250")
    assert pricing.provider_usd_to_vnd("key4u") == Decimal("3500")
    assert pricing.provider_usd_to_vnd("unknown-provider") == Decimal("3500")
    assert rows["shopaikey"]["vnd_per_usd"] == 3250
    assert rows["key4u"]["vnd_per_usd"] == 3500
    assert rows["default"]["vnd_per_usd"] == 3500
    assert rows["key4u"]["source_reference"] == (
        "Owner-verified live top-up checkout: 1 USD costs 3,500 VND"
    )
    assert all(row["approval_status"] == "canonical_approved" for row in rows.values())
    assert all(row["catalog_version"] == "2026-08-11.fx.1" for row in rows.values())


def test_video_public_prices_use_owner_default_rate_for_both_providers():
    video_prices = {
        row["key"]: row["unit_xu"]
        for row in pricing.model_catalog()
    }
    assert video_prices == {
        "social_fast_5": 200,
        "grok3_5": 220,
        "veo31_fast_8": 80,
        "motion_standard_5": 110,
        "motion_audio_5": 160,
        "kling_long_audio_15": 220,
        "motion_pro_audio_10": 370,
        "human_performance_6": 370,
        "multi_angle_reference_8": 1260,
        "cinematic_multishot_10": 2360,
    }

    for row in pricing.model_catalog():
        highest_usd = max(
            Decimal(str(cost["usd_per_scene"]))
            for cost in row["provider_costs"]
        )
        expected_vnd = int(highest_usd * Decimal("3500"))
        assert row["public_pricing_usd_to_vnd"] == 3500
        assert row["pricing_cost_vnd"] == expected_vnd


def test_video_catalog_has_ten_stable_tier_ids_in_owner_order():
    assert pricing.QUALITY_TIER_MODEL_KEYS == {
        200: "social_fast_5",
        300: "grok3_5",
        400: "veo31_fast_8",
        500: "motion_standard_5",
        600: "motion_audio_5",
        700: "kling_long_audio_15",
        800: "motion_pro_audio_10",
        1000: "human_performance_6",
        1200: "multi_angle_reference_8",
        1500: "cinematic_multishot_10",
    }


def test_video_package_registry_uses_tier_ids_with_canonical_price_and_duration():
    expected = {
        200: (200, 5),
        300: (220, 5),
        400: (80, 8),
        500: (110, 5),
        600: (160, 5),
        700: (220, 15),
        800: (370, 10),
        1000: (370, 6),
        1200: (1260, 8),
        1500: (2360, 10),
    }

    for tier_id, (price_xu, seconds) in expected.items():
        package_id = f"package_{tier_id}"
        package = video_product_system.VIDEO_PACKAGE_REGISTRY[package_id]
        assert package["tier_id"] == tier_id
        assert package["price_xu"] == price_xu
        assert package["duration_seconds"] == seconds

    extended = (
        "video_ai_real",
        "image_to_video",
        "script_image_video",
        "storyboard_prompt",
        "self_shot_scene_change",
        "self_shot_cinematic_transform",
    )
    protected = ("video_trend", "video_idea", "multi_scene_film")
    for product in extended:
        assert "package_700" in video_product_system.VIDEO_PRODUCT_REGISTRY[product]["allowed_packages"]
    for product in protected:
        assert "package_700" not in video_product_system.VIDEO_PRODUCT_REGISTRY[product]["allowed_packages"]


def test_each_video_tier_resolves_to_its_exact_catalog_model_and_duration():
    expected = {
        200: ("low", "shopaikey_video", "grok-video-3", 5),
        300: ("basic", "shopaikey_video", "grok-video-3", 5),
        400: ("common", "key4u_video", "veo_3_1-fast", 8),
        500: ("advanced", "shopaikey_video", "veo3.1-fast", 5),
        600: ("standard", "shopaikey_video", "veo3.1-fast", 5),
        700: ("long", "key4u_video", "kling-video", 15),
        800: ("high", "key4u_video", "kling-video", 10),
        1000: ("future_1000", "key4u_video", "MiniMax-Hailuo-2.3", 6),
        1200: ("future_1200", "shopaikey_video", "veo3.1-pro-components", 8),
        1500: (
            "future_1500",
            "key4u_video",
            "doubao-seedance-1-0-pro-250528",
            10,
        ),
    }
    env = {
        "KEY4U_VIDEO_ENDPOINT": "https://provider.invalid/video",
        "KEY4U_VIDEO_POLL_ENDPOINT": "https://provider.invalid/video/query",
        "KEY4U_KLING_VIDEO_ENDPOINT": "https://provider.invalid/kling",
        "KEY4U_KLING_VIDEO_POLL_URL": "https://provider.invalid/kling/query",
        "KEY4U_HAILUO_VIDEO_ENDPOINT": "https://provider.invalid/hailuo",
        "KEY4U_HAILUO_VIDEO_POLL_URL": "https://provider.invalid/hailuo/query",
        "KEY4U_VEO_VIDEO_ENDPOINT": "https://provider.invalid/veo",
        "KEY4U_VEO_VIDEO_POLL_URL": "https://provider.invalid/veo/query",
    }

    for tier_id, (tier_key, provider, model, seconds) in expected.items():
        resolved = video_provider_catalog.resolve_product_video_model(
            tier=tier_id,
            scene_count=2,
            required_capability="text_to_video",
            requires_concat=True,
            env=env,
        )
        assert resolved["ok"] is True
        assert resolved["tier"] == tier_key
        assert resolved["selected_provider"] == provider
        assert resolved["selected_model"] == model
        assert resolved["selected_clip_seconds"] == seconds
        assert resolved["selected_request_defaults"]["duration"] == seconds
        assert resolved["contract_validation_status"] == "ok"


def test_key4u_payload_applies_the_selected_tier_variant_without_duration_drift():
    env = {
        "KEY4U_VIDEO_ENDPOINT": "https://provider.invalid/video",
        "KEY4U_KLING_VIDEO_ENDPOINT": "https://provider.invalid/kling",
        "KEY4U_KLING_VIDEO_POLL_URL": "https://provider.invalid/kling/query",
    }
    expected = {
        500: {"duration": 5, "model_name": "kling-v3", "mode": "std", "sound": False},
        600: {"duration": 5, "model_name": "kling-v3", "mode": "std", "sound": True},
        700: {"duration": 15, "model_name": "kling-v3", "mode": "pro", "sound": True},
        800: {"duration": 10, "model_name": "kling-v3", "mode": "pro", "sound": True},
    }

    for tier_id, request_defaults in expected.items():
        resolved = video_provider_catalog.resolve_product_video_model(
            tier=tier_id,
            provider_chain=["key4u_video"],
            scene_count=1,
            required_capability="text_to_video",
            requires_concat=False,
            env=env,
        )
        assert resolved["ok"] is True
        metadata = video_provider_catalog.model_metadata_from_resolution(resolved)
        payload = build_key4u_video_payload(
            VideoGenerationRequest(
                job_id=f"tier-{tier_id}",
                prompt="Một cảnh quảng cáo sản phẩm rõ ràng.",
                ratio="9:16",
                duration_seconds=request_defaults["duration"],
                product_type="video_ai_prompt",
                required_capability="text_to_video",
                metadata=metadata,
            ),
            env,
        )

        assert payload["model"] == "kling-video"
        for key, value in request_defaults.items():
            assert payload[key] == value


def test_primary_motion_routes_preserve_the_public_audio_choice():
    catalog = {row["key"]: row for row in pricing.model_catalog()}
    expected = {
        500: ("motion_standard_5", False),
        600: ("motion_audio_5", True),
    }

    for tier_id, (model_key, sound) in expected.items():
        resolved = video_provider_catalog.resolve_product_video_model(
            tier=tier_id,
            scene_count=1,
            required_capability="text_to_video",
            requires_concat=False,
            env={},
        )
        shopaikey_cost = next(
            cost
            for cost in catalog[model_key]["provider_costs"]
            if cost["provider"] == "shopaikey"
        )

        assert resolved["selected_provider"] == "shopaikey_video"
        assert resolved["selected_request_defaults"]["sound"] is sound
        assert shopaikey_cost["request_metadata"]["sound"] is sound


def test_fifteen_second_tier_stays_scoped_to_approved_uiflow3_products():
    extended = (
        "video_ai_real",
        "video_ai_prompt",
        "video_ai_image",
        "script_image_video",
        "storyboard_prompt",
        "self_shot_scene_change",
        "self_shot_cinematic_transform",
    )
    protected = ("video_trend", "video_idea", "multi_scene_film", "video_long")

    for product in extended:
        assert 700 in video_tail9.commercial_contract(product)["supported_quality_tiers"]
    for product in protected:
        assert 700 not in video_tail9.commercial_contract(product)["supported_quality_tiers"]


def test_remote_worker_preserves_verified_fifteen_second_scene_duration():
    identity = "a" * 64
    shared = {
        "source": "product_video",
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "product_type": "video_ai_real",
        "public_product_type": "video_ai_real",
        "engine_adapter": "video_ai_canonical",
        "orchestration_mode": "per_scene_8s",
        "provider_orchestration_mode": "per_scene_8s",
        "provider_chain": ["key4u_video"],
        "scene_count": 2,
        "scene_duration_seconds": 15,
        "duration_seconds": 30,
        "expected_duration_seconds": 30,
        "uiflow3_bridge_version": "p0.uiflow3.routeengine.v1",
        "uiflow3_handoff_sha256": identity,
        "selected_provider": "key4u_video",
        "selected_model": "kling-video",
        "selected_family": "kling",
        "selected_clip_seconds": 15,
        "selected_payload_adapter": "key4u_kling_small_clip",
        "selected_request_defaults": {
            "model_name": "kling-v3",
            "mode": "pro",
            "duration": 15,
            "sound": True,
        },
        "provider_model_map": {"key4u_video": "kling-video"},
        "provider_request_defaults": {
            "key4u_video": {
                "model_name": "kling-v3",
                "mode": "pro",
                "duration": 15,
                "sound": True,
            }
        },
        "contract_validation_status": "ok",
    }
    scene_cards = [
        {"scene_index": index, "video_prompt": f"Cảnh {index}"}
        for index in (1, 2)
    ]
    project = {
        "project_id": 71,
        "user_id": 981071,
        "profile_id": "video_ai_real",
        "ratio": "9:16",
        "quality_tier": 700,
        "scene_count": 2,
        "total_xu_estimated": 440,
        "asset_pack_json": json.dumps(shared),
        "invoice_json": json.dumps({**shared, "tier": "long", "quality_tier": 700}),
        "addon_plan_json": "{}",
        "scene_cards_json": json.dumps(scene_cards),
    }
    payload = remote_worker_api.build_worker_job_payload(
        {
            "id": 81,
            "job_type": "video_render",
            "project": project,
            "scenes": [],
            "result_json": "{}",
        }
    )

    assert payload["scene_duration_seconds"] == 15
    assert payload["expected_duration_seconds"] == 30
    assert [item["scene_duration_seconds"] for item in payload["scene_tasks"]] == [15, 15]


def test_fifteen_second_tier_uses_stable_public_gate_identity():
    blocked_tiers = _source_between(
        "def video_public_blocked_tiers()",
        "def video_public_beta_tiers()",
    )
    billing_gate = _source_between(
        "def video_billing_public_gate()",
        "def video_remote_worker_runtime_status()",
    )
    safe_open = _source_between(
        "def video_public_open_safe_result(",
        "def video_public_open_safe_text(",
    )
    beta_open = _source_between(
        "def video_beta_open_result(",
        "def video_beta_open_text(",
    )
    beta_open_text = _source_between(
        "def video_beta_open_text(",
        "def video_beta_close_result(",
    )
    beta_close = _source_between(
        "def video_beta_close_result(",
        "def video_beta_close_text(",
    )
    public_status = _source_between(
        "def video_public_status_payload()",
        "def video_public_status_text()",
    )

    assert 'blocked.discard("long")' in blocked_tiers
    assert '"long": video_tier_public_flag("long")' in billing_gate
    assert 'set_video_runtime_bool("video_beta_tier_700_enabled"' in safe_open
    assert 'set_video_runtime_bool("video_beta_tier_700_enabled"' in beta_open
    assert 'set_video_runtime_bool("video_beta_tier_700_enabled", False' in beta_close
    assert "VIDEO_TIER_NAME_TO_ID[tier]" in safe_open
    assert "opened_prices" not in beta_open_text
    assert "VIDEO_TIER_ID_TO_NAME.items()" in beta_open_text
    assert '"video_700": _tier_public_conclusion("long")' in public_status
    assert '"advanced", "standard", "long", "high"' in public_status
    assert 'env_int("VIDEO_PUBLIC_MAX_DURATION_SECONDS", 15)' in BOT_SOURCE
    assert 'VIDEO_PUBLIC_MAX_DURATION_SECONDS must stay <= 15' in billing_gate


def test_video_fallback_metadata_matches_the_runtime_route_matrix():
    routing = video_provider_catalog.load_product_video_model_routing()
    rows = {row["key"]: row for row in pricing.model_catalog()}

    for tier_id, model_key in pricing.QUALITY_TIER_MODEL_KEYS.items():
        tier_name = routing["tier_aliases"][str(tier_id)]
        preferred = list(routing["tiers"][tier_name]["preferred"])
        expected = len(preferred) > 1
        row = rows[model_key]

        assert row["fallback_eligible"] is expected
        assert all(
            cost["fallback_eligible"] is expected
            for cost in row["provider_costs"]
        )


def test_video_package_identity_never_uses_the_public_total_as_a_tier():
    package_helper = _source_between(
        "def video_tier_package_id(",
        "def video_tier_enabled_map(",
    )
    quote = _source_between(
        "def calculate_video_quote(",
        "def video_quote_line_items(",
    )
    legacy_bridge = _source_between(
        "def build_legacy_shopaikey_video_order_from_task3d_session(",
        "def record_video_last_export_error(",
    )

    assert "VIDEO_TIER_NAME_TO_ID.get(tier_norm)" in package_helper
    assert "video_tier_package_id(tier)" in quote
    assert "video_tier_package_id(tier)" in legacy_bridge
    assert "total_xu if total_xu in" not in legacy_bridge


def test_admin_open_all_uses_the_complete_ten_tier_order():
    open_all = _source_between(
        "def video_open_all_current_tiers_result(",
        "def video_open_all_current_tiers_text(",
    )

    assert '"tiers=" + ",".join(VIDEO_TIER_ORDER)' in open_all
    assert '"video_1500"' not in open_all


def test_project_queue_keeps_route_tier_separate_from_the_public_quote_total():
    invoice = {
        "routing_quality_tier": 400,
        "quality_xu": 80,
        "scene_count": 2,
        "subtotal_xu": 160,
        "discount_percent": 10,
        "discount_xu": 16,
        "total_xu": 144,
    }
    project = {
        "quality_tier": 400,
        "total_xu_estimated": 144,
    }

    for current_invoice in (invoice, {**invoice, "package_xu": 144}):
        quote = video_project_queue._product_video_quote_consistency(
            current_invoice,
            project,
        )

        assert quote["selected_tier"] == "common"
        assert quote["user_visible_price_xu"] == 144
        assert quote["persisted_quoted_price_xu"] == 144
        assert quote["customer_charge_planned_xu"] == 144


def test_all_active_video_price_surfaces_reject_the_legacy_tier_as_price_table():
    public_rows = pricing.public_quality_catalog()
    expected_tiers = [
        (row["name"], row["unit_xu"])
        for row in public_rows
    ]
    expected_lines = [
        f"• {row['icon']} {row['name']} — {row['seconds']} giây/cảnh: {row['unit_xu']:,} Xu/cảnh.".replace(",", ".")
        for row in public_rows
    ]

    assert aas_shared_knowledge.VIDEO_TIERS == expected_tiers
    assert pricing_guide_content.default_context()["video_price_lines"] == expected_lines

    active_paths = (
        ROOT / "bot.py",
        ROOT / "video_product_system.py",
        ROOT / "services" / "pricing_guide_content.py",
        ROOT / "services" / "aas_shared_knowledge.py",
        ROOT / "services" / "video_selfshot2.py",
        ROOT / "services" / "video_selfshot3.py",
        ROOT / "services" / "video_tail9.py",
        ROOT / "knowledge" / "toan_aas_cskh_aichat_context.md",
        ROOT / "scripts" / "export_public_pricing_guides.py",
        ROOT / ".env.example",
        ROOT / "docs" / "COMMAND_REGISTRY.md",
        ROOT / "docs" / "provider_catalog_audit.md",
        ROOT / "docs" / "knowledge" / "TOAN_AAS_BOT_APP_KNOWLEDGE.md",
        ROOT / "docs" / "knowledge" / "TOAN_AAS_PRICING_KNOWLEDGE.md",
        ROOT / "docs" / "knowledge" / "TOAN_AAS_PROMPT_VAULT_SCHEMA.md",
        ROOT / "docs" / "public" / "bang-gia-toan-aas.md",
        ROOT / "docs" / "public" / "huong-dan-su-dung-toan-aas.md",
        ROOT / "docs" / "public" / "TOAN_AAS_HUONG_DAN_SU_DUNG_CHO_KHACH_V2.md",
    )
    active_text = "\n".join(path.read_text(encoding="utf-8") for path in active_paths)
    forbidden = (
        "Video 300 Xu: gói cơ bản",
        "Cơ bản — 300 Xu",
        "Phổ thông — 400 Xu",
        "Nâng cao — 500 Xu",
        "Bán hàng — 600 Xu",
        "Cao cấp — 800 Xu",
        "Chuyên nghiệp — 1000 Xu",
        "Pro Plus — 1200 Xu",
        "Premium — 1500 Xu",
        "gói Cơ bản 300 Xu",
        "300 × 90%",
        "2-9 cảnh: giảm 10%",
        "10-19 cảnh: giảm 15%",
        "• 20 cảnh: giảm 20%.",
        "Nâng lên 300 Xu",
        'InlineKeyboardButton("300 Xu", callback_data="vfinal|tier|basic")',
        'InlineKeyboardButton("400 Xu", callback_data="vfinal|tier|common")',
        'InlineKeyboardButton("300 Xu", callback_data="create_media|video_tier_basic")',
        'InlineKeyboardButton("400 Xu", callback_data="create_media|video_tier_common")',
        "VIDEO_BASIC_COST_XU=300",
        "VIDEO_COMMON_COST_XU=400",
        "VIDEO_PREMIUM_COST_XU=2000",
    )

    assert not [marker for marker in forbidden if marker in active_text]
    for line in expected_lines:
        assert line in pricing_guide_content.guide_markdown()
    assert video_tail9.CANONICAL_QUALITY_TIERS == tuple(
        row["tier_id"] for row in public_rows
    )


def test_video_multiscene_discount_uses_the_owner_bands_only_from_two_scenes():
    expected = {
        1: 0,
        2: 10,
        5: 10,
        6: 15,
        10: 15,
        11: 20,
        20: 20,
    }

    assert {
        scene_count: pricing.video_multiscene_discount_percent(scene_count)
        for scene_count in expected
    } == expected
    assert pricing.video_multiscene_price(200, 1) == {
        "scene_count": 1,
        "unit_xu": 200,
        "subtotal_xu": 200,
        "discount_percent": 0,
        "discount_xu": 0,
        "total_xu": 200,
    }
    assert pricing.video_multiscene_price(200, 3) == {
        "scene_count": 3,
        "unit_xu": 200,
        "subtotal_xu": 600,
        "discount_percent": 10,
        "discount_xu": 60,
        "total_xu": 540,
    }
    assert pricing.video_multiscene_price(110, 7) == {
        "scene_count": 7,
        "unit_xu": 110,
        "subtotal_xu": 770,
        "discount_percent": 15,
        "discount_xu": 116,
        "total_xu": 654,
    }

    guide = pricing_guide_content.guide_markdown()
    assert "2–5 cảnh: giảm 10%" in guide
    assert "6–10 cảnh: giảm 15%" in guide
    assert "11–20 cảnh: giảm 20%" in guide
    assert "1 cảnh không giảm" in guide
