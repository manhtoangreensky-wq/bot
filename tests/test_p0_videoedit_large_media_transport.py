from __future__ import annotations

import importlib

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
