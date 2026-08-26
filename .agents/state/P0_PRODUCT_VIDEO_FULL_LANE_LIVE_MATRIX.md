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
- [ ] RED: exact customer text is preserved for every supported manual lane.
- [ ] RED: a deterministic two-scene plan exists with zero provider calls.
- [ ] RED: next visible screen is `addon`, not Profile/Content Lock/Production Bible/suggestions.
- [ ] RED: Tail order is `addon -> review -> quality -> invoice -> confirm -> status`.
- [ ] RED: back targets stay inside the same product and state.
- [ ] Minimal production fix.
- [ ] Focused GREEN evidence.

Current source evidence:

| Product lane | Current target after manual text | Contract result |
|---|---|---|
| Video theo trend / `trend_manual_input` | `start_public_video_scene2_step` | FAIL |
| Video AI chan that / UIFLOW3 `manual_content` | `content_lock -> production_bible` | FAIL |
| Video AI chan that / `awaiting_prompt_text` | `start_public_video_scene2_step` | FAIL |
| Kich ban -> Video / `script_manual_topic` | `start_public_video_scene2_step` | FAIL |
| Storyboard / `storyboard_manual_input` | `start_public_video_scene2_step` | FAIL |
| Video dai tap / `film_manual_topic` | `start_public_video_scene2_step` | FAIL |
| Ghep anh thanh video / custom topic | generated suggestions | FAIL |
| Video tu quay / custom direction | generated suggestions | FAIL |
| Y tuong video / manual topic | generated suggestions | FAIL |

### SPEC-02: Quality Selector Matrix

- [ ] Every visible quality button has a registered callback.
- [ ] Selecting a tier preserves the exact tier in review, invoice, confirmation, admission, job, and manifest.
- [ ] Unsupported capability blocks before admission with no provider call and no charge.
- [ ] Focused GREEN evidence for every tier id.

Video AI Real public tiers:

| Tier | Selector GREEN | Two-scene LIVE | Artifact/Receipt Evidence |
|---:|:---:|:---:|---|
| 200 | [ ] | [ ] | pending |
| 300 | [ ] | [ ] | pending |
| 400 | [ ] | [ ] | pending |
| 500 | [ ] | [ ] | pending |
| 600 | [ ] | [ ] | pending |
| 700 | [ ] | [ ] | pending |
| 800 | [ ] | [ ] | pending |
| 1000 | [ ] | [ ] | pending |
| 1200 | [ ] | [ ] | pending |
| 1500 | [ ] | [ ] | pending |

### SPEC-03: Source Regression Gate

- [ ] Focused Product Video lane/Tail tests pass.
- [ ] Quality matrix tests pass.
- [ ] Back-stack, stale callback, duplicate confirm, read-only refresh, newline status, audio/final mux regressions pass.
- [ ] `python -m py_compile bot.py` passes.
- [ ] Touched runtime modules compile.
- [ ] `git diff --check` passes.
- [ ] Diff contains no protected-file or unrelated-flow changes.

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
