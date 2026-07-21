import asyncio
import inspect
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


def _rows(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


class CaptureMessage:
    def __init__(self):
        self.outputs = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        self.outputs.append(
            {
                "text": str(text),
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
                **kwargs,
            }
        )
        return SimpleNamespace(text=text, reply_markup=reply_markup)


def test_translate_language_menu_layout_adds_file_and_audio():
    markup = bot.translation_language_hub_keyboard("vi")

    assert _rows(markup) == [
        ["📝 Văn bản", "📄 Dịch file"],
        ["🎧 Dịch audio", "💬 Hội thoại"],
        ["🔁 Dịch 2 chiều", "🌐 Dịch tự động"],
        ["⚙️ Ngôn ngữ", "⏹ Tắt dịch tự động"],
        ["⬅️ Trung tâm", "🏠 Menu chính"],
    ]
    assert "menu|translation_media_file" in _callbacks(markup)
    assert "menu|translation_media_audio" in _callbacks(markup)


def test_translate_language_menu_keeps_existing_language_tools():
    labels = _labels(bot.translation_language_hub_keyboard("vi"))

    for expected in (
        "📝 Văn bản",
        "💬 Hội thoại",
        "🔁 Dịch 2 chiều",
        "🌐 Dịch tự động",
        "⚙️ Ngôn ngữ",
        "⏹ Tắt dịch tự động",
        "⬅️ Trung tâm",
        "🏠 Menu chính",
    ):
        assert expected in labels


def test_subdub_menu_removes_file_and_audio_but_keeps_video_tools():
    markup = bot.video_dubbing_menu_keyboard("vi", "translation")
    labels = _labels(markup)

    assert _rows(markup) == [
        ["🎬 Tạo phụ đề tự động", "🌐 Dịch phụ đề video"],
        ["🎙 Lồng tiếng video", "🎞 Phụ đề + Lồng tiếng"],
        ["⬅️ Trung tâm dịch", "🏠 Menu chính"],
    ]
    assert "📄 Dịch file" not in labels
    assert "🎧 Dịch audio" not in labels
    assert "menu|translation_media_file" not in _callbacks(markup)
    assert "menu|translation_media_audio" not in _callbacks(markup)


def test_file_and_audio_callbacks_use_existing_translation_flows():
    file_text, file_markup = bot.localized_menu_content("translation_media_file", False, "vi")
    audio_text, audio_markup = bot.localized_menu_content("translation_media_audio", False, "vi")

    assert "Dịch file" in file_text
    assert "Dịch audio" in audio_text
    assert "⬅️ Dịch ngôn ngữ" in _labels(file_markup)
    assert "⬅️ Dịch ngôn ngữ" in _labels(audio_markup)
    assert "menu|translation_language_hub" in _callbacks(file_markup)
    assert "menu|translation_language_hub" in _callbacks(audio_markup)


def test_translate_command_opens_language_hub(monkeypatch):
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "enter_product_context", lambda *args, **kwargs: None)
    message = CaptureMessage()
    update = SimpleNamespace(
        callback_query=None,
        effective_user=SimpleNamespace(id=42002),
        message=message,
    )
    context = SimpleNamespace(args=[])

    asyncio.run(bot.cmd_translate(update, context))

    assert message.outputs
    output = message.outputs[-1]
    assert "Dịch ngôn ngữ" in output["text"]
    assert "📄 Dịch file" in _labels(output["reply_markup"])
    assert "🎧 Dịch audio" in _labels(output["reply_markup"])


def test_translate_voice_still_uses_audio_translation_picker():
    source = inspect.getsource(bot.cmd_translate_voice)

    assert 'show_translation_picker(update, "voice")' in source
    assert bot.PUBLIC_COMMAND_FUNCTIONS["translate_voice"] == "cmd_translate_voice"


def test_public_translation_menus_do_not_expose_debug_terms():
    text = "\n".join(
        [
            bot.translation_language_hub_text("vi"),
            bot.translation_menu_text("vi"),
            bot.video_dubbing_menu_text("vi", "translation"),
        ]
        + _labels(bot.translation_language_hub_keyboard("vi"))
        + _labels(bot.video_dubbing_menu_keyboard("vi", "translation"))
    ).lower()

    forbidden = ("provider", "api", "handler", "callback", "debug", "admin")
    assert not any(term in text for term in forbidden)
