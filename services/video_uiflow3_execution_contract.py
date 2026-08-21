"""Immutable UIFLOW3 identity and final-artifact contract.

This module is deliberately transport-, database-, provider-, and UI-free so
the same checks can run at worker, completion, and delivery boundaries.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping


BRIDGE_VERSION = "video_uiflow3_routeengine_v1"
RATIO_GEOMETRY = {
    "9:16": {"width": 1080, "height": 1920},
    "16:9": {"width": 1920, "height": 1080},
    "1:1": {"width": 1080, "height": 1080},
    "4:5": {"width": 1080, "height": 1350},
}
UIFLOW3_IDENTITY_KEYS = (
    "uiflow3_bridge_version",
    "uiflow3_draft_id",
    "uiflow3_owner_user_id",
    "uiflow3_owner_chat_id",
    "uiflow3_snapshot_config_hash",
    "uiflow3_handoff_sha256",
    "uiflow3_quote_sha256",
    "uiflow3_route_selection_sha256",
)
UIFLOW3_HASH_KEYS = frozenset(
    {
        "uiflow3_snapshot_config_hash",
        "uiflow3_handoff_sha256",
        "uiflow3_quote_sha256",
        "uiflow3_route_selection_sha256",
    }
)


def _clean(value: Any, limit: int = 12000) -> str:
    return str(value or "").strip()[: max(0, int(limit))]


def _positive_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return deepcopy(dict(value))
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return deepcopy(dict(parsed)) if isinstance(parsed, Mapping) else {}
    return {}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _is_sha256(value: Any) -> bool:
    token = _clean(value, 64).lower()
    return bool(
        len(token) == 64
        and all(character in "0123456789abcdef" for character in token)
    )


def snapshot_hash_valid(snapshot: Mapping[str, Any] | None) -> bool:
    if not isinstance(snapshot, Mapping):
        return False
    expected = _clean(snapshot.get("config_hash"), 64).lower()
    if not _is_sha256(expected):
        return False
    material = deepcopy(dict(snapshot))
    material.pop("config_hash", None)
    return _sha256(material) == expected


def _failure(reason: str, **extra: Any) -> dict[str, Any]:
    return {
        **extra,
        "applies": True,
        "ok": False,
        "blocker": _clean(reason, 240) or "uiflow3_execution_contract_invalid",
    }


def _ratio_value(value: Any) -> float:
    text = _clean(value, 40)
    if ":" not in text:
        return 0.0
    left, right = text.split(":", 1)
    try:
        numerator = float(left)
        denominator = float(right)
    except (TypeError, ValueError):
        return 0.0
    if numerator <= 0 or denominator <= 0:
        return 0.0
    return numerator / denominator


def validate_execution_contract(
    project: Mapping[str, Any] | None = None,
    payload: Mapping[str, Any] | None = None,
    *,
    artifact_validation: Mapping[str, Any] | None = None,
    require_payload_identity: bool = False,
    require_artifact: bool = False,
) -> dict[str, Any]:
    """Validate one UIFLOW3 plan identity through render and delivery."""

    project_value = dict(project or {})
    payload_value = dict(payload or {})
    asset_pack = _mapping(payload_value.get("asset_pack"))
    if not asset_pack:
        asset_pack = _mapping(project_value.get("asset_pack_json"))
    marker = _clean(
        asset_pack.get("uiflow3_bridge_version")
        or payload_value.get("uiflow3_bridge_version"),
        120,
    )
    if not marker:
        return {"applies": False, "ok": True, "blocker": ""}
    if marker != BRIDGE_VERSION:
        return _failure("uiflow3_bridge_version_mismatch")

    expected_identity: dict[str, Any] = {}
    for key in UIFLOW3_IDENTITY_KEYS:
        expected = asset_pack.get(key)
        if expected in (None, ""):
            return _failure(f"{key}_missing")
        if key in UIFLOW3_HASH_KEYS and not _is_sha256(expected):
            return _failure(f"{key}_invalid")
        expected_identity[key] = expected
        actual = payload_value.get(key)
        if require_payload_identity and actual in (None, ""):
            return _failure(f"{key}_missing")
        if actual not in (None, "") and str(actual) != str(expected):
            return _failure(f"{key}_mismatch")

    snapshot = _mapping(asset_pack.get("uiflow3_approved_snapshot"))
    if not snapshot:
        return _failure("uiflow3_approved_snapshot_missing")
    if not snapshot_hash_valid(snapshot):
        return _failure("uiflow3_approved_snapshot_hash_mismatch")
    snapshot_hash = _clean(snapshot.get("config_hash"), 64).lower()
    if snapshot_hash != _clean(
        expected_identity["uiflow3_snapshot_config_hash"],
        64,
    ).lower():
        return _failure("uiflow3_snapshot_config_hash_mismatch")
    if _clean(snapshot.get("draft_id"), 160) != _clean(
        expected_identity["uiflow3_draft_id"],
        160,
    ):
        return _failure("uiflow3_draft_id_mismatch")

    owner_user_id = _positive_int(expected_identity["uiflow3_owner_user_id"])
    owner_chat_id = _positive_int(expected_identity["uiflow3_owner_chat_id"])
    observed_user_id = _positive_int(
        project_value.get("user_id") or payload_value.get("user_id")
    )
    if owner_user_id <= 0 or owner_chat_id != owner_user_id:
        return _failure("uiflow3_owner_identity_invalid")
    if observed_user_id and observed_user_id != owner_user_id:
        return _failure("uiflow3_owner_user_id_mismatch")

    route_selection = _mapping(asset_pack.get("route_selection"))
    if not route_selection:
        return _failure("uiflow3_route_selection_missing")
    if _clean(route_selection.get("route_selection_sha256"), 64).lower() != _clean(
        expected_identity["uiflow3_route_selection_sha256"],
        64,
    ).lower():
        return _failure("uiflow3_route_selection_sha256_mismatch")

    snapshot_ratio = _clean((snapshot.get("format") or {}).get("ratio"), 20)
    project_ratio = _clean(project_value.get("ratio"), 20)
    expected_ratio = _clean(asset_pack.get("aspect_ratio"), 20) or project_ratio or snapshot_ratio
    expected_geometry = _mapping(asset_pack.get("output_geometry")) or dict(
        RATIO_GEOMETRY.get(expected_ratio) or {}
    )
    if expected_ratio not in RATIO_GEOMETRY or not expected_geometry:
        return _failure("uiflow3_output_geometry_invalid")
    if snapshot_ratio != expected_ratio:
        return _failure("uiflow3_snapshot_ratio_mismatch")
    if project_ratio and project_ratio != expected_ratio:
        return _failure("uiflow3_project_ratio_mismatch")

    result = {
        "applies": True,
        "ok": True,
        "blocker": "",
        "bridge_version": marker,
        "snapshot_config_hash": snapshot_hash,
        "handoff_sha256": _clean(expected_identity["uiflow3_handoff_sha256"], 64),
        "expected_aspect_ratio": expected_ratio,
        "expected_geometry": expected_geometry,
    }
    if not require_artifact:
        return result

    validation = dict(artifact_validation or {})
    if not validation.get("ok"):
        return _failure("uiflow3_final_artifact_validation_required", **result)
    width = _positive_int(validation.get("width"))
    height = _positive_int(validation.get("height"))
    if width <= 0 or height <= 0:
        return _failure("uiflow3_output_geometry_missing", **result)
    sample_ratio = _ratio_value(validation.get("sample_aspect_ratio") or "1:1") or 1.0
    expected_ratio_value = _ratio_value(expected_ratio)
    actual_ratio_value = (float(width) * sample_ratio) / float(height)
    ratio_error = abs(actual_ratio_value - expected_ratio_value) / expected_ratio_value
    artifact_fields = {
        **result,
        "actual_width": width,
        "actual_height": height,
        "sample_aspect_ratio": _clean(
            validation.get("sample_aspect_ratio") or "1:1",
            40,
        ),
        "actual_aspect_ratio_value": actual_ratio_value,
        "aspect_ratio_relative_error": ratio_error,
    }
    if ratio_error > 0.01:
        return _failure("uiflow3_output_aspect_ratio_mismatch", **artifact_fields)
    return artifact_fields
