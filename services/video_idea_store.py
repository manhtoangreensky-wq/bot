"""SQLite-backed, provider-free storage for the Video Ideas catalog.

The store owns planning metadata only. It never creates a media artifact, job,
outbox entry, provider request, or wallet mutation.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = 1
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
ASPECT_RATIO_OPTIONS = ("9:16", "16:9", "1:1", "4:5")
FORBIDDEN_IMPORT_KEYS = {
    "api_key", "apikey", "token", "secret", "password", "authorization",
    "bearer", "private_key", "provider_key",
}

CATEGORY_FIELDS = (
    "category_key", "public_name", "short_button_name", "description", "icon",
    "sort_order", "is_active", "created_by",
)
PRESET_FIELDS = (
    "preset_key", "category_key", "title", "description", "system_guidance",
    "user_prompt_template", "recommended_scene_count", "scene_duration_sec",
    "recommended_aspect_ratio",
    "music_plan", "audio_plan", "voice_plan", "visual_plan", "content_safety_note",
    "recommended_product_id", "recommended_profile_id", "hook", "objective",
    "style", "image_prompt_seed", "video_prompt_seed", "scene_arc",
    "platform_fit_json", "variation_axes_json", "sort_order", "is_active",
    "created_by",
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _dict_rows(cursor) -> list[dict[str, Any]]:
    names = [str(item[0]) for item in cursor.description or ()]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _dict_row(cursor) -> dict[str, Any]:
    rows = _dict_rows(cursor)
    return rows[0] if rows else {}


def _json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value if value is not None else [], ensure_ascii=False, sort_keys=True)


def _json_value(value: Any, fallback: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _table_columns(conn, table_name: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _ensure_columns(conn, table_name: str, columns: Mapping[str, str]) -> None:
    existing = _table_columns(conn, table_name)
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}")


def ensure_schema(conn) -> None:
    """Create the catalog schema without altering unrelated tables."""

    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS video_idea_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_key TEXT NOT NULL UNIQUE,
            public_name TEXT NOT NULL,
            short_button_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            icon TEXT NOT NULL DEFAULT '💡',
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by TEXT NOT NULL DEFAULT 'system'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS video_idea_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            preset_key TEXT NOT NULL UNIQUE,
            category_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            system_guidance TEXT NOT NULL DEFAULT '',
            user_prompt_template TEXT NOT NULL DEFAULT '',
            recommended_scene_count INTEGER NOT NULL DEFAULT 3,
            scene_duration_sec INTEGER NOT NULL DEFAULT 8,
            recommended_aspect_ratio TEXT NOT NULL DEFAULT '9:16',
            music_plan TEXT NOT NULL DEFAULT '',
            audio_plan TEXT NOT NULL DEFAULT '',
            voice_plan TEXT NOT NULL DEFAULT '',
            visual_plan TEXT NOT NULL DEFAULT '',
            content_safety_note TEXT NOT NULL DEFAULT '',
            recommended_product_id TEXT NOT NULL DEFAULT 'video_ai_real',
            recommended_profile_id TEXT NOT NULL DEFAULT 'tutorial_explainer',
            hook TEXT NOT NULL DEFAULT '',
            objective TEXT NOT NULL DEFAULT '',
            style TEXT NOT NULL DEFAULT '',
            image_prompt_seed TEXT NOT NULL DEFAULT '',
            video_prompt_seed TEXT NOT NULL DEFAULT '',
            scene_arc TEXT NOT NULL DEFAULT '',
            platform_fit_json TEXT NOT NULL DEFAULT '[]',
            variation_axes_json TEXT NOT NULL DEFAULT '[]',
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by TEXT NOT NULL DEFAULT 'system',
            FOREIGN KEY(category_id) REFERENCES video_idea_categories(id) ON DELETE RESTRICT
        )
        """
    )
    _ensure_columns(conn, "video_idea_categories", {
        "public_name": "TEXT NOT NULL DEFAULT ''",
        "short_button_name": "TEXT NOT NULL DEFAULT ''",
        "description": "TEXT NOT NULL DEFAULT ''",
        "icon": "TEXT NOT NULL DEFAULT '💡'",
        "sort_order": "INTEGER NOT NULL DEFAULT 0",
        "is_active": "INTEGER NOT NULL DEFAULT 1",
        "version": "INTEGER NOT NULL DEFAULT 1",
        "created_at": "TEXT NOT NULL DEFAULT ''",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
        "created_by": "TEXT NOT NULL DEFAULT 'system'",
    })
    _ensure_columns(conn, "video_idea_presets", {
        "category_id": "INTEGER NOT NULL DEFAULT 0",
        "title": "TEXT NOT NULL DEFAULT ''",
        "description": "TEXT NOT NULL DEFAULT ''",
        "system_guidance": "TEXT NOT NULL DEFAULT ''",
        "user_prompt_template": "TEXT NOT NULL DEFAULT ''",
        "recommended_scene_count": "INTEGER NOT NULL DEFAULT 3",
        "scene_duration_sec": "INTEGER NOT NULL DEFAULT 8",
        "recommended_aspect_ratio": "TEXT NOT NULL DEFAULT '9:16'",
        "music_plan": "TEXT NOT NULL DEFAULT ''",
        "audio_plan": "TEXT NOT NULL DEFAULT ''",
        "voice_plan": "TEXT NOT NULL DEFAULT ''",
        "visual_plan": "TEXT NOT NULL DEFAULT ''",
        "content_safety_note": "TEXT NOT NULL DEFAULT ''",
        "recommended_product_id": "TEXT NOT NULL DEFAULT 'video_ai_real'",
        "recommended_profile_id": "TEXT NOT NULL DEFAULT 'tutorial_explainer'",
        "hook": "TEXT NOT NULL DEFAULT ''",
        "objective": "TEXT NOT NULL DEFAULT ''",
        "style": "TEXT NOT NULL DEFAULT ''",
        "image_prompt_seed": "TEXT NOT NULL DEFAULT ''",
        "video_prompt_seed": "TEXT NOT NULL DEFAULT ''",
        "scene_arc": "TEXT NOT NULL DEFAULT ''",
        "platform_fit_json": "TEXT NOT NULL DEFAULT '[]'",
        "variation_axes_json": "TEXT NOT NULL DEFAULT '[]'",
        "sort_order": "INTEGER NOT NULL DEFAULT 0",
        "is_active": "INTEGER NOT NULL DEFAULT 1",
        "version": "INTEGER NOT NULL DEFAULT 1",
        "created_at": "TEXT NOT NULL DEFAULT ''",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
        "created_by": "TEXT NOT NULL DEFAULT 'system'",
    })
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS video_idea_preset_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            action TEXT NOT NULL,
            actor_id TEXT NOT NULL DEFAULT 'system',
            before_json TEXT NOT NULL DEFAULT '{}',
            after_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )
        """
    )
    _ensure_columns(conn, "video_idea_preset_audit", {
        "entity_type": "TEXT NOT NULL DEFAULT ''",
        "entity_key": "TEXT NOT NULL DEFAULT ''",
        "action": "TEXT NOT NULL DEFAULT ''",
        "actor_id": "TEXT NOT NULL DEFAULT 'system'",
        "before_json": "TEXT NOT NULL DEFAULT '{}'",
        "after_json": "TEXT NOT NULL DEFAULT '{}'",
        "created_at": "TEXT NOT NULL DEFAULT ''",
    })
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_video_idea_categories_active_sort "
        "ON video_idea_categories(is_active, sort_order, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_video_idea_presets_category_active_sort "
        "ON video_idea_presets(category_id, is_active, sort_order, id)"
    )


def seed_catalog(
    conn,
    categories: Iterable[Mapping[str, Any]],
    presets: Iterable[Mapping[str, Any]],
    *,
    actor_id: str = "system_seed",
) -> dict[str, int]:
    """Insert missing curated rows and preserve every later admin edit."""

    ensure_schema(conn)
    now = _now()
    category_inserted = 0
    preset_inserted = 0
    for raw in categories:
        item = normalize_category(raw)
        before = conn.total_changes
        conn.execute(
            """
            INSERT OR IGNORE INTO video_idea_categories
                (category_key, public_name, short_button_name, description, icon,
                 sort_order, is_active, version, created_at, updated_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                item["category_key"], item["public_name"], item["short_button_name"],
                item["description"], item["icon"], item["sort_order"],
                item["is_active"], now, now, str(item.get("created_by") or actor_id),
            ),
        )
        category_inserted += int(conn.total_changes > before)

    category_ids = {
        str(row["category_key"]): int(row["id"])
        for row in list_categories(conn, active_only=False)
    }
    for raw in presets:
        item = normalize_preset(raw)
        category_id = category_ids.get(item["category_key"])
        if not category_id:
            raise ValueError(f"unknown_category:{item['category_key']}")
        before = conn.total_changes
        conn.execute(
            """
            INSERT OR IGNORE INTO video_idea_presets
                (preset_key, category_id, title, description, system_guidance,
                 user_prompt_template, recommended_scene_count, scene_duration_sec,
                 recommended_aspect_ratio,
                 music_plan, audio_plan, voice_plan, visual_plan, content_safety_note,
                 recommended_product_id, recommended_profile_id, hook, objective,
                 style, image_prompt_seed, video_prompt_seed, scene_arc,
                 platform_fit_json, variation_axes_json, sort_order, is_active,
                 version, created_at, updated_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                item["preset_key"], category_id, item["title"], item["description"],
                item["system_guidance"], item["user_prompt_template"],
                item["recommended_scene_count"], item["scene_duration_sec"],
                item["recommended_aspect_ratio"],
                item["music_plan"], item["audio_plan"], item["voice_plan"], item["visual_plan"],
                item["content_safety_note"], item["recommended_product_id"],
                item["recommended_profile_id"], item["hook"], item["objective"],
                item["style"], item["image_prompt_seed"], item["video_prompt_seed"],
                item["scene_arc"], _json_text(item["platform_fit_json"]),
                _json_text(item["variation_axes_json"]), item["sort_order"],
                item["is_active"], now, now, str(item.get("created_by") or actor_id),
            ),
        )
        preset_inserted += int(conn.total_changes > before)
    return {"categories_inserted": category_inserted, "presets_inserted": preset_inserted}


def list_categories(conn, *, active_only: bool = True) -> list[dict[str, Any]]:
    ensure_schema(conn)
    sql = "SELECT * FROM video_idea_categories"
    params: tuple[Any, ...] = ()
    if active_only:
        sql += " WHERE is_active=1"
    sql += " ORDER BY sort_order, id"
    return _dict_rows(conn.execute(sql, params))


def category_by_id(conn, category_id: int) -> dict[str, Any]:
    ensure_schema(conn)
    return _dict_row(conn.execute("SELECT * FROM video_idea_categories WHERE id=?", (int(category_id),)))


def category_by_key(conn, category_key: str) -> dict[str, Any]:
    ensure_schema(conn)
    return _dict_row(conn.execute("SELECT * FROM video_idea_categories WHERE category_key=?", (str(category_key),)))


def list_presets(
    conn,
    *,
    category_id: int | None = None,
    active_only: bool = True,
    offset: int = 0,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    ensure_schema(conn)
    where: list[str] = []
    params: list[Any] = []
    if category_id is not None:
        where.append("p.category_id=?")
        params.append(int(category_id))
    if active_only:
        where.append("p.is_active=1")
        where.append("c.is_active=1")
    sql = (
        "SELECT p.*, c.category_key, c.public_name AS category_name, "
        "c.short_button_name AS category_button_name, c.icon AS category_icon "
        "FROM video_idea_presets p JOIN video_idea_categories c ON c.id=p.category_id"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY c.sort_order, p.sort_order, p.id LIMIT ? OFFSET ?"
    params.extend([max(1, min(int(limit or 1), 2000)), max(0, int(offset or 0))])
    return [_hydrate_preset(row) for row in _dict_rows(conn.execute(sql, tuple(params)))]


def preset_by_id(conn, preset_id: int) -> dict[str, Any]:
    ensure_schema(conn)
    cursor = conn.execute(
        """
        SELECT p.*, c.category_key, c.public_name AS category_name,
               c.short_button_name AS category_button_name, c.icon AS category_icon
        FROM video_idea_presets p
        JOIN video_idea_categories c ON c.id=p.category_id
        WHERE p.id=?
        """,
        (int(preset_id),),
    )
    return _hydrate_preset(_dict_row(cursor))


def preset_by_key(conn, preset_key: str) -> dict[str, Any]:
    ensure_schema(conn)
    cursor = conn.execute(
        """
        SELECT p.*, c.category_key, c.public_name AS category_name,
               c.short_button_name AS category_button_name, c.icon AS category_icon
        FROM video_idea_presets p
        JOIN video_idea_categories c ON c.id=p.category_id
        WHERE p.preset_key=?
        """,
        (str(preset_key),),
    )
    return _hydrate_preset(_dict_row(cursor))


def _hydrate_preset(row: Mapping[str, Any] | None) -> dict[str, Any]:
    result = dict(row or {})
    if not result:
        return {}
    result["platform_fit"] = list(_json_value(result.get("platform_fit_json"), []))
    result["variation_axes"] = list(_json_value(result.get("variation_axes_json"), []))
    result["idea_id"] = str(result.get("preset_key") or "")
    result["category"] = str(result.get("category_key") or "")
    result["summary"] = str(result.get("description") or "")
    result["recommended_scene_count"] = int(result.get("recommended_scene_count") or 3)
    result["scene_seconds"] = int(result.get("scene_duration_sec") or 8)
    aspect_ratio = str(result.get("recommended_aspect_ratio") or "9:16").strip()
    result["recommended_aspect_ratio"] = aspect_ratio if aspect_ratio in ASPECT_RATIO_OPTIONS else "9:16"
    result["aspect_ratio"] = result["recommended_aspect_ratio"]
    result.update({
        "reference_only": True,
        "planning_only": True,
        "provider_called": False,
        "image_provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "wallet_mutations": 0,
        "xu_charged": 0,
    })
    return result


def catalog_counts(conn) -> dict[str, int]:
    ensure_schema(conn)
    categories = int(conn.execute("SELECT COUNT(*) FROM video_idea_categories WHERE is_active=1").fetchone()[0])
    presets = int(conn.execute("SELECT COUNT(*) FROM video_idea_presets WHERE is_active=1").fetchone()[0])
    return {"categories": categories, "presets": presets}


def normalize_category(raw: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(raw or {})
    _reject_secret_fields(item)
    _reject_unsafe_text(item)
    key = str(item.get("category_key") or "").strip().lower()
    if not KEY_RE.fullmatch(key):
        raise ValueError("invalid_category_key")
    public_name = _bounded(item.get("public_name"), 120, "public_name")
    short_name = _bounded(item.get("short_button_name") or public_name, 40, "short_button_name")
    return {
        "category_key": key,
        "public_name": public_name,
        "short_button_name": short_name,
        "description": _bounded(item.get("description"), 600, "description", required=False),
        "icon": _bounded(item.get("icon") or "💡", 12, "icon"),
        "sort_order": int(item.get("sort_order") or 0),
        "is_active": 1 if bool(int(item.get("is_active", 1))) else 0,
        "created_by": _bounded(item.get("created_by") or "admin", 80, "created_by"),
    }


def normalize_preset(raw: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(raw or {})
    _reject_secret_fields(item)
    _reject_unsafe_text(item)
    key = str(item.get("preset_key") or item.get("idea_id") or "").strip().lower()
    category_key = str(item.get("category_key") or item.get("category") or "").strip().lower()
    if not KEY_RE.fullmatch(key):
        raise ValueError("invalid_preset_key")
    if not KEY_RE.fullmatch(category_key):
        raise ValueError("invalid_category_key")
    scene_count = int(item.get("recommended_scene_count") or 3)
    if not 1 <= scene_count <= 20:
        raise ValueError("recommended_scene_count_out_of_range")
    duration = int(item.get("scene_duration_sec") or item.get("scene_seconds") or 8)
    if duration != 8:
        raise ValueError("scene_duration_must_be_8")
    aspect_ratio = str(
        item.get("recommended_aspect_ratio")
        or item.get("aspect_ratio")
        or "9:16"
    ).strip()
    if aspect_ratio not in ASPECT_RATIO_OPTIONS:
        raise ValueError("invalid_recommended_aspect_ratio")
    return {
        "preset_key": key,
        "category_key": category_key,
        "title": _bounded(item.get("title"), 160, "title"),
        "description": _bounded(item.get("description") or item.get("summary"), 1200, "description"),
        "system_guidance": _bounded(item.get("system_guidance"), 4000, "system_guidance"),
        "user_prompt_template": _bounded(item.get("user_prompt_template"), 4000, "user_prompt_template"),
        "recommended_scene_count": scene_count,
        "scene_duration_sec": duration,
        "recommended_aspect_ratio": aspect_ratio,
        "music_plan": _bounded(item.get("music_plan"), 600, "music_plan"),
        "audio_plan": _bounded(
            item.get("audio_plan") or "Âm thanh hiện trường tùy chọn; chỉ cân chỉnh sau khi ghép video.",
            800,
            "audio_plan",
        ),
        "voice_plan": _bounded(item.get("voice_plan"), 600, "voice_plan"),
        "visual_plan": _bounded(item.get("visual_plan"), 1000, "visual_plan"),
        "content_safety_note": _bounded(item.get("content_safety_note"), 1200, "content_safety_note", required=False),
        "recommended_product_id": _bounded(item.get("recommended_product_id") or "video_ai_real", 80, "recommended_product_id"),
        "recommended_profile_id": _bounded(item.get("recommended_profile_id") or "tutorial_explainer", 80, "recommended_profile_id"),
        "hook": _bounded(item.get("hook"), 600, "hook", required=False),
        "objective": _bounded(item.get("objective"), 600, "objective", required=False),
        "style": _bounded(item.get("style"), 600, "style", required=False),
        "image_prompt_seed": _bounded(item.get("image_prompt_seed"), 2500, "image_prompt_seed", required=False),
        "video_prompt_seed": _bounded(item.get("video_prompt_seed"), 2500, "video_prompt_seed", required=False),
        "scene_arc": _bounded(item.get("scene_arc"), 800, "scene_arc", required=False),
        "platform_fit_json": item.get("platform_fit_json", item.get("platform_fit", [])),
        "variation_axes_json": item.get("variation_axes_json", item.get("variation_axes", [])),
        "sort_order": int(item.get("sort_order") or 0),
        "is_active": 1 if bool(int(item.get("is_active", 1))) else 0,
        "created_by": _bounded(item.get("created_by") or "admin", 80, "created_by"),
    }


def _bounded(value: Any, limit: int, field: str, *, required: bool = True) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"missing_{field}")
    if len(text) > limit:
        raise ValueError(f"{field}_too_long")
    return text


def _audit(conn, entity_type: str, entity_key: str, action: str, actor_id: str, before: Any, after: Any) -> None:
    conn.execute(
        """
        INSERT INTO video_idea_preset_audit
            (entity_type, entity_key, action, actor_id, before_json, after_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(entity_type), str(entity_key), str(action), str(actor_id or "admin"),
            json.dumps(before or {}, ensure_ascii=False, sort_keys=True),
            json.dumps(after or {}, ensure_ascii=False, sort_keys=True), _now(),
        ),
    )


def create_category(conn, payload: Mapping[str, Any], *, actor_id: str) -> dict[str, Any]:
    item = normalize_category({**dict(payload), "created_by": actor_id})
    now = _now()
    conn.execute(
        """
        INSERT INTO video_idea_categories
            (category_key, public_name, short_button_name, description, icon,
             sort_order, is_active, version, created_at, updated_at, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """,
        (
            item["category_key"], item["public_name"], item["short_button_name"],
            item["description"], item["icon"], item["sort_order"], item["is_active"],
            now, now, actor_id,
        ),
    )
    created = category_by_key(conn, item["category_key"])
    _audit(conn, "category", item["category_key"], "create", actor_id, {}, created)
    conn.commit()
    return created


def update_category(conn, category_id: int, payload: Mapping[str, Any], *, actor_id: str) -> dict[str, Any]:
    before = category_by_id(conn, category_id)
    if not before:
        raise ValueError("category_not_found")
    merged = normalize_category({**before, **dict(payload), "created_by": before.get("created_by") or actor_id})
    conn.execute(
        """
        UPDATE video_idea_categories SET
            category_key=?, public_name=?, short_button_name=?, description=?, icon=?,
            sort_order=?, is_active=?, version=version+1, updated_at=?
        WHERE id=?
        """,
        (
            merged["category_key"], merged["public_name"], merged["short_button_name"],
            merged["description"], merged["icon"], merged["sort_order"],
            merged["is_active"], _now(), int(category_id),
        ),
    )
    after = category_by_id(conn, category_id)
    _audit(conn, "category", after["category_key"], "edit", actor_id, before, after)
    conn.commit()
    return after


def set_category_active(conn, category_id: int, active: bool, *, actor_id: str) -> dict[str, Any]:
    return update_category(conn, category_id, {"is_active": 1 if active else 0}, actor_id=actor_id)


def create_preset(conn, payload: Mapping[str, Any], *, actor_id: str) -> dict[str, Any]:
    item = normalize_preset({**dict(payload), "created_by": actor_id})
    category = category_by_key(conn, item["category_key"])
    if not category:
        raise ValueError("category_not_found")
    now = _now()
    conn.execute(
        """
        INSERT INTO video_idea_presets
            (preset_key, category_id, title, description, system_guidance,
             user_prompt_template, recommended_scene_count, scene_duration_sec,
             recommended_aspect_ratio,
             music_plan, audio_plan, voice_plan, visual_plan, content_safety_note,
             recommended_product_id, recommended_profile_id, hook, objective,
             style, image_prompt_seed, video_prompt_seed, scene_arc,
             platform_fit_json, variation_axes_json, sort_order, is_active,
             version, created_at, updated_at, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """,
        (
            item["preset_key"], category["id"], item["title"], item["description"],
            item["system_guidance"], item["user_prompt_template"],
            item["recommended_scene_count"], item["scene_duration_sec"],
            item["recommended_aspect_ratio"],
            item["music_plan"], item["audio_plan"], item["voice_plan"], item["visual_plan"],
            item["content_safety_note"], item["recommended_product_id"],
            item["recommended_profile_id"], item["hook"], item["objective"],
            item["style"], item["image_prompt_seed"], item["video_prompt_seed"],
            item["scene_arc"], _json_text(item["platform_fit_json"]),
            _json_text(item["variation_axes_json"]), item["sort_order"],
            item["is_active"], now, now, actor_id,
        ),
    )
    created = preset_by_key(conn, item["preset_key"])
    _audit(conn, "preset", item["preset_key"], "create", actor_id, {}, created)
    conn.commit()
    return created


def update_preset(conn, preset_id: int, payload: Mapping[str, Any], *, actor_id: str) -> dict[str, Any]:
    before = preset_by_id(conn, preset_id)
    if not before:
        raise ValueError("preset_not_found")
    merged = normalize_preset({**before, **dict(payload), "created_by": before.get("created_by") or actor_id})
    category = category_by_key(conn, merged["category_key"])
    if not category:
        raise ValueError("category_not_found")
    conn.execute(
        """
        UPDATE video_idea_presets SET
            preset_key=?, category_id=?, title=?, description=?, system_guidance=?,
            user_prompt_template=?, recommended_scene_count=?, scene_duration_sec=?,
            recommended_aspect_ratio=?,
            music_plan=?, audio_plan=?, voice_plan=?, visual_plan=?, content_safety_note=?,
            recommended_product_id=?, recommended_profile_id=?, hook=?, objective=?,
            style=?, image_prompt_seed=?, video_prompt_seed=?, scene_arc=?,
            platform_fit_json=?, variation_axes_json=?, sort_order=?, is_active=?,
            version=version+1, updated_at=?
        WHERE id=?
        """,
        (
            merged["preset_key"], category["id"], merged["title"], merged["description"],
            merged["system_guidance"], merged["user_prompt_template"],
            merged["recommended_scene_count"], merged["scene_duration_sec"],
            merged["recommended_aspect_ratio"],
            merged["music_plan"], merged["audio_plan"], merged["voice_plan"], merged["visual_plan"],
            merged["content_safety_note"], merged["recommended_product_id"],
            merged["recommended_profile_id"], merged["hook"], merged["objective"],
            merged["style"], merged["image_prompt_seed"], merged["video_prompt_seed"],
            merged["scene_arc"], _json_text(merged["platform_fit_json"]),
            _json_text(merged["variation_axes_json"]), merged["sort_order"],
            merged["is_active"], _now(), int(preset_id),
        ),
    )
    after = preset_by_id(conn, preset_id)
    _audit(conn, "preset", after["preset_key"], "edit", actor_id, before, after)
    conn.commit()
    return after


def set_preset_active(conn, preset_id: int, active: bool, *, actor_id: str) -> dict[str, Any]:
    before = preset_by_id(conn, preset_id)
    if not before:
        raise ValueError("preset_not_found")
    action = "enable" if active else "disable"
    after = update_preset(conn, preset_id, {"is_active": 1 if active else 0}, actor_id=actor_id)
    # update_preset already records the versioned edit; add the semantic audit row.
    _audit(conn, "preset", after["preset_key"], action, actor_id, before, after)
    conn.commit()
    return after


def clone_preset(conn, preset_id: int, new_key: str, new_title: str, *, actor_id: str) -> dict[str, Any]:
    source = preset_by_id(conn, preset_id)
    if not source:
        raise ValueError("preset_not_found")
    payload = {**source, "preset_key": new_key, "title": new_title, "is_active": 0}
    created = create_preset(conn, payload, actor_id=actor_id)
    _audit(conn, "preset", created["preset_key"], "clone", actor_id, source, created)
    conn.commit()
    return created


def list_audit(conn, *, limit: int = 20) -> list[dict[str, Any]]:
    ensure_schema(conn)
    return _dict_rows(
        conn.execute(
            "SELECT * FROM video_idea_preset_audit ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit or 20), 100)),),
        )
    )


def export_catalog(conn) -> dict[str, Any]:
    categories = list_categories(conn, active_only=False)
    presets = list_presets(conn, active_only=False)
    category_fields = {"category_key", "public_name", "short_button_name", "description", "icon", "sort_order", "is_active", "version"}
    preset_fields = {
        "preset_key", "category_key", "title", "description", "system_guidance",
        "user_prompt_template", "recommended_scene_count", "scene_duration_sec",
        "recommended_aspect_ratio",
        "music_plan", "audio_plan", "voice_plan", "visual_plan", "content_safety_note",
        "recommended_product_id", "recommended_profile_id", "hook", "objective",
        "style", "image_prompt_seed", "video_prompt_seed", "scene_arc",
        "platform_fit", "variation_axes", "sort_order", "is_active", "version",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "categories": [{key: row.get(key) for key in category_fields} for row in categories],
        "presets": [{key: row.get(key) for key in preset_fields} for row in presets],
    }


def validate_import_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    if int(data.get("schema_version") or 0) != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    _reject_secret_fields(data)
    categories_raw = data.get("categories")
    presets_raw = data.get("presets")
    if not isinstance(categories_raw, list) or not isinstance(presets_raw, list):
        raise ValueError("categories_and_presets_must_be_lists")
    categories = [normalize_category(item) for item in categories_raw]
    presets = [normalize_preset(item) for item in presets_raw]
    category_keys = [item["category_key"] for item in categories]
    preset_keys = [item["preset_key"] for item in presets]
    if len(category_keys) != len(set(category_keys)):
        raise ValueError("duplicate_category_key")
    if len(preset_keys) != len(set(preset_keys)):
        raise ValueError("duplicate_preset_key")
    known_categories = set(category_keys)
    if any(item["category_key"] not in known_categories for item in presets):
        raise ValueError("preset_references_unknown_category")
    return {"schema_version": SCHEMA_VERSION, "categories": categories, "presets": presets}


def _reject_secret_fields(value: Any, path: str = "") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in FORBIDDEN_IMPORT_KEYS or any(token in normalized for token in ("api_key", "secret", "password", "private_key", "bearer")):
                raise ValueError(f"provider_secret_not_allowed:{path}{key}")
            _reject_secret_fields(child, f"{path}{key}.")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_fields(child, f"{path}{index}.")


def _reject_unsafe_text(value: Any, path: str = "") -> None:
    """Reject executable markup and obvious destructive statement payloads.

    SQL remains parameterized everywhere; this validation is an additional
    admin-import guard rather than a replacement for bound parameters.
    """

    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_unsafe_text(child, f"{path}{key}.")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _reject_unsafe_text(child, f"{path}{index}.")
        return
    if not isinstance(value, str):
        return
    lowered = value.lower()
    blocked = (
        "\x00", "<script", "javascript:", "data:text/html", "<?php",
        "; drop table", "; delete from", "; alter table", " union select ",
    )
    if any(token in lowered for token in blocked):
        raise ValueError(f"unsafe_script_or_sql_payload:{path.rstrip('.')}")


def apply_import(conn, payload: Mapping[str, Any], *, actor_id: str) -> dict[str, int]:
    data = validate_import_payload(payload)
    ensure_schema(conn)
    created_categories = 0
    updated_categories = 0
    created_presets = 0
    updated_presets = 0
    for category in data["categories"]:
        existing = category_by_key(conn, category["category_key"])
        if existing:
            update_category(conn, int(existing["id"]), category, actor_id=actor_id)
            updated_categories += 1
        else:
            create_category(conn, category, actor_id=actor_id)
            created_categories += 1
    for preset in data["presets"]:
        existing = preset_by_key(conn, preset["preset_key"])
        if existing:
            update_preset(conn, int(existing["id"]), preset, actor_id=actor_id)
            updated_presets += 1
        else:
            create_preset(conn, preset, actor_id=actor_id)
            created_presets += 1
    conn.commit()
    return {
        "categories_created": created_categories,
        "categories_updated": updated_categories,
        "presets_created": created_presets,
        "presets_updated": updated_presets,
    }
