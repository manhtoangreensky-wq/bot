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
