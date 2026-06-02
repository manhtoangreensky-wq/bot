# STABLE REVENUE BOT STATUS

## Compile

- `python -m py_compile bot.py`: PASS.

## Brand/UI

- Website/landing đã là TOAN AAS chưa: Yes.
- `/start` đã gọn chưa: Yes, dùng menu nhóm.
- `/menu` có chưa: Yes.
- User menu: AI cơ bản, Video AI, Kiếm Tiền, Nạp Xu, Tài Khoản, Hỗ Trợ.
- Admin menu: AI Cơ Bản, Video Factory, Affiliate, Operator, Quản Trị, Hệ Thống, Billing, Hỗ Trợ.

## Payment

- PayOS packages: 10k, 20k, 50k, 100k, 200k, 500k.
- `/naptien`: Có bảng giá và inline package buttons.
- Checkout URL: Tạo qua PayOS khi ENV đủ.
- Webhook: `POST /webhook/payos`.
- Duplicate protection: `payos_processed` + transaction `BEGIN IMMEDIATE`.
- Amount mismatch protection: Có đối chiếu amount nội bộ.
- Manual fallback: `/thucong`, gửi bill, admin `/duyet` hoặc `/tuchoi`.
- Remaining risks: Need manual verification bằng giao dịch thật trên Railway.

## Credits/Xu

- Trial credits: `150`.
- `has_deposited`: Có trong users, dùng để phân biệt trial.
- deduct logic: `deduct_dynamic_credit`, `spend_fixed_credit`.
- refund logic: `refund_charged_credit`.
- admin add: `/add`.
- VIP logic: admin/VIP không bị trừ như user thường.
- remaining risks: Cần test thực tế từng flow media/tool sau deploy.

## AI tools

- Chat AI: Có.
- Gemini: Có nếu ENV đủ.
- OpenAI fallback: Có nếu ENV đủ.
- Deepgram: Có cho STT nếu ENV đủ.
- Fish/Edge TTS: Có premium/fallback.
- RemoveBG/Cutout: Có premium/fallback.
- Downloader: Có downloader flow và refund khi lấy được link nhưng gửi file lỗi.
- remaining risks: Quota/provider lỗi cần test thật, không chỉ compile.

## Data safety

- DB_FILE: `_env("DB_FILE", "toandaas_system.db")`.
- SQLite path: default root DB hoặc `/data/toandaas_system.db` khi Railway ENV được set.
- Railway Volume: Need manual verification.
- Backup command: `/backup_db` admin-only.
- `/health`: Có.
- remaining risks: Chưa có backup tự động hằng ngày, restore chưa test thật.

## Admin operations

- `/dashboard`: Có, đã có thêm user đã nạp, xu lưu hành, bill chờ, lead, góp ý, audit 24h.
- `/stats`: Có.
- `/pending`: Có.
- `/duyet`: Có.
- `/tuchoi`: Có.
- `/add`: Có.
- `/setvip`: Có.
- `/backup_db`: Có.
- remaining risks: Cần test Telegram thật sau Railway deploy.

## Next recommended task

- 1 việc nên làm tiếp: Manual Railway Volume verification + real `/backup_db` + real `/health` on Railway.
- việc không nên làm lúc này: Không làm dashboard lớn, app ngoài, Device Ops, SaaS, PostgreSQL migration lớn, auto publish hoặc full video render.

