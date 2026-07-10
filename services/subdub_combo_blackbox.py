from __future__ import annotations

from typing import Any


COMBO_MODE = "subtitle_plus_dub"
COMBO_FLOW = "subtitle_plus_dub"
COMBO_MODE_ALIASES = {
    COMBO_MODE,
    "subtitle_dub",
    "subtitle+dub",
    "subtitledub",
    "subtitle_dub_video",
    "subtitle_plus_dub_video",
    "translate_dub",
    "full_video",
}


def _token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def is_combo_state(state: dict | None) -> bool:
    current = state or {}
    mode_tokens = {
        _token(current.get("requested_mode")),
        _token(current.get("video_processing_mode")),
        _token(current.get("process_type")),
        _token(current.get("mode")),
    }
    return bool(
        COMBO_MODE_ALIASES.intersection(mode_tokens)
        or _token(current.get("active_flow")) == COMBO_FLOW
        or _token(current.get("product_type")) == "subtitle_dub"
    )


def normalize_combo_state(state: dict | None) -> dict:
    """Repair only stale combo mode keys before the existing combo MP4 callback."""
    current = state if isinstance(state, dict) else {}
    if not is_combo_state(current):
        return current
    normalized = dict(current)
    normalized.update(
        {
            "mode": COMBO_MODE,
            "process_type": COMBO_MODE,
            "video_processing_mode": COMBO_MODE,
            "requested_mode": COMBO_MODE,
            "active_flow": COMBO_FLOW,
            "product_type": "subtitle_dub",
            "_subdub_combo_blackbox_active": True,
        }
    )
    return normalized
