import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _joined(text, markup):
    return (str(text or "") + "\n" + "\n".join(_labels(markup))).lower()


def test_auto_subtitle_final_confirmation_is_public_clean():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_CREATE, "source_file_id": "video"}
    text = bot.video_dubbing_output_text(state, "vi")
    labels = _labels(bot.video_dubbing_output_keyboard("vi", state))

    assert "Tạo phụ đề tự động" in text
    assert "Đầu ra: SRT, VTT, TXT" in text
    assert "TOAN AAS chỉ xử lý sau khi anh/chị xác nhận" in text
    assert labels == ["👁 Xem thử", "✅ Xác nhận tạo đầy đủ", "⬅️ Quay lại", "🏠 Menu chính"]
    forbidden = ("tác vụ", "nguồn", "chi phí", "sửa lựa chọn", "đổi giọng", "đổi tốc độ", "admin", "curl")
    ui = _joined(text, bot.video_dubbing_output_keyboard("vi", state))
    for term in forbidden:
        assert term not in ui
    assert "📄 Xuất SRT" not in labels
    assert "🎞 Gắn vào video" not in labels


def test_auto_dubbing_final_confirmation_is_public_clean():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "source_file_id": "video",
        "target_language": "English",
        "voice_style": "giọng nữ mặc định",
        "voice_speed": "0.9",
    }
    text = bot.video_dubbing_confirm_text(state, "vi")
    labels = _labels(bot.video_dubbing_confirm_keyboard("vi", state))

    assert "Video đã sẵn sàng lồng tiếng" in text
    assert "Ngôn ngữ lồng tiếng: <b>English</b>" in text
    assert "Tốc độ: <b>0.9</b>" in text
    assert labels == ["▶️ Nghe thử", "✅ Xác nhận tạo đầy đủ", "⬅️ Quay lại", "🏠 Menu chính"]
    ui = _joined(text, bot.video_dubbing_confirm_keyboard("vi", state))
    for term in ("tác vụ", "nguồn", "chi phí dự kiến", "sửa lựa chọn", "đổi giọng", "đổi tốc độ", "admin", "curl"):
        assert term not in ui


def test_subtitle_plus_stage_a_hides_export_until_subtitle_result_exists():
    pending = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "source_file_id": "video",
        "target_language": "Tiếng Việt",
    }
    pending_labels = _labels(bot.video_dubbing_output_keyboard("vi", pending))
    assert pending_labels == ["👁 Xem thử", "✅ Xác nhận tạo đầy đủ", "⬅️ Quay lại", "🏠 Menu chính"]
    assert "🗣 Tiếp tục lồng tiếng" not in pending_labels

    ready = {**pending, "translated_subtitle_ref": "video_dubbing_artifact:test:translated"}
    ready_labels = _labels(bot.video_dubbing_output_keyboard("vi", ready))
    assert "📄 Xuất SRT" in ready_labels
    assert "🎞 Gắn phụ đề vào video" in ready_labels
    assert "🗣 Tiếp tục lồng tiếng" in ready_labels


def test_guard_public_buttons_are_clean_and_back_preserves_source():
    labels = _labels(bot.video_dubbing_guard_keyboard("vi", admin=False))
    callbacks = _callbacks(bot.video_dubbing_guard_keyboard("vi", admin=False))
    assert labels == ["⬅️ Quay lại", "🏠 Menu chính"]
    assert callbacks == ["videodub|guard_back", "menu|main"]

    uid = "task25-back"
    bot.clear_video_dubbing_pending(uid)
    bot.set_video_dubbing_pending(
        uid,
        "preview_guarded",
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
        source_file_id="kept-video",
        voice_style="giọng nữ mặc định",
        target_language="English",
        voice_speed="1.0",
    )
    state = bot.set_video_dubbing_pending(uid, bot.video_dubbing_back_route(bot.get_video_dubbing_pending(uid), "guard_back"))
    assert state["step"] == "confirm"
    assert state["source_file_id"] == "kept-video"


def test_preview_ready_screen_has_only_full_back_main():
    for mode in (bot.VIDEO_SUBTITLE_MODE_CREATE, bot.VIDEO_SUBTITLE_MODE_DUB, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB):
        markup = bot.video_dubbing_preview_ready_keyboard("vi", {"mode": mode})
        assert _labels(markup) == ["✅ Xác nhận tạo đầy đủ", "⬅️ Quay lại", "🏠 Menu chính"]
        assert "videodub|final" in _callbacks(markup)
