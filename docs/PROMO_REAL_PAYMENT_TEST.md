# Promo Real Payment Test — TOAN AAS

## Goal

Verify that a real PayOS payment with a promotion code adds the correct base Xu and bonus Xu without duplicate credit.

## BETA50 Expected Calculation

Payment package:

- 10k = 100 Xu

Promo:

- BETA50 = +50% Xu bonus

Expected result:

- Base Xu: 100
- Bonus Xu: 50
- Total Xu added: 150

## Important Rules

- Promo changes only the Xu credited to the user, not the VND amount paid through PayOS.
- Promo bonus is added only after payment success.
- Promo bonus must be idempotent; duplicate webhook or duplicate `/checkpayos` must not add the bonus again.
- Promo is per-user limited according to the promo configuration.
- Promo usage_count must increase only after successful redemption.
- Never bypass PayOS checksum validation.

## Admin Setup

Run these commands as admin before the test:

```text
/backup_db
/providers
/promo_seed_beta
/promo_list
```

Expected:

- PayOS Client/API/Checksum are configured.
- BETA50 exists and is active.
- BETA50 is percent_bonus 50.
- BETA50 min amount is at least 10k or lower.

## User Test Flow

Use a non-admin test user when possible:

```text
/promo BETA50
/naptien
```

Then choose the 10k package and pay the real QR.

Expected before payment:

- Order is created as pending.
- User does not receive Xu yet.
- Promo is pending for that order if the integration attaches promo to the order.

Expected after payment:

- User receives 100 base Xu.
- User receives 50 promo bonus Xu.
- Total increase for this payment is 150 Xu.
- Deposit and promo bonus are auditable in credit events or equivalent logs.

## Admin Verification

After the payment:

```text
/profile
/dashboard
/checkpayos <order_code>
/sales_ready
```

If all checks pass:

```text
/mark_payos_test pass order=<order_code> note="10k + BETA50 OK"
```

If the test fails:

```text
/mark_payos_test fail note="Describe the issue clearly"
```

## Duplicate Safety Check

If safe to do so, trigger the order check again:

```text
/checkpayos <order_code>
```

Expected:

- Base Xu is not added again.
- Promo bonus is not added again.
- Revenue dashboard is not double counted.

## Pass Criteria

- [ ] QR checkout URL created.
- [ ] User paid exactly 10k.
- [ ] Base Xu +100 credited once.
- [ ] BETA50 bonus +50 credited once.
- [ ] Duplicate check does not double credit.
- [ ] Admin marked PayOS test PASS.
- [ ] `/sales_ready` shows SALES READY or the remaining blocker clearly.
