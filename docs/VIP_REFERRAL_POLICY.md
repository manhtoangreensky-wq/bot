# TOAN AAS VIP And Referral Policy

## Scope

This policy applies to the current Stable Revenue Bot phase.

All rewards are internal TOAN AAS service Xu. They are not cash, cannot be withdrawn, cannot be transferred, and cannot be converted back to money.

## Member Tiers

Member rank is based on cumulative successful top-up amount.

| Tier | Threshold |
|---|---:|
| Tan thu | under 100,000 VND |
| Bac | from 100,000 VND |
| Vang | from 1,000,000 VND |
| Bach Kim | from 10,000,000 VND |
| Kim Cuong | from 50,000,000 VND |
| VIP | from 100,000,000 VND or admin override |

Admin can override a tier with `/set_vip USER_ID TIER`.

## Referral Reward

Referral reward is paid only when all conditions are true:

- The referred user is new.
- The referred user starts the bot from a referral link.
- The referred user completes the first successful top-up.
- The top-up is confirmed by PayOS success or admin manual approval.
- The referred user has not already generated a referral reward.
- The referral is not self-referral, spam, fake account farming, or fraud.

Reward is calculated from base Xu of the referred user's first top-up only.

Launch Bonus, promo bonus, gift codes and trial Xu are excluded.

| Referrer tier | Reward | Cap |
|---|---:|---:|
| Tan thu | 0% | 0 Xu |
| Bac | 3% | 100 Xu |
| Vang | 6% | 150 Xu |
| Bach Kim | 8% | 200 Xu |
| Kim Cuong | 10% | 250 Xu |
| VIP | 12% | 300 Xu |

Example with first top-up base 5,000 Xu:

- Bac receives 100 Xu because 3% is 150 Xu but cap is 100 Xu.
- Vang receives 150 Xu because 6% is 300 Xu but cap is 150 Xu.
- Bach Kim receives 200 Xu.
- Kim Cuong receives 250 Xu.
- VIP receives 300 Xu.

## Tool Discount Helper

The bot includes a helper for future member discounts.

Eligible conditions:

- Base tool cost is at least 50 Xu.
- Tool is not payment, promo, gift, trial, admin-only or provider-fail flow.
- Tool is not disabled or experimental for customers.

Discount rates:

| Tier | Discount |
|---|---:|
| Tan thu | 0% |
| Bac | 0% |
| Vang | 3% |
| Bach Kim | 5% |
| Kim Cuong | 8% |
| VIP | 10% |

MVP note: the helper exists first. Apply discounts to specific tools only after admin confirms the pricing impact.

## Public Commands

- `/referral` - show referral link, policy and quick stats.
- `/ref_link` - show only the referral link.
- `/ref_stats` - show referral stats.
- `/member`, `/vip`, `/rank` - show member tier and benefits.
- `/vip_policy` - show the full member and referral policy.

## Admin Commands

- `/set_vip USER_ID TIER` - set member tier override.
- `/clear_vip USER_ID` - clear tier override.
- `/ref_admin USER_ID` - inspect referral stats for one user.

Allowed tiers:

- `none`
- `bac`
- `vang`
- `bach_kim`
- `kim_cuong`
- `vip`

## Anti-Fraud Rules

- No self-referral.
- Do not overwrite the first referrer.
- No reward if the referred user already deposited before referral registration.
- Each referred user can generate only one referral reward.
- Admin may reject or adjust suspicious referrals later.
