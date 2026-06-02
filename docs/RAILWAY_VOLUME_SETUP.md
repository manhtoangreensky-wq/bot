# Railway Volume Setup

## Warning

If TOAN AAS uses SQLite on Railway without a persistent volume or backup, a redeploy or runtime storage reset can lose the database file depending on the deployment/storage configuration.

## Manual Checks

1. Check whether the Railway service has a Volume attached.
2. Check which path the SQLite database uses.
3. Check whether that path is inside the mounted volume.
4. Redeploy once in a controlled test and confirm the DB file remains.
5. Confirm there is a backup plan for recent PayOS orders, user credits, and bill approvals.

## Current Code State

Current `bot.py` uses:

```text
DB_FILE = "toandaas_system.db"
```

This task does not change `DB_FILE` logic. Do not assume `DB_FILE=/data/toandaas_system.db` works until a separate approved task adds and tests ENV support.

## Option A: Short Term

- Configure a Railway Volume.
- In a later approved code task, support `DB_FILE` from ENV.
- Set `DB_FILE=/data/toandaas_system.db` only after code supports it.
- Copy the current SQLite database into the volume path.
- Back up the DB daily.

## Option B: Medium Term

- Move to managed PostgreSQL.
- Create a tested SQLite-to-PostgreSQL migration.
- Keep SQLite backup for at least 30 days.
- Keep PayOS order and credit ledger history intact.

## Do Not Do In This Task

- Do not rewrite database logic.
- Do not migrate automatically.
- Do not change PayOS logic.
- Do not drop or rename tables.
