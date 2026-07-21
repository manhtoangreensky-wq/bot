import inspect

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _row_lengths(markup):
    return [len(row) for row in markup.inline_keyboard]


def test_voice_guard_keyboard_two_columns():
    markup = bot.voice_clone_permission_forbidden_keyboard("vi", bot.PRODUCT_CONTEXT_SHOWROOM)
    assert _row_lengths(markup) == [2, 2, 1]
    assert _labels(markup) == [
        "🎙 Dùng giọng nữ mặc định",
        "🎙 Dùng giọng nam mặc định",
        "🔁 Thử lại sau",
        "⬅️ Kho voice",
        "🏠 Menu chính",
    ]


def test_failed_profile_keyboard_two_columns():
    markup = bot.voice_profile_actions_keyboard(
        77,
        "vi",
        bot.PRODUCT_CONTEXT_SHOWROOM,
        {
            "id": 77,
            "user_id": "42",
            "display_name": "Voice rieng",
            "status": "failed_provider_not_ready",
            "provider_voice_id": "",
        },
    )
    assert _row_lengths(markup) == [2, 2, 1]
    assert _labels(markup) == ["🔁 Tạo/nghe thử lại", "✏️ Đổi tên", "🗑 Xóa", "⬅️ Kho voice", "🏠 Menu chính"]


def test_translate_result_keyboard_two_columns():
    markup = bot.video_dubbing_output_keyboard(
        "vi",
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            "active_flow": "subtitle_translate",
            "translated_subtitle_ref": "video_dubbing_artifact:1:translated",
        },
    )
    assert _row_lengths(markup) == [2, 2, 1]
    assert _labels(markup) == [
        "📹 Tải video phụ đề dịch",
        "📄 Tải SRT dịch",
        "🌐 Dịch ngôn ngữ khác",
        "🏠 Menu chính",
        "⬅️ Quay lại",
    ]


def test_dub_mp4_keyboard_two_columns():
    markup = bot.subtitle_plus_dub_completed_keyboard("vi", {"final_video_available": "1", "final_audio_available": "1"})
    assert _row_lengths(markup) == [2, 2, 1]
    assert _labels(markup) == ["📹 Tải video hoàn chỉnh", "🎧 Tải audio", "📄 Tải phụ đề", "🔁 Làm video khác", "🏠 Menu chính"]


def test_dub_fallback_keyboard_two_columns():
    markup = bot.subtitle_plus_dub_completed_keyboard("vi", {"final_video_available": "0", "final_audio_available": "1"})
    assert _row_lengths(markup) == [2, 2, 1]
    assert _labels(markup) == ["🎧 Tải audio", "📄 Tải phụ đề", "🔁 Thử ghép lại video", "🎙 Lồng tiếng lại", "🏠 Menu chính"]


def test_no_generic_red_error_in_result_callbacks():
    callback_source = inspect.getsource(bot.handle_video_dubbing_callback)
    forbidden = "Có lỗi khi xử lý lệnh. Bot chưa trừ Xu. Vui lòng thử lại sau."
    assert forbidden not in callback_source
