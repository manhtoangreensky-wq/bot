import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class CaptureMessage:
    def __init__(self, user_id=17001, text=""):
        self.chat_id = user_id
        self.text = text
        self.outputs = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.outputs.append({"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs})
        return SimpleNamespace(text=text, reply_markup=reply_markup)

    async def reply_audio(self, audio=None, filename=None, caption=None, **kwargs):
        self.outputs.append({"audio": audio, "filename": filename, "caption": str(caption or ""), **kwargs})
        return SimpleNamespace(audio=SimpleNamespace(file_id="tg-preview-file-id"))

    async def reply_document(self, document=None, filename=None, caption=None, **kwargs):
        self.outputs.append({"document": document, "filename": filename, "caption": str(caption or ""), **kwargs})
        return SimpleNamespace(document=SimpleNamespace(file_id="tg-preview-doc-id"))


def _init_voice_db(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "voice_assets.db"))
    monkeypatch.setattr(bot, "DB_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("VOICE_ASSET_STORAGE_DIR", str(tmp_path / "voice_assets"))
    bot.init_db()


def test_voice_showroom_entry_exists():
    tools = bot.music_tools_keyboard("vi", "menu|main")
    labels = _labels(tools)
    callbacks = _callbacks(tools)
    assert "🎙 Giọng đọc" in labels
    assert "music_quick|showroom|voice_hub" in callbacks
    hub_labels = _labels(bot.voice_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert "✍️ Văn bản thành giọng nói" in hub_labels
    assert "📂 Kho voice" in hub_labels
    assert "🎙 Tạo voice riêng" in hub_labels


def test_voice_default_female_path():
    labels = _labels(bot.voice_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    callbacks = _callbacks(bot.voice_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert any("Giọng nữ" in label for label in labels)
    assert "music_quick|showroom|voice_default_female" in callbacks
    assert bot.get_tts_voice_id("default_female") == bot.default_tts_voice_id("female")


def test_voice_default_male_path():
    labels = _labels(bot.voice_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    callbacks = _callbacks(bot.voice_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert any("Giọng nam" in label for label in labels)
    assert "music_quick|showroom|voice_default_male" in callbacks
    assert bot.get_tts_voice_id("default_male") == bot.default_tts_voice_id("male")


def test_voice_text_input_path():
    text = bot.voice_text_input_text("vi")
    labels = _labels(bot.voice_tts_choice_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert "Bạn nhập nội dung muốn tạo giọng đọc" in text
    assert any("Giọng nữ" in label for label in labels)
    assert any("Giọng nam" in label for label in labels)
    assert "✏️ Sửa nội dung" in labels


def test_voice_addon_context_preserves_video_session_if_touched(monkeypatch):
    user_id = 17002
    bot.set_video_finalization_state(user_id, {
        "source": "self_shot",
        "source_file_id": "video-source-file",
        "selected_video_tier": "basic",
    })
    session_id = bot.voice_asset_video_session_id(user_id, bot.PRODUCT_CONTEXT_VIDEO_ADDON)
    assert session_id == "video-source-file"
    source = inspect.getsource(bot.start_video_voice_script_step)
    assert "render_video" not in source
    assert "multiscene" not in source.lower()


def test_voice_admin_status_no_secret_leak(monkeypatch):
    monkeypatch.setattr(bot, "voice_provider_dependency_status", lambda: {
        "edge_tts": {"status": "available"},
        "fish_audio": {"status": "missing"},
        "elevenlabs": {"status": "missing"},
        "deepgram": {"status": "missing"},
        "deepl": {"status": "missing"},
        "auphonic": {"status": "missing"},
        "gemini": {"status": "missing"},
        "heygen": {"status": "missing"},
        "cutout": {"status": "missing"},
        "freesound": {"status": "missing"},
        "jamendo": {"status": "missing"},
    })
    lines = "\n".join(bot.voice_engine_status_lines())
    assert "Default TTS configured" in lines
    assert "Default TTS mode" in lines
    assert "Custom voice preview quota gate active" in lines
    assert "/voice_tts_admin_test --confirm-paid" in lines
    assert "sk-live" not in lines
    assert "Bearer live" not in lines
    assert "API_KEY=" not in lines


def test_voice_preview_duration_6s():
    assert bot.voice_preview_seconds() == 6
    assert bot.preview_duration_seconds("voice_ai") == 6
    assert "Nghe thử 6 giây" in bot.voice_preview_notice_text("vi")


def test_voice_preview_uses_global_quota_voice_ai():
    source = inspect.getsource(bot.create_minimax_voice_profile_preview)
    assert 'preview_quota_guard(user_id, "voice_ai")' in source
    assert 'consume_preview_quota(user_id, "voice_ai"' in source


def test_voice_preview_requires_silver(monkeypatch):
    monkeypatch.setattr(bot, "get_member_profile", lambda _user_id: {"tier": "newbie"})
    decision = bot.preview_quota_guard("public-user", "voice_ai")
    assert decision["allowed"] is False
    assert decision["reason"] == "tier"


def test_voice_preview_blocks_before_provider_when_quota_exhausted(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "preview_quota_guard", lambda *_args, **_kwargs: {
        "allowed": False,
        "reason": "quota",
        "product_type": "voice_ai",
        "quota": {},
    })

    async def forbidden_engine(*_args, **_kwargs):
        raise AssertionError("provider executor must not run when preview quota blocks")

    monkeypatch.setattr(bot, "execute_engine", forbidden_engine)
    message = CaptureMessage()
    ok = asyncio.run(bot.send_standalone_tts_result(
        message,
        17003,
        "Xin chào TOAN AAS",
        "giọng nâng cao",
        voice_id="style_voice",
        lang="vi",
    ))
    assert ok is False
    assert "chưa gọi provider" in message.outputs[-1]["text"]
    assert bot.voice_asset_status_counts()["blocked"] == 1


def test_voice_preview_notice_mentions_6s_and_15_days():
    text = bot.voice_preview_notice_text("vi")
    assert "6 giây" in text
    assert "1 lần trong 15 ngày" in text
    assert "1 lần/ngày" not in text


def test_voice_preview_no_full_delivery_before_confirm(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "preview_quota_guard", lambda *_args, **_kwargs: {"allowed": True, "reason": "ok", "product_type": "voice_ai", "quota": {}})
    monkeypatch.setattr(bot, "consume_preview_quota", lambda *_args, **_kwargs: {"ok": True})

    async def fake_engine(*_args, **_kwargs):
        return {"ok": True, "output_bytes": b"full-audio-bytes", "detail": "ok"}

    async def fake_cap(audio_bytes, seconds=6):
        assert audio_bytes == b"full-audio-bytes"
        assert seconds == 6
        return b"preview-6s", "ok"

    monkeypatch.setattr(bot, "execute_engine", fake_engine)
    monkeypatch.setattr(bot, "cap_voice_preview_audio_bytes", fake_cap)
    message = CaptureMessage()
    ok = asyncio.run(bot.send_standalone_tts_result(
        message,
        17004,
        "Xin chào TOAN AAS",
        "giọng nâng cao",
        voice_id="style_voice",
        lang="vi",
    ))
    assert ok is True
    audio_outputs = [item for item in message.outputs if item.get("filename")]
    assert audio_outputs[-1]["filename"] == "toan_aas_voice_preview.mp3"
    assert "Bản đầy đủ đã được lưu làm asset" in audio_outputs[-1]["caption"]
    rows = bot.list_voice_asset_records(status="preview_sent")
    assert rows and rows[0]["output_bytes"] == len(b"full-audio-bytes")


def test_clone_permission_forbidden_public_clean_message():
    text = bot.voice_clone_permission_forbidden_public_text("vi")
    assert "Tạo voice riêng đang tạm giới hạn" in text
    assert "tính năng tạo/clone voice riêng chưa sẵn sàng trên nhà cung cấp" in text
    assert "giọng nam/nữ mặc định miễn phí" in text
    assert "user forbidden" not in text.lower()


def test_clone_permission_forbidden_admin_sanitized(monkeypatch):
    monkeypatch.setattr(bot, "get_minimax_voice_clone_readiness", lambda: {
        "ready": True,
        "public_enabled": False,
        "provider_permission_blocked": True,
        "provider_permission_blocker": "clone_permission_forbidden",
        "routes": ["key4u_minimax"],
    })
    lines = "\n".join(bot.voice_engine_status_lines())
    assert "clone_permission_forbidden" in lines
    assert "sk-live" not in lines
    assert "Bearer live" not in lines
    assert "API_KEY=" not in lines


def test_clone_failure_offers_default_voice_fallback():
    labels = _labels(bot.voice_clone_permission_forbidden_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    assert "🎙 Dùng giọng nữ mặc định miễn phí" in labels
    assert "🎙 Dùng giọng nam mặc định miễn phí" in labels
    assert "⬅️ Kho voice" in labels
    assert "🏠 Menu chính" in labels


def test_clone_no_secret_leak():
    text = bot.voice_clone_permission_forbidden_public_text("vi")
    assert "API_KEY" not in text
    assert "TOKEN" not in text
    assert "SECRET" not in text


def test_clone_no_charge_before_confirm():
    source = inspect.getsource(bot.create_minimax_voice_profile_preview)
    forbidden_block = source[source.index('if readiness.get("provider_permission_blocked") and not route_attempts:'):source.index("if not voice_clone_access_allowed")]
    assert "spend_fixed_credit_info" not in forbidden_block


def test_voice_asset_created_for_preview(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    row = bot.create_voice_asset_record(
        17005,
        "voice_tts_preview",
        bot.PRODUCT_CONTEXT_SHOWROOM,
        "default_female",
        text="Xin chào",
        duration_seconds=6,
        output_bytes=123,
        status="preview_sent",
    )
    assert row["voice_asset_id"]
    stored = bot.get_voice_asset_record(row["voice_asset_id"])
    assert stored["voice_kind"] == "default_female"
    assert stored["status"] == "preview_sent"


def test_voice_asset_status_counts(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    bot.create_voice_asset_record(17006, "voice_tts_preview", bot.PRODUCT_CONTEXT_SHOWROOM, "default_female", status="preview_sent")
    bot.create_voice_asset_record(17006, "voice_saved_tts", bot.PRODUCT_CONTEXT_SHOWROOM, "custom_clone", status="used")
    counts = bot.voice_asset_status_counts()
    assert counts["preview_sent"] == 1
    assert counts["used"] == 1


def test_voice_asset_detail_no_secret(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    row = bot.create_voice_asset_record(
        17007,
        "voice_tts_preview",
        bot.PRODUCT_CONTEXT_SHOWROOM,
        "default_female",
        metadata={"provider_voice_id": "hidden", "SECRET_TOKEN": "hidden", "safe": "shown"},
    )
    stored = bot.get_voice_asset_record(row["voice_asset_id"])
    line = bot.voice_asset_summary_line(stored)
    assert "SECRET" not in line.upper()
    assert "hidden" not in line


def test_voice_asset_unused_lists_generated(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    row = bot.create_voice_asset_record(17008, "voice_tts_preview", bot.PRODUCT_CONTEXT_SHOWROOM, "default_female", status="generated_unused")
    rows = bot.list_voice_asset_records(status="generated_unused")
    assert [item["voice_asset_id"] for item in rows] == [row["voice_asset_id"]]


def test_voice_asset_no_provider_call_from_status(monkeypatch, tmp_path):
    _init_voice_db(monkeypatch, tmp_path)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    bot.create_voice_asset_record(17009, "voice_tts_preview", bot.PRODUCT_CONTEXT_SHOWROOM, "default_female", status="preview_sent")

    async def forbidden_engine(*_args, **_kwargs):
        raise AssertionError("status command must not call provider")

    monkeypatch.setattr(bot, "execute_engine", forbidden_engine)
    message = CaptureMessage(user_id=bot.ADMIN_ID)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=bot.ADMIN_ID), message=message)
    asyncio.run(bot.cmd_voice_asset_status(update, SimpleNamespace(args=[])))
    assert message.outputs
    assert "No provider call" in message.outputs[-1]["text"]


def test_voice_engine_status_command_registered():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert 'CommandHandler("voice_engine_status", cmd_voice_engine_status)' in source
    assert 'CommandHandler("voice_asset_status", cmd_voice_asset_status)' in source
    assert 'CommandHandler("voice_tts_admin_test", cmd_tool_test_voice_tts_product)' in source
    assert 'CommandHandler("voice_clone_admin_test", cmd_tool_test_minimax_voice_clone)' in source


def test_voice_admin_paid_test_requires_confirm(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    source = inspect.getsource(bot.cmd_tool_test_voice_tts_product)
    assert "has_admin_paid_confirmation" in source
    assert "NO_CONFIRM" in source


def test_voice_admin_paid_test_no_customer_charge():
    source = inspect.getsource(bot.cmd_tool_test_voice_tts_product)
    assert "spend_fixed_credit_info" not in source
