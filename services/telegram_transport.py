"""Shared transport policy for credential-bearing Telegram API requests.

The Bot API puts the bot token in the URL path.  A non-loopback HTTP origin
would therefore expose credentials before any reverse-proxy authentication can
help.  Keep the policy in a small dependency-free module so every request
construction path can enforce the same invariant.
"""

from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import urlsplit


_ALLOWED_SCHEMES = frozenset({"http", "https"})
_LOOPBACK_NAMES = frozenset({"localhost"})


def _is_loopback_host(hostname: str) -> bool:
    host = str(hostname or "").strip().lower().rstrip(".")
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _parse_and_validate(url: str, *, add_default_scheme: bool) -> str:
    value = str(url or "").strip().rstrip("/")
    if not value:
        return ""
    if add_default_scheme and "://" not in value:
        value = "https://" + value
    try:
        parsed = urlsplit(value)
        # Accessing .port validates malformed port syntax as well.
        _ = parsed.port
        hostname = parsed.hostname
    except ValueError as exc:
        raise ValueError("invalid Telegram API base URL") from exc

    if parsed.scheme not in _ALLOWED_SCHEMES or not hostname:
        raise ValueError("invalid Telegram API base URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
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
