import asyncio
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class CaptureMessage:
    def __init__(self, *, video=None, audio=None, voice=None, document=None):
        self.chat_id = 919600
        self.message_id = 6
        self.video = video
        self.audio = audio
        self.voice = voice
        self.document = document
        self.outputs = []

    async def reply_text(self, text, **kwargs):
        item = {"text": str(text), **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(**item)


def _update(uid, message):
    return SimpleNamespace(effective_user=SimpleNamespace(id=uid), message=message)


def test_translation_center_has_only_two_main_groups():
    labels = _labels(bot.translation_menu_keyboard("vi"))
    callbacks = _callbacks(bot.translation_menu_keyboard("vi"))
    assert labels == ["🌐 Dịch ngôn ngữ", "🎬 Phụ đề / Lồng tiếng", "⬅️ Quay lại", "🏠 Menu chính"]
    assert callbacks == ["menu|translation_language_hub", "menu|translation_video_factory", "menu|main", "menu|main"]


def test_translation_center_hides_file_audio_video_buttons():
    ui = "\n".join(_labels(bot.translation_menu_keyboard("vi")))
    for hidden in ("Dịch phụ đề / Video", "Dịch file", "Dịch audio", "Dịch phụ đề file", "SRT/VTT/TXT"):
        assert hidden not in ui


def test_subtitle_dub_center_has_video_file_audio_flows():
    labels = _labels(bot.video_dubbing_menu_keyboard("vi", "translation"))
    callbacks = _callbacks(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert labels == [
        "🎬 Tạo phụ đề tự động",
        "🌐 Dịch phụ đề video",
        "🎙 Lồng tiếng video",
        "🎞 Phụ đề + Lồng tiếng",
        "📄 Dịch file",
        "🎧 Dịch audio",
        "⬅️ Trung tâm dịch",
        "🏠 Menu chính",
    ]
    assert "menu|translation_media_file" in callbacks
    assert "menu|translation_media_audio" in callbacks
    assert "menu|translate" in callbacks


def test_file_audio_flows_moved_inside_subtitle_dub_center():
    top_callbacks = _callbacks(bot.translation_menu_keyboard("vi"))
    center_callbacks = _callbacks(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert "menu|translation_document" not in top_callbacks
    assert "menu|translation_voice" not in top_callbacks
    assert "menu|translation_subtitle_file" not in top_callbacks
    assert "menu|translation_media_file" in center_callbacks
    assert "menu|translation_media_audio" in center_callbacks


def test_language_translation_does_not_show_file_audio_routes():
    labels = _labels(bot.translation_language_hub_keyboard("vi"))
    callbacks = _callbacks(bot.translation_language_hub_keyboard("vi"))
    assert "📄 Tài liệu" not in labels
    assert "🎧 Audio" not in labels
    assert "🧾 Transcript" not in labels
    assert "menu|translation_document" not in callbacks
    assert "menu|translation_voice" not in callbacks
    assert "menu|translation_transcript" not in callbacks


def test_media_file_and_audio_set_isolated_context():
    uid_file = 919601
    uid_audio = 919602
    bot.clear_translation_menu_pending(uid_file)
    bot.clear_translation_menu_pending(uid_audio)
    text, markup = bot.localized_menu_content("translation_media_file", False, "vi", user_id=uid_file)
    assert "Dịch file" in text
    assert "menu|translation_video_factory" in _callbacks(markup)
    assert bot.get_translation_menu_pending(uid_file)["translation_context"] == "translate_file"
    text, markup = bot.localized_menu_content("translation_media_audio", False, "vi", user_id=uid_audio)
    assert "Dịch audio" in text
    assert "menu|translation_video_factory" in _callbacks(markup)
    assert bot.get_translation_menu_pending(uid_audio)["translation_context"] == "translate_audio"


def test_file_translation_does_not_start_video_flow(monkeypatch):
    uid = 919603
    bot.clear_translation_menu_pending(uid)
    bot.clear_video_dubbing_pending(uid)
    bot.set_translation_menu_pending(uid, "media_file", translation_context="translate_file")
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    message = CaptureMessage(video=SimpleNamespace(file_id="video-file"))
    handled = asyncio.run(bot.handle_translation_media_pending_upload(_update(uid, message), SimpleNamespace()))
    assert handled is True
    assert "chỉ dùng để dịch file" in message.outputs[-1]["text"]
    assert not bot.get_video_dubbing_pending(uid)


def test_audio_translation_does_not_start_video_flow(monkeypatch):
    uid = 919604
    bot.clear_translation_menu_pending(uid)
    bot.clear_video_dubbing_pending(uid)
    bot.set_translation_menu_pending(uid, "media_audio", translation_context="translate_audio")
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    message = CaptureMessage(video=SimpleNamespace(file_id="video-file"))
    handled = asyncio.run(bot.handle_translation_media_pending_upload(_update(uid, message), SimpleNamespace()))
    assert handled is True
    assert "chỉ dùng để dịch audio" in message.outputs[-1]["text"]
    assert not bot.get_video_dubbing_pending(uid)


def test_every_video_subflow_back_returns_subtitle_dub_center():
    for mode in (
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    ):
        callbacks = _callbacks(bot.video_dubbing_source_keyboard("vi", {"mode": mode, "origin": "translation"}))
        assert "videodub|back_type" in callbacks
        labels = _labels(bot.video_dubbing_source_keyboard("vi", {"mode": mode, "origin": "translation"}))
        assert "⬅️ Phụ đề / Lồng tiếng" in labels


def test_subtitle_plus_dub_two_path_screen_restored():
    labels = _labels(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "origin": "translation"}))
    callbacks = _callbacks(bot.video_dubbing_source_keyboard("vi", {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "origin": "translation"}))
    assert "🎞 Video đã có phụ đề" in labels
    assert "🎧 Video chưa có phụ đề" in labels
    assert f"videodub|path|{bot.VIDEO_DUBBING_FLOW_HAS_SUBTITLE}" in callbacks
    assert f"videodub|path|{bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE}" in callbacks


def test_no_random_cross_route_callbacks():
    top = set(_callbacks(bot.translation_menu_keyboard("vi")))
    center = set(_callbacks(bot.video_dubbing_menu_keyboard("vi", "translation")))
    assert not {"menu|translation_media_file", "menu|translation_media_audio"}.intersection(top)
    assert {"menu|translation_media_file", "menu|translation_media_audio"}.issubset(center)
    assert "videodub|type|subtitle_translate" not in top
