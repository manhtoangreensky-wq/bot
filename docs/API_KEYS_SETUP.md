# API KEYS SETUP - TOAN AAS

Date: 2026-06-02
Scope: Railway ENV only. No API key, token, checksum, or secret is stored in this file.

## Principles

- Store every provider key in Railway Variables.
- Do not commit `.env`.
- Do not paste API keys into Telegram, docs, GitHub, screenshots, workflow notes, or prompts.
- `/providers` only shows `configured` or `missing`.
- `/health` only shows booleans.
- Regenerate any key that appeared in screenshots or logs.

## Core

| ENV | Purpose | Required before public sale |
|---|---|---:|
| `TELEGRAM_TOKEN` or `BOT_TOKEN` | Telegram bot runtime | YES |
| `ADMIN_ID` | Admin-only commands and alerts | YES |
| `PUBLIC_BASE_URL` | Railway public URL and webhook URL | YES |
| `PORT` | Railway web process port | YES |

## AI

| ENV | Purpose | Current behavior |
|---|---|---|
| `GEMINI_API_KEY` | Primary chat/script/growth provider | Preferred when available. |
| `OPENAI_API_KEY` | AI fallback | Used when Gemini is missing or fails in existing fallback path. |

At least one AI provider should be configured before opening `/film` and `/growth_ai` to paid users.

## Audio

| ENV | Purpose | Current behavior |
|---|---|---|
| `DEEPGRAM_API_KEY` | Speech-to-text/audio transcription | Required for STT. |
| `FISH_AUDIO_KEY` | Paid HD TTS | Falls back to Edge TTS if missing or failed. |
| `DEEPL_API_KEY` | Translation reserve | Read from ENV; not a Deepgram replacement. |

## Image

| ENV | Purpose | Current behavior |
|---|---|---|
| `REMOVEBG_API_KEY` | Paid/high-quality background removal | Primary path when selected/configured. |
| `CUTOUT_API_KEY` | Background removal fallback | Used when configured and fallback path is needed. |

## Downloader

| ENV | Purpose | Current behavior |
|---|---|---|
| `COBALT_API_URL` | Preferred self-hosted downloader endpoint | Safer than public Cobalt. |
| `COBALT_API_KEY` | Optional Cobalt auth key | Sent only to Cobalt request headers. |
| `RAPIDAPI_KEY` | RapidAPI fallback | Read from ENV; do not expose. |
| `RAPIDAPI_HOST` | RapidAPI host | Read from ENV; do not expose. |

## Payment

| ENV | Purpose | Required before real PayOS test |
|---|---|---:|
| `PAYOS_CLIENT_ID` | PayOS checkout API | YES |
| `PAYOS_API_KEY` | PayOS checkout API | YES |
| `PAYOS_CHECKSUM_KEY` | PayOS signature/webhook verification | YES |

All three PayOS values must come from the same PayOS channel/account.

## Security/API Bridge

| ENV | Purpose | Notes |
|---|---|---|
| `TELEGRAM_WEBHOOK_SECRET` | Telegram webhook secret token | Recommended on Railway. |
| `LEAD_WEBHOOK_SECRET` | `/lead` form secret | Required only if lead webhook protection is enabled. |
| `OPERATOR_API_TOKEN` | Operator API bridge | Admin/worker only; never publish. |
| `AFFILIATE_POSTBACK_TOKEN` | Affiliate postback endpoint token | Required for protected postbacks. |

## Admin checks

1. Deploy with ENV set.
2. Run `/providers`.
3. Run `/sales_ready`.
4. Run `/payos_test_plan`.
5. Run `/backup_db` before the first real payment test.
