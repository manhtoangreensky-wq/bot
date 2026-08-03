"""Shared transport policy for credential-bearing Telegram API requests.

The Bot API puts the bot token in the URL path.  A non-loopback HTTP origin
would therefore expose credentials before any reverse-proxy authentication can
help.  Keep the policy in a small dependency-free module so every request
construction path can enforce the same invariant.
"""

from __future__ import annotations

from ipaddress import ip_address
import re
from urllib.parse import urlsplit


_ALLOWED_SCHEMES = frozenset({"http", "https"})
_LOOPBACK_NAMES = frozenset({"localhost"})
_CLOUD_API_ROOT = "https://api.telegram.org"
_BOT_METHOD = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_BOT_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_-]{0,255}$")
_SAFE_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9._~:-]+$")


def _is_loopback_host(hostname: str) -> bool:
    host = str(hostname or "").strip().lower().rstrip(".")
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _contains_control(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _parse_and_validate(url: str, *, add_default_scheme: bool) -> str:
    raw = str(url or "")
    if _contains_control(raw):
        raise ValueError("invalid Telegram API base URL")
    value = raw.strip().rstrip("/")
    if not value:
        return ""
    if add_default_scheme and "://" not in value:
        value = "https://" + value
    if (
        "\\" in value
        or "%" in value
        or "?" in value
        or "#" in value
        or any(char.isspace() for char in value)
    ):
        raise ValueError("invalid Telegram API base URL")
    try:
        parsed = urlsplit(value)
        # Accessing .port validates malformed port syntax as well.
        port = parsed.port
        hostname = parsed.hostname
    except ValueError:
        raise ValueError("invalid Telegram API base URL") from None

    if parsed.scheme not in _ALLOWED_SCHEMES or not hostname:
        raise ValueError("invalid Telegram API base URL")
    authority = parsed.netloc.rsplit("@", 1)[-1]
    if authority.endswith(":") or port == 0:
        raise ValueError("invalid Telegram API base URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("invalid Telegram API base URL")
    path_parts = parsed.path.split("/")
    if "//" in parsed.path or any(part in {".", ".."} for part in path_parts):
        raise ValueError("invalid Telegram API base URL")
    if parsed.scheme == "http" and not _is_loopback_host(hostname):
        raise ValueError("remote Telegram API base requires HTTPS")
    return value


def normalize_api_root(value: str = "") -> str:
    """Normalize a Bot API root and fail closed on unsafe origins."""

    root = str(value or "").strip().rstrip("/")
    if not root:
        return ""
    for suffix in ("/file/bot", "/bot"):
        if root.endswith(suffix):
            root = root[: -len(suffix)].rstrip("/")
            break
    if not root:
        return ""
    return _parse_and_validate(root, add_default_scheme=True).rstrip("/")


def validate_api_url(url: str = "") -> str:
    """Validate a final request URL before credentials reach an HTTP client."""

    return _parse_and_validate(url, add_default_scheme=False)


def is_cloud_api_url(url: str = "") -> bool:
    """Recognize the exact Telegram Cloud API host, avoiding lookalikes."""

    try:
        parsed = urlsplit(str(url or "").strip())
        return parsed.scheme == "https" and (parsed.hostname or "").lower().rstrip(".") == "api.telegram.org"
    except ValueError:
        return False


def validate_bot_token(token: str) -> str:
    """Return an opaque token only when it is one safe URL-path segment."""

    if not isinstance(token, str) or not _BOT_TOKEN.fullmatch(token):
        raise ValueError("invalid Telegram API request")
    return token


def _validate_path(
    value: str,
    *,
    absolute: bool,
    error_message: str,
) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError(error_message)
    if _contains_control(value) or "\\" in value or "%" in value:
        raise ValueError(error_message)
    if "?" in value or "#" in value:
        raise ValueError(error_message)
    if absolute:
        if not value.startswith("/") or value.startswith("//") or value.endswith("/"):
            raise ValueError(error_message)
        body = value[1:]
    else:
        if value.startswith("/") or value.endswith("/"):
            raise ValueError(error_message)
        body = value
    parts = tuple(body.split("/"))
    if not parts or any(
        not part
        or part in {".", ".."}
        or len(part) > 255
        or not _SAFE_PATH_SEGMENT.fullmatch(part)
        for part in parts
    ):
        raise ValueError(error_message)
    return parts


def validate_local_file_root(file_root: str) -> str:
    """Validate a canonical absolute Local Bot API storage root."""

    _validate_path(
        file_root,
        absolute=True,
        error_message="invalid Telegram local media path",
    )
    return file_root


def validate_local_media_path(media_path: str) -> str:
    """Validate a canonical reverse-proxy path such as ``/localfile``."""

    _validate_path(
        media_path,
        absolute=True,
        error_message="invalid Telegram local media path",
    )
    return media_path


def bot_method_url(*, api_root: str, token: str, method: str) -> str:
    """Build a validated Telegram Bot API method URL without performing I/O."""

    root = normalize_api_root(api_root) or _CLOUD_API_ROOT
    safe_token = validate_bot_token(token)
    if not isinstance(method, str) or not _BOT_METHOD.fullmatch(method):
        raise ValueError("invalid Telegram API request")
    return validate_api_url(f"{root}/bot{safe_token}/{method}")


def bot_file_url(*, api_root: str, token: str, file_path: str) -> str:
    """Build the standard Bot API file URL used by Cloud/rollback lanes."""

    root = normalize_api_root(api_root) or _CLOUD_API_ROOT
    safe_token = validate_bot_token(token)
    parts = _validate_path(
        file_path,
        absolute=False,
        error_message="invalid Telegram file path",
    )
    return validate_api_url(f"{root}/file/bot{safe_token}/{'/'.join(parts)}")


def local_media_url(
    *,
    api_root: str,
    token: str,
    absolute_file_path: str,
    file_root: str,
    media_path: str,
) -> str:
    """Map one current-token Local Bot API path to its proxy media URL."""

    root = normalize_api_root(api_root)
    if not root or is_cloud_api_url(root):
        raise ValueError("invalid Telegram local media path")
    safe_token = validate_bot_token(token)
    root_parts = _validate_path(
        validate_local_file_root(file_root),
        absolute=True,
        error_message="invalid Telegram local media path",
    )
    absolute_parts = _validate_path(
        absolute_file_path,
        absolute=True,
        error_message="invalid Telegram local media path",
    )
    proxy_path = validate_local_media_path(media_path)
    root_count = len(root_parts)
    if absolute_parts[:root_count] != root_parts:
        raise ValueError("invalid Telegram local media path")
    relative_parts = absolute_parts[root_count:]
    if len(relative_parts) < 2 or relative_parts[0] != safe_token:
        raise ValueError("invalid Telegram local media path")
    return validate_api_url(f"{root}{proxy_path}/{'/'.join(relative_parts)}")
