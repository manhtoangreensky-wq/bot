from __future__ import annotations

from typing import Any

from . import dub_only, subtitle_dub, subtitle_only
from .base import SubDubRunner


_LANES = (subtitle_only.LANE, dub_only.LANE, subtitle_dub.LANE)
_RUNNERS = {
    subtitle_only.LANE.name: subtitle_only.run,
    dub_only.LANE.name: dub_only.run,
    subtitle_dub.LANE.name: subtitle_dub.run,
}


def subdub_lane_name(mode: str) -> str:
    normalized = str(mode or "").strip()
    for lane in _LANES:
        if normalized in lane.modes:
            return lane.name
    return ""


async def run_subdub_lane_blackbox(
    *,
    lane_mode: str,
    runner: SubDubRunner,
    **payload: Any,
) -> dict[str, Any]:
    normalized_mode = str(lane_mode or "").strip()
    lane_name = subdub_lane_name(normalized_mode)
    lane_runner = _RUNNERS.get(lane_name)
    if lane_runner is None:
        raise ValueError("unsupported_subdub_lane_mode")
    if str(payload.get("mode") or "").strip() != normalized_mode:
        raise ValueError("subdub_lane_payload_mode_mismatch")
    return await lane_runner(runner, payload)
