from __future__ import annotations

import re
from pathlib import Path

from services import video_long_planning, video_uifreeze1


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
SERVICE_SOURCE = (ROOT / "services" / "video_uifreeze1.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    markers = (f"def {name}(", f"async def {name}(")
    starts = [BOT_SOURCE.find(marker) for marker in markers]
    start = min(position for position in starts if position >= 0)
    next_def = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[start + 1 :])
    end = start + 1 + next_def.start() if next_def else len(BOT_SOURCE)
    return BOT_SOURCE[start:end]


def test_public_video_menu_order_is_frozen_without_callback_changes() -> None:
    assert video_uifreeze1.PUBLIC_MENU_ROWS == (
        ("video_trend", "video_ai_real"),
        ("script_image_video", "frame_video_local"),
        ("self_shot_scene_change", "storyboard_prompt"),
        ("multi_scene_film", "video_idea"),
        ("video_local_edit", "video_downloader"),
        ("main_menu", "video_guide"),
    )
    assert "VIDEO_PUBLIC_MENU_ROWS = video_uifreeze1.PUBLIC_MENU_ROWS" in BOT_SOURCE
    menu_builder = _function_source("main_video_keyboard")
    assert "VIDEO_PUBLIC_MENU_ROWS" in menu_builder
    assert "entry_callback" in menu_builder
    assert "callback_data=str(route.get(\"entry_callback\")" in menu_builder


def test_long_video_opens_catalog_but_keeps_execution_locked() -> None:
    assert video_long_planning.PUBLIC_ENABLED is False
    assert "multi_scene_film" in video_uifreeze1.PUBLIC_EXECUTION_LOCKED_PRODUCTS
    report = video_uifreeze1.catalog_report("multi_scene_film", scene_count=1)
    assert report["ok"] is True
    assert report["tier_ids"] == [300, 400, 500, 600, 800, 1000, 1200, 1500]


def test_storyboard_catalog_keeps_compatible_image_video_packages_visible() -> None:
    image_to_video = video_uifreeze1.catalog_report(
        "storyboard_prompt",
        scene_count=2,
        ratio="9:16",
        required_capability="image_to_video",
    )
    first_last = video_uifreeze1.catalog_report(
        "storyboard_prompt",
        scene_count=2,
        ratio="9:16",
        required_capability="first_last_frame_video",
    )
    assert image_to_video["ok"] is True
    assert first_last["ok"] is True
    assert image_to_video["tier_ids"] == [300, 400, 500, 600, 800, 1000, 1200, 1500]
    assert first_last["tier_ids"] == image_to_video["tier_ids"]
    package_source = _function_source("storyboard2_package_resolutions")
    assert "video_uifreeze1.catalog_report" in package_source
    assert "video_provider_catalog" not in package_source


def test_canonical_products_share_one_tier_identity_and_order() -> None:
    expected = {
        "video_ai_real",
        "script_image_video",
        "storyboard_prompt",
        "video_trend",
        "video_local_edit",
        "self_shot_scene_change",
        "self_shot_cinematic_transform",
        "video_idea",
    }
    assert expected <= video_uifreeze1.CANONICAL_PRICING_PRODUCTS
    for product in expected:
        report = video_uifreeze1.catalog_report(
            product,
            scene_count=2,
            ratio="9:16",
            required_capability="image_to_video" if product == "storyboard_prompt" else "",
        )
        assert report["ok"] is True
        assert report["tier_ids"] == sorted(report["tier_ids"], key=video_uifreeze1.QUALITY_TIER_ORDER.index)
        for offer in report["offers"]:
            canonical = video_uifreeze1.tier_spec(offer["tier_id"])
            assert offer["name"] == canonical["name"]
            assert offer["public_level"] == canonical["public_level"]
            assert offer["public_detail"] == canonical["public_detail"]
    description_source = _function_source("video_scene3_public_quality_spec")
    assert "video_uifreeze1.tier_spec" in description_source
    assert "video_provider_catalog" not in description_source


def test_framevideo_keeps_its_separate_commercial_pricing_flow() -> None:
    report = video_uifreeze1.catalog_report("frame_video_local", scene_count=2)
    assert report["ok"] is False
    assert report["framevideo_excluded"] is True
    assert report["uses_canonical_pricing"] is False
    assert "frame_video_commercial" in BOT_SOURCE
    assert '"excluded_products": ["frame_video_local"]' in BOT_SOURCE


def test_quality_catalog_is_ui_only_and_preconfirm_side_effects_are_zero() -> None:
    forbidden = (
        "requests.",
        "httpx.",
        "aiohttp.",
        "urlopen(",
        "provider.submit",
        "subprocess",
        "update_wallet",
        "deduct_xu",
        "charge_wallet",
        "charge_xu",
        "open(",
    )
    assert all(token not in SERVICE_SOURCE for token in forbidden)
    report = video_uifreeze1.catalog_report("video_ai_real", scene_count=3)
    assert report["side_effects"] == {
        "job": 0,
        "outbox": 0,
        "provider_calls": 0,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }


def test_menu_and_quality_callbacks_have_one_owner_and_exact_back_rows() -> None:
    matrix = _function_source("video_route_matrix_rows")
    audit = _function_source("video_route_audit_payload")
    assert 'row_item["expected_handler"] == row_item["actual_handler"]' in matrix
    assert 'row_item["back_target"] == "menu|main_video"' in matrix
    assert "all(row.get(\"ok\") for row in rows)" in audit
    storyboard_keyboard = _function_source("storyboard2_quality_keyboard")
    assert 'f"vprofile|tier|{price}"' in storyboard_keyboard
    assert '[("⬅️ Quay lại", "vstory|review_from_quality"), ("🏠 Menu chính", "menu|main")]' in storyboard_keyboard
    assert BOT_SOURCE.count(
        'CallbackQueryHandler(handle_storyboard2_callback, pattern=r"^vstory\\|")'
    ) == 1
    assert BOT_SOURCE.count(
        'CallbackQueryHandler(handle_video_tail_callback, pattern=r"^video_tail\\|", block=True)'
    ) == 1
