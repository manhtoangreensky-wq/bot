# Current State

## Version

- App version in code: `TOAN DAAS V15.2`
- Main file: `bot.py`
- Current line count: `32609`

## Compile Status

- `python -m py_compile bot.py`: PASS before this documentation pass.

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

## Current Gaps / Not Fully Verified

- Railway production public domain is currently not reachable from local checks.
- Operator/Video Factory tables and commands exist, but the full automatic workflow is not verified end-to-end.
- Real video generation API integration is not yet proven.
- Auto-publish for TikTok/YouTube/Instagram/Facebook is not proven end-to-end.
- n8n/Claude worker execution is planned/configurable but not proven as a live closed loop.
- Affiliate postback exists generically, but per-network parsers and revenue attribution still need hardening.
- The current `bot.py` remains a very large single-file system and should be extracted gradually.
