import asyncio
import inspect
import json
from types import SimpleNamespace

import bot
from services import voice_clone_pipeline


class CaptureMessage:
    def __init__(self, user_id=22901):
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
        raise AssertionError("preview audio should not be sent when provider preview is unavailable")


def _init_voice_db(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "voice_p0_19a2.db"))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("VOICE_ASSET_STORAGE_DIR", str(tmp_path / "voice_assets"))
    bot.USER_PENDING.clear()
    bot.init_db()


def _make_confirmed_profile(user_id=22901, display_name="Voice rieng"):
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


def _ready_readiness(*, public_enabled=True, provider_permission_blocked=False):
    return {
        "ready": True,
        "public_enabled": public_enabled,
        "provider_permission_blocked": provider_permission_blocked,
        "provider_permission_blocker": "clone_permission_forbidden" if provider_permission_blocked else "",
        "routes": ["key4u_minimax"],
        "shopaikey_configured": False,
        "key4u_configured": True,
        "active_custom_voice_route": "key4u_minimax",
        "tts_smoke": "PASS",
        "clone_smoke": "PASS",
    }


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _run_product_clone(monkeypatch, tmp_path, *, user_id=22901, admin=False, tts_status="FAIL", provider_voice_id="provider-ready-voice"):
    _init_voice_db(monkeypatch, tmp_path)
    profile = _make_confirmed_profile(user_id, "Voice product")
    calls = []
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: _ready_readiness(public_enabled=True))
    monkeypatch.setattr(bot, "voice_clone_last_forbidden_provider", lambda: "")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: bool(admin))
    monkeypatch.setattr(bot, "preview_quota_guard", lambda *_args, **_kwargs: {"allowed": True})
    monkeypatch.setattr(bot, "consume_preview_quota", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(bot, "voice_preview_guard", lambda *_args, **_kwargs: {"ok": True, "preview_key": "p0-19a2", "preview_text": "Xin chao"})
    monkeypatch.setattr(bot, "acquire_voice_preview_generation", lambda _uid, _pid, _guard: (True, None))

    async def fake_engine(*_args, **_kwargs):
        calls.append("execute_engine")
        return {"ok": True}

    async def fake_upload(*_args, **_kwargs):
        calls.append("upload")
        return "PASS", "provider-file", "ok", 200

    async def fake_clone(_file_id, _voice_id, **_kwargs):
        calls.append("clone")
        payload = {"voice_id": provider_voice_id} if provider_voice_id else {}
        return "PASS", payload, "ok", 200

    async def fake_tts(*_args, **_kwargs):
        calls.append("tts")
        return tts_status, b"" if tts_status != "PASS" else b"preview-audio", "preview unavailable", 200

    def no_charge(*_args, **_kwargs):
        raise AssertionError("this product clone path must not charge before provider_voice_id/finalize policy")

    monkeypatch.setattr(bot, "execute_engine", fake_engine)
    monkeypatch.setattr(bot, "key4u_minimax_upload_voice_sample", fake_upload)
    monkeypatch.setattr(bot, "key4u_minimax_voice_clone", fake_clone)
    monkeypatch.setattr(bot, "key4u_minimax_tts_bytes", fake_tts)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", no_charge)

    message = CaptureMessage(user_id)
    query = SimpleNamespace(message=message)
    context = SimpleNamespace(bot=CaptureBot())
    asyncio.run(bot.create_minimax_voice_profile_preview(query, context, user_id, profile, "vi"))
    fresh = bot.get_user_voice_profile(user_id, int(profile["id"]))
    return calls, message, fresh


def test_admin_interactive_voice_not_public_blocked(monkeypatch):
    readiness = _ready_readiness(public_enabled=False, provider_permission_blocked=True)
    monkeypatch.setattr(bot, "voice_clone_last_forbidden_provider", lambda: "")
    attempts = bot.voice_clone_provider_route_attempts(readiness, admin_access=True)

    assert attempts
    assert bot.voice_clone_ready_for_processing(readiness, attempts, admin_access=True) is True
    assert bot.voice_clone_access_allowed(bot.ADMIN_ID, readiness, attempts, admin_access=True) is True


def test_voice_menu_labels_unchanged():
    labels = _labels(bot.voice_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))

    for label in ["✍️ Văn bản thành giọng nói", "🎧 Giọng nói thành văn bản", "👩 Giọng nữ", "👨 Giọng nam", "📂 Kho voice", "🎙 Tạo voice riêng"]:
        assert label in labels


def test_voice_keyboard_layout_unchanged():
    rows = [[button.text for button in row] for row in bot.voice_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM).inline_keyboard]

    assert rows[:3] == [
        ["✍️ Văn bản thành giọng nói", "🎧 Giọng nói thành văn bản"],
        ["👩 Giọng nữ", "👨 Giọng nam"],
        ["📂 Kho voice", "🎙 Tạo voice riêng"],
    ]


def test_no_voice_ui_redesign_in_p0_19a2():
    source = inspect.getsource(bot.voice_hub_keyboard)

    assert "process_custom_voice_create" not in source
    assert "voice_clone_pipeline" not in source
    assert "build_2col_keyboard" in source


def test_custom_voice_product_handler_calls_blackbox():
    source = inspect.getsource(bot.create_minimax_voice_profile_preview)

    assert "voice_clone_pipeline.process_custom_voice_create" in source
    assert "for route_name, upload_call, clone_call, tts_call in route_attempts" not in source
    assert "await upload_call(audio_bytes)" not in source
    assert "await clone_call(" not in source


def test_voice_tts_product_handler_calls_blackbox():
    source = inspect.getsource(bot.send_paid_saved_voice_tts_result)

    assert "voice_clone_pipeline.process_voice_tts" in source
    assert "voice_saved_tts" in source


def test_public_user_guarded_before_provider_when_not_ready(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    user_id = 22902
    profile = _make_confirmed_profile(user_id, "Voice public blocked")
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: _ready_readiness(public_enabled=False, provider_permission_blocked=True))
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "preview_quota_guard", lambda *_args, **_kwargs: {"allowed": True})
    monkeypatch.setattr(bot, "voice_preview_guard", lambda *_args, **_kwargs: {"ok": True, "preview_key": "blocked", "preview_text": "Xin chao"})
    monkeypatch.setattr(bot, "acquire_voice_preview_generation", lambda _uid, _pid, _guard: (True, None))

    async def forbidden_provider(*_args, **_kwargs):
        raise AssertionError("public blocked flow must stop before provider")

    monkeypatch.setattr(bot, "key4u_minimax_upload_voice_sample", forbidden_provider)
    monkeypatch.setattr(bot, "execute_engine", forbidden_provider)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not charge")))

    message = CaptureMessage(user_id)
    asyncio.run(bot.create_minimax_voice_profile_preview(SimpleNamespace(message=message), SimpleNamespace(bot=CaptureBot()), user_id, profile, "vi"))

    assert "Tạo voice riêng đang tạm khóa" in message.outputs[-1]["text"]
    assert "chưa trừ Xu" in message.outputs[-1]["text"]
    assert bot.get_user_voice_profile(user_id, int(profile["id"]))["status"] != "ready"


def test_admin_blocked_provider_gets_sanitized_diagnostic(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    user_id = 22903
    profile = _make_confirmed_profile(user_id, "Voice admin blocked")
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: _ready_readiness(public_enabled=False, provider_permission_blocked=True) | {"key4u_configured": False, "routes": []})
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    message = CaptureMessage(user_id)

    asyncio.run(bot.create_minimax_voice_profile_preview(SimpleNamespace(message=message), SimpleNamespace(bot=SimpleNamespace()), user_id, profile, "vi"))

    text = message.outputs[-1]["text"]
    assert "ADMIN TEST MODE" in text
    assert "public gate bypassed" in text
    assert "provider_voice_id present: <code>NO</code>" in text
    assert "TOKEN" not in text


def test_first_custom_voice_free_for_public_user(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    user_id = 22904
    default_id = bot.save_user_voice_profile(user_id, "default-source", display_name="Default imported")
    bot.update_user_voice_profile(user_id, default_id, source_file_id="", source_file_ref="", status="ready", provider_voice_id="default-provider-voice")
    failed_id = bot.save_user_voice_profile(user_id, "failed-sample", display_name="Failed")
    bot.update_user_voice_profile(user_id, failed_id, status="failed_provider_not_ready", provider_voice_id="")

    assert bot.count_successful_custom_voice_profiles(user_id) == 0
    assert bot.voice_profile_storage_price_xu(user_id) == 0
    assert "đầu tiên miễn phí" in bot.voice_clone_quote_text(_make_confirmed_profile(user_id, "Next voice"), "vi")


def test_second_custom_voice_costs_50_xu(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    user_id = 22905
    first = _make_confirmed_profile(user_id, "Voice one")
    bot.update_user_voice_profile(user_id, int(first["id"]), status="ready", provider_voice_id="provider-custom-one")

    assert bot.count_successful_custom_voice_profiles(user_id) == 1
    assert bot.voice_profile_storage_price_xu(user_id) == bot.VOICE_PROFILE_PRICE_XU == 50


def test_admin_custom_voice_always_zero_xu(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    user_id = 22906
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    first = _make_confirmed_profile(user_id, "Voice one")
    bot.update_user_voice_profile(user_id, int(first["id"]), status="ready", provider_voice_id="provider-custom-one")

    assert bot.voice_profile_storage_price_xu(user_id) == 0
    assert "ADMIN TEST MODE" in bot.voice_clone_quote_text(_make_confirmed_profile(user_id, "Admin voice"), "vi")


def test_voice_adapter_rejects_local_profile_id_for_saved_voice(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    user_id = 22907
    profile = _make_confirmed_profile(user_id, "Local leaked")
    profile_id = int(profile["id"])
    bot.update_user_voice_profile(user_id, profile_id, status="ready", provider_voice_id=str(profile_id))

    assert bot.voice_profile_can_generate_tts(bot.get_user_voice_profile(user_id, profile_id)) is False
    assert bot.voice_core_vault_lookup(user_id, include_inactive=True) == []


def test_saved_voice_tts_uses_provider_voice_id(tmp_path):
    calls = []
    profile = {"id": 12, "display_name": "Voice saved", "status": "ready", "provider_voice_id": "provider-saved-12"}

    async def fake_tts(_text, provider_voice_id="", **_kwargs):
        calls.append(provider_voice_id)
        return {"ok": True, "output_bytes": b"real-audio-bytes"}

    result = asyncio.run(
        voice_clone_pipeline.process_voice_tts(
            user_id=22913,
            text="Xin chao TOAN AAS",
            selected_voice_option=profile,
            product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
            output_path=str(tmp_path / "saved.mp3"),
            execute_tts_func=fake_tts,
        )
    )

    assert result.ok is True
    assert calls == ["provider-saved-12"]
    assert calls[0] != str(profile["id"])
    assert result.audio_bytes > 0


def test_uploaded_unready_voice_not_selectable(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    user_id = 22914
    profile = _make_confirmed_profile(user_id, "Uploaded only")
    bot.update_user_voice_profile(user_id, int(profile["id"]), status="ready", provider_voice_id="")

    assert bot.voice_core_vault_lookup(user_id, source="uploaded", include_inactive=True) == []


def test_no_charge_before_provider_voice_id(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    user_id = 22915
    profile = _make_confirmed_profile(user_id, "No provider")
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not charge")))

    result = bot.finalize_custom_voice_creation(user_id, int(profile["id"]), provider="minimax_fake", provider_voice_id="")

    assert result["ok"] is False
    assert bot.get_user_voice_profile(user_id, int(profile["id"]))["status"] == "pending_confirm"


def test_custom_voice_failure_not_saved_ready(monkeypatch, tmp_path):
    _calls, _message, profile = _run_product_clone(monkeypatch, tmp_path, user_id=22916, tts_status="FAIL", provider_voice_id="")

    assert profile["status"] != "ready"
    assert not profile["provider_voice_id"]


def test_custom_voice_success_saved_provider_voice_id(monkeypatch, tmp_path):
    _calls, _message, profile = _run_product_clone(monkeypatch, tmp_path, user_id=22917, tts_status="FAIL", provider_voice_id="provider-success-voice")

    assert profile["status"] == "ready"
    assert profile["provider_voice_id"] == "provider-success-voice"
    assert bot.voice_profile_metadata(profile)["source_type"] == "custom_clone"


def test_voice_back_from_confirm_returns_to_name_or_sample_step():
    callbacks = _callbacks(bot.voice_clone_quote_keyboard(91, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))

    assert "music_quick|showroom|voice_clone_back_name:91" in callbacks
    assert "menu|main" not in [callback for callback in callbacks if "voice_clone_back" in callback]


def test_voice_back_never_main_menu_unless_menu_main_pressed():
    callbacks = []
    callbacks.extend(_callbacks(bot.voice_clone_quote_keyboard(92, "vi", bot.PRODUCT_CONTEXT_SHOWROOM)))
    callbacks.extend(_callbacks(bot.custom_voice_failed_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM, profile_id=92)))

    back_callbacks = [callback for callback in callbacks if "back" in callback or "retry_context" in callback]
    assert back_callbacks
    assert all(callback != "menu|main" for callback in back_callbacks)


def test_preview_audio_saved_only_when_nonzero(monkeypatch, tmp_path):
    calls, _message, profile = _run_product_clone(monkeypatch, tmp_path, user_id=22918, tts_status="FAIL", provider_voice_id="provider-no-preview")
    metadata = bot.voice_profile_metadata(profile)

    assert "tts" in calls
    assert profile["status"] == "ready"
    assert not str(profile.get("preview_audio_ref") or "").strip()
    assert metadata.get("preview_unavailable_reason") == "provider_clone_succeeded_preview_unavailable"


def test_clone_success_without_preview_still_saves_ready(monkeypatch, tmp_path):
    calls, message, profile = _run_product_clone(monkeypatch, tmp_path, user_id=22908, tts_status="FAIL", provider_voice_id="provider-ready-no-preview")

    assert calls == ["execute_engine", "upload", "clone", "tts"]
    assert profile["status"] == "ready"
    assert profile["provider_voice_id"] == "provider-ready-no-preview"
    assert "Đã tạo voice riêng" in message.outputs[-1]["text"]
    assert "Bản nghe thử chưa tạo được" in message.outputs[-1]["text"]


def test_no_success_message_without_provider_voice_id(monkeypatch, tmp_path):
    _calls, message, profile = _run_product_clone(monkeypatch, tmp_path, user_id=22909, tts_status="FAIL", provider_voice_id="")

    assert profile["status"] != "ready"
    assert not profile["provider_voice_id"]
    assert "Đã tạo voice riêng" not in message.outputs[-1]["text"]
    assert "chưa tạo được voice hợp lệ" in message.outputs[-1]["text"]


def test_failure_keyboard_retry_preserves_profile_context():
    callbacks = _callbacks(bot.custom_voice_failed_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM, profile_id=77))

    assert "music_quick|showroom|voice_clone_retry_context:77" in callbacks
    assert "music_quick|showroom|voice_profiles" in callbacks
    assert "menu|main" in callbacks


def test_voice_flow_back_stack_preserves_origin_context():
    state = bot.set_voice_flow_pending(
        22910,
        "voice_clone_confirm",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        origin="voice_hub",
        current_screen="voice_clone_confirm",
        previous_screen="voice_clone_name",
        return_to="voice_clone_name",
        back_stack=["voice_hub", "voice_clone_intro", "voice_clone_upload", "voice_clone_sample_confirm", "voice_clone_name"],
        voice_flow_step="voice_clone_confirm",
        profile_id=88,
        voice_sample_file_id="sample-file",
        voice_name="Voice ban hang",
        selected_voice_profile_id=88,
    )

    assert state["current_screen"] == "voice_clone_confirm"
    assert state["return_to"] == "voice_clone_name"
    assert state["voice_flow_step"] == "voice_clone_confirm"
    assert bot.decode_voice_back_stack(state["back_stack"])[-1] == "voice_clone_name"
    assert state["voice_sample_file_id"] == "sample-file"
    assert state["voice_name"] == "Voice ban hang"
    assert state["selected_voice_profile_id"] == "88"


def test_voice_vault_back_returns_to_voice_hub(monkeypatch):
    monkeypatch.setattr(bot, "user_voice_profile_count", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(bot, "user_voice_profile_rows", lambda *_args, **_kwargs: [])
    labels = [row for row in bot.voice_vault_keyboard(22911, "vi", bot.PRODUCT_CONTEXT_SHOWROOM).inline_keyboard]
    callbacks = _callbacks(bot.voice_vault_keyboard(22911, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))

    assert "music_quick|showroom|voice_hub" in callbacks
    assert "menu|main" in callbacks
    assert any(button.text == "⬅️ Giọng đọc" for row in labels for button in row)


def test_voice_vault_default_rows_are_balanced(monkeypatch):
    monkeypatch.setattr(bot, "user_voice_profile_count", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(bot, "user_voice_profile_rows", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(bot, "default_tts_voices_distinct", lambda: True)
    rows = [[button.text for button in row] for row in bot.voice_vault_keyboard(22912, "vi", bot.PRODUCT_CONTEXT_SHOWROOM).inline_keyboard]

    assert rows[0] == ["👨 Giọng nam", "👩 Giọng nữ"]
    assert rows[1] == ["🧬 Tạo voice riêng"]
