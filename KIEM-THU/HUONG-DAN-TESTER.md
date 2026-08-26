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

## Cách test Public Landing Motion

1. Dùng đúng sáu case `ML-01..ML-06`; tải mới trang trước mỗi case.
2. Cuộn từ đầu tới cuối rồi quay lại; mỗi section chỉ được reveal một lần, không flash hoặc mắc kẹt mờ.
3. Desktop rê chuột tới bốn góc preview; độ lệch không quá `10px`. Tablet/mobile không được parallax.
4. Bật giảm chuyển động của hệ điều hành; nội dung, CTA và form phải hiện ngay.
5. PASS chỉ khi JSON có `failures=[]`, CLS/long task/overflow/pending/runtime error đều `0` ở cả hai lượt.
6. FAIL thì cập nhật issue `#884` và mở lại đúng `MOTION-LANDING-TOANAAS-001`; không sửa Bot/lead/Telegram/PayOS.
