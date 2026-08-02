# Video Edit Completion Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining truthful-navigation and execution gaps in the Vietnamese-first `videoedit|` product without changing Product Video, SubDub, Frame Video, Local Video Studio planning, billing, providers, or deployment.

**Architecture:** Keep the existing canonical `videoedit|` state and local FFmpeg executor. Add pure state-machine contracts for exact Review/Logo/Audio parents, require an explicit destructive transition from a composed manual plan to a separate split plan, and enforce the same split/manual, rights, duration, timing, and audio invariants in the bot, job writer, and worker. Extend real-media tests only for public operations whose current receipt cannot prove that the requested edit happened.

**Tech Stack:** Python 3.11, python-telegram-bot callbacks, SQLite job/outbox, FFmpeg/ffprobe, pytest.

---

## Scope and file map

- Modify `services/video_edit_state_machine.py`: exact Review Back, canonical `logo_options`/Split-warning screens, and `audio_reupload` callbacks.
- Modify `services/video_edit_capabilities.py`: keep deterministic internal capability IDs while making every `message_vi` result Vietnamese-first and free of implementation/provider vocabulary.
- Modify `bot.py`: Vietnamese goal-based copy, truthful audio-component copy, explicit manual-to-split reset, exact Back hierarchy, logo/watermark options, concat/audio confirmation truth, rights evidence, and mute/loudnorm compatibility.
- Modify `services/video_local_editing.py`: mixed-plan guard, final concatenated post-speed timing validation, rotated slow-zoom geometry, subtitle cue intersection, and mute summary.
- Modify `services/video_local_validation.py`: parse validated SRT cue windows without reading message bodies or external assets.
- Modify `services/video_editengine1.py`: reject mixed split/manual jobs and require durable local-free rights evidence.
- Modify `local_worker.py`: independently reject the same contradictions and re-probe downloaded source limits before execution.
- Modify focused `tests/test_p0_videoedit_*.py` files: RED/GREEN navigation, contract, worker, and real-media evidence.
- Do not modify Product Video, SubDub, Frame Video, `lvs27a`, `lvs27b`, provider adapters, wallet/PayOS, Railway/VPS, ENV, webhook, or top-level Video menu.

### Task 1: Exact Vietnamese navigation and truthful surfaces

- [ ] Add failing tests requiring `review_back_callback()` to return the saved immediate parent, `logo_options` to resume without re-upload, and `audio_upload` to canonicalize to `audio_reupload`.
- [ ] Run only those nodes; require failures caused by the hard-coded Review Back, missing logo callback, and manual alias.
- [ ] Implement the minimal state-machine mappings and handlers.
- [ ] Require the hub pair `✨ Chỉnh sửa theo mục tiêu → videoedit|ai`, informational audio-component labels prefixed with `ℹ️`, copy that says independent stem controls are not open, and `🖼 Logo / watermark ảnh → videoedit|logo`.
- [ ] Re-run the focused nodes and the existing callback-owner/backstack tests.

Commands:

```powershell
python -m pytest -q tests/test_p0_videoedit_canonical_navigation.py tests/test_p0_videoedit_back_hierarchy_adapter.py -k "review_back or logo_options or audio_reupload or vietnamese_pairs"
python -m pytest -q tests/test_p0_videoedit_canonical_bot_routes.py -k "audio or hub or logo or back"
```

### Task 2: Separate split plans without silent data loss

- [ ] Add failing callback tests showing that a manual operation plus `videoedit|split_from_manual` renders an explanation and preserves the current plan.
- [ ] Add the explicit pair `🧩 Bắt đầu kế hoạch chia riêng → videoedit|split_reset_manual`; only that callback clears manual operations/assets and enters Split.
- [ ] Add failing engine and worker tests requiring `local_free_split_manual_conflict` / `video_local_edit_split_manual_conflict` for a split payload containing any effective manual operation, concat source, logo source, or subtitle source.
- [ ] Implement one pure mixed-plan predicate reused by the engine and worker.
- [ ] Make split confirmation always describe source-audio preservation and never inherit manual mute/loudnorm copy.

Commands:

```powershell
python -m pytest -q tests/test_p0_videoedit_back_hierarchy_adapter.py -k "split"
python -m pytest -q tests/test_p0_videoedit_job_safety.py -k "split and manual"
python -m pytest -q tests/test_p0_videoedit_canonical_local_worker_receipt.py -k "split and manual"
```

### Task 3: Temporal, geometry, summary, and audio invariants

- [ ] Add failing unit tests for 90°/270° plus slow zoom retaining the rotated dimensions.
- [ ] Add failing tests that reject text wholly after the post-speed output, reject fade durations invalid after speed, and reject SRT files whose every cue is outside the output.
- [ ] Add failing tests that show `volume=0` in the public summary and nested concat `metadata.duration_ms` in the review estimate.
- [ ] Add callback tests proving mute clears loudnorm and loudnorm cannot be selected while muted.
- [ ] Revalidate fade/text/SRT timing after concat establishes the final timeline; never reject a valid appended-window overlay against only the primary source duration.
- [ ] Implement the minimal normalization, filter-size, summary, and callback changes; keep all FFmpeg commands argument-array based.

Commands:

```powershell
python -m pytest -q tests/test_p0_videoedit_canonical_local_runtime.py -k "slow_zoom or text or fade or subtitle or mute"
python -m pytest -q tests/test_p0_videoedit_canonical_bot_routes.py -k "concat or loudnorm or mute"
```

### Task 4: Durable rights and downloaded-source defense

- [ ] Add failing job tests requiring deterministic `rights_confirmation` evidence for local-free queue rows.
- [ ] Add failing worker tests requiring the same evidence and a fresh `probe_video_file` plus `validate_source_metadata` after Telegram download.
- [ ] Reuse the downloaded source duration for the final worker no-op guard so stale submitted metadata cannot turn a full-duration identity plan into an advertised edit.
- [ ] Stamp the confirming user, review revision, policy `video_edit_rights_v1`, and confirmation time only on the final `confirm_local` edge.
- [ ] Reject missing/foreign/corrupt evidence before queue insert and before FFmpeg; reject an over-duration downloaded source even if submitted metadata was stale.

Commands:

```powershell
python -m pytest -q tests/test_p0_videoedit_job_safety.py -k "rights"
python -m pytest -q tests/test_p0_videoedit_canonical_local_worker_receipt.py -k "rights or downloaded_source"
```

### Task 5: Real-media evidence and regression

- [ ] Add observable artifact checks for rotated slow zoom, split boundaries/gaps, logo position/opacity, text/SRT timing, speed/audio synchronization, volume/fade/loudnorm, sharpen/denoise, and representative color/vignette changes.
- [ ] Run focused Video Edit tests, the complete affected real-media/engine/worker/backstack set, callback-owner tests, and locked Product Video/SubDub/Local Video Studio isolation regressions.
- [ ] Lock the two clean-main comparator repairs introduced by the canonical local migration: the extracted `handle_video_tail_callback` test must inject the Video Edit legacy-tail owner and expect truthful upload recovery when no editor state/job exists; the shared Product Video submit test must require persisted-job `recover_submission` instead of the removed optimistic `mark_submitted` path.
- [ ] Run `py_compile` for changed modules/tests, `tokenize` plus narrow AST for `bot.py`, `git diff --check`, callback collision scan, secret/private-path scan, and changed-path scope audit.
- [ ] Obtain independent spec and code-quality review; fix only reproduced blockers with a fresh RED test.

Commands:

```powershell
python -m pytest -q tests/test_p0_videoedit_canonical_navigation.py tests/test_p0_videoedit_back_hierarchy_adapter.py tests/test_p0_videoedit_canonical_bot_routes.py tests/test_p0_videoedit_canonical_local_runtime.py tests/test_p0_videoedit_real_media_matrix.py tests/test_p0_videoedit_job_safety.py tests/test_p0_videoedit_canonical_local_worker_receipt.py
python -m py_compile local_worker.py services/video_edit_state_machine.py services/video_local_editing.py services/video_local_validation.py services/video_editengine1.py
git diff --check origin/main...HEAD
```

### Task 6: Ship, merge, and safe live gate

Before shipping, close the independent review blockers with focused RED/GREEN
evidence:

- [ ] Revalidate the latest-status row at the callback boundary: exact
  requesting user, exact `video_editengine1.WORKER_JOB_TYPE`, and positive
  worker-job ID. A malformed or foreign row must be indistinguishable from an
  empty state.
- [ ] Make the canonical status receipt lookup strictly SELECT-only. Opening
  or refreshing status must never call `ensure_schema()`, execute DDL, or begin
  a write transaction.
- [ ] Preserve the saved UI language across the complete six-stage status
  panel, public status, price, split-part progress, result/charge truth,
  refresh, empty/unavailable views, and Back controls.
- [ ] Treat a raw `delivered` progress stage, or a canonical delivered/charged
  row with incomplete receipt evidence, as delivery-uncertain: stages one
  through five complete, stage six warning, no false completion, resend, or
  charge.
- [ ] Log latest-status SQLite failures by exception category only. Never log
  raw exception text, SQL, filesystem paths, Telegram identifiers, or private
  state.

- [ ] Make every Split entry and re-upload persist one duration-independent
  canonical neutral manual plan; reject unknown or non-neutral Split fields at
  both engine and worker boundaries.
- [ ] Preserve actual manual work behind an explicit destructive reset while
  allowing an untouched full-duration intake plan to enter Split without a
  misleading warning. Bind the destructive button to a short deterministic
  fingerprint of the exact warned session, revision, manual plan, and asset
  records so a stale warning can never erase newer work; keep the click-time
  full-state CAS as the second race guard.
- [ ] Make source intake claims exclusive while a probe is in progress. Commit
  probe success, validation failure, exception recovery, and reply rollback
  only when the complete claimed state still wins; otherwise preserve and
  re-render the newer canonical screen (including job status) without writing
  any stale source data.
- [ ] Change the legacy-tail Review migration to full-state compare-and-set and
  re-render the winning state after a race; reconstruct a winning local
  `job_status` screen instead of falling back to the manual workspace.
- [ ] Make message-reply rollback a full-state CAS: if another asyncio task
  commits a newer Video Edit state while Telegram reply is pending, preserve
  that winner and do not let media-failure recovery write over it.
- [ ] Log stale-render failures by bounded exception category only; never emit
  raw exception detail, filesystem paths, SQL text, media identifiers, or
  private state while recovering the winning Video Edit screen.
- [ ] Persist `neutral_split_manual_plan()` at the moment a Split re-upload
  entry is opened, before the replacement media arrives; keep the same
  neutral contract after successful probing.
- [ ] Keep already-sent `video_tail|` buttons fail-closed, but stop emitting new
  shared-tail Video Edit callbacks or paid-package copy; all newly rendered
  actions must use the canonical `videoedit|` namespace.
- [ ] Bind rights evidence to the payload revision and bind manual plan asset
  placeholders to their Telegram asset records before queue insert and again
  in the worker.
- [ ] Translate public Vietnamese surfaces so internal execution terms are not
  exposed; keep implementation identifiers only in contracts, logs, and tests.

- [ ] Commit only approved Video Edit paths, push `fix/p0-videoedit-completion-hardening`, and open one non-draft PR against latest `main`.
- [ ] If `origin/main` advances, inspect every path; rebase only when the delta is unrelated or explicitly accepted.
- [ ] Record the exact pushed head and GitHub CI/check state honestly. After CI
  and every regression gate pass, merge with a merge commit (never squash) and
  record merge/new-main SHAs and two-parent ancestry.
- [ ] After merge, allow only a read-only/navigation live smoke. Do not
  manually deploy, change ENV, touch VPS/worker/webhook, upload production
  media, call providers/workers, create jobs, mutate wallet/Xu, or deliver
  media unless the owner opens a separate execution gate.

## Self-review

## Ordered CPU verification matrix (owner follow-up)

Run this matrix in the listed order after the CPU queue reaches Video Edit;
each row must have a focused test result and an exact Back-parent assertion
before moving to the next row. A green aggregate number is not sufficient if a
row is missing.

1. **Hub and lane admission:** `videoedit|hub`, the four existing actions,
   `videoedit|latest_status`, and the optional planning row; verify no status
   row leaks to the parent Video menu.
2. **Goal/AI lane:** `videoedit|ai` → source intake → `ai_suggestions` →
   `ai_settings`/prompt → local plan/review/confirmation/status; verify every
   Back callback returns to the screen that opened it and no provider path is
   entered before confirmation.
3. **Manual workspace parents:** `manual` → `workspace`, then independently
   exercise `cut`, `join`, `frame`, `transform`, `audio`, `color`, `overlay`,
   `effects`, `source_info`, and `review` with their immediate parents.
4. **Manual operations:** trim/remove-middle, split, concat/reorder, aspect/
   resolution, rotation/flip, speed, volume/mute/loudnorm, color presets,
   text overlay, logo/watermark position/opacity, SRT timing, sharpen/denoise,
   and representative effects. Each selected operation must be persisted in
   the plan, visible in review, and represented in the engine payload.
5. **Split isolation:** explicit manual→split warning, bound destructive reset,
   neutral plan on `videoedit|upload|split` before media arrives, split ranges/
   gaps, source-audio preservation, and rejection of mixed manual assets at
   engine and worker boundaries.
6. **Review/confirm/queue:** exact review parent, confirmation truth, rights
   evidence, duration/timing validation, idempotency, durable job/outbox row,
   and no duplicate submit/retry/replay.
7. **Engine/worker/receipt:** local FFmpeg argument construction, source and
   output probes, artifact receipt, delivery-uncertain handling, failure/no-
   charge truth, exact-job status refresh, and worker-side revalidation.
8. **Back and cross-product isolation:** every visible Back path, stale callback
   fail-closed behavior, callback-owner collision scan, and zero routes into
   Product Video, SubDub, Frame Video, Local Video Studio, or shared tails.

Only after all eight rows are green should the aggregate regression, compile,
scope, CI, merge, and safe live-navigation gates run.

The exact sequential commands, host-timeout budgets, corrected RouteEngine29
filenames, complete changed-file compile set, EOF tokenize, narrow AST, scope,
and safe release record are locked in
`docs/superpowers/plans/2026-08-02-video-edit-cpu-verification-matrix.md`.

## Owner-requirement traceability

| Requirement | Primary evidence |
| --- | --- |
| Preserve four hub actions; status row exactly once and not in parent Video menu | `tests/test_p0_video_edit3_compact_manual_flow.py`, `tests/test_p1_localvideostudio27b_public_ui.py`, `tests/test_p0_videoedit_latest_status_navigation.py` |
| Complete no-provider goal/AI lane with exact Back | `tests/test_p0_videoedit_review_parent_hardening.py::test_videoedit_complete_local_ai_lane_keeps_every_back_edge_and_creates_no_job` plus AI parent matrix |
| Every manual group and visible nested Back | `tests/test_p0_videoedit_back_hierarchy_adapter.py` workspace, nested-screen, source-info, review, confirmation, stale, and Split matrices |
| Direct manual choice persists and appears in Review | `test_videoedit_direct_manual_choices_persist_and_are_visible_in_review`; complex text/SRT/concat/effects/trim/Split cases remain in focused runtime and real-media suites |
| Logo/watermark position, opacity, fixed-scale truth | logo upload/options test, queued-plan identity test, and real-media logo artifact tests; no public scale callback is permitted |
| Split never silently mixes or destroys manual work | destructive-reset token/CAS tests, neutral re-upload test, engine/worker mixed-plan rejection, and gapped real-media Split evidence |
| Rights, confirmation, queue, idempotency, and zero-price truth | `tests/test_p0_videoedit_job_safety.py`, `tests/test_p0_videoedit_local_free_job.py`, confirmation/duplicate callback tests |
| Local engine, worker, MP4 validation, receipt, and delivery uncertainty | canonical runtime/worker receipt, split checkpoint, real-media, and latest-status suites |
| Latest owned task reopen, six-stage language, privacy, duplicate-read safety | `tests/test_p0_videoedit_latest_status_navigation.py`; task history is intentionally absent |
| Callback ownership, cross-product isolation, scope, secrets, compile/AST | X1-X4 and S1-S8 in the CPU matrix; exactly one `^videoedit\|` handler owner |

Passing a lower-layer helper test does not substitute for the corresponding
callback, review, engine-payload, worker, artifact, or Back evidence listed in
the ordered matrix.

## Static-only readiness checkpoint (2026-08-02)

The owner has reserved the current CPU queue for other tasks. Until an explicit
Video Edit grant arrives, this branch remains **static-only**: no Python,
pytest, py_compile, compileall, FFmpeg, ffprobe, Telegram, provider, worker,
deployment, or production-media command is allowed.

Completed without CPU:

- [x] Isolated linked worktree and single branch confirmed; dirty Video Edit
  work preserved without reset or checkout.
- [x] Changed-path inventory is contained by
  `VIDEO_EDIT_COMPLETION_SCOPE_FILES`.
- [x] Sole callback owner confirmed as
  `CallbackQueryHandler(handle_video_editor_callback, pattern=r"^videoedit\\|")`.
- [x] Rendered callback inventory reviewed; the only apparently unmatched
  literal actions are intentional compatibility aliases locked by canonical
  navigation tests.
- [x] No added Product Video, Frame Video, SubDub, `lvs27a`, or `lvs27b`
  callback route was found in the Video Edit delta.
- [x] Bot, engine, and worker contracts align on `video_edit`,
  `video_local_edit`, `local_worker_ffmpeg`, and `local_video_edit`.
- [x] Added-line secret/private-path scan found no credential, token, private
  key, connection URI, or real private filesystem path.
- [x] Conflict-marker, placeholder, and added empty-production-handler scans
  found no unresolved implementation placeholder; the sole added `pass` is
  the bounded Telegram callback-answer failure path before stale-screen
  recovery.
- [x] `git diff --check` is clean apart from Git's informational LF/CRLF
  conversion warnings.
- [x] Ten independent review blockers have focused tests written before their
  production fixes: latest-row ownership/type/ID, SQLite log privacy,
  six-stage language, incomplete-delivery truth, SELECT-only receipt reads,
  Vietnamese public copy/scope, reply-race CAS, Split re-upload neutrality,
  stale-rerender log privacy, and truthful logo position/opacity review copy.
- [x] Additional static trace tests cover saved-English empty/unavailable
  status, the complete no-provider AI planning lane, every visible nested Back
  screen, direct manual-choice persistence/review visibility, forbidden cross-
  route prefixes, and the absence of a public logo-scale control.

Remaining only after an explicit CPU grant:

- [ ] Observe the focused blocker tests fail for the intended reasons.
- [ ] Apply minimal production fixes, then run focused GREEN and all eight
  ordered clusters.
- [ ] Run aggregate Video Edit, cross-product, compile/tokenize/AST, scope,
  callback, secret, and diff gates once, sequentially and with bounded
  timeouts.
- [ ] Obtain spec then code-quality approval, integrate latest main safely,
  rerun exact-head gates, push, open one non-draft PR, require exact-head CI,
  merge with a merge commit, and perform only the authorized navigation/read-
  only live smoke.

## CPU borrowing protocol

Do not infer CPU availability from an empty process list or another task's
release. When static work is exhausted and CPU verification is the sole
remaining blocker, send this bounded request to the Codex task titled
`hoàn thiện bot` (thread `019efe1e-ee54-78e1-87c4-10db6e1e19e4`) and wait for
an explicit grant:

```text
VIDEO EDIT CPU BORROW REQUEST — STATIC WORK COMPLETE.

Branch: fix/p0-videoedit-completion-hardening
Worktree: C:\Users\toann\Documents\Codex\2026-07-28\t-m-l\work\local-video-studio27b-deploy-39c96bd

All non-CPU Video Edit work is complete. The only remaining work is one
sequential TDD/verification session: focused RED for the ten locked blockers,
minimal GREEN fixes, eight ordered Video Edit clusters, aggregate/cross-product
regressions, and compile/tokenize/AST/static ship gates. No Telegram, provider,
worker, deploy, wallet/Xu, or production media is requested.

Please reply with an explicit `CPU GRANTED TO VIDEO EDIT` and any bounded time
window. Until that exact grant, Video Edit will not start Python/pytest/compile/
FFmpeg/ffprobe.
```

After the grant, announce `CPU ACQUIRED BY VIDEO EDIT`, run only the locked
matrix, spawn no unrelated gate, and return `CPU RELEASED BY VIDEO EDIT` as
soon as every Python/FFmpeg/ffprobe process is terminal.

- No placeholder behavior or provider-backed operation is introduced.
- Split semantics are explicit: separate files, source audio retained, manual edits not silently applied or discarded.
- Logo means a user-supplied image overlay/watermark with existing position and opacity controls; no new scale/editor surface is added.
- Every new invariant is tested at the earliest layer and re-enforced at the worker boundary.
- The only public product changed is `videoedit|`; the existing `lvs27b` planning entry remains isolated.
