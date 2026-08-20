from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def generate_qr_code_url(content: str, size: int = 300) -> str:
    """Generate free QR Code image URL via public QRServer API."""
    encoded = urllib.parse.quote_plus(str(content or "").strip())
    size_str = f"{max(100, min(1000, size))}x{max(100, min(1000, size))}"
    return f"https://api.qrserver.com/v1/create-qr-code/?size={size_str}&data={encoded}"


def generate_avatar_ai_url(seed: str, avatar_set: int = 1) -> str:
    """Generate free AI robot/monster/human avatar image URL via public RoboHash API."""
    encoded = urllib.parse.quote_plus(str(seed or "toanaas_user").strip())
    set_id = max(1, min(5, int(avatar_set or 1)))
    return f"https://robohash.org/{encoded}.png?set=set{set_id}&size=300x300"


def fetch_usd_vnd_rate() -> dict[str, Any]:
    """Fetch current USD/VND exchange rate with safe fallback."""
    fallback = {
        "usd_vnd": 25450,
        "source": "TOAN AAS Canonical Standard (Offline Safe)",
        "xu_per_usd": 25.45,
        "vnd_per_xu": 1000,
    }
    url = "https://api.exchangerate-api.com/v4/latest/USD"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TOAN-AAS-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                vnd = float(data.get("rates", {}).get("VND", 25450))
                return {
                    "usd_vnd": round(vnd, 0),
                    "source": "ExchangeRate-API (Live)",
                    "xu_per_usd": round(vnd / 1000.0, 2),
                    "vnd_per_xu": 1000,
                }
    except Exception as exc:
        logger.debug("Failed to fetch live exchange rate: %s", exc)
    return fallback


def translate_free_text(text: str, source_lang: str = "en", target_lang: str = "vi") -> dict[str, Any]:
    """Translate prompt or script using public MyMemory API with safe fallback."""
    cleaned = str(text or "").strip()[:500]
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


def fetch_weather_report(city: str = "hanoi") -> dict[str, Any]:
    """Fetch basic current weather for major cities via Open-Meteo API."""
    city_coords = {
        "hanoi": (21.0285, 105.8542, "Hà Nội"),
        "hcm": (10.8231, 106.6297, "TP. Hồ Chí Minh"),
        "danang": (16.0544, 108.2022, "Đà Nẵng"),
    }
    c_key = city.lower().replace(" ", "").replace("-", "")
    lat, lon, city_name = city_coords.get(c_key, (21.0285, 105.8542, "Hà Nội"))
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TOAN-AAS-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                cw = data.get("current_weather", {})
                return {
                    "ok": True,
                    "city": city_name,
                    "temperature": cw.get("temperature", 28),
                    "windspeed": cw.get("windspeed", 10),
                    "weathercode": cw.get("weathercode", 0),
                    "source": "Open-Meteo (Live)",
                }
    except Exception as exc:
        logger.debug("Failed to fetch weather: %s", exc)
    
    return {
        "ok": True,
        "city": city_name,
        "temperature": 28.0,
        "windspeed": 10.0,
        "weathercode": 0,
        "source": "Dự báo chuẩn (Offline Safe)",
    }
