"""Pure transport-lane policy for Video Edit media."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from urllib.parse import urlsplit

from services import telegram_transport


SHORT_MEDIA_MAX_SECONDS = 60.0
SHORT_MEDIA_MAX_BYTES = 20 * 1024 * 1024
_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


def _effective_origin(url: str) -> tuple[str, str, int]:
    validated = telegram_transport.validate_api_url(url)
    if not validated:
        raise ValueError("invalid Telegram media request URL")
    parsed = urlsplit(validated)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if not hostname:
        raise ValueError("invalid Telegram media request URL")
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return parsed.scheme.lower(), hostname, port


@dataclass(frozen=True)
class TelegramMediaConfig:
    """Validated, I/O-free configuration for credential-bearing media calls."""

    token: str = field(repr=False)
    api_root: str
    proxy_secret_header: str
    proxy_secret: str = field(repr=False)
    local_file_root: str
    local_media_path: str
    follow_redirects: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        telegram_transport.bot_method_url(
            api_root=self.api_root,
            token=self.token,
            method="getFile",
        )
        telegram_transport.validate_local_file_root(self.local_file_root)
        telegram_transport.validate_local_media_path(self.local_media_path)
        if (
            not isinstance(self.proxy_secret_header, str)
            or not _HEADER_NAME.fullmatch(self.proxy_secret_header)
        ):
            raise ValueError("invalid Telegram proxy secret header")
        if not isinstance(self.proxy_secret, str):
            raise ValueError("invalid Telegram proxy secret")
        if any(ord(char) < 32 or ord(char) == 127 for char in self.proxy_secret):
            raise ValueError("invalid Telegram proxy secret")
        if self.proxy_secret != self.proxy_secret.strip():
            raise ValueError("invalid Telegram proxy secret")

    @property
    def is_local(self) -> bool:
        root = telegram_transport.normalize_api_root(self.api_root)
        return bool(root and not telegram_transport.is_cloud_api_url(root))

    def request_headers(self, *, request_url: str) -> dict[str, str]:
        request_origin = _effective_origin(request_url)
        if not self.is_local or not self.proxy_secret:
            return {}
        configured_root = telegram_transport.normalize_api_root(self.api_root)
        if request_origin != _effective_origin(configured_root):
            return {}
        return {self.proxy_secret_header: self.proxy_secret}


def select_media_lane(*, duration_seconds: float, size_bytes: int) -> str:
    duration = max(0.0, float(duration_seconds or 0.0))
    size = max(0, int(size_bytes or 0))
    if duration and size and duration <= SHORT_MEDIA_MAX_SECONDS and size <= SHORT_MEDIA_MAX_BYTES:
        return "short_media"
    return "large_media"
