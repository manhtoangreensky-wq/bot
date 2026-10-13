# Telegram UI integration — 13/10/2026

## Latest follow-up — S12.35.403/.404

Full Linux CI #38350432275 and source compile #38350432301 passed on HEAD
`ab2eb614f6473d2a9e93af008bb7a5faedb9ee0a`. After that CI, a missing dedicated
registration was reproduced for the emitted Product Video
`vproduct|owner_live_accept` button. The exact owner handler route is now added
ahead of the generic Video route and excluded from the generic pattern. RED was
confirmed; route/dedupe tests now pass (`2 tests in 2.376s`). Source-compile
guard #38353329268 and full CI #38353329226 both passed on exact commit
`b3f91bb0e8b7a74fdc9d7255617624f384b2135b`, including its `Product Callback
Replay Guard Boundary` step. S12.35.395's four saved-plan SQLite tests were
added to the existing Linux Small Navigation step because local Windows pytest
did not return a result; that CI selection is pending push/run.

The existing handler can admit an Owner-authorized paid Product Video test.
No callback or Telegram event was dispatched and no job, invoice, provider,
wallet or production data was used. The route fix is pushed to draft PR #1426,
not merged or live. Other A3/
A5/A6 visual/dynamic route coverage, A7 latency, protected-source/runtime
reconciliation and the one-batch delivery gate remain open.

## Source and delivery state

Base: `e2b48f215f30a088156a1e29c1f402170274dcf0` (current GitHub main).
Branch: `audit/telegram-ui-integration-20261013`.
Candidate bot blob: `36cd263870c077a1115509d941b8b82a22e1a7be`.

The original audit checkout at HEAD `523d6c83` remains preserved. Its scoped
UI/test/document patch was checked and applied to this current-main worktree
without conflicts. Prior PR #1421 was already merged; this is a new batch.

## Scope review

Provider/service/worker/router/config/deploy paths have no changes against
the base. A source-function comparison lists these 26 changed functions:

`cmd_start`, `cmd_vault_prompt_library`, `cmd_vault_review`,
`free_hub_byok_text`, `free_hub_docs_keyboard`,
`free_hub_library_item_keyboard_for_parent`,
`free_hub_library_suggestions_keyboard_for_parent`, `free_hub_main_keyboard`,
`handle_doc_tool_callback`, `handle_free_hub_callback`,
`handle_image_menu_pending_document`, `handle_image_menu_pending_photo`,
`handle_image_tools_callback`, `handle_knowledge_vault_callback`,
`handle_manual_package_choice`, `handle_memory_callback`,
`handle_menu_callback`, `handle_package_choice`, `handle_payos_risk_callback`,
`handle_product_progress_callback`, `handle_public_video_status_callback`,
`handle_ticket_callback`, `handle_translation_callback`,
`image_edit_ai_choice_keyboard`, `resolve_support_ticket_once`,
`set_image_menu_pending`.

Their changes concern UI recovery, callback acknowledgement, pending input,
Back ancestry, Support Ticket replay/concurrency, and read scheduling. Callback
handlers in protected product areas change UI behaviour only; this comparison
does not claim live product output or prove every route visually smooth.
The source of the processing engines and main-only provider changes is preserved.

## New closure S12.35.402

Image hub AI entry returned to the local editing menu. RED reproduced it for
recent-image/photo/document intake, and again after option → Back → Back.
The candidate carries transient `ai_choice_origin` metadata and emits the correct
hub Back for that origin. Internal callers keep their prior default destination.

Actual root/AI/request keyboards, exact callback registrations, and production
pending setter/getter were executed. Latest result: `Ran 4 tests in 6.900s — OK`.
Adjacent Image/Prompt intake regressions: `Ran 2 tests in 3.708s — OK`.
Other-user pending state and recent image are preserved by the fixtures.

## Verification

- Complete `python -m py_compile bot.py`: exit `0` on this integrated source.
- Related pytest set: `19 passed, 16 subtests passed in 30.23s`.
- First complete 41-module workflow-selected navigation run:
  `44 failed, 256 passed, 66 subtests passed in 904.14s`.
- Root cause of those failures: test fixture omitted the newly present planner
  cleanup helper; Admin status fixture omitted the not-found translation and
  retained the superseded read-before-ACK/alert-only expectations.
- Cleanup fixture group rerun: `16 passed, 19 deselected, 7 subtests passed
  in 21.56s` (only previously failed cases selected).
- Admin action/status modules rerun: `46 passed in 25.84s`. Assertions retain
  single ACK, no writes on missing Ticket, recovery Back/Home, and ACK before read.
- Pytest last-failure cache is `{}` after these reruns. This proves the prior
  failure IDs were rerun successfully; a new full Linux CI run is still required.
- State and CI YAML parsed with existing cached PyYAML; `git diff --check` exit `0`.
- No provider, real Telegram, wallet/payment, production-data, ENV or runtime
  mutation was used. Fixtures are local and reject unexpected I/O where applicable.

## Runtime and remaining gates

Strict-host SSH read returns runtime SHA
`381c71bb9e52876eb35b15f5c417ca2cf833dc28`, bot blob
`d7e4f3da4f07c326571084dcdb5d45e6053090eb`; bot/web/nginx are active/running,
`NRestarts=0`. Main's protected #1424 delta is not on runtime. A main deploy would
include that delta, so delivery requires review of it in addition to this UI batch.

This batch is on draft PR #1426 and requires complete CI. Merge/deploy remain separate gates.
Remaining A3/A5/A6 visual/dynamic coverage and A7 client timing are open. The goal
must stay active; no claim of complete bot audit or all-button smoothness follows.

Tester cases and operating-document updates are linked from
`KIEM-THU/DANH-SACH-CASE.md`, `KIEM-THU/HUONG-DAN-TESTER.md` and the two
`TAI-LIEU` operating documents. Existing GitHub tester labels and UI issue template
were verified; no new issue or Projects object was created.

## PR #1426 — first Linux run and fixture follow-up

Draft PR: https://github.com/manhtoangreensky-wq/bot/pull/1426.
Initial tested HEAD: `53a18c67d3d3e15762010a4e704ae171bacbae5c`.

- Source compile guard #38347923052 succeeded. Main CI #38347923041 completed
  complete-source compile, Python compile and Media Preview successfully, then
  failed in Admin Package Orders because its source-extracted Menu fixture had
  not supplied `_local_video_planning_clear_pending`.
- The same test-only dependency was supplied in independent Admin Package,
  Security/DB, denied-menu and Finance fixtures. Result: `9 passed,
  8 subtests passed in 21.04s`.
- Home/start fixture owners were checked for both new cleanup dependencies;
  relevant Broadcast, Document, Archive, Memory and Storage fixtures now provide
  their unrelated no-op seams. Result: `5 passed, 22 subtests passed in 71.36s`.
- Customer Done fixture separately reproduced missing `resolve_support_ticket_once`:
  `1 failed, 3 passed, 17 subtests passed`. Its owner-scoped once-only fixture
  seam preserves the original write/ACK assertions; GREEN: `3 passed,
  18 subtests passed in 7.75s`.
- The actual SQLite replay/concurrent regressions also passed: `2 passed
  in 51.13s`. This avoids relying solely on the Customer-action fixture stub.
- All follow-up source changes are test-only. `bot.py` blob remains
  `36cd263870c077a1115509d941b8b82a22e1a7be`; the complete-source compile result
  still applies to that exact blob. A new complete CI run is required after push.
- Codex PR attachment was attempted but the app returned
  `thread attachment identity count exceeds 100`; the PR is available by URL.

## Second Linux run — remaining Admin fixture namespaces

HEAD `a8dbd278e639521e2e8971f68b8078c6948d60b6`:
source compile #38349346631 succeeded. CI #38349346656 passed Package Orders
and Security/DB, then Admin Route completed 200 tests with 5 fixture errors.

The errors were missing `asyncio` in Ask/Note source-extracted namespaces and
missing `is_admin_user` in the customer-category fixture. The three namespaces
now provide their existing production dependencies. The Ask branch fixture also
stops adding a synthetic ACK before the actual branch and asserts exactly one
answer for valid/stale paths. No product-source changes were required.

Exact failed-case rerun: `Ran 5 tests in 13.174s — OK`. The original operation,
Back and pending-state assertions remain. The next full Linux run is still
required; no whole-workflow success is claimed from this narrow rerun.
