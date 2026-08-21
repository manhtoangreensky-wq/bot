# Video Edit UI Route Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove detached status navigation, place Planning beside the general Video guide, and make every affected Back button return to its exact Video parent without touching render/engine behavior.

**Architecture:** Keep the canonical callback families intact. Change only visible keyboard composition, route metadata for the feature-gated planning entry, and the planning root exit renderer. Preserve stale status handlers as compatibility-only read paths.

**Tech Stack:** Python 3.11, python-telegram-bot inline keyboards, pytest, existing TOAN AAS route-audit helpers.

---

### Task 1: Lock the requested UI contract with RED tests

**Files:**
- Modify: `tests/test_p0_video_uiflow3_telegram_ui.py`
- Modify: `tests/test_p0_video_edit3_compact_manual_flow.py`
- Modify: `tests/test_p0_videoedit_back_hierarchy_adapter.py`
- Modify: `tests/test_p1_localvideostudio27b_public_ui.py`
- Modify: `tests/test_p0_18k_video_menu_flow_standardization_routing_matrix.py`

- [ ] **Step 1: Change the general guide assertion**

Assert its visible callbacks are exactly `menu|main_video` and `menu|main`; explicitly reject `menu|main_guide`.

- [ ] **Step 2: Change the hub and workspace assertions**

Assert both keyboards exclude `videoedit|latest_status`; assert the hub also excludes `lvs27b|open` and retains only the four primary actions plus parent navigation.

- [ ] **Step 3: Add the feature-gated main-menu layout assertion**

With `local_video_studio_public_enabled=True`, assert the penultimate row is `lvs27b|open` beside `menu|guide_video_ai` and the last row is `menu|main`. With the flag off, assert no planning callback is visible.

- [ ] **Step 4: Change the planning root-Back assertion**

Compile the public adapter with a main-Video renderer and assert root Back renders that surface, deletes the planning session only after delivery, and never renders the Video Edit hub.

- [ ] **Step 5: Run RED**

Run the exact changed nodes with a fresh `--basetemp`. Expected: behavioral assertion failures for the current generic-guide Back, both standalone status buttons, planning placement/registration, and planning root exit. Collection/import errors are not valid RED.

### Task 2: Implement the minimal UI and route patch

**Files:**
- Modify: `bot.py`
- Modify: `services/local_video_studio_public.py`

- [ ] **Step 1: Remove detached status buttons**

Delete `videoedit|latest_status` only from `video_edit_hub_keyboard()` and `video_local_manual_options_keyboard()`. Replace its two-column workspace slot with `videoedit|guide|workspace`, whose Back edge returns to the same workspace. Do not delete the compatibility callback handler or per-job `status`/`ai_status` refresh callbacks.

- [ ] **Step 2: Make the general Video guide parent-exact**

Change `video_uiflow3_guide_keyboard()` to render one Back action to `menu|main_video` plus the explicit Main menu action.

- [ ] **Step 3: Register and render Planning from Main Video**

Add a `video_planning` route entry for `lvs27b|open` owned by `handle_local_video_studio_public_callback`. Build effective public rows so Planning appears beside `video_guide` only when enabled, while route-audit rows mirror the visible keyboard.

- [ ] **Step 4: Return Planning root Back to Main Video**

Render `menu_text_main_video_i18n()` and `main_video_keyboard()` on `exit_parent`, keep delivery-before-session-delete ordering, and update safe feedback copy from “Chỉnh sửa video” to “Menu Video”.

- [ ] **Step 5: Run focused GREEN**

Run the same nodes from Task 1 with a new basetemp. Require zero failures.

### Task 3: Reconcile affected contracts without hiding regressions

**Files:**
- Modify only tests whose old snapshots require the removed status/old Planning location/generic-guide Back.

- [ ] **Step 1: Search stale expectations**

Search for `videoedit|latest_status`, `lvs27b|open`, `menu|main_guide`, `PUBLIC_MENU_ROWS`, and route-matrix callback counts in the affected Video Edit and Video menu tests.

- [ ] **Step 2: Classify each assertion**

Keep read-only stale-callback safety tests. Update only visible-menu snapshots and parent/Back expectations superseded by this approved UI contract.

- [ ] **Step 3: Run affected suites**

Run the focused UI cleanup tests, Video Edit navigation/status compatibility tests, Local Video Studio public UI tests, UIFLOW3 Telegram UI tests, and Video route/back audit selectors. Record exact pass/fail counts.

### Task 4: Verify and prepare the separate UI merge

**Files:**
- Review all changed files; no new production scope.

- [ ] **Step 1: Static gates**

Run `D:\TOANAAS\_venv311_restore400\Scripts\python.exe -m py_compile bot.py`, `git diff --check`, `git status --short`, and `git diff --name-only origin/main`.

- [ ] **Step 2: Independent review**

Review route ownership, exact parent Back behavior, disabled-feature behavior, stale callback safety, and forbidden-file scope.

- [ ] **Step 3: Live Telegram QA after an approved runtime/deploy exists**

Verify Main Video → Video guide → Back, Main Video → Planning → root Back, Video Edit hub contents, active workspace contents, and caller-specific editor guide Back. Label this `LIVE PASS` only if the bot runtime SHA matches the UI commit and the real callbacks were clicked.

- [ ] **Step 4: Ship UI separately**

Commit and push only the UI/UX cluster, open/review its PR, and merge it before creating the route/engine branch. Do not deploy without explicit approval.

### Task 5: Start engine work only after the UI merge

**Files:**
- No files in this UI plan.

- [ ] **Step 1: Create a new branch from the merged main**

Use a separate route/engine branch for cut, logo image, text watermark, and job-bound progress.

- [ ] **Step 2: Reproduce each public path with RED tests**

Lock trigger, guard, state edge, worker action, artifact evidence, failure copy, and exact Back edge for each operation.

- [ ] **Step 3: Reuse the canonical executor**

Route the public flow through the existing `video_local_edit` job, `services/video_local_editing.py`, and `local_worker.py`; do not create a parallel engine.

- [ ] **Step 4: Prove artifacts and live behavior**

Require validated MP4 bytes/container/duration/dimensions and Telegram delivery evidence. A queued job, metadata object, or unit-only pass is not completion.
