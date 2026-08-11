# TOAN AAS Pricing Knowledge

Last updated: 2026-08-11

## Runtime Rule

This document is knowledge/backlog. Runtime pricing remains in bot configuration/code until explicitly migrated. Do not import this document as code.

## Xu Conversion

- 1 Xu = 100 VND.
- User is charged only after the final confirmation step.
- Provider failure before valid output must not leave the user charged incorrectly.

## Video Pricing Current Policy

| Tier ID | Gói công khai | Thời lượng | Giá bán |
| ---: | --- | ---: | ---: |
| 200 | Nhanh gọn | 5 giây/cảnh | 200 Xu/cảnh |
| 300 | Tiêu chuẩn có âm thanh | 5 giây/cảnh | 220 Xu/cảnh |
| 400 | Cân bằng rõ nét | 8 giây/cảnh | 80 Xu/cảnh |
| 500 | Chuyển động ổn định | 5 giây/cảnh | 110 Xu/cảnh |
| 600 | Chuyển động có âm thanh | 5 giây/cảnh | 160 Xu/cảnh |
| 700 | Cảnh dài có âm thanh | 15 giây/cảnh | 220 Xu/cảnh |
| 800 | Cao cấp linh hoạt | 10 giây/cảnh | 370 Xu/cảnh |
| 1000 | Diễn xuất chân thật | 6 giây/cảnh | 370 Xu/cảnh |
| 1200 | Đa góc máy | 8 giây/cảnh | 1.260 Xu/cảnh |
| 1500 | Điện ảnh nhiều cảnh | 10 giây/cảnh | 2.360 Xu/cảnh |

Tier ID là mã định tuyến ổn định, không phải giá bán.

## Video Add-on Policy

- Mỗi gói có thời lượng riêng như bảng trên.
- Khuyến mãi chỉ áp dụng cho đơn Video nhiều cảnh: 1 cảnh không giảm; 2–5 cảnh giảm 10%; 6–10 cảnh giảm 15%; 11–20 cảnh giảm 20%.
- Khuyến mãi chỉ giảm phần chi phí Video theo cảnh; add-on tính riêng.
- Items marked with `+` in user-facing pricing are the only items that add Xu.
- Built-in libraries, prompt/script templates and basic manual/local actions can remain free inside their technical limits.

## Provider Cost Rule

- Giá Video lấy chi phí cao nhất giữa provider đủ điều kiện, quy đổi mặc định 3.500 VND/USD, nhân 3 và làm tròn theo chính sách Xu.
- ShopAIKey là tuyến ưu tiên khi đủ điều kiện; Key4U là tuyến dự phòng theo mapping của từng tier.
- Không mở tuyến public khi model/adapter chưa có route readiness và bằng chứng chi phí tương ứng.

## Image Pricing Current Policy

- Low/test image: 50 Xu.
- Standard image: 200 Xu.
- Standard + warranty: 250 Xu.
- High image: 400 Xu.
- High + warranty: 500 Xu.

Warranty means one guarded retry in the same job/context only.
