from datetime import datetime, timedelta
from pathlib import Path

import bot


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_p0_14_protected_area_markers_still_present():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    for marker in [
        'CommandHandler("naptien"',
        "handle_payos_alert_callback",
        "PAYOS_WEBHOOK_URL",
        "record_credit_event",
        "cmd_ledger_user",
        "TASK3D_VIDEO_IMAGE_PACKAGES",
        "main_menu_keyboard",
        "synthesize_standalone_tts_audio",
    ]:
        assert marker in source


def test_admin_provider_back_returns_admin_root():
    assert bot.admin_back_callback("admin_provider") == "menu|admin"


def test_provider_usage_back_returns_provider_management():
    assert bot.admin_back_callback("admin_provider_usage") == "menu|admin_provider"


def test_provider_status_back_returns_provider_management():
    assert bot.admin_back_callback("admin_provider_status") == "menu|admin_provider"


def test_test_provider_back_returns_provider_management():
    assert bot.admin_back_callback("admin_provider_test") == "menu|admin_provider"


def test_finance_back_returns_finance_menu():
    assert bot.admin_back_callback("finance_revenue") == "menu|finance"


def test_freeze_queue_back_returns_freeze_queue_menu():
    assert bot.admin_back_callback("freeze_status") == "menu|freeze_queue"


def test_smoke_test_back_returns_smoke_menu():
    assert bot.admin_back_callback("smoke_video") == "menu|smoke_test"


def test_admin_menu_main_button_goes_public_main():
    assert bot.admin_menu_main_callback() == "menu|main"


def test_admin_button_from_submenu_goes_admin_root():
    assert bot.admin_menu_root_callback() == "menu|admin"
    callbacks = _callbacks(bot.admin_provider_child_keyboard("admin_provider_usage"))
    assert "menu|admin" in callbacks


def test_no_admin_submenu_random_back_jump():
    for action, parent in bot.ADMIN_NAV_PARENT_ACTIONS.items():
        state = bot.admin_nav_state(action)
        assert state["current_menu"] == action
        assert state["parent_menu"] == parent
        assert state["previous_callback"] == f"menu|{parent}"


def test_admin_callbacks_are_scoped():
    assert not bot.admin_callback_is_scoped("back")
    assert not bot.admin_callback_is_scoped("menu")
    assert bot.admin_callback_is_scoped("menu|admin_provider")
    assert bot.admin_callback_is_scoped("provider:shopaikey:freeze")
    assert bot.admin_callback_is_scoped("job:video_multiscene:status:msv-1")


def test_dangerous_actions_have_confirm():
    assert bot.admin_action_requires_confirm("freeze_provider")
    assert bot.admin_action_requires_confirm("unfreeze_provider")
    assert bot.admin_action_requires_confirm("manual_xu")
    assert bot.admin_action_requires_confirm("clear_lock")


def test_provider_paid_tests_require_confirm():
    assert bot.admin_action_requires_confirm("provider_paid_test")
    text = bot.admin_provider_test_text_v2()
    assert "--confirm-paid" in text
    assert "Provider paid real test" in text


def test_default_last_row_has_back_and_main_or_admin():
    admin_row = bot.admin_default_last_row("admin_provider_usage")
    assert [button.text for button in admin_row] == ["⬅️ Quay lại", "⚙️ Admin"]
    assert [button.callback_data for button in admin_row] == ["menu|admin_provider", "menu|admin"]
    main_row = bot.admin_default_last_row("admin_provider", include_admin=False)
    assert [button.text for button in main_row] == ["⬅️ Quay lại", "🏠 Menu chính"]
    assert main_row[-1].callback_data == "menu|main"


def test_provider_management_lists_shopaikey_and_key4u_when_configured(monkeypatch):
    monkeypatch.setattr(bot, "provider_freeze_display", lambda _provider: {"frozen": False})
    monkeypatch.setattr(bot, "provider_usage_summary", lambda *_args, **_kwargs: {"fail_count": 0})
    monkeypatch.setattr(bot, "get_suno_music_readiness", lambda: {"providers": {"key4u_suno": {"configured": True}}})
    monkeypatch.setattr(bot, "video_asr_provider_available_for", lambda public=True: True)
    monkeypatch.setattr(bot, "video_translation_provider_available", lambda: True)
    monkeypatch.setattr(bot, "video_tts_provider_available_for", lambda public=True: True)
    text = bot.admin_provider_menu_text_v2()
    assert "Provider | Nhóm | Trạng thái | Dùng cho | Ghi chú" in text
    assert "ShopAIKey" in text
    assert "Key4U" in text
    assert "Deepgram" in text


def test_provider_usage_no_secret(monkeypatch):
    monkeypatch.setattr(bot, "shopaikey_last_usage_snapshot", lambda: {
        "remaining": 10,
        "total": 20,
        "remaining_percent": 50,
        "group_name": "cheap",
        "last_at": "2026-06-24 00:00:00",
    })
    text = bot.admin_provider_usage_text_v2().lower()
    for forbidden in ("api_key", "token", "secret", "authorization", "bearer"):
        assert forbidden not in text


def test_provider_usage_key4u_missing_clear(monkeypatch):
    monkeypatch.setattr(bot, "shopaikey_last_usage_snapshot", lambda: {})
    monkeypatch.setattr(bot, "KEY4U_USAGE_ENDPOINT", "")
    assert "Key4U usage: chưa có endpoint usage đã xác minh" in bot.admin_provider_usage_text_v2()


def test_provider_management_buttons_route_correctly():
    callbacks = _callbacks(bot.admin_provider_keyboard_v2())
    assert callbacks == [
        "menu|admin_provider_status",
        "menu|admin_provider_test",
        "menu|admin_provider_usage",
        "menu|admin_provider_routes",
        "menu|admin_provider_freeze",
        "menu|admin_provider_unfreeze",
        "menu|admin_provider",
        "menu|admin",
        "menu|main",
    ]


def test_provider_status_compact_table(monkeypatch):
    rows = [("ShopAIKey", "cheap", "configured", "chat", "ok")]
    lines = bot.admin_provider_compact_table_lines(rows)
    assert "Provider | Nhóm | Trạng thái | Dùng cho | Ghi chú" in "\n".join(lines)
    assert "ShopAIKey" in "\n".join(lines)


def _admin_rules_doc():
    return Path(bot.__file__).with_name("docs").joinpath("admin_button_rules.md").read_text(encoding="utf-8")


def test_admin_command_descriptions_present():
    doc = _admin_rules_doc()
    for section in ("Provider", "Music/Suno", "Video", "Bill/Xu", "Finance", "Freeze/Queue"):
        assert f"### {section}" in doc
    for command in ("/providers", "/music_suno_jobs", "/video_multiscene_job", "/finance_dashboard", "/queue_status"):
        assert command in doc


def test_only_existing_commands_listed_or_marked_missing():
    doc = _admin_rules_doc()
    assert "/music_engine_status` — chưa có lệnh này" in doc
    assert "/video_engine_status` — chưa có lệnh này" in doc
    assert "/add_xu <telegram_id> <amount>` — chưa có lệnh này" in doc


def test_bill_xu_commands_have_examples():
    doc = _admin_rules_doc()
    assert "/add <telegram_id> <amount>" in doc
    assert "/deduct <telegram_id> <amount>" in doc
    assert "/grant_combo <telegram_id> <combo_code>" in doc


def test_dangerous_command_descriptions_warn_confirm():
    doc = _admin_rules_doc().lower()
    for phrase in ("provider paid real test requires explicit confirm", "confirm required", "freeze/unfreeze requires confirm"):
        assert phrase in doc


def test_music_processing_job_shows_age_and_timeout():
    job = {
        "feature": "music_suno",
        "internal_job_id": "MUS-OLD",
        "provider": "key4u_suno",
        "provider_task_id": "provider-task-123",
        "status": "processing",
        "created_at": (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": "2026-06-24 00:00:00",
        "last_poll_at": "2026-06-24 00:10:00",
        "next_poll_after": "2026-06-24 00:11:00",
        "poll_count": 7,
        "output_bytes": 0,
    }
    text = bot.engine_async_status_text(job, admin=True)
    assert "timeout_provider_processing" in text
    assert "Age:" in text
    assert "Last poll:" in text
    assert "Next poll after:" in text


def test_music_timeout_no_fake_success_no_charge():
    job = {
        "feature": "music_suno",
        "internal_job_id": "MUS-OLD",
        "provider_task_id": "provider-task-123",
        "status": "processing",
        "created_at": (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
        "output_bytes": 0,
    }
    text = bot.engine_async_status_text(job, admin=True)
    assert "TOAN AAS chưa trừ Xu" in text
    assert "PASS" not in text


def test_video_overloaded_error_suggests_retry_or_freeze():
    job = {"parent_task_id": "msv-1", "scene_jobs": [{"scene_index": 1, "status": "FAILED", "error": "upstream overloaded"}]}
    text = bot.multiscene_job_status_text(job, admin=True)
    assert "Provider video đang quá tải" in text
    labels = _labels(bot.engine_async_status_keyboard("msv-1", "multiscene"))
    assert "🔁 Retry cảnh lỗi" in labels
    assert "🟡 Freeze" in labels


def test_multiscene_retry_failed_scenes_requires_confirm():
    job = {"scene_jobs": [{"scene_index": 1, "status": "FAILED"}, {"scene_index": 2, "status": "COMPLETED"}]}
    plan = bot.multiscene_retry_plan(job, confirmed=False)
    assert plan["requires_confirm"] is True
    assert plan["retry_scene_indexes"] == [1]


def test_multiscene_retry_does_not_duplicate_successful_scenes():
    job = {"scene_jobs": [{"scene_index": 1, "status": "FAILED"}, {"scene_index": 2, "status": "COMPLETED"}]}
    plan = bot.multiscene_retry_plan(job, confirmed=True)
    assert plan["retry_scene_indexes"] == [1]
    assert plan["skip_scene_indexes"] == [2]


def test_fallback_only_shown_if_verified():
    job = {"scene_jobs": [{"scene_index": 1, "status": "FAILED"}]}
    assert bot.multiscene_retry_plan(job, fallback_verified=False)["fallback_available"] is False
    assert bot.multiscene_retry_plan(job, fallback_verified=True)["fallback_available"] is True


def test_upstream_overloaded_admin_vietnamese_copy():
    assert "Provider video đang quá tải" in bot.multiscene_overloaded_admin_copy()
    assert "TOAN AAS chưa trừ Xu" in bot.multiscene_overloaded_admin_copy()


def test_suno_processing_vietnamese_copy():
    job = {
        "feature": "music_suno",
        "internal_job_id": "MUS-NEW",
        "provider_task_id": "provider-task-123",
        "status": "processing",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "output_bytes": 0,
    }
    text = bot.engine_async_status_text(job, admin=True)
    assert "Provider đang xử lý" in text


def test_no_raw_provider_english_error_to_public():
    public_text = bot.ENGINE_ASYNC_PUBLIC_CHECKING_VI.lower()
    for forbidden in ("http", "traceback", "api", "key4u", "shopaikey", "task_id"):
        assert forbidden not in public_text
