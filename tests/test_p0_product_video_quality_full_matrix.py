from __future__ import annotations

from pathlib import Path

import pytest

import bot
from services import video_ai_real_pricing, video_tail9, video_uifreeze1


TIER_IDS = (200, 300, 400, 500, 600, 700, 800, 1000, 1200, 1500)
BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _callbacks(markup) -> set[str]:
    return {
        str(button.callback_data or "")
        for row in markup.inline_keyboard
        for button in row
        if str(button.callback_data or "")
    }


@pytest.mark.parametrize(
    ("product_type", "required_capability"),
    (
        ("video_ai_real", "text_to_video"),
        ("video_ai_image", "image_to_video"),
    ),
)
def test_video_ai_real_two_scene_catalog_exposes_every_public_quality(
    product_type: str,
    required_capability: str,
) -> None:
    report = video_uifreeze1.catalog_report(
        product_type,
        scene_count=2,
        ratio="9:16",
        required_capability=required_capability,
    )

    assert report["ok"] is True
    assert len(report["tier_ids"]) == len(TIER_IDS)
    assert set(report["tier_ids"]) == set(TIER_IDS)
    assert {int(item["tier_id"]) for item in report["offers"]} == set(TIER_IDS)
    assert report["side_effects"] == {
        "job": 0,
        "outbox": 0,
        "provider_calls": 0,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }


def test_video_ai_real_quality_keyboard_has_one_real_callback_for_every_tier() -> None:
    tail = video_tail9.new_state(
        product_type="video_ai_real",
        execution_product_type="video_ai_prompt",
        session_id="quality-keyboard-two-scenes",
        scene_count=2,
        ratio="9:16",
    )
    catalog = video_uifreeze1.catalog_report(
        "video_ai_real",
        scene_count=2,
        ratio="9:16",
        required_capability="text_to_video",
    )
    callbacks = _callbacks(bot.video_tail9_quality_keyboard(tail, catalog))

    assert {
        f"video_tail|quality|select|{tier_id}"
        for tier_id in TIER_IDS
    }.issubset(callbacks)
    assert 'if section == "quality":' in BOT_SOURCE
    assert 'if action == "select":' in BOT_SOURCE


@pytest.mark.parametrize("tier_id", TIER_IDS)
def test_each_video_ai_real_tier_survives_invoice_and_idempotent_confirm(
    tier_id: int,
) -> None:
    state = video_tail9.new_state(
        product_type="video_ai_real",
        execution_product_type="video_ai_prompt",
        session_id=f"quality-matrix-{tier_id}",
        plan_revision=3,
        scene_count=2,
        ratio="9:16",
    )
    state = video_tail9.apply_content_contract(
        state,
        {
            "content_source": "manual",
            "canonical_content_mode": "manual",
            "selected_prompt": f"Two scene prompt for tier {tier_id}",
            "scene_drafts": [
                {"scene_index": 1, "provider_prompt": "Scene one"},
                {"scene_index": 2, "provider_prompt": "Scene two"},
            ],
            "plan_approved": True,
        },
    )
    quality = video_ai_real_pricing.public_quality_by_tier(tier_id)
    pricing = {
        "quality_tier_id": tier_id,
        "quality_xu": tier_id,
        "routing_quality_tier": tier_id,
        "scene_count": 2,
        "unit_xu": int(quality["unit_xu"]),
        "total_xu": int(quality["unit_xu"]) * 2,
    }

    invoiced = video_tail9.select_package(
        state,
        quality_tier_id=str(tier_id),
        package_id=f"product_video_{tier_id}",
        pricing_snapshot=pricing,
        capability_snapshot={"ok": True, "required_capability": "text_to_video"},
    )

    assert invoiced["quality_tier_id"] == str(tier_id)
    assert invoiced["package_id"] == f"product_video_{tier_id}"
    assert invoiced["invoice_id"].endswith(f":{tier_id}")
    assert invoiced["pricing_snapshot"]["routing_quality_tier"] == tier_id
    assert video_tail9.invoice_allowed(invoiced) == (True, "ok")

    confirmed, created = video_tail9.confirm_once(invoiced, f"confirm-{tier_id}")
    duplicate, created_again = video_tail9.confirm_once(confirmed, f"confirm-{tier_id}")
    assert created is True
    assert created_again is False
    assert duplicate["quality_tier_id"] == str(tier_id)
    assert duplicate["pricing_snapshot"]["routing_quality_tier"] == tier_id
    assert duplicate["job_id"] == ""
    assert duplicate["charge_state"] == "not_charged"


@pytest.mark.parametrize(
    ("product_type", "tier_id"),
    (
        ("script_image_video", 200),
        ("storyboard_prompt", 200),
        ("multi_scene_film", 700),
        ("video_ai_real", 250),
    ),
)
def test_unsupported_or_forged_quality_cannot_replace_the_current_invoice(
    product_type: str,
    tier_id: int,
) -> None:
    state = video_tail9.new_state(
        product_type=product_type,
        session_id=f"unsupported-{product_type}",
        scene_count=5 if product_type == "script_image_video" else 2,
        ratio="9:16",
    )
    before = video_tail9.normalize_state(state)

    with pytest.raises(ValueError, match="quality_tier_not_supported"):
        video_tail9.select_package(
            state,
            quality_tier_id=str(tier_id),
            package_id=f"product_video_{tier_id}",
            pricing_snapshot={"quality_xu": tier_id, "total_xu": tier_id * 2},
            capability_snapshot={"ok": True},
        )

    assert video_tail9.normalize_state(state) == before
