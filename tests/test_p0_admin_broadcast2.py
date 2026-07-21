import asyncio
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

import admin_broadcast as broadcast


BOT_SOURCE = Path(__file__).resolve().parents[1] / "bot.py"


def make_db(tmp_path: Path) -> Path:
    db = tmp_path / "broadcast-lite.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE users (user_id TEXT PRIMARY KEY, username TEXT, join_date TEXT)")
    conn.executemany("INSERT INTO users(user_id,username,join_date) VALUES (?,?,?)", [("100", "one", "today"), ("200", "two", "today"), ("bad-id", "bad", "today")])
    broadcast.ensure_schema(conn)
    conn.commit()
    conn.close()
    return db


def test_admin_guard_templates_and_canonical_routes():
    assert not broadcast.is_authorized_admin("42", ["7", "8"])
    assert broadcast.is_authorized_admin("42", [42])
    assert broadcast.TEMPLATES["first_topup"]["ctas"] == ["topup"]
    assert "30% Xu" in broadcast.TEMPLATES["first_topup"]["message"]
    assert "20% Xu" in broadcast.TEMPLATES["second_topup"]["message"]
    assert broadcast.CTA_REGISTRY["topup"]["callback_data"] == "menu|main_topup"
    assert broadcast.CTA_REGISTRY["video"]["callback_data"] == "menu|main_video"
    assert broadcast.CTA_REGISTRY["image"]["callback_data"] == "menu|main_image"
    assert broadcast.CTA_REGISTRY["support"]["callback_data"] == "menu|support"
    assert all(len(row) <= 2 for row in broadcast._campaign_keyboard(["topup", "video", "image", "support"]))


def test_compose_custom_text_photo_and_preview(tmp_path: Path):
    db = make_db(tmp_path)
    draft = broadcast.create_empty_draft(db, 9001)
    draft = broadcast.set_draft_message(db, draft["draft_id"], 9001, "Thông báo tùy ý <không parse>")
    draft = broadcast.set_draft_ctas(db, draft["draft_id"], 9001, ["video", "support", "image", "topup", "video"])
    draft = broadcast.set_draft_audience(db, draft["draft_id"], 9001, "all")
    preview = broadcast.preview_draft(db, draft["draft_id"], 9001)
    assert "Thông báo tùy ý" in preview["preview_text"]
    assert preview["ctas"] == ["video", "support", "image", "topup"]
    assert preview["audience"]["eligible"] == 2

    photo = broadcast.create_empty_draft(db, 9001, state="awaiting_photo")
    photo = broadcast.set_draft_media(db, photo["draft_id"], 9001, "telegram-file-id", caption="Caption ảnh")
    assert photo["media_file_id"] == "telegram-file-id"
    assert photo["message_text"] == "Caption ảnh"


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
    draft = broadcast.set_draft_audience(db, draft["draft_id"], 9001, "all")

    preview = broadcast.preview_draft(db, draft["draft_id"], 9001)
    assert preview["audience"] == {"total": 2, "eligible": 2, "invalid": 1, "blocked": 0}

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
    assert all_stats == {"total": 2, "eligible": 1, "invalid": 1, "blocked": 1}
    assert broadcast.preview_audience(db, "user", "100")["eligible"] == 1
    assert broadcast.preview_audience(db, "user", "not-a-chat")["invalid"] == 1
    test_stats = broadcast.preview_audience(db, "test_list", "100, 200, 300, nope")
    assert test_stats["eligible"] == 2
    assert test_stats["blocked"] == 1
    assert test_stats["invalid"] == 1


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
    draft = broadcast.set_draft_audience(db, draft["draft_id"], 9001, "tiers", '["newbie","silver"]')
    campaign = broadcast.confirm_draft(db, draft["draft_id"], 9001)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM broadcast_lite_deliveries WHERE campaign_id=?", (campaign["campaign_id"],)).fetchone()[0] == 3
    conn.close()


def test_confirm_is_idempotent_and_one_delivery_per_user(tmp_path: Path):
    db = make_db(tmp_path)
    draft = broadcast.create_template_draft(db, 9001, "video")
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


def test_callback_flow_compose_audience_confirm_creates_outbox_without_sending(tmp_path: Path):
    db = make_db(tmp_path)
    source = BOT_SOURCE.read_text(encoding="utf-8")
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

    async def safe_answer(query, *args, **kwargs):
        await query.answer(*args, **kwargs)
        return True

    async def safe_edit(query, text, reply_markup=None, **kwargs):
        query.text = text
        query.reply_markup = reply_markup
        return True

    class Logger:
        def warning(self, *args, **kwargs):
            return None

    namespace = {
        **ui,
        "Update": object,
        "ContextTypes": ContextTypes,
        "DB_FILE": db,
        "is_admin_user": lambda user_id: int(user_id) == 9001,
        "safe_answer_callback_query": safe_answer,
        "safe_edit_query_message": safe_edit,
        "sanitize_log_text": lambda value: str(value),
        "logger": Logger(),
        "broadcast_lite_campaign_stats": broadcast.campaign_stats,
        "clear_broadcast_lite_pending_drafts": broadcast.clear_pending_drafts,
        "confirm_broadcast_lite_draft": broadcast.confirm_draft,
        "create_broadcast_lite_draft": broadcast.create_empty_draft,
        "create_broadcast_lite_template_draft": broadcast.create_template_draft,
        "get_broadcast_lite_draft": broadcast.get_draft,
        "get_latest_broadcast_lite_draft": broadcast.get_latest_draft,
        "list_broadcast_lite_campaigns": broadcast.list_campaigns,
        "preview_broadcast_lite_draft": broadcast.preview_draft,
        "set_broadcast_lite_audience": broadcast.set_draft_audience,
        "set_broadcast_lite_media": broadcast.set_draft_media,
        "set_broadcast_lite_message": broadcast.set_draft_message,
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

        compose = Query("broadcast_lite|compose")
        await namespace["handle_broadcast_lite_callback"](
            SimpleNamespace(callback_query=compose, effective_user=user), None
        )
        assert compose.reply_markup.inline_keyboard[-1][0].callback_data == "broadcast_lite|skip"

        skip = Query("broadcast_lite|skip")
        await namespace["handle_broadcast_lite_callback"](
            SimpleNamespace(callback_query=skip, effective_user=user), None
        )
        draft = broadcast.get_latest_draft(db, 9001, states=("awaiting_message",))
        assert draft is not None
        assert skip.reply_markup.inline_keyboard[0][0].callback_data == f"broadcast_lite|cancel|{draft['draft_id']}"

        message = Message("Thông báo kiểm thử toàn bot")
        handled = await namespace["handle_broadcast_lite_pending_text"](
            SimpleNamespace(effective_user=user, message=message), None
        )
        assert handled is True
        audience_markup = message.replies[-1][1]
        assert [button.callback_data for button in audience_markup.inline_keyboard[0]] == [
            f"broadcast_lite|aud_all|{draft['draft_id']}",
            f"broadcast_lite|aud_tiers|{draft['draft_id']}",
        ]

        select_all = Query(f"broadcast_lite|aud_all|{draft['draft_id']}")
        await namespace["handle_broadcast_lite_callback"](
            SimpleNamespace(callback_query=select_all, effective_user=user), None
        )
        assert select_all.reply_markup.inline_keyboard[0][0].callback_data == f"broadcast_lite|confirm|{draft['draft_id']}"
        assert "Dự kiến gửi: 2" in select_all.text

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
        assert [button.callback_data.split("|")[1] for button in template.reply_markup.inline_keyboard[0]] == ["aud_all", "aud_tiers"]

        skip_photo = Query("broadcast_lite|skip")
        await namespace["handle_broadcast_lite_callback"](
            SimpleNamespace(callback_query=skip_photo, effective_user=user), None
        )
        photo_message = PhotoMessage("Nội dung kèm ảnh")
        photo_handled = await namespace["handle_broadcast_lite_pending_photo"](
            SimpleNamespace(effective_user=user, message=photo_message), None
        )
        assert photo_handled is True
        assert photo_message.replies[-1][1].inline_keyboard[0][0].callback_data.startswith("broadcast_lite|aud_all|")

    asyncio.run(run_flow())

    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM broadcast_lite_campaigns").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM broadcast_lite_deliveries").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM broadcast_lite_deliveries WHERE status='pending'").fetchone()[0] == 2
    conn.close()


def test_scope_and_menu_routing_static_gates():
    module_source = Path(broadcast.__file__).read_text(encoding="utf-8").lower()
    for forbidden in ("payos", "wallet", "credit", "promotion", "payment"):
        assert forbidden not in module_source
    assert "import telegram" not in module_source
    assert "from telegram" not in module_source

    source = BOT_SOURCE.read_text(encoding="utf-8")
    contains = source.__contains__
    assert source.count('callback_data="menu|admin_broadcast_lite"') == 1
    assert contains('InlineKeyboardButton("📣 Thông báo khách hàng", callback_data="menu|admin_broadcast_lite"),')
    assert contains('InlineKeyboardButton("🏠 Menu chính", callback_data="menu|main"),')
    assert contains('InlineKeyboardButton("⏭ Bỏ qua mẫu", callback_data="broadcast_lite|skip")')
    assert contains('InlineKeyboardButton(("✅ " if all_selected else "") + "🌐 Toàn bộ bot", callback_data=f"broadcast_lite|aud_all|{draft_id}")')
    assert contains('InlineKeyboardButton("🏷 Hạng thành viên", callback_data=f"broadcast_lite|aud_tiers|{draft_id}")')
    assert not contains('callback_data=f"broadcast_lite|aud_mode|{draft_id}|test_list"')
    assert contains('set_broadcast_lite_audience(DB_FILE, parts[2], uid, "all")')
    assert contains("Dự kiến gửi:")
    assert contains('"Tất cả hạng", callback_data=f"broadcast_lite|tier|{draft_id}|all"')
    assert contains('if action in {"compose", "templates"}:')
    assert contains('if action in {"skip", "compose_text", "compose_photo"}:')
    assert contains("Gửi văn bản hoặc ảnh kèm nội dung ngay tin nhắn tiếp theo.")
    assert contains('InlineKeyboardButton("✅ Xác nhận gửi", callback_data=f"broadcast_lite|confirm|{draft_id}")')
    assert contains("broadcast_lite_preview_keyboard(preview)")
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
    compose_branch = handler.split('if action in {"compose", "templates"}:', 1)[1].split('if action in {"skip", "compose_text", "compose_photo"}:', 1)[0]
    skip_branch = handler.split('if action in {"skip", "compose_text", "compose_photo"}:', 1)[1].split('if action == "cancel"', 1)[0]
    template_branch = handler.split('if action == "template"', 1)[1].split('if action in {"draft", "content"}', 1)[0]
    assert "create_broadcast_lite_draft" not in compose_branch
    assert "broadcast_lite_template_keyboard" in compose_branch
    assert "create_broadcast_lite_draft" in skip_branch
    assert "create_broadcast_lite_template_draft" in template_branch
    assert "broadcast_lite_audience_keyboard" in template_branch
    pending_text = source.split("async def handle_broadcast_lite_pending_text", 1)[1].split("async def handle_broadcast_lite_pending_photo", 1)[0]
    assert "broadcast_lite_audience_keyboard(draft)" in pending_text
    assert "broadcast_lite_send_delivery" not in handler
    assert "tg_app.bot" not in handler


def _load_broadcast_ui():
    source = BOT_SOURCE.read_text(encoding="utf-8")
    start = source.index("def broadcast_lite_admin_menu_keyboard")
    end = source.index("async def cmd_broadcast_lite", start)

    class Button:
        def __init__(self, text, callback_data):
            self.text = text
            self.callback_data = callback_data

    class Markup:
        def __init__(self, rows):
            self.inline_keyboard = rows

    namespace = {
        "InlineKeyboardButton": Button,
        "InlineKeyboardMarkup": Markup,
        "BROADCAST_LITE_TEMPLATES": broadcast.TEMPLATES,
        "BROADCAST_LITE_CTA_REGISTRY": broadcast.CTA_REGISTRY,
        "BROADCAST_LITE_TIER_ORDER": broadcast.MEMBER_TIER_ORDER,
        "BROADCAST_LITE_TIER_REGISTRY": broadcast.MEMBER_TIER_REGISTRY,
    }
    exec(source[start:end], namespace)
    return namespace


def test_broadcast_menu_rows_are_exactly_two_buttons():
    namespace = _load_broadcast_ui()

    draft_id = "f" * 32
    empty = {"draft_id": draft_id, "audience_kind": "", "ctas": [], "tiers": []}
    ready = {"draft_id": draft_id, "audience_kind": "all", "ctas": ["topup"], "tiers": []}
    keyboards = [
        namespace["broadcast_lite_admin_menu_keyboard"](),
        namespace["broadcast_lite_navigation_keyboard"]("⬅️ Quay lại", "broadcast_lite|back"),
        namespace["broadcast_lite_template_keyboard"](),
        namespace["broadcast_lite_input_keyboard"](draft_id),
        namespace["broadcast_lite_input_keyboard"](draft_id, back_to="content"),
        namespace["broadcast_lite_draft_keyboard"](empty),
        namespace["broadcast_lite_draft_keyboard"](ready),
        namespace["broadcast_lite_preview_keyboard"](ready),
        namespace["broadcast_lite_cta_keyboard"](empty),
        namespace["broadcast_lite_cta_keyboard"](ready),
        namespace["broadcast_lite_audience_keyboard"](ready),
        namespace["broadcast_lite_tier_keyboard"](empty),
        namespace["broadcast_lite_campaign_keyboard"](1),
        namespace["broadcast_lite_history_keyboard"](),
    ]
    assert all(len(row) == 2 for keyboard in keyboards for row in keyboard.inline_keyboard)


def test_broadcast_button_routes_are_ordered_and_within_telegram_limit():
    namespace = _load_broadcast_ui()
    draft_id = "f" * 32
    empty = {"draft_id": draft_id, "audience_kind": "", "ctas": [], "tiers": []}
    ready = {"draft_id": draft_id, "audience_kind": "all", "ctas": ["topup"], "tiers": []}
    root = namespace["broadcast_lite_admin_menu_keyboard"]()
    templates = namespace["broadcast_lite_template_keyboard"]()
    custom_input = namespace["broadcast_lite_input_keyboard"](draft_id)
    content = namespace["broadcast_lite_draft_keyboard"](empty)
    audience = namespace["broadcast_lite_audience_keyboard"](ready)
    review = namespace["broadcast_lite_preview_keyboard"](ready)
    ctas_before_audience = namespace["broadcast_lite_cta_keyboard"](empty)
    ctas_after_audience = namespace["broadcast_lite_cta_keyboard"](ready)
    tiers = namespace["broadcast_lite_tier_keyboard"](empty)
    history = namespace["broadcast_lite_history_keyboard"]()

    assert [[button.callback_data for button in row] for row in root.inline_keyboard] == [
        ["broadcast_lite|compose", "broadcast_lite|history"],
        ["menu|admin", "menu|main"],
    ]
    assert [button.callback_data for button in templates.inline_keyboard[-1]] == ["broadcast_lite|skip", "broadcast_lite|back"]
    assert [button.callback_data for button in custom_input.inline_keyboard[0]] == [f"broadcast_lite|cancel|{draft_id}", "menu|main"]
    assert [button.callback_data for button in content.inline_keyboard[0]] == [f"broadcast_lite|audience|{draft_id}", f"broadcast_lite|ctas|{draft_id}"]
    assert [[button.callback_data for button in row] for row in audience.inline_keyboard] == [
        [f"broadcast_lite|aud_all|{draft_id}", f"broadcast_lite|aud_tiers|{draft_id}"],
        [f"broadcast_lite|content|{draft_id}", "menu|main"],
    ]
    assert [button.callback_data for button in review.inline_keyboard[0]] == [f"broadcast_lite|confirm|{draft_id}", f"broadcast_lite|audience|{draft_id}"]
    assert [button.callback_data for button in ctas_before_audience.inline_keyboard[-1]] == [f"broadcast_lite|ctas_done|{draft_id}", f"broadcast_lite|content|{draft_id}"]
    assert [button.callback_data for button in ctas_after_audience.inline_keyboard[-1]] == [f"broadcast_lite|ctas_done|{draft_id}", f"broadcast_lite|preview|{draft_id}"]
    assert [button.callback_data for button in tiers.inline_keyboard[-1]] == [f"broadcast_lite|audience|{draft_id}", "menu|main"]
    assert [button.callback_data for button in history.inline_keyboard[0]] == ["broadcast_lite|back", "menu|main"]

    keyboards = [root, templates, custom_input, content, audience, review, ctas_before_audience, ctas_after_audience, tiers, history]
    callback_data = [button.callback_data for keyboard in keyboards for row in keyboard.inline_keyboard for button in row]
    assert callback_data
    assert max(len(value.encode("utf-8")) for value in callback_data) <= 64
    assert not any("|aud_mode|" in value for value in callback_data)


@pytest.mark.parametrize("route", ["menu|main_topup", "menu|main_video", "menu|main_image", "menu|support"])
def test_cta_route_is_menu_only(route):
    assert route in {item["callback_data"] for item in broadcast.CTA_REGISTRY.values()}
