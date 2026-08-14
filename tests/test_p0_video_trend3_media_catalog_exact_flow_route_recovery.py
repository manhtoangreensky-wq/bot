from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services import video_flow7, video_profile_catalog, video_trend_catalog


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _between(start: str, end: str) -> str:
    return BOT_SOURCE.split(start, 1)[1].split(end, 1)[0]


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    video_trend_catalog.ensure_schema(conn)
    return conn


def _item(
    title: str,
    *,
    platform: str,
    now: datetime,
    summary: str = "Mẫu nội dung truyền thông đang được dùng công khai.",
) -> dict:
    return {
        "title": title,
        "summary": summary,
        "platform": platform,
        "region": "VN",
        "language": "vi",
        "category": "Media trend",
        "keywords": [title],
        "source_name": "Nguồn media công khai",
        "source_url": "https://example.com/media/" + re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-"),
        "source_published_at": now,
        "collected_at": now,
        "last_verified_at": now,
        "evidence": "Mẫu được ghi nhận trong nguồn media công khai.",
    }


def test_media_filter_accepts_social_video_formats_and_rejects_generic_search_terms() -> None:
    now = datetime(2026, 7, 18, 2, 0, tzinfo=timezone.utc)
    accepted = (
        _item("Hook ba giây đầu", platform="TikTok", now=now),
        _item("Mẫu chuyển cảnh match cut", platform="Instagram Reels", now=now),
        _item("POV review ngắn", platform="Facebook Reels", now=now),
        _item("Thử thách âm thanh remix", platform="YouTube Shorts", now=now),
    )
    assert all(video_trend_catalog.is_media_trend(item) for item in accepted)
    for title in ("nghệ", "FPT", "VTV5", "Arsenal gặp Man City"):
        assert video_trend_catalog.is_media_trend(
            _item(title, platform="Google Search", now=now, summary="Từ khóa tìm kiếm chung.")
        ) is False


def test_weekly_refresh_filters_generic_rows_and_moves_expired_media_to_history() -> None:
    conn = _conn()
    now = datetime(2026, 7, 18, 2, 0, tzinfo=timezone.utc)
    old = _item("Mẫu storytime cũ", platform="TikTok", now=now - timedelta(days=30))
    old["expires_at"] = now - timedelta(days=1)
    video_trend_catalog.upsert_items(conn, [old], now=now - timedelta(days=30))
    fresh = _item("Mẫu UGC mở hộp", platform="TikTok", now=now)
    generic = _item("FPT", platform="Google Search", now=now, summary="Từ khóa tìm kiếm chung.")

    result = video_trend_catalog.refresh_catalog(
        conn,
        source_registry={
            "fixture": {
                "name": "Fixture",
                "url": "https://example.com/media",
                "feed_url": "https://example.com/media.json",
                "adapter": "fixture",
            }
        },
        fetchers={"fixture": lambda _source: [fresh, generic]},
        now=now,
    )

    assert result["inserted_count"] == 1
    assert result["rejected_count"] == 1
    assert [row["title"] for row in video_trend_catalog.list_media_items(conn)] == ["Mẫu UGC mở hộp"]
    assert [row["title"] for row in video_trend_catalog.list_media_items(conn, historical=True)] == ["Mẫu storytime cũ"]
    assert video_trend_catalog.refresh_status(conn)["rejected_count"] == 1


def test_refresh_without_valid_media_preserves_last_media_cache() -> None:
    conn = _conn()
    now = datetime(2026, 7, 18, 2, 0, tzinfo=timezone.utc)
    cached = _item("Mẫu video POV gần nhất", platform="TikTok", now=now - timedelta(days=20))
    cached["expires_at"] = now - timedelta(days=1)
    video_trend_catalog.upsert_items(conn, [cached], now=now - timedelta(days=20))
    generic = _item("VTV5", platform="Google Search", now=now, summary="Từ khóa tìm kiếm chung.")

    result = video_trend_catalog.refresh_catalog(
        conn,
        source_registry={"fixture": {"adapter": "fixture"}},
        fetchers={"fixture": lambda _source: [generic]},
        now=now,
    )

    assert result["cache_preserved"] is True
    assert result["expired_count"] == 0
    assert result["paid_provider_calls"] == 0
    assert [row["title"] for row in video_trend_catalog.list_media_items(conn, now=now)] == ["Mẫu video POV gần nhất"]


def test_public_entry_catalog_and_ratio_contract_are_exact() -> None:
    labels = [label for row in video_flow7.entry_rows("video_trend") for label, _callback in row]
    assert labels == [
        "🔥 Trend mới nhất",
        "✍️ Tự nhập trend",
        "🔎 Tìm kiếm trend",
        "📹 Gửi video trend",
    ]

    entry = _between("def video_trend2_entry_keyboard", "def video_trend2_catalog_rows")
    assert "Trend theo nhóm" not in entry
    assert "Nguồn & độ mới" not in entry
    assert "Ý tưởng video" not in entry

    ratio = _between("def video_trend2_ratio_keyboard", "def video_trend2_content_source_keyboard")
    for label in ("Dọc 9:16", "Ngang 16:9", "Vuông 1:1", "Dọc 4:5"):
        assert label in ratio
    assert "Gợi ý" not in ratio
    assert "Tự nhập" not in ratio
    assert "ratio_suggest" not in ratio

    shared_ratio = _between("def video_scene3_aspect_keyboard", "def video_scene3_quality_keyboard")
    assert "Gợi ý" not in shared_ratio
    assert "ratio_suggest" not in shared_ratio


def test_catalog_and_suggestion_number_buttons_use_one_compact_row() -> None:
    catalog = _between("def video_trend2_catalog_keyboard", "def video_trend2_scene_count_text")
    suggestions = _between("def video_trend2_suggestions_keyboard", "def video_trend2_preview_text")
    shared = _between("def video_scene3_suggestion_keyboard", "def video_scene3_requirements_text")
    assert "keyboard.append([\n            InlineKeyboardButton(str(index)" in catalog
    assert "[InlineKeyboardButton(str(index)" in suggestions
    assert "number_buttons," in shared
    assert "number_buttons[:2]" not in shared
    assert "number_buttons[2:4]" not in shared


def test_content_source_profiles_idea_catalog_and_flow_order_are_canonical() -> None:
    content = _between("def video_trend2_content_source_keyboard", "def video_trend2_profile_rows")
    for label in ("🎯 Chọn loại nội dung", "💡 Kho Ý tưởng video", "✍️ Tự nhập nội dung", "🔄 Đổi trend"):
        assert label in content
    assert len([row for row in video_profile_catalog.PROFILE_SEEDS if row.get("is_active")]) == 32
    sequence = video_flow7.product_sequence("video_trend")
    assert sequence[:4] == ("trend_source", "scene_count", "aspect_ratio", "character")
    assert "content_source" not in sequence
    assert "content_profile_or_preset" not in sequence
    assert "content_choice" not in sequence
    assert sequence[-3:] == ("finish", "invoice", "confirm")


def test_exact_back_stack_and_idea_return_are_preserved() -> None:
    handler = _between("async def _handle_video_trend2_callback_impl", "async def handle_video_trend2_callback")
    for route in (
        'video_trend2_open_screen(state, "scene_count", parent="catalog")',
        'video_trend2_open_screen(state, "aspect_ratio", parent="scene_count")',
        'video_trend2_open_screen(state, "content_source", parent="aspect_ratio")',
        'video_trend2_open_screen(state, "suggestions", parent="profiles")',
    ):
        assert route in handler
    assert 'back_callback="vtrend|idea_return"' in handler
    assert "screen_parents.get(screen)" in handler
    assert 'callback_data="menu|main_video"' in _between("def video_trend2_nav", "def video_trend2_entry_keyboard")


def test_valid_trend_callbacks_have_one_owner_no_generic_x_and_zero_preconfirm_side_effects() -> None:
    assert BOT_SOURCE.count('CallbackQueryHandler(handle_video_trend2_callback, pattern=r"^vtrend\\|")') == 1
    owners = _between("VIDEO_PUBLIC_CALLBACK_OWNER_PREFIXES", "def video_route_expected_handler")
    assert owners.count('("vtrend|", "handle_video_trend2_callback")') == 1
    handler = _between("async def _handle_video_trend2_callback_impl", "async def handle_video_trend2_callback")
    wrapper = _between("async def handle_video_trend2_callback", "async def handle_video_product_callback")
    assert handler.count("await query.answer()") == 1
    assert "last_callback_query_id" in handler
    assert "Có lỗi khi xử lý lệnh" not in handler + wrapper
    handoff = _between("def video_trend2_canonical_state", "async def video_trend2_render")
    for contract in (
        '"provider_called": False', '"image_provider_called": False',
        '"job_created": False', '"outbox_created": False',
        '"files_generated": 0', '"wallet_mutations": 0', '"xu_charged": 0',
    ):
        assert contract in handoff


def test_changed_trend_regions_compile() -> None:
    compile(
        "VIDEO_TREND2_STATE_KEY" + _between(
            "VIDEO_TREND2_STATE_KEY",
            "@video_public_callback_failure_guard\nasync def handle_video_product_callback",
        ),
        "bot.py:trend3",
        "exec",
    )
