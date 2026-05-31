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
- `OPERATOR_API_TOKEN`: token riêng cho n8n/Claude/tool worker gọi Operator API Bridge. Không set thì bridge tự đóng.

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
- `/brain <lệnh tự nhiên>`: đầu não admin-only, hiểu lệnh tiếng Việt và tự định tuyến sang Operator Auto, tạo job, build job, job ready check hoặc báo cáo vận hành.
- `/autopilot niche=... platform=tiktok channel=all aff=<ID> campaign=<ID> limit=3 duration=45`: tìm trend, tạo production job và tự build creative/manifest/task cho batch video.
- `/operator_menu`: menu nút bấm cho toàn bộ quy trình AI Operator.
- `/campaign_new name=... niche=... platforms=... affiliate=...`: tạo chiến dịch AI Operator.
- `/campaigns`: liệt kê chiến dịch.
- `/video_plan campaign=<ID> topic=... platforms=... channel=<ID> aff=<ID>`: AI tạo brief video, caption, hashtag, CTA và compliance checklist.
- `/video_job <ID>`: xem lại video job.
- `/campaign_stats`: thống kê campaign/video job.
- `/channel_add platform=... name=... account=... focus=... audience=... slots=2/day`: lưu kênh/tài khoản nội bộ.
- `/channels`: liệt kê kênh/tài khoản nội bộ.
- `/channel_publish_set id=<CHANNEL_ID> mode=manual|api token_env=... page_id=...`: cấu hình khả năng đăng thủ công/API cho kênh, chỉ lưu tên biến môi trường token.
- `/publish_readiness`: kiểm tra kênh nào sẵn sàng đăng thủ công hoặc đã đủ cấu hình API cơ bản.
- `/affiliate_add network=... product=... niche=... url=... price=... rate=... audience=... allowed=... blocked=...`: lưu link affiliate Shopee/Lazada/TikTok hoặc sàn khác kèm hồ sơ sản phẩm.
- `/affiliates`: liệt kê link affiliate nội bộ.
- `/affiliate_profile id=<AFF_ID> price=... rate=... audience=... allowed=... blocked=... score=...`: cập nhật hồ sơ, claim được phép và claim cấm cho sản phẩm affiliate.
- `/affiliate_match niche=... platform=tiktok trend=...`: xếp hạng affiliate phù hợp với trend/niche để chọn link trước khi tạo video.
- `/calendar_plan days=7 channel=all campaign=<ID> aff=<ID> niche=...`: tạo lịch nội dung theo kênh.
- `/calendar`: xem lịch nội dung đã lên.
- `/operator topic=... channel=<ID> aff=<ID> campaign=<ID> date=YYYY-MM-DD`: ra lệnh một bước để tạo lịch nội dung + production job + brief AI.
- `/operator_build job=<ID> n=5 duration=45`: tự tạo creative variants, chọn biến thể tốt nhất, tạo manifest và tách task sản xuất cho một job.
- `/operator_auto niche=... platform=tiktok channel=all aff=<ID> campaign=<ID> limit=5`: tự tìm trend, chấm điểm ưu tiên affiliate và tạo batch production job cho nhiều kênh active.
- `/operator_next id=<JOB_ID> stage=script|voice|visuals|edit|review|publish`: AI điều phối stage tiếp theo, kèm tool chính/fallback và output cần lưu.
- `/operator_dashboard`: tổng quan kênh, affiliate, lịch sắp tới và production job cần xử lý.
- `/operator_daily days=1`: báo cáo vận hành theo ngày gồm job mới, publish queue, performance và việc cần xử lý.
- `/trend_search niche=... platform=tiktok channel=<ID> aff=<ID> campaign=<ID>`: tìm trend mới từ nguồn RSS/news công khai, chấm điểm trend/affiliate/cạnh tranh và hiện nút tạo video trend vào pipeline.
- `/trend_rank 10`: xem bảng xếp hạng trend đã lưu theo điểm ưu tiên sản xuất video affiliate.
- `/handoff job=<ID> tool=claude|gemini|runway|kling|capcut|ffmpeg|fish|edge stage=...`: xuất prompt giao việc cho AI/tool khác và chuyển job sang `waiting`.
- `/publish_pack job=<ID>`: tạo gói caption, hashtag, CTA, link affiliate và checklist trước khi đăng.
- `/review_gate job=<ID>`: AI kiểm duyệt quyền hình ảnh/âm thanh, affiliate claim, CTA và rủi ro nền tảng trước khi đăng.
- `/creative_test job=<ID> n=5`: sinh nhiều biến thể hook/caption/CTA để A/B test video affiliate.
- `/creative_variants <JOB_ID>`: xem các biến thể creative của job.
- `/creative_select id=<VARIANT_ID>`: chọn biến thể creative để đưa vào stage script/sản xuất.
- `/creative_report job=<ID>`: so sánh performance theo biến thể creative đã gắn khi ghi dữ liệu.
- `/manifest job=<ID> duration=45 variant=<VARIANT_ID>`: tạo production manifest JSON gồm scene, prompt video, voice, edit, publish và compliance cho AI/tool thực thi.
- `/manifests <JOB_ID>`: xem các production manifest đã tạo cho job.
- `/manifest_handoff job=<ID> tool=kling|runway|fish|capcut|ffmpeg|publish|review`: xuất prompt riêng từ manifest cho từng AI/tool thực thi.
- `/task_plan job=<ID>`: tách manifest mới nhất thành các task scene/voice/edit/review/publish.
- `/tasks job=<ID>`: xem hàng việc sản xuất chi tiết theo job.
- `/next_task job=<ID>`: lấy task ưu tiên tiếp theo và tự chuyển sang `working` để giao cho AI/tool.
- `/task_handoff id=<TASK_ID>`: xuất prompt giao riêng một task cho AI/tool.
- `/task_set id=<TASK_ID> status=ready url=https://... note=...`: cập nhật task, tự lưu output thành asset nếu có URL.
- `/queue_publish job=<ID> mode=manual|api schedule=... note=...`: đưa job đã duyệt vào hàng đợi đăng.
- `/publish_queue`: xem hàng đợi đăng.
- `/publish_queue_set id=<QUEUE_ID> status=published|blocked|scheduled url=https://... note=...`: cập nhật trạng thái hàng đợi đăng.
- `/asset_add job=<ID> type=script|voice|raw_video|subtitle|thumbnail|final_video url=... note=...`: lưu asset/link/file vào production job.
- `/assets <JOB_ID>`: xem toàn bộ asset đã lưu của job.
- `/job_report <JOB_ID>`: báo cáo tổng hợp brief, asset, publish queue, publish URL, affiliate và performance của một job.
- `/job_ready job=<JOB_ID>`: kiểm tra job đã đủ brief, affiliate, creative, manifest, task, final video, review và publish queue trước khi đăng chưa.
- `/mark_published job=<ID> url=https://... views=0 clicks=0 note=...`: ghi nhận bài đã đăng thủ công, lưu URL và chuyển job sang `published`.
- `/performance_add job=<ID> variant=<VARIANT_ID> type=view|click|order|revenue|lead value=... amount=... note=...`: ghi hiệu quả bài đăng/affiliate, có thể gắn vào biến thể creative.
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
- `GET /api/operator/tasks/next`: worker ngoài lấy task đang chờ, hỗ trợ query `job_id` và `tool`, cần `Authorization: Bearer OPERATOR_API_TOKEN`.
- `POST /api/operator/tasks/{task_id}/complete`: worker ngoài trả `status`, `output_url`, `note`; bot tự lưu asset theo loại task và báo admin.
- `GET /api/operator/jobs/{job_id}/ready`: worker ngoài kiểm tra job đã đủ điều kiện review/publish chưa.
- `GET /api/operator/publish/next`: publisher worker lấy bài trong publish queue, hỗ trợ query `platform` và `mode`, rồi chuyển queue sang `publishing`.
- `POST /api/operator/publish/{queue_id}/complete`: publisher worker trả `status`, `publish_url`, `views`, `clicks`, `note`; bot cập nhật job và performance.
- `POST /api/operator/performance`: worker ngoài gửi `job_id`, `event_type=view|click|order|revenue|lead|cost`, `value`, `amount`, `variant_id`, `source`, `note` để bot tự ghi hiệu quả affiliate.

## Ghi chú kiến trúc

- `bot.py` hiện là file chạy chính.
- Thư mục `handlers/` là mã legacy từ phiên bản cũ, chưa được import trong runtime hiện tại.
- SQLite phù hợp bản nhỏ. Khi public nhiều người dùng, nên chuyển sang PostgreSQL hoặc tách lớp repository để kiểm soát transaction tốt hơn.
- AI Operator v1 mới tạo kế hoạch video/caption/affiliate, lịch nội dung và production pipeline để admin duyệt/điều phối. Auto-post lên TikTok/Facebook/YouTube/OnlyFans cần cấu hình API/OAuth chính thức ở giai đoạn sau.
- AI Brain là lớp điều khiển admin-only phía trên AI Operator: admin có thể gõ lệnh tự nhiên trong Telegram, bot sẽ phân tích intent và gọi đúng luồng nội bộ thay vì phải nhớ toàn bộ cú pháp.
- Autopilot là lớp batch admin-only: một lệnh sẽ tìm trend, tạo job và chuẩn bị production bundle gồm creative variant, manifest và task. Video vẫn phải qua task output, review gate và publish queue trước khi đăng thật.
- Operator API Bridge là cổng bảo mật cho n8n/Claude/tool worker: tool ngoài có thể lấy task, chạy Kling/Fish/CapCut/FFmpeg hoặc quy trình khác, rồi trả output URL về bot. Publisher worker cũng có thể lấy publish queue, đăng qua API chính thức/thủ công có kiểm soát và trả publish URL về bot. Bridge chỉ bật khi có `OPERATOR_API_TOKEN`.
- Channel/affiliate/calendar registry là khu vực admin-only để quản lý kênh Facebook/TikTok/OnlyFans, tài khoản phụ, link affiliate và lịch đăng nội dung. Không hiển thị cho khách hàng.
- Production pipeline là admin-only, dùng để theo dõi từng video qua các stage: `brief`, `script`, `voice`, `visuals`, `edit`, `review`, `publish`, `done`.
- Performance tracking là admin-only, dùng để ghi view/click/order/revenue/lead/cost sau khi đăng bài và theo dõi kênh hoặc affiliate nào đang tạo tiền. Dữ liệu có thể nhập bằng Telegram hoặc đẩy tự động qua Operator API Bridge.
- Trend search là admin-only, dùng để tìm trend mới trước khi tạo video; bot lưu trend candidate, tạo lịch/job từ trend và vẫn yêu cầu admin kiểm duyệt trước khi đăng.
- Operator auto là admin-only, dùng để tạo hàng loạt production job từ trend mới cho các channel active; vẫn đi qua review gate/publish queue trước khi đăng.
- Review gate là admin-only, dùng làm chốt kiểm duyệt trước khi đăng; job đạt có thể chuyển sang `ready`, job rủi ro chuyển `blocked`.
- Publish queue là admin-only, dùng để gom job đã duyệt vào hàng đợi đăng thủ công hoặc chuẩn bị sẵn điểm nối API/OAuth chính thức.
- Job ready check là admin-only, dùng như chốt cuối trước khi đưa video vào hàng đợi đăng; nếu thiếu asset/review/creative/manifest/task, bot trả về lệnh cần chạy tiếp.
- Production assets là admin-only, dùng để lưu script, voice, raw video, subtitle, thumbnail, final video hoặc source link theo từng job trước khi review/publish.
- Auto-post readiness là admin-only, dùng để kiểm tra channel nào có thể đăng thủ công, channel nào đã có `token_env` trỏ tới biến môi trường trên server, và channel nào còn thiếu cấu hình. Secret không lưu trong SQLite.
- Tool routing giữ đúng ý tưởng gốc: ưu tiên công cụ tốt/có phí trước, sau đó mới fallback sang công cụ ít phí/miễn phí. Gemini → OpenAI cho chat, Fish Audio HD → Edge TTS cho voice, RemoveBG HD → Cutout.pro cho tách nền. Khi gói cao cấp lỗi/quota, bot hoàn phần chênh lệch, chuyển sang gói dự phòng và báo admin kiểm tra quota/số dư/API key.
- Với AI influencer/người mẫu AI: chỉ dùng nhân vật tự tạo hoặc người thật có đồng ý rõ ràng, đủ 18 tuổi; không dùng để giả mạo, lừa đảo hoặc tạo nội dung vi phạm nền tảng/pháp luật.
