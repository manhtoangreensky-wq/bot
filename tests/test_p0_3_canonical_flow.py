import asyncio
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


def _source_text() -> str:
    return Path(bot.__file__).resolve().read_text(encoding="utf-8")


def _source_between(start_marker: str, end_marker: str) -> str:
    source = _source_text()
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


class CaptureMessage:
    def __init__(self, text: str = ""):
        self.text = text
        self.chat_id = 900301
        self.outputs = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        item = {
            "text": str(text),
            "parse_mode": parse_mode,
            "reply_markup": reply_markup,
            **kwargs,
        }
        self.outputs.append(item)
        return SimpleNamespace(text=text, reply_markup=reply_markup)


class CaptureQuery:
    def __init__(self, data: str, user_id: int):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage()
        self.outputs = self.message.outputs

    async def answer(self, *args, **kwargs):
        return None

    async def edit_message_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        item = {
            "text": str(text),
            "parse_mode": parse_mode,
            "reply_markup": reply_markup,
            **kwargs,
        }
        self.outputs.append(item)
        return SimpleNamespace(text=text, reply_markup=reply_markup)


def _callback_update(query: CaptureQuery, user_id: int):
    return SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user_id))


def _reset_user(user_id: int):
    bot.clear_music_guided_pending(user_id)
    bot.USER_PENDING.pop(bot.music_guided_result_key(user_id), None)
    bot.clear_product_context(user_id)
    bot.clear_video_finalization_state(user_id)
    bot.clear_video_addon_state(user_id)
    bot.clear_public_video_package_context(user_id)
    bot.clear_developing_video_pending(user_id)


def test_no_old_voice_studio_public_menu():
    text = "\n".join([
        bot.voice_hub_text("vi", bot.PRODUCT_CONTEXT_SHOWROOM),
        bot.music_hub_text("vi", bot.PRODUCT_CONTEXT_SHOWROOM),
        "\n".join(_labels(bot.voice_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))),
        "\n".join(_labels(bot.music_tools_keyboard("vi"))),
        "\n".join(_labels(bot.music_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))),
    ])

    legacy_music_voice = "nhạc" + "/voice"
    for forbidden in [
        "Voice Studio " + "TOAN AAS",
        "Demo giọng nữ" + " miễn phí",
        "Demo giọng nam" + " miễn phí",
        "Nhập chữ" + " để đọc thử",
        "Chọn " + legacy_music_voice,
        "Bạn muốn " + legacy_music_voice,
    ]:
        assert forbidden not in text


def test_audio_studio_voice_flow_does_not_render_legacy_voice_menu(monkeypatch):
    user_id = 930301
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")

    query = CaptureQuery("music_quick|showroom|voice_hub", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))

    assert query.outputs
    assert "Bạn hãy gửi nội dung cần đọc" in query.outputs[-1]["text"]
    assert "Voice Studio " + "TOAN AAS" not in query.outputs[-1]["text"]
    assert "Demo giọng" not in "\n".join(_labels(query.outputs[-1]["reply_markup"]))
    pending = bot.get_music_guided_pending(user_id)
    assert pending["pending_action"] == "voice_text"
    assert pending["product_context"] == bot.PRODUCT_CONTEXT_SHOWROOM


def test_audio_studio_voice_text_to_style_to_preview_path(monkeypatch):
    user_id = 930302
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")

    bot.set_music_guided_pending(user_id, "voice_text", product_context=bot.PRODUCT_CONTEXT_SHOWROOM)
    message = CaptureMessage("Nước hoa nam cao cấp giúp tự tin hơn khi gặp khách hàng.")
    handled = asyncio.run(bot.handle_music_guided_pending_text(
        SimpleNamespace(message=message, effective_user=SimpleNamespace(id=user_id)),
        SimpleNamespace(),
    ))

    assert handled is True
    assert "3 kiểu giọng gợi ý" in message.outputs[-1]["text"]
    style_labels = _labels(message.outputs[-1]["reply_markup"])
    assert "1️⃣ Giọng nữ nhẹ nhàng" in style_labels
    assert "2️⃣ Giọng nam tin cậy" in style_labels
    assert "3️⃣ Giọng trẻ bán hàng" in style_labels

    query = CaptureQuery("music_quick|showroom|voice_style_1", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))
    assert "Bản nghe thử ngắn" in query.outputs[-1]["text"]
    preview_labels = _labels(query.outputs[-1]["reply_markup"])
    assert "✅ Tạo bản đầy đủ" in preview_labels
    assert "🔁 Đổi giọng" in preview_labels
    assert "✏️ Sửa nội dung" in preview_labels
    assert "🔁 Đổi giọng" + "/nhạc" not in preview_labels


def test_audio_studio_music_prompt_does_not_show_suno_or_provider(monkeypatch):
    user_id = 930303
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")

    query = CaptureQuery("music_quick|showroom|ai_music", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))

    text = query.outputs[-1]["text"]
    assert "Bạn mô tả kiểu nhạc muốn tạo" in text
    assert "Suno" not in text
    assert "provider" not in text.lower()
    assert "api" not in text.lower()
    assert bot.get_music_guided_pending(user_id)["pending_action"] == "music_ai_custom"


def test_no_public_choose_music_voice_step():
    guided_text = bot.guided_video_music_text({"selected_motion": "pushin"}, "vi")
    guided_labels = "\n".join(_labels(bot.guided_video_music_keyboard("promptvideo", "vi")))
    frame_text = bot.frame_video_music_text({"effect": "fade"})
    frame_labels = "\n".join(_labels(bot.frame_video_music_keyboard()))

    combined = "\n".join([guided_text, guided_labels, frame_text, frame_labels])
    legacy_music_voice = "nhạc" + "/voice"
    for forbidden in ["Bạn muốn " + legacy_music_voice, "Chọn " + legacy_music_voice, legacy_music_voice, "Đổi giọng" + "/nhạc"]:
        assert forbidden not in combined
    assert "Âm thanh cho video" in combined
    assert "Bỏ qua âm thanh" in combined


def test_video_music_addon_directly_opens_library_menu(monkeypatch):
    user_id = 930304
    _reset_user(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda uid: "vi")
    bot.set_video_finalization_state(user_id, {
        "source": "promptvideo",
        "selected_prompt": "Video quảng cáo nước hoa nam.",
        "source_video_file_id": "video-file-id",
        "selected_video_tier": "basic",
        "current_video_duration_seconds": 12,
        "video_finalization": {},
    })

    query = CaptureQuery("vfinal|music_use", user_id)
    asyncio.run(bot.handle_video_finalization_callback(
        SimpleNamespace(callback_query=query),
        SimpleNamespace(),
    ))

    assert query.outputs
    assert "kho nhạc" in query.outputs[-1]["text"].lower()
    callbacks = _callbacks(query.outputs[-1]["reply_markup"])
    assert any(callback.startswith("music_quick|video_addon|") for callback in callbacks)
    assert not any("music_suggest" in callback or "music_use" in callback for callback in callbacks)


def test_selfshot_full_path_music_back_returns_addons():
    labels = "\n".join(_labels(bot.self_scene_music_keyboard("vi")))
    text = bot.self_scene_music_text({"selected_motion": "pushin"}, "vi")

    assert "Tùy chọn hoàn thiện video" in text
    assert "🎛 Tùy chọn hoàn thiện video" in labels
    assert "Tiếp tục chọn gói" in labels
    assert "Chọn nhạc" + "/voice" not in labels
    assert "Quay lại nhạc" + "/voice" not in labels


def test_selfshot_full_path_no_music_returns_package_or_invoice_correctly(monkeypatch):
    user_id = 930305
    _reset_user(user_id)
    captured = {}

    async def fake_open_video_finalization(query, uid, source, source_state, lang, back_callback, source_payload=None):
        captured.update({
            "uid": uid,
            "source": source,
            "source_state": dict(source_state or {}),
            "back_callback": back_callback,
            "source_payload": dict(source_payload or {}),
        })
        return "opened"

    monkeypatch.setattr(bot, "get_user_language", lambda uid: "vi")
    monkeypatch.setattr(bot, "open_video_finalization", fake_open_video_finalization)
    bot.set_developing_video_pending(
        user_id,
        "selfscene",
        "addons",
        input_type="video",
        source_file_id="tg-source-video",
        selected_topic="chai nước hoa",
        selected_context="studio luxury",
        selected_motion="pushin",
    )

    query = CaptureQuery("selfscene|music|none", user_id)
    result = asyncio.run(bot.handle_self_scene_ai_callback(
        SimpleNamespace(callback_query=query),
        SimpleNamespace(),
    ))

    assert result == "opened"
    assert captured["source"] == "selfscene"
    assert captured["source_state"]["source_file_id"] == "tg-source-video"
    assert captured["source_state"]["selected_music"] == "none"
    assert captured["back_callback"] == "selfscene|back_style"


def test_invoice_change_music_returns_invoice_without_legacy_step(monkeypatch):
    user_id = 930306
    _reset_user(user_id)
    captured = {}

    async def fake_start_video_addon_step(query, uid, pending_payload, tier, lang="vi", source="ai"):
        captured.update({
            "uid": uid,
            "pending_payload": dict(pending_payload or {}),
            "tier": tier,
            "source": source,
        })
        return "invoice"

    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")
    monkeypatch.setattr(bot, "start_video_addon_step", fake_start_video_addon_step)
    bot.set_video_finalization_state(user_id, {
        "source": "promptvideo",
        "selected_prompt": "Video quảng cáo sản phẩm.",
        "source_video_file_id": "video-file-id",
        "source_file_id": "source-file-id",
        "selected_video_tier": "basic",
        "current_video_duration_seconds": 18,
        "addon_return_target": "invoice",
        "video_finalization": {"music_mode": "library", "music_item_count": 1},
    })

    query = CaptureQuery("music_quick|video_addon|music_none", user_id)
    result = asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))

    assert result == "invoice"
    saved = bot.get_video_finalization_state(user_id)
    assert saved["step"] == "confirm"
    assert saved["addon_return_target"] == "invoice"
    assert captured["tier"] == "basic"
    assert captured["pending_payload"]["source_video_file_id"] == "video-file-id"
    assert captured["pending_payload"]["source_file_id"] == "source-file-id"
    assert "music_suggest" not in "\n".join(str(output["text"]) for output in query.outputs)
    assert "Chọn nhạc" + "/voice" not in "\n".join(str(output["text"]) for output in query.outputs)


def test_invoice_no_duplicate_free_addon_lines():
    order = bot.video_order_from_state({
        "video_tier": "basic",
        "current_video_music_choice": "none",
        "current_video_voice_choice": "default_female",
        "video_order": {
            "tier": "basic",
            "free_items": [
                {"key": "music_none", "label": "Không thêm nhạc", "price_xu": 0},
                {"key": "voice_default_female", "label": "Giọng nữ mặc định", "price_xu": 0},
            ],
        },
    }, user_id=930307)
    keys = [item["key"] for item in order["free_items"]]

    assert keys.count("music_none") == 1
    assert keys.count("voice_default_female") == 1


def test_video_addons_before_package_invoice():
    registry = bot.CANONICAL_FLOW_REGISTRY
    assert registry["video_addon"].index("video_finalize_addons") < registry["video_addon"].index("video_package")
    assert registry["video_addon"].index("video_package") < registry["video_addon"].index("video_invoice")
    assert registry["video_addon"].index("video_invoice") < registry["video_addon"].index("video_preview")
    assert registry["video_addon"].index("video_preview") < registry["video_addon"].index("video_final_confirm")

    callbacks = _callbacks(bot.video_finalization_menu_keyboard("vi"))
    assert callbacks.index("vfinal|voice") < callbacks.index("vfinal|tier")
    assert callbacks.index("vfinal|music") < callbacks.index("vfinal|tier")
    assert callbacks.index("vfinal|addon") < callbacks.index("vfinal|tier")


def test_public_ui_no_provider_vendor_admin_terms():
    texts = [
        bot.voice_hub_text("vi", bot.PRODUCT_CONTEXT_SHOWROOM),
        bot.music_hub_text("vi", bot.PRODUCT_CONTEXT_SHOWROOM),
        bot.music_ai_input_text("custom", "vi"),
        bot.guided_video_music_text({"selected_motion": "pushin"}, "vi"),
        bot.frame_video_music_text({"effect": "fade"}),
        bot.video_idea_followup_text("music", {"selected_topic": "nước hoa nam"}, "vi"),
    ]
    labels = [
        "\n".join(_labels(bot.voice_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))),
        "\n".join(_labels(bot.music_hub_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM))),
        "\n".join(_labels(bot.guided_video_music_keyboard("promptvideo", "vi"))),
        "\n".join(_labels(bot.frame_video_music_keyboard())),
    ]
    lowered = "\n".join(texts + labels).lower()

    for term in ["provider", "api", "suno", "minimax", "key4u", "shopaikey", "env", "http", "smoke", "gate", "raw error", "not_tested"]:
        assert term not in lowered


def test_legacy_callbacks_redirect_to_canonical_handlers(monkeypatch):
    user_id = 930308
    _reset_user(user_id)
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")

    assert bot.LEGACY_CANONICAL_CALLBACK_REDIRECTS["music_quick|voice_pick"] == "music_quick|showroom|voice_custom"
    assert bot.LEGACY_CANONICAL_CALLBACK_REDIRECTS["vfinal|music_use"] == "vfinal|music_library"
    assert bot.LEGACY_CANONICAL_CALLBACK_REDIRECTS["vfinal|music_suggest"] == "vfinal|music"

    query = CaptureQuery("music_quick|voice_pick", user_id)
    asyncio.run(bot.handle_music_quick_callback(_callback_update(query, user_id), SimpleNamespace()))

    assert "Bạn hãy gửi nội dung cần đọc" in query.outputs[-1]["text"]
    assert bot.get_music_guided_pending(user_id)["product_context"] == bot.PRODUCT_CONTEXT_SHOWROOM


def test_no_provider_call_before_preview_guards():
    style_block = _source_between('if action.startswith("voice_style_"):', 'if action == "voice_tts_guard":')
    ai_music_block = _source_between('if action == "ai_music":', 'if action in {"music_ai_background",')

    for block in [style_block, ai_music_block]:
        assert "spend_fixed_credit_info" not in block
        assert "deduct_dynamic_credit" not in block
        assert "create_minimax_voice_profile_preview" not in block
        assert "shopaikey_tts_bytes" not in block
        assert "send_audio" not in block


def test_no_xu_before_final_confirm():
    preview_entry = bot.audio_voice_preview_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM)
    callbacks = _callbacks(preview_entry)
    style_block = _source_between('if action.startswith("voice_style_"):', 'if action == "voice_tts_guard":')
    music_block = _source_between('if action == "ai_music":', 'if action in {"music_ai_background",')

    assert "music_quick|showroom|voice_tts_guard" in callbacks
    for block in [style_block, music_block]:
        assert "spend_fixed_credit_info" not in block
        assert "deduct_xu" not in block
        assert "public_video_mark_xu_deducted" not in block
