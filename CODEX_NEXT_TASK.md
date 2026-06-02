# CODEX NEXT TASK

## Current Instruction

Do not start Video Factory implementation yet.

The current approved task is documentation and stabilization only.

## Completed In This Documentation Pass

- Compile check must pass.
- Create foundation docs.
- Do not modify `bot.py` unless compile fails.
- Do not rewrite architecture.
- Do not add new production logic.

## Next Task Requiring Approval

`TASK 2 - Add safe migration for Video Factory tables`

## TASK 2 Draft Scope

- Read `AGENTS.md`.
- Run `python -m py_compile bot.py`.
- Inspect existing `init_db()`.
- Identify which Video Factory tables already exist.
- Add only missing columns/tables using idempotent SQL.
- Test against a temporary SQLite database.
- Do not change Telegram handlers.
- Do not change PayOS.
- Do not change Railway entrypoint.

## TASK 2 Exit Criteria

- `python -m py_compile bot.py` passes.
- `pytest -q` passes if tests exist.
- Temporary DB migration smoke test passes.
- No existing table is dropped.
- No existing column is renamed.
