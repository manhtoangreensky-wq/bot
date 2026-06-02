# TOAN AAS Roadmap

## Stage 0: Stabilize Revenue Bot

- Keep Telegram `/start`, `/profile`, `/naptien`, manual bill, and admin dashboard stable.
- Keep PayOS verification and duplicate-order protection stable.
- Keep credit refunds correct for failed media tasks.
- Keep admin-only tools hidden from normal users.
- Keep FastAPI health/runtime endpoints available for production diagnosis.

## Stage 1: Foundation Documentation

- Add `AGENTS.md`.
- Add architecture and current-state docs.
- Add extraction plan.
- Add database foundation plan.
- Add revenue checklist.
- Add Video Factory plan without adding new runtime logic.

## Stage 2: Safe Database Migration

Next approved task:

`TASK 2 - Add safe migration for Video Factory tables`

Rules:

- Do not drop old tables.
- Do not rewrite existing DB helpers.
- Add idempotent migrations only.
- Test with a temporary SQLite database.

## Stage 3: Modular Extraction

- Extract config/env first.
- Extract database helpers second.
- Extract PayOS third.
- Extract AI providers fourth.
- Extract Telegram command registration later.

## Stage 4: Operator / Video Factory MVP

- Standardize campaign and affiliate data.
- Standardize job/task/asset lifecycle.
- Add worker upload and review gates.
- Add publish queue and performance events.
- Keep auto-publish disabled unless platform credentials and admin approval are present.

## Stage 5: AI Head Brain

- Telegram admin issues goals.
- The operator converts goals into tasks.
- Claude/Gemini/n8n/worker tools execute tasks.
- Admin reviews outputs.
- Only approved outputs enter publish queue.

## Stage 6: Scale

- Track revenue per affiliate link.
- Rank channels and campaigns by revenue, clicks, orders, and conversion.
- Remix winning formats.
- Reduce manual steps only after stable measurement.
