# Video Edit Legacy Callback Context Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two remaining Video Edit callback regressions without mutating frozen Telegram objects or leaking coroutine-local callback state.

**Architecture:** Keep Telegram's `CallbackQuery` immutable and route the legacy Product Video entry by passing an explicit internal callback-data override through the existing Video Edit guard chain. Expand the existing Video Edit `ContextVar` transaction boundary so it encloses claim CAS, stale-winner rerender, compatibility handling, and every return path.

**Tech Stack:** Python 3.11, python-telegram-bot 22.7, asyncio `ContextVar`, pytest, GitHub Actions, Railway, Telegram Web.

---

### Task 1: Lock the frozen legacy entry with a runtime regression

**Files:**
- Modify: `tests/test_p0_videoedit_callbackquery_frozen_runtime.py`
- Modify: `bot.py`

- [ ] **Step 1: Write the failing frozen-object test**

Add a real `telegram.CallbackQuery` case for `vproduct|legacy|video_local_edit`. Patch only Telegram I/O and the current product session, then assert the handler renders the Video Edit hub, answers exactly once without an alert, and leaves `query.data` equal to the original legacy payload.

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
D:\TOANAAS\_venv311_restore400\Scripts\python.exe -m pytest -q tests/test_p0_videoedit_callbackquery_frozen_runtime.py::test_legacy_videoedit_hub_delegation_keeps_frozen_callback_payload
```

Expected: FAIL because `handle_video_product_callback` reaches `query.data = route`, the frozen assignment is contained by the public guard, and the Video Edit hub is not rendered.

- [ ] **Step 3: Implement the smallest explicit override**

Allow `video_public_callback_failure_guard` and `video_editor_callback_state_guard` to forward optional arguments. Let the state guard initialize `_VIDEO_EDIT_CALLBACK_TRANSACTIONAL` from an explicit `callback_data_override` beginning with `videoedit|`. Add a keyword-only override to `handle_video_editor_callback`, parse it instead of `query.data` when supplied. In the legacy branch, dispatch `prefix == "videoedit"` with `callback_data_override=route` **before** the existing `query.data = route` statement. Keep that existing mutation and routing unchanged for the out-of-scope `menu`, `framevideo`, `selfscene`, and `videoref` prefixes; never proxy, copy-unfreeze, or mutate the Telegram object on the Video Edit path.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the exact command from Step 2. Expected: `1 passed`, with one edit and one non-alert callback answer.

### Task 2: Enclose stale legacy-tail handling in the ContextVar boundary

**Files:**
- Modify: `tests/test_p0_videoedit_callbackquery_frozen_runtime.py`
- Modify: `bot.py`

- [ ] **Step 1: Write sequential and overlapping RED regressions**

Add one test that executes a stale `video_tail|review|open` callback and then `videoedit|hub` in the same async task. Add one `asyncio.gather` test for overlapping stale/direct callbacks. Each callback must answer once, and both `_VIDEO_EDIT_CALLBACK_ANSWERED` and `_VIDEO_EDIT_CALLBACK_TRANSACTIONAL` must equal their pre-call values after each handler returns.

- [ ] **Step 2: Run both tests and verify RED**

Run:

```powershell
D:\TOANAAS\_venv311_restore400\Scripts\python.exe -m pytest -q tests/test_p0_videoedit_callbackquery_frozen_runtime.py -k "stale_legacy_tail or overlapping"
```

Expected: FAIL because the stale CAS branch returns after `rerender_video_editor_after_stale_commit` sets the answered ContextVar but before the current token/reset boundary.

- [ ] **Step 3: Move the token boundary, without changing tail behavior**

In `handle_video_tail_callback`, set both Video Edit ContextVar tokens immediately upon entering `owner == "video_edit"`. Keep claim CAS, stale rerender, compatibility dispatch, and failure alert inside the `try`; reset both tokens in the existing `finally`. Preserve every current return value, full-state CAS, winning-state rerender, no-provider behavior, and the ban on commercial Product Video fallthrough.

- [ ] **Step 4: Run both tests and verify GREEN**

Run the exact command from Step 2. Expected: both cases pass with one answer per callback and no flag leakage.

### Task 3: Ordered verification, review, ship, and read-only live smoke

**Files:**
- Verify: `bot.py`
- Verify: `tests/test_p0_videoedit_callbackquery_frozen_runtime.py`
- Verify: existing Video Edit canonical/tail/status suites selected by `docs/superpowers/plans/2026-08-02-video-edit-cpu-verification-matrix.md`

- [ ] **Step 1: Run the complete focused file**

Expected: all frozen-object and ContextVar regressions pass.

- [ ] **Step 2: Run canonical and broad Video Edit gates in the documented order**

Compare any broad failure set against clean `origin/main@838d313`; accept only zero branch-only failures.

- [ ] **Step 3: Compile changed Python modules and run `git diff --check`**

Expected: exit 0 for `bot.py` compile and a clean diff check.

- [ ] **Step 4: Obtain independent spec and code-quality review**

Resolve every blocker with a new RED/GREEN cycle before shipping.

- [ ] **Step 5: Commit, push, open one non-draft follow-up PR, merge, and wait for Railway**

The PR must contain only Video Edit callback/test/plan changes. Confirm CI source compile and deployed build SHA match the merge commit.

- [ ] **Step 6: Perform Telegram Web navigation-only smoke**

Send one fresh `/start`; open both the direct and legacy Video Edit entries; verify the four primary routes, exact Back hierarchy, truthful read-only status, summary double-click idempotency, and absence of new `product_video_callback_failed`. Do not upload/render media, call a provider/worker, use wallet/Xu/PayOS, or run production recovery commands.
