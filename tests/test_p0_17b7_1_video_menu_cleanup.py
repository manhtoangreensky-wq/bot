import inspect

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _rows(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def _menu_sources():
    return "\n".join(
        [
            inspect.getsource(bot.main_video_keyboard),
            inspect.getsource(bot.video_prompt_library_text),
            inspect.getsource(bot.video_prompt_library_keyboard),
            inspect.getsource(bot.video_prompt_library_guard_text),
            inspect.getsource(bot.handle_video_prompt_library_callback),
            inspect.getsource(bot.video_numbered_choice_keyboard),
        ]
    )


def test_video_menu_hides_music_voice_sfx_public():
    assert "🎵 Nhạc / Voice / SFX" not in _labels(bot.main_video_keyboard("vi"))


def test_video_menu_hides_video_sample_channel_public():
    assert "📥 Video mẫu / Kênh mẫu" not in _labels(bot.main_video_keyboard("vi"))
    assert "vproduct|open|video_reference" not in _callbacks(bot.main_video_keyboard("vi"))


def test_video_menu_hides_prompt_motion_public():
    labels = _labels(bot.main_video_keyboard("vi"))
    assert "🎥 Prompt / Chuyển động" not in labels
    assert "vproduct|open|motion_prompt" not in _callbacks(bot.main_video_keyboard("vi"))


def test_video_menu_has_prompt_library():
    labels = _labels(bot.main_video_keyboard("vi"))
    callbacks = _callbacks(bot.main_video_keyboard("vi"))
    assert "📚 Kho prompt video" in labels
    assert "vpromptlib|start" in callbacks
    assert "Kho prompt video" in bot.video_prompt_library_text("vi")


def test_video_menu_has_video_downloader():
    labels = _labels(bot.main_video_keyboard("vi"))
    callbacks = _callbacks(bot.main_video_keyboard("vi"))
    assert "📥 Tải video từ link" in labels
    assert "vdownload|start" in callbacks


def test_video_downloader_not_in_translation_dub_studio():
    labels = _labels(bot.video_dubbing_menu_keyboard("vi", "translation"))
    callbacks = _callbacks(bot.video_dubbing_menu_keyboard("vi", "translation"))
    assert "📥 Tải video từ link" not in labels
    assert "🔗 Tải video từ link" not in labels
    assert "vdownload|start" not in callbacks
    assert "videodub|link_start" not in callbacks


def test_prompt_library_does_not_require_media_upload():
    text = bot.video_prompt_library_text("vi")
    assert "Không cần gửi file/media" in text
    assert "Chưa xử lý video thật" in text


def test_prompt_library_no_provider_call():
    source = _menu_sources()
    for forbidden in ("shopaikey", "key4u", "AgentGemini", "OpenAI", "execute_engine(", "provider_job"):
        assert forbidden not in source


def test_prompt_library_no_xu_charge():
    source = _menu_sources()
    for forbidden in ("spend_fixed_credit_info", "deduct_dynamic_credit", "refund_charged_credit", "update_user_credits"):
        assert forbidden not in source
    assert "không trừ Xu" in bot.video_prompt_library_text("vi")


def test_numbered_video_choice_buttons_align_single_row_for_five():
    markup = bot.video_numbered_choice_keyboard([(str(i), f"x|{i}") for i in range(1, 6)], "vi", main=False)
    assert _rows(markup) == [["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]]


def test_numbered_video_choice_buttons_align_three_by_three_for_six():
    markup = bot.video_numbered_choice_keyboard([(str(i), f"x|{i}") for i in range(1, 7)], "vi", main=False)
    assert _rows(markup) == [["1️⃣", "2️⃣", "3️⃣"], ["4️⃣", "5️⃣", "6️⃣"]]


def test_numbered_video_choice_buttons_align_four_by_four_for_eight():
    markup = bot.video_numbered_choice_keyboard([(str(i), f"x|{i}") for i in range(1, 9)], "vi", main=False)
    assert _rows(markup) == [["1️⃣", "2️⃣", "3️⃣", "4️⃣"], ["5️⃣", "6️⃣", "7️⃣", "8️⃣"]]


def test_video_menu_does_not_touch_subtitle_dub_flow():
    labels = set(_labels(bot.video_dubbing_menu_keyboard("vi", "translation")))
    assert {
        "🎬 Tạo phụ đề tự động",
        "🌐 Dịch phụ đề",
        "🎙 Lồng tiếng",
        "🎞 Phụ đề + Lồng tiếng",
    }.issubset(labels)
    assert "📄 Dịch file phụ đề" not in labels
    assert "🧾 Bóc lời thoại" not in labels
    assert "📥 Tải video từ link" not in labels


def test_video_menu_does_not_touch_image_flow():
    labels = _labels(bot.main_image_keyboard("vi"))
    callbacks = _callbacks(bot.main_image_keyboard("vi"))
    assert "🖼 Tạo ảnh nhanh" in labels
    assert "create_media|quick_image" in callbacks
    assert "vpromptlib|start" not in callbacks


def test_video_menu_does_not_touch_music_flow():
    labels = _labels(bot.main_video_keyboard("vi"))
    assert "🎵 Nhạc / Voice / SFX" not in labels
    assert "music_quick" not in inspect.getsource(bot.main_video_keyboard)


def test_video_menu_does_not_touch_payment():
    source = _menu_sources()
    for forbidden in ("payos", "naptien", "payment", "wallet", "ledger"):
        assert forbidden not in source.lower()
