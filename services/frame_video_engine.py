"""Default-off deterministic Frame Video engine for ROUTEENGINE29F.

The adapter is transport-free and provider-free. It reuses the existing local
FFmpeg runtime, preserves ordered frame fingerprints, and keeps delivery,
receipt, charge, and terminal-report effects behind injected boundaries.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from services import frame_video_commercial, frame_video_runtime, video_engine_contract


ROUTE_ID = "frame_video_engine_v29f"
PRODUCT_FAMILY = video_engine_contract.VideoProduct.FRAME_VIDEO.value
ENGINE_ADAPTER = "frame_video_local_ffmpeg_v29f"
WORKER_JOB_TYPE = frame_video_commercial.WORKER_JOB_TYPE
WORKER_OWNER = frame_video_commercial.WORKER_OWNER
CANONICAL_WORKER_CAPABILITY = frame_video_commercial.WORKER_CAPABILITY
SUPPORTED_MODES = (
    video_engine_contract.VideoEngineMode.SINGLE_SCENE.value,
    video_engine_contract.VideoEngineMode.MULTI_SCENE.value,
)
UNSUPPORTED_CLAIMS = (
    "3d_orbit",
    "unseen_content_generation",
    "lip_sync",
    "character_animation",
)

FRAME_VIDEO_ENGINE_FLAG_DEFAULTS = {
    "FRAME_VIDEO_ENGINE_ENABLED": False,
    "FRAME_VIDEO_PUBLIC_ALLOWED": False,
    "FRAME_VIDEO_AUTO_RETRY": False,
    "FRAME_VIDEO_AUTO_FALLBACK": False,
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _clean(value).lower() in {"1", "true", "yes", "on"}


def _json_safe(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: _json_safe(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_safe(item) for item in value]
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _json_safe(value),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sequence(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if not isinstance(value, (list, tuple, set, frozenset)):
        return ()
    return tuple(_clean(item) for item in value if _clean(item))


def _mode(value: Any) -> str:
    token = _clean(value).lower()
    if token not in SUPPORTED_MODES:
        raise ValueError("frame_mode_unsupported")
    return token


def _custom_dimensions(width: Any, height: Any) -> tuple[int, int]:
    try:
        parsed_width = int(width)
        parsed_height = int(height)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("frame_custom_dimensions_invalid") from exc
    if isinstance(width, bool) or isinstance(height, bool):
        raise ValueError("frame_custom_dimensions_invalid")
    parsed_width = min(4096, parsed_width) - min(4096, parsed_width) % 2
    parsed_height = min(4096, parsed_height) - min(4096, parsed_height) % 2
    if parsed_width < 100 or parsed_height < 100:
        raise ValueError("frame_custom_dimensions_invalid")
    return parsed_width, parsed_height


def _aspect_ratio(value: Any, custom_width: Any = 0, custom_height: Any = 0) -> str:
    token = _clean(value).lower().replace("x", ":")
    if token == "custom":
        _custom_dimensions(custom_width, custom_height)
        return token
    if token not in {"9:16", "16:9", "1:1", "4:5"}:
        raise ValueError("frame_aspect_ratio_unsupported")
    return token


def _duration(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("frame_duration_invalid")
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("frame_duration_invalid") from exc
    if not math.isfinite(parsed) or parsed < 0.5 or parsed > 30.0:
        raise ValueError("frame_duration_invalid")
    return round(parsed, 3)


def frame_video_engine_flags(
    environ: Mapping[str, Any] | None = None,
) -> dict[str, bool]:
    source = os.environ if environ is None else environ
    return {
        name: _flag(source.get(name, default))
        for name, default in FRAME_VIDEO_ENGINE_FLAG_DEFAULTS.items()
    }


def shared_frame_video_engine_route() -> dict[str, Any]:
    return {
        "product": PRODUCT_FAMILY,
        "state": video_engine_contract.VideoRouteState.CONNECTED.value,
        "connected": True,
        "public_product_type": frame_video_commercial.PUBLIC_JOB_TYPE,
        "worker_job_type": WORKER_JOB_TYPE,
        "engine_route": ENGINE_ADAPTER,
        "worker_owner": WORKER_OWNER,
        "required_capability": CANONICAL_WORKER_CAPABILITY,
        "required_capabilities": (CANONICAL_WORKER_CAPABILITY,),
        "supported_modes": SUPPORTED_MODES,
        "provider_enabled": False,
        "local_enabled": True,
        "route_id": ROUTE_ID,
        "blocker": "",
    }


def frame_video_engine_contract(
    environ: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "route_id": ROUTE_ID,
        "product_family": PRODUCT_FAMILY,
        "engine_adapter": ENGINE_ADAPTER,
        "supported_modes": SUPPORTED_MODES,
        "provider_required": False,
        "cloud_provider_calls": 0,
        "automatic_retry": False,
        "automatic_fallback": False,
        "single_frame_minimum": 1,
        "multi_frame_minimum": 2,
        "maximum_frames": frame_video_runtime.FRAME_VIDEO_MAX_IMAGES,
        "unsupported_claims": UNSUPPORTED_CLAIMS,
        "artifact_promise": {
            "container": "mp4",
            "video_stream": True,
            "full_decode": True,
            "audio_when_promised": True,
            "ordered_frames": True,
        },
        "flags": frame_video_engine_flags(environ),
    }


@dataclass(frozen=True)
class FrameVideoFrame:
    frame_index: int
    asset_id: str
    source_path: str
    source_sha256: str
    source_bytes: int
    duration_seconds: float
    motion: str


@dataclass(frozen=True)
class FrameVideoPlan:
    mode: str
    frames: tuple[FrameVideoFrame, ...]
    aspect_ratio: str
    custom_width: int
    custom_height: int
    transition: str
    transition_seconds: float
    transition_manifest: tuple[Mapping[str, Any], ...]
    text_overlays: tuple[Mapping[str, Any], ...]
    audio_policy: Mapping[str, Any]
    voice_policy: Mapping[str, Any]
    frame_order_sha256: str
    expected_duration_seconds: float
    plan_sha256: str


def _frame_order_material(frames: tuple[FrameVideoFrame, ...]) -> list[dict[str, Any]]:
    return [
        {
            "frame_index": frame.frame_index,
            "asset_id": frame.asset_id,
            "source_sha256": frame.source_sha256,
        }
        for frame in frames
    ]


def _plan_material(plan: FrameVideoPlan) -> dict[str, Any]:
    return {
        "mode": plan.mode,
        "frames": [
            {
                "frame_index": frame.frame_index,
                "asset_id": frame.asset_id,
                "source_sha256": frame.source_sha256,
                "source_bytes": frame.source_bytes,
                "duration_seconds": frame.duration_seconds,
                "motion": frame.motion,
            }
            for frame in plan.frames
        ],
        "aspect_ratio": plan.aspect_ratio,
        "custom_width": plan.custom_width,
        "custom_height": plan.custom_height,
        "transition": plan.transition,
        "transition_seconds": plan.transition_seconds,
        "transition_manifest": [_json_safe(item) for item in plan.transition_manifest],
        "text_overlays": [_json_safe(item) for item in plan.text_overlays],
        "audio_policy": _json_safe(plan.audio_policy),
        "voice_policy": _json_safe(plan.voice_policy),
        "frame_order_sha256": plan.frame_order_sha256,
        "expected_duration_seconds": plan.expected_duration_seconds,
    }


def _plan_sha256(plan: FrameVideoPlan) -> str:
    return _sha256_text(_canonical_json(_plan_material(plan)))


def compile_frame_video_plan(
    *,
    frames: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    mode: str,
    aspect_ratio: str = "9:16",
    custom_width: Any = 0,
    custom_height: Any = 0,
    transition: str = "fade",
    transition_seconds: float = 0.35,
    text_overlays: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] = (),
    audio_policy: Mapping[str, Any] | None = None,
    voice_policy: Mapping[str, Any] | None = None,
) -> FrameVideoPlan:
    selected_mode = _mode(mode)
    raw_frames = tuple(frames or ())
    if not raw_frames:
        raise ValueError("frame_asset_required")
    if len(raw_frames) > frame_video_runtime.FRAME_VIDEO_MAX_IMAGES:
        raise ValueError("too_many_frames")
    if selected_mode == video_engine_contract.VideoEngineMode.SINGLE_SCENE.value:
        if len(raw_frames) != 1:
            raise ValueError("single_frame_mode_requires_one_frame")
    elif len(raw_frames) < 2:
        raise ValueError("multi_frame_mode_requires_multiple_frames")

    compiled: list[FrameVideoFrame] = []
    asset_ids: set[str] = set()
    fingerprints: set[str] = set()
    for ordinal, raw in enumerate(raw_frames, start=1):
        if not isinstance(raw, Mapping):
            raise ValueError("frame_asset_invalid")
        declared_index = raw.get("frame_index")
        if declared_index is not None:
            try:
                parsed_index = int(declared_index)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("frame_order_invalid") from exc
            if (
                isinstance(declared_index, bool)
                or (
                    isinstance(declared_index, float)
                    and not declared_index.is_integer()
                )
                or parsed_index != ordinal
            ):
                raise ValueError("frame_order_invalid")
        asset_id = _clean(raw.get("asset_id"))
        if not asset_id:
            raise ValueError("frame_asset_id_required")
        if asset_id in asset_ids:
            raise ValueError("duplicate_frame_asset_id")
        path = Path(_clean(raw.get("source_path"))).expanduser()
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError("frame_asset_missing")
        resolved = str(path.resolve())
        fingerprint = _sha256_file(resolved)
        if fingerprint in fingerprints:
            raise ValueError("duplicate_frame_fingerprint")
        motion = _clean(raw.get("motion") or "none").lower()
        if motion not in frame_video_runtime.MOTIONS:
            raise ValueError("frame_motion_unsupported")
        compiled.append(
            FrameVideoFrame(
                frame_index=ordinal,
                asset_id=asset_id,
                source_path=resolved,
                source_sha256=fingerprint,
                source_bytes=path.stat().st_size,
                duration_seconds=_duration(
                    raw["duration_seconds"] if "duration_seconds" in raw else 3.0
                ),
                motion=motion,
            )
        )
        asset_ids.add(asset_id)
        fingerprints.add(fingerprint)

    selected_transition = _clean(transition or "fade").lower()
    selected_transition = {
        "cut": "none",
        "natural": "none",
        "default": "fade",
    }.get(selected_transition, selected_transition)
    if selected_transition not in frame_video_runtime.TRANSITIONS:
        raise ValueError("frame_transition_unsupported")
    overlap = 0.0
    if len(compiled) > 1 and selected_transition != "none":
        try:
            requested_overlap = float(transition_seconds)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("frame_transition_duration_invalid") from exc
        if not math.isfinite(requested_overlap) or requested_overlap <= 0:
            raise ValueError("frame_transition_duration_invalid")
        overlap = round(
            min(1.5, requested_overlap, min(item.duration_seconds for item in compiled) / 2.0),
            3,
        )
    transitions = tuple(
        {
            "transition_index": index,
            "from_asset_id": left.asset_id,
            "to_asset_id": right.asset_id,
            "type": selected_transition,
            "duration_seconds": overlap,
        }
        for index, (left, right) in enumerate(
            zip(compiled, compiled[1:]),
            start=1,
        )
        if selected_transition != "none"
    )
    normalized_overlays = tuple(
        _json_safe(item) for item in tuple(text_overlays or ()) if isinstance(item, Mapping)
    )
    order_sha = _sha256_text(_canonical_json(_frame_order_material(tuple(compiled))))
    expected_duration = round(
        sum(item.duration_seconds for item in compiled) - overlap * len(transitions),
        3,
    )
    selected_aspect_ratio = _aspect_ratio(
        aspect_ratio,
        custom_width=custom_width,
        custom_height=custom_height,
    )
    selected_custom_width = 0
    selected_custom_height = 0
    if selected_aspect_ratio == "custom":
        selected_custom_width, selected_custom_height = _custom_dimensions(
            custom_width,
            custom_height,
        )
    provisional = FrameVideoPlan(
        mode=selected_mode,
        frames=tuple(compiled),
        aspect_ratio=selected_aspect_ratio,
        custom_width=selected_custom_width,
        custom_height=selected_custom_height,
        transition=selected_transition,
        transition_seconds=overlap,
        transition_manifest=transitions,
        text_overlays=normalized_overlays,
        audio_policy=_json_safe(dict(audio_policy or {})),
        voice_policy=_json_safe(dict(voice_policy or {})),
        frame_order_sha256=order_sha,
        expected_duration_seconds=expected_duration,
        plan_sha256="",
    )
    return replace(provisional, plan_sha256=_plan_sha256(provisional))


def replace_plan(plan: FrameVideoPlan, **changes: Any) -> FrameVideoPlan:
    return replace(plan, **changes)


def validate_frame_video_plan(plan: FrameVideoPlan) -> dict[str, Any]:
    if not isinstance(plan, FrameVideoPlan):
        return {"ok": False, "blocker": "frame_plan_required"}
    if _plan_sha256(plan) != plan.plan_sha256:
        return {"ok": False, "blocker": "frame_plan_hash_mismatch"}
    if plan.mode not in SUPPORTED_MODES:
        return {"ok": False, "blocker": "frame_mode_unsupported"}
    count = len(plan.frames)
    if plan.mode == video_engine_contract.VideoEngineMode.SINGLE_SCENE.value and count != 1:
        return {"ok": False, "blocker": "single_frame_mode_requires_one_frame"}
    if plan.mode == video_engine_contract.VideoEngineMode.MULTI_SCENE.value and count < 2:
        return {"ok": False, "blocker": "multi_frame_mode_requires_multiple_frames"}
    if count > frame_video_runtime.FRAME_VIDEO_MAX_IMAGES:
        return {"ok": False, "blocker": "too_many_frames"}
    if plan.aspect_ratio == "custom":
        try:
            normalized_dimensions = _custom_dimensions(
                plan.custom_width,
                plan.custom_height,
            )
        except ValueError:
            return {"ok": False, "blocker": "frame_custom_dimensions_invalid"}
        if normalized_dimensions != (plan.custom_width, plan.custom_height):
            return {"ok": False, "blocker": "frame_custom_dimensions_invalid"}
    elif plan.custom_width or plan.custom_height:
        return {"ok": False, "blocker": "frame_custom_dimensions_invalid"}
    if (
        not math.isfinite(plan.transition_seconds)
        or plan.transition_seconds < 0
        or not math.isfinite(plan.expected_duration_seconds)
        or plan.expected_duration_seconds <= 0
    ):
        return {"ok": False, "blocker": "frame_duration_invalid"}
    if [frame.frame_index for frame in plan.frames] != list(range(1, count + 1)):
        return {"ok": False, "blocker": "frame_order_invalid"}
    asset_ids = [frame.asset_id for frame in plan.frames]
    fingerprints = [frame.source_sha256 for frame in plan.frames]
    if len(set(asset_ids)) != count:
        return {"ok": False, "blocker": "duplicate_frame_asset_id"}
    if len(set(fingerprints)) != count:
        return {"ok": False, "blocker": "duplicate_frame_fingerprint"}
    expected_order_sha = _sha256_text(
        _canonical_json(_frame_order_material(plan.frames))
    )
    if expected_order_sha != plan.frame_order_sha256:
        return {"ok": False, "blocker": "frame_order_hash_mismatch"}
    for frame in plan.frames:
        if not math.isfinite(frame.duration_seconds):
            return {"ok": False, "blocker": "frame_duration_invalid"}
        path = Path(frame.source_path)
        if not path.is_file() or path.stat().st_size <= 0:
            return {"ok": False, "blocker": "frame_asset_missing"}
        if _sha256_file(path) != frame.source_sha256:
            return {"ok": False, "blocker": "frame_asset_fingerprint_mismatch"}
    expected_transitions = max(0, count - 1) if plan.transition != "none" else 0
    if len(plan.transition_manifest) != expected_transitions:
        return {"ok": False, "blocker": "frame_transition_manifest_mismatch"}
    return {
        "ok": True,
        "blocker": "",
        "frame_count": count,
        "frame_order": asset_ids,
        "frame_order_sha256": plan.frame_order_sha256,
        "plan_sha256": plan.plan_sha256,
        "expected_duration_seconds": plan.expected_duration_seconds,
        "transition_count": len(plan.transition_manifest),
    }


def build_frame_video_request(
    *,
    user_id: int,
    confirmation_id: str,
    language: str,
    plan: FrameVideoPlan,
    explicit_confirmation_receipt: Mapping[str, Any],
    runtime_sha: str,
    expected_worker_sha: str,
    admin_no_charge: bool = False,
    charge_plan: Mapping[str, Any] | None = None,
) -> video_engine_contract.VideoEngineRequest:
    validation = validate_frame_video_plan(plan)
    if not validation.get("ok"):
        raise ValueError(str(validation.get("blocker") or "frame_plan_invalid"))
    mode = video_engine_contract.VideoEngineMode(plan.mode)
    payload = {
        "route_id": ROUTE_ID,
        "plan_sha256": plan.plan_sha256,
        "frame_order_sha256": plan.frame_order_sha256,
        "frame_count": len(plan.frames),
        "transition_count": len(plan.transition_manifest),
        "admin_no_charge": bool(admin_no_charge),
        "charge_plan": _json_safe(dict(charge_plan or {})),
        "provider_calls": 0,
        "automatic_retry": False,
        "automatic_fallback": False,
    }
    input_assets = tuple(
        {
            "frame_index": frame.frame_index,
            "asset_id": frame.asset_id,
            "source_sha256": frame.source_sha256,
            "source_bytes": frame.source_bytes,
        }
        for frame in plan.frames
    )
    common = {
        "user_id": user_id,
        "language": language,
        "approved_plan": {
            "route_id": ROUTE_ID,
            "approved": True,
            "mode": plan.mode,
            "frame_count": len(plan.frames),
            "plan_sha256": plan.plan_sha256,
            "frame_order_sha256": plan.frame_order_sha256,
        },
        "input_assets": input_assets,
        "aspect_ratio": plan.aspect_ratio,
        "duration_profile": {
            "duration_seconds": plan.expected_duration_seconds,
            "profile": "frame_video_local",
        },
        "audio_policy": dict(plan.audio_policy),
        "voice_policy": dict(plan.voice_policy),
        "provider_selection": "local",
        "runtime_sha": runtime_sha,
        "expected_worker_sha": expected_worker_sha,
    }
    key = video_engine_contract.stable_request_idempotency_key(
        confirmation_id=confirmation_id,
        product_type=video_engine_contract.VideoProduct.FRAME_VIDEO,
        mode=mode,
        payload=payload,
        **common,
    )
    return video_engine_contract.VideoEngineRequest(
        request_id=f"{ROUTE_ID}:{key[:20]}",
        confirmation_id=confirmation_id,
        idempotency_key=key,
        product_type=video_engine_contract.VideoProduct.FRAME_VIDEO,
        mode=mode,
        explicit_confirmation_receipt=dict(explicit_confirmation_receipt),
        confirmed=True,
        payload=payload,
        **common,
    )


def _promised_audio_policies(plan: FrameVideoPlan) -> tuple[dict[str, Any], ...]:
    return tuple(
        dict(policy)
        for policy in (plan.audio_policy, plan.voice_policy)
        if _flag(policy.get("promised"))
    )


def frame_video_engine_readiness(
    request: video_engine_contract.VideoEngineRequest,
    *,
    plan: FrameVideoPlan,
    manifest: Mapping[str, Any],
    runtime_sha: str,
    environ: Mapping[str, Any] | None = None,
    public_request: bool = False,
) -> dict[str, Any]:
    flags = frame_video_engine_flags(environ)
    blocker = ""
    if not flags["FRAME_VIDEO_ENGINE_ENABLED"]:
        blocker = "frame_video_engine_disabled"
    elif public_request and not flags["FRAME_VIDEO_PUBLIC_ALLOWED"]:
        blocker = "frame_video_public_disabled"
    elif flags["FRAME_VIDEO_AUTO_RETRY"]:
        blocker = "automatic_retry_forbidden"
    elif flags["FRAME_VIDEO_AUTO_FALLBACK"]:
        blocker = "automatic_fallback_forbidden"
    elif request.product_type is not video_engine_contract.VideoProduct.FRAME_VIDEO:
        blocker = "frame_video_product_required"
    elif request.mode.value != plan.mode:
        blocker = "frame_video_mode_mismatch"
    plan_validation = validate_frame_video_plan(plan)
    if not blocker and not plan_validation.get("ok"):
        blocker = str(plan_validation.get("blocker") or "frame_plan_invalid")
    if not blocker and len(_promised_audio_policies(plan)) > 1:
        blocker = "multiple_promised_audio_assets_unsupported"
    if not blocker and request.payload.get("plan_sha256") != plan.plan_sha256:
        blocker = "frame_request_plan_mismatch"
    shared = video_engine_contract.evaluate_readiness(
        request,
        manifest=manifest,
        runtime_sha=runtime_sha,
        environ=environ,
    )
    if not blocker and not shared.get("ready"):
        blocker = str(shared.get("blocker") or "worker_not_ready")
    if not blocker and ENGINE_ADAPTER not in set(_sequence(manifest.get("engine_adapters"))):
        blocker = "worker_adapter_missing"
    if not blocker and not _flag(manifest.get("artifact_ready")):
        blocker = "worker_artifact_not_ready"
    return {
        "ready": not blocker,
        "submit_allowed": not blocker,
        "blocker": blocker,
        "flags": flags,
        "plan": plan_validation,
        "shared_readiness": shared,
        "route": shared_frame_video_engine_route(),
        "provider_calls": 0,
    }


@dataclass
class FrameVideoEngineLedger:
    jobs_by_idempotency: dict[str, video_engine_contract.VideoEngineJob] = field(
        default_factory=dict
    )
    records_by_job_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    render_count: int = 0
    compose_count: int = 0
    provider_calls: int = 0
    paid_provider_calls: int = 0
    delivery_count: int = 0
    production_telegram_deliveries: int = 0
    receipt_count: int = 0
    charge_attempts: int = 0
    wallet_mutations: int = 0
    terminal_report_count: int = 0


def _ledger_counters(ledger: FrameVideoEngineLedger) -> dict[str, int]:
    return {
        "job_count": len(ledger.jobs_by_idempotency),
        "render_count": ledger.render_count,
        "compose_count": ledger.compose_count,
        "provider_calls": ledger.provider_calls,
        "paid_provider_calls": ledger.paid_provider_calls,
        "delivery_count": ledger.delivery_count,
        "production_telegram_deliveries": ledger.production_telegram_deliveries,
        "receipt_count": ledger.receipt_count,
        "charge_attempts": ledger.charge_attempts,
        "wallet_mutations": ledger.wallet_mutations,
        "terminal_report_count": ledger.terminal_report_count,
    }


def _job_factory(
    request: video_engine_contract.VideoEngineRequest,
    route: Mapping[str, Any],
) -> video_engine_contract.VideoEngineJob:
    return video_engine_contract.VideoEngineJob(
        job_id=f"p29f-{request.idempotency_key[:24]}",
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
    ledger: FrameVideoEngineLedger,
    record: Mapping[str, Any] | None,
    *,
    submitted: bool,
    idempotent_replay: bool,
    blocker: str = "",
) -> dict[str, Any]:
    current = dict(record or {})
    return {
        "ok": bool(current and not blocker),
        "submitted": bool(submitted),
        "idempotent_replay": bool(idempotent_replay),
        "blocker": blocker,
        "job_id": _clean(current.get("job_id")),
        "terminal_state": _clean(current.get("terminal_state")),
        **_ledger_counters(ledger),
    }


def dispatch_frame_video(
    request: video_engine_contract.VideoEngineRequest,
    *,
    plan: FrameVideoPlan,
    manifest: Mapping[str, Any],
    runtime_sha: str,
    ledger: FrameVideoEngineLedger,
    environ: Mapping[str, Any] | None,
    public_request: bool = False,
) -> dict[str, Any]:
    readiness = frame_video_engine_readiness(
        request,
        plan=plan,
        manifest=manifest,
        runtime_sha=runtime_sha,
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
                blocker=str(readiness.get("blocker") or "frame_video_not_ready"),
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
                blocker=str(guarded.get("blocker") or "frame_job_not_created"),
            ),
            "readiness": readiness,
        }
    record = ledger.records_by_job_id.get(job.job_id)
    if record is None:
        record = {
            "job_id": job.job_id,
            "request": request,
            "plan": plan,
            "render_attempted": False,
            "artifact_path": "",
            "artifact_sha256": "",
            "output_bytes": 0,
            "terminal_state": "queued",
            "blocker": "",
            "validation": {},
            "delivery": {},
            "receipt": {},
            "charge": {},
            "terminal_report": {},
        }
        ledger.records_by_job_id[job.job_id] = record
    return {
        **_dispatch_result(
            ledger,
            record,
            submitted=bool(guarded.get("submitted")),
            idempotent_replay=bool(guarded.get("idempotent_replay")),
        ),
        "readiness": readiness,
    }


def _execution_result(
    ledger: FrameVideoEngineLedger,
    record: Mapping[str, Any],
    *,
    ok: bool,
    blocker: str = "",
    idempotent_replay: bool = False,
) -> dict[str, Any]:
    validation = dict(record.get("validation") or {})
    return {
        "ok": bool(ok),
        "blocker": blocker,
        "job_id": _clean(record.get("job_id")),
        "terminal_state": _clean(record.get("terminal_state")),
        "idempotent_replay": bool(idempotent_replay),
        "output_path": _clean(record.get("artifact_path")),
        "output_bytes": int(record.get("output_bytes") or 0),
        "output_sha256": _clean(record.get("artifact_sha256")),
        "validation": validation,
        "command": list(record.get("command") or []),
        **_ledger_counters(ledger),
    }


def _fail_record(
    ledger: FrameVideoEngineLedger,
    record: dict[str, Any],
    blocker: str,
    *,
    idempotent_replay: bool = False,
) -> dict[str, Any]:
    record["blocker"] = blocker
    record["terminal_state"] = "failed_no_charge"
    return _execution_result(
        ledger,
        record,
        ok=False,
        blocker=blocker,
        idempotent_replay=idempotent_replay,
    )


def _full_decode(path: str, ffmpeg_path: str) -> dict[str, Any]:
    command = [ffmpeg_path, "-v", "error", "-i", path, "-f", "null", "-"]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "blocker": "frame_full_decode_failed"}
    return {
        "ok": completed.returncode == 0,
        "blocker": "" if completed.returncode == 0 else "frame_full_decode_failed",
    }


def _audio_promise(plan: FrameVideoPlan) -> dict[str, Any]:
    promised = _promised_audio_policies(plan)
    return promised[0] if promised else {}


def execute_frame_video_local(
    request: video_engine_contract.VideoEngineRequest,
    *,
    plan: FrameVideoPlan,
    manifest: Mapping[str, Any],
    runtime_sha: str,
    ledger: FrameVideoEngineLedger,
    output_root: str | Path,
    asset_paths: Mapping[str, str],
    environ: Mapping[str, Any] | None,
    audio_path: str = "",
    audio_paths: Mapping[str, str] | None = None,
    logo_path: str = "",
    render_state: Mapping[str, Any] | None = None,
    output_path: str | Path | None = None,
    ffmpeg_path: str = "",
    ffprobe_path: str = "",
    public_request: bool = False,
) -> dict[str, Any]:
    dispatched = dispatch_frame_video(
        request,
        plan=plan,
        manifest=manifest,
        runtime_sha=runtime_sha,
        ledger=ledger,
        environ=environ,
        public_request=public_request,
    )
    if dispatched.get("blocker"):
        return dispatched
    record = ledger.records_by_job_id.get(_clean(dispatched.get("job_id")))
    if not isinstance(record, dict):
        return {
            **dispatched,
            "ok": False,
            "blocker": "frame_job_record_missing",
            "terminal_state": "failed_no_charge",
        }
    if record.get("validation", {}).get("ok"):
        artifact = Path(_clean(record.get("artifact_path")))
        if (
            artifact.is_file()
            and artifact.stat().st_size == int(record.get("output_bytes") or 0)
            and _sha256_file(artifact) == record.get("artifact_sha256")
        ):
            return _execution_result(
                ledger,
                record,
                ok=True,
                idempotent_replay=True,
            )
        return _fail_record(
            ledger,
            record,
            "frame_artifact_changed_after_validation",
            idempotent_replay=True,
        )
    if record.get("render_attempted"):
        return _fail_record(
            ledger,
            record,
            _clean(record.get("blocker") or "frame_render_not_retriable"),
            idempotent_replay=True,
        )

    record["render_attempted"] = True
    ordered_paths: list[str] = []
    for frame in plan.frames:
        selected = _clean(asset_paths.get(frame.asset_id))
        path = Path(selected)
        if not selected or not path.is_file() or path.stat().st_size <= 0:
            return _fail_record(ledger, record, "frame_asset_missing")
        if _sha256_file(path) != frame.source_sha256:
            return _fail_record(ledger, record, "frame_asset_fingerprint_mismatch")
        ordered_paths.append(str(path.resolve()))

    promised_audio = _audio_promise(plan)
    supplied_audio = {
        _clean(kind).lower(): _clean(path)
        for kind, path in dict(audio_paths or {}).items()
        if _clean(kind)
    }
    selected_audio: dict[str, str] = {}
    promised_components = [
        dict(component)
        for component in list(promised_audio.get("components") or [])
        if isinstance(component, Mapping)
    ]
    if promised_components:
        for component in promised_components:
            kind = _clean(component.get("kind")).lower()
            if kind not in {"music", "voice"} or kind in selected_audio:
                return _fail_record(ledger, record, "promised_audio_component_invalid")
            selected = supplied_audio.get(kind) or (
                _clean(audio_path) if len(promised_components) == 1 else ""
            )
            path = Path(selected)
            if not selected or not path.is_file() or path.stat().st_size <= 0:
                return _fail_record(ledger, record, f"promised_{kind}_missing")
            expected_audio_sha = _clean(component.get("sha256")).lower()
            if expected_audio_sha and _sha256_file(path) != expected_audio_sha:
                return _fail_record(
                    ledger,
                    record,
                    f"promised_{kind}_fingerprint_mismatch",
                )
            selected_audio[kind] = str(path.resolve())
    elif promised_audio:
        selected = _clean(audio_path)
        path = Path(selected)
        if not selected or not path.is_file() or path.stat().st_size <= 0:
            return _fail_record(ledger, record, "promised_audio_missing")
        expected_audio_sha = _clean(promised_audio.get("sha256")).lower()
        if expected_audio_sha and _sha256_file(path) != expected_audio_sha:
            return _fail_record(ledger, record, "promised_audio_fingerprint_mismatch")
        selected_audio["voice"] = str(path.resolve())

    selected_logo = _clean(logo_path)
    logo_contract = next(
        (
            dict(item)
            for item in plan.text_overlays
            if _clean(item.get("kind")) == "frame_public_runtime_contract"
        ),
        {},
    )
    expected_logo_sha = _clean(logo_contract.get("logo_sha256")).lower()
    if expected_logo_sha:
        path = Path(selected_logo)
        if not selected_logo or not path.is_file() or path.stat().st_size <= 0:
            return _fail_record(ledger, record, "promised_logo_missing")
        if _sha256_file(path) != expected_logo_sha:
            return _fail_record(ledger, record, "promised_logo_fingerprint_mismatch")
        selected_logo = str(path.resolve())

    ffmpeg = ffmpeg_path or shutil.which("ffmpeg") or ""
    ffprobe = ffprobe_path or shutil.which("ffprobe") or ""
    if not ffmpeg:
        return _fail_record(ledger, record, "ffmpeg_missing")
    if not ffprobe:
        return _fail_record(ledger, record, "ffprobe_missing")

    photos = [
        {
            "file_id": frame.asset_id,
            "file_unique_id": frame.source_sha256,
            "file_name": Path(frame.source_path).name,
            "file_size": frame.source_bytes,
            "mime_type": "image/png",
            "source": "frame_video_engine_29f",
        }
        for frame in plan.frames
    ]
    runtime_manifest = frame_video_runtime.canonical_image_manifest(photos)
    image_durations = {
        row["image_id"]: frame.duration_seconds
        for row, frame in zip(runtime_manifest, plan.frames)
    }
    image_motions = {
        row["image_id"]: frame.motion
        for row, frame in zip(runtime_manifest, plan.frames)
    }
    state = dict(render_state or {})
    state.update({
        "photos": photos,
        "image_count": len(photos),
        "ratio": plan.aspect_ratio,
        "custom_width": plan.custom_width,
        "custom_height": plan.custom_height,
        "fit_mode": _clean(state.get("fit_mode") or "contain"),
        "background_color": _clean(state.get("background_color") or "#111111"),
        "seconds_per_image": plan.frames[0].duration_seconds,
        "image_durations": image_durations,
        "transition": plan.transition,
        "transition_seconds": plan.transition_seconds or 0.1,
        "motion": plan.frames[0].motion,
        "image_motions": image_motions,
        "quality": _clean(state.get("quality") or "fast"),
        "text_overlays": list(plan.text_overlays),
    })
    for component in promised_components:
        kind = _clean(component.get("kind")).lower()
        state[f"{kind}_volume_percent"] = component.get("volume_percent")
        state[f"{kind}_fade_seconds"] = component.get("fade_seconds")
    if output_path is None:
        destination = Path(output_root) / record["job_id"]
        destination.mkdir(parents=True, exist_ok=True)
        selected_output_path = destination / "final.mp4"
    else:
        selected_output_path = Path(output_path)
        selected_output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        command = frame_video_runtime.build_ffmpeg_command(
            ordered_paths,
            str(selected_output_path),
            state,
            ffmpeg_path=ffmpeg,
            music_path=selected_audio.get("music", ""),
            voice_path=selected_audio.get("voice", ""),
            logo_path=selected_logo,
            min_images=1,
        )
    except ValueError as exc:
        return _fail_record(ledger, record, _clean(exc) or "frame_plan_invalid")

    record["command"] = list(command.command)
    ledger.render_count += 1
    ledger.compose_count += 1
    try:
        completed = subprocess.run(
            command.command,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        record["safe_error"] = type(exc).__name__
        return _fail_record(ledger, record, "frame_render_failed")
    if completed.returncode != 0:
        record["safe_error"] = _clean(completed.stderr)[-500:]
        return _fail_record(ledger, record, "frame_render_failed")

    probe = frame_video_runtime.probe_mp4(
        str(selected_output_path),
        command.expected_duration,
        expects_audio=bool(promised_audio),
        ffprobe_path=ffprobe,
    )
    if not probe.get("ok"):
        record["validation"] = {
            **probe,
            "ok": False,
            "full_decode": False,
            "frame_order": [frame.asset_id for frame in plan.frames],
            "transition_count": len(plan.transition_manifest),
            "compose_count": 1,
        }
        return _fail_record(
            ledger,
            record,
            _clean(probe.get("reason") or "frame_artifact_invalid"),
        )
    decode = _full_decode(str(selected_output_path), ffmpeg)
    if not decode.get("ok"):
        record["validation"] = {**probe, "ok": False, "full_decode": False}
        return _fail_record(
            ledger,
            record,
            _clean(decode.get("blocker") or "frame_full_decode_failed"),
        )
    artifact_sha = _sha256_file(selected_output_path)
    output_bytes = selected_output_path.stat().st_size
    record.update(
        {
            "artifact_path": str(selected_output_path),
            "artifact_sha256": artifact_sha,
            "output_bytes": output_bytes,
            "terminal_state": "rendered_validated",
            "blocker": "",
            "validation": {
                **probe,
                "ok": True,
                "full_decode": True,
                "frame_order": [frame.asset_id for frame in plan.frames],
                "frame_fingerprints": [
                    frame.source_sha256 for frame in plan.frames
                ],
                "transition_count": len(plan.transition_manifest),
                "compose_count": 1,
                "plan_sha256": plan.plan_sha256,
                "artifact_sha256": artifact_sha,
            },
        }
    )
    return _execution_result(ledger, record, ok=True)


def _finalize_result(
    ledger: FrameVideoEngineLedger,
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
        "terminal_state": _clean(record.get("terminal_state")),
        "idempotent_replay": bool(idempotent_replay),
        "delivery": dict(record.get("delivery") or {}),
        "receipt": dict(record.get("receipt") or {}),
        "charge": dict(record.get("charge") or {}),
        "terminal_report": dict(record.get("terminal_report") or {}),
        **_ledger_counters(ledger),
    }


def finalize_frame_video(
    *,
    ledger: FrameVideoEngineLedger,
    job_id: str,
    deliverer: Callable[[dict[str, Any]], Mapping[str, Any]],
    receipt_persister: Callable[[dict[str, Any]], Mapping[str, Any]],
    charger: Callable[[dict[str, Any]], Mapping[str, Any]],
    terminal_reporter: Callable[[dict[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    record = ledger.records_by_job_id.get(_clean(job_id))
    if not isinstance(record, dict):
        return {
            "ok": False,
            "blocker": "frame_job_not_found",
            "terminal_state": "failed_no_charge",
            "idempotent_replay": False,
            **_ledger_counters(ledger),
        }
    if record.get("terminal_report", {}).get("emitted"):
        return _finalize_result(
            ledger,
            record,
            ok=True,
            idempotent_replay=True,
        )
    if not record.get("validation", {}).get("ok"):
        return _finalize_result(
            ledger,
            record,
            ok=False,
            blocker=_clean(record.get("blocker") or "frame_artifact_not_validated"),
        )
    artifact = Path(_clean(record.get("artifact_path")))
    if (
        not artifact.is_file()
        or artifact.stat().st_size != int(record.get("output_bytes") or 0)
        or _sha256_file(artifact) != record.get("artifact_sha256")
    ):
        record["terminal_state"] = "failed_no_charge"
        record["blocker"] = "frame_artifact_changed_after_validation"
        return _finalize_result(
            ledger,
            record,
            ok=False,
            blocker=record["blocker"],
        )
    artifact_sha = _clean(record.get("artifact_sha256"))

    if not record.get("delivery", {}).get("accepted"):
        if record.get("delivery_attempted"):
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="delivery_not_accepted",
                idempotent_replay=True,
            )
        record["delivery_attempted"] = True
        ledger.delivery_count += 1
        try:
            delivery = dict(
                deliverer(
                    {
                        "job_id": record["job_id"],
                        "artifact_path": str(artifact),
                        "artifact_sha256": artifact_sha,
                        "idempotency_key": (
                            f"delivery:{record['job_id']}:{artifact_sha}"
                        ),
                        "production": False,
                    }
                )
                or {}
            )
        except Exception as exc:
            record["safe_error"] = type(exc).__name__
            delivery = {}
        if delivery.get("production"):
            ledger.production_telegram_deliveries += 1
            record["delivery"] = {**delivery, "accepted": False}
            record["blocker"] = "production_telegram_delivery_forbidden"
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker=record["blocker"],
            )
        if not delivery.get("accepted") or not _clean(delivery.get("message_id")):
            record["delivery"] = {**delivery, "accepted": False}
            record["blocker"] = "delivery_not_accepted"
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker=record["blocker"],
            )
        record["delivery"] = delivery

    if not record.get("receipt", {}).get("persisted"):
        if record.get("receipt_attempted"):
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="delivery_receipt_not_persisted",
                idempotent_replay=True,
            )
        record["receipt_attempted"] = True
        ledger.receipt_count += 1
        delivered_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        receipt_seed = {
            "job_id": record["job_id"],
            "delivered": True,
            "delivery_idempotency_key": (
                f"delivery:{record['job_id']}:{artifact_sha}"
            ),
            "delivery_message_id": _clean(record["delivery"].get("message_id")),
            "output_sha256": artifact_sha,
            "output_bytes": artifact.stat().st_size,
            "delivered_at": delivered_at,
        }
        try:
            persisted = dict(receipt_persister(receipt_seed) or {})
        except Exception as exc:
            record["safe_error"] = type(exc).__name__
            persisted = {}
        receipt = video_engine_contract.VideoDeliveryReceipt(
            **receipt_seed,
            receipt_id=_clean(persisted.get("receipt_id")),
        )
        if not persisted.get("persisted") or not receipt.valid:
            record["receipt"] = {**receipt_seed, **persisted, "persisted": False}
            record["blocker"] = "delivery_receipt_not_persisted"
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker=record["blocker"],
            )
        record["receipt"] = {
            **_json_safe(receipt),
            **persisted,
            "persisted": True,
        }

    if not record.get("charge", {}).get("recorded"):
        if record.get("charge_attempted"):
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="charge_not_recorded",
                idempotent_replay=True,
            )
        request = record.get("request")
        payload = dict(getattr(request, "payload", {}) or {})
        admin_no_charge = bool(payload.get("admin_no_charge"))
        amount = (
            0
            if admin_no_charge
            else int((payload.get("charge_plan") or {}).get("amount_xu") or 0)
        )
        if not admin_no_charge and amount <= 0:
            record["blocker"] = "charge_plan_missing"
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker=record["blocker"],
            )
        record["charge_attempted"] = True
        ledger.charge_attempts += 1
        try:
            charge = dict(
                charger(
                    {
                        "job_id": record["job_id"],
                        "amount_xu": amount,
                        "admin_no_charge": admin_no_charge,
                        "receipt_id": record["receipt"].get("receipt_id"),
                        "idempotency_key": (
                            f"charge:{record['job_id']}:{amount}"
                        ),
                    }
                )
                or {}
            )
        except Exception as exc:
            record["safe_error"] = type(exc).__name__
            charge = {}
        if charge.get("wallet_mutated"):
            ledger.wallet_mutations += 1
            if admin_no_charge:
                record["charge"] = {**charge, "recorded": False}
                record["blocker"] = "admin_wallet_mutation_forbidden"
                return _finalize_result(
                    ledger,
                    record,
                    ok=False,
                    blocker=record["blocker"],
                )
        if not charge.get("ok"):
            record["charge"] = {**charge, "recorded": False}
            record["blocker"] = "charge_not_recorded"
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker=record["blocker"],
            )
        record["charge"] = {
            **charge,
            "recorded": True,
            "amount_xu": amount,
        }

    if not record.get("terminal_report", {}).get("emitted"):
        if record.get("terminal_report_attempted"):
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="terminal_report_not_emitted",
                idempotent_replay=True,
            )
        record["terminal_report_attempted"] = True
        ledger.terminal_report_count += 1
        try:
            report = dict(
                terminal_reporter(
                    {
                        "job_id": record["job_id"],
                        "terminal_state": "final_delivered",
                        "artifact_sha256": artifact_sha,
                        "receipt_id": record["receipt"].get("receipt_id"),
                        "idempotency_key": (
                            f"terminal-report:{record['job_id']}"
                        ),
                    }
                )
                or {}
            )
        except Exception as exc:
            record["safe_error"] = type(exc).__name__
            report = {}
        if not report.get("emitted") or not _clean(report.get("report_id")):
            record["terminal_report"] = {**report, "emitted": False}
            record["blocker"] = "terminal_report_not_emitted"
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker=record["blocker"],
            )
        record["terminal_report"] = report

    record["terminal_state"] = "final_delivered"
    record["blocker"] = ""
    return _finalize_result(ledger, record, ok=True)
