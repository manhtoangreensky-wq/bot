"""Local prompt vault for video product planning.

The vault is intentionally provider-free: it only loads curated local JSON
blocks and returns text guidance for storyboard/prompt planning.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


VAULT_DIR = Path(__file__).resolve().parents[1] / "config" / "video_prompt_vault"
PROFILE_DIR = VAULT_DIR / "profiles"
SHARED_DIR = VAULT_DIR / "shared"

PROFILE_IDS = (
    "storytelling",
    "product_review",
    "news",
    "philosophy_quotes",
    "educational",
    "history",
    "ugc_affiliate",
    "real_estate_fpv",
    "fashion_lookbook",
    "food_asmr",
    "lofi_audio_visualizer",
    "cinematic_trailer",
)

SHARED_BLOCKS = (
    "shot_types",
    "camera_motion",
    "transitions",
    "color_tones",
    "negative_prompts",
    "postprocess_cues",
)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return dict(payload or {})


@lru_cache(maxsize=1)
def load_prompt_vault() -> dict[str, Any]:
    profiles = {profile_id: load_profile_pack(profile_id) for profile_id in PROFILE_IDS}
    shared = {name: load_shared_block(name) for name in SHARED_BLOCKS}
    return {
        "config_path": str(VAULT_DIR),
        "profiles": profiles,
        "shared": shared,
        "provider_called": False,
        "xu_charged": 0,
    }


@lru_cache(maxsize=64)
def load_profile_pack(profile_id: str) -> dict[str, Any]:
    clean = str(profile_id or "storytelling").strip()
    if clean not in PROFILE_IDS:
        clean = "storytelling"
    pack = _load_json(PROFILE_DIR / f"{clean}.json")
    pack.setdefault("profile_id", clean)
    return pack


@lru_cache(maxsize=32)
def load_shared_block(name: str) -> dict[str, Any]:
    clean = str(name or "").strip()
    if clean not in SHARED_BLOCKS:
        clean = "shot_types"
    payload = _load_json(SHARED_DIR / f"{clean}.json")
    payload.setdefault("name", clean)
    return payload


def list_profile_packs() -> list[dict[str, Any]]:
    return [load_profile_pack(profile_id) for profile_id in PROFILE_IDS]


def vault_status() -> dict[str, Any]:
    vault = load_prompt_vault()
    return {
        "config_path": vault["config_path"],
        "profile_count": len(vault["profiles"]),
        "profile_ids": list(vault["profiles"].keys()),
        "shared_blocks": list(vault["shared"].keys()),
        "provider_called": False,
        "xu_charged": 0,
    }


def prompt_vault_summary(profile_id: str = "") -> str:
    status = vault_status()
    if profile_id:
        pack = load_profile_pack(profile_id)
        return (
            f"profile={pack.get('profile_id')} hooks={len(pack.get('hook_templates') or [])} "
            f"domains={len(pack.get('product_domains') or {})} shared={len(status['shared_blocks'])}"
        )
    return f"profiles={status['profile_count']} shared={','.join(status['shared_blocks'])}"
