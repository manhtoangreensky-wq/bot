# TOAN AAS Admin Reporting And Persistent Modes

## Scope

This module is for the current Telegram revenue bot. It adds admin reporting, usage metrics and persistent user chat modes without changing PayOS, promo, gift, trial, pricing or provider logic.

## Database Tables

`usage_events`

- Tracks lightweight operational events.
- Examples: `/start`, `/naptien`, `/promo`, `/gift`, `/film`, chat tool usage, PayOS paid order, manual bill approval.
- Does not store API keys, tokens or provider secrets.

`user_modes`

- Stores persistent user chat mode by Telegram ID.
- `/start` does not reset user mode.
- Current supported modes: `normal`, `pro`, `deep`.

## Admin Report Commands

- `/admin_dashboard` - compact admin dashboard for today.
- `/report_today` - today report.
- `/report_week` - last 7 days report.
- `/report_month` - current month report.
- `/report_year` - current year report.
- `/report_range YYYY-MM-DD YYYY-MM-DD` - custom date range.
- `/report_ai_today` - AI insight for today's report.
- `/report_ai_week` - AI insight for last 7 days.
- `/report_ai_month` - AI insight for current month.
- `/report_chart_today` - text chart fallback for today.
- `/report_chart_week` - text chart fallback for last 7 days.
- `/report_chart_month` - text chart fallback for current month.

## Metrics Included

- Total users, new users, active users and returning users.
- PayOS paid orders and manual QR approvals.
- Revenue amount, sold Xu, added Xu, spent Xu and circulating Xu.
- Trial grants and promo/gift/launch credit events.
- Tool usage, success, failure and top commands.
- Provider debug/error summary.

## Persistent User Mode Commands

- `/mode` - view current mode.
- `/chat_pro_on` - keep Chat Pro active for future chat messages.
- `/chat_pro_off` - return to normal mode.
- `/chat_deep_on` - keep Chat Deep active for future chat messages.
- `/chat_deep_off` - return to normal mode.

## Smoke Test

Run after deploy:

```text
/admin_dashboard
/report_today
/report_week
/report_month
/report_ai_today
/report_chart_week
/mode
/chat_pro_on
send a normal chat message
/chat_pro_off
/chat_deep_on
send a normal chat message
/chat_deep_off
/sales_ready
```

Expected:

- Admin-only commands reject non-admin users.
- Reports do not expose secrets.
- Text charts render without extra dependencies.
- AI insight fails gracefully if AI provider is unavailable.
- User mode persists after `/start` until explicitly turned off.

## Locked Areas

This module must not alter:

- PayOS webhook or checkout signature.
- Manual QR fallback.
- Payment packages and pricing.
- Promo/gift/trial policy.
- Customer publish, ads or affiliate vault exposure.
