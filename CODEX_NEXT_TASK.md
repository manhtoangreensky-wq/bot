# CODEX NEXT TASK

## Current Instruction

Do not start the next task without approval.

The current completed scope is stabilization docs plus a safe `/health` endpoint.

## Next Task Proposal A: Support `DB_FILE` ENV Safely

- Read `AGENTS.md`.
- Run `python -m py_compile bot.py`.
- Keep default `toandaas_system.db`.
- Allow `DB_FILE` from ENV only after reviewing Railway Volume path.
- Do not move data automatically.
- Document migration steps from old DB path to volume DB path.

## Next Task Proposal B: Extract Config

- Create `app/core/config.py`.
- Do not rename ENV.
- Keep `bot.py` import-compatible.
- Do not hardcode secrets.
- Run `python -m py_compile bot.py` and `pytest -q`.

## Next Task Proposal C: Safe Video Factory Schema Audit

- Inspect existing `init_db()`.
- Identify which Video Factory tables already exist.
- Add only missing tables/columns using idempotent SQL.
- Test against a temporary SQLite database.
- Do not change Telegram handlers.
- Do not change PayOS.
- Do not change Railway entrypoint.
