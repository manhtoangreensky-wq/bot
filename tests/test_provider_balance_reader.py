import asyncio
import gzip
import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest

from services.provider_balance_reader import read_balance

NOW = datetime(2026, 9, 21, tzinfo=timezone.utc)


@pytest.mark.parametrize('provider', ['key4u', 'shopaikey'])
def test_official_request_and_sanitized_result(provider):
    seen = []
    def endpoint(request):
        seen.append(request)
        assert request.method == 'GET'
        if provider == 'key4u':
            assert str(request.url) == 'https://api.key4u.vn/v1/balance'
            assert request.headers['Authorization'] == 'Bearer test-only-secret'
        else:
            assert request.url.host == 'api.shopaikey.com'
            assert request.url.path == '/usage'
            assert request.url.params['apiKey'] == 'test-only-secret'
        return httpx.Response(200, json={'balance': '9.99', 'key': 'must-not-return', 'used': 321})
    result = asyncio.run(read_balance(provider, 'test-only-secret', transport=httpx.MockTransport(endpoint), clock=lambda: NOW))
    assert len(seen) == 1
    assert result['balance_usd'] == Decimal('9.99')
    assert result['low'] is True
    assert result['checked_at'] == NOW
    assert 'secret' not in repr(result) and 'must-not-return' not in repr(result)


@pytest.mark.parametrize('status,payload', [(401, {}), (429, {}), (500, {}),
    (200, {'used': 1}), (200, {'balance': 'bad'}), (200, []),
    (200, {'balance': None, 'remaining': 0})])
def test_failed_or_invalid_balance_never_alerts(status, payload):
    transport = httpx.MockTransport(lambda req: httpx.Response(status, json=payload))
    result = asyncio.run(read_balance('key4u', 'test', transport=transport, clock=lambda: NOW))
    assert result['state'] == 'UNKNOWN'
    assert result['low'] is False
    assert result['balance_usd'] is None


def test_redirect_does_not_forward_secret():
    calls = []
    def endpoint(req):
        calls.append(req)
        return httpx.Response(302, headers={'Location': 'https://other.invalid/steal'})
    result = asyncio.run(read_balance('shopaikey', 'test', transport=httpx.MockTransport(endpoint), clock=lambda: NOW))
    assert len(calls) == 1
    assert result['state'] == 'UNKNOWN'


def test_missing_credentials_and_unknown_provider_do_not_send():
    def forbidden(req):
        pytest.fail('request must not run')
    for provider, key in [('key4u', ''), ('unknown', 'test')]:
        result = asyncio.run(read_balance(provider, key, transport=httpx.MockTransport(forbidden), clock=lambda: NOW))
        assert result['state'] == 'UNKNOWN'


def test_unknown_json_and_transport_failure_hide_raw_error():
    def endpoint(req):
        raise httpx.ReadTimeout('sensitive URL/key must not escape')
    result = asyncio.run(read_balance('shopaikey', 'test', transport=httpx.MockTransport(endpoint), clock=lambda: NOW))
    assert result['reason'] == 'read_failed'
    assert 'sensitive' not in repr(result)


def test_real_gzip_shape_is_decoded_without_returning_key():
    body = gzip.compress(b'{"balance":24.18613397221324,"key":"private"}')
    transport = httpx.MockTransport(lambda req: httpx.Response(
        200, content=body, headers={'Content-Encoding': 'gzip', 'Content-Type': 'application/json'}))
    result = asyncio.run(read_balance('key4u', 'test', transport=transport, clock=lambda: NOW))
    assert result['balance_usd'] == Decimal('24.18613397221324')
    assert result['low'] is False
    assert 'private' not in repr(result)


def test_invalid_json_is_unknown():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b'not-json'))
    result = asyncio.run(read_balance('key4u', 'test', transport=transport, clock=lambda: NOW))
    assert result['state'] == 'UNKNOWN'
    assert result['reason'] == 'read_failed'


def test_http_client_logging_never_exposes_query_key(caplog):
    caplog.set_level(logging.INFO, logger='httpx')
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={'balance': 20}))
    asyncio.run(read_balance('shopaikey', 'sentinel-secret-123', transport=transport, clock=lambda: NOW))
    assert 'sentinel-secret-123' not in caplog.text
