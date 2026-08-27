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

## Cách test SubDub tự động

1. Chạy đúng thứ tự `SD-2S-01 -> SD-2S-02 -> SD-MS-01`; case trước chưa có
   artifact PASS thì cấm chạy case sau.
2. Hai case đầu chỉ upload file `2 giọng nam nữ.mp4` có SHA-256
   `85C8793D197CF2782BB554D46282E82A83BCB062A0483E412A0CA1DA668F9F51`;
   không dùng `Download.mp4` hoặc fixture lịch sử.
3. Chọn `Tự động 2 giọng`, mở `🎚 Âm thanh`. Màn chính phải chỉ có hai nút
   `Âm thanh gốc | Giọng lồng tiếng` cùng một hàng và Quay lại; không được có
   `Gốc xx%` hoặc `Lồng xx%`. Vào từng màn con để nhập gốc `40%`, lồng `150%`,
   quay lại kiểm tra hai giá trị còn nguyên, rồi confirm đúng một lần.
4. Status phải hiện từ saved input qua ASR/diarization, cast, TTS, mux và delivery;
   lỗi ở stage nào ghi đúng stage đó, không suy ra từ HTTP `200`.
5. Sidecar phải có đúng `2` speaker labels. Cast của từng label phải đến từ
   acoustic evidence độc lập; không chấp nhận forced male/female pairing.
6. Combo PASS cần MP4 + SRT + receipt đủ giá phụ đề, giá lồng tiếng, total và
   loại `Tự động 2 giọng`. Standalone PASS cần MP4 + receipt đủ dubbing list price.
7. Mỗi MP4 đo hash/bytes/duration/dimensions/codecs và AAC loudness; nghe lại để
   xác nhận có tiếng và mức gốc/lồng đúng lựa chọn.
8. Admin phải `charged_xu=0`; credits, total_spent, transaction count và wallet
   event delta phải giữ nguyên.
9. `empty_transcript`, thiếu một speaker, speaker evidence không chắc hoặc mapping
   cue dưới ngưỡng đều là FAIL-closed. Không sửa test để ép thành hai label.
10. Chỉ sau hai case 2-speaker PASS và lock manifest đã ghi hash mới dùng
    `test nhiều giọng.mp4` cho `SD-MS-01`.
11. Lặp lại contract audio UI trên giọng nữ mặc định, giọng nam mặc định, Kho
    voice, voice riêng, Auto 2 và Auto multi khi chạy case tương ứng; không chấp
    nhận một kiểu giọng mở bảng preset hoặc làm mất giá trị numeric.
12. Nếu Deepgram empty và Key4U lần đầu unusable, exact Auto 2 được gọi Key4U
    tối đa `2` lần. HTTP `401` hoặc segment không có timestamp provider phải
    dừng ngay; tuyệt đối không ép speaker hoặc mở fallback này cho Auto multi.
