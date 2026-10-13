# Telegram UI/callback — batch continuation 11/10/2026

## Latest continuation — 13/10/2026 — S12.35.403/.404

- Integrated full CI #38350432275 and source compile #38350432301 passed for
  HEAD `ab2eb614`. These runs predate the local S12.35.404 correction and do not
  verify the current working tree.
- S12.35.404 reproduced a missing dedicated registration for the emitted
  `vproduct|owner_live_accept` callback; the generic Video handler otherwise
  caught it. The exact Owner handler now registers before the generic route,
  and the generic pattern excludes Owner live-accept.
- RED failed because the dedicated route was absent. GREEN: two route/dedupe
  tests passed in 2.376s; `git diff --check` passed. A new full CI is required.
- The existing handler can admit an Owner-authorized paid Product Video test.
  No callback, provider, wallet or production data was used; no engine code
  changed. The fix remains local to draft PR #1426 and is not live.
- Remaining ordered A3/A5/A6 route coverage, client A7 timing, protected-main /
  runtime reconciliation and the one-batch delivery gate remain open.

## Canonical integration checkpoint — S12.35.403

- Continue in `work/telegram-ui-integration-20261013` on
  `audit/telegram-ui-integration-20261013`, based on current main `e2b48f21`.
  The original dirty checkout remains preserved. The UI patch applied without
  conflicts and without changes to provider/service/worker/router/config or
  deployment files. The bot source comparator lists 26 UI/pending/Support
  functions changed; all other function-source segments match main.
- Targeted suite: `19 passed, 16 subtests passed in 30.23s`. The PayOS-risk
  test-only no-I/O driver supersedes its earlier stalled local invocation.
- Full `py_compile bot.py` session **36866** ended exit `0`. The workflow-selected
  41-module suite **34782** ended `44 failed, 256 passed, 66 subtests passed`.
  Failures were test-fixture dependency/contract drift. Cleanup failures reran
  `16 passed, 7 subtests passed`; Admin action/status modules reran `46 passed`.
  The failure cache is empty. Full Linux CI is required on the draft batch PR.
- Latest VPS read: SHA `381c71bb9e52876eb35b15f5c417ca2cf833dc28`, bot blob
  `d7e4f3da4f07c326571084dcdb5d45e6053090eb`; bot/web/nginx active/running,
  `NRestarts=0`. Main's protected #1424 source is not on runtime. Delivery
  needs its delta reviewed separately; the UI batch has not been deployed.
- Existing GitHub tester labels and UI issue template are available. Two
  candidate cases and scoped operating-document updates were added locally;
  [draft PR #1426](https://github.com/manhtoangreensky-wq/bot/pull/1426) is open.
  No issue/project object was created.
- First Linux CI failed at one missing Package Orders fixture dependency;
  source compile and Media Preview passed. Same-class Menu/Home fixture owners
  and Customer Done dependency have been fixed and verified. Product source
  blob is unchanged; await the test-only follow-up CI before merge/deploy.
- Detailed integration evidence:
  [TELEGRAM_UI_INTEGRATION_20261013.md](TELEGRAM_UI_INTEGRATION_20261013.md).
- Second Linux CI on `a8dbd278` passed the earlier Package/Security gates and
  ran 200 Admin tests, with five namespace fixture errors. Ask/Note/customer
  category dependencies are supplied; exact rerun: 5 tests in 13.174s — OK.
  Push the test-only follow-up to the same draft PR and wait for full CI.

## Latest local checkpoint — 13/10/2026, S12.35.402

- Branch remains `audit/telegram-ui-closure-20261011`, HEAD `523d6c83`.
  Its original PR #1421 is already MERGED; the new local UI changes have not
  been pushed or delivered. Current GitHub main was read at `e2b48f21`.
- S12.35.399/.400 single-ACK manual controls and .401 malformed public Video
  status ACK are locally covered; S12.35.402 fixes Image hub AI choice Back
  across recent-image, photo and document intake, including option → Back → Back.
  Latest result: 4 tests in 6.900s; adjacent intake cases: 2 in 3.708s — OK.
- Actual keyboards, exact callback registrations and production Image pending
  setter/getter were used. A transient origin field selects the hub parent;
  internal caller defaults remain unchanged. This is UI navigation verification.
- Cached pytest/PyYAML exist in `work/ui-closure-test-deps-20261011` and import.
  YAML parser recovered; full compile and consolidated suites still need the
  new source tested. Prior PayOS-risk local no-result run is NOT_VERIFIED.
- Preserve dirty WIP and current main's protected provider/engine changes during
  integration. One batch merge/deploy follows the complete checklist and CI;
  live visual/client timing acceptance and A7 remain open. No paid provider,
  real Telegram, wallet, production data or runtime changes occurred.

The delivery records below describe earlier shipped snapshots.

Status: PR #1421 MERGED and exact-SHA bot-only deployment verified at
`6db4279c9907e964e38de33e46b3e92d37468968`. Whole-goal status remains ACTIVE
for the remaining client/latency acceptance.

Delivery evidence: [PR #1421 comment](https://github.com/manhtoangreensky-wq/bot/pull/1421#issuecomment-6105992470).
Latest latency evidence: [corrected A7 comment](https://github.com/manhtoangreensky-wq/bot/pull/1421#issuecomment-6106125655).
Full merge-SHA CI #38115605781 also completed SUCCESS after deployment.
VPS source blob matches `280e1ab0…`; bot/web/nginx and the three checked workers
are active/running with NRestarts=0, health=ok. The preparation snapshots below
retain their pre-delivery context.

## Current post-delivery checkpoint

- PR #1421 tested head `523d6c835a90a395bf2101f9c85687d1a717b95a` merged to
  `6db4279c9907e964e38de33e46b3e92d37468968`; exact-SHA bot-only deploy
  #38115714586 succeeded with `deploy_workers=false`.
- Strict-host runtime readback matches merge SHA and bot blob
  `280e1ab01fbb1ba055451c598af4bed5df1f2f37`; bot/web/nginx and three checked
  workers are active/running, `NRestarts=0`, health=ok.
- Full PR and merge-SHA CI passed, including Ubuntu workflow hygiene (102
  checks). See S12.35.297 for the complete delivery record.
- Current-main readback (2026-10-11 14:05 +07): GitHub main history shows
  `6db4279c9907e964e38de33e46b3e92d37468968` as latest. Its merge tree and this
  checkout's HEAD tree are both `351ade74f4a93a80fd8964c6fef112e94830ce73`.
  Local `origin/main` is stale at `5c38bd31…`; GitHub CLI/API/web fetch is
  unavailable from the shell. Code source matches current main by tree, but a
  new branch/PR must sync to the full main SHA before editing.
- Scope: emitted callback destinations, Back/Home context, pending expiry,
  callback acknowledgement and display/read scheduling. Processing engines,
  provider/worker, wallet/payment and AutoPost implementation are protected.

## Current local continuation — S12.35.304

- For six emitted Admin Ticket actions, language and ticket SELECT helpers now
  use `asyncio.to_thread`; permissions, one ACK, stale-ticket recovery, pending
  state, Back destination, and write ordering are preserved.
- Targeted `pytest -vv -s --noconftest`: 34 tests plus 2 subtests passed in
  7.94s across Admin Ticket stale/valid/denied/disappearing-assign/read-
  scheduling and Lead-repeat cases. The inert test runner fails if a fixture
  yields for real I/O. Adjacent Ticket Back/origin/pagination regression: 26
  tests passed in 81.084s. Full `bot.py` py_compile exited 0 in 482.344s. Nine
  affected test files compiled, YAML parsed, and `git diff --check` exited 0.
- Ordinary `asyncio.run` on this Windows host stalled in Proactor self-pipe
  `socket.accept` before entering a no-I/O handler; the two direct test fixtures
  now use a fail-on-yield runner. A broader nine-module local pytest run is
  `NOT_VERIFIED`; the two directly affected modules above are green.
- Added the existing Lead-repeat module to Admin route CI. These fixtures do
  not establish live latency. No DB, Telegram, provider, wallet, protected
  engine, AutoPost, merge, deploy, or restart was used.
- Durable details: S12.35.304 in
  [the ordered checklist](TELEGRAM_SMALL_FLOW_AUDIT_CHECKLIST_20261006.md) and
  [.agents state](../.agents/state/telegram-small-flow-audit-20261006.yaml).

## Previous behavior and delivered UI correction

| UI path | Confirmed previous behavior | Delivered behavior / evidence ledger |
|---|---|---|
| Tax report and Finance Audit Back | Skipped Tax/VAT/CIT and returned to Finance root | Immediate tax parent; S12.35.291–.294 |
| Catalog/Account Packages and Large Order | Lost the opening Catalog/Account/detail context | Origin retained across group/detail/Back; compact detail tokens preserve the 64-byte callback limit; .187/.203/.253 |
| Support My Tickets and Feedback receipt | Selected child/result Back lost its opening page | Exact Support/Account/result/list ancestry; .206/.219–.224 |
| Translation voice picker | Missing parent Back; expiry interfered with More/Back | Bounded Language/Media/action/command origin and recovery; .287 |
| Read/display callback acknowledgement | Selected language/SQLite work ran before ACK | Selected Ticket/Archive/Feedback/Document routes ACK before their read/display work; .271–.285 |
| Expired Document/Support input | Could fall through to generic chat | Expired input is consumed and returns to its recovery menu; .210/.212 |
| Ticket detail malformed ID | Missing ID raised IndexError; Unicode ID raised ValueError after pending cleanup | Validate bounded ASCII decimal ID before lookup/cleanup; .296 |

These changes are delivered by PR #1421. The full per-spec RED/GREEN history is in the
[checklist](TELEGRAM_SMALL_FLOW_AUDIT_CHECKLIST_20261006.md) and
[registered-handler evidence](TELEGRAM_CALLBACK_HANDLER_EVIDENCE_20261006.md).

## Verification and release gates

- The initial 64-file run collected 577 items: `77 failed, 507 passed,
  785 subtests passed in 1438.16s`. This run is not a PASS. Failure entries
  include sandbox TEMP/Bash errors and source-fixture expectations; their
  sequential classification is in S12.35.295.
- Broadcast: 4 tests/1.066s OK with usable fixture TEMP. Feedback: 12 tests
  passed/7.13s after one missing inert presentation stub was supplied.
- Package compact-token expectation corrections retain semantic Back checks;
  the two affected matrix methods passed 2 tests/41.145s.
- Ticket malformed-ID and foreign recovery checks passed 2 tests/15.784s;
  full Ticket ancestry/reply-origin regression passed 41 tests/206.240s.
- Source text comparison: 43 UI declaration blocks changed, 2 UI helpers
  added, 0 blocks removed; 5,352 protected-pattern blocks unchanged against
  current main and no
  protected file changes. These are text-block counts, not runtime coverage.
- CI explicitly selects 64 test files; local UI selection is 63 files.
  Ubuntu workflow hygiene passed 102 checks in PR CI.
- Pre-sync candidate full `py_compile bot.py` plus changed ancestry/package
  tests completed with exit 0 at blob `93ed4463…`. The failed-only UI rerun
  returned `7 passed, 79 deselected, 3 subtests passed in 62.78s`, exit 0;
  Package subtest matrices were verified separately as recorded above.
  One final sync/rebase is complete; post-sync Ticket validation passed
  2 tests/12.872s. Full post-sync compile completed with exit 0. PR/merge-SHA
  CI, one squash merge and exact-SHA bot-only deployment are complete as
  recorded in S12.35.297; remaining work is client/all-button acceptance.

## Tester handoff and difficult residual cases

Use the UI cases in [DANH-SACH-CASE.md](../../KIEM-THU/DANH-SACH-CASE.md)
and the existing `.github/ISSUE_TEMPLATE/05-telegram-ui-callback.yml`.
Record the exact path, expected/actual parent, HH:MM:SS +07, spinner duration
and screen duration. The fixture cases can run without a production action.

- A recent Account → Back tap matched `main_home` at 13:03:51.894 +07; bot
  dispatch took 199.984 ms and the awaited render helper 83.945 ms. The exact
  client screen appeared in under 1s per the Owner. This route sample meets the
  timing check; earlier 2–3s reports and all other button latency remain open.
  No network/device/VPS purchase diagnosis is supported.
- Telegram client wrapping/visual QA and all-button smoothness remain unverified.
- The Image Story aspect/prompt mismatch (.106) remains excluded by Owner.
  The aspect experiment and dependent .108 are absent from this batch.

## New Account → Back sample — 2026-10-11 13:03:51 +07

The Owner reported tapping “just now”. A read-only sanitized journal query found
exactly one `main_home` event at 13:03:51.894 +07. The bot's full callback
dispatch was 199.984 ms; its awaited render helper was 83.945 ms, and the
route-specific timing recorded `render_returned=1`. The exact tap's client
screen appeared in under 1s per the Owner. This confirms the event reached and
completed the bot handler quickly; it does not measure transport before bot
receipt or client display after the edit call. A7 and whole-goal status remain open.

A full-route, strict-host, sanitized 24-hour aggregate-only census had
`journalctl_exit=0`, zero parse failures and empty stderr, with only 2 callback
timing rows: `account_root` n=1 with dispatch/guard/handler/render-helper
avg=max 295.2/27.5/267.0/170.8 ms, and the correlated `main_home` n=1 with
200.0/26.3/173.0/83.9 ms. No callback exceeded 500 ms (or 1,000/2,000 ms);
the targeted timeout/network/connection/Telegram-retry signature scan found
zero matches. The `account_root` sample has no client-timed correlation; two
rows do not establish a latency distribution or network/device cause. Other
callback families and ReplyKeyboard latency have no observation in this
window. The evidence is summarized in the
[corrected A7 comment](https://github.com/manhtoangreensky-wq/bot/pull/1421#issuecomment-6106125655).

The Owner separately reported “Bảng giá” appeared immediately (<1s), without
an exact `HH:MM:SS +07`; retain it as uncorrelated client-only evidence. The
next narrow sample is `/start` → “Tạo video AI” → “Quay lại”, with each screen
duration/time recorded separately and no job confirmation.

Source-only latency candidate (not a reproduced defect): the registered PayOS
package-choice route runs `expire_old_payos_orders()` before answering the
callback; the helper synchronously updates/commits expired payment orders. The
source declares no secondary `(status, expires_at)` index, and a schema-shaped
in-memory SQLite plan reports a table scan. No production DB/query plan or
client-timed tap was observed. No payment behavior was changed; any ordering or
offload change needs a separate reviewed contract and explicit approval.

Local timing-instrumentation regression `python -m unittest -v
tests.test_callback_dispatch_timing` passed 5 tests in 6.791s. The direct
pytest attempt for `tests/test_menu_video_callback_timing.py` could not start
because the bundled interpreter lacks pytest; both files are selected by CI,
and PR #1421 CI passed. This does not replace an actual timed Telegram-client
sample.
The documented eight-case stdlib rerun against this tree returned no output for
over 100s and was interrupted (exit 1); that attempt is NOT_VERIFIED, not a
product failure. The earlier recorded eight-case pass and current PR CI remain
separate evidence.

`MERGED != DEPLOYED != LIVE`. A local test or active service does not establish
client smoothness or product-output success.

## Latest click attempt — 2026-10-11 14:17 +07

The Owner reported completing `/start` → “Tạo video AI” → “Quay lại”. After a
parser self-test caught an over-escaped regex in the first attempt, the same
strict-host, read-only 07:17–07:19 UTC journal window was parsed correctly.
“Tạo video AI” dispatch was 165.782ms (render 72.066ms); the subsequent Back
dispatch was 5,678.657ms, with 5,582.814ms inside render/edit. ACK and local
menu phases were fast. No `safe_edit_query_message` fallback warnings occurred.
Source confirms the shared helper awaits `query.edit_message_text`, but current
metrics cannot distinguish Telegram/API/network time from event-loop scheduling.
Three unauthenticated public API-root probes from the VPS took 707–735ms to an
HTTP 302 response; these do not reproduce the authenticated edit call. Per-screen
client durations remain unreported. The installed runtime is python-telegram-bot
22.7 / HTTPX 0.28.1; its default HTTPXRequest read/connect/write timeout is 5s
(pool timeout 1s), and source sets no override for this edit. The 5.583s result
is near that default but returned successfully, so this does not prove a timeout
or justify changing it. Do not change shared edit behavior or recommend
infrastructure purchase without stronger attribution; keep the goal open.

## Local follow-up after PR #1421 — S12.35.299 (not delivered)

- Rechecked the earlier Archive pre-ACK concern against current source and its
  registered-handler regression: Archive `view`/`file` already ACK before the
  owner-scoped SELECT and offload that lookup. The old S12.35.207 note is now
  explicitly marked superseded by S12.35.271; no Archive code change was needed.
- A separate Document Tool `docflow|confirm` RED showed its valid confirmation
  path called SQLite-backed `get_user_language()` before ACK. The local patch
  preserves the too-few-files alert, ACKs valid confirmation once, and offloads
  only that language read through `asyncio.to_thread`. The document-processing
  runner is unchanged.
- Four focused no-I/O assertions passed (valid confirm, insufficient-file
  alert, Send More, and Back). The test module is selected in CI and its
  `py_compile` passed. Full `bot.py` `py_compile` produced no output for over
  100 seconds and was interrupted; record NOT_VERIFIED, not a compile failure.
  No CI, commit, push, PR update, merge, deploy or restart has run for this local
  follow-up.
- The 14:17 `menu|main` sample remains separate and unresolved: the server spent
  5.583s in its awaited Telegram edit, but Owner-observed client durations are
  still missing and the event cannot distinguish transport/API wait from event
  loop scheduling. Keep A7 open and continue the remaining ordered audit.
## Corrected latest tap-window check — 2026-10-11 08:00–08:15 UTC

The Owner confirmed performing the requested Video-menu → Back tap, but did not
include a tap timestamp, whether each screen appeared, or client-observed
durations. The first journal-window attempt mistakenly supplied local +07 time
to the UTC VPS journal and is discarded. The corrected strict-host, sanitized
query returned JOURNALCTL_EXIT=0, JOURNALCTL_STDERR_BYTES=0, and MATCH_COUNT=0
for menu|main_video / menu|main timing rows.

At the same check the VPS readback showed toanaas-bot.service active/running,
NRestarts=0, runtime SHA 6db4279c9907e964e38de33e46b3e92d37468968, and callback
timing instrumentation in runtime source. This establishes the service and
instrumentation were present, not that the exact tap reached the handler or how
quickly the Telegram client rendered it. A7 remains open; no network, Telegram,
VPS, device, or client cause is established. No raw logs/IDs/payloads, code,
runtime, deployment, or restart action occurred.

S12.35.299 continuation verification: the bundled-Python direct runner returned
4 focused Document Tool assertions: OK; the test file compiled and git diff
check exited 0. A full bot.py syntax compile produced no output for over 120s
and was interrupted, so it remains NOT_VERIFIED. Consolidated CI/delivery is
still pending.

## S12.35.300 — PayOS package callback ACK order

An inert source-extracted regression followed helper-generated
payos_pkg|50k|123 through the production handle_package_choice registration.
RED recorded expire → ACK: expire_old_payos_orders synchronously opens SQLite,
updates expired pending orders, commits, and closes before answering Telegram.
The minimal fix moves only query.answer() before that cleanup; the cleanup
remains before package parsing/guards/order work. No order amount, payment,
PayOS, Xu, wallet or production-data behavior was changed.

The combined focused runner returned 5 callback assertions: OK (including the
four Document Tool assertions); both changed test files compiled and
git diff --check exited 0. The regression is included in the explicit CI test
selection, alongside the existing profile-top-up emitted-control test.
No PayOS call, DB/order write, wallet operation, real Telegram action, commit,
push, PR, merge, deploy or restart occurred. Full bot.py compile remains
NOT_VERIFIED after the >120-second no-output attempt; consolidated CI is still
required. This is a server-side ACK-order improvement, not proof of end-to-end
client smoothness; the later screen update still awaits the cleanup. Keep the
whole audit and A7 latency acceptance open.

The existing profile-top-up emitted-control module is selected in CI. A fresh
bundled-Python `python -m unittest -v tests.test_profile_topup_back_origin`
completed with `Ran 5 tests in 10.116s — OK`, including the emitted manual-
top-up route and Account/selector Back cases. This supersedes the earlier
55-second stalled local run (NOT_VERIFIED, not a test failure). The five-minute
whole-file compile attempt still leaves the combined WIP's full `bot.py`
compile NOT_VERIFIED; consolidated CI/source compile remains required.

## Latest Owner tap check — 2026-10-11 15:59 +07

The Owner confirmed completing the requested `/start` → “Tạo video AI” →
“Quay lại” path but provided no exact tap time, per-screen outcome, or client
duration. One strict-host SSH query summarized only the two approved menu
timing routes for `2026-10-11 08:52–09:05 UTC` (`15:52–16:05 +07`):
`JOURNALCTL_EXIT=0`, `JOURNALCTL_STDERR_BYTES=0`, `PARSE_FAILURES=0`, and zero
matching dispatcher/phase events for `main_video` and `main_home`. The empty
window does not show whether either tap reached Telegram/the handler and cannot
locate client-visible delay. A7 remains open; no network, Telegram, VPS, or
device cause is inferred. No raw logs, IDs, payloads, runtime/source changes,
provider, wallet, payment, deploy, or restart occurred.

## Latest tap-window check — 2026-10-11 15:30 +07

The Owner confirmed tapping the requested `/start` → “Tạo video AI” →
“Quay lại” path but did not report the exact tap timestamp, screen outcomes,
or per-screen display durations. A strict-host SSH query reduced the approved
menu timing fields to route counts and average/maximum only for 2026-10-11
08:20–08:32 UTC (15:20–15:32 +07). `JOURNALCTL_EXIT=0`, stderr 0 bytes,
parse failures 0; counts were zero for `main_video`, `main_home`,
`menu|main_video`, and `menu|main`. No raw log, ID, or payload was returned.
The empty window does not prove whether the taps reached the handler or
whether Telegram displayed either screen; it cannot locate a delay. A7 remains
open. Request only the two approximate screen durations/outcomes if the Owner
can provide them; meanwhile continue the ordered offline A3/A5/A6 audit.
No runtime, source, payment, provider, wallet, production-data, deploy, or
restart action occurred during this check.

## Combined WIP verification refresh — 2026-10-11

The bundled-Python direct runner re-executed the registered Document Tool and
PayOS package-choice callback regressions: 5 focused assertions returned OK;
both test files compiled and `git diff --check` was clean. A fresh full
`python -m py_compile bot.py` attempt remained live without output for five
minutes and was interrupted; record `NOT_VERIFIED`, not a syntax failure.
Consolidated CI/source compile is still required before delivery. The local
bundled Python also lacks PyYAML, so the updated state YAML was not locally
parsed; `.github/workflows/ci-main.yml` contains the authoritative PyYAML parse
gate, which remains pending until consolidated CI.

## Continuation — 2026-10-11 16:19 +07

- Owner confirmed another `/start` → “Tạo video AI” → “Quay lại” tap. The
  approved aggregate-only SSH window `09:15–09:30 UTC` returned journalctl
  exit 0, stderr 0 bytes, parse failures 0, and zero `menu|main` / `menu|main_video`
  callback latency events. No exact tap timestamp or client durations were
  provided; this is not a diagnosis. A subsequent read-only metadata check
  confirmed runtime `6db4279c9907e964e38de33e46b3e92d37468968`, bot active/running,
  `NRestarts=0`, and both timing-source markers present. A7 stays open.
- Offline Admin Ticket stale-assign recovery evidence showed the product's
  `menu|admin_support` Back is correct; one fixture assertion had stale
  `menu|admin`. Only the test expectation was aligned, and the pytest-style
  module was added to the existing CI regression selection. The no-I/O run
  completed 19 assertions; adjacent Admin Ticket hub regression passed 7 tests.
- No production code, provider, wallet, AutoPost, or protected engine changed.
  CI/source compile and whole-goal A3/A5/A6/A7 completion remain pending. Keep
  the accumulated one-batch delivery rule; do not create a separate PR for this
  test alignment.

## Continuation — 2026-10-11 16:31 +07

- Strengthened S12.35.303 from helper-generated input to the six actual
  `main_topup_keyboard()` PayOS controls. Each was matched to the registered
  handler and ACKed once before an inert expiry seam; execution stopped before
  package/payment logic.
- The exact emitted-route fixture passed, and the CI-selected Top-up navigation
  module passed 5 tests in 20.255s. No new production mismatch was reproduced;
  test-file compilation and diff check passed. Standard pytest/full CI and whole
  source compile remain pending.
- The earlier no-event Video/Back tap window remains inconclusive despite the
  active runtime and installed timing markers; no client duration was supplied.
  Do not diagnose or patch transport/render latency from that empty sample.
- WIP remains on the single batch branch. No push, merge, deployment, restart,
  real payment, provider, wallet, production data, AutoPost, or protected engine
  operation occurred.

## Latest Owner click report — 2026-10-11 16:37 +07

- Owner reports both “Tạo video AI” and “Quay lại” screens appeared in under
  one second on the latest `/start` → Video → Back path. Exact tap time and
  separate durations were not supplied. Record this as one positive client
  observation; it does not establish that every bot button is smooth.
- The already-approved 16:15–16:30 +07 aggregate window had valid journal
  execution but zero events for `menu|main` and `menu|main_video`; it cannot be
  correlated with this report. Runtime readback was
  `6db4279c9907e964e38de33e46b3e92d37468968`, active/running, `NRestarts=0`,
  timing markers present. No transport or infrastructure cause is established.
- Do not ask the Owner to repeat this exact Video → Back measurement absent a
  new reason. A7 remains open for other callback/message routes and repeatable
  time-correlated samples; full compile, consolidated CI, and the single-batch
  release gate also remain pending.
- Local checkpoint updated and the same concise report was published on the
  already-merged UI batch PR #1410:
  https://github.com/manhtoangreensky-wq/bot/pull/1410#issuecomment-6107692017.
  GitHub CLI authentication remains invalid, but the signed-in web session
  completed the comment. Nothing was posted to Product Video PR #1409.

## Continuation — 2026-10-11 — S12.35.305

- Closed one narrow Admin Ticket responsiveness gap: the three actual status
  controls previously read language and ticket through synchronous SQLite
  helpers on the event loop. A RED/GREEN matrix now proves both reads use the
  existing `asyncio.to_thread` seam for `resolved`, `refund_pending`, and
  `waiting_provider`, while preserving the stale alert, single ACK, update
  order, first-transition refund notice, and list/Main navigation.
- Combined focused pytest: 43 passed in 10.41s. The stale/malformed status
  callback module is now included in the existing Small Navigation CI step.
  The three changed test modules compile; audit-state/workflow YAML parse and
  diff check pass.
  No provider, wallet/payment, production data, real Telegram, AutoPost, or
  protected engine behavior changed.
- This removes event-loop blocking work; it is not proof that the Telegram
  client spinner or rendered screen is faster. Client-latency acceptance A7
  remains partial. Full current-source compile, final CI, current-main sync,
  protected-source comparison, and the one-batch release gate are still open.
- No push, PR update, merge, deploy, restart, or direct Telegram message was
  performed in this continuation.

## Continuation — 2026-10-11 — S12.35.306

- Admin-confirmed reply Send's language/ticket SELECTs are now scheduled through
  the existing thread seam. The actual preview-generated callback preserves
  token expiry, Admin-only guard, one ACK before the fake send, send lock,
  retry-on-failure and ticket history behavior.
- Combined focused pytest returned 48 passed plus 2 subtests in 19.23s. A later
  selector-based standard-library recheck of the dedicated send-concurrency
  module returned `Ran 2 tests in 0.855s — OK`. The no-I/O selector rejects
  descriptor registration and verifies one send for concurrent taps, replacement
  preview preservation, and retry after simulated failure. Ubuntu CI remains in
  the batch gate.
- No actual customer message or production data was touched. This source fix
  only removes synchronous SQLite reads from the bot event loop; it does not
  prove user-visible latency improved. Full compile/CI, protected-source sync,
  and the one-batch delivery gate remain open.

## Continuation — 2026-10-11 — S12.35.307

- Admin Ticket “📎 Xem file đính kèm” had the same narrow event-loop read gap:
  language and attachment-ticket SELECTs were synchronous. Only those reads are
  now routed through the existing `asyncio.to_thread` seam; Admin guard, ACK,
  duplicate lock, photo/document choice, failure reply and cleanup are intact.
- RED/GREEN: the new emitted-button test failed in both document/photo variants
  before the change. Afterward the focused check passed; the combined related
  Admin Ticket action/status/Send/Lead/refund/file no-I/O run returned
  `57 passed, 6 subtests passed in 29.88s` (only the file duplicate-tap case was
  deselected), including stale ticket, non-admin denial, resend, and fake-send
  retry/cleanup.
- The file duplicate-tap asyncio test initially stalled during Windows
  event-loop setup. A later no-I/O selector recheck passed the complete module:
  `Ran 7 tests in 2.139s — OK`, including the concurrent duplicate guard. The
  test remains in existing Ubuntu CI. No new CI selection was needed.
- This is callback read scheduling evidence, not live file delivery or proof
  of improved Telegram-client latency. Full source compile, consolidated CI,
  current-main/protected-source comparison, and one-batch release remain open.
- Only fixture metadata and fake Telegram sink were used; no real file/message,
  production ticket, provider, wallet/payment, AutoPost, or protected engine
  behavior changed. No push, merge, deploy or restart.

## Continuation — 2026-10-11 — S12.35.308

- The real Admin Support “🎧 Ticket admin” control reached `ticket|admin`; its
  successful route needlessly queried SQLite for language before ACK even
  though the destination uses fixed Admin text/keyboard.
- The new test was RED on the observed getter call. The narrow fix skips that
  unused lookup only for the exact valid callback and an authorized Admin;
  public denial and all other callback language behavior remain unchanged.
- Focused test passed; the complete CI-selected Ticket hub module passed
  `8 tests, 6 subtests in 16.31s`, including public-denial and Back/origin
  regressions. No CI workflow edit or live-latency claim.
- Combined related Ticket regression across S12.35.304–.308 passed
  `65 tests, 12 subtests in 132.15s`; one file duplicate-tap case was
  deselected because the Windows async runner stalls before test execution and
  remains pending Linux CI.
- Whole-bot compile, full CI, protected-source/main comparison, A7 and the
  single-batch release gate remain open. No production DB, message, provider,
  wallet, AutoPost, protected engine, push, merge, deploy or restart.

## Continuation — 2026-10-11 — S12.35.309

- The actual Admin Support → Ticket hub → “Ticket mới” button also read the
  SQLite language field before ACK even though list output is fixed-language.
  RED observed the call on the registered `ticket|al|new|0` route.
- Only valid list callbacks from an authorized Admin now skip that unused
  lookup. Filter, offset, ACK, list payload and public/malformed denial behavior
  remain intact.
- Focused test passed; the complete Ticket hub module passed
  `9 tests, 6 subtests in 43.04s`. Existing CI selection covers the module; no
  workflow change was needed. This is source-level responsiveness evidence, not
  a live client timing result.
- Whole-bot compile, consolidated CI, protected-source/main comparison, A7 and
  one-batch delivery remain open. No production data, message, provider, wallet,
  AutoPost or protected engine was touched.

## Continuation — 2026-10-11 — S12.35.310

- Stats, Templates, Search-by-User and Search-Ticket buttons from the actual
  Admin Ticket hub all made an unused SQLite language lookup before ACK on
  valid Admin callbacks.
- RED reproduced all four getter calls. The narrow guard now skips the lookup
  only for those exact valid Admin callback shapes; reports, Search pending,
  Back/Home, invalid/legacy routing and public denial are unchanged.
- Focused matrix passed `1 test, 4 subtests in 4.77s`; the full CI-selected hub
  module passed `10 tests, 10 subtests in 14.76s`. A fixture assertion on Search
  cleanup was corrected to match the pre-existing set-pending behavior; that
  correction did not change production code.
- Combined adjacent regression, test compilation, full bot compile, final CI,
  protected-source comparison, A7 and single-batch release remain open. No live
  delay measurement is claimed.

## Continuation — 2026-10-11 — S12.35.311

- Closed the Admin Ticket detail route's unused locale-read gap for only exact,
  validated Admin detail callbacks. The actual emitted detail and stale cases
  preserve the early ACK, necessary offloaded ticket SELECT, current screen or
  list/Home recovery; unauthorized denial still occurs before ticket access.
- RED had shown one unused `get_user_language()` call on both authorized paths.
  Focused GREEN: `Ran 3 tests in 11.088s — OK` for valid detail, stale recovery,
  and unauthorized denial. The fixture uses an inert no-I/O coroutine runner
  because Windows event-loop setup stalled before handler execution.
- No CI edit was needed; the test file is already in the selected small-flow
  suite. This is source-level event-loop evidence only, not proof of a faster
  Telegram client render or diagnosis of network/device delay.
- `faulthandler` identified the prior local stall at Windows
  `_fallback_socketpair` during `asyncio.run` loop initialization, before the
  callback ran. These fixtures are no-I/O; their async seams are inert fakes.
  Replacing only test-driver invocations with `_run_inert` (which asserts no
  unexpected yield) resolved the harness issue. The full module now passes
  `Ran 19 tests in 63.943s — OK`; test-file `py_compile` and diff check exit 0.
- Pending: full bot compile, consolidated CI, current-main/protected-source
  comparison, state YAML parse in CI, A7, and the one-batch release gate. Local
  PyYAML install was denied under sandbox TEMP; no project dependency changed.
  No production ticket/data, Telegram send, provider, wallet/payment, AutoPost,
  or protected engine was touched.

## Continuation — 2026-10-11 — S12.35.313 Memory confirmation replay

- Added a focused assertion to the existing CI-selected Memory callback test:
  after a valid delete confirmation, replay the same emitted payload using a
  new fixture callback-query ID. The registered `^memory\|` handler ACKs once,
  rejects the consumed confirmation, and performs no second archive update or
  event. The focused test passed (`1 test in 0.831s — OK`) using the existing
  inert no-I/O runner; test-file compilation and `git diff --check` passed.
- Source already consumes the matching pending token before synchronous
  archive work. No production handler change was warranted. The fixture covers
  sequential same-payload replay, not live Telegram rendering or cross-process
  concurrency.
- Pending: combined CI, full `bot.py` compile, exact-main/protected-source
  comparison, A7 client-latency acceptance, and the single-batch PR/merge/deploy
  gate. No production data, wallet/payment, provider, real Telegram send,
  protected engine, merge, deploy, or restart was touched.

## Continuation — 2026-10-11 — S12.35.314 Music suggestion Back

- Verified the existing suggestion/details Back callbacks across showroom and
  Video Add-on contexts through the registered `music_quick` handler. Fifteen
  inert cases passed: owned style/lyrics/background input is cleared while the
  exact Suggestions screen/result and unrelated state remain; stale other-
  context input is preserved; ordinary text after Back is not consumed.
- No Music generation, media, provider, or price-summary route was invoked and
  no production code changed. The pytest module has been added to the existing
  small-navigation CI selection; final CI is still pending.
- Remaining: whole-bot compile, consolidated CI, current-main/protected-source
  comparison, A7 client-latency acceptance, and the single-batch release gate.
  No push, PR update, merge, deploy, or restart occurred.

## Continuation — 2026-10-11 18:26 +07 — A7 all-callback aggregate

- A read-only 24-hour aggregate returned four callback events across three
  route groups. `menu|main_video` (admin, n=1) rendered in 72.066ms and
  dispatched in 135.942ms. `menu|main` (admin, n=2) had render average/max
  2833.405/5582.814ms and dispatch average/max 2909.028/5678.657ms.
  `account_root` (n=1) dispatched in 295.238ms. Only aggregate counts and
  timings were returned, never raw logs, IDs or payloads.
- The single Home outlier was spent in the awaited Telegram edit/render phase;
  pre-ACK, language, cleanup and build phases stayed fast. It localizes the
  server wait to the edit call but cannot attribute it to Telegram, VPS network,
  or client rendering. The Owner-reported latest Video → Back was <1s without
  an exact timestamp, so it cannot be matched to the slow event.
- No edit to the shared render helper is justified by this lone uncorrelated
  server-side sample, especially because it is shared by protected product
  flows. Other routes had no samples; all-button smoothness remains unverified
  and A7 partial. No source/runtime change, send, provider, wallet, deploy or
  restart occurred.
- Read-only `git ls-remote` confirmed GitHub main remains
  `6db4279c9907e964e38de33e46b3e92d37468968`. Local HEAD `523d6c8` has tree
  `351ade74`, matching the previously verified main tree; local `origin/main`
  remains stale at `5c38bd31`. No fetch/rebase was done. Re-fetch and compare the
  exact main/protected delta again immediately before the one-batch delivery.

## Continuation — 2026-10-11 — S12.35.315 Translation → SubDub landing navigation

- The public Main keyboard emitted `menu|translate`; the Translation center
  emitted `menu|translation_video_factory`. Both reached the registered
  `^menu\\|` handler. The landing emitted Back to Translation and Home to Main.
- One focused registered-handler unittest passed (`Ran 1 test in 1.008s — OK`).
  It verifies the actor's menu-only SubDub pending marker clears on Back/Home
  while another user's marker remains. The test module is already CI-selected;
  no workflow or production code change was made.
- The `videodub|` choices were never dispatched; no media, job, provider,
  wallet, production data, AutoPost, or protected processing engine was touched.
- Fresh read-only `git ls-remote` now confirms main `6db4279c9907e964e38de33e46b3e92d37468968`;
  after turn-scoped network permission, `git fetch --no-tags origin main`
  updated the local ref. `HEAD` and `origin/main` trees both equal
  `351ade74f4a93a80fd8964c6fef112e94830ce73`; the local `bot.py` diff contains
  no hunk for the tested Translation/SubDub route or pending-clear helpers.
- New checkpoint posted and read back on [PR #1410](https://github.com/manhtoangreensky-wq/bot/pull/1410#issuecomment-6109340170).
  The prior Video → Back user-timing note remains at
  [comment #6107692017](https://github.com/manhtoangreensky-wq/bot/pull/1410#issuecomment-6107692017); it was not duplicated.
- Consolidated CI, full bot compile, full protected-source comparison,
  remaining A3/A5/A6/A7 routes and batch delivery remain open. No push, merge,
  deploy, or restart occurred.

## Continuation — 2026-10-11 — S12.35.316 whole-bot compile probe

- The shell did not resolve bare `python`; the configured bundled workspace
  interpreter was used for `python -m py_compile bot.py`. It produced no output
  or exit result after about 60 seconds and was interrupted. Record
  `NOT_VERIFIED`, not a syntax failure or a pass; do not repeat without a changed
  runner/source. Consolidated Ubuntu CI/source-compile remains required.
- No source change or production side effect. The authorized S12.35.315
  checkpoint and Video → Back note are already present on PR #1410, so neither
  was duplicated. Whole-goal audit, exact-main/protected-source check, A7 and
  one-batch delivery remain open.

## Continuation — 2026-10-11 — current-main/protected-source comparator

- Read-only GitHub main SHA is still `6db4279c9907e964e38de33e46b3e92d37468968`;
  local `origin/main` matches. Audit HEAD `523d6c8` and main both have tree
  `351ade74`. The working-tree comparator found no changes in protected
  service/provider/worker/deploy/config directories. `bot.py` diffs are confined
  to package-choice ACK ordering, Ticket navigation/ACK/read scheduling, and
  Document Tool ACK/read scheduling; no protected product engine or AutoPost
  hunk is present.
- This completes the source-scope gate only. It does not complete functional
  audit, full compile, consolidated CI, A7 evidence, or batch delivery. No
  fetch/rebase, push, merge, deploy, or restart.

## Local continuation — S12.35.318 — PayOS duplicate callback guard

- The actual emitted `payos_pkg|10k|123` button was dispatched twice through
  its registered handler. Both fixture callback coroutines waited at ACK; the
  first created one pending auto-topup order in in-memory SQLite and stopped at
  a deliberately suspended fake PayOS request. The second then hit the actual
  source-extracted `payos_auto_topup_guard`, rendered `cooldown_5m`, and created
  no second order. Direct bundled-Python result: `PASS`; one fixture order,
  zero production DB/provider/wallet effects.
- An earlier probe used a permissive stub guard and produced two fixture rows;
  it was not representative and is discarded as a product finding. The follow-up
  used the actual guard logic and reproduced single-order behavior.
- No payment code, external service, live config/secrets, or endpoint was
  changed or called. The optional Web Billing path awaits the external
  `/billing/create-payment-link` endpoint before a local PayOS order is stored;
  its duplicate/idempotency behavior remains explicitly unverified.
- No source change, CI change, push, PR, merge, deploy or restart. Continue the
  ordered non-financial A3/A5/A6 evidence gaps; keep A7 partial and do not repeat
  this fixture absent new evidence.

## S12.35.319 — PayOS foreign-owner single ACK (locally verified)

- Owner approved the narrow ACK-only callback change on 2026-10-11. The initial
  emitted-control/registered-handler fixture was RED (`1 failed, 1 passed`): a
  foreign user received an empty ACK followed by the denial alert.
- The minimal handler change selects the foreign-owner alert before the normal
  ACK, preserves exactly one owner ACK before expiry cleanup, and preserves one
  normal ACK plus expiry cleanup for malformed-length callbacks. Expiry cleanup
  remains in place for valid and foreign-owner callbacks after their single ACK.
- GREEN: the actual emitted/registered callback fixture returned
  `3 passed in 2.46s` (owner ACK order, one foreign-owner alert, malformed-length
  ACK/cleanup); the focused test file's `py_compile` exited 0. A full local
  `python -m py_compile bot.py` produced no output and was interrupted after
  more than three minutes, so record it as `NOT_VERIFIED`, not as a syntax
  failure. On the next continuation, the exact CI guard
  `python scripts/check_bot_source_compile.py` also produced no output for four
  minutes and was interrupted (`NOT_VERIFIED`, not a syntax failure). Do not
  repeat the same local whole-file compile; rely on the batch CI runner for that
  gate. The focused test is already in the explicit CI regression selection.
- No package amount, order creation, cooldown, settlement, payment, Xu, wallet,
  provider, or production-data behavior changed. Fixture-only; provider calls,
  wallet mutations, and production DB operations were zero.
- S12.35.318 remains closed only for its tested legacy checkout replay path.
  Web Billing idempotency remains unverified; no runtime config, secret, or
  endpoint was inspected or used. No GitHub comment, push, merge, deploy, or
  restart was made. Continue the remaining ordered audit; do not repeat this
  fixture absent new evidence.

### S12.35.319 local verification refresh — 2026-10-11

- Re-ran all three plain test functions against the current worktree with the
  bundled Python no-I/O runner: `PASS: 3 package-choice callback assertions`;
  focused test-file `py_compile` exited 0. `git diff --check` exited 0 with the
  existing unrelated LF-to-CRLF warning in `tests/test_profile_topup_back_origin.py`.
- A fresh `python -m pytest` attempt was not runnable because this bundled
  interpreter has no `pytest` module. The earlier pytest result remains
  historical evidence; this refresh is direct function execution, not a new
  pytest/CI pass. Do not repeat the known stalled whole-bot compile locally;
  consolidated CI/source compile remains the batch gate.

## S12.35.320 — Admin Ticket prompt Back/pending cleanup (local fixture green)

- Audited actual Admin Ticket Reply, Ask, and Note prompt controls through the
  registered `ticket|` handler. Each emitted Back is `ticket|av|41|new|0`; it
  returns to the same Ticket detail, ACKs once, clears only actor 501's pending
  input via the actual helper, and preserves user 999's fixture state.
- Sixteen focused no-I/O test-function cases passed; changed test-file
  `py_compile` and `git diff --check` exited 0. The first matrix run's failure
  was a fixture expectation omitting the final render (not a product failure);
  after matching observed ACK → clear → read → render order, the matrix passed.
- No bot source change, ticket write, submitted text, message send, production
  data, provider, wallet, AutoPost, protected engine, merge, deploy or restart.
  Full compile/CI, broader route audit, A7 and one-batch delivery remain open.

## S12.35.321 — Suggested-music static callback route

- Built the five controls emitted by `suggest_music_style_keyboard()` and
  dispatched every callback through the exact registered handler. Each ACKed
  once and returned its matching static `/music_library` suggestion; unknown
  style stayed on the safe fallback. No route/UI defect was reproduced, so no
  production source changed.
- Direct bundled-Python no-I/O run: `PASS: 2 suggest-music callback route
  tests`; focused test `py_compile`, CI-selection check, and `git diff --check`
  exited 0. The new focused test is in the existing safe-navigation CI list;
  local direct invocation is not a pytest/CI pass.
- No real Telegram send, Music search/playback, provider, wallet, DB, AutoPost,
  protected engine, merge, deploy, restart or runtime change. Continue other
  in-scope A3/A5/A6 callback gaps; keep all-button latency and A7 acceptance
  partial. Consolidated CI/source compile and the one-batch delivery gate remain
  open.

## Continuation — S12.35.322 — current main protected-delta hold

- Current local `origin/main` is `381c71bb9e52876eb35b15f5c417ca2cf833dc28`,
  matching the preceding continuation's read-only remote SHA. Audit HEAD remains
  `523d6c835a90a395bf2101f9c85687d1a717b95a`; merge-base is
  `5c38bd31c20f26f815e2f05b6419f4dd64afbba9`.
- Main contains #1423 beyond the #1421 UI checkpoint. Its two `bot.py` hunks are
  spend guards before SubDub ASR transport and Product Video task submission; a
  focused diff search found no callback/keyboard/route hunk. Its remaining
  changes are provider/service files; no `workers/`, `deploy/`, or `config/` path
  changes. The exact file list and tree SHAs are in S12.35.322 of the checklist/
  state. The audit working tree itself has no local change under `services/`,
  `providers/`, `workers/`, `deploy/`, or `config/`.
- No rebase, cherry-pick, push, merge, deploy or restart was attempted. Keep
  #1423 out of the UX batch until the final protected-source review; continue
  safe local UI evidence while A3/A5/A6/A7 and consolidated CI remain open.

## Continuation — S12.35.323 — A7 edit-wait source trace

- The existing matched Video-menu → Back sample spent `5,582.814ms` in render,
  of `5,678.657ms` total; ACK was `42.933ms`, while local language/cleanup/build
  phases were each under `21ms`.
- Source shows the callback ACK precedes local menu render; the measured render
  wrapper spans `safe_edit_query_message` → awaited `query.edit_message_text`.
  PTB 22.7 / HTTPX 0.28.1 are pinned, but this app builder sets no explicit
  connect/read/write/pool timeout values. The existing metric cannot decompose
  request pool, DNS/TCP/TLS/network, Bot API response, and client display.
- This localizes one slow sample to the awaited edit boundary only. It does not
  prove a network, VPS, Telegram-service, or device cause; later `<1s` reports
  lacked a matching exact tap time. No timeout/transport change or hardware
  recommendation is justified. A7 remains partial pending correlated samples or
  request-phase telemetry; no new tap, Bot API call, network probe, config/code
  change, Telegram send, merge, deploy, or restart occurred.

## Continuation — S12.35.328 — Admin PayOS Risk report route

- The actual `payrisk|report` control was emitted by the Admin risk keyboard and
  dispatched through the registered callback. An inert no-yield fixture observed
  one ACK, one fixture audit event, the expected report render, and the emitted
  refresh/Admin/Main recovery controls. No callback, ACK, render, or navigation
  defect was found; report-data accuracy was not tested, so no production source
  change was made.
- This verifies only callback/UI plumbing, not production report accuracy or live
  rendering. Financial risk actions remain outside this fixture. Whole-goal
  A3/A5/A6/A7 and final batch gates remain open; no push, merge, deploy, or restart.

## Continuation — S12.35.329 — Legacy Language `lang_more`

- The retained stale `lang_more` value reached the registered Language handler,
  ACKed once, and rendered the canonical picker with choice, Back and Main
  callbacks using a two-locale fixture. No preference or usage write occurred;
  no product defect was reproduced.
- A heavier composite test-module import stalled before callback execution and
  was interrupted; only the lean source-extracted no-I/O run counts. The locale
  subset is not full all-locale or live UI proof. Goal and batch gates remain open.

## Continuation — S12.35.330 — Manual Top-up Back route

- The actual Back control from manual_payment_menu_keyboard() emits
  menu|main_topup. Dispatching that value through the registered Menu handler
  restored TOPUP SELECTOR, its package/manual-entry controls, and one ACK.
- Direct no-I/O route fixture passed; tests/test_profile_topup_back_origin.py
  passed 5 tests in 11.187s. No route defect, payment/order/provider action, or
  production code change. A3/A5/A6/A7, consolidated CI, exact-main/protected
  comparison, and single-batch delivery remain open.

## Continuation — S12.35.331 — ReplyKeyboard Home with Support pending

- The actual Home label was dispatched through extracted handle_message and
  cmd_start with in-memory Support Ticket pending state. Home rendered Main
  before Support text handling, cleared only the actor's pending entry,
  preserved another user's pending entry and retained the actor's last-ticket
  return marker.
- Direct no-I/O result passed. No production/test patch, payment/provider,
  AutoPost, protected engine, Telegram send, deploy or restart. Other pending
  families, client latency, A3/A5/A6/A7, consolidated CI, protected-source
  refresh and single-batch delivery remain open.

## Continuation — S12.35.384–.386 — Ticket Done concurrency and Admin status callbacks

- S12.35.384: the actual emitted customer `ticket|done|901|profile` callback was
  dispatched twice through the exact registered handler. A deterministic fixture
  held both reads at `new` and reproduced two status writes before the fix. A
  minimal owner-scoped conditional SQLite transition now resolves once. Combined
  focused regressions: `Ran 4 tests in 54.808s — OK`; shared in-memory SQLite only.
- S12.35.385: a registered but unsupported Admin Ticket status (`not_a_status`)
  previously reached the Ticket read and update. The handler now accepts only the
  three statuses emitted by the real keyboard; direct emitted/stale/malformed/
  invalid fixture checks: `PASS (4)`. Existing refund-notice replay:
  `Ran 1 test in 0.563s — OK`.
- S12.35.386: valid Admin Ticket status buttons previously reached language and
  Ticket reads at ACK count zero. The validated route now ACKs once before both;
  stale Tickets render not-found plus Back to the same list/page and Main Home,
  without update or duplicate ACK. Six focused source-extracted cases passed;
  refund replay rerun: `Ran 1 test in 0.304s — OK`.
- For .384–.386, changed test modules compiled and `git diff --check` exited 0.
  Full-source `py_compile bot.py` was interrupted after over 90 seconds without
  output/exit and remains `NOT_VERIFIED`. A broader Admin origin/offset test also
  stalled and remains `NOT_VERIFIED`, not a product failure. Protected
  services/providers/workers/deploy/config diff is empty. No production Ticket,
  message, payment, wallet, provider, engine, AutoPost, Telegram send, push, PR,
  merge, deploy or restart occurred. Continue A3/A5/A6 route evidence; A7, exact
  YAML validation, full CI, protected-main refresh and one-batch delivery remain
  open.

## Continuation — S12.35.387 — Memory delete confirmation owner/replay

- The actual emitted delete-confirm callback matched the registered Memory
  handler. A fixture verified one owner-scoped archive update, one ACK, one audit
  event/success render, actor-only pending cleanup, preservation of a second
  user's pending state, and replay rejection with no second update/event.
- The focused assertion and expired-confirm regression passed; changed test-file
  `py_compile` and `git diff --check` exited 0. The full Memory unittest module
  stalled after one dot and was interrupted (`NOT_VERIFIED`, not a product/test
  failure). State and checklist already contain this evidence; this entry closes
  the missing handover/inventory record only.
- No production data, Telegram send, provider, wallet, AutoPost, protected
  engine, push, merge, deploy or restart. Whole-source compile, consolidated CI,
  exact YAML parse, remaining A3/A5/A6, A7, main/protected comparison and the
  one-batch delivery gate remain open.

## Continuation — S12.35.388 — Expired Memory search-cancel cleanup

- RED reproduced the actual emitted search-origin cancel callback returning to
  Memory root while leaving its still-valid matching `delete_confirm` pending.
- The narrow fix records the origin search token and clears only a pending
  confirmation matching both note ID and callback token in stale/expired and
  missing-result recovery paths. A newer confirmation with a different token is
  preserved.
- GREEN: new stale-cancel fixture plus existing Memory owner/replay and expiry
  regressions: `Ran 3 tests in 3.419s — OK`; focused test-file `py_compile` and
  `git diff --check` exited 0. Full Memory module and whole-source compile remain
  `NOT_VERIFIED`; no production data, Telegram, provider, wallet, AutoPost,
  protected engine, merge, deploy or restart was touched.
- Continue ordered A3/A5/A6 callback audit. A7, consolidated CI, exact YAML
  parsing, latest-main/protected comparison and one-batch delivery remain open.

## Continuation — S12.35.389 — PayOS denial language follows the clicker

- Revalidated the Owner-approved single-ACK patch: the actual emitted package
  callback already returns one denial alert and keeps expiry cleanup after ACK.
- A separate RED showed the denial branch selected language using the encoded
  package owner (123), not the foreign user who clicked (456). Changed only that
  locale lookup to the clicker's ID; no order/payment/wallet logic changed.
- The direct fixture runner passed all five focused emitted/registered callback
  assertions; the test source compiles and `git diff --check` is clean apart from
  existing line-ending notices. The test is included in CI selection.
- No live Telegram, production DB, financial operation, push, PR update, merge,
  deploy or restart. Continue the ordered audit; full compile/CI, remaining
  A3/A5/A6, A7 and final one-batch delivery remain open.

## Continuation regression sweep — 2026-10-13

- PayOS package-choice: 5 direct registered-route assertions passed; test
  `py_compile` passed.
- Feedback: 14 registered-route assertions passed.
- Admin Ticket hub: 10 unittest cases passed in 11.601s.
- Admin Feedback: 3 registered-route assertions passed.
- Admin Help: 6 unittest cases passed in 2.085s.
- Admin Finance report/navigation renderers: 9 unittest cases passed in 96.080s.
- Admin child-menu/Back and footer-guide routes: one targeted unittest each
  passed in 6.361s and 7.242s.
- Full `bot.py` compile did not return within two minutes and was interrupted;
  `NOT_VERIFIED`. `git diff --check` exited 0 with only two existing line-ending
  notices. No production, payment, provider, Telegram, protected engine, or
  deployment side effects occurred.

## Continuation — S12.35.390 — Local Video Studio Home pending cleanup

- RED reproduced a stale text-input owner: `/start`, `/menu`, and the exact
  `menu|main` Home callback emitted by `main_video_keyboard()` left
  `local_video_planning_pending_brief` in the actor's context. The callback was
  dispatched through the registered Menu handler fixture.
- The minimal fix clears only this marker at `cmd_start` and common Menu
  navigation exits. Tests assert the saved `local_video_studio27b_public`
  session and unrelated `video_edit_sentinel` survive unchanged.
- Direct bundled-Python output: `Local Video Studio Home pending cleanup: PASS
  (cmd_start, cmd_menu, emitted Video-menu Home via registered Menu handler);
  plan and Video Edit sentinel retained`. This is UI input-state cleanup only;
  it does not exercise planner output, render, provider or protected engine code.
- Changed test-module `py_compile` and `git diff --check` exited 0. The full
  module run is `NOT_VERIFIED` because `asyncio.run` hung during Windows
  Proactor socketpair startup; the focused no-yield fixtures are the evidence.
- Evidence is recorded in the state YAML, checklist and callback inventory.
  The focused test file is already in the existing CI safe-navigation selection;
  no CI-list or workflow change was needed.
- Continue remaining ordered A3/A5/A6 gaps and A7 correlation. Full
  `bot.py` compile/local consolidated CI, exact YAML parse, latest-main/protected
  refresh and one-batch delivery remain open. No push, PR update, merge, deploy
  or restart occurred.

## Continuation — S12.35.391 — Finance Compliance Home reset

- RED reproduced that inline `menu|main` cleared Finance Compliance input, but
  `/start` and `/menu` left the actor's pending marker alive. The next text could
  still enter the compliance-note handler after a Home command.
- `cmd_start` now clears only the actor's transient marker; `/menu` aliases the
  same path. The direct fixture preserves another user's marker and does not
  invoke note persistence, database, payment or wallet logic.
- Combined focused regressions printed: `Home pending cleanup regressions: PASS
  (Video planner /start, /menu, emitted callback; Finance Compliance actor-only
  /start and /menu)`.
- Focused test-module `py_compile` and `git diff --check` exited 0, with two
  existing line-ending notices in unrelated files. Full-module execution remains
  `NOT_VERIFIED` due the previously observed Windows Proactor socketpair startup
  hang; only the direct no-yield target functions are claimed.
- Checklist/state/callback inventory updated. Continue the remaining A3/A5/A6
  audit and A7 correlation; all-bot CI/compile, YAML parse, current-main
  comparison and the one-batch delivery gate remain open. No GitHub write or
  deploy action occurred.

## Continuation — S12.35.400 — Manual top-up foreign-owner ACK

- Reproduced duplicate ACKs on ten owner-bound customer buttons from the real
  manual top-up and PayOS-recovery keyboards using the exact registered
  callback handler. The foreign clicker previously received an empty ACK and
  then the denial alert.
- Deferred the existing ACK until after the owner check; no payment/order/wallet
  path changed. Added the regression to the explicit CI safe-navigation list.
- Focused related tests: `Ran 3 tests in 1.843s — OK`. This proves only the
  offline registered-route ACK contract, not live Telegram behavior.
- No payment, provider, production data, Telegram send, GitHub write, merge,
  deploy or restart. Full bot compile, consolidated CI, ordered remaining route
  audit, A7 client timing, current-main/protected-source reconciliation and
  one-batch delivery remain open.
