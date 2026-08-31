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
