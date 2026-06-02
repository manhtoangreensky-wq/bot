# TRIAL BONUS AUDIT

Date: 2026-06-02
Scope: new-user trial/welcome bonus only.

## Current trial-related constants

| Name | Old value | New value | File |
|---|---:|---:|---|
| `TRIAL_CREDITS` | 150 Xu | 200 Xu | `bot.py` |

## Text references

| File | Old text | New text |
|---|---|---|
| `bot.py` | `150 Xu dùng thử` | `200 Xu trải nghiệm` |
| `bot.py` | trial grant note `Tặng xu dùng thử` | `Tặng 200 Xu trải nghiệm` |
| `index.html` | `150 Xu` trial copy | `200 Xu` trial copy |
| `docs/COST_CONTROL.md` | `Trial credits 150 Xu` | `Trial credits 200 Xu` |
| `docs/PRICING_ENGINE_V2.md` | no trial strategy section | added `New user trial = 200 Xu` |
| `docs/STABLE_REVENUE_BOT_STATUS.md` | `TRIAL_CREDITS = 150` | `TRIAL_CREDITS = 200` |
| `docs/CURRENT_STATE.md` | `TRIAL_CREDITS = 150` | `TRIAL_CREDITS = 200` |

## 150 values kept

| File | Reason kept |
|---|---|
| `bot.py` | `Tặng 150 Xu` belongs to the 200k payment package bonus, not trial. |
| `index.html` | `tặng 150 Xu` belongs to the 200k payment package card, not trial. |
| `docs/PRICING_AUDIT.md` | `IMAGE_REMOVE_BG_PREMIUM_COST = 150 Xu` is image pricing, not trial. |
| `docs/PRICING_ENGINE_V2.md` | `Background removal 80-150 Xu` is image pricing, not trial. |

## Decision

New user trial bonus = 200 Xu.

This applies to new users after deploy. Existing users are not automatically topped up in this task; a separate migration must be approved if admin wants to add 50 Xu to old trial users.
