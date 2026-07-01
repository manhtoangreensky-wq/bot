"""Kling-compatible video provider adapter.

Disabled unless explicit backend API configuration is present. No browser
automation, scraping, cookies, or user sessions are used.
"""

from __future__ import annotations

from providers.video_generic_http_provider import GenericHttpVideoProvider


class KlingVideoProvider(GenericHttpVideoProvider):
    provider_name = "kling"

    def __init__(self, environ=None):
        super().__init__(
            provider_name="kling",
            enabled_env="VIDEO_KLING_ENABLED",
            submit_url_env="VIDEO_KLING_ENDPOINT",
            poll_url_env="VIDEO_KLING_POLL_ENDPOINT",
            auth_header_name_env="VIDEO_KLING_AUTH_HEADER_NAME",
            auth_header_value_env="VIDEO_KLING_API_KEY",
            result_field_env="VIDEO_KLING_RESULT_FIELD",
            model_env="VIDEO_KLING_MODEL",
            capabilities_env="VIDEO_KLING_CAPABILITIES",
            environ=environ,
        )

    def _auth_header(self) -> tuple[str, str]:
        name = str(self.env.get("VIDEO_KLING_AUTH_HEADER_NAME") or "Authorization").strip()
        value = str(self.env.get("VIDEO_KLING_AUTH_HEADER_VALUE") or "").strip()
        api_key = str(self.env.get("VIDEO_KLING_API_KEY") or "").strip()
        if not value and api_key:
            value = api_key if api_key.lower().startswith(("bearer ", "apikey ", "key ")) else f"Bearer {api_key}"
        return name, value
