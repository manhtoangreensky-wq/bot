# PayOS Promo Test Audit - TOAN AAS

Date: 2026-06-02

## Scope

Audit and prepare the bot for a real PayOS 10k payment test with the beta promo code `BETA50`.

## Compile

- `python -m py_compile bot.py`: PASS locally with Codex bundled Python.
- `pytest -q`: PASS locally, 15 tests, 1 Starlette/httpx deprecation warning.

## PayOS Findings

- `PAYMENT_PACKAGES` remains unchanged.
- PayOS package callbacks still use `pkg|`.
- Provider callbacks still use `prov|`.
- `/webhook/payos` still verifies PayOS checksum before crediting.
- Paid orders still go through `process_payos_paid_order()`.
- Duplicate protection still uses both `payos_orders.status=PAID` and `payos_processed`.
- `/sales_ready` only returns `SALES READY` after admin records `payos_real_payment_test_status=PASS`.

## Promo MVP

- Admin command: `/promo_seed_beta`.
- User command: `/promo <code>`.
- Seeded beta codes:
  - `BETA50`: minimum 10k PayOS payment, one-time +50 Xu.
  - `BETA30`: minimum 10k PayOS payment, one-time +30 Xu.
- Promo activation creates a pending redemption for that user/code.
- Promo bonus is applied inside the same DB transaction as PayOS paid order credit.
- The same code cannot be applied twice to the same user.
- Replay of the same paid order returns `already_paid` and does not add base Xu or promo Xu again.

## Expected Real Test

For a user who has activated `BETA50`:

- Package: `10k`
- Base Xu: `100`
- Promo Xu: `50`
- Total expected credit: `150 Xu`

## Not Done By Codex

- No real payment was performed locally.
- No PayOS secret was inspected.
- No PayOS package amount was changed.
- No production DB was edited manually.

## Required Admin Confirmation

Only after a real 10k + BETA50 test passes, run:

```text
/mark_payos_test pass order=<order_code> note="Test 10k+BETA50 OK, user received 150 Xu"
```
