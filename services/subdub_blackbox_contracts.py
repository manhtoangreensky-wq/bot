"""Pure routing contracts for isolated SubDub language and product lanes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
import unicodedata


_LANGUAGE_ALIASES = {
    "vi": "vi",
    "vie": "vi",
    "vietnamese": "vi",
    "tieng viet": "vi",
    "en": "en",
    "eng": "en",
    "english": "en",
    "zh": "zh",
    "zho": "zh",
    "chi": "zh",
    "cn": "zh",
    "chinese": "zh",
    "mandarin": "zh",
    "ja": "ja",
    "jpn": "ja",
    "japanese": "ja",
    "ko": "ko",
    "kor": "ko",
    "korean": "ko",
    "th": "th",
    "tha": "th",
    "thai": "th",
    "ar": "ar",
    "ara": "ar",
    "arabic": "ar",
    "hi": "hi",
    "hin": "hi",
    "hindi": "hi",
    "ru": "ru",
    "rus": "ru",
    "russian": "ru",
}


def _ascii_key(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def normalize_language_code(value: object) -> tuple[str, str]:
    raw = str(value or "").strip().lower().replace("_", "-")
    if not raw or raw in {"auto", "detect", "default", "unknown", "-"}:
        return "auto", "auto"
    key = _ascii_key(raw)
    code = _LANGUAGE_ALIASES.get(key)
    if code:
        return code, code
    if raw.startswith("zh-"):
        return "zh", raw
    if re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*", raw):
        return raw.split("-", 1)[0], raw
    return raw.split("-", 1)[0][:12], raw[:32]


@dataclass(frozen=True)
class LanguageBlackbox:
    family: str
    language_code: str
    requested_locale: str
    translation_locale: str
    tts_locale: str


@dataclass(frozen=True)
class LaneBlackbox:
    lane: str
    uses_subtitles: bool
    uses_translation: bool
    uses_tts: bool
    keep_original_audio_default: bool


@dataclass(frozen=True)
class SubDubBlackboxContract:
    language: LanguageBlackbox
    lane: LaneBlackbox

    def debug_fields(self) -> dict:
        return {
            "subdub_language_blackbox": self.language.family,
            "subdub_language_code": self.language.language_code,
            "subdub_requested_locale": self.language.requested_locale,
            "subdub_translation_locale": self.language.translation_locale,
            "subdub_tts_locale": self.language.tts_locale,
            "subdub_lane_blackbox": self.lane.lane,
            "subdub_lane_contract": asdict(self.lane),
        }


def resolve_language_blackbox(value: object) -> LanguageBlackbox:
    code, locale = normalize_language_code(value)
    family = {
        "vi": "vietnamese",
        "en": "english",
        "zh": "chinese",
    }.get(code, "international")
    return LanguageBlackbox(
        family=family,
        language_code=code,
        requested_locale=locale,
        translation_locale=locale,
        tts_locale=locale,
    )


def resolve_lane_blackbox(mode: object) -> LaneBlackbox:
    value = str(mode or "").strip().lower().replace("-", "_")
    if value in {"subtitle_plus_dub", "subtitle_dub", "subdub", "combo", "video_subtitle_dub"}:
        return LaneBlackbox("combo", True, True, True, False)
    if value in {"dub", "dubbing", "voice", "video_dub"}:
        return LaneBlackbox("dub", False, False, True, False)
    if value in {"create", "auto_subtitle", "subtitle_create", "original_subtitle"}:
        return LaneBlackbox("auto_subtitle", True, False, False, True)
    return LaneBlackbox("subtitle", True, True, False, True)


def resolve_subdub_contract(mode: object, target_language: object) -> SubDubBlackboxContract:
    return SubDubBlackboxContract(
        language=resolve_language_blackbox(target_language),
        lane=resolve_lane_blackbox(mode),
    )
