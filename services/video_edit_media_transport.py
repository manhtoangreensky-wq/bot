"""Pure transport-lane policy for Video Edit media."""

from __future__ import annotations


SHORT_MEDIA_MAX_SECONDS = 60.0
SHORT_MEDIA_MAX_BYTES = 20 * 1024 * 1024


def select_media_lane(*, duration_seconds: float, size_bytes: int) -> str:
    duration = max(0.0, float(duration_seconds or 0.0))
    size = max(0, int(size_bytes or 0))
    if duration and size and duration <= SHORT_MEDIA_MAX_SECONDS and size <= SHORT_MEDIA_MAX_BYTES:
        return "short_media"
    return "large_media"
