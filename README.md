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
- `COBALT_API_URL`, `COBALT_API_KEY`: API tải video sạch. Public `api.cobalt.tools` có bot protection, nên self-host Cobalt trên Railway để bot tải ổn định.
- `BOT_USERNAME`: username bot, ví dụ `Httdhtoan`.
- `PUBLIC_BASE_URL`: domain public nếu cần dùng cho link ngoài.
- `MANUAL_BANK_NAME`, `MANUAL_BANK_CODE`, `MANUAL_BANK_ACCOUNT`, `MANUAL_BANK_OWNER`: tài khoản và mã VietQR nạp thủ công khi PayOS lỗi.
- `OPERATOR_API_TOKEN`: token riêng cho n8n/Claude/tool worker gọi Operator API Bridge. Không set thì bridge tự đóng.

## Domain web

- Nếu mua được domain `toanaas.com`, `toanaas.vn` hoặc biến thể gần nhất, trỏ DNS về Railway Custom Domain theo hướng dẫn Railway.
- Sau khi domain hoạt động HTTPS, set `PUBLIC_BASE_URL=https://<domain>` trên Railway để landing page, tracking affiliate `/r/...`, PayOS return/cancel URL và n8n worker dùng đúng domain mới.
- Không cần đổi code khi đổi domain; chỉ cần cập nhật DNS và biến môi trường.

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
- `/brain <lệnh tự nhiên>`: đầu não admin-only, hiểu lệnh tiếng Việt và tự định tuyến sang Director, Execute an toàn, Operator Auto, tạo job, build job, job ready check hoặc báo cáo vận hành.
- Ví dụ `/brain scale affiliate 3 lên TikTok build luôn 3 video`: tự gọi `/affiliate_scale` để tìm trend, tạo job và build bundle cho link affiliate đó.
- Ví dụ `/brain tạo 3 video kiếm tiền về đồ công nghệ văn phòng lên TikTok`: tự gọi `/make_video`, bot tự chọn affiliate phù hợp nếu chưa truyền `aff`.
- Ví dụ `/brain đầu não chạy bước tiếp theo an toàn`: tự gọi `/operator_execute` để scale/build hoặc queue publish manual theo next action.
- `/make_video topic=... platform=tiktok channel=all aff=<ID> campaign=<ID> limit=3 build=1 duration=45`: lệnh gọn để tạo pipeline video kiếm tiền; nếu thiếu `aff`, bot tự chấm điểm và chọn link affiliate phù hợp, tìm trend, tạo job, build creative/manifest/task và chuẩn bị publish pack.
- `/autopilot niche=... platform=tiktok channel=all aff=<ID> campaign=<ID> limit=3 duration=45`: tìm trend, tạo production job và tự build creative/manifest/task cho batch video.
- `/operator_menu`: menu nút bấm dạng thư mục, gom lệnh theo Điều hành, Trend, Affiliate, Kênh/Lịch, Sản xuất, Đăng bài, Doanh thu và API.
- `/campaign_new name=... niche=... platforms=... affiliate=...`: tạo chiến dịch AI Operator.
- `/campaigns`: liệt kê chiến dịch.
- `/video_plan campaign=<ID> topic=... platforms=... channel=<ID> aff=<ID>`: AI tạo brief video, caption, hashtag, CTA và compliance checklist.
- `/video_job <ID>`: xem lại video job.
- `/campaign_stats`: thống kê campaign/video job.
- `/channel_add platform=... name=... account=... focus=... audience=... slots=2/day`: lưu kênh/tài khoản nội bộ.
- `/channels`: liệt kê kênh/tài khoản nội bộ.
- `/channel_publish_set id=<CHANNEL_ID> mode=manual|api token_env=... page_id=...`: cấu hình khả năng đăng thủ công/API cho kênh, chỉ lưu tên biến môi trường token.
- `/publish_readiness`: kiểm tra kênh nào sẵn sàng đăng thủ công hoặc đã đủ cấu hình API cơ bản.
- `/publisher_status`: kiểm tra riêng lớp publisher, gồm kênh manual/API-ready, queue đang mở, blocker token/env/page_id và endpoint tiếp theo cho worker.
- `/affiliate_add network=... product=... niche=... url=... price=... rate=... audience=... allowed=... blocked=...`: lưu link affiliate Shopee/Lazada/TikTok hoặc sàn khác kèm hồ sơ sản phẩm.
- `/affiliate_seed`: import bộ link affiliate mặc định của admin vào database, tự bỏ qua URL đã tồn tại để không tạo trùng.
- `/affiliates`: liệt kê link affiliate nội bộ.
- `/affiliate_profile id=<AFF_ID> price=... rate=... audience=... allowed=... blocked=... score=...`: cập nhật hồ sơ, claim được phép và claim cấm cho sản phẩm affiliate.
- `/affiliate_match niche=... platform=tiktok trend=...`: xếp hạng affiliate phù hợp với trend/niche để chọn link trước khi tạo video.
- `/affiliate_related aff=<AFF_ID>` hoặc `/affiliate_related brand=Samsung niche=điện thoại limit=12`: tìm link cùng brand/nhóm sản phẩm, gồm các cặp Android/iOS, để chèn thêm vào caption, comment ghim, status hoặc mô tả video.
- `/affiliate_bundle aff=<AFF_ID> job=<JOB_ID> platform=tiktok`: xuất một gói link chính + link liên quan theo caption/comment ghim/bio/status/reply comment, mỗi vị trí có tracking `src` riêng để đo hiệu quả.
- `/affiliate_ideas aff=<AFF_ID> platform=tiktok n=5 topic=...`: tạo hook, angle, outline, CTA và rủi ro kiểm duyệt cho video ngắn từ một link affiliate đã lưu.
- `/affiliate_report days=30 limit=15`: báo cáo link affiliate nào có job, bài đăng, view, click, conversion, doanh thu, chi phí và ROI để quyết định scale.
- `/affiliate_decisions days=30 platform=tiktok limit=12`: AI Operator phân loại từng link thành `SCALE`, `PUBLISH`, `FIX_CTA`, `FIX_OFFER`, `TEST` hoặc `PAUSE_CHECK`, kèm lệnh tiếp theo và link liên quan nên chèn kèm.
- `/affiliate_scale aff=<AFF_ID> platform=tiktok channel=all limit=5 campaign=<ID> build=1 duration=45`: lấy niche của affiliate, tự chọn campaign active phù hợp nếu chưa truyền `campaign`, tìm trend phù hợp, tạo batch production job gắn sẵn link đó; thêm `build=1` để tự tạo creative variants, manifest và production tasks.
- `/calendar_plan days=7 channel=all campaign=<ID> aff=<ID> niche=...`: tạo lịch nội dung theo kênh.
- `/calendar`: xem lịch nội dung đã lên.
- `/operator topic=... channel=<ID> aff=<ID> campaign=<ID> date=YYYY-MM-DD`: ra lệnh một bước để tạo lịch nội dung + production job + brief AI.
- `/operator_build job=<ID> n=5 duration=45`: tự tạo creative variants, chọn biến thể tốt nhất, tạo manifest và tách task sản xuất cho một job.
- `/operator_auto niche=... platform=tiktok channel=all aff=<ID> campaign=<ID> limit=5`: tự tìm trend, chấm điểm ưu tiên affiliate và tạo batch production job cho nhiều kênh active.
- `/operator_next id=<JOB_ID> stage=script|voice|visuals|edit|review|publish`: AI điều phối stage tiếp theo, kèm tool chính/fallback và output cần lưu.
- `/operator_dashboard`: tổng quan kênh, affiliate, lịch sắp tới và production job cần xử lý.
- `/operator_loop limit=10 queue=1`: quét job đang mở, tự đưa job đủ điều kiện vào publish queue và báo task tiếp theo cho worker.
- `/operator_api`: xem trạng thái `OPERATOR_API_TOKEN`, base URL và mẫu endpoint/payload cho n8n/Claude/tool worker.
- `/operator_worker_spec`: xuất runbook JSON cho Claude/n8n/tool worker, gồm role, endpoint, payload mẫu và safety rules.
- `/operator_toolchain`: xem registry công cụ theo stage, tool chính có phí/chất lượng cao, fallback ít phí/miễn phí, env còn thiếu và protocol khi lỗi/quota.
- `/operator_tool_readiness`: kiểm tra runtime thật của các tool quan trọng; cảnh báo public Cobalt, thiếu key AI/voice/image/payment/operator trước khi bật full auto.
- `/operator_tool_events`: xem hoặc ghi sự cố tool/quota/fallback; ví dụ `stage=voice tool=Fish type=quota fallback=Edge message=het_quota`.
- `/operator_n8n_template`: xuất template workflow n8n an toàn: Cron, audit, make-video/director-run, task worker, publisher status/run/handoff và performance tracker.
- `/operator_n8n_workflow`: lấy URL JSON workflow có thể import vào n8n, mặc định inactive và giữ publisher-run/review gate trước khi đăng thật.
- `/operator_director days=30 platform=tiktok limit=10`: trả đúng một next action ưu tiên cho admin/Claude/n8n, kèm Telegram command hoặc API endpoint/payload cần gọi.
- `/operator_execute days=30 platform=tiktok build=1 duration=45`: chạy action an toàn tiếp theo từ director, ví dụ scale affiliate thành job/bundle hoặc đưa job ready vào publish queue; không tự đăng bài thật.
- `/operator_audit`: kiểm tra end-to-end hệ thống đầu não, gồm Telegram brain, API token, AI provider, PayOS, affiliate catalog, channel, publish readiness, production pipeline và performance tracking.
- `/operator_smoke`: smoke test nhẹ không tạo job, kiểm tra env, DB, file logo/landing, API surface, worker spec, n8n workflow và publisher readiness.
- `/operator_status`: kiểm tra hệ thống đã sẵn sàng scale chưa, gồm channel, affiliate, campaign, API token, publish readiness, queue, task và job blocked.
- `/operator_today`: kế hoạch ưu tiên trong ngày, tự gom việc setup còn thiếu, job blocked, task kế tiếp, publish queue và affiliate nên scale.
- `/operator_playbook`: checklist vận hành từ kiểm tra hệ thống, chọn affiliate, tạo video theo trend, giao task cho AI/tool, review, publish và đo doanh thu.
- `/operator_daily days=1`: báo cáo vận hành theo ngày gồm job mới, publish queue, performance và việc cần xử lý.
- `/trend_search niche=... platform=tiktok channel=<ID> aff=<ID> campaign=<ID>`: tìm trend mới từ nguồn RSS/news công khai, chấm điểm trend/affiliate/cạnh tranh và hiện nút tạo video trend vào pipeline.
- `/trend_rank 10`: xem bảng xếp hạng trend đã lưu theo điểm ưu tiên sản xuất video affiliate.
- `/handoff job=<ID> tool=claude|gemini|runway|kling|capcut|ffmpeg|fish|edge stage=...`: xuất prompt giao việc cho AI/tool khác và chuyển job sang `waiting`.
- `/publish_pack job=<ID>`: tạo gói caption, hashtag, CTA, disclosure, link affiliate chính, link liên quan/comment ghim, checklist compliance và kế hoạch ghi performance trước khi đăng.
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
- `/task_set id=<TASK_ID> status=ready urls=https://a.mp4,https://b.mp4 type=raw_video`: lưu nhiều output scene/audio/video cho cùng task.
- `/queue_publish job=<ID> mode=manual|api schedule=... note=...`: đưa job đã duyệt vào hàng đợi đăng.
- `/publish_queue`: xem hàng đợi đăng.
- `/publisher_handoff queue=<QUEUE_ID>`: xuất runbook đăng bài theo nền tảng cho publisher worker hoặc đăng thủ công, gồm final video, caption, comment ghim, env token cần có và payload trả kết quả.
- `/publisher_run platform=tiktok mode=api`: claim queue kế tiếp và trả quyết định `api_ready`, `manual_required` hoặc `blocked_missing_final_video` cho publisher worker/admin.
- `/publish_queue_set id=<QUEUE_ID> status=published|blocked|scheduled url=https://... note=...`: cập nhật trạng thái hàng đợi đăng.
- `/asset_add job=<ID> type=script|voice|raw_video|subtitle|thumbnail|final_video url=... note=...`: lưu asset/link/file vào production job.
- `/assets <JOB_ID>`: xem toàn bộ asset đã lưu của job.
- `/job_report <JOB_ID>`: báo cáo tổng hợp brief, asset, publish queue, publish URL, affiliate và performance của một job.
- `/job_context job=<JOB_ID>`: xuất context máy đọc được cho Claude/n8n/tool worker, gồm job, readiness, assets, creative, manifest, tasks, next_task, publish pack và runbook.
- `/job_ready job=<JOB_ID>`: kiểm tra job đã đủ brief, affiliate, creative, manifest, task, final video, review và publish queue trước khi đăng chưa.
- `/approve_publish job=<ID> queue=1 mode=manual note=...`: duyệt cuối sau review gate/final video; có thể tự đưa job vào publish queue manual/API.
- `/mark_published job=<ID> url=https://... views=0 clicks=0 note=...`: ghi nhận bài đã đăng thủ công, lưu URL và chuyển job sang `published`.
- `/performance_add job=<ID> variant=<VARIANT_ID> type=view|click|order|revenue|lead value=... amount=... note=...`: ghi hiệu quả bài đăng/affiliate, có thể gắn vào biến thể creative.
- `/performance`: báo cáo hiệu quả theo loại sự kiện, kênh và job gần nhất.
- `/tracking_report days=30 limit=10`: báo cáo funnel theo affiliate, source tracking URL/postback và job để biết link nào nên scale.
- `/scale_plan days=30 platform=tiktok limit=10`: kế hoạch hành động từ funnel, phân loại link/source/job thành `SCALE`, `FIX_CTA`, `FIX_OFFER`, `TEST_MORE`, `PAUSE_CHECK`.
- `/scale_execute days=30 platform=tiktok limit=3 per=3 build=1`: chạy an toàn các mục `SCALE` trong scale plan, tạo job video mới và build manifest/task nếu bật.
- `/growth days=14`: xếp hạng job/kênh/creative theo view, click, order, revenue, cost và đề xuất lệnh sản xuất/remix tiếp theo.
- `/produce slot=<calendar_id>`: tạo production job từ lịch nội dung, kèm brief AI nếu đã cấu hình provider.
- `/pipeline`: xem hàng đợi sản xuất video.
- `/pipeline <ID>`: xem chi tiết production job.
- `/pipeline_set id=<ID> stage=edit status=working asset=https://... publish=https://... note=...`: cập nhật pipeline.

## API FastAPI

- `GET /`: health check.
- `GET /landing`: phục vụ landing page `index.html` cùng domain với API.
- `GET /r/{affiliate_id}?job=<JOB_ID>&src=<SOURCE>`: redirect sang link affiliate gốc và tự ghi click vào performance khi có `job`.
- `POST /api/affiliate/postback`: nhận conversion/order/lead/revenue từ n8n hoặc network affiliate, hỗ trợ `AFFILIATE_POSTBACK_TOKEN`.
- `POST /webhook/payos`: nhận webhook PayOS, kiểm tra chữ ký, mã đơn, số tiền, trạng thái và chống cộng xu trùng.
- `POST /lead`: nhận lead từ landing page và gửi thông báo về admin Telegram.
- `GET /api/operator/tasks/next`: worker ngoài lấy task đang chờ, hỗ trợ query `job_id`, `tool`, `include_context=1`, cần `Authorization: Bearer OPERATOR_API_TOKEN`.
- `GET /api/operator/tasks/claim?include_context=1`: alias claim task mới, trả luôn `job_context` để Claude/n8n/tool worker có đủ runbook trong một lần gọi.
- `GET /api/operator/status`: worker ngoài kiểm tra readiness tổng thể trước khi tự động scale hoặc publish.
- `GET /api/operator/smoke-test`: worker ngoài kiểm tra nhanh hệ thống trước khi bật cron/n8n; không tạo job/queue và không gọi API ngoài.
- `GET /api/operator/publisher/status`: worker ngoài kiểm tra readiness riêng cho publisher: kênh nào manual/API-ready, queue nào chờ đăng, blocker token/env/page_id.
- `POST /api/operator/publisher/run`: worker ngoài claim queue kế tiếp an toàn, nhận handoff và quyết định nên auto đăng qua API chính thức hay chuyển manual.
- `GET /api/operator/audit`: worker ngoài kiểm tra mức sẵn sàng end-to-end và blocker còn thiếu trước khi bật automation.
- `GET /api/operator/worker-spec`: worker ngoài đọc runbook máy đọc được cho Director, Creative, Tool Worker, Publisher và Growth Analyst.
- `GET /api/operator/toolchain`: worker ngoài đọc chính sách paid-first/fallback theo từng stage, gồm Claude/Gemini/OpenAI, Fish/Edge, RemoveBG/Cutout, Kling/Runway, CapCut/FFmpeg, publisher và payment.
- `GET /api/operator/tool-readiness`: worker ngoài kiểm tra tool nào thật sự đủ runtime/env để bật automation, đặc biệt Cobalt self-host, AI provider, voice, image, PayOS và Operator API.
- `GET/POST /api/operator/tool-events`: worker ngoài báo tool lỗi/quota/hết tiền/fallback/recovered; bot lưu log và nhắn admin khi severity `warning|critical`.
- `GET /api/operator/n8n-template`: worker ngoài đọc template workflow n8n có sẵn cho cron, audit, director-run, task worker, publish pack, publisher và performance tracking.
- `GET /api/operator/n8n-workflow.json`: trả JSON workflow import được vào n8n, dùng env `OPERATOR_BASE_URL` và `OPERATOR_API_TOKEN`, có gate thủ công trước khi publish.
- `GET /api/operator/director`: endpoint “đầu não” cho Claude/n8n, gom setup, blocker, task, publish queue và affiliate decisions thành một next action có method/url/payload rõ ràng.
- `POST /api/operator/director/run`: chạy action an toàn tiếp theo từ director; scale affiliate/build job hoặc queue publish manual, nhưng không tự publish ngoài mạng xã hội.
- `GET /api/operator/today`: worker ngoài lấy danh sách hành động ưu tiên trong ngày, gồm setup, task, publish queue và affiliate nên scale.
- `POST /api/operator/tasks/{task_id}/complete`: worker ngoài trả `status`, `output_url` hoặc `output_urls`, `asset_type`, `note`; bot tự lưu asset theo loại task và báo admin. `failed` được quy về `blocked` để pipeline không kẹt im lặng.
- `POST /api/operator/tasks/{task_id}/upload`: worker ngoài upload file thật dạng multipart khi Kling/CapCut/Fish/FFmpeg chưa có public URL; bot lưu vào `operator_uploads`, tạo asset URL nội bộ và cập nhật task.
- `POST /api/operator/jobs/{job_id}/assets/upload`: upload asset trực tiếp vào job.
- `GET /api/operator/assets/{asset_id}/file`: tải asset nội bộ, cần `Authorization: Bearer OPERATOR_API_TOKEN` hoặc `?token=...`.
- `GET /api/operator/jobs/{job_id}/ready`: worker ngoài kiểm tra job đã đủ điều kiện review/publish chưa.
- `GET /api/operator/jobs/{job_id}/context`: worker ngoài lấy toàn bộ context và runbook của một job trong một lần gọi, thay vì phải tự ghép nhiều endpoint rời.
- `POST /api/operator/jobs/{job_id}/approve`: duyệt cuối job đã đủ điều kiện và tùy chọn đưa vào publish queue; dùng làm gate trước khi n8n/publisher lấy bài đăng.
- `GET /api/operator/jobs/{job_id}/publish-pack`: worker ngoài lấy caption, CTA, disclosure, tracking URL affiliate chính, link liên quan, comment ghim, checklist compliance và kế hoạch ghi performance.
- `POST /api/operator/loop`: cron/n8n gọi vòng điều phối an toàn với `limit`, `auto_queue`, `notify_admin`; bot tự queue job ready và trả task tiếp theo.
- `POST /api/operator/make-video`: endpoint một lệnh cho Claude/n8n tạo pipeline video kiếm tiền từ `topic`; bot tự chọn affiliate/campaign nếu thiếu, tìm trend, tạo job, build bundle và trả publish pack/tracking URL.
- `GET /api/operator/channels`: worker ngoài đọc danh sách kênh, topic focus, posting slots, publish mode và readiness manual/API để chọn nơi đăng.
- `GET /api/operator/campaigns`: worker ngoài đọc campaign active, niche, platform, affiliate/pay URL để chọn `campaign_id` khi scale.
- `GET /api/operator/affiliates`: worker ngoài đọc catalog affiliate active, gồm ID, niche, audience, claim được phép/cấm và link để chọn sản phẩm.
- `GET /api/operator/affiliate-bundle?affiliate_id=<AFF_ID>&job_id=<JOB_ID>`: worker ngoài lấy bundle link affiliate theo từng vị trí đăng, gồm tracking URL riêng cho caption/comment/status/bio để đo nguồn nào hiệu quả nhất.
- `GET /api/operator/affiliate-report`: worker ngoài đọc hiệu quả theo affiliate gồm job, publish, view, click, conversion, revenue, cost, ROI để chọn link nên scale.
- `GET /api/operator/tracking-report`: worker ngoài đọc funnel theo affiliate/source/job, gồm CTR, CVR, ROI, revenue và gợi ý scale/fix/pause.
- `GET /api/operator/scale-plan`: worker ngoài lấy kế hoạch hành động từ funnel để tự gọi scale affiliate, sửa CTA/offer hoặc tạm dừng nguồn kém.
- `POST /api/operator/scale-plan/run`: worker ngoài chạy các mục `SCALE` đủ điều kiện, tạo batch production job và optional build creative/manifest/task.
- `GET /api/operator/affiliate-decisions`: worker ngoài lấy quyết định scale/fix/test/pause cho từng affiliate, gồm lệnh Telegram/API gợi ý và danh sách link liên quan để chèn thêm.
- `POST /api/operator/affiliate-scale`: n8n/Claude worker gửi `affiliate_id`, `platform`, `channel`, `limit`, `build`, `duration`; nếu không gửi `campaign_id`, bot tự chọn campaign active phù hợp rồi tìm trend, tạo batch job và có thể build luôn creative/manifest/task cho link affiliate.
- `GET /api/operator/publish/next`: publisher worker lấy bài trong publish queue, hỗ trợ query `platform` và `mode`, rồi chuyển queue sang `publishing`.
- `GET /api/operator/publish/{queue_id}/handoff`: lấy runbook đăng bài cho queue đã duyệt, phân biệt TikTok, Facebook/Reels, OnlyFans/manual và trả sẵn copy/pinned comment/complete payload.
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
- `/operator_api` là lệnh admin-only để lấy checklist cấu hình n8n/worker mà không lộ token thật.
- `/make_video` và `POST /api/operator/make-video` là lớp lệnh gọn cho mục tiêu “ra lệnh trên Telegram/API là có pipeline video affiliate”; hệ thống vẫn giữ gate review/approve trước khi đăng thật để tránh spam, claim sai hoặc vi phạm nền tảng.
- Channel/affiliate/calendar registry là khu vực admin-only để quản lý kênh Facebook/TikTok/OnlyFans, tài khoản phụ, link affiliate và lịch đăng nội dung. Không hiển thị cho khách hàng.
- Production pipeline là admin-only, dùng để theo dõi từng video qua các stage: `brief`, `script`, `voice`, `visuals`, `edit`, `review`, `publish`, `done`.
- Performance tracking là admin-only, dùng để ghi view/click/order/revenue/lead/cost sau khi đăng bài và theo dõi kênh hoặc affiliate nào đang tạo tiền. Dữ liệu có thể nhập bằng Telegram hoặc đẩy tự động qua Operator API Bridge.
- Growth optimizer là admin-only, dùng dữ liệu performance để chọn job/creative/kênh thắng, gợi ý remix hoặc chạy autopilot tiếp theo thay vì sản xuất mù.
- Trend search là admin-only, dùng để tìm trend mới trước khi tạo video; bot lưu trend candidate, tạo lịch/job từ trend và vẫn yêu cầu admin kiểm duyệt trước khi đăng.
- Operator auto là admin-only, dùng để tạo hàng loạt production job từ trend mới cho các channel active; vẫn đi qua review gate/publish queue trước khi đăng.
- Operator loop là admin-only, dùng để chạy một vòng điều phối an toàn: tự queue publish cho job đã ready, liệt kê task kế tiếp cho worker ngoài và chỉ ra job nào còn nghẽn. Có thể chạy bằng Telegram hoặc cron/n8n qua `POST /api/operator/loop`.
- Review gate là admin-only, dùng làm chốt kiểm duyệt trước khi đăng; job đạt có thể chuyển sang `ready`, job rủi ro chuyển `blocked`.
- Publish queue là admin-only, dùng để gom job đã duyệt vào hàng đợi đăng thủ công hoặc chuẩn bị sẵn điểm nối API/OAuth chính thức.
- Publisher handoff là lớp nối giữa bot và publisher worker: bot không lưu secret nền tảng, chỉ trả tên biến môi trường/token cần có, nội dung cần đăng và endpoint để worker báo kết quả.
- Publisher status là chốt vận hành cho auto-post: cron/n8n nên gọi trước khi claim queue để biết có kênh API-ready hay chỉ nên trả handoff cho admin đăng thủ công.
- Publisher run là bước cron/n8n an toàn: claim một queue, kiểm tra final video/token/mode, trả handoff và chỉ cho API worker đăng khi kênh thật sự `api_ready`.
- Worker spec/n8n workflow đã có endpoint mới `/api/operator/make-video`, `/api/operator/publisher/status` và `/api/operator/publisher/run` để Claude/n8n chạy theo cùng một runbook với Telegram.
- Operator smoke test là chốt nhẹ trước khi bật automation: nếu fail ở env/file/db/surface thì xử lý trước, nếu chỉ warning ở audit/publisher thì vẫn có thể chạy manual nhưng chưa nên bật full auto.
- Job ready check là admin-only, dùng như chốt cuối trước khi đưa video vào hàng đợi đăng; nếu thiếu asset/review/creative/manifest/task, bot trả về lệnh cần chạy tiếp.
- Production assets là admin-only, dùng để lưu script, voice, raw video, subtitle, thumbnail, final video hoặc source link theo từng job trước khi review/publish.
- Auto-post readiness là admin-only, dùng để kiểm tra channel nào có thể đăng thủ công, channel nào đã có `token_env` trỏ tới biến môi trường trên server, và channel nào còn thiếu cấu hình. Secret không lưu trong SQLite.
- Tool routing giữ đúng ý tưởng gốc: ưu tiên công cụ tốt/có phí trước, sau đó mới fallback sang công cụ ít phí/miễn phí. Gemini → OpenAI cho chat, Fish Audio HD → Edge TTS cho voice, RemoveBG HD → Cutout.pro cho tách nền. Khi gói cao cấp lỗi/quota, bot hoàn phần chênh lệch, chuyển sang gói dự phòng và báo admin kiểm tra quota/số dư/API key.
- Với AI influencer/người mẫu AI: chỉ dùng nhân vật tự tạo hoặc người thật có đồng ý rõ ràng, đủ 18 tuổi; không dùng để giả mạo, lừa đảo hoặc tạo nội dung vi phạm nền tảng/pháp luật.
