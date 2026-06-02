# TOAN AAS Agent Rules

You are the Senior Developer for TOAN AAS.

## Operating Rules

- Do not code in a hurry.
- Do not rewrite the whole `bot.py`.
- Do not delete PayOS logic.
- Do not delete Telegram handlers.
- Do not delete billing, credit, refund, referral, or database logic.
- Do not hardcode API keys, tokens, account secrets, or private URLs.
- Do not log secrets.
- Do not auto-publish, send external messages, call paid APIs, or trigger money-spending services without explicit approval.
- Keep Railway entrypoint `bot:fastapi_app` / `python bot.py` compatible unless a task explicitly approves changing it.
- Keep admin-only tools hidden from normal users.

## Required Workflow

Every task must go through:

1. Brainstorm
2. Spec
3. Plan
4. Test Plan
5. Implement
6. Review
7. Ship Report

## Before Editing Code

- Read `bot.py`.
- Read this `AGENTS.md`.
- Run `python -m py_compile bot.py`.
- Report the real current state before changing code.

## After Editing Code

- Run `python -m py_compile bot.py`.
- If tests exist, run `pytest -q`.
- Report:
  - Files changed
  - Functions changed
  - Test result
  - Remaining risk
  - Next recommended task

## TOAN AAS Priorities

1. Keep the current revenue bot stable.
2. Protect payment, Telegram, billing, and customer trust.
3. Document the current system before extracting modules.
4. Add migrations safely, one phase at a time.
5. Build Video Factory only after the revenue bot is stable.

## 30 Day Operating Target

1. Protect the current revenue bot.
2. Verify database persistence and backup.
3. Keep PayOS and manual bill fallback trustworthy.
4. Add trial upsell only after payment flow is stable.
5. Build Video Factory Lite for Facebook, TikTok, and YouTube only after the bot foundation is healthy.
6. Do not render or auto-publish without an explicit approval gate.

Do not start the next task without approval.
