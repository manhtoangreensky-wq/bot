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

## Branch, PR, And Release Discipline

- Use one main branch for each large work cluster. Do not create small branches or PRs for related buttons, copy changes, back routes, or regressions in the same flow.
- Fix small issues discovered in a flow on that flow's existing branch.
- Push only after the whole work cluster is complete and the full relevant test suite passes.
- Create a PR only when the user explicitly requests it or the task is genuinely complete and ready for review.
- Do not merge or deploy piecemeal.
- If `main` changes, rebase or merge `main` into the current branch when safe; do not create another branch without a real isolation need.
- Use a separate branch when isolating dangerous work in PayOS, wallet/Xu, payment webhooks, DB migrations, provider internals, or a large export-core rewrite.
- Keep current video-flow regressions together on one P0 branch. Start multi-scene work only on its dedicated branch after the video-flow regression cluster is complete.

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

## Owner-Governed Codex for TOAN AAS

Before doing engineering work in this repository:

- Apply `owner-governed-codex`.
- Read project-specific approved knowledge only when relevant.
- One task / one branch / one PR unless Owner specifies otherwise.
- merged != deployed != LIVE.
- No provider calls in regression tests.
- No fake success.
- No wallet mutation unless explicitly authorized.
- PayOS/wallet, DB schema, provider ENV and unrelated modules are protected.
- Video Edit is protected from Video creation tasks unless explicitly authorized.
- SubDub and Music/Suno are protected unless task explicitly owns them.
- Record BASE SHA, HEAD SHA, files changed and test evidence.
- New failures introduced must equal 0 unless Owner explicitly accepts otherwise.
- No deploy without Owner approval.

Do not hardcode current SHAs or time-sensitive provider status in this file. Do not copy long memory into `AGENTS.md`.
