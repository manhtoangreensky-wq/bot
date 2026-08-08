from __future__ import annotations

import asyncio
import ast
import html
import json
import sqlite3
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
ENGINE_SOURCE = (ROOT / "services" / "video_editengine1.py").read_text(encoding="utf-8")
_HANDLER_NAMESPACE: dict | None = None
_HANDLER_FUNCTION = None


@lru_cache(maxsize=2)
def _top_level_function_sources(source: str) -> dict[str, str]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    return {
        node.name: "".join(lines[node.lineno - 1 : node.end_lineno]).rstrip() + "\n"
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.end_lineno is not None
    }


def _function_source(name: str, source: str = BOT_SOURCE) -> str:
    function_source = _top_level_function_sources(source).get(name)
    if function_source is None:
        raise AssertionError(f"missing function: {name}")
    return function_source


def _compile_function(name: str, namespace: dict, source: str = BOT_SOURCE):
    exec(
        compile(
            "from __future__ import annotations\n\n" + _function_source(name, source),
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


def _status_text(
    job: dict,
    lang: str = "vi",
    canonical: dict | None = None,
) -> str:
    progress = _compile_function(
        "video_local_job_progress_payload", {"json": __import__("json")}
    )
    status = _compile_function(
        "video_editor_job_status_text",
        {
            "video_local_job_progress_payload": progress,
            "video_editengine1_job_for_worker": lambda _job_id: dict(canonical or {}),
            "safe_int": lambda value, default=0: int(value or default),
            "html": html,
            "normalize_user_language": lambda value: str(value or "vi").lower(),
        },
    )
    return status(job, lang)


def _status_keyboard(job_id: int, lang: str = "vi"):
    keyboard = _compile_function(
        "video_editor_status_keyboard",
        {
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "normalize_user_language": lambda value: str(value or "vi").lower(),
            "ui_text": lambda value, key: {
                "common.back": "⬅️ Quay lại" if value == "vi" else "⬅️ Back",
                "common.main_menu": "🏠 Menu chính" if value == "vi" else "🏠 Main menu",
            }[key],
        },
    )
    return keyboard(job_id, lang)


def _latest_status_fallback_keyboard(lang: str = "vi"):
    keyboard = _compile_function(
        "video_editor_latest_status_fallback_keyboard",
        {
            "video_scene3_keyboard": lambda rows: _Markup(
                [[_Button(label, callback) for label, callback in row] for row in rows]
            ),
            "normalize_user_language": lambda value: str(value or "vi").lower(),
            "ui_text": lambda value, key: {
                "common.main_menu": "🏠 Menu chính" if value == "vi" else "🏠 Main menu",
            }[key],
        },
    )
    return keyboard(lang)


def _latest_status_text(function_name: str, lang: str = "vi") -> str:
    renderer = _compile_function(
        function_name,
        {"normalize_user_language": lambda value: str(value or "vi").lower()},
    )
    return renderer(lang)


def _handler(
    get_latest,
    get_job,
    *,
    user_id: int = 41,
    pending: dict | None = None,
    lang: str = "vi",
    log_messages: list[str] | None = None,
    status_renderer=None,
):
    global _HANDLER_FUNCTION, _HANDLER_NAMESPACE

    rendered: list[tuple[str, object]] = []
    state = deepcopy(pending or {})

    async def render(_query, text: str, **kwargs):
        rendered.append((text, kwargs.get("reply_markup")))
        return True

    def warning(message: str, *args) -> None:
        if log_messages is not None:
            log_messages.append(message % args if args else message)

    dependencies = {
        "get_user_language": lambda _uid: lang,
        "get_video_editor_pending": lambda _uid: deepcopy(state),
        "video_editor_state_snapshot": lambda value: deepcopy(dict(value or {})),
        "video_edit_state_machine": SimpleNamespace(
            requested_group=lambda _action: "",
            canonical_compatibility_action=lambda action: action,
        ),
        "video_editor_normalize_action": lambda action: action,
        "safe_edit_or_send": render,
        "get_latest_video_editor_job": get_latest,
        "get_local_worker_job_readonly": get_job,
        "video_editengine1": SimpleNamespace(WORKER_JOB_TYPE="video_local_edit"),
        "video_editor_job_status_text": status_renderer
        or (lambda job, selected_lang: _status_text(job, selected_lang)),
        "video_editor_status_keyboard": lambda job_id, selected_lang: _status_keyboard(job_id, selected_lang),
        "video_editor_latest_status_fallback_keyboard": lambda selected_lang: _latest_status_fallback_keyboard(selected_lang),
        "video_editor_latest_status_empty_text": lambda selected_lang: _latest_status_text(
            "video_editor_latest_status_empty_text", selected_lang
        ),
        "video_editor_latest_status_unavailable_text": lambda selected_lang: _latest_status_text(
            "video_editor_latest_status_unavailable_text", selected_lang
        ),
        "video_editor_split_callback_allowed": _compile_function(
            "video_editor_split_callback_allowed", {}
        ),
        "is_admin_user": lambda _uid: False,
        "safe_int": lambda value, default=0: int(value or default),
        "sqlite3": sqlite3,
        "logger": SimpleNamespace(warning=warning),
        "sanitize_log_text": lambda value: str(value),
    }
    if _HANDLER_FUNCTION is None:
        _HANDLER_NAMESPACE = dependencies
        _HANDLER_FUNCTION = _compile_function(
            "handle_video_editor_callback",
            _HANDLER_NAMESPACE,
        )
    else:
        assert _HANDLER_NAMESPACE is not None
        _HANDLER_NAMESPACE.update(dependencies)
    handler = _HANDLER_FUNCTION
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
    assert "videoedit|history" not in hub
    assert "videoedit|history" not in _function_source("handle_video_editor_callback")
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
            "db_connect_readonly": lambda: _db_connect(path),
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
            "db_connect_readonly": lambda: connection,
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
            "db_connect_readonly": lambda: (_ for _ in ()).throw(sqlite3.OperationalError("db unavailable")),
            "video_editengine1": SimpleNamespace(WORKER_JOB_TYPE="video_local_edit"),
            "local_worker_job_from_row": lambda row: dict(row) if row else {},
        },
    )

    with pytest.raises(sqlite3.OperationalError, match="db unavailable"):
        lookup(41)


def test_readonly_status_connector_never_creates_a_missing_database_or_parent(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing-parent" / "status.sqlite3"
    connector = _compile_function(
        "db_connect_readonly",
        {
            "DB_FILE": str(missing),
            "Path": Path,
            "sqlite3": sqlite3,
        },
    )

    with pytest.raises(sqlite3.OperationalError):
        connector()

    assert not missing.exists()
    assert not missing.parent.exists()


def test_canonical_receipt_lookup_is_select_only_and_never_ensures_schema() -> None:
    bot_lookup = _function_source("video_editengine1_job_for_worker")
    assert "db_connect_readonly()" in bot_lookup
    assert "except sqlite3" not in bot_lookup
    assert "get_job_by_worker_id_readonly" in bot_lookup
    assert ".get_job_by_worker_id(" not in bot_lookup

    readonly_lookup = _function_source("get_job_by_worker_id_readonly", ENGINE_SOURCE)
    assert "ensure_schema" not in readonly_lookup

    columns = (
        "id", "idempotency_key", "user_id", "chat_id", "product_type",
        "worker_job_type", "engine_route", "worker_owner", "status",
        "edit_session_id", "quality_tier_id", "price_xu", "local_worker_job_id",
        "progress_percent", "blocker", "source_video_path", "source_sha256",
        "output_file_id", "output_path", "output_sha256", "output_size_bytes",
        "ffprobe_json", "delivery_message_id", "delivery_file_id",
        "artifact_receipts_json", "delivery_cursor", "receipt_state",
        "charge_state", "charged_xu", "tail_json",
    )
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute(
            "CREATE TABLE video_edit_jobs ("
            + ",".join(f"{column} TEXT" for column in columns)
            + ")"
        )
        statements: list[str] = []
        conn.set_trace_callback(statements.append)
        lookup = _compile_function(
            "get_job_by_worker_id_readonly",
            {
                "_load": lambda value, default: json.loads(value) if value else default,
            },
            ENGINE_SOURCE,
        )

        assert lookup(conn, 71) == {}
        assert statements
        assert all(
            statement.lstrip().upper().startswith("SELECT")
            for statement in statements
        )
    finally:
        conn.close()


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
    assert "%" not in text
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "videoedit|status|71" in callbacks
    assert "videoedit|hub" in callbacks


def test_latest_status_preserves_saved_english_language_for_the_six_stage_panel() -> None:
    job = {
        "id": 73,
        "user_id": "41",
        "job_type": "video_local_edit",
        "status": "queued",
        "xu_cost": 0,
    }
    handler, rendered, state, query = _handler(
        lambda _uid: job,
        lambda _job_id: job,
        lang="en",
    )

    assert asyncio.run(
        handler(
            SimpleNamespace(callback_query=query, effective_user=query.from_user),
            SimpleNamespace(),
        )
    ) is True

    assert state == {}
    assert len(rendered) == 1
    text, markup = rendered[0]
    assert "Video Edit status" in text
    assert all(label in text for label in (
        "Receive video",
        "Check configuration",
        "Prepare file",
        "Edit video",
        "Validate MP4",
        "Deliver result",
    ))
    assert "Trạng thái chỉnh sửa video" not in text
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert "🔄 Update status" in labels
    assert "⬅️ Video Edit" in labels


def test_unverified_delivered_stage_never_completes_the_sixth_receipt_step() -> None:
    job = {
        "id": 76,
        "user_id": "41",
        "job_type": "video_local_edit",
        "status": "succeeded",
        "xu_cost": 0,
        "error_short": json.dumps({
            "local1": True,
            "stage": "delivered",
            "total": 1,
            "delivered": 1,
        }),
    }

    text = _status_text(job, "vi")

    assert "Cần kiểm tra việc giao file" in text
    assert "✅ Kiểm tra MP4" in text
    assert "⚠️ Gửi kết quả" in text
    assert "✅ Gửi kết quả" not in text
    assert "• Trạng thái: <b>Hoàn tất</b>" not in text


def test_unverified_multipart_delivered_stage_never_claims_every_part_was_sent() -> None:
    job = {
        "id": 761,
        "user_id": "41",
        "job_type": "video_local_edit",
        "status": "succeeded",
        "xu_cost": 0,
        "error_short": json.dumps({
            "local1": True,
            "stage": "delivered",
            "total": 3,
            "delivered": 1,
        }),
    }

    text = _status_text(job, "vi")

    assert "⚠️ Gửi kết quả" in text
    assert "Đã có biên nhận: <b>1/3</b> phần" in text
    assert "Đã gửi: <b>3/3</b> phần" not in text


def test_incomplete_canonical_delivered_receipt_is_delivery_uncertain() -> None:
    job = {
        "id": 77,
        "user_id": "41",
        "job_type": "video_local_edit",
        "status": "running",
        "xu_cost": 0,
        "error_short": json.dumps({"local1": True, "stage": "received"}),
    }
    incomplete_receipt = {
        "status": "delivered",
        "receipt_state": "created",
        "delivery_message_id": "123",
        "delivery_file_id": "",
        "output_sha256": "abc",
        "output_size_bytes": 2048,
        "ffprobe": {"ok": True},
    }

    text = _status_text(job, "vi", incomplete_receipt)

    assert "Cần kiểm tra việc giao file" in text
    assert "✅ Kiểm tra MP4" in text
    assert "⚠️ Gửi kết quả" in text
    assert "✅ Gửi kết quả" not in text
    assert "• Trạng thái: <b>Hoàn tất</b>" not in text


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
    logs: list[str] = []

    def latest(_uid):
        raise sqlite3.OperationalError("db unavailable PRIVATE_DATABASE_PATH")

    handler, rendered, state, query = _handler(
        latest,
        lambda _job_id: {},
        log_messages=logs,
    )
    assert asyncio.run(handler(SimpleNamespace(callback_query=query, effective_user=query.from_user), SimpleNamespace())) is True
    assert state == {}
    assert len(rendered) == 1
    text, markup = rendered[0]
    assert "chưa đọc được trạng thái chỉnh sửa" in text.lower()
    assert len(text) <= 360
    assert "db unavailable" not in text
    assert "PRIVATE_DATABASE_PATH" not in text
    assert "PRIVATE_DATABASE_PATH" not in "\n".join(logs)
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert callbacks == ["videoedit|hub", "menu|main"]


def test_latest_status_canonical_receipt_database_failure_is_sanitized_and_fail_closed() -> None:
    logs: list[str] = []
    job = {
        "id": 762,
        "user_id": "41",
        "job_type": "video_local_edit",
        "status": "running",
        "xu_cost": 0,
    }

    def fail_status(_job, _lang):
        raise sqlite3.DatabaseError("PRIVATE_CANONICAL_RECEIPT_PATH")

    handler, rendered, state, query = _handler(
        lambda _uid: job,
        lambda _job_id: job,
        log_messages=logs,
        status_renderer=fail_status,
    )

    assert asyncio.run(
        handler(
            SimpleNamespace(callback_query=query, effective_user=query.from_user),
            SimpleNamespace(),
        )
    ) is True

    assert state == {}
    assert len(rendered) == 1
    text, markup = rendered[0]
    assert "chưa đọc được trạng thái chỉnh sửa" in text.lower()
    assert "PRIVATE_CANONICAL_RECEIPT_PATH" not in text
    assert "PRIVATE_CANONICAL_RECEIPT_PATH" not in "\n".join(logs)
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]
    assert callbacks == ["videoedit|hub", "menu|main"]


@pytest.mark.parametrize(
    ("lookup", "expected_copy"),
    [
        (lambda _uid: {}, "You have not submitted a Video Edit task yet"),
        (
            lambda _uid: (_ for _ in ()).throw(
                sqlite3.OperationalError("PRIVATE_ENGLISH_DATABASE_PATH")
            ),
            "Edit status is temporarily unavailable",
        ),
    ],
)
def test_latest_status_empty_and_unavailable_views_preserve_saved_english(
    lookup,
    expected_copy: str,
) -> None:
    logs: list[str] = []
    handler, rendered, state, query = _handler(
        lookup,
        lambda _job_id: {},
        lang="en",
        log_messages=logs,
    )

    assert asyncio.run(
        handler(
            SimpleNamespace(callback_query=query, effective_user=query.from_user),
            SimpleNamespace(),
        )
    ) is True

    assert state == {}
    assert len(rendered) == 1
    text, markup = rendered[0]
    assert expected_copy in text
    assert "Trạng thái chỉnh sửa" not in text
    labels = [button.text for row in markup.inline_keyboard for button in row]
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]
    assert labels == ["⬅️ Video Edit", "🏠 Main menu"]
    assert callbacks == ["videoedit|hub", "menu|main"]
    assert "PRIVATE_ENGLISH_DATABASE_PATH" not in "\n".join(logs)


@pytest.mark.parametrize(
    "job",
    [
        {"id": 74, "user_id": "99", "job_type": "video_local_edit", "status": "queued"},
        {"id": 75, "user_id": "41", "job_type": "product_video", "status": "queued"},
        {"id": 0, "user_id": "41", "job_type": "video_local_edit", "status": "queued"},
    ],
)
def test_latest_status_revalidates_owned_video_edit_job_before_render(job: dict) -> None:
    handler, rendered, state, query = _handler(
        lambda _uid: job,
        lambda _job_id: job,
    )

    assert asyncio.run(
        handler(
            SimpleNamespace(callback_query=query, effective_user=query.from_user),
            SimpleNamespace(),
        )
    ) is True

    assert state == {}
    assert len(rendered) == 1
    text, markup = rendered[0]
    assert "chưa có tác vụ chỉnh sửa video" in text.lower()
    assert f"#{job['id']}" not in text
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]
    assert callbacks == ["videoedit|hub", "menu|main"]


def test_duplicate_latest_status_clicks_are_deterministic_read_only_edits() -> None:
    job = {
        "id": 72,
        "user_id": "41",
        "job_type": "video_local_edit",
        "status": "queued",
        "xu_cost": 0,
    }
    lookups: list[int] = []
    handler, rendered, state, query = _handler(
        lambda uid: lookups.append(uid) or job,
        lambda _job_id: job,
    )
    update = SimpleNamespace(callback_query=query, effective_user=query.from_user)

    assert asyncio.run(handler(update, SimpleNamespace())) is True
    assert asyncio.run(handler(update, SimpleNamespace())) is True

    assert lookups == [41, 41]
    assert state == {}
    assert len(rendered) == 2
    assert rendered[0][0] == rendered[1][0]
    assert [
        button.callback_data
        for row in rendered[0][1].inline_keyboard
        for button in row
    ] == [
        button.callback_data
        for row in rendered[1][1].inline_keyboard
        for button in row
    ]


@pytest.mark.parametrize("action", ["status|71", "ai_status|71"])
def test_existing_status_refreshes_remain_owned_and_stateless_after_hub_clear(action: str) -> None:
    job = {"id": 71, "user_id": "41", "job_type": "video_local_edit", "status": "queued", "xu_cost": 0}
    handler, rendered, state, query = _handler(lambda _uid: job, lambda _job_id: job)
    query.data = f"videoedit|{action}"

    assert asyncio.run(handler(SimpleNamespace(callback_query=query, effective_user=query.from_user), SimpleNamespace())) is True
    assert state == {}
    assert len(rendered) == 1
    assert "Trạng thái chỉnh sửa video" in rendered[0][0]


@pytest.mark.parametrize("action", ["status|71", "ai_status|71"])
def test_existing_status_refresh_database_failure_is_sanitized_and_fail_closed(
    action: str,
) -> None:
    logs: list[str] = []

    def fail_read(_job_id):
        raise sqlite3.DatabaseError("PRIVATE_REFRESH_DATABASE_PATH")

    handler, rendered, state, query = _handler(
        lambda _uid: {},
        fail_read,
        log_messages=logs,
    )
    query.data = f"videoedit|{action}"

    assert asyncio.run(
        handler(
            SimpleNamespace(callback_query=query, effective_user=query.from_user),
            SimpleNamespace(),
        )
    ) is True

    assert state == {}
    assert len(rendered) == 1
    text, markup = rendered[0]
    assert "chưa đọc được trạng thái chỉnh sửa" in text.lower()
    assert "PRIVATE_REFRESH_DATABASE_PATH" not in text
    assert "PRIVATE_REFRESH_DATABASE_PATH" not in "\n".join(logs)
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]
    assert callbacks == ["videoedit|hub", "menu|main"]


def test_latest_status_never_uses_admin_or_owner_privilege_to_read_another_users_job() -> None:
    callback = _function_source("handle_video_editor_callback")
    start = callback.index('if action == "latest_status":')
    end = callback.index("\n    if ", start + 1)
    latest = callback[start:end]
    assert "get_latest_video_editor_job(uid)" in latest
    assert "parts[2]" not in latest
    assert "is_admin_user" not in latest
    assert "product_video" not in latest
    assert "video_b14" not in latest
    assert "framevideo" not in latest
    assert "set_video_editor_pending" not in latest
    assert "update_video_editor_pending" not in latest
    assert "submit_video_edit" not in latest
    assert "create_job" not in latest
    assert "provider" not in latest
    assert "worker" not in latest
    assert "wallet" not in latest
    assert "send_video" not in latest
    assert "reply_text" not in latest
