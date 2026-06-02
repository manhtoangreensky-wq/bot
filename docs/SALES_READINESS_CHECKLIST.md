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
- [ ] `/menu` is clear for customers.
- [ ] `/help` and `/commands` work.
- [ ] Normal users do not see admin/operator commands.

## Money flow

- [ ] `/profile`.
- [ ] `/naptien`.
- [ ] PayOS 10k real payment test.
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
- `SALES READY`: PayOS real test passes, backup works, tools pass smoke tests, and at least 3 beta users run without payment errors.
