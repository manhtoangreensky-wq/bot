# Next Task Proposal

Sau task foundation này, task tiếp theo nên là một trong các task sau, admin chọn:

## Option A — Extract config.py safely

- Tạo `app/core/config.py`.
- Move ENV/constants.
- Không đổi tên ENV.
- `bot.py` vẫn chạy.

## Option B — Extract db.py safely

- Tạo `app/core/db.py`.
- Move DB helpers.
- Không đổi schema.

## Option C — Trial upsell flow

- Khi thiếu xu/hết trial, hiện gói 50k/100k/200k.
- Nút tạo PayOS link.
- Không phá `/naptien`.

## Option D — Video Factory schema MVP

- Tạo `video_projects`, `video_episodes`, `video_scenes`, `platform_outputs`.
- Không render.
- Không publish.

Codex không tự làm Option A/B/C/D nếu chưa được duyệt.
