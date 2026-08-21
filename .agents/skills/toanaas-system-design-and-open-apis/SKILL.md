---
name: toanaas-system-design-and-open-apis
description: Quy chuẩn thiết kế hệ thống phân tán chịu tải cao (System Design), xây dựng micro-engine độc lập từ số 0 (Build-Your-Own-X) và tích hợp danh mục Public APIs mở (Public APIs / Awesome) cho hệ sinh thái TOAN AAS (Telegram Bot, FastAPI, Ubuntu VPS Worker, SQLite WAL).
license: Apache-2.0
metadata:
  version: v2.0
  author: TOAN AAS Core Team
---

# TOAN AAS System Design, Native Engines & Open APIs Integration Skill

Áp dụng cho toàn bộ kiến trúc hạ tầng và các module dịch vụ trong hệ sinh thái **TOAN AAS**.

---

## 1. NGUYÊN TẮC THIẾT KẾ HỆ THỐNG PHÂN TÁN (SYSTEM DESIGN INVARIANTS)

1. **Phân tách định danh 3 tầng (Three-Tier ID Separation)**:
   - `REQUEST_ID`: Mã yêu cầu công khai, bền vững của khách hàng (`VID-YYYYMMDD-XXXXXX`). Phải được ghi nhận vào cơ sở dữ liệu trước mọi bước kiểm tra preflight.
   - `JOB_ID`: Mã tác vụ hàng đợi nội bộ (`video_jobs.id`), chỉ tạo ra khi vượt qua cổng Admission Pass.
   - `PROVIDER_TASK_ID`: Mã tham chiếu từ nhà cung cấp bên ngoài (ShopAIKey, Key4U, v.v.).

2. **Idempotency (Tính bất biến khi gọi lại)**:
   - Mọi thao tác xác nhận (`Confirm`), gửi task, trừ tiền (`Charge`), và nhận kết quả webhook đều phải có cơ chế Deduplication dựa trên `REQUEST_ID` / `order_code`.
   - Bấm trùng lặp nhiều lần chỉ sinh ra đúng 1 Job và trừ tiền đúng 1 lần duy nhất sau khi giao hàng thành công.

3. **Cơ chế khóa cổng an toàn (Fail-Closed Admission & Zero-Cost Stop)**:
   - Nếu preflight/readiness không đạt, hệ thống dừng ngay lập tức tại bước kiểm tra nội bộ (`ADMISSION_BLOCKED`), hiển thị mã yêu cầu thật và trạng thái thật.
   - Tuyệt đối không gửi request sang Provider trả phí trong quá trình kiểm thử hoặc khi chưa có sự chấp thuận của Owner (`OWNER_PROVIDER_GATE_APPROVED=NO`).

4. **Kiến trúc Triển Khai Thực Tế (VPS-Only Deploy Truth)**:
   - Hệ thống vận hành 100% trên Ubuntu VPS (`tg.toanaas.vn` / `/opt/toanaas/bot`).
   - Pipeline triển khai: `GitHub main` ──► `GitHub Actions CI/CD` ──► `SSH Auto-Deploy to VPS`.
   - Quản lý dịch vụ bằng systemd (`toanaas-bot.service`, `toanaas-web.service`, `nginx.service`).
