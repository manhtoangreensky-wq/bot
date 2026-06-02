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
- [ ] `/promo_seed_policy` admin tạo policy FIRST30/SECOND15/WEEKLY10/MONTHLY20/DAILY5/BETA50.
- [ ] `/promo FIRST30` user kích hoạt trước khi nạp lần đầu.
- [ ] Gói 50k + FIRST30 cộng đúng 650 Xu: 500 gốc + 150 promo, không có Launch Bonus.
- [ ] Lần đầu mua gói 100k không promo cộng đúng 1.050 Xu: 1.000 gốc + 50 Launch Bonus.
- [ ] `/gift <code>` cộng Xu quà tặng trực tiếp và không cho nhận trùng quá giới hạn.
- [ ] Promo không cộng bonus trùng khi replay cùng order.
- [ ] Manual fallback hoạt động.
- [ ] Pending bill duyệt/từ chối đúng.

## Credits

- [ ] Trial credit tạo user mới là 200 Xu.
- [ ] Spend/trừ xu đúng.
- [ ] Refund khi API lỗi.
- [ ] Chat paid exception hoàn xu.
- [ ] Admin add credit.
- [ ] VIP/admin bypass không trừ sai.
- [ ] `credit_events` ghi đủ.
- [ ] Thiếu xu hiện nút nạp 50k/100k/200k.

## AI tools

- [ ] Chat Gemini/OpenAI fallback.
- [ ] `/models` và `/ai_models` hiển thị normal/pro/deep, không lộ key.
- [ ] `/chat_pro` thiếu nội dung trả hướng dẫn và không trừ Xu.
- [ ] `/chat_pro` câu ngắn tính từ 20 Xu nếu provider configured.
- [ ] `/chat_pro tier=deep` tính từ 50 Xu.
- [ ] `/chat_pro model=sonnet` báo planned/missing và không trừ Xu.
- [ ] `/chat_pro` AI lỗi thì hoàn Xu.
- [ ] Voice Fish/Edge fallback.
- [ ] STT Deepgram.
- [ ] Background removal RemoveBG/Cutout fallback.
- [ ] Downloader trả file/kết quả đúng.
- [ ] `/film` tạo Video Script Lite với giá Basic 200 Xu.
- [ ] `/film episodes=3 scenes=5` tính 400 Xu.
- [ ] `/film tier=pro` tính 500 Xu.
- [ ] `/film tier=series` tính 1,200 Xu.
- [ ] `/film` thiếu Xu hiện topup với giá đúng.
- [ ] `/film` AI lỗi hoàn Xu.
- [ ] `/film` gửi file `.md`.
- [ ] `/film topic="..." link="https://..."` dùng link dán trực tiếp làm ngữ cảnh caption/CTA.
- [ ] `/help` không gọi API ngoài và không lộ admin/operator commands cho user thường.

## Affiliate + Calendar Internal Backlog

- [ ] User thường gọi `/addlink`, `/links`, `/campaign`, `/addcal`, `/calendar` sẽ nhận thông báo internal/backlog.
- [ ] Admin vẫn dùng được affiliate/calendar commands để test nội bộ.
- [ ] Không có render hoặc publish automation trong customer flow.

## Manual Publish + Performance Internal Backlog

- [ ] User thường gọi `/publish_done`, `/posts`, `/performance_add`, `/performance_report`, `/growth_loop` sẽ nhận thông báo internal/backlog.
- [ ] Admin vẫn dùng được manual publish/performance commands để test nội bộ.
- [ ] `/growth_ai` và `/campaign_report` không hướng dẫn user tự dùng publish tracking khi chưa có dữ liệu.
- [ ] `/growth_ai` có data thì trừ 120 Xu với user thường.
- [ ] `/growth_ai` không có data thì hướng dẫn dùng `/film` hoặc gửi số liệu cho admin, không trừ Xu.
- [ ] `/growth_ai` AI lỗi thì hoàn Xu.
- [ ] `/campaign_report format=txt` trừ 50 Xu và gửi file TXT.
- [ ] `/campaign_report format=csv` trừ 50 Xu và gửi file CSV.
- [ ] `/campaign_report` lỗi export thì hoàn 50 Xu.
- [ ] `/export_report` alias hoạt động.
- [ ] Admin `/growth_loop` vẫn giữ operator loop mặc định.
- [ ] Admin `/growth_loop manual=1` xem manual post loop.
- [ ] `/dashboard` admin có số bài publish/manual performance/revenue nhập tay.
- [ ] `/dashboard` có count AI Growth Coach tháng này.
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
- [ ] `/providers`
- [ ] `/costs`
- [ ] `/sales_ready`
- [ ] `/payos_test_plan`
- [ ] `/promo_seed_beta`
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

## Provider and sales readiness

- [ ] `/providers` shows configured/missing only.
- [ ] `/pricing` và `/banggia` hiển thị bảng giá user.
- [ ] `/pricing_admin` admin-only.
- [ ] `/costs` hiển thị Chat Pro Pro/Deep/content-unit/cap.
- [ ] `/providers` does not reveal key suffixes, tokens, checksum, or raw secret values.
- [ ] `/costs` matches current Xu pricing: `/film` 200/500/1,200, `/growth_ai` 120, `/campaign_report` 50, trial 200, free chat daily 20.
- [ ] `/sales_ready` returns NOT READY or BETA READY only.
- [ ] `/payos_test_plan` is available to admin.
- [ ] `docs/API_KEYS_SETUP.md` reviewed before adding new provider keys.
- [ ] `docs/PAYOS_REAL_PAYMENT_TEST.md` completed with one real 10k payment before public sale.
- [ ] `docs/FEATURE_FLAGS_STATUS.md` confirms `auto_publish=0`.
