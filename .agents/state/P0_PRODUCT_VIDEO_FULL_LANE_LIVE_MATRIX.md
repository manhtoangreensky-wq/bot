# P0 Product Video Full-Lane Live Matrix

## Scope Stamp

- Product: **Product Video** only
- Codex task: `019efe1e-ee54-78e1-87c4-10db6e1e19e4`
- Repository: `manhtoangreensky-wq/bot`
- Branch: `fix/product-video-post-deploy-finalizer-recovery`
- Contract HEAD: `f4c022a0ee72b67bf28ea0766fed880bd8419b36`
- Contract main: `cd4acb8c10ad3b82f50f13a6faa114c30791fe51`
- SubDub task `019fbbfe-59b7-7ee2-b298-dea276813ce4` is **out of scope**. It only owns shared CPU/LIVE/CHROME/VPS resources until exact release markers.

## Execution Rule

For every spec, use this exact loop and do not skip or reorder it:

`READ -> CONTRACT -> RED -> MINIMAL FIX -> GREEN -> REVIEW -> EVIDENCE`

After all source specs are GREEN:

`ONE BRANCH -> PUSH -> ONE PR -> SQUASH MERGE -> DEPLOY -> RUNTIME VERIFY -> LIVE MATRIX`

If a live row fails, reopen only that spec, add a RED reproducer from the real failure, apply the smallest fix, rerun GREEN, ship, and repeat that same live row. Never mark a row complete from intent, HTTP 200, a queued state, or a provider task id.

## Resource Boundary

- [x] Source READ and contract work allowed.
- [x] Local Python/FFmpeg available to Product Video.
- [x] LIVE/CHROME available to Product Video.
- [x] VPS/DEPLOY available to Product Video.
- [x] No wallet, PayOS, ENV, secret, destructive DB, onboarding, PWA, or SubDub changes allowed.

Current shared-resource owner: **Product Video**.

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

- [ ] Measured report updated in this tracker.
- [ ] One scoped Product Video commit series pushed on this branch.
- [ ] One Product Video PR created and linked to this tracker.
- [ ] PR checks terminal GREEN.
- [ ] Squash merge SHA recorded.
- [ ] Deploy terminal result recorded.
- [ ] Bot and Product Video worker run the exact merge SHA.
- [ ] Worker generation heartbeat is accepted with no reject reason.
- [ ] Bot `getMe`/ONLINE and services active evidence recorded.

### SPEC-05: Distinct Two-Scene Product/Lane LIVE Matrix

Each row needs a different scenario or fixture, exact request/project/job/outbox identity, two scene outputs, final MP4 SHA256/bytes/codec/dimensions/duration, audio evidence when requested, add-on requested/materialized/applied proof, Telegram delivery message id, `charged_xu=0`, zero wallet transaction delta, and no duplicate submit/delivery.

| Product/lane | Distinct scenario | Flow + Add-on | Two-scene artifact | Delivery/0 Xu |
|---|---|:---:|:---:|:---:|
| Video theo trend / manual | PV-L01: quầy cà phê xe điện -> sinh viên nhận ly tái sử dụng | [ ] | [ ] | [ ] |
| Video AI chan that / prompt manual | PV-L02: Linh tạo bình gốm xanh -> nâng thành phẩm | [ ] | [ ] | [ ] |
| Kich ban -> Video / manual | PV-L03: 5 cảnh trà sen Tây Hồ | [ ] | [ ] | [ ] |
| Ghep anh thanh video / custom | PV-L04: 2 ảnh đồng hồ thủ công | [ ] | [ ] | [ ] |
| Video tu quay / custom direction | PV-L05: đầu bếp chợ Hội An -> bếp rooftop, giữ thái rau | [ ] | [ ] | [ ] |
| Storyboard / manual | PV-L06: robot gieo hạt -> mầm cây phát sáng | [ ] | [ ] | [ ] |
| Video dai tap / manual | PV-L07: thợ lặn tìm thư viện -> mở phòng sách phát sáng | [ ] | [ ] | [ ] |
| Y tuong video / manual handoff | PV-L08: xe cà phê điện -> barista phục vụ sinh viên | [ ] | [ ] | [ ] |
| Chinh sua Video / two-scene input | PV-L09: cắt gọn chợ đêm, giữ tiếng môi trường | [ ] | [ ] | [ ] |

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
