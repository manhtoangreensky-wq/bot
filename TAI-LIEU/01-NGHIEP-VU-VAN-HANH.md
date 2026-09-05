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

### Failure loop live `#7C4BE502C0` và re-diarization nhiều giọng

- Combo trên runtime `da817b65...` terminal `failed_no_charge` tại
  `AUTO_CAST_MANUAL_REQUIRED`; `charged_xu=0`, TTS/mux/artifact/MP4/delivery đều
  `0`. Read-only provider attempt lúc `12:30:08+07` đo được
  `Deepgram / listen / PASS`, nhưng sidecar chỉ có `32` cue, `2` label
  (`16/16` cue), `5,422` bytes, SHA-256 `BC05D9AF...`.
- Hai label không được xem là đủ cho Auto multi. Cách tách label bằng pitch bị
  loại: một người đổi cao độ có thể bị bịa thành hai người, một pitch frame có
  thể là nhạc nền và refinement/classifier cũ reset budget. Runtime mới chỉ
  chuyển tiếp khi provider word diarization chứng minh `3–8` label thật; không
  truyền `expected_speakers` hoặc số người dự kiến.
- Provider word evidence dùng identity `(text chuẩn hóa, start, end)`. Duplicate
  cùng speaker bị bỏ; cùng word/timestamp nhưng khác speaker làm cả kết quả
  fail-closed. Mỗi label cần ít nhất `2` word riêng, mọi label phải map lại ít
  nhất một cue, mỗi cue cần dominance overlap `>=0.70`.
- Provider call chỉ mở sau exact product final-confirm. Missing key, busy lock,
  input quá `5 phút`, PCM sai shape, kết quả `1–2`/`>8` label, cue thiếu coverage
  hoặc label bị mất đều dừng trước TTS/mux và không charge.
- PCM được downmix/resample theo chunk `1 MiB` trong worker thread; một lock
  nonblocking bao trùm conversion + request. Base64/JSON cũng chạy ngoài event
  loop. Job đồng thời thứ hai fail trước cấp phát/call, tránh nhân RAM và block
  Telegram.
- Sau re-diarization, adapter multi tái dùng đúng UVR+PANNs model/inference và
  lock của engine hai giọng nhưng không sửa file khóa. `3–16` speaker được vote
  độc lập; male–male, male–female và female–female đều hợp lệ nếu evidence đạt;
  tổng evidence tối đa `48s`.
- Source evidence cuối: `135 passed, 241 deselected, 14 subtests in 20.05s`;
  baseline exact provider comparator `49 passed in 658.98s`, branch cùng selector
  `49 passed in 11.65s`, `NEW_FAILURES=0`; compile `6` changed Python files và
  diff-check exit `0`. Independent review: Critical `0`, Important `0`,
  `READY_TO_COMMIT=YES`.
- Đây vẫn là **SOURCE READY**, không phải deployed/LIVE PASS. Combo cùng fixture
  phải tạo MP4 thật trước; chỉ sau combo PASS mới chạy standalone và khóa multi.

### Failure loop live `#22B138532B` và metadata resume của nguồn cũ

- Fresh combo dùng đúng fixture `9,869,032` bytes, SHA-256 `83DE97B...`, duration
  `133.375420s`; Deepgram PASS tạo `32` cue và DeepL PASS, nhưng sidecar vẫn chỉ
  có `2` label (`16/16`). Job terminal `failed_no_charge` tại
  `AUTO_CAST_MANUAL_REQUIRED`; TTS/mux/artifact/delivery đều chưa chạy và
  `charged_xu=0`.
- Root cause nằm ở boundary nhận video: Telegram file ID/unique ID đã đổi sang
  nguồn mới nhưng `5` field private `auto_exact_*` của nguồn trước vẫn còn.
  Riêng `auto_exact_resume=true` làm wrapper coi sidecar mới là genuine resume
  và bỏ qua re-diarization undercluster. Receipt/provider PASS không phải bằng
  chứng nguồn hiện tại được phép resume.
- Correction chỉ xóa `SUBDUB_AUTO_PROFILE_PRIVATE_FIELDS` sau khi combo video
  mới đã qua readiness, step và media-type guard. Lane Auto multi cùng mức âm
  gốc `40%`/lồng `150%` vẫn giữ; callback resume thật không có upload mới vẫn
  giữ cache và không gọi lại provider.
- Bằng chứng local: RED `1 failed in 5.60s`; focused GREEN `1 passed in 520.48s`;
  `3` behavior comparators, `53` multi protected và `82` exact-two/audio tests
  PASS. Branch có `16 passed` cùng đúng `3` baseline failures; clean HEAD
  `8411ae7` cũng fail đúng ba ID/giá trị, nên `NEW_FAILURES=0`.
- Compile `bot.py` + test exit `0`; YAML/diff/scope/secret exit `0`; exact-two
  hashes giữ `2/2`; provider calls `0`, wallet mutations `0`. Đây là **LOCAL
  SOURCE READY**, chưa phải deployed hoặc LIVE PASS.
- Tester surface local có đúng `4` issue templates và `3` SubDub cases. Suite
  Strategy V2/docs có `8 passed` + `1` fixture-hash failure; clean HEAD
  `8411ae7` fail cùng test ID và cùng SHA actual/expected, nên đây là baseline,
  không sửa fixture Product Video trong correction SubDub.

### Failure loop live `#DB4FFFD7F6` và durable re-diarization evidence

- Fresh combo trên runtime `aaf3a9c6e6ebd4d18b6b5a584a39168ed0abe42c`
  dùng đúng fixture `9,869,032` bytes, SHA-256 `83DE97B744B931E544B569E6E750F8415545F226461BD2E36CFB49225898AD3E`,
  English, Auto multi, âm gốc `40%`, giọng lồng `150%` và Confirm đúng `1`
  lần. Public job là `#DB4FFFD7F6`, internal job
  `db4fffd7f6b63d1884f1`; duplicate count `0`.
- Job terminal `failed_no_charge` tại `AUTO_CAST_MANUAL_REQUIRED` trước TTS,
  mux, artifact và delivery; bốn stage này đều `0`. Engine jobs tăng đúng
  `319 -> 320`; transactions `0`, provider-usage ledger `0`, credit events giữ
  `11`, wallet giữ `200/0` và `charged_xu=0`.
- Workspace giữ source SHA đúng, normalized SHA
  `B3D735427011F71E81CE6C20077B3155F6C56A40C64C25D9B1DC643D888221C8`
  và sidecar `5,425` bytes, SHA-256
  `08D5CC607D68E995599486CCB716F91AF7969C9E41318F91617043FDDE200825`.
  Sidecar có `32` cue nhưng vẫn chỉ `2` label (`16/16`), nên chưa đạt acceptance
  tối thiểu `3` speaker.
- Manifest/terminal cũ không giữ các field direct re-diarization. Vì vậy kết quả
  provider trực tiếp của job này là **UNKNOWN**: thiếu field không chứng minh
  provider chưa được gọi, cũng không chứng minh timeout, HTTP/quota, response
  malformed hay mapping cue là root cause. Dòng Telegram progress `502/timeout`
  là best-effort UI warning, không phải authority của terminal cast.
- Correction hiện tại chỉ bảo toàn đúng `8` field bounded khi direct attempt có
  thật: attempted, provider, provider status, detail, HTTP status, provider word
  count, provider speaker count và mapped speaker count. `api_key`, raw response,
  credentials và provider payload không được ghi. Request, retry, model,
  provider call, mapping, TTS, mux, pricing và wallet không đổi; đây là
  **diagnostics correction**, chưa phải output fix.
- TDD đo được: RED `2 failed in 7.43s`; GREEN ban đầu `2 passed in 664.07s`;
  production-shape + functional durable wrapper `2 passed in 9.46s`; direct
  adapter contract `3 passed in 7.10s`; review RED exact detail `1 failed in
  7.19s` rồi GREEN `2 passed in 5.85s`; conditional-manifest RED `1 passed + 1
  failed in 6.55s` rồi GREEN `2 passed in 562.59s`; hai file focused cuối `58
  passed in 6.87s`; exact-two/audio protected `86 passed in 8.92s`. Task7 comparator
  branch `6 passed + 7 failed` và clean `a77b77f` cùng đúng `6/7` cùng failure
  IDs/giá trị, nên `NEW_FAILURES=0`. Full changed-file compile và final changed
  test compile đều exit `0`. Source tests tạo `0` provider call và `0` wallet
  mutation. Authorization đã được dùng cho chính job này; mọi combo mới cần
  Owner xác nhận mới sau deploy diagnostics.
- Standalone `Lồng tiếng video` vẫn bị chặn theo thứ tự. Không được ghi
  `LOCKED_LIVE_PASS` cho multi cho tới khi combo giao MP4 thật rồi receipt và
  sau đó standalone cũng giao MP4 thật rồi receipt, cùng zero-wallet evidence.

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
- PR #926 merge `3b585527...`, deploy `33213099898` SUCCESS `5m26s`; Review
  xác nhận source `1 tệp`. Hóa đơn tier `400` giữ đúng `144 Xu`, subtitle miễn
  phí, Owner không trừ.
- Final Confirm dừng trước DB với `trend_source_or_sample_missing`; không project,
  job, outbox hay provider call mới. Nguyên nhân là Flow7 đã công nhận upload
  Trend thực, còn Flow6 chỉ nhận URL/sample/user-topic.
- Flow6 dùng lại đúng predicate upload đã kiểm chứng ở Flow7; không đổi route hay
  engine. RED `1 failed in 9.29s`, GREEN `1 passed in 12.30s`; branch có
  `96 passed + 2` historical failures và clean main tái hiện đúng hai failure đó
  trong `593.52s`, nên `NEW_FAILURES=0`.

## Bổ sung PV2-R01 phục hồi flow đầy đủ của 4 lane Trend - 29/08/2026

- Bốn nguồn vào hiện hành là kho Trend media, tự nhập Trend, tìm kiếm Trend và
  gửi video Trend. Cả bốn dùng chung flow cũ đã có sẵn; không dựng wizard mới.
- Sau nguồn Trend, thứ tự bắt buộc là số cảnh, tỉ lệ, nguồn nội dung, loại nội
  dung/preset, gợi ý hoặc nội dung tự nhập, Preview, nhân vật/tham chiếu, phong
  cách, yêu cầu/bối cảnh, kế hoạch cảnh, prompt rồi Tail dùng chung.
- Các chốt cũ đã làm bốn màn hình nội dung không còn public, ép ratio đi thẳng
  sang nhân vật và ép nội dung nhập tay đi thẳng Tail. Minimal fix chỉ gỡ các
  chốt đó và thêm ba bước nội dung vào contract Flow7; canonical entity bridge,
  Tail, chất lượng, giá, provider, worker và wallet không đổi.
- TDD exact: `4 failed, 1 passed in 6.63s` -> `5 passed in 574.87s`; năm selector
  hợp đồng lịch sử đã cập nhật cùng GREEN `5 passed in 9.64s`; ba transition
  ratio/manual gọi thật handler đưa file restore lên `8 passed in 7.36s`.
- Branch Trend gate `124 passed + 2` Script-only baseline failures; phép so sánh
  cùng bảy file là branch `119 passed + 2` và clean main `117 passed + 3`.
  Hai failure còn lại trùng ID baseline, failure hash fixture chỉ có ở clean,
  nên `NEW_FAILURES=0`. Protected Tail/quality/UI `59 passed`; compile, YAML và
  diff-check đều exit `0`.
- Hóa đơn cũ được tạo từ flow rút gọn không phải bằng chứng LIVE cho flow mới.
  Sau deploy phải chạy fresh một lane upload phức tạp đến artifact/receipt/report.
- Rebase lên exact main `da817b65...` sạch; post-rebase Trend + protected gate
  `186 passed + 2` Script-only baseline failures trong `670.77s`; compile exit
  `0`. Đây là source evidence, chưa phải deploy hay LIVE PASS.
- PR #928 merge/runtime `fe25cc056df59af3c7f063f0ea5f3866ff160130`;
  deploy `33237168072` SUCCESS. Bot + owner worker cùng SHA; generation
  `35eb01aa...` authenticated/persisted, reject rỗng, cả 4 service active.
  Baseline live `31/27/26`, transactions/provider usage `0/0`, credit events
  `10`, active jobs `0`, Owner `200 Xu / spent 0`. Chưa có MP4 full-flow mới nên
  Trend vẫn không phải LIVE PASS.

## Bổ sung PV2-R01 Telegram document intake - 29/08/2026

- Fresh fixture SHA `784FBE5B...` đã tới Telegram dạng File `30.9MB`, nhưng bot
  dừng trước analysis với `video_trend_probe_failed / InvalidToken`; DB/provider/
  wallet không đổi (`31/27/26`, provider `0`, transactions `0`, credit events
  `10`, active jobs `0`, Owner `200/0`).
- Nguyên nhân: Trend probe dùng direct Telegram `get_file/download_to_drive`,
  không dùng shared bounded byte downloader đã hỗ trợ Local Bot API. Minimal fix
  chỉ thay transport trong helper probe, giữ size/hash/ffprobe/metadata y nguyên.
- TDD exact `1 failed in 1553.92s` -> `1 passed in 1148.40s`; protected effective
  `9 passed`; một AST harness failure tái hiện trên clean `fe25cc0` trong
  `2107.51s`, `NEW_FAILURES=0`; compile/diff/scope/secret exit `0`.
- Owner cho phép dùng `D:\TOANAAS\video AI tham khảo` làm kho fixture cho các
  row sau; mỗi file phải đo SHA/metadata trước live. Không đổi fixture PV2-R01
  giữa failure-loop.

## Bổ sung PV2-R01 job #28 và authority provider theo cảnh - 29/08/2026

- PR #930 đã squash-merge SHA
  `42cbf929b8f89b9154e7f343079ac6655c2ef512`; deploy run `33252027086`
  SUCCESS trong `10m22s`. Bot và Owner Product Video worker cùng SHA; generation
  `aae18624871f4008bdd46dc7e23437a3` authenticated/persisted, reject rỗng.
- Flow upload Trend đầy đủ đã đi qua analysis, 2 cảnh, 9:16, nguồn nội dung,
  Social creator Trend, Preview, entity/style/requirements/plan/prompts, Add-on,
  Review, tier `400`, Invoice `144 Xu`, một Confirm và Status. Admission tạo đúng
  request `VID-20260829-D78AA3`, project `32`, job `28`, outbox `27`.
- Forensic SQLite `-readonly` đo job `28` có `attempts=5/max_attempts=3`. Hai scene
  có hai task ShopAIKey `veo3.1-fast` khác nhau, đều `submit_accepted=1`,
  `task_pollable=1`, trạng thái authority `IN_PROGRESS` từ
  `shopaikey.data.status`; map task -> scene phủ đủ `1/2`. Root lại rỗng authority
  và chỉ đếm `1` task, nên marker cũ `failed_no_charge` thắng; outbox chuyển
  `terminal_failed` với reason `provider_in_progress`. Scene `130/131` chưa có
  video/audio path; delivery attempts `0`; charged Xu `0`, transactions `0`,
  credit events giữ `10`, Owner wallet giữ `200/0`.
- Nguyên nhân gốc: connector đã lưu authority thật trong từng `scene_tasks`, nhưng
  queue/worker chỉ dùng authority root khi quyết định task còn sống. Đây là bẫy
  dữ liệu phân cấp: root summary có thể stale hoặc collapsed, không được ghi đè
  hai task-scene rows đang chạy.
- Correction chỉ đổi `remote_worker.py` và `services/video_project_queue.py`.
  Scene task có ID thật + authority running chỉ được sửa marker terminal cũ khi
  root vẫn yêu cầu provider polling. Cancellation, delivery và explicit terminal
  reason như `all_scene_providers_exhausted_no_charge` vẫn fail-closed.
- Bằng chứng local khóa cuối: focused/recovery `7 passed`; protected effective
  `68 passed, 5` exact baseline deselected; raw protected `68 passed + đúng 5`
  baseline failures; broad impact `196 passed + đúng 34` baseline failures so với clean
  main `189 passed + cùng 34`, `NEW_FAILURES=0`. `bot.py` và changed runtime/test
  compile exit `0`; docs/state/diff/secret gates sạch; provider calls `0`, wallet
  mutations `0` trong source gate.
- Vận hành recovery không dùng SQL tay: `/api/v1/worker/claim` có owner hiện hữu
  tự CAS-requeue job failed đủ điều kiện và ghi `recovery_existing_tasks_only`.
  Claim/build/complete sau đó ép `provider_submit_allowed=false`,
  `automatic_resubmit/fallback=false`, charge `0`. Claim-scan preflight RED
  `1 failed, 1 passed` chứng minh job #27 explicit exhaustion từng có thể bị hồi
  sinh; shared terminal-reason guard chặn #27 nhưng vẫn cho #28, và `4` selector
  recovery hiện hữu PASS.
  Sau deploy chỉ poll/materialize hai task cũ của job `28`, cấm upload/Confirm/job
  hoặc provider submit mới.
- `PV2-R01` vẫn là LIVE RED, chưa được khóa. Chỉ đổi thành `LOCKED_LIVE_PASS` khi
  hai task cũ tạo MP4 2 cảnh thật, cover-fit 9:16, subtitle + transition + audio,
  Telegram receipt + báo cáo khách và zero-wallet đều có bằng chứng terminal.

## Bổ sung PV2-R01 one-shot authority repair - 30/08/2026

- PR #934 squash-merge `ef81f6a03f5384f6dbc02ebd6f9bf96edfbc6618`;
  deploy `33290296142` SUCCESS trong `15m15s`. VPS bot/web/nginx active; Owner
  Product Video worker cùng SHA, PID `695925`, generation
  `4ab7fd93482744a2bc06b81178ebb155`, heartbeat authenticated/persisted và reject
  rỗng.
- Claim runtime mới vẫn không lấy job #28. Classifier production read-only đo mọi
  cổng authority đều đạt: mapping `2/2`, hai task `IN_PROGRESS`, không explicit
  terminal/cancel/delivery/charge. Blocker duy nhất là
  `existing_task_recovery_count=3/max=3`, đã dùng trên runtime cũ trước khi sửa
  authority theo cảnh.
- Bẫy vận hành: giới hạn retry đúng nhưng không được biến ba lượt chạy trên logic
  authority lỗi thành cấm vĩnh viễn một task vẫn đang chạy. Correction không tăng
  max chung. Nó cho đúng một repair khi marker
  `provider_running_overrides_failed_no_charge` và task authority vẫn sống; marker
  repair được lưu bền để không có authority repair thứ hai. Submit/resubmit/fallback và charge vẫn
  false.
- TDD đo được: RED `1 failed in 8.41s`; GREEN `1 passed in 5.74s`; focused `15
  passed`; restart/claim `56 passed`; protected polling/CAS/multiscene/delivery/
  fallback `242 passed, 1 dependency warning in 48.09s`; final strategy-inclusive
  `251 passed, 1 dependency warning in 47.40s`; compile và diff-check exit `0`.
  Đây chưa phải LIVE PASS; còn phải ship và materialize đúng hai task cũ.

## Bổ sung PV2-R01 stale-root terminal classifier - 30/08/2026

- PR #935 squash-merge `06f38df793beabd14e3446dadd473d4e8737a0e6`;
  deploy `33293196471` SUCCESS trong `11m25s`; bot/worker cùng SHA, worker PID
  `703262`, generation `b264fd4f04994a3288f686ae09a51413`, heartbeat accepted và
  persisted.
- Authority repair được dùng đúng một lần lúc `11:59:17`, recovery count `4`, mọi
  submit/resubmit/fallback/charge vẫn `0`. Một giây sau job terminal lại dù hai scene
  còn `IN_PROGRESS`.
- Root cause: terminal classifier chỉ gọi `provider_task_alive()` khi root
  `continue_polling=true`. Payload production có root stale false nhưng scene authority
  true, nên reason pending bị hiểu nhầm thành terminal. Correction luôn hỏi authority
  sau khi explicit terminal reason đã được ưu tiên.
- Một marker classifier-repair riêng chỉ cho đúng payload đã dùng authority repair,
  `worker_failed`, pending reason và task authority còn sống. Sau marker này mọi recovery
  sau bị khóa. RED `1 failed in 6.27s`; GREEN `4 passed in 4.65s`; protected `252
  passed, 1 dependency warning in 45.50s`. Chưa phải LIVE PASS.

## Bổ sung PV2-R01 claim-ledger authority - 30/08/2026

- PR #936 squash-merge `eba42c15b1b58f8a8b08dd019584b1c8dde67bb3`;
  deploy `33294851362` SUCCESS trong `9m23s`; worker PID `706350`, generation
  `766c231c71e448949aaafe81d2cb918d`, heartbeat accepted/persisted.
- Marker classifier cuối được lưu lúc `12:40:47`, recovery count `5`, nhưng job
  terminal lại lúc `12:40:48` trước CAS claim: attempts giữ `5`, lock rỗng. Hai
  scene vẫn actual `IN_PROGRESS`, canonical `provider_running`; paid routes, artifact,
  delivery và wallet đều `0`.
- Root cause nằm trong ledger merge: summary `scene_status_by_index=failed` vào trước
  với rank `4`, chặn actual provider `IN_PROGRESS` rank `3`, rồi summary ghi đè lần
  nữa. Summary là dữ liệu trình bày stale, không phải authority cao hơn task-bearing
  current provider payload.
- Minimal fix cho actual provider status thắng historical summary của cùng task;
  summary chỉ áp dụng khi scene chưa có task candidate. RED `1 failed in 5.92s`;
  GREEN `1 passed in 5.14s`; focused `25 passed`; protected `252 passed, 1 warning
  in 43.96s`. Không thêm recovery marker mới; `PV2-R01` vẫn chưa LIVE PASS.

## Bổ sung PV2-R01 trusted task authority - 30/08/2026

- PR #937 squash-merge `6e0e42daae50859159c7781531e6c3228890dff5`;
  deploy `33296036307` SUCCESS `13m44s`; bot/worker cùng SHA, worker PID `710711`,
  generation `91ea20ee8faf4fe8b75343127b814f27`, heartbeat persisted/reject rỗng.
- CAS requeue vận hành có backup riêng, chỉ đổi job #28/project #32 failed -> queued;
  attempts/outbox/task identity giữ nguyên, new job/provider/wallet đều `0`. Job vẫn
  terminal trước CAS lock lúc `13:22:46`.
- Root refined: provider events historical và root canonical summary đều mang task
  identity nhưng status `FAILURE`, được merge sau per-scene current `IN_PROGRESS`.
  Vì thế điều kiện đúng không phải chỉ là “có task ID”, mà là authority source.
- Per-scene current payload hoặc completion có result thật được gắn trusted sticky;
  historical event/root summary không thể hạ status, nhưng current per-scene FAILURE
  vẫn terminal được. RED `1 failed in 5.31s`; GREEN `1 passed in 5.67s`; focused
  `27 passed`; protected `252 passed, 1 warning in 52.17s`. Chưa LIVE PASS.

## Bổ sung PV2-R01 tier-400 controlled fallback budget - 30/08/2026

- PR #938 squash-merge `3d16cf60511318d2c5eb7c799ecbee8c07631c1b`;
  deploy `33297745599` SUCCESS `11m31s`; worker PID `714298`, generation
  `8a63c9f4e4e949fe878e276c9d036511`.
- Final CAS có backup, worker thật sự claim job #28 (`attempts 5->6`) rồi kết luận
  primary `all_scene_providers_exhausted_no_charge`; artifact/delivery/submit mới/
  wallet đều `0`. Primary không được requeue lần nữa.
- Bảng giá/route giữ nguyên: khách `144 Xu`; ShopAIKey primary `4.550 VND/2 cảnh`;
  Key4U VEO fallback `21.150,72 VND/2 cảnh`, internal budget `212 Xu`; Owner chịu
  âm biên `6.750,72 VND`. Không tăng giá khách.
- Root source: scene stall policy trộn internal budget vào phép bằng nhau của ba
  trường giá khách. Router đã có budget-vs-cost guard riêng. Minimal fix chỉ tách
  hai khái niệm; fallback vẫn một lần/cảnh, dùng idempotency, cấm debug/recover source
  và cấm primary resubmit. RED `1 failed in 5.84s`; GREEN `5 passed in 5.63s`;
  protected `88 passed in 9.34s`. Chưa LIVE PASS.

## Bổ sung PV2-R01 fallback cost metadata - 30/08/2026

- PR #940 squash-merge `aaf3a9c6e6ebd4d18b6b5a584a39168ed0abe42c`;
  deploy #156 run `33302353405` SUCCESS. Bot và Owner worker cùng SHA; worker
  PID `723568`, generation `284c6fe3ab704dea8237d1bfeebdad92`, heartbeat
  authenticated/persisted và reject rỗng.
- Router đã có cổng `fallback_provider_cost_xu <= provider_budget_xu`, nhưng
  request metadata của scene chỉ truyền budget. Vì vậy live CAS phải dừng trước
  Key4U cho tới khi cost `212` cũng đi qua cùng boundary.
- Minimal fix chỉ thêm một metadata field; RED `1 failed in 8.29s`, exact GREEN
  `1 passed in 5.56s`, fallback/Key4U `19 passed in 6.76s`, compile/diff
  exit `0`. Giá khách, route, engine, provider order, ví và idempotency không đổi.
- PR #941 squash-merge `8134c28b80c1587a36cc782c0cdb98c4ebc9a74b`;
  deploy #157 SUCCESS `3m18s`; bot/worker exact SHA. Query-only job #28 dry-run
  đạt quote `144/144/144`, budget/cost `212/212`, one-scene preclaim,
  idempotency match và side effect `0`.
- Submit-path RED sau đó chứng minh single Key4U candidate chưa enforce cost guard:
  `213>212` vẫn gọi adapter một lần. Guard tối thiểu chặn trước submit chỉ cho
  public fallback source; `212==212` vẫn gọi đúng một lần. Spend safety
  `12 passed`, affected total `49 passed`, compile/diff `0`. Count trước
  submit `0` cho phép attempt hiện tại; `1` chặn retry.
- PR #942 squash-merge `db5f6a81bfb505c23eca61d68db419b984822a22`;
  deploy #158 run `33307435330` SUCCESS `4m4s`. Production CAS có backup
  `0600`, nhưng live job #28 terminal lại trước provider, attempts `6->8`;
  wallet/provider usage vẫn `0`.
- Claim preflight đã lưu one-scene Key4U candidate, nhưng worker payload chỉ mang
  route defaults và làm rơi quote/budget/cost/scene authority. Conditional
  worker-context overlay chỉ chạy cho controlled existing-task recovery đã suppress
  terminal; normal Product Video không đổi. Claim/hydrate `2 passed`,
  worker-to-scene `1 passed`; branch/base comparators có `NEW_FAILURES=0`.

## Bổ sung SubDub Auto multi same-job correction — 31/08/2026

- Owner recovery dùng lại đúng internal job `211844aa34788db33757`, fixture SHA-256
  `83DE97B744B931E544B569E6E750F8415545F226461BD2E36CFB49225898AD3E`,
  English, âm gốc `40%`, lồng tiếng `150%`; engine job mới `0`, `charged_xu=0`.
- Recovery đầu terminal `failed_no_charge` lúc `10:37:37`, trước ASR/translation/TTS/
  mux/artifact/delivery. Gemini production đã dùng bound `2` nhưng cả hai terminal
  HTTP `200 completed` đều không có word/speaker. Cùng file/config probe kế tiếp dùng
  đúng `1` POST, `0` poll và trả `152` word annotations, `149` word hợp lệ, `5`
  speaker; transcript/raw response/API key không được in hoặc lưu.
- Command-route tạo `6` progress panel ở các mốc `5/5/20/5/35/50%` vì không có
  message đích để edit. Correction giữ đúng một message: lần đầu gửi, mọi mốc sau
  chỉ edit; edit lỗi không được fallback thành panel mới.
- Minimal source change: terminal-empty bound `2 -> 3`; đúng một correction CAS thứ
  hai chỉ khi failure là Gemini HTTP `200`, word/speaker/mapped đều `0`, no-charge,
  no-output và `AUTO_CAST_MANUAL_REQUIRED`. Mọi failure khác hoặc correction kế tiếp
  vẫn fail-closed; không tạo job thứ hai.
- TDD: RED `3 failed in 609.21s`; exact GREEN `3 passed in 6.56s`; hai module trực
  tiếp `36 passed in 7.98s`; protected multi/exact-two/audio `68 passed in 12.28s`;
  full compile changed Python exit `0`. Hai hash exact-two giữ nguyên
  `DE93620F...145B` và `94748DEF...1177E`. LIVE MP4 vẫn chưa được tuyên bố PASS
  trước deploy và same-job correction.
- Pre-merge review RED thêm `17 failed, 8 passed in 8.64s`: missing no-charge/
  no-output fields còn bị coi là an toàn và nonempty-invalid annotation bị đồng
  nhất với terminal-empty. Correction yêu cầu mọi field safety có mặt với giá trị
  exact, không có artifact/delivery message/path; service lưu bounded raw
  `word_info` count + terminal-empty bool. Review GREEN `25 passed in 563.13s`;
  expanded direct/protected `126 passed in 9.39s`.
- Sau deploy `47f18be`, durable legacy job đã có mọi safety field explicit false/
  no-charge nhưng thiếu đúng cả hai raw-observability fields vì failure xảy ra trước
  deploy. Không backfill/giả mạo DB. Admin command có literal riêng
  `--confirm-observability-gap`; override chỉ cho cả hai field cùng thiếu, cùng job/
  SHA/Owner/options, one-shot marker và strict safety. Partial raw evidence bị chặn.
  RED `3 failed in 6.70s`; exact GREEN `3 passed in 4.76s`; recovery module `28
  passed in 5.66s`; expanded protected `128 passed in 8.98s`; full parser compile
  exit `0`. Post-rebase exact main: `128 passed in 561.56s`, full compile exit
  `0`. Chưa gọi provider hay correction lần hai trước deploy override.
- Review phát hiện literal legacy trước ordinary recovery có thể đi vào first CAS;
  RED `2 failed in 6.61s`. Guard mới chặn literal nếu predicate legacy không đúng;
  GREEN `4 passed in 556.37s`, recovery module `30 passed in 5.49s`, full compile
  exit `0`.

## Bổ sung parser evidence Auto multi — 31/08/2026

- Same-job recovery nhận HTTP `200 completed` với `151` raw `word_info`, nhưng
  accepted word/speaker/mapped đều `0` và dừng trước TTS/mux/artifact/delivery;
  `charged_xu=0`. Raw response/text/label/timing/key không được lưu.
- Parser giữ aggregate-only counts và một rejection code:
  `annotation_fields_invalid`, `word_identity_conflict`,
  `speaker_count_out_of_range`, `speaker_word_count_below_min`, hoặc
  `no_valid_word_annotations`. Lane multi cho phép bỏ tối đa `2` weak words và
  tối đa `2%` canonical words chỉ khi còn `3–8` speaker mạnh, mỗi speaker có ít
  nhất `2` words. Cue mapper sau lọc vẫn phải phủ `100%` cue, giữ confidence hiện
  hành và chứng minh mọi speaker mạnh; cue chỉ có weak evidence vẫn fail-closed.
- RED `3 failed in 796.08s`; focused GREEN `4 passed in 5.80s`; service/blackbox
  `67 passed in 6.37s`; exact-two/timing `37 passed in 8.18s`. Provider/DB/wallet
  action trong source-local loop là `0`. Behavior RED `3 failed in 9.00s`;
  behavior GREEN `3 passed in 19.32s`; propagation RED `2 failed in 6.95s`;
  propagation GREEN `2 passed in 638.78s`; parser/blackbox `70 passed in 11.09s`;
  exact-two/timing `37 passed in 10.00s`; boundary cap/mapper `3 passed in 29.68s`;
  combined `110 passed in 14.92s`; post-rebase `110 passed in 657.28s`; full
  compile exit `0`. Review RED mixed malformed `1 failed in 6.89s`; GREEN
  `3 passed in 7.27s`; final combined `111 passed in 9.94s`; compile `0`.
  Chưa có LIVE MP4 PASS.
## Bổ sung Product Video job #28 claim/poll authority — 31/08/2026

- Worker-context PR #943 đã deploy; bot/Owner worker được đồng bộ ở
  `1b25926257634545436dd8bf8aea5af005d6e4ab`. Query-only trước start PASS:
  job `28`, project `32`, outbox `27`, quote `144/144/144`, budget/cost
  `212/212`, đúng một Key4U slot scene 1, side effects `0`.
- Worker PID `830225` được start theo exact Owner authorization rồi dừng khi attempts
  tăng `8 -> 40`. Provider defer đã lưu `next_poll_at`, nhưng claim scan không đọc
  cổng thời gian nên re-claim ngay. Root lặp ShopAIKey `provider_in_progress`;
  metadata cả hai scene đổi sang Key4U dù chỉ scene 1 được cấp quyền. Artifact,
  delivery, provider-usage và transaction vẫn `0`; credit events `1`; wallet
  `200/0`; charged Xu `0`.
- Bẫy vận hành: `next_poll_at` không chỉ là metadata hiển thị; worker claim phải
  coi đó là admission gate. Claim-scoped fallback phải khớp cả root scene index,
  scene marker và Key4U candidate; exact quote một mình không cấp quyền cho scene
  khác. RED `2 failed in 773.83s`; GREEN `2 passed in 6.00s`; focused `33 passed`;
  protected `165 passed`; final combined sau mọi self-review `206 passed, 1 baseline
  deselected in 28.88s`;
  full compile/YAML/diff/scope/secret exit `0`.

## Bổ sung SubDub Auto multi local speaker-embedding ONNX — 01/09/2026

- Phạm vi duy nhất là exact state `voice_kind=auto_speaker_gender`,
  `voice_selection_mode=auto_speaker`, `auto_speaker_lane=multi`. Auto 2-speaker,
  manual/default, Product Video, PayOS và wallet không dùng backend mới.
- Authority source mới trên branch là một Deepgram word timeline strict, không
  request provider diarization. Mỗi word phải có index/start/end hợp lệ; mọi word
  được gán đúng một lần và giữ nguyên start/end qua acoustic cue, translation,
  TTS plan và mux. Embedded subtitle/OCR không được thay thế timeline này ở lane
  acoustic multi.
- Backend local dùng model
  `assets/models/subdub_auto_multi/voxceleb_resnet34.onnx`, đúng `26,534,127`
  bytes, SHA-256 `9FEA6516D7AD6BF0A76C7689F5A49B65D330FAD6DDE96C91BB4435FFBFE056A1`,
  input `feats [B,T,80]`, output `embs [B,256]`, chỉ
  `CPUExecutionProvider`. Ba notice/license bắt buộc phải có trước inference;
  model hoặc notice sai hash/missing thì fail-closed trước TTS/mux.
- Acoustic planner tách word units ở gap `>350ms`, tối đa `2.5s`; frontend là
  NumPy fbank 80-bin đối chiếu golden SHA-256 `4CE1C8BE...A7C32`. Embedding dùng
  cửa sổ `1.5s`, bước `0.75s`, short-region repeat-to-fill và hai view ổn định.
  Speaker count chỉ được chọn trong `3–8`; không nhận expected-speaker hint và
  không dùng provider label để ép `k`.
- Exact-fixture resource gate local đã đo `18` acoustic regions không overlap,
  `14` speech runs, `87` subsegment windows, `174` embeddings/two views và
  stable `k=5`; region stability `18/18`, base-window cluster sizes
  `[17,24,13,20,13]`, region cluster sizes `[2,6,2,7,1]`. Đây là offline
  resource proof, chưa phải MP4/LIVE PASS.
- Workspace job cũ không có strict transcript checkpoint. Vì vậy `k=5` resource
  authority dùng đúng cue timings của job sau khi xóa speaker/text/provider và
  union overlap; fixture `50` words tách riêng chỉ chứng minh parser/unit/coverage,
  không được nhận là transcript thật của job. Production full seam bắt buộc được
  chứng minh lại bằng chính same-job LIVE.
- Sidecar/resume chỉ hợp lệ khi model hash, algorithm version, source media,
  strict timeline và acoustic aggregate authority cùng khớp. Legacy/provider
  sidecar hoặc bundle thiếu acoustic fields phải force-fresh; bundle acoustic
  hợp lệ được resume mà không gọi ASR lần hai. Chỉ lưu aggregate bounded; cấm
  lưu embedding, PCM, raw provider payload hoặc transcript vào state.
- Final recovery được khóa vào chính internal job
  `b4cb6d5fe8a7bdfce507` / public `#B4CB6D5FE8`, fixture SHA-256
  `83DE97B744B931E544B569E6E750F8415545F226461BD2E36CFB49225898AD3E`,
  English, gốc `40%`, lồng `150%`, `charged_xu=0`. Model preflight chạy trước
  transaction; CAS chỉ cho attempt/correction `3/2 -> 4/3`, giữ cùng row/job/
  workspace, đánh marker acoustic one-shot. Attempt `5`, duplicate/concurrent
  loser, output/delivery đã có hoặc charge khác `0` đều bị chặn và không mutation.
- Các bẫy đã đo và khóa bằng regression: global eigengap từng chọn `k=1/2` rồi
  tự reject; whole-run embedding làm mất người nói ngắn; overlap bị đếm hai lần;
  shifted view từng append sai repeated tail; so stability ở window label làm
  fail giả dù region đồng nhất; typed acoustic evidence từng bị string-coerce/
  drop. Không sửa bằng fixture hash branch, expected `k`, label override hay nới
  threshold riêng cho video này.
- Source/resource hiện đã có `11` commit từ spec/plan tới fixture proof. Gate fresh
  Task 10: focused direct-impact `281 passed in 10.88s`; resource gate model thật
  `3 passed` hai process fresh (`22.68s`, `21.31s`); protected exact-two/direct
  impact replay `78 passed in 513.92s`; full changed-Python compile/diff exit `0`; exact-two
  hashes vẫn `DE93620F...145B` và `94748DEF...1177E`. Source tests gọi provider
  `0`, DB/wallet mutation `0`.
- Protected run đầu có `77 passed + 1` harness failure: comparator cũ gắn lane
  `multi` nhưng fake ASR không khai báo strict-word interface và không trả word
  timeline/acoustic result. Production fail-closed đúng tại `AUTO_CAST_UNAVAILABLE`.
  Chỉ fixture test được cập nhật để exact-two vẫn request diarization/fallback,
  multi request strict words rồi local acoustics; focused `2 passed in 4.78s`,
  full replay `78 passed`, không sửa production.
- Exact diff review đo `4` production files / `2,416` added lines: fixture-specific
  acoustic branch `0`, expected-speaker hint `0`, provider crosswalk call addition
  `0`, network import `0`, raw PCM/embedding/payload persistence `0`, wallet
  mutation `0`; verdict Critical `0`, Important `0`. Tester surface local giữ
  đúng `4` issue templates và thêm `5` case source/resource/CAS, không tạo issue/
  Project bên ngoài.
- Post-rebase lên exact Product Video/main runtime base
  `47D56E5C78EFEBB5FDED42FEC456B13F84C9A37C`: Git bỏ đúng commit crosswalk
  đã merge, giữ `12` scoped commits, branch `0 behind/12 ahead`. Focused
  `281 passed in 529.36s`; protected exact-two/direct impact
  `78 passed in 530.83s`; real ONNX resource `3 passed in 18.02s`.
- Resource RED sau checkout: two JSON fixtures có content Git LF nhưng working
  tree bị `core.autocrlf=true` đổi CRLF, làm SHA mismatch trước inference. Fix
  chỉ thêm `.gitattributes text eol=lf` cho đúng hai fixture; bytes quay lại exact
  `C061A165...B802F` và `5F16F84E...71D95F`, resource GREEN `3 passed`.
  Không đổi JSON data, hash constants, model hay production behavior.
- Cùng gate hash phát hiện spec approved Markdown cũng bị checkout CRLF. EOL
  contract được mở rộng đúng một path spec; byte rewrite chỉ thay CRLF→LF và
  khôi phục exact approved SHA-256 `5A0B0864...A5E5`, nội dung Git không đổi.
- PR `#967` đã deploy exact runtime `C6A431E2...BA95`; run `33516918998`
  SUCCESS `3m47s`, services active, health `ok`, NumPy `2.4.6`, ORT `1.29.0`,
  CPU preflight và hash model/spec/fixtures đều PASS.
- Pre-CAS read-only cho job `#B4CB6D5FE8` xác nhận attempt `3/2`, no-charge/
  no-output, nhưng root copies của SHA/language/40/150 là null. Durable authority
  vẫn đầy đủ/exact trong `auto_multi_recovery`, đúng structure executor đang đọc.
  Guard correction tối thiểu bắt nested authority; root copies được phép thiếu
  nhưng nếu hiện diện và mâu thuẫn thì fail-closed. Source path/file SHA vẫn
  được resolve/hash lại trong transaction trước CAS. RED `2 failed`; GREEN
  `2 passed`; recovery `56 passed`; protected `48 passed`; compile/diff `0`;
  chưa gửi command, provider/DB/wallet mutation `0`.
- Trạng thái vận hành hiện tại là `SOURCE_AND_RESOURCE_PASS / NOT_DEPLOYED /
  LIVE_PENDING`. Chỉ được công nhận LIVE PASS khi **chính** job `#B4CB6D5FE8`
  giao MP4 thật rồi một receipt, có `3–8` speaker âm học, số distinct voice bằng
  speaker count, cue timing không lệch và mọi finance delta bằng `0`.

### Fixed-vocal authority v2 — 02/09/2026

- Live forensic bác bỏ word/VAD speaker-count authority: hai ASR timeline độc
  lập chọn `k=6` và `k=5`; pairwise agreement `87.3518%` nhưng ARI chỉ `0.637`;
  raw-mix và UVR VAD cũng đổi `k` theo threshold.
- Exact Auto Multi v2 tìm speaker trước ASR mapping: stereo `44.1 kHz` -> UVR
  vocal stem khóa hash -> mono `16 kHz` -> fixed windows `1.5s/0.75s` -> energy
  percentiles `42.5/45/47.5/50` -> exact core partition -> overlap/centroid word
  mapping. Không dùng expected speaker count hoặc fixture-specific branch.
- Exact fixture đo `5` speaker, `50` words, `23` units, `178` embedding views,
  clusters `[9,18,26,25,11]`, speaker-unit coverage `[3,2,4,11,3]`, `19`
  overlap mappings, `4` centroid mappings và `11` final segments. Cosine min/
  mean là `0.990487/0.997246`.
- Post-main base `ab267bed`: recovery `57 passed in 529.16s`, focused/protected
  `307 passed in 10.84s`, real resource `4 passed in 165.18s`; fixed-vocal call
  `139.76s`, dưới wall budget `300s`. Full compile/YAML/diff/hash/secret exit
  `0`; provider/DB/wallet mutation `0`.
- Không persist raw word text, PCM, embeddings hoặc centroids. Hai exact-two
  SHA vẫn `DE93620F...AC145B` và `94748DEF...1177E`.
- Lệnh recovery cũ của `#B4CB6D5FE8` đã được dùng và không được gửi lại. Sau
  exact-SHA deploy cần fresh Owner action-time authorization cho đúng một same-job
  continuation; cấm upload/Confirm/job mới. LIVE PASS vẫn đòi MP4 + receipt thật.

### Vận hành one-shot upgrade v1 -> fixed-vocal v2 — 02/09/2026

- PR `#974` merge `c8e954a03322f4af8559cf3f6e99178dbd6bfe7a`; compile guard
  `33599876207` SUCCESS `27s`; deploy run `33600033108` SUCCESS `3m53s`.
  VPS exact SHA, tracked diff `0`, bot/web/nginx active/running, health `ok`.
- Runtime fixed-vocal model preflight PASS với exact model SHA và CPU provider.
  Job `#B4CB6D5FE8` vẫn lưu v1 cũ, attempt/correction `4/3`, hai marker cũ true,
  `charged_xu=0`; ASR/translation/TTS/mux/artifact/delivery chưa chạy. Bẫy: code
  v2 đã deploy không tự làm marker v1 đã consumed chạy lại được.
- Script rearm mới chỉ hợp lệ cho exact transition v1 -> v2, giữ attempt `4/3`
  và hai marker cũ, thêm một marker v2. Preflight model/CPU chạy trước DB; duplicate,
  concurrent loser hoặc bất kỳ mismatch nào đều no-op. Script không được chạy
  trước fresh Owner authorization sau exact-SHA deploy của chính script.
- Source TDD hiện tại: initial RED `13 failed`; review RED `4 failed`; final
  focused GREEN `24 passed`; recovery `75 passed`; protected `331 passed`; full
  compile exit `0`; provider/production-DB/wallet action `0/0/0`.

### Live fixed-vocal v2 và duration correction — 02/09/2026

- PR `#976` merge `dd217036577e2627a9bfcf8ce1ed510ba6ebb233`; compile
  guard `33615387847` SUCCESS `32s`; deploy `33615508521` SUCCESS `3m44s`.
  VPS exact SHA, tracked diff `0`, bot/web/nginx active và health `ok`.
- Owner-authorized invocation `2f1c9a37c0c349268be24ebc397b877f` CAS đúng cùng
  job `#B4CB6D5FE8`, giữ attempt/correction `4/3`, rồi terminal
  `failed_no_charge` lúc `17:26:02`. Fresh exact-acoustic path đã tới local
  acoustic sau strict word-timeline; raw words không được persist. Durable job
  vẫn giữ aggregate Gemini lịch sử `147` words / `4` provider labels / `151`
  annotations. Fixed-vocal evidence, translation, TTS, mux, artifact và delivery
  đều `0`; `charged_xu=0`.
- Root đo được: media/PCM thật `133.37542s`, nhưng ASR success trả integer
  duration `134s`. Fixed-vocal loader cho drift tối đa `0.25s`; lệch
  `0.62458s` nên fail `fixed_vocal_duration_mismatch` sau UVR và trước ONNX
  evidence. Đây là lỗi duration contract, không phải lỗi speaker count.
- Correction local chỉ ở Auto Multi helper: duration truyền vào fixed-vocal
  được đo từ số frame PCM stereo `44.1kHz`, không dùng integer ASR duration.
  Duration behavior RED `1 failed in 6.68s`, GREEN `1 passed in 7.08s`;
  duration-repair RED `1 failed in 16.86s`, GREEN `1 passed in 8.85s`;
  `39` focused repair tests và `287` Auto Multi tests PASS. Protected batch có
  `323 passed + 1` exact baseline byte-lock failure; clean detached baseline có
  đúng failure đó trong `580.03s`, nên `NEW_FAILURES=0`.
- Marker v2 đã consumed; correction thêm đúng một marker duration riêng chỉ cho
  hậu trạng thái đo trên job này. Chưa deploy, chưa được chạy live. Phải có exact
  correction SHA deploy và fresh Owner authorization trước lần continuation kế.
- Full `py_compile` cho bot/worker/helper/runner/tests exit `0`; YAML/diff-check
  exit `0`. Production delta chỉ helper Auto Multi + exact-job runner; không có
  provider call, production DB mutation hoặc wallet mutation trong source TDD.

### Live duration repair và Deepgram timeout contract — 02/09/2026

- PR `#979` merge `899a93f5420f47c95fcc88cd4b8de655f7fee8c8`;
  compile guard `33643563823` SUCCESS `28s`; deploy `33643751951` SUCCESS
  `3m38s`. VPS exact SHA, tracked diff `0`, bot/web/nginx active, health `ok`,
  fixed-vocal v2 model/CPU preflight PASS.
- Owner-authorized duration invocation `a13ecafffd31411d89e6b16837c64742`
  CAS đúng cùng job lúc `22:29:28`, marker duration true, giữ attempt `4/3`,
  rồi terminal `failed_no_charge` lúc `22:31:10`. Acoustic/translation/TTS/mux/
  artifact/delivery đều `0`; `charged_xu=0`; finance `322/0/0/11`, wallet `200/0`.
- Root mới đo được ở provider receipt `22:31:08`: caller chọn timeout `300s`
  cho media `134s`, nhưng non-diarization branch của `deepgram_asr_adapter`
  không forward tham số nên diagnostic dùng default `60s`. Deepgram trả
  `status=FAIL,error=deepgram_timeout`; adapter đổi thành `deepgram_empty_transcript`
  và tầng ASR tiếp tục đổi thành unavailable/empty transcript.
- Correction local forward `timeout_seconds` cho strict-word branch và giữ
  `deepgram_timeout` xuyên adapter + ASR. Không đổi manual default `60s`, không
  thêm retry/fallback/provider call. Adapter RED `1 failed in 7.41s`, GREEN
  `1 passed in 591.21s`; ASR RED `1 failed in 5.53s`, GREEN `1 passed in
  510.85s`; timeout contract `10 passed + 7 subtests`; direct impact `90 passed
  + 7 subtests`; combined recovery/Auto Multi `194 passed + 7 subtests`.
- Một ASR-timeout marker local chỉ hợp lệ khi job có v2 + duration markers,
  ASR started nhưng mọi downstream/output/charge false, và SQLite receipt exact
  `deepgram/listen/DEEPGRAM_EMPTY_TRANSCRIPT/deepgram_timeout/22:31:08` do Owner.
  Marker giữ attempt `4/3`, reset chỉ `asr_started`; sáu receipt mutations và
  duplicate đều no-op. Full bot/runner/test compile, YAML và diff-check exit `0`;
  production additions không có retry/fallback/provider call/secret/PayOS/wallet.
  Production read-only xác nhận receipt `updated_by=7126457028`; query mutation `0`.
  Correction chưa commit, chưa deploy, chưa live-authorized.

### Quy trình nạp thủ công QR và admin duyệt — 04/09/2026

- Luồng khách hiện tại là: `/naptien` → `Nạp thủ công` → chọn `VND` → chọn
  mệnh giá (`10k`, `20k`, `50k`, `100k`, `200k` hoặc `500k`) → chọn kênh
  `ACB/VietQR` hoặc kênh manual đang mở → bot gửi một ảnh QR/hướng dẫn có số
  tiền, Xu dự kiến và nội dung chuyển khoản.
- Chọn mệnh giá manual chỉ lưu bản nháp ngắn hạn trong `USER_BILL_STATE`;
  không tạo `payos_orders`. Test callback và `/thucong 50k` đo được
  `2 passed, 1 warning in 523.59s`, cả hai DB tạm đều có `payos_orders=0`.
- Khách bấm `Tôi đã chuyển khoản / gửi bill`, rồi gửi ảnh bill. Bot ghi đúng
  một hàng `pending_deposits` với `status=pending_admin_review`; lúc này
  `users.credits` không tăng và không có `manual_deposit` credit event dương.
  Test bill + duplicate file đo được `2 passed, 1 warning in 7.21s`; file lặp
  trả `duplicate_file_unique_id` và không tạo hàng thứ hai.
- Admin nhận ảnh bill kèm mã `deposit_id`, user, phương thức, số tiền và Xu.
  Nút `Duyệt đúng Xu dự kiến` chỉ mở bước xác nhận, chưa cộng Xu. Nút xác nhận
  thứ hai chạy transaction `BEGIN IMMEDIATE`, đọc lại đúng `deposit_id`, ghi
  `approved_xu/approved_by/approved_at`, đổi hàng sang `approved` và tạo đúng
  một `manual_deposit` credit event. Test approval/reject và risk comparator đo
  được `47 passed, 1 warning in 27.19s`.
- Nút từ chối chỉ đổi đúng hàng được chọn sang `rejected`, thông báo khách và
  không tạo credit event manual. Một hàng khác của cùng user vẫn giữ pending.
- Không cộng Xu từ ảnh bill/TXID tự động; chỉ admin xác nhận sau khi đối soát
  giao dịch thật. Các test trên dùng SQLite tạm; chưa gọi PayOS thật, chưa
  mutate ví production và chưa deploy đợt sửa này.

#### Bổ sung kiểm tra metadata sau CAS duyệt — 04/09/2026

Sau khi status được CAS sang `approved` ở đầu transaction, bước ghi metadata
được khóa theo đúng `deposit_id` và `status='approved'`; không còn một UPDATE
status lần hai có thể trả zero-row rồi làm mất ngầm `payment_market` hoặc
`successful_topup_ordinal`. Regression metadata xác nhận cùng hàng giữ
`payment_market=VN`, `domestic_eligibility=1`, `successful_topup_ordinal=7`.
Batch approval/reject/risk sau sửa đo được `48 passed, 2 warnings in 33.00s`.
`py_compile bot.py local_worker.py` thoát `0`, `git diff --check` thoát `0`.

#### Hotfix callback QR-photo gửi bill — 04/09/2026

- QR manual được Telegram gửi bằng `send_photo` kèm caption và nút. Callback
  `manual|await_bill|<uid>` vì vậy xuất phát từ message ảnh, không phải text.
- Forensic VPS lúc `14:01:42 +07` đo được `BadRequest: There is no text in the
  message to edit` tại `handle_manual_package_choice`; generic error đã che
  traceback nên khách không nhận prompt gửi bill. Đây là lỗi render callback,
  không phải PayOS, ví Xu hay thiếu lệnh duyệt admin.
- Hotfix dùng fallback render hiện hữu cho photo callback: giữ QR và trả một
  prompt gửi bill mới; state vẫn là `await_bill`. Chỉ khi ảnh bill/TXID được
  nhận mới tạo `pending_admin_review` và gửi card duyệt cho admin.
- RED `1 failed in 424.99s`; GREEN callback + bill + duplicate `3 passed,
  2 warnings in 490.21s`; full manual regression `19 passed, 268 deselected,
  2 warnings in 9.44s`. Không gọi PayOS/provider hoặc mutate production trong
  các test.

## SubDub Auto Multi private-context closeout — 04/09/2026

- Phạm vi chỉ là exact Auto Multi và same-job `#B4CB6D5FE8`. Auto 2-speaker
  vẫn `LOCKED_LIVE_PASS`; hai file authority exact-two có diff rỗng so với
  `origin/main`.
- Root live đã đo: strict Deepgram ASR thành công nhưng hai lần ghi pending
  state loại bỏ invocation-only `_pipeline_*`; acoustic stage vì vậy mất
  workspace/source và terminal `AUTO_CAST_MANUAL_REQUIRED` ở `5%`, trước
  translation/TTS/mux/artifact/delivery, `charged_xu=0`.
- Correction giữ bốn field `_pipeline_workspace`,
  `_pipeline_saved_source_path`, `_pipeline_source_bytes_override`,
  `_pipeline_source_content_type_override` qua prepare/translation và trả lại
  cho classifier/TTS/mux chỉ trong lane Multi. Không persist raw bytes vào DB.
- Attribution được khóa hai tầng: tập speaker đã đi TTS phải bằng đúng tập
  speaker acoustic; mỗi speaker giữ một voice riêng xuyên mọi cue. Durable
  terminal proof chỉ tồn tại khi `auto_multi_attribution_verified=true`.
- Vì source trong workspace production đã cleanup, runner same-job chỉ được
  rehydrate từ Telegram `file_id` đã lưu và khớp token trong job key. Exact
  size, MIME `video/mp4` và fixture SHA-256 phải PASS trước atomic file write
  và trước CAS. File hiện hữu sai hash, file ID lệch, bytes tải sai hash,
  duplicate marker và CAS loser đều no-op đối với DB và source.
- Resource gate thật trên fixture `9,869,032` bytes đo `k=5`, word coverage
  `50/50`, `23` units, `178` embedding views, clusters `[9,18,26,25,11]`,
  speaker-unit counts `[3,2,4,11,3]`, overlap mappings `19`, centroid mappings
  `4`, và `11` cues/`5` speaker IDs; hai lượt temp sạch `1 passed in 136.87s`
  và `1 passed in 119.25s`. Model-byte/missing-
  notice negative gate `2 passed in 0.89s`.
- Full-chain provider-stub rehearsal đi qua `5` acoustic speakers, `10`
  translated cues, `10` scalar TTS calls, `5` voice riêng, cue-lock và MP4 mux:
  `1 passed in 5.39s`. Mapping-evidence RED/GREEN là `9 failed in 5.71s` →
  `14 passed in 383.36s`; final focused/protected gate `365 passed, 1` baseline
  stale-hash test deselected in `12.36s`; exact-two selected comparator `46
  passed`; full changed-file compile và diff-check exit `0`.
- Side effects của toàn local loop: provider calls `0`, production DB mutations
  `0`, wallet mutations `0`. Trạng thái là `LOCAL_SOURCE_AND_RESOURCE_PASS`;
  chưa push, chưa deploy và chưa LIVE PASS. Voice acoustic distinctness của
  MP4 cuối chỉ được đo sau khi có artifact thật bằng ngưỡng hiệu chuẩn; source
  không bịa cosine threshold.

### Live RED downloadable Telegram identity — 05/09/2026

- PR `#990` deploy exact runtime `b5a972850a5bf441d44a50c4a445f342088a3165`;
  deploy run `33903797590` SUCCESS `3m42s`; VPS tracked diff `0`, services/health
  active/ok và fixed-vocal preflight chọn đúng `CPUExecutionProvider`.
- Owner-authorized unit
  `toanaas-subdub-private-context-b4cb6d5fe8-b5a97285.service`, invocation
  `8dfa559e6a034a9081b63669f28ad805`, terminal exit `1` trước CAS tại Telegram
  `get_file` với `telegram_download_failed:api`. Context marker chưa dùng;
  ASR/translation/TTS/mux/artifact/delivery đều false.
- Root đo được: `subtitle_dub_pipeline_job_key()` dùng `file_unique_id` để
  idempotency. Recovery cũ lại lấy token này làm `source_file_id`, rồi ghi đè
  `input_save.file_id`. Durable job vì vậy chỉ còn cùng unique ID dài `15` ký tự,
  không còn full Telegram `file_id` có thể download.
- Forensic read-only kiểm `20` startup DB backups, `2` exact-job JSON backups,
  journal và Local Bot API exact-size cache; không tìm thấy full file ID hoặc
  source `9,869,032` bytes. Không suy diễn file đã chết từ lỗi transport; authority
  đơn giản là full ID không còn được persist ở bất kỳ nguồn đo nào.
- Correction local lưu riêng `file_id` và `file_unique_id`; job key chỉ khớp
  unique ID, Telegram chỉ nhận full ID distinct/nonempty. Legacy alias, ID sai
  type hoặc nhiều full IDs mâu thuẫn đều fail-closed.
- TDD: contract RED/GREEN `4 failed -> 5 passed`; legacy RED/GREEN `2 failed ->
  5 passed`; type RED/GREEN `2 failed + 2 passed -> 6 passed`; full recovery
  `124 passed`; direct impact `373 passed + 1` baseline test deselected;
  exact-two `46 passed`. Provider/DB/job/transaction/wallet/credit delta trong
  live RED đều `0`; Owner credits/spent vẫn `200/0`, `charged_xu=0`.

### Live RED normalized acoustic source — 05/09/2026

- PR `#991` deploy runtime `9715b6f0a7436347fd1b3a8023fe89bc8bbf3938`.
  Exact fixture được restore mode `600`, đúng `9,869,032` bytes/SHA
  `83DE97B7...98AD3E`; invocation `648943c375da47659795fb6314040dc3`
  CAS đúng một lần và Deepgram PASS `145` words.
- Job sau đó fail trước translation/TTS/mux. Direct traceback trên chính
  `normalized_source.mp4` là `fixed_vocal_speaker_count_unstable`.
- Original source giữ AAC `44.1kHz`; normalization AV1→H.264 đã resample audio
  lên `48kHz`, rồi acoustic extractor resample lại `44.1kHz`. Hai lần resample
  làm bốn fixed-vocal stability views không còn đồng ý về speaker count.
- Direct original-source diagnostic PASS exact `k=5`, `50` words, `23` units,
  `178` views, clusters `[9,18,26,25,11]`, speaker units `[3,2,4,11,3]`,
  overlap/centroid `19/4`.
- Correction chỉ đổi input của exact Auto Multi acoustic: dùng original
  hash-locked source. ASR/render vẫn dùng normalized video; non-Multi và exact-two
  giữ saved normalized path. RED/isolation `1 failed + 1 passed`; GREEN
  `3 passed in 471.43s`. `charged_xu=0`; không job mới.
- Direct impact `375 passed + 1` known baseline deselected; exact-two `46
  passed`; full compile/YAML/diff exit `0`.
- Cùng job đã consume context marker nên correction có marker original-source
  riêng, chỉ nhận exact aggregate `acoustic_failure_unknown`, `145` words,
  `134000ms`, attempts `4/3`, downstream/output false, charge `0`. Marker
  RED/GREEN `1 failed -> 1 passed`; full recovery `125 passed`; direct impact
  `376 passed`; duplicate no-op.

### Auto Multi acoustic runtime budget và lỗi `5%` — 05/09/2026

- Runtime `a0c45d4d6b222bc747c71202eb228f67c72b94a6` đã dùng original source nhưng
  same-job invocation vẫn terminal `failed_no_charge` ở `5%`, strict ASR `145`
  words, trước translation/TTS/mux/artifact/delivery. Durable evidence chỉ ghi
  `acoustic_failure_unknown`, vì bộ lọc cũ chỉ nhận mã `acoustic_*` và làm mất
  các cause hợp lệ `fixed_vocal_*` của chính engine.
- Hai Deepgram diagnostic read-only trên cùng normalized source đều trả `145`
  words nhưng timing-only SHA khác nhau: `8AD855EC...2737DE8` và
  `948B4F94...DF42AF`; đúng `3/145` hàng timestamp khác, delta lớn nhất `80ms`.
  Cả hai chạy original acoustic source và đều PASS `k=5`, `37` units, `178`
  embedding views, clusters `[9,18,26,25,11]`, speaker-unit counts
  `[2,9,9,11,6]`, overlap/centroid `29/8`, `23` cues và đủ `5` speaker. Nội
  dung từ không được persist; fixture regression chỉ giữ index/timing và token
  `wordNNN`.
- Async wrapper thật có một lượt PASS `247s` wall trên video `133.37542s`, tức
  dùng hơn `82%` budget cố định `300s`; một fresh-ASR wrapper khác PASS `156s`.
  Budget cố định vì vậy không bao phủ ổn định toàn direct lane tối đa `300s`.
  Correction dùng chính duration đo từ stereo PCM: `max(300, ceil(duration*4))`,
  cap `1200s`; không đọc fixture SHA, job ID, codec hay expected speaker count.
  Timeout giờ có cause `acoustic_runtime_timeout`; các cause an toàn
  `acoustic_*` và `fixed_vocal_*` đều được giữ để lần fail không còn thành
  `unknown`.
- TDD timeout/observability RED `7 failed, 1 passed` rồi GREEN `8 passed`.
  Same-job marker RED/GREEN `1 failed, 4 passed` → `5 passed`; duplicate,
  charged/output mutation và wrong failure aggregate đều no-op. Auto Multi
  regression `338 passed`; exact-two comparator `37 passed`; real model/source
  resource gate `5 passed in 255.84s`; full compile và diff-check exit `0`.
- Đây là `SOURCE_AND_RESOURCE_PASS`, chưa phải deploy hoặc LIVE PASS. Chỉ cùng
  job `#B4CB6D5FE8` được CAS bởi marker runtime-budget mới sau exact-SHA deploy;
  attempts vẫn `4/3`, marker cũ giữ nguyên, không upload/Confirm/job mới và
  `charged_xu=0`.
