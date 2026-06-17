"""Subtitle/dubbing pipeline adapter contract.

Pipeline order: upload media -> ASR -> optional translate -> TTS -> worker mux
or separate output. Public modes require provider readiness and smoke PASS.
"""

from __future__ import annotations

from media_provider_router import guarded_readiness


def readiness() -> dict:
    return guarded_readiness("subtitle_dub_pipeline", "deepgram+tts+worker", "requires_pipeline_smoke")
