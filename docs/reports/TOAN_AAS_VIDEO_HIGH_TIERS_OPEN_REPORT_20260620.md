# TOAN AAS Video High Tiers Open Report 2026-06-20

Date: 2026-06-17

## Scope

Open Video AI tiers 500/600/800 as `PUBLIC_CONTROLLED` after provider smoke and admin cost override gates. This report does not change payment, top-up, package wallet, trial bonus, or PayOS logic.

## Tier policy

| Tier | Price | Public mode | Limit |
|---|---:|---|---|
| advanced | 500 Xu | PUBLIC_CONTROLLED | 2/user/day, 20/global/day |
| standard | 600 Xu | PUBLIC_CONTROLLED | 2/user/day, 15/global/day |
| high | 800 Xu | PUBLIC_CONTROLLED | 1/user/day, 10/global/day |

## Guard rails

- 200/300/400 remain on the existing beta path.
- 500/600/800 require the shared Video AI smoke gate and public video billing guard.
- High tiers can pass the cost gate through `VIDEO_COST_GATE_ALLOW_HIGH_TIERS_AFTER_SMOKE=true` and `VIDEO_COST_GATE_ALLOW_ADMIN_OVERRIDE=true`.
- Provider failures must keep refund/job-lock behavior unchanged.
- `VIDEO_HIGH_TIER_AUTO_FREEZE_ON_ERROR=true` is available for freeze automation.
- 1000/1500, long render, premium, Kling and Seedance stay `COMING_SOON`/OFF.

## Commands

- `/video_tier_status`
- `/video_cost_status`
- `/video_open_high_tiers`
- `/video_close_high_tiers`
- `/video_smoke_tier_500`
- `/video_smoke_tier_600`
- `/video_smoke_tier_800`

## Verification

- Admin status should show 500/600/800 as `PUBLIC_CONTROLLED` after gates pass.
- Public users should not see raw `billing/cost gate` errors for controlled tiers.
- If a high tier exceeds its daily user/global limit, the bot blocks before provider call and before Xu deduction.
- 1000/1500 remain coming soon and do not create provider jobs.
