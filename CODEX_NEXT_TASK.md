# NEXT TASK OPTIONS - STABLE REVENUE BOT ONLY

Chưa quay lại kế hoạch lớn TOAN AAS.
Chưa làm app ngoài.
Chưa làm dashboard web.
Chưa làm ERP/Device Ops/SaaS.

Sau Step 10 Pricing Engine V2, admin chọn 1 task:

## Option A - Promotion/Discount Code System

- Tạo mã giảm giá theo % hoặc tặng Xu.
- Không đổi bảng giá gốc.
- Không đụng PayOS packages nếu chưa cần.

## Option B - Beta Launch Offer

- Test gói 10k thật.
- Nếu PASS, chạy `/mark_payos_test pass order=<order_code> note="Test 10k OK"`.
- Mở bán thử cho 3-10 user.

## Option C - PayOS Real Payment Manual Test

- Làm đúng `docs/PAYOS_REAL_PAYMENT_TEST.md`.
- Không sửa code nếu không phát hiện lỗi rõ.

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

Codex không tự làm task tiếp theo.
