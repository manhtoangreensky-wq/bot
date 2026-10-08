# Telegram Bot Small-Flow Audit — Checklist & Evidence Ledger

Status: ACTIVE — do not treat this file or any isolated green test as whole-bot completion.

Latest delivery evidence (08/10/2026): PR #1410 merged at `87bf32064473b02ee32aa6a6b63997ae3ef9b533`, CI run `37723283055` passed, bot-only deploy run `37727154776` succeeded. Follow-up PR #1411 merged at `ea516e37c1e482b5cb8708d5b7591cf93c1ecfcc`; CI runs `37733054155` and `37733054147` passed, and its bot-only deploy `37733818022` succeeded with `deploy_workers=false`. A later independent workflow dispatch `37736313510` targeted the same SHA but used `DEPLOY_WORKERS=true`: worker repo advanced from `76f0454f…` to `ea516e37…`, deploying the #1409 Product Video `services/video_provider_router.py` delta and reconciling/restarting the SubDub worker. VPS readback confirms bot/web/nginx/Product Video worker/SubDub worker active, all `NRestarts=0`; internal `127.0.0.1:8080/health` returned `status=ok`. Therefore current runtime is not UI-only, although the UI PRs themselves contain no engine edits. This audit did not initiate the worker-inclusive run and did not call providers or validate product output. The whole-bot audit remains ACTIVE because A3/A5/A6/A7 are partial. Account → Back is still reported at 2–3 seconds without a matched client/server sample; do not claim all-button smoothness or zero defects.

## Scope locks

- Audit emitted Telegram buttons through their registered callback/message handlers; verify source, target, state, Back/Home destination, repeat/expiry behavior, and side effects.
- Keep the AutoPost WIP untouched. Do not refactor the shared router or alter stable Product/Edit/SubDub/Voice/Music engine behavior.
- No secrets, production user data, wallet changes, paid provider calls, real customer messages, restart, merge, or deployment without the applicable owner approval.
- Static callback counts are inventory evidence only; a route is complete only after exercising the emitted control through its registered handler.

## Ordered checklist

| ID | Spec / acceptance evidence | State |
|---|---|---|
| A0 | Audit comparator baseline: `93919f93d7207f252252f10f9c03d1e8a2d458f8` after Admin Finance renderer PR #1408; bot blob `b0886d443b8b26e593be5e5efdc421f4ab2e1fbf`. Exact-SHA bot-only deploy #37599864501 succeeded (`deploy_workers=false`); strict-host SSH verified exact bot source, bot/web/nginx active, `NRestarts=0`, and `/health` `status=ok`. Fresh read-only check at 2026-10-08 00:18:30 +07 found GitHub main and VPS at `76f0454fbab5e467f9ca71a0135b6fd05d8d70c4`; versus this audit base, the one intervening commit changes only `services/remote_worker_api.py` and its focused test (separate Product Video worker-authority work, not this UI audit). Current bot service is active/running with `NRestarts=0`, and deployed `bot.py` contains the anonymous callback timing instrumentation. The audit branch remains based on `93919f9` and was not rebased or overwritten. Historical AST registration inventory at `0929d61a` measures 87 direct registrations, 85 distinct expressions and 83 literal patterns; the old emitter snapshot `4f1455ed` had 3,981 constructors/821 dynamic expressions/0 unmatched static callbacks. These inventories and old line locations do not prove current route behavior. |
| A1 | Admin screens: verify each visible action label matches its handler; test emitted callback, authorization, state transition, and error/stale path. | ADMIN UI ROUTE MATRIX VERIFIED OFFLINE — Admin Control Center destinations, module guide callbacks, report/read-only paths, scoped child entries, feedback/access, Broadcast Lite, Marketing/Affiliate, Ticket, and System/Operator/Provider routes have emitted-control → registered-handler evidence using inert seams. S12.35.26 verifies Data Status/Backup DB/Health are honestly labeled as guides; S12.35.27 verifies the System Provider Status route. Buttons that hand off to an operator command are tested as guide/command handoffs only; payment/wallet/freeze/provider mutations were not executed. Manual Telegram rendering/visual QA remains NOT_TESTED and A7 latency is still open. |
| A2 | Admin Back/Home: verify immediate parent and preserve list/filter/page context; test prompt and preview exits without performing the underlying action. | ADMIN ROUTE BACK MATRIX VERIFIED OFFLINE — ticket-origin specs S12.6–S12.10 (#1367–#1374) are in #1376; S12.12 merged/deployed in #1378; S12.18 Package Orders and S12.19 Security/DB origin fixes are deployed. S12.35.6–13, .20–22, .24–28 cover Finance, Marketing, Queue/Package, Security/DB, Support/Ticket, Broadcast Lite, legacy System/Operator and System → Provider Status round-trips using the registered handlers; .59 verifies Admin Notes → Internal Archive → Back to Notes through the registered menu handler. Stateful payment/provider/worker/archive-data actions were not run. Manual Telegram visual/client confirmation is NOT_TESTED; latency measurement remains A7. |
| A3 | Customer screens: verify ownership, same-product navigation, Back/Home, and no cross-user or cross-product route. | PARTIAL — Account Pricing/member, Support/Ticket, credit guide, packages/referrals and Top-up have scoped evidence. S12.35.3 covers 25 emitted Top-up→Back paths and is merged/deployed. S12.35.4 is merged/deployed at runtime SHA cfbeb530762526df148de351a8714815119b5db1; 20/20 focused handler tests verify direct /pricing_xu command ancestry. S12.35.14/.29/.34/.37/.38/.40/.41/.43/.44/.45/.46/.47/.51/.52/.57/.58/.60/.61/.62/.65/.66/.67/.68 dispatch selected public-root and account/support/language/image/notes/docs/guide/feedback/pricing/Storage Add-on/Ticket/package/Memory/Free Tools controls through registered handlers; .37 verifies Chat Pro info → Home; .38 verifies Account root/children; .40 covers root/account/credit-guide/support/language; .41 verifies Image landing → Home without entering a tool; .43 verifies Notes → Documents → Back/Home without opening tools; .44 verifies Guide landing → Home; .45 covers Memory pending reset plus Feedback/Language accepted/rejected paths; .46 covers Feedback category → prompt Back/Home and Cancel → Home; .47 ran Account Pricing/member/Top-up regressions (13 tests); .51 reran the public/Admin root menu suite (11 tests); .52 verified all seven Guide articles and corrected only the Guide-origin Video article Back while preserving the legacy Video-origin destination; .57 verifies Memory empty-delete state cleanup and Document Back routes; .58 verifies Storage Add-on custom-input Back and the Notes parent target without payment; .60 verifies customer-owned Ticket list/detail/prompt ancestry and wrong-owner/malformed rejection without sending or writing; .61 dispatches emitted “Gói Ảnh” → Back to Gói/Combo; .62 verifies empty-delete → Back returns to Notes/Docs; .65/.66 preserve saved-list and Delete-picker origins; .67 restores the exact search-result list after detail/Cancel and rejects stale/foreign tokens; .68 verifies Free Tools → Prompt Library → Back to Free Tools → Home through registered handlers. Stateful/tool terminals and protected processing remain explicitly untested, not passed. Manual Telegram client QA remains NOT_TESTED. |
| A4 | Pending input: verify `/start`, `/menu`, Back, expiry, stale controls, repeated presses, and abandoned drafts clear only the intended state. | VERIFIED FOR IN-SCOPE SMALL NAVIGATION/PENDING FLOWS — ReplyKeyboard Home preemption PR #1375 is already deployed in #1376; S12.35.15–19 cover FreeHub maintenance, `/start`/`/menu` pending release, owner TTL, stale Archive Save, Support expiry, Document/Downloader exits and saved-draft preservation. S12.35.30 covers current-branch stale/repeat/back behavior. S12.35.31 reran seven pending/expiry regressions (`Ran 7 tests in 13.082s — OK`) plus four direct Start/Menu pending-cleanup checks (`4 direct pending-cleanup checks — OK`). S12.35.57 rechecks empty Memory Delete clears stale pending and document-tool Back/page-prompt exits through the registered callback; .58 confirms the Storage Add-on custom draft is cleared by its Back button; .62 verifies the emitted empty-delete route clears only the Memory draft and its Back returns to Notes/Docs; .68 verifies Prompt Library Back clears only FreeHub's pending marker. AutoPost WIP input semantics and engine-owned product/job pending state are explicitly excluded; the Home-label priority behavior remains as delivered and tested in #1375. |
| A5 | Callback coverage: check static and dynamic emitted values against actual registrations and dispatched terminal behavior; no module-only route test counts as completion. | PARTIAL — current main-menu emitter produced 14 public and 15 admin callback values; each matches a registered literal callback pattern and every value is ≤64 UTF-8 bytes (S12.35.33). S12.35.14/.29/.31/.34/.37/.38/.40/.41/.43/.44/.45/.46/.47/.51/.52/.57/.58/.59/.60/.61/.62/.65/.66/.67/.68/.82/.83 add registered-handler evidence for selected emitted root/account/support/guide/language/image/notes-docs, Account Packages/referral read-only children, Feedback/Language, Account Pricing/member/Top-up, Document, Storage Add-on, Memory empty-delete, Internal Archive type screen, Admin Internal Archive, customer Ticket, package group, saved-list, delete-picker, search-result, and Free Tools prompt-picker navigation callbacks; .41/.43/.44 cover UI landing/back only, not tool/article terminals; .46 adds Feedback category/cancel terminals with Back/Home assertions; .51 reran the safe root menu/callback suite (11 tests in 6.271s); .52 dispatches all seven Guide articles and asserts Guide/Main destinations plus preservation of legacy Video-origin Back (13 tests). S12.35.45/.57 cover Memory pending cleanup; .58 verifies Storage Add-on custom Back and the registered handler; .59 dispatches Admin Notes → Internal Archive → Back to Notes; .60 verifies owned Ticket ancestry plus malformed/foreign rejection; .61 dispatches the emitted Image package group and its Back through the registered package handler; .62 dispatches emitted Memory empty-delete and its Back through the registered Memory/Menu handlers; .65/.66 verify saved-list and delete-picker origin; .67 verifies search → detail → Cancel → exact search results, stale/expired/foreign rejection and callback byte bounds; .68 dispatches Free Tools root → prompt picker → Back → Home. S12.35.82/.83 add the emitted Account → Packages → Account and three referral read-only child Back/Home round-trips through the registered `menu|` handler; they are now included in merged PR #1411 and runtime `ea516e3…`. Remaining untested dynamic terminals perform stateful/data-changing actions or enter protected processing lanes; they are explicitly not claimed as verified in this UI/navigation batch. |
| A6 | UI/UX consistency: inspect admin/customer button labels, duplicated actions, misleading guide/status labels, row density, and recovery copy; propose or implement only narrow approved fixes. | PARTIAL — S12.35.35/.39 aligned four stale 7-row test contracts with the current 8-row menu without changing production layout; .36 corrected three stale Railway references in Owner setup UI to match VPS. S12.35.51 records the source structure: public root is 8 rows (one single action, seven paired rows), with 14 callback buttons and one community URL; Admin adds one final row. S12.35.52 corrects Guide-origin Video Back; .53 aligns the Vietnamese Guide “Admin” label with its actual Support destination; a source sweep found no other label/callback mismatch in the Guide topics/downloads/Back/Home. Existing A1/A2 specs cover many misleading Admin guide labels and Back paths. S12.35.48 source review matches the requested $100 baseline / warning strictly below $10, with a six-hour reminder cooldown; the provider endpoint and real admin message were not exercised. Source alone does not prove viewport wrapping/scroll or visual polish; Telegram visual/client QA and remaining copy/layout review remain NOT_TESTED. |
| A7 | Final latency diagnosis (last, after route checks): correlate anonymous server phases with a timed user click; separate callback acknowledgement, local build/cleanup, Telegram render, and client/network wait. Report measured distribution and limits; do not guess hardware/network purchases from an uncorrelated sample. | PARTIAL — eight deterministic root Video/Home timing scenarios run (S12.35.32); anonymous timing-instrumentation fixture passed 4 tests in 7.490s (S12.35.49). Owner again reports Account → Back takes about 2–3 seconds, including this turn, but no exact `HH:MM:SS +07` click time was supplied. Prior strict-host queries had no callback timing event that can be tied to this click. The 2–3s remains a user-reported end-to-end estimate, not a server measurement or cause diagnosis. Older Main/Video samples are insufficient for an all-button distribution. No client/network fault or purchase is inferred. |
| A8 | Closeout: run focused regressions, required syntax/tests, diff/scope review; collect scoped fixes on one batch PR and merge/deploy once after the complete ordered checklist, with live verification separate. | PARTIAL — UI PR #1410/#1411 and their bot-only deliveries are verified. A later worker-inclusive dispatch at the same SHA also updated Product Video worker state; see S12.35.84. Whole-goal closeout remains OPEN until A3/A5/A6/A7 evidence gaps and final scope/delivery review are complete. |

Latest A3/A5 delta (S12.35.90–.103): Ticket reply/file guards, SubDub navigation-only Back, Voice Hub Back/Home, Ticket category-prompt Back, public Translation root → language hub → Back/Home, Free Tools rate/QR/Avatar/weather/suggestion routes, and Notes/Docs origin-aware Back are recorded in their individual specs. S12.35.95 finds the primary public general-support form is reachable, while the separate category chooser lacks a public entry; no behavior change is made pending Owner direction.

A6 source-only continuation (2026-10-08): Billing command-guide labels and emitted risk-menu Back passed 6 focused tests in 12.726s; Finance action/report labels, origin, authorization and Back passed 9 tests in 83.266s; System/Provider/Operator read-only guide and Back round-trips passed 4 tests in 29.083s; Admin Overview rendered its report page and emitted navigation in 1 actual-handler fixture test (0.160s). These are handler/keyboard fixtures, not Telegram viewport or customer-device visual QA.

Account layout source recheck (S12.35.63): the Account root is six rows (five paired action rows plus one Main-menu row); Account-child screens use one paired row with Back to Account and Home to Main. Their callback destinations match the previously dispatched routes in S12.35.1/.38. Source review cannot establish Telegram client wrapping, scroll behavior or visual polish.

A3/A5 boundary supplement (S12.35.64): the public-root Studio âm thanh callback, its landing screen, and the emitted Back/Home controls now have registered-handler fixture evidence. This covers navigation only; no Voice/Music child action or engine is included.

A3/A5 safety boundary (S12.35.86): `progress|status` is not uniformly read-only. The Music branch delegates to a helper that can refresh/poll and deliver an existing artifact; the SubDub branch can recover an existing MP4 and send its receipt. No callback was dispatched in this UI audit. Keep these product-state actions with their owning engine task; do not treat them as safe UI-only button tests.

A3/A5 supplement (S12.35.65): the actual Saved Notes keyboard emits a list-origin detail callback. Registered-handler fixtures verify detail Back and delete-confirm Cancel preserve the immediate saved-list ancestry. Note reads use owner-scoped fixtures; no production note access or mutation occurred. This closes only that route slice, not Memory CRUD or other dynamic terminals.

A3/A5 supplement (S12.35.66): the emitted Delete-picker choice carries its parent into confirmation; Cancel is dispatched through the registered handler and returns to the same picker. The destructive confirm edge remains untested.

A3/A5 supplement (S12.35.67): search-result note details now carry an ephemeral per-user token and result ID snapshot. Back restores that exact result list; the Cancel path from delete confirmation preserves the same search origin. Expired, mismatched or foreign-user tokens fail closed to the Memory root. Fixture traversal verifies callback payloads remain ≤64 UTF-8 bytes, including maximum signed SQLite ID and a 19-digit token. No production DB or destructive action was used.

A3/A4/A5 supplement (S12.35.73): the emitted Free Tools “Prompt ảnh/video” entry opens the local suggestion screen through the registered FreeHub handler. Its Back returns to Free Tools, clears only the current owner's pending marker, and leaves another user's marker unchanged. The suggestion builder ran on fixture data only; no prompt was selected or processed.

A3/A4/A5 supplement (S12.35.74): the emitted Free Tools “Lưu tệp tạm” entry opens its upload prompt through the registered FreeHub handler. Back returns to Free Tools, clears only the current owner's upload-pending marker, and preserves another user's marker. No file was sent or processed.

A3/A4/A5 supplement (S12.35.68): actual public-root Free Tools → registered FreeHub → static Prompt Library picker → Back → Free Tools → Home → registered Menu → Main all dispatch correctly. The fixture confirms only FreeHub's pending marker is cleared; quota/suggestion seams are inert, with no generation/input/upload/provider/payment/job/AutoPost action. No production change was required.

A3/A4/A5 supplement (S12.35.69): the separate Kho Prompt library path was traced through the public-root Free Tools entry, registered FreeHub handler, library/category keyboard, and category-suggestions Back. The Back previously skipped Kho Prompt and returned to Free Tools; it now returns to the category menu through the existing `freehub|library` route and clears only FreeHub pending state. The prompt library remains local/inert in the route fixture.

A3/A4/A5 supplement (S12.35.70): selecting a local prompt then pressing Back previously returned to Free Tools and discarded the visible list context. The detail Back now routes to `freehub|lib_back`; that handler restores the exact prior result IDs/text without rerolling the prompt library. No prompt-generation, save, provider, or engine action is exercised.

A3/A4/A5 supplement (S12.35.71): the static Tiện ích chooser is reached from the actual Free Tools menu and its Back dispatches to Free Tools. The four utility choices are inventoried and registration-matched, but rate, weather, QR, and avatar actions were deliberately not invoked.

A3/A4/A5 supplement (S12.35.72): the Free Tools menu's text-translation prompt is reached through its actual emitted button and registered FreeHub handler. Back returns to Free Tools and clears only the FreeHub input marker; the translation input/provider path was not invoked.

A6 observation (S12.35.64): the Studio âm thanh landing currently emits both “Quay lại” and “Trang chủ” to the same `menu|main` destination. This is a redundant UI control, not a navigation failure. It remains unchanged because the Music/Voice UI lane is explicitly protected from edits in this batch.

A6 update (S12.35.65): on saved-list-origin note detail, “Back” now returns to “Ghi chú đã lưu”; the redundant shortcut to the same list is omitted on that screen. Legacy detail screens keep their previous Notes/Documents Back.

A6 update (S12.35.66): on confirmation reached from the Delete picker, Cancel returns to that picker and the misleading alternate “Ghi chú đã lưu” shortcut is omitted. The actual delete action is not part of this UI test.

A6 update (S12.35.67): on a note opened from search results, Back now targets the originating result set instead of Notes/Documents; the delete-confirm Cancel path retains that same origin. Existing saved-list, delete-picker and command-driven Memory Back behavior stays unchanged.

## Current evidence

### A1 — Admin operational surface (partial)

- Prior focused evidence: Admin Overview callback and report-source tests passed (one test each); a read-only handler simulation covered monthly/yearly reports, authorization before report read, and invalid period (4 assertions).
- Admin root/help/package evidence: admin root and help tests (2 + 3) and package-storage guide tests (2) passed. Admin feedback/access checks covered emitted destinations, read-only inbox query/no commit, handbook rendering, admin guard, and public denial (6 focused cases); a stale fake helper signature was corrected in the local test fixture.
- Current batch audit: the actual Admin Control Center “💰 Tài chính” button is dispatched through the registered `menu|` handler and reaches the Finance hub with its overview child and Admin Back. Regression: `test_admin_control_center_finance_button_opens_finance_hub` → 1 test OK. This supplements the Finance page-action tests; it does not claim every root action is covered.
- Current root-route audit: the actual `menu_nav_keyboard("admin", True)` emitter produced the full 12-button Admin Control Center; its 10 `menu|admin_*` destinations dispatched through the registered menu handler to the expected module heading and `menu|admin` Back. The separate Marketing/Affiliate callback opened its cockpit through the registered `admin_growth|` handler, returned to Admin, and denied a public user before the inert report seam. Two fixture-only tests pass; the other Admin action/error-state matrix remains open.
- Current S12.12 route test exercises the real configured `ADMIN_CONTROL_MODULES` keyboard builders and registered-help callback body; it does not exercise every non-guide admin action or every state-changing handler.
- Scoped Admin callback/guide/read-only path coverage is now represented in the matrix above and its linked specs. No payment, wallet, provider/worker, destructive DB operation, user-data mutation, or production message was performed; do not infer those operations work from the UI-route evidence.

### S12.24.1 — Provider/Worker route label matches its destination

- Emitted control: `ADMIN_CONTROL_MODULES["provider_worker"]` creates “🧾 Route/Group Info” → `menu|admin_provider_routes|admin_provider_worker`.
- Registered route: `handle_menu_callback` accepts the validated `admin_provider_worker` origin and renders `admin_provider_routes_text`, whose page heading is “Route/Group Info”.
- RED: the focused source-extracted test observed the old button label “🎬 Video job” while the registered destination rendered Route/Group Info.
- Fix: change only that button label. No callback, provider state, command, provider call, or execution path changed.
- GREEN: `test_admin_module_child_back_origin.py` → 4 tests OK; `test_admin_billing_guide_labels.py` → 3 tests OK; `python -m py_compile bot.py tests/test_admin_module_child_back_origin.py` exited 0; `git diff --check` exited 0 (Git reports only the existing LF→CRLF working-copy warning for the test file).
- Delivery: [PR #1389](https://github.com/manhtoangreensky-wq/bot/pull/1389) merged at `54ee434aab7c44b09af793bdb7dd9764976cf3bd`; required CI checks SUCCESS. Exact-SHA bot-only deploy [37524980913](https://github.com/manhtoangreensky-wq/bot/actions/runs/37524980913) SUCCESS (`deploy_workers=false`). SSH confirms runtime SHA/source match, bot/web/nginx active, all `NRestarts=0`, health `status=ok`. [PR delivery evidence comment](https://github.com/manhtoangreensky-wq/bot/pull/1389#issuecomment-6024706054).
- Manual Telegram/client QA remains NOT_TESTED; other A1/A2 routes remain open.

### S12.24.2 — Package controls identify command-guide destinations

- Emitted buttons from the registered Admin → Gói/Combo module were labeled “Catalog gói”, “Cấp combo”, “Cấp tháng”, and “Gói của user”.
- The registered menu handler rendered command instructions (`/package_catalog`, `/grant_combo`, `/grant_monthly`, `/user_packages`) rather than executing those operations or displaying user/package records.
- RED: four subcases failed against the observed labels before the correction.
- Fix: prefix each of those four buttons with “Hướng dẫn…”; callback payloads stay unchanged. Storage, order, and other actions are unchanged.
- GREEN: source-extracted test opens Admin → Gói/Combo through the registered menu callback, dispatches each emitted guide button, verifies the command and emitted Back to Gói/Combo, then presses Back. Five Admin module tests and two Package Orders origin regressions pass; `python -m py_compile bot.py tests/test_admin_module_child_back_origin.py` and `git diff --check` pass.
- Delivery: [PR #1390](https://github.com/manhtoangreensky-wq/bot/pull/1390) merged at `1f1b035edb225f8fef6b475836c75f6c7b609a81`; both required checks SUCCESS. Exact-SHA bot-only deploy [37528116347](https://github.com/manhtoangreensky-wq/bot/actions/runs/37528116347) SUCCESS (`deploy_workers=false`). SSH confirms runtime SHA/source match, bot/web/nginx active, all `NRestarts=0`, health `status=ok`. [PR delivery evidence comment](https://github.com/manhtoangreensky-wq/bot/pull/1390#issuecomment-6025092937).
- Manual Telegram/client QA remains NOT_TESTED; other A1/A2 routes remain open.
- Business-operation, wallet, production-data and provider calls: 0.

### S12.24.3 — Queue command-guide controls do not claim an action was confirmed

- Trigger: Admin → Queue → Freeze Video / Unfreeze Tool / Refund Job prompt.
- Evidence: the actual emitted control dispatched through registered `handle_menu_callback`. Each “✅ Xác nhận” callback only rendered a page instructing the admin to send a slash command manually; it did not run the command. That page nevertheless said “Đã xác nhận thao tác admin”, which implied a completed action.
- RED: the registered-handler regression failed on the same misleading CTA in all 3 Queue cases before production text was changed; there were no setup errors.
- Fix: change the CTA to “📋 Xem lệnh cần chạy” and the result heading to “Hướng dẫn thao tác admin”. Callback payloads, commands, authorization, Cancel/Back routes and all operational handlers are unchanged.
- GREEN: `tests/test_admin_queue_confirm_back_origin.py` → 5 tests OK; adjacent `tests/test_admin_module_child_back_origin.py` → 5 tests OK. PR CI, main CI and full-source compile passed.
- Scope: two UI strings, one focused callback assertion and one existing label assertion. The manual command is never executed by this callback. No provider, wallet, database, production-data, job or real Telegram side effect.
- Delivery: PR [#1391](https://github.com/manhtoangreensky-wq/bot/pull/1391) merged; bot-only deploy [#37532325983](https://github.com/manhtoangreensky-wq/bot/actions/runs/37532325983) succeeded. SSH verified runtime SHA `d05c2ae034f23c7808f3a739e98ebe4826634e40`; bot/web/nginx active, `NRestarts=0`, health `status=ok`. [Delivery evidence](https://github.com/manhtoangreensky-wq/bot/pull/1391#issuecomment-6025641399). Manual Telegram/client QA remains NOT_TESTED; this does not close A1/A2 or the whole-bot goal.

### S12.24.4 — Finance buttons identify command guides and render safely

- Trigger: Admin → Tài chính / Finance → “Thêm chi phí” or “Xuất báo cáo”; also the expense report's add-expense shortcut.
- Baseline: `d05c2ae034f23c7808f3a739e98ebe4826634e40`, after S12.24.3 delivery.
- RED: the emitted controls dispatched through the actual registered menu callback. Baseline focused test produced 4 label assertion failures and 2 `NameError`s: `finance_add_expense_help_text` and `finance_export_menu_text` were referenced but undefined. The callback failed before rendering a page. Source review also found the period chooser labels said “Xuất tháng/năm này” although they displayed only a slash-command guide.
- Minimal fix: define the two missing read-only guide renderers; identify expense/export buttons as “Hướng dẫn”; make export month/year pages explicitly command guides. Callback payloads, admin guard, commands, ledger, export implementation, report logic and Back destinations are unchanged.
- GREEN: focused Finance renderer test → 4 tests OK. Combined with Finance Back, Admin module child-Back and Queue confirmation regressions → `Ran 15 tests in 44.804s — OK`. Actual emitted Finance controls dispatch through the registered menu callback; page content, Back target and public-user denial are covered. Finance actions are not executed by these tests.
- CI/local verification: focused test is included in Admin Route Regressions. Test-file execution and `git diff --check` pass. Local `py_compile bot.py` ran over 90 seconds at high CPU on the 15 MB source and was stopped; it is NOT a pass or syntax failure. PR/main complete-source compile and Admin Route CI subsequently passed.
- Scope/side effects: UI labels and guide renderers in `bot.py`, one registered-handler regression, CI invocation, and this ledger only. Provider calls, financial commands, ledger/wallet mutations, database writes, job creation and real Telegram messages: 0. Product/Edit/SubDub/Voice/Music route/engine and AutoPost WIP are untouched.
- Delivery: PR [#1392](https://github.com/manhtoangreensky-wq/bot/pull/1392) merged as `19bccd6ba945de0495dca29eb84b088b1a68c2d4`; PR/main complete-source compile and Admin Route CI passed. Bot-only deploy [#37537997175](https://github.com/manhtoangreensky-wq/bot/actions/runs/37537997175) succeeded with `deploy_workers=false`. SSH verified exact runtime SHA, bot/web/nginx active, `NRestarts=0`, and local health `status=ok`. [PR evidence](https://github.com/manhtoangreensky-wq/bot/pull/1392#issuecomment-6026340413). Manual Telegram/client QA case `UI-ADMIN-FINANCE-GUIDE-01` remains NOT_TESTED.

### S12.24.5 — Queue Freeze tools button identifies its guide destination

- Trigger: Admin → Queue / Freeze → “Freeze tools”.
- Baseline: `19bccd6ba945de0495dca29eb84b088b1a68c2d4`, after S12.24.4 delivery.
- Evidence: actual `ADMIN_CONTROL_MODULES["queue"]` emitter sent `menu|freeze_queue_help|admin_queue` through the registered menu handler. That handler rendered the static “Hướng dẫn Freeze / Queue” page, explicitly stating “Không thao tác trực tiếp từ nút này để tránh bấm nhầm”, with Back to Admin Queue; it does not freeze anything.
- RED: the focused test dispatched the emitted callback through the registered handler, then failed only because the button read “🧊 Freeze tools” instead of the guide destination. No fixture/setup failure.
- Minimal fix: change only that visible label to “📚 Hướng dẫn Freeze / Queue”. Callback, origin token, authorization, commands, Queue/Freeze behavior and confirmation flows are unchanged.
- GREEN: registered-handler Queue, Billing guide and Admin module regressions → `Ran 14 tests in 44.334s — OK`. Python 3.11.15 full `bot.py` and changed-test `py_compile` exited 0; `scripts/check_bot_source_compile.py` returned compile/source and AST PASS; `git diff --check` exited 0. PR CI remains required before merge.
- Scope/safety: one Admin Queue module label, one assertion in the already-CI-covered Queue callback test, audit ledger and staging case. No freeze/unfreeze/refund command, wallet/ledger/database mutation, provider call, job creation or real Telegram message. Product/Edit/SubDub/Voice/Music engines/routes and AutoPost WIP are untouched.
- Delivery: PR [#1393](https://github.com/manhtoangreensky-wq/bot/pull/1393) merged as `c00e42b054164fcfaa560d81fefae6edcda651d1`; both PR and main CI checks passed. Bot-only deploy [37562202893](https://github.com/manhtoangreensky-wq/bot/actions/runs/37562202893) succeeded with `deploy_workers=false`. Strict-host SSH verified exact runtime SHA, matching bot blob `71289092d7fce8a8c4933e80dbbd261553bf9d77`, all three services active/running/status 0/restarts 0 and health `status=ok`. Manual case `UI-ADMIN-QUEUE-GUIDE-01` remains NOT_TESTED.

### S12.25 — Old SS2/SS3 controls acknowledge their read-only recovery

- Trigger: an actual SS2/SS3 intro “Gửi video nguồn” callback is pressed after the active Product Video session has moved to another product.
- Base: `c00e42b054164fcfaa560d81fefae6edcda651d1` (Queue PR #1393 merged). Both stale-product branches render the existing Self-shot Hub through `safe_edit_or_send`; this helper acknowledges automatically only for `videoedit|`. Consequently neither branch acknowledged the old self-shot control.
- RED: actual service-emitted callbacks → exact registered Product Video handler including its failure guard → actual Hub keyboard and render helper; 2 test methods produced 4 SS2/SS3 behavioral failures (`[edit]` instead of `[answer, edit]`), zero setup errors. Session content and Hub recovery already remained correct.
- Fix: add one best-effort ACK before the existing Hub render in each of the two stale-product branches. No route target, session, source asset, planning, generation, quote, provider, worker or wallet logic changes.
- GREEN: focused stale-callback tests and callback timing regressions → `Ran 6 tests in 16.408s — OK`; normal ACK and simulated ACK timeout both preserve read-only recovery. Full Python 3.11.15 bot/test compile and diff check exit 0. Exact-base source comparator proves only two four-line ACK blocks differ in `bot.py`; services/providers/workers/deploy/config are unchanged.
- Delivery: PR [#1394](https://github.com/manhtoangreensky-wq/bot/pull/1394) merged as `ffc0da03165e31e4a23ca7a352cdd65f7c66f4ce`; both PR checks succeeded. Bot-only deploy [37562883724](https://github.com/manhtoangreensky-wq/bot/actions/runs/37562883724) succeeded with workers disabled. Strict-host SSH verified exact runtime SHA, matching tracked/deployed bot blob `ca8c40d4171f4d5023a1661e6f64a88b95a3e7ab`, bot/web/nginx active/running/status 0/restarts 0 and health `ok`. `UI-SELFSHOT-STALE-ACK-01` remains NOT_TESTED on Telegram. Whole-bot latency and callback coverage remain open.

### S12.26 — Remaining manual command-guide entry labels are truthful

- Scope: the read-only `admin_confirm_*` family across Admin Queue, legacy Queue/Freeze/Maintenance and Provider screens. All 13 command keys are registered as real slash commands; this spec changes no command operation.
- RED on base `ffc0da03`: 23 emitted guide-entry labels across 12 UI surfaces dispatch through the registered menu handler and display a command guide, but are labelled as direct actions. One focused method produces 23 assertion failures, zero setup errors.
- Fix: 25 visible entry labels (23 tested Admin entries plus 2 equivalent multiscene Admin diagnostic shortcuts), 13 page headings and one explanatory paragraph now identify manual guidance. Existing callback payloads, authorization, commands, Back destinations and operation logic are unchanged.
- GREEN: Queue/module registered-handler suite → `Ran 12 tests in 44.830s — OK`; all 13 guide actions covered. Full bot/test Python 3.11 compile and diff check exit 0. AST comparator proves exactly 39 UI string literal changes and otherwise identical structure; services/providers/workers/deploy/config unchanged.
- Delivery: PR [#1395](https://github.com/manhtoangreensky-wq/bot/pull/1395) merged as `2f185dbd6c8f2d0d6e26a76a50c074ae50168fdf`; both required CI checks passed. Bot-only deploy [37563691766](https://github.com/manhtoangreensky-wq/bot/actions/runs/37563691766) SUCCESS; strict SSH verifies runtime SHA, matching bot blob `6b484061d7bead121ffd70474171a994ffe14f25`, all services active/status 0/restarts 0 and health `ok`. Manual Telegram case `UI-ADMIN-MANUAL-COMMAND-GUIDES-01` remains NOT_TESTED. A1–A8 remain incomplete.

### S12.27 — Smoke Test guide Back preserves Provider/Worker ancestry

- RED on `2f185dbd`: actual Admin Provider/Worker entry → Smoke Test → each of 8 emitted guide buttons → Back renders a contextless Smoke menu whose Back goes to Admin root. 8 behavioral failures, zero setup errors.
- Fix: carry the validated `admin_provider_worker` UI origin from Smoke Test into its 8 guide controls and back into Smoke Test. Context-free legacy controls and the Security/DB Sales Ready context retain original behavior. Invalid/public contexts stop before cleanup, reads or render. Guide content/commands, registrations and operation/engine logic are unchanged.
- Same-guide UI correction: those 8 buttons also had direct-test/status labels although their pages only display manual instructions. Registered dispatch reproduced 8 label failures; only their Smoke menu labels now say `Hướng dẫn`. Final emitted-label/guide/Back round-trip method passes in 3.412s; full bot/test compile passes after this copy-only correction.
- GREEN: 15 Queue/Admin child-route test methods in `47.856s — OK`; full bot/test compile and diff check exit 0; exact-base source comparator allows only the closed Smoke guide validation and keyboard propagation blocks. Protected services/providers/workers/deploy/config unchanged. One prior test assumption about equal legacy/scoped payloads was updated for exactly the 8 newly scoped controls, retaining all remaining exact comparisons.
- Delivery verified: PR [#1396](https://github.com/manhtoangreensky-wq/bot/pull/1396) merged as `df82d1ae13c777d07d36f1e727d15903aca3b91b`; both required checks passed. Bot-only deploy [37565200990](https://github.com/manhtoangreensky-wq/bot/actions/runs/37565200990) SUCCESS, workers excluded. Strict SSH verifies exact runtime SHA, deployed/tracked bot blob `c3937f4a43cb42e66c7ff9dae41278460f76e8e3`, all three services active/status 0/restarts 0 and health `ok`. Manual case `UI-ADMIN-SMOKE-BACK-01` remains unverified.

### S12.28 — Broader offline callback ACK evidence (no product changes)

- On the #1395 source, executed all 23 `*callback*single_ack.py` modules with the standard-library runner, including standalone no-argument cases: **62 cases, 0 failures, 0 errors**. These exercise source-extracted callback handlers with inert transport/data/provider seams; route registration and emitted-control coverage differs by fixture.
- Additional direct cases: SubDub emitted Status/Download controls 4; SubDub Edit/Branding/error handoff 3; Provider Choice ownership/expiry 2; Support Admin permission/ACK 2 = **11 cases, all pass**. The two parameterized SubDub cases were invoked explicitly with only the pytest decorator shimmed; this is not a pytest run. The earlier unittest attempt failed to import missing pytest and did not prove these cases; the explicit direct run supersedes it.
- Updated 19 corresponding handler rows from NOT PROVEN to PARTIAL. Their unexercised emitted values, complete Back/expiry/repeat matrix and live timing remain open. Menu/help and other family rows retain their already-partial evidence.
- No provider calls, real Telegram sends, production data/wallet writes, jobs or product engine changes. These assertions are not evidence that every button is smooth or that a generated media job completes.

### S12.29 — Account credit-guide Back returns to Account

- RED on `df82d1ae`: actual `main_profile_keyboard` emits the generic `menu|guide_credits`; registered menu dispatch and real guide keyboard render Back=`menu|main_guide`. Expected immediate parent is Account. Vietnamese/English produce 2 behavioral failures, zero setup errors.
- Fix: scope only the Account credit-guide emitter to `main_profile`; validate that closed UI origin before cleanup and render its existing guide keyboard with Account Back. Generic guide callbacks retain Guide-index Back. Guide helper signature/content, prices, top-up, wallet/payment and engine routes are unchanged.
- GREEN: 11 Account/Admin child-route methods in `32.918s — OK`; full bot/test compile and diff check pass. Exact-source comparator allows one UI emitter plus closed guide-origin/Back blocks; services/providers/workers/deploy/config unchanged. Fixture corrections target the actual profile data seam and preserve the existing outer action trimming.
- Delivery: PR [#1397](https://github.com/manhtoangreensky-wq/bot/pull/1397) merged/deployed at `ae01c60dc8a28e6179d3da7df23ef30f81fa7592`; deploy [37566268771](https://github.com/manhtoangreensky-wq/bot/actions/runs/37566268771) SUCCESS with workers excluded. Strict SSH verified source blob `c578cde191f42f41ab8c0fafb24d6028b9526d3d`, all services active/status 0/restarts 0 and health `ok` at 07/10 10:24 +07. `UI-PROFILE-CREDIT-GUIDE-BACK-01` manual client QA NOT_TESTED.
- Next A3 checks: Account Pricing/Membership/Language/Support child navigation, using actual emitters and registered handlers with financial/provider seams inert. Scope only confirmed UI origin/Back defects; every unproven route remains incomplete.

### S12.30 — Account Pricing/Membership retains read-only UI ancestry

- Base `ae01c60d`; actual Account emitters and registered pricing handler reproduce missing Account Back on Pricing (VI/EN/ZH) and direct Member Back to Pricing: 4 behavioral failures, zero setup errors.
- Fix: two Account callbacks carry a closed UI origin; scoped pricing keyboards retain it through catalog/details, direct Member and nested Member/birthday paths. Legacy destinations and non-pricing/payment/package callbacks stay unchanged. Malformed origin stops before cleanup, data producers or render; callback objects are not mutated.
- GREEN: 9 Account pricing/credit-guide test methods in `26.897s — OK`; international catalog fallback layouts verified across all supported non-VI/EN/ZH locales. Full bot/test compile and diff check pass. Pricing branch/producer AST matches base after removing UI additions and keyboard wrappers; all remaining bot source matches base except two emitters, and engine/service/provider/worker/config/deploy directories unchanged.
- Final sweep also reproduced Total skipping Catalog and promo-code guide skipping Offers. Two narrow Back mappings fix them in the same UI scope. Final combined run: **11 tests in 34.086s — OK**, full compile/diff pass; current PR head must pass CI again before merge.
- Delivery: PR/CI/merge/bot-only deploy pending. `UI-PROFILE-PRICING-BACK-01` client QA NOT_TESTED. Next A3 spec checks Language, then Support, then remaining account/package paths.
- Delivery verified: [#1398](https://github.com/manhtoangreensky-wq/bot/pull/1398) merged/deployed at `a63934cc868a91e65d8093816deabc89b0221d8a`; final-head CI checks passed and bot-only deploy [37570356211](https://github.com/manhtoangreensky-wq/bot/actions/runs/37570356211) SUCCESS. Strict SSH at 07/10 11:17 +07 verifies matching bot blob `6eb235503ec27951fd8c3b1ca120717e27f90409`, all services active/status 0/restarts 0 and health `ok`. Prior pending note is historical; client QA remains unverified.

### S12.31 — Account language picker returns to Account

- Base `a63934cc`; actual Account button → registered language handler → actual picker Back or EN selection renders Main instead of Account: 2 behavioral failures, zero setup errors.
- Fix: one Account emitter and a validated optional UI origin retained by the native picker. Scoped Back and successful selection return Account; global/legacy language controls retain Main. Registration accepts scoped/malformed suffixes so the owner handler can reject invalid context with one alert. Query payload is not mutated.
- GREEN: 9 language/credit-guide methods in `21.255s — OK`; all 17 emitted locales, exactly one preference/event update, scoped old More control, legacy destinations, unsupported/malformed controls, Home and <=64-byte payloads checked. Full compile/diff pass.
- Protected comparator: preference persistence, usage and broadcast statements/arguments unchanged after removing presentation additions; all bot outside one emitter, language handler and registration suffix matches base. Engines/providers/workers/config/deploy/finance/AutoPost unchanged.
- Delivery: PR/CI/merge/bot-only deploy pending. `UI-PROFILE-LANGUAGE-BACK-01` manual client QA NOT_TESTED. Next A3 spec is Account Support ancestry.
- Delivery verified: [#1399](https://github.com/manhtoangreensky-wq/bot/pull/1399) merged/deployed at `a02af2d0edf80edf64a4aa17972bb5274fc40f4d`; deploy [37571259356](https://github.com/manhtoangreensky-wq/bot/actions/runs/37571259356) SUCCESS with workers excluded. Strict SSH at 07/10 11:28 +07 verified matching bot blob `fd8b9fb23ba5edfed82082fef542dbe3f3db5b3b`, active services/status 0/restarts 0 and health `ok`. Pending note above is historical; client QA remains open.

### S12.32 — Account Support read-only ancestry

- Base `a02af2d0`; actual Account Support emitter has no Account Back on hub; 5 read-only child round trips lose the opening Account context. Registered-dispatch RED: 6 behavioral failures, zero setup errors.
- Fix: closed origin on one Account emitter/menu branch; pure keyboard propagation for 8 read-only Support actions, including Bot/Consult details. Root gets Account Back and preserves Home. Invalid read context stops before cleanup/render. Ticket/Lead/My Tickets callbacks, pending setters and send/persistence behavior remain unchanged and are explicitly queued as dependent specs.
- GREEN: 8 Support/credit-guide methods in `45.623s — OK`, covering 5 hub children, 5 Bot and 6 Consult detail paths, legacy/malformed contexts, <=64-byte controls and unchanged form/ticket links. Full compile/diff pass. Three original Support ACK cases pass by loading the real new UI helper in their source fixture; no assertion weakened.
- Protected comparator: Support operation AST/pending/form/message arguments identical after presentation additions are removed; bot outside UI scope and engine/provider/worker/config/deploy directories unchanged. A missing fixture-only pure consult-choice dependency was loaded from the real local module before final GREEN.
- Delivery: PR/CI/merge/bot-only deploy pending. `UI-PROFILE-SUPPORT-READ-BACK-01` manual client QA NOT_TESTED. This closes only the read-only spec after delivery; full Support closure still needs pending Ticket/Lead/My Tickets context evidence.
- Delivery verified: [#1400](https://github.com/manhtoangreensky-wq/bot/pull/1400) merged/deployed at `72f46e1a12657491f15878d4f368cad4aa9c89de`; exact-SHA bot-only deploy [37573625803](https://github.com/manhtoangreensky-wq/bot/actions/runs/37573625803) SUCCESS. Strict SSH at 07/10 11:58 +07 verified matching bot blob `aa15ac1074c66c210f57a44bf5755705ea32b4c7`, active services/status 0/restarts 0 and health `ok`. Prior pending note historical; manual QA and dependent form/ticket specs remain open.

### S12.33 — Account Support form/pending origin survives retry and completion

- Base `72f46e1a`; four actual Ticket/Premium/Bot/Consult form controls pass through registered Support callback and real pending setter, but `back_to` loses Account origin: 4 behavioral failures, zero setup errors.
- Fix: scoped form controls/validation, UI-only suffix on existing allowlisted `back_to`, scoped prompt Back, short Ticket retry Back from pending state, and result Support Back using origin captured before pending completion. No new pending field/schema, TTL or lifecycle mutation. My Tickets/view/reply/attachment links remain unchanged for dependent S12.34.
- GREEN: 10 pending/read-Support methods in `56.663s — OK`; real pending helpers, all four fixture-only submissions, short retry, malformed forms, expired pending, legacy input and ancestor Back checked. Three legacy ACK cases pass; full compile/diff pass. Scope/operation comparator preserves classification/create/append/notify/clear statements and arguments, except the explicitly UI-valued `back_to`; engines/providers/workers/config/deploy unchanged.
- Delivery: PR/CI/merge/bot-only deploy pending. `UI-PROFILE-SUPPORT-PENDING-BACK-01` client QA NOT_TESTED. Next S12.34 is owned My Tickets/view/reply/attachment ancestry through the actual ticket handler and pending seams.
- Delivery verified: [#1401](https://github.com/manhtoangreensky-wq/bot/pull/1401) merged/deployed at `ba60dfed0dca5bc37734f6d55c8f0ed980b95e7d`; deploy [37576223955](https://github.com/manhtoangreensky-wq/bot/actions/runs/37576223955) SUCCESS with workers excluded. Strict SSH at 07/10 12:32 +07 verified matching bot blob `3735fd0c137e41150dd74470b999b21beb5fcb56`, all services active/status 0/restarts 0 and health `ok`. Pending line above historical; client QA remains open.

### S12.34.1 — Customer stale Ticket actions answer once

- Base `ba60dfed`; actual detail Reply/Done/Attach controls dispatch through the registered Ticket handler. Missing/owner-denied tickets produce an initial normal ACK then a not-found alert ACK. Missing IDs also double ACK; nonnumeric IDs raise production ValueError. RED: 6 behavioral failures plus 3 production parse errors, no fixture/setup errors; valid paths pass baseline.
- Fix: validate ID and actor-owned ticket once before normal acknowledgement for these three actions; reuse the resulting ticket in their original operation branches. Missing/unowned/malformed controls return one alert and zero writes. Valid pending/Done arguments and all Admin branches unchanged.
- GREEN: 3 focused methods in `2.126s — OK`, 3 original Ticket-view direct cases pass; full compile/diff and exact source comparator pass. Comparator permits only shared customer-action prevalidation and 3 lookup reuses; engines/providers/workers/config/deploy unchanged.
- Delivery: PR/CI/merge/bot-only deploy pending. `UI-CUSTOMER-TICKET-STALE-ACK-01` client QA NOT_TESTED. S12.34.2 My Tickets ancestry remains next and open.
- Delivery verified: [#1402](https://github.com/manhtoangreensky-wq/bot/pull/1402) merged/deployed at `d43864a3827ece9ddf68515785712fac131c048f`; deploy [37577735804](https://github.com/manhtoangreensky-wq/bot/actions/runs/37577735804) SUCCESS, workers excluded. Initial read observed HTTP still starting during deploy; terminal recheck at 07/10 12:57 +07 verified bot blob `1d7e137c050e8a277da7f3d8c0efa46a9e86c138`, services active/status 0/restarts 0 and health `ok`. Prior pending note historical; client QA remains open.

### S12.34.2 — Owned My Tickets/detail/input/result ancestry

- Base `d43864a3`; actual Account Support/My Tickets, detail and Reply/Attach controls, plus fixture-created result View controls reproduce 5 parent/context failures, zero setup errors.
- Fix: validated customer UI origins distinguish list (`profile`) and result (`profile_result`). Scoped detail Back returns list or an actor-owned read-only result screen (`ticket|summary`); no resubmission. Scoped Reply/Attach prompts retain `back_to`, retry and completion/result controls retain context; Done Back returns its detail. Existing helper schema/TTL, business data/notification operations and all Admin branches unchanged. Invalid/unowned scoped controls preserve unrelated pending state; valid owned Back cancels only the actor's pending input.
- GREEN: 17 ancestry/pending/stale-action methods in `86.088s — OK`; full source/test compile and exact-source/business AST comparators pass. Covers actor-owned list/detail/result, both completion types, short retry, empty/foreign lists, malformed/foreign controls, single existing Done update, same-user cancellation and other-user preservation. A local double-origin regression at combined read/form Ticket entry was caught before push; the form transform is idempotent and all four form submissions now pass.
- Existing result restoration reads the owned ticket and reuses the current result renderer; classification/create/append/update/notify decisions remain unchanged. Engines/providers/workers/config/deploy unchanged. Manual Telegram/client timing NOT_TESTED.
- Adjacent gates: 5 read-Support methods in `25.262s — OK` and 6 legacy Support/Ticket direct cases pass. The prior read-only fixture comparison now expects origin metadata on exactly `ticket|mine` and `support|ticket`, retaining all other literal comparisons; real form/pending execution remains verified by the 17-method suite.
- Delivery: PR/CI/merge/bot-only deploy pending. Full UI audit and remaining pending/expiry/repeat route matrix remain open after this bounded Support/Ticket context spec.
- Delivery verified: [#1404](https://github.com/manhtoangreensky-wq/bot/pull/1404) merged/deployed at `39c92d8f382581964cc49fe97fc6303e2843e559`; deploy [37580095807](https://github.com/manhtoangreensky-wq/bot/actions/runs/37580095807) SUCCESS, workers excluded. Strict SSH at 07/10 13:17 +07 verified matching bot blob `3b9f8b9aa524b325f767f7182950736d68277380`, active services/status 0/restarts 0 and health `ok`. Prior pending line historical; manual/client QA remains open.

### S12.35.1 — Account package/referral read navigation (no defect)

- Executed 4 actual Account emitters for Packages/Referral link/policy/stats through the registered Menu callback, real `profile_child_keyboard`, and emitted Back through the same registration. VI/EN/ZH × customer/admin = 24 direct navigation cases pass, one normal ACK per action, correct actor passed to each data producer.
- Data producers were inert; this verifies UI/Back and actor routing only, not package balances/referral data accuracy or live latency. No source fix or standalone PR needed. Remaining data/route matrix stays partial.

### S12.35.2 — Account Top-up selector Back

- Base `39c92d8f`; Account Top-up emits the generic selector and its Back opens Pricing. Actual registered menu/selector RED: 3 VI/EN/ZH parent failures, zero setup errors; legacy amount-payload assertion already passes.
- Fix: one Account emitter and a closed Menu origin/Back override. Scoped Back returns Account; generic selector retains Pricing Back. Existing price/text producers, 6 denomination callbacks, manual callback, Home and all payment/order/wallet code are unchanged. No amount/order button is clicked.
- GREEN: 7 Top-up/credit-guide methods in `19.221s — OK`, including 34 locale/role contexts, exact 7 payment payloads/actor, legacy and malformed scope. Full compile/diff and exact source comparator pass; bot outside the emitter/closed UI blocks and all protected directories matches base.
- Delivery: [PR #1405](https://github.com/manhtoangreensky-wq/bot/pull/1405) merged at `938f6813717831e17cb564c8de9172e6c22906df`; required CI passed. Bot-only deploy [37582086304](https://github.com/manhtoangreensky-wq/bot/actions/runs/37582086304) SUCCESS, workers excluded. Strict-host SSH verified exact runtime/source, all three services active with zero restarts, and health `ok` at 07/10 13:39 +07. `UI-PROFILE-TOPUP-SELECTOR-BACK-01` manual client QA NOT_TESTED. Pricing-origin Top-up/manual screen ancestry and other Support/Ticket entry sources remain open; this scoped fix is not whole-goal Back proof.

### S12.35.3 — Pricing-origin Top-up Back

- Baseline: main/runtime `938f6813717831e17cb564c8de9172e6c22906df`, bot blob `e3532eae3ff45fdf7617096c9a2d8c0a5b87bd5c`; services active and health `ok` at 07/10 13:39 +07.
- Trigger: actual Top-up buttons emitted by Pricing main, Offers, promo guide, Video pricing, Image pricing, locale-fallback Catalog and the Xu read screen; dispatch through registered Pricing and Menu callbacks.
- Acceptance: selector Back returns to the exact Pricing screen that emitted Top-up, retaining Account Pricing origin where present. Direct legacy `menu|main_topup` remains Pricing main. Invalid origin has no cleanup/read/render; amount/manual payloads, pricing data, payments and Home remain unchanged.
- RED: the original registered-handler test failed 5/5 behavioral cases, zero setup errors: Top-up from Account Pricing main, Offers, promo guide, Video pricing and Image pricing returned Pricing main. Follow-up emitter checks reproduced 14 more failures across every non-VI/EN/ZH Catalog fallback locale, plus one Xu screen failure; these were behavior failures, not fixture/setup errors.
- Minimal fix: encode one allowlisted Pricing screen token into the existing Menu Top-up callback and map it back to that read-only Pricing screen. Account Pricing origin is retained. The direct legacy Menu Top-up route still uses its existing Pricing parent. No payment/order callback or producer is changed.
- GREEN: Python 3.11 `-S -m unittest tests.test_profile_pricing_back_origin tests.test_profile_topup_back_origin tests.test_profile_credit_guide_back_origin -v` → `Ran 19 tests in 93.459s — OK`. The verified route cycles cover ten existing Account/legacy Pricing paths, all 14 locale-fallback Catalog emitters, and the actual `vip_services_keyboard` → registered Pricing handler → Xu → Top-up path. Malformed origins stop before read/cleanup/render; Home, seven payment payloads and callback length stay intact.
- Verification: Python 3.11 `py_compile bot.py tests/test_profile_pricing_back_origin.py tests/test_profile_topup_back_origin.py` exit `0`; `git diff --check` exit `0`. Required PR checks passed. PR [#1406](https://github.com/manhtoangreensky-wq/bot/pull/1406) merged at `03558c3408498201d6b2e0f1bce27485a8fb3b7a`; exact-SHA bot-only deploy [37589150697](https://github.com/manhtoangreensky-wq/bot/actions/runs/37589150697) SUCCESS with workers excluded. Strict-host SSH verified matching bot blob, three services active and `NRestarts=0`; deploy validated health `status=ok`. No payment/order/provider action or real Telegram message was used; manual client QA remains NOT_TESTED.
- Runtime note: Product Video `worker_sha_mismatch` warnings were already present at 14:44:47 +07 before the SSH deploy step started at 14:44:48 +07 and continued afterwards. No worker/engine file or deployment was changed in this UI-only spec; track that warning separately.

### S12.35.4 — Direct `/pricing_xu` command Top-up Back

- Baseline: main/runtime `03558c3408498201d6b2e0f1bce27485a8fb3b7a` after S12.35.3 deployment.
- Trigger: registered `/pricing_xu` command directly emits `pricing_xu_keyboard`; its `menu|main_topup` callback lacks Pricing-screen origin, so selector Back defaults to Pricing main instead of Xu.
- Acceptance: execute actual command handler, dispatch its emitted Top-up through registered Menu callback, press its emitted Back through registered Pricing callback, and verify it returns to the Xu page content. `/pricing`, callback-driven Xu, payments, Home, price/text producers and route engines remain unchanged.
- Allowed scope: one command's read-only keyboard origin, focused command-emitter/registered-handler regression, checklist and delivery evidence.
- Protected scope: denominations/manual/payment/order/wallet, provider/worker, Product/Edit/SubDub/Voice/Music/Image engines, AutoPost WIP, shared router architecture.
- RED: the actual registered `cmd_pricing_xu` emitted an unscoped `menu|main_topup`; after dispatch through registered Menu callback, the selector emitted Back `pricing|main` instead of `pricing|xu`. One behavioral failure, zero setup errors.
- Minimal fix: only `cmd_pricing_xu` rewrites its emitted Top-up callback to the existing allowlisted `pricing_xu` origin. Shared `pricing_xu_keyboard`, the Pricing callback path and Top-up/payment logic stay unchanged.
- GREEN: Python 3.11 `-S -m unittest tests.test_profile_pricing_back_origin tests.test_profile_topup_back_origin tests.test_profile_credit_guide_back_origin -v` → `Ran 20 tests in 137.681s — OK`; the command-emitted selector Back dispatched through registered handlers to `pricing|xu`. Test-file `py_compile` and `git diff --check` exit `0`. Full local `bot.py` compile did not finish within 7 minutes and was stopped; it is explicitly UNVERIFIED locally. `pytest` is unavailable in the workspace Python. No provider/payment API, Telegram send, job, wallet, or production DB side effects.
- Delivery: PR [#1407](https://github.com/manhtoangreensky-wq/bot/pull/1407) merged as `cfbeb530762526df148de351a8714815119b5db1`; required checks passed. Bot-only deploy [37593983924](https://github.com/manhtoangreensky-wq/bot/actions/runs/37593983924) SUCCESS with `deploy_workers=false`. SSH verified exact runtime SHA, `bot.py` blob `8ff1456bfc96714e6bba161e06b3c576dd6491a`, bot/web/nginx active, `NRestarts=0`, and health `status=ok`. Manual Telegram client QA remains NOT_TESTED.

### S12.35.5 — Admin Finance report renderers

- Baseline: main `cfbeb530762526df148de351a8714815119b5db1`, after S12.35.4.
- Trigger: Admin → Tài chính → Tổng quan / Doanh thu / Chi phí, plus Doanh thu → Nhập tháng khác. The actual `ADMIN_MENU_PAGE_HANDLERS` mapped these actions to undefined `finance_overview_text`, `finance_revenue_text`, `finance_revenue_month_menu_text`, and `finance_expense_month_menu_text`.
- Full Finance handler-reference check: 36 Finance action entries and 74 callable references were inspected. One additional undefined legacy target, `finance_command_help_text` (`finance_help`), was found although it is not emitted by current Finance keyboards; all five missing callable names now have a defined read-only renderer/alias. Other Finance handlers referenced defined renderers.
- RED: emitted overview, revenue, custom-period, and expense callbacks were dispatched through the registered Menu handler and raised 5 `NameError`s, zero setup errors. No report database read was reached.
- Minimal fix: add read-only renderers that reuse existing Finance report/period helpers; custom-period guidance uses existing `/revenue_report YYYY-MM` or `/revenue_report YYYY`. The legacy `finance_help` action delegates to the existing Finance handbook. No callback, authorization, report formula, command, ledger, invoice/payment or product route changed.
- GREEN: `tests.test_admin_finance_action_renderers`, `tests.test_finance_back_destination`, and `tests.test_admin_module_child_back_origin` → `Ran 14 tests in 75.793s — OK`. The fixture uses in-memory report payloads; actual emitted report callbacks and the legacy help action traverse the registered handler; Finance Back and public-user denial are covered. No production DB access/write, wallet change, provider call, job, or real Telegram send.
- Scope: `bot.py`, focused Finance renderer regression, and this checklist only. Product/Edit/SubDub/Voice/Music/Image engines, AutoPost WIP, workers, payment/wallet behavior, shared router, and report calculations are protected.
- Local complete-source `py_compile bot.py` was manually stopped after more than six minutes without output; it has NO PASS/FAIL verdict. GitHub CI `python-311-source-compile` and `python_hygiene_and_tests` both passed. PR [#1408](https://github.com/manhtoangreensky-wq/bot/pull/1408) merged at `93919f93d7207f252252f10f9c03d1e8a2d458f8`; bot-only deploy [37599864501](https://github.com/manhtoangreensky-wq/bot/actions/runs/37599864501) SUCCESS (`deploy_workers=false`). Strict-host SSH confirmed the exact bot SHA/blob, worker SHA unchanged, all services active, `NRestarts=0`, and health `status=ok`. [Delivery evidence](https://github.com/manhtoangreensky-wq/bot/pull/1408#issuecomment-6035017721). Manual Telegram QA is NOT_TESTED.

### S12.35.6 — Billing → PayOS Risk Back preserves module ancestry

- Baseline: main/runtime `93919f93d7207f252252f10f9c03d1e8a2d458f8` after S12.35.5.
- Trigger: Admin → Bill / PayOS → “Rủi ro nạp tiền” → Back.
- Hypothesis to verify before BUILD: the Billing module emits `menu|payos_risk`, while `payos_risk_menu_keyboard()` emits Back `menu|admin`; the immediate Billing parent may therefore be lost.
- Acceptance: dispatch the actual emitted control through the registered `handle_menu_callback`; if RED is reproduced, Back must return to `menu|admin_billing`, and re-entering the risk page must preserve that parent. Legacy `/payos_risk` and unscoped `menu|payos_risk` retain their existing Admin Back behavior. Public and malformed/stale origin callbacks must stop before rendering or pending-state cleanup.
- Scope lock: only Billing’s emitted UI origin and an action-specific menu render/back branch, plus the focused regression and this ledger. No risk-review action, database read/write, payment, PayOS webhook, wallet/ledger, provider, product engine, AutoPost WIP, or shared-router refactor.
- RED: the actual Billing module emitter was dispatched through the registered `menu|` handler and its production `payos_risk_menu_keyboard()`. The test observed `menu|admin` instead of the expected immediate parent `menu|admin_billing`. Public scoped origin was not denied and rendered fallback UI; both were behavioral failures, with no production I/O. An initial negative-case test had a missing main-menu fixture stub; that harness setup error was corrected and is not counted as product evidence.
- Minimal fix: Billing emits the validated `admin_billing` origin. The menu handler rejects public or malformed scoped origins before shared pending cleanup, normalizes only the allowlisted Billing case, and changes only the Risk page's Back button to `menu|admin_billing`. Unscoped legacy entry remains unchanged.
- GREEN: the new round-trip, legacy-entry and public/stale-origin cases pass. Combined Billing guide, Admin module child-origin, Admin handbook callback and Finance Back suite: `Ran 20 tests in 41.191s — OK`. Tests traverse the production keyboard builders and registered handler with inert replies; no risk query, DB/provider/payment/wallet operation or real message.
- Verification/scope: changed-handler source is compiled/executed by the registered-handler fixture; `py_compile tests/test_admin_billing_guide_labels.py` exited `0`; `git diff --check` exited `0` (only existing LF→CRLF working-copy warning). Full-source compile remains reserved for the final batch gate. `bot.py`, the existing focused Billing test, and this ledger are the only changed files. No payment/webhook/wallet, AutoPost WIP, protected product engine, or worker code changed.
- Delivery: local batch branch only. No per-spec PR, push, merge or deployment; the requested single batch release remains gated on completion of the entire ordered checklist and final CI.

### S12.35.7 — Admin System Ops Dashboard → Finance Overview Back preserves origin

- Baseline: main/runtime `93919f93d7207f252252f10f9c03d1e8a2d458f8` after S12.35.5.
- Trigger: Admin → System Ops → Dashboard → “Tổng quan” / Finance Overview → Back.
- RED: actual System Ops Dashboard emitter → registered `menu|` handler → production Finance keyboard/report renderer returned `menu|finance`; the immediate opening Dashboard was `menu|admin_overview|admin_system_ops`. One behavioral mismatch, zero setup errors. The route mismatch was verified without report DB/provider/payment access.
- Root cause: Admin Overview reused `finance_admin_keyboard()`, exposing the whole Finance hub under a Dashboard page. Finance report Back targets its canonical Finance parent, which was not the screen that emitted this Dashboard shortcut.
- Minimal UI correction: Admin Overview now uses a compact Dashboard keyboard with one read-only “Báo cáo tài chính” entry, Back and Home. Its finance-overview callback carries a closed origin (`admin_overview`, optionally `admin_system_ops`); the registered handler validates the origin before pending-state cleanup and returns to the exact Dashboard. The existing Finance hub, its controls, report renderers, and direct Admin → Finance Back remain unchanged.
- GREEN: `python.exe -S -m unittest tests.test_admin_finance_action_renderers tests.test_admin_module_child_back_origin tests.test_admin_overview_callback tests.test_admin_billing_guide_labels tests.test_finance_back_destination -v` → `Ran 25 tests in 112.639s — OK`. Covers System Ops → Dashboard → Finance Overview → Dashboard → System Ops; legacy unscoped Dashboard; standard Admin → Finance hub and report-child return; public/stale/malformed scoped callbacks; Admin module, Billing Back and Finance regressions. Callback sizes are asserted within Telegram's 64-byte limit. No production DB/report write, provider, payment, wallet, job, or real Telegram send.
- Test hygiene: the existing import-based System Ops label test expected the old unscoped Dashboard callback; its assertion is now aligned to the actual scoped `menu|admin_overview|admin_system_ops` emitted by the module. The route behavior itself is covered by the registered-handler tests above; `pytest` is unavailable in the local runtime, so the import-based test is syntax-compiled and remains in the final CI gate.
- Scope: `bot.py`, focused Admin/Finance route tests, the stale System Ops label expectation, and this ledger only. No report calculations, payment/wallet behavior, Product/Edit/SubDub/Voice/Music/Image engines, AutoPost WIP, worker, config, or shared-router architecture changed.
- Verification/delivery: changed test files' `py_compile` and `git diff --check` pass; full-source `py_compile bot.py` and final CI remain for the single batch closeout. Local only; no push, PR, merge, deploy, restart or LIVE claim. Manual Telegram QA remains NOT_TESTED.

### S12.35.8 — Admin Control Center top-level destinations (no mismatch reproduced)

- Baseline: main/runtime `93919f93d7207f252252f10f9c03d1e8a2d458f8`.
- Scope: actual Admin root emitter → every top-level module destination → registered handler and immediate Admin Back; separate Marketing/Affiliate registration, Back and public denial. This is source-level route verification, not a live-client check.
- Evidence: the real `menu_nav_keyboard("admin", True)` emitted 10 `menu|admin_*` module entries, `admin_growth|main`, and `menu|main`. The 10 menu routes each rendered the expected module title and `menu|admin` Back. Marketing/Affiliate rendered its cockpit using an inert metrics fixture; its Back returned through the registered menu route to the same Admin root. Public Growth access was denied before the metrics seam.
- GREEN: `python.exe -S -m unittest tests.test_admin_module_child_back_origin.AdminModuleChildBackTests.test_admin_control_center_entries_reach_their_registered_module_roots tests.test_admin_module_child_back_origin.AdminModuleChildBackTests.test_admin_growth_root_denies_public_user_before_report_read -v` → `Ran 2 tests in 6.668s — OK`. No DB/report read, provider, payment, wallet, production-data write, job, or real Telegram send; the Marketing report data was stubbed.
- Outcome: no root-navigation mismatch reproduced; no production code change. A1 remains partial because child actions, stale/repeat states, and live Telegram presentation are not all covered.

### S12.35.9 — Marketing/Affiliate child routes retain navigation origin and identify guides

- Baseline: main/runtime `93919f93d7207f252252f10f9c03d1e8a2d458f8`; work remains local on the single audit batch branch.
- Scope: Marketing root → Affiliate Links, Content Ideas, Calendar, Revenue/Click Report, Channels and Publish Packages; nested Add/Import guides, Calendar → Campaign list, Channels → Packages → Content guide, Back/Home and stale callback validation.
- RED: registered-handler baseline tests reproduced the nested Channels → Packages → Content Ideas Back mismatch (`admin_growth|main` instead of the immediate Packages parent); the root Content Ideas control also failed the “Hướng dẫn” label assertion; all three malformed-origin subcases rendered instead of being rejected. Root module destination checks themselves passed.
- Minimal fix: preserve a closed, three-entry Marketing navigation trail in callback data and pop it for Back; validate route names/parent edges and reject invalid trails before report/list reads; retain legacy unscoped Add/Import Back to Affiliate Links. Rename only controls whose destination is a command guide/list. No command, report calculation, data access implementation, publish pipeline or AutoPost state changed.
- GREEN: focused Marketing suite `python.exe -m unittest test_admin_module_child_back_origin.AdminGrowthNavigationTests -v` → `Ran 5 tests in 16.197s — OK`. Then Billing, Finance, the full Admin module-origin suite (including Marketing) and Admin Overview regressions ran together: `Ran 31 tests in 142.890s — OK`. The Marketing harness registers and dispatches the actual `handle_admin_growth_callback`; it covers root children, immediate and multi-step Back, Campaign ↔ Calendar, old Add/Import callbacks, guide/list labels, Home target registration, public denial before inert reads, malformed trail rejection before reads, and Telegram's 64-byte callback limit.
- Side effects: all report/list seams are in-memory stubs; DB/provider/paid calls, content creation/import, campaign commands, job creation, publish, wallet/payment and real Telegram sends: 0. Stable Product/Edit/SubDub/Voice/Music/Image routes, worker, shared router and AutoPost WIP are outside the change.
- Delivery: local only. No push, PR, merge, deploy, restart or LIVE claim. Manual Telegram/client QA remains NOT_TESTED; final full-source compile, broader regression batch and final CI are still open for the one planned release batch.

### S12.35.10 — Admin User/Xu help buttons dispatch to their emitted module (no mismatch reproduced)

- Scope: Admin Control Center → User/Xu, its five visible command-guide controls plus the module-level handbook shortcut, registered Admin Help callback, Back, and public-user denial. No `/add`, `/deduct`, `/settier`, `/setvip`, user lookup, ledger mutation, or production user data is exercised.
- Evidence: the Admin root route regression verifies `menu|admin_users` renders the User/Xu module with Admin Back. The generic emitted-help regression iterates each real `ADMIN_CONTROL_MODULES` keyboard, dispatches each emitted `admin_help|...|admin_users` button through `handle_admin_help_callback`, checks the handbook renderer and `menu|admin_users` return; it also verifies one normal acknowledgement and stale/public denial before rendering.
- GREEN: `python.exe -m unittest test_admin_help_callback_single_ack -v` → `Ran 5 tests in 1.001s — OK`. The all-module route loop includes User/Xu and other current Admin help controls. No UI or callback mismatch was reproduced; no production code change for this spec.
- Side effects: read-only inert handbook fixtures; DB, wallet, financial command, provider, user-data access/write, and real Telegram sends: 0. Delivery remains local to the single batch; no push/PR/merge/deploy/restart. A1 remains partial pending the remaining Admin visible-action and manual/live matrix.

### S12.35.11 — Broadcast Lite root, read-only views and pending Back (no mismatch reproduced)

- Scope: Admin Control Center → Broadcast Lite root; Compose/History/Schedule/Limits top-level controls; Back/Home and pending-draft exit; stop before any real customer delivery.
- Evidence: the Admin root emitter/registered `menu|` handler and Admin Back were verified under S12.35.8. Direct execution of the existing offline Broadcast Lite route gates checked root row layout, emitted callback ordering, handler action coverage, and the 64-byte limit. The existing actual-callback regression dispatches Back and Menu, clears only temporary pending ownership, and preserves saved draft content in a temporary SQLite database.
- GREEN: `python.exe -m unittest discover -s tests -p 'test_broadcast_lite_back_pending_cleanup.py' -v` → `Ran 3 tests in 0.499s — OK`. Three selected `test_p0_admin_broadcast2` offline UI gates passed with only its pytest decorator shimmed. The actual callback-flow regression also passed against temp SQLite; its injected worker/send path was not invoked, and the test confirms the confirmation result is only written to its test outbox. No live message was sent.
- Outcome: no route/label mismatch reproduced for the audited top-level Broadcast Lite controls; no production code change. Tests used temporary/test-only state. Production DB/user data, wallet/payment, paid provider, AutoPost WIP, real customer messages and runtime were untouched. Manual Telegram QA remains NOT_TESTED; A1/A4 stay partial. No push, PR, merge, deploy or restart.

### S12.35.12 — Admin Queue/Package child routes preserve their module origin (no mismatch reproduced)

- Baseline: audit batch based on main/runtime `93919f93d7207f252252f10f9c03d1e8a2d458f8`; no per-spec release.
- Scope: actual Admin Queue and Package module controls through the registered `menu|`/Admin Help handlers; Queue Status and Refresh/Back/Home; Freeze/Refund guide and confirmation-preview/cancel/acknowledgement exits; Package catalog/grant/user guides, storage handbook, and Package Orders Back for both Package and Finance origins.
- Evidence: the focused harness dispatches controls emitted by the production keyboard builders through the registered callback pattern. Queue Status uses an inert data renderer, and verifies Refresh retains `admin_queue`, Back returns to Queue, Home targets the registered main menu, confirmation guidance/cancel remains non-executing, and malformed/public origins stop before reads/cleanup. Package controls reach their guide renderers and immediate Package parent; Package Orders retains whichever of Package or Finance opened it; storage guidance reaches the registered Admin Help callback.
- GREEN: bundled workspace Python `-S -m unittest tests.test_admin_module_child_back_origin.AdminModuleChildBackTests tests.test_admin_queue_confirm_back_origin tests.test_admin_package_orders_back_origin tests.test_admin_package_storage_guide_label -v` → `Ran 21 tests in 75.213s — OK`.
- Outcome: no new mismatch reproduced and no production-code change for this spec. The render and data seams are inert; no production DB/backup, wallet/payment, paid provider, job, user-data mutation, or real Telegram send. This is not live Telegram/client QA and does not close A1/A2; remaining visible actions and manual latency/client checks stay open. No push, PR, merge, deploy, or restart.

### S12.35.13 — Admin Security/DB sibling routes and Runtime Help Back

- Scope: Security/DB module → DB Status / Security Log, sibling transitions, refresh, module Back, Backup result Back from each supported origin, Runtime Help origin from Security/DB and System Ops, and malformed/public origin rejection.
- Evidence: actual controls and registered `menu|` callback handler were exercised with `db_status_admin_text`, `security_log_text`, `create_db_backup_now`, and audit/security logging replaced by inert fixtures. Backup result navigation was verified without creating any backup. Runtime Help content/Back was exercised through its registered route; invalid and public callbacks stop before pending cleanup or render.
- GREEN: bundled workspace Python `-S -m unittest tests.test_admin_security_db_back_origin tests.test_admin_runtime_help_back_origin -v` → `Ran 9 tests in 20.786s — OK`.
- Outcome: no mismatch reproduced for these tested child routes; no production-code change for this spec. No production DB read/backup, security log read, wallet/payment, provider, job, user-data mutation, real Telegram send, push, PR, merge, deploy, or restart. Manual Telegram/client QA and other Admin controls remain open.

### S12.35.14 — Customer Image/Account/Memory root entries reach their registered menu destinations

- Scope: production `localized_main_menu_keyboard` emitter → registered `menu|` callback handler for the Image, Account, and Notes/Documents root entries. Video's dedicated handler also performs intentional pending-trend cleanup, so this spec asserts its emitted entry only and leaves callback execution to the dedicated Video timing/navigation harness; it does not exercise any product workflow.
- RED diagnosis: the first generic fixture dispatch included `menu|main_video` without the Video-only cleanup seam and raised `NameError: video_trend2_cancel_pending_on_video_menu`. Source tracing showed this was a fixture omission: the real route intentionally calls that cleanup before rendering. No product failure was established. The test was narrowed to route-only screens; Video remains covered by its separate harness.
- GREEN (initial subset run; superseded by S12.35.34): bundled workspace Python `-S -m unittest tests.test_admin_root_menu_callback_single_ack.AdminRootMenuCallbackSingleAckTests.test_customer_ui_root_entries_dispatch_to_their_emitted_screens -v` → `Ran 1 test in 0.392s — OK`. Each then-covered emitted callback matched the registered pattern, acknowledged once, and dispatched the same action to the inert screen renderer.
- Outcome: no production-code change. No pending state, product engine, provider, job, Xu, user data, or Telegram message was executed. A3 remains partial pending other customer routes and live/client QA; no push, PR, merge, deploy or restart.

### S12.35.15 — Free Tools maintenance exit clears only its own pending input

- Scope: actual `freehub|main` and `freehub|suggest_custom` callbacks through the registered Free Tools handler, maintenance response, and subsequent ordinary-text routing. No AutoPost state or other pending lane is in scope.
- Evidence: the test uses the production `handle_free_hub_callback`, pending-state helpers, and `handle_free_hub_pending_text` with a temporary in-memory pending map. It enters Free Tools, opens custom input, switches to maintenance, then proves Free Tools pending is gone, unrelated pending remains, and the next ordinary text is not consumed by Free Tools.
- GREEN: bundled workspace Python `-S -m unittest tests.test_freehub_maintenance_main_pending_reset -v` → `Ran 1 test in 0.941s — OK`.
- Outcome: no defect reproduced and no production-code change. The Free Tools generator/provider seam remained inert; no job, Xu, production data or real Telegram send. A3/A4 stay partial; expiry, repeat, cross-lane pending and live/client cases remain open. No push, PR, merge, deploy or restart.

### S12.35.16 — `/start` and `/menu` release selected pending inputs without losing saved data

- Scope: `/start` and `/menu` ownership for Broadcast Lite draft input, Memory search, Document page-range input, Internal Archive metadata, Storage Add-on custom input, Free Tools Downloader input and Admin Tool test pending. Subsequent ordinary text must not be captured by those stale prompts. This does not change or clear AutoPost's WIP input semantics.
- Evidence: focused harnesses compile production `cmd_start`/`cmd_menu` and actual pending helpers/handlers. Broadcast Lite uses temporary SQLite and verifies the draft returns to `draft` without overwriting saved content. Memory, Document, Archive and Storage verify their own per-user state clears while unrelated pending keys remain; Free Tools verifies unsupported user text is neither consumed nor passed to URL detection. Admin Tool confirms `/start`, `/menu` and callback Home clear its pending test action. Its old fixture omitted timing and unrelated cleanup dependencies; inert test dependencies were added without weakening assertions.
- GREEN: bundled workspace Python `-S -m unittest tests.test_broadcast_lite_start_pending_reset tests.test_memory_pending_reset_on_start tests.test_doc_page_prompt_reset_on_start -v` → `Ran 3 tests in 4.598s — OK`; `tests.test_internal_archive_metadata_reset_on_start`, `tests.test_storage_addon_pending_reset_on_start`, and `tests.test_video_downloader_freehub_exit_pending` → `Ran 3 tests in 4.863s — OK`; three Admin Tool test functions invoked directly → `Ran 3 Admin Tool pending-reset checks — OK`, with `py_compile tests/test_admin_tool_test_pending_reset.py` exit `0`.
- Outcome: no reset defect reproduced in these lanes and no production-code change. Only temporary/test state was used; no provider/job/Xu/real message. A4 remains partial for expiry, stale, repeat, other pending lanes, and cross-feature combinations. No push, PR, merge, deploy or restart.

### S12.35.17 — Pending expiry, stale replay and child Back spot-check

- Scope: check the relevant existing registered-flow tests for Account Support pending expiry, Internal Archive stale Save replay, Video Downloader pending release on Free Tools Home, and Document page-range Back/parent exit. This is a bounded follow-up to S12.35.16, not a claim that every pending lane or callback has been audited.
- GREEN: bundled workspace Python `-m unittest tests.test_profile_support_pending_origin tests.test_internal_archive_save_callback_single_ack tests.test_video_downloader_freehub_exit_pending -v` → `Ran 8 tests in 55.928s — OK`. The support expiry case proves an expired input is not consumed and legacy ticket flow remains legacy; stale Archive Save replay receives exactly one acknowledgement and does not save twice; Free Tools Home releases Downloader text ownership.
- Document Back checks: directly invoked `test_split_pdf_page_prompt_back_emits_preserving_route_and_keeps_selection` and `test_document_tool_parent_back_still_clears_session_and_returns_docs_menu` → `2 tests OK`; nested-page Back preserves its current selection, while parent Back clears the session and returns to the Docs menu.
- Outcome: no defect reproduced and no production-code change. Tests use fixture state/inert seams; no production DB/archive write, provider, wallet, job, or real Telegram message. A4 remains partial: pending expiry/stale/repeat behavior and cross-feature combinations still need lane-by-lane evidence. `pytest` is unavailable in the bundled runtime; the listed tests were run via stdlib `unittest` or directly invoked test functions, not claimed as a full pytest run. No push, PR, merge, deploy, or restart.

### S12.35.18 — Selected small-flow pending expiry is scoped and fail-closed

- Contract: exercise the actual pending-state getters for Free Tools, Downloader, Admin Tool, Support, Document, Memory, Storage Add-on, and Internal Archive using expired in-memory fixtures. Each getter must reject its expired state and remove only that owner's entry; unrelated users' pending state must remain unchanged. This is a characterization/coverage spec: do not alter business/engine code unless it demonstrates a behavioral defect.
- Protected: Broadcast Lite saved draft remains preserved by S12.35.16; Translation/SubDub and all Product/Edit/Image/Voice/Music engine paths remain outside this spec.
- Acceptance: one standard-library test invokes the real source helper bodies with a frozen clock and inert dictionaries; all eight owner cases assert the expired state is cleared and another user's state remains. No DB/provider/wallet/job/Telegram effects.
- GREEN: bundled workspace Python `-m unittest -v tests.test_small_flow_pending_expiry` → `Ran 1 test in 1.373s — OK`; `python -m py_compile tests/test_small_flow_pending_expiry.py` exited `0`; `git diff --check` exited `0` (only the existing LF→CRLF working-copy warnings for three previously modified test files).
- Outcome: all eight expired owner states are cleared and another user's in-memory state is preserved; no expired-state defect reproduced. Test-only addition; no production-code change, DB/provider/wallet/job/Telegram side effect. A4 stays partial for handler-level expiry confirmation in the remaining lanes, stale/repeat buttons and cross-feature combinations. No push, PR, merge, deploy or restart.

### S12.35.19 — Keep the start pending-cleanup test scoped

- Baseline evidence: directly invoking the pending-cleanup test parses the entire 14.5 MB bot.py although the assertion examines only cmd_start; after 30 seconds the local run still had no result and was interrupted. This is a slow test harness, not a product failure.
- Contract: parse only the exact top-level cmd_start function and preserve the existing assertion that all required small-flow pending clear helpers are called. Do not weaken the assertion or change bot behavior.
- Minimal test-only change: locate the top-level cmd_start/cmd_menu boundaries and parse only cmd_start; the six-helper assertion remains unchanged.
- GREEN: direct invocation of test_start_clears_all_small_navigation_pending_states → 1 test OK in 0.648s. Bundled Python py_compile for this test and the S12.35.18 test exited 0; git diff --check exited 0 with only the existing LF→CRLF warnings for three other modified test files.
- Outcome: the same A4 check now returns in under one second without parsing unrelated modules. No bot code, callback, product engine or runtime behavior changed. No PR/merge/deploy/restart.

### S12.35.20 — Admin Support → Marketing planner Back preserves its opening module

- Baseline: main/runtime `93919f93d7207f252252f10f9c03d1e8a2d458f8`, audit batch branch; no release per spec.
- Scope: the actual `ADMIN_CONTROL_MODULES["support"]` Marketing planner entry, registered `marketing|` callback, landing-page Back, and the landing → industry suggestions → Back-to-landing → Support return. Keep legacy unscoped `marketing|start` returning to Admin.
- RED: the actual Support module emitted `marketing|start`; dispatch through `handle_marketing_callback` rendered the landing keyboard with `menu|admin` instead of immediate parent `menu|admin_support`. One behavioral failure, no fixture/setup error.
- Minimal fix: scope that emitted entry with `admin_support`, retain the allowlisted navigation origin in the per-user UI context while returning to the planner landing page, and render a Support Back target only for that origin. Unscoped legacy entry remains unchanged. Planning text/state logic, input handlers, generation, publishing, AutoPost, and provider behavior are not changed.
- GREEN: `python.exe -S -m unittest tests.test_admin_marketing_support_back_origin tests.test_marketing_callback_single_ack -v` → `Ran 5 tests in 2.597s — OK`. The fixture instantiates the source-declared `marketing|` callback registration and dispatches the actual module-emitted control through that route; it verifies the nested industry Back returns to a landing page whose Back is Support, a fresh unscoped legacy start still returns to Admin, and non-admin access is denied before marketing-state access. Pending state and text are inert fixtures; no content generation or input processing is executed.
- Safety/scope: one Admin UI origin callback, Marketing planner keyboard Back label/target, handler-local UI-context selection, two focused regression files, and this ledger. No `autopost|` WIP, media/product engine or worker code, database, wallet, provider, job, production data, or Telegram send. Manual Telegram QA is not tested. Full-source compile is a closeout CI gate; no push, PR, merge, deploy, or restart per spec.

### S12.35.21 — Broadcast Lite read-only panels return to their emitting page

- Scope: real Broadcast Lite root/history/schedule/limits keyboard emitters and the registered `broadcast_lite|` callback; test History → Broadcast root, Schedule → Broadcast root, root Limits → root, and Schedule → Limits → Schedule. No draft confirmation, audience delivery, schedule creation/toggle, or limit mutation.
- Evidence: dispatch the exact root-emitted controls through the source-declared callback registration. The fixture replaces history/schedule/limit data reads with inert values and replaces pending cleanup with a no-op; it checks acknowledgements, page output and actual Back callbacks.
- GREEN: `python.exe -S -m unittest tests.test_broadcast_lite_back_pending_cleanup -v` → `Ran 4 tests in 0.739s — OK`, including prior Back/Menu pending-owner and saved-draft preservation cases. No Back mismatch reproduced.
- Side effects: no production DB read/write, schedule or draft creation, limit mutation, provider, wallet, job, campaign, or real customer send. The write/confirm callbacks are never dispatched. No production-code change for this spec; no push, PR, merge, deploy, or restart.

### S12.35.22 — Marketing plan-result Back returns to its suggestion parent

- Scope: Support-origin Marketing planner → industry suggestions → one locally rendered plan result → Back to suggestions → landing → Support. Preserve unscoped legacy plan-result Back to Admin. Test uses inert suggestions, wait text, and plan renderer; no content-generation function/API is called.
- RED: with a Support-origin callback, the plan result's emitted Back was `menu|admin`; expected its immediate parent `marketing|back_suggestions`. One behavioral mismatch, no setup error.
- Minimal fix: give `marketing_result_keyboard` an optional, closed Back choice and select `marketing|back_suggestions` only for the Support-origin plan-result callback. Default/legacy keyboard remains `menu|admin`; no plan content, selection logic, follow-up work, or publishing behavior changes.
- GREEN: `python.exe -S -m unittest tests.test_admin_marketing_support_back_origin tests.test_marketing_callback_single_ack -v` → `Ran 7 tests in 4.609s — OK`; both edited test files also pass `py_compile`, and `git diff --check` passes. The test traverses Support → plan → suggestions → landing Back and verifies the legacy plan result still emits Admin Back; every plan/generation seam is inert.
- Scope/safety: UI Back callback and regression evidence only; no content generation, provider call, AutoPost, media/product engine, DB, wallet, job, or Telegram send. Full-source compile remains a final CI gate. No push, PR, merge, deploy, or restart per spec.

### S12.35.23 — Provider/Worker Smoke Test entry is clearly labeled as a guide

- Scope: Admin Provider/Worker module → emitted Smoke Test entry → registered `menu|` handler → Smoke Test command hub. Do not execute any smoke-test command or contact a provider/worker.
- RED: the emitted callback opened the static `Smoke Test Tools` page and quick-command guide; its follow-on Smoke Test controls are labeled `📘 Hướng dẫn …`, but the module entry said `🧪 Smoke Test`. Focused registered-handler test failed on that exact label mismatch.
- Minimal fix: rename only the Admin module entry label to `📘 Hướng dẫn Smoke Test`; callback, command text, handler and test/execution behavior are unchanged.
- GREEN: `python.exe -S -m unittest tests.test_admin_module_child_back_origin tests.test_admin_billing_guide_labels -v` → `Ran 22 tests in 61.431s — OK`. The new regression dispatches the actual module-emitted control through the registered callback and verifies the quick-command hub and guide-only child labels. The 7 Marketing route/authorization/legacy tests also passed after S12.35.22 was finalized. Changed test-file `py_compile` and `git diff --check` exited 0.
- Test note: an initial assertion expected wording from a child page rather than the root hub; it was corrected to assert the actual rendered `Lệnh nhanh` hub and its emitted guide controls. The corrected full suite is green.
- Scope/safety: one Admin UI label, one assertion in the existing callback regression file, this ledger and the runbook only. No provider call, test execution, worker, wallet, database, job or Telegram send. AutoPost and Product/Edit/Image/SubDub/Voice/Music routes/engines remain untouched. No PR, merge, deploy or restart; keep it in the single batch release.

### S12.35.24 — Sales Ready guide labels and legacy System Back target

- Scope: the two Admin emitters for Sales Ready (Security/DB and legacy System), their registered `menu|` callback, Sales Ready guide rendering, and Back to the legacy System page. No readiness command or system operation is executed.
- RED: both Admin emitters labeled a static `/sales_ready` command guide as `✅ Sales Ready`. The legacy System emitter omitted its origin; actual handler dispatch showed Back → `menu|smoke_test`. Dispatching `menu|system` then fell through `localized_menu_content` to the main-menu fallback instead of rendering the existing System page.
- Minimal fix: label both controls as `📘 Hướng dẫn Sales Ready`; scope the legacy System callback and reject its public use; route Back to `menu|system`; add the existing Admin-only System renderer to `localized_menu_content`, reusing `menu_text_system()` and `menu_nav_keyboard()`.
- GREEN: new emitted-control tests verify both labels, authorized registered-handler dispatch, guide output, Back to System, successful render of the existing System menu, and public denial before cleanup/read. Admin module-child + Billing route regressions → `Ran 24 tests in 84.682s — OK`; focused new Sales Ready tests → `Ran 2 tests in 8.745s — OK`. Changed-test `py_compile` and `git diff --check` exited 0.
- Scope/safety: two visible labels and the narrowly scoped legacy System callback/render path. No changes to system commands/status operations, credentials, configuration, engine/provider/worker code, wallet, database, jobs or real messages. AutoPost and Product/Edit/Image/SubDub/Voice/Music lanes remain protected. Manual Telegram/client QA remains NOT_TESTED; no PR, merge, deploy or restart before batch closeout.

### S12.35.25 — Legacy System Operator entry opens Operator and returns to System

- Scope: Admin legacy System menu → emitted Operator button → registered `menu|` handler → existing read-only Operator page → Back to System. Preserve context-free legacy Operator → Admin behavior and reject a public `system`-origin callback before cleanup/render.
- RED: the actual System menu emitted `menu|operator`, but `localized_menu_content` had no Operator branch; registered-handler dispatch rendered `MAIN MENU` instead of the Operator page.
- Minimal fix: emit `menu|operator|system` only from the legacy System entry, authorize and validate that closed origin, render the existing Operator text/keyboard for the legacy callback router, and make only the scoped Back return to `menu|system`. Remove the duplicate explicit System shortcut from that scoped keyboard; preserve its Admin and Home controls.
- GREEN: focused emitted-route test verifies the scoped callback, Operator page, single System return control, actual System renderer, and public denial before cleanup/read. Admin module-child + Billing route regressions → `Ran 25 tests in 109.778s — OK`; focused route → `Ran 1 test in 7.125s — OK`. Changed-test `py_compile` and `git diff --check` are recorded at batch verification.
- Scope/safety: one legacy System entry callback, one Admin-only localized route, and the origin-specific return keyboard. No Operator command, system operation, provider/worker, wallet, DB write, job or real Telegram send ran. AutoPost and Product/Edit/Image/SubDub/Voice/Music engines/routes remain untouched. Manual Telegram/client QA remains NOT_TESTED; no PR, merge, deploy or restart before batch closeout.

### S12.35.26 — Legacy System read-only shortcut labels identify guide destinations

- A1 target: the System menu's Data Status, Backup DB, and Health controls open static command/API instructions; verify the actual emitted controls through the registered menu callback and label each as a guide without changing callbacks or operations.
- Acceptance: all three controls keep their existing instruction text and System/Admin/Home destinations, but their labels clearly say “Hướng dẫn”. Providers remains a live read-only status page and is excluded from this label-only spec.
- RED: the registered-handler test found three label-only mismatches: “🗄 Data Status”, “💾 Backup DB”, and “❤️ Health” each opened a static instruction page.
- Minimal fix/GREEN: prefix those labels with “Hướng dẫn”; leave callbacks, guide text and renderer unchanged. Focused System guide/Sales Ready/Operator tests → `Ran 3 tests in 13.835s — OK`; all three guide buttons returned to the actual System renderer. No system command, backup, provider, worker, DB-write, wallet or Telegram-send operation ran.
- State: locally verified on the single batch branch; changed-file syntax/diff and full-batch closeout are still pending. No PR, push, merge, deploy or restart.

### S12.35.27 — Legacy System Providers status retains its opening origin (locally verified)

- A1 route evidence: the actual legacy System emitter's “📊 Providers” control dispatches through the registered `menu|` handler to the existing read-only Provider Status page; the inert renderer returns the expected status destination.
- A2 defect reproduced: the resulting controls initially showed Refresh → `menu|admin_provider_status`, Details → `menu|admin_provider_routes`, and Back → `menu|admin_provider`. System-origin context was lost; Back opened the provider management menu, not System.
- Minimal fix/GREEN: carry a closed `system` origin only from the legacy System emitter; scoped status Back returns to System, scoped refresh retains that origin, and Details Back returns to scoped Provider Status. Existing Provider/Worker module origins remain unchanged. Public and malformed origins stop before reads/cleanup.
- Evidence: the seven-route existing Admin module Back regression plus the new System Provider Status route test and System guide-label test → `Ran 3 tests in 22.997s — OK`; changed-test `py_compile` and `git diff --check` exited 0. A broader three-module test command exceeded three minutes without output and was interrupted; that attempt is NOT counted.
- State: locally verified on the single batch branch; full-batch compile, suite, scope review and CI remain open. No PR, push, merge, deploy or restart. Provider probes/tests/freeze, worker calls, DB writes, wallet mutations, jobs and real messages: 0.

### S12.35.28 — Operator → System Back returns to Operator (locally verified)

- A2 defect reproduced from the actual Operator menu emitter: “⚙️ Hệ thống” emitted `menu|system`; registered-handler dispatch rendered System, whose Back was `menu|admin` rather than the Operator menu.
- Minimal fix/GREEN: carry a validated `operator` origin from that button and make only the scoped System page Back return to Operator. Direct legacy `menu|system` still returns to Admin; System → Operator retains scoped Back and removes the duplicate System shortcut. Public/stale origins fail closed before cleanup/render.
- Evidence: the new two-direction System route test plus the existing seven-route Admin-origin regression and System Provider/guide route tests → `Ran 5 tests in 50.643s — OK`. No system command/status, provider/worker, DB, wallet, job, or real-send operation ran.
- State: locally verified on the single batch branch; changed-test syntax and diff checks pass, while full-batch compile/suite/scope review/CI remain open. No PR, push, merge, deploy or restart.

### S12.35.29 — Customer root/account/support/language navigation regressions (locally verified)

- Scope: run existing emitted-control and registered-handler tests for customer Image/Account/Memory root destinations, account credit guide, Account → Support read-only children and detail Back, legacy Support compatibility, and account language-picker Back/selection. No product processing route is entered.
- Evidence: `tests.test_admin_root_menu_callback_single_ack`, `tests.test_profile_credit_guide_back_origin`, `tests.test_profile_support_read_back_origin`, and `tests.test_profile_language_back_origin` → `Ran 17 tests in 50.025s — OK`. Public/stale scoped controls are rejected before cleanup/render; supported Back paths return to their account/support parent; legacy controls remain intact.
- Outcome: no mismatch reproduced in this bounded customer subset; no production-code change. The full customer callback matrix, visual/client QA, and remaining product-boundary checks are still open. No provider, job, wallet, production-data, or real Telegram side effect; no push, PR, merge, deploy, or restart.
- A6 observation closed by S12.35.96: the current emitter and `test_translation_main_menu_hotfix.py` agree on eight public rows, all existing shortcuts, and the Admin-only final row; the earlier mismatch was a stale test contract already corrected in S12.35.35/.39. A source-extracted current-emitter/registered-route fixture passed. No production UI change. A6 remains partial for Telegram-client viewport/wrapping and remaining copy/layout review.

### S12.35.30 — Small-flow stale/repeat/back regressions (locally verified)

- Scope: current-branch registered-handler checks for Marketing support-origin navigation, Account Support pending ancestry/expiry, stale Internal Archive Save replay, repeated Admin Ticket lead markers, and FreeHub maintenance exit. Fixtures keep report/storage/message/provider side effects inert.
- Evidence: `tests.test_marketing_callback_single_ack`, `tests.test_admin_marketing_support_back_origin`, `tests.test_internal_archive_save_callback_single_ack`, `tests.test_support_ticket_lead_action_repeat`, `tests.test_freehub_maintenance_main_pending_reset`, and `tests.test_profile_support_pending_origin` → `Ran 18 tests in 45.676s — OK`. Duplicate stale Archive Save did not save twice; repeated same-admin lead markers did not duplicate notes; Support Back/expiry retained the opening account; FreeHub maintenance released only its owner state.
- Outcome: no mismatch reproduced in this bounded set. A4 remains partial for the remaining owner/state matrix and protected AutoPost pending semantics; no production-code change, provider call, wallet change, production write, job, real Telegram message, push, PR, merge, deploy, or restart.

### S12.35.31 — In-scope `/start`/`/menu` pending-owner and TTL closeout

- Contract: verify the remaining listed small-flow owners release only their own unsaved input on Home, `/start`, or `/menu`, preserve saved Broadcast draft and unrelated state, and reject expired ownership. Keep AutoPost WIP input semantics and product/job engine pending state unchanged.
- Evidence: current branch, bundled Python `-S -m unittest` across Broadcast Lite, Memory, Document, Internal Archive, Storage Add-on, Video Downloader and Small Flow Expiry → `Ran 7 tests in 13.082s — OK`. The three Admin Tool pending exit functions and `test_start_clears_all_small_navigation_pending_states` were invoked directly → `4 direct pending-cleanup checks — OK`.
- Internal Archive route evidence: 3 focused checks OK, including its registered `^archive\|` pattern and type-screen Back to either the pending-file preview or department dashboard; a pending fixture file and title were preserved. No archive contents were read.
- Outcome: A4 is verified for the in-scope small navigation/pending matrix. Protected AutoPost content state and engine-owned product actions are not claimed as audited or changed. No production-code change, provider/job/wallet/data/Telegram side effect, PR, push, merge, deploy, or restart.

### S12.35.32 — Root Video/Home timing harness extraction (test-only)

- RED diagnosis: invoking the existing root Video/Home callback timing tests with the bundled standard-library runner failed before callback dispatch with `NameError: ContextVar`. `safe_edit_query_message` extraction had swallowed the following module-level callback telemetry block; a first regex boundary also matched a default-valued parameter because the search began mid-signature.
- Minimal test-only fix: extract a named top-level function by its source line and stop at the next top-level definition/class/assignment. Production bot code, telemetry and routes are unchanged.
- GREEN: the same eight intended scenarios were invoked after the fix: root Video for public/admin × new/resume, render-error timing, other-root no-timing, and Back/Home for public/admin → `8 Video/Home callback timing checks — OK (stdlib runner; pytest decorators and approx shimmed)`. This is deterministic synthetic handler timing, not a live latency sample.
- Scope: one test helper and this ledger; no product workflow, provider, job, wallet, production data, real Telegram message, push, PR, merge, deploy, or restart.

### S12.35.33 — Current public/admin main-menu callback registration inventory

- Evidence: execute the production `localized_main_menu_keyboard` emitter against both public/admin fixture roles; compare each emitted callback value against all current literal `CallbackQueryHandler` regex registrations and Telegram's 64-byte callback bound.
- Result: public menu has 8 rows/14 callbacks and admin menu has 9 rows/15 callbacks; both `unmatched_registered_routes=[]` and `over_64_bytes=[]`.
- Limit: this is only a registration/size inventory, not proof each button reaches the intended rendered page. Existing per-route dispatch evidence remains the acceptance gate. The conflicting compact-layout expectation is tracked separately under A6; this inventory does not approve a menu redesign.

### S12.35.34 — Public main-menu small-flow root dispatch (locally verified)

- Scope: extend actual-emitter dispatch coverage for Image, Account, Memory, Support and Guide through the registered menu handler, plus Feedback through its separately registered handler. Video remains covered by S12.35.32. No translation, Music, AutoPost, Chat Pro, or product-processing route is entered.
- Harness note: the first run reached the registered handler but failed because the source-extracted fixture omitted the production Guide and Support render dependencies (`NameError`); this was a fixture setup error, not a callback assertion or production failure. Added inert render seams only to the test fixture.
- GREEN: bundled Python 3.12 `-S -m unittest tests.test_admin_root_menu_callback_single_ack -v` → `Ran 6 tests in 1.612s — OK`. Ten safe small-flow callbacks from the production root keyboard match their respective registered menu/freehub/pricing/language/feedback handlers; Image/Account/Memory/Support/Guide traverse `handle_menu_callback`, Feedback traverses its registered handler and clears only its intended pending states, and root Support Home returns to Main through the registered menu handler. The same suite checks the observed 8-row, all-shortcuts-preserved emitter. Existing FreeHub, Pricing, Language, Video and Admin tests provide the separate behavior checks.
- Outcome: no production-code change or UX defect reproduced. This closes the bounded safe root-link matrix only; protected product routes, remaining customer branches and visual/client QA remain open. No provider, job, wallet, production-data, or real Telegram side effect; no PR, push, merge, deploy, or restart.

### S12.35.35 — Align stale compact-menu test with current emitted shortcuts (test-only)

- Finding: `test_translation_main_menu_hotfix.py` still required the historical 7-row/14-control arrangement from commit `f1773441`; its expected row positions omitted the later AutoPost shortcut. The current emitter retains all 14 callbacks plus one community URL across 8 rows (one singleton and 7 pairs). Seven 2-column rows cannot contain all 15 controls.
- Decision/fix: preserve the current bot UI, every callback payload, and ordering. Update only the stale test contract to assert the current 8-row layout and AutoPost/Account/Guide/Feedback positions. No AutoPost handler or state was entered or changed.
- GREEN: the production-emitter source fixture in S12.35.34 verifies current row shape and callback registration; `tests.test_admin_root_menu_callback_single_ack` → `Ran 6 tests in 1.612s — OK`. The updated `test_translation_main_menu_hotfix.py` syntax-compiles. Its pytest assertions could not be executed locally because pytest and the bot's full import dependencies are unavailable in the bundled Python; required CI remains the final execution gate.
- Outcome: no rendered UI/layout change. This resolves a stale test expectation only. Final Ubuntu CI must run the broader configured suite before batch merge; no provider, job, wallet, data, or Telegram side effect.

### S12.35.36 — Correct Owner setup guidance for the active VPS runtime

- Finding: the real `owner_required_text` and registered `/admin_whoami` outputs told an admin to edit `OWNER_IDS` on Railway, although TOAN AAS runtime is Ubuntu VPS/systemd. This was stale operator UI copy, not a permissions/configuration defect.
- Minimal fix: replace only three displayed Railway references in those two renderers with VPS guidance. `OWNER_IDS`/role checks, ENV, deployment, restart, secrets, and all unrelated Railway/runtime behavior remain unchanged.
- GREEN: source-extracted fake-role/output checks → `Owner UI runtime copy: 2 checks OK`; assertions confirm both outputs say VPS, contain no Railway, preserve ID/role diagnostics, and perform only one captured reply in the test.
- Scope/limits: only the two named outputs were corrected; this is not a global Railway terminology cleanup. Other runtime-dependent Railway references remain unchanged. No real Telegram message, config write, role change, restart, or deploy.
- Delivery: one batch branch only. No commit, push, PR, merge, or deploy before A3–A7 and final batch verification close.

### S12.35.37 — Public Chat Pro root entry and Home dispatch (locally verified)

- Scope: take the actual `menu|chat_pro` value emitted by the public main menu, dispatch it through the registered `handle_menu_callback`, exercise only the read-only Chat Pro information screen, then dispatch its emitted `menu|main` Home control through the same handler. Do not toggle Chat Pro, send a prompt, call a provider, or mutate billing/wallet state.
- Evidence: the route displays the fixture balance and Chat Pro summary; Home returns to the main renderer. The test records one fake account read and zero Chat Pro mode writes. Registration pattern, one callback acknowledgement per dispatch, and emitted Back destination are asserted.
- GREEN: bundled Python `-S -m unittest tests.test_admin_root_menu_callback_single_ack -v` → `Ran 7 tests in 1.781s — OK`.
- Finding: no callback destination or Back defect reproduced. Test-only coverage addition; `bot.py` and production Chat Pro behavior are unchanged. This closes only the bounded non-mutating Chat Pro entry; product engines, persistent Chat Pro toggles, prompts, and full visual/client QA are not covered. No provider, wallet, DB write, job, real Telegram send, PR, push, merge, deploy, or restart.

### S12.35.38 — Public Account root entry renders the account menu and returns Home

- Scope: derive `menu|main_profile` from the production main-menu emitter, dispatch it through the registered `handle_menu_callback` and actual `localized_menu_content`, `menu_text_main_profile_i18n`, and `main_profile_keyboard` source functions. Use inert user/package fixtures; then dispatch the emitted `menu|main` through the same handler.
- Evidence: the account page renders fixture ID/tier/balance and the actual account keyboard. All 11 emitted Account controls match their registered Menu/Pricing/Language handler patterns; the existing focused child suites cover scoped Pricing, Guide, Support, and Language behavior. Home renders Main. No real database/account access occurs.
- GREEN: bundled Python `-S -m unittest tests.test_admin_root_menu_callback_single_ack -v` → `Ran 8 tests in 2.914s — OK`.
- Outcome: no wrong route or Home defect reproduced. Test-only coverage; no `bot.py` change and no wallet, provider, product-engine, database, job, or real Telegram side effect. This does not claim every Account child was individually dispatched in this test.

### S12.35.39 — Align remaining root-menu tests with the current 8-row emitter (test-only)

- RED: direct invocation of `test_hub_layout_has_the_exact_owner_rows_and_preserves_existing_routes` failed at its obsolete `len(rows) == 7` assertion; the legacy-menu test separately failed its seven-row width assertion. Static review found the same stale seven-row layout/no-AutoPost expectation in `test_free_tools_hub_v1.py` and `test_core.py`.
- Fix: update only those test expectations and the i18n fixture music callback stub to match the current production emitter: 8 public rows, 9 admin rows, AutoPost at its existing position, all other controls/callback order preserved. No UI, route, product engine, or AutoPost handler change.
- GREEN: the two extracted current/legacy menu layout tests passed across supported locales; current visible Vietnamese labels and callback row positions match the production source. Root dispatch regression suite: `Ran 8 tests in 2.914s — OK`. `py_compile` for all four affected test files and `git diff --check` exited `0`.
- Limits: full `pytest` and imported `bot.py` suites are unavailable in this local runtime; Ubuntu CI must run the existing `test_free_tools_hub_v1.py`, `test_p0_i18n_native_hub_restore.py`, and `test_core.py` gates before the single batch merge. No production side effect or release action.

### S12.35.40 — Non-engine customer route gap review after root-menu closure

- Scope: recheck emitted public root and Account child Back paths in the existing small-flow suites: root callback dispatch, Account credit guide, read-only Support panels, and language picker/selection. Use registered-handler/source fixtures only. Product/Edit/Image/SubDub/Voice/Music processing, AutoPost WIP, payment mutation, provider calls, Telegram sends, and production data remain protected.
- Finding: no new wrong-parent, Home, registration, or stale-origin defect reproduced in the bounded non-engine customer set. This does not prove all dynamic route families or protected lanes.
- GREEN: bundled Python `C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest tests.test_admin_root_menu_callback_single_ack tests.test_profile_credit_guide_back_origin tests.test_profile_support_read_back_origin tests.test_profile_language_back_origin` → `Ran 22 tests in 72.487s — OK`.
- Side effects: inert fixtures only; provider calls=0, wallet mutations=0, production database writes=0, jobs=0, real Telegram sends=0.
- Limits: this is offline handler evidence, not Telegram client visual QA or end-to-end latency. Remaining dynamic customer callback families and all protected product routes remain explicitly unverified; A3/A5 stay PARTIAL. Full source compile and Ubuntu CI remain final batch gates.
- Delivery: local cumulative branch only; no commit, push, PR, merge, deploy, or restart.

### S12.35.41 — Public Image menu display and Back without entering tools

- Scope: take the public root's menu|main_image control through the registered Menu handler, render the actual Image menu keyboard, verify its Home destination, then dispatch only menu|main. The four image task callback values are asserted as rendered controls but are not executed; Image generation/edit engines and providers stay protected.
- Finding: no wrong screen or Back/Home target reproduced; the UI-only callback returns to the existing Main menu.
- GREEN: the combined root/Account/credit-guide/Support/Language regression set, including this actual Image renderer/Back test, ran 23 tests in 72.314s — OK. Changed test py_compile and git diff --check exited 0.
- Side effects: fixture-only; provider calls=0, wallet mutations=0, production database writes=0, jobs=0, real Telegram sends=0.
- Limits: this does not verify image task terminals, Telegram client rendering, or end-to-end latency. Image engine and all other protected product routes remain excluded.
- Delivery: local cumulative branch only; no commit, push, PR, merge, deploy, or restart.

### S12.35.42 — Public root callback inventory and evidence gaps (read-only)

- Source truth: S12.35.33 inventoried 14 public main-menu callback values, all registered and within Telegram's 64-byte limit. Current root values are:
  - FreeHub — freehub|main
  - AutoPost — menu|autopost
  - Chat Pro — menu|chat_pro
  - Account — menu|main_profile
  - Image menu — menu|main_image
  - Video menu — menu|main_video
  - Translation — menu|translate
  - Notes/Documents — menu|main_memory
  - Voice/Music — music_quick|showroom|root
  - Guide — menu|main_guide
  - Support — menu|support
  - Pricing — pricing|main
  - Feedback — feedback|start
  - Language — back_lang
- Evidence map: FreeHub main/maintenance uses S12.35.15 and pending regressions; Chat Pro read-only info → Home is S12.35.37; Account root and children are S12.35.38/.40/.47; Image landing → Home is S12.35.41; Support → Home and Account credit/language paths are S12.35.40; Notes/Documents → Back/Home is S12.35.43; Guide landing → Home is S12.35.44; Video is limited to its menu/timing coverage and no job processing; Pricing/Feedback/Language have their focused route suites. Existing protected AutoPost, Voice/Music, Translation, and product processing are not re-entered by this inventory.
- Remaining non-engine gaps: no uncovered top-level landing/Back route from the S12.35.42 inventory was identified after S12.35.43/.44/.47. Stateful mutations, payment terminals, document/tool actions and protected processing still require their own bounded authorization/test scope; they are not silently counted as UI-navigation passes. No behavior defect is asserted by this inventory.
- Limits: an inventory is not terminal-route proof. Keep A3/A5 PARTIAL until the named gaps are exercised or explicitly excluded by the approved boundary. No production change or side effect.

### S12.35.43 — Notes/Documents landing and origin-preserving Back/Home

- Scope: dispatch the emitted public Notes/Documents root through the registered Menu handler and actual Notes/Documents menu builders; follow only the emitted Documents landing, then Back to Notes and Home to Main. Use fake storage-copy values. Do not create/search/delete a note, upload/save a file, or enter any PDF/Word tool.
- Finding: the registered callbacks render the expected Notes and Documents screens; Documents Back returns to Notes, and Home returns to Main. No mismatch reproduced.
- GREEN: the combined root/Account/credit-guide/Support/Language suite ran 24 tests in 55.024s — OK. The focused new route test passed; changed root test py_compile and git diff --check exited 0.
- Side effects: fixture-only; production storage/DB reads and writes=0, provider calls=0, wallet=0, jobs=0, real Telegram sends=0.
- Limits: no note/document terminal or real Telegram rendering was exercised. Guide landing remains the next bounded customer route gap; A3/A5 remain PARTIAL.
- Delivery: local cumulative branch only; no commit, push, PR, merge, deploy, or restart.

### S12.35.44 — Customer Guide landing and Home

- Scope: dispatch the public main menu's Guide entry through the registered Menu handler and actual Guide menu builder; verify that Home is emitted and returns to Main. Do not dispatch the Video/Image/Music or other engine-linked guide articles.
- Finding: Guide landing and Home resolve to their expected pages; no callback mismatch reproduced.
- GREEN: the combined root/Account/credit-guide/Support/Language suite ran 25 tests in 47.425s — OK. The focused new Guide test passed; changed root test py_compile and git diff --check exited 0.
- Side effects: inert source-extracted UI fixture only; provider calls=0, wallet=0, production data=0, jobs=0, real Telegram sends=0.
- Limits: only landing and Home are tested; article terminals and Telegram client visual QA remain open. A3/A5 remain PARTIAL.
- Delivery: local cumulative branch only; no commit, push, PR, merge, deploy, or restart.

### S12.35.45 — Existing Memory-pending, Feedback, and Language callback evidence

- Scope: reuse the small existing source-extracted checks for Memory's /start and /menu pending ownership, Feedback start/unsupported action, and supported/unsupported Language selection. Do not send Feedback to a real customer/admin, write production language settings, or create/delete a Memory note.
- GREEN: bundled Python command for tests.test_memory_pending_reset_on_start plus the Feedback/Language unittest modules ran 1 unittest in 1.812s — OK (the latter modules expose direct functions, so their assertions were invoked separately). Four direct checks returned OK: Feedback start and unsupported callback (2), Language supported and unsupported callback (2).
- Limitation: invoking the legacy test_memory_empty_delete_state.py helper stalled while parsing the full 15 MB bot.py; it was interrupted, NOT_COUNTED. No product defect was inferred; that assertion still requires Ubuntu CI/full-suite evidence.
- Side effects: fake user/update state only; production language write, database write, note create/delete, wallet, provider, job and real Telegram send = 0.
- Delivery: local cumulative branch only; no commit, push, PR, merge, deploy, or restart.

### S12.35.46 — Feedback category prompt and Cancel Back/Home

- Scope: dispatch an emitted Feedback category value and the existing Cancel value through the actual registered Feedback callback handler. Assert one callback acknowledgement, only the Feedback pending-state transition, and emitted Back/Home destinations. No real report is submitted.
- GREEN: all four direct checks in tests/test_feedback_callback_single_ack.py returned OK, covering start, unsupported action, category prompt and cancel.
- Side effects: in-memory fixture only; no customer/admin message, production pending state, database, wallet, provider or job operation.
- Delivery: local cumulative branch only; no commit, push, PR, merge, deploy, or restart.

### S12.35.47 — Account Pricing/member/Top-up callback regression

- Scope: rerun the bounded Account Pricing, member and Top-up navigation regressions; verify Back ancestry and emitted destinations using inert fixtures. Do not initiate a top-up/payment or change wallet state.
- GREEN: the focused Account Pricing/member/Top-up regression set ran 13 tests in 77.406s — OK.
- Side effects: fixture-only; no payment, wallet mutation, provider call, production-data write, job or real Telegram send.
- Delivery: local cumulative branch only; no commit, push, PR, merge, deploy, or restart.

### S12.35.48 — Provider low-balance notice path (source-only UI/operations audit)

- Scope: read the existing provider notice policy and admin delivery seam only; do not query ShopAIKey/Key4U, send a Telegram message, alter credentials/settings, or change provider/engine routing.
- Source evidence: the shared policy uses a fixed $100 baseline and warns only below $10 (exactly $10 is normal), rejects stale/unknown balances, persists a pending/sent receipt, and rate-limits repeats to six hours. The monitor has ShopAIKey and Key4U gates and sends through the admin bot client; no auto-freeze is part of this notice path.
- Existing regression evidence files: `tests/test_provider_balance_alert_policy.py`, `tests/test_provider_balance_notifications.py`, and `tests/test_provider_balance_runtime_seam.py` cover the policy and inert delivery seam. They were inspected but not executed in this spec.
- Result: source behavior matches the requested 10%-of-$100 threshold. Whether production credentials/flags permit delivery and whether a real admin received a notice are NOT_VERIFIED here.
- Side effects: read-only source/test inspection; provider calls=0, real Telegram messages=0, runtime setting writes=0.
- Delivery: local cumulative branch only; no commit, push, PR, merge, deploy, or restart.

### S12.35.49 — Callback latency instrumentation regression

- Scope: verify the existing anonymous callback timing wrapper/observer with a fake application, callback and render helper only; no production callback or Telegram update is sent.
- GREEN: `python -m unittest tests.test_callback_dispatch_timing -v` → 4 tests in 7.490s — OK. The tests cover observer installation after direct registrations, guard/handler/render timing, blocked/error cases, and absence of callback payload, message, or user ID in log output.
- Live correlation: the user reports Account → Back takes about 2–3 seconds. The read-only VPS journal window `2026-10-07 22:49:45–22:59:45 +07` contained 301 INFO lines but no callback timing event; a separate read-only service check at 22:59 +07 showed `active/running`, `NRestarts=0`. No exact click timestamp or matching event exists, so this remains a user-observed end-to-end estimate, not a server-phase measurement.
- Side effects: local mock test and read-only VPS queries only; no provider, wallet, data, Telegram-message, deploy or restart side effect.
- Delivery: local cumulative branch only; no commit, push, PR, merge, deploy, or restart.

### S12.35.50 — Account → Back reported latency correlation

- User observation: Account → Back takes approximately 2–3 seconds. This is an approximate click-to-screen report, not a timed instrumented sample; no exact `HH:MM:SS` was supplied.
- Existing evidence: the strict-host journal query for `2026-10-07 22:49:45–22:59:45 +07` returned no callback timing events despite 301 INFO lines in that window. The bot service was active/running with `NRestarts=0` at 22:59 +07. Because the click time is unknown, the query cannot be asserted to contain that click.
- Source coverage check: Account child Back emits `menu|main_profile` and Account Home emits `menu|main`; both are registered under the shared `menu|` callback handler. The anonymous observer is installed after callback registrations and wraps all registered `CallbackQueryHandler` instances. If the click reached those callback handlers during the queried window, a timing event should be eligible to appear; the unmatched time means the log result still cannot identify the delay source.
- Result: the observed delay is real as reported, but its share across bot dispatch, Telegram delivery/render, and device/network remains unassigned. Historical Main/Video measurements are not Account-route evidence.
- Acceptance to close A7: collect multiple route-specific user samples with exact local timestamps and durations, then correlate each with anonymous server phases; do not change routes or infer a network/device cause from unmatched evidence.
- Fresh read-only recheck: at VPS time `2026-10-08 00:18:30 +07`, the query window `00:03:30–00:18:30 +07` returned no `callback_dispatch_timing prefix=menu` or `callback_latency route=menu` lines. The service was active/running, `NRestarts=0`, and the deployed timing instrumentation source was present. The owner still reports approximately 2–3 seconds without exact click time; this empty window cannot attribute the delay. The generic observer records registered-handler prefix `menu`, not the specific Account action, so route-level attribution also requires an accurately timed sample.
- Latest read-only recheck: strict-host SSH succeeded at `2026-10-08 01:39:52 +07`; `journalctl -u toanaas-bot.service --since '15 minutes ago'` returned no `callback_dispatch_timing` or `callback_latency` lines. The owner again estimates 2–3 seconds but did not provide the exact click time. This confirms no correlatable server sample was available in the queried window; it does not identify whether the delay is in bot dispatch, Telegram render/delivery, device, or network.
- Side effects: checklist/state update and prior read-only log/service checks only; provider calls=0, real messages=0, production writes=0, deploy/restart=0.
- Delivery: local cumulative branch only; no commit, push, PR, merge, deploy, or restart.

### S12.35.51 — Public/Admin root menu and callback regression rerun

- Scope: rerun the existing emitted-root and registered-handler UI regression set; keep all processing, data mutation, payment, AutoPost, and protected product engines inert.
- GREEN: `python -m unittest tests.test_admin_root_menu_callback_single_ack -v` → `Ran 11 tests in 6.271s — OK`.
- Covered: public root row shape and registration-pattern checks for safe root callbacks; actual dispatch/Back/Home for Image, Account, Notes/Documents, Support, Guide and Feedback; Chat Pro read-only landing/Home; Admin authorization/root callback behavior. Video timing/navigation has its separate test. AutoPost, Translation and Music/Voice entries are not dispatched by this suite.
- Source layout: public root has 8 rows with sizes `1,2,2,2,2,2,2,2` (14 callback buttons and one URL button); Admin receives one additional final row. This establishes source structure only, not Telegram client wrapping/scroll or visual polish.
- Side effects: fixture-only; no database/provider call, job, payment, wallet change, real Telegram send, or protected engine execution.
- Delivery: local cumulative branch only; no commit, push, PR, merge, deploy, or restart.

### S12.35.52 — Guide-origin Video article Back

- Source finding: the public Guide menu emits the generic `menu|guide_video_ai` callback, whose informational page Back is hard-wired to `menu|main_video`. The same generic entry is used by Video product screens, where `main_video` remains the correct parent. This is a Guide-origin navigation mismatch, not a Video-engine defect.
- Contract: distinguish only the Guide-menu entry, return that article's Back to `menu|main_guide`, and preserve the existing generic Video-origin callback/Back to `menu|main_video`. Dispatch all seven Guide article controls through the registered menu handler and verify their Back/Home destinations; inspect but never dispatch article action buttons.
- Acceptance evidence: a focused fixture must exercise actual Guide/video-guide emitters and `handle_menu_callback`, observe Article → Guide and Article → Main, and prove the legacy Video-origin Back remains Video. No tool/job/provider/payment/data action is allowed.
- RED: one route test failed at the expected navigation assertion: Video article Back was `menu|main_video`, while the Guide-origin contract requires `menu|main_guide`.
- Minimal fix: only the Guide menu's Video article callback carries `main_guide` origin; the registered handler validates that origin and changes that article's Back target. The existing context-free Video callback still renders Back to `menu|main_video`.
- GREEN: fresh `python -m unittest tests.test_admin_root_menu_callback_single_ack -v` → `Ran 13 tests in 7.632s — OK`. The actual Guide emitter and menu handler dispatched all seven Guide articles; each article's Back returned to Guide and Home returned to Main. No article action button was dispatched. A separate legacy Video-origin assertion retained the Video parent.
- Compile/diff: changed test files passed `python -m py_compile`; `git diff --check` exited 0 (only existing LF→CRLF warnings). Full `bot.py` py_compile was attempted normally and with GC disabled, then stopped after >8 minutes and ~700 MB without a result: `NOT_VERIFIED`. The focused callback fixture compiled and executed the changed function source; full-source compile and Ubuntu CI remain final-batch gates. `tests.test_menu_video_callback_timing` could not import because bundled Python lacks `pytest`; the new registered-handler compatibility case covers the legacy Video guide Back, but does not replace the timing suite.
- Status: LOCALLY VERIFIED — fixture evidence only; full-source compile, final protected-scope review, CI and delivery remain open.
- Side effects: local test/checklist/state only; no real Telegram messages, provider calls, jobs, wallet/production-data changes, push, PR, merge, deploy, or restart.

### S12.35.53 — Vietnamese Guide support-button label

- Source finding: the Vietnamese Guide keyboard labels the `menu|support` action “👨‍💼 Admin”, although the registered route renders the customer Support screen. The English/other locale branches use support-oriented wording.
- Contract: change only this Vietnamese button label to “👨‍💼 Hỗ trợ”; keep its callback, row position, and all support behavior unchanged.
- Acceptance evidence: a source-extracted test must build the actual Vietnamese Guide keyboard and assert the emitted label/callback pair; the callback must remain registered to the existing Support menu route.
- RED: the focused emitter test failed at the expected label assertion: actual “👨‍💼 Admin”, expected “👨‍💼 Hỗ trợ”; the callback already remained `menu|support`.
- Minimal fix: change only the Vietnamese button text to “👨‍💼 Hỗ trợ”. No callback, order, locale branch, support handler or message flow changed.
- GREEN: fresh `python -m unittest tests.test_admin_root_menu_callback_single_ack -v` → `Ran 14 tests in 6.734s — OK`; this includes the seven Guide article Back/Home checks, legacy Video Back, and the Vietnamese support label/destination assertion.
- Compile/diff: changed test files `python -m py_compile` exited 0; `git diff --check` exited 0 with existing LF→CRLF warnings. The full `bot.py` compiler remains `NOT_VERIFIED` as recorded in S12.35.52; source-extracted actual Guide emitter execution compiled the changed function.
- Read-only source review: the other Guide topic labels, download controls, Back/Home targets and community URL have their corresponding article or destination callbacks; no second Guide-menu label mismatch was found. Telegram viewport/wrapping remains unverified.
- Status: LOCALLY VERIFIED — fixture evidence only; full-source compile, final protected-scope review, CI and delivery remain open.
- Side effects: local UI/test/checklist/state only; no support ticket, database, provider, payment, or message action.

### S12.35.54 — Public/Admin root and Guide label/destination recheck

- Scope: rerun the emitted root-menu/Guide controls through the source-extracted keyboard builders and registered callback handlers, including Admin root authorization. Do not dispatch tool actions, media generation, payments, or protected product flows.
- GREEN: bundled Python command python -m unittest tests.test_admin_root_menu_callback_single_ack -v → Ran 14 tests in 5.179s — OK.
- Finding: no new root/Guide label-to-destination or Back/Home mismatch was reproduced. Guide Video origin returns to Guide, legacy Video origin remains Video, and Vietnamese Hỗ trợ still opens Support.
- Limits: source-extracted fixture only; no Telegram client viewport/wrapping or end-to-end timing claim. Protected AutoPost/Translation/Voice/Music and action terminals are not covered.
- Side effects: fixture-only; no database/provider/wallet/job/payment/real Telegram actions and no product-engine execution.
- Delivery: local cumulative branch; no commit, push, PR, merge, deploy, or restart.

### S12.35.69 — Prompt Library category Back preserves its parent

- Contract: start from the public root's emitted Free Tools button, dispatch through the registered FreeHub handler, open `Kho Prompt`, select a prompt category, then dispatch Back. It must render the same Kho Prompt category menu, not jump to the Free Tools root. Home remains `menu|main`.
- RED: the actual emitted category-suggestions keyboard used `freehub|main`; dispatching that Back rendered Free Tools rather than Kho Prompt. Initial fixture run had a missing `html` dependency and was not counted; after fixture correction, the focused test failed only on the expected callback mismatch, with no setup error.
- Fix: in `free_hub_library_suggestions_keyboard`, change only the Back label/route to `Kho Prompt` / `freehub|library`. The existing registered library handler already renders the category menu and clears only FreeHub pending state.
- GREEN: `test_free_tools_prompt_library_back_stack_restores_parent_and_exact_results` → `Ran 1 test in 0.532s — OK` on the extended route; the source-extracted fixture uses actual root/library/category/item keyboard builders and actual registered FreeHub handler, with one acknowledgement per callback.
- Limits: prompt suggestions are inert fixture data; no prompt selection/save/generation, provider, wallet, production DB, job, AutoPost, engine, or real Telegram action. Other Free Tools terminals remain unverified; A3/A5 stay PARTIAL.
- Delivery: local cumulative branch; no commit, push, PR, merge, deploy, or restart.

### S12.35.70 — Prompt detail Back restores the exact result list

- Contract: from Kho Prompt → category suggestions → select one prompt, Back from the local prompt detail restores the exact same suggestion text and IDs. It must not jump to Free Tools or rerun the randomized suggestion query; category-list Back then returns to Kho Prompt.
- RED: the actual prompt-detail keyboard emitted `freehub|main` rather than a result-list Back; the focused registered-handler fixture failed at that emitted callback assertion, with no setup error.
- Fix: prompt-detail Back now emits `freehub|lib_back`; the existing `lib_back` route reconstructs the list from the preserved `library_ids` via the local prompt lookup. It does not call the randomized suggestion helper.
- GREEN: the same registered-handler test passed in `0.532s`; it asserts byte-for-byte same rendered suggestion text, same ID snapshot, exactly one suggestion query total, then Back to Kho Prompt. `.69` category Back and Main Home targets remain verified.
- Limits: all library contents and pending data are fixtures. No prompt-save/write, text generation, provider, wallet, production data, job, AutoPost, protected engine, or real Telegram activity. A3/A5 remain partial.
- Delivery: local cumulative branch; no commit, push, PR, merge, deploy, or restart.

### S12.35.71 — Free Tools utilities landing Back

- Contract: dispatch the actual Free Tools → Tiện ích control through the registered FreeHub handler; verify its four emitted utility controls match the FreeHub registration and its Back returns to Free Tools. Do not invoke utility actions.
- Evidence: included in `test_free_tools_prompt_library_back_stack_restores_parent_and_exact_results`, which traverses the emitted chooser and Back through the actual handler; one ACK each, root destination rendered, and FreeHub pending remains cleared. `Ran 1 test in 0.608s — OK`.
- Limits: rate/weather/QR/avatar terminals were not dispatched; no network/API/provider, wallet, production data, job, AutoPost, engine, or Telegram action occurred. This closes only the static chooser Back route; A3/A5 remain partial.
- Delivery: test/evidence only on the cumulative local branch; no commit, push, PR, merge, deploy, or restart.

### S12.35.72 — Free Tools translation prompt Back releases its pending state

- Contract: dispatch the actual Free Tools translation entry through the registered FreeHub handler; verify it opens the input prompt with its owned pending marker, and emitted Back returns to Free Tools and clears that marker.
- Evidence: `test_free_tools_translation_prompt_back_clears_only_its_pending_state` uses the actual FreeHub keyboard, exact registered handler, fixture-local pending state and inert renderer; both callbacks are acknowledged once. `Ran 1 test in 0.222s — OK`.
- Limits: no translation text, external/paid provider, wallet, production data, job, AutoPost, media engine or real Telegram send was invoked. Other Free Tools terminals remain open; A3/A4/A5 stay partial.
- Delivery: local cumulative branch; no commit, push, PR, merge, deploy, or restart.

### S12.35.73 — Free Tools prompt-generator Back returns to its hub

- Contract: take the emitted Free Tools “Prompt ảnh/video” button from the actual hub keyboard, dispatch through the registered `freehub|` handler, verify the local suggestion screen and its pending marker, then dispatch its emitted Back. Back must restore Free Tools, clear only this owner's pending marker, and preserve a second user's marker.
- Finding: no route or pending-ownership defect reproduced. Prompt entry and Back were each acknowledged once; the suggestion generator was called once with the expected `image_video_prompt` type and offset `0`.
- GREEN: `python -m unittest tests.test_admin_root_menu_callback_single_ack -v` → `Ran 24 tests in 10.355s — OK`; the focused route method passed in `0.266s`. `python -m py_compile tests/test_admin_root_menu_callback_single_ack.py` exited 0; `git diff --check` exited 0, with only existing LF→CRLF warnings on three unrelated tests.
- Limits: suggestion values and pending maps are fixture-local. No prompt choice/use, image/video engine, provider, wallet, database, job, AutoPost, production data, or real Telegram action occurred. A3/A5 remain PARTIAL.
- Delivery: local cumulative branch; no commit, push, PR, merge, deploy, or restart.

### S12.35.74 — Free Tools upload prompt Back returns to its hub

- Contract: take the emitted “Lưu tệp tạm” control from the actual Free Tools keyboard, dispatch it through the registered `freehub|` handler, verify the upload prompt and owner-scoped pending marker, then dispatch its emitted Back. Back must return to Free Tools, clear only the current owner's marker, and leave another user's marker unchanged.
- Finding: no label/destination or pending-isolation defect reproduced. Upload entry and Back each receive one acknowledgement; only the local upload prompt is rendered.
- GREEN: `python -m unittest tests.test_admin_root_menu_callback_single_ack -v` → `Ran 25 tests in 10.108s — OK`; the focused upload-route method passed in `0.346s`. The upload flow remains a prompt-only fixture.
- Limits: no file/media was received, saved, downloaded, or processed; no database, provider, wallet, job, AutoPost, product engine, production data, or Telegram client action occurred. A3/A5 remain PARTIAL.
- Delivery: local cumulative branch; no commit, push, PR, merge, deploy, or restart.

### S12.35.75 — Copy help preserves Prompt Library ancestry

- Acceptance: dispatch the Copy control emitted by a selected Prompt Library item through the registered FreeHub handler. Display clear manual-copy instructions and retain the item keyboard's Back to the exact previous suggestion list; acknowledge once and preserve the suggestion ID snapshot. The Copy label must describe the action. No clipboard success claim or external Meta handoff is implied.
- Scope: only the library item label, the existing `copy`/`prompt_back` render branch, and its inert registered-handler regression. No prompt generator, save, provider, or engine execution.
- Verification: RED on the current batch source, then the smallest renderer correction and the existing root/FreeHub regression module. Delivery remains part of the single batch.
- RED: the emitted Copy label incorrectly said “Dùng cho Meta”; handler output had no manual-copy help and Back changed from `freehub|lib_back` to `freehub|main`. The registered-handler fixture reported 3 behavioral failures, 0 setup errors.
- Fix: use the existing localized Copy label, display localized manual-copy instructions, and retain the library-item keyboard when `task_type=prompt_library`. Pending content and suggestion IDs remain unchanged.
- GREEN: focused actual-emitter/registered-handler method `Ran 1 test in 1.531s — OK`; it exercises Copy, exact-list Back restoration, category Back and utilities Back with one ACK each. Fixture-only; provider/wallet/DB/jobs/real Telegram=0.
- State: LOCALLY VERIFIED. Full batch regression/CI and delivery remain open.

### S12.35.76 — Marketing follow-up and custom-brief Back retain CSKH ancestry

- Acceptance: after opening Marketing from CSKH, both a selected suggestion and a custom brief produce results whose follow-up controls and Back retain the suggestions parent, then Marketing, then CSKH. Legacy direct Admin entry keeps its existing parent.
- Scope: only the two result-keyboard arguments that omit the validated existing origin; use the existing inert Marketing registered-handler and pending-text fixtures. No generation/publishing/provider/data action.
- RED: 5-method suite reported 7 behavioral failures (all six emitted follow-ups plus Support custom-brief output), 0 setup errors. Legacy Admin cases passed.
- Fix: pass the already-validated CSKH origin to the follow-up renderer and read the same UI origin for custom-brief text output. No content-generation or posting behavior changes.
- GREEN: `tests.test_admin_marketing_support_back_origin` → `Ran 5 tests in 7.439s — OK`; actual emitted callbacks, registered handler, pending-text result and full Back ancestry are covered with inert planning outputs.
- State: LOCALLY VERIFIED; final batch regression/CI/delivery pending.

### S12.35.77 — Memory search controls validate the same live result snapshot

- Acceptance: search-tagged View/Delete controls validate the actor's current token, TTL and result-ID membership before note reads or pending cleanup. Replaced/expired/foreign/invalid controls recover to Memory without reading a note or changing a current draft. Valid search-results Back releases only the actor's abandoned Memory draft and restores the same result list. Legacy and saved-list navigation remain unchanged.
- Scope: existing Memory search UI origin branches and inert regression; never dispatch `delete_yes` or production note CRUD.
- RED: registered-handler search fixture reported 11 behavioral failures, 0 setup errors: replaced/expired/missing-membership/invalid-time View/Delete, foreign-user origins and abandoned draft on valid Back.
- Fix: the existing search validation now covers search-tagged View/Delete before reads/cleanup; validated search-results Back clears only the actor's Memory draft. SQL ownership and destructive confirmation are unchanged.
- GREEN: six search/saved-list/delete-picker/empty-delete/Start/Menu regressions → `Ran 6 tests in 5.960s — OK`. Invalid callbacks read no note and preserve current pending; valid Back preserves another user's draft.
- State: LOCALLY VERIFIED; final batch/CI/live delivery pending.

### S12.35.78 — Operator → System child round trip preserves Operator parent

- Acceptance: Operator → System → Provider Status or a static System guide → Back restores the same System origin, whose Back returns to Operator. Direct legacy System entry retains Admin Back. Validate unexpected origins before report reads.
- Scope: existing System UI callback-origin propagation and registered menu-handler fixture; report/provider/operator bodies are unchanged.
- RED: 7 behavioral failures, 0 setup errors: six child round-trips lost Operator origin and an invalid guide origin fell through to Main.
- Fix: carry a closed `system|operator` UI origin through the six emitted child entries, Provider Details/Refresh and their Back targets. Unexpected guide origins stop before cleanup/read; legacy origin payloads remain supported.
- GREEN: Operator descendants, legacy Provider Status/details and System guides → `Ran 3 tests in 39.974s — OK`, including public/stale denial and callback byte bounds.
- State: LOCALLY VERIFIED; final batch/CI/live delivery pending.

### S12.35.79 — Final callback-delay diagnosis and explicitly deferred evidence

- Scope: read-only VPS service/timing/load and public Telegram HTTPS measurement. Do not change routing, update concurrency, environment, or engines without a reproduced bottleneck.
- Current runtime: `76f0454fbab5e467f9ca71a0135b6fd05d8d70c4`; bot/web/nginx active, NRestarts=0. Journal now contains menu dispatch events at 2026-10-07 22:14:45/56 and 2026-10-08 09:29:31/09:30:17 +07, so the earlier empty narrow windows were not evidence that instrumentation was absent.
- Measured recent menu dispatch: 306.038, 360.419, 424.794 and 512.953 ms. Guard 33.458–118.951 ms; measured render helper 89.179–101.572 ms. These are server handler phases, not click-to-screen or every-route samples. Generic menu timing does not identify the Account action.
- VPS read at 09:31 +07: load average 0.73/0.78/0.76; available RAM 5235 MiB; bot NRestarts=0. One fresh public `https://api.telegram.org/` request measured TCP 268 ms, TLS 513 ms, first byte/total 734 ms; this is not a bot-method or warm-connection measurement.
- Owner-reported Account → Back remains approximately 2–3 seconds without a matching exact click timestamp. Pre-handler/event-loop wait and client delivery/render are unmeasured. No specific network/device/server cause or hardware purchase is supported.
- DEFERRED FOR OWNER per the latest explicit instruction to record difficult faults at task end: correlate several exact click-to-screen recordings across Account, Admin and a product landing with anonymous timing/ingress data. Keep this unresolved; no claim that all buttons are now smooth. Code fixes proceed to the batch delivery gates.

### S12.35.55 — Admin Billing, Finance, and System UI route recheck

- Scope: validate current emitted Billing/Finance/System controls, labels, authorization and Back origin through their registered menu handlers. Read-only/fake data only; do not approve, reject, charge, call a provider, or execute operator commands.
- Billing: bundled Python unittest ran 6 tests in 12.726s — OK. Both Billing keyboard builders label all eight command destinations as guides; emitted guide controls return to Billing; risk menu Back returns to Billing; stale/public origin is rejected before cleanup; legacy unscoped Back still returns to Admin.
- Finance: bundled Python unittest ran 9 tests in 83.266s — OK. Finance hub, expense/export guide pages, read-only report period buttons, public denial, stale-origin rejection, and Dashboard/Finance parent separation passed.
- Admin Overview: bundled Python unittest ran 1 test in 0.160s — OK. The emitted Admin Overview callback reaches the registered menu handler, renders a report page from inert sample data, and emits Finance/Admin/Home destinations. This verifies only the display/navigation seam, not production report data freshness.
- System/Provider/Operator: four focused registered-handler tests ran 4 tests in 29.083s — OK. Provider Status details/refresh return to System; Operator return preserves its System parent; legacy shortcuts remain accurately labeled as guides; all seven module-emitted controls return to their module.
- Finding: no new in-scope label, authorization-before-render, or parent/Back defect reproduced in these slices.
- Test hygiene: a combined five-module invocation produced no output for about two minutes and was interrupted; NOT_COUNTED. The three focused module invocations above completed independently and provide the counted evidence.
- Limits: fixture-only; no report query against production data, state-changing admin command, financial operation, provider/worker test, or Telegram viewport QA.
- Side effects: provider calls=0, wallet/payment mutations=0, production DB writes=0, jobs=0, real messages=0, engine execution=0.
- Delivery: local cumulative branch; no commit, push, PR, merge, deploy, or restart.

### S12.35.56 — A3/A5 handler-family evidence reconciliation

- Baseline: current GitHub main remains 76f0454fbab5e467f9ca71a0135b6fd05d8d70c4. Its one commit beyond this audit base changes only Product Video worker authority in services/remote_worker_api.py and its focused test; the bot callback/keyboard source is unchanged by that commit.
- Reconciliation: the historical 87-registration candidate table in TELEGRAM_CALLBACK_HANDLER_EVIDENCE_20261006.md marked many handlers NOT PROVEN based only on filename matches. The new dated addendum maps current emitted-handler evidence for safe small-flow families and explicitly preserves PARTIAL/excluded status for untested actions.
- Acceptance: every named handler has an emitted-control/registration/terminal evidence reference or a clear reason it remains outside the approved UI-only boundary; no candidate filename is promoted to proof by itself.
- Result: FreeHub root/maintenance, Account/Pricing, Feedback/Language, Notes/Documents landing/pending, Admin feedback inbox, Ticket, Marketing planner origin, Broadcast Lite read-only panels, and selected Menu/Admin routes have bounded route evidence. Stateful note/document actions, posting/publishing, payment, protected translation/audio/video/image processing and remaining dynamic terminals remain unverified or excluded, not passed.
- A3/A5 remain PARTIAL: this reconciliation closes no live/client QA, every-button terminal, ownership, stale/expiry, or protected-engine coverage gap beyond the cited specs.
- Side effects: documentation-only; no DB/provider/wallet/job/Telegram action, source behavior change, push, PR, merge, deploy, or restart.

### S12.35.57 — Memory empty-delete and document-tool Back callback verification

- Scope: verify that an empty Memory Delete list clears an older `delete_id` pending state; verify document-tool split-page Back releases only the page prompt while preserving selected files/options, and parent Back clears the tool state and returns to Documents. Do not execute file processing or note CRUD.
- Harness repair: `tests/test_memory_empty_delete_state.py` now extracts only `handle_memory_callback` rather than parsing the full large `bot.py` into an AST. This is test-only; product behavior is unchanged.
- GREEN: `python -m unittest tests/test_memory_empty_delete_state.py tests/test_memory_pending_reset_on_start.py tests/test_storage_addon_navigation_callbacks.py -v` ran 3 tests in 3.384s — OK, covering stale Memory Delete state, Start/Menu pending release, and Storage Add-on Back. Four additional direct Document callback checks passed, including exact registered-handler split-page Back and parent Back.
- CI wiring: `ci-main.yml` now runs those same three Memory/Storage unittest modules; remote CI has not run because the cumulative batch has not been pushed.
- Compile/diff: `python -m py_compile` on the five focused Memory/Document/Storage test files exited 0; `git diff --check` exited 0 with only the existing LF→CRLF warnings on unrelated modified tests.
- Result: no new product callback/pending defect reproduced in these narrow cases; the previous empty-delete regression is now practical to run without whole-file AST parsing.
- Limits: fixture/source-extracted evidence only. No Memory note read/write/archive, uploaded file, PDF/Word processing, job, payment, provider, production DB, or Telegram client action was performed. A3/A5 remain PARTIAL.
- Delivery: local cumulative branch; no commit, push, PR, merge, deploy, or restart.

### S12.35.58 — Storage Add-on custom-input Back route

- Scope: exercise the actual Storage Add-on keyboard and registered `storage|` callback for custom input → Back. Verify pending state is released and the user returns to the Storage Add-on menu; verify the menu’s Back target is the Notes parent and accepted by the registered `menu|` route. Do not dispatch payment confirmation.
- GREEN: the CI-target unittest command ran 3 tests in 3.384s — OK; its Storage case verifies the emitted-control/registered-handler round trip, confirms custom draft existed before Back and was absent afterward, and asserts returned menu callbacks match the initial menu.
- CI wiring: the focused Memory/Storage regression step is included in `ci-main.yml`; remote CI remains NOT_RUN until the one batch PR.
- Compile/diff: focused tests `python -m py_compile` exited 0; `git diff --check` exited 0 with existing LF→CRLF warnings on unrelated modified tests.
- Result: no Back-origin or pending-state defect reproduced. No payment callback or purchase helper was reached.
- Limits: one source-extracted fixture path only. No PayOS, wallet/Xu, order, DB, provider, or Telegram client side effect. A3/A5 remain PARTIAL.
- Delivery: local cumulative branch; no commit, push, PR, merge, deploy, or restart.

### S12.35.59 — Admin Internal Archive returns to Notes

- Scope: dispatch the emitted Admin Notes → Internal Archive entry and the emitted Back control through the registered `menu|` handler; verify the archive screen, Back label/target, and return to the exact Notes screen/keyboard. Do not read or mutate archived documents.
- GREEN: `python -m unittest tests/test_admin_root_menu_callback_single_ack.py -v` ran 15 tests in 6.292s — OK. The new route test verifies both emitted callbacks match the registered menu pattern, each dispatch is acknowledged once, and Back returns to the Notes screen with its original keyboard. The Memory/Storage regression command also reran: 3 tests in 4.280s — OK.
- Compile/diff: focused test `py_compile` exited 0; `git diff --check` exited 0 with only existing LF→CRLF working-copy warnings on unrelated modified tests.
- Limits: handler/keyboard fixture only; no archive contents, customer files, DB, payment, provider, or Telegram-client behavior was accessed. A2/A5 remain offline/partial; manual visual QA remains NOT_TESTED.
- Delivery: local cumulative branch; no commit, push, PR, merge, deploy, or restart.

### S12.35.60 — Customer Ticket ownership and Back ancestry

- Scope: use an owned inert Ticket fixture to dispatch the emitted Account → Support → My Tickets list, list → detail, reply/attachment prompt → detail, and malformed/foreign controls through the registered `ticket|` handler. Verify each Back parent, pending cleanup, and fail-closed ownership checks. Do not send a Ticket reply or attachment.
- GREEN: five bounded cases from `tests.test_profile_ticket_ancestry.AccountTicketAncestryTests` ran in 21.280s — OK: Account-origin list Back, detail/list round trip, reply/attachment prompt Back, malformed/foreign rejection, and empty-list/legacy destinations. Read/list helpers and state are fixture-local; calls were asserted absent for these cases.
- Limits: no real customer record, message, attachment, DB, payment, wallet, provider, or job was touched. Completion/submit action terminals remain outside this spec; A3/A5 are still partial.
- Delivery: local cumulative branch; no commit, push, PR, merge, deploy, or restart.

### S12.35.61 — Package group Back dispatches to Gói/Combo

- Scope: take the actual “Gói Ảnh” button emitted by the package menu, dispatch it through the exact registered `pkgcombo:` handler, press its emitted Back, and verify the prior Gói/Combo keyboard returns. Do not open a package detail, checkout, payment, or product engine.
- GREEN: `python -m unittest tests/test_pkgcombo_navigation_registered_callback.py -v` → 1 test in 0.468s — OK. The exact registration pattern accepted both emitted callbacks; the handler rendered the expected group/menu fixture; Back returned to a keyboard with the same callback set and pricing/Home destinations. Pending cleanup was observed only through an inert counter.
- CI wiring: the focused regression is added to the single-batch `ci-main.yml` test sequence; remote CI is NOT_RUN.
- Limits: source-extracted UI fixture only. No package purchase, Xu/wallet, order, provider, job, DB, or Telegram action occurred. Product package detail/purchase callbacks remain untested.
- Delivery: local cumulative branch; no commit, push, PR, merge, deploy, or restart.

### S12.35.62 — Memory empty-list Back returns to Notes/Documents

- Scope: take the actual `memory|delete_start` button from `memory_main_keyboard`, dispatch it through the registered Memory handler with an empty in-memory notes fixture, verify the empty-list Back targets `menu|main_memory`, then dispatch that Back through the registered Menu handler. Confirm only this user's stale Memory pending marker is released.
- GREEN: `tests.test_admin_root_menu_callback_single_ack.AdminRootMenuCallbackSingleAckTests.test_memory_empty_delete_back_returns_to_notes_docs_through_registered_handlers` → 1 test in 0.380s — OK. Both callbacks match their registered patterns; each is acknowledged once; the empty result returned the Notes/Docs Back control and the Menu handler rendered the Notes/Docs parent.
- Regression: full `tests/test_admin_root_menu_callback_single_ack.py` rerun after adding this case → 16 tests in 6.292s — OK.
- Limits: fixture-only empty notes list and pending map. No note records/content, production DB, write/delete, payment, provider, job, or Telegram action occurred.
- CI wiring: included in the existing Admin Route Regressions unittest module; remote CI remains NOT_RUN.
- Delivery: local cumulative branch; no commit, push, PR, merge, deploy, or restart.

### S12.35.63 — Account keyboard layout/source destination recheck

- Scope: read the actual Account root and child keyboard builders; verify row density and Back/Home targets against existing registered-handler evidence. Do not repeat the Referral link/stats/policy dispatches already covered by S12.35.1.
- Source evidence: `main_profile_keyboard` emits six rows (five paired rows plus a final Main-menu row); `profile_child_keyboard` emits one row with Back → `menu|main_profile` and Home → `menu|main`. These destinations are covered by S12.35.1/.38.
- Result: no source-level label/destination mismatch reproduced; no production or test code was changed.
- Limits: static keyboard structure does not prove client-side label wrapping, viewport scroll or polish. The Account → Back 2–3 second report remains unmatched to server timings under A7.

### S12.35.64 — Studio Audio landing and Back/Home navigation

- Contract: dispatch the actual public-root “Studio âm thanh” control through its exact registered callback handler; verify only the showroom landing page and its emitted Back/Home controls; dispatch both navigation controls through the exact registered Menu handler and assert they return to Main.
- Safety boundary: stub only in-memory product-context/pending seams and Telegram reply/edit transport. Do not open Voice/Music child actions or invoke generation, media, provider, Xu, jobs, database, AutoPost or real Telegram behavior.
- Acceptance: emitted control matches the registered pattern; one callback acknowledgement; expected studio landing and actual emitted Back/Home controls; both navigation callbacks return to the public Main keyboard; no business side effects.
- UX observation gate: if Back and Home are duplicate destinations, record the source evidence but do not change the protected Music/Voice UI in this spec.
- GREEN: final `python -m unittest tests.test_admin_root_menu_callback_single_ack -v` → `Ran 17 tests in 7.672s — OK`; `python -m py_compile tests/test_admin_root_menu_callback_single_ack.py` and `git diff --check` exited 0. The new case confirms the root emitter produced `music_quick|showroom|root`; the exact music registration reached the landing handler once, and actual Back/Home values both traversed the registered Menu handler to Main.
- Duplicate-route recheck on merged head: `test_public_audio_studio_landing_back_and_home_return_to_main_via_registered_handlers` ran 1 test in 0.880s — OK. It covers the same emitter → landing → Back/Home → Main path, so this is confirmation of S12.35.64, not a separate spec.
- Finding: Back and Home currently share `menu|main`; no route defect reproduced, but the duplicate navigation control is a UI tidy-up candidate. Not changed because the Music/Voice UI lane is protected.
- Side effects: product-context and pending helpers plus Telegram transport were inert fixture seams; no voice/music child control, provider call, Xu, job, DB, AutoPost, real Telegram action or production user state.
- CI wiring: the containing `test_admin_root_menu_callback_single_ack.py` module is already included in the existing Admin Route Regressions CI step; no workflow edit was needed. Remote CI remains NOT_RUN.
- Delivery: local cumulative branch; no production-code change, commit, push, PR, merge, deploy or restart.

### S12.35.65 — Saved-note detail Back retains saved-list origin

- Trigger: Notes/Documents → Ghi chú đã lưu → open a note → Back; also open Delete confirmation from that detail and Cancel.
- RED: the emitted list item was `memory|view|440`, with no saved-list origin. The focused registered-handler test failed at the expected callback assertion before production code changed.
- Fix: the saved-list route now tags its emitted detail/delete callbacks with the fixed `list` origin. Detail Back returns to `memory|list`; Delete Cancel returns to the same list-origin detail. The duplicate “Ghi chú đã lưu” shortcut is omitted only on this list-origin detail screen, leaving one clear Back action. Legacy detail/command callers and search/delete-start list paths retain their prior callbacks.
- GREEN: `python -m unittest tests.test_admin_root_menu_callback_single_ack tests.test_memory_empty_delete_state tests.test_memory_pending_reset_on_start tests.test_doc_page_prompt_reset_on_start -v` → `Ran 21 tests in 11.220s — OK`. The new route case starts from the actual `main_memory_keyboard` emitter and dispatches actual `memory|` controls through the registered handler; it verifies owner-scoped fixture reads, list → detail → delete confirmation → Cancel → detail → list, one acknowledgement per callback, and no DB connection/event/delete.
- Syntax/scope: focused test `py_compile` and `git diff --check -- bot.py tests/test_admin_root_menu_callback_single_ack.py` exited 0. Full `bot.py` compilation remains a final Ubuntu CI gate because local full-source compilation previously exceeded the environment limit.
- Limits/side effects: no production DB, note mutation/archive/delete, payment, provider, job, AutoPost, engine, or real Telegram activity; callback/client rendering outside this saved-list route remains unverified. A3/A5 remain PARTIAL.
- Delivery: local cumulative branch; no commit, push, PR, merge, deploy, or restart.

### S12.35.66 — Memory delete-picker Cancel returns to the picker

- Trigger: Notes/Documents → Delete → select a note → confirmation → Cancel. Do not dispatch the destructive confirm control.
- RED: the emitted picker item was `memory|delete|441` without its `delete_start` parent. The focused test failed on that exact callback value before production changed.
- Fix: only items emitted by the delete picker carry `|delete_start`. Its confirmation Cancel now returns to `memory|delete_start`, which restores the same picker and its pending choice; the competing “Back to saved notes” shortcut is omitted on this confirmation screen. Default command/detail and saved-list confirmation paths remain unchanged.
- GREEN: focused case `test_memory_delete_picker_emits_a_cancel_route_to_its_parent` → 1 test in 0.477s — OK. It traverses the actual `main_memory_keyboard`, emitted picker item, and confirmation/cancel through the registered Memory handler; Cancel restores the same item callback and picker pending state. `db_connect` is forbidden by the fixture.
- Regression: Memory/Notes/root/Document group → `Ran 22 tests in 11.496s — OK`; focused test `py_compile` and `git diff --check` pass.
- Side effects/limits: fixture-only in-memory pending and owner-scoped note seam. The destructive `memory|delete_yes` edge was never dispatched; no production DB, delete/archive, provider, wallet, job, AutoPost, engine, or Telegram call. Other Memory terminals remain unverified; A3/A5 remain PARTIAL.

### S12.35.67 — Memory search-result detail Back preserves the search origin

- Finding confirmed: actual search-prompt/text → emitted result item → registered Memory callback reproduces the missing origin. The emitted detail route is `memory|view|442`, with no search token; the detail Back therefore targets Notes/Documents, not the originating result list.
- Contract: the exact detail opened from a search result must offer a Back route that restores that same query's results, not another search, the full saved-note list, or Notes/Documents. Stale/foreign origins must fail closed and never show another search result.
- RED: the source-extracted traversal failed at its behavioral route assertion (`memory|view|442` versus the required search-origin route), with no setup error. The only note data is fixture-local.
- Fix: search results now receive a time-bounded per-user token plus the matching note IDs/query; emitted detail and delete callbacks preserve the token. Back safely re-queries only those IDs under the current owner's existing active-note filter. A mismatched, expired, empty, or foreign session returns to the Memory root instead of showing a different search. Delete-confirm Cancel returns to its originating detail; destructive confirmation remains outside scope.
- GREEN: the new actual-emitter/pending-text/registered-handler traversal verifies search → detail → delete confirmation → Cancel → detail → exact same results, plus stale, expired and foreign token fail-closed behavior. The test asserts dynamic callback values stay within 64 UTF-8 bytes even with the maximum signed SQLite ID and 19-digit token.
- Regression: Memory/Notes/root/Start/Menu/Document group → `Ran 23 tests in 12.134s — OK`. Focused test `py_compile` exited 0; `git diff --check` exited 0 (only existing LF→CRLF warnings on unrelated tests).
- Side effects/limits: all notes/query/state were fixture-local; `memory_list_notes` and `memory_fetch_note` were stubbed, no DB connection, delete confirmation edge, provider, wallet, job, AutoPost, engine, customer message, or Telegram request occurred. Does not establish live Telegram rendering or latency; A3/A5 remain PARTIAL.
- Delivery: local cumulative branch; no commit, push, PR, merge, deploy, or restart.

### S12.35.68 — Free Tools prompt-picker Back/Home round-trip

- Contract: start at the actual public root's emitted Free Tools button, dispatch it through the exact registered FreeHub handler, open the static Prompt Library picker, dispatch its Back to Free Tools, then its Home to the public Main menu through the exact registered Menu handler. Back must clear only FreeHub's owned pending marker.
- Scope: menus and owned pending cleanup only. Suggestion data/quota are inert fixtures. Do not choose a suggestion, enter text, upload media, generate/publish, call a provider, charge Xu, or enter AutoPost/media processing.
- Evidence plan: focused source-extracted handler traversal; assert actual emitted callback values match both registered routes, one acknowledgement per callback, and the final destinations/pending state.
- GREEN: `test_free_tools_prompt_picker_back_and_home_round_trip_through_registered_handlers` dispatches the actual public root callback through the exact FreeHub handler, then the actual Prompt Library button and emitted Back through FreeHub, then Home through Menu. It verifies one ACK each, immediate-parent destinations and only the FreeHub pending marker clearing.
- Regression: Memory/Notes/root/Start/Menu/Document group → `Ran 24 tests in 12.687s — OK`; focused test `py_compile` and `git diff --check` exited 0. No mismatch reproduced and no production-code change was made.
- Limits: quota and suggestion results are inert fixtures. No suggestion selection, text input, upload, generation, provider, wallet, DB, job, AutoPost, media engine, or Telegram request occurred. Other Free Tools leaf terminals remain unverified; A3/A5 stay PARTIAL.
- Delivery: local cumulative branch; no commit, push, PR, merge, deploy, or restart.

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
- Delivery: PR [#1383](https://github.com/manhtoangreensky-wq/bot/pull/1383) merged as `5c040c22f2cf07b9edaa9631c219dbf07c15a6ff`; required checks and main-push CI passed. Bot-only deploy [#37496473987](https://github.com/manhtoangreensky-wq/bot/actions/runs/37496473987) succeeded. Read-only VPS verification confirmed exact runtime SHA, bot/web/nginx `active`, `NRestarts=0`, and health `status=ok`. Manual Telegram QA is not claimed.
- Status: MERGED + DEPLOYED + RUNTIME-SHA-VERIFIED.

### S12.19 — Admin Security/DB child Back retains module origin

- Trigger: Admin → Bảo mật / DB → DB trạng thái hoặc Nhật ký bảo mật → Quay lại.
- RED: the production `admin_db_status_keyboard()` and `security_log_keyboard()` both rendered `⬅️ Admin menu` → `menu|admin`, losing the immediate Security/DB parent; cross-links between the two child screens also had no origin.
- Minimal fix: carry validated origin tokens through DB Status, Security Log and backup callbacks; render the matching Back label/destination; reject unknown origins. Legacy command entry defaults to Security/DB. Refresh, DB backup, security log and Menu chính behavior remain unchanged.
- GREEN: Security/DB (5 focused cases), Package Orders, Finance, Broadcast pending cleanup, Runtime, Billing, root and timing regression command → `Ran 24 tests in 40.707s — OK`. Emitted module/sibling controls traverse the actual registered menu handler; Back reaches the actual parent screen, refresh preserves origin and fake backup results return to each emitting screen. Public/unknown origins stop before reads, backup and pending cleanup. Real DB writes, backup creation, provider calls, wallet mutations and production messages: 0.
- Impact: `admin_db_status_keyboard` and `security_log_keyboard` have 2 definitions and 8 production call sites, all in `bot.py`; both optional parameters preserve no-argument command callers. Backup creation and security/audit event bodies are unchanged. Engine/service/provider/worker sources are protected comparators.
- Final verification: focused 5 tests including callback byte limits → `Ran 5 tests in 10.227s — OK`; full `py_compile bot.py` plus both changed test files exited 0; protected comparator passed; legacy security registration assertions passed; `git diff --check` exited 0. Local full pytest suite is not run (bundled Python lacks pytest).
- Scope lock: two UI keyboard families, one menu-handler origin branch, one focused unittest, one compatibility assertion update, one CI invocation and this ledger. Product/Edit/SubDub/Voice/Music engines, AutoPost WIP and PayOS routes are untouched.
- Delivery: PR [#1384](https://github.com/manhtoangreensky-wq/bot/pull/1384) merged as `3557b97a59b19b267f07efe5558269ea6894f9ec`; PR/main checks pass, 163 configured CI tests OK. Bot-only deploy [#37505100609](https://github.com/manhtoangreensky-wq/bot/actions/runs/37505100609) succeeded. Read-only SSH confirms exact SHA, tracked bot.py matches, all three services active/running, NRestarts=0 and health status=ok. Manual Telegram/client QA remains NOT_TESTED.
- Status: MERGED + DEPLOYED + RUNTIME-SHA-VERIFIED.

### S12.20 — module children lose their emitting origin (07/10/2026)

Prerequisite: finish S12.19 delivery. Inert dispatch of actual emitted controls through the current menu handler and actual keyboard builders reproduced 7 additional Back mismatches. Report data was replaced with inert fixtures; no DB/provider/backup/wallet/send operations occurred. The first harness run missed a `re` import; the corrected run exited 0 and measured these destinations. These are navigation failures, not engine failures.

| Opening module | Emitted child action | Expected Back | Actual Back |
|---|---|---|---|
| Queue | `freeze_queue_status` | `admin_queue` | `freeze_queue` |
| Queue | `freeze_queue_help` | `admin_queue` | `admin` |
| Security/DB | `smoke_sales_ready` | `admin_security_db` | `smoke_test` |
| System Ops | `admin_overview` | `admin_system_ops` | `admin` |
| Provider/Worker | `admin_provider_status` | `admin_provider_worker` | `admin_provider` |
| Provider/Worker | `smoke_test` | `admin_provider_worker` | `admin` |
| Provider/Worker | `admin_provider_routes` | `admin_provider_worker` | `admin_provider` |

Acceptance: these 7 entry callbacks retain the emitting module through their UI page, refresh and Back; legacy entry screens keep their existing origin, and invalid/public callbacks stop before cleanup/read/render. Existing queue, provider, report, freeze, backup, financial and product engine operations remain protected. S12.19 delivery was verified before this BUILD. The whole-bot error total remains unknown while other checklist entries are unaudited.

- RED: corrected registered-handler fixture on base `3557b97a` ran 3 test methods with 15 behavioral assertion failures and 0 setup errors: 7 lost-parent cases, 7 unrecognized new-origin fallbacks and invalid-origin recovery. The first harness run had missing fallback stubs; it is not counted as product evidence.
- Fix: 7 module emitters carry a validated parent. A closed, action-specific origin branch changes only the matching Back control and same-page refresh callback after the existing page renderer. Legacy pages and all business controls are preserved; public/invalid contexts stop before reads and cleanup.
- GREEN: focused suite 3 tests OK; adjacent Security/DB, Package Orders, Finance, Broadcast pending, Runtime, Billing, root and latency regressions → `Ran 27 tests in 38.252s — OK`.
- Protected comparator: whole bot source outside `handle_menu_callback` and `ADMIN_CONTROL_MODULES` is byte-equivalent to base; services/providers/remote worker/config and callback registration order unchanged. Provider calls, production-data writes, wallet mutations, real messages and jobs: 0.
- Final full `py_compile bot.py tests/test_admin_module_child_back_origin.py` exited 0; diff check exited 0.
- Delivery: PR [#1385](https://github.com/manhtoangreensky-wq/bot/pull/1385) merged as `406280d6c5ec545915f16786cc9e74538fedf436`; main compile and quality CI pass, 166 configured tests OK. Bot-only deploy [#37508350342](https://github.com/manhtoangreensky-wq/bot/actions/runs/37508350342) SUCCESS; SSH confirms exact SHA, tracked bot.py matches, all three services active/running with NRestarts=0 and health status=ok. Manual Telegram/client QA NOT_TESTED.
- Status: MERGED + DEPLOYED + RUNTIME-SHA-VERIFIED.

### S12.21 — Queue confirmation-guide origins, 07/10/2026

Read-only fixture dispatch from the actual Queue module emitted controls reproduced 3 additional immediate-parent mismatches. These pages only show command instructions; no freeze, refund, provider or financial operation was executed.

| Queue entry | Expected immediate Back | Actual Back |
|---|---|---|
| `admin_confirm_unfreeze_tool` | `menu|admin_queue` | `menu|unfreeze_tool_help` |
| `admin_confirm_freeze_video` | `menu|admin_queue` | `menu|freeze_video_help` |
| `admin_confirm_refund_job` | `menu|admin_queue` | `menu|freeze_queue_help` |

Queued after S12.20 delivery. Acceptance: Queue-entered confirmation guides retain Queue origin through Cancel, Back and instruction acknowledgement; legacy guide-entered controls preserve their current parent. All instruction text and freeze/refund/wallet/provider behavior are protected. No implementation of this next spec is included in S12.20.

- S12.20 delivery was verified before this spec's BUILD. Corrected flow: prompt Back/Cancel → Queue; acknowledgement Back → the same confirmation prompt → Queue. All instruction text and operations remain byte-equivalent.
- RED: baseline focused suite ran 3 methods with 4 behavioral failures and 0 setup errors. Legacy prompt/acknowledgement text and parent assertions passed.
- GREEN: focused Queue and S12.20 suites ran 6 tests OK; adjacent full route subset ran `30 tests in 48.340s — OK`. Real emitted controls pass through the actual callback registration; malformed/public origins stop before cleanup/render; callback byte limits pass.
- Protected comparator PASS: whole source outside the menu UI-origin branch and 3 Queue module entry callbacks unchanged, including confirmation builders/text and all financial/freeze/product engines/services/providers/workers/config/registration order. Provider calls, wallet mutations, DB writes, jobs and real sends: 0.
- Final focused 4 tests in 12.724s OK (including common guards under normal/maintenance fixtures); final full `py_compile bot.py tests/test_admin_queue_confirm_back_origin.py` exited 0; diff check exited 0.
- Delivery: PR [#1386](https://github.com/manhtoangreensky-wq/bot/pull/1386) merged as `877aea89da20037f1c03265e8c2e53a1961f1c0e`; PR/main checks pass, 170 configured CI tests OK. Exact-SHA bot-only deploy [#37511737977](https://github.com/manhtoangreensky-wq/bot/actions/runs/37511737977) SUCCESS. SSH confirms exact SHA, tracked bot.py matches, bot/web/nginx active/running, all NRestarts=0, health status=ok. Manual Telegram/client QA NOT_TESTED.
- Status: MERGED + DEPLOYED + RUNTIME-SHA-VERIFIED.

### S12.22 — Admin feedback inbox navigation and long-message rendering

- Source-extracted `handle_admin_gopy_callback` → `cmd_admin_gopy` replay for empty and populated read-only rows: one callback acknowledgement and one reply, but no `reply_markup` in either branch. Fake DB commit is forbidden, real sends/provider calls are zero.
- Contract: add Back to Support and Home navigation for read-only inbox results; preserve query/filter/authorization/manual status updates and all 15 returned rows. Long results must fit Telegram message bounds, with the final navigation footer.
- RED: 3 assertions failed on empty/populated/filtered results because markup was missing. A 15-long-row fixture independently produced 6,937 visible characters in one message, exceeding the [Telegram 4,096-character limit](https://core.telegram.org/bots/api#sendmessage); its size assertion failed, with no setup error.
- Minimal fix: the empty result uses existing `admin_child_keyboard("admin_support")`; populated results use existing `send_pricing_lines` to split lines and attach the same navigation to the final chunk. Both helpers remain unchanged. SQL, filters, permission checks and manual status-update paths are byte-equivalent to base.
- GREEN: focused 4 methods OK; adjacent Inbox/Queue/module-child/Security/DB/package/finance/broadcast/runtime/billing/root/timing regressions → `Ran 35 tests in 63.974s — OK`. Tests execute actual emitted Góp ý control, exact callback registrations, command body and shared chunk helper; Back/Home traverse the registered menu handler to existing Support/Home renderers. A 15-row result retains every row, each message ≤4,096 visible characters, navigation only on last chunk. Existing feedback authorization/read-only/handbook tests also run.
- Protected comparator PASS: only the 2 inbox rendering lines differ in bot.py; all SQL/status/filter/auth/text, helpers, handlers, engine/service/provider/worker/config source is unchanged. Fake DB permits SELECT only and rejects commit; provider calls, wallets, jobs, production data writes and real messages: 0.
- Final verification: exact final 4-method suite on baseline source reproduces 4 behavioral failures, 0 setup errors (baseline-verifier exit 0). Final full py_compile module via runpy (GC disabled only in compiler process) on bot.py and both changed test files exits 0; diff check exits 0.
- Delivery: PR [#1387](https://github.com/manhtoangreensky-wq/bot/pull/1387) merged as `8faa35eb93ac5a967d1f3f6eb097c735987ecf91`, PR/main checks SUCCESS, 174 configured CI tests OK. Bot-only deploy [37517206697](https://github.com/manhtoangreensky-wq/bot/actions/runs/37517206697) SUCCESS. SSH confirms exact SHA, tracked source matches, bot/web/nginx active/running, NRestarts=0 and health status=ok. Manual Telegram/client QA NOT_TESTED.
- Status: MERGED + DEPLOYED + RUNTIME-SHA-VERIFIED. Other A1–A6 route families and A7 latency remain open.

### S12.23 — Admin Ticket hub and read-only panel navigation (07/10/2026)

After S12.22 delivery: actual Support module emitter `🎧 Ticket admin` → `ticket|admin` was dispatched through its exact registration and production handler/keyboard. The only Back was `menu|admin`; expected immediate parent is `menu|admin_support`. Fixture used no DB/report/provider reads, writes, wallet or real sends. This is one reproduced UI navigation defect, not a ticket operation/engine defect. The correction must cover entry, nested hub return and legacy paths without altering ticket data/status/reply behavior. No implementation is included in S12.22.

- S12.22 delivery was verified before BUILD. The hub now has its logical parent Support; read-only Stats/Templates carry validated UI origins (`admin` or sibling), self/repeat controls retain the same parent, and malformed/public contexts stop before cleanup/read/render. Existing no-argument callers remain supported; ticket list/search/status/reply/file callbacks are unchanged.
- RED: exact final 4-method suite on base `8faa35eb` reproduces 3 navigation/invalid-origin behavioral failures, 0 setup errors; unchanged business-control/pending assertions pass.
- GREEN: Ticket hub, inbox and ticket-origin/reply/note/stale/pagination subset → `Ran 24 tests in 36.372s — OK`; final focused 4 methods → `Ran 4 tests in 4.533s — OK`. Tests use actual module emitter, exact Ticket registration, production handler/keyboard and registered menu Back; reports are inert values. Root/panel/sibling/legacy/repeat/public/bad-origin and 64-byte bounds covered.
- Impact at base: `support_admin_menu_keyboard` definition `bot.py:61027`; 9 production calls at `141059`, `141078`, `141081`, `141094`, `141219`, `184611`, `184643`, `184649`, `184661`, all in bot.py. Two test consumers; one existing pending fixture stub accepts the new optional UI parameters. No shared router refactor.
- Scope comparator PASS: Ticket handler restores byte-equivalent after removing only UI origin validation and read-panel keyboard args; all bot source outside handler/keyboard unchanged, including SQL/status/reply/list/file operations, menu router, product engines/services/providers/workers/config and registrations. Provider calls, wallet mutations, jobs, real sends and production writes: 0.
- Final gates: full py_compile on bot.py/both changed tests exits 0; test files recompile after test-only updates exits 0. Original pending regression list/stats/templates assertions PASS after parsing the same handler only (whole-file AST attempt intentionally interrupted and not counted). Scope comparator and diff check PASS.
- Delivery: PR [#1388](https://github.com/manhtoangreensky-wq/bot/pull/1388) merged as `c0a05ce0910dab0242af593ae17b39be430c0d55`, PR/main checks SUCCESS, 178 configured CI tests OK. Exact-SHA bot-only deploy [37521327174](https://github.com/manhtoangreensky-wq/bot/actions/runs/37521327174) SUCCESS. SSH confirms exact SHA, tracked source matches, all three services active/running, NRestarts=0 and health status=ok. Manual Telegram/client QA NOT_TESTED.
- Status: MERGED + DEPLOYED + RUNTIME-SHA-VERIFIED. Whole-bot goal remains active; S12.24 resumes remaining Admin route evidence.

### A6 platform-copy status — bounded wording fix applied

S12.35.36 replaces the three stale Railway references in `owner_required_text` and `/admin_whoami` with VPS guidance. Two source-extracted fake-role/output checks pass; role checks, configuration, and unrelated Railway-aware runtime paths are untouched. This is not a global terminology rewrite. Full UI wording/layout and Telegram rendering QA remain open; ShopAIKey/Key4U notices remain diagnostic until their policy is known.

### Final latency spec — partial, server/client split preserved

- Current audit baseline A0 is `93919f93d7207f252252f10f9c03d1e8a2d458f8` after PR #1408. The latency events below predate that baseline; telemetry instrumentation is still present, but there were no callback timing events dated 2026-10-07 in the read-only journal query at 21:23 +07.
- After the owner confirmed clicking “Tạo video AI” then “Quay lại”, the anonymous event sequence was `menu|main_video` at `2026-10-06 16:57:18.250 +07`, then `menu|main` at `16:57:20.867 +07`. This is consistent with the two-button round, but there was no exact user click timestamp and the logs contain no identity/callback data, so attribution is not absolute.
- Per-route `callback_latency`: handler `156.054 ms` / `156.930 ms`; acknowledgement `58.973 ms` / `58.998 ms`; awaited `safe_edit_query_message` `76.181 ms` / `79.439 ms`; `render_returned=1` for both.
- `callback_dispatch_timing`: shared guards `35.518 ms` / `33.789 ms`, of which `safe_mode_callback_guard` was `35.405 ms` / `33.724 ms`; total server dispatch `193.403 ms` / `192.631 ms`.
- Bounded historical server sample from 2026-10-06: seven `main`/`main_video` route events. Handler time range `138–358 ms`; awaited edit helper `71–115 ms`; callback ACK `52–223 ms`. The two events with generic dispatch timing were `193.403 ms` and `192.631 ms`. These are only two root routes and seven events, not an all-button latency distribution.
- Supported inference: the measured bot-side processing in those events does not account for a reported 2–3 second wait by itself. It does not measure Telegram-client display, device rendering, carrier/Wi-Fi, the interval before Telegram delivers the callback, or the exact user click-to-screen interval. No network/device fault or hardware purchase is established.
- Coverage: this is one reported two-route sequence plus a few older `main`/`main_video` events, not a latency distribution and not evidence for every bot button. The owner reports the buttons now feel smooth, but no newer callback timing entries or precise user click time were found. Keep A7 PARTIAL until several user-timed samples from more than these two routes can be compared with server phases.
- Following later owner click reports, queries covered 18:08–18:15 and 18:40–18:47 +07 and returned no matching timing records. No precise owner-supplied click time exists for these reports; no additional latency conclusion is drawn.
- Latest Account → Back report: owner replied “đã nhấn”; strict-host read-only SSH queried `2026-10-07 22:17:00–22:19:30 +07` for anonymous callback timing records and returned none. Exact click time/route event cannot be correlated, so this is not a latency sample.
- Latest Account → Back report: owner estimates the click-to-screen delay at 2–3 seconds. No exact click time was supplied. The earlier strict-host query `2026-10-07 22:49:45–22:59:45 +07` had 301 INFO lines but no callback timing event; without a matching timestamp, it cannot be tied to this click and does not locate the delay.
- Latest follow-up: owner again estimates Account → Back at 2–3 seconds after being asked for a precise duration/timestamp. No `HH:MM:SS +07` was supplied, so this still cannot be correlated with anonymous server phases or assigned to bot/server, Telegram, device, or network.
- Interim post-deploy snapshot (2026-10-08 ~15:12 +07): strict-host query aggregated only anonymous `callback_dispatch_timing`/`callback_latency` fields from the preceding two hours and returned `ANON_CALLBACK_EVENTS=0`. This is no sample, not proof of logger failure or an all-button latency result; retain A7 PARTIAL and do not infer a cause.
- Access recovery on 2026-10-06: execution under the actual Windows account `martin\\toann` returned GitHub auth exit 0; the SSH identity and pinned ED25519 host key were already accessible. Earlier denied reads under `CodexSandboxOffline` had incorrectly been treated as missing identity/host trust. No ACL, host-key or credential content was changed. Read-only VPS verification at 19:51 +07 confirmed all three services active/running, `NRestarts=0`, and runtime SHA `392d2eec`.
- No provider call, wallet mutation, production-data write, or customer message was made in either audit spec.

### Production runtime boundary (read-only; excluded from the local UI batch)

- The earlier VPS observation was commit `76f0454fbab5e467f9ca71a0135b6fd05d8d70c4`, parent `93919f93d7207f252252f10f9c03d1e8a2d458f8`, subject `fix(product-video): reconcile R05A zero-submit worker provider authority (R16.10B14N)`.
- A later read-only comparison shows the current worker repo at `ea516e37c1e482b5cb8708d5b7591cf93c1ecfcc`; the range includes PR #1409's `services/video_provider_router.py` change. This is a separate Product Video engine change, not part of the local UI source diff.
- Current runtime evidence and the later worker-inclusive deployment are recorded in S12.35.84. Services are active and health is `status=ok`, but no provider/job/output test was run here. Do not infer engine output correctness from service health.

### S12.35.81 — Account-root route key in anonymous callback timing

- Finding: the registered `menu|` handler and generic callback observer measured Account dispatch under `prefix=menu`, without distinguishing `menu|main_profile`; the existing detailed menu timer covered only `main` and `main_video`.
- Change: the generic observer now emits the fixed `route_key=account_root` only for the exact static callback `menu|main_profile`. All other values remain `unclassified`; callback data, user ID, message, and dynamic suffixes are not logged.
- RED: the new regression had two expected failures because `route_key` was absent for both the exact Account callback and a callback with a private suffix.
- GREEN: timing suite plus the actual Account-root keyboard/registered-handler regression → `Ran 6 tests in 8.200s — OK`. The test checks exact-route labeling and ensures callback/message/user data stay out of logs. The timing test is already wired into `.github/workflows/ci-main.yml`.
- Limits: route instrumentation is deployed, but no owner-timed Account click has been correlated to a live event. Full local `py_compile bot.py` did not complete; PR #1411's complete source-compile check passed. No provider, wallet, production DB, job, customer-message or Telegram action occurred in the fixture.
- Delivery: PR #1411 merged as `ea516e37c1e482b5cb8708d5b7591cf93c1ecfcc`; CI `37733054155` and source compile `37733054147` passed. Bot-only deploy `37733818022` passed with `deploy_workers=false`; independent strict-host readback matched runtime SHA and `bot.py` blob, all three services were active/running with `NRestarts=0`, and internal health was `status=ok`. This proves delivery, not a new latency sample or all-button smoothness.

### S12.35.82 — Account → Packages → Account registered-handler round trip

- Scope: dispatch the actual Account keyboard's `menu|profile_packages` entry through the registered `menu|` handler, then dispatch its emitted Back control and verify that it restores the Account screen and the same Account keyboard. Use an inert package-summary fixture; do not read production packages, open checkout, charge Xu, or call a provider.
- RED: the first fixture run stopped at setup because the extracted dependency map omitted the existing `profile_back_account` label used by `profile_child_keyboard`; no production assertion failed and no runtime route was changed.
- GREEN: after adding that test-only fixture dependency, `test_customer_root_account_renders_actual_keyboard_and_home_returns_to_main` → `Ran 1 test in 1.630s — OK`. The path uses the actual `main_profile_keyboard`, `localized_menu_content`, `profile_child_keyboard`, and registered menu-pattern check. It verifies one ACK per dispatch, `menu|main_profile` Back, `menu|main` Home, and byte-identical Account callback set after return.
- Limits/side effects: source-extracted/inert fixture only; no production DB, package read, checkout, payment, wallet, provider, job, AutoPost, product engine, customer message or real Telegram action. A3/A5 remain partial outside this route; A7 latency remains unresolved.
- Delivery: included in PR #1411, merged as `ea516e37c1e482b5cb8708d5b7591cf93c1ecfcc`, CI-green and included in the exact-SHA bot-only deploy `37733818022`; see S12.35.81 runtime evidence above.

### S12.35.83 — Account referral read-only child round trips

- Scope: dispatch the three actual Account referral controls (`profile_ref_link`, `profile_ref_stats`, `profile_ref_policy`) through the registered `menu|` handler; verify each read-only screen emits Back → Account and Home → Main, then dispatch Back and compare the restored Account keyboard. Referral text and identity are inert fixture values.
- RED: the first fixture run stopped because the extracted namespace lacked the production `BOT_USERNAME` dependency used by the referral-link renderer; no production assertion failed and no live identity was read.
- GREEN: after adding the fixture-only username, the expanded Account regression → `Ran 1 test in 0.696s — OK`; each of the three controls received one ACK, rendered its expected fixture text, emitted exactly `menu|main_profile` / `menu|main`, and restored the same Account callback set.
- Limits/side effects: source-extracted/read-only fixture only; no referral ledger/profile write, database, payment, provider, job, AutoPost, product engine, customer message or real Telegram action. A3/A5 remain partial outside these children; A7 latency remains unresolved.
- Delivery: included in PR #1411, merged as `ea516e37c1e482b5cb8708d5b7591cf93c1ecfcc`, CI-green and included in the exact-SHA bot-only deploy `37733818022`; see S12.35.81 runtime evidence above.

### S12.35.84 — Reconcile latest runtime deploy mode and protected worker scope

- Acceptance: compare current GitHub main/PR checks with VPS bot and worker SHA/source/health/services; identify whether the deployment remained bot-only. Read-only only.
- Evidence: GitHub main, bot repo and worker repo all resolve to `ea516e37c1e482b5cb8708d5b7591cf93c1ecfcc`. PR #1411 is merged; CI runs `37733054155` and `37733054147` passed. Bot-only deploy `37733818022` logged `DEPLOY_WORKERS=false`.
- Scope finding: later workflow-dispatch run `37736313510` targeted the same SHA but logged `DEPLOY_WORKERS=true`, with previous worker SHA `76f0454fbab5e467f9ca71a0135b6fd05d8d70c4`. The worker diff contains `services/video_provider_router.py` from #1409; logs show `WORKER_TARGET_HEALTH_PROVEN` and `SUBDUB_WORKER_TARGET_HEALTH_PROVEN`. This run was not initiated by this audit. It means current runtime is no longer UI-only.
- Live readback: bot/web/nginx/Product Video worker/SubDub worker all `active/running`, each `NRestarts=0`; bot source blob `9cef0f6f9e0f3a0d476642817ce1beb1778c6dfe`; Product Video router blob `578f6e103cb11997d497de86238b55aab4e3d9a5`; deployment endpoint `http://127.0.0.1:8080/health` returned `status=ok`. Public `https://tg.toanaas.vn/health` returned 403 and is not the workflow health gate.
- Limits: no provider/API call, Product Video/SubDub job, output artifact, DB/wallet change, customer message, Telegram client test, or deploy/restart was initiated by this audit. Service health does not prove a video/SubDub artifact or end-to-end function. Preserve A7's no-cause conclusion.

### S12.35.86 — Product progress status callback side-effect boundary

- Scope: source-review `progress|status` only to determine whether it is safe evidence for a UI-only audit. Do not dispatch a live callback or enter a real product job.
- Evidence: `handle_product_progress_callback` routes Music to `maybe_deliver_music_progress_job`, which can call `music_progress_refresh_job_status(..., allow_provider_poll=True)` and poll/download through `poll_music_suno_async_job`; the SubDub branch can call `subdub_recover_existing_mp4_delivery`, finalize a delivered panel, and send a receipt.
- Finding: the status button is not uniformly read-only. It may refresh provider state or recover/deliver an existing artifact depending on job state. This is a processing seam, not a demonstrated defect; no UI/engine behavior was changed.
- Limits: no real callback/job/provider/Telegram action was run. Candidate tests import `bot.py`, and the bundled Python runtime has no `pytest`; no candidate test was executed in this pass. Keep this action path with its owning Product/Music/SubDub validation and leave A3/A5 processing terminals explicitly unverified.

### S12.35.87 — SubDub entry and conditional no-subtitle navigation

- Scope: verify only the safe menu-entry and conditional no-subtitle UI transitions through the actual registered videodub callback. Do not enter confirmation, progress/status, delivery, provider, or engine-processing branches.
- Entry evidence: the actual publish_package_keyboard emitter produces videodub|start; the registered handler renders the SubDub menu, acknowledges once, and emits Back to menu|main_video for the Video origin.
- Conditional-route evidence: video_dubbing_missing_existing_subtitle_keyboard emits videodub|path|no_subtitle for the combined subtitle+dub mode; the registered handler moves fixture state to no_subtitle_menu and renders the next videodub|no_subtitle_flow|... control. The control is conditional on the missing-subtitle screen, not part of video_dubbing_source_keyboard.
- GREEN: source-extracted registered-handler entry and conditional no-subtitle traversals both passed with in-memory state and intercepted rendering/acknowledgement. tests/test_subdub_voice_child_back.py → Ran 4 tests in 6.658s — OK.
- Historical source-only checks: direct invocation of 8 checks in tests/test_p0_subdub_live10_menu_route_isolation.py originally returned 5 pass/3 fail. S12.35.91/.92 corrected the two stale UI-emitter expectations (Audio-layer Back target and conditional NO_SUBTITLE emitter); the rerun is 7 pass/1 fail. The sole remaining failure is an obsolete terminal-panel source marker (`ValueError: substring not found`); keep that protected delivery seam unexecuted and do not treat the assertion as production failure. This legacy file is not in the configured CI list.
- Limits/side effects: fixtures only; pending state and product context were in-memory, rendering/acknowledgement intercepted, provider/job/DB/wallet/production-data/customer-message/real Telegram-send counts are 0. No callback defect reproduced on these paths. This does not prove client rendering, latency, every SubDub control, or product output; A3/A5/A6/A7 remain partial/open.
- Delivery: no production source/test delta, PR, merge, deploy, or restart. Current main/runtime matching evidence remains in S12.35.84; no redeploy is needed.

### S12.35.88 — Voice Settings Back preserves source and pending state

- Contract: exercise only the settings UI path for speed/volume input prompts, prompt Back to the settings screen, parent Back to the prior source screen, and stale Back while a different pending action/context is active. Do not invoke generation, provider, price summary, wallet, job, DB, or real Telegram behavior.
- Evidence: `tests/test_voice_settings_input_back.py` source-extracts the actual keyboard functions and registered `handle_music_quick_callback`, while generation/provider/price-summary functions are hard-failed. All 19 explicit parameter combinations/assertion calls passed using the bundled standard Python (`DIRECT_FIXTURE_ASSERTIONS_OK count=19`).
- Finding: prompt Back releases only the matching input; saved voice options remain unchanged; parent Back returns to the previous source screen; an old settings Back does not clear unrelated pending action/context. No callback defect reproduced and no production source/test file changed.
- Limit: `pytest` is absent from the available interpreter; this was direct function invocation with a no-op `pytest.parametrize` decorator shim, not pytest or CI. It proves fixture assertions only, not Telegram-client render or live latency.
- Side effects: all context/pending state was in-memory; generation/provider/quote/wallet/DB/job/AutoPost/real Telegram calls = 0.
- Delivery: no source delta, PR, merge, deploy, or restart. Run the actual test module in the consolidated batch CI; A3/A5 remain partial.

### S12.35.89 — Reconcile stale current-main SHA in callback evidence

- Finding: the A3/A5 evidence document described `76f0454…` as current main even though fresh GitHub and VPS reads both show `ea516e37…`; its old source comparison remains useful only as a historical snapshot.
- Fix: relabel `76f0454…` as the initial historical reconciliation and point current main/runtime truth to `ea516e37…` and S12.35.84. No callback or engine source changed.
- Verification: fresh read-only GitHub PR/main and strict-host VPS checks agree; PR #1410/#1411 remain merged with required checks successful. `git diff --check` is the local documentation gate.
- Delivery: report-only local change; no PR/merge/deploy because A3/A5/A6/A7 and final batch gates remain open.

### S12.35.90 — Ticket send/file repeat guard through registered handler

- Contract: exercise only admin Ticket reply-send and attachment-send controls through the exact `ticket|` handler registration. Assert concurrent duplicate send is single, stale and non-admin controls do not send, failed sends release the in-flight guard and remain retryable, unrelated pending state survives, and sequential reopen remains available. All sends are intercepted by `FakeBot`; ticket/message state is fixture-local.
- RED/setup finding: initial reply-send concurrency run errored in 2/2 tests after FakeBot send, and stale-preview run errored in 2/3 successful-send cases: both test stubs accepted only one positional renderer argument while production accepts `(ticket, source, list_offset)`. The independent file-send suite passed 6/6 initially. These were fixture setup errors, not product assertion failures.
- Minimal correction: changed only the two test stubs to match the production renderer signature; no `bot.py` change.
- GREEN: `python.exe -B -S tests\\test_support_ticket_send_concurrency.py -v` → 2 tests in 2.445s, OK; `python.exe -B -S tests\\test_support_ticket_file_send_concurrency.py -v` → 6 tests in 4.638s, OK; `python.exe -B -S tests\\test_support_ticket_send_matches_preview.py -v` → 3 tests in 5.960s, OK. These are standard-library unittest tests, not pytest.
- CI gate: Owner approved adding all three modules to `.github/workflows/ci-main.yml` under “Small Navigation and UI Closure Regressions”; the exact list is now wired. Consolidated local rerun: `-B -m unittest tests.test_support_ticket_send_concurrency tests.test_support_ticket_file_send_concurrency tests.test_support_ticket_send_matches_preview` → 11 tests in 21.488s, OK. Remote CI has not run for this local workflow change.
- Result/limits: no duplicate-send or retry defect reproduced in these fixtures. Exact emitter/registered-handler route and callback payloads are checked, but this is not real Telegram delivery or client-latency evidence.
- Side effects: FakeBot/in-memory only; production Telegram=0, DB=0, provider=0, wallet=0, job=0, AutoPost=0.
- Delivery: two one-line test-only fixes and local report/state updates; the three tests are included in the Owner-approved consolidated CI batch. CI remains pending. No production source delta, push/PR/merge/deploy/restart.

### S12.35.91 — SubDub Audio-layer Back returns to its immediate parent

- Contract: emit the original-audio layer keyboard, click its Back control through the exact registered `videodub|` handler, and assert the `audio_mix` state plus the restored Audio mix parent controls and exactly one callback acknowledgement. This is UI navigation only; TTS/ASR/provider/processing calls are forbidden by the fixture.
- Baseline: a legacy source-only assertion expected `menu|main` on the layer keyboard, while the current label says “Âm thanh” and callback is `videodub|audio_mix`.
- Files allowed: `tests/test_subdub_voice_child_back.py`, the one stale source assertion in `tests/test_p0_subdub_live10_menu_route_isolation.py`, the safe-navigation test list in `.github/workflows/ci-main.yml`, and this checklist/state only. `bot.py` and all processing/engine/provider/worker code stay protected.
- Result: exact registered-handler dispatch sets `step=audio_mix` and renders the parent Original/Dub controls with one callback ACK. The immediate-parent route is correct; no Home shortcut is needed and no production defect was reproduced.
- GREEN: focused case → 1 test in 21.884s, OK; entire `tests.test_subdub_voice_child_back` → 5 tests in 20.321s, OK. The test uses extracted handler code and in-memory FakeBot/query only.
- CI gate: `tests/test_subdub_voice_child_back.py` is included in the same safe-navigation CI step alongside the three Ticket modules. Remote CI remains pending until the consolidated batch is pushed.
- Limits/side effects: `bot.py` unchanged; no processing, provider, ASR/TTS, job, production DB, wallet or real Telegram activity.
- Status: locally verified and wired for batch CI; no push/PR/merge/deploy/restart.

### S12.35.92 — SubDub no-subtitle source assertion targets its actual emitter

- Contract: the source-only UI assertion must check the no-subtitle callback on `video_dubbing_missing_existing_subtitle_keyboard`, not `video_dubbing_source_keyboard`; retain the existing exact handler traversal evidence from S12.35.87.
- Baseline: `video_dubbing_source_keyboard` emits the has-subtitle path only; the conditional missing-subtitle keyboard emits `videodub|path|no_subtitle` and Back/Home. The old test incorrectly expected both choices on the source keyboard.
- Allowed change: one source-test assertion only; no `bot.py`, handler, engine, provider or runtime behavior change.
- Verification: invoke the exact source assertion and all eight historical static assertions; preserve any remaining protected-terminal failure as excluded, not fixed here.
- GREEN: target source assertion → `TARGET_SOURCE_ASSERTION_OK`; all eight historical checks → 7 pass/1 fail. The remaining failure is only the protected terminal-panel source marker, not a UI route failure.
- Status: locally verified; no runtime/source behavior change, push, PR, merge, deploy or restart.

### S12.35.93 — Public Voice Hub Back/Home round trip

- Contract: dispatch the Voice Hub control emitted by the customer Audio Studio root through the exact registered `music_quick` handler. Verify its Back returns to Audio Studio through the same registered handler and Home returns to the exact main-menu keyboard through the registered menu handler, with one ACK per press.
- Safety boundary: navigation only. Do not click TTS, STT, voice generation/clone, profile mutation or provider/action controls. Use in-memory context and intercepted message rendering.
- Verification: run the new focused case and the existing Audio Studio landing Back/Home regression. `tests/test_admin_root_menu_callback_single_ack.py` is already included in the safe UI CI workflow list.
- Result: the emitted Voice Hub control reached `handle_music_quick_callback`; its Back returned to Audio Studio through the same handler, while Home reached the exact main keyboard through `handle_menu_callback`. Each callback was acknowledged once.
- GREEN: new focused case → 1 test in 3.140s, OK; adjacent Audio Studio landing Back/Home case → 1 test in 3.130s, OK. Both use in-memory state/context and intercepted rendering.
- CI: this test file is already in the safe UI CI list; remote CI remains pending for the consolidated batch.
- Limits/side effects: TTS/STT/generation buttons were not pressed; provider/DB/job/wallet/real Telegram calls = 0; `bot.py` unchanged.
- Status: locally verified; no source behavior change, push, PR, merge, deploy or restart.

### S12.35.94 — Customer Ticket category prompt Back

- Contract: dispatch the Ticket category chooser's emitted category through the exact registered `ticket|` handler, verify its prompt, then press the emitted Back and confirm the same category keyboard returns and only the fixture user's pending Ticket marker is cleared. No text submission or ticket creation.
- Test authored: `tests/test_admin_root_menu_callback_single_ack.py::test_customer_ticket_category_prompt_back_restores_category_menu`; the test module is already in the safe-navigation CI step, so the workflow allowlist is unchanged.
- Source review: `support_ticket_input_keyboard` emits `ticket|start`; `handle_ticket_callback` clears only `support_ticket:<uid>` on `start`, then renders `support_ticket_menu_keyboard`. Pending state is fixture-local; no action-capable Ticket seam is needed.
- GREEN: focused method → `Ran 1 test in 0.704s — OK`; full `tests.test_admin_root_menu_callback_single_ack` module → `Ran 27 tests in 19.239s — OK`. Used an existing workspace venv Python in `-B -S` mode (no bytecode/site packages). Exact registered Ticket callback restored the category set and cleared only fixture pending state; no Back defect reproduced.
- Safety: no ticket submit, production DB, real Telegram, customer message, provider, wallet, job, engine, deploy or restart.
- Status: locally verified; remote CI for the consolidated batch remains pending. Continue reachability review before any submission path.

### S12.35.95 — Customer Ticket category-picker entry reachability

- Source evidence: public Support keyboards emit `support|ticket`; `handle_human_support_callback(action=ticket)` opens the existing `general_support` free-text form and preserves its Support Back. The category picker is emitted by `support_ticket_menu_keyboard` and rendered by `handle_ticket_callback(action=start)`, but the only `ticket|start` emitter in `bot.py` is the category form's own Back button. `/support_ticket` is admin-only ticket lookup, not customer intake.
- Fixture evidence: the existing Account Support form case passed 1 test in 18.580s — OK; it opens the direct general-support form without submitting text. S12.35.94 separately confirms the category prompt/Back loop itself works.
- Finding: the public one-step ticket form is operational; no broken callback was reproduced. The separate category picker has no public entry from Support and is therefore not discoverable; this may be intentional legacy UI, so it is not labeled a production defect without owner intent.
- Owner choice requested before any UI change: retarget “Tạo Ticket” to the category picker (with “Khác” for free-form requests), or preserve the direct one-step general-support prompt. No production source change was made.
- Safety: source review and inert prompt fixture only; no ticket submit, DB, real Telegram, payment, provider, AutoPost or product engine action.

### S12.35.96 — Reconcile current root-menu layout expectation

- Contract: inspect `localized_main_menu_keyboard` against the current `test_translation_main_menu_hotfix.py` assertions and an inert source-extracted fixture; close the historical row-count/order discrepancy only if source and expectations agree. Do not change menu layout or translation behavior.
- Source review: public root emits eight rows (one singleton and seven pairs), retaining all callbacks plus one community URL; Admin adds a separate singleton `menu|admin` row. The current pytest test asserts the same row shape and relevant positions for its listed locales. This is static/source comparison, not Telegram viewport QA.
- GREEN: `tests.test_admin_root_menu_callback_single_ack.AdminRootMenuCallbackSingleAckTests.test_public_main_menu_small_flow_callbacks_match_their_registered_handlers` → `Ran 1 test in 0.422s — OK`; the fixture extracts the current production keyboard function without importing bot runtime, asserts the eight-row shape and selected shortcuts, and matches safe emitted callbacks to their registered patterns.
- Limitation: the direct pytest case in `test_translation_main_menu_hotfix.py` did not return a result during local bot-module import and was stopped; it is NOT counted as pass. Full CI remains required for the consolidated batch. No production source or UI changed.
- Safety: no provider, job, wallet, DB, AutoPost, product engine, real Telegram, deploy or restart side effect.

### S12.35.97 — Customer Translation root and language-hub navigation

- Contract: start from the actual public main-menu keyboard, dispatch its emitted `menu|translate` callback through the registered menu handler, then use the emitted language-hub entry and emitted Back/Home controls. Verify the direct Translation hub is restored on Back and Main on Home. Navigation only; do not select a translation target, submit input, start sessions, or enter SubDub/provider paths.
- RED review: the existing menu test checked the root callback and static Translation content separately; the source-extracted root-route dispatcher case omitted `menu|translate`. This was a coverage gap, not a reproduced production failure.
- GREEN: focused test `test_customer_translation_entry_and_hub_back_home_dispatch_registered_menu` → `Ran 1 test in 0.804s — OK`; entire `tests.test_admin_root_menu_callback_single_ack` module → `Ran 28 tests in 20.334s — OK`. The main-menu and Translation renderer/handler functions are source-extracted; `enter_product_context`, pending cleanup, and the generic two-column markup helper are inert fakes. Callback values and registered dispatch are checked; Telegram viewport/row layout is not.
- A first fixture attempt expected “Dịch”; the source emits “Trung tâm dịch”. The test expectation was corrected to the actual text; this was a fixture mismatch, not a product RED.
- Safety: no translation input, provider, TTS/ASR, product job, wallet, production DB, AutoPost, real Telegram, deploy or restart.

### S12.35.98 — Free Tools QR prompt returns to Utilities

- Contract: dispatch the emitted Free Tools `open_utilities` entry and its QR child through the exact registered `freehub|` handler; verify the QR input prompt emits Back to Utilities, Back restores the same four utility choices, and the next Back returns to the Free Tools root. Only the current fixture user's pending input may be cleared.
- Coverage finding: the previous test asserted the utility selector's callback set and Back to root, but did not dispatch an individual utility control through the handler. This was a route-evidence gap; no production callback defect was reproduced.
- GREEN: existing `test_free_tools_prompt_library_back_stack_restores_parent_and_exact_results` dispatches the QR child and its Back through the exact registered handler. The same focused method now also covers rate and Avatar routes: `Ran 1 test in 3.354s — OK`; final `tests.test_admin_root_menu_callback_single_ack` → `Ran 28 tests in 42.457s — OK`; `tests.test_freehub_maintenance_main_pending_reset` → `Ran 1 test in 1.791s — OK`.
- Scope/side effects: actual current `free_hub_main_keyboard` and `handle_free_hub_callback` were source-extracted; rendering and pending maps were in-memory. QR generation/input, weather/rate services, network, provider, DB, wallet, job, AutoPost, product engines and real Telegram were not invoked. No production source changed.
- Status: offline navigation evidence added to the existing CI-listed root/menu module; final consolidated remote CI and live Telegram/client QA remain separate gates.

### S12.35.99 — Free Tools Avatar style selection stays in its prompt

- Contract: from the emitted Utilities menu, dispatch Avatar and an emitted style choice through the exact registered `freehub|` handler; verify the displayed style and fixture pending state update, then Back restores Utilities and clears only this user's pending state. Do not send character text, generate an image, or invoke an image/provider route.
- Coverage finding: the utility chooser emitted Avatar controls, but existing safe tests had not dispatched a style choice or its Back. No production defect was reproduced.
- GREEN: the focused existing Free Tools back-stack method, now covering QR, Avatar and rate routes, → `Ran 1 test in 3.354s — OK`; final root/menu module → `Ran 28 tests in 42.457s — OK`.
- Scope/side effects: production keyboard and `handle_free_hub_callback` are source-extracted; only in-memory pending state and fake rendering were used. No image generation/provider, user input, network, DB, wallet, job, AutoPost or real Telegram action.
- Status: offline route evidence added to the existing CI-listed test; remote CI and Telegram client rendering remain pending.

### S12.35.100 — Free Tools exchange-rate prompt returns to Utilities

- Contract: from the emitted Utilities keyboard, dispatch `util_rate`, then its emitted `util_rate_input` control through the registered `freehub|` handler; verify the input prompt and Back to the same Utilities controls with only this user's pending state cleared. Stub the overview formatter; do not call exchange-rate services or submit an amount.
- Coverage finding: previous coverage checked that the Rates control was emitted, but had not dispatched the overview/input prompt pair through the handler. This is a coverage gap, not a reproduced production defect.
- GREEN: focused existing Free Tools back-stack method → `Ran 1 test in 3.354s — OK`; full `tests.test_admin_root_menu_callback_single_ack` → `Ran 28 tests in 42.457s — OK`.
- Scope/side effects: current keyboard/handler source extracted; `format_exchange_rate_overview` replaced with an inert fixture; no network, quote/payment, wallet, provider, DB, job, AutoPost, product engine or Telegram side effect.
- Status: locally verified navigation evidence in the CI-listed test; no production source changed, remote CI remains pending.

### S12.35.101 — Free Tools weather prompt returns to Utilities

- Contract: dispatch the emitted `util_weather` and `util_weather_input` controls through the exact registered `freehub|` handler. Check the overview, location-input prompt, emitted Back, restored Utilities choices, and cleanup limited to this fixture user's pending state. Replace weather retrieval with a deterministic in-memory stub; do not call the network or submit a location.
- Coverage finding: the emitted weather control was present in the Utilities keyboard but had not been dispatched through the registered handler in this safe-navigation case. This is an evidence gap; no production callback defect was reproduced.
- GREEN: focused existing Free Tools back-stack test → `Ran 1 test in 1.005s — OK`; full `tests.test_admin_root_menu_callback_single_ack` module → `Ran 28 tests in 28.245s — OK`. The stub recorded the three overview city lookups; the input prompt caused no additional lookup; Back restored Utilities and cleared only the current fixture user's pending state.
- Scope/side effects: current keyboard and callback handler were source-extracted; `fetch_weather_report` was replaced by an inert fixture. No Open-Meteo/network, location submission, provider, DB, wallet, job, AutoPost, product engine, or real Telegram action.
- Status: locally verified; no production source changed. Remote CI and Telegram-client rendering remain pending.

### S12.35.102 — Free Tools Meta/Caption/Ideas suggestion Back

- Contract: dispatch the three controls actually emitted by `free_hub_main_keyboard` through the exact registered `freehub|` handler. Verify each opens the correct local suggestion task, its emitted Back returns to the Free Tools root, and only this fixture user's pending state is cleared. Do not choose a suggestion, submit custom text, or continue to content generation.
- Coverage finding: the Free Tools root emitted Meta, Caption, and Ideas, but existing coverage dispatched only the general Prompt Library picker; this route-family gap is not a reproduced production failure.
- Fixture RED: the first run raised `NameError` because the source-extracted handler fixture omitted `normalize_free_hub_task_type`; no product assertion ran. Added an identity stub limited to the already-normalized Meta/Caption/Ideas task names.
- GREEN: focused prompt/navigation test → `Ran 1 test in 0.327s — OK`; full `tests.test_admin_root_menu_callback_single_ack` module → `Ran 28 tests in 16.090s — OK`. All three emitted callbacks reached the expected local suggestion task and Back restored the exact Free Tools root; another user's pending state remained unchanged.
- Scope/side effects: quota and suggestion data were in-memory stubs; no suggestion selection, content submission/generation, provider, network, DB, wallet, job, AutoPost, protected engine, or real Telegram action.
- Status: locally verified route evidence; no production source changed. Remote CI and Telegram-client rendering remain pending.

### S12.35.103 — Free Tools Notes/Docs immediate-parent Back

- Contract: dispatch the emitted Free Tools → Notes/Docs control through the registered menu handler, open the emitted Create Note prompt through the registered Memory handler, press prompt Back, then press the Memory root Back. Verify it returns to Free Tools; verify ordinary Main-origin Memory still returns to Main. Verify `/start`, `/menu`, `/memory`, and Free Tools exit clear the temporary origin. Keep note/document operations inert.
- RED: after the prompt Back, the Memory root emitted `menu|main`; expected immediate parent was `freehub|main`. The first fixture execution stopped on a missing `ui_text` stub (`NameError`), so it did not count as behavioral RED. After correcting that fixture dependency, the registered-handler test reproduced the wrong Back target.
- Correction: tag the Free Tools Notes/Docs entry with its parent origin, preserve that origin across the prompt → Memory-root return, render the root Back to Free Tools, and clear the temporary UI origin on Free Tools exit, `/start`/`/menu` (shared `cmd_start`) or `/memory`. Main-origin Back remains unchanged.
- GREEN: focused origin-flow and fresh-command reset regressions → `Ran 2 tests in 0.935s — OK`; full `tests.test_admin_root_menu_callback_single_ack` → `Ran 30 tests in 12.859s — OK`. A new `/menu` assertion failed against pre-S12.35.103 committed source with the expected stale-origin assertion, then passed on the current handler. Consolidated local rerun of root/menu + three Ticket modules + SubDub voice-child navigation → `Ran 46 tests in 33.547s — OK`; full `py_compile bot.py` completed with exit code 0. `git diff --check` exited 0.
- Scope/side effects: changed only `bot.py` navigation/callback UI and its source-extracted tests. No note CRUD, PDF/Word tool, provider, wallet, production DB, job, AutoPost, product engine, customer message or real Telegram action.
- Status: local source/navigation fix verified. Manual case `UI-FREEHUB-MEMORY-ORIGIN-01` is recorded in `KIEM-THU/DANH-SACH-CASE.md` and the tester guide. The root/menu suite and three Owner-approved Ticket modules plus the previously approved SubDub navigation test are wired in the safe-navigation CI step. Remote batch CI, Telegram-client visual QA, Account latency correlation and final delivery gates remain open; no push/PR/merge/deploy/restart.

### S12.35.104 — Public main-menu safe-route reconciliation

- Contract: reconcile the current public main-menu callback inventory with registered handlers and the existing focused route evidence. Separate menu/landing navigation from AutoPost WIP, stateful actions and protected product processing. Do not dispatch generation, payment, delivery, polling, or other action-capable terminals.
- Finding: no uncovered safe public-root navigation callback was found. Existing registered-handler tests cover customer root entry screens, Translation, Image, Account, Chat Pro, Support, Feedback, Guide, Audio Studio/Voice Hub, Free Tools, Pricing, Memory and the Video root/back timing seam. The static inventory's AutoPost WIP and downstream stateful/protected terminals remain explicitly excluded, not passed.
- Evidence: consolidated local focused rerun → `Ran 46 tests in 33.547s — OK` across root/menu, three Ticket, and SubDub child-Back modules; root/menu module contributed 30 tests. `py_compile bot.py` completed with exit code 0; `git diff --check` exited 0. No new behavior change or RED reproduced.
- Limits: source/registered-handler fixtures do not prove Telegram viewport rendering, client/network latency, full product output, or action-capable terminal behavior. A3/A5 remain partial outside the reconciled safe root routes; A6 visual/client QA and A7 timed latency correlation remain open.
- Status: report-only source/test reconciliation complete; no delivery action performed.

## Current next steps

1. PR #1410/#1411 bot-only deliveries are verified. Current main/bot/worker SHA is `ea516e37…`; #1411 CI `37733054155` + source compile `37733054147`; bot-only deploy `37733818022`. A separate later run `37736313510` used workers=true and changed worker runtime; do not repeat it under this UI goal. The old `76f0454…` in the evidence inventory is historical, corrected by S12.35.89. This does not close the whole audit.
2. Account → Packages/Referral by S12.35.82–83; Audio Studio landing Back/Home by S12.35.64; Voice Settings Back/pending preservation by S12.35.88 (direct fixture checks, not pytest/CI); Ticket reply/file repeat guard by S12.35.90 (unittest + FakeBot; CI pending). S12.35.91 verifies SubDub Audio-layer Back; .92 corrects the stale conditional no-subtitle emitter assertion; .93 verifies public Voice Hub → Audio Studio Back and Main Home; .94 verifies Ticket category prompt Back through its registered handler. Remote CI and client UX remain separate gates.
3. S12.35.98–.104 close the reviewed Free Tools QR/Avatar/rate/weather/Meta/Caption/Ideas and Notes/Docs Back routes and reconcile the safe public root routes. Continue only independent A3/A5 evidence gaps; preserve current Support intake behavior pending Owner choice and keep stateful actions/protected processing explicitly unverified/excluded.
4. Keep Product progress `progress|status` outside read-only UI dispatch: Music can refresh/poll and deliver; SubDub can recover/re-deliver an MP4. S12.35.86 records the source boundary; no action was executed.
5. Continue A6 wording/layout review from source/emitted keyboards; S12.35.96 closes the historical root-menu row-count/test discrepancy only. Telegram-client viewport/wrapping and remaining copy/layout review are still unverified; do not make speculative visual changes or alter ShopAIKey/Key4U policy.
6. Keep A7 open: S12.35.81 now adds the Account route key in runtime logs, but needs owner-timed samples correlated with server events. No post-deploy Account sample exists yet. Do not assign the reported 2–3s to bot, Telegram, device, or network without correlation.
7. Keep the goal ACTIVE. No new merge/deploy/restart before remaining ordered checklist and final scope review; batch cadence remains consolidated. Product Video/SubDub output correctness is outside this UI audit and was not exercised.

## Historical execution-order notes

1. S12.11 (#1376) is merged/deployed and its exact runtime SHA is verified; its release scope includes ancestors #1367–#1375.
2. S12.12 (#1378) is merged, deployed, and runtime-SHA verified; no dependent spec starts with an unknown runtime.
3. S12.13 (#1379) is merged, deployed and runtime-SHA verified at `2099eb3`; its 3-label source comparator and CI gates passed.
4. S12.14 (#1380) is merged/deployed/runtime verified at `74a8d86f`; 8 emitted guide controls, Back/public guards, source comparator and CI gates passed.
5. S12.15 (#1381) is merged/deployed/runtime verified at `0929d61a`; S12.16 inventories registrations but is not whole-bot route proof.
6. S12.17 is merged/deployed/runtime verified at `979c0ee5`; its stale media result controls are closed.
7. S12.18 (#1383) is merged/deployed/runtime verified at `5c040c22`.
8. S12.19–S12.29 (#1384–#1397) are merged/deployed/runtime verified; latest runtime `ae01c60d`. S12.30 Account pricing origin is locally verified and requires PR/CI/merge/deploy. S12.28 adds bounded offline ACK evidence; those coverage states are not error counts or whole-bot completion.
9. Continue A1–A5 for remaining admin/customer routes, pending-state expiry/stale/repeat behavior, preserving protected product lanes.
10. Finish A6 UI/UX consistency review and update this ledger with evidence, not assumptions.
11. Close A7 only after multiple user-timed samples can be compared to anonymous server phases; separate server, Telegram render and client/network wait.
12. Complete A8 only after every checklist row has evidence and delivery states are separately verified.
