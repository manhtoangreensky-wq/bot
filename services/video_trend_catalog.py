"""Persistent, source-backed catalog for the public Trend Video flow.

This module only reads public trend metadata and stores planning context.  It
never creates media jobs, calls a paid provider, or mutates a customer wallet.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Iterable, Mapping


SCHEMA_VERSION = 1
DEFAULT_MAX_AGE_DAYS = 14
DEFAULT_REFRESH_DAYS = 7
MEDIA_TREND_TERMS = (
    "tiktok", "reels", "shorts", "youtube short", "facebook reel", "instagram reel",
    "meme", "challenge", "thử thách", "âm thanh", "audio", "sound", "remix",
    "transition", "chuyển cảnh", "hiệu ứng", "effect", "hook", "mở đầu",
    "pov", "ugc", "unboxing", "đập hộp", "review", "livestream", "viral",
    "dance", "nhảy", "biến hình", "storytime", "duet", "stitch", "capcut",
    "template", "filter", "video format", "format video", "phong cách quay",
    "cách quay", "quảng cáo ngắn", "video quảng cáo",
)
MEDIA_PLATFORM_TERMS = (
    "tiktok", "youtube shorts", "shorts", "instagram reels", "facebook reels",
    "reels", "mạng xã hội", "social video",
)
GENERIC_SEARCH_ONLY_TITLES = {"nghệ", "fpt", "vtv5"}
SOURCE_REGISTRY = {
    "google_trends_vn": {
        "name": "Google Trends - Việt Nam",
        "url": "https://trends.google.com/trending?geo=VN",
        "feed_url": "https://trends.google.com/trending/rss?geo=VN",
        "adapter": "google_trends_rss",
    },
    "tiktok_creative_center_vn": {
        "name": "TikTok Creative Center - Việt Nam",
        "url": "https://ads.tiktok.com/business/creativecenter/trends/home/pc/vi",
        "feed_url": "",
        "adapter": "reference_only",
    },
}


# Provider-free fallback formats keep the public catalog usable when a public
# trend feed is unavailable. They are reusable media patterns, not claims about
# live popularity; the weekly source refresh can rank fresh sourced items ahead
# of them whenever it succeeds.
FALLBACK_MEDIA_FORMATS = (
    ("POV tình huống đời thường", "POV", "Kể một tình huống gần gũi từ góc nhìn người trong cuộc, có mở đầu, diễn biến và kết tự nhiên."),
    ("Một ngày cùng nhân vật", "Nhật ký ngắn", "Theo các mốc trong một ngày, mỗi cảnh hoàn tất một hoạt động và cùng phục vụ một chủ đề."),
    ("Mở hộp và hé lộ", "Review / unboxing", "Đi từ bao bì, chi tiết, thao tác thật đến điểm nổi bật và kết luận có căn cứ."),
    ("Trước và sau", "Biến đổi", "Giữ cùng chủ thể và góc nhìn để thể hiện thay đổi rõ ràng, không phóng đại kết quả."),
    ("Hướng dẫn ba bước", "Hướng dẫn", "Mỗi cảnh hoàn tất một bước; không cắt giữa thao tác, câu nói hoặc chuyển động camera."),
    ("Demo sản phẩm trong tình huống thật", "Quảng cáo ngắn", "Đặt sản phẩm vào nhu cầu thật, chứng minh công dụng rồi kết bằng lời mời phù hợp."),
    ("Phản ứng rồi giải thích", "Reaction / giải thích", "Mở bằng phản ứng đáng chú ý, giải thích nguyên nhân và chốt thông tin hữu ích."),
    ("Phỏng vấn nhanh ngoài đường", "Phỏng vấn ngắn", "Một câu hỏi rõ, các câu trả lời ngắn và phần tổng kết không xuyên tạc ý người nói."),
    ("Storytime có cao trào", "Kể chuyện", "Mở bằng tình huống, tăng dần xung đột và khép bằng kết quả trọn ý."),
    ("Thử thách có kết quả", "Challenge", "Nêu luật chơi, thực hiện, quan sát và xác nhận kết quả mà không dựng thành tích giả."),
    ("Đối đáp hai góc nhìn", "Duet / đối chiếu", "Đặt hai quan điểm cạnh nhau theo cùng tiêu chí rồi kết luận cân bằng."),
    ("Biến đổi liên tục một cú máy", "One-take transformation", "Giữ nhận diện và chuyển động gốc trong khi trang phục, cảnh vật hoặc ánh sáng biến đổi theo nhịp."),
    ("Vòng lặp chuyển động thỏa mãn", "Loop / satisfying", "Thiết kế điểm đầu và cuối khớp tự nhiên để video lặp mượt, không cắt cụt hành động."),
    ("Âm thanh chân thực cận cảnh", "ASMR", "Ưu tiên thao tác, chất liệu và âm thanh môi trường; hạn chế lời nói không cần thiết."),
    ("Tình huống hài có ngữ cảnh", "Meme / parody", "Dùng tình huống nhận biết được, nhịp gọn và không giả mạo người thật hoặc phát ngôn."),
    ("Micro-vlog một địa điểm", "Vlog ngắn", "Dẫn người xem qua một địa điểm theo hướng liên tục và khép tại chi tiết đáng nhớ nhất."),
    ("Chuỗi B-roll điện ảnh", "Cinematic B-roll", "Nối toàn, trung và cận cảnh cùng hướng chuyển động, ánh sáng và màu sắc nhất quán."),
    ("Trải nghiệm người dùng thật", "UGC / testimonial", "Đi từ nhu cầu, cách dùng tới nhận xét cuối; không bịa đánh giá, số liệu hoặc danh tính."),
    ("So sánh hai lựa chọn", "Comparison", "Dùng cùng tiêu chí cho hai lựa chọn, nêu điểm mạnh yếu và chốt theo nhu cầu cụ thể."),
    ("Tin nhanh bằng dữ liệu", "News / data short", "Nêu điều mới, nguồn và bối cảnh; chỉ dùng số liệu kiểm chứng được và nói rõ giới hạn."),
)


def fallback_media_items(*, now: datetime | None = None) -> list[dict[str, Any]]:
    current = now or utc_now()
    fallback_verified_at = current - timedelta(days=365)
    source_url = "https://ads.tiktok.com/business/creativecenter/inspiration/popular/pc/en"
    return [
        {
            "trend_id": f"tr_seed_media_{index:02d}",
            "title": title,
            "short_title": title,
            "summary": summary,
            "platform": "TikTok / Reels / Shorts",
            "region": "VN",
            "language": "vi",
            "category": category,
            "keywords": ["media trend", "video format", category, title],
            "source_name": "TOAN AAS - mẫu media đã duyệt",
            "source_url": source_url,
            "source_published_at": "",
            "collected_at": current,
            # Fresh source-backed rows sort ahead of fallback formats.
            "last_verified_at": fallback_verified_at,
            "expires_at": current + timedelta(days=3650),
            "evidence": "Mẫu định dạng media dự phòng; không đại diện cho số liệu thịnh hành trực tiếp.",
            "popularity_signal": "",
            "content_safety": "approved_fallback_media_format",
            "is_active": True,
            "version": SCHEMA_VERSION,
        }
        for index, (title, category, summary) in enumerate(FALLBACK_MEDIA_FORMATS, 1)
    ]


def seed_media_catalog(conn, *, now: datetime | None = None) -> dict[str, int]:
    """Idempotently guarantee twenty safe media choices without network I/O."""

    ensure_schema(conn)
    existing = conn.execute(
        "SELECT COUNT(*) FROM trend_items WHERE is_active=1 AND content_safety='approved_fallback_media_format'"
    ).fetchone()
    if int((existing or [0])[0] or 0) >= len(FALLBACK_MEDIA_FORMATS):
        return {"inserted": 0, "updated": 0}
    return upsert_items(conn, fallback_media_items(now=now), now=now)


def source_registry_from_json(raw_value: str | None) -> dict[str, dict[str, Any]]:
    """Load an optional admin registry without weakening source metadata."""

    raw = str(raw_value or "").strip()
    if not raw:
        return {key: dict(value) for key, value in SOURCE_REGISTRY.items()}
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("trend_source_registry_invalid_json") from exc
    if not isinstance(decoded, Mapping) or not decoded:
        raise ValueError("trend_source_registry_must_be_object")
    registry: dict[str, dict[str, Any]] = {}
    for raw_key, raw_source in decoded.items():
        key = _clean(raw_key, 80)
        source = dict(raw_source) if isinstance(raw_source, Mapping) else {}
        name = _clean(source.get("name"), 160)
        url = _clean(source.get("url"), 1000)
        adapter = _clean(source.get("adapter"), 80)
        feed_url = _clean(source.get("feed_url"), 1000)
        if not key or not name or not url.startswith(("https://", "http://")) or not adapter:
            raise ValueError("trend_source_registry_entry_invalid")
        if feed_url and not feed_url.startswith(("https://", "http://")):
            raise ValueError("trend_source_registry_feed_invalid")
        registry[key] = {
            "name": name,
            "url": url,
            "feed_url": feed_url,
            "adapter": adapter,
        }
    return registry


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_text(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return ""
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return raw
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def parse_time(value: datetime | str | None) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = parsedate_to_datetime(raw)
            except (TypeError, ValueError, OverflowError):
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS trend_items (
            trend_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            short_title TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            platform TEXT NOT NULL DEFAULT '',
            region TEXT NOT NULL DEFAULT '',
            language TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '',
            keywords TEXT NOT NULL DEFAULT '[]',
            source_name TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            source_published_at TEXT NOT NULL DEFAULT '',
            collected_at TEXT NOT NULL DEFAULT '',
            last_verified_at TEXT NOT NULL DEFAULT '',
            expires_at TEXT NOT NULL DEFAULT '',
            evidence TEXT NOT NULL DEFAULT '',
            popularity_signal TEXT NOT NULL DEFAULT '',
            content_safety TEXT NOT NULL DEFAULT 'reviewed_public_metadata',
            is_active INTEGER NOT NULL DEFAULT 1,
            version INTEGER NOT NULL DEFAULT 1
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS trend_refresh_state (
            state_key TEXT PRIMARY KEY,
            last_run_at TEXT NOT NULL DEFAULT '',
            last_success_at TEXT NOT NULL DEFAULT '',
            next_run_at TEXT NOT NULL DEFAULT '',
            sources_checked TEXT NOT NULL DEFAULT '[]',
            inserted_count INTEGER NOT NULL DEFAULT 0,
            updated_count INTEGER NOT NULL DEFAULT 0,
            expired_count INTEGER NOT NULL DEFAULT 0,
            blocker TEXT NOT NULL DEFAULT '',
            detail_json TEXT NOT NULL DEFAULT '{}'
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trend_items_active_fresh "
        "ON trend_items(is_active,last_verified_at,category)"
    )
    conn.commit()


def _clean(value: Any, limit: int = 1000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _trend_id(source_name: str, source_url: str, title: str) -> str:
    identity = "|".join((source_name.casefold(), source_url.casefold(), title.casefold()))
    return "tr_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def _media_search_text(raw: Mapping[str, Any]) -> str:
    keywords = raw.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [keywords]
    return " ".join(
        _clean(value, 1000).casefold()
        for value in (
            raw.get("title"), raw.get("short_title"), raw.get("summary"),
            raw.get("platform"), raw.get("category"), raw.get("evidence"),
            *list(keywords),
        )
        if _clean(value, 1000)
    )


def is_media_trend(raw: Mapping[str, Any]) -> bool:
    """Return true only when the record describes a reusable media trend."""

    title = _clean(raw.get("title") or raw.get("short_title"), 240).casefold()
    platform = _clean(raw.get("platform"), 160).casefold()
    searchable = _media_search_text(raw)
    if title in GENERIC_SEARCH_ONLY_TITLES and not any(term in platform for term in MEDIA_PLATFORM_TERMS):
        return False
    platform_match = any(term in platform for term in MEDIA_PLATFORM_TERMS)
    format_match = any(term in searchable for term in MEDIA_TREND_TERMS)
    return bool(platform_match or format_match)


def _deduplicate_media_items(items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for raw in items:
        if not isinstance(raw, Mapping) or not is_media_trend(raw):
            continue
        title = re.sub(r"[^a-z0-9\u00c0-\u024f\u1e00-\u1eff]+", " ", _clean(raw.get("title"), 240).casefold()).strip()
        key = title or _clean(raw.get("source_url"), 1000).casefold()
        if key and key not in unique:
            unique[key] = dict(raw)
    return list(unique.values())


def normalize_item(
    raw: Mapping[str, Any],
    *,
    now: datetime | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> dict[str, Any]:
    now = now or utc_now()
    title = _clean(raw.get("title"), 240)
    source_name = _clean(raw.get("source_name"), 160)
    source_url = _clean(raw.get("source_url"), 1000)
    if not title or not source_name or not source_url.startswith(("https://", "http://")):
        raise ValueError("trend_source_metadata_missing")
    published = parse_time(raw.get("source_published_at"))
    collected = parse_time(raw.get("collected_at")) or now
    verified = parse_time(raw.get("last_verified_at")) or now
    expires = parse_time(raw.get("expires_at")) or (verified + timedelta(days=max(1, max_age_days)))
    keywords = raw.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [part.strip() for part in keywords.split(",") if part.strip()]
    return {
        "trend_id": _clean(raw.get("trend_id"), 80) or _trend_id(source_name, source_url, title),
        "title": title,
        "short_title": _clean(raw.get("short_title") or title, 64),
        "summary": _clean(raw.get("summary"), 500),
        "platform": _clean(raw.get("platform") or "Web / mạng xã hội", 120),
        "region": _clean(raw.get("region") or "VN", 40),
        "language": _clean(raw.get("language") or "vi", 16),
        "category": _clean(raw.get("category") or "Đang thịnh hành", 120),
        "keywords": list(dict.fromkeys(_clean(item, 80) for item in keywords if _clean(item, 80)))[:20],
        "source_name": source_name,
        "source_url": source_url,
        "source_published_at": iso_text(published),
        "collected_at": iso_text(collected),
        "last_verified_at": iso_text(verified),
        "expires_at": iso_text(expires),
        "evidence": _clean(raw.get("evidence") or "Tên chủ đề xuất hiện trong nguồn công khai.", 500),
        # Empty is intentional when the source does not publish a metric.
        "popularity_signal": _clean(raw.get("popularity_signal"), 240),
        "content_safety": _clean(raw.get("content_safety") or "reviewed_public_metadata", 120),
        "is_active": 1 if bool(raw.get("is_active", True)) else 0,
        "version": max(1, int(raw.get("version") or SCHEMA_VERSION)),
    }


_ITEM_COLUMNS = (
    "trend_id", "title", "short_title", "summary", "platform", "region", "language",
    "category", "keywords", "source_name", "source_url", "source_published_at",
    "collected_at", "last_verified_at", "expires_at", "evidence", "popularity_signal",
    "content_safety", "is_active", "version",
)


def upsert_items(conn, items: Iterable[Mapping[str, Any]], *, now: datetime | None = None, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> dict[str, int]:
    ensure_schema(conn)
    inserted = 0
    updated = 0
    for raw in items:
        item = normalize_item(raw, now=now, max_age_days=max_age_days)
        existed = conn.execute("SELECT 1 FROM trend_items WHERE trend_id=?", (item["trend_id"],)).fetchone()
        values = [json.dumps(item[key], ensure_ascii=False) if key == "keywords" else item[key] for key in _ITEM_COLUMNS]
        placeholders = ",".join("?" for _ in _ITEM_COLUMNS)
        updates = ",".join(f"{key}=excluded.{key}" for key in _ITEM_COLUMNS if key != "trend_id")
        conn.execute(
            f"INSERT INTO trend_items ({','.join(_ITEM_COLUMNS)}) VALUES ({placeholders}) "
            f"ON CONFLICT(trend_id) DO UPDATE SET {updates}",
            values,
        )
        if existed:
            updated += 1
        else:
            inserted += 1
    conn.commit()
    return {"inserted": inserted, "updated": updated}


def expire_items(conn, *, now: datetime | None = None) -> int:
    ensure_schema(conn)
    cutoff = iso_text(now or utc_now())
    cursor = conn.execute(
        "UPDATE trend_items SET is_active=0 WHERE is_active=1 AND expires_at<>'' AND expires_at<?",
        (cutoff,),
    )
    conn.commit()
    return max(0, int(cursor.rowcount or 0))


def _row_dict(row) -> dict[str, Any]:
    values = dict(zip(_ITEM_COLUMNS, row))
    try:
        values["keywords"] = json.loads(values.get("keywords") or "[]")
    except (TypeError, ValueError):
        values["keywords"] = []
    return values


def list_items(conn, *, limit: int = 5, offset: int = 0, category: str = "", include_stale_cache: bool = True, now: datetime | None = None) -> list[dict[str, Any]]:
    ensure_schema(conn)
    now = now or utc_now()
    clauses = ["is_active=1"]
    params: list[Any] = []
    if category:
        clauses.append("category=?")
        params.append(str(category))
    if not include_stale_cache:
        clauses.append("(expires_at='' OR expires_at>=?)")
        params.append(iso_text(now))
    params.extend((max(1, min(100, int(limit or 5))), max(0, int(offset or 0))))
    rows = conn.execute(
        f"SELECT {','.join(_ITEM_COLUMNS)} FROM trend_items WHERE {' AND '.join(clauses)} "
        "ORDER BY last_verified_at DESC, source_published_at DESC, title ASC LIMIT ? OFFSET ?",
        tuple(params),
    ).fetchall()
    result = []
    for row in rows:
        item = _row_dict(row)
        expires = parse_time(item.get("expires_at"))
        item["stale"] = bool(expires and expires < now)
        result.append(item)
    return result


def list_media_items(
    conn,
    *,
    limit: int = 5,
    offset: int = 0,
    category: str = "",
    historical: bool = False,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """List only media trends; inactive rows form the historical catalog."""

    ensure_schema(conn)
    clauses = ["is_active=0" if historical else "is_active=1"]
    params: list[Any] = []
    if category:
        clauses.append("category=?")
        params.append(str(category))
    rows = conn.execute(
        f"SELECT {','.join(_ITEM_COLUMNS)} FROM trend_items WHERE {' AND '.join(clauses)} "
        "ORDER BY last_verified_at DESC, source_published_at DESC, title ASC",
        tuple(params),
    ).fetchall()
    current = now or utc_now()
    media_rows: list[dict[str, Any]] = []
    for row in rows:
        item = _row_dict(row)
        if not is_media_trend(item):
            continue
        expires = parse_time(item.get("expires_at"))
        item["stale"] = bool(historical or (expires and expires < current))
        media_rows.append(item)
    start = max(0, int(offset or 0))
    size = max(1, min(100, int(limit or 5)))
    return media_rows[start:start + size]


def list_media_categories(conn, *, historical: bool = False) -> list[str]:
    rows = list_media_items(conn, limit=100, historical=historical)
    return sorted({str(row.get("category") or "").strip() for row in rows if str(row.get("category") or "").strip()})


def get_item(conn, trend_id: str) -> dict[str, Any]:
    ensure_schema(conn)
    row = conn.execute(
        f"SELECT {','.join(_ITEM_COLUMNS)} FROM trend_items WHERE trend_id=?",
        (str(trend_id or ""),),
    ).fetchone()
    return _row_dict(row) if row else {}


def list_categories(conn) -> list[str]:
    ensure_schema(conn)
    return [str(row[0]) for row in conn.execute(
        "SELECT category FROM trend_items WHERE is_active=1 GROUP BY category ORDER BY category"
    ).fetchall() if str(row[0] or "").strip()]


def fetch_google_trends_rss(source: Mapping[str, Any], *, timeout: int = 15) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        str(source.get("feed_url") or ""),
        headers={"User-Agent": "TOAN-AAS-TrendCatalog/1.0"},
    )
    with urllib.request.urlopen(request, timeout=max(3, timeout)) as response:
        payload = response.read()
    root = ET.fromstring(payload)
    now = utc_now()
    items: list[dict[str, Any]] = []
    for node in root.findall("./channel/item"):
        title = _clean(node.findtext("title"), 240)
        link = _clean(node.findtext("link") or source.get("url"), 1000)
        published = _clean(node.findtext("pubDate"), 120)
        description = _clean(node.findtext("description"), 500)
        if not title:
            continue
        items.append({
            "title": title,
            "short_title": title,
            "summary": description,
            "platform": "Google Search",
            "region": "VN",
            "language": "vi",
            "category": "Xu hướng tìm kiếm",
            "keywords": [title],
            "source_name": str(source.get("name") or "Google Trends"),
            "source_url": link or str(source.get("url") or ""),
            "source_published_at": published,
            "collected_at": now,
            "last_verified_at": now,
            "evidence": "Chủ đề xuất hiện trong nguồn Trending Now công khai.",
            "popularity_signal": "",
            "content_safety": "requires_content_planning_review",
        })
    return items


DEFAULT_FETCHERS: dict[str, Callable[[Mapping[str, Any]], list[dict[str, Any]]]] = {
    "google_trends_rss": fetch_google_trends_rss,
}


def refresh_catalog(
    conn,
    *,
    source_registry: Mapping[str, Mapping[str, Any]] | None = None,
    fetchers: Mapping[str, Callable[[Mapping[str, Any]], list[dict[str, Any]]]] | None = None,
    now: datetime | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    refresh_days: int = DEFAULT_REFRESH_DAYS,
) -> dict[str, Any]:
    ensure_schema(conn)
    now = now or utc_now()
    registry = dict(source_registry or SOURCE_REGISTRY)
    adapters = dict(DEFAULT_FETCHERS if fetchers is None else fetchers)
    all_items: list[dict[str, Any]] = []
    checked: list[str] = []
    blockers: list[str] = []
    for key, source in registry.items():
        adapter = str(source.get("adapter") or "")
        fetcher = adapters.get(adapter)
        if not fetcher:
            blockers.append(f"{key}:reference_only")
            continue
        checked.append(key)
        try:
            all_items.extend(fetcher(source) or [])
        except Exception as exc:  # Cache is intentionally kept on source failure.
            blockers.append(f"{key}:{type(exc).__name__}")
    media_items = _deduplicate_media_items(all_items)
    rejected_count = max(0, len(all_items) - len(media_items))
    counts = upsert_items(conn, media_items, now=now, max_age_days=max_age_days) if media_items else {"inserted": 0, "updated": 0}
    success = bool(media_items)
    # A source outage must not empty the public menu. Expiration resumes only
    # after at least one source returned a fresh, attributable item.
    expired = expire_items(conn, now=now) if success else 0
    previous = refresh_status(conn)
    result = {
        "last_run_at": iso_text(now),
        "last_success_at": iso_text(now) if success else str(previous.get("last_success_at") or ""),
        "next_run_at": iso_text(now + timedelta(days=max(1, refresh_days))),
        "sources_checked": checked,
        "inserted_count": counts["inserted"],
        "updated_count": counts["updated"],
        "expired_count": expired,
        "rejected_count": rejected_count,
        "blocker": ";".join(blockers),
        "cache_preserved": not success,
        "paid_provider_calls": 0,
    }
    conn.execute(
        """INSERT INTO trend_refresh_state
           (state_key,last_run_at,last_success_at,next_run_at,sources_checked,inserted_count,updated_count,expired_count,blocker,detail_json)
           VALUES ('weekly',?,?,?,?,?,?,?,?,?)
           ON CONFLICT(state_key) DO UPDATE SET
             last_run_at=excluded.last_run_at,last_success_at=excluded.last_success_at,
             next_run_at=excluded.next_run_at,sources_checked=excluded.sources_checked,
             inserted_count=excluded.inserted_count,updated_count=excluded.updated_count,
             expired_count=excluded.expired_count,blocker=excluded.blocker,detail_json=excluded.detail_json""",
        (
            result["last_run_at"], result["last_success_at"], result["next_run_at"],
            json.dumps(checked, ensure_ascii=False), result["inserted_count"], result["updated_count"],
            result["expired_count"], result["blocker"], json.dumps(result, ensure_ascii=False),
        ),
    )
    conn.commit()
    return result


def refresh_status(conn) -> dict[str, Any]:
    ensure_schema(conn)
    row = conn.execute(
        "SELECT last_run_at,last_success_at,next_run_at,sources_checked,inserted_count,updated_count,expired_count,blocker,detail_json "
        "FROM trend_refresh_state WHERE state_key='weekly'"
    ).fetchone()
    if not row:
        return {
            "last_run_at": "", "last_success_at": "", "next_run_at": "",
            "sources_checked": [], "inserted_count": 0, "updated_count": 0,
            "expired_count": 0, "rejected_count": 0,
            "blocker": "not_refreshed_yet",
        }
    try:
        sources = json.loads(row[3] or "[]")
    except (TypeError, ValueError):
        sources = []
    try:
        detail = json.loads(row[8] or "{}")
    except (TypeError, ValueError):
        detail = {}
    return {
        "last_run_at": row[0] or "",
        "last_success_at": row[1] or "",
        "next_run_at": row[2] or "",
        "sources_checked": sources,
        "inserted_count": int(row[4] or 0),
        "updated_count": int(row[5] or 0),
        "expired_count": int(row[6] or 0),
        "rejected_count": int(detail.get("rejected_count") or 0),
        "blocker": row[7] or "",
    }


def refresh_due(status: Mapping[str, Any], *, now: datetime | None = None) -> bool:
    next_run = parse_time(status.get("next_run_at"))
    return not next_run or next_run <= (now or utc_now())


_CONTENT_STRUCTURES = (
    ("Mở bằng tín hiệu nổi bật", "nêu điều đang thu hút chú ý, giải thích bối cảnh rồi chốt điều người xem cần nhớ"),
    ("Giải thích trong một phút", "đi từ câu hỏi chính tới ba dữ kiện dễ hiểu và kết luận có giới hạn rõ ràng"),
    ("Góc nhìn người trải nghiệm", "đặt người xem vào tình huống thật, theo diễn biến rồi kết bằng nhận xét có căn cứ"),
    ("Trước và sau", "giữ cùng chủ thể để thể hiện thay đổi, nguyên nhân và kết quả mà không phóng đại"),
    ("Một ngày theo xu hướng", "theo mốc thời gian tự nhiên, mỗi cảnh hoàn tất một hoạt động liên quan"),
    ("Ba điều cần biết", "mỗi ý có ví dụ riêng và cảnh cuối nối chúng thành một kết luận thống nhất"),
    ("Sai lầm và cách sửa", "nêu sai lầm thường gặp, hậu quả, cách xử lý rồi xác nhận kết quả"),
    ("Câu hỏi đang được quan tâm", "trả lời từng phần bằng thông tin kiểm chứng được, không biến suy đoán thành sự thật"),
    ("Phân tích lợi ích thực tế", "mở bằng nhu cầu, chứng minh lợi ích bằng tình huống rồi chốt giới hạn sử dụng"),
    ("Cận cảnh chi tiết", "đi từ chi tiết nổi bật ra toàn cảnh, công dụng và mối liên hệ với xu hướng"),
    ("Câu chuyện nguồn gốc", "nối nguồn gốc, lý do được quan tâm hiện tại và giá trị còn lại"),
    ("So sánh hai lựa chọn", "dùng cùng tiêu chí, chỉ rõ điểm mạnh yếu và kết luận theo nhu cầu cụ thể"),
    ("Hướng dẫn từng bước", "mỗi cảnh hoàn tất một bước, không cắt giữa thao tác hoặc lời nói"),
    ("Một thử thách ngắn", "đặt mục tiêu, thực hiện, quan sát và xác nhận kết quả cuối"),
    ("Phản ứng có giải thích", "mở bằng phản ứng, truy nguyên nguyên nhân rồi kết bằng thông tin hữu ích"),
    ("Dữ liệu dễ hiểu", "chỉ dùng số liệu có nguồn, minh họa trực quan và nói rõ giới hạn của dữ liệu"),
    ("Tin nhanh có bối cảnh", "nêu điều mới, bối cảnh cần biết và ảnh hưởng thực tế, tránh giật tít sai lệch"),
    ("Góc nhìn chuyên ngành", "giải nghĩa thuật ngữ, phân tích một tình huống và đưa ra kết luận thận trọng"),
    ("Hành trình khám phá", "dẫn người xem qua các điểm theo một hướng liên tục và khép tại điểm đáng nhớ nhất"),
    ("Mở bằng kết quả", "cho thấy kết quả trước, lần lại quá trình rồi trở về kết quả với lời kết trọn ý"),
)


def build_content_suggestions(
    trend: Mapping[str, Any],
    profile: Mapping[str, Any],
    *,
    scene_count: int,
    aspect_ratio: str,
) -> list[dict[str, Any]]:
    """Build 20 deterministic, trend/profile-specific planning choices."""

    title = _clean(trend.get("title") or trend.get("short_title"), 180)
    summary = _clean(trend.get("summary"), 260)
    profile_key = _clean(profile.get("profile_key") or profile.get("key"), 80)
    profile_label = _clean(profile.get("public_name") or profile.get("label") or profile_key, 160)
    profile_description = _clean(profile.get("description"), 260)
    scene_pattern = [_clean(item, 120) for item in (profile.get("default_scene_pattern") or []) if _clean(item, 120)]
    visual_tags = [_clean(item, 80) for item in (profile.get("visual_tags") or []) if _clean(item, 80)]
    platform_tags = [_clean(item, 80) for item in (profile.get("platform_tags") or []) if _clean(item, 80)]
    goal_tags = [_clean(item, 80) for item in (profile.get("goal_tags") or []) if _clean(item, 80)]
    count = max(1, min(20, int(scene_count or 1)))
    ratio = aspect_ratio if aspect_ratio in {"9:16", "16:9", "1:1", "4:5"} else "9:16"
    if not title or not profile_key:
        raise ValueError("trend_and_profile_required")
    context = f" Bối cảnh nguồn cần giữ: {summary}." if summary else ""
    suggestions: list[dict[str, Any]] = []
    for index, (heading, structure) in enumerate(_CONTENT_STRUCTURES, 1):
        rotated_pattern = scene_pattern[index % len(scene_pattern):] + scene_pattern[:index % len(scene_pattern)] if scene_pattern else []
        pattern_text = " → ".join(rotated_pattern[:min(count, len(rotated_pattern))])
        profile_plan = f" Nhịp profile: {pattern_text}." if pattern_text else ""
        visual_plan = f" Hình ảnh ưu tiên: {', '.join(visual_tags[:3])}." if visual_tags else ""
        platform_plan = f" Kênh phù hợp: {', '.join(platform_tags[:3])}." if platform_tags else ""
        goal_plan = f" Mục tiêu: {', '.join(goal_tags[:3])}." if goal_tags else ""
        suggestions.append({
            "id": f"{profile_key}:{index:02d}",
            "title": f"{heading} · {profile_label}",
            "content": (
                f"{heading} về {title}: {structure}. Dùng đúng {count} cảnh {ratio}; "
                f"mỗi cảnh hoàn tất một ý hoặc hành động và nối tự nhiên sang cảnh kế tiếp. "
                f"Định hướng riêng của {profile_label}: {profile_description or 'bám đúng mục tiêu người xem'}."
                f"{profile_plan}{visual_plan}{platform_plan}{goal_plan}{context} "
                "Không thêm số liệu, nhân vật hoặc kết luận chưa có trong nguồn."
            ),
            "profile_key": profile_key,
            "trend_id": _clean(trend.get("trend_id"), 80),
        })
    return suggestions


def suggestion_page(items: Iterable[Mapping[str, Any]], offset: int = 0, page_size: int = 5) -> list[dict[str, Any]]:
    rows = [dict(item) for item in items]
    if not rows:
        return []
    size = max(1, min(5, int(page_size or 5)))
    start = max(0, int(offset or 0)) % len(rows)
    return [dict(rows[(start + index) % len(rows)]) for index in range(min(size, len(rows)))]
