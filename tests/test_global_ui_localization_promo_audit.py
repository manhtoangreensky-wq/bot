import re

import bot


def _text(lines):
    if isinstance(lines, str):
        return lines
    return "\n".join(str(line) for line in lines)


def _video_state(tier="basic", scenes=3, aspect="9:16"):
    scene_seconds = int(bot.TASK3D_SCENE_SECONDS)
    return {
        "source": "promptvideo",
        "source_label": "Prompt/storyboard",
        "source_payload": {
            "source": "promptvideo",
            "video_prompt": "A clear product demonstration",
            "aspect_ratio": aspect,
        },
        "selected_video_tier": tier,
        "video_tier": tier,
        "selected_scene_count": scenes,
        "estimated_scene_seconds": scene_seconds,
        "estimated_duration_seconds": scenes * scene_seconds,
        "selected_video_aspect_ratio": aspect,
        "aspect_ratio": aspect,
        "video_finalization": bot.video_finalization_defaults(),
    }


def _public_samples(lang):
    state = _video_state()
    quote = bot.calculate_video_quote(state)
    keys = (
        "common.no_api_no_charge",
        "media.cancelled",
        "image.prompt.ask",
        "image.confirm.cost",
        "video.prompt.ask",
    )
    ui_samples = [
        bot.ui_text(
            lang,
            key,
            label="Standard",
            cost=300,
            credits=1000,
            warranty_note="included",
            prompt="sample",
        )
        for key in keys
    ]
    return [
        *ui_samples,
        _text(bot.pricing_hub_lines(lang)),
        _text(bot.billing_promotions_lines(lang)),
        _text(bot.member_policy_lines(lang)),
        bot.public_media_aspect_ratio_text("video", "basic", "sample", lang),
        bot.video_finalization_menu_text(state, lang),
        bot.video_finalization_tier_text(state, lang),
        bot.video_finalization_scene_count_text(state, lang),
        bot.video_quote_invoice_text(quote, state, lang),
    ]


def test_vi_ui_no_unwanted_english_mixed_copy():
    text = "\n".join(_public_samples("vi"))
    for phrase in ("Choose video", "Final video invoice", "Scene count:", "Source:", "Add-ons:", "Admin has"):
        assert phrase not in text


def test_en_ui_no_vietnamese_copy():
    text = "\n".join(_public_samples("en"))
    for phrase in ("Chọn ", "Hóa đơn", "Số cảnh", "Thời lượng", "Chưa xử lý", "Khuyến mãi nạp tiền"):
        assert phrase not in text
    assert not re.search(r"[ăâđêôơưĂÂĐÊÔƠƯ]", text)


def test_zh_ui_no_vietnamese_copy():
    text = "\n".join(_public_samples("zh"))
    for phrase in ("Chọn ", "Hóa đơn", "Số cảnh", "Thời lượng", "Khuyến mãi", "Quay lại"):
        assert phrase not in text
    assert not re.search(r"[ăâđêôơưĂÂĐÊÔƠƯ]", text)


def test_public_no_provider_debug_text():
    text = "\n".join(
        sample.lower()
        for lang in ("vi", "en", "zh")
        for sample in _public_samples(lang)
    )
    for token in ("shopaikey", "key4u", "provider", "debug", "http status", "model id"):
        assert token not in text


def test_public_no_env_api_text():
    text = "\n".join(
        sample
        for lang in ("vi", "en", "zh")
        for sample in _public_samples(lang)
    )
    assert "API_KEY" not in text
    assert "ENV" not in text
    assert not re.search(r"\bAPI\b", text)


def test_vi_promo_table_keeps_domestic_deposit_promos():
    text = _text(bot.billing_promotions_lines("vi"))
    assert "FIRST30" in text
    assert "SECOND15" in text
    assert "Launch Bonus" in text


def test_vi_promo_notes_payos_bank_only():
    text = _text(bot.billing_promotions_lines("vi"))
    assert "Khuyến mãi nạp tiền chỉ áp dụng cho PayOS hoặc chuyển khoản ngân hàng Việt Nam." in text


def test_vi_promo_excludes_zalo_momo():
    text = _text(bot.billing_promotions_lines("vi"))
    assert "Không áp dụng cho Zalo/MoMo hoặc kênh nạp quốc tế." in text


def test_en_promo_table_removes_deposit_launch_bonus():
    text = _text(bot.billing_promotions_lines("en"))
    assert "FIRST30" not in text
    assert "SECOND15" not in text
    assert "Launch Bonus theo mệnh giá" not in text
    assert "launch bonuses are not offered" in text


def test_international_promo_shows_tier_discount_only():
    text = _text(bot.billing_promotions_lines("en"))
    assert "member-tier service discounts" in text
    assert "Vietnam domestic deposit bonuses" in text


def test_promo_policy_no_cross_market_confusion():
    vi = _text(bot.billing_promotions_lines("vi"))
    en = _text(bot.billing_promotions_lines("en"))
    assert "FIRST30" in vi
    assert "FIRST30" not in en
    assert "International users receive" in en
    assert "PayOS hoặc chuyển khoản ngân hàng Việt Nam" in vi


def test_member_tier_copy_clear():
    for lang in ("vi", "en", "zh"):
        text = _text(bot.member_policy_lines(lang))
        assert "Newbie" in text
        assert "VIP" in text
        assert "%" in text


def test_member_discount_separate_from_deposit_promo():
    vi = _text(bot.member_policy_lines("vi"))
    en = _text(bot.member_policy_lines("en"))
    assert "<b>Chiết khấu khi dùng dịch vụ</b>" in vi
    assert "<b>Khuyến mãi nạp tiền nội địa</b>" in vi
    assert "<b>Service discounts</b>" in en
    assert "<b>Domestic deposit campaigns</b>" in en


def test_owner_admin_text_not_shown_to_public():
    for lang in ("vi", "en", "zh"):
        labels = " ".join(
            button.text
            for row in bot.localized_main_menu_keyboard(False, lang).inline_keyboard
            for button in row
        ).lower()
        public_copy = "\n".join(_public_samples(lang)).lower()
        assert "owner" not in labels
        assert "admin" not in labels
        assert "admin-only" not in public_copy


def test_video_flow_copy_has_no_provider_leak():
    for lang in ("vi", "en", "zh"):
        text = "\n".join(_public_samples(lang)).lower()
        for token in ("provider", "shopaikey", "key4u", "http", "debug"):
            assert token not in text


def test_video_invoice_copy_shows_total_and_no_charge_before_confirm():
    state = _video_state()
    quote = bot.calculate_video_quote(state)
    vi = bot.video_quote_invoice_text(quote, state, "vi")
    en = bot.video_quote_invoice_text(quote, state, "en")
    zh = bot.video_quote_invoice_text(quote, state, "zh")
    assert "Tổng:" in vi and "chỉ bắt đầu xử lý và trừ Xu sau" in vi
    assert "Total:" in en and "only after you press the final confirmation" in en
    assert "总计：" in zh and "最终确认" in zh


def test_video_scene_copy_clear_duration_and_price():
    state = _video_state()
    for lang in ("vi", "en", "zh"):
        text = bot.video_finalization_scene_count_text(state, lang)
        assert "18" in text
        assert "810" in text
        assert "270" in text


def test_video_aspect_copy_clear():
    for lang in ("vi", "en", "zh"):
        text = bot.public_media_aspect_ratio_text("video", "basic", "sample", lang)
        for ratio in ("9:16", "16:9", "1:1", "4:5"):
            assert ratio in text
