# Video Edit Canonical Route/Engine Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Cut, image Logo, and text Watermark follow the canonical local worker route and show truthful progress inside each submitted edit job.

**Architecture:** Keep `videoedit|` as the only editor callback namespace and reuse `video_editengine1`, `local_worker.py`, and `video_local_editing.py`. Fix ownership when a user explicitly leaves Video Edit, then add a Video Edit-specific read-only adapter to the existing status-panel scheduler so it renders `video_editor_job_status_text()` for one exact owned worker job.

**Tech Stack:** Python 3.11, python-telegram-bot handlers, SQLite read-only status queries, pytest, FFmpeg/ffprobe fixture tests.

---

### Task 1: Lock the cross-product text-owner boundary

**Files:**
- Modify: `tests/test_p0_videoedit_flow_isolation_branding.py`
- Modify: `bot.py`

- [ ] **Step 1: Write the failing public-handler test**

Seed a valid stale Video Edit state at `await_brightness`, invoke the real
`create_media|quick_image`/image-tier entry, and assert that Video Edit no
longer owns the next logo/watermark text. Also assert the media/quick-image
state advances to its position screen and no brightness response is emitted.

- [ ] **Step 2: Run the focused RED**

Run:

```powershell
D:\TOANAAS\_venv311_restore400\Scripts\python.exe -m pytest -q --noconftest -p no:cacheprovider --basetemp .videoedit-owner-red tests/test_p0_videoedit_flow_isolation_branding.py::test_explicit_image_entry_releases_stale_videoedit_text_owner
```

Expected: one behavioral failure showing the stale Video Edit state remains.

- [ ] **Step 3: Implement the smallest owner handoff**

On explicit public media/image entry callbacks, clear only the stale
`video_editor:<uid>` session before creating the new product state. Do not
change message-handler priority, payment, provider, or media generation code.

- [ ] **Step 4: Run the focused GREEN**

Expected: the same node passes and its assertions prove no Brightness mutation.

### Task 2: Lock the three canonical public edit lanes

**Files:**
- Create: `tests/test_p0_videoedit_route_engine_status.py`
- Modify only if RED proves a defect: `bot.py`

- [ ] **Step 1: Add callback/text REDs**

Use real handlers and provider-free fixtures to cover:

```text
workspace -> cut -> trim input -> workspace/review
workspace -> branding -> logo upload/options -> review
workspace -> branding -> watermark text/options -> review
```

Assert exact parent callbacks, exact independent plan fields, no color/
brightness fall-through, and that Review keeps both logo and watermark.

- [ ] **Step 2: Run only these nodes and classify results**

Tests that already pass are characterization evidence. Any failing behavioral
node must fail at the exact public edge before production code changes.

- [ ] **Step 3: Apply only proven route/state fixes**

Do not rewrite executors or duplicate callback namespaces. Preserve the exact
working Logo/Watermark normalization and worker payload fields.

### Task 3: Render and bind the initial job progress panel

**Files:**
- Modify: `tests/test_p0_videoedit_route_engine_status.py`
- Modify: `bot.py`

- [ ] **Step 1: Write the failing submit-panel test**

Submit one canonical local job through the real public confirm seam with a
fake Telegram transport and local DB fixture. Assert the first submitted view
already contains all six Video Edit progress stages, uses
`videoedit|status|<job_id>`, and registers that exact chat/message/job tuple.

- [ ] **Step 2: Verify RED**

Expected: current code sends a simple acceptance receipt and does not register
the Video Edit panel.

- [ ] **Step 3: Add one shared panel sender**

Render `video_editor_job_status_text(job, lang)`, use
`video_editor_status_keyboard(job_id, lang)`, capture the edited/sent Telegram
message, and register it with the existing scheduler under the dedicated
`video_edit` type. Reuse it from canonical local submit paths.

- [ ] **Step 4: Verify GREEN**

Assert one job, one panel, one callback, no provider call, and zero wallet
mutation.

### Task 4: Add Video Edit-specific read-only auto refresh

**Files:**
- Modify: `tests/test_p0_videoedit_route_engine_status.py`
- Modify: `bot.py`

- [ ] **Step 1: Write failing scheduler tests**

Cover stage changes:

```text
received -> inspecting_input -> preparing_plan -> processing_video
-> validating_output -> delivering -> delivered/failed_no_charge/delivery_unknown
```

Assert edits target the original message and exact owned job. Refresh must not
create/requeue a job, execute media, deliver a file, call a provider, or touch
wallet state.

- [ ] **Step 2: Add a dedicated status adapter**

Preserve `video_edit` in auto-refresh keys, read only
`local_worker_jobs` plus the canonical `video_edit_jobs` receipt, derive the
render hash from `video_editor_job_status_text()`, and keep the existing Video
Edit keyboard. Do not route through Product Video's generic multiscene spec.

- [ ] **Step 3: Lock terminal truth**

Only receipt-backed MP4 delivery stops as `delivered`. Missing full-decode,
Telegram IDs, SHA, positive bytes, or ffprobe evidence renders
`delivery_unknown`; failure renders `failed_no_charge`.

- [ ] **Step 4: Run focused GREEN**

Expected: same-message edits, no fallback duplicate messages, and scheduler
stops on each terminal state.

### Task 5: Prove the actual engine artifacts

**Files:**
- Modify tests only if a missing public seam is proven.

- [ ] **Step 1: Run focused public route/worker suites**

Run the new route/status file plus canonical bot routes, flow isolation,
navigation, and receipt suites with fresh writable basetemps.

- [ ] **Step 2: Run real-media FFmpeg evidence**

Run the existing bounded real-media nodes for trim/remove-middle/split, image
logo, text watermark, and combined final timeline. Require MP4/H.264, duration,
dimensions, bytes, full decode, SHA, and delivery receipt assertions.

- [ ] **Step 3: Run compile and scope checks**

```powershell
D:\TOANAAS\_venv311_restore400\Scripts\python.exe -m py_compile bot.py local_worker.py services\video_local_editing.py services\video_editengine1.py
git diff --check
git status --short
```

- [ ] **Step 4: Independent review**

Review route ownership, callback/Back graph, idempotency, read-only refresh,
terminal artifact truth, forbidden-scope diff, and public copy.

### Task 6: Ship the engine change separately

**Files:**
- Commit only the engine branch's focused source/tests/docs.

- [ ] **Step 1: Commit after all relevant gates pass**
- [ ] **Step 2: Rebase on current `origin/main` and rerun affected gates**
- [ ] **Step 3: Push and create one engine PR**
- [ ] **Step 4: Merge only after CI/review passes**
- [ ] **Step 5: Request explicit deployment approval before Telegram LIVE QA**

Unit, fixture, or real local FFmpeg results are never reported as Telegram
LIVE PASS.
