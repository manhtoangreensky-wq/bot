from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping


SubDubRunner = Callable[..., Awaitable[dict[str, Any]]]


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


def normalize_video_lane_state(mode: str, state: Mapping[str, Any]) -> dict[str, Any]:
    """Keep video-only outputs on their MP4 contract without changing file/audio flows."""
    if not _video_source(state):
        return state if isinstance(state, dict) else dict(state or {})
    current = dict(state or {})
    if mode in {"subtitle_create", "subtitle_translate"}:
        output = str(current.get("output_type") or "").strip().lower()
        if output not in {"burn", "both", "video_subtitle"}:
            current["output_type"] = "burn"
            current["output_format"] = "burn"
    elif mode == "subtitle_plus_dub":
        current["output_type"] = "video_subtitle"
        current["output_format"] = "video_subtitle"
    else:
        return state if isinstance(state, dict) else current
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
