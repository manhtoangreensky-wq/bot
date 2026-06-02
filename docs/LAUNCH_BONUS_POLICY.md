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
- FIRST30 bonus: internal capped calculation
- Final customer-facing total under current policy: 7,000 Xu

## Storage

`launch_bonus_redemptions` stores one row per user/package:

- `user_id`
- `package_amount_vnd`
- `base_xu`
- `launch_bonus_xu` / `bonus_xu`
- `order_code`
- `status`
- `note`

The unique protection is `user_id + package_amount_vnd`, exposed through `idx_launch_bonus_user_package`.

`payos_orders` also stores the order-time preview fields `package_amount_vnd`, `base_xu`, `launch_bonus_xu` and `xu` total. Actual crediting still happens only after PayOS success.

Manual fallback uses the same order-time `xu` preview as the PayOS order. Example: a first 50k package order must show `530 Xu`, and a first 100k package order must show `1,050 Xu`, in both PayOS QR flow and manual QR fallback.

If admin approves a manual bill connected to an eligible order, `launch_bonus_redemptions` is recorded so the same user/package cannot receive Launch Bonus twice.

## Safety

- Never credit Launch Bonus before PayOS success.
- Do not credit Launch Bonus twice for same user/package.
- Duplicate webhook must not duplicate base, launch, or promo bonus.
- Old paid PayOS orders count as prior package purchases for launch eligibility.
- Manual transfer content uses `AAS <user_id> <order_code>`.
