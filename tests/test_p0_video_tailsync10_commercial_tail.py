from __future__ import annotations

from pathlib import Path

import pytest

from services import video_tail9, video_uifreeze1


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _between(start: str, end: str) -> str:
    left = BOT_SOURCE.index(start)
    right = BOT_SOURCE.index(end, left + len(start))
    return BOT_SOURCE[left:right]


@pytest.mark.parametrize(
    ("public_product", "canonical_product", "engine_route", "input_type"),
    [
        ("video_ai_realistic", "video_ai_real", "video_ai_canonical", "text_prompt"),
        ("trend_video", "video_trend", "trend_video", "trend_prompt"),
        ("script_to_video", "script_image_video", "script_to_video", "long_script"),
        ("storyboard_to_video", "storyboard_prompt", "storyboard_to_video", "storyboard_frames"),
        ("self_shot_scene_change", "self_shot_scene_change", "self_shot_scene_change", "source_video"),
        (
            "self_shot_cinematic_transform",
            "self_shot_cinematic_transform",
            "self_shot_cinematic_transform",
            "source_video",
        ),
        ("frame_video", "frame_video_local", "frame_video_render", "image_sequence"),
        ("long_video", "multi_scene_film", "multi_scene_film", "long_form_plan"),
    ],
)
def test_product_matrix_keeps_distinct_engine_and_input_contracts(
    public_product: str,
    canonical_product: str,
    engine_route: str,
    input_type: str,
) -> None:
    contract = video_tail9.commercial_contract(public_product)
    assert contract["product_type"] == canonical_product
    assert contract["engine_route"] == engine_route
    assert contract["input_type"] == input_type
    assert contract["output_type"] == "mp4"


def test_catalog_is_compatible_without_runtime_provider_health() -> None:
    storyboard = video_uifreeze1.catalog_report(
        "storyboard_to_video",
        scene_count=2,
        ratio="9:16",
    )
    script = video_uifreeze1.catalog_report(
        "script_to_video",
        scene_count=2,
        ratio="9:16",
    )
    ai_single = video_uifreeze1.catalog_report(
        "video_ai_realistic",
        scene_count=1,
        ratio="9:16",
    )
    expected_multi = [300, 400, 500, 600, 800, 1000, 1200, 1500]
    assert storyboard["tier_ids"] == expected_multi
    assert script["tier_ids"] == expected_multi
    assert ai_single["tier_ids"] == [200, *expected_multi]


def test_tier_200_is_capability_driven_and_rejected_by_service_for_multiscene_products() -> None:
    for product in ("storyboard_to_video", "script_to_video"):
        compatibility = video_tail9.package_compatibility(
            product,
            scene_count=2,
            ratio="9:16",
            quality_tier_id=200,
        )
        assert compatibility["ok"] is False
        assert compatibility["reason"] == "quality_tier_not_supported"
        state = video_tail9.new_state(
            product_type=product,
            session_id=f"{product}-session",
            scene_count=2,
        )
        with pytest.raises(ValueError, match="quality_tier_not_supported"):
            video_tail9.select_package(
                state,
                quality_tier_id="200",
                package_id="product_video_200",
                pricing_snapshot={"total_xu": 400},
                capability_snapshot={"ok": True},
            )


def test_framevideo_keeps_distinct_pricing_but_shared_delivery_truth() -> None:
    contract = video_tail9.commercial_contract("frame_video")
    report = video_uifreeze1.catalog_report("frame_video", scene_count=2, ratio="9:16")
    status = video_tail9.status_contract("frame_video")
    assert contract["pricing_mode"] == "frame_video"
    assert report["framevideo_excluded"] is True
    assert report["offers"] == []
    assert status["delivery_requires_message_id"] is True
    assert status["receipt_after_delivery"] is True
    assert status["charge_after_receipt"] is True


def test_invoice_identity_tracks_package_and_confirmation_is_idempotent() -> None:
    state = video_tail9.new_state(
        product_type="video_ai_realistic",
        session_id="invoice-session",
        plan_revision=7,
        scene_count=1,
    )
    first = video_tail9.select_package(
        state,
        quality_tier_id="300",
        package_id="product_video_300",
        pricing_snapshot={"total_xu": 300},
        capability_snapshot={"ok": True},
    )
    second = video_tail9.select_package(
        first,
        quality_tier_id="400",
        package_id="product_video_400",
        pricing_snapshot={"total_xu": 400},
        capability_snapshot={"ok": True},
    )
    assert first["invoice_id"].endswith(":300")
    assert second["invoice_id"].endswith(":400")
    confirmed, created = video_tail9.confirm_once(second, "telegram-confirm-1")
    duplicate, created_again = video_tail9.confirm_once(confirmed, "telegram-confirm-1")
    assert created is True
    assert created_again is False
    assert duplicate["confirm_token"] == "telegram-confirm-1"


def test_long_video_reaches_quote_but_cannot_confirm_or_create_side_effects() -> None:
    contract = video_tail9.commercial_contract("long_video")
    catalog = video_uifreeze1.catalog_report("long_video", scene_count=1, ratio="9:16")
    state = video_tail9.new_state(
        product_type="long_video",
        session_id="long-preview",
        scene_count=1,
        estimated_duration=600,
    )
    invoiced = video_tail9.select_package(
        state,
        quality_tier_id="300",
        package_id="product_video_300",
        pricing_snapshot={"total_xu": 300},
        capability_snapshot={"ok": True},
    )
    assert contract["scene_duration_seconds"] == 600
    assert contract["public_planning_enabled"] is True
    assert contract["execution_enabled"] is False
    assert catalog["ok"] is True
    assert video_tail9.invoice_allowed(invoiced) == (True, "ok")
    with pytest.raises(ValueError, match="long_video_under_upgrade"):
        video_tail9.confirm_once(invoiced, "confirm-long")
    assert invoiced["final_confirmed"] is False
    assert invoiced["job_id"] == ""
    compatibility = video_tail9.package_compatibility(
        "long_video",
        scene_count=1,
        ratio="9:16",
        quality_tier_id=300,
    )
    assert compatibility["side_effects"] == {
        "job": 0,
        "outbox": 0,
        "provider_calls": 0,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }


def test_long_public_entry_and_final_confirm_have_exact_separate_owners() -> None:
    route = _between("VIDEO_PUBLIC_ROUTE_MATRIX = {", "\n\n\ndef video_public_route_for_tool")
    handler = _between("async def handle_long_video_callback", "async def handle_storyboard_pack_callback")
    confirm = _between("async def handle_video_tail_callback", "async def handle_video_tail9_pending_text")
    assert '"entry_callback": "longvideo|public_guard"' in route
    assert '"invoice_reachable": True' in route[route.index('"multi_scene_film"'):]
    assert "start_public_video_scene2_step" in handler
    assert '"multi_scene_film"' in handler
    assert "handle_video_product_callback" not in handler
    assert "query.data =" not in handler
    assert "video_tail9_long_maintenance_text" in confirm
    maintenance_start = confirm.index('if not contract.get("execution_enabled")')
    maintenance_end = confirm.index('if owner == "video_edit":', maintenance_start)
    maintenance = confirm[maintenance_start:maintenance_end]
    assert "handle_product_video_public_confirm_callback" not in maintenance


def test_shared_invoice_and_status_contract_preserve_delivery_before_charge() -> None:
    invoice = _between("def video_tail9_invoice_text", "def video_tail9_long_maintenance_text")
    keyboard = _between("def video_tail9_invoice_keyboard", "def video_tail9_invoice_text")
    assert "Sản phẩm" in invoice
    assert "Số cảnh" in invoice
    assert "Thời lượng" in invoice
    assert "Tỉ lệ" in invoice
    assert "Âm thanh/Add-on" in invoice
    assert "Logo/Watermark" in invoice
    assert "message_id" in invoice
    assert "biên nhận" in invoice
    assert keyboard.count("video_tail|confirm") == 1
    for product in (
        "video_ai_realistic",
        "trend_video",
        "script_to_video",
        "storyboard_to_video",
        "self_shot_scene_change",
        "self_shot_cinematic_transform",
        "frame_video",
    ):
        status = video_tail9.status_contract(product)
        assert status["stages"][-2:] == ("delivering", "delivered")
        assert status["delivery_requires_message_id"] is True
        assert status["receipt_after_delivery"] is True
        assert status["charge_after_receipt"] is True


def test_preconfirm_contract_has_zero_side_effects_and_no_provider_submission() -> None:
    compatibility = video_tail9.package_compatibility(
        "storyboard_to_video",
        scene_count=2,
        ratio="9:16",
        quality_tier_id=300,
        asset_ready=True,
        input_valid=True,
    )
    assert compatibility["ok"] is True
    assert compatibility["side_effects"] == {
        "job": 0,
        "outbox": 0,
        "provider_calls": 0,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
    service_source = (ROOT / "services" / "video_tail9.py").read_text(encoding="utf-8")
    catalog_source = (ROOT / "services" / "video_uifreeze1.py").read_text(encoding="utf-8")
    for forbidden in ("provider.submit", "requests.post", "httpx.post", "deduct_xu", "charge_wallet"):
        assert forbidden not in service_source
        assert forbidden not in catalog_source
