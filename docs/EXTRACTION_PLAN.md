# Extraction Plan

Do not extract all modules at once.

The current goal is to keep `bot.py` working while moving toward maintainable modules.

## Phase 1: Config / ENV

Target:

- `app/core/config.py`

Move:

- `_env`
- public URL detection
- Telegram config
- PayOS config
- AI provider keys
- upload directory config

Rules:

- Keep `bot.py` importing config.
- Do not change ENV names.
- Do not hardcode secrets.
- Compile after extraction.

## Phase 2: Database Helpers

Target:

- `app/core/db.py`

Move:

- `db_connect`
- `init_db`
- common CRUD helpers

Rules:

- Do not change table names.
- Do not drop tables.
- Add tests with temporary SQLite DB.

## Phase 3: PayOS

Target:

- `app/modules/billing/payos.py`

Move:

- PayOS signature helpers
- order creation
- webhook verification
- duplicate protection
- manual fallback helpers

Rules:

- Keep old command behavior.
- Test correct signature, bad signature, duplicate order, wrong amount.

## Phase 4: AI Providers

Target:

- `app/modules/ai/providers.py`

Move:

- Gemini client
- OpenAI fallback
- Deepgram
- Fish Audio / Edge TTS flow
- RemoveBG / Cutout flow

Rules:

- Preserve paid-first, fallback-second behavior.
- Preserve refund behavior on failed paid operations.

## Phase 5: Telegram Commands

Target:

- `app/telegram/commands.py`
- `app/telegram/handlers.py`

Move:

- Command registration
- callback registration
- customer/admin command grouping

Rules:

- Do not expose admin commands to customers.
- Keep `/start`, `/profile`, `/naptien`, `/gopy`, billing commands stable.

## Phase 6: Video Factory

Target:

- `app/modules/video_factory/`

Move:

- campaign planning
- affiliate matching
- manifests
- production tasks
- assets
- review/approve/publish queue
- performance tracking

Rules:

- Only start after revenue bot and database migration are stable.
- Keep review gate before publishing.
- Do not auto-publish without admin approval.
