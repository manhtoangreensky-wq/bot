# Local Video Studio 27A Owner Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tạo sản phẩm Telegram preview tiếng Việt, owner/admin only, để duyệt
flow tạo/chỉnh video và toàn bộ capability 26B–26I mà không gọi provider,
renderer, wallet, worker hoặc sửa menu sản phẩm cũ.

**Architecture:** `services/local_video_studio_preview.py` là pure local service
đọc capability index, quản lý state/backstack và sinh view model. `bot.py` chỉ
chuyển view model thành Telegram keyboard và đăng ký một command/callback
namespace riêng. Focused tests import service trực tiếp và kiểm integration
`bot.py` bằng source/AST để không cần import file 12,7 MB.

**Tech Stack:** Python stdlib, python-telegram-bot primitives đã có, JSON 26I,
pytest, Telegram inline keyboard.

---

## File structure

- Create: `services/local_video_studio_preview.py` — index reader, exact flow,
  state/history, callback parser và pure view renderer.
- Modify: `bot.py` — một import, hai handler functions và hai registrations.
- Create: `tests/test_p1_localvideostudio27a_preview.py` — focused contract,
  navigation, coverage, safety và static integration tests.
- Create: `docs/superpowers/plans/2026-07-29-localvideostudio27a-preview.md`
  — execution record này.

Không sửa `services/frame_video_*`, `video_product_system.py`, Product Video,
SubDub, portal/static UI, renderer, worker, ENV, DB, wallet hoặc billing.

## Task 1: Inventory baseline and RED contract

- [ ] **Step 1: Record exact baseline**

Run:

```powershell
git rev-parse HEAD
git status --short --branch
python -m py_compile bot.py
```

Expected: HEAD contains 27A spec commit; worktree clean except this plan after
creation. Record baseline `py_compile` result honestly; latest-main baseline
already timed out after 184 seconds.

- [ ] **Step 2: Write focused test constants and forbidden boundaries**

Create `tests/test_p1_localvideostudio27a_preview.py` with exact constants:

```python
CALLBACK_PREFIX = "lvs27a"
STATE_KEY = "local_video_studio27a_preview"
LOCAL_RECORD_IDS = (
    "openmontage_local",
    "editing_grammar",
    "framing_composition",
    "pacing_storytelling",
    "camera_movement",
    "rights_requirements",
    "transition_motion_pack",
    "sound_design_pack",
    "viral_effects",
    "local_free_capabilities",
    "video_qa",
)
PAID_RECORD_IDS = ("mosaic_motion", "higgsfield", "suno")
CREATE_SCREENS = (
    "create_goal", "create_format", "create_style", "create_audio",
    "create_review", "create_qa", "complete",
)
EDIT_SCREENS = (
    "edit_goal", "edit_source", "edit_delivery", "edit_review",
    "edit_qa", "complete",
)
```

Tests must require service import, 14 records/251 IDs, local 248/paid 3
coverage, exact 19 QA IDs, pure stdlib imports, exact namespace/state key,
flow order, Back, mandatory-step rejection, callback length, no cross-product
route and bot registration/authorization.

- [ ] **Step 3: Run RED**

Run:

```powershell
python -m pytest -q --noconftest -p no:cacheprovider tests/test_p1_localvideostudio27a_preview.py
```

Expected: FAIL because `services.local_video_studio_preview` does not exist.

## Task 2: Pure capability/index boundary

- [ ] **Step 1: Add module envelope and index validator**

Create `services/local_video_studio_preview.py` with:

```python
CALLBACK_PREFIX = "lvs27a"
STATE_KEY = "local_video_studio27a_preview"
PREVIEW_VERSION = "27A"
CATALOG_PAGE_SIZE = 6
PACK_PAGE_SIZE = 8
LOCAL_RECORD_IDS = (
    "openmontage_local",
    "editing_grammar",
    "framing_composition",
    "pacing_storytelling",
    "camera_movement",
    "rights_requirements",
    "transition_motion_pack",
    "sound_design_pack",
    "viral_effects",
    "local_free_capabilities",
    "video_qa",
)
PAID_RECORD_IDS = ("mosaic_motion", "higgsfield", "suno")
```

Add `PreviewDataError` and `PreviewActionError` as `ValueError` subclasses.
`load_capability_index()` reads the UTF-8 JSON at the repository-relative 26I
path and returns `validate_capability_index(payload)`. The validator returns a
deep-copy-safe dictionary only after exact count/order/lock checks.
`capability_coverage(payload)` returns exact `local`, `paid`, `all` and `qa`
ID tuples derived from the validated records.

Validation requires exact record order, 14 records, 251 globally unique IDs,
248 IDs in the 11 local records, 3 paid IDs, 19 QA IDs and four per-record
planning locks. It must reject any production-ready/public/provider-executable
record and must not upgrade readiness.

- [ ] **Step 2: Run focused index tests**

Expected: index/coverage tests PASS; flow/render tests remain FAIL.

## Task 3: Session, callback and exact Back behavior

- [ ] **Step 1: Define data-driven flow**

Add exact immutable definitions:

```python
FLOW_STEPS = {
    "create": (
        ("create_goal", "goal"),
        ("create_format", "format"),
        ("create_style", "style"),
        ("create_audio", "audio"),
        ("create_review", ""),
        ("create_qa", ""),
        ("complete", ""),
    ),
    "edit": (
        ("edit_goal", "goal"),
        ("edit_source", "source"),
        ("edit_delivery", "delivery"),
        ("edit_review", ""),
        ("edit_qa", ""),
        ("complete", ""),
    ),
}
```

Each selectable step has 3–4 exact Vietnamese options and a short stored ID.
Audio options exclude Suno/generation. Source options explicitly require
owner-supplied/licensed/planned footage.

- [ ] **Step 2: Implement immutable session navigation**

Add `new_session()`, `normalize_session(session)` and
`apply_callback(session, callback_data)`. `new_session()` returns every state
field from the design with empty history/selections and screen `home`.
`normalize_session` rebuilds unknown input from that schema and accepts only
known screens/modes/non-negative pages. `apply_callback` parses only the exact
allowlist and returns `{"session": normalized_copy, "closed": bool,
"feedback": Vietnamese text}`.

`apply_callback` returns a new session/result, never mutates the input. `Back`
pops exactly one history entry. `Home` resets only 27A. `Close` returns
`closed=True`. `pick` is accepted only when its screen equals current screen;
therefore a callback cannot skip required steps.

- [ ] **Step 3: Run navigation tests**

Expected: create/edit forward flow, every parent Back, stale action rejection,
home reset and close all PASS.

## Task 4: Pure Vietnamese view renderer

- [ ] **Step 1: Implement button and pagination helpers**

Add `callback_data(*parts)`, `paginate(items, page, page_size)` and
`render_view(session, payload=None)`. `callback_data` rejects separators inside
parts and any encoded value over 64 UTF-8 bytes. `paginate` clamps page and
returns `(visible_items, current_page, total_pages)`. `render_view` validates
the session/index and returns the exact view model below.

Every view is a dictionary with `screen: str`, `text: str` and `rows`: an
ordered tuple of rows, each row an ordered tuple of `(label, callback)` pairs.
Enforce callback namespace and UTF-8 size ≤64 bytes.
Each row has at most two buttons.

- [ ] **Step 2: Render exact home and wizards**

Home has create, edit, catalog, safety and close. Flow screens show progress,
current choice and only valid next actions. Review/QA/complete screens state
`planning-only`, `provider calls=0`, `Xu=0`, `không tạo MP4`.

- [ ] **Step 3: Render catalog and safety**

Catalog pages expose all 11 local records. Pack pages expose every one of 248
local qualified IDs. Safety/QA pages expose 3 paid-disabled IDs, exact 19 QA
IDs and all zero counters. No button may target `menu|`, `vproduct|`,
`videoedit|`, `videodub|`, `motion|` or another product namespace.

- [ ] **Step 4: Run local preview tests**

Iterate every flow screen, catalog page, pack page and QA page. Expected:
all render without exception, all text ≤4096 chars, callback matrix PASS,
coverage 251/251.

## Task 5: Narrow Telegram adapter

- [ ] **Step 1: Add service import only**

Modify the existing services import section in `bot.py`:

```python
from services import local_video_studio_preview
```

- [ ] **Step 2: Add keyboard adapter and two guarded handlers**

Add exactly three adapter functions:

- `local_video_studio_preview_keyboard(view)` maps every `(label, callback)`
  pair to one `InlineKeyboardButton` and preserves the row order;
- `cmd_local_video_studio_preview(update, context)` guards admin, stores a new
  session, renders home and replies once;
- `handle_local_video_studio_preview_callback(update, context)` guards admin,
  answers once, applies the pure callback result, stores/clears only the 27A
  key and edits the same preview message.

Both paths verify `is_admin_user`. Unauthorized callbacks answer with an alert
and do not create state. The command initializes only `context.user_data[STATE_KEY]`.
The callback acknowledges once, applies the pure result, edits the same message
and clears only the 27A state on close.

- [ ] **Step 3: Register hidden entry and callback**

Add only:

```python
tg_app.add_handler(CommandHandler(
    "local_video_studio_preview",
    admin_internal_command(cmd_local_video_studio_preview),
))
tg_app.add_handler(CallbackQueryHandler(
    handle_local_video_studio_preview_callback,
    pattern=r"^lvs27a\|",
))
```

Do not edit any menu text, keyboard, existing handler pattern or callback.

- [ ] **Step 4: Run focused tests**

Expected: focused 27A all PASS.

## Task 6: Verification, review and ship

- [ ] **Step 1: Run focused and regressions**

Run:

```powershell
python -m pytest -q --noconftest -p no:cacheprovider tests/test_p1_localvideostudio27a_preview.py
python -m pytest -q --noconftest -p no:cacheprovider tests/test_p1_localvideostudio26c_filmmaking_skills.py tests/test_p1_localvideostudio26d_transition_motion_pack.py tests/test_p1_localvideostudio26d_transition_audio.py tests/test_p1_localvideostudio26e_sound_design.py tests/test_p1_localvideostudio26f_viral_effects.py tests/test_p1_localvideostudio26g_local_capabilities.py tests/test_p1_localvideostudio26h_video_qa.py tests/test_p1_localvideostudio26i_codex_index.py tests/test_p1_localvideostudio27a_preview.py
```

Expected: zero failures/new failures.

- [ ] **Step 2: Validate changed Python**

Run:

```powershell
python -m py_compile services/local_video_studio_preview.py tests/test_p1_localvideostudio27a_preview.py
python -m tokenize bot.py
python -m py_compile bot.py
```

For `bot.py`, report timeout honestly and compare to baseline timeout; do not
claim compile PASS unless exit code is 0.

- [ ] **Step 3: Static and scope gates**

Run `git diff --check`, secret/placeholder scan, callback length/namespace
tests and `git diff --name-only`. Exact implementation scope must be plan,
service, focused test and narrow `bot.py`; no protected product files.

- [ ] **Step 4: Independent spec and quality review**

Reject Critical/Important findings or fix them on the same branch. Re-run
focused/regression after every code correction.

- [ ] **Step 5: Commit, sync, PR and merge**

Commit implementation, fetch latest origin/main, rebase if advanced, re-run
gates, push, create one PR and verify head/MERGEABLE/CLEAN. Because owner đã
explicitly chọn auto-merge, merge by merge commit only after all gates pass.
Do not deploy and do not start 27B.
