# TOAN AAS Load Tests

These scripts are safe test harnesses for staging/local environments. Do not run them against production unless dry-run flags are enabled and the operator confirms the test window.

## Required Runtime Flags

Set these in the target environment before webhook/write/billing tests:

```text
LOAD_TEST_MODE=true
BOT_DRY_RUN_SEND=true
PROVIDER_DRY_RUN=true
PAYOS_DRY_RUN=true
DISABLE_REAL_TELEGRAM_SEND=true
LOAD_TEST_USER_PREFIX=loadtest_
```

The current scripts also send safety headers:

- `X-Load-Test-Mode: true`
- `X-Dry-Run: true`

## Scripts

- `k6_app.js`: app/API read and light-write dry-run paths.
- `k6_bot_webhook.js`: synthetic Telegram webhook updates.
- `k6_mixed.js`: mixed app + bot workload.

## Examples

Local/staging read-only:

```bash
k6 run -e BASE_URL=http://localhost:8000 loadtests/k6_app.js
```

Bot webhook dry-run:

```bash
k6 run -e BASE_URL=http://localhost:8000 -e TELEGRAM_WEBHOOK_PATH=/webhook/telegram/<secret> loadtests/k6_bot_webhook.js
```

Mixed:

```bash
k6 run -e BASE_URL=http://localhost:8000 -e TELEGRAM_WEBHOOK_PATH=/webhook/telegram/<secret> loadtests/k6_mixed.js
```

## Production Safety

Do not run:

- real PayOS order creation without `PAYOS_DRY_RUN=true`
- real Telegram sendMessage spam
- real ShopAIKey/OpenAI/Gemini/VEO image/video/TTS jobs
- webhook payment transaction replay

If `BASE_URL` points to production, run a small read-only smoke first:

```bash
k6 run -e BASE_URL=https://app.toanaas.vn -e READ_ONLY=true loadtests/k6_app.js
```
