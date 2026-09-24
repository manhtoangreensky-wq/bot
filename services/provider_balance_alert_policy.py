"""Notification-only fixed USD-credit policy; no billing/freeze/network effects.

Callers must supply a provider-verified USD credit value, not an API health
response, raw quota units, synthetic zero, or an unlabelled local estimate.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation


def classify_balance(balance, *, checked_at: datetime | None, now: datetime,
                     max_age_seconds: int, fetch_ok: bool = True) -> dict:
    """Classify fresh balance against Owner's fixed 100 USD reference.

    Compare unrounded values: exactly 10 USD is normal, less than 10 is low.
    Polling frequency and persistence belong to the caller, not this policy.
    """
    result = {'state': 'UNKNOWN', 'low': False, 'balance_usd': None,
              'remaining_percent': None, 'baseline_usd': Decimal('100')}
    if fetch_ok is not True:
        return {**result, 'reason': 'fetch_not_verified'}
    if (not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None
            or type(max_age_seconds) is not int or max_age_seconds <= 0):
        raise ValueError('invalid_freshness_policy')
    if (not isinstance(checked_at, datetime) or checked_at.tzinfo is None
            or checked_at.utcoffset() is None):
        return {**result, 'reason': 'timestamp_missing_or_naive'}
    age = (now - checked_at).total_seconds()
    if age < 0 or age > max_age_seconds:
        return {**result, 'reason': 'snapshot_not_fresh'}
    if isinstance(balance, bool) or not isinstance(balance, (str, int, float, Decimal)):
        return {**result, 'reason': 'invalid_balance'}
    try:
        amount = Decimal(str(balance).strip())
    except (InvalidOperation, ValueError):
        return {**result, 'reason': 'invalid_balance'}
    if not amount.is_finite() or amount < 0:
        return {**result, 'reason': 'invalid_balance'}
    low = amount < Decimal('10')
    return {**result, 'state': 'LOW' if low else 'NORMAL', 'low': low,
            'balance_usd': amount, 'remaining_percent': amount, 'reason': ''}
