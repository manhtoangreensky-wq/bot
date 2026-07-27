from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_bytes()
_TARGET_FUNCTIONS = (
    "handle_video_tail_callback",
    "video_b14_send_or_edit_status_panel",
    "video_tail9_callback_guard",
    "video_tail9_render_confirmed_status",
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
    data = "video_tail|confirm|submit"
    from_user = SimpleNamespace(id=18001)

    def __init__(self):
        self.answers: list[tuple] = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def test_old_canonical_renderer_remains_the_only_confirmed_status_authority() -> None:
    confirmed = _function_source("video_tail9_render_confirmed_status")
    status = _function_source("video_b14_send_or_edit_status_panel")

    assert "video_b14_send_or_edit_status_panel" in confirmed
    assert "video_b14_queue_status_text" in status
    assert "video_b14_queue_status_keyboard" in status
    assert _B14_REFRESH_FOUND is True


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


def test_submit_exception_without_job_returns_to_existing_confirmation_owner() -> None:
    rendered: list[str] = []
    blocker_calls: list[str] = []

    async def failing_handler(_update, _context):
        raise RuntimeError("submit interrupted before job persistence")

    async def render(_query, _uid, _context, screen):
        rendered.append(screen)
        return f"screen:{screen}"

    async def blocker(_query, text, **_kwargs):
        blocker_calls.append(str(text))
        return "redundant-board"

    guard = _load_function(
        "video_tail9_callback_guard",
        {
            "ApplicationHandlerStop": type("ApplicationHandlerStop", (Exception,), {}),
            "logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None),
            "video_tail9_context": lambda _uid, _context: (_tail(), "scene3", {}),
            "video_tail9_render": render,
            "video_tail9_render_confirmed_status": lambda *_args, **_kwargs: None,
            "video_tail9_submit_blocker_text": lambda: "redundant technical blocker",
            "video_tail9_submit_blocker_keyboard": lambda: "redundant-keyboard",
            "safe_edit_or_send": blocker,
        },
    )
    query = _Query()

    result = asyncio.run(
        guard(failing_handler)(SimpleNamespace(callback_query=query), SimpleNamespace())
    )

    assert result == "screen:confirm"
    assert rendered == ["confirm"]
    assert blocker_calls == []


def _submit_handler_namespace(
    *,
    owner: str = "scene3",
    technical_ready: bool = True,
    bridge_result=None,
    local_result=None,
):
    state = _tail()
    rendered: list[str] = []
    blocker_calls: list[str] = []
    bridge_calls: list[str] = []
    session = {"draft": {}}

    async def render(_query, _uid, _context, screen):
        rendered.append(screen)
        return f"screen:{screen}"

    async def blocker(_query, text, **_kwargs):
        blocker_calls.append(str(text))
        return "redundant-board"

    async def bridge(_update, _context):
        bridge_calls.append("bridge")
        return bridge_result

    async def local_submit(_update, _context, _host, *, tail):
        return local_result

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
        "safe_edit_or_send": blocker,
        "video_tail9_submit_preflight_keyboard": lambda _result: "redundant-keyboard",
        "video_tail9_submit_blocker_text": lambda: "redundant technical blocker",
        "video_tail9_submit_blocker_keyboard": lambda: "redundant-keyboard",
        "now_text_safe": lambda: "2026-07-27T16:00:00+07:00",
        "VIDEO_TAIL9_STATE_KEY": "video_tail9",
        "logger": SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    }
    return namespace, rendered, blocker_calls, bridge_calls


def test_technical_preflight_denial_stays_on_confirmation_without_redundant_board() -> None:
    namespace, rendered, blocker_calls, bridge_calls = _submit_handler_namespace(
        technical_ready=False,
    )
    handler = _load_function("handle_video_tail_callback", namespace)

    result = asyncio.run(
        handler(SimpleNamespace(callback_query=_Query()), SimpleNamespace())
    )

    assert result == "screen:confirm"
    assert rendered == ["confirm"]
    assert blocker_calls == []
    assert bridge_calls == []


def test_confirm_bridge_without_persisted_job_returns_to_confirmation() -> None:
    namespace, rendered, blocker_calls, bridge_calls = _submit_handler_namespace(
        bridge_result=None,
    )
    handler = _load_function("handle_video_tail_callback", namespace)

    result = asyncio.run(
        handler(SimpleNamespace(callback_query=_Query()), SimpleNamespace())
    )

    assert result == "screen:confirm"
    assert rendered == ["confirm"]
    assert blocker_calls == []
    assert bridge_calls == ["bridge"]


def test_video_edit_without_persisted_job_returns_to_confirmation() -> None:
    namespace, rendered, blocker_calls, bridge_calls = _submit_handler_namespace(
        owner="video_edit",
        local_result=None,
    )
    handler = _load_function("handle_video_tail_callback", namespace)

    result = asyncio.run(
        handler(SimpleNamespace(callback_query=_Query()), SimpleNamespace())
    )

    assert result == "screen:confirm"
    assert rendered == ["confirm"]
    assert blocker_calls == []
    assert bridge_calls == []
