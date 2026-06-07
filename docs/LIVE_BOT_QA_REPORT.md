# LIVE BOT QA REPORT - TOAN AAS

Date: 2026-06-02
App: TOAN AAS V15.2
Public website: `https://www.toanaas.vn/`
Backend/runtime: Railway `PUBLIC_BASE_URL`

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
- `python -m py_compile local_worker.py`: PASS.
- `pytest -q`: PASS, 29 tests on 2026-06-07 after commit `706998a`.
- Import test: PASS, `cmd_help` and `help_text_for_user` exist.
- Local route smoke: PASS for `/`, `/landing`, `/health`, `/banner.png`.

## 2026-06-07 Current Evidence Snapshot

- Latest pushed commit: `706998a Add admin provider orchestrator v1`.
- Git status after push: clean.
- Local Worker Phase 1: admin-reported LIVE PASS for Railway ENV, Windows heartbeat, worker poll, worker ping and ffmpeg health.
- PayOS: admin-reported real payment PASS, checkout URL creation PASS and automatic Xu credit PASS. Keep PayOS logic locked unless a direct PayOS task is given.
- Provider Orchestrator V1: CODE READY/admin-only with `/orchestrator_status`, `/provider_matrix`, `/tool_test_openrouter`, `/tool_test_kling_status`, `/tool_test_replicate_status`, `/tool_test_elevenlabs_status`, `/tool_test_deepgram_status`, `/shopaikey_status`, `/tool_test_shopaikey`.
- ShopAIKey: experimental admin-only provider, disabled by default, not public and not default.

## Telegram Smoke Test

| Test | Expected | Result | Notes |
|---|---|---|---|
| `/start` | User onboarding + menu | Need live Telegram verification | User should not see operator/admin commands. |
| `/menu` | Main menu | Need live Telegram verification | Same funnel as `/start`. |
| `/help` | Quick guide | Added in Step 6 | Registered handler. |
| `/commands` | Same as `/help` | Added in Step 6 | Registered alias. |
| `/profile` | Balance/profile | Need live Telegram verification | No external API. |
| `/naptien` | Package buttons | Need live Telegram verification | `pkg|` callback unchanged. |
| `pkg|` callback | PayOS/manual fallback | Admin-reported PayOS real PASS | PayOS code locked; manual fallback remains available. |
| `/film` | Script Lite + file | Need live Telegram verification | Requires AI key and enough Xu. |
| `/addlink` as normal user | Internal/backlog lock message | Need live Telegram verification | Admin can still test internally. |
| `/links` as normal user | Internal/backlog lock message | Need live Telegram verification | No public affiliate vault. |
| `/calendar` as normal user | Internal/backlog lock message | Need live Telegram verification | No public calendar. |
| `/publish_done` as normal user | Internal/backlog lock message | Need live Telegram verification | No public publish tracking. |
| `/performance_report` as normal user | Internal/backlog lock message | Need live Telegram verification | Admin/internal only. |
| `/growth_loop` as normal user | Internal/backlog lock message | Need live Telegram verification | Admin/internal only. |
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
4. Existing public surface test must treat `/addlink` as internal/backlog and verify normal users do not access it.

## Fixes Applied

1. Added `cmd_help`.
2. Registered `/help` and `/commands`.
3. Updated `/start` copy for the revenue/onboarding funnel.
4. Updated support menu to point users to `/help`.
5. Guarded affiliate/calendar/publish/operator lab commands for non-admin users.

## Manual Admin Checklist After Deploy

- Run `/runtime` and confirm build matches the latest Git commit.
- Run `/customer_surface` and confirm no A-TOOLS/operator leak.
- Run `/naptien`, click 10k/50k/100k, and confirm PayOS/manual fallback text still matches the locked flow.
- Run `/orchestrator_status` and `/provider_matrix` after deploy to confirm new admin-only provider layer is visible.
