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
    combo_subpath = _token(normalized.get("combo_subpath"))
    if combo_subpath == "direct_dub":
        combo_subpath = "create_then_dub"
    normalized.update(
        {
            "mode": COMBO_MODE,
            "process_type": COMBO_MODE,
            "video_processing_mode": COMBO_MODE,
            "requested_mode": COMBO_MODE,
            "active_flow": COMBO_FLOW,
            "product_type": "subtitle_dub",
            "translate_requested": "1",
            "dub_text_source": "translated",
            "dub_source": "translated_subtitle",
            "output_type": "video_subtitle",
            "output_format": "video_subtitle",
            "_subdub_combo_blackbox_active": True,
        }
    )
    if combo_subpath:
        normalized["combo_subpath"] = combo_subpath
    return normalized
