# TOAN AAS Video Tier Matrix 2026-06-20

Date: 2026-06-17

## Launch tiers

| Tier | Price | Role | Public rule |
|---|---:|---|---|
| low | 200 Xu | Video Trải Nghiệm / marketing starter | Public only when video beta and provider gates pass; limited 3/day, 10/week, 30/month per user |
| basic | 300 Xu | Video Cơ Bản | Same base model line as 200, upsell after 200 limits |
| common | 400 Xu | Video Phổ Thông | Public when smoke/cost gate pass |
| advanced | 500 Xu | Video Nâng Cao | Public when smoke/cost gate pass |
| standard | 600 Xu | Video Bán Hàng | Public when smoke/cost gate pass |
| high | 800 Xu | Video Cao Cấp | Public when smoke/cost gate pass |
| future_1000 | 1000 Xu | Kling/Seedance future | Coming soon, no job |
| future_1500 | 1500 Xu | Premium future | Coming soon, no job |

## Policy

- 200 Xu can be a controlled marketing-loss product but is rate-limited.
- 300 Xu remains the stable upsell tier for the same base quality line.
- 500/600/800 are `PUBLIC_CONTROLLED` when smoke/cost override/admin gate pass, with daily user/global limits and auto-freeze guard.
- 1000/1500 must not call providers until the future provider path is real.

## Status commands

- `/video_tier_status`
- `/video_public_status`
- `/video_gate_status`
- `/video_cost_status`
- `/video_beta_limits`
- `/video_beta_open`
- `/video_beta_close`
- `/video_open_high_tiers`
- `/video_close_high_tiers`
- `/video_smoke_tier_500`
- `/video_smoke_tier_600`
- `/video_smoke_tier_800`
