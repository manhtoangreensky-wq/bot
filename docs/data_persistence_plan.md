# TOAN AAS Data Persistence Plan

## Current SQLite Mode

TOAN AAS still uses SQLite for the revenue-bot MVP. SQLite is acceptable only when the database file is stored on persistent storage.

Production target:

```env
DATA_PERSISTENCE_MODE=sqlite
DB_PATH=/data/toandaas_system.db
DB_FILE=/data/toandaas_system.db
DB_BACKUP_DIR=/data/backups
REQUIRE_PERSISTENT_DB=true
DB_STARTUP_BACKUP_ENABLED=true
DB_ALLOW_DESTRUCTIVE_MIGRATION=false
```

`DB_PATH` is the primary path. `DB_FILE` remains only for backward compatibility with older code/docs.

## Why Railway Redeploy Can Lose SQLite Data

A normal relative file such as `toandaas_system.db` can live inside the temporary container filesystem. Redeploy/rebuild/container replacement can remove that file and make balances, PayOS records, trial grants, ShopAIKey jobs, billing events and audit history appear reset.

Risk signs:

- `DB_PATH` is missing or relative, for example `toandaas_system.db`.
- Railway is running without a Volume mounted at `/data`.
- `/data_status` shows `Persistent path candidate: no`.
- `/data_status` shows `Data loss risk: YES` or `ERROR`.

## Railway Volume Setup

1. Run `/data_status` and `/backup_db`.
2. In Railway, create a Volume for the bot service.
3. Mount the Volume at `/data`.
4. Set:

```env
DB_PATH=/data/toandaas_system.db
DB_BACKUP_DIR=/data/backups
REQUIRE_PERSISTENT_DB=true
```

5. Redeploy the correct bot service.
6. Run `/data_status`.
7. Confirm:
   - DB path: `/data/toandaas_system.db`
   - DB exists: yes
   - DB writable: yes
   - Backup dir writable: yes
   - Persistent path candidate: yes
   - Data loss risk: `NO` or `LOW`

## Safe Copy From Old Local DB

On startup, if `DB_PATH=/data/toandaas_system.db` does not exist and the old `./toandaas_system.db` exists, the bot copies the old DB to `/data/toandaas_system.db` one time.

Rules:

- Never overwrite an existing `/data/toandaas_system.db`.
- Never delete the old local DB during startup.
- Log the event as `migrated local sqlite db to persistent path`.
- If neither DB exists, a new DB is created and `/data_status` warns that this may be unexpected.

## Startup Backup

If an existing DB file is present and `DB_STARTUP_BACKUP_ENABLED=true`, startup creates:

`/data/backups/toandaas_system_YYYYMMDD_HHMMSS_startup.db`

Retention keeps the newest 20 startup backups by default.

If backup creation fails, do not run destructive migration work. Production should keep:

```env
DB_ALLOW_DESTRUCTIVE_MIGRATION=false
```

## No Reset Rules

Do not drop, delete or reset these data groups:

- users and Xu balances
- PayOS/top-up/manual bill records
- credit ledger/events
- free trial/anti-spam records
- member tier and rewards
- promo/gift/referral history
- ShopAIKey jobs and billing events
- provider status/freeze records
- system settings/flags
- audit logs and backup evidence

The bot must not use `DROP TABLE`, bulk `DELETE`, or balance reset migrations for production data.

## Verification

After deploy, run:

- `/runtime`
- `/data_status`
- `/providers`

Expected production result:

- `DB mode: sqlite`
- `DB path: /data/toandaas_system.db`
- `Backup dir: /data/backups`
- `Persistent path candidate: yes`
- `Data loss risk: NO` or `LOW`
- Existing user/payment/top-up counts did not reset.

## Future Migration

PostgreSQL/Supabase is a later migration path after the bot is stable on persistent SQLite. That must be a separate task with export, dry-run import, table count validation, balance validation and rollback backup.
