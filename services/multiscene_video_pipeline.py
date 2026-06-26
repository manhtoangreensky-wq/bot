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
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable


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


@dataclass
class MultisceneManifest:
    job_id: str
    user_id: str
    workspace_dir: str
    scene_specs: list[dict[str, Any]] = field(default_factory=list)
    scene_results: list[dict[str, Any]] = field(default_factory=list)
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


def plan_multiscene_video(
    user_prompt: str,
    *,
    max_scenes: int = 3,
    default_scene_duration: float = 6.0,
    aspect_ratio: str = "9:16",
    style: str | None = None,
    llm_func: Callable[..., Any] | None = None,
) -> list[SceneSpec]:
    count = max(1, min(3, int(max_scenes or 3)))
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
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(asdict(manifest), handle, ensure_ascii=False, indent=2)
    return path


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
            last_error = type(exc).__name__
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
    del allow_slowdown, allow_speedup
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
    if pad > 0.05:
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
    burn_subtitles: bool = True,
    logo_position: str = "top-right",
) -> str:
    del logo_position
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
    if logo_path:
        cmd += ["-i", ensure_video_output(logo_path)]
    video_map = "0:v:0"
    if subtitle_path and burn_subtitles:
        sub = os.path.abspath(subtitle_path).replace("\\", "\\\\").replace(":", "\\:")
        filters.append(f"[{video_map}]subtitles='{sub}'[vsub]")
        video_map = "vsub"
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
        cmd += ["-an"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", output]
    result = safe_run_ffmpeg(cmd, timeout=300)
    if result.returncode != 0:
        if output != master:
            shutil.copyfile(master, output)
        return ensure_video_output(output)
    return ensure_video_output(output)


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
) -> dict[str, Any]:
    workspace = os.path.abspath(workspace_dir)
    os.makedirs(workspace, exist_ok=True)
    manifest = MultisceneManifest(job_id=str(job_id), user_id=str(user_id), workspace_dir=workspace, status="planning")
    created_files: list[str] = []
    try:
        scenes = plan_multiscene_video(user_prompt, max_scenes=max_scenes, default_scene_duration=default_scene_duration, aspect_ratio=aspect_ratio, llm_func=llm_func)
        manifest.scene_specs = [asdict(scene) for scene in scenes]
        _write_manifest(manifest)
        normalized_paths: list[str] = []
        durations: list[float] = []
        failed: list[int] = []
        for scene in scenes:
            manifest.status = f"rendering_scene_{scene.scene_id}"
            _write_manifest(manifest)
            rendered = render_scene(scene, workspace_dir=workspace, render_video_func=render_video_func, retry=1)
            if not rendered.ok or not rendered.raw_video_path:
                failed.append(scene.scene_id)
                manifest.scene_results.append(asdict(rendered))
                _write_manifest(manifest)
                break
            created_files.append(rendered.raw_video_path)
            normalized = os.path.join(workspace, f"scene_{scene.scene_id:03d}_normalized.mp4")
            normalized = normalize_scene_duration(rendered.raw_video_path, normalized, scene.target_duration_sec)
            rendered.normalized_video_path = normalized
            rendered.duration_sec = probe_duration(normalized)
            normalized_paths.append(normalized)
            durations.append(float(rendered.duration_sec or scene.target_duration_sec))
            created_files.append(normalized)
            manifest.scene_results.append(asdict(rendered))
            _write_manifest(manifest)
        if failed:
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
                "duration_sec": sum(durations),
                "failed_scenes": failed,
                "created_files": created_files,
                "error": "scene_render_failed",
            }
        master = stitch_scenes(normalized_paths, os.path.join(workspace, "master_video_only.mp4"))
        created_files.append(master)
        manifest.master_video_path = master
        subtitle_path = None
        if enable_subtitle:
            subtitle_path = build_scene_subtitle(scenes, durations, os.path.join(workspace, "scene_subtitles.srt"))
            created_files.append(subtitle_path)
            manifest.subtitle_path = subtitle_path
        voice_path = None
        if enable_voice:
            voice_path = create_master_voice_audio(scenes, workspace_dir=workspace, tts_func=tts_func, default_silence=True)
            if voice_path:
                created_files.append(voice_path)
                manifest.voice_audio_path = voice_path
        final = mux_final_multiscene_video(
            master_video_path=master,
            output_path=os.path.join(workspace, "final_output.mp4"),
            voice_audio_path=voice_path,
            bgm_audio_path=bgm_audio_path,
            subtitle_path=subtitle_path,
            logo_path=logo_path if enable_logo else None,
            burn_subtitles=bool(enable_subtitle),
        )
        created_files.append(final)
        manifest.final_video_path = final
        manifest.status = "completed"
        manifest_path = _write_manifest(manifest)
        return {
            "ok": True,
            "status": "completed",
            "final_video_path": final,
            "master_video_path": master,
            "subtitle_path": subtitle_path,
            "manifest_path": manifest_path,
            "scene_count": len(scenes),
            "duration_sec": sum(durations),
            "failed_scenes": [],
            "created_files": created_files,
            "error": None,
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
