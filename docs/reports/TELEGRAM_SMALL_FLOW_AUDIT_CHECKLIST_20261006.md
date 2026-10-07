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
| A0 | Active main/runtime baseline: `938f6813717831e17cb564c8de9172e6c22906df` after Account Top-up Back PR #1405; bot blob `e3532eae3ff45fdf7617096c9a2d8c0a5b87bd5c`. Exact-SHA deploy #37582086304 succeeded with workers excluded; SSH at 07/10 13:39 +07 verified tracked source, bot/web/nginx active, zero restarts and health `ok`. Historical AST registration inventory at `0929d61a` measures 87 direct registrations, 85 distinct expressions and 83 literal patterns; the old emitter snapshot `4f1455ed` had 3,981 constructors/821 dynamic expressions/0 unmatched static callbacks. These inventories and old line locations do not prove current route behavior. | Per-registration matrix in `TELEGRAM_CALLBACK_HANDLER_EVIDENCE_20261006.md`; route verdicts remain partial/unproven. |
| A1 | Admin screens: verify each visible action label matches its handler; test emitted callback, authorization, state transition, and error/stale path. | PARTIAL — report/overview, root/help/package, Queue/Finance guide labels and feedback/access samples have evidence below; full visible-action matrix remains open. |
| A2 | Admin Back/Home: verify immediate parent and preserve list/filter/page context; test prompt and preview exits without performing the underlying action. | IN PROGRESS — ticket-origin specs S12.6–S12.10 (#1367–#1374) are in #1376; S12.12 merged/deployed in #1378 at runtime SHA `392d2eec`; S12.18 fixes Package Orders origin and S12.19 fixes Security/DB child Back. Other admin/customer routes remain open. |
| A3 | Customer screens: verify ownership, same-product navigation, Back/Home, and no cross-user or cross-product route. | PARTIAL — Account Pricing/member, Support/Ticket, credit guide, packages/referrals and Top-up have scoped evidence. S12.35.3 now covers 25 emitted Top-up→Back paths, including 14 fallback locales and Xu; PR/CI/deploy pending. Manual command-entry ancestry and remaining customer matrix open. |
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
- Verification: Python 3.11 `py_compile bot.py tests/test_profile_pricing_back_origin.py tests/test_profile_topup_back_origin.py` exit `0`; `git diff --check` exit `0` (only the configured LF→CRLF working-copy notice). CI/deploy pending. No payment/order/provider action or real Telegram message was used.
- Other manual command-entry screens whose keyboards bypass the registered Pricing callback flow remain split into S12.35.4 after delivery of this focused route fix.

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

### A6 platform-copy backlog — queued after route checks

Fake-role execution of actual UI functions produced 1 Railway reference in `owner_required_text` and 2 in registered `/admin_whoami` output. All 3 are stale because current Owner/runbook/runtime truth is Ubuntu VPS. The eventual fix is wording-only; permission logic, ENV and keys are protected. No config change or copy fix has been implemented. This is queued under A6 while A1–A5 remains incomplete.

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

## Current next steps

1. Finish S12.35.3 delivery as its own PR, with CI, merge, bot-only deploy and exact runtime verification against current main `938f6813717831e17cb564c8de9172e6c22906df`.
2. Inspect S12.35.4 manual read-screen ancestry as a separate narrow customer spec; verify actual emitters/registered handlers before changing it.
3. Continue remaining A1/A2 visible Admin actions and Back/Home routes, then A3–A5 customer, pending/expiry/repeat and dynamic callback coverage.
4. Finish A6 wording/layout consistency after route checks. Keep ShopAIKey/Key4U notices diagnostic until policy is clear.
5. Finish A7 only with multiple user-timed clicks correlated to anonymous server phases; retain the network/device uncertainty limits.
6. Close A8 only when each required route family and delivery/runtime state has direct evidence; keep this goal ACTIVE meanwhile.

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
