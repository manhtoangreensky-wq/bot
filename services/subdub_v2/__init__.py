"""Disabled, offline-only SubDub Pipeline V2 shadow/replay package.

The package intentionally contains no Telegram, provider, worker, payment or
database imports.  Importing it only defines pure contracts and helpers.
Production V1 remains the selected path unless an explicitly isolated replay
caller opts in.
"""

from .config import V2Flags, V2ResourceLimits
from .contracts import AcceptanceState, StageState, ValidationResult, validate_artifact

__all__ = [
    "AcceptanceState",
    "StageState",
    "V2Flags",
    "V2ResourceLimits",
    "ValidationResult",
    "validate_artifact",
]
