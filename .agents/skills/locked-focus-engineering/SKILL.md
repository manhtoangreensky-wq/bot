---
name: locked-focus-engineering
description: Nguyên tắc bất biến về việc sửa đúng trọng tâm 1 lỗi duy nhất, không lan man, khóa chặt mã nguồn các luồng cũ và cô lập phạm vi để triệt tiêu lỗi lây lan. Áp dụng cho toàn bộ các model AI.
license: Apache-2.0
metadata:
  version: v2.0
  author: TOAN AAS Core Team
---

# TOAN AAS Locked-Focus Engineering Invariant

## 1. ĐỌC SKILL TRƯỚC KHI CODE
- Đọc và áp dụng skill này cùng `owner-governed-codex` trước khi can thiệp mã nguồn.
- Xác định chính xác 1 điểm lỗi trọng tâm cần giải quyết.

## 2. SỬA ĐÚNG TRỌNG TÂM (ZERO CODE SPRAWL)
- Người dùng yêu cầu sửa lỗi ở đâu, chỉ sửa ĐÚNG hàm/dòng xử lý trực tiếp lỗi đó.
- CẤM chỉnh sửa lan man sang các hàm khác, module khác hoặc luồng lân cận.
- Không tự ý tái cấu trúc (refactor) ngoài phạm vi yêu cầu.

## 3. SỬA XONG LÀ KHÓA CHẶT (CODE LOCKING & ANTI-REGRESSION)
- Bất kỳ luồng/tính năng nào đã test chạy đúng phải được coi là **ĐÃ KHÓA**.
- Tuyệt đối không chạm vào code của các luồng đã khóa để tránh lỗi hồi quy.

## 4. CÔ LẬP PHẠM VI BẰNG CONDITION BRANCH
- Viết nhánh rẽ cô lập an toàn, tránh sửa vào thân hàm dùng chung (shared logic) nếu chưa có bộ test kiểm chứng đầy đủ.
