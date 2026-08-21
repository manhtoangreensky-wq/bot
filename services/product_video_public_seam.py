"""Durable Product Video routing contract for the locked public confirm path.

This module is transport-free and has no provider, worker, wallet, or database
side effects. It selects from the immutable RouteEngine29M project snapshot and
validates the persisted decision at worker boundaries without inspecting prompt
keywords.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Callable, Mapping

from services import (
    product_video_multiscene_engine,
    product_video_one_scene_engine,
    video_engine_contract,
    video_uiflow3_execution_contract,
)


PUBLIC_SEAM_FLAG = "PRODUCT_VIDEO_DURABLE_PUBLIC_SEAM_ENABLED"
ROUTE_DECISION_VERSION = "videomenu_routeengine29n_product_public_seam_v1"
ONE_SCENE_ORCHESTRATION_MODE = "single_task_legacy"
MULTISCENE_ORCHESTRATION_MODE = "per_scene_8s"
WORKER_ROUTE_PAYLOAD_KEYS = (
    "product_video_durable_public_seam",
    "product_video_route_decision_version",
    "product_video_route_decision",
    "product_video_route_decision_sha256",
    "product_video_route_selection_sha256",
    "product_video_engine_mode",
    "scene_count",
    "route_id",
    "product_video_engine_adapter",
    "worker_job_type",
    "worker_owner",
    "required_worker_capability",
    "automatic_retry_allowed",
    "automatic_resubmit_allowed",
    "automatic_fallback_allowed",
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _clean(value).lower() in {"1", "true", "yes", "on"}


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _is_sha256(value: Any) -> bool:
    token = _clean(value).lower()
    return bool(
        len(token) == 64
        and all(character in "0123456789abcdef" for character in token)
    )


def _disabled_state() -> dict[str, Any]:
    return {
        "enabled": False,
        "ready": True,
        "legacy_passthrough": True,
        "blocker": "",
        "route_decision": None,
    }


def _blocked(blocker: str) -> dict[str, Any]:
    return {
        "enabled": True,
        "ready": False,
        "legacy_passthrough": False,
        "blocker": _clean(blocker) or "product_video_public_seam_blocked",
        "route_decision": None,
    }


def product_video_public_seam_enabled(
    environ: Mapping[str, Any] | None = None,
) -> bool:
    source = os.environ if environ is None else environ
    return _flag(source.get(PUBLIC_SEAM_FLAG, False))


def product_video_public_seam_applies_to_worker_job(
    job: Mapping[str, Any] | None,
) -> bool:
    payload = dict(job or {})
    if (
        payload.get("product_video_durable_public_seam")
        or "product_video_route_decision" in payload
    ):
        return True
    explicit = payload.get("product_video_public_seam_applicable")
    if isinstance(explicit, bool):
        return explicit
    project = payload.get("project")
    if isinstance(project, Mapping):
        selection = video_engine_contract.durable_video_product_route_selection(
            project
        )
        if selection.get("selection_ok"):
            return (
                selection.get("engine_product")
                == video_engine_contract.VideoProduct.PRODUCT_VIDEO.value
            )
    return bool(
        _clean(payload.get("source")) == "product_video"
        or payload.get("product_video")
        or _clean(payload.get("job_type")) == "video_render"
    )


def _mode_readiness(
    mode: str,
    environ: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], str]:
    if mode == video_engine_contract.VideoEngineMode.SINGLE_SCENE.value:
        flags = product_video_one_scene_engine.product_video_one_scene_flags(environ)
        checks = (
            ("PRODUCT_VIDEO_ONE_SCENE_ENGINE_ENABLED", "product_video_one_scene_engine_disabled"),
            ("PRODUCT_VIDEO_ONE_SCENE_PUBLIC_ALLOWED", "product_video_one_scene_public_disabled"),
            ("PRODUCT_VIDEO_ONE_SCENE_AUTO_RETRY", "product_video_one_scene_automatic_retry_forbidden", True),
            ("PRODUCT_VIDEO_ONE_SCENE_AUTO_FALLBACK", "product_video_one_scene_automatic_fallback_forbidden", True),
            ("PRODUCT_VIDEO_ONE_SCENE_REAL_PROVIDER_ENABLED", "product_video_one_scene_real_provider_disabled"),
        )
    elif mode == video_engine_contract.VideoEngineMode.MULTI_SCENE.value:
        flags = product_video_multiscene_engine.product_video_multiscene_flags(environ)
        checks = (
            ("PRODUCT_VIDEO_MULTISCENE_ENGINE_ENABLED", "product_video_multiscene_engine_disabled"),
            ("PRODUCT_VIDEO_MULTISCENE_PUBLIC_ALLOWED", "product_video_multiscene_public_disabled"),
            ("PRODUCT_VIDEO_MULTISCENE_AUTO_RESUBMIT", "product_video_multiscene_automatic_resubmit_forbidden", True),
            ("PRODUCT_VIDEO_MULTISCENE_AUTO_FALLBACK", "product_video_multiscene_automatic_fallback_forbidden", True),
            ("PRODUCT_VIDEO_MULTISCENE_REAL_PROVIDER_ENABLED", "product_video_multiscene_real_provider_disabled"),
        )
    else:
        return {}, "product_video_public_seam_mode_unsupported"
    for check in checks:
        name, blocker = check[0], check[1]
        forbidden_when_true = len(check) > 2 and check[2] is True
        value = bool(flags.get(name))
        if (forbidden_when_true and value) or (not forbidden_when_true and not value):
            return flags, blocker
    return flags, ""


def evaluate_product_video_public_seam(
    project: Mapping[str, Any] | None,
    *,
    environ: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve one immutable Product Video route decision without side effects."""

    if not product_video_public_seam_enabled(environ):
        return _disabled_state()
    selection = video_engine_contract.durable_video_product_route_selection(project)
    if not selection.get("selection_ok"):
        return _blocked(
            _clean(selection.get("blocker"))
            or "product_video_public_seam_selection_invalid"
        )
    if selection.get("engine_product") != video_engine_contract.VideoProduct.PRODUCT_VIDEO.value:
        return _disabled_state()
    mode = _clean(selection.get("mode"))
    _flags, blocker = _mode_readiness(mode, environ)
    if blocker:
        return _blocked(blocker)
    route = video_engine_contract.product_route_contract(
        video_engine_contract.VideoProduct.PRODUCT_VIDEO,
        mode=mode,
        environ=environ,
    )
    if not route.get("connected"):
        return _blocked(
            _clean(route.get("blocker"))
            or "product_video_public_seam_route_not_connected"
        )
    if mode not in tuple(route.get("supported_modes") or ()):
        return _blocked("product_video_public_seam_route_mode_mismatch")
    scene_count = int(selection.get("scene_count") or 0)
    if scene_count <= 0 or (scene_count == 1) != (
        mode == video_engine_contract.VideoEngineMode.SINGLE_SCENE.value
    ):
        return _blocked("product_video_public_seam_scene_count_mismatch")
    material = {
        "route_decision_version": ROUTE_DECISION_VERSION,
        "engine_product": video_engine_contract.VideoProduct.PRODUCT_VIDEO.value,
        "mode": mode,
        "scene_count": scene_count,
        "selection_sha256": _clean(selection.get("route_selection_sha256")).lower(),
        "route_id": _clean(route.get("route_id")),
        "engine_adapter": _clean(route.get("engine_route")),
        "worker_job_type": _clean(route.get("worker_job_type")),
        "worker_owner": _clean(route.get("worker_owner")),
        "required_capability": _clean(route.get("required_capability")),
        "canonical_engine_entry": "b13_r18c",
        "automatic_retry_allowed": False,
        "automatic_resubmit_allowed": False,
        "automatic_fallback_allowed": False,
    }
    required_values = (
        material["selection_sha256"],
        material["route_id"],
        material["engine_adapter"],
        material["worker_job_type"],
        material["worker_owner"],
        material["required_capability"],
    )
    if not all(required_values) or not _is_sha256(material["selection_sha256"]):
        return _blocked("product_video_public_seam_route_material_incomplete")
    decision = {
        **material,
        "route_decision_sha256": _sha256(material),
    }
    return {
        "enabled": True,
        "ready": True,
        "legacy_passthrough": False,
        "blocker": "",
        "route_decision": decision,
    }


def product_video_route_decision_payload(
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    frozen = dict(decision or {})
    return {
        "product_video_durable_public_seam": True,
        "product_video_route_decision_version": _clean(
            frozen.get("route_decision_version")
        ),
        "product_video_route_decision": frozen,
        "product_video_route_decision_sha256": _clean(
            frozen.get("route_decision_sha256")
        ).lower(),
        "product_video_route_selection_sha256": _clean(
            frozen.get("selection_sha256")
        ).lower(),
        "product_video_engine_mode": _clean(frozen.get("mode")),
        "scene_count": int(frozen.get("scene_count") or 0),
        "route_id": _clean(frozen.get("route_id")),
        "product_video_engine_adapter": _clean(
            frozen.get("engine_adapter")
        ),
        "worker_job_type": _clean(frozen.get("worker_job_type")),
        "worker_owner": _clean(frozen.get("worker_owner")),
        "required_worker_capability": _clean(
            frozen.get("required_capability")
        ),
        "automatic_retry_allowed": False,
        "automatic_resubmit_allowed": False,
        "automatic_fallback_allowed": False,
    }


def _validation_failure(blocker: str) -> dict[str, Any]:
    return {
        "enabled": True,
        "ready": False,
        "legacy_passthrough": False,
        "blocker": blocker,
        "decision": None,
    }


def validate_persisted_product_video_route_decision(
    payload: Mapping[str, Any] | None,
    *,
    environ: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate persisted route truth without reselecting from project content."""

    persisted_marker = bool(
        isinstance(payload, Mapping)
        and (
            payload.get("product_video_durable_public_seam")
            or "product_video_route_decision" in payload
        )
    )
    if not product_video_public_seam_enabled(environ) and not persisted_marker:
        return {
            "enabled": False,
            "ready": True,
            "legacy_passthrough": True,
            "blocker": "",
            "decision": None,
        }
    if not isinstance(payload, Mapping):
        return _validation_failure("product_video_route_decision_missing")
    raw_decision = payload.get("product_video_route_decision")
    if not isinstance(raw_decision, Mapping):
        return _validation_failure("product_video_route_decision_missing")
    decision = dict(raw_decision)
    persisted_hash = _clean(decision.pop("route_decision_sha256", "")).lower()
    if (
        not _is_sha256(persisted_hash)
        or persisted_hash != _sha256(decision)
        or persisted_hash
        != _clean(payload.get("product_video_route_decision_sha256")).lower()
    ):
        return _validation_failure("product_video_route_decision_hash_mismatch")
    decision["route_decision_sha256"] = persisted_hash
    if decision.get("route_decision_version") != ROUTE_DECISION_VERSION:
        return _validation_failure("product_video_route_decision_version_mismatch")
    if decision.get("engine_product") != video_engine_contract.VideoProduct.PRODUCT_VIDEO.value:
        return _validation_failure("product_video_route_decision_product_mismatch")
    mode = _clean(decision.get("mode"))
    try:
        scene_count = int(decision.get("scene_count") or 0)
    except (TypeError, ValueError):
        scene_count = 0
    if scene_count <= 0 or (scene_count == 1) != (
        mode == video_engine_contract.VideoEngineMode.SINGLE_SCENE.value
    ):
        return _validation_failure("product_video_route_decision_scene_count_mismatch")
    try:
        payload_scene_count = int(payload.get("scene_count") or 0)
    except (TypeError, ValueError):
        payload_scene_count = 0
    if payload_scene_count != scene_count:
        return _validation_failure("product_video_route_decision_scene_count_mismatch")
    if not _is_sha256(decision.get("selection_sha256")):
        return _validation_failure("product_video_route_selection_hash_invalid")
    _flags, blocker = _mode_readiness(mode, environ)
    if blocker:
        return _validation_failure(blocker)
    route = video_engine_contract.product_route_contract(
        video_engine_contract.VideoProduct.PRODUCT_VIDEO,
        mode=mode,
        environ=environ,
    )
    expected = {
        "route_id": _clean(route.get("route_id")),
        "engine_adapter": _clean(route.get("engine_route")),
        "worker_job_type": _clean(route.get("worker_job_type")),
        "worker_owner": _clean(route.get("worker_owner")),
        "required_capability": _clean(route.get("required_capability")),
        "canonical_engine_entry": "b13_r18c",
    }
    if "job_type" in payload and _clean(payload.get("job_type")) != expected["worker_job_type"]:
        return _validation_failure(
            "product_video_route_decision_worker_job_type_mismatch"
        )
    for key, value in expected.items():
        if decision.get(key) != value:
            return _validation_failure(
                f"product_video_route_decision_{key}_mismatch"
            )
    for key in (
        "automatic_retry_allowed",
        "automatic_resubmit_allowed",
        "automatic_fallback_allowed",
    ):
        if decision.get(key) is not False or payload.get(key) is not False:
            return _validation_failure(f"product_video_route_decision_{key}_forbidden")
    flattened = product_video_route_decision_payload(decision)
    for key in (
        "product_video_route_decision_version",
        "product_video_route_selection_sha256",
        "product_video_engine_mode",
        "route_id",
        "product_video_engine_adapter",
        "worker_job_type",
        "worker_owner",
        "required_worker_capability",
    ):
        if payload.get(key) != flattened[key]:
            return _validation_failure(
                f"product_video_route_decision_{key}_mismatch"
            )
    return {
        "enabled": True,
        "ready": True,
        "legacy_passthrough": False,
        "blocker": "",
        "decision": decision,
    }


def prepare_product_video_worker_job(
    job: Mapping[str, Any] | None,
    *,
    environ: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    prepared = dict(job or {})
    validation = validate_persisted_product_video_route_decision(
        prepared,
        environ=environ,
    )
    if not validation.get("ready"):
        raise RuntimeError(
            _clean(validation.get("blocker"))
            or "product_video_route_decision_invalid"
        )
    uiflow3_contract = video_uiflow3_execution_contract.validate_execution_contract(
        payload=prepared,
        require_payload_identity=True,
    )
    if not uiflow3_contract.get("ok"):
        raise RuntimeError(
            _clean(uiflow3_contract.get("blocker"))
            or "uiflow3_execution_contract_invalid"
        )
    if uiflow3_contract.get("applies"):
        prepared["uiflow3_execution_contract"] = uiflow3_contract
    decision = validation.get("decision")
    if isinstance(decision, Mapping):
        prepared.update(product_video_route_decision_payload(decision))
        prepared["engine_adapter"] = _clean(decision.get("engine_adapter"))
        mode = _clean(decision.get("mode"))
        prepared["product_video_runtime_lane"] = mode
        prepared["product_video_runtime_engine_adapter"] = _clean(
            decision.get("engine_adapter")
        )
        if mode == video_engine_contract.VideoEngineMode.SINGLE_SCENE.value:
            orchestration_mode = ONE_SCENE_ORCHESTRATION_MODE
        elif mode == video_engine_contract.VideoEngineMode.MULTI_SCENE.value:
            orchestration_mode = MULTISCENE_ORCHESTRATION_MODE
        else:
            raise RuntimeError("product_video_route_decision_mode_unsupported")
        prepared["orchestration_mode"] = orchestration_mode
        prepared["provider_orchestration_mode"] = orchestration_mode
    return prepared


def execute_product_video_worker_route(
    job: Mapping[str, Any] | None,
    *,
    one_scene_executor: Callable[[dict[str, Any]], Any],
    multiscene_executor: Callable[[dict[str, Any]], Any],
    legacy_executor: Callable[[dict[str, Any]], Any] | None = None,
    environ: Mapping[str, Any] | None = None,
) -> Any:
    """Execute only the immutable worker lane selected at public confirm."""

    raw_job = dict(job or {})
    if not product_video_public_seam_applies_to_worker_job(raw_job):
        if legacy_executor is None:
            raise RuntimeError("product_video_legacy_executor_missing")
        return legacy_executor(raw_job)
    prepared = prepare_product_video_worker_job(job, environ=environ)
    decision = prepared.get("product_video_route_decision")
    if not isinstance(decision, Mapping):
        if legacy_executor is None:
            raise RuntimeError("product_video_route_decision_missing")
        return legacy_executor(prepared)
    mode = _clean(decision.get("mode"))
    if mode == video_engine_contract.VideoEngineMode.SINGLE_SCENE.value:
        return one_scene_executor(prepared)
    if mode == video_engine_contract.VideoEngineMode.MULTI_SCENE.value:
        return multiscene_executor(prepared)
    raise RuntimeError("product_video_route_decision_mode_unsupported")
