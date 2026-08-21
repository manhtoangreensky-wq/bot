# SubDub Combo Single-Lane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose one SubDub combo path from video upload to language, default/automatic voice, confirmation, and exactly one final MP4 without a public original-subtitle step.

**Architecture:** Reuse the existing `videodub|source_upload` route and current combo pipeline. The fresh lane records language and voice before confirmation; only final confirmation starts internal ASR, translation, TTS, and mux on VPS. Resolve the existing `ASR_PROVIDER=auto` value through existing adapters without changing provider configuration. Preserve legacy callback handlers, large-MP4 document delivery, and billing behavior.

**Tech Stack:** Python, python-telegram-bot inline keyboards, pytest.

---

### Task 1: Lock the single-lane combo contract

**Files:**
- Modify: `tests/test_p0_19b5_hard_fix_video_translation_routing_restore_file_audio.py`

- [x] **Step 1: Replace the old two-path assertion with a failing single-lane assertion**

Assert that the combo keyboard contains exactly one `videodub|source_upload`, contains no callback beginning with `videodub|path|`, and does not expose the no-subtitle path.

- [x] **Step 2: Strengthen the upload-routing assertion**

After a fresh combo video upload, assert `step == "language"`, `step != "original_subtitle_confirm"`, and no reply button uses `videodub|confirm_original_subtitle`.

- [x] **Step 3: Run the exact selector and confirm RED**

Run:

```powershell
python -m pytest -q tests/test_p0_19b5_hard_fix_video_translation_routing_restore_file_audio.py::test_combo_single_upload_lane tests/test_p0_19b5_hard_fix_video_translation_routing_restore_file_audio.py::test_combo_internal_transcript_after_confirm_only
```

Expected: the first test fails because the current keyboard exposes two `videodub|path|...` callbacks.

### Task 2: Expose the existing direct combo route

**Files:**
- Modify: `bot.py:231667`

- [x] **Step 1: Make the minimal production change**

For `VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB`, return one item using the existing localized upload label and `videodub|source_upload`. Do not remove legacy handlers or constants.

Route preset/custom language directly to the voice picker for the fresh lane. Hide intermediate download actions and fail closed unless the final MP4 is delivered. Keep MP4 document fallback for large files.

- [ ] **Step 2: Run the focused GREEN selector**

Run the two tests from Task 1 and expect 2 passed.

- [ ] **Step 3: Run the protected final-confirm comparator**

```powershell
python -m pytest -q tests/test_p0_17b6_3_subtitle_plus_dub_state_machine.py::test_subtitle_plus_dub_full_requires_confirm
```

Expected: 1 passed and zero provider calls.

- [ ] **Step 4: Verify the patch**

Run `git diff --check`, parse the changed Python files, and inspect the complete diff. Do not run broad tests.

### Task 3: Deliver and verify live

**Files:**
- No additional source files unless a concrete focused failure proves a blocker.

- [ ] **Step 1: Commit and open one PR**

Stage exact task files only, commit, push, and open one PR.

- [ ] **Step 2: Merge and allow the existing VPS auto-deploy**

Merge only when required CI is successful and the PR is clean.

- [ ] **Step 3: Run the authorized two-speaker live smoke**

Verify one combo entry, direct language picker after upload, final confirmation, real provider output, delivered MP4, media probe/decode, speaker mapping, audio mix, and exact Xu result.
