import asyncio
import sqlite3
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _row_lengths(markup):
    return [len(row) for row in markup.inline_keyboard]


class CaptureMessage:
    def __init__(self, text="", user_id=990100):
        self.text = text
        self.chat_id = user_id
        self.message_id = 1
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        self.outputs.append({"text": str(text), **kwargs})
        return SimpleNamespace(text=text)


class CaptureQuery:
    def __init__(self, data, user_id=990100):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id, first_name="P0")
        self.message = CaptureMessage(user_id=user_id)
        self.outputs = self.message.outputs

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, **kwargs):
        self.outputs.append({"text": str(text), **kwargs})
        return SimpleNamespace(text=text)


def _callback_update(query, user_id):
    return SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user_id))


def test_image_quick_tier_prices_exact():
    assert _labels(bot.quick_image_tier_keyboard("vi"))[:7] == [
        "🟢 Tiết kiệm — 50 Xu",
        "🔵 Chuẩn — 150 Xu",
        "🛡 Chuẩn + BH — 200 Xu",
        "🟣 Phổ thông — 300 Xu",
        "🛡 Phổ thông + BH — 400 Xu",
        "🔴 Cao — 500 Xu",
        "🛡 Cao + BH — 600 Xu",
    ]


def test_image_prompt_tier_prices_exact():
    assert _labels(bot.public_image_tier_keyboard("vi"))[:7] == [
        "🟢 Tiết kiệm — 50 Xu",
        "🔵 Chuẩn — 150 Xu",
        "🛡 Chuẩn + BH — 200 Xu",
        "🟣 Phổ thông — 300 Xu",
        "🛡 Phổ thông + BH — 400 Xu",
        "🔴 Cao — 500 Xu",
        "🛡 Cao + BH — 600 Xu",
    ]


def test_no_old_image_price_200_standard_without_warranty():
    standard = bot.image_tier_payload("standard")
    standard_warranty = bot.image_tier_payload("standard_warranty")
    assert standard["cost"] == 150
    assert standard["retry_warranty_count"] == 0
    assert standard_warranty["cost"] == 200
    assert standard_warranty["retry_warranty_count"] == 1


def test_image_warranty_tiers_exact():
    assert {
        tier: (bot.image_tier_cost_xu(tier), bot.image_tier_retry_warranty_count(tier))
        for tier in bot.IMAGE_TIER_ORDER
    } == {
        "low": (50, 0),
        "standard": (150, 0),
        "standard_warranty": (200, 1),
        "common": (300, 0),
        "common_warranty": (400, 1),
        "high": (500, 0),
        "high_warranty": (600, 1),
    }


def test_public_keyboards_default_two_columns_image():
    for markup in (bot.quick_image_tier_keyboard("vi"), bot.public_image_tier_keyboard("vi")):
        assert all(length == 2 for length in _row_lengths(markup))


def test_public_keyboards_default_two_columns_video():
    markup = bot.video_finalization_menu_keyboard("vi")
    assert all(length == 2 for length in _row_lengths(markup))


def test_long_primary_buttons_allowed_full_row_only():
    assert all(length <= 2 for length in _row_lengths(bot.quick_image_prepared_prompt_keyboard("vi")))
    assert all(length <= 2 for length in _row_lengths(bot.video_finalization_scene_count_keyboard({"selected_video_tier": "basic"}, "vi")))


def test_image_logo_optional_does_not_block_ratio():
    callbacks = _callbacks(bot.quick_image_prepared_prompt_keyboard("vi"))
    assert callbacks[0] == "create_media|qi_choose_ratio"
    assert "create_media|qi_logo_choice" in callbacks


def test_image_position_without_content_returns_input_request():
    user_id = 990101
    bot.clear_image_menu_pending(user_id)
    bot.set_image_menu_pending(
        user_id,
        "image_editor_text_position",
        file_id="image-file",
        file_unique_id="uniq",
        back_to="imgtool|edit_back_choice",
        editor_source="editor_text_menu",
    )
    query = CaptureQuery("imgtool|editor_text_pos|top_left", user_id)
    asyncio.run(bot.handle_image_tools_callback(_callback_update(query, user_id), SimpleNamespace()))
    pending = bot.get_image_menu_pending(user_id)
    assert pending["pending_action"] == "image_editor_text_input"
    assert "Gửi nội dung chữ" in query.outputs[-1]["text"]
    assert "Chọn vị trí" not in query.outputs[-1]["text"]
    bot.clear_image_menu_pending(user_id)


def test_image_edit_clean_maintenance_copy():
    assert bot.PUBLIC_PRODUCT_MAINTENANCE_VI == "Hệ thống đang bảo trì/nâng cấp. TOAN AAS chưa xử lý và chưa trừ Xu. Vui lòng thử lại sau."
    for forbidden in ("kiểm thử", "provider", "task", "job", "API", "ShopAIKey"):
        assert forbidden not in bot.PUBLIC_PRODUCT_MAINTENANCE_VI


def test_video_200_valid_export_path():
    state = {
        "video_tier": "low",
        "selected_scene_count": 1,
        "pending_payload": {"video_tier": "low", "base_cost": 200},
        "current_video_price_preview": {"total_xu": 200, "raw_total_xu": 200, "addon_xu": 0},
    }
    assert bot.calculate_video_quote(state)["is_package_200_valid"] is True
    assert bot.validate_video_tier_selection(state, "low")["ok"] is True


def test_video_200_blocks_only_confirmed_paid_addon():
    state = {
        "video_tier": "low",
        "selected_scene_count": 1,
        "pending_payload": {"video_tier": "low", "base_cost": 200},
        "current_video_price_preview": {"total_xu": 350, "raw_total_xu": 350, "addon_xu": 150},
        "selected_paid_addons": [{"key": "paid_voice", "label": "Voice trả phí", "price_xu": 150}],
    }
    classified = bot.classify_video_addons_for_package(state)
    assert classified["allowed_for_200"] is False
    assert classified["paid_addons"]
    assert bot.validate_video_tier_selection(state, "low")["ok"] is False


def test_public_maintenance_copy_standard():
    assert bot.VIDEO_MULTISCENE_PUBLIC_GUARD_TEXT == bot.PUBLIC_PRODUCT_MAINTENANCE_VI
    assert set(bot.VIDEO_COMPLETED_ADDON_GUARD_TEXTS.values()) == {bot.PUBLIC_PRODUCT_MAINTENANCE_VI}


def test_public_no_testing_word_multiscene():
    assert "kiểm thử" not in bot.VIDEO_MULTISCENE_PUBLIC_GUARD_TEXT


def test_public_no_provider_task_job_api_words():
    joined = "\n".join([
        bot.PUBLIC_PRODUCT_MAINTENANCE_VI,
        bot.VIDEO_MULTISCENE_PUBLIC_GUARD_TEXT,
        *bot.VIDEO_COMPLETED_ADDON_GUARD_TEXTS.values(),
    ])
    for forbidden in ("provider", "Provider", "ShopAIKey", "task", "Task", "job", "Job", "API"):
        assert forbidden not in joined


def test_video_final_result_sent_once(monkeypatch, tmp_path):
    path = tmp_path / "dedupe.sqlite3"
    monkeypatch.setattr(bot, "DB_FILE", str(path))
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE shopaikey_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, chat_id TEXT, job_type TEXT,
            task_id TEXT UNIQUE, status TEXT, result_url TEXT,
            result_sent INTEGER DEFAULT 0, output_send_claimed_at TEXT DEFAULT '',
            output_sent_at TEXT DEFAULT '', output_sent_result_url TEXT DEFAULT '',
            output_sent_source TEXT DEFAULT '', telegram_video_file_id TEXT DEFAULT '',
            output_file_id TEXT DEFAULT '', last_telegram_send_error TEXT DEFAULT '',
            completed_notified_at TEXT DEFAULT '', duplicate_prevented_count INTEGER DEFAULT 0,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE system_settings (
            key TEXT PRIMARY KEY, value TEXT, note TEXT, updated_at TEXT, updated_by TEXT
        );
        """
    )
    cur = conn.execute(
        """INSERT INTO shopaikey_jobs
           (user_id, chat_id, job_type, task_id, status, result_url, created_at, updated_at)
           VALUES ('990102', '990102', 'video', 'task_once', 'SUCCESS', 'https://example.test/video.mp4', '2026-06-22 10:00:00', '2026-06-22 10:00:00')"""
    )
    conn.commit()
    job_id = int(cur.lastrowid)
    conn.close()

    class Client:
        def __init__(self):
            self.video_calls = 0

        async def send_video(self, **kwargs):
            self.video_calls += 1
            return SimpleNamespace(video=SimpleNamespace(file_id="file_once"))

        async def send_message(self, **kwargs):
            raise AssertionError("link fallback should not be used")

    client = Client()
    first = asyncio.run(bot.send_shopaikey_video_result_once(client, 990102, "task_once", "https://example.test/video.mp4", job_id=job_id, source="first"))
    second = asyncio.run(bot.send_shopaikey_video_result_once(client, 990102, "task_once", "https://example.test/video.mp4", job_id=job_id, source="status_poll"))
    assert first["sent"] is True
    assert second["sent"] is False
    assert client.video_calls == 1
