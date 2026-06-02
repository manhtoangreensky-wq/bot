# NEXT TASK OPTIONS - STABLE REVENUE BOT ONLY

Chưa quay lại kế hoạch lớn TOAN AAS.
Chưa làm app ngoài.
Chưa làm dashboard web.
Chưa làm ERP/Device Ops/SaaS.

Sau Step 11 Chat AI Tier System, admin chọn 1 task:

## Option A - Promotion/Discount Code System

- Tạo mã giảm giá theo % hoặc tặng Xu.
- Không đổi bảng giá gốc.
- Không đụng PayOS packages nếu chưa cần.

## Option B - PayOS Real Payment Manual Test

- Test gói 10k thật.
- Nếu PASS, chạy `/mark_payos_test pass order=<order_code> note="Test 10k OK"`.
- Không sửa code nếu không phát hiện lỗi rõ.

## Option C - Beta Launch Offer

- Mở bán thử cho 3-10 user.
- Test `/naptien`, `/film`, `/chat_pro`, `/growth_ai`.

## Option D - Video Script template packs

- Cải thiện `/film` output theo niche.
- Không render.

## Option E - AI Caption Variant Generator

- Tạo 5 hook/caption/CTA variants từ bài thắng.
- Có thể dùng dữ liệu `/growth_ai`.
- Không auto publish.

## Option F - Extract config.py safely

- Tách ENV/constants.
- Không đổi behavior.

## Option G - Extract db.py safely

- Tách DB helpers.
- Không đổi schema.

## Option H - Command QA Polish

- Kiểm `/help`, `/menu`, command registry.
- Chỉ sửa text/handler thiếu, không thêm module lớn.

## Future Backlog

- GitHub Copilot dev workflow
- Legal Docs Lite with OpenLaw/OpenLaws
- Legal templates for service contracts and warranty documents

## Optional future task — Trial top-up migration

Nếu admin muốn bù user cũ đã nhận 150 Xu lên 200 Xu:

- Viết migration an toàn.
- Chỉ bù user có `trial_credit_event` cũ.
- Chỉ bù thêm 50 Xu một lần.
- Ghi `credit_event` rõ ràng.
- Admin duyệt trước khi chạy.

Codex không tự làm task tiếp theo.
