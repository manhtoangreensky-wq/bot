from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from services import video_flow7, video_storyboard2, video_trend_catalog


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    markers = (f"def {name}(", f"async def {name}(")
    positions = [BOT_SOURCE.find(marker) for marker in markers]
    start = min(position for position in positions if position >= 0)
    next_def = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[start + 1 :])
    end = start + 1 + next_def.start() if next_def else len(BOT_SOURCE)
    return BOT_SOURCE[start:end]


def test_script_uses_canonical_count_ratio_source_order_and_long_form_bounds() -> None:
    sequence = video_flow7.product_sequence("script_image_video")
    assert sequence[:3] == ("scene_count", "aspect_ratio", "content_source")
    assert "script_mode" not in sequence
    assert "scene_count_confirm" not in sequence

    public_open = _function_source("handle_video_product_callback")
    assert '"script_image_video"}' in public_open
    assert "start_at_scene_count=True" in public_open

    bounds = _function_source("video_profile_scene_count_bounds")
    count_keyboard = _function_source("video_profile_scene1_count_keyboard")
    count_text = _function_source("video_profile_scene1_count_text")
    assert 'return (5, 20) if video_flow7_kind' in bounds
    for count in (5, 6, 8, 10, 15, 20):
        assert f'"vprofile|count|{count}"' in count_keyboard
    assert '"vprofile|count|1"' in count_keyboard
    assert "40–160 giây" in count_text


def test_ai_real_keeps_three_input_types_then_three_distinct_content_sources() -> None:
    labels = [
        label
        for row in video_flow7.entry_rows("video_ai_real")
        for label, _callback in row
    ]
    assert labels[:3] == ["✨ Prompt → Video", "🖼 Ảnh → Video", "🎞 Video → Video"]
    assert video_flow7.product_sequence("video_ai_real")[:4] == (
        "scene_count",
        "aspect_ratio",
        "ai_input_type",
        "content_source",
    )

    input_keyboard = _function_source("video_scene3_ai_input_keyboard")
    source_keyboard = _function_source("video_scene3_content_source_keyboard")
    for callback in (
        "vprofile|ai_input|prompt_video",
        "vprofile|ai_input|image_video",
        "vprofile|ai_input|video_video",
    ):
        assert callback in input_keyboard
    for callback in (
        "vprofile|source|profiles",
        "vprofile|source|idea",
        "vprofile|source|manual",
    ):
        assert callback in source_keyboard


def test_all_public_product_ratio_screens_expose_only_four_ratios_and_navigation() -> None:
    for name in (
        "video_scene3_aspect_keyboard",
        "storyboard2_ratio_keyboard",
        "video_trend2_ratio_keyboard",
    ):
        source = _function_source(name)
        assert "9:16" in source or "9x16" in source
        assert "16:9" in source or "16x9" in source
        assert "1:1" in source or "1x1" in source
        assert "4:5" in source or "4x5" in source
        assert "Gợi ý" not in source
        assert "suggest" not in source.casefold()
        assert "Tự nhập" not in source
        assert "custom" not in source.casefold()


def test_storyboard_has_two_entry_branches_and_separate_content_source_screen() -> None:
    entry = video_flow7.entry_rows("storyboard_prompt")
    assert entry == [
        [("✨ Tạo storyboard AI", "vstory|ai"), ("📎 Gửi storyboard có sẵn", "vstory|upload")]
    ]
    entry_keyboard = _function_source("storyboard2_entry_keyboard")
    source_keyboard = _function_source("storyboard2_content_source_keyboard")
    profiles_keyboard = _function_source("storyboard2_profiles_keyboard")
    suggestion_keyboard = _function_source("storyboard2_suggestion_keyboard")
    assert "Bắt đầu Storyboard" not in entry_keyboard
    assert "Tạo storyboard AI" in entry_keyboard
    assert "Gửi storyboard có sẵn" in entry_keyboard
    assert "vstory|idea_source" in source_keyboard
    assert "vstory|content_manual" in source_keyboard
    assert "vstory|idea_source" not in profiles_keyboard
    assert "vstory|content_manual" not in profiles_keyboard
    assert 'range(1, 6)' in suggestion_keyboard

    board = video_storyboard2.default_state()
    assert board["scene_count"] == 0
    assert board["content_source"] == ""


def test_trend_catalog_always_has_twenty_provider_free_media_formats_five_at_a_time() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        first = video_trend_catalog.seed_media_catalog(conn)
        second = video_trend_catalog.seed_media_catalog(conn)
        rows = video_trend_catalog.list_media_items(conn, limit=100)
    finally:
        conn.close()

    assert first == {"inserted": 20, "updated": 0}
    assert second == {"inserted": 0, "updated": 0}
    assert len(rows) == 20
    assert len({row["trend_id"] for row in rows}) == 20
    assert all(row["content_safety"] == "approved_fallback_media_format" for row in rows)
    assert all(not row["popularity_signal"] for row in rows)

    entry = _function_source("video_trend2_entry_keyboard")
    catalog = _function_source("video_trend2_catalog_keyboard")
    after_ratio = _function_source("video_flow7_after_ratio")
    assert "Xem 5 trend media" in entry
    assert "Trend đã xu hướng" not in entry
    assert "Trend theo nhóm" not in entry
    assert 'enumerate(page, 1)' in catalog
    assert "Đổi 5 trend" in catalog
    assert 'flow_kind in {"script_to_video", "trend_video"}' in after_ratio
    assert 'return updated, "content_source"' in after_ratio


def test_public_callback_families_have_one_owner_and_no_generic_x_copy() -> None:
    owners = {
        "vprofile": 'CallbackQueryHandler(handle_video_profile_studio_callback, pattern=r"^vprofile\\|")',
        "vstory": 'CallbackQueryHandler(handle_storyboard2_callback, pattern=r"^vstory\\|")',
        "vtrend": 'CallbackQueryHandler(handle_video_trend2_callback, pattern=r"^vtrend\\|")',
    }
    for token, registration in owners.items():
        assert BOT_SOURCE.count(registration) == 1, token

    for name in (
        "handle_storyboard2_callback",
        "handle_video_trend2_callback",
    ):
        assert "Có lỗi khi xử lý lệnh" not in _function_source(name)


def test_preconfirm_planners_are_explicitly_side_effect_free() -> None:
    result = video_flow7.preflight(
        "script_image_video",
        {},
        owner_ready=False,
        worker_ready=False,
        capability_ready=False,
        package_available=False,
        provider_healthy=False,
        storage_ready=False,
        delivery_ready=False,
    )
    assert result["ok"] is False
    assert result["side_effects"] == {
        "job": 0,
        "outbox": 0,
        "invoice": 0,
        "provider_calls": 0,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
