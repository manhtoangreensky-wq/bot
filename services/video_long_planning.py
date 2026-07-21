"""Internal-only contract for the unavailable long-form Video product."""

from __future__ import annotations

from copy import deepcopy


PUBLIC_ENABLED = False
SCENE_DURATION_SECONDS = 600
MIN_DURATION_MINUTES = 10
MAX_DURATION_MINUTES = 120
CANONICAL_PLANNING_FLOW = "video_ai_real"
INTERNAL_STEPS = (
    "scene_count",
    "aspect_ratio",
    "content_source",
    "scene_plan",
    "video_prompts",
    "transitions",
    "addons",
    "quality",
    "review",
    "final_confirm",
)


def normalize_internal_plan(state: dict | None) -> dict:
    updated = deepcopy(dict(state or {}))
    try:
        duration_minutes = int(updated.get("duration_minutes") or MIN_DURATION_MINUTES)
    except (TypeError, ValueError):
        duration_minutes = MIN_DURATION_MINUTES
    duration_minutes = max(MIN_DURATION_MINUTES, min(MAX_DURATION_MINUTES, duration_minutes))
    scene_count = max(1, (duration_minutes * 60 + SCENE_DURATION_SECONDS - 1) // SCENE_DURATION_SECONDS)
    updated.update({
        "flow": "longvideo_internal",
        "owner": "longvideo_internal",
        "canonical_planning_flow": CANONICAL_PLANNING_FLOW,
        "planning_steps": list(INTERNAL_STEPS),
        "public_enabled": False,
        "duration_minutes": duration_minutes,
        "scene_unit_minutes": SCENE_DURATION_SECONDS // 60,
        "scene_duration_seconds": SCENE_DURATION_SECONDS,
        "scene_count": scene_count,
        "final_confirmed": False,
        "provider_called": False,
        "job_created": False,
        "outbox_created": False,
        "wallet_mutations": 0,
        "xu_charged": 0,
    })
    return updated


def public_access_allowed(*, is_admin: bool = False) -> bool:
    # The product remains unavailable in public even for an admin using public UI.
    return bool(PUBLIC_ENABLED and is_admin)
