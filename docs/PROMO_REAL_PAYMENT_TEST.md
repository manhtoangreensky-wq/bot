# Promo Real Payment Test - BETA50

Date: 2026-06-02

## Goal

Confirm that a real PayOS payment can credit the normal package Xu plus one promo bonus without duplicate credit.

## Setup

1. Admin runs:

```text
/promo_seed_beta
```

2. Use a non-admin test Telegram account.
3. Test user runs:

```text
/promo BETA50
```

Expected:

- Bot confirms the code is activated.
- No Xu is added yet.
- Promo waits for a valid PayOS payment.

## Payment Test

1. Test user runs `/naptien`.
2. Test user selects package `10k`.
3. Test user pays the PayOS QR.
4. Wait for webhook.
5. Test user runs `/profile`.

Expected:

- 10k package adds 100 Xu.
- `BETA50` adds 50 Xu.
- Total new credit from this payment is 150 Xu.
- `credit_events` has one `payos_deposit` and one `promo_bonus`.
- `promotion_redemptions.status` becomes `applied`.

## Duplicate Test

If safe to simulate replay:

- Replay the same PayOS order/webhook or run `/checkpayos <order_code>` after webhook success.
- Expected result: no new 100 Xu and no new 50 Xu.
- `process_payos_paid_order()` should return `already_paid` or duplicate/ignored state.

## Failure Conditions

- User receives more than 150 Xu from one 10k+BETA50 payment.
- User can apply `BETA50` twice.
- `/sales_ready` shows `SALES READY` before admin marks the real test PASS.
