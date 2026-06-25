import asyncio
import inspect
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class CaptureQuery:
    def __init__(self, data: str, user_id: int = 175510):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(chat_id=user_id, outputs=[])

    async def answer(self, *args, **kwargs):
        self.message.outputs.append({"answer": args, **kwargs})

    async def edit_message_text(self, text, parse_mode=None, reply_markup=None):
        self.message.outputs.append({"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup})
        return SimpleNamespace(text=text, reply_markup=reply_markup)


def _configured_translation_dub(monkeypatch):
    monkeypatch.setattr(bot, "TRANSLATION_DUB_MAINTENANCE", False)
    monkeypatch.setattr(
        bot,
        "get_asr_adapter_readiness",
        lambda public=True: {
            "configured": True,
            "ready": True,
            "public_ready": False,
            "adapter": "deepgram",
            "supports_audio": True,
            "supports_video": True,
        },
    )
    monkeypatch.setattr(bot, "video_translation_provider_configured", lambda: True)
    monkeypatch.setattr(bot, "video_tts_provider_configured_for_dub", lambda: True)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")


def test_translate_menu_no_disable_auto_translate_button():
    labels = _labels(bot.translation_language_hub_keyboard("vi"))
    callbacks = _callbacks(bot.translation_language_hub_keyboard("vi"))

    assert "⏹ Tắt dịch tự động" not in labels
    assert "menu|translation_stop_session" not in callbacks


def test_translate_menu_keeps_other_buttons():
    labels = _labels(bot.translation_language_hub_keyboard("vi"))

    for label in [
        "🔁 Dịch 2 chiều",
        "💬 Hội thoại",
        "📝 Văn bản",
        "📄 Tài liệu",
        "🎧 Audio",
        "⚙️ Ngôn ngữ",
        "🌐 Dịch tự động",
        "🧾 Transcript",
        "⬅️ Trung tâm",
        "🏠 Menu chính",
    ]:
        assert label in labels


def test_no_maintenance_guard_by_default(monkeypatch):
    _configured_translation_dub(monkeypatch)

    readiness = bot.video_dubbing_capability(
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE, "source_file_name": "sample.mp4"},
        public=True,
    )
    text = bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_CREATE, {"source_file_name": "sample.mp4"}, "vi")

    assert readiness["ok"] is True
    assert "bảo trì/nâng cấp" not in text
    assert "mode_disabled" not in text
    assert "asr_adapter_missing" not in text


def test_maintenance_guard_only_when_env_true(monkeypatch):
    _configured_translation_dub(monkeypatch)
    monkeypatch.setattr(bot, "TRANSLATION_DUB_MAINTENANCE", True)

    readiness = bot.video_dubbing_capability(bot.VIDEO_SUBTITLE_MODE_DUB, {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}, public=True)
    text = bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_DUB, {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}, "vi")

    assert readiness["ok"] is False
    assert "maintenance" in readiness["missing"]
    assert "bảo trì/nâng cấp" in text


def test_subtitle_studio_not_blocked_when_asr_configured(monkeypatch):
    _configured_translation_dub(monkeypatch)

    assert bot.video_dubbing_public_processing_ready(
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE, "source_file_name": "sample.mp4"},
    ) is True


def test_dub_studio_not_blocked_when_tts_configured(monkeypatch):
    _configured_translation_dub(monkeypatch)

    assert bot.video_dubbing_public_processing_ready(
        bot.VIDEO_SUBTITLE_MODE_DUB,
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "source_kind": "subtitle_file"},
    ) is True


def test_each_tool_has_separate_active_flow():
    assert bot.video_dubbing_active_flow_for_mode(bot.VIDEO_SUBTITLE_MODE_CREATE) == "auto_subtitle"
    assert bot.video_dubbing_active_flow_for_mode(bot.VIDEO_SUBTITLE_MODE_TRANSLATE) == "subtitle_translate"
    assert bot.video_dubbing_active_flow_for_mode(bot.VIDEO_SUBTITLE_MODE_DUB) == "dub_audio"
    assert bot.video_dubbing_active_flow_for_mode(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB) == "subtitle_plus_dub"


def test_video_translation_menu_has_separate_tool_buttons():
    labels = _labels(bot.video_dubbing_menu_keyboard("vi", "translation"))
    callbacks = _callbacks(bot.video_dubbing_menu_keyboard("vi", "translation"))

    assert "👁 Tạo phụ đề tự động" in labels
    assert "🌐 Dịch phụ đề" in labels
    assert "🎙 Lồng tiếng" in labels
    assert "🎬 Phụ đề + lồng tiếng" in labels
    assert f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_CREATE}" in callbacks
    assert f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_TRANSLATE}" in callbacks
    assert f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_DUB}" in callbacks
    assert f"videodub|type|{bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}" in callbacks


def test_tool_name_buttons_start_matching_active_flow(monkeypatch):
    _configured_translation_dub(monkeypatch)
    uid = 175511
    cases = [
        (bot.VIDEO_SUBTITLE_MODE_CREATE, "auto_subtitle"),
        (bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "subtitle_translate"),
        (bot.VIDEO_SUBTITLE_MODE_DUB, "dub_audio"),
        (bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "subtitle_plus_dub"),
    ]

    for mode, active_flow in cases:
        bot.clear_video_dubbing_pending(uid)
        bot.set_video_dubbing_pending(uid, "menu", origin="translation")
        query = CaptureQuery(f"videodub|type|{mode}", uid)
        asyncio.run(bot.handle_video_dubbing_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
        state = bot.get_video_dubbing_pending(uid)
        assert state["mode"] == mode
        assert state["active_flow"] == active_flow
        assert state["step"] == "source"
        assert not any("bảo trì/nâng cấp" in item.get("text", "") for item in query.message.outputs)


def test_dub_button_starts_dub_flow_not_auto_subtitle():
    text = bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_DUB}, "vi")
    labels = _labels(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_DUB}))

    assert "Lồng tiếng" in text
    assert "📄 Gửi SRT/VTT/TXT" in labels
    assert "🕘 Dùng phụ đề vừa tạo" in labels
    assert bot.video_dubbing_active_flow_for_mode(bot.VIDEO_SUBTITLE_MODE_DUB) != "auto_subtitle"


def test_active_studio_media_not_generic_video_menu():
    source = inspect.getsource(bot.handle_media_cache_only)

    assert source.index("handle_video_dubbing_pending_upload") < source.index("handle_video_product_pending_media")
    assert source.index("handle_translation_studio_lost_state_media") < source.index("handle_video_product_pending_media")


def test_public_no_mode_disabled_or_asr_adapter_missing(monkeypatch):
    monkeypatch.setattr(bot, "TRANSLATION_DUB_MAINTENANCE", False)
    monkeypatch.setattr(
        bot,
        "get_asr_adapter_readiness",
        lambda public=True: {"configured": False, "adapter": "none"},
    )

    text = bot.video_dubbing_guard_text(bot.VIDEO_SUBTITLE_MODE_CREATE, {"source_file_name": "sample.mp4"}, "vi", admin=False)

    assert "mode_disabled" not in text
    assert "asr_adapter_missing" not in text
    assert "bảo trì/nâng cấp" not in text
    assert "provider" not in text.lower()


def test_no_pipeline_terms_in_public_tool_messages():
    public = "\n".join(
        [
            bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_CREATE}, "vi"),
            bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE}, "vi"),
            bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_DUB}, "vi"),
            bot.video_dubbing_source_text({"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}, "vi"),
        ]
    ).lower()

    for term in ("asr segment", "tts segment", "timeline audio", "mux", "smoke", "provider", "mode_disabled", "asr_adapter_missing"):
        assert term not in public
