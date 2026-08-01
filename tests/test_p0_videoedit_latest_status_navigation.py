from __future__ import annotations

import asyncio
import html
import sqlite3
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    markers = (f"async def {name}(", f"def {name}(")
    starts = [BOT_SOURCE.find(marker) for marker in markers]
    starts = [position for position in starts if position >= 0]
    if not starts:
        raise AssertionError(f"missing function: {name}")
    start = min(starts)
    following = [
        position
        for position in (
            BOT_SOURCE.find("\ndef ", start + 1),
            BOT_SOURCE.find("\nasync def ", start + 1),
            BOT_SOURCE.find("\n@", start + 1),
        )
        if position >= 0
    ]
    end = min(following) if following else len(BOT_SOURCE)
    return BOT_SOURCE[start:end].rstrip() + "\n"


def _compile_function(name: str, namespace: dict):
    exec(
        compile(
            "from __future__ import annotations\n\n" + _function_source(name),
            filename="bot.py",
            mode="exec",
        ),
        namespace,
    )
    return namespace[name]


class _Button:
    def __init__(self, text: str, callback_data: str) -> None:
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, rows) -> None:
        self.inline_keyboard = rows


class _Query:
    def __init__(self, user_id: int, callback_data: str) -> None:
        self.id = f"latest-status-{user_id}-{callback_data}"
        self.from_user = SimpleNamespace(id=user_id)
        self.data = callback_data
        self.answers: list[tuple[tuple, dict]] = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))
        return True


def _job_db(path: Path) -> None:
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
        conn.commit()
    finally:
        conn.close()


def _insert_job(path: Path, job_id: int, user_id: int, job_type: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """INSERT INTO local_worker_jobs
               (id,user_id,command,job_type,status,provider,input_file_id,created_at,xu_cost,admin_only,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job_id,
                str(user_id),
                "video_editengine1",
                job_type,
                "queued",
                "local_worker",
                "{}",
                f"2026-08-01 00:00:{job_id:02d}",
                0,
                0,
                f"2026-08-01 00:00:{job_id:02d}",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _db_connect(path: Path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _status_text(job: dict) -> str:
    progress = _compile_function(
        "video_local_job_progress_payload", {"json": __import__("json")}
    )
    status = _compile_function(
        "video_editor_job_status_text",
        {
            "video_local_job_progress_payload": progress,
            "video_editengine1_job_for_worker": lambda _job_id: {},
            "safe_int": lambda value, default=0: int(value or default),
            "html": html,
        },
    )
    return status(job, "vi")


def _status_keyboard(job_id: int):
    keyboard = _compile_function(
        "video_editor_status_keyboard",
        {
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "normalize_user_language": lambda _lang: "vi",
            "ui_text": lambda _lang, key: {
                "common.back": "⬅️ Quay lại",
                "common.main_menu": "🏠 Menu chính",
            }[key],
        },
    )
    return keyboard(job_id, "vi")


def _latest_status_fallback_keyboard():
    keyboard = _compile_function(
        "video_editor_latest_status_fallback_keyboard",
        {
            "video_scene3_keyboard": lambda rows: _Markup(
                [[_Button(label, callback) for label, callback in row] for row in rows]
            ),
            "normalize_user_language": lambda _lang: "vi",
            "ui_text": lambda _lang, key: {
                "common.main_menu": "🏠 Menu chính",
            }[key],
        },
    )
    return keyboard("vi")


def _latest_status_text(function_name: str) -> str:
    renderer = _compile_function(
        function_name,
        {"normalize_user_language": lambda _lang: "vi"},
    )
    return renderer("vi")


def _handler(get_latest, get_job, *, user_id: int = 41, pending: dict | None = None):
    rendered: list[tuple[str, object]] = []
    state = deepcopy(pending or {})

    async def render(_query, text: str, **kwargs):
        rendered.append((text, kwargs.get("reply_markup")))
        return True

    handler = _compile_function(
        "handle_video_editor_callback",
        {
            "get_user_language": lambda _uid: "vi",
            "get_video_editor_pending": lambda _uid: deepcopy(state),
            "video_edit_state_machine": SimpleNamespace(
                requested_group=lambda _action: "",
                canonical_compatibility_action=lambda action: action,
            ),
            "video_editor_normalize_action": lambda action: action,
            "safe_edit_or_send": render,
            "get_latest_video_editor_job": get_latest,
            "get_local_worker_job": get_job,
            "video_editengine1": SimpleNamespace(WORKER_JOB_TYPE="video_local_edit"),
            "video_editor_job_status_text": lambda job, _lang: _status_text(job),
            "video_editor_status_keyboard": lambda job_id, _lang: _status_keyboard(job_id),
            "video_editor_latest_status_fallback_keyboard": lambda _lang: _latest_status_fallback_keyboard(),
            "video_editor_latest_status_empty_text": lambda _lang: _latest_status_text(
                "video_editor_latest_status_empty_text"
            ),
            "video_editor_latest_status_unavailable_text": lambda _lang: _latest_status_text(
                "video_editor_latest_status_unavailable_text"
            ),
            "video_editor_split_callback_allowed": _compile_function(
                "video_editor_split_callback_allowed", {}
            ),
            "is_admin_user": lambda _uid: False,
            "safe_int": lambda value, default=0: int(value or default),
            "sqlite3": sqlite3,
            "logger": SimpleNamespace(warning=lambda *_args, **_kwargs: None),
            "sanitize_log_text": lambda value: str(value),
        },
    )
    return handler, rendered, state, _Query(user_id, "videoedit|latest_status")


def test_hub_has_one_status_row_after_four_primary_actions_and_no_legacy_video_menu_status() -> None:
    hub = _function_source("video_edit_hub_keyboard")
    expected_primary = (
        '"videoedit|ai"',
        '"videoedit|manual"',
        '"videoedit|restore"',
        '"videoedit|guide"',
    )
    assert all(hub.count(callback) == 1 for callback in expected_primary)
    assert [hub.index(callback) for callback in expected_primary] == sorted(
        hub.index(callback) for callback in expected_primary
    )
    assert hub.count('"videoedit|latest_status"') == 1
    assert hub.index('"videoedit|guide"') < hub.index('"videoedit|latest_status"')
    assert hub.index('"videoedit|latest_status"') < hub.index('"lvs27b|open"')
    assert '"📊 Trạng thái chỉnh sửa"' in hub
    assert "latest_status" not in _function_source("video_editor_menu_keyboard")
    assert "latest_status" not in _function_source("main_video_keyboard")


def test_latest_lookup_returns_only_newest_owned_exact_local_edit_job(tmp_path: Path) -> None:
    path = tmp_path / "latest-status.sqlite3"
    _job_db(path)
    _insert_job(path, 1, 41, "video_local_edit")
    _insert_job(path, 2, 99, "video_local_edit")
    _insert_job(path, 3, 41, "product_video")
    _insert_job(path, 4, 41, "video_ai_edit")
    _insert_job(path, 5, 41, "video_local_edit")
    lookup = _compile_function(
        "get_latest_video_editor_job",
        {
            "db_connect": lambda: _db_connect(path),
            "video_editengine1": SimpleNamespace(WORKER_JOB_TYPE="video_local_edit"),
            "local_worker_job_from_row": lambda row: dict(row) if row else {},
        },
    )

    assert lookup(41)["id"] == 5
    assert lookup(99)["id"] == 2
    assert lookup(404) == {}


def test_latest_lookup_closes_its_read_connection(tmp_path: Path) -> None:
    path = tmp_path / "latest-status-close.sqlite3"
    _job_db(path)
    _insert_job(path, 6, 41, "video_local_edit")
    connection = _db_connect(path)
    lookup = _compile_function(
        "get_latest_video_editor_job",
        {
            "db_connect": lambda: connection,
            "video_editengine1": SimpleNamespace(WORKER_JOB_TYPE="video_local_edit"),
            "local_worker_job_from_row": lambda row: dict(row) if row else {},
        },
    )

    assert lookup(41)["id"] == 6
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT 1")


def test_latest_lookup_propagates_sqlite_error_for_distinct_unavailable_copy() -> None:
    lookup = _compile_function(
        "get_latest_video_editor_job",
        {
            "db_connect": lambda: (_ for _ in ()).throw(sqlite3.OperationalError("db unavailable")),
            "video_editengine1": SimpleNamespace(WORKER_JOB_TYPE="video_local_edit"),
            "local_worker_job_from_row": lambda row: dict(row) if row else {},
        },
    )

    with pytest.raises(sqlite3.OperationalError, match="db unavailable"):
        lookup(41)


def test_latest_status_renders_owned_job_after_pending_state_is_cleared_with_six_stage_refresh() -> None:
    job = {"id": 71, "user_id": "41", "job_type": "video_local_edit", "status": "queued", "xu_cost": 0}
    calls: list[int] = []
    handler, rendered, state, query = _handler(
        lambda uid: calls.append(uid) or job,
        lambda _job_id: job,
    )

    assert asyncio.run(handler(SimpleNamespace(callback_query=query, effective_user=query.from_user), SimpleNamespace())) is True
    assert calls == [41]
    assert state == {}
    assert len(rendered) == 1
    text, markup = rendered[0]
    assert all(label in text for label in (
        "Nhận video", "Kiểm tra cấu hình", "Chuẩn bị file", "Chỉnh sửa video", "Kiểm tra MP4", "Gửi kết quả",
    ))
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "videoedit|status|71" in callbacks
    assert "videoedit|hub" in callbacks


def test_latest_status_empty_is_useful_vietnamese_and_back_to_exact_hub() -> None:
    handler, rendered, state, query = _handler(lambda _uid: {}, lambda _job_id: {})
    assert asyncio.run(handler(SimpleNamespace(callback_query=query, effective_user=query.from_user), SimpleNamespace())) is True
    assert state == {}
    assert len(rendered) == 1
    text, markup = rendered[0]
    assert "chưa có tác vụ chỉnh sửa video" in text.lower()
    assert len(text) <= 360
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert callbacks == ["videoedit|hub", "menu|main"]


def test_latest_status_database_failure_is_sanitized_and_back_to_exact_hub() -> None:
    def latest(_uid):
        raise sqlite3.OperationalError("db unavailable /private/path")

    handler, rendered, state, query = _handler(latest, lambda _job_id: {})
    assert asyncio.run(handler(SimpleNamespace(callback_query=query, effective_user=query.from_user), SimpleNamespace())) is True
    assert state == {}
    assert len(rendered) == 1
    text, markup = rendered[0]
    assert "chưa đọc được trạng thái chỉnh sửa" in text.lower()
    assert len(text) <= 360
    assert "db unavailable" not in text
    assert "/private/path" not in text
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert callbacks == ["videoedit|hub", "menu|main"]


@pytest.mark.parametrize("action", ["status|71", "ai_status|71"])
def test_existing_status_refreshes_remain_owned_and_stateless_after_hub_clear(action: str) -> None:
    job = {"id": 71, "user_id": "41", "job_type": "video_local_edit", "status": "queued", "xu_cost": 0}
    handler, rendered, state, query = _handler(lambda _uid: job, lambda _job_id: job)
    query.data = f"videoedit|{action}"

    assert asyncio.run(handler(SimpleNamespace(callback_query=query, effective_user=query.from_user), SimpleNamespace())) is True
    assert state == {}
    assert len(rendered) == 1
    assert "Trạng thái chỉnh sửa video" in rendered[0][0]


def test_latest_status_never_uses_admin_or_owner_privilege_to_read_another_users_job() -> None:
    callback = _function_source("handle_video_editor_callback")
    start = callback.index('if action == "latest_status":')
    end = callback.index("\n    if ", start + 1)
    latest = callback[start:end]
    assert "get_latest_video_editor_job(uid)" in latest
    assert "parts[2]" not in latest
    assert "is_admin_user" not in latest
    assert "product_video" not in latest
    assert "set_video_editor_pending" not in latest
    assert "update_video_editor_pending" not in latest
    assert "submit_video_edit" not in latest
    assert "create_job" not in latest
    assert "provider" not in latest
    assert "worker" not in latest
    assert "wallet" not in latest
    assert "send_video" not in latest
