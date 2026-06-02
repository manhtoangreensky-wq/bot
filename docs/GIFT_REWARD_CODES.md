# Gift / Reward Codes - TOAN AAS

## Purpose

Gift code dùng để tặng Xu trực tiếp.

Use cases:

- Xin lỗi khách khi hệ thống lỗi.
- Tặng khách VIP.
- Tặng khách tiềm năng.
- Tặng Xu trải nghiệm.
- Test hệ thống.
- Thưởng campaign.

## Difference From Deposit Promo

| Type | When Xu is added | Example |
|---|---|---|
| Deposit promo | After PayOS success | FIRST30 |
| Gift code | Immediately after valid redemption | BETA100 |

## User Commands

- `/gift <code>`
- `/nhanqua <code>`
- `/promo <code>`

If `/promo <code>` points to a `gift_xu` code, the bot credits Xu immediately.

## Admin Commands

- `/gift_create code=BETA100 xu=100 limit=100 per_user=1 note="..."`
- `/gift_seed_beta`
- `/gift_list`
- `/gift_disable <code>`

## Default Beta Gift Codes

- BETA5
- BETA10
- BETA20
- BETA100
- BETA200
- BETA500
- BETA1000

## Safety Rules

- Admin only creates codes.
- User redemption must be logged.
- Usage limit required.
- Per-user limit required.
- No secrets in logs.
- No unlimited public codes unless explicitly approved.
