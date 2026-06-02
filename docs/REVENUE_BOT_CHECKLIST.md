# Revenue Bot Checklist

## Railway ENV

Required for stable revenue bot:

- `TELEGRAM_TOKEN`
- `ADMIN_ID`
- `PORT`
- `PUBLIC_BASE_URL` or Railway public domain fallback
- `GEMINI_API_KEY` or `OPENAI_API_KEY`
- `PAYOS_CLIENT_ID`
- `PAYOS_API_KEY`
- `PAYOS_CHECKSUM_KEY`
- `DEEPGRAM_API_KEY`
- `REMOVEBG_API_KEY` or `CUTOUT_API_KEY`

Recommended:

- `FISH_AUDIO_KEY`
- `DEEPL_API_KEY`
- `RAPIDAPI_KEY`
- `RAPIDAPI_HOST`
- `COBALT_API_KEY`
- `LEAD_WEBHOOK_SECRET`
- `OPERATOR_API_TOKEN`
- `AFFILIATE_POSTBACK_TOKEN`

## Telegram Test

- `/start`
- `/profile`
- `/naptien`
- `/tools`
- `/mmo`
- `/ref`
- `/dashboard` as admin
- Normal user cannot access admin/operator commands.

## Payment Test

- Create 10k order.
- Open PayOS checkout.
- PayOS webhook credits the user.
- Duplicate order is not credited twice.
- Wrong amount is not credited.
- Expired/cancelled order is not credited.
- Manual bill fallback reaches admin.
- `/duyet` credits correctly.
- `/tuchoi` notifies customer.

## AI Test

- Normal chat works.
- Gemini failure falls back to OpenAI.
- Missing Gemini and OpenAI returns a clear error.
- Credits are charged/refunded correctly.

## Media Test

- Audio transcription works.
- Deepgram error refunds charged credits.
- Image background removal works.
- RemoveBG failure falls back to Cutout when configured.
- Voice generation works.
- Premium voice failure falls back to Edge TTS when configured.
- Video download/cleanup path works.

## Security

- No API key/token in logs.
- No `.env` committed.
- User cannot call admin commands.
- PayOS signature is verified.
- PayOS amount must match order before crediting.
- Lead endpoint uses secret if configured.
- Manual bank info is intentional and configurable by ENV.

## Production Check

- `GET /` returns OK.
- `GET /runtime` returns current build.
- Telegram webhook URL points to current Railway service.
- No other deployment uses the same Telegram token.
