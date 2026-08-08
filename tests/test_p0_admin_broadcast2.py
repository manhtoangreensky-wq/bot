import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

import admin_broadcast as broadcast
from services import ui_navigation


BOT_SOURCE = Path(__file__).resolve().parents[1] / "bot.py"
BOT_TEXT = BOT_SOURCE.read_text(encoding="utf-8")


def make_db(tmp_path: Path) -> Path:
    db = tmp_path / "broadcast-lite.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE users (user_id TEXT PRIMARY KEY, username TEXT, join_date TEXT, "
        "user_market TEXT DEFAULT '', country_code TEXT DEFAULT '', "
        "account_region TEXT DEFAULT '', international_account INTEGER DEFAULT 0, "
        "user_language TEXT DEFAULT '', initial_user_language TEXT DEFAULT '')"
    )
    conn.executemany(
        "INSERT INTO users(user_id,username,join_date,user_market,country_code,account_region,"
        "international_account,user_language,initial_user_language) VALUES (?,?,?,?,?,?,?,?,?)",
        [
            ("100", "one", "today", "VN", "VN", "VIETNAM", 0, "vi", "vi"),
            ("200", "two", "today", "INTL", "US", "INTERNATIONAL", 1, "en", "en"),
            ("bad-id", "bad", "today", "VN", "VN", "VIETNAM", 0, "vi", "vi"),
        ],
    )
    broadcast.ensure_schema(conn)
    conn.commit()
    conn.close()
    return db


def test_admin_guard_templates_and_canonical_routes():
    assert not broadcast.is_authorized_admin("42", ["7", "8"])
    assert broadcast.is_authorized_admin("42", [42])
    assert broadcast.TEMPLATES["first_topup"]["ctas"] == []
    assert "30% Xu" in broadcast.TEMPLATES["first_topup"]["message"]
    assert "20% Xu" in broadcast.TEMPLATES["second_topup"]["message"]
    assert broadcast.CTA_REGISTRY["topup"]["callback_data"] == "menu|main_topup"
    assert broadcast.CTA_REGISTRY["video"]["callback_data"] == "menu|main_video"
    assert broadcast.CTA_REGISTRY["image"]["callback_data"] == "menu|main_image"
    assert broadcast.CTA_REGISTRY["support"]["callback_data"] == "menu|support"
    assert broadcast.AUTO_NOTICE_CONTENT["first_topup_30"]["ctas"] == ["topup"]
    source = BOT_TEXT
    for key in broadcast.SPECIAL_FEATURE_CTA_KEYS:
        route = broadcast.CTA_REGISTRY[key]["callback_data"]
        assert route.startswith("menu|main_")
        action = route.split("|", 1)[1]
        assert f'if action == "{action}":' in source
    assert all(len(row) <= 2 for row in broadcast._campaign_keyboard(["topup", "video", "image", "support"]))


def test_compose_custom_text_photo_and_preview(tmp_path: Path):
    db = make_db(tmp_path)
    draft = broadcast.create_empty_draft(db, 9001)
    draft = broadcast.set_draft_message(db, draft["draft_id"], 9001, "Thông báo tùy ý <không parse>")
    draft = broadcast.set_draft_ctas(db, draft["draft_id"], 9001, ["video", "support", "image", "topup", "video"])
    draft = broadcast.set_draft_market(db, draft["draft_id"], 9001, "all")
    draft = broadcast.set_draft_audience(db, draft["draft_id"], 9001, "all")
    preview = broadcast.preview_draft(db, draft["draft_id"], 9001)
    assert "Thông báo tùy ý" in preview["preview_text"]
    assert preview["ctas"] == ["video", "support", "image", "topup"]
    assert preview["audience"]["eligible"] == 2

    photo = broadcast.create_empty_draft(db, 9001, state="awaiting_photo")
    photo = broadcast.set_draft_media(db, photo["draft_id"], 9001, "telegram-file-id", caption="Caption ảnh")
    assert photo["media_file_id"] == "telegram-file-id"
    assert photo["message_text"] == "Caption ảnh"


def test_template_is_optional_content_only_and_can_be_edited(tmp_path: Path):
    db = make_db(tmp_path)
    draft = broadcast.create_empty_draft(db, 9001, state="awaiting_content")
    draft = broadcast.set_draft_ctas(db, draft["draft_id"], 9001, ["video", "support"])
    draft = broadcast.set_draft_market(db, draft["draft_id"], 9001, "vn")
    draft = broadcast.apply_template_to_draft(db, draft["draft_id"], 9001, "first_topup")
    assert "30% Xu" in draft["message_text"]
    assert draft["ctas"] == ["video", "support"]
    edited = broadcast.set_draft_message(db, draft["draft_id"], 9001, "Nội dung do Admin sửa")
    assert edited["message_text"] == "Nội dung do Admin sửa"
    assert edited["ctas"] == ["video", "support"]


def test_generic_cta_registry_supports_one_to_four_or_none(tmp_path: Path):
    db = make_db(tmp_path)
    draft = broadcast.create_empty_draft(db, 9001)
    for key in ("topup", "video", "image", "support"):
        draft = broadcast.toggle_draft_cta(db, draft["draft_id"], 9001, key)
    assert draft["ctas"] == ["topup", "video", "image", "support"]
    with pytest.raises(ValueError, match="Tối đa 4"):
        broadcast.toggle_draft_cta(db, draft["draft_id"], 9001, "f_ai")
    assert broadcast.set_draft_ctas(db, draft["draft_id"], 9001, [])["ctas"] == []


def test_pending_input_cleanup_clears_every_stale_draft(tmp_path: Path):
    db = make_db(tmp_path)
    first = broadcast.create_empty_draft(db, 9001, state="awaiting_message")
    second = broadcast.create_empty_draft(db, 9001, state="awaiting_caption")

    latest = broadcast.get_latest_draft(db, 9001, states=("awaiting_message", "awaiting_caption"))
    assert latest["draft_id"] == second["draft_id"]
    assert broadcast.clear_pending_drafts(db, 9001) == 2
    assert broadcast.get_latest_draft(db, 9001, states=("awaiting_message", "awaiting_caption")) is None
    assert broadcast.get_draft(db, first["draft_id"], 9001)["state"] == "draft"
    assert broadcast.get_draft(db, second["draft_id"], 9001)["state"] == "draft"


def test_all_used_bot_audience_returns_to_draft_with_expected_delivery_count(tmp_path: Path):
    db = make_db(tmp_path)
    draft = broadcast.create_empty_draft(db, 9001)
    draft = broadcast.set_draft_message(db, draft["draft_id"], 9001, "Thông báo toàn bot")
    draft = broadcast.set_draft_market(db, draft["draft_id"], 9001, "all")
    draft = broadcast.set_draft_audience(db, draft["draft_id"], 9001, "all")

    preview = broadcast.preview_draft(db, draft["draft_id"], 9001)
    assert preview["audience"] == {
        "total": 2,
        "eligible": 2,
        "invalid": 1,
        "blocked": 0,
        "wrong_market": 0,
    }

    campaign = broadcast.confirm_draft(db, draft["draft_id"], 9001)
    assert campaign["total_targets"] == 2
    conn = sqlite3.connect(db)
    targets = [row[0] for row in conn.execute(
        "SELECT telegram_chat_id FROM broadcast_lite_deliveries WHERE campaign_id=? ORDER BY telegram_chat_id",
        (campaign["campaign_id"],),
    )]
    conn.close()
    assert targets == ["100", "200"]


def test_audience_all_user_test_list_and_blocked(tmp_path: Path):
    db = make_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO broadcast_lite_blocked_users(user_id,blocked_at,reason) VALUES ('200','now','blocked')")
    conn.commit()
    conn.close()
    all_stats = broadcast.preview_audience(db, "all")
    assert all_stats == {
        "total": 2,
        "eligible": 1,
        "invalid": 1,
        "blocked": 1,
        "wrong_market": 0,
    }
    assert broadcast.preview_audience(db, "user", "100")["eligible"] == 1
    assert broadcast.preview_audience(db, "user", "not-a-chat")["invalid"] == 1
    test_stats = broadcast.preview_audience(db, "test_list", "100, 200, 300, nope")
    assert test_stats["eligible"] == 2
    assert test_stats["blocked"] == 1
    assert test_stats["invalid"] == 1


def test_market_scopes_filter_delivery_and_lock_domestic_templates(tmp_path: Path):
    db = make_db(tmp_path)
    vietnam = broadcast.preview_audience(db, "all", market_scope="vn")
    international = broadcast.preview_audience(db, "all", market_scope="intl")
    all_bot = broadcast.preview_audience(db, "all", market_scope="all")

    assert vietnam == {
        "total": 1,
        "eligible": 1,
        "invalid": 1,
        "blocked": 0,
        "wrong_market": 1,
    }
    assert international == {
        "total": 1,
        "eligible": 1,
        "invalid": 1,
        "blocked": 0,
        "wrong_market": 1,
    }
    assert all_bot["eligible"] == 2
    assert all_bot["wrong_market"] == 0

    domestic = broadcast.create_template_draft(db, 9001, "first_topup")
    with pytest.raises(ValueError, match="chỉ được gửi cho thị trường Việt Nam"):
        broadcast.set_draft_market(db, domestic["draft_id"], 9001, "intl")
    with pytest.raises(ValueError, match="chỉ được gửi cho thị trường Việt Nam"):
        broadcast.set_draft_market(db, domestic["draft_id"], 9001, "all")
    domestic = broadcast.set_draft_market(db, domestic["draft_id"], 9001, "vn")
    domestic = broadcast.set_draft_audience(db, domestic["draft_id"], 9001, "all")
    preview = broadcast.preview_draft(db, domestic["draft_id"], 9001)
    assert preview["audience"]["eligible"] == 1
    assert preview["audience"]["wrong_market"] == 1
    campaign = broadcast.confirm_draft(db, domestic["draft_id"], 9001)

    conn = sqlite3.connect(db)
    delivery = conn.execute(
        "SELECT telegram_chat_id,campaign_market_scope,user_market_snapshot,locale_snapshot,"
        "country_snapshot FROM broadcast_lite_deliveries WHERE campaign_id=?",
        (campaign["campaign_id"],),
    ).fetchone()
    conn.close()
    assert delivery == ("100", "vn", "VN", "vi", "VN")


def test_member_tier_audience_includes_no_tier_and_all_tiers(tmp_path: Path):
    db = tmp_path / "member-tiers.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE users (user_id TEXT PRIMARY KEY, username TEXT, join_date TEXT, total_paid_vnd INTEGER DEFAULT 0, is_vip INTEGER DEFAULT 0, vip_tier_override TEXT DEFAULT '')")
    conn.executemany(
        "INSERT INTO users(user_id,username,total_paid_vnd,is_vip) VALUES (?,?,?,?)",
        [("101", "zero", 0, 0), ("102", "under-silver", 99_999, 0), ("103", "silver", 100_000, 0), ("104", "gold", 1_000_000, 0), ("105", "vip", 0, 1), ("bad", "invalid", 0, 0)],
    )
    broadcast.ensure_schema(conn)
    conn.commit()
    conn.close()

    no_tier = broadcast.preview_audience(db, "tiers", '["newbie"]')
    assert no_tier["eligible"] == 2
    silver = broadcast.preview_audience(db, "tiers", '["silver"]')
    assert silver["eligible"] == 1
    all_tiers = broadcast.preview_audience(db, "tiers", '["newbie","silver","gold","platinum","diamond","vip"]')
    assert all_tiers["eligible"] == 5
    assert all_tiers["invalid"] == 1

    draft = broadcast.create_template_draft(db, 9001, "video")
    draft = broadcast.set_draft_market(db, draft["draft_id"], 9001, "all")
    draft = broadcast.set_draft_audience(db, draft["draft_id"], 9001, "tiers", '["newbie","silver"]')
    campaign = broadcast.confirm_draft(db, draft["draft_id"], 9001)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM broadcast_lite_deliveries WHERE campaign_id=?", (campaign["campaign_id"],)).fetchone()[0] == 3
    conn.close()


def test_confirm_is_idempotent_and_one_delivery_per_user(tmp_path: Path):
    db = make_db(tmp_path)
    draft = broadcast.create_template_draft(db, 9001, "video")
    draft = broadcast.set_draft_market(db, draft["draft_id"], 9001, "all")
    draft = broadcast.set_draft_audience(db, draft["draft_id"], 9001, "test_list", "100 100 200")
    first = broadcast.confirm_draft(db, draft["draft_id"], 9001)
    second = broadcast.confirm_draft(db, draft["draft_id"], 9001)
    assert first["campaign_id"] == second["campaign_id"]
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM broadcast_lite_campaigns").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM broadcast_lite_deliveries").fetchone()[0] == 2
    conn.close()
    assert broadcast.campaign_stats(db, first["campaign_id"])["waiting"] == 2


def test_outbox_success_429_retry_blocked_and_no_duplicate(tmp_path: Path):
    db = make_db(tmp_path)
    draft = broadcast.create_template_draft(db, 9001, "image")
    draft = broadcast.set_draft_market(db, draft["draft_id"], 9001, "all")
    draft = broadcast.set_draft_audience(db, draft["draft_id"], 9001, "test_list", "100 200")
    campaign = broadcast.confirm_draft(db, draft["draft_id"], 9001)

    calls = []

    class TooManyRequests(Exception):
        retry_after = 0

    def sender(delivery):
        calls.append(delivery["telegram_chat_id"])
        if delivery["telegram_chat_id"] == "100" and calls.count("100") == 1:
            raise TooManyRequests("429")
        if delivery["telegram_chat_id"] == "200":
            error = RuntimeError("Forbidden: bot was blocked")
            error.status_code = 403
            raise error
        return {"message_id": "m-100"}

    first = broadcast.run_outbox_once(db, sender, retry_delay=0)
    assert first["retried"] == 1
    assert first["blocked"] == 1
    second = broadcast.run_outbox_once(db, sender, retry_delay=0)
    assert second["success"] == 1
    third = broadcast.run_outbox_once(db, sender, retry_delay=0)
    assert third["claimed"] == 0
    assert calls.count("100") == 2
    assert calls.count("200") == 1
    stats = broadcast.campaign_stats(db, campaign["campaign_id"])
    assert stats["sent"] == 1
    assert stats["blocked"] == 1
    assert stats["waiting"] == 0


def test_async_outbox_used_by_live_worker_has_bounded_retry(tmp_path: Path):
    db = make_db(tmp_path)
    draft = broadcast.create_template_draft(db, 9001, "video")
    draft = broadcast.set_draft_market(db, draft["draft_id"], 9001, "all")
    draft = broadcast.set_draft_audience(db, draft["draft_id"], 9001, "all")
    campaign = broadcast.confirm_draft(db, draft["draft_id"], 9001)
    calls = []

    class TooManyRequests(Exception):
        retry_after = 0

    async def sender(delivery):
        calls.append(delivery["telegram_chat_id"])
        if delivery["telegram_chat_id"] == "100" and calls.count("100") == 1:
            raise TooManyRequests("429")
        return {"message_id": "fake-message"}

    first = asyncio.run(broadcast.run_outbox_once_async(db, sender, batch_size=20, max_attempts=3, retry_delay=0))
    second = asyncio.run(broadcast.run_outbox_once_async(db, sender, batch_size=20, max_attempts=3, retry_delay=0))
    third = asyncio.run(broadcast.run_outbox_once_async(db, sender, batch_size=20, max_attempts=3, retry_delay=0))

    assert first == {"claimed": 2, "success": 1, "failed": 0, "blocked": 0, "retried": 1}
    assert second == {"claimed": 1, "success": 1, "failed": 0, "blocked": 0, "retried": 0}
    assert third["claimed"] == 0
    assert calls.count("100") == 2
    assert calls.count("200") == 1
    assert broadcast.campaign_stats(db, campaign["campaign_id"])["sent"] == 2


def test_live_worker_startup_registers_broadcast_worker_once():
    source = BOT_TEXT
    lifespan_start = source.index("async def lifespan")
    lifespan_end = source.index("fastapi_app = FastAPI", lifespan_start)
    lifespan_source = source[lifespan_start:lifespan_end]
    worker_start = "tg_broadcast_lite_worker_task = asyncio.create_task(broadcast_lite_outbox_loop(tg_app.bot))"
    assert lifespan_source.count(worker_start) == 1
    assert lifespan_source.index(worker_start) < lifespan_source.index(
        "tg_subdub_recovery_task = asyncio.create_task("
    )


def test_outbox_resumes_stale_claim_and_records_heartbeat(tmp_path: Path):
    db = make_db(tmp_path)
    draft = broadcast.create_template_draft(db, 9001, "support")
    draft = broadcast.set_draft_market(db, draft["draft_id"], 9001, "all")
    draft = broadcast.set_draft_audience(db, draft["draft_id"], 9001, "user", "100")
    campaign = broadcast.confirm_draft(db, draft["draft_id"], 9001)
    stale = (datetime.now(timezone.utc) - timedelta(minutes=11)).replace(microsecond=0).isoformat()
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE broadcast_lite_deliveries SET status='sending',last_attempt_at=?,worker_heartbeat_at=? WHERE campaign_id=?",
        (stale, stale, campaign["campaign_id"]),
    )
    conn.commit()
    conn.close()

    result = broadcast.run_outbox_once(db, lambda _delivery: {"message_id": "resumed"}, worker_name="resume-test")
    assert result["success"] == 1
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT status FROM broadcast_lite_deliveries").fetchone()[0] == "success"
    heartbeat = conn.execute(
        "SELECT detail FROM broadcast_lite_worker_heartbeats WHERE worker_name='resume-test'"
    ).fetchone()
    conn.close()
    assert heartbeat and "success=1" in heartbeat[0]


def test_callback_flow_compose_audience_confirm_creates_outbox_without_sending(tmp_path: Path):
    db = make_db(tmp_path)
    source = BOT_TEXT
    ui = _load_broadcast_ui()
    ui["DB_FILE"] = db
    ui["preview_broadcast_lite_audience"] = broadcast.preview_audience

    class ContextTypes:
        DEFAULT_TYPE = object

    class Query:
        def __init__(self, data):
            self.data = data
            self.answers = []
            self.text = ""
            self.reply_markup = None

        async def answer(self, text="", **kwargs):
            self.answers.append((text, kwargs))

    class Message:
        def __init__(self, text):
            self.text = text
            self.replies = []

        async def reply_text(self, text, reply_markup=None, **kwargs):
            self.replies.append((text, reply_markup, kwargs))

    class PhotoMessage(Message):
        def __init__(self, caption):
            super().__init__("")
            self.caption = caption
            self.photo = [SimpleNamespace(file_id="telegram-photo-file-id")]

    async def safe_edit(query, text, reply_markup=None, **kwargs):
        query.text = text
        query.reply_markup = reply_markup
        return True

    warning_calls = []

    class Logger:
        def warning(self, *args, **kwargs):
            warning_calls.append((args, kwargs))
            return None

    namespace = {
        **ui,
        "Update": object,
        "ContextTypes": ContextTypes,
        "DB_FILE": db,
        "is_admin_user": lambda user_id: int(user_id) == 9001,
        "safe_edit_query_message": safe_edit,
        "sanitize_log_text": lambda value: str(value),
        "logger": Logger(),
        "BroadcastLiteFrequencyCapWarning": broadcast.FrequencyCapWarning,
        "apply_broadcast_lite_template": broadcast.apply_template_to_draft,
        "broadcast_lite_campaign_stats": broadcast.campaign_stats,
        "clear_broadcast_lite_pending_drafts": broadcast.clear_pending_drafts,
        "confirm_broadcast_lite_draft": broadcast.confirm_draft,
        "create_broadcast_lite_draft": broadcast.create_empty_draft,
        "create_broadcast_lite_schedule_from_draft": broadcast.create_schedule_from_draft,
        "create_broadcast_lite_template_draft": broadcast.create_template_draft,
        "get_broadcast_lite_promo_limits": broadcast.get_promo_limits,
        "get_broadcast_lite_draft": broadcast.get_draft,
        "get_latest_broadcast_lite_draft": broadcast.get_latest_draft,
        "list_broadcast_lite_campaigns": broadcast.list_campaigns,
        "list_broadcast_lite_schedules": broadcast.list_schedules,
        "preview_broadcast_lite_draft": broadcast.preview_draft,
        "set_broadcast_lite_audience": broadcast.set_draft_audience,
        "set_broadcast_lite_ctas": broadcast.set_draft_ctas,
        "set_broadcast_lite_market": broadcast.set_draft_market,
        "set_broadcast_lite_media": broadcast.set_draft_media,
        "set_broadcast_lite_message": broadcast.set_draft_message,
        "set_broadcast_lite_promo_limits": broadcast.set_promo_limits,
        "set_broadcast_lite_schedule_active": broadcast.set_schedule_active,
        "set_broadcast_lite_schedule_config": broadcast.set_draft_schedule_config,
        "set_broadcast_lite_state": broadcast.set_draft_state,
        "toggle_broadcast_lite_cta": broadcast.toggle_draft_cta,
        "toggle_broadcast_lite_tier": broadcast.toggle_draft_tier,
    }
    start = source.index("async def _broadcast_lite_edit")
    end = source.index("async def broadcast_lite_send_delivery", start)
    exec(source[start:end], namespace)

    user = SimpleNamespace(id=9001)

    async def run_flow():
        blocked = Query("broadcast_lite|compose")
        await namespace["handle_broadcast_lite_callback"](
            SimpleNamespace(callback_query=blocked, effective_user=SimpleNamespace(id=42)), None
        )
        assert blocked.answers[-1][1] == {"show_alert": True}
        assert blocked.reply_markup is None

        top_level_screens = (
            ("broadcast_lite|back", "Thông báo khách hàng"),
            ("broadcast_lite|history", "Lịch sử gửi"),
            ("broadcast_lite|sched", "Lịch thông báo"),
            ("broadcast_lite|limits", "Giới hạn gửi"),
        )
        for callback_data, expected_text in top_level_screens:
            screen = Query(callback_data)
            await namespace["handle_broadcast_lite_callback"](
                SimpleNamespace(callback_query=screen, effective_user=user), None
            )
            assert screen.answers == [("", {})]
            assert expected_text in screen.text, warning_calls[-1] if warning_calls else None

        class ExpiredAnswerQuery(Query):
            async def answer(self, text="", **kwargs):
                raise RuntimeError("callback query expired")

        expired = ExpiredAnswerQuery("broadcast_lite|history")
        await namespace["handle_broadcast_lite_callback"](
            SimpleNamespace(callback_query=expired, effective_user=user), None
        )
        assert "Lịch sử gửi" in expired.text

        compose = Query("broadcast_lite|compose")
        await namespace["handle_broadcast_lite_callback"](
            SimpleNamespace(callback_query=compose, effective_user=user), None
        )
        draft = broadcast.get_latest_draft(db, 9001, states=("awaiting_content",))
        assert draft is not None
        assert [button.callback_data for button in compose.reply_markup.inline_keyboard[0]] == [
            f"broadcast_lite|tpls|{draft['draft_id']}",
            f"broadcast_lite|tpls|{draft['draft_id']}",
        ]
        assert compose.reply_markup.inline_keyboard[-1][0].callback_data == f"broadcast_lite|cancel|{draft['draft_id']}"

        message = Message("Thông báo kiểm thử toàn bot")
        handled = await namespace["handle_broadcast_lite_pending_text"](
            SimpleNamespace(effective_user=user, message=message), None
        )
        assert handled is True
        cta_markup = message.replies[-1][1]
        assert cta_markup.inline_keyboard[-1][0].callback_data == f"broadcast_lite|ctas_done|{draft['draft_id']}"

        back_content = Query(f"broadcast_lite|content|{draft['draft_id']}")
        await namespace["handle_broadcast_lite_callback"](
            SimpleNamespace(callback_query=back_content, effective_user=user), None
        )
        assert "Thông báo kiểm thử toàn bot" in back_content.text
        back_ctas = Query(f"broadcast_lite|ctas|{draft['draft_id']}")
        await namespace["handle_broadcast_lite_callback"](
            SimpleNamespace(callback_query=back_ctas, effective_user=user), None
        )
        assert back_ctas.reply_markup.inline_keyboard[-1][0].callback_data == f"broadcast_lite|ctas_done|{draft['draft_id']}"

        ctas_done = Query(f"broadcast_lite|ctas_done|{draft['draft_id']}")
        await namespace["handle_broadcast_lite_callback"](
            SimpleNamespace(callback_query=ctas_done, effective_user=user), None
        )
        market_markup = ctas_done.reply_markup
        assert [button.callback_data for button in market_markup.inline_keyboard[0]] == [
            f"broadcast_lite|market|{draft['draft_id']}|v",
            f"broadcast_lite|market|{draft['draft_id']}|i",
        ]
        assert [button.callback_data for button in market_markup.inline_keyboard[1]] == [
            f"broadcast_lite|market|{draft['draft_id']}|a",
            f"broadcast_lite|ctas|{draft['draft_id']}",
        ]

        select_market = Query(f"broadcast_lite|market|{draft['draft_id']}|a")
        await namespace["handle_broadcast_lite_callback"](
            SimpleNamespace(callback_query=select_market, effective_user=user), None
        )
        audience_markup = select_market.reply_markup
        assert [button.callback_data for button in audience_markup.inline_keyboard[0]] == [
            f"broadcast_lite|aud_all|{draft['draft_id']}",
            f"broadcast_lite|aud_tiers|{draft['draft_id']}",
        ]

        select_all = Query(f"broadcast_lite|aud_all|{draft['draft_id']}")
        await namespace["handle_broadcast_lite_callback"](
            SimpleNamespace(callback_query=select_all, effective_user=user), None
        )
        assert select_all.reply_markup.inline_keyboard[0][0].callback_data == f"broadcast_lite|confirm|{draft['draft_id']}"
        assert "Tổng khách dự kiến: 2" in select_all.text

        back_audience = Query(f"broadcast_lite|audience|{draft['draft_id']}")
        await namespace["handle_broadcast_lite_callback"](
            SimpleNamespace(callback_query=back_audience, effective_user=user), None
        )
        assert "Đã chọn: Toàn bộ khách đã dùng bot" in back_audience.text
        assert back_audience.reply_markup.inline_keyboard[2][0].callback_data == f"broadcast_lite|preview|{draft['draft_id']}"
        retained = broadcast.get_draft(db, draft["draft_id"], 9001)
        assert retained["market_scope"] == "all"
        assert retained["audience_kind"] == "all"

        first_confirm = Query(f"broadcast_lite|confirm|{draft['draft_id']}")
        duplicate_confirm = Query(f"broadcast_lite|confirm|{draft['draft_id']}")
        await namespace["handle_broadcast_lite_callback"](
            SimpleNamespace(callback_query=first_confirm, effective_user=user), None
        )
        await namespace["handle_broadcast_lite_callback"](
            SimpleNamespace(callback_query=duplicate_confirm, effective_user=user), None
        )
        assert "Đã xác nhận" in first_confirm.text

        template = Query("broadcast_lite|template|video")
        await namespace["handle_broadcast_lite_callback"](
            SimpleNamespace(callback_query=template, effective_user=user), None
        )
        assert [button.callback_data.split("|")[1] for button in template.reply_markup.inline_keyboard[0]] == ["use", "edit"]

        skip_photo = Query("broadcast_lite|skip")
        await namespace["handle_broadcast_lite_callback"](
            SimpleNamespace(callback_query=skip_photo, effective_user=user), None
        )
        photo_message = PhotoMessage("Nội dung kèm ảnh")
        photo_handled = await namespace["handle_broadcast_lite_pending_photo"](
            SimpleNamespace(effective_user=user, message=photo_message), None
        )
        assert photo_handled is True
        assert photo_message.replies[-1][1].inline_keyboard[-1][0].callback_data.startswith("broadcast_lite|ctas_done|")

    asyncio.run(run_flow())

    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM broadcast_lite_campaigns").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM broadcast_lite_deliveries").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM broadcast_lite_deliveries WHERE status='pending'").fetchone()[0] == 2
    conn.close()


def test_scope_and_menu_routing_static_gates():
    module_source = Path(broadcast.__file__).read_text(encoding="utf-8").lower()
    assert "import telegram" not in module_source
    assert "from telegram" not in module_source
    assert "update payos_orders" not in module_source
    assert "insert into wallet" not in module_source
    assert "update users set xu" not in module_source
    assert "from providers" not in module_source
    assert "import providers" not in module_source

    source = BOT_TEXT
    contains = source.__contains__
    assert source.count('callback_data="menu|admin_broadcast_lite"') == 1
    assert contains('InlineKeyboardButton("📣 Thông báo khách hàng", callback_data="menu|admin_broadcast_lite"),')
    assert contains('InlineKeyboardButton("🏠 Menu chính", callback_data="menu|main"),')
    assert contains('InlineKeyboardButton("⏭️ Bỏ qua nhập tay", callback_data=f"broadcast_lite|tpls|{draft_id}")')
    assert contains('InlineKeyboardButton(("✅ " if all_selected else "") + "🌐 Toàn bộ bot", callback_data=f"broadcast_lite|aud_all|{draft_id}")')
    assert contains('InlineKeyboardButton("🏷 Hạng thành viên", callback_data=f"broadcast_lite|aud_tiers|{draft_id}")')
    assert not contains('callback_data=f"broadcast_lite|aud_mode|{draft_id}|test_list"')
    assert contains('set_broadcast_lite_audience(DB_FILE, parts[2], uid, "all")')
    assert contains("Tổng khách dự kiến:")
    assert contains('"Tất cả hạng", callback_data=f"broadcast_lite|tier|{draft_id}|all"')
    assert contains('if action == "compose":')
    assert contains('state="awaiting_content"')
    assert contains('if action == "tpls" and len(parts) >= 3:')
    assert contains('if action == "ctas_done" and len(parts) >= 3:')
    assert contains('return await _broadcast_lite_edit(query, broadcast_lite_audience_text(draft), broadcast_lite_audience_keyboard(draft))')
    assert contains('if action in {"au", "aud_mode"} and len(parts) >= 4:')
    assert contains('InlineKeyboardButton("✅ Xác nhận gửi", callback_data=f"broadcast_lite|confirm|{draft_id}")')
    assert contains("broadcast_lite_preview_keyboard(prepared)")
    assert contains("clear_broadcast_lite_pending(query.from_user.id)")
    assert contains('"⚠️ " + str(error)[:300] + "\\n\\n" + broadcast_lite_draft_text(draft)')
    assert contains('CallbackQueryHandler(handle_broadcast_lite_callback, pattern=r"^broadcast_lite\\|")')
    assert contains("broadcast_lite_send_delivery(delivery, bot_client)")
    assert contains('if action == "main_topup":\n        return menu_text_main_topup(), main_topup_keyboard()')
    assert contains('if action == "main_video":\n        return menu_text_main_video(), main_video_keyboard()')
    assert contains('if action == "main_image":\n        return menu_text_main_image(), main_image_keyboard()')
    assert contains('if action == "support":\n        return menu_text_support(), menu_nav_keyboard("support", is_admin)')
    handler = source.split("async def handle_broadcast_lite_callback", 1)[1].split("async def handle_broadcast_lite_pending_text", 1)[0]
    assert "if not query or not update.effective_user or not is_admin_user(update.effective_user.id):" in handler
    compose_branch = handler.split('if action == "compose":', 1)[1].split('if action in {"templates", "skip", "compose_text", "compose_photo"}:', 1)[0]
    template_branch = handler.split('if action == "tpl"', 1)[1].split('if action == "tpl_review"', 1)[0]
    assert "create_broadcast_lite_draft" in compose_branch
    assert 'state="awaiting_content"' in compose_branch
    assert "broadcast_lite_compose_keyboard" in compose_branch
    assert "apply_broadcast_lite_template" in template_branch
    assert "broadcast_lite_template_review_keyboard" in template_branch
    pending_text = source.split("async def handle_broadcast_lite_pending_text", 1)[1].split("async def handle_broadcast_lite_pending_photo", 1)[0]
    assert '"awaiting_content"' in pending_text
    assert "broadcast_lite_cta_keyboard(draft)" in pending_text
    assert "broadcast_lite_send_delivery" not in handler
    assert "tg_app.bot" not in handler
    assert source.index("if await handle_broadcast_lite_pending_text(update, context):") < source.index("if await handle_support_pending_input(update, context):")
    assert source.index("if await handle_broadcast_lite_pending_text(update, context):") < source.index("if await handle_manual_topup_pending_text(update, context):")
    assert source.index("if await handle_broadcast_lite_pending_photo(update, context):") < source.index("if await handle_image_menu_pending_photo(update, context):")
    assert source.index("if await handle_video_editor_pending_upload(update, context):") < source.index("if await handle_broadcast_lite_pending_photo(update, context):")
    assert "asyncio.create_task(enqueue_broadcast_first_start_safe(uid))" in source
    paid = source.split("def process_payos_paid_order", 1)[1].split("# ─── ADMIN ALERT", 1)[0]
    assert paid.index("conn.commit()") < paid.index("enqueue_broadcast_after_first_topup_safe(target_id)") < paid.index('return True, "success", info')


def _load_broadcast_ui():
    source = BOT_TEXT
    start = source.index("def broadcast_lite_admin_menu_text")
    end = source.index("async def cmd_broadcast_lite", start)

    class Button:
        def __init__(self, text, callback_data):
            self.text = text
            self.callback_data = callback_data

    class Markup:
        def __init__(self, rows):
            self.inline_keyboard = rows

    namespace = {
        "re": __import__("re"),
        "InlineKeyboardButton": Button,
        "InlineKeyboardMarkup": Markup,
        "DB_FILE": ":memory:",
        "BROADCAST_LITE_DEFAULT_TIMEZONE": broadcast.DEFAULT_TIMEZONE,
        "BROADCAST_LITE_CORE_CTA_KEYS": broadcast.CORE_CTA_KEYS,
        "BROADCAST_LITE_SPECIAL_FEATURE_CTA_KEYS": broadcast.SPECIAL_FEATURE_CTA_KEYS,
        "BROADCAST_LITE_TEMPLATES": broadcast.TEMPLATES,
        "BROADCAST_LITE_CTA_REGISTRY": broadcast.CTA_REGISTRY,
        "BROADCAST_LITE_TIER_ORDER": broadcast.MEMBER_TIER_ORDER,
        "BROADCAST_LITE_TIER_REGISTRY": broadcast.MEMBER_TIER_REGISTRY,
        "BROADCAST_LITE_MARKET_SCOPE_VN": broadcast.MARKET_SCOPE_VN,
        "BROADCAST_LITE_MARKET_SCOPE_INTL": broadcast.MARKET_SCOPE_INTL,
        "BROADCAST_LITE_MARKET_SCOPE_ALL": broadcast.MARKET_SCOPE_ALL,
        "BROADCAST_LITE_MARKET_SCOPE_LABELS": broadcast.MARKET_SCOPE_LABELS,
        "get_broadcast_lite_promo_limits": lambda _db: {"max_24h": 1, "max_7d": 3, "weekly_then_daily": False},
        "preview_broadcast_lite_audience": lambda *_args, **_kwargs: {"total": 0, "eligible": 0, "invalid": 0, "blocked": 0},
    }
    exec(source[start:end], namespace)
    return namespace


def test_broadcast_menu_rows_are_exactly_two_buttons():
    namespace = _load_broadcast_ui()

    draft_id = "f" * 32
    empty = {"draft_id": draft_id, "market_scope": "", "audience_kind": "", "ctas": [], "tiers": []}
    ready = {"draft_id": draft_id, "market_scope": "all", "audience_kind": "all", "ctas": ["topup"], "tiers": []}
    keyboards = [
        namespace["broadcast_lite_admin_menu_keyboard"](),
        namespace["broadcast_lite_navigation_keyboard"]("⬅️ Quay lại", "broadcast_lite|back"),
        namespace["broadcast_lite_compose_keyboard"](draft_id),
        namespace["broadcast_lite_template_keyboard"](),
        namespace["broadcast_lite_template_keyboard"](draft_id),
        namespace["broadcast_lite_template_review_keyboard"](ready),
        namespace["broadcast_lite_input_keyboard"](draft_id),
        namespace["broadcast_lite_input_keyboard"](draft_id, back_to="content"),
        namespace["broadcast_lite_draft_keyboard"](empty),
        namespace["broadcast_lite_draft_keyboard"](ready),
        namespace["broadcast_lite_preview_keyboard"](ready),
        namespace["broadcast_lite_cta_keyboard"](empty),
        namespace["broadcast_lite_cta_keyboard"](ready),
        namespace["broadcast_lite_feature_cta_keyboard"](ready),
        namespace["broadcast_lite_market_keyboard"](empty),
        namespace["broadcast_lite_market_keyboard"](ready),
        namespace["broadcast_lite_audience_keyboard"](ready),
        namespace["broadcast_lite_tier_keyboard"](empty),
        namespace["broadcast_lite_campaign_keyboard"](1),
        namespace["broadcast_lite_history_keyboard"](),
        namespace["broadcast_lite_schedule_menu_keyboard"](),
        namespace["broadcast_lite_schedule_time_keyboard"]({**ready, "schedule_cadence": "daily"}),
        namespace["broadcast_lite_schedule_preview_keyboard"](ready),
        namespace["broadcast_lite_schedule_list_keyboard"]([]),
        namespace["broadcast_lite_limits_keyboard"](),
    ]
    assert all(len(row) == 2 for keyboard in keyboards for row in keyboard.inline_keyboard)


def test_broadcast_button_routes_are_ordered_and_within_telegram_limit():
    namespace = _load_broadcast_ui()
    draft_id = "f" * 32
    empty = {"draft_id": draft_id, "market_scope": "", "audience_kind": "", "ctas": [], "tiers": []}
    ready = {"draft_id": draft_id, "market_scope": "all", "audience_kind": "all", "ctas": ["topup"], "tiers": []}
    root = namespace["broadcast_lite_admin_menu_keyboard"]()
    compose = namespace["broadcast_lite_compose_keyboard"](draft_id)
    templates = namespace["broadcast_lite_template_keyboard"](draft_id)
    custom_input = namespace["broadcast_lite_input_keyboard"](draft_id)
    content = namespace["broadcast_lite_draft_keyboard"](empty)
    audience = namespace["broadcast_lite_audience_keyboard"](ready)
    review = namespace["broadcast_lite_preview_keyboard"](ready)
    ctas_before_audience = namespace["broadcast_lite_cta_keyboard"](empty)
    ctas_after_audience = namespace["broadcast_lite_cta_keyboard"](ready)
    market = namespace["broadcast_lite_market_keyboard"](empty)
    tiers = namespace["broadcast_lite_tier_keyboard"](empty)
    history = namespace["broadcast_lite_history_keyboard"]()
    template_review = namespace["broadcast_lite_template_review_keyboard"](ready)
    features = namespace["broadcast_lite_feature_cta_keyboard"](ready)
    force = namespace["broadcast_lite_force_confirm_keyboard"](ready)
    schedule_menu = namespace["broadcast_lite_schedule_menu_keyboard"]()
    limits_from_root = namespace["broadcast_lite_limits_keyboard"]()
    limits_from_schedule = namespace["broadcast_lite_limits_keyboard"]("sched")
    schedule_list = namespace["broadcast_lite_schedule_list_keyboard"]([
        {"schedule_id": 1, "is_active": 1},
        {"schedule_id": 2, "is_active": 0},
    ])

    assert [[button.callback_data for button in row] for row in root.inline_keyboard] == [
        ["broadcast_lite|compose", "broadcast_lite|history"],
        ["broadcast_lite|sched", "broadcast_lite|limits"],
        ["menu|admin", "menu|main"],
    ]
    assert [button.callback_data for button in compose.inline_keyboard[0]] == [f"broadcast_lite|tpls|{draft_id}", f"broadcast_lite|tpls|{draft_id}"]
    assert [button.callback_data for button in templates.inline_keyboard[-1]] == [f"broadcast_lite|compose_back|{draft_id}", "menu|main"]
    assert [button.callback_data for button in custom_input.inline_keyboard[0]] == [f"broadcast_lite|cancel|{draft_id}", "menu|main"]
    assert [button.callback_data for button in content.inline_keyboard[0]] == [f"broadcast_lite|edit|{draft_id}", f"broadcast_lite|tpls|{draft_id}"]
    assert [[button.callback_data for button in row] for row in market.inline_keyboard] == [
        [f"broadcast_lite|market|{draft_id}|v", f"broadcast_lite|market|{draft_id}|i"],
        [f"broadcast_lite|market|{draft_id}|a", f"broadcast_lite|ctas|{draft_id}"],
        [f"broadcast_lite|cancel|{draft_id}", "menu|main"],
    ]
    assert [[button.callback_data for button in row] for row in audience.inline_keyboard] == [
        [f"broadcast_lite|aud_all|{draft_id}", f"broadcast_lite|aud_tiers|{draft_id}"],
        [f"broadcast_lite|au|{draft_id}|u", f"broadcast_lite|au|{draft_id}|t"],
        [f"broadcast_lite|preview|{draft_id}", f"broadcast_lite|market_screen|{draft_id}"],
        [f"broadcast_lite|market_screen|{draft_id}", f"broadcast_lite|cancel|{draft_id}"],
    ]
    assert [button.callback_data for button in review.inline_keyboard[0]] == [f"broadcast_lite|confirm|{draft_id}", f"broadcast_lite|edit|{draft_id}"]
    assert [button.callback_data for button in ctas_before_audience.inline_keyboard[-1]] == [f"broadcast_lite|ctas_done|{draft_id}", f"broadcast_lite|content|{draft_id}"]
    assert [button.callback_data for button in ctas_after_audience.inline_keyboard[-1]] == [f"broadcast_lite|ctas_done|{draft_id}", f"broadcast_lite|content|{draft_id}"]
    assert [button.callback_data for button in tiers.inline_keyboard[-1]] == [f"broadcast_lite|audience|{draft_id}", "menu|main"]
    assert [button.callback_data for button in history.inline_keyboard[0]] == ["broadcast_lite|back", "menu|main"]
    assert [button.callback_data for button in schedule_menu.inline_keyboard[2]] == ["broadcast_lite|sclist", "broadcast_lite|limits|sched"]
    assert [[button.callback_data for button in row] for row in limits_from_root.inline_keyboard] == [
        ["broadcast_lite|limtoggle|root", "broadcast_lite|limreset|root"],
        ["broadcast_lite|back", "menu|main"],
    ]
    assert [[button.callback_data for button in row] for row in limits_from_schedule.inline_keyboard] == [
        ["broadcast_lite|limtoggle|sched", "broadcast_lite|limreset|sched"],
        ["broadcast_lite|sched", "menu|main"],
    ]
    normalized_root_limits = ui_navigation.canonicalize_bottom_navigation(
        limits_from_root.inline_keyboard,
        button_factory=namespace["InlineKeyboardButton"],
    )
    assert [[button.callback_data for button in row] for row in normalized_root_limits] == [
        ["broadcast_lite|limtoggle|root", "broadcast_lite|limreset|root"],
        ["broadcast_lite|back", "menu|main"],
    ]

    keyboards = [
        root, compose, templates, template_review, custom_input, content, market, audience, review,
        ctas_before_audience, ctas_after_audience, features, tiers, force, history, schedule_menu, schedule_list,
        limits_from_root, limits_from_schedule,
    ]
    callback_data = [button.callback_data for keyboard in keyboards for row in keyboard.inline_keyboard for button in row]
    assert callback_data
    assert max(len(value.encode("utf-8")) for value in callback_data) <= 64
    assert not any("|aud_mode|" in value for value in callback_data)
    emitted_actions = {value.split("|")[1] for value in callback_data if value.startswith("broadcast_lite|")}
    handler_source = BOT_TEXT.split("async def handle_broadcast_lite_callback", 1)[1].split("async def handle_broadcast_lite_pending_text", 1)[0]
    assert all(f'"{action}"' in handler_source for action in emitted_actions)


@pytest.mark.parametrize("route", ["menu|main_topup", "menu|main_video", "menu|main_image", "menu|support"])
def test_cta_route_is_menu_only(route):
    assert route in {item["callback_data"] for item in broadcast.CTA_REGISTRY.values()}


def make_payment_db(tmp_path: Path) -> Path:
    db = tmp_path / "broadcast-auto.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE users (user_id TEXT PRIMARY KEY, username TEXT, join_date TEXT, "
        "has_deposited INTEGER NOT NULL DEFAULT 0, user_market TEXT DEFAULT '', "
        "country_code TEXT DEFAULT '', account_region TEXT DEFAULT '', "
        "international_account INTEGER DEFAULT 0, user_language TEXT DEFAULT '', "
        "initial_user_language TEXT DEFAULT '')"
    )
    conn.executemany(
        "INSERT INTO users(user_id,username,join_date,has_deposited,user_market,country_code,"
        "account_region,international_account,user_language,initial_user_language) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("100", "new", "today", 0, "VN", "VN", "VIETNAM", 0, "vi", "vi"),
            ("200", "paid", "today", 1, "VN", "VN", "VIETNAM", 0, "vi", "vi"),
            ("300", "pending", "today", 0, "VN", "VN", "VIETNAM", 0, "vi", "vi"),
            ("400", "fast", "today", 0, "VN", "VN", "VIETNAM", 0, "vi", "vi"),
            ("500", "international", "today", 0, "INTL", "US", "INTERNATIONAL", 1, "en", "en"),
            ("600", "non-vietnamese", "today", 0, "VN", "VN", "VIETNAM", 0, "en", "en"),
        ],
    )
    conn.execute(
        "CREATE TABLE payos_orders (order_code TEXT PRIMARY KEY,user_id TEXT,status TEXT,order_type TEXT)"
    )
    conn.execute(
        "CREATE TABLE payos_processed_events ("
        "order_code TEXT, transaction_id TEXT, credited INTEGER DEFAULT 0)"
    )
    conn.execute("INSERT INTO payos_orders VALUES ('paid-200','200','SETTLED','topup')")
    conn.execute("INSERT INTO payos_processed_events VALUES ('paid-200','tx-paid-200',1)")
    conn.executemany(
        "INSERT INTO payos_orders VALUES (?,?,?,?)",
        [
            ("pending-300", "300", "PENDING", "topup"),
            ("failed-300", "300", "FAILED", "topup"),
            ("refund-300", "300", "REFUNDED", "topup"),
        ],
    )
    broadcast.ensure_schema(conn)
    conn.commit()
    conn.close()
    return db


def test_automatic_first_start_once_and_real_send_is_injected(tmp_path: Path):
    db = make_payment_db(tmp_path)
    first = broadcast.enqueue_first_start_notice(db, "100")
    duplicate = broadcast.enqueue_first_start_notice(db, "100")
    paid_user = broadcast.enqueue_first_start_notice(db, "200")
    international = broadcast.enqueue_first_start_notice(db, "500")
    non_vietnamese_initial = broadcast.enqueue_first_start_notice(db, "600")

    assert first["queued"] is True
    assert duplicate["queued"] is False and duplicate["reason"] == "duplicate"
    assert paid_user["queued"] is False and paid_user["reason"] == "not_eligible"
    assert international["queued"] is False
    assert international["reason"] == "initial_language_or_market_not_vietnamese"
    assert non_vietnamese_initial["queued"] is False
    assert non_vietnamese_initial["reason"] == "initial_language_or_market_not_vietnamese"

    calls = []

    def fake_telegram(delivery):
        calls.append(delivery["telegram_chat_id"])
        return {"message_id": "fake-auto-message"}

    assert broadcast.run_outbox_once(db, fake_telegram)["success"] == 1
    assert calls == ["100"]
    conn = sqlite3.connect(db)
    notice = conn.execute(
        "SELECT status,telegram_message_id FROM broadcast_lite_auto_notices WHERE user_id='100'"
    ).fetchone()
    campaign = conn.execute(
        "SELECT source,keyboard_json FROM broadcast_lite_campaigns WHERE campaign_id=?",
        (first["campaign_id"],),
    ).fetchone()
    conn.close()
    assert notice == ("sent", "fake-auto-message")
    assert campaign == ("first_start", '["topup"]')


def test_after_first_topup_once_pending_failed_refund_do_not_count(tmp_path: Path):
    db = make_payment_db(tmp_path)
    assert broadcast.settled_topup_count(db, "300") == 0
    assert broadcast.enqueue_after_first_topup_notice(db, "300")["reason"] == "not_eligible"

    first = broadcast.enqueue_after_first_topup_notice(db, "200")
    duplicate = broadcast.enqueue_after_first_topup_notice(db, "200")
    assert first["queued"] is True
    assert duplicate["queued"] is False and duplicate["reason"] == "duplicate"

    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO payos_orders VALUES ('paid-200-2','200','PAID','topup')")
    conn.execute("INSERT INTO payos_processed_events VALUES ('paid-200-2','tx-paid-200-2',1)")
    conn.commit()
    conn.close()
    other_db = tmp_path / "already-twice.sqlite3"
    other_db.write_bytes(db.read_bytes())
    conn = sqlite3.connect(other_db)
    conn.execute("DELETE FROM broadcast_lite_auto_notices WHERE user_id='200'")
    conn.execute("DELETE FROM broadcast_lite_frequency_log WHERE user_id='200'")
    conn.commit()
    conn.close()
    assert broadcast.enqueue_after_first_topup_notice(other_db, "200")["reason"] == "not_eligible"


def test_after_first_topup_supersedes_only_pending_first_offer(tmp_path: Path):
    db = make_payment_db(tmp_path)
    first = broadcast.enqueue_first_start_notice(db, "400")
    assert first["queued"] is True
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO payos_orders VALUES ('paid-400','400','SETTLED','topup')")
    conn.execute("INSERT INTO payos_processed_events VALUES ('paid-400','tx-paid-400',1)")
    conn.execute("UPDATE users SET has_deposited=1 WHERE user_id='400'")
    conn.commit()
    conn.close()

    second = broadcast.enqueue_after_first_topup_notice(db, "400")
    assert second["queued"] is True
    assert second["next_retry_at"] == 0
    conn = sqlite3.connect(db)
    statuses = conn.execute(
        "SELECT auto_notice_type,status FROM broadcast_lite_auto_notices WHERE user_id='400' ORDER BY auto_notice_id"
    ).fetchall()
    deliveries = conn.execute(
        "SELECT trigger_type,status FROM broadcast_lite_deliveries WHERE user_id='400' ORDER BY delivery_id"
    ).fetchall()
    conn.close()
    assert statuses == [("first_topup_30", "superseded"), ("second_topup_20", "queued")]
    assert deliveries == [("first_topup_30", "suppressed"), ("second_topup_20", "pending")]


@pytest.mark.parametrize(
    ("cadence", "kwargs"),
    [
        ("monthly", {"day_of_month": 1, "send_time": "09:00"}),
        ("weekly", {"day_of_week": 3, "send_time": "09:00"}),
        ("daily", {"send_time": "09:00"}),
        ("one_time", {"starts_at": "2026-07-01 09:00", "send_time": "09:00"}),
    ],
)
def test_schedule_once_per_period_timezone_and_restart_recovery(tmp_path: Path, cadence: str, kwargs: dict):
    case_dir = tmp_path / cadence
    case_dir.mkdir()
    db = make_db(case_dir)
    base = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
    schedule = broadcast.create_schedule(
        db,
        name=f"{cadence} notice",
        message_text=f"Nội dung {cadence}",
        ctas=["video"],
        audience_kind="user",
        audience_filter="100",
        cadence=cadence,
        created_by="9001",
        now=base,
        **kwargs,
    )
    assert schedule["timezone"] == "Asia/Ho_Chi_Minh"
    due = datetime.fromisoformat(schedule["next_run_at"])
    assert due == datetime(2026, 7, 1, 2, 0, tzinfo=timezone.utc)
    first = broadcast.run_due_schedules(db, now=due)
    second = broadcast.run_due_schedules(db, now=due + timedelta(seconds=1))
    assert first["queued"] == 1
    assert second["queued"] == 0
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM broadcast_lite_campaigns").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM broadcast_lite_deliveries").fetchone()[0] == 1
    active = conn.execute("SELECT is_active FROM broadcast_lite_schedules").fetchone()[0]
    conn.close()
    assert active == (0 if cadence == "one_time" else 1)


def test_vietnam_scheduled_notice_requires_initial_vietnamese(tmp_path: Path):
    db = make_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO users(user_id,username,join_date,user_market,country_code,account_region,"
        "international_account,user_language,initial_user_language) VALUES (?,?,?,?,?,?,?,?,?)",
        ("300", "vn-en", "today", "VN", "VN", "VIETNAM", 0, "en", "en"),
    )
    conn.commit()
    conn.close()
    base = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
    schedule = broadcast.create_schedule(
        db,
        name="Thông báo tuần nội địa",
        message_text="Nội dung tuần",
        ctas=["topup"],
        audience_kind="all",
        market_scope="vn",
        cadence="one_time",
        starts_at="2026-07-01 09:00",
        created_by="9001",
        now=base,
    )
    due = datetime.fromisoformat(schedule["next_run_at"])
    result = broadcast.run_due_schedules(db, now=due)
    assert result["queued"] == 1
    conn = sqlite3.connect(db)
    recipients = conn.execute(
        "SELECT user_id FROM broadcast_lite_deliveries ORDER BY delivery_id"
    ).fetchall()
    conn.close()
    assert recipients == [("100",)]


def test_disabled_and_expired_schedule_never_enqueue(tmp_path: Path):
    db = make_db(tmp_path)
    base = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
    disabled = broadcast.create_schedule(
        db,
        name="disabled",
        message_text="Không được gửi",
        audience_kind="all",
        cadence="daily",
        created_by="9001",
        send_time="09:00",
        now=base,
    )
    broadcast.set_schedule_active(db, disabled["schedule_id"], False, now=base)
    expired = broadcast.create_schedule(
        db,
        name="expired",
        message_text="Đã hết hạn",
        audience_kind="all",
        cadence="daily",
        created_by="9001",
        send_time="09:00",
        expires_at="2026-07-01 08:00",
        now=base,
    )
    assert expired["is_active"] == 0
    result = broadcast.run_due_schedules(db, now=base + timedelta(days=2))
    assert result["queued"] == 0


def test_manual_frequency_warning_and_explicit_override(tmp_path: Path):
    db = make_db(tmp_path)
    first = broadcast.create_empty_draft(db, 9001)
    first = broadcast.set_draft_message(db, first["draft_id"], 9001, "Tin thứ nhất")
    first = broadcast.set_draft_market(db, first["draft_id"], 9001, "all")
    first = broadcast.set_draft_audience(db, first["draft_id"], 9001, "user", "100")
    broadcast.confirm_draft(db, first["draft_id"], 9001)

    second = broadcast.create_empty_draft(db, 9001)
    second = broadcast.set_draft_message(db, second["draft_id"], 9001, "Tin thứ hai")
    second = broadcast.set_draft_market(db, second["draft_id"], 9001, "all")
    second = broadcast.set_draft_audience(db, second["draft_id"], 9001, "user", "100")
    with pytest.raises(broadcast.FrequencyCapWarning):
        broadcast.confirm_draft(db, second["draft_id"], 9001)
    campaign = broadcast.confirm_draft(db, second["draft_id"], 9001, override_frequency_cap=True)
    assert campaign["frequency_override"] == 1
    assert broadcast.confirm_draft(db, second["draft_id"], 9001)["campaign_id"] == campaign["campaign_id"]


def test_frequency_cap_duplicate_monthly_weekly_and_weekly_daily_policy(tmp_path: Path):
    db = make_db(tmp_path)
    now = datetime(2026, 7, 1, 2, 0, tzinfo=timezone.utc)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    content_hash = broadcast.notification_content_hash("Trùng nội dung")
    cta_hash = broadcast.notification_cta_hash(["topup"])
    conn.execute(
        "INSERT INTO broadcast_lite_frequency_log "
        "(user_id,source,priority,content_hash,cta_hash,promotion_id,idempotency_key,status,reserved_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,'sent',?,?)",
        ("100", "monthly_schedule", 60, content_hash, cta_hash, "monthly:1", "freq-monthly", now.isoformat(), now.isoformat()),
    )
    duplicate = broadcast._frequency_decision_conn(
        conn,
        "100",
        source="weekly_schedule",
        content_hash=content_hash,
        cta_hash=cta_hash,
        promotion_id="weekly:1",
        now=now,
    )
    conn.execute("DELETE FROM broadcast_lite_frequency_log")
    conn.execute(
        "INSERT INTO broadcast_lite_frequency_log "
        "(user_id,source,priority,content_hash,cta_hash,promotion_id,idempotency_key,status,reserved_at,updated_at) "
        "VALUES ('100','weekly_schedule',50,'weekly-content','weekly-cta','weekly:1','freq-weekly','sent',?,?)",
        (now.isoformat(), now.isoformat()),
    )
    default_daily = broadcast._frequency_decision_conn(
        conn,
        "100",
        source="daily_schedule",
        content_hash="different-content",
        cta_hash="different-cta",
        promotion_id="daily:1",
        now=now,
    )
    conn.commit()
    conn.close()
    assert duplicate["reason"] == "duplicate_7d" and duplicate["retry_at"] is None
    assert default_daily["reason"] == "daily_after_weekly"

    broadcast.set_promo_limits(db, max_24h=1, max_7d=3, weekly_then_daily=True, updated_by=9001)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    six_hour_rule = broadcast._frequency_decision_conn(
        conn,
        "100",
        source="daily_schedule",
        content_hash="different-content",
        cta_hash="different-cta",
        promotion_id="daily:1",
        now=now + timedelta(hours=1),
    )
    allowed_after_six = broadcast._frequency_decision_conn(
        conn,
        "100",
        source="daily_schedule",
        content_hash="different-content",
        cta_hash="different-cta",
        promotion_id="daily:1",
        now=now + timedelta(hours=6),
    )
    conn.close()
    assert six_hour_rule["reason"] == "weekly_then_daily_6h"
    assert six_hour_rule["retry_at"] == now + timedelta(hours=6)
    assert allowed_after_six["allowed"] is True


def test_frequency_cap_three_in_seven_days(tmp_path: Path):
    db = make_db(tmp_path)
    now = datetime(2026, 7, 8, 2, 0, tzinfo=timezone.utc)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    for index, days_ago in enumerate((6, 4, 2), start=1):
        stamp = (now - timedelta(days=days_ago)).isoformat()
        conn.execute(
            "INSERT INTO broadcast_lite_frequency_log "
            "(user_id,source,priority,content_hash,cta_hash,promotion_id,idempotency_key,status,reserved_at,updated_at) "
            "VALUES ('100','weekly_schedule',50,?,?,?,?,'sent',?,?)",
            (f"content-{index}", f"cta-{index}", f"promo-{index}", f"freq-{index}", stamp, stamp),
        )
    conn.commit()
    decision = broadcast._frequency_decision_conn(
        conn,
        "100",
        source="monthly_schedule",
        content_hash="new-content",
        cta_hash="new-cta",
        promotion_id="new-promo",
        now=now,
    )
    conn.close()
    assert decision["allowed"] is False
    assert decision["reason"] == "cap_7d"
