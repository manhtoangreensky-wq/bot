import json
import subprocess

import bot


def _fresh_db(monkeypatch, tmp_path):
    db_path = tmp_path / "pricing1.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_path))
    bot.init_db()
    return db_path


def _diff_text(*paths):
    base = subprocess.check_output(["git", "merge-base", "HEAD", "origin/main"], text=True, encoding="utf-8").strip()
    cmd = ["git", "diff", base, "--", *paths]
    return subprocess.check_output(cmd, text=True, encoding="utf-8")


def test_canonical_price_table_has_voice_subdub_video_keys():
    table = bot.canonical_price_table()
    required = {
        "voice_tts_basic",
        "voice_tts_long",
        "voice_clone_custom",
        "subtitle_translate_video",
        "auto_subtitle_video",
        "dub_video",
        "subtitle_dub_video",
        "auto_subtitle_then_dub",
        "video_beta_200",
        "video_beta_300",
        "video_beta_400",
        "video_addon_voice",
        "video_addon_subtitle",
        "video_addon_dub",
        "video_addon_music",
        "video_addon_logo",
    }
    assert required <= set(table)


def test_voice_subdub_base_price_x2_applied():
    assert bot.canonical_price_xu("voice_tts_basic") == bot.VOICE_TTS_PRODUCT_PRICE_PER_WORD_XU == 0.10
    assert bot.canonical_price_xu("voice_clone_custom") == bot.CUSTOM_VOICE_USAGE_PRICE_PER_CHAR_XU == 0.20
    assert bot.canonical_price_xu("dub_video") == bot.VIDEO_ONLY_DUB_DEFAULT_RATE_XU == 0.10


def test_no_public_old_voice_price_reference():
    public_text = "\n".join(bot.public_pricing_all_lines(bot.public_pricing_context()))
    assert "0.05 Xu" not in public_text
    assert "0,05 Xu" not in public_text


def test_no_public_old_subdub_price_reference():
    public_text = "\n".join(bot.public_pricing_all_lines(bot.public_pricing_context()))
    assert "provider" not in public_text.lower()
    assert "API" not in public_text


def test_voice_invoice_uses_canonical_price():
    quote = bot.voice_tts_product_quote(" ".join(["xin"] * 20))
    assert quote["price_per_word_xu"] == bot.canonical_price_xu("voice_tts_basic")
    assert quote["raw_price_xu"] == 2.0


def test_voice_total_payment_matches_price_table():
    quote = bot.voice_tts_product_quote(" ".join(["xin"] * 20))
    assert quote["total_xu"] == 2
    assert quote["total_xu"] == int(20 * bot.canonical_price_xu("voice_tts_basic"))


def test_subtitle_invoice_uses_canonical_price():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "billing_chars": 1000}
    invoice = bot.video_dubbing_invoice_breakdown(state)
    assert invoice["subtitle_rate_xu"] == bot.canonical_price_xu("subtitle_translate_video")
    assert invoice["translation_xu"] == bot.calculate_video_only_char_price(1000, bot.canonical_price_xu("subtitle_translate_video"))["total_xu"]


def test_dub_invoice_uses_canonical_price():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "billing_chars": 1000}
    invoice = bot.video_dubbing_invoice_breakdown(state)
    assert invoice["dub_rate_xu"] == bot.canonical_price_xu("dub_video")
    assert invoice["voice_xu"] == bot.calculate_video_only_char_price(1000, bot.canonical_price_xu("dub_video"))["total_xu"]


def test_subtitle_dub_total_is_subtitle_plus_dub():
    state = {"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "billing_chars": 1000}
    invoice = bot.video_dubbing_invoice_breakdown(state)
    assert invoice["total_xu"] == invoice["translation_xu"] + invoice["voice_xu"]
    assert bot.canonical_price_xu("subtitle_dub_video") == bot.canonical_price_xu("subtitle_translate_video") + bot.canonical_price_xu("dub_video")


def test_auto_subtitle_then_dub_total_is_auto_subtitle_plus_dub():
    assert bot.canonical_price_xu("auto_subtitle_then_dub") == bot.canonical_price_xu("auto_subtitle_video") + bot.canonical_price_xu("dub_video")


def test_subdub_discount_cap_30_percent():
    assert bot.finance_discount_cap_percent(80) == 30
    invoice = bot.video_dubbing_invoice_breakdown({"mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, "billing_chars": 20_000})
    assert invoice["subtitle_discount_percent"] <= 30
    assert invoice["dub_discount_percent"] <= 30


def test_subdub_b2c_no_vat_or_cit_extra():
    text = bot.video_dubbing_confirm_text({"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "billing_chars": 1000}, "vi")
    lowered = text.lower()
    assert "vat" not in lowered
    assert "tndn" not in lowered
    assert "tổng" in lowered or "chi phí" in lowered


def test_video_beta_200_price_consistent():
    assert bot.video_tier_pricing_payload()["low"]["cost"] == bot.canonical_price_xu("video_beta_200") == 200
    assert bot.calculate_short_video_quote("200", 8, 1, [])["total_xu"] == 200


def test_video_beta_300_price_consistent():
    assert bot.video_tier_pricing_payload()["basic"]["cost"] == bot.canonical_price_xu("video_beta_300") == 300
    assert bot.calculate_short_video_quote("300", 8, 1, [])["total_xu"] == 300


def test_video_beta_400_price_consistent():
    assert bot.video_tier_pricing_payload()["common"]["cost"] == bot.canonical_price_xu("video_beta_400") == 400
    assert bot.calculate_short_video_quote("400", 8, 1, [])["total_xu"] == 400


def test_video_invoice_matches_selected_package():
    quote = bot.calculate_short_video_quote("300", 8, 1, [])
    invoice = bot.video_quote_invoice_text(
        {
            "tier": "basic",
            "package_base_xu": quote["base_price_xu"],
            "scene_count": 1,
            "estimated_seconds": 8,
            "scene_discount_percent": 0,
            "scene_video_xu": quote["base_price_xu"],
            "addon_fee_xu": 0,
            "total_xu": quote["total_xu"],
            "estimated_vnd": quote["estimated_vnd"],
            "paid_items": [],
        },
        {"video_tier": "basic"},
        "vi",
    )
    assert "300 Xu" in invoice
    assert "Tổng: <b>300 Xu</b>" in invoice


def test_video_addon_voice_uses_canonical_price():
    matrix = bot.video_addon_pricing_matrix()
    assert matrix["voice_advanced"]["price_xu"] == bot.canonical_price_xu("video_addon_voice")


def test_video_addon_subtitle_uses_canonical_price():
    matrix = bot.video_addon_pricing_matrix()
    assert matrix["subtitle_auto"]["price_xu"] == bot.canonical_price_xu("video_addon_subtitle")


def test_video_addon_dub_uses_canonical_price():
    matrix = bot.video_addon_pricing_matrix()
    assert matrix["dubbing_default"]["price_xu"] == bot.canonical_price_xu("video_addon_dub")


def test_video_included_addon_not_double_charged():
    quote = bot.calculate_short_video_quote("300", 8, 1, ["stock_music_library", "subtitle_from_script"])
    assert quote["addon_fee_xu"] == 0
    assert quote["total_xu"] == bot.canonical_price_xu("video_beta_300")


def test_video_total_payment_sum_correct():
    quote = bot.calculate_short_video_quote("300", 8, 1, ["subtitle_auto", "dubbing_default"])
    expected = bot.canonical_price_xu("video_beta_300") + bot.canonical_price_xu("video_addon_subtitle") + bot.canonical_price_xu("video_addon_dub")
    assert quote["total_xu"] == expected


def test_public_pricing_table_matches_canonical():
    text = "\n".join(bot.public_pricing_all_lines(bot.public_pricing_context()))
    for key in ("voice_tts_basic", "subtitle_translate_video", "dub_video", "video_beta_200", "video_beta_300", "video_beta_400"):
        assert bot.canonical_price_display(key) in text


def test_bot_guide_pricing_matches_canonical():
    context = bot.public_pricing_context()
    assert "voice_price_lines" in context
    assert "subtitle_price_lines" in context
    assert any(bot.canonical_price_display("dub_video") in line for line in context["subtitle_price_lines"])


def test_website_pricing_matches_canonical_if_present():
    html_page = bot.public_lines_to_html_page("Bảng giá TOAN AAS", bot.public_pricing_all_lines(bot.public_pricing_context()))
    assert bot.canonical_price_display("video_beta_300") in html_page
    assert "Bảng giá TOAN AAS" in html_page


def test_markdown_download_pricing_matches_canonical_if_present():
    markdown = bot.public_pricing_markdown()
    assert bot.PRICING_DOWNLOAD_FILENAME.endswith(".md")
    assert bot.canonical_price_display("video_beta_400") in markdown


def test_pricing_audit_passes():
    text = "\n".join(bot.pricing_audit_lines())
    assert "Canonical pricing table" in text
    assert "Loaded: <code>YES</code>" in text
    assert "CIT customer charge: <code>NO</code>" in text


def test_subdub_pricing_audit_passes():
    text = "\n".join(bot.product_price_audit_lines("subdub"))
    assert "subtitle_dub_video = subtitle_translate_video + dub_video: <code>YES</code>" in text
    assert "auto_subtitle_then_dub = auto_subtitle_video + dub_video: <code>YES</code>" in text


def test_video_pricing_audit_passes():
    text = "\n".join(bot.product_price_audit_lines("video"))
    assert "Video 200 invoice/table match: <code>YES</code>" in text
    assert "Video 300 invoice/table match: <code>YES</code>" in text
    assert "Video 400 invoice/table match: <code>YES</code>" in text


def test_voice_pricing_audit_passes():
    text = "\n".join(bot.product_price_audit_lines("voice"))
    assert "Giọng nói thường" in text
    assert bot.canonical_price_display("voice_tts_basic") in text


def test_price_set_owner_override_updates_canonical_and_public_copy(monkeypatch, tmp_path):
    _fresh_db(monkeypatch, tmp_path)
    bot.set_canonical_price_value("video_beta_300", 308, updated_by="owner-test")
    assert bot.canonical_price_xu("video_beta_300") == 308
    assert bot.video_tier_pricing_payload()["basic"]["cost"] == 308
    assert "308 Xu" in "\n".join(bot.public_pricing_all_lines(bot.public_pricing_context()))


def test_price_set_help_admin_default_view_only():
    help_text = bot.price_set_help_text()
    assert "Chỉ owner được đổi giá" in help_text
    assert "Admin mặc định chỉ xem audit" in help_text


def test_payos_webhook_not_changed():
    diff = _diff_text("bot.py")
    assert "def verify_payos_signature" not in diff
    assert "webhook_payos" not in diff
    assert "PAYOS_CHECKSUM_KEY" not in diff


def test_wallet_conversion_not_changed():
    diff = _diff_text("bot.py")
    assert "def package_base_xu" not in diff
    assert "UPDATE users SET credits" not in diff


def test_no_db_destructive_migration():
    diff = _diff_text("bot.py")
    upper = diff.upper()
    assert "DROP TABLE" not in upper
    assert "DELETE FROM" not in upper


def test_no_music_or_linkdl_files_touched():
    base = subprocess.check_output(["git", "merge-base", "HEAD", "origin/main"], text=True, encoding="utf-8").strip()
    names = subprocess.check_output(["git", "diff", "--name-only", base], text=True, encoding="utf-8").splitlines()
    forbidden = [
        "providers/video_downloader_provider.py",
        "services/public_video_link_downloader.py",
        "services/subtitle_dub_pipeline.py",
        "services/subtitle_dub_product_pipeline.py",
    ]
    assert not any(name.replace("\\", "/") in forbidden for name in names)
