"""Pure word counting and pricing policy for SubDub Auto speaker casting.

This module deliberately has no bot, provider, database, wallet, or environment
dependencies.  Both estimate and actual-charge callers must use the same
counter and Auto-component formula defined here.
"""

from __future__ import annotations

import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_CEILING


AUTO_XU_PER_WORD = Decimal("0.5")

# These scripts do not reliably use spaces between customer-visible words.
# Count each normalized base letter/number as one deterministic billable unit;
# combining marks remain part of their preceding base and are never billed.
UNSPACED_RANGES = (
    (0x3400, 0x4DBF),  # CJK Unified Ideographs Extension A
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0x3040, 0x30FF),  # Hiragana and Katakana
    (0x31F0, 0x31FF),  # Katakana Phonetic Extensions
    (0x0E00, 0x0E7F),  # Thai
    (0xAC00, 0xD7AF),  # Hangul syllables
)


def _unspaced_base(char: str) -> bool:
    codepoint = ord(char)
    return any(start <= codepoint <= end for start, end in UNSPACED_RANGES)


def count_billable_words(text: str) -> int:
    """Count canonical Auto billable units after Unicode NFKC normalization.

    Spaced scripts use contiguous letter/number runs. Han, Kana, Hangul, and
    Thai use one unit per normalized base character. Whitespace, punctuation,
    symbols, emoji, and combining marks do not add billable units.
    """

    count = 0
    in_spaced_word = False
    for char in unicodedata.normalize("NFKC", str(text or "")):
        category = unicodedata.category(char)
        if category.startswith("M"):
            continue
        if _unspaced_base(char) and category[0] in {"L", "N"}:
            count += 1
            in_spaced_word = False
        elif category[0] in {"L", "N"}:
            if not in_spaced_word:
                count += 1
            in_spaced_word = True
        else:
            in_spaced_word = False
    return count


def _non_negative_word_count(value: object, *, name: str) -> int:
    """Normalize persisted integer-like counts without silently truncating."""

    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer word count")
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer word count") from exc
    if not parsed.is_finite() or parsed != parsed.to_integral_value():
        raise ValueError(f"{name} must be an integer word count")
    return max(0, int(parsed))


def auto_volume_discount_percent(words: int) -> int:
    """Return the single applicable Auto word-volume discount tier."""

    safe_words = _non_negative_word_count(words, name="words")
    if safe_words >= 10_000:
        return 20
    if safe_words >= 1_000:
        return 10
    return 0


def auto_voice_component_xu(words: int) -> int:
    """Price only the Auto voice component, rounded up once to whole Xu."""

    safe_words = _non_negative_word_count(words, name="words")
    discount_multiplier = (
        Decimal(100 - auto_volume_discount_percent(safe_words)) / Decimal(100)
    )
    amount = Decimal(safe_words) * AUTO_XU_PER_WORD * discount_multiplier
    return int(amount.to_integral_value(rounding=ROUND_CEILING))


def auto_exact_confirmation_state(
    *,
    quoted_words: int | None,
    actual_words: int,
    exact_known_at_quote: bool,
    quoted_total_xu: int | None = None,
    actual_total_xu: int | None = None,
) -> dict[str, int | bool | None]:
    """Build the pure estimate-versus-actual Auto confirmation decision.

    Subtitle pricing and all wallet/receipt operations belong to the caller.
    A count mismatch requires confirmation even if two rounded prices happen to
    be equal.
    """

    if not isinstance(exact_known_at_quote, bool):
        raise ValueError("exact_known_at_quote must be a boolean")
    quoted = (
        None
        if quoted_words is None
        else _non_negative_word_count(quoted_words, name="quoted_words")
    )
    actual = _non_negative_word_count(actual_words, name="actual_words")
    quoted_total = (
        None
        if quoted_total_xu in (None, "")
        else _non_negative_word_count(quoted_total_xu, name="quoted_total_xu")
    )
    actual_total = (
        None
        if actual_total_xu in (None, "")
        else _non_negative_word_count(actual_total_xu, name="actual_total_xu")
    )
    total_pair_supplied = quoted_total is not None or actual_total is not None
    total_changed = total_pair_supplied and (
        quoted_total is None
        or actual_total is None
        or quoted_total != actual_total
    )
    return {
        "quoted_billable_words": quoted,
        "actual_billable_words": actual,
        "quoted_auto_xu": (
            None if quoted is None else auto_voice_component_xu(quoted)
        ),
        "actual_auto_xu": auto_voice_component_xu(actual),
        "exact_confirmation_required": (
            not exact_known_at_quote
            or quoted is None
            or quoted != actual
            or total_changed
        ),
    }


__all__ = (
    "AUTO_XU_PER_WORD",
    "auto_exact_confirmation_state",
    "auto_voice_component_xu",
    "auto_volume_discount_percent",
    "count_billable_words",
)
