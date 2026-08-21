# TOAN AAS Bot/App Knowledge Base

Last updated: 2026-08-11

## TOAN AAS là gì

TOAN AAS là hệ thống tự động hóa AI cho tạo nội dung, ảnh, video, voice, dịch thuật, tài liệu, ghi chú và hỗ trợ khách hàng. Bot Telegram là kênh thao tác nhanh. App/web là khu điều khiển dài hạn cho tài khoản, ví Xu, công cụ và dashboard.

## Bot Telegram dùng làm gì

- Tạo ảnh AI, chỉnh ảnh local, chỉnh ảnh AI khi provider thật sẵn sàng.
- Lên ý tưởng video, trend, storyboard, prompt ảnh/video và xuất video AI theo gói đã mở.
- Dịch văn bản, voice/audio, phụ đề và lồng tiếng video theo mode đã qua smoke test.
- Quản lý Xu, gói đã mua, combo, ghi chú, tài liệu và ticket hỗ trợ.
- Hỏi AI và hỏi trợ lý TOAN AAS về cách dùng hệ thống.

## App.toanaas.vn dùng làm gì

App là trung tâm dài hạn cho tài khoản, ví Xu, dashboard, workspace, quản lý file, công cụ AI và sau này là đầu não điều phối tự động hóa. Bot vẫn là kênh thao tác Telegram nhanh.

## Chính sách Xu cơ bản

1 Xu tương đương 100 VND trong hệ thống. Bot chỉ trừ Xu sau khi người dùng xác nhận bước cuối. Nếu provider lỗi trước khi có kết quả hợp lệ, hệ thống không trừ Xu hoặc hoàn Xu theo chính sách từng công cụ.

## Gói video public

- Tier ID 200: Nhanh gọn, 5 giây/cảnh, 200 Xu/cảnh.
- Tier ID 300: Tiêu chuẩn có âm thanh, 5 giây/cảnh, 220 Xu/cảnh.
- Tier ID 400: Cân bằng rõ nét, 8 giây/cảnh, 80 Xu/cảnh.
- Tier ID 500: Chuyển động ổn định, 5 giây/cảnh, 110 Xu/cảnh.
- Tier ID 600: Chuyển động có âm thanh, 5 giây/cảnh, 160 Xu/cảnh.
- Tier ID 700: Cảnh dài có âm thanh, 15 giây/cảnh, 220 Xu/cảnh.
- Tier ID 800: Cao cấp linh hoạt, 10 giây/cảnh, 370 Xu/cảnh.
- Tier ID 1000: Diễn xuất chân thật, 6 giây/cảnh, 370 Xu/cảnh.
- Tier ID 1200: Đa góc máy, 8 giây/cảnh, 1.260 Xu/cảnh.
- Tier ID 1500: Điện ảnh nhiều cảnh, 10 giây/cảnh, 2.360 Xu/cảnh.

Tier ID là mã route/package ổn định, không phải giá bán.

## Khuyến mãi Video nhiều cảnh

- 1 cảnh không giảm.
- 2–5 cảnh giảm 10%.
- 6–10 cảnh giảm 15%.
- 11–20 cảnh giảm 20%.
- Khuyến mãi chỉ giảm phần Video theo cảnh; add-on tính riêng.

## Cách tạo video

Người dùng vào Video AI, chọn hoặc nhập ý tưởng/prompt, chọn nhạc/phụ đề/lồng tiếng nếu cần, chọn gói giá, xem hóa đơn nhỏ, xác nhận, sau đó bot tạo job và gửi kết quả khi provider trả output. Nếu provider chưa sẵn sàng, bot báo bảo trì/nâng cấp và không trừ Xu.

## Cách chỉnh ảnh AI

Người dùng gửi ảnh, chọn loại chỉnh sửa, nhập yêu cầu, chọn một trong ba phương án prompt, xem màn xác nhận rồi mới gọi provider. Nếu chưa có provider edit thật, bot chỉ báo bảo trì/nâng cấp; không tạo output giả.

## Chat AI hiểu ảnh

Chat AI có thể phân tích ảnh, đọc chữ trong ảnh, tư vấn thiết kế/nội dung, tạo prompt ảnh/video từ ảnh và chuyển sang flow chỉnh sửa ảnh khi người dùng muốn sửa ảnh.

## Dịch phụ đề và lồng tiếng

Pipeline chuẩn: video đầu vào -> ASR -> phụ đề -> dịch nếu cần -> TTS nếu cần -> ghép audio/subtitle nếu worker sẵn sàng -> gửi file output. Mỗi mode chỉ mở public khi provider và smoke test tương ứng pass.

## Media AI provider gate

Chỉnh sửa ảnh AI, Suno music, MiniMax Voice và pipeline phụ đề/lồng tiếng đều đi qua cùng nguyên tắc: provider readiness -> admin smoke -> public gate -> pricing -> confirm -> job -> output thật -> lỗi thân thiện. Nếu chưa có endpoint/model/tài liệu thật, hệ thống trả NEED_DOCS/NOT_CONFIGURED cho admin và báo bảo trì/nâng cấp cho khách, không fake output.

Add-on chỉ chạy khi tuyến tương ứng sẵn sàng và luôn được ghi riêng trong hóa đơn trước khi xác nhận.

## Nạp Xu

Người dùng mở Nạp Xu/Bảng giá trong bot hoặc app. PayOS/VND và các phương thức thủ công đã có policy riêng. Bot không tự cộng Xu nếu giao dịch chưa được xác nhận theo cơ chế thanh toán hiện hành.

## Lỗi và hoàn Xu

Nếu job lỗi do provider, timeout hoặc hệ thống bận, TOAN AAS báo bằng ngôn ngữ thân thiện. Nếu đã trừ Xu mà provider fail theo chính sách hoàn, hệ thống hoàn phần Xu đã trừ cho bước đó.

## Hỗ trợ

Người dùng có thể mở Hỗ trợ để hỏi nhanh, tạo ticket hoặc xem Ticket của tôi. Bot nên trả lời các câu phổ biến trước, sau đó lưu ticket khi cần admin xử lý.

## Tính năng đang phát triển

Video dài, video nhiều tập, Kling, Seedance, auto publish, ads assistant, image-to-video nâng cao và video-to-video chỉ mở sau khi có smoke test/gate rõ ràng.
