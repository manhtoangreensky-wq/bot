# P0.17C1 PayOS Signature Status Gate And Idempotency

Patch date: 2026-06-27

Repository: `manhtoangreensky-wq/bot`

Branch: `hotfix/p0-17c1-payos-signature-idempotency`

Base: latest `main` after P0.17C0 audit merge, expected `ab76b7c` or newer.

Scope: critical PayOS webhook safety only. This patch does not change PayOS pricing ratio, package prices, top-up order creation, manual top-up UX, wallet debit logic, video, voice/TTS, subtitle/dubbing, music/Suno, image/image-to-video, web/app/standalone, or destructive DB migrations.

## C0 Report Read

Source: `docs/reports/P0_17C0_PAYOS_SECURITY_AUDIT_ONLY.md`

C0 finding carried forward:

- PayOS webhook verified signed `data`, but accepted payable handling when unsigned outer `body.success` was true even if signed `data.status` was not explicitly `PAID`.
- Idempotency existed by internal `order_code` and paid order state, but transaction id and paymentLinkId were not persistently reserved as independent idempotency keys.
- C0 proposed this branch: `hotfix/p0-17c1-payos-signature-idempotency`.

## Current Webhook Surface

Webhook endpoint:

- `POST /api/v1/billing/webhook/payos`
- `POST /webhook/payos`

Handler:

- `bot.py:144237`: `webhook_payos`

Current signature verification helper:

- `bot.py:144223`: `verify_payos_signature(data, received_sig)`
- Secret source: `PAYOS_CHECKSUM_KEY`
- Signature input remains the signed PayOS `data` object sorted by key.

Signature extraction:

- `bot.py:144192`: `extract_payos_webhook_signature`
- Accepts the current body field `signature`, compatibility body field `checksum`, and safe header fallbacks.

Credit Xu function:

- `bot.py:28515`: `process_payos_paid_order`

Order lookup:

- `process_payos_paid_order` selects the internal row from `payos_orders` by `order_code`.
- Amount, status, expiry, payment link, currency, and idempotency checks occur before the existing credit/grant branches.

Duplicate protection:

- Legacy: `payos_processed` by `order_code`.
- New: `payos_processed_events` with persistent event key plus stored `order_code`, `payment_link_id`, `transaction_id`, `user_id`, `amount`, `status`, `credited`, `created_at`, and `raw_hash`.

## Old Risk

The old webhook gate performed signature verification before processing, but the paid decision was:

```text
body.success OR data.status == "PAID"
```

Because `body.success` is outside the signed `data` object, a valid signed non-PAID `data` payload could be paired with an unsigned `success=true` field and reach `process_payos_paid_order`. Amount and order checks still existed, but money credit should never depend on unsigned status-like fields.

The old idempotency protection was strong for one internal order, but did not persist provider transaction id or paymentLinkId as separate replay/conflict keys. That left weaker forensics and weaker defense against the same transaction/payment link being reused against a different order.

## Patch Summary

Signature gate:

- Reads the raw request body safely and hashes it for internal event storage.
- Requires `PAYOS_CHECKSUM_KEY`.
- Rejects missing signature with no credit.
- Rejects invalid signature with no credit.
- Does not trust `orderCode`, amount, or status for crediting before signature passes.
- Records internal security events without exposing checksum/secret details.

Status gate:

- Requires signed `data.status == PAYOS_STATUS_PAID`.
- Ignores unsigned outer `success` for credit decisions.
- Returns safe `status_not_paid` for pending, cancelled, failed, unknown, or missing status.
- Rejects invalid amount, amount mismatch, order not found, expired/cancelled internal order, and currency mismatch with no credit.

Idempotency:

- Adds non-destructive table `payos_processed_events`.
- Reserves a persistent idempotency event inside the same DB transaction before credit/grant logic.
- Strongest event key order:
  - transaction id when present
  - paymentLinkId when present
  - orderCode fallback
- Rejects duplicate or conflicting credited events by order, transaction id, or paymentLinkId.
- Marks the idempotency event `credited=1` only after the existing successful credit/grant branch writes `payos_processed`.

Credit path:

- Existing package, plan, storage add-on, and Xu top-up success branches remain the only apply branches.
- No credit/grant branch runs before:
  - valid signature
  - signed paid status
  - internal order lookup
  - amount match
  - currency match when webhook currency is present
  - paymentLinkId match when both internal and webhook values exist
  - persistent idempotency reserve

## Files Changed

- `bot.py`
- `tests/test_p0_17c1_payos_signature_idempotency.py`
- `docs/reports/P0_17C1_PAYOS_SIGNATURE_IDEMPOTENCY.md`

No other production modules are intentionally changed.

## Tests Added

- `test_payos_webhook_rejects_missing_signature`
- `test_payos_webhook_rejects_invalid_signature`
- `test_payos_webhook_credits_only_after_valid_signature`
- `test_payos_webhook_duplicate_does_not_credit_twice`
- `test_payos_webhook_invalid_amount_does_not_credit`
- `test_payos_webhook_currency_mismatch_does_not_credit`
- `test_payos_webhook_pending_or_cancelled_does_not_credit`
- `test_payos_webhook_no_fake_success`
- `test_payos_webhook_order_not_found_does_not_credit`
- `test_payos_webhook_same_transaction_different_order_is_rejected`
- `test_payos_webhook_duplicate_payment_link_does_not_credit_twice`
- `test_p0_17c1_static_guard_no_unrelated_files_touched`

## Not Touched

- Top-up limits, cooldowns, rolling limits: not touched.
- Manual top-up approval UX: not touched.
- Admin lock/block/risk report: not touched.
- PayOS ratio/pricing/package prices: not touched.
- Wallet debit logic: not touched.
- Video, voice/TTS, subtitle/dubbing, music/Suno, image/image-to-video: not touched.
- Web/app/standalone: not touched.
- Destructive DB migration: not touched.
- Deploy: not done.
- LIVE PASS: not claimed.
