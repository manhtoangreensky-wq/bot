import sqlite3
from pathlib import Path

import bot


def _callbacks(markup):
    return {button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data}


def _prepare_reference_db(monkeypatch, tmp_path):
    db_path = tmp_path / "reference-pipeline.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE channel_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, channel_name TEXT, platform TEXT,
            channel_url TEXT, niche TEXT, target_audience TEXT, content_style TEXT, tone TEXT,
            language TEXT, blocked_topics_json TEXT, cta_default TEXT, affiliate_allowed INTEGER,
            preferred_aspect_ratio TEXT, preferred_duration_seconds INTEGER, primary_goal TEXT,
            status TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE publish_packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, reference_video_id INTEGER,
            channel_profile_id INTEGER, platform TEXT, title TEXT, caption TEXT, hashtags TEXT,
            cta TEXT, pinned_comment TEXT, thumbnail_idea TEXT, posting_time_note TEXT,
            checklist_json TEXT, content_json TEXT, status TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE content_performance_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, channel_profile_id INTEGER,
            publish_package_id INTEGER, post_url TEXT, event_type TEXT, value_number REAL,
            amount_vnd REAL, note TEXT, created_at TEXT
        );
        """
    )
    conn.commit()
    conn.close()
    return db_path


def test_reference_video_menu_opens_and_all_hub_callbacks_are_routed():
    callbacks = _callbacks(bot.video_reference_hub_keyboard("vi"))
    assert {
        "videoref|link", "videoref|start", "videoref|profile", "videoref|catalog",
        "videoref|format", "videoref|publish_package", "menu|main_video", "menu|main",
    }.issubset(callbacks)


def test_reference_entries_are_isolated_from_free_hub():
    callbacks = _callbacks(bot.free_hub_main_keyboard("vi"))
    assert not {"videoref|hub", "videoref|profile", "videoref|publish_package", "videoref|catalog"}.intersection(callbacks)
    assert "freehub|library" in callbacks


def test_reference_back_routes_stay_inside_video_reference_flow():
    hub_callbacks = _callbacks(bot.video_reference_hub_keyboard("vi"))
    profile_callbacks = _callbacks(bot.channel_profile_keyboard("vi"))
    catalog_callbacks = _callbacks(
        bot.video_v6_keyboard(
            [("📤 Thêm video mẫu", "videoref|start")],
            "vi",
            back=("⬅️ Video mẫu / Kênh mẫu", "videoref|hub"),
        )
    )

    assert "menu|main_video" in hub_callbacks
    assert "videoref|hub" in profile_callbacks
    assert "videoref|hub" in catalog_callbacks
    assert "freehub|main" not in profile_callbacks | catalog_callbacks


def test_channel_profile_and_publish_package_are_channel_aware(monkeypatch, tmp_path):
    _prepare_reference_db(monkeypatch, tmp_path)
    profile_id = bot.create_channel_profile(
        123,
        {
            "platform": "facebook",
            "niche": "nước hoa nam",
            "target_audience": "nam 25-40 tuổi",
            "content_style": "sang trọng, ngắn",
            "tone": "rõ ràng",
            "affiliate_allowed": True,
            "primary_goal": "sales",
            "language": "vi",
        },
    )
    assert profile_id > 0
    profile = bot.get_latest_channel_profile(123)
    assert profile["platform"] == "facebook"
    package = bot.create_publish_package(123, {"selected_topic": "nước hoa nam"}, profile)
    assert package["id"] > 0
    assert package["platform"] == "facebook"
    assert package["title"] and package["caption"] and package["hashtags"] and package["cta"]
    assert package["pinned_comment"] and package["checklist"]


def test_manual_performance_event_insert(monkeypatch, tmp_path):
    _prepare_reference_db(monkeypatch, tmp_path)
    event_id = bot.add_content_performance_event(
        456,
        {"post_url": "https://example.com/post", "event_type": "view", "value_number": 1200},
    )
    assert event_id > 0


def test_reference_pipeline_is_manual_safe_and_uses_common_finalization():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    handler = source.split("async def handle_video_reference_callback", 1)[1].split("async def handle_self_scene_ai_callback", 1)[0]
    assert 'open_video_finalization(query, uid, "videoref"' in handler
    assert "platform download is disabled" in source
    assert "Manual publish package only" in source
    assert "Không copy/reup" in source or "không copy/reup" in source
    assert "admin_import_reference_video" in source
    assert "reference_catalog_status" in source


def test_reference_planning_text_confirms_no_xu_charge():
    assert "không trừ Xu" in bot.video_reference_hub_text("vi")
    assert "chưa trừ Xu" in bot.video_reference_plan_text({"selected_topic": "sản phẩm mẫu"}, "vi")
