from __future__ import annotations

import importlib
import hashlib
import os

import pytest

from services import telegram_transport, video_local_validation


MIB = 1024 * 1024
TOKEN = "123:token"
LOCAL_ROOT = "https://tg.toanaas.vn"
LOCAL_FILE_ROOT = "/var/lib/telegram-bot-api"
LOCAL_MEDIA_PATH = "/localfile"


def _media_transport():
    return importlib.import_module("services.video_edit_media_transport")


def _local_config(**overrides):
    values = {
        "token": TOKEN,
        "api_root": LOCAL_ROOT,
        "proxy_secret_header": "X-Toanaas-Proxy-Secret",
        "proxy_secret": "test-secret",
        "local_file_root": LOCAL_FILE_ROOT,
        "local_media_path": LOCAL_MEDIA_PATH,
    }
    values.update(overrides)
    return _media_transport().TelegramMediaConfig(**values)


def test_video_edit_lane_uses_both_short_media_boundaries() -> None:
    media_transport = _media_transport()

    assert media_transport.select_media_lane(duration_seconds=60, size_bytes=20 * MIB) == "short_media"
    assert media_transport.select_media_lane(duration_seconds=61, size_bytes=20 * MIB) == "large_media"
    assert media_transport.select_media_lane(duration_seconds=60, size_bytes=20 * MIB + 1) == "large_media"


@pytest.mark.parametrize(
    ("duration_seconds", "size_bytes"),
    [
        (None, 10 * MIB),
        (0, 10 * MIB),
        (-1, 10 * MIB),
        (30, None),
        (30, 0),
        (30, -1),
    ],
)
def test_video_edit_lane_routes_unknown_or_nonpositive_metadata_to_large(
    duration_seconds: float | None,
    size_bytes: int | None,
) -> None:
    media_transport = _media_transport()

    assert (
        media_transport.select_media_lane(
            duration_seconds=duration_seconds,
            size_bytes=size_bytes,
        )
        == "large_media"
    )


def test_video_edit_can_disable_product_size_and_duration_rejection_only_explicitly() -> None:
    metadata = {
        "ok": True,
        "bytes": 300 * MIB,
        "duration": 7_200,
        "width": 1920,
        "height": 1080,
    }

    size_only = {
        **metadata,
        "bytes": video_local_validation.MAX_UPLOAD_BYTES + 1,
        "duration": 1,
    }
    rejected_by_default = video_local_validation.validate_source_metadata(
        size_only,
        file_size=video_local_validation.MAX_UPLOAD_BYTES + 1,
    )
    assert rejected_by_default["ok"] is False
    assert rejected_by_default["reason"] == "video_too_large"

    duration_only = {
        **metadata,
        "bytes": 1,
        "duration": video_local_validation.MAX_DURATION_SECONDS + 1,
    }
    rejected_duration_by_default = video_local_validation.validate_source_metadata(
        duration_only,
        file_size=1,
    )
    assert rejected_duration_by_default["ok"] is False
    assert rejected_duration_by_default["reason"] == "duration_too_long"

    accepted = video_local_validation.validate_source_metadata(
        metadata,
        file_size=300 * MIB,
        maximum_bytes=0,
        maximum_duration_seconds=0,
    )
    assert accepted["ok"] is True
    assert accepted["reason"] == ""

    invalid_metadata = {**metadata, "ok": False, "reason": "invalid_video_metadata"}
    still_invalid = video_local_validation.validate_source_metadata(
        invalid_metadata,
        file_size=300 * MIB,
        maximum_bytes=0,
        maximum_duration_seconds=0,
    )
    assert still_invalid["ok"] is False
    assert still_invalid["reason"] == "invalid_video_metadata"


def test_telegram_endpoint_builders_produce_exact_cloud_local_and_loopback_urls() -> None:
    assert telegram_transport.bot_method_url(
        api_root="",
        token=TOKEN,
        method="getFile",
    ) == "https://api.telegram.org/bot123:token/getFile"
    assert telegram_transport.bot_method_url(
        api_root="https://tg.toanaas.vn/bot",
        token=TOKEN,
        method="sendDocument",
    ) == "https://tg.toanaas.vn/bot123:token/sendDocument"
    assert telegram_transport.bot_method_url(
        api_root="http://127.0.0.1:8081",
        token=TOKEN,
        method="getMe",
    ) == "http://127.0.0.1:8081/bot123:token/getMe"

    assert telegram_transport.bot_file_url(
        api_root="",
        token=TOKEN,
        file_path="videos/file_1.mp4",
    ) == "https://api.telegram.org/file/bot123:token/videos/file_1.mp4"
    assert telegram_transport.bot_file_url(
        api_root=LOCAL_ROOT,
        token=TOKEN,
        file_path="videos/file_1.mp4",
    ) == "https://tg.toanaas.vn/file/bot123:token/videos/file_1.mp4"


@pytest.mark.parametrize(
    "api_root",
    (
        "http://tg.toanaas.vn",
        "ftp://tg.toanaas.vn",
        "https://user:pass@tg.toanaas.vn",
        "https://@tg.toanaas.vn",
        "https://tg.toanaas.vn?token=leak",
        "https://tg.toanaas.vn?",
        "https://tg.toanaas.vn#fragment",
        "https://tg.toanaas.vn#",
        "https://tg.toanaas.vn:not-a-port",
        "https://tg.toanaas.vn:",
        "https://tg.toanaas.vn:0",
        "https://tg.toanaas.vn\\@evil.example",
        "https://tg.toanaas.vn/../evil",
        "https://tg.toanaas.vn//evil",
        "https://tg.toanaas.vn/%2e%2e/evil",
        "https://tg.toanaas.vn\r\n.evil.example",
    ),
)
def test_telegram_endpoint_builders_reject_unsafe_api_roots(api_root: str) -> None:
    with pytest.raises(ValueError):
        telegram_transport.bot_method_url(api_root=api_root, token=TOKEN, method="getFile")
    with pytest.raises(ValueError):
        telegram_transport.bot_file_url(api_root=api_root, token=TOKEN, file_path="videos/file.mp4")


@pytest.mark.parametrize("api_root", ("https://tg.toanaas.vn?", "https://tg.toanaas.vn#"))
def test_normalize_api_root_rejects_empty_query_or_fragment_delimiters(api_root: str) -> None:
    with pytest.raises(ValueError):
        telegram_transport.normalize_api_root(api_root)


@pytest.mark.parametrize(
    "method",
    (
        "",
        "1getFile",
        "get/File",
        "getFile?debug=1",
        "getFile#fragment",
        "getFile%2fdeleteWebhook",
        "getFile\r\nX-Evil",
        "x" * 65,
    ),
)
def test_bot_method_url_rejects_unsafe_method_names(method: str) -> None:
    with pytest.raises(ValueError):
        telegram_transport.bot_method_url(api_root=LOCAL_ROOT, token=TOKEN, method=method)


@pytest.mark.parametrize(
    "token",
    (
        "",
        " 123:token",
        "123:to/ken",
        "123:to\\ken",
        "123:to?ken",
        "123:to#ken",
        "123:to%2fken",
        "123:to\r\nken",
        "123:to\x00ken",
    ),
)
def test_telegram_endpoint_builders_reject_token_path_injection(token: str) -> None:
    with pytest.raises(ValueError):
        telegram_transport.bot_method_url(api_root=LOCAL_ROOT, token=token, method="getFile")
    with pytest.raises(ValueError):
        telegram_transport.bot_file_url(api_root=LOCAL_ROOT, token=token, file_path="videos/file.mp4")


@pytest.mark.parametrize(
    "file_path",
    (
        "",
        "/videos/file.mp4",
        "videos//file.mp4",
        "videos/./file.mp4",
        "videos/../file.mp4",
        "videos\\file.mp4",
        "videos/%2e%2e/file.mp4",
        "videos/%2fetc/passwd",
        "videos/%5c..%5csecret",
        "videos/%0d%0aX-Evil",
        "videos/file.mp4?download=1",
    ),
)
def test_bot_file_url_rejects_unsafe_file_paths(file_path: str) -> None:
    with pytest.raises(ValueError):
        telegram_transport.bot_file_url(api_root=LOCAL_ROOT, token=TOKEN, file_path=file_path)


def test_local_media_url_requires_current_token_and_preserves_its_exact_segment() -> None:
    absolute_path = "/var/lib/telegram-bot-api/123:token/videos/file_1.mp4"
    assert telegram_transport.local_media_url(
        api_root=LOCAL_ROOT,
        token=TOKEN,
        absolute_file_path=absolute_path,
        file_root=LOCAL_FILE_ROOT,
        media_path=LOCAL_MEDIA_PATH,
    ) == "https://tg.toanaas.vn/localfile/123:token/videos/file_1.mp4"

    with pytest.raises(TypeError):
        telegram_transport.local_media_url(
            api_root=LOCAL_ROOT,
            absolute_file_path=absolute_path,
            file_root=LOCAL_FILE_ROOT,
            media_path=LOCAL_MEDIA_PATH,
        )


@pytest.mark.parametrize(
    "absolute_file_path",
    (
        "/var/lib/telegram-bot-api/999:token/videos/file.mp4",
        "/var/lib/telegram-bot-api/123:token-prefix/videos/file.mp4",
        "/var/lib/telegram-bot-api/prefix-123:token/videos/file.mp4",
        "/var/lib/telegram-bot-api-copy/123:token/videos/file.mp4",
        "/tmp/var/lib/telegram-bot-api/123:token/videos/file.mp4",
        "/var/lib/telegram-bot-api/../telegram-bot-api/123:token/videos/file.mp4",
        "/var/lib/telegram-bot-api//123:token/videos/file.mp4",
        "/var/lib/telegram-bot-api/123:token//videos/file.mp4",
        "/var/lib/telegram-bot-api/123:token/videos/./file.mp4",
        "/var/lib/telegram-bot-api/123:token/videos/../file.mp4",
        "/var/lib/telegram-bot-api/123:token/videos\\file.mp4",
        "/var/lib/telegram-bot-api/123:token/videos/%2e%2e/file.mp4",
        "/var/lib/telegram-bot-api/123:token/videos/%2fetc/passwd",
        "/var/lib/telegram-bot-api/123:token/videos/%5csecret",
        "/var/lib/telegram-bot-api/123:token/videos/%0d%0aX-Evil",
    ),
)
def test_local_media_url_rejects_wrong_token_traversal_and_root_smuggling(
    absolute_file_path: str,
) -> None:
    with pytest.raises(ValueError):
        telegram_transport.local_media_url(
            api_root=LOCAL_ROOT,
            token=TOKEN,
            absolute_file_path=absolute_file_path,
            file_root=LOCAL_FILE_ROOT,
            media_path=LOCAL_MEDIA_PATH,
        )


@pytest.mark.parametrize(
    ("file_root", "media_path"),
    (
        ("var/lib/telegram-bot-api", "/localfile"),
        ("/var//lib/telegram-bot-api", "/localfile"),
        ("/var/lib/../telegram-bot-api", "/localfile"),
        ("/var/lib/telegram-bot-api/", "/localfile"),
        ("/var/lib/telegram-bot-api", "localfile"),
        ("/var/lib/telegram-bot-api", "/localfile/"),
        ("/var/lib/telegram-bot-api", "/localfile//media"),
        ("/var/lib/telegram-bot-api", "/localfile/../media"),
        ("/var/lib/telegram-bot-api", "/localfile%2fmedia"),
        ("/var/lib/telegram-bot-api", "/localfile\\media"),
    ),
)
def test_local_media_url_rejects_unsafe_configured_paths(
    file_root: str,
    media_path: str,
) -> None:
    with pytest.raises(ValueError):
        telegram_transport.local_media_url(
            api_root=LOCAL_ROOT,
            token=TOKEN,
            absolute_file_path="/var/lib/telegram-bot-api/123:token/videos/file.mp4",
            file_root=file_root,
            media_path=media_path,
        )


def test_local_media_url_rejects_cloud_and_unsafe_remote_roots() -> None:
    kwargs = {
        "token": TOKEN,
        "absolute_file_path": "/var/lib/telegram-bot-api/123:token/videos/file.mp4",
        "file_root": LOCAL_FILE_ROOT,
        "media_path": LOCAL_MEDIA_PATH,
    }
    for root in ("", "https://api.telegram.org", "http://tg.toanaas.vn"):
        with pytest.raises(ValueError):
            telegram_transport.local_media_url(api_root=root, **kwargs)


def test_telegram_media_config_binds_secret_to_exact_local_origin() -> None:
    config = _local_config()

    assert config.is_local is True
    assert config.follow_redirects is False
    assert config.request_headers(
        request_url="https://tg.toanaas.vn/bot123:token/getFile"
    ) == {"X-Toanaas-Proxy-Secret": "test-secret"}
    assert config.request_headers(
        request_url="https://TG.TOANAAS.VN:443/localfile/123:token/videos/file.mp4"
    ) == {"X-Toanaas-Proxy-Secret": "test-secret"}

    for request_url in (
        "https://tg.toanaas.vn.evil/bot123:token/getFile",
        "https://api.telegram.org/bot123:token/getFile",
        "https://tg.toanaas.vn:444/bot123:token/getFile",
        "https://other.example/bot123:token/getFile",
    ):
        assert config.request_headers(request_url=request_url) == {}


def test_telegram_media_config_never_returns_secret_for_cloud_configuration() -> None:
    config = _local_config(api_root="https://api.telegram.org")

    assert config.is_local is False
    assert config.request_headers(
        request_url="https://api.telegram.org/bot123:token/getFile"
    ) == {}
    assert config.request_headers(
        request_url="https://tg.toanaas.vn/bot123:token/getFile"
    ) == {}


def test_telegram_media_config_requires_request_url_and_rejects_unsafe_request_url() -> None:
    config = _local_config()

    with pytest.raises(TypeError):
        config.request_headers()
    with pytest.raises(ValueError):
        config.request_headers(request_url="https://user:pass@tg.toanaas.vn/bot123:token/getFile")
    with pytest.raises(ValueError):
        config.request_headers(request_url="http://tg.toanaas.vn/bot123:token/getFile")


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("proxy_secret", "abc\r\nX-Evil: yes"),
        ("proxy_secret_header", "X-Good\r\nX-Evil"),
        ("proxy_secret_header", "Bad Header"),
        ("proxy_secret_header", "Bad:Header"),
        ("token", "123:token\r\nInjected"),
        ("api_root", "https://tg.toanaas.vn\r\n.evil"),
        ("local_file_root", "/var/lib/../telegram-bot-api"),
        ("local_media_path", "/localfile/%2e%2e"),
    ),
)
def test_telegram_media_config_rejects_raw_header_secret_and_transport_injection(
    field: str,
    value: str,
) -> None:
    with pytest.raises(ValueError) as exc_info:
        _local_config(**{field: value})
    assert value not in str(exc_info.value)


def test_telegram_media_config_repr_does_not_log_token_or_secret() -> None:
    config = _local_config()

    rendered = repr(config)
    assert TOKEN not in rendered
    assert "test-secret" not in rendered


def test_telegram_media_config_redirect_policy_cannot_be_enabled() -> None:
    with pytest.raises(TypeError):
        _local_config(follow_redirects=True)


class _BoundedStream:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.requested = []

    def __call__(self, *, url, headers, follow_redirects, chunk_size):
        self.requested.append((url, headers, follow_redirects, chunk_size))
        assert chunk_size <= 512 * 1024
        return iter(self.chunks)


def _get_file(*, path, size=None):
    calls = []

    def request(*, url, headers, follow_redirects, json):
        calls.append((url, headers, follow_redirects, json))
        result = {"file_path": path}
        if size is not None:
            result["file_size"] = size
        return {"ok": True, "result": result}

    request.calls = calls
    return request


def test_download_streams_to_private_partial_then_atomically_replaces_and_receipts(tmp_path) -> None:
    media_transport = _media_transport()
    target = tmp_path / "clip.mp4"
    chunks = [b"first-", b"second"]
    stream = _BoundedStream(chunks)
    get_file = _get_file(path="/var/lib/telegram-bot-api/123:token/videos/file.mp4", size=sum(map(len, chunks)))
    progress = []

    receipt = media_transport.download_file_to_path(
        config=_local_config(),
        file_id="file-id",
        destination=target,
        get_file_json=get_file,
        stream_bytes=stream,
        progress_callback=lambda actual, declared: progress.append((actual, declared)),
    )

    assert target.read_bytes() == b"".join(chunks)
    assert not target.with_name("clip.mp4.partial").exists()
    assert receipt.lane == "large_media"
    assert receipt.transport == "localfile"
    assert receipt.actual_bytes == 12
    assert receipt.declared_bytes == 12
    assert receipt.sha256 == hashlib.sha256(b"".join(chunks)).hexdigest()
    assert progress == [(6, 12), (12, 12)]
    assert get_file.calls == [
        ("https://tg.toanaas.vn/bot123:token/getFile", {"X-Toanaas-Proxy-Secret": "test-secret"}, False, {"file_id": "file-id"})
    ]
    assert stream.requested == [
        ("https://tg.toanaas.vn/localfile/123:token/videos/file.mp4", {"X-Toanaas-Proxy-Secret": "test-secret"}, False, 512 * 1024)
    ]


def test_download_cloud_rolls_back_to_safe_file_endpoint_without_credentials_in_headers(tmp_path) -> None:
    media_transport = _media_transport()
    stream = _BoundedStream([b"ok"])

    receipt = media_transport.download_file_to_path(
        config=_local_config(api_root="https://api.telegram.org"),
        file_id="file-id",
        destination=tmp_path / "cloud.mp4",
        get_file_json=_get_file(path="videos/file.mp4", size=2),
        stream_bytes=stream,
    )

    assert receipt.transport == "file"
    assert stream.requested[0][:3] == (
        "https://api.telegram.org/file/bot123:token/videos/file.mp4", {}, False
    )


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({}, "get_file_invalid"),
        ({"ok": False, "result": {}}, "get_file_invalid"),
        ({"ok": True, "result": {"file_path": "../bad"}}, "get_file_invalid"),
    ],
)
def test_download_rejects_malformed_get_file_without_creating_output(tmp_path, payload, reason) -> None:
    media_transport = _media_transport()
    target = tmp_path / "bad.mp4"

    with pytest.raises(media_transport.MediaTransferError) as error:
        media_transport.download_file_to_path(
            config=_local_config(), file_id="file-id", destination=target,
            get_file_json=lambda **_kwargs: payload, stream_bytes=_BoundedStream([b"x"]),
        )

    assert error.value.reason == reason
    assert not target.exists()
    assert not target.with_name("bad.mp4.partial").exists()


def test_download_refuses_redirect_and_cleans_its_partial_without_replacing_final(tmp_path) -> None:
    media_transport = _media_transport()
    target = tmp_path / "existing.mp4"
    target.write_bytes(b"old")
    def stream(**_kwargs):
        raise RuntimeError("redirect https://evil.example")

    with pytest.raises(media_transport.MediaTransferError) as error:
        media_transport.download_file_to_path(
            config=_local_config(), file_id="file-id", destination=target,
            get_file_json=_get_file(path="/var/lib/telegram-bot-api/123:token/videos/file.mp4"), stream_bytes=stream, max_attempts=1,
        )

    assert error.value.reason == "stream_failed"
    assert target.read_bytes() == b"old"
    assert not target.with_name("existing.mp4.partial").exists()


def test_download_checks_cancel_deadline_and_disk_before_next_chunk_and_cleans(tmp_path) -> None:
    media_transport = _media_transport()
    target = tmp_path / "guarded.mp4"

    for kwargs, reason in (
        ({"cancel_requested": lambda: True}, "cancelled"),
        ({"deadline_monotonic": 3, "monotonic": lambda: 3}, "deadline_exceeded"),
        ({"workspace_reserve_bytes": 10, "disk_usage": lambda _path: type("D", (), {"free": 9})()}, "insufficient_disk"),
    ):
        with pytest.raises(media_transport.MediaTransferError) as error:
            media_transport.download_file_to_path(
                config=_local_config(), file_id="file-id", destination=target,
                get_file_json=_get_file(path="/var/lib/telegram-bot-api/123:token/videos/file.mp4"), stream_bytes=_BoundedStream([b"one"]),
                max_attempts=1, **kwargs,
            )
        assert error.value.reason == reason
        assert not target.with_name("guarded.mp4.partial").exists()


@pytest.mark.parametrize(
    ("kind", "reason"),
    (
        ("cancel", "cancelled"),
        ("deadline", "deadline_exceeded"),
        ("disk", "insufficient_disk"),
    ),
)
def test_download_rechecks_guards_after_a_chunk_is_yielded_before_writing(tmp_path, kind, reason) -> None:
    media_transport = _media_transport()
    target = tmp_path / f"post-yield-{kind}.mp4"
    state = {"changed": False}
    progress = []

    def stream(**_kwargs):
        state["changed"] = True
        yield b"abc"

    kwargs = {
        "cancel_requested": lambda: state["changed"] if kind == "cancel" else False,
        "deadline_monotonic": 1 if kind == "deadline" else None,
        "monotonic": lambda: 1 if state["changed"] and kind == "deadline" else 0,
        "workspace_reserve_bytes": 8 if kind == "disk" else 0,
        "free_bytes": lambda _path: 10 if state["changed"] and kind == "disk" else 20,
    }

    with pytest.raises(media_transport.MediaTransferError) as error:
        media_transport.download_file_to_path(
            config=_local_config(),
            file_id="file-id",
            destination=target,
            get_file_json=_get_file(path="/var/lib/telegram-bot-api/123:token/videos/file.mp4"),
            stream_bytes=stream,
            progress_callback=lambda actual, declared: progress.append((actual, declared)),
            max_attempts=1,
            **kwargs,
        )

    assert error.value.reason == reason
    assert progress == []
    assert not target.exists()
    assert not target.with_name(f"post-yield-{kind}.mp4.partial").exists()


def test_download_checks_post_yield_chunk_disk_space_with_zero_reserve(tmp_path, monkeypatch) -> None:
    media_transport = _media_transport()
    target = tmp_path / "post-yield-zero-reserve.mp4"
    state = {"changed": False}
    writes = []
    progress = []
    real_fdopen = media_transport.os.fdopen

    class _TrackingOutput:
        def __init__(self, output) -> None:
            self._output = output

        def __enter__(self):
            self._output.__enter__()
            return self

        def __exit__(self, *args) -> None:
            return self._output.__exit__(*args)

        def write(self, chunk: bytes) -> int:
            writes.append(chunk)
            return self._output.write(chunk)

        def __getattr__(self, name):
            return getattr(self._output, name)

    def track_fdopen(*args, **kwargs):
        return _TrackingOutput(real_fdopen(*args, **kwargs))

    def stream(**_kwargs):
        state["changed"] = True
        yield b"abc"

    monkeypatch.setattr(media_transport.os, "fdopen", track_fdopen)

    with pytest.raises(media_transport.MediaTransferError) as error:
        media_transport.download_file_to_path(
            config=_local_config(),
            file_id="file-id",
            destination=target,
            get_file_json=_get_file(path="/var/lib/telegram-bot-api/123:token/videos/file.mp4"),
            stream_bytes=stream,
            workspace_reserve_bytes=0,
            free_bytes=lambda _path: 2 if state["changed"] else 20,
            progress_callback=lambda actual, declared: progress.append((actual, declared)),
            max_attempts=1,
        )

    assert error.value.reason == "insufficient_disk"
    assert writes == []
    assert progress == []
    assert not target.exists()
    assert not target.with_name("post-yield-zero-reserve.mp4.partial").exists()


def test_download_rejects_size_mismatch_and_hard_actual_overflow_without_final(tmp_path) -> None:
    media_transport = _media_transport()

    with pytest.raises(media_transport.MediaTransferError) as mismatch:
        media_transport.download_file_to_path(
            config=_local_config(), file_id="file-id", destination=tmp_path / "mismatch.mp4",
            get_file_json=_get_file(path="/var/lib/telegram-bot-api/123:token/videos/file.mp4", size=2), stream_bytes=_BoundedStream([b"three"]),
            max_attempts=1,
        )
    assert mismatch.value.reason == "size_mismatch"

    with pytest.raises(media_transport.MediaTransferError) as overflow:
        media_transport.download_file_to_path(
            config=_local_config(), file_id="file-id", destination=tmp_path / "overflow.mp4",
            get_file_json=_get_file(path="/var/lib/telegram-bot-api/123:token/videos/file.mp4"), stream_bytes=_BoundedStream([b"12", b"34"]),
            hard_max_bytes=3, max_attempts=1,
        )
    assert overflow.value.reason == "size_limit_exceeded"
    assert not (tmp_path / "mismatch.mp4").exists()
    assert not (tmp_path / "overflow.mp4").exists()


def test_download_rejects_expected_size_overflow_before_write_or_progress(tmp_path) -> None:
    media_transport = _media_transport()
    target = tmp_path / "expected-overflow.mp4"
    progress = []

    with pytest.raises(media_transport.MediaTransferError) as error:
        media_transport.download_file_to_path(
            config=_local_config(),
            file_id="file-id",
            destination=target,
            get_file_json=_get_file(path="/var/lib/telegram-bot-api/123:token/videos/file.mp4"),
            stream_bytes=_BoundedStream([b"four"]),
            expected_bytes=3,
            progress_callback=lambda actual, declared: progress.append((actual, declared)),
            max_attempts=1,
        )

    assert error.value.reason == "size_mismatch"
    assert progress == []
    assert not target.exists()
    assert not target.with_name("expected-overflow.mp4.partial").exists()


def test_download_does_not_retry_after_atomic_publish_fails(tmp_path, monkeypatch) -> None:
    media_transport = _media_transport()
    target = tmp_path / "publish-failed.mp4"
    target.write_bytes(b"old")
    get_file = _get_file(path="/var/lib/telegram-bot-api/123:token/videos/file.mp4", size=3)
    stream = _BoundedStream([b"new"])

    def fail_replace(_source, _destination, **_kwargs):
        raise OSError("simulated publish failure")

    if os.name == "nt":
        monkeypatch.setattr(media_transport, "_win_rename_handle", fail_replace)
    else:
        monkeypatch.setattr(media_transport.os, "replace", fail_replace)

    with pytest.raises(media_transport.MediaTransferError) as error:
        media_transport.download_file_to_path(
            config=_local_config(),
            file_id="file-id",
            destination=target,
            get_file_json=get_file,
            stream_bytes=stream,
            max_attempts=2,
        )

    assert error.value.reason == "publish_failed"
    assert get_file.calls and len(get_file.calls) == 1
    assert len(stream.requested) == 1
    assert target.read_bytes() == b"old"
    assert not target.with_name("publish-failed.mp4.partial").exists()


def test_download_never_uses_unbounded_reads_and_redacts_urls_tokens_and_secrets(tmp_path) -> None:
    media_transport = _media_transport()
    token = "123:private-token"
    secret = "private-secret"
    target = tmp_path / "redacted.mp4"

    with pytest.raises(media_transport.MediaTransferError) as error:
        media_transport.download_file_to_path(
            config=_local_config(token=token, proxy_secret=secret), file_id="file-id", destination=target,
            get_file_json=_get_file(path="/var/lib/telegram-bot-api/123:private-token/videos/file.mp4"),
            stream_bytes=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("https://tg.toanaas.vn/file/bot123:private-token bad private-secret")),
            max_attempts=1,
        )

    text = str(error.value)
    assert error.value.reason == "stream_failed"
    assert token not in text
    assert secret not in text
    assert "https://" not in text


def test_download_never_takes_over_a_preexisting_partial(tmp_path) -> None:
    media_transport = _media_transport()
    target = tmp_path / "owned.mp4"
    partial = target.with_name("owned.mp4.partial")
    partial.write_bytes(b"another transfer")

    with pytest.raises(media_transport.MediaTransferError) as error:
        media_transport.download_file_to_path(
            config=_local_config(), file_id="file-id", destination=target,
            open_json=_get_file(path="/var/lib/telegram-bot-api/123:token/videos/file.mp4"),
            open_stream=_BoundedStream([b"new"]), expected_size=3, max_attempts=1,
        )

    assert error.value.reason == "invalid_destination"
    assert partial.read_bytes() == b"another transfer"
    assert not target.exists()


@pytest.mark.skipif(os.name == "nt", reason="Windows holds an undeletable parent lease")
def test_download_parent_swap_fails_closed_and_preserves_both_final_files(
    tmp_path, monkeypatch
) -> None:
    media_transport = _media_transport()
    workspace = tmp_path / "workspace"
    captured = tmp_path / "captured-workspace"
    attacker = tmp_path / "attacker-workspace"
    workspace.mkdir()
    attacker.mkdir()
    target = workspace / "clip.mp4"
    target.write_bytes(b"original")
    (attacker / "clip.mp4").write_bytes(b"attacker")
    real_open = media_transport.os.open
    swapped = False

    def swap_parent_before_partial_open(path, flags, mode=0o777, **kwargs):
        nonlocal swapped
        if not swapped and os.fspath(path).endswith("clip.mp4.partial"):
            swapped = True
            workspace.rename(captured)
            attacker.rename(workspace)
        return real_open(path, flags, mode, **kwargs)

    monkeypatch.setattr(media_transport.os, "open", swap_parent_before_partial_open)

    with pytest.raises(media_transport.MediaTransferError) as error:
        media_transport.download_file_to_path(
            config=_local_config(),
            file_id="file-id",
            destination=target,
            get_file_json=_get_file(
                path="/var/lib/telegram-bot-api/123:token/videos/file.mp4",
                size=3,
            ),
            stream_bytes=_BoundedStream([b"new"]),
            max_attempts=1,
        )

    assert swapped is True
    assert error.value.reason == "invalid_destination"
    assert (captured / "clip.mp4").read_bytes() == b"original"
    assert (workspace / "clip.mp4").read_bytes() == b"attacker"


@pytest.mark.skipif(os.name != "nt", reason="requires Win32 delete-sharing semantics")
def test_download_windows_parent_lease_blocks_swap_before_partial_creation(
    tmp_path,
) -> None:
    media_transport = _media_transport()
    workspace = tmp_path / "workspace"
    captured = tmp_path / "captured-workspace"
    attacker = tmp_path / "attacker-workspace"
    workspace.mkdir()
    attacker.mkdir()
    target = workspace / "clip.mp4"
    target.write_bytes(b"original")
    (attacker / "clip.mp4").write_bytes(b"attacker")
    rename_blocked = False

    def get_file_after_validation(**_kwargs):
        nonlocal rename_blocked
        try:
            workspace.rename(captured)
        except OSError:
            rename_blocked = True
        else:
            attacker.rename(workspace)
        return {
            "ok": True,
            "result": {
                "file_path": "/var/lib/telegram-bot-api/123:token/videos/file.mp4",
                "file_size": 3,
            },
        }

    receipt = media_transport.download_file_to_path(
        config=_local_config(),
        file_id="file-id",
        destination=target,
        get_file_json=get_file_after_validation,
        stream_bytes=_BoundedStream([b"new"]),
        max_attempts=1,
    )

    assert rename_blocked is True
    assert receipt.actual_bytes == 3
    assert target.read_bytes() == b"new"
    assert (attacker / "clip.mp4").read_bytes() == b"attacker"
    assert not captured.exists()


@pytest.mark.skipif(os.name != "nt", reason="requires Win32 handle-based publication")
def test_download_windows_never_publishes_or_deletes_swapped_partial(
    tmp_path, monkeypatch
) -> None:
    media_transport = _media_transport()
    target = tmp_path / "exact-partial.mp4"
    partial = target.with_name("exact-partial.mp4.partial")
    stolen = target.with_name("trusted-partial-stolen.mp4")
    attacker_bytes = b"attacker replacement"
    real_replace = media_transport.os.replace
    path_replace_attempted = False

    def swap_partial_in_path_replace(source, destination, **kwargs):
        nonlocal path_replace_attempted
        path_replace_attempted = True
        partial.rename(stolen)
        partial.write_bytes(attacker_bytes)
        return real_replace(source, destination, **kwargs)

    monkeypatch.setattr(media_transport.os, "replace", swap_partial_in_path_replace)

    try:
        receipt = media_transport.download_file_to_path(
            config=_local_config(),
            file_id="file-id",
            destination=target,
            get_file_json=_get_file(
                path="/var/lib/telegram-bot-api/123:token/videos/file.mp4",
                size=7,
            ),
            stream_bytes=_BoundedStream([b"trusted"]),
            max_attempts=1,
        )
    except media_transport.MediaTransferError as error:
        assert error.reason == "invalid_destination"
        assert not target.exists()
        assert partial.read_bytes() == attacker_bytes
        assert stolen.read_bytes() == b"trusted"
    else:
        assert receipt.actual_bytes == 7
        assert target.read_bytes() == b"trusted"
        assert path_replace_attempted is False
        assert not partial.exists()
        assert not stolen.exists()


class _ClosableStream:
    def __init__(self, chunks) -> None:
        self._chunks = iter(chunks)
        self.close_calls = 0

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._chunks)

    def close(self) -> None:
        self.close_calls += 1


@pytest.mark.parametrize("outcome", ("success", "cancel", "failure"))
def test_download_closes_stream_exactly_once_for_every_outcome(tmp_path, outcome) -> None:
    media_transport = _media_transport()
    stream = _ClosableStream([b"ok"] if outcome != "failure" else [b"too large"])
    kwargs = {}
    if outcome == "cancel":
        kwargs["cancel_requested"] = lambda: True
    if outcome == "failure":
        kwargs["hard_max_bytes"] = 2

    if outcome == "success":
        media_transport.download_file_to_path(
            config=_local_config(),
            file_id="file-id",
            destination=tmp_path / "closed.mp4",
            get_file_json=_get_file(
                path="/var/lib/telegram-bot-api/123:token/videos/file.mp4", size=2
            ),
            stream_bytes=lambda **_kwargs: stream,
            max_attempts=1,
        )
    else:
        with pytest.raises(media_transport.MediaTransferError):
            media_transport.download_file_to_path(
                config=_local_config(),
                file_id="file-id",
                destination=tmp_path / f"closed-{outcome}.mp4",
                get_file_json=_get_file(
                    path="/var/lib/telegram-bot-api/123:token/videos/file.mp4"
                ),
                stream_bytes=lambda **_kwargs: stream,
                max_attempts=1,
                **kwargs,
            )

    assert stream.close_calls == 1


def test_download_retries_transient_precompletion_failures_with_bounded_backoff(
    tmp_path,
) -> None:
    media_transport = _media_transport()
    attempts = []
    delays = []

    def stream(**_kwargs):
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            return iter(_RaisesOnNext(RuntimeError("secret https://evil.example")))
        return iter([b"ok"])

    receipt = media_transport.download_file_to_path(
        config=_local_config(),
        file_id="file-id",
        destination=tmp_path / "retry.mp4",
        get_file_json=_get_file(
            path="/var/lib/telegram-bot-api/123:token/videos/file.mp4", size=2
        ),
        stream_bytes=stream,
        max_attempts=3,
        retry_backoff=lambda attempt: 0.25 * attempt,
        max_retry_delay_seconds=0.4,
        sleep=delays.append,
    )

    assert receipt.actual_bytes == 2
    assert attempts == [1, 2, 3]
    assert delays == [0.25, 0.4]
    assert all(0 < delay <= 0.4 for delay in delays)


class _RaisesOnNext:
    def __init__(self, error) -> None:
        self.error = error

    def __iter__(self):
        return self

    def __next__(self):
        raise self.error


def test_download_stops_at_max_attempts_and_redacts_transient_failure(tmp_path) -> None:
    media_transport = _media_transport()
    attempts = []
    delays = []
    token = "123:private-token"

    def stream(**_kwargs):
        attempts.append(1)
        return _RaisesOnNext(RuntimeError(f"https://evil.example/{token}"))

    with pytest.raises(media_transport.MediaTransferError) as error:
        media_transport.download_file_to_path(
            config=_local_config(token=token),
            file_id="file-id",
            destination=tmp_path / "retry-exhausted.mp4",
            get_file_json=_get_file(
                path="/var/lib/telegram-bot-api/123:private-token/videos/file.mp4"
            ),
            stream_bytes=stream,
            max_attempts=3,
            retry_backoff=lambda _attempt: 0.01,
            sleep=delays.append,
        )

    assert error.value.reason == "stream_failed"
    assert token not in str(error.value)
    assert "https://" not in str(error.value)
    assert len(attempts) == 3
    assert delays == [0.01, 0.01]


@pytest.mark.parametrize(
    ("overrides", "reason"),
    (
        ({"max_attempts": 0}, "invalid_max_attempts"),
        ({"max_attempts": True}, "invalid_max_attempts"),
        ({"retry_backoff": None}, "invalid_retry_policy"),
        ({"max_retry_delay_seconds": 0}, "invalid_retry_policy"),
        ({"sleep": None}, "invalid_retry_policy"),
    ),
)
def test_download_rejects_invalid_retry_policy_before_transport(
    tmp_path, overrides, reason
) -> None:
    media_transport = _media_transport()
    get_file = _get_file(
        path="/var/lib/telegram-bot-api/123:token/videos/file.mp4"
    )

    with pytest.raises(media_transport.MediaTransferError) as error:
        media_transport.download_file_to_path(
            config=_local_config(),
            file_id="file-id",
            destination=tmp_path / "invalid-retry.mp4",
            get_file_json=get_file,
            stream_bytes=_BoundedStream([b"ok"]),
            **overrides,
        )

    assert error.value.reason == reason
    assert get_file.calls == []


@pytest.mark.parametrize("failure", ("cancelled", "complete", "classified"))
def test_download_never_retries_nontransient_failures(tmp_path, failure) -> None:
    media_transport = _media_transport()
    attempts = []
    delays = []

    def stream(**_kwargs):
        attempts.append(1)
        if failure == "classified":
            return iter(["not bytes"])
        return iter([b"x"])

    kwargs = {}
    if failure == "cancelled":
        kwargs["cancel_requested"] = lambda: True
    elif failure == "complete":
        kwargs["expected_bytes"] = 2

    with pytest.raises(media_transport.MediaTransferError):
        media_transport.download_file_to_path(
            config=_local_config(),
            file_id="file-id",
            destination=tmp_path / f"no-retry-{failure}.mp4",
            get_file_json=_get_file(
                path="/var/lib/telegram-bot-api/123:token/videos/file.mp4"
            ),
            stream_bytes=stream,
            max_attempts=3,
            retry_backoff=lambda _attempt: 0.01,
            sleep=delays.append,
            **kwargs,
        )

    assert len(attempts) == 1
    assert delays == []
