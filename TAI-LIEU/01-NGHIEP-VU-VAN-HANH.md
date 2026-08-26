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
