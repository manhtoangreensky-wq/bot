# Danh sách case Product Video

Nguồn gốc duy nhất cho acceptance live. Sửa case tại file này trước khi tạo/sửa Issue.

## Lane sản phẩm

| ID | Case | Mức | PASS bắt buộc |
|---|---|---|---|
| PV-L01 | Video theo trend / manual | chặn-bán-hàng | Kịch bản riêng, Tail đủ 6 màn, MP4 2 cảnh, receipt 0 Xu |
| PV-L02 | Video AI chân thật / prompt manual | chặn-bán-hàng | Kịch bản riêng, add-on thật, MP4 2 cảnh, receipt 0 Xu |
| PV-L03 | Kịch bản -> Video / manual | chặn-bán-hàng | Giữ nguyên script, min 5 cảnh theo contract, MP4/receipt |
| PV-L04 | Ghép ảnh thành video / custom | nặng | 2 ảnh thật, 3 quality Frame chọn được, MP4/receipt |
| PV-L05 | Video tự quay / custom | chặn-bán-hàng | Video nguồn thật, nội dung riêng, min 2 cảnh, MP4 có audio/receipt |
| PV-L06 | Storyboard / manual | chặn-bán-hàng | 2 ảnh start mapped, Tail đủ, MP4 2 cảnh/receipt |
| PV-L07 | Video dài tập / manual | chặn-bán-hàng | Kịch bản riêng, Tail đủ, output thật/receipt theo runtime hỗ trợ |
| PV-L08 | Ý tưởng video / manual handoff | nặng | Ý tưởng riêng đi Tail, MP4 2 cảnh/receipt |
| PV-L09 | Chỉnh sửa Video / input 2 cảnh | nặng | Operation thật, output MP4 dùng được, receipt 0 Xu |

## Video AI Chân thật theo tier

| ID | Tier | Mức | PASS bắt buộc |
|---|---:|---|---|
| PV-Q200 | 200 | chặn-bán-hàng | Kịch bản riêng 2 cảnh, exact tier, MP4/receipt 0 Xu |
| PV-Q300 | 300 | chặn-bán-hàng | Kịch bản riêng 2 cảnh, exact tier, MP4/receipt 0 Xu |
| PV-Q400 | 400 | chặn-bán-hàng | Kịch bản riêng 2 cảnh, exact tier, MP4/receipt 0 Xu |
| PV-Q500 | 500 | chặn-bán-hàng | Kịch bản riêng 2 cảnh, exact tier, MP4/receipt 0 Xu |
| PV-Q600 | 600 | chặn-bán-hàng | Kịch bản riêng 2 cảnh, exact tier, MP4/receipt 0 Xu |
| PV-Q700 | 700 | chặn-bán-hàng | Kịch bản riêng 2 cảnh, exact tier, MP4/receipt 0 Xu |
| PV-Q800 | 800 | chặn-bán-hàng | Kịch bản riêng 2 cảnh, exact tier, MP4/receipt 0 Xu |
| PV-Q1000 | 1000 | chặn-bán-hàng | Kịch bản riêng 2 cảnh, exact tier, MP4/receipt 0 Xu |
| PV-Q1200 | 1200 | chặn-bán-hàng | Kịch bản riêng 2 cảnh, exact tier, MP4/receipt 0 Xu |
| PV-Q1500 | 1500 | chặn-bán-hàng | Kịch bản riêng 2 cảnh, exact tier, MP4/receipt 0 Xu |

## Bằng chứng mỗi case

- Scenario/fixture hash riêng.
- REQUEST_ID, project, job, outbox.
- Hai scene output và final MP4 hash/bytes/codec/dimensions/duration.
- Audio stream + mức nghe được nếu yêu cầu audio.
- Add-on requested/materialized/applied.
- Telegram delivery message id.
- `charged_xu=0`, transaction delta 0, không duplicate.
