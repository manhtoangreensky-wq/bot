"""Suno music provider adapter contract.

Suno remains admin-smoke/public-gated. Do not fake audio output.
"""

from __future__ import annotations

from media_provider_router import guarded_readiness


def readiness() -> dict:
    return guarded_readiness("suno_music", "key4u_suno", "requires_endpoint_model_and_smoke")
