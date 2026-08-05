# Backup & Recovery — TOAN AAS

## Mục tiêu

Không mất user, xu, đơn PayOS, `credit_events`, bill thủ công, affiliate links và dữ liệu vận hành.

## Backup hiện tại

- Manual command: `/backup_db`.
- DB_FILE: đọc từ ENV `DB_FILE`, default `toandaas_system.db`.
- Backup receiver: `ADMIN_ID`.
- Lưu ý: `/backup_db` gửi file SQLite qua Telegram cho admin, có checkpoint WAL trước khi gửi.

## Backup ngắn hạn

- Admin chạy `/backup_db` mỗi ngày.
- Trước khi deploy lớn, chạy `/backup_db`.
- Trước migration, chạy `/backup_db`.
- Sau khi tạo Railway Volume, chạy backup trước và sau khi đổi `DB_FILE`.
- Runtime tự giữ tối đa 3 bản backup hợp lệ gần nhất trong `/data/backups`; file đang được DB/job tham chiếu hoặc backup lỗi không bị xóa.
- Vòng maintenance kiểm tra mỗi 5 phút, dọn temp/partial theo TTL và chạy sweep daily lúc 12:00 Asia/Ho_Chi_Minh; backup retention chạy Sunday 03:30.
- Auto backup health/checkpoint notification chạy mỗi 12 giờ; đây không thay thế backup thủ công trước migration/deploy.

## Backup trung hạn

- Upload Google Drive/S3/R2.
- Giữ 7 bản gần nhất.
- Mỗi bản có timestamp.
- Tách backup khỏi Telegram nếu DB lớn hơn giới hạn gửi file.

## Restore checklist

1. Stop Railway service.
2. Lấy file backup mới nhất.
3. Upload lại vào đúng `DB_FILE` path.
4. Start service.
5. Kiểm tra `/health`.
6. Kiểm tra `/profile` với user test.
7. Kiểm tra `/dashboard` admin.
8. Kiểm tra `payos_orders` gần nhất.
9. Kiểm tra `credit_events` gần nhất.

## Khi nào bắt buộc backup

- Trước khi sửa DB schema.
- Trước khi chuyển Railway Volume.
- Trước khi tách `db.py`.
- Trước khi deploy major update.
- Trước khi thêm Video Factory schema.

## Rủi ro còn lại

- `/backup_db` là backup thủ công, chưa phải backup tự động hằng ngày.
- Nếu file DB quá lớn, Telegram có thể không nhận file.
- Cần test restore thật ít nhất một lần trên môi trường staging/local.
