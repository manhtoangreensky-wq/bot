# SALES READINESS CHECKLIST - TOAN AAS

Date: 2026-06-02

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
- [ ] `/promo BETA50` activates once for a beta test user after admin `/promo_seed_beta`.
- [ ] PayOS 10k real payment test.
- [ ] PayOS 20k + FIRST30 real payment gives exactly 260 Xu.
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

## Revenue tools

- [ ] `/film`.
- [ ] `/addlink`.
- [ ] `/links`.
- [ ] `/calendar`.
- [ ] `/publish_done`.
- [ ] `/performance_report`.
- [ ] `/growth_loop`.
- [ ] `/growth_ai`.
- [ ] `/campaign_report`.

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

Rule: never mark `SALES READY` until PayOS real test is `PASS`.
