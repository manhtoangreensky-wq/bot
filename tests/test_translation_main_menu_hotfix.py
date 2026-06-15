import asyncio
import inspect
from types import SimpleNamespace

import bot


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return {button.callback_data for button in _buttons(markup) if button.callback_data}


def test_main_menu_has_translation_button_and_public_rows_are_balanced():
    for lang in ("vi", "en", "zh"):
        public = bot.localized_main_menu_keyboard(False, lang)
        callbacks = _callbacks(public)
        assert "menu|translate" in callbacks
        assert "back_lang" not in callbacks
        assert "menu|admin" not in callbacks
        assert all(len(row) == 2 for row in public.inline_keyboard)

        admin = bot.localized_main_menu_keyboard(True, lang)
        assert admin.inline_keyboard[-1][0].callback_data == "menu|admin"
        assert len(admin.inline_keyboard[-1]) == 1
        assert all(len(row) == 2 for row in admin.inline_keyboard[:-1])


def test_language_entry_is_in_account_and_translation_menu_opens():
    account_callbacks = _callbacks(bot.main_profile_keyboard("vi"))
    assert "back_lang" in account_callbacks

    text, markup = bot.localized_menu_content("translate", False, "vi", user_id=123)
    callbacks = _callbacks(markup)
    assert "Dịch thuật TOAN AAS" in text
    assert callbacks == {
        "menu|translation_text",
        "menu|translation_document",
        "videodub|type|subtitle_translate",
        "videodub|type|subtitle_plus_dub",
        "menu|translation_transcript",
        "menu|translation_language",
        "menu|main",
    }


def test_translation_child_callbacks_have_handlers_or_existing_routes():
    source = inspect.getsource(bot)
    assert 'CallbackQueryHandler(handle_menu_callback, pattern=r"^menu\\|")' in source
    assert 'CallbackQueryHandler(handle_video_dubbing_callback, pattern=r"^videodub\\|")' in source
    assert 'if action in {"translation_text", "translation_transcript"}' in source
    assert 'if action == "translation_document"' in source
    assert 'if action == "translation_language"' in source
    assert 'VIDEO_SUBTITLE_MODE_TRANSLATE = "subtitle_translate"' in source
    assert 'VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB = "subtitle_plus_dub"' in source


def test_translation_text_pending_routes_without_charging(monkeypatch):
    user_id = 812345
    bot.clear_translation_menu_pending(user_id)
    bot.set_translation_menu_pending(user_id, "text")
    saved = {}

    def fake_save(uid, source_type, source_text="", source_ref=None):
        saved.update(user_id=uid, source_type=source_type, source_text=source_text)

    async def fake_picker(update, source_type, edit=False, more=False):
        saved.update(picker_source=source_type)

    monkeypatch.setattr(bot, "save_translation_request", fake_save)
    monkeypatch.setattr(bot, "show_translation_picker", fake_picker)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        message=SimpleNamespace(text="Translate this short text"),
    )

    assert asyncio.run(bot.handle_translation_menu_pending_text(update, SimpleNamespace())) is True
    assert saved == {
        "user_id": user_id,
        "source_type": "text",
        "source_text": "Translate this short text",
        "picker_source": "text",
    }
    assert not bot.get_translation_menu_pending(user_id)
    handler_source = inspect.getsource(bot.handle_translation_menu_pending_text)
    assert "deduct" not in handler_source
    assert "spend_" not in handler_source


def test_language_menu_remains_accessible_from_translation_and_account():
    translation_callbacks = _callbacks(bot.translation_language_options_keyboard("vi"))
    assert "menu|translation_auto_target" in translation_callbacks
    assert "back_lang" in translation_callbacks
    assert "back_lang" in _callbacks(bot.main_profile_keyboard("vi"))
