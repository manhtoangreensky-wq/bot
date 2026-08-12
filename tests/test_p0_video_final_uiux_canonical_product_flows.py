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
    assert "5–20 cảnh" in count_text
    assert "40–160 giây" in count_text


def test_script_three_routes_must_choose_scene_count_then_ratio_before_branch_content() -> None:
    callback = _function_source("handle_video_product_callback")
    for branch in ("script_ai", "script_manual", "script_upload"):
        start = callback.index(f'if action == "{branch}"')
        end = callback.find('\n        if action == "', start + 1)
        block = callback[start : end if end >= 0 else len(callback)]
        assert '"script_scene_count"' in block
        assert f'script_entry_route="{branch}"' in block
        assert '"script_ai_goal"' not in block
        assert '"awaiting_existing_script"' not in block
        assert '"awaiting_script_file"' not in block

    count_block = callback[
        callback.index('if action == "script_entry_count"') :
        callback.index('if action == "script_entry_ratio"')
    ]
    assert '"script_scene_ratio"' in count_block
    assert 'script_entry_scene_count=count' in count_block
    assert 'existing_script = str(draft.get("manual_script_raw") or draft.get("script_text") or "")' in count_block
    assert "video_script_product.semantic_beats(existing_script, count)" in count_block
    assert "video_flow7_script_count_text(proposal)" in count_block

    ratio_block = callback[
        callback.index('if action == "script_entry_ratio"') :
        callback.index('if action == "script_goal_screen"')
    ]
    assert 'script_entry_ratio=ratio' in ratio_block
    assert '"script_ai_goal"' in ratio_block
    assert '"awaiting_existing_script"' in ratio_block
    assert '"awaiting_script_file"' in ratio_block

    count_keyboard = _function_source("video_script_entry_count_keyboard")
    ratio_keyboard = _function_source("video_script_entry_ratio_keyboard")
    for count in (5, 6, 8, 10, 15, 20):
        assert f"vproduct|script_entry_count|{count}" in count_keyboard
    assert "vproduct|script_entry_count|2" not in count_keyboard
    assert "vproduct|script_entry_count|20" in count_keyboard
    assert "vproduct|script_hub" in count_keyboard
    assert "vproduct|script_entry_ratio|9x16" in ratio_keyboard
    assert "vproduct|script_entry_ratio|4x5" in ratio_keyboard
    assert "vproduct|script_entry_count_screen" in ratio_keyboard


def test_script_custom_count_back_routes_and_ai_continuity_contract() -> None:
    callback = _function_source("handle_video_product_callback")
    text_handler = _function_source("handle_video_product_pending_text")
    renderer = _function_source("video_script_render_step")
    ai_prompt = (ROOT / "services" / "video_script_product.py").read_text(encoding="utf-8")
    script_handoff = _function_source("video_flow7_start_confirmed_script_state")
    scene_planner = (ROOT / "services" / "video_scene3_flow.py").read_text(encoding="utf-8")

    assert 'current_step == "awaiting_script_entry_scene_count"' in text_handler
    assert '"script_scene_ratio"' in text_handler
    assert 'script_entry_scene_count=count' in text_handler
    assert '"awaiting_script_ai_style": ("script_ai_duration", "script_style_label")' in text_handler
    assert "def duration_options(scene_count: int)" in ai_prompt
    assert "def duration_bounds(scene_count: int)" in ai_prompt
    duration_keyboard = _function_source("video_script_duration_keyboard")
    assert "video_script_product.duration_options(scene_count)" in duration_keyboard
    assert "Nhịp chuẩn" in duration_keyboard
    assert "Kịch bản dài" in duration_keyboard
    assert "video_script_duration_keyboard(session)" in renderer

    assert 'if action == "script_upload"' in callback
    assert 'if action == "script_file_replace"' in callback
    assert 'script_file_back_callback="vproduct|script_file_review"' in callback
    assert 'draft.get("script_file_back_callback")' in renderer
    assert '"awaiting_existing_script": "vproduct|script_entry_ratio_screen"' in renderer

    character_keyboard = _function_source("video_scene3_character_keyboard")
    assert '"vproduct|script_scene_review"' in character_keyboard
    assert 'str((state or {}).get("flow_kind") or "") == "script_to_video"' in character_keyboard
    assert '"script_scene_review"' in callback
    assert 'video_flow7_script_count_text(proposal)' in callback

    assert "KHÔNG phải một prompt video một cảnh" in ai_prompt
    assert "mạch ngữ cảnh xuyên suốt" in ai_prompt
    assert "prompt video chi tiết cho riêng cảnh đó" in ai_prompt
    assert 'idea_scene_beats=semantic_beats' in script_handoff
    assert 'script_text=raw_script' in script_handoff
    assert 'manual_script_raw=raw_script' in script_handoff
    assert 'context=selected_content[:1600]' not in script_handoff
    assert '"context": selected_content[:1600]' in script_handoff
    assert 'updated.get("idea_scene_beats")' in scene_planner
    assert 'semantic_beats=semantic_beats' in scene_planner


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


def test_reference_and_motion_entries_keep_their_distinct_product_flows() -> None:
    callback = _function_source("handle_video_product_callback")
    text_handler = _function_source("handle_video_product_pending_text")
    media_handler = _function_source("handle_video_product_pending_media")
    handoff = _function_source("video_flow7_start_single_scene_motion_state")
    after_ratio = _function_source("video_flow7_after_ratio")
    profile_callback = _function_source("handle_video_profile_studio_callback")
    intro_keyboard = _function_source("task3d_product_intro_keyboard")

    reference_block = callback[
        callback.index('if value == "video_reference"') :
        callback.index('if value == "motion_prompt"')
    ]
    assert "video_reference_hub_text(lang)" in reference_block
    assert "video_reference_hub_keyboard(lang)" in reference_block
    assert "start_public_video_scene2_step" not in reference_block

    motion_block = callback[
        callback.index('if value == "motion_prompt"') :
        callback.index("current_session = get_video_session(uid)")
    ]
    assert "selected_scene_count=1" in motion_block
    assert "scene_count=1" in motion_block
    assert "task3d_product_intro_keyboard(value, lang)" in motion_block
    assert '"video_ai_real", "video_reference", "motion_prompt", "multi_scene_film"' not in callback
    assert '"vproduct|input_text|motion_prompt"' in intro_keyboard
    assert '"vproduct|input_media|motion_prompt"' in intro_keyboard
    assert 'product_id == "motion_prompt"' in text_handler
    assert "video_flow7_start_single_scene_motion_state(" in text_handler
    assert 'product_id == "motion_prompt"' in media_handler
    assert "video_flow7_start_single_scene_motion_state(" in media_handler
    assert '"motion_prompt"' in handoff
    assert '"scene_count": 1' in handoff
    assert '"selected_scene_count": 1' in handoff
    assert '"step": "aspect_ratio"' in handoff
    assert 'source_product_id == "motion_prompt"' in after_ratio
    assert 'return updated, "content_source"' in after_ratio
    assert 'source_product_id == "motion_prompt"' in profile_callback
    assert "task3d_product_intro_text(source_product_id, lang)" in profile_callback

    owner_guard_start = callback.index(
        'session = get_video_session(uid)\n    product_id = str(session.get("product_id") or "")'
    )
    owner_guard = callback[
        owner_guard_start : callback.index("script_actions =", owner_guard_start)
    ]
    assert 'if product_id == "video_reference":' in owner_guard
    assert "video_reference_hub_keyboard(lang)" in owner_guard
    assert 'if product_id == "motion_prompt" and (' in owner_guard
    assert '(action, value)' in owner_guard
    assert '("input_text", "motion_prompt")' in owner_guard
    assert '("input_media", "motion_prompt")' in owner_guard
    assert 'task3d_product_intro_keyboard("motion_prompt", lang)' in owner_guard

    route_matrix = BOT_SOURCE[
        BOT_SOURCE.index("VIDEO_PUBLIC_ROUTE_MATRIX =") :
        BOT_SOURCE.index("def video_public_route_for_tool")
    ]
    assert '"flow_type": "reference_video_owner"' in route_matrix
    assert '"first_step": "hub"' in route_matrix
    assert '"flow_type": "single_scene_motion_prompt"' in route_matrix
    assert '"videoref|start"' in route_matrix


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
