# Content Platform Risk Backlog - TOAN AAS

## Current Scope

TOAN AAS hiện chỉ tạo nội dung/video/prompt/caption để khách tự đăng.

## Not Supported For Customers Yet

- Auto publish
- Customer affiliate vault
- Customer social account connection
- Ads management
- Running ads with customer payment cards
- Taking control of customer pages/accounts

## Why

Facebook, TikTok, YouTube và các nền tảng quảng cáo kiểm duyệt rất gắt. Nếu nội dung hoặc quảng cáo sai chính sách có thể gây:

- Không duyệt bài
- Hạn chế phân phối
- Khóa tài khoản
- Khóa page/kênh
- Mất tiền quảng cáo
- Rủi ro pháp lý/thương hiệu

## Future Paid Module

Sau này nếu mở dịch vụ Ads/Publish Management cần có:

- Danh sách từ cấm/từ hạn chế theo nền tảng
- Bộ lọc claim quá đà
- Bộ lọc y tế/tài chính/pháp lý/giảm cân/kiếm tiền nhanh
- Kiểm tra nội dung trước khi đăng
- Duyệt thủ công
- Hợp đồng/phạm vi trách nhiệm
- Khách tự giữ thẻ thanh toán trong tài khoản ads của họ
- TOAN AAS chỉ nhận quyền được ủy quyền
- Phí dịch vụ riêng

## Admin-First Publish Rule

Publish Workflow không thuộc scope khách hàng hiện tại. Tính năng này chỉ được thiết kế/test trong admin hoặc TOAN AAS Lab trước.

Rollout tương lai:

1. Generate content pack.
2. Run platform risk checker.
3. Create publish draft.
4. Admin review.
5. Admin approve.
6. Upload/post to admin-owned platform account.
7. Save published URL.
8. Track manual performance.
9. Feed result into `growth_ai`.

Admin phải tự test trước với page/account/channel thuộc admin:

- account connection
- permission scope
- upload flow
- caption/hashtag formatting
- thumbnail handling
- platform policy/risk warning
- approval gate
- audit log
- failure handling
- rollback/manual note

Required feature flags:

- `publish_workflow = 0`
- `admin_publish = 0` until explicit admin approval
- `customer_publish = 0`
- `auto_publish = 0`
- `ads_assistant = 0`

Customer rules if opened later:

- Customer must explicitly connect account or grant permission.
- No password collection.
- No payment card collection.
- No posting without approval.
- No auto publish by default.
- Every post must have approval status and audit log.
- Failed publish must not retry endlessly.
- Customer can revoke access.
- Admin can disable `customer_publish` anytime.

Future admin modules:

- Admin Publish Queue
- Admin Review Gate
- Admin Platform Account Manager
- Admin Risk Checker
- Admin Upload Test Panel
- Admin Publish Logs
- Admin Failure/Retry Panel

## Future Restricted Keyword Database

TODO:

- `blocked_words`
- `restricted_claims`
- `sensitive_categories`
- `platform_policy_notes`
- `manual_review_required`

Sensitive categories:

- Y tế/sức khỏe
- Giảm cân
- Tài chính/đầu tư
- Làm giàu nhanh
- Cờ bạc
- Người lớn
- Thuốc/supplement
- Chính trị
- Sản phẩm bị hạn chế
- Cam kết kết quả tuyệt đối
- Before/after claims

## Future Claude Ads Safety Checker

Status: backlog only. Do not expose to current customer bot.

Claude có thể dùng trong tương lai như Ads Safety Checker và Ads Copy Optimizer cho module Ads admin-first.

Future flow:

1. Bot generates video script/caption/CTA.
2. Claude checks risky words, restricted claims, exaggerated promises, sensitive categories and platform policy risks.
3. Bot returns risk level: `SAFE`, `NEEDS_REWRITE`, or `HIGH_RISK`.
4. Bot suggests safer alternative copy.
5. Admin reviews.
6. Admin approves before posting or running ads.

Possible future admin commands:

- `/ads_check <caption>`
- `/ads_rewrite <caption>`
- `/ads_score <caption>`
- `/ads_pack topic="..."`
- `/ads_risk_report`

Rules:

- Ads Assistant is admin-first.
- Customer ads automation remains OFF by default.
- No automatic ad launch.
- No password collection.
- No payment card collection.
- No guarantee of platform approval or revenue.
- Customer-facing ads service can be opened later only if admin approves pricing, workflow and responsibility rules.
