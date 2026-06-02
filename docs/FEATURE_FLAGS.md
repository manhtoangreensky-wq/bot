# Feature Flags — TOAN AAS

## Hiện trạng

Đã thêm bảng `feature_flags`:

- `key TEXT PRIMARY KEY`
- `enabled INTEGER DEFAULT 0`
- `scope TEXT DEFAULT 'all'`
- `note TEXT`
- `updated_at DATETIME`

Helper:

- `is_feature_enabled(key, user_id=None, default=False) -> bool`

Nếu flag chưa có hoặc DB lỗi, helper trả `default`.

## Flags seed

| Flag | Default | Ghi chú |
| --- | ---: | --- |
| `video_factory` | 0 | Chặn mở rộng Video Factory lớn khi foundation chưa ổn. |
| `youtube_output` | 0 | Chặn output YouTube nâng cao. |
| `affiliate_engine` | 0 | Chặn automation affiliate nâng cao. |
| `device_ops` | 0 | Không ưu tiên trong 90 ngày đầu. |
| `auto_publish` | 0 | Luôn tắt auto publish nếu chưa duyệt rõ. |
| `worker_queue` | 0 | Worker queue chưa bật rộng. |
| `dashboard` | 0 | Dashboard mở rộng đang gated. |
| `trial_upsell` | 1 | Có thể bật flow upsell trial sau khi payment ổn. |
| `payos_dynamic` | 1 | Dynamic billing đang bật. |
| `telegram_menu_v2` | 1 | Menu TOAN AAS mới đang bật. |
| `website_rebrand` | 1 | Landing TOAN AAS đang bật. |

## Quy tắc dùng

- Không dùng feature flag để bypass bảo mật.
- Không bật `auto_publish` nếu chưa có approval gate.
- Không bật module lớn khi chưa có test/recovery plan.

