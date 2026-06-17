"""Image edit provider adapter contract.

No provider call is performed here. The production bot must only route to a
real implementation after readiness, admin smoke, pricing and public gates pass.
"""

from __future__ import annotations

from media_provider_router import guarded_readiness


def readiness() -> dict:
    return guarded_readiness("image_edit", "router", "runtime_readiness_lives_in_bot")
