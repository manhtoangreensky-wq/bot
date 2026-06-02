# PAYOS REAL PAYMENT TEST - TOAN AAS

Date: 2026-06-02

## Goal

Run one real low-value PayOS payment before selling to customers.

This test now includes two paths:

1. PayOS 10k without promo.
2. PayOS 10k with BETA50 promo.

## Preconditions

- `/health` returns `db_ok=true`.
- `/providers` shows PayOS Client ID, API Key, and Checksum as `configured`.
- `/backup_db` has been run successfully.
- `/naptien` shows all payment packages.
- `/promo_seed_beta` or `/promo_create` can create BETA50.
- Admin is online to inspect `/dashboard`, `/pending`, `/promo_list`, and user messages.

## Test case 1 - Create QR

1. Use a non-admin test user if possible.
2. Call `/naptien`.
3. Select package `10k`.
4. Confirm the bot creates a PayOS checkout URL/QR.
5. Confirm `payos_orders` has the order in `PENDING`.

Expected:

- Checkout URL exists.
- Order code exists.
- No Xu is added before real payment.

## Test case 2 - Real payment without promo

1. Pay the 10k QR.
2. Wait for PayOS webhook.
3. Check `/profile` as the test user.
4. Check `/dashboard` as admin.

Expected:

- Test user receives exactly 100 Xu.
- Order status becomes `PAID`.
- `payos_processed` or the equivalent idempotency guard contains the order code.
- `credit_events` or equivalent audit log contains the PayOS deposit.
- Dashboard revenue increases once.

## Test case 3 - Real payment with BETA50 promo

Admin setup:

```text
/backup_db
/providers
/promo_seed_beta
/promo_list
```

User flow:

```text
/promo BETA50
/naptien
```

Then select package `10k` and pay the real QR.

Expected:

- Base Xu: 100.
- BETA50 bonus Xu: 50.
- Total Xu added: 150.
- Promo bonus is added only after payment success.
- Promo bonus is auditable separately from the base deposit when possible.
- Promo usage count increases once.

## Test case 4 - Duplicate protection

If a duplicate webhook/order replay can be simulated safely, or if `/checkpayos <order_code>` is run after webhook success, confirm the bot does not add Xu twice.

Expected:

- Same order code is not credited twice.
- Promo bonus is not credited twice.
- Dashboard revenue does not double count.

## Test case 5 - Manual fallback

1. Trigger manual flow with `/thucong` or a PayOS checkout failure.
2. User sends bill screenshot.
3. Admin approves with `/duyet`.

Expected:

- Pending bill is approved once.
- User receives the intended Xu.
- Credit event is recorded.

## Test case 6 - Missing checksum audit

Do not run this on production while selling. Code expectation:

- Missing checksum rejects automatic webhook credit.
- Manual fallback remains available.

## Pass criteria before public sale

- [ ] Real 10k PayOS payment PASS.
- [ ] Real 10k + BETA50 promo payment PASS.
- [ ] Duplicate protection PASS or manually reviewed.
- [ ] Dashboard revenue updates once.
- [ ] Promo bonus does not duplicate.
- [ ] Backup was taken before and after test.
- [ ] Manual fallback path is understood by admin.

## Final admin confirmation

After a successful real 10k + BETA50 test, run:

```text
/mark_payos_test pass order=<order_code> note="10k + BETA50 OK"
```

If the test fails, run:

```text
/mark_payos_test fail note="Webhook or promo bonus failed"
```

Reset status if needed:

```text
/mark_payos_test reset
```

Then run `/sales_ready` again.
