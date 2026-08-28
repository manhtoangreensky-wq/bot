# Hướng dẫn tester Product Video

Strategy V2 có đúng 8 representative rows và 9 quality-only rows. Tier `400`
được representative rows bao phủ; không tạo quality-only job thứ mười.

1. Chọn đúng case `PV2-*` trong `DANH-SACH-CASE.md`; không tự đổi scenario giữa chừng.
2. Representative phải dùng lane phức tạp không-manual. Manual/direct-input chỉ
   kiểm tra source contract đi thẳng Add-on, không dùng làm paid representative.
3. Ghi baseline project/job/outbox/provider-usage/transaction/credit-event trước
   khi bấm Xác nhận cuối.
4. Đi qua đúng Add-on -> Review -> Chất lượng -> Hóa đơn -> Xác nhận -> Trạng thái.
5. Chỉ bấm Xác nhận cuối một lần; thử callback lặp chỉ khi case yêu cầu idempotency.
6. Chờ job terminal. Queued/processing/HTTP 200 không phải PASS.
7. Tải MP4, đo hash, bytes, codec, kích thước, duration, scene coverage và audio.
8. Đối chiếu Add-on requested/materialized/applied với video thật; `missing` phải rỗng.
9. Ghi video delivery message ID, file ID, file_unique_id, `charged_xu`, transaction
   delta và credit-event delta.
10. Sau MP4, kiểm tra đúng một báo cáo kinh doanh được gửi sau receipt + settlement;
    ghi `delivery_report_message_id` và `delivery_report_sent=true`.
11. Callback completion trùng không được gửi lại MP4, settlement hoặc report.
12. FAIL ở bước nào thì mở lại đúng spec/case đó; không chuyển sang case tiếp theo.

Lỗi cũ cần canh: literal `\\n`, status nằm ngang, video mất audio, back nhảy sản
phẩm, tier bị đổi, thiếu scene, Add-on bị drop/tự bật từ profile, duplicate
job/delivery/report, report gửi trước settlement hoặc lộ thông tin kỹ thuật.

13. Với output `9:16`, không chỉ kiểm tra stream width/height. Mở video và xác nhận hình thật phủ kín canvas, không có hai dải đen trên/dưới hoặc trái/phải do `pad`; cảnh ngang phải được crop-to-fill, không co nhỏ giữa khung.
14. Ở mọi nút Chất lượng, bấm một lần phải chuyển sang Hóa đơn; `Xác nhận tạo video` phải chuyển sang Xác nhận; `Bắt đầu tạo video` phải luôn chuyển sang Trạng thái kể cả provider/worker chưa sẵn sàng. Đứng nguyên màn là FAIL callback.
15. Add-on PASS cần đồng thời: project plan ghi requested, worker materialization có artifact, manifest `addon_application.requested/applied` có đúng tên và video thật thể hiện add-on. Có SRT bên cạnh nhưng `subtitle_path=null` vẫn là FAIL.
16. Customer report chỉ được chứa thông tin kinh doanh: sản phẩm, chất lượng,
    cảnh/thời lượng/tỉ lệ, giá video, Add-on miễn phí/có phí/đã áp dụng, phí Add-on,
    tổng hóa đơn, Xu thực trả và trạng thái giao. Có provider, worker, job/task ID,
    SHA, manifest, JSON, engine route hoặc mã lỗi nội bộ là FAIL.
17. Không test `multi_scene_film`, `video_long`, `video_local_edit` hoặc
    `videoedit|ai` trong chu kỳ V2 hiện tại. Local Edit là baseline đã khóa.

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
6. Combo và standalone chỉ được tự gửi MP4 rồi receipt cuối. Không được tự gửi
   SRT, audio, sidecar hoặc document phụ; SRT chỉ dùng nội bộ để gắn phụ đề/QC
   hoặc khi người dùng chủ động bấm tải. Receipt phải đủ giá phụ đề, giá lồng
   tiếng, total và loại `Tự động 2 giọng`.
7. Nghe từng cue: giọng dịch phải bắt đầu/kết thúc trong đúng timestamp phụ đề
   gốc; cue sau không bị trễ vì cue trước dài. Evidence job phải có số cue đo,
   `speech_rate_max_drift_seconds=0` và duration MP4 bằng duration nguồn trong
   tolerance validator.
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
13. Fixture karaoke có nhạc nền: kiểm evidence cast, không chỉ nhìn hai label.
    Kết quả khóa local là speaker 0 `male/low`, vote `7/8`, dominance `0.875`,
    evidence `21s`; speaker 1 `female/high`, vote `8/10`, dominance `0.800`,
    evidence `27s`. Tổng unique evidence `48s`, classifier provider calls `0`.
    Filter cũ từng trả sai `high/high`; raw-frame fallback đã bị cấm. Nếu log
    chỉ có label mà không có gender/register/dominance/evidence time, hoặc dùng
    “một nam + một nữ” không qua vote độc lập, FAIL.
