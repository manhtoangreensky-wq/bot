# Promo Policy Audit

Date: 2026-06-02

## Compile

- `py_compile`: PASS before implementation.

## Current Promo Codes

| Code | Current value | New value | Action |
|---|---:|---:|---|
| FIRST30 | missing/variable | +30% Xu | Seed active |
| SECOND20 | legacy if present | disabled | Disable, replaced by SECOND15 |
| SECOND15 | missing/variable | +15% Xu | Seed active |
| WEEKLY15 | legacy if present | disabled | Disable, replaced by WEEKLY10 |
| WEEKLY10 | missing/variable | +10% Xu | Seed active |
| DAILY10 | legacy if present | disabled | Disable, replaced by DAILY5 |
| DAILY5 | missing/variable | +5% Xu | Seed active |
| MONTHLY20 | missing/variable | +20% Xu | Seed active for larger deposits |
| BETA50 | fixed beta bonus | +50% Xu | Keep limited/internal only |

## Stacking Rule

- One order = one promo only.
- `user_promo_state` stores only one pending code per user.
- A new promo replaces the previous pending promo.
- Bonus is credited only after PayOS success.

## Decision

- FIRST30 remains the strongest public offer.
- SECOND20 becomes SECOND15.
- WEEKLY15 becomes WEEKLY10.
- DAILY10 becomes DAILY5.
- MONTHLY20 remains for larger deposits.
- BETA50 remains limited/internal and should not be promoted broadly.
