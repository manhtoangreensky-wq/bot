import asyncio
import inspect
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import bot


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _labels(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def _video_job_db(monkeypatch, tmp_path):
    path = tmp_path / "task3d7.sqlite3"
    monkeypatch.setattr(bot, "DB_FILE", str(path))
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE shopaikey_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT, chat_id TEXT, job_type TEXT, provider TEXT DEFAULT 'shopaikey',
            model TEXT, task_id TEXT UNIQUE, status TEXT, prompt_preview TEXT,
            result_url TEXT, result_sent INTEGER DEFAULT 0, output_file_id TEXT DEFAULT '',
            output_send_claimed_at TEXT DEFAULT '', output_sent_at TEXT DEFAULT '',
            output_sent_message_id TEXT DEFAULT '', output_sent_result_url TEXT DEFAULT '',
            output_sent_source TEXT DEFAULT '', completed_notified_at TEXT DEFAULT '',
            telegram_video_file_id TEXT DEFAULT '', duplicate_prevented_count INTEGER DEFAULT 0,
            last_telegram_send_error TEXT DEFAULT '', error_class TEXT DEFAULT '',
            provider_error_code TEXT DEFAULT '', provider_message TEXT DEFAULT '', fail_reason TEXT DEFAULT '',
            attempts INTEGER DEFAULT 0, poll_count INTEGER DEFAULT 0, admin_only INTEGER DEFAULT 0,
            xu_cost_planned INTEGER DEFAULT 0, package_item_type TEXT DEFAULT '',
            created_at TEXT, updated_at TEXT, finished_at TEXT
        );
        CREATE TABLE system_settings (
            key TEXT PRIMARY KEY, value TEXT, note TEXT, updated_at TEXT, updated_by TEXT
        );
        """
    )
    conn.commit()
    conn.close()
    return path


def _insert_video_job(path, task_id="task_3d7", result_sent=0, result_url="https://example.test/video.mp4"):
    conn = sqlite3.connect(path)
    cur = conn.execute(
        """INSERT INTO shopaikey_jobs
           (user_id, chat_id, job_type, task_id, status, result_url, result_sent, created_at, updated_at)
           VALUES ('7001', '9001', 'video', ?, 'SUCCESS', ?, ?, '2026-06-21 10:00:00', '2026-06-21 10:00:00')""",
        (task_id, result_url, int(result_sent)),
    )
    conn.commit()
    job_id = int(cur.lastrowid)
    conn.close()
    return job_id


class _TelegramBot:
    def __init__(self, video_fails=False):
        self.video_fails = video_fails
        self.video_calls = 0
        self.message_calls = 0

    async def send_video(self, **kwargs):
        self.video_calls += 1
        if self.video_fails:
            raise RuntimeError("telegram URL fetch failed")
        return SimpleNamespace(message_id=321, video=SimpleNamespace(file_id="telegram_file_1"))

    async def send_message(self, **kwargs):
        self.message_calls += 1
        return SimpleNamespace(message_id=321)


def test_video_result_sent_once_per_task_id(monkeypatch, tmp_path):
    path = _video_job_db(monkeypatch, tmp_path)
    job_id = _insert_video_job(path)
    client = _TelegramBot()
    first = asyncio.run(bot.send_shopaikey_video_result_once(client, 9001, "task_3d7", "https://example.test/video.mp4", job_id=job_id, source="pytest"))
    second = asyncio.run(bot.send_shopaikey_video_result_once(client, 9001, "task_3d7", "https://example.test/video.mp4", job_id=job_id, source="pytest_status"))
    assert first["sent"] is True
    assert second["sent"] is False
    assert second["duplicate_prevented"] is True
    assert client.video_calls == 1
    row = bot.shopaikey_job_by_id(job_id)
    assert row["result_sent"] == 1
    assert row["output_sent_at"]
    assert row["output_sent_source"] == "pytest"
    assert row["telegram_video_file_id"] == "telegram_file_1"
    assert row["duplicate_prevented_count"] == 1


def test_video_result_atomic_claim_allows_only_one_sender(monkeypatch, tmp_path):
    path = _video_job_db(monkeypatch, tmp_path)
    job_id = _insert_video_job(path, task_id="task_race")

    def claim(source):
        return bot.claim_shopaikey_video_output(
            task_id="task_race",
            job_id=job_id,
            result_url="https://example.test/video.mp4",
            source=source,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ("auto_poll", "status_check")))
    assert sum(bool(item.get("claimed")) for item in results) == 1
    assert sum(bool(item.get("duplicate_prevented")) for item in results) == 1


def test_url_link_result_marks_output_sent(monkeypatch, tmp_path):
    path = _video_job_db(monkeypatch, tmp_path)
    job_id = _insert_video_job(path, task_id="task_link")
    client = _TelegramBot(video_fails=True)
    result = asyncio.run(bot.send_shopaikey_video_result_once(client, 9001, "task_link", "https://example.test/video.mp4", job_id=job_id, source="link_fallback"))
    assert result["sent"] is True
    assert result["link_fallback"] is True
    assert client.video_calls == 1 and client.message_calls == 1
    assert bot.shopaikey_job_by_id(job_id)["result_sent"] == 1


def test_video_resend_button_can_send_again_explicitly(monkeypatch, tmp_path):
    path = _video_job_db(monkeypatch, tmp_path)
    job_id = _insert_video_job(path, task_id="task_resend")
    client = _TelegramBot()
    asyncio.run(bot.send_shopaikey_video_result_once(client, 9001, "task_resend", "https://example.test/video.mp4", job_id=job_id, source="first"))
    result = asyncio.run(bot.send_shopaikey_video_result_once(client, 9001, "task_resend", "https://example.test/video.mp4", job_id=job_id, source="explicit_public_resend", explicit_resend=True))
    assert result["sent"] is True
    assert result["explicit_resend"] is True
    assert client.video_calls == 2


def test_video_poll_and_status_use_idempotent_sender():
    poll_source = inspect.getsource(bot.auto_poll_shopaikey_video_job)
    status_source = inspect.getsource(bot.handle_shopaikey_video_job_callback)
    assert "send_shopaikey_video_result_once" in poll_source
    assert "send_shopaikey_video_result_once" in status_source
    assert "source=f\"auto_poll_{provider_route}\"" in poll_source
    assert 'source="public_status_check"' in status_source
    assert "if output_sent:" in poll_source
    assert "callback_may_deliver_result" in status_source


def test_admin_status_does_not_consume_public_video_result():
    command_source = inspect.getsource(bot.cmd_shopaikey_video_job)
    callback_source = inspect.getsource(bot.handle_shopaikey_video_job_callback)
    assert 'bool(int((db_job or {}).get("admin_only") or 0))' in command_source
    assert "callback_may_deliver_result = not is_admin_user(uid)" in callback_source
    assert "send_shopaikey_video_result(" not in command_source


def test_video_poll_does_not_resend_if_output_sent():
    source = inspect.getsource(bot.auto_poll_shopaikey_video_job)
    assert "send_shopaikey_video_result_once" in source
    assert "already_sent = bool(send_result.get" in source


def test_video_status_check_does_not_resend_completed():
    source = inspect.getsource(bot.handle_shopaikey_video_job_callback)
    assert 'source="public_status_check"' in source
    assert "send_result.get(\"duplicate_prevented\")" in source


def test_status_check_completed_offers_locked_result_actions():
    markup = bot.public_video_status_keyboard(
        "task_complete",
        {"id": 12, "status": "SUCCESS", "result_sent": 1, "package_item_type": "video_low"},
        "SUCCESS",
        "vi",
        output_sent=True,
    )
    callbacks = _callbacks(markup)
    assert callbacks == [
        "shopai_video_job|av|task_complete",
        "shopai_video_job|am|task_complete",
        "shopai_video_job|as|task_complete",
        "shopai_video_job|fb|task_complete",
        "shopai_video_job|main",
    ]
    assert _labels(markup) == [
        ["🎙 Thêm giọng/lồng tiếng", "🎵 Thêm nhạc"],
        ["📝 Thêm phụ đề", "💬 Góp ý kết quả"],
        ["🏠 Menu chính"],
    ]


def test_completed_video_result_menu_has_no_old_actions():
    callbacks = _callbacks(bot.public_video_success_keyboard("low", "vi", "task_complete"))
    joined = "\n".join(callbacks)
    for old in ("resend", "create_media|", "quick_image", "trendg|", "feedback|start", "menu|main_music"):
        assert old not in joined


def test_completed_video_addon_guards_are_clear():
    for kind in ("voice", "music", "subtitle"):
        text = bot.VIDEO_COMPLETED_ADDON_GUARD_TEXTS[kind]
        assert text == "Hệ thống đang bảo trì/nâng cấp. TOAN AAS chưa xử lý và chưa trừ Xu. Vui lòng thử lại sau."
        for forbidden in ("kiểm thử", "provider", "task", "job", "API", "ShopAIKey"):
            assert forbidden not in text


def test_video_addon_status_hides_secrets(monkeypatch):
    monkeypatch.setattr(bot, "is_voice_mux_ready", lambda: False)
    monkeypatch.setattr(bot, "is_music_mux_ready", lambda: False)
    monkeypatch.setattr(bot, "is_subtitle_burn_ready", lambda: False)
    monkeypatch.setattr(bot, "is_asr_ready", lambda: False)
    monkeypatch.setattr(bot, "local_worker_status_payload", lambda: {"connected": False, "ffmpeg_path_configured": True})
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {"full_result_ok": False})
    monkeypatch.setattr(bot, "get_system_setting", lambda key, default="": default)
    payload = bot.video_completed_addon_status_payload()
    assert payload["completed_buttons_visible"] is True
    assert payload["voice_mux_ready"] is False
    assert payload["ai_music_full_result_ready"] is False
    assert "token" not in payload
    assert "key" not in payload


def test_public_video_status_message_sanitizes_provider_state():
    text = bot.public_video_status_message(
        "Provider accepted",
        "model=veo3.1-fast; http=200; task_id=task_1; provider_status=queued; ShopAIKey",
        output_sent=False,
        lang="vi",
    )
    lowered = text.lower()
    for term in ("shopaikey", "provider", "model=", "http=", "task_id", "provider_status"):
        assert term not in lowered
    assert "Đang tạo video" in text


def test_no_generic_error_after_successful_output():
    source = inspect.getsource(bot.on_telegram_error)
    assert "completed_video_job_for_callback_error(update)" in source
    assert "record_video_post_output_error" in source
    assert "suppressed public error after completed video output" in source
    assert source.index("if completed_video_job:") < source.index("await context.bot.send_message")


def test_default_voice_not_silently_ignored(monkeypatch):
    monkeypatch.setattr(bot, "is_voice_mux_ready", lambda: False)
    state = {
        "current_video_voice_choice": "default_male",
        "video_finalization": {"voice_enabled": True, "voice_choice": "default_male", "voice_script": "Xin chào"},
    }
    guard = bot.video_voice_mux_export_guard(state)
    assert guard == {"ok": True, "reason": "default_voice_saved_not_muxed", "selected": True, "default_voice": True}
    text = bot.video_finalization_summary_text(state, "vi")
    assert "đã lưu nội dung nhưng chưa ghép vào video" in text


def test_voice_mux_unready_shows_clear_message(monkeypatch):
    monkeypatch.setattr(bot, "is_voice_mux_ready", lambda: False)
    text = bot.video_price_invoice_text({
        "video_tier": "low",
        "current_video_voice_choice": "default_female",
        "pending_payload": {"video_tier": "low", "base_cost": 200, "voice_choice": "default_female"},
    }, "vi")
    assert "Giọng đọc mặc định đã được lưu nhưng chưa ghép vào video" in text


def test_paid_voice_mux_unready_blocks_cleanly(monkeypatch):
    monkeypatch.setattr(bot, "is_voice_mux_ready", lambda: False)
    state = {
        "current_video_voice_choice": "voice_clone_create",
        "video_finalization": {"voice_enabled": True, "voice_choice": "voice_clone_create", "voice_script": "Xin chào"},
    }
    guard = bot.video_voice_mux_export_guard(state)
    assert guard["ok"] is False
    assert guard["reason"] == "paid_voice_mux_maintenance"
    export_source = inspect.getsource(bot.handle_video_export_confirm)
    assert "PUBLIC_PRODUCT_MAINTENANCE_VI" in export_source
    assert export_source.index("video_voice_mux_export_guard") < export_source.index("shopaikey_public_generation_guard")


def test_voice_scene_sync_schema_present(monkeypatch):
    monkeypatch.setattr(bot, "is_voice_mux_ready", lambda: False)
    schema = bot.video_voice_scene_sync_schema({
        "video_finalization": {"voice_enabled": True, "voice_choice": "default_female", "voice_script": "Lời đọc chung"},
        "source_payload": {"prompt_bundle": {"shot_table": [
            {"shot_number": 1, "duration_seconds": 5, "narration_text": "Cảnh một"},
            {"shot_number": 2, "duration_seconds": 4, "narration_text": "Cảnh hai"},
        ]}},
    })
    assert set(schema) == {"scene_voice_map", "narration_segments", "tts_audio_refs", "mux_status"}
    assert [item["duration_seconds"] for item in schema["scene_voice_map"]] == [5, 4]
    assert schema["mux_status"] == "maintenance"


def test_public_unready_guards_are_clean_and_have_no_admin_blocker():
    texts = [
        bot.voice_clone_public_guard_text("vi"),
        bot.voice_clone_provider_not_ready_public_text("vi"),
        bot.music_ai_public_guard_text("vi"),
        bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_DUB, {"origin": "video_addon"}, "vi", admin=False),
        bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_CREATE, {"origin": "video_addon"}, "vi", admin=False),
    ]
    for text in texts:
        assert "chưa xử lý" in text and "chưa trừ Xu" in text
        assert "Admin blocker" not in text
        assert "API" not in text and "ENV" not in text


def test_voice_clone_public_guard_verified_copy():
    assert bot.voice_clone_provider_not_ready_public_text("vi") == bot.VOICE_CLONE_PROVIDER_NOT_READY_PUBLIC_VI
    text = bot.voice_clone_provider_not_ready_public_text("vi")
    assert "Tạo voice riêng đang tạm khóa" in text
    assert "chưa xử lý và chưa trừ Xu" in text


def test_ai_music_public_guard_verified_copy():
    assert bot.music_ai_public_guard_text("vi") == "Dịch vụ đang được kiểm tra. TOAN AAS chưa xử lý và chưa trừ Xu. Vui lòng thử lại sau."


def test_video_dub_public_guard_maintenance():
    text = bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_DUB, {"origin": "video_addon"}, "vi", admin=False)
    assert "TOAN AAS chưa thể" in text
    assert "chưa trừ Xu" in text


def test_subtitle_public_guard_maintenance():
    text = bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_CREATE, {"origin": "video_addon"}, "vi", admin=False)
    assert "TOAN AAS chưa thể" in text
    assert "chưa trừ Xu" in text


def test_public_buttons_stay_visible_for_unready_products():
    main_callbacks = _callbacks(bot.main_video_keyboard("vi"))
    final_callbacks = _callbacks(bot.video_finalization_menu_keyboard("vi"))
    assert "vproduct|open|audio_addons" not in main_callbacks
    assert "vproduct|open|video_reference" not in main_callbacks
    assert "vproduct|open|motion_prompt" not in main_callbacks
    assert "vfinal|voice" in final_callbacks
    assert "vfinal|music" in final_callbacks
    assert "vfinal|addon" in final_callbacks


def test_video_flow_lock_snapshots_are_unchanged():
    assert bot.VIDEO_FLOW_LOCKED_AFTER_TASK3D7 is True
    menu = bot.main_video_keyboard("vi")
    assert len(menu.inline_keyboard) == 6
    assert sum(len(row) for row in menu.inline_keyboard) == 12  # 9 public products + prompt library + downloader utility + Menu chính
    assert len([item for item in _callbacks(menu) if item.startswith("vproduct|open|")]) == 9
    assert "vpromptlib|start" in _callbacks(menu)
    assert "vdownload|start" in _callbacks(menu)
    assert _labels(bot.task3d_result_keyboard("storyboard_prompt", "vi")) == [
        ["🖼 Tạo prompt ảnh", "🎥 Tạo prompt video"],
        ["📦 Xuất bộ prompt", "💾 Lưu Kho prompt"],
        ["🔁 Đổi phong cách"],
        ["🎬 Dùng để tạo video"],
        ["⬅️ Quay lại", "🏠 Menu chính"],
    ]
    assert _labels(bot.video_addon_confirm_keyboard("locked-token", "low", "vi")) == [
        ["🎬 Xuất video", "⚙️ Đổi tùy chọn"],
        ["⬅️ Quay lại", "🏠 Menu chính"],
    ]
    assert _callbacks(bot.video_addon_confirm_keyboard("locked-token", "low", "vi")) == [
        "videoaddon|export|locked-token", "vfinal|menu", "videoaddon|back", "videoaddon|main",
    ]


def test_export_core_unchanged_except_dedupe_bridge():
    source = inspect.getsource(bot.handle_video_export_confirm)
    assert "handle_shopaikey_public_callback(update, context, canonical_callback)" in source
    assert 'canonical_callback = f"shopai|confirm|{token}"' in source
    assert "query.data =" not in source
    assert "spend_fixed_credit" not in source
