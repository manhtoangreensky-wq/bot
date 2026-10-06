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
| A0 | Pin source baseline and enumerate static/dynamic callbacks. Main baseline: `4f1455ed31c3ebb4acbb6f6d3eff4144bf02185d`; inventory reports 3,981 button constructors, 83 static handler patterns, 0 unmatched static callbacks, and 821 dynamic callback expressions. Counts do not prove route correctness. | Baseline captured; dynamic paths still require route evidence. |
| A1 | Admin screens: verify each visible action label matches its handler; test emitted callback, authorization, state transition, and error/stale path. | OPEN — audit ledger not complete. |
| A2 | Admin Back/Home: verify immediate parent and preserve list/filter/page context; test prompt and preview exits without performing the underlying action. | IN PROGRESS — S12.6 has local code and focused tests; delivery gate open. |
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
- Delivery state: local branch `fix/admin-ticket-reply-origin-pagination`, based on `4f1455ed…`; committed locally, but not yet pushed or opened as a PR. This Admin Ticket change is separate from the logger-only PRs #1365/#1366 and is not authorized for deployment by the logging approval.
- Verification limitation: the bundled Python has no `pytest` module. Full `py_compile bot.py` consumed over six minutes of CPU without returning; that run was interrupted and has no pass/fail verdict. The focused harness compiled/executed the modified route functions. `ci-main.yml` now invokes the focused `unittest` regression on PRs; the separate `bot-source-compile` workflow supplies the full-file compile/tokenize gate. Do not merge this spec until both required PR checks are green.

### Final latency spec — provisional runtime sample

- Logging implementation is in main via PR #1365; bot-only release #1366 targets runtime SHA `4f1455ed31c3ebb4acbb6f6d3eff4144bf02185d`.
- Read-only VPS observation: `toanaas-bot.service` is `active/running`, `NRestarts=0`, runtime SHA matches the target.
- Last-24-hour anonymous query returned one admin `menu|main_video` event at `2026-10-06T08:37:49+07:00`: `pre_ack_ms=0.023`, `ack_ms=222.983`, `language_ms=6.130`, `cleanup_ms=11.910`, `build_ms=2.088`, `render_ms=114.876`, `handler_ms=358.009`, `render_returned=1`.
- The same query returned no `menu|main` event. User-reported 2–3 second experience lacks an exact local timestamp, so the one Video event cannot be attributed conclusively to that click. It proves only that this measured server handler returned in 358.009 ms; it does not identify the remaining client/network wait or describe a distribution.
- No production action was performed during this check: no deploy, restart, provider call, real message, or wallet mutation.

## Next execution order

1. Push S12.6 as its own PR to run the focused route regression plus full-source compile/tokenize checks; merge only when those PR checks are green under the existing ordered-PR authorization. No deployment is implied.
2. Continue A1/A2 with the next concrete admin Back/callback defect found on current main; one route per spec, RED before minimal fix, then actual handler dispatch.
3. Continue A3/A4/A5 for customer and pending-state flows, preserving protected product lanes.
4. Finish A6 UI/UX consistency review and update this ledger with evidence, not assumptions.
5. Re-run A7 after a user timing sample can be correlated by local time/timezone; classify only from measured phases.
6. Complete A8 only after all checklist rows have evidence and delivery states are separately verified.
