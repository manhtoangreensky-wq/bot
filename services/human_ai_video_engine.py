"""UI-free Human/AI Video engine for owner-supplied footage in Video Menu 29I.

The local adapter only trims, normalizes, composes, captions, and brands source
footage that has explicit rights and consent receipts. It never presents local
FFmpeg editing as avatar generation, lip-sync, face/voice cloning, or video
generation, and it never selects or calls a paid provider.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping

from services import ffmpeg_text, frame_video_runtime
from services import multiscene_video_pipeline as pipeline
from services import video_engine_contract, video_selfshot2, video_selfshot3


PRODUCT_FAMILY = "human_ai_video"
ROUTE_ID = "human_ai_video_local_v1"
ENGINE_ADAPTER = "human_ai_owner_footage_ffmpeg_v29i"
WORKER_JOB_TYPE = "human_ai_owner_footage_render"
WORKER_OWNER = "local_worker"
CANONICAL_WORKER_CAPABILITY = "human_ai_owner_footage_ffmpeg"
SUPPORTED_MODES = (
    video_engine_contract.VideoEngineMode.SINGLE_SCENE.value,
    video_engine_contract.VideoEngineMode.MULTI_SCENE.value,
)
SUPPORTED_FLOW_PRODUCTS = (
    video_selfshot2.PRODUCT_ID,
    video_selfshot3.PRODUCT_ID,
)
SUPPORTED_EXECUTION_KINDS = ("owner_footage_edit",)
UNSUPPORTED_EXECUTION_KINDS = (
    "avatar_generation",
    "ai_presenter",
    "lip_sync",
    "face_clone",
    "voice_clone",
    "ai_video_generation",
    "direct_video_to_video",
)
HUMAN_AI_VIDEO_ENGINE_FLAG_DEFAULTS = {
    "HUMAN_AI_VIDEO_ENGINE_ENABLED": False,
    "HUMAN_AI_VIDEO_PUBLIC_ALLOWED": False,
    "HUMAN_AI_VIDEO_AUTO_RETRY": False,
    "HUMAN_AI_VIDEO_AUTO_FALLBACK": False,
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
_POSITION_ALIASES = {
    "middle_left": "center_left",
    "middle": "center",
    "middle_right": "center_right",
}
_CONSENT_FIELDS = (
    "source_ownership",
    "person_consent",
    "face_identity_consent",
    "voice_consent",
    "brand_rights",
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
    return json.dumps(
        _json_safe(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _normalize_ratio(value: Any) -> str:
    token = _clean(value or "9:16").lower().replace("x", ":")
    return token if token in {"9:16", "16:9", "1:1", "4:5"} else "9:16"


def _normalize_position(value: Any, fallback: str, field_name: str) -> str:
    raw = _clean(value)
    token = raw.lower().replace("-", "_") if raw else fallback
    token = _POSITION_ALIASES.get(token, token)
    if token not in SUPPORTED_POSITIONS:
        raise ValueError(f"{field_name}_invalid")
    return token


def _safe_job_id(value: Any) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "-", _clean(value)).strip("-.")
    return token or "human-ai-job"


def human_ai_video_engine_flags(
    environ: Mapping[str, Any] | None = None,
) -> dict[str, bool]:
    source = os.environ if environ is None else environ
    return {
        name: _flag(source.get(name, default))
        for name, default in HUMAN_AI_VIDEO_ENGINE_FLAG_DEFAULTS.items()
    }


def shared_human_ai_video_engine_route() -> dict[str, Any]:
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


def human_ai_video_engine_contract(
    environ: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "route_id": ROUTE_ID,
        "product_family": PRODUCT_FAMILY,
        "engine_adapter": ENGINE_ADAPTER,
        "supported_modes": SUPPORTED_MODES,
        "supported_flow_products": SUPPORTED_FLOW_PRODUCTS,
        "supported_execution_kinds": SUPPORTED_EXECUTION_KINDS,
        "unsupported_execution_kinds": UNSUPPORTED_EXECUTION_KINDS,
        "provider_required": False,
        "cloud_provider_calls": 0,
        "automatic_retry": False,
        "automatic_fallback": False,
        "source_footage_required": True,
        "rights_and_consent_required": True,
        "identity_assurance": "verified_source_lineage_not_biometric_comparison",
        "artifact_promise": {
            "container": "mp4",
            "video_stream": True,
            "full_decode": True,
            "ordered_scenes": True,
            "source_audio_when_promised": True,
        },
        "flags": human_ai_video_engine_flags(environ),
    }


@dataclass(frozen=True)
class HumanAIScene:
    scene_id: str
    scene_index: int
    source_asset_id: str
    source_asset_sha256: str
    source_segment_start: float
    source_segment_end: float
    duration_seconds: float
    prompt: str
    negative_prompt: str
    subject_ids: tuple[str, ...]
    relationship_lock_sha256: str
    caption: str = ""


@dataclass(frozen=True)
class HumanAIVideoPlan:
    flow_product_type: str
    mode: str
    execution_kind: str
    scenes: tuple[HumanAIScene, ...]
    source_asset_id: str
    source_asset_path: str
    source_asset_sha256: str
    source_asset_bytes: int
    aspect_ratio: str
    transition: str
    transition_seconds: float
    audio_policy: Mapping[str, Any]
    voice_policy: Mapping[str, Any]
    final_assets: Mapping[str, Any]
    subject_manifest: Mapping[str, Any]
    rights_consent: Mapping[str, Any]
    expected_duration_seconds: float
    approved_snapshot_sha256: str
    scene_order_sha256: str
    plan_sha256: str


def _subject_ids(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    candidates = (
        list(manifest.get("selected_ids") or [])
        or list(manifest.get("subject_ids") or [])
        or [
            item.get("subject_id")
            for item in list(manifest.get("subjects") or [])
            if isinstance(item, Mapping)
        ]
    )
    values = tuple(dict.fromkeys(_clean(item) for item in candidates if _clean(item)))
    if not values and not _flag(manifest.get("motion_only")):
        raise ValueError("human_ai_subject_manifest_required")
    return values


def _person_present(manifest: Mapping[str, Any]) -> bool:
    if list(manifest.get("person_subject_ids") or []):
        return True
    if _clean(manifest.get("selection_type") or manifest.get("selection_mode")) in {
        "person",
        "person_object",
        "multiple",
    }:
        return True
    return any(
        _clean(item.get("subject_type")) == "person"
        for item in list(manifest.get("subjects") or [])
        if isinstance(item, Mapping)
    )


def _object_present(manifest: Mapping[str, Any]) -> bool:
    if list(manifest.get("object_subject_ids") or []):
        return True
    return any(
        _clean(item.get("subject_type")) in {"object", "product"}
        for item in list(manifest.get("subjects") or [])
        if isinstance(item, Mapping)
    )


def _normalize_receipts(
    value: Mapping[str, Any] | None,
    *,
    person_required: bool,
    voice_required: bool,
    brand_required: bool,
) -> dict[str, dict[str, Any]]:
    source = dict(value or {})
    required = {"source_ownership"}
    if person_required:
        required.update({"person_consent", "face_identity_consent"})
    if voice_required:
        required.add("voice_consent")
    if brand_required:
        required.add("brand_rights")
    normalized: dict[str, dict[str, Any]] = {}
    for field_name in _CONSENT_FIELDS:
        row = dict(source.get(field_name) or {})
        receipt_id = _clean(row.get("receipt_id") or row.get("id"))
        approved = _flag(row.get("approved"))
        normalized[field_name] = {
            "approved": approved,
            "receipt_id": receipt_id,
        }
        if field_name in required and (not approved or not receipt_id):
            raise ValueError(f"{field_name}_receipt_required")
    return normalized


def _normalize_final_assets(value: Mapping[str, Any] | None) -> dict[str, Any]:
    source = dict(value or {})
    logo_enabled = _flag(
        source.get("logo_enabled")
        or source.get("enable_logo")
        or source.get("logo_path")
    )
    logo_asset_id = _clean(source.get("logo_asset_id") or "human-ai-brand-logo")
    logo_path = Path(_clean(source.get("logo_path"))).expanduser()
    logo_sha256 = _clean(source.get("logo_sha256")).lower()
    if logo_enabled:
        if not logo_path.is_file() or logo_path.stat().st_size <= 0:
            raise ValueError("human_ai_logo_asset_missing")
        actual_sha = _sha256_file(logo_path)
        if logo_sha256 and logo_sha256 != actual_sha:
            raise ValueError("human_ai_logo_asset_fingerprint_mismatch")
        logo_sha256 = actual_sha
    return {
        "enable_subtitle": _flag(source.get("enable_subtitle")),
        "logo_enabled": logo_enabled,
        "logo_asset_id": logo_asset_id if logo_enabled else "",
        "logo_path": str(logo_path.resolve()) if logo_enabled else "",
        "logo_sha256": logo_sha256 if logo_enabled else "",
        "logo_bytes": logo_path.stat().st_size if logo_enabled else 0,
        "logo_position": _normalize_position(
            source.get("logo_position"), "top_left", "human_ai_logo_position"
        ),
        "watermark_text": _clean(source.get("watermark_text"))[:500],
        "watermark_position": _normalize_position(
            source.get("watermark_position"),
            "bottom_right",
            "human_ai_watermark_position",
        ),
    }


def _scene_material(scene: HumanAIScene) -> dict[str, Any]:
    return {
        "scene_id": scene.scene_id,
        "scene_index": scene.scene_index,
        "source_asset_id": scene.source_asset_id,
        "source_asset_sha256": scene.source_asset_sha256,
        "source_segment_start": scene.source_segment_start,
        "source_segment_end": scene.source_segment_end,
        "duration_seconds": scene.duration_seconds,
        "prompt": scene.prompt,
        "negative_prompt": scene.negative_prompt,
        "subject_ids": list(scene.subject_ids),
        "relationship_lock_sha256": scene.relationship_lock_sha256,
        "caption": scene.caption,
    }


def _plan_material(plan: HumanAIVideoPlan) -> dict[str, Any]:
    final_assets = dict(plan.final_assets or {})
    final_assets.pop("logo_path", None)
    return {
        "flow_product_type": plan.flow_product_type,
        "mode": plan.mode,
        "execution_kind": plan.execution_kind,
        "scenes": [_scene_material(scene) for scene in plan.scenes],
        "source_asset_id": plan.source_asset_id,
        "source_asset_sha256": plan.source_asset_sha256,
        "source_asset_bytes": plan.source_asset_bytes,
        "aspect_ratio": plan.aspect_ratio,
        "transition": plan.transition,
        "transition_seconds": plan.transition_seconds,
        "audio_policy": dict(plan.audio_policy or {}),
        "voice_policy": dict(plan.voice_policy or {}),
        "final_assets": final_assets,
        "subject_manifest": dict(plan.subject_manifest or {}),
        "rights_consent": dict(plan.rights_consent or {}),
        "expected_duration_seconds": plan.expected_duration_seconds,
        "approved_snapshot_sha256": plan.approved_snapshot_sha256,
        "scene_order_sha256": plan.scene_order_sha256,
    }


def _plan_sha256(plan: HumanAIVideoPlan) -> str:
    return _sha256_text(_canonical_json(_plan_material(plan)))


def _approved_snapshot_material(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    source = dict(snapshot)
    source_video = dict(source.get("source_video") or source.get("source_asset") or {})
    source_video.pop("path", None)
    source_video.pop("local_path", None)
    source["source_video"] = source_video
    source.pop("source_asset", None)
    return _json_safe(source)


def _source_audio_requested(snapshot: Mapping[str, Any]) -> bool:
    audio_plan = dict(snapshot.get("audio_plan") or snapshot.get("audio_policy") or {})
    source = audio_plan.get("source")
    if isinstance(source, Mapping):
        return _flag(source.get("enabled"))
    return _flag(
        audio_plan.get("preserve_source_audio")
        or audio_plan.get("source_audio")
        or snapshot.get("preserve_source_audio")
    )


def _voice_policy(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    policy = dict(snapshot.get("voice_policy") or {})
    audio_plan = dict(snapshot.get("audio_plan") or {})
    voice = audio_plan.get("voice")
    if isinstance(voice, Mapping):
        policy.setdefault("promised", _flag(voice.get("enabled")))
        policy.setdefault("kind", _clean(voice.get("kind") or "owner_voiceover"))
    unsupported = any(
        _flag(policy.get(key))
        for key in (
            "lip_sync",
            "lip_sync_requested",
            "face_clone",
            "voice_clone",
            "clone_requested",
            "avatar_generation",
            "ai_presenter",
        )
    )
    if unsupported or _flag(policy.get("promised")):
        raise ValueError("human_ai_voice_generation_capability_missing")
    return _json_safe(policy)


def compile_human_ai_video_plan(
    *,
    approved_snapshot: Mapping[str, Any],
    rights_consent: Mapping[str, Any],
    execution_kind: str,
    transition: str = "cut",
    transition_seconds: float = 0.0,
    final_assets: Mapping[str, Any] | None = None,
) -> HumanAIVideoPlan:
    snapshot = dict(approved_snapshot or {})
    if not _flag(snapshot.get("plan_approved")) or _clean(snapshot.get("plan_status")) != "ready":
        raise ValueError("human_ai_approved_snapshot_required")
    selected_execution = _clean(execution_kind).lower()
    if selected_execution not in SUPPORTED_EXECUTION_KINDS:
        raise ValueError("human_ai_execution_kind_unsupported")
    if _clean(snapshot.get("local_execution_truth")) != "owner_footage_edit":
        raise ValueError("human_ai_local_execution_truth_required")
    flow_product = _clean(snapshot.get("product_type") or snapshot.get("product_id"))
    if flow_product not in SUPPORTED_FLOW_PRODUCTS:
        raise ValueError("human_ai_locked_flow_product_unsupported")

    source = dict(snapshot.get("source_video") or snapshot.get("source_asset") or {})
    source_asset_id = _clean(source.get("asset_id") or source.get("file_id") or "source-human")
    source_path = Path(_clean(source.get("path") or source.get("local_path"))).expanduser()
    if not source_asset_id or not source_path.is_file() or source_path.stat().st_size <= 0:
        raise ValueError("human_ai_source_asset_missing")
    actual_source_sha = _sha256_file(source_path)
    # SelfShot's source_analysis.source_hash is a Telegram metadata fingerprint,
    # not a content digest. Only compare an explicitly supplied content SHA.
    declared_sha = _clean(
        source.get("sha256") or source.get("content_sha256")
    ).lower()
    if declared_sha and declared_sha != actual_source_sha:
        raise ValueError("human_ai_source_asset_fingerprint_mismatch")

    subject_manifest = dict(snapshot.get("subject_manifest") or {})
    subject_ids = _subject_ids(subject_manifest)
    relationship_locks = list(
        snapshot.get("relationship_locks")
        or subject_manifest.get("interaction_graph")
        or []
    )
    relationship_sha = _sha256_text(_canonical_json(relationship_locks))
    preserve_source_audio = _source_audio_requested(snapshot)
    voice_policy = _voice_policy(snapshot)
    normalized_final_assets = _normalize_final_assets(
        final_assets if final_assets is not None else snapshot.get("final_assets")
    )
    normalized_receipts = _normalize_receipts(
        rights_consent,
        person_required=_person_present(subject_manifest),
        voice_required=preserve_source_audio,
        brand_required=bool(
            _object_present(subject_manifest)
            or normalized_final_assets.get("logo_enabled")
            or normalized_final_assets.get("watermark_text")
        ),
    )
    audio_policy = {
        "promised": preserve_source_audio,
        "kind": "approved_source_audio" if preserve_source_audio else "none",
        "preserve_source_audio": preserve_source_audio,
        "source_asset_sha256": actual_source_sha if preserve_source_audio else "",
    }

    selected_transition = _clean(transition or "cut").lower().replace("-", "_")
    if selected_transition not in SUPPORTED_TRANSITIONS:
        raise ValueError("human_ai_transition_unsupported")
    try:
        selected_overlap = max(0.0, min(1.5, float(transition_seconds or 0.0)))
    except (TypeError, ValueError) as exc:
        raise ValueError("human_ai_transition_duration_invalid") from exc
    if selected_transition not in {"cut", "none"} and selected_overlap <= 0:
        raise ValueError("human_ai_transition_duration_invalid")
    if selected_transition in {"cut", "none"}:
        selected_overlap = 0.0

    analysis_duration = float(dict(snapshot.get("source_analysis") or {}).get("duration_seconds") or 0.0)
    if analysis_duration <= 0:
        raise ValueError("human_ai_source_duration_required")
    caption = _clean(dict(snapshot.get("selected_content") or {}).get("title"))[:500]
    compiled: list[HumanAIScene] = []

    if flow_product == video_selfshot2.PRODUCT_ID:
        raw_scenes = list(snapshot.get("scene_plan") or [])
        prompt_rows = {
            int(item.get("scene_index") or item.get("scene_id") or 0): dict(item)
            for item in list(snapshot.get("video_prompts") or [])
            if isinstance(item, Mapping)
        }
        expected_count = int(snapshot.get("scene_count") or len(raw_scenes))
        if not raw_scenes or len(raw_scenes) != expected_count or len(prompt_rows) != expected_count:
            raise ValueError("human_ai_selfshot2_scene_plan_incomplete")
        for ordinal, raw in enumerate(raw_scenes, start=1):
            row = dict(raw or {})
            scene_index = int(row.get("scene_index") or row.get("scene_id") or ordinal)
            if scene_index != ordinal:
                raise ValueError("human_ai_scene_order_invalid")
            start = float(row.get("source_segment_start") or 0.0)
            end = float(row.get("source_segment_end") or 0.0)
            if start < 0 or end <= start or end > analysis_duration + 0.1:
                raise ValueError("human_ai_source_segment_invalid")
            prompt_row = prompt_rows.get(scene_index) or {}
            prompt = _clean(prompt_row.get("prompt"))
            if not prompt:
                raise ValueError("human_ai_scene_prompt_required")
            compiled.append(
                HumanAIScene(
                    scene_id=_clean(row.get("scene_id") or f"scene-{scene_index}"),
                    scene_index=scene_index,
                    source_asset_id=source_asset_id,
                    source_asset_sha256=actual_source_sha,
                    source_segment_start=round(start, 3),
                    source_segment_end=round(end, 3),
                    duration_seconds=round(end - start, 3),
                    prompt=prompt,
                    negative_prompt=_clean(prompt_row.get("negative_prompt")),
                    subject_ids=subject_ids,
                    relationship_lock_sha256=relationship_sha,
                    caption=caption or f"Scene {scene_index}",
                )
            )
    else:
        layer_rules = dict(snapshot.get("layer_rules") or {})
        if any(_clean(state) == "transform" for state in layer_rules.values()):
            raise ValueError("human_ai_generation_capability_missing")
        segment = dict(snapshot.get("source_segment") or {})
        start = float(segment.get("start_ms") or 0) / 1000.0
        end = float(segment.get("end_ms") or 0) / 1000.0
        if start < 0 or end <= start or end > analysis_duration + 0.1:
            raise ValueError("human_ai_source_segment_invalid")
        compiled_prompt = dict(snapshot.get("compiled_prompt") or {})
        prompt_rows = [
            dict(item)
            for item in list(compiled_prompt.get("stage_prompts") or snapshot.get("video_prompts") or [])
            if isinstance(item, Mapping)
        ]
        prompt = "\n".join(_clean(item.get("prompt")) for item in prompt_rows if _clean(item.get("prompt")))
        negative = "\n".join(
            _clean(item.get("negative_prompt"))
            for item in prompt_rows
            if _clean(item.get("negative_prompt"))
        )
        if not prompt:
            raise ValueError("human_ai_scene_prompt_required")
        compiled.append(
            HumanAIScene(
                scene_id="scene-1",
                scene_index=1,
                source_asset_id=source_asset_id,
                source_asset_sha256=actual_source_sha,
                source_segment_start=round(start, 3),
                source_segment_end=round(end, 3),
                duration_seconds=round(end - start, 3),
                prompt=prompt,
                negative_prompt=negative,
                subject_ids=subject_ids,
                relationship_lock_sha256=relationship_sha,
                caption=caption or "One take",
            )
        )

    mode = "single_scene" if len(compiled) == 1 else "multi_scene"
    expected_duration = round(
        sum(scene.duration_seconds for scene in compiled)
        - selected_overlap * max(0, len(compiled) - 1),
        3,
    )
    snapshot_sha = _sha256_text(_canonical_json(_approved_snapshot_material(snapshot)))
    scene_order_sha = _sha256_text(
        _canonical_json(
            [
                {
                    "scene_index": scene.scene_index,
                    "scene_id": scene.scene_id,
                    "start": scene.source_segment_start,
                    "end": scene.source_segment_end,
                    "prompt_sha256": _sha256_text(scene.prompt),
                }
                for scene in compiled
            ]
        )
    )
    provisional = HumanAIVideoPlan(
        flow_product_type=flow_product,
        mode=mode,
        execution_kind=selected_execution,
        scenes=tuple(compiled),
        source_asset_id=source_asset_id,
        source_asset_path=str(source_path.resolve()),
        source_asset_sha256=actual_source_sha,
        source_asset_bytes=source_path.stat().st_size,
        aspect_ratio=_normalize_ratio(snapshot.get("aspect_ratio") or "9:16"),
        transition=selected_transition,
        transition_seconds=selected_overlap,
        audio_policy=_json_safe(audio_policy),
        voice_policy=_json_safe(voice_policy),
        final_assets=_json_safe(normalized_final_assets),
        subject_manifest=_json_safe(subject_manifest),
        rights_consent=_json_safe(normalized_receipts),
        expected_duration_seconds=expected_duration,
        approved_snapshot_sha256=snapshot_sha,
        scene_order_sha256=scene_order_sha,
        plan_sha256="",
    )
    return replace(provisional, plan_sha256=_plan_sha256(provisional))


def validate_human_ai_video_plan(plan: HumanAIVideoPlan) -> dict[str, Any]:
    blockers: list[str] = []
    if not isinstance(plan, HumanAIVideoPlan):
        return {"ok": False, "blocker": "human_ai_plan_type_invalid", "blockers": ["human_ai_plan_type_invalid"]}
    if plan.flow_product_type not in SUPPORTED_FLOW_PRODUCTS:
        blockers.append("human_ai_locked_flow_product_unsupported")
    if plan.execution_kind not in SUPPORTED_EXECUTION_KINDS:
        blockers.append("human_ai_execution_kind_unsupported")
    if plan.mode not in SUPPORTED_MODES:
        blockers.append("human_ai_mode_unsupported")
    if plan.mode == "single_scene" and len(plan.scenes) != 1:
        blockers.append("single_scene_requires_one_scene")
    if plan.mode == "multi_scene" and len(plan.scenes) < 2:
        blockers.append("multi_scene_requires_multiple_scenes")
    if [scene.scene_index for scene in plan.scenes] != list(range(1, len(plan.scenes) + 1)):
        blockers.append("human_ai_scene_order_invalid")
    if any(scene.subject_ids != plan.scenes[0].subject_ids for scene in plan.scenes[1:]):
        blockers.append("human_ai_subject_continuity_manifest_mismatch")
    if _plan_sha256(plan) != plan.plan_sha256:
        blockers.append("human_ai_plan_fingerprint_mismatch")
    return {
        "ok": not blockers,
        "blocker": blockers[0] if blockers else "",
        "blockers": blockers,
        "mode": plan.mode,
        "scene_count": len(plan.scenes),
        "generation_claim_supported": False,
        "execution_truth": "owner_footage_edit_only",
    }


def build_human_ai_video_request(
    *,
    user_id: int,
    confirmation_id: str,
    language: str,
    plan: HumanAIVideoPlan,
    explicit_confirmation_receipt: Mapping[str, Any],
    runtime_sha: str,
    expected_worker_sha: str,
    admin_no_charge: bool,
    charge_plan: Mapping[str, Any] | None = None,
) -> video_engine_contract.VideoEngineRequest:
    validation = validate_human_ai_video_plan(plan)
    if not validation.get("ok"):
        raise ValueError(_clean(validation.get("blocker") or "human_ai_plan_invalid"))
    payload = {
        "plan_sha256": plan.plan_sha256,
        "approved_snapshot_sha256": plan.approved_snapshot_sha256,
        "scene_order_sha256": plan.scene_order_sha256,
        "flow_product_type": plan.flow_product_type,
        "execution_kind": plan.execution_kind,
        "admin_no_charge": bool(admin_no_charge),
        "charge_plan": _json_safe(dict(charge_plan or {})),
        "provider_calls": 0,
        "automatic_retry": False,
        "automatic_fallback": False,
    }
    input_assets = (
        {
            "asset_id": plan.source_asset_id,
            "sha256": plan.source_asset_sha256,
            "bytes": plan.source_asset_bytes,
        },
    )
    key = video_engine_contract.stable_request_idempotency_key(
        confirmation_id=confirmation_id,
        product_type=video_engine_contract.VideoProduct.HUMAN_AI_VIDEO,
        mode=plan.mode,
        payload=payload,
        user_id=user_id,
        language=language,
        approved_plan={
            "plan_sha256": plan.plan_sha256,
            "flow_product_type": plan.flow_product_type,
            "scene_count": len(plan.scenes),
        },
        input_assets=input_assets,
        aspect_ratio=plan.aspect_ratio,
        duration_profile={
            "expected_duration_seconds": plan.expected_duration_seconds,
            "scene_count": len(plan.scenes),
        },
        audio_policy=plan.audio_policy,
        voice_policy=plan.voice_policy,
        provider_selection="local",
        runtime_sha=runtime_sha,
        expected_worker_sha=expected_worker_sha,
    )
    return video_engine_contract.VideoEngineRequest(
        request_id=f"h29i-{key[:24]}",
        confirmation_id=confirmation_id,
        idempotency_key=key,
        product_type=video_engine_contract.VideoProduct.HUMAN_AI_VIDEO,
        mode=plan.mode,
        user_id=user_id,
        language=language,
        approved_plan={
            "plan_sha256": plan.plan_sha256,
            "flow_product_type": plan.flow_product_type,
            "scene_count": len(plan.scenes),
        },
        input_assets=input_assets,
        aspect_ratio=plan.aspect_ratio,
        duration_profile={
            "expected_duration_seconds": plan.expected_duration_seconds,
            "scene_count": len(plan.scenes),
        },
        audio_policy=plan.audio_policy,
        voice_policy=plan.voice_policy,
        provider_selection="local",
        explicit_confirmation_receipt=explicit_confirmation_receipt,
        runtime_sha=runtime_sha,
        expected_worker_sha=expected_worker_sha,
        confirmed=True,
        payload=payload,
    )


def _sequence(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (_clean(value),) if _clean(value) else ()
    try:
        return tuple(_clean(item) for item in value if _clean(item))
    except TypeError:
        return ()


def human_ai_video_engine_readiness(
    request: video_engine_contract.VideoEngineRequest,
    *,
    plan: HumanAIVideoPlan,
    manifest: Mapping[str, Any],
    runtime_sha: str,
    environ: Mapping[str, Any] | None,
    public_request: bool = False,
) -> dict[str, Any]:
    flags = human_ai_video_engine_flags(environ)
    blocker = ""
    if not flags["HUMAN_AI_VIDEO_ENGINE_ENABLED"]:
        blocker = "human_ai_video_engine_disabled"
    elif public_request and not flags["HUMAN_AI_VIDEO_PUBLIC_ALLOWED"]:
        blocker = "human_ai_video_public_disabled"
    elif flags["HUMAN_AI_VIDEO_AUTO_RETRY"]:
        blocker = "automatic_retry_forbidden"
    elif flags["HUMAN_AI_VIDEO_AUTO_FALLBACK"]:
        blocker = "automatic_fallback_forbidden"
    elif request.product_type is not video_engine_contract.VideoProduct.HUMAN_AI_VIDEO:
        blocker = "human_ai_product_type_mismatch"
    elif request.mode.value != plan.mode:
        blocker = "human_ai_mode_mismatch"
    elif _clean(request.payload.get("plan_sha256")) != plan.plan_sha256:
        blocker = "human_ai_request_plan_mismatch"
    elif _clean(request.payload.get("flow_product_type")) != plan.flow_product_type:
        blocker = "human_ai_request_flow_mismatch"
    elif _clean(request.payload.get("execution_kind")) != "owner_footage_edit":
        blocker = "human_ai_execution_kind_unsupported"
    else:
        validation = validate_human_ai_video_plan(plan)
        if not validation.get("ok"):
            blocker = _clean(validation.get("blocker") or "human_ai_plan_invalid")
    shared = {
        "ready": False,
        "submit_allowed": False,
        "blocker": blocker,
        "route": shared_human_ai_video_engine_route(),
    }
    if not blocker:
        shared = video_engine_contract.evaluate_readiness(
            request,
            manifest=manifest,
            runtime_sha=runtime_sha,
            environ=environ,
        )
        blocker = _clean(shared.get("blocker"))
    if not blocker and ENGINE_ADAPTER not in set(_sequence(manifest.get("engine_adapters"))):
        blocker = "worker_engine_adapter_missing"
    if not blocker and not _flag(manifest.get("artifact_ready")):
        blocker = "worker_artifact_output_unavailable"
    return {
        **dict(shared),
        "ready": not blocker,
        "submit_allowed": not blocker,
        "blocker": blocker,
        "route": shared_human_ai_video_engine_route(),
        "execution_kind": plan.execution_kind,
        "flow_product_type": plan.flow_product_type,
        "provider_calls": 0,
        "paid_provider_calls": 0,
        "automatic_retry": False,
        "automatic_fallback": False,
    }


@dataclass
class HumanAIVideoEngineLedger:
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


def _ledger_counters(ledger: HumanAIVideoEngineLedger) -> dict[str, int]:
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
        job_id=f"p29i-{request.idempotency_key[:24]}",
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
    ledger: HumanAIVideoEngineLedger,
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


def dispatch_human_ai_video(
    request: video_engine_contract.VideoEngineRequest,
    *,
    plan: HumanAIVideoPlan,
    manifest: Mapping[str, Any],
    runtime_sha: str,
    ledger: HumanAIVideoEngineLedger,
    environ: Mapping[str, Any] | None,
    public_request: bool = False,
) -> dict[str, Any]:
    readiness = human_ai_video_engine_readiness(
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
                blocker=_clean(readiness.get("blocker") or "human_ai_video_not_ready"),
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
                blocker=_clean(guarded.get("blocker") or "human_ai_job_not_created"),
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


def _font_path() -> str:
    candidates = (
        _clean(os.environ.get("TOANAAS_FFMPEG_FONT")),
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    return next((str(Path(item).resolve()) for item in candidates if item and Path(item).is_file()), "")


def _drawtext_position(position: str) -> tuple[str, str]:
    token = _POSITION_ALIASES.get(_clean(position).lower().replace("-", "_"), _clean(position).lower().replace("-", "_"))
    if token in {"top_left", "center_left", "bottom_left"}:
        x_expr = "24"
    elif token in {"top_center", "center", "bottom_center"}:
        x_expr = "(w-text_w)/2"
    else:
        x_expr = "w-text_w-24"
    if token in {"top_left", "top_center", "top_right"}:
        y_expr = "24"
    elif token in {"center_left", "center", "center_right"}:
        y_expr = "(h-text_h)/2"
    else:
        y_expr = "h-text_h-24"
    return x_expr, y_expr


def _full_decode(path: str, ffmpeg: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [ffmpeg, "-v", "error", "-i", path, "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "reason": "human_ai_full_decode_failed"}
    return {
        "ok": completed.returncode == 0,
        "reason": "" if completed.returncode == 0 else "human_ai_full_decode_failed",
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
                "16",
                "-f",
                "framemd5",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "reason": "human_ai_motion_probe_failed", "unique_frames": 0}
    hashes = {
        line.rsplit(",", 1)[-1].strip()
        for line in completed.stdout.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "," in line
    }
    ok = completed.returncode == 0 and len(hashes) > 1
    return {
        "ok": ok,
        "reason": "" if ok else "human_ai_motion_evidence_missing",
        "unique_frames": len(hashes),
    }


def _audio_evidence(path: str, ffmpeg: str, *, promised: bool) -> dict[str, Any]:
    if not promised:
        return {"ok": True, "promised": False, "non_silent": False, "mean_volume_db": None}
    try:
        completed = subprocess.run(
            [ffmpeg, "-v", "info", "-i", path, "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "promised": True, "non_silent": False, "mean_volume_db": None}
    match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", completed.stderr or "")
    mean_volume = float(match.group(1)) if match else None
    non_silent = bool(completed.returncode == 0 and mean_volume is not None and mean_volume > -75.0)
    return {
        "ok": non_silent,
        "promised": True,
        "non_silent": non_silent,
        "mean_volume_db": mean_volume,
    }


def _execution_result(
    ledger: HumanAIVideoEngineLedger,
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
    ledger: HumanAIVideoEngineLedger,
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


def _extract_source_segment(
    *,
    ffmpeg: str,
    source_path: str,
    output_path: str,
    start_seconds: float,
    duration_seconds: float,
    width: int,
    height: int,
    preserve_audio: bool,
    subtitle_text: str = "",
    watermark_text: str = "",
    watermark_position: str = "bottom_right",
) -> dict[str, Any]:
    filters = [
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        "setsar=1,fps=24,setpts=PTS-STARTPTS,format=yuv420p"
    ]
    clean_subtitle = ffmpeg_text.sanitize_overlay_text(subtitle_text)
    clean_watermark = ffmpeg_text.sanitize_overlay_text(watermark_text)
    if clean_subtitle or clean_watermark:
        font = _font_path()
        if not font:
            return {
                "ok": False,
                "reason": "human_ai_subtitle_font_missing",
                "safe_error": "subtitle_font_missing",
            }
        if clean_subtitle:
            filters.append(
                "drawtext="
                f"fontfile='{ffmpeg_text.escape_filter_path(font)}':"
                f"text='{ffmpeg_text.escape_filter_text(clean_subtitle)}':"
                f"{ffmpeg_text.DRAWTEXT_NO_EXPANSION}:"
                "fontcolor=white:fontsize=32:borderw=2:bordercolor=black@0.75:"
                "box=1:boxcolor=black@0.25:boxborderw=8:"
                "x=(w-text_w)/2:y=h-text_h-36"
            )
        if clean_watermark:
            x_expr, y_expr = _drawtext_position(watermark_position)
            filters.append(
                "drawtext="
                f"fontfile='{ffmpeg_text.escape_filter_path(font)}':"
                f"text='{ffmpeg_text.escape_filter_text(clean_watermark)}':"
                f"{ffmpeg_text.DRAWTEXT_NO_EXPANSION}:"
                "fontcolor=white@0.90:fontsize=24:borderw=2:bordercolor=black@0.70:"
                "box=1:boxcolor=black@0.20:boxborderw=6:"
                f"x={x_expr}:y={y_expr}"
            )
    command = [
        ffmpeg,
        "-y",
        "-ss",
        f"{max(0.0, start_seconds):.3f}",
        "-i",
        source_path,
        "-t",
        f"{max(0.1, duration_seconds):.3f}",
        "-map",
        "0:v:0",
        "-vf",
        ",".join(filters),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
    ]
    if preserve_audio:
        command.extend(
            [
                "-map",
                "0:a:0?",
                "-af",
                "aresample=48000:async=1:first_pts=0,apad,atrim=duration="
                f"{max(0.1, duration_seconds):.3f},asetpts=PTS-STARTPTS",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-ac",
                "2",
            ]
        )
    else:
        command.append("-an")
    command.extend(
        [
            "-map_metadata",
            "-1",
            "-video_track_timescale",
            "90000",
            "-movflags",
            "+faststart",
            output_path,
        ]
    )
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(120, int(duration_seconds * 30)),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "reason": "human_ai_scene_render_failed", "safe_error": type(exc).__name__}
    return {
        "ok": completed.returncode == 0 and Path(output_path).is_file() and Path(output_path).stat().st_size > 0,
        "reason": "" if completed.returncode == 0 else "human_ai_scene_render_failed",
        "safe_error": _clean(completed.stderr)[-500:] if completed.returncode else "",
        "command_contract": {
            "source_segment_start": round(start_seconds, 3),
            "duration_seconds": round(duration_seconds, 3),
            "preserve_audio": preserve_audio,
            "output_width": width,
            "output_height": height,
            "subtitle_burned": bool(clean_subtitle),
            "watermark_burned": bool(clean_watermark),
        },
    }


def execute_human_ai_video_local(
    request: video_engine_contract.VideoEngineRequest,
    *,
    plan: HumanAIVideoPlan,
    manifest: Mapping[str, Any],
    runtime_sha: str,
    ledger: HumanAIVideoEngineLedger,
    output_root: str | Path,
    source_asset_paths: Mapping[str, str],
    environ: Mapping[str, Any] | None,
    final_asset_paths: Mapping[str, str] | None = None,
    ffmpeg_path: str = "",
    ffprobe_path: str = "",
    public_request: bool = False,
) -> dict[str, Any]:
    dispatched = dispatch_human_ai_video(
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
        return {**dispatched, "ok": False, "blocker": "human_ai_job_not_found"}
    artifact = Path(_clean(record.get("artifact_path")))
    if artifact.is_file() and record.get("validation", {}).get("ok"):
        return _execution_result(ledger, record, ok=True, idempotent_replay=True)
    if record.get("render_attempted"):
        return _fail_record(
            ledger,
            record,
            _clean(record.get("blocker") or "human_ai_render_not_retriable"),
            idempotent_replay=True,
        )
    record["render_attempted"] = True

    ffmpeg = ffmpeg_path or shutil.which("ffmpeg") or ""
    ffprobe = ffprobe_path or shutil.which("ffprobe") or ""
    if not ffmpeg:
        return _fail_record(ledger, record, "ffmpeg_missing")
    if not ffprobe:
        return _fail_record(ledger, record, "ffprobe_missing")

    selected_source = Path(
        _clean(source_asset_paths.get(plan.source_asset_id) or plan.source_asset_path)
    )
    if not selected_source.is_file() or selected_source.stat().st_size <= 0:
        return _fail_record(ledger, record, "human_ai_source_asset_missing")
    if _sha256_file(selected_source) != plan.source_asset_sha256:
        return _fail_record(
            ledger, record, "human_ai_source_asset_fingerprint_mismatch"
        )

    final_assets = dict(plan.final_assets or {})
    selected_logo = ""
    if final_assets.get("logo_enabled"):
        logo_asset_id = _clean(final_assets.get("logo_asset_id"))
        selected_logo_path = Path(
            _clean(
                (final_asset_paths or {}).get(logo_asset_id)
                or final_assets.get("logo_path")
            )
        )
        if not selected_logo_path.is_file() or selected_logo_path.stat().st_size <= 0:
            return _fail_record(ledger, record, "human_ai_logo_asset_missing")
        if _sha256_file(selected_logo_path) != _clean(final_assets.get("logo_sha256")):
            return _fail_record(
                ledger, record, "human_ai_logo_asset_fingerprint_mismatch"
            )
        selected_logo = str(selected_logo_path.resolve())

    root = Path(output_root).resolve()
    workspace = (root / _safe_job_id(record["job_id"])).resolve()
    try:
        workspace.relative_to(root)
    except ValueError:
        return _fail_record(ledger, record, "human_ai_output_path_unsafe")
    scene_dir = workspace / "scenes"
    evidence_dir = workspace / "evidence"
    composition_dir = workspace / "composition"
    scene_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    composition_dir.mkdir(parents=True, exist_ok=True)
    record["evidence_dir"] = str(evidence_dir)

    width, height = _output_geometry(plan.aspect_ratio)
    preserve_source_audio = _flag(plan.audio_policy.get("preserve_source_audio"))
    subtitle_requested = _flag(final_assets.get("enable_subtitle"))
    watermark_text = _clean(final_assets.get("watermark_text"))
    scene_clip_paths: dict[int, str] = {}
    pipeline_scenes: list[pipeline.SceneSpec] = []
    consent_receipt_ids = {
        name: _clean(dict(plan.rights_consent.get(name) or {}).get("receipt_id"))
        for name in _CONSENT_FIELDS
        if _clean(dict(plan.rights_consent.get(name) or {}).get("receipt_id"))
    }

    for scene in plan.scenes:
        clip_path = scene_dir / f"scene_{scene.scene_index:03d}.mp4"
        rendered = _extract_source_segment(
            ffmpeg=ffmpeg,
            source_path=str(selected_source.resolve()),
            output_path=str(clip_path),
            start_seconds=scene.source_segment_start,
            duration_seconds=scene.duration_seconds,
            width=width,
            height=height,
            preserve_audio=preserve_source_audio,
            subtitle_text=scene.caption if subtitle_requested else "",
            watermark_text=watermark_text,
            watermark_position=_clean(
                final_assets.get("watermark_position") or "bottom_right"
            ),
        )
        if not rendered.get("ok"):
            record["safe_error"] = _clean(rendered.get("safe_error"))
            return _fail_record(
                ledger,
                record,
                _clean(rendered.get("reason") or "human_ai_scene_render_failed"),
            )
        clip_probe = frame_video_runtime.probe_mp4(
            str(clip_path),
            scene.duration_seconds,
            expects_audio=preserve_source_audio,
            ffprobe_path=ffprobe,
        )
        clip_motion = _motion_evidence(str(clip_path), ffmpeg)
        if not clip_probe.get("ok"):
            return _fail_record(
                ledger,
                record,
                _clean(clip_probe.get("reason") or "human_ai_scene_invalid"),
            )
        if not clip_motion.get("ok"):
            return _fail_record(
                ledger,
                record,
                _clean(clip_motion.get("reason") or "human_ai_motion_evidence_missing"),
            )
        ledger.render_count += 1
        scene_clip_paths[scene.scene_index] = str(clip_path)
        scene_manifest = {
            **_scene_material(scene),
            "flow_product_type": plan.flow_product_type,
            "execution_kind": plan.execution_kind,
            "source_asset_path_runtime": str(selected_source.resolve()),
            "source_lineage_verified": True,
            "prompt_sha256": _sha256_text(scene.prompt),
            "negative_prompt_sha256": _sha256_text(scene.negative_prompt),
            "consent_receipt_ids": consent_receipt_ids,
            "clip_path": str(clip_path),
            "clip_sha256": _sha256_file(clip_path),
            "clip_probe": clip_probe,
            "motion_evidence": clip_motion,
            "render_contract": dict(rendered.get("command_contract") or {}),
            "subtitle_burned": bool(
                dict(rendered.get("command_contract") or {}).get("subtitle_burned")
            ),
            "watermark_burned": bool(
                dict(rendered.get("command_contract") or {}).get("watermark_burned")
            ),
            "identity_assurance": "source_footage_lineage_not_biometric_comparison",
            "provider_calls": 0,
        }
        _write_json(
            evidence_dir / f"scene_{scene.scene_index:03d}_manifest.json",
            scene_manifest,
        )
        pipeline_scenes.append(
            pipeline.SceneSpec(
                scene_id=scene.scene_index,
                title=scene.caption or scene.scene_id,
                visual_prompt=scene.prompt,
                video_prompt=scene.prompt,
                narration_text=scene.caption or None,
                target_duration_sec=scene.duration_seconds,
                aspect_ratio=plan.aspect_ratio,
                transition=(
                    plan.transition if scene.scene_index < len(plan.scenes) else "cut"
                ),
                seed_image_path=None,
                provider_params={
                    "provider": "local",
                    "execution_kind": plan.execution_kind,
                    "source_asset_sha256": plan.source_asset_sha256,
                },
            )
        )

    subtitle_path = ""
    if subtitle_requested:
        subtitle_path = pipeline.build_scene_subtitle(
            pipeline_scenes,
            [scene.duration_seconds for scene in plan.scenes],
            str(composition_dir / "scene_subtitles.srt"),
        )
    composition = pipeline.finalize_multiscene_scene_clips(
        user_id=str(request.user_id),
        job_id=record["job_id"],
        workspace_dir=str(composition_dir),
        scenes=pipeline_scenes,
        scene_clip_paths=scene_clip_paths,
        logo_path=selected_logo or None,
        enable_voice=False,
        # Captions are burned into each verified source scene with an explicit
        # font file. The SRT above remains the timing/evidence artifact.
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
        preserve_scene_audio=preserve_source_audio,
    )
    if not composition.get("ok") or not _clean(composition.get("final_video_path")):
        record["composition"] = _json_safe(composition)
        return _fail_record(
            ledger,
            record,
            _clean(composition.get("error") or "human_ai_composition_failed"),
        )
    ledger.compose_count += 1
    final_path = Path(_clean(composition.get("final_video_path")))
    final_probe = frame_video_runtime.probe_mp4(
        str(final_path),
        float(
            composition.get("target_duration_sec")
            or plan.expected_duration_seconds
        ),
        expects_audio=preserve_source_audio,
        ffprobe_path=ffprobe,
    )
    decode = _full_decode(str(final_path), ffmpeg)
    motion = _motion_evidence(str(final_path), ffmpeg)
    audio = _audio_evidence(
        str(final_path), ffmpeg, promised=preserve_source_audio
    )
    scene_order = list(composition.get("scene_order") or [])
    expected_order = [scene.scene_index for scene in plan.scenes]
    scene_coverage_complete = bool(
        composition.get("scene_coverage_valid_bool")
        and scene_order == expected_order
        and not list(composition.get("missing_scene_indexes") or [])
    )
    master_path = Path(_clean(composition.get("master_video_path")))
    visual_postprocess_requested = bool(selected_logo)
    visual_postprocess_applied = bool(
        not visual_postprocess_requested
        or (
            master_path.is_file()
            and final_path.is_file()
            and _sha256_file(master_path) != _sha256_file(final_path)
        )
    )
    identity_continuity = {
        "ok": bool(
            scene_coverage_complete
            and decode.get("ok")
            and all(
                scene.source_asset_sha256 == plan.source_asset_sha256
                and scene.subject_ids == plan.scenes[0].subject_ids
                for scene in plan.scenes
            )
        ),
        "method": "verified_source_footage_lineage",
        "biometric_comparison_claimed": False,
        "source_asset_sha256": plan.source_asset_sha256,
        "subject_ids": list(plan.scenes[0].subject_ids),
        "generative_identity_transform": False,
    }
    subtitle_applied = bool(
        not subtitle_requested
        or (
            Path(subtitle_path).is_file()
            and all(
                json.loads(
                    (
                        evidence_dir
                        / f"scene_{scene.scene_index:03d}_manifest.json"
                    ).read_text(encoding="utf-8")
                ).get("subtitle_burned")
                for scene in plan.scenes
            )
        )
    )
    watermark_applied = bool(
        not watermark_text
        or all(
            json.loads(
                (
                    evidence_dir / f"scene_{scene.scene_index:03d}_manifest.json"
                ).read_text(encoding="utf-8")
            ).get("watermark_burned")
            for scene in plan.scenes
        )
    )
    final_assets_applied = bool(
        visual_postprocess_applied and subtitle_applied and watermark_applied
    )
    validation = {
        **final_probe,
        "ok": bool(
            final_probe.get("ok")
            and decode.get("ok")
            and motion.get("ok")
            and audio.get("ok")
            and scene_coverage_complete
            and identity_continuity["ok"]
            and final_assets_applied
        ),
        "full_decode": bool(decode.get("ok")),
        "motion_valid": bool(motion.get("ok")),
        "unique_frames": int(motion.get("unique_frames") or 0),
        "audio_non_silent": bool(audio.get("non_silent")),
        "audio_mean_volume_db": audio.get("mean_volume_db"),
        "scene_count": len(plan.scenes),
        "scene_order": expected_order,
        "scene_coverage_complete": scene_coverage_complete,
        "scene_order_sha256": plan.scene_order_sha256,
        "plan_sha256": plan.plan_sha256,
        "approved_snapshot_sha256": plan.approved_snapshot_sha256,
        "identity_continuity": identity_continuity,
        "transition_plan": list(composition.get("transition_plan") or []),
        "compose_count": 1,
        "provider_calls": 0,
        "paid_provider_calls": 0,
        "subtitle_applied": bool(subtitle_requested and subtitle_applied),
        "subtitle_path": subtitle_path,
        "logo_applied": bool(selected_logo and visual_postprocess_applied),
        "watermark_applied": bool(watermark_text and watermark_applied),
        "final_assets_applied": final_assets_applied,
        "execution_truth": "owner_footage_edit_only",
        "generation_claim_supported": False,
    }
    if not validation["ok"]:
        record["validation"] = validation
        blocker = _clean(
            final_probe.get("reason")
            or decode.get("reason")
            or motion.get("reason")
            or ("human_ai_promised_audio_invalid" if not audio.get("ok") else "")
            or (
                "human_ai_scene_coverage_incomplete"
                if not scene_coverage_complete
                else ""
            )
            or (
                "human_ai_identity_continuity_evidence_missing"
                if not identity_continuity["ok"]
                else ""
            )
            or (
                "human_ai_final_assets_not_applied"
                if not final_assets_applied
                else ""
            )
            or "human_ai_artifact_invalid"
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
            "approved_snapshot_sha256": plan.approved_snapshot_sha256,
            "scene_order_sha256": plan.scene_order_sha256,
            "consent_receipt_ids": consent_receipt_ids,
            "provider_calls": 0,
            "paid_provider_calls": 0,
            "automatic_retry": False,
            "automatic_fallback": False,
        },
    )
    _write_json(evidence_dir / "validation_report.json", validation)
    return _execution_result(ledger, record, ok=True)


def _finalize_result(
    ledger: HumanAIVideoEngineLedger,
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


def finalize_human_ai_video(
    *,
    ledger: HumanAIVideoEngineLedger,
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
            "blocker": "human_ai_job_not_found",
            "terminal_state": "failed_no_charge",
            "idempotent_replay": False,
            **_ledger_counters(ledger),
        }
    if record.get("terminal_report", {}).get("emitted"):
        return _finalize_result(ledger, record, ok=True, idempotent_replay=True)
    if not record.get("validation", {}).get("ok"):
        record["terminal_state"] = "failed_no_charge"
        record["blocker"] = "human_ai_artifact_not_validated"
        return _finalize_result(
            ledger,
            record,
            ok=False,
            blocker="human_ai_artifact_not_validated",
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
        record["blocker"] = "human_ai_artifact_changed_after_validation"
        return _finalize_result(
            ledger,
            record,
            ok=False,
            blocker="human_ai_artifact_changed_after_validation",
        )
    evidence_dir = Path(_clean(record.get("evidence_dir")))

    if not record.get("delivery", {}).get("accepted"):
        if record.get("delivery_attempted"):
            return _finalize_result(
                ledger, record, ok=False, blocker="delivery_not_accepted"
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
                ledger, record, ok=False, blocker="delivery_not_accepted"
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
                ledger, record, ok=False, blocker="charge_not_recorded"
            )
        request = record.get("request")
        payload = dict(
            request.payload
            if isinstance(request, video_engine_contract.VideoEngineRequest)
            else {}
        )
        admin_no_charge = bool(payload.get("admin_no_charge"))
        amount = (
            0
            if admin_no_charge
            else int((payload.get("charge_plan") or {}).get("amount_xu") or 0)
        )
        if not admin_no_charge and amount <= 0:
            record["blocker"] = "charge_plan_missing"
            return _finalize_result(
                ledger, record, ok=False, blocker="charge_plan_missing"
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
                ledger, record, ok=False, blocker="charge_not_recorded"
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
                        "delivery_message_id": _clean(
                            record["delivery"].get("message_id")
                        ),
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
            _write_json(
                evidence_dir / "terminal_report.json", record["terminal_report"]
            )
    return _finalize_result(ledger, record, ok=True)
