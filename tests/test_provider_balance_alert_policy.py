from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from services.provider_balance_alert_policy import classify_balance

NOW = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize('amount,low', [('100', False), ('10', False),
    ('9.99', True), ('9.999', True), ('0', True), ('150', False)])
def test_fixed_baseline_and_strict_unrounded_threshold(amount, low):
    result = classify_balance(amount, checked_at=NOW, now=NOW, max_age_seconds=300)
    assert result['low'] is low
    assert result['remaining_percent'] == Decimal(amount)
    assert result['baseline_usd'] == Decimal('100')


@pytest.mark.parametrize('amount', [None, '', 'bad', 'NaN', 'Infinity', '-1', True, {}, []])
def test_invalid_balance_is_unknown_not_zero(amount):
    result = classify_balance(amount, checked_at=NOW, now=NOW, max_age_seconds=300)
    assert result['state'] == 'UNKNOWN'
    assert result['low'] is False
    assert result['balance_usd'] is None


@pytest.mark.parametrize('checked', [None, NOW.replace(tzinfo=None),
    NOW - timedelta(seconds=301), NOW + timedelta(seconds=1)])
def test_untrusted_timestamp_cannot_trigger_low_alert(checked):
    result = classify_balance('0', checked_at=checked, now=NOW, max_age_seconds=300)
    assert result['state'] == 'UNKNOWN'
    assert result['low'] is False


def test_boundary_freshness_and_failed_fetch():
    assert classify_balance('0', checked_at=NOW-timedelta(seconds=300), now=NOW,
                            max_age_seconds=300)['low'] is True
    assert classify_balance('0', checked_at=NOW, now=NOW, max_age_seconds=300,
                            fetch_ok=False)['state'] == 'UNKNOWN'
