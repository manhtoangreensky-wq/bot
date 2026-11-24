# BÁO CÁO FIX BATCH BOT — 2026-11-24

Đang đọc và áp dụng skill owner-governed-codex cho task này.

- TASK=fix-batch-bot-2026-11-24
- BASE_SHA=838ba4914ef9bb33730cfdfa9ff271b30399e8d3 (main, sau merge PR #1468)
- HEAD_SHA=(không có — bản copy `bot-fix` không phải git repo; chỉ là working copy)
- FILES_CHANGED=14 (13 sửa + 1 mới) — gồm guard test cập nhật theo quyết định L1 (A) của Owner, xem dưới đây
- TESTS=xem mục Cổng nghiệm thu bên dưới (số thực tế)
- BASELINE_FAILURES=bộ 4 file chuẩn 225 passed / 2 failed (artifact git-diff, xem GATE2); các test khác liệt kê từng cổng
- BRANCH_FAILURES=cùng tập baseline, không thêm failure mới do fix
- NEW_FAILURES=0 (không test nào đang pass bị fix làm hỏng — đã kiểm chứng từng cái)
- PROTECTED_COMPARATORS=`test_local1_no_wallet_business_rule_changes` — **ĐÃ GIẢI QUYẾT theo quyết định A của Owner (2026-11-24 23:52): giữ L1, cập nhật guard test** — guard nay allowlist đúng 1 file `services/admin_wallet_service.py` (ngoại lệ L1 có chủ ý), mọi path "wallet" khác vẫn bị chặn; đã kiểm chứng logic bằng mô phỏng diff (batch 15 file → pass, thêm file wallet lạ → vẫn fail). Ở CI guard sẽ chạy thật (có `.git`) và pass cùng batch này.
- PROVIDER_CALLS=0
- PROVIDER_CALLS=0
- WALLET_MUTATIONS=CÓ — chỉ H2 hoàn Xu trùng (Owner đã duyệt "sửa hết bug" 2026-11-24 22:46). M1 race trừ Xu KHÔNG đụng (phiếu Antigravity riêng)
- DEPLOY=NO, RUNTIME_SHA=n/a, LIVE_PASS=NO (không test live)
- BLOCKERS=xem mục Xin quyết định

## Tổng kết

| Nhóm | Số lượng |
|---|---|
| ĐÃ SỬA | 17 |
| KHÔNG SỬA (có lý do, đúng phiếu) | 2 (T4, L6) |
| TEST CŨ (không phải bug code) | 1 (T6) |
| Tổng trong phạm vi phiếu | 20 |
| KHÔNG LÀM (ngoài phạm vi) | M1 race trừ Xu (Antigravity riêng), giá tier #8/#9 (cần Owner xác nhận), lane SubDub khóa, ~690 test cũ còn lại |

## Chi tiết từng bug

### H1 — Open redirect qua /addlink — ĐÃ SỬA
- **File:** `bot.py:22743` `create_affiliate_link`, `bot.py:23765` `approve_affiliate_link` (mới), `cmd_addlink` admin-gated
- **Mô tả:** audit ghi bất kỳ user Telegram nào cũng tạo được link redirect active trên domain bot qua `/addlink` → `/r/{id}` 302 tới URL tùy ý.
- **Cách sửa:** link do non-admin tạo mặc định `pending` (admin vẫn `active`); thêm hàm `approve_affiliate_link` + lệnh `/affiliate_approve` + handler. Redirect `/r/{id}` vốn đã 404 với link non-active.
- **Lưu ý kiểm chứng:** audit nói quá — `/addlink` vốn đã bọc trong `admin_internal_command` và redirect đã lọc `owner_id=ADMIN_ID`. Fix này là defense-in-depth ở tầng dữ liệu.
- **Test chứng minh:** growth checklist 6 passed; hand-check script 15/15 PASS (đã xóa sau khi chạy).

### H2 — Hoàn Xu trùng khi retry (ref_id không dedupe) — ĐÃ SỬA
- **File:** `bot.py:14968` `refund_charged_credit`
- **Mô tả:** hàm nhận `ref_id` nhưng không bao giờ dedupe theo nó, không `BEGIN IMMEDIATE` → retry hoàn Xu 2 lần.
- **Cách sửa:** `BEGIN IMMEDIATE` + dedupe trên `ref_id` non-empty (cùng user + delta>0 + event loại refund); try/except/finally rollback + close.
- **Test chứng minh:** script proof: retry cùng ref → False; 2 thread cùng ref → đúng 1 True; ref rỗng giữ hành vi cũ. Script đã xóa. Test refund: 5 passed, 1 failed pre-existing (`test_support_ticket_menu_admin_registry_and_no_auto_refund` — fail y hệt trên pristine).

### H3 — Telegram webhook fail-open khi chưa cấu hình secret — ĐÃ SỬA
- **File:** `bot.py:279765`
- **Mô tả:** khi `TELEGRAM_WEBHOOK_SECRET` unset, webhook vẫn xử lý request (fail-open), khác handler PayOS (fail-closed).
- **Cách sửa:** trả 503 `"webhook secret not configured"` khi secret unset; khi đã cấu hình, hành vi không đổi.
- **Test chứng minh:** file webhook 10 passed (1 test guard git-dependent fail dạng artifact, xem GATE3A).

### M2 — SSRF qua provider + download audio không giới hạn — ĐÃ SỬA
- **File:** `bot.py:65881` `_download_audio_url_bytes`, `local_worker.py:1371` `download_url_file`
- **Mô tả:** tải URL do provider/user đưa về không kiểm tra IP đích, không chặn redirect, không cap dung lượng.
- **Cách sửa:** validate `getaddrinfo` + `ipaddress.is_global` fail-closed, chặn redirect, stream + cap 250 MB.
- **Test chứng minh:** các test liên quan pass (xem GATE3C, 132 passed).

### M3 — Tách autopost exec string thành module thật — ĐÃ SỬA
- **File:** `services/autopost_engine.py` (MỚI, 20.609 bytes), `bot.py:41` (import thường), xóa block string + `exec` ở `bot.py:143086` cũ
- **Mô tả:** ~313 dòng logic autopost nằm trong string `autopost_engine_code`, `exec` lúc import (bot.py:143399 cũ) — linter/grep không thấy, không thể kiểm tra tĩnh.
- **Cách sửa:** tạo `services/autopost_engine.py` chứa nguyên văn code + import (3 tên export: `autopost_hub_keyboard`, `autopost_hub_text`, `handle_autopost_callback`); 3 helper định nghĩa trong bot.py (`is_admin_user`, `get_user_language`, `safe_edit_query_message`) được lazy-import trong hàm để tránh circular import. Kiểm chứng bằng diff pristine + 5 patch: khác biệt duy nhất là import (+5 dòng) và block bị xóa (−314 dòng).
- **Test chứng minh:** 2 test ghim thiết kế cũ được viết lại tối thiểu để ghim thiết kế mới (cùng ý định — engine tồn tại / compile / đăng ký): `tests/test_p0_autopost_dynamic_compile.py`, `tests/test_p0_vps_autopost_startup_symbol.py` — 2 passed. Grep sau merge: 0 `autopost_engine_code`, 0 `exec(compile(`.

### M4 — `_ensure_column` latent SQLi (f-string table/column) — ĐÃ SỬA
- **File:** `services/video_editengine1.py:222`, `services/video_idea_store.py:68`, `admin_broadcast.py:201` (bản copy local của `_safe_sql_identifier` — tránh circular import; bản chuẩn đã có ở `bot.py:3399`)
- **Mô tả:** `_ensure_column` nội suy tên bảng/cột vào SQL bằng f-string không validate.
- **Cách sửa:** validate identifier bằng `_safe_sql_identifier` trước khi nội suy. Các caller hiện tại đều truyền literal nên chỉ là latent.
- **Test chứng minh:** các test liên quan pass (xem GATE3C).

### L1 — Wallet/credit endpoint chấp nhận 1 trong 4 secret — ĐÃ SỬA (có rủi ro CI, xem Xin quyết định #1)
- **File:** `bot.py` (check inline) + `services/admin_wallet_service.py:168`
- **Mô tả:** endpoint wallet/credit chấp nhận cả link token cùng với token chuyên dụng.
- **Cách sửa:** chỉ chấp nhận `CORE_BRIDGE_TOKEN` / `INTERNAL_API_SECRET`.
- **Test chứng minh:** các test liên quan pass (GATE3C). **Hậu quả:** webapp caller phải chuyển sang token chuyên dụng trước khi deploy batch này, nếu không endpoint trả 401 (xem Xin quyết định #2).

### L2 — Token `confirm_local` so sánh bằng `!=`, không dùng `compare_digest` — ĐÃ SỬA
- **File:** `bot.py:77868` (token check dùng `hmac.compare_digest`), `bot.py:279778` (webhook token)
- **Cách sửa:** chuyển so sánh token sang `hmac.compare_digest` (chống timing attack).
- **Test chứng minh:** các test liên quan pass (GATE3C).

### L3 — Thư mục job/workspace 0755 — ĐÃ SỬA
- **File:** `bot.py:8885`, `30098`, `30275`, `30332`, `34226`, `34349`, `246742` (7 điểm)
- **Cách sửa:** `os.chmod(..., 0o700)` sau khi tạo thư mục (bọc try/except OSError), cùng chuẩn với fix #1460.
- **Test chứng minh:** py_compile PASS; các test liên quan pass.

### L4 — `/linkweb` không giới hạn số lần thử — ĐÃ SỬA
- **File:** `bot.py:138173-138194`
- **Cách sửa:** rate limit in-memory 5 lần / user / 10 phút, xóa khi thành công.
- **Test chứng minh:** `test_confirm_webapp_telegram_link_success` pass khi chạy với env sạch (xem LỆCH #2 — trong cổng GATE3C nó fail do quirk `no_proxy` của sandbox, không phải do L4).

### L6 — RSS query không encode — KHÔNG CẦN SỬA
- **File:** `bot.py:37518`
- **Lý do:** kiểm chứng lại thấy `quote()` đã được áp sẵn tại đây. Không có gì để sửa.

### L7 — `add_credit` không ép int() — ĐÃ SỬA
- **File:** `bot.py:14930`
- **Cách sửa:** `amount = int(amount or 0)`.
- **Test chứng minh:** các test liên quan pass.

### T1 — `frame_video_runtime_guard` bỏ qua `FRAME_VIDEO_REQUIRE_LOCAL_WORKER` — ĐÃ SỬA
- **File:** `bot.py:180972` `frame_video_runtime_guard`; check ở `181112`, `181122` (nhánh short-media)
- **Cách sửa:** thêm check flag + `DIRECT_RENDER_ENABLED` trong nhánh short-media.
- **Test chứng minh:** 4 test đích re-run độc lập: 4 passed trong 7.03s.

### T2 — Nút stop auto-translate luôn hiện — ĐÃ SỬA
- **File:** `bot.py:126837`, `126845` (nút stop)
- **Cách sửa:** chỉ hiện nút stop khi có translate session đang active; try/except giữ hành vi cũ nếu check lỗi.
- **Test chứng minh:** GATE3B2: 2 passed.
- **Lưu ý:** `test_p0_11::test_language_translation_menu_restored` đã fail TRƯỚC fix (lệch label nav 'Dịch thuật' vs 'Trung tâm'); T2 chỉ thêm 1 diff nữa (thiếu nút stop, đúng kỳ vọng khi không có session). Không test nào đang pass bị T2 làm hỏng.

### T3 — Tier video-200 liệt kê addon 0 Xu — ĐÃ SỬA
- **File:** `bot.py:49744-49764` (`paid_items`)
- **Cách sửa:** lọc item 0 Xu khỏi `paid_items` chỉ ở tier low (tier basic có test dựa vào 1 item 0 Xu nên giữ nguyên ở đó).
- **Test chứng minh:** GATE3B: pass cùng T1 (2 passed).

### T4 — Copy "kho affiliate" trong text admin — KHÔNG SỬA
- **File:** `bot.py:234404`
- **Lý do:** chuỗi chỉ xuất hiện 1 lần, trong `handle_admin_growth_callback`, đã được guard `is_admin_user` ở đầu hàm — là copy admin-only. Test quét source-wide nên báo, nhưng code không sai. Xem Xin quyết định #4.

### T5 — Worker claim không trả job (watchdog fail job tươi ngay lập tức) — ĐÃ SỬA
- **File:** `services/video_project_queue.py:431` `_parse_time_epoch` (naive timestamp parse theo giờ host-local qua `astimezone()`, trước đây parse theo giờ Việt Nam trong khi `now_text()` ghi giờ host-local → trên host UTC mọi tính toán elapsed/lease lệch đúng 25200s = 7h)
- **Cách sửa thêm:** diagnostic creator giờ tạo dispatch outbox; lane-mismatch release không còn tiêu retry; `last_worker_id` được stash trước khi terminal fail (phục vụ canary status).
- **Test chứng minh:** 18d4b 16 passed, 18d4a 17 passed, R6 fixed tests 2 passed (GATE3D: tổng 37 passed).
- **Follow-up chưa làm:** xem Xin quyết định #6.

### T6 — DID NOT RAISE RealVideoRenderError — TEST CŨ
- **Bằng chứng:** các test mock `process_multiscene_video_pipeline` — một layer đã chết; contract hiện tại là return-based polling, không phải raise; không tìm thấy silent local-composer fallback. Không sửa code.
- **Follow-up:** xem Xin quyết định #5.

### T7 — Fake provider progress % (monotonic carry số không đáng tin) — ĐÃ SỬA
- **File:** `services/video_project_queue.py:1342`
- **Cách sửa:** monotonic carry chỉ áp dụng khi progress trước đó đáng tin (`provider_progress_trusted` hoặc có result URL hoặc final output sẵn sàng); trước đây `progress = max(previous_render_progress, progress)` "rửa" số phần trăm không đáng tin thành số đã xác nhận.
- **Test chứng minh:** R6 fixed tests 2 passed (trong GATE3D 37 passed). 6 failure R6 còn lại là TEST CŨ (đã bị R13/r6a/r7a thay thế).

### T8 — `httpx.InvalidURL: Invalid port: ':1]'` — ĐÃ SỬA
- **File:** `bot.py:828-846` (`trust_env=False` trên mọi build `HTTPXRequest`)
- **Nguyên nhân gốc:** `no_proxy` chứa `[::1]` khiến httpx build bypass key không parse được.
- **Test chứng minh:** T8 builders 2 passed (trong GATE3D 37 passed).
- **Follow-up chưa làm:** xem Xin quyết định #7.

## Danh sách file đổi (14 file, so với pristine `~/workspace/repos/bot` — `diff -rq`)

| File | Nhóm |
|---|---|
| `bot.py` (287.315 dòng; pristine 287.391) | H1, H2, H3, M2, M3, M4, L1, L2, L3, L4, L7, T1, T2, T3, T7*, T8 |
| `local_worker.py` | M2 |
| `admin_broadcast.py` | M4 |
| `services/admin_wallet_service.py` | L1 |
| `services/autopost_engine.py` (MỚI) | M3 |
| `services/remote_worker_api.py` | T5/T8 |
| `services/video_editengine1.py` | M4 |
| `services/video_idea_store.py` | M4 |
| `services/video_project_queue.py` | T5, T7 |
| `tests/test_growth_checklist_fix_v1.py` | H1 |
| `tests/test_p0_17c4_webhook_db_html_security_events.py` | H3 |
| `tests/test_p0_autopost_dynamic_compile.py` | M3 (viết lại ghim thiết kế mới) |
| `tests/test_p0_vps_autopost_startup_symbol.py` | M3 (viết lại ghim thiết kế mới) |
| `tests/test_p0_video_local1_manual_editing_smart_splitter.py` | L1 — guard test cập nhật theo quyết định A của Owner (allowlist 1 file `services/admin_wallet_service.py`) |

\* T7 nằm ở `services/video_project_queue.py`; bot.py chỉ chứa cờ hiển thị `progress_monotonic_applied`.

## Quyết định L1 của Owner — (A) giữ L1, cập nhật guard test (2026-11-24 23:52)

- Giữ nguyên fix L1 (wallet/credit endpoint chỉ nhận token ví chuyên dụng).
- Guard test `test_local1_no_wallet_business_rule_changes` (`tests/test_p0_video_local1_manual_editing_smart_splitter.py:861`) được cập nhật tối thiểu: thay `assert "wallet" not in changed` bằng allowlist đúng 1 file `services/admin_wallet_service.py`, kèm comment ghi rõ ngoại lệ L1 có chủ ý theo quyết định A; mọi path "wallet" khác vẫn fail như cũ.
- Kiểm chứng: mô phỏng diff của batch (15 file gồm cả báo cáo này) → guard pass; thêm file wallet lạ → guard vẫn fail; `py_compile` file test OK; bộ 4 file chuẩn chạy lại local vẫn 225 passed / 2 failed (2 guard fail dạng artifact do bản copy không có `.git`, không phải do sửa guard — ở CI có `.git` thật guard sẽ chạy và pass).
- Lưu ý còn mở: webapp caller phải chuyển sang token ví chuyên dụng trước khi deploy batch này, nếu không endpoint wallet/credit trả 401 (xem Xin quyết định #2).

Kiểm chứng: `diff -rq` giữa `bot` và `bot-fix` (loại `.venv`, `__pycache__`, `.pytest_cache`, `.git`) chỉ ra đúng 14 file trên, không file lạ. File `.agents/state/g2-m2-m4-lows.yaml` của nhóm g2 KHÔNG merge (agent state, không phải fix). Mọi script proof/check tay đã xóa sau khi chạy.

## Cổng nghiệm thu (số thực tế)

Môi trường: `TMPDIR=/home/hatch/tmp APP_ENV=test TELEGRAM_TOKEN=test-token DB_FILE=/tmp/pv-catalog.sqlite DB_PATH=/tmp/pv-catalog.sqlite LOCAL_WORKER_JOB_SCOPE=video_edit_only`, venv `~/workspace/repos/bot/.venv/bin/python`. Script `~/workspace/run_fix_gates.sh`, log `/home/hatch/tmp/fix_gates.log`.

### GATE1 — py_compile: PASS
`python -m py_compile bot.py local_worker.py services/*.py` → `COMPILE_OK` (chạy lại sạch sau khi cổng báo lỗi đường dẫn, xem LỆCH #1).

### GATE2 — Bộ 4 file requalification (kỳ vọng 225 passed / 2 failed artifact): ĐÚNG KỲ VỌNG
**2 failed, 225 passed trong 74.72s.**
- `test_local1_no_payos_changes` — FAILED (artifact: guard chạy `git diff`, bản copy không có `.git`)
- `test_local1_no_wallet_business_rule_changes` — FAILED (artifact, cùng lý do)

### GATE3A — M3 autopost + H3 webhook: 18 passed, 1 failed (artifact)
- FAILED: `test_p0_17c4_static_guard_no_unrelated_files_touched` (test_p0_17c4_webhook_db_html_security_events.py:282) — guard git-dependent, artifact do không có `.git` (nhóm g1 đã báo cùng kết quả khi deselect test này: 10 passed).
- Passed: 2 test M3 + 10 test webhook + 6 test growth = 18.

### GATE3B — T1/T3/T4 + T2 + refund
- T1/T3: **2 passed**, T4 FAILED như kỳ vọng (KHÔNG SỬA).
- T2: **2 passed**.
- Refund `-k`: **5 passed**, 1 failed pre-existing: `test_support_ticket_menu_admin_registry_and_no_auto_refund` (test_core.py:3387) — fail y hệt trên pristine, không do H2.

### GATE3C — M4/L1/L4: 132 passed, 2 failed (cả 2 đều không phải do fix)
- `test_p0_admin_broadcast2.py::test_live_worker_startup_registers_broadcast_worker_once` — FAILED, pre-existing (chuỗi kiểm tra không có trong cả pristine lẫn bản fix).
- `test_p1_telegram_bot_webapp_link.py::test_confirm_webapp_telegram_link_success` — FAILED trong cổng, nhưng là artifact môi trường sandbox (xem LỆCH #2): chạy lại với `env -u no_proxy -u NO_PROXY` → **1 passed trong 5.19s**; chạy lại với `no_proxy` nguyên → fail lại. L4 không phải nguyên nhân.

### GATE3D — T5/T7/T8: 37 passed, 0 failed
18d4b 16 + 18d4a 17 + R6 fixed 2 + T8 builders 2 = 37 passed trong 44.65s.

### GATE4 — Đếm file đổi: 14 file (danh sách ở trên)

## LỆCH (chỗ nào lệch kỳ vọng thì ghi thẳng)

1. **GATE1 lần chạy đầu in `[Errno 2] No such file or directory: 'remote_worker_api.py'`** — LỆCH do lệnh trong phiếu ghi sai đường dẫn (file nằm ở `services/remote_worker_api.py`, vốn đã nằm trong `services/*.py`). Không phải lỗi code. Chạy lại sạch với đúng đường dẫn → `COMPILE_OK`.
2. **GATE3C: `test_confirm_webapp_telegram_link_success` fail trong cổng** — LỆCH do môi trường sandbox: biến `no_proxy` chứa `[::1]` trần làm httpx lỗi (đúng bug T8 đã sửa ở tầng code, nhưng test này chạy qua `httpx.AsyncClient()` khác chưa được sửa — xem Xin quyết định #7). Đã kiểm chứng sau cổng: `env -u no_proxy` → pass; giữ `no_proxy` → fail lại. Fix L4 không liên quan.
3. **L1 chưa lộ ở cổng local nhưng sẽ lộ ở CI** — cổng GATE2 local vẫn 225/2 vì 2 test guard fail dạng artifact (không có `.git`). Ở CI (có `.git` thật), `test_local1_no_wallet_business_rule_changes` sẽ fail thật vì diff chứa `services/admin_wallet_service.py` (chứa "wallet"). Đây là hậu quả có chủ ý của fix L1 đã duyệt, cần Owner quyết (mục #1 bên dưới).
4. **T2 làm `test_p0_11::test_language_translation_menu_restored` thêm 1 diff** — test này đã fail TRƯỚC fix (lệch label nav). T2 không phá test đang pass nào; chỉ là test-maintenance còn mở (mục #3 bên dưới).

## Xin quyết định (Owner)

1. **L1 vs protected comparator — ĐÃ QUYẾT (A), 2026-11-24 23:52: giữ L1 và cập nhật guard test** (xem mục "Quyết định L1 của Owner" ở trên). Không còn mở.
2. **Webapp caller phải chuyển sang token wallet chuyên dụng trước khi deploy batch này**, nếu không endpoint wallet/credit trả 401 (caller webapp nằm ngoài repo bot, chưa kiểm chứng được nó đang gửi token nào).
3. **T2 vs `test_p0_11::test_language_translation_menu_restored`** — cập nhật expected labels của test (test-maintenance) hay để nguyên fail (test đã fail trước fix do lệch label nav).
4. **T4** — giữ nguyên không sửa (copy admin-only) hay đổi copy admin / thu hẹp test quét source-wide.
5. **T6 follow-up** — `_run_per_scene_provider_orchestrator` suppression (`processing_truth_applied`) nuốt mọi scene failure cứng thành `provider_in_progress` giả. Fix hẹp (chỉ suppress khi task đang live/`pending_seen`) chạm semantics retry/fallback và không có test validate.
6. **T5 follow-up** — (a) sweep `claim_retries_exhausted` đang đếm `outbox.attempt_count` (tăng cả khi lease mismatch); (b) `product_video_probation_lock_state` (`services/video_project_queue.py:2348`) vẫn tính `current_dt` theo VIETNAM_TZ trong khi expiry đã parse host-local — cùng họ lỗi TZ, khác code path, ngoài phạm vi T5.
7. **T8 follow-up** — các `httpx.AsyncClient()` khác trong codebase vẫn đọc env proxy và sẽ crash y hệt trên host có `[::1]` trong `no_proxy` (đây cũng là nguyên nhân LỆCH #2 ở GATE3C). Ngoài phạm vi T8.

## Ghi chú điều phối

- Làm việc chỉ trong `~/workspace/repos/bot-fix` (và 5 bản copy nhóm g1–g5, đã merge xong); tuyệt đối không đụng `~/workspace/repos/bot` (suite đang chạy lại ở đó).
- Merge 5 nhóm vào `bot-fix`: patch bot.py áp sạch bằng `patch --fuzz=0` (30 hunk, chỉ lệch offset, 0 file `.rej`); 9 file đơn nhóm copy byte-identical (kiểm chứng bằng `cmp`).
- Lỗi điều phối đã sửa: một lệnh `cp` sớm đã copy nhầm 3 file service vào thư mục gốc `bot-fix/` — đã xóa ngay, kiểm chứng bằng `diff -rq` (không còn file lạ).
- 2 test M3 được viết lại tối thiểu để ghim thiết kế mới (không đổi ý định test).
- Không merge, không deploy, không push, không động DB production, không gọi API có phí.
