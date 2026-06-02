# FOUNDATION AUDIT REPORT

## 1. Compile status

- `python -m py_compile bot.py`: PASS before changes.
- `python -m py_compile bot.py`: PASS after foundation code changes.

## 2. Current bot status

- FastAPI app name: `TOAN AAS V15.2`
- Telegram bot startup: FastAPI lifespan builds the Telegram app when `TELEGRAM_TOKEN` is configured. If token/builder fails, FastAPI remains alive for diagnostics.
- PayOS dynamic QR: Present. Package callbacks still use `pkg|` and were not changed.
- Billing/xu: Present through `users`, `credit_events`, `transactions`, PayOS orders, manual bill approval and refunds.
- AI providers: Chat AI has Gemini/OpenAI availability checks. `/health` only checks whether at least one AI key is configured; it does not call external AI APIs.
- Media services: Voice/audio/image/downloader flows are present. Provider callbacks still use `prov|` and were not changed.
- Menu V2: Present with grouped TOAN AAS menu and admin-only sections.
- Landing/index: Present, branded TOAN AAS, uses `LOGO.png`, and public content hides provider/tool names.

## 3. Current DB

- DB_FILE current value: `DB_FILE = _env("DB_FILE", "toandaas_system.db")`
- SQLite path: default `toandaas_system.db`; Railway can set `DB_FILE=/data/toandaas_system.db` after creating a persistent volume.
- Có đọc từ ENV chưa: Yes.
- Có Railway Volume docs chưa: Yes, see `docs/RAILWAY_VOLUME_SETUP.md`.
- Tables hiện có:
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
- Risk: SQLite is still production-risky on Railway unless DB file is inside a persistent volume and backups are tested.

## 4. Critical risks

- SQLite persistence: Need manual verification on Railway Volume.
- Backup: `/backup_db` now exists for admin manual backup, but daily automated off-platform backup is not implemented.
- Health: `/health` exists and checks local DB/config only.
- PayOS checksum: Webhook now rejects auto-credit if `PAYOS_CHECKSUM_KEY` is missing.
- Admin alert: Existing admin alerts remain. No new scheduled monitor was added.
- Audit log: Foundation table/helper added and applied to PayOS success, admin add credit, manual bill approval/rejection, VIP update and backup command.
- Feature flags: Foundation table/helper added and seeded.
- System events: Foundation table/helper added. PayOS paid order emits `payment.paid`.

## 5. Recommendation

- Task nên làm tiếp: Extract `config.py` safely only after Railway Volume/backup is manually verified.
- Không nên làm gì: Do not build big Video Factory, PostgreSQL migration, auto-publish, Celery/Redis or paid video APIs until DB persistence and backup are proven.
- Manual check cần admin làm:
  - Confirm Railway Volume exists.
  - Set `DB_FILE=/data/toandaas_system.db` only after copying/backup plan is ready.
  - Call `/health` on Railway and confirm `db_ok=true`.
  - Run `/backup_db` on Telegram as admin.
  - Redeploy once and verify users/credits/orders remain.
  - Test one real PayOS payment and one manual bill approval.

