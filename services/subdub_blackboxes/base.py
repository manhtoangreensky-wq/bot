from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping


SubDubRunner = Callable[..., Awaitable[dict[str, Any]]]


_COMBO_MODE = "subtitle_plus_dub"
_VIDEO_LANE_PROFILES = {
    "subtitle_create": {
        "active_flow": "auto_subtitle",
        "product": "auto_subtitle",
        "product_type": "subtitle_only",
        "output_type": "burn",
    },
    "subtitle_translate": {
        "active_flow": "subtitle_translate",
        "product": "subtitle_translation",
        "product_type": "subtitle_only",
        "output_type": "burn",
    },
    "dub": {
        "active_flow": "dub_audio",
        "product": "auto_dubbing",
        "product_type": "dub_only",
        "output_type": "video",
    },
}


def _video_source(state: Mapping[str, Any]) -> bool:
    content_type = str(
        state.get("source_mime_type")
        or state.get("source_content_type")
        or state.get("content_type")
        or ""
    ).strip().lower()
    media_kind = str(
        state.get("source_media_type") or state.get("media_kind") or ""
    ).strip().lower()
    return bool(
        content_type.startswith("video/")
        or media_kind == "video"
        or state.get("video_file_id")
    )


def normalize_standalone_video_lane_entry_state(
    state: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Clear stale cross-lane keys without changing a real combo session."""
    current = state if isinstance(state, dict) else dict(state or {})
    if not _video_source(current):
        return current

    active_flow = str(current.get("active_flow") or "").strip().lower()
    if active_flow == _COMBO_MODE:
        return current

    mode = str(
        current.get("video_processing_mode")
        or current.get("mode")
        or current.get("process_type")
        or ""
    ).strip()
    profile = _VIDEO_LANE_PROFILES.get(mode)
    if not profile:
        return current

    canonical_fields = {
        "mode": mode,
        "process_type": mode,
        "video_processing_mode": mode,
        "requested_mode": mode,
        "active_flow": str(profile["active_flow"]),
        "product": str(profile["product"]),
        "product_type": str(profile["product_type"]),
        "output_type": str(profile["output_type"]),
        "output_format": str(profile["output_type"]),
    }
    normalized = dict(current)
    changed = False
    for key, canonical_value in canonical_fields.items():
        existing = normalized.get(key)
        if existing is None or str(existing).strip() == "":
            normalized[key] = canonical_value
            changed = True
            continue
        if str(existing).strip().lower() == canonical_value.lower():
            continue
        normalized[key] = canonical_value
        changed = True
    if not changed:
        return current
    normalized["_subdub_standalone_lane_normalized"] = True
    return normalized


def normalize_video_lane_state(mode: str, state: Mapping[str, Any]) -> dict[str, Any]:
    """Keep video-only outputs on their MP4 contract without changing file/audio flows."""
    normalized = normalize_standalone_video_lane_entry_state(state)
    if not _video_source(normalized):
        return normalized
    current = dict(normalized)
    if mode in {"subtitle_create", "subtitle_translate"}:
        output = str(current.get("output_type") or "").strip().lower()
        if output not in {"burn", "both", "video_subtitle"}:
            current["output_type"] = "burn"
            current["output_format"] = "burn"
    elif mode == "subtitle_plus_dub":
        current["output_type"] = "video_subtitle"
        current["output_format"] = "video_subtitle"
    else:
        return current
    current["_subdub_delivery_active_flow"] = "subdub_video"
    current["_subdub_lane_video_output_locked"] = True
    return current


@dataclass(frozen=True)
class SubDubLaneContract:
    name: str
    modes: frozenset[str]

    async def run(
        self,
        *,
        runner: SubDubRunner,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        runner_payload = dict(payload)
        mode = str(runner_payload.get("mode") or "").strip()
        if mode not in self.modes:
            raise ValueError(f"mode_not_owned_by_{self.name}")
        lane_state = normalize_video_lane_state(
            mode,
            runner_payload.get("state") or {},
        )
        runner_payload["state"] = lane_state
        result = await runner(**runner_payload)
        if lane_state.get("_subdub_delivery_active_flow") and isinstance(result, dict):
            result = dict(result)
            result.setdefault(
                "_subdub_delivery_active_flow",
                lane_state["_subdub_delivery_active_flow"],
            )
        return result
