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
- [ ] Local Python/FFmpeg available to Product Video.
- [ ] LIVE/CHROME available to Product Video.
- [ ] VPS/DEPLOY available to Product Video.
- [x] No wallet, PayOS, ENV, secret, destructive DB, onboarding, PWA, or SubDub changes allowed.

Current shared-resource owner: **SubDub Auto**.

## Ordered Specs

### SPEC-01: Manual/Text Lane -> Shared Tail

- [x] Audit current routes from public buttons through pending text handlers.
- [x] Prove current behavior contradicts the Owner contract.
- [x] RED: exact customer text is preserved for every supported manual lane.
- [x] RED: a deterministic two-scene plan exists with zero provider calls.
- [x] RED: next visible screen is `addon`, not Profile/Content Lock/Production Bible/suggestions.
- [x] RED: Tail order is `addon -> review -> quality -> invoice -> confirm -> status`.
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

| Tier | Selector GREEN | Two-scene LIVE | Artifact/Receipt Evidence |
|---:|:---:|:---:|---|
| 200 | [x] | [ ] | source GREEN; live pending |
| 300 | [x] | [ ] | source GREEN; live pending |
| 400 | [x] | [ ] | source GREEN; live pending |
| 500 | [x] | [ ] | source GREEN; live pending |
| 600 | [x] | [ ] | source GREEN; live pending |
| 700 | [x] | [ ] | source GREEN; live pending |
| 800 | [x] | [ ] | source GREEN; live pending |
| 1000 | [x] | [ ] | source GREEN; live pending |
| 1200 | [x] | [ ] | source GREEN; live pending |
| 1500 | [x] | [ ] | source GREEN; live pending |

### SPEC-03: Source Regression Gate

- [x] Focused Product Video lane/Tail tests pass.
- [x] Quality matrix tests pass.
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
| Video theo trend / manual | pending | [ ] | [ ] | [ ] |
| Video AI chan that / prompt manual | pending | [ ] | [ ] | [ ] |
| Kich ban -> Video / manual | pending | [ ] | [ ] | [ ] |
| Ghep anh thanh video / custom | pending | [ ] | [ ] | [ ] |
| Video tu quay / custom direction | pending | [ ] | [ ] | [ ] |
| Storyboard / manual | pending | [ ] | [ ] | [ ] |
| Video dai tap / manual | pending | [ ] | [ ] | [ ] |
| Y tuong video / manual handoff | pending | [ ] | [ ] | [ ] |
| Chinh sua Video / two-scene input | pending | [ ] | [ ] | [ ] |

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
