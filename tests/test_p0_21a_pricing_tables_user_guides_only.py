from pathlib import Path

import bot
from services import pricing_guide_content as pricing_content


REPO_ROOT = Path(bot.__file__).resolve().parent
FORBIDDEN_PUBLIC_WORDS = pricing_content.TECHNICAL_WORDS


def _button_texts(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _button_callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def _assert_no_technical_words(text: str) -> None:
    found = pricing_content.technical_words_found(text)
    assert found == []


def _pricing_text() -> str:
    return "\n".join(bot.public_pricing_all_lines(bot.public_pricing_context()))


def _guide_text() -> str:
    return "\n".join(bot.public_guide_all_lines())


def test_pricing_menu_has_total_voice_music_video_subtitle_image_member_guides():
    labels = _button_texts(bot.pricing_catalog_keyboard("vi"))
    callbacks = _button_callbacks(bot.pricing_catalog_keyboard("vi"))
    for label in [
        "💰 Bảng giá tổng",
        "🎙 Giọng nói",
        "🎵 Nhạc AI",
        "🎬 Video",
        "🌐 Phụ đề / Lồng tiếng",
        "🖼 Hình ảnh",
        "🎁 Khuyến mãi / Thành viên",
        "📘 Hướng dẫn sử dụng",
    ]:
        assert label in labels
    for callback in [
        "pricing|total",
        "pricing|voice",
        "pricing|music",
        "pricing|video",
        "pricing|subtitle",
        "pricing|image",
        "pricing|member",
        "pricing|guide",
    ]:
        assert callback in callbacks


def test_voice_pricing_copy_first_voice_free_second_50():
    text = "\n".join(bot.pricing_voice_lines())
    assert "Voice riêng đầu tiên tạo thành công: miễn phí" in text
    assert "Từ voice riêng thứ 2 trở đi: 50 Xu" in text


def test_voice_tts_pricing_copy_005_xu_per_word_min_20():
    text = "\n".join(bot.pricing_voice_lines())
    assert "0.05 Xu / từ" in text
    assert "Nội dung tối thiểu: 20 từ" in text
    assert "Tối thiểu thanh toán: 1 Xu" in text


def test_music_pricing_copy_instrumental_100_150_200():
    text = "\n".join(bot.pricing_music_lines())
    assert "Nhạc nền / không lời" in text
    assert "Cơ bản: 100 Xu" in text
    assert "Tiêu chuẩn: 150 Xu" in text
    assert "Cao cấp: 200 Xu" in text


def test_music_pricing_copy_song_200_250_300():
    text = "\n".join(bot.pricing_music_lines())
    assert "Bài hát có lời" in text
    assert "Cơ bản: 200 Xu" in text
    assert "Tiêu chuẩn: 250 Xu" in text
    assert "Cao cấp: 300 Xu" in text


def test_subtitle_pricing_copy_auto_subtitle_free():
    text = "\n".join(bot.pricing_subtitle_lines())
    assert "Tạo phụ đề tự động" in text
    assert "Miễn phí" in text


def test_subtitle_translate_copy_01_xu_per_char():
    text = "\n".join(bot.pricing_subtitle_lines())
    assert "Dịch phụ đề" in text
    assert "0.1 Xu / ký tự" in text


def test_dub_default_copy_005_xu_per_char():
    text = "\n".join(bot.pricing_subtitle_lines())
    assert "Lồng tiếng giọng mặc định" in text
    assert "0.05 Xu / ký tự" in text


def test_dub_custom_copy_01_xu_per_char():
    text = "\n".join(bot.pricing_subtitle_lines())
    assert "Lồng tiếng voice riêng" in text
    assert "0.1 Xu / ký tự" in text


def test_discount_copy_1000_10000_chars():
    text = "\n".join(bot.pricing_subtitle_lines() + bot.public_pricing_lines("member", bot.public_pricing_context()))
    assert "Trên 1.000 ký tự: giảm 10%" in text
    assert "Trên 10.000 ký tự: giảm 20%" in text


def test_member_discount_copy_uses_existing_config_or_disabled():
    text = "\n".join(bot.public_pricing_lines("member", bot.public_pricing_context()))
    assert "Khuyến mãi & Thành viên" in text
    assert "Chiết khấu thành viên" in text
    assert "Hiển thị tổng cuối trước xác nhận" in text


def test_free_resource_copy():
    text = "\n".join(bot.pricing_free_lines())
    for expected in [
        "Dùng ảnh do anh/chị gửi lên",
        "Dùng nhạc do anh/chị gửi lên",
        "Dùng voice/audio có sẵn",
        "Hủy trước xác nhận: không trừ Xu",
    ]:
        assert expected in text


def test_guides_include_examples_each_product():
    text = _guide_text()
    for expected in [
        "Ví dụ: 100 từ = 5 Xu",
        "Ví dụ: chọn Nhạc nền Tiêu chuẩn = 150 Xu",
        "Ví dụ: gói Cơ bản 300 Xu",
        "Ví dụ: 2.000 ký tự = 200 Xu",
        "Ví dụ: lồng tiếng giọng mặc định 2.000 ký tự",
        "Ví dụ: chọn gói ảnh 200 Xu",
    ]:
        assert expected in text


def test_pricing_ui_no_technical_words():
    _assert_no_technical_words(_pricing_text())
    _assert_no_technical_words(_guide_text())


def test_pricing_task_does_not_touch_voice_music_video_engine():
    source = Path(pricing_content.__file__).read_text(encoding="utf-8").lower()
    for token in ["call_video", "run_video", "suno", "clone_voice", "deduct_xu", "wallet_ledger"]:
        assert token not in source


def test_pricing_download_button_exists():
    labels = _button_texts(bot.pricing_main_keyboard("vi")) + _button_texts(bot.pricing_catalog_keyboard("vi"))
    callbacks = _button_callbacks(bot.pricing_main_keyboard("vi")) + _button_callbacks(bot.pricing_catalog_keyboard("vi"))
    assert "📥 Tải bảng giá" in labels
    assert "pricing|download_pricing" in callbacks


def test_user_guide_download_button_exists():
    labels = _button_texts(bot.pricing_main_keyboard("vi")) + _button_texts(bot.main_guide_keyboard("vi"))
    callbacks = _button_callbacks(bot.pricing_main_keyboard("vi")) + _button_callbacks(bot.main_guide_keyboard("vi"))
    assert "📘 Tải hướng dẫn sử dụng" in labels
    assert "pricing|download_guide" in callbacks


def test_pricing_download_file_contains_voice_music_video_subtitle_image():
    text = (REPO_ROOT / "docs" / "public" / pricing_content.PRICING_DOWNLOAD_FILENAME).read_text(encoding="utf-8")
    for expected in ["Bảng giá Giọng nói", "Bảng giá Nhạc AI", "Bảng giá Video", "Bảng giá Phụ đề / Lồng tiếng", "Bảng giá Hình ảnh"]:
        assert expected in text


def test_guide_download_file_contains_examples():
    text = (REPO_ROOT / "docs" / "public" / pricing_content.GUIDE_DOWNLOAD_FILENAME).read_text(encoding="utf-8")
    for expected in ["Ví dụ: 100 từ = 5 Xu", "Ví dụ: gói Cơ bản 300 Xu", "Ví dụ: chọn gói ảnh 200 Xu"]:
        assert expected in text


def test_download_files_have_no_technical_words():
    pricing_md = (REPO_ROOT / "docs" / "public" / pricing_content.PRICING_DOWNLOAD_FILENAME).read_text(encoding="utf-8")
    guide_md = (REPO_ROOT / "docs" / "public" / pricing_content.GUIDE_DOWNLOAD_FILENAME).read_text(encoding="utf-8")
    _assert_no_technical_words(pricing_md)
    _assert_no_technical_words(guide_md)


def test_pricing_content_single_source_used_by_bot_and_download():
    assert bot.public_pricing_markdown() == bot.shared_pricing_markdown(bot.public_pricing_context())
    assert bot.public_guide_markdown() == pricing_content.guide_markdown()
    assert bot.shared_pricing_markdown.__module__ == "services.pricing_guide_content"


def test_website_pricing_content_exists_if_web_routes_in_repo():
    routes = {route.path for route in bot.fastapi_app.routes}
    index = (REPO_ROOT / "index.html").read_text(encoding="utf-8")
    assert "/pricing" in routes
    assert "/pricing" in index
    assert "Giọng nói: audio từ voice 0.05 Xu/từ" in index
    assert "Bảng giá video: 200, 300, 400, 500, 600, 800, 1000, 1200 và 1500 Xu" in index
    assert f"/download/{pricing_content.PRICING_DOWNLOAD_FILENAME}" in index


def test_website_guide_content_exists_if_web_routes_in_repo():
    routes = {route.path for route in bot.fastapi_app.routes}
    index = (REPO_ROOT / "index.html").read_text(encoding="utf-8")
    assert "/guide" in routes
    assert "/help" in routes
    assert "/guide" in index
    assert f"/download/{pricing_content.GUIDE_DOWNLOAD_FILENAME}" in index


def test_no_web_standalone_repo_touched_from_bot_repo():
    assert not (REPO_ROOT / "TOAN_AAS_WEB_APP").exists()
    assert (REPO_ROOT / "index.html").exists()
