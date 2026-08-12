import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import pricing_guide_content as guide
from services import video_ai_real_pricing as canonical
from services import aas_shared_knowledge as shared_knowledge
from scripts import export_public_pricing_guides as exporter


APPROVED_PUBLIC_VIDEO_ROWS = (
    ("Nhanh gọn", 5, 200),
    ("Tiêu chuẩn có âm thanh", 5, 220),
    ("Cân bằng rõ nét", 8, 80),
    ("Chuyển động ổn định", 5, 110),
    ("Chuyển động có âm thanh", 5, 160),
    ("Cảnh dài có âm thanh", 15, 220),
    ("Cao cấp linh hoạt", 10, 370),
    ("Diễn xuất chân thật", 6, 370),
    ("Đa góc máy", 8, 1260),
    ("Điện ảnh nhiều cảnh", 10, 2360),
)


def _approved_video_markers() -> list[str]:
    return [
        f"• {name}: <b>{price:,} Xu / cảnh</b> — {seconds} giây.".replace(",", ".")
        for name, seconds, price in APPROVED_PUBLIC_VIDEO_ROWS
    ]


def _image_values() -> list[int]:
    return sorted({int(item["unit_xu"]) for item in canonical.public_image_quality_catalog()})


def test_default_public_guide_context_uses_canonical_image_prices_and_owner_approved_video_catalog():
    context = guide.default_context()
    image_text = "\n".join(context["image_price_lines"])

    for value in _image_values():
        assert f"{value} Xu" in image_text
    assert "Ảnh 50 Xu: tác vụ ảnh nhẹ / cơ bản." not in image_text
    assert context["video_price_lines"] == _approved_video_markers()


def test_pricing_markdown_updates_image_prices_and_owner_approved_video_table():
    markdown = guide.pricing_markdown()
    assert "• Ảnh 50 Xu: tác vụ ảnh nhẹ / cơ bản." not in markdown
    for value in _image_values():
        assert f"{value} Xu" in markdown
    for marker in _approved_video_markers():
        assert marker.replace("<b>", "").replace("</b>", "") in markdown
    assert "Video 200 Xu: gói trải nghiệm." not in markdown
    assert "2-9 cảnh: giảm 10%" not in markdown
    assert "10-19 cảnh: giảm 15%" not in markdown
    assert "• 2–5 cảnh: giảm 10%." in markdown
    assert "• 6–10 cảnh: giảm 15%." in markdown
    assert "• 11–20 cảnh: giảm 20%." in markdown


def test_customer_guide_uses_canonical_image_prices_and_owner_approved_video_examples():
    markdown = guide.guide_markdown()
    for value in _image_values():
        assert f"{value} Xu" in markdown
    assert "Ví dụ: chọn gói ảnh 200 Xu" not in markdown
    for name, seconds, price in APPROVED_PUBLIC_VIDEO_ROWS:
        assert name in markdown
        assert f"{price:,} Xu".replace(",", ".") in markdown
        assert f"{seconds} giây" in markdown
    assert "Nhanh gọn 3 cảnh = 200 × 3 = 600 Xu; giảm 10% là 60 Xu; tiền video còn 540 Xu." in markdown


def test_v2_download_guide_uses_canonical_image_prices_and_owner_approved_video_quick_prices():
    markdown = exporter.guide_v2_markdown()
    image_prices = " / ".join(str(value) for value in _image_values())
    assert f"Bảng giá tạo ảnh: {image_prices} Xu/ảnh." in markdown
    for name, seconds, price in APPROVED_PUBLIC_VIDEO_ROWS:
        assert f"- {name} — {seconds} giây/cảnh: {price:,} Xu/cảnh.".replace(",", ".") in markdown
    assert "- Bảng giá video: 200, 300, 400, 500, 600, 800, 1000, 1200 và 1500 Xu." not in markdown
    assert "- Tiết kiệm: 50 Xu." not in markdown
    assert "- Cao + bảo hành: 600 Xu." not in markdown


def test_every_public_locale_uses_the_owner_approved_video_catalog_and_discount_boundary():
    for locale in guide.PUBLIC_COPY_LOCALES:
        pricing = "\n".join(guide.all_pricing_lines(lang=locale))
        guide_text = "\n".join(guide.all_guide_lines(lang=locale))
        for _name, _seconds, price in APPROVED_PUBLIC_VIDEO_ROWS:
            rendered_price = f"{price:,} Xu".replace(",", ".")
            assert rendered_price in pricing
            assert rendered_price in guide_text
        assert "2-9" not in pricing
        assert "10-19" not in pricing
        assert "2-9" not in guide_text
        assert "10-19" not in guide_text


def test_shared_cskh_pricing_copy_uses_the_public_video_checkpoint_not_legacy_tiers():
    video_reply = shared_knowledge.video_pricing_reply()
    table_reply = shared_knowledge.pricing_table_reply()

    for name, seconds, price in APPROVED_PUBLIC_VIDEO_ROWS:
        assert f"{name} {seconds} giây {price:,} Xu/cảnh".replace(",", ".") in video_reply
        assert f"{name} {seconds} giây {price:,} Xu/cảnh".replace(",", ".") in table_reply

    assert "2-9 cảnh" not in video_reply
    assert "10-19 cảnh" not in video_reply
    assert "2–5 cảnh: giảm 10%" in video_reply
    assert "Video AI: 200 / 300 / 400 / 500 / 600 / 800 / 1000 / 1200 / 1500 Xu" not in table_reply
    assert "Nhạc nền AI: 100 / 150 / 200 Xu" not in table_reply


def test_cskh_knowledge_document_matches_current_public_image_music_and_video_copy():
    text = (ROOT / "knowledge" / "toan_aas_cskh_aichat_context.md").read_text(encoding="utf-8")

    for name, seconds, price in APPROVED_PUBLIC_VIDEO_ROWS:
        assert f"{name} — {seconds} giây/cảnh: {price:,} Xu/cảnh.".replace(",", ".") in text
    for marker in (
        "Nhanh gọn: 10 Xu / ảnh.",
        "Cân bằng: 20 Xu / ảnh.",
        "Cân bằng + bảo hành: 30 Xu / ảnh.",
        "Sáng tạo chi tiết: 50 Xu / ảnh.",
        "Sáng tạo chi tiết + bảo hành: 100 Xu / ảnh.",
        "Cao cấp: 70 Xu / ảnh.",
        "Cao cấp + bảo hành: 140 Xu / ảnh.",
        "Nhạc nền AI: 130 / 150 / 200 Xu.",
        "1 cảnh không giảm; 2–5 cảnh: giảm 10%; 6–10 cảnh: giảm 15%; 11–20 cảnh: giảm 20%.",
    ):
        assert marker in text

    for stale in (
        "Nhạc nền AI: 100 / 150 / 200 Xu.",
        "Video: 200 / 300 / 400 / 500 / 600 / 800 / 1000 / 1200 / 1500 Xu theo gói.",
        "Product Video scene duration: 1 cảnh = 8s",
        "Ảnh: 50 / 150 / 200 / 300 / 400 / 500 / 600 Xu.",
        "Sáng tạo chi tiết + bảo hành: 110 Xu / ảnh.",
        "Cao cấp: 80 Xu / ảnh.",
        "Cao cấp + bảo hành: 150 Xu / ảnh.",
    ):
        assert stale not in text


def test_exported_public_guides_match_the_current_shared_copy():
    public_dir = ROOT / "docs" / "public"
    assert (public_dir / guide.PRICING_DOWNLOAD_FILENAME).read_text(encoding="utf-8") == guide.pricing_markdown()
    assert (public_dir / guide.GUIDE_DOWNLOAD_FILENAME).read_text(encoding="utf-8") == guide.guide_markdown()
    assert (public_dir / "TOAN_AAS_HUONG_DAN_SU_DUNG_CHO_KHACH_V2.md").read_text(encoding="utf-8") == exporter.guide_v2_markdown()


def test_public_pricing_copy_states_current_chat_pro_token_rates_not_a_per_message_fee():
    markdown = guide.pricing_markdown()
    assert "Chat Pro: 5 Xu / 1K token đầu vào; 25 Xu / 1K token đầu ra." in markdown
    assert "5/25 Xu mỗi tin nhắn" not in markdown


if __name__ == "__main__":
    direct_tests = [
        test_default_public_guide_context_uses_canonical_image_prices_and_owner_approved_video_catalog,
        test_pricing_markdown_updates_image_prices_and_owner_approved_video_table,
        test_customer_guide_uses_canonical_image_prices_and_owner_approved_video_examples,
        test_v2_download_guide_uses_canonical_image_prices_and_owner_approved_video_quick_prices,
        test_every_public_locale_uses_the_owner_approved_video_catalog_and_discount_boundary,
        test_shared_cskh_pricing_copy_uses_the_public_video_checkpoint_not_legacy_tiers,
        test_cskh_knowledge_document_matches_current_public_image_music_and_video_copy,
        test_exported_public_guides_match_the_current_shared_copy,
        test_public_pricing_copy_states_current_chat_pro_token_rates_not_a_per_message_fee,
    ]
    for direct_test in direct_tests:
        direct_test()
    print(f"{len(direct_tests)} direct guide checks passed")
