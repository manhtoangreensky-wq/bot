# Promotion Policy V2.1 - TOAN AAS

## Philosophy

TOAN AAS keeps base top-up packages stable. Promotions are expressed as extra Xu so customers can use more service after payment.

## Rules

- One order can use only one promo code.
- Promo codes do not stack.
- A new pending promo replaces the old pending promo.
- Bonus Xu is credited only after PayOS payment success.
- Duplicate webhook or `/checkpayos` replay must not add promo bonus twice.
- Public promotion codes start from 50.000đ top-up.
- 10k and 20k packages are trial/test packages and do not receive public promo bonus.

## Rule: Minimum top-up for promo

All public promotion codes start from 50.000đ top-up.

Reason:

- 10k/20k packages are trial/test packages.
- Promo should encourage users to start from 50k.
- 50k package becomes the first serious usage package.
- This avoids many tiny low-value promo deposits.

## Main Public Offers

| Code | Bonus | Minimum top-up | Purpose |
|---|---:|---:|---|
| FIRST30 | +30% Xu | 50k | First top-up |
| SECOND15 | +15% Xu | 50k | Second top-up |
| WEEKLY10 | +10% Xu | 50k | Weekly offer |
| DAILY5 | +5% Xu | 50k | Daily offer |
| MONTHLY20 | +20% Xu | 100k | Monthly/larger package |

## Limited/Internal

| Code | Bonus | Minimum top-up | Usage |
|---|---:|---:|---|
| BETA50 | +50% Xu | 50k | Beta/internal limited only, not broad public campaign |

## Recommended Use Order

1. FIRST30
2. SECOND15
3. MONTHLY20
4. WEEKLY10
5. DAILY5

## Customer-Facing Wording

"Ưu đãi bắt đầu từ gói 50k. Gói 10k/20k chỉ để thử nghiệm, không áp dụng mã ưu đãi."

## Commands

User:

- `/khuyenmai`
- `/uudai`
- `/promos`
- `/promo <code>`
- `/magiamgia <code>`

Admin:

- `/promo_seed_policy`
- `/promo_seed_beta`
- `/promo_list`
- `/promo_create`
- `/promo_disable`
