# STABLE REVENUE BOT STATUS

## Compile

- `py_compile`: PASS using Codex bundled Python on 2026-06-02.
- `pytest -q`: PASS, 21 tests, 1 Starlette/httpx deprecation warning.
- Import test: PASS, `cmd_help` and `help_text_for_user` exist.
- Step 7 import test: PASS, `cmd_growth_ai`, `cmd_campaign_report`, and report CSV helper exist.
- Step 8 compile: PASS after provider status and sales readiness commands.
- Step 9 compile: PASS after sales hardening, `/mark_payos_test`, and beta offer commands.
- Step 10 compile: PASS after Pricing Engine V2 and higher Xu defaults.
- Step 11 compile: PASS after Chat AI Tier System and `/chat_pro`.
- Trial bonus update: `TRIAL_CREDITS = 200` so new users can try one `/film` Basic.

## UI

- Website TOAN AAS: `index.html` exists and `/landing` serves it.
- Website index update: landing reworked for TOAN AAS V15.2 Stable Revenue Bot on 2026-06-02.
- Website CTA: Telegram bot, PayOS Xu section, Video Script Lite, Content Pack self-post workflow, and `/lead` form.
- `/start`: creates/loads user, handles referral payload, shows trial -> tool -> missing Xu -> `/naptien` funnel.
- `/menu`: reuses start/menu flow.
- `/help`: added in Step 6, registered with `/commands` alias.
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

## Promo / Beta Codes

- `/promo_seed_policy`: admin-only, seeds Promotion Policy V2.1.
- `/promo_seed_beta`: compatibility alias for `/promo_seed_policy`.
- `/promo <code>` and `/magiamgia <code>`: user-facing one-code pending promo activation.
- `/khuyenmai`, `/uudai`, `/promos`: user-facing promo guide and recommended use order.
- Public codes: `FIRST30`, `SECOND15`, `MONTHLY20`, `WEEKLY10`, `DAILY5`.
- `BETA50`: beta/internal limited, not broad public offer.
- Launch Bonus: 100k +50 Xu, 200k +150 Xu, 500k +500 Xu, once per user/package after PayOS success. 50k is promo-eligible but has no Launch Bonus.
- Launch Bonus storage: `launch_bonus_redemptions` keeps `user_id + package_amount_vnd` unique, with base/bonus/order/note fields for audit.
- Gift codes: `/gift`, `/nhanqua`, and gift-type `/promo` credit Xu immediately when valid.
- Admin gift commands: `/gift_create`, `/gift_seed_beta`, `/gift_list`, `/gift_disable`.
- Promo bonus is applied inside `process_payos_paid_order()` transaction after PayOS success.
- Duplicate paid order replay does not apply base Xu or promo Xu twice.
- One order uses one promo only; new pending code replaces the previous pending code.
- Real PayOS promo test still requires admin execution on Railway.

## Credits

- trial: `TRIAL_CREDITS = 200`.
- has_deposited: stored on users and used for first-deposit/referral logic.
- package base Xu: `PAYMENT_PACKAGES` stores base Xu; Launch Bonus and promo bonus are separate credit events.
- deduct: fixed and dynamic credit helpers exist.
- add: `add_credit()` and admin/manual deposit paths exist.
- refund: `refund_charged_credit()` exists; per-flow coverage still needs audit.

## Admin

- `/dashboard`: exists.
- `/stats`: exists.
- `/backup_db`: exists.
- `/pricing_admin`: exists, admin-only Pricing Engine V2 constants/formula.
- `/pending`, `/duyet`, `/tuchoi`, `/checkpayos`: exist.
- `/providers`: exists, admin-only, shows configured/missing only.
- `/costs`: exists, admin-only, summarizes Xu pricing and provider cost risk.
- `/sales_ready`: exists, admin-only, reports NOT READY or BETA READY only.
- `/payos_test_plan`: exists, admin-only, checklist for one real 10k payment test.
- `/mark_payos_test`: exists, admin-only, records PASS/FAIL/NOT_TESTED in `system_settings`.

## Provider & Sales Readiness

- `/providers`: added in Step 8; no key suffixes or secret values are printed.
- `/sales_ready`: Step 9 logic supports NOT READY, BETA READY, and SALES READY after PayOS real test PASS.
- `/costs`: added in Step 8 and updated in Step 10; documents `/film` 200/500/1,200 Xu, `/growth_ai` 120 Xu, `/campaign_report` 50 Xu, trial 200 Xu, free chat daily 20.
- `/payos_test_plan`: added in Step 8; guides real 10k payment validation.
- `/payos_test_plan`: now includes BETA50 real payment test steps.
- PayOS real payment test: still manual and required before public selling.
- API key setup docs: `docs/API_KEYS_SETUP.md`.
- Cost control docs: `docs/COST_CONTROL.md`.
- Sales readiness docs: `docs/SALES_READINESS_CHECKLIST.md`.
- Provider security audit: `docs/PROVIDER_SECURITY_AUDIT.md`.
- Current status: SALES READY only after admin runs `/mark_payos_test pass ...`; no automatic payment/order mutation is performed.

## Sales Hardening Status

- `/status`: hardened to compact public JSON.
- `/runtime`: protected by `OPERATOR_API_TOKEN` on the public FastAPI route.
- `/health`: remains public and compact.
- `system_settings`: added for non-secret operational flags such as PayOS real test state.
- `/beta_offer` and `/goi_beta`: user-facing beta package commands.
- Sales docs: `docs/BETA_SALES_PACKAGE.md`, `docs/FIRST_CUSTOMER_BETA_PLAN.md`, `docs/SALES_SCRIPT.md`.
- Safety: PayOS packages/webhook/billing callbacks untouched in Step 9.

## Pricing Engine V2 Status

- `/pricing` and `/banggia`: user-facing price table.
- `/pricing_admin`: admin-only formula/constants.
- `/film`: 200 Xu basic, 500 Xu pro, 1,200 Xu series.
- `/chat_pro`: Pro from 20 Xu, Deep from 50 Xu, long content +20 Xu/unit, cap 200 Xu.
- `/growth_ai`: 120 Xu.
- `/campaign_report`: 50 Xu for normal users; no data means no charge; export errors refund.
- MB helpers: `calculate_audio_cost`, `calculate_video_download_cost`, `calculate_mb_cost`.
- Safety: PayOS packages and payment callbacks untouched in Step 10.

## Chat AI Tier Status

- Normal chat: existing fair-use/legacy billing flow preserved.
- `/chat_pro`: explicit paid deep-answer command.
- `/models` and `/ai_models`: user-facing tier/model status.
- Router: Gemini/OpenAI configured paths only; Claude/Grok planned and not called.
- Refund: Chat Pro refunds if AI fails after Xu was charged.

## Not in current phase

- Copilot is for development workflow only.
- OpenLaw/OpenLaws legal automation is backlog, not production.

## Trial / Welcome Bonus

- New users receive 200 Xu trải nghiệm after deploy.
- Purpose: enough to test one `/film` Basic run.
- Existing users are not automatically topped up from 150 to 200 in this task.

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
- Cost: 200 Xu basic, 500 Xu pro, 1,200 Xu series.
- Scope: script, prompts, captions, CTA, hashtags, quality check.
- Platforms: Facebook, TikTok, YouTube by default.
- Direct-link context: `/film topic="..." link="https://..."` can use a pasted link as caption/CTA context.
- Output: Telegram preview plus Markdown file export.
- DB: `video_script_jobs`, `video_script_outputs`.
- Safety: no render, no auto publish, no browser automation.
- Remaining tests: real Telegram command, insufficient-Xu account, AI quota failure/refund, file export.

## Affiliate + Calendar Internal Status

- `/addlink`, `/links`, `/campaign`, `/addcal`, `/calendar`: admin/internal only after customer-scope cleanup.
- Customer-facing affiliate vault/calendar is backlog, not current production scope.
- Customers can paste a product/link directly into `/film`; TOAN AAS does not expose a public affiliate vault.
- `/dashboard`: includes video script, active campaign, affiliate link, and calendar counters.
- DB: reused `affiliate_links`, `campaigns`, `content_calendar`.
- Safety: no PayOS/billing changes, no auto publish, no render API.

## Manual Publish + Performance Loop Internal Status

- `/publish_done`, `/performance_add`, `/performance_report`, `/posts`, `/growth_loop`: admin/internal only after customer-scope cleanup.
- Customer-facing publish tracking is disabled by default.
- `/publish_done queue=...` and `/publish_done job=...`: existing admin/operator flow preserved.
- `/performance_add job=...`: existing admin/operator performance flow preserved.
- `/performance_report`: aggregates manual posts by platform and top posts.
- `/posts`: lists recent manually recorded posts.
- `/growth_loop`: admin/internal rule-based recommendations from manual metrics.
- Customer access to `/growth_loop` is disabled; customers should use `/growth_ai` or `/film`.
- `/growth_ai`: AI Growth Coach deep analysis, 120 Xu for normal users, admin/VIP free.
- `/campaign_report`: TXT/CSV report export, 50 Xu for normal users.
- `/export_report`: alias for `/campaign_report`.
- `/growth_loop manual=1`: admin can view manual loop; admin default remains operator growth loop.
- DB: `published_posts`, `manual_performance_events`, `growth_recommendations`.
- Dashboard: includes manual publish/performance/revenue counters.
- Safety: no social API calls, no auto publish, no browser automation, no render API.

## Growth Coach & Reports

- `/growth_loop`: admin/internal rule-based loop, fast, no AI charge.
- `/growth_ai`: Gemini/OpenAI text fallback through existing `AgentGemini.chat`.
- `/growth_ai` pricing: 120 Xu; no charge when no data; refund on AI error.
- `/campaign_report`: exports TXT or CSV using owner-scoped manual data.
- Report export: temp file only, deleted after Telegram send.
- Local route smoke after Step 7: PASS for `/`, `/landing`, `/health`, `/banner.png`.

## Future Admin-First Pipeline Status

- TOAN AAS Admin Trend-to-Video-to-Publish Pipeline is a future backlog item, not current customer scope.
- Current bot V1 only gives customers AI tools and content/video packs for self-posting.
- Trend finder, AI video builder, publish queue, platform account manager and ads assistant stay admin/internal or off by default.
- Required future flags: `trend_finder` admin-only, `ai_video_builder` admin-only, `publish_workflow` off by default, `admin_publish` admin-only, `customer_publish` off by default, `auto_publish` off by default, `ads_assistant` off by default.
- No customer social account connection, no customer auto publish and no customer ads management in Stable Revenue Bot.

## Live Website Status

- `/`: PASS before Step 6; serves TOAN AAS landing HTML.
- `/landing`: PASS before Step 6; serves TOAN AAS landing HTML.
- `/health`: PASS before Step 6; returns JSON status.
- `/banner.png`: PASS before Step 6; image route works.
- `/LOGO.png`: PASS before Step 6; logo route works.

## Bot QA Status

- `/start`: updated in Step 6; needs live Telegram smoke test after deploy.
- `/menu`: uses same surface as `/start`; needs live Telegram smoke test.
- `/help`: added and registered; compile/pytest/import PASS.
- `/commands`: alias to `/help`; compile/pytest/import PASS.
- `/profile`: registered.
- `/naptien`: registered; PayOS logic untouched in Step 6.
- `/film`: registered in local `bot.py`; needs live AI/Xu test.
- Affiliate commands: `/addlink`, `/links`, `/campaign`, `/addcal`, `/calendar` registered and guarded admin/internal.
- Performance commands: `/publish_done`, `/performance_add`, `/performance_report`, `/posts`, `/growth_loop` registered and guarded admin/internal.
- Growth/report commands: `/growth_ai`, `/campaign_report`, `/export_report` registered in local `bot.py`.
- Admin commands: `/dashboard`, `/admin`, `/stats`, `/pending`, `/duyet`, `/tuchoi`, `/add`, `/setvip`, `/backup_db`, `/runtime`, `/checkpayos`, `/telegram_takeover`.

## Ready For Next Revenue Step?

- Status: YES after Railway deploy passes live Telegram smoke test.
- Blockers:
  1. Real Telegram verification for `/film` plus non-admin internal locks on `/addlink`, `/publish_done`, `/performance_report`.
  2. Real PayOS 10k payment test.
  3. Railway Volume persistence confirmation.

## Head Brain Control Status

- `/head_brain`: registered admin command for the control cockpit.
- `/head_run`: registered admin command for safe preview/run cycles.
- `/tao_video` and `/boss_video`: registered admin aliases for one-shot video order creation through the existing head-brain/operator launch pipeline.
- `POST /api/operator/video-order`: machine-readable video order endpoint for Claude/n8n; returns worker/review/approve/publish/tracking handoff, batch work orders, submit/upload URLs and a run card while keeping auto-publish off.
- `/operator_contract`: registered admin command for the AI commander contract.
- `/goal_audit`: registered admin command for completion and blocker audit.
- Head brain default rule: create plans/jobs/tasks and stop at review/approve/publish gates.
- Auto publish remains disabled unless a separate task explicitly enables an official adapter.
- Operating doc: `docs/HEAD_BRAIN_OPERATING_SYSTEM.md`.
