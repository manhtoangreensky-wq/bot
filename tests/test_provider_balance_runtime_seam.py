import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
from functools import lru_cache
import subprocess
from datetime import datetime, timezone
from decimal import Decimal

import pytest


@lru_cache(maxsize=None)
def _function(name):
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'bot.py').read_text(encoding='utf-8'))
    return next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)


@pytest.mark.parametrize('shop_on,shop_key,key_on,key_key,expected', [
    (False, '', True, 'key', True), (True, 'shop', False, '', True),
    (False, '', False, 'key', False), (True, '', True, '', False)])
def test_actual_startup_condition(shop_on, shop_key, key_on, key_key, expected):
    lifespan = _function('lifespan')
    condition = next(n for n in ast.walk(lifespan) if isinstance(n, ast.If)
                     and any(isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
                             and child.func.id == 'shopaikey_usage_monitor_loop'
                             for stmt in n.body for child in ast.walk(stmt))
                     and 'SHOPAIKEY_USAGE_CHECK_ENABLED' in ast.unparse(n.test))
    scope = {'SHOPAIKEY_USAGE_CHECK_ENABLED': shop_on, 'SHOPAIKEY_API_KEY': shop_key,
             'key4u_usage_alert_enabled': lambda: key_on,
             'KEY4U_SYSTEM_API_KEY': key_key, 'KEY4U_API_KEY': ''}
    assert bool(eval(compile(ast.Expression(condition.test), 'actual-startup', 'eval'), scope)) is expected


@pytest.mark.parametrize('key_enabled', [True, False])
def test_monitor_continues_after_shopaikey_failure_and_honors_key4u_switch(key_enabled):
    calls = []
    async def sleep(seconds):
        calls.append(seconds)
        if len(calls) == 2:
            raise asyncio.CancelledError()
    tick = AsyncMock(return_value='NORMAL')
    scope = {'asyncio': SimpleNamespace(sleep=sleep, CancelledError=asyncio.CancelledError),
             'SHOPAIKEY_USAGE_CHECK_INTERVAL_MINUTES': 60,
             'SHOPAIKEY_USAGE_CHECK_ENABLED': True, 'SHOPAIKEY_API_KEY': 'fake',
             'get_shopaikey_usage': AsyncMock(side_effect=ValueError('simulated')),
             'key4u_usage_alert_enabled': lambda: key_enabled,
             'KEY4U_SYSTEM_API_KEY': 'fake-key4u', 'KEY4U_API_KEY': '',
             'provider_balance_notification_tick': tick,
             'logger': SimpleNamespace(warning=lambda *a: None)}
    exec(compile(ast.Module(body=[_function('shopaikey_usage_monitor_loop')], type_ignores=[]), 'actual-monitor', 'exec'), scope)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(scope['shopaikey_usage_monitor_loop'](object()))
    assert tick.await_count == int(key_enabled)
    if key_enabled:
        assert tick.await_args.args[1:] == ('key4u', 'fake-key4u')


def test_actual_tick_reads_persists_and_deduplicates(monkeypatch):
    from services import provider_balance_reader
    stamp = datetime.now(timezone.utc)
    reader = AsyncMock(return_value={'state': 'LOW', 'balance_usd': Decimal('9.99'), 'checked_at': stamp})
    monkeypatch.setattr(provider_balance_reader, 'read_balance', reader)
    store = {}
    def write(key, value, *args): store[key] = value
    scope = {'ADMIN_ID': 42, 'asyncio': asyncio, 'json': json,
             '_provider_balance_notification_locks': {},
             'get_system_setting': lambda key: store.get(key, ''), 'set_system_setting': write}
    exec(compile(ast.Module(body=[_function('provider_balance_notification_tick')], type_ignores=[]), 'actual-tick', 'exec'), scope)
    sender = AsyncMock(return_value=SimpleNamespace(message_id=18))
    client = SimpleNamespace(send_message=sender)
    async def scenario():
        return await asyncio.gather(*[scope['provider_balance_notification_tick'](client, 'key4u', 'fake') for _ in range(2)])
    assert asyncio.run(scenario()) == ['SENT', 'COOLDOWN']
    assert sender.await_count == 1
    assert sender.await_args.kwargs['chat_id'] == 42
    assert json.loads(store['provider_balance_notice_v1_key4u'])['message_id'] == 18


def test_only_notification_functions_and_startup_changed():
    root = Path(__file__).resolve().parents[1]
    base = subprocess.check_output(['git', 'show', '0ec38f1587fbe4f2126bf6975345de63f3da9130:bot.py'], cwd=root).decode('utf-8')
    current = (root / 'bot.py').read_text(encoding='utf-8')
    def functions(text):
        return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(text).body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    before, after = functions(base), functions(current)
    changed = {name for name in before if before[name] != after.get(name)}
    assert changed == {'maybe_alert_shopaikey_low_quota', 'shopaikey_usage_monitor_loop', 'lifespan'}
    assert set(after) - set(before) == {'provider_balance_notification_tick'}


def test_existing_shopaikey_entry_uses_fixed_balance_not_legacy_quota():
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'bot.py').read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)
                and n.name == 'maybe_alert_shopaikey_low_quota')
    delegated = AsyncMock(return_value='SENT')
    scope = {'provider_balance_notification_tick': delegated, 'SHOPAIKEY_API_KEY': 'test'}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'actual-bot-seam', 'exec'), scope)
    client = SimpleNamespace()
    result = asyncio.run(scope[node.name](client, {'balance': 0}, 'manual'))
    assert result is True
    delegated.assert_awaited_once_with(client, 'shopaikey', 'test')
