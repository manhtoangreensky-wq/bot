from __future__ import annotations

import ast
import asyncio
import hashlib
import inspect
import json
import os
import re
import shutil
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import (
    video_edit_long_media,
    video_edit_media_transport,
    video_edit_state_machine,
    video_local_editing,
    video_local_validation,
    video_scene3_flow,
)


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
BOT_MODULE = ast.parse(BOT_SOURCE)
MIB = 1024 * 1024


def _is_whole_response_content_access(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "content"


def _function_source(name: str) -> str:
    async_marker = f"async def {name}("
    sync_marker = f"def {name}("
    start = BOT_SOURCE.find(async_marker)
    if start < 0:
        start = BOT_SOURCE.index(sync_marker)
    candidates = [
        BOT_SOURCE.find("\ndef ", start + 1),
        BOT_SOURCE.find("\nasync def ", start + 1),
        BOT_SOURCE.find("\n@", start + 1),
    ]
    ends = [position for position in candidates if position >= 0]
    return BOT_SOURCE[start:min(ends) if ends else len(BOT_SOURCE)]


def _compile_function(name: str, namespace: dict):
    module = ast.parse("from __future__ import annotations\n\n" + _function_source(name))
    exec(compile(module, filename="bot.py", mode="exec"), namespace)
    return namespace[name]


def _literal_assignment(name: str):
    for node in BOT_MODULE.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"missing assignment: {name}")


class _InlineKeyboardButton:
    def __init__(self, text: str, *, callback_data: str):
        self.text = text
        self.callback_data = callback_data


class _InlineKeyboardMarkup:
    def __init__(self, inline_keyboard: list[list[_InlineKeyboardButton]]):
        self.inline_keyboard = inline_keyboard


def _compiled_video_edit_lane_upload_keyboard():
    scene_keyboard = _compile_function(
        "video_scene3_keyboard",
        {
            "video_scene3_flow": video_scene3_flow,
            "InlineKeyboardMarkup": _InlineKeyboardMarkup,
            "InlineKeyboardButton": _InlineKeyboardButton,
        },
    )
    return _compile_function(
        "video_edit_lane_upload_keyboard",
        {
            "video_scene3_keyboard": scene_keyboard,
            "ui_text": lambda _lang, key: key,
        },
    )


def _back_callback(reply_markup: _InlineKeyboardMarkup) -> str:
    return reply_markup.inline_keyboard[0][0].callback_data


class _NoNetworkHttpResponse:
    def __init__(self, *, json_payload: dict | None = None):
        self._json_payload = json_payload or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return dict(self._json_payload)

    def iter_bytes(self, chunk_size: int):
        assert isinstance(chunk_size, int) and chunk_size > 0
        # Deliberately split a tiny test body so an adapter cannot pass a whole
        # response object/body through as one unbounded "chunk".
        for chunk in (b"bounded-", b"stream-", b"chunks"):
            assert len(chunk) <= chunk_size
            yield chunk


class _NoNetworkHttpClient:
    def __init__(self, requests: list[dict], **defaults):
        self._requests = requests
        self._defaults = defaults

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def _record(self, method: str, url: str, **kwargs) -> _NoNetworkHttpResponse:
        headers = kwargs.get("headers", self._defaults.get("headers"))
        follow_redirects = kwargs.get(
            "follow_redirects", self._defaults.get("follow_redirects")
        )
        assert headers, "credential-bearing transport request requires headers"
        self._requests.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "follow_redirects": follow_redirects,
                "json": kwargs.get("json"),
            }
        )
        return _NoNetworkHttpResponse(
            json_payload={
                "ok": True,
                "result": {"file_path": "videos/source.mp4", "file_size": 21},
            }
        )

    def post(self, url: str, **kwargs) -> _NoNetworkHttpResponse:
        return self._record("POST", url, **kwargs)

    def get(self, url: str, **kwargs) -> _NoNetworkHttpResponse:
        return self._record("GET", url, **kwargs)

    def request(self, method: str, url: str, **kwargs) -> _NoNetworkHttpResponse:
        return self._record(method.upper(), url, **kwargs)

    def stream(self, method: str, url: str, **kwargs) -> _NoNetworkHttpResponse:
        return self._record(method.upper(), url, **kwargs)


class _NoNetworkHttpx:
    def __init__(self):
        self.requests: list[dict] = []

    def Client(self, **kwargs) -> _NoNetworkHttpClient:
        return _NoNetworkHttpClient(self.requests, **kwargs)


def _streaming_download_fake(
    *,
    payload: bytes,
    bytes_written: int,
    sha256: str,
    lane: str = "large_media",
    transport: str = "localfile",
    calls: list[dict] | None = None,
    failure: Exception | None = None,
):
    """Mirror the transport boundary and exercise both streaming callbacks."""

    def fake_download_file_to_path(
        *,
        config,
        file_id,
        destination,
        get_file_json=None,
        stream_bytes=None,
        expected_bytes=None,
        expected_size=None,
        open_json=None,
        open_stream=None,
        progress_callback=None,
        cancel_requested=None,
        deadline_monotonic=None,
        workspace_reserve_bytes=0,
        hard_max_bytes=None,
        require_private_parent=False,
        disk_usage=shutil.disk_usage,
        free_bytes=None,
        monotonic=time.monotonic,
        max_attempts=2,
        retry_backoff=None,
        max_retry_delay_seconds=1.0,
        sleep=None,
    ):
        json_callback = get_file_json or open_json
        stream_callback = stream_bytes or open_stream
        assert callable(json_callback), "missing JSON transport callback"
        assert callable(stream_callback), "missing streaming transport callback"
        assert expected_bytes is None
        assert expected_size is None

        json_request = {
            "url": "https://tg.toanaas.vn/bot123:test-token/getFile",
            "headers": {"X-Toanaas-Proxy-Secret": "test-secret"},
            "follow_redirects": False,
            "json": {"file_id": file_id},
        }
        stream_request = {
            "url": "https://tg.toanaas.vn/localfile/videos/source.mp4",
            "headers": {"X-Toanaas-Proxy-Secret": "test-secret"},
            "follow_redirects": False,
            "chunk_size": 64,
        }
        # Bind before invocation: adapters must accept the transport module's
        # keyword-only contract, not merely be callable no-argument closures.
        inspect.signature(json_callback).bind(**json_request)
        inspect.signature(stream_callback).bind(**stream_request)
        json_callback(**json_request)
        chunks = stream_callback(**stream_request)
        chunk_count = 0
        for chunk in chunks:
            assert isinstance(chunk, bytes)
            assert 0 < len(chunk) <= stream_request["chunk_size"]
            chunk_count += 1
        assert chunk_count > 1, "stream adapter must yield bounded chunks"
        request = {
            "config": config,
            "file_id": file_id,
            "destination": destination,
            "get_file_json": get_file_json,
            "stream_bytes": stream_bytes,
            "expected_bytes": expected_bytes,
            "expected_size": expected_size,
            "open_json": open_json,
            "open_stream": open_stream,
            "progress_callback": progress_callback,
            "cancel_requested": cancel_requested,
            "deadline_monotonic": deadline_monotonic,
            "workspace_reserve_bytes": workspace_reserve_bytes,
            "hard_max_bytes": hard_max_bytes,
            "require_private_parent": require_private_parent,
            "disk_usage": disk_usage,
            "free_bytes": free_bytes,
            "monotonic": monotonic,
            "max_attempts": max_attempts,
            "retry_backoff": retry_backoff,
            "max_retry_delay_seconds": max_retry_delay_seconds,
            "sleep": sleep,
        }
        if calls is not None:
            calls.append(request)
        if failure is not None:
            raise failure
        Path(destination).write_bytes(payload)
        return video_edit_media_transport.DownloadReceipt(
            path=str(destination),
            bytes_written=bytes_written,
            sha256=sha256,
            lane=lane,
            transport=transport,
            declared_bytes=bytes_written,
        )

    return fake_download_file_to_path


def _compile_real_inspector(
    video_local_validation,
    *,
    api_root: str = "https://tg.toanaas.vn",
    shutil_dependency=shutil,
    httpx_dependency=None,
):
    return _compile_function(
        "inspect_video_editor_source",
        {
            "video_edit_media_transport": video_edit_media_transport,
            "video_edit_long_media": video_edit_long_media,
            "video_local_validation": video_local_validation,
            "safe_int": lambda value, default=0: int(value or default),
            "tempfile": tempfile,
            "os": os,
            "hashlib": hashlib,
            "asyncio": asyncio,
            "shutil": shutil_dependency,
            "httpx": httpx_dependency or _NoNetworkHttpx(),
            "TELEGRAM_TOKEN": "123:test-token",
            "TELEGRAM_API_ROOT": api_root,
            "TELEGRAM_CLOUD_API_ROOT": "https://api.telegram.org",
            "TELEGRAM_API_PROXY_SECRET_HEADER": "X-Toanaas-Proxy-Secret",
            "TELEGRAM_API_PROXY_SECRET": "test-secret",
            "TELEGRAM_LOCAL_API_FILE_ROOT": "/var/lib/telegram-bot-api",
            "TELEGRAM_LOCAL_API_MEDIA_PATH": "/localfile",
        },
    )


@pytest.mark.parametrize(
    ("mode", "ready"),
    [
        ("manual_edit", "manual_edit"),
        ("ai_edit", "ai_edit"),
        ("quality_enhance", "quality_enhance"),
    ],
)
def test_edit3_lane_state_has_one_canonical_contract(mode: str, ready: str) -> None:
    state = video_edit_state_machine.start_lane(mode)
    assert state == {
        "step": "await_edit_video",
        "edit_mode": mode,
        "current_screen": f"{mode}_upload",
        "return_to": "videoedit|hub",
        "awaiting_media": True,
        "source_file_id": None,
        "last_media_message_id": 0,
        "intake_in_progress": False,
        "probe_count": 0,
    }
    complete = video_edit_state_machine.complete_intake(
        state,
        {"source_file_id": "file-1", "source_file_name": "input.mp4"},
        {"ok": True, "duration": 8.0},
    )
    assert complete["step"] == ready
    assert complete["current_screen"] == ready
    assert complete["awaiting_media"] is False
    assert complete["probe_count"] == 1


def _run_canonical_upload(
    mode: str,
    *,
    valid: bool = True,
    active_product: str = "video_local_edit",
    source_size: int = 1_024,
    source_duration: int = 8,
    inspected_size: int | None = None,
    inspected_duration: float | None = None,
    failure_reason: str = "invalid_video_metadata",
    language: str = "vi",
    concurrent_winner: dict | None = None,
    inspection_exception: Exception | None = None,
    failure_metadata: dict | None = None,
    fallback_result: dict | None = None,
    fallback_calls: list[str] | None = None,
    repeat: bool = True,
):
    persisted = video_edit_state_machine.start_lane(mode)
    replies: list[dict] = []
    probes: list[str] = []
    lane_upload_keyboard = _compiled_video_edit_lane_upload_keyboard()
    actual_size = source_size if inspected_size is None else inspected_size
    actual_duration = (
        float(source_duration)
        if inspected_duration is None
        else float(inspected_duration)
    )

    class Message:
        message_id = 901
        video = SimpleNamespace(
            file_id="video-file-901",
            file_unique_id="telegram-opaque-901",
            file_name="source.mp4",
            mime_type="video/mp4",
            file_size=source_size,
            duration=source_duration,
        )
        document = None

        async def reply_text(self, text: str, **kwargs):
            replies.append({"text": text, **kwargs})
            return True

    update = SimpleNamespace(effective_user=SimpleNamespace(id=78), message=Message())
    context = SimpleNamespace(bot=SimpleNamespace(), user_data={})

    async def inspect(_context, source):
        probes.append(str(source.get("source_file_id") or ""))
        if concurrent_winner is not None:
            persisted.clear()
            persisted.update(deepcopy(concurrent_winner))
        if inspection_exception is not None:
            raise inspection_exception
        if not valid:
            return {
                "ok": False,
                "reason": failure_reason,
                **deepcopy(failure_metadata or {}),
            }
        declared_lane = video_edit_media_transport.select_media_lane(
            duration_seconds=source_duration,
            size_bytes=source_size,
        )
        inspected_lane = video_edit_media_transport.select_media_lane(
            duration_seconds=actual_duration,
            size_bytes=actual_size,
        )
        return {
            "ok": True,
            "bytes": actual_size,
            "actual_bytes": actual_size,
            "declared_bytes": source_size,
            "declared_duration_seconds": source_duration,
            "duration": actual_duration,
            "duration_ms": int(round(actual_duration * 1_000)),
            "width": 1_080,
            "height": 1_920,
            "fps": 30.0,
            "has_audio": True,
            "audio_stream_count": 1,
            "format_name": "mov,mp4",
            "source_sha256": "a" * 64,
            "media_lane": (
                "large_media"
                if "large_media" in {declared_lane, inspected_lane}
                else "short_media"
            ),
        }

    def telegram_probe_fallback(_source, reason):
        if fallback_calls is not None:
            fallback_calls.append(str(reason or ""))
        return dict(fallback_result or {})

    def save(_uid: int, state: dict) -> dict:
        persisted.clear()
        persisted.update(state)
        return dict(persisted)

    def snapshot(state: dict | None) -> dict:
        return deepcopy(dict(state or {}))

    def compare_and_set(_uid: int, expected: dict, step: str = "", **fields):
        current = snapshot(persisted)
        if current != snapshot(expected):
            return False, current
        committed = {**current, **deepcopy(fields)}
        committed["step"] = step or str(current.get("step") or "await_edit_video")
        save(_uid, committed)
        return True, snapshot(persisted)

    def compare_and_replace(
        _uid: int,
        expected: dict,
        replacement: dict,
        *,
        replacement_exists: bool = True,
    ):
        current = snapshot(persisted)
        if current != snapshot(expected):
            return False, current
        save(_uid, replacement if replacement_exists else {})
        return True, snapshot(persisted)

    async def rerender_stale(_message, winner: dict, _lang: str) -> None:
        replies.append({"text": "stale", "winner": snapshot(winner)})

    handler = _compile_function(
        "handle_video_editor_pending_upload",
        {
            "get_video_editor_pending": lambda _uid: dict(persisted),
            "video_editor_state_snapshot": snapshot,
            "compare_and_set_video_editor_pending": compare_and_set,
            "compare_and_replace_video_editor_pending": compare_and_replace,
            "rerender_video_editor_after_stale_commit": rerender_stale,
            "get_video_session": lambda _uid: {"product_id": active_product},
            "video_edit_state_machine": video_edit_state_machine,
            "safe_int": lambda value, default=0: int(value or default),
            "save_video_edit_canonical_state": save,
            "clear_video_editor_competing_video_states": lambda _uid, _context: {},
            "get_user_language": lambda _uid: language,
            "video_editor_source_from_update": lambda _update: {
                "source_file_id": "video-file-901",
                "source_file_unique_id": "telegram-opaque-901",
                "source_file_name": "source.mp4",
                "source_mime_type": "video/mp4",
                "source_file_size": source_size,
                "source_duration": source_duration,
            },
            "inspect_video_editor_source": inspect,
            "video_editor_telegram_probe_fallback": telegram_probe_fallback,
            "video_edit_media_transport": video_edit_media_transport,
            "video_local_validation": video_local_validation,
            "logger": SimpleNamespace(warning=lambda *_args, **_kwargs: None),
            "sanitize_log_text": str,
            "video_local_public_error": lambda reason, message_lang="vi": f"{message_lang}:{reason}",
            "video_edit_lane_upload_keyboard": lane_upload_keyboard,
            "cache_recent_media_state": lambda _update: "video",
            "video_local_editing": video_local_editing,
            "video_local_manual_options_text": lambda _state, _lang: "manual-screen",
            "video_local_manual_options_keyboard": lambda lang, _state=None: f"manual-keyboard:{lang}",
            "video_ai_edit_router": SimpleNamespace(DEFAULT_PRESERVE_CONTROLS={"identity": True}),
            "video_quality_enhance_source_text": lambda _state, _lang: "quality-screen",
            "video_quality_enhance_source_keyboard": lambda lang, _state=None: f"quality-keyboard:{lang}",
            "video_ai_edit_source_summary_text": lambda _state, _lang: "ai-screen",
            "video_ai_edit_source_summary_keyboard": lambda lang, _state: f"ai-keyboard:{lang}",
        },
    )
    first = asyncio.run(handler(update, context))
    second = asyncio.run(handler(update, context)) if repeat else None
    return first, second, persisted, replies, probes


def test_edit3_telegram_unique_id_is_not_used_as_content_sha256() -> None:
    extractor = _compile_function(
        "video_editor_source_from_update",
        {"safe_int": lambda value, default=0: int(value or default)},
    )
    media = SimpleNamespace(
        file_id="telegram-file-id",
        file_unique_id="opaque-telegram-identity",
        file_name="source.mp4",
        mime_type="video/mp4",
        file_size=1024,
        duration=8,
        width=1280,
        height=720,
    )
    update = SimpleNamespace(message=SimpleNamespace(video=media, document=None))

    source = extractor(update)

    assert source["source_file_unique_id"] == "opaque-telegram-identity"
    assert source["source_video_hash"] == ""


def test_edit3_opaque_telegram_identity_is_retained_as_separate_audit_field() -> None:
    fields_start = BOT_SOURCE.index("VIDEO_EDITOR_TEXT_FIELDS = {")
    fields_end = BOT_SOURCE.index("\n}", fields_start)
    assert '"source_file_unique_id"' in BOT_SOURCE[fields_start:fields_end]


def test_edit3_media_lane_survives_real_video_editor_persistence_allow_list() -> None:
    pending: dict[str, dict] = {}
    setter = _compile_function(
        "set_video_editor_pending",
        {
            "VIDEO_EDITOR_TEXT_FIELDS": _literal_assignment("VIDEO_EDITOR_TEXT_FIELDS"),
            "VIDEO_EDITOR_NUMBER_FIELDS": _literal_assignment("VIDEO_EDITOR_NUMBER_FIELDS"),
            "VIDEO_EDITOR_STRUCTURED_FIELDS": _literal_assignment("VIDEO_EDITOR_STRUCTURED_FIELDS"),
            "USER_PENDING": pending,
            "video_editor_pending_key": lambda user_id: f"video_editor:{user_id}",
            "record_video_editor_state_write": lambda *_args, **_kwargs: None,
            "safe_int": lambda value, default=0: int(value or default),
            "json": json,
            "re": re,
            "time": time,
        },
    )

    state = setter(78, "manual_edit", media_lane="large_media")

    assert state["media_lane"] == "large_media"
    assert pending["video_editor:78"]["media_lane"] == "large_media"


def test_edit3_local_inspection_is_file_backed_unbounded_and_uses_local_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"actual-video-content-for-sha256"
    digest = hashlib.sha256(payload).hexdigest()
    download_calls: list[dict] = []
    validation_calls: list[dict] = []

    async def legacy_get_file_must_not_run(_file_id: str):
        raise AssertionError("Video Edit inspection must use the file-backed transport")

    from services import video_local_validation

    monkeypatch.setattr(
        video_local_validation,
        "probe_video_file",
        lambda _path: {
            "ok": True,
            "bytes": len(payload),
            "duration": 3_600.0,
            "duration_ms": 3_600_000,
            "width": 640,
            "height": 360,
            "has_video": True,
            "has_audio": False,
            "audio_stream_count": 0,
            "format_name": "mov,mp4",
        },
    )
    validate_source_metadata = video_local_validation.validate_source_metadata

    def capture_validation(metadata, **kwargs):
        validation_calls.append(dict(kwargs))
        return validate_source_metadata(metadata, **kwargs)

    monkeypatch.setattr(
        video_local_validation,
        "validate_source_metadata",
        capture_validation,
    )

    fake_download_file_to_path = _streaming_download_fake(
        payload=payload,
        bytes_written=len(payload),
        sha256=digest,
        calls=download_calls,
    )

    monkeypatch.setattr(
        video_edit_media_transport,
        "download_file_to_path",
        fake_download_file_to_path,
    )
    fake_http = _NoNetworkHttpx()
    inspect_source = _compile_real_inspector(
        video_local_validation,
        httpx_dependency=fake_http,
    )

    result = asyncio.run(
        inspect_source(
            SimpleNamespace(bot=SimpleNamespace(get_file=legacy_get_file_must_not_run)),
            {
                "source_file_id": "telegram-file-id",
                "source_file_name": "source.mp4",
                "source_file_size": len(payload),
                "source_duration": 3_600,
            },
        )
    )

    assert result["ok"] is True
    assert result["source_sha256"] == digest
    assert result["media_lane"] == "large_media"
    assert len(download_calls) == 1
    request = download_calls[0]
    assert request["file_id"] == "telegram-file-id"
    assert callable(request["get_file_json"] or request["open_json"])
    assert callable(request["stream_bytes"] or request["open_stream"])
    assert request["expected_bytes"] is None
    assert request["expected_size"] is None
    assert request["hard_max_bytes"] is None
    assert request["require_private_parent"] is True
    assert request["workspace_reserve_bytes"] == (
        video_edit_long_media.DEFAULT_WORKSPACE_RESERVE_BYTES
    )
    assert request["config"].api_root == "https://tg.toanaas.vn"
    assert request["config"].local_media_path == "/localfile"
    assert len(fake_http.requests) == 2
    get_file_request, file_stream_request = fake_http.requests
    assert get_file_request["json"] == {"file_id": "telegram-file-id"}
    assert file_stream_request["json"] is None
    for adapter_request in (get_file_request, file_stream_request):
        assert adapter_request["headers"] == {
            "X-Toanaas-Proxy-Secret": "test-secret"
        }
        assert adapter_request["follow_redirects"] is False
    assert validation_calls == [
        {
            "file_size": len(payload),
            "maximum_bytes": 0,
            "maximum_duration_seconds": 0,
        }
    ]


def test_edit3_real_inspector_keeps_exact_short_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import video_local_validation

    exact_bytes = 20 * MIB

    async def legacy_get_file_must_not_run(_file_id: str):
        raise AssertionError("Video Edit inspection must use the file-backed transport")

    monkeypatch.setattr(
        video_local_validation,
        "probe_video_file",
        lambda _path: {
            "ok": True,
            "bytes": exact_bytes,
            "duration": 60.0,
            "duration_ms": 60_000,
            "width": 640,
            "height": 360,
            "has_video": True,
            "has_audio": False,
            "audio_stream_count": 0,
            "format_name": "mov,mp4",
        },
    )

    fake_download_file_to_path = _streaming_download_fake(
        payload=b"boundary-probe",
        bytes_written=exact_bytes,
        sha256="b" * 64,
    )

    monkeypatch.setattr(
        video_edit_media_transport,
        "download_file_to_path",
        fake_download_file_to_path,
    )
    inspector = _compile_real_inspector(video_local_validation)

    result = asyncio.run(
        inspector(
            SimpleNamespace(
                bot=SimpleNamespace(get_file=legacy_get_file_must_not_run)
            ),
            {
                "source_file_id": "telegram-file-id",
                "source_file_name": "source.mp4",
                "source_file_size": exact_bytes,
                "source_duration": 60,
            },
        )
    )

    assert result["ok"] is True
    assert result["declared_bytes"] == exact_bytes
    assert result["declared_duration_seconds"] == 60
    assert result["actual_bytes"] == exact_bytes
    assert result["media_lane"] == "short_media"


@pytest.mark.parametrize(
    (
        "declared_bytes",
        "declared_duration",
        "actual_bytes",
        "actual_duration",
        "expected_lane",
    ),
    [
        (1 * MIB, 30, 20 * MIB + 1, 30.0, "large_media"),
        (1 * MIB, 30, 1 * MIB, 60.1, "large_media"),
        (0, 0, 1 * MIB, 30.0, "large_media"),
        (21 * MIB, 61, 1 * MIB, 30.0, "large_media"),
    ],
)
def test_edit3_real_inspector_uses_declared_and_actual_evidence_monotonically(
    monkeypatch: pytest.MonkeyPatch,
    declared_bytes: int,
    declared_duration: int,
    actual_bytes: int,
    actual_duration: float,
    expected_lane: str,
) -> None:
    """Inspection may promote to large media, but never demote a conservative lane."""

    payload = b"streamed-video-evidence"
    download_calls: list[dict] = []
    monkeypatch.setattr(
        video_local_validation,
        "probe_video_file",
        lambda _path: {
            "ok": True,
            "bytes": actual_bytes,
            "duration": actual_duration,
            "duration_ms": int(round(actual_duration * 1_000)),
            "width": 640,
            "height": 360,
            "has_video": True,
            "has_audio": False,
            "audio_stream_count": 0,
            "format_name": "mov,mp4",
        },
    )
    monkeypatch.setattr(
        video_edit_media_transport,
        "download_file_to_path",
        _streaming_download_fake(
            payload=payload,
            bytes_written=actual_bytes,
            sha256=hashlib.sha256(payload).hexdigest(),
            calls=download_calls,
        ),
    )
    inspector = _compile_real_inspector(video_local_validation)

    result = asyncio.run(
        inspector(
            SimpleNamespace(bot=SimpleNamespace()),
            {
                "source_file_id": "telegram-file-id",
                "source_file_name": "source.mp4",
                "source_file_size": declared_bytes,
                "source_duration": declared_duration,
            },
        )
    )

    assert result["ok"] is True
    assert result["declared_bytes"] == declared_bytes
    assert result["declared_duration_seconds"] == declared_duration
    assert result["actual_bytes"] == actual_bytes
    assert result["duration"] == actual_duration
    assert result["media_lane"] == expected_lane
    assert len(download_calls) == 1
    assert callable(download_calls[0]["get_file_json"] or download_calls[0]["open_json"])
    assert callable(download_calls[0]["stream_bytes"] or download_calls[0]["open_stream"])


def test_edit3_cloud_rollback_keeps_the_real_download_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import video_local_validation

    payload = b"bounded-cloud-control"
    download_calls: list[dict] = []
    monkeypatch.setattr(
        video_local_validation,
        "probe_video_file",
        lambda _path: {
            "ok": True,
            "bytes": len(payload),
            "duration": 8.0,
            "duration_ms": 8_000,
            "width": 640,
            "height": 360,
            "has_video": True,
            "has_audio": False,
            "audio_stream_count": 0,
            "format_name": "mov,mp4",
        },
    )

    fake_download_file_to_path = _streaming_download_fake(
        payload=payload,
        bytes_written=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        transport="file",
        calls=download_calls,
    )

    monkeypatch.setattr(
        video_edit_media_transport,
        "download_file_to_path",
        fake_download_file_to_path,
    )
    inspector = _compile_real_inspector(
        video_local_validation,
        api_root="https://api.telegram.org",
    )

    result = asyncio.run(
        inspector(
            SimpleNamespace(bot=SimpleNamespace()),
            {
                "source_file_id": "telegram-file-id",
                "source_file_name": "source.mp4",
                "source_file_size": len(payload),
                "source_duration": 8,
            },
        )
    )

    assert result["ok"] is True
    assert len(download_calls) == 1
    assert download_calls[0]["config"].is_local is False
    assert download_calls[0]["hard_max_bytes"] == (
        video_edit_media_transport.SHORT_MEDIA_MAX_BYTES
    )


def test_edit3_known_source_fails_before_transfer_when_disk_reserve_is_insufficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import video_local_validation

    declared_bytes = 10 * MIB
    download_calls: list[dict] = []

    monkeypatch.setattr(
        video_edit_media_transport,
        "download_file_to_path",
        _streaming_download_fake(
            payload=b"",
            bytes_written=0,
            sha256="0" * 64,
            calls=download_calls,
            failure=AssertionError("insufficient disk must fail before transfer"),
        ),
    )
    inspector = _compile_real_inspector(
        video_local_validation,
        shutil_dependency=SimpleNamespace(
            disk_usage=lambda _path: SimpleNamespace(
                free=(
                    video_edit_long_media.DEFAULT_WORKSPACE_RESERVE_BYTES
                    + declared_bytes
                    - 1
                )
            )
        ),
    )

    result = asyncio.run(
        inspector(
            SimpleNamespace(bot=SimpleNamespace()),
            {
                "source_file_id": "telegram-file-id",
                "source_file_name": "source.mp4",
                "source_file_size": declared_bytes,
                "source_duration": 30,
            },
        )
    )

    assert result["ok"] is False
    assert result["reason"] == "insufficient_disk"
    assert result["declared_bytes"] == declared_bytes
    assert result["declared_duration_seconds"] == 30
    assert result["media_lane"] == "short_media"
    assert download_calls == []


def test_edit3_real_inspector_retains_stream_evidence_when_ffprobe_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services import video_local_validation

    payload = b"probe-unavailable-after-complete-transfer"
    digest = hashlib.sha256(payload).hexdigest()

    async def legacy_get_file_must_not_run(_file_id: str):
        raise AssertionError("Video Edit inspection must use the file-backed transport")

    fake_download_file_to_path = _streaming_download_fake(
        payload=payload,
        bytes_written=len(payload),
        sha256=digest,
    )

    monkeypatch.setattr(
        video_edit_media_transport,
        "download_file_to_path",
        fake_download_file_to_path,
    )

    def probe_unavailable(_path):
        raise video_local_validation.LocalVideoValidationError("ffprobe_missing")

    monkeypatch.setattr(
        video_local_validation,
        "probe_video_file",
        probe_unavailable,
    )
    inspector = _compile_real_inspector(video_local_validation)

    result = asyncio.run(
        inspector(
            SimpleNamespace(
                bot=SimpleNamespace(get_file=legacy_get_file_must_not_run)
            ),
            {
                "source_file_id": "telegram-file-id",
                "source_file_name": "source.mp4",
                "source_file_size": len(payload),
                "source_duration": 8,
            },
        )
    )

    assert result["ok"] is False
    assert result["reason"] == "ffprobe_missing"
    assert result["declared_bytes"] == len(payload)
    assert result["declared_duration_seconds"] == 8
    assert result["actual_bytes"] == len(payload)
    assert result["source_sha256"] == digest
    assert result["media_lane"] == "short_media"


def test_edit3_stale_state_cannot_consume_another_video_product_upload() -> None:
    first, second, state, replies, probes = _run_canonical_upload(
        "manual_edit",
        active_product="product_video",
    )

    assert first is False and second is False
    assert probes == []
    assert replies == []
    assert state == video_edit_state_machine.start_lane("manual_edit")


@pytest.mark.parametrize(
    ("mode", "screen"),
    [
        ("manual_edit", "manual-screen"),
        ("ai_edit", "ai-screen"),
        ("quality_enhance", "quality-screen"),
    ],
)
def test_edit3_one_upload_probes_once_and_routes_to_exact_lane(mode: str, screen: str) -> None:
    first, second, state, replies, probes = _run_canonical_upload(mode)
    assert first is True and second is True
    assert probes == ["video-file-901"]
    assert len(replies) == 1
    assert replies[0]["text"] == screen
    assert state["edit_mode"] == mode
    assert state["current_screen"] == mode
    assert state["awaiting_media"] is False
    assert state["source_file_id"] == "video-file-901"
    assert state["source_file_unique_id"] == "telegram-opaque-901"
    assert state["source_video_hash"] == "a" * 64
    assert state["probe_count"] == 1


@pytest.mark.parametrize(
    (
        "source_size",
        "source_duration",
        "inspected_size",
        "inspected_duration",
        "expected_lane",
    ),
    [
        (20 * MIB, 60, 20 * MIB, 60.0, "short_media"),
        (20 * MIB + 1, 60, 20 * MIB + 1, 60.0, "large_media"),
        (20 * MIB, 61, 20 * MIB, 61.0, "large_media"),
        (0, 30, 1 * MIB, 30.0, "large_media"),
        (1 * MIB, 0, 1 * MIB, 30.0, "large_media"),
    ],
)
def test_edit3_exact_lane_boundaries_and_unknown_metadata_are_persisted(
    source_size: int,
    source_duration: int,
    inspected_size: int,
    inspected_duration: float,
    expected_lane: str,
) -> None:
    first, second, state, replies, probes = _run_canonical_upload(
        "manual_edit",
        source_size=source_size,
        source_duration=source_duration,
        inspected_size=inspected_size,
        inspected_duration=inspected_duration,
    )

    assert first is True and second is True
    assert probes == ["video-file-901"]
    assert len(replies) == 1
    assert state["media_lane"] == expected_lane
    assert state["source_metadata"]["media_lane"] == expected_lane
    assert state.get("local_worker_job_id") in {None, ""}
    assert state.get("job_id") in {None, "", 0}


def test_edit3_actual_byte_evidence_promotes_short_declaration_without_demoting() -> None:
    first, second, state, _replies, probes = _run_canonical_upload(
        "quality_enhance",
        source_size=20 * MIB,
        source_duration=60,
        inspected_size=20 * MIB + 1,
        inspected_duration=60.0,
    )

    assert first is True and second is True
    assert probes == ["video-file-901"]
    assert state["media_lane"] == "large_media"
    assert state["source_file_size"] == 20 * MIB + 1
    assert state["source_metadata"]["declared_bytes"] == 20 * MIB
    assert state["source_metadata"]["actual_bytes"] == 20 * MIB + 1


def test_edit3_actual_duration_promotes_short_declaration_without_demoting() -> None:
    first, second, state, _replies, probes = _run_canonical_upload(
        "ai_edit",
        source_size=1 * MIB,
        source_duration=60,
        inspected_size=1 * MIB,
        inspected_duration=61.0,
    )

    assert first is True and second is True
    assert probes == ["video-file-901"]
    assert state["media_lane"] == "large_media"
    assert state["source_duration"] == 61
    assert state["source_metadata"]["declared_duration_seconds"] == 60
    assert state["source_metadata"]["duration"] == 61.0


def test_edit3_transfer_resource_failure_keeps_saved_language_back_and_no_job() -> None:
    first, second, state, replies, probes = _run_canonical_upload(
        "manual_edit",
        valid=False,
        failure_reason="insufficient_disk",
        language="en",
    )

    assert first is True and second is True
    assert probes == ["video-file-901"]
    assert len(replies) == 1
    assert replies[0]["text"] == "en:insufficient_disk"
    assert _back_callback(replies[0]["reply_markup"]) == "videoedit|hub"
    assert state["last_error"] == "insufficient_disk"
    assert state["return_to"] == "videoedit|hub"
    assert state["awaiting_media"] is True
    assert state.get("local_worker_job_id") in {None, ""}
    assert state.get("job_id") in {None, "", 0}
    assert state.get("outbox_id") in {None, "", 0}


def test_edit3_transfer_failure_is_fail_closed_without_telegram_envelope_fallback() -> None:
    fallback_calls: list[str] = []
    first, second, state, replies, probes = _run_canonical_upload(
        "ai_edit",
        valid=False,
        failure_reason="stream_failed",
        fallback_result={
            "ok": True,
            "bytes": 1_024,
            "duration": 8.0,
            "duration_ms": 8_000,
        },
        fallback_calls=fallback_calls,
    )

    assert first is True and second is True
    assert probes == ["video-file-901"]
    assert fallback_calls == []
    assert len(replies) == 1
    assert state["awaiting_media"] is True
    assert state["source_file_id"] is None
    assert state["last_error"] == "stream_failed"
    assert state.get("job_id") in {None, "", 0}


def test_edit3_transport_exception_is_not_reclassified_as_ffprobe_failure() -> None:
    fallback_calls: list[str] = []
    first, second, state, replies, probes = _run_canonical_upload(
        "quality_enhance",
        inspection_exception=video_edit_media_transport.MediaTransferError(
            "stream_failed"
        ),
        fallback_result={
            "ok": True,
            "bytes": 1_024,
            "duration": 8.0,
            "duration_ms": 8_000,
        },
        fallback_calls=fallback_calls,
        language="en",
    )

    assert first is True and second is True
    assert probes == ["video-file-901"]
    assert fallback_calls == []
    assert len(replies) == 1
    assert replies[0]["text"] == "en:stream_failed"
    assert _back_callback(replies[0]["reply_markup"]) == "videoedit|hub"
    assert state["last_error"] == "stream_failed"
    assert state["return_to"] == "videoedit|hub"
    assert state["awaiting_media"] is True
    assert state.get("job_id") in {None, "", 0}


def test_edit3_probe_unavailable_preserves_truthful_telegram_envelope_fallback() -> None:
    fallback_calls: list[str] = []
    first, second, state, replies, probes = _run_canonical_upload(
        "manual_edit",
        valid=False,
        failure_reason="ffprobe_missing",
        failure_metadata={
            "actual_bytes": 1_024,
            "declared_bytes": 1_024,
            "declared_duration_seconds": 8,
            "source_sha256": "c" * 64,
            "media_lane": "short_media",
        },
        fallback_result={
            "ok": True,
            "reason": "",
            "bytes": 1_024,
            "duration": 8.0,
            "duration_ms": 8_000,
            "width": 1_080,
            "height": 1_920,
            "has_video": True,
            "has_audio": False,
            "audio_stream_count": 0,
            "format_name": "telegram_video",
            "probe_fallback": "telegram_video_metadata",
        },
        fallback_calls=fallback_calls,
    )

    assert first is True and second is True
    assert probes == ["video-file-901"]
    assert fallback_calls == ["ffprobe_missing"]
    assert len(replies) == 1
    assert state["awaiting_media"] is False
    assert state["source_file_id"] == "video-file-901"
    assert state["media_lane"] == "short_media"
    assert state["source_video_hash"] == "c" * 64
    assert state["source_metadata"]["actual_bytes"] == 1_024
    assert state["source_metadata"]["declared_bytes"] == 1_024
    assert state["source_metadata"]["declared_duration_seconds"] == 8
    assert state["source_metadata"]["probe_fallback"] == "telegram_video_metadata"
    assert state.get("job_id") in {None, "", 0}


def test_edit3_transport_resource_copy_is_truthful_and_localized() -> None:
    public_error = _compile_function("video_local_public_error", {})

    vi_disk = public_error("insufficient_disk", "vi")
    en_disk = public_error("insufficient_disk", "en")
    vi_transfer = public_error("stream_failed", "vi")
    en_transfer = public_error("stream_failed", "en")

    assert "dung lượng" in vi_disk.lower()
    assert "storage" in en_disk.lower() or "space" in en_disk.lower()
    assert "tải" in vi_transfer.lower()
    assert "download" in en_transfer.lower() or "transfer" in en_transfer.lower()
    for text in (vi_disk, en_disk, vi_transfer, en_transfer):
        assert "50 MB" not in text
        assert "30 phút" not in text
        assert "30 minutes" not in text


def test_edit3_completed_inspection_cannot_overwrite_concurrent_state_winner() -> None:
    winner = {
        **video_edit_state_machine.start_lane("manual_edit"),
        "step": "manual_edit",
        "current_screen": "manual_edit",
        "awaiting_media": False,
        "intake_in_progress": False,
        "source_file_id": "winner-video",
        "source_video_id": "winner-video",
        "source_video_hash": "b" * 64,
    }

    first, second, state, replies, probes = _run_canonical_upload(
        "manual_edit",
        concurrent_winner=winner,
        repeat=False,
    )

    assert first is True and second is None
    assert probes == ["video-file-901"]
    assert state == winner
    assert replies == [{"text": "stale", "winner": winner}]


@pytest.mark.parametrize(
    ("failure_reason", "inspection_exception"),
    [
        ("insufficient_disk", None),
        (
            "stream_failed",
            video_edit_media_transport.MediaTransferError("stream_failed"),
        ),
    ],
)
def test_edit3_failed_inspection_cannot_overwrite_a_concurrent_state_winner(
    failure_reason: str,
    inspection_exception: Exception | None,
) -> None:
    winner = {
        **video_edit_state_machine.start_lane("manual_edit"),
        "step": "manual_edit",
        "current_screen": "manual_edit",
        "awaiting_media": False,
        "intake_in_progress": False,
        "source_file_id": "winner-video",
        "source_video_id": "winner-video",
        "source_video_hash": "b" * 64,
        "source_metadata": {"winner": "byte-for-byte"},
        "job_id": 44,
    }

    first, second, state, replies, probes = _run_canonical_upload(
        "manual_edit",
        valid=False,
        failure_reason=failure_reason,
        inspection_exception=inspection_exception,
        concurrent_winner=winner,
        repeat=False,
    )

    assert first is True and second is None
    assert probes == ["video-file-901"]
    assert state == winner
    assert replies == [{"text": "stale", "winner": winner}]
    assert state["job_id"] == 44


@pytest.mark.parametrize("legacy_step", ["await_concat", "await_logo", "await_srt"])
def test_edit3_legacy_stale_state_cannot_consume_another_product_upload(
    legacy_step: str,
) -> None:
    state = {
        "step": legacy_step,
        "selected_tool": "manual",
        "source_file_id": "old-video",
    }
    replies: list[str] = []
    clear_calls: list[int] = []

    class Message:
        message_id = 999
        video = None
        document = None
        photo = []

        async def reply_text(self, text: str, **_kwargs):
            replies.append(text)
            return True

    recovery_mode = _compile_function(
        "video_edit_recovery_mode",
        {"video_edit_state_machine": video_edit_state_machine},
    )
    handler = _compile_function(
        "handle_video_editor_pending_upload",
        {
            "get_video_editor_pending": lambda _uid: dict(state),
            "get_video_session": lambda _uid: {"product_id": "product_video"},
            "video_edit_recovery_mode": recovery_mode,
            "video_edit_state_machine": video_edit_state_machine,
            "safe_int": lambda value, default=0: int(value or default),
            "clear_video_editor_competing_video_states": lambda uid, _context: clear_calls.append(uid),
            "get_user_language": lambda _uid: "vi",
            "video_editor_aux_source_from_update": lambda _update, _kind: {},
            "video_editor_source_from_update": lambda _update: {},
            "video_local_input_keyboard": lambda *_args, **_kwargs: "input-keyboard",
            "video_local_public_error": lambda reason: reason,
        },
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=78),
        message=Message(),
    )

    assert asyncio.run(handler(update, SimpleNamespace(user_data={}))) is False
    assert clear_calls == []
    assert replies == []


def test_edit3_invalid_upload_replies_once_and_keeps_active_lane() -> None:
    first, second, state, replies, probes = _run_canonical_upload("manual_edit", valid=False)
    assert first is True and second is True
    assert probes == ["video-file-901"]
    assert len(replies) == 1
    assert state["edit_mode"] == "manual_edit"
    assert state["step"] == "await_edit_video"
    assert state["awaiting_media"] is True
    assert state["source_file_id"] is None
    assert state["last_error"] == "invalid_video_metadata"


def test_edit3_invalid_text_replies_once_and_keeps_session_for_retry() -> None:
    persisted = video_edit_state_machine.start_lane("ai_edit")
    replies: list[dict] = []

    class Message:
        message_id = 902
        text = "đây không phải video"

        async def reply_text(self, text: str, **kwargs):
            replies.append({"text": text, **kwargs})
            return True

    update = SimpleNamespace(effective_user=SimpleNamespace(id=78), message=Message())

    def save(_uid: int, state: dict) -> dict:
        persisted.clear()
        persisted.update(state)
        return dict(persisted)

    handler = _compile_function(
        "handle_video_editor_invalid_intake_text",
        {
            "get_video_editor_pending": lambda _uid: dict(persisted),
            "video_edit_state_machine": video_edit_state_machine,
            "safe_int": lambda value, default=0: int(value or default),
            "save_video_edit_canonical_state": save,
            "get_user_language": lambda _uid: "vi",
            "video_edit_lane_upload_keyboard": _compiled_video_edit_lane_upload_keyboard(),
        },
    )
    assert asyncio.run(handler(update, SimpleNamespace())) is True
    assert asyncio.run(handler(update, SimpleNamespace())) is True
    assert len(replies) == 1
    assert persisted["edit_mode"] == "ai_edit"
    assert persisted["awaiting_media"] is True
    assert persisted["source_file_id"] is None
    assert persisted["last_error"] == "video_file_required"
    assert _back_callback(replies[0]["reply_markup"]) == "videoedit|hub"


def test_edit3_back_matrix_never_targets_creation_scene3_or_global_help() -> None:
    assert video_edit_state_machine.back_target("manual_edit") == "videoedit|hub"
    assert video_edit_state_machine.back_target("ai_edit") == "videoedit|hub"
    assert video_edit_state_machine.back_target("quality_enhance") == "videoedit|hub"
    assert video_edit_state_machine.back_target("manual_edit", child=True) == "videoedit|manual"
    assert video_edit_state_machine.back_target("ai_edit", child=True) == "videoedit|ai"
    assert video_edit_state_machine.back_target("quality_enhance", child=True) == "videoedit|restore"
    module_source = (ROOT / "services" / "video_edit_state_machine.py").read_text(encoding="utf-8")
    for leaked_route in ("SCENE3", "create_video", "menu|guide", "guide_video_ai"):
        assert leaked_route not in module_source


def test_edit3_single_registered_video_media_gateway_and_read_only_legacy_callbacks() -> None:
    media = _function_source("handle_media_cache_only")
    documents = _function_source("handle_document_cache_only")
    audio = _function_source("handle_media")
    photo = _function_source("handle_photo")
    assert media.count("handle_video_editor_pending_upload(update, context)") == 1
    assert documents.count("handle_video_editor_pending_upload(update, context)") == 1
    assert audio.count("handle_video_editor_pending_upload(update, context)") == 1
    assert photo.count("handle_video_editor_pending_upload(update, context)") == 1
    assert BOT_SOURCE.count("async def handle_video_editor_pending_upload(") == 1

    callback = _function_source("handle_video_editor_callback")
    compatibility_start = callback.index("requested_group = video_edit_state_machine.requested_group(raw_action)")
    compatibility_end = callback.index("if action == \"guide\"")
    compatibility = callback[compatibility_start:compatibility_end]
    assert "canonical_compatibility_action(raw_action)" in compatibility
    assert "set_video_editor_pending" not in compatibility
    assert "update_video_editor_pending" not in compatibility
    assert "clear_video_editor_pending" not in compatibility


@pytest.mark.parametrize(
    ("expression", "expected"),
    (
        ("response.content", True),
        ("reply.content", True),
        ("client.get(...).content", True),
        ("receipt.content_type", False),
        ("chunk", False),
    ),
)
def test_edit3_whole_response_content_guard_is_receiver_independent(
    expression: str,
    expected: bool,
) -> None:
    expression_module = ast.parse(expression)
    assert any(
        _is_whole_response_content_access(node)
        for node in ast.walk(expression_module)
    ) is expected


def test_edit3_probe_contract_exposes_required_local_metadata_without_side_effects() -> None:
    probe = _function_source("inspect_video_editor_source")
    intake = _function_source("handle_video_editor_pending_upload")
    validation = (ROOT / "services" / "video_local_validation.py").read_text(encoding="utf-8")
    probe_module = ast.parse("from __future__ import annotations\n\n" + probe)
    calls = [node for node in ast.walk(probe_module) if isinstance(node, ast.Call)]

    def called_name(call: ast.Call) -> str:
        if isinstance(call.func, ast.Name):
            return call.func.id
        if isinstance(call.func, ast.Attribute):
            return call.func.attr
        return ""

    forbidden_whole_file_calls = {
        "bytearray",
        "BytesIO",
        "StringIO",
        "read_bytes",
        "read_text",
        "download_as_bytearray",
        "download_to_memory",
        "readall",
        "getvalue",
        "getbuffer",
        "write_bytes",
    }

    def is_whole_body_expression(node: ast.expr) -> bool:
        """Recognize expressions that materialize a streamed response body."""

        if _is_whole_response_content_access(node):
            return True
        if isinstance(node, ast.Call):
            if called_name(node) == "iter_bytes":
                return True
            if called_name(node) == "read" and is_unbounded_read(node):
                return True
        return False

    def is_bytes_join_of_iter_bytes(call: ast.Call) -> bool:
        return (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "join"
            and isinstance(call.func.value, ast.Constant)
            and isinstance(call.func.value.value, bytes)
            and any(is_whole_body_expression(argument) for argument in call.args)
        )

    def is_wrapper_of_whole_body(call: ast.Call) -> bool:
        return (
            called_name(call) in {"bytes", "list", "tuple"}
            and any(is_whole_body_expression(argument) for argument in call.args)
        )

    def keyword_value(call: ast.Call, name: str) -> ast.expr | None:
        for keyword in call.keywords:
            if keyword.arg == name:
                return keyword.value
        return None

    def is_false(node: ast.expr | None) -> bool:
        return isinstance(node, ast.Constant) and node.value is False

    def bounded_positive_integer(node: ast.expr) -> int | None:
        """Return a statically bounded positive chunk size, if one is present."""

        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, int):
                return None
            return node.value if 0 < node.value <= 8 * MIB else None
        if not isinstance(node, ast.BinOp) or not isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Mod)
        ):
            return None
        left = bounded_positive_integer(node.left)
        right = bounded_positive_integer(node.right)
        if left is None or right is None:
            return None
        try:
            if isinstance(node.op, ast.Add):
                value = left + right
            elif isinstance(node.op, ast.Sub):
                value = left - right
            elif isinstance(node.op, ast.Mult):
                value = left * right
            elif isinstance(node.op, ast.FloorDiv):
                value = left // right
            else:
                value = left % right
        except ZeroDivisionError:
            return None
        return value if 0 < value <= 8 * MIB else None

    def is_unbounded_read(call: ast.Call) -> bool:
        if called_name(call) != "read":
            return False
        if not call.args:
            return True
        size = call.args[0]
        # Dynamic values such as os.path.getsize(path) can consume the entire
        # file. A receipt SHA makes this second pass unnecessary.
        return bounded_positive_integer(size) is None

    credential_requests = [
        call
        for call in calls
        if called_name(call) in {"get", "post", "request", "stream"}
        and keyword_value(call, "headers") is not None
    ]
    json_requests = [
        call for call in credential_requests if keyword_value(call, "json") is not None
    ]
    stream_requests = [
        call for call in credential_requests if called_name(call) == "stream"
    ]
    iter_bytes_calls = [
        call for call in calls if called_name(call) == "iter_bytes"
    ]

    assert "probe_video_file" in probe
    assert "download_file_to_path" in probe
    assert "telegram_local_media_fetch" not in probe
    assert "context.bot.get_file" not in probe
    assert all(called_name(call) not in forbidden_whole_file_calls for call in calls)
    assert not any(
        _is_whole_response_content_access(node) for node in ast.walk(probe_module)
    )
    assert not any(is_bytes_join_of_iter_bytes(call) for call in calls)
    assert not any(is_wrapper_of_whole_body(call) for call in calls)
    assert not any(is_unbounded_read(call) for call in calls)
    assert json_requests, "credential-bearing getFile JSON adapter is required"
    assert stream_requests, "credential-bearing media stream adapter is required"
    assert all(
        is_false(keyword_value(call, "follow_redirects"))
        for call in (*json_requests, *stream_requests)
    )
    assert iter_bytes_calls, "stream adapter must expose bounded iter_bytes chunks"
    assert all(
        bounded_positive_integer(keyword_value(call, "chunk_size")) is not None
        for call in iter_bytes_calls
    )
    assert "audio_stream_count" in validation
    assert "format_name" in validation
    canonical = intake[:intake.index('step = str(state.get("step") or "")')]
    assert canonical.count("inspect_video_editor_source(context, source)") == 1
    for forbidden in (
        "create_local_worker_job",
        "submit_video_ai_edit_job",
        "submit_local_video_editor_job",
        "spend_fixed_credit_info",
        "wallet",
    ):
        assert forbidden not in canonical


def test_edit3_large_media_inspector_is_exclusive_to_video_edit_routes() -> None:
    unbounded_inspector = "inspect_video_editor_source"
    bounded_inspector = "inspect_bounded_telegram_video_source"

    def direct_calls(function_name: str, callee_name: str) -> int:
        function_module = ast.parse(
            "from __future__ import annotations\n\n" + _function_source(function_name)
        )
        return sum(
            isinstance(call.func, ast.Name) and call.func.id == callee_name
            for call in ast.walk(function_module)
            if isinstance(call, ast.Call)
        )

    unbounded_callers = {
        node.name
        for node in BOT_MODULE.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and direct_calls(node.name, unbounded_inspector)
    }

    assert unbounded_callers == {"handle_video_editor_pending_upload"}
    assert direct_calls("handle_video_product_pending_media", unbounded_inspector) == 0
    assert direct_calls("handle_video_reference_pending_upload", unbounded_inspector) == 0
    assert direct_calls("handle_video_product_pending_media", bounded_inspector) == 2
    assert direct_calls("handle_video_reference_pending_upload", bounded_inspector) == 1


def test_edit3_bounded_telegram_inspector_rejects_oversized_declaration_before_download() -> None:
    helper_name = "inspect_bounded_telegram_video_source"
    assert any(
        isinstance(node, ast.AsyncFunctionDef) and node.name == helper_name
        for node in BOT_MODULE.body
    )
    inspector = _compile_function(
        helper_name,
        {
            "video_local_validation": video_local_validation,
            "safe_int": lambda value, default=0: int(value or default),
            "asyncio": asyncio,
            "hashlib": hashlib,
            "os": os,
            "tempfile": tempfile,
        },
    )

    class Bot:
        def __getattr__(self, name: str):
            raise AssertionError(f"oversized declaration accessed bot.{name}")

    result = asyncio.run(
        inspector(
            SimpleNamespace(bot=Bot()),
            {
                "source_file_id": "oversized-telegram-file",
                "source_file_name": "source.mp4",
                "source_file_size": video_local_validation.MAX_UPLOAD_BYTES + 1,
                "source_duration": 8,
            },
        )
    )

    assert result == {"ok": False, "reason": "video_too_large"}
