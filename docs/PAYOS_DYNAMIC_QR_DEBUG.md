# PayOS Dynamic QR Debug

Current phase: Stable Revenue Bot only.

## Admin Test Order

Run after deploy:

```text
/providers
/payos_debug_create
/naptien
```

Then select:

- 10k: expected 100 Xu, no Launch Bonus, no promo.
- 50k: expected 500 Xu base plus 30 Xu Launch Bonus on first purchase of the 50k package.

## Expected Debug PASS

`/payos_debug_create` must return:

- `PayOS debug create PASS`
- `Description: AAS10K`
- Checkout URL exists
- `paymentLinkId` exists when PayOS returns it
- Signature data order:

```text
amount=...&cancelUrl=...&description=AAS10K&orderCode=...&returnUrl=...
```

The debug command stores its result in `system_settings` so `/sales_ready` can tell whether PayOS checkout creation has been proven.

## Expected Debug FAIL

If PayOS rejects the request, the bot must show:

- HTTP status
- PayOS code
- PayOS desc/message
- order code
- amount
- description
- signature data

The bot must not show:

- `PAYOS_API_KEY`
- `PAYOS_CHECKSUM_KEY`
- Telegram token

## Sales Ready Rule

- If `/payos_debug_create` has not produced a checkout URL: `BETA READY / NEED PAYOS DEBUG`.
- If checkout URL is created but no real payment has been marked pass: `BETA READY`.
- If checkout URL works and admin marks real payment pass: `SALES READY`.

## Manual Fallback

If PayOS creation fails during `/naptien`, the bot sends manual VietQR using the same order:

- same `order_code`
- same amount
- same calculated Xu
- transfer content: `AAS <user_id> <order_code>`
