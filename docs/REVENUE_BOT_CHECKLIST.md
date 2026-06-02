# TOAN AAS Stable Revenue Bot Checklist

## Daily

- [ ] `/health`
- [ ] `/start`
- [ ] `/menu`
- [ ] `/help`
- [ ] `/commands`
- [ ] `/profile`
- [ ] `/naptien`
- [ ] Admin `/dashboard`
- [ ] Admin `/admin`
- [ ] Admin `/backup_db`

## Payment

- [ ] Chọn gói nạp.
- [ ] Tạo PayOS checkout.
- [ ] Webhook success cộng đúng xu.
- [ ] Duplicate webhook không cộng trùng.
- [ ] Amount mismatch không cộng xu.
- [ ] Missing checksum không tự cộng xu.
- [ ] Manual fallback hoạt động.
- [ ] Pending bill duyệt/từ chối đúng.

## Credits

- [ ] Trial credit tạo user mới.
- [ ] Spend/trừ xu đúng.
- [ ] Refund khi API lỗi.
- [ ] Chat paid exception hoàn xu.
- [ ] Admin add credit.
- [ ] VIP/admin bypass không trừ sai.
- [ ] `credit_events` ghi đủ.
- [ ] Thiếu xu hiện nút nạp 50k/100k/200k.

## AI tools

- [ ] Chat Gemini/OpenAI fallback.
- [ ] Voice Fish/Edge fallback.
- [ ] STT Deepgram.
- [ ] Background removal RemoveBG/Cutout fallback.
- [ ] Downloader trả file/kết quả đúng.
- [ ] `/film` tạo Video Script Lite.
- [ ] `/film` thiếu Xu hiện topup.
- [ ] `/film` AI lỗi hoàn Xu.
- [ ] `/film` gửi file `.md`.
- [ ] `/film topic="..." affiliate_id=1` dùng link đã lưu.
- [ ] `/help` không gọi API ngoài và không lộ admin/operator commands cho user thường.

## Affiliate + Calendar

- [ ] `/addlink` lưu link affiliate mới.
- [ ] `/addlink` không tạo trùng URL cùng user.
- [ ] `/links` chỉ hiện link active của user hiện tại.
- [ ] `/campaign` tạo campaign đơn giản.
- [ ] `/addcal` thêm lịch với affiliate_id/campaign hợp lệ.
- [ ] `/calendar` hiện lịch 7 ngày tới.
- [ ] `/calendar days=14 platform=tiktok` lọc đúng.
- [ ] Không có auto publish/render trong các flow này.

## Manual Publish + Performance

- [ ] `/publish_done tiktok https://... topic` lưu bài vào `published_posts`.
- [ ] `/publish_done platform=facebook url=https://... topic="..." affiliate_id=1` gắn affiliate đúng user.
- [ ] `/posts` hiện bài đã đăng gần đây.
- [ ] `/performance_add post_id=1 views=... clicks=... revenue=...` lưu vào `manual_performance_events`.
- [ ] `/performance_report` tổng hợp views/clicks/revenue theo nền tảng.
- [ ] `/growth_loop` cho user thường trả rule-based recommendation.
- [ ] Admin `/growth_loop` vẫn giữ operator loop mặc định.
- [ ] Admin `/growth_loop manual=1` xem manual post loop.
- [ ] `/dashboard` có số bài publish/manual performance/revenue nhập tay.
- [ ] Không gọi social API, không auto publish.

## Data safety

- [ ] `DB_FILE` đang đúng môi trường.
- [ ] Railway Volume đã cấu hình nếu chạy production.
- [ ] `/backup_db` gửi DB cho admin.
- [ ] Backup mới nhất có timestamp.
- [ ] Restore checklist đã được test.

## Admin

- [ ] `/stats`
- [ ] `/dashboard`
- [ ] `/admin`
- [ ] `/pending`
- [ ] `/duyet`
- [ ] `/tuchoi`
- [ ] `/add`
- [ ] `/setvip`
- [ ] `/admin_gopy`
- [ ] `/runtime`
- [ ] `/checkpayos`
- [ ] `/telegram_takeover`

## Live bot QA

- [ ] `/runtime` build khớp Git commit mới nhất.
- [ ] `/customer_surface` không báo leak A-TOOLS/operator/admin surface.
- [ ] `/start -> /profile -> /film -> thiếu Xu -> /naptien` đi được hết luồng.
- [ ] `/help` và `/commands` trả cùng hướng dẫn.
- [ ] User thường không thấy `/operator_menu`, `/dashboard`, `/pending`, `/duyet`, `/runtime`.
- [ ] Admin vẫn thấy dashboard/system commands.

## Growth

- [ ] `/ref`
- [ ] `/invite`
- [ ] Link ref đúng `https://t.me/{bot}?start=ref_{user_id}`.
- [ ] Thưởng khi người được mời nạp lần đầu.
- [ ] Không thưởng trùng.

## Health endpoint

- [ ] `status`
- [ ] `version`
- [ ] `uptime_seconds`
- [ ] `db_ok`
- [ ] `payos_configured`
- [ ] `gemini_configured`
- [ ] `openai_configured`
- [ ] `ai_provider_available`
- [ ] `deepgram_configured`
- [ ] `fish_audio_configured`
- [ ] `removebg_configured`
- [ ] `cutout_configured`
- [ ] `telegram_configured`
- [ ] `public_base_url_configured`
