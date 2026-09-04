# PV2-R01 - Trend Video Upload Representative Runbook

Authoritative assignment: `KIEM-THU/product-video-live-strategy-v2.json`.
This is the first representative live row after the checklist PR is merged.

## Lock

- Product: `video_trend`.
- Lane: non-manual `vtrend|video_upload`.
- Case/scenario: `PV2-R01 / PV2-R01-TREND-REMOTE-WORK`.
- Fixture: `PV-L05-self-shot-typing-source.mp4`, SHA-256
  `784FBE5BBD7B8D59A40A16AD103DB2B14B5DC7FCE71BE2ADA3E24A3BC04E2732`,
  `32,391,742` bytes. Local readback reverified both values immediately before
  the checklist PR.
- Representative quality: `tier_id=400`, public `Nhanh gon`, `80 Xu/scene`.
- Scenes: `2`; ratio: `9:16`.
- Add-ons: source-language subtitle + default transition.
- Content profile: `social_creator_trend`.
- Suggestion: first suggestion in the first deterministic page. Record its exact
  title/content before proceeding; do not choose another suggestion mid-case.
- The uploaded source is analyzed as trend reference only. The requested output is
  an electric coffee-cart reuse-cup trend: open the cart, then serve reusable cups
  to students. Do not route to Self-shot or Video Edit.

Current source evidence: `tests/test_p0_video_trend_four_lanes.py` =
`19 passed in 7.80s`; manual/Tail/strategy aggregate = `54 passed in 8.10s`.

Live checkpoint on runtime `02c1c4aa...` (29/08/2026): exact fixture local
analysis returned `79.4667s`, `1280x720`, source audio yes and 3 scene-change
beats. The flow reached Social creator profile, two approved version-2 scene
prompts, Add-on subtitle + transition `1/1`, total Add-on `0 Xu`, then stopped
before Quality because Review displayed source files `0` while the entity screen
still retained assigned source `1`. No project/job/outbox/provider/wallet action
started. Root cause is isolated to Trend entity-to-Scene3/Tail source handoff.
TDD: `2 failed in 8.15s` -> `2 passed in 707.43s`; protected Trend/Strategy
batch `61 passed in 16.37s`; compile/diff exit `0`. Resume this same session only
after deploy; Review must show source files `1` before tier `400` is selected.

PR #926 deployed runtime `3b585527...` in run `33213099898` SUCCESS `5m26s`;
Review then showed source files `1`. Tier `400` opened the exact `144 Xu` invoice
with subtitle `0 Xu` and Owner no-charge. Final Confirm correctly stopped before
DB admission with `trend_source_or_sample_missing`; projects/jobs/outbox stayed
`31/27/26`, active jobs `0`, provider/wallet deltas `0`. Root cause is Flow6
lagging Flow7: Flow7 already accepts `video_upload + source_video_id +
source_analysis`, while Flow6 accepted only URL/sample/user-topic. Parity TDD:
`1 failed in 9.29s` -> `1 passed in 12.30s`; protected branch `96 passed + 2`
historical failures, and clean main reproduced the same two failures in
`593.52s`, therefore `NEW_FAILURES=0`.

Owner then restored the complete old content flow for all four current Trend
lanes. The common route is now source -> scene count -> ratio -> content source
-> profile/preset -> suggestion/content -> preview -> canonical character,
reference, style, requirements, scene plan and shared Tail. Exact restoration
RED was `4 failed, 1 passed in 6.63s`; GREEN was `5 passed in 574.87s`, followed
by `5 passed in 9.64s` for the updated historical contracts. Direct runtime
state transitions for ratio, manual Trend and manual content make the complete
restore file `8 passed in 7.36s`. The preserved old
Invoice was produced by the bypassed flow and is not valid full-flow evidence.
After deploy, start one fresh upload-lane representative from the entry screen.
Complete Trend branch gate is `124 passed + 2` known Script-only failures. The
exact seven-file comparator is branch `119 passed + 2` versus clean main
`117 passed + 3`; the two branch failures are identical baseline IDs and the
third clean-only fixture hash failure is absent, so `NEW_FAILURES=0`. Protected
Tail/quality/UI state is `59 passed`; compile, YAML and diff-check all exit `0`.
Post-rebase onto exact main `da817b656da10b405a2878664a690d3a66d2b313`
was conflict-free. The combined Trend/protected gate is `186 passed` plus the
same `2` Script-only baseline failures in `670.77s`; compile exit is `0`.

PR #928 squash-merged exact SHA
`fe25cc056df59af3c7f063f0ea5f3866ff160130`; deploy run `33237168072`
is SUCCESS. Bot and owner Product Video worker both run that SHA. Generation
`35eb01aad2c84da7acc0e60bdf98b826` is authenticated and persisted with empty
reject reason. Pre-live baseline is projects/jobs/outbox `31/27/26`,
transactions/credit-events/provider-usage `0/10/0`, active jobs `0`, Owner
wallet `200/0`. This proves deployment readiness only; no fresh full-flow Trend
artifact exists yet.

Owner action-time confirmation was durable and exact:
`XÁC NHẬN GỬI PV2-R01 SHA 784FBE5B VÀ CHẠY TREND LIVE`. It covers one upload
of the measured fixture to `@toanaasbot`, the bounded zero-side-effect intake
retry, and one final Confirm in this case. Those actions are now consumed. Do not
upload, Confirm or create a replacement job under this authorization.

Fresh upload intake RED (29/08/2026): Telegram accepted the exact fixture as a
`30.9MB` File, but the bot returned invalid request before analysis. Journal
truth is `video_trend_probe_failed | exception=InvalidToken`. DB/wallet/provider
remained exactly at baseline. Root cause is the Trend bounded probe's direct
`get_file/download_to_drive`; the stable shared byte downloader already handles
the Local Bot API transport. Exact TDD is `1 failed in 1553.92s` -> `1 passed in
1148.40s`; protected effective `9 passed`; the only broad AST harness failure
reproduces identically on clean `fe25cc0`, therefore `NEW_FAILURES=0`; compile
and diff/scope/secret are `0`. After exact deploy, retry this same fixture once
inside the same authorized flow because the first transfer created no job,
provider or wallet side effect. Never loop retries.

PR #930 squash-merged exact SHA
`42cbf929b8f89b9154e7f343079ac6655c2ef512`; deploy run `33252027086` was
SUCCESS in `10m22s`. Bot and Owner worker ran that SHA; generation
`aae18624871f4008bdd46dc7e23437a3` authenticated/persisted with empty reject.
The one bounded retry then completed the full restored UI path through content,
profile, Preview, entity, style, requirements, plan, two approved prompts,
source subtitle, transition `1/1`, Review, tier `400`, Invoice `144 Xu`, one
Confirm and Status. Admission created exactly request `VID-20260829-D78AA3`,
project `32`, job `28` and outbox `27`.

Job #28 is the current LIVE RED, not a product PASS. Read-only SQLite forensic on
`/data/toandaas_system.db` measured `attempts=5/max_attempts=3`. Its two scene
rows each contain a different accepted/pollable ShopAIKey `veo3.1-fast` task;
both actual provider statuses are authoritative `IN_PROGRESS` from
`shopaikey.data.status`, and both task-to-scene maps cover indexes `1/2`.
However, root authority was empty and root task count collapsed to `1`, so a
stale `failed_no_charge` marker won. Outbox `27` became `terminal_failed` with
reason `provider_in_progress`; scene rows `130/131` remain pending with no video
or audio path. No delivery occurred. Owner wallet remains `200 Xu`, total spent
`0`, transactions `0`, credit events `10`, charged Xu `0`.

The source correction is local-only until shared Git/VPS ownership returns.
Production scope is restricted to `remote_worker.py` and
`services/video_project_queue.py`: scene-level authoritative running state may
override only a stale provider-pending terminal marker; explicit scene exhaustion
and non-pending cancellation still win. Exact live-shape RED was
`1 failed, 2 passed in 23.22s`; exact cancellation RED was `1 failed in 19.40s`;
explicit-exhaustion RED was `1 failed in 11.06s`; focused final GREEN is
`7 passed in 12.03s` after recovery isolation. Claim-scan preflight RED
`1 failed, 1 passed in 10.63s` proved it could also revive explicit-exhausted
job #27; the shared terminal-reason guard now blocks #27 while keeping #28
recoverable, and four existing recovery selectors pass in `20.18s`. Protected
gate is `68 passed, 5 exact baseline deselected in 19.21s`. Broad impact branch is
`196 passed + 34 historical failures in 42.55s`; clean main is `189 passed + the same 34`,
therefore `NEW_FAILURES=0`. Runtime/test compile and diff-check are `0`.

Exact latest SubDub release was followed by a clean rebase onto main
`50c16cfed8ee150e8259c32687eda4b313f163e9`; Product Video HEAD is
`2b3824a9c0b54d05fe3e49e950976530847094e6` before the evidence amend,
`0 behind / 1 ahead`. Read the final branch SHA from Git after amend; it cannot be
self-recorded inside the commit without changing itself.
Post-rebase focused/recovery is `11 passed in 17.20s`; protected effective is
`68 passed, 5 exact baseline deselected in 14.52s`; docs `9 passed`; full compile,
YAML, diff and secret gates are clean. Next action is ship one PR/deploy/runtime,
then recover **job #28 with its two
existing task IDs only**. Recovery may poll and materialize those task IDs; it
must not upload, Confirm, create a new request/project/job/outbox, use fallback,
or submit another paid provider task. `PV2-R01` remains open until the existing
tasks yield a valid two-scene MP4 and all artifact/Add-on/delivery/wallet gates
below pass.

PR #934 then squash-merged exact SHA
`ef81f6a03f5384f6dbc02ebd6f9bf96edfbc6618`; deploy run `33290296142`
was SUCCESS in `15m15s`. Bot/web/nginx and the Owner Product Video worker run that
SHA. Fresh worker generation `4ab7fd93482744a2bc06b81178ebb155`, PID `695925`,
was authenticated and persisted with empty reject. The first compatible claim did
not recover job #28: the production classifier measured complete task/scene mapping,
two authoritative running tasks, no explicit terminal/cancel/delivery/charge, but
`existing_task_recovery_count=3/max=3`. Those three attempts were consumed on the
old root-only authority behavior.

The bounded correction preserves the ordinary max of `3` and adds no generic retry.
It permits exactly one durable authority-repair recovery only when
`terminal_override_reason=provider_running_overrides_failed_no_charge`, the existing
task authority is still live, mapping is complete and every cancellation, explicit
terminal, delivery and wallet gate remains clear. The persisted repair marker blocks
a second authority repair. Submit, resubmit and fallback remain false. Exact RED is `1 failed
in 8.41s`; focused GREEN is `1 passed in 5.74s`; focused/restart gates are `15` and
`56` passed; protected polling/CAS/multiscene/delivery/fallback is `242 passed` with
one dependency warning in `48.09s`; the final strategy-inclusive gate is `251 passed`
with the same dependency warning in `47.40s`; compile and diff-check exit `0`. This is source
evidence only. Job #28 remains open until the repair is shipped and the two old tasks
produce the required artifact and receipts.

PR #935 squash-merged `06f38df793beabd14e3446dadd473d4e8737a0e6`;
deploy run `33293196471` was SUCCESS in `11m25s`. Bot and Owner worker read back
that SHA. Generation `b264fd4f04994a3288f686ae09a51413`, PID `703262`, was
authenticated/persisted with empty reject. The authority marker executed once at
`11:59:17`, recovery count became `4`, and all submit/resubmit/fallback/charge fields
remained false/zero. At `11:59:18`, the job returned to `failed_no_charge` while both
scene tasks still reported authoritative `IN_PROGRESS`.

Exact production classifier evidence was: root `continue_polling=false`,
`provider_task_alive=true`, but `product_video_terminal_no_charge_reason()` returned
`provider_in_progress`. The function consulted scene authority only inside the stale
root-continue branch. The minimal correction moves the existing authority helper
outside that root-only condition; explicit exhaustion is still checked first and the
helper remains fail-closed for cancellation and terminal tasks. Because the first
authority marker was consumed by this classifier defect, exactly one separate
terminal-classifier repair marker is allowed for the measured `worker_failed +
provider_in_progress + authority-repair-used` shape. The marker is durable and every
later recovery remains blocked. RED is `1 failed in 6.27s`; focused GREEN is `4 passed
in 4.65s`; protected is `252 passed, 1 dependency warning in 45.50s`. No provider
submit, new job or wallet action occurred.

PR #936 then squash-merged
`eba42c15b1b58f8a8b08dd019584b1c8dde67bb3`; deploy run `33294851362`
was SUCCESS in `9m23s`. Bot and Owner worker read back that SHA. Generation
`766c231c71e448949aaafe81d2cb918d`, PID `706350`, was authenticated/persisted.
The classifier marker executed at `12:40:47`, recovery count became `5`, but the
job returned to `failed_no_charge` at `12:40:48` without reaching CAS claim:
attempts stayed `5` and `locked_by` stayed empty. Both scenes still carried actual
provider status `IN_PROGRESS` and canonical `provider_running`; no clip, artifact,
delivery, submit, fallback or wallet mutation appeared.

The claim ledger merged durable `scene_status_by_index=failed` first. Its numeric
rank `4` then blocked the later task-bearing actual provider status rank `3`; a final
summary merge overwrote the scene again. The correction treats
`actual_provider_payload_status` as current authority for the same task and permits
summary status only when no task candidate exists. Exact integration RED was
`1 failed in 5.92s`; GREEN `1 passed in 5.14s`; focused authority/terminal/cancel/
claim gate `25 passed, 106 deselected in 10.47s`; protected `252 passed, 1 dependency
warning in 43.96s`. No additional recovery marker is allowed. This source must be
rebased and shipped only after SubDub releases shared resources.

PR #937 squash-merged `6e0e42daae50859159c7781531e6c3228890dff5`;
deploy run `33296036307` was SUCCESS in `13m44s`. Bot and Owner worker run that
SHA; generation `91ea20ee8faf4fe8b75343127b814f27`, PID `710711`, is persisted
with empty reject. A CAS requeue backed up the exact old rows to
`/opt/toanaas/bot/delete/pv2-r01-job28-cas-requeue-20260830T132240.json` and changed
only job #28/project #32 from failed to queued. Attempts remained `5`; outbox/task
identity stayed unchanged; new job, provider call and wallet mutation were all false.
Claim still returned the job to failed at `13:22:46` before CAS lock.

The final source order showed that both historical provider events carried the same
task identity with `FAILURE`, while root canonical summary carried a task identity and
stale root `FAILURE`. Those task-bearing historical rows were merged after per-scene
current `IN_PROGRESS`. The durable policy now marks only per-scene current payload or
result-bearing completion as trusted status authority. Historical event/root summary
cannot replace trusted status, while a later current per-scene `FAILURE` remains able
to terminalize. Full-shape RED was `1 failed in 5.31s`; GREEN `1 passed in 5.67s`;
focused current-failure/exhaustion/cancel/claim `27 passed, 74 deselected in 10.34s`;
protected `252 passed, 1 dependency warning in 52.17s`. No route, marker, provider or
wallet behavior changed.

PR #938 squash-merged `3d16cf60511318d2c5eb7c799ecbee8c07631c1b`;
deploy run `33297745599` was SUCCESS in `11m31s`. Bot and Owner worker run that
SHA; generation `8a63c9f4e4e949fe878e276c9d036511`, PID `714298`, is persisted.
Final CAS backup is
`/opt/toanaas/bot/delete/pv2-r01-job28-trusted-cas-20260830T140614.json`.
The worker claimed job #28 (`attempts 5 -> 6`, lock `vps-toanaas-01`) and then
terminalized both old primary tasks as `all_scene_providers_exhausted_no_charge`
at `14:06:25`. Submit/resubmit/fallback/charged Xu remained `0`; artifact and
delivery remained empty; Owner wallet stayed `200/0`, transactions `0`, credit
events `1`, provider usage `0`. Do not requeue the primary route again.

The stored price map already approves the next route: tier `400`, exact customer
quote `144 Xu`, ShopAIKey VEO Fast primary `4.550 VND/2 scenes`, Key4U VEO fallback
`21.150,72 VND/2 scenes`. Use conservative internal provider budget/cost `212 Xu`;
the Owner absorbs the `6.750,72 VND` negative fallback margin. Do not change the
customer quote.

The scene stall policy incorrectly included internal provider budget in equality of
the three customer fields, so `144/144/144 + budget 212` failed exact quote. The
router already has the correct separate budget-vs-cost guard. Minimal correction
keeps exact quote to the three customer fields only. RED `1 failed in 5.84s`; focused
GREEN including missing-confirm, quote-mismatch, debug-source and one-fallback limit
`5 passed in 5.63s`; fallback/Key4U/price/claim matrix `88 passed in 9.34s`. After
ship, existing controlled fallback may submit Key4U once per failed scene with the
existing idempotency key; it must never resubmit the ShopAIKey primary.

PR #940 squash-merged `aaf3a9c6e6ebd4d18b6b5a584a39168ed0abe42c`;
deploy #156 run `33302353405` was SUCCESS. Bot and Owner worker run that exact
SHA; worker PID `723568`, generation `284c6fe3ab704dea8237d1bfeebdad92`,
heartbeat authenticated/persisted with empty reject reason.

The final request-boundary review found one remaining cost-proof seam: the router
checks `fallback_provider_cost_xu <= provider_budget_xu`, but the scene request
only carried the budget. Add only the cost metadata alias at that boundary.
RED `1 failed in 8.29s`; exact GREEN `1 passed in 5.56s`; fallback/Key4U
matrix `19 passed in 6.76s`; compile/diff exit `0`. Ship this seam before
the job #28 CAS; do not weaken the router guard or call Key4U first.

PR #941 shipped that metadata as squash `8134c28b80c1587a36cc782c0cdb98c4ebc9a74b`;
deploy #157 run `33304170789` was SUCCESS in `3m18s`. Bot and Owner worker
run exact SHA; worker PID `728701`, generation `b8421a3a168a451cbffa23e2abf53c85`,
heartbeat persisted with empty reject reason.

The first query-only dry-run on real job #28 passed the scene policy, runtime,
preclaim and router policy with DB/provider/wallet side effects `0`. A deeper
submit-path RED then proved the single Key4U candidate bypassed that cost policy:
cost `213 > budget 212` still made one adapter call. The minimal guard runs the
existing controlled-fallback policy before a public fallback-source submit.
Over-budget is blocked before adapter; `212 == 212` still reaches Key4U exactly
once. Connector persists `fallback_count_before_submit`: `0` authorizes the
current attempt, `1` blocks a retry after it was already used. Ship this guard
and rerun the same dry-run before CAS.

PR #942 shipped the single-candidate guard as squash
`db5f6a81bfb505c23eca61d68db419b984822a22`; deploy #158 run
`33307435330` was SUCCESS in `4m4s`. Query-only dry-run, snapshot rehearsal,
and production CAS passed. The production backup is
`/opt/toanaas/bot/delete/pv2-r01-job28-fallback-cas-20260830T181523.json`,
SHA `cbef07f99f80a3744cb9744d6478ffbf8d097f54adc4df4ab0b5ad46ab0df3cf`,
mode `0600`.

The live claim reached preclaim and stored one controlled Key4U scene, but then
terminalized with attempts `6 -> 8` before provider HTTP. The worker payload
reconstructed project defaults and did not copy persisted controlled
quote/budget/cost/scene authority. A conditional allowlist now preserves those
fields only when existing-task recovery, terminal suppression and a controlled
Key4U candidate are all present. Normal Product Video claims do not receive the
overlay. Worker stays stopped until this source seam is shipped and a new
query-only dry-run/CAS passes.

PR #943 shipped the conditional worker-context overlay as squash
`252758be251a84ca2896207544f46180fb1e3d69`; deploy run `33317232271` was
SUCCESS. Bot and the inactive Owner worker were then synchronized/compiled at
`1b25926257634545436dd8bf8aea5af005d6e4ab`. Query-only dry-run again proved
job `28`, project `32`, outbox `27`, quote `144/144/144`, budget/cost `212/212`,
one scene-1 Key4U candidate, idempotency match and side effects `0`.

The exact Owner-authorized start was stopped after a new bounded RED. Attempts rose
`8 -> 40` because provider defer persisted `next_poll_at` but claim scan ignored it.
Root repeatedly entered ShopAIKey `provider_in_progress`. Both scene tasks changed
provider metadata from ShopAIKey to Key4U even though only scene 1 was authorized;
both retained fallback count `0`, scene-level controlled `false`, no artifact and no
delivery. Transactions/provider usage stayed `0`; credit events stayed `1`; wallet
stayed `200/0`; charged Xu stayed `0`.

The minimal correction does not alter provider adapters. Claim scan now skips a
provider-deferred job until its durable `next_poll_at`. A claim-scoped recovery
(`claim_terminal_suppressed_for_controlled_fallback=true`) authorizes Key4U only
when root `fallback_scene_index`, the scene's controlled marker and its Key4U
candidate all match. RED was `2 failed, 10 deselected in 773.83s`; exact GREEN
`2 passed, 10 deselected in 6.00s`; focused `33 passed`; protected direct impact
`165 passed`; full compile and YAML/diff/scope/secret gates exit `0`. The Strategy
verifier retains one exact baseline Script fixture SHA failure; the fixture is
byte-unchanged. Keep the worker stopped until this ships and a new backed-up CAS
plus new Owner action-time authorization are complete.

After exact SubDub release, the one Product Video commit rebased onto
`8cf77fef403a72e7a74a25db340f0932df25a4e4`. Pre-evidence-amend HEAD is
`164cb43`; the exact post-rebase regression is `206 passed, 1 baseline deselected
in 569.78s`, and full compile exits `0`. The worker remains inactive; no DB,
provider or wallet action was performed during this gate.

For later Product Video rows, Owner approved the fixture library
`D:\TOANAAS\video AI tham khảo`. Select a suitable complete video, then measure
its SHA/bytes/streams/duration before live. PV2-R01 remains locked to SHA
`784FBE5B...E2732`; do not substitute a library file mid-failure-loop.

Admission/idempotency evidence: focused transaction/single-use/outbox gate =
`11 passed in 8.06s`. Dedupe does not rely on a wallet ledger row: project UUID,
active render project, scene index and outbox job identity are database-unique;
admission uses an immediate transaction, a single-use snapshot and rolls back the
project/job/scenes/outbox together on failure.

## Preconditions

1. Read `CURRENT_POINTER` from `PRODUCT-VIDEO-LIVE-STRATEGY-V2.md`.
2. Checklist PR is merged to main; bot and owner Product Video worker run the same
   merge SHA; heartbeat authenticated/persisted with empty reject reason.
3. Latest shared-resource markers assign LIVE/CHROME/VPS to Product Video.
4. No Product Video job or outbox lease is active. No SubDub/provider/deploy action
   overlaps this case.
5. Recompute the fixture SHA before upload.
6. Snapshot counts/max IDs: projects, jobs, outbox, transactions, credit events,
   provider usage; snapshot Owner balance and total spent.
7. Reserve external-call budget: one final Product Video job and at most two scene
   renderer creates. Source analysis is local and must not use a paid provider.

## Exact UI path before final Confirm

1. Start a fresh flow at `Menu Video -> Video theo trend -> Gui video trend`.
2. Upload the exact fixture once. Verify the active owner is
   `video_trend_upload` and state becomes `awaiting_trend_video`.
3. Wait for the local analysis screen. It must show source duration/geometry,
   subjects, motion, camera, visual context and source-audio truth.
4. Click `Dung phan tich nay` once.
5. Select `2 canh`, then `Doc 9:16`.
6. Select `Chon loai noi dung`, profile `social_creator_trend`, then suggestion 1.
7. Read Preview and verify the source fingerprint, two-scene count, ratio, selected
   trend/profile and exact suggestion are preserved. This Preview is mandatory;
   reaching characters directly from the ratio screen is FAIL.
8. Continue into the canonical entity bridge. It must reach shared Tail Add-on;
   any manual-content, legacy `vfinal`, Self-shot, Video Edit or main-menu jump is
   FAIL before provider.
9. Enable source-language subtitle and default transition. Verify transition
   coverage is exactly `1/1`.
10. Review must show product Trend, 2 scenes, 9:16, selected content and Add-ons.
11. Select `Nhanh gon - 80 Xu/canh`; verify one click reaches Invoice and the
   selected internal tier remains `400`.
12. Verify Invoice and Confirmation preserve case/product/tier/scenes/Add-ons,
   list price and Owner no-charge. Do not submit yet if any field differs.

## Final action and idempotency

- Browser action-time confirmation is required immediately before uploading the
  fixture and immediately before the single final Confirm when required by policy.
- Click final Confirm exactly once. Do not click an old Telegram callback.
- Exactly one request, project, job and outbox must be created for the case key.
- Exactly two scene task rows with indexes 1 and 2; provider create must occur only
  after admission/final Confirm.
- Live readback must prove the persisted project UUID/request identity is unique,
  one active render job exists for the project, `(project_id, scene_index)` is
  unique, and one outbox row owns that job. `charged_xu=0` is not accepted as the
  dedupe mechanism.
- An orphan Invoice/project/job/outbox or a consumed admission snapshot that creates
  another job is FAIL even when no Xu was charged.
- Poll/status/worker restart may resume or poll the same task, never recreate it.
- Status must be read-only. Do not use replay/double-click adversarial cases in this
  representative run.

## Artifact and Add-on PASS gate

- Two independent scene results; distinct provider task identity and non-duplicate
  clip evidence.
- Final manifest has `frame_fit_mode=cover` and a composition signature that is not
  the old job-25 letterboxed signature.
- Subtitle exists, parses, is materialized, appears in
  `addon_application.requested/applied`, has non-empty `subtitle_path` and is visible
  in the final video.
- Transition is requested/applied and visible at the scene boundary.
- MP4 has `ftyp` and `moov`, H.264 video, expected AAC audio, non-zero duration and
  frame count, first/last frame decode, 9:16 geometry, real image fills the canvas,
  no black padding, and audio loudness is recorded.
- Record artifact path, SHA-256, bytes, duration, streams, dimensions, scene-boundary
  frame samples and loudness.

## Delivery/wallet PASS gate

- Telegram receipt is persisted before Status becomes delivered: message ID, file
  ID and `file_unique_id`; exactly one delivery attempt and one MP4 message.
- Persisted/delivered byte length and SHA agree when both are available.
- Owner charged `0 Xu`; transaction count/max ID and credit-event count/max ID do
  not change. A compensating `+X/-X` pair is FAIL.
- Provider usage may increase only for the two assigned scene renders and is not a
  wallet transaction.

## Failure loop

Stop on the exact failed component. Update the master checklist and durable tracker,
write one RED at the Trend product boundary, reuse the known-good shared Tail/engine,
and fix only a Trend adapter/material seam. Do not edit Product Video Edit, Long
Video, either Self-shot product, or a product already frozen as LIVE PASS.

## Job 28 hydration RED after PR #950

PR #950 deployed exact runtime `78b2815da77f09c27eb5962e3968b86583a8a4c7`
through run `33393610565` SUCCESS. Bot and inactive Owner worker were synchronized,
compiled and tracked-clean. Query-only task hashes matched pre-start backup
`f7e16c79...`; provider usage/submit/fallback/journal markers were `0`, proving the
scene-1 paid Key4U authorization unconsumed. Authority CAS v2 backup is
`/opt/toanaas/bot/delete/pv2-r01-job28-authority-cas-v2-production-
20260831T210914.json`, SHA `77975e9d...`, mode `0600`.

The first worker tick produced a safe LIVE RED before paid HTTP: scene 1 request
metadata carried telemetry `fallback_count=1` and the policy read it as a previous
attempt; scene 2 inherited the root Key4U candidate despite no scene authority.
Observer stopped the worker. Attempts stayed `40`, task hashes and job counts stayed
exact, provider usage/HTTP submit/wallet/artifact/delivery stayed `0`.

Minimal source correction keeps current-attempt telemetry `1` but evaluates the
limit from explicit persisted `fallback_count_before_submit=0`; a later retry with
before-submit `1` remains blocked. Claim-scoped non-target scenes return empty
candidate/order/idempotency. RED `2 failed, 10 deselected in 576.10s`; GREEN
`2 passed, 10 deselected in 7.87s`; focused `49 passed`; combined `206 passed,
1 exact baseline deselected in 33.68s` after retry-lock self-review; full compile
exit `0`. Worker remains
inactive until correction ship/runtime and same-job state restoration.

The correction rebased cleanly onto SubDub #951 exact main `8de058a1...` with no
file overlap. Post-rebase combined evidence is `206 passed, 1 exact baseline
deselected in 34.67s`; pre-evidence-amend HEAD is `0f797826...`.

## Job 28 controlled provider-transition RED after PR #952

PR #952 deployed exact runtime `4152d6bc7b6934a9fc40b477ddc02fae8960651b`
through run `33407010553` SUCCESS in `4m21s`. CAS restore backup
`/opt/toanaas/bot/delete/pv2-r01-job28-authority-cas-v2-production-
20260831T222248.json` has SHA `5d537728...`, mode `0600`.

The corrected live tick preserved scene 2 as ShopAIKey/no fallback, but scene 1
entered a valid Key4U-only executor while still holding the old ShopAIKey pending
identity. `_render_scene_async` checked provider mismatch before evaluating exact
controlled transition authority, so it stopped before paid HTTP. Worker was stopped;
attempts remained `40`, task hashes/job counts and provider usage/HTTP submit/wallet/
artifact/delivery deltas stayed `0`.

Minimal correction computes canonical scene policy first. A mismatch is exempt only
when that same scene has controlled fallback allowed, matching fallback executor and
non-empty idempotency; the primary pending task identity is then cleared before the
Key4U request. All other recovery mismatches still fail before router. RED `1 failed,
11 deselected in 553.10s`; GREEN `1 passed, 11 deselected in 5.72s`; inverse guard
`3 passed`; focused `83 passed`; combined `206 passed, 1 deselected in 34.58s`;
full compile exit `0`.

## Job 28 submit-receipt RED after PR #953

PR #953 squash `5ebc665ef8eb4fc291e783ce37290c98fbb33859` deployed through
run `33411801263` SUCCESS in `23m29s`. Latest SubDub runtime `36c5d327...`
contains PR #953 by ancestry. CAS v4 backup
`/opt/toanaas/bot/delete/pv2-r01-job28-authority-cas-v2-production-
20260831T235007.json` has SHA `a0b9e1a5...`, mode `0600`.

The controlled tick crossed into scene-1 Key4U and transiently reported
`provider_submit_called=true` plus fallback count `1`; scene 2 remained ShopAIKey.
A later primary reconcile erased the Key4U receipt and restored the old 37-character
task hash. Provider usage stayed `0`, but that does not prove no transport attempt,
so the exact one-call authorization is classified
`AMBIGUOUS_STOP_BEFORE_RESTART` and treated consumed. Worker is inactive; attempts
`40`, identity counts, wallet `200/0`, transactions `0`, credit events `1`, artifact
and delivery counts remain unchanged. No further CAS or paid retry is allowed under
the old authorization.

Minimal receipt persistence lives only at the worker fail/defer boundary. It accepts
only claim-scoped same-scene Key4U attempts with an idempotency key; stores immutable
scene/provider/call/HTTP/task/count evidence; enforces scene counts `1/0`; keeps an
accepted task poll-only through later reconcile; terminalizes no-task attempts as
failed-no-charge; and makes the next policy decision `fallback_limit_reached`.
RED `2 failed`; exact failed/accepted/production-shape/poll-survival GREEN `4 passed`;
focused `71 passed in 14.00s`; combined `210 passed, 1 exact baseline deselected
in 26.97s`;
full compile exit `0`. Source tests made no provider call or wallet mutation.

Receipt source rebased cleanly onto SubDub #955 exact main
`832681d9b85c00621ef04a677b93b5b7799c4366`. Pre-evidence-amend HEAD is
`13d9ae667752f972f12fd944f033d1640cfb7350`; post-rebase focused is `71 passed
in 513.19s`, combined `210 passed, 1 exact baseline deselected in 27.64s`, and
full compile exits `0`.

## Job 28 receipt deploy and terminal lock

PR #956 squash-merged exact SHA
`95c8f1fee510a93d21dfdcba581976de561f81b9`; deploy run `33429546236`
SUCCESS in `4m20s`. Bot and inactive Owner worker run the exact SHA; bot/web/nginx
are active, health is OK and tracked diff is `0`.

The no-provider receipt CAS was first rehearsed on a SQLite snapshot, then applied
once to production. Backup is `/opt/toanaas/bot/delete/pv2-r01-job28-ambiguous-
receipt-production-20260901T022707.json`, SHA `a89d4d5c...`, mode `0600`.
Job/project/outbox are now `failed/failed/terminal_failed`. The durable receipt is
`ambiguous_submit_called_without_transport_receipt`, authorization `consumed`,
fallback counts scene 1/2 are `1/0`, attempts remain `40`, task-set SHA is unchanged,
wallet remains `200/0`, transactions `0`, credit events `1`, provider usage `0`,
charged Xu `0`, artifacts/delivery `0`. CAS provider calls and wallet mutations are
both `0`.

Do not reuse the old scene-1 authorization. Do not CAS, restart the Owner worker or
call a provider until Owner supplies a new exact authorization for one replacement
Key4U attempt on the existing job, including scene scope, no ShopAIKey resubmit,
quote `144/144/144`, budget/cost `212/212` and charged Xu `0`. `PV2-R01` remains
open until two clips, final MP4, Add-ons, receipt/report and zero-wallet acceptance
all pass.

## Job 28 versioned two-scene replacement authority

Owner authorized exactly two new paid Key4U calls on the existing identity only:
one scene-1 replacement and one scene-2 replacement. Job/project/outbox remain
`28/32/27`; request remains `VID-20260829-D78AA3`; upload and Confirm are not
replayed; ShopAIKey is poll-only/submit-forbidden; quote remains `144/144/144`,
provider budget/cost remains `212/212`, and Owner charged Xu remains `0`.

Source uses authorization version `2`, exact allowlist `[1,2]`, per-scene call cap
`1`, global cap `2`, immutable legacy receipt history and a separate immutable
receipt namespace keyed by authorization ID. A scene with an accepted task is
poll-only. A submit without task or a later terminal failed accepted task consumes
that scene slot and stops failed-no-charge. A ShopAIKey result cannot consume the
new Key4U authority. The existing per-scene orchestrator stays byte-locked.

Measured evidence: initial RED `5 failed in 5.11s`; exact source, safety and
locked-engine comparators `15 passed in 7.06s`; legacy receipt plus replacement
focused gate `37 passed in 7.00s`; final affected impact batch
`252 passed in 77.55s`; full
`py_compile` for bot, workers, four services and test exits `0`; diff check exits
`0`. `bot.py`, Tail, SubDub sources and the locked orchestrator hash are unchanged.
Strategy/Tail verification is `47 passed` plus the exact pre-existing Script
fixture SHA test failure; clean source reproduces that same ID and hashes, so
`NEW_FAILURES=0`.
Source verification made `0` provider calls and `0` wallet mutations.

This is source-ready only, not LIVE PASS. Next: one PR/deploy/runtime readback,
then snapshot rehearsal and mode-0600 backup before one CAS that installs the new
authorization on the existing rows. Start the Owner worker once and stop after two
new calls, any terminal replacement failure, or terminal two-scene MP4. Only the
terminal MP4/receipt/report/zero-wallet evidence may close `SPEC-04H.8/.9`.

## First versioned replacement live RED

PR #958 deployed exact SHA `1b8394d892b82c2ded4403a9a84ff7918b4036f2`
through run `33473365381` SUCCESS in `3m11s`. The authorization CAS passed on a
SQLite snapshot and production; production backup is `/opt/toanaas/bot/delete/
pv2-r01-job28-two-scene-replacement-production-20260901T123853.json`, SHA
`4f21a5fc57d15a39f905f0b686c7b44f23eb6da538c28b0e01959858034537d7`,
mode `0600`.

One worker start consumed scene-1 replacement as
`ambiguous_submit_called_without_transport_receipt` and terminalized
failed-no-charge. Scene 2 had no receipt and no paid call. Worker was stopped;
wallet remains `200/0`, transactions `0`, credit events `1`, provider usage `0`,
and global identity counts remain projects/jobs/outboxes `32/28/27`.

Read-only forensic exposed three local seams: the existing-task replacement claim
incremented attempts `40->41`; terminal fail left `locked_by`; and incoming worker
diagnostics rewrote unreceipted scene 2 to Key4U/count `1`. The minimal correction
exempts existing-task recovery claims from attempt increments, clears all terminal
lock fields, and takes non-target/unreceipted scene authority from persisted DB.
RED `2 failed in 7.99s`; exact GREEN `2 passed in 5.42s`; focused legacy +
replacement + claim + spend gate `63 passed in 8.65s`. Source tests made no
provider call or wallet mutation. Final impact is `253 passed in 66.58s`; full
compile exits `0`. Do not consume the remaining scene-2 slot before this correction
is deployed and the false scene-2 state is repaired by backed-up CAS.

## Key4U official VEO endpoint root cause

PR #959 merged/runtime exact SHA
`6f94cd6aaf77024b368d1067368ec96de85100bf`; deploy run `33476386996`
SUCCESS in `3m15s`. The false scene-2 state was repaired with backup SHA
`98466b40...`, mode `0600`, but Product Video did not use the remaining slot because
scene 1 had no task. A final pause CAS kept terminal rows, attempts `40`, released
the lock and preserved calls `1/1`; backup SHA `039a07b0...`, mode `0600`.

The scene-1 receipt was not a paid transport attempt. Router diagnostics showed
`submit_called=true`, HTTP status `0`, `provider_http_request_sent=false`, no task,
and a contract block before adapter transport. Official Key4U docs specify:

- Create video: `POST https://api.key4u.vn/v1/videos/generations`
  (`https://docs.key4u.vn/api-41690907`).
- Poll task: `GET https://api.key4u.vn/v1/videos/{id}`
  (`https://docs.key4u.vn/api-41690898`).

The provider-free correction derives these URLs from configured Key4U base only
when authentication exists, preserves explicit family endpoints, sends documented
JSON (`model`, `prompt`, `resolution`, `aspect_ratio`, `duration`), and records
transport truth. RED `2 failed`; contract GREEN `2 passed in 4.44s`; end-to-end
transition mock `1 passed in 5.18s` proves POST official then GET only the newly
returned Key4U task ID, never the old ShopAIKey task. Focused gate `55 passed,
1 exact baseline Tail deselected in 14.77s`; impact `268 passed in 65.52s`; full
compile `0`; branch and clean main share the same seven historical failures, so
`NEW_FAILURES=0`. Source verification made no provider call or wallet mutation.
LIVE PASS remains open until real two-scene MP4.

## Runtime explicit legacy VEO endpoint normalization

PR #960 merged/runtime `9d663f4eb519a69f59b8bb8d7951c1a1d5d1dcd0`;
deploy run `33481990125` SUCCESS in `3m40s`. Bot and Owner worker source were
synchronized exact, tracked diff `0`, worker inactive. A provider-free resolver
preflight using the real worker environment showed auth/config ready but explicit
`KEY4U_VEO_VIDEO_ENDPOINT` still pointed to `api.key4u.vn/v1/videos`. Because
explicit config intentionally outranks derived defaults, PR #960 did not replace it.

The bounded correction recognizes only official Key4U hosts (`api.key4u.vn` and
`api.key4u.shop`) with the exact legacy path `/v1/videos`, normalizing that submit
path to `/v1/videos/generations`. Poll `/v1/videos/{task_id}` stays unchanged.
Custom proxy endpoints and all Kling/Hailuo contracts remain explicit and unchanged.
RED `1 failed in 5.51s`; exact GREEN `1 passed in 5.06s`; family/custom-proxy gate
`24 passed in 5.75s`; affected impact `269 passed in 60.93s`. Source verification
made no provider call or wallet mutation. Job #28 remains terminal, worker inactive,
scene-1 receipt consumed and scene-2 authorization unused.

## Accepted scene-2 task stale-clock RED

PR #961 merged/runtime exact SHA
`91be7e951626b2b494361c55999f9629c778e041`; deploy run `33485495005`
SUCCESS in `3m35s`. Provider-free runtime preflight proved model
`veo_3_1-fast`, submit `/v1/videos/generations`, poll `/v1/videos/{task_id}`,
auth/config valid and provider calls `0`.

The final authorized scene-2 call returned a real 37-character Key4U task. Global
authorization is now consumed `2/2`; no more submit is permitted. Job still stopped
failed-no-charge because the new task inherited ShopAIKey's old `900s` elapsed,
stalled and exhausted fields, so claim scan terminalized before polling it. Worker
was stopped; attempts remain `40`, lock released, wallet `200/0`, transactions `0`,
credit events `1`, provider usage `0`, identity counts `32/28/27`, artifacts `0`.

The local receipt correction force-resets every accepted replacement task to fresh
`provider_running/queued`, clears all elapsed/stall/exhausted/failure fields, and
keeps the task poll-only at cap. RED `1 failed`; exact GREEN `1 passed in 6.08s`;
focused `68 passed in 11.04s`; affected impact `270 passed in 64.50s`. Source tests
made no provider call or wallet mutation. Next deploy/CAS may only poll the existing
scene-2 task; it cannot submit any third call.

## Pollable scene-2 task ledger authority RED

PR #962 merged/runtime exact SHA
`8624a528102ebb30a9da1a33d02da9a367c18ee6`; deploy run `33488979036`
SUCCESS in `3m13s`. The backup-safe poll-only CAS kept existing identities and
authorization cap `2/2`, but the worker terminalized before polling because the
persisted root summary still said scene 2 was failed. The current task-bearing
scene row remained `provider_running/queued`, pollable, elapsed `0` and not
stalled; scene 1 remained failed with no task.

The ledger previously ranked the stale failed summary above the current running
row whenever that row did not carry a separate current-status telemetry field.
The minimal correction treats only a current scene task row with a pollable task
and a non-terminal status as authoritative over the stale failed summary. It does
not copy an active task into scene 1, and explicit current provider failure remains
terminal. RED `1 failed, 1 passed`; exact GREEN `2 passed in 7.57s`; focused
inverse guard `2 passed in 6.13s`; job28/ledger `49 passed in 9.65s`; impact
`197 passed, 1 deselected in 31.37s`.
Clean main reproduced the deselected historical attempts assertion as `1 failed in
612.99s`, therefore `NEW_FAILURES=0`. Full compile returned
`PY_COMPILE_EXIT=0`; locked engine route hash PASS. Source verification made no
provider call or wallet mutation. The only allowed live continuation is polling
and downloading the already accepted scene-2 task; no third submit is authorized.

## Scene-1 stale task ownership RED

PR #963 squash/runtime `6960c7f66c122c887bf5e0f9246f30d316b48e2c`;
deploy `33496787770` SUCCESS in `3m6s`. Bot and Owner worker checkout matched exact
SHA with tracked diff `0`; Owner worker remained inactive PID `0`, bot/web/nginx
active and health OK. Snapshot rehearsal and production poll-only CAS both passed:
identity `28/32/27`, attempts `40`, cap `2/0`, scene 2 task length `37`, submit
false, wallet `200/0`, transactions `0`, credit events `1`, usage and charged Xu
`0`. Production backup is `/opt/toanaas/bot/delete/pv2-r01-job28-scene2-poll-only-
production-20260901T172821.json`, SHA `78872b67...`, mode `0600`.

The deployed ledger correctly returned `processing_scenes`, active scene `[2]` and
continued polling, but a read-only verifier blocked worker start because scene 1's
old task still entered durable ownership from historical `scene_ledger`, provider
events, winner map and canonical summary. Both current scene rows already declared
scene 1 failed/exhausted/taskless; therefore the old task was not a valid current
authority. Worker was never started and provider calls stayed `0`. A fail-closed
pause CAS returned the existing job/project to failed-no-charge while preserving
outbox, task, receipts, cap, attempts and finance. Pause backup is
`/opt/toanaas/bot/delete/pv2-r01-job28-scene1-ownership-guard-
20260901T173710.json`, SHA `09713e3d...`, mode `0600`.

The minimal correction derives explicit current taskless scenes from current result
rows only. A scene is eligible only when its current rows contain no task identity
and explicitly report `task_id_present=false`, `task_pollable=false`,
`exhausted=true` and terminal failed status; task-bearing historical rows for only
that scene are then ignored. Every current row for the scene must agree; a
disagreeing row preserves task ownership. A current accepted or terminal task
remains authority. Primary RED `1 failed in 6.19s`; GREEN `1 passed in 5.05s`;
self-review disagreement RED `1 failed in 6.23s` -> consensus GREEN `2 passed in
5.50s`; old/new exact guards `4 passed in 5.70s`; focused `51 passed in 8.69s`;
impact `199 passed, 1 exact baseline deselected in 27.08s`; locked engine hash and
final full compile PASS. Source verification made no provider call or wallet
mutation.

## Key4U official model-qualified poll ID RED

PR #964 squash/runtime `85cb4482149a7965afc76da00ce636db1914b72a`;
deploy `33501305826` SUCCESS in `3m25s`. Bot and Owner worker checkout matched exact
SHA with tracked diff `0`; bot/web/nginx active and health OK. Snapshot rehearsal,
production alias-clear CAS and deployed pre-start verifier all passed. Scene 1 was
failed and taskless; scene 2 retained the existing 37-character task hash prefix
`925d3315ec8a`, active/pollable; cap `2/0`, submit false, finance unchanged.
Production backup is `/opt/toanaas/bot/delete/pv2-r01-job28-scene2-poll-only-
production-20260901T182800.json`, SHA `25d54637...`, mode `0600`.

Owner worker PID `996057` claimed existing job `28` exactly once. It terminalized
failed-no-charge and was stopped inactive PID `0`. Sanitized terminal forensic
separates the generic journal label from transport truth: root submit called false,
submit HTTP `0`, every new attempt has `phase=poll`, Key4U poll HTTP `400`, the
accepted task hash and authorization cap remain unchanged, provider usage `0`,
transactions `0`, credit events `1`, wallet `200/0`, charged Xu `0`, and artifact/
concat/delivery are all `0`. Therefore no third paid submit occurred.

Runtime/backup evidence records model `veo3.1-fast`, interface
`key4u_google_veo_exclusive`, and a raw `task_...` accepted ID. Key4U's official
OpenAI query contract is GET `/v1/videos/{id}` and its documented example uses a
model-qualified ID such as `sora-2:task_...`; polling the raw ID produced the
measured HTTP `400`. The minimal correction qualifies a raw `task_...` with the
configured model exactly once, only when provider is Key4U, host is official and
the path is exact OpenAI `/v1/videos/{task_id|id}`. Already-composite IDs, generic
query, Kling, Hailuo and custom proxy routes stay unchanged.

RED `1 failed, 5 passed in 8.52s`; exact GREEN `6 passed in 4.93s`; focused Key4U/
job28 `52 passed in 6.38s`. Broad branch `371 passed, 1 skipped, 61 failed in
48.17s`; clean main exact selector `365 passed, 1 skipped, same 61 failures in
601.32s`, so `NEW_FAILURES=0`. Locked engine hash PASS in `7.23s`; full compile and
diff-check exit `0`. Source verification made no provider call or wallet mutation.

## Existing-task model-family poll contract RED

PR #965 squash/runtime `bbfeca06926b68fb0e9ffd5772ceecdf4d6fd335`;
deploy `33507905216` SUCCESS in `4m14s`. Bot and inactive Owner worker matched exact
SHA with tracked diff `0`; bot/web/nginx active and health OK. Snapshot rehearsal,
production alias-clear CAS and deployed ledger verifier passed. Scene 1 was
taskless; scene 2 retained accepted task hash prefix `925d3315ec8a`, active/
pollable; cap `2/0`, submit false, wallet/transactions/usage/charged Xu unchanged.
Production backup is `/opt/toanaas/bot/delete/pv2-r01-job28-scene2-poll-only-
production-20260901T193600.json`, SHA `0ad9b441...`, mode `0600`.

Owner worker PID `1002035` claimed existing job `28` once, terminalized and was
stopped inactive PID `0`. Terminal forensic again proves no third submit: root
submit called false, submit HTTP `0`, accepted task/cap/finance unchanged, only poll
HTTP `400`, artifact/concat/delivery `0`.

The composite-ID adapter correction was deployed but its safe marker path was not
reached. Source trace found the precise boundary: `poll_existing_task` reconstructs
a synthetic `VideoSubmitResult` from persisted task IDs, but omitted
`provider_poll_url_override`. The subsequent poll therefore used generic Key4U
`/v1/video/query?id={task_id}` instead of the configured Google Veo/OpenAI family
poll contract. The minimal correction derives the model-family contract from the
current Key4U adapter only when no persisted override exists. An explicit/custom
override remains authoritative; safe booleans/source markers persist, but the URL
itself is not exposed in result/debug output.

RED `2 failed in 5.50s`; GREEN `2 passed in 5.69s`; final end-to-end contract chain
`8 passed in 5.01s`; focused existing-task/Key4U/job28 `67 passed in 7.02s`.
Broad branch `373 passed, 1 skipped, exact same 61 baseline failures in 37.98s`,
therefore `NEW_FAILURES=0`. Locked engine hash PASS in `5.05s`; direct and full
compile plus diff-check exit `0`. Source verification made no provider call or
wallet mutation.

## Provider task terminally absent after poll-contract recovery

PR #966 squash/runtime `47d56e5c78efebb5fded42fec456b13f84c9a37c`;
deploy `33511826474` SUCCESS in `3m57s`. The latest shared runtime
`3d45e2e9755279523b812de7f57e02df35f73e7b` contains PR #966 by ancestry. Bot and
Owner worker matched exact runtime, tracked diff `0`, bot/web/nginx active and
health OK; Owner worker remained inactive before CAS.

Snapshot rehearsal, production alias-clear CAS and deployed ledger verifier passed.
Production backup is `/opt/toanaas/bot/delete/pv2-r01-job28-scene2-poll-only-
production-20260901T215503.json`, SHA `16201473...`, mode `0600`. Scene 1 was failed
and taskless; scene 2 retained accepted task hash prefix `925d3315ec8a`, active/
pollable; cap `2/0`, submit false and finance unchanged.

Owner worker PID `1016755` claimed existing job `28` exactly once and was stopped
inactive PID `0` after terminal. Sanitized forensic proves both source corrections
were in effect: `provider_poll_contract_recovered=true`, endpoint source
`KEY4U_VEO_VIDEO_POLL_URL`, and `poll_task_id_model_qualified=true`. Key4U returned
HTTP `400` with safe message `task_not_exist`. Root submit remained false with HTTP
`0`; no third submit occurred; accepted task hash/cap/identity remained unchanged;
artifact, concat and delivery were `0`; wallet `200/0`, transactions `0`, credit
events `1`, provider usage `0`, charged Xu `0`.

This is now an external authority blocker, not another source-routing ambiguity.
Both approved replacement calls are consumed and the only accepted task is absent
at provider. Producing the required two-scene MP4 needs a new explicit Owner paid-
call authorization on existing identity `job 28 / project 32 / outbox 27`. Under
the current authorization, no third submit, new job/project/outbox, upload/Confirm
replay or ShopAIKey resubmit is permitted. `PV2-R01`, `SPEC-04H.8/.9` and
`SPEC-04I` remain open.

## V3 two-scene replacement authority

The Owner supplied a new exact V3 authorization for existing identity `job 28 /
project 32 / outbox 27` only. V2 remains immutable and consumed at `2/0`. V3 grants
exactly two new paid Key4U calls: one replacement for scene 1 and one for scene 2.
It forbids a new job/project/outbox, upload or Confirm replay and any ShopAIKey
resubmit. User-visible/persisted/planned price remains `144/144/144`, provider
budget/cost cap remains `212/212`, and Owner charged Xu remains `0`. Execution must
stop after two V3 calls or a terminal two-scene MP4, whichever happens first.

Source audit found one exact seam before production CAS: durable worker merge kept
only the active authorization's receipt namespace, so activating V3 could erase the
historical V2 receipts. The RED reproduced only that loss: `1 failed, 2 passed, 22
deselected in 635.35s`. The minimal correction copies every persisted namespace
unchanged and permits incoming receipts only within the persisted active V3
namespace. V2 replay or overwrite is ignored, while V3 starts independently at
`0/2` and each scene can consume only one slot.

Exact V3 GREEN is `3 passed, 22 deselected in 5.39s`; job28 focused is `50 passed
in 12.34s`; focused plus locked engine/UI comparators are `78 passed in 9.92s`.
The broad branch has `338 passed, 73 failed`; clean main has `335 passed` and the
exact same 73 failed test IDs in `715.58s`, therefore `NEW_FAILURES=0`. Full compile
for `bot.py`, `local_worker.py`, `services/remote_worker_api.py` and the changed test
returned exit `0`; diff-check passed. Source gates made `0` provider calls and `0`
wallet mutations. Next action is one PR/deploy, exact-runtime readback, backup-safe
rehearsal/CAS, then one worker start under the V3 hard stop.

## V3 live idempotency boundary

PR #970 squash/runtime `0780f7ae4a0215a74bc46792bf528061a52ffb76`;
deploy `33533569117` SUCCESS in `3m44s`. Bot and Owner worker matched exact SHA with
tracked diff `0`; bot/web/nginx were active. Snapshot rehearsal, production CAS and
the deployed pre-start parser/claim verifier passed. V3 was `0/2`, V2 stayed
immutable at `2/0`, only scene 1 was controlled, all prices/caps/wallet values were
unchanged, and DB/provider/wallet pre-start mutations were `0/0/0`. Production
backup `/opt/toanaas/bot/delete/pv2-r01-job28-v3-replacement-production-
20260902T000903.json` has SHA `ec0c5b7b...` and mode `0600`.

The first V3 worker tick was stopped before scene 2. It persisted a V3 scene-1
receipt at `1/1`, but the task hash prefix `e5ec08abdfc0` exactly matched the old V2
task from the proven backup; `provider_http_request_sent=false` and submit HTTP `0`.
Thus no genuinely new paid call is evidenced and the receipt must not consume V3.
Worker PID `1035369` was stopped to inactive PID `0`; wallet `200/0`, transactions,
provider usage and charged Xu stayed `0`; artifact/concat/delivery stayed `0`.

Code tracing isolated the exact source: `product_video_scene_stall_policy` generated
the versioned replacement idempotency key, but `_render_scene_async` discarded it
and recomputed the legacy fallback key. Key4U deduplication therefore returned the
old V2 task. RED `1 failed, 24 deselected in 551.30s`; minimal GREEN `1 passed, 24
deselected in 6.63s`. Job28/fallback comparators are `50 passed in 10.21s`; legacy
fallback plus locked engine/UI comparators are `57 passed in 8.34s`; compile and
diff-check exit `0`. The correction propagates the policy key when present and keeps
the legacy key unchanged for non-versioned fallback. After ship, only the false V3
scene-1 receipt may be CAS-reset before resuming the unchanged two-new-call cap.
Final strategy verification returned `8 passed` plus the exact pre-existing PV2-R03
fixture SHA failure; this correction changes no PV2-R03 file. YAML, changed-file
compile, diff-check and secret scan returned exit `0`.

## V3 ledger namespace persistence boundary

PR #971 squash/runtime `538b3e605b65f8580d44d17f53f72b7a15f7b7bd`;
deploy `33538556118` SUCCESS in `3m30s`. Bot and inactive Owner worker matched exact
SHA with tracked diff `0`; bot/web/nginx were active. Current read-only production
state remained failed-no-charge with only the false V3 scene-1 receipt, old task
hash `e5ec08abdfc0`, transport HTTP `0`, no artifact/delivery and unchanged finance.
However, the immutable V2 receipt namespace had disappeared during the worker cycle.

Three snapshot stages isolated the exact writer without provider calls. Actual claim
and worker payload preserved both `{V2,V3}`. Calling the actual fail/defer API with
persisted `{V2,V3}` plus an incoming V3-only diagnostic also preserved both. In both
stages production DB changes, provider calls and wallet mutations were `0/0/0`.
The only remaining boundary was `product_video_scene_ledger_state(job, result)`:
its replacement-field projection let a partial active-only `result` overwrite all
persisted namespaces from `job`, so the following fail API could no longer recover
V2.

Ledger RED `1 failed, 25 deselected in 651.64s`; final GREEN `1 passed, 25 deselected
in 7.23s`. The minimal correction starts with every persisted namespace, accepts new
receipts only for the active V3 authorization, and ignores an incoming attempt to
rewrite V2. Job28/persistence focused tests are `52 passed in 10.66s`; locked engine/
UI comparators are `48 passed in 9.42s`; changed production/test compile and diff-
check exit `0`. No production reset or worker restart is allowed before this seam is
deployed and the immutable V2 namespace is restored from the proven backup.

## V3 taskless replacement authority

PR #972 squash/runtime `53d8305ba7a90a2d9a5bb6c7cd1ca32d76a9405b`;
deploy `33542877096` SUCCESS in `3m27s`. Bot and inactive Owner worker matched exact
SHA with tracked diff `0`. False-receipt reset rehearsal, production CAS and the
deployed pre-start verifier passed. V2 was restored to immutable `2/0`; V3 reset to
`0/2`; scene 1 alone was selected; identity, `144/144/144`, `212/212`, wallet
`200/0`, transactions/provider usage/charged Xu stayed exact. Production backup
`/opt/toanaas/bot/delete/pv2-r01-job28-v3-false-receipt-reset-production-
20260902T013030.json` has SHA `a279da68...` and mode `0600`.

The next worker resume was again stopped before scene 2. Exact submit forensic now
proved `submit_invoked_count=0`, `provider_http_request_sent=false`, and every new
attempt was only a poll of historical tasks. No genuinely new paid call occurred.
The old scene task aliases had been revived from manifest/ledger state, and the
legacy recovery executor required a provider task ID before it would evaluate a
replacement. That combination guaranteed another old-task poll instead of a V3
submit even though V3 authorization and its versioned idempotency key were valid.

The correction makes taskless replacement an explicit V3-only contract. A scene may
submit without an old task only when V3 identity/finance is valid, the scene remains
authorized, claim selected that exact nested scene row, and Key4U is its candidate.
V2, non-versioned and unselected scenes still fail closed. Canonical manifest tasks,
task lists, result URLs and artifact aliases are suppressed only when every current
DB row agrees the scene is taskless and V3 authorizes it; a V2 payload or disagreeing
row preserves recovery state.

Taskless RED was `1 failed, 1 passed, 26 deselected in 10.50s`; claim-scope RED was
`1 failed, 28 deselected in 7.35s`; stale-manifest RED was `1 failed, 31 deselected
in 5.86s`. Final exact taskless/pending/two-scene suite is `7 passed, 26 deselected
in 5.80s`; job28/persistence focused is `59 passed in 11.32s`; locked engine/UI is
`57 passed in 10.48s`. Full `bot.py`, `local_worker.py`, connector and changed-test
compile, diff-check and secret scan PASS. Two-scene mock output proves calls `[1,2]`
in receipt order, distinct V3 keys, empty pending IDs, immutable V2 namespace, V3
exactly `2/2` and charged Xu `0`. No live restart is allowed until this seam is
deployed and both DB plus canonical manifest are reset to taskless V3 `0/2`.
Final strategy verification returned `8 passed` plus the exact pre-existing PV2-R03
fixture SHA failure; no PV2-R03 file is changed by this correction.

## V3 taskless watchdog worker-wait boundary

PR #973 squash/runtime is `ab267bedd4aa300bf2160be7b8d828009578127c`;
deploy run `33588541923` completed SUCCESS in `4m2s`. Bot and inactive Owner worker
matched exact SHA with tracked diff `0`. The combined SQLite + canonical-manifest
taskless reset then passed. Its production backup is
`/opt/toanaas/bot/delete/pv2-r01-job28-taskless-v3-reset-production-
20260902T112112.json`, SHA `9739d756781ffbb213867f6484d38ff38513b96c4c5ba875cca50729acd4a06c`,
mode `0600`. V2 receipt scenes `[1,2]` stayed immutable; V3 stayed `0/2`; scene 1
alone was selected; DB and manifest task/artifact aliases were empty; wallet,
transactions, provider usage and charged Xu were unchanged.

The bot zero-task watchdog ran before the intentionally inactive Owner worker could
publish a fresh heartbeat. Its eligibility recheck had no candidate and retained
the read-only recovery source, so `ok=false` was treated as a permanent admission
block. It terminalized existing job/project/outbox `28/32/27` before worker claim.
No Key4U submit occurred, V3 remains genuinely unused `0/2`, the manifest remains
taskless, and artifact/concat/delivery remain zero.

The regression test uses the actual SQLite job/project/outbox boundary. RED was
`1 failed, 1 passed, 33 deselected in 528.98s`: exact V3 was terminalized while the
non-V3 inverse guard correctly failed closed. A second strict-scope RED was `3 failed,
37 deselected in 7.77s`: a different self-consistent V3 ID, identity or price/cap
could still inherit the wait branch. Final GREEN is `7 passed, 33 deselected in
5.15s`; full job28 authority is `40 passed in 7.64s`; protected zero-task/outbox
is `85 passed in 31.58s`. Combined branch coverage is `220 passed, 2 failed in
50.98s`; clean `ab267bed` reproduces both exact IDs in `547.25s`, therefore
`NEW_FAILURES=0`. Full `bot.py`, local worker, changed source/test compile and
diff-check exit `0`.

The correction does not reopen generic watchdog behavior. It waits only when the
existing taskless scene has exact active authorization ID
`pv2-r01-job28-key4u-replacements-v3`, identity
`28/32/27/VID-20260829-D78AA3`, immutable receipt namespaces, V3 `0/2`, price `144`,
cap `212`, zero charge, one selected Key4U scene, and the
only live blocker is worker disconnected, stale heartbeat or expired lease. The
historical `worker_poll_existing_task_read_only` marker may accompany that transient
worker blocker. Missing/malformed/consumed authority, permanent SHA mismatch,
capability mismatch, permanent provider-route block, finance mismatch or a selected-
scene mismatch remains terminal fail-closed. Once deployed, use a new backup-safe
CAS for the already-clean failed rows; do not replay the old task-hash reset script.
Start the Owner worker once and stop after two genuinely new V3 calls or a terminal
two-scene MP4.

The new recovery command is separate from the consumed task-hash reset. It requires
the already-clean manifest, exact failed watchdog state, attempts `40/1`, inactive
worker and exact deployed bot/worker SHA. Local SQLite rehearsal changed only job,
project, outbox and two scene statuses; preserved manifest SHA, V2, V3 `0/2`, prices,
wallet/provider counts and charged Xu. A duplicate invocation and an invalid V3
fixture both failed before mutation. Production execution remains pending exact
deploy/runtime readback; rehearsal provider calls and wallet mutations were `0/0`.
Final strict-scope full `bot.py`, local worker, queue and changed-test compile exit
`0`; YAML, diff, secret and forbidden-scope gates are clean. Strategy V2 is `8
passed` plus the exact pre-existing PV2-R03 fixture SHA failure; this correction
changes no PV2-R03 file.

After SubDub PR #974 deployed, this one Product Video commit rebased conflict-free
onto exact main/runtime `c8e954a03322f4af8559cf3f6e99178dbd6bfe7a` with no
overlapping file. Post-rebase combined job28/watchdog/outbox/restart coverage is
`220 passed, 2 failed in 924.92s`; clean exact main reproduced the same two failure
IDs in `856.69s`, therefore `NEW_FAILURES=0`. Full `bot.py`, local worker, queue and
changed-test compile exit `0`; Strategy remains `8 passed` plus the exact PV2-R03
fixture baseline, and YAML/diff/secret/forbidden-scope gates are clean.

## V3 fresh-worker claim handoff boundary

PR #975 squash-merged exact runtime
`f507feef5f546211c064c79eb15c310ec8a4d682`; deploy run `33609379330` was SUCCESS
in `3m39s`. The PR showed zero checks because the existing compile workflow filters
out changes that do not touch `bot.py`, its compile script or the workflow itself;
local post-rebase full compile and protected test evidence remained the gate. Bot
checkout matched exact SHA with tracked diff `0`. The detached Owner worker checkout
was still `ab267bed...`, so it was advanced from the deployed local bot repository
only after proving clean status and ancestry. Backup ref
`refs/backups/worker-pre-product-video-20260902084632` preserves the old SHA; worker
ended exact `f507feef...`, compile exit `0`, tracked diff `0`, inactive PID `0`.

The VPS SQLite backup API produced a `14,184,448`-byte rehearsal snapshot mode
`0600`. Exact-runtime CAS rehearsal and replay-fail-closed passed; all temporary
files were removed. Production recovery then passed with backup
`/opt/toanaas/bot/delete/pv2-r01-job28-watchdog-recovery-production-
20260902T155114.json`, SHA `53dd0c48854fbd133c9a07b5e0f4cdc1a46b97f6d50337f9ade6646bd490b734`,
mode `0600`. After more than one watchdog interval, job/project/outbox stayed
`queued/queued_for_worker/acknowledged`, exact taskless wait marker was true, V3
stayed `0/2`, both DB scenes stayed pending, charged Xu stayed `0`, and manifest SHA
stayed `6f2c69472c56c123fdfa65fd9b5ea34d93a97b59817d5d19d351f7d55c43883b`.
The read-only prestart verifier passed all 15 checks including scene-1-only claim,
Key4U runtime/contract readiness, immutable V2 and finance.

One Owner worker start at PID `1097461` produced a new pre-provider LIVE RED. The
bot watchdog rechecked the now-fresh worker, retained only
`worker_poll_existing_task_read_only`, and terminalized the taskless job before the
worker emitted a claim. Worker was stopped inactive PID `0`. Job/project/outbox
identity counts remained `32/28/27`; V3 remained `0/2`; wallet stayed `200/0`;
transactions, credit events and provider usage remained `0/1/0`; provider transport,
artifact/delivery and charged Xu remained `0`.

The integration test now covers the real bot-watchdog-to-worker-claim sequence.
RED was `1 failed, 40 deselected in 994.59s`. Minimal GREEN was `1 passed, 40
deselected in 9.20s`; focused inverse plus claim was `5 passed in 13.47s`; full
job28 authority was `42 passed in 10.91s`; protected watchdog/outbox was `85 passed
in 51.23s`; combined scope was `222 passed, 2 exact baseline failures in 61.21s`,
so `NEW_FAILURES=0`. Exact V3 may interpret the read-only marker as a fresh-worker
claim handoff only when worker blocker is empty and every existing exact identity,
price, cap, receipt and scene guard passes. Worker-side sweep then moves the
acknowledged outbox through retry/lease and claims job 28. A permanent provider
route blocker remains terminal fail-closed. No provider or wallet action occurs in
the source test.

After SubDub PR #976 deployed, the claim-handoff commit rebased conflict-free onto
exact main/runtime `dd217036577e2627a9bfcf8ce1ed510ba6ebb233`. Git correctly
skipped Product Video PR #975 as already upstream and replayed only this new seam.
Post-rebase focused claim/inverse coverage was `5 passed in 10.46s`; full job28
authority plus protected watchdog/outbox was `127 passed in 33.26s`; full `bot.py`
and changed-file compile exit `0`; YAML/diff/Strategy/secret/forbidden-scope gates
retain the exact source result.

## V3 acknowledged-outbox wake and controlled-candidate handoff

PR #977 passed compile run `33630623078`, squash-merged as
`c3167ef2de6e3beada8297a54e724f22dff5613f`, and deploy run `33630731575` was
SUCCESS in `4m20s`. Bot and inactive Owner worker matched the exact clean SHA;
bot/web/nginx were active and health was OK. Snapshot rehearsal and duplicate
replay rejection passed. Production recovery backup
`/opt/toanaas/bot/delete/pv2-r01-job28-watchdog-recovery-production-
20260902T195036.json` has SHA
`33cbbfa054491f41f656f82d57fae2705cbca73d8cabd11a33871cc3a9a2deb1`, mode
`0600`. Identity `28/32/27`, V2 `[1,2]`, V3 `0/2`, quote `144`, cap `212`, wallet
`200/0`, transactions/provider usage/charged Xu all remained unchanged.

One worker start at PID `1116240` produced another pre-provider LIVE RED. Every
exact V3 wait/identity/finance/receipt/scene guard was true and the persisted marker
`taskless_v3_authority_ready_for_worker_claim` was true, but the outbox remained
`acknowledged`. After the wake boundary, generic runtime eligibility still replaced
the validated controlled Key4U candidate with an empty candidate list. The watchdog
terminalized the same job before claim. Worker was stopped inactive PID `0`; V3
receipts remained empty `0/2`, provider usage/transactions/charged Xu stayed `0`,
and no artifact or delivery was created.

The production-aligned RED is `1 failed, 41 deselected in 11.38s`. The minimal
correction changes only two handoff points: an exact V3-ready acknowledged outbox is
made immediately claimable, and the claim stage consumes only the candidate already
returned by the validated controlled-fallback parser. Full authority is `42 passed
in 5.75s`; protected scheduler/outbox/public-confirm coverage is `224 passed, 1
deselected in 54.40s`. Exact clean main reproduced the deselected `job_131` failure
in `569.47s`, so `NEW_FAILURES=0`. Changed source/test compile and diff-check exit
`0`. No provider call or wallet mutation occurred during source verification.

## V3 unified Key4U Veo contract RED

PR #978 passed compile run `33637384667`, squash-merged as
`833dc6ccd6112c2a92b6e0dde8a49a74b3490bfd`, and deploy run `33637571154` was
SUCCESS in `5m0s`. Bot and inactive Owner worker matched the exact clean SHA after
backup ref `refs/backups/worker-pre-product-video-20260902T135036Z`; services and
health were OK. Fresh snapshot rehearsal and duplicate rejection passed. Production
CAS backup `/opt/toanaas/bot/delete/pv2-r01-job28-watchdog-recovery-production-
20260902T205253.json` has SHA
`c8c24164e2600169047965e918317f5f12431d81cc618aecee3ecfaca0e5670d`, mode
`0600`; deployed prestart passed 15/15.

One worker start at PID `1121117` crossed the repaired claim boundary and advanced
job attempts `40 -> 41`. Scene 1 then stopped at Key4U HTTP `404` before any task or
V3 receipt. The worker was stopped inactive PID `0`; V3 remained `0/2`, provider
usage/transactions/charged Xu stayed `0`, and artifact/delivery stayed empty.

The earlier endpoint interpretation was wrong and is now explicitly superseded:
Key4U's current OpenAPI places Veo unified generation at POST `/v1/video/create`
with GET `/v1/video/query?id={task_id}`. POST `/v1/videos/generations` belongs to
the Grok official-format group, not Veo. The bounded correction changes only new
Veo submissions on official Key4U hosts. It preserves the persisted pricing model
`veo_3_1-fast`, emits the unified wire alias `veo3.1-fast`, sends only documented
unified fields, and derives the matching poll route from the accepted submit.
Custom proxy `/v1/videos`, historical OpenAI task polling, Kling and Hailuo remain
unchanged.

Sanitized before/after production forensic confirms this was not a stale `404`.
Before the CAS, the same scene and provider-attempt set had HTTP `0`; after the one
worker cycle, scene 1 had exactly one Key4U event at HTTP `404`, no task and no V3
receipt. The worker's base Key4U adapter was already configured for
`/v1/video/create`, while the model-specific Google Veo resolver still overrode a
new submit to `/v1/videos/generations`. The correction removes that override only
for official Key4U hosts and derives unified polling only from a newly accepted
unified submit, so historical OpenAI task polling remains locked.

Contract RED was `1 failed, 19 deselected in 9.14s`. Key4U GREEN is `20 passed in
7.23s`; existing-task/custom guard is `2 passed`; job28 wire guard is `2 passed`;
focused final is `89 passed in 12.04s`. The broad branch has `167 passed, 25 failed,
1 skipped in 22.30s`; exact clean main has the same 25 IDs plus one obsolete payload assertion,
so `NEW_FAILURES=0` and one baseline was closed. Source verification made `0`
provider calls and `0` wallet mutations.

The commit rebased conflict-free onto SubDub PR #979 main/runtime
`899a93f5420f47c95fcc88cd4b8de655f7fee8c8`; the scoped branch is `0 behind / 1
ahead`. Post-rebase
focused remains `89 passed in 10.21s`; broad remains `167 passed, 25 exact baseline
failures, 1 skipped in 24.84s`, so `NEW_FAILURES=0`.

The consumed watchdog CAS is not reused. A separate attempts-`41`/outbox-`2`
Key4U-404 CAS passes isolated rehearsal; duplicate replay, invalid V3, wrong HTTP and
wrong attempts all fail before backup. Its script/test SHA are `F62AEF1F...` and
`042EC460...`. Reconstructed scene authority returns to historical ShopAIKey while
only exact V3 selects Key4U, so ShopAIKey cannot be resubmitted. Production remains
untouched until this source is deployed and the exact-runtime snapshot rehearsal
passes.

## V3 Key4U model-authority correction

PR #980 was squash-merged/runtime-synced as
`54309814910e469a763bccd511c209bbebe697e5`; compile run `33652913080` and deploy
run `33653080637` both succeeded, with deploy duration `3m25s`. A fresh strict
recovery at current attempts `42` and outbox attempts `3` made exactly one new
scene-1 Key4U submit. The official host/path accepted the request far enough to
return a structured HTTP `404` `model_not_found` for wire model `veo3.1-fast`.
There was no provider task, V3 receipt, clip, concat, artifact or delivery; V3 stayed
genuinely `0/2`, V2 stayed immutable, and provider usage, transactions and charged
Xu stayed `0`.

That result supersedes only the prior wire-alias assumption above. The claimed
fallback scene retained ShopAIKey-oriented `selected_model`, payload adapter and
provider model/default maps. `_render_scene_async` therefore skipped the existing
tier resolver and the Key4U adapter fell through to the worker ENV model. The
minimal correction invokes the existing resolver only when the validated fallback
candidate is exactly `key4u_video`, with current tier/capability/concat requirements.
It overlays only that scene's model metadata (`veo_3_1-fast`, duration `8`, resolution
`1080p`) and preserves the resolved model on the unified wire. Resolver failure or
provider mismatch raises an exact no-charge blocker before any HTTP call. All
non-fallback scenes/providers, custom proxies, existing-task polling, authorization,
pricing, wallet and Tail code remain unchanged.

Production-shaped authority RED was `1 failed in 8.94s`; fail-closed mutation RED
was `1 failed in 12.84s`; diagnostics RED was `1 failed in 6.56s`. Exact GREEN is
`2 passed in 6.90s`; focused job28/Key4U/fallback is `89 passed in 11.76s`. The broad
branch is `182 passed, 12 failed in 29.76s`; an isolated clean `5430981` snapshot is
`181 passed,` the exact same `12` failures in `644.54s`, so `NEW_FAILURES=0` and the
extra branch case is the new passing guard. Strategy branch and clean each have
`8 passed` plus the same PV2-R03 fixture SHA failure. Full compile for bot, both
workers and changed files exits `0`; diff-check exits `0`; source tests made `0`
provider calls and `0` wallet mutations.

Read-only VPS preflight confirms `toanaas-bot.service` loads
`/etc/toanaas/bot.env`, while `toanaas-worker-owner-product-video.service` loads the
readable `/etc/toanaas-worker.env`. The Key4U auth, enable, submit-route and model
variable names are all present. No secret value was printed or changed and no
service was mutated. The next recovery must use a new exact attempts-`42`/outbox-`3`
snapshot-first CAS; the attempts-`41` script is stale and must not be replayed.

The correction rebased cleanly onto SubDub PR #981/runtime
`09a06aef40b1c21cc5ab4197c3da18f697e0fbba`. On that base, focused Product Video
authority is `89 passed in 542.89s`; an isolated clean-main snapshot is `88 passed
in 543.86s`, with the extra branch case being the new passing fail-closed guard.
The broad branch remains `182 passed` plus the exact same `12` baseline failures in
`23.59s`; full bot/workers/changed-file compile and diff-check exit `0`.
`NEW_FAILURES=0` after integration.

## V3 accepted-task unified poll authority

PR #982 squash-merged as `095b6c88aa98a42ebbb3fc6535d44d7222e29779`;
deploy run `33706481637` succeeded in `3m34s`. Bot/web/nginx were active and the
inactive Owner worker was advanced from `5430981` to that exact clean runtime after
creating backup ref
`refs/backups/worker-pre-product-video-model-authority-20260903T030530Z`.

The first production CAS preserved current outbox attempt `3`, which equaled the
generic `max_attempts=3`; the bot watchdog therefore terminalized job 28 one second
after CAS and before worker start. No provider/wallet/artifact action occurred. A
stage-2 CAS was then written against the exact resulting marker/state. It resets
only the scheduler attempt `3 -> 1`; job attempt `42`, V2 receipts, V3 `0/2`, price
`144/144/144`, provider cap `212/212` and charged Xu `0` remain unchanged. Actual
watchdog code on a `14,184,448`-byte mode-`0600` snapshot preserved
`queued/queued_for_worker/retry_wait`, with `terminal_failed=0`, SQLite `ok`, and
replay fail-closed. Production backup SHA values are `b612d919...` for the SQLite
copy and `82355ce0...` for the stage-2 JSON, both mode `0600`.

Final prestart then passed all `15/15` checks. One worker start, PID `1214876`, sent
scene 1 to Key4U using model `veo_3_1-fast`; the provider returned HTTP `200` and a
37-character task was persisted. This real call is operationally call `1/2`, even
though its durable V3 receipt remained empty when polling failed. It must never be
resubmitted. Scene 2 was not submitted. Provider usage, transactions and charged Xu
remained `0`; the worker was stopped inactive PID `0`.

The accepted scene-1 task was reconstructed using the worker ENV dot model and
therefore polled through historical `/v1/videos/{task}`, producing
`provider_poll_http_error`. Production-shaped RED was `1 failed in 12.19s` and
captured that exact URL. The correction reads the persisted scene model and only
for exact `key4u_video + veo_3_1-fast + official /v1/video/create` restores
`/v1/video/query?id={task_id}`. It is poll-only and cannot POST. A dot-model inverse
test proves historical model-qualified `/v1/videos` is unchanged; custom proxies,
Kling, Hailuo and other products are untouched. Unified/inverse is `2 passed in
9.00s`; focused is `91 passed in 10.66s`; broad is `184 passed` plus the exact same
`12` baseline failures in `30.62s`, so `NEW_FAILURES=0`. Full bot/workers/router/
connector/provider/test compile and diff-check exit `0`.

PR #983 shipped that poll authority as runtime
`b3c217eb73324e316b62a052b6f86e0ee08c78e4`; deploy run `33779100072` succeeded.
An exact poll-only CAS then passed against a `14,184,448`-byte production snapshot,
six negative state variants and duplicate replay. It was applied once with DB backup
SHA `5e9609cb...`, manifest backup SHA `960a1c72...` and CAS JSON backup SHA
`67735746...`, all mode `0600`. A post-watchdog snapshot retained task SHA
`e0946432...`, V2 receipts `[1,2]`, V3 scene `[1]`, cap `1/1`, attempts `43/1`,
submit disabled and zero finance delta.

One guarded worker start at PID `1255055` advanced the accepted scene-1 provider
state to raw `completed`; scene 2 remained taskless and unreceipted. Before a clip
was persisted, the first claim/defer cycle dropped the immutable V2 namespace. The
guard stopped the worker at tick 2, inactive PID `0`. V3 stayed exactly `1/1`, the
scene-1 task hash was unchanged, artifact/delivery remained empty, wallet remained
`200/0`, and transactions/provider usage/charged Xu remained `0/0/0`.

The isolated root is row shape: `_product_video_replacement_ledger_fields` read
receipt fields directly from `job`, while the production SQLite row keeps them in
`job.result_json`. Existing tests supplied a hydrated flat dict and missed the
boundary. A production-shaped RED failed on the missing V2 namespace in `77.43s`.
The minimal correction parses the durable result JSON and overlays direct hydrated
job fields as the priority layer. Exact plus inverse GREEN is `2 passed in 5.22s`;
the final job28 authority file is `47 passed in 5.90s`; ledger/claim/poll blast radius
is `136 passed` plus one exact clean-main RouteEngine29O attempts baseline failure,
so `NEW_FAILURES=0`. Changed source/test compile and diff-check exit `0`.

Next, ship only this seam. After runtime sync, restore only immutable V2 from the
existing mode-`0600` evidence through a fresh exact-state rehearsal/CAS, retain the
accepted scene-1 task and V3 `1/1`, then resume poll/download. Scene 1 must never be
resubmitted. Scene 2 may consume the last call only after a valid scene-1 clip.

PR #984 shipped the row-shape fix as runtime
`6a30db5bfb099c52195e755afccf3a45f9826ca8`; deploy run `33788585436` succeeded
in `3m28s`. The inactive Owner worker was synchronized to the same clean SHA with
backup ref `refs/backups/worker-pre-product-video-receipt-row-20260903T181242Z`.

An immutable-V2 restore rehearsal then passed on a `14,184,448`-byte snapshot, six
negative variants and duplicate replay. Production CAS changed only the namespace
map, with DB backup SHA `7c5fe649...`, manifest backup SHA `6b5c28cc...` and CAS
JSON backup SHA `99c8bf2c...`, all mode `0600`. Post-watchdog verification proved
V2+V3 survived both ledger and telemetry, attempts remained `43/1`, V3 remained
`1/1`, scene-1 task SHA remained `e0946432...`, scene 2 remained taskless, and all
finance evidence remained zero.

Guarded resume PID `1288614` nevertheless lost V2 again before a clip and was
stopped at tick 2, inactive PID `0`, before scene 2 or another paid call. Replaying
actual claim and fail/defer against SQLite snapshots retained V2+V3 at every stage.
The remaining writer was `stamp_worker_claim_trace`: it serialized the whole job
through the generic secret filter, whose `authorization` marker removed not just
secrets but both sanitized durable authority/receipt keys. The worker diagnostics
therefore later contained only active V3.

The claim-trace RED failed on missing durable authorization in `5.39s`. The minimal
fix applies generic secret stripping first and then restores only the existing
whitelisted `_controlled_fallback_durable_internal_fields(payload)`. Injected
`api_key` and bearer header remain absent. Exact plus inverse GREEN is `3 passed in
5.09s`; final full authority is `48 passed in 6.35s`; Strategy V2 is `9 passed in
5.83s`; protected claim/watchdog/ledger/job28 is `114 passed in 15.74s`. Three
unrelated debug assertions fail identically on clean main, so `NEW_FAILURES=0`.

PR #985 shipped claim-trace preservation as runtime
`259bce40c095309b87a73a518a83904a6d6022ce`; deploy run `33833696318` succeeded
in `4m17s`. Bot and inactive Owner worker matched that exact clean SHA. An exact
public-path snapshot proved V2 `[1,2]`, V3 `[1]` and cap `1/1` survive before claim,
after claim trace, in the worker payload and after fail/defer. Live PID `1295567`
then kept the same namespaces over repeated cycles; scene 2 and finance were untouched.

The remaining scene-1 boundary is external result retention. Key4U query is HTTP
`200`, status `completed`, progress `100`; the adapter correctly parses top-level
`video_url` and uses the raw task. The signed `flow-content.google` URL expired at
`2026-09-03 22:01:27 +07` and returns `403 Forbidden`. A no-cache query returns the
same URL. Official `/v1/videos/{id}/content` returned `403` for the raw task and
`400` for the model-qualified form; official docs expose no refresh endpoint. These
checks made zero paid submit calls and zero DB/wallet mutations.

Owner therefore authorized V4 with exactly two new Key4U calls: one expired-link
replacement for scene 1 and one replacement for scene 2. V3 remains immutable at
`1/2` and cannot replay; existing identity `28/32/27`, quote `144/144/144`, provider
cap `212/212` and charged Xu `0` remain fixed. V4 watchdog RED failed `1` in `5.11s`
because the taskless wait gate allowed only exact V3. The minimal correction adds
only exact V4 to that allowlist. Exact plus strict-scope inverses are `6 passed in
5.08s`; full authority/protected watchdog is `82 passed in 10.74s`; full compile
and diff-check exit `0`.
