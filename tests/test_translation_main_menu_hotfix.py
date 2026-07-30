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
        assert len(admin.inline_keyboard[-2]) == 2
        assert all(len(row) == 2 for row in admin.inline_keyboard[:-1])


def test_language_entry_is_in_account_and_translation_menu_opens():
    account_callbacks = _callbacks(bot.main_profile_keyboard("vi"))
    assert "back_lang" in account_callbacks

    text, markup = bot.localized_menu_content("translate", False, "vi", user_id=123)
    callbacks = _callbacks(markup)
    assert "Trung tâm dịch" in text
    assert callbacks == {
        "menu|translation_language_hub",
        "menu|translation_video_factory",
        "menu|main",
    }

    language_text, language_markup = bot.localized_menu_content(
        "translation_language_hub", False, "vi", user_id=123
    )
    language_callbacks = _callbacks(language_markup)
    assert "Dịch ngôn ngữ" in language_text
    assert {
        "menu|translation_text",
        "menu|translation_media_file",
        "menu|translation_media_audio",
        "menu|translation_two_way",
        "menu|translation_live_conversation",
        "menu|translation_language",
        "menu|translation_auto_target",
        "menu|translation_stop_session",
        "menu|main",
        "menu|translate",
    }.issubset(language_callbacks)
    assert "menu|translation_voice" not in language_callbacks
    assert "menu|translation_document" not in language_callbacks
    assert "menu|translation_transcript" not in language_callbacks


def test_translation_child_callbacks_have_handlers_or_existing_routes():
    source = inspect.getsource(bot)
    assert 'CallbackQueryHandler(handle_menu_callback, pattern=r"^menu\\|")' in source
    assert 'CallbackQueryHandler(handle_video_dubbing_callback, pattern=r"^videodub\\|")' in source
    assert 'if action == "translation_text"' in source
    assert 'if action == "translation_transcript"' in source
    assert 'if action == "translation_voice"' in source
    assert 'if action == "translation_two_way"' in source
    assert 'if action == "translation_live_conversation"' in source
    assert 'if action == "translation_document"' in source
    assert 'if action == "translation_language"' in source
    assert 'if action == "translation_video_factory"' in source
    assert 'if action.startswith("translation_pair_source_") or action.startswith("translation_pair_target_")' in source
    assert 'if action.startswith("translation_pair_start_")' in source
    assert 'if action in {"translation_stop_session", "translation_cancel"}' in source
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


def test_translation_text_confirm_keeps_pending_until_executor(monkeypatch):
    user_id = 812350
    bot.clear_translation_menu_pending(user_id)
    bot.set_translation_menu_pending(
        user_id,
        "text_confirm",
        target_language="en",
        source_text="Xin chao khach hang",
        confirm_token="confirm-token",
    )
    executed = {}

    class Query:
        data = "menu|translation_text_confirm"
        from_user = SimpleNamespace(id=user_id)
        message = SimpleNamespace(chat_id=user_id)

        def __init__(self):
            self.edits = []

        async def answer(self, *args, **kwargs):
            return None

        async def edit_message_text(self, text, **kwargs):
            self.edits.append((text, kwargs))

    async def fake_run(update, context, source_text, target):
        executed.update(source_text=source_text, target=target)
        return "translation-executed"

    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "run_translate_text_to_target", fake_run)
    query = Query()

    result = asyncio.run(
        bot.handle_menu_callback(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(),
        )
    )

    assert result == "translation-executed"
    assert executed == {
        "source_text": "Xin chao khach hang",
        "target": "en",
    }
    assert not bot.get_translation_menu_pending(user_id)
    assert query.edits == []


def test_language_menu_remains_accessible_from_translation_and_account():
    translation_callbacks = _callbacks(bot.translation_language_options_keyboard("vi"))
    assert "menu|translation_auto_target" in translation_callbacks
    assert "back_lang" in translation_callbacks
    assert "back_lang" in _callbacks(bot.main_profile_keyboard("vi"))


def test_full_translation_hub_has_voice_two_way_live_and_video_branch():
    text, markup = bot.localized_menu_content("translate", False, "vi", user_id=123)
    callbacks = _callbacks(markup)
    assert "Trung tâm dịch" in text
    assert "menu|translation_language_hub" in callbacks
    assert "menu|translation_video_factory" in callbacks
    assert "menu|translation_video_dub_menu" not in callbacks
    assert "menu|translation_document" not in callbacks
    assert "menu|translation_voice" not in callbacks
    assert "menu|translation_subtitle_file" not in callbacks
    assert "videodub|type|subtitle_translate" not in callbacks

    _, language_markup = bot.localized_menu_content("translation_language_hub", False, "vi", user_id=123)
    language_callbacks = _callbacks(language_markup)
    assert "menu|translation_voice" not in language_callbacks
    assert "menu|translation_two_way" in language_callbacks
    assert "menu|translation_live_conversation" in language_callbacks


def test_translation_pair_uses_separate_source_target_controls():
    user_id = 812348
    bot.clear_translation_pair_drafts(user_id)
    bot.set_translation_pair_draft(user_id, "two_way", source="vi", target="en")
    markup = bot.translation_pair_keyboard("two_way", "vi", user_id)
    callbacks = _callbacks(markup)
    labels = [button.text for button in _buttons(markup)]

    assert "menu|translation_pair_source_two_way" in callbacks
    assert "menu|translation_pair_target_two_way" in callbacks
    assert "menu|translation_pair_swap_two_way" in callbacks
    assert "menu|translation_pair_start_two_way" in callbacks
    assert "menu|translation_language_hub" in callbacks
    assert any("Nguồn:" in label and "Tiếng Việt" in label for label in labels)
    assert any("Dịch sang:" in label and "English" in label for label in labels)


def test_video_dubbing_back_route_tracks_entry_origin():
    translation_markup = bot.video_dubbing_menu_keyboard("vi", "translation")
    video_markup = bot.video_dubbing_menu_keyboard("vi", "video")

    assert "menu|translate" in _callbacks(translation_markup)
    assert "menu|main_video" not in _callbacks(translation_markup)
    assert "menu|main_video" in _callbacks(video_markup)

    bot.clear_video_dubbing_pending(812349)
    state = bot.set_video_dubbing_pending(812349, "menu", origin="translation")
    state = bot.set_video_dubbing_pending(812349, "language", mode="subtitle_translate")
    assert state["origin"] == "translation"


def test_language_alias_map_extended():
    assert bot.normalize_translate_target("Trung giản thể") == "zh_cn"
    assert bot.normalize_translate_target("Chinese Traditional") == "zh_tw"
    assert bot.normalize_translate_target("Tiếng Đức") == "de"
    assert bot.normalize_translate_target("Filipino") == "fil"
    assert bot.normalize_translate_target("tự nhận diện") == "auto"


def test_two_way_translation_session_text_uses_translation_provider(monkeypatch):
    user_id = 812346
    bot.clear_translation_session(user_id)
    bot.set_translation_session(user_id, "two_way", "vi", "en")
    sent = {}

    async def fake_translate(text, target):
        sent["source"] = text
        sent["target"] = target
        return {"provider": "pytest", "text": "Hello customer", "target": target}

    async def fake_reply(text, **kwargs):
        sent["reply"] = text
        sent["reply_markup"] = kwargs.get("reply_markup")

    monkeypatch.setattr(bot, "translate_to_language", fake_translate)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        message=SimpleNamespace(text="Xin chào khách hàng", reply_text=fake_reply),
    )

    assert asyncio.run(bot.handle_translation_session_text(update, SimpleNamespace())) is True
    assert sent["target"] == "en"
    assert "Hello customer" in sent["reply"]
    assert "Bot chưa trừ Xu" in sent["reply"]


def test_stop_translation_session_clears_runtime_state():
    user_id = 812347
    bot.set_translation_session(user_id, "live_conversation", "vi", "en")
    assert bot.translation_session_is_active(user_id)
    assert bot.clear_translation_session(user_id) is True
    assert not bot.translation_session_is_active(user_id)
