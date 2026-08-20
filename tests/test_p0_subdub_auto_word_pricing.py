from decimal import Decimal

import pytest

from services.subdub_auto_word_pricing import (
    AUTO_XU_PER_WORD,
    auto_exact_confirmation_state,
    auto_voice_component_xu,
    auto_volume_discount_percent,
    count_billable_words,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Xin chào thế giới", 4),
        ("Hello, world!", 2),
        ("你好世界", 4),
        ("こんにちは世界", 7),
        ("สวัสดีโลก", 7),
        ("안녕하세요 세계", 7),
        ("नमस्ते दुनिया", 2),
        ("مرحبا بالعالم", 2),
        ("Hello，世界!", 3),
    ],
)
def test_billable_word_contract(text, expected):
    assert count_billable_words(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, 0),
        ("", 0),
        ("   … — 👩\u200d💻 + ©  ", 0),
        ("Ｈｅｌｌｏ，１２３", 2),
        ("e\u0301cole Việt_Nam", 3),
        ("Hello世界 สวัสดี", 7),
    ],
)
def test_billable_word_nfkc_symbols_and_mixed_script_invariants(text, expected):
    assert count_billable_words(text) == expected


@pytest.mark.parametrize(
    ("words", "discount", "expected_xu"),
    [
        (0, 0, 0),
        (1, 0, 1),
        (999, 0, 500),
        (1_000, 10, 450),
        (9_999, 10, 4_500),
        (10_000, 20, 4_000),
        (10_001, 20, 4_001),
    ],
)
def test_auto_price_boundary_contract(words, discount, expected_xu):
    assert auto_volume_discount_percent(words) == discount
    assert auto_voice_component_xu(words) == expected_xu
    assert isinstance(auto_voice_component_xu(words), int)


def test_auto_price_uses_decimal_half_xu_and_non_stacking_tiers():
    assert AUTO_XU_PER_WORD == Decimal("0.5")
    assert auto_voice_component_xu(3) == 2
    assert auto_voice_component_xu(1_000) == int(
        (Decimal(1_000) * Decimal("0.5") * Decimal("0.9")).to_integral_value()
    )
    assert auto_voice_component_xu(10_000) == int(
        (Decimal(10_000) * Decimal("0.5") * Decimal("0.8")).to_integral_value()
    )


@pytest.mark.parametrize("value", [None, "", -1, -10_000, "-7"])
def test_empty_or_negative_word_counts_are_canonical_zero(value):
    assert auto_volume_discount_percent(value) == 0
    assert auto_voice_component_xu(value) == 0


@pytest.mark.parametrize(
    "value",
    [True, False, "not-a-count", "1.5", Decimal("NaN"), Decimal("Infinity")],
)
def test_invalid_word_counts_fail_closed_without_truncation(value):
    with pytest.raises(ValueError, match="integer word count"):
        auto_volume_discount_percent(value)
    with pytest.raises(ValueError, match="integer word count"):
        auto_voice_component_xu(value)


def test_integer_like_persisted_count_is_accepted_exactly():
    assert auto_volume_discount_percent("1000") == 10
    assert auto_voice_component_xu("1000") == 450
    assert auto_voice_component_xu(Decimal("10001")) == 4_001


@pytest.mark.parametrize(
    ("quoted", "actual", "known", "required"),
    [
        (999, 999, True, False),
        (999, 1_000, True, True),
        (1, 2, True, True),
        (1_000, 1_000, False, True),
        (None, 0, True, True),
    ],
)
def test_exact_confirmation_decision_uses_counts_not_only_rounded_price(
    quoted, actual, known, required
):
    decision = auto_exact_confirmation_state(
        quoted_words=quoted,
        actual_words=actual,
        exact_known_at_quote=known,
    )

    assert decision == {
        "quoted_billable_words": quoted,
        "actual_billable_words": actual,
        "quoted_auto_xu": (
            None if quoted is None else auto_voice_component_xu(quoted)
        ),
        "actual_auto_xu": auto_voice_component_xu(actual),
        "exact_confirmation_required": required,
    }


def test_exact_confirmation_normalizes_persisted_counts_without_mutating_price():
    decision = auto_exact_confirmation_state(
        quoted_words="1000",
        actual_words=Decimal("10000"),
        exact_known_at_quote=True,
    )
    assert decision == {
        "quoted_billable_words": 1_000,
        "actual_billable_words": 10_000,
        "quoted_auto_xu": 450,
        "actual_auto_xu": 4_000,
        "exact_confirmation_required": True,
    }


def test_exact_confirmation_requires_reconfirm_when_total_changes_at_same_word_count():
    decision = auto_exact_confirmation_state(
        quoted_words=1_000,
        actual_words=1_000,
        exact_known_at_quote=True,
        quoted_total_xu=550,
        actual_total_xu=650,
    )

    assert decision["quoted_billable_words"] == 1_000
    assert decision["actual_billable_words"] == 1_000
    assert decision["exact_confirmation_required"] is True


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "quoted_words": 1,
                "actual_words": 1,
                "exact_known_at_quote": "yes",
            },
            "must be a boolean",
        ),
        (
            {
                "quoted_words": "unknown",
                "actual_words": 1,
                "exact_known_at_quote": True,
            },
            "integer word count",
        ),
        (
            {
                "quoted_words": 1,
                "actual_words": 1.25,
                "exact_known_at_quote": True,
            },
            "integer word count",
        ),
    ],
)
def test_exact_confirmation_invalid_inputs_fail_closed(kwargs, message):
    with pytest.raises(ValueError, match=message):
        auto_exact_confirmation_state(**kwargs)
