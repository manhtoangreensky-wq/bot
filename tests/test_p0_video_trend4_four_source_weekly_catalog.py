from __future__ import annotations

import sqlite3
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from services import video_trend_catalog


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    video_trend_catalog.ensure_schema(conn)
    return conn


def _item(source_key: str, title: str, platform: str) -> dict:
    return {
        "title": title,
        "summary": f"Mẫu video ngắn từ {platform}.",
        "platform": platform,
        "region": "VN",
        "language": "vi",
        "category": "Video ngắn",
        "keywords": [platform, "video trend"],
        "source_key": source_key,
        "source_name": f"Nguồn công khai {platform}",
        "source_url": f"https://example.com/{source_key}/{title.replace(' ', '-').lower()}",
        "source_published_at": "2026-08-27T00:00:00+00:00",
        "evidence": "Metadata công khai có nguồn.",
    }


def test_default_registry_covers_exact_four_public_source_groups() -> None:
    assert set(video_trend_catalog.TREND_SOURCE_GROUPS) == {
        "media",
        "facebook",
        "youtube",
        "tiktok",
    }
    registry = video_trend_catalog.source_registry_from_json(None)
    assert {source["source_group"] for source in registry.values()} == set(
        video_trend_catalog.TREND_SOURCE_GROUPS
    )
    assert all(source["adapter"] != "reference_only" for source in registry.values())


def test_default_facebook_feed_uses_the_live_nonempty_public_query() -> None:
    source = video_trend_catalog.source_registry_from_json(None)[
        "facebook_reels_public_vn"
    ]
    query = urllib.parse.parse_qs(
        urllib.parse.urlparse(source["feed_url"]).query
    )["q"][0]

    assert query == "Facebook Reels Vietnam"


def test_weekly_refresh_reports_and_preserves_each_source_group() -> None:
    conn = _conn()
    now = datetime(2026, 8, 27, tzinfo=timezone.utc)
    registry = {
        group: {
            "name": group.title(),
            "url": f"https://example.com/{group}",
            "feed_url": f"https://example.com/{group}.json",
            "adapter": group,
            "source_group": group,
        }
        for group in video_trend_catalog.TREND_SOURCE_GROUPS
    }
    fetchers = {
        "media": lambda _source: [_item("media", "Media format mới", "Media")],
        "facebook": lambda _source: [_item("facebook", "Facebook Reel mới", "Facebook Reels")],
        "youtube": lambda _source: [_item("youtube", "YouTube Short mới", "YouTube Shorts")],
        "tiktok": lambda _source: [_item("tiktok", "TikTok format mới", "TikTok")],
    }

    result = video_trend_catalog.refresh_catalog(
        conn,
        source_registry=registry,
        fetchers=fetchers,
        now=now,
        refresh_days=7,
    )

    assert result["source_group_counts"] == {
        "media": 1,
        "facebook": 1,
        "youtube": 1,
        "tiktok": 1,
    }
    assert result["paid_provider_calls"] == 0
    assert result["next_run_at"].startswith("2026-09-03")
    for group in video_trend_catalog.TREND_SOURCE_GROUPS:
        assert len(video_trend_catalog.list_media_items(conn, source_group=group)) == 1


def test_one_source_failure_preserves_only_that_source_cache() -> None:
    conn = _conn()
    now = datetime(2026, 8, 27, tzinfo=timezone.utc)
    cached = _item("facebook", "Facebook Reel gần nhất", "Facebook Reels") | {
        "expires_at": "2026-08-26T00:00:00+00:00",
    }
    video_trend_catalog.upsert_items(conn, [cached], now=now)
    registry = {
        group: {
            "name": group.title(),
            "url": f"https://example.com/{group}",
            "feed_url": f"https://example.com/{group}.json",
            "adapter": group,
            "source_group": group,
        }
        for group in video_trend_catalog.TREND_SOURCE_GROUPS
    }

    def facebook_down(_source):
        raise OSError("facebook feed unavailable")

    fetchers = {
        "media": lambda _source: [_item("media", "Media mới", "Media")],
        "facebook": facebook_down,
        "youtube": lambda _source: [_item("youtube", "YouTube mới", "YouTube Shorts")],
        "tiktok": lambda _source: [_item("tiktok", "TikTok mới", "TikTok")],
    }
    result = video_trend_catalog.refresh_catalog(
        conn,
        source_registry=registry,
        fetchers=fetchers,
        now=now,
        refresh_days=7,
    )

    assert result["source_group_status"]["facebook"]["ok"] is False
    assert result["source_group_status"]["facebook"]["cache_preserved"] is True
    assert [
        row["title"]
        for row in video_trend_catalog.list_media_items(
            conn,
            source_group="facebook",
            now=now,
        )
    ] == ["Facebook Reel gần nhất"]


def test_four_source_refresh_does_not_change_public_trend_layout() -> None:
    entry = BOT_SOURCE[
        BOT_SOURCE.index("def video_trend2_entry_keyboard") : BOT_SOURCE.index(
            "def video_trend2_catalog_rows"
        )
    ]
    catalog = BOT_SOURCE[
        BOT_SOURCE.index("def video_trend2_catalog_keyboard") : BOT_SOURCE.index(
            "def video_trend2_search_results_text"
        )
    ]

    assert '"🔥 Xem 5 trend media", callback_data="vtrend|catalog|latest"' in entry
    assert '"✍️ Tự nhập trend", callback_data="vtrend|manual_trend"' in entry
    assert '"🔎 Tìm kiếm trend", callback_data="vtrend|search"' in entry
    assert '"📹 Gửi video trend", callback_data="vtrend|video_upload"' in entry
    assert "catalog_source_group" not in BOT_SOURCE
    for callback in (
        "vtrend|catalog|all",
        "vtrend|catalog|media",
        "vtrend|catalog|facebook",
        "vtrend|catalog|youtube",
        "vtrend|catalog|tiktok",
    ):
        assert callback not in catalog
