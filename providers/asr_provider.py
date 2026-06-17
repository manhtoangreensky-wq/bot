"""ASR provider adapter contract for subtitle/dub flows."""

from __future__ import annotations

from media_provider_router import guarded_readiness


def readiness() -> dict:
    return guarded_readiness("asr", "deepgram", "runtime_readiness_lives_in_bot")
