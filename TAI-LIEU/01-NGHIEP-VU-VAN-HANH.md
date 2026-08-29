# Nghiệp vụ vận hành Product Video

Đo từ `KIEM-THU/product-video-live-strategy-v2.json` và source Product Video tại
local commit `d7f296d2a00eba050d437ca51962d33acc5b4ffa`, ngày 2026-08-28.

## Phạm vi

- 8 representative rows theo sản phẩm/lane: 19 cảnh; trong đó Kịch bản -> Video
  dùng 5 cảnh, 7 row còn lại dùng 2 cảnh.
- 9 quality-only rows, mỗi row 1 cảnh; tier `400` đã được 8 representative rows
  bao phủ nên không tạo quality-only job thứ mười.
- Trần live: 17 final jobs, 28 assigned scene renders, 4 source-image tasks và
  tối đa 32 external create calls.
- 10 mức chất lượng công khai của Video AI Chân thật: `200`, `300`, `400`, `500`, `600`, `700`, `800`, `1000`, `1200`, `1500`.
- 3 mức chất lượng riêng của Ghép ảnh thành video: `fast`, `balanced`, `beautiful`.
- 1 Tail thương mại dùng chung, đúng 6 màn: `Add-on -> Review -> Quality -> Invoice -> Confirm -> Status`.

Nguồn tiến độ duy nhất: [P0_PRODUCT_VIDEO_FULL_LANE_LIVE_MATRIX.md](../.agents/state/P0_PRODUCT_VIDEO_FULL_LANE_LIVE_MATRIX.md).

## Đường đi hiện tại

1. Khách mở đúng sản phẩm và lane phức tạp không-manual được giao trong Strategy V2.
2. Lane tự nhập vẫn bắt buộc nhận nội dung khách rồi đi thẳng vào Tail, nhưng chỉ
   dùng source-contract test; không tạo paid representative job trùng lặp.
3. Bot giữ nguyên nội dung, nguồn ảnh/video và dựng số cảnh khóa mà chưa gọi provider.
4. Lane cần media phải vượt asset gate; thiếu media dừng trước Tail.
5. Bot mở Add-on, sau đó Review, Chất lượng, Hóa đơn, Xác nhận và Trạng thái.
6. Chỉ Xác nhận cuối mới được admission; callback lặp không được tạo job thứ hai.
7. MP4 cuối phải hợp lệ và giao Telegram thành công trước khi ghi Xu.
8. Sau khi receipt đã bền vững và settlement đã biết, bot gửi đúng 1 báo cáo kinh
   doanh: sản phẩm, chất lượng, cảnh/thời lượng/tỉ lệ, giá video, Add-on miễn phí/
   có phí/đã áp dụng, tổng hóa đơn, Xu thực trả và trạng thái giao thành công.

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
- 8 representative rows V2, mỗi row kịch bản riêng; 7 row cần MP4 tối thiểu 2
  cảnh, Kịch bản -> Video cần đúng 5 cảnh.
- 9 quality-only rows được phân cho các sản phẩm tương thích, mỗi row 1 cảnh;
  không dồn toàn bộ quality coverage vào Video AI Chân thật.
- Mọi dòng cần artifact hash/bytes/codec/duration/audio, delivery message id và Owner `0 Xu`.
- `multi_scene_film` / Video dài tập bị loại khỏi chu kỳ hiện tại. `video_local_edit`
  là sản phẩm đã khóa; `videoedit|ai` hoãn cùng Long Video. Không sửa hoặc live-test
  ba boundary này cho tới lệnh Owner mới.

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

- Thứ tự khóa: combo `Phụ đề + Lồng tiếng` chỉ tự giao MP4 rồi receipt trước;
  sau đó lane `Lồng tiếng video` cũng chỉ tự giao MP4 rồi receipt; SRT/audio/
  sidecar là artifact nội bộ hoặc tải chủ động. Chỉ khi cả hai PASS mới
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
- Điều khiển âm thanh là một owner dùng chung cho cả `Lồng tiếng video` và
  `Phụ đề + Lồng tiếng`, không phụ thuộc giọng nữ/nam mặc định, Kho voice,
  voice riêng, `Tự động 2 giọng` hay `Tự động nhiều giọng`. Màn chính chỉ có
  `Âm thanh gốc | Giọng lồng tiếng` cùng một hàng và nút Quay lại; màn con cho
  nhập số gốc `0–100`, lồng `0–200`. PR #896 đã thêm nhầm `10` nút preset và
  `2` callback preset; bản rollback xóa đúng các phần đó, không đổi state/mux.
- Bằng chứng UI source hiện tại: RED `3 failed in 3.84s`; GREEN trọng tâm
  `35 passed, 3 warnings in 12.44s`, exit `0`; compile `bot.py` + `3` test files
  exit `0`. Matrix đo đủ `2 × 6 = 12` tổ hợp lane/voice và nhập thật
  `40% / 150%` ở cả hai lane. Batch rộng hơn có `58 passed`, `1 skipped` và
  đúng `1` failure copy baseline không thuộc diff.
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

## Bổ sung SubDub Key4U transcript retry — 28/08/2026

- Combo job `#00911B6FF0`, internal `00911b6ff01590de3834`, runtime
  `4458d4c` dùng đúng fixture SHA `85C8793D...` rồi dừng
  `failed_no_charge` trước SRT/sidecar/TTS/mux/delivery.
- Provider attempt thật: Deepgram empty đã vào đúng
  `key4u_audio+gemini_diarization`, nhưng Key4U lần đầu trả transcript không
  dùng được: `key4u_two_speaker_transcript_unavailable`.
- Một diagnostic production-equivalent duy nhất trên mono MP3 `582,540` bytes
  ngay sau lỗi trả HTTP `200`, `145` ký tự và `18/18` segment timestamp
  phủ `0..48s`. Vì vậy model/fixture/endpoint dùng được; lỗi thuộc phản hồi
  tạm thời, không thuộc classifier/cast.
- Runtime fallback chỉ được retry tối đa `1` lần sau attempt đầu: tổng tối đa
  `2` Key4U calls, delay `1s`; permanent `401` hoặc timestamp giả/thiếu
  vẫn dừng ngay trước Gemini. Deepgram-first, multi, UI, giá, ví, TTS và mux
  không đổi.
- Evidence source: RED `2 failed in 0.88s`; GREEN service `7 passed in
  0.43s`; bot isolation `7 passed in 11.73s`; locked hashes `2 passed in
  7.95s`; compile/diff exit `0`. Admin wallet vẫn `200/0`, transactions
  `0`.
- Retry job `#A86321F62B` chứng minh cả hai production attempts đều fail
  trước HTTP: `http=0 / FAIL_PROVIDER_ERROR`. Exact production-adapter
  diagnostic ghi lỗi `Attempted to send an sync request with an AsyncClient
  instance.`
- Root cause transport: OpenAI-compatible ASR gửi multipart bằng
  `httpx.AsyncClient` nhưng form `data` là sync `list[tuple]`. Bản sửa chỉ
  đổi container sang `dict`; model, endpoint, fields, retry, provider order,
  giá, ví và engine không đổi.
- Transport RED dùng real `AsyncClient + MockTransport`: `1 failed in
  14.26s`; GREEN `1 passed in 607.69s`; protected `17 passed in 9.72s`;
  compile/diff exit `0`.

- Live job `24` cho thấy server claim gate chạy trước connector: summary đã `61s/60s` nhưng scene evidence cuối chỉ `53s`, nên ledger terminal `failed_no_charge` trước lượt worker có thể submit Key4U. Claim gate hiện enrich pure state trước terminal decision: chỉ scene có primary task thật, stalled, final-confirm, exact quote, chưa giao/chưa trừ/chưa fallback và Key4U capability-ready mới nhận candidate + idempotency; primary resubmit vẫn cấm.
- Bằng chứng source job `24`: focused `8 passed`; protected `54 passed, 2 baseline deselected`. Patch chỉ mở một fallback tick cho đúng `fallback_scene_index`, không submit đồng thời hai cảnh; compile/diff vẫn phải chạy trước local commit. LIVE rerun vẫn là gate riêng sau SubDub release và deploy Product Video tiếp theo.

## Bổ sung SubDub acoustic cast trên video karaoke — 28/08/2026

- PR `#915` đã sửa transport và deploy runtime `77fee7ce...`. Combo job
  `#6DC569C0A6` đi qua Key4U + Gemini thật, tạo `18` cue (`8/10` theo hai
  speaker) và sidecar, nhưng dừng trước TTS/mux/delivery vì acoustic cast trả
  `AUTO_CAST_MANUAL_REQUIRED`. Admin vẫn `charged_xu=0`; credits `200`,
  total_spent `0`, transactions `0`, credit_events `1`.
- Exact source PCM là mono `16 kHz` `s16le`, `1,547,794` bytes, SHA-256
  `82F1FFB6621588FC0B906C074B8E3E5C64CE8D6E2E9CA954444AD689668DB952`.
  Signal không im lặng: RMS cửa sổ được chọn `0.154301..0.269327`, peak
  `0.652008..0.923553`.
- Whole-window classifier thử `18` cửa sổ speaker 0 nhưng nhận `0` pitch; quét
  dày `186` cửa sổ cho thấy `156` thiếu hai frame F0 và `14` có competing pitch
  ổn định. Nguyên nhân là lời hát nằm trong backing music; không được hạ
  threshold hoặc ép một cặp nam/nữ.
- Comparator filter cũ #853 / filter multi trả sai `high/high` trên fixture
  nam/nữ nên bị loại. PCM extractor vẫn không filter; shared classifier và
  multi engine giữ nguyên.
- Nhánh raw-frame fallback từng thử đã bị review bác và **không được ship**:
  frame chồng lặp, confidence không phản ánh vote dominance, có thể bắt backing
  music và reset thành hai budget `48s`. Không còn helper raw-frame nào trong
  production exact-two.
- Authority exact-two mới chạy local, deterministic: stereo PCM `44.1 kHz`
  `s16le` → UVR MDX-Net tách vocal → PANNs AudioSet MobileNetV1 chấm từng cue
  → vote độc lập theo từng speaker. Không có luật ép hai speaker thành hai giới
  đối nhau; male–male, male–female và female–female đều hợp lệ nếu mỗi group có
  ít nhất `4` cue và dominance `>=0.75`.
- Model được khóa hash và license: UVR SHA-256 `E02220E8...` MIT; PANNs ONNX
  SHA-256 `0DA2C433...`, source code MIT, pretrained model record CC BY 4.0.
  Inference không gọi provider; tổng evidence unique tối đa `48s`.
- Exact fixture source result thật: speaker 0 `male/low`, vote `7/8`, confidence
  `0.875`, evidence `21s`; speaker 1 `female/high`, vote `8/10`, confidence
  `0.800`, evidence `27s`; post-rebase elapsed `106.031s` trên ONNX Runtime
  `1.29.0` với wall budget bounded `300s`,
  provider/wallet `0`. Đây vẫn là source-local evidence, chưa phải LIVE PASS.
- ONNX contract RED `20 failed, 5 passed`; dedicated final GREEN `33 passed`;
  isolation marker multi RED→GREEN `1 failed → 1 passed`. Protected branch
  `278 passed, 28 failed, 1 skipped`; BASE_SHA có cùng đúng `28` failure IDs
  nên `NEW_FAILURES=0`. Skip là test montage cần NumPy trên Python 3.14; cùng
  case đã GREEN riêng trên Python 3.12 + NumPy/ORT `1.29.0` (`7 passed`).
  Compile/hash/diff và post-rebase gate vẫn là cổng bắt buộc trước push.
- Trap vận hành: một sidecar có đúng hai label không chứng minh cast đúng;
  provider HTTP `200`, SRT hay sidecar cũng không phải MP4 PASS. Combo phải giao
  MP4 rồi receipt, không file tự động dư, trước standalone và multi-speaker.

## SubDub Auto 2-speaker LIVE PASS và khóa lane — 28/08/2026

- PR `#919` merge/deploy/runtime
  `e819c1cd00d66273e00c667355325549dbea8d44`; GitHub Actions run
  `33176635110` SUCCESS. Đây là build đầu tiên được công nhận sau khi cả artifact
  và nhịp cue đều được đo, không chỉ dựa trên HTTP/job id.
- Combo public job `#3A3BEA618D` giao video message `33764`, rồi receipt
  `33765`; giữa hai message có `0` SRT/audio/document tự động. MP4
  `9,673,714` bytes, SHA-256
  `4FFEFD25F7FE3860460C50845E20E6C1508CDE69327A71345E730466B0EF79D9`,
  H.264 `576x884` `30fps` + AAC stereo `48kHz`, `49.000s`, `-18.4 LUFS`,
  true peak `-3.6 dBFS`. SRT nội bộ `18` cue, `1,269` bytes, không gửi.
- Standalone public job `#282347E26C` giao video message `33771`, rồi receipt
  `33772`; file tự động phụ `0`. MP4 `9,978,464` bytes, SHA-256
  `449FFE9D592E14679A9F511442B48010AE8AC946AD324F5A26EABB8CD77F1B1B`,
  cùng H.264/AAC, `49.000s`, `-18.3 LUFS`, true peak `-4.1 dBFS`.
- Cả hai job dùng fixture SHA-256 `85C8793D...`, English, Auto 2-speaker,
  original `40%`, dub `150%`, confirm đúng `1` lần. Cast thật giữ
  `speaker_0=male/low` (`7/8` vote) và `speaker_1=female/high` (`8/10` vote).
  Các boundary cue là `0,4,9,11,13,15,17,19,21,23,25,27,29,31,33,35,38,43,48`;
  không cumulative drift và final duration bằng nguồn.
- Receipt combo: subtitle `61 Xu`, dubbing `75 Xu`, total `136 Xu`; standalone:
  dubbing/total `77 Xu`. Admin `charged_xu=0`; wallet sau cả hai vẫn credits
  `200`, total_spent `0`, transactions `0`, credit_events `1`.
- Hai lỗi presentation phát hiện sau live chỉ là nhãn callback: `voice_create`
  bị ghi nhầm “Gửi video khác” và back trạng thái ghi nhầm “Phụ đề + Lồng
  tiếng”. Local correction đổi đúng `2` dòng nhãn; UI + compact numeric audio
  `5 passed`, `py_compile bot.py` và diff-check exit `0`. PR `#922` đã merge
  SHA `2fd989e23ab298b7a1c8f415ac1ecda085e07476`; deploy `33202076833`
  SUCCESS `15m7s`; VPS readback cùng SHA, bot/web/nginx active và cả hai nhãn
  runtime đúng. Lane Auto 2-speaker từ đây là `LOCKED_LIVE_PASS`.
- Từ mốc này classifier/cast/timing/mux/delivery/audio numeric của Auto
  2-speaker là vùng khóa. Multi chỉ được sửa owner `auto_multi_speaker` hoặc
  nhánh điều kiện `auto_speaker_lane=multi`, đồng thời phải giữ toàn bộ
  comparator Auto 2-speaker GREEN.

## SubDub Auto multi-speaker source correction — 29/08/2026

- Lane Auto 2-speaker vẫn `LOCKED_LIVE_PASS`. SPEC multi chỉ đổi hai seam dùng
  chung: marker `auto_speaker_lane=multi` bật lại chính cue-lock đã chứng minh;
  successful multi MP4 không còn tự gửi SRT companion. Internal SRT/burn-in/QC
  và explicit download vẫn còn.
- Fixture multi thật được khóa trước live: `9,869,032` bytes, SHA-256
  `83DE97B744B931E544B569E6E750F8415545F226461BD2E36CFB49225898AD3E`.
  Refined sidecar local có `36` cue, đúng `3` label, end `126.505s`; sidecar cũ
  chỉ `2` label bị loại là underclustered.
- RED timing: `1 failed in 1.32s`, actual cue-lock `False`. RED delivery:
  `1 failed in 854.23s`, trace tới `reply_document(multi.srt)` sau MP4.
  Final focused: `23 passed`; cả `dub` + `subtitle_plus_dub` multi video-only
  `2 passed`; literal `3` cue/`3` speaker giữ nguyên start/end, drift `0`, final
  duration nguồn. Target language được giữ cho `vi/ja/en/ko/zh`.
- Protected comparison hiệu lực: `82 passed` và đúng `3` baseline-stale failures
  tái hiện trên clean source, `NEW_FAILURES=0`. Multi owner/cast/exact-two
  fallback hashes giữ đúng `3/3`; compile/diff/YAML/secret exit `0`;
  provider calls `0`, wallet mutations `0`.
- Đây là **SOURCE PASS**, chưa phải LIVE PASS multi. Chỉ đổi trạng thái sau một
  deploy/runtime SHA thật, combo MP4 thật PASS trước, rồi standalone MP4 thật
  PASS; mỗi flow phải video → receipt, ≥3 distinct voices và wallet delta `0`.

## Bổ sung Product Video job 25 và khóa UI — 28/08/2026

- PR `#910` merge SHA `82ffb117e6c2e84bd76a3aee6e5e747465958c66`; deploy run `33078757523` SUCCESS. Bot và owner worker cùng exact SHA.
- Request `VID-20260827-2803A3`, project `29`, job `25`, outbox `24`; hai scene ShopAIKey đều `SUCCESS 100%`. Telegram giao đúng một lần ở message `27576`, `charged_xu=0`, transaction count vẫn `0`.
- MP4 giao có `1.660.101` bytes, H.264 `540x960`, AAC stereo `48kHz`, duration `16.000s`, SHA-256 `FD48B933BE3552F8F0AE38CBD7FA6BA81FAD54855AA4898A9E177F1D916ECFBB`; audio `mean=-24.4 dB`, `max=-3.1 dB`.
- Artifact này **không PASS PV-L01**: clip provider ngang bị `scale=decrease + pad=black`, khiến hình thật co nhỏ giữa canvas dọc; subtitle được chọn và có SRT `84` bytes nhưng manifest ghi `subtitle_path=null`, `addon_application.requested=[]`.
- Product Video mới dùng `frame_fit_mode=cover`: `scale=increase + crop` phủ kín khung; default shared normalizer vẫn `contain`. Composition signature chứa fit mode để không tái sử dụng artifact letterbox cũ.
- Mọi Tail owner hiện compile strict `product-video-addons-v1`; materializer vẫn fail-closed, không đoán schema cũ. ACK Telegram trong Tail là best-effort để `502/timeout` không giữ khách ở màn Chất lượng hoặc Hóa đơn.
- UI được khóa byte-for-byte: `14/14` function Menu/Add-on/Review/Chất lượng/Hóa đơn/Xác nhận/Trạng thái khớp `origin/main`; cấm đổi chữ, hàng nút, callback hoặc back-stack trong failure loop này.
- Final source evidence: focused acceptance `45 passed`; quality/manual `39 passed`; Trend/scene `52 passed`; full Product Video output `24 passed`; 5 runtime files compile exit `0`. Old Tail suite có `41 passed, 15 failed` y hệt clean baseline, `NEW_FAILURES=0`.
- Source vẫn chưa là LIVE PASS. Phải deploy exact post-rebase SHA rồi rerun PV-L01; chỉ PASS khi video dọc phủ kín, subtitle materialized/applied, đủ 2 cảnh, audio, delivery và receipt `0 Xu`.

## Bổ sung kho trend bốn nguồn — 28/08/2026

- Scheduler hiện hữu vẫn kiểm tra mỗi giờ và chỉ refresh khi `next_run_at` đến hạn; khoảng refresh mặc định giữ đúng `7` ngày.
- Backend đọc bốn nhóm metadata công khai: `media`, `facebook`, `youtube`, `tiktok`; không dùng API trả phí, không cần key, `paid_provider_calls=0`.
- `source_group` được lưu trong trường `keywords` hiện có để không migration SQLite. Một nguồn lỗi chỉ giữ cache của nguồn đó; nguồn còn lại vẫn cập nhật, dữ liệu cũ không bị làm rỗng.
- UI trend không đổi: vẫn `Xem 5 trend media`, `Tự nhập trend`, `Tìm kiếm trend`, `Gửi video trend`; không thêm bộ lọc/nút/callback mới.

## Bổ sung Tail chọn chất lượng — 28/08/2026

- Callback live `video_tail|quality|select|400` từng dừng trước Hóa đơn tại
  `uiflow3_product_duration_contract_mismatch`. Nút vẫn gửi đúng tier nội bộ
  `400`; phần `2.360 Xu` khách nhìn thấy là đoạn cuối màn danh mục cũ được render
  lại sau exception, không phải nút `80 Xu` bị đổi thành tier `1500`.
- Tier callback hiện phải parse exact và còn nằm trong catalog của đúng product;
  giá trị rỗng, chữ, có zero đầu, tier ngoài catalog hoặc `2360` đều fail-closed
  trước khi thay session, tạo job/outbox, gọi provider hoặc chạm ví.
- Với UIFLOW3, planning state/UI giữ nguyên. Khi chọn gói, bot tạo một execution
  snapshot đã hash lại, đồng bộ `seconds_per_scene`, tổng thời lượng và mọi scene;
  RouteEngine, storyboard, Hóa đơn và guard xác thực đều dùng cùng snapshot đó.
- Với Tail scene3/session, draft lưu `b14_scene_seconds` từ đúng tier công khai;
  tier `300` được đo là `5 giây/cảnh`, tier `400` là `8 giây/cảnh`.
- UI vẫn khóa byte-for-byte `14/14` hàm Menu/Add-on/Review/Chất lượng/Hóa đơn/
  Xác nhận/Trạng thái. `video_local_edit`, `videoedit|ai`, Video dài tập, wallet,
  PayOS và provider-submit không thuộc diff.
- Bằng chứng cuối: acceptance `130 passed in 22.07s`; full RouteEngine `25 passed`;
  public seam `6 passed`; resume/invoice/Add-on `3 passed`; clean base và branch
  cùng `44 passed, 10` historical failures nên `NEW_FAILURES=0`; compile và
  diff-check exit `0`.
- Đây là SOURCE PASS. Chỉ được ghi LIVE PASS sau deploy exact SHA và click thật
  `Nhanh gọn - 80 Xu` đi qua Hóa đơn -> Xác nhận -> Trạng thái mà không hiện lại
  catalog `2.360 Xu`.

## Bổ sung Strategy V2 và báo cáo sau giao video — 28/08/2026

- `KIEM-THU/product-video-live-strategy-v2.json` là assignment machine-readable:
  đúng 8 representative rows + 9 quality-only rows = 17 final jobs. Số cảnh khóa
  là 19 + 9 = 28 assigned scene renders; 4 source-image tasks đưa trần create call
  lên 32. Mọi số này có regression verifier, không phải ước lượng.
- Representative luôn dùng tier `400` / `80 Xu/cảnh`. Kịch bản -> Video dùng 5
  cảnh; 7 representative rows còn lại dùng 2 cảnh. Quality-only dùng 1 cảnh và
  chỉ chạy trên product/adapter đã được catalog xác nhận tương thích.
- Video tự quay có 2 sản phẩm độc lập, nên có 2 representative rows:
  `self_shot_scene_change` và `self_shot_cinematic_transform`.
- Lane manual/direct-input chỉ chứng minh nội dung khách đi thẳng
  `Add-on -> Review -> Quality -> Invoice -> Confirm -> Status`; không dùng làm
  representative paid job vì bỏ qua phần product-specific phức tạp.
- `multi_scene_film`, `video_long` và `video_local_edit` bị loại khỏi paid matrix;
  `videoedit|ai` hoãn. Local Edit giữ 8 function hashes và 2 protected test files,
  không được sửa để làm sản phẩm khác PASS.
- Job #26 chứng minh tier `400`, Invoice `144 Xu`, 2 cảnh, 16 giây, 9:16 và MP4
  thật đã giao; nhưng legacy project persistence làm rơi strict Add-on contract và
  tạo `partial_addons=1`, nên chưa được ghi representative PASS.
- Source correction giữ nguyên `product-video-addons-v1` từ Tail tới worker, không
  tự bật voice/music/subtitle. Final focused gate `24 passed`; protected Tail/
  RouteEngine `103 passed`; local artifact/UI lock `21 passed`; broad clean base và
  branch cùng `38 passed + 7 historical failures`, `NEW_FAILURES=0`; compile/diff
  exit `0`.
- Báo cáo sau giao video là best-effort và at-most-once: chỉ gửi sau receipt +
  settlement, lưu `delivery_report_message_id` và `delivery_report_sent=true`;
  callback trùng không giao MP4, settle hoặc gửi report lần hai. Report failure
  không đảo ngược delivery và không charge lại.
- Tin khách hàng cấm provider, worker, job/task ID, SHA, manifest, JSON, engine
  route và mã lỗi nội bộ. `video_local_edit` và Long Video dừng trước DB claim của
  report helper.
- Exact correction live được khóa tại
  `KIEM-THU/runbooks/PV2-SPEC04G1-addon-report-rerun.md`. SOURCE PASS khác DEPLOY
  và LIVE PASS; phải có exact runtime SHA, MP4/receipt/report/zero-wallet readback
  rồi mới tick hoàn thành.
- Tester workspace readback ngày 28/08: 21 GitHub labels, 2 issues được trả về và
  4 issue templates local. Projects board là `UNKNOWN` vì token thiếu
  `read:project`; Owner cần tự cấp scope bằng `gh auth refresh -s read:project`
  trước khi task được phép đọc/tạo board. Không tự mở browser hoặc nâng scope.

## Bổ sung Product Video job #27 terminal truth — 29/08/2026

- PR #921 đã squash-merge SHA `4fa07a017dd5db9212b213dfd8c272564f4cb443`;
  deploy run `33198542741` SUCCESS trong `12m8s`. Bot và owner worker đọc lại
  đúng SHA; generation `0ad4cac82ec54d2c9d45fa84379dcf09` được chấp nhận.
- Live readback vẫn RED: hai scene đều có provider status thật `FAILURE`, không
  có clip/URL, fallback `0` và forensic terminal
  `all_scene_providers_exhausted_no_charge`; job vẫn queued vì presence-only
  marker rỗng tạo sai `unprocessed_result_indexes=[1,2]`.
- Presence-only marker không phải artifact. Scene authoritative `failed` chỉ
  được giữ ở bước tải/validate khi có URL cụ thể hoặc `result_url_valid`; cờ
  `provider_result_url_present=true` nhưng URL rỗng phải bị bỏ qua.
- Source F2: RED `1 failed in 13.96s`; exact GREEN `1 passed in 14.92s`; toàn bộ
  7 module gọi trực tiếp scene-ledger `85 passed in 26.69s`; compile, YAML và
  diff-check exit `0`. Năm engine route, Tail UI, provider order/task IDs và ví
  không đổi.
- Trước khi nhả shared slot, chỉ owner worker bị dừng; job #27 giữ queued/unlocked,
  hai task ID không đổi, provider usage `0`, transaction `0`, credit-event giữ
  `10`, charged Xu `0`. Đây vẫn là failure-loop, không phải product LIVE PASS.
- F2 PR #924 đã squash-merge SHA
  `f3f79fd50d4b2ad7ce345c7edc5c463ebaea44b5`; deploy run `33206104844`
  SUCCESS trong `10m23s`. Bot và owner worker cùng đọc đúng SHA.
- Một bounded worker claim đổi job #27 từ queued sang DB `failed` với durable
  `terminal_state/final_decision=failed_no_charge`, `continue_polling=0` và
  unprocessed result rỗng. Attempts chỉ tăng `950 -> 951`; scene/task map vẫn
  giữ đúng hai task gốc, một task mỗi scene, cả hai `failed/exhausted`.
- Sau terminal: active Product Video jobs `0`, provider usage `0`, transactions
  `0`, credit events giữ `10`, `provider_submit_called=0`, charged Xu `0`; owner
  worker được dừng và xác minh `inactive`.
- Job #27 chỉ PASS failure-loop, không PASS sản phẩm. Không tạo thêm manual job
  trùng. Bằng chứng MP4/Add-on/report còn lại phải được lấy trên representative
  thật `PV2-R01` để một provider job đồng thời kiểm Video Trend và shared Tail.

## Bổ sung PV2-R01 Trend source handoff - 29/08/2026

- Runtime `02c1c4aa...` nhận đúng fixture `32,391,742` bytes, SHA
  `784FBE5B...E2732`; local analysis đo `79.4667s`, `1280x720`, có audio và 3
  nhịp đổi cảnh. Chưa có project/job/outbox/provider/wallet action.
- Flow non-manual đã đi qua entity, creative, requirements, scene plan, hai
  prompt riêng bản 2, subtitle nguồn, transition `1/1` và Review. Review báo sai
  `0 tệp` trong khi entity UI vẫn có source được gán `1`.
- Nguyên nhân: lần kết thúc Trend entity bridge chỉ chuyển các reference đã gán,
  bỏ source upload của UIFLOW3 khỏi Scene3 `reference_assets`; khi quay lại Review
  embedded Tail cũng không refresh `source_asset_ids`.
- Fix chỉ ở Trend handoff, không đổi shared Tail, UI, route engine, provider,
  worker hoặc wallet. RED `2 failed in 8.15s`; exact GREEN `2 passed in 707.43s`;
  protected Trend/Strategy `61 passed in 16.37s`; compile/diff exit `0`.
