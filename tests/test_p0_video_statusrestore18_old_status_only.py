from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_bytes()
_TARGET_FUNCTIONS = (
    "handle_product_video_public_confirm_callback",
    "handle_video_product_callback",
    "handle_video_tail_callback",
    "video_b14_send_or_edit_status_panel",
    "video_b14_queue_status_keyboard",
    "video_b14_queue_status_text",
    "video_edit_legacy_tail_compatibility",
    "video_editor_state_snapshot",
    "video_edit_review_return_action",
    "video_tail9_callback_guard",
    "video_tail9_prepare_submit_status",
    "video_tail9_render_confirmed_status",
    "video_tail9_status_recovery_keyboard",
    "video_tail9_status_recovery_text",
)


def _read_target_source(name: str) -> str:
    signatures = (f"async def {name}(".encode(), f"def {name}(".encode())
    starts = [BOT_SOURCE.find(signature) for signature in signatures]
    starts = [start for start in starts if start >= 0]
    assert starts, f"missing function: {name}"
    start = min(starts)
    boundaries = [
        position
        for marker in (b"\n@", b"\nasync def ", b"\ndef ")
        for position in [BOT_SOURCE.find(marker, start + 1)]
        if position >= 0
    ]
    end = min(boundaries) if boundaries else len(BOT_SOURCE)
    return BOT_SOURCE[start:end].decode("utf-8")


_FUNCTION_SOURCES = {name: _read_target_source(name) for name in _TARGET_FUNCTIONS}
_B14_REFRESH_FOUND = b'if action == "b14_job_status":' in BOT_SOURCE
_COMPILED_FUNCTIONS = {}


def _function_source(name: str) -> str:
    source = _FUNCTION_SOURCES.get(name, "")
    assert source, f"missing function: {name}"
    return source


def _load_function(name: str, namespace: dict | None = None):
    scope = dict(namespace or {})
    code = _COMPILED_FUNCTIONS.get(name)
    if code is None:
        code = compile(
            "from __future__ import annotations\n" + _function_source(name),
            f"<bot.py:{name}>",
            "exec",
        )
        _COMPILED_FUNCTIONS[name] = code
    exec(code, scope)
    return scope[name]


def _tail() -> dict:
    return {
        "video_product_type": "video_ai_real",
        "video_flow_owner": "scene3",
        "video_session_id": "statusrestore18-session",
        "status_stage": "invoice",
        "scene_count": 1,
        "estimated_duration": 8,
        "ratio": "9:16",
        "quality_tier_id": "200",
        "package_id": "product_video_200",
        "invoice_id": "pv:statusrestore18:1:200",
        "pricing_snapshot": {"total_xu": 200},
        "job_id": "",
        "public_processing_code": "",
        "final_confirmed": False,
    }


class _TailOps:
    def __init__(self, *, technical_ready: bool = True):
        self.technical_ready = technical_ready

    @staticmethod
    def claim_callback(state: dict, _callback_id: str):
        return dict(state), True

    @staticmethod
    def next_required_screen(_state: dict) -> str:
        return ""

    @staticmethod
    def invoice_allowed(_state: dict):
        return True, ""

    @staticmethod
    def commercial_contract(_product_type: str) -> dict:
        return {"execution_enabled": True}

    def evaluate_submit_preflight(
        self,
        _state: dict,
        *,
        provider_ready: bool,
        worker_ready: bool,
        **_kwargs,
    ) -> dict:
        allowed = bool(provider_ready and worker_ready)
        return {
            "allowed": allowed,
            "blocker_code": "" if allowed else "provider_unavailable",
            "public_message": "redundant technical blocker",
        }


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class _Query:
    id = "statusrestore18-submit"
    from_user = SimpleNamespace(id=18001)

    def __init__(self):
        self.answers: list[tuple] = []

    @property
    def data(self) -> str:
        return "video_tail|confirm|submit"

    @data.setter
    def data(self, _value: str) -> None:
        raise AttributeError("CallbackQuery.data is read-only")

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def test_old_canonical_renderer_remains_the_only_confirmed_status_authority() -> None:
    confirmed = _function_source("video_tail9_render_confirmed_status")
    status = _function_source("video_b14_send_or_edit_status_panel")

    assert "video_b14_send_or_edit_status_panel" in confirmed
    assert "video_b14_queue_status_text" in status
    assert "video_b14_queue_status_keyboard" in status
    assert _B14_REFRESH_FOUND is True


def test_no_job_shared_status_is_truthful_and_retries_the_shared_submit_owner() -> None:
    status_text = _function_source("video_b14_queue_status_text")
    status_keyboard = _function_source("video_b14_queue_status_keyboard")
    status_sender = _function_source("video_b14_send_or_edit_status_panel")
    status_prepare = _function_source("video_tail9_prepare_submit_status")

    assert "b14_submit_attempted" in status_text
    assert "b14_submit_preflight_snapshot" in status_text
    assert "Chưa thể bắt đầu tạo video" in status_text
    assert '"video_tail|confirm|submit"' in status_keyboard
    assert '"video_tail|confirm|back"' in status_keyboard
    assert "start_task=job_id > 0" in status_sender
    assert "chưa tạo tác vụ" not in status_text
    assert "chưa tạo tác vụ" not in status_prepare


def test_submit_status_persistence_keeps_job_provider_outbox_and_charge_zero() -> None:
    saved_sessions: list[dict] = []
    session = {"draft": {"kept": True}}
    prepare = _load_function(
        "video_tail9_prepare_submit_status",
        {
            "video_tail9": SimpleNamespace(normalize_state=lambda current: dict(current)),
            "save_video_tail9_state": lambda _uid, _context, current, _owner, _host: dict(current),
            "video_tail9_apply_to_session": lambda *_args, **_kwargs: dict(session),
            "save_video_session": lambda _uid, current: saved_sessions.append(dict(current)) or current,
            "VIDEO_TAIL9_STATE_KEY": "video_tail9",
        },
    )

    result = prepare(
        18001,
        SimpleNamespace(),
        _tail(),
        "scene3",
        {},
        {"allowed": False, "blocker_code": "worker_unavailable"},
    )

    assert result["submit_attempted"] is True
    assert result["status_stage"] == "invoice"
    assert result["job_id"] == ""
    assert result["final_confirmed"] is False
    draft = saved_sessions[-1]["draft"]
    assert draft["kept"] is True
    assert draft["job_created"] is False
    assert draft["outbox_created"] is False
    assert draft["provider_called"] is False
    assert draft["xu_charged"] == 0
    assert draft["video_tail9"]["video_product_type"] == "video_ai_real"


def test_video_edit_no_job_recovery_is_truthful_and_retries_submit() -> None:
    recovery_text = _function_source("video_tail9_status_recovery_text")
    recovery_keyboard = _load_function(
        "video_tail9_status_recovery_keyboard",
        {"video_scene3_keyboard": lambda rows: rows},
    )
    tail = {
        "submit_attempted": True,
        "job_id": "",
        "submit_preflight_snapshot": {"allowed": False},
    }

    rows = recovery_keyboard(tail)

    assert "submit_attempted" in recovery_text
    assert "Chưa thể bắt đầu tạo video" in recovery_text
    assert rows[0][0][1] == "video_tail|confirm|submit"
    assert rows[1][0][1] == "video_tail|confirm|back"


def test_confirm_bridge_never_mutates_telegram_callback_data() -> None:
    tail_handler = _function_source("handle_video_tail_callback")
    public_confirm = _function_source("handle_product_video_public_confirm_callback")
    product_handler = _function_source("handle_video_product_callback")

    override = "_product_video_callback_data_override"
    assert override in tail_handler
    assert override in public_confirm
    assert override in product_handler
    assert 'query.data = "vproduct|b14_confirm"' not in tail_handler
    assert "query.data =" not in public_confirm


def test_public_confirm_wrapper_accepts_context_override_with_readonly_query() -> None:
    delegated: list[tuple[str, bool]] = []

    async def product_handler(_update, context):
        delegated.append(
            (
                str(getattr(context, "_product_video_callback_data_override", "") or ""),
                bool(getattr(context, "_product_video_authoritative_confirm", False)),
            )
        )
        return "delegated"

    handler = _load_function(
        "handle_product_video_public_confirm_callback",
        {
            "video_project_queue": SimpleNamespace(
                PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK="vproduct|b14_confirm"
            ),
            "PRODUCT_VIDEO_CONFIRM_HANDLER_DIAGNOSTICS": {
                "product_video_confirm_handler_count": 1,
                "duplicate_confirm_handler_detected": False,
                "duplicate_callback_pattern_detected": False,
            },
            "handle_video_product_callback": product_handler,
        },
    )
    context = SimpleNamespace(
        _product_video_callback_data_override="vproduct|b14_confirm"
    )

    result = asyncio.run(
        handler(SimpleNamespace(callback_query=_Query()), context)
    )

    assert result == "delegated"
    assert delegated == [("vproduct|b14_confirm", True)]
    assert not hasattr(context, "_product_video_authoritative_confirm")
    assert context._product_video_callback_data_override == "vproduct|b14_confirm"


def test_double_submit_reuses_same_job_and_public_code_without_bridge() -> None:
    state = _tail()
    state.update(
        {
            "job_id": "318",
            "public_processing_code": "#318",
            "final_confirmed": True,
            "status_stage": "confirmed",
        }
    )
    status_calls: list[dict] = []
    bridge_calls: list[str] = []

    async def render_status(_query, _context, _uid, current, _owner, _host):
        status_calls.append(dict(current))
        return "status-panel"

    async def bridge(_update, _context):
        bridge_calls.append("bridge")
        raise AssertionError("double submit must not call the confirm bridge")

    handler = _load_function(
        "handle_video_tail_callback",
        {
            "video_tail9_context": lambda _uid, _context: (dict(state), "scene3", {}),
            "video_tail9": _TailOps(),
            "save_video_tail9_state": lambda *_args, **_kwargs: None,
            "video_tail9_render_confirmed_status": render_status,
            "handle_product_video_public_confirm_callback": bridge,
        },
    )

    result = asyncio.run(
        handler(SimpleNamespace(callback_query=_Query()), SimpleNamespace())
    )

    assert result == "status-panel"
    assert len(status_calls) == 1
    assert status_calls[0]["job_id"] == "318"
    assert status_calls[0]["public_processing_code"] == "#318"
    assert bridge_calls == []


def test_submit_exception_without_job_opens_canonical_status_recovery() -> None:
    rendered: list[str] = []
    blocker_calls: list[str] = []
    status_calls: list[dict] = []

    async def failing_handler(_update, _context):
        raise RuntimeError("submit interrupted before job persistence")

    async def render(_query, _uid, _context, screen):
        rendered.append(screen)
        return f"screen:{screen}"

    async def blocker(_query, text, **_kwargs):
        blocker_calls.append(str(text))
        return "redundant-board"

    async def render_status(_query, _context, _uid, current, _owner, _host):
        status_calls.append(dict(current))
        return "status-panel"

    guard = _load_function(
        "video_tail9_callback_guard",
        {
            "ApplicationHandlerStop": type("ApplicationHandlerStop", (Exception,), {}),
            "logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None),
            "video_tail9_context": lambda _uid, _context: (_tail(), "scene3", {}),
            "video_tail9_render": render,
            "video_tail9_prepare_submit_status": lambda _uid, _context, current, _owner, _host, snapshot: {
                **current,
                "submit_attempted": True,
                "submit_preflight_snapshot": dict(snapshot),
            },
            "video_tail9_render_confirmed_status": render_status,
            "video_tail9_submit_blocker_text": lambda: "redundant technical blocker",
            "video_tail9_submit_blocker_keyboard": lambda: "redundant-keyboard",
            "safe_edit_or_send": blocker,
        },
    )
    query = _Query()

    result = asyncio.run(
        guard(failing_handler)(SimpleNamespace(callback_query=query), SimpleNamespace())
    )

    assert result == "status-panel"
    assert rendered == []
    assert blocker_calls == []
    assert len(status_calls) == 1
    assert status_calls[0]["submit_attempted"] is True


def _submit_handler_namespace(
    *,
    owner: str = "scene3",
    technical_ready: bool = True,
    bridge_result=None,
    bridge_preflight: bool = False,
    local_result=None,
    product_type: str = "video_ai_real",
    content_source: str = "selected_content",
):
    state = _tail()
    state.update(
        {
            "video_product_type": product_type,
            "content_source": content_source,
            "canonical_content_mode": content_source,
        }
    )
    rendered: list[str] = []
    blocker_calls: list[str] = []
    bridge_calls: list[str] = []
    status_calls: list[dict] = []
    session = {"draft": {}}

    async def render(_query, _uid, _context, screen):
        rendered.append(screen)
        return f"screen:{screen}"

    async def blocker(_query, text, **_kwargs):
        blocker_calls.append(str(text))
        return "redundant-board"

    async def bridge(_update, _context):
        bridge_calls.append(
            str(getattr(_context, "_product_video_callback_data_override", "") or "")
        )
        if bridge_preflight:
            session["draft"] = {
                **dict(session.get("draft") or {}),
                "b14_preflight_ui_context": {"selected_scene_count": 1},
            }
        return bridge_result

    async def local_submit(_update, _context, _host, *, tail):
        return local_result

    async def render_status(_query, _context, _uid, current, current_owner, _host):
        status_calls.append(
            {
                "tail": dict(current),
                "owner": current_owner,
            }
        )
        return "status-panel"

    def prepare_status(_uid, _context, current, _owner, _host, snapshot):
        return {
            **dict(current),
            "submit_attempted": True,
            "submit_preflight_snapshot": dict(snapshot),
            "status_stage": "invoice",
        }

    namespace = {
        "video_tail9_context": lambda _uid, _context: (dict(state), owner, {}),
        "video_tail9": _TailOps(technical_ready=technical_ready),
        "save_video_tail9_state": lambda *_args, **_kwargs: None,
        "video_tail9_render": render,
        "video_tail9_apply_to_session": lambda *_args, **_kwargs: session,
        "video_b14_is_admin_or_owner": lambda _uid: False,
        "get_user": lambda _uid: (200, None, None),
        "safe_int": _safe_int,
        "product_video_public_preflight_evaluation": lambda *_args, **_kwargs: {
            "ready": technical_ready,
            "preflight_resolved_state": "ready" if technical_ready else "blocked_provider",
        },
        "product_video_worker_admission_status": lambda: {
            "worker_version_compatible": technical_ready,
        },
        "handle_product_video_public_confirm_callback": bridge,
        "get_video_session": lambda _uid: session,
        "save_video_session": lambda _uid, current: current,
        "submit_local_video_editor_job": local_submit,
        "get_video_editor_pending": lambda _uid: {},
        "compare_and_set_video_editor_pending": (
            lambda _uid, _expected, step, **fields: (
                True,
                {"step": step, **fields},
            )
        ),
        "rerender_video_editor_after_stale_commit": (
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("fresh Video Edit legacy callback must win its CAS")
            )
        ),
        "get_user_language": lambda _uid: "vi",
        "get_local_worker_job": lambda _job_id: None,
        "video_edit_lane_upload_keyboard": lambda *_args, **_kwargs: "upload-keyboard",
        "video_tail9_render_confirmed_status": render_status,
        "video_tail9_prepare_submit_status": prepare_status,
        "safe_edit_or_send": blocker,
        "video_tail9_submit_preflight_keyboard": lambda _result: "redundant-keyboard",
        "video_tail9_submit_blocker_text": lambda: "redundant technical blocker",
        "video_tail9_submit_blocker_keyboard": lambda: "redundant-keyboard",
        "now_text_safe": lambda: "2026-07-27T16:00:00+07:00",
        "VIDEO_TAIL9_STATE_KEY": "video_tail9",
        "logger": SimpleNamespace(
            warning=lambda *_args, **_kwargs: None,
            exception=lambda *_args, **_kwargs: None,
        ),
        "_status_calls": status_calls,
    }
    namespace["video_editor_state_snapshot"] = _load_function(
        "video_editor_state_snapshot",
        {"json": json},
    )
    namespace["video_edit_review_return_action"] = _load_function(
        "video_edit_review_return_action",
    )
    namespace["video_edit_legacy_tail_compatibility"] = _load_function(
        "video_edit_legacy_tail_compatibility",
        namespace,
    )
    return namespace, rendered, blocker_calls, bridge_calls


def test_technical_preflight_denial_opens_canonical_status_without_fake_job() -> None:
    namespace, rendered, blocker_calls, bridge_calls = _submit_handler_namespace(
        technical_ready=False,
    )
    handler = _load_function("handle_video_tail_callback", namespace)

    result = asyncio.run(
        handler(SimpleNamespace(callback_query=_Query()), SimpleNamespace())
    )

    assert result == "status-panel"
    assert rendered == []
    assert blocker_calls == []
    assert bridge_calls == []
    assert len(namespace["_status_calls"]) == 1
    status_tail = namespace["_status_calls"][0]["tail"]
    assert status_tail["job_id"] == ""
    assert status_tail["final_confirmed"] is False
    assert status_tail["status_stage"] == "invoice"
    assert status_tail["submit_preflight_snapshot"]["allowed"] is False


def test_confirm_bridge_without_persisted_job_opens_canonical_status() -> None:
    namespace, rendered, blocker_calls, bridge_calls = _submit_handler_namespace(
        bridge_result=None,
    )
    handler = _load_function("handle_video_tail_callback", namespace)

    result = asyncio.run(
        handler(SimpleNamespace(callback_query=_Query()), SimpleNamespace())
    )

    assert result == "status-panel"
    assert rendered == []
    assert blocker_calls == []
    assert bridge_calls == ["vproduct|b14_confirm"]
    assert len(namespace["_status_calls"]) == 1


def test_confirm_bridge_preflight_panel_is_normalized_to_canonical_status() -> None:
    namespace, rendered, blocker_calls, bridge_calls = _submit_handler_namespace(
        bridge_result="preflight-panel",
        bridge_preflight=True,
    )
    handler = _load_function("handle_video_tail_callback", namespace)

    result = asyncio.run(
        handler(SimpleNamespace(callback_query=_Query()), SimpleNamespace())
    )

    assert result == "status-panel"
    assert rendered == []
    assert blocker_calls == []
    assert bridge_calls == ["vproduct|b14_confirm"]
    assert len(namespace["_status_calls"]) == 1


def test_video_edit_without_persisted_job_opens_its_status_recovery_panel() -> None:
    namespace, rendered, blocker_calls, bridge_calls = _submit_handler_namespace(
        owner="video_edit",
        local_result=None,
    )
    handler = _load_function("handle_video_tail_callback", namespace)

    result = asyncio.run(
        handler(SimpleNamespace(callback_query=_Query()), SimpleNamespace())
    )

    assert result == "redundant-board"
    assert rendered == []
    assert len(blocker_calls) == 1
    public_copy = blocker_calls[0].lower()
    assert "gửi video nguồn" in public_copy
    assert "chưa tạo tác vụ" in public_copy
    assert "chưa trừ xu" in public_copy
    assert bridge_calls == []
    assert namespace["_status_calls"] == []


def test_status_handoff_covers_shared_products_and_embedded_idea_source() -> None:
    products = (
        ("video_ai_real", "scene3"),
        ("video_trend", "scene3"),
        ("script_image_video", "scene3"),
        ("storyboard_prompt", "scene3"),
        ("self_shot_scene_change", "session"),
        ("self_shot_cinematic_transform", "session"),
    )
    for product_type, owner in products:
        for content_source in ("selected_content", "idea_catalog"):
            namespace, rendered, blocker_calls, bridge_calls = _submit_handler_namespace(
                owner=owner,
                technical_ready=False,
                product_type=product_type,
                content_source=content_source,
            )
            handler = _load_function("handle_video_tail_callback", namespace)

            result = asyncio.run(
                handler(SimpleNamespace(callback_query=_Query()), SimpleNamespace())
            )

            assert result == "status-panel"
            assert rendered == []
            assert blocker_calls == []
            assert bridge_calls == []
            assert namespace["_status_calls"][0]["owner"] == owner
            assert namespace["_status_calls"][0]["tail"]["content_source"] == content_source
