# Product Video Live Strategy V2

File nay la checklist tong authoritative cho dot live Product Video tiep theo.
No thay the chien luoc cu "moi lane va moi tier deu tao video 2 canh". Lich su
job cu van duoc giu trong `.agents/state/P0_PRODUCT_VIDEO_FULL_LANE_LIVE_MATRIX.md`
nhung khong duoc dung de mo them job ngoai bang assignment ben duoi.

## 1. Pointer hien tai

`CURRENT_POINTER=V2-03/PV2-R01` - execute the first complex non-manual
representative: Video Trend upload, tier `400`, two 9:16 scenes, strict subtitle
and transition Add-ons, durable MP4/receipt/report and Owner zero-wallet proof.
The completed Tail UI and terminal engine seams remain byte-locked.

- [x] `V2-00` Trend4 Facebook failure loop: PR #914 merged as
  `d92a98ddbc10ea4c626f75a65c2ddb58403a2fc6`; deploy run `33107893686`
  SUCCESS; refresh live media/Facebook/YouTube/TikTok = `3/57/100/99`, next run
  +7 days, `paid_provider_calls=0`, transaction/credit/provider-usage deltas 0.
- [x] `V2-01` Registry audit: visible Product Video menu and Tail adapter contracts
  measured on merge SHA `d92a98d`.
- [x] `V2-02` Resolve active source-contract seams before any representative
  provider job.
- [-] `V2-03` Execute one representative complex non-manual lane per product;
  current row is `PV2-R01` only.
  - [x] Full Trend upload flow, shared Tail, tier `400`, Invoice `144 Xu`, one
    Confirm and exact admission `VID-20260829-D78AA3 / project 32 / job 28 /
    outbox 27` are proven. Two provider tasks were accepted, one per scene.
  - [x] LIVE RED forensic: both tasks remain durable and authoritative
    `IN_PROGRESS`, but root-only alive detection let stale `failed_no_charge`
    close job/outbox after `5` claims. Charged Xu and wallet deltas are `0`.
  - [x] Local source correction: focused/recovery `7 passed`; protected `68 passed + 5`
    exact baseline deselected; broad impact branch/main has the same 34 historical
    failures and `NEW_FAILURES=0`. No UI/Tail/quality/route/submit/wallet change.
    Claim-scan guard prevents explicit-exhausted job #27 from being recovered while
    preserving poll-only recovery for job #28.
  - [x] PR #934/deploy/runtime and exact bot/worker SHA `ef81f6a...` are proven.
    Fresh generation `4ab7fd...` exposed one bounded claim RED: three recovery slots
    were consumed before scene authority was corrected, while both tasks remained
    authoritative `IN_PROGRESS` and zero-charge.
  - [x] PR #935/deploy #151 and exact bot/worker SHA `06f38df...` are proven.
    Generation `b264fd4f...` used the authority marker once with all paid routes
    blocked, but stale root `continue_polling=false` terminalized the two live scene
    tasks one second later before their authority was consulted.
  - [x] PR #936/deploy #152 and bot/worker SHA `eba42c15...` are proven. The final
    marker executed with all paid routes blocked, but claim-scan merged stale
    `scene_status_by_index=failed` before actual per-task `IN_PROGRESS`, so job #28
    never reached worker CAS.
  - [x] PR #937/deploy #153 and bot/worker SHA `6e0e42d...` are proven. A backed-up
    CAS requeue of job #28 created no job/task/provider/wallet side effect, but
    task-bearing historical provider events and root canonical FAILURE still replaced
    per-scene current `IN_PROGRESS` before CAS claim.
  - [x] PR #938/deploy #154 and bot/worker SHA `3d16cf6...` are proven. Final CAS
    reached the worker (`attempts 5->6`) and established the two ShopAIKey tasks are
    truly exhausted, zero-charge and without artifact.
  - [x] Tier-400 map remains exact: quote `144 Xu`; ShopAIKey primary `4.550 VND/2`;
    Key4U VEO fallback `21.150,72 VND/2` with internal budget `212 Xu`. Customer price
    is unchanged; Owner accepts the negative fallback margin.
  - [x] Rebased onto `3d16cf6...`; focused fallback `9 passed`; branch matrix
    `88 passed + 3 exact baseline failures`; clean main reproduced the same three
    test IDs, so `NEW_FAILURES=0`. Compile/YAML/diff/secret gates are `0`.
  - [x] After SubDub PR #939, rebased cleanly onto `301d5b81...`; final focused
    fallback `9 passed in 8.49s`; compile/YAML/diff remained `0`, with the same
    8-file scope and production diff `0 added / 1 removed`.
  - [x] Customer-price/internal-budget separation shipped as PR #940, squash
    `aaf3a9c6...`, deploy #156 run `33302353405` SUCCESS. Bot and Owner worker
    run exact SHA; worker generation `284c6fe3...` is authenticated/persisted
    with empty reject reason.
  - [x] Final source review found the existing router cost guard was not receiving
    `fallback_provider_cost_xu` from the scene request. One-field propagation
    RED `1 failed in 8.29s` -> GREEN `1 passed in 5.56s`; fallback/Key4U
    protected `19 passed in 6.76s`; compile/diff `0`. No provider/wallet action.
  - [x] Cost metadata shipped as PR #941, squash `8134c28b...`, deploy #157
    run `33304170789` SUCCESS `3m18s`; bot/worker exact SHA, worker PID
    `728701`, generation `b8421a3a...`, heartbeat persisted/reject empty.
  - [x] Query-only production dry-run on job #28 passed with quote `144/144/144`,
    budget/cost `212/212`, scene 1 stalled, Key4U ready/contract-valid, preclaim
    applied to one scene and DB/provider/wallet side effects `0`.
  - [x] Dry-run review found single-candidate fallback did not enforce the cost
    guard before submit. RED proved Key4U `submit_calls=1` for cost `213>212`;
    minimal pre-submit guard GREEN; persisted count-before-submit `0` allows the
    current attempt while `1` blocks retry. Spend safety `12 passed`, affected
    total `49 passed`, compile/diff `0`.
  - [x] Single-candidate budget guard shipped as PR #942, squash
    `db5f6a81bfb505c23eca61d68db419b984822a22`; deploy #158 run
    `33307435330` SUCCESS `4m4s`; bot/worker exact SHA before live recovery.
  - [x] Query-only dry-run, snapshot rehearsal and production CAS passed.
    Backup `/opt/toanaas/bot/delete/pv2-r01-job28-fallback-cas-20260830T181523.json`,
    SHA `cbef07f...`, mode `0600`; quote/budget/cost and wallet/provider exact.
  - [x] Live RED after CAS: attempts `6->8`, terminal failed_no_charge before
    provider HTTP; usage/transaction/wallet deltas `0`. Preclaim applied, but
    worker payload rebuilt quote `400/0/0`, budget `0`, fallback scene `0`
    and dropped Key4U candidate/idempotency.
  - [x] Root is `build_worker_job_payload`: minimal conditional allowlist overlay
    preserves controlled authority only when existing-task recovery + terminal
    suppression + Key4U candidate are all true. Claim/hydrate integration `2 passed`;
    worker-to-scene render `1 passed`; expanded branch/main share exact 4 failures,
    focused branch/main share exact 2 failures, `NEW_FAILURES=0`.
  - [x] Worker-context overlay shipped as PR #943, squash `252758be...`; deploy
    run `33317232271` SUCCESS. Bot and stopped Owner worker were synchronized to
    latest runtime `1b259262...`; query-only preflight still proved quote
    `144/144/144`, budget/cost `212/212`, one scene-1 Key4U slot and side effects 0.
  - [x] Owner-authorized worker start exposed a provider-authority RED before
    artifact: attempts `8->40`, root repeatedly returned ShopAIKey
    `provider_in_progress`, and both scene rows were reclassified to Key4U while
    scene-level controlled flags/fallback counts remained `false/0`. Worker was
    stopped; artifacts/delivery/provider-usage/transaction/wallet deltas remained 0.
  - [x] Source correction is isolated to two guards: respect deferred
    `next_poll_at` before claim, and require claim-scoped scene index/marker/candidate
    before controlled fallback. Self-review also made scene-level Key4U candidate
    mandatory instead of falling back to root. RED `2 failed`; exact GREEN `2 passed`; focused
    `33 passed`; protected claim/stall/scene authority `165 passed`; full compile,
    YAML/diff/scope/secret gates `0`. Strategy verifier has `8 passed` plus the
    exact pre-existing Script fixture SHA failure; that fixture is byte-unchanged.
    Final self-review gate is `206 passed, 1 baseline deselected in 28.88s`, full
    compile `0`, Critical/Important `0/0`.
  - [x] After exact SubDub release, rebased onto main/runtime `8cf77fef...`.
    Post-rebase gate is `206 passed, 1 baseline deselected in 569.78s`; full
    compile exit `0`; production scope remains exactly two services.
  - [x] Authority-loop PR #950 deployed exact runtime `78b2815...`; post-deploy
    forensic proved both task hashes unchanged and paid Key4U scene-1 authorization
    unconsumed. CAS v2 backup SHA `77975e9d...`, mode `0600`; early/due claim proof
    preserved attempts `40`, scene 1 controlled and scene 2 primary-only.
  - [-] First worker tick exposed hydration RED before paid HTTP: telemetry count
    `1` hit the current-attempt limit and scene 2 inherited the root candidate.
    Worker stopped with provider/ShopAIKey/Key4U submit/wallet/artifact deltas `0`.
    Source RED `2 failed` -> GREEN `2 passed`; focused `49 passed`; combined
    `206 passed, 1 baseline deselected in 33.68s`; compile `0`. Direct self-review
    also proves before-submit `1` remains blocked. Ship/recover same job next.
  - [x] Rebased cleanly onto SubDub #951 main `8de058a...`; post-rebase combined
    `206 passed, 1 exact baseline deselected in 34.67s`, no overlapping file.
  - [x] Hydration correction PR #952 deployed exact runtime `4152d6bc...` through
    run `33407010553` SUCCESS. Same-job CAS restore used backup SHA `5d537728...`.
    Corrected live tick isolated scene 2 but hit `scene_provider_mismatch` for scene
    1 before paid HTTP because controlled Key4U transition still carried the primary
    ShopAIKey task identity. Worker stopped with all side-effect deltas `0`.
  - [-] Transition source RED `1 failed` -> GREEN `1 passed`; inverse mismatch guard
    `3 passed`; focused `83 passed`; combined `206 passed, 1 deselected`; compile
    `0`. PR #953 deployed exact SHA `5ebc665e...`; latest SubDub runtime
    `36c5d327...` contains it by ancestry.
  - [-] The next controlled tick transiently reported a scene-1 Key4U submit attempt
    and fallback count `1`, but later ShopAIKey reconcile erased its receipt and
    restored the old task hash. Provider usage remained `0`; evidence is still
    ambiguous, so the exact one-call authorization is treated consumed and the
    worker is stopped. No CAS/restart/paid retry is allowed under that authorization.
  - [x] Durable receipt source: failed/no-task terminal, accepted/task defer,
    production-shape and poll-survival/retry-lock comparators `4 passed`; focused
    `71 passed`; combined `210 passed, 1 baseline deselected`; compile `0`.
    Ship receipt only; persist current ambiguity consumed/no-charge after deploy.
  - [x] Rebased cleanly onto SubDub #955 main `832681d9...`; post-rebase focused
    `71 passed in 513.19s`, combined `210 passed, 1 deselected in 27.64s`, compile
    `0`, no file overlap.
  - [x] Receipt PR #956 deployed exact SHA `95c8f1fe...` via run `33429546236`
    SUCCESS. No-provider CAS stored backup SHA `a89d4d5c...`, mode `0600`, and
    terminalized the existing job as failed-no-charge with immutable ambiguity
    receipt consumed, scene counts `[1,0]`, task/finance/output deltas `0`.
  - [-] The old scene-1 authorization is consumed. Stop before any CAS/restart or
    paid call. A new exact Owner authorization is required for one replacement
    attempt; `PV2-R01` remains open and `V2-04`/`SPEC-04I` remain blocked behind it.
    `PV2-R01` stays open until real MP4/receipt/report/zero-wallet acceptance passes.
- [ ] `V2-04` Execute remaining quality coverage assignments once each.
- [ ] `V2-05` Cross-run idempotency/artifact audit and GitHub evidence closeout.

Only one checkbox may be `in progress` in the durable tracker. Finish or stop at a
terminal/pause-safe boundary before moving to another product/spec.

### V2-02 source-only subspecs

- [x] `V2-02.0` Persist Owner scope in Markdown + machine-readable JSON.
- [x] `V2-02.1` Final strategy/manual/Tail verifier: `54 passed in 8.10s`; no
  runtime source changed.
- [x] `V2-02A` Audited `videoref|start`: it uses legacy `vfinal`, not the shared
  Tail9. Reuse-first decision: do not modify Video Reference merely for quality
  coverage. Tier 300 was reassigned to the compatible Trend catalog lane; runtime
  source stayed unchanged.
- [x] `V2-02B` Source-audited every representative callback in the assignment
  JSON: each callback is the entry or declared child of its exact public route,
  route Invoice/Job reachability is true, and Tail owner/engine/tier compatibility
  matches. Strategy gate `4 passed in 6.99s`; no runtime byte changed.
  it is visible/reachable, non-manual, preserves the exact product owner, and
  reaches the shared Tail without pre-confirm side effects.
- [x] `V2-02C` Product Video Edit protected lock persisted at `d92a98d`: eight
  UI/handler function hashes plus navigation/local-free protected files. Branch
  gate `34 passed, 1 failed`; clean-main exact selector reproduced the same
  `test_local_free_delivery_keeps_charge_zero_and_cannot_claim_charge` failure in
  `640.98s`; `NEW_FAILURES=0`. No Edit source/test byte was changed.
- [x] `V2-02D` Bounded Owner live window recorded below: dedicated Owner test
  account, Product Video only, exact job/provider caps, one active heavy job at a
  time, Browser action-time confirmation, and zero wallet mutation.
- [x] `V2-02E` Locked 17 unique case/scenario IDs, fixture hashes, Add-on sets and
  source-generation prompts. Strategy verifier `8 passed in 6.89s`; calculated
  caps are 19 representative scenes + 9 quality scenes + 4 source-image tasks.
- [x] `V2-02F` Checklist, assignment JSON, script fixture and machine verifier
  committed as `2d490e3` and pushed to branch
  `docs/product-video-live-strategy-v2`. Pre-push gate `54 passed in 8.10s`;
  runtime source changed `0` files.
- [x] `V2-02G` Checklist PR #916 squash-merged as
  `79d9b345807d93edda0375b5df7a6fdbabe8758e`; deploy run `33138591557`
  completed SUCCESS.
- [x] `V2-02H` First representative runbook persisted at
  `KIEM-THU/runbooks/PV2-R01-trend-video-upload.md`; Trend upload + strategy gate
  `27 passed in 7.81s`. The runbook may not execute until `V2-02G` is complete.
- [x] `V2-02I` Shared Tail quality integrity hotfix. Live RED at
  `2026-08-28 10:14:18` proved callback `video_tail|quality|select|400` reached
  `video_uiflow3_routeengine_not_ready:uiflow3_product_duration_contract_mismatch`
  before Invoice. Scope is limited to exact tier parsing, selected-tier duration
  synchronization and current-catalog validation. Protected UI text, keyboard
  rows, callbacks, back-stack, `video_local_edit`, `videoedit|ai`,
  `multi_scene_film`, wallet and provider-submit behavior must remain unchanged.
  Acceptance: tier `400` preserves public `80 Xu`, synchronizes every scene to
  8 seconds, reaches Invoice -> Confirm -> Status, and forged/stale tier values
  fail closed before session/job/provider/wallet mutation. Source GREEN is locked:
  final post-review acceptance `130 passed`, public seam `6 passed`, full
  RouteEngine `25 passed`, compile/diff/scope exit `0`, `NEW_FAILURES=0`. PR #917
  squash-merged as `d5dc3000986601a11764866bed2fcdc0ea5b03bb`; compile run
  `33151948480` and deploy run `33151948497` completed SUCCESS; bot and Owner
  worker ran exact `d5dc300...`. Fresh job #26 selected tier `400` / public
  `80 Xu`, reached Invoice -> Confirm -> Status and delivered a real two-scene
  9:16 MP4, but its Add-on truth failed and opened `SPEC-04G.1` below.
- [x] `SPEC-04G.1` Add-on truth/report source and terminal failure-loop. Live job #26
  proved the session held a strict `product-video-addons-v1` Tail plan, while the
  generic project persistence rebuilt it from legacy profile defaults and dropped
  strict requested/materialization fields. Result: UI selected no voice/music/
  subtitle, but the worker implicitly requested defaults and returned
  `partial_addons=1`. Fix only this persistence boundary, then send one friendly
  report after the MP4 receipt is durable and settlement is known. The report must
  show product, quality, scenes/duration/ratio, video price, selected/free/paid
  Add-on counts, Add-on total, invoice total, actual Xu charged and delivered
  status; it must never show provider, worker, job/task ID, SHA, manifest, JSON,
  engine route or internal diagnostics. Duplicate completion must not resend the
  report, and report failure must not invalidate delivery or charge again.
  Source is verified: final focused acceptance `24 passed`,
  protected Tail/quality/menu/RouteEngine batch `103 passed`, strict material/
  local-artifact/UI-lock comparator `21 passed`, broad branch/base comparator
  reproduced exact `38 passed + 7 historical failures` with `NEW_FAILURES=0`,
  `py_compile bot.py` and diff/scope/secret/UI gates exit `0`. Terminal correction
  PR #921 deployed as `4fa07a01...`; live exposed an empty result-marker seam.
  F2 PR #924 deployed as `f3f79fd5...`; existing job #27 then terminalized
  `failed_no_charge` with exactly two durable failed scene tasks, no new submit,
  provider usage `0`, transactions `0`, credit events unchanged and charged Xu
  `0`. This closes the failure-loop but is not product LIVE PASS. Per Owner's
  one-job/reuse-first rule, do not create another manual provider rerun: verify
  strict Add-on materialization and the customer report on `PV2-R01`, the first
  actual representative, then freeze that product if its real artifact passes.

## 2. Rules that must not change

1. Work product-by-product. Do not open unrelated UI, provider, wallet, SubDub,
   PayOS, ENV or deployment work while one Product Video spec is active.
2. Manual/direct-input lanes are source-contract coverage only. Valid prompt or
   content must go directly to the completed shared Tail at Add-on. They are not
   representative live lanes because they skip too many product-specific nodes.
3. For every normal product, live the most complex non-manual lane once at the
   public `Nhanh gon` offer (`tier_id=400`, `80 Xu/scene`) with two real scenes.
   `Kich ban -> Video` keeps its existing product minimum of five scenes and is
   the only current scene-count exception.
4. `Video tu quay` is the only product-menu exception: it contains two different
   products and both must be lived independently:
   `self_shot_scene_change` (`selfshot2`) and
   `self_shot_cinematic_transform` (`selfshot3`).
5. Quality coverage is global, not confined to Video AI chan that. `tier_id=400`
   is already covered by every representative product run. Each remaining visible
   quality is one additional one-scene job assigned to a compatible product/route.
6. Never create a duplicate provider job merely to cover a lane or quality already
   proven by an assigned row. One run may satisfy both a product and a quality row
   only when its scene count and acceptance contract match both rows.
7. Every case uses a unique `case_id` in the prompt/content and idempotency key.
   Only an explicit replay case may reuse the full key.
8. `Video dai tap / multi_scene_film` is completely excluded from this cycle by
   Owner direction. Do not repair, test, submit, deploy for, or spend provider
   calls on it. Reopen only after every current product is complete and the Owner
   explicitly requests the long-video test.
9. `video_local_edit` is a protected completed product. Do not edit or live it in
   this cycle. Its unfinished `videoedit|ai` lane is deferred to the same future
   cycle as long video. Do not repair, route quality coverage through, submit,
   deploy for, or infer PASS for that AI-edit lane now.

## 2A. Owner scope decisions - authoritative checklist

- [x] Do not run every lane. One most-complex non-manual representative per active
  product is enough; sibling lanes inherit only after source contract comparison.
- [x] Do not use a manual/direct-input lane as the representative live lane.
- [x] Direct input remains mandatory on every applicable product and must enter the
  shared Tail directly at Add-on after valid prompt/content.
- [x] Normal representatives use public `Nhanh gon`, `80 Xu/scene`, two scenes.
- [x] `Kich ban -> Video` keeps its existing five-scene minimum for its one live.
- [x] `Video tu quay` contains two different products, so both
  `self_shot_scene_change` and `self_shot_cinematic_transform` live separately.
- [x] `Video dai tap / multi_scene_film` is fully excluded until all active products
  finish and the Owner explicitly opens a future long-video cycle.
- [x] `video_local_edit` is frozen/protected and excluded. Its unfinished AI Edit
  lane is deferred with long video; no code, test, UI, route, worker or live action.
- [x] Quality coverage is distributed across compatible products. Each remaining
  visible quality needs one one-scene artifact; it is not all assigned to AI Real.
- [x] Reuse an existing LIVE PASS blackbox/shared engine through a new product
  adapter. Never change the passed product to make the new one work.
- [x] Keep exactly one active spec pointer; stop at terminal/pause-safe before moving.
- [x] Record every RED/GREEN/PR/deploy/runtime/job/artifact/delivery/zero-wallet
  proof in this checklist and the durable tracker; never work from memory alone.

## 3. Reuse-first and protected-live rule

Once a product has terminal LIVE PASS, it becomes a protected baseline.

- Freeze its merge SHA, runtime SHA, route/engine owner, UI function hashes,
  protected test IDs, request/project/job/outbox IDs, scene records, final artifact
  SHA/bytes/probe, Telegram receipt identity and zero-wallet snapshots.
- Do not edit its route, UI, state schema, blackbox, shared engine or tests to make a
  later product pass.
- Attach a later product to a proven blackbox/shared engine using the smallest
  adapter, alias, input normalizer or material handoff.
- A later product failure must first produce a RED at that later product boundary.
  Fix only that boundary while the protected product comparators stay byte/behavior
  identical.
- Do not call a paid provider again for a protected product merely to "check again"
  when none of its locked bytes/contracts changed.
- If a shared change is truly unavoidable, stop first: run impact search, name every
  protected product, prove adapter-only is impossible, obtain Owner direction, add
  a RED for the shared defect, then run every affected protected comparator. Never
  silently weaken or rewrite a passed baseline.

Execution loop:

`READ LOCK -> REUSE KNOWN-GOOD ENGINE -> RED NEW BOUNDARY -> MINIMAL ADAPTER FIX -> GREEN -> PROTECTED COMPARATORS -> SHIP -> LIVE NEW PRODUCT -> FREEZE NEW LOCK`

## 4. Representative product matrix

All active rows use `tier_id=400` (`Nhanh gon`, `80 Xu/scene`) and two real scenes,
except `Kich ban -> Video`, which uses its locked minimum of five scenes.

| ID | Product / exact owner | Most complex non-manual lane | Why selected | Status |
|---|---|---|---|---|
| `PV2-R01` | `video_trend` / `trend_video` | Upload one public trend reference through `vtrend|video_upload`, then select content profile and full Tail | Media intake + trend source + content/profile + Add-on + renderer | IN PROGRESS - full flow/admission GREEN; one-shot job28 authority repair ship/live pending |
| `PV2-R02` | `video_ai_real` / `video_ai_canonical` | `vid3|mode|image_video` with mapped scene images, character/style/requirements and full Tail | More material gates than prompt-only/manual | PENDING |
| `PV2-R03` | `script_image_video` / `script_to_video` | Upload/parse existing script through `vproduct|script_upload`, review a five-scene plan and full Tail | File parsing + long script + scene planning; Owner approved existing 5-scene minimum | PENDING, 5 scenes |
| `PV2-R04` | `frame_video_local` / `frame_video_render` | Use `framevideo|source|ai`, create/map/order two images, movement/transition/Add-on/full Tail | Most complex Frame source path; exercises image preparation plus mapping and local FFmpeg route | PENDING |
| `PV2-R05A` | `self_shot_scene_change` / `selfshot2` | Source video -> segment -> subject -> multi-scene plan -> prompts -> Add-on/full Tail | Distinct video-to-video product: preserves subject and creates changed scenes | PENDING |
| `PV2-R05B` | `self_shot_cinematic_transform` / `selfshot3` | Source video -> segment -> subject -> preset -> staged timeline -> wardrobe/world/effects -> prompt bundle -> Add-on/full Tail | Distinct one-take transform product with different owner and engine | PENDING |
| `PV2-R06` | `storyboard_prompt` / `storyboard_to_video` | `vstory|ai`, content/profile -> generate/map two storyboard frames -> transition/Add-on/full Tail | Exercises storyboard generation, asset mapping and scene boundaries | PENDING |
| `PV2-R07` | `multi_scene_film` / `multi_scene_film` | Not run in this cycle | Owner deferred the entire long-video product until all current products are complete and explicitly requests it | EXCLUDED - no source/provider/live action |
| `PV2-R08` | `video_idea` / `video_idea_to_product` | `videoidea|explore`, category -> dynamic preset -> develop/handoff -> full Tail | Longest idea route and proves handoff into executable product owner | PENDING |
| `PV2-R09` | `video_local_edit` / `local_worker_ffmpeg` | Not run in this cycle | Completed Product Video Edit is protected; unfinished AI Edit is deferred with long video by Owner | PROTECTED / EXCLUDED - no code, test or live action |

The video downloader, prompt library, guide and planning-only helpers are not paid
Product Video products and do not create representative provider jobs.

## 5. Quality coverage assignment

The catalog is measured from `services.video_ai_real_pricing.public_quality_catalog()`.
Every assigned product below supports single-scene execution and the assigned tier.
`tier_id=400 / 80 Xu` needs no extra quality-only job because all representative
product rows already cover it.

| Quality ID | Public offer | Assigned product/lane | Scenes | Status |
|---:|---|---|---:|---|
| `400` | Nhanh gon - `80 Xu` | Covered by every representative product row | 2 | PENDING representative rows |
| `500` | Chuyen dong on dinh - `110 Xu` | `video_trend`, search/catalog sibling lane | 1 | PENDING |
| `600` | Chuyen dong co am thanh - `160 Xu` | `video_idea`, explored preset handoff | 1 | PENDING |
| `200` | Can bang ro net - `200 Xu` | `frame_video_local`, uploaded image route | 1 | PENDING |
| `300` | Tieu chuan co am thanh - `220 Xu` | `video_trend`, public catalog lane | 1 | PENDING |
| `700` | Canh dai co am thanh - `220 Xu` | `self_shot_scene_change` (`selfshot2`) | 1 | PENDING |
| `800` | Cao cap linh hoat - `370 Xu` | `self_shot_cinematic_transform` (`selfshot3`) | 1 | PENDING |
| `1000` | Dien xuat chan that - `370 Xu` | `video_ai_real`, prompt-video sibling lane | 1 | PENDING |
| `1200` | Da goc may - `1260 Xu` | `video_ai_real`, image-video lane | 1 | PENDING |
| `1500` | Dien anh nhieu canh - `2360 Xu` | `video_ai_real`, image-video lane | 1 | PENDING |

Before each quality job, assert the exact button is visible and its selected tier is
persisted through Invoice, Confirm, job payload and manifest. Distinct non-replay
cases must never share final SHA or Telegram `file_unique_id`.

## 6. Source-only manual Tail lock

No paid live job is needed for these direct-input seams. Current fresh evidence:

- `tests/test_p0_product_video_manual_tail_matrix.py`: `22 passed in 6.77s`.
- `tests/test_p0_product_video_full_menu_tail_to_status_matrix.py`:
  `24 passed in 8.36s`.
- Ten input owners preserve exact customer text, create zero provider/job/outbox/
  wallet side effect before Confirm, and enter the same Tail at Add-on.

Any regression here is fixed at the product-specific pending-text adapter. The
completed Add-on/Review/Quality/Invoice/Confirm/Status UI is protected and must not
be redesigned.

## 7. Required evidence for every live row

1. Exact case/product/lane/tier/Add-on/scenario or fixture SHA.
2. Baseline and after snapshots: project/job/outbox counts, transaction count and
   max ID, credit-event count and max ID, provider-usage count and max ID, balance
   and total spent.
3. Admission occurs before provider spend; exactly one project, job and outbox for
   the idempotency key; Invoice/job/outbox are not orphaned.
4. Poll timeline records initial, material progress and terminal state. Poll/retry
   may refresh an existing task but must never recreate provider work.
5. Independent scene records plus media evidence at scene boundaries. A two-scene
   database claim with one duplicated clip is FAIL.
6. MP4 `ftyp`/`moov`, container, streams, duration, dimensions, decode first/last
   frames, expected audio, size floor, SHA-256 and visual inspection.
7. Add-on requested/materialized/applied in persisted plan and final manifest; the
   artifact must visibly/audibly contain it.
8. Telegram delivery response and persisted receipt: message ID, file ID and
   `file_unique_id`; exactly one delivery per job; Status becomes delivered only
   after receipt persistence.
9. Owner `charged_xu=0`; transaction row-count and max-ID deltas both zero. A
   `+X/-X` pair with net zero is still FAIL.
10. Run-level audit: one job/invoice/delivery per key; distinct artifact SHA and
    Telegram file identity for all non-replay cases.

## 8. Stop conditions

- Stop at the exact failed component; do not move to the next product.
- Do not mark PASS from merge, deploy, HTTP 200, provider task ID or stream geometry
  alone.
- Do not start a second heavy provider job while the current assigned job is active.
- Do not edit a protected LIVE PASS product to repair another product.
- Do not touch Product Video Edit or its AI Edit lane in this cycle, including using
  it as a quality probe. Reopen only with the future long-video Owner instruction.
- Do not close the current Product Video work until every active assigned row is
  terminal PASS and every active source contract is resolved. The explicitly
  excluded long-video row is not touched or inferred as PASS.

## 9. Bounded Owner live window

- Destination: current signed-in Owner admin test account at `@toanaasbot` only.
- Scope: only rows assigned in `product-video-live-strategy-v2.json`.
- Final Product Video job cap: `17` (`8` representative + `9` quality-only).
- Assigned scene-render upper bound: `28` (`19` representative scenes + `9`
  quality-only scenes). Local-only routes may make the real paid-call count lower.
- Source-image provider task cap: `4`, only where the selected complex Frame AI
  source and Storyboard AI lanes require two source images.
- Total external create-call cap: `32` (`28` scene-render upper bound + `4`
  source-image tasks). Exceeding this cap requires a new Owner instruction and a
  checklist update before the next call.
- Concurrency: one heavy provider job/task at a time. A new row starts only after
  the previous row is terminal or explicitly pause-safe before provider submit.
- Telegram uploads/messages and final Confirm require the Browser's action-time
  confirmation. Never reuse an old confirmation for a materially different file,
  destination or job.
- Provider submit is permitted only after the assigned UI Confirm and admission
  gates. Unit/source tests keep provider calls at zero.
- Wallet contract: Owner `charged_xu=0`; transaction row count/max ID and credit
  event count/max ID must not change. Any `+X/-X` pair, nonzero charge, balance or
  total-spent change immediately stops the window.
- No PayOS, top-up, ENV/key, destructive DB, SubDub, Video Edit, AI Edit or Long
  Video action is included.
- The Owner can revoke or narrow this window at any time; newer direct instruction
  is written here before the next external action.
