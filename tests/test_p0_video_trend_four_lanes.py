from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from services import video_flow7, video_selfshot_local_analysis, video_trend_catalog


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    pattern = re.compile(rf"^(?:async )?def {re.escape(name)}\(", re.MULTILINE)
    match = pattern.search(BOT_SOURCE)
    assert match, f"missing function: {name}"
    next_match = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[match.end() :])
    end = match.end() + next_match.start() if next_match else len(BOT_SOURCE)
    return BOT_SOURCE[match.start() : end]


def test_trend_entry_has_four_lanes_in_two_rows() -> None:
    entry = _function_source("video_trend2_entry_keyboard")

    callbacks = (
        "vtrend|catalog|latest",
        "vtrend|manual_trend",
        "vtrend|search",
        "vtrend|video_upload",
    )
    for callback in callbacks:
        assert f'callback_data="{callback}"' in entry
    assert entry.index(callbacks[0]) < entry.index(callbacks[1])
    assert entry.index(callbacks[1]) < entry.index(callbacks[2])
    assert entry.index(callbacks[2]) < entry.index(callbacks[3])


def test_route_matrix_and_shared_catalog_declare_the_same_four_lanes() -> None:
    matrix_start = BOT_SOURCE.index("VIDEO_PUBLIC_ROUTE_MATRIX = {")
    trend_start = BOT_SOURCE.index('"video_trend": {', matrix_start)
    trend_end = BOT_SOURCE.index('"video_ai_real": {', trend_start)
    route = BOT_SOURCE[trend_start:trend_end]
    callbacks = (
        "vtrend|catalog|latest",
        "vtrend|manual_trend",
        "vtrend|search",
        "vtrend|video_upload",
    )

    for callback in callbacks:
        assert f'"{callback}"' in route
    assert tuple(
        callback
        for row in video_flow7.entry_rows("video_trend")
        for _label, callback in row
    ) == callbacks


def test_online_search_results_keep_source_and_search_lane() -> None:
    now = datetime(2026, 8, 14, 3, 0, tzinfo=timezone.utc)
    rows = video_trend_catalog.normalize_online_search_results(
        "du lich xanh",
        [
            {
                "title": "Du lich xanh dang duoc quan tam",
                "url": "https://example.com/green-travel",
                "source": "Example News",
                "summary": "<p>Mot xu huong du lich moi.</p>",
            }
        ],
        now=now,
    )

    assert len(rows) == 1
    assert rows[0]["intake_lane"] == "search"
    assert rows[0]["search_query"] == "du lich xanh"
    assert rows[0]["source_name"] == "Example News"
    assert rows[0]["source_url"] == "https://example.com/green-travel"
    assert rows[0]["summary"] == "Mot xu huong du lich moi."
    assert rows[0]["online_search"] is True


def test_search_callbacks_and_pending_text_join_scene_count_continuation() -> None:
    callback = _function_source("_handle_video_trend2_callback_impl")
    pending = _function_source("handle_video_trend2_pending_text")
    render = _function_source("video_trend2_render")

    assert 'if action == "search":' in callback
    assert 'if action == "search_pick":' in callback
    assert 'if action == "search_more":' in callback
    assert 'video_trend2_open_screen(state, "scene_count", parent="search_results")' in callback
    assert 'pending == "trend_search"' in pending
    assert "fetch_google_news_trends" in pending
    assert "normalize_online_search_results" in pending
    assert 'screen == "search_results"' in render


def test_local_video_analysis_includes_visual_context() -> None:
    analysis = video_selfshot_local_analysis.analyze_observations(
        [
            {
                "timestamp_seconds": 0,
                "width": 1080,
                "height": 1920,
                "detections": [],
                "motion_score": 0.22,
                "camera_shift": [3.5, 0.5],
                "mean_brightness": 0.78,
                "mean_saturation": 0.62,
                "mean_rgb": [190, 125, 70],
            }
        ],
        duration_seconds=8,
        source_hash="trend-video-hash",
    )

    assert analysis["visual_context"]["orientation"] == "vertical"
    assert analysis["visual_context"]["lighting"] == "bright"
    assert analysis["visual_context"]["color_style"] == "vivid"
    assert analysis["visual_context"]["color_temperature"] == "warm"
    assert analysis["visual_context"]["scene_change_count"] == 1
    assert analysis["visual_context_summary"]


def test_visual_context_extension_preserves_selfshot_tracking_contract() -> None:
    observations = []
    for index, timestamp in enumerate((0, 4)):
        observations.append({
            "timestamp_seconds": timestamp,
            "frame_index": index * 120,
            "width": 640,
            "height": 360,
            "detections": [
                {"kind": "person", "bbox": [40 + index * 10, 35, 130, 280], "confidence": 0.94, "face_detected": True},
                {"kind": "object", "bbox": [145 + index * 10, 145, 75, 70], "confidence": 0.81},
                {"kind": "pet", "bbox": [390 + index * 10, 185, 105, 120], "confidence": 0.87},
            ],
            "camera_shift": [0.2 + index * 0.2, 0.1],
            "motion_score": 0.14 + index * 0.04,
        })

    report = video_selfshot_local_analysis.analyze_observations(
        observations,
        duration_seconds=8,
        source_hash="selfshot-regression-hash",
    )

    assert len(report["person_tracks"]) == 1
    assert len(report["object_tracks"]) == 1
    assert len(report["pet_tracks"]) == 1
    assert len(report["subject_candidates"]) == 3
    assert report["relationship_candidates"]
    assert report["provider_calls"] == 0
    assert report["job_created"] is False
    assert report["outbox_created"] is False
    assert report["wallet_mutations"] == 0


def test_video_upload_lane_has_isolated_owner_analysis_and_scene_continuation() -> None:
    callback = _function_source("_handle_video_trend2_callback_impl")
    media = _function_source("handle_video_product_pending_media")
    owner = _function_source("video_trend2_upload_owner_valid")
    ready = _function_source("video_trend2_mark_video_ready")
    render = _function_source("video_trend2_render")
    snapshot = _function_source("video_trend2_source_snapshot")
    bridge = _function_source("video_trend_prepare_entity_bridge")

    assert 'if action == "video_upload":' in callback
    assert 'if action == "video_accept":' in callback
    assert '"awaiting_trend_video"' in callback
    assert 'video_trend2_open_screen(state, "scene_count", parent="video_analysis")' in callback
    assert "video_trend2_mark_video_ready" in callback
    assert 'current_step == "awaiting_trend_video"' in media
    assert 'product_id == "video_trend"' in media
    assert 'inspect_selfshot_source' in media
    assert "video_trend2_upload_owner_valid" in media
    assert '"video_trend_upload"' in owner
    assert '"trend_video_ready"' in ready
    assert 'screen == "video_analysis"' in render
    for key in (
        '"source_video_id"',
        '"source_video"',
        '"source_analysis"',
        '"analysis_revision"',
        '"analysis_provenance"',
    ):
        assert key in snapshot
    assert "video_uiflow3.add_source_asset" in bridge


def test_search_text_and_upload_media_keyboard_have_separate_owners() -> None:
    search_text = _function_source("video_trend2_search_results_text")
    upload_keyboard = _function_source("video_trend2_upload_keyboard")
    analysis_keyboard = _function_source("video_trend2_video_analysis_keyboard")
    callback = _function_source("_handle_video_trend2_callback_impl")

    assert 'if step == "awaiting_trend_video":' not in search_text
    assert "video_trend2_upload_token(state)" in upload_keyboard
    assert "vtrend|cancel_upload|" in upload_keyboard
    assert "vtrend|video_menu|" in upload_keyboard
    assert "video_trend2_upload_token(state)" in analysis_keyboard
    assert "vtrend|video_accept|" in analysis_keyboard
    assert "vtrend|video_back|" in analysis_keyboard
    assert "vtrend|video_menu|" in analysis_keyboard
    assert 'if action == "video_back":' in callback
    assert 'if action == "video_menu":' in callback
    assert "video_trend2_close_video_source_session" in callback
    assert "video_trend2_upload_token(state) != value" in callback
    entry_branch = callback.split('if action == "entry":', 1)[1].split(
        'if action == "cancel_upload":', 1
    )[0]
    cancel_branch = callback.split('if action == "cancel_upload":', 1)[1].split(
        'if action == "video_back":', 1
    )[0]
    upload_branch = callback.split('if action == "video_upload":', 1)[1].split(
        'if action == "video_accept":', 1
    )[0]
    assert "video_trend2_close_video_source_session" in entry_branch
    assert "video_trend2_close_video_source_session" in cancel_branch
    assert "video_trend2_close_video_source_session" in upload_branch


def test_video_menu_clears_only_pending_trend_text_or_media_owner() -> None:
    cleanup = _function_source("video_trend2_cancel_pending_on_video_menu")
    menu = _function_source("handle_menu_callback")

    assert 'str(state.get("pending_input") or "")' in cleanup
    assert 'str(state.get("upload_owner") or "") == "video_trend_upload"' in cleanup
    assert '"awaiting_trend_video"' in cleanup
    assert '"trend_video_analysis"' in cleanup
    assert "video_trend2_close_video_source_session" in cleanup
    assert 'state["pending_input"] = ""' in cleanup
    assert 'if action == "main_video":' in menu
    assert "video_trend2_cancel_pending_on_video_menu" in menu


def test_uploaded_trend_source_is_valid_without_public_url() -> None:
    result = video_flow7.preflight(
        "video_trend",
        {
            "scene_count": 3,
            "aspect_ratio": "9:16",
            "trend_source": {
                "intake_lane": "video_upload",
                "source_video_id": "telegram-video-id",
                "source_analysis": {"analysis_revision": 1},
            },
        },
        owner_ready=True,
        worker_ready=True,
        capability_ready=True,
        package_available=True,
        provider_healthy=True,
        storage_ready=True,
        delivery_ready=True,
    )

    assert result["ok"] is True
    assert result["blockers"] == []
