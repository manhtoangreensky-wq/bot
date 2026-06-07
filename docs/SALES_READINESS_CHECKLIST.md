# SALES READINESS CHECKLIST - TOAN AAS

Date: 2026-06-02

## Current Evidence - 2026-06-07

- Latest pushed commit: `706998a Add admin provider orchestrator v1`.
- Local checks: `python -m py_compile bot.py` PASS, `python -m py_compile local_worker.py` PASS, `pytest -q` PASS with 29 tests, `git diff --check` PASS.
- PayOS: admin-reported live PASS for checkout URL creation, real payment and automatic Xu credit.
- Local Worker Phase 1: admin-reported LIVE PASS for Railway ENV, Windows worker heartbeat/poll, worker ping and ffmpeg health.
- New provider orchestrator is admin-only/code-ready and needs live Telegram smoke after deploy.

## Website

- [ ] `/` shows TOAN AAS landing.
- [ ] `/landing` shows TOAN AAS landing.
- [ ] `/banner.png` loads.
- [ ] `/LOGO.png` loads.
- [ ] CTA opens the main Telegram bot.
- [ ] CTA tells users to use `/naptien` to top up Xu.
- [ ] `/lead` form works if used.

## Bot onboarding

- [ ] `/start` is clear for customers.
- [ ] `/start` explains new users receive 200 Xu and can try one `/film` Basic.
- [ ] `/menu` is clear for customers.
- [ ] `/help` and `/commands` work.
- [ ] Normal users do not see admin/operator commands.

## Money flow

- [ ] `/profile`.
- [ ] `/naptien`.
- [ ] `/promo FIRST30` activates once for a beta test user after admin `/promo_seed_policy`.
- [x] PayOS real payment test - admin-reported PASS on 2026-06-07.
- [ ] First PayOS 50k + FIRST30 real payment gives exactly 680 Xu: 500 base + 30 Launch Bonus + 150 promo.
- [ ] PayOS first 100k real payment gives exactly 1,050 Xu without promo: 1,000 base + 50 Launch Bonus.
- [ ] Manual fallback.
- [ ] Missing-Xu upsell.
- [ ] Refund on paid API failure.
- [ ] `/dashboard` revenue counters.

## Core tools

- [ ] Chat AI.
- [ ] Voice/TTS.
- [ ] STT.
- [ ] Background removal.
- [ ] Downloader.

## Customer revenue tools

- [ ] `/film`.
- [ ] `/growth_ai`.
- [ ] `/campaign_report`.

## Internal/backlog locks

- [ ] Normal user calling `/addlink`, `/links`, `/calendar` receives the internal/backlog message.
- [ ] Normal user calling `/publish_done`, `/performance_report`, `/growth_loop` receives the internal/backlog message.
- [ ] Admin can still test internal affiliate/calendar/publish commands.

## Admin

- [ ] `/dashboard`.
- [ ] `/stats`.
- [ ] `/providers`.
- [ ] `/costs`.
- [ ] `/sales_ready`.
- [ ] `/payos_test_plan`.
- [ ] `/promo_seed_beta`.
- [ ] `/mark_payos_test`.
- [ ] `/backup_db`.
- [ ] `/runtime`.
- [ ] `/orchestrator_status`.
- [ ] `/provider_matrix`.
- [ ] `/tool_test_openrouter`.
- [ ] `/tool_test_kling_status`.
- [ ] `/tool_test_replicate_status`.
- [ ] `/tool_test_elevenlabs_status`.
- [ ] `/tool_test_deepgram_status`.
- [ ] `/shopaikey_status`.
- [ ] `/tool_test_shopaikey`.

## Safety

- [ ] No auto publish.
- [ ] No spam workflow.
- [ ] No deepfake/non-consent workflow.
- [ ] No API key exposed in Telegram, `/health`, `/runtime`, logs, or docs.
- [ ] Railway Volume or backup process is verified.

## Ready status rule

- `NOT READY`: DB, PayOS, AI, or `/film` is not ready.
- `BETA READY`: core checks pass, but PayOS real payment still needs manual confirmation.
- `SALES READY`: core checks pass and `/mark_payos_test pass ...` has recorded `payos_real_payment_test_status=PASS`.
- Promo/BETA50 is visible in `/sales_ready` for admin review, but does not automatically mark sales ready.

## PayOS real test status

- `NOT_TESTED`: default state.
- `FAIL`: admin marked the test as failed.
- `PASS`: admin confirmed a real 10k payment test passed.

Command:

```text
/mark_payos_test pass order=<order_code> note="Test 10k OK"
```

Rule: never mark `SALES READY` until PayOS real test is `PASS` and the current deployed bot passes the core live Telegram smoke checks.
