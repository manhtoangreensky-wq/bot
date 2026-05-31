# TOAN DAAS Bot

Bot Telegram + FastAPI cho dịch vụ AI tính phí bằng Xu: chat AI, bóc băng audio, đọc voice, tách nền ảnh, tải video sạch, PayOS QR động, referral và dashboard admin.

## Chạy cục bộ

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python bot.py
```

Không lưu token/API key thật trong source code. Cấu hình trên Railway/Render/VPS bằng biến môi trường theo `.env.example`.

## Biến môi trường quan trọng

- `TELEGRAM_TOKEN`: token bot từ BotFather.
- `ADMIN_ID`: Telegram ID admin chính.
- `GEMINI_API_KEY`, `OPENAI_API_KEY`: AI provider chính và fallback.
- `DEEPGRAM_API_KEY`, `FISH_AUDIO_KEY`: bóc băng và voice cao cấp.
- `REMOVEBG_API_KEY`, `CUTOUT_API_KEY`: tách nền ảnh.
- `PAYOS_CLIENT_ID`, `PAYOS_API_KEY`, `PAYOS_CHECKSUM_KEY`: PayOS QR động.
- `BOT_USERNAME`: username bot, ví dụ `Httdhtoan`.
- `PUBLIC_BASE_URL`: domain public nếu cần dùng cho link ngoài.
- `MANUAL_BANK_NAME`, `MANUAL_BANK_CODE`, `MANUAL_BANK_ACCOUNT`, `MANUAL_BANK_OWNER`: tài khoản và mã VietQR nạp thủ công khi PayOS lỗi.

## Lệnh người dùng

- `/start`: menu chính.
- `/profile`: xem số dư, hạng, tổng chi.
- `/naptien`: tạo hóa đơn PayOS QR động.
- `/thucong`: nạp thủ công khi QR tự động lỗi.
- `/ref`: lấy link giới thiệu nhận thưởng.
- `/gopy <nội dung>`: góp ý hoặc báo lỗi.

## Lệnh admin

- `/add <ID> <Số_Xu>`: cộng xu thủ công.
- `/duyet <ID> <Số_Xu>`: duyệt bill thủ công.
- `/checkpayos <Mã_đơn>`: admin gọi PayOS kiểm tra lại đơn đã tạo link và tự cộng xu nếu trạng thái đã thanh toán.
- `/tuchoi <ID>`: từ chối bill thủ công.
- `/pending`: xem bill đang chờ.
- `/stats`: thống kê nhanh.
- `/dashboard`: dashboard text gồm user, đơn PayOS, biến động xu.
- `/setvip <ID> <1|0>`: bật/tắt VIP.
- `/admin_gopy`: tóm tắt góp ý 7 ngày.
- `/tools`: kho 30 công cụ AI/MMO nội bộ.
- `/mmo`: workflow kiếm tiền bằng AI hợp pháp nội bộ.
- `/campaign_new name=... niche=... platforms=... affiliate=...`: tạo chiến dịch AI Operator.
- `/campaigns`: liệt kê chiến dịch.
- `/video_plan campaign=<ID> topic=... platforms=... channel=<ID> aff=<ID>`: AI tạo brief video, caption, hashtag, CTA và compliance checklist.
- `/video_job <ID>`: xem lại video job.
- `/campaign_stats`: thống kê campaign/video job.
- `/channel_add platform=... name=... account=... focus=... audience=... slots=2/day`: lưu kênh/tài khoản nội bộ.
- `/channels`: liệt kê kênh/tài khoản nội bộ.
- `/affiliate_add network=... product=... niche=... url=... note=...`: lưu link affiliate Shopee/Lazada/TikTok hoặc sàn khác.
- `/affiliates`: liệt kê link affiliate nội bộ.
- `/calendar_plan days=7 channel=all campaign=<ID> aff=<ID> niche=...`: tạo lịch nội dung theo kênh.
- `/calendar`: xem lịch nội dung đã lên.
- `/operator topic=... channel=<ID> aff=<ID> campaign=<ID> date=YYYY-MM-DD`: ra lệnh một bước để tạo lịch nội dung + production job + brief AI.
- `/operator_next id=<JOB_ID> stage=script|voice|visuals|edit|review|publish`: AI điều phối stage tiếp theo, kèm tool chính/fallback và output cần lưu.
- `/operator_dashboard`: tổng quan kênh, affiliate, lịch sắp tới và production job cần xử lý.
- `/trend_search niche=... platform=tiktok channel=<ID> aff=<ID> campaign=<ID>`: tìm trend mới từ nguồn RSS/news công khai, hiện nút tạo video trend vào pipeline.
- `/handoff job=<ID> tool=claude|gemini|runway|kling|capcut|ffmpeg|fish|edge stage=...`: xuất prompt giao việc cho AI/tool khác và chuyển job sang `waiting`.
- `/publish_pack job=<ID>`: tạo gói caption, hashtag, CTA, link affiliate và checklist trước khi đăng.
- `/review_gate job=<ID>`: AI kiểm duyệt quyền hình ảnh/âm thanh, affiliate claim, CTA và rủi ro nền tảng trước khi đăng.
- `/mark_published job=<ID> url=https://... views=0 clicks=0 note=...`: ghi nhận bài đã đăng thủ công, lưu URL và chuyển job sang `published`.
- `/performance_add job=<ID> type=view|click|order|revenue|lead value=... amount=... note=...`: ghi hiệu quả bài đăng/affiliate.
- `/performance`: báo cáo hiệu quả theo loại sự kiện, kênh và job gần nhất.
- `/produce slot=<calendar_id>`: tạo production job từ lịch nội dung, kèm brief AI nếu đã cấu hình provider.
- `/pipeline`: xem hàng đợi sản xuất video.
- `/pipeline <ID>`: xem chi tiết production job.
- `/pipeline_set id=<ID> stage=edit status=working asset=https://... publish=https://... note=...`: cập nhật pipeline.

## API FastAPI

- `GET /`: health check.
- `GET /landing`: phục vụ landing page `index.html` cùng domain với API.
- `POST /webhook/payos`: nhận webhook PayOS, kiểm tra chữ ký, mã đơn, số tiền, trạng thái và chống cộng xu trùng.
- `POST /lead`: nhận lead từ landing page và gửi thông báo về admin Telegram.

## Ghi chú kiến trúc

- `bot.py` hiện là file chạy chính.
- Thư mục `handlers/` là mã legacy từ phiên bản cũ, chưa được import trong runtime hiện tại.
- SQLite phù hợp bản nhỏ. Khi public nhiều người dùng, nên chuyển sang PostgreSQL hoặc tách lớp repository để kiểm soát transaction tốt hơn.
- AI Operator v1 mới tạo kế hoạch video/caption/affiliate, lịch nội dung và production pipeline để admin duyệt/điều phối. Auto-post lên TikTok/Facebook/YouTube/OnlyFans cần cấu hình API/OAuth chính thức ở giai đoạn sau.
- Channel/affiliate/calendar registry là khu vực admin-only để quản lý kênh Facebook/TikTok/OnlyFans, tài khoản phụ, link affiliate và lịch đăng nội dung. Không hiển thị cho khách hàng.
- Production pipeline là admin-only, dùng để theo dõi từng video qua các stage: `brief`, `script`, `voice`, `visuals`, `edit`, `review`, `publish`, `done`.
- Performance tracking là admin-only, dùng để ghi view/click/order/revenue/lead sau khi đăng bài và theo dõi kênh hoặc affiliate nào đang tạo tiền.
- Trend search là admin-only, dùng để tìm trend mới trước khi tạo video; bot lưu trend candidate, tạo lịch/job từ trend và vẫn yêu cầu admin kiểm duyệt trước khi đăng.
- Review gate là admin-only, dùng làm chốt kiểm duyệt trước khi đăng; job đạt có thể chuyển sang `ready`, job rủi ro chuyển `blocked`.
- Tool routing giữ đúng ý tưởng gốc: ưu tiên công cụ tốt/có phí trước, sau đó mới fallback sang công cụ ít phí/miễn phí. Gemini → OpenAI cho chat, Fish Audio HD → Edge TTS cho voice, RemoveBG HD → Cutout.pro cho tách nền. Khi gói cao cấp lỗi/quota, bot hoàn phần chênh lệch, chuyển sang gói dự phòng và báo admin kiểm tra quota/số dư/API key.
- Với AI influencer/người mẫu AI: chỉ dùng nhân vật tự tạo hoặc người thật có đồng ý rõ ràng, đủ 18 tuổi; không dùng để giả mạo, lừa đảo hoặc tạo nội dung vi phạm nền tảng/pháp luật.
