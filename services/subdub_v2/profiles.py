"""Versioned, language-aware subtitle and audio adaptation profiles."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Callable, Iterable


GlyphChecker = Callable[[str], bool]


@dataclass(frozen=True)
class SubtitleProfile:
    name: str
    language: str
    max_cpl: int
    max_lines: int
    max_cps: float = 25.0
    max_event_duration_ms: int = 7000
    font_family: str = "Noto Sans"
    rendered_glyph_required: bool = True
    target_cps: float = 17.0
    warning_cps: float = 20.0
    hard_cps: float = 23.0
    min_duration_ms: int = 833
    gap_frames: int = 2
    safe_width_ratio: float = 0.86
    unicode_normalization: str = "NFC"


@dataclass(frozen=True)
class AudioProfile:
    name: str
    language: str
    provider_speech_rate: float = 1.0
    post_tempo: float = 1.0
    loudness_target_lufs: float = -16.0
    true_peak_dbfs: float = -1.0
    preserve_original_audio: bool = False


SUBTITLE_PROFILES = {
    "vi": SubtitleProfile("vi_telegram_general_v1", "vi", 42, 2, 23.0, target_cps=17.0, warning_cps=20.0, hard_cps=23.0),
    "en": SubtitleProfile("en_telegram_general_v1", "en", 42, 2, 23.0, target_cps=17.0, warning_cps=20.0, hard_cps=23.0),
    # CJK glyphs carry more visual weight, so they use a separate profile.
    "zh": SubtitleProfile("zh_telegram_general_v1", "zh", 20, 2, 16.0, target_cps=12.0, warning_cps=14.0, hard_cps=16.0),
    "ja": SubtitleProfile("ja_telegram_general_v1", "ja", 20, 2, 16.0, target_cps=12.0, warning_cps=14.0, hard_cps=16.0),
    "ko": SubtitleProfile("ko_telegram_general_v1", "ko", 20, 2, 16.0, target_cps=12.0, warning_cps=14.0, hard_cps=16.0),
    "th": SubtitleProfile("th_telegram_general_v1", "th", 35, 2, 20.0, target_cps=15.0, warning_cps=18.0, hard_cps=20.0),
}

AUDIO_PROFILES = {
    "telegram_social_v1": AudioProfile("telegram_social_v1", "auto", loudness_target_lufs=-16.0, true_peak_dbfs=-1.0),
    "streaming_dialogue_v1": AudioProfile("streaming_dialogue_v1", "auto", loudness_target_lufs=-18.0, true_peak_dbfs=-1.0),
    "broadcast_ebu_v1": AudioProfile("broadcast_ebu_v1", "auto", loudness_target_lufs=-23.0, true_peak_dbfs=-1.0),
    "vi": AudioProfile("vi_owner_fidelity_1x_v1", "vi"),
    "en": AudioProfile("en_owner_fidelity_1x_v1", "en"),
    "zh": AudioProfile("zh_owner_fidelity_1x_v1", "zh"),
    "default": AudioProfile("default_owner_fidelity_1x_v1", "auto"),
}


def normalize_language(language: str | None) -> str:
    value = str(language or "auto").strip().lower().replace("_", "-")
    return value.split("-", 1)[0]


def get_subtitle_profile(language_or_profile: str | SubtitleProfile | None) -> SubtitleProfile:
    if isinstance(language_or_profile, SubtitleProfile):
        return language_or_profile
    value = str(language_or_profile or "vi").strip().lower()
    if value in {profile.name.lower() for profile in SUBTITLE_PROFILES.values()}:
        return next(profile for profile in SUBTITLE_PROFILES.values() if profile.name.lower() == value)
    return SUBTITLE_PROFILES.get(normalize_language(value), SUBTITLE_PROFILES["en"])


def get_audio_profile(language_or_profile: str | AudioProfile | None) -> AudioProfile:
    if isinstance(language_or_profile, AudioProfile):
        return language_or_profile
    value = str(language_or_profile or "default").strip().lower()
    if value in {profile.name.lower() for profile in AUDIO_PROFILES.values()}:
        return next(profile for profile in AUDIO_PROFILES.values() if profile.name.lower() == value)
    return AUDIO_PROFILES.get(normalize_language(value), AUDIO_PROFILES["default"])


def _graphemes(text: str) -> list[str]:
    """Keep combining marks with their base character for line/chunk work."""
    result: list[str] = []
    for char in str(text):
        if result and (unicodedata.combining(char) or char in "\ufe0e\ufe0f"):
            result[-1] += char
        else:
            result.append(char)
    return result


def _display_width(grapheme: str, language: str) -> int:
    if normalize_language(language) in {"zh", "ja", "ko"}:
        return 2 if any(unicodedata.east_asian_width(char) in {"W", "F"} for char in grapheme) else 1
    return 1


def _line_width(line: str, language: str) -> int:
    return sum(_display_width(item, language) for item in _graphemes(line))


def display_width(text: str, language: str) -> int:
    return _line_width(str(text or ""), language)


def _split_long_token(token: str, profile: SubtitleProfile) -> list[str]:
    parts: list[str] = []
    current = ""
    width = 0
    for grapheme in _graphemes(token):
        next_width = _display_width(grapheme, profile.language)
        if current and width + next_width > profile.max_cpl:
            parts.append(current)
            current, width = "", 0
        current += grapheme
        width += next_width
    if current or not parts:
        parts.append(current)
    return parts


def wrap_subtitle_text(text: str, profile: SubtitleProfile | str) -> list[str]:
    profile = get_subtitle_profile(profile)
    normalized = unicodedata.normalize("NFC", str(text or "")).strip()
    if not normalized:
        return [""]
    if _line_width(normalized, profile.language) <= profile.max_cpl:
        return [normalized]

    # Spaces are break opportunities for word-oriented scripts. CJK/Thai are
    # handled as grapheme streams because inserting arbitrary spaces changes
    # the text.
    is_cjk = normalize_language(profile.language) in {"zh", "ja", "ko"}
    if not is_cjk and " " in normalized:
        tokens = [item for item in re.split(r"\s+", normalized) if item]
        expanded: list[str] = []
        for token in tokens:
            expanded.extend(_split_long_token(token, profile))
        lines: list[str] = []
        current = ""
        for token in expanded:
            candidate = token if not current else f"{current} {token}"
            if current and _line_width(candidate, profile.language) > profile.max_cpl:
                lines.append(current)
                current = token
            else:
                current = candidate
        if current:
            lines.append(current)
    else:
        lines = []
        current = ""
        width = 0
        for grapheme in _graphemes(normalized):
            item_width = _display_width(grapheme, profile.language)
            if current and width + item_width > profile.max_cpl:
                lines.append(current)
                current, width = "", 0
            current += grapheme
            width += item_width
        if current:
            lines.append(current)

    if len(lines) <= profile.max_lines:
        return lines

    # Keep the configured line count while retaining all text. This branch is
    # only used when the text cannot be represented within the profile width;
    # QC will report the overflow instead of silently dropping content.
    if profile.max_lines == 1:
        return [" ".join(lines)]
    first = ""
    second_parts: list[str] = []
    target = max(1, sum(_line_width(item, profile.language) for item in lines) // profile.max_lines)
    for item in lines:
        candidate = item if not first else f"{first} {item}"
        if first and _line_width(candidate, profile.language) > target and not second_parts:
            second_parts.append(item)
        elif second_parts:
            second_parts.append(item)
        else:
            first = candidate
    if not second_parts:
        second_parts = [""]
    separator = "" if normalize_language(profile.language) in {"zh", "ja", "ko"} else " "
    return [first, separator.join(second_parts)]


def rendered_glyph_qc(text: str, glyph_checker: GlyphChecker | None = None) -> dict[str, object]:
    value = unicodedata.normalize("NFC", str(text or ""))
    if "\ufffd" in value:
        return {"pass": False, "reason": "replacement_character"}
    if any(unicodedata.category(char) in {"Cc", "Cs"} and char not in "\n\r\t" for char in value):
        return {"pass": False, "reason": "control_character"}
    if glyph_checker is not None:
        try:
            if not all(bool(glyph_checker(grapheme)) for grapheme in _graphemes(value)):
                return {"pass": False, "reason": "missing_glyph"}
        except Exception:
            return {"pass": False, "reason": "glyph_checker_error"}
    return {"pass": True, "reason": "checked"}


def subtitle_text_qc(
    text: str,
    lines: Iterable[str],
    duration_ms: int,
    profile: SubtitleProfile | str,
    glyph_checker: GlyphChecker | None = None,
) -> dict[str, object]:
    profile = get_subtitle_profile(profile)
    line_list = list(lines)
    glyph = rendered_glyph_qc(text, glyph_checker)
    widths = [_line_width(line, profile.language) for line in line_list]
    cps = sum(_display_width(item, profile.language) for item in _graphemes(text)) / max(
        0.001, int(duration_ms or 0) / 1000
    )
    return {
        "max_lines_pass": len(line_list) <= profile.max_lines,
        "cpl_pass": all(width <= profile.max_cpl for width in widths),
        "cps_pass": cps <= profile.hard_cps,
        "unicode_pass": "\ufffd" not in str(text),
        "rendered_glyph_pass": bool(glyph["pass"]),
        "glyph_reason": glyph["reason"],
        "cps": round(cps, 3),
    }


__all__ = [
    "AudioProfile",
    "SubtitleProfile",
    "display_width",
    "get_audio_profile",
    "get_subtitle_profile",
    "normalize_language",
    "rendered_glyph_qc",
    "subtitle_text_qc",
    "wrap_subtitle_text",
]
