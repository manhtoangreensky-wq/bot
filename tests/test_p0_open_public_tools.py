import pytest
from services import open_public_tools as opt


def test_generate_qr_code_url():
    url = opt.generate_qr_code_url("https://www.toanaas.vn/")
    assert "api.qrserver.com" in url
    assert "https" in url


def test_generate_avatar_ai_url():
    url = opt.generate_avatar_ai_url("hero_toanaas", 2)
    assert "robohash.org" in url
    assert "set2" in url


def test_fetch_usd_vnd_rate():
    res = opt.fetch_usd_vnd_rate()
    assert "usd_vnd" in res
    assert res["usd_vnd"] > 20000
    assert "xu_per_usd" in res
    assert res["vnd_per_xu"] == 1000


def test_convert_custom_currency_hkd():
    res_hkd = opt.convert_custom_currency("1000 HKD", target_lang="vi")
    assert res_hkd["currency_in"] == "HKD"
    assert res_hkd["amount_in"] == 1000.0
    assert res_hkd["vnd"] > 2000000
    assert res_hkd["xu"] > 2000
    assert res_hkd["usd"] > 100

    text_vi = opt.format_currency_conversion_result(res_hkd, lang="vi")
    assert "1,000.00 HKD" in text_vi
    assert "VNĐ" in text_vi


def test_convert_custom_currency_formula():
    res_formula = opt.convert_custom_currency("1 USD = ? CNY", target_lang="vi")
    assert res_formula["currency_in"] == "USD"
    assert res_formula["target_currency"] == "CNY"
    assert res_formula["target_converted"] > 5.0

    text_vi = opt.format_currency_conversion_result(res_formula, lang="vi")
    assert "CNY" in text_vi


def test_format_exchange_rate_overview_multilang():
    text_vi = opt.format_exchange_rate_overview("vi")
    assert "TỶ GIÁ NGOẠI TỆ" in text_vi
    assert "Hồng Kông" in text_vi
    assert "Trung Quốc" in text_vi

    text_en = opt.format_exchange_rate_overview("en")
    assert "GLOBAL EXCHANGE RATES" in text_en
    assert "Hong Kong" in text_en
    assert "China" in text_en

    text_zh = opt.format_exchange_rate_overview("zh")
    assert "全球实时汇率" in text_zh
    assert "中国香港" in text_zh


def test_translate_free_text_autodetect():
    # Russian to Vietnamese
    res_ru = opt.translate_free_text("Привет, как дела?", target_lang="vi")
    assert res_ru["ok"] is True
    assert len(res_ru["translated_text"]) > 0

    # Format result card
    card_vi = opt.format_translation_result(res_ru, "Привет, как дела?", user_lang="vi")
    assert "KẾT QUẢ DỊCH THUẬT" in card_vi
    assert "Привет" in card_vi


def test_fetch_weather_report_cities():
    res_hanoi = opt.fetch_weather_report("Hà Nội")
    assert res_hanoi["ok"] is True
    assert "Hà Nội" in res_hanoi["city"] or "Hanoi" in res_hanoi["city"]

    res_tokyo = opt.fetch_weather_report("Tokyo")
    assert res_tokyo["ok"] is True
