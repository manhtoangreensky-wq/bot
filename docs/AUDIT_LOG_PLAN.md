# Audit Log Plan — TOAN AAS

## Hiện trạng

Đã thêm bảng `audit_logs`:

- `id`
- `actor_id`
- `actor_type`
- `action`
- `object_type`
- `object_id`
- `before_json`
- `after_json`
- `note`
- `created_at`

Đã thêm helper:

- `record_audit(conn, actor_id, actor_type, action, object_type="", object_id="", before=None, after=None, note="")`
- `record_audit_event(...)` cho các action ngoài transaction chính.

## Nguyên tắc

- Không log API key/token/secret.
- Không để lỗi audit làm crash billing.
- Nếu có transaction đang mở, truyền cùng `conn` vào `record_audit`.
- `before`/`after` được serialize JSON với `ensure_ascii=False`.

## Đã áp dụng

- PayOS paid order success: `payment.paid`.
- Admin cộng xu thủ công: `credit.added`.
- Admin duyệt bill thủ công: `bill.approved`.
- Admin từ chối bill: `bill.rejected`.
- Admin cập nhật VIP: `user.vip_updated`.
- Admin backup DB thành công/thất bại: `backup.created`, `backup.failed`.

## TODO

- Áp dụng cho các luồng trừ xu trả phí.
- Áp dụng cho refund media/download.
- Áp dụng cho tạo/xóa/sửa affiliate link.
- Áp dụng cho publish queue và review gate.
- Thêm màn hình admin đọc audit theo ngày/action.

