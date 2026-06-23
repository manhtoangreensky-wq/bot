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


def test_video_200_tier_selection_discards_stale_multiscene_state(monkeypatch):
    user_id = 990102
    bot.clear_video_finalization_state(user_id)
    bot.clear_video_addon_state(user_id)
    bot.set_video_finalization_state(user_id, {
        "step": "tier",
        "selected_video_tier": "basic",
        "selected_scene_count": 3,
        "scene_count": 3,
        "selected_video_aspect_ratio": "9:16",
        "source": "promptvideo",
        "source_payload": {
            "video_prompt": "Prompt video ready",
            "aspect_ratio": "9:16",
            "selected_scene_count": 3,
            "scene_count": 3,
        },
        "video_project": {"selected_scene_count": 3, "scene_count": 3},
        "has_video_prompt": True,
        "session_context": {"video_prompt": "Prompt video ready", "aspect_ratio": "9:16"},
    })
    monkeypatch.setattr(
        bot,
        "get_public_video_tier_ui_status",
        lambda tier, _admin=False: {"enabled": True, "label": tier, "price_xu": bot.video_tier_cost_xu(tier)},
    )
    query = CaptureQuery("vfinal|tier|low", user_id)

    asyncio.run(bot.handle_video_finalization_callback(_callback_update(query, user_id), SimpleNamespace()))

    current = bot.get_video_finalization_state(user_id)
    assert current["step"] == "scene_count"
    assert current["selected_video_tier"] == "low"
    assert current["selected_scene_count"] == 1
    assert current["source_payload"]["selected_scene_count"] == 1
    assert current["video_project"]["selected_scene_count"] == 1
    assert "1 cảnh ≈ 6s = 200 Xu" in _labels(query.outputs[-1]["reply_markup"])
    assert "đã hết lượt" not in query.outputs[-1]["text"]
    bot.clear_video_finalization_state(user_id)


def test_video_200_detail_back_to_package_list():
    user_id = 990103
    bot.clear_video_finalization_state(user_id)
    bot.set_video_finalization_state(user_id, {
        "step": "scene_count",
        "selected_video_tier": "low",
        "selected_scene_count": 1,
        "source": "promptvideo",
        "source_payload": {"video_prompt": "Prompt video ready", "aspect_ratio": "9:16"},
        "has_video_prompt": True,
    })
    query = CaptureQuery("vfinal|back", user_id)

    asyncio.run(bot.handle_video_finalization_callback(_callback_update(query, user_id), SimpleNamespace()))

    assert bot.get_video_finalization_state(user_id)["step"] == "tier"
    assert "vfinal|tier|low" in _callbacks(query.outputs[-1]["reply_markup"])
    bot.clear_video_finalization_state(user_id)


def test_video_200_invoice_back_to_package_200_detail():
    user_id = 990104
    bot.clear_video_finalization_state(user_id)
    bot.clear_video_addon_state(user_id)
    finalization = {
        "step": "confirm",
        "selected_video_tier": "low",
        "selected_scene_count": 1,
        "source": "promptvideo",
        "source_payload": {"video_prompt": "Prompt video ready", "aspect_ratio": "9:16"},
        "has_video_prompt": True,
    }
    bot.set_video_finalization_state(user_id, finalization)
    bot.set_video_addon_state(user_id, {
        "source": "ai",
        "video_tier": "low",
        "pending_confirm_token": "invoice-token",
        "pending_payload": {
            "video_tier": "low",
            "video_prompt": "Prompt video ready",
            "selected_scene_count": 1,
            "scene_count": 1,
            "aspect_ratio": "9:16",
        },
        "video_order": {"current_screen": "invoice"},
    })
    query = CaptureQuery("videoaddon|back", user_id)

    asyncio.run(bot.handle_video_addon_callback(_callback_update(query, user_id), SimpleNamespace()))

    current = bot.get_video_finalization_state(user_id)
    assert current["step"] == "scene_count"
    assert current["selected_video_tier"] == "low"
    assert "1 cảnh ≈ 6s = 200 Xu" in _labels(query.outputs[-1]["reply_markup"])
    assert not bot.get_video_addon_state(user_id)
    bot.clear_video_finalization_state(user_id)


def test_video_200_quota_back_to_package_200_detail():
    callbacks = _callbacks(bot.video_beta_200_limit_keyboard("vi"))
    assert callbacks == ["vfinal|tier|basic", "vfinal|tier|common", "vfinal|scene_count_screen", "vfinal|main"]


def test_video_200_real_quota_block_creates_no_pending_confirmation(monkeypatch):
    user_id = 990105
    created_tokens = []
    recorded_events = []
    bot.clear_video_addon_state(user_id)
    state = bot.set_video_addon_state(user_id, {
        "source": "ai",
        "video_tier": "low",
        "selected_scene_count": 1,
        "pending_payload": {
            "job_type": "video",
            "video_tier": "low",
            "video_prompt": "Prompt video ready",
            "selected_scene_count": 1,
            "scene_count": 1,
        },
    })
    monkeypatch.setattr(bot, "video_beta_200_marketing_loss_enabled_runtime", lambda: True)
    monkeypatch.setattr(bot, "check_video_beta_200_limit", lambda _user_id=None: {"ok": False})
    monkeypatch.setattr(bot, "set_shopaikey_pending_confirmation", lambda *_args, **_kwargs: created_tokens.append("called"))
    monkeypatch.setattr(bot, "record_shopaikey_billing_event", lambda *args, **kwargs: recorded_events.append(args))
    query = CaptureQuery("videoaddon|none", user_id)

    asyncio.run(bot.finalize_video_addon_confirmation(query, user_id, state, "vi"))

    assert query.outputs[-1]["text"] == bot.video_beta_200_limit_message("vi")
    assert not created_tokens
    assert not recorded_events
    assert not bot.get_video_addon_state(user_id)


def test_video_200_quota_counts_only_real_accepted_jobs(monkeypatch, tmp_path):
    db_path = tmp_path / "video_200_quota.sqlite3"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    bot.init_db()
    accepted_job_id = bot.create_shopaikey_job(
        "quota_user",
        "quota_user",
        "video",
        status="IN_PROGRESS",
        admin_only=False,
        xu_cost_planned=200,
    )
    bot.record_shopaikey_billing_event(
        "quota_user",
        accepted_job_id,
        "video_confirmed",
        0,
        1000,
        1000,
        "confirmed_at=now; job_type=video; tier=low; marketing_loss=true",
    )
    assert bot.video_beta_200_today_counts("quota_user")["user_count"] == 0
    bot.record_shopaikey_billing_event(
        "quota_user",
        accepted_job_id,
        "video_deducted_after_provider_accept",
        200,
        1000,
        800,
        "tier=low",
    )
    assert bot.video_beta_200_today_counts("quota_user")["user_count"] == 1


def test_video_200_failed_or_guarded_jobs_not_counted(monkeypatch, tmp_path):
    db_path = tmp_path / "video_200_failed_quota.sqlite3"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    bot.init_db()
    failed_job_id = bot.create_shopaikey_job(
        "quota_user",
        "quota_user",
        "video",
        status="FAILED",
        admin_only=False,
        xu_cost_planned=200,
    )
    bot.record_shopaikey_billing_event(
        "quota_user",
        failed_job_id,
        "video_deducted_after_provider_accept",
        200,
        1000,
        800,
        "tier=low",
    )
    bot.record_shopaikey_billing_event(
        "quota_user",
        999999,
        "video_deducted_after_provider_accept",
        200,
        1000,
        800,
        "tier=low",
    )
    assert bot.video_beta_200_today_counts("quota_user")["user_count"] == 0


def test_video_200_quota_copy_is_public_safe():
    text = bot.video_beta_200_limit_message("vi")
    assert text == "Gói trải nghiệm 200 Xu đã hết lượt sử dụng trong hôm nay. Bạn có thể chọn gói 300 Xu hoặc 400 Xu để tiếp tục."
    for forbidden in ("Provider", "provider", "ShopAIKey", "task", "job", "API"):
        assert forbidden not in text


def test_image_result_copy_and_actions_are_public_safe(monkeypatch):
    text = bot.ui_text("vi", "image.success", label="Phổ thông", job_id=129, billing_note="Provider nội bộ")
    assert "Job" not in text
    assert "Provider" not in text
    assert "nội bộ" not in text
    monkeypatch.setattr(bot, "image_job_retry_warranty_remaining", lambda _job_id: 1)
    rows = bot.public_image_success_keyboard(129, "standard_warranty", "vi").inline_keyboard
    labels = [button.text for row in rows for button in row]
    assert [len(row) for row in rows] == [2, 2, 2]
    assert "🔁 Tạo lại ảnh bảo hành 1 lần" in labels
    assert "🖼 Tạo ảnh nữa" in labels
    assert "💾 Lưu ảnh/package" not in labels


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
    assert bot.VIDEO_MULTISCENE_PUBLIC_GUARD_TEXT == "Dịch vụ đang được kiểm tra. TOAN AAS chưa xử lý và chưa trừ Xu. Vui lòng thử lại sau."
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
