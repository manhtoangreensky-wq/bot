from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def generate_qr_code_url(content: str, size: int = 400) -> str:
    """Generate free QR Code image URL via public QRServer API."""
    cleaned = str(content or "").strip()
    if not cleaned:
        cleaned = "https://toanaas.vn"
    encoded = urllib.parse.quote_plus(cleaned)
    size_str = f"{max(100, min(1000, size))}x{max(100, min(1000, size))}"
    return f"https://api.qrserver.com/v1/create-qr-code/?size={size_str}&data={encoded}"


def generate_avatar_ai_url(seed: str, avatar_set: int = 1) -> str:
    """Generate free AI robot/monster/human avatar image URL via public RoboHash API."""
    encoded = urllib.parse.quote_plus(str(seed or "toanaas_user").strip())
    set_id = max(1, min(5, int(avatar_set or 1)))
    return f"https://robohash.org/{encoded}.png?set=set{set_id}&size=400x400"


def fetch_usd_vnd_rate() -> dict[str, Any]:
    """Fetch current USD/VND exchange rate with safe fallback."""
    fallback = {
        "usd_vnd": 25450.0,
        "eur_vnd": 27500.0,
        "source": "TOAN AAS Standard (Offline Safe)",
        "xu_per_usd": 25.45,
        "vnd_per_xu": 1000,
    }
    url = "https://api.exchangerate-api.com/v4/latest/USD"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TOAN-AAS-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                rates = data.get("rates", {})
                vnd = float(rates.get("VND", 25450.0))
                eur = float(rates.get("EUR", 0.92))
                eur_vnd = vnd / eur if eur else 27500.0
                return {
                    "usd_vnd": round(vnd, 0),
                    "eur_vnd": round(eur_vnd, 0),
                    "source": "ExchangeRate-API (Live)",
                    "xu_per_usd": round(vnd / 1000.0, 2),
                    "vnd_per_xu": 1000,
                }
    except Exception as exc:
        logger.debug("Failed to fetch live exchange rate: %s", exc)
    return fallback


def convert_custom_currency(raw_input: str) -> dict[str, Any]:
    """Convert custom user input amount (e.g. 50 USD, 1.000.000 VND, 200 Xu)."""
    rate_data = fetch_usd_vnd_rate()
    usd_rate = rate_data["usd_vnd"]
    text = str(raw_input or "").strip().lower()

    # Extract number
    num_match = re.search(r"([0-9]+(?:[.,][0-9]+)?)", text)
    if not num_match:
        amount = 1.0
    else:
        num_str = num_match.group(1).replace(",", ".")
        try:
            amount = float(num_str)
        except ValueError:
            amount = 1.0

    if "usd" in text or "$" in text:
        vnd = amount * usd_rate
        xu = vnd / 1000.0
        return {
            "amount_in": amount,
            "currency_in": "USD",
            "vnd": round(vnd, 0),
            "xu": round(xu, 2),
            "rate_usd": usd_rate,
        }
    elif "xu" in text:
        vnd = amount * 1000.0
        usd = vnd / usd_rate
        return {
            "amount_in": amount,
            "currency_in": "Xu",
            "vnd": round(vnd, 0),
            "usd": round(usd, 2),
            "rate_usd": usd_rate,
        }
    else:
        # Default VND
        vnd = amount if amount > 100 else amount * 1000.0
        usd = vnd / usd_rate
        xu = vnd / 1000.0
        return {
            "amount_in": amount,
            "currency_in": "VND",
            "vnd": round(vnd, 0),
            "usd": round(usd, 2),
            "xu": round(xu, 2),
            "rate_usd": usd_rate,
        }


def translate_free_text(text: str, source_lang: str = "en", target_lang: str = "vi") -> dict[str, Any]:
    """Translate prompt or script using public MyMemory API with safe fallback."""
    cleaned = str(text or "").strip()[:800]
    if not cleaned:
        return {"ok": False, "translated_text": "", "error": "empty_input"}

    pair = f"{source_lang}|{target_lang}"
    encoded = urllib.parse.quote_plus(cleaned)
    url = f"https://api.mymemory.translated.net/get?q={encoded}&langpair={pair}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TOAN-AAS-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                translated = data.get("responseData", {}).get("translatedText")
                if translated and not str(translated).startswith("MYMEMORY WARNING:"):
                    return {
                        "ok": True,
                        "translated_text": str(translated),
                        "source_lang": source_lang,
                        "target_lang": target_lang,
                        "source": "MyMemory Free Open API",
                    }
    except Exception as exc:
        logger.debug("Free translation API unavailable: %s", exc)

    return {
        "ok": True,
        "translated_text": cleaned,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "source": "Original Text (Fallback)",
    }


def fetch_weather_report(location: str = "hanoi") -> dict[str, Any]:
    """Fetch current weather for any city in Vietnam or Internationally."""
    loc_clean = str(location or "").strip()
    if not loc_clean:
        loc_clean = "Hà Nội"

    # Geocoding via Open-Meteo Geocoding API
    lat, lon, display_name, country = 21.0285, 105.8542, "Hà Nội", "Việt Nam"
    geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote_plus(loc_clean)}&count=1&language=vi"
    try:
        req = urllib.request.Request(geo_url, headers={"User-Agent": "TOAN-AAS-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                geo_data = json.loads(resp.read().decode("utf-8"))
                results = geo_data.get("results")
                if results and len(results) > 0:
                    first = results[0]
                    lat = float(first.get("latitude", lat))
                    lon = float(first.get("longitude", lon))
                    display_name = first.get("name", loc_clean)
                    country = first.get("country", "")
    except Exception as exc:
        logger.debug("Geocoding lookup failed: %s", exc)

    # Weather forecast via Open-Meteo
    weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    try:
        req = urllib.request.Request(weather_url, headers={"User-Agent": "TOAN-AAS-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                cw = data.get("current_weather", {})
                w_code = int(cw.get("weathercode", 0))
                descriptions = {
                    0: "Trời quang đãng, nắng nhẹ ☀️",
                    1: "Chủ yếu quang đãng 🌤",
                    2: "Mây rải rác ⛅",
                    3: "Nhiều mây âm u ☁️",
                    45: "Có sương mù 🌫",
                    51: "Mưa phùn nhẹ 🌦",
                    61: "Mưa vừa 🌧",
                    63: "Mưa to 🌧",
                    80: "Mưa rào từng đợt 🌦",
                    95: "Có dông sét ⛈",
                }
                desc = descriptions.get(w_code, "Thời tiết ổn định 🌤")
                return {
                    "ok": True,
                    "city": display_name,
                    "country": country,
                    "temperature": cw.get("temperature", 28.0),
                    "windspeed": cw.get("windspeed", 10.0),
                    "weathercode": w_code,
                    "description": desc,
                    "source": "Open-Meteo Live API",
                }
    except Exception as exc:
        logger.debug("Weather fetch failed: %s", exc)

    return {
        "ok": True,
        "city": loc_clean.title(),
        "country": country,
        "temperature": 29.0,
        "windspeed": 12.0,
        "weathercode": 0,
        "description": "Thời tiết đẹp, nắng nhẹ ☀️",
        "source": "Dự báo chuẩn (Offline Safe)",
    }
