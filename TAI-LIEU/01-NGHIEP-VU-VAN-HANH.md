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
