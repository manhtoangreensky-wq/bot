# Danh sách case Product Video và Public Landing

Nguồn gốc duy nhất cho acceptance live. Sửa case tại file này trước khi tạo/sửa Issue.

## Lane sản phẩm

| ID | Case | Kịch bản khóa | Add-on khóa | PASS bắt buộc |
|---|---|---|---|---|
| PV-L01 | Video theo trend / manual | C1 quầy cà phê xe điện mở buổi sáng; C2 sinh viên nhận ly tái sử dụng và giơ ngón tay cái | phụ đề + transitions | Tail đủ 6 màn, MP4 2 cảnh, receipt 0 Xu |
| PV-L02 | Video AI chân thật / prompt manual | C1 Linh tạo hình bình gốm xanh; C2 Linh nâng thành phẩm trong xưởng ấm | dubbing + phụ đề | Add-on thật, MP4 2 cảnh có audio, receipt 0 Xu |
| PV-L03 | Kịch bản -> Video / manual | 5 cảnh trà sen Tây Hồ: hái sen, tách gạo, ướp trà, pha trà, mời khách | voice + phụ đề + nhạc | Giữ nguyên script, min 5 cảnh, MP4/receipt |
| PV-L04 | Ghép ảnh thành video / custom | 2 ảnh đồng hồ thủ công: bàn lắp ráp và hero shot thành phẩm | chữ + transition | 2 ảnh thật, 3 quality Frame chọn được, MP4/receipt |
| PV-L05 | Video tự quay / custom | Source `PV-L05-self-shot-typing-source.mp4`: giữ người thật và động tác gõ máy; đổi phòng làm việc thành quán cà phê rooftop | source audio + watermark | Source SHA `784FBE5B...`; min 2 cảnh, MP4 có audio/receipt |
| PV-L06 | Storyboard / manual | C1 robot nhỏ gieo hạt trên mái nhà; C2 mầm cây phát sáng khi bình minh lên | transitions + phụ đề | 2 ảnh start mapped, MP4 2 cảnh/receipt |
| PV-L07 | Video dài tập / manual | C1 thợ lặn tìm cửa thư viện dưới biển; C2 mở phòng sách phát sáng và đọc bản đồ | narration + nhạc | Tail đủ, output thật/receipt theo runtime hỗ trợ |
| PV-L08 | Ý tưởng video / manual handoff | C1 xe cà phê điện tới cổng trường; C2 barista phục vụ nhóm sinh viên | phụ đề | Ý tưởng riêng đi Tail, MP4 2 cảnh/receipt |
| PV-L09 | Chỉnh sửa Video / input 2 cảnh | Source `PV-L09-edit-review-source.mp4`: cắt review 29,54s thành 2 nhịp, đổi 9:16 và giữ lời nói gốc | preserve audio + watermark | Source SHA `3A53DA94...`; operation thật, MP4 dùng được, receipt 0 Xu |

## Video AI Chân thật theo tier

| ID | Tier | Kịch bản 2 cảnh khóa | Add-on | PASS bắt buộc |
|---|---:|---|---|---|
| PV-Q200 | 200 | gấp diều giấy -> thả diều trên đê | transitions | exact tier, MP4/receipt 0 Xu |
| PV-Q300 | 300 | xếp bộ trà gốm -> rót trà cạnh cửa sổ | phụ đề | exact tier, MP4/receipt 0 Xu |
| PV-Q400 | 400 | sửa phanh xe đạp -> chạy thử trong công viên | SFX | exact tier, MP4/receipt 0 Xu |
| PV-Q500 | 500 | nghệ nhân nhuộm khăn lụa -> người mẫu choàng khăn | nhạc | exact tier, MP4/receipt 0 Xu |
| PV-Q600 | 600 | lắp đèn năng lượng mặt trời -> đèn sáng ở sân vườn | dubbing | exact tier, MP4 có audio/receipt 0 Xu |
| PV-Q700 | 700 | phi hành gia chăm vườn kính -> thu hoạch quả đỏ ngoài sao Hỏa | phụ đề | exact tier, MP4/receipt 0 Xu |
| PV-Q800 | 800 | pha nước hoa trong phòng lab -> hero shot chai trên đá đen | nhạc + SFX | exact tier, MP4/receipt 0 Xu |
| PV-Q1000 | 1000 | vũ công khởi động trước gương -> biểu diễn xoay người trên sân khấu | source dialogue | exact tier, MP4 có audio/receipt 0 Xu |
| PV-Q1200 | 1200 | máy pha cà phê góc rộng -> macro dòng espresso chảy | transitions | exact tier, MP4/receipt 0 Xu |
| PV-Q1500 | 1500 | ga tàu mưa đêm toàn cảnh -> nhân vật gặp nhau dưới đồng hồ lớn | dubbing + phụ đề | exact tier, MP4 có audio/receipt 0 Xu |

## Bằng chứng mỗi case

- Scenario/fixture hash riêng.
- REQUEST_ID, project, job, outbox.
- Hai scene output và final MP4 hash/bytes/codec/dimensions/duration.
- Audio stream + mức nghe được nếu yêu cầu audio.
- Add-on requested/materialized/applied.
- Telegram delivery message id.
- `charged_xu=0`, transaction delta 0, không duplicate.

## Public Landing Motion

| ID | Viewport/chế độ | PASS bắt buộc |
|---|---|---|
| ML-01 | `1440×900`, normal | Hero semantic opacity `1` từ 10ms; settle ≤`8px/360ms`; reveal once; parallax ≤`10px`; CLS/long task/overflow/error `0` |
| ML-02 | `768×900`, normal | Presentation motion `0`; nội dung/CTA/form đủ; overflow/error `0` |
| ML-03 | `390×667`, normal | Presentation motion `0`; nội dung/CTA/form đủ; overflow/error `0` |
| ML-04 | `360×640`, normal | Presentation motion `0`; nội dung/CTA/form đủ; overflow/error `0` |
| ML-05 | `1440×900`, reduced | Animation/parallax `0`; nội dung hiện; pending/error `0` |
| ML-06 | `390×667`, reduced | Animation/parallax `0`; nội dung hiện; pending/error `0` |

Evidence nguồn: `D:/TOANAAS/TOAN_AAS_WEB_APP/evidence/motion-landing-toanaas-001/r1/candidate-io-green-run-1/` và `candidate-io-green-run-2/`. GitHub Tester tracker: `manhtoangreensky-wq/bot#884`.

## SubDub — thứ tự acceptance khóa

Fixture hai giọng cho cả hai case đầu: `C:/Users/toann/Downloads/test sub/2 giọng nam nữ.mp4`,
`4,284,017` bytes, SHA-256 `85C8793D197CF2782BB554D46282E82A83BCB062A0483E412A0CA1DA668F9F51`.

| ID | Lane | Thiết lập khóa | PASS bắt buộc | Canh lỗi cũ |
|---|---|---|---|---|
| SD-2S-01 | Phụ đề + Lồng tiếng | English; Tự động 2 giọng; numeric UI chỉ 2 layer cùng hàng; nhập gốc 40%, lồng 150%; không preset | MP4 + SRT + receipt; đúng 2 labels/cast; giá phụ đề + lồng tiếng + total; admin 0 Xu; wallet delta 0 | `empty_transcript`; Key4U first response unavailable; FAIL nếu >2 Key4U attempts; preset grid quay lại |
| SD-2S-02 | Lồng tiếng video | Cùng fixture; Tự động 2 giọng; cùng numeric UI; gốc 40%, lồng 150%; không preset | MP4 + receipt; đúng 2 labels/cast; dubbing list price >0; admin 0 Xu; wallet delta 0 | Lane combo PASS nhưng standalone hồi quy; audio UI khác combo |
| SD-MS-01 | Tự động nhiều giọng | Chỉ dùng `test nhiều giọng.mp4`; chạy sau SD-2S-01 và SD-2S-02 | MP4 thật; mọi label/cast/voice; multi-language; receipt và wallet evidence | FAIL nếu chạm source/hash của lane 2 đã khóa |

Mỗi MP4 phải đo SHA-256/bytes/duration/dimensions/codec và AAC loudness; job id
hoặc HTTP 200 không được tính PASS. Sửa case tại file này trước khi tạo/sửa
GitHub Issue.

Comparator UI bổ sung: `2` lane × `6` kiểu giọng (nữ mặc định, nam mặc định,
Kho voice, voice riêng, Auto 2, Auto multi) phải cùng callback
`videodub|audio_mix`, cùng ba callback màn chính và cùng numeric range.
