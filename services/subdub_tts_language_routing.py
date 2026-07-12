from __future__ import annotations

import re
import unicodedata
from typing import Any


_LANGUAGE_ROUTES: dict[str, dict[str, Any]] = {
    "vi": {
        "code": "vi-VN",
        "name": "Vietnamese",
        "boost": "Vietnamese",
        "female": "vi-VN-HoaiMyNeural",
        "male": "vi-VN-NamMinhNeural",
        "aliases": ("vi", "vi-vn", "vietnamese", "viet nam", "tieng viet", "tiếng việt"),
    },
    "en": {
        "code": "en-US",
        "name": "English",
        "boost": "English",
        "female": "en-US-JennyNeural",
        "male": "en-US-GuyNeural",
        "aliases": ("en", "en-us", "english", "tieng anh", "tiếng anh"),
    },
    "ja": {
        "code": "ja-JP",
        "name": "Japanese",
        "boost": "Japanese",
        "female": "ja-JP-NanamiNeural",
        "male": "ja-JP-KeitaNeural",
        "aliases": ("ja", "ja-jp", "jp", "japanese", "tieng nhat", "tiếng nhật", "日本語"),
    },
    "zh": {
        "code": "zh-CN",
        "name": "Chinese",
        "boost": "Chinese",
        "female": "zh-CN-XiaoxiaoNeural",
        "male": "zh-CN-YunxiNeural",
        "aliases": (
            "zh", "zh-cn", "cn", "chinese", "mandarin", "tieng trung", "tiếng trung",
            "中文", "汉语", "漢語", "普通话", "普通話",
        ),
    },
    "ko": {
        "code": "ko-KR",
        "name": "Korean",
        "boost": "Korean",
        "female": "ko-KR-SunHiNeural",
        "male": "ko-KR-InJoonNeural",
        "aliases": ("ko", "ko-kr", "kr", "korean", "tieng han", "tiếng hàn", "한국어"),
    },
    "th": {
        "code": "th-TH",
        "name": "Thai",
        "boost": "Thai",
        "female": "th-TH-PremwadeeNeural",
        "male": "th-TH-NiwatNeural",
        "aliases": ("th", "th-th", "thai", "tieng thai", "tiếng thái", "ไทย"),
    },
    "ar": {
        "code": "ar-SA",
        "name": "Arabic",
        "boost": "Arabic",
        "female": "ar-SA-ZariyahNeural",
        "male": "ar-SA-HamedNeural",
        "aliases": ("ar", "ar-sa", "arabic", "tieng a rap", "tiếng ả rập", "العربية"),
    },
    "hi": {
        "code": "hi-IN",
        "name": "Hindi",
        "boost": "Hindi",
        "female": "hi-IN-SwaraNeural",
        "male": "hi-IN-MadhurNeural",
        "aliases": ("hi", "hi-in", "hindi", "tieng hindi", "tiếng hindi", "हिन्दी", "हिंदी"),
    },
    "ru": {
        "code": "ru-RU",
        "name": "Russian",
        "boost": "Russian",
        "female": "ru-RU-SvetlanaNeural",
        "male": "ru-RU-DmitryNeural",
        "aliases": ("ru", "ru-ru", "russian", "tieng nga", "tiếng nga", "русский"),
    },
    "es": {
        "code": "es-ES",
        "name": "Spanish",
        "boost": "Spanish",
        "female": "es-ES-ElviraNeural",
        "male": "es-ES-AlvaroNeural",
        "aliases": ("es", "es-es", "spanish", "tieng tay ban nha", "tiếng tây ban nha", "español"),
    },
    "fr": {
        "code": "fr-FR",
        "name": "French",
        "boost": "French",
        "female": "fr-FR-DeniseNeural",
        "male": "fr-FR-HenriNeural",
        "aliases": ("fr", "fr-fr", "french", "tieng phap", "tiếng pháp", "français"),
    },
    "de": {
        "code": "de-DE",
        "name": "German",
        "boost": "German",
        "female": "de-DE-KatjaNeural",
        "male": "de-DE-ConradNeural",
        "aliases": ("de", "de-de", "german", "tieng duc", "tiếng đức", "deutsch"),
    },
    "id": {
        "code": "id-ID",
        "name": "Indonesian",
        "boost": "Indonesian",
        "female": "id-ID-GadisNeural",
        "male": "id-ID-ArdiNeural",
        "aliases": ("id", "id-id", "indonesian", "bahasa indonesia", "tieng indonesia", "tiếng indonesia"),
    },
    "ms": {
        "code": "ms-MY",
        "name": "Malay",
        "boost": "Malay",
        "female": "ms-MY-YasminNeural",
        "male": "ms-MY-OsmanNeural",
        "aliases": ("ms", "ms-my", "malay", "bahasa melayu", "tieng ma lai", "tiếng mã lai"),
    },
    "pt": {
        "code": "pt-BR",
        "name": "Portuguese",
        "boost": "Portuguese",
        "female": "pt-BR-FranciscaNeural",
        "male": "pt-BR-AntonioNeural",
        "aliases": ("pt", "pt-br", "pt-pt", "portuguese", "português", "tieng bo dao nha", "tiếng bồ đào nha"),
    },
    "lo": {
        "code": "lo-LA",
        "name": "Lao",
        "boost": "Lao",
        "female": "lo-LA-KeomanyNeural",
        "male": "lo-LA-ChanthavongNeural",
        "aliases": ("lo", "lo-la", "lao", "tieng lao", "tiếng lào", "ລາວ"),
    },
    "km": {
        "code": "km-KH",
        "name": "Khmer",
        "boost": "Khmer",
        "female": "km-KH-SreymomNeural",
        "male": "km-KH-PisethNeural",
        "aliases": ("km", "km-kh", "khmer", "tieng khmer", "tiếng khmer", "ខ្មែរ"),
    },
    "my": {
        "code": "my-MM",
        "name": "Burmese",
        "boost": "Burmese",
        "female": "my-MM-NilarNeural",
        "male": "my-MM-ThihaNeural",
        "aliases": ("my", "my-mm", "burmese", "myanmar", "tieng myanmar", "tiếng myanmar", "မြန်မာ"),
    },
    "fil": {
        "code": "fil-PH",
        "name": "Filipino",
        "boost": "Filipino",
        "female": "fil-PH-BlessicaNeural",
        "male": "fil-PH-AngeloNeural",
        "aliases": ("fil", "fil-ph", "filipino", "tagalog", "tieng philippines", "tiếng philippines"),
    },
}

_SOURCE_ALIASES = {
    "source", "original", "same", "auto", "nguyen ban", "nguyên bản",
    "giu nguyen ngon ngu goc", "giữ nguyên ngôn ngữ gốc", "ngon ngu goc", "ngôn ngữ gốc",
}


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _ascii_fold(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", _compact(value))
    return "".join(char for char in normalized if not unicodedata.combining(char)).replace("đ", "d")


def _alias_keys(value: Any) -> set[str]:
    raw = _compact(value)
    folded = _ascii_fold(value)
    return {item for item in (raw, folded) if item}


_ROUTE_BY_ALIAS: dict[str, str] = {}
for _key, _route in _LANGUAGE_ROUTES.items():
    for _alias in (_key, _route["code"], _route["name"], *_route["aliases"]):
        for _normalized_alias in _alias_keys(_alias):
            _ROUTE_BY_ALIAS[_normalized_alias] = _key


def _gender_from_state(state: dict[str, Any]) -> str:
    values = " ".join(
        str(state.get(key) or "")
        for key in (
            "selected_voice_gender", "requested_voice_gender", "voice_gender", "gender",
            "voice_kind", "voice_style", "voice_label",
        )
    )
    folded = _ascii_fold(values)
    if any(token in folded for token in ("female", "giong nu", "default_female")):
        return "female"
    if any(token in folded for token in ("male", "giong nam", "default_male")):
        return "male"
    return "female"


def _lookup_route(value: Any) -> tuple[str, dict[str, Any]] | tuple[None, None]:
    for candidate in _alias_keys(value):
        key = _ROUTE_BY_ALIAS.get(candidate)
        if key:
            return key, dict(_LANGUAGE_ROUTES[key])
    return None, None


def resolve_subdub_tts_language_route(state: dict[str, Any] | None) -> dict[str, Any]:
    current = dict(state or {})
    requested = str(
        current.get("target_language")
        or current.get("selected_language")
        or current.get("dub_target_language")
        or ""
    ).strip()
    requested_keys = _alias_keys(requested)
    source_requested = not requested or bool(requested_keys & _SOURCE_ALIASES)
    lookup_value = str(
        current.get("source_language")
        or current.get("detected_language")
        or ""
    ).strip() if source_requested else requested

    key, route = _lookup_route(lookup_value)
    if not route and source_requested and _ascii_fold(lookup_value) in {"", "auto", "unknown", "detect", "detected"}:
        return {
            "ok": True,
            "requested_target_language": requested or "source",
            "resolved_tts_language_code": "auto",
            "resolved_tts_language_name": "Auto",
            "tts_language_boost": "auto",
            "resolved_edge_voice_id": "",
            "voice_source": "source_language_auto",
            "unsupported_reason": "",
            "language_route_key": "auto",
        }
    if not route:
        return {
            "ok": False,
            "requested_target_language": requested or lookup_value,
            "resolved_tts_language_code": "",
            "resolved_tts_language_name": "",
            "tts_language_boost": "",
            "resolved_edge_voice_id": "",
            "voice_source": "",
            "unsupported_reason": "unsupported_language_for_tts",
            "language_route_key": "",
        }

    gender = _gender_from_state(current)
    return {
        "ok": True,
        "requested_target_language": requested or lookup_value,
        "resolved_tts_language_code": str(route["code"]),
        "resolved_tts_language_name": str(route["name"]),
        "tts_language_boost": str(route["boost"]),
        "resolved_edge_voice_id": str(route["female" if gender == "female" else "male"]),
        "voice_source": str(current.get("voice_kind") or current.get("selected_voice_kind") or "subdub_selected_voice"),
        "unsupported_reason": "",
        "language_route_key": str(key),
    }


def subdub_tts_language_state_fields(route: dict[str, Any]) -> dict[str, Any]:
    return {
        key: route.get(key)
        for key in (
            "requested_target_language",
            "resolved_tts_language_code",
            "resolved_tts_language_name",
            "tts_language_boost",
            "resolved_edge_voice_id",
            "voice_source",
            "unsupported_reason",
            "language_route_key",
        )
    }
