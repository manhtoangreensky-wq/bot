"""Local FFmpeg postprocess for generated video add-ons.

This module never renders scenes, calls providers, talks to Telegram, or charges
Xu. It starts from an existing final MP4 and returns one validated MP4.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from services import ffmpeg_text


@dataclass
class VideoPostprocessPlan:
    source_video_path: str
    output_video_path: str
    voice_audio_path: str | None = None
    music_audio_path: str | None = None
    subtitle_path: str | None = None
    logo_path: str | None = None
    burn_subtitles: bool = False
    logo_position: str = "bottom_right"
    logo_opacity: float = 0.82
    voice_speed: float = 1.0
    voice_volume: float = 1.0
    music_speed: float = 1.0
    music_volume: float = 0.18
    keep_original_audio: bool = False
    replace_original_audio: bool = True
    target_loudness: float = -16.0
    cleanup_paths: list[str] = field(default_factory=list)


@dataclass
class VideoPostprocessResult:
    ok: bool
    output_video_path: str = ""
    output_bytes: int = 0
    status: str = ""
    detail: str = ""
    provider_called: bool = False
    xu_charged: int = 0
    ffmpeg_cmd: list[str] = field(default_factory=list)


def _ffmpeg_path() -> str:
    configured = str(os.getenv("FFMPEG_PATH") or "").strip()
    if configured and os.path.isfile(configured):
        return configured
    return shutil.which("ffmpeg") or ""


def _ffprobe_path() -> str:
    ffmpeg = Path(_ffmpeg_path() or "ffmpeg")
    sibling = ffmpeg.with_name("ffprobe.exe" if ffmpeg.suffix.lower() == ".exe" else "ffprobe")
    if sibling.exists():
        return str(sibling)
    return shutil.which("ffprobe") or ""


def _run(cmd: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def ensure_mp4(path: str) -> str:
    target = os.path.abspath(str(path or ""))
    if not os.path.isfile(target) or os.path.getsize(target) <= 0:
        raise RuntimeError("postprocess_output_empty")
    return target


def probe_duration(path: str) -> float:
    source = ensure_mp4(path)
    ffprobe = _ffprobe_path()
    if not ffprobe:
        return 0.0
    result = _run([
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        source,
    ], timeout=30)
    if result.returncode != 0:
        return 0.0
    try:
        return max(0.0, float((result.stdout or "").strip()))
    except ValueError:
        return 0.0


def _filter_path(path: str) -> str:
    # Single definition lives in services/ffmpeg_text: a quote cannot be
    # escaped inside a quoted filtergraph value, so it has to be replaced.
    return ffmpeg_text.escape_filter_path(path)


def _overlay_expr(position: str) -> str:
    key = str(position or "bottom_right").lower()
    if key == "top_left":
        return "24:24"
    if key == "top_right":
        return "W-w-24:24"
    if key == "bottom_left":
        return "24:H-h-24"
    if key == "center":
        return "(W-w)/2:(H-h)/2"
    return "W-w-24:H-h-24"


def _safe_speed(value: float | int | str | None) -> float:
    try:
        amount = float(value)
    except Exception:
        return 1.0
    return max(0.1, min(2.0, amount))


def _atempo_chain(speed: float) -> str:
    speed = _safe_speed(speed)
    if abs(speed - 1.0) < 0.001:
        return ""
    factors: list[float] = []
    remaining = speed
    while remaining < 0.5:
        factors.append(0.5)
        remaining = remaining / 0.5
    factors.append(remaining)
    return ",".join(f"atempo={factor:.6g}" for factor in factors)


def _existing_file(path: str | None) -> str:
    if not path:
        return ""
    target = os.path.abspath(str(path))
    return target if os.path.isfile(target) and os.path.getsize(target) > 0 else ""


def _copy_source(plan: VideoPostprocessPlan) -> VideoPostprocessResult:
    source = ensure_mp4(plan.source_video_path)
    output = os.path.abspath(plan.output_video_path)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    if os.path.abspath(source) != output:
        shutil.copyfile(source, output)
    return VideoPostprocessResult(ok=True, output_video_path=ensure_mp4(output), output_bytes=os.path.getsize(output), status="COPIED")


def process_video_postprocess_plan(plan: VideoPostprocessPlan) -> VideoPostprocessResult:
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        return VideoPostprocessResult(ok=False, status="FFMPEG_MISSING", detail="ffmpeg_missing")
    source = _existing_file(plan.source_video_path)
    if not source:
        return VideoPostprocessResult(ok=False, status="SOURCE_VIDEO_MISSING", detail="source_video_missing")
    voice = _existing_file(plan.voice_audio_path)
    music = _existing_file(plan.music_audio_path)
    logo = _existing_file(plan.logo_path)
    subtitle = _existing_file(plan.subtitle_path) if plan.burn_subtitles else ""
    if not any([voice, music, logo, subtitle]):
        return _copy_source(plan)

    source_duration = probe_duration(source)
    voice_speed = _safe_speed(plan.voice_speed)
    music_speed = _safe_speed(plan.music_speed)
    voice_duration = probe_duration(voice) if voice else 0.0
    adjusted_voice_duration = (voice_duration / voice_speed) if voice and voice_speed else voice_duration
    if voice and source_duration and adjusted_voice_duration > source_duration + 0.35:
        return VideoPostprocessResult(
            ok=False,
            status="VOICE_LONGER_THAN_VIDEO",
            detail=f"voice_duration={adjusted_voice_duration:.2f}; video_duration={source_duration:.2f}",
        )

    output = os.path.abspath(plan.output_video_path)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    tmp_output = output + ".tmp.mp4"
    inputs = [ffmpeg, "-y", "-i", source]
    input_index = 1
    voice_idx = music_idx = logo_idx = None
    if voice:
        voice_idx = input_index
        inputs.extend(["-i", voice])
        input_index += 1
    if music:
        music_idx = input_index
        inputs.extend(["-i", music])
        input_index += 1
    if logo:
        logo_idx = input_index
        inputs.extend(["-i", logo])
        input_index += 1

    filters: list[str] = []
    video_label = "[0:v]"
    if subtitle:
        filters.append(f"{video_label}subtitles='{_filter_path(subtitle)}'[vsub]")
        video_label = "[vsub]"
    if logo and logo_idx is not None:
        opacity = max(0.0, min(1.0, float(plan.logo_opacity or 0.0)))
        filters.append(f"[{logo_idx}:v]format=rgba,colorchannelmixer=aa={opacity:.3f}[logo]")
        filters.append(f"{video_label}[logo]overlay={_overlay_expr(plan.logo_position)}[vout]")
        video_label = "[vout]"

    audio_label = ""
    audio_inputs: list[str] = []
    if voice and voice_idx is not None:
        voice_filters = [_atempo_chain(voice_speed), f"volume={max(0.0, float(plan.voice_volume or 0.0)):.3f}"]
        filters.append(f"[{voice_idx}:a]{','.join(item for item in voice_filters if item)}[voice]")
        audio_inputs.append("[voice]")
    if music and music_idx is not None:
        music_filters = [_atempo_chain(music_speed), f"volume={max(0.0, float(plan.music_volume or 0.0)):.3f}"]
        filters.append(f"[{music_idx}:a]{','.join(item for item in music_filters if item)}[music]")
        audio_inputs.append("[music]")
    if len(audio_inputs) == 1:
        audio_label = audio_inputs[0]
    elif len(audio_inputs) > 1:
        joined = "".join(audio_inputs)
        filters.append(f"{joined}amix=inputs={len(audio_inputs)}:duration=first:dropout_transition=1[aout]")
        audio_label = "[aout]"

    cmd = inputs[:]
    if filters:
        cmd.extend(["-filter_complex", ";".join(filters)])
    cmd.extend(["-map", video_label if filters and video_label != "[0:v]" else "0:v:0"])
    if audio_label:
        cmd.extend(["-map", audio_label])
    elif not plan.replace_original_audio:
        cmd.extend(["-map", "0:a?"])
    cmd.extend([
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
    ])
    if audio_label or not plan.replace_original_audio:
        cmd.extend(["-c:a", "aac", "-b:a", "160k"])
    else:
        cmd.append("-an")
    cmd.extend(["-movflags", "+faststart", "-shortest", tmp_output])
    result = _run(cmd, timeout=240)
    if result.returncode != 0:
        return VideoPostprocessResult(ok=False, status="FFMPEG_FAILED", detail=(result.stderr or result.stdout or "")[-800:], ffmpeg_cmd=cmd)
    ensure_mp4(tmp_output)
    if os.path.exists(output):
        os.remove(output)
    os.replace(tmp_output, output)
    try:
        for cleanup_path in plan.cleanup_paths:
            cleanup = os.path.abspath(str(cleanup_path or ""))
            if cleanup and os.path.exists(cleanup) and cleanup.startswith(tempfile.gettempdir()):
                os.remove(cleanup)
    except Exception:
        pass
    return VideoPostprocessResult(
        ok=True,
        output_video_path=ensure_mp4(output),
        output_bytes=os.path.getsize(output),
        status="PASS",
        provider_called=False,
        xu_charged=0,
        ffmpeg_cmd=cmd,
    )
