"""Google Veo-compatible video provider adapter.

This adapter is config-only by default. It supports an admin-provided official
Gemini/Vertex/custom endpoint shape through the generic HTTP provider contract.
"""

from __future__ import annotations

from providers.video_generic_http_provider import GenericHttpVideoProvider


class VeoVideoProvider(GenericHttpVideoProvider):
    provider_name = "veo"

    def __init__(self, environ=None):
        super().__init__(
            provider_name="veo",
            enabled_env="VIDEO_VEO_ENABLED",
            submit_url_env="VIDEO_VEO_ENDPOINT",
            poll_url_env="VIDEO_VEO_POLL_ENDPOINT",
            auth_header_name_env="VIDEO_VEO_AUTH_HEADER_NAME",
            auth_header_value_env="VIDEO_VEO_API_KEY",
            result_field_env="VIDEO_VEO_RESULT_FIELD",
            model_env="VIDEO_VEO_MODEL",
            capabilities_env="VIDEO_VEO_CAPABILITIES",
            environ=environ,
        )

    def _auth_header(self) -> tuple[str, str]:
        name = str(self.env.get("VIDEO_VEO_AUTH_HEADER_NAME") or "Authorization").strip()
        value = str(self.env.get("VIDEO_VEO_AUTH_HEADER_VALUE") or "").strip()
        api_key = str(self.env.get("VIDEO_VEO_API_KEY") or "").strip()
        if not value and api_key:
            value = api_key if api_key.lower().startswith(("bearer ", "apikey ", "key ")) else f"Bearer {api_key}"
        return name, value
