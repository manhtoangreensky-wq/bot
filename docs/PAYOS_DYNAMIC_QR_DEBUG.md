# PayOS Dynamic QR Debug

## Current Issue

Bot falls back to manual QR when PayOS create payment link fails.

## Required Debug

Use admin-only command:

```text
/payos_debug_create
```

The command reports:

- HTTP status
- PayOS code
- PayOS desc/message
- Signature data
- orderCode
- amount
- description
- returnUrl/cancelUrl

## Do Not Expose

- `PAYOS_API_KEY`
- `PAYOS_CHECKSUM_KEY`
- `TELEGRAM_TOKEN`

## Signature Data

The create-payment signature string must use this exact order:

```text
amount=<amount>&cancelUrl=<cancelUrl>&description=<description>&orderCode=<orderCode>&returnUrl=<returnUrl>
```

Do not URL-encode values before signing.

## Payment Content

Use `AAS`, not `DAAS`.

Manual transfer content:

```text
AAS <user_id> <order_code>
```

PayOS description examples:

```text
AAS10K
AAS50K
```

## Manual Fallback

Manual fallback must use the same `order_code`, `amount`, and order `xu` preview as the PayOS order. If a 50k first package order is eligible for Launch Bonus, the fallback text must show `530 Xu`.
