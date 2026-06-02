# PAYOS + PROMO TEST AUDIT

## Compile

- py_compile: pending manual/local run. GitHub connector cannot execute code.

## PayOS config

| ENV | Status shown only configured/missing | Notes |
|---|---|---|
| PAYOS_CLIENT_ID | required | Must be checked with `/providers`. |
| PAYOS_API_KEY | required | Must be checked with `/providers`. |
| PAYOS_CHECKSUM_KEY | required | Must be checked with `/providers`; never print the key. |

## Payment flow

| Step | Function/Table | Status |
|---|---|---|
| User starts deposit | `/naptien` and `pkg\|` callback | Must create order only, no Xu before payment. |
| Order persistence | `payos_orders` | Must store order_code, amount, base_xu, user_id. |
| Success confirmation | PayOS webhook or `/checkpayos` | Must verify payment status before adding Xu. |
| Idempotency | `payos_processed` / processed-order guard | Must prevent duplicate credit. |
| Credit event | `credit_events` | Must record deposit and promo bonus separately if applicable. |

## Webhook safety

| Check | Exists? | Notes |
|---|---|---|
| Checksum verification | manual/code verification required | Do not bypass checksum for production. |
| Idempotency | manual/code verification required | Same order_code must not add Xu twice. |
| Duplicate prevention | manual/code verification required | Includes promo bonus duplicate prevention. |
| Credit event | required | Base deposit and promo bonus should be auditable. |

## Promo flow

| Step | Table/Function | Status |
|---|---|---|
| Pending promo | `user_promo_state` or equivalent | User runs `/promo BETA50` before `/naptien`. |
| Promo code | `promo_codes` | `BETA50` should be active, percent_bonus 50, min 10000. |
| Redemption | `promo_redemptions` | Pending at order creation, redeemed only after payment success. |
| Bonus calculation | helper | 10k package = 100 base Xu; BETA50 = 50 bonus Xu. |
| Duplicate prevention | order_code + redemption status | Bonus must not be added twice. |

## Blockers before real test

1. `/providers` must show PayOS configured.
2. `/backup_db` must run before payment test.
3. `BETA50` must exist and be active.
4. Real payment test should use a non-admin test user when possible.
5. Admin must confirm PASS only after checking base Xu + bonus Xu + duplicate safety.
