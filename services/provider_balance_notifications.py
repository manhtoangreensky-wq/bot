"""Single-monitor notification state, using the application's settings store.

The runtime must use one monitor owner; this is not a distributed DB lease.
Persist PENDING before send. Unknown outcomes require reconciliation, not retry.
"""
import json
from datetime import datetime

from services.provider_balance_alert_policy import classify_balance


async def notify_low_balance(provider, balance, *, checked_at, now, read, write, send):
    if provider not in {'key4u', 'shopaikey'}:
        return 'UNKNOWN'
    current = classify_balance(balance, checked_at=checked_at, now=now, max_age_seconds=300)
    if current['state'] == 'UNKNOWN':
        return 'UNKNOWN'
    key = 'provider_balance_notice_v1_' + provider
    try:
        state = json.loads(read(key) or '{}')
        if not isinstance(state, dict): return 'RECONCILE_REQUIRED'
    except (TypeError, ValueError):
        return 'RECONCILE_REQUIRED'
    # Never resolve uncertain delivery merely because balance recovered.
    if state.get('status') == 'PENDING':
        return 'RECONCILE_REQUIRED'
    if not current['low']:
        if state:
            write(key, '{}')
        return 'NORMAL'
    if state.get('sent_at'):
        try:
            elapsed = (now - datetime.fromisoformat(state['sent_at'])).total_seconds()
        except (ValueError, TypeError):
            return 'RECONCILE_REQUIRED'
        if elapsed < 21600:  # Existing six-hour reminder cadence.
            return 'COOLDOWN'
    write(key, json.dumps({'status': 'PENDING', 'attempted_at': now.isoformat()}))
    amount = current['balance_usd']
    message = (f'⚠️ {provider.upper()}: số dư thấp {amount:.2f} USD credit '
               f'({amount:.2f}% theo mốc 100 USD). Ngưỡng cảnh báo: dưới 10 USD. '
               'Thông báo này không tự khóa provider.')
    try:
        receipt = await send(message)
        message_id = getattr(receipt, 'message_id', None)
        if type(message_id) is not int or message_id <= 0:
            return 'RECONCILE_REQUIRED'
        write(key, json.dumps({'status': 'SENT', 'sent_at': now.isoformat(),
                              'message_id': message_id}))
    except Exception:
        return 'RECONCILE_REQUIRED'
    return 'SENT'
