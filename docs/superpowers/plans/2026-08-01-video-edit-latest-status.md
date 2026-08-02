# Video Edit Latest Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `📊 Trạng thái chỉnh sửa` entry inside Video Edit that reopens the requesting user's latest canonical local-edit job and keeps all status refresh callbacks usable without pending session state.

**Architecture:** Reuse the existing Video Edit six-stage status renderer and exact-job refresh keyboard. Add one bounded database read helper filtered by `user_id` and `video_editengine1.WORKER_JOB_TYPE`, one hub callback, and Vietnamese empty/unavailable views. Keep `latest_status`, `status`, and legacy `ai_status` stateless and separate from Product Video status/state.

**Tech Stack:** Python 3.12, python-telegram-bot inline callbacks, SQLite, pytest, existing TOAN AAS Video Edit state/engine contracts.

---

## File map

- Modify `bot.py`: add the hub row, route contract child, latest-owned-job read helper, empty/unavailable renderer, and stateless callback routing.
- Create `tests/test_p0_videoedit_latest_status_navigation.py`: focused runtime tests for layout, ownership, empty/error behavior, refresh after hub state clear, and zero-side-effect isolation.
- Modify `tests/test_p0_video_edit3_compact_manual_flow.py`: update the exact public hub/route contract lock without weakening the four-primary-action invariant.
- Modify `tests/test_p1_localvideostudio27b_public_ui.py`: preserve the exact flag-off/flag-on row matrix while accounting for the independent status row.
- Modify `tests/test_p0_videoedit_canonical_bot_routes.py`: lock `status` and `ai_status` as read-only stateless callbacks.

No service, worker, database schema, Product Video, SubDub, Frame Video, Local Video Studio, provider, wallet, or deployment file changes for this feature.

### Task 1: Write and prove the focused RED contract

**Files:**
- Create: `tests/test_p0_videoedit_latest_status_navigation.py`
- Modify: `tests/test_p0_video_edit3_compact_manual_flow.py`
- Modify: `tests/test_p1_localvideostudio27b_public_ui.py`
- Modify: `tests/test_p0_videoedit_canonical_bot_routes.py`

- [ ] **Step 1: Add shared focused-test helpers and hub layout tests**

Create `tests/test_p0_videoedit_latest_status_navigation.py` with the imports,
callback fakes, and first contract tests below:

```python
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot


def _rows(markup) -> list[list[tuple[str, str]]]:
    return [
        [(str(button.text), str(button.callback_data or "")) for button in row]
        for row in markup.inline_keyboard
    ]


class _Message:
    chat_id = 991_001

    async def reply_text(self, _text: str, **_kwargs):
        return None


class _Query:
    def __init__(self, user_id: int, data: str) -> None:
        self.id = f"latest-status-{user_id}-{data}"
        self.from_user = SimpleNamespace(id=user_id, first_name="Status")
        self.data = data
        self.message = _Message()
        self.edits: list[tuple[str, dict]] = []
        self.answers: list[tuple[tuple, dict]] = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def edit_message_text(self, text: str, **kwargs):
        self.edits.append((text, kwargs))


def _press(user_id: int, callback: str) -> _Query:
    query = _Query(user_id, callback)
    asyncio.run(
        bot.handle_video_editor_callback(
            SimpleNamespace(callback_query=query),
            SimpleNamespace(user_data={}),
        )
    )
    return query


def test_videoedit_hub_adds_one_secondary_status_row_without_changing_primary_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bot, "local_video_studio_public_enabled", lambda: False)
    rows = _rows(bot.video_edit_hub_keyboard("vi"))

    assert rows[:2] == [
        [
            ("✨ Chỉnh sửa theo mục tiêu", "videoedit|ai"),
            ("✂️ Chỉnh sửa thủ công", "videoedit|manual"),
        ],
        [
            ("🧹 Nâng chất lượng video", "videoedit|restore"),
            ("❓ Hướng dẫn công cụ này", "videoedit|guide"),
        ],
    ]
    assert rows[2] == [("📊 Trạng thái chỉnh sửa", "videoedit|latest_status")]
    assert rows[-1] == [
        ("⬅️ Quay lại", "menu|main_video"),
        ("🏠 Menu chính", "menu|main"),
    ]
    assert sum(callback == "videoedit|latest_status" for row in rows for _, callback in row) == 1


def test_videoedit_status_row_stays_independent_of_optional_planning_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bot, "local_video_studio_public_enabled", lambda: True)
    rows = _rows(bot.video_edit_hub_keyboard("vi"))

    assert rows[2] == [("📊 Trạng thái chỉnh sửa", "videoedit|latest_status")]
    assert rows[3] == [("🧭 Lập kế hoạch dựng video", "lvs27b|open")]
    assert rows[-1][0][1] == "menu|main_video"


def test_top_level_video_menu_does_not_gain_a_videoedit_status_button() -> None:
    source = Path(bot.__file__).read_text(encoding="utf-8")
    start = source.index("def main_video_keyboard")
    end = source.index("\ndef ", start + 5)

    assert "videoedit|latest_status" not in source[start:end]
```

- [ ] **Step 2: Add latest-owned-job lookup tests**

Append a real SQLite fixture and ownership test:

```python
def _create_worker_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """CREATE TABLE local_worker_jobs (
                id INTEGER PRIMARY KEY,
                user_id TEXT,
                command TEXT,
                job_type TEXT,
                status TEXT,
                provider TEXT,
                input_file_id TEXT,
                output_file_id TEXT,
                output_url TEXT,
                error_short TEXT,
                created_at TEXT,
                started_at TEXT,
                finished_at TEXT,
                xu_cost INTEGER,
                admin_only INTEGER,
                worker_id TEXT,
                updated_at TEXT
            )"""
        )
        rows = [
            (10, "700", "video_editengine1", "video_local_edit", "succeeded"),
            (11, "701", "video_editengine1", "video_local_edit", "queued"),
            (12, "700", "product_video", "product_video", "running"),
            (13, "700", "video_editengine1", "video_local_edit", "running"),
            (14, "700", "legacy_ai", "video_ai_edit", "queued"),
        ]
        conn.executemany(
            """INSERT INTO local_worker_jobs
               (id,user_id,command,job_type,status,provider,input_file_id,
                output_file_id,output_url,error_short,created_at,started_at,
                finished_at,xu_cost,admin_only,worker_id,updated_at)
               VALUES (?,?,?,?,?,'local_worker','{}','','','','2026-08-01',
                       '', '',0,0,'worker','2026-08-01')""",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def test_latest_videoedit_job_is_newest_owned_local_edit_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "latest-status.sqlite3"
    _create_worker_db(db_path)
    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(db_path))

    assert bot.get_latest_video_editor_job(700)["id"] == 13
    assert bot.get_latest_video_editor_job(701)["id"] == 11
    assert bot.get_latest_video_editor_job(999) == {}
```

- [ ] **Step 3: Add no-state callback, privacy, empty, and database-error tests**

Append these behavior tests. They deliberately clear pending editor state before
every read route:

```python
def _owned_job(user_id: int, job_id: int = 77) -> dict:
    return {
        "id": job_id,
        "user_id": str(user_id),
        "command": "video_editengine1",
        "job_type": bot.video_editengine1.WORKER_JOB_TYPE,
        "status": "queued",
        "provider": "local_worker",
        "error_short": '{"local1":true,"stage":"received"}',
        "xu_cost": 0,
    }


def test_latest_status_opens_without_pending_state_and_refreshes_exact_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 702
    bot.clear_video_editor_pending(user_id)
    job = _owned_job(user_id)
    monkeypatch.setattr(bot, "get_latest_video_editor_job", lambda uid: job if uid == user_id else {})
    monkeypatch.setattr(bot, "video_editengine1_job_for_worker", lambda _job_id: {})

    opened = _press(user_id, "videoedit|latest_status")
    assert "Trạng thái chỉnh sửa video" in opened.edits[-1][0]
    assert "videoedit|status|77" in [callback for row in _rows(opened.edits[-1][1]["reply_markup"]) for _, callback in row]
    assert bot.get_video_editor_pending(user_id) is None

    monkeypatch.setattr(bot, "get_local_worker_job", lambda job_id: job if job_id == 77 else {})
    refreshed = _press(user_id, "videoedit|status|77")
    assert "#77" in refreshed.edits[-1][0]
    assert not refreshed.answers or not refreshed.answers[-1][1].get("show_alert")


def test_latest_status_has_useful_empty_state_and_exact_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 703
    bot.clear_video_editor_pending(user_id)
    monkeypatch.setattr(bot, "get_latest_video_editor_job", lambda _uid: {})

    query = _press(user_id, "videoedit|latest_status")
    text, kwargs = query.edits[-1]
    callbacks = [callback for row in _rows(kwargs["reply_markup"]) for _, callback in row]
    assert "chưa có tác vụ chỉnh sửa video" in text.lower()
    assert callbacks == ["videoedit|hub", "menu|main"]
    assert bot.get_video_editor_pending(user_id) is None


def test_latest_status_database_failure_is_sanitized_and_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 704
    bot.clear_video_editor_pending(user_id)

    def fail_lookup(_uid):
        raise sqlite3.OperationalError("private/database/path")

    monkeypatch.setattr(bot, "get_latest_video_editor_job", fail_lookup)
    query = _press(user_id, "videoedit|latest_status")
    text = query.edits[-1][0]
    assert "chưa đọc được trạng thái" in text.lower()
    assert "private/database/path" not in text
    assert bot.get_video_editor_pending(user_id) is None


def test_legacy_ai_status_remains_read_only_without_pending_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 705
    bot.clear_video_editor_pending(user_id)
    job = _owned_job(user_id, 78)
    monkeypatch.setattr(bot, "get_local_worker_job", lambda job_id: job if job_id == 78 else {})
    monkeypatch.setattr(bot, "video_editengine1_job_for_worker", lambda _job_id: {})

    query = _press(user_id, "videoedit|ai_status|78")
    assert "Trạng thái chỉnh sửa video" in query.edits[-1][0]
    assert bot.get_video_editor_pending(user_id) is None
```

- [ ] **Step 4: Update exact source-lock tests to require the new contract**

In `tests/test_p0_video_edit3_compact_manual_flow.py`, keep the four primary
callback assertions and add:

```python
assert keyboard.count('"videoedit|latest_status"') == 1
assert '"expected_children": (' in route
assert '"videoedit|latest_status"' in route
```

In `tests/test_p1_localvideostudio27b_public_ui.py`, change the exact flag-off
and flag-on expected callback rows to:

```python
assert [[button.callback_data for button in row] for row in off_rows] == [
    ["videoedit|ai", "videoedit|manual"],
    ["videoedit|restore", "videoedit|guide"],
    ["videoedit|latest_status"],
    ["menu|main_video", "menu|main"],
]

assert [[button.callback_data for button in row] for row in on_rows] == [
    ["videoedit|ai", "videoedit|manual"],
    ["videoedit|restore", "videoedit|guide"],
    ["videoedit|latest_status"],
    ["lvs27b|open"],
    ["menu|main_video", "menu|main"],
]
```

In `tests/test_p0_videoedit_canonical_bot_routes.py`, add a source-contract
test requiring all three read routes before the session-expiry guard:

```python
def test_videoedit_status_routes_are_stateless_reads_after_hub_clear() -> None:
    callback = _function_source("handle_video_editor_callback")
    stateless = callback[callback.index("VIDEO_EDIT_STATELESS_ACTIONS"):callback.index("VIDEO_EDIT_COMPAT_UPLOAD_ACTIONS")]
    assert all(action in stateless for action in ('"latest_status"', '"status"', '"ai_status"'))
```

- [ ] **Step 5: Run the focused RED tests and record the expected failures**

Run:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest -q --noconftest tests/test_p0_videoedit_latest_status_navigation.py tests/test_p0_video_edit3_compact_manual_flow.py tests/test_p1_localvideostudio27b_public_ui.py tests/test_p0_videoedit_canonical_bot_routes.py
```

Expected before implementation: failures specifically for missing
`videoedit|latest_status`, missing `get_latest_video_editor_job`, missing
empty/error renderers, route-matrix mismatch, and `status`/`ai_status` being
blocked after pending state is cleared. Existing unrelated nodes must not fail.

- [ ] **Step 6: Commit the RED tests as the second task commit**

```powershell
git add -- tests/test_p0_videoedit_latest_status_navigation.py tests/test_p0_video_edit3_compact_manual_flow.py tests/test_p1_localvideostudio27b_public_ui.py tests/test_p0_videoedit_canonical_bot_routes.py
git commit -m "test(video-edit): lock latest status navigation"
```

### Task 2: Implement the minimal read-only status entry

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Add the latest-owned-job query beside the existing worker-job readers**

Insert after `get_local_worker_job()`:

```python
def get_latest_video_editor_job(user_id) -> dict:
    conn = db_connect()
    try:
        row = conn.execute(
            """SELECT id,user_id,command,job_type,status,provider,input_file_id,
                      output_file_id,output_url,error_short,created_at,started_at,
                      finished_at,xu_cost,admin_only,worker_id,updated_at
               FROM local_worker_jobs
               WHERE user_id=? AND job_type=?
               ORDER BY id DESC
               LIMIT 1""",
            (str(user_id), video_editengine1.WORKER_JOB_TYPE),
        ).fetchone()
        return local_worker_job_from_row(row)
    finally:
        conn.close()
```

This function has no mutation, no admin exception, no fallback job type, and no
media/body read.

- [ ] **Step 2: Add the secondary hub row and public route contract child**

In `video_edit_hub_keyboard()`, append the row immediately after the two primary
rows and before the optional planning row:

```python
rows.append([
    (
        "📊 Trạng thái chỉnh sửa" if is_vi else "📊 Edit status",
        "videoedit|latest_status",
    )
])
```

Update `VIDEO_PUBLIC_ROUTE_MATRIX["video_local_edit"]["expected_children"]` to:

```python
(
    "videoedit|ai",
    "videoedit|manual",
    "videoedit|restore",
    "videoedit|guide",
    "videoedit|latest_status",
)
```

- [ ] **Step 3: Add bounded empty/unavailable renderers**

Insert beside `video_editor_status_keyboard()`:

```python
def video_editor_latest_status_fallback_keyboard(lang: str = "vi") -> InlineKeyboardMarkup:
    return video_scene3_keyboard([[
        (
            "⬅️ Chỉnh sửa video" if normalize_user_language(lang) == "vi" else "⬅️ Video Edit",
            "videoedit|hub",
        ),
        (ui_text(lang, "common.main_menu"), "menu|main"),
    ]])


def video_editor_latest_status_empty_text(lang: str = "vi") -> str:
    if normalize_user_language(lang) != "vi":
        return "📊 <b>Edit status</b>\n\nYou have not submitted a Video Edit task yet."
    return (
        "📊 <b>Trạng thái chỉnh sửa video</b>\n\n"
        "Anh/chị chưa có tác vụ Chỉnh sửa video nào. Hãy quay lại, chọn thao tác, "
        "gửi video và xác nhận khi kế hoạch đã đúng."
    )


def video_editor_latest_status_unavailable_text(lang: str = "vi") -> str:
    if normalize_user_language(lang) != "vi":
        return "⚠️ <b>Edit status is temporarily unavailable</b>\n\nNo task was changed. Please try again later."
    return (
        "⚠️ <b>Chưa đọc được trạng thái chỉnh sửa</b>\n\n"
        "Hệ thống chưa thay đổi tác vụ, chưa tạo file và chưa trừ Xu. "
        "Anh/chị có thể thử lại sau."
    )
```

- [ ] **Step 4: Make all status callbacks explicitly stateless and split-safe**

Extend `VIDEO_EDIT_STATELESS_ACTIONS` with:

```python
"latest_status", "status", "ai_status",
```

Extend `split_owned_allowed_actions` in
`video_editor_split_callback_allowed()` with:

```python
"latest_status",
"ai_status",
```

`status` is already in that split allowlist and remains there.

- [ ] **Step 5: Route latest status before any stateful editing branches**

Immediately after the session-expiry and split-owner guards, add:

```python
if action == "latest_status":
    try:
        job = get_latest_video_editor_job(uid)
    except sqlite3.Error as exc:
        logger.warning(
            "videoedit latest status lookup failed | error=%s",
            sanitize_log_text(str(exc))[:180],
        )
        return await safe_edit_or_send(
            query,
            video_editor_latest_status_unavailable_text(lang),
            parse_mode="HTML",
            reply_markup=video_editor_latest_status_fallback_keyboard(lang),
        )
    if not job:
        return await safe_edit_or_send(
            query,
            video_editor_latest_status_empty_text(lang),
            parse_mode="HTML",
            reply_markup=video_editor_latest_status_fallback_keyboard(lang),
        )
    job_id = safe_int(job.get("id"), 0)
    return await safe_edit_or_send(
        query,
        video_editor_job_status_text(job, lang),
        parse_mode="HTML",
        reply_markup=video_editor_status_keyboard(job_id, lang),
    )
```

Do not call `video_b14_queue_status_text()`, update pending state, clear another
product's state, requeue work, deliver media, or change accounting.

- [ ] **Step 6: Run focused GREEN tests**

Run the exact Task 1 command again.

Expected: all selected tests pass; there are no newly deselected or skipped
nodes and the previously recorded failures are closed by production behavior.

- [ ] **Step 7: Commit the production implementation as the third task commit**

```powershell
git add -- bot.py
git commit -m "feat(video-edit): reopen latest job status"
```

### Task 3: Verify status truth, route isolation, and legacy compatibility

**Files:**
- Test only; no planned production edits.

- [ ] **Step 1: Run the focused Video Edit status/route/state cluster**

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest -q --noconftest tests/test_p0_videoedit_latest_status_navigation.py tests/test_p0_videoedit_review_parent_hardening.py tests/test_p0_videoedit_canonical_bot_routes.py tests/test_p0_videoedit_canonical_navigation.py tests/test_p0_videoedit_back_hierarchy_adapter.py tests/test_p0_video_statusrestore18_old_status_only.py tests/test_p0_video_tailflow16_dedupe_summary_audio_status.py
```

Expected: PASS with no session-expiry failure for `latest_status`, `status`, or
`ai_status`; no `NameError` in legacy status recovery; exact Back hierarchy
remains green.

- [ ] **Step 2: Run engine, worker, safety, and real-media Video Edit tests**

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest -q --noconftest tests/test_p0_video_editengine1_local_render_status_delivery.py tests/test_p0_video_editengine2_buttons_worker_heartbeat_package.py tests/test_p0_videoedit_canonical_local_runtime.py tests/test_p0_videoedit_canonical_local_worker_receipt.py tests/test_p0_videoedit_job_safety.py tests/test_p0_videoedit_local_free_job.py tests/test_p0_videoedit_split_receipt_checkpoint.py tests/test_p0_videoedit_real_media_matrix.py
```

Expected: PASS; valid local media outputs and canonical receipt/delivery truth
remain unchanged.

- [ ] **Step 3: Run cross-product UI and callback isolation regressions**

Run the repository's accepted callback-owner, Product Video UI-freeze, SubDub
receipt-truth, Local Video Studio 27A/27B, and RouteEngine29 selectors recorded
in the completion-hardening plan. Expected results are identical to clean-main
comparators except for the intentionally added Video Edit status callback.

- [ ] **Step 4: Run compile and static gates**

```powershell
python -m py_compile bot.py local_worker.py services/video_edit_capabilities.py services/video_edit_state_machine.py services/video_editengine1.py services/video_local_editing.py services/video_local_validation.py
python -c "import pathlib,tokenize; f=pathlib.Path('bot.py').open('rb'); tokenize.tokenize(f.readline); f.close()"
git diff --check
```

Expected: exit code 0 for each command. Run the existing narrow adapter AST,
scope guard, callback collision, cross-product route, secret, and private-path
scans from the completion-hardening plan and require zero new findings.

### Task 4: Review, latest-main integration, and ship gate

**Files:**
- Review all branch files; modify only in response to a proven Video Edit blocker.

- [ ] **Step 1: Request independent spec and code-quality reviews**

Require reviewers to check user isolation, status truth, stateless refresh,
Product Video non-use, DB connection closure, failure copy, no state mutation,
and callback/backstack ownership. Every valid blocker gets a focused RED test
before a fix.

- [ ] **Step 2: Audit the three-commit structure**

```powershell
git log --oneline --decorate origin/main..HEAD
git show --stat --oneline b9aa99d
```

Expected logical commits:

1. design + implementation plan;
2. tests;
3. production implementation.

- [ ] **Step 3: Fetch latest main and review every intervening path**

```powershell
git fetch origin --prune
git log --oneline HEAD..origin/main
git diff --name-status HEAD..origin/main
```

Stop before rebase if latest main changes Video Edit route/engine/state/backstack,
the same tests, shared callback ownership, or another path that conflicts with
this branch. Otherwise rebase without squashing and preserve all three commits.

- [ ] **Step 4: Rerun the exact focused, full Video Edit, comparator, compile, and static gates on the rebased head**

Expected: no new failure-set or collected-node delta versus the clean latest-main
comparator; every intentionally changed exact-layout test is green.

- [ ] **Step 5: Push and open one non-draft PR**

Use `--force-with-lease` only if the already-published branch was rebased. Do
not squash or merge. Record design/test/implementation SHAs, pushed PR head,
changed-file scope, non-draft state, and the initial CI/check status honestly.

- [ ] **Step 6: Stop after the PR opens**

Do not merge. Do not deploy Railway, change ENV, touch VPS/worker/webhook, run
production Telegram smoke, upload media, call providers/workers, create jobs,
mutate wallet/Xu, or deliver media unless the owner opens a separate gate.
