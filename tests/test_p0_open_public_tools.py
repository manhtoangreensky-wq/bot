import pytest
from services import open_public_tools as opt


def test_generate_qr_code_url():
    url = opt.generate_qr_code_url("https://toanaas.vn")
    assert "api.qrserver.com" in url
    assert "https%3A%2F%2Ftoanaas.vn" in url or "https%3a%2f%2ftoanaas.vn" in url or "https" in url


def test_generate_avatar_ai_url():
    url = opt.generate_avatar_ai_url("user123", 2)
    assert "robohash.org" in url
    assert "set2" in url


def test_fetch_usd_vnd_rate():
    res = opt.fetch_usd_vnd_rate()
    assert "usd_vnd" in res
    assert res["usd_vnd"] > 20000
    assert "xu_per_usd" in res
    assert res["vnd_per_xu"] == 1000


def test_translate_free_text():
    res = opt.translate_free_text("Hello world", source_lang="en", target_lang="vi")
    assert res["ok"] is True
    assert len(res["translated_text"]) > 0


def test_fetch_weather_report():
    res = opt.fetch_weather_report("hanoi")
    assert res["ok"] is True
    assert res["city"] == "Hà Nội"
    assert "temperature" in res
