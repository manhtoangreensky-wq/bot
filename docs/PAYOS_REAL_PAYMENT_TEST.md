# PAYOS REAL PAYMENT TEST - TOAN AAS

Date: 2026-06-02

## Goal

Run one real low-value PayOS payment before selling to customers.

## Preconditions

- `/health` returns `db_ok=true`.
- `/providers` shows PayOS Client ID, API Key, and Checksum as `configured`.
- `/backup_db` has been run successfully.
- `/naptien` shows all payment packages.
- Admin is online to inspect `/dashboard`, `/pending`, and user messages.

## Test case 1 - Create QR

1. Use a non-admin test user.
2. Call `/naptien`.
3. Select package `10k`.
4. Confirm the bot creates a PayOS checkout URL/QR.
5. Confirm `payos_orders` has the order in `PENDING`.

Expected:

- Checkout URL exists.
- Order code exists.
- No Xu is added before real payment.

## Test case 2 - Real payment

1. Pay the 10k QR.
2. Wait for PayOS webhook.
3. Check `/profile` as the test user.
4. Check `/dashboard` as admin.

Expected:

- Test user receives exactly 100 Xu.
- Order status becomes `PAID`.
- `payos_processed` contains the order code.
- `credit_events` contains the PayOS deposit.
- Dashboard revenue increases.

## Test case 3 - Duplicate protection

If a duplicate webhook/order replay can be simulated safely, confirm the bot does not add Xu twice.

Expected:

- Same order code is not credited twice.
- Dashboard revenue does not double count.

## Test case 4 - Manual fallback

1. Trigger manual flow with `/thucong` or a PayOS checkout failure.
2. User sends bill screenshot.
3. Admin approves with `/duyet`.

Expected:

- Pending bill is approved once.
- User receives the intended Xu.
- Credit event is recorded.

## Test case 5 - Missing checksum audit

Do not run this on production while selling. Code expectation:

- Missing checksum rejects automatic webhook credit.
- Manual fallback remains available.

## Pass criteria before public sale

- [ ] Real 10k PayOS payment PASS.
- [ ] Duplicate protection PASS or manually reviewed.
- [ ] Dashboard revenue updates.
- [ ] Backup was taken before and after test.
- [ ] Manual fallback path is understood by admin.
