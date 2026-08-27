# P0 Product Video Full-Lane Live Matrix

## Scope Stamp

- Product: **Product Video** only
- Codex task: `019efe1e-ee54-78e1-87c4-10db6e1e19e4`
- Repository: `manhtoangreensky-wq/bot`
- Branch: `fix/product-video-terminal-provider-claim-loop`
- Current branch base: `8d23bbf1a09dee8d43896bad963a800d3dd25cda`
- SubDub task `019fbbfe-59b7-7ee2-b298-dea276813ce4` is **out of scope**. CPU is independent; only Telegram/Chrome/provider/VPS/deploy ownership is coordinated.

## Execution Rule

For every spec, use this exact loop and do not skip or reorder it:

`READ -> CONTRACT -> RED -> MINIMAL FIX -> GREEN -> REVIEW -> EVIDENCE`

After all source specs are GREEN:

`ONE BRANCH -> PUSH -> ONE PR -> SQUASH MERGE -> DEPLOY -> RUNTIME VERIFY -> LIVE MATRIX`

If a live row fails, reopen only that spec, add a RED reproducer from the real failure, apply the smallest fix, rerun GREEN, ship, and repeat that same live row. Never mark a row complete from intent, HTTP 200, a queued state, or a provider task id.

## Resource Boundary

- [x] Source READ and contract work allowed.
- [x] Local Python/FFmpeg available to Product Video.
- [x] LIVE/CHROME available to Product Video for the current PV-L01 failure loop.
- [x] VPS/DEPLOY available to Product Video for the current PV-L01 failure loop.
- [x] Owner approved only the Key4U `.vn` endpoint configuration needed for Product Video; no secret values are committed.
- [x] No wallet, PayOS, destructive DB, onboarding, PWA, or SubDub changes allowed.

Current shared-resource owner: **Product Video**. SubDub is static until exact Product Video release markers.

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
- [ ] PR merged and deployed at exact runtime SHA.
- [ ] Same PV-L01 flow delivers the required two-scene MP4 with audio/add-ons/receipt.

### SPEC-05: Distinct Two-Scene Product/Lane LIVE Matrix

Each row needs a different scenario or fixture, exact request/project/job/outbox identity, two scene outputs, final MP4 SHA256/bytes/codec/dimensions/duration, audio evidence when requested, add-on requested/materialized/applied proof, Telegram delivery message id, `charged_xu=0`, zero wallet transaction delta, and no duplicate submit/delivery.

| Product/lane | Distinct scenario | Flow + Add-on | Two-scene artifact | Delivery/0 Xu |
|---|---|:---:|:---:|:---:|
| Video theo trend / manual | PV-L01: quầy cà phê xe điện -> sinh viên nhận ly tái sử dụng | [ ] | [ ] | [ ] |
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
