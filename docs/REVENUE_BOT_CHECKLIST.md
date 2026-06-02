# TOAN AAS Revenue Bot Checklist

## Daily test

- `/start`
- `/menu`
- `/profile`
- `/naptien`
- `/health`
- admin `/dashboard`
- admin `/backup_db`

## Payment test

- Tạo gói 10k.
- Tạo PayOS checkout.
- PayOS webhook.
- Không cộng trùng.
- Amount mismatch không cộng.
- Thiếu checksum không cộng.
- Manual fallback gửi bill về admin.
- `/duyet` cộng xu đúng.
- `/tuchoi` thông báo khách đúng.

## AI test

- Chat AI.
- Gemini fallback OpenAI.
- Cả hai thiếu thì báo lỗi rõ.
- Không trừ xu sai khi AI lỗi.

## Media test

- Voice.
- STT.
- Image background removal.
- Video downloader.
- Paid tool lỗi thì fallback/hoàn xu đúng.

## Admin test

- `/stats`
- `/dashboard`
- `/pending`
- `/duyet`
- `/tuchoi`
- `/add`
- `/setvip`
- `/backup_db`

## Data safety

- Railway volume.
- `DB_FILE`.
- `/backup_db`.
- Latest backup timestamp.
- `audit_logs` có ghi action billing/admin.
- `system_events` có event payment.
- `feature_flags` seed đúng.

## Production check

- `GET /` returns OK.
- `GET /landing` returns landing.
- `GET /LOGO.png` returns logo.
- `GET /health` returns:
  - `status`
  - `service`
  - `version`
  - `app_version`
  - `uptime_seconds`
  - `db_ok`
  - `db_file`
  - `payos_configured`
  - `ai_provider_available`
  - `telegram_configured`
  - `public_base_url_configured`
  - `timestamp`
- Telegram webhook URL points to current Railway service.
- No other deployment uses the same Telegram token.

## Railway Persistence Check

- Confirm Railway Volume exists before trusting SQLite for production money data.
- Set `DB_FILE=/data/toandaas_system.db` only after backup/copy plan.
- Redeploy and verify test user remains.
- Never disable PayOS/manual bill logs while testing storage.
