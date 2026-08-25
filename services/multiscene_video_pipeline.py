"""Telegram-free blackbox pipeline for short multi-scene videos.

This module has no billing, Telegram, or provider credentials. Callers own
confirmation, queueing, provider selection, and final delivery.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Callable

from services import ffmpeg_text


DEFAULT_TEMP_ROOT = os.path.join(tempfile.gettempdir(), "toanaas_multiscene_blackbox")
DEFAULT_VIDEO_TRACK_TIMESCALE = 90_000
DEFAULT_NORMALIZED_FPS = 30
DEFAULT_AUDIO_SAMPLE_RATE = 48_000
DEFAULT_AUDIO_CHANNELS = 2

_XFADE_TRANSITIONS = {
    "fade": "fade",
    "dissolve": "dissolve",
    "wipe_left": "wipeleft",
    "wipe_right": "wiperight",
    "wipe_up": "wipeup",
    "wipe_down": "wipedown",
    "slide_left": "slideleft",
    "slide_right": "slideright",
    "slide_up": "slideup",
    "slide_down": "slidedown",
    "circle_open": "circleopen",
    "circle_close": "circleclose",
    "fade_black": "fadeblack",
    "fade_white": "fadewhite",
}

_SEMANTIC_CUT_TRANSITIONS = frozenset(
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


@dataclass
class SceneSpec:
    scene_id: int
    title: str
    visual_prompt: str
    video_prompt: str
    narration_text: str | None = None
    target_duration_sec: float = 6.0
    aspect_ratio: str = "9:16"
    transition: str | None = None
    seed_image_path: str | None = None
    provider_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class SceneRenderResult:
    scene_id: int
    ok: bool
    raw_video_path: str | None = None
    normalized_video_path: str | None = None
    duration_sec: float | None = None
    retry_count: int = 0
    error: str | None = None
    provider: str | None = None
    provider_task_id: str | None = None
    provider_status: str | None = None
    dispatch_attempts: int = 0
    result_url: str | None = None
    winner_task: str | None = None


@dataclass
class MultisceneManifest:
    job_id: str
    user_id: str
    workspace_dir: str
    scene_specs: list[dict[str, Any]] = field(default_factory=list)
    scene_results: list[dict[str, Any]] = field(default_factory=list)
    required_scene_indexes: list[int] = field(default_factory=list)
    task_ids_by_scene: dict[str, list[str]] = field(default_factory=dict)
    dispatch_attempts_by_scene: dict[str, int] = field(default_factory=dict)
    provider_status_by_scene: dict[str, str] = field(default_factory=dict)
    raw_clip_paths_by_scene: dict[str, str] = field(default_factory=dict)
    normalized_clip_paths_by_scene: dict[str, str] = field(default_factory=dict)
    retry_count_by_scene: dict[str, int] = field(default_factory=dict)
    winner_task_by_scene: dict[str, str] = field(default_factory=dict)
    scene_order: list[int] = field(default_factory=list)
    expected_duration_sec: float = 0.0
    transition_plan: list[str] = field(default_factory=list)
    transition_implementation_plan: list[str] = field(default_factory=list)
    transition_duration_sec: float = 0.0
    normalization_profile: dict[str, Any] = field(default_factory=dict)
    final_duration_sec: float = 0.0
    concat_state: str = "not_ready"
    delivery_state: str = "pending"
    charge_state: str = "pending"
    errors: dict[str, str] = field(default_factory=dict)
    master_video_path: str | None = None
    voice_audio_path: str | None = None
    bgm_audio_path: str | None = None
    sfx_audio_paths: list[str] = field(default_factory=list)
    subtitle_path: str | None = None
    logo_path: str | None = None
    watermark_text: str = ""
    watermark_position: str = "bottom_right"
    text_overlays: list[dict[str, Any]] = field(default_factory=list)
    addon_application: dict[str, Any] = field(default_factory=dict)
    composition_signature: str = ""
    final_video_path: str | None = None
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


def _safe_name(value: str, fallback: str = "job") -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("._")
    return safe[:120] or fallback


def _temp_root() -> str:
    return os.path.abspath(os.getenv("MULTISCENE_VIDEO_TEMP_ROOT") or DEFAULT_TEMP_ROOT)


def _ensure_inside(root: str, path: str) -> str:
    root_abs = os.path.abspath(root)
    path_abs = os.path.abspath(path)
    if path_abs != root_abs and not path_abs.startswith(root_abs + os.sep):
        raise ValueError("unsafe_multiscene_path")
    return path_abs


def _ffmpeg_path() -> str:
    configured = str(os.getenv("FFMPEG_PATH") or "").strip()
    if configured and os.path.isfile(configured):
        return configured
    return shutil.which("ffmpeg") or ""


def _ffprobe_path(ffmpeg_path: str = "") -> str:
    ffmpeg = Path(ffmpeg_path or _ffmpeg_path())
    probe_name = "ffprobe.exe" if ffmpeg.suffix.lower() == ".exe" else "ffprobe"
    sibling = ffmpeg.with_name(probe_name)
    if sibling.exists():
        return str(sibling)
    return shutil.which("ffprobe") or ""


def safe_run_ffmpeg(cmd: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    if not cmd or "ffmpeg" not in os.path.basename(str(cmd[0])).lower():
        raise ValueError("ffmpeg_command_required")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def ensure_video_output(path: str) -> str:
    target = os.path.abspath(str(path or ""))
    if not os.path.isfile(target) or os.path.getsize(target) <= 0:
        raise RuntimeError("video_output_empty")
    return target


def probe_duration(path: str) -> float:
    source = ensure_video_output(path)
    ffprobe = _ffprobe_path()
    if not ffprobe:
        raise RuntimeError("ffprobe_missing")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            source,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("ffprobe_failed")
    try:
        return max(0.0, float((result.stdout or "").strip()))
    except ValueError as exc:
        raise RuntimeError("ffprobe_duration_invalid") from exc


def probe_media_streams(path: str) -> dict[str, Any]:
    source = ensure_video_output(path)
    ffprobe = _ffprobe_path()
    if not ffprobe:
        raise RuntimeError("ffprobe_missing")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            (
                "format=duration:"
                "stream=index,codec_type,codec_name,width,height,pix_fmt,"
                "sample_aspect_ratio,r_frame_rate,time_base,sample_rate,channels,channel_layout:"
                "stream_side_data=rotation"
            ),
            "-of",
            "json",
            source,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("ffprobe_failed")
    try:
        payload = json.loads(result.stdout or "{}")
    except (TypeError, ValueError) as exc:
        raise RuntimeError("ffprobe_json_invalid") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("ffprobe_json_invalid")
    return payload


def _stream_rotation(stream: dict[str, Any]) -> int:
    rotations = [
        int(item.get("rotation") or 0)
        for item in list(stream.get("side_data_list") or [])
        if isinstance(item, dict)
    ]
    return rotations[-1] % 360 if rotations else 0


def _display_geometry(path: str) -> tuple[int, int]:
    payload = probe_media_streams(path)
    video = next(
        (
            item
            for item in list(payload.get("streams") or [])
            if isinstance(item, dict) and item.get("codec_type") == "video"
        ),
        {},
    )
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    if width <= 0 or height <= 0:
        raise RuntimeError("scene_video_geometry_invalid")
    if _stream_rotation(video) in {90, 270}:
        width, height = height, width
    return width - (width % 2), height - (height % 2)


def _has_audio_stream(path: str) -> bool:
    return any(
        isinstance(item, dict) and item.get("codec_type") == "audio"
        for item in list(probe_media_streams(path).get("streams") or [])
    )


def _transition_key(value: Any) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", str(value or "cut").strip().lower()).strip("_")
    return token or "cut"


def _transition_effect(value: Any) -> str:
    token = _transition_key(value)
    if token in _SEMANTIC_CUT_TRANSITIONS:
        return "cut"
    if token == "before_after_morph":
        return "dissolve"
    effect = _XFADE_TRANSITIONS.get(token)
    if not effect:
        raise ValueError(f"unsupported_multiscene_transition:{token}")
    return effect


def _transition_plan(
    transition: str | list[str] | tuple[str, ...] | None,
    boundary_count: int,
) -> tuple[list[str], list[str]]:
    if boundary_count <= 0:
        return [], []
    if isinstance(transition, (list, tuple)):
        requested = [_transition_key(item) for item in transition]
        if len(requested) != boundary_count:
            raise ValueError("multiscene_transition_count_invalid")
    else:
        requested = [_transition_key(transition)] * boundary_count
    return requested, [_transition_effect(item) for item in requested]


def _transition_overlap_seconds(
    effect: str,
    requested_seconds: float,
    left_duration: float,
    right_duration: float,
    fps: int,
) -> float:
    if effect == "cut":
        return 0.0
    maximum = max(1.0 / max(1, fps), min(left_duration, right_duration) / 2.0)
    return min(max(1.0 / max(1, fps), requested_seconds), maximum)


MAX_MULTISCENE_SCENES = 20


def plan_multiscene_video(
    user_prompt: str,
    *,
    max_scenes: int = 3,
    default_scene_duration: float = 6.0,
    aspect_ratio: str = "9:16",
    style: str | None = None,
    llm_func: Callable[..., Any] | None = None,
) -> list[SceneSpec]:
    count = max(1, min(MAX_MULTISCENE_SCENES, int(max_scenes or 3)))
    duration = max(1.0, min(8.0, float(default_scene_duration or 6.0)))
    prompt = re.sub(r"\s+", " ", str(user_prompt or "").strip())
    if not prompt:
        prompt = "Short TOAN AAS multi-scene video"
    if llm_func:
        payload = llm_func(prompt, max_scenes=count, default_scene_duration=duration, aspect_ratio=aspect_ratio, style=style)
        if inspect.isawaitable(payload):
            raise TypeError("llm_func must be synchronous in blackbox module")
        raw_scenes = payload.get("scenes") if isinstance(payload, dict) else payload
        scenes: list[SceneSpec] = []
        for index, raw in enumerate(list(raw_scenes or [])[:count], start=1):
            item = dict(raw or {})
            scenes.append(SceneSpec(
                scene_id=int(item.get("scene_id") or index),
                title=str(item.get("title") or f"Scene {index}"),
                visual_prompt=str(item.get("visual_prompt") or item.get("prompt") or prompt),
                video_prompt=str(item.get("video_prompt") or item.get("prompt") or prompt),
                narration_text=item.get("narration_text"),
                target_duration_sec=float(item.get("target_duration_sec") or duration),
                aspect_ratio=str(item.get("aspect_ratio") or aspect_ratio or "9:16"),
                transition=item.get("transition"),
                seed_image_path=item.get("seed_image_path"),
                provider_params=dict(item.get("provider_params") or {}),
            ))
        if scenes:
            return scenes

    parts = [part.strip() for part in re.split(r"(?:\n+|(?<=[.!?。！？])\s+)", prompt) if part.strip()]
    if not parts:
        parts = [prompt]
    while len(parts) < count:
        parts.append(prompt)
    scenes = []
    for index, part in enumerate(parts[:count], start=1):
        title = f"Scene {index}"
        video_prompt = " ".join(filter(None, [style or "", f"{title}: {part}", f"aspect {aspect_ratio}", f"{duration:.1f}s"]))
        scenes.append(SceneSpec(
            scene_id=index,
            title=title,
            visual_prompt=part,
            video_prompt=video_prompt,
            narration_text=part,
            target_duration_sec=duration,
            aspect_ratio=aspect_ratio,
            transition=None if index == count else "cut",
            provider_params={"fallback_planner": True},
        ))
    return scenes


def create_multiscene_workspace(job_id: str) -> str:
    root = _temp_root()
    os.makedirs(root, exist_ok=True)
    workspace = os.path.join(root, _safe_name(job_id, "job"))
    workspace = _ensure_inside(root, workspace)
    os.makedirs(workspace, exist_ok=True)
    return workspace


def _write_manifest(manifest: MultisceneManifest) -> str:
    manifest.updated_at = time.time()
    path = os.path.join(manifest.workspace_dir, "manifest.json")
    os.makedirs(manifest.workspace_dir, exist_ok=True)
    temporary_path = os.path.join(
        manifest.workspace_dir,
        f".manifest.{os.getpid()}.{time.time_ns()}.tmp",
    )
    with open(temporary_path, "w", encoding="utf-8") as handle:
        json.dump(asdict(manifest), handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary_path, path)
    return path


def load_multiscene_manifest(
    workspace_dir: str,
    *,
    job_id: str = "",
    user_id: str = "",
) -> MultisceneManifest:
    """Load a resumable manifest without trusting paths stored outside its workspace."""
    workspace = os.path.abspath(workspace_dir)
    os.makedirs(workspace, exist_ok=True)
    path = os.path.join(workspace, "manifest.json")
    payload: dict[str, Any] = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                payload = loaded
        except (OSError, ValueError, TypeError):
            payload = {}
    allowed = {item.name for item in fields(MultisceneManifest)}
    values = {key: value for key, value in payload.items() if key in allowed}
    values["job_id"] = str(job_id or values.get("job_id") or "")
    values["user_id"] = str(user_id or values.get("user_id") or "")
    values["workspace_dir"] = workspace
    return MultisceneManifest(**values)


def _scene_index_from_record(record: dict[str, Any], default: int = 0) -> int:
    try:
        return max(0, int(record.get("scene_index") or record.get("scene_id") or default))
    except (TypeError, ValueError):
        return max(0, int(default or 0))


def _task_ids_from_record(record: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in (
        "active_task_id",
        "provider_task_id",
        "task_id",
        "provider_video_id",
        "video_id",
        "winning_task_id",
        "scene_winner_task",
        "canonical_task_selected",
    ):
        values.append(record.get(key))
    for key in ("provider_task_ids", "provider_video_ids"):
        if isinstance(record.get(key), list):
            values.extend(record.get(key) or [])
    task_ids: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in task_ids:
            task_ids.append(text)
    return task_ids


def sync_multiscene_manifest(
    manifest: MultisceneManifest,
    *,
    scene_specs: list[dict[str, Any]] | None = None,
    scene_tasks: list[dict[str, Any]] | None = None,
    scene_clip_paths: dict[int, str] | None = None,
    status: str | None = None,
) -> str:
    """Merge durable scene/task truth into the canonical B13 manifest."""
    if scene_specs is not None:
        manifest.scene_specs = [dict(item or {}) for item in scene_specs if isinstance(item, dict)]
        indexes = [_scene_index_from_record(item, index) for index, item in enumerate(manifest.scene_specs, start=1)]
        manifest.required_scene_indexes = [index for index in indexes if index > 0]
        manifest.scene_order = list(manifest.required_scene_indexes)
        manifest.expected_duration_sec = sum(
            max(0.0, float(item.get("target_duration_sec") or 0.0))
            for item in manifest.scene_specs
        )
    for record in list(scene_tasks or []):
        if not isinstance(record, dict):
            continue
        index = _scene_index_from_record(record)
        if index <= 0:
            continue
        key = str(index)
        task_ids = _task_ids_from_record(record)
        if task_ids:
            current = list(manifest.task_ids_by_scene.get(key) or [])
            manifest.task_ids_by_scene[key] = current + [item for item in task_ids if item not in current]
        attempted = bool(
            record.get("dispatch_attempted")
            or record.get("scene_dispatch_attempted")
            or record.get("provider_submit_called")
        )
        manifest.dispatch_attempts_by_scene[key] = max(
            int(manifest.dispatch_attempts_by_scene.get(key) or 0),
            int(record.get("dispatch_attempts") or record.get("attempt_count") or (1 if attempted else 0)),
        )
        provider_status = str(
            record.get("provider_status_raw")
            or record.get("normalized_provider_status")
            or record.get("provider_status")
            or record.get("status")
            or ""
        ).strip()
        if provider_status:
            manifest.provider_status_by_scene[key] = provider_status
        manifest.retry_count_by_scene[key] = max(
            int(manifest.retry_count_by_scene.get(key) or 0),
            int(record.get("retry_count") or record.get("fallback_count") or record.get("provider_fallback_count") or 0),
        )
        winner = str(
            record.get("winning_task_id")
            or record.get("scene_winner_task")
            or record.get("canonical_task_selected")
            or ""
        ).strip()
        if winner:
            manifest.winner_task_by_scene[key] = winner
        raw_path = str(
            record.get("clip_path")
            or record.get("output_path")
            or record.get("local_path")
            or record.get("raw_provider_video_path")
            or ""
        ).strip()
        if raw_path and os.path.isfile(raw_path) and os.path.getsize(raw_path) > 0:
            manifest.raw_clip_paths_by_scene[key] = os.path.abspath(raw_path)
        error = str(record.get("error") or record.get("provider_error") or record.get("blocker") or "").strip()
        if error and provider_status.lower() not in {"success", "completed", "done", "scene_clip_validated", "clip_downloaded"}:
            manifest.errors[key] = error[:500]
    for index, path in dict(scene_clip_paths or {}).items():
        key = str(int(index))
        clip_path = str(path or "").strip()
        if clip_path and os.path.isfile(clip_path) and os.path.getsize(clip_path) > 0:
            manifest.raw_clip_paths_by_scene[key] = os.path.abspath(clip_path)
            manifest.provider_status_by_scene[key] = "scene_clip_validated"
            manifest.errors.pop(key, None)
    if status:
        manifest.status = str(status)
    return _write_manifest(manifest)


def multiscene_manifest_scene_tasks(manifest: MultisceneManifest) -> list[dict[str, Any]]:
    """Return restart-safe scene records that can be merged into the current R18 ledger."""
    indexes = manifest.required_scene_indexes or sorted(
        {int(key) for key in manifest.task_ids_by_scene if str(key).isdigit()}
        | {int(key) for key in manifest.raw_clip_paths_by_scene if str(key).isdigit()}
    )
    records: list[dict[str, Any]] = []
    for index in indexes:
        key = str(index)
        task_ids = list(manifest.task_ids_by_scene.get(key) or [])
        winner_task = str(manifest.winner_task_by_scene.get(key) or "")
        active_task = winner_task or (task_ids[-1] if task_ids else "")
        raw_path = str(manifest.raw_clip_paths_by_scene.get(key) or "")
        clip_valid = False
        if raw_path and os.path.isfile(raw_path) and os.path.getsize(raw_path) > 0:
            try:
                clip_valid = probe_duration(raw_path) > 0.0
            except (OSError, RuntimeError, ValueError):
                clip_valid = False
        records.append(
            {
                "scene_index": index,
                "scene_id": index,
                "provider_task_id": active_task,
                "task_id": active_task,
                "provider_task_ids": task_ids,
                "status": "scene_clip_validated" if clip_valid else str(manifest.provider_status_by_scene.get(key) or "pending_submit"),
                "provider_status": str(manifest.provider_status_by_scene.get(key) or ""),
                "dispatch_attempts": int(manifest.dispatch_attempts_by_scene.get(key) or 0),
                "dispatch_attempted": bool(manifest.dispatch_attempts_by_scene.get(key) or task_ids),
                "clip_path": raw_path if clip_valid else "",
                "output_path": raw_path if clip_valid else "",
                "clip_valid": clip_valid,
                "validation_passed": clip_valid,
                "retry_count": int(manifest.retry_count_by_scene.get(key) or 0),
                "scene_winner_task": winner_task,
                "source_of_truth": "canonical_multiscene_manifest",
            }
        )
    return records


def _coerce_render_output(result: Any, raw_path: str) -> str:
    if isinstance(result, (bytes, bytearray)):
        with open(raw_path, "wb") as handle:
            handle.write(bytes(result))
        return ensure_video_output(raw_path)
    if isinstance(result, dict):
        if result.get("ok") is False:
            raise RuntimeError(str(result.get("error") or result.get("status") or "scene_render_failed"))
        source = str(result.get("output_path") or result.get("video_path") or result.get("raw_video_path") or "").strip()
    else:
        source = str(result or "").strip()
    if not source:
        source = raw_path
    source = ensure_video_output(source)
    if os.path.abspath(source) != os.path.abspath(raw_path):
        shutil.copyfile(source, raw_path)
    return ensure_video_output(raw_path)


def render_scene(
    scene: SceneSpec,
    *,
    workspace_dir: str,
    render_video_func,
    retry: int = 1,
) -> SceneRenderResult:
    workspace = _ensure_inside(os.path.abspath(workspace_dir), workspace_dir)
    raw_path = os.path.join(workspace, f"scene_{scene.scene_id:03d}_raw.mp4")
    attempts = max(1, int(retry or 0) + 1)
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            result = render_video_func(scene, raw_path)
            if inspect.isawaitable(result):
                raise TypeError("render_video_func must be synchronous in blackbox module")
            output = _coerce_render_output(result, raw_path)
            return SceneRenderResult(
                scene_id=scene.scene_id,
                ok=True,
                raw_video_path=output,
                duration_sec=probe_duration(output),
                retry_count=attempt - 1,
                error=None,
            )
        except Exception as exc:
            last_error = str(exc)[:240] or type(exc).__name__
            if attempt >= attempts:
                break
    return SceneRenderResult(scene_id=scene.scene_id, ok=False, retry_count=attempts - 1, error=last_error or "scene_render_failed")


def normalize_scene_duration(
    input_video_path: str,
    output_video_path: str,
    target_duration_sec: float,
    *,
    allow_slowdown: bool = True,
    allow_speedup: bool = True,
    target_width: int | None = None,
    target_height: int | None = None,
    target_fps: int = DEFAULT_NORMALIZED_FPS,
    preserve_audio: bool = False,
    audio_sample_rate: int = DEFAULT_AUDIO_SAMPLE_RATE,
    audio_channels: int = DEFAULT_AUDIO_CHANNELS,
) -> str:
    del allow_speedup
    source = ensure_video_output(input_video_path)
    target = max(1.0, float(target_duration_sec or 6.0))
    output = os.path.abspath(output_video_path)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("ffmpeg_missing")
    duration = probe_duration(source)
    width = int(target_width or 0)
    height = int(target_height or 0)
    if bool(width) != bool(height):
        raise ValueError("normalized_geometry_incomplete")
    if width <= 0 or height <= 0:
        width, height = _display_geometry(source)
    width -= width % 2
    height -= height % 2
    fps = max(1, min(120, int(target_fps or DEFAULT_NORMALIZED_FPS)))
    sample_rate = max(8_000, min(192_000, int(audio_sample_rate or DEFAULT_AUDIO_SAMPLE_RATE)))
    channels = max(1, min(8, int(audio_channels or DEFAULT_AUDIO_CHANNELS)))
    if width <= 0 or height <= 0:
        raise ValueError("normalized_geometry_invalid")
    if preserve_audio and not _has_audio_stream(source):
        raise RuntimeError("scene_audio_missing")
    pad = max(0.0, target - duration)
    video_filters: list[str] = []
    slowdown_ratio = duration / target if target > 0 else 1.0
    slowdown_min_ratio = max(0.5, min(0.99, float(os.getenv("MULTISCENE_SLOWDOWN_MIN_RATIO") or 0.85)))
    audio_tempo = 1.0
    if pad > 0.05 and allow_slowdown and slowdown_ratio >= slowdown_min_ratio:
        video_filters.append(f"setpts={target / max(duration, 0.001):.8f}*PTS")
        audio_tempo = slowdown_ratio
    elif pad > 0.05:
        video_filters.append(f"tpad=stop_mode=clone:stop_duration={pad:.3f}")
    video_filters.extend(
        [
            f"scale={width}:{height}:force_original_aspect_ratio=decrease",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
            "setsar=1",
            f"fps={fps}",
            f"settb=1/{DEFAULT_VIDEO_TRACK_TIMESCALE}",
            "setpts=PTS-STARTPTS",
            "format=yuv420p",
        ]
    )
    cmd = [ffmpeg, "-y", "-i", source]
    if preserve_audio:
        audio_filters: list[str] = []
        if abs(audio_tempo - 1.0) > 0.0001:
            audio_filters.append(f"atempo={audio_tempo:.8f}")
        audio_filters.extend(
            [
                f"aresample={sample_rate}:async=1:first_pts=0",
                f"aformat=sample_rates={sample_rate}:channel_layouts={'mono' if channels == 1 else 'stereo' if channels == 2 else f'{channels}c'}",
                "apad",
                f"atrim=duration={target:.3f}",
                "asetpts=PTS-STARTPTS",
            ]
        )
        cmd.extend(
            [
                "-filter_complex",
                f"[0:v:0]{','.join(video_filters)}[vout];[0:a:0]{','.join(audio_filters)}[aout]",
                "-map",
                "[vout]",
                "-map",
                "[aout]",
            ]
        )
    else:
        cmd.extend(["-map", "0:v:0", "-vf", ",".join(video_filters), "-an"])
    cmd.extend(
        [
            "-t",
            f"{target:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
        ]
    )
    if preserve_audio:
        cmd.extend(["-c:a", "aac", "-ar", str(sample_rate), "-ac", str(channels)])
    cmd.extend(
        [
            "-map_metadata",
            "-1",
            "-metadata:s:v:0",
            "rotate=0",
            "-video_track_timescale",
            str(DEFAULT_VIDEO_TRACK_TIMESCALE),
            "-movflags",
            "+faststart",
            output,
        ]
    )
    result = safe_run_ffmpeg(cmd, timeout=max(60, int(target * 20)))
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg_normalize_failed:{(result.stderr or '')[-300:]}")
    return ensure_video_output(output)


def stitch_scenes(
    scene_video_paths: list[str],
    output_path: str,
    *,
    transition: str | list[str] | tuple[str, ...] | None = None,
    transition_duration_sec: float = 0.35,
    include_audio: bool = False,
) -> str:
    if not scene_video_paths:
        raise ValueError("scene_video_paths_required")
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("ffmpeg_missing")
    for path in scene_video_paths:
        ensure_video_output(path)
    output = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    requested_plan, implementation_plan = _transition_plan(
        transition,
        max(0, len(scene_video_paths) - 1),
    )
    del requested_plan
    if not include_audio and all(item == "cut" for item in implementation_plan):
        list_path = os.path.join(os.path.dirname(output), "concat_scenes.txt")
        with open(list_path, "w", encoding="utf-8") as handle:
            for path in scene_video_paths:
                normalized = os.path.abspath(path).replace("\\", "/").replace("'", "'\\''")
                handle.write(f"file '{normalized}'\n")
        cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", "-movflags", "+faststart", output]
        result = safe_run_ffmpeg(cmd, timeout=max(120, len(scene_video_paths) * 60))
        if result.returncode != 0:
            raise RuntimeError("ffmpeg_stitch_failed")
        return ensure_video_output(output)

    durations = [probe_duration(path) for path in scene_video_paths]
    if include_audio and any(not _has_audio_stream(path) for path in scene_video_paths):
        raise RuntimeError("normalized_scene_audio_missing")
    cmd = [ffmpeg, "-y"]
    for path in scene_video_paths:
        cmd.extend(["-i", ensure_video_output(path)])
    filters: list[str] = []
    for index in range(len(scene_video_paths)):
        filters.append(
            f"[{index}:v:0]settb=1/{DEFAULT_VIDEO_TRACK_TIMESCALE},setpts=PTS-STARTPTS[v{index}]"
        )
        if include_audio:
            filters.append(
                f"[{index}:a:0]aresample={DEFAULT_AUDIO_SAMPLE_RATE}:async=1:first_pts=0,"
                "aformat=sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS"
                f"[a{index}]"
            )
    previous_video = "[v0]"
    previous_audio = "[a0]"
    cumulative_duration = durations[0]
    requested_overlap = max(0.0, float(transition_duration_sec or 0.0))
    for index, effect in enumerate(implementation_plan, start=1):
        next_video = f"[v{index}]"
        output_video = f"[vx{index}]"
        if effect == "cut":
            filters.append(
                f"{previous_video}{next_video}concat=n=2:v=1:a=0{output_video}"
            )
            if include_audio:
                output_audio = f"[ax{index}]"
                filters.append(
                    f"{previous_audio}[a{index}]concat=n=2:v=0:a=1{output_audio}"
                )
                previous_audio = output_audio
            cumulative_duration += durations[index]
        else:
            overlap = _transition_overlap_seconds(
                effect,
                requested_overlap,
                cumulative_duration,
                durations[index],
                DEFAULT_NORMALIZED_FPS,
            )
            offset = max(0.0, cumulative_duration - overlap)
            filters.append(
                f"{previous_video}{next_video}xfade=transition={effect}:"
                f"duration={overlap:.6f}:offset={offset:.6f}{output_video}"
            )
            if include_audio:
                output_audio = f"[ax{index}]"
                filters.append(
                    f"{previous_audio}[a{index}]acrossfade=d={overlap:.6f}:c1=tri:c2=tri{output_audio}"
                )
                previous_audio = output_audio
            cumulative_duration += durations[index] - overlap
        previous_video = output_video
    cmd.extend(["-filter_complex", ";".join(filters), "-map", previous_video])
    if include_audio:
        cmd.extend(["-map", previous_audio, "-c:a", "aac", "-ar", "48000", "-ac", "2"])
    else:
        cmd.append("-an")
    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-video_track_timescale",
            str(DEFAULT_VIDEO_TRACK_TIMESCALE),
            "-movflags",
            "+faststart",
            output,
        ]
    )
    result = safe_run_ffmpeg(cmd, timeout=max(120, len(scene_video_paths) * 60))
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg_stitch_failed:{(result.stderr or '')[-300:]}")
    return ensure_video_output(output)


def _srt_time(seconds: float) -> str:
    ms_total = max(0, int(round(float(seconds) * 1000)))
    hours, rem = divmod(ms_total, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _drawtext_escape(text: str) -> str:
    # Single definition lives in services/ffmpeg_text: a quote cannot be
    # escaped inside a quoted filtergraph value, so it has to be replaced.
    # `%` is handled by passing expansion=none to drawtext instead.
    return ffmpeg_text.escape_filter_text(re.sub(r"\s+", " ", str(text or "").strip())[:120])


def _drawtext_font_path() -> str:
    candidates = (
        os.getenv("LOCAL_FFMPEG_FONT_PATH", ""),
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\segoeui.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    )
    for candidate in candidates:
        selected = str(candidate or "").strip()
        if selected and os.path.isfile(selected):
            return os.path.abspath(selected)
    return ""


def _drawtext_expr(position: str) -> tuple[str, str]:
    key = str(position or "bottom_right").lower().replace("-", "_")
    if key == "top_left":
        return "24", "24"
    if key == "top_center":
        return "(w-text_w)/2", "24"
    if key == "top_right":
        return "w-text_w-24", "24"
    if key == "center_left":
        return "24", "(h-text_h)/2"
    if key == "center":
        return "(w-text_w)/2", "(h-text_h)/2"
    if key == "center_right":
        return "w-text_w-24", "(h-text_h)/2"
    if key == "bottom_left":
        return "24", "h-text_h-24"
    if key == "bottom_center":
        return "(w-text_w)/2", "h-text_h-24"
    return "w-text_w-24", "h-text_h-24"


def _clamped_percent(value: Any, default: int) -> int:
    try:
        selected = int(value)
    except (TypeError, ValueError):
        selected = int(default)
    return max(0, min(200, selected))


def _file_signature(path: str | None) -> dict[str, Any]:
    selected = str(path or "").strip()
    if not selected:
        return {}
    absolute = os.path.abspath(selected)
    try:
        stat = os.stat(absolute)
    except OSError:
        return {"missing": True}
    digest = hashlib.sha256()
    try:
        with open(absolute, "rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        return {"missing": True}
    return {"size": int(stat.st_size), "sha256": digest.hexdigest()}


def _scene_windows(
    scene_durations: list[float],
    transition_overlaps: list[float],
) -> dict[int, tuple[float, float]]:
    windows: dict[int, tuple[float, float]] = {}
    cursor = 0.0
    for index, duration in enumerate(scene_durations, start=1):
        selected_duration = max(0.0, float(duration or 0.0))
        windows[index] = (cursor, cursor + selected_duration)
        overlap = (
            max(0.0, float(transition_overlaps[index - 1] or 0.0))
            if index - 1 < len(transition_overlaps)
            else 0.0
        )
        cursor += max(0.0, selected_duration - overlap)
    return windows


def _overlay_window(
    overlay: dict[str, Any],
    scene_windows: dict[int, tuple[float, float]],
) -> tuple[float, float] | None:
    scope = str(overlay.get("scene_scope") or "").strip().lower()
    if scope.isdigit() and int(scope) in scene_windows:
        start, end = scene_windows[int(scope)]
    elif "start_seconds" in overlay:
        try:
            start = max(0.0, float(overlay.get("start_seconds") or 0.0))
        except (TypeError, ValueError):
            start = 0.0
        end = float("inf")
    else:
        return None
    try:
        duration = float(overlay.get("duration_seconds") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration > 0.0:
        end = min(end, start + duration)
    if end == float("inf") or end <= start:
        return None
    return start, end


def _composition_signature(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_composed_video(path: str, *, require_audio: bool) -> dict[str, Any]:
    selected = ensure_video_output(path)
    streams = probe_media_streams(selected)
    stream_rows = [item for item in list(streams.get("streams") or []) if isinstance(item, dict)]
    video_streams = [item for item in stream_rows if item.get("codec_type") == "video"]
    audio_streams = [item for item in stream_rows if item.get("codec_type") == "audio"]
    if not video_streams:
        raise RuntimeError("final_video_stream_missing")
    if require_audio and not audio_streams:
        raise RuntimeError("final_audio_stream_missing")
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("ffmpeg_missing")
    decoded = safe_run_ffmpeg(
        [ffmpeg, "-v", "error", "-i", selected, "-f", "null", "-"],
        timeout=300,
    )
    if decoded.returncode != 0:
        raise RuntimeError(f"final_full_decode_failed:{(decoded.stderr or '')[-300:]}")
    return {
        "container_probe": True,
        "full_decode": True,
        "video_stream_count": len(video_streams),
        "audio_stream_count": len(audio_streams),
        "bytes": int(os.path.getsize(selected)),
        "streams": stream_rows,
    }


def build_scene_subtitle(scenes: list[SceneSpec], durations: list[float], output_srt_path: str) -> str:
    output = os.path.abspath(output_srt_path)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    cursor = 0.0
    blocks: list[str] = []
    for index, scene in enumerate(scenes, start=1):
        duration = max(0.5, float(durations[index - 1] if index - 1 < len(durations) else scene.target_duration_sec))
        start = cursor
        end = cursor + duration
        text = scene.narration_text or scene.title or scene.video_prompt
        blocks.append(f"{index}\n{_srt_time(start)} --> {_srt_time(end)}\n{text.strip()}\n")
        cursor = end
    with open(output, "w", encoding="utf-8") as handle:
        handle.write("\n".join(blocks).strip() + "\n")
    return output


def create_master_voice_audio(
    scenes: list[SceneSpec],
    *,
    workspace_dir: str,
    tts_func=None,
    default_silence: bool = True,
) -> str | None:
    narrations = [scene.narration_text for scene in scenes if str(scene.narration_text or "").strip()]
    if not narrations:
        return None
    workspace = os.path.abspath(workspace_dir)
    if tts_func:
        pieces: list[str] = []
        for scene in scenes:
            if not str(scene.narration_text or "").strip():
                continue
            out_path = os.path.join(workspace, f"voice_scene_{scene.scene_id:03d}.mp3")
            result = tts_func(scene.narration_text, out_path, scene)
            if inspect.isawaitable(result):
                raise TypeError("tts_func must be synchronous in blackbox module")
            if isinstance(result, (bytes, bytearray)):
                with open(out_path, "wb") as handle:
                    handle.write(bytes(result))
                pieces.append(ensure_video_output(out_path))
            else:
                pieces.append(ensure_video_output(str(result or out_path)))
        if not pieces:
            return None
        if len(pieces) == 1:
            master = os.path.join(workspace, "master_voice.mp3")
            shutil.copyfile(pieces[0], master)
            return ensure_video_output(master)
        ffmpeg = _ffmpeg_path()
        if not ffmpeg:
            return None
        concat_path = os.path.join(workspace, "voice_concat.txt")
        with open(concat_path, "w", encoding="utf-8") as handle:
            for path in pieces:
                handle.write(f"file '{os.path.abspath(path).replace(chr(92), '/')}'\n")
        master = os.path.join(workspace, "master_voice.mp3")
        result = safe_run_ffmpeg([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat_path, "-c", "copy", master])
        return ensure_video_output(master) if result.returncode == 0 else None
    if not default_silence:
        return None
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        return None
    total = sum(max(0.5, float(scene.target_duration_sec or 6.0)) for scene in scenes)
    master = os.path.join(workspace, "master_voice.mp3")
    result = safe_run_ffmpeg([
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t",
        f"{total:.3f}",
        "-q:a",
        "9",
        "-acodec",
        "libmp3lame",
        master,
    ])
    return ensure_video_output(master) if result.returncode == 0 else None


def mux_final_multiscene_video(
    *,
    master_video_path: str,
    output_path: str,
    voice_audio_path: str | None = None,
    bgm_audio_path: str | None = None,
    sfx_audio_paths: list[str] | None = None,
    sfx_assets: list[dict[str, Any]] | None = None,
    subtitle_path: str | None = None,
    logo_path: str | None = None,
    logo_text: str | None = None,
    watermark_text: str | None = None,
    burn_subtitles: bool = True,
    logo_position: str = "top-right",
    watermark_position: str | None = None,
    watermark_opacity_percent: int = 45,
    text_overlays: list[dict[str, Any]] | None = None,
    scene_windows: dict[int, tuple[float, float]] | None = None,
    voice_volume_percent: int = 100,
    music_volume_percent: int = 20,
    sfx_volume_percent: int = 35,
    preserve_master_audio: bool = False,
    audio_sample_rate: int = DEFAULT_AUDIO_SAMPLE_RATE,
    audio_channels: int = DEFAULT_AUDIO_CHANNELS,
) -> str:
    master = ensure_video_output(master_video_path)
    output = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("ffmpeg_missing")
    filters: list[str] = []
    cmd = [ffmpeg, "-y", "-i", master]
    next_input_index = 1
    voice_input_index = None
    if voice_audio_path:
        cmd += ["-i", ensure_video_output(voice_audio_path)]
        voice_input_index = next_input_index
        next_input_index += 1
    bgm_input_index = None
    if bgm_audio_path:
        cmd += ["-i", ensure_video_output(bgm_audio_path)]
        bgm_input_index = next_input_index
        next_input_index += 1
    sfx_input_indexes: list[int] = []
    selected_sfx_paths = list(sfx_audio_paths or [])
    for sfx_path in selected_sfx_paths:
        cmd += ["-i", ensure_video_output(sfx_path)]
        sfx_input_indexes.append(next_input_index)
        next_input_index += 1
    logo_input_index = None
    if logo_path:
        logo_input_index = next_input_index
        cmd += ["-loop", "1", "-i", ensure_video_output(logo_path)]
        next_input_index += 1
    video_map = "0:v:0"
    if subtitle_path and burn_subtitles:
        # Was the only site that escaped the backslash and colon but left the
        # quote alone, so a path containing one could close the value.
        sub = ffmpeg_text.escape_filter_path(ensure_video_output(subtitle_path))
        filters.append(f"[{video_map}]subtitles='{sub}'[vsub]")
        video_map = "vsub"
    clean_watermark_text = _drawtext_escape(watermark_text or logo_text or "")
    selected_text_overlays = [
        dict(item) for item in list(text_overlays or []) if isinstance(item, dict)
    ]
    drawtext_font = ""
    if clean_watermark_text or any(_drawtext_escape(str(item.get("text") or "")) for item in selected_text_overlays):
        drawtext_font_path = _drawtext_font_path()
        if not drawtext_font_path:
            raise RuntimeError("drawtext_font_missing")
        drawtext_font = f"fontfile='{ffmpeg_text.escape_filter_path(drawtext_font_path)}':"
    if clean_watermark_text:
        x_expr, y_expr = _drawtext_expr(watermark_position or logo_position)
        input_label = f"[{video_map}]"
        watermark_alpha = max(0.0, min(1.0, int(watermark_opacity_percent or 0) / 100.0))
        filters.append(
            f"{input_label}drawtext={drawtext_font}text='{clean_watermark_text}':{ffmpeg_text.DRAWTEXT_NO_EXPANSION}:"
            f"fontcolor=white@{watermark_alpha:.3f}:"
            f"fontsize=36:borderw=2:bordercolor=black@0.65:"
            f"box=1:boxcolor=black@0.25:boxborderw=10:x={x_expr}:y={y_expr}[vtxt]"
        )
        video_map = "vtxt"
    selected_scene_windows = dict(scene_windows or {})
    for index, overlay in enumerate(
        selected_text_overlays,
        start=1,
    ):
        clean_text = _drawtext_escape(str(overlay.get("text") or ""))
        if not clean_text:
            continue
        x_expr, y_expr = _drawtext_expr(str(overlay.get("position") or "center"))
        try:
            font_size = max(14, min(96, int(overlay.get("font_size") or 32)))
        except (TypeError, ValueError):
            font_size = 32
        try:
            opacity = max(0.0, min(1.0, int(overlay.get("opacity_percent") or 100) / 100.0))
        except (TypeError, ValueError):
            opacity = 1.0
        enable = ""
        time_window = _overlay_window(overlay, selected_scene_windows)
        if time_window:
            enable = f":enable='between(t,{time_window[0]:.6f},{time_window[1]:.6f})'"
        output_label = f"vtext{index}"
        filters.append(
            f"[{video_map}]drawtext={drawtext_font}text='{clean_text}':{ffmpeg_text.DRAWTEXT_NO_EXPANSION}:"
            f"fontcolor=white@{opacity:.3f}:fontsize={font_size}:borderw=2:"
            f"bordercolor=black@0.75:box=1:boxcolor=black@0.30:boxborderw=8:"
            f"x={x_expr}:y={y_expr}{enable}[{output_label}]"
        )
        video_map = output_label
    if logo_input_index is not None:
        position = str(logo_position or "bottom_right").strip().lower().replace("-", "_")
        if position in {"top_left", "center_left", "bottom_left"}:
            logo_x = "main_w*0.04"
        elif position in {"top_center", "center", "bottom_center"}:
            logo_x = "(main_w-overlay_w)/2"
        else:
            logo_x = "main_w-overlay_w-main_w*0.04"
        if position in {"top_left", "top_center", "top_right"}:
            logo_y = "main_h*0.035"
        elif position in {"center_left", "center", "center_right"}:
            logo_y = "(main_h-overlay_h)/2"
        else:
            logo_y = "main_h-overlay_h-main_h*0.035"
        input_label = f"[{video_map}]"
        filters.append(
            f"[{logo_input_index}:v]{input_label}scale2ref=w='min(main_w*0.18,main_w*0.12)':h=-1[logo][base];"
            f"[base][logo]overlay=x={logo_x}:y={logo_y}:format=auto:shortest=1[vlogo]"
        )
        video_map = "vlogo"
    selected_sample_rate = max(
        8_000,
        min(192_000, int(audio_sample_rate or DEFAULT_AUDIO_SAMPLE_RATE)),
    )
    selected_channels = max(1, min(8, int(audio_channels or DEFAULT_AUDIO_CHANNELS)))
    audio_labels: list[str] = []
    if preserve_master_audio:
        filters.append("[0:a:0]volume=1.0[amaster]")
        audio_labels.append("[amaster]")
    if voice_input_index is not None:
        voice_volume = _clamped_percent(voice_volume_percent, 100) / 100.0
        filters.append(f"[{voice_input_index}:a:0]volume={voice_volume:.4f}[avoice]")
        audio_labels.append("[avoice]")
    if bgm_input_index is not None:
        music_volume = _clamped_percent(music_volume_percent, 20) / 100.0
        filters.append(f"[{bgm_input_index}:a:0]volume={music_volume:.4f}[abgm]")
        audio_labels.append("[abgm]")
    selected_sfx_assets = [
        dict(item) if isinstance(item, dict) else {}
        for item in list(sfx_assets or [])
    ]
    sfx_volume = _clamped_percent(sfx_volume_percent, 35) / 100.0
    for index, input_index in enumerate(sfx_input_indexes):
        asset = selected_sfx_assets[index] if index < len(selected_sfx_assets) else {}
        try:
            delay_ms = max(0, int(round(float(asset.get("start_seconds") or 0.0) * 1000.0)))
        except (TypeError, ValueError):
            delay_ms = 0
        output_label = f"asfx{index}"
        filters.append(
            f"[{input_index}:a:0]volume={sfx_volume:.4f},"
            f"adelay={delay_ms}:all=1[{output_label}]"
        )
        audio_labels.append(f"[{output_label}]")
    if len(audio_labels) > 1:
        filters.append(
            "".join(audio_labels)
            + f"amix=inputs={len(audio_labels)}:duration=longest:dropout_transition=2,"
            + f"aresample={selected_sample_rate}:async=1:first_pts=0,apad[aout]"
        )
        audio_map = "[aout]"
    elif audio_labels:
        filters.append(
            audio_labels[0]
            + f"aresample={selected_sample_rate}:async=1:first_pts=0,apad[aout]"
        )
        audio_map = "[aout]"
    else:
        audio_map = ""
    if filters:
        cmd += ["-filter_complex", ";".join(filters), "-map", f"[{video_map}]" if video_map.startswith("v") else video_map]
    else:
        cmd += ["-map", video_map]
    if audio_map:
        cmd += [
            "-map",
            audio_map,
            "-shortest",
            "-c:a",
            "aac",
            "-ar",
            str(selected_sample_rate),
            "-ac",
            str(selected_channels),
        ]
    else:
        cmd += (["-shortest"] if logo_input_index is not None else []) + ["-an"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", output]
    result = safe_run_ffmpeg(cmd, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg_mux_failed:{(result.stderr or result.stdout or '')[-500:]}")
    return ensure_video_output(output)


def _upsert_scene_result(manifest: MultisceneManifest, result: SceneRenderResult) -> None:
    payload = asdict(result)
    for index, existing in enumerate(manifest.scene_results):
        if _scene_index_from_record(existing) == int(result.scene_id):
            manifest.scene_results[index] = {**dict(existing or {}), **payload}
            return
    manifest.scene_results.append(payload)


def finalize_multiscene_scene_clips(
    *,
    user_id: str,
    job_id: str,
    workspace_dir: str,
    scenes: list[SceneSpec],
    scene_clip_paths: dict[int, str],
    manifest: MultisceneManifest | None = None,
    tts_func=None,
    voice_audio_path: str | None = None,
    voice_volume_percent: int = 100,
    bgm_audio_path: str | None = None,
    music_volume_percent: int = 20,
    sfx_audio_paths: list[str] | None = None,
    sfx_assets: list[dict[str, Any]] | None = None,
    sfx_volume_percent: int = 35,
    subtitle_path: str | None = None,
    logo_path: str | None = None,
    enable_voice: bool = False,
    enable_subtitle: bool = True,
    enable_logo: bool = False,
    logo_text: str | None = None,
    logo_position: str = "bottom_right",
    watermark_text: str | None = None,
    watermark_position: str | None = None,
    watermark_opacity_percent: int = 45,
    text_overlays: list[dict[str, Any]] | None = None,
    transition_plan: list[str] | tuple[str, ...] | None = None,
    requested_addons: list[str] | tuple[str, ...] | None = None,
    final_duration_tolerance_sec: float | None = None,
    output_width: int | None = None,
    output_height: int | None = None,
    output_fps: int = DEFAULT_NORMALIZED_FPS,
    transition_duration_sec: float = 0.35,
    preserve_scene_audio: bool = False,
    audio_sample_rate: int = DEFAULT_AUDIO_SAMPLE_RATE,
    audio_channels: int = DEFAULT_AUDIO_CHANNELS,
) -> dict[str, Any]:
    """Canonical B13 finalizer for fully downloaded Product Video scene clips."""
    workspace = os.path.abspath(workspace_dir)
    os.makedirs(workspace, exist_ok=True)
    active_manifest = manifest or load_multiscene_manifest(workspace, job_id=str(job_id), user_id=str(user_id))
    active_manifest.job_id = str(job_id)
    active_manifest.user_id = str(user_id)
    active_manifest.workspace_dir = workspace
    ordered_scenes = sorted(list(scenes or []), key=lambda item: int(item.scene_id))
    required_indexes = [int(scene.scene_id) for scene in ordered_scenes]
    requested_addon_names = list(
        dict.fromkeys(
            _transition_key(item)
            for item in list(requested_addons or [])
            if str(item or "").strip()
        )
    )
    selected_sfx_paths = [str(item or "").strip() for item in list(sfx_audio_paths or []) if str(item or "").strip()]
    selected_sfx_assets = [dict(item) for item in list(sfx_assets or []) if isinstance(item, dict)]
    selected_text_overlays = [
        dict(item)
        for item in list(text_overlays or [])
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    selected_subtitle_path = str(subtitle_path or "").strip()
    selected_voice_path = str(voice_audio_path or "").strip()
    selected_music_path = str(bgm_audio_path or "").strip()
    selected_logo_path = str(logo_path or "").strip()
    selected_watermark_text = str(watermark_text or logo_text or "").strip()
    scene_durations = [
        max(1.0, float(scene.target_duration_sec or 0.0))
        for scene in ordered_scenes
    ]
    selected_transition_source: str | list[str] | tuple[str, ...] | None = [
        scene.transition or "cut" for scene in ordered_scenes[:-1]
    ]
    if transition_plan:
        selected_transition_source = transition_plan
    requested_transition_plan, implementation_transition_plan = _transition_plan(
        selected_transition_source,
        max(0, len(ordered_scenes) - 1),
    )
    missing_addons: list[str] = []

    def _material_file_present(path: str) -> bool:
        try:
            return bool(path and os.path.isfile(path) and os.path.getsize(path) > 0)
        except OSError:
            return False

    for addon_name in requested_addon_names:
        if addon_name == "subtitle" and not _material_file_present(selected_subtitle_path):
            missing_addons.append(addon_name)
        elif addon_name == "dubbing" and not _material_file_present(selected_voice_path):
            missing_addons.append(addon_name)
        elif addon_name == "music" and not _material_file_present(selected_music_path):
            missing_addons.append(addon_name)
        elif addon_name == "sfx" and (
            not selected_sfx_paths
            or any(not _material_file_present(path) for path in selected_sfx_paths)
        ):
            missing_addons.append(addon_name)
        elif addon_name == "logo" and (
            not enable_logo or not _material_file_present(selected_logo_path)
        ):
            missing_addons.append(addon_name)
        elif addon_name == "watermark" and not selected_watermark_text:
            missing_addons.append(addon_name)
        elif addon_name == "text" and not selected_text_overlays:
            missing_addons.append(addon_name)
        elif addon_name == "transitions" and len(ordered_scenes) > 1 and (
            not transition_plan
            or len(list(transition_plan)) != len(ordered_scenes) - 1
        ):
            missing_addons.append(addon_name)
        elif addon_name not in {
            "subtitle",
            "dubbing",
            "music",
            "sfx",
            "logo",
            "watermark",
            "text",
            "transitions",
        }:
            missing_addons.append(addon_name)
    if missing_addons:
        active_manifest.status = "addon_material_blocked"
        active_manifest.concat_state = "not_ready"
        active_manifest.addon_application = {
            "requested": requested_addon_names,
            "applied": [],
            "missing": list(dict.fromkeys(missing_addons)),
        }
        active_manifest.errors["addons"] = f"addon_material_missing:{missing_addons[0]}"
        manifest_path = _write_manifest(active_manifest)
        return {
            "ok": False,
            "status": "addon_material_blocked",
            "continue_polling": False,
            "concat_attempted": False,
            "concat_ready": False,
            "manifest_path": manifest_path,
            "addon_application": dict(active_manifest.addon_application),
            "error": f"addon_material_missing:{missing_addons[0]}",
        }
    selected_fps = max(1, min(120, int(output_fps or DEFAULT_NORMALIZED_FPS)))
    selected_transition_duration = max(0.0, float(transition_duration_sec or 0.0))
    transition_overlaps = [
        _transition_overlap_seconds(
            effect,
            selected_transition_duration,
            scene_durations[index],
            scene_durations[index + 1],
            selected_fps,
        )
        for index, effect in enumerate(implementation_transition_plan)
    ]
    selected_scene_windows = _scene_windows(scene_durations, transition_overlaps)
    target_duration = sum(scene_durations) - sum(transition_overlaps)
    active_manifest.scene_specs = [asdict(scene) for scene in ordered_scenes]
    active_manifest.required_scene_indexes = required_indexes
    active_manifest.scene_order = required_indexes
    active_manifest.expected_duration_sec = target_duration
    missing = []
    for index in required_indexes:
        candidate = str(scene_clip_paths.get(index) or "").strip()
        try:
            valid = bool(candidate and os.path.isfile(candidate) and os.path.getsize(candidate) > 0)
        except OSError:
            valid = False
        if not valid:
            missing.append(index)
    if not required_indexes or missing:
        active_manifest.concat_state = "waiting_for_full_coverage"
        active_manifest.status = "waiting_for_scene_clips"
        for index in missing:
            active_manifest.errors[str(index)] = "scene_clip_missing"
        manifest_path = _write_manifest(active_manifest)
        return {
            "ok": False,
            "status": "waiting_for_scene_clips",
            "continue_polling": True,
            "concat_attempted": False,
            "concat_ready": False,
            "scene_coverage_count": len(required_indexes) - len(missing),
            "scene_coverage_expected": len(required_indexes),
            "missing_scene_indexes": missing,
            "manifest_path": manifest_path,
            "error": "full_scene_coverage_required",
        }

    requested_width = int(output_width or 0)
    requested_height = int(output_height or 0)
    if bool(requested_width) != bool(requested_height):
        raise ValueError("normalized_geometry_incomplete")
    if requested_width <= 0 or requested_height <= 0:
        requested_width, requested_height = _display_geometry(
            str(scene_clip_paths[required_indexes[0]])
        )
    requested_width -= requested_width % 2
    requested_height -= requested_height % 2
    normalization_profile = {
        "width": requested_width,
        "height": requested_height,
        "fps": selected_fps,
        "pixel_format": "yuv420p",
        "sample_aspect_ratio": "1:1",
        "video_time_base": f"1/{DEFAULT_VIDEO_TRACK_TIMESCALE}",
    }
    previous_profile = dict(active_manifest.normalization_profile or {})
    previous_transition_plan = list(active_manifest.transition_plan or [])
    previous_transition_duration = float(active_manifest.transition_duration_sec or 0.0)
    previous_composition_signature = str(active_manifest.composition_signature or "")
    active_manifest.normalization_profile = dict(normalization_profile)
    active_manifest.transition_plan = list(requested_transition_plan)
    active_manifest.transition_implementation_plan = list(
        implementation_transition_plan
    )
    active_manifest.transition_duration_sec = selected_transition_duration
    active_manifest.voice_audio_path = os.path.abspath(selected_voice_path) if selected_voice_path else None
    active_manifest.bgm_audio_path = os.path.abspath(selected_music_path) if selected_music_path else None
    active_manifest.sfx_audio_paths = [os.path.abspath(path) for path in selected_sfx_paths]
    active_manifest.subtitle_path = os.path.abspath(selected_subtitle_path) if selected_subtitle_path else None
    active_manifest.logo_path = os.path.abspath(selected_logo_path) if selected_logo_path else None
    active_manifest.watermark_text = selected_watermark_text
    active_manifest.watermark_position = str(watermark_position or logo_position or "bottom_right")
    active_manifest.text_overlays = [dict(item) for item in selected_text_overlays]
    active_manifest.addon_application = {
        "requested": requested_addon_names,
        "applied": [],
        "missing": [],
    }
    composition_contract = {
        "scene_inputs": [
            _file_signature(str(scene_clip_paths.get(index) or ""))
            for index in required_indexes
        ],
        "normalization_profile": normalization_profile,
        "transition_plan": requested_transition_plan,
        "transition_implementation_plan": implementation_transition_plan,
        "transition_duration_sec": selected_transition_duration,
        "requested_addons": requested_addon_names,
        "enable_voice": bool(enable_voice),
        "enable_subtitle": bool(enable_subtitle),
        "enable_logo": bool(enable_logo),
        "voice": _file_signature(selected_voice_path),
        "voice_volume_percent": _clamped_percent(voice_volume_percent, 100),
        "music": _file_signature(selected_music_path),
        "music_volume_percent": _clamped_percent(music_volume_percent, 20),
        "sfx": [_file_signature(path) for path in selected_sfx_paths],
        "sfx_assets": selected_sfx_assets,
        "sfx_volume_percent": _clamped_percent(sfx_volume_percent, 35),
        "subtitle": _file_signature(selected_subtitle_path),
        "logo": _file_signature(selected_logo_path),
        "logo_position": str(logo_position or "bottom_right"),
        "watermark_text": selected_watermark_text,
        "watermark_position": str(watermark_position or logo_position or "bottom_right"),
        "watermark_opacity_percent": max(0, min(100, int(watermark_opacity_percent or 0))),
        "text_overlays": selected_text_overlays,
        "preserve_scene_audio": bool(preserve_scene_audio),
        "audio_sample_rate": int(audio_sample_rate or DEFAULT_AUDIO_SAMPLE_RATE),
        "audio_channels": int(audio_channels or DEFAULT_AUDIO_CHANNELS),
    }
    current_composition_signature = _composition_signature(composition_contract)
    active_manifest.composition_signature = current_composition_signature
    tolerance = (
        max(0.25, float(final_duration_tolerance_sec))
        if final_duration_tolerance_sec is not None
        else max(1.0, len(ordered_scenes) * 0.2)
    )
    persisted_final = str(active_manifest.final_video_path or "")
    reuse_contract_matches = bool(
        previous_profile == normalization_profile
        and previous_transition_plan == requested_transition_plan
        and abs(previous_transition_duration - selected_transition_duration) <= 0.000001
        and previous_composition_signature == current_composition_signature
    )
    if reuse_contract_matches and persisted_final and os.path.isfile(persisted_final) and os.path.getsize(persisted_final) > 0:
        persisted_duration = 0.0
        persisted_validation: dict[str, Any] | None = None
        try:
            persisted_duration = probe_duration(persisted_final)
            if abs(persisted_duration - target_duration) <= tolerance:
                persisted_validation = _validate_composed_video(
                    persisted_final,
                    require_audio=bool(
                        preserve_scene_audio
                        or selected_voice_path
                        or selected_music_path
                        or selected_sfx_paths
                    ),
                )
        except (OSError, RuntimeError, ValueError):
            persisted_validation = None
        if persisted_validation:
            active_manifest.status = "final_ready"
            active_manifest.concat_state = "completed"
            active_manifest.final_duration_sec = persisted_duration
            active_manifest.addon_application = {
                "requested": requested_addon_names,
                "applied": list(requested_addon_names),
                "missing": [],
            }
            manifest_path = _write_manifest(active_manifest)
            return {
                "ok": True,
                "status": "completed",
                "continue_polling": False,
                "final_video_path": persisted_final,
                "master_video_path": active_manifest.master_video_path,
                "subtitle_path": active_manifest.subtitle_path,
                "manifest_path": manifest_path,
                "scene_count": len(ordered_scenes),
                "scene_order": required_indexes,
                "raw_scene_paths": [str(active_manifest.raw_clip_paths_by_scene.get(str(index)) or "") for index in required_indexes],
                "normalized_scene_paths": [str(active_manifest.normalized_clip_paths_by_scene.get(str(index)) or "") for index in required_indexes],
                "duration_sec": persisted_duration,
                "target_duration_sec": target_duration,
                "transition_plan": list(requested_transition_plan),
                "transition_implementation_plan": list(implementation_transition_plan),
                "transition_duration_seconds": selected_transition_duration,
                "normalization_profile": dict(normalization_profile),
                "final_duration_tolerance_sec": tolerance,
                "scene_coverage_count": len(required_indexes),
                "scene_coverage_expected": len(required_indexes),
                "scene_coverage_valid_bool": True,
                "missing_scene_indexes": [],
                "concat_attempted": False,
                "concat_ready": True,
                "concat_output_valid": True,
                "final_mp4_valid": True,
                "final_reused_from_manifest": True,
                "artifact_validation": persisted_validation,
                "addon_application": dict(active_manifest.addon_application),
                "composition_signature": current_composition_signature,
                "delivery_state": active_manifest.delivery_state,
                "charge_state": active_manifest.charge_state,
                "error": None,
            }

    normalized_paths: list[str] = []
    raw_paths: list[str] = []
    durations: list[float] = []
    active_manifest.status = "normalizing_scenes"
    active_manifest.concat_state = "normalizing"
    _write_manifest(active_manifest)
    for scene in ordered_scenes:
        index = int(scene.scene_id)
        source = ensure_video_output(str(scene_clip_paths[index]))
        raw_path = os.path.join(workspace, f"scene_{index:03d}_raw.mp4")
        if os.path.abspath(source) != os.path.abspath(raw_path):
            shutil.copyfile(source, raw_path)
        raw_path = ensure_video_output(raw_path)
        normalized_path = os.path.join(workspace, f"scene_{index:03d}_normalized.mp4")
        normalized_path = normalize_scene_duration(
            raw_path,
            normalized_path,
            scene.target_duration_sec,
            target_width=requested_width,
            target_height=requested_height,
            target_fps=selected_fps,
            preserve_audio=preserve_scene_audio,
            audio_sample_rate=audio_sample_rate,
            audio_channels=audio_channels,
        )
        normalized_duration = probe_duration(normalized_path)
        raw_paths.append(raw_path)
        normalized_paths.append(normalized_path)
        durations.append(normalized_duration)
        key = str(index)
        active_manifest.raw_clip_paths_by_scene[key] = raw_path
        active_manifest.normalized_clip_paths_by_scene[key] = normalized_path
        active_manifest.provider_status_by_scene[key] = "scene_clip_validated"
        active_manifest.errors.pop(key, None)
        task_ids = list(active_manifest.task_ids_by_scene.get(key) or [])
        _upsert_scene_result(
            active_manifest,
            SceneRenderResult(
                scene_id=index,
                ok=True,
                raw_video_path=raw_path,
                normalized_video_path=normalized_path,
                duration_sec=normalized_duration,
                retry_count=int(active_manifest.retry_count_by_scene.get(key) or 0),
                provider_task_id=task_ids[-1] if task_ids else None,
                provider_status="scene_clip_validated",
                dispatch_attempts=int(active_manifest.dispatch_attempts_by_scene.get(key) or 0),
                winner_task=str(active_manifest.winner_task_by_scene.get(key) or "") or None,
            ),
        )
        _write_manifest(active_manifest)

    active_manifest.status = "concatenating"
    active_manifest.concat_state = "running"
    _write_manifest(active_manifest)
    master = stitch_scenes(
        normalized_paths,
        os.path.join(workspace, "master_video_only.mp4"),
        transition=requested_transition_plan,
        transition_duration_sec=selected_transition_duration,
        include_audio=preserve_scene_audio,
    )
    active_manifest.master_video_path = master
    master_duration = probe_duration(master)
    if abs(master_duration - target_duration) > tolerance:
        active_manifest.status = "error"
        active_manifest.concat_state = "invalid_duration"
        active_manifest.errors["final"] = "final_duration_out_of_tolerance"
        manifest_path = _write_manifest(active_manifest)
        return {
            "ok": False,
            "status": "error",
            "continue_polling": False,
            "concat_attempted": True,
            "concat_output_valid": False,
            "manifest_path": manifest_path,
            "master_video_path": master,
            "duration_sec": master_duration,
            "target_duration_sec": target_duration,
            "error": "final_duration_out_of_tolerance",
        }

    resolved_subtitle_path = None
    if enable_subtitle:
        if selected_subtitle_path:
            resolved_subtitle_path = ensure_video_output(selected_subtitle_path)
        else:
            subtitle_durations = [
                max(0.1, duration - (transition_overlaps[index] if index < len(transition_overlaps) else 0.0))
                for index, duration in enumerate(durations)
            ]
            resolved_subtitle_path = build_scene_subtitle(
                ordered_scenes,
                subtitle_durations,
                os.path.join(workspace, "scene_subtitles.srt"),
            )
        active_manifest.subtitle_path = resolved_subtitle_path
    resolved_voice_path = None
    if enable_voice:
        if selected_voice_path:
            resolved_voice_path = ensure_video_output(selected_voice_path)
        else:
            resolved_voice_path = create_master_voice_audio(
                ordered_scenes,
                workspace_dir=workspace,
                tts_func=tts_func,
                default_silence=True,
            )
        active_manifest.voice_audio_path = resolved_voice_path
    final = mux_final_multiscene_video(
        master_video_path=master,
        output_path=os.path.join(workspace, "final_output.mp4"),
        voice_audio_path=resolved_voice_path,
        voice_volume_percent=voice_volume_percent,
        bgm_audio_path=selected_music_path or None,
        music_volume_percent=music_volume_percent,
        sfx_audio_paths=selected_sfx_paths,
        sfx_assets=selected_sfx_assets,
        sfx_volume_percent=sfx_volume_percent,
        subtitle_path=resolved_subtitle_path,
        logo_path=selected_logo_path if enable_logo else None,
        logo_text=logo_text,
        watermark_text=selected_watermark_text,
        burn_subtitles=bool(enable_subtitle),
        logo_position=logo_position,
        watermark_position=watermark_position,
        watermark_opacity_percent=watermark_opacity_percent,
        text_overlays=selected_text_overlays,
        scene_windows=selected_scene_windows,
        preserve_master_audio=preserve_scene_audio,
        audio_sample_rate=audio_sample_rate,
        audio_channels=audio_channels,
    )
    final_duration = probe_duration(final)
    if abs(final_duration - target_duration) > tolerance:
        active_manifest.status = "error"
        active_manifest.concat_state = "invalid_final_duration"
        active_manifest.errors["final"] = "final_duration_out_of_tolerance"
        manifest_path = _write_manifest(active_manifest)
        return {
            "ok": False,
            "status": "error",
            "continue_polling": False,
            "concat_attempted": True,
            "concat_output_valid": False,
            "manifest_path": manifest_path,
            "final_video_path": final,
            "duration_sec": final_duration,
            "target_duration_sec": target_duration,
            "error": "final_duration_out_of_tolerance",
        }
    artifact_validation = _validate_composed_video(
        final,
        require_audio=bool(
            preserve_scene_audio
            or resolved_voice_path
            or selected_music_path
            or selected_sfx_paths
        ),
    )
    active_manifest.final_video_path = final
    active_manifest.final_duration_sec = final_duration
    active_manifest.status = "final_ready"
    active_manifest.concat_state = "completed"
    active_manifest.delivery_state = "pending"
    active_manifest.charge_state = "pending"
    active_manifest.addon_application = {
        "requested": requested_addon_names,
        "applied": list(requested_addon_names),
        "missing": [],
    }
    active_manifest.errors.pop("final", None)
    manifest_path = _write_manifest(active_manifest)
    return {
        "ok": True,
        "status": "completed",
        "continue_polling": False,
        "final_video_path": final,
        "master_video_path": master,
        "subtitle_path": resolved_subtitle_path,
        "manifest_path": manifest_path,
        "scene_count": len(ordered_scenes),
        "scene_order": required_indexes,
        "raw_scene_paths": raw_paths,
        "normalized_scene_paths": normalized_paths,
        "duration_sec": final_duration,
        "target_duration_sec": target_duration,
        "transition_plan": list(requested_transition_plan),
        "transition_implementation_plan": list(implementation_transition_plan),
        "transition_duration_seconds": selected_transition_duration,
        "normalization_profile": dict(normalization_profile),
        "final_duration_tolerance_sec": tolerance,
        "scene_coverage_count": len(required_indexes),
        "scene_coverage_expected": len(required_indexes),
        "scene_coverage_valid_bool": True,
        "missing_scene_indexes": [],
        "concat_attempted": True,
        "concat_ready": True,
        "concat_output_valid": True,
        "final_mp4_valid": True,
        "artifact_validation": artifact_validation,
        "addon_application": dict(active_manifest.addon_application),
        "composition_signature": current_composition_signature,
        "delivery_state": "pending",
        "charge_state": "pending",
        "error": None,
    }


def process_multiscene_video_pipeline(
    *,
    user_id: str,
    job_id: str,
    user_prompt: str,
    workspace_dir: str,
    render_video_func,
    llm_func=None,
    tts_func=None,
    voice_audio_path: str | None = None,
    voice_volume_percent: int = 100,
    bgm_audio_path: str | None = None,
    music_volume_percent: int = 20,
    sfx_audio_paths: list[str] | None = None,
    sfx_assets: list[dict[str, Any]] | None = None,
    sfx_volume_percent: int = 35,
    subtitle_path: str | None = None,
    logo_path: str | None = None,
    max_scenes: int = 3,
    default_scene_duration: float = 6.0,
    aspect_ratio: str = "9:16",
    enable_voice: bool = False,
    enable_subtitle: bool = True,
    enable_logo: bool = False,
    logo_text: str | None = None,
    logo_position: str = "bottom_right",
    watermark_text: str | None = None,
    watermark_position: str | None = None,
    watermark_opacity_percent: int = 45,
    text_overlays: list[dict[str, Any]] | None = None,
    transition_plan: list[str] | tuple[str, ...] | None = None,
    requested_addons: list[str] | tuple[str, ...] | None = None,
    output_width: int | None = None,
    output_height: int | None = None,
) -> dict[str, Any]:
    workspace = os.path.abspath(workspace_dir)
    os.makedirs(workspace, exist_ok=True)
    manifest = MultisceneManifest(job_id=str(job_id), user_id=str(user_id), workspace_dir=workspace, status="planning")
    created_files: list[str] = []
    try:
        scenes = plan_multiscene_video(user_prompt, max_scenes=max_scenes, default_scene_duration=default_scene_duration, aspect_ratio=aspect_ratio, llm_func=llm_func)
        manifest.scene_specs = [asdict(scene) for scene in scenes]
        manifest.required_scene_indexes = [int(scene.scene_id) for scene in scenes]
        manifest.scene_order = list(manifest.required_scene_indexes)
        manifest.expected_duration_sec = sum(float(scene.target_duration_sec or 0.0) for scene in scenes)
        _write_manifest(manifest)
        raw_paths: dict[int, str] = {}
        failed: list[int] = []
        for scene in scenes:
            manifest.status = f"rendering_scene_{scene.scene_id}"
            _write_manifest(manifest)
            retry_count = 0 if dict(scene.provider_params or {}).get("real_provider") else 1
            rendered = render_scene(scene, workspace_dir=workspace, render_video_func=render_video_func, retry=retry_count)
            if not rendered.ok or not rendered.raw_video_path:
                failed.append(scene.scene_id)
                _upsert_scene_result(manifest, rendered)
                manifest.errors[str(scene.scene_id)] = str(rendered.error or "scene_render_failed")
                _write_manifest(manifest)
                break
            created_files.append(rendered.raw_video_path)
            raw_paths[int(scene.scene_id)] = rendered.raw_video_path
            manifest.raw_clip_paths_by_scene[str(scene.scene_id)] = rendered.raw_video_path
            manifest.provider_status_by_scene[str(scene.scene_id)] = "scene_clip_validated"
            manifest.retry_count_by_scene[str(scene.scene_id)] = int(rendered.retry_count or 0)
            _upsert_scene_result(manifest, rendered)
            _write_manifest(manifest)
        if failed:
            failed_error = ""
            for item in reversed(manifest.scene_results):
                failed_error = str(item.get("error") or "")
                if failed_error:
                    break
            manifest.status = "error"
            _write_manifest(manifest)
            return {
                "ok": False,
                "status": "error",
                "final_video_path": None,
                "master_video_path": None,
                "subtitle_path": None,
                "manifest_path": os.path.join(workspace, "manifest.json"),
                "scene_count": len(scenes),
                "duration_sec": 0.0,
                "failed_scenes": failed,
                "created_files": created_files,
                "error": failed_error or "scene_render_failed",
            }
        result = finalize_multiscene_scene_clips(
            user_id=str(user_id),
            job_id=str(job_id),
            workspace_dir=workspace,
            scenes=scenes,
            scene_clip_paths=raw_paths,
            manifest=manifest,
            tts_func=tts_func,
            voice_audio_path=voice_audio_path,
            voice_volume_percent=voice_volume_percent,
            bgm_audio_path=bgm_audio_path,
            music_volume_percent=music_volume_percent,
            sfx_audio_paths=sfx_audio_paths,
            sfx_assets=sfx_assets,
            sfx_volume_percent=sfx_volume_percent,
            subtitle_path=subtitle_path,
            logo_path=logo_path,
            enable_voice=enable_voice,
            enable_subtitle=enable_subtitle,
            enable_logo=enable_logo,
            logo_text=logo_text,
            logo_position=logo_position,
            watermark_text=watermark_text,
            watermark_position=watermark_position,
            watermark_opacity_percent=watermark_opacity_percent,
            text_overlays=text_overlays,
            transition_plan=transition_plan,
            requested_addons=requested_addons,
            output_width=output_width,
            output_height=output_height,
        )
        created_files.extend(
            str(path)
            for path in (
                list(result.get("normalized_scene_paths") or [])
                + [result.get("master_video_path"), result.get("subtitle_path"), result.get("final_video_path")]
            )
            if path
        )
        return {
            **result,
            "failed_scenes": [],
            "created_files": list(dict.fromkeys(created_files)),
        }
    except Exception as exc:
        manifest.status = "error"
        manifest_path = _write_manifest(manifest)
        return {
            "ok": False,
            "status": "error",
            "final_video_path": None,
            "master_video_path": manifest.master_video_path,
            "subtitle_path": manifest.subtitle_path,
            "manifest_path": manifest_path,
            "scene_count": len(manifest.scene_specs),
            "duration_sec": 0.0,
            "failed_scenes": [],
            "created_files": created_files,
            "error": type(exc).__name__,
        }


def cleanup_multiscene_workspace(workspace_dir: str) -> None:
    root = _temp_root()
    path = _ensure_inside(root, workspace_dir)
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
