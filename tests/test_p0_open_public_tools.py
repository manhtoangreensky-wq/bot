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


def test_convert_custom_currency():
    res_usd = opt.convert_custom_currency("50 USD")
    assert res_usd["currency_in"] == "USD"
    assert res_usd["amount_in"] == 50.0
    assert res_usd["vnd"] > 1000000
    assert res_usd["xu"] > 1000

    res_vnd = opt.convert_custom_currency("500000 VND")
    assert res_vnd["currency_in"] == "VND"
    assert res_vnd["vnd"] == 500000.0
    assert res_vnd["xu"] == 500.0

    res_xu = opt.convert_custom_currency("250 Xu")
    assert res_xu["currency_in"] == "Xu"
    assert res_xu["vnd"] == 250000.0


def test_translate_free_text():
    res = opt.translate_free_text("Hello world", source_lang="en", target_lang="vi")
    assert res["ok"] is True
    assert len(res["translated_text"]) > 0


def test_fetch_weather_report_cities():
    res_hanoi = opt.fetch_weather_report("Hà Nội")
    assert res_hanoi["ok"] is True
    assert "Hà Nội" in res_hanoi["city"] or "Hanoi" in res_hanoi["city"]

    res_tokyo = opt.fetch_weather_report("Tokyo")
    assert res_tokyo["ok"] is True
