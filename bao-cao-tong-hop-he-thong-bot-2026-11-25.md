# Báo cáo tổng hợp — Review hệ thống bot (toanaas-bot)

**Ngày:** 2026-11-25 01:05 +07
**Phạm vi:** chỉ đọc + chạy test local. KHÔNG test live, KHÔNG gọi provider, KHÔNG sửa code trong báo cáo này.
**Base:** bot main `838ba49` (merged PR #1468). Checkout local đọc code ở HEAD `1c5fd69` (không có git history đầy đủ) — số dòng `file:line` có thể lệch vài dòng so với main.

## Schema chuẩn

- TASK= system-review bot (bugs + test local + audit bảo mật + phân loại toàn bộ lỗi test)
- BASE_SHA= 838ba49
- HEAD_SHA= 838ba49 (main; fix batch nằm ở PR #1469 chưa merge, head `ab4c879`)
- FILES_CHANGED= 0 (báo cáo này không sửa code)
- TESTS= canonical 225 passed / 2 failed (artifact) · full suite rerun 1.205 failed / 9.872 passed (622 file)
- BASELINE_FAILURES= 1.205 (rerun 1–9) + 946 (chunk 1+3 đợt đầu)
- BRANCH_FAILURES= n/a (không có branch code trong báo cáo này)
- NEW_FAILURES= 0
- PROTECTED_COMPARATORS= không chạy (không sửa code)
- PROVIDER_CALLS= 0
- WALLET_MUTATIONS= 0
- DEPLOY= chưa (PR #1469 đang chờ Owner phê duyệt merge/deploy)
- RUNTIME_SHA= n/a (chưa deploy gì mới)
- LIVE_PASS= NO — #1460 vẫn chờ Owner chạy smoke gate bằng tay trên Telegram thật
- BLOCKERS= quyết định merge/deploy PR #1469; xác nhận giá catalog; quyết định mở lane SubDub; smoke gate #1460

## 1. Kết quả tổng quan

| Hạng mục | Kết quả |
|---|---|
| Compile tĩnh (bot.py, local_worker.py, services, providers, config, tests) | PASS |
| Canonical suite (4 file, guard provider-free) | **225 passed / 2 failed** — 2 lỗi là artifact checkout (git-diff), 0 lỗi thật |
| Full suite đợt đầu (5 chunk ~209 file) | chunk 1: 633 fail / 2.397 pass · chunk 3: 313 fail / 3.932 pass · chunk 2: lỗi collection (1 file gọi `git show 526dfac3:bot.py`) · chunk 4+5: OOM-kill (giới hạn 6 GB RAM) |
| Full suite rerun (9 nhóm ~70 file, 622 file) | **1.205 failed / 9.872 passed** (xem bảng dưới) |
| Audit bảo mật (chỉ đọc) | 0 CRITICAL · 3 HIGH · 4 MEDIUM · 7 LOW |
| Fix batch (PR #1469) | 17 sửa / 2 không sửa có lý do / 1 test cũ · CI xanh 2/2 · chưa merge, chưa deploy |

### Rerun 1–9 (đã chạy lại toàn bộ sau OOM)

| Rerun | Failed | Passed | Ghi chú |
|---|---|---|---|
| 1 | 221 | 830 | 63 skipped |
| 2 | 105 | 1.148 | 34m37s |
| 3 | 97 | 1.209 | 1 test chạy 2.457s làm log đứng ~40 phút |
| 4 | 74 | 767 | 17 skipped |
| 5 | 99 | 1.127 | 1 skipped |
| 6 | 170 | 1.056 | 1 skipped |
| 7 | 248 | 2.353 | 7 skipped |
| 8 | 29 | 795 | +331 subtests passed |
| 9 | 162 | 587 | +32 subtests passed · bị restart giết ở ~6%, chạy lại sạch nhờ marker .done |
| **Tổng** | **1.205** | **9.872** | 622 file |

Lưu ý quan trọng: **CI (ci-main.yml) chỉ chạy một số file test được chọn, không chạy full suite — CI xanh không có nghĩa full suite xanh.**

## 2. Phân loại toàn bộ lỗi test — 2.151 lỗi

Đã phân loại hết, đối chiếu chéo, **0 lỗi trùng nhau giữa các đợt** (mỗi đợt chạy file khác nhau).

| Đợt | Tổng | TEST CŨ | ARTIFACT | LANE KHÓA SubDub | CẦN ĐIỀU TRA |
|---|---|---|---|---|---|
| Chunk 1+3 | 946 | ~690 | ~85 | 31 | ~135 |
| Rerun 1+2 | 326 | 193 | 54 | 38 | 41 |
| Rerun 3 | 97 | 45 | 48 | 1 | 3 |
| Rerun 4 | 74 | 64 | 7 | 0 | 3 |
| Rerun 5 | 99 | 73 | 13 | 0 | 13 |
| Rerun 6 | 170 | 99 | 6 | 0 | 65 |
| Rerun 7 | 248 | 116 | 126 | 0 | 6 |
| Rerun 8 | 29 | 20 | 7 | 0 | 2 |
| Rerun 9 | 162 | 146 | 1 | 0 | 15 |
| **Tổng** | **2.151** | **~1.446** | **~347** | **~70** | **~283** |

Dữ liệu chi tiết từng đợt: `phan-loai-loi-test-2026-11-24.md` (+ `triage_mapped.json`, `triage_grouped.json`), `triage_rerun12.md`, `triage_rerun3.md`, `triage_rerun4.md`, `triage_rerun5.md`, `triage_rerun6.md`, `triage_rerun7.md`, `triage_rerun8.md`, `triage_rerun9.md` (+ file `.json` tương ứng).

### Đọc kết quả thế nào

- **TEST CŨ (~67%)** — test khẳng định hành vi cũ đã lỗi thời sau redesign / đổi giá / đổi copy. Không phải bug code đang chạy, nhưng là nợ test lớn: ~1.446 test cần cập nhật hoặc xóa.
- **ARTIFACT (~16%)** — lỗi môi trường, không phải bug: thiếu `cv2` (42 lỗi), git-diff trên checkout không có history, fixture tạo workspace 0755 (chưa theo fix #1460), slice-exec thiếu tên, receipt test thiếu key `full_decode`, thiếu env policy của spend guard. Nhóm này biến mất khi sửa fixture/môi trường.
- **LANE KHÓA SubDub (~3%)** — test của lane đã khóa theo quyết định Owner (2026-10-04). Muốn điều tra các lỗi này phải mở lane trước.
- **CẦN ĐIỀU TRA (~13%, ~283 lỗi)** — nghi bug thật. Sau khi gộp theo root cause, ước tính bug thật khoảng **~40–80**, tập trung ở các họ dưới đây.

## 3. Bug thật đã xác nhận (đã đọc code, không đoán)

### Đã sửa trong fix batch / PR #1469

- H1: `/addlink` tạo redirect active không kiểm soát (defense-in-depth; thực tế đã có admin-gate).
- H2: `refund_charged_credit` không dedupe theo `ref_id` → retry cộng Xu 2 lần.
- H3: webhook fail-open khi `TELEGRAM_WEBHOOK_SECRET` chưa set → trả 503.
- M2: SSRF-via-provider + download audio không cap → fail-closed + cap 250 MB.
- M3: logic autopost nằm trong chuỗi exec → tách thành `services/autopost_engine.py`.
- M4: `_ensure_column` dùng f-string cho SQL identifier → `_safe_sql_identifier`.
- L1: endpoint wallet chấp nhận 1 trong 4 secret → chỉ còn dedicated token (**hệ quả: webapp phải đổi sang dedicated token trước khi deploy, nếu không endpoint wallet trả 401**).
- L2: so sánh token bằng `!=` → `compare_digest`. L3: chmod 0700 (7 chỗ). L4: rate-limit `/linkweb` 5/10 phút. L7: `add_credit` ép int.
- T1: guard `FRAME_VIDEO_REQUIRE_LOCAL_WORKER` bị bỏ qua ở nhánh short-media. T2: nút stop auto-translate luôn hiện. T3: tier video-200 liệt kê addon 0 Xu. T5: worker claim lệch đúng 25.200s (lỗi timezone). T7: progress giả của provider. T8: `trust_env=False` cho HTTPXRequest.

Không sửa có lý do: T4 (copy "kho affiliate" đã là admin-only), L6 (`quote()` đã có sẵn). Test cũ: T6 (mock layer đã chết).

### Mới phát hiện qua phân loại rerun (chưa sửa — cần debug run / quyết định Owner trước)

**P0 — chặn delivery/charge/concat multiscene:**
- **Probe-gate** (`services/video_project_queue.py:9131-9145`, 21 lỗi, rerun6): scene chưa probe bị ép `clip_valid=False` dù đã có xác nhận hợp lệ → delivery/progress/charge/concat đều kẹt.

**Đã xác nhận bằng đọc code:**
- **Proxy header injection** (`bot.py:609`, rerun7): check chặn `\r` thật nhưng chỉ chặn chuỗi `\n` theo nghĩa đen → ký tự xuống dòng thật lọt qua, không raise `ValueError`.
- **Trial policy chết** (`bot.py:102853-102855`, 6 lỗi, rerun5): `video_b14_is_trial_quality` luôn `return False`.
- **Admission cloud bỏ qua worker truth** (`queue.py:3621`, 6 lỗi, rerun6): `local_worker_required=False` với candidate cloud → mọi check worker bị skip, confirm `ok=True` dù worker mất kết nối/heartbeat cũ/lease hết hạn.
- **Selfshot2 lock identity/relationship chết** (8 lỗi, rerun6): `preserve_gate` là stub luôn trả OK, `compile_scene_prompts` tính `interaction_labels` nhưng không đưa vào prompt, `select_subjects` không raise khi thiếu stable id.

**Cần debug run trước khi sửa:**
- Summary không cap: 194.371 ký tự vs giới hạn Telegram 4.096 (rerun7).
- Cooldown recovery lệch timezone (rerun8) — cùng họ lỗi T5, cần chốt canonical TZ.
- `sanitize_filename` không tách `\` trên POSIX (rerun8) — ưu tiên thấp, output vẫn an toàn trên Linux.
- Pipeline lồng tiếng SUBTITLE_PLUS_DUB trả `ok=False` dù đủ chain + `no such table: system_settings` (rerun9).
- Cache phụ đề dịch không tái dùng: `set_video_dubbing_pending` xóa `translated_subtitle_ref` vừa set (rerun9, `bot.py:254027`).
- Claim atomic 2 thread → `sqlite3.OperationalError: database is locked` thay vì `duplicate_prevented` (rerun9, `bot.py:3206`).
- Gate-override chết: `gate_overridden_for_product` tính ở `bot.py:247456` nhưng không chỗ nào đọc → core vẫn trả `GATE_BLOCKED_AFTER_INPUT_SAVE` (15 lỗi P0, rerun1+2).
- Frame-preview bypass Xu; video-200 bỏ qua tier; Suno 130 vs 80 Xu; copy leak "Cloud Bot API"; `httpx InvalidURL`.
- R18s4 orchestrator multiclip, sweep/claim/outbox, r18s8 health-promotion, tail9 capability fail-open, freehub thiếu owner-map.

**Giá catalog — cần Owner xác nhận, KHÔNG sửa mù:**
- Video beta 259 vs tên tier 200; basic 221 vs 300; song_full 800 vs 500; tier-400 371 vs 80; tier-300 220 vs 221; AI images 10/20/30/50 vs 50–600; Gemini 3.6 vs 3.7. Xuất hiện lặp lại qua 6 đợt triage.

## 4. Audit bảo mật — tóm tắt

Báo cáo đầy đủ: `bao-cao-bao-mat-bot-2026-11-24.md`. **0 CRITICAL, 3 HIGH** (H1/H2/H3 — đã sửa trong PR #1469), MEDIUM: M1 Xu race (ticket Antigravity riêng, đã duyệt, chờ user chạy trên server), M2/M3/M4 (đã sửa), LOW: L1–L7 (đã sửa trừ L5 không cần sửa, L6 đã có sẵn).

Đã xác minh an toàn: 0 secret hardcode, 0 shell injection, PayOS webhook HMAC fail-closed, internal API auth, path traversal guards.

## 5. Issue #1460 và PR #1469 — trạng thái

- **#1460:** đã fix, PR #1468 merge (`838ba49`), deploy VPS thành công 2026-11-24 18:04 (Deploy Bot to VPS #512, health "ok"), receipt đã post lên #1460 và #1155. **LIVE_ACCEPTED=NO — còn chờ Owner chạy smoke gate bằng tay trên Telegram thật** (video edit hub → "Chỉnh sửa thủ công" → upload MP4 thật <30s/<50MB → phải nhận video đã sửa, Xu=0, không gọi provider).
- **PR #1469** (branch `fix/batch-2026-11-24`, head `ab4c879`, 15 file +1.171/−452): CI xanh 2/2. **Chưa merge, chưa deploy — chờ Owner phê duyệt.** Cảnh báo: webapp phải đổi sang dedicated wallet token trước khi deploy (hệ quả của L1), nếu không endpoint wallet/credit trả 401.

## 6. Quyết định cần Owner

1. **Merge + deploy PR #1469** (hay chỉ merge, chưa deploy)? + webapp đã đổi sang dedicated wallet token chưa?
2. **Giá catalog:** basic 221 hay 300? low 259 hay 200? song_full 800 hay 500? tier-400 371 hay 80? tier-300 220 hay 221? Tên tier có còn khớp giá thu không?
3. **Gate-override:** nối override vào core, hay cập nhật test theo thiết kế locked-public?
4. **Probe-gate:** sửa gate hay cập nhật test theo thiết kế coverage hiện tại?
5. **Trial 200 Xu còn hiệu lực không?** (`video_b14_is_trial_quality` luôn False)
6. **Selfshot2:** lock identity/relationship còn là tính năng yêu cầu không?
7. **Mở lane SubDub** để điều tra các lỗi trong lane khóa?
8. **Chuẩn thời lượng 1 cảnh:** quote 5s vs finalization 8s vs test cũ 6s — mâu thuẫn 3 nơi.
9. **Upload khi lane locked:** giữ (drop) hay nhớ để resume? Lane public subtitle/dub giữ khóa hay mở?
10. **Canonical timezone** cho cooldown recovery / timestamp (họ lỗi T5)?
11. **Smoke gate #1460** trên Telegram thật (Owner tự chạy).
12. **Ticket Antigravity sửa race trừ Xu:** user cung cấp số phiếu `<n>` và chạy trên server (đã duyệt 2026-11-24 20:41).

## 7. Khuyến nghị

1. **Merge + deploy PR #1469 trước** (sau khi webapp đổi token) — 17 bug + 3 HIGH bảo mật đã fix, CI xanh, càng để lâu càng lệch với main.
2. **Chốt giá catalog (mục 2 ở trên)** — đây là họ lỗi lặp lại nhiều nhất qua mọi đợt triage; không chốt thì mọi test giá tiếp tục đỏ và không phân biệt được bug thật.
3. **Debug run rồi sửa nhóm P0:** probe-gate (21 lỗi), gate-override (15 lỗi P0), proxy header injection, summary cap.
4. **Dọn ARTIFACT fixture:** workspace 0755 → 0700 trong fixture (48 lỗi rerun7), slice-exec thiếu tên (59 lỗi), receipt thiếu `full_decode` (16 lỗi), cài `opencv-python-headless` (42 lỗi) — nhóm này không phải bug code nhưng đang che mất tín hiệu test.
5. **Dọn TEST CŨ theo đợt:** ~1.446 test — cập nhật theo thiết kế hiện tại hoặc xóa nếu tính năng đã bỏ; làm sau khi chốt giá và các quyết định ở mục 6.
6. **Giữ nguyên tắc:** không test live, không gọi provider; mọi sửa bug mới đều qua PR + CI + Owner duyệt merge/deploy như quy trình đã dùng cho #1468/#1469.

## Phụ lục — file tham chiếu

- Audit: `~/workspace/bao-cao-bao-mat-bot-2026-11-24.md`
- Phân loại chunk 1+3: `~/workspace/phan-loai-loi-test-2026-11-24.md`, `triage_mapped.json`, `triage_grouped.json`
- Phân loại rerun: `~/workspace/triage_rerun12.md`, `triage_rerun3.md`, `triage_rerun4.md`, `triage_rerun5.md`, `triage_rerun6.md`, `triage_rerun7.md`, `triage_rerun8.md`, `triage_rerun9.md` (+ `.json`)
- Fix batch: `~/workspace/repos/bot-fix/BAO-CAO-FIX-BATCH-2026-11-24.md` · PR #1469 https://github.com/manhtoangreensky-wq/bot/pull/1469
- Receipt #1460: `~/workspace/issue1460_receipt_and_smoke_gate.md`
- Ticket Xu race: `~/workspace/phieu-antigravity-wallet-debit-race.md`
