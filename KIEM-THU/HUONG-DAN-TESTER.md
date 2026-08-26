# Hướng dẫn tester Product Video

1. Chọn đúng case trong `DANH-SACH-CASE.md`; không tự đổi scenario giữa chừng.
2. Ghi baseline project/job/outbox/transaction trước khi bấm Xác nhận cuối.
3. Đi qua đúng Add-on -> Review -> Chất lượng -> Hóa đơn -> Xác nhận -> Trạng thái.
4. Chỉ bấm Xác nhận cuối một lần; thử callback lặp chỉ khi case yêu cầu idempotency.
5. Chờ job terminal. Queued/processing/HTTP 200 không phải PASS.
6. Tải MP4, đo hash, bytes, codec, kích thước, duration, scene coverage và audio.
7. Đối chiếu add-on trong job/manifest với video thật.
8. Ghi delivery message id, `charged_xu` và transaction delta.
9. FAIL ở bước nào thì mở lại đúng spec/case đó; không chuyển sang case tiếp theo.

Lỗi cũ cần canh: literal `\\n`, status nằm ngang, video mất audio, back nhảy sản phẩm, tier bị đổi, thiếu scene, add-on bị drop, duplicate job/delivery.
