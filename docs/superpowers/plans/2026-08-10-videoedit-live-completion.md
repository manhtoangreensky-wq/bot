# Video Edit Live Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve exact Video Edit target values, render a receipt-backed professional status report, and prove supported products through focused automated and Telegram live evidence.

**Architecture:** Extend the pure local intent compiler with bounded context-aware percentage extraction. Persist the executed operation summary in the worker's terminal success detail, then enrich `video_editor_job_status_text` from that terminal evidence plus canonical job and artifact receipt fields so live status never invents provider, charge, balance, duration, or delivery facts.

**Tech Stack:** Python 3.11, python-telegram-bot inline callbacks, SQLite job/receipt state, FFmpeg/ffprobe local worker, pytest.

---

### Task 1: Exact numeric target compiler

**Files:**
- Modify: `tests/test_p0_videoedit_capability_truth.py`
- Modify: `services/video_edit_capabilities.py`

- [ ] **Step 1: Write the failing test**

Add a test that compiles `Làm sáng video lên 120% và tăng âm lượng lên 110%` and asserts `feature_keys == ["enhance_light_color", "audio_master_volume"]`, `brightness_percent == 120`, `volume == 1.1`, all side-effect flags remain false, and the original request is preserved.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
D:\TOANAAS\_venv311_restore400\Scripts\python.exe -m pytest -q --noconftest -p no:cacheprovider --basetemp .videoedit-goal-percent-red tests/test_p0_videoedit_capability_truth.py::test_numeric_brightness_and_master_volume_are_preserved_from_one_goal
```

Expected: one behavioral failure because the current compiler emits only `color_preset=bright_clear` and omits master volume.

- [ ] **Step 3: Implement the minimal compiler change**

Add private helpers in `services/video_edit_capabilities.py` that extract a single bounded percentage near brightness or master-volume phrases. Override the default `enhance_light_color` patch with `{"brightness_percent": percent}` when brightness is explicit; add `audio_master_volume` with `{"volume": percent / 100}` when master volume is explicit. Reject out-of-range explicit percentages instead of silently applying a preset.

- [ ] **Step 4: Run focused and existing compiler tests**

Run the exact RED node, then the whole `tests/test_p0_videoedit_capability_truth.py`. Expected: zero failures.

### Task 2: Professional receipt-backed Video Edit status

**Files:**
- Modify: `tests/test_p0_videoedit_route_engine_status.py`
- Modify: `bot.py`

- [ ] **Step 1: Write terminal success and failure RED tests**

Extend status fixtures with real `created_at`, `started_at`, `finished_at`, `artifact_receipts`, `manual_edit_plan`, `charge_state`, and `charged_xu`. Assert terminal success contains the Subdub-style fields for result, output duration, processing elapsed time, engine, confirmed price, charged Xu, and delivered status. Assert failure names the failed stage/reason and does not claim a charge or delivered video.

- [ ] **Step 2: Run only the two new nodes and verify behavioral failures**

Use `--noconftest -p no:cacheprovider` with a fresh writable basetemp. Expected: missing receipt/report fields only, no collection error.

- [ ] **Step 3: Enrich `video_editor_job_status_text`**

Derive operation labels only from the worker's terminal `operation_summary`, duration/resolution/size from validated artifact receipts, elapsed time from persisted timestamps, engine from canonical selected interface/worker ownership, and charge from canonical charge state. Show account balance only when that authoritative field exists. Preserve the existing six-stage board and delivery/failure safeguards.

- [ ] **Step 4: Run focused status tests**

Run the two new nodes and the existing Video Edit status test file. Expected: zero failures and no weakened delivery assertions.

### Task 3: Protected regression and static review

**Files:**
- Review: `services/video_edit_capabilities.py`
- Review: `bot.py`
- Review: changed tests and docs

- [ ] **Step 1: Run focused Video Edit route/engine comparators**

Run only the established Video Edit capability, canonical route, route-engine status, latest-status navigation, and local engine files that cover changed functions. No broad Product Video/Frame matrix.

- [ ] **Step 2: Run protected zero-side-effect comparators**

Verify compiler/preflight creates no provider call, invoice, job, or wallet mutation before final confirmation; verify local completed jobs remain 0 Xu.

- [ ] **Step 3: Compile and inspect the diff**

Run `python -m py_compile bot.py services\video_edit_capabilities.py`, `git diff --check`, inspect every changed hunk, and confirm no credentials, ENV, Product Video, Frame, or PayOS changes.

### Task 4: Authorized deployment and live product matrix

**Files:**
- No source edits unless a live failure supplies a new reproducible RED.

- [ ] **Step 1: Obtain the Owner gate for merge/deploy of the exact reviewed commit**

Do not infer this gate from earlier PR-specific approvals.

- [ ] **Step 2: Verify Railway and VPS exact revision**

Confirm Railway and `/opt/toanaas/bot` use the same approved commit; restart only `toanaas-video-edit-worker.service` if the Owner authorizes it. Do not restart Product Video or Frame.

- [ ] **Step 3: Live test the supported matrix**

Run one bounded job each for manual brightness and target-driven brightness plus master volume; inspect manual trim/logo/watermark evidence already produced; route through quality options and all Back/help buttons. Paid/provider-only actions stop at truthful pricing/preflight unless separately authorized.

- [ ] **Step 4: Validate each delivered artifact**

Download the actual Telegram MP4, ffprobe container/streams/duration, full-decode it, and measure the requested visual/audio transformation. Count exactly one job, one status board, and one delivered result per confirmation.

- [ ] **Step 5: Close and lock the task only after complete evidence**

Use the signed-in ChatGPT web task explicitly named by the Owner to report the final evidence, ask it to close this task, and state that other tasks must not modify Video Edit. Do this only after all supported products and routes have terminal evidence.
