# NEXT TASK OPTIONS - STABLE REVENUE BOT ONLY

Chưa quay lại kế hoạch lớn TOAN AAS.
Chưa làm app ngoài.
Chưa làm dashboard web.
Chưa làm ERP/Device Ops/SaaS.

Sau Step 9 Sales Hardening + Beta Offer, admin chọn 1 task:

## Option A - PayOS Real Payment Manual Test

- Test gói 10k thật.
- Nếu PASS, chạy `/mark_payos_test pass order=<order_code> note="Test 10k OK"`.
- Không sửa code nếu không phát hiện lỗi rõ.

## Option B - First Customer Beta Launch

- Chọn 3-10 user đầu tiên.
- Cho chạy `/beta_offer`, `/naptien`, `/film`, `/publish_done`, `/performance_add`, `/growth_ai`.
- Ghi feedback thật.

## Option C - Sales Page Copy Polish

- Chỉnh nội dung landing để bán thử beta.
- Không show tên provider/công cụ bí mật.
- Không đổi PayOS/billing.

## Option D - Video Script Lite Templates

- Cải thiện `/film` output.
- Thêm template niche: affiliate, giáo dục, review, story.
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

Codex không tự làm task tiếp theo.
