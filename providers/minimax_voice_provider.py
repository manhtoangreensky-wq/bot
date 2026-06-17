"""MiniMax voice provider adapter contract.

Voice clone/profile flows require explicit consent and user-scoped profiles.
"""

from __future__ import annotations

from media_provider_router import guarded_readiness


def readiness() -> dict:
    return guarded_readiness("minimax_voice", "minimax", "requires_verified_tts_endpoint_and_consent")
