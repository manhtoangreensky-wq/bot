"""Fail-closed Product Video one-scene engine contract.

The module is transport-free and provider-free. Runtime callers inject the
provider submit, delivery, receipt, charge, and terminal-report boundaries.
All public and real-provider feature flags are disabled by default.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping

from services import video_engine_contract, video_final_output


ROUTE_ID = "product_video_one_scene_v1"
PRODUCT_FAMILY = "product_video"
MODE = "one_scene"
ENGINE_ADAPTER = "b13_r18c_product_one_scene_v1"
WORKER_JOB_TYPE = "video_render"
WORKER_OWNER = "owner_product_video"
CANONICAL_WORKER_CAPABILITY = "canonical_multiscene_b13_r18c_v1"
REQUIRED_WORKER_CAPABILITIES = (
    "product_video",
    "owner_product_video",
    CANONICAL_WORKER_CAPABILITY,
)
ADDON_NAMES = (
    "voice",
    "subtitle",
    "dubbing",
    "music",
    "sfx",
    "logo",
    "watermark",
    "text",
    "transitions",
)
SUPPORTED_ADDONS = ADDON_NAMES
MINIMUM_ARTIFACT_BYTES = 4096
ACCEPTED_VIDEO_CODECS = frozenset({"h264", "hevc", "av1", "vp9"})

FEATURE_FLAG_DEFAULTS = {
    "PRODUCT_VIDEO_ONE_SCENE_ENGINE_ENABLED": False,
    "PRODUCT_VIDEO_ONE_SCENE_PUBLIC_ALLOWED": False,
    "PRODUCT_VIDEO_ONE_SCENE_REAL_PROVIDER_ENABLED": False,
    "PRODUCT_VIDEO_ONE_SCENE_AUTO_RETRY": False,
    "PRODUCT_VIDEO_ONE_SCENE_AUTO_FALLBACK": False,
}


class ProviderState(str, Enum):
    NOT_SUBMITTED = "NOT_SUBMITTED"
    SUBMITTING = "SUBMITTING"
    ACCEPTED = "ACCEPTED"
    ACCEPTANCE_UNKNOWN = "ACCEPTANCE_UNKNOWN"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ProviderAcceptanceUnknown(RuntimeError):
    """The submit transport ended without proving accepted or rejected."""


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _clean(value).lower() in {"1", "true", "yes", "on"}


def _positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name}_required")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name}_required") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name}_required")
    return parsed


def _nonnegative_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return max(0, int(default or 0))
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return max(0, int(default or 0))


def _canonical_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", _clean(value)).casefold()
    return " ".join(normalized.split())


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: _json_safe(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_safe(item) for item in value]
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(_json_safe(value), ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def product_video_one_scene_flags(
    environ: Mapping[str, Any] | None = None,
) -> dict[str, bool]:
    source = os.environ if environ is None else environ
    return {
        name: _flag(source.get(name, default))
        for name, default in FEATURE_FLAG_DEFAULTS.items()
    }


def shared_product_video_one_scene_route() -> dict[str, Any]:
    return {
        "product": PRODUCT_FAMILY,
        "state": video_engine_contract.VideoRouteState.CONNECTED.value,
        "connected": True,
        "public_product_type": PRODUCT_FAMILY,
        "worker_job_type": WORKER_JOB_TYPE,
        "engine_route": ENGINE_ADAPTER,
        "worker_owner": WORKER_OWNER,
        "required_capability": CANONICAL_WORKER_CAPABILITY,
        "required_capabilities": REQUIRED_WORKER_CAPABILITIES,
        "supported_modes": (
            video_engine_contract.VideoEngineMode.SINGLE_SCENE.value,
        ),
        "provider_enabled": True,
        "local_enabled": False,
        "route_id": ROUTE_ID,
        "blocker": "",
    }


def product_video_one_scene_contract(
    environ: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    flags = product_video_one_scene_flags(environ)
    return {
        "route_id": ROUTE_ID,
        "product_family": PRODUCT_FAMILY,
        "mode": MODE,
        "engine_adapter": ENGINE_ADAPTER,
        "required_inputs": (
            "explicit_confirmation_receipt",
            "original_user_prompt",
            "compiled_engine_prompt",
            "approved_product_facts",
            "input_assets",
            "aspect_ratio",
            "duration_seconds",
            "scene_count=1",
            "explicit_provider_route",
        ),
        "supported_addons": SUPPORTED_ADDONS,
        "unsupported_addons": tuple(
            name for name in ADDON_NAMES if name not in SUPPORTED_ADDONS
        ),
        "provider_requirements": {
            "explicit_route": True,
            "at_most_one_submit": True,
            "automatic_retry": False,
            "automatic_fallback": False,
        },
        "worker_capabilities": REQUIRED_WORKER_CAPABILITIES,
        "artifact_promise": {
            "container": "mp4",
            "scene_count": 1,
            "video_stream": True,
            "full_decode": True,
            "placeholder": False,
        },
        "validation_promise": (
            "minimum_size",
            "ffprobe",
            "video_stream",
            "duration_tolerance",
            "accepted_codec_container",
            "full_decode",
            "motion_when_promised",
            "audio_when_promised",
        ),
        "delivery_billing_contract": (
            "validate_mp4",
            "delivery_accepted",
            "receipt_persisted",
            "charge_once",
            "terminal_report_once",
        ),
        "readiness": {
            "engine_enabled": flags["PRODUCT_VIDEO_ONE_SCENE_ENGINE_ENABLED"],
            "public_allowed": flags["PRODUCT_VIDEO_ONE_SCENE_PUBLIC_ALLOWED"],
            "real_provider_enabled": flags[
                "PRODUCT_VIDEO_ONE_SCENE_REAL_PROVIDER_ENABLED"
            ],
        },
    }


@dataclass(frozen=True)
class ProductVideoPromptContract:
    original_user_prompt: str
    compiled_engine_prompt: str
    original_prompt_sha256: str
    compiled_prompt_sha256: str
    product_name: str
    required_visual_attributes: tuple[str, ...]
    forbidden_claims: tuple[str, ...]
    language: str
    aspect_ratio: str
    duration_seconds: int
    scene_count: int


def compile_product_video_prompt(
    *,
    original_user_prompt: str,
    product_name: str,
    required_visual_attributes: tuple[str, ...] | list[str],
    forbidden_claims: tuple[str, ...] | list[str],
    language: str,
    aspect_ratio: str,
    duration_seconds: int,
    scene_count: int = 1,
) -> ProductVideoPromptContract:
    original = _clean(original_user_prompt)
    product = _clean(product_name)
    lang = _clean(language)
    ratio = _clean(aspect_ratio)
    duration = _positive_int(duration_seconds, field_name="duration_seconds")
    count = _positive_int(scene_count, field_name="scene_count")
    attributes = tuple(_clean(item) for item in required_visual_attributes if _clean(item))
    forbidden = tuple(_clean(item) for item in forbidden_claims if _clean(item))
    if not original:
        raise ValueError("original_user_prompt_required")
    if not product:
        raise ValueError("product_name_required")
    if not lang:
        raise ValueError("language_required")
    if not ratio:
        raise ValueError("aspect_ratio_required")
    if count != 1:
        raise ValueError("one_scene_required")
    compiled_lines = [
        f"original_user_prompt={original}",
        f"product_name={product}",
        f"required_visual_attributes={'; '.join(attributes) or 'none'}",
        f"forbidden_claims={'; '.join(forbidden) or 'none'}",
        f"language={lang}",
        f"aspect_ratio={ratio}",
        f"duration_seconds={duration}",
        "scene_count=1",
        "continuity=single approved product scene; preserve all approved facts",
    ]
    compiled = "\n".join(compiled_lines)
    return ProductVideoPromptContract(
        original_user_prompt=original,
        compiled_engine_prompt=compiled,
        original_prompt_sha256=_sha256_text(original),
        compiled_prompt_sha256=_sha256_text(compiled),
        product_name=product,
        required_visual_attributes=attributes,
        forbidden_claims=forbidden,
        language=lang,
        aspect_ratio=ratio,
        duration_seconds=duration,
        scene_count=count,
    )


def validate_product_video_prompt(
    contract: ProductVideoPromptContract,
) -> dict[str, Any]:
    if not isinstance(contract, ProductVideoPromptContract):
        return {"ok": False, "blocker": "prompt_contract_required"}
    if contract.scene_count != 1:
        return {"ok": False, "blocker": "one_scene_required"}
    if _sha256_text(contract.original_user_prompt) != contract.original_prompt_sha256:
        return {"ok": False, "blocker": "original_prompt_hash_mismatch"}
    if _sha256_text(contract.compiled_engine_prompt) != contract.compiled_prompt_sha256:
        return {"ok": False, "blocker": "compiled_prompt_hash_mismatch"}
    required_values = (
        contract.original_user_prompt,
        contract.product_name,
        *contract.required_visual_attributes,
        *contract.forbidden_claims,
        contract.language,
        contract.aspect_ratio,
        str(contract.duration_seconds),
        "scene_count=1",
    )
    compiled = _canonical_text(contract.compiled_engine_prompt)
    missing = [item for item in required_values if _canonical_text(item) not in compiled]
    if missing:
        return {
            "ok": False,
            "blocker": "compiled_prompt_semantic_loss",
            "missing_fact_hashes": [_sha256_text(_clean(item)) for item in missing],
        }
    return {
        "ok": True,
        "blocker": "",
        "original_prompt_sha256": contract.original_prompt_sha256,
        "compiled_prompt_sha256": contract.compiled_prompt_sha256,
        "scene_count": 1,
    }


@dataclass(frozen=True)
class ProductVideoAddonState:
    name: str
    requested: bool
    approved: bool
    supported: bool
    required: bool
    materialized: bool
    handoff_status: str
    blocker_reason: str = ""
    artifact_path: str = ""
    artifact_kind: str = ""


def normalize_product_video_addons(
    values: Mapping[str, Mapping[str, Any]] | None,
) -> tuple[ProductVideoAddonState, ...]:
    source = values if isinstance(values, Mapping) else {}
    normalized: list[ProductVideoAddonState] = []
    for name in ADDON_NAMES:
        item = source.get(name) if isinstance(source.get(name), Mapping) else {}
        normalized.append(
            ProductVideoAddonState(
                name=name,
                requested=_flag(item.get("requested")),
                approved=_flag(item.get("approved")),
                supported=_flag(item.get("supported")),
                required=_flag(item.get("required")),
                materialized=_flag(item.get("materialized")),
                handoff_status=_clean(item.get("handoff_status") or "not_requested"),
                blocker_reason=_clean(item.get("blocker_reason")),
                artifact_path=_clean(item.get("artifact_path")),
                artifact_kind=_clean(item.get("artifact_kind")),
            )
        )
    return tuple(normalized)


def validate_product_video_addons(
    addons: tuple[ProductVideoAddonState, ...] | list[ProductVideoAddonState],
) -> dict[str, Any]:
    by_name = {item.name: item for item in addons if isinstance(item, ProductVideoAddonState)}
    manifest: dict[str, dict[str, Any]] = {}
    blocker = ""
    for name in ADDON_NAMES:
        item = by_name.get(name) or ProductVideoAddonState(
            name=name,
            requested=False,
            approved=False,
            supported=name in SUPPORTED_ADDONS,
            required=False,
            materialized=False,
            handoff_status="not_requested",
        )
        manifest[name] = _json_safe(item)
        if blocker or not item.requested:
            continue
        if not item.approved:
            blocker = f"addon_not_approved:{name}"
        elif not item.supported:
            blocker = item.blocker_reason or f"addon_unsupported:{name}"
        elif not item.materialized or not item.artifact_path:
            blocker = item.blocker_reason or f"addon_material_missing:{name}"
        elif item.handoff_status.lower() not in {"ready", "materialized", "handed_off"}:
            blocker = item.blocker_reason or f"addon_handoff_not_ready:{name}"
        elif name == "music" and any(
            marker in f"{item.artifact_path} {item.artifact_kind}".lower()
            for marker in ("sine_220", "sine-220", "220hz", "220_hz", "lavfi_sine")
        ):
            blocker = "music_material_not_valid_music"
    return {"ok": not blocker, "blocker": blocker, "addons": manifest}


def build_product_video_one_scene_request(
    *,
    user_id: int,
    confirmation_id: str,
    language: str,
    prompt_contract: ProductVideoPromptContract,
    addons: tuple[ProductVideoAddonState, ...],
    input_assets: tuple[Any, ...] | list[Any],
    aspect_ratio: str,
    duration_seconds: int,
    audio_policy: Mapping[str, Any],
    voice_policy: Mapping[str, Any],
    provider_selection: str,
    explicit_confirmation_receipt: Mapping[str, Any],
    runtime_sha: str,
    expected_worker_sha: str,
    scene_count: int = 1,
    admin_no_charge: bool = False,
    charge_plan: Mapping[str, Any] | None = None,
) -> video_engine_contract.VideoEngineRequest:
    prompt_state = validate_product_video_prompt(prompt_contract)
    if not prompt_state.get("ok") and prompt_state.get("blocker") != "compiled_prompt_semantic_loss":
        raise ValueError(str(prompt_state.get("blocker") or "prompt_contract_invalid"))
    duration = _positive_int(duration_seconds, field_name="duration_seconds")
    count = _positive_int(scene_count, field_name="scene_count")
    provider = _clean(provider_selection).lower()
    payload = {
        "route_id": ROUTE_ID,
        "product_family": PRODUCT_FAMILY,
        "scene_count": count,
        "original_user_prompt": prompt_contract.original_user_prompt,
        "compiled_engine_prompt": prompt_contract.compiled_engine_prompt,
        "original_prompt_sha256": prompt_contract.original_prompt_sha256,
        "compiled_prompt_sha256": prompt_contract.compiled_prompt_sha256,
        "product_name": prompt_contract.product_name,
        "required_visual_attributes": list(prompt_contract.required_visual_attributes),
        "forbidden_claims": list(prompt_contract.forbidden_claims),
        "addons": [_json_safe(item) for item in addons],
        "admin_no_charge": bool(admin_no_charge),
        "charge_plan": dict(charge_plan or {}),
        "motion_promised": True,
    }
    common = {
        "user_id": user_id,
        "language": language,
        "approved_plan": {
            "route_id": ROUTE_ID,
            "product_family": PRODUCT_FAMILY,
            "scene_count": count,
            "approved": True,
            "original_prompt_sha256": prompt_contract.original_prompt_sha256,
            "compiled_prompt_sha256": prompt_contract.compiled_prompt_sha256,
        },
        "input_assets": tuple(input_assets),
        "aspect_ratio": aspect_ratio,
        "duration_profile": {
            "duration_seconds": duration,
            "profile": "product_video_one_scene",
        },
        "audio_policy": dict(audio_policy),
        "voice_policy": dict(voice_policy),
        "provider_selection": provider,
        "runtime_sha": runtime_sha,
        "expected_worker_sha": expected_worker_sha,
    }
    key = video_engine_contract.stable_request_idempotency_key(
        confirmation_id=confirmation_id,
        product_type=video_engine_contract.VideoProduct.PRODUCT_VIDEO,
        mode=video_engine_contract.VideoEngineMode.SINGLE_SCENE,
        payload=payload,
        **common,
    )
    return video_engine_contract.VideoEngineRequest(
        request_id=f"{ROUTE_ID}:{key[:20]}",
        confirmation_id=confirmation_id,
        idempotency_key=key,
        product_type=video_engine_contract.VideoProduct.PRODUCT_VIDEO,
        mode=video_engine_contract.VideoEngineMode.SINGLE_SCENE,
        explicit_confirmation_receipt=dict(explicit_confirmation_receipt),
        confirmed=True,
        payload=payload,
        **common,
    )


def _sequence(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if not isinstance(value, (list, tuple, set, frozenset)):
        return ()
    return tuple(_clean(item) for item in value if _clean(item))


def product_video_one_scene_readiness(
    request: video_engine_contract.VideoEngineRequest,
    *,
    manifest: Mapping[str, Any],
    runtime_sha: str,
    prompt_contract: ProductVideoPromptContract,
    addons: tuple[ProductVideoAddonState, ...],
    environ: Mapping[str, Any] | None = None,
    public_request: bool = False,
) -> dict[str, Any]:
    flags = product_video_one_scene_flags(environ)
    blocker = ""
    if not flags["PRODUCT_VIDEO_ONE_SCENE_ENGINE_ENABLED"]:
        blocker = "one_scene_engine_disabled"
    elif public_request and not flags["PRODUCT_VIDEO_ONE_SCENE_PUBLIC_ALLOWED"]:
        blocker = "one_scene_public_disabled"
    elif flags["PRODUCT_VIDEO_ONE_SCENE_AUTO_RETRY"]:
        blocker = "automatic_retry_forbidden"
    elif flags["PRODUCT_VIDEO_ONE_SCENE_AUTO_FALLBACK"]:
        blocker = "automatic_fallback_forbidden"
    elif request.product_type is not video_engine_contract.VideoProduct.PRODUCT_VIDEO:
        blocker = "product_video_required"
    elif request.mode is not video_engine_contract.VideoEngineMode.SINGLE_SCENE:
        blocker = "one_scene_required"
    elif int(request.approved_plan.get("scene_count") or request.payload.get("scene_count") or 0) != 1:
        blocker = "one_scene_required"
    prompt_state = validate_product_video_prompt(prompt_contract)
    if not blocker and not prompt_state.get("ok"):
        blocker = str(prompt_state.get("blocker") or "prompt_contract_invalid")
    addon_state = validate_product_video_addons(addons)
    if not blocker and not addon_state.get("ok"):
        blocker = str(addon_state.get("blocker") or "addon_contract_invalid")
    shared = video_engine_contract.evaluate_readiness(
        request,
        manifest=manifest,
        runtime_sha=runtime_sha,
        environ=environ,
    )
    if not blocker and not shared.get("ready"):
        blocker = str(shared.get("blocker") or "worker_not_ready")
    capabilities = set(_sequence(manifest.get("capabilities")))
    if not blocker and not set(REQUIRED_WORKER_CAPABILITIES).issubset(capabilities):
        blocker = "worker_capability_mismatch"
    if not blocker and not _flag(manifest.get("artifact_ready")):
        blocker = "worker_artifact_not_ready"
    if not blocker and ENGINE_ADAPTER not in set(_sequence(manifest.get("engine_adapters"))):
        blocker = "worker_adapter_missing"
    if not blocker and request.provider_selection not in set(_sequence(manifest.get("provider_routes"))):
        blocker = "explicit_provider_route_missing"
    if not blocker and request.provider_selection == "fake_provider":
        if public_request or not _flag(manifest.get("offline_fixture")):
            blocker = "fake_provider_offline_only"
    elif not blocker and not flags["PRODUCT_VIDEO_ONE_SCENE_REAL_PROVIDER_ENABLED"]:
        blocker = "real_provider_disabled"
    return {
        "ready": not blocker,
        "submit_allowed": not blocker,
        "blocker": blocker,
        "flags": flags,
        "prompt": prompt_state,
        "addons": addon_state,
        "shared_readiness": shared,
        "route": shared_product_video_one_scene_route(),
    }


@dataclass
class ProductVideoOneSceneLedger:
    jobs_by_idempotency: dict[str, video_engine_contract.VideoEngineJob] = field(
        default_factory=dict
    )
    records_by_job_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    provider_submit_intents: int = 0
    offline_provider_calls: int = 0
    paid_provider_calls: int = 0
    delivery_count: int = 0
    production_telegram_deliveries: int = 0
    receipt_count: int = 0
    charge_attempts: int = 0
    wallet_mutations: int = 0
    success_report_count: int = 0


def _ledger_counters(ledger: ProductVideoOneSceneLedger) -> dict[str, int]:
    return {
        "job_count": len(ledger.jobs_by_idempotency),
        "provider_submit_intents": ledger.provider_submit_intents,
        "offline_provider_calls": ledger.offline_provider_calls,
        "paid_provider_calls": ledger.paid_provider_calls,
        "delivery_count": ledger.delivery_count,
        "production_telegram_deliveries": ledger.production_telegram_deliveries,
        "receipt_count": ledger.receipt_count,
        "charge_attempts": ledger.charge_attempts,
        "wallet_mutations": ledger.wallet_mutations,
        "success_report_count": ledger.success_report_count,
    }


def _job_factory(
    request: video_engine_contract.VideoEngineRequest,
    route: Mapping[str, Any],
) -> video_engine_contract.VideoEngineJob:
    return video_engine_contract.VideoEngineJob(
        job_id=f"p29c-{request.idempotency_key[:24]}",
        request_id=request.request_id,
        idempotency_key=request.idempotency_key,
        product_type=request.product_type,
        mode=request.mode,
        user_id=request.user_id,
        runtime_sha=request.runtime_sha,
        expected_worker_sha=request.expected_worker_sha,
        worker_job_type=_clean(route.get("worker_job_type")),
        engine_route=_clean(route.get("engine_route")),
        worker_owner=_clean(route.get("worker_owner")),
        status="queued",
    )


def _dispatch_result(
    ledger: ProductVideoOneSceneLedger,
    record: Mapping[str, Any] | None,
    *,
    submitted: bool,
    idempotent_replay: bool,
    blocker: str = "",
) -> dict[str, Any]:
    current = dict(record or {})
    provider_state = _clean(
        current.get("provider_state") or ProviderState.NOT_SUBMITTED.value
    )
    state_is_truthfully_active = provider_state in {
        ProviderState.ACCEPTED.value,
        ProviderState.RUNNING.value,
        ProviderState.COMPLETED.value,
    }
    return {
        "ok": bool(current and not blocker and state_is_truthfully_active),
        "submitted": bool(submitted),
        "idempotent_replay": bool(idempotent_replay),
        "blocker": blocker,
        "job_id": _clean(current.get("job_id")),
        "provider_state": provider_state,
        "terminal_state": _clean(current.get("terminal_state")),
        **_ledger_counters(ledger),
    }


def dispatch_product_video_one_scene(
    request: video_engine_contract.VideoEngineRequest,
    *,
    manifest: Mapping[str, Any],
    runtime_sha: str,
    prompt_contract: ProductVideoPromptContract,
    addons: tuple[ProductVideoAddonState, ...],
    environ: Mapping[str, Any] | None,
    ledger: ProductVideoOneSceneLedger,
    submitter: Callable[[dict[str, Any]], Mapping[str, Any]],
    public_request: bool = False,
) -> dict[str, Any]:
    readiness = product_video_one_scene_readiness(
        request,
        manifest=manifest,
        runtime_sha=runtime_sha,
        prompt_contract=prompt_contract,
        addons=addons,
        environ=environ,
        public_request=public_request,
    )
    if not readiness.get("ready"):
        return {
            **_dispatch_result(
                ledger,
                None,
                submitted=False,
                idempotent_replay=False,
                blocker=str(readiness.get("blocker") or "one_scene_not_ready"),
            ),
            "readiness": readiness,
        }
    guarded = video_engine_contract.guarded_submit(
        request,
        manifest=manifest,
        runtime_sha=runtime_sha,
        jobs_by_idempotency=ledger.jobs_by_idempotency,
        submitter=_job_factory,
        environ=environ,
    )
    job = guarded.get("job")
    if not isinstance(job, video_engine_contract.VideoEngineJob):
        return {
            **_dispatch_result(
                ledger,
                None,
                submitted=False,
                idempotent_replay=False,
                blocker=str(guarded.get("blocker") or "engine_job_not_created"),
            ),
            "readiness": readiness,
        }
    record = ledger.records_by_job_id.get(job.job_id)
    if record is None:
        record = {
            "job_id": job.job_id,
            "request": request,
            "prompt_contract": prompt_contract,
            "addons": addons,
            "provider_state": ProviderState.NOT_SUBMITTED.value,
            "provider_task_id": "",
            "provider": request.provider_selection,
            "artifact_path": "",
            "provider_submit_intents": 0,
            "accepted_provider_tasks": 0,
            "render_count": 0,
            "compose_count": 0,
            "terminal_state": "",
            "validation": {},
            "delivery": {},
            "receipt": {},
            "charge": {},
            "terminal_report": {},
        }
        ledger.records_by_job_id[job.job_id] = record
    state = _clean(record.get("provider_state"))
    if state != ProviderState.NOT_SUBMITTED.value:
        return {
            **_dispatch_result(
                ledger,
                record,
                submitted=False,
                idempotent_replay=True,
            ),
            "readiness": readiness,
        }
    record["provider_state"] = ProviderState.SUBMITTING.value
    record["provider_submit_intents"] = 1
    ledger.provider_submit_intents += 1
    if request.provider_selection == "fake_provider":
        ledger.offline_provider_calls += 1
    else:
        ledger.paid_provider_calls += 1
    submit_payload = {
        "route_id": ROUTE_ID,
        "job_id": job.job_id,
        "idempotency_key": request.idempotency_key,
        "product_family": PRODUCT_FAMILY,
        "mode": MODE,
        "scene_count": 1,
        "provider": request.provider_selection,
        "original_user_prompt": prompt_contract.original_user_prompt,
        "compiled_engine_prompt": prompt_contract.compiled_engine_prompt,
        "original_prompt_sha256": prompt_contract.original_prompt_sha256,
        "compiled_prompt_sha256": prompt_contract.compiled_prompt_sha256,
        "approved_plan": dict(request.approved_plan),
        "input_assets": list(request.input_assets),
        "aspect_ratio": request.aspect_ratio,
        "duration_profile": dict(request.duration_profile),
        "addons": [_json_safe(item) for item in addons],
        "automatic_retry": False,
        "automatic_fallback": False,
    }
    try:
        response = dict(submitter(submit_payload) or {})
    except (ProviderAcceptanceUnknown, TimeoutError) as exc:
        record.update(
            {
                "provider_state": ProviderState.ACCEPTANCE_UNKNOWN.value,
                "blocker": "provider_acceptance_unknown",
                "safe_error": type(exc).__name__,
            }
        )
        return {
            **_dispatch_result(
                ledger,
                record,
                submitted=True,
                idempotent_replay=False,
                blocker="provider_acceptance_unknown",
            ),
            "readiness": readiness,
        }
    except Exception as exc:
        record.update(
            {
                "provider_state": ProviderState.FAILED.value,
                "terminal_state": "failed_no_charge",
                "blocker": "provider_submit_failed",
                "safe_error": type(exc).__name__,
            }
        )
        return {
            **_dispatch_result(
                ledger,
                record,
                submitted=True,
                idempotent_replay=False,
                blocker="provider_submit_failed",
            ),
            "readiness": readiness,
        }
    paid = bool(response.get("paid"))
    state_value = _clean(response.get("state")).upper()
    try:
        provider_state = ProviderState(state_value)
    except ValueError:
        provider_state = ProviderState.ACCEPTANCE_UNKNOWN
    provider_task_id = _clean(response.get("provider_task_id"))
    scene_count = _nonnegative_int(response.get("scene_count"), 1)
    render_count = _nonnegative_int(
        response.get("render_count"),
        1 if provider_state is ProviderState.COMPLETED else 0,
    )
    compose_count = _nonnegative_int(
        response.get("compose_count"),
        1 if provider_state is ProviderState.COMPLETED else 0,
    )
    blocker = ""
    if paid and request.provider_selection == "fake_provider":
        blocker = "fake_provider_cannot_be_paid"
    elif scene_count != 1:
        blocker = "provider_hidden_scene_detected"
    elif render_count > 1:
        blocker = "multiple_render_paths_forbidden"
    elif compose_count > 1:
        blocker = "multiple_compositions_forbidden"
    elif provider_state in {
        ProviderState.ACCEPTED,
        ProviderState.RUNNING,
        ProviderState.COMPLETED,
    } and not provider_task_id:
        blocker = "provider_task_identity_missing"
    elif provider_state is ProviderState.FAILED:
        blocker = "provider_failed"
    elif provider_state in {
        ProviderState.NOT_SUBMITTED,
        ProviderState.SUBMITTING,
        ProviderState.ACCEPTANCE_UNKNOWN,
    }:
        provider_state = ProviderState.ACCEPTANCE_UNKNOWN
        blocker = "provider_acceptance_unknown"
    if blocker and blocker != "provider_acceptance_unknown":
        provider_state = ProviderState.FAILED
    terminal_state = (
        "failed_no_charge"
        if blocker and blocker != "provider_acceptance_unknown"
        else ""
    )
    accepted_tasks = 1 if provider_task_id else 0
    record.update(
        {
            "provider_state": provider_state.value,
            "provider_task_id": provider_task_id,
            "provider": _clean(response.get("provider") or request.provider_selection),
            "paid": paid,
            "artifact_path": _clean(response.get("artifact_path")),
            "accepted_provider_tasks": accepted_tasks,
            "render_count": render_count,
            "compose_count": compose_count,
            "blocker": blocker,
            "terminal_state": terminal_state,
        }
    )
    return {
        **_dispatch_result(
            ledger,
            record,
            submitted=True,
            idempotent_replay=False,
            blocker=blocker,
        ),
        "readiness": readiness,
    }


def _ffprobe_details(path: str, ffprobe: str = "") -> dict[str, Any]:
    probe = ffprobe or video_final_output.ffprobe_path()
    if not probe:
        return {"ok": False, "reason": "ffprobe_missing"}
    command = [
        probe,
        "-v",
        "error",
        "-show_entries",
        "format=format_name,duration:stream=codec_type,codec_name,width,height",
        "-of",
        "json",
        path,
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=45)
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "reason": "ffprobe_failed"}
    if completed.returncode != 0:
        return {"ok": False, "reason": "ffprobe_failed"}
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "reason": "ffprobe_invalid_json"}
    streams = [item for item in payload.get("streams") or [] if isinstance(item, dict)]
    video_streams = [item for item in streams if item.get("codec_type") == "video"]
    audio_streams = [item for item in streams if item.get("codec_type") == "audio"]
    video = video_streams[0] if video_streams else {}
    return {
        "ok": bool(video_streams),
        "reason": "" if video_streams else "output_no_video_stream",
        "format_name": _clean((payload.get("format") or {}).get("format_name")),
        "duration": float((payload.get("format") or {}).get("duration") or 0),
        "codec": _clean(video.get("codec_name")).lower(),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "has_audio": bool(audio_streams),
    }


def _full_decode(path: str, ffmpeg: str = "") -> dict[str, Any]:
    binary = ffmpeg or video_final_output.ffmpeg_path()
    if not binary:
        return {"ok": False, "reason": "ffmpeg_missing"}
    command = [binary, "-v", "error", "-i", path, "-f", "null", "-"]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "reason": "full_decode_failed"}
    return {
        "ok": completed.returncode == 0,
        "reason": "" if completed.returncode == 0 else "full_decode_failed",
    }


def _motion_evidence(path: str, ffmpeg: str = "") -> dict[str, Any]:
    binary = ffmpeg or video_final_output.ffmpeg_path()
    if not binary:
        return {"ok": False, "reason": "ffmpeg_missing", "unique_frames": 0}
    command = [
        binary,
        "-v",
        "error",
        "-i",
        path,
        "-map",
        "0:v:0",
        "-vf",
        "fps=4",
        "-frames:v",
        "8",
        "-f",
        "framemd5",
        "-",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "reason": "motion_probe_failed", "unique_frames": 0}
    if completed.returncode != 0:
        return {"ok": False, "reason": "motion_probe_failed", "unique_frames": 0}
    hashes = {
        line.rsplit(",", 1)[-1].strip()
        for line in completed.stdout.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "," in line
    }
    return {
        "ok": len(hashes) > 1,
        "reason": "" if len(hashes) > 1 else "motion_promised_but_static",
        "unique_frames": len(hashes),
    }


def _audio_not_silent(path: str, ffmpeg: str = "") -> dict[str, Any]:
    binary = ffmpeg or video_final_output.ffmpeg_path()
    if not binary:
        return {"ok": False, "reason": "ffmpeg_missing"}
    command = [
        binary,
        "-v",
        "info",
        "-i",
        path,
        "-map",
        "0:a:0",
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "reason": "audio_probe_failed"}
    text = f"{completed.stdout}\n{completed.stderr}"
    match = re.search(r"max_volume:\s*(-?inf|-?[0-9.]+)\s*dB", text, re.IGNORECASE)
    if completed.returncode != 0 or not match:
        return {"ok": False, "reason": "audio_probe_failed"}
    value = match.group(1).lower()
    maximum = float("-inf") if value == "-inf" else float(value)
    return {
        "ok": maximum > -70.0,
        "reason": "" if maximum > -70.0 else "output_audio_silent",
        "max_volume_db": maximum,
    }


def validate_product_video_one_scene_artifact(
    path: str,
    *,
    expected_duration_seconds: int | float,
    motion_promised: bool,
    audio_promised: bool,
    result: Mapping[str, Any] | None = None,
    ffmpeg: str = "",
    ffprobe: str = "",
) -> dict[str, Any]:
    clean_path = _clean(path)
    payload = dict(result or {})
    base = video_final_output.validate_final_video_output(
        path=clean_path,
        result=payload,
        require_audio=bool(audio_promised),
        allow_admin_test=False,
        ffprobe=ffprobe,
    )
    if not base.get("ok"):
        return {**base, "full_decode": False, "motion_valid": False}
    size = int(base.get("bytes") or 0)
    if size < MINIMUM_ARTIFACT_BYTES:
        return {**base, "ok": False, "reason": "output_below_minimum_size"}
    if Path(clean_path).suffix.lower() != ".mp4":
        return {**base, "ok": False, "reason": "output_container_not_mp4"}
    details = _ffprobe_details(clean_path, ffprobe=ffprobe)
    if not details.get("ok"):
        return {**base, **details, "ok": False}
    if "mp4" not in str(details.get("format_name") or "").lower():
        return {**base, **details, "ok": False, "reason": "output_container_not_mp4"}
    if str(details.get("codec") or "") not in ACCEPTED_VIDEO_CODECS:
        return {**base, **details, "ok": False, "reason": "output_codec_unsupported"}
    expected = float(expected_duration_seconds or 0)
    actual = float(details.get("duration") or 0)
    tolerance = max(0.75, expected * 0.20)
    if expected <= 0 or abs(actual - expected) > tolerance:
        return {
            **base,
            **details,
            "ok": False,
            "reason": "output_duration_out_of_tolerance",
            "expected_duration": expected,
            "duration_tolerance": tolerance,
        }
    decode = _full_decode(clean_path, ffmpeg=ffmpeg)
    if not decode.get("ok"):
        return {**base, **details, **decode, "ok": False, "full_decode": False}
    motion = {"ok": True, "unique_frames": 0, "reason": ""}
    if motion_promised:
        motion = _motion_evidence(clean_path, ffmpeg=ffmpeg)
        if not motion.get("ok"):
            return {
                **base,
                **details,
                "ok": False,
                "reason": str(motion.get("reason") or "motion_promised_but_static"),
                "full_decode": True,
                "motion_valid": False,
                "unique_frames": int(motion.get("unique_frames") or 0),
            }
    audio = {"ok": True, "reason": ""}
    if audio_promised:
        audio = _audio_not_silent(clean_path, ffmpeg=ffmpeg)
        if not audio.get("ok"):
            return {
                **base,
                **details,
                **audio,
                "ok": False,
                "full_decode": True,
                "motion_valid": bool(motion.get("ok")),
            }
    return {
        **base,
        **details,
        "ok": True,
        "reason": "",
        "full_decode": True,
        "motion_valid": bool(motion.get("ok")),
        "unique_frames": int(motion.get("unique_frames") or 0),
        "audio_non_silent": bool(audio.get("ok")),
        "expected_duration": expected,
        "duration_tolerance": tolerance,
    }


def _record_for_job(
    ledger: ProductVideoOneSceneLedger,
    job_id: str,
) -> dict[str, Any] | None:
    record = ledger.records_by_job_id.get(_clean(job_id))
    return record if isinstance(record, dict) else None


def _artifact_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_evidence_bundle(
    evidence_dir: Path,
    *,
    record: Mapping[str, Any],
) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    artifact = Path(_clean(record.get("artifact_path")))
    final_path = evidence_dir / "final.mp4"
    scene_path = evidence_dir / "scene_001.mp4"
    if artifact.is_file():
        if artifact.resolve() != final_path.resolve():
            shutil.copy2(artifact, final_path)
        if artifact.resolve() != scene_path.resolve():
            shutil.copy2(artifact, scene_path)
    request = record.get("request")
    prompt = record.get("prompt_contract")
    _write_json(
        evidence_dir / "job_manifest.json",
        {
            "job_id": record.get("job_id"),
            "route_id": ROUTE_ID,
            "product_family": PRODUCT_FAMILY,
            "mode": MODE,
            "scene_count": 1,
            "idempotency_key": getattr(request, "idempotency_key", ""),
            "original_prompt_sha256": getattr(prompt, "original_prompt_sha256", ""),
            "compiled_prompt_sha256": getattr(prompt, "compiled_prompt_sha256", ""),
            "provider_state": record.get("provider_state"),
            "provider_submit_intents": record.get("provider_submit_intents"),
            "accepted_provider_tasks": record.get("accepted_provider_tasks"),
            "render_count": record.get("render_count"),
            "compose_count": record.get("compose_count"),
        },
    )
    _write_json(
        evidence_dir / "scene_001_manifest.json",
        {
            "scene_id": "scene_001",
            "scene_index": 1,
            "scene_count": 1,
            "artifact": "scene_001.mp4",
            "artifact_sha256": _artifact_sha256(str(scene_path)) if scene_path.is_file() else "",
            "status": "validated" if record.get("validation", {}).get("ok") else "unvalidated",
        },
    )
    _write_json(evidence_dir / "validation_report.json", record.get("validation") or {})
    _write_json(evidence_dir / "delivery_receipt.json", record.get("receipt") or {})
    _write_json(evidence_dir / "terminal_report.json", record.get("terminal_report") or {})


def _finalize_result(
    ledger: ProductVideoOneSceneLedger,
    record: Mapping[str, Any],
    *,
    ok: bool,
    blocker: str = "",
    idempotent_replay: bool = False,
) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "blocker": blocker,
        "job_id": _clean(record.get("job_id")),
        "provider_state": _clean(record.get("provider_state")),
        "terminal_state": _clean(record.get("terminal_state")),
        "idempotent_replay": bool(idempotent_replay),
        "validation": dict(record.get("validation") or {}),
        "delivery": dict(record.get("delivery") or {}),
        "receipt": dict(record.get("receipt") or {}),
        "charge": dict(record.get("charge") or {}),
        "terminal_report": dict(record.get("terminal_report") or {}),
        **_ledger_counters(ledger),
    }


def finalize_product_video_one_scene(
    *,
    ledger: ProductVideoOneSceneLedger,
    job_id: str,
    expected_duration_seconds: int | float,
    motion_promised: bool,
    audio_promised: bool,
    deliverer: Callable[[dict[str, Any]], Mapping[str, Any]],
    receipt_persister: Callable[[dict[str, Any]], Mapping[str, Any]],
    charger: Callable[[dict[str, Any]], Mapping[str, Any]],
    terminal_reporter: Callable[[dict[str, Any]], Mapping[str, Any]],
    evidence_dir: str | Path | None = None,
) -> dict[str, Any]:
    record = _record_for_job(ledger, job_id)
    if record is None:
        return {
            "ok": False,
            "blocker": "one_scene_job_not_found",
            "terminal_state": "failed_no_charge",
            "idempotent_replay": False,
            **_ledger_counters(ledger),
        }
    if record.get("terminal_report", {}).get("emitted"):
        return _finalize_result(ledger, record, ok=True, idempotent_replay=True)
    if record.get("provider_state") != ProviderState.COMPLETED.value:
        return _finalize_result(
            ledger,
            record,
            ok=False,
            blocker="provider_not_completed",
        )
    artifact_path = _clean(record.get("artifact_path"))
    if not record.get("validation"):
        record["validation"] = validate_product_video_one_scene_artifact(
            artifact_path,
            expected_duration_seconds=expected_duration_seconds,
            motion_promised=motion_promised,
            audio_promised=audio_promised,
            result={
                "renderer": "fake_provider_fixture"
                if record.get("provider") == "fake_provider"
                else "provider_scene_video",
                "visual_classification": "final_ai_video",
                "scene_count": 1,
            },
        )
    if not record["validation"].get("ok"):
        record["terminal_state"] = "failed_no_charge"
        record["blocker"] = str(
            record["validation"].get("reason") or "final_output_invalid"
        )
        if evidence_dir is not None:
            _write_evidence_bundle(Path(evidence_dir), record=record)
        return _finalize_result(
            ledger,
            record,
            ok=False,
            blocker=record["blocker"],
        )
    artifact_sha = _artifact_sha256(artifact_path)
    if not record.get("delivery", {}).get("accepted"):
        delivery = dict(
            deliverer(
                {
                    "job_id": record["job_id"],
                    "artifact_path": artifact_path,
                    "artifact_sha256": artifact_sha,
                    "idempotency_key": f"delivery:{record['job_id']}:{artifact_sha}",
                    "production": False,
                }
            )
            or {}
        )
        ledger.delivery_count += 1
        if delivery.get("production"):
            ledger.production_telegram_deliveries += 1
        if not delivery.get("accepted") or not _clean(delivery.get("message_id")):
            record["delivery"] = {**delivery, "accepted": False}
            record["blocker"] = "delivery_not_accepted"
            return _finalize_result(
                ledger, record, ok=False, blocker="delivery_not_accepted"
            )
        record["delivery"] = delivery
    if not record.get("receipt", {}).get("persisted"):
        delivered_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        receipt_seed = {
            "job_id": record["job_id"],
            "delivered": True,
            "delivery_idempotency_key": f"delivery:{record['job_id']}:{artifact_sha}",
            "delivery_message_id": _clean(record["delivery"].get("message_id")),
            "output_sha256": artifact_sha,
            "output_bytes": os.path.getsize(artifact_path),
            "delivered_at": delivered_at,
        }
        persisted = dict(receipt_persister(receipt_seed) or {})
        ledger.receipt_count += 1
        if not persisted.get("persisted") or not _clean(persisted.get("receipt_id")):
            record["receipt"] = {**receipt_seed, **persisted, "persisted": False}
            record["blocker"] = "delivery_receipt_not_persisted"
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="delivery_receipt_not_persisted",
            )
        receipt = video_engine_contract.VideoDeliveryReceipt(
            **receipt_seed,
            receipt_id=_clean(persisted.get("receipt_id")),
        )
        if not receipt.valid:
            record["receipt"] = {**receipt_seed, **persisted, "persisted": False}
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="delivery_receipt_invalid",
            )
        record["receipt"] = {**_json_safe(receipt), **persisted, "persisted": True}
    if not record.get("charge", {}).get("recorded"):
        request = record.get("request")
        payload = dict(getattr(request, "payload", {}) or {})
        charge_plan = dict(payload.get("charge_plan") or {})
        admin_no_charge = bool(payload.get("admin_no_charge"))
        amount = 0 if admin_no_charge else int(charge_plan.get("amount_xu") or 0)
        if not admin_no_charge and amount <= 0:
            record["blocker"] = "charge_plan_missing"
            return _finalize_result(
                ledger, record, ok=False, blocker="charge_plan_missing"
            )
        charge_result = dict(
            charger(
                {
                    "job_id": record["job_id"],
                    "amount_xu": amount,
                    "admin_no_charge": admin_no_charge,
                    "receipt_id": record["receipt"].get("receipt_id"),
                    "idempotency_key": f"charge:{record['job_id']}:{amount}",
                }
            )
            or {}
        )
        ledger.charge_attempts += 1
        if charge_result.get("wallet_mutated"):
            ledger.wallet_mutations += 1
        if not charge_result.get("ok"):
            record["charge"] = {**charge_result, "recorded": False}
            record["blocker"] = "charge_not_recorded"
            return _finalize_result(
                ledger, record, ok=False, blocker="charge_not_recorded"
            )
        record["charge"] = {**charge_result, "recorded": True, "amount_xu": amount}
    if not record.get("terminal_report", {}).get("emitted"):
        report = dict(
            terminal_reporter(
                {
                    "job_id": record["job_id"],
                    "terminal_state": "final_delivered",
                    "artifact_sha256": artifact_sha,
                    "receipt_id": record["receipt"].get("receipt_id"),
                    "charge_idempotency_key": f"charge:{record['job_id']}:{record['charge'].get('amount_xu', 0)}",
                    "idempotency_key": f"terminal-report:{record['job_id']}",
                }
            )
            or {}
        )
        if not report.get("emitted") or not _clean(report.get("report_id")):
            record["terminal_report"] = {**report, "emitted": False}
            record["blocker"] = "terminal_report_not_emitted"
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="terminal_report_not_emitted",
            )
        ledger.success_report_count += 1
        record["terminal_report"] = report
    record["terminal_state"] = "final_delivered"
    record["blocker"] = ""
    if evidence_dir is not None:
        _write_evidence_bundle(Path(evidence_dir), record=record)
    return _finalize_result(ledger, record, ok=True)
