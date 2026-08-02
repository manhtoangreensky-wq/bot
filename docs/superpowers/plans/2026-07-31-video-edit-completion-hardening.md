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

### Task 6: Ship and merge gate

Before shipping, close the independent review blockers with focused RED/GREEN
evidence:

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
- [ ] Keep already-sent `video_tail|` buttons fail-closed, but stop emitting new
  shared-tail Video Edit callbacks or paid-package copy; all newly rendered
  actions must use the canonical `videoedit|` namespace.
- [ ] Bind rights evidence to the payload revision and bind manual plan asset
  placeholders to their Telegram asset records before queue insert and again
  in the worker.
- [ ] Translate public Vietnamese surfaces so internal execution terms are not
  exposed; keep implementation identifiers only in contracts, logs, and tests.

- [ ] Commit only approved Video Edit paths, push `fix/p0-videoedit-completion-hardening`, and open one PR against latest `main`.
- [ ] If `origin/main` advances, inspect every path; rebase only when the delta is unrelated or explicitly accepted.
- [ ] Require GitHub CI PASS on the exact head, merge with a merge commit, and prove the implementation head is an ancestor of the two-parent merge.
- [ ] Do not deploy or run Telegram production media smoke; report provider/worker production calls, wallet mutations, production deliveries, jobs, ENV changes, and deploys as zero.

## Self-review

- No placeholder behavior or provider-backed operation is introduced.
- Split semantics are explicit: separate files, source audio retained, manual edits not silently applied or discarded.
- Logo means a user-supplied image overlay/watermark with existing position and opacity controls; no new scale/editor surface is added.
- Every new invariant is tested at the earliest layer and re-enforced at the worker boundary.
- The only public product changed is `videoedit|`; the existing `lvs27b` planning entry remains isolated.
