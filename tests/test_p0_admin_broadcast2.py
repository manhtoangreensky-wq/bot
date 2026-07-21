from pathlib import Path
import sqlite3

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


def test_scope_and_menu_routing_static_gates():
    module_source = Path(broadcast.__file__).read_text(encoding="utf-8").lower()
    for forbidden in ("payos", "wallet", "credit", "promotion", "payment"):
        assert forbidden not in module_source
    assert "import telegram" not in module_source
    assert "from telegram" not in module_source

    source = BOT_SOURCE.read_text(encoding="utf-8")
    assert source.count('callback_data="menu|admin_broadcast_lite"') == 1
    assert 'rows.append([InlineKeyboardButton("📣 Thông báo khách hàng", callback_data="menu|admin_broadcast_lite")])' in source
    assert 'InlineKeyboardButton("🏷 Chọn hạng thành viên", callback_data="broadcast_lite|audience")' in source
    assert '"Tất cả hạng", callback_data=f"broadcast_lite|tier|{draft_id}|all"' in source
    assert 'CallbackQueryHandler(handle_broadcast_lite_callback, pattern=r"^broadcast_lite\\|")' in source
    handler = source.split("async def handle_broadcast_lite_callback", 1)[1].split("async def handle_broadcast_lite_pending_text", 1)[0]
    assert "broadcast_lite_send_delivery" not in handler
    assert "tg_app.bot" not in handler


@pytest.mark.parametrize("route", ["menu|main_topup", "menu|main_video", "menu|main_image", "menu|support"])
def test_cta_route_is_menu_only(route):
    assert route in {item["callback_data"] for item in broadcast.CTA_REGISTRY.values()}
