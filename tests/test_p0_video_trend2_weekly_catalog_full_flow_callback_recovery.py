from __future__ import annotations

import sqlite3
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services import video_flow7, video_profile_catalog, video_trend_catalog


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _item(*, title: str = "Xu hướng thử nghiệm", now: datetime | None = None) -> dict:
    now = now or datetime(2026, 7, 18, 2, 0, tzinfo=timezone.utc)
    return {
        "title": title,
        "summary": "Chủ đề xuất hiện trong nguồn công khai và cần được trình bày có bối cảnh.",
        "platform": "TikTok / mạng xã hội",
        "region": "VN",
        "language": "vi",
        "category": "Nội dung xã hội",
        "keywords": [title, "video"],
        "source_name": "Nguồn xu hướng công khai",
        "source_url": f"https://example.com/trends/{title.replace(' ', '-').lower()}",
        "source_published_at": "Sat, 18 Jul 2026 02:00:00 +0000",
        "collected_at": now,
        "last_verified_at": now,
        "evidence": "Tên chủ đề có trong trang xu hướng công khai.",
        "popularity_signal": "",
    }


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    video_trend_catalog.ensure_schema(conn)
    return conn


def _between(start: str, end: str) -> str:
    return BOT_SOURCE.split(start, 1)[1].split(end, 1)[0]


def test_catalog_schema_contains_source_freshness_and_safety_contract() -> None:
    conn = _conn()
    columns = {row[1] for row in conn.execute("PRAGMA table_info(trend_items)").fetchall()}
    assert {
        "trend_id", "title", "summary", "platform", "region", "language",
        "category", "keywords", "source_name", "source_url",
        "source_published_at", "collected_at", "last_verified_at", "expires_at",
        "evidence", "popularity_signal", "content_safety", "is_active", "version",
    } <= columns


def test_catalog_deduplicates_and_parses_public_source_timestamp() -> None:
    conn = _conn()
    first = video_trend_catalog.upsert_items(conn, [_item()])
    second = video_trend_catalog.upsert_items(conn, [_item()])
    rows = video_trend_catalog.list_items(conn, limit=20)
    assert first == {"inserted": 1, "updated": 0}
    assert second == {"inserted": 0, "updated": 1}
    assert len(rows) == 1
    assert rows[0]["source_published_at"].startswith("2026-07-18T02:00:00")
    assert rows[0]["popularity_signal"] == ""


def test_weekly_refresh_keeps_last_cache_when_public_source_fails() -> None:
    conn = _conn()
    now = datetime(2026, 7, 18, 2, 0, tzinfo=timezone.utc)
    expired = _item(title="Bản lưu gần nhất", now=now - timedelta(days=20))
    expired["expires_at"] = now - timedelta(days=1)
    video_trend_catalog.upsert_items(conn, [expired], now=now - timedelta(days=20))

    def fail(_source):
        raise OSError("source temporarily unavailable")

    result = video_trend_catalog.refresh_catalog(
        conn,
        source_registry={
            "public": {
                "name": "Nguồn công khai",
                "url": "https://example.com/trends",
                "feed_url": "https://example.com/trends.xml",
                "adapter": "test_feed",
            }
        },
        fetchers={"test_feed": fail},
        now=now,
    )
    cached = video_trend_catalog.list_items(conn, limit=20, include_stale_cache=True, now=now)
    assert result["cache_preserved"] is True
    assert result["paid_provider_calls"] == 0
    assert result["expired_count"] == 0
    assert len(cached) == 1 and cached[0]["stale"] is True


def test_successful_refresh_expires_old_rows_and_records_weekly_status() -> None:
    conn = _conn()
    now = datetime(2026, 7, 18, 2, 0, tzinfo=timezone.utc)
    old = _item(title="Trend đã cũ", now=now - timedelta(days=20))
    old["expires_at"] = now - timedelta(days=1)
    video_trend_catalog.upsert_items(conn, [old], now=now - timedelta(days=20))

    result = video_trend_catalog.refresh_catalog(
        conn,
        source_registry={
            "public": {
                "name": "Nguồn công khai",
                "url": "https://example.com/trends",
                "feed_url": "https://example.com/trends.xml",
                "adapter": "test_feed",
            }
        },
        fetchers={"test_feed": lambda _source: [_item(title="Trend mới", now=now)]},
        now=now,
        refresh_days=7,
    )
    status = video_trend_catalog.refresh_status(conn)
    active_titles = {row["title"] for row in video_trend_catalog.list_items(conn, limit=20)}
    assert result["paid_provider_calls"] == 0
    assert result["expired_count"] == 1
    assert active_titles == {"Trend mới"}
    assert status["last_success_at"]
    assert status["next_run_at"]
    assert video_trend_catalog.refresh_due(status, now=now) is False


def test_optional_source_registry_is_validated() -> None:
    registry = video_trend_catalog.source_registry_from_json(
        '{"public":{"name":"Public trends","url":"https://example.com",'
        '"feed_url":"https://example.com/feed","adapter":"google_trends_rss"}}'
    )
    assert registry["public"]["adapter"] == "google_trends_rss"
    with pytest.raises(ValueError, match="invalid_json"):
        video_trend_catalog.source_registry_from_json("{")
    with pytest.raises(ValueError, match="entry_invalid"):
        video_trend_catalog.source_registry_from_json('{"bad":{"name":"x"}}')


def test_32_profiles_build_20_distinct_profile_specific_suggestions() -> None:
    active_profiles = [dict(row) for row in video_profile_catalog.PROFILE_SEEDS if row.get("is_active")]
    assert len(active_profiles) == 32
    trend = video_trend_catalog.normalize_item(_item())
    sales = video_trend_catalog.build_content_suggestions(
        trend, active_profiles[0], scene_count=5, aspect_ratio="9:16"
    )
    review = video_trend_catalog.build_content_suggestions(
        trend, active_profiles[1], scene_count=5, aspect_ratio="9:16"
    )
    assert len(sales) == len(review) == 20
    assert len({row["id"] for row in sales}) == 20
    assert all(trend["title"] in row["content"] for row in sales)
    assert all("đúng 5 cảnh 9:16" in row["content"] for row in sales)
    assert sales[0]["content"] != review[0]["content"]
    assert active_profiles[0]["description"] in sales[0]["content"]


def test_suggestion_paging_shows_five_without_early_repeat() -> None:
    profile = dict(video_profile_catalog.PROFILE_SEEDS[0])
    suggestions = video_trend_catalog.build_content_suggestions(
        video_trend_catalog.normalize_item(_item()), profile, scene_count=3, aspect_ratio="16:9"
    )
    pages = [video_trend_catalog.suggestion_page(suggestions, offset) for offset in (0, 5, 10, 15)]
    ids = [row["id"] for page in pages for row in page]
    assert all(len(page) == 5 for page in pages)
    assert len(ids) == len(set(ids)) == 20


def test_trend_entry_and_sequence_are_canonical() -> None:
    rows = video_flow7.ENTRY_ROWS["video_trend"]
    labels = [label for row in rows for label, _callback in row]
    callbacks = [callback for row in rows for _label, callback in row]
    assert labels == [
        "🔥 Trend mới nhất",
        "✍️ Tự nhập trend",
        "🔎 Tìm kiếm trend",
        "📹 Gửi video trend",
    ]
    assert all("idea" not in callback for callback in callbacks)
    sequence = video_flow7.PRODUCT_SPECS["trend_video"]["sequence"]
    assert sequence[:4] == ("trend_source", "scene_count", "aspect_ratio", "character")
    assert "content_source" not in sequence
    assert "content_profile_or_preset" not in sequence
    assert "content_choice" not in sequence
    assert sequence[-6:] == ("addons", "review", "quality", "invoice", "confirm", "status")
    assert video_flow7.PRODUCT_SPECS["trend_video"]["execution_owner"] == "owner_product_video"


def test_public_trend_callback_has_one_specific_owner_before_generic_handler() -> None:
    assert BOT_SOURCE.count('CallbackQueryHandler(handle_video_trend2_callback, pattern=r"^vtrend\\|")') == 1
    assert BOT_SOURCE.index('pattern=r"^vtrend\\|"') < BOT_SOURCE.index('pattern=r"^vproduct\\|(?!b14_confirm')
    assert '("vtrend|", "handle_video_trend2_callback")' in BOT_SOURCE
    handler = _between(
        "async def _handle_video_trend2_callback_impl",
        "async def handle_video_trend2_callback",
    )
    assert handler.count("await query.answer()") == 1
    assert "last_callback_query_id" in handler
    assert "Có lỗi khi xử lý lệnh" not in handler
    wrapper = _between("async def handle_video_trend2_callback", "async def handle_video_product_callback")
    assert "video_trend2_callback_failed" in wrapper
    assert "Có lỗi khi xử lý lệnh" not in wrapper


def test_legacy_trend_callbacks_have_one_read_only_redirect_owner() -> None:
    assert BOT_SOURCE.count(
        'CallbackQueryHandler(handle_video_trend2_legacy_callback, pattern=r"^trendg\\|")'
    ) == 1
    assert BOT_SOURCE.count(
        'CallbackQueryHandler(handle_video_trend2_legacy_callback, pattern=r"^tvflow\\|")'
    ) == 1
    assert 'CallbackQueryHandler(handle_trend_guided_callback, pattern=r"^trendg\\|")' not in BOT_SOURCE
    assert 'CallbackQueryHandler(handle_trend_video_flow_callback, pattern=r"^tvflow\\|")' not in BOT_SOURCE
    assert '("trendg|", "handle_video_trend2_legacy_callback")' in BOT_SOURCE
    assert '("tvflow|", "handle_video_trend2_legacy_callback")' in BOT_SOURCE
    redirect = _between(
        "async def handle_video_trend2_legacy_callback",
        "def video_selfshot_product_hub_text",
    )
    assert "save_video_trend2_state" not in redirect
    assert "set_trend_video_flow_pending" not in redirect
    assert "restore_developing_video_pending" not in redirect
    assert "Có lỗi khi xử lý lệnh" not in redirect


def test_trend_screen_parent_stack_preserves_exact_back_target() -> None:
    source = _between("VIDEO_TREND2_STATE_KEY", "async def handle_video_trend2_callback")
    assert "def video_trend2_open_screen" in source
    assert 'video_trend2_open_screen(state, "catalog")' in source
    assert 'video_trend2_open_screen(state, "scene_count", parent="catalog")' in source
    assert 'video_trend2_open_screen(state, "aspect_ratio", parent="scene_count")' in source
    assert 'video_trend2_open_screen(state, "content_source", parent="aspect_ratio")' in source
    assert 'video_trend2_open_screen(state, "suggestions", parent="profiles")' in source
    assert 'screen_parents.get(screen)' in source


def test_changed_bot_regions_compile_as_python_311_source() -> None:
    trend_region = "VIDEO_TREND2_STATE_KEY" + _between(
        "VIDEO_TREND2_STATE_KEY",
        "@video_public_callback_failure_guard\nasync def handle_video_product_callback",
    )
    scheduler_region = "def run_video_trend_catalog_refresh_once" + _between(
        "def run_video_trend_catalog_refresh_once",
        "tg_polling_task:",
    )
    catalog_region = "async def video_flow7_open_idea_catalog_from_state" + _between(
        "async def video_flow7_open_idea_catalog_from_state",
        "async def start_public_video_scene2_step",
    )
    idea_region = "async def handle_video_idea_dynamic_callback" + _between(
        "async def handle_video_idea_dynamic_callback",
        "async def handle_video_idea_admin_callback",
    )
    compile(trend_region, "bot.py:trend2", "exec")
    compile(scheduler_region, "bot.py:trend2_scheduler", "exec")
    compile(catalog_region, "bot.py:trend2_idea_catalog", "exec")
    compile(idea_region, "bot.py:trend2_idea_callback", "exec")


def test_public_layout_catalog_ratio_content_and_back_contracts_are_present() -> None:
    source = _between("VIDEO_TREND2_STATE_KEY", "async def handle_video_trend2_callback")
    entry = _between("def video_trend2_entry_keyboard", "def video_trend2_catalog_rows")
    catalog = _between("def video_trend2_catalog_keyboard", "def video_trend2_scene_count_text")
    for callback in (
        'callback_data="vtrend|catalog|latest"',
        'callback_data="vtrend|manual_trend"',
        'callback_data="vtrend|search"',
        'callback_data="vtrend|video_upload"',
    ):
        assert callback in entry
    assert 'callback_data="vtrend|categories"' not in entry + catalog
    assert 'callback_data="vtrend|historical"' not in entry + catalog
    assert 'callback_data="vtrend|help"' not in entry + catalog
    assert 'callback_data="vtrend|ratio_custom"' not in source
    assert 'callback_data="vtrend|ratio_suggest"' not in source
    assert 'callback_data="vtrend|sources"' not in source
    assert 'callback_data="vtrend|freshness"' not in source
    assert 'callback_data="vtrend|idea_catalog"' not in entry
    assert 'callback_data="vtrend|manual_content"' not in entry
    assert "[InlineKeyboardButton(str(index)" in source
    assert 'InlineKeyboardButton("⬅️ Quay lại"' in source
    assert 'InlineKeyboardButton("🎬 Menu Video"' in source


def test_legacy_trend_idea_callback_is_read_only_and_not_public() -> None:
    entry = _between("def video_trend2_entry_keyboard", "def video_trend2_catalog_rows")
    trend_handler = _between(
        "async def _handle_video_trend2_callback_impl",
        "async def handle_video_trend2_callback",
    )
    redirect = trend_handler.split(
        'if action in {"manual_content", "edit_content", "idea_catalog"}:',
        1,
    )[1].split('if action == "profiles":', 1)[0]
    assert "idea_catalog" not in entry
    assert '"screen": "aspect_ratio"' in redirect
    assert "video_trend2_render" in redirect
    assert "video_flow7_open_idea_catalog_from_state" not in redirect


def test_stale_trend_idea_back_is_read_only_and_does_not_clear_session() -> None:
    product_handler = _between(
        "async def handle_video_product_callback",
        "async def handle_video_product_pending_text",
    )
    idea_back = product_handler.split('if action == "idea_back":', 1)[1].split(
        'if action == "script_count_accept"', 1
    )[0]
    stale_branch = idea_back.split('if requested_product == "video_trend":', 1)[1].split(
        "clear_developing_video_pending(uid)", 1
    )[0]
    assert 'trend_state["screen"] = "content_source"' in stale_branch
    assert "save_video_trend2_state" not in stale_branch
    assert "context.user_data.pop" not in stale_branch


def test_idea_callback_is_idempotent_and_trend_errors_are_specific() -> None:
    handler = _between(
        "async def handle_video_idea_dynamic_callback",
        "async def handle_video_idea_admin_callback",
    )
    assert "video_idea_processed_callback_ids" in handler
    assert 'await query.answer("Đã nhận lựa chọn này.")' in handler
    assert "video_idea_parent_handoff" in handler
    assert "Có lỗi khi xử lý lệnh" not in handler


def test_public_trend_catalog_hides_internal_source_and_freshness_details() -> None:
    source = _between("def video_trend2_catalog_text", "def video_trend2_catalog_keyboard")
    for label in ("Nền tảng:", "Dạng nội dung:", "Ý chính:"):
        assert label in source
    assert "Nguồn:" not in source
    assert "Kiểm tra gần nhất:" not in source


def test_every_public_trend_button_has_one_action_branch() -> None:
    public_keyboards = "".join(
        _between(start, end)
        for start, end in (
            ("def video_trend2_entry_keyboard", "def video_trend2_catalog_rows"),
            ("def video_trend2_catalog_keyboard", "def video_trend2_scene_count_text"),
            ("def video_trend2_scene_count_keyboard", "def video_trend2_ratio_keyboard"),
            ("def video_trend2_ratio_keyboard", "def video_trend2_content_source_keyboard"),
            ("def video_trend2_content_source_keyboard", "def video_trend2_profile_rows"),
            ("def video_trend2_profiles_keyboard", "def video_trend2_profile_record"),
            ("def video_trend2_suggestions_keyboard", "def video_trend2_preview_text"),
            ("def video_trend2_preview_keyboard", "def video_trend2_source_snapshot"),
        )
    )
    handler = _between(
        "async def _handle_video_trend2_callback_impl",
        "async def handle_video_trend2_callback",
    )
    declared = set(re.findall(r"vtrend\|([a-z_]+)", public_keyboards))
    for action in declared - {"manual_content", "edit_content", "back"}:
        assert f'action == "{action}"' in handler
    assert 'action in {"manual_content", "edit_content"}' in handler
    assert 'if action == "ratio_custom":' in handler


def test_trend_handoff_persists_source_and_has_zero_preconfirm_side_effects() -> None:
    handoff = _between("def video_trend2_canonical_state", "async def video_trend2_render")
    assert "trend_source = video_trend2_source_snapshot(state)" in handoff
    assert '"trend_source": trend_source' in handoff
    assert '"source_video_id": str(trend_source.get("source_video_id") or "")' in handoff
    assert '"source_analysis": deepcopy(dict(trend_source.get("source_analysis") or {}))' in handoff
    assert '"source_product_id": "video_trend"' in handoff
    assert '"step": "creative_controls"' in handoff
    bridge = _between("def video_trend_prepare_entity_bridge", "async def video_trend_finish_entity_bridge")
    assert '"current_step": "production_bible"' in bridge
    for contract in (
        '"provider_called": False',
        '"image_provider_called": False',
        '"job_created": False',
        '"outbox_created": False',
        '"files_generated": 0',
        '"wallet_mutations": 0',
        '"xu_charged": 0',
    ):
        assert contract in handoff


def test_trend_engine_preflight_delivery_and_charge_contract() -> None:
    context = {
        "scene_count": 3,
        "aspect_ratio": "9:16",
        "trend_source": {
            "trend_id": "tr_public",
            "title": "Trend có nguồn",
            "source_url": "https://example.com/trend",
            "observed_at": "2026-07-18T02:00:00+00:00",
        },
    }
    preflight = video_flow7.preflight(
        "video_trend",
        context,
        owner_ready=True,
        worker_ready=True,
        capability_ready=True,
        package_available=True,
        provider_healthy=True,
        storage_ready=True,
        delivery_ready=True,
    )
    assert preflight["ok"] is True
    assert preflight["route"]["product_kind"] == "trend_video"
    assert preflight["route"]["execution_owner"] == "owner_product_video"
    assert preflight["side_effects"] == {
        "job": 0,
        "outbox": 0,
        "invoice": 0,
        "provider_calls": 0,
        "generated_files": 0,
        "wallet_mutations": 0,
        "xu_charged": 0,
    }
    assert video_flow7.charge_allowed(context) is False
    delivered = video_flow7.record_delivery(context, message_id=901, receipt_key="trend:901")
    assert video_flow7.charge_allowed(delivered) is True
    assert video_flow7.record_delivery(delivered, message_id=901, receipt_key="trend:901") == delivered


def test_legacy_trend_callbacks_redirect_without_restoring_old_mutation_path() -> None:
    callback = _between("async def handle_video_product_callback", "async def handle_video_product_pending_text")
    redirect_at = callback.index('action in {"trend_today", "trend_more", "trend_custom", "trend_select"}')
    redirect = callback[redirect_at:callback.index('    if action == "open":', redirect_at)]
    assert 'legacy_state["screen"] = "entry"' in redirect
    assert "task3d_session_step" not in redirect
    assert 'if action in {"trend_today", "trend_more"}' not in callback
    assert "TASK3D_TREND_STORE" not in BOT_SOURCE


def test_weekly_scheduler_and_admin_truth_do_not_call_paid_provider() -> None:
    scheduler = _between("def run_video_trend_catalog_refresh_once", "tg_polling_task:")
    assert 'os.getenv("TREND_REFRESH_ENABLED"' in scheduler
    assert 'os.getenv("TREND_SOURCE_REGISTRY")' in scheduler
    assert 'os.getenv("TREND_MAX_AGE_DAYS")' in scheduler
    assert "video_trend_catalog.refresh_due" in scheduler
    assert "provider" not in scheduler.casefold() or "Provider trả phí: 0" in scheduler


def test_framevideo_regression_keeps_one_assets_done_owner_and_continuity_anchor() -> None:
    assert BOT_SOURCE.count("async def handle_frame_video_assets_done") == 1
    frame_callback = _between("async def handle_frame_video_callback", "async def handle_frame_video_message")
    assert 'if action == "assets_done"' in frame_callback
    assert "handle_frame_video_assets_done" in frame_callback
    assert "img2vid_continuity_anchor" in BOT_SOURCE
    assert "chính xác cùng một chủ thể trong mọi ảnh" in BOT_SOURCE
