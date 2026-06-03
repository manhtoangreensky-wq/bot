# TOAN AAS VIP, Referral, Tier Promo And Birthday Policy

Status: current bot policy.

## Member Tiers

| Internal key | Badge | Threshold |
|---|---|---:|
| `newbie` | 🌱 Newbie | under 100,000 VND |
| `silver` | 🥈 Silver | from 100,000 VND |
| `gold` | 🥇 Gold | from 1,000,000 VND |
| `platinum` | 💠 Platinum | from 10,000,000 VND |
| `diamond` | 💎 Diamond | from 50,000,000 VND |
| `vip` | 👑 VIP | from 100,000,000 VND or admin override |

Old aliases are kept for data compatibility:
`none` -> `newbie`, `bac` -> `silver`, `vang` -> `gold`, `bach_kim` -> `platinum`, `kim_cuong` -> `diamond`.

## Platinum+ Free Chat

Platinum, Diamond and VIP get:

- Free Normal Chat.
- Free Chat Pro.
- Chat Deep still costs Xu to control deep/API-heavy work.

Base chat prices remain unchanged:

- Normal Chat: 5 Xu.
- Chat Pro: 10 Xu.
- Chat Deep: 20 Xu.

AI/provider failure must not charge Xu.

## Referral Rewards

Referral rewards are paid only when the referred user completes their first successful deposit.

Rewards are calculated from base Xu only:

- No Launch Bonus in referral base.
- No promo bonus in referral base.
- No gift/trial in referral base.
- One reward per referred user.
- No self-referral.

| Referrer tier | Percent | Cap |
|---|---:|---:|
| Newbie | 0% | 0 Xu |
| Silver | 3% | 100 Xu |
| Gold | 6% | 150 Xu |
| Platinum | 8% | 200 Xu |
| Diamond | 10% | 250 Xu |
| VIP | 12% | 300 Xu |

Calculation example with `base_xu=5000`:

- Silver: 100 Xu.
- Gold: 150 Xu.
- Platinum: 200 Xu.
- Diamond: 250 Xu.
- VIP: 300 Xu.

## Tier-Up Promo

When a user crosses a member tier threshold, the bot creates a personal top-up promo.

Code format:

`UP_<TIER>_<USERID_SHORT>`

Rules:

- Owner-only. Other users cannot use the code.
- One code per tier per user.
- One use only.
- Minimum top-up amount: 50,000 VND.
- Does not stack with other promo codes.
- Adds service Xu only. It is not cash discount.

| Tier reached | Bonus | Cap |
|---|---:|---:|
| Silver | +10% | 100 Xu |
| Gold | +12% | 150 Xu |
| Platinum | +15% | 250 Xu |
| Diamond | +18% | 400 Xu |
| VIP | +20% | 600 Xu |

Commands:

- User: `/my_promos`
- Admin: `/grant_tier_promo USER_ID TIER`

## Birthday Gifts

Birthday gifts are service Xu only.

| Tier | Birthday gift |
|---|---:|
| Newbie | 0 Xu |
| Silver | 111 Xu |
| Gold | 333 Xu |
| Platinum | 555 Xu |
| Diamond | 666 Xu |
| VIP | 888 Xu |

Rules:

- User must save birthday with `/set_birthday DD-MM`.
- If birthday is not saved, the system does not automatically grant a gift.
- No birth year is required.
- User cannot self-change birthday after saving.
- Birthday must be saved at least 30 days before the birthday for automatic gift.
- If birthday is within 30 days after saving, admin manual review is required.
- One gift per account per year.
- Birthday gifts are internal service Xu only, not withdrawable, transferable, or redeemable back to cash.
- Admin can grant manually with `/birthday_gift_grant USER_ID`.
- Admin can inspect with `/birthday_gift_check USER_ID`.

## Tool Discount

Eligible tools can use member discounts when base cost is at least 50 Xu and the tool is not disabled/admin-only/provider-failing.

Discounts:

- Newbie: 0%.
- Silver: 0%.
- Gold: 3%.
- Platinum: 5%.
- Diamond: 8%.
- VIP: 10%.

Not eligible:

- Payment, PayOS, manual QR.
- Promo, gift, trial.
- Admin/internal tools.
- Disabled or provider-failing tools.
- Chat pricing under 50 Xu, except Platinum+ free Normal/Pro chat.

## Anti-Fraud

- No self-referral.
- Do not overwrite the first referrer.
- No referral reward if referred user had a successful deposit before referral.
- One referral reward per referred user.
- Admin can reject suspicious referral or birthday claims.
- Birthday changes require admin.
- All benefits are internal service Xu only: no cash withdrawal, no transfer, no conversion back to money.

## Admin Commands

- `/set_vip USER_ID newbie|silver|gold|platinum|diamond|vip`
- `/clear_vip USER_ID`
- `/ref_admin USER_ID`
- `/grant_tier_promo USER_ID silver|gold|platinum|diamond|vip`
- `/set_birthday_admin USER_ID DD-MM`
- `/birthday_gift_check USER_ID`
- `/birthday_gift_grant USER_ID`
