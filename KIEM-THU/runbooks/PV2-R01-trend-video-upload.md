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
`593.52s`, therefore `NEW_FAILURES=0`. Resume the preserved invoice only after
the Flow6 parity deploy; do not upload or create another configuration.

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

1. Open `Menu Video -> Video theo trend -> Gui video trend`.
2. Upload the exact fixture once. Verify the active owner is
   `video_trend_upload` and state becomes `awaiting_trend_video`.
3. Wait for the local analysis screen. It must show source duration/geometry,
   subjects, motion, camera, visual context and source-audio truth.
4. Click `Dung phan tich nay` once.
5. Select `2 canh`, then `Doc 9:16`.
6. Select `Chon loai noi dung`, profile `social_creator_trend`, then suggestion 1.
7. Read Preview and verify the source fingerprint, two-scene count, ratio, selected
   trend/profile and exact suggestion are preserved.
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
