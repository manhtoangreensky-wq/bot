import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


def test_main_menu_vi_labels_are_natural_and_balanced():
    markup = bot.localized_main_menu_keyboard(False, "vi")
    labels = _labels(markup)

    assert "🎙 Voice Studio" in labels
    assert "🎵 Music Studio" in labels
    assert "🌐 Dịch / Phụ đề / Lồng tiếng Studio" in labels
    assert "🌐 Trung tâm" in labels
    assert "🎙 Voice / Nhạc" not in labels
    assert "🌐 Hub" not in labels
    assert all(len(row) == 2 for row in markup.inline_keyboard[:-1])
    assert len(markup.inline_keyboard[-1]) == 1
    assert "🔐 Admin" not in labels


def test_main_menu_en_labels_do_not_mix_vietnamese_public_terms():
    labels = _labels(bot.localized_main_menu_keyboard(False, "en"))

    assert "🆓 Free tools" in labels
    assert "📝 Notes / Docs" in labels
    assert "🎬 AI Video" in labels
    assert "🎙 Voice Studio" in labels
    assert "🎵 Music Studio" in labels
    assert "🌐 Translation / Subtitle / Dubbing Studio" in labels
    assert "💬 Feedback / Bug" in labels
    assert "📝 Ghi chú / Tài liệu" not in labels
    assert "🎙 Giọng nói / Nhạc" not in labels


def test_storyboard_pack_i18n_guard_and_back_callbacks():
    vi_guard = bot.storyboard_pack_guard_text("create_video_ai", "vi")
    en_guard = bot.storyboard_pack_guard_text("create_video_ai", "en")

    assert "TOAN AAS chưa bắt đầu xử lý" in vi_guard
    assert "No processing has started" in en_guard

    callbacks = _callbacks(bot.storyboard_pack_result_keyboard("vi"))
    assert "storypack|back_concepts" in callbacks
    assert "vfinal|export_local" not in callbacks
