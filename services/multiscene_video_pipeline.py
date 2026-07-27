"""Telegram-free blackbox pipeline for short multi-scene videos.

This module has no billing, Telegram, or provider credentials. Callers own
confirmation, queueing, provider selection, and final delivery.
"""

from __future__ import annotations

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
    final_duration_sec: float = 0.0
    concat_state: str = "not_ready"
    delivery_state: str = "pending"
    charge_state: str = "pending"
    errors: dict[str, str] = field(default_factory=dict)
    master_video_path: str | None = None
    voice_audio_path: str | None = None
    bgm_audio_path: str | None = None
    subtitle_path: str | None = None
    logo_path: str | None = None
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
    pad = max(0.0, target - duration)
    vf = "fps=30,format=yuv420p"
    slowdown_ratio = duration / target if target > 0 else 1.0
    slowdown_min_ratio = max(0.5, min(0.99, float(os.getenv("MULTISCENE_SLOWDOWN_MIN_RATIO") or 0.85)))
    if pad > 0.05 and allow_slowdown and slowdown_ratio >= slowdown_min_ratio:
        vf = f"setpts={target / max(duration, 0.001):.8f}*PTS,fps=30,format=yuv420p"
    elif pad > 0.05:
        vf = f"{vf},tpad=stop_mode=clone:stop_duration={pad:.3f}"
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        source,
        "-map",
        "0:v:0",
        "-vf",
        vf,
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
        "-an",
        "-movflags",
        "+faststart",
        output,
    ]
    result = safe_run_ffmpeg(cmd, timeout=max(60, int(target * 20)))
    if result.returncode != 0:
        raise RuntimeError("ffmpeg_normalize_failed")
    return ensure_video_output(output)


def stitch_scenes(scene_video_paths: list[str], output_path: str, *, transition: str | None = None) -> str:
    del transition
    if not scene_video_paths:
        raise ValueError("scene_video_paths_required")
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("ffmpeg_missing")
    for path in scene_video_paths:
        ensure_video_output(path)
    output = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output), exist_ok=True)
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


def _drawtext_expr(position: str) -> tuple[str, str]:
    key = str(position or "bottom_right").lower().replace("-", "_")
    if key == "top_left":
        return "24", "24"
    if key == "top_center":
        return "(w-text_w)/2", "24"
    if key == "top_right":
        return "w-text_w-24", "24"
    if key == "bottom_left":
        return "24", "h-text_h-24"
    if key == "bottom_center":
        return "(w-text_w)/2", "h-text_h-24"
    return "w-text_w-24", "h-text_h-24"


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
    subtitle_path: str | None = None,
    logo_path: str | None = None,
    logo_text: str | None = None,
    burn_subtitles: bool = True,
    logo_position: str = "top-right",
) -> str:
    master = ensure_video_output(master_video_path)
    output = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("ffmpeg_missing")
    filters: list[str] = []
    cmd = [ffmpeg, "-y", "-i", master]
    audio_inputs = []
    if voice_audio_path:
        cmd += ["-i", ensure_video_output(voice_audio_path)]
        audio_inputs.append("voice")
    if bgm_audio_path:
        cmd += ["-i", ensure_video_output(bgm_audio_path)]
        audio_inputs.append("bgm")
    logo_input_index = None
    if logo_path:
        logo_input_index = 1 + len(audio_inputs)
        cmd += ["-loop", "1", "-i", ensure_video_output(logo_path)]
    video_map = "0:v:0"
    if subtitle_path and burn_subtitles:
        # Was the only site that escaped the backslash and colon but left the
        # quote alone, so a path containing one could close the value.
        sub = ffmpeg_text.escape_filter_path(subtitle_path)
        filters.append(f"[{video_map}]subtitles='{sub}'[vsub]")
        video_map = "vsub"
    clean_logo_text = _drawtext_escape(logo_text or "")
    if clean_logo_text:
        x_expr, y_expr = _drawtext_expr(logo_position)
        input_label = f"[{video_map}]"
        filters.append(
            f"{input_label}drawtext=text='{clean_logo_text}':{ffmpeg_text.DRAWTEXT_NO_EXPANSION}:fontcolor=white:"
            f"fontsize=36:borderw=2:bordercolor=black@0.65:"
            f"box=1:boxcolor=black@0.25:boxborderw=10:x={x_expr}:y={y_expr}[vtxt]"
        )
        video_map = "vtxt"
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
    if voice_audio_path and bgm_audio_path:
        filters.append("[1:a]volume=1.0[a1];[2:a]volume=0.10[a2];[a1][a2]amix=inputs=2:duration=first:dropout_transition=2[aout]")
        audio_map = "[aout]"
    elif voice_audio_path:
        audio_map = "1:a:0"
    elif bgm_audio_path:
        audio_map = "1:a:0"
    else:
        audio_map = ""
    if filters:
        cmd += ["-filter_complex", ";".join(filters), "-map", f"[{video_map}]" if video_map.startswith("v") else video_map]
    else:
        cmd += ["-map", video_map]
    if audio_map:
        cmd += ["-map", audio_map, "-shortest", "-c:a", "aac", "-ar", "44100", "-ac", "2"]
    else:
        cmd += (["-shortest"] if logo_input_index is not None else []) + ["-an"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", output]
    result = safe_run_ffmpeg(cmd, timeout=300)
    if result.returncode != 0:
        if output != master:
            shutil.copyfile(master, output)
        return ensure_video_output(output)
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
    bgm_audio_path: str | None = None,
    logo_path: str | None = None,
    enable_voice: bool = False,
    enable_subtitle: bool = True,
    enable_logo: bool = False,
    logo_text: str | None = None,
    logo_position: str = "bottom_right",
    final_duration_tolerance_sec: float | None = None,
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
    active_manifest.scene_specs = [asdict(scene) for scene in ordered_scenes]
    active_manifest.required_scene_indexes = required_indexes
    active_manifest.scene_order = required_indexes
    active_manifest.expected_duration_sec = sum(max(1.0, float(scene.target_duration_sec or 0.0)) for scene in ordered_scenes)
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

    target_duration = active_manifest.expected_duration_sec
    tolerance = (
        max(0.25, float(final_duration_tolerance_sec))
        if final_duration_tolerance_sec is not None
        else max(1.0, len(ordered_scenes) * 0.2)
    )
    persisted_final = str(active_manifest.final_video_path or "")
    if persisted_final and os.path.isfile(persisted_final) and os.path.getsize(persisted_final) > 0:
        persisted_duration = probe_duration(persisted_final)
        if abs(persisted_duration - target_duration) <= tolerance:
            active_manifest.status = "final_ready"
            active_manifest.concat_state = "completed"
            active_manifest.final_duration_sec = persisted_duration
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
        normalized_path = normalize_scene_duration(raw_path, normalized_path, scene.target_duration_sec)
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
    master = stitch_scenes(normalized_paths, os.path.join(workspace, "master_video_only.mp4"))
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

    subtitle_path = None
    if enable_subtitle:
        subtitle_path = build_scene_subtitle(ordered_scenes, durations, os.path.join(workspace, "scene_subtitles.srt"))
        active_manifest.subtitle_path = subtitle_path
    voice_path = None
    if enable_voice:
        voice_path = create_master_voice_audio(
            ordered_scenes,
            workspace_dir=workspace,
            tts_func=tts_func,
            default_silence=True,
        )
        active_manifest.voice_audio_path = voice_path
    final = mux_final_multiscene_video(
        master_video_path=master,
        output_path=os.path.join(workspace, "final_output.mp4"),
        voice_audio_path=voice_path,
        bgm_audio_path=bgm_audio_path,
        subtitle_path=subtitle_path,
        logo_path=logo_path if enable_logo else None,
        logo_text=logo_text if enable_logo else None,
        burn_subtitles=bool(enable_subtitle),
        logo_position=logo_position,
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
    active_manifest.final_video_path = final
    active_manifest.final_duration_sec = final_duration
    active_manifest.status = "final_ready"
    active_manifest.concat_state = "completed"
    active_manifest.delivery_state = "pending"
    active_manifest.charge_state = "pending"
    active_manifest.errors.pop("final", None)
    manifest_path = _write_manifest(active_manifest)
    return {
        "ok": True,
        "status": "completed",
        "continue_polling": False,
        "final_video_path": final,
        "master_video_path": master,
        "subtitle_path": subtitle_path,
        "manifest_path": manifest_path,
        "scene_count": len(ordered_scenes),
        "scene_order": required_indexes,
        "raw_scene_paths": raw_paths,
        "normalized_scene_paths": normalized_paths,
        "duration_sec": final_duration,
        "target_duration_sec": target_duration,
        "final_duration_tolerance_sec": tolerance,
        "scene_coverage_count": len(required_indexes),
        "scene_coverage_expected": len(required_indexes),
        "scene_coverage_valid_bool": True,
        "missing_scene_indexes": [],
        "concat_attempted": True,
        "concat_ready": True,
        "concat_output_valid": True,
        "final_mp4_valid": True,
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
    bgm_audio_path: str | None = None,
    logo_path: str | None = None,
    max_scenes: int = 3,
    default_scene_duration: float = 6.0,
    aspect_ratio: str = "9:16",
    enable_voice: bool = False,
    enable_subtitle: bool = True,
    enable_logo: bool = False,
    logo_text: str | None = None,
    logo_position: str = "bottom_right",
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
            bgm_audio_path=bgm_audio_path,
            logo_path=logo_path,
            enable_voice=enable_voice,
            enable_subtitle=enable_subtitle,
            enable_logo=enable_logo,
            logo_text=logo_text,
            logo_position=logo_position,
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
