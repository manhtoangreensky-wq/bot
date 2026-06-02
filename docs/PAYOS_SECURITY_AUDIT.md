# PayOS Security Audit

## PAYOS_CHECKSUM_KEY required

Required for auto-credit webhook.

Nếu `PAYOS_CHECKSUM_KEY` thiếu, `/webhook/payos` reject request và không cộng xu tự động.

## Signature verification

Function: `verify_payos_signature(data, received_sig)`.

- Uses sorted keys.
- Uses HMAC SHA256 with `PAYOS_CHECKSUM_KEY`.
- Uses `hmac.compare_digest`.
- Returns `False` when checksum key is missing.

## Duplicate protection

Function: `process_payos_paid_order`.

- Uses `BEGIN IMMEDIATE`.
- Checks `payos_processed`.
- Inserts order code into `payos_processed` inside transaction.
- Rejects already paid/duplicate order.

## Amount mismatch protection

- Reads internal `payos_orders.amount`.
- Compares webhook amount against expected amount.
- Does not credit on mismatch.

## Expired order protection

- Rejects `EXPIRED` and `CANCELLED`.
- If pending order has expired timestamp, updates status to `EXPIRED` and does not credit.

## Manual fallback

- `/thucong` creates manual payment flow.
- `/duyet` approves manual bill.
- `/tuchoi` rejects manual bill.
- These are admin-only commands.

## Remaining risk

- Need real PayOS production payment test after Railway deploy.
- Need verify Railway ENV values match PayOS dashboard.
- Need confirm PayOS webhook URL points to current Railway service.
- Need watch logs for signature errors without printing secrets.

