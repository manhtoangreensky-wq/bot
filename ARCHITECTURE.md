# TOAN AAS Architecture

## Current Shape

TOAN AAS currently runs as a single large `bot.py` application:

- FastAPI web server
- Telegram bot lifecycle through FastAPI lifespan
- SQLite database helpers
- PayOS dynamic QR and webhook handling
- Manual bill fallback
- Credit ledger and refund handling
- Gemini/OpenAI chat fallback
- Deepgram transcription
- Fish Audio / Edge TTS voice flow
- RemoveBG / Cutout image background removal
- Downloader tooling
- Lead form endpoint
- Admin dashboard commands
- Operator and Video Factory planning surfaces

The system is operationally centered on `bot.py`. Module extraction should be gradual.

## Runtime

- Local/production entrypoint: `python bot.py`
- FastAPI app object: `fastapi_app`
- Railway port: `PORT`
- Deployment config:
  - `Dockerfile`
  - `railway.json`
  - `requirements.txt`

## Core Domains

### Revenue Bot

Revenue Bot covers:

- User credits
- Dynamic costs
- Discounts
- Referrals
- PayOS orders and webhook
- Manual transfer bill approval
- Admin stats/dashboard
- Lead capture

### AI Services

AI services currently live inside `bot.py`:

- Gemini primary chat
- OpenAI fallback
- Deepgram audio transcription
- Fish Audio premium voice path
- Edge TTS fallback voice path
- RemoveBG premium background removal
- Cutout fallback background removal

### Operator / Video Factory

The current code already contains many operator and Video Factory tables, commands, and endpoints. Treat this as a foundation, not yet a fully verified automatic production system.

The future stable flow should be:

topic -> campaign -> affiliate match -> manifest -> production tasks -> worker output -> review -> approve -> publish queue -> performance tracking

## Extraction Direction

Do not split everything at once.

The safe extraction order is:

1. `app/core/config.py`
2. `app/core/db.py`
3. `app/modules/billing/payos.py`
4. `app/modules/ai/providers.py`
5. `app/telegram/commands.py`
6. `app/modules/video_factory/`

Each phase must compile and pass tests before the next phase starts.

## Long Term Platform Model

TOAN AAS is not only a Telegram bot. The long-term architecture is an AI Automation System:

- Telegram Command Bot: fast control, admin approval, alerts, reports, customer commands.
- Core Backend: FastAPI, config, database, auth, user, billing, approval, audit, jobs, reports.
- Worker System: script worker, prompt worker, video worker, CRM/report worker, future device-ops worker.
- Dashboard: admin dashboard, customer portal, video factory, affiliate reports, project tracking.
- Automation Connectors: Telegram, PayOS, Facebook, TikTok, YouTube, Google Drive/Sheets, n8n/Make, email.
- Data Layer: SQLite temporarily, Railway Volume or backup required, PostgreSQL later, object storage later.

Refactor rule: use a gradual Strangler Fig pattern. Keep `bot.py` running while extracting config, DB, billing, AI providers, Telegram commands, and Video Factory modules one phase at a time.
