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


def _joined_markup(markup):
    return "\n".join(_labels(markup) + _callbacks(markup))


class CaptureMessage:
    def __init__(self, text="", user_id=940400):
        self.text = text
        self.chat_id = user_id
        self.message_id = 77
        self.outputs = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        item = {"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(text=text, reply_markup=reply_markup)


class CaptureQuery:
    def __init__(self, data, user_id=940400):
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
        "source_label": "Self-shot",
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
        "video_finalization": {},
    })


def test_audio_studio_top_level_only_two_buttons():
    labels = _labels(bot.music_tools_keyboard("vi"))
    callbacks = _callbacks(bot.music_tools_keyboard("vi"))

    assert labels[:2] == ["🎙 Giọng đọc", "🎵 Nhạc"]
    assert callbacks[:2] == ["music_quick|showroom|voice_hub", "music_quick|showroom|music_hub"]
    assert "📁 Kho voice" not in labels
    assert "🎼 Kho nhạc / SFX" not in labels
    assert "📁 Media âm thanh" not in labels
    assert not any(callback.startswith("vfinal|") or callback.startswith("videoaddon|") for callback in callbacks)


def test_audio_voice_single_prompt_no_duplicate_prompt(monkeypatch):
    user_id = 940401
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")

    first = CaptureQuery("music_quick|showroom|voice_custom", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(first, user_id), SimpleNamespace()))
    second = CaptureQuery("music_quick|showroom|voice_custom", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(second, user_id), SimpleNamespace()))

    assert "Bạn nhập nội dung muốn tạo giọng đọc nhé." in first.outputs[-1]["text"]
    assert "Bạn gửi nội dung cần đọc ở tin nhắn tiếp theo nhé." in second.outputs[-1]["text"]
    assert "Bạn nhập nội dung muốn tạo giọng đọc nhé." not in second.outputs[-1]["text"]
    assert bot.get_music_guided_pending(user_id)["pending_action"] == "audio_voice_waiting_text"


def test_audio_voice_text_to_style_to_preview_flow(monkeypatch):
    user_id = 940402
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")

    start = CaptureQuery("music_quick|showroom|voice_custom", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(start, user_id), SimpleNamespace()))
    message = CaptureMessage("Xin chào, đây là nội dung giới thiệu sản phẩm.", user_id)
    handled = asyncio.run(bot.handle_music_guided_pending_text(_message_update(message, user_id), SimpleNamespace()))

    assert handled is True
    assert "Chọn kiểu giọng" in message.outputs[-1]["text"]
    assert "👩 Giọng nữ nhẹ nhàng" in _labels(message.outputs[-1]["reply_markup"])
    assert "👨 Giọng nam tin cậy" in _labels(message.outputs[-1]["reply_markup"])
    assert "⚡ Giọng bán hàng năng lượng" in _labels(message.outputs[-1]["reply_markup"])

    preview = CaptureQuery("music_quick|showroom|voice_style_1", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(preview, user_id), SimpleNamespace()))
    preview_labels = _labels(preview.outputs[-1]["reply_markup"])
    assert "Bản nghe thử ngắn" in preview.outputs[-1]["text"]
    assert "✅ Tạo giọng đọc" in preview_labels
    assert "🔁 Đổi giọng" in preview_labels
    assert "✏️ Sửa nội dung" in preview_labels
    assert "🏠 Menu chính" in preview_labels


def test_audio_music_menu_simple(monkeypatch):
    user_id = 940403
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")

    query = CaptureQuery("music_quick|showroom|music_hub", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))
    labels = _labels(query.outputs[-1]["reply_markup"])

    assert "Bạn muốn làm gì?" in query.outputs[-1]["text"]
    assert labels[:4] == ["🎼 Tạo nhạc nền", "🎤 Bài hát có lời", "📂 Kho nhạc", "🎚 Cắt/ghép nhạc"]
    assert "🚫 Không thêm nhạc" not in labels


def test_audio_music_create_asks_prompt(monkeypatch):
    user_id = 940404
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")

    query = CaptureQuery("music_quick|showroom|ai_music", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))

    assert "Tạo nhạc nền" in query.outputs[-1]["text"]
    assert "🎵 Cơ bản — 100 Xu" in _joined_markup(query.outputs[-1]["reply_markup"])
    assert "🎶 Tiêu chuẩn — 150 Xu" in _joined_markup(query.outputs[-1]["reply_markup"])
    assert "💎 Cao cấp — 200 Xu" in _joined_markup(query.outputs[-1]["reply_markup"])


def test_no_old_voice_studio_public():
    surfaces = "\n".join([
        bot.menu_text_main_music(),
        bot.voice_hub_text("vi", bot.PRODUCT_CONTEXT_SHOWROOM),
        bot.music_hub_text("vi", bot.PRODUCT_CONTEXT_SHOWROOM),
        _joined_markup(bot.music_tools_keyboard("vi")),
        _joined_markup(bot.music_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM)),
        _joined_markup(bot.voice_style_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM)),
    ])

    assert "Voice Studio TOAN AAS" not in surfaces
    assert "Demo giọng nữ" not in surfaces
    assert "Demo giọng nam" not in surfaces
    assert "Nhập chữ để đọc thử" not in surfaces


def test_no_public_phong_cach_am_thanh():
    surfaces = "\n".join([
        bot.guided_video_music_text({"selected_motion": "pushin"}, "vi"),
        _joined_markup(bot.guided_video_music_keyboard("promptvideo", "vi")),
        bot.video_finalization_music_text({}, "vi"),
        _joined_markup(bot.video_finalization_music_keyboard("vi")),
    ])

    assert "Phong cách âm thanh 1" not in surfaces
    assert "Phong cách âm thanh 2" not in surfaces
    assert "Phong cách âm thanh 3" not in surfaces


def test_no_public_chon_nhac_voice():
    surfaces = "\n".join([
        bot.guided_video_music_text({"selected_motion": "pushin"}, "vi"),
        _joined_markup(bot.guided_video_music_keyboard("promptvideo", "vi")),
        bot.video_finalization_menu_text({"source": "selfscene"}, "vi"),
        _joined_markup(bot.video_addon_confirm_keyboard("tok", "basic", "vi")),
    ])

    assert "Chọn nhạc/voice" not in surfaces
    assert "nhạc/voice" not in surfaces
    assert "Đổi giọng/nhạc" not in surfaces


def test_video_addons_before_package_invoice():
    registry = bot.CANONICAL_FLOW_REGISTRY["video_addon"]
    callbacks = _callbacks(bot.video_finalization_menu_keyboard("vi"))

    assert registry.index("video_finalize_addons") < registry.index("video_package")
    assert registry.index("video_package") < registry.index("video_invoice")
    assert callbacks.index("vfinal|voice") < callbacks.index("vfinal|skip")
    assert callbacks.index("vfinal|music") < callbacks.index("vfinal|skip")
    assert callbacks.index("vfinal|addon") < callbacks.index("vfinal|skip")
    assert "Công cụ hoàn thiện video" in bot.video_finalization_menu_text({"source": "selfscene"}, "vi")


def test_video_music_direct_library_no_suggestion_step(monkeypatch):
    user_id = 940405
    _reset_user(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda uid: "vi")
    _seed_video_state(user_id)

    query = CaptureQuery("vfinal|music", user_id)
    asyncio.run(bot.handle_video_finalization_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    text = query.outputs[-1]["text"]
    labels = _labels(query.outputs[-1]["reply_markup"])
    callbacks = _callbacks(query.outputs[-1]["reply_markup"])
    assert "Nhạc cho video" in text
    assert "🎼 Kho nhạc có sẵn" in labels
    assert "🔊 Kho hiệu ứng âm thanh" in labels
    assert "vfinal|music_library" in callbacks
    assert "vfinal|music_suggest" not in callbacks
    assert "Phong cách âm thanh" not in text + "\n".join(labels)


def test_video_voice_free_selection_asks_script(monkeypatch):
    user_id = 940406
    _reset_user(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda uid: "vi")
    _seed_video_state(user_id)

    query = CaptureQuery("vfinal|voice_default|female", user_id)
    asyncio.run(bot.handle_video_finalization_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    finalization = bot.get_video_finalization_state(user_id)["video_finalization"]

    assert finalization["voice_mode"] == "default_female_free"
    assert finalization["dub_enabled"] is False
    assert bot.get_video_finalization_state(user_id)["step"] == "await_voice_script"
    assert "gửi nội dung/kịch bản cần đọc" in query.outputs[-1]["text"]


def test_video_music_free_selection_returns_origin(monkeypatch):
    user_id = 940407
    _reset_user(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda uid: "vi")
    _seed_video_state(user_id)

    query = CaptureQuery("vfinal|music_none", user_id)
    asyncio.run(bot.handle_video_finalization_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    finalization = bot.get_video_finalization_state(user_id)["video_finalization"]

    assert finalization["music_mode"] == "none"
    assert finalization["music_enabled"] is False
    assert bot.get_video_finalization_state(user_id)["step"] == "menu"
    assert "Công cụ hoàn thiện video" in query.outputs[-1]["text"]
    assert "Chọn gói xuất video AI" not in query.outputs[-1]["text"]
    assert "vfinal|tier" in _callbacks(query.outputs[-1]["reply_markup"])


def test_video_subdub_selection_returns_origin(monkeypatch):
    user_id = 940408
    _reset_user(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda uid: "vi")
    _seed_video_state(user_id)

    query = CaptureQuery("vfinal|translate_sub", user_id)
    asyncio.run(bot.handle_video_finalization_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    finalization = bot.get_video_finalization_state(user_id)["video_finalization"]

    assert finalization["translation_enabled"] is True
    assert finalization["subtitle_dub_choice"] == "translate_subtitle"
    assert bot.get_video_finalization_state(user_id)["step"] == "menu"
    assert "Công cụ hoàn thiện video" in query.outputs[-1]["text"]
    assert "Chọn gói xuất video AI" not in query.outputs[-1]["text"]
    assert "vfinal|tier" in _callbacks(query.outputs[-1]["reply_markup"])


def test_invoice_change_music_returns_tools(monkeypatch):
    user_id = 940409
    _reset_user(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda uid: "vi")
    _seed_video_state(user_id, addon_return_target="invoice")
    bot.set_video_addon_state(user_id, {
        "source": "ai",
        "video_tier": "basic",
        "pending_confirm_token": "tok",
        "pending_payload": {
            "prompt": "Video quảng cáo nước hoa nam.",
            "source_file_id": "source-file-id",
            "source_video_file_id": "source-video-file-id",
            "video_tier": "basic",
        },
        "video_order": {"current_screen": "invoice", "screen_stack": ["video_addon_menu", "invoice"]},
    })

    query = CaptureQuery("vfinal|music_none", user_id)
    result = asyncio.run(bot.handle_video_finalization_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert result is not None
    assert "Công cụ hoàn thiện video" in query.outputs[-1]["text"]
    assert "Chọn gói xuất video AI" not in query.outputs[-1]["text"]
    assert "vfinal|tier" in _callbacks(query.outputs[-1]["reply_markup"])
    assert bot.get_video_finalization_state(user_id)["step"] == "menu"
    assert bot.get_video_finalization_state(user_id)["video_finalization"]["music_mode"] == "none"


def test_invoice_back_returns_scene_count(monkeypatch):
    user_id = 940410
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    bot.set_video_addon_state(user_id, {
        "source": "ai",
        "video_tier": "basic",
        "pending_confirm_token": "tok",
        "pending_payload": {
            "prompt": "Video quảng cáo nước hoa nam.",
            "source_file_id": "source-file-id",
            "source_video_file_id": "source-video-file-id",
            "video_tier": "basic",
        },
        "video_order": {"current_screen": "invoice", "screen_stack": ["video_addon_menu", "invoice"]},
    })

    query = CaptureQuery("videoaddon|back", user_id)
    asyncio.run(bot.handle_video_addon_callback(_callback_update(query, user_id), SimpleNamespace()))

    assert "Chọn số cảnh video" in query.outputs[-1]["text"]
    assert "vfinal|scene_count|3" in _callbacks(query.outputs[-1]["reply_markup"])
    assert "vfinal|back" in _callbacks(query.outputs[-1]["reply_markup"])


def test_invoice_no_duplicate_free_lines():
    order = bot.video_order_from_state({
        "video_tier": "basic",
        "current_video_music_choice": "none",
        "current_video_voice_choice": "default_female",
        "video_order": {
            "tier": "basic",
            "free_items": [
                {"key": "music_none", "label": "Không thêm nhạc", "price_xu": 0},
                {"key": "music_none", "label": "Không thêm nhạc", "price_xu": 0},
                {"key": "voice_default_female", "label": "Giọng nữ miễn phí", "price_xu": 0},
                {"key": "voice_default_female", "label": "Giọng nữ miễn phí", "price_xu": 0},
            ],
        },
    }, user_id=940411)
    keys = [item["key"] for item in order["free_items"]]

    assert keys.count("music_none") == 1
    assert keys.count("voice_default_female") == 1


def test_selfshot_music_back_no_reset(monkeypatch):
    user_id = 940412
    _reset_user(user_id)
    captured = {}

    async def fake_open(query, uid, source, source_state, lang, back_callback, source_payload=None, initial_step="addons"):
        captured.update(source=source, source_state=dict(source_state or {}), back_callback=back_callback, source_payload=dict(source_payload or {}))
        return "opened"

    monkeypatch.setattr(bot, "get_user_language", lambda uid: "vi")
    monkeypatch.setattr(bot, "open_video_finalization", fake_open)
    bot.set_developing_video_pending(
        user_id,
        "selfscene",
        "addons",
        source_file_id="selfshot-file-id",
        selected_topic="chai nước hoa",
        selected_context="studio",
        selected_motion="pushin",
    )

    query = CaptureQuery("selfscene|music|none", user_id)
    result = asyncio.run(bot.handle_self_scene_ai_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert result == "opened"
    assert captured["source"] == "selfscene"
    assert captured["source_state"]["source_file_id"] == "selfshot-file-id"
    assert captured["source_state"]["selected_music"] == "none"
    assert captured["back_callback"] == "selfscene|back_style"


def test_public_no_vendor_technical_terms():
    surfaces = "\n".join([
        bot.menu_text_main_music(),
        bot.voice_text_input_text("vi"),
        bot.voice_style_suggestions_text("Xin chào khách hàng", "vi"),
        bot.music_hub_text("vi", bot.PRODUCT_CONTEXT_SHOWROOM),
        bot.music_ai_input_text("custom", "vi"),
        bot.video_finalization_menu_text({"source": "selfscene"}, "vi"),
        bot.video_finalization_voice_text({}, "vi"),
        bot.video_finalization_music_text({}, "vi"),
        bot.video_finalization_addon_text("vi"),
        _joined_markup(bot.music_tools_keyboard("vi")),
        _joined_markup(bot.music_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM)),
        _joined_markup(bot.video_finalization_menu_keyboard("vi")),
        _joined_markup(bot.video_finalization_music_keyboard("vi")),
        _joined_markup(bot.video_addon_confirm_keyboard("tok", "basic", "vi")),
    ])
    forbidden = [
        "API",
        "provider",
        "Suno",
        "MiniMax",
        "Key4U",
        "ShopAIKey",
        "OpenAI",
        "Google",
        "Claude",
        "Kling",
        "VEO",
        "ENV",
        "HTTP",
        "traceback",
        "smoke",
        "gate",
        "ready=False",
        "NOT_TESTED",
        "Bot chưa gọi API",
        "nhạc/voice",
        "Phong cách âm thanh",
        "Voice Studio TOAN AAS",
    ]

    for term in forbidden:
        assert term.lower() not in surfaces.lower()


def test_no_xu_before_final_confirm():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    voice_style_block = source[source.index('if action.startswith("voice_style_"):'):source.index('if action == "voice_tts_guard":')]
    music_ai_block = source[source.index('if action == "ai_music":'):source.index('if action in {"music_ai_background"')]
    preview_block = source[source.index("def video_paid_preview_text"):source.index("def video_paid_preview_keyboard")]

    for block in (voice_style_block, music_ai_block, preview_block):
        assert "spend_fixed_credit_info" not in block
        assert "deduct_dynamic_credit" not in block
        assert "public_video_mark_xu_deducted" not in block


def test_no_full_output_before_final_confirm():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    preview_block = source[source.index("async def handle_video_addon_callback"):source.index("async def finalize_video_addon_confirmation")]
    voice_preview_block = source[source.index('if action.startswith("voice_style_"):'):source.index('if action == "voice_tts_guard":')]

    assert "send_document" not in preview_block
    assert "send_video" not in preview_block
    assert "send_audio" not in voice_preview_block
    assert "videoaddon|export|" in _joined_markup(bot.video_addon_confirm_keyboard("tok", "basic", "vi"))


def test_payos_not_touched():
    repo = Path(bot.__file__).resolve().parent
    result = subprocess.run(["git", "diff", "--name-only", "origin/main"], cwd=repo, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    changed = {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}
    changed.discard("docs/reports/P0_17C0_PAYOS_SECURITY_AUDIT_ONLY.md")
    changed.discard("docs/reports/P0_17C2_PAYOS_AUTO_TOPUP_LIMITS.md")
    changed.discard("docs/reports/P0_17C3_PAYOS_ADMIN_RISK_LOCK_REVIEW.md")
    changed.discard("docs/reports/P0_17C4_WEBHOOK_DB_HTML_SECURITY_EVENTS.md")
    changed.discard("tests/test_p0_17a1_admin_control_center_handbook.py")
    changed.discard("tests/test_p0_17c1_payos_signature_idempotency.py")
    changed.discard("tests/test_p0_17c2_payos_auto_topup_limits.py")
    changed.discard("tests/test_p0_17c3_payos_admin_risk_lock_review.py")
    changed.discard("tests/test_p0_17c4_webhook_db_html_security_events.py")
    changed.discard("tests/test_p0_21e_tax_payment_accounting_business_dashboard.py")
    forbidden = ("payos", "naptien", "webhook", "wallet", "topup", "top-up", "payment")

    assert not any(any(term in path.lower() for term in forbidden) for path in changed)
