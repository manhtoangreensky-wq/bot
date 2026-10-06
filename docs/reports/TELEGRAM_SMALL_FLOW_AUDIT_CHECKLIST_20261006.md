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
| A0 | Pin source baseline and enumerate static/dynamic callbacks. Inventory snapshot: `4f1455ed31c3ebb4acbb6f6d3eff4144bf02185d`; current main after S12.8 merge: `e954fcaef968a421e8628428d733f99ec7ee275c`. Snapshot reports 3,981 button constructors, 83 static handler patterns, 0 unmatched static callbacks, and 821 dynamic callback expressions. Counts do not prove route correctness and have not yet been refreshed after the merges. | Baseline captured; dynamic paths still require route evidence. |
| A1 | Admin screens: verify each visible action label matches its handler; test emitted callback, authorization, state transition, and error/stale path. | OPEN — audit ledger not complete. |
| A2 | Admin Back/Home: verify immediate parent and preserve list/filter/page context; test prompt and preview exits without performing the underlying action. | IN PROGRESS — S12.6 #1367, S12.7 #1368, S12.8 #1370 merged; S12.9 Assign origin regression is green locally and awaiting its own PR gate. |
| A3 | Customer screens: verify ownership, same-product navigation, Back/Home, and no cross-user or cross-product route. | OPEN — audit ledger not complete. |
| A4 | Pending input: verify `/start`, `/menu`, Back, expiry, stale controls, repeated presses, and abandoned drafts clear only the intended state. | OPEN — audit ledger not complete. |
| A5 | Callback coverage: check static and dynamic emitted values against actual registrations and dispatched terminal behavior; no module-only route test counts as completion. | OPEN — static unmatched count alone is insufficient. |
| A6 | UI/UX consistency: inspect admin/customer button labels, duplicated actions, misleading guide/status labels, row density, and recovery copy; propose or implement only narrow approved fixes. | OPEN — audit ledger not complete. |
| A7 | Final latency diagnosis (last, after route checks): correlate anonymous server phases with a timed user click; separate callback acknowledgement, local build/cleanup, Telegram render, and client/network wait. Report measured distribution and limits; do not guess hardware/network purchases from an uncorrelated sample. | PARTIAL — one server event below; needs a timestamp-correlated sample and additional events. |
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
- Delivery state: local implementation verified; PR/CI gate pending. No deployment is authorized or included.

### Final latency spec — provisional runtime sample

- Logging implementation is in main via PR #1365; bot-only release #1366 targets runtime SHA `4f1455ed31c3ebb4acbb6f6d3eff4144bf02185d`.
- Read-only SSH observation this turn: `toanaas-bot.service` is `active/running`, `NRestarts=0`, runtime SHA `4f1455ed31c3ebb4acbb6f6d3eff4144bf02185d` matches the logger-only target. No restart or deployment was run this turn.
- Last-24-hour anonymous query returned one admin `menu|main_video` event at `2026-10-06T08:37:49+07:00`: `pre_ack_ms=0.023`, `ack_ms=222.983`, `language_ms=6.130`, `cleanup_ms=11.910`, `build_ms=2.088`, `render_ms=114.876`, `handler_ms=358.009`, `render_returned=1`.
- The same query returned no `menu|main` event. User-reported 2–3 second experience lacks an exact local timestamp, so the one Video event cannot be attributed conclusively to that click. It proves only that this measured server handler returned in 358.009 ms; it does not identify the remaining client/network wait or describe a distribution.
- The newly approved logging-only request was checked against source and prior runtime release evidence: #1365 already emits separate timing records for `menu|main` and `menu|main_video`, and #1366 deployed that logger to runtime SHA `4f1455ed31c3ebb4acbb6f6d3eff4144bf02185d`. No duplicate logger PR or deploy was needed. A fresh SSH log query was blocked this turn because the key was inaccessible and no trusted host key was available; no new runtime measurement is claimed.
- No production action was performed during this check: no deploy, restart, provider call, real message, or wallet mutation.

## Next execution order

1. S12.6–S12.8 closed: PRs #1367, #1368, and #1370 merged with required checks green; none of these Admin Ticket changes was deployed.
2. Open the separate S12.9 PR and require its focused route regression plus full-source compile/tokenize checks before merge; no deployment is implied.
3. Continue A1/A2 with the next concrete admin Back/callback defect found on current main; one route per spec, RED before minimal fix, then actual handler dispatch.
4. Continue A3/A4/A5 for customer and pending-state flows, preserving protected product lanes.
5. Finish A6 UI/UX consistency review and update this ledger with evidence, not assumptions.
6. Re-run A7 after a user timing sample can be correlated by local time/timezone; classify only from measured phases.
7. Complete A8 only after all checklist rows have evidence and delivery states are separately verified.
