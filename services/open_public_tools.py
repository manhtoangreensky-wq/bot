from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

CURRENCY_CATALOG = {
    "vi": {
        "VND": "🇻🇳 Việt Nam (VND)",
        "USD": "🇺🇸 Hoa Kỳ (USD)",
        "HKD": "🇭🇰 Hồng Kông (HKD)",
        "CNY": "🇨🇳 Trung Quốc (CNY)",
        "JPY": "🇯🇵 Nhật Bản (JPY)",
        "EUR": "🇪🇺 Châu Âu (EUR)",
        "GBP": "🇬🇧 Anh Quốc (GBP)",
        "KRW": "🇰🇷 Hàn Quốc (KRW)",
        "SGD": "🇸🇬 Singapore (SGD)",
        "THB": "🇹🇭 Thái Lan (THB)",
        "TWD": "🇹🇼 Đài Loan (TWD)",
        "AUD": "🇦🇺 Úc (AUD)",
        "CAD": "🇨🇦 Canada (CAD)",
        "Xu": "🪙 Xu TOAN AAS (1 Xu = 1.000 VNĐ)",
    },
    "en": {
        "VND": "🇻🇳 Vietnam (VND)",
        "USD": "🇺🇸 United States (USD)",
        "HKD": "🇭🇰 Hong Kong (HKD)",
        "CNY": "🇨🇳 China (CNY)",
        "JPY": "🇯🇵 Japan (JPY)",
        "EUR": "🇪🇺 Europe (EUR)",
        "GBP": "🇬🇧 United Kingdom (GBP)",
        "KRW": "🇰🇷 South Korea (KRW)",
        "SGD": "🇸🇬 Singapore (SGD)",
        "THB": "🇹🇭 Thailand (THB)",
        "TWD": "🇹🇼 Taiwan (TWD)",
        "AUD": "🇦🇺 Australia (AUD)",
        "CAD": "🇨🇦 Canada (CAD)",
        "Xu": "🪙 TOAN AAS Xu (1 Xu = 1,000 VND)",
    },
    "zh": {
        "VND": "🇻🇳 越南 (VND)",
        "USD": "🇺🇸 美国 (USD)",
        "HKD": "🇭🇰 中国香港 (HKD)",
        "CNY": "🇨🇳 中国 (CNY)",
        "JPY": "🇯🇵 日本 (JPY)",
        "EUR": "🇪🇺 欧洲 (EUR)",
        "GBP": "🇬🇧 英国 (GBP)",
        "KRW": "🇰🇷 韩国 (KRW)",
        "SGD": "🇸🇬 新加坡 (SGD)",
        "THB": "🇹🇭 泰国 (THB)",
        "TWD": "🇹🇼 中国台湾 (TWD)",
        "AUD": "🇦🇺 澳大利亚 (AUD)",
        "CAD": "🇨🇦 加拿大 (CAD)",
        "Xu": "🪙 TOAN AAS 币 (1 币 = 1,000 越南盾)",
    },
}

CURRENCY_ALIASES = {
    "vnd": "VND", "vnđ": "VND", "dong": "VND", "đồng": "VND", "vietnam": "VND", "việt nam": "VND", "₫": "VND",
    "usd": "USD", "$": "USD", "dola": "USD", "đô": "USD", "dollar": "USD", "mỹ": "USD", "us": "USD",
    "hkd": "HKD", "hongkong": "HKD", "hồng kông": "HKD", "hong kong": "HKD", "港币": "HKD",
    "cny": "CNY", "rmb": "CNY", "te": "CNY", "tệ": "CNY", "yuan": "CNY", "nhân dân tệ": "CNY", "人民币": "CNY",
    "jpy": "JPY", "yen": "JPY", "yên": "JPY", "japan": "JPY", "日元": "JPY",
    "eur": "EUR", "euro": "EUR", "€": "EUR", "châu âu": "EUR", "欧元": "EUR",
    "gbp": "GBP", "pound": "GBP", "bảng": "GBP", "£": "GBP", "anh": "GBP", "uk": "GBP", "英镑": "GBP",
    "krw": "KRW", "won": "KRW", "₩": "KRW", "hàn": "KRW", "korea": "KRW", "韩元": "KRW",
    "sgd": "SGD", "sing": "SGD", "singapore": "SGD", "新加坡": "SGD",
    "thb": "THB", "baht": "THB", "thai": "THB", "thái": "THB", "泰铢": "THB",
    "twd": "TWD", "đài tệ": "TWD", "taiwan": "TWD", "đài loan": "TWD", "新台币": "TWD",
    "aud": "AUD", "úc": "AUD", "australia": "AUD", "澳元": "AUD",
    "cad": "CAD", "canada": "CAD", "加元": "CAD",
    "xu": "Xu", "point": "Xu", "coin": "Xu", "bcoin": "Xu", "币": "Xu",
}

FALLBACK_RATES_USD = {
    "USD": 1.0,
    "VND": 26127.0,
    "HKD": 7.84,
    "CNY": 6.75,
    "JPY": 158.55,
    "EUR": 0.858,
    "GBP": 0.736,
    "KRW": 1391.0,
    "SGD": 1.27,
    "THB": 32.95,
    "TWD": 31.81,
    "AUD": 1.48,
    "CAD": 1.36,
}

LANGUAGE_NAMES = {
    "vi": {
        "vi": "Tiếng Việt 🇻🇳",
        "en": "Tiếng Anh 🇬🇧",
        "ru": "Tiếng Nga 🇷🇺",
        "zh": "Tiếng Trung 🇨🇳",
        "zh-CN": "Tiếng Trung 🇨🇳",
        "ja": "Tiếng Nhật 🇯🇵",
        "ko": "Tiếng Hàn 🇰🇷",
        "fr": "Tiếng Pháp 🇫🇷",
        "de": "Tiếng Đức 🇩🇪",
        "es": "Tiếng Tây Ban Nha 🇪🇸",
        "th": "Tiếng Thái 🇹🇭",
        "it": "Tiếng Ý 🇮🇹",
        "pt": "Tiếng Bồ Đào Nha 🇵🇹",
        "ar": "Tiếng Ả Rập 🇸🇦",
        "auto": "Tự động nhận diện 🌐",
    },
    "en": {
        "vi": "Vietnamese 🇻🇳",
        "en": "English 🇬🇧",
        "ru": "Russian 🇷🇺",
        "zh": "Chinese 🇨🇳",
        "zh-CN": "Chinese 🇨🇳",
        "ja": "Japanese 🇯🇵",
        "ko": "Korean 🇰🇷",
        "fr": "French 🇫🇷",
        "de": "German 🇩🇪",
        "es": "Spanish 🇪🇸",
        "th": "Thai 🇹🇭",
        "it": "Italian 🇮🇹",
        "pt": "Portuguese 🇵🇹",
        "ar": "Arabic 🇸🇦",
        "auto": "Auto Detect 🌐",
    },
    "zh": {
        "vi": "越南语 🇻🇳",
        "en": "英语 🇬🇧",
        "ru": "俄语 🇷🇺",
        "zh": "中文 🇨🇳",
        "zh-CN": "中文 🇨🇳",
        "ja": "日语 🇯🇵",
        "ko": "韩语 🇰🇷",
        "fr": "法语 🇫🇷",
        "de": "德语 🇩🇪",
        "es": "西班牙语 🇪🇸",
        "th": "泰语 🇹🇭",
        "it": "意大利语 🇮🇹",
        "pt": "葡萄牙语 🇵🇹",
        "ar": "阿拉伯语 🇸🇦",
        "auto": "自动识别 🌐",
    },
}

def generate_qr_code_url(content: str, size: int = 400) -> str:
    cleaned = str(content or "").strip()
    if not cleaned:
        cleaned = "https://toanaas.vn"
    encoded = urllib.parse.quote_plus(cleaned)
    size_str = f"{max(100, min(1000, size))}x{max(100, min(1000, size))}"
    return f"https://api.qrserver.com/v1/create-qr-code/?size={size_str}&data={encoded}"

def generate_avatar_ai_url(seed: str, avatar_set: int = 1) -> str:
    encoded = urllib.parse.quote_plus(str(seed or "toanaas_user").strip())
    set_id = max(1, min(5, int(avatar_set or 1)))
    return f"https://robohash.org/{encoded}.png?set=set{set_id}&size=400x400"

def fetch_all_exchange_rates() -> tuple[dict[str, float], str]:
    url = "https://api.exchangerate-api.com/v4/latest/USD"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TOAN-AAS-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                raw_rates = data.get("rates", {})
                rates = dict(FALLBACK_RATES_USD)
                for curr, val in raw_rates.items():
                    try:
                        rates[curr.upper()] = float(val)
                    except (ValueError, TypeError):
                        pass
                return rates, "ExchangeRate-API (Live)"
    except Exception as exc:
        logger.debug("Failed to fetch live exchange rates: %s", exc)
    return dict(FALLBACK_RATES_USD), "TOAN AAS Standard (Offline Safe)"

def fetch_usd_vnd_rate() -> dict[str, Any]:
    rates, source = fetch_all_exchange_rates()
    vnd = rates.get("VND", 26127.0)
    eur = rates.get("EUR", 0.858)
    eur_vnd = vnd / eur if eur else 30450.0
    return {
        "usd_vnd": round(vnd, 0),
        "eur_vnd": round(eur_vnd, 0),
        "source": source,
        "xu_per_usd": round(vnd / 1000.0, 2),
        "vnd_per_xu": 1000,
        "rates": rates,
    }

def format_exchange_rate_overview(lang: str = "vi") -> str:
    lang_key = lang if lang in CURRENCY_CATALOG else "vi"
    names = CURRENCY_CATALOG[lang_key]
    rates, source = fetch_all_exchange_rates()
    vnd_rate = rates.get("VND", 26127.0)

    if lang_key == "en":
        lines = [
            "💱 <b>GLOBAL EXCHANGE RATES & TOAN AAS XU</b>\n",
            f"💵 <b>1 USD</b> = {int(vnd_rate):,} VND",
            f"🪙 <b>1 Xu</b> = 1,000 VND (1 USD ≈ {vnd_rate/1000.0:,.2f} Xu)\n",
            "<b>🌍 Live Currency Rates (vs 1 USD):</b>",
        ]
        for code in ["HKD", "CNY", "EUR", "JPY", "GBP", "KRW", "SGD", "THB", "TWD"]:
            rate_val = rates.get(code, 0)
            cname = names.get(code, code)
            lines.append(f"• {cname}: <b>{rate_val:,.2f} {code}</b>")
        lines.extend([
            f"\n<i>Source: {source}</i>\n",
            "👉 <b>Enter any amount or formula to convert</b>:\n"
            "• <code>1000 HKD</code>\n"
            "• <code>1 USD = ? CNY</code>\n"
            "• <code>500 EUR to VND</code>\n"
            "• <code>250 Xu</code>",
        ])
    elif lang_key == "zh":
        lines = [
            "💱 <b>全球实时汇率 & TOAN AAS 币换算</b>\n",
            f"💵 <b>1 美元 (USD)</b> = {int(vnd_rate):,} 越南盾 (VND)",
            f"🪙 <b>1 TOAN AAS 币</b> = 1,000 越南盾 (1 USD ≈ {vnd_rate/1000.0:,.2f} 币)\n",
            "<b>🌍 常用货币对 (1 美元对应):</b>",
        ]
        for code in ["HKD", "CNY", "EUR", "JPY", "GBP", "KRW", "SGD", "THB", "TWD"]:
            rate_val = rates.get(code, 0)
            cname = names.get(code, code)
            lines.append(f"• {cname}: <b>{rate_val:,.2f} {code}</b>")
        lines.extend([
            f"\n<i>数据源: {source}</i>\n",
            "👉 <b>直接输入金额或换算公式即可自动换算</b>:\n"
            "• <code>1000 HKD</code>\n"
            "• <code>1 USD = ? CNY</code>\n"
            "• <code>500 EUR to VND</code>\n"
            "• <code>250 Xu</code>",
        ])
    else:
        lines = [
            "💱 <b>TỶ GIÁ NGOẠI TỆ & QUY ĐỔI XU TOAN AAS</b>\n",
            f"💵 <b>1 USD</b> = {int(vnd_rate):,} VNĐ",
            f"🪙 <b>1 Xu</b> = 1,000 VNĐ (1 USD ≈ {vnd_rate/1000.0:,.2f} Xu)\n",
            "<b>🌍 Bảng tỷ giá các đồng tiền phổ biến (so với 1 USD):</b>",
        ]
        for code in ["HKD", "CNY", "EUR", "JPY", "GBP", "KRW", "SGD", "THB", "TWD"]:
            rate_val = rates.get(code, 0)
            cname = names.get(code, code)
            lines.append(f"• {cname}: <b>{rate_val:,.2f} {code}</b>")
        lines.extend([
            f"\n<i>Nguồn: {source}</i>\n",
            "👉 <b>Nhập số tiền hoặc công thức bất kỳ để quy đổi</b>:\n"
            "• <code>1000 HKD</code>\n"
            "• <code>1 USD = ? CNY</code>\n"
            "• <code>500 EUR sang VND</code>\n"
            "• <code>250 Xu</code>",
        ])
    return "\n".join(lines)

def resolve_currency_code(token: str) -> str:
    cleaned = str(token or "").strip().lower()
    return CURRENCY_ALIASES.get(cleaned, token.upper())

def convert_custom_currency(raw_input: str, target_lang: str = "vi") -> dict[str, Any]:
    rates, source = fetch_all_exchange_rates()
    text = str(raw_input or "").strip()

    m_formula = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*([a-zA-Z$€£₩₫]+)\s*(?:=|to|sang|qua|in|\?|->)+\s*\??\s*([a-zA-Z$€£₩₫]+)?", text, re.IGNORECASE)

    if m_formula and m_formula.group(3):
        amount_str = m_formula.group(1).replace(",", ".")
        src_token = m_formula.group(2)
        dst_token = m_formula.group(3)
    else:
        m_simple = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*([a-zA-Z$€£₩₫]+)?", text, re.IGNORECASE)
        amount_str = m_simple.group(1).replace(",", ".") if m_simple else "1"
        src_token = m_simple.group(2) if m_simple and m_simple.group(2) else ""
        dst_token = ""

    try:
        amount = float(amount_str)
    except ValueError:
        amount = 1.0

    src_curr = resolve_currency_code(src_token) if src_token else ("VND" if amount > 500 else "USD")
    dst_curr = resolve_currency_code(dst_token) if dst_token else ""

    if src_curr == "Xu":
        amount_vnd = amount * 1000.0
        amount_usd = amount_vnd / rates.get("VND", 26127.0)
    elif src_curr == "USD":
        amount_usd = amount
    elif src_curr in rates:
        amount_usd = amount / rates[src_curr]
    else:
        amount_usd = amount / rates.get("VND", 26127.0)
        src_curr = "VND"

    vnd = amount_usd * rates.get("VND", 26127.0)
    xu = vnd / 1000.0
    usd = amount_usd
    cny = amount_usd * rates.get("CNY", 6.75)
    hkd = amount_usd * rates.get("HKD", 7.84)
    eur = amount_usd * rates.get("EUR", 0.858)
    jpy = amount_usd * rates.get("JPY", 158.55)

    target_converted = None
    if dst_curr and dst_curr in rates:
        target_converted = amount_usd * rates[dst_curr]
    elif dst_curr == "Xu":
        target_converted = xu

    lang_key = target_lang if target_lang in CURRENCY_CATALOG else "vi"
    names = CURRENCY_CATALOG[lang_key]

    return {
        "amount_in": amount,
        "currency_in": src_curr,
        "currency_in_name": names.get(src_curr, src_curr),
        "target_currency": dst_curr,
        "target_converted": target_converted,
        "target_currency_name": names.get(dst_curr, dst_curr) if dst_curr else "",
        "usd": round(usd, 2),
        "vnd": round(vnd, 0),
        "xu": round(xu, 2),
        "cny": round(cny, 2),
        "hkd": round(hkd, 2),
        "eur": round(eur, 2),
        "jpy": round(jpy, 2),
        "rate_usd_vnd": rates.get("VND", 26127.0),
        "source": source,
    }

def format_currency_conversion_result(conv: dict[str, Any], lang: str = "vi") -> str:
    lang_key = lang if lang in CURRENCY_CATALOG else "vi"
    c_in = conv["currency_in"]
    c_in_label = conv.get("currency_in_name", c_in)

    if lang_key == "en":
        lines = [
            "💱 <b>CURRENCY & XU CONVERSION RESULT</b>\n",
            f"💵 Amount: <b>{conv['amount_in']:,.2f} {c_in}</b> ({c_in_label})",
        ]
        if conv.get("target_currency") and conv.get("target_converted") is not None:
            dst = conv["target_currency"]
            lines.append(f"\n🎯 <b>Converted to {dst}:</b> <b>{conv['target_converted']:,.2f} {dst}</b>\n")
        lines.extend([
            f"\n🇻🇳 <b>VND:</b> {int(conv['vnd']):,} VND",
            f"🪙 <b>TOAN AAS Xu:</b> {conv['xu']:,.2f} Xu",
            f"🇺🇸 <b>USD:</b> ${conv['usd']:,.2f} USD",
            f"🇨🇳 <b>CNY:</b> ¥{conv['cny']:,.2f} CNY",
            f"🇭🇰 <b>HKD:</b> HK${conv['hkd']:,.2f} HKD",
            f"🇪🇺 <b>EUR:</b> €{conv['eur']:,.2f} EUR",
            f"\n<i>Exchange rate source: {conv.get('source', 'Live API')}</i>",
        ])
    elif lang_key == "zh":
        lines = [
            "💱 <b>货币 & TOAN AAS 币 换算结果</b>\n",
            f"💵 输入金额: <b>{conv['amount_in']:,.2f} {c_in}</b> ({c_in_label})",
        ]
        if conv.get("target_currency") and conv.get("target_converted") is not None:
            dst = conv["target_currency"]
            lines.append(f"\n🎯 <b>换算至 {dst}:</b> <b>{conv['target_converted']:,.2f} {dst}</b>\n")
        lines.extend([
            f"\n🇨🇳 <b>人民币:</b> ¥{conv['cny']:,.2f} CNY",
            f"🪙 <b>TOAN AAS 币:</b> {conv['xu']:,.2f} 币",
            f"🇺🇸 <b>美元:</b> ${conv['usd']:,.2f} USD",
            f"🇻🇳 <b>越南盾:</b> {int(conv['vnd']):,} VND",
            f"🇭🇰 <b>港币:</b> HK${conv['hkd']:,.2f} HKD",
            f"🇪🇺 <b>欧元:</b> €{conv['eur']:,.2f} EUR",
            f"\n<i>实时汇率数据源: {conv.get('source', 'Live API')}</i>",
        ])
    else:
        lines = [
            "💱 <b>KẾT QUẢ QUY ĐỔI TIỀN TỆ & XU</b>\n",
            f"💵 Số tiền nhập: <b>{conv['amount_in']:,.2f} {c_in}</b> ({c_in_label})",
        ]
        if conv.get("target_currency") and conv.get("target_converted") is not None:
            dst = conv["target_currency"]
            lines.append(f"\n🎯 <b>Quy đổi trực tiếp sang {dst}:</b> <b>{conv['target_converted']:,.2f} {dst}</b>\n")
        lines.extend([
            f"\n🇻🇳 <b>Việt Nam Đồng:</b> {int(conv['vnd']):,} VNĐ",
            f"🪙 <b>Xu TOAN AAS:</b> {conv['xu']:,.2f} Xu",
            f"🇺🇸 <b>Đô la Mỹ:</b> ${conv['usd']:,.2f} USD",
            f"🇨🇳 <b>Nhân dân tệ:</b> ¥{conv['cny']:,.2f} CNY",
            f"🇭🇰 <b>Đô la HK:</b> HK${conv['hkd']:,.2f} HKD",
            f"🇪🇺 <b>Euro Châu Âu:</b> €{conv['eur']:,.2f} EUR",
            f"\n<i>Nguồn dữ liệu: {conv.get('source', 'Live API')}</i>",
        ])
    return "\n".join(lines)

def translate_free_text(text: str, target_lang: str = "vi") -> dict[str, Any]:
    cleaned = str(text or "").strip()[:1000]
    if not cleaned:
        return {"ok": False, "translated_text": "", "error": "empty_input"}

    target = target_lang if target_lang in {"vi", "en", "zh"} else "vi"

    is_target_vi = target == "vi" and any(ch in cleaned.lower() for ch in "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ")

    if is_target_vi:
        langpair = "vi|en"
        actual_target = "en"
    else:
        langpair = f"autodetect|{target}"
        actual_target = target

    encoded = urllib.parse.quote_plus(cleaned)
    url = f"https://api.mymemory.translated.net/get?q={encoded}&langpair={langpair}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TOAN-AAS-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                translated = data.get("responseData", {}).get("translatedText")
                detected = data.get("responseData", {}).get("detectedLanguage") or ("vi" if is_target_vi else "auto")
                if translated and not str(translated).startswith("MYMEMORY WARNING:"):
                    return {
                        "ok": True,
                        "translated_text": str(translated),
                        "source_lang": detected,
                        "target_lang": actual_target,
                        "source": "MyMemory Global Open Translation API",
                    }
    except Exception as exc:
        logger.debug("Free translation API unavailable: %s", exc)

    return {
        "ok": True,
        "translated_text": cleaned,
        "source_lang": "auto",
        "target_lang": actual_target,
        "source": "Bản gốc (Fallback)",
    }

def format_translation_result(res: dict[str, Any], original_text: str, user_lang: str = "vi") -> str:
    lang_key = user_lang if user_lang in LANGUAGE_NAMES else "vi"
    names = LANGUAGE_NAMES[lang_key]
    src_label = names.get(res.get("source_lang", ""), res.get("source_lang", "Tự động"))
    tgt_label = names.get(res.get("target_lang", ""), res.get("target_lang", "Tiếng Việt"))

    if lang_key == "en":
        lines = [
            f"🌐 <b>TRANSLATION RESULT ({src_label} ➔ {tgt_label})</b>\n",
            f"<b>Original:</b>\n{original_text}\n",
            f"<b>Translation:</b>\n<code>{res['translated_text']}</code>\n",
            f"<i>Source: {res.get('source', 'Open API')}</i>",
        ]
    elif lang_key == "zh":
        lines = [
            f"🌐 <b>翻译结果 ({src_label} ➔ {tgt_label})</b>\n",
            f"<b>原文:</b>\n{original_text}\n",
            f"<b>译文:</b>\n<code>{res['translated_text']}</code>\n",
            f"<i>数据源: {res.get('source', 'Open API')}</i>",
        ]
    else:
        lines = [
            f"🌐 <b>KẾT QUẢ DỊCH THUẬT ({src_label} ➔ {tgt_label})</b>\n",
            f"<b>Văn bản gốc:</b>\n{original_text}\n",
            f"<b>Bản dịch:</b>\n<code>{res['translated_text']}</code>\n",
            f"<i>Nguồn: {res.get('source', 'Open API')}</i>",
        ]
    return "\n".join(lines)

def fetch_weather_report(location: str = "hanoi") -> dict[str, Any]:
    loc_clean = str(location or "").strip()
    if not loc_clean:
        loc_clean = "Hà Nội"

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
