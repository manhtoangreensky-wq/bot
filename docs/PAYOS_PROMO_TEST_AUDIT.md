# PayOS Promo Test Audit - Promotion Policy V2.1

Date: 2026-06-02

## Current Promo Policy

- Public first top-up: `FIRST30`, +30% Xu.
- Second top-up: `SECOND15`, +15% Xu.
- Weekly: `WEEKLY10`, +10% Xu.
- Monthly/large package: `MONTHLY20`, +20% Xu.
- Daily: `DAILY5`, +5% Xu.
- Limited/internal: `BETA50`, +50% Xu, not broad public offer.

## Real Payment Test

Use a non-admin test user:

```text
/promo_seed_policy
/promo FIRST30
/naptien
```

Choose 20k or higher and pay the real PayOS QR.

Expected for 20k:

- Base Xu: 200.
- Promo bonus: 60.
- Total credit: 260 Xu.
- Duplicate webhook or `/checkpayos` replay does not add base or bonus again.

## Safety

- PayOS VND amount is unchanged.
- `PAYMENT_PACKAGES` is unchanged.
- Bonus is applied only inside PayOS success processing.
- One order uses one promo only.
