import asyncio
import inspect
import json
from types import SimpleNamespace

import bot


PRODUCT_UI_DENYLIST = [
    "ADMIN TEST MODE",
    "OWNER/ADMIN",
    "ADMIN DIAGNOSTIC",
    "test mode",
    "fake",
    "smoke",
    "provider",
    "API",
    "route",
    "adapter",
    "endpoint",
    "provider_voice_id",
    "profile_id",
    "public gate",
    "bypassed",
    "clone endpoint",
    "HTTP status",
    "http_status",
    "error_code",
    "route_errors",
    "traceback",
    "debug",
    "ENV",
    "configured_for_admin_smoke",
    "MiniMax",
    "Key4U",
    "ShopAIKey",
]


class CaptureMessage:
    def __init__(self, user_id=23901):
        self.chat_id = user_id
        self.outputs = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.outputs.append({"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs})
        return SimpleNamespace(text=text, reply_markup=reply_markup)


class FakeTelegramFile:
    async def download_as_bytearray(self):
        return bytearray(b"sample-audio")


class CaptureBot:
    async def get_file(self, _file_id):
        return FakeTelegramFile()

    async def send_audio(self, *_args, **_kwargs):
        raise AssertionError("preview audio should not be sent in clean failure tests")


def _assert_clean_product_text(text: str):
    folded = str(text or "").lower()
    for term in PRODUCT_UI_DENYLIST:
        assert term.lower() not in folded


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _init_voice_db(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "voice_p0_19a3.db"))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("VOICE_ASSET_STORAGE_DIR", str(tmp_path / "voice_assets"))
    bot.USER_PENDING.clear()
    bot.init_db()


def _make_confirmed_profile(user_id=23901, display_name="Voice product"):
    profile_id = bot.save_user_voice_profile(user_id, "telegram-sample-file", display_name=display_name, consent_at=bot.now_text())
    profile = bot.get_user_voice_profile(user_id, profile_id)
    metadata = bot.voice_profile_metadata(profile)
    metadata["confirmation_sample_text"] = bot.VOICE_CLONE_CONFIRMATION_SAMPLE_TEXT
    bot.update_user_voice_profile(
        user_id,
        profile_id,
        display_name=display_name,
        status="pending_confirm",
        metadata_json=json.dumps(metadata, ensure_ascii=False),
    )
    return bot.get_user_voice_profile(user_id, profile_id)


def _ready_readiness(*, public_enabled=True):
    return {
        "ready": True,
        "public_enabled": public_enabled,
        "provider_permission_blocked": False,
        "provider_permission_blocker": "",
        "routes": ["key4u_minimax"],
        "shopaikey_configured": False,
        "key4u_configured": True,
        "active_custom_voice_route": "key4u_minimax",
        "tts_smoke": "PASS",
        "clone_smoke": "PASS",
    }


def _run_product_clone(monkeypatch, tmp_path, *, user_id=23901, admin=False, public_enabled=True, provider_voice_id="voice-clean-1", tts_status="FAIL"):
    _init_voice_db(monkeypatch, tmp_path)
    profile = _make_confirmed_profile(user_id, "Voice product")
    calls = []
    charges = []
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: _ready_readiness(public_enabled=public_enabled))
    monkeypatch.setattr(bot, "voice_clone_last_forbidden_provider", lambda: "")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: bool(admin))
    monkeypatch.setattr(bot, "preview_quota_guard", lambda *_args, **_kwargs: {"allowed": True})
    monkeypatch.setattr(bot, "consume_preview_quota", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(bot, "voice_preview_guard", lambda *_args, **_kwargs: {"ok": True, "preview_key": "p0-19a3", "preview_text": "Xin chao"})
    monkeypatch.setattr(bot, "acquire_voice_preview_generation", lambda _uid, _pid, _guard: (True, None))

    async def fake_engine(*_args, **_kwargs):
        calls.append("execute_engine")
        return {"ok": True}

    async def fake_upload(*_args, **_kwargs):
        calls.append("upload")
        return "PASS", "provider-file", "ok", 200

    async def fake_clone(_file_id, _voice_id, **_kwargs):
        calls.append("clone")
        return "PASS", ({"voice_id": provider_voice_id} if provider_voice_id else {}), "ok", 200

    async def fake_tts(*_args, **_kwargs):
        calls.append("tts")
        return tts_status, b"" if tts_status != "PASS" else b"preview-audio", "preview unavailable", 200

    def fake_spend(*args, **kwargs):
        charges.append((args, kwargs))
        raise AssertionError("product flow must not charge before a valid saved voice")

    monkeypatch.setattr(bot, "execute_engine", fake_engine)
    monkeypatch.setattr(bot, "key4u_minimax_upload_voice_sample", fake_upload)
    monkeypatch.setattr(bot, "key4u_minimax_voice_clone", fake_clone)
    monkeypatch.setattr(bot, "key4u_minimax_tts_bytes", fake_tts)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", fake_spend)

    message = CaptureMessage(user_id)
    query = SimpleNamespace(message=message)
    context = SimpleNamespace(bot=CaptureBot())
    asyncio.run(bot.create_minimax_voice_profile_preview(query, context, user_id, profile, "vi"))
    fresh = bot.get_user_voice_profile(user_id, int(profile["id"]))
    return calls, charges, message, fresh


def test_voice_product_confirm_has_no_admin_test_mode(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "count_successful_custom_voice_profiles", lambda *_args, **_kwargs: 0)
    text = bot.voice_clone_quote_text({"id": 1, "user_id": bot.ADMIN_ID}, "vi")

    assert "Tạo voice riêng" in text
    _assert_clean_product_text(text)


def test_voice_product_confirm_has_no_provider_words(monkeypatch):
    monkeypatch.setattr(bot, "count_successful_custom_voice_profiles", lambda *_args, **_kwargs: 0)
    text = bot.voice_clone_quote_text({"id": 1, "user_id": 23901}, "vi")

    _assert_clean_product_text(text)


def test_admin_voice_product_ui_same_clean_copy_as_public(monkeypatch):
    monkeypatch.setattr(bot, "count_successful_custom_voice_profiles", lambda *_args, **_kwargs: 0)
    public_text = bot.voice_clone_quote_text({"id": 1, "user_id": 23902}, "vi")
    admin_text = bot.voice_clone_quote_text({"id": 1, "user_id": bot.ADMIN_ID}, "vi")

    assert admin_text == public_text
    _assert_clean_product_text(admin_text)


def test_first_custom_voice_free_label_clean(monkeypatch):
    monkeypatch.setattr(bot, "get_voice_profile_by_id", lambda _pid: {"id": 10, "user_id": 23903})
    monkeypatch.setattr(bot, "count_successful_custom_voice_profiles", lambda *_args, **_kwargs: 0)
    labels = _labels(bot.voice_clone_quote_keyboard(10, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))

    assert "✅ Tạo voice miễn phí" in labels
    for label in labels:
        _assert_clean_product_text(label)


def test_second_custom_voice_50_xu_label_clean(monkeypatch):
    monkeypatch.setattr(bot, "get_voice_profile_by_id", lambda _pid: {"id": 10, "user_id": 23904})
    monkeypatch.setattr(bot, "count_successful_custom_voice_profiles", lambda *_args, **_kwargs: 1)
    labels = _labels(bot.voice_clone_quote_keyboard(10, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))

    assert f"✅ Tạo voice riêng {bot.VOICE_PROFILE_PRICE_XU} Xu" in labels
    for label in labels:
        _assert_clean_product_text(label)


def test_admin_does_not_show_admin_test_mode_on_first_free_screen(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "get_voice_profile_by_id", lambda _pid: {"id": 10, "user_id": bot.ADMIN_ID})
    monkeypatch.setattr(bot, "count_successful_custom_voice_profiles", lambda *_args, **_kwargs: 0)

    text = bot.voice_clone_quote_text({"id": 10, "user_id": bot.ADMIN_ID}, "vi")
    labels = _labels(bot.voice_clone_quote_keyboard(10, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))

    _assert_clean_product_text(text)
    assert "✅ Tạo voice miễn phí" in labels
    assert not any("Admin" in label or "test" in label.lower() for label in labels)


def test_voice_product_failure_has_no_provider_words():
    text = bot.voice_clone_product_failure_text("vi", "voice_routes_failed")

    assert "TOAN AAS chưa tạo được voice hợp lệ" in text
    _assert_clean_product_text(text)


def test_voice_product_failure_has_no_route_errors():
    text = bot.voice_clone_product_failure_text("vi", "route_errors http_status adapter")

    _assert_clean_product_text(text)


def test_voice_product_failure_has_no_http_status():
    text = bot.voice_clone_product_failure_text("vi", "http_status=500 error_code=FAIL")

    _assert_clean_product_text(text)


def test_voice_product_failure_has_no_provider_voice_id():
    text = bot.voice_clone_product_failure_text("vi", "missing_provider_voice_id")

    _assert_clean_product_text(text)


def test_voice_product_ui_no_technical_english_dump():
    text = bot.voice_clone_product_failure_text("vi", "adapter=shopaikey_minimax; http_status=500; provider_status=fail")

    _assert_clean_product_text(text)
    assert "adapter=" not in text
    assert "http" not in text.lower()


def test_provider_failure_returns_clean_voice_message(monkeypatch, tmp_path):
    _calls, charges, message, fresh = _run_product_clone(monkeypatch, tmp_path, user_id=23905, provider_voice_id="")

    text = message.outputs[-1]["text"]
    assert fresh["status"] != "ready"
    assert charges == []
    _assert_clean_product_text(text)


def test_provider_voice_id_missing_clean_failure_no_ready_save(monkeypatch, tmp_path):
    _calls, _charges, message, fresh = _run_product_clone(monkeypatch, tmp_path, user_id=23906, provider_voice_id="")

    assert not str(fresh.get("provider_voice_id") or "").strip()
    assert fresh["status"] != "ready"
    _assert_clean_product_text(message.outputs[-1]["text"])


def test_voice_duration_too_short_clean_message():
    text = bot.voice_clone_product_failure_text("vi", "duration_too_short")

    assert "Mẫu giọng hơi ngắn" in text
    _assert_clean_product_text(text)


def test_no_charge_on_clean_failure(monkeypatch, tmp_path):
    _calls, charges, message, _fresh = _run_product_clone(monkeypatch, tmp_path, user_id=23907, provider_voice_id="")

    assert charges == []
    assert "chưa trừ Xu" in message.outputs[-1]["text"]


def test_admin_interactive_voice_no_charge_internal_only(monkeypatch, tmp_path):
    _calls, charges, message, fresh = _run_product_clone(
        monkeypatch,
        tmp_path,
        user_id=23908,
        admin=True,
        provider_voice_id="admin-clean-voice",
        tts_status="FAIL",
    )

    metadata = bot.voice_profile_metadata(fresh)
    assert fresh["status"] == "ready"
    assert int(metadata.get("charged_xu") or 0) == 0
    assert charges == []
    _assert_clean_product_text(message.outputs[-1]["text"])


def test_admin_interactive_voice_bypasses_public_lock_without_ui_leak(monkeypatch, tmp_path):
    calls, charges, message, fresh = _run_product_clone(
        monkeypatch,
        tmp_path,
        user_id=23909,
        admin=True,
        public_enabled=False,
        provider_voice_id="",
    )

    assert "upload" in calls
    assert "clone" in calls
    assert fresh["status"] != "ready"
    assert charges == []
    _assert_clean_product_text(message.outputs[-1]["text"])


def test_admin_diagnostic_not_used_in_product_callbacks():
    source = inspect.getsource(bot.create_minimax_voice_profile_preview)

    assert "voice_clone_admin_product_block_text(" not in source
    assert "voice_clone_admin_preview_failure_text(" not in source
    assert "ADMIN TEST MODE" not in source


def test_voice_slash_smoke_output_not_reused_by_product_flow():
    source = inspect.getsource(bot.create_minimax_voice_profile_preview)

    assert "/tool_test" not in source
    assert "save_tool_test_result" not in source


def test_voice_product_buttons_do_not_route_to_smoke_diagnostic():
    markup = bot.custom_voice_failed_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM, profile_id=123)
    callbacks = _callbacks(markup)
    labels = _labels(markup)

    assert "🔁 Thử lại" in labels
    assert "🎙 Giọng nữ mặc định" in labels
    assert "🎙 Giọng nam mặc định" in labels
    assert "📚 Kho voice" in labels
    assert "🏠 Menu chính" in labels
    assert not any("tool_test" in callback or "voice_admin" in callback for callback in callbacks)


def test_voice_failure_retry_preserves_context():
    callbacks = _callbacks(bot.custom_voice_failed_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM, profile_id=123))

    assert "music_quick|showroom|voice_clone_retry_context:123" in callbacks
    assert "menu|main" in callbacks


def test_voice_back_from_failure_returns_vault_or_confirm():
    callbacks = _callbacks(bot.custom_voice_failed_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM, profile_id=123))

    assert "music_quick|showroom|voice_profiles" in callbacks
    assert "music_quick|showroom|voice_clone_retry_context:123" in callbacks


def test_voice_back_never_main_menu_unless_menu_main_pressed():
    callbacks = _callbacks(bot.custom_voice_failed_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM, profile_id=123))
    non_main = [callback for callback in callbacks if callback != "menu|main"]

    assert "menu|main" in callbacks
    assert all(callback.startswith("music_quick|showroom|") for callback in non_main)
