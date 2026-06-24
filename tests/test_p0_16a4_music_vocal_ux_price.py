import asyncio
import inspect
from types import SimpleNamespace

import bot


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


class CaptureMessage:
    def __init__(self, chat_id=160404):
        self.chat_id = chat_id
        self.outputs = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        item = {"text": str(text), "parse_mode": parse_mode, "reply_markup": reply_markup, **kwargs}
        self.outputs.append(item)
        return SimpleNamespace(**item)


class CaptureQuery:
    def __init__(self, data, user_id=160404):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = CaptureMessage(chat_id=user_id)

    async def answer(self, *args, **kwargs):
        return None


def _callback_update(data, user_id=160404):
    query = CaptureQuery(data, user_id)
    return SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=user_id)), query


def _reset_user(user_id, monkeypatch):
    bot.clear_music_guided_pending(user_id)
    bot.save_music_guided_result(user_id, {})
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "music_ui_lang", lambda user_id=None, lang="": "vi")


def _vocal_result(**overrides):
    result = bot.music_vocal_full_initial_result()
    result.update({"selected_prompt": "Bài hát cảm ơn khách hàng"})
    result.update(overrides)
    return result


def test_music_vocal_menu_goes_direct_to_topic_selection(monkeypatch):
    user_id = 160401
    _reset_user(user_id, monkeypatch)
    update, query = _callback_update("music_quick|showroom|song_menu", user_id)

    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    text = query.message.outputs[-1]["text"]

    assert "🎤 <b>Tạo bài hát có lời</b>" in text
    assert "Sản phẩm: <b>Bài hát có lời AI</b>" in text
    assert "Bạn muốn bài hát nói về điều gì" in text
    assert "Bài hát có lời AI: 800 Xu" not in text
    assert "Nghe thử" not in text


def test_music_vocal_intermediate_info_screen_removed(monkeypatch):
    user_id = 160402
    _reset_user(user_id, monkeypatch)
    update, query = _callback_update("music_quick|showroom|song_menu", user_id)

    asyncio.run(bot.handle_music_quick_callback(update, SimpleNamespace()))
    text = query.message.outputs[-1]["text"]

    assert "TOAN AAS sẽ tạo một bài hoàn chỉnh" not in text
    assert "Bài hát có lời AI: 500 Xu" not in text
    assert "Bài hát có lời AI: 800 Xu" not in text
    assert "Nửa bài" not in text
    assert "Không bán nửa bài" not in text


def test_music_vocal_topic_buttons_still_exist():
    labels = _labels(bot.music_song_topic_keyboard("vi", back_action="music_hub"))

    for label in [
        "Câu chuyện thương hiệu",
        "Cảm ơn khách hàng",
        "Ra mắt sản phẩm",
        "🔁 Gợi ý chủ đề khác",
        "✍️ Tự nhập chủ đề",
        "⬅️ Quay lại",
        "🏠 Menu chính",
    ]:
        assert label in labels


def test_music_vocal_price_shown_before_preview():
    text = bot.music_ai_preview_text(_vocal_result(), "vi")

    assert "🎧 <b>Nghe thử bài hát có lời AI</b>" in text
    assert "Bản đầy đủ bài hát có lời AI: <b>800 Xu</b>" in text


def test_music_vocal_preview_notice_shows_12s():
    text = bot.music_ai_preview_text(_vocal_result(), "vi")

    assert "12 giây đầu" in text
    assert "Nghe thử: theo chính sách preview" in text


def test_music_vocal_preview_notice_mentions_full_saved_to_vault():
    text = bot.music_ai_preview_text(_vocal_result(), "vi")

    assert "Bản đầy đủ được lưu trong kho" in text
    assert "chỉ giao khi quý khách xác nhận dùng bản đầy đủ" in text


def test_music_vocal_preview_notice_mentions_15_day_quota():
    text = bot.music_ai_preview_text(_vocal_result(), "vi")

    assert "1 lần trong 15 ngày" in text
    assert "Silver" in text
    assert "1 lần/ngày" not in text


def test_music_vocal_full_confirm_button_800_xu():
    labels = _labels(bot.music_ai_preview_keyboard("vi", result=_vocal_result()))

    assert "▶️ Nghe thử 12 giây" in labels
    assert "✅ Dùng bản đầy đủ 800 Xu" in labels
    assert "🗂 Lưu vào kho nhạc" in labels


def test_music_vocal_price_constant_800():
    assert bot.MUSIC_VOCAL_FULL_PRICE_XU == 800
    assert bot.music_ai_output_price_xu(120, "song_full") == 800
    assert bot.music_product_quote_price_xu("vocal_ai") == 800


def test_music_vocal_price_display_800():
    assert "800 Xu" in bot.music_ai_preview_text(_vocal_result(), "vi")
    assert any("800 Xu" in label for label in _labels(bot.music_ai_preview_keyboard("vi", result=_vocal_result())))


def test_music_vocal_invoice_line_800_if_applicable():
    text = bot.music_song_length_selection_text(_vocal_result(), "vi")

    assert "Giá dự kiến: 800 Xu." in text


def test_music_pricing_table_vocal_800():
    source = inspect.getsource(bot.cmd_pricing_legacy_monthly_snapshot)

    assert "Bài hát có lời AI" in source
    assert "MUSIC_VOCAL_FULL_PRICE_XU or 800" in source


def test_no_unwanted_music_vocal_500_customer_text():
    public_text = "\n".join([
        bot.music_song_product_text("vi"),
        bot.music_ai_preview_text(_vocal_result(), "vi"),
        bot.music_song_length_selection_text(_vocal_result(), "vi"),
        inspect.getsource(bot.cmd_pricing_legacy_monthly_snapshot),
    ])

    assert "Bài hát có lời AI: 500 Xu" not in public_text
    assert "Dùng bản đầy đủ 500 Xu" not in public_text
    assert "từ 500–1.000 Xu" not in public_text


def test_music_vocal_no_half_song_customer_text():
    public_text = "\n".join([
        bot.music_song_product_text("vi"),
        bot.music_ai_preview_text(_vocal_result(song_product="half"), "vi"),
        bot.music_song_length_selection_text(_vocal_result(song_product="half"), "vi"),
    ])

    assert "Nửa bài" not in public_text
    assert "nửa bài" not in public_text.lower()
    assert "Không bán nửa bài" not in public_text


def test_music_vocal_no_provider_short_mode_public_text():
    public_text = "\n".join([
        bot.music_song_product_text("vi"),
        bot.music_ai_preview_text(_vocal_result(), "vi"),
        inspect.getsource(bot.cmd_pricing_legacy_monthly_snapshot),
    ])

    assert "provider short/clip" not in public_text
    assert "short/clip mode" not in public_text


def test_music_short_mode_internal_flag_not_public_by_default(monkeypatch):
    monkeypatch.setattr(bot, "MUSIC_SHORT_MODE_VERIFIED", True)
    labels = _labels(bot.music_song_product_keyboard("vi"))

    assert "🎤 Bài hát có lời AI" in labels
    assert not any("Nửa bài" in label for label in labels)


def test_bot_pricing_music_vocal_800():
    source = inspect.getsource(bot.cmd_pricing_legacy_monthly_snapshot)

    assert "Nhạc AI" in source
    assert "Bài hát có lời AI" in source
    assert "MUSIC_VOCAL_FULL_PRICE_XU or 800" in source


def test_bot_pricing_no_half_song_public():
    source = inspect.getsource(bot.cmd_pricing_legacy_monthly_snapshot)

    assert "nửa bài" not in source.lower()
    assert "short/clip" not in source
