import re
from pathlib import Path


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"
BOT_SOURCE = BOT_PATH.read_text(encoding="utf-8")


class _Button:
    def __init__(self, text, callback_data=""):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


def _load_function(name, namespace):
    start = BOT_SOURCE.index(f"def {name}(")
    next_sync = BOT_SOURCE.find("\ndef ", start + 1)
    next_async = BOT_SOURCE.find("\nasync def ", start + 1)
    candidates = [offset for offset in (next_sync, next_async) if offset >= 0]
    end = min(candidates) if candidates else len(BOT_SOURCE)
    exec(compile(BOT_SOURCE[start:end], str(BOT_PATH), "exec"), namespace)
    return namespace[name]


def _copy(_lang):
    return {
        "voice": "🎙 Chọn giọng",
        "saved_voice": "🎙 Kho giọng đã lưu",
        "back": "⬅️ Quay lại",
        "menu": "🎬 Phụ đề / Lồng tiếng",
        "update": "🔄 Cập nhật trạng thái",
        "another": "📤 Gửi video khác",
        "main": "🏠 Menu chính",
    }


def _video_v6_keyboard(items, _lang, *, back):
    return _Markup(
        [[_Button(text, callback)] for text, callback in items]
        + [[_Button(back[0], back[1])]]
    )


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_standalone_voice_create_button_does_not_claim_to_send_another_video():
    keyboard = _load_function(
        "video_dubbing_voice_keyboard",
        {
            "normalize_user_language": lambda value: str(value or "vi"),
            "public_subdub_deep_copy": _copy,
            "normalize_video_translate_mode": lambda value: str(value or ""),
            "subtitle_plus_dub_is_active": lambda _state: False,
            "VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB": "subtitle_plus_dub",
            "subtitle_plus_dub_voice_keyboard": lambda *_args, **_kwargs: None,
            "video_v6_keyboard": _video_v6_keyboard,
            "subdub_auto_provider_capacity_ready": lambda: True,
            "subdub_auto_voice_choice": lambda _lang: ("two", "two"),
            "subdub_auto_multi_voice_choice": lambda _lang: ("multi", "multi"),
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
        },
    )
    markup = keyboard(
        "vi",
        {
            "mode": "dub",
            "video_processing_mode": "dub",
            "source_file_id": "locked-two-speaker-fixture",
        },
        include_auto=True,
    )
    buttons = _buttons(markup)
    voice_create = next(
        button for button in buttons if button.callback_data == "videodub|voice_create"
    )

    assert voice_create.text == "🎙 Tạo voice riêng"
    assert all(button.text != "📤 Gửi video khác" for button in buttons)


def test_progress_back_button_names_the_menu_its_callback_opens():
    keyboard = _load_function(
        "subdub_progress_keyboard",
        {
            "re": re,
            "normalize_user_language": lambda value: str(value or "vi"),
            "public_subdub_deep_copy": _copy,
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
        },
    )
    markup = keyboard("282347E26C", "vi")
    buttons = _buttons(markup)
    back = next(
        button for button in buttons if button.callback_data == "videodub|status_back_type"
    )

    assert back.text == "⬅️ 🎬 Phụ đề / Lồng tiếng"
    assert "Phụ đề + Lồng tiếng" not in back.text
