# TOAN AAS Stable Revenue Bot Checklist

## Daily health

- `/health`
- `/start`
- `/menu`
- `/profile`
- `/naptien`
- admin `/dashboard`
- admin `/backup_db`

## Payment

- user chọn gói.
- PayOS checkout URL.
- webhook success.
- duplicate không cộng trùng.
- amount mismatch không cộng.
- missing checksum không cộng.
- manual fallback.
- admin `/duyet` đúng số Xu.
- admin `/tuchoi` thông báo khách.

## Credits

- trial credits.
- spend credits.
- refund on API error.
- admin add.
- VIP free.
- thiếu Xu hiện topup 50k/100k/200k.

## AI tools

- chat.
- voice.
- STT.
- background removal.
- downloader.
- fallback tool/refund behavior.

## Data safety

- DB_FILE.
- Railway Volume.
- `/backup_db`.
- latest backup timestamp.
- restore checklist.

## Admin

- `/stats`
- `/dashboard`
- `/pending`
- `/duyet`
- `/tuchoi`
- `/add`
- `/setvip`
- `/admin_gopy`
- `/backup_db`

## Production check

- `GET /` returns OK.
- `GET /landing` returns landing.
- `GET /LOGO.png` returns logo.
- `GET /health` returns config and DB status without external API calls.
- Telegram webhook URL points to current Railway service.
- No other deployment uses the same Telegram token.

## Do not expand yet

- No dashboard lớn.
- No ERP/CRM lớn.
- No Device Ops.
- No PostgreSQL migration lớn.
- No auto publish.
- No full video render.
