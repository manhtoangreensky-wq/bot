# Video Planning Assistant MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the public capability-checklist wizard with a structured Vietnamese editing-planning assistant and a small owner-scoped saved-plan library, without executing or handing off media.

**Architecture:** Preserve the old `services/local_video_studio_public.py` capability adapter as legacy internal evidence and add `services/video_planning_assistant.py` as the new pure public callback/state/view owner. `bot.py` imports the new service under the existing adapter alias, so the public namespace and single registered handler remain stable. A separate SQLite CRUD module owns saved plans. Ordinary navigation commits state only after successful delivery, while an explicit durable save must complete idempotently before copy may claim `Đã lưu`. The adapter never calls Video Edit, Product Video, worker, provider, billing or wallet code.

**Tech Stack:** Python 3.11, python-telegram-bot inline callbacks, SQLite, pytest.

---

### Task 1: Freeze the approved product contract

**Files:**
- Create: `docs/superpowers/specs/2026-08-11-video-planning-assistant-design.md`
- Create: `docs/superpowers/plans/2026-08-11-video-planning-assistant.md`

- [ ] **Step 1: Record exact boundaries**

Verify the design contains the public distinction:

```text
Product Video = create new content
Video Edit = execute against media
Video Planning = prepare a plan only
```

- [ ] **Step 2: Verify scope text**

Run:

```powershell
rg -n "provider|wallet|handoff|version history|media upload" docs/superpowers/specs/2026-08-11-video-planning-assistant-design.md
```

Expected: every term appears only as a protected boundary or exclusion.

### Task 2: Build the pure structured planning state machine with TDD

**Files:**
- Create: `services/video_planning_assistant.py`
- Create: `tests/test_p1_video_planning_assistant.py`

- [ ] **Step 1: Write failing public-flow tests**

Add tests that require this exact visible sequence from `services.video_planning_assistant`:

```python
assert screens == [
    "goal",
    "brief",
    "platform",
    "source_duration",
    "target_duration",
    "assets",
    "priorities",
    "operations",
    "safety",
    "summary",
]
```

The tests must also assert:

```python
assert service.public_entry_rows(True) == (
    ("🧭 Lên kế hoạch chỉnh sửa", "lvs27b|open"),
)
assert "⬅️ Menu Video" in root_labels
assert "Mã hạng mục" not in summary
assert "REQUIRES_RUNTIME" not in summary
```

- [ ] **Step 2: Run RED**

Run:

```powershell
D:\TOANAAS\_venv311_restore400\Scripts\python.exe -m pytest -q --noconftest -p no:cacheprovider --basetemp .planning-assistant-red tests/test_p1_video_planning_assistant.py
```

Expected: behavioral failures for the old label/old catalog-first flow/raw technical summary, with no collection error.

- [ ] **Step 3: Add the minimal session schema**

The normalized session shape is:

```python
{
    "version": "27B",
    "plan_schema_version": 1,
    "session_id": sid,
    "plan_id": "",
    "screen": "goal",
    "history": [],
    "goal": "",
    "editing_brief": "",
    "platform_ratio": "",
    "source_duration": "",
    "target_duration": "",
    "available_assets": [],
    "priorities": [],
    "selected_operations": [],
    "processed_callback_ids": [],
    "sent_summary_fingerprint": "",
    "created_at": stamp,
    "updated_at": stamp,
}
```

Use allow-listed IDs and curated Vietnamese labels. Multi-select callbacks toggle a value; `assets_done`, `priorities_done` and `operations_done` require valid input. Single-choice callbacks auto-advance. The brief screen accepts one bounded Vietnamese text input through a pure `apply_text_input` function and also offers a guided `Bỏ qua` path.

- [ ] **Step 4: Produce an ordered human report**

Define one deterministic step sentence per public operation, for example:

```python
PUBLIC_OPERATION_STEPS = {
    "cut": "Cắt các đoạn thừa và giữ lại nội dung phục vụ mục tiêu chính.",
    "pace": "Sắp xếp lại nhịp dựng theo thời lượng thành phẩm đã chọn.",
    "reframe": "Chỉnh khung hình và vùng an toàn theo nền tảng đích.",
    "transitions": "Bổ sung chuyển cảnh tiết chế giữa các đoạn phù hợp.",
    "audio": "Cân âm lượng và làm rõ phần âm thanh chính.",
    "branding": "Đặt logo hoặc watermark từ tài nguyên người dùng đã có.",
    "qa": "Kiểm tra hình, tiếng, tỷ lệ và thời lượng trước khi xuất.",
}
```

Add a bounded keyword-to-operation adviser for common public words such as `nhanh`, `sản phẩm`, `sáng`, `âm lượng`, `logo`, `watermark`, `phụ đề`, `9:16`. Guided priorities remain authoritative and the user must confirm proposed operations. Preserve user-supplied time ranges in `editing_brief`; never invent a timestamp when the brief has none. Do not expose catalog IDs or readiness values.

- [ ] **Step 5: Run GREEN**

Run the same focused file. Expected: all planning assistant service tests pass.

### Task 3: Add owner-scoped lightweight persistence with TDD

**Files:**
- Create: `services/local_video_planning_store.py`
- Create: `tests/test_p1_video_planning_store.py`

- [ ] **Step 1: Write failing SQLite CRUD tests**

Use `sqlite3.connect(":memory:")` and require:

```python
store.ensure_schema(conn)
saved = store.save_plan(conn, user_id="7", chat_id="70", plan=plan)
assert store.get_plan(conn, user_id="7", chat_id="70", plan_id=saved["plan_id"])
assert len(store.list_plans(conn, user_id="7", chat_id="70")) == 1
assert store.get_plan(conn, user_id="8", chat_id="70", plan_id=saved["plan_id"]) is None
assert store.soft_delete_plan(conn, user_id="7", chat_id="70", plan_key=saved["plan_key"]) is True
```

Also require save with the same source session/fingerprint to update one row, optimistic version conflict to fail closed, malformed JSON to fail closed, and list results to be bounded and newest-first.

- [ ] **Step 2: Run RED**

Run:

```powershell
D:\TOANAAS\_venv311_restore400\Scripts\python.exe -m pytest -q --noconftest -p no:cacheprovider --basetemp .planning-store-red tests/test_p1_video_planning_store.py
```

Expected: import/module missing failure only.

- [ ] **Step 3: Implement the narrow store**

Create only this table and index:

```sql
CREATE TABLE IF NOT EXISTS local_video_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_key TEXT NOT NULL UNIQUE,
    owner_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    source_session_id TEXT NOT NULL,
    title TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    content_fingerprint TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '',
    UNIQUE(owner_id, chat_id, source_session_id)
);
CREATE INDEX IF NOT EXISTS idx_local_video_plans_owner_updated
ON local_video_plans(owner_id, chat_id, deleted_at, updated_at DESC);
```

The module accepts an existing SQLite connection, validates all public fields, parameterizes every query, enforces `owner_id + chat_id` on get/update/delete, uses optimistic `version` updates, and commits no wallet/job/project records. It exposes only `ensure_schema`, `save_plan_from_session`, `list_plans`, `get_plan`, `update_plan` and `soft_delete_plan`.

- [ ] **Step 4: Run GREEN**

Run the same store test file. Expected: all tests pass.

### Task 4: Connect Telegram delivery to the store without false side effects

**Files:**
- Modify: `bot.py`
- Modify: `tests/test_p1_localvideostudio27b_public_ui.py`

- [ ] **Step 1: Write failing adapter tests**

Tests must prove:

```python
# Durable save succeeds before copy may claim "Đã lưu".
assert persisted_calls == 1
assert provider_calls == 0
assert wallet_mutations == 0

# Failed Telegram confirmation does not duplicate or lose the already-saved plan.
assert persisted_rows == 1

# List/open/delete are owner-scoped and delete requires confirmation.

# One pending brief message belongs only to the exact planning session.
# It is consumed before generic chat/product text handlers and cannot mutate Video Edit state.
```

- [ ] **Step 2: Run RED**

Run only the exact adapter tests by node ID. Expected: failure because persistence/list callbacks are not connected.

- [ ] **Step 3: Add the minimal adapter integration**

Modify `bot.py` only to:

```python
from services import local_video_planning_store
from services import video_planning_assistant as local_video_studio_public

# inside init_db(), before the final commit
local_video_planning_store.ensure_schema(conn)
```

Then connect `persist`, `plans`, `view`, `edit`, `delete` and `delete_confirm` callbacks. Add one narrow pending-text handler for `editing_brief` before generic product/chat text routing; it is owner/chat/session scoped, length-bounded and cleared on consume/back/close/expiry. Reopen builds a new validated planning session from the stored plan. No callback routes to Video Edit or Product Video.

- [ ] **Step 4: Update public route copy**

Set the route matrix and menu label to:

```text
🧭 Lên kế hoạch chỉnh sửa
```

Keep `invoice_reachable=False` and `job_reachable=False`.

- [ ] **Step 5: Run GREEN**

Run the planning UI file and the store file together. Expected: zero failures.

### Task 5: Protected review and proportionate verification

**Files:**
- Review all changed files only.

- [ ] **Step 1: Inspect scope**

Run:

```powershell
git status --short
git diff --name-status
git diff --check
git diff -- bot.py services/video_planning_assistant.py services/local_video_planning_store.py tests/test_p1_video_planning_assistant.py tests/test_p1_localvideostudio27b_public_ui.py tests/test_p1_video_planning_store.py
```

Stop if Video Edit, Product Video, provider, payment, wallet, worker, ENV or deployment files changed.

- [ ] **Step 2: Run focused planning tests once**

```powershell
D:\TOANAAS\_venv311_restore400\Scripts\python.exe -m pytest -q --noconftest -p no:cacheprovider --basetemp .planning-assistant-green tests/test_p1_video_planning_assistant.py tests/test_p1_localvideostudio27b_public_ui.py tests/test_p1_video_planning_store.py
```

- [ ] **Step 3: Run route/back protected comparators**

```powershell
D:\TOANAAS\_venv311_restore400\Scripts\python.exe -m pytest -q --noconftest -p no:cacheprovider --basetemp .planning-route-green tests/test_p0_18k_video_menu_flow_standardization_routing_matrix.py tests/test_p0_18n1_unify_video_product_entry_ui_flow_matrix.py
```

- [ ] **Step 4: Compile changed Python**

```powershell
D:\TOANAAS\_venv311_restore400\Scripts\python.exe -m py_compile bot.py services/video_planning_assistant.py services/local_video_planning_store.py
```

- [ ] **Step 5: Run the project-required suite once**

Run `pytest -q` once only because repository `AGENTS.md` requires it. Do not repeat broad suites for vanity counts. If baseline failures exist, compare exact IDs with `origin/main` before claiming `NEW_FAILURES=0`.

- [ ] **Step 6: Report without shipping**

Report exact commands, exit codes, counts and changed files. Keep:

```text
PROVIDER_CALLS=0
WALLET_MUTATIONS=0
DEPLOY=NO
LIVE_PASS=NOT_TESTED
```

No push, PR, merge or deploy is authorized by this approval.
