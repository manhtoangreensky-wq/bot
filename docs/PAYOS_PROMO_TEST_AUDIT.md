# PayOS Promo Test Audit - Promotion Policy V2.1

Date: 2026-06-02

## Current Promo Policy

- Public first top-up: `FIRST30`, +30% Xu.
- Second top-up: `SECOND15`, +15% Xu.
- Weekly: `WEEKLY10`, +10% Xu.
- Monthly/large package: `MONTHLY20`, +20% Xu.
- Daily: `DAILY5`, +5% Xu.
- Limited/internal: `BETA50`, +50% Xu, not broad public offer.
- Public promo minimum top-up starts at 50k; 10k/20k are trial packages.

## Real Payment Test

Use a non-admin test user:

```text
/promo_seed_policy
/promo FIRST30
/naptien
```

Choose 50k or higher and pay the real PayOS QR.

Expected for 50k:

- Base Xu: 500.
- Launch Bonus: 30 if this is the user's first 50k package purchase.
- Promo bonus: 150.
- Total credit: 680 Xu.
- Duplicate webhook or `/checkpayos` replay does not add base or bonus again.

## Safety

- PayOS VND amount is unchanged.
- PayOS VND amounts are unchanged.
- Bonus is applied only inside PayOS success processing.
- One order uses one promo only.
