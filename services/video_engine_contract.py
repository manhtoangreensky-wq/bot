"""Shared Product Video route and worker contract.

This module is deliberately transport-free. It does not import Telegram,
billing, database, provider, or worker loops. Callers supply persisted jobs and
the submit function; this layer only decides whether submission is safe.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, MutableMapping

from services import frame_video_commercial, video_editengine1


CONTRACT_VERSION = "videomenu_routeengine29b_v1"


class VideoProduct(str, Enum):
    ANIMATED_VIDEO = "animated_video"
    HUMAN_AI_VIDEO = "human_ai_video"
    PRODUCT_VIDEO = "product_video"
    SUMMARY_VIDEO = "summary_video"
    PODCAST_VIDEO = "podcast_video"
    FRAME_VIDEO = "frame_video"
    VIDEO_EDITING = "video_editing"


class VideoEngineMode(str, Enum):
    SINGLE_SCENE = "single_scene"
    MULTI_SCENE = "multi_scene"
    SINGLE_ASSET_EDIT = "single_asset_edit"
    MULTI_ASSET_EDIT = "multi_asset_edit"


class VideoRouteState(str, Enum):
    CONNECTED = "CONNECTED"
    PROFILE_ONLY = "PROFILE_ONLY"
    ENGINE_MISSING = "ENGINE_MISSING"


def _product(value: VideoProduct | str) -> VideoProduct:
    if isinstance(value, VideoProduct):
        return value
    return VideoProduct(str(value or "").strip())


def _mode(value: VideoEngineMode | str) -> VideoEngineMode:
    if isinstance(value, VideoEngineMode):
        return value
    return VideoEngineMode(str(value or "").strip())


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _clean_text(value).lower() in {"1", "true", "yes", "on"}


def _normalized_payload(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return json.loads(
        json.dumps(dict(value or {}), ensure_ascii=True, sort_keys=True, default=str)
    )


def _normalized_mapping(value: Mapping[str, Any] | None, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"video_engine_{field_name}_required")
    return _normalized_payload(value)


def _normalized_assets(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        values = (value,)
    else:
        try:
            values = tuple(value)
        except TypeError as exc:
            raise ValueError("video_engine_input_assets_required") from exc
    normalized: list[Any] = []
    for item in values:
        if isinstance(item, Mapping):
            normalized.append(_normalized_payload(item))
        else:
            normalized.append(_clean_text(item))
    return tuple(normalized)


def _positive_user_id(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("video_engine_user_id_required")
    try:
        user_id = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("video_engine_user_id_required") from exc
    if user_id <= 0:
        raise ValueError("video_engine_user_id_required")
    return user_id


_AUTO_SELECTIONS = frozenset({"auto", "auto_product", "auto_provider"})


@dataclass(frozen=True)
class VideoEngineRequest:
    request_id: str
    confirmation_id: str
    idempotency_key: str
    product_type: VideoProduct | str
    mode: VideoEngineMode | str
    user_id: int
    language: str
    approved_plan: Mapping[str, Any]
    input_assets: tuple[Any, ...]
    aspect_ratio: str
    duration_profile: Mapping[str, Any]
    audio_policy: Mapping[str, Any]
    voice_policy: Mapping[str, Any]
    provider_selection: str
    explicit_confirmation_receipt: Mapping[str, Any]
    runtime_sha: str
    expected_worker_sha: str
    confirmed: bool
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        request_id = _clean_text(self.request_id)
        idempotency_key = _clean_text(self.idempotency_key)
        if not request_id:
            raise ValueError("video_engine_request_id_required")
        if not idempotency_key:
            raise ValueError("video_engine_idempotency_key_required")
        object.__setattr__(self, "request_id", request_id)
        object.__setattr__(self, "confirmation_id", _clean_text(self.confirmation_id))
        object.__setattr__(self, "idempotency_key", idempotency_key)
        object.__setattr__(self, "product_type", _product(self.product_type))
        object.__setattr__(self, "mode", _mode(self.mode))
        object.__setattr__(self, "user_id", _positive_user_id(self.user_id))
        language = _clean_text(self.language)
        if not language:
            raise ValueError("video_engine_language_required")
        object.__setattr__(self, "language", language)
        approved_plan = _normalized_mapping(self.approved_plan, "approved_plan")
        if not approved_plan:
            raise ValueError("video_engine_approved_plan_required")
        object.__setattr__(self, "approved_plan", approved_plan)
        object.__setattr__(self, "input_assets", _normalized_assets(self.input_assets))
        aspect_ratio = _clean_text(self.aspect_ratio)
        if not aspect_ratio:
            raise ValueError("video_engine_aspect_ratio_required")
        object.__setattr__(self, "aspect_ratio", aspect_ratio)
        object.__setattr__(
            self,
            "duration_profile",
            _normalized_mapping(self.duration_profile, "duration_profile"),
        )
        object.__setattr__(self, "audio_policy", _normalized_mapping(self.audio_policy, "audio_policy"))
        object.__setattr__(self, "voice_policy", _normalized_mapping(self.voice_policy, "voice_policy"))
        provider_selection = _clean_text(self.provider_selection).lower()
        if not provider_selection:
            raise ValueError("video_engine_provider_selection_required")
        if provider_selection in _AUTO_SELECTIONS:
            raise ValueError("video_engine_auto_selection_forbidden")
        object.__setattr__(self, "provider_selection", provider_selection)
        receipt = _normalized_mapping(self.explicit_confirmation_receipt, "confirmation_receipt")
        object.__setattr__(self, "explicit_confirmation_receipt", receipt)
        runtime_sha = _clean_text(self.runtime_sha)
        expected_worker_sha = _clean_text(self.expected_worker_sha)
        if not runtime_sha:
            raise ValueError("video_engine_runtime_sha_required")
        if not expected_worker_sha:
            raise ValueError("video_engine_expected_worker_sha_required")
        object.__setattr__(self, "runtime_sha", runtime_sha)
        object.__setattr__(self, "expected_worker_sha", expected_worker_sha)
        object.__setattr__(self, "confirmed", _as_bool(self.confirmed))
        payload = _normalized_payload(self.payload)
        object.__setattr__(self, "payload", payload)
        if self.confirmed:
            if not self.confirmation_id:
                raise ValueError("video_engine_confirmation_id_required")
            receipt_id = _clean_text(receipt.get("confirmation_id") or receipt.get("receipt_id"))
            if not receipt_id:
                raise ValueError("video_engine_confirmation_receipt_required")
            if self.confirmation_id and receipt_id != self.confirmation_id:
                raise ValueError("video_engine_confirmation_receipt_mismatch")
        if self.confirmation_id:
            expected_key = stable_request_idempotency_key(
                confirmation_id=self.confirmation_id,
                product_type=self.product_type,
                mode=self.mode,
                payload=payload,
                user_id=self.user_id,
                language=self.language,
                approved_plan=self.approved_plan,
                input_assets=self.input_assets,
                aspect_ratio=self.aspect_ratio,
                duration_profile=self.duration_profile,
                audio_policy=self.audio_policy,
                voice_policy=self.voice_policy,
                provider_selection=self.provider_selection,
                runtime_sha=self.runtime_sha,
                expected_worker_sha=self.expected_worker_sha,
            )
            if expected_key != idempotency_key:
                raise ValueError("video_engine_idempotency_key_mismatch")

    @property
    def product(self) -> VideoProduct:
        return self.product_type


@dataclass(frozen=True)
class VideoEngineJob:
    job_id: str
    request_id: str
    idempotency_key: str
    product_type: VideoProduct | str
    mode: VideoEngineMode | str
    user_id: int
    runtime_sha: str
    expected_worker_sha: str
    worker_job_type: str
    engine_route: str
    worker_owner: str
    status: str

    def __post_init__(self) -> None:
        if not _clean_text(self.job_id):
            raise ValueError("video_engine_job_id_required")
        if not _clean_text(self.request_id):
            raise ValueError("video_engine_request_id_required")
        if not _clean_text(self.idempotency_key):
            raise ValueError("video_engine_idempotency_key_required")
        object.__setattr__(self, "job_id", _clean_text(self.job_id))
        object.__setattr__(self, "request_id", _clean_text(self.request_id))
        object.__setattr__(self, "idempotency_key", _clean_text(self.idempotency_key))
        object.__setattr__(self, "product_type", _product(self.product_type))
        object.__setattr__(self, "mode", _mode(self.mode))
        object.__setattr__(self, "user_id", _positive_user_id(self.user_id))
        runtime_sha = _clean_text(self.runtime_sha)
        expected_worker_sha = _clean_text(self.expected_worker_sha)
        if not runtime_sha:
            raise ValueError("video_engine_runtime_sha_required")
        if not expected_worker_sha:
            raise ValueError("video_engine_expected_worker_sha_required")
        object.__setattr__(self, "runtime_sha", runtime_sha)
        object.__setattr__(self, "expected_worker_sha", expected_worker_sha)
        object.__setattr__(self, "worker_job_type", _clean_text(self.worker_job_type))
        object.__setattr__(self, "engine_route", _clean_text(self.engine_route))
        object.__setattr__(self, "worker_owner", _clean_text(self.worker_owner))
        object.__setattr__(self, "status", _clean_text(self.status))

    @property
    def product(self) -> VideoProduct:
        return self.product_type


@dataclass(frozen=True)
class VideoEngineResult:
    job_id: str
    ok: bool
    status: str
    output_path: str = ""
    output_bytes: int = 0
    mime_type: str = ""
    provider_task_id: str = ""
    provider_status: str = ""
    blocker: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "job_id", _clean_text(self.job_id))
        object.__setattr__(self, "ok", _as_bool(self.ok))
        object.__setattr__(self, "status", _clean_text(self.status))
        object.__setattr__(self, "output_path", _clean_text(self.output_path))
        object.__setattr__(self, "output_bytes", max(0, int(self.output_bytes or 0)))
        object.__setattr__(self, "mime_type", _clean_text(self.mime_type))
        object.__setattr__(self, "provider_task_id", _clean_text(self.provider_task_id))
        object.__setattr__(self, "provider_status", _clean_text(self.provider_status))
        object.__setattr__(self, "blocker", _clean_text(self.blocker))

    @property
    def artifact_valid(self) -> bool:
        return bool(
            self.job_id
            and self.ok
            and self.status in {"completed", "delivered"}
            and self.output_path
            and self.output_bytes > 0
            and self.mime_type == "video/mp4"
        )


@dataclass(frozen=True)
class VideoDeliveryReceipt:
    job_id: str
    delivered: bool
    delivery_idempotency_key: str
    receipt_id: str = ""
    delivery_message_id: str = ""
    output_sha256: str = ""
    output_bytes: int = 0
    delivered_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "job_id", _clean_text(self.job_id))
        object.__setattr__(self, "delivered", _as_bool(self.delivered))
        object.__setattr__(
            self,
            "delivery_idempotency_key",
            _clean_text(self.delivery_idempotency_key),
        )
        object.__setattr__(self, "receipt_id", _clean_text(self.receipt_id))
        object.__setattr__(self, "delivery_message_id", _clean_text(self.delivery_message_id))
        object.__setattr__(self, "output_sha256", _clean_text(self.output_sha256).lower())
        object.__setattr__(self, "output_bytes", max(0, int(self.output_bytes or 0)))
        object.__setattr__(self, "delivered_at", _clean_text(self.delivered_at))

    @property
    def valid(self) -> bool:
        return bool(
            self.job_id
            and self.delivered
            and self.delivery_idempotency_key
            and self.receipt_id
            and self.delivery_message_id
            and len(self.output_sha256) == 64
            and all(character in "0123456789abcdef" for character in self.output_sha256)
            and self.output_bytes > 0
            and self.delivered_at
        )


_PROFILE_ONLY_PRODUCTS = frozenset(
    {
        VideoProduct.ANIMATED_VIDEO,
        VideoProduct.HUMAN_AI_VIDEO,
        VideoProduct.PRODUCT_VIDEO,
        VideoProduct.SUMMARY_VIDEO,
        VideoProduct.PODCAST_VIDEO,
    }
)


def product_route_contract(
    product: VideoProduct | str,
    *,
    environ: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    item = _product(product)
    if item is VideoProduct.PRODUCT_VIDEO:
        from services import product_video_one_scene_engine

        flags = product_video_one_scene_engine.product_video_one_scene_flags(environ)
        if flags["PRODUCT_VIDEO_ONE_SCENE_ENGINE_ENABLED"]:
            return product_video_one_scene_engine.shared_product_video_one_scene_route()
    if item in _PROFILE_ONLY_PRODUCTS:
        return {
            "product": item.value,
            "state": VideoRouteState.PROFILE_ONLY.value,
            "connected": False,
            "public_product_type": "",
            "worker_job_type": "",
            "engine_route": "",
            "worker_owner": "",
            "required_capability": "",
            "supported_modes": (),
            "provider_enabled": False,
            "local_enabled": False,
            "blocker": "independent_product_contract_missing",
        }
    if item is VideoProduct.FRAME_VIDEO:
        return {
            "product": item.value,
            "state": VideoRouteState.CONNECTED.value,
            "connected": True,
            "public_product_type": frame_video_commercial.PUBLIC_JOB_TYPE,
            "worker_job_type": frame_video_commercial.WORKER_JOB_TYPE,
            "engine_route": frame_video_commercial.ENGINE_ROUTE,
            "worker_owner": frame_video_commercial.WORKER_OWNER,
            "required_capability": frame_video_commercial.WORKER_CAPABILITY,
            "supported_modes": (VideoEngineMode.MULTI_ASSET_EDIT.value,),
            "provider_enabled": False,
            "local_enabled": True,
            "blocker": "",
        }
    return {
        "product": item.value,
        "state": VideoRouteState.CONNECTED.value,
        "connected": True,
        "public_product_type": "video_local_edit",
        "worker_job_type": video_editengine1.WORKER_JOB_TYPE,
        "engine_route": video_editengine1.ENGINE_ROUTE,
        "worker_owner": video_editengine1.OUTBOX_OWNER,
        "required_capability": video_editengine1.WORKER_CAPABILITY,
        "supported_modes": (
            VideoEngineMode.SINGLE_ASSET_EDIT.value,
            VideoEngineMode.MULTI_ASSET_EDIT.value,
        ),
        "provider_enabled": False,
        "local_enabled": True,
        "blocker": "",
    }


def _ordered_products(values: list[VideoProduct | str] | tuple[VideoProduct | str, ...]) -> tuple[str, ...]:
    selected = {_product(item) for item in values}
    return tuple(item.value for item in VideoProduct if item in selected)


def _ordered_modes(values: list[VideoEngineMode | str] | tuple[VideoEngineMode | str, ...]) -> tuple[str, ...]:
    selected = {_mode(item) for item in values}
    return tuple(item.value for item in VideoEngineMode if item in selected)


def _normalized_flag_map(value: Mapping[str, Any] | None) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        return {}
    return {
        _clean_text(key): _as_bool(enabled)
        for key, enabled in dict(value or {}).items()
        if _clean_text(key)
    }


def build_worker_manifest(
    *,
    worker_sha: str,
    worker_instance_id: str,
    supported_products: list[VideoProduct | str] | tuple[VideoProduct | str, ...],
    supported_modes: list[VideoEngineMode | str] | tuple[VideoEngineMode | str, ...],
    renderer_name: str,
    renderer_version: str,
    ffmpeg_version: str,
    provider_enabled: bool,
    local_enabled: bool,
    queue_ready: bool,
    worker_connected: bool,
    heartbeat_fresh: bool,
    capabilities: list[str] | tuple[str, ...],
    health_ok: bool,
    worker_status: str,
    provider_availability: Mapping[str, Any] | None = None,
    local_capabilities: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    capability_values = tuple(
        sorted({_clean_text(item) for item in capabilities if _clean_text(item)})
    )
    local_flags = _normalized_flag_map(local_capabilities)
    if local_capabilities is None:
        local_flags = {item: True for item in capability_values}
    return {
        "engine_contract_version": CONTRACT_VERSION,
        "contract_version": CONTRACT_VERSION,
        "worker_sha": _clean_text(worker_sha),
        "worker_instance_id": _clean_text(worker_instance_id),
        "supported_products": _ordered_products(supported_products),
        "supported_modes": _ordered_modes(supported_modes),
        "renderer_name": _clean_text(renderer_name),
        "renderer_version": _clean_text(renderer_version),
        "ffmpeg_version": _clean_text(ffmpeg_version),
        "provider_enabled": _as_bool(provider_enabled),
        "local_enabled": _as_bool(local_enabled),
        "queue_ready": _as_bool(queue_ready),
        "worker_connected": _as_bool(worker_connected),
        "heartbeat_fresh": _as_bool(heartbeat_fresh),
        "health_ok": _as_bool(health_ok),
        "worker_status": _clean_text(worker_status).lower(),
        "provider_availability": _normalized_flag_map(provider_availability),
        "local_capabilities": local_flags,
        "capabilities": capability_values,
    }


def stable_request_idempotency_key(
    *,
    confirmation_id: str,
    product_type: VideoProduct | str,
    mode: VideoEngineMode | str,
    payload: Mapping[str, Any] | None,
    user_id: int,
    language: str,
    approved_plan: Mapping[str, Any],
    input_assets: tuple[Any, ...],
    aspect_ratio: str,
    duration_profile: Mapping[str, Any],
    audio_policy: Mapping[str, Any],
    voice_policy: Mapping[str, Any],
    provider_selection: str,
    runtime_sha: str,
    expected_worker_sha: str,
) -> str:
    confirmation = _clean_text(confirmation_id)
    if not confirmation:
        raise ValueError("video_engine_confirmation_id_required")
    provider = _clean_text(provider_selection).lower()
    if provider in _AUTO_SELECTIONS:
        raise ValueError("video_engine_auto_selection_forbidden")
    material = {
        "engine_contract_version": CONTRACT_VERSION,
        "confirmation_id": confirmation,
        "user_id": _positive_user_id(user_id),
        "product_type": _product(product_type).value,
        "mode": _mode(mode).value,
        "language": _clean_text(language),
        "approved_plan": _normalized_mapping(approved_plan, "approved_plan"),
        "input_assets": _normalized_assets(input_assets),
        "aspect_ratio": _clean_text(aspect_ratio),
        "duration_profile": _normalized_mapping(duration_profile, "duration_profile"),
        "audio_policy": _normalized_mapping(audio_policy, "audio_policy"),
        "voice_policy": _normalized_mapping(voice_policy, "voice_policy"),
        "provider_selection": provider,
        "runtime_sha": _clean_text(runtime_sha),
        "expected_worker_sha": _clean_text(expected_worker_sha),
        "payload": _normalized_payload(payload),
    }
    encoded = json.dumps(material, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def evaluate_readiness(
    request: VideoEngineRequest,
    *,
    manifest: Mapping[str, Any],
    runtime_sha: str,
    environ: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    route = product_route_contract(request.product_type, environ=environ)
    supported_products = tuple(manifest.get("supported_products") or ())
    supported_modes = tuple(manifest.get("supported_modes") or ())
    capabilities = set(manifest.get("capabilities") or ())
    local_capabilities = _normalized_flag_map(manifest.get("local_capabilities"))
    provider_availability = _normalized_flag_map(manifest.get("provider_availability"))
    blocker = ""
    if not request.confirmed:
        blocker = "confirmation_required"
    elif not route["connected"]:
        blocker = str(route["blocker"] or "independent_product_contract_missing")
    elif request.mode.value not in route["supported_modes"]:
        blocker = "product_mode_unsupported"
    elif _clean_text(manifest.get("engine_contract_version")) != CONTRACT_VERSION:
        blocker = "worker_contract_version_mismatch"
    elif not _clean_text(runtime_sha) or request.runtime_sha != _clean_text(runtime_sha):
        blocker = "runtime_sha_mismatch"
    elif (
        _clean_text(manifest.get("worker_sha")) != _clean_text(runtime_sha)
        or request.expected_worker_sha != _clean_text(manifest.get("worker_sha"))
    ):
        blocker = "worker_sha_mismatch"
    elif not _clean_text(manifest.get("worker_instance_id")):
        blocker = "worker_instance_missing"
    elif not _as_bool(manifest.get("worker_connected")):
        blocker = "worker_disconnected"
    elif not _as_bool(manifest.get("heartbeat_fresh")):
        blocker = "worker_heartbeat_stale"
    elif not _as_bool(manifest.get("health_ok")):
        blocker = "worker_unhealthy"
    elif _clean_text(manifest.get("worker_status")).lower() not in {"healthy", "ready", "idle", "running"}:
        blocker = "worker_status_not_ready"
    elif not _as_bool(manifest.get("queue_ready")):
        blocker = "worker_queue_not_ready"
    elif not _clean_text(manifest.get("renderer_name")):
        blocker = "worker_renderer_missing"
    elif not _clean_text(manifest.get("renderer_version")):
        blocker = "worker_renderer_version_missing"
    elif not _clean_text(manifest.get("ffmpeg_version")):
        blocker = "worker_ffmpeg_missing"
    elif request.product_type.value not in supported_products:
        blocker = "worker_product_unsupported"
    elif request.mode.value not in supported_modes:
        blocker = "worker_mode_unsupported"
    elif route["required_capability"] not in capabilities:
        blocker = "worker_capability_mismatch"
    elif route["local_enabled"] and not _as_bool(manifest.get("local_enabled")):
        blocker = "local_engine_disabled"
    elif route["local_enabled"] and not local_capabilities.get(route["required_capability"], False):
        blocker = "local_capability_disabled"
    elif route["local_enabled"] and request.provider_selection != "local":
        blocker = "provider_selection_mismatch"
    elif route["provider_enabled"] and not _as_bool(manifest.get("provider_enabled")):
        blocker = "provider_engine_disabled"
    elif route["provider_enabled"] and not provider_availability.get(request.provider_selection, False):
        blocker = "provider_unavailable"
    ready = not blocker
    return {
        "ready": ready,
        "submit_allowed": ready,
        "blocker": blocker,
        "product_type": request.product_type.value,
        "product": request.product_type.value,
        "mode": request.mode.value,
        "route": route,
        "engine_contract_version": CONTRACT_VERSION,
        "contract_version": CONTRACT_VERSION,
        "worker_sha": _clean_text(manifest.get("worker_sha")),
        "runtime_sha": _clean_text(runtime_sha),
    }


def _coerce_job(value: VideoEngineJob | Mapping[str, Any]) -> VideoEngineJob:
    return value if isinstance(value, VideoEngineJob) else VideoEngineJob(**dict(value))


def guarded_submit(
    request: VideoEngineRequest,
    *,
    manifest: Mapping[str, Any],
    runtime_sha: str,
    jobs_by_idempotency: MutableMapping[str, VideoEngineJob],
    submitter: Callable[[VideoEngineRequest, Mapping[str, Any]], VideoEngineJob | Mapping[str, Any]],
    environ: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    existing = jobs_by_idempotency.get(request.idempotency_key)
    if existing is not None:
        job = _coerce_job(existing)
        route = product_route_contract(request.product_type, environ=environ)
        if not route["connected"]:
            readiness = evaluate_readiness(
                request,
                manifest=manifest,
                runtime_sha=runtime_sha,
                environ=environ,
            )
            return {
                "submitted": False,
                "submit_allowed": False,
                "idempotent_replay": False,
                "blocker": readiness["blocker"],
                "job": None,
                "readiness": readiness,
            }
        if (
            job.product_type is not request.product_type
            or job.mode is not request.mode
            or job.idempotency_key != request.idempotency_key
            or job.user_id != request.user_id
            or job.runtime_sha != request.runtime_sha
            or job.expected_worker_sha != request.expected_worker_sha
        ):
            raise ValueError("video_engine_existing_job_request_mismatch")
        if (
            job.worker_job_type != route["worker_job_type"]
            or job.engine_route != route["engine_route"]
            or job.worker_owner != route["worker_owner"]
        ):
            raise ValueError("video_engine_existing_job_route_mismatch")
        return {
            "submitted": False,
            "submit_allowed": False,
            "idempotent_replay": True,
            "blocker": "",
            "job": job,
            "readiness": evaluate_readiness(
                request,
                manifest=manifest,
                runtime_sha=runtime_sha,
                environ=environ,
            ),
        }
    readiness = evaluate_readiness(
        request,
        manifest=manifest,
        runtime_sha=runtime_sha,
        environ=environ,
    )
    if not readiness["submit_allowed"]:
        return {
            "submitted": False,
            "submit_allowed": False,
            "idempotent_replay": False,
            "blocker": readiness["blocker"],
            "job": None,
            "readiness": readiness,
        }
    route = readiness["route"]
    job = _coerce_job(submitter(request, route))
    if job.idempotency_key != request.idempotency_key:
        raise ValueError("video_engine_job_idempotency_mismatch")
    if (
        job.product_type is not request.product_type
        or job.mode is not request.mode
        or job.user_id != request.user_id
        or job.runtime_sha != request.runtime_sha
        or job.expected_worker_sha != request.expected_worker_sha
    ):
        raise ValueError("video_engine_job_request_mismatch")
    if (
        job.worker_job_type != route["worker_job_type"]
        or job.engine_route != route["engine_route"]
        or job.worker_owner != route["worker_owner"]
    ):
        raise ValueError("video_engine_job_route_mismatch")
    jobs_by_idempotency[request.idempotency_key] = job
    return {
        "submitted": True,
        "submit_allowed": True,
        "idempotent_replay": False,
        "blocker": "",
        "job": job,
        "readiness": readiness,
    }
