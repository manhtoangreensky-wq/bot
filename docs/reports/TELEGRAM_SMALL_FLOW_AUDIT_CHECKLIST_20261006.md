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
| A0 | Pin source baseline and enumerate static/dynamic callbacks. Inventory snapshot source: `4f1455ed31c3ebb4acbb6f6d3eff4144bf02185d`; main at last check: `f9e2ea473617409194ad48498beab14b68c2e8dd` after PR #1375. Snapshot reports 3,981 button constructors, 83 static handler patterns, 0 unmatched static callbacks, and 821 dynamic callback expressions, all measured on the older snapshot SHA; counts do not prove route correctness and have not yet been refreshed after the merges. | Baseline captured; dynamic paths still require route evidence. |
| A1 | Admin screens: verify each visible action label matches its handler; test emitted callback, authorization, state transition, and error/stale path. | OPEN — audit ledger not complete. |
| A2 | Admin Back/Home: verify immediate parent and preserve list/filter/page context; test prompt and preview exits without performing the underlying action. | IN PROGRESS — S12.6 #1367, S12.7 #1368, S12.8 #1370, S12.9 #1371, S12.10 #1372, and subsequent Admin Ticket navigation #1373/#1374 merged; other admin/customer routes remain open. |
| A3 | Customer screens: verify ownership, same-product navigation, Back/Home, and no cross-user or cross-product route. | OPEN — audit ledger not complete. |
| A4 | Pending input: verify `/start`, `/menu`, Back, expiry, stale controls, repeated presses, and abandoned drafts clear only the intended state. | PARTIAL — ReplyKeyboard Home preemption is locally fixed/tested below; the remaining reset/expiry/stale-state matrix is open. |
| A5 | Callback coverage: check static and dynamic emitted values against actual registrations and dispatched terminal behavior; no module-only route test counts as completion. | OPEN — static unmatched count alone is insufficient. |
| A6 | UI/UX consistency: inspect admin/customer button labels, duplicated actions, misleading guide/status labels, row density, and recovery copy; propose or implement only narrow approved fixes. | OPEN — audit ledger not complete. |
| A7 | Final latency diagnosis (last, after route checks): correlate anonymous server phases with a timed user click; separate callback acknowledgement, local build/cleanup, Telegram render, and client/network wait. Report measured distribution and limits; do not guess hardware/network purchases from an uncorrelated sample. | PARTIAL — one server event below; needs a timestamp-correlated sample and additional events. An approved instrumentation spec is tracked separately below; it does not close A7. |
| A8 | Closeout: run focused regressions, required syntax/tests, diff/scope review; push a separate PR for each completed spec, merge only in order, and keep deployment/live verification separate. | OPEN. |

## Current evidence

### S12.6 — Admin Ticket reply origin and pagination

- Trigger: Admin Ticket list `high`, offset `6` → ticket detail → `Soạn trả lời` → Back from input or reply preview.
- Root cause: emitted `ticket|reply|<id>` discarded origin; handler hard-coded `source="new"`; pending-state allowlist discarded `list_offset`; preview Back also hard-coded `new`.
- Expected: both Back controls return through `ticket|av|<id>|high|6` to `ticket|al|high|6`; Back must not send the customer reply.
- Local fix: propagate validated source/offset in the Reply callback and pending state, and preserve them in the text preview's Back/Edit controls.
- Evidence before fix: both focused route cases failed at the expected lost-origin assertions.
- Evidence after fix: `python.exe tests/test_support_ticket_reply_origin_pagination.py` → `Ran 2 tests ... OK`; tests dispatch actual emitted controls through the registered ticket handler and assert no send attempt.
- Scope review: the intended patch is `bot.py`, the new focused route test, CI invocation, this checklist, and the tester case. After all edits, the focused unittest reported `Ran 2 tests ... OK`, test-file `py_compile` returned 0, and `git diff --check` returned 0; untracked text files were also checked for trailing whitespace.
- Tester source: `KIEM-THU/DANH-SACH-CASE.md` includes `ADMIN-TICKET-BACK-01`; it requires a seven-ticket fixture/staging list, not production data. Existing tester labels and issue templates were found; no GitHub issue/project was created.
- Delivery state: PR #1367 merged to main on 2026-10-06 as `eba2652bb4ed142bdb4a3daf77099b55bc825cdb`; both `python_hygiene_and_tests` and `python-311-source-compile` passed. It was not deployed; the logging-only approval did not authorize deployment of this Admin Ticket change.
- Verification limitation: local `pytest` is unavailable and the earlier full local `py_compile bot.py` run was interrupted after more than six minutes, so it has no local pass/fail verdict. The modified route functions were compiled and exercised by the focused harness, and PR #1367 supplied the missing delivery gates: both `python_hygiene_and_tests` and `python-311-source-compile` passed. No claim is made that the entire repository test suite ran.

### S12.7 — Admin Ticket note origin and pagination

- Trigger: high-priority ticket list `high`, offset `6` → detail → `Ghi chú admin` → Back or submit a note → detail Back.
- Root cause: the note button omitted source/offset; note pending state and prompt Back then defaulted to `new|0`; successful note save also rebuilt detail with the default keyboard.
- Expected: prompt Back returns to the same ticket detail and clears only that pending note; after saving a note, the detail's Back returns to `ticket|al|high|6`.
- RED evidence: three focused tests failed before the fix: emitted callback was `ticket|note|9006` instead of `ticket|note|9006|high|6`; pending data omitted source/offset; saved-note detail linked to `ticket|al|new|0`.
- Minimal fix: carry the validated source/offset in the emitted note callback, pending state, prompt Back, and post-save detail keyboard; legacy callbacks default to `new|0`.
- GREEN evidence: the note-origin tests, existing note stale-guard tests, existing ticket detail pagination test, and S12.6 reply-origin test ran together: `Ran 8 tests ... OK`.
- Scope: `bot.py`, focused regression tests, the CI focused-test command, the tester case, and this ledger. No customer message, provider, wallet, or production data was touched.
- Delivery state: PR #1368 merged to main on 2026-10-06 as `781e23f92e5f169faf2ec7c9cf415d9a0982956a`; `python_hygiene_and_tests` and `python-311-source-compile` passed. It was not deployed.

### S12.8 — Admin Ticket ask-customer origin and pagination

- Trigger: high-priority ticket list `high`, offset `6` → detail → `Hỏi thêm khách` → Back at prompt or at preview.
- Root cause: the ask callback omitted source/offset and the handler hard-coded `source="new"`; the existing pending-input/preview path could preserve origin, but it received the wrong default.
- Expected: both Back controls return to the same ticket detail; its list Back returns to `ticket|al|high|6`; pending input is cleared and no customer message is sent.
- RED evidence: three focused tests failed before the fix: emitted callback was `ticket|ask|9006` instead of `ticket|ask|9006|high|6`; pending source was `new` with no offset; preview Back linked to `ticket|av|9006|new|0`.
- Minimal fix: include the validated source/offset in the ask callback, carry them in `admin_reply_input`, and use them in the prompt Back. Existing preview construction already preserves that state.
- GREEN evidence: ask-origin, ask stale-guard, note-origin, note stale-guard, ticket detail pagination, and reply-origin tests ran together: `Ran 13 tests ... OK`. Fake Telegram send spy recorded zero sends during Back paths.
- Scope: `bot.py`, focused regressions, CI invocation, tester case, support runbook, and this ledger. No real customer message, provider, wallet, or production data was touched.
- Delivery state: PR #1370 merged to main on 2026-10-06 as `e954fcaef968a421e8628428d733f99ec7ee275c`; both PR CI gates passed. Main push CI passed; no deploy workflow ran for this merge. It was not deployed.

### S12.9 — Admin Ticket assignment origin and pagination

- Trigger: high-priority ticket list `high`, offset `6` → ticket detail → `Nhận xử lý` → `Danh sách`.
- Root cause: the Assign button emitted `ticket|assign|<id>` without source/offset; after assignment the handler rebuilt the detail keyboard with its default `new|0` context.
- Expected: Assign updates only the fixture ticket's assignee/status; the refreshed detail's list button remains `ticket|al|high|6`.
- RED evidence: the registered-handler regression expected `ticket|assign|9006|high|6` but got `ticket|assign|9006`.
- Minimal fix: carry validated source/offset in the Assign callback, parse them in the handler with legacy `new|0` fallback, and rebuild the detail keyboard with that context.
- GREEN evidence: ask/assign origin, ask stale-guard, note origin/stale-guard, reply origin, and Admin Ticket Back pagination ran together: `Ran 14 tests ... OK`. Assign is dispatched through the registered ticket handler; no production data or customer message is used.
- Scope: `bot.py`, the generic focused origin test module, CI invocation, tester case, support runbook, and this ledger. No provider call or wallet mutation.
- Delivery state: PR #1371 merged to main on 2026-10-06 as `b3aa82150c570b139dc36047821eb4bbdd04b99d`; both PR checks and main-push CI/source-compile passed. No deploy workflow ran for this merge; it was not deployed.

### S12.10 — Admin Ticket status-change origin and pagination

- Trigger: high-priority ticket list `high`, offset `6` → detail → any status action (`Đã xử lý`, `Đánh dấu refund`, or `Chờ provider`) → `Danh sách`.
- Root cause: all three status callbacks omitted source/offset; after updating status, the handler rebuilt the detail keyboard with the default `new|0` context.
- Expected: all three emitted callbacks carry the current filter/page; a status update changes only the fixture ticket and keeps `ticket|al|high|6` in the refreshed detail.
- RED evidence: the registered-handler test expected `ticket|st|9006|resolved|high|6`, `...|refund_pending|high|6`, and `...|waiting_provider|high|6`; all emitted callbacks omitted `high|6`.
- Minimal fix: append validated source/offset to all three status callbacks; parse them with legacy `new|0` fallback and rebuild the detail with that origin.
- GREEN evidence: status, Assign, Ask, stale-guard, Note, Reply, and Admin Ticket Back regressions ran together: `Ran 15 tests ... OK`. The test dispatches a real emitted status callback through the registered handler using an in-memory ticket fixture.
- Scope: `bot.py`, the existing focused origin regression module/CI command, tester case, support runbook, and this ledger. No production ticket, provider call, customer message, or wallet mutation.
- Delivery state: PR #1372 merged on 2026-10-06. GitHub reports `python_hygiene_and_tests` and `python-311-source-compile` SUCCESS. No deployment is authorized or included.

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
- Delivery state: PR #1375 merged on 2026-10-06 as `f9e2ea473617409194ad48498beab14b68c2e8dd`; `python_hygiene_and_tests` and `python-311-source-compile` passed. It has not been deployed.

### S12.11 — Anonymous timing coverage for registered callback handlers

- State: implemented locally on separate branch `fix/callback-dispatch-latency`, commit `c23e875250cbb153f5e2c2a1d1f109d4b1310ea8` (based on main `f9e2ea47`); not pushed and no PR/CI yet. Owner authorized a separate logging-only PR and deployment after CI. Latest release instruction is one PR at a time: after each merge, deploy and verify that exact merge SHA before merging/deploying the next PR. This branch's base already contains #1367–#1375; its eventual merge SHA therefore includes those ancestors, which must be stated as part of the release scope.
- Trigger/coverage: installer wraps all 87 pre-existing `CallbackQueryHandler` registrations after registration is complete, including the three shared negative-group guards, then adds a final observer. Source review found no `ConversationHandler` and no `CallbackQueryHandler(block=False)` path in this repo. Callback registration patterns and Python handler names are source-defined labels; full callback data is not read for logging.
- Log fields: `prefix`, `handler`, aggregate `guard_ms`, source-named `guard_phases`, `handler_ms`, `render_helper_ms`, `render_helper_calls`, `dispatch_ms`, and coarse `outcome`. `handler_ms` includes nested awaited work; `render_helper_ms` overlaps it and is not an additive phase.
- Privacy: the instrumentation does not log user/chat/message IDs, callback payload, message text, exception details, provider/job IDs, or secrets. Synthetic regression cases verify this for success, guard stop, and handler error.
- RED/GREEN evidence: the first run failed because the instrumentation API was absent; a second RED exposed missing per-guard attribution. Latest standard-library run with the Codex-bundled Python: `Ran 4 tests in 6.112s — OK`. `pytest` is unavailable (`No module named pytest`); test-file `py_compile` and `git diff --check` returned 0. Full `py_compile bot.py` produced no output after 60 seconds and was interrupted; no full local syntax pass is claimed. GitHub source-compile and hygiene/tests CI remain required.
- Coverage limit: `render_helper_ms` measures only the shared `safe_edit_query_message` await time; it is not client display/network time and excludes direct Telegram send/edit calls that bypass this helper. `dispatch_ms` is bot-process dispatch from the first guard to the final observer. Existing `callback_latency` records for `menu|main` and `menu|main_video` remain, so those two callbacks will emit a second, separately named `callback_dispatch_timing` record.
- Deploy-scope gate: last ledger runtime SHA is `4f1455ed31c3ebb4acbb6f6d3eff4144bf02185d`; recorded `main` `f9e2ea47` is 9 commits ahead, including PR #1369 Product Video and #1367–#1375 admin/UI changes. Before dispatch, re-read live SHA and current `main` SHA, pin the exact logger PR merge SHA, and verify no later merge has moved production ahead of that target. Do not claim the resulting deployment is logger-only; it carries its merged ancestors. Do not merge another PR until this SHA is verified live.
- Delivery gate: push as a separate PR; wait for both required CI checks. Only claim deploy/live after the target scope is authorized, deployment workflow succeeds, and VPS health/runtime SHA plus an anonymous event are verified. No Telegram click is simulated; server timings alone do not close A7 or identify client/network wait.

### Final latency spec — provisional runtime sample

- Logging implementation is in main via PR #1365; bot-only release #1366 targets runtime SHA `4f1455ed31c3ebb4acbb6f6d3eff4144bf02185d`.
- Read-only SSH observation this turn: `toanaas-bot.service` is `active/running`, `NRestarts=0`, runtime SHA `4f1455ed31c3ebb4acbb6f6d3eff4144bf02185d` matches the logger-only target. No restart or deployment was run this turn.
- Last-24-hour anonymous query returned one admin `menu|main_video` event at `2026-10-06T08:37:49+07:00`: `pre_ack_ms=0.023`, `ack_ms=222.983`, `language_ms=6.130`, `cleanup_ms=11.910`, `build_ms=2.088`, `render_ms=114.876`, `handler_ms=358.009`, `render_returned=1`.
- The same query returned no `menu|main` event. User-reported 2–3 second experience lacks an exact local timestamp, so the one Video event cannot be attributed conclusively to that click. It proves only that this measured server handler returned in 358.009 ms; it does not identify the remaining client/network wait or describe a distribution.
- Source coverage gap: shared callback guards run before `handle_menu_callback` starts the per-route timer. In particular, `safe_mode_callback_guard` calls `current_system_mode()`, which opens a DB connection and SELECT for each of seven flags. This is a concrete common-path cost candidate, but its live duration is not measured and it cannot yet be blamed for the delay. Existing route timers cover only `menu|main` and `menu|main_video`; other callback families and shared-guard time are uninstrumented.
- The existing #1365 logger measures only `menu|main` and `menu|main_video`; it does not include the three shared guards or other callback families. S12.11 adds a distinct `callback_dispatch_timing` record while retaining those prior records. A fresh SSH log query has not been performed in this spec; no new runtime measurement is claimed.
- Owner reports that the “Tạo video AI” and “Quay lại” buttons now feel smooth after the logging-only release. This is a qualitative user check without a timestamp or per-button duration, so it does not close A7 or establish latency for other button families.
- A grouped offline callback single-ACK suite across 24 files was started with `--noconftest`; it produced progress dots but no final summary after more than 90 seconds, while the Python process reached about 1.5 GB working set, so it was interrupted. No suite-wide pass/fail is claimed; the three-test route-specific suite above is the only current green evidence for the local change.
- No production action was performed during this check: no deploy, restart, provider call, real message, or wallet mutation.

## Next execution order

1. S12.6–S12.10 and A4 Home preemption closed in source: PRs #1367–#1375 merged with required checks green; they were not deployed by this audit.
2. Push S12.11 as a separate PR, require both CI checks, and merge only after CI is green.
3. Immediately deploy the exact merge SHA under the approved release scope; verify VPS runtime SHA, service health, and one anonymous event before starting another PR.
4. Continue A1/A2 with the next concrete admin Back/callback defect on current main; one route per spec, RED before minimal fix, then actual handler dispatch.
5. Continue A3/A4/A5 for customer and pending-state flows, preserving protected product lanes.
6. Finish A6 UI/UX consistency review and update this ledger with evidence, not assumptions.
7. Close A7 only after a user timing sample is correlated by local time/timezone; classify measured server and client/network phases separately.
8. Complete A8 only after all checklist rows have evidence and delivery states are separately verified.
