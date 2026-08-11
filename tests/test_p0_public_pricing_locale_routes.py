import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import pricing_guide_content as guide
from services import video_ai_real_pricing as canonical


BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
LANDING_SOURCE = (ROOT / "index.html").read_text(encoding="utf-8")


INTERNATIONAL_PRICING_TITLES = {
    "en": "TOAN AAS Pricing",
    "zh": "TOAN AAS 价格",
    "es": "Precios TOAN AAS",
    "pt": "Preços TOAN AAS",
    "fr": "Tarifs TOAN AAS",
    "de": "TOAN AAS Preise",
    "ja": "TOAN AAS 料金",
    "ko": "TOAN AAS 요금",
    "hi": "TOAN AAS मूल्य",
    "ar": "أسعار TOAN AAS",
    "ru": "Цены TOAN AAS",
    "tr": "TOAN AAS Fiyatları",
    "th": "ราคา TOAN AAS",
    "fil": "Mga Presyo ng TOAN AAS",
    "it": "Prezzi TOAN AAS",
    "id": "Harga TOAN AAS",
}

INTERNATIONAL_GUIDE_TITLES = {
    "en": "TOAN AAS Customer Guide",
    "zh": "TOAN AAS 使用指南",
    "es": "Guía del usuario TOAN AAS",
    "pt": "Guia do usuário TOAN AAS",
    "fr": "Guide d’utilisation TOAN AAS",
    "de": "TOAN AAS Benutzerhandbuch",
    "ja": "TOAN AAS ユーザーガイド",
    "ko": "TOAN AAS 사용자 가이드",
    "hi": "TOAN AAS उपयोगकर्ता मार्गदर्शिका",
    "ar": "دليل المستخدم TOAN AAS",
    "ru": "Руководство пользователя TOAN AAS",
    "tr": "TOAN AAS Kullanım Kılavuzu",
    "th": "คู่มือผู้ใช้ TOAN AAS",
    "fil": "Gabay para sa gumagamit ng TOAN AAS",
    "it": "Guida utente TOAN AAS",
    "id": "Panduan Pengguna TOAN AAS",
}


def _current_image_prices() -> list[str]:
    return [str(int(item["unit_xu"])) for item in canonical.public_image_quality_catalog()]


def _current_product_video_prices() -> list[str]:
    return [
        f"{int(item['unit_xu']):,}".replace(",", ".")
        for item in guide.public_product_video_catalog()
    ]


def test_international_public_pricing_is_localized_with_current_canonical_prices():
    text = "\n".join(guide.all_pricing_lines(lang="es"))

    assert INTERNATIONAL_PRICING_TITLES["es"] in text
    for price in _current_image_prices():
        assert f"{price} Xu" in text
    for price in _current_product_video_prices():
        assert f"{price} Xu" in text
    assert "50 / 150 / 200 / 300 / 400 / 500 / 600" not in text
    assert "200 / 300 / 400 / 500 / 600 / 800 / 1000 / 1200 / 1500" not in text


def test_international_public_guide_is_localized_and_has_current_product_price_lists():
    text = "\n".join(guide.all_guide_lines(lang="fil"))

    assert INTERNATIONAL_GUIDE_TITLES["fil"] in text
    for price in _current_image_prices():
        assert f"{price} Xu" in text
    for price in _current_product_video_prices():
        assert f"{price} Xu" in text
    assert "Gói Trải nghiệm 200 Xu" not in text
    assert "Ảnh 50 Xu" not in text


def test_international_public_documents_exclude_vietnam_topup_promotions_but_keep_member_discounts():
    text = "\n".join(
        [
            guide.pricing_markdown(lang="en"),
            guide.guide_markdown(lang="zh"),
        ]
    ).lower()

    for vietnam_only_promotion in (
        "first settled top-up",
        "second settled top-up",
        "+30% xu",
        "+20% xu",
        "payos/bank-transfer campaigns",
    ):
        assert vietnam_only_promotion not in text

    assert "member service discounts remain available when eligible" in text


def test_international_public_guides_have_a_base_xu_only_topup_section():
    for lang in INTERNATIONAL_GUIDE_TITLES:
        section_keys = [key for key, _title, _body in guide._international_guide_sections(lang)]
        assert "credits" in section_keys
        assert guide.guide_lines("topup", lang=lang) == guide.guide_lines("credits", lang=lang)

    english = "\n".join(guide.guide_lines("topup", lang="en"))
    chinese = "\n".join(guide.guide_lines("topup", lang="zh"))
    assert "International top-ups receive only verified base Xu." in english
    assert "国际充值只获得经核验的基础 Xu。" in chinese


def test_vietnamese_public_topup_guide_discloses_the_international_base_xu_boundary():
    text = "\n".join(guide.guide_lines("topup", lang="vi"))

    assert "Khách quốc tế chỉ nhận Xu gốc đã xác minh" in text
    assert "bonus, mã nạp, referral Xu hoặc Xu điều chỉnh vượt mức" in text


def test_public_pricing_keeps_the_same_base_xu_only_boundary_for_every_international_locale():
    for lang in INTERNATIONAL_PRICING_TITLES:
        text = "\n".join(guide.pricing_lines("member", lang=lang))
        expected_policy = guide._INTERNATIONAL_TOPUP_GUIDE_COPY[lang][1][0]
        assert expected_policy in text

    vietnamese = "\n".join(guide.pricing_lines("member", lang="vi"))
    assert "Khách quốc tế chỉ nhận Xu gốc đã xác minh" in vietnamese


def test_public_html_and_routes_accept_and_preserve_locale():
    page = guide.lines_to_html_page("Pricing", ["copy"], lang="en", home_href="/?lang=en")
    assert '<html lang="en">' in page
    assert 'href="/?lang=en"' in page
    assert "data-locale-resource" in LANDING_SOURCE
    assert "async def public_pricing_page(lang: str = \"vi\")" in BOT_SOURCE
    assert "async def public_guide_page(lang: str = \"vi\")" in BOT_SOURCE
    assert "async def download_pricing_markdown(lang: str = \"vi\")" in BOT_SOURCE
    assert "async def download_guide_markdown(lang: str = \"vi\")" in BOT_SOURCE
    assert "requested_locale = normalize_user_language(lang) or \"vi\"" in BOT_SOURCE
    assert 'home_href=f"/?lang={requested_locale}"' in BOT_SOURCE


def test_public_page_titles_use_the_existing_native_locale_labels():
    for lang, title in INTERNATIONAL_PRICING_TITLES.items():
        assert guide.public_page_title("pricing", lang) == title
    for lang, title in INTERNATIONAL_GUIDE_TITLES.items():
        assert guide.public_page_title("guide", lang) == title


def test_public_markdown_downloads_keep_every_supported_public_locale():
    assert "public_copy_locale," in BOT_SOURCE
    assert "locale = public_copy_locale(lang)" in BOT_SOURCE
    assert "public_guide_markdown(public_copy_locale(lang))" in BOT_SOURCE


def test_every_international_locale_has_its_own_public_pricing_copy_and_video_matches_checkpoint():
    vietnamese_video = "\n".join(guide.pricing_lines("video", lang="vi"))
    assert "Nhanh gọn: <b>200 Xu / cảnh</b> — 5 giây." in vietnamese_video
    assert "Điện ảnh nhiều cảnh: <b>2.360 Xu / cảnh</b> — 10 giây." in vietnamese_video
    assert "2–5 cảnh: giảm 10%." in vietnamese_video
    assert "2-9 cảnh" not in vietnamese_video

    for lang, title in INTERNATIONAL_PRICING_TITLES.items():
        assert guide.public_copy_locale(lang) == lang
        pricing = "\n".join(guide.pricing_lines("total", lang=lang))
        video = "\n".join(guide.pricing_lines("video", lang=lang))
        document = "\n".join((guide.pricing_markdown(lang=lang), guide.guide_markdown(lang=lang))).lower()

        assert title in pricing
        for price in _current_image_prices():
            assert f"{price} Xu" in pricing
        assert re.search(r"130\b.*150\b.*200\s+Xu", pricing, flags=re.DOTALL)
        for price in _current_product_video_prices():
            assert f"{price} Xu" in video
        for vietnam_only_promotion in ("first settled top-up", "second settled top-up", "+30% xu", "+20% xu"):
            assert vietnam_only_promotion not in document


if __name__ == "__main__":
    checks = [
        test_international_public_pricing_is_localized_with_current_canonical_prices,
        test_international_public_guide_is_localized_and_has_current_product_price_lists,
        test_international_public_documents_exclude_vietnam_topup_promotions_but_keep_member_discounts,
        test_international_public_guides_have_a_base_xu_only_topup_section,
        test_vietnamese_public_topup_guide_discloses_the_international_base_xu_boundary,
        test_public_pricing_keeps_the_same_base_xu_only_boundary_for_every_international_locale,
        test_public_html_and_routes_accept_and_preserve_locale,
        test_public_page_titles_use_the_existing_native_locale_labels,
        test_public_markdown_downloads_keep_every_supported_public_locale,
        test_every_international_locale_has_its_own_public_pricing_copy_and_video_matches_checkpoint,
    ]
    for check in checks:
        check()
    print(f"{len(checks)} direct public locale route checks passed")
