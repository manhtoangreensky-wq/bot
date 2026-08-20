---
name: toanaas-system-design-and-open-apis
description: Quy chuẩn thiết kế hệ thống phân tán chịu tải cao (System Design), xây dựng micro-engine độc lập từ số 0 (Build-Your-Own-X) và tích hợp danh mục Public APIs mở (Public APIs / Awesome) cho hệ sinh thái TOAN AAS (Telegram Bot, FastAPI, Railway, Ubuntu VPS Worker, SQLite WAL).
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

4. **Đồng bộ hóa Trạng thái & Heartbeat Worker (Generation Fencing)**:
   - Worker chạy trên VPS kết nối về Railway thông qua API trung gian (`/api/v1/worker/claim`, `/internal/worker/heartbeat`).
   - Phải kiểm tra khớp `git commit SHA` và quản lý `generation_id` để ngăn ngừa tình trạng Split-Brain và xung đột phiên bản worker cũ.

5. **Concurrency & Database Scaling (SQLite WAL Mode)**:
   - Sử dụng `PRAGMA journal_mode=WAL` và `PRAGMA busy_timeout=30000`.
   - Tách biệt luồng đọc nhanh và ghi có lock, đảm bảo chịu tải cao và phục hồi an toàn khi restart container.

---

## 2. KIẾN TRÚC TỰ XÂY DỰNG NATIVE ENGINE (BUILD-YOUR-OWN-X)

1. **Tự chủ công nghệ lõi (No Heavy Black-Box Dependencies)**:
   - Ưu tiên xây dựng các pipeline xử lý media, frame splitter, audio mixer trực tiếp qua `ffmpeg` CLI và Python async native.
   - Không lạm dụng các gói trả phí hay SDK cồng kềnh khi có thể tự lập trình logic gọn nhẹ, minh bạch.

2. **Event-Sourcing & Traceability**:
   - Mọi bước chuyển dịch trạng thái (`REQUEST_RECEIVED` -> `PRECHECK_PASSED` -> `JOB_CREATED` -> `PROVIDER_SUBMITTED` -> `ARTIFACT_READY` -> `CHARGED`) đều được lưu trữ dạng event log trong `video_request_traces`.

---

## 3. TÍCH HỢP PUBLIC APIS MỞ (OPEN APIS INTEGRATION)

1. **Danh mục API miễn phí**:
   - Sử dụng danh mục trong `references/PUBLIC_APIS_CATALOG.md` để bổ sung tính năng tiện ích không tốn chi phí (tra cứu tỷ giá, dịch thuật mở, OCR, TTS/STT mở, dự báo thời tiết, tiện ích lập trình).
2. **Circuit Breaker & Fallback**:
   - Mọi kết nối API công khai bên ngoài phải có timeout nghiêm ngặt (dưới 8s), cơ chế bắt lỗi và fallback thông minh để không làm gián đoạn trải nghiệm của bot chính.

---

## 4. TÀI LIỆU THAM CHIẾU KÈM THEO

- [Danh mục Public APIs mở (PUBLIC_APIS_CATALOG.md)](references/PUBLIC_APIS_CATALOG.md)
- [Mẫu thiết kế hệ thống TOAN AAS (SYSTEM_DESIGN_PATTERNS.md)](references/SYSTEM_DESIGN_PATTERNS.md)
- [Hướng dẫn xây dựng Micro-Engine nội bộ (BUILD_YOUR_OWN_ENGINES.md)](references/BUILD_YOUR_OWN_ENGINES.md)
