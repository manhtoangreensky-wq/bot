"""Read-only, versioned prompt-pattern library for video planning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PATTERN_ROOT = REPO_ROOT / "knowledge" / "video" / "prompt_patterns"


def _load(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    values = payload.get("patterns") if isinstance(payload, dict) else payload
    return [dict(item) for item in (values or []) if isinstance(item, dict)]


def pattern_is_default_eligible(pattern: dict[str, Any]) -> bool:
    if not bool(pattern.get("admin_approved")):
        return False
    if str(pattern.get("status") or "active") != "active":
        return False
    source_type = str(pattern.get("source_type") or "").strip()
    if source_type in {"curated_default", "admin_template"}:
        return True
    return bool(pattern.get("anonymized") and pattern.get("customer_consent") and not pattern.get("contains_private_assets"))


def load_approved_patterns(root: Path | None = None) -> list[dict[str, Any]]:
    base = root or PATTERN_ROOT
    patterns: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json")):
        patterns.extend(_load(path))
    eligible = [item for item in patterns if pattern_is_default_eligible(item)]
    return sorted(eligible, key=lambda item: (-float(item.get("evaluation_score") or 0), str(item.get("version") or ""), str(item.get("pattern_id") or "")))


def select_approved_pattern(profile_id: str, scene_count: int, root: Path | None = None) -> dict[str, Any]:
    profile = str(profile_id or "general").lower()
    count = max(1, min(20, int(scene_count or 1)))
    patterns = load_approved_patterns(root)
    candidates = [
        item for item in patterns
        if str(item.get("profile") or "general").lower() in {"general", profile}
        and count in [int(value) for value in (item.get("scene_counts") or [count])]
    ]
    if not candidates:
        candidates = [item for item in patterns if str(item.get("profile") or "general").lower() == "general"]
    return dict(candidates[0]) if candidates else {
        "pattern_id": "deterministic_fallback",
        "profile": "general",
        "version": "1.0.0",
        "scene_roles": ["setup", "development", "conclusion"],
        "transition_pattern": ["match cut", "sound bridge"],
        "admin_approved": True,
        "source_type": "curated_default",
        "evaluation_score": 0,
    }


def learning_candidate_metadata(
    *,
    profile: str,
    scene_count: int,
    duration: int,
    scene_roles: list[str],
    transitions: list[str],
    addon_plan: dict[str, Any],
    evaluation_score: float = 0,
) -> dict[str, Any]:
    """Create isolated review metadata; never persists raw customer prompts/assets."""

    return {
        "profile": str(profile or "general"),
        "scene_count": max(1, min(20, int(scene_count or 1))),
        "duration": max(1, int(duration or 8)),
        "scene_roles": [str(item) for item in scene_roles],
        "transition_pattern": [str(item) for item in transitions],
        "add_on_plan": dict(addon_plan or {}),
        "prompt_template_version": "candidate-1",
        "evaluation_score": float(evaluation_score or 0),
        "admin_approved": False,
        "contains_private_assets": False,
        "raw_customer_prompt_stored": False,
        "default_eligible": False,
    }
