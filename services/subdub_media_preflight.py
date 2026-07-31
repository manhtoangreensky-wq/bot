"""Canonical, provider-neutral media preflight for SubDub."""

from __future__ import annotations

from fractions import Fraction
from typing import Any


MAX_STAGE_TIMEOUT_SECONDS = 7200
DEFAULT_DURATION_TOLERANCE_SECONDS = 0.35


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _rate(value: Any) -> float:
    token = str(value or "").strip()
    if not token or token in {"0/0", "N/A"}:
        return 0.0
    try:
        return float(Fraction(token))
    except (ValueError, ZeroDivisionError):
        return _float(token)


def _rotation(stream: dict[str, Any]) -> int:
    candidates: list[Any] = []
    for item in list(stream.get("side_data_list") or []):
        if isinstance(item, dict):
            candidates.append(item.get("rotation"))
    tags = stream.get("tags") if isinstance(stream.get("tags"), dict) else {}
    candidates.extend((tags.get("rotate"), stream.get("rotation")))
    for candidate in candidates:
        if candidate in {None, ""}:
            continue
        try:
            return int(round(float(candidate))) % 360
        except (TypeError, ValueError):
            continue
    return 0


def _container_name(format_name: Any) -> str:
    tokens = {
        item.strip().lower()
        for item in str(format_name or "").split(",")
        if item.strip()
    }
    if "webm" in tokens:
        return "webm"
    if "matroska" in tokens:
        return "mkv"
    if tokens & {"mp4", "m4v", "3gp", "3g2", "mj2"}:
        return "mp4"
    if "mov" in tokens:
        return "mov"
    return sorted(tokens)[0] if tokens else "unknown"


def _bit_depth(pixel_format: str) -> int:
    token = str(pixel_format or "").lower()
    for depth in (16, 14, 12, 10, 9):
        if str(depth) in token:
            return depth
    return 8 if token else 0


def parse_ffprobe_payload(payload: dict[str, Any] | None, *, size_bytes: int = 0) -> dict[str, Any]:
    """Normalize FFprobe JSON and state every reason normalization is needed."""
    source = dict(payload or {})
    format_info = dict(source.get("format") or {})
    streams = [dict(item or {}) for item in list(source.get("streams") or [])]
    video_streams = [item for item in streams if str(item.get("codec_type") or "").lower() == "video"]
    audio_streams = [item for item in streams if str(item.get("codec_type") or "").lower() == "audio"]
    video = video_streams[0] if video_streams else {}
    audio = audio_streams[0] if audio_streams else {}

    duration = max(
        0.0,
        _float(format_info.get("duration")),
        _float(video.get("duration")),
        max((_float(item.get("duration")) for item in audio_streams), default=0.0),
    )
    start_time = _float(format_info.get("start_time"), _float(video.get("start_time")))
    container = _container_name(format_info.get("format_name"))
    video_codec = str(video.get("codec_name") or "").lower()
    pixel_format = str(video.get("pix_fmt") or "").lower()
    avg_rate = _rate(video.get("avg_frame_rate"))
    nominal_rate = _rate(video.get("r_frame_rate"))
    frame_rate_mode = "cfr"
    if avg_rate <= 0 or nominal_rate <= 0 or abs(avg_rate - nominal_rate) > 0.01:
        frame_rate_mode = "vfr"
    rotation = _rotation(video)
    coded_width = max(0, _int(video.get("width")))
    coded_height = max(0, _int(video.get("height")))
    if rotation in {90, 270}:
        display_width, display_height = coded_height, coded_width
    else:
        display_width, display_height = coded_width, coded_height

    audio_codec = str(audio.get("codec_name") or "").lower()
    audio_sample_rate = max(0, _int(audio.get("sample_rate")))
    audio_channels = max(0, _int(audio.get("channels")))
    audio_layout = str(audio.get("channel_layout") or "").lower()
    reasons: list[str] = []
    if container != "mp4":
        reasons.append("container_not_mp4")
    if video_codec != "h264":
        reasons.append("video_codec_not_h264")
    if pixel_format != "yuv420p":
        reasons.append("pixel_format_not_yuv420p")
    if frame_rate_mode != "cfr":
        reasons.append("variable_frame_rate")
    if rotation:
        reasons.append("rotation_metadata")
    stream_start_times = [_float(item.get("start_time")) for item in streams]
    if abs(start_time) > 0.001 or any(abs(value) > 0.001 for value in stream_start_times):
        reasons.append("non_zero_start_time")
    if len(audio_streams) > 1:
        reasons.append("multiple_audio_streams")
    if audio_streams:
        if audio_codec != "aac":
            reasons.append("audio_codec_not_aac")
        if audio_sample_rate != 48000:
            reasons.append("audio_sample_rate_not_48000")
        if audio_layout not in {"mono", "stereo"} or audio_channels not in {1, 2}:
            reasons.append("audio_layout_not_mono_or_stereo")

    return {
        "ok": bool(video_streams and duration > 0),
        "detail": "ok" if video_streams and duration > 0 else "video_stream_or_duration_missing",
        "duration": duration,
        "start_time": start_time,
        "size": max(0, int(size_bytes or _int(format_info.get("size")))),
        "container": container,
        "format_name": str(format_info.get("format_name") or ""),
        "has_video": bool(video_streams),
        "has_audio": bool(audio_streams),
        "video_stream_count": len(video_streams),
        "audio_stream_count": len(audio_streams),
        "video_codec": video_codec,
        "video_profile": str(video.get("profile") or ""),
        "pixel_format": pixel_format,
        "bit_depth": _bit_depth(pixel_format),
        "coded_width": coded_width,
        "coded_height": coded_height,
        "display_width": display_width,
        "display_height": display_height,
        "width": display_width,
        "height": display_height,
        "rotation": rotation,
        "avg_frame_rate": avg_rate,
        "nominal_frame_rate": nominal_rate,
        "frame_rate_mode": frame_rate_mode,
        "video_time_base": str(video.get("time_base") or ""),
        "audio_codec": audio_codec,
        "audio_sample_rate": audio_sample_rate,
        "audio_channels": audio_channels,
        "audio_layout": audio_layout,
        "audio_time_base": str(audio.get("time_base") or ""),
        "normalization_required": bool(reasons),
        "normalization_reasons": reasons,
    }


def timeout_for_stage(stage: str, *, duration_seconds: float = 0.0, size_bytes: int = 0) -> int:
    """Return a bounded timeout derived from measured work, not a fixture size."""
    duration = max(0.0, _float(duration_seconds))
    size_mib = max(0.0, float(size_bytes or 0) / (1024.0 * 1024.0))
    policies = {
        "probe": (60, 0.20, 0.50),
        "extract": (300, 1.50, 1.00),
        "normalize": (600, 4.00, 2.00),
        "render": (900, 6.00, 3.00),
        "compress": (900, 6.00, 3.00),
    }
    floor, duration_factor, size_factor = policies.get(str(stage or "").lower(), (120, 2.0, 1.0))
    estimate = max(float(floor), duration * duration_factor + size_mib * size_factor)
    return int(min(MAX_STAGE_TIMEOUT_SECONDS, max(1, round(estimate))))


def build_normalization_command(
    ffmpeg_path: str,
    input_path: str,
    output_path: str,
    probe: dict[str, Any] | None,
) -> list[str]:
    """Build one full-duration canonical H.264/AAC normalization command."""
    current = dict(probe or {})
    duration = max(0.001, _float(current.get("duration")))
    rotation = _int(current.get("rotation")) % 360
    command = [str(ffmpeg_path), "-y"]
    if rotation:
        command.append("-noautorotate")
    command.extend(["-i", str(input_path), "-map", "0:v:0", "-map", "0:a:0?"])

    video_filters: list[str] = []
    if rotation == 90:
        video_filters.append("transpose=clock")
    elif rotation == 270:
        video_filters.append("transpose=cclock")
    elif rotation == 180:
        video_filters.extend(("hflip", "vflip"))
    if str(current.get("frame_rate_mode") or "") == "vfr":
        target_rate = _float(current.get("avg_frame_rate")) or 30.0
        target_rate = min(60.0, max(15.0, target_rate))
        video_filters.append(f"fps={target_rate:.3f}")
    video_filters.extend(("setpts=PTS-STARTPTS", "pad=ceil(iw/2)*2:ceil(ih/2)*2"))
    command.extend([
        "-vf", ",".join(video_filters),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
    ])
    if current.get("has_audio"):
        command.extend([
            "-af", "aresample=48000,asetpts=PTS-STARTPTS",
            "-c:a", "aac",
            "-b:a", "160k",
            "-ac", "2",
            "-ar", "48000",
        ])
    command.extend([
        "-t", f"{duration:.3f}",
        "-metadata:s:v:0", "rotate=0",
        "-avoid_negative_ts", "make_zero",
        "-movflags", "+faststart",
        str(output_path),
    ])
    return command


def duration_matches_source(
    source_duration: float,
    output_duration: float,
    *,
    tolerance_seconds: float = DEFAULT_DURATION_TOLERANCE_SECONDS,
) -> bool:
    source = max(0.0, _float(source_duration))
    output = max(0.0, _float(output_duration))
    return bool(source > 0 and output > 0 and abs(output - source) <= max(0.01, _float(tolerance_seconds, 0.35)))
