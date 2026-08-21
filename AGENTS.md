# Owner-Governed Codex & Auto Git/VPS Pipeline Rules (All AI Models)

Áp dụng cho TOÀN BỘ các phiên làm việc và toàn bộ các model AI khi thực hiện nhiệm vụ kỹ thuật trong hệ sinh thái TOAN AAS.

---

## 1. BẮT ĐẦU MỖI TASK (TASK STARTUP DISCIPLINE)

1. Trước khi kiểm tra hoặc chỉnh sửa mã nguồn, bắt buộc đọc và áp dụng các skill cốt lõi:
   - `owner-governed-codex`
   - `locked-focus-engineering`
   - `single-agent-anti-overengineering`
   - `toanaas-system-design-and-open-apis`

2. Ở đầu mỗi báo cáo task, bắt buộc tuyên bố:
   `Đang đọc và áp dụng skill owner-governed-codex cho task này.`

3. Tuân thủ nghiêm ngặt vòng đời 7 bước FSM:
   `READ -> CONTRACT -> BUILD -> REVIEW -> VERIFY -> REPORT -> LEARN`

4. Thực thi chế độ **Single-Agent by Default** + **Anti-Overengineering**:
   - 1 Agent duy nhất làm chủ vòng đời task từ A-Z, cấm tự ý spawn subagent khi chưa thỏa mãn 4 điều kiện ngoại lệ.
   - Sửa đúng trọng tâm, tối thiểu dòng code (`MINIMAL_CODE_FOOTPRINT=ON`), không over-engineer (`YAGNI=ON`), dừng ngay khi test pass (`EARLY_STOP=ON`).
   - Không tự ý tái cấu trúc (refactor) các luồng mã nguồn đã khóa ổn định.

---

## 2. KẾT THÚC MỖI TASK (AUTO-PR, AUTO-PUSH, AUTO-MERGE, AUTO-DEPLOY TO VPS)

Khi hoàn thành chỉnh sửa mã nguồn và vượt qua toàn bộ các bài kiểm thử tự động (`python -m py_compile bot.py`, `pytest`):

1. **Tự động Commit & Push**:
   - `git add <files>`
   - `git commit -m "<semantic message>"`
   - `git push origin <branch>`

2. **Tự động Tạo PR & Merge vào `main`**:
   - Tạo PR qua GitHub CLI: `gh pr create --title "<title>" --body "<summary>"`
   - Tự động Merge vào nhánh `main`: `gh pr merge <pr_number> --squash --admin`

3. **Tự động Theo Dõi & Xác Minh Deploy Lên VPS**:
   - Theo dõi workflow GitHub Actions CI/CD: `gh run watch <run_id>`
   - Kiểm tra trạng thái dịch vụ thực tế trên Ubuntu VPS (`tg.toanaas.vn`) qua SSH:
     `ssh -i C:\Users\toann\.ssh\toanaas_vps_cowork root@tg.toanaas.vn "systemctl status toanaas-bot.service toanaas-web.service nginx.service --no-pager"`

4. **Báo Cáo Bằng Chứng Thực Nghiệm**:
   - Xuất đầy đủ bằng chứng test passed, link PR đã merged và trạng thái Active Running trên VPS.

---

## 3. CÁC CHỐT CHẶN AN TOÀN BẤT BIẾN CỦA OWNER (OWNER SAFETY GATES)

Tuyệt đối KHÔNG tự ý thực hiện khi chưa có lệnh rõ ràng từ Owner:
1. Thay đổi biến môi trường ENV / API Keys / Secrets;
2. Xóa bảng dữ liệu SQLite / User data / Dropping tables;
3. Gọi API bên ngoài có tính phí trong lúc kiểm thử (`PROVIDER_CALLS`);
4. Thay đổi logic ví tiền Xu, nạp rút, PayOS / thanh toán (`WALLET_MUTATIONS`);
5. Tự động thăng cấp bài học thành luật toàn cục (`AUTO_PROMOTION=OFF`).

---

## 4. CHÂN LÝ TRIỂN KHAI VÀ XÁC MINH
- `MERGED != DEPLOYED != LIVE`.
- `HTTP 200 != FINAL OUTPUT SUCCESS`.
- `BUILD != PASS` (Chỉ công nhận PASS khi có output thực tế từ terminal).
- Toàn bộ hệ thống production vận hành trên Ubuntu VPS (`tg.toanaas.vn`), không sử dụng Railway cho runtime hiện tại.
