# Railway Volume Setup — TOAN AAS

## Vì sao cần làm

TOAN AAS hiện dùng SQLite. Nếu DB nằm trong filesystem không persistent của Railway, redeploy có thể làm mất dữ liệu user/xu/giao dịch.

## Cách làm thủ công trên Railway

1. Mở Railway Project.
2. Chọn service bot.
3. Vào Volumes.
4. Tạo volume mount vào `/data`.
5. Vào Variables.
6. Thêm:

```text
DB_FILE=/data/toandaas_system.db
```

7. Redeploy.
8. Kiểm tra `/health` xem `db_ok=true`.
9. Tạo user test.
10. Redeploy lại.
11. Kiểm tra user test còn không.

## Checklist xác nhận

- [ ] Volume đã tạo.
- [ ] DB_FILE đã trỏ `/data/toandaas_system.db`.
- [ ] `/health` `db_ok=true`.
- [ ] Redeploy không mất user.
- [ ] Backup hoạt động.

## Cảnh báo

Không đổi `DB_FILE` nếu chưa backup DB cũ.

Nếu trước đó DB cũ đang nằm ở `toandaas_system.db`, cần copy dữ liệu thủ công sang volume trước khi chạy production.

Không xóa DB cũ cho đến khi đã xác nhận:

- `/health` trên Railway OK.
- `/profile` của user test còn đúng.
- PayOS order gần nhất còn trong DB.
- `credit_events` còn lịch sử.

## Plan B

Nếu Railway Volume không ổn:

- Chuyển Turso.
- Hoặc Supabase/PostgreSQL.
- Hoặc backup DB mỗi ngày về admin.
