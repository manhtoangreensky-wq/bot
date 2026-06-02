# STABLE REVENUE BOT STATUS

## Compile

- `py_compile`: PASS using Codex bundled Python on 2026-06-02.

## UI

- Website TOAN AAS: `index.html` exists and `/landing` serves it.
- Website index update: landing reworked for TOAN AAS V15.2 Stable Revenue Bot on 2026-06-02.
- Website CTA: Telegram bot, PayOS Xu section, Video Script Lite, affiliate workflow, and `/lead` form.
- `/start`: creates/loads user, handles referral payload, shows public menu.
- `/menu`: reuses start/menu flow.
- User menu: public service/payment/profile/help surface.
- Admin menu: operator/system/internal areas are gated.

## Data safety

- `DB_FILE`: `_env("DB_FILE", "toandaas_system.db")`.
- DB_FILE env support: YES.
- Railway volume docs: `docs/RAILWAY_VOLUME_SETUP.md`.
- `/health`: exists and checks DB/config flags without external API calls.
- `/backup_db`: exists, admin-only, sends DB document if file exists and size is acceptable.

## Payment

- `/naptien`: present.
- packages: 6 packages from `10k` to `500k`.
- checkout: dynamic PayOS checkout path exists.
- webhook: `/webhook/payos` exists.
- duplicate protection: `payos_processed` plus order status checks.
- manual fallback: `/thucong`, `pending_deposits`, `/duyet`, `/tuchoi`.

## Credits

- trial: `TRIAL_CREDITS = 150`.
- has_deposited: stored on users and used for first-deposit/referral logic.
- deduct: fixed and dynamic credit helpers exist.
- add: `add_credit()` and admin/manual deposit paths exist.
- refund: `refund_charged_credit()` exists; per-flow coverage still needs audit.

## Admin

- `/dashboard`: exists.
- `/stats`: exists.
- `/backup_db`: exists.
- `/pending`, `/duyet`, `/tuchoi`, `/checkpayos`: exist.

## Next risk to fix

1. Verify Railway Volume and DB persistence after redeploy.
2. Run real `/backup_db` on Telegram admin account.
3. Audit PayOS security and money flow without changing package/callback logic.
4. Audit refund coverage for paid API failures.
5. Improve trial upsell after foundation is verified.

## Phase 1 Money Flow Completion

- PayOS security audit: documented; no code change required in PayOS.
- Trial upsell: shared missing-Xu message now sells topup clearly.
- Topup keyboard: existing `pkg|50k/100k/200k` preserved.
- Balance hint: added for paid chat success.
- Refund audit: chat paid exception now refunds; existing media refunds retained.
- Referral: `/ref` expanded with stats; `/invite` alias added.
- Admin revenue dashboard: `/dashboard` and `/admin` show today/month revenue, users, xu, referrals, pending.

## Remaining blockers before Video Script Lite

1. Real PayOS payment test on Railway.
2. Real `/backup_db` Telegram test.
3. Real provider failure tests for Fish/Deepgram/RemoveBG/Cutout/Cobalt.
4. Confirm Railway Volume persistence after redeploy.

## Video Script Lite Status

- Commands: `/film`, `/video_script`.
- Cost: 50 Xu/script pack.
- Scope: script, prompts, captions, CTA, hashtags, quality check.
- Platforms: Facebook, TikTok, YouTube by default.
- Affiliate integration: `/film topic="..." affiliate_id=1` validates owner link before charging.
- Output: Telegram preview plus Markdown file export.
- DB: `video_script_jobs`, `video_script_outputs`.
- Safety: no render, no auto publish, no browser automation.
- Remaining tests: real Telegram command, insufficient-Xu account, AI quota failure/refund, file export.

## Affiliate + Calendar MVP Status

- `/addlink`: user-facing link storage, owner-scoped.
- `/links`: user-facing active link list.
- `/campaign`: user-facing campaign create/list.
- `/addcal`: user-facing manual content calendar insert.
- `/calendar`: user-facing next-7-days calendar view.
- `/dashboard`: includes video script, active campaign, affiliate link, and calendar counters.
- DB: reused `affiliate_links`, `campaigns`, `content_calendar`.
- Safety: no PayOS/billing changes, no auto publish, no render API.
