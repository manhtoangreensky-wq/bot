import asyncio
import json
from types import SimpleNamespace

import bot
from services import minimax_voice_adapter as voice_adapter
from services import provider_gate


class CaptureMessage:
    def __init__(self, user_id=21901):
        self.chat_id = user_id
        self.outputs = []
        self.reply_to_message = None

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.outputs.append({"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs})
        return SimpleNamespace(text=text, reply_markup=reply_markup)


def _init_voice_db(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "voice_p0_19a1.db"))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("VOICE_ASSET_STORAGE_DIR", str(tmp_path / "voice_assets"))
    bot.init_db()


def _make_profile(user_id=21901, display_name="Voice rieng"):
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
    return profile_id


def _labels_by_row(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def test_custom_voice_adapter_fake_returns_provider_voice_id(tmp_path):
    sample = tmp_path / "sample.wav"
    sample.write_bytes(b"fake-sample-audio")

    result = voice_adapter.create_custom_voice_from_sample(
        sample,
        "Voice ban hang",
        21901,
        "idem-1",
        fake=True,
    )

    assert result.ok is True
    assert result.provider_voice_id.startswith("toanaas-custom-21901-")
    assert voice_adapter.validate_provider_voice_id(result.provider_voice_id)


def test_custom_voice_adapter_rejects_missing_provider_voice_id(tmp_path):
    sample = tmp_path / "sample.wav"
    sample.write_bytes(b"fake-sample-audio")

    result = voice_adapter.create_custom_voice_from_sample(
        sample,
        "Voice thieu id",
        21902,
        "idem-2",
        create_func=lambda **_kwargs: {"status": "ok"},
    )

    assert result.ok is False
    assert result.error_code == "missing_provider_voice_id"
    assert "Voice này chưa sẵn sàng" in result.public_message


def test_custom_voice_adapter_safe_error_no_raw_provider_copy(tmp_path):
    sample = tmp_path / "sample.wav"
    sample.write_bytes(b"fake-sample-audio")

    def boom(**_kwargs):
        raise RuntimeError("provider api token traceback leaked")

    result = voice_adapter.create_custom_voice_from_sample(
        sample,
        "Voice loi",
        21903,
        "idem-3",
        create_func=boom,
    )

    assert result.ok is False
    assert result.public_message
    assert not provider_gate.public_copy_has_technical_terms(result.public_message)


def test_voice_vault_menu_male_female_custom_centered(monkeypatch):
    monkeypatch.setattr(bot, "user_voice_profile_count", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(bot, "user_voice_profile_rows", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(bot, "default_tts_voices_distinct", lambda: True)

    rows = _labels_by_row(bot.voice_vault_keyboard(21904, "vi", bot.PRODUCT_CONTEXT_SHOWROOM))

    assert rows[0] == ["👨 Giọng nam", "👩 Giọng nữ"]
    assert rows[1] == ["🧬 Tạo voice riêng"]


def test_custom_voice_finalize_saves_provider_id_to_vault_ready(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    user_id = 21905
    profile_id = _make_profile(user_id, "Voice san sang")
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("first free must not charge")))

    result = bot.finalize_custom_voice_creation(
        user_id,
        profile_id,
        provider="minimax_fake",
        provider_voice_id="provider-custom-21905",
        provider_file_id="file-21905",
        metadata_updates={"sample_metadata": {"duration": 12}, "adapter_fake": True},
    )
    fresh = bot.get_user_voice_profile(user_id, profile_id)
    mapped = bot.voice_core_vault_lookup(user_id, include_inactive=True)

    assert result["ok"] is True
    assert fresh["status"] == "ready"
    assert fresh["provider_voice_id"] == "provider-custom-21905"
    assert mapped[0]["display_name"] == "Voice san sang"
    assert bot.voice_profile_metadata(fresh)["source_type"] == "custom_clone"


def test_custom_voice_missing_provider_id_not_selectable(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    user_id = 21906
    profile_id = _make_profile(user_id, "Voice local only")
    bot.update_user_voice_profile(user_id, profile_id, status="ready", provider_voice_id="")

    assert bot.voice_profile_can_generate_tts(bot.get_user_voice_profile(user_id, profile_id)) is False
    assert bot.voice_core_vault_lookup(user_id, include_inactive=True) == []


def test_custom_voice_second_success_charged_after_provider_success(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    user_id = 21907
    first_id = _make_profile(user_id, "Voice one")
    bot.update_user_voice_profile(user_id, first_id, status="ready", provider_voice_id="provider-custom-first")
    second_id = _make_profile(user_id, "Voice two")
    charges = []
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(
        bot,
        "spend_fixed_credit_info",
        lambda user, amount, event_type, note="", apply_member_discount_flag=True: charges.append(
            {"user": user, "amount": amount, "event_type": event_type}
        ) or {"ok": True, "final_cost": amount},
    )

    result = bot.finalize_custom_voice_creation(
        user_id,
        second_id,
        provider="minimax_fake",
        provider_voice_id="provider-custom-second",
    )
    fresh = bot.get_user_voice_profile(user_id, second_id)
    metadata = bot.voice_profile_metadata(fresh)

    assert result["ok"] is True
    assert charges == [{"user": user_id, "amount": bot.VOICE_PROFILE_PRICE_XU, "event_type": "voice_clone_create"}]
    assert fresh["status"] == "ready"
    assert fresh["provider_voice_id"] == "provider-custom-second"
    assert metadata["charge_status"] == "paid_custom_voice_created"


def test_custom_voice_provider_fail_no_charge(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    user_id = 21908
    profile_id = _make_profile(user_id, "Voice fail")
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("missing provider id must not charge")))

    result = bot.finalize_custom_voice_creation(
        user_id,
        profile_id,
        provider="minimax_fake",
        provider_voice_id="",
    )
    fresh = bot.get_user_voice_profile(user_id, profile_id)

    assert result["ok"] is False
    assert fresh["provider_voice_id"] == ""
    assert fresh["status"] == "pending_confirm"


def test_custom_voice_admin_no_charge(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    user_id = 21909
    first_id = _make_profile(user_id, "Voice one")
    bot.update_user_voice_profile(user_id, first_id, status="ready", provider_voice_id="provider-custom-first")
    second_id = _make_profile(user_id, "Voice admin")
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("admin test must not charge")))

    result = bot.finalize_custom_voice_creation(
        user_id,
        second_id,
        provider="minimax_fake",
        provider_voice_id="provider-custom-admin",
    )
    metadata = bot.voice_profile_metadata(bot.get_user_voice_profile(user_id, second_id))

    assert result["ok"] is True
    assert metadata["charged_xu"] == 0
    assert metadata["charge_status"] == "admin_custom_voice_created_no_charge"


def test_tool_test_custom_voice_flow_fake_saves_voice(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    user_id = 21910

    async def allow_guard(*_args, **_kwargs):
        return True

    monkeypatch.setattr(bot, "p0_18a_admin_guard", allow_guard)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    message = CaptureMessage(user_id)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=user_id), message=message)
    context = SimpleNamespace(args=["--fake"])

    asyncio.run(bot.cmd_tool_test_custom_voice_flow(update, context))

    assert "Result: <code>PASS</code>" in message.outputs[-1]["text"]
    assert bot.voice_core_vault_lookup(user_id, include_inactive=True)


def test_tool_test_custom_voice_provider_fake(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    user_id = 21911

    async def allow_guard(*_args, **_kwargs):
        return True

    monkeypatch.setattr(bot, "p0_18a_admin_guard", allow_guard)
    message = CaptureMessage(user_id)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=user_id), message=message)
    context = SimpleNamespace(args=["--fake"])

    asyncio.run(bot.cmd_tool_test_custom_voice_provider(update, context))

    assert "Provider voice id:" in message.outputs[-1]["text"]
    assert "Result: <code>PASS</code>" in message.outputs[-1]["text"]


def test_tool_test_custom_voice_provider_real_requires_confirm(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    user_id = 21912

    async def allow_guard(*_args, **_kwargs):
        return True

    monkeypatch.setattr(bot, "p0_18a_admin_guard", allow_guard)
    message = CaptureMessage(user_id)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=user_id), message=message)
    context = SimpleNamespace(args=["--real"])

    asyncio.run(bot.cmd_tool_test_custom_voice_provider(update, context))

    assert "--confirm-provider-cost" in message.outputs[-1]["text"]
