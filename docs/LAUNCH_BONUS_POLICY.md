# Launch Bonus Policy - TOAN AAS

## Rule

Launch Bonus is granted once per user per eligible package.

| Package | Base Xu | Launch Bonus | First purchase total | Repeat purchase total |
|---|---:|---:|---:|---:|
| 50k | 500 | +30 | 530 | 500 |
| 100k | 1,000 | +50 | 1,050 | 1,000 |
| 200k | 2,000 | +150 | 2,150 | 2,000 |
| 500k | 5,000 | +500 | 5,500 | 5,000 |

Non-eligible:

- 10k = 100 Xu
- 20k = 200 Xu

## Promo Interaction

Launch Bonus can coexist with one promo code.

Launch Bonus is not a promo code.

One order can have:

- Base Xu
- Launch Bonus if first purchase of that package
- One promo code bonus if eligible

## Example

500k first purchase with FIRST30:

- Base Xu: 5,000
- Launch Bonus: +500
- FIRST30: +30% Xu, capped internally by policy
- Final customer-facing total under current policy: 7,000 Xu

## Safety

- Never credit Launch Bonus before PayOS success.
- Do not credit Launch Bonus twice for same user/package.
- Duplicate webhook must not duplicate base, launch, or promo bonus.
- Old paid PayOS orders count as prior package purchases for launch eligibility.
