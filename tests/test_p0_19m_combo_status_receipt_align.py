import inspect

import bot


def _delivered_job():
    return {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "video_delivery_message_id": "telegram-video-77",
        "delivery_success": True,
        "final_mp4_delivered": True,
        "terminal_state": "delivered",
    }


def test_combo_delivered_mp4_recovers_to_common_success_receipt_path():
    result = bot.subdub_restore_delivered_combo_result(
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        {"ok": False, "status": "FINAL_VIDEO_NOT_CREATED"},
        _delivered_job(),
        {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB},
    )
    assert result["ok"] is True
    assert result["has_video"] is True
    assert result["video_delivery_message_id"] == "telegram-video-77"
    assert result["terminal_state"] == "delivered"
    assert result["state"]["panel_final_percent"] == 100
    receipt = bot.video_dubbing_receipt_text(result["state"], result, "vi")
    assert "Đã tạo video phụ đề + lồng tiếng thành công" in receipt
    assert "Trạng thái: <b>Đã gửi video</b>" in receipt


def test_combo_without_real_video_message_id_does_not_fake_success():
    result = bot.subdub_restore_delivered_combo_result(
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        {"ok": False, "status": "FINAL_VIDEO_NOT_CREATED"},
        {"terminal_state": "delivered", "final_mp4_delivered": True},
        {},
    )
    assert result["ok"] is False


def test_subtitle_only_and_dub_only_are_locked_out_of_combo_recovery():
    for mode in (bot.VIDEO_SUBTITLE_MODE_TRANSLATE, bot.VIDEO_SUBTITLE_MODE_DUB):
        original = {"ok": False, "status": "FAILED"}
        assert bot.subdub_restore_delivered_combo_result(mode, original, _delivered_job(), {}) == original


def test_combo_handler_rejoins_existing_full_green_and_receipt_block():
    source = inspect.getsource(bot.handle_video_dubbing_callback)
    recovery = source.index("subdub_restore_delivered_combo_result")
    failure = source.index('if not result.get("ok"):', recovery)
    delivered_panel = source.index('subdub_progress_text("delivered"', failure)
    receipt = source.index("video_dubbing_receipt_text(completed_state, result, lang)", delivered_panel)
    assert recovery < failure < delivered_panel < receipt
    assert 'mode == VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB' in source[:failure]
