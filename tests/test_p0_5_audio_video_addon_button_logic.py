import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def _joined(markup):
    return "\n".join(_labels(markup) + _callbacks(markup))


class CaptureMessage:
    def __init__(self, text="", user_id=950500):
        self.text = text
        self.chat_id = user_id
        self.message_id = 55
        self.outputs = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        item = {"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(text=text, reply_markup=reply_markup)

    async def reply_audio(self, audio=None, filename=None, caption=None, **kwargs):
        item = {"audio": audio, "filename": filename, "caption": str(caption or ""), **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(audio=audio, caption=caption)


class CaptureQuery:
    def __init__(self, data, user_id=950500):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage(user_id=user_id)
        self.outputs = self.message.outputs

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        item = {"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(text=text, reply_markup=reply_markup)


def _callback_update(query, user_id):
    return SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user_id))


def _message_update(message, user_id):
    return SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id))


def _reset_user(user_id):
    bot.clear_music_guided_pending(user_id)
    bot.USER_PENDING.pop(bot.music_guided_result_key(user_id), None)
    bot.clear_product_context(user_id)
    bot.clear_video_finalization_state(user_id)
    bot.clear_video_addon_state(user_id)
    bot.clear_public_video_package_context(user_id)
    bot.clear_developing_video_pending(user_id)


def _seed_video_state(user_id, addon_return_target="hub"):
    bot.set_video_finalization_state(user_id, {
        "source": "selfscene",
        "source_label": "Tự quay / đổi cảnh",
        "selected_prompt": "Video quảng cáo nước hoa nam.",
        "video_prompt": "Video quảng cáo nước hoa nam.",
        "source_file_id": "source-file-id",
        "source_video_file_id": "source-video-file-id",
        "selected_video_tier": "basic",
        "current_video_duration_seconds": 18,
        "object_prompt": "chai nước hoa",
        "direction_prompt": "quay cận cảnh",
        "addon_return_target": addon_return_target,
        "source_payload": {
            "prompt": "Video quảng cáo nước hoa nam.",
            "source_file_id": "source-file-id",
            "source_video_file_id": "source-video-file-id",
            "video_tier": "basic",
        },
        "video_order": {"tier": "basic", "current_screen": "video_addon_menu"},
        "video_finalization": {},
    })


def test_studio_audio_top_level_two_buttons_only():
    labels = _labels(bot.music_tools_keyboard("vi"))
    callbacks = _callbacks(bot.music_tools_keyboard("vi"))

    assert labels[:2] == ["🎙 Giọng đọc", "🎵 Nhạc"]
    assert callbacks[:2] == ["music_quick|showroom|voice_hub", "music_quick|showroom|music_hub"]
    assert not any("Kho voice" in label or "Kho nhạc" in label or "Media âm thanh" in label for label in labels[:2])
    assert not any(callback.startswith("vfinal|") or callback.startswith("videoaddon|") for callback in callbacks)


def test_voice_inner_menu_restores_default_saved_custom_voice():
    labels = _labels(bot.voice_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    callbacks = _callbacks(bot.voice_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))

    for label in ["✍️ Văn bản thành giọng nói", "🎧 Giọng nói thành văn bản", "👩 Giọng nữ", "👨 Giọng nam", "📂 Kho voice", "🎙 Tạo voice riêng"]:
        assert label in labels
    for callback in ["music_quick|showroom|voice_tts_text", "music_quick|showroom|stt", "music_quick|showroom|voice_default_female", "music_quick|showroom|voice_default_male", "music_quick|showroom|voice_profiles", "music_quick|showroom|voice_clone"]:
        assert callback in callbacks
    assert "Không thêm giọng" not in "\n".join(labels)


def test_showroom_voice_hub_callback_opens_inner_menu(monkeypatch):
    user_id = 950516
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")

    query = CaptureQuery("music_quick|showroom|voice_hub", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))

    assert "Kho voice" in _joined(query.outputs[-1]["reply_markup"])
    assert bot.get_music_guided_pending(user_id) is None


def test_music_inner_menu_restores_stock_sfx_user_media_create_new_music():
    labels = _labels(bot.music_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))
    callbacks = _callbacks(bot.music_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))

    for label in ["🎵 Tạo nhạc nền", "🎤 Bài hát có lời", "📂 Kho nhạc", "🎚 Cắt/ghép nhạc"]:
        assert label in labels
    for callback in ["music_quick|showroom|music", "music_quick|showroom|music_edit", "music_quick|showroom|ai_music", "music_quick|showroom|song_menu"]:
        assert callback in callbacks
    assert "Không thêm nhạc" not in "\n".join(labels)


def test_showroom_voice_default_asks_text_then_confirm(monkeypatch):
    user_id = 950501
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    async def fake_tts(text, voice_id="", voice_style="", speed="normal"):
        return True, b"mp3-bytes", "ok"
    monkeypatch.setattr(bot, "synthesize_standalone_tts_audio", fake_tts)
    monkeypatch.setattr(bot, "preview_quota_guard", lambda *_args, **_kwargs: {"allowed": True, "reason": "ok", "product_type": "voice_ai", "quota": {}})
    monkeypatch.setattr(bot, "consume_preview_quota", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(bot, "cap_voice_preview_audio_bytes", lambda audio_bytes, seconds=6: asyncio.sleep(0, result=(b"preview-bytes", "ok")))

    query = CaptureQuery("music_quick|showroom|voice_default_female", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))
    assert bot.get_music_guided_pending(user_id)["pending_action"] == "voice_text"

    message = CaptureMessage("Xin chào khách hàng.", user_id)
    handled = asyncio.run(bot.handle_music_guided_pending_text(_message_update(message, user_id), SimpleNamespace()))

    assert handled is True
    assert "Tạo giọng đọc miễn phí" in message.outputs[-1]["text"]
    assert "6 giây" not in message.outputs[-1]["text"]
    assert "music_quick|showroom|voice_default_confirm:female" in _callbacks(message.outputs[-1]["reply_markup"])


def test_showroom_saved_voice_profile_asks_text_then_confirm(monkeypatch):
    user_id = 950502
    _reset_user(user_id)
    profile = {"id": 77, "display_name": "Voice bán hàng", "provider_voice_id": "voice-77", "status": "active"}
    touched = {}
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    monkeypatch.setattr(bot, "get_user_voice_profile", lambda uid, profile_id: profile if profile_id == 77 else None)
    monkeypatch.setattr(bot, "update_user_voice_profile", lambda uid, profile_id, **fields: touched.update(fields) or True)
    async def fake_tts(text, voice_id="", voice_style="", speed="normal"):
        return True, b"mp3-bytes", "ok"
    monkeypatch.setattr(bot, "synthesize_standalone_tts_audio", fake_tts)
    bot.set_music_guided_pending(user_id, "voice_profile_read_text", profile_id=77, product_context=bot.PRODUCT_CONTEXT_SHOWROOM)

    message = CaptureMessage("Đọc câu này bằng voice đã lưu.", user_id)
    handled = asyncio.run(bot.handle_music_guided_pending_text(_message_update(message, user_id), SimpleNamespace()))

    result = bot.get_music_guided_result(user_id)
    assert handled is True
    assert result["selected_voice_profile_id"] == 77
    assert "Dùng voice riêng để đọc văn bản" in message.outputs[-1]["text"]
    assert "0.1 Xu / ký tự" in message.outputs[-1]["text"]
    assert "music_quick|showroom|voice_profile_generate:77" in _callbacks(message.outputs[-1]["reply_markup"])
    assert touched.get("last_used_at")


def test_showroom_voice_custom_asks_text_not_dead(monkeypatch):
    user_id = 950503
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")

    query = CaptureQuery("music_quick|showroom|voice_custom", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))

    assert "Bạn nhập nội dung muốn tạo giọng đọc nhé." in query.outputs[-1]["text"]
    assert bot.get_music_guided_pending(user_id)["pending_action"] == "audio_voice_waiting_text"


def test_showroom_music_create_new_asks_prompt_then_suggestions(monkeypatch):
    user_id = 950504
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")

    query = CaptureQuery("music_quick|showroom|ai_music", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))
    assert "Tạo nhạc nền" in query.outputs[-1]["text"]
    assert "Video bán hàng" in _joined(query.outputs[-1]["reply_markup"])

    purpose = CaptureQuery("music_quick|showroom|music_ai_purpose_sales_video", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(purpose, user_id), SimpleNamespace()))
    style = CaptureQuery("music_quick|showroom|music_ai_style_cinematic", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(style, user_id), SimpleNamespace()))
    mood = CaptureQuery("music_quick|showroom|music_ai_mood_cheerful", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(mood, user_id), SimpleNamespace()))
    duration = CaptureQuery("music_quick|showroom|music_ai_duration_30s", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(duration, user_id), SimpleNamespace()))
    assert "3 prompt nhạc gợi ý" in duration.outputs[-1]["text"]
    assert "Chọn gợi ý 1" in _joined(duration.outputs[-1]["reply_markup"])


def test_video_addon_voice_menu_shows_free_and_paid_choices():
    labels = _labels(bot.video_finalization_voice_keyboard("vi"))

    for label in ["🚫 Không thêm giọng", "👩 Giọng nữ miễn phí", "👨 Giọng nam miễn phí", "📁 Voice đã lưu"]:
        assert label in labels
    assert f"🧬 Tạo voice riêng free/{bot.VOICE_PROFILE_PRICE_XU} Xu" in labels
    assert "▶️ Nghe thử giọng" in labels


def test_video_addon_music_menu_shows_free_and_paid_choices():
    labels = _labels(bot.video_finalization_music_keyboard("vi"))

    for label in ["🎼 Kho nhạc có sẵn", "🔊 Kho hiệu ứng âm thanh", "📁 Media âm thanh của tôi", "🚫 Không thêm nhạc"]:
        assert label in labels
    assert f"🎵 Tạo nhạc mới +{bot.VIDEO_SUNO_MUSIC_XU} Xu" in labels


def test_video_addon_subtitle_dub_menu_opens_factory():
    labels = _labels(bot.video_finalization_addon_keyboard("vi"))
    callbacks = _callbacks(bot.video_finalization_addon_keyboard("vi"))

    assert "🌐 Phụ đề / Dịch / Lồng tiếng" in labels
    assert "videodub|start|video_addon" in callbacks
    assert not any("Dịch phụ đề +" in label or "Lồng tiếng +" in label for label in labels)


def test_video_addon_paid_voice_updates_invoice_line(monkeypatch):
    user_id = 950505
    _reset_user(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda uid: "vi")
    _seed_video_state(user_id)

    query = CaptureQuery("vfinal|voice_create", user_id)
    asyncio.run(bot.handle_video_finalization_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    order = bot.video_order_from_state(bot.get_video_finalization_state(user_id), user_id=user_id)

    assert any(item["key"] == "voice_clone_create" and item["price_xu"] == 0 for item in order["paid_items"])
    assert "chưa trừ Xu" in query.outputs[-1]["text"]


def test_video_addon_paid_music_asks_prompt_before_invoice(monkeypatch):
    user_id = 950506
    _reset_user(user_id)
    called = {"invoice": False}

    async def fake_invoice(*args, **kwargs):
        called["invoice"] = True
        return "invoice"

    monkeypatch.setattr(bot, "get_user_language", lambda uid: "vi")
    monkeypatch.setattr(bot, "start_video_addon_step", fake_invoice)
    _seed_video_state(user_id)

    query = CaptureQuery("vfinal|music_ai", user_id)
    asyncio.run(bot.handle_video_finalization_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert called["invoice"] is False
    assert "Tạo nhạc nền" in query.outputs[-1]["text"]
    assert "Video bán hàng" in _joined(query.outputs[-1]["reply_markup"])
    assert bot.get_video_finalization_state(user_id)["video_finalization"]["music_mode"] == "none"


def test_video_addon_paid_music_updates_invoice_after_prompt_choice(monkeypatch):
    user_id = 950507
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    _seed_video_state(user_id)
    suggestions = bot.music_prompt_suggestions("Nhạc nền vui tươi cho video bán hàng.", 0, "vi", "custom")
    bot.save_music_guided_result(user_id, {"description": "Nhạc nền vui tươi", "offset": 0, "suggestions": suggestions, "music_ai_kind": "custom"})

    query = CaptureQuery("music_quick|video_addon|prompt_choose_1", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))
    order = bot.video_order_from_state(bot.get_video_finalization_state(user_id), user_id=user_id)

    assert bot.get_video_finalization_state(user_id)["video_finalization"]["music_mode"] == "ai_music"
    assert any(item["key"] == "suno_music" and item["price_xu"] == bot.VIDEO_SUNO_MUSIC_XU for item in order["paid_items"])


def test_video_addon_free_stock_music_updates_draft_without_paid_line():
    order = bot.video_order_from_state({
        "video_tier": "basic",
        "video_finalization": {"music_enabled": True, "music_mode": "library", "music_choice": "stock_music"},
    }, user_id=950508)

    assert any(item["key"] == "stock_music_library" for item in order["free_items"])
    assert not any(item["key"] == "suno_music" for item in order["paid_items"])


def test_video_addon_free_sfx_updates_draft_without_paid_line():
    order = bot.video_order_from_state({
        "video_tier": "basic",
        "video_finalization": {"music_enabled": True, "music_mode": "sfx_library", "music_choice": "stock_sfx"},
    }, user_id=950509)

    assert any(item["key"] == "stock_sfx_library" for item in order["free_items"])
    assert not any(item["key"] == "suno_music" for item in order["paid_items"])


def test_video_addon_my_media_is_free_choice_visible():
    labels = _labels(bot.video_finalization_music_keyboard("vi"))
    order = bot.video_order_from_state({
        "video_tier": "basic",
        "video_finalization": {"music_enabled": True, "music_mode": "uploaded", "music_choice": "user_media"},
    }, user_id=950510)

    assert "📁 Media âm thanh của tôi" in labels
    assert any(item["key"] == "user_audio_media" for item in order["free_items"])


def test_video_addon_return_from_hub_stays_on_video_options(monkeypatch):
    user_id = 950511
    _reset_user(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda uid: "vi")
    _seed_video_state(user_id)

    query = CaptureQuery("vfinal|voice_default|female", user_id)
    asyncio.run(bot.handle_video_finalization_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert "gửi nội dung/kịch bản cần đọc" in query.outputs[-1]["text"]
    assert bot.get_video_finalization_state(user_id)["step"] == "await_voice_script"
    assert bot.get_video_finalization_state(user_id)["source_file_id"] == "source-file-id"


def test_video_addon_invoice_origin_returns_tools_after_explicit_selection(monkeypatch):
    user_id = 950512
    _reset_user(user_id)

    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    _seed_video_state(user_id, addon_return_target="invoice")
    bot.set_video_addon_state(user_id, {
        "source": "ai",
        "video_tier": "basic",
        "pending_confirm_token": "tok",
        "pending_payload": {"prompt": "Video quảng cáo nước hoa nam.", "video_tier": "basic", "source_file_id": "source-file-id"},
        "video_order": {"current_screen": "invoice", "screen_stack": ["video_addon_menu", "invoice"]},
    })
    suggestions = bot.music_prompt_suggestions("Nhạc nền vui tươi.", 0, "vi", "custom")
    bot.save_music_guided_result(user_id, {"description": "Nhạc nền vui tươi", "offset": 0, "suggestions": suggestions, "music_ai_kind": "custom"})

    query = CaptureQuery("music_quick|video_addon|prompt_choose_1", user_id)
    result = asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))

    assert result is not None
    assert "Công cụ hoàn thiện video" in query.outputs[-1]["text"]
    assert "Chọn gói xuất video AI" not in query.outputs[-1]["text"]
    assert "vfinal|tier" in _callbacks(query.outputs[-1]["reply_markup"])
    state = bot.get_video_finalization_state(user_id)
    assert state["step"] == "menu"
    assert state["video_finalization"]["music_mode"] == "ai_music"
    assert state["source_payload"]["source_file_id"] == "source-file-id"


def test_selfshot_state_preserved_after_voice_choice(monkeypatch):
    user_id = 950513
    _reset_user(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda uid: "vi")
    _seed_video_state(user_id)

    query = CaptureQuery("vfinal|voice_default|male", user_id)
    asyncio.run(bot.handle_video_finalization_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    state = bot.get_video_finalization_state(user_id)

    assert state["step"] == "await_voice_script"
    assert state["source"] == "selfscene"
    assert state["source_file_id"] == "source-file-id"
    assert state["source_video_file_id"] == "source-video-file-id"
    assert state["object_prompt"] == "chai nước hoa"
    assert state["direction_prompt"] == "quay cận cảnh"


def test_selfshot_state_preserved_after_music_prompt_choice(monkeypatch):
    user_id = 950514
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    _seed_video_state(user_id)
    suggestions = bot.music_prompt_suggestions("Nhạc nền vui tươi.", 0, "vi", "custom")
    bot.save_music_guided_result(user_id, {"description": "Nhạc nền vui tươi", "offset": 0, "suggestions": suggestions, "music_ai_kind": "custom"})

    query = CaptureQuery("music_quick|video_addon|prompt_choose_1", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))
    state = bot.get_video_finalization_state(user_id)

    assert state["source"] == "selfscene"
    assert state["source_file_id"] == "source-file-id"
    assert state["source_video_file_id"] == "source-video-file-id"
    assert state["object_prompt"] == "chai nước hoa"
    assert state["video_finalization"]["music_mode"] == "ai_music"


def test_legacy_voice_pick_redirects_to_voice_hub(monkeypatch):
    user_id = 950515
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")

    query = CaptureQuery("music_quick|voice_pick", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))

    assert "Kho voice" in _joined(query.outputs[-1]["reply_markup"])
    assert bot.get_music_guided_pending(user_id) is None


def test_no_public_voice_studio_legacy_copy():
    surfaces = "\n".join([
        bot.voice_hub_text("vi", bot.PRODUCT_CONTEXT_SHOWROOM),
        bot.music_hub_text("vi", bot.PRODUCT_CONTEXT_SHOWROOM),
        _joined(bot.voice_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM)),
        _joined(bot.music_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM)),
    ])

    assert "Voice Studio TOAN AAS" not in surfaces
    assert "Chọn nhạc/voice" not in surfaces
    assert "Không thêm giọng" not in surfaces
    assert "Không thêm nhạc" not in surfaces


def test_no_video_addon_music_ai_direct_invoice_jump():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    handler = source[source.index("async def handle_video_finalization_callback"):source.index("async def handle_video_finalization_pending_text")]
    block = handler[handler.index('if action == "music_ai":'):handler.index('if action == "music_suggest":')]

    assert "start_video_addon_step" not in block
    assert "video_finalization_return_after_addon" not in block
    assert 'music_guided_step_keyboard("purpose", lang, PRODUCT_CONTEXT_VIDEO_ADDON, 0)' in block


def test_no_forbidden_payment_files_touched():
    repo = Path(bot.__file__).resolve().parent
    result = subprocess.run(["git", "diff", "--name-only", "origin/main"], cwd=repo, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    changed = {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}
    changed.discard("docs/reports/P0_17C0_PAYOS_SECURITY_AUDIT_ONLY.md")
    changed.discard("docs/reports/P0_17C2_PAYOS_AUTO_TOPUP_LIMITS.md")
    changed.discard("docs/reports/P0_17C3_PAYOS_ADMIN_RISK_LOCK_REVIEW.md")
    changed.discard("tests/test_p0_17c1_payos_signature_idempotency.py")
    changed.discard("tests/test_p0_17c2_payos_auto_topup_limits.py")
    changed.discard("tests/test_p0_17c3_payos_admin_risk_lock_review.py")
    forbidden = ("payos", "naptien", "webhook", "wallet", "topup", "top-up", "payment")

    assert not any(any(term in path.lower() for term in forbidden) for path in changed)


def test_p0_5_public_copy_no_provider_env_raw_error():
    surfaces = "\n".join([
        bot.voice_hub_text("vi", bot.PRODUCT_CONTEXT_SHOWROOM),
        bot.music_hub_text("vi", bot.PRODUCT_CONTEXT_SHOWROOM),
        bot.video_finalization_voice_text({}, "vi"),
        bot.video_finalization_music_text({}, "vi"),
        bot.video_finalization_addon_text("vi"),
        _joined(bot.voice_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM)),
        _joined(bot.music_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM)),
        _joined(bot.video_finalization_voice_keyboard("vi")),
        _joined(bot.video_finalization_music_keyboard("vi")),
        _joined(bot.video_finalization_addon_keyboard("vi")),
    ]).lower()

    for term in ["provider", "api", "suno", "minimax", "key4u", "shopaikey", "env", "http", "smoke", "gate", "raw error"]:
        assert term not in surfaces
