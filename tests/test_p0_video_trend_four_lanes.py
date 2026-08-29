from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from services import pricing_guide_content, video_flow7, video_selfshot_local_analysis, video_trend_catalog


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    pattern = re.compile(rf"^(?:async )?def {re.escape(name)}\(", re.MULTILINE)
    match = pattern.search(BOT_SOURCE)
    assert match, f"missing function: {name}"
    next_match = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[match.end() :])
    end = match.end() + next_match.start() if next_match else len(BOT_SOURCE)
    return BOT_SOURCE[match.start() : end]


def _runtime_function(name: str, namespace: dict) -> object:
    source = _function_source(name).rsplit("\n@", 1)[0]
    exec(compile(source, f"bot.py:{name}", "exec"), namespace)
    return namespace[name]


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


def test_all_trend_content_callbacks_reopen_the_restored_full_flow() -> None:
    parent_map = BOT_SOURCE.split("VIDEO_TREND2_PARENT = {", 1)[1].split("}\n\n", 1)[0]
    for restored_screen in ("content_source", "profiles", "suggestions", "preview"):
        assert f'"{restored_screen}"' in parent_map

    state = _function_source("video_trend2_state")
    assert "VIDEO_TREND2_PUBLIC_SCREENS" in state

    callback = _function_source("_handle_video_trend2_callback_impl")
    assert "VIDEO_TREND2_LEGACY_CONTENT_ACTIONS" not in callback
    for restored_action in (
        "manual_content",
        "edit_content",
        "idea_catalog",
        "idea_return",
        "profiles",
        "profile",
        "suggestions_more",
        "suggestion",
        "restore_content",
        "continue",
    ):
        assert f'action == "{restored_action}"' in callback or f'"{restored_action}"' in callback

    emitted_actions = set()
    for keyboard_name in (
        "video_trend2_content_source_keyboard",
        "video_trend2_profiles_keyboard",
        "video_trend2_suggestions_keyboard",
        "video_trend2_preview_keyboard",
    ):
        emitted_actions.update(
            re.findall(r'callback_data=f?"vtrend\|([a-z_]+)', _function_source(keyboard_name))
        )
    for emitted_action in emitted_actions - {"back", "catalog"}:
        assert f'action == "{emitted_action}"' in callback or f'"{emitted_action}"' in callback

    pending = _function_source("handle_video_trend2_pending_text")
    assert "VIDEO_TREND2_LEGACY_PENDING_INPUTS" not in pending
    assert 'elif pending == "manual_trend":' in pending
    assert 'video_trend2_open_screen(state, "scene_count"' in pending
    assert 'elif pending in {"manual_content", "edit_content"}:' in pending
    assert 'video_trend2_open_screen(state, "preview"' in pending
    assert "video_manual_lane_open_shared_tail" not in pending


def test_public_trend_ui_has_no_internal_side_effect_copy() -> None:
    start = BOT_SOURCE.index("VIDEO_TREND2_STATE_KEY")
    end = BOT_SOURCE.index("def storyboard2_prepare_quick_image", start)
    trend_copy_start = BOT_SOURCE.index('    "video_trend": (', BOT_SOURCE.index("TASK3D_PUBLIC_COPY = {"))
    trend_copy_end = BOT_SOURCE.index('    "video_idea": (', trend_copy_start)
    public_surface = (
        BOT_SOURCE[start:end]
        + BOT_SOURCE[trend_copy_start:trend_copy_end]
        + _function_source("handle_video_trend2_pending_text")
    ).casefold()

    for forbidden in (
        "chưa tạo tác vụ",
        "chưa gọi nguồn dựng",
        "chưa trừ xu",
        "chưa tạo video",
    ):
        assert forbidden not in public_surface


def test_non_vietnamese_trend_intro_uses_product_specific_localized_copy() -> None:
    intro = _runtime_function(
        "task3d_product_intro_text",
        {
            "VIDEO_PRODUCT_REGISTRY": {"video_trend": {"id": "video_trend"}},
            "normalize_user_language": lambda lang: str(lang or "en"),
            "public_video_menu_label": pricing_guide_content.public_video_menu_label,
            "public_video_deep_copy": pricing_guide_content.public_video_deep_copy,
            "public_hub_copy": lambda _lang: {
                "video_label": "GENERIC-VIDEO",
                "freehub_input_title": "SEND {item}",
            },
            "video_script_hub_text": lambda _lang: "SCRIPT",
            "task3d_public_copy": lambda _product, _lang: "VI",
        },
    )

    for locale in (
        "en", "zh", "ja", "ko", "th", "ar", "es", "pt",
        "fr", "de", "hi", "ru", "tr", "fil", "it", "id",
    ):
        text = intro("video_trend", locale)
        copy = pricing_guide_content.public_video_deep_copy(locale)
        assert copy["no_charge"] not in text
        assert pricing_guide_content.public_video_menu_label("video_trend", locale) in text
        assert copy["trend_pending"] in text
        assert copy["scene_title"] in text
        assert copy["aspect_title"] in text


def test_octet_stream_extension_fallback_is_owned_only_by_trend_upload() -> None:
    media = _function_source("handle_video_product_pending_media")
    media_flow_start = media.index("if current_step in VIDEO_MICROFLOW_MEDIA_INPUT_STEPS:")
    document_start = media.index('elif getattr(update.message, "document", None):', media_flow_start)
    document_end = media.index("if not media:", document_start)
    document_branch = media[document_start:document_end]

    assert "trend_document_video = (" in document_branch
    assert 'str(session.get("product_id") or "") == "video_trend"' in document_branch
    assert 'current_step == "awaiting_trend_video"' in document_branch
    assert "video_flow7.video_document_is_supported" in document_branch
    assert 'elif mime_type.startswith("video/") or trend_document_video:' in document_branch


def test_async_search_and_upload_results_require_current_owner() -> None:
    pending = _function_source("handle_video_trend2_pending_text")
    search_owner = _function_source("video_trend2_search_result_owner_valid")
    media = _function_source("handle_video_product_pending_media")
    upload_owner = _function_source("video_trend2_upload_result_owner_valid")

    assert "search_token = video_trend2_search_token(state)" in pending
    assert pending.index("await fetch_google_news_trends") < pending.index(
        "video_trend2_search_result_owner_valid"
    ) < pending.index('video_trend2_open_screen(state, "search_results"')
    assert 'pending_input") or "") == "trend_search"' in search_owner
    assert 'search_owner") or "") == "video_trend_search"' in search_owner
    assert 'active_search_message_id")' in search_owner
    assert 'state["active_search_message_id"] = message_id' in pending
    assert "video_trend2_upload_token(state) == expected_token" in upload_owner
    assert "video_trend2_upload_owner_valid(session, state)" in upload_owner
    assert 'active_video_message_id")' in upload_owner
    assert media.count("video_trend2_upload_result_owner_valid") >= 3
    assert 'trend_state["active_video_message_id"] = message_id' in media


def test_async_owner_helpers_reject_stale_generation_or_message() -> None:
    search_state = {
        "pending_input": "trend_search",
        "search_owner": "video_trend_search",
        "token": "search-session:2",
        "active_search_message_id": 301,
    }
    search_valid = _runtime_function(
        "video_trend2_search_result_owner_valid",
        {
            "video_trend2_state": lambda _context: dict(search_state),
            "video_trend2_search_token": lambda state: state["token"],
            "safe_int": lambda value, default=0: int(value or default),
        },
    )
    assert search_valid(object(), "search-session:2", 301) is True
    search_state["active_search_message_id"] = 302
    assert search_valid(object(), "search-session:2", 301) is False
    search_state["active_search_message_id"] = 301
    search_state["pending_input"] = ""
    assert search_valid(object(), "search-session:2", 301) is False
    search_state.update({"pending_input": "trend_search", "token": "search-session:3"})
    assert search_valid(object(), "search-session:2", 301) is False

    upload_state = {"token": "upload-session:4", "active_video_message_id": 401}
    upload_session = {"valid": True}
    upload_valid = _runtime_function(
        "video_trend2_upload_result_owner_valid",
        {
            "video_trend2_state": lambda _context: dict(upload_state),
            "get_video_session": lambda _user_id: dict(upload_session),
            "safe_int": lambda value, default=0: int(value or default),
            "video_trend2_upload_token": lambda state: state["token"],
            "video_trend2_upload_owner_valid": lambda session, _state: bool(session.get("valid")),
        },
    )
    assert upload_valid(1, object(), "upload-session:4", 401) is True
    upload_state["active_video_message_id"] = 402
    assert upload_valid(1, object(), "upload-session:4", 401) is False
    upload_state.update({"active_video_message_id": 401, "token": "upload-session:5"})
    assert upload_valid(1, object(), "upload-session:4", 401) is False
    upload_state["token"] = "upload-session:4"
    upload_session["valid"] = False
    assert upload_valid(1, object(), "upload-session:4", 401) is False


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
    assert '"trend_video_ready"' in cleanup
    assert "video_trend2_close_video_source_session" in cleanup
    assert 'state["pending_input"] = ""' in cleanup
    assert 'if action == "main_video":' in menu
    assert "video_trend2_cancel_pending_on_video_menu" in menu


def test_video_menu_cleanup_closes_accepted_upload_context() -> None:
    state = {
        "pending_input": "",
        "upload_owner": "",
        "upload_session_id": "upload-session",
        "active_video_message_id": 0,
        "source_video": {"file_id": "video-id"},
        "source_analysis": {"analysis_revision": 1},
        "selected_trend": {"intake_lane": "video_upload"},
        "search_owner": "",
        "search_session_id": "",
    }
    closed = []
    saved = []
    cleanup = _runtime_function(
        "video_trend2_cancel_pending_on_video_menu",
        {
            "video_trend2_state": lambda _context: state,
            "get_video_session": lambda _user_id: {"current_step": "trend_video_ready"},
            "video_trend2_close_video_source_session": lambda user_id: closed.append(user_id),
            "save_video_trend2_state": lambda _context, current: saved.append(dict(current)),
        },
    )

    assert cleanup(77, object()) is True
    assert closed == [77]
    assert state["source_video"] == {}
    assert state["source_analysis"] == {}
    assert state["selected_trend"] == {}
    assert saved


def test_video_documents_use_mime_or_allowed_extension() -> None:
    assert video_flow7.video_document_is_supported("video/mp4", "clip.bin") is True
    assert video_flow7.video_document_is_supported("application/octet-stream", "clip.mp4") is True
    assert video_flow7.video_document_is_supported("application/octet-stream", "clip.mkv") is True
    assert video_flow7.video_document_is_supported("application/octet-stream", "clip.webm") is True
    assert video_flow7.video_document_is_supported("application/pdf", "clip.pdf") is False
    assert video_flow7.video_document_is_supported("image/png", "clip.mp4") is False


def test_trend_contract_ends_with_exact_shared_tail() -> None:
    sequence = video_flow7.product_sequence("video_trend")

    assert sequence[-6:] == (
        "addons",
        "review",
        "quality",
        "invoice",
        "confirm",
        "status",
    )
    for legacy_step in ("audio", "transitions", "text", "finish"):
        assert legacy_step not in sequence


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
