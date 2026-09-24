"""Official read-only balance endpoints; never return keys or raw responses.

Credentials are supplied by the existing runtime, not read or changed here.
No imports from bot, billing, producers, database or provider freeze logic.
"""
from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
import re

import httpx

from services.provider_balance_alert_policy import classify_balance


class _UsageURLRedactor(logging.Filter):
    """Redact only the official usage URL's credential; preserve other logs."""
    _pattern = re.compile(r'(https://api\.shopaikey\.com/usage\?[^\s\"\']*?\bapiKey=)[^&\s\"\']+', re.I)

    def filter(self, record):
        message = record.getMessage()
        sanitized = self._pattern.sub(r'\1[REDACTED]', message)
        if sanitized != message:
            record.msg, record.args = sanitized, ()
        return True


def _protect_usage_request_logs():
    logger = logging.getLogger('httpx')
    if not any(isinstance(item, _UsageURLRedactor) for item in logger.filters):
        logger.addFilter(_UsageURLRedactor())


async def read_balance(provider: str, credential: str, *, transport=None,
                       clock=lambda: datetime.now(timezone.utc)) -> dict:
    """One GET attempt with redirects disabled. HTTPX handles gzip decoding.

    Returned freshness timestamp records this successful read, not a cached value.
    Callers must preserve it and enforce freshness again before delayed sending.
    """
    unknown = {'provider': provider if provider in {'key4u', 'shopaikey'} else 'unsupported',
               'state': 'UNKNOWN', 'low': False, 'balance_usd': None,
               'remaining_percent': None, 'baseline_usd': Decimal('100'),
               'checked_at': None}
    if provider not in {'key4u', 'shopaikey'}:
        return {**unknown, 'reason': 'unsupported_provider'}
    if not isinstance(credential, str) or not credential.strip():
        return {**unknown, 'reason': 'missing_credential'}
    credential = credential.strip()
    _protect_usage_request_logs()
    if provider == 'key4u':
        url = 'https://api.key4u.vn/v1/balance'
        token = credential if credential.lower().startswith('bearer ') else 'Bearer ' + credential
        headers, params = {'Authorization': token}, None
    else:
        url = 'https://api.shopaikey.com/usage'
        headers, params = {}, {'apiKey': credential}
    try:
        async with httpx.AsyncClient(transport=transport, timeout=20, follow_redirects=False) as client:
            response = await client.get(url, headers=headers, params=params)
        if response.status_code != 200:
            return {**unknown, 'reason': 'http_error', 'http_status': response.status_code}
        if len(response.content) > 65536:
            return {**unknown, 'reason': 'response_too_large'}
        data = json.loads(response.content, parse_float=Decimal)
        if not isinstance(data, dict):
            return {**unknown, 'reason': 'invalid_schema'}
        # Use balance when present; malformed balance is not silently replaced.
        amount = data.get('balance')
        if 'balance' not in data and provider == 'shopaikey':
            amount = data.get('remaining')
        checked = clock()
        result = classify_balance(amount, checked_at=checked, now=checked, max_age_seconds=1)
        return {**unknown, **result, 'checked_at': checked if result['state'] != 'UNKNOWN' else None}
    except (httpx.HTTPError, ValueError, UnicodeError):
        # HTTP errors can embed the ShopAIKey query credential. Do not log them.
        return {**unknown, 'reason': 'read_failed'}
