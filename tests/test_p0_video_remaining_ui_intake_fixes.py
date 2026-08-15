from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from services import video_scene3_flow, video_scene_prompt_builder, video_selfshot2, video_uiflow3


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    pattern = re.compile(rf"^(?:async )?def {re.escape(name)}\(", re.MULTILINE)
    match = pattern.search(BOT_SOURCE)
    assert match, f"missing function: {name}"
    next_match = re.search(
        r"\n(?=@|(?:async )?def [A-Za-z_])",
        BOT_SOURCE[match.end() :],
    )
    end = match.end() + next_match.start() if next_match else len(BOT_SOURCE)
    return BOT_SOURCE[match.start() : end]


def _runtime_function(name: str, namespace: dict):
    source = _function_source(name).rsplit("\n@", 1)[0]
    exec("from __future__ import annotations\n" + source, namespace)
    return namespace[name]


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _bridge_prompt_state(product: str) -> dict:
    marker_key = {
        "script_image_video": "script_entity_bridge",
        "video_trend": "trend_entity_bridge",
    }[product]
    scene_count = 5 if product == "script_image_video" else 2
    state = video_uiflow3.new_state(
        product,
        draft_id=f"focused-quick-{product}",
        entry_mode="prompt_video" if product == "script_image_video" else "selected_trend",
    )
    state = video_uiflow3.set_source_metadata(
        state,
        source_kind="focused_test",
        source_title="Nội dung đã tiếp nhận",
    )
    state = video_uiflow3.set_format(
        state,
        ratio="9:16",
        target_duration_seconds=scene_count * 8,
    )
    state = video_uiflow3.set_content_candidate(
        state,
        source="approved_script" if product == "script_image_video" else "selected_trend",
        original_intent="Một nội dung hoàn chỉnh về du lịch xanh.",
        profile_id="social_creator_trend",
        approved_brief={
            "title": "Du lịch xanh",
            "summary": "Giới thiệu hành trình du lịch xanh có mở đầu, diễn biến và kết thúc.",
        },
    )
    state = video_uiflow3.lock_content(state)
    state = video_uiflow3.confirm_scene_count(state, scene_count)
    state = video_uiflow3.suggest_scene_plan(state)
    legacy = dict(state.get("legacy_compat") or {})
    legacy[marker_key] = {"active": True, "bridge_key": f"focused-{product}"}
    state["legacy_compat"] = legacy
    return video_uiflow3.normalize_state(state)


def test_script_and_trend_quick_prompt_compiler_uses_the_generic_builder_without_side_effects():
    compile_bridge = _runtime_function(
        "video_entity_bridge_compile_quick_prompts",
        {
            "video_uiflow3": video_uiflow3,
            "video_entity_bridge_marker": lambda state: next(
                (
                    value
                    for key, value in dict(state.get("legacy_compat") or {}).items()
                    if key in {"script_entity_bridge", "trend_entity_bridge"}
                    and bool(dict(value or {}).get("active"))
                ),
                {},
            ),
            "video_ai_real_enabled_scene3_values": lambda *_args, **_kwargs: [],
            "video_scene3_flow": video_scene3_flow,
            "VIDEO_AI_REAL_PILOT_REQUIREMENT_CATEGORIES": (),
            "video_scene_prompt_builder": video_scene_prompt_builder,
            "safe_int": _safe_int,
            "hashlib": hashlib,
            "json": json,
        },
    )

    for product in ("script_image_video", "video_trend"):
        original = _bridge_prompt_state(product)
        compiled = compile_bridge(original)
        assert len(compiled["scenes"]) == (5 if product == "script_image_video" else 2)
        assert all(scene.get("provider_prompt") for scene in compiled["scenes"])
        assert all(scene.get("visual_prompt") == scene.get("provider_prompt") for scene in compiled["scenes"])
        assert all(scene.get("negative_prompt") for scene in compiled["scenes"])
        assert all(scene.get("compiled_prompt_status") == "compiled" for scene in compiled["scenes"])
        assert compiled["legacy_compat"]["product_quick_prompt_compile"]["product"] == product
        assert compiled["side_effects"] == original["side_effects"] == {
            "provider_calls": 0,
            "jobs": 0,
            "outbox": 0,
            "wallet_mutations": 0,
            "xu_charged": 0,
        }

    builder = _function_source("video_ai_real_build_quick_plan")
    assert "if video_entity_bridge_marker(state):" in builder
    assert "video_entity_bridge_compile_quick_prompts(state)" in builder
    assert "else:\n        state = video_ai_real_compile_state(state)" in builder


def test_trend_cached_search_prefers_query_matches_and_keeps_real_source_metadata():
    fallback = _runtime_function(
        "video_trend2_catalog_search_fallback",
        {
            "unicodedata": unicodedata,
            "re": re,
            "safe_int": _safe_int,
            "deepcopy": deepcopy,
        },
    )
    rows = [
        {
            "trend_id": "other",
            "title": "Mở hộp sản phẩm",
            "summary": "Một video review ngắn.",
            "category": "Review",
            "platform": "TikTok",
            "keywords": ["review"],
            "source_name": "Nguồn A",
            "source_url": "https://example.com/review",
            "stale": False,
        },
        {
            "trend_id": "green-travel",
            "title": "Du lịch xanh",
            "summary": "Hành trình bền vững.",
            "category": "Vlog",
            "platform": "Reels",
            "keywords": ["du lịch", "xanh"],
            "source_name": "Nguồn B",
            "source_url": "https://example.com/green-travel",
            "stale": False,
        },
        {
            "trend_id": "invalid-source",
            "title": "Du lịch xanh không nguồn",
            "source_name": "",
            "source_url": "",
        },
    ]

    results = fallback("du lich xanh", rows)

    assert [item["trend_id"] for item in results] == ["green-travel", "other"]
    assert results[0]["intake_lane"] == "search"
    assert results[0]["catalog_fallback"] is True
    assert results[0]["online_search"] is False
    assert results[0]["source_name"] == "Nguồn B"
    assert results[0]["source_url"] == "https://example.com/green-travel"


def test_all_four_trend_lanes_join_the_same_scene_count_ratio_and_entity_continuation():
    callback = _function_source("_handle_video_trend2_callback_impl")
    pending = _function_source("handle_video_trend2_pending_text")

    search_pick = callback.split('if action == "search_pick":', 1)[1].split(
        'if action == "help":', 1
    )[0]
    video_accept = callback.split('if action == "video_accept":', 1)[1].split(
        'if action == "search":', 1
    )[0]
    catalog_pick = callback.split('if action == "pick":', 1)[1].split(
        'if action == "manual_trend":', 1
    )[0]
    manual_input = pending.split('elif pending == "manual_trend":', 1)[1].split(
        'elif pending == "scene_count":', 1
    )[0]
    ratio = callback.split('if action == "ratio":', 1)[1].split(
        'if action == "ratio_custom":', 1
    )[0]

    for branch in (search_pick, video_accept, catalog_pick, manual_input):
        assert '"scene_count"' in branch
    assert "video_trend_prepare_entity_bridge" in ratio
    assert 'return await video_uiflow3_render(query, context, bridge)' in ratio


def test_selfshot_hub_has_two_buttons_per_row_and_one_exact_video_menu_return():
    hub_keyboard = _runtime_function(
        "video_selfshot_product_hub_keyboard",
        {"video_scene3_keyboard": lambda rows: rows},
    )
    rows = hub_keyboard()

    assert all(len(row) == 2 for row in rows)
    assert rows[0] == [
        ("🎥 Tự quay & đổi cảnh AI", "vproduct|selfshot_product|scene_change"),
        ("🎥 Tự quay & biến đổi điện ảnh", "vproduct|selfshot_product|cinematic"),
    ]
    assert rows[-1] == [
        ("⬅️ Quay lại", "menu|main_video"),
        ("📖 Xem hướng dẫn", "menu|guide_video_ai"),
    ]
    assert sum(callback == "menu|main_video" for row in rows for _label, callback in row) == 1


def test_trend_and_selfshot2_scene_ratio_buttons_have_icons_without_changing_callbacks():
    trend_count = _function_source("video_trend2_scene_count_keyboard")
    trend_ratio = _function_source("video_trend2_ratio_keyboard")
    selfshot_count = video_selfshot2.screen_model(
        "scene_count",
        video_selfshot2.initial_draft(),
    )["rows"]
    selfshot_ratio = video_selfshot2.screen_model(
        "ratio",
        video_selfshot2.initial_draft(),
    )["rows"]

    for label, callback in (
        ("🎬 1 cảnh", "vtrend|scenes|1"),
        ("🎬 20 cảnh", "vtrend|scenes|20"),
    ):
        assert label in trend_count
        assert callback in trend_count
    for label, callback in (
        ("📱 Dọc 9:16", "vtrend|ratio|9:16"),
        ("🖥 Ngang 16:9", "vtrend|ratio|16:9"),
        ("⬜ Vuông 1:1", "vtrend|ratio|1:1"),
        ("📱 Dọc 4:5", "vtrend|ratio|4:5"),
    ):
        assert label in trend_ratio
        assert callback in trend_ratio
    assert selfshot_count[0] == [
        ("🎬 1 cảnh", "vproduct|ss2|scene_count|1"),
        ("🎬 2 cảnh", "vproduct|ss2|scene_count|2"),
    ]
    assert selfshot_ratio[0] == [
        ("📱 Dọc 9:16", "vproduct|ss2|ratio|9:16"),
        ("🖥 Ngang 16:9", "vproduct|ss2|ratio|16:9"),
    ]


def test_selfshot_local_analysis_uses_the_cloud_local_download_adapter():
    downloaded = []

    async def fake_download(_context, source, maximum_bytes, *, read_timeout=60.0):
        downloaded.append((dict(source), maximum_bytes, read_timeout))
        return b"focused-video-bytes"

    validation = SimpleNamespace(
        MAX_UPLOAD_BYTES=1024 * 1024,
        ALLOWED_SOURCE_EXTENSIONS={".mp4"},
        validate_extension=lambda file_name, _allowed: str(file_name),
        probe_video_file=lambda _path: {
            "duration": 8.0,
            "width": 1080,
            "height": 1920,
            "fps": 30.0,
            "format_name": "mp4",
            "video_codec": "h264",
            "audio_stream_count": 1,
        },
        validate_source_metadata=lambda probe, *, file_size, **_kwargs: {
            "ok": True,
            "bytes": file_size,
            **probe,
        },
    )
    local_analysis = SimpleNamespace(
        analyze_video_file=lambda _path, **kwargs: {
            "analysis_revision": kwargs["analysis_revision"],
            "tracking_source": "focused_local_test",
            "subject_candidates": [],
            "motion_summary": "Chuyển động đã nhận diện",
            "camera_summary": "Máy quay ổn định",
            "visual_context_summary": "Bối cảnh ngoài trời",
        }
    )
    inspect_source = _runtime_function(
        "inspect_selfshot_source",
        {
            "video_local_validation": validation,
            "video_selfshot_local_analysis": local_analysis,
            "download_video_editor_asset_bytes": fake_download,
            "safe_int": _safe_int,
            "tempfile": tempfile,
            "os": os,
            "hashlib": hashlib,
            "asyncio": asyncio,
        },
    )

    result = asyncio.run(
        inspect_source(
            SimpleNamespace(bot=object()),
            {
                "source_asset": {
                    "file_id": "telegram-file-id",
                    "file_name": "trend.mp4",
                    "file_size": len(b"focused-video-bytes"),
                },
                "source_segment": {
                    "start_ms": 0,
                    "end_ms": 8000,
                    "start_seconds": 0,
                    "end_seconds": 8,
                },
            },
            "ss2",
        )
    )

    assert result["ok"] is True
    assert downloaded == [
        ({"file_id": "telegram-file-id"}, validation.MAX_UPLOAD_BYTES, 120.0)
    ]
