# Event Bus Plan — TOAN AAS

## Hiện trạng

Event bus hiện tại là SQLite table `system_events`.

Schema:

- `id`
- `event_type`
- `source`
- `payload_json`
- `status`
- `created_at`
- `processed_at`

Helper:

- `emit_event(conn, event_type, source, payload=None, status="pending")`

## Đã dùng

- PayOS success phát event `payment.paid` với payload không chứa secret:
  - `order_code`
  - `user_id`
  - `amount`
  - `xu`

## Event dự kiến

- `payment.paid`
- `credit.added`
- `credit.deducted`
- `video.created`
- `approval.requested`
- `backup.created`
- `health.failed`

## Dài hạn

- SQLite event table chỉ là foundation.
- Khi có worker thật, cân nhắc Redis queue hoặc managed queue.
- Không thêm Celery/Redis cho đến khi foundation và revenue bot ổn định.

