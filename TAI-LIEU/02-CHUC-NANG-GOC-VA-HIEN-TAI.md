# Product Video: chức năng gốc và hiện tại

## Tài liệu giai đoạn trước

Nguồn đối chiếu:

1. `docs/superpowers/specs/2026-08-20-product-video-real-output-design.md`
2. `docs/reports/TOAN_AAS_2H_SYSTEM_AUDIT_20260616.md`
3. `docs/architecture/TOAN_AAS_GATE_CALLBACK_STATE_MAP_20260616.md`

## Đối chiếu

| Chức năng gốc | Hiện tại | Trạng thái |
|---|---|---|
| Video AI Prompt -> Add-on -> tier -> invoice -> confirm -> job | Tail hiện khóa 6 màn Add-on, Review, Quality, Invoice, Confirm, Status | Còn dùng, đã mở rộng |
| Video AI Prompt và Ảnh là hai lane riêng | Public product giữ `video_ai_real`; executor tách `video_ai_prompt` / `video_ai_image` | Còn dùng |
| Add-on giữ theo draft và materialize sau render | Tail/session giữ content, asset, add-on và owner snapshot | Còn dùng |
| Tier Video AI cũ tập trung 300/400 | Video AI Chân thật hiện có 10 tier: 200..1500 theo catalog | Tài liệu cũ không còn đủ |
| Frame dùng renderer riêng | Frame vẫn có 3 quality và pricing/engine riêng | Còn dùng, không được fallback Video AI |
| Long video public guard cũ | `multi_scene_film` có planner/Tail riêng; live output vẫn cần matrix mới | Dùng khác, live pending |

## Chỗ tài liệu cũ không còn đúng

- `docs/reports/TOAN_AAS_2H_SYSTEM_AUDIT_20260616.md:30,40` mô tả chủ yếu tier `300/400`; source hiện có 10 tier công khai cho Video AI Chân thật.
- `tests/test_p0_video_tail_confirm_logo_idea_backstack.py:56` đòi Logo/Summary trước Quality; Owner contract hiện tại là Add-on -> Review -> Quality -> Invoice -> Confirm -> Status.
- `docs/architecture/TOAN_AAS_GATE_CALLBACK_STATE_MAP_20260616.md:33` ghi `longvideo|start` planning-only; route hiện tại của `multi_scene_film` thuộc UIFLOW3/Tail và live output vẫn pending.
- Một số test cũ so tier theo thứ tự số; catalog hiện sắp theo giá/copy, vì vậy contract đúng là đủ đúng tập tier và đúng identity.

## Không có trong tài liệu cũ

- Lane tự nhập phải đi thẳng Tail sau khi provider-free planner dựng đủ cảnh.
- Asset gate fail-closed cho Frame/Storyboard/Self-shot và Video AI Ảnh.
- Service guard từ chối forged/unsupported tier trước state mutation.
- Durable parent snapshot để Back đúng owner sau bot restart.
- Full live matrix 9 lane + 10 tier với artifact/receipt/0 Xu.

## Rác hoặc bất nhất đã thấy

- 11 assertion baseline trong 2 test contract cũ đã fail y hệt trên `origin/main cd4acb8`; chưa sửa trong task này để tránh lan man.
- GitHub CLI local có token hết hiệu lực; chưa tạo label/Issue/Project thật. Tracker trong branch đang là nguồn tiến độ có thể đọc trên GitHub.

## Đối chiếu Public Landing — Motion 26/08/2026

Nguồn ban đầu đã tìm thấy: `index.html` tại base `5a4f942bc0b2e8820a96c5772ddb6372f1648604`; mẫu AI Suite Home/Login và NGOCTINCO chỉ là nguồn kỹ thuật chuyển động, không phải nguồn nội dung.

| Chức năng ban đầu | Hiện tại | Trạng thái |
|---|---|---|
| Hero giới thiệu và CTA Workspace/Telegram | Giữ nguyên URL/copy; semantic content luôn opacity `1`, chỉ settle `8px/360ms` một lần | ✅ Còn dùng |
| Các section nội dung hiện mặc định | Vẫn fail-open; chỉ section dưới fold nhận pending | ✅ Còn dùng |
| Form gửi JSON tới `/lead` | Không đổi endpoint, payload hoặc source authority | ✅ Còn dùng |
| Tablet/mobile/reduced-motion | Nội dung hiện ngay, không presentation motion | ✅ Đã khóa bằng test |
| Landing tĩnh không có parallax | Thêm parallax riêng `.workflow-preview`, desktop-only, tối đa `10px` | ⚠️ Mở rộng presentation |

Chỗ tài liệu cũ không còn đúng: dòng nói GitHub CLI hết hiệu lực đã lỗi thời; ngày 26/08/2026 `gh auth status` xác nhận tài khoản đăng nhập, issue Tester Landing là `#884`. Tài khoản hiện thiếu scope `read:project`, nên chưa gắn issue vào GitHub Projects; tracker issue vẫn là phiên Tester có ID/link.
