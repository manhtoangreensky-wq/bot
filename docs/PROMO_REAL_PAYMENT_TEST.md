# Promo Real Payment Test - Policy V2.1

Date: 2026-06-02

## Goal

Confirm that a real PayOS payment credits the normal package Xu plus exactly one promo bonus without duplicate credit.

## Setup

1. Admin runs:

```text
/promo_seed_policy
```

`/promo_seed_beta` is kept as a compatibility alias.

2. Use a non-admin test Telegram account.
3. Test user runs:

```text
/promo FIRST30
```

Expected:

- Bot confirms the code is saved.
- No Xu is added yet.
- Promo waits for a valid PayOS payment.

## Payment Test

1. Test user runs `/naptien`.
2. Test user selects package `50k` or higher.
3. Test user pays the PayOS QR.
4. Wait for webhook or use `/checkpayos <order_code>`.
5. Test user runs `/profile`.

Expected for 50k + FIRST30:

- 50k package adds 500 Xu.
- Launch Bonus adds 30 Xu if this is the user's first 50k package purchase.
- FIRST30 adds 150 Xu.
- Total new credit from this payment is 680 Xu for a first 50k package purchase; 650 Xu if Launch Bonus was already used for 50k.
- `credit_events` has one `payos_deposit`, one `launch_bonus` if eligible, and one `promo_bonus`.
- `promotion_redemptions.status` becomes `applied`.

## Duplicate Test

If safe to simulate replay:

- Replay the same PayOS order/webhook or run `/checkpayos <order_code>` after webhook success.
- Expected result: no new base Xu and no new promo Xu.
- `process_payos_paid_order()` should return `already_paid` or duplicate/ignored state.

## BETA50 Note

`BETA50` is limited/internal only and requires a larger package. Do not promote it broadly as the public launch offer.
