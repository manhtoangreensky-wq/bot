"""Default-off Product Video multi-scene contract, dispatch, and recovery.

Provider, delivery, receipt, charge, and report boundaries are injected. The
module persists ordered scene truth with the 29D atomic checkpoint store and
never creates a replacement task for an accepted or ambiguous scene.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping

from services import multiscene_video_pipeline as pipeline
from services import product_video_one_scene_engine as one_scene
from services import product_video_poll_recovery
from services import video_engine_contract


ROUTE_ID = "product_video_multiscene_v1"
PRODUCT_FAMILY = "product_video"
MODE = "multi_scene"
ENGINE_ADAPTER = "b13_r18c_product_multiscene_v1"
WORKER_JOB_TYPE = one_scene.WORKER_JOB_TYPE
WORKER_OWNER = one_scene.WORKER_OWNER
CANONICAL_WORKER_CAPABILITY = one_scene.CANONICAL_WORKER_CAPABILITY
REQUIRED_WORKER_CAPABILITIES = one_scene.REQUIRED_WORKER_CAPABILITIES
MAX_MULTISCENE_SCENES = 20
DEFAULT_SCENE_POLL_INTERVAL_SECONDS = 30.0
DEFAULT_RECOVERY_LEASE_SECONDS = 60.0
MULTISCENE_SCHEMA_VERSION = 1
DEFAULT_TRANSITION_DURATION_SECONDS = 0.35
DEFAULT_OUTPUT_FPS = 30
DEFAULT_AUDIO_SAMPLE_RATE = 48_000
DEFAULT_AUDIO_CHANNELS = 2

_CUT_TRANSITIONS = frozenset(
    {
        "cut",
        "none",
        "cut_on_action",
        "match_cut",
        "motion_match",
        "camera_pan_continuation",
        "whip_pan",
        "sound_bridge",
        "dialogue_bridge",
        "object_wipe",
        "doorway_transition",
        "reveal",
    }
)
_TRANSITION_ALIASES = {
    "mở trực tiếp": "cut",
    "kết thúc trọn vẹn": "cut",
    "before/after morph": "before_after_morph",
    "biến đổi trước sau": "before_after_morph",
    "biến đổi trước-sau": "before_after_morph",
    "cắt theo hành động": "cut_on_action",
    "cắt tương đồng": "match_cut",
    "nối cùng hướng chuyển động": "motion_match",
    "tiếp nối lia máy": "camera_pan_continuation",
    "vật thể lướt che khung": "object_wipe",
    "chuyển qua cửa": "doorway_transition",
    "mở lộ cảnh": "reveal",
    "hòa cảnh": "dissolve",
    "mờ dần": "fade",
    "lia nhanh": "whip_pan",
    "nối bằng âm thanh": "sound_bridge",
    "nối bằng lời thoại": "dialogue_bridge",
}
_SUPPORTED_TRANSITIONS = _CUT_TRANSITIONS | frozenset(
    {
        "fade",
        "dissolve",
        "wipe_left",
        "wipe_right",
        "wipe_up",
        "wipe_down",
        "slide_left",
        "slide_right",
        "slide_up",
        "slide_down",
        "circle_open",
        "circle_close",
        "fade_black",
        "fade_white",
        "before_after_morph",
    }
)

_FENCE_MAP_LOCK = threading.Lock()
_PROCESS_FENCES: dict[str, threading.Lock] = {}

MULTISCENE_FLAG_DEFAULTS = {
    "PRODUCT_VIDEO_MULTISCENE_ENGINE_ENABLED": False,
    "PRODUCT_VIDEO_MULTISCENE_PUBLIC_ALLOWED": False,
    "PRODUCT_VIDEO_MULTISCENE_REAL_PROVIDER_ENABLED": False,
    "PRODUCT_VIDEO_MULTISCENE_AUTO_RESUBMIT": False,
    "PRODUCT_VIDEO_MULTISCENE_AUTO_FALLBACK": False,
}

_AUTO_PROVIDERS = frozenset({"auto", "auto_product", "auto_provider"})
_ACTIVE_STATES = frozenset(
    {
        one_scene.ProviderState.ACCEPTED.value,
        one_scene.ProviderState.RUNNING.value,
    }
)


def _acquire_process_fence(
    store: product_video_poll_recovery.ProductVideoPollRecoveryStore,
    *,
    job_id: str,
) -> tuple[threading.Lock, Any] | None:
    fence_key = str(store.lease_path(job_id))
    with _FENCE_MAP_LOCK:
        process_lock = _PROCESS_FENCES.setdefault(fence_key, threading.Lock())
    if not process_lock.acquire(blocking=False):
        return None
    path = store.lease_path(job_id).with_name(
        f"{store.lease_path(job_id).stem}.recovery.fence"
    )
    try:
        handle = open(path, "a+b")
        handle.seek(0)
        if handle.read(1) != b"0":
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
            os.fsync(handle.fileno())
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return process_lock, handle
    except (BlockingIOError, OSError):
        try:
            handle.close()
        except UnboundLocalError:
            pass
        process_lock.release()
        return None


def _release_process_fence(fence: tuple[threading.Lock, Any] | None) -> None:
    if fence is None:
        return
    process_lock, handle = fence
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except (OSError, ValueError):
        pass
    finally:
        handle.close()
        process_lock.release()


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


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


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
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    return _json_safe(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if not isinstance(value, (list, tuple, set, frozenset)):
        return ()
    return tuple(_clean(item) for item in value if _clean(item))


def _asset_tuple(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    raw_items = value if isinstance(value, (list, tuple)) else (value,)
    assets: list[Any] = []
    for item in raw_items:
        if item is None or (isinstance(item, str) and not _clean(item)):
            continue
        assets.append(_json_safe(item))
    return tuple(assets)


def _normalize_transition(value: Any) -> str:
    raw = _clean(value).lower()
    if raw in _TRANSITION_ALIASES:
        return _TRANSITION_ALIASES[raw]
    token = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    if token in {"", "none"}:
        return "cut"
    if token not in _SUPPORTED_TRANSITIONS:
        raise ValueError("unsupported_scene_transition")
    return token


def _transition_duration(value: Any) -> float:
    try:
        duration = float(value if value is not None else DEFAULT_TRANSITION_DURATION_SECONDS)
    except (TypeError, ValueError, OverflowError):
        duration = DEFAULT_TRANSITION_DURATION_SECONDS
    return max(0.0, min(5.0, duration))


def _output_profile(aspect_ratio: str, final_assets: Mapping[str, Any]) -> dict[str, int]:
    raw = _mapping(final_assets.get("output_profile"))
    defaults = {
        "9:16": (360, 640),
        "16:9": (640, 360),
        "1:1": (512, 512),
        "4:5": (400, 500),
        "5:4": (500, 400),
    }
    default_width, default_height = defaults.get(_clean(aspect_ratio), (0, 0))
    try:
        width = int(raw.get("width") or default_width)
        height = int(raw.get("height") or default_height)
        fps = int(raw.get("fps") or DEFAULT_OUTPUT_FPS)
        sample_rate = int(raw.get("audio_sample_rate") or DEFAULT_AUDIO_SAMPLE_RATE)
        channels = int(raw.get("audio_channels") or DEFAULT_AUDIO_CHANNELS)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("output_profile_invalid") from exc
    if width <= 0 or height <= 0:
        # The compositor can derive geometry from the first real clip when the
        # locked flow carries a custom ratio without an explicit profile.
        width = 0
        height = 0
    return {
        "width": width - (width % 2) if width else 0,
        "height": height - (height % 2) if height else 0,
        "fps": max(1, min(120, fps)),
        "audio_sample_rate": max(8_000, min(192_000, sample_rate)),
        "audio_channels": max(1, min(8, channels)),
    }


def _composition_target_duration(
    graph: tuple["ProductVideoSceneContract", ...] | list["ProductVideoSceneContract"],
    *,
    transition_duration_seconds: float,
    fps: int,
) -> float:
    durations = [max(1.0, float(scene.duration_seconds)) for scene in graph]
    if not durations:
        return 0.0
    target = sum(durations)
    for index, scene in enumerate(graph[:-1]):
        if scene.transition in _CUT_TRANSITIONS:
            continue
        maximum = max(1.0 / max(1, fps), min(durations[index], durations[index + 1]) / 2.0)
        overlap = min(
            maximum,
            max(1.0 / max(1, fps), transition_duration_seconds),
        )
        target -= overlap
    return max(0.0, target)


def product_video_multiscene_flags(
    environ: Mapping[str, Any] | None = None,
) -> dict[str, bool]:
    source = os.environ if environ is None else environ
    return {
        name: _flag(source.get(name, default))
        for name, default in MULTISCENE_FLAG_DEFAULTS.items()
    }


def shared_product_video_multiscene_route() -> dict[str, Any]:
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
        "supported_modes": (video_engine_contract.VideoEngineMode.MULTI_SCENE.value,),
        "provider_enabled": True,
        "local_enabled": False,
        "route_id": ROUTE_ID,
        "blocker": "",
    }


def product_video_multiscene_contract(
    environ: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    flags = product_video_multiscene_flags(environ)
    return {
        "schema_version": MULTISCENE_SCHEMA_VERSION,
        "route_id": ROUTE_ID,
        "product_family": PRODUCT_FAMILY,
        "mode": MODE,
        "engine_adapter": ENGINE_ADAPTER,
        "scene_count": {"minimum": 2, "maximum": MAX_MULTISCENE_SCENES},
        "scene_required_fields": (
            "scene_id",
            "scene_index",
            "scene_specification",
            "duration_seconds",
            "aspect_ratio",
            "transition",
            "input_assets",
            "audio_requirement",
            "voice_requirement",
            "provider",
            "model",
            "idempotency_key",
            "status",
            "artifact_fingerprint",
        ),
        "same_provider_task_only": True,
        "accepted_task_limit_per_scene": 1,
        "automatic_resubmit": False,
        "automatic_fallback": False,
        "acceptance_unknown_policy": "manual_review_no_poll_no_resubmit",
        "completed_scene_policy": "fingerprint_and_reuse",
        "required_scene_failure_policy": "fail_or_waiting_review_never_drop",
        "final_compose_count": 1,
        "final_delivery_count": 1,
        "flags": flags,
    }


@dataclass(frozen=True)
class ProductVideoSceneContract:
    scene_id: str
    scene_index: int
    scene_specification: str
    original_user_prompt: str
    compiled_engine_prompt: str
    original_prompt_sha256: str
    compiled_prompt_sha256: str
    product_name: str
    required_visual_attributes: tuple[str, ...]
    forbidden_claims: tuple[str, ...]
    duration_seconds: int
    aspect_ratio: str
    transition: str
    input_assets: tuple[Any, ...]
    audio_requirement: Mapping[str, Any]
    voice_requirement: Mapping[str, Any]
    provider: str
    model: str
    idempotency_key: str
    status: str = one_scene.ProviderState.NOT_SUBMITTED.value
    artifact_fingerprint: str = ""


def compile_product_video_scene_graph(
    *,
    scenes: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    user_id: int,
    confirmation_id: str,
    language: str,
) -> tuple[ProductVideoSceneContract, ...]:
    raw_scenes = list(scenes or ())
    if not 2 <= len(raw_scenes) <= MAX_MULTISCENE_SCENES:
        raise ValueError("multiscene_scene_count_out_of_range")
    parsed_user_id = _positive_int(user_id, field_name="user_id")
    confirmation = _clean(confirmation_id)
    selected_language = _clean(language)
    if not confirmation:
        raise ValueError("confirmation_id_required")
    if not selected_language:
        raise ValueError("language_required")

    compiled: list[ProductVideoSceneContract] = []
    seen_ids: set[str] = set()
    expected_ratio = ""
    expected_provider = ""
    for expected_index, raw_value in enumerate(raw_scenes, start=1):
        raw = dict(raw_value or {})
        scene_id = _clean(raw.get("scene_id"))
        scene_index = _positive_int(raw.get("scene_index"), field_name="scene_index")
        specification = _clean(raw.get("scene_specification"))
        original_prompt = _clean(raw.get("original_user_prompt"))
        product_name = _clean(raw.get("product_name"))
        duration = _positive_int(raw.get("duration_seconds"), field_name="duration_seconds")
        ratio = _clean(raw.get("aspect_ratio"))
        transition = _normalize_transition(
            raw.get("transition") or raw.get("transition_out") or "cut"
        )
        provider = _clean(raw.get("provider")).lower()
        model = _clean(raw.get("model"))
        attributes = tuple(
            _clean(item)
            for item in (raw.get("required_visual_attributes") or ())
            if _clean(item)
        )
        forbidden = tuple(
            _clean(item)
            for item in (raw.get("forbidden_claims") or ())
            if _clean(item)
        )
        input_assets = _asset_tuple(raw.get("input_assets"))
        audio_requirement = _mapping(raw.get("audio_requirement"))
        voice_requirement = _mapping(raw.get("voice_requirement"))
        if scene_index != expected_index:
            raise ValueError("multiscene_scene_order_invalid")
        if not scene_id or scene_id in seen_ids:
            raise ValueError("multiscene_scene_id_invalid")
        if not specification:
            raise ValueError("scene_specification_required")
        if not input_assets:
            raise ValueError("scene_input_assets_required")
        if not ratio:
            raise ValueError("scene_aspect_ratio_required")
        if expected_ratio and ratio != expected_ratio:
            raise ValueError("multiscene_aspect_ratio_mismatch")
        if not provider or provider in _AUTO_PROVIDERS:
            raise ValueError("explicit_scene_provider_required")
        if expected_provider and provider != expected_provider:
            raise ValueError("multiscene_provider_route_mismatch")
        if not model:
            raise ValueError("scene_model_required")
        prompt = one_scene.compile_product_video_prompt(
            original_user_prompt=original_prompt,
            product_name=product_name,
            required_visual_attributes=attributes,
            forbidden_claims=forbidden,
            language=selected_language,
            aspect_ratio=ratio,
            duration_seconds=duration,
            scene_count=1,
        )
        identity = {
            "route_id": ROUTE_ID,
            "user_id": parsed_user_id,
            "confirmation_id": confirmation,
            "scene_id": scene_id,
            "scene_index": scene_index,
            "scene_specification": specification,
            "transition": transition,
            "original_prompt_sha256": prompt.original_prompt_sha256,
            "compiled_prompt_sha256": prompt.compiled_prompt_sha256,
            "input_assets": input_assets,
            "audio_requirement": audio_requirement,
            "voice_requirement": voice_requirement,
            "provider": provider,
            "model": model,
        }
        compiled.append(
            ProductVideoSceneContract(
                scene_id=scene_id,
                scene_index=scene_index,
                scene_specification=specification,
                original_user_prompt=prompt.original_user_prompt,
                compiled_engine_prompt=prompt.compiled_engine_prompt,
                original_prompt_sha256=prompt.original_prompt_sha256,
                compiled_prompt_sha256=prompt.compiled_prompt_sha256,
                product_name=prompt.product_name,
                required_visual_attributes=prompt.required_visual_attributes,
                forbidden_claims=prompt.forbidden_claims,
                duration_seconds=duration,
                aspect_ratio=ratio,
                transition=transition,
                input_assets=input_assets,
                audio_requirement=audio_requirement,
                voice_requirement=voice_requirement,
                provider=provider,
                model=model,
                idempotency_key=_sha256_text(_canonical_json(identity)),
            )
        )
        seen_ids.add(scene_id)
        expected_ratio = ratio
        expected_provider = provider
    return tuple(compiled)


def scene_graph_sha256(
    scene_graph: tuple[ProductVideoSceneContract, ...]
    | list[ProductVideoSceneContract],
) -> str:
    return _sha256_text(_canonical_json(list(scene_graph or ())))


def _validate_canonical_scene_graph(
    graph: tuple[ProductVideoSceneContract, ...],
    *,
    user_id: int,
    confirmation_id: str,
    language: str,
) -> None:
    parsed_user_id = _positive_int(user_id, field_name="user_id")
    confirmation = _clean(confirmation_id)
    selected_language = _clean(language)
    seen_scene_ids: set[str] = set()
    seen_idempotency_keys: set[str] = set()
    for scene in graph:
        if not _clean(scene.scene_id) or scene.scene_id in seen_scene_ids:
            raise ValueError("multiscene_scene_id_invalid")
        if not _clean(scene.model):
            raise ValueError("scene_model_required")
        if not scene.input_assets:
            raise ValueError("scene_input_assets_required")
        normalized_transition = _normalize_transition(scene.transition)
        if normalized_transition != scene.transition:
            raise ValueError("multiscene_scene_transition_invalid")
        if _sha256_text(scene.original_user_prompt) != scene.original_prompt_sha256:
            raise ValueError("original_prompt_hash_mismatch")
        if _sha256_text(scene.compiled_engine_prompt) != scene.compiled_prompt_sha256:
            raise ValueError("compiled_prompt_hash_mismatch")
        expected_prompt = one_scene.compile_product_video_prompt(
            original_user_prompt=scene.original_user_prompt,
            product_name=scene.product_name,
            required_visual_attributes=scene.required_visual_attributes,
            forbidden_claims=scene.forbidden_claims,
            language=selected_language,
            aspect_ratio=scene.aspect_ratio,
            duration_seconds=scene.duration_seconds,
            scene_count=1,
        )
        if (
            scene.compiled_engine_prompt != expected_prompt.compiled_engine_prompt
            or scene.original_prompt_sha256 != expected_prompt.original_prompt_sha256
            or scene.compiled_prompt_sha256 != expected_prompt.compiled_prompt_sha256
        ):
            raise ValueError("multiscene_scene_prompt_contract_invalid")
        identity = {
            "route_id": ROUTE_ID,
            "user_id": parsed_user_id,
            "confirmation_id": confirmation,
            "scene_id": scene.scene_id,
            "scene_index": scene.scene_index,
            "scene_specification": scene.scene_specification,
            "transition": normalized_transition,
            "original_prompt_sha256": scene.original_prompt_sha256,
            "compiled_prompt_sha256": scene.compiled_prompt_sha256,
            "input_assets": scene.input_assets,
            "audio_requirement": scene.audio_requirement,
            "voice_requirement": scene.voice_requirement,
            "provider": scene.provider,
            "model": scene.model,
        }
        expected_key = _sha256_text(_canonical_json(identity))
        if (
            not _clean(scene.idempotency_key)
            or scene.idempotency_key in seen_idempotency_keys
            or scene.idempotency_key != expected_key
        ):
            raise ValueError("multiscene_scene_idempotency_invalid")
        if (
            _clean(scene.status).upper()
            != one_scene.ProviderState.NOT_SUBMITTED.value
            or _clean(scene.artifact_fingerprint)
        ):
            raise ValueError("multiscene_scene_initial_state_invalid")
        seen_scene_ids.add(scene.scene_id)
        seen_idempotency_keys.add(scene.idempotency_key)


def build_product_video_multiscene_request(
    *,
    user_id: int,
    confirmation_id: str,
    language: str,
    scene_graph: tuple[ProductVideoSceneContract, ...]
    | list[ProductVideoSceneContract],
    input_assets: tuple[Any, ...] | list[Any],
    aspect_ratio: str,
    audio_policy: Mapping[str, Any],
    voice_policy: Mapping[str, Any],
    final_assets: Mapping[str, Any],
    provider_selection: str,
    explicit_confirmation_receipt: Mapping[str, Any],
    runtime_sha: str,
    expected_worker_sha: str,
    admin_no_charge: bool = False,
    charge_plan: Mapping[str, Any] | None = None,
) -> video_engine_contract.VideoEngineRequest:
    graph = tuple(scene_graph or ())
    if not 2 <= len(graph) <= MAX_MULTISCENE_SCENES:
        raise ValueError("multiscene_scene_count_out_of_range")
    if [item.scene_index for item in graph] != list(range(1, len(graph) + 1)):
        raise ValueError("multiscene_scene_order_invalid")
    ratio = _clean(aspect_ratio)
    provider = _clean(provider_selection).lower()
    if not ratio or any(item.aspect_ratio != ratio for item in graph):
        raise ValueError("multiscene_aspect_ratio_mismatch")
    if not provider or provider in _AUTO_PROVIDERS:
        raise ValueError("explicit_scene_provider_required")
    if any(item.provider != provider for item in graph):
        raise ValueError("multiscene_provider_route_mismatch")
    _validate_canonical_scene_graph(
        graph,
        user_id=user_id,
        confirmation_id=confirmation_id,
        language=language,
    )
    parent_input_assets = _asset_tuple(input_assets)
    if not parent_input_assets:
        raise ValueError("product_video_input_assets_required")
    graph_payload = [_json_safe(item) for item in graph]
    graph_hash = scene_graph_sha256(graph)
    scene_order = [item.scene_index for item in graph]
    final_assets_snapshot = _mapping(final_assets)
    output_profile = _output_profile(ratio, final_assets_snapshot)
    transition_plan = [item.transition for item in graph[:-1]]
    transition_duration_seconds = _transition_duration(
        final_assets_snapshot.get("transition_duration_seconds")
    )
    target_duration_seconds = _composition_target_duration(
        graph,
        transition_duration_seconds=transition_duration_seconds,
        fps=output_profile["fps"],
    )
    payload = {
        "route_id": ROUTE_ID,
        "product_family": PRODUCT_FAMILY,
        "scene_count": len(graph),
        "scene_order": scene_order,
        "scene_graph_sha256": graph_hash,
        "scenes": graph_payload,
        "transition_plan": transition_plan,
        "transition_duration_seconds": transition_duration_seconds,
        "output_profile": output_profile,
        "target_duration_seconds": target_duration_seconds,
        "final_assets": final_assets_snapshot,
        "admin_no_charge": bool(admin_no_charge),
        "charge_plan": _mapping(charge_plan),
        "automatic_resubmit": False,
        "automatic_fallback": False,
    }
    approved_plan = {
        "route_id": ROUTE_ID,
        "product_family": PRODUCT_FAMILY,
        "approved": True,
        "scene_count": len(graph),
        "scene_order": scene_order,
        "scene_graph_sha256": graph_hash,
        "transition_plan": transition_plan,
        "transition_duration_seconds": transition_duration_seconds,
        "output_profile": output_profile,
        "target_duration_seconds": target_duration_seconds,
        "scenes": graph_payload,
    }
    total_duration = sum(item.duration_seconds for item in graph)
    common = {
        "user_id": user_id,
        "language": language,
        "approved_plan": approved_plan,
        "input_assets": parent_input_assets,
        "aspect_ratio": ratio,
        "duration_profile": {
            "duration_seconds": total_duration,
            "target_duration_seconds": target_duration_seconds,
            "scene_durations": [item.duration_seconds for item in graph],
            "transition_plan": transition_plan,
            "transition_duration_seconds": transition_duration_seconds,
            "output_profile": output_profile,
            "profile": "product_video_multiscene",
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
        mode=video_engine_contract.VideoEngineMode.MULTI_SCENE,
        payload=payload,
        **common,
    )
    return video_engine_contract.VideoEngineRequest(
        request_id=f"{ROUTE_ID}:{key[:20]}",
        confirmation_id=confirmation_id,
        idempotency_key=key,
        product_type=video_engine_contract.VideoProduct.PRODUCT_VIDEO,
        mode=video_engine_contract.VideoEngineMode.MULTI_SCENE,
        explicit_confirmation_receipt=dict(explicit_confirmation_receipt),
        confirmed=True,
        payload=payload,
        **common,
    )


@dataclass
class ProductVideoMultisceneLedger:
    jobs_by_idempotency: dict[str, video_engine_contract.VideoEngineJob] = field(
        default_factory=dict
    )


def _request_snapshot(
    request: video_engine_contract.VideoEngineRequest,
) -> dict[str, Any]:
    return {
        "request_id": request.request_id,
        "idempotency_key": request.idempotency_key,
        "user_id": request.user_id,
        "language": request.language,
        "product_type": request.product_type.value,
        "mode": request.mode.value,
        "input_assets": _json_safe(request.input_assets),
        "aspect_ratio": request.aspect_ratio,
        "duration_profile": _json_safe(request.duration_profile),
        "audio_policy": _json_safe(request.audio_policy),
        "voice_policy": _json_safe(request.voice_policy),
        "provider_selection": request.provider_selection,
        "runtime_sha": request.runtime_sha,
        "expected_worker_sha": request.expected_worker_sha,
        "payload": _json_safe(request.payload),
    }


def _new_counters(value: Any = None) -> dict[str, int]:
    current = dict(value) if isinstance(value, Mapping) else {}
    names = (
        "scene_submit_intents",
        "fixture_provider_submit_calls",
        "production_provider_submits",
        "real_provider_calls",
        "paid_provider_calls",
        "provider_status_get_calls",
        "artifact_fetch_calls",
        "compose_count",
        "delivery_count",
        "receipt_count",
        "charge_count",
        "terminal_report_count",
        "wallet_mutations",
        "production_telegram_deliveries",
    )
    return {name: _nonnegative_int(current.get(name)) for name in names}


def _scene_records(
    scene_graph: tuple[ProductVideoSceneContract, ...]
    | list[ProductVideoSceneContract],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for scene in scene_graph:
        record = _json_safe(scene)
        record.update(
            {
                "provider_state": one_scene.ProviderState.NOT_SUBMITTED.value,
                "provider_task_id": "",
                "artifact_path": "",
                "artifact_url": "",
                "artifact_fingerprint": "",
                "validation": {},
                "next_poll_epoch": 0.0,
                "blocker": "",
            }
        )
        records.append(record)
    return records


def _durable_scene_artifact_truth(scene: Mapping[str, Any]) -> tuple[bool, str]:
    expected_fingerprint = _clean(scene.get("artifact_fingerprint"))
    artifact_path = _clean(scene.get("artifact_path"))
    if not expected_fingerprint:
        return False, ""
    path = Path(artifact_path)
    if not path.is_file():
        return False, "scene_durable_artifact_missing"
    try:
        actual_fingerprint = _sha256_file(path)
    except OSError:
        return False, "scene_durable_artifact_missing"
    if actual_fingerprint != expected_fingerprint:
        return False, "scene_durable_artifact_fingerprint_mismatch"
    return True, ""


def _checkpoint_result(
    checkpoint: Mapping[str, Any] | None,
    *,
    ok: bool,
    blocker: str = "",
    outcome: str = "blocked",
    submitted_scene_count: int = 0,
    idempotent_replay: bool = False,
    completed_scenes_reused: int = 0,
    stale_lease_recovered: bool = False,
) -> dict[str, Any]:
    current = dict(checkpoint or {})
    scenes = list(current.get("scenes") or ())
    counters = _new_counters(current.get("counters"))
    completed_count = sum(_durable_scene_artifact_truth(scene)[0] for scene in scenes)
    return {
        "ok": bool(ok),
        "submitted": submitted_scene_count > 0,
        "submitted_scene_count": _nonnegative_int(submitted_scene_count),
        "idempotent_replay": bool(idempotent_replay),
        "blocker": _clean(blocker),
        "outcome": _clean(outcome),
        "job_id": _clean(current.get("job_id")),
        "job_count": 1 if current.get("job_id") else 0,
        "scene_count": len(scenes),
        "scene_order": [int(scene.get("scene_index") or 0) for scene in scenes],
        "completed_scene_count": completed_count,
        "completed_scenes_reused": _nonnegative_int(completed_scenes_reused),
        "terminal_state": _clean(current.get("terminal_state")),
        "final_artifact_path": _clean(current.get("final_artifact_path")),
        "final_validation": dict(current.get("final_validation") or {}),
        "stale_lease_recovered": bool(stale_lease_recovered),
        **counters,
    }


def _checkpoint_replay_truth(checkpoint: Mapping[str, Any]) -> tuple[bool, str, str]:
    terminal_blocker, terminal_outcome = _persisted_terminal_blocker(checkpoint)
    if terminal_blocker:
        return False, terminal_blocker, terminal_outcome
    terminal_report = dict(checkpoint.get("terminal_report") or {})
    if terminal_report.get("emitted"):
        return True, "", "final_delivered"
    states = {
        _clean(scene.get("provider_state")).upper()
        for scene in checkpoint.get("scenes", ())
    }
    if one_scene.ProviderState.ACCEPTANCE_UNKNOWN.value in states:
        return False, "scene_provider_acceptance_unknown", "waiting_review"
    if one_scene.ProviderState.FAILED.value in states:
        return False, _clean(checkpoint.get("blocker") or "required_scene_failed"), "failed_no_charge"
    blocker = _clean(checkpoint.get("blocker"))
    if blocker:
        return False, blocker, "waiting_review"
    return True, "", "waiting_provider"


def _existing_dispatch_response(
    existing: Mapping[str, Any],
    *,
    request: video_engine_contract.VideoEngineRequest,
    graph: tuple[ProductVideoSceneContract, ...],
    readiness: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        _clean(existing.get("idempotency_key")) != request.idempotency_key
        or _clean(existing.get("scene_graph_sha256")) != scene_graph_sha256(graph)
        or _clean(existing.get("expected_worker_sha")) != request.expected_worker_sha
    ):
        raise product_video_poll_recovery.RecoveryCheckpointError(
            "multiscene_checkpoint_identity_mismatch"
        )
    ok, blocker, outcome = _checkpoint_replay_truth(existing)
    return {
        **_checkpoint_result(
            existing,
            ok=ok,
            blocker=blocker,
            outcome=outcome,
            idempotent_replay=True,
        ),
        "readiness": dict(readiness),
    }


def _multiscene_readiness(
    request: video_engine_contract.VideoEngineRequest,
    *,
    scene_graph: tuple[ProductVideoSceneContract, ...]
    | list[ProductVideoSceneContract],
    manifest: Mapping[str, Any],
    runtime_sha: str,
    environ: Mapping[str, Any] | None,
    public_request: bool,
) -> dict[str, Any]:
    flags = product_video_multiscene_flags(environ)
    graph = tuple(scene_graph or ())
    blocker = ""
    if not flags["PRODUCT_VIDEO_MULTISCENE_ENGINE_ENABLED"]:
        blocker = "product_video_multiscene_disabled"
    elif public_request and not flags["PRODUCT_VIDEO_MULTISCENE_PUBLIC_ALLOWED"]:
        blocker = "product_video_multiscene_public_disabled"
    elif flags["PRODUCT_VIDEO_MULTISCENE_AUTO_RESUBMIT"]:
        blocker = "automatic_resubmit_forbidden"
    elif flags["PRODUCT_VIDEO_MULTISCENE_AUTO_FALLBACK"]:
        blocker = "automatic_fallback_forbidden"
    elif request.product_type is not video_engine_contract.VideoProduct.PRODUCT_VIDEO:
        blocker = "product_video_required"
    elif request.mode is not video_engine_contract.VideoEngineMode.MULTI_SCENE:
        blocker = "multi_scene_required"
    elif not 2 <= len(graph) <= MAX_MULTISCENE_SCENES:
        blocker = "multiscene_scene_count_out_of_range"
    elif request.payload.get("scene_graph_sha256") != scene_graph_sha256(graph):
        blocker = "scene_graph_hash_mismatch"
    elif any(scene.provider != request.provider_selection for scene in graph):
        blocker = "multiscene_provider_route_mismatch"
    if not blocker:
        for scene in graph:
            if _flag(scene.audio_requirement.get("required")) and not _clean(
                scene.audio_requirement.get("artifact_path")
            ):
                blocker = "scene_audio_artifact_missing"
                break
            if _flag(scene.voice_requirement.get("required")) and not _clean(
                scene.voice_requirement.get("artifact_path")
            ):
                blocker = "scene_voice_artifact_missing"
                break
    shared = video_engine_contract.evaluate_readiness(
        request,
        manifest=manifest,
        runtime_sha=runtime_sha,
        environ=environ,
    )
    if not blocker and not shared.get("ready"):
        blocker = _clean(shared.get("blocker") or "worker_not_ready")
    capabilities = set(_sequence(manifest.get("capabilities")))
    if not blocker and not set(REQUIRED_WORKER_CAPABILITIES).issubset(capabilities):
        blocker = "worker_capability_mismatch"
    if not blocker and not _flag(manifest.get("artifact_ready")):
        blocker = "worker_artifact_not_ready"
    if not blocker and ENGINE_ADAPTER not in set(_sequence(manifest.get("engine_adapters"))):
        blocker = "worker_adapter_missing"
    if not blocker and request.provider_selection not in set(
        _sequence(manifest.get("provider_routes"))
    ):
        blocker = "explicit_provider_route_missing"
    if not blocker and request.provider_selection == "fake_provider":
        if public_request or not _flag(manifest.get("offline_fixture")):
            blocker = "fake_provider_offline_only"
    elif not blocker and not flags["PRODUCT_VIDEO_MULTISCENE_REAL_PROVIDER_ENABLED"]:
        blocker = "real_provider_disabled"
    return {
        "ready": not blocker,
        "submit_allowed": not blocker,
        "blocker": blocker,
        "flags": flags,
        "shared_readiness": shared,
        "route": shared_product_video_multiscene_route(),
    }


def _job_factory(
    request: video_engine_contract.VideoEngineRequest,
    route: Mapping[str, Any],
) -> video_engine_contract.VideoEngineJob:
    return video_engine_contract.VideoEngineJob(
        job_id=f"p29e-{request.idempotency_key[:24]}",
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


def _save_checkpoint(
    store: product_video_poll_recovery.ProductVideoPollRecoveryStore,
    checkpoint: dict[str, Any],
    *,
    now_epoch: float,
) -> dict[str, Any]:
    checkpoint["updated_at_epoch"] = float(now_epoch)
    store.save(checkpoint)
    return checkpoint


def dispatch_product_video_multiscene(
    request: video_engine_contract.VideoEngineRequest,
    *,
    scene_graph: tuple[ProductVideoSceneContract, ...]
    | list[ProductVideoSceneContract],
    manifest: Mapping[str, Any],
    runtime_sha: str,
    environ: Mapping[str, Any] | None,
    store: product_video_poll_recovery.ProductVideoPollRecoveryStore,
    ledger: ProductVideoMultisceneLedger,
    scene_submitter: Callable[[dict[str, Any]], Mapping[str, Any]],
    public_request: bool = False,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    now = time.time() if now_epoch is None else float(now_epoch)
    graph = tuple(scene_graph or ())
    parent_job_id = f"p29e-{request.idempotency_key[:24]}"
    readiness = _multiscene_readiness(
        request,
        scene_graph=graph,
        manifest=manifest,
        runtime_sha=runtime_sha,
        environ=environ,
        public_request=public_request,
    )
    try:
        existing = store.load(parent_job_id)
    except product_video_poll_recovery.RecoveryCheckpointNotFound:
        existing = None
    if existing is not None:
        return _existing_dispatch_response(
            existing,
            request=request,
            graph=graph,
            readiness=readiness,
        )
    if not readiness["ready"]:
        return {
            **_checkpoint_result(
                None,
                ok=False,
                blocker=readiness["blocker"],
            ),
            "readiness": readiness,
        }

    fence = _acquire_process_fence(store, job_id=parent_job_id)
    if fence is None:
        return {
            **_checkpoint_result(
                None,
                ok=False,
                blocker="multiscene_dispatch_fence_active",
                outcome="blocked",
            ),
            "readiness": readiness,
        }
    claim_owner = f"dispatch-{os.getpid()}-{time.time_ns()}"
    try:
        claim = store.acquire_lease(
            job_id=parent_job_id,
            owner=claim_owner,
            now_epoch=now,
            lease_seconds=DEFAULT_RECOVERY_LEASE_SECONDS,
        )
    except Exception:
        _release_process_fence(fence)
        raise
    if not claim.get("acquired"):
        _release_process_fence(fence)
        try:
            existing = store.load(parent_job_id)
        except product_video_poll_recovery.RecoveryCheckpointNotFound:
            return {
                **_checkpoint_result(
                    None,
                    ok=False,
                    blocker="multiscene_dispatch_active",
                    outcome="blocked",
                ),
                "readiness": readiness,
            }
        return _existing_dispatch_response(
            existing,
            request=request,
            graph=graph,
            readiness=readiness,
        )

    token = _clean(claim.get("token"))
    try:
        return _dispatch_product_video_multiscene_claimed(
            request,
            scene_graph=graph,
            manifest=manifest,
            runtime_sha=runtime_sha,
            environ=environ,
            store=store,
            ledger=ledger,
            scene_submitter=scene_submitter,
            public_request=public_request,
            now_epoch=now,
        )
    finally:
        store.release_lease(job_id=parent_job_id, token=token)
        _release_process_fence(fence)


def _dispatch_product_video_multiscene_claimed(
    request: video_engine_contract.VideoEngineRequest,
    *,
    scene_graph: tuple[ProductVideoSceneContract, ...]
    | list[ProductVideoSceneContract],
    manifest: Mapping[str, Any],
    runtime_sha: str,
    environ: Mapping[str, Any] | None,
    store: product_video_poll_recovery.ProductVideoPollRecoveryStore,
    ledger: ProductVideoMultisceneLedger,
    scene_submitter: Callable[[dict[str, Any]], Mapping[str, Any]],
    public_request: bool = False,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    now = time.time() if now_epoch is None else float(now_epoch)
    graph = tuple(scene_graph or ())
    readiness = _multiscene_readiness(
        request,
        scene_graph=graph,
        manifest=manifest,
        runtime_sha=runtime_sha,
        environ=environ,
        public_request=public_request,
    )
    if not readiness["ready"]:
        return {
            **_checkpoint_result(
                None,
                ok=False,
                blocker=readiness["blocker"],
            ),
            "readiness": readiness,
        }

    parent_job_id = f"p29e-{request.idempotency_key[:24]}"
    try:
        existing = store.load(parent_job_id)
    except product_video_poll_recovery.RecoveryCheckpointNotFound:
        existing = None
    if existing is not None:
        return _existing_dispatch_response(
            existing,
            request=request,
            graph=graph,
            readiness=readiness,
        )

    guarded = video_engine_contract.guarded_submit(
        request,
        manifest=manifest,
        runtime_sha=runtime_sha,
        jobs_by_idempotency=ledger.jobs_by_idempotency,
        submitter=_job_factory,
        environ=environ,
    )
    if guarded.get("idempotent_replay"):
        return {
            **_checkpoint_result(
                None,
                ok=False,
                blocker="multiscene_checkpoint_missing_for_existing_job",
                outcome="waiting_review",
                idempotent_replay=True,
            ),
            "readiness": readiness,
        }
    job = guarded.get("job")
    if not isinstance(job, video_engine_contract.VideoEngineJob):
        return {
            **_checkpoint_result(
                None,
                ok=False,
                blocker=_clean(guarded.get("blocker") or "engine_job_not_created"),
            ),
            "readiness": readiness,
        }
    checkpoint = {
        "schema_version": MULTISCENE_SCHEMA_VERSION,
        "job_id": job.job_id,
        "request_id": request.request_id,
        "idempotency_key": request.idempotency_key,
        "product_family": PRODUCT_FAMILY,
        "mode": MODE,
        "engine_mode": request.mode.value,
        "scene_graph_sha256": scene_graph_sha256(graph),
        "scene_count": len(graph),
        "request": _request_snapshot(request),
        "expected_worker_sha": request.expected_worker_sha,
        "scenes": _scene_records(graph),
        "counters": _new_counters(),
        "compose": {},
        "delivery": {},
        "receipt": {},
        "charge": {},
        "terminal_report": {},
        "terminal_state": "",
        "blocker": "",
        "final_artifact_path": "",
        "final_validation": {},
        "updated_at_epoch": now,
    }
    checkpoint = store.save(checkpoint)
    submitted_scene_count = 0
    for scene in checkpoint["scenes"]:
        counters = _new_counters(checkpoint.get("counters"))
        scene["provider_state"] = one_scene.ProviderState.SUBMITTING.value
        counters["scene_submit_intents"] += 1
        if request.provider_selection == "fake_provider":
            counters["fixture_provider_submit_calls"] += 1
        else:
            counters["production_provider_submits"] += 1
            counters["real_provider_calls"] += 1
        checkpoint["counters"] = counters
        checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
        submitted_scene_count += 1
        payload = {
            "route_id": ROUTE_ID,
            "job_id": job.job_id,
            "parent_idempotency_key": request.idempotency_key,
            "scene_id": scene["scene_id"],
            "scene_index": scene["scene_index"],
            "scene_idempotency_key": scene["idempotency_key"],
            "scene_specification": scene["scene_specification"],
            "original_user_prompt": scene["original_user_prompt"],
            "compiled_engine_prompt": scene["compiled_engine_prompt"],
            "original_prompt_sha256": scene["original_prompt_sha256"],
            "compiled_prompt_sha256": scene["compiled_prompt_sha256"],
            "input_assets": list(scene["input_assets"]),
            "duration_seconds": scene["duration_seconds"],
            "aspect_ratio": scene["aspect_ratio"],
            "transition": scene["transition"],
            "audio_requirement": dict(scene["audio_requirement"]),
            "voice_requirement": dict(scene["voice_requirement"]),
            "provider": scene["provider"],
            "model": scene["model"],
            "automatic_resubmit": False,
            "automatic_fallback": False,
        }
        try:
            response = dict(scene_submitter(payload) or {})
        except (one_scene.ProviderAcceptanceUnknown, TimeoutError) as exc:
            scene["provider_state"] = one_scene.ProviderState.ACCEPTANCE_UNKNOWN.value
            scene["blocker"] = "scene_provider_acceptance_unknown"
            scene["safe_error"] = type(exc).__name__
            checkpoint["blocker"] = "scene_provider_acceptance_unknown"
            checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
            return {
                **_checkpoint_result(
                    checkpoint,
                    ok=False,
                    blocker="scene_provider_acceptance_unknown",
                    outcome="waiting_review",
                    submitted_scene_count=submitted_scene_count,
                ),
                "readiness": readiness,
            }
        except Exception as exc:
            scene["provider_state"] = one_scene.ProviderState.FAILED.value
            scene["blocker"] = "scene_provider_submit_failed"
            scene["safe_error"] = type(exc).__name__
            checkpoint["terminal_state"] = "failed_no_charge"
            checkpoint["blocker"] = "scene_provider_submit_failed"
            checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
            return {
                **_checkpoint_result(
                    checkpoint,
                    ok=False,
                    blocker="scene_provider_submit_failed",
                    outcome="failed_no_charge",
                    submitted_scene_count=submitted_scene_count,
                ),
                "readiness": readiness,
            }
        response_state = _clean(response.get("state") or response.get("status")).upper()
        response_task_id = _clean(response.get("provider_task_id"))
        response_provider = _clean(response.get("provider") or scene["provider"]).lower()
        response_index = _nonnegative_int(response.get("scene_index"))
        paid = bool(response.get("paid"))
        if paid:
            counters = _new_counters(checkpoint.get("counters"))
            counters["paid_provider_calls"] += 1
            checkpoint["counters"] = counters
        blocker = ""
        if response_index != int(scene["scene_index"]):
            blocker = "scene_response_index_mismatch"
        elif response_provider != scene["provider"]:
            blocker = "scene_provider_identity_mismatch"
        elif paid and scene["provider"] == "fake_provider":
            blocker = "fake_provider_cannot_be_paid"
        elif response_state not in {
            one_scene.ProviderState.ACCEPTED.value,
            one_scene.ProviderState.RUNNING.value,
            one_scene.ProviderState.COMPLETED.value,
            one_scene.ProviderState.FAILED.value,
        }:
            blocker = "scene_provider_acceptance_unknown"
            response_state = one_scene.ProviderState.ACCEPTANCE_UNKNOWN.value
        elif not response_task_id:
            blocker = "scene_provider_task_identity_missing"
            response_state = one_scene.ProviderState.ACCEPTANCE_UNKNOWN.value
        elif response_state == one_scene.ProviderState.FAILED.value:
            blocker = "required_scene_failed"
        scene.update(
            {
                "provider_state": response_state,
                "provider_task_id": response_task_id,
                "provider": response_provider,
                "artifact_path": _clean(response.get("artifact_path")),
                "artifact_url": _clean(
                    response.get("artifact_url") or response.get("output_url")
                ),
                "paid": paid,
                "blocker": blocker,
                "next_poll_epoch": now,
            }
        )
        if blocker == "scene_provider_acceptance_unknown":
            checkpoint["blocker"] = blocker
        elif blocker:
            checkpoint["blocker"] = blocker
            checkpoint["terminal_state"] = "failed_no_charge"
        checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
        if blocker:
            return {
                **_checkpoint_result(
                    checkpoint,
                    ok=False,
                    blocker=blocker,
                    outcome=(
                        "waiting_review"
                        if blocker == "scene_provider_acceptance_unknown"
                        else "failed_no_charge"
                    ),
                    submitted_scene_count=submitted_scene_count,
                ),
                "readiness": readiness,
            }
    checkpoint["blocker"] = ""
    checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
    return {
        **_checkpoint_result(
            checkpoint,
            ok=True,
            outcome="waiting_provider",
            submitted_scene_count=submitted_scene_count,
        ),
        "readiness": readiness,
    }


def _scene_artifact_path(
    store: product_video_poll_recovery.ProductVideoPollRecoveryStore,
    *,
    job_id: str,
    scene_index: int,
) -> Path:
    job_key = _sha256_text(_clean(job_id))
    directory = store.artifacts_dir / job_key
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"scene_{scene_index:03d}.mp4"


def _copy_scene_artifact(source_path: str, destination: Path) -> str:
    source = Path(source_path)
    if not source.is_file():
        return ""
    if source.resolve() != destination.resolve():
        temporary = destination.with_name(
            f".{destination.name}.{os.getpid()}.{time.time_ns()}.tmp"
        )
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    return str(destination)


def _pipeline_scenes(checkpoint: Mapping[str, Any]) -> list[pipeline.SceneSpec]:
    return [
        pipeline.SceneSpec(
            scene_id=int(scene["scene_index"]),
            title=_clean(scene["scene_specification"]),
            visual_prompt=_clean(scene["original_user_prompt"]),
            video_prompt=_clean(scene["compiled_engine_prompt"]),
            narration_text=None,
            target_duration_sec=float(scene["duration_seconds"]),
            aspect_ratio=_clean(scene["aspect_ratio"]),
            transition=_clean(scene.get("transition") or "cut"),
            seed_image_path=(
                _clean(scene.get("input_assets", [""])[0])
                if scene.get("input_assets")
                else None
            ),
            provider_params={
                "provider": _clean(scene["provider"]),
                "model": _clean(scene["model"]),
                "scene_idempotency_key": _clean(scene["idempotency_key"]),
            },
        )
        for scene in checkpoint.get("scenes", ())
    ]


def _default_compositor(
    *,
    store: product_video_poll_recovery.ProductVideoPollRecoveryStore,
    checkpoint: Mapping[str, Any],
    scene_clip_paths: Mapping[int, str],
) -> dict[str, Any]:
    request = dict(checkpoint.get("request") or {})
    payload = dict(request.get("payload") or {})
    final_assets = dict(payload.get("final_assets") or {})
    aspect_ratio = _clean(request.get("aspect_ratio") or payload.get("aspect_ratio"))
    output_profile = _output_profile(aspect_ratio, final_assets)
    duration_profile = dict(request.get("duration_profile") or {})
    output_profile.update(
        {
            key: value
            for key, value in _mapping(duration_profile.get("output_profile")).items()
            if key in output_profile
        }
    )
    transition_duration_seconds = _transition_duration(
        payload.get("transition_duration_seconds")
        if payload.get("transition_duration_seconds") is not None
        else final_assets.get("transition_duration_seconds")
    )
    audio_policy = dict(request.get("audio_policy") or {})
    voice_policy = dict(request.get("voice_policy") or {})
    preserve_scene_audio = bool(
        _flag(audio_policy.get("source_audio"))
        or _flag(audio_policy.get("preserve_source_audio"))
        or _flag(audio_policy.get("preserve_scene_audio"))
    )
    scenes = _pipeline_scenes(checkpoint)
    workspace = store.root / "multiscene" / _sha256_text(_clean(checkpoint.get("job_id")))
    workspace.mkdir(parents=True, exist_ok=True)
    base = pipeline.finalize_multiscene_scene_clips(
        user_id=str(request.get("user_id") or ""),
        job_id=_clean(checkpoint.get("job_id")),
        workspace_dir=str(workspace),
        scenes=scenes,
        scene_clip_paths=dict(scene_clip_paths),
        bgm_audio_path=None,
        logo_path=None,
        enable_voice=False,
        enable_subtitle=False,
        enable_logo=False,
        output_width=output_profile["width"] or None,
        output_height=output_profile["height"] or None,
        output_fps=output_profile["fps"],
        transition_duration_sec=transition_duration_seconds,
        preserve_scene_audio=preserve_scene_audio,
        audio_sample_rate=output_profile["audio_sample_rate"],
        audio_channels=output_profile["audio_channels"],
    )
    if not base.get("ok"):
        return dict(base)
    voice_path = _clean(final_assets.get("voice_audio_path"))
    bgm_path = _clean(final_assets.get("bgm_audio_path"))
    logo_path = _clean(final_assets.get("logo_path"))
    logo_text = _clean(final_assets.get("logo_text"))
    enable_subtitle = _flag(final_assets.get("enable_subtitle"))
    requested_assets = any(
        (voice_path, bgm_path, logo_path, logo_text, enable_subtitle)
    )
    if not requested_assets:
        return dict(base)
    subtitle_path = ""
    if enable_subtitle:
        subtitle_path = pipeline.build_scene_subtitle(
            scenes,
            [float(item.target_duration_sec) for item in scenes],
            str(workspace / "scene_subtitles.srt"),
        )
    master_path = _clean(base.get("master_video_path"))
    output_path = workspace / "final_output_with_assets.mp4"
    final_path = pipeline.mux_final_multiscene_video(
        master_video_path=master_path,
        output_path=str(output_path),
        voice_audio_path=voice_path or None,
        bgm_audio_path=bgm_path or None,
        subtitle_path=subtitle_path or None,
        logo_path=logo_path or None,
        logo_text=logo_text or None,
        burn_subtitles=enable_subtitle,
        logo_position=_clean(final_assets.get("logo_position") or "bottom_right"),
        preserve_master_audio=preserve_scene_audio,
        audio_sample_rate=output_profile["audio_sample_rate"],
        audio_channels=output_profile["audio_channels"],
    )
    if _sha256_file(final_path) == _sha256_file(master_path):
        return {**dict(base), "ok": False, "error": "final_assets_not_applied"}
    return {
        **dict(base),
        "ok": True,
        "final_video_path": final_path,
        "subtitle_path": subtitle_path,
    }


def _recovery_result(
    checkpoint: Mapping[str, Any],
    *,
    ok: bool,
    blocker: str = "",
    outcome: str,
    idempotent_replay: bool = False,
    completed_scenes_reused: int = 0,
    stale_lease_recovered: bool = False,
) -> dict[str, Any]:
    return _checkpoint_result(
        checkpoint,
        ok=ok,
        blocker=blocker,
        outcome=outcome,
        idempotent_replay=idempotent_replay,
        completed_scenes_reused=completed_scenes_reused,
        stale_lease_recovered=stale_lease_recovered,
    )


def _persisted_terminal_blocker(checkpoint: Mapping[str, Any]) -> tuple[str, str]:
    if _clean(checkpoint.get("terminal_state")) == "failed_no_charge":
        return _clean(checkpoint.get("blocker") or "multiscene_terminal_failure"), "failed_no_charge"
    delivery = dict(checkpoint.get("delivery") or {})
    if delivery.get("accepted") and not _clean(delivery.get("message_id")):
        return "delivery_record_invalid", "waiting_review"
    receipt = dict(checkpoint.get("receipt") or {})
    if receipt.get("persisted") and not _clean(receipt.get("receipt_id")):
        return "delivery_receipt_invalid", "waiting_review"
    charge = dict(checkpoint.get("charge") or {})
    if charge.get("recorded"):
        request_payload = dict(checkpoint.get("request", {}).get("payload") or {})
        if not bool(request_payload.get("admin_no_charge")) and _nonnegative_int(
            charge.get("amount_xu")
        ) <= 0:
            return "charge_record_invalid", "waiting_review"
    report = dict(checkpoint.get("terminal_report") or {})
    if report.get("emitted") and not _clean(report.get("report_id")):
        return "terminal_report_invalid", "waiting_review"
    compose = dict(checkpoint.get("compose") or {})
    if (
        _clean(compose.get("state")).upper()
        in {"INTENT_PERSISTED", "ACCEPTANCE_UNKNOWN"}
        and not compose.get("completed")
    ):
        return "compose_acceptance_unknown", "waiting_review"
    for key, label, success_field in (
        ("delivery", "delivery", "accepted"),
        ("receipt", "receipt", "persisted"),
        ("charge", "charge", "recorded"),
        ("terminal_report", "report", "emitted"),
    ):
        stage = dict(checkpoint.get(key) or {})
        if stage.get(success_field):
            continue
        state = _clean(stage.get("state")).upper()
        if state in {"INTENT_PERSISTED", "ACCEPTANCE_UNKNOWN"}:
            return f"{label}_acceptance_unknown", "waiting_review"
        if state in {"FAILED", "REJECTED", "INVALID"}:
            return _clean(checkpoint.get("blocker") or f"{label}_not_completed"), "waiting_review"
    return "", ""


def recover_product_video_multiscene(
    *,
    store: product_video_poll_recovery.ProductVideoPollRecoveryStore,
    job_id: str,
    lease_owner: str,
    actual_worker_sha: str,
    status_getter: Callable[[dict[str, Any]], Mapping[str, Any]],
    artifact_fetcher: Callable[[dict[str, Any]], Mapping[str, Any]],
    scene_validator: Callable[..., Mapping[str, Any]],
    final_validator: Callable[..., Mapping[str, Any]],
    deliverer: Callable[[dict[str, Any]], Mapping[str, Any]],
    receipt_persister: Callable[[dict[str, Any]], Mapping[str, Any]],
    charger: Callable[[dict[str, Any]], Mapping[str, Any]],
    terminal_reporter: Callable[[dict[str, Any]], Mapping[str, Any]],
    compositor: Callable[..., Mapping[str, Any]] | None = None,
    environ: Mapping[str, Any] | None = None,
    public_request: bool = False,
    now_epoch: float | None = None,
    poll_interval_seconds: float = DEFAULT_SCENE_POLL_INTERVAL_SECONDS,
    lease_seconds: float = DEFAULT_RECOVERY_LEASE_SECONDS,
) -> dict[str, Any]:
    now = time.time() if now_epoch is None else float(now_epoch)
    try:
        checkpoint = store.load(job_id)
    except product_video_poll_recovery.RecoveryCheckpointNotFound:
        return _checkpoint_result(
            None,
            ok=False,
            blocker="multiscene_checkpoint_not_found",
        )
    except product_video_poll_recovery.RecoveryCheckpointError:
        return _checkpoint_result(
            None,
            ok=False,
            blocker="multiscene_checkpoint_invalid",
        )
    if (
        _nonnegative_int(checkpoint.get("schema_version")) != MULTISCENE_SCHEMA_VERSION
        or _clean(checkpoint.get("product_family")) != PRODUCT_FAMILY
        or _clean(checkpoint.get("mode")) != MODE
        or not 2 <= _nonnegative_int(checkpoint.get("scene_count")) <= MAX_MULTISCENE_SCENES
    ):
        return _recovery_result(
            checkpoint,
            ok=False,
            blocker="multiscene_checkpoint_semantic_mismatch",
            outcome="waiting_review",
        )
    if _clean(checkpoint.get("expected_worker_sha")) != _clean(actual_worker_sha):
        return _recovery_result(
            checkpoint,
            ok=False,
            blocker="worker_sha_mismatch",
            outcome="blocked",
        )
    terminal_blocker, terminal_outcome = _persisted_terminal_blocker(checkpoint)
    if terminal_blocker:
        return _recovery_result(
            checkpoint,
            ok=False,
            blocker=terminal_blocker,
            outcome=terminal_outcome,
            idempotent_replay=True,
        )
    if checkpoint.get("terminal_report", {}).get("emitted"):
        return _recovery_result(
            checkpoint,
            ok=True,
            outcome="final_delivered",
            idempotent_replay=True,
        )
    scene_states = {
        _clean(scene.get("provider_state")).upper()
        for scene in checkpoint.get("scenes", ())
    }
    if one_scene.ProviderState.ACCEPTANCE_UNKNOWN.value in scene_states:
        return _recovery_result(
            checkpoint,
            ok=False,
            blocker="scene_provider_acceptance_unknown",
            outcome="waiting_review",
        )
    if one_scene.ProviderState.FAILED.value in scene_states:
        checkpoint["terminal_state"] = "failed_no_charge"
        checkpoint["blocker"] = "required_scene_failed"
        checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
        return _recovery_result(
            checkpoint,
            ok=False,
            blocker="required_scene_failed",
            outcome="failed_no_charge",
        )

    fence = _acquire_process_fence(store, job_id=job_id)
    if fence is None:
        return _recovery_result(
            checkpoint,
            ok=False,
            blocker="recovery_fence_active",
            outcome="blocked",
        )
    try:
        lease = store.acquire_lease(
            job_id=job_id,
            owner=lease_owner,
            now_epoch=now,
            lease_seconds=max(1.0, float(lease_seconds)),
        )
    except Exception:
        _release_process_fence(fence)
        raise
    if not lease.get("acquired"):
        _release_process_fence(fence)
        return _recovery_result(
            checkpoint,
            ok=False,
            blocker=_clean(lease.get("blocker") or "recovery_lease_active"),
            outcome="blocked",
            stale_lease_recovered=bool(lease.get("stale_recovered")),
        )
    token = _clean(lease.get("token"))
    stale_recovered = bool(lease.get("stale_recovered"))
    try:
        checkpoint = store.load(job_id)
        if _clean(checkpoint.get("expected_worker_sha")) != _clean(actual_worker_sha):
            return _recovery_result(
                checkpoint,
                ok=False,
                blocker="worker_sha_mismatch",
                outcome="blocked",
                stale_lease_recovered=stale_recovered,
            )
        terminal_blocker, terminal_outcome = _persisted_terminal_blocker(checkpoint)
        if terminal_blocker:
            return _recovery_result(
                checkpoint,
                ok=False,
                blocker=terminal_blocker,
                outcome=terminal_outcome,
                idempotent_replay=True,
                stale_lease_recovered=stale_recovered,
            )
        if checkpoint.get("terminal_report", {}).get("emitted"):
            return _recovery_result(
                checkpoint,
                ok=True,
                outcome="final_delivered",
                idempotent_replay=True,
                stale_lease_recovered=stale_recovered,
            )
        completed_reused = sum(
            _durable_scene_artifact_truth(scene)[0]
            for scene in checkpoint.get("scenes", ())
        )
        waiting_provider = False
        for scene in checkpoint.get("scenes", ()):
            state = _clean(scene.get("provider_state")).upper()
            if state == one_scene.ProviderState.ACCEPTANCE_UNKNOWN.value:
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker="scene_provider_acceptance_unknown",
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            if state == one_scene.ProviderState.FAILED.value:
                checkpoint["terminal_state"] = "failed_no_charge"
                checkpoint["blocker"] = "required_scene_failed"
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker="required_scene_failed",
                    outcome="failed_no_charge",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            if state not in _ACTIVE_STATES:
                continue
            if now < float(scene.get("next_poll_epoch") or 0):
                waiting_provider = True
                continue
            provider_task_id = _clean(scene.get("provider_task_id"))
            if not provider_task_id:
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker="scene_provider_task_id_missing",
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            counters = _new_counters(checkpoint.get("counters"))
            counters["provider_status_get_calls"] += 1
            if _clean(scene.get("provider")) != "fake_provider":
                counters["real_provider_calls"] += 1
            checkpoint["counters"] = counters
            scene["next_poll_epoch"] = now + max(
                1.0, float(poll_interval_seconds)
            )
            checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
            try:
                response = dict(
                    status_getter(
                        {
                            "method": "GET",
                            "provider": _clean(scene.get("provider")),
                            "provider_task_id": provider_task_id,
                            "job_id": _clean(job_id),
                            "scene_id": _clean(scene.get("scene_id")),
                            "scene_index": int(scene.get("scene_index") or 0),
                        }
                    )
                    or {}
                )
            except product_video_poll_recovery.ProviderTaskUnknown:
                scene["provider_state"] = one_scene.ProviderState.FAILED.value
                scene["blocker"] = "scene_provider_task_unknown"
                checkpoint["terminal_state"] = "failed_no_charge"
                checkpoint["blocker"] = "required_scene_failed"
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker="required_scene_failed",
                    outcome="failed_no_charge",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            except Exception as exc:
                scene["safe_error"] = type(exc).__name__
                scene["blocker"] = "scene_provider_status_unavailable"
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker="scene_provider_status_unavailable",
                    outcome="waiting_provider",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            if _clean(response.get("provider_task_id")) != provider_task_id:
                scene["blocker"] = "scene_provider_task_identity_mismatch"
                checkpoint["blocker"] = scene["blocker"]
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker=scene["blocker"],
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            if _clean(response.get("provider")).lower() != _clean(scene.get("provider")):
                scene["blocker"] = "scene_provider_identity_mismatch"
                checkpoint["blocker"] = scene["blocker"]
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker=scene["blocker"],
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            if _nonnegative_int(response.get("scene_index")) != int(scene["scene_index"]):
                scene["blocker"] = "scene_response_index_mismatch"
                checkpoint["blocker"] = scene["blocker"]
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker=scene["blocker"],
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            next_state = _clean(response.get("state") or response.get("status")).upper()
            if next_state not in {
                one_scene.ProviderState.ACCEPTED.value,
                one_scene.ProviderState.RUNNING.value,
                one_scene.ProviderState.COMPLETED.value,
                one_scene.ProviderState.FAILED.value,
            }:
                scene["blocker"] = "scene_provider_status_unknown"
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker=scene["blocker"],
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            scene["provider_state"] = next_state
            scene["blocker"] = ""
            if next_state == one_scene.ProviderState.COMPLETED.value:
                scene["artifact_path"] = _clean(
                    response.get("artifact_path") or scene.get("artifact_path")
                )
                scene["artifact_url"] = _clean(
                    response.get("artifact_url")
                    or response.get("output_url")
                    or scene.get("artifact_url")
                )
            elif next_state == one_scene.ProviderState.FAILED.value:
                scene["blocker"] = "required_scene_failed"
                checkpoint["terminal_state"] = "failed_no_charge"
                checkpoint["blocker"] = "required_scene_failed"
            else:
                waiting_provider = True
            checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
            if next_state == one_scene.ProviderState.FAILED.value:
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker="required_scene_failed",
                    outcome="failed_no_charge",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )

        for scene in checkpoint.get("scenes", ()):
            if _clean(scene.get("provider_state")).upper() != one_scene.ProviderState.COMPLETED.value:
                waiting_provider = True
                continue
            persisted_fingerprint = _clean(scene.get("artifact_fingerprint"))
            artifact_is_durable, artifact_blocker = _durable_scene_artifact_truth(scene)
            if artifact_is_durable:
                continue
            artifact_path = _clean(scene.get("artifact_path"))
            artifact_url = _clean(scene.get("artifact_url"))
            if persisted_fingerprint and not artifact_url:
                scene["blocker"] = artifact_blocker or "scene_durable_artifact_missing"
                checkpoint["blocker"] = scene["blocker"]
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker=scene["blocker"],
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            needs_fetch = (
                not Path(artifact_path).is_file()
                or bool(persisted_fingerprint and not artifact_is_durable)
            )
            if needs_fetch:
                if not artifact_url:
                    scene["blocker"] = "scene_provider_output_missing"
                    checkpoint["blocker"] = scene["blocker"]
                    checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                    return _recovery_result(
                        checkpoint,
                        ok=False,
                        blocker=scene["blocker"],
                        outcome="waiting_review",
                        completed_scenes_reused=completed_reused,
                        stale_lease_recovered=stale_recovered,
                    )
                counters = _new_counters(checkpoint.get("counters"))
                counters["artifact_fetch_calls"] += 1
                checkpoint["counters"] = counters
                destination = _scene_artifact_path(
                    store,
                    job_id=job_id,
                    scene_index=int(scene["scene_index"]),
                )
                try:
                    fetched = dict(
                        artifact_fetcher(
                            {
                                "method": "GET",
                                "provider": _clean(scene.get("provider")),
                                "provider_task_id": _clean(scene.get("provider_task_id")),
                                "artifact_url": artifact_url,
                                "destination_path": str(destination),
                                "job_id": _clean(job_id),
                                "scene_id": _clean(scene.get("scene_id")),
                                "scene_index": int(scene.get("scene_index") or 0),
                            }
                        )
                        or {}
                    )
                except Exception as exc:
                    scene["safe_error"] = type(exc).__name__
                    fetched = {}
                artifact_path = _clean(fetched.get("artifact_path") or destination)
                if not fetched.get("ok") or not Path(artifact_path).is_file():
                    scene["blocker"] = "scene_provider_output_fetch_failed"
                    checkpoint["blocker"] = scene["blocker"]
                    checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                    return _recovery_result(
                        checkpoint,
                        ok=False,
                        blocker=scene["blocker"],
                        outcome="waiting_review",
                        completed_scenes_reused=completed_reused,
                        stale_lease_recovered=stale_recovered,
                    )
            durable_path = _copy_scene_artifact(
                artifact_path,
                _scene_artifact_path(
                    store,
                    job_id=job_id,
                    scene_index=int(scene["scene_index"]),
                ),
            )
            if not durable_path or not Path(durable_path).is_file():
                scene["blocker"] = "scene_provider_output_missing"
                checkpoint["blocker"] = scene["blocker"]
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker=scene["blocker"],
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            validation = dict(
                scene_validator(
                    durable_path,
                    expected_duration_seconds=float(scene["duration_seconds"]),
                    motion_promised=True,
                    audio_promised=(
                        _flag(scene.get("audio_requirement", {}).get("required"))
                        or _flag(scene.get("voice_requirement", {}).get("required"))
                    ),
                    result={"scene_index": int(scene["scene_index"])},
                )
                or {}
            )
            if not validation.get("ok"):
                scene["validation"] = validation
                scene["blocker"] = _clean(
                    validation.get("reason") or "scene_artifact_invalid"
                )
                checkpoint["terminal_state"] = "failed_no_charge"
                checkpoint["blocker"] = scene["blocker"]
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker=scene["blocker"],
                    outcome="failed_no_charge",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            actual_fingerprint = _sha256_file(durable_path)
            if persisted_fingerprint and actual_fingerprint != persisted_fingerprint:
                scene["blocker"] = "scene_durable_artifact_fingerprint_mismatch"
                checkpoint["blocker"] = scene["blocker"]
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker=scene["blocker"],
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            scene["artifact_path"] = durable_path
            scene["artifact_fingerprint"] = actual_fingerprint
            scene["validation"] = validation
            scene["blocker"] = ""
            checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)

        if waiting_provider:
            return _recovery_result(
                checkpoint,
                ok=False,
                outcome="waiting_provider",
                completed_scenes_reused=completed_reused,
                stale_lease_recovered=stale_recovered,
            )
        if not all(
            _durable_scene_artifact_truth(scene)[0]
            for scene in checkpoint.get("scenes", ())
        ):
            return _recovery_result(
                checkpoint,
                ok=False,
                blocker="full_scene_coverage_required",
                outcome="waiting_review",
                completed_scenes_reused=completed_reused,
                stale_lease_recovered=stale_recovered,
            )

        if not checkpoint.get("compose", {}).get("completed"):
            counters = _new_counters(checkpoint.get("counters"))
            counters["compose_count"] += 1
            checkpoint["counters"] = counters
            checkpoint["compose"] = {
                "state": "INTENT_PERSISTED",
                "completed": False,
            }
            checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
            clips = {
                int(scene["scene_index"]): _clean(scene["artifact_path"])
                for scene in checkpoint["scenes"]
            }
            try:
                if compositor is None:
                    composition = _default_compositor(
                        store=store,
                        checkpoint=checkpoint,
                        scene_clip_paths=clips,
                    )
                else:
                    composition = dict(
                        compositor(
                            job_id=_clean(job_id),
                            user_id=int(checkpoint["request"]["user_id"]),
                            scene_count=len(checkpoint["scenes"]),
                            scene_order=[
                                int(scene["scene_index"])
                                for scene in checkpoint["scenes"]
                            ],
                            scene_clip_paths=clips,
                            scenes=_json_safe(checkpoint["scenes"]),
                            final_assets=dict(
                                checkpoint["request"]["payload"].get("final_assets") or {}
                            ),
                            transition_plan=list(
                                checkpoint["request"]["payload"].get("transition_plan") or []
                            ),
                            transition_duration_seconds=float(
                                checkpoint["request"]["payload"].get(
                                    "transition_duration_seconds",
                                    DEFAULT_TRANSITION_DURATION_SECONDS,
                                )
                                or 0.0
                            ),
                            target_duration_seconds=float(
                                checkpoint["request"].get("duration_profile", {}).get(
                                    "target_duration_seconds",
                                    checkpoint["request"]["payload"].get(
                                        "target_duration_seconds", 0.0
                                    ),
                                )
                                or 0.0
                            ),
                            output_profile=dict(
                                checkpoint["request"]["payload"].get("output_profile") or {}
                            ),
                            audio_policy=dict(checkpoint["request"].get("audio_policy") or {}),
                            voice_policy=dict(checkpoint["request"].get("voice_policy") or {}),
                        )
                        or {}
                    )
            except Exception as exc:
                checkpoint["compose"] = {
                    "state": "FAILED",
                    "completed": False,
                    "safe_error": type(exc).__name__,
                }
                checkpoint["terminal_state"] = "failed_no_charge"
                checkpoint["blocker"] = "final_compose_failed"
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker="final_compose_failed",
                    outcome="failed_no_charge",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            final_path = _clean(
                composition.get("final_video_path")
                or composition.get("final_artifact_path")
            )
            if not composition.get("ok") or not Path(final_path).is_file():
                blocker = _clean(composition.get("error") or "final_compose_failed")
                checkpoint["compose"] = {
                    "state": "FAILED",
                    "completed": False,
                    "result": composition,
                }
                checkpoint["terminal_state"] = "failed_no_charge"
                checkpoint["blocker"] = blocker
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker=blocker,
                    outcome="failed_no_charge",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            expected_scene_order = [
                int(scene["scene_index"]) for scene in checkpoint["scenes"]
            ]
            reported_scene_order = [
                _nonnegative_int(value)
                for value in (composition.get("scene_order") or ())
            ]
            reported_scene_count = _nonnegative_int(composition.get("scene_count"))
            if reported_scene_count != len(expected_scene_order):
                blocker = "final_scene_count_mismatch"
            elif reported_scene_order != expected_scene_order:
                blocker = "final_scene_order_mismatch"
            else:
                blocker = ""
            if blocker:
                checkpoint["compose"] = {
                    "state": "FAILED",
                    "completed": False,
                    "result": composition,
                }
                checkpoint["terminal_state"] = "failed_no_charge"
                checkpoint["blocker"] = blocker
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker=blocker,
                    outcome="failed_no_charge",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            request_snapshot = dict(checkpoint.get("request") or {})
            duration_profile = dict(request_snapshot.get("duration_profile") or {})
            composition_target = composition.get("target_duration_sec")
            if composition_target is None:
                composition_target = composition.get("target_duration_seconds")
            if composition_target is None:
                composition_target = duration_profile.get("target_duration_seconds")
            try:
                expected_duration = float(composition_target)
            except (TypeError, ValueError, OverflowError):
                expected_duration = 0.0
            if expected_duration <= 0:
                expected_duration = sum(
                    float(scene["duration_seconds"]) for scene in checkpoint["scenes"]
                )
            audio_policy = dict(request_snapshot.get("audio_policy") or {})
            voice_policy = dict(request_snapshot.get("voice_policy") or {})
            final_validation = dict(
                final_validator(
                    final_path,
                    expected_duration_seconds=expected_duration,
                    motion_promised=True,
                    audio_promised=(
                        _flag(audio_policy.get("promised"))
                        or _flag(voice_policy.get("promised"))
                    ),
                    result=composition,
                )
                or {}
            )
            if not final_validation.get("ok"):
                blocker = _clean(
                    final_validation.get("reason") or "final_output_invalid"
                )
                checkpoint["final_artifact_path"] = final_path
                checkpoint["final_validation"] = final_validation
                checkpoint["terminal_state"] = "failed_no_charge"
                checkpoint["blocker"] = blocker
                checkpoint["compose"] = {
                    "state": "COMPLETED_INVALID",
                    "completed": True,
                    "result": composition,
                }
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker=blocker,
                    outcome="failed_no_charge",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            checkpoint["final_artifact_path"] = final_path
            checkpoint["final_artifact_fingerprint"] = _sha256_file(final_path)
            checkpoint["final_validation"] = final_validation
            checkpoint["compose"] = {
                "state": "COMPLETED",
                "completed": True,
                "result": composition,
            }
            checkpoint["blocker"] = ""
            checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)

        final_path = _clean(checkpoint.get("final_artifact_path"))
        final_fingerprint = _clean(checkpoint.get("final_artifact_fingerprint"))
        final_bytes = _nonnegative_int(
            checkpoint.get("delivery", {}).get("output_bytes")
        )
        if not checkpoint.get("delivery", {}).get("accepted"):
            final_validation = dict(checkpoint.get("final_validation") or {})
            final_blocker = ""
            if not Path(final_path).is_file():
                final_blocker = "final_artifact_missing"
            elif not final_fingerprint:
                final_blocker = "final_artifact_fingerprint_missing"
            else:
                try:
                    current_fingerprint = _sha256_file(final_path)
                except OSError:
                    current_fingerprint = ""
                if current_fingerprint != final_fingerprint:
                    final_blocker = "final_artifact_fingerprint_mismatch"
            if not final_blocker and not final_validation.get("ok"):
                final_blocker = "final_artifact_validation_missing"
            if final_blocker:
                checkpoint["blocker"] = final_blocker
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker=final_blocker,
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            final_bytes = Path(final_path).stat().st_size
            checkpoint["delivery"] = {
                "state": "INTENT_PERSISTED",
                "accepted": False,
                "idempotency_key": f"delivery:{job_id}:{final_fingerprint}",
                "output_sha256": final_fingerprint,
                "output_bytes": final_bytes,
            }
            checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
            try:
                delivery = dict(
                    deliverer(
                        {
                            "job_id": _clean(job_id),
                            "final_artifact_path": final_path,
                            "output_sha256": final_fingerprint,
                            "production": False,
                            "idempotency_key": checkpoint["delivery"]["idempotency_key"],
                        }
                    )
                    or {}
                )
            except Exception as exc:
                checkpoint["delivery"] = {
                    **checkpoint["delivery"],
                    "state": "ACCEPTANCE_UNKNOWN",
                    "safe_error": type(exc).__name__,
                }
                checkpoint["blocker"] = "delivery_acceptance_unknown"
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker="delivery_acceptance_unknown",
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            if not delivery.get("accepted") or not _clean(delivery.get("message_id")):
                checkpoint["delivery"] = {
                    **checkpoint["delivery"],
                    "state": "REJECTED",
                    "accepted": False,
                    "result": delivery,
                }
                checkpoint["blocker"] = "delivery_not_accepted"
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker="delivery_not_accepted",
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            checkpoint["delivery"] = {
                **checkpoint["delivery"],
                **delivery,
                "state": "ACCEPTED",
                "accepted": True,
                "idempotency_key": f"delivery:{job_id}:{final_fingerprint}",
                "output_sha256": final_fingerprint,
                "output_bytes": final_bytes,
            }
            counters = _new_counters(checkpoint.get("counters"))
            counters["delivery_count"] += 1
            if delivery.get("production"):
                counters["production_telegram_deliveries"] += 1
            checkpoint["counters"] = counters
            checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)

        if not checkpoint.get("receipt", {}).get("persisted"):
            delivered_at = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(now),
            )
            receipt_seed = {
                "job_id": _clean(job_id),
                "delivered": True,
                "delivery_idempotency_key": _clean(
                    checkpoint["delivery"].get("idempotency_key")
                ),
                "delivery_message_id": _clean(
                    checkpoint["delivery"].get("message_id")
                ),
                "output_sha256": final_fingerprint,
                "output_bytes": final_bytes,
                "delivered_at": delivered_at,
            }
            checkpoint["receipt"] = {
                "state": "INTENT_PERSISTED",
                "persisted": False,
                "idempotency_key": receipt_seed["delivery_idempotency_key"],
            }
            checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
            try:
                receipt = dict(receipt_persister(receipt_seed) or {})
            except Exception as exc:
                checkpoint["receipt"] = {
                    **checkpoint["receipt"],
                    "state": "ACCEPTANCE_UNKNOWN",
                    "safe_error": type(exc).__name__,
                }
                checkpoint["blocker"] = "receipt_acceptance_unknown"
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker="receipt_acceptance_unknown",
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            receipt_contract = video_engine_contract.VideoDeliveryReceipt(
                **receipt_seed,
                receipt_id=_clean(receipt.get("receipt_id")),
            )
            if not receipt.get("persisted") or not receipt_contract.valid:
                checkpoint["receipt"] = {
                    **receipt_seed,
                    **receipt,
                    "state": "INVALID",
                    "persisted": False,
                }
                checkpoint["blocker"] = "delivery_receipt_not_persisted"
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker="delivery_receipt_not_persisted",
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            checkpoint["receipt"] = {
                **receipt,
                **_json_safe(receipt_contract),
                "state": "PERSISTED",
                "persisted": True,
                "idempotency_key": receipt_seed["delivery_idempotency_key"],
            }
            counters = _new_counters(checkpoint.get("counters"))
            counters["receipt_count"] += 1
            checkpoint["counters"] = counters
            checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)

        if not checkpoint.get("charge", {}).get("recorded"):
            request_payload = dict(checkpoint["request"].get("payload") or {})
            admin_no_charge = bool(request_payload.get("admin_no_charge"))
            charge_plan = dict(request_payload.get("charge_plan") or {})
            amount_xu = 0 if admin_no_charge else _nonnegative_int(
                charge_plan.get("amount_xu")
            )
            if not admin_no_charge and amount_xu <= 0:
                checkpoint["blocker"] = "charge_plan_missing"
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker="charge_plan_missing",
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            charge_key = f"charge:{job_id}:{amount_xu}"
            checkpoint["charge"] = {
                "state": "INTENT_PERSISTED",
                "recorded": False,
                "amount_xu": amount_xu,
                "admin_no_charge": admin_no_charge,
                "idempotency_key": charge_key,
            }
            checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
            try:
                charge = dict(
                    charger(
                        {
                            "job_id": _clean(job_id),
                            "amount_xu": amount_xu,
                            "admin_no_charge": admin_no_charge,
                            "receipt_id": checkpoint["receipt"].get("receipt_id"),
                            "idempotency_key": charge_key,
                        }
                    )
                    or {}
                )
            except Exception as exc:
                checkpoint["charge"] = {
                    **checkpoint["charge"],
                    "state": "ACCEPTANCE_UNKNOWN",
                    "safe_error": type(exc).__name__,
                }
                checkpoint["blocker"] = "charge_acceptance_unknown"
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker="charge_acceptance_unknown",
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            if not charge.get("ok"):
                checkpoint["charge"] = {
                    **checkpoint["charge"],
                    "state": "FAILED",
                    "result": charge,
                }
                checkpoint["blocker"] = "charge_not_recorded"
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker="charge_not_recorded",
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            checkpoint["charge"] = {
                **checkpoint["charge"],
                **charge,
                "state": "RECORDED",
                "recorded": True,
                "amount_xu": amount_xu,
                "idempotency_key": charge_key,
            }
            counters = _new_counters(checkpoint.get("counters"))
            counters["charge_count"] += 1
            if charge.get("wallet_mutated"):
                counters["wallet_mutations"] += 1
            checkpoint["counters"] = counters
            checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)

        if not checkpoint.get("terminal_report", {}).get("emitted"):
            report_key = f"terminal-report:{job_id}"
            checkpoint["terminal_report"] = {
                "state": "INTENT_PERSISTED",
                "emitted": False,
                "idempotency_key": report_key,
            }
            checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
            try:
                report = dict(
                    terminal_reporter(
                        {
                            "job_id": _clean(job_id),
                            "scene_count": len(checkpoint["scenes"]),
                            "scene_order": [
                                int(scene["scene_index"])
                                for scene in checkpoint["scenes"]
                            ],
                            "final_artifact_path": final_path,
                            "output_sha256": final_fingerprint,
                            "terminal_state": "final_delivered",
                            "receipt_id": checkpoint["receipt"].get("receipt_id"),
                            "charge_idempotency_key": checkpoint["charge"].get(
                                "idempotency_key"
                            ),
                            "idempotency_key": report_key,
                        }
                    )
                    or {}
                )
            except Exception as exc:
                checkpoint["terminal_report"] = {
                    **checkpoint["terminal_report"],
                    "state": "ACCEPTANCE_UNKNOWN",
                    "safe_error": type(exc).__name__,
                }
                checkpoint["blocker"] = "report_acceptance_unknown"
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker="report_acceptance_unknown",
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            if not report.get("emitted") or not _clean(report.get("report_id")):
                checkpoint["terminal_report"] = {
                    **checkpoint["terminal_report"],
                    "state": "FAILED",
                    "emitted": False,
                    "result": report,
                }
                checkpoint["blocker"] = "terminal_report_not_emitted"
                checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)
                return _recovery_result(
                    checkpoint,
                    ok=False,
                    blocker="terminal_report_not_emitted",
                    outcome="waiting_review",
                    completed_scenes_reused=completed_reused,
                    stale_lease_recovered=stale_recovered,
                )
            checkpoint["terminal_report"] = {
                **report,
                "state": "EMITTED",
                "emitted": True,
                "idempotency_key": report_key,
            }
            counters = _new_counters(checkpoint.get("counters"))
            counters["terminal_report_count"] += 1
            checkpoint["counters"] = counters
            checkpoint["terminal_state"] = "final_delivered"
            checkpoint["blocker"] = ""
            checkpoint = _save_checkpoint(store, checkpoint, now_epoch=now)

        return _recovery_result(
            checkpoint,
            ok=True,
            outcome="final_delivered",
            completed_scenes_reused=completed_reused,
            stale_lease_recovered=stale_recovered,
        )
    finally:
        store.release_lease(job_id=job_id, token=token)
        _release_process_fence(fence)
