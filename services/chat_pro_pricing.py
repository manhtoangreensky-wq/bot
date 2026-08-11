"""Pure pricing policy for public Claude Opus chat.

No environment, database, wallet, or provider state is read here. Provider
rates are converted with the approved 3x multiplier, then the public
input/output tariff is rounded up to a five-Xu amount per 1K tokens. Each
request is still rounded only once after actual usage is known.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import Any, Iterable, Mapping


OPUS_MODEL_ID = "claude-opus-4-8"
CLAUDE_OPUS_MODEL = OPUS_MODEL_ID
OPUS_INPUT_USD_PER_MILLION = Decimal("6")
OPUS_OUTPUT_USD_PER_MILLION = Decimal("30")
OPUS_CACHE_READ_USD_PER_MILLION = Decimal("0.60")
SALE_MULTIPLIER = Decimal("3")
DEFAULT_USD_FIXED_RATE_VND = 25_000
DEFAULT_XU_TO_VND = 100
PUBLIC_CHAT_VISIBLE_RATE_INCREMENT_XU = Decimal("5")
MAX_PRO_OUTPUT_TOKENS = 4_096
KEY4U_RATE_EFFECTIVE_DATE = date(2026, 8, 9)
KEY4U_RATE_REVIEW_BY = date(2026, 9, 8)


def _whole(value: Any, name: str, *, positive: bool = False) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a {'positive' if positive else 'non-negative'} integer")
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a {'positive' if positive else 'non-negative'} integer") from exc
    if not parsed.is_finite() or parsed != parsed.to_integral_value():
        raise ValueError(f"{name} must be a {'positive' if positive else 'non-negative'} integer")
    result = int(parsed)
    if result < (1 if positive else 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'non-negative'} integer")
    return result


@dataclass(frozen=True)
class OpusUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_tokens", _whole(self.input_tokens, "input_tokens"))
        object.__setattr__(self, "output_tokens", _whole(self.output_tokens, "output_tokens"))
        object.__setattr__(self, "cache_read_tokens", _whole(self.cache_read_tokens, "cache_read_tokens"))


TokenUsage = OpusUsage


@dataclass(frozen=True)
class ClaudeOpusPricing:
    """Injectable Xu rates used by isolated runtime tests/integrations."""

    input_xu_per_million: Decimal | int | str
    output_xu_per_million: Decimal | int | str
    cache_read_xu_per_million: Decimal | int | str = 0
    multiplier: Decimal | int | str = SALE_MULTIPLIER

    def _decimal(self, value: Any, name: str) -> Decimal:
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be non-negative") from exc
        if not parsed.is_finite() or parsed < 0:
            raise ValueError(f"{name} must be non-negative")
        return parsed

    @property
    def input_rate(self) -> Decimal:
        return self._decimal(self.input_xu_per_million, "input_xu_per_million")

    @property
    def output_rate(self) -> Decimal:
        return self._decimal(self.output_xu_per_million, "output_xu_per_million")

    @property
    def cache_rate(self) -> Decimal:
        return self._decimal(self.cache_read_xu_per_million, "cache_read_xu_per_million")

    @property
    def sale_multiplier(self) -> Decimal:
        return self._decimal(self.multiplier, "multiplier")


def calculate_actual_xu(usage: OpusUsage, pricing: ClaudeOpusPricing) -> int:
    normalized = usage if isinstance(usage, OpusUsage) else OpusUsage(**dict(usage))
    numerator = (
        Decimal(normalized.input_tokens) * pricing.input_rate
        + Decimal(normalized.output_tokens) * pricing.output_rate
        + Decimal(normalized.cache_read_tokens) * pricing.cache_rate
    ) * pricing.sale_multiplier
    return int((numerator / Decimal(1_000_000)).to_integral_value(rounding=ROUND_CEILING))


def _source_sale_rates_per_thousand(
    *, usd_fixed_rate_vnd: Any = DEFAULT_USD_FIXED_RATE_VND, xu_to_vnd: Any = DEFAULT_XU_TO_VND
) -> dict[str, Decimal]:
    usd_vnd = _whole(usd_fixed_rate_vnd, "usd_fixed_rate_vnd", positive=True)
    xu_vnd = _whole(xu_to_vnd, "xu_to_vnd", positive=True)
    conversion = SALE_MULTIPLIER * Decimal(usd_vnd) / Decimal(xu_vnd) / Decimal(1_000)
    return {
        "input": OPUS_INPUT_USD_PER_MILLION * conversion,
        "output": OPUS_OUTPUT_USD_PER_MILLION * conversion,
        "cache_read": OPUS_CACHE_READ_USD_PER_MILLION * conversion,
    }


def _round_visible_rate_xu(value: Decimal) -> Decimal:
    return (
        value / PUBLIC_CHAT_VISIBLE_RATE_INCREMENT_XU
    ).to_integral_value(rounding=ROUND_CEILING) * PUBLIC_CHAT_VISIBLE_RATE_INCREMENT_XU


def public_chat_customer_pricing(
    *, usd_fixed_rate_vnd: Any = DEFAULT_USD_FIXED_RATE_VND, xu_to_vnd: Any = DEFAULT_XU_TO_VND
) -> ClaudeOpusPricing:
    """Return the single retail tariff shared by Pro reservations and settlement."""
    source = _source_sale_rates_per_thousand(
        usd_fixed_rate_vnd=usd_fixed_rate_vnd,
        xu_to_vnd=xu_to_vnd,
    )
    return ClaudeOpusPricing(
        input_xu_per_million=_round_visible_rate_xu(source["input"]) * Decimal(1_000),
        output_xu_per_million=_round_visible_rate_xu(source["output"]) * Decimal(1_000),
        cache_read_xu_per_million=source["cache_read"] * Decimal(1_000),
        multiplier=1,
    )


def calculate_opus_provider_cost_usd(input_tokens: Any, output_tokens: Any, cache_read_tokens: Any = 0) -> Decimal:
    usage = OpusUsage(input_tokens, output_tokens, cache_read_tokens)
    return (
        Decimal(usage.input_tokens) * OPUS_INPUT_USD_PER_MILLION
        + Decimal(usage.output_tokens) * OPUS_OUTPUT_USD_PER_MILLION
        + Decimal(usage.cache_read_tokens) * OPUS_CACHE_READ_USD_PER_MILLION
    ) / Decimal(1_000_000)


def calculate_opus_charge_xu(
    input_tokens: Any,
    output_tokens: Any,
    cache_read_tokens: Any = 0,
    *,
    usd_fixed_rate_vnd: Any = DEFAULT_USD_FIXED_RATE_VND,
    xu_to_vnd: Any = DEFAULT_XU_TO_VND,
) -> int:
    return calculate_actual_xu(
        OpusUsage(input_tokens, output_tokens, cache_read_tokens),
        public_chat_customer_pricing(
            usd_fixed_rate_vnd=usd_fixed_rate_vnd,
            xu_to_vnd=xu_to_vnd,
        ),
    )


def opus_price_per_thousand_xu(
    *, usd_fixed_rate_vnd: Any = DEFAULT_USD_FIXED_RATE_VND, xu_to_vnd: Any = DEFAULT_XU_TO_VND
) -> dict[str, Decimal]:
    pricing = public_chat_customer_pricing(
        usd_fixed_rate_vnd=usd_fixed_rate_vnd,
        xu_to_vnd=xu_to_vnd,
    )
    return {
        "input": pricing.input_rate / Decimal(1_000),
        "output": pricing.output_rate / Decimal(1_000),
        "cache_read": pricing.cache_rate / Decimal(1_000),
    }


def opus_price_per_thousand_labels(**kwargs: Any) -> dict[str, str]:
    def label(value: Decimal) -> str:
        return format(value, "f").rstrip("0").rstrip(".") or "0"

    return {key: label(value) for key, value in opus_price_per_thousand_xu(**kwargs).items()}


def pricing_rate_review_status(as_of: date | datetime | str | None = None) -> dict[str, Any]:
    if as_of is None:
        checked = date.today()
    elif isinstance(as_of, datetime):
        checked = as_of.date()
    elif isinstance(as_of, date):
        checked = as_of
    else:
        try:
            checked = date.fromisoformat(str(as_of).strip())
        except ValueError as exc:
            raise ValueError("as_of must be an ISO date") from exc
    return {
        "effective_date": KEY4U_RATE_EFFECTIVE_DATE.isoformat(),
        "review_by": KEY4U_RATE_REVIEW_BY.isoformat(),
        "checked_on": checked.isoformat(),
        "review_required": checked > KEY4U_RATE_REVIEW_BY,
    }


def estimate_reservation_usage(
    messages: Iterable[Mapping[str, Any]], max_output_tokens: Any, *, extra_input_tokens: Any = 0
) -> OpusUsage:
    if isinstance(messages, (str, bytes, bytearray)):
        raise ValueError("messages must be mappings")
    estimate = 32
    for message in list(messages):
        if not isinstance(message, Mapping):
            raise ValueError("messages must be mappings")
        estimate += 16
        for key in ("role", "content", "name"):
            estimate += len(str(message.get(key) or "").encode("utf-8"))
    estimate += _whole(extra_input_tokens, "extra_input_tokens")
    output = min(_whole(max_output_tokens, "max_output_tokens"), MAX_PRO_OUTPUT_TOKENS)
    return OpusUsage(estimate, output, 0)


def reserve_xu(
    messages: Iterable[Mapping[str, Any]],
    max_output_tokens: Any,
    *,
    extra_input_tokens: Any = 0,
    usd_fixed_rate_vnd: Any = DEFAULT_USD_FIXED_RATE_VND,
    xu_to_vnd: Any = DEFAULT_XU_TO_VND,
) -> int:
    usage = estimate_reservation_usage(messages, max_output_tokens, extra_input_tokens=extra_input_tokens)
    return calculate_opus_charge_xu(
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_read_tokens,
        usd_fixed_rate_vnd=usd_fixed_rate_vnd,
        xu_to_vnd=xu_to_vnd,
    )


__all__ = [
    "CLAUDE_OPUS_MODEL", "ClaudeOpusPricing", "DEFAULT_USD_FIXED_RATE_VND", "DEFAULT_XU_TO_VND",
    "KEY4U_RATE_EFFECTIVE_DATE", "KEY4U_RATE_REVIEW_BY", "MAX_PRO_OUTPUT_TOKENS",
    "OPUS_CACHE_READ_USD_PER_MILLION", "OPUS_INPUT_USD_PER_MILLION", "OPUS_MODEL_ID",
    "OPUS_OUTPUT_USD_PER_MILLION", "OpusUsage", "SALE_MULTIPLIER", "TokenUsage",
    "calculate_actual_xu", "calculate_opus_charge_xu", "calculate_opus_provider_cost_usd",
    "estimate_reservation_usage", "opus_price_per_thousand_labels", "opus_price_per_thousand_xu",
    "public_chat_customer_pricing",
    "pricing_rate_review_status", "reserve_xu",
]
