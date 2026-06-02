# Promotion Policy V2.1 - TOAN AAS

## Philosophy

TOAN AAS does not discount top-up money and does not lower the base price. Promotions are expressed as extra Xu so customers can use more service after payment.

## Rules

- No VND discount.
- No base price discount.
- One order can use only one promo code.
- Promo codes do not stack.
- A new pending promo replaces the old pending promo.
- Bonus Xu is credited only after PayOS payment success.
- Duplicate webhook or `/checkpayos` replay must not add promo bonus twice.

## Main Public Offers

| Code | Bonus | Purpose |
|---|---:|---|
| FIRST30 | +30% Xu | First top-up, strongest public offer |
| SECOND15 | +15% Xu | Second top-up |
| MONTHLY20 | +20% Xu | Monthly or larger package offer |
| WEEKLY10 | +10% Xu | Weekly offer |
| DAILY5 | +5% Xu | Light daily incentive |

## Limited/Internal

| Code | Bonus | Usage |
|---|---:|---|
| BETA50 | +50% Xu | Beta/internal limited only, not broad public campaign |

## Recommended Use Order

1. FIRST30
2. SECOND15
3. MONTHLY20
4. WEEKLY10
5. DAILY5

## Customer-Facing Wording

"Không giảm giá. TOAN AAS tặng thêm Xu để bạn dùng được nhiều hơn."

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
