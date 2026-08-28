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

### SPEC-05: Distinct Two-Scene Product/Lane LIVE Matrix

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
