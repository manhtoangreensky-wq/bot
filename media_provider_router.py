"""Media AI provider readiness contracts for TOAN AAS.

This module intentionally does not call providers. Runtime wiring remains in
bot.py until each provider has verified docs, smoke tests, pricing and gates.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class MediaProviderReadiness:
    name: str
    ready: bool
    provider: str
    model: str = "auto/NEED_DOCS"
    endpoint_configured: bool = False
    api_key_configured: bool = False
    public_enabled: bool = False
    admin_smoke_status: str = "NOT_TESTED"
    reason: str = "not_ready"
    safe_user_message: str = "Provider is under validation. No API call and no Xu charge."

    def to_dict(self) -> dict:
        return asdict(self)


def guarded_readiness(name: str, provider: str, reason: str = "NEED_DOCS") -> dict:
    return MediaProviderReadiness(
        name=name,
        ready=False,
        provider=provider,
        reason=reason,
    ).to_dict()
