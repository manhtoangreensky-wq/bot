import asyncio
import inspect
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


FORBIDDEN_PUBLIC_TERMS = [
    "Bot chưa gọi " + "API",
    "chưa gọi " + "API",
    "A" + "PI",
    "pro" + "vider",
    "nhà cung cấp",
    "E" + "NV",
    "H" + "TTP",
    "traceback",
    "smo" + "ke",
    "ga" + "te",
    "ready=False",
    "NOT" + "_TESTED",
    "Key" + "4U",
    "Shop" + "AIKey",
    "Mini" + "Max",
    "Suno",
    "Open" + "AI",
    "Google",
    "Claude",
    "Whisper",
    "Deep" + "gram",
]


class CaptureMessage:
    def __init__(self, text: str = "", file_id: str = "video-file"):
        self.text = text
        self.chat_id = 990301
        self.message_id = 77
        self.outputs = []
        self.video = SimpleNamespace(
            file_id=file_id,
            file_unique_id=f"{file_id}-unique",
            file_name=f"{file_id}.mp4",
            mime_type="video/mp4",
            duration=18,
            file_size=2048,
            width=720,
            height=1280,
        )
        self.audio = None
        self.voice = None
        self.document = None

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


def _callback_update(query):
    return SimpleNamespace(callback_query=query)


def _reset_user(user_id: int):
    bot.clear_video_dubbing_pending(user_id)
    bot.clear_video_finalization_state(user_id)
    bot.clear_video_addon_state(user_id)
    bot.clear_public_video_package_context(user_id)
    bot.clear_product_context(user_id)


def _assert_public_clean(text: str):
    lowered = str(text or "").lower()
    for term in FORBIDDEN_PUBLIC_TERMS:
        assert term.lower() not in lowered


async def _press_videodub(data: str, user_id: int):
    query = CaptureQuery(data, user_id)
    await bot.handle_video_dubbing_callback(_callback_update(query), SimpleNamespace())
    return query


def test_standalone_translate_menu_no_api_text():
    text = bot.translation_menu_text("vi")
    labels = _labels(bot.translation_menu_keyboard("vi"))
    callbacks = _callbacks(bot.translation_menu_keyboard("vi"))

    assert "🌐 <b>Trung tâm dịch</b>" in text
    assert labels == [
        "🌐 Dịch ngôn ngữ",
        "🎬 Dịch phụ đề, lồng tiếng",
        "⬅️ Quay lại",
        "🏠 Menu chính",
    ]
    assert "menu|translation_language_hub" in callbacks
    assert "menu|translation_video_factory" in callbacks
    assert not any(callback.startswith(("vfinal|", "videoaddon|")) for callback in callbacks)
    _assert_public_clean("\n".join([text, *labels]))


def test_standalone_subtitle_asks_upload(monkeypatch):
    user_id = 990302
    _reset_user(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "video_dubbing_public_processing_ready", lambda *_args, **_kwargs: True)

    query = asyncio.run(_press_videodub(f"videodub|studio|{bot.VIDEO_SUBTITLE_MODE_CREATE}", user_id))

    state = bot.get_video_dubbing_pending(user_id)
    assert state["origin"] == "translation"
    assert state["step"] == "source"
    assert "Tạo phụ đề tự động" in query.outputs[-1]["text"]
    assert "đúng ngôn ngữ đang nói" in query.outputs[-1]["text"]
    assert "videodub|link_start" not in _callbacks(query.outputs[-1]["reply_markup"])

    query = asyncio.run(_press_videodub("videodub|source_upload", user_id))
    state = bot.get_video_dubbing_pending(user_id)
    assert state["step"] == "await_video"
    assert "Bạn gửi hoặc reply video/audio cần xử lý" in query.outputs[-1]["text"]
    assert bot.current_product_context(user_id) == bot.PRODUCT_CONTEXT_SHOWROOM
    _assert_public_clean(query.outputs[-1]["text"])


def test_standalone_translate_subtitle_asks_upload_then_language(monkeypatch):
    user_id = 990303
    _reset_user(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    monkeypatch.setattr(bot, "remember_last_media", lambda _update: None)
    monkeypatch.setattr(bot, "video_dubbing_capability", lambda *_args, **_kwargs: {"ok": True})

    async def fake_prepare(_context, passed_state, user_id, allow_admin=False):
        assert passed_state["mode"] == bot.VIDEO_SUBTITLE_MODE_CREATE
        assert passed_state["requested_mode"] == bot.VIDEO_SUBTITLE_MODE_TRANSLATE
        source = "1\n00:00:00,000 --> 00:00:02,000\nXin chao tu video"
        ref = bot.set_video_dubbing_artifact(user_id, "source_subtitle", source)
        saved = bot.set_video_dubbing_pending(user_id, passed_state.get("step") or "creating_original_subtitle", subtitle_ref=ref)
        return {
            "state": saved,
            "source_subtitle": source,
            "source_segments": [{"start": 0, "end": 2, "text": "Xin chao tu video"}],
            "detected_language": "vi",
        }

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fake_prepare)

    asyncio.run(_press_videodub(f"videodub|studio|{bot.VIDEO_SUBTITLE_MODE_TRANSLATE}", user_id))
    query = asyncio.run(_press_videodub("videodub|source_upload", user_id))
    assert bot.get_video_dubbing_pending(user_id)["step"] == "await_video"
    assert "Bạn gửi hoặc reply video/audio cần xử lý" in query.outputs[-1]["text"]

    message = CaptureMessage(file_id="translate-video")
    handled = asyncio.run(bot.handle_video_dubbing_pending_upload(
        SimpleNamespace(effective_user=SimpleNamespace(id=user_id), message=message),
        SimpleNamespace(),
    ))

    assert handled is True
    state = bot.get_video_dubbing_pending(user_id)
    assert state["step"] == "language"
    assert state["subtitle_ref"]
    assert state["video_file_id"] == "translate-video"
    assert "Dịch phụ đề sang ngôn ngữ nào" in message.outputs[-1]["text"]
    _assert_public_clean(message.outputs[-1]["text"])


def test_standalone_dubbing_asks_upload_then_language_or_voice(monkeypatch):
    user_id = 990304
    _reset_user(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    monkeypatch.setattr(bot, "remember_last_media", lambda _update: None)

    async def fake_prepare(_context, passed_state, user_id, allow_admin=False):
        assert passed_state["mode"] == bot.VIDEO_SUBTITLE_MODE_CREATE
        assert passed_state["requested_mode"] == bot.VIDEO_SUBTITLE_MODE_DUB
        source = "1\n00:00:00,000 --> 00:00:02,000\nXin chao tu video"
        ref = bot.set_video_dubbing_artifact(user_id, "source_subtitle", source)
        saved = bot.set_video_dubbing_pending(user_id, passed_state.get("step") or "creating_original_subtitle", subtitle_ref=ref)
        return {
            "state": saved,
            "source_subtitle": source,
            "source_segments": [{"start": 0, "end": 2, "text": "Xin chao tu video"}],
            "detected_language": "vi",
        }

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fake_prepare)

    asyncio.run(_press_videodub(f"videodub|studio|{bot.VIDEO_SUBTITLE_MODE_DUB}", user_id))
    query = asyncio.run(_press_videodub("videodub|source_upload", user_id))
    assert "Bạn gửi hoặc reply video/audio cần xử lý" in query.outputs[-1]["text"]

    message = CaptureMessage(file_id="dub-video")
    assert asyncio.run(bot.handle_video_dubbing_pending_upload(
        SimpleNamespace(effective_user=SimpleNamespace(id=user_id), message=message),
        SimpleNamespace(),
    )) is True

    state = bot.get_video_dubbing_pending(user_id)
    assert state["step"] == "language"
    assert "Bạn muốn lồng tiếng sang ngôn ngữ nào" in message.outputs[-1]["text"]
    _assert_public_clean(message.outputs[-1]["text"])


def test_standalone_subtitle_plus_dubbing_flow(monkeypatch):
    user_id = 990305
    _reset_user(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "cache_recent_media_state", lambda _update: None)
    monkeypatch.setattr(bot, "remember_last_media", lambda _update: None)
    monkeypatch.setattr(bot, "video_dubbing_capability", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(bot, "video_dubbing_configured_readiness", lambda *_args, **_kwargs: {"missing": []})
    monkeypatch.setattr(bot, "video_dubbing_asr_missing_for_state", lambda *_args, **_kwargs: False)

    async def fake_prepare(_context, state, user_id, allow_admin=False):
        mode = bot.normalize_video_translate_mode(state.get("mode") or state.get("video_processing_mode"))
        if mode == bot.VIDEO_SUBTITLE_MODE_CREATE:
            source = "1\n00:00:00,000 --> 00:00:02,000\nXin chào"
            subtitle_ref = bot.set_video_dubbing_artifact(user_id, "source_subtitle", source)
            saved = bot.set_video_dubbing_pending(user_id, state.get("step") or "creating_original_subtitle", subtitle_ref=subtitle_ref)
            return {
                "state": saved,
                "source_subtitle": source,
                "source_segments": [{"start": 0, "end": 2, "text": "Xin chào"}],
                "detected_language": "vi",
            }
        translated = "1\n00:00:00,000 --> 00:00:02,000\nHello"
        translated_ref = bot.set_video_dubbing_artifact(user_id, "translated_subtitle", translated)
        state = bot.set_video_dubbing_pending(user_id, state.get("step") or "translating_subtitle", translated_subtitle_ref=translated_ref)
        return {
            "state": state,
            "output_subtitle": translated,
            "output_script": "Hello",
            "output_segments": [{"start": 0, "end": 2, "text": "Hello"}],
        }

    monkeypatch.setattr(bot, "video_dubbing_prepare_subtitles", fake_prepare)

    asyncio.run(_press_videodub(f"videodub|studio|{bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}", user_id))
    asyncio.run(_press_videodub("videodub|source_upload", user_id))
    message = CaptureMessage(file_id="combo-video")
    asyncio.run(bot.handle_video_dubbing_pending_upload(
        SimpleNamespace(effective_user=SimpleNamespace(id=user_id), message=message),
        SimpleNamespace(),
    ))
    assert bot.get_video_dubbing_pending(user_id)["step"] == "original_subtitle_ready"
    assert "Đã tạo phụ đề gốc" in message.outputs[-1]["text"]

    asyncio.run(_press_videodub("videodub|combo_translate", user_id))
    lang_query = asyncio.run(_press_videodub("videodub|language|English", user_id))
    state = bot.get_video_dubbing_pending(user_id)
    assert state["step"] == "translated_subtitle_ready"
    assert "Đã dịch phụ đề sang English" in lang_query.outputs[-1]["text"]

    continue_query = asyncio.run(_press_videodub("videodub|combo_dub_translated", user_id))
    assert "Chọn giọng lồng tiếng" in continue_query.outputs[-1]["text"]

    voice_query = asyncio.run(_press_videodub("videodub|voice|default_female", user_id))
    state = bot.get_video_dubbing_pending(user_id)
    assert state["voice_style"]
    assert state["step"] == "dub_confirmation"
    assert "Xác nhận lồng tiếng" in voice_query.outputs[-1]["text"]
    _assert_public_clean(voice_query.outputs[-1]["text"])


def test_translation_public_guard_no_api_provider_words():
    for mode in [
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    ]:
        text = bot.video_dubbing_guard_text(mode, {}, "vi")
        assert "TOAN AAS chưa thể" in text or "bảo trì" in text
        assert "chưa trừ Xu" in text
        _assert_public_clean(text)


def test_translation_forbidden_text_absent_public():
    public_parts = [
        bot.translation_menu_text("vi"),
        "\n".join(_labels(bot.translation_menu_keyboard("vi"))),
        bot.video_dubbing_upload_text({"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE}, "vi"),
        bot.video_dubbing_language_text({"mode": bot.VIDEO_SUBTITLE_MODE_DUB}, "vi"),
        bot.video_dubbing_voice_text({"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "target_language": "English"}, "vi"),
        bot.video_dubbing_confirm_text({
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "video_file_id": "file",
            "video_duration": 12,
            "target_language": "English",
            "voice_style": "Nữ tự nhiên",
            "translate_requested": "1",
        }, "vi"),
        bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, {}, "vi"),
        bot.video_finalization_addon_text("vi"),
        "\n".join(_labels(bot.video_finalization_addon_keyboard("vi"))),
    ]
    _assert_public_clean("\n\n".join(public_parts))


def test_video_subdub_mode_updates_draft_only(monkeypatch):
    user_id = 990306
    _reset_user(user_id)
    captured = {}

    async def fake_return(query, uid, state, lang):
        captured["state"] = dict(state)
        return "returned"

    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "video_finalization_return_after_addon", fake_return)
    bot.set_video_finalization_state(user_id, {
        "source": "promptvideo",
        "selected_prompt": "Video nước hoa nam.",
        "source_video_file_id": "source-video",
        "selected_video_tier": "basic",
        "current_video_duration_seconds": 24,
        "video_finalization": {},
    })

    query = CaptureQuery("vfinal|translate_sub", user_id)
    result = asyncio.run(bot.handle_video_finalization_callback(_callback_update(query), SimpleNamespace()))

    finalization = bot.get_video_finalization_state(user_id)["video_finalization"]
    assert result == "returned"
    assert captured["state"]["source_video_file_id"] == "source-video"
    assert finalization["subtitle_enabled"] is True
    assert finalization["subtitle_mode"] == "translate_subtitle"
    assert finalization["translation_enabled"] is True
    assert finalization["dub_enabled"] is False


def test_video_subdub_returns_tools_before_invoice(monkeypatch):
    user_id = 990307
    _reset_user(user_id)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    bot.set_video_finalization_state(user_id, {
        "source": "promptvideo",
        "selected_prompt": "Video nước hoa nam.",
        "source_video_file_id": "source-video",
        "current_video_duration_seconds": 24,
        "video_finalization": {},
    })

    query = CaptureQuery("vfinal|subtitle", user_id)
    asyncio.run(bot.handle_video_finalization_callback(_callback_update(query), SimpleNamespace()))

    state = bot.get_video_finalization_state(user_id)
    assert state["step"] == "menu"
    assert query.outputs
    assert "Công cụ hoàn thiện video" in query.outputs[-1]["text"]
    assert "Hóa đơn xác nhận video" not in query.outputs[-1]["text"]
    assert "Chọn gói xuất video AI" not in query.outputs[-1]["text"]
    assert "vfinal|tier" in _callbacks(query.outputs[-1]["reply_markup"])


def test_video_subdub_returns_tools_from_invoice(monkeypatch):
    user_id = 990308
    _reset_user(user_id)

    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    bot.set_video_finalization_state(user_id, {
        "source": "promptvideo",
        "selected_prompt": "Video nước hoa nam.",
        "source_video_file_id": "source-video",
        "selected_video_tier": "basic",
        "current_video_duration_seconds": 24,
        "addon_return_target": "invoice",
        "video_finalization": {},
    })

    query = CaptureQuery("vfinal|subtitle", user_id)
    result = asyncio.run(bot.handle_video_finalization_callback(_callback_update(query), SimpleNamespace()))

    assert result is not None
    state = bot.get_video_finalization_state(user_id)
    assert state["step"] == "menu"
    assert state["selected_video_tier"] == "basic"
    assert state["video_finalization"]["subtitle_enabled"] is True
    assert state["video_finalization"]["subtitle_dub_choice"] == "subtitle"
    assert "Công cụ hoàn thiện video" in query.outputs[-1]["text"]
    assert "Chọn gói xuất video AI" not in query.outputs[-1]["text"]
    assert "vfinal|tier" in _callbacks(query.outputs[-1]["reply_markup"])


def test_video_subdub_preserves_source_package_duration_direction(monkeypatch):
    user_id = 990309
    _reset_user(user_id)

    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    bot.set_video_finalization_state(user_id, {
        "source": "selfscene",
        "selected_prompt": "Video đổi cảnh sản phẩm.",
        "source_video_file_id": "source-video-file",
        "source_file_id": "source-file-id",
        "source_file_name": "input.mp4",
        "selected_video_tier": "standard",
        "current_video_duration_seconds": 42,
        "object_prompt": "chai nước hoa",
        "direction_prompt": "slow push in",
        "source_payload": {
            "source_file_id": "source-file-id",
            "source_video_file_id": "source-video-file",
            "object_prompt": "chai nước hoa",
            "direction_prompt": "slow push in",
        },
        "addon_return_target": "invoice",
        "video_finalization": {},
    })

    query = CaptureQuery("vfinal|combo", user_id)
    asyncio.run(bot.handle_video_finalization_callback(_callback_update(query), SimpleNamespace()))
    state = bot.get_video_finalization_state(user_id)
    payload = state["source_payload"]

    assert state["step"] == "menu"
    assert state["selected_video_tier"] == "standard"
    assert payload["source_file_id"] == "source-file-id"
    assert payload["source_video_file_id"] == "source-video-file"
    assert payload["object_prompt"] == "chai nước hoa"
    assert payload["direction_prompt"] == "slow push in"
    assert state["video_finalization"]["subtitle_enabled"] is True
    assert state["video_finalization"]["dub_enabled"] is True
    assert state["video_finalization"]["subtitle_dub_choice"] == "subtitle_plus_dubbing"
    assert "Công cụ hoàn thiện video" in query.outputs[-1]["text"]
    assert "Chọn gói xuất video AI" not in query.outputs[-1]["text"]
    assert "vfinal|tier" in _callbacks(query.outputs[-1]["reply_markup"])


def test_subtitle_preview_max_6_seconds():
    assert bot.paid_preview_seconds(120) == 6
    assert bot.paid_preview_seconds(999) == 6


def test_dubbing_preview_max_6_seconds():
    assert bot.paid_preview_seconds(18) == 6
    assert bot.paid_task_requires_preview("dubbing", {"price_xu": 250})


def test_no_full_translation_output_before_final_confirm():
    preconfirm = _source_between("async def handle_video_dubbing_callback", "    confirm_modes = {")
    assert "execute_video_dubbing_pipeline" not in preconfirm
    assert "reply_document" not in preconfirm
    assert "reply_audio" not in preconfirm


def test_no_xu_before_final_confirm():
    preconfirm = "\n".join([
        _source_between("async def handle_video_dubbing_pending_upload", "async def handle_video_dubbing_pending_text"),
        _source_between("async def handle_video_dubbing_pending_text", "async def handle_video_dubbing_callback"),
        _source_between("async def handle_video_dubbing_callback", "    confirm_modes = {"),
    ])
    assert "spend_fixed_credit_info" not in preconfirm
    assert "deduct_dynamic_credit" not in preconfirm
    assert "public_video_mark_xu_deducted" not in preconfirm


def test_no_provider_call_before_allowed_preview_guard():
    preconfirm = _source_between("async def handle_video_dubbing_callback", "    confirm_modes = {")
    for marker in [
        "video_dubbing_download_source",
        "video_dubbing_transcribe_bytes",
        "video_dubbing_tts_bytes",
        "translate_subtitle_text",
    ]:
        assert marker not in preconfirm


def test_admin_diagnostics_can_show_sanitized_provider_status():
    source = inspect.getsource(bot.cmd_subtitle_dub_status)
    assert "is_admin_user" in source
    text = bot.subtitle_dub_status_text()
    assert "subtitle" in text.lower()
    assert "dub status" in text.lower()
    for secret_marker in ["API_KEY", "SECRET", "TOKEN=", "sk-"]:
        assert secret_marker not in text
