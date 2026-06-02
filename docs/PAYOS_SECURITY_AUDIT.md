# PAYOS SECURITY AUDIT

## Current payment packages

- `10k`: 10.000đ -> 100 Xu
- `20k`: 20.000đ -> 200 Xu
- `50k`: 50.000đ -> 500 Xu
- `100k`: 100.000đ -> 1.000 Xu
- `200k`: 200.000đ -> 2.000 Xu
- `500k`: 500.000đ -> 5.000 Xu

Launch Bonus is credited separately after PayOS success for the first purchase of eligible packages: 100k +50 Xu, 200k +150 Xu, 500k +500 Xu. The 50k package is promo-eligible but has no Launch Bonus.

## Checkout creation

- uses `PAYOS_CLIENT_ID`: Yes.
- uses `PAYOS_API_KEY`: Yes.
- uses `PAYOS_CHECKSUM_KEY`: Yes.
- stores order: Yes, via `payos_orders`.
- returns checkout URL: Yes when PayOS response code is `00`.
- fallback: if PayOS config/signature creation fails, the bot shows manual transfer QR flow.

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

## Webhook

- route: `POST /webhook/payos`.
- signature verification: Required.
- missing checksum behavior: Reject, no auto-credit.
- duplicate protection: `payos_processed`.
- amount mismatch protection: compares against internal order.
- order status protection: rejects paid/expired/cancelled/duplicate.
- user notification: sends success message when Telegram app is ready.
- admin notification: sends success summary when Telegram app is ready.

## Remaining risk

- Need real PayOS production payment test after Railway deploy.
- Need verify Railway ENV values match PayOS dashboard.
- Need confirm PayOS webhook URL points to current Railway service.
- Need watch logs for signature errors without printing secrets.
