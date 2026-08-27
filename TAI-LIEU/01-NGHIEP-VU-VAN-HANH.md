# Nghiệp vụ vận hành Product Video

Đo tại branch `fix/product-video-post-deploy-finalizer-recovery`, ngày 2026-08-26.

## Phạm vi

- 9 dòng acceptance theo sản phẩm/lane trong tracker Product Video.
- 10 mức chất lượng công khai của Video AI Chân thật: `200`, `300`, `400`, `500`, `600`, `700`, `800`, `1000`, `1200`, `1500`.
- 3 mức chất lượng riêng của Ghép ảnh thành video: `fast`, `balanced`, `beautiful`.
- 1 Tail thương mại dùng chung, đúng 6 màn: `Add-on -> Review -> Quality -> Invoice -> Confirm -> Status`.

Nguồn tiến độ duy nhất: [P0_PRODUCT_VIDEO_FULL_LANE_LIVE_MATRIX.md](../.agents/state/P0_PRODUCT_VIDEO_FULL_LANE_LIVE_MATRIX.md).

## Đường đi hiện tại

1. Khách mở đúng sản phẩm/lane và tự nhập nội dung.
2. Bot giữ nguyên nội dung, nguồn ảnh/video và dựng kế hoạch tối thiểu 2 cảnh mà chưa gọi provider.
3. Lane cần media phải vượt asset gate; thiếu media dừng trước Tail.
4. Bot mở Add-on, sau đó Review, Chất lượng, Hóa đơn, Xác nhận và Trạng thái.
5. Chỉ Xác nhận cuối mới được admission; callback lặp không được tạo job thứ hai.
6. MP4 cuối phải hợp lệ và giao Telegram thành công trước khi ghi Xu.

## Chất lượng

- Video AI Chân thật phải hiển thị và giữ đúng cả 10 tier từ nút chọn qua hóa đơn/xác nhận.
- Script/Storyboard không nhận tier `200` hoặc `700`; callback giả/stale bị service từ chối trước mutation.
- Video dài tập không nhận tier `700`.
- Ghép ảnh giữ bảng giá/chất lượng Frame riêng, không fallback sang tier Video AI.

## Back và khôi phục

- Back từ Add-on trở về đúng owner vừa nhập: Trend, UIFLOW3, Scene3, Storyboard, Self-shot hoặc Video Idea dynamic.
- Parent snapshot được lưu trong session để bot restart vẫn khôi phục đúng màn cha.
- Status/refresh chỉ đọc; không submit lại, không tạo outbox mới và không chạm ví.

## Bằng chứng source hiện tại

- SPEC-01: `21 passed, 1 warning in 592.76s`.
- SPEC-02: `17 passed, 1 warning in 11.07s`.
- SPEC-03 regression branch: `79 passed, 11 failed`; baseline `origin/main cd4acb8`: `16 passed, 11 failed` cùng 11 test names, nên `NEW_FAILURES=0`.
- Audio/mux pure gates: 5 selectors pass + 1 replacement comparator pass; selector FFmpeg thật bị Windows `WinError 6` trước spawn và không được tính PASS.
- `py_compile bot.py services/video_tail9.py services/product_video_owner_recovery.py`: exit `0`.
- Post-rebase trên `origin/main 371a422`: 2 focused files `38 passed, 1 warning in 483.56s`; compile 3 runtime files và diff-check đều exit `0`.
- Sau SubDub PR #889, rebase tiếp lên `origin/main f16fb75`: 2 focused files `38 passed, 1 warning in 758.99s`; compile 3 runtime files exit `0`.
- Job/artifact/receipt live của matrix mới: **pending**.

## Bẫy vận hành

- Không suy ra PASS từ HTTP 200, queued state hoặc provider task id; cần MP4 + receipt Telegram.
- Không cho callback chất lượng tự ghi tier trước khi kiểm tra compatibility.
- Không dùng fallback Video AI cho Frame; Frame có engine, giá và quality owner riêng.
- Không coi test lỗi do harness Windows là regression; phải chạy baseline cùng lệnh và so test names.
- `MERGED != DEPLOYED != LIVE`; bot và worker phải cùng merge SHA và heartbeat accepted trước live.

## Việc còn treo

- Push/PR/merge/deploy runtime mới.
- 9 dòng live sản phẩm/lane, mỗi dòng kịch bản riêng và MP4 tối thiểu 2 cảnh.
- 10 live job Video AI Chân thật, mỗi tier một kịch bản 2 cảnh riêng.
- Mọi dòng cần artifact hash/bytes/codec/duration/audio, delivery message id và Owner `0 Xu`.

## Bổ sung vận hành Public Landing — Motion 26/08/2026

- Phạm vi production của đợt này là đúng `1` file: `index.html`; thêm `1` file contract test. Không đổi `bot.py`, `/lead`, nội dung, locale, CTA, ENV, dữ liệu, Telegram, PayOS hoặc ví.
- Hero có đúng `5` phần tử, luôn hiện với opacity `1`, chỉ settle `8px` trong `360ms`, delay `0/50/100/150/150ms`; tổng dài nhất `510ms`.
- Section fade-up `20px`, `480ms`, reveal một lần. Dữ liệu vị trí lấy từ `IntersectionObserverEntry`; không gọi đồng bộ `getBoundingClientRect()` lúc khởi tạo.
- Parallax chỉ chạy desktop có chuột chính xác, giới hạn `10px` mỗi trục và gộp sự kiện bằng `requestAnimationFrame`.
- Tablet, mobile và `prefers-reduced-motion: reduce` không chạy presentation motion; nội dung vẫn hiện nếu JavaScript hoặc observer lỗi.
- Hai lượt render, mỗi lượt `6` trường hợp: CLS `0`, long task trên `200ms` bằng `0`, overflow/pending/replay/lỗi runtime bằng `0`.
- Đợt này có `0` provider call, `0` wallet mutation, `0` production-data mutation, `0` ENV mutation và `0` Telegram mutation.
- Local đã verify; merge, deploy và live test vẫn là các cổng riêng.

## Bổ sung vận hành SubDub tự động 2 giọng — 27/08/2026

- Thứ tự khóa: combo `Phụ đề + Lồng tiếng` phải giao MP4 + SRT + receipt trước;
  sau đó lane `Lồng tiếng video` phải giao MP4 + receipt; chỉ khi cả hai PASS mới
  được chạy `Tự động nhiều giọng`.
- Fixture acceptance hai giọng: `2 giọng nam nữ.mp4`, `4,284,017` bytes,
  SHA-256 `85C8793D197CF2782BB554D46282E82A83BCB062A0483E412A0CA1DA668F9F51`.
- Engine hai giọng là exact Git blob PR #842
  `6634191cb2c0d463b86d7d9b58ded94e493a7b07`; multi engine giữ hash
  `55AAB8949EFAECAD8DD987AC6DFE056AB0E4BC4EF81A23977EA5EDD1CDF64911`.
- Job live `#EE4E7E69CD` trên runtime `085a1aaa` đã lưu đúng source hash nhưng
  dừng `empty_transcript` trước sidecar/cast/TTS/mux; wallet trước/sau vẫn
  `credits=200`, `total_spent=0`, `transactions=0`, `credit_events=1`.
- File có AAC stereo `48.344s`; decode mono đo `mean=-12.2 dB`, `max=0.0 dB`,
  vì vậy không được phân loại lỗi này thành file im lặng.
- Default/manual Deepgram request vẫn dùng `nova-2`. Chỉ request đã xác nhận
  cần diarization đổi sang `nova-3-general` + `diarize_model=latest`; không đổi
  ENV/key, classifier, cast, TTS, pricing hoặc wallet.
- Bằng chứng source: RED `1 failed in 460.89s`; GREEN AST `1 passed in
  534.54s`; protected `9 passed in 1002.61s`; `py_compile bot.py` và
  `git diff --check` exit `0`.
- Bẫy: một apply-patch từng làm rơi `2,004` dòng Product Video; scope audit đã
  bắt được trước ship, toàn bộ `bot.py` được restore exact `origin/main`, rồi
  áp lại đúng `1` dòng. Luôn kiểm `git diff --numstat` trước test/commit.
- Merge/deploy và same-fixture LIVE PASS vẫn là cổng riêng; chưa có MP4 cuối thì
  không được ghi lane là hoàn tất.

## Bổ sung Product Video provider/giá — 27/08/2026

- Nguồn vận hành mới là `config/product_video_price_route_map_20260827.json`; bản đọc cho người nằm tại `docs/knowledge/PRODUCT_VIDEO_PRICE_ROUTE_MAP_20260827.md` và bản dự phòng đồng nhất tại `D:\TOANAAS\kiến thức`.
- Giá khách được khóa ở 10 mức: `80`, `110`, `160`, `200`, `220`, `220`, `370`, `370`, `1.260`, `2.360` Xu/cảnh; đơn 2 cảnh giảm 10% phần giá Video.
- Chỉ so provider khi cùng thời lượng và đủ capability; route đủ điều kiện có tổng chi phí bảo thủ thấp hơn đứng trước.
- Snapshot live: ShopAIKey `3.250 VND/USD`; Key4U `3.000 VND/USD`. Kling v3 tính theo giây, không phải theo lần tạo.
- Key4U hiện dùng `api.key4u.vn`. VEO, Kling và Hailuo có endpoint, payload và poll contract riêng.
- Bảng/provider snapshot ngày 11/08 trong `services/video_ai_real_pricing.py` chỉ là lịch sử dựng giá khách; không được dùng để quyết định runtime route ngày 27/08.
- ShopAIKey còn `59,29 USD` nhưng VEO trả `429 RESOURCE_EXHAUSTED`; đây là quota/capacity upstream, không phải số dư bằng 0.
- Mọi live PASS vẫn cần MP4 tối thiểu 2 cảnh, audio nghe được, add-on đã materialize, receipt Telegram và `charged_xu=0`.

## Bổ sung Product Video `NOT_START` và fallback có kiểm soát — 27/08/2026

- PV-L01 tạo đúng request `VID-20260827-87B9C2`, project `26`, job `22`, outbox `21`; hai scene task ShopAIKey được nhận nhưng cùng trả `NOT_START`, chưa có clip và `charged_xu=0`.
- `NOT_START` còn task id và chưa terminal phải giữ `continue_polling`; worker không được đổi nó thành `real_video_renderer_unavailable` chỉ vì chưa có `final_video_path`.
- Cờ durable `automatic_fallback_allowed=false` vẫn cấm retry/fallback ngầm. Ngoại lệ duy nhất trong đợt này là fallback Key4U có kiểm soát: final confirm + invoice đã xác nhận, bốn trường quote/budget cùng `144 Xu`, primary task có thật, chưa giao, chưa trừ Xu và `fallback_count=0`.
- Fallback dùng khóa idempotency theo `job + scene + provider`; quote lệch, thiếu xác nhận, đã giao, đã trừ hoặc đã fallback một lần đều fail-closed. Owner job vẫn có receipt `0 Xu`; khách thật vẫn giữ nguyên quote và chỉ charge sau giao file hợp lệ.
- RED đo được `4 failed`, elapsed RED riêng expected `90`/actual `0`; focused GREEN cuối `6 passed`; protected gate `51 passed, 2 baseline deselected`; hai baseline fail tái hiện y hệt trên sạch `origin/main 21022ed`; compile ba runtime file và diff-check exit `0`.
- Đây mới là source PASS. PV-L01 vẫn chưa LIVE PASS cho tới khi cùng case giao MP4 2 cảnh có audio/phụ đề/chuyển cảnh và receipt Telegram `0 Xu`.
- Live rerun job `23` chứng minh elapsed đã đúng `66s/60s`, nhưng job-level `provider_order=[shopaikey_video]` ghi đè readiness cục bộ có cả ShopAIKey + Key4U; marker/decision durable cũng bị rơi nhưng cờ persisted `automatic_fallback_allowed=false` còn nguyên. Policy hiện vẫn tôn trọng chốt fail-closed đó và chỉ phục hồi `key4u_video` từ worker readiness khi toàn bộ final-confirm/exact-quote/task/no-delivery/no-charge/idempotency gates đã đạt; không phục hồi provider khác.
- Bằng chứng bổ sung: job `23` bounded recovery `3/3`, terminal `failed_no_charge`, focused candidate recovery `7 passed`, protected `52 passed`, `NEW_FAILURES=0`. Same-case LIVE rerun sau deploy tiếp theo vẫn bắt buộc.

## Bổ sung SubDub failure loop ASR — 27/08/2026

- PR `#904` đã merge/deploy runtime `8d23bbf1...`; job mới `#19A16753A4`
  vượt lỗi bảng trạng thái, hiện thật `35% / Nhận diện lời thoại`, rồi dừng
  `empty_transcript` trước sidecar/cast/TTS/mux/delivery. Admin vẫn `0 Xu`, ví
  không đổi.
- Deepgram `nova-3` nhận file `48.421s` với HTTP `200` nhưng trả `0` transcript,
  `0` word và `0` speaker; detect nhầm `id` ở confidence `0.31629473`. Ghim lại
  đúng mã đó vẫn rỗng, nên không tiếp tục thay model Deepgram mò mẫm.
- ShopAIKey không giao transcript cho fixture. Key4U canonical
  `https://api.key4u.vn/v1` giao `18` cue Whisper có timestamp và nhận đúng
  ngôn ngữ Chinese; hostname `.shop` cũ lỗi chứng thư và không bao giờ được tắt
  TLS verify để ép chạy.
- Gemini `gemini-3.5-transcribe` giao `125/125` word annotations có timestamp,
  đúng `2` speaker (`58` và `67` word). Đối chiếu thời gian map đủ `18/18` cue
  Key4U, split `8/10`, minimum dominance `1.0`.
- Fallback mới chỉ mở khi đồng thời: confirmed product + `require_diarization`
  + exact lane `Tự động 2 giọng` + Deepgram empty. Multi/default/manual không
  nhận cờ fallback. Thiếu đúng hai speaker, mỗi speaker dưới hai cue hoặc cue có
  dominance dưới `0.70` đều fail-closed, không ép cặp nam/nữ.
- Bằng chứng source cuối: initial RED `3 failed, 2 passed in 8.43s`; initial
  GREEN `5 passed in 1523.09s`; review RED service `1 failed/4 passed` và bot
  `3 failed`; review-fix GREEN service `5 passed`, bot `7 passed`; protected
  `19 passed in 543.25s`; compile và diff-check exit `0`.
  Hash locked: two-speaker engine `49E905C0...`, multi `55AAB894...`, cast
  `DE93620F...`.
- Đây mới là `CODE/PROVIDER_DIAGNOSTIC PASS`; combo và standalone vẫn phải giao
  MP4 thật qua Telegram sau deploy mới được ghi `LIVE PASS`.
