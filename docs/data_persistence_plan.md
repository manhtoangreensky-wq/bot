# TOAN AAS Data Persistence Plan

## Current DB Status

TOAN AAS currently uses SQLite by default.

- Default mode: `DATA_PERSISTENCE_MODE=sqlite`
- Default file: `DB_PATH=toandaas_system.db`
- Backward compatible file variable: `DB_FILE`
- External database placeholder: `DATABASE_URL`

The bot keeps user balance, payment/top-up records, free trial records, member tier data, ShopAIKey jobs, billing events, provider status, settings, audit logs, and backup evidence in the database.

## Railway SQLite Risk

SQLite is acceptable for early MVP operation only if the file is stored on persistent storage. A normal relative SQLite file on Railway can be lost when a deploy/rebuild/container replacement happens.

Risk signs:

- `DB_FILE` is a relative path like `toandaas_system.db` on Railway.
- No Railway Volume path is detected.
- DB file is missing or empty before `init_db`.
- `REQUIRE_PERSISTENT_DB=true` is not enabled for production hard guard.

Use `/data_status` after deploy to verify:

- DB mode
- DB path
- DB exists and size
- table counts
- startup backup status
- data loss risk warnings

## Railway Volume Option

Recommended MVP path:

1. Run `/backup_db` before any move.
2. Create a Railway Volume for the bot service.
3. Mount it at a stable path such as `/data`.
4. Copy the current DB into the volume.
5. Set:

```env
DATA_PERSISTENCE_MODE=sqlite
DB_PATH=/data/toandaas_system.db
DB_FILE=/data/toandaas_system.db
REQUIRE_PERSISTENT_DB=true
DB_STARTUP_BACKUP_ENABLED=true
```

6. Redeploy.
7. Run `/data_status`.
8. Confirm DB size and table counts did not reset.

Do not switch `DB_FILE` before the current production DB has been backed up and copied.

## Postgres Option

Postgres is the stronger long-term option when TOAN AAS scales beyond early bot MVP usage. Migration should be a separate planned task.

Rules for a future Postgres migration:

- Export SQLite first.
- Verify table mapping.
- Run dry-run migration.
- Validate balances, PayOS orders, trial grants, ShopAIKey jobs, billing events, and credit ledger counts.
- Keep SQLite backup until production has been verified.

## Preserved Tables

Do not delete or reset these categories:

- `users`
- `credit_events`
- `transactions`
- `pending_deposits`
- `payos_orders`
- `payos_processed`
- `trial_grants`
- `trial_bonus_claims`
- `member_tier_overrides`
- `member_tier_rewards`
- `promotion_codes`
- `promotion_redemptions`
- `promo_usage_periods`
- `gift_redemptions`
- `gift_assignments`
- `launch_bonus_redemptions`
- `shopaikey_jobs`
- `shopaikey_billing_events`
- `provider_freeze_state`
- `system_settings`
- `system_flags`
- `feature_flags`
- `audit_logs`

## Backup Before Migration

When `DB_STARTUP_BACKUP_ENABLED=true`, startup creates a local copy before schema migration if an existing non-empty SQLite file is present:

`backups/toandaas_system_YYYYMMDD_HHMMSS_before_migration.db`

Retention defaults to 20 newest backups. Backups are ignored by git and must not be public.

If backup fails, `/data_status` reports a warning. Do not run risky migration work until backup is fixed.

## Safe Migration Rules

Allowed:

- `CREATE TABLE IF NOT EXISTS`
- `CREATE INDEX IF NOT EXISTS`
- `ALTER TABLE ... ADD COLUMN ...` after checking it is additive
- `INSERT OR IGNORE` seed/default records

Blocked unless explicitly allowed:

- `DROP TABLE`
- `DROP DATABASE`
- `TRUNCATE`
- bulk delete/reset of `users`, `payos_orders`, `credit_events`, trial records, or ShopAIKey jobs
- resetting user balances

Keep `DB_ALLOW_DESTRUCTIVE_MIGRATION=false` in production.

## No Reset Rules

- Do not reset Xu balances.
- Do not delete PayOS/top-up history.
- Do not re-grant free trial by deleting trial records.
- Do not delete ShopAIKey job/billing records.
- Do not delete provider status/settings/audit evidence.
- Do not commit `.env`, `.db`, backup files, logs, or media test files.

## Operations Checklist

Before deploys that touch DB schema:

1. Run `/data_status`.
2. Run `/backup_db` if DB is small enough for Telegram backup.
3. Confirm startup backup is enabled.
4. Deploy.
5. Run `/data_status` again.
6. Compare users, payments, credits, trial, ShopAIKey jobs, and settings counts.

If counts unexpectedly reset, stop feature work and restore from backup before accepting real traffic.
