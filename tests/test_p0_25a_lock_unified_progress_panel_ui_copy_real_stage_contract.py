import bot
from services import product_progress_status


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def test_progress_button_label_is_cap_nhat_trang_thai():
    labels = _labels(bot.product_progress_status_keyboard("music_song", "MUS1"))
    assert labels[0] == "🔄 Cập nhật trạng thái"
    assert _labels(bot.video_b14_queue_status_keyboard("vi"))[0] == "🔄 Cập nhật trạng thái"


def test_no_progress_panel_uses_kiem_tra_trang_thai_label():
    payload = product_progress_status.progress_panel_contract_audit_payload()
    assert payload["ok"] is True
    assert not any("Kiểm tra trạng thái" in label for label in payload["labels"])


def test_no_music_panel_uses_check_send_result_button():
    labels = _labels(bot.product_progress_status_keyboard("music_song", "MUS1"))
    assert "🔎 Kiểm tra/gửi kết quả" not in labels
    assert not any("Kiểm tra/gửi" in label for label in labels)


def test_music_steps_not_green_before_real_state():
    text = bot.product_progress_status_text("music_song", "MUS1", "preparing_style", percent=95)
    assert "⏳ Chuẩn bị phong cách" in text
    assert "✅ Tạo bài hát" not in text
    assert "✅ Kiểm tra file nhạc" not in text
    assert "✅ Gửi kết quả" not in text
    assert "Tiến độ: 35%" in text


def test_video_steps_not_green_before_real_state():
    text = bot.product_progress_status_text("multiscene_video", "VID1", "generating_video", percent=95)
    assert "⏳ Tạo video" in text
    assert "✅ Ghép hậu kỳ" not in text
    assert "✅ Kiểm tra file" not in text
    assert "✅ Gửi kết quả" not in text
    assert "Tiến độ: 60%" in text


def test_video_draft_not_rendered_as_final():
    state = product_progress_status.product_progress_stage_from_job(
        "multiscene_video",
        {"status": "completed", "visual_classification": "partial_simple_video", "progress_percent": 100},
    )
    assert state["terminal_state"] == "failed_no_charge"
    text = bot.product_progress_status_text(
        "multiscene_video",
        "VID2",
        state["current_stage"],
        state["percent"],
        state["terminal_state"],
        "Đã có bản nháp, chưa có video hoàn chỉnh. Bản này chưa trừ Xu.",
    )
    assert "Đã gửi kết quả" not in text
    assert "chưa có video hoàn chỉnh" in text


def test_video_no_95_percent_without_final_or_checking_artifact():
    state = product_progress_status.product_progress_stage_from_job(
        "multiscene_video",
        {"status": "processing", "progress_percent": 95},
    )
    assert state["percent"] < 95
    text = bot.product_progress_status_text("multiscene_video", "VID3", state["current_stage"], state["percent"])
    assert "Tiến độ: 95%" not in text


def test_progress_panel_contract_audit_passes():
    assert product_progress_status.progress_panel_contract_audit_payload()["ok"] is True


def test_music_progress_panel_audit_passes():
    assert product_progress_status.music_progress_panel_audit_payload()["ok"] is True


def test_video_progress_panel_audit_passes():
    assert product_progress_status.video_progress_panel_audit_payload()["ok"] is True
