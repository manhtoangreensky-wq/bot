# Promotion System V1/V2 - TOAN AAS

## Strategy

Keep base pricing clear and stable. Promotions do not change PayOS amount; they grant extra Xu after successful payment.

## User Flow

1. User receives 200 Xu trial on first use.
2. User tries a lightweight workflow such as `/film`.
3. User checks offers with `/khuyenmai`.
4. User enters one code, for example `/promo FIRST30`.
5. User runs `/naptien` and pays through PayOS.
6. After PayOS success, the bot credits base Xu plus one promo bonus.

Promo starts at 50k. The 10k/20k packages are trial/test packages and do not receive public promo bonus.

Launch Bonus is separate from promo code and is credited once per user per eligible package after PayOS success.

## Promo Types

- `percent_bonus`
- `fixed_bonus_xu`
- `service_discount_future`
- `gift_xu`

## Commands

User:

- `/promo <code>`
- `/magiamgia <code>`
- `/khuyenmai`
- `/uudai`
- `/promos`
- `/gift <code>`
- `/nhanqua <code>`

Admin:

- `/promo_seed_policy`
- `/promo_seed_beta`
- `/promo_create`
- `/promo_list`
- `/promo_disable`
- `/gift_create`
- `/gift_seed_beta`
- `/gift_list`
- `/gift_disable`

## Example

50k = 500 Xu.

FIRST30 = +30%.

If the user has not bought the 50k package before, Launch Bonus adds +30 Xu.

User receives 680 Xu total after PayOS success: 500 base Xu + 30 Launch Bonus + 150 promo bonus.

## Safety

- Do not change PayOS VND amount.
- Do not change `PAYMENT_PACKAGES`.
- Do not credit bonus before payment success.
- Duplicate webhook must not credit bonus twice.
- Promo activation stores only one pending code per user.
