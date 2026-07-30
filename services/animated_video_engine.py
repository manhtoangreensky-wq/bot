"""UI-free local Animated Video route and engine for Video Menu 29H.

The adapter accepts only an approved scene graph and user/owner-supplied assets.
It renders deterministic motion locally through the existing FFmpeg runtime;
it never invents unseen animation, selects a provider, or hides a blocker.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping

from services import frame_video_runtime
from services import multiscene_video_pipeline as pipeline
from services import video_engine_contract


PRODUCT_FAMILY = "animated_video"
ROUTE_ID = "animated_video_local_v1"
ENGINE_ADAPTER = "animated_video_local_ffmpeg_v29h"
WORKER_JOB_TYPE = "animated_video_local_render"
WORKER_OWNER = "local_worker"
CANONICAL_WORKER_CAPABILITY = "animated_video_local_ffmpeg"
SUPPORTED_MODES = (
    video_engine_contract.VideoEngineMode.SINGLE_SCENE.value,
    video_engine_contract.VideoEngineMode.MULTI_SCENE.value,
)
ANIMATED_VIDEO_ENGINE_FLAG_DEFAULTS = {
    "ANIMATED_VIDEO_ENGINE_ENABLED": False,
    "ANIMATED_VIDEO_PUBLIC_ALLOWED": False,
    "ANIMATED_VIDEO_AUTO_RETRY": False,
    "ANIMATED_VIDEO_AUTO_FALLBACK": False,
}
SUPPORTED_TRANSITIONS = {"cut", "none", "fade", "dissolve"}
SUPPORTED_POSITIONS = {
    "top_left",
    "top_center",
    "top_right",
    "center_left",
    "center",
    "center_right",
    "bottom_left",
    "bottom_center",
    "bottom_right",
}
UNSUPPORTED_CLAIMS = (
    "3d_orbit",
    "unseen_content_generation",
    "lip_sync",
    "character_animation_generation",
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _clean(value).lower() in {"1", "true", "yes", "on"}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _normalize_ratio(value: Any) -> str:
    token = _clean(value or "9:16").lower().replace("x", ":")
    return token if token in {"9:16", "16:9", "1:1", "4:5"} else "9:16"


def _normalize_position(value: Any, fallback: str = "bottom_right") -> str:
    token = _clean(value or fallback).lower().replace("-", "_")
    return token if token in SUPPORTED_POSITIONS else fallback


def _strict_position(value: Any, fallback: str, field_name: str) -> str:
    raw = _clean(value)
    token = _normalize_position(raw, fallback)
    if raw and raw.lower().replace("-", "_") not in SUPPORTED_POSITIONS:
        raise ValueError(f"{field_name}_invalid")
    return token


def _normalize_motion(value: Any) -> str:
    token = _clean(value or "ken_burns").lower().replace("-", "_")
    aliases = {"pan": "pan_horizontal", "push_in": "zoom_in", "push_out": "zoom_out"}
    token = aliases.get(token, token)
    if token in UNSUPPORTED_CLAIMS or token not in frame_video_runtime.MOTIONS or token == "none":
        raise ValueError("animated_motion_unsupported")
    return token


def animated_video_engine_flags(environ: Mapping[str, Any] | None = None) -> dict[str, bool]:
    source = os.environ if environ is None else environ
    return {
        name: _flag(source.get(name, default))
        for name, default in ANIMATED_VIDEO_ENGINE_FLAG_DEFAULTS.items()
    }


def shared_animated_video_engine_route() -> dict[str, Any]:
    return {
        "product": PRODUCT_FAMILY,
        "state": video_engine_contract.VideoRouteState.CONNECTED.value,
        "connected": True,
        "public_product_type": PRODUCT_FAMILY,
        "worker_job_type": WORKER_JOB_TYPE,
        "engine_route": ENGINE_ADAPTER,
        "worker_owner": WORKER_OWNER,
        "required_capability": CANONICAL_WORKER_CAPABILITY,
        "required_capabilities": (CANONICAL_WORKER_CAPABILITY,),
        "supported_modes": SUPPORTED_MODES,
        "provider_enabled": False,
        "local_enabled": True,
        "blocker": "",
    }


def animated_video_engine_contract(environ: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "route_id": ROUTE_ID,
        "product_family": PRODUCT_FAMILY,
        "engine_adapter": ENGINE_ADAPTER,
        "supported_modes": SUPPORTED_MODES,
        "provider_required": False,
        "cloud_provider_calls": 0,
        "automatic_retry": False,
        "automatic_fallback": False,
        "scene_asset_required": True,
        "rights_receipt_required": True,
        "character_style_continuity_required": True,
        "unsupported_claims": UNSUPPORTED_CLAIMS,
        "artifact_promise": {
            "container": "mp4",
            "video_stream": True,
            "full_decode": True,
            "motion_when_promised": True,
            "ordered_scenes": True,
        },
        "flags": animated_video_engine_flags(environ),
    }


@dataclass(frozen=True)
class AnimatedScene:
    scene_id: str
    scene_index: int
    visual_prompt: str
    style_prompt: str
    character_id: str
    style_id: str
    asset_id: str
    asset_path: str
    asset_sha256: str
    asset_bytes: int
    rights_approved: bool
    rights_receipt_id: str
    duration_seconds: float
    motion: str
    caption: str = ""


@dataclass(frozen=True)
class AnimatedVideoPlan:
    mode: str
    scenes: tuple[AnimatedScene, ...]
    aspect_ratio: str
    transition: str
    transition_seconds: float
    audio_policy: Mapping[str, Any]
    voice_policy: Mapping[str, Any]
    final_assets: Mapping[str, Any]
    expected_duration_seconds: float
    scene_order_sha256: str
    plan_sha256: str


def _scene_material(scene: AnimatedScene) -> dict[str, Any]:
    return {
        "scene_id": scene.scene_id,
        "scene_index": scene.scene_index,
        "visual_prompt": scene.visual_prompt,
        "style_prompt": scene.style_prompt,
        "character_id": scene.character_id,
        "style_id": scene.style_id,
        "asset_id": scene.asset_id,
        "asset_sha256": scene.asset_sha256,
        "asset_bytes": scene.asset_bytes,
        "rights_approved": scene.rights_approved,
        "rights_receipt_id": scene.rights_receipt_id,
        "duration_seconds": scene.duration_seconds,
        "motion": scene.motion,
        "caption": scene.caption,
    }


def _plan_material(plan: AnimatedVideoPlan) -> dict[str, Any]:
    return {
        "mode": plan.mode,
        "scenes": [_scene_material(scene) for scene in plan.scenes],
        "aspect_ratio": plan.aspect_ratio,
        "transition": plan.transition,
        "transition_seconds": plan.transition_seconds,
        "audio_policy": _json_safe(plan.audio_policy),
        "voice_policy": _json_safe(plan.voice_policy),
        "final_assets": _json_safe(
            {key: value for key, value in plan.final_assets.items() if key not in {"logo_path"}}
        ),
        "expected_duration_seconds": plan.expected_duration_seconds,
        "scene_order_sha256": plan.scene_order_sha256,
    }


def _plan_sha256(plan: AnimatedVideoPlan) -> str:
    return _sha256_text(_canonical_json(_plan_material(plan)))


def _promised_audio_policies(plan: AnimatedVideoPlan) -> tuple[dict[str, Any], ...]:
    return tuple(
        dict(policy)
        for policy in (plan.audio_policy, plan.voice_policy)
        if _flag(policy.get("promised"))
    )


def compile_animated_video_plan(
    *,
    scenes: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    mode: str,
    aspect_ratio: str = "9:16",
    transition: str = "fade",
    transition_seconds: float = 0.35,
    audio_policy: Mapping[str, Any] | None = None,
    voice_policy: Mapping[str, Any] | None = None,
    final_assets: Mapping[str, Any] | None = None,
) -> AnimatedVideoPlan:
    selected_mode = _clean(mode).lower()
    if selected_mode not in SUPPORTED_MODES:
        raise ValueError("animated_mode_unsupported")
    raw_scenes = tuple(scenes or ())
    if not raw_scenes:
        raise ValueError("animated_scene_required")
    if selected_mode == "single_scene" and len(raw_scenes) != 1:
        raise ValueError("single_scene_requires_one_scene")
    if selected_mode == "multi_scene" and len(raw_scenes) < 2:
        raise ValueError("multi_scene_requires_multiple_scenes")
    selected_transition = _clean(transition or "fade").lower().replace("-", "_")
    if selected_transition not in SUPPORTED_TRANSITIONS:
        raise ValueError("animated_transition_unsupported")
    try:
        transition_seconds_value = max(0.0, min(1.5, float(transition_seconds)))
    except (TypeError, ValueError) as exc:
        raise ValueError("animated_transition_duration_invalid") from exc
    if selected_transition not in {"cut", "none"} and transition_seconds_value <= 0:
        raise ValueError("animated_transition_duration_invalid")

    compiled: list[AnimatedScene] = []
    for ordinal, raw in enumerate(raw_scenes, start=1):
        if not isinstance(raw, Mapping):
            raise ValueError("animated_scene_invalid")
        scene_id = _clean(raw.get("scene_id") or f"scene-{ordinal}")
        scene_index = int(raw.get("scene_index") or ordinal)
        if scene_index != ordinal:
            raise ValueError("animated_scene_order_invalid")
        visual_prompt = _clean(raw.get("visual_prompt"))
        style_prompt = _clean(raw.get("style_prompt"))
        character_id = _clean(raw.get("character_id"))
        style_id = _clean(raw.get("style_id"))
        asset_id = _clean(raw.get("asset_id"))
        asset_path = Path(_clean(raw.get("asset_path"))).expanduser()
        rights_receipt_id = _clean(raw.get("rights_receipt_id"))
        if not visual_prompt or not style_prompt or not character_id or not style_id:
            raise ValueError("animated_scene_specification_required")
        if not asset_id or not asset_path.is_file() or asset_path.stat().st_size <= 0:
            raise ValueError("animated_scene_asset_missing")
        if not _flag(raw.get("rights_approved")) or not rights_receipt_id:
            raise ValueError("rights_receipt_required")
        try:
            duration = float(raw.get("duration_seconds") or 0.0)
        except (TypeError, ValueError) as exc:
            raise ValueError("animated_scene_duration_invalid") from exc
        if duration < 1.0 or duration > 30.0:
            raise ValueError("animated_scene_duration_invalid")
        motion = _normalize_motion(raw.get("motion"))
        compiled.append(
            AnimatedScene(
                scene_id=scene_id,
                scene_index=scene_index,
                visual_prompt=visual_prompt,
                style_prompt=style_prompt,
                character_id=character_id,
                style_id=style_id,
                asset_id=asset_id,
                asset_path=str(asset_path.resolve()),
                asset_sha256=_sha256_file(asset_path),
                asset_bytes=asset_path.stat().st_size,
                rights_approved=True,
                rights_receipt_id=rights_receipt_id,
                duration_seconds=round(duration, 3),
                motion=motion,
                caption=_clean(raw.get("caption"))[:500],
            )
        )
    style_ids = {scene.style_id for scene in compiled}
    character_ids = {scene.character_id for scene in compiled}
    if len(style_ids) != 1 or len(character_ids) != 1:
        raise ValueError("animated_continuity_manifest_mismatch")
    normalized_final_assets = dict(final_assets or {})
    logo_enabled = _flag(
        normalized_final_assets.get("logo_enabled")
        or normalized_final_assets.get("enable_logo")
        or normalized_final_assets.get("logo_path")
    )
    logo_path = Path(_clean(normalized_final_assets.get("logo_path"))).expanduser()
    logo_asset_id = _clean(normalized_final_assets.get("logo_asset_id") or "brand-logo")
    logo_sha256 = _clean(normalized_final_assets.get("logo_sha256")).lower()
    if logo_enabled:
        if not logo_path.is_file() or logo_path.stat().st_size <= 0:
            raise ValueError("animated_logo_asset_missing")
        actual_logo_sha = _sha256_file(logo_path)
        if logo_sha256 and logo_sha256 != actual_logo_sha:
            raise ValueError("animated_logo_asset_fingerprint_mismatch")
        logo_sha256 = actual_logo_sha
    normalized_final_assets = {
        "enable_subtitle": _flag(normalized_final_assets.get("enable_subtitle")),
        "logo_enabled": logo_enabled,
        "logo_asset_id": logo_asset_id if logo_enabled else "",
        "logo_path": str(logo_path.resolve()) if logo_enabled else "",
        "logo_sha256": logo_sha256 if logo_enabled else "",
        "logo_bytes": logo_path.stat().st_size if logo_enabled else 0,
        "logo_position": _strict_position(
            normalized_final_assets.get("logo_position"),
            "top_left",
            "animated_logo_position",
        ),
        "watermark_text": _clean(normalized_final_assets.get("watermark_text"))[:500],
        "watermark_position": _strict_position(
            normalized_final_assets.get("watermark_position"),
            "bottom_right",
            "animated_watermark_position",
        ),
    }
    promised_audio = _promised_audio_policies(
        AnimatedVideoPlan(
            mode=selected_mode,
            scenes=tuple(compiled),
            aspect_ratio=_normalize_ratio(aspect_ratio),
            transition=selected_transition,
            transition_seconds=transition_seconds_value,
            audio_policy=dict(audio_policy or {}),
            voice_policy=dict(voice_policy or {}),
            final_assets=normalized_final_assets,
            expected_duration_seconds=0.0,
            scene_order_sha256="",
            plan_sha256="",
        )
    )
    if len(promised_audio) > 1:
        raise ValueError("multiple_promised_audio_assets_unsupported")
    overlap = transition_seconds_value if selected_transition not in {"cut", "none"} else 0.0
    expected_duration = round(
        sum(scene.duration_seconds for scene in compiled) - overlap * max(0, len(compiled) - 1),
        3,
    )
    scene_order_sha = _sha256_text(
        _canonical_json(
            [
                {"scene_index": scene.scene_index, "scene_id": scene.scene_id, "asset_sha256": scene.asset_sha256}
                for scene in compiled
            ]
        )
    )
    provisional = AnimatedVideoPlan(
        mode=selected_mode,
        scenes=tuple(compiled),
        aspect_ratio=_normalize_ratio(aspect_ratio),
        transition=selected_transition,
        transition_seconds=overlap,
        audio_policy=_json_safe(dict(audio_policy or {})),
        voice_policy=_json_safe(dict(voice_policy or {})),
        final_assets=_json_safe(normalized_final_assets),
        expected_duration_seconds=expected_duration,
        scene_order_sha256=scene_order_sha,
        plan_sha256="",
    )
    return replace(provisional, plan_sha256=_plan_sha256(provisional))


def validate_animated_video_plan(plan: AnimatedVideoPlan) -> dict[str, Any]:
    if not isinstance(plan, AnimatedVideoPlan):
        return {"ok": False, "blocker": "animated_plan_required"}
    if _plan_sha256(plan) != plan.plan_sha256:
        return {"ok": False, "blocker": "animated_plan_hash_mismatch"}
    count = len(plan.scenes)
    if plan.mode not in SUPPORTED_MODES:
        return {"ok": False, "blocker": "animated_mode_unsupported"}
    if plan.mode == "single_scene" and count != 1:
        return {"ok": False, "blocker": "single_scene_requires_one_scene"}
    if plan.mode == "multi_scene" and count < 2:
        return {"ok": False, "blocker": "multi_scene_requires_multiple_scenes"}
    if [scene.scene_index for scene in plan.scenes] != list(range(1, count + 1)):
        return {"ok": False, "blocker": "animated_scene_order_invalid"}
    if len({scene.style_id for scene in plan.scenes}) != 1 or len({scene.character_id for scene in plan.scenes}) != 1:
        return {"ok": False, "blocker": "animated_continuity_manifest_mismatch"}
    for scene in plan.scenes:
        if (
            not scene.asset_id
            or scene.asset_bytes <= 0
            or len(scene.asset_sha256) != 64
            or any(character not in "0123456789abcdef" for character in scene.asset_sha256)
        ):
            return {"ok": False, "blocker": "animated_scene_asset_manifest_invalid"}
        if not scene.rights_approved or not scene.rights_receipt_id:
            return {"ok": False, "blocker": "rights_receipt_required"}
    if len(_promised_audio_policies(plan)) > 1:
        return {"ok": False, "blocker": "multiple_promised_audio_assets_unsupported"}
    final_assets = dict(plan.final_assets or {})
    if final_assets.get("logo_enabled"):
        logo_sha = _clean(final_assets.get("logo_sha256"))
        if (
            not _clean(final_assets.get("logo_asset_id"))
            or int(final_assets.get("logo_bytes") or 0) <= 0
            or len(logo_sha) != 64
            or any(character not in "0123456789abcdef" for character in logo_sha)
        ):
            return {"ok": False, "blocker": "animated_logo_asset_manifest_invalid"}
    if final_assets.get("logo_position") not in SUPPORTED_POSITIONS:
        return {"ok": False, "blocker": "animated_logo_position_invalid"}
    if final_assets.get("watermark_position") not in SUPPORTED_POSITIONS:
        return {"ok": False, "blocker": "animated_watermark_position_invalid"}
    return {
        "ok": True,
        "blocker": "",
        "scene_count": count,
        "scene_order": [scene.scene_index for scene in plan.scenes],
        "scene_order_sha256": plan.scene_order_sha256,
        "plan_sha256": plan.plan_sha256,
        "expected_duration_seconds": plan.expected_duration_seconds,
    }


def build_animated_video_request(
    *,
    user_id: int,
    confirmation_id: str,
    language: str,
    plan: AnimatedVideoPlan,
    explicit_confirmation_receipt: Mapping[str, Any],
    runtime_sha: str,
    expected_worker_sha: str,
    admin_no_charge: bool = False,
    charge_plan: Mapping[str, Any] | None = None,
) -> video_engine_contract.VideoEngineRequest:
    validation = validate_animated_video_plan(plan)
    if not validation.get("ok"):
        raise ValueError(_clean(validation.get("blocker") or "animated_plan_invalid"))
    mode = video_engine_contract.VideoEngineMode(plan.mode)
    payload = {
        "route_id": ROUTE_ID,
        "plan_sha256": plan.plan_sha256,
        "scene_order_sha256": plan.scene_order_sha256,
        "scene_count": len(plan.scenes),
        "transition": plan.transition,
        "transition_seconds": plan.transition_seconds,
        "final_assets": {
            key: value for key, value in plan.final_assets.items() if key != "logo_path"
        },
        "admin_no_charge": bool(admin_no_charge),
        "charge_plan": _json_safe(dict(charge_plan or {})),
        "provider_calls": 0,
        "automatic_retry": False,
        "automatic_fallback": False,
    }
    input_assets = tuple(
        {
            "scene_index": scene.scene_index,
            "scene_id": scene.scene_id,
            "asset_id": scene.asset_id,
            "asset_sha256": scene.asset_sha256,
            "asset_bytes": scene.asset_bytes,
            "rights_receipt_id": scene.rights_receipt_id,
        }
        for scene in plan.scenes
    )
    approved_plan = {
        "route_id": ROUTE_ID,
        "approved": True,
        "mode": plan.mode,
        "plan_sha256": plan.plan_sha256,
        "scene_order_sha256": plan.scene_order_sha256,
        "scene_count": len(plan.scenes),
        "character_id": plan.scenes[0].character_id,
        "style_id": plan.scenes[0].style_id,
        "scenes": [_scene_material(scene) for scene in plan.scenes],
        "final_assets": {
            key: value for key, value in plan.final_assets.items() if key != "logo_path"
        },
    }
    common = {
        "user_id": user_id,
        "language": language,
        "approved_plan": approved_plan,
        "input_assets": input_assets,
        "aspect_ratio": plan.aspect_ratio,
        "duration_profile": {
            "duration_seconds": plan.expected_duration_seconds,
            "profile": "animated_video_local",
        },
        "audio_policy": dict(plan.audio_policy),
        "voice_policy": dict(plan.voice_policy),
        "provider_selection": "local",
        "runtime_sha": runtime_sha,
        "expected_worker_sha": expected_worker_sha,
    }
    key = video_engine_contract.stable_request_idempotency_key(
        confirmation_id=confirmation_id,
        product_type=video_engine_contract.VideoProduct.ANIMATED_VIDEO,
        mode=mode,
        payload=payload,
        **common,
    )
    return video_engine_contract.VideoEngineRequest(
        request_id=f"{ROUTE_ID}:{key[:20]}",
        confirmation_id=confirmation_id,
        idempotency_key=key,
        product_type=video_engine_contract.VideoProduct.ANIMATED_VIDEO,
        mode=mode,
        explicit_confirmation_receipt=dict(explicit_confirmation_receipt),
        confirmed=True,
        payload=payload,
        **common,
    )


def _sequence(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(_clean(item) for item in value if _clean(item))
    return ()


def animated_video_engine_readiness(
    request: video_engine_contract.VideoEngineRequest,
    *,
    plan: AnimatedVideoPlan,
    manifest: Mapping[str, Any],
    runtime_sha: str,
    environ: Mapping[str, Any] | None = None,
    public_request: bool = False,
) -> dict[str, Any]:
    flags = animated_video_engine_flags(environ)
    blocker = ""
    if not flags["ANIMATED_VIDEO_ENGINE_ENABLED"]:
        blocker = "animated_video_engine_disabled"
    elif public_request and not flags["ANIMATED_VIDEO_PUBLIC_ALLOWED"]:
        blocker = "animated_video_public_disabled"
    elif flags["ANIMATED_VIDEO_AUTO_RETRY"]:
        blocker = "automatic_retry_forbidden"
    elif flags["ANIMATED_VIDEO_AUTO_FALLBACK"]:
        blocker = "automatic_fallback_forbidden"
    elif request.product_type is not video_engine_contract.VideoProduct.ANIMATED_VIDEO:
        blocker = "animated_video_product_required"
    elif request.mode.value != plan.mode:
        blocker = "animated_video_mode_mismatch"
    plan_validation = validate_animated_video_plan(plan)
    if not blocker and not plan_validation.get("ok"):
        blocker = _clean(plan_validation.get("blocker") or "animated_plan_invalid")
    if not blocker and request.payload.get("plan_sha256") != plan.plan_sha256:
        blocker = "animated_request_plan_mismatch"
    shared = video_engine_contract.evaluate_readiness(
        request,
        manifest=manifest,
        runtime_sha=runtime_sha,
        environ=environ,
    )
    if not blocker and not shared.get("ready"):
        blocker = _clean(shared.get("blocker") or "worker_not_ready")
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
        "route": shared_animated_video_engine_route(),
        "provider_calls": 0,
    }


@dataclass
class AnimatedVideoEngineLedger:
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


def _ledger_counters(ledger: AnimatedVideoEngineLedger) -> dict[str, int]:
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
        job_id=f"p29h-{request.idempotency_key[:24]}",
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
    ledger: AnimatedVideoEngineLedger,
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


def dispatch_animated_video(
    request: video_engine_contract.VideoEngineRequest,
    *,
    plan: AnimatedVideoPlan,
    manifest: Mapping[str, Any],
    runtime_sha: str,
    ledger: AnimatedVideoEngineLedger,
    environ: Mapping[str, Any] | None,
    public_request: bool = False,
) -> dict[str, Any]:
    readiness = animated_video_engine_readiness(
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
                blocker=_clean(readiness.get("blocker") or "animated_video_not_ready"),
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
                blocker=_clean(guarded.get("blocker") or "animated_job_not_created"),
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
            "evidence_dir": "",
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


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(value), ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _output_geometry(aspect_ratio: str) -> tuple[int, int]:
    return {
        "9:16": (720, 1280),
        "16:9": (1280, 720),
        "1:1": (720, 720),
        "4:5": (720, 900),
    }.get(_normalize_ratio(aspect_ratio), (720, 1280))


def _full_decode(path: str, ffmpeg: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [ffmpeg, "-v", "error", "-i", path, "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "reason": "animated_full_decode_failed"}
    return {
        "ok": completed.returncode == 0,
        "reason": "" if completed.returncode == 0 else "animated_full_decode_failed",
    }


def _motion_evidence(path: str, ffmpeg: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-i",
                path,
                "-map",
                "0:v:0",
                "-vf",
                "fps=4",
                "-frames:v",
                "12",
                "-f",
                "framemd5",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "reason": "animated_motion_probe_failed", "unique_frames": 0}
    if completed.returncode != 0:
        return {"ok": False, "reason": "animated_motion_probe_failed", "unique_frames": 0}
    hashes = {
        line.rsplit(",", 1)[-1].strip()
        for line in completed.stdout.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "," in line
    }
    return {
        "ok": len(hashes) > 1,
        "reason": "" if len(hashes) > 1 else "animated_motion_promised_but_static",
        "unique_frames": len(hashes),
    }


def _execution_result(
    ledger: AnimatedVideoEngineLedger,
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
        "output_path": _clean(record.get("artifact_path")),
        "output_bytes": int(record.get("output_bytes") or 0),
        "evidence_dir": _clean(record.get("evidence_dir")),
        "validation": dict(record.get("validation") or {}),
        **_ledger_counters(ledger),
    }


def _fail_record(
    ledger: AnimatedVideoEngineLedger,
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


def _selected_audio_path(plan: AnimatedVideoPlan, audio_path: str) -> tuple[str, str]:
    promised = _promised_audio_policies(plan)
    if not promised:
        return "", ""
    selected = Path(_clean(audio_path))
    if not selected.is_file() or selected.stat().st_size <= 0:
        return "", "promised_audio_missing"
    expected_sha = _clean(promised[0].get("sha256")).lower()
    if expected_sha and _sha256_file(selected) != expected_sha:
        return "", "promised_audio_fingerprint_mismatch"
    return str(selected.resolve()), ""


def _scene_runtime_state(scene: AnimatedScene, plan: AnimatedVideoPlan) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    photos = [
        {
            "file_id": scene.asset_id,
            "file_unique_id": scene.asset_sha256,
            "file_name": Path(scene.asset_path).name,
            "file_size": scene.asset_bytes,
            "mime_type": "image/png",
            "source": "animated_video_engine_29h",
        }
    ]
    manifest = frame_video_runtime.canonical_image_manifest(photos)
    image_id = manifest[0]["image_id"]
    text_overlays = []
    if scene.caption:
        text_overlays.append(
            {
                "content": scene.caption,
                "start_seconds": 0.0,
                "end_seconds": scene.duration_seconds,
                "position": "bottom_center",
                "animation": "fade",
            }
        )
    watermark = _clean(plan.final_assets.get("watermark_text"))
    if watermark:
        text_overlays.append(
            {
                "content": watermark,
                "start_seconds": 0.0,
                "end_seconds": scene.duration_seconds,
                "position": _clean(plan.final_assets.get("watermark_position") or "bottom_right"),
                "animation": "none",
                "font_size": 24,
            }
        )
    state = {
        "photos": manifest,
        "image_count": 1,
        "ratio": plan.aspect_ratio.replace(":", "x"),
        "duration_seconds": scene.duration_seconds,
        "image_durations": {image_id: scene.duration_seconds},
        "transition": "none",
        "motion": scene.motion,
        "image_motions": {image_id: scene.motion},
        "fit_mode": "contain",
        "background_color": "#111111",
        "quality": "fast",
        "text_overlays": text_overlays,
        "font_path": os.environ.get("TOANAAS_FFMPEG_FONT", ""),
    }
    return manifest, state


def execute_animated_video_local(
    request: video_engine_contract.VideoEngineRequest,
    *,
    plan: AnimatedVideoPlan,
    manifest: Mapping[str, Any],
    runtime_sha: str,
    ledger: AnimatedVideoEngineLedger,
    output_root: str | Path,
    asset_paths: Mapping[str, str],
    environ: Mapping[str, Any] | None,
    audio_path: str = "",
    final_asset_paths: Mapping[str, str] | None = None,
    ffmpeg_path: str = "",
    ffprobe_path: str = "",
    public_request: bool = False,
) -> dict[str, Any]:
    dispatched = dispatch_animated_video(
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
        return {**dispatched, "ok": False, "blocker": "animated_job_not_found"}
    artifact = Path(_clean(record.get("artifact_path")))
    if artifact.is_file() and record.get("validation", {}).get("ok"):
        return _execution_result(ledger, record, ok=True, idempotent_replay=True)
    if record.get("render_attempted"):
        return _fail_record(
            ledger,
            record,
            _clean(record.get("blocker") or "animated_render_not_retriable"),
            idempotent_replay=True,
        )
    record["render_attempted"] = True

    ffmpeg = ffmpeg_path or shutil.which("ffmpeg") or ""
    ffprobe = ffprobe_path or shutil.which("ffprobe") or ""
    if not ffmpeg:
        return _fail_record(ledger, record, "ffmpeg_missing")
    if not ffprobe:
        return _fail_record(ledger, record, "ffprobe_missing")
    selected_audio, audio_blocker = _selected_audio_path(plan, audio_path)
    if audio_blocker:
        return _fail_record(ledger, record, audio_blocker)
    final_assets = dict(plan.final_assets or {})
    selected_logo = ""
    if final_assets.get("logo_enabled"):
        logo_asset_id = _clean(final_assets.get("logo_asset_id"))
        selected_logo_path = Path(
            _clean((final_asset_paths or {}).get(logo_asset_id) or final_assets.get("logo_path"))
        )
        if not selected_logo_path.is_file() or selected_logo_path.stat().st_size <= 0:
            return _fail_record(ledger, record, "animated_logo_asset_missing")
        if _sha256_file(selected_logo_path) != _clean(final_assets.get("logo_sha256")):
            return _fail_record(ledger, record, "animated_logo_asset_fingerprint_mismatch")
        selected_logo = str(selected_logo_path.resolve())

    workspace = Path(output_root) / record["job_id"]
    scene_dir = workspace / "scenes"
    evidence_dir = workspace / "evidence"
    scene_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    record["evidence_dir"] = str(evidence_dir)
    scene_clip_paths: dict[int, str] = {}
    pipeline_scenes: list[pipeline.SceneSpec] = []

    for scene in plan.scenes:
        selected = Path(_clean(asset_paths.get(scene.asset_id)))
        if not selected.is_file() or selected.stat().st_size <= 0:
            return _fail_record(ledger, record, "animated_scene_asset_missing")
        if _sha256_file(selected) != scene.asset_sha256:
            return _fail_record(ledger, record, "animated_scene_asset_fingerprint_mismatch")
        runtime_manifest, state = _scene_runtime_state(scene, plan)
        clip_path = scene_dir / f"scene_{scene.scene_index:03d}.mp4"
        try:
            command = frame_video_runtime.build_ffmpeg_command(
                [str(selected.resolve())],
                str(clip_path),
                state,
                ffmpeg_path=ffmpeg,
                min_images=1,
                continuous_still_motion=True,
            )
            completed = subprocess.run(
                command.command,
                capture_output=True,
                text=True,
                timeout=max(180, int(scene.duration_seconds * 60)),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            record["safe_error"] = type(exc).__name__
            return _fail_record(ledger, record, "animated_scene_render_failed")
        if completed.returncode != 0:
            record["safe_error"] = _clean(completed.stderr)[-500:]
            return _fail_record(ledger, record, "animated_scene_render_failed")
        clip_probe = frame_video_runtime.probe_mp4(
            str(clip_path),
            command.expected_duration,
            expects_audio=False,
            ffprobe_path=ffprobe,
        )
        clip_motion = _motion_evidence(str(clip_path), ffmpeg)
        if not clip_probe.get("ok"):
            return _fail_record(ledger, record, _clean(clip_probe.get("reason") or "animated_scene_invalid"))
        if not clip_motion.get("ok"):
            return _fail_record(ledger, record, _clean(clip_motion.get("reason") or "animated_motion_promised_but_static"))
        ledger.render_count += 1
        scene_clip_paths[scene.scene_index] = str(clip_path)
        scene_manifest = {
            **_scene_material(scene),
            "runtime_manifest": runtime_manifest,
            "text_overlays": list(state.get("text_overlays") or []),
            "visual_prompt_sha256": _sha256_text(scene.visual_prompt),
            "style_prompt_sha256": _sha256_text(scene.style_prompt),
            "clip_path": str(clip_path),
            "clip_sha256": _sha256_file(clip_path),
            "clip_probe": clip_probe,
            "motion_evidence": clip_motion,
            "provider_calls": 0,
        }
        _write_json(evidence_dir / f"scene_{scene.scene_index:03d}_manifest.json", scene_manifest)
        pipeline_scenes.append(
            pipeline.SceneSpec(
                scene_id=scene.scene_index,
                title=scene.caption or scene.scene_id,
                visual_prompt=scene.visual_prompt,
                video_prompt=f"{scene.style_prompt}; motion={scene.motion}",
                narration_text=scene.caption or None,
                target_duration_sec=scene.duration_seconds,
                aspect_ratio=plan.aspect_ratio,
                transition=plan.transition if scene.scene_index < len(plan.scenes) else "cut",
                seed_image_path=str(selected.resolve()),
                provider_params={"provider": "local", "rights_receipt_id": scene.rights_receipt_id},
            )
        )

    width, height = _output_geometry(plan.aspect_ratio)
    subtitle_requested = _flag(final_assets.get("enable_subtitle"))
    subtitle_path = ""
    if subtitle_requested:
        subtitle_path = pipeline.build_scene_subtitle(
            pipeline_scenes,
            [scene.duration_seconds for scene in plan.scenes],
            str(workspace / "composition" / "scene_subtitles.srt"),
        )
    composition = pipeline.finalize_multiscene_scene_clips(
        user_id=str(request.user_id),
        job_id=record["job_id"],
        workspace_dir=str(workspace / "composition"),
        scenes=pipeline_scenes,
        scene_clip_paths=scene_clip_paths,
        bgm_audio_path=selected_audio or None,
        logo_path=selected_logo or None,
        enable_voice=False,
        # Caption text is burned into each scene by frame_video_runtime. Keeping
        # the finalizer subtitle filter off avoids a second burn and libass/font
        # configuration drift across workers; the SRT remains the audit artifact.
        enable_subtitle=False,
        enable_logo=bool(selected_logo),
        logo_text=None,
        logo_position=_clean(final_assets.get("logo_position") or "top_left"),
        watermark_position=_clean(
            final_assets.get("watermark_position") or "bottom_right"
        ),
        output_width=width,
        output_height=height,
        output_fps=24,
        transition_duration_sec=plan.transition_seconds,
        preserve_scene_audio=False,
    )
    if not composition.get("ok") or not _clean(composition.get("final_video_path")):
        record["composition"] = _json_safe(composition)
        return _fail_record(
            ledger,
            record,
            _clean(composition.get("error") or "animated_composition_failed"),
        )
    ledger.compose_count += 1
    final_path = Path(_clean(composition.get("final_video_path")))
    final_probe = frame_video_runtime.probe_mp4(
        str(final_path),
        float(composition.get("target_duration_sec") or plan.expected_duration_seconds),
        expects_audio=bool(selected_audio),
        ffprobe_path=ffprobe,
    )
    decode = _full_decode(str(final_path), ffmpeg)
    motion = _motion_evidence(str(final_path), ffmpeg)
    logo_requested = bool(final_assets.get("logo_enabled"))
    watermark_requested = bool(_clean(final_assets.get("watermark_text")))
    visual_assets_requested = bool(logo_requested)
    master_path = Path(_clean(composition.get("master_video_path")))
    visual_assets_applied = not visual_assets_requested or (
        master_path.is_file() and _sha256_file(master_path) != _sha256_file(final_path)
    )
    subtitle_applied = bool(subtitle_requested and Path(subtitle_path).is_file())
    watermark_applied = not watermark_requested or bool(
        all(
            Path(evidence_dir / f"scene_{scene.scene_index:03d}_manifest.json").is_file()
            for scene in plan.scenes
        )
    )
    final_assets_applied = bool(
        (not subtitle_requested or subtitle_applied)
        and (not watermark_requested or watermark_applied)
        and visual_assets_applied
    )
    validation = {
        **final_probe,
        "ok": bool(final_probe.get("ok") and decode.get("ok") and motion.get("ok")),
        "full_decode": bool(decode.get("ok")),
        "motion_valid": bool(motion.get("ok")),
        "unique_frames": int(motion.get("unique_frames") or 0),
        "scene_count": len(plan.scenes),
        "scene_order": [scene.scene_index for scene in plan.scenes],
        "scene_order_sha256": plan.scene_order_sha256,
        "plan_sha256": plan.plan_sha256,
        "transition_plan": list(composition.get("transition_plan") or []),
        "compose_count": 1,
        "provider_calls": 0,
        "subtitle_applied": subtitle_applied,
        "subtitle_path": subtitle_path,
        "logo_applied": bool(logo_requested and visual_assets_applied),
        "watermark_applied": bool(watermark_requested and watermark_applied),
        "final_assets_applied": bool(final_assets_applied),
    }
    validation["ok"] = bool(validation["ok"] and final_assets_applied)
    if not validation["ok"]:
        record["validation"] = validation
        blocker = _clean(
            final_probe.get("reason")
            or decode.get("reason")
            or motion.get("reason")
            or ("final_assets_not_applied" if not final_assets_applied else "")
            or "animated_artifact_invalid"
        )
        return _fail_record(ledger, record, blocker)
    record.update(
        {
            "artifact_path": str(final_path),
            "artifact_sha256": _sha256_file(final_path),
            "output_bytes": final_path.stat().st_size,
            "terminal_state": "rendered_validated",
            "blocker": "",
            "validation": validation,
            "composition": _json_safe(composition),
        }
    )
    _write_json(
        evidence_dir / "job_manifest.json",
        {
            "job_id": record["job_id"],
            "route_id": ROUTE_ID,
            "plan": _plan_material(plan),
            "plan_sha256": plan.plan_sha256,
            "scene_order_sha256": plan.scene_order_sha256,
            "provider_calls": 0,
            "automatic_retry": False,
            "automatic_fallback": False,
        },
    )
    _write_json(evidence_dir / "validation_report.json", validation)
    return _execution_result(ledger, record, ok=True)


def _finalize_result(
    ledger: AnimatedVideoEngineLedger,
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


def finalize_animated_video(
    *,
    ledger: AnimatedVideoEngineLedger,
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
            "blocker": "animated_job_not_found",
            "terminal_state": "failed_no_charge",
            "idempotent_replay": False,
            **_ledger_counters(ledger),
        }
    if record.get("terminal_report", {}).get("emitted"):
        return _finalize_result(ledger, record, ok=True, idempotent_replay=True)
    if not record.get("validation", {}).get("ok"):
        record["terminal_state"] = "failed_no_charge"
        record["blocker"] = "animated_artifact_not_validated"
        return _finalize_result(
            ledger,
            record,
            ok=False,
            blocker="animated_artifact_not_validated",
        )
    artifact = Path(_clean(record.get("artifact_path")))
    artifact_sha = _clean(record.get("artifact_sha256"))
    output_bytes = int(record.get("output_bytes") or 0)
    if (
        not artifact.is_file()
        or artifact.stat().st_size != output_bytes
        or _sha256_file(artifact) != artifact_sha
    ):
        record["terminal_state"] = "failed_no_charge"
        record["blocker"] = "animated_artifact_changed_after_validation"
        return _finalize_result(
            ledger,
            record,
            ok=False,
            blocker="animated_artifact_changed_after_validation",
        )
    evidence_dir = Path(_clean(record.get("evidence_dir")))

    if not record.get("delivery", {}).get("accepted"):
        if record.get("delivery_attempted"):
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="delivery_not_accepted",
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
                        "output_bytes": output_bytes,
                        "idempotency_key": f"delivery:{record['job_id']}:{artifact_sha}",
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
                blocker="production_telegram_delivery_forbidden",
            )
        if not delivery.get("accepted") or not _clean(delivery.get("message_id")):
            record["delivery"] = {**delivery, "accepted": False}
            record["blocker"] = "delivery_not_accepted"
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="delivery_not_accepted",
            )
        record["delivery"] = delivery

    if not record.get("receipt", {}).get("persisted"):
        if record.get("receipt_attempted"):
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="delivery_receipt_not_persisted",
            )
        record["receipt_attempted"] = True
        ledger.receipt_count += 1
        receipt_seed = {
            "job_id": record["job_id"],
            "delivered": True,
            "delivery_idempotency_key": f"delivery:{record['job_id']}:{artifact_sha}",
            "delivery_message_id": _clean(record["delivery"].get("message_id")),
            "output_sha256": artifact_sha,
            "output_bytes": output_bytes,
            "delivered_at": str(time.time()),
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
                blocker="delivery_receipt_not_persisted",
            )
        record["receipt"] = {**asdict(receipt), **persisted, "persisted": True}
        if evidence_dir:
            _write_json(evidence_dir / "delivery_receipt.json", record["receipt"])

    if not record.get("charge", {}).get("recorded"):
        if record.get("charge_attempted"):
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="charge_not_recorded",
            )
        request = record.get("request")
        payload = dict(request.payload if isinstance(request, video_engine_contract.VideoEngineRequest) else {})
        admin_no_charge = bool(payload.get("admin_no_charge"))
        amount = 0 if admin_no_charge else int((payload.get("charge_plan") or {}).get("amount_xu") or 0)
        if not admin_no_charge and amount <= 0:
            record["blocker"] = "charge_plan_missing"
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="charge_plan_missing",
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
                        "idempotency_key": f"charge:{record['job_id']}:{artifact_sha}",
                    }
                )
                or {}
            )
        except Exception as exc:
            record["safe_error"] = type(exc).__name__
            charge = {}
        if charge.get("wallet_mutated"):
            ledger.wallet_mutations += 1
        if (
            not charge.get("recorded")
            or int(charge.get("amount_xu") or 0) != amount
            or (admin_no_charge and charge.get("wallet_mutated"))
        ):
            record["charge"] = {**charge, "recorded": False}
            record["blocker"] = "charge_not_recorded"
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="charge_not_recorded",
            )
        record["charge"] = {**charge, "recorded": True, "amount_xu": amount}

    if not record.get("terminal_report", {}).get("emitted"):
        if record.get("terminal_report_attempted"):
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="terminal_report_not_emitted",
            )
        record["terminal_report_attempted"] = True
        ledger.terminal_report_count += 1
        try:
            report = dict(
                terminal_reporter(
                    {
                        "job_id": record["job_id"],
                        "artifact_sha256": artifact_sha,
                        "delivery_message_id": _clean(record["delivery"].get("message_id")),
                        "receipt_id": _clean(record["receipt"].get("receipt_id")),
                        "amount_xu": int(record["charge"].get("amount_xu") or 0),
                        "idempotency_key": f"report:{record['job_id']}:{artifact_sha}",
                    }
                )
                or {}
            )
        except Exception as exc:
            record["safe_error"] = type(exc).__name__
            report = {}
        if not report.get("emitted"):
            record["terminal_report"] = {**report, "emitted": False}
            record["blocker"] = "terminal_report_not_emitted"
            return _finalize_result(
                ledger,
                record,
                ok=False,
                blocker="terminal_report_not_emitted",
            )
        record["terminal_report"] = {**report, "emitted": True}
        record["terminal_state"] = "final_delivered"
        record["blocker"] = ""
        if evidence_dir:
            _write_json(evidence_dir / "terminal_report.json", record["terminal_report"])
    return _finalize_result(ledger, record, ok=True)
