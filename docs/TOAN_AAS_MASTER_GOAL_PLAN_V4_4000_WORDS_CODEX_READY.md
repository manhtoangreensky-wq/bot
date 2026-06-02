# TOAN AAS — MASTER GOAL PLAN V4.1 CURRENT
## Bản chi tiết trên 4.000 từ · Codex Goal Ready · Living Document

**Tên hệ sinh thái:** TOAN AAS — AI Automation System  
**Tên bot hiện tại:** TOAN AAS Bot V1 — Stable Revenue Tool Bot  
**Bot Telegram hiện tại:** @toanaasbot  
**Trạng thái kế hoạch:** Đang xây thực tế, ưu tiên bot kiếm tiền trước, không chệch khỏi kế hoạch gốc  
**Chủ sở hữu:** Toàn Nguyễn Mạnh  
**Phiên bản:** V4.1 Current — Codex Goal Ready  
**Mục đích file:** Làm tài liệu mục tiêu chính để Codex, Claude, Gemini hoặc bất kỳ AI Coder nào đọc trước khi code, tránh làm lệch hướng, tránh nhồi tính năng quá sớm, tránh phá bot hiện tại.

---

# 0. Tuyên bố quan trọng cho Codex

Codex phải đọc file này như **GOAL chính** của dự án TOAN AAS hiện tại. Đây không phải tài liệu ý tưởng lan man. Đây là bản điều hướng để đảm bảo quá trình code thực tế không đi lệch khỏi chiến lược lớn. Nếu trong quá trình code phát hiện yêu cầu mới, tính năng mới hoặc sửa đổi nào làm lệch khỏi file này, Codex phải dừng lại, báo rõ rủi ro, hỏi admin trước khi làm tiếp.

Trong giai đoạn hiện tại, **không được biến bot hiện tại thành một hệ thống quá lớn**, không được cố gắng nhồi affiliate vault, auto publish, quảng cáo, dashboard lớn, ERP, Device Ops hoặc SaaS vào `bot.py` hiện tại. Bot hiện tại phải được hoàn thiện như một sản phẩm nhỏ nhưng dùng được thật, bán được thật, có doanh thu thật và có thể vận hành an toàn.

TOAN AAS có kế hoạch lớn, nhưng kế hoạch lớn không được phép phá bot đang chạy tiền. Chúng ta đang xây từ nhỏ đến lớn. Cái nhỏ phải chắc, có móng tốt, có lớp bảo vệ, có backup, có billing rõ, có UX dễ hiểu, có khả năng tạo doanh thu. Sau khi phần nhỏ ổn định, mới mở sang phần lớn bằng bot phụ, branch riêng hoặc project sandbox.

Nếu Codex thấy trong code có bảng, hàm hoặc lệnh liên quan đến affiliate, publish, social channels, campaign, performance, device ops, dashboard, worker queue, CRM, ERP, automation lớn, thì **không được tự ý public cho khách**. Những thứ đó có thể giữ làm nền tảng nội bộ hoặc backlog, nhưng trong menu khách hàng hiện tại phải ưu tiên tool AI, Video Factory Lite, nạp Xu, pricing, promo, gift và trải nghiệm dùng thử.

---

# 1. Tư duy tổng thể

TOAN AAS được xây theo hướng: **lấy nhỏ nuôi lớn**. Nghĩa là trong ngắn hạn, dự án không cố làm một nền tảng khổng lồ ngay. Trước tiên, bot hiện tại phải chạy ổn định, khách có thể hiểu, có thể nạp Xu, có thể dùng tool AI, có thể tạo script/video pack/caption/prompt để tự đăng, và admin có thể vận hành không bị rối.

Khi bot hiện tại kiếm được tiền, có user thật và có dữ liệu thật, chúng ta mới quay lại kế hoạch lớn. Kế hoạch lớn gồm nhiều phần như Affiliate Vault, Publish Workflow, Platform Risk Checker, Core Backend, Dashboard, Worker System, CRM, Project OS, Device Ops, SaaS/ERP Automation. Nhưng tất cả những phần đó chỉ được mở khi bot hiện tại đạt đủ điều kiện Goal Gate.

Triết lý vận hành:

- Không cần nhanh, cần đúng.
- Không cần nhiều tính năng, cần tính năng tạo tiền và chạy ổn.
- Không cần khoe to, cần khách hiểu và trả tiền.
- Không thêm tính năng lớn nếu billing chưa chắc.
- Không mở rộng nếu DB chưa an toàn.
- Không auto publish nếu chưa có approval gate.
- Không nhận quyền tài khoản khách khi chưa có quy trình bảo mật.
- Không chạy quảng cáo hộ khách nếu chưa có hợp đồng, checklist, fee riêng và risk checker.
- Không để AI Coder tự ý sửa sâu vào PayOS, callback, DB hoặc billing nếu không có yêu cầu rõ.

Mọi việc phải đi theo nguyên tắc:

```text
Current bot first → stable revenue → real users → real payment → clean data → then big plan.
```

---

# 2. Định vị sản phẩm hiện tại

TOAN AAS Bot V1 hiện tại là một **bot AI tạo nội dung/video/prompt/caption/voice/media và nạp Xu tự động**, giúp khách tạo sản phẩm nội dung nhanh hơn để tự đăng lên Facebook, TikTok, YouTube.

Bot hiện tại không phải:

- Agency chạy quảng cáo.
- Công cụ auto publish công khai cho khách.
- Công cụ giữ tài khoản mạng xã hội của khách.
- Công cụ giữ thẻ thanh toán của khách.
- Công cụ cam kết doanh thu.
- ERP hoàn chỉnh.
- Dashboard doanh nghiệp lớn.
- Hệ thống quản trị social account đầy đủ.

Bot hiện tại là:

- Cổng Telegram để dùng AI nhanh.
- Tool tạo nội dung/video lite.
- Hệ thống Xu để thanh toán dịch vụ AI.
- PayOS/manual QR để nạp tiền.
- Nơi khách trải nghiệm công cụ.
- Sản phẩm đầu tiên để tạo dòng tiền cho TOAN AAS.

Định vị customer-facing nên ngắn gọn:

```text
TOAN AAS giúp bạn tạo script, prompt, caption, hashtag, CTA, voice và content pack cho Facebook, TikTok, YouTube. Bạn tự đăng lên nền tảng của mình. Bot hỗ trợ nạp Xu và dùng công cụ AI ngay trong Telegram.
```

---

# 3. Giai đoạn hiện tại — Stable Revenue Bot

Tên giai đoạn:

```text
TOAN AAS Bot V1 — Stable Revenue Tool Bot
```

Mục tiêu giai đoạn này:

1. Bot chạy ổn định.
2. Không mất database.
3. PayOS Dynamic QR hoạt động hoặc manual fallback rõ ràng.
4. Nội dung chuyển khoản dùng AAS, không còn DAAS trong phần thanh toán customer-facing.
5. User mới nhận 200 Xu trải nghiệm.
6. Pricing rõ ràng, không gây hiểu nhầm.
7. Launch Bonus theo gói rõ ràng.
8. Promo code rõ ràng.
9. Gift code rõ ràng.
10. Menu Telegram sạch, dễ hiểu, không quá dài.
11. Website đúng thương hiệu TOAN AAS, đúng bot @toanaasbot.
12. Video Factory Lite hoạt động.
13. /film, /growth_ai, /campaign_report hoạt động.
14. Không public affiliate vault.
15. Không public auto publish.
16. Không public ads management.
17. Có backup DB.
18. Có /providers, /sales_ready, /backup_db để admin kiểm tra nhanh.
19. Có Git clean, py_compile pass trước khi deploy.
20. Có ít nhất 1 giao dịch nạp thật hoặc manual fallback xác nhận trước khi bán rộng.

Giai đoạn hiện tại không làm:

- App riêng bên ngoài.
- Dashboard lớn.
- ERP full.
- Device Ops full.
- CRM full.
- Worker system lớn.
- Affiliate Vault public.
- Publish Workflow public.
- Ads Assistant public.
- Auto social login hoặc social account connection cho khách.

---

# 4. Các module chính trong bot hiện tại

## 4.1 AI Tools hằng ngày

Mục tiêu: khách vào bot có thể dùng AI cho các việc phổ biến.

Bao gồm:

- Chat AI thường.
- Chat AI Pro/Deep nếu bật.
- Viết kịch bản.
- Viết caption.
- Viết bài bán hàng.
- Viết code hoặc ý tưởng code.
- Lập kế hoạch.
- Tạo ý tưởng nội dung.
- Phân tích hook/caption/CTA.
- Tối ưu nội dung cho Facebook/TikTok/YouTube.

Nguyên tắc:

- Chat thường có thể miễn phí theo giới hạn/ngày nếu còn quota.
- Chat Pro/Deep tính phí theo mức thông minh và độ dài nếu đã bật.
- Không bắt khách hiểu token.
- Khách chỉ cần hiểu: bản thường miễn phí/giới hạn, bản chuyên sâu tính Xu.

## 4.2 Video Factory Lite

Đây là module kiếm tiền trọng tâm trong bot hiện tại.

Mục tiêu:

- Tạo ý tưởng video.
- Tạo script.
- Tạo storyboard.
- Tạo scene prompt.
- Tạo caption.
- Tạo hashtag.
- Tạo CTA.
- Tạo content pack riêng cho Facebook, TikTok, YouTube.
- Khách tự đăng.

Câu chữ customer-facing:

```text
TOAN AAS tạo nội dung/video pack để bạn tự đăng. Hệ thống hiện chưa tự đăng bài, chưa quản lý tài khoản mạng xã hội và chưa chạy quảng cáo hộ khách.
```

Không được ghi trong menu khách:

- Kho affiliate.
- affiliate_id.
- Lưu link affiliate.
- Auto publish.
- Chạy quảng cáo hộ.
- Kết nối tài khoản Facebook/TikTok/YouTube của khách.

Nếu khách muốn thêm link sản phẩm, chỉ cho phép họ dán link trực tiếp trong prompt hoặc tin nhắn, ví dụ:

```text
/film topic="review sản phẩm A" link="https://..."
```

Bot chỉ dùng link đó để viết nội dung tham khảo, không lưu thành kho affiliate chính thức trong public flow.

## 4.3 Audio / Voice / STT

Mục tiêu:

- Bóc băng âm thanh/video thành văn bản nếu provider sẵn sàng.
- Tạo voice-off tiếng Việt.
- Dùng Edge TTS fallback.
- Dùng Fish Audio nếu configured.
- Tính phí theo MB hoặc block nếu đã có pricing engine.

Nguyên tắc:

- Nếu provider lỗi, báo rõ và không trừ Xu hoặc hoàn Xu nếu đã trừ.
- Không hứa “nhân bản giọng người thật” nếu chưa có consent.
- Không dùng giọng người thật khi không có quyền.

## 4.4 Media / Image Tools

Mục tiêu:

- RemoveBG.
- Cutout fallback.
- Prompt hình ảnh.
- Xử lý ảnh cơ bản.
- Tải media nếu provider hoạt động.

Nguyên tắc:

- Không hứa tải mọi video mọi nền tảng nếu provider không ổn.
- Không khuyến khích reup vi phạm bản quyền.
- Nếu tải video có watermark/copyright, cần cảnh báo user tự chịu trách nhiệm.

## 4.5 Billing / Xu

Đây là lõi sống còn.

Mục tiêu:

- User nạp Xu dễ hiểu.
- PayOS Dynamic QR tạo checkout link được.
- Nếu PayOS lỗi, manual QR fallback rõ ràng.
- Admin có thể duyệt bill thủ công.
- Không cộng Xu trùng.
- Không mất order.
- Không log secret.
- Không lẫn DAAS/AAS trong nội dung thanh toán.

---

# 5. Chính sách Xu, gói nạp, Launch Bonus

Chính sách hiện tại phải đồng bộ trong code, docs, menu và website.

## 5.1 Trial

User mới:

```text
Trial = 200 Xu
```

Trial dùng để khách trải nghiệm thật. Mục tiêu không phải cho dùng mãi, mà là đủ để khách thấy giá trị và có động lực nạp.

## 5.2 Gói nạp gốc

Quy ước:

```text
1 Xu = 100đ
```

Gói nạp gốc:

| Gói | Tiền | Xu gốc |
|---|---:|---:|
| Dùng thử | 10.000đ | 100 Xu |
| Nhỏ | 20.000đ | 200 Xu |
| Trung | 50.000đ | 500 Xu |
| Tiêu chuẩn | 100.000đ | 1.000 Xu |
| Nâng cao | 200.000đ | 2.000 Xu |
| Doanh nghiệp | 500.000đ | 5.000 Xu |

## 5.3 Launch Bonus theo gói

Launch Bonus không phải tặng mãi mãi mỗi lần mua. Launch Bonus là ưu đãi theo từng gói, **mỗi tài khoản chỉ nhận một lần cho mỗi gói đủ điều kiện**.

| Gói | Xu gốc | Launch Bonus lần đầu mua gói | Tổng lần đầu mua gói | Mua lại cùng gói |
|---|---:|---:|---:|---:|
| 50k | 500 | +30 | 530 | 500 |
| 100k | 1.000 | +50 | 1.050 | 1.000 |
| 200k | 2.000 | +150 | 2.150 | 2.000 |
| 500k | 5.000 | +500 | 5.500 | 5.000 |

10k và 20k không có Launch Bonus. Đây là gói thử nghiệm.

Nguyên tắc kỹ thuật:

- Phải có tracking `launch_bonus_redemptions` hoặc cơ chế tương đương để mỗi user chỉ nhận Launch Bonus một lần cho từng gói.
- Không cộng Launch Bonus trước khi thanh toán thành công.
- Nếu duplicate webhook/checkpayos, không cộng lại.
- Manual fallback cũng phải dùng cùng số Xu order đã tính.
- Manual approval cũng phải ghi nhận Launch Bonus đã dùng nếu order đó có Launch Bonus.

---

# 6. Promo code và Gift code

## 6.1 Promo code nạp tiền

Promo code nạp tiền chỉ cộng bonus Xu sau khi PayOS/manual payment thành công.

Không giảm giá VND. Không giảm số tiền khách chuyển khoản. Không cộng trước khi thanh toán. Không cộng dồn nhiều promo code trong cùng một order.

Các mã chính:

| Code | Ý nghĩa | Điều kiện |
|---|---|---|
| FIRST30 | Nạp lần đầu từ 50k: +30% Xu | User đủ điều kiện, internal cap để kiểm soát chi phí |
| SECOND15 | Nạp lần 2 từ 50k: +15% Xu | Theo policy |
| MONTHLY20 | Ưu đãi tháng từ 100k: +20% Xu | Theo policy |
| WEEKLY10 | Ưu đãi tuần từ 50k: +10% Xu | Theo policy |
| DAILY5 | Ưu đãi ngày từ 50k: +5% Xu | Theo policy |
| BETA50 | Beta/internal giới hạn | Không quảng bá rộng |

Lưu ý quan trọng:

- Customer-facing text không cần ghi “tối đa 1.500 Xu” cho FIRST30.
- Nội bộ có thể giữ `max_bonus_xu=1500` để kiểm soát chi phí.
- Admin có thể thấy cap trong `/promo_list`, nhưng user-facing `/khuyenmai`, `/promo`, `/naptien`, `/pricing` không cần ghi cap.

## 6.2 Gift / Reward Code

Gift code khác promo nạp tiền.

Gift code dùng để:

- Tặng thưởng khách.
- Xin lỗi khi hệ thống lỗi.
- Tặng khách VIP.
- Tặng khách tiềm năng.
- Test hệ thống.
- Giveaway.

Ví dụ:

- BETA5 = +5 Xu.
- BETA10 = +10 Xu.
- BETA20 = +20 Xu.
- BETA100 = +100 Xu.
- BETA200 = +200 Xu.
- BETA500 = +500 Xu.
- BETA1000 = +1000 Xu.
- SORRY100 = +100 Xu.
- VIP500 = +500 Xu.
- TEST20 = +20 Xu.

Gift code:

- Không cần PayOS.
- User nhập mã hợp lệ là cộng Xu ngay.
- Phải có usage_limit.
- Phải có per_user_limit.
- Phải ghi credit_event/audit.
- User thường không được tạo gift code.
- Admin có thể tạo/tắt/list mã.

---

# 7. PayOS và manual fallback

PayOS là cổng thanh toán tự động chính. Manual QR là dự phòng.

## 7.1 PayOS Dynamic QR

Yêu cầu:

- Tạo checkout link được.
- Signature đúng.
- Payload đúng.
- Không log secret.
- Webhook verify checksum.
- Không cộng trùng order.
- Nếu PayOS lỗi, user nhận manual QR fallback.

PayOS create payment cần debug an toàn nếu fail:

- HTTP status.
- PayOS code.
- PayOS message/desc.
- orderCode.
- amount.
- description.
- returnUrl/cancelUrl.
- signature_data string.

Không log:

- PAYOS_API_KEY.
- PAYOS_CHECKSUM_KEY.
- TELEGRAM_TOKEN.

## 7.2 Nội dung thanh toán

Tất cả customer-facing payment content phải dùng:

```text
AAS <user_id> <order_code>
```

Không dùng DAAS trong nội dung chuyển khoản mới.

Nếu còn DAAS trong comment legacy hoặc docs cũ, không nguy hiểm, nhưng user-facing payment text phải đổi sang AAS.

## 7.3 Manual fallback

Manual fallback phải:

- Dùng cùng order_code.
- Dùng cùng amount.
- Dùng cùng Xu đã tính trong order.
- Không tự tính lại từ PAYMENT_PACKAGES cũ.
- Nếu order 50k lần đầu có 530 Xu, manual fallback cũng phải hiện 530 Xu.
- Admin duyệt manual thì phải cộng đúng Xu và ghi Launch Bonus redemption nếu có.

---

# 8. Những thứ không public ở bot hiện tại

Bot hiện tại không public cho khách:

- Affiliate Vault.
- Kho affiliate của khách.
- Lưu link affiliate chính thức.
- Auto publish.
- Đăng bài hộ khách.
- Chạy quảng cáo hộ khách.
- Kết nối tài khoản Facebook/TikTok/YouTube của khách.
- Xin quyền quản trị page/channel/ad account của khách.
- Nhận thẻ thanh toán của khách.
- Quản lý ads campaign cho khách.
- Tự động lên lịch đăng bài cho khách.
- Tự động submit nội dung lên nền tảng.

Lý do:

- Quyền tài khoản mạng xã hội rất nhạy cảm.
- Ads account/payment card rất rủi ro.
- Facebook/TikTok/YouTube kiểm duyệt rất gắt.
- Nếu đăng/chạy quảng cáo sai có thể khóa tài khoản, khóa page, mất tiền, ảnh hưởng pháp lý.
- Cần quy trình riêng, hợp đồng riêng, phí riêng, bảo mật riêng.

Nếu các command cũ còn tồn tại như `/addlink`, `/links`, `/publish_done`, `/postback_setup`, `/affiliate_sale`, `/social_channels`, thì:

- Không hiển thị trong menu khách.
- User thường gọi thì báo đây là tính năng nội bộ/backlog.
- Admin có thể test nội bộ nếu cần.
- Không xóa DB table nếu đã có.

---

# 9. Kế hoạch lớn sau khi bot chính ổn định

Khi bot chính đạt Goal Gate, chúng ta mới mở kế hoạch lớn bằng bot phụ, branch riêng hoặc project sandbox.

## 9.1 Affiliate Vault

Mục tiêu tương lai:

- Mỗi khách có kho link affiliate riêng.
- Lưu link sản phẩm.
- Lưu tên sản phẩm.
- Lưu nền tảng.
- Lưu hoa hồng.
- Lưu ghi chú rủi ro.
- Gắn link vào script/caption theo yêu cầu.
- Không tự đăng nếu chưa có approval.

Điều kiện trước khi làm:

- Có phân quyền user rõ.
- Có DB schema riêng.
- Có consent của khách.
- Có chính sách bảo mật dữ liệu.
- Có export/import.
- Có audit log.
- Có quyền xóa/sửa link của khách.
- Có cảnh báo trách nhiệm nội dung.

## 9.2 Customer Publish Workflow

Mục tiêu tương lai:

- Khách tạo nội dung.
- Bot tạo caption/video pack.
- Bot đưa vào hàng chờ duyệt.
- Khách hoặc admin duyệt.
- Sau đó mới đăng.

Nguyên tắc:

- Không auto publish mặc định.
- Bắt buộc có approval gate.
- Bắt buộc có log.
- Bắt buộc có rollback/manual note.
- Bắt buộc có cảnh báo nền tảng.
- Khách chịu trách nhiệm tài khoản/nội dung/nền tảng của họ.

Phạm vi chính:

- Hỗ trợ khách đăng bài.
- Hỗ trợ lịch đăng.
- Hỗ trợ content pack theo nền tảng.
- Hỗ trợ kiểm tra rủi ro từ ngữ trước khi đăng.
- Không bắt buộc chạy quảng cáo.

## 9.3 Platform Risk Checker

Risk checker cần cho publish và content pack, không chỉ cho quảng cáo.

Mục tiêu:

- Danh sách từ cấm.
- Từ hạn chế.
- Claim bị cấm.
- Nội dung nhạy cảm.
- Risk score theo nền tảng.
- Facebook/TikTok/YouTube/Instagram/Threads.
- Gắn cờ manual review.

Nhóm rủi ro:

- Y tế/sức khỏe.
- Giảm cân.
- Tài chính/đầu tư.
- Làm giàu nhanh.
- Cờ bạc.
- Người lớn.
- Thuốc/supplement.
- Chính trị.
- Sản phẩm bị hạn chế.
- Cam kết kết quả tuyệt đối.
- Before/after claims.
- Nội dung gây hiểu nhầm.
- Nội dung kích động/câu kéo quá đà.

## 9.4 Ads / Quảng cáo — module tùy chọn

Quảng cáo không phải mục tiêu chính ngay sau bot hiện tại.

Ads chỉ là module thử nghiệm tùy chọn sau này, khi:

- Khách thật sự cần.
- TOAN AAS có đủ quy trình.
- Có kiểm duyệt nội dung.
- Có cảnh báo rủi ro.
- Có phân quyền rõ.
- Có phí dịch vụ riêng.
- Có quy định trách nhiệm rõ.

Nếu khách không cần quảng cáo, hệ thống có thể dừng ở Affiliate Vault + Publish Workflow là đủ.

Không làm:

- Không giữ thẻ thanh toán của khách.
- Không yêu cầu khách đưa mật khẩu.
- Không nhận quyền quá rộng nếu chưa có hợp đồng.
- Không cam kết doanh thu.
- Không tự chạy ads khi chưa có approval.

Nguyên tắc:

- Khách tự add thẻ vào tài khoản quảng cáo của họ.
- Nếu TOAN AAS hỗ trợ chạy quảng cáo, chỉ nhận quyền được ủy quyền.
- Có phí riêng.
- Có hợp đồng/phạm vi trách nhiệm riêng.

---

# 10. Core Foundation sau bot ổn định

Sau bot chính ổn định và kế hoạch lớn sandbox được xác nhận, hệ thống có thể tiến tới Core Foundation.

Mục tiêu:

- Tách backend core khỏi Telegram bot.
- Chuyển DB từ SQLite sang PostgreSQL khi cần.
- Xây IAM/role: admin, staff, customer, technician.
- Xây worker queue.
- Xây audit/approval chuẩn.
- Xây dashboard nhẹ.
- Xây CRM lite.
- Chuẩn bị Project OS.

Nguyên tắc:

- Telegram bot vẫn giữ vai trò điều khiển nhanh.
- Backend core là bộ não dài hạn.
- Dashboard không thay thế bot ngay, chỉ bổ sung.
- Nếu web lỗi, bot vẫn vận hành được.

---

# 11. ELV / Device Ops / SaaS sau này

Đây là lợi thế cạnh tranh dài hạn.

TOAN AAS không chỉ là tool content. Về dài hạn, TOAN AAS có thể trở thành AI Automation Operating System cho doanh nghiệp nhỏ và lĩnh vực ELV: camera, âm thanh, ánh sáng, thiết bị điện tử, dự án thi công, bảo trì, bảo hành.

Các module tương lai:

- Project OS.
- CRM.
- Device inventory.
- Installation jobs.
- Maintenance schedule.
- Warranty tracking.
- Technician assignment.
- Quotation.
- Acceptance report PDF.
- Customer evaluation.
- Project risk.
- Dashboard/Client portal.
- SaaS/ERP automation.

Không làm các module này khi bot hiện tại chưa có doanh thu ổn định.

---

# 12. Goal Gate trước khi chuyển kế hoạch lớn

Chỉ chuyển sang kế hoạch lớn khi bot chính đạt các điều kiện:

- `/start` sạch, đúng thương hiệu.
- `/help` sạch, không quảng bá quá tầm.
- `/naptien` hoạt động.
- PayOS Dynamic QR tạo được checkout link hoặc manual fallback rõ ràng.
- Nội dung chuyển khoản dùng AAS, không còn DAAS.
- `/providers` rõ.
- `/backup_db` hoạt động hoặc có kế hoạch backup an toàn.
- `/sales_ready` rõ.
- Trial 200 Xu hoạt động.
- Pricing rõ.
- Launch Bonus rõ.
- Promo code rõ.
- Gift code rõ.
- `/film` hoạt động.
- `/growth_ai` hoạt động.
- `/campaign_report` hoạt động.
- Website link đúng bot @toanaasbot.
- Không còn link Telegram cũ trong customer-facing CTA.
- Không còn public text “kho affiliate”.
- Không còn public text “auto publish/chạy quảng cáo hộ”.
- `python -m py_compile bot.py` PASS.
- Git clean.
- Có ít nhất một test nạp tiền thật PayOS hoặc manual fallback được xác nhận.
- Admin hiểu quy trình vận hành khi PayOS lỗi.
- Admin hiểu quy trình cộng Xu thủ công nếu fallback.
- Admin có backup DB trước khi deploy thay đổi lớn.

Nếu chưa đạt Goal Gate, không code kế hoạch lớn vào bot chính.

---

# 13. Deviation Control — kiểm soát lệch hướng

Đây là phần cực kỳ quan trọng. Khi làm thực tế, nếu Codex hoặc AI khác code lệch khỏi kế hoạch, phải sửa ngay. Nếu không sửa, hệ thống sẽ hở nhiều lỗ hổng.

Các dấu hiệu lệch hướng:

1. Codex tự public affiliate vault cho khách.
2. Codex đưa affiliate_id/kho affiliate vào menu khách.
3. Codex bật auto publish mặc định.
4. Codex thêm text chạy quảng cáo hộ khách.
5. Codex yêu cầu khách đưa thẻ thanh toán/mật khẩu.
6. Codex sửa pricing không theo policy hiện tại.
7. Codex đưa Trial về 150 Xu hoặc bảng giá cũ.
8. Codex đổi payment content về DAAS.
9. Codex phá callback `pkg|`.
10. Codex sửa PayOS webhook khi không được yêu cầu.
11. Codex bỏ idempotency chống cộng Xu trùng.
12. Codex log API key/token/secret.
13. Codex DROP TABLE hoặc xóa DB.
14. Codex rewrite toàn bộ bot.py.
15. Codex nhồi Dashboard/ERP/Device Ops vào bot hiện tại.
16. Codex tạo chức năng social account connection public.
17. Codex hứa render video hoàn chỉnh nếu hiện tại chỉ tạo script/prompt.
18. Codex bỏ manual fallback.
19. Codex làm mất /naptien, /film, /providers, /backup_db.
20. Codex tự làm task tiếp theo khi chưa được duyệt.

Khi thấy lệch hướng:

- Dừng task.
- Chạy `git diff`.
- Xác định file/hàm bị lệch.
- Revert phần sai nếu cần.
- Cập nhật CODEX_NEXT_TASK.md để ghi rõ hướng đúng.
- Chạy `python -m py_compile bot.py`.
- Không deploy nếu chưa hiểu rủi ro.

---

# 14. Quy tắc cho Codex khi code

Codex phải làm theo quy trình:

## 14.1 Plan First

Trước khi code, in PLAN gồm:

- File sẽ đọc.
- File sẽ sửa.
- Hàm sẽ sửa.
- Những thứ không được đụng.
- Test sẽ chạy.
- Rủi ro nếu làm sai.

## 14.2 Không được làm

- Không rewrite toàn bộ bot.py.
- Không xóa PayOS.
- Không đổi pricing nếu không có lệnh rõ.
- Không đổi callback pkg|.
- Không đổi callback prov|.
- Không DROP TABLE.
- Không hardcode secret.
- Không log secret.
- Không tự mở kế hoạch lớn.
- Không auto publish.
- Không làm ads public.

## 14.3 Bắt buộc sau code

- Chạy `python -m py_compile bot.py`.
- Nếu có pytest thì chạy `pytest -q`.
- Chạy grep các text cấm nếu task liên quan UI.
- Báo ship report.
- Commit/push nếu admin yêu cầu.

## 14.4 Ship report phải có

- File đã sửa.
- Logic đã thêm.
- Những thứ không đụng.
- Test đã chạy.
- Kết quả py_compile.
- Rủi ro còn lại.
- Commit hash.
- Push result.

---

# 15. Step hiện tại cần làm tiếp

Current priority:

1. Sửa PayOS Dynamic QR hoặc debug rõ lý do fallback.
2. Đổi DAAS → AAS trong nội dung thanh toán customer-facing.
3. Đảm bảo manual fallback dùng đúng Xu đã tính, bao gồm Launch Bonus.
4. Hoàn thiện /naptien text.
5. Hoàn thiện /khuyenmai, /promo, /gift.
6. Dọn menu khách: không affiliate vault, không auto publish, không ads.
7. Đồng bộ website @toanaasbot.
8. Test /providers, /backup_db, /sales_ready.
9. Test /film, /growth_ai, /campaign_report.
10. Test nạp tiền thật hoặc manual fallback.

Sau khi xong:

- Đưa bot vào beta bán thử.
- Thu feedback.
- Fix lỗi nhỏ.
- Đo user, doanh thu, chi phí API, lỗi payment.
- Chưa mở kế hoạch lớn nếu chưa qua Goal Gate.

---

# 16. CODEX_NEXT_TASK nên ghi gì

CODEX_NEXT_TASK.md nên có nội dung:

```text
Current phase: Stable Revenue Bot.
Do not code the big plan into current bot.
Priority:
1. PayOS dynamic QR / manual fallback.
2. AAS payment content.
3. Launch Bonus / Promo / Gift sync.
4. Clean customer menu.
5. Video Factory Lite.
6. Website @toanaasbot.
7. Sales readiness.

Future after Goal Gate:
- Sandbox bot/project for Affiliate Vault.
- Publish Workflow.
- Platform Risk Checker.
- Ads Assistant only as optional module if customer needs it.
- Core Backend / Dashboard / Worker later.
```

---

# 17. Future Admin-First Trend-to-Video-to-Publish Pipeline

## 17.1. Long-term goal

TOAN AAS sẽ hỗ trợ một pipeline admin-first, nơi Admin có thể tìm trend, tạo nội dung video AI, kiểm duyệt output và chỉ publish sau khi duyệt.

Workflow dài hạn:

```text
Trend Finder
→ Trend Scoring
→ Script / Context
→ Scene Prompts
→ AI Video Tasks
→ Voice / TTS
→ Captions / Hashtags / CTA
→ Risk Check
→ Admin Approval
→ Publish Queue
→ Platform Publish
→ Performance Tracking
→ Growth Feedback
```

Current status:

- Đây là workflow tương lai, admin-first.
- Không expose cho khách public trong Stable Revenue Bot hiện tại.
- Bot V1 customer-facing chỉ tạo content/video pack để khách tự đăng.
- Không public auto publish.
- Không public trend-to-post automation.
- Không kết nối tài khoản mạng xã hội của khách.
- Không quản lý ads cho khách.

## 17.2. Original long-term workflow

1. Admin clicks hoặc chạy Trend Finder.
2. Bot tìm trending topics/products/content angles.
3. Bot chấm điểm tiềm năng trend.
4. Bot chọn hoặc gợi ý trend tốt nhất.
5. Bot tạo context, angle, audience, hook và script.
6. Bot tạo video prompts/scenes tự động.
7. Bot tạo AI video assets hoặc video generation tasks.
8. Bot tạo voice-over/TTS.
9. Bot combine hoặc chuẩn bị video package.
10. Bot tạo captions, hashtags, CTA và platform-specific outputs.
11. Bot gửi complete draft package cho Admin.
12. Admin review.
13. Admin approve/reject/request rewrite.
14. Chỉ sau Admin approval hệ thống mới được publish/post lên social platforms.
15. Sau khi post, bot lưu published URL và performance data.
16. Performance feed back vào Growth AI và Trend Finder.

## 17.3. Admin-first rollout

1. Build trong admin/internal interface trước.
2. Test chỉ với admin-owned accounts/pages/channels.
3. Keep customer access disabled.
4. Require admin approval before every post.
5. Keep audit logs for every action.
6. Chỉ mở cho khách sau này nếu Admin approve và pricing/package rõ.

Future admin modules:

- Admin Trend Finder.
- Admin Trend Scoring.
- Admin AI Video Builder.
- Admin Voice Builder.
- Admin Caption/Hashtag/CTA Generator.
- Admin Review Gate.
- Admin Approval Queue.
- Admin Publish Queue.
- Admin Platform Account Manager.
- Admin Publish Logs.
- Admin Performance Tracker.

## 17.4. Feature flags

```text
trend_finder = admin only
ai_video_builder = admin only
publish_workflow = off by default
admin_publish = admin only
customer_publish = off by default
auto_publish = off by default
ads_assistant = off by default
```

Pipeline stages:

```text
trend_scan
→ trend_score
→ angle_select
→ script_generate
→ scene_prompt_generate
→ video_generate_task
→ voice_generate
→ assemble_or_export
→ platform_output_generate
→ risk_check
→ admin_review
→ admin_approve
→ publish_queue
→ publish_execute
→ performance_track
→ growth_ai_feedback
```

## 17.5. Safety rules

- No automatic publishing without approval.
- Every generated video/post must go through approval gate.
- Every publish action must have audit log.
- Every platform account connection must be admin-owned or explicitly authorized.
- No password collection.
- No payment card collection.
- No customer publish access until admin manually enables it later.
- Failed publish must not retry endlessly.
- Risk checker must run before publish.

Ads:

- Ads là optional và separate.
- Publishing organic video là main future workflow.
- Ads Assistant chỉ thêm nếu khách thật sự cần và TOAN AAS có clear rules, fees và permission model.

Important:

- Keep affiliate vault, trend finder, publish workflow và video posting tools as admin/internal modules first.
- Do not expose these to customers in current public bot.
- Only after admin tests successfully can admin decide whether to open it as a paid customer feature.

---

# 18. Kết luận

TOAN AAS không được chệch khỏi kế hoạch ban đầu. Kế hoạch ban đầu là xây một hệ sinh thái lớn, nhưng phải bắt đầu bằng một bot nhỏ, chắc, kiếm được tiền. Nếu làm thực tế mà thấy chệch hướng, phải sửa ngay vì mỗi chỗ lệch có thể mở ra lỗ hổng: lỗ hổng bảo mật, lỗ hổng thanh toán, lỗ hổng dữ liệu, lỗ hổng pháp lý, lỗ hổng vận hành, lỗ hổng niềm tin khách hàng.

Bot hiện tại là móng. Móng phải chắc. Khi móng chắc, TOAN AAS mới có thể mở sang Affiliate Vault, Publish Workflow, Platform Risk Checker, Core Backend, Dashboard, Device Ops và SaaS.

Trong mọi task, Codex phải nhớ:

```text
Không làm lan man.
Không phá bot đang chạy tiền.
Không public tính năng rủi ro.
Không mở rộng khi chưa qua Goal Gate.
Hoàn thiện bot hiện tại trước.
```
