# Telegram UI integration — 13/10/2026

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

This batch is prepared for a draft PR and CI. Merge/deploy remain separate gates.
Remaining A3/A5/A6 visual/dynamic coverage and A7 client timing are open. The goal
must stay active; no claim of complete bot audit or all-button smoothness follows.

Tester cases and operating-document updates are linked from
`KIEM-THU/DANH-SACH-CASE.md`, `KIEM-THU/HUONG-DAN-TESTER.md` and the two
`TAI-LIEU` operating documents. Existing GitHub tester labels and UI issue template
were verified; no new issue or Projects object was created.
