# P0 Product Video Full-Lane Live Matrix

> **AUTHORITATIVE SCOPE OVERRIDE (28/08/2026):** Current execution follows
> `KIEM-THU/PRODUCT-VIDEO-LIVE-STRATEGY-V2.md`. The older exhaustive lane/tier
> tables below are retained as history and prior evidence only. Do not create jobs
> from them. V2 uses one complex non-manual representative per product at tier 400
> (80 Xu/scene, two scenes), lives both distinct Self-shot products, and distributes
> the remaining single-scene quality probes across compatible products.

## Scope Stamp

- Product: **Product Video** only
- Codex task: `019efe1e-ee54-78e1-87c4-10db6e1e19e4`
- Repository: `manhtoangreensky-wq/bot`
- Branch: `fix/product-video-live25-final-coverage`
- Current deployed Product Video base: `f16d74a1b23188625810113ceb24ee2028d857c9`
- Local branch must rebase onto shared `origin/main` after SubDub releases Git/VPS ownership.
- SubDub task `019fbbfe-59b7-7ee2-b298-dea276813ce4` is **out of scope**. CPU is independent; only Telegram/Chrome/provider/VPS/deploy ownership is coordinated.

## Execution Rule

For every spec, use this exact loop and do not skip or reorder it:

`READ -> CONTRACT -> RED -> MINIMAL FIX -> GREEN -> REVIEW -> EVIDENCE`

After all source specs are GREEN:

`ONE BRANCH -> PUSH -> ONE PR -> SQUASH MERGE -> DEPLOY -> RUNTIME VERIFY -> LIVE MATRIX`

If a live row fails, reopen only that spec, add a RED reproducer from the real failure, apply the smallest fix, rerun GREEN, ship, and repeat that same live row. Never mark a row complete from intent, HTTP 200, a queued state, or a provider task id.

Before building any product-specific flow, compare it with the completed Product Video lanes and reuse compatible Tail screens, state contracts, Add-on materialization, quality/invoice/confirm/status edges, artifact validators and delivery/receipt logic. Add only the missing product adapter, alias or material boundary; never rebuild a completed shared flow from the beginning.

## Resource Boundary

- [x] Source READ and contract work allowed.
- [x] Local Python/FFmpeg available to Product Video.
- [x] LIVE/CHROME available to Product Video for the current PV-L01 failure loop.
- [x] VPS/DEPLOY available to Product Video for the current PV-L01 failure loop.
- [x] Owner approved only the Key4U `.vn` endpoint configuration needed for Product Video; no secret values are committed.
- [x] No wallet, PayOS, destructive DB, onboarding, PWA, or SubDub changes allowed.

Shared-resource ownership is determined only by the latest exact inter-task
LIVE/CHROME/VPS markers. This history file does not claim a current owner.

## Ordered Specs

### SPEC-01: Manual/Text Lane -> Shared Tail

- [x] Audit current routes from public buttons through pending text handlers.
- [x] Prove current behavior contradicts the Owner contract.
- [x] RED: exact customer text is preserved for every supported manual lane.
- [x] RED: a deterministic two-scene plan exists with zero provider calls.
- [x] RED: next visible screen is `addon`, not Profile/Content Lock/Production Bible/suggestions.
- [x] RED: Tail order is `addon -> review -> quality -> invoice -> confirm -> status`.
- [x] Quality Back returns to Review for every manual lane, including `multi_scene_film`.
- [x] Invoice opens the distinct Confirm screen; only Confirm may submit.
- [x] RED: back targets stay inside the same product and state.
- [x] Minimal production fix.
- [x] Focused GREEN evidence.

Current source evidence:

| Product lane | Current target after manual text | Contract result |
|---|---|---|
| Video theo trend / `trend_manual_input` | `start_public_video_scene2_step` | FAIL |
| Video AI chan that / UIFLOW3 `manual_content` | `content_lock -> production_bible` | FAIL |
| Video AI chan that / `awaiting_prompt_text` | `start_public_video_scene2_step` | FAIL |
| Kich ban -> Video / canonical `awaiting_existing_script` | script proposal/planner | FAIL |
| Kich ban -> Video / `script_manual_topic` | `start_public_video_scene2_step` | FAIL |
| Storyboard / `storyboard_manual_input` | `start_public_video_scene2_step` | FAIL |
| Video dai tap / `film_manual_topic` | `start_public_video_scene2_step` | FAIL |
| Ghep anh thanh video / custom topic | generated suggestions | FAIL |
| Video tu quay / custom direction | generated suggestions | FAIL |
| Y tuong video / manual topic | generated suggestions | FAIL |

### SPEC-02: Quality Selector Matrix

- [x] Every visible quality button has a registered callback.
- [x] Selecting a tier preserves the exact tier in review, invoice and confirmation; live admission/job/manifest evidence remains required below.
- [x] Unsupported or forged tier blocks before admission with no provider call and no charge.
- [x] Focused GREEN evidence for every tier id.

Video AI Real public tiers:

| Tier | Locked two-scene scenario | Selector GREEN | Two-scene LIVE | Artifact/Receipt Evidence |
|---:|---|:---:|:---:|---|
| 200 | PV-Q200: gấp diều giấy -> thả diều trên đê | [x] | [ ] | source GREEN; live pending |
| 300 | PV-Q300: xếp bộ trà gốm -> rót trà cạnh cửa sổ | [x] | [ ] | source GREEN; live pending |
| 400 | PV-Q400: sửa phanh xe đạp -> chạy thử trong công viên | [x] | [ ] | source GREEN; live pending |
| 500 | PV-Q500: nhuộm khăn lụa -> người mẫu choàng khăn | [x] | [ ] | source GREEN; live pending |
| 600 | PV-Q600: lắp đèn mặt trời -> đèn sáng sân vườn | [x] | [ ] | source GREEN; live pending |
| 700 | PV-Q700: chăm vườn kính -> thu hoạch quả đỏ trên sao Hỏa | [x] | [ ] | source GREEN; live pending |
| 800 | PV-Q800: pha nước hoa -> hero shot chai trên đá đen | [x] | [ ] | source GREEN; live pending |
| 1000 | PV-Q1000: vũ công khởi động -> xoay người trên sân khấu | [x] | [ ] | source GREEN; live pending |
| 1200 | PV-Q1200: máy pha cà phê góc rộng -> macro espresso | [x] | [ ] | source GREEN; live pending |
| 1500 | PV-Q1500: ga tàu mưa đêm -> gặp nhau dưới đồng hồ lớn | [x] | [ ] | source GREEN; live pending |

### SPEC-03: Source Regression Gate

- [x] Frame/Storyboard live renderers use real line breaks and never expose literal backslash-n.
- [x] Focused Product Video lane/Tail tests pass.
- [x] Quality matrix tests pass.
- [x] Add-on Tail-to-worker materialization and missing-material fail-closed gate passes.
- [x] Back-stack, duplicate confirm, read-only refresh, newline status and audio/final mux source regressions pass; real artifact evidence remains live-only.
- [x] `python -m py_compile bot.py` passes.
- [x] Touched runtime modules compile.
- [x] `git diff --check` passes.
- [x] Diff contains no secret, wallet, PayOS, provider-submit, SubDub or unrelated runtime changes.

### SPEC-04: One PR, Merge, Deploy, Runtime

- [x] Measured report updated in this tracker.
- [ ] One scoped Product Video commit series pushed on this branch.
- [ ] One Product Video PR created and linked to this tracker.
- [ ] PR checks terminal GREEN.
- [ ] Squash merge SHA recorded.
- [ ] Deploy terminal result recorded.
- [ ] Bot and Product Video worker run the exact merge SHA.
- [ ] Worker generation heartbeat is accepted with no reject reason.
- [ ] Bot `getMe`/ONLINE and services active evidence recorded.

### SPEC-04B: Provider Price/Domain/Quota Recovery for PV-L01

- [x] Read ShopAIKey live balance and both existing scene task payloads without submit.
- [x] Prove 59.29 USD remains; failure is VEO `429 RESOURCE_EXHAUSTED`, not zero balance.
- [x] Read live provider prices from ShopAIKey `/pricing` and Key4U `/api/pricing_v3`.
- [x] Persist one current price/route JSON plus a human-readable map and the D-drive knowledge copy.
- [x] Correct Kling v3 unit from per-scene to per-second and record two-scene costs/margins.
- [x] RED/GREEN Key4U `.vn` domain plus VEO/Kling/Hailuo family payload/poll contracts.
- [x] RED/GREEN preserve ShopAIKey quota blocker and exact-price controlled fallback policy.
- [x] Focused/protected tests and compile/diff gates terminal.
- [x] PR #905 merged as `21022ed724aa605f1b90dbb35e140a8dbba9e09b`; deploy run `33051106470` SUCCESS; bot and owner worker verified at the same SHA.
- [ ] Same PV-L01 flow delivers the required two-scene MP4 with audio/add-ons/receipt.

### SPEC-04C: Reused Final Manifest Delivery Recovery for PV-L01

- [x] Live request `VID-20260827-2803A3`, project `29`, job `25`, outbox `24` created exactly once.
- [x] Both ShopAIKey scene tasks reached authoritative `SUCCESS 100%` and produced two distinct scene clips.
- [x] Canonical concat produced a real 16-second H.264/AAC MP4 with the requested subtitle/transition plan.
- [x] RED: a canonical final reused from manifest was incorrectly downgraded because `concat_attempted=false` prevents duplicate concat.
- [x] Minimal ledger fix accepts `final_reused_from_manifest` only when full scene coverage, valid concat output and explicit final validity are also present.
- [x] Focused GREEN and protected scene-ledger/recovery comparators pass.
- [x] PR #910 merged as `82ffb117e6c2e84bd76a3aee6e5e747465958c66`; deploy run `33078757523` SUCCESS; bot and worker exact SHA.
- [x] Job `25` resumed to one Telegram delivery message `27576` with `charged_xu=0`, transaction delta `0`.
- [ ] PV-L01 remains FAIL: delivered artifact letterboxed the landscape scene inside 9:16 and degraded the requested subtitle.

### SPEC-04D: Weekly Four-Source Trend Catalog

- [x] Owner approved exact design with `DUYỆT KHO TREND 4 NGUỒN`.
- [x] RED: source registry and normalization cover `media`, `facebook`, `youtube`, `tiktok` with attributable public metadata.
- [x] UI LOCK: no new source-filter button/callback and no text/layout/back-stack change; existing `Xem 5 trend media` screen remains the only public catalog UI.
- [x] RED: refresh is idempotent, due every 7 days, preserves old cache on per-source failure and never calls a paid provider or wallet.
- [x] Minimal backend source/status implementation; `source_group` is encoded in existing keywords, so no DB migration is required.
- [x] Focused GREEN `4 passed`; protected Trend2/Trend3 flow batch `67 passed` before final UI-lock adjustment.
- [x] PR #913 merged as `ccf9523613418dfd37535f14901173624d5cbc3e`; deploy run `33105339710` SUCCESS; bot and owner worker exact SHA; generation `91016743...` accepted/persisted with empty reject reason.
- [x] First real VPS refresh: `paid_provider_calls=0`, next run `+7 days`; media `4`, YouTube `100`, TikTok `99`, but Facebook `0` because the site-only query returned an empty feed.
- [x] SPEC-04D.1 live RED: exact Facebook query contract `1 failed in 8.42s`; bounded public diagnostic proved `Facebook Reels Vietnam` returns `57` attributable items.
- [x] Minimal one-line Facebook `feed_url` correction; Trend4 + protected Trend2/Trend3 GREEN `37 passed in 9.95s`; module compile exit `0`.
- [ ] Ship/deploy SPEC-04D.1 and rerun one real VPS refresh proving all four source groups non-zero, next run `+7 days`, `paid_provider_calls=0`, transaction/provider-usage deltas `0`.

### SPEC-04E: PV-L01 Vertical Fill and Strict Add-on Recovery

- [x] Owner screenshot proves a landscape scene was scaled down and padded black inside a 9:16 canvas.
- [x] RED `2 failed, 1 passed`: Product Video had no `cover` mode; shared non-Product default was already locked to `contain`.
- [x] Minimal Product Video-only `scale=increase + center crop`; composition signature includes fit mode so the letterboxed manifest cannot be reused.
- [x] GREEN `3 passed`; shared default still uses `scale=decrease + pad` for protected non-Product lanes.
- [x] Job `25` forensic: UI/project requested subtitle and SRT existed, but persisted manifest had `subtitle_path=null`, `addon_application.requested=[]`.
- [x] RED `1 failed`: scene3/manual Tail persisted legacy flat Add-on data without `contract_version`.
- [x] Minimal handoff fix compiles `product-video-addons-v1` for every Product Video Tail owner; uiflow3's richer canonical handoff remains authoritative.
- [ ] Post-rebase protected gate, ship/deploy and same-case live rerun proving full-frame 9:16 + subtitle applied.

### SPEC-04F: Video UI Lock and Tail-to-Status Matrix

- [x] Owner rule locked: do not change completed Video UI text, keyboard rows, callbacks or back-stack; only repair content/contract/runtime behavior.
- [x] RED ACK timeout: `11 failed in 5.03s`; all 10 quality callbacks and Confirm stopped before their next screen.
- [x] Minimal Tail callback ACK best-effort; no text/keyboard function changed.
- [x] GREEN `11 passed in 4.51s`: all 10 tiers open Invoice and Confirm opens Confirmation under Telegram ACK timeout.
- [x] Final Submit runtime-not-ready path persists attempt and renders Status: `1 passed in 0.76s`.
- [x] Full menu RED: PV-L08 `video_idea_to_product` had no adapter owner (`1 failed, 9 passed`).
- [x] One alias fix; full nine-lane Invoice/Confirm/Status contract GREEN `10 passed in 0.68s`.
- [x] UI byte-lock: 14/14 completed Menu/Add-on/Review/Quality/Invoice/Confirm/Status function blocks match `origin/main` byte-for-byte.
- [x] Final source focused acceptance `45 passed in 5.88s`; dependency-complete quality/manual files `39 passed in 8.85s`.
- [x] Protected old Tail suite branch `41 passed, 15 failed in 9.04s`; clean `origin/main` reproduces exact same 15 IDs with `41 passed, 15 failed in 9.02s`; `NEW_FAILURES=0`.
- [x] Trend/scene ledger protected `52 passed in 5.56s`; full Product Video output contract `24 passed in 12.54s`.
- [x] `py_compile` five touched runtime files exit 0.
- [ ] Post-SubDub rebase gate and live traversal for every acceptance row.

### SPEC-04G: Shared Tail Quality-State Integrity

- [-] Active pointer: repair the Tail -> UIFLOW3 quality boundary before any new
  representative or quality provider job.
- [x] Live RED: callback `video_tail|quality|select|400` failed before Invoice with
  `uiflow3_product_duration_contract_mismatch`; the button still carried exact
  internal tier `400` / public `80 Xu` and was not mapped to tier `1500`.
- [x] UI lock: no completed Tail text, keyboard, callback label, row layout or
  back-stack function may change.
- [x] Security RED: a non-catalog tier must not be clamped into tier `1500`, replace
  a session, create a job/outbox, call a provider or mutate wallet state.
- [x] Cross-product RED: canonical `storyboard_prompt` Tail reached the route-engine
  alias table as unsupported because only the retired `video_storyboard` spelling
  was registered; add only the canonical alias and keep the existing spelling.
- [x] Minimal source patch: parse exact tier, validate it against the current
  product catalog, synchronize `seconds_per_scene`, total duration and every scene
  duration before compiling the immutable route-engine handoff, and persist the
  synchronized host/Tail scope.
- [x] Focused GREEN for tier `400`, cross-product duration mapping and forged tier.
- [x] Protected quality/Tail matrix, UI byte locks, duration fail-closed comparator,
  compile/diff/secret/scope gates.
- [x] One PR, squash merge, deploy and bot/owner-worker exact runtime SHA: PR #917
  merged as `d5dc3000986601a11764866bed2fcdc0ea5b03bb`; compile run
  `33151948480` SUCCESS; deploy run `33151948497` SUCCESS; bot and Owner worker
  both ran exact `d5dc300...` with generation `19022d4550bd4a6180cc21025ed67789`.
- [x] Same live screen: clicked `Nhanh gon - 80 Xu` once and proved
  Invoice -> Confirm -> Status with tier `400`, 8 seconds/scene and no `2360` jump.
- [x] Audit every active product Tail through the same six-stage sequence before
  resuming representative provider jobs.

Current source evidence:

- Execution snapshot / forged-tier GREEN: `11 passed in 6.70s`.
- UI lock + nine product Tail + route-security focused GREEN:
  `40 passed in 8.04s`.
- Full UIFLOW3 RouteEngine GREEN: `25 passed in 9.10s`.
- Ten-tier quality matrix GREEN: `17 passed in 6.35s`.
- Full public Tail/session seam GREEN: `6 passed in 8.35s`.
- Scene3/session selected-duration + strict Add-on comparator:
  `2 passed in 7.55s`.
- Final consolidated execution/quality/UI/route gate:
  `78 passed in 746.49s`.
- Broad artifact/Add-on review RED: `23 passed, 1 failed in 645.64s` exposed
  execution-snapshot synchronization running before canonical revision comparison.
  Minimal review fix keeps rebuild invalidation on the planning snapshot and moves
  selected-quality execution snapshot work back behind handoff/guard only.
- Focused resume/invoice + Add-on correction rerun: `3 passed in 706.30s`.
- Final post-review acceptance across execution snapshot, all 10 qualities, nine
  Tail products, UI byte locks, RouteEngine, manual Tail, Add-on/artifact and
  public session seam: `130 passed in 22.07s`.
- Legacy Tail comparator on branch after harness dependency correction:
  `44 passed, 10 failed in 14.95s`.
- Exact clean base `79d9b345807d93edda0375b5df7a6fdbabe8758e` reproduced the
  same ten historical UI/tier assertion IDs with `44 passed, 10 failed in
  714.64s`; `NEW_FAILURES=0`. No historical UI assertion was changed.
- Final `py_compile bot.py services/video_uiflow3_routeengine.py` exit `0`;
  `git diff --check` exit `0`; forbidden-path hits `0`; secret-value hits `0`.

### SPEC-04G.1: Strict Add-on Truth and Customer Delivery Report

- [-] Active pointer: fix the exact Add-on persistence boundary exposed by fresh
  job #26, then add one idempotent customer report after durable delivery and
  settlement. Do not change completed Tail UI text, keyboards, callbacks, layout,
  back-stack or quality flow.
- [x] Fresh live route: manual `video_ai_real` input went directly to Add-on ->
  Review -> Quality -> Invoice -> Confirm -> Status as required.
- [x] Fresh live artifact: job #26 delivered `/opt/toanaas/bot/files/worker_results/
  worker_job_26_final_output.mp4`, `3,943,967` bytes, SHA-256
  `e554198469c3e2ed37cae2c78fe7d4d0ba968f24f983fbf03ff53cb2c6b062f7`,
  H.264 `540x960` SAR 1:1 + AAC stereo 48 kHz, duration `16.000s`, no black
  interval; Telegram delivery message `27652`; Owner charged `0 Xu`, transaction
  delta `0`.
- [x] Live RED: invoice `pv:manual-7126457028-27648:1:400` was `144 Xu` for two
  scenes at tier `400`; Tail UI said voice/music/subtitle `Khong them`, but durable
  result reported `partial_addons=1`, implicit default music, unavailable voice and
  missing subtitle.
- [x] Root cause traced: `video_tail9_apply_to_session()` persisted strict
  `product-video-addons-v1`; `video_b14_prepare_project_for_invoice()` then called
  legacy `video_b14_addon_plan_from_session()`, which retained only legacy default
  keys and discarded strict `requested_addons`, component payloads, transition and
  materialization requirements.
- [x] RED/GREEN: strict Tail contract survives session -> project byte-for-byte; no
  implicit voice/music/subtitle or partial Add-on result when Tail leaves them off.
- [x] RED/GREEN: customer report contains every required business field, excludes all
  internal technical terms, sends only after receipt/settlement and sends once on
  duplicate completion.
- [x] Minimal GREEN: a narrow worker-persistence helper preserves strict contracts
  unchanged and falls back to the existing legacy plan for legacy sessions.
- [x] Minimal GREEN: pure report data/text helpers plus best-effort send/persist;
  report failure never reverses delivery and never repeats settlement.
- [x] Protected Tail/UI/RouteEngine/delivery gates, compile, diff, scope and
  baseline comparison with `NEW_FAILURES=0`.
- [ ] Rebase after SubDub releases shared Git, then one PR/squash/deploy/runtime
  exact-SHA verification.
- [x] Exact live rerun path, case ID, Add-on contract, artifact gate, customer
  report text and duplicate-completion gate persisted at
  `KIEM-THU/runbooks/PV2-SPEC04G1-addon-report-rerun.md`.
- [ ] Same-fixture live rerun: strict Add-on plan, `partial_addons=0`, valid MP4,
  one friendly report after MP4, `charged_xu=0`, transaction delta `0`.
- [ ] Only after that live PASS, lock artifact/report/test evidence and continue
  checklist order at `V2-03`; job #26 alone is not representative-product PASS.

Live failure-loop job #27 on runtime `89192bab94c871214476a9c1feb7b3d2f94dcc7a`:

- [x] PR #920 squash-merged as `89192bab...`; deploy run `33185502717` SUCCESS
  in `4m6s`; bot and owner worker run exact SHA. Worker generation
  `94a97d28abab4efb8b3cfcd76b28c263`, request/auth/persist yes/yes/yes, reject
  empty, ShopAIKey + Key4U capability ready.
- [x] Exact action-time confirm; one request `VID-20260828-F71C71`, project `31`,
  job `27`, outbox `26`, scenes `126/127`, no duplicate. Invoice
  `pv:manual-7126457028-27689:1:400`: tier `400`, 2 scenes, 16 seconds, 9:16,
  `160 - 16 + 0 = 144 Xu`, Owner no-charge.
- [x] Direct input went straight to Add-on. Persisted strict contract is
  `product-video-addons-v1`, requested exactly `[transitions]`; music/dubbing/
  subtitle `0`, silent drop `0`.
- [x] Upstream terminal RED: both existing ShopAIKey tasks returned FAILURE with
  Veo Fast concurrency capacity `0`; worker emitted
  `all_scene_providers_exhausted_no_charge`, but stale diagnostics kept the job
  queued/processing at 55% with `continue_polling=1` for more than 5 minutes.
  No new task/provider/charge was created.
- [x] Terminal-decision RED `1 failed in 26.21s`; minimal worker-only GREEN
  `1 passed in 8.08s`. Only orchestrator terminal no-charge reasons may override
  stale polling; provider route/order/tasks and wallet stay unchanged.
- [x] Owner-requested percent tree added presentation-only below the existing
  progress percentage by reusing `subdub_progress_bar`; 5 engine-route SHA-256
  locks unchanged. Focused terminal/progress/route gate `3 passed in 890.94s`.
- [x] Broad branch comparator `14 passed, 24 failed`; clean pre-patch HEAD
  reproduced exact `14 passed, 24 failed` with the same IDs, so
  `NEW_FAILURES=0`. Progress tree remains; it would be removed if route hashes or
  a new regression changed.
- [x] Terminal/progress correction shipped in PR #921, squash SHA `4fa07a01...`;
  compile run `33198389817` SUCCESS and deploy run `33198542741` SUCCESS in
  `12m8s`. Bot + owner worker read back exact SHA; generation
  `0ad4cac82ec54d2c9d45fa84379dcf09` accepted with empty reject reason.
- [x] Post-deploy live readback exposed a second exact RED: job #27 stayed
  queued at `60%`, attempts `906 -> 950`, while both durable ShopAIKey task IDs
  stayed unchanged, `provider_submit_called=0`, charged Xu `0`, provider usage
  rows `0`, transaction rows `0`, credit-event rows unchanged at `10`.
- [x] Root cause measured from the durable scene ledger: both scenes are
  authoritative `FAILURE`, fallback count `0`, forensic terminal reason
  `all_scene_providers_exhausted_no_charge`; however an empty
  `provider_result_url_present=true` marker created false
  `unprocessed_result_indexes=[1,2]` and suppressed terminal state.
- [x] F2 RED reproduced the false result marker (`1 failed in 13.96s`);
  minimal ledger GREEN ignores presence-only markers on failed scenes while
  retaining concrete/validated results. Exact selector `1 passed in 14.92s`;
  all 7 direct-impact modules `85 passed in 26.69s`.
- [x] F2 shipped in PR #924, squash SHA `f3f79fd50d4b2ad7ce345c7edc5c463ebaea44b5`;
  deploy run `33206104844` SUCCESS in `10m23s`. Bot and owner worker both read
  back exact SHA before the bounded worker start.
- [x] Existing job #27 terminalized after exactly one more claim (`950 -> 951`):
  DB status `failed`, durable `terminal_state/final_decision=failed_no_charge`,
  `continue_polling=0`, unprocessed result indexes empty, active jobs `0`.
  Authoritative scene/task maps retained exactly two original tasks, one per
  scene; both scenes are `failed/exhausted` with no URL, clip or fallback.
- [x] Final ledger proof: provider-usage rows `0`, transaction rows `0`,
  credit-event rows unchanged at `10`, `provider_submit_called=0`, charged Xu
  `0`. Owner worker was stopped after terminal and read back `inactive`.
- [x] Job #27 is a terminal failure-loop proof, not a representative product
  PASS. To avoid a duplicate manual paid job, strict Add-on/report live
  acceptance moves into the first real representative `PV2-R01`; do not rerun
  the completed failure-loop or edit any frozen route.

PV2-R01 live failure-loop on runtime `02c1c4aa0533788816d740245ba9812bf4f63ea0`:

- [x] Baseline projects/jobs/outbox `31/27/26`; transactions/credit-events/
  provider-usage `0/10/0`; Owner credits/total-spent `200/0`; active jobs `0`.
- [x] Exact fixture SHA `784FBE5B...E2732`, `32,391,742` bytes uploaded once.
  Local analysis: `79.4667s`, `1280x720`, source audio yes, 3 scene-change beats.
- [x] Long non-manual lane reached Social creator profile, entity + creative +
  requirements, two version-2 approved prompts carrying `PV2-R01`, Add-on source
  subtitle + transition `1/1`, total Add-on `0 Xu`, then Review.
- [x] Live RED before Quality: Review showed `Tư liệu nguồn: 0 tệp`; entity UI
  still showed assigned source `1`, proving upload bytes/hash were retained but
  omitted at Trend entity-to-Scene3/Tail handoff. Project/job/outbox/provider/
  wallet deltas remained zero.
- [x] TDD RED `2 failed in 8.15s`; minimal Trend-only GREEN copies the uploaded
  source into Scene3 reference assets and refreshes embedded Tail source IDs.
  Exact `2 passed in 707.43s`; protected Trend/Strategy `61 passed in 16.37s`;
  compile and diff-check exit `0`. Shared Tail/engine/provider/worker unchanged.
- [x] PR #926 merged `3b585527...`; deploy `33213099898` SUCCESS `5m26s`;
  Review live changed to source files `1`. Worker generation
  `30a883a4823948d7807bf982e064501e` accepted, reject empty.
- [x] Tier `400` Invoice remained exact: 2 scenes, 16s, 9:16, `80 Xu/scene`,
  subtitle `0`, Add-on total `0`, invoice total `144`, Owner no-charge.
- [x] Final Confirm RED before admission: `trend_source_or_sample_missing`;
  project/job/outbox counts remained `31/27/26`, active jobs `0`, provider and
  wallet deltas `0`. Flow7 accepted the uploaded source but Flow6 did not.
- [x] Flow6 parity RED `1 failed in 9.29s`; minimal Trend-only GREEN
  `1 passed in 12.30s`. Protected branch `96 passed + 2` failures; clean main
  reproduced the same two Script-only failures in `593.52s`, `NEW_FAILURES=0`.
- [x] Owner restored the complete historical content flow for all four current
  Trend lanes: catalog/media, manual Trend, public search and uploaded Trend
  video. All must converge on `scene_count -> aspect_ratio -> content_source ->
  profile/preset -> suggestion/content -> preview -> character/reference ->
  style -> requirements/context -> scene plan -> prompts -> shared Tail`.
- [x] History comparison found the existing dormant implementation from
  `6a92f47`; no new wizard was built. RED was exactly `4 failed, 1 passed in
  6.63s`. Minimal restoration removed only the stale redirect/reset seams and
  added the three missing Flow7 sequence steps. Exact GREEN is `5 passed in
  574.87s`; updated historical-contract selectors are `5 passed in 9.64s`.
  Three real state-transition tests then call the ratio/manual handlers directly;
  the complete restore file is `8 passed in 7.36s`.
- [x] Complete branch Trend gate: `124 passed, 2 failed in 21.49s`; exact
  seven-file comparison is branch `119 passed, 2 failed in 17.42s` versus clean
  `3b585527...` `117 passed, 3 failed in 18.18s`. Both remaining failures are
  the same Script-only IDs; the clean fixture-hash failure is absent on branch,
  therefore `NEW_FAILURES=0`.
- [x] Protected completed UI/Tail/quality/state gate `59 passed in 8.57s`;
  changed runtime/tests compile exit `0`; state YAML `STATE_OK`; diff-check exit
  `0`. No shared Tail UI, engine, provider, worker or wallet production file was
  changed.
- [x] Rebased without conflict onto SubDub runtime/main
  `da817b656da10b405a2878664a690d3a66d2b313`; exact remaining Product Video
  chain is two commits. Post-rebase Trend + protected gate is `186 passed, 2`
  exact Script-only baseline failures in `670.77s`; runtime/test compile exit `0`.
- [x] PR #928 merged exact SHA
  `fe25cc056df59af3c7f063f0ea5f3866ff160130`; deploy run `33237168072`
  SUCCESS. Bot and owner Product Video worker both read back exact SHA; worker
  generation `35eb01aad2c84da7acc0e60bdf98b826` is authenticated/persisted,
  reject reason empty, PID `553332`, service active.
- [x] Fresh live baseline: projects/jobs/outbox `31/27/26`; transactions `0`;
  credit events `10`; provider usage `0`; active video jobs `0`; Owner wallet
  `200 Xu`, total spent `0`. Fixture still exactly `32,391,742` bytes, SHA
  `784FBE5B...E2732`.
- [x] Owner action-time confirmation received exactly:
  `XÁC NHẬN GỬI PV2-R01 SHA 784FBE5B VÀ CHẠY TREND LIVE`. It authorizes one
  fresh upload of the measured fixture to `@toanaasbot` and one final Confirm;
  it does not authorize duplicate upload/job retries.
- [x] Exact SubDub releases received; fresh upload sent once as Telegram File.
  Live intake RED before admission: journal
  `video_trend_probe_failed | exception=InvalidToken`; bot returned the safe
  invalid-request panel. Projects/jobs/outbox stayed `31/27/26`, provider usage
  and transactions stayed `0`, credit events `10`, active jobs `0`, wallet
  `200/0`.
- [x] Root cause: bounded Trend probe directly used Telegram
  `get_file/download_to_drive`, while stable Video lanes already use
  `download_video_editor_asset_bytes`, which supports the Local Bot API path and
  avoids decrypting the incompatible file token.
- [x] TDD exact `1 failed in 1553.92s` -> `1 passed in 1148.40s`. Protected
  effective `9 passed`; one broad AST harness failure reproduced identically on
  clean `fe25cc0` in `2107.51s`, so `NEW_FAILURES=0`. Compile and diff/scope/
  secret gates exit `0`.
- [x] Intake correction shipped in PR #930, squash SHA
  `42cbf929b8f89b9154e7f343079ac6655c2ef512`; deploy run `33252027086`
  SUCCESS in `10m22s`. Bot and Owner worker read back the same SHA; generation
  `aae18624871f4008bdd46dc7e23437a3` authenticated/persisted with empty reject.
- [x] The single bounded same-fixture retry completed the restored long path:
  upload analysis -> 2 scenes -> 9:16 -> content source -> Social creator Trend ->
  suggestion/Preview -> entity/style/requirements/scene plan/prompts -> Add-on ->
  Review -> tier `400` -> Invoice `144 Xu` -> one final Confirm -> Status. Exactly
  request `VID-20260829-D78AA3`, project `32`, job `28`, outbox `27` were admitted;
  no duplicate project/job/outbox and charged Xu remained `0`.
- [x] Read-only production forensic proved job #28 contains two distinct accepted,
  pollable ShopAIKey `veo3.1-fast` tasks, one for each scene. Both scene rows are
  authoritative `IN_PROGRESS` from `shopaikey.data.status`; both durable task-to-
  scene maps cover indexes `1/2`. Root task count incorrectly collapsed to `1`
  and root authority was empty. After `5` claims against `max_attempts=3`, stale
  `failed_no_charge` won and outbox `27` became `terminal_failed` with reason
  `provider_in_progress`. Scene rows `130/131` have no artifact yet; wallet stays
  `200/0`, transactions `0`, credit events `10`, charged Xu `0`.
- [x] Exact production-shape RED `1 failed, 2 passed in 23.22s`; exact cancellation
  guard RED `1 failed in 19.40s`. Minimal GREEN recognizes only task-bearing scene rows
  with authoritative running status while the root still requests provider polling;
  explicit exhaustion RED `1 failed in 11.06s` and GREEN now remain terminal.
  Focused final plus recovery isolation `7 passed in 12.03s`; protected
  `68 passed, 5 exact baseline deselected in 19.21s`.
- [x] Claim-scan preflight RED proved explicit exhausted job #27 was recoverable
  (`1 failed, 1 passed in 10.63s`). Shared terminal-reason guard GREEN keeps job
  #28 recoverable but blocks job #27; four existing restart/CAS/cooldown/terminal
  selectors pass in `20.18s`.
- [x] Baseline classification: protected branch `68 passed + 5 failed in 19.08s` versus clean
  `42cbf929` `61 passed + the same 5 failed in 1442.84s`; broad impact branch
  `196 passed + 34 failed in 42.55s` versus clean `189 passed + the same 34 failed`.
  `NEW_FAILURES=0`. `bot.py`, worker/queue/test/local-worker compile exit `0`.
- [x] Rebased one local commit cleanly again onto exact latest SubDub main
  `50c16cfed8ee150e8259c32687eda4b313f163e9`; post-rebase HEAD
  before evidence amend was `2b3824a9c0b54d05fe3e49e950976530847094e6`,
  `0 behind / 1 ahead`. Final commit SHA is read from Git after amend, not stored
  inside the commit itself.
  Focused/recovery `11 passed in 17.20s`; protected effective
  `68 passed, 5 exact baseline deselected in 14.52s`; docs `9 passed in 14.12s`;
  full bot/worker/queue/test compile, YAML, diff and secret gates exit `0`.
- [x] Branch `2f997326...` shipped once as PR #934; squash merge
  `ef81f6a03f5384f6dbc02ebd6f9bf96edfbc6618`; deploy run `33290296142`
  SUCCESS in `15m15s`. VPS bot/web/nginx are active at that SHA. Owner worker was
  fast-forwarded without touching untracked runtime data; generation
  `4ab7fd93482744a2bc06b81178ebb155`, PID `695925`, heartbeat authenticated and
  persisted, reject empty.
- [x] Worker-claim live RED after the authority fix: job #28 stayed
  `failed_no_charge` although both scene maps and both authoritative `IN_PROGRESS`
  tasks were valid. The production classifier measured the sole blocker as historical
  `existing_task_recovery_count=3/max=3`; those three recoveries were consumed before
  the scene-authority correction. Provider task hashes and wallet remained unchanged.
- [x] One-shot authority-repair source RED `1 failed in 8.41s`; minimal GREEN
  `1 passed in 5.74s`; focused `15 passed`; restart/claim `56 passed`; protected
  polling/CAS/multiscene/delivery/fallback `242 passed, 1 dependency warning in
  48.09s`; final strategy-inclusive gate `251 passed, 1 dependency warning in
  47.40s`; compile and diff-check exit `0`. Ordinary recovery stays capped at `3`;
  the repair marker is durable and permits no second authority repair, submit, resubmit or
  fallback.
- [x] Authority repair shipped as PR #935, squash SHA
  `06f38df793beabd14e3446dadd473d4e8737a0e6`; deploy run `33293196471`
  SUCCESS in `11m25s`. Bot/web/nginx and Owner worker read back that SHA; worker
  generation `b264fd4f04994a3288f686ae09a51413`, PID `703262`, heartbeat
  authenticated/persisted with empty reject.
- [x] Post-claim live RED: the durable authority repair executed once at
  `11:59:17`, stored recovery count `4` and kept submit/resubmit/fallback/charge `0`.
  One second later `product_video_terminal_no_charge_reason()` read stale root
  `continue_polling=false` before consulting `provider_task_alive=true`, so it
  terminalized the still-running two-scene job again as `provider_in_progress`.
- [x] Stale-root terminal-classifier RED `1 failed in 6.27s`; classifier and bounded
  classifier-repair GREEN `4 passed in 4.65s`; final protected suite `252 passed,
  1 dependency warning in 45.50s`. The classifier now always consults scene authority
  after explicit terminal reasons; a second durable marker permits only the repair
  consumed by this exact live bug, then blocks every later recovery.
- [x] Terminal classifier shipped as PR #936, squash SHA
  `eba42c15b1b58f8a8b08dd019584b1c8dde67bb3`; deploy run `33294851362`
  SUCCESS in `9m23s`. Bot/worker exact SHA; worker generation
  `766c231c71e448949aaafe81d2cb918d`, PID `706350`, heartbeat accepted/persisted.
- [x] Claim-scan live RED after the final marker: classifier repair stored once at
  `12:40:47`, recovery count `5`; at `12:40:48` the job returned to
  `failed_no_charge` before CAS claim. `attempts` stayed `5`, `locked_by` stayed
  empty and both scene tasks stayed authoritative `IN_PROGRESS/provider_running`.
  Provider submit/resubmit/fallback/charge/artifact/delivery all remained `0`.
- [x] Root cause: durable summary `scene_status_by_index=failed` was merged first
  with rank `4`; later actual provider `IN_PROGRESS` had rank `3` and was rejected,
  then the summary overwrote the scene again. Exact claim integration RED
  `1 failed in 5.92s`; minimal authority merge GREEN `1 passed in 5.14s`; focused
  authority/terminal/cancel/claim `25 passed, 106 deselected in 10.47s`; protected
  `252 passed, 1 dependency warning in 43.96s`.
- [x] Claim-ledger correction shipped as PR #937, squash SHA
  `6e0e42daae50859159c7781531e6c3228890dff5`; deploy run `33296036307`
  SUCCESS in `13m44s`. Bot/worker exact SHA; worker generation
  `91ea20ee8faf4fe8b75343127b814f27`, PID `710711`, heartbeat persisted/reject empty.
- [x] Bounded operational CAS requeue backed up the exact old rows at
  `/opt/toanaas/bot/delete/pv2-r01-job28-cas-requeue-20260830T132240.json`, then
  changed only job #28/project #32 from failed to queued. Attempts stayed `5`, outbox
  and task IDs were preserved, and new-job/provider/wallet actions were `0`. Claim
  still terminalized at `13:22:46` before CAS lock.
- [x] Refined production root: `provider_events` carried the same `task_id` with
  historical `FAILURE`, and root canonical summary carried a task identity plus stale
  root `FAILURE`. They were merged after task-scoped current `IN_PROGRESS`, so mere
  task identity was insufficient. Per-scene current status must become sticky trusted
  authority; only another per-scene current status or result-bearing completion may
  replace it.
- [x] Exact full-shape RED `1 failed in 5.31s`; sticky authority GREEN `1 passed in
  5.67s`; current FAILURE/exhaustion/cancel/claim comparators `27 passed, 74 deselected
  in 10.34s`; protected `252 passed, 1 dependency warning in 52.17s`.
- [x] Trusted authority shipped as PR #938, squash SHA
  `3d16cf60511318d2c5eb7c799ecbee8c07631c1b`; deploy run `33297745599`
  SUCCESS in `11m31s`. Bot/worker exact SHA; generation
  `8a63c9f4e4e949fe878e276c9d036511`, PID `714298`, heartbeat accepted/persisted.
- [x] Final backed-up CAS at
  `/opt/toanaas/bot/delete/pv2-r01-job28-trusted-cas-20260830T140614.json`
  requeued job #28 only. Claim authority PASS: attempts increased `5->6` and worker
  lock `vps-toanaas-01` appeared. Poll of the two old ShopAIKey tasks then terminalized
  at `14:06:25` as `all_scene_providers_exhausted_no_charge`; no artifact/delivery,
  submit/resubmit/fallback/charged Xu remained `0`, wallet `200/0`, tx `0`, credit
  events `1`, provider usage `0`. No further primary requeue is allowed.
- [x] Existing price map remains authoritative: tier `400`, customer quote `144 Xu`;
  ShopAIKey VEO Fast primary cost `4.550 VND/2 scenes`; approved Key4U VEO fallback
  cost `21.150,72 VND/2 scenes`, rounded internal budget/cost `212 Xu`; Owner absorbs
  negative margin `6.750,72 VND`. Exact customer price must not change.
- [x] Scene fallback RED: internal provider budget `212` was incorrectly included in
  equality of the three customer quote fields `144/144/144`, so controlled fallback
  stayed blocked. RED `1 failed in 5.84s`; minimal GREEN plus missing-confirm,
  quote-mismatch, debug-source and one-fallback limit `5 passed in 5.63s`; complete
  fallback/Key4U/price/claim matrix `88 passed in 9.34s`.
- [x] Post-rebase source gate on main `3d16cf6...`: focused fallback `9 passed in
  5.08s`; branch matrix `88 passed + 3 failures in 14.92s`; clean main reproduced
  the exact same three test IDs in `5.52s`, so `NEW_FAILURES=0`. Compile, YAML,
  diff-check and secret scan exit `0`; production diff remains `0 added / 1 removed`.
- [x] Final interleaving rebase after SubDub PR #939 onto `301d5b81...` is clean:
  focused fallback `9 passed in 8.49s`; compile/YAML/diff exit `0`; same 8-file
  scope and production diff `0 added / 1 removed`.
- [x] Tier-400 separation shipped in PR #940, squash `aaf3a9c6...`, deploy #156
  run `33302353405` SUCCESS. VPS bot and Owner worker exact SHA; worker PID
  `723568`, generation `284c6fe3...`, heartbeat persisted and reject empty.
- [x] Cost metadata seam RED/GREEN: router already checks fallback cost against
  provider budget, but scene request omitted `fallback_provider_cost_xu`. Minimal
  one-field propagation: RED `1 failed in 8.29s`, GREEN `1 passed in 5.56s`,
  protected fallback/Key4U `19 passed in 6.76s`, compile/diff `0`.
- [x] Cost metadata shipped in PR #941, squash `8134c28b...`, deploy #157
  run `33304170789` SUCCESS `3m18s`; bot/worker exact SHA, PID `728701`,
  generation `b8421a3a...`, heartbeat persisted/reject empty.
- [x] Query-only job #28 production dry-run: scene 1 stalled `73625s/300s`,
  Key4U ready/contract-valid, preclaim one scene, idempotency match, quote
  `144/144/144`, budget/cost `212/212`, DB/provider/wallet side effects `0`.
- [x] Single-candidate budget guard RED/GREEN: cost `213>212` incorrectly called
  Key4U once; minimal pre-submit fail-closed guard blocks before adapter. Exact
  persisted count-before-submit `0` allows the current attempt, while `1`
  blocks retry. Spend safety `12 passed`, affected total `49 passed`,
  compile/diff `0`; cost `212==212` still submits exactly once.
- [x] Guard shipped as PR #942, squash `db5f6a81...`; deploy #158 run
  `33307435330` SUCCESS `4m4s`, bot/worker exact SHA.
- [x] Query-only dry-run + snapshot rehearsal + production CAS PASS. Backup
  `/opt/toanaas/bot/delete/pv2-r01-job28-fallback-cas-20260830T181523.json`,
  SHA `cbef07f...`, mode `0600`; exact rows `28/32/27`, two primary tasks,
  quote `144/144/144`, budget/cost `212/212`, wallet/provider side effects `0`.
- [x] Live RED: attempts `6->8`, failed_no_charge before provider HTTP. Preclaim
  stored controlled fallback and terminal suppression, but hydrated worker payload
  dropped scene authority/quote/budget/cost and collapsed provider order to
  ShopAIKey; Key4U submit `0`, wallet/provider usage `0`.
- [x] Worker-context hydration RED/GREEN: conditional allowlist overlay runs only
  for suppressed controlled existing-task recovery. Worker-to-scene `1 passed`,
  claim/hydrate `2 passed`; expanded branch `97 passed + 4 failures` vs clean
  same 4, focused branch `61 passed + 2` vs clean same 2, `NEW_FAILURES=0`.
- [x] Worker-context overlay shipped as PR #943, squash `252758be...`, deploy
  `33317232271` SUCCESS. Bot and stopped Owner worker were synchronized/compiled at
  `1b259262...`; query-only quote/budget/cost/one-scene authority remained exact.
- [-] Continue only `SPEC-04H` below. Do not start `SPEC-05`, another product,
  quality row, upload, Confirm, project/job/outbox, ShopAIKey submit or price change
  before `SPEC-04H.9` is terminal.
- [x] Owner approved `D:\TOANAAS\video AI tham khảo` as the fixture library for
  later Product Video rows. Measure hash/metadata per selected file; do not swap
  the active PV2-R01 fixture during its failure loop.

Current source evidence:

- Primary RED: `6 failed in 12.60s`, exactly strict-plan loss, missing report
  helpers/integration and duplicate/report-failure gaps.
- Final focused GREEN plus delivery retry: `24 passed in 9.03s`.
- Tail/quality/manual/full-menu/message/RouteEngine protected batch:
  `103 passed in 45.45s`.
- Broad Tail/long-history comparator on branch: `38 passed, 7 failed in 11.49s`;
  clean detached base `3e28d3d9ac63baf26b939db4c55111bea3b97610`
  reproduced exact same seven test IDs with `38 passed, 7 failed in 784.38s`;
  `NEW_FAILURES=0`. Those assertions cover historical copy/long-video behavior
  outside this spec and were not edited.
- Review RED/GREEN for public product aliases and missing-report duplicate retry:
  `2 failed` -> `2 passed in 1148.99s`.
- Report exception RED/GREEN: `1 failed in 698.03s` ->
  `1 passed in 892.21s`; receipt/settlement remain terminal on report failure.
- Owner protected/excluded report boundary RED/GREEN: `7 failed, 1 passed in
  4227.60s` -> `8 passed in 1253.15s`; Product Video Edit and Long Video stop
  before DB claim, and all Video AI runtime aliases render the public product name.
- Protected project-profile fallback RED/GREEN: `2 failed in 38.79s` ->
  `2 passed in 886.85s`; a protected job remains excluded even when its product
  identity exists only in the persisted project profile.
- Strict material/local-artifact/UI-lock comparator: `21 passed in 54.08s`,
  including a decodable two-scene MP4 and 14 completed UI function byte locks.
- Final `py_compile bot.py` exit `0`; `git diff --check` exit `0`; forbidden-path,
  secret-value and completed UI hunk hits `0`.

### SPEC-04H: PV2-R01 Job #28 Poll and Scene Authority

Only this spec is active. Ordered sub-specs are blocking gates; finish each before
starting the next.

#### SPEC-04H.0 — Scope and protected locks

- [x] Existing identity only: request `VID-20260829-D78AA3`, project `32`, job `28`,
  outbox `27`, scenes `130/131`, fixture SHA prefix `784FBE5B`.
- [x] Customer quote stays `144/144/144`; provider budget/cost cap stays `212/212`;
  Owner charged Xu stays `0`.
- [x] Product Video Edit, AI Edit, Long Video and all already-LIVE-PASS products are
  protected. No code/test/live action for those products in this goal.
- [x] Reuse Tail/engine/artifact/delivery code by contract, adapted to Trend upload
  semantics; mechanical cross-product copying is forbidden.

#### SPEC-04H.1 — Query-only preflight and bounded live start

- [x] Bot/worker runtime synchronized at `1b259262...`; worker initially inactive.
- [x] Query-only preflight proved one controlled Key4U slot for scene 1,
  idempotency match, other active Owner jobs `0`, artifacts `0`, side effects `0`.
- [x] Exact Owner authorization limited paid Key4U to scene 1, no new job and no
  ShopAIKey resubmit.

#### SPEC-04H.2 — Live RED forensic and safe stop

- [x] Worker PID `830225` was stopped when attempts rose `8 -> 40`.
- [x] Durable RED: root looped ShopAIKey `provider_in_progress`; both scenes were
  reclassified to Key4U metadata although only scene 1 was authorized; scene-level
  controlled markers/fallback counts remained `false/0`.
- [x] Artifact/delivery `0`; provider usage/transactions `0`; credit events `1`;
  wallet `200/0`; charged Xu `0`. Worker final state inactive/PID 0.

#### SPEC-04H.3 — TDD RED

- [x] RED: claim-scoped scene 1 authority must not authorize scene 2.
- [x] RED: provider-deferred job must remain idle before durable `next_poll_at`.
- [x] RED: a due poll-only claim must not increment render attempts.
- [x] Self-review RED: scene 1 cannot borrow a root Key4U candidate when its own
  candidate marker is missing.
- [x] Measured RED: initial pair `2 failed, 10 deselected in 773.83s`; poll-attempt
  refinement `1 failed, 11 deselected in 8.45s`; missing scene candidate
  `1 failed, 11 deselected in 6.56s`.

#### SPEC-04H.4 — Minimal production fix

- [x] `services/video_real_render_connector.py`: claim-scoped fallback requires
  exact root scene index + scene controlled marker + scene-level Key4U candidate.
- [x] `services/remote_worker_api.py`: skip early claim before `next_poll_at`; due
  poll-only claim receives a lease without increasing attempts.
- [x] Provider adapters, provider URLs/ENV, Tail, Add-ons, quality, quote, wallet,
  artifact, delivery and other product routes unchanged.

#### SPEC-04H.5 — Source verification and review

- [x] Exact GREEN pair `2 passed, 10 deselected in 6.00s`; poll-attempt GREEN
  `1 passed, 11 deselected in 6.60s`.
- [x] Self-review exact pair GREEN `2 passed, 10 deselected in 7.52s`.
- [x] Focused job28/controlled fallback/spend safety `33 passed`.
- [x] Direct claim/defer/stall/scene authority blast radius `165 passed`.
- [x] Final combined regression `206 passed, 1 exact baseline deselected in 35.28s`;
  full compile exit `0`; YAML/diff/scope/secret gates clean.
- [x] Final combined after all self-review refinements `206 passed, 1 exact baseline
  deselected in 28.88s`; full compile exit `0`; YAML/diff/scope/secret gates clean.
- [x] Exact self-review: Critical `0`, Important `0`; poll-only attempt exemption
  additionally requires an existing provider task.
- [x] One focused local commit created; remote ship waits for exact SubDub releases.

#### SPEC-04H.6 — One source commit and ship

- [x] One focused commit on `fix/product-video-job28-provider-authority-loop`.
- [x] Rebased onto exact SubDub runtime/main `8cf77fef403a72e7a74a25db340f0932df25a4e4`;
  pre-evidence-amend HEAD `164cb43`; post-rebase regression `206 passed, 1 exact
  baseline deselected in 569.78s`; full compile exit `0`.
- [x] PR #950 squash-merged exact SHA `78b2815da77f09c27eb5962e3968b86583a8a4c7`;
  deploy run `33393610565` SUCCESS in `25m36s`; workflow compile/package/SSH PASS.
- [x] VPS bot/web/nginx active and health OK at exact merge SHA; tracked bot diff
  `0`. Owner Product Video worker fast-forwarded/compiled to exact SHA with tracked
  diff `0`, then kept inactive/dead PID `0` before CAS/live authorization.

#### SPEC-04H.7 — Post-deploy DB/task identity and backed-up CAS

- [x] Query-only forensic compared both 37-character task hashes with pre-start
  backup SHA `f7e16c79...`, mode `0600`; task-set SHA matched exactly. Provider
  usage, fallback/submit markers and matching journal submit markers were all `0`,
  so the exact scene-1 Key4U authorization was proven unconsumed.
- [x] CAS v2 rehearsed on two independent SQLite snapshots, then production applied
  once with backup `/opt/toanaas/bot/delete/pv2-r01-job28-authority-cas-v2-
  production-20260831T210914.json`, SHA `77975e9d...`, mode `0600`.
- [x] Post-CAS query-only + snapshot claim proof: identity `28/32/27`, attempts
  `40->40`, early claim empty, due claim job `28`, one controlled scene `[1]`,
  scene 2 ShopAIKey/no candidate, quote `144/144/144`, budget/cost `212/212`,
  artifact/delivery/provider/wallet side effects `0`.

#### SPEC-04H.8 — Same-job live terminal

- [-] Worker start on runtime `78b2815` exposed a new hydration RED before paid
  HTTP: scene 1 request carried current telemetry count `1` into the policy and
  hit `fallback_limit_reached`; scene 2 inherited root Key4U candidate. Observer
  stopped worker immediately. Task hashes/job counts/attempts `40`, provider usage,
  ShopAIKey/Key4U HTTP submit markers, wallet, artifacts and delivery all stayed `0`.
- [x] Source RED `2 failed, 10 deselected in 576.10s`; minimal GREEN `2 passed,
  10 deselected in 7.87s`; focused hydration/policy/spend/parallel/reconcile
  `49 passed in 9.53s`; combined `206 passed, 1 exact baseline deselected in
  33.68s` after retry-lock self-review; full compile exit `0`.
- [x] Rebased cleanly onto SubDub #951 exact main `8de058a...`; post-rebase
  combined `206 passed, 1 exact baseline deselected in 34.67s`; production/test
  diff auto-merged without overlap.
- [x] Hydration correction shipped as PR #952, squash SHA
  `4152d6bc7b6934a9fc40b477ddc02fae8960651b`; deploy run `33407010553`
  SUCCESS in `4m21s`; bot/worker exact SHA, tracked diff `0`, worker inactive
  before CAS restore.
- [-] Corrected live tick exposed a second pre-HTTP RED: scene 1 had exact
  controlled Key4U authority but still carried its ShopAIKey pending task identity,
  so the recovery provider mismatch guard fired before transition. Scene 2 remained
  correctly isolated. Worker stopped; task hashes/attempts/job counts/provider
  usage/HTTP submit/wallet/artifact/delivery deltas stayed `0`.
- [x] Transition RED `1 failed, 11 deselected in 553.10s`; exact GREEN `1 passed,
  11 deselected in 5.72s`; guard inverse `3 passed`; focused `83 passed in
  17.30s`; combined `206 passed, 1 exact baseline deselected in 34.58s`; full
  compile exit `0`.
- [x] Provider-transition correction shipped as PR #953, squash SHA
  `5ebc665ef8eb4fc291e783ce37290c98fbb33859`; deploy run `33411801263`
  SUCCESS in `23m29s`. SubDub #954 runtime `36c5d327...` contains PR #953 by
  ancestry; bot/worker tracked diff `0`, services active and Owner worker inactive.
- [-] CAS v4 restored the same job with backup SHA `a0b9e1a5...`, mode `0600`.
  The next worker tick crossed the controlled transition and transiently reported
  `provider_submit_called=true`/scene-1 fallback count `1`, then a later ShopAIKey
  reconcile erased the Key4U attempt receipt and restored the old 37-character task
  hash. Provider usage stayed `0`, but paid-call evidence is ambiguous, so the exact
  one-call authorization is treated as consumed and worker was stopped. No CAS,
  restart or paid retry is allowed under the old authorization.
- [x] Submit-receipt RED `2 failed`; production-shape/poll-survival/retry-lock
  GREEN `4 passed`; focused fail/defer/restart/spend `71 passed`; combined
  `210 passed, 1 exact baseline deselected in 26.97s`; full compile exit `0`.
- [x] Rebased cleanly onto SubDub #955 exact main `832681d9...`; post-rebase
  focused `71 passed in 513.19s`, combined `210 passed, 1 exact baseline
  deselected in 27.64s`, full compile exit `0`; no overlapping file.
- [x] Receipt persistence shipped as PR #956, squash SHA
  `95c8f1fee510a93d21dfdcba581976de561f81b9`; deploy run `33429546236`
  SUCCESS in `4m20s`. Bot and inactive Owner worker exact SHA; tracked diff `0`,
  bot/web/nginx active and health OK.
- [x] No-provider receipt CAS rehearsed then applied once. Production backup
  `/opt/toanaas/bot/delete/pv2-r01-job28-ambiguous-receipt-production-
  20260901T022707.json`, SHA `a89d4d5c...`, mode `0600`. Job/project/outbox are
  `failed/failed/terminal_failed`; receipt is immutable
  `ambiguous_submit_called_without_transport_receipt`, authorization `consumed`,
  counts `[1,0]`, attempts `40`, task-set SHA unchanged, charged/provider usage/
  wallet/artifact/delivery deltas `0`.
- [x] Owner authorized exactly two new Key4U calls for existing job/project/outbox
  `28/32/27`: one replacement per scene, no new identity row, no upload/Confirm,
  no ShopAIKey resubmit, quote `144/144/144`, budget/cost `212/212`, charged `0`.
- [x] `SPEC-04H.8` source is READY_TO_SHIP. Authorization v2 has scene allowlist
  `[1,2]`, per-scene cap `1`, global cap `2`, immutable legacy history and one
  immutable receipt namespace per authorization. Accepted tasks are poll-only;
  no-task or terminal failed tasks consume their slot and stop failed-no-charge.
  RED `5 failed in 5.11s`; exact + locked-engine `15 passed in 7.06s`; focused
  `37 passed`; impact `252 passed in 77.55s`; full compile/diff `0`. The locked orchestrator hash,
  `bot.py`, Tail and SubDub sources are unchanged.
  Strategy/Tail matrix has `47 passed` and the exact baseline Script fixture SHA
  failure reproduced on clean source; `NEW_FAILURES=0`.
- [ ] Ship/deploy one PR, then install the new authorization with rehearsal/backup/
  production CAS while Owner worker is inactive. CAS must preserve receipt history,
  exact identities, attempts, quote, provider cap and wallet/provider baselines.
- [ ] Poll cadence respects `next_poll_at`; an accepted Key4U task is poll-only and
  cannot spend a second slot for the same scene.
- [ ] Scene 1 and scene 2 may each consume exactly one replacement slot; authority
  cannot leak across scenes and total replacement calls cannot exceed `2`.
- [-] PR #958/runtime `1b8394d8...` and CAS backup SHA `4f21a5fc...` are proven.
  First live tick consumed scene-1 as ambiguous/no-transport and terminalized
  failed-no-charge; scene 2 had no receipt/call. Exact forensic exposed three source
  seams: attempts `40->41`, terminal lock not cleared, and unreceipted scene 2
  inherited Key4U/count `1`. Worker is inactive, wallet `200/0`, provider usage `0`,
  identity counts `32/28/27`. RED `2 failed`; GREEN `2 passed in 5.42s`; focused
  `63 passed in 8.65s`. Ship correction only; do not use remaining slot yet.
  Final impact is `253 passed in 66.58s`; full compile exit `0`.
- [x] PR #959/runtime `6f94cd6a...`, deploy `33476386996` SUCCESS `3m15s`.
  False scene-2 state was repaired by rehearsal/production CAS, but the remaining
  slot was not used because scene 1 had no task. Pause CAS backup SHA `039a07b0...`,
  mode `0600`; terminal rows, attempts `40`, lock released, calls `1/1`, scene-2
  unused, wallet/provider/identity unchanged.
- [x] Official Key4U docs prove VEO/OpenAI video uses POST
  `https://api.key4u.vn/v1/videos/generations` and GET `/v1/videos/{id}`. Source now
  derives these only when auth exists, keeps explicit overrides, sends documented
  JSON, and records transport truth. RED `2 failed`; GREEN `2 passed`; focused
  `55 passed, 1 exact baseline Tail deselected`; impact `268 passed in 65.52s`;
  compile `0`; branch/clean main share the same 7 historical failures.
- [x] PR #960/runtime `9d663f4e...`, deploy `33481990125` SUCCESS `3m40s`.
  Runtime preflight was provider-free and found explicit production VEO path
  `/v1/videos`; this correctly overrode the derived fallback, but is stale versus
  official docs. Exact official-host normalization RED `1 failed` -> GREEN `1 passed
  in 5.06s`; custom proxy + family guard `24 passed`; impact `269 passed in 60.93s`.
  Scene-2 slot is still unused and job remains terminal/inactive.
- [-] PR #961/runtime `91be7e95...`, deploy `33485495005` SUCCESS `3m35s`.
  Runtime preflight selected official generation/poll paths. Remaining scene-2 call
  returned a real Key4U task; calls are now `2/2`, receipts `[1,2]`, no artifact.
  Accepted task inherited the old primary `900s` stall clock and was terminalized
  before poll. Worker stopped; attempts `40`, lock released, wallet `200/0`, usage
  `0`, identity unchanged. Stall-reset RED `1 failed` -> GREEN `1 passed in 6.08s`;
  focused `68 passed`; impact `270 passed in 64.50s`. No submit remains authorized;
  ship correction and poll only the accepted scene-2 task.
- [x] PR #962/runtime `8624a528...`, deploy `33488979036` SUCCESS `3m13s`,
  reset the accepted task clock. Poll-only CAS then proved a second source RED:
  stale root `scene_status_by_index[2]=failed` outranked the current scene-2
  pollable `provider_running/queued` row, so the ledger terminalized without a
  poll. Minimal authority correction lets only a current task-bearing pollable
  non-terminal scene row override that stale summary; scene 1 remains failed with
  no task and an explicit current provider failure still wins. RED `1 failed, 1
  passed`; exact GREEN `2 passed in 7.57s`; final inverse guard `2 passed in
  6.13s`; focused ledger/job28 `49 passed in 9.65s`; impact `197 passed, 1 exact
  baseline deselected in 31.37s`. Clean main
  reproduced the deselected historical attempts assertion as `1 failed in
  612.99s`, so `NEW_FAILURES=0`; full compile and locked engine hash exit/PASS `0`.
  Cap remains `2/2`, remaining `0`; the next live action may poll/download only.
- [-] PR #963 squash `6960c7f6...`, deploy `33496787770` SUCCESS `3m6s`;
  bot and inactive Owner worker exact SHA/clean, services active/health OK. Snapshot
  rehearsal and production poll-only CAS PASS with cap `2/0`, submit false and
  finance unchanged; production backup SHA `78872b67...`, mode `0600`. Deployed
  ledger suppressed the false job terminal, but read-only pre-start verifier found
  scene 1's old task still resurrected from `scene_ledger`, provider events, winner
  map and canonical summary despite both current rows declaring scene 1 failed,
  taskless and exhausted. Worker was never started. Job was immediately paused
  fail-closed with backup SHA `09713e3d...`, mode `0600`; status
  `failed/failed/acknowledged`, attempts `40`, cap/receipts/task/finance unchanged.
- [x] Same-spec ownership RED `1 failed in 6.19s` -> GREEN `1 passed in 5.05s`.
  Self-review disagreement RED `1 failed in 6.23s` -> consensus GREEN `2 passed
  in 5.50s`; exact old/new guards `4 passed in 5.70s`; focused `51 passed in
  8.69s`; impact `199 passed, 1 exact baseline deselected in 27.08s`; locked
  engine hash and final full compile PASS/exit `0`. Only unanimous current rows
  explicitly failed+exhausted+taskless suppress task-bearing history for that
  scene; a disagreeing row preserves ownership. Scene 2's real accepted task
  remains active/pollable. Provider calls and wallet mutations `0`.
- [-] PR #964 squash/runtime `85cb4482...`; deploy `33501305826` SUCCESS in
  `3m25s`; bot and inactive Owner worker exact SHA/clean, services active/health
  OK. Snapshot plus deployed pre-start verifier passed after CAS cleared every
  scene-1 task alias; production backup SHA `25d54637...`, mode `0600`. Worker PID
  `996057` claimed existing job `28` once and terminalized. Terminal forensic proves
  no third submit: root submit false/HTTP `0`, every new attempt is `phase=poll`,
  Key4U poll HTTP `400`, accepted scene-2 raw task hash prefix `925d3315ec8a`
  unchanged, cap `2/0`, provider usage/transactions/charged Xu `0`, wallet `200/0`,
  artifact/concat/delivery `0`. Worker stopped inactive PID `0`.
- [x] Poll-contract root is isolated to official Key4U OpenAI video. Runtime and
  submit evidence use model `veo3.1-fast` with a raw 37-character `task_...`, while
  official GET `/v1/videos/{id}` examples use a model-qualified ID such as
  `sora-2:task_...`; raw GET returned the measured `400`. Minimal adapter fix adds
  the configured model exactly once only for Key4U official hosts + exact OpenAI
  poll path + raw `task_...`. Composite IDs, generic query, Kling, Hailuo and custom
  proxy stay unchanged. RED `1 failed, 5 passed in 8.52s`; exact GREEN `6 passed
  in 4.93s`; focused Key4U/job28 `52 passed in 6.38s`; broad branch `371 passed,
  1 skipped, 61 failed in 48.17s` vs clean main exact same 61 IDs with `365 passed,
  1 skipped in 601.32s`, `NEW_FAILURES=0`; locked hash/full compile/diff PASS.
- [-] PR #965 squash/runtime `bbfeca06...`; deploy `33507905216` SUCCESS in
  `4m14s`; bot and inactive Owner worker exact SHA/clean, services active/health
  OK. Snapshot and production alias-clear CAS plus deployed verifier passed with
  scene 1 taskless, scene 2 hash prefix `925d3315ec8a` active/pollable, cap `2/0`,
  submit false and finance unchanged. Production backup SHA `0ad9b441...`, mode
  `0600`. Worker PID `1002035` claimed existing job once and terminalized; worker
  stopped inactive PID `0`. Forensic again proves submit false/HTTP `0`, task/cap/
  finance unchanged and only poll HTTP `400`; artifact/concat/delivery `0`.
- [x] Exact live root after #965: persisted-task reconstruction omitted
  `provider_poll_url_override`, so router used generic
  `/v1/video/query?id={task_id}`; the adapter's official-path qualification branch
  was unreachable. Minimal router correction recovers the model-family poll
  contract from the configured Key4U adapter only when persisted override is
  absent; explicit/custom override remains authoritative. Safe durable markers
  record recovered/source/model-qualified booleans without exposing URL. RED
  `2 failed in 5.50s`; GREEN `2 passed in 5.69s`; final exact chain `8 passed in
  5.01s`; focused `67 passed in 7.02s`; broad `373 passed, 1 skipped, exact same
  61 baseline failures in 37.98s`, `NEW_FAILURES=0`; locked hash/direct/full
  compile/diff PASS. Provider calls and wallet mutations during source gate `0`.
- [-] PR #966 squash `47d56e5c...`, deploy `33511826474` SUCCESS in `3m57s`;
  latest shared runtime `3d45e2e...` contains #966 by ancestry. Snapshot and
  production alias-clear CAS plus deployed verifier PASS; production backup
  `/opt/toanaas/bot/delete/pv2-r01-job28-scene2-poll-only-production-
  20260901T215503.json`, SHA `16201473...`, mode `0600`. Owner worker PID `1016755`
  claimed existing job `28` once and was stopped inactive PID `0` after terminal.
  Latest poll proves both corrections executed: contract recovered from
  `KEY4U_VEO_VIDEO_POLL_URL` and task ID model-qualified. Key4U returned HTTP `400`
  with safe message `task_not_exist`. Root submit false/HTTP `0`, accepted task hash
  prefix `925d3315ec8a` unchanged, cap `2/0`, artifact/concat/delivery `0`, wallet
  `200/0`, transactions/provider usage/charged Xu `0/0/0`, credit events `1`.
- [x] The prior blocker is closed by the exact Owner V3 authorization. V2 remains
  immutable and consumed at `2/0`; V3 alone grants exactly two new Key4U calls,
  one replacement for scene 1 and one for scene 2, on existing identity `28/32/27`.
  New job/project/outbox, upload/Confirm replay and ShopAIKey resubmit remain
  prohibited; prices stay `144/144/144`, provider cap `212/212`, charged Xu `0`.
- [x] V3 source RED proved durable worker merge dropped the inactive V2 receipt
  namespace whenever V3 became active: `1 failed, 2 passed, 22 deselected in
  635.35s`. Minimal GREEN keeps every persisted namespace immutable and permits
  incoming receipts only for the persisted active V3 authority. Exact V3 `3 passed,
  22 deselected in 5.39s`; job28 focused `50 passed in 12.34s`; focused plus locked
  engine/UI hashes `78 passed in 9.92s`. Broad branch `338 passed, 73 failed` vs
  clean main `335 passed, exact same 73 failed in 715.58s`, so `NEW_FAILURES=0`.
  Full compile and diff-check exit `0`; source provider calls/wallet mutations `0/0`.
- [x] PR #970 squash/runtime `0780f7ae...`; deploy `33533569117` SUCCESS in
  `3m44s`; bot/worker exact SHA and tracked diff `0`, bot/web/nginx active. Snapshot
  rehearsal and production CAS PASS on existing `28/32/27`: V3 `0/2`, V2 immutable
  `2/0`, only scene 1 controlled, prices/cap/wallet unchanged. Production backup
  SHA `ec0c5b7b...`, mode `0600`; pre-start parser/claim verifier PASS with DB/
  provider/wallet mutations `0/0/0`.
- [-] First V3 live tick was hard-stopped before scene 2. Receipt scene 1 changed to
  V3 `1/1`, but task hash `e5ec08abdfc0` exactly matched the old V2 task and receipt
  transport remained `http_sent=false`, HTTP `0`; therefore no new paid call is
  proven and the V3 scene-1 receipt cannot be treated as consumed. Root trace found
  `_render_scene_async` discarded the versioned replacement idempotency key and
  recomputed the legacy key, allowing provider dedupe to return the old task.
  Worker inactive PID `0`; wallet `200/0`, transactions/provider usage/charged Xu
  `0/0/0`; artifact/concat/delivery `0`.
- [x] Exact idempotency RED `1 failed, 24 deselected in 551.30s`; minimal GREEN
  `1 passed, 24 deselected in 6.63s`. Job28/fallback `50 passed in 10.21s`; legacy
  fallback plus locked engine/UI `57 passed in 8.34s`; compile/diff exit `0`.
  Versioned authority now supplies its own key; non-versioned fallback retains the
  legacy key unchanged. Ship this seam, then CAS-reset only the false V3 receipt and
  resume within the original two-new-call cap.
- [x] Final strategy verifier `8 passed` plus the exact pre-existing PV2-R03 fixture
  SHA failure; no file in that product/spec changed. YAML, changed production/test
  compile, diff-check and secret scan exit `0`.
- [x] PR #971 squash/runtime `538b3e60...`; deploy `33538556118` SUCCESS in
  `3m30s`; bot and inactive Owner worker exact SHA, tracked diff `0`, bot/web/nginx
  active. Read-only current state confirmed V3 false receipt `[1]`, old task hash,
  transport `0`, no artifact/delivery and finance unchanged. It also proved V2
  namespace had disappeared after the worker cycle despite the #970 fail/complete
  durable merge.
- [x] Boundary stages on SQLite snapshots isolated the second namespace loss:
  actual claim + worker payload preserved `{V2,V3}`; actual `fail/defer` with an
  active-only incoming payload also preserved `{V2,V3}`; production changes/provider/
  wallet were `0/0/0`. Only `product_video_scene_ledger_state(job, partial_result)`
  preferred the active-only result map and erased V2 before fail persistence.
- [x] Ledger namespace RED `1 failed, 25 deselected in 651.64s`; final GREEN
  `1 passed, 25 deselected in 7.23s`. The ledger now starts from persisted namespaces,
  accepts only active V3 partial receipts and ignores attempted V2 overwrite.
  Job28/persistence focused `52 passed in 10.66s`; locked engine/UI `48 passed in
  9.42s`; changed production/test compile and diff-check exit `0`. Ship this exact
  seam before any production reset or worker restart.
- [x] PR #972 squash/runtime `53d8305b...`; deploy `33542877096` SUCCESS in
  `3m27s`; bot/worker exact SHA and tracked diff `0`. False-receipt reset rehearsal,
  production CAS and pre-start verifier all PASS: V2 restored `2/0`, V3 reset `0/2`,
  only scene 1 selected, identity/price/cap/wallet exact; production reset backup
  SHA `a279da68...`, mode `0600`.
- [-] Corrected live resume was hard-stopped before scene 2. Exact forensic showed
  `submit_invoked_count=0`, `provider_http_request_sent=false`, provider attempts
  only poll old tasks and no new task was created; therefore V3 still consumed zero
  genuinely new paid calls. Old task aliases were revived from manifest/ledger and
  the executor's legacy recovery prerequisite required a task ID, preventing the V3
  authorization from reaching submit. Worker inactive PID `0`; wallet/transaction/
  provider-usage/charged/artifact/delivery deltas remain `0`.
- [x] Taskless V3 RED `1 failed, 1 passed, 26 deselected in 10.50s`; claim-scope
  RED `1 failed, 28 deselected in 7.35s`; stale-manifest RED `1 failed, 31 deselected
  in 5.86s`. Final exact taskless/claim/manifest/two-scene/pending suite `7 passed,
  26 deselected in 5.80s`; focused job28/persistence `59 passed in 11.32s`; locked
  engine/UI `57 passed in 10.48s`; full bot/local-worker/connector/test compile,
  diff and secret gates PASS. Taskless semantics require V3+, exact selected scene,
  exact finance/identity and Key4U candidate; V2/legacy remain task-required. Stale
  manifest task/artifact aliases are suppressed only when all current rows agree
  taskless and V3 authorizes that scene. Two-scene mock proves ordered calls `[1,2]`,
  distinct versioned keys, pending IDs empty, V2 immutable and V3 exactly `2/2`.
- [x] Final strategy gate `8 passed` plus the exact pre-existing PV2-R03 fixture SHA
  failure; taskless correction changes no PV2-R03 file. YAML/diff/secret PASS.
- [x] PR #973 squash/runtime `ab267bedd4aa300bf2160be7b8d828009578127c`;
  deploy `33588541923` SUCCESS in `4m2s`; bot/worker exact SHA before recovery and
  tracked diff `0`. Combined DB + canonical-manifest taskless reset passed with
  backup `/opt/toanaas/bot/delete/pv2-r01-job28-taskless-v3-reset-production-
  20260902T112112.json`, SHA `9739d756...`, mode `0600`: V2 `[1,2]` immutable,
  V3 `0/2`, scene 1 selected, all task/artifact aliases empty, wallet/provider/
  charged deltas `0/0/0`.
- [-] Live RED after the clean reset: the bot zero-task watchdog ran while the
  Owner worker was intentionally inactive and treated its transient stale/read-only
  worker eligibility as permanent admission failure. It terminalized existing
  identity `28/32/27` before claim; V3 remains genuinely unused `0/2`, canonical
  manifest stays taskless, artifact/concat/delivery and all finance deltas stay `0`.
- [x] Watchdog authority RED `1 failed, 1 passed, 33 deselected in 528.98s`.
  Strict-scope RED `3 failed, 37 deselected in 7.77s` proved a different V3 ID,
  identity or self-consistent price/cap could inherit the wait branch. Final exact
  GREEN is `7 passed, 33 deselected in 5.15s`; full job28 authority is `40 passed
  in 7.64s`; protected zero-task/outbox is `85 passed in 31.58s`.
  Combined branch is `220 passed, 2 failed in 50.98s`; clean `ab267bed` reproduces
  both exact failure IDs in `547.25s`, so `NEW_FAILURES=0`. Only an
  untouched exact authorization `pv2-r01-job28-key4u-replacements-v3` on identity
  `28/32/27/VID-20260829-D78AA3`, price `144` and cap `212` may wait through worker
  disconnected/stale-heartbeat/expired-lease; any scope mismatch, SHA mismatch or
  permanent provider route block still fails closed.
  Full `bot.py` compile and changed worker/source/test compile exit `0`.
- [x] New local snapshot-first recovery CAS compile and isolated SQLite rehearsal
  PASS: exact failed rows become `queued/queued_for_worker/acknowledged`, attempts
  remain `40/1`, V2 immutable, V3 `0/2`, scene selection `[1]`, manifest hash and
  wallet/provider counts unchanged. Duplicate replay and invalid V3 both fail before
  mutation; provider calls/wallet mutations `0/0`. Production remains untouched.
- [x] Final strict-scope compile and state gates: full `bot.py`, local worker, queue
  and changed test compile exit `0`; YAML/diff/secret/forbidden scope clean. Strategy
  V2 is `8 passed` plus the exact pre-existing PV2-R03 fixture SHA failure; this
  spec changes no PV2-R03 file.
- [x] Rebased conflict-free onto SubDub PR #974 main/runtime
  `c8e954a03322f4af8559cf3f6e99178dbd6bfe7a`. Post-rebase combined gate is
  `220 passed, 2 failed in 924.92s`; clean exact main reproduced the same two IDs
  in `856.69s`, `NEW_FAILURES=0`. Full and changed compile exit `0`; Strategy is
  `8 passed` plus the exact PV2-R03 baseline; YAML/diff/secret/scope clean.
- [x] PR #975 squash/runtime `f507feef5f546211c064c79eb15c310ec8a4d682`;
  deploy run `33609379330` SUCCESS in `3m39s`. The PR legitimately had zero checks
  because `bot-source-compile.yml` path-filters non-`bot.py` queue/test/docs diffs;
  the measured local post-rebase compile/protected gates remained authoritative.
  Bot checkout was exact/clean. Owner worker was safely fast-forwarded from
  `ab267bed...` to exact runtime using the deployed bot checkout, with backup ref
  `refs/backups/worker-pre-product-video-20260902084632`; worker compile and tracked
  diff `0`, service inactive PID `0` before recovery.
- [x] Exact-runtime VPS rehearsal PASS on SQLite backup `14,184,448` bytes mode
  `0600`; recovery backup mode `0600`; replay fail-closed. Production CAS then
  passed with backup `/opt/toanaas/bot/delete/pv2-r01-job28-watchdog-recovery-
  production-20260902T155114.json`, SHA `53dd0c48...`, mode `0600`. After more than
  one watchdog interval, job remained `queued/queued_for_worker/acknowledged`,
  taskless wait marker true, V3 `0/2`, scenes pending, manifest SHA `6f2c6947...`
  unchanged and charged Xu `0`. Prestart verifier passed all 15 exact checks.
- [-] Fresh-worker LIVE RED: one worker start at PID `1097461` caused the bot
  watchdog to terminalize `28/32/27` on `worker_poll_existing_task_read_only`
  before the worker could claim. Worker was stopped inactive PID `0`; identity
  counts remained `32/28/27`, V3 `0/2`, wallet `200/0`, transaction/credit/provider
  usage `0/1/0`, provider transport and charged Xu `0`.
- [x] Fresh-worker claim-handoff RED `1 failed, 40 deselected in 994.59s` -> GREEN
  `1 passed, 40 deselected in 9.20s`; focused inverse/claim `5 passed in 13.47s`;
  full job28 authority `42 passed in 10.91s`; protected watchdog/outbox `85 passed
  in 51.23s`; combined `222 passed, 2 exact baseline failures in 61.21s`,
  `NEW_FAILURES=0`. Exact V3 now survives the read-only bot handoff and the actual
  worker claim path advances acknowledged outbox to a claim, while a permanent
  provider blocker still terminalizes. Provider/wallet calls during source tests `0`.
- [x] Rebased conflict-free onto SubDub PR #976 main/runtime
  `dd217036577e2627a9bfcf8ce1ed510ba6ebb233`; upstream PR #975 was skipped as
  already applied and only the claim-handoff commit replayed. Post-rebase focused
  claim/inverse `5 passed in 10.46s`; full authority + protected watchdog/outbox
  `127 passed in 33.26s`; full and changed compile exit `0`; YAML/diff/Strategy/
  secret/scope retain the exact source result.
- [ ] Two distinct scene clips and one final MP4 terminal; otherwise stop at the
  exact new RED and reopen only `SPEC-04H`.

#### SPEC-04H.9 — Full product/add-on/artifact/delivery lock

- [ ] Revalidate the complete Trend upload flow: analysis, content/profile, entity
  details, style, requirements/context, plan, prompts, Add-on, Review, tier 400,
  Invoice, Confirm and Status. Do not count a partial traversal as PASS.
- [ ] Subtitle-source and transition `1/1` are requested, materialized, applied and
  visibly present; missing Add-on list is empty.
- [ ] MP4 is real two-scene cover-fit 9:16, H.264 + AAC, measured SHA/bytes/duration/
  dimensions/first-last frames/scene boundary/loudness, with no black padding.
- [ ] Exactly one Telegram MP4, receipt and customer report; delivery deduped;
  charged Xu `0`, transaction and credit-event deltas `0`.
- [ ] Mark `PV2-R01 LOCKED_LIVE_PASS`; freeze its code and only then open the next
  active representative in Strategy V2.

### SPEC-04I: Compatible Product Add-on — SubDub Auto 2-Speaker

> Pending until `SPEC-04H.9` is terminal. This spec does not reopen or modify any
> lane/product already marked `LOCKED_LIVE_PASS`.

- [ ] Audit every active Product Video lane by media semantics. Show Auto 2-speaker
  only where a source video/audio with dialogue exists; do not mechanically attach
  it to text/image-only generation lanes.
- [ ] Reuse the locked SubDub Auto 2-speaker contract unchanged: detect male/female,
  translate, synthesize two voices and mux/deliver through the product's existing
  Tail Add-on boundary. Product adapters may connect data, but SubDub engine/cast/
  timing/mux/wallet code stays byte-locked.
- [ ] Expose Auto multi-speaker only as a disabled/locked option with truthful copy
  until SubDub Auto multi has a real MP4 LIVE PASS. It must have no provider route,
  callback submit, price or wallet side effect while locked.
- [ ] TDD compatibility, route/back/idempotency/Add-on materialization and no-cross-
  product guards. Live-test one not-yet-PASS media-compatible Product Video lane;
  prove male/female detection, translation, two-voice dub, final MP4, receipt/report
  and Owner wallet delta `0` without retesting a locked product.
- [ ] Only after that representative PASS, connect the same contract to remaining
  compatible unfinished products, adapted to each product's own source/context;
  never copy flow mechanically.

### SPEC-05: Distinct Two-Scene Product/Lane LIVE Matrix

> Historical table only under the V2 scope override. Do not execute Long Video or
> Video Edit rows. Active product/lane order and distributed quality assignments
> come only from `KIEM-THU/PRODUCT-VIDEO-LIVE-STRATEGY-V2.md`, after SPEC-04H.9.

Each row needs a different scenario or fixture, exact request/project/job/outbox identity, two scene outputs, final MP4 SHA256/bytes/codec/dimensions/duration, audio evidence when requested, add-on requested/materialized/applied proof, Telegram delivery message id, `charged_xu=0`, zero wallet transaction delta, and no duplicate submit/delivery.

| Product/lane | Distinct scenario | Flow + Add-on | Two-scene artifact | Delivery/0 Xu |
|---|---|:---:|:---:|:---:|
| Video theo trend / manual | PV-L01: quầy cà phê xe điện -> sinh viên nhận ly tái sử dụng | [x] | [ ] | [ ] |
| Video AI chan that / prompt manual | PV-L02: Linh tạo bình gốm xanh -> nâng thành phẩm | [ ] | [ ] | [ ] |
| Kich ban -> Video / manual | PV-L03: 5 cảnh trà sen Tây Hồ | [ ] | [ ] | [ ] |
| Ghep anh thanh video / custom | PV-L04: 2 ảnh đồng hồ thủ công | [ ] | [ ] | [ ] |
| Video tu quay / custom direction | PV-L05: giữ người thật gõ máy -> quán cà phê rooftop, giữ source audio | [ ] | [ ] | [ ] |
| Storyboard / manual | PV-L06: robot gieo hạt -> mầm cây phát sáng | [ ] | [ ] | [ ] |
| Video dai tap / manual | PV-L07: thợ lặn tìm thư viện -> mở phòng sách phát sáng | [ ] | [ ] | [ ] |
| Y tuong video / manual handoff | PV-L08: xe cà phê điện -> barista phục vụ sinh viên | [ ] | [ ] | [ ] |
| Chinh sua Video / two-scene input | PV-L09: cắt review 29,54s thành 2 nhịp 9:16, giữ lời nói gốc | [ ] | [ ] | [ ] |

### SPEC-06: Video AI Real All-Quality LIVE Matrix

- [ ] Every tier uses a different two-scene scenario.
- [ ] Every tier is selected through the real Telegram quality button.
- [ ] Every tier reaches terminal delivery with a validated MP4.
- [ ] Every tier preserves its identity from button to manifest.
- [ ] Every Owner receipt is 0 Xu with zero wallet mutation.

### SPEC-07: Completion Audit and GitHub Evidence

- [ ] Every explicit Owner requirement maps to terminal, PR, runtime, job, artifact, or receipt evidence.
- [ ] No checklist row is pending, contradicted, indirect, or missing.
- [ ] Final GitHub tracker contains PR/check/deploy/runtime/live links and measured hashes/ids.
- [ ] Goal is marked complete only after the full audit passes.

## Evidence Log

| Time (Asia/Saigon) | Spec | Evidence | Result |
|---|---|---|---|
| 2026-08-31 | PV2-R01 job28 provider-authority loop | PR #943 runtime synced; query preflight PASS; Owner start attempts 8->40 then worker stopped; both scenes wrongly opened to Key4U metadata; side effects 0; RED 2 failed -> GREEN 2 passed; focused 33; protected 165 | SOURCE GREEN; ship/deploy/new CAS still open |
| 2026-08-30 | PV2-R01 job28 authority-repair RED/GREEN | PR #934 -> `ef81f6a...`; deploy `33290296142` SUCCESS; worker generation `4ab7fd...`; live blocker recovery `3/3`; RED 1 failed -> GREEN 1 passed; protected 242 and final 251 passed | SOURCE PASS; one repair ship/live still open |
| 2026-08-28 | SPEC-04G ship/runtime | PR #917 -> `d5dc300...`; compile/deploy SUCCESS; bot+worker exact SHA | PASS |
| 2026-08-28 | SPEC-04G live | Job #26 tier 400, Invoice/Confirm/Status, valid 2-scene 9:16 MP4, delivery 27652, 0 Xu/0 tx | QUALITY/ARTIFACT PASS |
| 2026-08-28 | SPEC-04G.1 live RED | UI no voice/music/subtitle but durable `partial_addons=1`; strict plan lost at generic project persistence | RED; lane remains open |
| 2026-08-28 | SPEC-04G.1 source RED/GREEN | Primary 6 failed -> final focused 24 passed; report exception and protected-product RED/GREEN terminal | SOURCE PASS |
| 2026-08-28 | SPEC-04G.1 protected verify | 103 passed; artifact/UI lock 21 passed; broad branch/base exact 38 passed + same 7 historical failures | NEW_FAILURES=0 |
| 2026-08-26 | READ/CONTRACT | Source route audit at branch HEAD `f4c022a` | Manual direct-Tail contract FAIL; SPEC-01 opened |
| 2026-08-26 | SPEC-01 RED environment attempt | Bundled Python collection: missing `telegram`; 623.45s | ENV INVALID; not accepted as RED |
| 2026-08-26 | SPEC-01 authoritative RED | Python 3.14 dependency-complete: `11 failed, 1 warning in 9.62s` | PASS as RED; missing seam/constants/wiring reproduced |
| 2026-08-26 | SPEC-01 GREEN attempt 1 | Pytest internal error in `tests/conftest.py`: subprocess `git diff` raised WinError 6 after 674.48s | HARNESS INVALID; no assertion result, GREEN remains open |
| 2026-08-26 | SPEC-01 GREEN attempt 2 | `17 passed, 2 failed, 1 warning in 479.82s` | Behavioral matrix GREEN; two test-only decorator-wrapper introspection assertions failed, full GREEN remains open |
| 2026-08-26 | SPEC-01 GREEN attempt 3 | `18 passed, 2 failed, 1 warning in 464.36s` | Expanded behavioral matrix GREEN; decorator lacks `__wrapped__`, two static introspection assertions remain open |
| 2026-08-26 | SPEC-01 GREEN attempt 4 | `19 passed, 1 failed, 1 warning in 10.44s` | Direct-source extraction fixed wrapper issue; final static assertion targeted wrapper instead of `_handle_storyboard2_callback_impl` |
| 2026-08-26 | SPEC-01 final GREEN | Full file: `20 passed, 1 warning in 10.60s`, exit 0 | PASS; warning only google.genai deprecation |
| 2026-08-26 | SPEC-02 RED | `4 failed, 13 passed, 1 warning in 14.14s` | PASS as RED; `select_package` discarded compatibility for four unsupported/forged tiers |
| 2026-08-26 | SPEC-02 GREEN attempt 1 | `15 passed, 2 failed, 1 warning in 12.80s` | Service guard worked; Script/Storyboard contract still advertised hidden tier 200 |
| 2026-08-26 | SPEC-02 final GREEN | `17 passed, 1 warning in 11.07s`, exit 0 | PASS; 10 valid Video AI tiers and all invalid tier guards verified |
| 2026-08-26 | SPEC-03 compile | `py_compile bot.py services/video_tail9.py services/product_video_owner_recovery.py`, exit 0 | PASS |
| 2026-08-26 | SPEC-03 branch regression | `79 passed, 11 failed, 1 warning in 22.03s` | Compared to baseline before classification |
| 2026-08-26 | SPEC-03 origin/main baseline | Detached `cd4acb8`: `16 passed, 11 failed in 3.14s`, same 11 test names | NEW_FAILURES=0; old contract tests remain stale |
| 2026-08-26 | SPEC-03 audio/mux | Five selectors pass; one real-FFmpeg selector harness-failed with WinError 6 before spawn; replacement pure comparator `1 passed in 0.47s` | Source policy PASS; real media proof deferred to live artifact |
| 2026-08-26 | SPEC-01 final after durability review | `21 passed, 1 warning in 10.49s`, exit 0 | PASS on exact pre-push source |
| 2026-08-26 | Final pre-push compile | `py_compile bot.py services/video_tail9.py services/product_video_owner_recovery.py`, exit 0 | PASS on exact pre-push source |
| 2026-08-26 | Post-rebase focused gate | Rebased cleanly onto `origin/main 371a422`; manual + quality files `38 passed, 1 warning in 483.56s` | PASS; warning only google.genai deprecation |
| 2026-08-26 | Post-rebase compile/diff | Three runtime files compile exit 0; `git diff --check origin/main...HEAD` exit 0 | PASS; branch is exactly two commits ahead before this evidence update |
| 2026-08-26 | Rebase after SubDub PR #889 | Rebased cleanly onto `origin/main f16fb75`; combined gate `38 passed, 1 warning in 758.99s`; compile 3 runtime files exit 0 | PASS; warning only google.genai deprecation |
| 2026-08-26 | SPEC-03 Frame/Storyboard newline RED | Focused source selector: `1 failed, 2 warnings in 0.88s`; all 8 locked renderers reported as offenders | VALID RED; literal backslash-n reproduced |
| 2026-08-26 | SPEC-03 Frame/Storyboard newline GREEN | Same focused selector: `1 passed, 1 warning in 0.81s`; measured escaped separator count is 0 in all 8 renderers | PASS; only separators changed |
| 2026-08-26 | SPEC-01 Tail order RED | Dependency-complete selectors: `2 failed, 3 warnings in 760.76s`; invoice callback was `confirm|submit` and skipped the Confirm screen | VALID RED; source remained unchanged during RED |
| 2026-08-26 | SPEC-01 Tail order GREEN | Lightweight source contract: `1 passed, 1 warning in 0.74s`; invoice now opens Confirm, Quality Back returns Review, and long-form Confirm no longer auto-submits | PASS; three callback edges changed |
| 2026-08-26 | Final focused source gate after recovery | Manual Tail + 10-tier quality + newline/order + rendered Confirm: `42 passed, 2 warnings in 519.56s` | PASS; warnings are dependency/cache only |
| 2026-08-26 | Final compile after recovery | `py_compile bot.py services/video_tail9.py services/product_video_owner_recovery.py`, exit 0 | PASS on final source |
| 2026-08-26 | Post-rebase add-on materialization gate | Nine source-only selectors: `9 passed, 1 warning in 2.94s` | PASS; Tail -> handoff -> worker contract and fail-closed-before-provider covered |
| 2026-08-26 | Rebase after SubDub PR #890 | Rebased cleanly onto `origin/main edf4320`; focused gate `42 passed, 2 warnings in 567.32s`; post-rebase compile 3 runtime files exit 0; diff-check exit 0 | PASS; ready to force-with-lease PR #888 |
| 2026-08-26 | PV-L01 live attempt 1 on runtime `a5c1fe1` | Exact scenario entered through Video theo trend -> Tu nhap trend; traceback `Message.edit_message_text` at `safe_edit_or_send_long_html` before Add-on render | FAIL REOPENED; project/job/outbox/transaction deltas all 0 after 19:37:30 |
| 2026-08-26 | PV-L01 render hotfix RED | Focused behavior selector: `1 failed, 2 warnings in 0.86s`; normal Message reached CallbackQuery edit renderer | VALID RED; production traceback reproduced without provider |
| 2026-08-26 | PV-L01 render hotfix GREEN | Message reply + CallbackQuery edit + newline/Tail locks: `5 passed, 1 warning in 1.40s` | PASS; one guarded dispatch branch, provider/wallet unchanged |
| 2026-08-26 | PV-L01 live attempt 3 on runtime `c9278bc` | Re-entered fresh pending state after deploy; Add-on rendered, subtitle detail showed enabled, but `Xong phu de` rehydrated Add-on as disabled | FAIL REOPENED; stopped before Add-on completion/provider/job |
| 2026-08-26 | PV-L01 scene3 add-on persistence RED/GREEN | RED `KeyError subtitles` in saved scene3 host; final focused gate `6 passed, 1 warning in 1.41s` | PASS; Tail postprocessing merged into authoritative scene3 host |
| 2026-08-26 | PV-L01 Review -> Quality live failure | Review saved 2 scenes + subtitle, but oversize Quality HTML split inside `<code>`; Telegram edit timed out and HTML fallback parse failed | FAIL REOPENED; stopped before package/provider/job |
| 2026-08-26 | PV-L01 long HTML RED/GREEN | RED `oversize HTML reached direct edit path`; final helper + long-reply gate `8 passed, 1 warning in 1044.46s` | PASS; oversize HTML converts to plain before exact chunking |
| 2026-08-26 | PV-L01 submit callback live failure | Confirm screen was correct, but `confirm|submit` stopped at execution-preflight `query.answer()` with Telegram `ConnectTimeout`; DB remained project/job/outbox 24/20/19 | FAIL REOPENED; no admission/provider/wallet action |
| 2026-08-26 | PV-L01 submit ack RED/GREEN | RED: best-effort ack helper absent; final Message/Tail/ack gate `8 passed, 1 warning in 2.20s` | PASS; exact execution-preflight acknowledgement is non-blocking |
| 2026-08-26 | PV-L01 submit ack ship | PR #894 merged as `6157707`; GitHub recorded zero check-runs for that merge push | MERGED, NOT DEPLOYED; evidence-only follow-up push required |
| 2026-08-26 | PV-L01 submit ack live traceback on `fd26e30` | Best-effort helper was accidentally decorated with handler guard; submit raised missing `context`, DB remained project/job/outbox 24/20/19 | FAIL REOPENED; no admission/provider/wallet action |
| 2026-08-26 | PV-L01 ack decorator RED/GREEN | Source RED proved guard wrapped helper instead of handler; final helper/Tail gate `9 passed, 1 warning in 1.92s` | PASS; decorator restored to `handle_video_tail_callback` only |
| 2026-08-27 | Post-SubDub-main Product Video gate attempt | Bundled Python stopped at collection after `1577.39s`: `ModuleNotFoundError: telegram` | ENV INVALID; zero test assertions accepted, source unchanged |
| 2026-08-27 | Protected submit baseline classification | Exact selector failed on both Product Video SHA `21a8672` and shared main `3fc190c` with missing `get_user_language` in the AST-extracted test namespace | TEST HARNESS BASELINE; production callback path was not the failure |
| 2026-08-27 | Test-harness correction GREEN | Exact selector `1 passed in 0.71s`; full PV-L01/source-proof scope `57 passed, 2 warnings in 14.09s` | PASS; only test namespace dependencies added, no production byte changed |
| 2026-08-27 | Post-main compile/diff | `py_compile bot.py services/video_tail9.py services/product_video_owner_recovery.py`: `PY_COMPILE_EXIT=0`; `git diff --check`: exit 0 (LF/CRLF warning only) | PASS on shared main base `3fc190c` |
| 2026-08-27 | Rebase after SubDub PR #899 | Rebased test-only evidence commit cleanly onto shared main `397ca576`; same focused scope `57 passed, 2 warnings in 15.63s` | PASS; PR #900 remains draft and does not merge/deploy during SubDub live ownership |
| 2026-08-27 | PV-L01 fresh Tail on runtime `397ca576` | Manual text entered Add-on directly; subtitle auto/source-language persisted; transition coverage `1/1`; Review showed 2 scenes/16s; Quality selected `Nhanh gọn 80 Xu/scene`; Invoice/Confirm showed Owner no-charge | Tail flow PASS through the one-and-only final submit click |
| 2026-08-27 | PV-L01 live submit RED | Status terminal-before-admission: `trend_source_or_sample_missing`, job code `Chưa tạo`, progress 0%, scenes 0/2, no provider action | VALID LIVE RED; DB remained project/job/outbox `24/20/19`, owner transactions `0`, credit events `1`, balance/spent `200/0` |
| 2026-08-27 | PV-L01 manual-trend source RED/GREEN | RED `1 failed in 12.17s` with `trend_source={}`; minimal source fix persisted `source_type=user_topic` and aligned Flow7 with existing Flow6 rule; GREEN `1 passed in 631.07s` | PASS; no provider/wallet/runtime side effect in tests |
| 2026-08-27 | PV-L01 protected source gate | Manual/Tail/render/quality/add-on/idempotency/owner-no-charge plus old Flow6/Flow7 source contracts: `60 passed, 2 warnings in 15.59s`; compile four runtime files `PY_COMPILE_EXIT=0`; diff-check exit 0 | SHIP READY for same-case rerun; warnings only dependency deprecations/line endings |
| 2026-08-27 | Rebase after unrelated PR #901 | Rebased two Product Video commits cleanly onto `origin/main 8ccfe8f`; protected scope rerun with authoritative output `60 passed, 2 warnings in 14.54s`; diff-check remains 0 | PASS; PR #901 touched landing/docs/tester case files only, no Product Video runtime overlap |
| 2026-08-27 | PR #900 deploy/runtime | PR #900 squash merge `085a1aaa3545911ab8cd3ac1a69ab05c18b68b66`; deploy run `33006092441` SUCCESS in `9m23s`; bot+owner worker same SHA; generation `d7dc8fa031f5445eb2dcf008944ba5f5`, heartbeat persisted yes/reject empty | DEPLOYED and runtime-ready |
| 2026-08-27 | PV-L01 provider admission | Same Tail on `085a1aaa` created exactly project/job/outbox `25/21/20`, request `VID-20260826-5F299E`, and exactly two ShopAIKey task ids; charged Xu 0 | Manual source blocker fixed; provider admission PASS, artifact still pending |
| 2026-08-27 | PV-L01 terminal provider failure loop | Both scene tasks returned `FAILURE` with `provider_failed_result_url_invalid`; no clip/result URL; job remained processing/queued and owner worker raised `real_video_renderer_unavailable`; attempts reached `79` despite max `3`; owner worker stopped separately, bot remained active, charged Xu 0 | VALID LIVE RED; no new submit/job and no wallet mutation |
| 2026-08-27 | Terminal claim-loop RED/GREEN | Exact DB integration RED: ledger terminalized only after current failed summary, but claim left DB `processing`; minimal claim transaction now persists job/project `failed_no_charge`, outbox `terminal_failed`, clears leases and preserves charged Xu 0; focused GREEN `1 passed in 8.78s` | PASS; no fallback/resubmit/provider code added |
| 2026-08-27 | Terminal claim-loop protected gate | Existing-task poll-only recovery, active/pending scene truth, all-scenes-exhausted terminal, outbox watchdog, lease, cancellation and no-resubmit coverage: `10 passed, 1 warning in 11.39s`; compile `services/remote_worker_api.py services/video_project_queue.py remote_worker.py bot.py` exit 0; diff-check exit 0 | SHIP READY; owner worker remains intentionally stopped until deploy |
| 2026-08-27 | ShopAIKey balance/quota forensic | Usage HTTP 200: total 351.00 USD, used 291.71 USD, remaining 59.29 USD. Both PV-L01 tasks poll HTTP 200 but payload `FAILURE`, progress 100%, inner `429 RESOURCE_EXHAUSTED / PUBLIC_ERROR_USER_QUOTA_REACHED`, no result URL | ROOT CAUSE LOCKED; balance is not exhausted; provider calls 0 during forensic |
| 2026-08-27 | Key4U domain and live price audit | `.shop` TLS verify failed on VPS; `.vn` verify code 0. Read-only live sources: ShopAIKey `/pricing`, Key4U `/api/pricing_v3` and `/v1/models` | DOMAIN/PRICE SOURCE LOCKED; no paid submit |
| 2026-08-27 | Price-route map durability | Repo map + `D:\\TOANAAS\\kiến thức\\PRODUCT_VIDEO_PRICE_ROUTE_MAP_20260827.md` SHA256 `69A4EBC43A2FC9B0C3B5612765F6B2574571228C5F079B982B865A9E223990CA`; JSON covers 10 tiers, customer prices 80..2360 Xu, exact 2-scene totals, six family contract URLs and three live endpoint ids | PASS; Kling per-second unit and negative margins recorded |
| 2026-08-27 | Domain/price/quota and family contract RED/GREEN | Initial RED `4 failed`; family wire RED `4 failed`; final Product Video/provider gate `49 passed, 1 deselected`; Key4U domain gate `31 passed, 36 deselected` | PASS; deselected case is pre-existing tier-700 product-scope assertion outside this correction |
| 2026-08-27 | Baseline comparison | Clean `origin/main 43d8664` full music/provider file: 10 failed/35 passed. Branch: same 9 baseline failures/36 passed after `.vn` correction | NEW_FAILURES=0; one baseline URL failure fixed |
| 2026-08-27 | Compile/diff gate | `py_compile` on 8 runtime files exit 0; `git diff --check` exit 0 | SOURCE SHIP READY; deploy/live still pending |
| 2026-08-27 | Documentation scope recovery | Restored both existing `TAI-LIEU` files byte-for-byte through their previous final sections, then appended only the measured Product Video provider/pricing addenda | PASS; Landing/SubDub/history content preserved, no wholesale replacement remains |
| 2026-08-27 | Current-map runtime authority | `services/video_ai_real_pricing.py` exports runtime `provider_priority/provider_costs` from `config/product_video_price_route_map_20260827.json`; the 11/08 rows remain only under explicit `legacy_provider_*` fields | PASS; fixed customer prices are not recomputed from provider costs |
| 2026-08-27 | Primary contract readback | Key4U docs verified VEO `/v1/videos`, Kling `/kling/v1/videos/text2video`, Hailuo submit/query, plus `.vn` DNS/TLS; pricing endpoint ids `gygkmi`, `m0kp1x`, `1au654` map to those exact POST paths; all evidence persisted in the JSON map | PASS; zero paid submit and zero secret mutation |
| 2026-08-27 | Kling v3 audio wire RED/GREEN | Official-compatible contract requires `sound` enum `on`/`off`; RED `1 failed` because runtime emitted boolean; minimal wire normalization GREEN `3 passed`, then provider/pricing gate `77 passed, 1 deselected in 21.52s` | PASS; internal catalog bool remains unchanged, only outbound Key4U Kling payload normalized |
| 2026-08-27 | Final provider/pricing gate | Current branch `77 passed, 1 deselected in 21.52s`; deselected tier-700 scope selector fails identically on clean `43d8664`. Shared voice/music branch `9 failed/36 passed` vs clean baseline `10 failed/35 passed`; changed-domain selectors `12 passed` | NEW_FAILURES=0; one `.shop` URL baseline failure fixed |
| 2026-08-27 | Final static/scope gate | `py_compile` 8 runtime/dependency files exit 0; JSON contract PASS; `git diff --check` exit 0; secret scan PASS; forbidden wallet/PayOS/SubDub/onboarding/PWA paths 0 | SOURCE SHIP READY on pre-rebase bytes; post-rebase gate still required |
| 2026-08-27 | Post-SubDub-#904 rebase gate | Rebased cleanly onto exact `origin/main 8d23bbf`; provider/pricing `77 passed, 1 baseline deselected`; current Tail v18/manual/10-tier source acceptance `66 passed`; compile 8 runtime/dependency files and diff-check exit 0 | PASS; branch remains exactly one Product Video commit, no conflict or shared-runtime drift |
| 2026-08-27 | PV-L01 exact-price fallback safety | Spend-safety + quota parser + exact-price fallback selectors `11 passed in 11.18s`: in-progress primary suppresses fallback; paid fallback requires explicit confirmation; confirmed retry permits exactly one Key4U submit; quote remains 144 Xu and charged Xu 0 | PASS; same-flow live still required after deploy |
| 2026-08-27 | Media fixture readiness | Generated and hashed four 1672x941 PNG fixtures for PV-L04/PV-L06; selected two measured source MP4s for PV-L05/PV-L09 with H.264 + AAC and durable SHA256 manifest under workspace `artifacts/product-video-live-fixtures/` | PASS; files are evidence inputs and are not committed into production Git |
| 2026-08-27 | PR #905 deploy/runtime | PR #905 squash merged as `21022ed724aa605f1b90dbb35e140a8dbba9e09b`; deploy run `33051106470` SUCCESS; bot PID `256171`, owner worker PID `253437`, generation `d3e9f65983b3497697f562c0d72b6350`, health 200 | DEPLOYED; LIVE artifact still required |
| 2026-08-27 | PV-L01 Tail/admission rerun on `21022ed` | Codex Browser only; exact manual scenario -> Add-on subtitle + transition -> Review -> `Nhanh gon 80 Xu/canh`; invoice 144 Xu; one final submit created request `VID-20260827-87B9C2`, project `26`, job `22`, outbox `21` | FLOW + ADD-ON + ADMISSION PASS; no duplicate submit; Owner no-charge |
| 2026-08-27 | PV-L01 job #22 terminal | Two ShopAIKey `veo3.1-fast` scene tasks were accepted, both remained authoritative `NOT_START`; worker converted the pending state to `real_video_renderer_unavailable`, reclaimed eight times, then job terminal `provider_not_start`; 0/2 clips, charged Xu 0 | VALID LIVE RED; artifact/delivery remain open |
| 2026-08-27 | Job #22 pending/controlled-fallback RED | Exact new selector `4 failed, 280 warnings in 12.39s`: pending reason collapsed to renderer unavailable; durable seam suppressed the Owner no-charge exact-quote Key4U fallback | VALID RED; no production provider or wallet action |
| 2026-08-27 | Job #22 pending/controlled-fallback GREEN | Focused selector `6 passed in 11.02s`; worker preserves `provider_not_start`; text `started_at` yields measured elapsed; final-confirmed exact quote can use exactly one idempotent Key4U fallback per scene; missing confirm or mismatched quote stays blocked | PASS |
| 2026-08-27 | Job #22 protected gate | Pending worker, NOT_START/stall, spend safety, durable no-resubmit, restart recovery: `51 passed, 2 deselected in 18.78s`; the two deselected comparator failures reproduce identically on clean `origin/main 21022ed` | NEW_FAILURES=0 |
| 2026-08-27 | Job #22 compile/diff | `py_compile bot.py remote_worker.py services/video_real_render_connector.py` exit 0; `git diff --check` exit 0 (line-ending warnings only) | SOURCE SHIP READY; same-case live rerun still mandatory |
| 2026-08-27 | Job #22 correction ship/runtime | PR #906 squash merged as `74655192cf6f78574f7a41c085820dcbff107b00`; deploy run `33063575033` SUCCESS in `7m17s`; bot PID `266942`, worker PID `267762`; generation `1df006444c88481880190c66f302b869`, authenticated/persisted, reject empty | DEPLOYED and runtime-ready |
| 2026-08-27 | PV-L01 live rerun job #23 | Exact Tail via Codex Browser created request `VID-20260827-C26899`, project `27`, job `23`, outbox `22`; elapsed reached `66s` and stall threshold `60s`, but persisted `provider_order=[shopaikey_video]` hid locally-ready Key4U and returned `no_fallback_provider` | VALID LIVE RED; bounded recovery `3/3`, terminal failed_no_charge, charged Xu 0 |
| 2026-08-27 | Job #23 candidate recovery RED/GREEN | Corrected RED used live payload shape: job-level provider chain collapsed, durable marker/decision null, persisted `automatic_fallback_allowed=false`; policy now honors that fail-closed flag and recovers only capability-ready `key4u_video` when final confirm/exact quote/task/no-delivery/no-charge/count=0 gates all pass | Focused GREEN `7 passed in 9.87s` |
| 2026-08-27 | Job #23 protected gate | Pending worker, NOT_START/stall, durable no-resubmit, restart recovery and spend safety | `52 passed, 2 baseline deselected in 15.36s`; NEW_FAILURES=0 |
| 2026-08-27 | Job #23 correction ship/runtime | PR #907 squash merged as `124468aaf73ab002c9fa6c8e003485573b2f4ede`; deploy run `33066231410` SUCCESS in `9m51s`; bot/worker same SHA; worker PID `271183`, generation `4e6e1b5a18c941e48d32dc4da4b3d0d4`, authenticated/persisted, reject empty | DEPLOYED and runtime-ready |
| 2026-08-27 | PV-L01 live rerun job #24 | Exact Tail via Codex Browser created request `VID-20260827-1DA4A5`, project `28`, job `24`, outbox `23`; summary elapsed reached `61s/60s`, but last scene authority was only `53s`; server claim gate terminalized before connector could run controlled Key4U fallback | VALID LIVE RED; terminal failed_no_charge, charged Xu 0 |
| 2026-08-27 | Job #24 claim-gate RED/GREEN | Corrected RED reproduced `_claim_video_render_candidate` returning no job after ledger `failed_no_charge`; thin pre-claim adapter selects only the summary-authoritative `fallback_scene_index`, calls canonical stall policy, persists its Key4U/idempotency decision, then re-evaluates ledger | Focused GREEN `8 passed in 13.62s` |
| 2026-08-27 | Job #24 protected gate | Pending/NOT_START, claim terminalization, one-scene controlled fallback, durable primary no-resubmit, bounded recovery and spend safety | `54 passed, 2 baseline deselected in 47.56s`; NEW_FAILURES=0 |
| 2026-08-27 | Job #24 correction ship/runtime | PR #909 squash merged as `f16d74a1b23188625810113ceb24ee2028d857c9`; deploy run `33073326136` SUCCESS; bot/owner worker same SHA; generation `16424e56bf634c0d8d3134d6e50bde73`, heartbeat accepted/reject empty | DEPLOYED and runtime-ready |
| 2026-08-27 | PV-L01 live rerun job #25 | Exact Tail via Codex Browser: manual trend -> source subtitle -> transition `1/1` -> Review `2 scenes/16s/9:16` -> `Nhanh gọn 80 Xu/cảnh`; invoice `144 Xu`; one submit created request `VID-20260827-2803A3`, project `29`, job `25`, outbox `24` | FLOW/ADD-ON/ADMISSION PASS; no duplicate submit; Owner no-charge |
| 2026-08-27 | PV-L01 job #25 real artifact | Both primary scene tasks reached `SUCCESS 100%`; final `/tmp/toanaas_multiscene_blackbox/product-video-25-c7eb882db394/final_output.mp4` is 1,660,101 bytes, H.264 540x960 + AAC stereo 48kHz, duration 16.000s | ARTIFACT VALID; delivery still blocked by reused-manifest ledger regression |
| 2026-08-27 | Job #25 manifest-reuse RED/GREEN | RED `1 failed in 0.85s`: `scene_coverage_valid_bool=False`; one-condition production fix; GREEN `1 passed in 0.73s`; protected scene-ledger/recovery batch `21 passed in 3.65s` | SOURCE PASS; PR/deploy/live delivery still required |
| 2026-08-27 | Job #25 delivery after PR #910 | Deploy `33078757523` SUCCESS; bot/worker `82ffb117...`; job `25` completed 100%, delivery message `27576`, one delivery attempt, charged Xu 0, transactions 0 | DELIVERY PASS, but case still FAIL on visual/add-on acceptance |
| 2026-08-27 | Job #25 delivered artifact probe | `1,660,101` bytes; SHA256 `fd48b933...`; H.264 540x960 + AAC stereo 48kHz; duration 16.000s; mean/max audio `-24.4/-3.1 dB` | MEDIA VALID; Owner screenshot proves black letterbox bars |
| 2026-08-27 | Product Video vertical cover RED/GREEN | RED `2 failed, 1 passed in 0.83s`; Product-only cover fix; GREEN `3 passed in 1.01s` | Source PASS; same-fixture live required |
| 2026-08-27 | Strict Add-on owner RED | Scene3/manual Trend Tail produced no strict contract: `1 failed in 1.34s` at missing `contract_version` | VALID RED matching job #25 subtitle degrade |
| 2026-08-27 | Quality/Confirm ACK timeout RED/GREEN | RED `11 failed in 5.03s`; Tail ACK best-effort; GREEN `11 passed in 4.51s`; Submit-to-Status blocked path `1 passed in 0.76s` | Flow source PASS; UI bytes unchanged |
| 2026-08-27 | Full menu Tail-to-Status matrix | RED PV-L08 missing executor owner: `1 failed, 9 passed`; alias fix; GREEN `10 passed in 0.68s` | All nine acceptance lanes have Invoice/Confirm/Status contracts; live rows remain pending |
| 2026-08-28 | Final source acceptance | ACK/10-tier/Confirm/Status + 9 lane + UI byte-lock + cover + strict Add-on + Trend4: `45 passed in 5.88s`; full Product Video output `24 passed in 12.54s` | PASS on current local bytes |
| 2026-08-28 | Protected baseline comparison | Branch old Tail suite `41 passed, 15 failed in 9.04s`; clean `origin/main` same 15 IDs `41 passed, 15 failed in 9.02s` | `NEW_FAILURES=0`; stale tests request superseded UI and remain untouched |
| 2026-08-28 | Protected focused regressions | Quality/manual `39 passed in 8.85s`; Trend/scene ledger `52 passed in 5.56s`; compile 5 runtime files exit 0 | SOURCE REVIEW READY; post-rebase/live pending |
| 2026-08-28 | Fresh resumed source gate on local `98de28d` | Five-file branch run `72 passed, 4 failed in 30.68s`; isolated parent `bc422d5` with the same tests `54 passed, 22 failed in 811.91s`; all four branch failures are the same stale UI/tier IDs present on the parent, so `NEW_FAILURES=0` | BASELINE CLASSIFIED; no UI/test assertion was changed |
| 2026-08-28 | Fresh clean acceptance and protected comparators | Same five-file acceptance with the four measured baseline-stale IDs deselected: `72 passed, 4 deselected in 25.22s`; quality/manual `39 passed in 8.17s`; Trend/scene expanded `56 passed in 12.13s`; full Product Video output `24 passed in 16.20s` | SOURCE PASS on pre-rebase bytes |
| 2026-08-28 | Fresh compile/scope gate | `py_compile` five runtime files exit 0; `git diff --check HEAD^..HEAD` exit 0; forbidden-path hits 0; secret-pattern hits 0; 14 completed UI functions remained byte-locked in the acceptance batch | SOURCE PASS; post-SubDub fetch/rebase, ship, deploy and live matrix remain open |
| 2026-08-28 | Post-rebase gate on exact `origin/main a9471b6` | Commit rebased cleanly with prior `bc422d5` skipped as already upstream; unified 11-file gate `163 passed, 4 measured-baseline deselected in 596.32s`; `py_compile` five runtime files exit 0 | POST-REBASE SOURCE PASS; push/PR/deploy/runtime/live remain open |
| 2026-08-28 | PR #913 ship/runtime | PR #913 squash merged `ccf9523613418dfd37535f14901173624d5cbc3e`; compile run `33105132268` SUCCESS; deploy run `33105339710` SUCCESS in `4m17s`; bot+owner worker exact SHA; generation `91016743...` accepted/persisted/reject empty | DEPLOYED; PV-L01 and Trend4 live output gates remain distinct |
| 2026-08-28 | Trend4 first VPS refresh + Facebook RED | Refresh inserted `203`, media `4`, Facebook `0`, YouTube `100`, TikTok `99`, next run `+7 days`, paid provider `0`; public diagnostic returned `57` items for `Facebook Reels Vietnam`; RED `1 failed in 8.42s` on old site-only query | VALID LIVE RED limited to Facebook source query |
| 2026-08-28 | Trend4 Facebook minimal GREEN | One registry line changed; Trend4 + protected Trend2/Trend3 `37 passed in 9.95s`; `py_compile services/video_trend_catalog.py` exit 0 | SOURCE PASS; ship/deploy and four-group live refresh remain open |
