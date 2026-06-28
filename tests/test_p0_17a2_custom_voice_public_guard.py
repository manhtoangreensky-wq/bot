import asyncio
import inspect
import json
from types import SimpleNamespace

import bot


PUBLIC_FORBIDDEN_TERMS = [
    "selected_adapter",
    "route_errors",
    "error_code",
    "provider_status",
    "CLONE_PERMISSION_FORBIDDEN",
    "clone_permission_forbidden",
    "payload_fields",
    "http_status",
    "operation",
    "adapter",
    "user forbidden",
    "api/",
    "Authorization",
    "Bearer",
    "API_KEY",
    "TOKEN",
    "SECRET",
]


class CaptureMessage:
    def __init__(self, user_id=19001):
        self.chat_id = user_id
        self.outputs = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.outputs.append({"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs})
        return SimpleNamespace(text=text, reply_markup=reply_markup)


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _init_voice_db(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "voice_p0_17a2.db"))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("VOICE_ASSET_STORAGE_DIR", str(tmp_path / "voice_assets"))
    bot.init_db()


def _clone_blocked_readiness():
    return {
        "ready": True,
        "public_enabled": False,
        "provider_permission_blocked": True,
        "provider_permission_blocker": "clone_permission_forbidden",
        "routes": ["key4u_minimax"],
        "shopaikey_configured": False,
        "key4u_configured": True,
        "tts_smoke": "PASS",
        "clone_smoke": "BLOCKED",
    }


def _route_ready_readiness(active_route="shopaikey_minimax"):
    return {
        "ready": True,
        "public_enabled": True,
        "provider_permission_blocked": False,
        "provider_permission_blocker": "",
        "routes": ["shopaikey_minimax", "key4u_minimax"],
        "shopaikey_configured": True,
        "key4u_configured": True,
        "shopaikey_clone_readiness": "UNKNOWN",
        "key4u_clone_readiness": "UNKNOWN",
        "active_custom_voice_route": active_route,
        "tts_smoke": "PASS",
        "clone_smoke": "PASS",
    }


def _make_confirmed_profile(monkeypatch, tmp_path, user_id=19001):
    _init_voice_db(monkeypatch, tmp_path)
    profile_id = bot.save_user_voice_profile(user_id, "telegram-sample-file", display_name="Voice riêng")
    profile = bot.get_user_voice_profile(user_id, profile_id)
    metadata = bot.voice_profile_metadata(profile)
    metadata["confirmation_sample_text"] = bot.VOICE_CLONE_CONFIRMATION_SAMPLE_TEXT
    bot.update_user_voice_profile(
        user_id,
        profile_id,
        display_name="Voice riêng",
        metadata_json=json.dumps(metadata, ensure_ascii=False),
    )
    return bot.get_user_voice_profile(user_id, profile_id)


def _block_readiness(monkeypatch):
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", _clone_blocked_readiness)


def _forbid_provider_and_charge(monkeypatch):
    async def forbidden_async(*_args, **_kwargs):
        raise AssertionError("blocked custom voice flow must not call provider")

    def forbidden_sync(*_args, **_kwargs):
        raise AssertionError("blocked custom voice flow must not charge")

    monkeypatch.setattr(bot, "key4u_minimax_upload_voice_sample", forbidden_async)
    monkeypatch.setattr(bot, "key4u_minimax_voice_clone", forbidden_async)
    monkeypatch.setattr(bot, "key4u_minimax_tts_bytes", forbidden_async)
    monkeypatch.setattr(bot, "shopaikey_minimax_upload_voice_sample", forbidden_async)
    monkeypatch.setattr(bot, "shopaikey_minimax_voice_clone", forbidden_async)
    monkeypatch.setattr(bot, "shopaikey_minimax_tts_bytes", forbidden_async)
    monkeypatch.setattr(bot, "execute_engine", forbidden_async)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", forbidden_sync)


class FakeTelegramFile:
    async def download_as_bytearray(self):
        return bytearray(b"sample-audio")


class CaptureBot:
    async def get_file(self, _file_id):
        return FakeTelegramFile()

    async def send_audio(self, chat_id=None, audio=None, title=None, caption=None, **kwargs):
        return SimpleNamespace(audio=SimpleNamespace(file_id=f"tg-audio-{chat_id}"))


def _run_blocked_flow(monkeypatch, tmp_path, user_id=19001, admin=False):
    _block_readiness(monkeypatch)
    _forbid_provider_and_charge(monkeypatch)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: bool(admin))
    monkeypatch.setattr(bot, "preview_quota_guard", lambda *_args, **_kwargs: {"allowed": True})
    monkeypatch.setattr(bot, "voice_preview_guard", lambda *_args, **_kwargs: {"ok": True, "preview_key": "p0-17a2-blocked", "preview_text": "Xin chào từ TOAN AAS."})
    monkeypatch.setattr(bot, "acquire_voice_preview_generation", lambda _uid, _pid, _guard: (True, None))
    profile = _make_confirmed_profile(monkeypatch, tmp_path, user_id)
    message = CaptureMessage(user_id)
    query = SimpleNamespace(message=message)
    context = SimpleNamespace(bot=CaptureBot())
    asyncio.run(bot.create_minimax_voice_profile_preview(query, context, user_id, profile, "vi"))
    return message, bot.get_user_voice_profile(user_id, int(profile["id"]))


def _run_routed_flow(
    monkeypatch,
    tmp_path,
    *,
    user_id=19101,
    admin=False,
    active_route="shopaikey_minimax",
    shopaikey_clone_status="PASS",
    key4u_clone_status="PASS",
):
    calls = []
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: _route_ready_readiness(active_route))
    monkeypatch.setattr(bot, "voice_clone_last_forbidden_provider", lambda: "")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: bool(admin))
    monkeypatch.setattr(bot, "preview_quota_guard", lambda *_args, **_kwargs: {"allowed": True, "reason": "ok", "product_type": "voice_ai", "quota": {}})
    monkeypatch.setattr(bot, "consume_preview_quota", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(bot, "voice_preview_guard", lambda *_args, **_kwargs: {"ok": True, "preview_key": "p0-17a2", "preview_text": "Xin chào từ TOAN AAS."})
    monkeypatch.setattr(bot, "acquire_voice_preview_generation", lambda _uid, _pid, _guard: (True, None))

    async def fake_cap(audio, _seconds):
        return bytes(audio or b""), "ok"

    monkeypatch.setattr(bot, "cap_voice_preview_audio_bytes", fake_cap)

    async def fake_engine(*_args, **_kwargs):
        calls.append("execute_engine")
        return {"ok": True}

    def forbidden_charge(*_args, **_kwargs):
        raise AssertionError("route fallback tests must not charge Xu")

    monkeypatch.setattr(bot, "execute_engine", fake_engine)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", forbidden_charge)

    async def shop_upload(*_args, **_kwargs):
        calls.append("shopaikey_upload")
        return "PASS", "shop-file", "ok", 200

    async def shop_clone(*_args, **_kwargs):
        calls.append("shopaikey_clone")
        if shopaikey_clone_status == "PASS":
            return "PASS", {"voice_id": "shop-voice"}, "ok", 200
        return shopaikey_clone_status, {}, "voice clone user forbidden", 403

    async def shop_tts(*_args, **_kwargs):
        calls.append("shopaikey_tts")
        return "PASS", b"shop-preview-audio", "ok", 200

    async def key_upload(*_args, **_kwargs):
        calls.append("key4u_upload")
        return "PASS", "key-file", "ok", 200

    async def key_clone(*_args, **_kwargs):
        calls.append("key4u_clone")
        if key4u_clone_status == "PASS":
            return "PASS", {"voice_id": "key-voice"}, "ok", 200
        return key4u_clone_status, {}, "voice clone user forbidden", 403

    async def key_tts(*_args, **_kwargs):
        calls.append("key4u_tts")
        return "PASS", b"key-preview-audio", "ok", 200

    monkeypatch.setattr(bot, "shopaikey_minimax_upload_voice_sample", shop_upload)
    monkeypatch.setattr(bot, "shopaikey_minimax_voice_clone", shop_clone)
    monkeypatch.setattr(bot, "shopaikey_minimax_tts_bytes", shop_tts)
    monkeypatch.setattr(bot, "key4u_minimax_upload_voice_sample", key_upload)
    monkeypatch.setattr(bot, "key4u_minimax_voice_clone", key_clone)
    monkeypatch.setattr(bot, "key4u_minimax_tts_bytes", key_tts)

    profile = _make_confirmed_profile(monkeypatch, tmp_path, user_id)
    message = CaptureMessage(user_id)
    query = SimpleNamespace(message=message)
    context = SimpleNamespace(bot=CaptureBot())
    asyncio.run(bot.create_minimax_voice_profile_preview(query, context, user_id, profile, "vi"))
    return calls, message, bot.get_user_voice_profile(user_id, int(profile["id"]))


def test_custom_voice_block_public_clean_message():
    text = bot.voice_clone_permission_forbidden_public_text("vi")
    assert "Tạo voice riêng đang tạm khóa" in text
    assert "chưa xử lý và chưa trừ Xu" in text
    assert "giọng nam/nữ mặc định" in text


def test_custom_voice_block_public_no_admin_diagnostic():
    text = bot.voice_clone_permission_forbidden_public_text("vi")
    for term in PUBLIC_FORBIDDEN_TERMS:
        assert term not in text


def test_custom_voice_block_public_no_clone_permission_forbidden_text(monkeypatch, tmp_path):
    message, _profile = _run_blocked_flow(monkeypatch, tmp_path)
    text = message.outputs[-1]["text"]
    assert "clone_permission_forbidden" not in text
    assert "CLONE_PERMISSION_FORBIDDEN" not in text


def test_custom_voice_block_public_no_route_errors(monkeypatch, tmp_path):
    message, _profile = _run_blocked_flow(monkeypatch, tmp_path)
    text = message.outputs[-1]["text"]
    assert "route_errors" not in text
    assert "selected_adapter" not in text
    assert "provider_status" not in text


def test_custom_voice_block_public_fallback_buttons():
    markup = bot.voice_clone_permission_forbidden_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM)
    labels = _labels(markup)
    callbacks = _callbacks(markup)
    assert "🎙 Dùng giọng nữ mặc định" in labels
    assert "🎙 Dùng giọng nam mặc định" in labels
    assert "🔁 Thử lại sau" in labels
    assert "⬅️ Kho voice" in labels
    assert "🏠 Menu chính" in labels
    assert "music_quick|showroom|voice_default_female" in callbacks
    assert "music_quick|showroom|voice_default_male" in callbacks
    assert "music_quick|showroom|voice_clone" in callbacks
    assert "music_quick|showroom|voice_profiles" in callbacks


def test_custom_voice_block_no_charge(monkeypatch, tmp_path):
    message, _profile = _run_blocked_flow(monkeypatch, tmp_path)
    assert message.outputs
    assert "chưa trừ Xu" in message.outputs[-1]["text"]


def test_custom_voice_block_does_not_consume_first_free(monkeypatch, tmp_path):
    user_id = 19002
    _message, profile = _run_blocked_flow(monkeypatch, tmp_path, user_id=user_id)
    assert profile["status"] == "failed_clone_permission_forbidden"
    assert bot.successful_custom_voice_creation_count(user_id) == 0
    assert bot.voice_profile_storage_price_xu(user_id) == 0


def test_custom_voice_menu_admin_user_still_customer_clean(monkeypatch, tmp_path):
    monkeypatch.setattr(
        bot,
        "voice_clone_admin_preview_failure_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("admin diagnostic must not be sent from public menu flow")),
    )
    message, _profile = _run_blocked_flow(monkeypatch, tmp_path, user_id=19003, admin=True)
    output = message.outputs[-1]
    assert "TOAN AAS chưa tạo được voice" in output["text"]
    assert "ADMIN TEST MODE" not in output["text"]
    assert "public gate bypassed" not in output["text"]
    assert "route_errors" not in output["text"]
    assert "provider_voice_id" not in output["text"]
    assert "TOKEN" not in output["text"]
    assert "traceback" not in output["text"].lower()


def test_voice_engine_status_admin_can_show_sanitized_clone_blocker(monkeypatch):
    _block_readiness(monkeypatch)
    lines = "\n".join(bot.voice_engine_status_lines())
    assert "clone_permission_forbidden" in lines
    assert "Bearer live" not in lines
    assert "API_KEY=" not in lines


def test_voice_admin_diagnostic_no_secret(monkeypatch):
    _block_readiness(monkeypatch)
    text = bot.voice_clone_admin_preview_failure_text(
        _clone_blocked_readiness(),
        provider_name="key4u_minimax",
        route_errors=[{"route": "clone", "error": "secret=sk-live TOKEN=hidden"}],
        error="clone_permission_forbidden",
    )
    assert "sk-live" not in text
    assert "TOKEN=hidden" not in text


def test_voice_admin_diagnostic_not_sent_from_public_flow(monkeypatch, tmp_path):
    monkeypatch.setattr(
        bot,
        "voice_clone_admin_preview_failure_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("admin diagnostic must stay out of public flow")),
    )
    message, _profile = _run_blocked_flow(monkeypatch, tmp_path, user_id=19004, admin=True)
    assert "TOAN AAS chưa tạo được voice" in message.outputs[-1]["text"]
    assert "ADMIN TEST MODE" not in message.outputs[-1]["text"]
    assert "public gate bypassed" not in message.outputs[-1]["text"]


def test_custom_voice_block_before_provider_when_clone_readiness_blocked(monkeypatch, tmp_path):
    message, _profile = _run_blocked_flow(monkeypatch, tmp_path)
    assert message.outputs[-1]["text"].startswith("⚙️ TOAN AAS chưa tạo được voice")


def test_custom_voice_block_no_provider_call(monkeypatch, tmp_path):
    _message, profile = _run_blocked_flow(monkeypatch, tmp_path)
    assert not str(profile.get("provider_voice_id") or "").strip()


def test_custom_voice_block_no_first_free_consumed(monkeypatch, tmp_path):
    user_id = 19005
    _message, _profile = _run_blocked_flow(monkeypatch, tmp_path, user_id=user_id)
    assert bot.voice_profile_storage_price_xu(user_id) == 0


def test_custom_voice_first_creation_free_preserved(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    assert bot.voice_profile_storage_price_xu(19006) == 0


def test_custom_voice_second_creation_50_preserved(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    user_id = 19007
    profile_id = bot.save_user_voice_profile(user_id, "sample-file", display_name="Voice ok")
    bot.update_user_voice_profile(user_id, profile_id, provider_voice_id="voice-ok", status="active")
    assert bot.voice_profile_storage_price_xu(user_id) == bot.VOICE_PROFILE_PRICE_XU == 50


def test_custom_voice_usage_0_1_xu_per_char_preserved():
    assert bot.custom_voice_usage_price_xu("a" * 11) == 2
    assert bot.custom_voice_usage_price_xu("a" * 50) == 5


def test_custom_voice_usage_min_rules_preserved():
    assert bot.custom_voice_usage_text_too_short("a" * 10) is True
    assert bot.custom_voice_usage_text_too_short("a" * 11) is False
    assert bot.custom_voice_usage_output_too_short("abcdefghijk", "normal", b"audio") is True


def test_default_voice_free_still_works():
    assert "miễn phí" in bot.default_voice_confirm_text("Xin chào", "female", "vi").lower()
    assert "miễn phí" in bot.default_voice_confirm_text("Xin chào", "male", "vi").lower()


def test_default_voice_no_preview_quota_still_removed():
    source = inspect.getsource(bot.send_default_free_tts_result)
    assert "preview_quota_guard" not in source
    assert "consume_preview_quota" not in source


def test_default_voice_no_charge_still_true():
    assert "spend_fixed_credit_info" not in inspect.getsource(bot.send_default_free_tts_result)


def test_custom_voice_block_no_success_profile(monkeypatch, tmp_path):
    user_id = 19008
    _message, profile = _run_blocked_flow(monkeypatch, tmp_path, user_id=user_id)
    assert profile["status"] != "ready"
    assert profile["status"] != "active"
    assert bot.successful_custom_voice_creation_count(user_id) == 0


def test_custom_voice_block_no_paid_metadata(monkeypatch, tmp_path):
    _message, profile = _run_blocked_flow(monkeypatch, tmp_path, user_id=19009)
    metadata = bot.voice_profile_metadata(profile)
    assert "charged_xu" not in metadata
    assert "charge_status" not in metadata
    assert "price_xu" not in metadata
    assert "final_cost_xu" not in metadata


def test_custom_voice_block_no_first_free_applied(monkeypatch, tmp_path):
    _message, profile = _run_blocked_flow(monkeypatch, tmp_path, user_id=19010)
    metadata = bot.voice_profile_metadata(profile)
    assert "first_free_applied" not in metadata
    assert metadata.get("activation_status") == "failed_clone_permission_forbidden"


def test_voice_asset_detail_no_raw_clone_diagnostic(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    row = bot.create_voice_asset_record(
        19011,
        "voice_clone_preview",
        bot.PRODUCT_CONTEXT_SHOWROOM,
        "custom_clone",
        metadata={
            "selected_adapter": "key4u",
            "route_errors": ["clone forbidden"],
            "error_code": "CLONE_PERMISSION_FORBIDDEN",
            "provider_status": "403",
            "payload_fields": ["voice_id"],
            "http_status": 403,
            "operation": "clone",
            "provider_voice_id": "hidden",
            "safe_key": "shown",
        },
    )
    message = CaptureMessage(bot.ADMIN_ID)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=bot.ADMIN_ID), message=message)
    context = SimpleNamespace(args=[row["voice_asset_id"]])
    asyncio.run(bot.cmd_voice_asset_detail(update, context))
    text = message.outputs[-1]["text"]
    assert "safe_key" in text
    for term in [
        "selected_adapter",
        "route_errors",
        "error_code",
        "provider_status",
        "payload_fields",
        "http_status",
        "operation",
        "provider_voice_id",
    ]:
        assert term not in text


def test_custom_voice_routes_include_shopaikey_minimax(monkeypatch):
    monkeypatch.setattr(bot, "voice_clone_last_forbidden_provider", lambda: "")
    names = bot.voice_clone_provider_route_names(_route_ready_readiness())
    assert "shopaikey_minimax" in names


def test_custom_voice_routes_include_key4u_minimax(monkeypatch):
    monkeypatch.setattr(bot, "voice_clone_last_forbidden_provider", lambda: "")
    names = bot.voice_clone_provider_route_names(_route_ready_readiness())
    assert "key4u_minimax" in names


def test_custom_voice_fallback_from_shopaikey_to_key4u_when_blocked(monkeypatch, tmp_path):
    calls, _message, profile = _run_routed_flow(
        monkeypatch,
        tmp_path,
        user_id=19102,
        active_route="shopaikey_minimax",
        shopaikey_clone_status="CLONE_PERMISSION_FORBIDDEN",
        key4u_clone_status="PASS",
    )
    assert calls.index("shopaikey_clone") < calls.index("key4u_clone")
    assert "key4u_tts" in calls
    assert profile["status"] == "ready"
    assert profile["provider"] == "key4u_minimax"


def test_custom_voice_keeps_shopaikey_first_when_key4u_active(monkeypatch, tmp_path):
    calls, _message, profile = _run_routed_flow(
        monkeypatch,
        tmp_path,
        user_id=19103,
        active_route="key4u_minimax",
        shopaikey_clone_status="PASS",
        key4u_clone_status="CLONE_PERMISSION_FORBIDDEN",
    )
    assert calls.index("shopaikey_clone") < calls.index("shopaikey_tts")
    assert "key4u_clone" not in calls
    assert "shopaikey_tts" in calls
    assert profile["status"] == "ready"
    assert profile["provider"] == "shopaikey_minimax"


def test_custom_voice_both_providers_blocked_public_clean_message(monkeypatch, tmp_path):
    _calls, message, profile = _run_routed_flow(
        monkeypatch,
        tmp_path,
        user_id=19104,
        active_route="shopaikey_minimax",
        shopaikey_clone_status="CLONE_PERMISSION_FORBIDDEN",
        key4u_clone_status="CLONE_PERMISSION_FORBIDDEN",
    )
    text = message.outputs[-1]["text"]
    assert "TOAN AAS chưa tạo được voice" in text
    assert "chưa trừ Xu" in text
    assert profile["status"] == "failed_clone_permission_forbidden"


def test_custom_voice_public_no_provider_route_leak(monkeypatch, tmp_path):
    _calls, message, _profile = _run_routed_flow(
        monkeypatch,
        tmp_path,
        user_id=19105,
        active_route="shopaikey_minimax",
        shopaikey_clone_status="CLONE_PERMISSION_FORBIDDEN",
        key4u_clone_status="CLONE_PERMISSION_FORBIDDEN",
    )
    text = message.outputs[-1]["text"]
    for term in PUBLIC_FORBIDDEN_TERMS + ["shopaikey_minimax", "key4u_minimax", "/tts/minimax", "https://"]:
        assert term not in text


def test_voice_engine_status_shows_sanitized_shopaikey_key4u_routes(monkeypatch):
    readiness = _route_ready_readiness("shopaikey_minimax")
    readiness.update({
        "shopaikey_clone_readiness": "UNKNOWN",
        "key4u_clone_readiness": "BLOCKED",
        "provider_permission_blocker": "clone_permission_forbidden",
        "blocked_provider": "key4u_minimax",
    })
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: readiness)
    lines = "\n".join(bot.voice_engine_status_lines())
    assert "ShopAIKey MiniMax configured: <code>YES</code>" in lines
    assert "Key4U MiniMax configured: <code>YES</code>" in lines
    assert "ShopAIKey clone readiness: <code>UNKNOWN</code>" in lines
    assert "Key4U clone readiness: <code>BLOCKED</code>" in lines
    assert "Active custom voice route: <code>shopaikey_minimax</code>" in lines


def test_voice_engine_status_no_secret(monkeypatch):
    readiness = _route_ready_readiness("key4u_minimax")
    readiness["provider_permission_blocker"] = "clone_permission_forbidden TOKEN=sk-live"
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: readiness)
    lines = "\n".join(bot.voice_engine_status_lines())
    assert "sk-live" not in lines
    assert "TOKEN=" not in lines
    assert "API_KEY=" not in lines


def test_custom_voice_provider_block_no_charge(monkeypatch, tmp_path):
    _calls, message, _profile = _run_routed_flow(
        monkeypatch,
        tmp_path,
        user_id=19106,
        shopaikey_clone_status="CLONE_PERMISSION_FORBIDDEN",
        key4u_clone_status="CLONE_PERMISSION_FORBIDDEN",
    )
    assert "chưa trừ Xu" in message.outputs[-1]["text"]


def test_custom_voice_provider_block_no_first_free_consumed(monkeypatch, tmp_path):
    user_id = 19107
    _calls, _message, _profile = _run_routed_flow(
        monkeypatch,
        tmp_path,
        user_id=user_id,
        shopaikey_clone_status="CLONE_PERMISSION_FORBIDDEN",
        key4u_clone_status="CLONE_PERMISSION_FORBIDDEN",
    )
    assert bot.successful_custom_voice_creation_count(user_id) == 0
    assert bot.voice_profile_storage_price_xu(user_id) == 0
