from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from services import video_tail9


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")

LOCKED_UI_FUNCTION_HASHES = {
    "main_video_keyboard": "54d1b1cc1ea8d5a60b45005cc3ce13703f9a3da9f4c4d207cf31f5094f452ffa",
    "menu_text_main_video_i18n": "43945a07f7680b612def8a7b5f9b38f8412cf048775f775847ea10ae07f02931",
    "video_tail9_addon_text": "6b406611841bc16e30fc6a497f625034b9b2d1281437b9bee6a6c272135165e5",
    "video_tail9_addon_keyboard": "d7bc422fec98528121ec77406ab99027fd45663429e2dd6e7aa4c85fa6439ee7",
    "video_tail9_review_text": "27ec69d92c8c044422199c9107f8ab575a2ad23b3ec5bfcfd96334015de30127",
    "video_tail9_review_keyboard": "b47e3173a3d3c177eb22d205bbaa45dd561196c38806ce2a1f1db24e8037623a",
    "video_tail9_quality_text": "163bdaa0efd2c81ddcd03643ddb909c9007e52fd467960a4050cf651d1a6b676",
    "video_tail9_quality_keyboard": "a0bc0dba9e4419992a6f7fa0298fea935508891196fd9ecd28f4a1c5901bdc3e",
    "video_tail9_invoice_text": "975d244430c7f4e7ef6897d70a9cc53c001a5d5ae87e390fc40d157c87213bde",
    "video_tail9_invoice_keyboard": "fc65e49bca1942bfe5487f8e1ec1775db95fa4e09fa3df7b377c42a103fefedb",
    "video_tail9_confirm_text": "c68ffa14a128510d1c4900fcb5766af4de542c7d2298bb304f14e71fa9c27466",
    "video_tail9_confirm_keyboard": "d5739136ec3bfb266710de01c4479b3082e162bdb68a07583e8ad2312ef00252",
    "video_tail9_status_recovery_text": "21ebd133e413234485c64953ee433618dfcbe4c6d6262b599da7c0a84322928d",
    "video_tail9_status_recovery_keyboard": "59911e71764d07aaf1ce77bd7251237c385cb83a32fb7e08738c9184347b577f",
}

LANES = (
    ("PV-L01", "video_trend", 2),
    ("PV-L02", "video_ai_real", 2),
    ("PV-L03", "script_image_video", 5),
    ("PV-L04", "frame_video_local", 2),
    ("PV-L05", "self_shot_scene_change", 2),
    ("PV-L06", "storyboard_prompt", 2),
    ("PV-L07", "multi_scene_film", 2),
    ("PV-L08", "video_idea", 2),
    ("PV-L09", "video_local_edit", 2),
)


@pytest.mark.parametrize(("case_id", "product_type", "scene_count"), LANES)
def test_each_video_menu_lane_has_invoice_confirm_and_terminal_status_contract(
    case_id: str,
    product_type: str,
    scene_count: int,
) -> None:
    contract = video_tail9.commercial_contract(product_type)
    assert contract["product_type"], case_id
    assert contract["public_planning_enabled"] is True, case_id
    assert contract["execution_enabled"] is True, case_id
    assert contract["supported_quality_tiers"], case_id

    selected_tier = int(contract["supported_quality_tiers"][0])
    state = video_tail9.new_state(
        product_type=product_type,
        execution_product_type=str(contract["executor_product_type"]),
        session_id=f"{case_id}-tail-status",
        scene_count=scene_count,
        ratio="9:16" if product_type != "video_local_edit" else "keep",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "manual",
            "canonical_content_mode": "manual",
            "selected_prompt_text": f"{case_id} approved content",
            "per_scene_content": [
                {"scene_index": index, "provider_prompt": f"Scene {index}"}
                for index in range(1, scene_count + 1)
            ],
            "plan_status": "ready",
        },
    )
    invoiced = video_tail9.select_package(
        state,
        quality_tier_id=str(selected_tier),
        package_id=f"product_video_{selected_tier}",
        pricing_snapshot={
            "routing_quality_tier": selected_tier,
            "quality_xu": selected_tier,
            "total_xu": selected_tier * scene_count,
        },
        capability_snapshot={
            "ok": True,
            "required_capability": contract["required_capability"],
        },
    )

    assert invoiced["status_stage"] == "invoice", case_id
    assert video_tail9.invoice_allowed(invoiced) == (True, "ok"), case_id
    confirmed, created = video_tail9.confirm_once(invoiced, f"confirm-{case_id}")
    replayed, created_again = video_tail9.confirm_once(
        confirmed,
        f"confirm-{case_id}",
    )
    assert created is True and created_again is False, case_id
    assert replayed["status_stage"] == "confirmed", case_id
    assert replayed["charge_state"] == "not_charged", case_id

    status = video_tail9.status_contract(product_type)
    assert status["stages"][-1] == "delivered", case_id
    assert status["delivery_requires_message_id"] is True, case_id
    assert status["receipt_after_delivery"] is True, case_id
    assert status["charge_after_receipt"] is True, case_id


def test_shared_tail_flow_edges_remain_quality_invoice_confirm_status() -> None:
    handler = BOT_SOURCE[
        BOT_SOURCE.index("async def handle_video_tail_callback") : BOT_SOURCE.index(
            "async def handle_video_tail9_pending_text"
        )
    ]
    assert 'return await video_tail9_render(query, uid, context, "invoice")' in handler
    assert 'return await video_tail9_render(query, uid, context, "confirm")' in handler
    assert "video_tail9_prepare_submit_status(" in handler
    assert "video_tail9_render_confirmed_status(" in handler
    assert handler.index('if section == "quality":') < handler.index(
        'if section == "confirm":'
    )


@pytest.mark.parametrize(
    ("function_name", "expected_sha256"),
    tuple(LOCKED_UI_FUNCTION_HASHES.items()),
)
def test_completed_video_ui_function_bytes_are_locked(
    function_name: str,
    expected_sha256: str,
) -> None:
    match = re.search(
        rf"(?ms)^def {re.escape(function_name)}\(.*?(?=^(?:async )?def [A-Za-z_]|\Z)",
        BOT_SOURCE,
    )
    assert match, function_name
    actual = hashlib.sha256(match.group(0).rstrip().encode("utf-8")).hexdigest()
    assert actual == expected_sha256, function_name
