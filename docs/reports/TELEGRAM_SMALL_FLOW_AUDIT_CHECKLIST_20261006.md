# Telegram Bot Small-Flow Audit — Checklist & Evidence Ledger

Status: ACTIVE — do not treat this file or any isolated green test as whole-bot completion.

Current checkpoint (2026-10-11, S12.35.295): GitHub main and VPS bot both equal
`5c38bd31c20f26f815e2f05b6419f4dd64afbba9`; bot/web/nginx are active/running,
`NRestarts=0`. Full dirty `bot.py` compilation completed with exit 0 (blob
`4084700a09990d86c1cb0faf2b3f679fccebaabf`), and task YAML parses. The current
UI batch selected 64 safe test files and collected 577 cases; it is still running.
S12.35.296 subsequently fixed the Ticket ID guard; current candidate blob
`93ed446354e11947f52bee923a9f5a846c6ad6f1` compiled successfully, with 41 Ticket
regressions green. Classified UI failures were resolved (7-case failed-only
rerun plus 2 Package matrix methods green); Ubuntu workflow-hygiene CI remains
required. The earlier protected #1420 deployment hold is cleared. Batch CI/delivery and
live client latency remain open. Historical snapshots below retain their dates.

Delivery snapshot (2026-10-09 11:14 +07): GitHub main and VPS `/opt/toanaas/bot` both equaled `c3f40e4e5700c725f2321518a4e47113e5717654`. PR [#1416](https://github.com/manhtoangreensky-wq/bot/pull/1416) is MERGED; `python_hygiene_and_tests` and `python-311-source-compile` passed; bot-only deploy run [#37881668526](https://github.com/manhtoangreensky-wq/bot/actions/runs/37881668526) succeeded. At readback, bot/web/nginx were active, `NRestarts=0`, and `/health` returned `ok`. PR #1416 delivered S12.35.147–.149.

Latest main/runtime state (2026-10-09 11:54 +07): GitHub main is `62566249d4d54f6047ab33ddffd1bf94c57d0e41`, one commit (#1417) ahead of VPS `c3f40e4e5700c725f2321518a4e47113e5717654`. The VPS bot is active with `NRestarts=0`, and the deployed callback-timing observer is present. Read-only comparison shows #1417 adds Web Image runtime code and changes a Music internal-API test; it does not alter `handle_menu_callback` or the callback timing logger. Do not deploy this main delta as part of the UI batch without a separate protected-source review/authorization. This does not affect the live 7-day timing query against VPS `c3f40e…`.

Latest delivery evidence (08/10/2026): PR #1410 merged at `87bf32064473b02ee32aa6a6b63997ae3ef9b533`, CI run `37723283055` passed, bot-only deploy run `37727154776` succeeded. Follow-up PR #1411 merged at `ea516e37c1e482b5cb8708d5b7591cf93c1ecfcc`; CI runs `37733054155` and `37733054147` passed, and its bot-only deploy `37733818022` succeeded with `deploy_workers=false`. PR #1413 then merged at `9835b432464c4ccd94fe43690d41b6500c75eb7b`; CI runs `37782845604` and `37782845591` passed, and exact-SHA bot-only deploy `37783893626` succeeded. Fresh VPS readback confirms bot SHA `9835b432…`, `bot.py` blob `70633821…`, bot/web/nginx/both Product Video workers/SubDub worker active, all `NRestarts=0`, and `/health` `status=ok`. A separate earlier worker-inclusive dispatch `37736313510` targeted `ea516e37…` and used `DEPLOY_WORKERS=true`, deploying the #1409 Product Video `services/video_provider_router.py` delta and reconciling/restarting the SubDub worker. Therefore production runtime is not UI-only, although the UI PRs themselves contain no engine edits. This audit did not initiate that worker-inclusive run and did not call providers or validate product output. The whole-bot audit remains ACTIVE because A3/A5/A6/A7 are partial. Account → Back is still reported at 2–3 seconds without a matched client/server sample; do not claim all-button smoothness or zero defects.

Latest read-only delivery gate (2026-10-08 15:26 UTC): GitHub main is `f232deafaef5461e1de0494e750db16e26612b78`, one commit beyond VPS bot `9835b432464c4ccd94fe43690d41b6500c75eb7b`. The commit is merged PR #1412, a Product Video source-transfer change in `api_worker_selfshot3_source_video` plus its focused test; PR CI/source compile runs `37796119546` and `37796119564` passed. VPS still has #1409 as an ancestor, bot active/running, `NRestarts=0`, and internal health `status=ok`. No deploy run targets `f232de`. Do not deploy current main with the UI batch until #1412 is live or the Owner explicitly approves that protected delta.

Fresh read-only gate superseding the prior hold (2026-10-09 02:35 +07): GitHub main and VPS bot now both equal `f232deafaef5461e1de0494e750db16e26612b78`; deployed `bot.py` blob is `9cb361a490d7e1292af1a7516c39d02e11e05ab0`. PR #1412 is merged with both required checks successful and is live. `toanaas-bot.service` is `active/running`, `NRestarts=0`, and local `/health` returns `ok`. No deploy/restart was run in this audit. The UI branch is still based on `9835b432`; delivery remains pending checklist completion and one final refresh/rebase + protected-source comparison.

A3/A5 recent supplements: S12.35.95 and .129–.130 preserve the reachable one-step Support → general-support form by Owner direction; the separate category-picker entry question is resolved, not an open defect. S12.35.98–.104 reconcile the reviewed safe Free Tools/customer-root navigation set; .110–.111 cover Translation picker More/Back and the verified audio label; .112 covers AI Chat consent-request/Back only; .113 covers public-root Language picker Back; .139–.142 cover selected package/Combo Back routes; .184–.185 dispatch public Pricing Voice/Guide informational screens and their Back/Home routes. S12.35.186 reproduced and fixed the public Pricing Catalog → Member Back skipping the Catalog; it retains nested Member → birthday-instructions → Member → Catalog and Account-origin ancestry, with invalid origins rejected. S12.35.197 dispatches all eight emitted Feedback category controls to their prompt/back/home routes; .199 verifies public Pricing document-download callback plumbing with an inert send sink; .200 rechecks public Support → Home; .201 verifies Document Split “Add more” preserves staged files and returns to upload; .202 checks package Back ancestry for Image/Video/Music/Voice/SubDub without entering an engine; .205 completes the transient Feedback retry check through the actual registered `MessageHandler` and decorated `handle_message` dispatch. These are selected emitted routes/source maps, not full-handler/action coverage. Stateful terminals, protected engines, Telegram-client rendering, and correlated all-button latency remain open or explicitly excluded.

A6 source-only supplement: S12.35.116 compared all 14 Free Tools root button label keys and emitted callbacks with the actual handler branches. No root label/route mismatch was found; this does not establish viewport wrapping or visual polish in Telegram.

Fresh read-only recheck at 2026-10-08 22:47 +07: GitHub main remains `f232deafaef5461e1de0494e750db16e26612b78`; exact compare shows it is one commit ahead of live VPS `9835b432464c4ccd94fe43690d41b6500c75eb7b`, with only PR #1412 (`bot.py` +56/−5 and its new Product Video source-transfer test) in the delta. PR #1412 is MERGED and its required CI/source-compile checks are SUCCESS. VPS bot remains active/running, `NRestarts=0`, internal `/health` is `ok`. No deployment is valid under this UX-only scope while that Product Video delta is not live or separately approved; no deployment/restart was attempted.

The detailed continuation evidence for S12.35.117/.118 and this delivery blocker was posted to [the designated audit PR #1410](https://github.com/manhtoangreensky-wq/bot/pull/1410#issuecomment-6063693918). It is explicitly a post-merge tracking note; this local batch is not part of #1410 or #1413.

## Scope locks

Current GitHub main source check (read-only, 2026-10-10): main is `5c38bd31c20f26f815e2f05b6419f4dd64afbba9`. The audit worktree is `b2a45cf72c8d11b838ce67101c6385128106e856`; merge-base is `4dc0c31bab44d2c0427a7d4ab38b28b1e72693ec`, with one local commit and five main commits diverged. The net main delta contains #1417 Web Image runtime API and protected Product Video/provider changes in #1418–#1420. A focused `git diff -G` for callback registrations, callback data, callback handlers and the timing installer returned no callback-related hunk; `ci-main.yml` also has no delta. Do not rebase, merge or deploy this batch over those protected changes. VPS runtime was not checked in this source-only refresh; the last runtime snapshot above is historical, not current.

Fresh main-source revalidation (2026-10-11): GitHub's commits page and the #1420 commit page still show main at `5c38bd31c20f26f815e2f05b6419f4dd64afbba9`; local `origin/main` matches. The local audit branch remains at `b2a45cf72c8d11b838ce67101c6385128106e856`, one local commit ahead and five main commits behind its `4dc0c31bab44d2c0427a7d4ab38b28b1e72693ec` merge base. The latest #1420 commit changes provider/worker files, not the bot UI. GitHub CLI authentication is invalid, so this read-only confirmation used the already-open GitHub web session; no reauthentication, fetch, rebase, push, merge, or deploy was attempted. Keep the protected main delta isolated until ordered checklist closeout.

- Audit emitted Telegram buttons through their registered callback/message handlers; verify source, target, state, Back/Home destination, repeat/expiry behavior, and side effects.
- Keep the AutoPost WIP untouched. Do not refactor the shared router or alter stable Product/Edit/SubDub/Voice/Music engine behavior.
- No secrets, production user data, wallet changes, paid provider calls, real customer messages, restart, merge, or deployment without the applicable owner approval.
- Static callback counts are inventory evidence only; a route is complete only after exercising the emitted control through its registered handler.

## Ordered checklist

Fresh Admin navigation recheck (2026-10-10): Admin Ticket hub passed 6 tests in 9.582s; Admin Overview/report passed 3 tests in 4.957s; the combined Admin/customer root-menu safe-flow suite passed 50 tests in 48.397s. The root-suite rerun used a test-only immediate no-yield authorization fixture; no production behavior changed. These focused local results do not close Admin actions globally or the whole-bot audit.

Current continuation (2026-10-10): S12.35.200 verifies public Support → Home; .201 verifies Document Split “Add more” retains staged state; .202 verifies public and Account-origin package Back across Image/Video/Music/Voice/SubDub using navigation-only fixtures; .203 fixes large-order Back ancestry across package origins; .204 dispatches Pricing Guide → Back/Home in 14 fallback locales; .205 exercises Feedback retry through the registered text `MessageHandler` and decorated `handle_message`; .206 fixes Feedback-result Ticket → View Current → Back receipt ancestry; .207 flags Admin Archive View/File as a possible pre-ACK SQLite wait, unproven slow; .208 confirms Account route/ACK boundaries but the 2–3s report remains uncorrelated; .209 verifies ReplyKeyboard Home preemption and ordinary text behavior with direct no-I/O fixture assertions; .210–.213 cover expired Document/Support inputs, Admin Overview/report fixture aggregation, and emitted Document Confirm/Add more route wiring. S12.35.214 verifies `/profile` registration and localized account-keyboard delivery through an inert command fixture; .215 dispatches the public Support “CSKH tự động” information control through its registered handler and checks Back to Support plus Home to Main. Fresh local reruns on 2026-10-10: Support/Ticket ancestry + read-only Support Back/Home + pending/expiry modules passed 34 tests in 515.271s; Admin Overview/report passed 3 in 4.957s; Operator guide/navigation passed 13 in 5.341s; exact public Video duplicate-update guard passed 1 in 0.405s. Package/Combo module did not produce test output before its 120-second local run was interrupted; this is NOT_VERIFIED, not a product failure. ReplyKeyboard suite was not runnable via `unittest` because bundled Python lacks `pytest`; its earlier immediate-fixture assertions remain recorded, with consolidated CI pending. The latest approved menu-phase VPS aggregate is valid but empty; no click was correlated. Owner reports Bảng giá `<1s` and Account → Back 2–3s; all-button and ReplyKeyboard latency remain unproven. A3/A5/A6/A7 remain partial.

Continuation update (2026-10-10): S12.35.216 additionally dispatches public Support `admin_contact`, `premium`, `bot`, and `consult` information buttons through the registered Support handler; all four restore the exact Support root on Back and reach Main through Home. Focused local evidence is green; the full module's earlier Account-origin test stalls in this Windows runtime, so the module run is NOT_VERIFIED and consolidated CI remains pending.

Continuation update (2026-10-10): S12.35.220 reproduces and fixes My Tickets Back losing its immediate parent from public/Account Admin-contact, Auto-support, and Premium pages, plus the Ticket category menu. The support-child paths now return to their exact emitting page; the category path round-trips category → list → detail → list → category. Focused regressions are green and whole-file compile/CI gates remain pending. Latest owner-reported Bảng giá tap displayed in `<1s`; it does not correlate to the sparse server aggregate or close A7.

Continuation update (2026-10-10): S12.35.225 verifies the common public-Video callback guard suppresses an exact replay of the same Telegram query ID before the registered `vprofile` route and answers once. A distinct callback ID passes, so this only proves duplicate-update replay handling—not idempotency of two separate rapid taps. The actual Video handler body remains protected and uninvoked. One focused unittest passed and is listed in CI; CI and goal-wide closeout remain pending.

Source baseline note for S12.35.225: local `origin/main` ref was `381d335961bea01db60cda99f0dfe98e2b2d1760`; the audit worktree is still based on `4dc0c31b` with accumulated WIP. The guard/prefix/registration slice has no diff hunk against that local ref. No remote fetch was made, so this is not a fresh GitHub-main or runtime check; defer the single planned rebase and protected-source comparison until checklist closeout.

Continuation update (2026-10-10): S12.35.221 found and fixed the separate Premium lead-form “Vé của tôi” origin loss for public and Account entry. The emitted list now returns to the Premium page (or Account → Premium). The full `tests.test_profile_ticket_ancestry` module subsequently passed 18 tests in 171.092s — OK. Whole-file `bot.py` compile remains NOT_VERIFIED; consolidated CI is pending.

Evidence-matrix delta: .220 adds A3/A5 registered-route evidence for the three Support child My Tickets controls (public and Account origins) and the Ticket category menu. It does not close any handler family, stateful Ticket action, live-client UX, or A3/A5 globally.

Evidence-matrix delta: .217's full Account pending-origin module passed 6 tests; .220–.221 cover Support-child, Ticket-category, and Premium-form My Tickets ancestry, with the complete Ticket ancestry module passing 18 tests. These strengthen selected A3/A5 registered-route and pending-context evidence only; stateful Ticket operations, remaining callback families, client UX, and A3/A5 globally remain open.

Evidence-matrix delta: .222–.224 extend selected Account Support A3/A4/A5 route evidence: four form prompts' Back/Home, five information pages' exact Back/Home, and expired text recovery for all four form types. These are offline registered-route/state fixtures, not global callback coverage or live Telegram latency; A3/A5/A6/A7 remain partial.

Continuation update (2026-10-10): S12.35.217's public Support → Ticket → prompt → Back/Home route is green. The previously stalled Account-origin four-form regression was isolated: its nested fixture used `asyncio.run()` on Windows. Its menu/form dispatch now uses an immediate no-I/O test driver; the full `tests.test_profile_support_pending_origin` module passed 6 tests in 71.052s — OK. Consolidated CI remains pending.

Continuation update (2026-10-10): S12.35.218 dispatches the public Support root's emitted My Tickets button through the registered Ticket handler with an owner-scoped in-memory list. S12.35.219 reproduced and fixed the public My Tickets → ticket detail Back mismatch by carrying a scoped Support origin; focused route, Account-scope and Feedback-result regressions are green. Test-file compile and diff check are green; CI and live/client timing remain pending.

Additional ordered evidence (2026-10-10): S12.35.210 verifies expired Document Split prompts are consumed before generic chat; .211 verifies only the offline Admin Overview/report aggregation slice; .212 verifies expired Support/Ticket text is consumed by the registered text handler, recovers to the stored Support parent/Home, and clears only the actor's stale state; .213 connects the emitted Document Confirm/Add more controls to the registered handler. The six focused Support tests and two Document route tests are locally green and listed in safe-navigation CI; GitHub CI remains pending.

Continuation recheck (2026-10-11): one bounded three-case focused run passed (`Ran 3 tests in 6.728s — OK`): expired Document input is consumed before generic chat, expired Support/Ticket input before public chat, and replay of the same Video callback query ID stops before route dispatch while a distinct ID passes. This is local source-fixture evidence only; no whole-module/CI, live latency, separate-tap idempotency, or protected Video behavior is claimed.

Current main source refresh (2026-10-11): the GitHub commits/main page and local `origin/main` both show `5c38bd31c20f26f815e2f05b6419f4dd64afbba9` (#1420; the page reports checks success). Since the last verified PR #1416 merge `c3f40e4e5700c725f2321518a4e47113e5717654`, main includes #1417–#1420 with Web Image plus protected Music/Video runtime, provider, and worker changes. A function-aware `bot.py` diff shows the added Web Image internal API endpoints in the Web Music API region; it found no direct Telegram callback-handler hunk, but is only a source pre-screen, not the final semantic comparator. Audit worktree is `b2a45cf72c8d11b838ce67101c6385128106e856`; `origin/main...HEAD` divergence is 5 main-only / 1 branch-only commits. VPS has not been rechecked since its recorded `c3f40e4` state; do not infer it matches main or rebase before checklist closeout.

S12.35.286 extends A3/A5 evidence for Translation: the emitted file and voice target controls reach their exact registered handler, ACK once, and stop at inert pre-provider seams. It adds no production behavior and does not validate media processing, ASR/TTS, or provider execution.

S12.35.287 adds a narrow Translation voice-prompt navigation fix: its Back control retains the exact Language/Media/audio-action origin; More → Back remains usable after media expiry; expired target selection recovers to that source menu before any request save or voice runner. This does not prove live latency, audio processing, or engine/provider behavior; A3/A5 remain partial.

Latest continuation (2026-10-10): S12.35.253 extends A5 package/pricing coverage: emitted callbacks from Packages home, all seven task groups plus Combo, both detail types, and Large Order result Back stay within Telegram's 64-byte limit across all nine origin tokens, with exact Back restored in local registered-handler fixtures. S12.35.255 verifies the emitted package-confirm callback reaches its exact registration and only an inert checkout seam; its Back returns to the same package group. No order or payment action runs. The fresh strict-host 24-hour menu callback phase sample (~22:21 +07) was valid and empty (`SSH_EXIT=0`), so it still does not resolve A7. A3/A5/A6/A7 and A8 closeout remain partial/open.

| ID | Spec / acceptance evidence | State |
|---|---|---|
| A0 | Audit comparator baseline: `93919f93d7207f252252f10f9c03d1e8a2d458f8` after Admin Finance renderer PR #1408; bot blob `b0886d443b8b26e593be5e5efdc421f4ab2e1fbf`. Exact-SHA bot-only deploy #37599864501 succeeded (`deploy_workers=false`); strict-host SSH verified exact bot source, bot/web/nginx active, `NRestarts=0`, and `/health` `status=ok`. Fresh read-only check at 2026-10-08 00:18:30 +07 found GitHub main and VPS at `76f0454fbab5e467f9ca71a0135b6fd05d8d70c4`; versus this audit base, the one intervening commit changes only `services/remote_worker_api.py` and its focused test (separate Product Video worker-authority work, not this UI audit). Current bot service is active/running with `NRestarts=0`, and deployed `bot.py` contains the anonymous callback timing instrumentation. The audit branch remains based on `93919f9` and was not rebased or overwritten. Historical AST registration inventory at `0929d61a` measures 87 direct registrations, 85 distinct expressions and 83 literal patterns; the old emitter snapshot `4f1455ed` had 3,981 constructors/821 dynamic expressions/0 unmatched static callbacks. These inventories and old line locations do not prove current route behavior. |
| A1 | Admin screens: verify each visible action label matches its handler; test emitted callback, authorization, state transition, and error/stale path. | ADMIN UI ROUTE MATRIX VERIFIED OFFLINE — Admin Control Center destinations, module guide callbacks, report/read-only paths, scoped child entries, feedback/access, Broadcast Lite, Marketing/Affiliate, Ticket, and System/Operator/Provider routes have emitted-control → registered-handler evidence using inert seams. S12.35.26 verifies Data Status/Backup DB/Health are honestly labeled as guides; .27 verifies the System Provider Status route; .149 dispatches all eight emitted Admin Handbook root-section controls and verifies the exact registered handler, guide content, and Back destinations. Fresh local recheck: Admin Ticket hub passed 6 tests in 9.582s; Admin Overview/report passed 3 in 4.957s; Admin/customer root-menu safe-flow suite passed 50 tests in 48.397s after a test-only immediate no-yield authorization-fixture correction. These are scoped handler fixtures, not all Admin operational actions. Payment/wallet/freeze/provider mutations were not executed. Manual Telegram rendering/visual QA remains NOT_TESTED and A7 latency is still open. |
| A2 | Admin Back/Home: verify immediate parent and preserve list/filter/page context; test prompt and preview exits without performing the underlying action. | ADMIN ROUTE BACK MATRIX VERIFIED OFFLINE — ticket-origin specs S12.6–S12.10 (#1367–#1374) are in #1376; S12.12 merged/deployed in #1378; S12.18 Package Orders and S12.19 Security/DB origin fixes are deployed. S12.35.6–13, .20–22, .24–28 cover Finance, Marketing, Queue/Package, Security/DB, Support/Ticket, Broadcast Lite, legacy System/Operator and System → Provider Status round-trips using the registered handlers; .59 verifies Admin Notes → Internal Archive → Back to Notes through the registered menu handler; .149 verifies each Handbook page emits Handbook/Admin/Home returns accepted by the registered Menu handler. Fresh Admin/customer root-menu safe-flow rerun passed 50 tests in 48.397s, including emitted Admin roots and immediate Admin Back in offline fixtures. Stateful payment/provider/worker/archive-data actions were not run. Manual Telegram visual/client confirmation is NOT_TESTED; latency measurement remains A7. |
| A3 | Customer screens: verify ownership, same-product navigation, Back/Home, and no cross-user or cross-product route. | PARTIAL — Account Pricing/member, Support/Ticket, credit guide, packages/referrals and Top-up have scoped evidence. S12.35.3 covers 25 emitted Top-up→Back paths and is merged/deployed. S12.35.4 is merged/deployed at runtime SHA cfbeb530762526df148de351a8714815119b5db1; 20/20 focused handler tests verify direct /pricing_xu command ancestry. S12.35.14/.29/.34/.37/.38/.40/.41/.43/.44/.45/.46/.47/.51/.52/.57/.58/.60/.61/.62/.65/.66/.67/.68 dispatch selected public-root and account/support/language/image/notes/docs/guide/feedback/pricing/Storage Add-on/Ticket/package/Memory/Free Tools controls through registered handlers; .37 verifies Chat Pro info → Home; .38 verifies Account root/children; .40 covers root/account/credit-guide/support/language; .41 verifies Image landing → Home without entering a tool; .43 verifies Notes → Documents → Back/Home without opening tools; .44 verifies Guide landing → Home; .45 covers Memory pending reset plus Feedback/Language accepted/rejected paths; .46 covers Feedback category → prompt Back/Home and Cancel → Home; .47 ran Account Pricing/member/Top-up regressions (13 tests); .51 reran the public/Admin root menu suite (11 tests); .52 verified all seven Guide articles and corrected only the Guide-origin Video article Back while preserving the legacy Video-origin destination; .57 verifies Memory empty-delete state cleanup and Document Back routes; .58 verifies Storage Add-on custom-input Back and the Notes parent target without payment; .60 verifies customer-owned Ticket list/detail/prompt ancestry and wrong-owner/malformed rejection without sending or writing; .61 dispatches emitted “Gói Ảnh” → Back to Gói/Combo; .62 verifies empty-delete → Back returns to Notes/Docs; .65/.66 preserve saved-list and Delete-picker origins; .67 restores the exact search-result list after detail/Cancel and rejects stale/foreign tokens; .68 verifies Free Tools → Prompt Library → Back to Free Tools → Home through registered handlers. S12.35.217–.219 add registered-handler evidence for public Support information, Ticket prompt/pending origin, My Tickets list Back/Home, and fix public list→detail Back losing its parent. Stateful/tool terminals and protected processing remain explicitly untested, not passed. Manual Telegram client QA remains NOT_TESTED. |
| A4 | Pending input: verify `/start`, `/menu`, Back, expiry, stale controls, repeated presses, and abandoned drafts clear only the intended state. | VERIFIED FOR IN-SCOPE SMALL NAVIGATION/PENDING FLOWS — ReplyKeyboard Home preemption PR #1375 is deployed in #1376; S12.35.15–19, .30–31, .57–68, .138, and .147 cover selected pending/expiry/back routes. S12.35.209 executes the actual `handle_message` source for Home labels while AutoPost content is pending and preserves ordinary AutoPost input. S12.35.210 reproduces and fixes expired Split PDF page text falling through to generic chat; its focused registered-handler assertion passes and another user's pending state remains preserved. Both new cases are in the safe-navigation CI step; the consolidated run remains pending. AutoPost WIP input semantics and engine-owned product/job pending state remain protected; no AutoPost production logic changed. |
| A5 | Callback coverage: check static and dynamic emitted values against actual registrations and dispatched terminal behavior; no module-only route test counts as completion. | PARTIAL — current main-menu emitter produced 14 public and 15 admin callback values; each matches a registered literal callback pattern and every value is ≤64 UTF-8 bytes (S12.35.33). S12.35.14/.29/.31/.34/.37/.38/.40/.41/.43/.44/.45/.46/.47/.51/.52/.57/.58/.59/.60/.61/.62/.65/.66/.67/.68/.82/.83/.138/.147/.149/.151/.152 add registered-handler evidence for selected emitted root/account/support/guide/language/image/notes-docs, Account Packages/referral read-only children, Feedback/Language, Account Pricing/member/Top-up, Document, Storage Add-on Back/expiry, Memory empty-delete, Internal Archive type/Search/Back/Home and emitted `view`/`file` controls (including expiry, stale and malformed IDs), Admin Internal Archive, customer Ticket, package group, saved-list, delete-picker, search-result, Free Tools prompt-picker, and Admin Handbook section navigation; .41/.43/.44 cover UI landing/back only, not tool/article terminals; .46 adds Feedback category/cancel terminals with Back/Home assertions; .51 reran the safe root menu/callback suite (11 tests in 6.271s); .52 dispatches all seven Guide articles and asserts Guide/Main destinations plus preservation of legacy Video-origin Back (13 tests). S12.35.45/.57 cover Memory pending cleanup; .58/.147 test the Storage Add-on route and custom-input state through registered/source-extracted handlers; .59 dispatches Admin Notes → Internal Archive → Back to Notes; .60 verifies owned Ticket ancestry plus malformed/foreign rejection; .61 dispatches the emitted Image package group and its Back through the registered package handler; .62 dispatches emitted Memory empty-delete and its Back through the registered Memory/Menu handlers; .65/.66 verify saved-list and delete-picker origin; .67 verifies search → detail → Cancel → exact search results, stale/expired/foreign rejection and callback byte bounds; .68 dispatches Free Tools root → prompt picker → Back → Home. S12.35.82/.83 add the emitted Account → Packages → Account and three referral read-only child Back/Home round-trips through the registered `menu|` handler; they are now included in merged PR #1411 and runtime `ea516e3…`. S12.35.217–.219 now dispatch the public Support `support|ticket`, `ticket|mine|support`, and `ticket|pv|<id>|support` controls through their exact registrations and verify the list/detail return chain; its old detail→Support-root mismatch is reproduced and fixed. Remaining untested dynamic terminals perform stateful/data-changing actions or enter protected processing lanes; they are explicitly not claimed as verified in this UI/navigation batch. |
| A6 | UI/UX consistency: inspect admin/customer button labels, duplicated actions, misleading guide/status labels, row density, and recovery copy; propose or implement only narrow approved fixes. | PARTIAL — S12.35.35/.39 aligned four stale 7-row test contracts with the current 8-row menu without changing production layout; .36 corrected three stale Railway references in Owner setup UI to match VPS. S12.35.51 records the source structure: public root is 8 rows (one single action, seven paired rows), with 14 callback buttons and one community URL; Admin adds one final row. S12.35.52 corrects Guide-origin Video Back; .53 aligns the Vietnamese Guide “Admin” label with its actual Support destination; a source sweep found no other label/callback mismatch in the Guide topics/downloads/Back/Home. S12.35.48 source review matches the requested $100 baseline / warning strictly below $10, with a six-hour reminder cooldown; the provider endpoint and real admin message were not exercised. S12.35.130 source-reviewed the customer Support root: 5 rows, 8 unique controls, no label-to-callback mismatch or missing Home. S12.35.148 audits real customer/Admin root copy and keyboard output for all 17 supported locales; labels are present and all callbacks match registered handlers, without a source-level mismatch. Source tests do not prove translation semantics, Telegram viewport wrapping/scroll or visual polish; client visual QA and remaining copy/layout review remain NOT_TESTED. |
| A7 | Final latency diagnosis (last, after route checks): correlate anonymous server phases with a timed user click; separate callback acknowledgement, local build/cleanup, Telegram render, and client/network wait. Report measured distribution and limits; do not guess hardware/network purchases from an uncorrelated sample. | PARTIAL — The earlier approved 2026-10-10 12:17 +07 aggregate found 1 `menu` and 3 `pricing` dispatches but no click correlation. The checked full-stream 24-hour query at 17:16:56 +07 returned `EVENTS=0`; a corrected full-stream query at 18:04 +07 again returned `EVENTS=0`, `MALFORMED_MATCHING_LINES=0`, `journalctl` exit 0 and empty stderr. The 17:54 +07 `--grep` attempt returned exit 1 with empty stderr and is not counted. `menu|main_video` has a historical 373.478 ms sample (S12.35.198). Owner reports Bảng giá `<1s` and Account → Back 2–3s; neither has a matching timestamped server event. S12.35.262 verifies locally that the observer wraps registered callback handlers after registration and the 5 focused timing tests pass; this does not verify current VPS deployment or produce a matched click. ReplyKeyboard Home and client rendering remain outside callback telemetry. All-button smoothness and Telegram/network/client attribution remain unproven; no hardware purchase is inferred. |
| A8 | Closeout: run focused regressions, required syntax/tests, diff/scope review; collect scoped fixes on one batch PR and merge/deploy once after the complete ordered checklist, with live verification separate. | PARTIAL — UI PR #1410/#1411 and their bot-only deliveries are verified. A later worker-inclusive dispatch at the same SHA also updated Product Video worker state; see S12.35.84. Whole-goal closeout remains OPEN until A3/A5/A6/A7 evidence gaps and final scope/delivery review are complete. Latest full-file `bot.py` compile attempt is recorded as NOT_VERIFIED in S12.35.249; the current three-file `py_compile` session was interrupted after repeated polls produced no output, so it is also NOT_VERIFIED (not a syntax failure). S12.35.261 recheck found all 23 dirty tracked/untracked test files named by the current CI workflow; this checks test selection only, not successful execution or CI. `git diff --check` exited 0. |

Fresh deltas (2026-10-09): S12.35.134/.137 add registered-handler evidence for expired Document parent Back and staged-file Add-more/Remove-last state transitions; S12.35.135 corrects two Admin Knowledge Vault command-guide labels without changing their callbacks; S12.35.136 rechecks the anonymous latency window and still has no Account-correlated event; S12.35.138 preserves Internal Archive department Search Back after pending TTL expiry and proves Search Home clears only the actor's pending state. These additions do not close all Document/Vault/Archive actions, client QA, or Account latency.

Latest A3/A5 delta (S12.35.90–.199): Ticket reply/file guards, SubDub navigation-only Back, Voice Hub Back/Home, Ticket category-prompt Back, public Translation root → language hub → Back/Home, Translation text/file picker More/Back, the corrected Translation audio-picker label and Voice More/Back, Free Tools rate/QR/Avatar/weather/suggestion routes, Notes/Docs origin-aware Back, Admin Growth read-only routes, and selected Feedback/Pricing registered-handler paths are recorded in their individual specs. Owner excluded S12.35.106 on 2026-10-09 because aspect selection changes prompt-pack output; its experiment was reverted. S12.35.108 is dropped as dependent; only S12.35.107 render-hint test coverage remains. The pre-existing aspect-button/prompt mismatch is unresolved and not part of this UI batch. S12.35.95's 2026-10-09 decision preserves the reachable one-step general-support form; the category chooser's lack of a public entry is a deliberate deferred UI path, not an unresolved Owner choice or reproduced callback defect.

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
- Regression recheck on 2026-10-09: `tests.test_admin_module_child_back_origin tests.test_admin_queue_confirm_back_origin` → `Ran 29 tests in 155.459s — OK`; confirms the current Queue/Admin child-back and guide-route baseline still passes.
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
- Fresh source gate (2026-10-10): GitHub API read verified `main=5c38bd31c20f26f815e2f05b6419f4dd64afbba9`. A focused diff of the registered handler and delivery helper names between `origin/main` and this audit branch returned no hunk; the scope exclusion still applies to current main.

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
- Limit: `pytest` is absent from the available interpreter; this was direct function invocation with a no-op `pytest.parametrize` decorator shim, not pytest or CI. The module is now added to the consolidated safe-navigation CI command; remote CI is still pending. It proves fixture assertions only, not Telegram-client render or live latency.
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
- Resolution (2026-10-09): under the Owner’s delegation to choose the recommended small-flow UX, preserve the existing direct one-step general-support prompt. It is reachable and its Back route works; adding a category step has no reproduced defect or confirmed need. No production source change.
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

### S12.35.105 — PR #1413 CI/deploy reconciliation

- Contract: close the Owner-approved safe-navigation CI wiring gate with actual remote check, merge-SHA, bot-only deploy, and strict-host runtime evidence. Keep the overall audit ACTIVE.
- Evidence: PR [#1413](https://github.com/manhtoangreensky-wq/bot/pull/1413) merged at `9835b432464c4ccd94fe43690d41b6500c75eb7b`; PR CI runs [#37782845604](https://github.com/manhtoangreensky-wq/bot/actions/runs/37782845604) and [#37782845591](https://github.com/manhtoangreensky-wq/bot/actions/runs/37782845591) succeeded. Exact-SHA bot-only deploy [#37783893626](https://github.com/manhtoangreensky-wq/bot/actions/runs/37783893626) succeeded. Read-only VPS recheck returned the same bot SHA, `bot.py` blob `70633821294c449fe61b70b96aafb86449c12da3`, six checked units active/running with `NRestarts=0`, and `/health` status `ok`.
- Finding: the three Owner-approved Ticket regressions and SubDub safe-navigation test are now in remote CI and delivered. This closes the CI/deployment gate only, not full Ticket delivery or SubDub/engine output behavior.
- Limits: no Telegram client visual test, new timed click, provider/job, wallet, DB, message, worker sync, deployment, or restart was performed in this reconciliation. A3/A5/A6/A7 remain partial/open.
- Status: CI/GitHub/VPS evidence reconciled; whole-goal checklist remains ACTIVE.

### S12.35.106 — Image Story aspect application (Owner-excluded from this batch)

- Owner decision (2026-10-09): exclude this spec because applying the selected ratio changes prompt-pack output, beyond UI/navigation-only scope.
- RED: source review and fixture reproduced that `/image_story` hard-coded `9:16` after selection, and the callback accepted unsupported ratios without an alert.
- Current source still emits 9:16, 1:1, and 16:9 aspect buttons and the callback says the choice will affect a future pack; `cmd_image_story` still builds at fixed `9:16`. This mismatch is unresolved. Do not claim the selected ratio is applied or that this defect is fixed.
- A local one-shot aspect-application experiment and its tests had previously passed, but those source/test changes were reverted after the Owner decision. Their results are historical only and are not current verification.
- Historical scope/limits: the experiment fixtures stubbed media-state lookup, job recording and Telegram replies; they performed no image rendering, provider call, DB/wallet write, job, or real Telegram send. Those results are not current verification, remote CI, or a deployed behavior claim.
- Status: OWNER-EXCLUDED / REVERTED / NOT IN UI BATCH. The mismatch remains deferred; no render, provider, engine, wallet, DB, or delivery path was exercised.

### S12.35.107 — Image Story Admin render-hint callback

- Contract: dispatch the keyboard's actual `image_story_render_hint` value through its registered handler; assert exactly one callback acknowledgement and the informational “admin-test” reply. Keep `create_media_factory_job`, rendering and providers inert; do not change the button label or any engine behavior.
- Acceptance: one focused source-extracted regression passes; scope confirms no render/job/provider function is invoked. This is coverage reconciliation, not a claim that real rendering works.
- GREEN: tests.test_admin_root_menu_callback_single_ack.AdminRootMenuCallbackSingleAckTests.test_image_story_render_hint_only_informs_without_creating_media_job → Ran 1 test in 0.218s — OK. The emitted callback matched the registered handler; one acknowledgement and the exact informational reply were verified; media-job seam remained untouched.
- Historical combined rerun before the Owner scope decision: 3 aspect/expiry/render-hint tests in 0.879s — OK. It included the reverted experiment and is not a current result.
- Status: retain only the independent render-hint route-only test; it must be rerun alone. No production source/label or engine change. The containing module is already in the approved safe-navigation CI list; whole-goal audit remains ACTIVE.

### S12.35.108 — Image Story aspect pending reset (dropped dependent spec)

- Dropped after the Owner excluded S12.35.106: the new per-user aspect pending key was reverted, so no extra `/start`, `/menu`, or inline-menu cleanup is required by this batch.
- The earlier reset test passed against that reverted experiment only; it is historical, not evidence for current source. No `image_story_aspect:<uid>` pending key or added cleanup remains in the current diff.
- Status: DROPPED AS DEPENDENT; do not include or report as complete in the consolidated UI batch.

### S12.35.109 — Admin Growth read-only routes and Back ancestry

- Contract: dispatch the emitted Admin Growth root links and read-only report/information pages through the exact registered `admin_growth|` handler. Verify immediate/nested Back, guide-only labels, callback byte bounds, malformed-origin rejection, and public denial before any report read. Replace all list/report data providers with in-memory fixtures; do not execute affiliate, publish, package, or campaign actions.
- Finding: no route/Back or public-access defect reproduced in the covered read-only pages. Affiliates, Ideas, Calendar, Revenue & Click, Channels, and Packages render through the route; immediate and nested page ancestry is preserved.
- GREEN: `tests.test_admin_module_child_back_origin.AdminGrowthNavigationTests` → `Ran 5 tests in 15.089s — OK`.
- Scope/limits: source-extracted production keyboard, handler, and callback registration; report/list helpers, render and acknowledgement were inert/in-memory. No production DB, publish job, external network, provider, wallet, customer data/message, real Telegram, or product engine action. Admin Growth write actions and remaining dynamic terminals remain open.
- Status: route evidence reconciled locally; test module is already listed in `ci-main.yml`. No production source, CI workflow, PR, merge, deploy, or restart change in this spec. Whole-goal audit remains ACTIVE.

### S12.35.110 — Translation text/file picker More/Back

- Contract: render the Translation text and file target pickers without submitting text or sending a file, dispatch each emitted More Languages control through the exact registered `tr_` handler, then dispatch the emitted Back and verify the original target options return. Assert one acknowledgement per callback. Do not select a target, transcribe, submit media/text, or enter provider/action paths.
- Source boundary: `translation_target_keyboard("text"/"file")` emits `tr_more|<source>`; its expanded keyboard emits `tr_pick|<source>` as Back. The handler enters the existing showroom context, then routes only those controls to `show_translation_picker`; target-selection and transcribe terminals remain excluded.
- GREEN: `test_translation_text_and_file_picker_more_and_back_dispatch_registered_callback` → `Ran 1 test in 0.345s — OK`; the full existing `tests.test_admin_root_menu_callback_single_ack` module → `Ran 34 tests in 17.550s — OK`. Exact registered callback pattern, one ACK each, and identical restored text/file target callback sets were asserted. The first harness run lacked a `translation_text` copy field and raised before product assertions; the fixture was corrected, not production code.
- Scope/limits: test-only source-extracted render/handler/registration with in-memory context and Telegram-query fakes. No user media/input, target selection, translation/provider/ASR/TTS, wallet, DB, job, AutoPost, real Telegram, engine change, deploy, or restart. `bot.py` and CI workflow remain unchanged; this test module is already in the existing CI safe-navigation list.
- Status: locally verified route evidence only; Translation handler and overall A3/A5 audit remain partial. Keep the test in the single consolidated batch; do not create a per-spec PR/deploy.

### S12.35.111 — Translation Voice picker label and More/Back

- Contract: ensure the Translation Voice menu control that emits `tr_pick|voice` is labeled as audio translation, then dispatch it through the exact registered handler. Verify More Languages and its emitted Back restore the original audio target options with one acknowledgement per callback. Do not select a language, transcribe, send media, or call translation/ASR/TTS providers.
- RED: the actual `translation_voice_menu_keyboard` paired `tr_pick|voice` with `📝 Văn bản`; its screen text says the customer will send/reply with voice/audio, and the route opens the audio target picker. The focused label assertion failed exactly: actual `📝 Văn bản`, expected `🌐 Dịch audio`.
- Fix: changed only that button label/icon to the existing localized `translation_audio` copy; callback and all processing behavior are unchanged.
- GREEN: `test_translation_voice_picker_label_matches_audio_callback_and_returns_from_more` → `Ran 1 test in 0.238s — OK`; fresh root/menu module → `Ran 35 tests in 14.869s — OK`. The actual keyboard control traversed the exact registered handler; More → Back restored identical callback options; one ACK per callback.
- Scope/limits: one localized UI label in `bot.py` plus regression/evidence updates. The fixture faked recent-audio eligibility; it read no media and invoked no target selection, translation/provider, ASR/TTS, DB, wallet, job, AutoPost, Telegram delivery, deploy, or restart. Full bot compile and consolidated CI remain final batch gates.
- Status: local RED/GREEN verified, pending the single consolidated branch PR/CI/merge/deploy; do not ship separately. Whole-goal audit remains ACTIVE.

### S12.35.112 — Free Tools AI Chat consent entry and Back

- Contract: render the actual Free Tools root and dispatch its emitted `aichat|on` control through the exact registered handler. Verify the consent-request screen emits `aichat|back_freehub`; dispatch that Back and confirm the Free Tools root returns. Assert one callback acknowledgement each and that the request-consent seam runs while the enable/grant seam does not. Do not grant consent, configure or activate AI Chat, call a provider, or enter any generation/action path.
- Source boundary: the Free Tools root keyboard emits the AI Chat entry; `handle_aichat_callback` requests consent and renders the consent keyboard; its registered Back restores the root using the actual Free Tools renderer/keyboard.
- GREEN: `test_free_tools_aichat_entry_requires_consent_and_back_returns_to_free_tools` → `Ran 1 test in 0.298s — OK`; fresh `tests.test_admin_root_menu_callback_single_ack` module → `Ran 36 tests in 18.816s — OK`; `git diff --check` exit 0. CI already runs this test module; the three Owner-approved Ticket modules are also already listed, so the approved CI change requires no workflow edit.
- Scope/limits: source-extracted offline handler/keyboard/registration with in-memory state and Telegram-query/render fakes. Consent was requested but never granted; no user input, provider/network, DB, wallet, job, AutoPost, real Telegram, deploy, or restart. No production source or CI workflow changed.
- Status: locally verified navigation evidence only, kept in the one consolidated batch. AI Chat consent behavior and the broader Free Tools/A3/A5 audits remain partial; whole-goal audit remains ACTIVE.

### S12.35.113 — Public root Language picker Back

- Contract: take the `back_lang` control emitted by the actual public main-menu keyboard, dispatch it through the exact registered `handle_language_callback`, then dispatch only the emitted `lang_back` and verify the identical original Main-menu callback set returns. Assert one ACK per callback and zero language-setting/usage/broadcast writes. Do not select a language or change user preferences.
- Source boundary: `localized_main_menu_keyboard` → `back_lang` → `language_choice_keyboard` → `lang_back` → `localized_main_menu_keyboard`. Account-origin picker is already covered by the separate Account Language Back regression; this spec covers the public main-root ancestry.
- GREEN: `test_public_root_language_picker_back_restores_exact_main_menu_without_preference_write` → `Ran 1 test in 0.275s — OK`; fresh `tests.test_admin_root_menu_callback_single_ack` module → `Ran 37 tests in 17.159s — OK`; `git diff --check` exit 0. Actual public-root entry and emitted picker Back traversed the registered handler and restored the exact callback set. One initial fixture run stopped before assertions because it omitted the root keyboard dependency in the extracted handler namespace; fixture-only correction, no product assertion failed.
- Scope/limits: test-only source-extracted entry/keyboard/handler/registration and in-memory write stubs. No locale selection, preference/usage/broadcast write, provider, DB, wallet, job, AutoPost, real Telegram, deploy, or restart. No `bot.py` or CI workflow change; this module is already CI-listed.
- Status: locally verified navigation evidence only. Account-origin Language is covered separately; the broader Language handler, all-locale selection, stale/expiry/repeat paths and client timing remain partial/unverified. Keep in the consolidated batch.

### S12.35.114 — Final anonymous callback timing sample

- Contract: inspect only anonymous server-side callback timing events from the last 24 hours. Separate guard, handler, shared-render helper and dispatch timings from client display/network time. Correlate the Owner-reported Account Back estimate only if an exact click timestamp and matching route event exist; never assign a cause from unmatched events.
- Evidence: strict-host, read-only query at `2026-10-08T15:25:38Z` found two `menu` dispatch entries. At `09:29:31 +07`, generic dispatch was `306.038 ms` (`handler_ms=271.747`, `render_helper_ms=90.793`). At `09:30:17 +07`, `menu|main`, role `admin`, reported handler `309.919 ms`, ACK `179.210 ms`, render `101.631 ms`; generic dispatch was `360.419 ms`.
- Limits: neither event is an Account route or has a precise Owner click-time correlation. These server timings do not measure Telegram delivery/client render or device/network wait; the reported 2–3 seconds remains unexplained. No cause or purchase recommendation is established.
- Status: A7 remains PARTIAL; keep existing anonymized instrumentation and collect a precisely timed Account sample before diagnosing the residual wait. No source/config change, provider call, customer action, deploy, or restart.

### S12.35.115 — Protected main-to-VPS deployment gate

- Contract: before the one consolidated UI deployment, compare exact GitHub main with VPS runtime, source, health and CI. Deploy only if the runtime-to-target delta contains the approved UI batch and no unapproved Product/engine/provider/worker change; otherwise hold without restart.
- Evidence: at `2026-10-08T15:26:14Z`, main was `f232deafaef5461e1de0494e750db16e26612b78`, one commit ahead of VPS bot `9835b432464c4ccd94fe43690d41b6500c75eb7b`. The sole intervening change is merged Product Video PR #1412, modifying `api_worker_selfshot3_source_video` in `bot.py` and adding its Product Video test; required CI and source-compile checks passed (`37796119546`, `37796119564`). No deploy run targets `f232de`. VPS confirms #1409 is an ancestor, bot source SHA-256 `4c7bce0e8fcccfb2cca23a4dd5dd1da8252980faafbea6106ed10d0e880f2970`, video-router SHA-256 `efca258187bde556142ccc6206cda7039394c45b512b437366332554797b4130`, bot active/running, `NRestarts=0`, and internal health `status=ok`.
- Decision: deployment is held because shipping current main would include an unapproved Product Video source-transfer change outside the UX-only batch. Resume only after the owning Product Video task deploys #1412 or the Owner separately approves inclusion; then refresh main, rebase once, compare exact source scope and deploy once with `deploy_workers=false` if runtime-to-target is UI-only. No push, merge, deploy, restart, secret read, provider call, wallet/DB mutation, or real Telegram action was performed in this spec.

### S12.35.116 — Free Tools root label/callback source review

- Contract: compare every actual Free Tools root button label key and emitted callback with the route family and user-facing destination. Confirm the Home control is present. Do not dispatch publish, upload, downloader, Music, Voice/SubDub, provider, or processing routes.
- Evidence: `free_hub_main_keyboard` emits 14 controls plus the shared Home row. Read-only source comparison with `handle_free_hub_callback` found the labels map to the expected AI Chat consent, Utilities, Meta/Caption/Ideas/Prompt, Prompt Library, publishing-package prompt, Notes/Docs, upload prompt, Voice/SubDub script helper, Music/SFX helper, Translation, and Video Downloader route families. Existing S12.35.98–.113 evidence was cross-referenced for tested navigation destinations.
- Finding: no label-to-route mismatch reproduced in this source-only pass. Publishing/upload/downloader/Music/Voice/SubDub processing helpers remain excluded, not passed.
- Limits/status: documentation-only; no source/test/CI change or callback/action dispatch. A6 remains PARTIAL until Telegram-client viewport/wrapping and visual QA are observed.

### S12.35.117 — Public main-menu label/callback source review

- Contract: compare the current public main-menu builder's visible copy keys with every emitted callback/URL, then verify the callback family has its exact handler registration and expected landing branch. Do not dispatch callbacks; AutoPost, audio, video, image, translation, and other product behavior remain protected.
- Evidence: `localized_main_menu_keyboard` emits the expected 8 public rows (14 callback controls plus the community URL); the optional Admin row is only appended for admins. The label/callback pairs are Free Tools→`freehub|main`, AI Video→`menu|main_video`, AI Images→`menu|main_image`, Translation→`menu|translate`, Audio Studio→`music_quick|showroom|root`, Account→`menu|main_profile`, Top-up/Pricing→`pricing|main`, AutoPost→`menu|autopost`, Chat Pro→`menu|chat_pro`, Notes/Documents→`menu|main_memory`, Support→`menu|support`, Guide→`menu|main_guide`, Feedback→`feedback|start`, Community→the configured URL, and Change language→`back_lang`; Admin→`menu|admin` is conditional. Registered patterns exist for each emitted callback family. The Audio Studio `root` branch is a landing screen with Back to Main; no child action was entered.
- Finding: no source-level label-to-callback/handler mismatch reproduced. AutoPost is only confirmed as a dashboard entry; its WIP behavior is not validated. This check does not rate translation quality across locales or prove Telegram client row wrapping, rendering, or latency.
- Scope/status: read-only source review; no callback/action dispatch, production source/test/CI change, provider/job/wallet/DB/Telegram effect, deploy, or restart. A6 remains PARTIAL for client visuals and localization QA; A3/A5 remain partial for action-capable/protected terminals.

### S12.35.118 — Public-root language selection across emitted locales

- Contract: open the language picker from the actual public Main keyboard, enumerate every locale emitted by the current `language_choice_keyboard`, and dispatch each emitted `lang|<locale>` through the exact registered handler. Verify one ACK, one fixture-only preference update, one usage event, and return to the Main renderer in the selected locale. Do not write user preferences, broadcast, or change language in production.
- Coverage finding: the public-root picker had registered-handler Back evidence (S12.35.113), while all-locale selection evidence existed for the Account-scoped variant. The unscoped public Main selection/render branch lacked equivalent dispatch evidence; this was a coverage gap, not a reproduced defect.
- GREEN: focused test `test_public_root_language_picker_emitted_locales_update_only_fixture_and_restore_main` → `Ran 1 test in 0.976s — OK`; full existing CI-listed `tests.test_admin_root_menu_callback_single_ack` → `Ran 38 tests in 57.760s — OK`. All 17 emitted locale values matched the registered pattern, acknowledged once, updated only the in-memory fixture and rendered the Main menu using the selected locale.
- Scope/limits: source-extracted production keyboard/handler/registration; preference and usage seams, renderer and Telegram query were in-memory fakes. No actual preference/usage/broadcast write, provider, DB, wallet, job, AutoPost, product engine, Telegram delivery, deploy, or restart. This does not verify linguistic accuracy, client viewport/wrapping, latency, or every language-specific screen; whole-goal A3/A5/A6/A7 remain partial.

### S12.35.119 — Reconcile callback evidence ledger to current route evidence

- Contract: correct the current evidence summary without rewriting its historical source-registration baseline. Supersede stale candidate-status text only for public Main label/registration mapping (S12.35.117) and public-root language selection (S12.35.118); retain PARTIAL/NOT PROVEN for every action-capable, protected, payment/provider, AutoPost, and client/runtime route.
- Evidence: the callback inventory now records S12.35.117/.118 and a fresh read-only runtime snapshot at 2026-10-08 22:52 +07 (`main=f232de…`, `VPS=9835b4…`, bot active, `NRestarts=0`, health `ok`). The only commit ahead is merged Product Video #1412; no deployment/restart was attempted.
- Status/limits: documentation reconciliation only; no handler, test, CI, production source, or runtime change. A3/A5/A6/A7 remain partial outside the two named slices.

### S12.35.120 — Recheck the Owner-approved Ticket safe-navigation CI gate

- Contract: verify the three approved Ticket regression modules are part of the explicit safe-navigation CI job. Add them only if absent; do not duplicate entries or change deploy behavior.
- Evidence: all three are already invoked by `.github/workflows/ci-main.yml` in the `Small Navigation and UI Closure Regressions` step: `tests/test_support_ticket_send_concurrency.py`, `tests/test_support_ticket_file_send_concurrency.py`, and `tests/test_support_ticket_send_matches_preview.py`. The exact local unittest command ran 11 tests in 5.115s — OK.
- Status/limits: CI request satisfied with no workflow edit. This is local test evidence, not a fresh GitHub Actions run; the consolidated batch still needs remote CI. Tests use fake/in-memory seams; no Ticket was sent or written, and no real Telegram action occurred.

### S12.35.121 — Revalidate the protected main-to-VPS delivery gate

- Evidence at 2026-10-08 23:01:29 +07: GitHub main is `f232deafaef5461e1de0494e750db16e26612b78`; VPS bot runtime is `9835b432464c4ccd94fe43690d41b6500c75eb7b`. The exact GitHub compare is one commit ahead and contains only PR #1412 (`bot.py` plus `tests/test_p0_video_r05a_source_video_transfer_local_bot_api.py`), a protected Product Video source-transfer change. PR #1412 checks succeeded, but no deploy run targets its SHA. VPS bot is active/running, `NRestarts=0`, `/health` is `ok`.
- Decision: hold deployment of current main with the UX batch until #1412 is live or the Owner separately authorizes its inclusion. This turn performed no push, merge, deploy, restart, provider call or Telegram action.

### S12.35.122 — Reconcile Admin root landing-route evidence

- Contract: verify that the Admin control-center's emitted root navigation controls reach their matching registered module roots and return to Admin. Do not dispatch child operations or action-capable terminals.
- Evidence: `test_admin_control_center_entries_reach_their_registered_module_roots` dispatches all 10 emitted `menu|admin_*` controls through the registered menu handler and checks each module heading plus `menu|admin` Back; the separate `admin_growth|main` path and Back are covered by the earlier S12.35.8 two-test group. Current focused rerun: `Ran 1 test in 5.148s — OK`. Marketing metrics are fixture-only.
- Status/limits: no root callback mismatch reproduced and no source change needed. This closes only root landing navigation; Admin child operations, payment/provider/stateful actions and Telegram-client timing remain partial or excluded. The callback inventory's `handle_menu_callback` row is narrowed to these verified facts instead of broadly implying the root entries lack route tests.

### S12.35.123 — Memory Delete confirmation rejects stale callback replay

- Contract: `memory|delete_yes` may archive only while it matches the current user's live confirmation for the same note. Cancel, replacement confirmation, missing/legacy token, mismatch, or expiry must fail closed. Do not change note ownership, SQL/schema, or any product engine.
- RED: the test drove the production Memory root → Delete picker → emitted note → confirmation → Cancel, then replayed the old emitted confirmation. Before the fix, the fixture note changed from `active` to `archived` and the fake DB/event were invoked; this was a behavioral failure, not setup error.
- Fix: bind the emitted confirmation to existing per-user pending state (`delete_confirm`, note ID, `time.time_ns()` token and existing pending TTL). The handler validates exact action/note/token and consumes valid state before the existing archive update. Both picker and text-ID confirmation emitters use the same guard. No SQL/schema/business-price changes.
- GREEN: final stale/tokenless replay + current-token acceptance case → `Ran 1 test in 0.859s — OK`; complete existing registered root/menu callback module → `Ran 39 tests in 21.574s — OK`; Memory Start/Menu pending reset → `Ran 1 test in 2.663s — OK`; empty-delete state → `Ran 1 test in 0.307s — OK`. Edited test `py_compile` and `git diff --check` exited 0.
- CI/compile: this test is in `tests/test_admin_root_menu_callback_single_ack.py`, already included in the safe-navigation CI step; no workflow edit was needed. Full 15 MB `bot.py` `py_compile` did not produce output after repeated multi-minute local attempts and was stopped to limit resource use; it is NOT_VERIFIED locally and remains a consolidated CI gate. Local bundled Python has no pytest.
- Scope/side effects: only the fake DB captured the valid current-token update; stale/tokenless callbacks made no write or event. No production DB/user note, provider, wallet, job, AutoPost, product engine, or real Telegram action. This spec is local only; no commit, push, PR, merge, deploy, or restart.

### Fresh release gate recheck — 2026-10-08 23:39 +07

- GitHub main remains `f232deafaef5461e1de0494e750db16e26612b78`; PR #1412 is merged and both CI and source-compile checks succeeded.
- Latest deploy workflow run `37783893626` targets `9835b432464c4ccd94fe43690d41b6500c75eb7b`, not main. VPS still runs `9835b432464c4ccd94fe43690d41b6500c75eb7b`; bot/web/nginx are active/running, all `NRestarts=0`, `/health` is `ok` at `2026-10-08 23:39:11 +07`.
- Therefore #1412 is not live and the UX batch remains held. `gh pr list --state open` returned no open PR; no push, PR, merge, deploy, or restart was performed.
- Progress evidence for this local continuation was appended to merged [PR #1410](https://github.com/manhtoangreensky-wq/bot/pull/1410#issuecomment-6064603175), explicitly marked as not included in merged code.

## Current next steps

1. Latest completed route evidence is S12.35.186. Do not repeat Archive `.172–.181`, public Pricing root `.166`, Audio Studio `.182`, Music Hub `.183`, Pricing Voice `.184`, Pricing Guide `.185`, or Catalog Member `.186`; the Owner's latest Bảng giá observation is `<1s`, while the callback log sample is uncorrelated. This is one manual observation, not an all-button latency result.
2. Select the next distinct customer/admin callback or pending-state gap from the evidence inventory; continue one safe emitted control → registered handler → emitted Back/Home or state-expiry path at a time. Keep payment/provider/protected product terminals excluded.
3. Continue A3/A5 in checklist order with one emitted safe control → registered handler → emitted Back/Home or state-expiry path at a time. Prioritize remaining customer/admin navigation and message-handler pending-state gaps; do not count a static map or a test filename as executed route evidence. Preserve all action-capable/payment/provider/protected product terminals as explicitly excluded unless their required safe fixture contract is available.
4. Keep Product `progress|status` outside read-only UI dispatch; Music/SubDub delivery and recovery routes, AutoPost WIP and all stable product engines remain protected. Do not refactor shared routers or test live providers.
5. A6 remains PARTIAL: source/emitted-keyboard checks do not prove Telegram viewport, wrapping, translated-copy quality, or visual polish. Make no speculative UI changes; ShopAIKey/Key4U policy stays unchanged.
6. A7 remains PARTIAL: Bảng giá was reported `<1s`; Account → Back is still reported at 2–3s without a matched event. Other callback families and ReplyKeyboard/message-handler latency are unmeasured. Do not attribute delay to bot, Telegram, client, or network without correlated phase data; do not claim all buttons are smooth.
7. A8 and the overall goal remain ACTIVE. Latest local route evidence is S12.35.215; do not rerun the completed profile-command or public Support information slices. Continue with the next distinct safe gap in A3/A5, excluding payment/provider/protected product terminals. Local audit branch `audit/storage-addon-expiry-20261009` was recorded at `b2a45cf`; refresh branch/base status only at the final release gate. Finish ordered specs first, then one final refresh/rebase and protected-source comparison, consolidated CI, and one batch PR/merge/deploy cycle. No merge, deploy, or restart is authorized by this continuation.

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

### S12.35.124 — Internal Archive “Change group” Back preserves the pending preview

- Contract: from an Admin Archive file preview, “Đổi nhóm” opens a department-only picker; selecting another department applies its default document type and returns to that same preview with the pending file retained, while Back also returns there. Preview Home must return to Main and clear only the current actor's pending Archive draft; the Notes parent Back is also checked. The normal Archive root Back and Search must remain unchanged.
- RED: the source-extracted production handler reused the root keyboard, so the nested picker emitted `menu|main_memory` instead of immediate-parent `archive|preview` and also exposed `archive|search`. That unrelated Search prompt routes Back to Archive root, which clears the pending state.
- Fix: the existing department keyboard now has a preview variant: only the nested change-group picker omits Search and uses `archive|preview` for Back. Department choice callbacks, Home exit and default root behavior are unchanged.
- GREEN: the inert fixture asserts Search is absent, the emitted Back is `archive|preview`, and dispatching that exact control restores preview while retaining the same fake file. A second route test dispatches emitted `archive|dept|sales` and verifies the new department/default document type while retaining the same file and returning to Preview. Exact Menu-handler integration tests dispatch Archive→Notes and the preview's actual Home control; both verify the expected screen and that only the actor's pending state clears. Final CI-style runs: Archive picker module 5 tests in 0.764s — OK; registered Menu routes 2 tests in 0.679s — OK. An initial unittest-discovery invocation reported `Ran 0 tests`; the harness was corrected to `unittest.TestCase` so CI executes all assertions.
- CI: `tests/test_internal_archive_type_back_label.py` is included in the existing safe-navigation CI step and matches its unittest runner. The three Owner-approved Ticket regression modules were already listed and verified present; no duplicates were added.
- Limits: no real Archive file/database, Search query, save/send-file terminal, provider, wallet, job, AutoPost, protected product engine, or live Telegram action. Full-source compile and consolidated remote CI remain delivery gates; the whole-goal audit remains active.

### S12.35.125 — Anonymous server-side callback latency recheck

- Contract: inspect aggregate anonymous callback dispatch timings over the latest 24 hours. Attribute the Owner-reported Account → Back delay only if there is a precise click timestamp and a matching account-route event; do not infer client/network cause from unrelated events.
- Evidence: strict-host, read-only journal aggregation at 2026-10-09 00:05:48 +07 found two `callback_dispatch_timing` events, both `prefix=menu`, `route_key=unclassified`. Average dispatch was 333.2 ms; maximum 360.4 ms; maximum guard 48.0 ms and render helper 101.6 ms; none exceeded 500 ms or 1000 ms. No `account_root` callback event was present.
- Classifier check: `menu|main_profile` maps to `account_root`; other menu callbacks default to `unclassified`. Existing `tests/test_callback_dispatch_timing.py` ran 5 tests in 7.764s — OK, including exact Account-route classification and checks that user IDs, callback payloads and message contents are not logged. No telemetry defect reproduced; no code change.
- Finding: the two observed server callbacks were sub-500 ms, but neither correlates with the reported Account click. The verified classifier would label an exact `menu|main_profile` event `account_root`; none occurred in the sampled window. This does not explain the user's 2–3 second wait and cannot distinguish Telegram rendering, device/client, or network delay. No cause is assigned.
- Limits/next: only aggregated route/timing fields were returned, with no IDs or callback payloads. A7 remains partial until a precisely timed Owner click matches an Account route event; other independent offline checklist items continue.

### Fresh deployment-gate recheck — 2026-10-09

- GitHub main is `f232deafaef5461e1de0494e750db16e26612b78`. PR #1409 is merged at `d24716db154b77aadebfdefe87ab9cac17416bd2`, and its `python_hygiene_and_tests` check succeeded.
- VPS bot remains at `9835b432464c4ccd94fe43690d41b6500c75eb7b`; the #1409 merge is an ancestor of runtime. `toanaas-bot.service` is `active/running`, `NRestarts=0`.
- Main still includes PR #1412 (`f232de…`), whose Product Video source-transfer change is outside this UI-only scope; its CI and source-compile checks succeeded, but it is not in the VPS runtime. Deploying main with the UI batch would include that protected delta.
- No deploy/restart was attempted. Hold the consolidated UI release until #1412 is deployed by its owning task or the Owner explicitly approves including it; UI batch remains local-only and whole-goal status ACTIVE.

### S12.35.126 — Admin root labels match emitted destinations

- Contract: compare every visible Admin root label with its emitted callback and intended landing route, including the Growth entry and Main/Home. Do not dispatch child/action controls or change business behavior.
- Evidence: source-extracted `admin_control_center_keyboard` + `menu_nav_keyboard("admin", True)` comparison returned `Admin root label/callback pairs: 12 matched expected destinations`. The 10 module callbacks and their landing/Back behavior are independently exercised by `test_admin_control_center_entries_reach_their_registered_module_roots`; Growth has its separate registered-handler coverage.
- Status/limits: no mismatch or code/CI/runtime change. This closes only source-level Admin root label-to-route mapping; Telegram viewport, wrapping and live latency remain unverified, and child/action terminals remain partial or excluded.

### S12.35.127 — Admin help route and guide Back evidence

- Contract: run the exact source-extracted `admin_help|` callback tests and record only the covered safe branches: registered handler, one acknowledgement and handbook render for an authorized Admin, emitted module-guide Back returns to the emitting module, runtime shortcuts remain accurately labeled and retain callback values, and stale Support guide control is denied to a non-admin before render. Do not exercise any Admin operational action.
- Evidence: `python -B -S -m unittest tests.test_admin_help_callback_single_ack.AdminHelpCallbackSingleAckTests -v` → `Ran 5 tests in 1.077s — OK`; the test module's `py_compile` and `git diff --check` exited 0.
- Scope/limits: source-extracted handler, actual registered pattern and emitted module keyboard; in-memory Telegram and handbook render fakes. No production data/handbook mutation, provider, wallet, job, customer message, real Telegram, deploy or restart. Other Admin help branches remain partial; this is not whole-handler completion.
- Status: evidence-only; no production source change. Preserve the consolidated batch/release gates and whole-goal ACTIVE status.

### S12.35.128 — Knowledge Vault Home returns to Main

- Contract: verify that the actual `vault_admin_keyboard` emits the registered `menu|main` callback, and dispatch that emitted Home through the exact registered `handle_menu_callback`. Require one acknowledgement and the Main renderer. Preserve all existing Vault buttons and do not invoke Vault status/import/search/approve/sync/backup operations.
- RED: unchanged source's actual Vault keyboard emitted eight Vault-specific callbacks and no Home; the focused regression failed specifically on missing `menu|main` before dispatch.
- Correction: added one `🏠 Menu chính` row with `callback_data="menu|main"`; Vault callbacks and handler/action code are unchanged.
- GREEN: `test_knowledge_vault_home_returns_to_main_via_registered_menu_handler` → `Ran 1 test in 0.296s — OK`. It asserts both Vault and Menu callback registrations and dispatches Home through the actual extracted Menu handler; exactly one ACK and Main render are asserted. Initial harness attempts stopped on missing extracted `time` and `logger`; inert test-only dependencies were added, with no production assertion failure.
- Scope/limits: source-extracted keyboard/menu handler and in-memory query/render fixtures. No Vault operation, DB/data mutation, provider, wallet, AutoPost, product engine, real Telegram, deploy, or restart. Full root/menu regression, `bot.py` compile and final consolidated CI remain required before delivery.
- Status: local minimal UI fix, pending consolidated batch; do not deliver as a per-spec PR.

### S12.35.129 — Customer Support direct Ticket route recheck

- Contract: revalidate the currently emitted Support → “Tạo Ticket” direct general-support form through the exact registered Support callback. Confirm that Account-origin Back, pending input retry/expiry, and Ticket list/detail navigation retain their intended origin. Do not submit/create a ticket or change the separate category-picker UX.
- Evidence: bundled Python command `-B -S -m unittest tests.test_profile_support_pending_origin tests.test_profile_ticket_ancestry tests.test_profile_support_read_back_origin -v` → `Ran 19 tests in 141.541s — OK`. The existing tests use source-extracted handlers and in-memory query/pending/DB/message seams; those three modules are already in the safe-navigation CI job.
- Finding: the current direct general-support Ticket form is reachable and Account/Support Back and pending paths pass. The separate `ticket|start` category chooser remains internal; S12.35.95's 2026-10-09 delegated decision preserves the simpler direct form, not a broken callback.
- Scope/limits: evidence-only. No source/test/workflow change, real ticket submission, production DB/data, customer message, provider, wallet, job, AutoPost, product engine, real Telegram, deploy, or restart. Whole A3/A5 coverage remains PARTIAL for action-capable and excluded routes; S12.35.95 resolved the category-picker question by preserving the current direct-form behavior.

### S12.35.130 — Customer Support root labels match emitted routes

- Contract: source-review the actual `human_support_keyboard` visible labels, callback values, row count, duplicate callbacks, and root Home; map each value to the intended registered Support/Ticket/Menu handler. Do not submit a ticket or enter lead, payment, provider, or customer-message actions.
- Evidence: the source-extracted keyboard emitted 5 rows and 8 unique callback controls: Admin contact → `support|admin_contact`, Tạo Ticket → `support|ticket`, My Tickets → `ticket|mine`, Premium → `support|premium`, custom bot → `support|bot`, consultation → `support|consult`, automatic support → `support|cskh_auto`, Main → `menu|main`. Support values map to existing branches of registered `^support\\|`; My Tickets is registered to the Ticket handler; Main uses the Menu handler. No duplicate, absent Home, or source-level label/route mismatch was found.
- Finding/limits: the Tạo Ticket button accurately opens the direct general-support form verified in S12.35.129; the delegated 2026-10-09 decision preserves this one-step behavior rather than exposing the separate category picker. The source fixture uses copy keys, not final localized strings, and cannot prove Telegram viewport, wrapping, or visual quality. No source/test/workflow change or production/client side effect.

### S12.35.131 — Feedback same-message redelivery is suppressed

- Contract: invoke two concurrent copies of the same incoming Telegram message through the actual source-extracted `telegram_message_idempotent` wrapper attached to `handle_message`, with inert pending/ticket/reply/admin-notifier seams. Verify its per-chat/message lock lets the Feedback pending handler execute only once. Do not use production DB or Telegram.
- Evidence: all five plain test functions in the CI-listed `tests/test_feedback_callback_single_ack.py` were invoked with the bundled Python standard library runner → `Ran 5 focused test functions — OK`. The regression extracts the actual pending handler, message dedupe key, lock/prune functions and idempotency wrapper; it confirms decorated `handle_message` reaches Feedback and asserts one classification, ticket create, pending clear, customer reply and admin notification for concurrent copies of message `123:444`.
- Finding: no same-message concurrent redelivery defect reproduced. This closes only in-process duplicate delivery of one Telegram message ID. Distinct message IDs submitted rapidly, cross-process dedupe, service-failure retry, translated client rendering, and live Telegram timing remain unverified.
- Scope/limits: test-only, no production handler change, DB, customer/admin message, provider, wallet, job, engine, AutoPost, deploy, or restart. The bundled Python has no pytest, so local execution used an explicit stdlib runner for these plain functions; the configured CI pytest job remains a consolidated delivery gate. An initial `unittest` invocation ran zero tests and exited 1 because this module uses pytest-style functions; that invocation is not counted as verification.
- Status: locally verified, no source-level product defect found; keep A3/A5 and Telegram-client evidence partial outside this exact same-message redelivery case.

### S12.35.132 — Expired Feedback input stays in the Feedback flow

- Contract: with an expired Feedback pending record (>600-second TTL), consume the submitted text, clear stale state, show a dedicated expiry message in all 17 supported locales with the Feedback category keyboard, and prevent later generic chat handlers from receiving it. Active Feedback submission behavior must remain unchanged.
- RED: source-extracted actual getter removed the expired state and `handle_feedback_pending_text` returned `False` without replying; `handle_message` then continued into later CSKH/AI-capable handlers. The new 601-second fixture failed only the expected-consumed assertion; no setup error or external side effect.
- Minimal fix: the Feedback handler snapshots only its own raw pending record before calling the existing expiry getter. If that getter expired and removed the Feedback record, it replies with `feedback_expired_text(lang)` plus the existing Feedback category keyboard and returns `True`. The message helper contains explicit translations for all 17 supported locales; active/no-pending paths are unchanged.
- GREEN: all seven plain functions in the CI-listed Feedback module at this spec's completion, including concurrent same-message suppression, actual expired-handler behavior, and source-extracted copy coverage for all 17 locales, passed through the bundled-Python stdlib runner → `Ran 7 focused test functions — OK`. The expiry case asserts stale-state removal, one response, existing category keyboard, and no ticket/classifier call. Test module syntax and `git diff --check` pass; local pytest is unavailable, so configured CI remains required.
- Scope/limits: one branch in `handle_feedback_pending_text` plus a focused regression. No real customer message, DB, provider, wallet, job, engine, AutoPost, deploy, or restart. Distinct rapid message IDs, cross-process duplicate delivery, failure/retry, and Telegram-client rendering/timing remain open.
- Status: locally verified; active Feedback flow and other Support/Ticket routes remain unchanged.

### S12.35.133 — Invalid Feedback category callbacks fail closed

- Contract: compare actual emitted Feedback category values with the authoritative `FEEDBACK_CATEGORY_LABELS` whitelist; reject malformed/retired category callbacks with one alert before acknowledgement, pending mutation, or render. Keep all eight emitted categories and Home route working.
- RED: `feedback|cat|retired_category` matched the broad registered `^feedback\\|` handler and was accepted by its prefix check; the pending setter would coerce it to `other` instead of denying the stale/invalid value. The focused test failed on the missing unsupported-category alert, with no setup error.
- Minimal fix: validate only the category suffix against `FEEDBACK_CATEGORY_LABELS` before the normal callback ACK; reuse the validated suffix for the existing pending/render branch. No labels or valid category behavior changed.
- GREEN: the new regression verifies unsupported category gets exactly one alert and no set-pending/render effect; a source-extracted builder test verifies all eight emitted categories are unique, whitelisted, and retain `menu|main`. All nine functions in the CI-listed Feedback module passed through the bundled-Python stdlib runner → `Ran 9 focused test functions — OK`; this includes 17-locale expiry-copy coverage. Syntax and `git diff --check` pass.
- Scope/limits: one category-validation guard plus two focused assertions, no DB, real Telegram, customer/admin message, provider, wallet, job, engine, AutoPost, deploy, or restart. Local pytest unavailable; remote CI remains required. Full client appearance/localization and live latency remain unverified.
- Status: locally verified; valid categories and all prior Feedback route cases pass, while whole Support/Ticket and Telegram-client evidence remain partial.

### S12.35.134 — Expired Document Back preserves its originating parent

- Contract: emitted Back buttons from Document tools must retain their UI parent after the per-user pending request expires. `save_document` returns to Notes/Documents; PDF tools return to Documents. A live pending state remains authoritative over callback-supplied context. Cover the quota-error screen without processing files, saving/sending data, or calling a provider.
- RED: `save_document` Back from both the after-file screen and the quota-error screen emitted generic `docflow|back`; after the real TTL getter removed pending state, the registered handler no longer knew the origin and rendered the PDF Documents menu instead of Notes/Documents. Both assertions failed at the observed route/output, not from setup errors.
- Minimal fix: the three Document keyboard builders (upload prompt, after-file menu and confirmation menu) and the quota-error Back control now include only the known `main_memory`/`main_docs` parent. The handler trusts live per-user pending state first; after expiry it accepts only those two callback contexts, while legacy/malformed callbacks retain the safe Documents fallback. The split-page prompt Back remains `docflow|back_received` and unchanged.
- GREEN: the source-extracted exact registered-handler module ran five tests — `Ran 5 Document Back tests — OK`. It covers all three keyboard builders for `save_document` and `split_pdf`, the actual quota-error early-stop branch using fake metadata, real TTL expiry via `get_doc_tool_pending`, Notes parent restoration, and existing split-page selection-preserving Back.
- Scope/limits: callback data plus UI Back controls in the quota-error screen only; no document body, DB, wallet mutation, file save/send or processing continuation, provider, AutoPost, product engine, real Telegram, deploy or restart. The test module is added to the consolidated safe-navigation CI step; CI and full `bot.py` compile remain delivery gates.
- Status: locally fixed and focused-verified; the broader Document handler/action routes and Telegram-client visual/latency evidence remain partial.

### S12.35.135 — Admin Knowledge Vault instruction labels

- Contract: keep Vault callbacks and operations unchanged while making command-guide shortcuts read as instructions, not immediate Import/Search actions. Preserve Home and all list/action destinations.
- RED: actual source-extracted `vault_admin_keyboard` emitted “Import học liệu” for `vault|import`, but the registered handler opens slash-command instructions; the new label assertion failed on this mismatch.
- Fix: rename only the two guide destinations to “Hướng dẫn import học liệu” and “Hướng dẫn tìm kiếm”; callback values are unchanged.
- GREEN: the new guide-label assertion and existing Home → registered Menu test ran together: `Ran 2 tests in 0.374s — OK`. The complete CI-listed root/menu module then ran `Ran 39 tests in 16.171s — OK`. The root/menu test file `py_compile` and `git diff --check` exited 0. Existing source evidence in S12.35.128 covers Home dispatch; no Vault operation was executed.
- Scope/limits: no prompt/import/search/review/approve/sync/backup action, database or production data, provider, wallet, AutoPost, engine, Telegram, deployment or restart. Client display and translation layout remain unverified; whole audit remains ACTIVE.
- Status: local UI-only fix, pending consolidated CI and final scope/delivery gate.

### S12.35.136 — Fresh 24-hour anonymous callback latency recheck

- Contract: inspect the latest 24-hour server callback window only; emit aggregate-safe evidence and do not infer client/network causes without a timed, matching click.
- Evidence: strict-host, read-only journal query at approximately 2026-10-09 02:38 +07 returned exactly the two previously observed records, both `prefix=menu`, `route_key=unclassified`, `outcome=ok`: dispatch 306.038 ms and 360.419 ms (average 333.2 ms; maximum 360.4 ms); guard 33.458/48.036 ms; handler 271.747/310.951 ms; render helper 90.793/101.572 ms. No event exceeded 500 ms or 1000 ms and no `account_root` event appeared.
- Finding/limits: no server-side callback delay reproduced in those two menu samples. They do not correlate with the reported Account Back 2–3 s, do not cover all buttons, and cannot separate Telegram rendering, client, or network time. A7 remains partial until an Owner click timestamp matches an Account event and broader samples exist. No cause or hardware purchase is inferred.
- Scope: anonymous timing fields only; no IDs, callback payloads, message contents, log writes, code change, Telegram action, deploy or restart.

### S12.35.137 — Document Add-more and Remove-last controls

- Contract: dispatch the actual Add-more and Remove-last buttons emitted by Document keyboards through the exact registered callback. Add-more must retain staged files/options; Remove-last removes only the latest staged item and returns to upload when no items remain. Do not process or send a file.
- Finding/evidence: no mismatch reproduced. `docflow|send_more` preserved both in-memory file fixtures and `awaiting_page_spec`, displayed the upload prompt, and acknowledged once. Repeated emitted `docflow|pop` retained the first file after removing the second; removing the last returned to upload with zero files and one ACK per press. All were source-extracted production keyboard/handler paths with fake metadata. The first attempt stopped on a missing fixture dependency (`doc_tool_display_copy`); adding an inert stub corrected the harness, not product code.
- Scope/limits: no source/test change, real file, persistent storage, database, provider, wallet, AutoPost, engine, Telegram, deployment or restart. Other Document processing terminals and live client timing remain unverified; route-family status is still partial.

### S12.35.138 — Internal Archive department Search Back after expiry

- RED/root cause: the actual department-search prompt emitted generic `archive|back_department`. Once the real pending-state TTL getter expired and removed its `department`, dispatching that emitted callback through the registered Archive handler returned to Archive root rather than the department that opened Search.
- Fix: only this Search prompt's Back now carries the validated department (`archive|back_department|<department>`). The handler uses the allowlisted suffix only when pending state is gone; a live per-user department still wins over stale callback context. Root Search Back remains `archive|root`.
- GREEN: source-extracted production keyboards, TTL helpers and exact registered handler passed 11 focused Archive tests, including root Search → Back, department Search → Back after 901 seconds, and live-state precedence over a stale department suffix. All callbacks received one ACK. The emitted department Search → Home then traversed the exact registered Menu handler and cleared only the actor's pending search, preserving another user's state (focused method: `Ran 1 test — OK`; full CI-listed root/menu module: `Ran 51 tests in 22.448s — OK`). The new regression module is included in consolidated safe-navigation CI.
- Scope/limits: no search was executed, no Archive record/file was read or written, and no DB, provider, wallet, product engine, AutoPost, real Telegram action, deploy or restart occurred. Local pytest is unavailable; full CI remains a consolidated gate. Archive action paths, manual client UI and latency remain partial.

### S12.35.139 — Package detail Back returns to its emitting group

- Contract: follow the actual package screen emitter into the Image package group, open a monthly package using its emitted detail button, then dispatch that detail screen's emitted Back through the exact registered `^pkgcombo:` handler. Back must restore the same group and its emitted controls.
- Evidence: existing tests covered group → Gói/Combo through the registered handler and separately checked the static detail-back helper value, but did not traverse the emitted detail callback and emitted Back as one registered-handler chain.
- Finding: no mismatch reproduced. The actual group keyboard emitted `pkgcombo:detail:image_mini_monthly`; the registered handler rendered the fixture-only detail screen and the production manual-detail keyboard emitted `pkgcombo:group:image`; dispatching it restored `image packages` and the identical group callback set.
- Verification: `tests.test_pkgcombo_navigation_registered_callback` → `Ran 2 tests in 1.460s — OK` using the bundled Python standard-library runner. The module was already present in `.github/workflows/ci-main.yml`; no workflow change was needed.
- Scope/limits: one focused test only; no product source changed. The fixture does not dispatch `pkgbuy|confirm`, `pkgcombo:pay`, `pkgcombo:combo_pay`, or `pkgcombo:large_order`, and invokes no order, checkout, payment, provider, database, wallet, engine, AutoPost, Telegram, deploy, or restart path. This closes only package group/detail/Back navigation evidence; other package actions remain outside this spec.

### S12.35.140 — Combo detail Back returns to the Combo group

- Contract: open Combo trọn gói from the emitted Gói/Combo menu, select an actual emitted Combo detail button, then dispatch that detail keyboard's Back through the exact registered `^pkgcombo:` handler. Back must restore the Combo group and its same controls.
- Evidence gap: existing package coverage exercised monthly Image details and static Combo detail-back helper output, but not the Combo group keyboard → emitted Combo detail → emitted Back chain.
- Finding: no mismatch reproduced. The production Combo group keyboard emitted `pkgcombo:combo_detail:combo_ad_video_588k`; the registered handler rendered fixture-only detail using the production manual-detail keyboard; its Back emitted `pkgcombo:group:combo`, which restored the Combo screen and identical callbacks.
- Verification: `tests.test_pkgcombo_navigation_registered_callback` → `Ran 3 tests in 2.542s — OK` using the bundled Python standard-library runner. The module was already included in safe-navigation CI.
- Harness note: the first attempt returned no Combo detail controls because the existing test fixture replaced `pricing_combo_keyboard` with an empty stub. Removing that fixture-only override exposed the production builder; the corrected test passed. No product assertion failed and no production code changed.
- Scope/limits: navigation only. No `pkgbuy|confirm`, pay/combo-pay, large-order dispatch, checkout, order request, wallet, provider, DB, job, product engine, AutoPost, real Telegram, deploy, or restart action. Other package operations and Telegram-client visuals remain outside this spec.

### S12.35.141 — Package notes Back returns to Gói/Combo

- Contract: select the actual `pkgcombo:notes` control emitted by the production package home, dispatch it through the exact registered handler, then use its emitted Back. It must render the original package home with the same callbacks.
- Evidence gap: existing tests asserted the static package-notes content and that a Back callback exists, but did not dispatch both emitted controls through the registered handler.
- Finding: no mismatch reproduced. The Notes screen emitted `pkgcombo:home`; dispatch restored the package-home fixture text and identical callback set.
- Verification: final `tests.test_pkgcombo_navigation_registered_callback` run → `Ran 4 tests in 4.387s — OK` using the bundled Python standard-library runner. The module was already included in safe-navigation CI.
- Scope/limits: informational navigation only. The visible `pkgcombo:large_order:notes` control was not dispatched; no order, checkout, payment, provider, DB, wallet, engine, AutoPost, Telegram, deploy, or restart path ran.

### S12.35.142 — My Packages Back returns to Gói/Combo

- Contract: from the production package-home keyboard, dispatch the emitted `pkgcombo:my` control through the exact registered handler using an inert account-summary seam. Then dispatch My Packages' emitted Back and verify that the same package-home callback set returns.
- Evidence gap: previous tests checked the static Back control and exercised Account → My Packages separately; they did not dispatch the package-home My Packages route and its Back as one exact-handler chain.
- Finding: no mismatch reproduced. The read-only screen rendered the fixture summary, emitted Back `pkgcombo:home`, and restored the package-home fixture render and identical callbacks.
- Verification: the final `tests.test_pkgcombo_navigation_registered_callback` module, including all five package navigation chains, ran `Ran 5 tests in 7.581s — OK`. This module is already included in safe-navigation CI.
- Scope/limits: the real account summary/DB seam is stubbed and no customer package data was read. No purchase, large-order, checkout, payment, provider, wallet, engine, AutoPost, Telegram, deployment, or restart action occurred.

### S12.35.143 — Pricing catalog Membership/Promotion label-to-route review

- Contract: verify the Vietnamese catalog button's visible label, emitted callback, actual Pricing handler destination and Back ancestry; change nothing if the label accurately describes the screen.
- Evidence: `pricing_catalog_keyboard` emits “🎁 Khuyến mãi / Thành viên” → `pricing|member`; `handle_pricing_callback` dispatches `member` to the public member-pricing section and its policy keyboard. The rendered section title is “Khuyến mãi & Thành viên” and copy covers service discounts plus promotion/top-up boundaries.
- Existing regression evidence: `tests/test_p0_21a_pricing_tables_user_guides_only.py` asserts the actual menu label/callback pair and membership/promotion copy; `tests/test_profile_pricing_back_origin.py` dispatches `pricing|member` through the registered handler and verifies Back to legacy Pricing or the preserved Account origin.
- Finding: no mismatch; no source/test change. Slash versus ampersand is only wording variation and the destination includes both concepts, so no label edit is justified.
- Scope/limits: source review plus existing test evidence only; no pricing mutation, payment, wallet, provider, Account DB read, production message, or engine action. This does not validate the entire Pricing catalog or visual rendering on a Telegram client.

### S12.35.144 — Reconcile all 16 Vietnamese Pricing catalog controls

- Contract: source-review every Vietnamese label/callback pair emitted by `pricing_catalog_keyboard("vi")` against its registered route and actual handler branch. Do not dispatch document-send, package-purchase, top-up, payment, or provider actions.
- Source mapping (all 16 emitted controls):

| Label | Emitted callback | Registered destination |
|---|---|---|
| Bảng giá tổng | `pricing|total` | `handle_pricing_callback` → `pricing_main_lines` + Pricing catalog keyboard |
| Giọng nói | `pricing|voice` | Pricing voice detail |
| Nhạc AI | `pricing|music` | Pricing music detail |
| Video | `pricing|video` | Pricing video detail |
| Phụ đề / Lồng tiếng | `pricing|subtitle` | Pricing subtitle/dubbing detail |
| Hình ảnh | `pricing|image` | Pricing image detail |
| Tài liệu/PDF | `pricing|docs` | Pricing document detail |
| Miễn phí / Không tính Xu | `pricing|free` | Pricing free-use detail |
| Khuyến mãi / Thành viên | `pricing|member` | Public member/promotion section + policy keyboard |
| Hướng dẫn sử dụng | `pricing|guide` | Usage guide + Back to Pricing |
| Tải bảng giá | `pricing|download_pricing` | Registered generated-document send branch; not invoked |
| Tải hướng dẫn | `pricing|download_guide` | Registered generated-document send branch; not invoked |
| Ghi chú/Lưu trữ | `pricing|storage` | Pricing storage detail |
| Gói/Combo | `pkgcombo:home` | Separate `^pkgcombo:` handler → package home |
| Quay lại | `pricing|main` | Pricing hub/main keyboard |
| Menu chính | `menu|main` | Separate `^menu\\|` handler → main menu |

- Registration/source evidence: `bot.py` registers `handle_pricing_callback` on `^pricing\\|`, `handle_pkgcombo_callback` on `^pkgcombo:`, and `handle_menu_callback` on `^menu\\|`; each ordinary Pricing action above has a corresponding explicit branch. `pkgcombo:home` renders `pricing_packages_lines` and the package keyboard; `menu|main` renders the prepared main-menu text/keyboard.
- Verification: `tests.test_profile_pricing_back_origin` ran 13 tests in 89.627s — OK, including catalog → total → Back restoration, member/promotion Back ancestry, and unsupported-origin denial. Existing static catalog assertions are present in `tests/test_p0_21a_pricing_tables_user_guides_only.py`, but a separate invocation was stopped before assertions because importing the full bot remained CPU-bound with no output; it is not counted as a test result. The 16-pair conclusion is a direct source reconciliation, not a claim that every screen was dispatched end-to-end.
- Finding: no label/callback/registration/handler mismatch found; no code, test, or workflow edit was justified.
- Scope/limits: both download actions were source-reviewed only; no document was sent. No package purchase/order, top-up, payment, provider, wallet, customer/account data, DB, production Telegram, product engine, AutoPost, deployment, or restart action. Visual client layout and end-to-end behavior of all 16 screens remain unverified.

### S12.35.145 — Pricing hub dynamic controls and destination review

- Contract: source-review the parent Pricing keyboard under its Vietnamese domestic-promotion, Vietnamese non-domestic, English/Chinese, and other-locale branches. Match every emitted control to the registered handler and expected destination; do not query real market eligibility or invoke send/transaction actions.
- Evidence: the source gate is explicit: only Vietnamese + `user_id is None` or domestic-market eligibility exposes “Xem ưu đãi” → `pricing|promotions`; the non-domestic Vietnamese branch substitutes “Nạp Xu” and omits the offer control. English/Chinese show Pricing, Top-up, Packages/Combos, and Home. Other-locale fallback additionally exposes Guide, both generated-document controls, and Support. Every branch routes to its corresponding Pricing callback branch or registered `^menu\\|` / `^pkgcombo:` handler.
- Destination review: `pricing|catalog` opens the catalog; `pricing|promotions` opens Offers; top-up is wrapped by the Pricing renderer as `menu|main_topup|pricing_main` and the existing menu handler restores Pricing on Back; `pkgcombo:home` opens package home; download callbacks enter their matching document-send branches (not invoked); `pricing|guide` opens the guide; `menu|support` renders the Support screen; and `menu|main` renders Main.
- Existing regression evidence: `tests.test_profile_pricing_back_origin` ran 13 tests in 89.627s — OK, including origin-aware top-up Back and promotion ancestry. This validates selected paths, not dispatch of every locale/market variant.
- Finding: no source label/route mismatch; no source or test change was justified. Market branching and labels were source-reviewed without querying an actual user/market record.
- Scope/limits: no generated document sent, actual market lookup, top-up/transaction/payment, provider, wallet, account data, DB, production Telegram, product engine, AutoPost, deployment, or restart. Locale/viewport rendering and all variant handlers remain only partially proven.

### S12.35.96 — Public root menu layout contract recheck

- Contract: verify the public main-menu row structure, retained safe shortcuts, and callback-registration mapping using the CI-listed source-extracted root/menu test; do not change production layout.
- Evidence: `tests.test_admin_root_menu_callback_single_ack.AdminRootMenuCallbackSingleAckTests.test_public_main_menu_small_flow_callbacks_match_their_registered_handlers` ran 1 test in 0.241s — OK. It asserts eight rows (one singleton + seven paired), expected shortcut callbacks, and registration patterns for selected small-flow routes. The same module is in the consolidated safe-navigation CI step.
- Finding: no root row-count or callback-registration mismatch reproduced; no production UI change.
- Scope/limits: this focused case verifies Vietnamese public root shape and selected callback patterns only. It does not establish all-locale/admin visual rendering, viewport wrapping, Telegram-client appearance, or all downstream actions. No provider, wallet, DB, AutoPost, product engine, Telegram, deploy, or restart action.
### S12.35.146 — Anonymous callback timing recheck (A7)

- Contract: inspect only the latest 24-hour `callback_dispatch_timing` records and aggregate anonymous route/timing fields. Attribute the reported Account → Back delay only when an Account-route event matches a precisely timed Owner click; do not infer client, Telegram, server, or network cause from unmatched events.
- Evidence: strict-host, read-only journal query around 2026-10-09 03:50 +07 found two callback timing records. Aggregate dispatch was 333.228 ms average and 360.419 ms maximum; guard maximum was 48.036 ms, handler maximum 310.951 ms, and render-helper maximum 101.572 ms. The returned records did not expose a `route_key` field.
- Finding/limits: neither record can be attributed to `account_root` or correlated with the Owner's reported click. These generic timings do not explain the 2–3 second client delay and do not establish that all buttons are smooth. A7 remains partial pending a route-bearing, precisely timed Account sample; no cause or hardware purchase is inferred.
- Scope: anonymous timing query and aggregation only. No raw unrelated journal output, IDs/payloads, source/config change, Telegram action, provider, wallet, deploy, or restart.

### Consolidated local verification refresh — 2026-10-09

- The CI-listed standard-library callback/UI modules for root navigation, Document Back, Feedback, Internal Archive, and package navigation ran together: `Ran 53 tests in 34.370s — OK`.
- The first combined command also named `tests.test_voice_settings_input_back`, but local import stopped before its assertions because `pytest` is not installed in the configured runtime. This is a local runner limitation, not a product assertion; keep that module for consolidated CI.
- Required full `bot.py` `py_compile` was attempted and remained without output/exit code for more than six minutes, then was interrupted. Status is `NOT_VERIFIED`, not pass or product failure; full-source compile in CI is a merge gate.
- `git diff --check` passed before this note. The configured local runtimes have no PyYAML/YAML package, so state-file parser validation remains a CI gate.

### Consolidated delivery readiness — 2026-10-09 04:25 +07

- Owner excluded S12.35.106 from this UI batch; dependent S12.35.108 is dropped. The existing Image Story aspect/prompt mismatch remains unresolved. Keep only the independent S12.35.107 render-hint test; no prompt/engine change is included.
- Current runtime gate is clear: GitHub main and VPS `/opt/toanaas/bot` both read `96dd90201a89465555871276cf687fdebfff8cb0`; merged PR #1409 is present; bot/web/nginx active, `NRestarts=0`; health returned `ok` at 04:25:05 +07. The previously held Product Video delta is already in the identical current main/runtime base.
- Fresh focused local verification after rebase on main `96dd9020…`: `Ran 53 tests in 25.490s — OK` across root navigation, Document Back, Feedback, Internal Archive, and package navigation. A wider invocation could not import `tests.test_core` because `fastapi` is unavailable; Voice Settings similarly awaits CI because `pytest` is unavailable. Full `bot.py` compile remains `NOT_VERIFIED` after the earlier multi-minute no-output attempt. Require CI compile, focused tests, and workflow/YAML validation before merge.
- The batch is local and not delivered. Rebase once on `96dd9020…`, compare the exact outgoing diff to protect engines/providers/workers/wallet/AutoPost, then run one consolidated PR/merge/bot-only deploy cycle only if all CI and runtime checks pass. Account Back 2–3s correlation, visual/viewport QA, and Support category-picker behavior remain explicitly open/deferred.

### Consolidated delivery refresh — after PR #1415

- PR #1415 is merged at `4dc0c31bab44d2c0427a7d4ab38b28b1e72693ec`; deploy workflow run [#37849493306](https://github.com/manhtoangreensky-wq/bot/actions/runs/37849493306) succeeded with `deploy_workers=false`. Readback recorded main and VPS bot at that SHA, bot/web/nginx and checked workers active, `NRestarts=0`, and internal health `ok`. Evidence is attached to [PR #1415](https://github.com/manhtoangreensky-wq/bot/pull/1415#issuecomment-6069784833). This supersedes the earlier `96dd9020…` delivery-readiness snapshot above; it does not close the broader audit.
- The current local continuation is on `audit/storage-addon-expiry-20261009`, based on the verified `4dc0c31…` runtime SHA. Keep it in the single consolidated batch: no per-spec PR, merge, deploy, or restart. The owner-excluded Image Story S12.35.106 and dependent .108 remain out of scope; do not restore the prompt-pack change.
- A7 remains partial: no callback log event was correlated to the reported Account → Back click. The 2–3 second estimate is not evidence that every button is smooth. Telegram-client visual/viewport QA and Support category-picker behavior remain open or owner-deferred.

### S12.35.147 — Expired Storage Add-on custom input consumes stale text

- Contract: after the emitted `storage|custom` prompt expires, the next ordinary non-command message must receive the localized expiry/no-charge notice and Storage Add-on keyboard, and must be consumed before later `handle_message` text handlers. Slash commands must still pass through. Clear only the user's expired custom-input entry; do not enter purchase/payment.
- RED: the baseline expiry getter removed the stale entry, then `handle_storage_addon_pending_text` returned `False`, allowing `handle_message` to continue dispatching later text handlers. The focused pre-fix assertion failed at `handled is True` as expected; this was a behavioral failure, not fixture setup. A follow-up Spanish handler regression also reproduced the raw `common.expired_not_charged:es` key because shared `UI_TEXT` has that key only for vi/en/zh.
- Fix: the handler snapshots only the current user's pending record before the expiry getter. If an expired `custom` record is removed, non-command text is answered with feature-local localized expiry/no-charge copy and the Storage Add-on menu, then returns `True`. The copy covers all 17 supported locales. Slash commands still return `False`; active custom input follows the existing confirmation path.
- GREEN: bundled Python `-m unittest tests.test_storage_addon_navigation_callbacks -v` rerun → `Ran 6 tests in 8.682s — OK`. Tests cover emitted Back/registered route, expired-input consumption and localized menu, isolation of another user's pending state, all 17 locale strings and Spanish handler output, `/start` fall-through, active custom confirmation, and the actual source-extracted production `handle_message` dispatcher with inert neighboring pending handlers; Storage consumes the message before Memory is reached. Changed test `py_compile` and `git diff --check` exited `0`.
- Limits/scope: this is source-extracted handler/dispatch evidence, not Telegram-client or live-runtime QA. Full `bot.py` compilation remains NOT_VERIFIED locally and must pass in consolidated CI. No purchase, PayOS, wallet, provider, database, real Telegram, job, engine, AutoPost, deploy, worker sync, or restart action occurred. Keep this spec local until the ordered audit and final protected-source comparator are complete.

### S12.35.148 — Public/Admin root menu locale callback reconciliation

- Contract: build the actual public and admin root keyboards with the production localized copy for every locale in `USER_LANGUAGE_ORDER`; verify required labels are present, callback sets/order do not vary by locale, every callback matches its registered handler and the Telegram 64-byte bound. Do not invoke any root destination.
- Evidence: the existing `_main_menu_dependencies` test fixture was changed only for this test to provide the real `services.pricing_guide_content.public_hub_copy`; the actual source-extracted `localized_main_menu_keyboard` and production handler registration patterns are used. User-facing label keys are checked for each locale and all generated controls checked in both public and admin mode.
- Finding: no raw/missing root label, label/callback locale divergence, unregistered callback, or callback-size violation reproduced across 17 locales. No production change was indicated.
- Verification: focused case `test_public_and_admin_root_menus_keep_registered_routes_across_all_locales` → 1 test in 1.883s — OK; the CI-listed `tests.test_admin_root_menu_callback_single_ack` module → `Ran 41 tests in 20.707s — OK`; the changed test modules compile and `git diff --check` passes.
- Limits/scope: this is keyboard/copy-data structure and registration evidence, not semantic translation review or live Telegram visual, viewport, wrapping, scroll, or tap-latency QA. No language preference write, real Telegram action, AutoPost/product route, engine, provider, wallet, database, job, deployment, or restart occurred.

### S12.35.149 — Admin Handbook root sections dispatch to their pages

- Contract: use the actual Admin Handbook keyboard and all eight emitted section controls; dispatch each through the exact registered `admin_help|` handler. Verify one ACK, matching handbook content, and emitted Handbook/Admin/Home returns accepted by the registered Menu route. Do not execute any handbook command or operational action.
- Evidence: source-extracted production `admin_handbook_menu_keyboard`, `admin_handbook_section_text`, `admin_handbook_section_keyboard`, and `handle_admin_help_callback`; exact callback registration patterns; admin identity is a fixture; Telegram edit is captured in memory.
- Finding: all eight sections (`xu`, `payment`, `refund`, `freeze`, `backup`, `runtime`, `sales`, `roles`) dispatch and render their matching page; each page emits the expected Handbook/Admin/Home routes. No callback mismatch found.
- Verification: focused `test_all_emitted_handbook_sections_dispatch_and_return_to_admin_handbook` passed; full CI-listed `tests.test_admin_help_callback_single_ack` → `Ran 6 tests in 2.840s — OK`; changed module compilation and `git diff --check` passed. An initial test-only assertion used object identity for two separately constructed keyboard fixtures; value-based label/callback comparison fixed that harness mistake, with no production code change.
- Limits/scope: handbook display/navigation only. No live report, financial or user data, Xu, PayOS, provider, worker, backup, DB, customer/admin message, real Telegram, deploy or restart action. It does not prove the report and operational commands described by the guide actually function.

### Final A7 latency recheck — 2026-10-09 10:33 +07

- Read-only strict-host VPS query of the last 24 hours returned `callback_dispatch_timing_count=0`; therefore there is no route-level sample to correlate with the reported 2–3 second Account → Back interaction.
- The same window had zero warning/error log lines matching the checked transport/Telegram patterns (`NetworkError`, timeout, retry-after, and common Telegram HTTP/auth/conflict errors). `toanaas-bot.service` was `active/running`, `NRestarts=0` at query time.
- Finding: no server-side callback sample or matching transport warning was observed in this window. This does **not** prove the client/network was responsible or that every bot button is smooth. The Owner click still lacks an exact correlated timestamp/event, and client rendering/network from the device cannot be inferred from this VPS-only evidence. A7 remains partial; no logger/source change or hardware recommendation is justified.
- Scope: aggregate-only journal query and service health properties. No raw journal lines, IDs, callback payloads, external API calls, Telegram messages, provider calls, data writes, deploy, or restart.

### A7 tap follow-up — 2026-10-09 11:06 +07

- The Owner confirmed tapping but did not provide an exact `HH:MM:SS`. A strict-host, aggregate-only journal query over the latest 10 minutes returned 2 `callback_dispatch_timing` events. The latest event was at 11:04:59 +07, static prefix `menu`, handler `handle_menu_callback`, `guard_ms=35.401`, `handler_ms=163.551`, `render_helper_ms=80.185`, and `dispatch_ms=199.914`; the two-event sample averaged 237.3 ms dispatch (max 274.8 ms). No checked transport/Telegram warning pattern matched in that window.
- This is a nearby menu sample, not a certain match to the Account → Back tap. If it is the tap, measured bot dispatch was about 0.2 s; the remaining reported end-to-end delay is outside this measured handler interval, but these logs cannot distinguish Telegram/network/client rendering. A7 remains PARTIAL; one short two-event window does not establish an all-button latency distribution or prove every button smooth.
- Scope: aggregate output only; no raw journal lines, user IDs, callback payloads, messages, production writes, provider calls, deploy, or restart.

### A7 tap follow-up — 2026-10-09 approximately 11:39 +07

- The Owner confirmed tapping but initially did not identify the button or provide an exact `HH:MM:SS`. A strict-host read-only VPS query made immediately afterward found `callback_events_15m=0`; `toanaas-bot.service` remained `ActiveState=active`, `NRestarts=0`.
- There is no server timing event to correlate with this tap. This does not establish whether the click reached Telegram, nor whether delay is in the client, Telegram delivery, network, or bot. A7 remains partial; no all-button smoothness or cause is claimed.
- Scope: aggregate timing count and service properties only; no raw journal lines, IDs, payloads, messages, provider calls, data writes, deploy, or restart.

### A7 Account → Back tap follow-up — 2026-10-09 11:51 +07

- The Owner identified `Account → Quay lại` and tapped again. Source inspection confirms `route_key=account_root` is assigned only to `menu|main_profile` (opening Account), not Back. The 11:49:16 +07 event (`dispatch_ms=529.393`) therefore measures Account entry, not the Back control.
- Strict-host read-only aggregation at 11:51:30 +07 found four `menu` timing events in the preceding five minutes: one `account_root` event at `529.393 ms`, and three `unclassified` events at `208.509`, `373.478`, and `186.657 ms`. Because the shared `menu|main` Back callback is intentionally unclassified and the logger omits callback payloads, none can be identified as the Account Back tap without an exact click time; the three samples may include unrelated menu actions. At the earlier 11:49:16 +07 query, the service was active with `NRestarts=0` and the 5-minute transport/Telegram warning count was zero.
- Destination check: the existing CI-listed `test_customer_root_account_renders_actual_keyboard_and_home_returns_to_main` dispatches the actual Account keyboard's `menu|main` control through the registered menu handler and verifies it renders `MAIN SCREEN`; that functional Back route passed in the 42-test module. This does not measure live latency.
- Findings: sampled server-side menu dispatches ranged from `186.657` to `529.393 ms`, but Account Back itself remains unmeasured. This does not explain the reported 2–3 s end-to-end delay or assign the remainder to Telegram, network, client rendering, or another component. A7 remains partial; no all-button smoothness claim.
- Scope: allowlisted anonymous route/timing fields, aggregate warning count and service properties only; no raw journal record, IDs, payloads, messages, provider calls, data writes, deploy, or restart.

### S12.35.150 — Stale AI Chat consent callback after opt-out

- Contract: an old emitted `aichat|consent_on` button must not grant or persist consent if the user is disabled and `pending_consent` is false. Return to Free Tools in that state; if already enabled, show current status. Leave the valid pending-consent grant path unchanged. No AI Chat action/provider behavior is in scope.
- Root cause: the callback previously called `enable_with_consent` unconditionally for `consent_on`, so a stale inline button could bypass the `pending_consent` state after opt-out.
- Minimal fix: add a guard at the exact callback branch. A stale disabled callback returns to the Free Tools root without state save; an already-enabled callback renders current status; only a genuinely pending consent reaches the pre-existing grant operation.
- GREEN: focused `test_aichat_consent_requires_pending_state_and_preserves_valid_grant` → `Ran 1 test in 0.340s — OK`; it covers both stale opt-out denial/no-save and the still-valid pending-consent grant. Full `tests.test_admin_root_menu_callback_single_ack` → `Ran 42 tests in 23.118s — OK`; changed test `py_compile` and `git diff --check` both exited `0`. The test uses the production consent keyboard builder, exact registered handler pattern and source-extracted production callback with fixture-only state/service/Telegram doubles.
- Limits: no production account state, real Telegram callback, AI action/provider, persistence, wallet, or database was invoked. Full `bot.py` compile remains `NOT_VERIFIED` locally and must pass in the consolidated CI/source-compile gate. This spec is local and not yet delivered; keep it in the single consolidated batch.

### A7 all-callback latency census — 2026-10-09 11:54 +07

- Contract: inspect seven days of deployed anonymous `callback_dispatch_timing` events, grouped by static prefix/route/handler; report counts above 500/1,000/2,000 ms and correlate common Telegram/network warning signatures within 60 seconds. Do not return raw log lines, callback data, user IDs or message content. Interpret handler-level evidence separately from Telegram-client end-to-end time.
- Telemetry coverage: runtime SHA `c3f40e4…` contains the timing logger. `tests.test_callback_dispatch_timing` passed 5 tests in 13.422s; it verifies installation after the last directly registered callback, captures guard/handler/shared-render timings, and asserts callback payload, message text and user ID are absent from emitted log output.
- Evidence: the seven-day journal window returned 10 callback events, all `prefix=menu` / `handle_menu_callback`; global average `337.692 ms`, median `333.229 ms`, max `529.393 ms`. Two events exceeded 500 ms, none exceeded 1,000 or 2,000 ms. The 11 matching warning-signature lines over the window had zero events within 60 seconds of any callback, including both >500 ms events.
- Outliers: `2026-10-07 22:14:45 +07` was a menu handler with missing route classification, dispatch `512.953 ms` (guard `59.691`, handler `451.334`, render-helper `99.508`); callback identity is unavailable. `2026-10-09 11:48:51 +07` was `route_key=account_root`, dispatch `529.393 ms` (guard `30.743`, handler `497.735`, render-helper `176.002`). The source classifier maps that key only to `menu|main_profile` (Account entry), not Account Back. Three contemporaneous unclassified menu samples were `208.509`, `373.478`, and `186.657 ms`; the generic `menu|main` Back cannot be singled out without callback payload or exact click time.
- Root-cause decision: the end-to-end 2–3 second Account → Back delay was not reproduced in server dispatch; no server callback exceeded 1 second in the seven-day sample. Account entry does perform synchronous balance/role/package-summary reads, but the available two samples (average `402.077 ms`, max `529.393 ms`) do not identify which sub-call caused the single >500 ms sample, so no speculative database/cache/router change is justified. The emitted Account Back route itself passes the existing source-dispatch test and returns to `MAIN SCREEN`.
- Limits: 10 events is a sparse sample and all are menu callbacks, so other callback families have no live latency observation in this window. This is not proof that all buttons are fast or that the missing end-to-end time is caused by the client/network. Keep A7 PARTIAL; collect a precise click time if the Account Back delay recurs. No production code, provider, wallet, DB, Telegram send, deploy or restart was changed/performed for this census.

### A7 route and runtime recheck — 2026-10-09 12:01 +07

- Read-only source/runtime gate: GitHub main and VPS bot runtime both equal `62566249d4d54f6047ab33ddffd1bf94c57d0e41`; live `bot.py` SHA-256 is `109d7a301e81550977c4adf57b30dd816e2faa0a2d061f80415ed823a7f6f9b1`; PR #1409 commit `d24716db154b77aadebfdefe87ab9cac17416bd2` is an ancestor. `toanaas-bot.service` is active/running with `NRestarts=0`. This audit did not deploy or restart. Runtime now includes the previously noted #1417 Web Image source delta; no product output was invoked or validated here. This supersedes the 11:54 main/runtime snapshot near the top of this report.
- Seven-day callback window is unchanged: 16 timing records total (10 dispatch + 6 legacy); all dispatch records are `menu` / `handle_menu_callback`. Average dispatch `337.692 ms`, median `333.229 ms`, max `529.393 ms`; 2 exceed 500 ms, none exceed 1,000 or 2,000 ms.
- The recent fixed-route records include `menu|main` at 11:48:53 +07 (handler `173.293 ms`, dispatch `208.509 ms`), `menu|main_video` at 11:49:01 (handler `291.160 ms`, dispatch `373.478 ms`), and `menu|main` again at 11:49:05 (handler `154.158 ms`, dispatch `186.657 ms`). They are consistent with the reported Back/Video sequence, but cannot be tied to each tap without an exact timestamp. The `529.393 ms` outlier is Account entry, not Back.
- No other callback family has a live sample; the callback timing wrapper does not measure ReplyKeyboard text-message handlers. No 2–3 second server callback or new slow route was reproduced, so there is no safe, evidence-backed code fix to apply in this latency slice. This does not prove all bot buttons are fast or identify client/Telegram/network cause. A7 remains PARTIAL; no all-button smoothness claim.

### S12.35.151 — Internal Archive stale/malformed view and file callbacks

- Contract: emitted Archive result buttons must still render the selected fixture record; malformed/missing IDs and stale records/files must return one alert ACK, must not raise, must not call the document accessor for malformed IDs, and must not clear unrelated pending handlers. Only fixture accessors are used; no production documents or files are read/sent.
- RED: the first test run exposed two test-harness defects (an undefined registration helper and an expectation inconsistent with the actual emitted Back controls); those were corrected before accepting RED. Corrected RED reproduced `ValueError` for nonnumeric IDs, no alert for missing ID, duplicate ACK for stale record/file, and pending cleanup before validation.
- Minimal fix: `handle_internal_archive_callback` now handles only `view`/`file` first, validates a decimal ID, performs the owner-scoped lookup, and gives exactly one result-appropriate ACK. Valid selections retain the existing detail render/file delivery path; unrelated Archive actions are unchanged.
- GREEN: `python -m unittest tests.test_internal_archive_search_back_origin tests.test_internal_archive_preview_callback_single_ack tests.test_internal_archive_save_callback_single_ack -v` → `Ran 7 tests in 11.218s — OK` (Search and Save cases). The Preview module uses standalone pytest-style checks, so its two ACK/navigation cases were executed directly and passed (`Ran 2 standalone Archive Preview checks — OK`). Changed test modules compiled and `git diff --check` exited 0. Full `bot.py` compile and consolidated CI remain required.
- A7 current-window recheck at 12:21 +07: strict-host aggregate-only VPS query for 15 minutes found zero callback timing events; bot service remained active/running, `NRestarts=0`. This yields no new slow-route evidence and cannot prove all buttons smooth. The seven-day prior census remains menu-only and sparse; ReplyKeyboard/message paths and end-to-end Telegram/client rendering remain unmeasured.
- Limits: source-extracted fixture tests are not a live Telegram interaction. No engine, provider, worker, AutoPost, wallet, production data, real send, deploy, merge, or restart was touched. Keep the batch local and A7 partial.

### A7 Start/Home/Video per-phase latency recheck — 2026-10-09 12:29 +07

- Strict-host, read-only seven-day aggregation of the menu handler's fixed-route `callback_latency` fields matched 6 events, all `role=admin`: `menu|main` count 5 (average handler `220.728 ms`, max `309.919 ms`; max pre-ACK `0.119 ms`, ACK `179.210 ms`, language `10.096 ms`, cleanup `22.105 ms`, build `12.520 ms`, render `101.631 ms`) and `menu|main_video` count 1 (handler `291.160 ms`; pre-ACK `0.040 ms`, ACK `180.930 ms`, language `6.827 ms`, cleanup `9.908 ms`, build `2.003 ms`, render `91.453 ms`). None of the measured phases is near the reported 2–3 seconds.
- These are sparse admin-only samples and cannot be tied to a specific Owner tap. The preceding 15-minute callback window had zero events and the service was active with `NRestarts=0`. The earlier seven-day generic callback census also contained only menu handlers; other callback families, public-user routes, ReplyKeyboard paths, viewport rendering and device/network time remain unmeasured. A7 stays PARTIAL; no all-button smoothness or network-cause claim.
- Scope: aggregate timing fields only; no raw journal records, IDs, callback payloads, messages, data writes, provider calls, deployment or restart.

### S12.35.152 — Internal Archive emitted File button reaches the send boundary

- Contract: use the actual emitted search-result `view` button, dispatch it through the production Archive registration/handler to its detail keyboard, then dispatch the emitted `file` button through that same route. Assert one ACK and the expected fixture file ID, chat ID, and caption at a fake `context.bot.send_document` boundary. Do not read a production document or send a real Telegram file.
- Evidence: no production behavior change was indicated. The test was added first as route-coverage evidence and passed on its first run: `python -m unittest tests.test_internal_archive_search_back_origin -v` → `Ran 6 tests in 12.824s — OK`. Final adjacent rerun `python -m unittest tests.test_internal_archive_search_back_origin tests.test_internal_archive_save_callback_single_ack -v` → `Ran 8 tests in 11.053s — OK`; 2 standalone Archive Preview ACK/navigation checks also passed. Changed test modules compiled and `git diff --check` exited 0. The regression asserts the emitted `archive|file|441` control is registered, reaches the actual source-extracted handler, and forwards exactly `fixture-file-id` with caption `Hồ sơ #441: Fixture policy` once.
- Limits: the Telegram send boundary is a fake, so this proves callback wiring and payload construction only, not Telegram delivery. No real file, customer document, production data, wallet, provider, engine, AutoPost, deploy, merge, or restart. Keep the broader A3/A5 checklist partial.

### S12.35.153 — Internal Archive emitted Recent button returns to its department

- Contract: open the customer Archive department dashboard from the actual emitted control, take its emitted `archive|recent` callback through the registered Archive handler, and verify one acknowledgement, fixture-only Recent lookup, rendered result controls, correct pending department, and Back to the same department dashboard. No production Archive data or documents.
- Evidence: `test_emitted_recent_button_renders_fixture_and_back_returns_to_department` passed. The combined Archive Search/Recent/Detail/File/Back and adjacent Save unittest run completed `Ran 9 tests in 11.715s — OK`; 2 standalone Preview ACK/navigation checks passed. The changed test modules compiled and `git diff --check` exited `0`.
- Finding: no callback destination or rendering mismatch reproduced; no production code change was indicated. This verifies route behavior only, not Telegram client render time.
- Limits: fixture accessors and fake Telegram methods only; no real send, customer record/document, database, provider, wallet, product engine, AutoPost, deploy, merge, or restart. A3/A5/A6/A7 and all-button live latency remain partial.

### A7 Account → Back post-tap recheck — 2026-10-09 12:42 +07

- The Owner reported another tap of Account → Back. A strict-host, aggregate-only VPS journal query over the preceding 15 minutes returned `callback_events=0` and `transport_telegram_warning_matches=0` for the checked timeout/network/Telegram error signatures.
- The VPS was rechecked at 12:45 +07: bot `ActiveState=active`, `SubState=running`, `NRestarts=0`; deployed HEAD `62566249d4d54f6047ab33ddffd1bf94c57d0e41`; health `status=ok`; callback instrumentation marker present. No event can be correlated to this tap. This is not evidence that the tap failed to reach Telegram, and it does not distinguish bot processing, Telegram delivery, network, or client rendering. No other callback family has current live latency evidence; the existing seven-day sample is sparse and menu-only, and ReplyKeyboard/message handlers are outside the callback timing observer.
- No raw logs, IDs, payloads, user content, provider calls, data writes, deployment, or restart. Keep A7 PARTIAL; no all-button smoothness or cause claim.

### A8 local syntax gate — current audit batch

- The bundled Python runtime completed `python -m py_compile bot.py` in the current audit worktree with exit code `0` and no diagnostics. The changed Archive test modules also compiled; `git diff --check` was clean at the prior verification point.
- The safe-navigation CI invocation now includes the registered Archive Search/Recent/Detail/File route tests plus the adjacent Archive Preview single-ACK and Save replay-guard modules, so the locally checked regression edges run in the consolidated batch.
- This closes only local syntax verification. Consolidated configured CI, final diff/protected-scope review, and the requested single delivery cycle remain open; no push, PR, merge, deploy, or restart occurred.

### S12.35.154 — Public international Pricing catalog Back returns to Pricing hub

- Contract: for every public-copy locale outside `vi`/`en`/`zh`, open Pricing hub → follow its actual emitted Catalog control through the registered `^pricing\\|` handler → inspect the emitted catalog keyboard → dispatch Back through the same registered handler. Back must return to the Pricing hub. Preserve the existing top-up origin control and all other fallback destinations; do not send generated documents or enter payment/top-up operations.
- RED: the actual French public route rendered catalog content but reused `pricing_main_keyboard` unchanged; it emitted no Back-labeled control, and its “Pricing” button repeated `pricing|catalog`. The account-origin test had hidden this because its origin wrapper inserts a separate Back.
- Minimal fix: only in the unsupported-catalog-locale fallback, replace the emitted `pricing|catalog` control with localized `common.back` → `pricing|main`. The other fallback buttons remain in their original order; Pricing handler still scopes Top-up Back to `menu|main_topup|pricing_catalog`.
- GREEN: the new source-extracted test dispatches all 14 locales in `PUBLIC_COPY_LOCALES - {vi,en,zh}` through the actual registered Pricing callback; it checks the localized Back label, exact return to hub, preservation/order of all other controls, and one ACK. Focused test passed; full `tests.test_profile_pricing_back_origin` ran `14 tests in 76.239s — OK`.
- Scope/limits: one fallback keyboard branch and one regression method. No pricing values, admin settings, payment, generated document, account DB, wallet, provider, product engine, AutoPost, customer message, production Telegram, deploy, merge, or restart. `git diff --check` and `python -m py_compile bot.py tests/test_profile_pricing_back_origin.py` exited 0; consolidated CI remains a final batch gate.

### A7 all-callback latency recheck and pre-ACK source screen — 2026-10-09 13:33 +07

- Live scope: strict-host, read-only VPS check confirmed runtime HEAD `62566249d4d54f6047ab33ddffd1bf94c57d0e41`, deployed `bot.py` SHA-256 `109d7a301e81550977c4adf57b30dd816e2faa0a2d061f80415ed823a7f6f9b1`, callback observer marker present, and `toanaas-bot.service` active/running with `NRestarts=0`.
- Seven-day aggregate-only callback census is unchanged: 10 `callback_dispatch_timing` events, all `prefix=menu` / `handle_menu_callback`; average `337.692 ms`, max `529.393 ms`, two above 500 ms, none above 1,000 or 2,000 ms. Six phase records are only `menu|main` and `menu|main_video`; no other callback family has a live sample. The last 15-minute aggregate window contained zero callback events, so the latest tap cannot be correlated without an event/time match.
- Coverage: source and `test_callback_dispatch_timing` confirm installation after the last direct callback registration and wrapping of all registered `CallbackQueryHandler`s. The focused suite reran as `Ran 5 tests in 7.780s — OK`. This covers server-side callback dispatch when a callback reaches the bot; it does not measure ReplyKeyboard/message-handler actions, callback delivery before bot receipt, Telegram/client rendering, or device/network time.
- Static screen: 87 callback handler definitions were scanned for awaited work and known synchronous I/O before the first direct `query.answer`. It found source-only candidates where `get_user_language()` opens SQLite before acknowledgement, including Ticket and Document Tools; similar candidates also occur in protected Video/SubDub/Video Edit handlers. Delegated/branch-specific ACK paths make this a screening heuristic, not proof of a slow route. No production database was queried. Do not modify protected engine routes or make a speculative optimization from this result.
- Finding/action: no additional slow server callback was reproduced, so no latency code change is justified by current evidence. Keep A7 PARTIAL. To close the all-button latency question, collect matched samples from other safe callback families and separately test ReplyKeyboard paths; for every measured >1 s route, isolate guard/handler/ACK/render before changing that route. Do not infer a Telegram, network, or device cause from missing events.
- Side effects: aggregate timing/status only; no raw logs, IDs, payloads, user content, provider calls, wallet/database writes, Telegram sends, deploy, or restart.

### S12.35.155 — Public English/Chinese Pricing catalog navigation

- Contract: from public `pricing|main` in `en` and `zh`, follow the actual emitted `pricing|catalog`, verify every emitted catalog callback against the registered Pricing/Menu handler, dispatch only safe read-only catalog detail controls, check each detail Back restores the exact catalog controls, check catalog Back returns to the Pricing hub, and check Home reaches the existing Main handler. Expect one ACK and callback data within Telegram's 64-byte limit.
- Exclusions: do not dispatch `pkgcombo:home`, top-up, storage purchase/status, generated-document sends, payment, package purchase, provider, or any media-processing action. Do not alter pricing copy/values or any product engine.
- Evidence: the source-extracted test follows the actual emitted catalog controls in both English and Chinese through the registered Pricing handler. It dispatches the eight safe read-only detail routes, checks each detail Back returns to `pricing|catalog` with the exact catalog callback list restored, checks catalog Back returns to the hub, and sends Home through the registered Menu handler. Each route ACKs once and emitted callbacks stay within 64 bytes.
- Harness note: the first Menu dispatch fixture lacked `time` and `logger`; adding test-only stubs corrected setup. This was not a product failure and did not change `bot.py` for this spec.
- Verification: the focused test was rerun as `Ran 1 test in 5.302s — OK`. The complete Pricing-origin module had previously run `Ran 15 tests in 86.612s — OK`; final changed-file syntax and diff hygiene are recorded in the consolidated verification gate.
- Limits: navigation and safe pricing-detail rendering only; no generated documents, purchase/top-up/payment, storage action, product-processing, provider, wallet, database write, production Telegram, deploy, merge, or restart. This spec adds regression evidence only; `bot.py` is not changed by S12.35.155.

### A7 post-tap latency recheck — 2026-10-09 approximately 13:51 +07

- Immediately after the Owner reported a tap, a strict-host read-only query of the preceding 15 minutes returned `callback_dispatch_timing_count=0`. `toanaas-bot.service` was `active/running` with `NRestarts=0`.
- The tap had no exact `HH:MM:SS` or named route in that message, and the window contained no callback event; therefore this check cannot correlate the tap or diagnose bot, Telegram, network, or client-render time. No transport-warning query was run in this check.
- Seven-day route evidence remains sparse and menu-only; other callback families have no live latency sample. ReplyKeyboard/message-handler actions are outside the callback observer. A7 remains PARTIAL; no all-button smoothness claim or speculative code change is justified.
- Scope: anonymous event count and service properties only. No raw journal lines, IDs, payloads, provider calls, data writes, deploy, or restart.

### A7 Pricing-family tap sample — 2026-10-09 approximately 13:53 +07

- After the Owner said they had tapped the requested “Bảng giá” entry, the strict-host read-only 15-minute aggregate contained three `callback_dispatch_timing` events: `prefix=pricing`, `handler=handle_pricing_callback`, `route_key=unclassified`; dispatch times were `205.060`, `741.848`, and `186.535 ms` (handler times `165.943`, `663.021`, and `155.148 ms`). The bot service was `active/running`, `NRestarts=0`.
- A refreshed seven-day prefix census now contains 10 `menu` and 3 `pricing` events; sorted dispatch values top out at `741.848 ms`, with no observed event over 1,000 ms. The 15-minute events cannot be individually correlated to the one tap without its exact time because callback payloads are intentionally not logged; the Owner also did not provide end-to-end screen delay. The sample therefore does not prove the Bảng giá button itself was smooth, or explain a 2–3 second report.
- Finding: no server-side >1s callback was observed in the available 13-event sample, so no latency patch is justified. Other callback families and ReplyKeyboard/message handlers still have no live sample; keep A7 PARTIAL and continue one safe family at a time.
- Scope: aggregate allowlisted fields and service properties only. No raw journal lines, IDs, payloads, provider calls, data writes, deploy, or restart.

### A7 Pricing tap follow-up — 2026-10-09 14:06 +07

- The Owner again confirmed the “Bảng giá” tap, without an exact `HH:MM:SS +07` or observed screen-appearance time. A strict-host, read-only query at 14:06:21 returned the same three anonymous `pricing` events at 13:54:17.562, 13:54:22.913, and 13:54:25.042, with dispatch times `205.060`, `741.848`, and `186.535 ms`. There was no later event in that 15-minute window. These records cannot be attributed to this confirmation without the click time; they do not prove end-to-end smoothness or explain a 2–3 second display delay.
- The bot remained `active/running`, `NRestarts=0`. No callback over 1 second was observed in this sparse sample, so no latency patch is justified. No raw logs, identifiers, payloads, provider calls, data writes, deployment, or restart.

### A7 Pricing tap current-window check — 2026-10-09 approximately 14:25 +07

- After the Owner confirmed the “Bảng giá” tap, a strict-host SSH query aggregated only anonymous callback timing fields from the preceding 15 minutes. It returned zero `callback_dispatch_timing` events; the service remained `active/running` with `NRestarts=0`.
- Source check: the public root’s “Bảng giá Xu” control emits inline callback `pricing|main`. The registered Pricing handler ACKs after payload/origin validation and before language lookup, pending cleanup, and screen rendering; no obvious synchronous work in that handler precedes its ACK.
- The confirmation did not include exact `HH:MM:SS +07` or screen-appearance delay, and the query window had no event. This cannot be correlated to that tap and does not show whether Telegram received it or distinguish bot, Telegram, network, or client-render time. No new slow callback was reproduced, so no latency patch is justified. Keep A7 PARTIAL.
- Scope: aggregate count and service properties only; no raw journal lines, identifiers, payloads, provider calls, data writes, deploy, or restart.

### A7 transport warning and local callback-diff screen — 2026-10-09 14:39 +07

- A strict-host, read-only query at 14:39:35 +07 counted common timeout/network/Telegram warning signatures in the preceding 15 minutes. Count: `0`. This is not proof that the earlier tap reached Telegram or that client/network rendering is fast; the click still lacks an exact timestamp and elapsed display time.
- Local `bot.py` diff review for this batch found only: stale AI Chat consent rejection, unsupported-locale Pricing Back rendering, and Internal Archive `view/file` validation/owner-scoped lookup. No AutoPost or Product/Edit/SubDub/Voice/Music engine hunk was present in this diff. The local Archive `view/file` handler performs one synchronous owner-scoped SELECT before ACK to choose the correct stale/missing alert. This is an unmeasured local-source latency candidate, not a live defect; retain the accurate alert behavior and make no speculative optimization.
- No raw warning lines, IDs, payloads, production data, provider calls, wallet mutation, deploy, or restart. Keep A7 PARTIAL.

### S12.35.157 — Image prompt intake Back restores Image hub

- Contract: from the actual customer Image hub keyboard, dispatch emitted `menu|image_prompt_start` through the registered Menu handler, dispatch its actual `imgtool|prompt_need_image` control through the exact registered Image handler, then dispatch the emitted Back through the registered Menu handler. Verify one ACK per step, Image hub restoration, and cleanup of only the actor's image pending state. Do not upload an image or enter image processing.
- Evidence: the source-extracted fixture executes the actual Menu and `^imgtool\|` registration lines. It follows the emitted Send image button, verifies the handler sets `image_prompt_wait_image`, then follows Back=`menu|main_image` and compares the full restored Image hub callback list. Back clears the actor's image pending state while preserving another user's fixture state. Focused case: `Ran 1 test in 1.194s — OK`; full root callback module: `Ran 43 tests in 27.102s — OK`.
- Finding: no route or pending-state mismatch reproduced; no production-code change was indicated. Handler connectivity is source-registration fixture evidence, not a live Telegram interaction or latency measurement.
- Limits: no image upload, Image processing/engine, provider, wallet, production data, real Telegram message, deploy, merge, or restart. The overall A3/A5/A6/A7 checklist remains partial.

### S12.35.158 — A5 classify unproven registration rows by safety boundary

- Contract: classify every registration row currently marked `NOT PROVEN` in `TELEGRAM_CALLBACK_HANDLER_EVIDENCE_20261006.md` by its actual scope. Do not dispatch shared guards, AutoPost, product/media engines, status actions with mixed behavior, or purchase/payment handlers as a blanket test. This is an inventory/scope check, not a claim that the handlers are correct or broken.
- Evidence: a read-only extraction of the current 87-registration evidence matrix found 49 registration rows marked `NOT PROVEN`: 3 shared guards, 41 protected product/media/status registrations, 1 Owner-locked AutoPost registration, and 4 purchase/payment registrations. This count is registration rows, not unique handler functions; repeated registrations include separate patterns. The classification matches the established protected-scope list and S12.35.86's finding that `progress|status` is not uniformly read-only.
- Finding: none of these 49 rows can be safely bulk-dispatched as an unrestricted UI smoke test. A navigation-only branch may still be tested if isolated by its exact emitted control and inert fixture, but terminal processing, provider, product status/delivery, AutoPost, or payment behavior remains excluded. This does not establish whole-handler coverage or close A5.
- Scope/limits: source/evidence inventory only. No callback handler was executed, no product or AutoPost code changed, no provider/wallet/production data action occurred, and no Telegram send/deploy/merge/restart occurred. Continue the remaining A3/A5/A6 safe, action-level gaps; keep A7 partial.

### S12.35.159 — Confirmation “Thêm tệp nữa” preserves staged documents

- Contract: build `doc_tool_confirm_keyboard()` and dispatch its actual emitted “Thêm tệp nữa” control through the single registered `^docflow\\|` handler. Require one ACK, upload-prompt destination, and preservation of `doc_tool_files`, mirrored `doc_files`, file count, options, and another user's pending fixture. Keep the separate after-file “Gửi tệp” reset route unchanged.
- RED: the actual confirmation control emitted `docflow|reset_files`; dispatch cleared staged files, mirror, count and options before returning to “Upload files”. The test failed first at the expected staged-file preservation assertion.
- GREEN: changed only the confirmation keyboard callback to the existing state-preserving `docflow|send_more` action. The after-file Send-file control still emits `docflow|reset_files` and its inert regression confirms intentional reset behavior. All 7 test functions in `tests/test_doc_split_back_emitted_callback.py` were rerun after strengthening the unrelated-user-state assertion with a deep copy; all passed.
- Validation limits: `pytest` is not installed in the bundled Python runtime. `git diff --check` exited 0 (Git printed only the pre-existing LF/CRLF working-copy notice). Full `bot.py` syntax verification (`py_compile` and in-memory `compile`) remained CPU-bound beyond 60 seconds; both task-started checks were stopped, so syntax is still pending and is not claimed as passed.
- Scope/limits: one emitted keyboard callback only; no document was processed, sent, opened, or charged. The handler and reset implementation remain unchanged; no provider, wallet, production data, AutoPost, Product/Edit/SubDub/Voice/Music engine, live Telegram, merge, deploy, or restart was touched. This closes the reproduced navigation/state-loss defect locally, not the overall A3/A5/A6/A7 goal.

### A7 Bảng giá tap correlation recheck — 2026-10-09 approximately 14:50 +07

- After the Owner said “đã nhấn”, strict-host read-only aggregation over the preceding 15 minutes found zero callback events. `toanaas-bot.service` remained `active/running`, `NRestarts=0`.
- The tap had no exact `HH:MM:SS +07` or measured screen delay, and the query contained no event, so it cannot be correlated. This neither proves the click reached Telegram nor distinguishes server, Telegram, network, or client-render time. No slow callback was reproduced; no latency change is justified. Keep A7 PARTIAL.
- Query returned only an aggregate event count and service properties; no raw logs, IDs, payloads, provider calls, writes, deployment, or restart.

### S12.35.160 — Image AI-edit intake Back restores Image hub

- Contract: from the actual `main_image_keyboard()` output, dispatch emitted `imgtool|edit_ai_start` through the actual registered Image-tools handler with no recent/source image available. Verify it only enters `image_edit_wait_image`; then extract Back from the rendered `image_edit_start_keyboard()` and dispatch its emitted `menu|main_image` through registered Menu. Require one ACK each, exact Image-hub callback-list restoration, actor-only pending cleanup, and preservation of another user's pending fixture.
- Evidence: the fixture executes both actual registration lines. The emitted AI-edit action entered `image_edit_wait_image` with `edit_type=ai_edit`, without a source image. Its emitted Back restored the exact Image-hub callback list through Menu and cleared only the actor's state. Adjacent S12.35.157's Image prompt intake/Back regression also passed. Combined rerun: `Ran 2 tests in 2.780s — OK`; full CI-listed root/menu module rerun including the new Image case: `Ran 44 tests in 50.612s — OK`.
- Harness note: the first attempt stopped before route assertions because the test keyboard stub required `main_label` where the real builder omits it. This was corrected only in the new fixture; it was not a product RED. The corrected test and adjacent route both passed.
- Finding/scope: no callback or pending-state mismatch reproduced; no production source edit was justified. No image was uploaded/read/processed, provider/upscale/edit or charge action was invoked, and Product/Edit/Image engines, production data, wallet, AutoPost, live Telegram, merge, deploy, and restart were untouched. UI route evidence only; global checklist remains active.

### S12.35.161 — Document confirmation Back keeps the parent origin

- Contract: for active fixture sessions `split_pdf` (`main_docs`) and `save_document` (`main_memory`), build the actual confirmation keyboard and dispatch its emitted Back through the exact registered `^docflow\\|` handler.
- Evidence: both emitted callbacks exactly matched `docflow|back|main_docs` / `docflow|back|main_memory`. Through the registered handler, each ACKed once, cleared the actor's Document state, preserved another user's pending fixture, and rendered the expected existing Docs or Notes keyboard. Full `tests/test_doc_split_back_emitted_callback.py` fixture module ran all 8 test functions in `10.887 s — OK` after this addition.
- Finding: no route/pending mismatch reproduced; no production source change indicated.
- Scope: inert file IDs/state only. No confirm/run, file read/send, provider, Xu charge, production data, AutoPost, Product/Edit/SubDub/Voice/Music engine, real Telegram, merge, deploy, or restart.

### A7 Bảng giá tap recheck — 2026-10-09 15:32 +07

- The Owner confirmed tapping “Bảng giá”. A strict-host, read-only query at 15:32:57 +07 aggregated only allowlisted callback timing fields for the prior 10 minutes and returned zero events. Runtime HEAD was `62566249d4d54f6047ab33ddffd1bf94c57d0e41`; PR #1409 is an ancestor; `toanaas-bot.service` was active/running with `NRestarts=0`; internal health returned `ok`.
- No matching callback event or screen-appearance time was supplied. This cannot establish whether the tap reached the bot or attribute delay to bot, Telegram, network, or client rendering. A7 remains partial; no latency code change is justified.
- Scope: aggregate event count, current SHA, service state, and health only. No raw logs, identifiers, payloads, provider calls, data writes, deployment, or restart.

### S12.35.162 — Translation text target handoff

- Contract: construct the actual text target picker, choose its emitted English target callback, and dispatch it through the registered `handle_translation_callback`. Require one callback ACK and the exact inert fixture text plus target code to reach a stubbed local translation-runner boundary.
- Safety boundary: do not execute translation, call a provider, process audio/files, send Telegram, read production state, or mutate Xu. Change production code only if a concrete route mismatch reproduces.
- Evidence: the fixture built the actual text target picker, selected its emitted `tr_target|text|en` control, verified the callback matches the registered handler pattern, and dispatched the actual handler. It ACKed once and handed the exact fixture source text plus literal target `en` to a test-only translation-runner boundary. Focused unittest passed; the full root/menu module ran `45 tests in 26.683s — OK`.
- Finding: the UI target callback and handler handoff matched; no route mismatch reproduced and no production code change was indicated.
- Limits: the runner was stubbed. No translation/provider call, Telegram send, production state read, file/audio processing, Xu mutation, AutoPost, protected product engine, merge, deploy, or restart.

### S12.35.163 — AI Chat Trace Back returns to enabled status

- Contract: from the actual enabled AI Chat control keyboard, dispatch its emitted Trace button through the registered `aichat|` handler, then dispatch the emitted “AI Chatbot” Back control. Verify the trace view, return to enabled status/control screen, one ACK per callback, and zero state persistence or change.
- Safety: fixture-only status/trace payload; no AI message, provider call, real account, or action permission change. Build this test before deciding whether a product change is warranted.
- Evidence: the actual enabled control keyboard emitted Trace → `aichat|trace`; the actual trace keyboard emitted Back → `aichat|back_active`. Both traversed the registered handler, ACKed once, and rendered the expected Trace then enabled status/control screen. The state-save seam fails if called; it was not reached. Focused test `0.601s — OK`; full root/menu module `46 tests in 27.023s — OK`.
- Finding/limits: no navigation mismatch reproduced, so no production-code change was justified. No real account, AI action, provider, Telegram delivery, or state persistence was used. This is local callback/UI route evidence only.

### S12.35.164 — AI Chat Status button renders status

- Contract: from the actual enabled AI Chat control keyboard, dispatch the emitted “AI Chatbot status” callback through the registered aichat handler. Require status text, the read-only Trace/Back/Home controls, one ACK, and no state persistence/change.
- Safety: fixture-only enabled state/trace data; no AI message, provider, real account, or permission mutation. This is route verification, not a production-code change unless a mismatch appears.
- Evidence: actual control keyboard emitted “AI Chatbot status” to aichat|status; the registered handler ACKed once and rendered enabled/consented status with emitted Back=aichat|back_active and Home=menu|main. State-save seam was not called. Focused test 0.450s — OK; full root/menu module 47 tests in 33.443s — OK.
- Finding/limits: no status-route mismatch reproduced; production code and account state remained unchanged. No AI/provider, real Telegram, or permission action.

### S12.35.165 — Enabled AI Chat Back returns to Free Tools

- Contract: from the actual enabled AI Chat control keyboard, dispatch its emitted Back-to-Free-Tools control through the registered aichat handler. Require the real Free Tools root keyboard, one ACK, and unchanged enabled fixture state.
- Safety: no AI/provider call, real account, state persistence, or permission mutation.
- Evidence: the actual enabled AI Chat keyboard emitted Back=aichat|back_freehub; the registered handler ACKed once and returned Free Tools root text plus the actual Free Tools keyboard callback set (15 controls, including AI Chat entry and Main). Enabled fixture state stayed unchanged and the save seam was not called. Focused test 0.414s — OK; full root/menu module 48 tests in 28.459s — OK.
- Finding/limits: no parent-route mismatch reproduced. No real account state, provider, AI, or Telegram operation; production behavior unchanged.

### A7 Bảng giá tap recheck — 2026-10-09 approximately 16:20 +07

- The Owner confirmed pressing the requested “Bảng giá” button. A strict-host, read-only query of allowlisted anonymous callback timing fields over the preceding 15 minutes returned zero callback events. Runtime HEAD was `5e11ce7865eaf0e2a792561851967ff45711d9e6`; `toanaas-bot.service` was `active/running` with `NRestarts=0`, and the deployed `bot.py` still contained the callback observer marker.
- The confirmation did not include an exact `HH:MM:SS +07` or screen-appearance duration, and the query contained no event to match. This cannot show whether the tap reached the bot or distinguish bot, Telegram, network, and client-render delay. No latency fix is justified; A7 remains PARTIAL.
- Offline route recheck for the same public Pricing handler: `AccountPricingOriginTests.test_legacy_pricing_screens_keep_their_exact_topup_parent` → `Ran 1 test in 3.658s — OK`; it dispatches `pricing|main` to the registered handler and verifies the exact Back parent in inert fixtures. This does not correlate or time the Owner's live tap.
- A separate strict-host aggregate query at approximately 16:30 +07 counted zero common timeout/network/Telegram rate-limit warning signatures in the preceding 15 minutes. The count does not rule out unlogged transport or client-side problems and is not correlated to the tap.
- Scope: event count, runtime SHA and service state only. No raw logs, identifiers, payloads, provider calls, data writes, deploy, or restart.

### A7 Bảng giá tap recheck — 2026-10-09 16:53:57 +07

- After the Owner confirmed the requested tap, the strict-host query aggregated only allowlisted anonymous callback timing fields and matching common timeout/network/Telegram rate-limit warnings for the preceding 15 minutes: `callback_events=0`, `warning_matches=0`.
- Runtime was `5e11ce7865eaf0e2a792561851967ff45711d9e6`; deployed `bot.py` SHA-256 was `109d7a301e81550977c4adf57b30dd816e2faa0a2d061f80415ed823a7f6f9b1`; observer marker present; `toanaas-bot.service` active/running, `NRestarts=0`.
- No exact `HH:MM:SS +07` or time-to-screen was supplied. The empty window does not prove the tap failed to reach Telegram or locate delay in the bot, Telegram, network, or client. No latency code change is justified; A7 remains PARTIAL.
- Scope was aggregate-only runtime readback. No raw logs, IDs, payloads, provider, Telegram send, data write, deploy, or restart.

### S12.35.48 — Provider balance notice policy fixture recheck — 2026-10-09

- Ran the classification, durable-notice, and runtime seam tests with isolated pytest/httpx dependencies in TEMP and pytest plugin/conftest autoload disabled. Result: `36 passed, 1 deselected in 9.08s`.
- The deselected case compares every changed `bot.py` function to `origin/main`; that includes unrelated in-progress UI changes and is not a focused provider-notice assertion. Selected test sends/readers/stores were fake or temporary SQLite; the HTTP client was replaced with a fake client.
- No provider/network call, real Telegram send, production DB/settings write, wallet mutation, behavior change, or source edit occurred. A6 stays PARTIAL for remaining UI/client checks.

### A7 Bảng giá post-measurement recheck — 2026-10-09 approximately 17:05 +07

- The Owner reports that the Bảng giá screen appeared immediately, under one second.
- A strict-host read-only aggregate after that report still returned `callback_events=0` and `warning_matches=0` for the preceding 15 minutes. Runtime remained `5e11ce7865eaf0e2a792561851967ff45711d9e6`, observer marker present, and `toanaas-bot.service` active/running with `NRestarts=0`.
- This records one fast user-visible interaction, not an all-button guarantee. No server-side event was available to attribute phases; no network/client fault is inferred and no latency fix is indicated. No raw logs, IDs, payloads, provider calls, writes, deploy, or restart.

### A7 Bảng giá tap recheck — 2026-10-09, current continuation

- The Owner reports the latest Bảng giá screen appeared immediately (`<1s`). A strict-host aggregate-only query over the preceding 10 minutes found `pricing_callback_events=0`; it returned no raw log lines or identifiers. The sample cannot be correlated to a server phase and does not establish all-button smoothness or any Telegram/network/client cause. No latency code change is justified by this sample.
- No production source, raw logs, user IDs/payloads, provider, wallet, data, Telegram send, deploy, or restart was touched.

### S12.35.166 — Public main-menu Pricing entry opens the hub and Home returns to main

- Contract: build the actual public main-menu keyboard, select its emitted `pricing|main` control, dispatch through the registered Pricing callback, then dispatch the emitted `menu|main` Home control through the registered Menu callback. Require one ACK for each step, Pricing hub content on entry, and the exact original main-menu callback list on return.
- Evidence: `tests.test_profile_pricing_back_origin` plus `tests.test_profile_topup_back_origin` ran `20 tests in 130.171s — OK`; the new emitted-control case confirms the public button label/callback, Pricing hub rendering, registered Home route, and exact restored main-menu callback list. The Pricing module is already included in `.github/workflows/ci-main.yml`'s safe-navigation unittest step; no CI workflow change was needed for this case.
- Finding/limits: no callback/Back mismatch reproduced, so no production behavior change was indicated. The Owner separately reports the Pricing screen appeared in under one second; this single visible duration is not tied to a server timing event and does not establish smoothness for other buttons. Fixture-only route execution; no payment, top-up action, wallet, provider, production data, Telegram send, deploy, or restart.

### S12.35.167 — Internal Archive emitted Save is single-use and stale replay is rejected

- Contract: build the actual Archive preview keyboard, dispatch its emitted “Lưu hồ sơ” callback through the registered `archive|` handler using fixture-only pending state, and require one save, one ACK, pending cleanup and a success render. Re-dispatch the same emitted callback after cleanup; require one stale alert and no duplicate save.
- Evidence: the source keyboard emitted `archive|save`. `tests.test_internal_archive_save_callback_single_ack` ran `2 tests in 0.940s — OK`; it verifies registration, actual emitted callback, first-save behavior, one ACK and no second save on stale replay. The adjacent Preview module's two inert checks were invoked directly and printed `2 Archive Preview checks — OK`. The existing CI safe-navigation step includes both modules.
- Verification caveat: the combined pytest command collected 4 cases but stalled on its first module with sustained CPU and no per-test output; it was interrupted and is not counted as a pass. The focused Save unittest and direct Preview checks above are the counted evidence.
- Limits: persistence is a local list fake. No production Archive record/database, real Telegram send, provider, wallet, engine, AutoPost, merge, deploy or restart was used. This closes only this Save/replay route locally; the broader A2/A3/A5/A6/A7 and live/client UX review remain partial.

### S12.35.168 — Internal Archive Change department Back restores the same preview

- Contract: build the actual Archive preview keyboard, dispatch its emitted `archive|change_dept` control through the registered Archive handler, then dispatch the picker’s emitted `archive|preview` Back through the same handler. Require one ACK per step, exact preview-control restoration and preservation of the fixture file, department and document type; do not save or send the file.
- Evidence: both emitted callbacks matched the registered Archive handler and ACKed once. The first rendered the actual department picker; Back restored the exact original preview callback list and retained `step=preview`, department=`customers`, type=`customer_profile` and fixture file metadata. `tests.test_internal_archive_search_back_origin` ran `8 tests in 19.192s — OK`; this module is in the existing CI safe-navigation step.
- Limits: fixture-only state and render capture; no file save/send, production Archive/DB data, real Telegram, provider, wallet, engine, AutoPost, merge, deploy or restart. The broader A2/A3/A5/A6/A7 and live/client UX review remain partial.

### S12.35.169 — Internal Archive emitted Edit enters the correct metadata pending state

- Contract: build the actual Archive preview keyboard, dispatch its emitted `archive|edit` control through the registered handler, and verify one ACK, the metadata prompt, `awaiting_metadata`, and preservation of the fixture file, department, type and title. Do not submit text or save/send the file.
- Evidence: the emitted Edit callback matched the registered Archive handler, rendered the expected metadata template and ACKed exactly once. Pending became `awaiting_metadata` while retaining the fixture metadata. `tests.test_internal_archive_search_back_origin` ran `9 tests in 18.318s — OK`; the module is included in CI.
- Limits: fixture-only state and render capture. No metadata text submission, save/send, production Archive/DB data, Telegram, provider, wallet, engine, AutoPost, merge, deploy or restart. The broader A2/A3/A5/A6/A7 and live/client UX review remain partial.

### S12.35.170 — Internal Archive emitted “Hồ sơ hiện tại” drops only the actor's draft

- Contract: build the actual Archive preview keyboard, dispatch its emitted `archive|discard_to_dept` control through the registered Archive handler, and require one ACK, return to the same department dashboard, removal of only the actor's unsaved file draft, and preservation of another user's pending state.
- Evidence: the actual “📁 Hồ sơ hiện tại” control emitted the expected callback, which ACKed once, returned to `DEPARTMENT DASHBOARD: customers`, transitioned the actor to `department_dashboard` without draft file/title, and left another user's full pending-state snapshot unchanged. First run failed only because the fixture expected bare fields and omitted `pending_action`/`step`/`created_at_ts`; the fixture was corrected, not product code. The complete registered Archive module then ran `10 tests in 63.040s — OK`; it is in CI.
- Limits: fixture-only state/render capture. No real file delete/save/send, production Archive/database, Telegram, provider, wallet, engine, AutoPost, merge, deploy or restart. The broader A2/A3/A5/A6/A7 and live/client UX review remain partial.

### S12.35.171 — Internal Archive “Hướng dẫn lưu” Back returns to its department

- Contract: build the actual Archive root and department keyboards, dispatch its emitted department control through the registered Archive handler, take the department dashboard's emitted “Hướng dẫn lưu” button through that same handler, then dispatch the help screen's emitted Back. Require one ACK per tap, actual help text, exact restoration of the same department keyboard and `department_dashboard` state. Do not perform file, record, database, or document actions.
- Evidence: focused registered-handler unittest passed (`1 test in 1.964s — OK`). It used the actual root/department/help keyboard builders, actual `archive|` registration and `internal_archive_help_text`; Back returned to the customers dashboard and the original emitted callback list. Archive lookup/recent/send fakes remained unused. The module is already included in CI's safe-navigation step.
- Finding/limits: no route mismatch or production fix was indicated. Fixture-only navigation/rendering; no production Archive/DB access, file save/send, provider, wallet, real Telegram, engine, AutoPost, merge, deploy or restart. Broader A3/A5/A6/A7 and live/client latency remain partial.

### S12.35.172 — Internal Archive type-picker Back returns to the same department

- Contract: start from the actual Archive root keyboard, dispatch its emitted customer-department callback through the registered Archive handler, then follow the department keyboard's emitted type-picker button and dispatch the type keyboard's emitted Back. Require one ACK at each step, the actual type prompt, and exact restoration of the same department keyboard and `department_dashboard` state. Do not select a document type or perform file/record/database actions.
- Evidence: focused registered-handler unittest passed (`1 test in 2.535s — OK`). The test traversed root → customers → emitted `archive|types` → emitted `archive|back_department`, checked the actual type prompt and `archive|type|customer_profile` option, restored the exact department callback list, and retained `department=customers`. Archive lookup/recent/send fakes remained unused; the module is in CI's safe-navigation step.
- Finding/limits: no navigation mismatch or production change was indicated. Fixture-only route/render/state evidence; no document type was selected and no production Archive/DB/file action, Telegram send, provider, wallet, engine, AutoPost, merge, deploy or restart occurred. Broader A3/A5/A6/A7 and live/client latency remain partial.

### S12.35.173 — Internal Archive type selection Back returns to the type picker

- Contract: from the actual department dashboard, dispatch its emitted type-picker control and then one emitted document-type option through the registered Archive handler. Require the expected upload prompt, `awaiting_file` state with matching department/type, and then dispatch the prompt's emitted Back. Require restoration of the same type-picker callback list and `choosing_type` state while preserving the selected draft type. Do not send or save a file.
- Evidence: focused registered-handler unittest passed (`1 test in 1.882s — OK`). It dispatched the actual emitted `archive|type|customer_profile`, rendered the upload prompt, retained `awaiting_file` with the matching department/type, then dispatched the emitted `archive|types` Back and restored the exact type-picker callback list with `choosing_type` and the draft type preserved.
- Finding/limits: no route mismatch or production fix was indicated. Fixture-only state/rendering; no file upload/save, production Archive/DB record, Telegram, provider, wallet, engine, AutoPost, merge, deploy or restart. Broader A3/A5/A6/A7 and live/client latency remain partial.

### S12.35.174 — Internal Archive quick-save entry Back returns to its department

- Contract: build the actual Archive root and department keyboards, dispatch the emitted customer department and “Lưu file vào nhóm này” controls through the registered Archive handler, then dispatch the quick-save prompt's emitted Back. Require one ACK per tap, the actual quick-save prompt, exact restoration of the same department keyboard and `department_dashboard` state. Do not send a file.
- Evidence: focused registered-handler unittest passed (`1 test in 3.024s — OK`). It dispatched the actual emitted quick-save button, rendered the actual quick-save prompt with its Back controls, and confirmed that Back restored the exact customers department callback list and `department_dashboard` state.
- Finding/limits: no navigation mismatch or production change was indicated. Fixture-only pending-state/rendering; no file upload/save, production Archive/DB record, Telegram send, provider, wallet, engine, AutoPost, merge, deploy or restart. Broader A3/A5/A6/A7 and live/client latency remain partial.

### S12.35.175 — Internal Archive department Search Back returns to its department

- Contract: build the actual Archive root and department keyboards, dispatch the emitted customer department and “Tìm trong nhóm” controls through the registered Archive handler, then dispatch the search prompt's emitted Back. Require one ACK per tap, the actual search prompt, and restoration of the exact same department keyboard and `department_dashboard` state. Do not enter a search term or run a document query.
- Evidence: focused registered-handler unittest passed (`1 test in 2.336s — OK`). It dispatched the emitted department and “Tìm trong nhóm” controls, verified the department-specific search prompt and emitted `archive|back_department|customers`, then restored the exact customers department keyboard and `department_dashboard` state. The complete registered Archive module then ran `15 tests in 102.177s — OK`, covering .172–.175 together with existing Archive route regressions.
- Finding/limits: no navigation mismatch or production change was indicated. Fixture-only state/rendering; no term was entered and no production Archive/database query, Telegram, provider, wallet, engine, AutoPost, merge, deploy or restart occurred. Broader A3/A5/A6/A7 and live/client latency remain partial.

### S12.35.176 — Internal Archive department Back returns to Archive root

- Contract: build the actual Archive root and department keyboards, dispatch the emitted customer-department control, then dispatch the department keyboard's emitted “Hồ sơ nội bộ” Back through the registered Archive handler. Require one ACK per tap, the exact Archive-root callback list/text, and clearing of only the fixture user's department pending state. Do not perform file/record/database actions.
- Evidence: focused registered-handler unittest passed (`1 test in 21.640s — OK`). The emitted Back restored the exact root callback list/text and cleared only the fixture user's pending state. The first failure was only a fixture expected-value mismatch (`None` is the actual cleared-state representation, not `{}`); the assertion was corrected with no product-code change. The latest full Archive route module then passed `16 tests in 45.381s — OK`, including S12.35.172–.177.
- Finding/limits: no route mismatch or production fix was indicated. Fixture-only navigation/pending state; no production Archive/DB/file, Telegram, provider, wallet, engine, AutoPost, merge, deploy or restart. Broader A3/A5/A6/A7 and live/client latency remain partial.

### S12.35.177 — Internal Archive root Search is dispatched from its emitted button

- Contract: build the actual Archive root keyboard, select its visible “Tìm hồ sơ” control, and dispatch that emitted callback through the registered Archive handler. Then dispatch the prompt's emitted Back. Require the actual prompt, one ACK per tap, exact restoration of the root callback list, and clearing of only fixture pending search state. Do not enter a term or run a query.
- Evidence: `tests.test_internal_archive_search_back_origin.InternalArchiveSearchBackOriginTests.test_root_search_prompt_back_returns_to_archive_root` passed (`1 test in 2.197s — OK`) after the test was tightened to select the visible “🔍 Tìm hồ sơ” button from the actual root keyboard rather than hard-code `archive|search`. The emitted callback reached the registered Archive handler, and the prompt's emitted `archive|root` Back restored the exact root controls. The complete Archive route module then passed `16 tests in 45.381s — OK`, including S12.35.172–.177.
- Finding/limits: this closed a test-coverage gap; no product mismatch reproduced and no production-source change was needed. Fixture-only; no search term, DB query, Telegram, provider, wallet, engine, AutoPost, merge, deploy or restart. Broader A3/A5/A6/A7 and live/client latency remain partial.

### S12.35.178 — Expired Internal Archive Quick Save button returns safely to root

- Contract: build the actual Archive root and department keyboards, dispatch the emitted department control, retain the dashboard's emitted “Lưu file vào nhóm này” callback, advance fixture time past the Archive TTL, and dispatch that stale callback through the registered handler. Require one ACK, exact Archive-root restoration, cleanup of only the expired actor, and preservation of another user's fresh pending state. No upload, lookup, DB action, or send.
- Evidence: `test_expired_emitted_quick_save_button_returns_to_root_without_pending` passed (`Ran 1 test in 0.026s — OK`). The complete registered Archive module passed 17 tests in 0.516s — OK. Both used the exact emitted controls and registered `^archive\\|` handler. An initial assertion failed because the fixture expired both users; the fixture was corrected to create the second user's pending state after advancing its clock. No product failure was reproduced.
- Test-environment note: the default Windows Proactor loop blocked in `_fallback_socketpair` while `asyncio.run` created its self-pipe, before the handler ran. Local fixture verification therefore used an in-memory source index and an immediate coroutine driver that rejects any yielded I/O; CI runs on `ubuntu-latest` and retains the normal test code. This is not a product-code workaround.
- Limits: fixture-only pending-state/rendering; no file upload/save, Archive/document DB lookup, Telegram, provider, wallet, engine, AutoPost, merge, deploy, or restart. Broader A3/A5/A6/A7 and live/client latency remain partial.

### S12.35.179 — Expired Internal Archive “Hồ sơ gần đây” button does not query

- Contract: from the actual Archive root, dispatch the emitted customer department, capture the department keyboard's emitted “Hồ sơ gần đây” control, expire the actor's pending state, then dispatch that stale callback through the registered handler. Require one ACK, exact Archive-root controls, zero recent/document lookup calls, only the actor's expired pending state cleared, and preservation of another user's fresh pending state.
- Evidence: `test_expired_emitted_recent_button_returns_to_root_without_query` passed (`1 test in 0.028s — OK`). The complete Archive route module passed 18 tests in 0.541s — OK. The stale emitted callback returned to the exact root keyboard without calling the fixture recent-query, document-lookup, or send boundaries. No product mismatch reproduced.
- Test environment: same Windows Proactor `asyncio.run` socketpair issue as S12.35.178; verified with the same in-memory source index and immediate fake-coroutine driver, which rejects yielded I/O. CI runs on `ubuntu-latest` with the normal test code.
- Limits: fixture-only navigation/state/query seams; no production Archive/document read, file action, Telegram, provider, wallet, engine, AutoPost, merge, deploy, or restart. Broader A3/A5/A6/A7 remain partial.

### S12.35.180 — Expired Internal Archive type-picker button returns to root

- Contract: from the actual Archive root, dispatch the emitted customer department, capture its emitted “Chọn loại hồ sơ” button, expire the actor's pending state, and dispatch that stale callback through the registered handler. Require one ACK, exact root restoration, no `choosing_type` or `awaiting_file` state, only actor expiry, and preservation of another user's fresh pending state.
- Evidence: `test_expired_emitted_types_button_returns_to_root_without_upload_state` passed (`1 test in 0.067s — OK`). The complete Archive route module passed 19 tests in 2.790s — OK. The stale emitted type-picker callback returned the exact root controls without lookup, recent query, or send; another user's fresh pending state remained unchanged. No product mismatch reproduced.
- Test environment: same Windows Proactor `asyncio.run` socketpair limitation as `.178–.179`; verified with the in-memory source index and immediate fake-coroutine driver, which rejects yielded I/O. CI runs on `ubuntu-latest` with the normal test code.
- Limits: fixture-only state/rendering; no file upload/save, DB, Telegram, provider, wallet, engine, AutoPost, merge, deploy, or restart. Broader A3/A5/A6/A7 remain partial.

### S12.35.181 — Expired Internal Archive department Search does not open a prompt

- Contract: from the actual Archive root, dispatch the emitted customer department, capture the department keyboard's emitted “Tìm trong nhóm” control, expire the actor's pending state, and dispatch that stale callback through the registered handler. Require one ACK, exact root controls, no `awaiting_search_department` state or search query, actor-only expiry, and preservation of another user's fresh pending state.
- Evidence: `test_expired_emitted_department_search_returns_to_root_without_prompt` passed (`1 test in 0.040s — OK`). The full Archive route module passed 20 tests in 0.806s — OK. The stale emitted callback returned to the exact root without opening the search prompt or calling the fixture recent/document lookup or send boundaries; another user's fresh pending state was preserved. No product mismatch reproduced.
- Test environment: same Windows Proactor `asyncio.run` socketpair limitation as `.178–.180`; verified with the in-memory source index and immediate fake-coroutine driver, which rejects yielded I/O. CI runs on `ubuntu-latest` with the normal test code.
- Limits: fixture-only navigation/state; no search term/query, production document/DB access, Telegram, provider, wallet, engine, AutoPost, merge, deploy, or restart. Broader A3/A5/A6/A7 remain partial.

### S12.35.182 — Public Audio Studio landing Back/Home returns to Main

- Contract: build the actual public main-menu keyboard, dispatch its emitted `music_quick|showroom|root` Audio Studio control through the registered `handle_music_quick_callback`, then dispatch both emitted Main-menu controls through the registered `handle_menu_callback`. Require one ACK per callback, the Audio Studio landing screen, and the original main-menu callback list on return. Do not enter Voice or Music child flows.
- Evidence: `test_public_audio_studio_landing_back_and_home_return_to_main_via_registered_handlers` passed in the corrected combined focused rerun (`Ran 2 tests in 2.790s — OK`) using a synchronous coroutine driver that rejects yielded I/O. It selected the actual root control, verified the Studio Audio screen and emitted Back/Home values, dispatched both through the registered Menu route, and restored the original main-menu controls. The earlier ordinary Windows Proactor invocation stalled before handler execution in `_fallback_socketpair`; it is not counted as a pass.
- Finding/limits: no route mismatch reproduced; no production source changed. Navigation-only fixture evidence; no Voice/Music child flow, generation, provider, production data, wallet, Telegram send, AutoPost, merge, deploy, or restart. A3/A5/A6/A7 and live/client visual and latency checks remain partial.

### S12.35.183 — Public Music Hub Back returns to Audio Studio

- Contract: from the actual Audio Studio keyboard, dispatch its emitted Music Hub control through the registered `handle_music_quick_callback`; then dispatch the Music Hub's emitted Back through the same registered handler and Home through `handle_menu_callback`. Require one ACK per callback, the Music Hub screen, exact restoration of the Audio Studio controls on Back, and Main on Home. No music/voice action is selected.
- Evidence: `test_public_music_hub_back_restores_audio_studio_and_home_returns_main_via_registered_handlers` passed in the corrected combined focused rerun (`Ran 2 tests in 2.790s — OK`) using a synchronous coroutine driver that rejects yielded I/O. The actual emitted Music Hub entry reached the registered callback; its emitted Back restored the exact Audio Studio controls and Home reached the registered Menu handler, restoring the public Main menu.
- Finding/limits: no route mismatch reproduced, so no production change was needed. Navigation-only fixture; no Music/Voice action, generation, provider, production data, wallet, Telegram send, AutoPost, merge, deploy, or restart. Live client visuals/latency and broader A3/A5/A6/A7 remain partial.

### S12.35.184 — Public Pricing → Voice → Catalog Back → Pricing → Main

- Contract: use the public Pricing hub's actual emitted Catalog and Voice pricing controls, then follow the emitted Voice Back, Catalog Back, and Main Home through the registered Pricing/Menu handlers. Require one ACK per callback and exact restoration of each immediate parent. Keep the fixture at read-only pricing text; do not enter Voice Studio, generation, provider, payment, or top-up.
- Evidence: `test_public_voice_pricing_back_restores_catalog_then_pricing_hub` passed in `2.582s` with a corrected synchronous coroutine driver that raises on any yielded I/O. A mutation check changed the emitted Voice Back to `pricing|main`; the test failed at the expected `pricing|catalog` assertion, confirming it catches the wrong-parent defect. The full Account Pricing module then ran 17 tests in 89.763s — OK. Six emitted callbacks matched registered handlers and ACKed exactly once; Voice rendered inert fixture text, Back restored the exact Catalog callback list, Catalog Back returned to the Pricing hub, and Home restored Main.
- Finding/limits: no route mismatch reproduced and no production change was indicated. Fixture-only navigation evidence; no Voice/product action, provider, wallet, payment, production data, real Telegram send, AutoPost, merge, deploy, or restart. Client visual/latency and broader A3/A5/A6/A7 remain partial.

### S12.35.185 — Public Pricing Guide Back returns to Pricing

- Contract: follow the Catalog's emitted Guide control through the registered Pricing callback, then verify its emitted Back returns to Pricing and its Home returns to Main. Do not dispatch the generated-document buttons.
- Evidence: focused registered-handler test `test_public_pricing_guide_back_returns_to_pricing_hub` passed in `2.891s`; full Account Pricing regression passed `18 tests in 121.573s — OK`. Both used an inline coroutine driver that fails if a fixture yields I/O. The initial attempt found an omitted `effective_public_base_url` fixture dependency (setup only); the corrected empty-URL seam passed. A mutated Back callback to `menu|main_guide` failed at the expected `pricing|main` assertion.
- Finding/limits: current Guide Back/Home routes are correct; no production mismatch or code change was indicated. Fixture-only. No document generation/send, payment, wallet, provider, production data, real Telegram send, AutoPost, product engine, merge, deploy, or restart. Client visual and live latency remain unverified.

### S12.35.186 — Public Catalog Member Back returns to Catalog

- Contract: dispatch the actual public Vietnamese Catalog's Member button through the registered Pricing handler; require Member Back → exact Catalog, birthday-instruction Back → Member → Catalog, and one ACK per step. Preserve Account-origin Member Back and the unscoped legacy `pricing|member` destination; reject `catalog` origin on unrelated `main`/`video` routes before cleanup/render.
- RED: the emitted Member control opened the Member screen, but its actual Back was `pricing|main`; the immediate Catalog parent should be `pricing|catalog`. One behavioral assertion failed with no fixture error.
- Fix: the Vietnamese Catalog's Member control now carries explicit `catalog` origin. The Pricing handler allows that origin only for `member`/`birthday`, and a focused menu-wrapper branch maps it to `profile_catalog` when the Catalog came from Account. Legacy unscoped callbacks remain unchanged. No price, Xu, wallet, or product behavior changed.
- GREEN: public Member/birthday/Back, Account Catalog Member ancestry, and invalid-origin controls: `3 tests in 7.628s — OK`. Full `test_profile_pricing_back_origin.py`: `19 tests in 107.535s — OK`. Test file `py_compile` exited `0`; `git diff --check` exited `0` with an LF→CRLF warning. The required full `python -m py_compile bot.py` attempt produced no output after >2 minutes and was interrupted; full-source compile remains NOT_VERIFIED for the consolidated CI gate.
- Limits: local fixture navigation only. No payment, birthday update command, provider, production data, Telegram send, AutoPost, product engine, merge, deploy, or restart. Broader A3/A5/A6/A7 remain partial.

### S12.35.188 — Package Home Back preserves Account and Total-price origin

- Contract: dispatch the emitted Package/Combo entry from Account Pricing and from public Catalog → Total price through registered Pricing/Package callbacks; Package Home Back must restore the exact immediate screen, and Total Back must still return through Catalog. No package detail, purchase, payment, wallet or provider action.
- RED: both focused tests found the actual emitted entry was unscoped `pkgcombo:home` instead of the expected origin-bearing value; the failures were route assertions, not fixture errors.
- Fix: the Pricing wrapper now adds narrow, allowlisted origins for Account Pricing main and Catalog/Account Total pages. The Package handler resolves each token to its exact Pricing parent. Legacy unscoped package callbacks remain unchanged. Existing Pricing tests had stale expected callback strings for the Account hub and international Catalog; only those expected values were aligned with the origin-aware behavior.
- GREEN: package callback suite passed `14 tests in 39.241s — OK`, including Account → Catalog → Total → Packages → Total → Catalog → Account. After aligning the two stale expected callback values, the full Pricing module passed `28 tests in 118.453s — OK`; on Windows the final run used a fixture-only immediate coroutine driver that fails if any I/O is yielded. The earlier 15 assertions were confined to the now-updated expectations.
- Current recheck: an attempted fresh `unittest` rerun of `tests.test_pkgcombo_navigation_registered_callback` did not print a test result before 120 seconds, and was interrupted before a test completed. Preserve the earlier recorded 14/14 result; current recheck is NOT_VERIFIED, not a regression or product failure.
- Limits: fixture-only UI navigation. No package detail/purchase, payment, wallet, provider, production data, Telegram send, AutoPost, product engine, merge, deploy or restart. Whole-bot compile/CI, other route families, and live all-button latency are still open.

### S12.35.189 — Ticket category prompt Back restores the same category list

- Rechecked the customer Ticket category menu → emitted `ticket|cat|image_error` → pending message prompt → emitted `ticket|start` Back through the Ticket route pattern.
- Focused test `test_customer_ticket_category_prompt_back_restores_category_menu` passed (`1 test in 0.492s — OK`): one ACK per callback, expected fixture pending state, only the actor's pending state cleared on Back, and the exact category callback list restored. The first invocation used an incorrect unittest class name (test discovery error); the corrected invocation passed.
- No ticket was sent and no production record, provider, wallet, product engine, AutoPost, merge, deploy, or restart was touched. This does not verify ticket delivery/retries or live client latency.

### A7 — Timing-observer coverage recheck

- The current source installs a wrapper around every registered `CallbackQueryHandler`; it records bounded route prefix, guard phases, handler time and the shared render-helper time, without callback payload or user ID. Focused suite `tests.test_callback_dispatch_timing` passed `5 tests in 8.245s — OK`.
- These measurements stop at bot callback/render-helper boundaries; they do not include Telegram transport after the API call, client rendering or ReplyKeyboard/message handlers. The latest Bảng giá tap is reported `<1s`, but the adjacent aggregate window had no matching callback event, so it cannot be attributed to server timing. Account → Back remains owner-reported 2–3s without a correlated event; no network/device/server root cause or all-button smoothness claim is justified.

### S12.35.190 — Exact Home/Back route gets an anonymous timing label

- RED: the existing callback timing fixture dispatched exact `menu|main`, but its fixed route key was `unclassified`, preventing an aggregate from separating Home/Back from other `menu` callbacks.
- Fix: the observer assigns constant `route_key=main_home` only to the exact `menu|main` value. Exact `menu|main_profile` remains `account_root`; callback values with extra/dynamic suffix remain `unclassified`. No payload or user ID is logged, and the menu handler/keyboard are unchanged.
- GREEN: `tests.test_callback_dispatch_timing` passed `5 tests in 6.990s — OK`. The module is included in the current safe-navigation CI workflow.
- The current Account UI route regression also passed: actual Account keyboard → its emitted `menu|main` Home/Back → Main screen (`1 test in 0.722s — OK`, one ACK, correct destination). This is offline navigation evidence only, not a latency measurement.
- Limits: diagnostic-only, not a speed fix. It measures bot guard/handler/render-helper timing, not Telegram/client rendering. A fresh correlated Account → Back tap after the batch is live is still required; until then the reported 2–3s has no proven cause.

### S12.35.191 — Package detail Back preserves Account and Total-price origins

- Contract: start from the actual Account Pricing hub, Account Total, and public Catalog Total controls; follow emitted Package/Combo → Image group → package detail → Back → group → package home → exact originating Pricing screen through the registered handlers. Do not select any purchase/checkout control.
- RED: all three emitted detail pages lost the scoped origin on Back, returning `pkgcombo:group:image` instead of `pkgcombo:group:image:<origin>`. The package home and group controls carried the expected tokens; the loss occurred in `render_pkgcombo_detail`'s origin allowlist.
- Fix: add the three already-allowlisted navigation origins (`pricing_main_profile`, `pricing_total_profile`, `pricing_total_catalog`) to the detail Back preservation branch. Purchase markup, prices, checkout and engine behavior are unchanged.
- GREEN: the focused emitted-route test passed (`1 test in 6.304s — OK`) across all three origin scenarios. The complete package navigation module passed `15 tests in 52.225s — OK`, with the Windows immediate coroutine driver rejecting any yielded I/O. Existing Pricing regression passed 28 tests in 118.453s before this narrow package-detail change; consolidated CI remains the final combined gate.
- Limits: fixture-only navigation/detail rendering. No purchase, payment, wallet, provider, customer data, engine, AutoPost, Telegram send, merge, deploy, or restart. A3/A5/A6 and A7 remain partial.

### S12.35.192 — Document split emitted Back and staged-state recheck

- Contract: follow the actual emitted split-PDF “Ask pages” action into its input prompt, then dispatch the prompt’s emitted Back through the registered `^docflow\\|` handler. Recheck confirmation Add-more, parent Back, stale/expired state, actor-only cleanup, and preservation of another user’s staged state. Do not process, upload, save, or send a file.
- Result: no callback destination or staged-state mismatch reproduced in this recheck.
- Evidence: all 8 fixture test functions in `tests/test_doc_split_back_emitted_callback.py` were directly invoked with an immediate coroutine driver that aborts if a callback yields I/O; `8 Document emitted-route checks — OK` (10.1s). The current CI workflow includes this file in its `pytest --noconftest` navigation step. The bundled local Python lacks `pytest`, so this run is not reported as a pytest/CI pass.
- Limits: fixture-only route/state evidence. No PDF processing, upload/save, production data, provider, wallet, AutoPost, product engine, Telegram send, merge, deploy, or restart. A3/A4/A5 and whole-bot closeout remain partial.

### S12.35.193 — SubDub/Voice child Back navigation recheck

- Contract: inspect the emitted child controls and exercise their Back destinations through the registered SubDub callback, preserving the expected immediate parent, product origin, source file and unrelated fixture state. Use inert fixtures only; do not select a voice or enter media processing.
- Evidence: `tests.test_subdub_voice_child_back.SubDubVoiceChildBackTests` passed all 5 tests in 4.353s — OK with an immediate coroutine driver that fails if any callback yields I/O. This covers Audio Mix layer Back, expired-child recovery, Voice parent Back for both modes/visibility states, saved-voice pagination Back, and main Voice Back to Language.
- Result/limits: no route mismatch reproduced and no source change was indicated. This is navigation-only fixture evidence, not a SubDub/Voice engine test. No voice selection, job, media processing, provider, production data, wallet, real Telegram action, merge, deploy, or restart. A3/A5/A6 and whole-goal closeout remain partial.

### S12.35.194 — Voice TTS settings prompt Back recheck

- Contract: check the speed/volume input prompt Back across default/saved/standalone voice sources and showroom/video-addon contexts; preserve selected voice settings/context, release only the matching input-pending state, and leave unrelated pending state untouched. Generation/price-summary/provider calls are forbidden.
- Evidence: 19 test cases passed with the immediate no-I/O coroutine driver: 12 prompt-back combinations, 6 parent-back combinations, and one stale-Back/unrelated-pending case. Because the bundled local Python lacks pytest, the test module's parameter decorators were expanded by a one-shot in-memory shim; this is not a pytest/CI pass.
- Result/limits: no Back/state mismatch reproduced. Fixture-only UI state; no voice was generated, no provider/price action ran, and no production source change was indicated. Stable Voice/Music engines remain untested and untouched; A3/A5/A6 and closeout remain partial.

### S12.35.195 — Admin Broadcast Lite Back and read-only navigation recheck

- Contract: dispatch actual emitted History/Schedule/Limits controls and Back through the registered Broadcast Lite handler. Back/Menu must release only the fixture pending owner and retain the draft. No broadcast send or AutoPost action.
- Evidence: `tests.test_broadcast_lite_back_pending_cleanup.BroadcastLiteBackPendingCleanupTests` passed 4 tests in 0.801s — OK. It covers callback registration, Back/Menu draft preservation, the three read-only pages, and nested Limits Back to Schedule. The first run failed before product assertions because the sandbox's AppData temporary path denied SQLite access and cleanup; the rerun used a verified worktree-local temp directory and cleaned that exact directory afterward.
- Result/limits: no route/state mismatch reproduced. Temporary SQLite fixture only; no real broadcast, production data, provider, wallet, AutoPost, engine, merge, deploy, or restart. This closes only the tested Admin navigation slice; whole-bot audit remains active.

### A7 Bảng giá live recheck — 2026-10-10 02:01 +07

- The Owner reports Bảng giá appeared immediately (`<1s`). A strict-host, read-only 15-minute query returned no `callback_dispatch_timing` events. The query emitted no raw journal lines or identifiers, so there is still no server phase to correlate with the user-visible tap.
- Result: this route is fast in the one manual observation; no latency fix is indicated. It does not establish all-button smoothness or identify Telegram/network/client cause. Account → Back remains reported at 2–3s without a correlated sample; A7 stays partial.
- No production source, raw logs, user IDs/payloads, provider, wallet, data, Telegram send, deploy, or restart was touched.

### S12.35.196 — Feedback transient-failure retry and duplicate protection

- Contract: inject a one-time classifier failure for Feedback pending text, then retry the same message ID. Require the pending state and dedupe eligibility to survive the first exception; the retry must create one fixture ticket, clear only Feedback pending, and produce one reply/notification.
- Evidence: the focused assertion function printed `direct assertion: OK` using an immediate coroutine driver that rejects any yielded I/O. The first attempt failed as injected without clearing pending or marking the message done; retrying the same update completed once. Changed test `py_compile` exited `0`; `git diff --check` exited `0`. `pytest` is unavailable in the bundled Python (`No module named pytest`), so this is not a pytest/CI pass.
- Scope note at the time of S196: the test source-checked that decorated `handle_message` dispatches Feedback pending, but only executed the extracted pending handler. S12.35.205 below closes that specific full-dispatcher evidence gap using the registered message handler; no real Telegram message, production data, DB, provider, wallet, AutoPost, engine, merge, deploy or restart.

### S12.35.197 — All emitted Feedback category controls reach the correct prompt

- Contract: build the actual Feedback category keyboard and dispatch all eight emitted `feedback|cat|...` controls through the registered route pattern and extracted handler. Verify one ACK, exact category pending state, matching prompt, Back to `feedback|start` and Home to `menu|main`.
- Evidence: all eight fixture routes passed using the actual keyboard builder and handler source. The test also rejected an in-memory mutation of the emitted `image_error` callback. Test `py_compile` exited `0`; `git diff --check` exited `0` with only an existing LF→CRLF warning on another changed test file. The module is already included in the safe-navigation CI workflow; local `pytest` is unavailable (`No module named pytest`), so this is direct assertion evidence, not pytest/CI.
- Limits: local fixture state/render capture; registration-pattern match plus extracted handler, not live PTB dispatcher. No real Feedback submission, production DB/data, provider, wallet, AutoPost, protected engine, Telegram send, merge, deploy or restart. User-visible latency remains unmeasured by this offline test.

### S12.35.198 — Video entry latency recheck; no duplicate instrumentation

- Existing audit-state evidence already isolates `menu|main_video`: at 11:49:01 +07 on 2026-10-09, handler `291.160 ms`, pre-ACK `0.040 ms`, ACK `180.930 ms`, language `6.827 ms`, cleanup `9.908 ms`, build `2.003 ms`, render `91.453 ms`; matching dispatch was `373.478 ms`. The seven-day anonymous dispatch census had 10 events, maximum `529.393 ms` and none above `1,000 ms`.
- Finding: no server-side >1s Video callback was reproduced. The separate `callback_dispatch_timing` label would duplicate the existing route-specific phase record, so the temporary local test/source experiment was removed; no production change remains for this spec.
- Limits: these are sparse server-side samples, not a correlated fresh tap or end-to-end Telegram/client/network timing. They do not prove all buttons are smooth. The Owner's later report that Bảng giá appeared in `<1s` is one separate manual sample without a server event correlation. A7 remains partial; no code/deploy/restart was performed.

### A7 — Seven-day callback dispatch distribution — 2026-10-10 03:10 +07

- Strict-host, read-only aggregate returned only anonymous counts/timings (no raw journal lines): 14 callback dispatches in seven days. `menu`: 11, average 350.520 ms, maximum 529.393 ms. `pricing`: 3, average 377.814 ms, maximum 741.848 ms. Zero observed dispatches exceeded 1 second; no other route prefix appeared in this sample.
- VPS bot runtime SHA was `381d335961bea01db60cda99f0dfe98e2b2d1760`; `toanaas-bot.service` was active with `NRestarts=0`.
- This is server callback dispatch only, not an individual click correlation. It excludes ReplyKeyboard/message handlers and Telegram transport/client rendering. It does not prove all buttons are smooth or explain the reported Account → Back 2–3s.

### S12.35.199 — Public Pricing document-download callback dispatch

- Source review: actual Catalog buttons emit `pricing|download_pricing` and `pricing|download_guide`; the registered Pricing handler has matching read-only branches that produce localized markdown and call `send_generated_markdown_document`. The helper builds an in-memory `BytesIO` and calls the Telegram `reply_document` boundary. No source-level route/argument mismatch was found; no product-source change was indicated.
- The focused test in the existing `tests/test_profile_pricing_back_origin.py` CI step dispatches actual Catalog/Guide controls through the registered Pricing handler and real in-memory document helper. A fake `reply_document` sink asserted one ACK plus exact filename, caption and generated bytes; `Ran 1 test in 3.119s — OK`.
- Root cause of the first local hang was the test using legacy `fixture._dispatch`/`asyncio.run`, which blocked in Windows Proactor `_fallback_socketpair`. Replacing those calls in this new test with the immediate no-I/O driver and using the nested Query fixture fixed the harness. Test-file `py_compile` and `git diff --check` exited `0` (only LF→CRLF notices). Consolidated CI remains the batch gate.
- No real Telegram document was sent; no file, production data, provider, wallet, AutoPost, engine, merge, deploy, or restart was touched. This verifies offline callback plumbing, not live delivery or client rendering. A3/A5/A6 and end-to-end A7 remain partial.

### A7 Bảng giá latest manual tap — 2026-10-10 approximately 03:21 +07

- The Owner reports the Bảng giá screen appeared immediately (`<1s`) after the latest tap. This is one manual end-to-end screen observation; the click time was not supplied to second precision.
- The nearest seven-day strict-host aggregate contained three `pricing` dispatches (average `377.814 ms`, maximum `741.848 ms`) and no dispatch above one second, but those records cannot be matched to this individual tap.
- No Pricing latency fix is justified by this evidence. It does not establish that other buttons are fast or explain Account → Back's reported 2–3 seconds. ReplyKeyboard/message-handler time and Telegram/client rendering remain outside the callback observer; A7 stays partial. No production change, deploy, or restart.

### S12.35.200 — Public Support root → Home round-trip recheck

- Contract: dispatch the actual main-menu `menu|support` control through the registered Menu handler, then dispatch its emitted `menu|main` control through the same registered handler. Require the Support screen, exact Main return, and exactly one ACK per callback. No form submission or message send.
- Evidence: `test_customer_root_support_home_returns_to_main_menu` passed (`Ran 1 test in 0.287s — OK`) using a synchronous fixture driver that rejects yielded async I/O. The actual public keyboard supplied both controls; the Support screen rendered, the emitted Home returned to Main, and both callbacks were ACKed once.
- Harness note: the normal Windows `asyncio.run` fixture invocation stalled before completion in the known Proactor fallback path and was interrupted; the immediate no-I/O fixture run completed. This is a test-harness limitation, not a reproduced bot-route defect.
- Limits: offline registered-handler evidence only; no real Telegram, customer message, production data, provider, wallet, AutoPost, engine, merge, deploy, or restart. A3/A5 remain partial for untested action-capable and excluded paths.

### S12.35.201 — Document Split confirmation “Add more” callback

- Contract: dispatch the actual “Add more” control emitted by the Document Split confirmation keyboard through the registered document callback. Require the upload prompt, preserve the current user's staged files/options/page selection, preserve another user's pending state, and ACK once; do not upload or process files.
- Evidence: `test_confirmation_add_more_preserves_staged_files_options_and_other_user_state` passed using the source-extracted production builder/handler and an immediate driver that rejects yielded I/O (`focused emitted document Add-more route: OK`). The emitted callback was `docflow|send_more`, accepted by the registered route; the handler returned to Upload files without clearing staged selections or touching the other fixture user's state.
- Limits: fixture-only callback/state evidence; no real file, processing, production data, Telegram, provider, wallet, AutoPost, product engine, merge, deploy, or restart. Consolidated CI remains the batch gate.

### S12.35.202 — Package group Back ancestry across protected product categories

- Contract: from the public Pricing Catalog and Account → Pricing → Catalog, enter the emitted Gói/Combo screen and dispatch only each emitted Image, Video, Music, Voice and SubDub package-group control. Each group Back must restore the exact Gói/Combo controls, then its Back must restore the exact originating Catalog and Account Pricing parent. Do not open package details, purchase, generate, upload, or invoke a product engine/provider.
- Evidence: immediate no-I/O source-extracted drivers dispatched emitted controls through the registered Pricing and Package handlers. In both public and Account-origin paths, all five group callbacks retained the correct origin; every group Back returned to the corresponding `pkgcombo:home:*`; package-home Back restored the exact Catalog callback set, and Catalog Back restored the exact Pricing hub in the Account-origin route. Results: `package Back route matrix (Image/Video/Music/Voice/SubDub): 5 groups — OK` and `Account → Pricing → Catalog → Packages Back matrix (Image/Video/Music/Voice/SubDub): 5 groups — OK`.
- Limits: UI navigation only. No Product/Edit/SubDub/Voice/Music engine function, package detail, payment, wallet, provider, production data, Telegram, merge, deploy, or restart was entered. Consolidated CI remains the batch gate.

### S12.35.203 — Large-order Back restores its immediate package screen and Pricing origin

- Contract: dispatch the emitted “Cần gói lớn hơn” controls from origin-scoped package Home, Notes, My Packages, Image group, Combo group, monthly detail and combo detail through the registered `^pkgcombo:` handler. Back must restore the exact immediate parent for Account Pricing and public Catalog origins. Fake order-request creation and Telegram rendering; do not create an order, purchase, payment or product job.
- RED: the Account-origin Home path emitted Back=`pkgcombo:home`, losing `pricing_main_profile`. The expanded route matrix showed the same origin loss for group, combo-group and both detail types. After those were preserved, Notes and My Packages still returned to Home instead of their own screen for both Account and Catalog origins.
- Fix: origin-bearing package screens now append their allowlisted origin to their large-order controls. Large-order Back restores the corresponding Home/Notes/My/group/combo-group/detail/combo-detail parent. Legacy unscoped routes retain their prior destinations. Only callback navigation/render data changed.
- GREEN: the registered-handler matrix passed 14 scenarios (7 emitting screens × 2 Pricing origins); with five adjacent package-navigation tests, the initial targeted run passed `6 tests in 30.583s — OK`. A follow-up Home → large-order → Back regression passed for English, Chinese, and fallback locales; the final focused run passed `7 tests in 34.619s — OK`. These tests use emitted controls and registered routes, with order creation and Telegram rendering replaced by inert fakes.
- Verification limits: the full package-navigation module stalled in the legacy Windows Proactor Pricing-fixture `asyncio.run` path and was interrupted; it is not a pass. Full `py_compile bot.py` produced no output for 60 seconds and was interrupted; the source-extracted production functions did compile/execute in the focused fixture. `git diff --check` had no whitespace errors. Consolidated CI remains required.
- No actual order, purchase, payment, provider, wallet, production write, Telegram send, Product/Edit/SubDub/Voice/Music engine action, AutoPost, merge, deploy or restart. Overall A3/A5/A6/A7 remain partial.

### A7 Bảng giá latest user-visible tap — 2026-10-10 approximately 04:02 +07

- The Owner reports the Bảng giá screen appeared immediately (`<1s`) after the latest tap. The response arrived around 04:02 +07; exact tap time was not supplied, so it cannot be correlated to a particular server event.
- This supports that Bảng giá was fast in this observation only. The nearest seven-day aggregate remains sparse and uncorrelated; Account → Back is still reported at 2–3 seconds without a matched event. No latency patch is indicated for Pricing, and no all-button smoothness or Telegram/network/client root-cause claim is made.
- No production source, raw logs, IDs/payloads, provider, wallet, data, Telegram send, deploy, or restart was touched for this observation.

### S12.35.204 — Pricing Guide Back/Home across fallback locales

- Contract: for each supported locale outside vi/en/zh, dispatch the actual Pricing hub's emitted Guide callback through the registered Pricing handler; verify the Guide screen, its emitted Back to the same Pricing hub, and emitted Home to Main through the registered Menu handler. Use deterministic guide text and an immediate fixture driver that rejects I/O. Do not top up, send documents, change preferences, or enter product actions.
- Evidence: all 14 fallback locales were run from actual menu builders and registered handlers. Guide text matched the selected locale, every emitted Back restored the exact Pricing-hub callback list, and every emitted Home returned to Main; each callback ACKed once. Focused result: `Ran 1 test in 37.584s — OK`.
- Limits: fixture-only route/render assertions; no real Telegram/client timing, preference or billing operation, document send, provider, wallet, production data, AutoPost, engine, merge, deploy, or restart. A3/A5 remain partial beyond this Guide-entry slice.

### S12.35.205 — Feedback retry through the registered text dispatcher

- Contract: reproduce a one-time Feedback classifier failure and retry the same message through the actual registered non-command `MessageHandler`, actual decorated `handle_message` body, and actual idempotency decorator. Verify the first failure preserves Feedback pending/dedupe eligibility and the retry creates one fixture ticket, clears only Feedback pending, and replies/notifies once. Stub all earlier pending owners as false and leave AutoPost `context.user_data` empty; no production message/DB access.
- RED/fix scope: the previous S196 assertion source-checked `handle_message` but invoked only the child handler. An initial attempt to run the full handler under Windows `asyncio.run` stalled before assertions; replacing that runner with the immediate no-I/O coroutine driver exposed a fixture context missing `user_data` and an incorrect expected return (`handle_message` intentionally returns `None` after handling). The fixture now supplies empty context state and asserts the actual outer contract. No production-code change.
- GREEN: exact registered-message retry assertion printed `registered handle_message retry assertion: OK`; changed test modules `py_compile` exited `0`; `git diff --check` exited `0` (one existing LF→CRLF notice only). The module is included in the safe-navigation pytest CI step; local pytest is unavailable, so this is direct assertion evidence, not pytest/CI.
- Limits: fixture-only classifier/ticket/notifier/reply and false-returning unrelated pending owners. No AutoPost branch, real Telegram message, production DB/data, provider, wallet, engine, merge, deploy, or restart. Other `handle_message` branches and live Telegram delivery remain outside this case; A3/A5 remain partial.

### A7 Bảng giá follow-up — 2026-10-10 approximately 11:01 +07

- The Owner reports that after the latest tap the Bảng giá screen appeared immediately (`<1s`). The exact click timestamp was not supplied, so this cannot be correlated to a particular server timing event.
- This is one user-visible Pricing observation only; it does not establish all-button smoothness or explain the separate Account → Back report of 2–3 seconds. No Pricing code change is indicated. Telegram/client/network attribution remains unproven.
- No source, raw logs, IDs/payloads, provider, wallet, production data, Telegram send, deploy, or restart was touched for this observation.

### S12.35.206 — Feedback-created ticket View Current Back origin

- Contract: from the actual Feedback-created ticket result keyboard, dispatch only its emitted “View Current” control through the registered `^ticket\|` handler. Its detail Back must restore the same ticket receipt screen. Preserve Account/profile and legacy Support destinations; use fixture reads only and do not reply, resolve, attach files, message an admin, or mutate production data.
- RED: the actual `support_ticket_created_keyboard` was passed through the existing origin wrapper with Feedback result context, but the wrapper returned `ticket|pv|901` without origin. The focused assertion failed specifically: expected `ticket|pv|901|feedback_result`, actual `ticket|pv|901`; fixture setup had no errors.
- Fix: the Feedback success response now wraps the existing ticket-created keyboard with `feedback_result`; the registered `^ticket\|` route accepts this scoped origin for customer detail and summary only. Detail Back emits `ticket|summary|<id>|feedback_result`, restoring the same receipt. The Ticket-origin wrapper preserves unscoped My Tickets, Support and Home destinations for this origin while retaining Profile/legacy behavior.
- GREEN: actual emitted control → registered Ticket handler → detail → emitted Back → rendered receipt passed: `Feedback result -> View Current -> Back -> receipt: OK`. Reply and Attachment prompts also returned through Ticket detail to the receipt without sending input/files: `Feedback result -> View/Reply/Attach -> Back -> receipt: OK`. Five adjacent Ticket/Profile-origin regressions passed: `5 ticket/profile-origin fixture regressions: OK`; three additional Profile-result/legacy regressions passed: `3 Profile-result/legacy ticket-origin regressions: OK`; the actual registered Feedback retry remained green: `registered handle_message retry assertion: OK`. Both changed test files `py_compile` exited 0 and `git diff --check` exited 0.
- Verification limits: full `py_compile bot.py` returned no output for about 100 seconds and was interrupted; do not count it as a pass. Ordinary `unittest` invocations stalled in the Windows Proactor path; focused no-I/O fixtures passed. No reply text was submitted, no attachment was sent, and the resolve/done action was not invoked. Consolidated GitHub source-compile and CI remain required. No real ticket/data/message, provider, wallet, AutoPost, protected engine, merge, deploy, or restart.

### S12.35.207 — Internal Archive view/file pre-ACK lookup latency risk

- Contract: source-audit the actual emitted Archive result `view` control and detail `file` control against the registered `^archive\\|` handler. Determine whether the owner-scoped lookup runs before callback acknowledgement. Do not read real documents, send files, or change stale/error UX without a reproduced route-specific delay.
- Evidence: `internal_archive_results_keyboard` emits `archive|view|<id>`; the registered handler is `handle_internal_archive_callback` (`bot.py:274765`). Its `view` and `file` branch calls synchronous `get_internal_document(uid, id)` (`bot.py:234940`), which opens SQLite and executes an owner/status-scoped SELECT (`bot.py:234879`), before either branch calls `query.answer()` (`bot.py:234946+`). Existing S12.35.151/.152 fixture checks establish route/render and fake-send behavior, not latency.
- Complementary S12.35.232 pre-screen: the narrow explicit DB/execute/fetch/network/sleep scan found `get_internal_document` as its only textual match in 87 callback-handler bodies; a separate getter-name scan flagged 20 bodies for manual triage. Source review also confirms Ticket and Document Back/Main paths call SQLite-backed `get_user_language` before ACK, and selected Ticket result/detail actions perform an additional `get_support_ticket` SELECT before ACK. See S12.35.232. These are possible server-side waits, not confirmed slow buttons; no stale/error UX change is justified without a correlated slow-route sample.
- Fresh source detail (2026-10-10): get_internal_document calls synchronous db_connect() before the view/file ACK. That helper configures SQLite timeout=30 and busy_timeout=30000 before the SELECT, so a database lock can theoretically delay this callback path before acknowledgement. This is a source-level upper-bound risk only; the approved 24-hour aggregate was empty and no live delay was correlated. Preserve the current stale-document alert until a measured route-specific delay and replacement UX are established.
- Finding: this is a possible server-side pre-ACK wait on those Admin actions, but there is no correlated live timing sample showing it is slow. No production/UI code was changed: moving the ACK ahead of lookup would change how missing/stale documents can retain the current alert response.
- Limits: source-only review; no database read, document access/send, production click, Telegram/network timing, provider, wallet, AutoPost, engine, merge, deploy, or restart. A7 and whole-bot completion remain partial. Defer an ACK-order change until a safe route-specific latency sample or an explicit stale-result UX contract exists.

### S12.35.208 — Account Back route and ACK/render boundary

- Contract: distinguish Account-root Home (`menu|main`) from Account-child Back (`menu|main_profile`), verify each is registered and inspect which latency phases are already observable. Do not change common menu timing/handler logic absent a correlated slow server phase.
- Evidence: the Account root keyboard emits `menu|main` for its Main-menu button (`bot.py:136054`); Account child keyboards emit `menu|main_profile` (`bot.py:136061`). Both use the registered Menu handler. Existing S12.35.190 fixture evidence dispatched the actual root keyboard and confirmed Account → Main, while the timing observer labels exact root/account callbacks separately. In `handle_menu_callback`, the `menu|main` path ACKs at `bot.py:142020` before cleanup, language lookup, content build (`bot.py:142594`) and render; its existing route logger separates pre-ACK, ACK, language, cleanup, build and render. The `menu|main_profile` render reads account balance/role/package summary synchronously, but its generic observer already reports handler and render-helper durations.
- Finding: no wrong destination or late callback ACK was found in source. The Owner's 2–3s report lacks an exact route/screen and matching event; the latest measured tap in this conversation was Bảng giá (<1s), which is a different callback. The prior seven-day aggregate is sparse and cannot attribute this particular delay. No code change or new instrumentation is justified by the current evidence.
- Verification: a focused local unittest rerun produced no output for over 30s and was interrupted; it is not counted as a pass. Retain the prior S12.35.190 route/timing-fixture result already recorded above. No end-to-end Account click was newly measured.
- Limits: no production data, Telegram send, provider, wallet, AutoPost, protected engine, merge, deploy, or restart. A7 remains partial pending a route-specific correlated sample; client/network attribution is unproven.

### S12.35.209 — ReplyKeyboard Home routing and latency boundary

- Contract: verify the visible ReplyKeyboard Home labels reach the main-menu route before a pending AutoPost content prompt can consume them. Separate this message route from inline callback latency; do not change AutoPost or shared message dispatch without a reproduced defect.
- Source evidence: `main_reply_keyboard()` emits `🏠 TOAN AAS MENU`; the registered `MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)` sends both supported Home labels to `cmd_start` before the AutoPost `awaiting_content_input_type` branch. The idempotency decorator uses a per-message in-memory lock/dedupe set, not a database lookup. The callback timing observer does not measure this MessageHandler path.
- RED/root cause: the focused fixture under the original `asyncio.run` produced no result; a checkpointed rerun confirmed it stalls at that runner boundary on Windows. The fixture itself uses only immediate coroutine stubs and requires no I/O.
- Minimal test fix: replace `asyncio.run` in this test with a no-I/O coroutine driver that raises if the fixture yields. No production `handle_message`, AutoPost, or menu code changed.
- GREEN: the test’s exact production-source handler assertions were directly invoked with only the `pytest.mark.parametrize` decorator shimmed: `ReplyKeyboard Home priority: 2 labels OK; ordinary AutoPost input preserved: OK`. Bundled Python `py_compile` exited `0`; local `python -m pytest ...` could not start because pytest is not installed in that runtime. The test is in CI’s safe-navigation pytest list; GitHub CI has not run for this change. This is direct local evidence, not a pytest or CI pass.
- Finding/limits: no Home-vs-AutoPost routing defect reproduced. Server timing for ReplyKeyboard/`cmd_start`, live Telegram rendering, and a correlated click remain unmeasured. No real Telegram message, production data, provider, wallet, AutoPost state, protected engine, merge, deploy, or restart. A7 and whole-bot latency remain partial.
- A read-only 24-hour production callback aggregate was attempted after this observation. The default workspace could not resolve `tg.toanaas.vn`; the authenticated retry was rejected by the approval reviewer because remote journal access needs more explicit authorization. No production logs were returned/read, so this adds no timing evidence and does not change the finding.
- Current runner check (2026-10-10): bundled Python has no `pytest` package (`unittest` import fails with `ModuleNotFoundError: No module named 'pytest'`), so the existing parameterized module cannot be run as ordinary unittest. The prior direct no-I/O assertions above remain the only local result; consolidated CI has not run.

### S12.35.210 — Expired Document Split page prompt is consumed

- Contract: dispatch an expired Split PDF page-range text through the actual registered non-command `MessageHandler` and production `handle_message` / `handle_doc_tool_pending_text` source. It must be consumed with an expiry notice and Documents-menu recovery, not generic chat; clear only that user's stale Document state and preserve another user's state. No file/PDF/provider/wallet/production action.
- RED: the focused test reached the behavior assertion and observed `events == ['generic_chat']` for an expired `split_pdf` prompt. Initial harness setup lacked unrelated dispatcher globals; adding false-returning pending-handler stubs and inert route utilities resolved setup without altering product behavior.
- Fix: the Document pending-text handler now detects an expired page prompt before the generic TTL getter removes it, clears only that user's expired state, replies with localized expiry text and `main_docs_keyboard`, and returns handled.
- GREEN: the registered-handler regression first passed `Ran 1 test in 1.082s — OK`; fresh 2026-10-10 replay passed `Ran 1 test in 1.434s — OK`. A same-day replay against exact `HEAD:bot.py` independently reproduced the behavior RED (`BASELINE_FAILURES=1`, `BASELINE_ERRORS=0`, `generic_chat` received the expired page text). The test is included in the current dirty safe-navigation CI list; remote CI has not run on this WIP. Fresh continuation rerun: `python -m unittest -v tests.test_doc_expired_page_spec_input` — `Ran 1 test in 1.471s — OK`.
- Fresh cross-case recheck (2026-10-11): `test_expired_emitted_message_handler_consumes_text_before_generic_chat` passed as part of the three-case focused run (`Ran 3 tests in 6.728s — OK`).
- Verification limits: the adjacent legacy Document Back test imports the full `bot` module and produced no output for over 60 seconds in this Windows runtime; it was interrupted and is NOT_VERIFIED, not counted as a pass or product failure. Local pytest is unavailable; consolidated CI is still pending. The new test compiles/executes the changed extracted handler; full `py_compile bot.py` was not rerun.
- No PDF processing, file upload/save, production data, Telegram send, provider, wallet, AutoPost, protected engine, merge, deploy or restart. A3/A5/A6/A7 and whole-goal closeout remain partial.

### S12.35.211 — Admin Overview route and report aggregation

- Contract: dispatch Admin Overview through the registered `menu|` route and verify its report render plus emitted Finance/Admin/Home controls. Validate the actual report aggregation helpers against seeded in-memory SQLite under a read-only query authorizer; missing provider telemetry must be shown as unavailable, not a healthy zero.
- Harness issue: the original Overview test used `asyncio.run`; on this Windows runtime it hung in Proactor `_fallback_socketpair` before product assertions. Replaced only the test runner with an immediate driver that fails if any fixture coroutine yields I/O.
- Evidence: the registered Overview callback rendered the expected fixture summary and routes. The actual report payload aggregated seeded users, revenue/Xu, credits, tools, provider failures and referrals; when the provider-log table was absent, it rendered “không khả dụng” rather than zero. The two Admin Overview/report-source modules were rerun after fixture expansion: `Ran 3 tests in 4.355s — OK`; a fresh local rerun on 2026-10-10 passed `Ran 3 tests in 4.957s — OK`. Data came only from in-memory SQLite under a SELECT/READ/FUNCTION-only authorizer and a fake Telegram sink.
- Limits: all data is in-memory and rendering uses a fake Telegram sink. This verifies only the tested read-only report slice—not production report data, every Admin report, operational actions, or all Admin screens. No production DB/message, provider, wallet, AutoPost, protected engine, merge, deploy or restart. CI remains pending; A1/A3/A5/A6/A7 and whole-goal closeout remain partial.

### S12.35.212 — Expired Support/Ticket input is consumed

- Contract: dispatch expired Support/Ticket text through the actual registered non-command MessageHandler and production handle_message / handle_support_pending_input source. It must be consumed with localized expiry copy and origin-aware Back/Home, clear only that user's expired Support state, and not reach generic chat or ticket create/notify seams.
- Root cause: expired Support input could fall through after the generic Support TTL getter discarded the pending entry. The narrow expired-step guard already present in this worktree recognizes stale Support steps before normal pending processing and returns handled.
- RED/fixture diagnosis: the adjacent Account Support origin test failed because its inherited ui_text stub returned “🔙 Back” for every key; the assertion expected the expired copy. This was a fixture compatibility issue, not a second product defect.
- Minimal test correction: the Support pending fixture now returns expiry copy only for common.expired_not_charged and keeps the existing Back copy for all other keys. No production behavior changed in this fixture correction.
- GREEN: the expired Support origin test passed individually. The Support pending-origin and registered-dispatcher regressions ran 6 tests in 47.628s — OK using an immediate no-I/O coroutine driver. The registered-dispatcher case verifies expiry response with support|start|profile and menu|main, no generic-chat event, removal of only the actor's stale key, and preservation of another user's active key. The adjacent origin test confirms no ticket create/notify calls. Both test files are added to CI's safe-navigation list; remote CI is pending.
- Verification limits: the bundled Python has no pytest. Two full bot.py compile attempts produced no marker/exit and were interrupted after bounded waits, so full-file syntax verification is NOT_VERIFIED; production handler functions were source-extracted, compiled, and executed by the focused tests. git diff --check exited 0; only existing LF-to-CRLF warnings were reported.
- Limits: offline extracted-source fixture only. No real Telegram message, ticket, production data, provider, wallet, AutoPost, protected engine, merge, deploy, or restart. A3/A5/A6/A7 and whole-goal closeout remain partial.
- Fresh 2026-10-10 baseline recheck: exact `HEAD:bot.py` returned `BASELINE_FAILURES=1`, `BASELINE_ERRORS=0`, with `public_chat` receiving the expired Support text; the current registered-dispatcher test passed `Ran 1 test in 3.129s — OK`. This is a product baseline RED, distinct from the earlier fixture-copy mismatch. The narrow TTL guard is a pre-existing WIP hunk; no source was changed in this turn. Fresh continuation rerun: `python -m unittest -v tests.test_support_expired_input_dispatch` — `Ran 1 test in 1.931s — OK`.
- Fresh cross-case recheck (2026-10-11): `test_expired_ticket_text_is_consumed_before_public_chat` passed as part of the three-case focused run (`Ran 3 tests in 6.728s — OK`).

### S12.35.213 — Document Confirm/Add more use emitted registered callbacks

- Contract: for a one-file PDF-tool fixture, build Confirm and Add more with the production after-file keyboard. Match each emitted callback through the source registration to the actual document handler; Confirm must show the minimum-file alert once, while Add more must return to that tool's upload prompt with one ACK. Keep file-processing and delivery seams inert.
- Evidence gap: the previous test wrote docflow|confirm and docflow|send_more directly into the query, then called an extracted handler. It did not prove those controls were emitted or selected by the actual registration pattern.
- Verification: the revised two-case test runs the production keyboard builder, executes the source registration line with an inert Telegram adapter, matches each emitted callback to that route, and invokes the registered handler. Local output: “Document emitted Confirm/Add more -> registered handler: 2 tests OK”. The test is added to CI's safe-navigation list; remote CI is pending.
- Finding: both buttons are emitted with callbacks handled by the registered route. Confirm with one input for a two-file tool returns the expected alert; Add more shows that tool's upload prompt. No product defect reproduced; this closes the callback-evidence gap.
- Limits: offline extracted-source fixture only. No file processing, file send, real Telegram, production data, provider, wallet, AutoPost, protected engine, merge, deploy, or restart. A3/A5/A6/A7 and whole-goal closeout remain partial.

### A7 — Approved 24-hour callback timing aggregate — 2026-10-10 12:17:44 +07

- Owner approved a single SSH read-only query against `toanaas-bot.service`, filtered to `callback_dispatch_timing`; the command returned anonymous aggregates only, not raw log lines, IDs, or payloads.
- Result: `menu` / `handle_menu_callback` / `unclassified`: 1 event, 478.802 ms average and maximum; `pricing` / `handle_pricing_callback` / `unclassified`: 3 events, 377.814 ms average, 741.848 ms maximum. No sampled dispatch exceeded 1,000 ms; no other route prefix appeared in this window.
- Interpretation/limits: this is a sparse 24-hour handler-dispatch sample. The menu event cannot be attributed to Account → Back; Pricing events cannot be tied to the Owner's individual Bảng giá tap. Handler duration includes awaited work but does not isolate internal or Telegram API phases, nor measure the user's network-to-Telegram or client rendering. ReplyKeyboard/MessageHandler remains outside this observer. No route-specific latency defect was reproduced; no code change is indicated. A7 remains partial.
- Owner follow-up after this sample: the latest manual Bảng giá tap displayed immediately (`<1s`). It is a user-reported screen observation without an exact click timestamp or matching server event; it supports “Pricing was fast on this tap” only and does not close A7 or establish all-button smoothness.

### S12.35.214 — `/profile` command registration delivers the localized Account keyboard

- Contract: execute the actual `CommandHandler("profile", cmd_profile)` registration with an inert Telegram adapter, invoke the registered command against fixture-only account values, and verify the production `main_profile_keyboard` is attached in the saved locale with its six expected rows. Stub the birthday auto-grant seam and all account reads; no wallet or production access.
- Evidence gap: `tests/test_core.py` already asserted that `/profile` sends its keyboard, but that test imports the entire bot module and is not in the consolidated safe-navigation test step. Existing callback navigation starts at the inline root, so the command registration/output was not independently proven there.
- Fixture correction: the first direct run exposed a synchronous `None` stub for an awaited birthday-check seam, then a missing `balance` copy key. Both were harness setup errors before the product assertion; the fixture now uses an immediate async no-op and complete copy values.
- GREEN: targeted unittest `test_profile_command_registration_sends_the_actual_localized_account_keyboard` → `Ran 1 test in 0.270s — OK`. It executes the source registration line, checks command name and callback identity, invokes the registered callback with inert user/account seams, verifies HTML output and compares the emitted callback rows with the actual production keyboard builder for `en` (six rows); all locale-bearing seams received `en`. The method is in `tests/test_admin_root_menu_callback_single_ack.py`, already included in CI's Admin Route Regressions command; no workflow change was needed.
- Finding/limits: the approved `/profile` keyboard path is present and localized; no product defect or production source change reproduced. This is command/UI fixture evidence, not a real account or Telegram-client rendering test. No birthday grant, wallet/database operation, provider, production data, AutoPost, protected engine, merge, deploy or restart. Consolidated CI and whole-bot closeout remain pending; A3/A5/A6/A7 remain partial.

### S12.35.215 — Public Support Auto-support information route returns to its parent

- Contract: emit the public Support root keyboard, dispatch its `support|cskh_auto` information control through the registered Support handler, then follow that page's emitted Back to the exact Support root and Home through the registered Menu handler to Main. Keep the Telegram contact URL inert; do not open a ticket, enter a lead, or send a message.
- Evidence: actual production keyboard builders and registration expressions were source-extracted. The route fixture asserts one ACK on each dispatch, Auto-support information render, the exact Support-root callback set after Back, Main after Home, and pending cleanup scoped to the fixture actor. Focused unittest: `Ran 1 test in 3.723s — OK`.
- Harness notes: the first attempt referenced the nested fixture's dispatcher at the wrong level; the next used a Windows `asyncio.run` path that waited without reaching assertions and was interrupted. The test now uses an immediate no-I/O coroutine driver; missing fixture `Query`/Menu timer dependencies were supplied before the final pass. These were harness setup/runtime issues, not product assertions.
- Finding/limits: the public informational route and its Back/Home destinations match the intended flow; no production defect/source change reproduced. The test is in `tests/test_profile_support_read_back_origin.py`, already run by CI's Account Support Read-only Back Regressions command. This is offline UI/route evidence only; no external URL, ticket/lead, customer message, production data, provider, wallet, AutoPost, protected engine, merge, deploy, or restart. A3/A5/A6/A7 and whole-goal closeout remain partial.

### S12.35.216 — Public Support information pages Back/Home routes

- Contract: emit the public Support root keyboard and dispatch its `admin_contact`, `premium`, `bot`, and `consult` information controls through the registered Support route. Each page must expose Back to Support root and Home to Main; emitted Back must restore the exact root callbacks. Keep contact URLs inert and do not enter ticket/lead input or creation routes.
- Evidence: the focused test exercises all four actual emitted callbacks against the registered Support handler, asserts one ACK per page/Back/Home, checks each localized information page, exact root callback restoration, and Main rendering. Combined focused S12.35.215/S12.35.216 run: `Ran 2 tests in 15.228s — OK`; changed test `py_compile` exited 0; `git diff --check` exited 0. Test is in the existing CI Account Support Read-only Back Regressions command.
- Harness/verification limits: the first run exposed a wrong nested-fixture helper reference, corrected without reaching product assertions. The whole test module stalled in its earlier Account-origin method and was interrupted after about 60 seconds; that module run is NOT_VERIFIED, not a product failure or pass. The focused new and adjacent S12.35.215 tests are the counted evidence; consolidated CI is still pending.
- Finding/limits: all four public informational buttons have registered routes and return to the expected parent; no product callback defect or production-source change reproduced. Fixture-only route evidence does not measure live latency or Telegram-client rendering. No contact URL opened, ticket/lead created, customer message sent, production data, provider, wallet, AutoPost, protected engine, merge, deploy, or restart. A3/A5/A6/A7 and whole-goal closeout remain partial.

### S12.35.217 — Public Support ticket prompt Back/Home

- Contract: from the actual public Support root, dispatch only its emitted `support|ticket` control through the registered Support handler. Verify the general-support prompt, one acknowledgement, actor-scoped `awaiting_message` state and stored Support Back origin. Exercise emitted Back and Home through registered handlers; Back must restore the exact public Support root, Home must render Main, and neither may create a ticket or notify an administrator. Preserve another user's pending fixture; submit no input and keep all business seams inert.
- Acceptance evidence: emitted callback → exact registered route; prompt and pending fields match public Support origin; Back restores exact callback set and clears only the actor; Home reaches Main and clears only the actor; zero ticket creation, notification, submitted text, production data or customer messages.
- Evidence: `test_public_emitted_ticket_prompt_back_and_home_use_registered_routes` dispatches the actual `support|ticket` control emitted by `human_support_keyboard()` through the registered Support handler, asserts the general-support prompt and stored public-origin pending fields, and dispatches the prompt's emitted Back and Home through the registered Support/Menu routes. Both exits clear only actor 123 and preserve user 999's pending fixture; the fake create/classify/notify seams remain unused. Focused result: `Ran 1 test in 7.508s — OK`; changed-test `py_compile` and `git diff --check` exited 0. This test is in the existing safe-navigation CI command.
- Account-origin follow-up: `test_all_four_form_emitters_persist_their_account_back_context` dispatches the emitted Account and Support controls through their registered routes for Ticket, Premium, Bot and Consult. It asserts each prompt retains its expected `back_to` callback and invokes no business seam. The original nested fixture called `asyncio.run()` and stalled on Windows; `_form` now uses an immediate driver that fails if a callback yields I/O. First driver attempt referenced the nested Query fixture at the wrong level (setup errors); after correcting the reference, `Ran 1 test in 22.184s — OK`.
- Verification: after replacing only the Windows-stalling nested `asyncio.run()` fixture dispatch with the immediate no-I/O test driver, the full `tests.test_profile_support_pending_origin` module passed 6 tests in 71.052s — OK. Consolidated CI remains pending. No public or Account-origin ticket-entry navigation/pending mismatch was reproduced, so production code did not change for S12.35.217. No customer text, ticket, classification, notification, database write, production data, provider, wallet, AutoPost, protected engine, real Telegram message, merge, deploy, or restart. Live client latency/rendering and A3/A5/A6/A7 whole-goal evidence remain open.

### S12.35.218 — Public Support My Tickets list Back/Home

- Contract: emit the public Support root keyboard, select its `ticket|mine` callback, and dispatch through the registered Ticket handler with only a fixture-owned ticket. Require one ACK and a fixture-only list read; the emitted Back must restore the exact public Support root, and emitted Home must reach Main through the registered Menu route. Preserve owner scoping; do not update a ticket, reply, attach a file, access production data, or send a customer message.
- Acceptance evidence: actual Support-root emitter → exact registered Ticket route; actor-owned fixture list; emitted Back restores exact public Support callback list; emitted Home reaches Main; zero ticket mutation/message/production access.
- Evidence: `test_public_emitted_my_tickets_back_restores_public_support_and_home` dispatches Support start, selects the emitted `ticket|mine` control, and invokes the exact registered Ticket handler. The fixture list contains the owned row, ACKs once, and reads with `user_id=123`; emitted Back dispatches through Support and restores the exact public-root callbacks, while emitted Home dispatches through Menu to Main. Ticket status remains `new`, with no mutation/send calls. Focused result: `Ran 1 test in 4.359s — OK`; changed-test `py_compile` and `git diff --check` exited 0. The test is in CI's Customer Ticket Action Acknowledgement step.
- Finding/limits: no public My Tickets navigation/ownership defect reproduced; production code did not change. Fixture-only read/navigation evidence, not live latency or Telegram rendering. No ticket update, reply, attachment, production data, message, provider, wallet, AutoPost, protected engine, merge, deploy, or restart. Consolidated CI and whole-goal closeout remain pending.

### S12.35.219 — Public My Tickets detail Back restores the list

- Contract: reach My Tickets from the actual public Support root through its registered route. Select the emitted owned ticket row and dispatch through the registered Ticket route. Its emitted Back must restore the exact public list callback set and owned row. Use fixture-only reads; do not reply, attach a file, update status, or send a customer message.
- Acceptance evidence: registered Support and Ticket routes; only the owned fixture record is rendered/read; detail Back restores exact list controls and item; status and mutation/send ledger remain unchanged.
- RED: the exact emitted public path reproduced a behavioral mismatch with no fixture errors: ticket detail Back was `support|start` instead of the expected `ticket|mine` parent.
- Minimal fix: the public Support root's My Tickets control now emits `ticket|mine|support`. The registered Ticket route carries this UI origin through the owned detail and emits detail Back=`ticket|mine|support`; the origin wrapper normalizes the same shared Support keyboard back to `ticket|mine|profile` when entered from Account. Feedback-result summary origins and unscoped legacy routes keep their existing destinations. No Ticket business operation changed.
- GREEN: public My Tickets root Back/Home, public list→owned detail→exact list Back, and Account-origin scope regression passed together: `Ran 3 tests in 11.761s — OK`. Feedback-created-result Back and its reply/attachment prompt-return cases each passed in a separate run before the legacy adjacent case stalled. Changed ancestry test `py_compile` and `git diff --check` exited 0. The route module is in CI's Account Owned Ticket Ancestry step; consolidated CI is pending.
- Verification limits: a broader selected regression command stalled in a legacy `asyncio.run` case before completion and was interrupted after ~60 seconds; it is NOT_VERIFIED, not a product failure/pass. The named focused registered-route cases are the counted evidence.
- Finding/limits: public My Tickets → detail → Back now returns to the exact list, list Back returns to Support root, and Home returns to Main. Account and Feedback-result destinations remain scoped; fixture-only owned reads, ticket status remains `new`, and create/update/reply/attachment/send seams are not called. No production ticket/data, provider, wallet, AutoPost, protected engine, real Telegram, merge, deploy or restart. Live/client timing and A3/A5/A6/A7 whole-goal closure remain open.

### S12.35.220 — My Tickets Back preserves its exact parent

- Contract: from public and Account-origin Admin-contact, Auto-support, and Premium pages, plus the Ticket category menu, select emitted My Tickets controls through the registered Ticket route. List Back must return to the exact emitting page; detail Back must restore the same owner-scoped list. Fixture reads only.
- RED: two focused tests reproduced six Support-child mismatches without fixture/setup errors: all three public pages returned `support|start`; all three Account pages returned `support|start|profile`. A separate category-menu test showed its My Tickets control emitted unscoped `ticket|mine`, losing its parent.
- Minimal fix: the child-page My Tickets controls and category-menu control carry narrow origin tokens. Ticket origin parsing/wrapping preserves those tokens and composes `profile_<page>` for Account-origin Support pages. List Back now targets the exact child or category menu; Ticket business logic and engines are unchanged.
- GREEN: Support-child emitted-route regressions now include child → My Tickets → detail → exact list → exact child for all three public and Account-origin pages; `2 tests in 30.129s — OK`. Ticket category → list → detail → list → category passed `1 test in 3.799s — OK`. Existing public root Back/Home, detail Back, Account-root, Feedback-result and reply/attachment-prompt regressions ran `5 tests in 22.410s — OK`. Final combined 8-route regression passed `8 tests in 58.886s — OK`. The route module is already included in safe-navigation CI.
- Verification limits: focused fixtures source-extracted and compiled the changed production handlers. Full `py_compile bot.py` produced no output for 60 seconds and was interrupted, so whole-file compilation is **NOT VERIFIED**. `git diff --check` exited 0; only existing LF→CRLF notices appeared. Consolidated CI remains pending.
- Finding/limits: public and Account-origin Support-child My Tickets Back returns to the exact emitting page; Ticket category-menu Back restores the category menu and detail Back restores the list. Reads use actor-scoped fixtures; no ticket mutation, reply, attachment, notification, production data, Telegram message, provider, wallet, AutoPost, protected engine, merge, deploy, or restart. A3/A5/A6/A7 and whole-goal closure remain partial.

### S12.35.221 — Premium lead-form My Tickets preserves its parent

- Contract: from public and Account-origin Premium lead forms, select the emitted “Vé của tôi” control through the registered Ticket route. List Back must return to the exact Premium page; the abandoned lead-input pending state must be cleared by the existing list route. Fixture reads only.
- RED: the focused emitted-route test failed both contexts without setup errors: public emitted `ticket|mine`, Account emitted `ticket|mine|profile`; neither retained the Premium page origin.
- Root cause/fix: the shared `support_flow_back_keyboard` produced a generic Ticket-list callback in the Premium form context. Added an optional origin argument that defaults to the exact legacy callback; only the Premium lead form passes `premium`, allowing the existing Account wrapper to compose `profile_premium`. No Ticket lifecycle or pending helper changed.
- GREEN: Premium-form public/Account route and existing public/Account Premium-page ancestry regressions: `Ran 3 tests in 32.322s — OK`. A subsequent full `tests.test_profile_ticket_ancestry` rerun passed `18 tests in 171.092s — OK`, including this form and the earlier Ticket origin regressions. Test file `py_compile` exited 0; focused tests compile and execute extracted production handlers; `git diff --check` exited 0 with existing LF→CRLF notices. Full `bot.py` `py_compile` remains NOT_VERIFIED (the bounded local attempt produced no output for 60 seconds and was interrupted). The module is already in CI's Account Owned Ticket Ancestry step; consolidated CI remains pending.
- Limits: offline actor-owned fixtures only. No ticket mutation/reply/attachment/notification, production data, Telegram message or latency test, provider, wallet, AutoPost, protected engine, merge, deploy, or restart. This closes only the Premium-form route defect; A3/A5/A6/A7 and whole-goal closure remain partial.

### S12.35.222 — Account-origin Support form prompt Back/Home

- Contract: open each emitted Ticket, Premium, Bot and Consult input form from Account → Support through the registered Menu/Support handlers. Dispatch the prompt's actual Back and Home controls. Back must restore the exact immediate parent keyboard (Account Support root, Premium information, Bot detail, or Consult detail); Home must restore Main. Each exit clears only the actor's pending prompt and preserves another user's pending fixture.
- Acceptance evidence: eight route cases (four forms × Back/Home); callbacks come from the emitted prompt and match their registered handlers; exact parent callback sets and Main destination are asserted; no user text is submitted and create/classify/notify/DB/provider/payment seams stay unused.
- RED/fixture note: the first focused attempt errored before route assertions because the new fixture omitted the Menu handler's deterministic `perf_counter`; adding the same inert clock already used by the public-form test resolved this setup error. No product assertion failed.
- GREEN: the focused test dispatched all eight emitted Back/Home callbacks through registered Support/Menu routes and verified exact parent keyboards, Main, actor-only pending cleanup, other-user preservation, and zero business calls: `Ran 1 test in 53.834s — OK`. The complete `tests.test_profile_support_pending_origin` module then passed `Ran 7 tests in 119.708s — OK`. Changed test-file `py_compile` exited 0; `git diff --check` exited 0 with only existing LF→CRLF notices.
- Finding/limits: no Account-origin prompt Back/Home route defect reproduced; no production source changed. Fixture-only route/state evidence, not Telegram-client rendering or live latency. No user text, ticket creation, classification/notification, production data, provider, wallet, AutoPost, protected engine, merge, deploy, or restart. Consolidated CI and whole-goal A3/A5/A6/A7 closeout remain pending.

### S12.35.223 — Account Support information pages exact Back/Home

- Contract: from the actual Account → Support root, open each emitted read-only Admin-contact, Auto-support, Premium, Bot and Consult information page through the registered Support handler. Each page's emitted Back must restore the exact Account Support callback list; Home must dispatch through Menu to Main. Do not open a contact URL, enter a lead form, submit text, or invoke a business operation.
- Acceptance evidence: 10 emitted-route cases (five pages × Back/Home), exact Account Support callback-set comparison on Back, Main destination on Home, one ACK per callback, no create/classify/notify calls.
- Harness/expectation note: the original full-module run stalled in the imported `asyncio.run()` fixture helper; this module now uses the immediate no-I/O dispatcher, which fails if a route yields I/O. Its first completed run exposed one stale assertion from S12.35.221: Account Premium info correctly scopes `ticket|mine|premium` to `ticket|mine|profile_premium`. The registered Ticket origin parser returns to `support|premium|profile`; the test expectation was updated, with no production edit.
- GREEN: the focused Account Support information Back/Home matrix passed 10 emitted-route combinations in `Ran 1 test in 48.305s — OK`; the scoped-Premium assertion passed `Ran 1 test in 4.514s — OK`; the complete `tests.test_profile_support_read_back_origin` module passed `Ran 8 tests in 123.354s — OK`.
- Finding/limits: all five Account Support information pages restore the exact Support root on Back and reach Main on Home. No route defect reproduced; no contact URL opened, lead form entered, message submitted, or business operation invoked. Fixture-only evidence; both changed test files passed `py_compile`, and `git diff --check` exited 0 with only existing LF→CRLF notices. Consolidated CI remains the batch gate.

### S12.35.224 — Account Support form expiry Back/Home

- Contract: create each Account-origin Ticket, Premium, Bot and Consult pending form with in-memory fixtures, advance past its TTL, and submit one inert fixture message through the registered text handler. The stale input must be consumed with expiry copy; Back returns to the exact form parent, Home returns Main, and only the actor's expired pending state is cleared.
- Acceptance evidence: four emitted form types × expired-text handling; exact Back callback and parent keyboard; emitted Home to Main; other user's pending state preserved; create/classify/notify seams remain unused.
- Harness notes: the first runs exposed only fixture setup errors, not product assertions: the other-user pending fixture was created before advancing the shared clock and therefore was stale too, then the fixture markup flattener was called with a Markup instead of a Query. The test now creates the other user's fresh state after expiry and reads the returned keyboard directly.
- GREEN: focused test covered all eight emitted expired-form Back/Home routes (4 forms × 2 exits), exact parent callback sets, Main, actor-only cleanup, other-user preservation, and no create/classify/notify calls: `Ran 1 test in 44.463s — OK`. The full `tests.test_profile_support_pending_origin` module passed `Ran 8 tests in 197.600s — OK`.
- Finding/limits: no form-specific expiry or Back/Home defect reproduced; no production source changed. Fixture-only test; all three changed Support/Ticket test files passed `py_compile`, and `git diff --check` exited 0 with only existing LF→CRLF notices. Consolidated CI and overall A4/A3/A5/A6/A7 closeout remain pending.

### S12.35.225 — Public Video exact callback replay boundary

- Contract: exercise the actual extracted replay guard before the registered public `vprofile` callback without invoking its handler body, job/provider/wallet seams, or protected engine.
- Evidence: the first query ID reaches the inert route seam; replay of the same ID is stopped before the route and acknowledged once; a distinct ID reaches the seam. Focused result: `Ran 1 test in 0.424s — OK`; test-file `py_compile` and `git diff --check` exited 0.
- Fresh cross-case recheck (2026-10-11): `test_exact_replay_stops_before_route_but_distinct_event_reaches_route` passed as part of the three-case focused run (`Ran 3 tests in 6.728s — OK`).
- Finding/limits: no production change was justified. This proves exact Telegram update replay suppression only—not idempotency of two distinct rapid taps, product output, or live latency. The test is in CI; GitHub CI remains pending. Local `origin/main` was `381d3359…` (not freshly fetched); the guard/prefix/registration slice had no diff hunk against it.

### S12.35.226 — Approved callback timing query and checked rerun

- Contract: one strict-host, read-only SSH query over the preceding 24 hours, filtered only to `callback_dispatch_timing`; return anonymous count/average/maximum grouped by route and handler. No raw logs, IDs, or payloads.
- First attempt: SSH exited 0 and printed `NO_EVENTS`, but that reducer suppressed `journalctl` stderr and did not propagate its exit status. That output remains inconclusive and is not counted as zero.
- Checked rerun: at 2026-10-10 17:16:56 +07, SSH succeeded; the single `journalctl -u toanaas-bot.service --since '24 hours ago' --no-pager -o cat` process returned exit 0 with empty stderr. The bounded reducer returned `EVENTS=0 malformed_matching_lines=0`; it printed no journal lines, identifiers, or payloads.
- Finding/limits: this is a verified empty 24-hour callback-timing sample, not evidence that buttons are fast or slow. No server dispatch can be tied to the Owner's approximate 2–3 second Account → Back report, and this query cannot distinguish bot handling from Telegram transport, network, device, or client rendering. No code, service, or hardware change is justified. A7 remains partial pending a precisely timed click with a matching route event and coverage of uninstrumented message/reply-keyboard paths.

### S12.35.227 — Admin Support Ticket hub and read-only panel Back

- Contract: dispatch the actual Admin Support → Ticket admin control through the registered Ticket handler, verify Stats and Reply-template screens and their exact parent Back through Ticket/Menu handlers, and fail closed for public/bad origins before pending cleanup or report reads. Do not invoke ticket reply/note/ask/refund actions.
- Initial runner issue: the test reused a fixture helper calling `asyncio.run`, which stalled without output on this Windows runtime. The fixture callbacks use immediate inert coroutines; the test now uses a single-step no-I/O driver that fails if any callback yields.
- GREEN: `tests.test_admin_ticket_hub_navigation` ran `Ran 4 tests in 8.074s — OK`, covering module entry, nested/sibling/self navigation, exact Back origins, one ACK, public/invalid-origin denial before reads, and preservation of business controls without invoking them. Test-file `py_compile` exited 0; `git diff --check` exited 0 with only existing LF→CRLF notices.
- Finding/limits: no route defect reproduced; only the test harness changed. No real ticket, report database, reply, customer message, production data, provider, wallet, AutoPost, protected engine, merge, deploy, or restart. Consolidated CI and whole-goal closeout remain pending.

### S12.35.228 — Callback latency observer coverage and blind spots

- Contract: source-review the observer install point and registered inline callback wrapper; separate server callback time from ReplyKeyboard/MessageHandler and client-side display. Do not add telemetry or change shared routing without a reproducible gap or a matched slow route.
- Source evidence: `install_callback_latency_instrumentation` walks every registered `CallbackQueryHandler` and wraps it, then adds the observer in a later handler group. Its existing timing test asserts instrumentation is installed after the final direct callback registration. The fixed route key distinguishes only `menu|main` and `menu|main_profile`; other callbacks are aggregated by static prefix/handler as `unclassified`. It measures guards, handler duration and the shared `safe_edit_query_message` helper, not client rendering.
- Harness root cause: faulthandler showed `asyncio.run` blocked while Windows Proactor initialized its self-pipe in `socket._fallback_socketpair`/`accept`, before any callback fixture ran. The fixture callbacks are no-I/O, so the test-only `asyncio.run` calls now use `_run_no_io`, which fails if a coroutine unexpectedly yields.
- GREEN: `python.exe -B -S -m unittest tests.test_callback_dispatch_timing -v` completed `Ran 5 tests in 16.056s — OK`. This verifies source-extracted timing/logger fixtures and privacy assertions, not production latency or Telegram rendering.
- Finding/limits: no callback-observer coverage defect was reproduced for inline handlers. ReplyKeyboard/MessageHandler, Telegram transport before the update reaches the bot, and client rendering are outside this observer. The verified empty 24-hour sample has no per-route values and cannot explain the reported 2–3 second Account → Back delay. No instrumentation or product patch and no hardware recommendation are justified. A7 remains partial pending an exact click timestamp and matching event; if no event appears, runtime instrumentation/log delivery requires a separate read-only check.
- Finding/limits: no callback-observer coverage defect was reproduced for inline handlers. ReplyKeyboard/MessageHandler, Telegram transport before the update reaches the bot, and client rendering are outside this observer. The verified empty 24-hour sample has no per-route values and cannot explain the reported 2–3 second Account → Back delay. No instrumentation or product patch and no hardware recommendation are justified. A7 remains partial pending an exact click timestamp and matching event; if no event appears, runtime instrumentation/log delivery requires a separate read-only check.

### S12.35.229 — Origin-aware UI callback snapshots and timing retry

- Contract: keep emitted Back/child callback origins consistent across Support, Account, and Ticket category menus; fix only stale UI test expectations. Do not edit production handlers, engines, payment, provider, or AutoPost behavior.
- RED: `tests/test_p0_i18n_root_flow_copy.py` retained legacy callback expectations (`ticket|mine`, unscoped Account entry points, `back_lang`, and Ticket category `ticket|mine`) after the UI had been changed to preserve its immediate parent.
- Change: updated expected callbacks to the emitted origins (`ticket|mine|support/cskh_auto/admin_contact/premium/ticket_menu`, Account-scoped top-up/pricing/member/guide/support, and `back_lang|profile`). Added the source-copy test module to the existing small-navigation CI step.
- GREEN: the emitted public Support-child Back round-trip through the registered Ticket handler passed (1 test). All 29 source-only functions in `tests/test_p0_i18n_root_flow_copy.py` passed via direct invocation. Selected Account-origin routes also passed with no-I/O fixture drivers: pricing/detail Back and pricing-origin Top-up Back (2 tests), language picker (6 tests), and Credit Guide Back (3 tests). These fixtures use fake UI, preference, and payment seams only. The standard pytest module is wired into CI but has not run locally (bundled Python lacks pytest) or on GitHub yet.
- Validation limit: the normal Account pricing-back fixture invocation using `asyncio.run` stalled on Windows and was interrupted; that invocation is not counted. The selected pricing, language and Credit Guide reruns above used existing immediate/no-I/O fixture helpers instead. No top-up/payment or real preference write occurred. Other Account routes, normal Windows runner behavior, standard pytest and GitHub CI remain unverified. No production callback changed. No wallet, provider, customer message, production data, protected engine, deploy, or restart.
- A7: Owner reports Bảng giá rendered in under 1 second; this is a manual client observation without a precise tap time or correlated server event. Account → Back remains reported at 2–3 seconds. The 17:54 +07 `--grep` attempt returned exit 1 with empty stderr and was not counted because the reducer did not retain stdout; systemd documents that a no-match grep may legitimately return 1 ([journalctl issue #32422](https://github.com/systemd/systemd/issues/32422)). A corrected full-stream 24-hour aggregate at 18:04 +07 returned `JOURNALCTL_EXIT=0`, empty stderr, `EVENTS=0`, and `MALFORMED_MATCHING_LINES=0`, with no route rows. This is a verified empty timing window, not proof of speed or cause. A7 and overall audit remain partial; no delay cause or hardware recommendation is supported.

### S12.35.230 — Fresh callback timing aggregate and menu-phase boundary

- Contract: run the Owner-approved strict-host SSH read-only aggregates for the preceding 24 hours: first `callback_dispatch_timing`, then the separately approved `callback_latency` phase records for exact `menu|main` and `menu|main_video`. Return aggregate counts/averages/maximums and journalctl exit/stderr only; never return raw journal records, IDs, or payloads.
- Runtime result at 2026-10-10 18:13:58 +07: `JOURNALCTL_EXIT=0`, stderr empty, `MATCHING_EVENTS=0`, `MALFORMED_MATCHING_LINES=0`, `AGGREGATE_STATUS=VALID`; no group rows or raw records were emitted.
- Source boundary: `handle_menu_callback` separately logs `callback_latency` for exact `menu|main` and `menu|main_video`, with `pre_ack_ms`, `ack_ms`, `language_ms`, `cleanup_ms`, `build_ms`, `render_ms`, `handler_ms`, and `render_returned`. For `menu|main`, source awaits callback ACK before language lookup, pending-state cleanup, keyboard build and Telegram message edit. These post-ACK steps may affect screen-render time, but this is not a reproduced defect. Eight source-extracted assertions in `tests/test_menu_video_callback_timing.py` were directly invoked with an immediate no-I/O driver (public/admin root, draft preservation, render exception, unrelated root, and public/admin Back); all passed. The bundled Python lacks pytest, so this is not a standard pytest/CI pass. A first phase-aggregate attempt was discarded after a local regex sanity issue; after correcting and validating the parser against a representative route line, the exact same approved query scope was rerun.
- Phase aggregate at about 2026-10-10 18:41 +07: `JOURNALCTL_EXIT=0`, stderr empty, `MATCHING_EVENTS=0`, `MALFORMED_MATCHING_LINES=0`, `AGGREGATE_STATUS=VALID`; no route/role groups were returned. The earlier generic `callback_dispatch_timing` 24-hour query was also valid and empty.
- Finding/limits: both valid windows contain no callback event for these menu routes; this does not prove no click reached the bot, explain the reported 2–3s Account → Back delay, or attribute time to bot/Telegram/network/device/client. No code or runtime change is justified from an empty sample. A7 remains partial pending a click-correlated sample and client-side observation. No raw log, service change, deploy, or restart.

### S12.35.231 — Current-main literal callback-assignment registration pre-screen

- Contract: pre-screen string-literal `callback_data` assignments against literal `CallbackQueryHandler` regex patterns on the current local `origin/main` source and the audit worktree HEAD. Treat this only as a source inventory; do not claim dynamic controls or actual emitted-route behavior passed.
- Evidence: `origin/main` `5c38bd31c20f26f815e2f05b6419f4dd64afbba9` had 83 valid literal registration patterns, 3,139 static callback-data assignments, 1,300 unique literal values, and 494 dynamic-template assignments. The audit HEAD `b2a45cf72c8d11b838ce67101c6385128106e856` had 83 valid patterns, 3,120 static assignments, 1,306 unique literals, and 495 dynamic-template assignments. Neither source had an unmatched unique literal after inspecting two text-scan artifacts: `"|".join(...)` is a delimiter, and `callback_data = ""` is a local default, not an emitted control.
- Limits: text scan only; it does not prove the assignments are in emitted keyboards, verify conditional registration eligibility, cover computed/positional callback data or dynamic templates, dispatch handlers, or verify terminal behavior. The dynamic values remain open under A5. An earlier whole-file AST scan exceeded the local time budget and was interrupted; it is not counted. No source/runtime change or external side effect.

### S12.35.232 — Callback pre-ACK database-helper risk screen

- Contract: use bounded source scans to triage registered inline callback handlers for possible synchronous work before acknowledgement. Manually verify only safe customer/Admin navigation paths; keep engines, external calls, and action-capable behavior protected. Do not change ACK order from source suspicion alone.
- Evidence: 87 top-level `handle_*_callback` bodies were scanned. A narrow direct-token scan found only `get_internal_document` before a later `query.answer()`; a broad getter-name scan flagged 20 bodies, which is only a triage list because it is branch-agnostic and many hits are in-memory or protected routes. Manual review confirms: (1) Internal Archive `view`/`file` in `handle_internal_archive_callback` (`bot.py:234996`) performs the owner/status-scoped SQLite lookup before ACK, while missing/stale rows retain an alert; (2) `handle_ticket_callback` (`bot.py:141148`) calls SQLite-backed `get_user_language` (`bot.py:13727`) before ACK on callback entry, with another `get_support_ticket` SELECT (`bot.py:60821`) before ACK for valid summary/preview/customer-action/admin-detail/status paths; and (3) Document tool `main`/`back` in `handle_doc_tool_callback` (`bot.py:187110`) reads `get_user_language` before ACK. The helper opens SQLite and selects `user_language`.
- Account-delay boundary: the exact `menu|main_profile` Back uses `handle_menu_callback` (`bot.py:141867`), whose common callback ACK (`bot.py:142074`) occurs before `get_user_language` and before profile content/keyboard rendering. The Account renderer (`menu_text_main_profile_i18n`, `bot.py:136327`) subsequently performs synchronous account/member/package reads, including `get_user` and `user_package_rows` (`bot.py:60038`), so a server-side render wait remains possible; the approved 24-hour window had no events and cannot time it. This source order rules out only a late ACK at this handler, not delay in Telegram edit/client rendering or later data reads.
- Finding/limits: Archive, Ticket, and Document navigation contain source-visible SQLite work on pre-ACK paths; none is proven to account for any user's delay. Account Back ACKs before rendering, but its post-ACK reads are not isolated by the available sample. No product code changed. Do not attribute the 2–3s report to bot, Telegram, network, or device; no hardware purchase/repair recommendation is supported.
- Verification: read-only source inspection and bounded lexical scans only; no DB, document, ticket, provider, wallet, production data, real Telegram message, service mutation, merge, deploy, or restart. Route-correlated runtime evidence for Ticket/Archive/Document and Account screen-render timing remains open; A7 and whole-goal completion remain partial.

### S12.35.233 — Malformed Admin Ticket list offset fails closed

- Root cause: malformed Admin `ticket|al|<kind>|<offset>` reached `int(parts[3])` only after the generic ACK and `clear_support_ticket_pending`, raising `ValueError` and leaving the route without its intended stale-session response.
- Fix: after Admin authorization, `handle_ticket_callback` now validates exact route shape, the emitted list kinds (`new`, `high`, `refund`), and an ASCII decimal offset before generic ACK, pending cleanup, or list reads. Invalid input gets one stale-session alert; valid pagination is unchanged.
- RED: the test-first run reproduced the expected `ValueError` for `ticket|al|new|not-a-number` through the registered route before the guard was added.
- GREEN: `C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -S -m unittest tests.test_admin_ticket_hub_navigation -v` → `Ran 6 tests in 9.901s — OK`. The registered-handler regression covers malformed text, missing/empty offset, unsupported kind, negative and non-ASCII offsets; each must alert once with no edit, pending clear or list read. A valid `ticket|al|high|6` still ACKs once, clears pending once, reads `("high", 6)` and renders the list.
- Review: the existing `Admin Route Regressions` CI step includes `tests/test_admin_ticket_hub_navigation.py`; scoped `git diff --check -- bot.py tests/test_admin_ticket_hub_navigation.py docs/reports/TELEGRAM_SMALL_FLOW_AUDIT_CHECKLIST_20261006.md .agents/state/telegram-small-flow-audit-20261006.yaml` exited 0 (only the existing LF→CRLF warning for the test file). `C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m pytest tests/test_admin_ticket_hub_navigation.py -q -p no:cacheprovider` could not start (`No module named pytest`); no dependency was installed. `C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -B -m py_compile bot.py tests/test_admin_ticket_hub_navigation.py` did not return within 90 seconds and was interrupted, so it is NOT counted as a pass; the extracted registered-handler fixture loaded and exercised the changed handler successfully.
- Scope/limits: this spec's production delta is only the pre-ACK malformed-list guard. Other dirty changes in `bot.py` and the worktree belong to earlier WIP and were preserved. Tests use inert admin/pending/list seams; no production DB/ticket, customer message, wallet, provider, engine, AutoPost, merge, deploy, or restart. Whole-goal audit remains active.

### S12.35.234 — Admin Ticket pagination regression fixture compatibility

- Contract: keep the existing emitted Admin Ticket list → detail → note/Back regressions runnable against the current `handle_support_pending_input` dependencies; test-only fixture change, no business handler edits.
- Root cause: the fixture failed with `NameError: support_ticket_pending_key is not defined` before the note-input path. The handler's expiry guard also expects `USER_PENDING`; the fixture modeled only its separate in-memory `self.pending` store.
- Fix: the fixture now supplies an empty local `USER_PENDING` and the real key shape `support_ticket:<user_id>`. The tested admin-note step is not an expirable customer-input step, so the expiry guard stays inactive; existing ticket state remains in the fixture dictionary.
- RED/environment: the ordinary unittest invocation did not complete within about 60 seconds and was interrupted; its cause was not established, so it is NOT counted. Under the immediate no-I/O driver, the same module reproduced the fixture `NameError` in the save-note case while the two list/detail/Back cases passed.
- GREEN: reran the same 3 tests with the no-I/O driver (which fails on any coroutine yield): `Ran 3 tests in 8.519s — OK`. This includes the actual `support_admin_list_payload` page-6 emitter, detail callback, and originating-page Back through the extracted ticket handler; note mutation is only to the local fixture ticket dictionary.
- Scope/limits: test fixture only; existing `Admin Route Regressions` CI step includes this module. No production handler, database, customer message, wallet, provider, engine, AutoPost, merge, deploy, or restart changed. Live Telegram/client behavior and the wider A3/A5/A6/A7 audit remain open.

### S12.35.235 — Admin Ticket emitted pagination stays on the registered route

- Contract: use the real `support_admin_list_payload` emitter and actual `handle_ticket_callback` registration line. From the high-priority page at offset 6, emitted Previous/Next controls must be `ticket|al|high|0` and `ticket|al|high|12`; dispatching Next through the registered `^ticket\|` route must read the same filter at offset 12.
- Evidence: the test builds six inert fixture tickets, captures emitted controls, asserts the literal callbacks, validates them against the registration regex, and invokes the registered handler; fake `list_support_tickets` records `limit=6`, `high_priority=True`, offsets 6 then 12. It does not access production storage or execute ticket actions.
- GREEN: the immediate no-I/O runner (rejects any yielded coroutine) ran the module: `Ran 4 tests in 11.615s — OK`. Combined registered-route regressions for malformed Admin offsets, valid `high|6`, and the emitted pagination/note flow then passed: `Ran 10 tests in 20.372s — OK`.
- Finding: no dynamic pagination filter/offset or registration mismatch reproduced; no production-source change indicated. Mutation check: changing the expected emitted offset, filter, or registered pattern causes the literal/route assertion to fail.
- Scope/limits: test-only; `Admin Route Regressions` already includes this module. No production DB, customer message, wallet, provider, engine, AutoPost, merge, deploy, restart, or real Telegram action. This closes only the Admin Ticket emitted pagination slice; dynamic callbacks elsewhere and A3/A5/A6/A7 whole-goal closure remain open.

### S12.35.236 — Admin Marketing dynamic callback trail and parent Back

- Contract: from the actual Admin Marketing emitter, dispatch read-only child callbacks through the exact `^admin_growth\\|` registration. Verify both immediate Back and nested return trails (`channels → packages → ideas`, `calendar → campaigns`), malformed-trail rejection before report reads, public-user denial, and guide-only labeling. Do not run affiliate, campaign, publish, or package writes.
- Source review: `handle_admin_growth_callback` validates each trail against the explicit parent map, rejects unknown/extra parents before read seams, acknowledges before rendering, and composes nested Back callbacks. Callback registration is `bot.py:274850`; its menu/module fixture and exact route are covered by the CI Admin Route Regressions step.
- GREEN: `tests.test_admin_module_child_back_origin.AdminGrowthNavigationTests` ran with the immediate no-I/O fixture driver (which rejects any coroutine yield): `Ran 5 tests in 33.561s — OK`. Assertions cover actual emitted controls, exact registered-route dispatch, parent restoration, malformed callback rejection before reads, public denial, and callback byte bounds. The ordinary Windows unittest runner stalled before completing its first case and is not counted.
- Finding/limits: no callback/Back mismatch reproduced; no production source change. Read seams are fixture-local. This closes only the selected Admin Marketing navigation slice; it does not validate production Marketing reports/data, write operations, Telegram client rendering, whole-bot callback coverage, or live latency. A3/A5/A6/A7 remain partial.

### S12.35.237 — Fresh approved menu callback-latency aggregate

- Contract: one Owner-approved strict-host SSH query over the preceding 24 hours, filtered to `callback_latency` for exact `menu|main` and `menu|main_video`; return only counts, phase averages/maxima, and journalctl exit/stderr status. No raw records, identifiers, payloads, or runtime changes.
- Runtime result (2026-10-10, approximately 19:50 +07): `JOURNALCTL_EXIT=0`, stderr empty (`0` bytes), `MATCHING_EVENTS=0`, `MALFORMED_MATCHING_LINES=0`, `AGGREGATE_STATUS=VALID`; no route/role groups existed to aggregate.
- Fresh Owner-approved recheck (2026-10-10 20:38:38 +07): the sandbox attempt could not resolve the VPS hostname and did not reach the host. The approved strict-host retry completed: `JOURNALCTL_EXIT=0`, stderr empty (`0` bytes), `MATCHING_EVENTS=0`, `MALFORMED_MATCHING_LINES=0`, `AGGREGATE_STATUS=VALID`; no route/role groups existed. The parser emitted only aggregates.
- Finding/limits: this confirms an empty sampled window only. It cannot show that a click reached the bot, prove every button fast, explain the reported Account → Back 2–3 seconds, or attribute delay to server, Telegram transport, network, device, or client rendering. No code, hardware, service, or deploy change is justified; A7 and goal-wide closure remain pending a click-correlated event plus client observation.

### S12.35.238 — AI Operator command-guide Back returns to its category

- Contract: select an emitted command-guide control from each of the nine Admin AI Operator categories, dispatch it through the registered `^opmenu\\|` handler, and require Back to reopen the exact category. Keep all displayed slash/API instructions inert; do not run Operator, publishing, API, wallet, provider, or production actions.
- RED: from emitted `operator_category_keyboard("cat_control")` → “System status”, the registered handler returned Back=`opmenu|root` instead of the emitting category. The focused assertion failed for that exact destination mismatch.
- Root cause/minimal fix: category guide buttons discarded their parent category (`opmenu|<action>`), and the guide renderer unconditionally emitted `opmenu|root`. Category-emitted guide callbacks now carry `opmenu|<action>|<category>` and the guide Back targets that category. Root category entry and legacy root-origin guide callbacks retain their existing behavior; no command execution path changed.
- GREEN: all emitted command-guide controls across the nine categories were dispatched through the production handler extracted with the actual `^opmenu\\|` registration. The regression checks one ACK, exact category Back, and callback length ≤64 bytes. `OperatorMenuCallbackSingleAckTests`: `Ran 4 tests in 1.370s — OK` using an immediate no-I/O driver; all route, render, and command seams remained local fakes. The module is added to Admin Route Regressions CI.
- Limits: local callback/UI evidence only; no Operator command, schedule, publishing, API, wallet, provider, or production data was touched. Telegram-client layout and live latency remain unmeasured. No protected product engine or AutoPost handler was changed. Goal-wide A3/A5/A6/A7 and final CI/delivery gates remain pending.

### S12.35.239 — AI Operator root Dashboard label matches its destination

- Contract: dispatch the actual root-emitted `opmenu|dashboard` through the operator callback; the button label must describe the screen's real behavior (showing `/operator_dashboard` instructions), not imply that the dashboard itself opens. Preserve callback data, command text, Back route, and all operational handlers.
- RED: the emitted label was `📊 Dashboard`, while the registered handler rendered the command-only guide. The focused behavior assertion failed because the label did not start with the existing guide-label convention.
- Minimal fix: changed only the emitted label to `📘 Hướng dẫn Dashboard`; callback `opmenu|dashboard`, instruction text, handler, and Back remain unchanged.
- GREEN: the complete `OperatorMenuCallbackSingleAckTests` class passed under the immediate no-I/O fixture driver: `Ran 5 tests in 2.264s — OK`. It includes the new root-label/real-guide assertion plus all nine category guide Back routes, one-ACK checks, admin denial, registration pattern and callback-size assertions. The module is already included in Admin Route Regressions CI.
- Limits: source/fixture UI proof only. No Operator command, report, production data, publishing, API, wallet, provider, AutoPost, or product-engine action was executed. Manual Telegram visual/latency QA and consolidated CI remain pending.

### S12.35.240 — Publish approval guide label does not imply action completion

- Contract: from the emitted Admin Operator `cat_publish` keyboard, dispatch `approvepublish` through the registered callback. The UI label must make clear it opens `/approve_publish` instructions; callback, guide text and exact category Back stay unchanged. Do not approve, queue, publish or mutate a job.
- RED: the emitted control was labeled `✅ Approve publish`, but the actual handler only rendered a manual command/API guide. The focused assertion failed on the label before any production action.
- Minimal fix: changed only that control label to `📘 Hướng dẫn duyệt bài đăng`; the existing callback and command-guide renderer are unchanged.
- GREEN: `OperatorMenuCallbackSingleAckTests`: `Ran 6 tests in 2.109s — OK` with immediate no-I/O fixture dispatch. The test verifies the emitted `opmenu|approvepublish|cat_publish` control, one ACK, guide text, and Back=`opmenu|cat_publish`; the whole module also rechecks Dashboard label and all nine category Back paths. This test module is in Admin Route Regressions CI.
- Limits: fixture/UI evidence only. No job data, wallet, provider, schedule, approval, publish, AutoPost worker, or product engine was accessed. Live Telegram layout/latency and consolidated CI remain pending.

### S12.35.241 — Operator category prompt describes command-guide behavior

- Contract: open an emitted Admin Operator category through the registered route; the screen prompt must accurately tell the admin its child controls display command guidance, not perform the operation. Preserve category title, callback values, ACK count, menu, and all commands.
- RED: the registered `cat_control` callback rendered “Chọn mục cần thao tác” although every child callback routes to the command-snippet renderer. The focused screen-output assertion failed on this copy.
- Minimal fix: changed the shared category prompt to “Chọn lệnh cần xem hướng dẫn”; no callback, command, router, or action behavior changed.
- GREEN: `OperatorMenuCallbackSingleAckTests`: `Ran 6 tests in 2.610s — OK` via the immediate no-I/O driver. The actual category callback now returns the expected prompt; the same module reruns all emitted category-guide Back, root Dashboard, Publish-guide, ACK and admin-denial checks. It is included in Admin Route Regressions CI.
- Limits: fixture-only copy/route evidence. No Operator command or production operation was invoked. Live Telegram layout/latency and consolidated CI remain pending.

### S12.35.242 — “Mark published” identifies its guide-only destination

- Contract: dispatch the emitted Admin Operator `cat_publish` `markpublished` control through the registered `^opmenu\\|` handler. The label must say it opens instructions; preserve callback data, `/mark_published` guide, one ACK, and exact category Back. Do not mark or publish any job.
- RED: the emitted label `✅ Mark published` failed the guide-label assertion while the handler rendered only `/mark_published` instructions.
- Minimal fix: changed only the label to `📘 Hướng dẫn đánh dấu đã đăng`; no handler, callback, job, or publishing behavior changed.
- GREEN: the full `OperatorMenuCallbackSingleAckTests` suite passed: `Ran 7 tests in 3.045s — OK`. It exercises the emitted control through the extracted registered handler, confirms one ACK, guide text, exact Back, and existing route/category checks. Test-source compile and scoped `git diff --check` both exited 0; the module is already in Admin Route Regressions CI.
- Limits: fixture/UI evidence only. No job data, publish operation, wallet, provider, AutoPost, or protected engine was accessed. Consolidated CI, client rendering, and live latency remain pending.

### S12.35.243 — “Publisher run” identifies its guide-only destination

- Contract: dispatch the emitted Admin Operator `cat_publish` `publisherrun` control through the registered `^opmenu\\|` handler. The label must say it opens instructions; preserve callback data, `/publisher_run` guide, one ACK, and exact category Back. Do not run Publisher or call any API/provider.
- RED: the emitted label `▶️ Publisher run` failed the guide-label assertion although the registered handler only displayed the `/publisher_run` command/API instructions.
- Minimal fix: changed only the label to `📘 Hướng dẫn chạy Publisher`; no callback, handler, publisher, worker, or publishing behavior changed.
- GREEN: `OperatorMenuCallbackSingleAckTests`: `Ran 8 tests in 3.350s — OK`. The emitted control was dispatched through the extracted registered handler; the test confirms one ACK, guide text, and exact `cat_publish` Back. Test-source compile and scoped `git diff --check` exited 0; the module is already in Admin Route Regressions CI.
- Limits: local fixture/UI evidence only. No job, queue, publication, API, provider, wallet, AutoPost, or product engine was accessed. Consolidated CI, live rendering, and latency remain pending.

### S12.35.244 — “Publisher status” does not imply live status lookup

- Contract: dispatch the emitted Admin Operator `cat_publish` `publisherstatus` control through the registered `^opmenu\\|` handler. The label must identify a guide-only destination; preserve callback, `/publisher_status` guide, one ACK, and exact category Back. Do not query Publisher API or queue state.
- RED: the label `📡 Publisher status` suggested a live status screen, but the handler only returned `/publisher_status` instructions; the focused guide-label assertion failed.
- Minimal fix: changed only the label to `📘 Hướng dẫn trạng thái Publisher`; no status query, API, worker, or publishing logic changed.
- GREEN: `OperatorMenuCallbackSingleAckTests`: `Ran 9 tests in 3.992s — OK`. The emitted control passed through the extracted registered handler; test checked one ACK, guide text, and exact `cat_publish` Back. Test-source compile and scoped `git diff --check` exited 0; the test module is in Admin Route Regressions CI.
- Limits: local fixture/UI evidence only. No API/provider, job, queue, wallet, production data, AutoPost, or protected engine was accessed. Consolidated CI, live UI, and latency remain pending.

### S12.35.245 — “Publish queue” identifies its guide-only destination

- Contract: dispatch the emitted Admin Operator `cat_publish` `publishqueue` control through the registered `^opmenu\\|` handler. Label must make clear it opens queue instructions; preserve callback, `/publish_queue` guide, one ACK, and exact category Back. Do not read or mutate any queue.
- RED: emitted label `📮 Publish queue` failed the guide-label assertion while the handler returned only the `/publish_queue` and related command instructions.
- Minimal fix: changed only the label to `📘 Hướng dẫn hàng đợi đăng bài`; no queue query, command, API, or publishing behavior changed.
- GREEN: `OperatorMenuCallbackSingleAckTests`: `Ran 10 tests in 4.838s — OK`. The emitted control was dispatched through the registered handler fixture; one ACK, guide text, and category Back were verified. Test-source compile and scoped `git diff --check` exited 0; module is in Admin Route Regressions CI.
- Limits: local fixture/UI evidence only. No queue, API, provider, wallet, production data, AutoPost, or product engine was accessed. Consolidated CI, live rendering, and latency remain pending.

### S12.35.246 — “Publisher handoff” identifies its guide-only destination

- Contract: dispatch the emitted Admin Operator `cat_publish` `publisherhandoff` control through the registered `^opmenu\\|` handler. Label must say it opens instructions; preserve callback, `/publisher_handoff` text, one ACK, and category Back. Do not hand off a queue or execute Publisher commands.
- RED: `🤖 Publisher handoff` failed the guide-label assertion; the handler only rendered the `/publisher_handoff` command/API guide.
- Minimal fix: changed only the label to `📘 Hướng dẫn bàn giao Publisher`; no handoff, queue, API, or worker behavior changed.
- GREEN: `OperatorMenuCallbackSingleAckTests`: `Ran 11 tests in 5.299s — OK`. The emitted control was dispatched through the registered handler fixture and checked for one ACK, guide text, and exact `cat_publish` Back. Test-source compile and scoped `git diff --check` exited 0; module is already listed in Admin Route Regressions CI.
- Limits: fixture/UI evidence only. No queue, job, Publisher command/API, provider, wallet, production data, AutoPost, or protected engine was accessed. Consolidated CI and live latency remain pending.

### S12.35.247 — “Publish cockpit” identifies its guide-only destination

- Contract: dispatch the emitted Admin Operator `cat_publish` `publishcockpit` control through the registered `^opmenu\\|` handler. Label must state that it opens a guide, not a live cockpit; preserve callback, `/publish_cockpit` text, one ACK, and exact category Back. Do not read or mutate publish data.
- RED: the emitted label `🎛 Publish cockpit` failed the guide-label assertion, while the handler only rendered `/publish_cockpit` instructions.
- Minimal fix: changed only the label to `📘 Hướng dẫn bảng điều khiển đăng bài`; no cockpit, API, queue, or publishing behavior changed.
- GREEN: `OperatorMenuCallbackSingleAckTests`: `Ran 12 tests in 5.216s — OK`. The emitted callback traversed the registered handler fixture; one ACK, guide text, and category Back were asserted. Test-source compile and scoped `git diff --check` exited 0; module remains in Admin Route Regressions CI.
- Limits: local UI fixture evidence only. No publish data, queue, API, provider, wallet, AutoPost, or protected engine was accessed. Consolidated CI, live rendering, and latency remain pending.

### S12.35.248 — “Publish readiness” identifies its guide-only destination

- Contract: dispatch the emitted Admin Operator `cat_publish` `readiness` control through the registered `^opmenu\\|` handler. Label must say the callback opens instructions, not a live readiness check; preserve callback, `/publish_readiness` text, one ACK, and exact category Back. Do not inspect or change channel readiness.
- RED: `🧪 Publish readiness` failed the guide-label assertion while the handler rendered only `/publish_readiness` and channel-configuration instructions.
- Minimal fix: changed only the `cat_publish` label to `📘 Hướng dẫn kiểm tra điều kiện đăng`; no readiness/API/AutoPost logic changed.
- GREEN: `OperatorMenuCallbackSingleAckTests`: `Ran 13 tests in 5.694s — OK`; fresh local rerun on 2026-10-10: `Ran 13 tests in 5.341s — OK`. The emitted control went through the registered route fixture; one ACK, guide text, and category Back were checked. Test-source compile and scoped `git diff --check` exited 0; the module is in Admin Route Regressions CI.
- Limits: local UI fixture evidence only. No channel, API, provider, wallet, production data, AutoPost, or protected engine was accessed. Consolidated CI and live timing remain pending.

### S12.35.249 — Whole-file syntax gate attempt (not verified)

- Contract: run the required whole-file `py_compile bot.py` gate on the current WIP; distinguish a syntax failure from an environment/runtime timeout. Do not change source to work around a slow verifier.
- Evidence: system `python` is not on PATH. The bundled Python starts (`python -S -c ...` returned `PYTHON_STARTUP_OK`). `bot.py` is 15,280,769 bytes / 285,001 lines. Two compile attempts produced no terminal compile result; the diagnostic attempt's watchdog showed Python in `importlib._bootstrap_external.source_to_code` / `py_compile.compile` after 45 seconds and was still active after five minutes, then only that local verifier was interrupted.
- Result: `NOT_VERIFIED` — neither PASS nor a syntax error. Full-source compilation remains a required closeout gate; no source code was changed because of this runtime duration.
- Scope: local read/compile only. No test import of the full bot, production data, provider, wallet, Telegram, AutoPost, protected engine, merge, deploy, or restart.

### S12.35.250 — Current safe-navigation regression recheck

- Fresh Admin recheck on 2026-10-10: Admin Ticket hub passed 6 tests in 9.582s; Admin Overview/report passed 3 in 4.957s; Admin/customer root-menu safe-flow suite passed 50 tests in 48.397s.
- The root-suite rerun required only a test-fixture adjustment: its authorization stub now returns True immediately from an async function instead of yielding with asyncio.sleep(0), because the no-I/O fixture runner deliberately fails on yielded coroutines. No production code changed for this harness correction.
- These results are scoped local fixture evidence. They do not close Admin actions globally, full callback coverage, Telegram-client visuals, all-button latency, consolidated CI, or whole-goal completion.

### S12.35.251 — Current worktree protected-source hunk review

- Contract: compare the current local working diff with its checked-out HEAD, identify every production-source hunk, and verify this UI/navigation batch does not edit protected Product Video/Edit/SubDub/Voice/Music engines or service/provider files. Do not infer that this is the final main/runtime comparison.
- Evidence: worktree branch audit/storage-addon-expiry-20261009 at HEAD b2a45cf72c8d11b838ce67101c6385128106e856. The changed-path inventory contains bot.py, tests, CI, checklist/evidence and state files; no services/provider source path is modified. The bot.py hunk headers are limited to Package/Pricing navigation, Support/Ticket/Feedback/Document small-flow handlers, Admin Operator/Archive UI, AI Chat consent replay guard, and callback timing labels. No hunk is inside a Product Video, Edit, SubDub, Voice or Music engine handler.
- Result: local working-tree scope check finds no protected engine/service edit in this batch. This is only a comparison to the local HEAD; main has diverged protected commits and the final main/runtime protected-source comparison remains open.
- Limits: read-only diff review; no source edit, merge, push, deploy or restart. Pending working-tree changes remain preserved.

### S12.35.252 — Archive View/File focused rerun in local Windows runner

- Contract: re-run only emitted Archive View, File, and stale/malformed-record regressions against the registered callback; require route rendering/send fixture, exactly one ACK, and preserved stale alerts. No real document access or send.
- Evidence: standard unittest emitted the first test name but no assertion/result for 180 seconds; one Selector-policy retry emitted the first test name but no result for 125 seconds. A timed stack snapshot showed the standard run blocked in Windows Proactor self-pipe setup (socket.accept/socketpair) before entering the test method's handler dispatch. Both stuck sessions were cancelled. Then the three exact test methods were invoked directly with the existing immediate no-I/O fixture driver: Archive View render, Archive File fake-send, and malformed/stale alert cases all completed and passed.
- Result: focused direct no-I/O assertions GREEN; standard unittest/pytest execution remains NOT_VERIFIED on this Windows runner. This is not a consolidated CI result and not live latency evidence.
- Limits: no bot code change, production database/document access, Telegram send, provider, wallet, AutoPost, protected engine, merge, deploy or restart. A7 and whole-goal completion remain partial.

### S12.35.253 — Package detail origin callback byte limits

- Contract: follow Account Pricing → Packages → all package groups → monthly/Combo details through the registered Package/Combo handler; every callback must be ≤64 UTF-8 bytes and group/detail/Large Order Back must restore the exact origin. Do not dispatch Large Order or create an order request.
- RED: the Combo detail Large Order callback was 74 bytes; the all-origin matrix found a 65-byte Combo detail selector and Large Order result Back, plus a 66-byte Prompt/Workflow group Large Order callback. These exceeded Telegram's 64-byte callback-data limit.
- Minimal fix: encode allowlisted origin suffixes as one character on package group/detail selectors and origin-bearing Large Order callbacks/Backs, then decode at the registered routes. Parent-origin Back remains exact; purchase/action routing and other engines remain untouched. One-character package codes are not interpreted as origins.
- GREEN: the focused registered-handler test passed `Ran 1 test in 3.042s — OK` across all nine origin tokens, all seven task groups plus Combo (63 group screens), and both monthly/Combo detail paths (18 detail cases). Fresh rerun on 2026-10-10 passed the exact test in `3.912s — OK`; test-file `py_compile` exited `0` and full-worktree `git diff --check` exited `0` (only existing LF→CRLF warnings). Every emitted callback on Package home/group/detail and Large Order result Back is ≤64 bytes. It dispatches group/detail Back controls and confirms identical screen controls without dispatching the Large Order action.
- Broader module recheck: running the whole `tests.test_pkgcombo_navigation_registered_callback` module emitted `test_account_catalog_packages_back_preserves_account_catalog_origin` but produced no assertion/result within ~30 seconds and was interrupted. The separate legacy group/detail integration `test_account_pricing_package_group_and_detail_back_preserve_full_origin` also previously emitted no result within 60 seconds. Both broad rechecks remain NOT_VERIFIED in this Windows runner, not product assertion failures; the focused 18-case registered-handler matrix is the verified evidence for this spec.
- Limits: fixture/source route evidence only; no real order request, DB, wallet, provider, production Telegram action, or protected engine. Full `bot.py` compile remains NOT_VERIFIED, consolidated CI and final main/runtime comparison remain pending; no merge, deploy or restart.

### A7 — Approved 24-hour menu callback phase aggregate (2026-10-10 22:01 +07)

- Contract: use the single Owner-approved read-only SSH query for `callback_latency` on exact `menu|main` and `menu|main_video`; emit only route/role counts and avg/max for pre-ACK, ACK, language, cleanup, build, render and handler phases, plus journalctl exit/stderr status.
- Runtime output: `JOURNALCTL_EXIT=0`, `AGGREGATE_EXIT=0`, `JOURNALCTL_STDERR_BYTES=0`, `MATCHING_EVENTS=0`, `MALFORMED_MATCHING_LINES=0`; therefore there were no route/role groups in the sampled 24 hours. No raw journal lines were returned.
- Tool-wrapper note: the remote Bash wrapper then returned SSH exit 2 because PowerShell CRLF remained on its final `exit` argument (`0\r`). The already-emitted journalctl and aggregate statuses are explicitly 0; the single-query approval was not used for a retry.
- Finding/limits: an empty window does not prove buttons are fast or that a tap reached the bot, and cannot attribute the reported 2–3s delay to bot, Telegram, network, device, or client rendering. A7 remains unresolved pending a click-correlated event plus client measurement; no runtime change is indicated by this sample.

### A7 — Fresh approved 24-hour menu callback phase aggregate (2026-10-10 ~22:21 +07)

- Contract: one newly approved, strict-host, read-only SSH query for `callback_latency` on exact `menu|main` and `menu|main_video`; return only route/role count and phase averages/maxima (`pre_ack_ms`, `ack_ms`, `language_ms`, `cleanup_ms`, `build_ms`, `render_ms`, `handler_ms`) plus journalctl/aggregator exit and stderr status.
- Runtime output: `SSH_EXIT=0`, `JOURNALCTL_EXIT=0`, `JOURNALCTL_STDERR_BYTES=0`, `AGGREGATE_EXIT=0`, `MATCHING_EVENTS=0`, `MALFORMED_MATCHING_LINES=0`; no route/role rows existed. The reducer emitted no raw journal records, identifiers, or payloads.
- Finding/limits: this is a valid empty 24-hour sample, not proof that a tap reached the bot or that buttons are fast. It cannot correlate or explain the reported Account → Back 2–3s delay, nor distinguish server work from Telegram transport, network, device, or client rendering. A7 remains unresolved pending a precisely timed click with a matching event and client measurement; no runtime change is indicated.
- Side effects: read-only journal aggregation only; no production writes, Telegram send, provider call, wallet operation, service change, deploy, or restart.

### S12.35.254 — Current GitHub-main callback/protected-delta refresh (2026-10-10 22:30 +07)

- Contract: read the authoritative GitHub main SHA and compare the upstream delta with this audit HEAD for callback/CI changes; identify protected-source deltas without rebasing, merging, deploying, or restarting.
- Evidence: `gh api repos/manhtoangreensky-wq/bot/commits/main --jq .sha` returned `5c38bd31c20f26f815e2f05b6419f4dd64afbba9`. `git rev-list --left-right --count HEAD...origin/main` returned `1 5`. Upstream commits are #1416–#1420: #1417 Web Image runtime, #1418–#1420 Product Video/provider. `git diff --exit-code -G 'CallbackQueryHandler|callback_data|callback_data=|async def handle_.*callback|install_callback_latency_instrumentation' HEAD..origin/main -- bot.py .github/workflows/ci-main.yml` exited `0`, so those five commits contain no matching callback/CI-source hunk.
- Hygiene observation: `git diff --check HEAD..origin/main` exited `1` only for trailing whitespace at lines 522 and 525 of upstream `tests/test_p0_video_r05a_kling_v3_15s_stall_budget.py`. This is within protected Product Video work, outside this audit patch, and was not changed.
- Result/limits: no new callback issue was found in the upstream delta. Protected source is still present, so no rebase/merge/deploy and no runtime SHA/service claim; the working tree remains unchanged by this comparison.

### S12.35.255 — Package confirmation callback route

- Contract: build the auto-checkout confirmation keyboard through the registered package-detail route, dispatch its emitted `pkgbuy|confirm|…` control through the exact registered purchase callback with `start_package_purchase` replaced by an inert seam, then dispatch its emitted Back through the registered package handler and assert return to the same group.
- Safety boundary: this verifies callback wiring and screen ancestry only. It must not call the production purchase function, create an order, contact PayOS/provider, read/write DB, alter Xu, or send Telegram messages. `bot.py` and payment/wallet implementations are protected; allowed changes are the focused test, checklist, and durable state.
- Harness correction: the first assertion used regex `fullmatch`, although the actual registered Telegram pattern is a prefix (`^pkgbuy\|`). The test now uses `search`, matching handler dispatch semantics; this was a test assertion issue, not a product failure.
- GREEN: 3 focused methods ran in `13.004s — OK`: emitted confirmation → exact `pkgbuy` registration → inert checkout seam; Back → same group; package callback-byte matrix; and emitted detail Back regression. The new test checks one ACK, exact user/type/code/message seam arguments, callback ≤64 bytes, and returned group screen. Test-file `py_compile` exited `0`; `git diff --check` exited `0` with only existing LF→CRLF warnings.
- Limits: no `start_package_purchase` production body, order creation, PayOS, DB, wallet/Xu, provider, real Telegram, or product engine ran. This proves only the confirmation route/UI boundary; actual purchase/checkout completion and the handler's other branches remain untested. The test module is already included in `.github/workflows/ci-main.yml`; consolidated CI is still pending.

### A7 — Fresh approved 24-hour menu callback phase aggregate (2026-10-10 22:40 +07)

- Contract: run the newly approved strict-host, read-only SSH query for `callback_latency` on exact `menu|main` and `menu|main_video`; return only route/role counts and avg/max for `pre_ack_ms`, `ack_ms`, `language_ms`, `cleanup_ms`, `build_ms`, `render_ms`, and `handler_ms`, plus journalctl/aggregator exit and stderr status.
- Runtime output: `SSH_EXIT=0`, `JOURNALCTL_EXIT=0`, `JOURNALCTL_STDERR_BYTES=0`, `AGGREGATE_EXIT=0`, `MATCHING_EVENTS=0`, `MALFORMED_MATCHING_LINES=0`; there were no route/role groups to report. No raw journal records, identifiers, or payloads were emitted.
- Finding/limits: this is a valid empty 24-hour sample, not proof that a tap reached the bot or that the buttons are fast. It does not explain the reported 2–3 second Account → Back delay or distinguish bot work from Telegram transport, network, device, or client rendering. A7 remains open pending a precisely timed click with a matching event and client-side measurement; no runtime change is justified by this sample.
- Side effects: one read-only aggregate query only; no production writes, provider or wallet operations, Telegram send, service change, deploy, or restart.

### S12.35.256 — Legacy public `buy_plan|` callback fallback

- Contract: verify that current public pricing/package keyboards do not emit `buy_plan|` controls, then dispatch one stale public callback through the exact registered handler. Require one ACK, the current public package list, and no call to `start_plan_purchase`. Do not enter the admin or checkout branch.
- Source finding: `handle_buy_plan_callback` remains registered, but the repository has no current `buy_plan|` button emitter. It is a legacy/stale callback route, not a currently reachable pricing button.
- GREEN: the focused registered-handler test passed `Ran 1 test in 6.261s — OK`. It asserted the exact registration, one ACK, public package destinations, and zero calls to an inert purchase seam. `tests/test_profile_pricing_back_origin.py` is already run by the Account Pricing Back CI step.
- Result: no product defect reproduced, so `bot.py` was not changed. Keep the handler as a safe fallback for stale keyboards; this evidence does not claim admin purchase or checkout behavior is tested.
- Limits: no order, PayOS, wallet/Xu, DB, provider, production Telegram send, or protected engine operation. Consolidated CI and the broader callback audit remain open.

### S12.35.257 — A7 timing event-name/source reconciliation

- Contract: reconcile the approved menu-phase query with the current instrumentation source and focused regression. Keep the general dispatch event separate from the root-menu phase event; a zero-match query must not be reported as proof of a fast tap.
- Source: the generic registered-handler observer emits `callback_dispatch_timing` with bounded route/handler labels and guard, handler, render-helper, and dispatch durations. It maps `menu|main_profile` to fixed `route_key=account_root` and `menu|main` to `route_key=main_home` without logging callback payload; the focused timing test covers the Account label. Only the exact `menu|main` and `menu|main_video` branches emit the separate `callback_latency` phase event (`pre_ack_ms`, `ack_ms`, `language_ms`, `cleanup_ms`, `build_ms`, `render_ms`, `handler_ms`).
- Runtime evidence: the already approved strict-host 24-hour aggregate for `callback_latency` on those exact menu routes returned `SSH_EXIT=0`, `JOURNALCTL_EXIT=0`, `AGGREGATE_EXIT=0`, empty stderr, and `MATCHING_EVENTS=0`. It is a valid empty sample, not a matched tap. The earlier `callback_dispatch_timing` sample (one generic menu event and three Pricing events) is a distinct event family/window and cannot be joined to the user's click.
- GREEN: `python -m unittest -v tests.test_callback_dispatch_timing` — `Ran 5 tests in 18.483s — OK`; checks observer installation after registrations, anonymous handler timing, shared render timing, and guard/error cleanup. It does not establish live callback latency.
- Result/limits: no source defect reproduced and no code change made. The approved `callback_latency` sample covers `menu|main`/`menu|main_video`, not `account_root`; the earlier generic `callback_dispatch_timing` row `menu/unclassified` cannot be attributed to Account Back. A7 remains open until a click has a precise +07 timestamp, client-observed latency, and matching server event. No network/device/hardware cause is inferred. The `bot.py` whole-file `py_compile` attempt returned no result after >65 seconds and was interrupted; record as NOT_VERIFIED, not as a syntax failure or pass. Focused callback tests passed.
- Side effects: source and local tests only; no production query retry, Telegram send, provider/wallet action, merge, deploy, or restart.

### S12.35.258 — Account language picker emitted-locale selection

- Contract: dispatch every locale button emitted by the Account language picker through the exact registered language callback; assert one ACK, correct scoped callback, callback length ≤64 bytes, one fixture preference update and usage event, and return to Account.
- GREEN: selected `test_all_emitted_locales_preserve_context_payload_and_single_update` passed with an immediate no-I/O driver — `Ran 1 test in 11.139s — OK`. The test derives the expected set from `USER_LANGUAGE_ORDER`, builds the actual picker, matches the registered language pattern, and executes the handler. Preference and usage seams are in-memory only.
- Harness note: the ordinary unittest invocation stalled before the first test completed in this Windows environment and was interrupted. An initial temporary driver referenced the fixture Query at the wrong namespace and failed before product assertions; correcting that adapter allowed the focused case to pass. No test or production source was changed for the harness.
- Result/limits: no mismatch reproduced for Account-origin locale selection. This does not verify persisted preference writes, broadcast behavior, other language branches, expiry/repeat behavior, Telegram rendering, or live latency. No database or user preference was changed.
- Side effects: offline callback fixture only; no real Telegram send, provider/wallet operation, engine, merge, deploy, or restart.

### S12.35.259 — Free Tools Voice/SubDub script-helper entry and Back

- Contract: use the actual Free Tools keyboard's “Script voice/SubDub” control, dispatch it through the exact registered `freehub|` handler, and verify the prompt screen, actor-scoped pending state, one ACK, and emitted Back/Home. Stop before choosing/submitting a prompt or entering a product engine.
- GREEN: extended the existing safe-navigation fixture; its actual `freehub|hook` emitter is confirmed in the root keyboard, then the registered handler renders `hook_script` suggestions at offset 0. Back returns to Free Tools, Home points to Main, Back clears only this user's pending marker, and a second user's marker remains. Immediate no-I/O runner: `Ran 1 test in 0.481s — OK`. The test module is already in `.github/workflows/ci-main.yml`.
- Result/limits: no callback mismatch reproduced. This verifies only the free prompt-helper UI, not Voice/SubDub engine behavior or resulting scripts. No prompt selection/submission, provider, job, wallet, DB, or real Telegram operation; no production code changed.

### S12.35.260 — Memory delete cancel and confirmation callback boundaries

- Contract: dispatch the Memory delete picker and its emitted Confirm/Cancel controls through the registered `handle_memory_callback`; Cancel must restore the exact delete picker and note choice, stale confirmation must not archive, and a fresh valid confirmation must update only a fixture record once. Never open the production database.
- Evidence: selected methods `test_memory_delete_picker_emits_a_cancel_route_to_its_parent` and `test_stale_memory_delete_confirmation_cannot_archive_reconfirmed_note` in the existing CI-listed root-navigation test. Standard `unittest` emitted the first method name but no result within 30 seconds; the same two assertions then ran with the immediate no-I/O driver: `Ran 2 focused no-I/O Memory callback checks — OK`. Each dispatch asserts exactly one callback ACK. The cancellation fixture forbids DB access; confirmation uses an in-memory fake connection. Stale confirmation produced no archive update/event; fresh confirmation produced exactly one fixture update/event.
- Result/limits: no Memory callback defect reproduced, so no production code changed. This is registered-route fixture evidence only; not live client rendering or latency evidence, and not a consolidated CI result.
- Side effects: no production DB/data, wallet, provider, job, real Telegram message, merge, deploy, or restart.

### A7 — Fresh approved 24-hour menu callback phase aggregate (2026-10-10 23:37 +07)

- Contract: run the newly approved, read-only 24-hour `callback_latency` aggregate for exact `menu|main` and `menu|main_video`; emit only route/role counts and per-phase count/average/maximum for `pre_ack_ms`, `ack_ms`, `language_ms`, `cleanup_ms`, `build_ms`, `render_ms`, and `handler_ms`, plus journalctl/aggregator status. No raw logs, IDs, or payloads.
- Runtime output: `JOURNALCTL_EXIT=0`, `JOURNALCTL_STDERR_BYTES=0`, `AGGREGATE_EXIT=0`, `MATCHING_EVENTS=0`, `MALFORMED_MATCHING_LINES=0`; no route/role groups existed. The SSH wrapper then returned `SSH_EXIT=127` because a trailing CRLF was parsed by remote Bash (`$'\\r': command not found`) after the aggregate had completed.
- Finding/limits: this is an empty 24-hour sample, not proof that a tap arrived or that either button is fast, and it does not explain Account → Back 2–3s. The aggregation itself completed with journalctl exit 0 and no stderr, but the wrapper exit was nonzero and is recorded rather than hidden. A7 remains unresolved pending a click-correlated event and client-side measurement; no runtime change is justified.
- Side effects: one approved read-only journal aggregate only; no raw records, production writes, Telegram send, provider/wallet action, service change, deploy, or restart.

### A7 — Account → Back dispatch aggregate and source path (2026-10-10 23:49 +07)

- Contract: use the separately approved read-only 24-hour `callback_dispatch_timing` aggregate for exact `route_key=account_root`; return only count/avg/max of `guard_ms`, `handler_ms`, `render_helper_ms`, and `dispatch_ms`, plus command status. Do not emit raw records, IDs, or payloads.
- Runtime output: `SSH_EXIT=0`, `JOURNALCTL_EXIT=0`, `JOURNALCTL_STDERR_BYTES=0`, `AGGREGATE_EXIT=0`, `MATCHING_EVENTS=0`, `MALFORMED_METRIC_FIELDS=0`; no phase rows existed.
- Source finding: Account → Back is acknowledged before user-language lookup and pending cleanup. The subsequent Account render synchronously calls `get_user()` for credits, `get_role_badge()` (which may call `get_member_profile()`), and `user_package_account_short_text()` → `user_package_rows()` (lazy expiry plus a package query) before editing the message. These are plausible server-side work contributors, not proof of the reported 2–3s delay; no cache/read-path change is justified without a correlated timing sample.
- Finding/limits: the empty aggregate does not show whether a click reached the bot and cannot distinguish handler/database time from Telegram, network, device, or client rendering. A7 stays open until a click timestamp/client duration matches a route event. No runtime change is justified by this sample.
- Side effects: one approved read-only aggregate and offline source inspection only; no raw records, production DB/data change, Telegram send, provider/wallet operation, service change, deploy, or restart.

### S12.35.261 — Current WIP test-selection closeout check

- Contract: compare every tracked and untracked dirty Python test file with the test commands in `.github/workflows/ci-main.yml`. Acceptance is that each dirty test file is named by a CI command; this is a selection audit only, not a test or CI result.
- Evidence: the S12.35.261 snapshot identified 22 dirty test files, including the three untracked expiry/replay tests. The current S12.35.263 recheck has 23 dirty test files after adding the Downloader ancestry regression; an exact filename comparison against the workflow still found `not_named_in_ci=0`.
- Result/limits: no test module is missing from the current CI selection, so no workflow change is indicated. This does not prove those tests pass, that the full test run or `bot.py` compile succeeds, or that CI has run against this dirty worktree. A8 remains partial; A3/A5/A6/A7 and final comparator/delivery gates remain open.
- Side effects: read-only local Git/workflow inspection; no code/workflow changes, test execution, external calls, push, merge, deploy, or restart.

### S12.35.262 — Callback timing observer source coverage

- Contract: verify that callback timing instrumentation is installed after all direct callback registrations, wraps registered callback handlers, keeps callback/message data out of timing logs, and emits route/guard/handler/render timing on fixture execution. Do not alter telemetry or runtime based on an empty sample.
- Evidence: source inspection shows `install_callback_latency_instrumentation(tg_app)` follows the last direct `CallbackQueryHandler` registration; the installer wraps each existing callback handler and the shared `safe_edit_query_message` render helper. Focused local command `python -m unittest -v tests.test_callback_dispatch_timing` returned `Ran 5 tests in 30.535s — OK`, covering `account_root` fixed label, anonymous handler/render timing, errors, shared-guard stop, and install order.
- Finding/limits: no instrumentation coverage defect reproduced in this local source. This is not proof that the same source is currently deployed on VPS, that a live tap reached the bot, or that Telegram/client rendering is fast. The approved 24-hour `account_root` aggregate remains empty; A7 is open pending a click-correlated server event and client duration. No telemetry/source patch is justified by this evidence.
- Side effects: local source/test only; no raw production log, provider, wallet, production data, Telegram send, deploy, restart, or protected engine access.

### S12.35.263 — Free Tools Downloader preserves entry ancestry

- Contract: dispatch the actual Free Tools Downloader button through the registered `vdownload|` handler; Back from both the initial link prompt and the format/retry screen must return to Free Tools, while the existing Video Studio entry retains its Video Studio parent. Confirm Home and cross-entry shortcuts remain available and leaving the pending prompt clears only the current user's downloader state. Do not call the downloader adapter or enter media processing.
- RED: reproduced the mismatch before the focused fix: Free Tools and Video Studio both emitted `vdownload|start`, and the Downloader's default Back returned to `menu|main_video` rather than the Free Tools parent.
- Change: Free Tools now emits `vdownload|start|freehub`; the registered handler carries the origin in the actor's pending state; start and choice keyboards select the matching Back destination and preserve the origin on “Gửi link khác”. The legacy `vdownload|start` callback and Video Studio route retain their existing Video Studio behavior. No downloader/provider/engine behavior changed.
- GREEN: `tests.test_video_downloader_freehub_exit_pending` — `Ran 2 tests in 4.314s — OK`. The fixture dispatches emitted controls through the exact registered handlers, checks Free Tools Back/Home and alternate Video Studio route, preserves another user's pending state, verifies Video Studio's legacy Back, and confirms ordinary text after leaving is not consumed or passed to link detection. The test file is named in `.github/workflows/ci-main.yml`; the current dirty-test selection audit found 23/23 listed. `git diff --check` exited 0.
- Limits: adapter detection, link fetching, media delivery, paid/external work, wallet, real Telegram rendering, and live latency were not invoked. This closes this one ancestry regression only; A3/A4/A5 and whole-bot coverage remain partial. The current three-file `py_compile` session was interrupted after repeated polls produced no output and is NOT_VERIFIED; this is not a compile failure and no compile pass is claimed.
- Side effects: offline registered-handler fixtures only; no provider, wallet, production data, Telegram message, merge, deployment, or restart.

Evidence-matrix delta: S12.35.263 adds one Free Tools → Downloader parent/Back regression to A3/A4/A5. It does not close any other Downloader terminal, all-button latency, or the global callback matrix.

### S12.35.265 — Admin Finance report route recheck

- Contract: validate the Admin Control Center → Finance entry and emitted finance-report controls through the registered `menu|` handler. Cover a read-only report route, its Back destination, and rejection of public/stale dashboard origins using fixture data only; do not add expenses, export real data, or touch financial records.
- GREEN: three focused cases ran with an immediate no-I/O driver using the nested fixture's `Query`: `test_admin_control_center_finance_button_opens_finance_hub`, `test_finance_report_buttons_render_readonly_pages_and_return_to_finance`, and `test_dashboard_finance_overview_rejects_public_and_stale_origins` — `Ran 3 tests in 61.103s — OK`. This proves the emitted Admin Finance entry reaches the registered route, selected read-only finance pages render and return to Finance, and public/invalid origins are rejected before report rendering.
- Supplemental evidence: in a combined command, the actual Admin Overview route and both fixture-based report payload/provider-availability tests passed. The combined 12-test command as a whole failed because the temporary immediate adapter initially looked for `Query` on the outer module (28 harness errors before the affected handler assertions); the standard run first stalled in the existing Windows `asyncio.run()` fixture. Neither result is counted as product failure or full-suite pass. The corrected, focused three-case run above is the counted Finance route evidence.
- Limits: report values and provider source are in-memory fixtures, not production DB/report correctness. No write/action path, real export, live Telegram rendering, or latency was tested. A1/A2/A5 remain partial; this does not validate all Admin reports or operational controls.
- Side effects: local source-extracted callback fixtures only; no production database, financial record, provider, wallet, Telegram send, merge, deploy, or restart.

Evidence-matrix delta: S12.35.265 adds selected Admin Finance entry, report-page, Back, and stale-origin evidence to A1/A2/A5; it does not close the Admin report matrix or A7 latency.

### S12.35.266 — Protected engine and wallet diff boundary

- Contract: review the entire current WIP path list and every `bot.py` diff hunk against the Owner's UI-only scope. Verify that no Product/Edit/SubDub/Voice/Music/Image/Video engine, provider, worker, wallet, or payment implementation was changed; do not rebase or deliver.
- Evidence: `git diff --name-only` lists `bot.py`, CI, tests, and audit documents only; there are no changed `services/`, `providers/`, worker, or product-engine files. The complete `bot.py` hunk-header inventory is confined to keyboard builders, callback handlers, route-origin/pending-state preservation, stale-input handling, and callback timing instrumentation. The package diff carries origin tokens through display/Back callbacks; the `start_package_purchase` call sites remain unchanged. The Downloader change only carries the UI entry origin through its existing pending state and keyboards; link detection/download code is unchanged.
- Result: no protected processing engine, provider, worker, wallet, or payment implementation delta was found in the current WIP. This is a local source-boundary check, not proof of current VPS behavior. The WIP remains uncommitted and is not merged or deployed.
- Side effects: read-only diff/path review only; no provider, wallet, production data, push, merge, deploy, or restart.

### A7 — Fresh approved callback timing aggregates (2026-10-11 00:45 +07)

- Contract: execute the separately Owner-approved read-only 24-hour aggregates for (1) `callback_dispatch_timing` on `route_key=account_root`, (2) `callback_dispatch_timing` grouped by route/handler, and (3) `callback_latency` on exact `menu|main` / `menu|main_video`, grouped by route/role and phase. Return only count/average/maximum and command exit/stderr status; never expose raw logs, IDs, or payloads.
- Runtime output: all three strict-host SSH queries completed; each reported `JOURNALCTL_EXIT=0`, `JOURNALCTL_STDERR_BYTES=0`, and `AGGREGATE_EXIT=0`. The Account-root query had `MATCHING_EVENTS=0` and count 0 for `guard_ms`, `handler_ms`, `render_helper_ms`, and `dispatch_ms`. The all-route dispatcher query had `MATCHING_EVENTS=0`; the exact menu-phase query also had `MATCHING_EVENTS=0`. No aggregate rows existed.
- Finding/limits: these are valid empty 24-hour windows, not proof the buttons are fast, proof a tap reached the bot, or evidence of a server delay. They cannot explain the reported 2–3s Account → Back or distinguish server handling from Telegram transport, network, device, or client rendering. No route fix, cache change, or hardware purchase is justified. A7 remains open until an exact client click time/duration can be matched to a server event; uninstrumented message/reply-keyboard paths remain outside these callback aggregates.
- Side effects: three approved read-only journal aggregates only; no raw records, service/runtime change, Telegram send, provider/wallet operation, deploy, or restart.

### S12.35.267 — Admin Finance action-renderer fixture gate

- Contract: run the focused Admin Finance action-renderer fixture suite, including the public-user denial boundary; use local fixture data only and do not invoke production report, finance, or wallet operations.
- GREEN: all 9 tests in `tests.test_admin_finance_action_renderers` passed with an immediate no-I/O fixture driver: `Ran 9 tests in 289.990s — OK`. Coverage includes the emitted Admin Finance entry, report pages and their Finance Back, System Ops dashboard ancestry, legacy context, guide labels, and public/stale-origin denial before render/cleanup.
- Runner note: standard `unittest` remained at its first test for over 130 seconds and was interrupted; the fixture's `_dispatch` calls `asyncio.run()` in this Windows environment. The complete suite then passed after replacing only that test-fixture call with the existing immediate no-I/O pattern; no test or product source was edited for the runner.
- Limits/side effects: no production database, financial record, wallet mutation, provider, Telegram message, source edit, merge, deploy, or restart. A1/A2/A5 remain partial.

### S12.35.268 — Admin report source availability and period aggregation

- Contract: exercise report helpers with seeded in-memory SQLite under a SELECT/READ/FUNCTION-only authorizer. Verify period totals and ensure missing provider telemetry is shown as unavailable rather than as a healthy zero; never open the production database.
- GREEN: `python.exe -m unittest -v tests.test_admin_report_source_availability` returned `Ran 2 tests in 9.122s — OK`. It verified period fixture aggregation and missing-provider-table behavior.
- Limits/side effects: fixture-only report data and in-memory read-only SQLite; no production report query, database, financial record, provider, wallet, real Telegram send, or source change. This closes only the selected report-source slice; A1/A2/A5 remain partial.

### S12.35.269 — Admin Knowledge Vault status callback

- Contract: dispatch the emitted Admin Vault `vault|status` control through the exact registered callback pattern using an inert status/importer fixture. Verify one ACK, read-only status rendering, and the existing Main-menu return. Do not access production vault storage or run import, approval, or asset actions.
- GREEN: `test_knowledge_vault_status_dispatches_emitted_control_to_read_only_status` in the existing CI-listed `tests/test_admin_root_menu_callback_single_ack.py` returned `Ran 1 test in 0.857s — OK` with an immediate no-I/O dispatcher. It checks the actual emitted callback, `^vault\|` registration, extracted `handle_knowledge_vault_callback`, one ACK, one fixture `debug_status()` read, expected status text/keyboard, and the pre-existing `menu|main` return evidence.
- Runner note: a standard `unittest` attempt produced no result for about 75 seconds and was interrupted because this Windows fixture's `asyncio.run()` setup stalls; it is not counted as a product failure. The focused no-I/O dispatch completed and is the counted result.
- Result/limits: no callback destination, ACK, or status-render defect was reproduced, so no product-code change was made. This closes one selected Admin route only; A1/A5, manual Telegram UI, full-file compile, consolidated CI, and whole-goal closeout remain open.
- Side effects: offline source-extracted callback and in-memory fixtures only; no production vault/database, import/approval, provider, wallet, real Telegram message, merge, deploy, or restart.

Evidence-matrix delta: S12.35.269 adds one emitted Admin Knowledge Vault status → registered-handler render check to A1/A5. It does not validate other Vault actions, production inventory accuracy, client rendering/latency, or the whole Admin/callback matrix.

### S12.35.270 — `bot.py` static compile runner status

- Contract: run `python -m py_compile bot.py` without importing or executing the bot. A bounded runner stall is recorded as `NOT_VERIFIED`; it is not evidence of a source syntax defect.
- Result: the bundled Python process produced no output or exit result after approximately 95 seconds and was interrupted. Full-file `bot.py` syntax remains `NOT_VERIFIED` (not a compile failure). The focused test module did compile successfully: `python -m py_compile tests/test_admin_root_menu_callback_single_ack.py` exited 0.
- Limits/side effects: no product code was changed to work around the runner; bot was not imported or executed, and no provider, wallet, production data, Telegram send, service change, merge, deploy, or restart occurred. This keeps A8 open.

### S12.35.271 — Internal Archive view/file callback ACK and DB lookup

- Contract: for emitted Archive `view` and `file` actions, ACK before the SQLite lookup and move only that read off the bot event loop. Preserve valid detail and file behavior; keep malformed-ID alerts; after an early ACK, stale/missing rows must show a recoverable screen and must not clear pending state. Use fixtures only, never a production document or real Telegram send.
- RED: the new `test_archive_document_reads_are_acknowledged_before_lookup` failed for both `view` and `file` on the original source: the instrumented `get_internal_document` seam saw `query.answers == []`. The sync lookup was before callback ACK.
- Minimal fix: `handle_internal_archive_callback` now ACKs once, then awaits `asyncio.to_thread(get_internal_document, uid, document_id)`. On missing record/file after that ACK it edits the stale result message to a concise error and existing Archive-root/Home keyboard; malformed IDs still use the original alert. Successful view/file and their actor-scoped cleanup paths remain after the lookup.
- GREEN: the existing CI-listed `tests/test_internal_archive_search_back_origin.py` module passed `Ran 21 tests in 146.976s — OK` using an immediate no-I/O dispatcher. It includes ACK-before-lookup for both actions, emitted detail view, a fake file-send boundary, malformed/stale recovery, Back/expiry and actor-only state preservation. The new RED was observed before implementation; the same focused test passed after the change. `py_compile` for the changed test file exited 0; source extraction in the tests compiles the exact handler.
- Scope/limits: only one Archive handler and its existing test file changed for this spec; no Archive engine/storage format, payment, provider, or wallet behavior was altered. Fixture ordering is not a live latency measurement and does not explain Account → Back. Full `bot.py` py_compile remains `NOT_VERIFIED` after two no-output attempts (the second also tried with GC disabled); no syntax failure is inferred. No production DB/file or Telegram send was used. A1/A2/A5/A7 and A8 remain partial.
- Side effects: inert fixtures only; no production document/database, provider, wallet, real Telegram delivery, merge, deploy, service change, or restart.

Evidence-matrix delta: S12.35.271 strengthens selected A1/A2/A5 Archive evidence by ensuring a slow document lookup cannot hold the callback spinner or block the event loop; stale errors have a safe route back. It does not prove live delay reduction or close the overall latency diagnosis.

### S12.35.272 — Feedback callback ACK before language lookup

- Contract: for supported Feedback `start`, `cancel`, and category callbacks, validate the local callback/category first, ACK exactly once, then load the user's language and render. Keep the original unsupported-action/category alerts and all pending-state behavior unchanged.
- RED: `test_feedback_start_acknowledges_before_user_language_lookup` failed before the change because the injected `user_ui_lang` seam observed no ACK; source ordering confirmed the synchronous language lookup happened first.
- Minimal fix: moved `user_ui_lang(uid)` to immediately after the supported-action/category checks and one `query.answer()`. Unsupported actions and category values still alert before lookup or pending mutation.
- GREEN: eight focused callback fixture functions from the existing CI-listed `tests/test_feedback_callback_single_ack.py` returned `Ran 8 focused Feedback callback tests — OK` using the immediate no-I/O driver. Coverage: invalid action alert, start and cancel, emitted category prompt and Back/Home, ACK-before-language ordering, invalid category, category whitelist, and all eight emitted category routes.
- Runner/evidence limits: this file defines pytest-style functions; a direct `unittest` run reports zero tests, not a pass. The CI workflow runs it through pytest. No consolidated CI result or live Telegram measurement was produced; this closes only one short customer callback path. A3/A5/A7 remain partial.
- Side effects: offline source-extracted registered-handler fixtures only; no Feedback text submission, Ticket creation, production data, provider, wallet, real Telegram send, merge, deploy, or restart.

Evidence-matrix delta: S12.35.272 improves ACK ordering for the supported Feedback controls before the synchronous language lookup. It does not establish all-button latency, end-to-end screen rendering, or whole-goal completion.

### S12.35.273 — Document Tools Back ACK before language lookup

- Contract: dispatch the emitted `docflow|back|main_docs` through its exact registered handler; acknowledge once before synchronous `get_user_language`, return to Documents, and clear only the current user's pending document draft. Keep Confirm's existing lookup/ACK and minimum-file validation order unchanged.
- RED: the new emitted-Back regression failed against the original source because the language seam observed no prior ACK (`language_lookup_after_ack=[False]`).
- Minimal fix: parse the action first; non-Confirm actions now ACK before language lookup. Confirm retains its previous lookup-before-ACK path and validation behavior.
- GREEN: all three focused tests in CI-listed `tests/test_doc_tool_callback_single_ack.py` passed through the exact registered handler with an immediate no-I/O driver. Coverage includes the emitted Back destination, one ACK, actor-only pending cleanup, Send-more, and insufficient-file Confirm. The test module `py_compile` and `git diff --check` exited 0. Local bundled Python has no `pytest` module, so this is not reported as pytest or CI success.
- Limits: proves only source-fixture ACK ordering and Back destination, not live Telegram speed or full Document Tools behavior. Full `bot.py` compile remains NOT_VERIFIED and A1/A2/A5/A7 plus whole-goal closeout remain partial.
- Side effects: inert source-extracted callbacks/in-memory state only; no file processing, production data, provider, wallet, Telegram send, merge, deploy, or restart.

### A7 — Account-root aggregate recheck — 2026-10-11 01:52 +07

The Owner-approved strict-host SSH query for the preceding 24 hours completed successfully (`JOURNALCTL_EXIT=0`, stderr 0 bytes, aggregate exit 0) and matched zero `callback_dispatch_timing` events with `route_key=account_root`; each timing metric therefore had count 0 and no average/maximum. This empty sample cannot explain the reported Account → Back 2–3 seconds or identify whether delay is server, Telegram, network, device, or client rendering. No speculative latency patch or hardware recommendation is justified; A7 remains open pending a precisely timed click correlated to a server event.

### A7 — Account-root aggregate recheck — 2026-10-11 05:31 +07

- A second Owner-approved strict-host SSH query covered the preceding 24 hours and returned `SSH_EXIT=0`, `JOURNALCTL_EXIT=0`, `JOURNALCTL_STDERR_BYTES=0`, `AGGREGATE_EXIT=0`, and `MATCHING_EVENTS=0` for `callback_dispatch_timing route_key=account_root`.
- `guard_ms`, `handler_ms`, `render_helper_ms`, and `dispatch_ms` each had count 0; averages/maxima are unavailable. No raw lines, IDs, or payloads were returned.
- This remains an empty server-side sample, not evidence that the click reached the bot or a diagnosis of the 2–3 second Account → Back delay. A7 remains open; no latency patch or hardware/network cause is inferred, and runtime was not changed.

### A7 — Account → Back route classification — 2026-10-11 05:47 +07

- Correction: `account_root` is assigned only to the Account-entry callback `menu|main_profile`; Account → Back emits `menu|main` and is classified `main_home`. The preceding approved `account_root` query therefore did not measure the reported Back click.
- Local source review: `handle_menu_callback` ACKs before language lookup, pending cleanup, keyboard construction, and Telegram edit. Before ACK it performs callback/origin checks and an in-memory `OWNER_IDS`/`ADMIN_IDS` membership test; no synchronous database/network read was found on this route.
- Exact emitted Account menu → registered Menu handler → Home → Package child Back to Account fixture passed: `Ran 1 test in 1.995s — OK` with the immediate no-I/O runner. A later full-module attempt emitted its first test name but produced no result after >120s; interrupted and recorded `NOT_VERIFIED`, not a product failure. This does not supersede the earlier 50-test result.
- No code change is supported by current evidence. Early ACK is verified locally, but post-ACK render/network/client timing remains unmeasured. A7 remains open until a client-timed `main_home` tap is matched to an approved live phase aggregate; no latency cause is assigned.

### S12.35.274 — Ticket-input Back ACK before language lookup

- Contract: emit the production Ticket-input Back control, dispatch exact `ticket|start` through the registered `^ticket\|` handler, and ACK once before synchronous `get_user_language`; preserve the same Ticket menu render and all other Ticket callback behavior.
- RED: the new focused registered-route test failed on original source because the language lookup observed ACK count `0` instead of `1`.
- Minimal fix: only exact `data == "ticket|start"` ACKs before language lookup; the shared later ACK skips that exact callback to avoid double-ACK. Other Ticket validations, database reads, alert behavior, and callback order are unchanged.
- GREEN: `AdminTicketReplyOriginPaginationTest.test_emitted_ticket_back_acks_before_language_lookup` passed using an immediate no-I/O runner. It verifies the production keyboard-emitted callback, registered handler match, ACK-before-language, one ACK, and existing Ticket-menu render. A later run of the CI-listed fixture class passed all five test methods after the adjacent preview spec was added; this supersedes the earlier bounded run that returned no output. The test files compiled. Full CI/pytest and full `bot.py` compile remain pending.
- Limits: closes only the exact Ticket-input Back/start path in a fixture. Other Ticket detail/list callbacks and live latency remain unverified; no all-button speed or cause claim.
- Side effects: in-memory fixture data and fake handler/render only; no ticket submit, production ticket/user read, Telegram send, provider, wallet, engine, AutoPost, merge, deploy, or restart.

### S12.35.275 — Customer Ticket preview ACK/read and stale recovery

- Contract: follow the real customer ticket-list preview button into the exact registered handler; validate ID/origin, ACK once before synchronous language/ticket lookup, run the read-only SQLite lookup through `asyncio.to_thread`, preserve successful detail rendering, and give stale/missing rows a valid recovery path. Keep malformed-ID alerts and actor pending semantics.
- RED: the emitted `ticket|pv|9006` route first read the ticket while ACK count was 0. After the first narrow move, a second assertion exposed that the synchronous language lookup still happened before ACK (`[0]`); the final test checks both boundaries.
- Minimal fix: only well-formed preview callbacks with allowed origins ACK before language lookup, then call `get_support_ticket` via `asyncio.to_thread`. A missing record now replaces the alert with a short not-found screen and a valid My Tickets/Ticket return plus Home. Malformed callbacks still receive their original alert; success detail and pending cleanup remain intact.
- GREEN: the actual `public_support_ticket_list_keyboard` emitted `ticket|pv|9006`; it matched the registered `^ticket\|` handler. The CI-listed `AdminTicketReplyOriginPaginationTest` fixture class passed all five tests with an immediate no-I/O driver. A separate focused source-extracted run passed the Ticket start, valid preview, stale preview, and malformed preview checks (`6 focused assertions — OK`). The relevant test files compiled.
- Limits: fixture evidence only; no live Ticket timing or production read. Other Ticket detail/status/list callbacks remain separate audit items. `bot.py` full compile and consolidated CI remain outstanding; A7 and whole-goal completion remain open.
- Side effects: fixture ticket rows and fake getter/thread adapter only; no production user/ticket read, ticket mutation/submission, Telegram send, provider, wallet, engine, AutoPost, merge, deploy, or restart.

### S12.35.276 — Customer Ticket summary Back ACK/read and stale recovery

- Contract: dispatch the emitted customer Ticket-detail Back-to-summary callback through the registered Ticket handler. For exact numeric IDs and the two result origins, ACK once before language lookup and ticket read; offload only the read-only lookup. Preserve the summary and its View-ticket control. Missing rows must render a safe Ticket-menu/Home recovery screen after ACK; malformed/unsupported alerts remain unchanged.
- RED: the emitted summary Back regression failed on current source with `language_ack_counts=[1, 0]`; language lookup ran before ACK on the second callback.
- Minimal fix: valid `ticket|summary|<id>|profile_result|feedback_result` callbacks ACK before language lookup and perform the ticket read with `asyncio.to_thread`. A stale row now renders Ticket-menu/Home after ACK. No other Ticket action/read ordering changed.
- GREEN: CI-listed `AdminTicketReplyOriginPaginationTest` ran 7 tests in 82.822s — OK using the immediate no-I/O runner. It covers emitted summary Back success and stale recovery, one ACK and ACK-before-language/read, preserved View-ticket control, Ticket start/preview and existing admin reply pagination.
- Verification: test-file `py_compile` exited 0 and `git diff --check` exited 0. Full `bot.py` compile produced no output for over two minutes and was interrupted (`NOT_VERIFIED`, not a syntax failure). Local pytest/remote CI, full source compile, live latency and whole-bot coverage remain open.
- Side effects: in-memory fixtures and fake getter/thread/render seams only; no production Ticket/user read, ticket mutation/submission, Telegram send, provider, wallet, engine, AutoPost, merge, deploy, or restart.

### S12.35.277 — Customer Ticket Reply prompt ACK/read

- Contract: follow the actual Ticket-detail Reply button into the registered Ticket handler. For valid ID/origin, ACK once before language/ticket lookup, move only the read-only lookup off the event loop, then preserve the existing reply prompt, actor-owned pending state and Back-to-detail callback. A stale row must recover to Ticket menu/Home after ACK; malformed/unsupported values retain their alerts.
- RED: the emitted `ticket|reply_user|9006` control reached `get_user_language` while ACK count was `0`.
- Minimal fix: exact valid `reply_user` callback shapes ACK before language lookup; only this action's ticket SELECT uses `asyncio.to_thread`. A missing ticket renders Ticket menu/Home after ACK. The shared later ACK skips the exact early-ACKed route. Attach and Done are unchanged.
- GREEN: the complete CI-listed `AdminTicketReplyOriginPaginationTest` fixture class ran 9 tests in 104.359s — OK. It includes the emitted Reply prompt's single ACK before both lookups, actor-owned `awaiting_ticket_reply` state, exact Back-to-detail callback, stale recovery without pending mutation, and the prior summary/preview/start/admin-pagination tests. Test-file `py_compile` exited 0; `git diff --check` exited 0.
- Limits/side effects: source-extracted registered-handler fixtures only; no reply text submitted, real message sent, production Ticket/user read, mutation, provider, wallet, engine, AutoPost, merge, deploy or restart. This does not establish live latency or close other Ticket controls/A7.

### S12.35.278 — Customer Ticket Attach prompt ACK/read

- Contract: follow the actual Ticket-detail Attach button into the registered Ticket handler. For valid ID/origin, ACK once before language/ticket lookup, offload only the read-only lookup, then preserve the attachment prompt, actor-owned pending state and Back-to-detail callback. A stale row must recover to Ticket menu/Home after ACK; malformed/unsupported values keep their alerts.
- RED: emitted `ticket|attach|9006` reached language lookup at ACK count `0`.
- Minimal fix: valid Attach callbacks ACK before language lookup and perform only the read-only `get_support_ticket` in `asyncio.to_thread`; stale rows render Ticket-menu/Home after ACK. Reply behavior is retained; Done is unchanged.
- GREEN: complete CI-listed Ticket fixture class ran 11 tests in 129.764s — OK, covering emitted Attach prompt, single ACK before both getters, actor pending state and exact Back/Home; stale recovery without pending state; plus Reply, summary, preview, Ticket start and admin reply/pagination routes. Test-file `py_compile` and `git diff --check` exited 0.
- Limits/side effects: fixture-only; no file uploaded, real message sent, production Ticket/user read, status mutation, provider, wallet, engine, AutoPost, merge, deploy or restart. No live latency claim; A7 remains open.

### S12.35.279 — Customer Ticket Done confirmation (in progress)

- Contract: inspect the emitted Ticket-detail Done action through the registered callback using inert fixtures. Verify ACK vs language/read/update order, one status update, stale-row behavior, and the exact success controls/Back/Home. Do not mutate production Ticket data.
- Boundary: this action resolves a Ticket, unlike Reply/Attach prompt navigation. Do not change its status-update semantics or offload the write without direct evidence that the current order blocks acknowledgement and a focused regression test.
- RED: the emitted `ticket|done|9006` control reached language lookup while ACK count was `0`.
- Minimal fix: only well-formed Done callbacks ACK before language lookup; the existing status update remains exactly once and unchanged. The read-only Ticket lookup is offloaded; stale rows render Ticket-menu/Home after ACK and never call the update helper.
- GREEN: complete CI-listed `AdminTicketReplyOriginPaginationTest` ran 13 tests in 146.806s — OK. Success asserts one update to `resolved` and unchanged Mine/Support/Home controls; stale asserts no update and Ticket-menu/Home. Reply, Attach, Summary, Preview, Start and admin pagination also remain green. Test-file `py_compile` and `git diff --check` exited 0.
- Limits/side effects: fake update helper and in-memory fixtures only; no production Ticket status change or user data read, reply, upload, real Telegram send, provider, wallet, engine, AutoPost, merge, deploy or restart. The synchronous status-update call remains after ACK; this spec does not prove screen-edit latency or live smoothness.

### S12.35.280 — Admin Ticket detail ACK/read

- Contract: follow the actual Admin Ticket detail/view control through its registered handler. Keep authorization before any user-visible result; for a valid authorized callback ACK before language/SQLite lookup, offload only the read, preserve detail/back controls, and show safe recovery on stale records. No status mutation, reply/file send, or production Ticket read.
- GREEN: three focused `AdminTicketReplyOriginPaginationTest` methods passed in 51.358s — authorized emitted detail ACKs before language/read and restores the exact `high` page 6 Back plus Home; stale detail recovers after one ACK with no update; non-admin is denied before the Ticket read. Related Ticket regression modules passed 15 tests in 149.819s — OK.
- Fixture-only correction: the preview-Back test harness lacked `support_ticket_pending_key`, which the extracted production handler calls. Added only the production-equivalent fixture helper; the corrected focused test passed (1 test in 8.940s), and `py_compile` for that test file succeeded. This was a harness setup issue, not a new production defect.
- Limits: no real ticket read/update, reply/file send, live Telegram rendering or click latency. Full `bot.py` compile remains `NOT_VERIFIED`; consolidated CI and whole-goal review remain open. Account → Back still lacks a matched `account_root` event, so no server/client/network cause is assigned.
- Side effects: in-memory fixtures and fake read/update/render seams only; no production data, provider, wallet, protected engine, AutoPost, Telegram send, merge, deploy, or restart.

### S12.35.281 — Admin Ticket list read offload

- Contract: dispatch an emitted valid Admin Ticket list-page callback through its exact registered handler. Preserve admin authorization, list kind/offset, malformed-input denial and existing page UI; ACK exactly once before the read. First prove `support_admin_list_payload` only reads/formats fixture data. Offload only read-only list work; do not write tickets, send replies/files, or access production data.
- RED: the emitted `ticket|al|high|6` callback already ACKed before the list SELECT, but the tightened assertion failed because the payload builder did not cross `asyncio.to_thread`; the SELECT and payload formatting were synchronous on the event loop.
- Fix: the valid `al` branch now awaits `asyncio.to_thread(support_admin_list_payload, kind, offset)`. The existing ACK, authorization/validation, actor pending cleanup, filters, page offset, screen content and buttons are unchanged.
- GREEN: five focused Admin Ticket list/detail cases passed after the one-line product change (including emitted next page/offload boundary, unauthorized no-read, authorized detail, stale detail, and non-admin detail). The CI-listed Admin Ticket hub module passed all 6 tests in 15.747s — OK, including malformed offset, valid filter/page, Back ancestry and denial. Three changed test files `py_compile` and `git diff --check` exited 0. An initial combined run found only a missing test-fixture `asyncio.to_thread` adapter; after adding the inert adapter, the complete hub module passed.
- Limits: fake list rows prove the offload boundary and callback output, not production query duration or client-rendering latency. No live database, real ticket, reply/file send, provider, wallet, protected engine, AutoPost, merge, deploy, or restart.

### S12.35.282 — Admin Ticket Stats read offload

- Contract: dispatch the actual emitted Admin Ticket Stats control through its registered handler. Preserve authorization and exact originating Back route; verify one ACK before the read-only stats helper and offload that helper only after confirming SELECT-only behavior. Keep report content fixture-only; no production DB or financial action.
- RED: the actual emitted `ticket|stats|admin` callback ACKed but invoked the three-SELECT `support_ticket_stats_text()` helper synchronously; the focused test observed no `asyncio.to_thread` boundary.
- Fix: the Stats branch now awaits `asyncio.to_thread(support_ticket_stats_text)` before rendering. Existing report text, Stats panel, Back-to-origin, Home and authorization remain unchanged.
- GREEN: the emitted-control/read-boundary test checks one ACK before offload/read and exact `ticket|admin` Back plus `menu|main` Home. The complete CI-listed Admin Ticket hub module passed 7 tests in 18.185s — OK, including list paging/filter, invalid offsets, authorization, sibling panels and Back routes.
- Limits: inert read seams only; no production DB or report data. This verifies offload wiring, not live query duration or client-rendering time. Full `bot.py` compile, consolidated CI and live latency remain pending.

### S12.35.283 — Admin Ticket Search input read offload

- Contract: dispatch the actual emitted Ticket Search control through the registered callback, then deliver fixture text to the actual pending-input handler. Preserve `admin_search` pending ownership and Back/Home; confirm the search payload is SELECT-only and executes via `asyncio.to_thread`. Keep other users' pending state unchanged; no production or real message I/O.
- RED: the real emitted `ticket|asearch|all` control established admin-search pending state, but fixture text called `support_admin_search_payload()` synchronously; the focused boundary assertion observed no `to_thread` call.
- Fix: the `admin_search` input branch now awaits `asyncio.to_thread(support_admin_search_payload, text)` before rendering. Actor pending cleanup, query construction, output, Back and Home remain unchanged.
- GREEN: one focused test passed in 28.849s. It dispatched the emitted Search control through the registered callback, then exercised `handle_support_pending_input` with fixture text; it verified offload, search helper inputs, actor-only pending cleanup, preserved other-user state, and result Back/Home. No real message or production DB.
- Limits: local fixture boundary only, not production search timing or Telegram message rendering. Full bot compile and consolidated CI remain pending.

### S12.35.284 — Customer My Tickets ACK and read offload (locally verified; batch delivery pending)

- Contract: dispatch the actual emitted customer My Tickets callback through the registered handler. For valid shapes, ACK before language lookup/read, offload only the read-only public list payload, retain origin-specific Back/Home, and clear only the actor's pending state. Invalid/public routes must fail closed without reads; no production Ticket data.
- RED: the emitted `ticket|mine|support` callback reached language lookup before its ACK and called `list_support_tickets()` synchronously; the first focused test failed with observed order `language → ACK → list` and no thread offload.
- Minimal fix: ACK only valid `ticket|mine` shapes before language lookup; offload only `list_support_tickets()` with `asyncio.to_thread`, then pass the returned rows into the existing keyboard renderer. Keep rendered controls, origin mapping, list limit/filter, pending cleanup, invalid-origin rejection and all Ticket business actions unchanged.
- GREEN: the new ACK/offload + actor-only-pending test and invalid-origin fail-closed test passed; existing public My Tickets Back/Home, list→detail→exact-list Back, legacy unscoped `ticket|mine`, and supported Ticket category ACK regressions were rerun after both local fixes: `6 tests in 72.927s — OK`. The test file `py_compile` and focused `git diff --check` exited 0. `tests/test_profile_ticket_ancestry.py` is already in the safe-navigation CI workflow; remote CI has not run for this batch.
- Limits: fixture-only source/ordering/navigation evidence; no production ticket read, full `bot.py` compile, remote CI, Telegram client render/timing, or client/network diagnosis. A broader `test_customer_ticket_action_ack` run was interrupted after >150s in the Windows test harness without a result; it is NOT_VERIFIED, not a product failure. Consolidated CI and batch delivery remain pending. No provider, wallet, real Telegram, AutoPost, protected engine, merge, deploy or restart.

### S12.35.285 — Customer Ticket category prompt ACK order (locally verified; batch delivery pending)

- Contract: dispatch an actual emitted supported Ticket category control through the exact registered handler. For a valid category callback, ACK once before language lookup, pending-state set and prompt render. Preserve selected category, actor ownership and prompt Back/Home. Do not change existing fallback behavior for unsupported category values; fixture only.
- RED: after fixing two missing source globals in the fixture only, the actual emitted `ticket|cat|image_error` route reproduced `language → ACK → pending`, violating the required prompt responsiveness order. The initial `NameError`s (`SUPPORT_CATEGORIES`, `support_ticket_message_prompt`) were fixture omissions, not product failures.
- Minimal fix: ACK only the exact supported `ticket|cat|<category>` shape before language lookup, and skip the shared ACK for that already-acknowledged route. Existing unsupported-category fallback, pending semantics, prompt content and callbacks remain unchanged.
- GREEN: the new emitted-control/registered-handler test passed (`1 test in 13.785s — OK`), asserting single ACK before language/pending, selected category, foreign pending preservation, and prompt Back/Home. After both local ACK changes, the six-case focused combined regression passed (`6 tests in 72.927s — OK`). Test-file `py_compile` and focused `git diff --check` exited 0; the test module is already listed in safe-navigation CI.
- Limits: fixture evidence only; the existing `asyncio.run` category-navigation test showed no progress for >60s and was interrupted, so it is NOT_VERIFIED. The focused test covers the same category route and asserts prompt/back/home. No production Ticket data, real Telegram, full `bot.py` compile, remote CI, client/network latency, provider, wallet, AutoPost, protected engine, merge, deploy or restart.

### S12.35.286 — Translation file/voice target callbacks reach the correct pre-provider boundary

- Contract: build the actual file and voice Translation target pickers, select the emitted `tr_target|file|en` and `tr_target|voice|en` controls, and dispatch each through the exact registered `tr_` handler. Assert one ACK and the correct target/source reference reaches a test-only runner boundary. No media read, translation/ASR/TTS/provider call, production state, wallet, or product code change.
- Review: the handler routes file to `run_translate_file_to_target(..., info=source_ref)` and voice to `run_translate_voice_to_target(...)`; the test replaces both runners and cached media/request state with fixture-only seams.
- Fixture correction: the first new test run failed only because its expected number of `enter_product_context` calls was 4 instead of 2. Corrected the assertion. The existing text-target test then stalled under `asyncio.run` on this Windows runner; switched only that test to the existing immediate no-I/O driver.
- GREEN: focused text + file/voice target tests passed `Ran 2 tests in 1.874s — OK`; `tests/test_admin_root_menu_callback_single_ack.py` `py_compile` exited 0. The module is already listed in `.github/workflows/ci-main.yml`.
- Limits: a fresh whole-module attempt stalled at the first unrelated Admin Archive test without reaching a result; interrupted after >60s, so the full module is NOT_VERIFIED in this run. No remote CI, full `bot.py` compile, media/provider operation, live Telegram delivery, latency, merge, deploy, or restart. A3/A5/A7 and goal closeout remain partial.

### S12.35.287 — Translation voice picker preserves its parent and recovers after audio expiry

- Contract: follow emitted audio-target controls from the Language, Media, and received-audio action screens. Back must restore the exact emitting screen; Home must reach Main; More → Back must return to the target list even after cached audio expires. A target click with expired audio must warn, retain a usable recovery keyboard, and stop before saving a request or entering the voice runner. No audio read, translation/ASR/TTS/provider call, wallet, or production state.
- RED: the focused assertion reproduced `tr_pick|voice` without any origin token. The target picker emitted no Back/Home, and its generic `tr_pick|voice` route checked for recent media before allowing the More → Back navigation.
- Minimal fix: carry a bounded origin token (`language`, `media`, `actions`, or `command`) through the Translation picker callbacks; restore that exact UI on Back; add Home; use a distinct `tr_pick_back` route for More-page navigation so it remains available after expiry. Initial picker entry still warns immediately if no audio; target selection retains its fresh-media guard and matching recovery keyboard. Existing file/text target routes and voice runner call remain unchanged.
- GREEN: registered-handler voice navigation/recovery, text/file picker More/Back, file/voice target, and text target-boundary regressions passed `Ran 4 tests in 3.352s — OK`. The sibling text/file test initially stalled under `asyncio.run`; since its Telegram/UI seams are immediate and inert, the fixture now uses the existing no-yield driver and passes. Test-file `py_compile` exited 0; `git diff --check` exited 0 (only existing LF→CRLF warnings). The module is already in `.github/workflows/ci-main.yml`.
- Limits: all evidence uses inert runner, media, and render fixtures. Full `bot.py` `py_compile` produced no output for 55 seconds and was interrupted; mark NOT_VERIFIED, not syntax failure. No remote CI, real Telegram click/render, live latency/network diagnosis, provider, merge, deploy, or restart. A3/A5/A7 and goal closeout remain partial.

### Runtime/release gate recheck — 2026-10-11

- [x] Read-only deployment check: workflow #492 succeeded at `381d335961bea01db60cda99f0dfe98e2b2d1760`; VPS bot runtime matched. PRs #1410, #1411, and #1415 are ancestors of that runtime. Bot/web/nginx active; `NRestarts=0`.
- [x] Main/runtime comparison: main is `5c38bd31c20f26f815e2f05b6419f4dd64afbba9`; runtime is an ancestor. The 7-file delta is confined to Product Video provider/router/worker and tests (#1420).
- [ ] Do not deploy current main from this UX-only task: it would add the protected Product Video delta. No deploy/restart was run.
- [ ] Account → Back latency remains unresolved: its callback is `menu|main` (`main_home`), not `account_root`; the approved account-root and exact menu phase windows were valid but empty. No cause (bot, Telegram, network, device, or rendering) is established.
- [ ] Whole-WIP compile remains `NOT_VERIFIED`: local `py_compile bot.py` had no result after 90 seconds and was interrupted. Full local/remote batch CI and final branch delivery remain open.
- [ ] State YAML parse is `NOT_VERIFIED`: PyYAML was unavailable and the sandbox denied a temporary package install; `git diff --check` exited 0.

### S12.35.289 — Admin monthly/yearly report command routes

- Contract: dispatch the exact registered `/admin_report_month` and `/admin_report_year` callbacks with inert fixtures. Verify valid bounds → report payload → rendered period/export hint, malformed-period recovery, and non-admin denial before report helpers. Never query production data or mutate finance/wallet state.
- Baseline source check: both command registrations exist, and the command function region is unchanged from current `main`. Existing fixture tests cover report aggregation and missing-provider-table availability but do not exercise these registered commands.
- Acceptance: both real registrations are reached; valid month/year render their respective output; invalid month exits without report payload; non-admin denial happens before any bounds/report read.
- First test invocation hit a fixture-only source-extractor mismatch (`def` vs `async def`); the helper was expanded to accept async functions. No product change.
- GREEN: `python.exe -m unittest -v tests.test_admin_report_source_availability` → `Ran 3 tests in 8.808s — OK`; test module `py_compile` and `git diff --check` exited 0 (existing LF→CRLF warnings only). Exact month/year registrations, valid rendering/export, invalid month no-read, and public denial for both commands are covered.
- Result: no product defect reproduced in these two commands. This does not establish live production report accuracy or close the wider Admin report audit.

### S12.35.290 — Standard Admin report quick-command routes

- Contract: dispatch the exact registered `/report_today`, `/report_week`, `/report_month`, `/report_year`, and `/report_range` command callbacks. Verify period mapping, range-argument forwarding, and non-admin denial before report bounds/data reads using in-memory fixtures only.
- Exclusion: do not invoke `/report_ai_*` or `/report_chart_*` because they can call external services or generate files; do not access production data or mutate finance/wallet state.
- Acceptance: all five registrations reach the standard read-only report path with correct period/range arguments; no provider, chart/file output, or production database action occurs.
- GREEN: `python.exe -m unittest -v tests.test_admin_report_source_availability` → `Ran 4 tests in 10.919s — OK`; the test module `py_compile` and `git diff --check` exited 0 (existing LF→CRLF warnings only). Five exact registered commands were dispatched; today/week/month/year map correctly, range arguments are forwarded, outputs retain expected labels, and all five public-user paths deny before bounds/data helpers.
- Limits: fixture/source-extracted evidence only; no production report query, provider, chart/file generation, wallet, or Telegram send. AI/chart commands and the broader Admin report matrix remain unverified.
- Status: locally verified; final batch CI/delivery pending.

## Current-main tester intake 2026-10-15 — ordered callback gate

- [x] Filter the supplied PDF/tester material. Legacy/WebApp findings without
  an active Telegram producer/registered handler remain unmapped; no route or
  engine patch was copied into the bot.
- [x] Lock protected scope: Product Video, Video, Image, Music, Voice, SubDub,
  provider, worker, job, pricing, wallet/Xu, PayOS, AutoPost, ENV/secrets and
  production data are out of scope.
- [x] Require exact producer + registered `^menu\\|` handler + side-effect-free
  RED before opening each implementation spec.
- [ ] Full-source compile, exact-head CI, protected comparator and live-client
  evidence remain release gates.

### S12.35.477–S12.35.490 ledger

- [x] **477 `main`** — stale suffix rejected before ACK/cleanup/render; exact
  root remains valid; focused `2 tests ... OK`.
- [x] **478 `main_profile`** — stale suffix rejected before side effects;
  focused `1 test ... OK`.
- [x] **479 `main_memory`** — exact root and `freehub` origin preserved; stale
  suffix rejected; focused `3 tests ... OK`.
- [x] **480 `main_video`** — stale suffix guard only; focused `1 test ... OK`;
  Product Video/Video engine untouched.
- [x] **481 `main_image`** — stale suffix guard only; focused `1 test ... OK`;
  Image engine untouched.
- [x] **482 `main_guide`** — stale suffix rejected; focused `1 test ... OK`.
- [x] **483 `main_music`** — stale suffix rejected; focused `1 test ... OK`;
  Music engine/provider/pricing untouched.
- [x] **484 `main_topup`** — no implementation opened: baseline already rejects
  unknown origin before ACK; duplicate speculative guard removed.
- [x] **485 `translate`** — producer-backed values allowlisted; unknown suffix
  rejected; focused `1 test ... OK`; translation execution untouched.
- [x] **486 `doc_tools`** — stale suffix rejected; focused `1 test ... OK`;
  document/PDF processing untouched.
- [x] **487 `chat_pro`** — stale suffix rejected; focused `1 test ... OK`;
  provider/engine untouched.
- [x] **488 `chat_free`** — stale suffix rejected; focused `1 test ... OK`;
  provider/engine untouched.
- [x] **489 `admin`** — exact current-main RED reproduced; focused stale-root
  regression passes; Admin data/report/provider helpers are not called.
- [x] **490 `finance`** — exact current-main RED reproduced; focused stale-root
  regression passes; finance calculations/wallet/PayOS are not called.
- [x] **491 `billing`** — exact current-main RED reproduced; focused stale-root
  regression passes; wallet/payment logic is not called.
- [x] **492 `main_docs`** — exact current-main RED reproduced; focused stale-root
  regression passes; document processing/PDF logic is not called.
- [x] **493 Admin submenu matrix** — 11 exact producer roots reject stale
  suffixes before ACK/cleanup/render; child-origin routes remain explicit and
  unchanged (`admin_overview|...`, provider status/routes, DB refresh/back,
  package orders).
- [ ] `main_quick`/`main_audio`: no current literal producer; do not patch until
  an active producer and RED are found.
- [ ] `autopost`: WIP is intentionally held; no new implementation here.
- [x] `billing` producer/ownership is isolated as an exact admin-menu root; no
  broad admin/finance rule was generalized to it.

### Verification record for this candidate

- [x] Exact current-main baseline probes were run through the registered Menu
  handler with inert cleanup/render seams and no I/O.
- [x] Focused unittest batch: `Ran 19 tests in 3.392s`, `OK` (Admin matrix
  contains 11 producer-root subtests).
- [x] Changed test modules compile: `TEST_MODULE_COMPILE_EXIT=0`.
- [ ] Full `bot.py` compile emitted `COMPILE_START` but no completion marker
  during a bounded ~300s observation and was stopped with Ctrl+C;
  `FULL_SOURCE_COMPILE=NOT_VERIFIED` (not interpreted as a syntax failure).
- [x] `git diff --check`: `DIFF_CHECK_EXIT=0`.
- [x] Added `bot.py` executable lines contain no protected provider/worker/
  job/wallet/PayOS/engine/route mutation (UI label strings excluded):
  `PROTECTED_CODE_COMPARATOR_EXIT=0`.
- [x] Changed-file allowlist is exact: `CHANGED_FILE_SCOPE_EXIT=0`.
- [x] Main-menu emitted callback registration smoke: one focused test returned
  `NO_HANDLER_ENTRY_EXIT=0`.
- [x] All public/admin main-menu callback patterns across configured locales:
  `ALL_LOCALE_HANDLER_MAP_EXIT=0` (1 test, 2.768s).
- [x] Read-only producer inventory found no emitted `menu|<guarded-root>|...`
  values beyond the explicit `main_memory|freehub` allowlist; valid child
  screens use distinct callback roots. This is source inventory evidence only,
  not live Telegram evidence.
- [ ] No PR/push/merge/deploy/restart is claimed by this checklist yet.
- [ ] Broader Admin child/Back runner: `NOT_VERIFIED` (no completion marker;
  not interpreted as a product failure or pass).

### S12.35.293 — Admin tax read-only child Back matrix

- Contract: build the actual `finance_tax_keyboard()` emitted from
  `menu|finance_tax_vat`; follow its seven read-only/help controls through the
  registered `menu|` handler and verify every screen's Back restores the
  immediate `finance_tax_vat` parent.
- Included: Tax settings, VAT/CIT rate-help screens, B2C/B2B policy, 100k tax
  scenario, Provider cost/FCT status, and Finance Audit. Excluded: VAT/CIT
  toggles, tax report period/export, database/config writes, and provider calls.
- Baseline: current main `5c38bd31…` emits all seven controls. Existing direct
  keyboard assertions cover only tax settings and VAT/CIT rate-help Back and
  do not traverse the registered handler. Audit Back was separately reproduced
  and fixed in S12.35.292 on this candidate branch.
- Acceptance: actual emitted controls → registered callback handler → emitted
  child Back → registered handler, with each Back=`menu|finance_tax_vat`, one
  ACK per step, and inert child text/status stubs.
- GREEN: `python.exe -S -m unittest -v tests.test_admin_overview_callback` →
  `Ran 4 tests in 0.836s — OK`. The new matrix clicks all seven controls from
  the emitted tax keyboard through the exact registered handler, verifies each
  inert child screen and its emitted Back to `finance_tax_vat`, then verifies
  the parent screen and one ACK per callback.
- Finding: no additional route/Back defect reproduced in these seven read-only
  children; no `bot.py` change. Test-file `py_compile` exited 0; `git diff
  --check` exited 0 with only pre-existing LF→CRLF notices in unrelated tests.
- Limits: fixture-only; no tax DB/config/report/export/provider/wallet operation
  or real Telegram action. This closes only S12.35.293 route evidence, not all
  Admin/whole-bot routes, live UI rendering/latency, full bot compile, batch CI,
  or final delivery.
- Status: locally verified; final batch CI/delivery pending.

### S12.35.294 — Admin CIT report shortcut Back origin

- Contract: select the actual “Báo cáo TNDN” control emitted by
  `finance_tax_keyboard()`, dispatch it through the registered `menu|` handler,
  then dispatch its emitted report-screen Back. The route must render only an
  inert report fixture and Back must restore `menu|finance_tax_vat`.
- Exclude report database reads/calculations, period changes, exports, config,
  wallet, and provider operations.
- Baseline: `finance_cit_report` shares the report callback branch and
  `finance_tax_report_keyboard()`; no current test traverses this emitted CIT
  shortcut through both registered-handler hops.
- Acceptance: actual emitted CIT button → registered callback → actual report
  Back → registered callback, with expected report keyboard, exact tax-parent
  restoration, and one ACK per step.
- GREEN: `python.exe -S -m unittest -v tests.test_admin_overview_callback` →
  `Ran 5 tests in 1.402s — OK`; test-file `py_compile` exited 0; `git diff
  --check` exited 0 with pre-existing LF→CRLF notices in unrelated tests. The
  emitted CIT callback reached the shared report display stub, emitted the real
  report selector keyboard, and its Back returned to the tax module with one
  ACK for each callback.
- Finding: no CIT report Back mismatch reproduced; no `bot.py` change.
- Limits: inert report display only; no report data/calculation, period update,
  export, database/config write, wallet/provider operation or Telegram action.
  Other report/action routes, live UI latency, full bot compile, batch CI and
  final delivery remain open.
- Status: locally verified; final batch CI/delivery pending.

### S12.35.295 — Consolidated UI batch verification

- Compile full `bot.py`, parse task YAML, run the explicit safe tests in CI
  together with changed tests, and review all WIP against protected engines,
  provider/worker, wallet/payment and AutoPost boundaries.
- Install pytest/PyYAML only in a separate local tool directory. Classify each
  concrete failure before changing its narrow cause. Keep accumulated fixes
  on one batch branch for the agreed single release cycle.
- Acceptance: compile/parse results and complete selected-test results are
  recorded; new failures and protected-scope changes are resolved or explicitly
  deferred. Live latency and runtime acceptance retain their separate gates.
- Full `python.exe -S -m py_compile bot.py` completed with exit 0; bot blob
  `4084700a09990d86c1cb0faf2b3f679fccebaabf`. Task YAML parses using temporary
  PyYAML 6.0.3. Pytest 9.1.1 selected 64 files and collected 577 cases;
  the complete result is pending. Tools are outside the repository.
- Read-only current gate: main=VPS=`5c38bd31…`, bot/web/nginx active/running,
  NRestarts=0; the earlier protected #1420 hold is cleared.
- Status: in progress; batch tests and source comparators are running.

### S12.35.296 — Ticket detail malformed-ID guard

- RED through registered inert fixtures: `ticket|pv` raises IndexError in
  candidate source, while main `5c38bd31…` gives one alert without a read or
  pending loss. Superscript-ID customer/admin detail raises ValueError and
  clears pending on both sources. A pure in-memory SQLite bind confirms an
  out-of-range integer raises OverflowError.
- Contract: change only customer/admin detail ID predicates; reject missing,
  empty, non-ASCII/non-decimal and SQLite-out-of-range IDs before read/cleanup.
  Existing valid IDs, ownership and navigation/recovery behavior stay intact.
- Acceptance: emitted/registered fixture matrix, one alert, zero ticket
  reads/writes, actor and foreign pending preserved; valid-route regressions,
  full bot compile and protected comparison after the minimal fix.
- GREEN: 16 malformed-ID combinations plus foreign recovery assertions passed
  2 tests/15.784s. Full ancestry/reply-origin regression passed 41 tests/206.240s.
  Candidate full compile exited 0; protected text comparator and diff-check
  exited 0. Only the pv/av ID predicates were changed for this defect.
- Status: locally verified; final batch CI/delivery pending.

### S12.35.297 — Single batch sync, PR, CI and delivery

- Commit reviewed WIP, sync/rebase once onto verified current main and compare
  protected source against that exact base. Push one PR; complete Ubuntu CI
  (including Linux workflow hygiene) must pass before merge.
- Deploy the exact merge SHA with `deploy_workers=false` when runtime-to-target
  contains only approved UI changes; verify runtime SHA, services and health.
  Runtime newer than target or an unapproved protected delta stops that deploy.
- Status: review/delivery preparation; client visual/latency remains deferred.

### S12.35.292 — Admin Finance Audit Back origin

- Contract: from Admin `menu|finance_tax_vat`, activate the actual emitted
  “Audit menu” button through the registered `menu|` handler. The audit screen's
  Back must return to its immediate `finance_tax_vat` parent, not Finance root.
- Baseline source evidence on current main `5c38bd31…`: the only inline emitter
  of `menu|finance_menu_audit` is `finance_tax_keyboard()`, but the
  `ADMIN_MENU_PAGE_HANDLERS` entry returns `finance_child_keyboard()` (`menu|finance`).
  The standalone `/finance_menu_audit` command separately uses the generic
  Finance Back and must remain unchanged. Existing tests check audit content but
  do not traverse the emitted inline control through the registered handler.
- Acceptance: test the actual tax keyboard button → exact callback handler →
  actual audit keyboard Back → exact callback handler. Reproduce the wrong
  destination before a minimal route-only change. No DB/report/config/provider/
  wallet operation or real Telegram activity.
- RED: exact emitted `menu|finance_menu_audit` was dispatched through the
  registered `menu|` handler. The Audit screen emitted Back=`menu|finance`,
  while the immediate tax-module parent is `menu|finance_tax_vat` (one
  assertion failure, zero fixture errors).
- Minimal fix: changed only the inline `ADMIN_MENU_PAGE_HANDLERS` entry for
  `finance_menu_audit` to use `finance_tax_child_keyboard()`. The standalone
  `/finance_menu_audit` command still uses its Finance-root Back.
- GREEN: `python.exe -S -m unittest -v tests.test_admin_overview_callback` →
  `Ran 3 tests in 0.577s — OK`; test-file `py_compile` exited 0;
  `git diff --check` exited 0 with existing LF-to-CRLF warnings in unrelated
  tests. The module already runs in CI.
- Limits: source-extracted inert text/render fixture; no production audit/report
  data, DB/config write, provider, wallet, AutoPost, protected engine, or real
  Telegram. Batch CI/release and live performance remain open.
- Status: locally verified; final batch CI/delivery pending.

### S12.35.291 — Admin tax report selector Back origin

- Contract: enter the Admin VAT/CIT module through `menu|finance_tax_vat`, open its emitted VAT/CIT report selector, and dispatch that selector's emitted Back through the registered `menu|` handler. Back must restore the immediate tax module, not Finance root; public access must be rejected before report helpers.
- Scope: inert rendering only. Do not query production reports, generate exports, change tax calculations, touch finance/wallet state, providers, jobs, AutoPost, or protected product engines.
- Baseline source evidence: `ADMIN_MENU_PAGE_HANDLERS` maps `finance_tax_vat` to the tax dashboard and `finance_tax_keyboard`; that keyboard emits the report selector. `finance_tax_report_keyboard()` currently labels Back “Tài chính” and emits `menu|finance`, which is the wrong ancestor. Existing tests cover tax report helpers, not this emitted Back route through the menu handler.
- Acceptance: focused test fails on the wrong destination before the minimal fix and passes after only the report selector's Back label/callback is changed to the immediate tax parent. Check one ACK and public denial before report helpers.
- RED: the first fixture invocation stopped on a missing test-only
  `VIDEO_TAIL9_TEXT_INPUT_KEY` name; after adding that inert fixture stub, the
  registered-handler test failed behaviorally: actual Back was `menu|finance`,
  expected `menu|finance_tax_vat` (one assertion failure, zero setup errors).
- Minimal fix: only `finance_tax_report_keyboard()`'s Back label/callback changed
  to “Thuế / VAT / TNDN” → `menu|finance_tax_vat`; report calculations and tax
  state were not changed.
- GREEN: `python.exe -S -m unittest -v tests.test_admin_overview_callback` →
  `Ran 2 tests in 1.232s — OK`; `tests.test_admin_report_source_availability` →
  `Ran 4 tests in 12.791s — OK`; changed-test `py_compile` exited 0;
  `git diff --check` exited 0 with existing LF-to-CRLF warnings in unrelated
  tests. The route test executes the emitted tax-module controls and exact
  registered menu handler, verifies the immediate-parent Back, one ACK for
  each navigation, and public denial before report helpers.
- Limits: fixture-only, no production tax/report query, export, provider,
  finance/wallet mutation, job, AutoPost, protected engine, or real Telegram.
  Full bot compilation, batch CI, PR/delivery, and live UI latency remain open.
- Status: locally verified; final batch CI/delivery pending.
