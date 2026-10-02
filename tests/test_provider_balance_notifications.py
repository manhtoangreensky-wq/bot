import asyncio
import sqlite3
import pytest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from services.provider_balance_notifications import notify_low_balance

NOW = datetime(2026, 9, 22, tzinfo=timezone.utc)


def test_repeat_low_and_restart_use_durable_state():
    store, sent = {}, []
    def save(k, v): store[k] = v
    async def send(text):
        sent.append(text)
        return SimpleNamespace(message_id=17)
    async def scenario():
        for _ in range(2):
            await notify_low_balance('key4u', '9.99', checked_at=NOW, now=NOW,
                                     read=store.get, write=save, send=send)
    asyncio.run(scenario())
    assert len(sent) == 1
    assert '9.99' in sent[0]
    assert '100' in sent[0]
    assert '"sent_at"' in next(iter(store.values()))


def test_ambiguous_send_never_retries_automatically():
    store, calls = {}, []
    def save(k, v): store[k] = v
    async def send(text):
        calls.append(text)
        raise TimeoutError('unknown outcome')
    async def scenario():
        for _ in range(2):
            result = await notify_low_balance('shopaikey', '0', checked_at=NOW, now=NOW,
                                             read=store.get, write=save, send=send)
            assert result == 'RECONCILE_REQUIRED'
    asyncio.run(scenario())
    assert len(calls) == 1
    assert '"sent_at"' not in next(iter(store.values()))


def test_invalid_data_does_not_clear_pending_state_or_send():
    store = {'provider_balance_notice_v1_key4u': '{"status":"PENDING"}'}
    async def forbidden(text): raise AssertionError('must not send')
    before = dict(store)
    result = asyncio.run(notify_low_balance('key4u', None, checked_at=NOW, now=NOW,
                       read=store.get, write=lambda k,v:store.update({k:v}), send=forbidden))
    assert result == 'UNKNOWN'
    assert store == before


def test_topup_rearms_and_providers_are_independent():
    store, sent = {}, []
    async def send(text):
        sent.append(text)
        return SimpleNamespace(message_id=len(sent))
    async def tick(provider, amount, now=NOW):
        return await notify_low_balance(provider, amount, checked_at=now, now=now,
            read=store.get, write=lambda k,v:store.update({k:v}), send=send)
    async def scenario():
        assert await tick('key4u', '9') == 'SENT'
        assert await tick('shopaikey', '9') == 'SENT'
        assert await tick('key4u', '9', NOW+timedelta(hours=5)) == 'COOLDOWN'
        assert await tick('key4u', '9', NOW+timedelta(hours=6)) == 'SENT'
        assert await tick('key4u', '100', NOW+timedelta(hours=7)) == 'NORMAL'
        assert await tick('key4u', '9', NOW+timedelta(hours=8)) == 'SENT'
    asyncio.run(scenario())
    assert len(sent) == 4


def test_sqlite_restart_preserves_sent_receipt(tmp_path):
    path = str(tmp_path / 'settings.db')
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE settings (key TEXT PRIMARY KEY,value TEXT)')
    def read(key):
        with sqlite3.connect(path) as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            return row[0] if row else ''
    def write(key, value):
        with sqlite3.connect(path) as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key,value))
    sent = []
    async def send(text):
        sent.append(text)
        return SimpleNamespace(message_id=21)
    for expected in ['SENT', 'COOLDOWN']:
        # Each invocation recreates the event loop and each store access reopens SQLite.
        assert asyncio.run(notify_low_balance('key4u', '1', checked_at=NOW, now=NOW,
                          read=read, write=write, send=send)) == expected
    assert len(sent) == 1


def test_pending_write_failure_prevents_send():
    def failed_write(*args): raise sqlite3.OperationalError('disk full')
    async def forbidden(text): pytest.fail('must not send without durable state')
    with pytest.raises(sqlite3.OperationalError):
        asyncio.run(notify_low_balance('key4u', '1', checked_at=NOW, now=NOW,
                    read=lambda k: '', write=failed_write, send=forbidden))


def test_receipt_write_failure_keeps_pending_for_reconciliation():
    store, sent = {}, []
    def write(key, value):
        if 'sent_at' in value: raise sqlite3.OperationalError('disk full')
        store[key] = value
    async def send(text):
        sent.append(text)
        return SimpleNamespace(message_id=22)
    for _ in range(2):
        assert asyncio.run(notify_low_balance('key4u', '1', checked_at=NOW, now=NOW,
                          read=store.get, write=write, send=send)) == 'RECONCILE_REQUIRED'
    assert len(sent) == 1
