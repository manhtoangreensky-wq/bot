"""Local-only manual video editing and split execution.

The module builds argument arrays and invokes FFmpeg without a shell.  It has
no provider, Telegram, database, or wallet dependency.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable

from services.video_local_validation import (
    FFMPEG_TIMEOUT_SECONDS,
    LocalVideoValidationError,
    enforce_workspace_limit,
    find_ffmpeg,
    find_ffprobe,
    path_is_within,
    probe_video_file,
    require_path_within,
    validate_mp4_output,
    validate_srt_file,
)
from services.video_smart_splitter import SplitRange, split_output_name, validate_exact_coverage


ASPECT_RATIOS = {"keep", "16:9", "9:16", "1:1", "4:5"}
RESOLUTION_PRESETS = {"keep", "720p", "1080p"}
ROTATIONS = {0, 90, 180, 270}
FLIP_MODES = {"none", "horizontal", "vertical"}
SPEED_PRESETS = {0.5, 0.75, 1.0, 1.25, 1.5, 2.0}
VOLUME_PRESETS = {0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0, 1.5, 2.0}
COLOR_PRESETS = {
    "keep": "",
    "bright_clear": "eq=brightness=0.025:contrast=1.06:saturation=1.06,unsharp=5:5:0.45:5:5:0.0",
    "light_cinematic": "eq=brightness=-0.01:contrast=1.12:saturation=0.93:gamma=0.98",
    "warm": "colorbalance=rs=0.06:gs=0.015:bs=-0.04",
    "cool": "colorbalance=rs=-0.04:gs=0.01:bs=0.06",
    "high_contrast": "eq=contrast=1.25:saturation=1.05",
    "black_white": "hue=s=0,eq=contrast=1.08",
}
TEXT_POSITIONS = {"top", "center", "bottom"}
LOGO_POSITIONS = {"top_left", "top_right", "bottom_left", "bottom_right"}


class LocalVideoEditError(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_text(value: Any, maximum: int = 500) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:maximum]


def default_manual_edit_plan(input_video: str = "") -> dict[str, Any]:
    return {
        "input_video": str(input_video or ""),
        "concat_inputs": [],
        "trim": {"start_ms": 0, "end_ms": 0},
        "crop_or_fit": {"aspect_ratio": "keep", "mode": "fit"},
        "resolution": "keep",
        "rotation": 0,
        "flip": "none",
        "speed": 1.0,
        "volume": 1.0,
        "brightness_percent": 100,
        "text_overlay": {},
        "logo_overlay": {},
        "subtitle_file": "",
        "color_preset": "keep",
        "output_format": "mp4",
    }


def normalize_manual_edit_plan(
    plan: dict[str, Any] | None,
    *,
    source_duration_ms: int,
    workspace: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    source_duration_ms = max(0, int(source_duration_ms or 0))
    if source_duration_ms <= 0:
        raise LocalVideoEditError("source_duration_invalid")
    raw = {**default_manual_edit_plan(), **dict(plan or {})}
    source = str(raw.get("input_video") or "").strip()
    if not source:
        raise LocalVideoEditError("input_video_missing")
    if workspace is not None:
        try:
            require_path_within(source, workspace)
        except LocalVideoValidationError as exc:
            raise LocalVideoEditError(exc.reason) from exc
    concat_inputs = [str(item or "").strip() for item in raw.get("concat_inputs") or [] if str(item or "").strip()]
    if len(concat_inputs) > 9:
        raise LocalVideoEditError("concat_input_limit")
    if workspace is not None:
        for item in concat_inputs:
            try:
                require_path_within(item, workspace)
            except LocalVideoValidationError as exc:
                raise LocalVideoEditError(exc.reason) from exc
    trim = dict(raw.get("trim") or {})
    start_ms = max(0, _integer(trim.get("start_ms"), 0))
    end_ms = _integer(trim.get("end_ms"), 0) or source_duration_ms
    if start_ms >= end_ms or end_ms > source_duration_ms:
        raise LocalVideoEditError("trim_range_invalid")
    crop = dict(raw.get("crop_or_fit") or {})
    aspect = str(crop.get("aspect_ratio") or "keep").strip().lower()
    mode = str(crop.get("mode") or "fit").strip().lower()
    if aspect not in ASPECT_RATIOS:
        raise LocalVideoEditError("aspect_ratio_invalid")
    if mode not in {"crop", "fit"}:
        raise LocalVideoEditError("crop_mode_invalid")
    resolution = str(raw.get("resolution") or "keep").strip().lower()
    if resolution not in RESOLUTION_PRESETS:
        raise LocalVideoEditError("resolution_invalid")
    rotation = _integer(raw.get("rotation"), 0)
    if rotation not in ROTATIONS:
        raise LocalVideoEditError("rotation_invalid")
    flip = str(raw.get("flip") or "none").strip().lower()
    if flip not in FLIP_MODES:
        raise LocalVideoEditError("flip_invalid")
    speed = _number(raw.get("speed"), 1.0)
    if speed not in SPEED_PRESETS:
        raise LocalVideoEditError("speed_invalid")
    volume = _number(raw.get("volume"), 1.0)
    if not 0.0 <= volume <= 2.0:
        raise LocalVideoEditError("volume_invalid")
    brightness_percent = _integer(raw.get("brightness_percent"), 100)
    if not 20 <= brightness_percent <= 200:
        raise LocalVideoEditError("brightness_invalid")
    color = str(raw.get("color_preset") or "keep").strip().lower()
    if color not in COLOR_PRESETS:
        raise LocalVideoEditError("color_preset_invalid")
    text = dict(raw.get("text_overlay") or {})
    if text:
        content = _safe_text(text.get("content"), 260)
        position = str(text.get("position") or "bottom").strip().lower()
        start = max(0, _integer(text.get("start_ms"), 0))
        end = _integer(text.get("end_ms"), 0) or end_ms - start_ms
        font_size = max(16, min(120, _integer(text.get("font_size"), 42)))
        if not content or position not in TEXT_POSITIONS or start >= end:
            raise LocalVideoEditError("text_overlay_invalid")
        text = {
            "content": content,
            "position": position,
            "start_ms": start,
            "end_ms": end,
            "font_size": font_size,
            "outline": max(1, min(6, _integer(text.get("outline"), 2))),
            "font_path": str(text.get("font_path") or "").strip(),
        }
    logo = dict(raw.get("logo_overlay") or {})
    if logo:
        logo_path = str(logo.get("path") or "").strip()
        position = str(logo.get("position") or "top_right").strip().lower()
        scale = _number(logo.get("scale"), 0.12)
        opacity = _number(logo.get("opacity"), 1.0)
        if position not in LOGO_POSITIONS or not 0.02 <= scale <= 0.18 or not 0.1 <= opacity <= 1.0:
            raise LocalVideoEditError("logo_overlay_invalid")
        if workspace is not None:
            try:
                require_path_within(logo_path, workspace)
            except LocalVideoValidationError as exc:
                raise LocalVideoEditError(exc.reason) from exc
        logo = {"path": logo_path, "position": position, "scale": scale, "opacity": opacity}
    subtitle_file = str(raw.get("subtitle_file") or "").strip()
    if subtitle_file:
        validation = validate_srt_file(subtitle_file, workspace=workspace)
        if not validation.get("ok"):
            raise LocalVideoEditError(str(validation.get("reason") or "subtitle_invalid"))
    if str(raw.get("output_format") or "mp4").lower() != "mp4":
        raise LocalVideoEditError("output_format_invalid")
    return {
        "input_video": source,
        "concat_inputs": concat_inputs,
        "trim": {"start_ms": start_ms, "end_ms": end_ms},
        "crop_or_fit": {"aspect_ratio": aspect, "mode": mode},
        "resolution": resolution,
        "rotation": rotation,
        "flip": flip,
        "speed": speed,
        "volume": volume,
        "brightness_percent": brightness_percent,
        "text_overlay": text,
        "logo_overlay": logo,
        "subtitle_file": subtitle_file,
        "color_preset": color,
        "output_format": "mp4",
    }


def expected_manual_duration_ms(plan: dict[str, Any]) -> int:
    trim = dict(plan.get("trim") or {})
    selected = max(0, int(trim.get("end_ms") or 0) - int(trim.get("start_ms") or 0))
    speed = max(0.01, float(plan.get("speed") or 1.0))
    return int(round(selected / speed))


def _target_size(aspect: str, resolution: str, source_width: int, source_height: int) -> tuple[int, int]:
    aspect = aspect if aspect in ASPECT_RATIOS else "keep"
    resolution = resolution if resolution in RESOLUTION_PRESETS else "keep"
    if aspect == "keep":
        if resolution == "keep":
            source_width = max(2, int(source_width or 2))
            source_height = max(2, int(source_height or 2))
            scale = min(1.0, 1920 / source_width, 1920 / source_height)
            width = max(2, int(source_width * scale) // 2 * 2)
            height = max(2, int(source_height * scale) // 2 * 2)
            return width, height
        landscape = source_width >= source_height
        if resolution == "720p":
            return (1280, 720) if landscape else (720, 1280)
        return (1920, 1080) if landscape else (1080, 1920)
    sizes = {
        "720p": {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (720, 720), "4:5": (720, 900)},
        "1080p": {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)},
    }
    selected = resolution if resolution in {"720p", "1080p"} else "1080p"
    return sizes[selected][aspect]


def _escape_filter_text(value: str) -> str:
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace("%", "\\%")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace(",", "\\,")
    )


def _escape_filter_path(path: str) -> str:
    return str(Path(path).resolve(strict=False)).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def resolve_vietnamese_font_path(explicit: str = "") -> str:
    candidates = (
        explicit,
        os.getenv("LOCAL_FFMPEG_FONT_PATH", ""),
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\segoeui.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    )
    for candidate in candidates:
        clean = str(candidate or "").strip()
        if clean and Path(clean).is_file():
            return clean
    return ""


def _text_filter(config: dict[str, Any]) -> str:
    if not config:
        return ""
    position = str(config.get("position") or "bottom")
    y = {"top": "h*0.06", "center": "(h-text_h)/2", "bottom": "h-text_h-h*0.06"}[position]
    font_path = resolve_vietnamese_font_path(str(config.get("font_path") or ""))
    font = f"fontfile='{_escape_filter_path(font_path)}':" if font_path else ""
    start = int(config.get("start_ms") or 0) / 1000
    end = int(config.get("end_ms") or 0) / 1000
    return (
        f"drawtext={font}text='{_escape_filter_text(str(config.get('content') or ''))}':"
        f"fontcolor=white:fontsize={int(config.get('font_size') or 42)}:"
        f"borderw={int(config.get('outline') or 2)}:bordercolor=black@0.9:"
        f"x=(w-text_w)/2:y={y}:enable='between(t,{start:.3f},{end:.3f})'"
    )


def build_manual_ffmpeg_command(
    plan: dict[str, Any],
    *,
    output_path: str,
    source_probe: dict[str, Any],
    ffmpeg_path: str,
) -> list[str]:
    source = str(plan.get("input_video") or "")
    trim = dict(plan.get("trim") or {})
    start_seconds = int(trim.get("start_ms") or 0) / 1000
    selected_seconds = (int(trim.get("end_ms") or 0) - int(trim.get("start_ms") or 0)) / 1000
    command = [ffmpeg_path, "-y", "-ss", f"{start_seconds:.3f}", "-i", source]
    logo = dict(plan.get("logo_overlay") or {})
    if logo:
        command.extend(["-i", str(logo.get("path") or "")])
    filters: list[str] = []
    aspect = str((plan.get("crop_or_fit") or {}).get("aspect_ratio") or "keep")
    mode = str((plan.get("crop_or_fit") or {}).get("mode") or "fit")
    width, height = _target_size(
        aspect,
        str(plan.get("resolution") or "keep"),
        int(source_probe.get("width") or 1280),
        int(source_probe.get("height") or 720),
    )
    needs_geometry_filter = bool(
        aspect != "keep"
        or str(plan.get("resolution") or "keep") != "keep"
        or int(source_probe.get("width") or 0) > 1920
        or int(source_probe.get("height") or 0) > 1920
    )
    if needs_geometry_filter:
        if mode == "crop":
            filters.extend([
                f"scale={width}:{height}:force_original_aspect_ratio=increase",
                f"crop={width}:{height}",
            ])
        else:
            filters.extend([
                f"scale={width}:{height}:force_original_aspect_ratio=decrease",
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
            ])
        filters.append("setsar=1")
    rotation = int(plan.get("rotation") or 0)
    if rotation == 90:
        filters.append("transpose=1")
    elif rotation == 180:
        filters.extend(["hflip", "vflip"])
    elif rotation == 270:
        filters.append("transpose=2")
    if plan.get("flip") == "horizontal":
        filters.append("hflip")
    elif plan.get("flip") == "vertical":
        filters.append("vflip")
    speed = float(plan.get("speed") or 1.0)
    if speed != 1.0:
        filters.append(f"setpts=PTS/{speed:g}")
    color = COLOR_PRESETS.get(str(plan.get("color_preset") or "keep"), "")
    if color:
        filters.append(color)
    brightness_percent = int(plan.get("brightness_percent") or 100)
    if brightness_percent != 100:
        filters.append(f"eq=brightness={(brightness_percent - 100) / 200:.3f}")
    text = _text_filter(dict(plan.get("text_overlay") or {}))
    if text:
        filters.append(text)
    subtitle = str(plan.get("subtitle_file") or "")
    if subtitle:
        subtitle_font = resolve_vietnamese_font_path()
        subtitle_style = "DejaVu Sans" if "dejavu" in subtitle_font.lower() else "Noto Sans"
        filters.append(
            f"subtitles='{_escape_filter_path(subtitle)}':"
            f"force_style='FontName={subtitle_style},FontSize=22,Outline=2,Shadow=0,MarginV=42,Alignment=2'"
        )
    filters.append("format=yuv420p")
    base_filter = ",".join(item for item in filters if item)
    if logo:
        position = str(logo.get("position") or "top_right")
        x_map = {"top_left": "main_w*0.04", "bottom_left": "main_w*0.04", "top_right": "main_w-overlay_w-main_w*0.04", "bottom_right": "main_w-overlay_w-main_w*0.04"}
        y_map = {"top_left": "main_h*0.035", "top_right": "main_h*0.035", "bottom_left": "main_h-overlay_h-main_h*0.035", "bottom_right": "main_h-overlay_h-main_h*0.035"}
        complex_filter = (
            f"[0:v]{base_filter}[base];"
            f"[1:v]format=rgba,colorchannelmixer=aa={float(logo.get('opacity') or 1.0):.3f}[logo0];"
            f"[logo0][base]scale2ref=w=main_w*{float(logo.get('scale') or 0.12):.3f}:h=ow/mdar[logo][base2];"
            f"[base2][logo]overlay={x_map[position]}:{y_map[position]}[v]"
        )
        command.extend(["-filter_complex", complex_filter, "-map", "[v]"])
    else:
        command.extend(["-vf", base_filter, "-map", "0:v:0"])
    has_audio = bool(source_probe.get("has_audio"))
    volume = float(plan.get("volume") or 0.0)
    if has_audio and volume > 0:
        command.extend(["-map", "0:a:0?"])
        audio_filters = []
        if speed != 1.0:
            audio_filters.append(f"atempo={speed:g}")
        if volume != 1.0:
            audio_filters.append(f"volume={volume:g}")
        if audio_filters:
            command.extend(["-af", ",".join(audio_filters)])
        command.extend(["-c:a", "aac", "-b:a", "160k", "-ar", "48000"])
    else:
        command.append("-an")
    expected_output_seconds = selected_seconds / max(0.01, speed)
    command.extend([
        "-t", f"{expected_output_seconds:.3f}",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-maxrate", "8M",
        "-bufsize", "16M",
        "-movflags", "+faststart",
        "-max_muxing_queue_size", "2048",
        str(output_path),
    ])
    return command


def build_split_ffmpeg_command(
    source_path: str,
    item: SplitRange,
    output_path: str,
    *,
    ffmpeg_path: str,
    has_audio: bool,
) -> list[str]:
    command = [
        ffmpeg_path, "-y",
        "-ss", f"{item.start_ms / 1000:.3f}",
        "-i", str(source_path),
        "-t", f"{item.duration_ms / 1000:.3f}",
        "-map", "0:v:0",
        "-vf", "scale=w='min(iw,1920)':h='min(ih,1920)':force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1,format=yuv420p",
    ]
    if has_audio:
        command.extend(["-map", "0:a:0?", "-c:a", "aac", "-b:a", "160k", "-ar", "48000"])
    else:
        command.append("-an")
    command.extend([
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-max_muxing_queue_size", "2048", str(output_path),
    ])
    return command


def _run(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    if not command or "ffmpeg" not in Path(str(command[0])).name.lower():
        raise LocalVideoEditError("ffmpeg_command_required")
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=max(1, int(timeout)), check=False)
    except subprocess.TimeoutExpired as exc:
        raise LocalVideoEditError("ffmpeg_timeout") from exc
    except OSError as exc:
        raise LocalVideoEditError(f"ffmpeg_exec_failed:{type(exc).__name__}") from exc


def _run_checked(command: list[str], *, timeout: int) -> None:
    result = _run(command, timeout=timeout)
    if result.returncode != 0:
        lines = [line.strip() for line in str(result.stderr or result.stdout or "").splitlines() if line.strip()]
        diagnostics = [
            line for line in lines
            if not line.startswith("[Parsed_")
            and any(token in line.lower() for token in ("error", "invalid", "failed", "unable", "not found"))
        ]
        detail = " | ".join((diagnostics or lines)[-2:])
        raise LocalVideoEditError(f"ffmpeg_failed:{detail[:300] or result.returncode}")


def _ffconcat_manifest_entry(path: str | Path) -> str:
    normalized_path = str(path).replace("\\", "/")
    escaped_path = normalized_path.replace("'", "'\\''")
    return f"file '{escaped_path}'\n"


def _normalize_concat_inputs(
    sources: list[str],
    *,
    workspace: Path,
    ffmpeg_path: str,
    ffprobe_path: str,
    timeout: int,
) -> tuple[str, dict[str, Any]]:
    normalized: list[Path] = []
    for index, source in enumerate(sources, start=1):
        probe = probe_video_file(source, ffprobe_path=ffprobe_path)
        if not probe.get("ok"):
            raise LocalVideoEditError(str(probe.get("reason") or "concat_probe_failed"))
        target = workspace / f"concat_normalized_{index:03d}.mp4"
        command = [ffmpeg_path, "-y", "-i", source]
        if not probe.get("has_audio"):
            command.extend(["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"])
        command.extend([
            "-map", "0:v:0", "-map", "0:a:0?" if probe.get("has_audio") else "1:a:0",
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=30,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
            "-shortest", "-movflags", "+faststart", str(target),
        ])
        _run_checked(command, timeout=timeout)
        normalized.append(target)
    manifest = workspace / "concat_inputs.txt"
    manifest.write_text(
        "".join(_ffconcat_manifest_entry(item) for item in normalized),
        encoding="utf-8",
    )
    concat_output = workspace / "concat_source.mp4"
    _run_checked(
        [ffmpeg_path, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", "-movflags", "+faststart", str(concat_output)],
        timeout=timeout,
    )
    probe = probe_video_file(concat_output, ffprobe_path=ffprobe_path)
    if not probe.get("ok"):
        raise LocalVideoEditError(str(probe.get("reason") or "concat_output_invalid"))
    return str(concat_output), probe


def execute_manual_edit(
    plan: dict[str, Any],
    *,
    output_path: str,
    workspace: str | os.PathLike[str],
    ffmpeg_path: str = "",
    ffprobe_path: str = "",
    timeout: int = FFMPEG_TIMEOUT_SECONDS,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    workspace_path = Path(workspace).resolve(strict=False)
    output = require_path_within(output_path, workspace_path)
    ffmpeg = find_ffmpeg(ffmpeg_path)
    probe_bin = find_ffprobe(ffprobe_path, ffmpeg_path=ffmpeg)
    if not ffmpeg:
        raise LocalVideoEditError("ffmpeg_missing")
    if not probe_bin:
        raise LocalVideoEditError("ffprobe_missing")
    source_probe = probe_video_file(str(plan.get("input_video") or ""), ffprobe_path=probe_bin)
    if not source_probe.get("ok"):
        raise LocalVideoEditError(str(source_probe.get("reason") or "input_probe_failed"))
    normalized = normalize_manual_edit_plan(plan, source_duration_ms=int(source_probe.get("duration_ms") or 0), workspace=workspace_path)
    if progress:
        progress({"stage": "preparing_plan", "processed": 0, "total": 1})
    concat_sources = [normalized["input_video"], *normalized.get("concat_inputs", [])]
    if len(concat_sources) > 1:
        source, source_probe = _normalize_concat_inputs(
            concat_sources,
            workspace=workspace_path,
            ffmpeg_path=ffmpeg,
            ffprobe_path=probe_bin,
            timeout=timeout,
        )
        normalized["input_video"] = source
        normalized["trim"] = {"start_ms": 0, "end_ms": int(source_probe.get("duration_ms") or 0)}
    if progress:
        progress({"stage": "processing_video", "processed": 0, "total": 1})
    command = build_manual_ffmpeg_command(normalized, output_path=str(output), source_probe=source_probe, ffmpeg_path=ffmpeg)
    _run_checked(command, timeout=timeout)
    enforce_workspace_limit(workspace_path)
    if progress:
        progress({"stage": "validating_output", "processed": 1, "total": 1})
    expected = expected_manual_duration_ms(normalized)
    validation = validate_mp4_output(
        output,
        expected_duration_ms=expected,
        require_audio=bool(source_probe.get("has_audio") and float(normalized.get("volume") or 0) > 0),
        ffprobe_path=probe_bin,
    )
    if not validation.get("ok"):
        raise LocalVideoEditError(str(validation.get("reason") or "output_validation_failed"))
    return {
        "ok": True,
        "output_path": str(output),
        "validation": validation,
        "expected_duration_ms": expected,
        "audio_preserved": bool(validation.get("has_audio")) if source_probe.get("has_audio") else False,
        "provider_called": False,
        "xu_charged": 0,
    }


def execute_split_plan(
    source_path: str,
    ranges: Iterable[SplitRange],
    *,
    workspace: str | os.PathLike[str],
    coverage_required: bool,
    ffmpeg_path: str = "",
    ffprobe_path: str = "",
    timeout: int = FFMPEG_TIMEOUT_SECONDS,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    workspace_path = Path(workspace).resolve(strict=False)
    source = require_path_within(source_path, workspace_path)
    items = list(ranges or [])
    if not items:
        raise LocalVideoEditError("split_plan_empty")
    ffmpeg = find_ffmpeg(ffmpeg_path)
    probe_bin = find_ffprobe(ffprobe_path, ffmpeg_path=ffmpeg)
    if not ffmpeg:
        raise LocalVideoEditError("ffmpeg_missing")
    if not probe_bin:
        raise LocalVideoEditError("ffprobe_missing")
    source_probe = probe_video_file(source, ffprobe_path=probe_bin)
    if not source_probe.get("ok"):
        raise LocalVideoEditError(str(source_probe.get("reason") or "input_probe_failed"))
    coverage = validate_exact_coverage(items, int(source_probe.get("duration_ms") or 0))
    if coverage_required and not coverage.get("ok"):
        raise LocalVideoEditError("split_coverage_invalid")
    outputs: list[dict[str, Any]] = []
    total = len(items)
    for item in items:
        if progress:
            progress({"stage": "processing_video", "processed": item.index - 1, "total": total, "current_part": item.index})
        target = workspace_path / split_output_name(item.index, total)
        command = build_split_ffmpeg_command(
            str(source), item, str(target), ffmpeg_path=ffmpeg, has_audio=bool(source_probe.get("has_audio"))
        )
        _run_checked(command, timeout=timeout)
        validation = validate_mp4_output(
            target,
            expected_duration_ms=item.duration_ms,
            require_audio=bool(source_probe.get("has_audio")),
            ffprobe_path=probe_bin,
        )
        if not validation.get("ok"):
            raise LocalVideoEditError(f"split_part_invalid:{item.index}:{validation.get('reason')}")
        outputs.append({"index": item.index, "path": str(target), "duration_ms": item.duration_ms, "validation": validation})
        enforce_workspace_limit(workspace_path)
        if progress:
            progress({"stage": "validating_output", "processed": item.index, "total": total, "current_part": item.index})
    actual_total = sum(int(item["validation"].get("duration_ms") or 0) for item in outputs)
    expected_total = sum(item.duration_ms for item in items)
    tolerance = max(1_000, 750 * len(items))
    if abs(actual_total - expected_total) > tolerance:
        raise LocalVideoEditError("split_total_duration_mismatch")
    return {
        "ok": True,
        "outputs": outputs,
        "part_count": total,
        "coverage": coverage,
        "source_duration_ms": int(source_probe.get("duration_ms") or 0),
        "actual_total_duration_ms": actual_total,
        "expected_total_duration_ms": expected_total,
        "audio_preserved": bool(source_probe.get("has_audio")),
        "provider_called": False,
        "xu_charged": 0,
    }


def public_plan_summary(plan: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    trim = dict(plan.get("trim") or {})
    if int(trim.get("start_ms") or 0) or int(trim.get("end_ms") or 0):
        lines.append("Cắt theo khoảng đã chọn")
    aspect = str((plan.get("crop_or_fit") or {}).get("aspect_ratio") or "keep")
    if aspect != "keep":
        lines.append(f"Tỉ lệ {aspect} · {str((plan.get('crop_or_fit') or {}).get('mode') or 'fit')}")
    if str(plan.get("resolution") or "keep") != "keep":
        lines.append(f"Độ phân giải {plan['resolution']}")
    if int(plan.get("rotation") or 0):
        lines.append(f"Xoay {int(plan['rotation'])}°")
    if str(plan.get("flip") or "none") != "none":
        lines.append("Lật ngang" if plan["flip"] == "horizontal" else "Lật dọc")
    if float(plan.get("speed") or 1.0) != 1.0:
        lines.append(f"Tốc độ {float(plan['speed']):g}x")
    if float(plan.get("volume") or 1.0) != 1.0:
        lines.append("Tắt tiếng" if float(plan.get("volume") or 0) == 0 else f"Âm lượng {float(plan['volume']) * 100:g}%")
    if int(plan.get("brightness_percent") or 100) != 100:
        lines.append(f"Độ sáng {int(plan['brightness_percent'])}%")
    if plan.get("text_overlay"):
        lines.append("Chèn chữ")
    if plan.get("logo_overlay"):
        lines.append("Chèn logo")
    if plan.get("subtitle_file"):
        lines.append("Chèn phụ đề SRT")
    if str(plan.get("color_preset") or "keep") != "keep":
        lines.append("Màu: " + str(plan.get("color_preset")))
    if plan.get("concat_inputs"):
        lines.append(f"Ghép {len(plan['concat_inputs']) + 1} video")
    return lines or ["Giữ nguyên hình và âm thanh"]
