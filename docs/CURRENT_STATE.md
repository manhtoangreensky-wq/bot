# Current State

## Version

- App version in code: `TOAN AAS V15.2`
- Main file: `bot.py`
- Current line count after this pass: `33097`

## Compile Status

- `python -m py_compile bot.py`: PASS during TASK 1 audit.

## Business Scope From Latest Direction

- First 30 days: foundation plus early revenue.
- Primary money platforms: Facebook, TikTok, YouTube.
- Secondary platforms: Instagram, Threads, OnlyFans, Website.
- Do not prioritize HR, Tax, or Travel modules during the first 90 days.
- Device Ops should wait, or stay Lite until there is a real paying customer.
- Do not expand the system too broadly before the revenue bot is stable.

## Environment Variables In Use

Current `bot.py` reads these ENV names:

- `TELEGRAM_TOKEN`
- `BOT_TOKEN`
- `ADMIN_ID`
- `RAILWAY_GIT_COMMIT_SHA`
- `GIT_COMMIT_SHA`
- `SOURCE_VERSION`
- `RAILWAY_DEPLOYMENT_ID`
- `RENDER_SERVICE_ID`
- `DEPLOYMENT_ID`
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
- `DEEPGRAM_API_KEY`
- `DEEPL_API_KEY`
- `FISH_AUDIO_KEY`
- `REMOVEBG_API_KEY`
- `CUTOUT_API_KEY`
- `PAYOS_CLIENT_ID`
- `PAYOS_API_KEY`
- `PAYOS_CHECKSUM_KEY`
- `RAPIDAPI_KEY`
- `RAPIDAPI_HOST`
- `COBALT_API_URL`
- `COBALT_API_KEY`
- `PORT`
- `BOT_USERNAME`
- `TELEGRAM_UPDATE_MODE`
- `TELEGRAM_FORCE_POLLING`
- `TELEGRAM_WEBHOOK_SECRET`
- `TELEGRAM_TAKEOVER_INTERVAL_SECONDS`
- `TELEGRAM_WEBHOOK_PATH`
- `LEAD_WEBHOOK_SECRET`
- `OPERATOR_API_TOKEN`
- `AFFILIATE_POSTBACK_TOKEN`
- `OPERATOR_UPLOAD_DIR`
- `MAX_OPERATOR_UPLOAD_MB`
- `META_GRAPH_VERSION`
- `DB_FILE`
- `REFERENCE_VIDEO_DIR`
- `MANUAL_BANK_NAME`
- `MANUAL_BANK_CODE`
- `MANUAL_BANK_ACCOUNT`
- `MANUAL_BANK_OWNER`
- `KLING_API_KEY`
- `RUNWAY_API_KEY`

Commented future ENV references exist for `CLAUDE_API_KEY`, `GROQ_KEY`, and other AI providers, but they are not active runtime config in the current code.

## FastAPI Routes

Core routes currently include:

- `GET /`
- `GET /health`
- `GET /runtime`
- `POST /api/telegram/takeover`
- `POST <TELEGRAM_WEBHOOK_PATH>`
- `GET /landing`
- `GET /LOGO.png`
- `GET /logo.png`
- `GET /r/{affiliate_id}`
- `POST /api/affiliate/postback`
- `GET /api/affiliate/postback`
- `POST /lead`
- `POST /webhook/payos`

The current code also includes many `/api/operator/...` routes for worker intake, command center, Video Factory planning, task upload, asset upload, publish queue, affiliate reporting, and performance tracking.

## Telegram Commands

Required current revenue-bot commands are present:

- `/start`
- `/profile`
- `/naptien`
- `/thucong`
- `/tools`
- `/mmo`
- `/ref`
- `/gopy`
- `/add`
- `/admin_gopy`
- `/duyet`
- `/tuchoi`
- `/pending`
- `/stats`
- `/dashboard`
- `/setvip`

Additional admin/operator commands are already registered, including:

- `/runtime`
- `/telegram_status`
- `/telegram_takeover`
- `/campaign_new`
- `/campaigns`
- `/campaign_preset`
- `/video_plan`
- `/video_job`
- `/channel_add`
- `/channels`
- `/affiliate_add`
- `/affiliate_import`
- `/affiliates`
- `/operator`
- `/operator_dashboard`
- `/head_brain`
- `/head_run`
- `/make_video`
- `/trend_search`
- `/film_series`
- `/film_review`
- `/film_rewrite`
- `/film_approve`
- `/reference_analyze`
- `/video_work_orders`
- `/worker_intake`
- `/publish_queue`
- `/performance_add`

These operator commands should remain admin-only unless explicitly reviewed.

## Callback Handlers

Current callback handlers include:

- Provider choice: `^prov|`
- Package choice: `^pkg|`
- Video job callback: `^job|`
- Pipeline callback: `^pipe|`
- Trend callback: `^trend|`
- Creative callback: `^creative|`
- Task callback: `^task|`
- Operator menu callback: `^opmenu|`

## Database Tables

Current `init_db()` creates these tables:

- `users`
- `feedback`
- `pending_deposits`
- `transactions`
- `payos_processed`
- `payos_orders`
- `credit_events`
- `leads`
- `referrals`
- `campaigns`
- `video_jobs`
- `social_channels`
- `affiliate_links`
- `content_calendar`
- `production_jobs`
- `operator_missions`
- `production_assets`
- `creative_variants`
- `production_manifests`
- `production_tasks`
- `performance_events`
- `tool_events`
- `reference_videos`
- `trend_candidates`
- `publish_queue`
- `audit_logs`
- `system_events`
- `feature_flags`

## Functions That Appear Stable

- PayOS dynamic QR path exists.
- Manual bill fallback exists.
- Credit events exist.
- Referral table and referral-related logic exist.
- Free chat daily / dynamic credit logic exists.
- Gemini/OpenAI fallback exists.
- Deepgram transcription exists.
- Voice flow exists with premium/fallback pattern.
- Image background removal exists with premium/fallback pattern.
- Lead form endpoint exists.
- Admin dashboard/stats commands exist.

## PayOS / Billing State

- PayOS config is read from `PAYOS_CLIENT_ID`, `PAYOS_API_KEY`, and `PAYOS_CHECKSUM_KEY`.
- PayOS webhook route exists at `POST /webhook/payos`.
- Signature verification function exists: `verify_payos_signature`.
- Paid order processing function exists: `process_payos_paid_order`.
- Duplicate order tracking table exists: `payos_processed`.
- PayOS order table exists: `payos_orders`.
- Manual bill fallback exists through `/thucong`, `/duyet`, `/tuchoi`, and `pending_deposits`.
- Credit ledger exists through `credit_events`.
- Do not change PayOS logic without a focused payment test plan.

## AI State

- Main chat provider class exists: `AgentGemini`.
- Gemini key: `GEMINI_API_KEY`.
- OpenAI fallback key: `OPENAI_API_KEY`.
- Deepgram transcription class exists: `AgentDeepgram`.
- Deepgram key: `DEEPGRAM_API_KEY`.
- Future high-end providers such as Claude/Groq are mentioned in comments but not active runtime providers in the current code.

## Media State

- Voice uses a premium-first/fallback-second pattern:
  - Fish Audio HD when `FISH_AUDIO_KEY` is configured.
  - Edge TTS fallback through `edge_tts`.
- Image background removal uses:
  - RemoveBG HD when `REMOVEBG_API_KEY` is configured.
  - Cutout.pro fallback when `CUTOUT_API_KEY` is configured.
- Downloader class exists: `AgentDownloader`.
- Cobalt config exists through `COBALT_API_URL` and `COBALT_API_KEY`.
- Failed paid media tasks should preserve refund behavior.

## Updated by Codex: Stabilize + Health Check Pass

| Area | Current State | Risk | Recommendation |
| --- | --- | --- | --- |
| Version | `APP_VERSION = TOAN AAS V15.2` | Public brand has been reworked to TOAN AAS. | Keep internal legacy identifiers stable unless a focused migration is approved. |
| Entrypoint | `bot.py`, FastAPI object `fastapi_app` | Monolith is large; one syntax error can crash all runtime. | Extract gradually, starting with config and DB helpers. |
| Routes | `GET /`, `GET /runtime`, `GET /health`, Telegram webhook, landing, lead, affiliate, operator APIs, PayOS webhook. | Many operator routes exist but are not fully verified end to end. | Keep admin/API-token guards and test route groups in phases. |
| Database | SQLite file defaults to `toandaas_system.db`; `DB_FILE` ENV can point to Railway Volume. | Railway storage can be ephemeral without volume. | Configure Railway Volume and verify backup before relying on production SQLite. |
| PayOS | Dynamic QR, webhook signature verification, duplicate table, manual fallback. | Real payment still needs production verification. | Do not change PayOS without focused tests. |
| AI | Gemini and OpenAI clients exist; Deepgram exists; media fallback pattern exists. | API quota/key failures can interrupt paid flows. | Preserve refund behavior and add clear admin alerts for quota failures. |
| Media | Voice, image background removal, downloader paths exist. | Some tool integrations still need real-world test. | Test paid-first/free-fallback behavior one tool at a time. |
| Video Factory | Operator/video/affiliate/publish foundations exist. | Not a proven automatic production system yet. | Start with script/output generation, review gate, then manual publish. |
| Device Ops | Not in current near-term runtime scope. | Expanding too early dilutes revenue bot work. | Keep as Lite plan only until there is a paying customer. |

## Current Gaps / Not Fully Verified

- Railway production public domain is currently not reachable from local checks.
- SQLite persistence on Railway is risky unless `DB_FILE` points to a persistent volume.
- `/health` now exists and reports DB/config status without calling external APIs; production monitoring still needs manual setup.
- `/backup_db` exists for admin manual DB backup, but automated off-platform backup is not implemented.
- `audit_logs`, `system_events`, and `feature_flags` foundations exist.
- Operator/Video Factory tables and commands exist, but the full automatic workflow is not verified end-to-end.
- Real video generation API integration is not yet proven.
- Auto-publish for TikTok/YouTube/Instagram/Facebook is not proven end-to-end.
- n8n/Claude worker execution is planned/configurable but not proven as a live closed loop.
- Affiliate postback exists generically, but per-network parsers and revenue attribution still need hardening.
- The current `bot.py` remains a very large single-file system and should be extracted gradually.

## TASK 1 Conclusion

The current codebase is more than a simple revenue bot: it already contains operator, affiliate, publish, and Video Factory foundations. The near-term priority should still be stability and revenue, not adding more broad modules.

The next approved task should be manual Railway persistence verification: configure Railway Volume, set `DB_FILE=/data/toandaas_system.db`, test `/health`, run `/backup_db`, then redeploy and verify data remains.
