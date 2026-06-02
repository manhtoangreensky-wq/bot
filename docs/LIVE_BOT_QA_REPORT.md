# LIVE BOT QA REPORT - TOAN AAS

Date: 2026-06-02
App: TOAN AAS V15.2
Domain: `https://bot-production-2dd7.up.railway.app`

## Deploy

| Route | Expected | Last verified | Notes |
|---|---|---:|---|
| `/` | TOAN AAS landing HTML | PASS local Step 6 | Root serves `index.html`. |
| `/landing` | TOAN AAS landing HTML | PASS local Step 6 | Same landing file. |
| `/health` | JSON status | PASS local Step 6 | No external API calls required. |
| `/banner.png` | Banner image | PASS local Step 6 | Static safe route. |
| `/LOGO.png` | Logo image | PASS before Step 6 | Static safe route. |

## Automated Test Result

- `python -m py_compile bot.py`: PASS.
- `pytest -q`: PASS, 13 tests.
- Import test: PASS, `cmd_help` and `help_text_for_user` exist.
- Local route smoke: PASS for `/`, `/landing`, `/health`, `/banner.png`.

## Telegram Smoke Test

| Test | Expected | Result | Notes |
|---|---|---|---|
| `/start` | User onboarding + menu | Need live Telegram verification | User should not see operator/admin commands. |
| `/menu` | Main menu | Need live Telegram verification | Same funnel as `/start`. |
| `/help` | Quick guide | Added in Step 6 | Registered handler. |
| `/commands` | Same as `/help` | Added in Step 6 | Registered alias. |
| `/profile` | Balance/profile | Need live Telegram verification | No external API. |
| `/naptien` | Package buttons | Need live Telegram verification | `pkg|` callback unchanged. |
| `pkg|` callback | PayOS/manual fallback | Need real payment test | PayOS code not changed in Step 6. |
| `/film` | Script Lite + file | Need live Telegram verification | Requires AI key and enough Xu. |
| `/addlink` | Save affiliate URL | Need live Telegram verification | Owner-scoped. |
| `/links` | List affiliate links | Need live Telegram verification | Active links only. |
| `/calendar` | Content calendar | Need live Telegram verification | 7-day view. |
| `/publish_done` | Record manual post | Need live Telegram verification | No social API call. |
| `/performance_report` | Manual performance report | Need live Telegram verification | Uses stored manual metrics. |
| `/growth_loop` | Scale/fix suggestions | Need live Telegram verification | Rule-based for user flow. |
| `/dashboard` admin | Admin dashboard | Need admin verification | Admin-only. |
| `/backup_db` admin | Send DB backup | Need admin verification | Requires DB file and Telegram. |

## Critical Checks

- PayOS touched in Step 6: NO.
- Billing package prices touched in Step 6: NO.
- `pkg|` callback touched in Step 6: NO.
- `prov|` callback touched in Step 6: NO.
- Auto publish added in Step 6: NO.
- Social API calls added in Step 6: NO.
- User/admin separation: `/start`, `/menu`, `/help` now keep admin/operator commands hidden from user-facing text.

## Issues Found

1. `/help` and `/commands` were missing before Step 6.
2. `/start` text did not clearly show trial -> tool -> missing Xu -> `/naptien` funnel.
3. Local `bot.py` contained Step 4/5 commands that must be committed for Railway to expose them.
4. Existing public surface test treats `/addlink` as `/add`; `/start` avoids showing `/addlink` directly and keeps it in `/help`/money menu.

## Fixes Applied

1. Added `cmd_help`.
2. Registered `/help` and `/commands`.
3. Updated `/start` copy for the revenue/onboarding funnel.
4. Updated support menu to point users to `/help`.

## Manual Admin Checklist After Deploy

- Run `/runtime` and confirm build matches the latest Git commit.
- Run `/customer_surface` and confirm no A-TOOLS/operator leak.
- Run `/naptien`, click 10k/50k/100k, and confirm PayOS/manual fallback text.
- Run a small real PayOS 10k test only after Railway deploy is healthy.
