# PAYOS REAL PAYMENT TEST - TOAN AAS

Date: 2026-06-02

## Goal

Run real low-value PayOS payments before selling to customers.

This test includes two paths:

1. PayOS 10k without promo.
2. PayOS 50k or higher with public promo `FIRST30`.

`BETA50` is limited/internal only and should not be the broad public launch test.

## Preconditions

- `/health` returns `db_ok=true`.
- `/providers` shows PayOS Client ID, API Key, and Checksum as `configured`.
- `/backup_db` has been run successfully.
- `/naptien` shows all payment packages.
- `/promo_seed_policy` has seeded Promotion Policy V2.1.
- Admin is online to inspect `/dashboard`, `/pending`, and user messages.
- PayOS checkout URL can be created before sending real money.

If PayOS returns signature invalid, fix create-payment signature first. Do not run a real payment test until `/naptien` can create a checkout URL.

See `docs/PAYOS_SIGNATURE_TROUBLESHOOTING.md`.

## Test Case 1 - Create QR

1. Use a non-admin test user if possible.
2. Call `/naptien`.
3. Select package `10k`.
4. Confirm the bot creates a PayOS checkout URL/QR.
5. Confirm `payos_orders` has the order in `PENDING`.

Expected:

- Checkout URL exists.
- Order code exists.
- No Xu is added before real payment.

## Test Case 2 - Real Payment Without Promo

1. Pay the 10k QR.
2. Wait for PayOS webhook.
3. Check `/profile` as the test user.
4. Check `/dashboard` as admin.

Expected:

- Test user receives exactly 100 Xu.
- Order status becomes `PAID`.
- `payos_processed` contains the order code.
- `credit_events` contains the PayOS deposit.
- Dashboard revenue increases once.

## Test Case 3 - Real Payment With FIRST30 Promo

Admin setup:

```text
/backup_db
/providers
/promo_seed_policy
```

User flow:

```text
/promo FIRST30
/naptien
```

Then select package `50k` or higher and pay the real QR.

Expected for 50k:

- Base Xu: 500.
- FIRST30 bonus Xu: 150.
- Total Xu added: 650.
- Promo bonus is added only after payment success.
- `credit_events` contains one `payos_deposit` and one `promo_bonus`.
- `promotion_redemptions.status` becomes `applied`.

## Test Case 4 - Duplicate Protection

If a duplicate webhook/order replay can be simulated safely, or if `/checkpayos <order_code>` is run after webhook success, confirm the bot does not add Xu twice.

Expected:

- Same order code is not credited twice.
- Promo bonus is not credited twice.
- Dashboard revenue does not double count.

## Test Case 5 - Manual Fallback

1. Trigger manual flow with `/thucong` or a PayOS checkout failure.
2. User sends bill screenshot.
3. Admin approves with `/duyet`.

Expected:

- Pending bill is approved once.
- User receives the intended Xu.
- Credit event is recorded.

## Pass Criteria Before Public Sale

- [ ] Real 10k PayOS payment PASS.
- [ ] Real 50k+FIRST30 promo payment PASS.
- [ ] Duplicate protection PASS or manually reviewed.
- [ ] Dashboard revenue updates once.
- [ ] Promo bonus does not duplicate.
- [ ] Backup was taken before and after test.
- [ ] Manual fallback path is understood by admin.

## Final Admin Confirmation

After a successful real FIRST30 test, run:

```text
/mark_payos_test pass order=<order_code> note="Test FIRST30 OK, base+bonus credited once"
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
