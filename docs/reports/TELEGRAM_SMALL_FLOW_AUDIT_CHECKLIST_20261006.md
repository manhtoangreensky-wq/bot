# Telegram Bot Small-Flow Audit — Checklist & Evidence Ledger

Status: ACTIVE — do not treat this file or any isolated green test as whole-bot completion.

## Scope locks

- Audit emitted Telegram buttons through their registered callback/message handlers; verify source, target, state, Back/Home destination, repeat/expiry behavior, and side effects.
- Keep the AutoPost WIP untouched. Do not refactor the shared router or alter stable Product/Edit/SubDub/Voice/Music engine behavior.
- No secrets, production user data, wallet changes, paid provider calls, real customer messages, restart, merge, or deployment without the applicable owner approval.
- Static callback counts are inventory evidence only; a route is complete only after exercising the emitted control through its registered handler.

## Ordered checklist

| ID | Spec / acceptance evidence | State |
|---|---|---|
| A0 | Current source/main/runtime baseline: `0929d61ade4b8f0d60b803b62417763e90acce9e` after PR #1381. AST inventory measures 87 direct callback registrations, 85 distinct callback expressions and 83 literal patterns; the 4 pattern-free entries are 3 guards plus the final timing observer. Historical emitter snapshot `4f1455ed` had 3,981 constructors/821 dynamic expressions/0 unmatched static callbacks; these older emitter figures have not been refreshed and are not current route proof. | Per-registration matrix drafted in `TELEGRAM_CALLBACK_HANDLER_EVIDENCE_20261006.md`; route verdicts remain partial/unproven. |
| A1 | Admin screens: verify each visible action label matches its handler; test emitted callback, authorization, state transition, and error/stale path. | PARTIAL — report/overview, root/help/package and feedback/access samples have evidence below; S12.13 corrects three Runtime-guide labels without changing their routes; full visible-action matrix remains open. |
| A2 | Admin Back/Home: verify immediate parent and preserve list/filter/page context; test prompt and preview exits without performing the underlying action. | IN PROGRESS — ticket-origin specs S12.6–S12.10 (#1367–#1374) are in #1376; S12.12 merged/deployed in #1378 at runtime SHA `392d2eec`; S12.18 fixes Package Orders returning to Finance instead of Gói/Combo. Other admin/customer routes remain open. |
| A3 | Customer screens: verify ownership, same-product navigation, Back/Home, and no cross-user or cross-product route. | OPEN — audit ledger not complete. |
| A4 | Pending input: verify `/start`, `/menu`, Back, expiry, stale controls, repeated presses, and abandoned drafts clear only the intended state. | PARTIAL — ReplyKeyboard Home preemption PR #1375 is in the deployed #1376 release; the remaining reset/expiry/stale-state matrix is open. |
| A5 | Callback coverage: check static and dynamic emitted values against actual registrations and dispatched terminal behavior; no module-only route test counts as completion. | OPEN — static unmatched count alone is insufficient. |
| A6 | UI/UX consistency: inspect admin/customer button labels, duplicated actions, misleading guide/status labels, row density, and recovery copy; propose or implement only narrow approved fixes. | OPEN — audit ledger not complete. |
| A7 | Final latency diagnosis (last, after route checks): correlate anonymous server phases with a timed user click; separate callback acknowledgement, local build/cleanup, Telegram render, and client/network wait. Report measured distribution and limits; do not guess hardware/network purchases from an uncorrelated sample. | PARTIAL — the 16:57 two-button sequence has measured server timings. After restoring execution under the real Windows account, queries for 18:08–18:15 and 18:40–18:47 +07 returned no matching timing records. The owner did not provide a precise click time; these reports are not additional latency samples. |
| A8 | Closeout: run focused regressions, required syntax/tests, diff/scope review; push a separate PR for each completed spec, merge only in order, and keep deployment/live verification separate. | OPEN. |

## Current evidence

### A1 — Admin operational surface (partial)

- Prior focused evidence: Admin Overview callback and report-source tests passed (one test each); a read-only handler simulation covered monthly/yearly reports, authorization before report read, and invalid period (4 assertions).
- Admin root/help/package evidence: admin root and help tests (2 + 3) and package-storage guide tests (2) passed. Admin feedback/access checks covered emitted destinations, read-only inbox query/no commit, handbook rendering, admin guard, and public denial (6 focused cases); a stale fake helper signature was corrected in the local test fixture.
- Current S12.12 route test exercises the real configured `ADMIN_CONTROL_MODULES` keyboard builders and registered-help callback body; it does not exercise every non-guide admin action or every state-changing handler.
- A1 remains open until each remaining visible admin action has an emitted-button → registered-handler → authorized outcome/error-path evidence row. No provider, wallet, user-data, or production-message operation was performed.

### S12.6 — Admin Ticket reply origin and pagination

- Trigger: Admin Ticket list `high`, offset `6` → ticket detail → `Soạn trả lời` → Back from input or reply preview.
- Root cause: emitted `ticket|reply|<id>` discarded origin; handler hard-coded `source="new"`; pending-state allowlist discarded `list_offset`; preview Back also hard-coded `new`.
- Expected: both Back controls return through `ticket|av|<id>|high|6` to `ticket|al|high|6`; Back must not send the customer reply.
- Local fix: propagate validated source/offset in the Reply callback and pending state, and preserve them in the text preview's Back/Edit controls.
- Evidence before fix: both focused route cases failed at the expected lost-origin assertions.
- Evidence after fix: `python.exe tests/test_support_ticket_reply_origin_pagination.py` → `Ran 2 tests ... OK`; tests dispatch actual emitted controls through the registered ticket handler and assert no send attempt.
- Scope review: the intended patch is `bot.py`, the new focused route test, CI invocation, this checklist, and the tester case. After all edits, the focused unittest reported `Ran 2 tests ... OK`, test-file `py_compile` returned 0, and `git diff --check` returned 0; untracked text files were also checked for trailing whitespace.
- Tester source: `KIEM-THU/DANH-SACH-CASE.md` includes `ADMIN-TICKET-BACK-01`; it requires a seven-ticket fixture/staging list, not production data. Existing tester labels and issue templates were found; no GitHub issue/project was created.
- Delivery state: PR #1367 merged to main on 2026-10-06 as `eba2652bb4ed142bdb4a3daf77099b55bc825cdb`; both required CI checks passed. It was not deployed at its individual merge; it was later deployed as an ancestor in #1376, whose exact runtime SHA is verified below.
- Verification limitation: local `pytest` is unavailable and the earlier full local `py_compile bot.py` run was interrupted after more than six minutes, so it has no local pass/fail verdict. The modified route functions were compiled and exercised by the focused harness, and PR #1367 supplied the missing delivery gates: both `python_hygiene_and_tests` and `python-311-source-compile` passed. No claim is made that the entire repository test suite ran.

### S12.7 — Admin Ticket note origin and pagination

- Trigger: high-priority ticket list `high`, offset `6` → detail → `Ghi chú admin` → Back or submit a note → detail Back.
- Root cause: the note button omitted source/offset; note pending state and prompt Back then defaulted to `new|0`; successful note save also rebuilt detail with the default keyboard.
- Expected: prompt Back returns to the same ticket detail and clears only that pending note; after saving a note, the detail's Back returns to `ticket|al|high|6`.
- RED evidence: three focused tests failed before the fix: emitted callback was `ticket|note|9006` instead of `ticket|note|9006|high|6`; pending data omitted source/offset; saved-note detail linked to `ticket|al|new|0`.
- Minimal fix: carry the validated source/offset in the emitted note callback, pending state, prompt Back, and post-save detail keyboard; legacy callbacks default to `new|0`.
- GREEN evidence: the note-origin tests, existing note stale-guard tests, existing ticket detail pagination test, and S12.6 reply-origin test ran together: `Ran 8 tests ... OK`.
- Scope: `bot.py`, focused regression tests, the CI focused-test command, the tester case, and this ledger. No customer message, provider, wallet, or production data was touched.
- Delivery state: PR #1368 merged to main on 2026-10-06 as `781e23f92e5f169faf2ec7c9cf415d9a0982956a`; both required CI checks passed. It was not deployed at its individual merge; it was later deployed as an ancestor in #1376.

### S12.8 — Admin Ticket ask-customer origin and pagination

- Trigger: high-priority ticket list `high`, offset `6` → detail → `Hỏi thêm khách` → Back at prompt or at preview.
- Root cause: the ask callback omitted source/offset and the handler hard-coded `source="new"`; the existing pending-input/preview path could preserve origin, but it received the wrong default.
- Expected: both Back controls return to the same ticket detail; its list Back returns to `ticket|al|high|6`; pending input is cleared and no customer message is sent.
- RED evidence: three focused tests failed before the fix: emitted callback was `ticket|ask|9006` instead of `ticket|ask|9006|high|6`; pending source was `new` with no offset; preview Back linked to `ticket|av|9006|new|0`.
- Minimal fix: include the validated source/offset in the ask callback, carry them in `admin_reply_input`, and use them in the prompt Back. Existing preview construction already preserves that state.
- GREEN evidence: ask-origin, ask stale-guard, note-origin, note stale-guard, ticket detail pagination, and reply-origin tests ran together: `Ran 13 tests ... OK`. Fake Telegram send spy recorded zero sends during Back paths.
- Scope: `bot.py`, focused regressions, CI invocation, tester case, support runbook, and this ledger. No real customer message, provider, wallet, or production data was touched.
- Delivery state: PR #1370 merged to main on 2026-10-06 as `e954fcaef968a421e8628428d733f99ec7ee275c`; both PR CI gates passed. No deploy workflow ran at that individual merge; it was later deployed as an ancestor in #1376.

### S12.9 — Admin Ticket assignment origin and pagination

- Trigger: high-priority ticket list `high`, offset `6` → ticket detail → `Nhận xử lý` → `Danh sách`.
- Root cause: the Assign button emitted `ticket|assign|<id>` without source/offset; after assignment the handler rebuilt the detail keyboard with its default `new|0` context.
- Expected: Assign updates only the fixture ticket's assignee/status; the refreshed detail's list button remains `ticket|al|high|6`.
- RED evidence: the registered-handler regression expected `ticket|assign|9006|high|6` but got `ticket|assign|9006`.
- Minimal fix: carry validated source/offset in the Assign callback, parse them in the handler with legacy `new|0` fallback, and rebuild the detail keyboard with that context.
- GREEN evidence: ask/assign origin, ask stale-guard, note origin/stale-guard, reply origin, and Admin Ticket Back pagination ran together: `Ran 14 tests ... OK`. Assign is dispatched through the registered ticket handler; no production data or customer message is used.
- Scope: `bot.py`, the generic focused origin test module, CI invocation, tester case, support runbook, and this ledger. No provider call or wallet mutation.
- Delivery state: PR #1371 merged to main on 2026-10-06 as `b3aa82150c570b139dc36047821eb4bbdd04b99d`; both PR checks and main-push CI/source-compile passed. No deploy workflow ran at that individual merge; it was later deployed as an ancestor in #1376.

### S12.10 — Admin Ticket status-change origin and pagination

- Trigger: high-priority ticket list `high`, offset `6` → detail → any status action (`Đã xử lý`, `Đánh dấu refund`, or `Chờ provider`) → `Danh sách`.
- Root cause: all three status callbacks omitted source/offset; after updating status, the handler rebuilt the detail keyboard with the default `new|0` context.
- Expected: all three emitted callbacks carry the current filter/page; a status update changes only the fixture ticket and keeps `ticket|al|high|6` in the refreshed detail.
- RED evidence: the registered-handler test expected `ticket|st|9006|resolved|high|6`, `...|refund_pending|high|6`, and `...|waiting_provider|high|6`; all emitted callbacks omitted `high|6`.
- Minimal fix: append validated source/offset to all three status callbacks; parse them with legacy `new|0` fallback and rebuild the detail with that origin.
- GREEN evidence: status, Assign, Ask, stale-guard, Note, Reply, and Admin Ticket Back regressions ran together: `Ran 15 tests ... OK`. The test dispatches a real emitted status callback through the registered handler using an in-memory ticket fixture.
- Scope: `bot.py`, the existing focused origin regression module/CI command, tester case, support runbook, and this ledger. No production ticket, provider call, customer message, or wallet mutation.
- Delivery state: PR #1372 merged on 2026-10-06; both required checks passed. No deploy ran at that individual merge; it was later deployed as an ancestor in #1376.

### A4 — ReplyKeyboard Home while AutoPost content input is pending

- Trigger: with `awaiting_content_input_type` set, press either `🏠 TOAN AAS MENU` or the legacy `🛸 MENU DỊCH VỤ TOAN AAS` ReplyKeyboard label.
- Root cause: `handle_message` checked those Home labels below the AutoPost pending-content branch, so the Home label could be stored as post content instead of opening `/start`'s menu.
- RED evidence: the baseline handler harness failed on the Home-route assertion while the pending-content state was active.
- Minimal fix: recognize exactly those two labels immediately after slash-state handling and before pending-input handlers; leave the AutoPost content branch unchanged.
- GREEN evidence: `python -m pytest -q --noconftest -p no:cacheprovider tests/test_reply_keyboard_home_route_priority.py` → `3 passed in 1.11s`. Two cases exercise both Home labels and assert the emitted keyboard label plus text-handler registration; the third confirms ordinary pending AutoPost text still follows its existing save-and-draft path. `--noconftest` avoids the unrelated autouse fixture that imports the full `bot.py` module; this test compiles and dispatches the extracted `handle_message` function directly.
- Current-turn verification: shell Python has no `pytest` module, so the same 3 test cases were rerun with the standard-library runner and only the `pytest.mark.parametrize` decorator shimmed: `3 focused route cases passed (built-in runner; pytest decorators shimmed)`. `python -m py_compile tests/test_reply_keyboard_home_route_priority.py` and `git diff --check` returned 0.
- Syntax/scope limit: full `py_compile bot.py` previously produced no result after 60 seconds and was interrupted; the focused harness compiles the complete changed `handle_message` function, but no full-file syntax pass is claimed. GitHub source-compile CI remains a required gate.
- Scope: `bot.py`, the focused regression test, tester case, and this ledger. No provider call, Telegram send, job, wallet, production data, or protected engine was touched.
- Boundary: Home now routes correctly, but current `cmd_start` does not clear `awaiting_content_input_type`; therefore later ordinary text still follows the active AutoPost input path. Changing that reset/cancel behavior is outside this approved change.
- Delivery state: PR #1375 merged on 2026-10-06 as `f9e2ea473617409194ad48498beab14b68c2e8dd`; both required CI checks passed. It was later deployed as an ancestor in #1376.

### S12.11 — Anonymous timing coverage for registered callback handlers

- State: PR #1376 merged to main as `27926e15375f9ce7d41bbf37d5fee596c1216fec`; required `python_hygiene_and_tests` and `python-311-source-compile` checks passed. Deploy workflow #37445257742 succeeded; read-only VPS check confirmed `toanaas-bot.service` active/running, `NRestarts=0`, runtime SHA equals the merge SHA. This release also contains merged ancestors #1367–#1375 (including Product Video #1369), so it was not logger-only. Worker sync was disabled because the target diff did not include worker source.
- Trigger/coverage: installer wraps pre-existing `CallbackQueryHandler` registrations after registration is complete, including the three shared negative-group guards, then adds a final observer. The prior "87 pre-existing" count is superseded by the current AST inventory: 87 total direct registrations include that observer (86 precede it). Source review found no `ConversationHandler` and no `CallbackQueryHandler(block=False)` path in this repo. Callback registration patterns and Python handler names are source-defined labels; full callback data is not read for logging.
- Log fields: `prefix`, `handler`, aggregate `guard_ms`, source-named `guard_phases`, `handler_ms`, `render_helper_ms`, `render_helper_calls`, `dispatch_ms`, and coarse `outcome`. `handler_ms` includes nested awaited work; `render_helper_ms` overlaps it and is not an additive phase.
- Privacy: the instrumentation does not log user/chat/message IDs, callback payload, message text, exception details, provider/job IDs, or secrets. Synthetic regression cases verify this for success, guard stop, and handler error.
- RED/GREEN evidence: the first run failed because the instrumentation API was absent; a second RED exposed missing per-guard attribution. Standard-library run with the Codex-bundled Python: `Ran 4 tests in 6.112s — OK`. Full local `py_compile bot.py` produced no output after 60 seconds and was interrupted; no full local syntax pass is claimed. Both GitHub compile and hygiene/tests checks passed for #1376.
- Coverage limit: `render_helper_ms` measures only the shared `safe_edit_query_message` await time; it is not client display/network time and excludes direct Telegram send/edit calls that bypass this helper. `dispatch_ms` is bot-process dispatch from the first guard to the final observer. Existing `callback_latency` records for `menu|main` and `menu|main_video` remain, so those two callbacks will emit a second, separately named `callback_dispatch_timing` record.
- Post-deploy runtime/event gate: satisfied for #1376. The owner confirmed clicking Product Video then Back; anonymous logs contain the expected route sequence, with limits recorded under A7 below. This does not establish client-render timing or all-route smoothness.

### S12.12 — Admin handbook Back returns to its originating module

- Trigger: open an Admin module such as Queue/Freeze or CSKH, press a guide button, then use the guide's Back button.
- Root cause: module guide callbacks omitted their source module (except User/Xu); `handle_admin_help_callback` discarded every parent except `admin_users`; the handbook keyboard therefore fell back to `menu|admin`.
- RED evidence: before the production patch, focused dispatch expected `admin_help|refund|admin_queue` but the Queue button emitted `admin_help|refund`.
- Minimal change: scope only Admin-module `admin_help` callbacks to their module; render a validated Back callback to that module. Legacy/context-free handbook links retain their existing Admin-root Back behavior. No guide text, business action, or product engine changed.
- GREEN evidence: standard-library harness ran `Ran 4 tests ... OK`; it extracts the actual module config and keyboard/handler functions, dispatches every emitted Admin guide callback from all 9 modules, and asserts the Back destination equals the source module. The test also checks registration and non-admin denial. Package-guide tests: `Ran 2 tests ... OK`; three admin-feedback route functions passed via the built-in runner. Changed test files compiled and `git diff --check` returned 0.
- Limits: full-file `py_compile bot.py` was attempted but had no output after about 65 seconds and was interrupted; local full suite/pytest has not been established for this spec. GitHub required CI must pass before merge. No DB mutation, customer message, provider call, wallet operation, deploy, or restart.
- Delivery state: PR #1378 merged as `392d2eec8f942c8e5c1232e5ac537b9a84dfd82c` at `2026-10-06T11:00:27Z`; both required CI gates passed. Deploy run [#37453919573](https://github.com/manhtoangreensky-wq/bot/actions/runs/37453919573) succeeded with that SHA. Read-only VPS check returned `active`, `running`, `NRestarts=0`, and runtime SHA `392d2eec8f942c8e5c1232e5ac537b9a84dfd82c`. No worker sync was requested by the workflow.
- Post-deploy click check: the owner confirmed another click. The read-only journal query covered `2026-10-06 18:08–18:15 +07`; no `callback_dispatch_timing` or `callback_latency route=menu` lines were returned. Without the precise click time and a matching record, this does not prove whether the click reached the callback handler. A7 stays partial.

### S12.13 — Admin Runtime shortcut labels match the guide destination

- Trigger: Admin System, Security/DB, or the legacy Admin System screen → press `Runtime`.
- Source evidence: all three buttons emitted `menu|system_runtime_help`; the registered page spec resolves that action to `system_help_text("runtime")`, a guide page rather than a live status probe.
- RED evidence: an isolated harness executed the actual `menu_nav_keyboard` and `admin_module_keyboard` builders; it found three callbacks labelled `🧬 Runtime`, and the expected guide-label assertion failed.
- Minimal fix: rename those three labels to `📘 Hướng dẫn Runtime`; preserve every callback, handler, guide body, and live runtime command.
- GREEN evidence: the label assertion moved into the existing source-extracted `unittest` fixture and is explicitly executed by CI. Admin handbook/package and ticket-origin regressions ran together: `Ran 24 tests in 25.950s — OK`. The same label case on exact main returned one expected assertion failure. A source comparator proves all `bot.py` differences are exactly the three labels. Full local `py_compile bot.py` previously returned `PY_COMPILE_OK`; changed test files compile successfully.
- Local environment limit: `pytest` is absent. Workflow hygiene ran 99 tests and had 31 failures in Windows Bash fixtures (`bash`/`mkdir`/`dirname` unavailable inside simulated scripts). The deployment workflow, worker-sync script and hygiene test are unchanged; required Ubuntu CI must pass before merge.
- Scope: three labels in `bot.py`, the existing Admin help `unittest`, one CI invocation, tester case and documentation. No runtime action, DB/user-data write, provider call, wallet action, or production message was performed.
- Delivery state: PR [#1379](https://github.com/manhtoangreensky-wq/bot/pull/1379) merged as `2099eb319483ba1acc80f1080a094ba9710b5f3d`. Both CI gates passed; Ubuntu ran 22 Admin route regressions and 99 workflow-hygiene tests successfully. Deploy [#37468134372](https://github.com/manhtoangreensky-wq/bot/actions/runs/37468134372) attempt 2 succeeded. Attempt 1 lost SSH while reading the old SHA, before mutation. Read-only runtime verification confirmed matching SHA, three guide labels, bot/web/nginx active/running with `NRestarts=0`, and HTTP health 200. New-label manual Telegram QA is not claimed.

### S12.14 — Billing shortcuts describe command guides

- Baseline: `2099eb319483ba1acc80f1080a094ba9710b5f3d`; branch `fix/admin-billing-guide-labels-20261006`.
- Scope: seven misleading labels across the module and legacy Billing keyboards. Four destinations (`pending`, `duyet`, `tuchoi`, `payos`) are read-only instructions; the legacy PayOS shortcut also needs the existing module's plan label.
- Acceptance: all eight emitted guide controls dispatch through registered `handle_menu_callback`, show the intended slash-command instructions and Back to Billing; public access is denied before state cleanup. Financial/provider/DB behavior is outside this label patch.
- RED: 3 fixture tests ran; guide dispatch and public-denial tests passed, while the guide-label assertion failed on the actual `📋 Pending` output. Production labels have not yet changed at this evidence point.
- GREEN: seven labels changed across the two keyboards. All 8 emitted controls traverse the registered menu handler, render their command guide and dispatch Back to the actual Billing module. Public access is denied before state cleanup. The focused and Admin/package/ticket regressions ran `27 tests in 32.017s — OK`; test-file compile and `git diff --check` passed. An exact source comparator proves no `bot.py` difference beyond those seven label replacements.
- Delivery: PR [#1380](https://github.com/manhtoangreensky-wq/bot/pull/1380) merged as `74a8d86f24d1c8960706bc2c73b0ca984a69ae56`. Full local bot.py py_compile passed; both Ubuntu CI gates passed (25 Admin route tests and 99 workflow-hygiene tests). Deploy [#37471503412](https://github.com/manhtoangreensky-wq/bot/actions/runs/37471503412) succeeded with workers disabled. Read-only VPS verification confirmed exact SHA, tracked bot.py matches, bot/web/nginx active/running with `NRestarts=0` and health HTTP 200. New-label manual Telegram QA is not claimed.
- Next route candidate after delivery: Runtime-help Back from Security/DB/System Ops appears to return to the legacy System page. This is source-only evidence; reproduce the real emitted-control/registered-handler path before changing it.

### S12.15 — Runtime guide Back retains Admin module origin

- Baseline `74a8d86f`; branch `fix/admin-runtime-guide-back-origin-20261006`. Actual emitted controls from Security/DB and System Ops were dispatched through registered `handle_menu_callback`; both guide Back keyboards contained `menu|system` rather than the emitting module: 2 expected RED assertions. Legacy and public-denial cases passed.
- Minimal change: append a validated module origin to these two emitters; the menu handler recognizes only this Runtime-guide context and replaces only its Back control. The existing Admin/Home controls, Runtime guide body and context-free legacy callback are preserved. Unknown, empty or extra origin data receives one expired-button alert before cleanup.
- GREEN: 31 Admin/runtime/Billing/package/ticket route tests passed in 39.856s; 6 root-menu/timing tests passed in 5.868s; the original denied-menu test passed for 3 routes. Tests dispatch the corrected Back into the actual module renderer, verify callbacks fit the byte limit and prove denied/invalid contexts have no pending cleanup.
- Changed tests compile and CI explicitly executes Runtime Back, root-menu and timing regressions. Complete-source compile and workflow hygiene remain required Ubuntu PR gates.
- Delivery: PR [#1381](https://github.com/manhtoangreensky-wq/bot/pull/1381) merged as `0929d61ade4b8f0d60b803b62417763e90acce9e`. Both CI gates passed: 35 Admin route regressions and 99 deployment-hygiene tests, complete compile/AST/py_compile/tokenize. Bot-only deploy [#37474025306](https://github.com/manhtoangreensky-wq/bot/actions/runs/37474025306) succeeded. Read-only VPS verification confirmed exact SHA, tracked bot.py matches, bot/web/nginx active/running with `NRestarts=0`, health HTTP200. Manual Telegram QA of the new Back is not claimed.
- Provider calls, production DB writes, wallet operations and customer messages: 0. Engine/worker sources and AutoPost WIP remain protected.

### S12.16 — Current handler evidence inventory

- Source baseline `0929d61a`; AST inspection of blocks containing callback constructors found 87 direct registrations and 87 constructor calls, 85 distinct handler expressions and 83 literal patterns. Each registration has its measured bot.py line in `TELEGRAM_CALLBACK_HANDLER_EVIDENCE_20261006.md`.
- The table separates source inventory from verdicts. Test-name references are candidates only; negative-group guards and the timing observer do not prove a business route works. Current 35-route CI is not whole-bot coverage.
- Five source handler names have no direct named-test references: Buy Plan, Image Story, media preview, Pixabay media and suggested music. Their source paths require review; absence of a reference is not a proven defect.
- Initial source review of the three media/suggestion top-level handlers shows early acknowledgement; six immediate downstream preview/select/source/license helpers contain no direct `.answer(` calls. This has not demonstrated a duplicate-ack bug; cache ownership, stale/error and recovery Back paths still need inert fixtures. No code change, real media fetch, provider or wallet call occurred in this inventory step.
- Full current-source inventory is published in PR #1381: https://github.com/manhtoangreensky-wq/bot/pull/1381#issuecomment-6018079915. Local delivery/checklist updates are retained on the active audit branch for the next narrow fix; no extra production restart was used to publish an audit report.

### S12.17 — Media-library buttons stay bound to their result snapshot

- Contract: verify the emitted Jamendo music, Freesound SFX, and Pixabay controls through their registered handlers. A button from result set A must never read/select result set B after a newer search replaces the same user's cache; callbacks from another user, an expired cache, or a different active product context must fail closed. Old tokenless buttons must show an expired-result response. Current valid controls must still work, and the video follow-up License button must stay bound to the selected result.
- RED: the corrected source-extraction harness failed on five behavioral assertions against baseline `0929d61a`: music and Pixabay item buttons had only `action|index`; an old Music Select reached the registered handler and resolved the replacement `Track B`; an old showroom Select still reached its helper after switching to Video Add-on; an old Pixabay Preview resolved replacement item B. No provider/helper setup error caused the RED.
- Minimal fix: each search cache now has a UUID callback token and product context. Emitted item controls and the video-follow-up License control carry that token. Registered handlers validate the token, per-user cache, 10-minute TTL and current product context before reaching preview/select helpers. Tokenless legacy callbacks are accepted by the old-compatible pattern but fail closed with a localized alert. `/play_music`, `/select_music`, SFX and media commands still call helpers without a callback token.
- GREEN: `python -m unittest tests/test_media_preview_callback_snapshot.py` → `Ran 19 tests in 51.593s — OK`. Actual emitted keyboard builders and exact registered handler source are exercised; valid Music/Pixabay Select reaches the production in-memory selection function; valid Preview and selected-video License traverse their registered handlers with the same token; stale follow-up License is rejected after replacement. Telegram/provider sends are inert. Stale replacement, user mismatch, context change, expiry, invalid index, legacy callback and callback byte limit cases pass.
- Syntax/scope: bundled Python `-m py_compile bot.py tests/test_media_preview_callback_snapshot.py` exited `0` for this exact branch state; `git diff --check` exited `0` (only the expected LF→CRLF state-file warning). Local `pytest` is unavailable (`No module named pytest`); the new unittest is added as a separate Ubuntu CI step for complete source compilation and workflow verification.
- Side effects: provider calls `0`; real Telegram sends `0`; jobs `0`; wallet mutations `0`; production-data writes `0`. Manual Telegram/client behavior is not claimed.
- Impact check before code (all references are in `bot.py` except noted):

  | Symbol | Definition and call sites | Files |
  |---|---|---|
  | `save_media_preview_results` | `bot.py:174627`, calls at `175843`, `175914` | 1 |
  | `get_media_preview_item` | `bot.py:174637`, calls at `174840`, `174861`, `174885`, `175014` | 1 |
  | `media_preview_keyboard` | `bot.py:174653`, calls at `175844`, `175915`; labels also checked at `tests/test_product_context_separation.py:119-120` | 2 |
  | Preview helpers/handler | `bot.py:174837`, `174858`, `174882`, `175011`, `175147`; command wrappers at `175166`, `175170`, `175211`, `175215` | 1 |
  | Pixabay save/get/keyboard | `bot.py:175600`, `175609`, `175624`; callers at `175963-175964` | 1 |
  | Pixabay preview/select/handler | `bot.py:175648`, `175689`, `175738`; command wrappers at `175752`, `175756` | 1 |
  | `selected_music_video_followup_keyboard` | `bot.py:174954`, call at `175103`; label regression at `tests/test_core.py:4234` | 2 |

- Planned delivery files: `bot.py`, one focused registered-handler unittest, the explicit CI route-test command, this checklist, the handler evidence matrix, the tester case and durable state. The existing modified operating notes remain in scope only for an evidence-backed progress update.
- Delivery: PR [#1382](https://github.com/manhtoangreensky-wq/bot/pull/1382) merged as `979c0ee5d9cc3b51d23b5c6470a6d02947f69208`; required PR checks and main-push CI passed. Deploy run [#37486561839](https://github.com/manhtoangreensky-wq/bot/actions/runs/37486561839) succeeded with `deploy_workers=false`. Read-only VPS verification returned exact runtime SHA `979c0ee5d9cc3b51d23b5c6470a6d02947f69208`, bot/web/nginx `active`, `NRestarts=0`, and health `status=ok`. Manual Telegram/provider QA is not claimed.
- Status: MERGED + DEPLOYED + RUNTIME-SHA-VERIFIED. Overall bot audit remains open.

### S12.18 — Admin Package Orders Back retains package-module origin

- Trigger: Admin → Gói / Combo → Đơn chờ duyệt → Quay lại.
- RED: the actual `admin_module_keyboard("packages")` emitted `menu|admin_package_orders`, but `admin_package_orders_keyboard()` rendered `⬅️ Tài chính` with `menu|finance`; the immediate parent was lost. The same child screen is also reachable from Finance, so a fixed static Back would break the Finance entry.
- Minimal fix: carry a validated origin token (`admin_packages` or `finance`) in each entry callback; render the matching Back label/destination and reject unknown origin tokens. Catalog, User Packages, Menu chính and all package/payment behavior are unchanged.
- GREEN: `python -m unittest tests/test_admin_package_orders_back_origin.py tests/test_finance_back_destination.py tests/test_broadcast_lite_back_pending_cleanup.py` → `Ran 6 tests ... OK`. The new test executes the production keyboard builder and registered menu handler for both origins. No DB writes, provider calls, wallet mutations, broadcast sends or production messages.
- Scope lock: one narrow callback route, two keyboard emitters, one focused unittest, one CI invocation, and this evidence ledger. Product/Edit/SubDub/Voice/Music engines and AutoPost WIP are untouched.
- Status: LOCAL GREEN — PR/CI/deploy pending.

### Final latency spec — partial, server/client split preserved

- Current main/runtime target: `0929d61ade4b8f0d60b803b62417763e90acce9e` from PR #1381. Deploy run [#37474025306](https://github.com/manhtoangreensky-wq/bot/actions/runs/37474025306) succeeded; read-only VPS verification found all three services active/running with `NRestarts=0` and the matching runtime SHA. The timings below are the earlier historical sample, not fresh measurements of this release.
- After the owner confirmed clicking “Tạo video AI” then “Quay lại”, the anonymous event sequence was `menu|main_video` at `2026-10-06 16:57:18.250 +07`, then `menu|main` at `16:57:20.867 +07`. This is consistent with the two-button round, but there was no exact user click timestamp and the logs contain no identity/callback data, so attribution is not absolute.
- Per-route `callback_latency`: handler `156.054 ms` / `156.930 ms`; acknowledgement `58.973 ms` / `58.998 ms`; awaited `safe_edit_query_message` `76.181 ms` / `79.439 ms`; `render_returned=1` for both.
- `callback_dispatch_timing`: shared guards `35.518 ms` / `33.789 ms`, of which `safe_mode_callback_guard` was `35.405 ms` / `33.724 ms`; total server dispatch `193.403 ms` / `192.631 ms`.
- Supported conclusion: in this sample the server completed dispatch in about 0.19 seconds and the Telegram edit helper returned in about 0.08 seconds. This does not measure Telegram-client display, device rendering, carrier/Wi-Fi, or the end-to-end interval; it cannot identify a remaining network/device cause or justify a hardware purchase.
- Coverage: this is one two-route sequence, not a latency distribution and not evidence for every bot button. Continue gathering route families after A1–A6; then compare several user-timed samples with server phases. Keep A7 PARTIAL until that evidence exists.
- Following later owner click reports, queries covered 18:08–18:15 and 18:40–18:47 +07 and returned no matching timing records. No precise owner-supplied click time exists for these reports; no additional latency conclusion is drawn.
- Access recovery on 2026-10-06: execution under the actual Windows account `martin\\toann` returned GitHub auth exit 0; the SSH identity and pinned ED25519 host key were already accessible. Earlier denied reads under `CodexSandboxOffline` had incorrectly been treated as missing identity/host trust. No ACL, host-key or credential content was changed. Read-only VPS verification at 19:51 +07 confirmed all three services active/running, `NRestarts=0`, and runtime SHA `392d2eec`.
- No provider call, wallet mutation, production-data write, or customer message was made in either audit spec.

## Next execution order

1. S12.11 (#1376) is merged/deployed and its exact runtime SHA is verified; its release scope includes ancestors #1367–#1375.
2. S12.12 (#1378) is merged, deployed, and runtime-SHA verified; no dependent spec starts with an unknown runtime.
3. S12.13 (#1379) is merged, deployed and runtime-SHA verified at `2099eb3`; its 3-label source comparator and CI gates passed.
4. S12.14 (#1380) is merged/deployed/runtime verified at `74a8d86f`; 8 emitted guide controls, Back/public guards, source comparator and CI gates passed.
5. S12.15 (#1381) is merged/deployed/runtime verified at `0929d61a`; S12.16 inventories registrations but is not whole-bot route proof.
6. S12.17 is merged/deployed/runtime verified at `979c0ee5`; its stale media result controls are closed.
7. S12.18 now has local RED/GREEN evidence for shared Package Orders origin; finish separate CI, merge, deploy and exact-runtime verification before marking its delivery closed.
8. Continue A1–A5 for remaining admin/customer routes, pending-state expiry/stale/repeat behavior, preserving protected product lanes.
9. Finish A6 UI/UX consistency review and update this ledger with evidence, not assumptions.
10. Close A7 only after multiple user-timed samples can be compared to anonymous server phases; separate server, Telegram render and client/network wait.
11. Complete A8 only after every checklist row has evidence and delivery states are separately verified.
