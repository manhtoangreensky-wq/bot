"""Validation, limits, and workspace safety for local video tools."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Iterable


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


REPO_ROOT = Path(__file__).resolve().parents[1]
VIDEO_LOCAL_WORKSPACE_ROOT = Path(
    os.getenv("VIDEO_LOCAL_WORKSPACE_ROOT") or REPO_ROOT / "data" / "tmp" / "video_local"
)
MAX_UPLOAD_BYTES = _env_int("VIDEO_LOCAL_MAX_UPLOAD_BYTES", 50 * 1024 * 1024, 1 * 1024 * 1024, 2 * 1024 * 1024 * 1024)
MAX_DURATION_SECONDS = _env_int("VIDEO_LOCAL_MAX_DURATION_SECONDS", 30 * 60, 10, 12 * 60 * 60)
MAX_SPLIT_PARTS = _env_int("VIDEO_LOCAL_MAX_SPLIT_PARTS", 30, 1, 100)
MAX_ACTIVE_JOBS_PER_USER = _env_int("VIDEO_LOCAL_MAX_ACTIVE_JOBS_PER_USER", 1, 1, 5)
MAX_ACTIVE_FFMPEG = _env_int("VIDEO_LOCAL_MAX_ACTIVE_FFMPEG", 1, 1, 4)
FFMPEG_TIMEOUT_SECONDS = _env_int("VIDEO_LOCAL_FFMPEG_TIMEOUT_SECONDS", 600, 30, 7_200)
MAX_WORKSPACE_BYTES = _env_int("VIDEO_LOCAL_MAX_WORKSPACE_BYTES", 1024 * 1024 * 1024, 50 * 1024 * 1024, 20 * 1024 * 1024 * 1024)
MIN_OUTPUT_BYTES = _env_int("VIDEO_LOCAL_MIN_OUTPUT_BYTES", 1024, 128, 1024 * 1024)
MAX_OUTPUT_WIDTH = 1920
MAX_OUTPUT_HEIGHT = 1920

ALLOWED_SOURCE_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg"}
ALLOWED_SUBTITLE_EXTENSIONS = {".srt"}
ALLOWED_OUTPUT_EXTENSIONS = {".mp4"}
FORBIDDEN_DELIVERY_EXTENSIONS = {".db", ".sqlite", ".sqlite3", ".env", ".log", ".bak"}
_SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_SRT_TIME = re.compile(
    r"(?m)^\s*\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}\s*$"
)


class LocalVideoValidationError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _resolve(path: str | os.PathLike[str]) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def path_is_within(path: str | os.PathLike[str], root: str | os.PathLike[str]) -> bool:
    target = _resolve(path)
    base = _resolve(root)
    return target != base and base in target.parents


def require_path_within(path: str | os.PathLike[str], root: str | os.PathLike[str]) -> Path:
    target = _resolve(path)
    if not path_is_within(target, root):
        raise LocalVideoValidationError("path_outside_workspace")
    return target


def create_job_workspace(job_id: str | int, *, root: str | os.PathLike[str] | None = None) -> Path:
    clean_id = str(job_id or "").strip()
    if not _SAFE_JOB_ID.fullmatch(clean_id):
        raise LocalVideoValidationError("unsafe_job_id")
    base = _resolve(root or VIDEO_LOCAL_WORKSPACE_ROOT)
    if base == Path(base.anchor) or base == REPO_ROOT.resolve(strict=False):
        raise LocalVideoValidationError("unsafe_workspace_root")
    base.mkdir(parents=True, exist_ok=True)
    workspace = base / clean_id
    require_path_within(workspace, base)
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def cleanup_job_workspace(
    workspace: str | os.PathLike[str],
    *,
    root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    base = _resolve(root or VIDEO_LOCAL_WORKSPACE_ROOT)
    try:
        target = require_path_within(workspace, base)
    except LocalVideoValidationError as exc:
        return {"ok": False, "removed": False, "reason": exc.reason}
    if not target.exists():
        return {"ok": True, "removed": False, "reason": "already_absent"}
    try:
        shutil.rmtree(target)
    except Exception as exc:
        return {"ok": False, "removed": False, "reason": f"cleanup_failed:{type(exc).__name__}"}
    return {"ok": not target.exists(), "removed": not target.exists(), "reason": "removed" if not target.exists() else "cleanup_failed"}


def workspace_size_bytes(workspace: str | os.PathLike[str]) -> int:
    target = _resolve(workspace)
    if not target.exists() or not target.is_dir():
        return 0
    total = 0
    for child in target.rglob("*"):
        if child.is_file() and not child.is_symlink():
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return total


def enforce_workspace_limit(workspace: str | os.PathLike[str], *, maximum_bytes: int = MAX_WORKSPACE_BYTES) -> int:
    size = workspace_size_bytes(workspace)
    if size > int(maximum_bytes):
        raise LocalVideoValidationError("workspace_limit_exceeded")
    return size


def validate_extension(filename: str, allowed: set[str]) -> str:
    name = Path(str(filename or "").replace("\\", "/")).name
    suffix = Path(name).suffix.lower()
    if not name or name in {".", ".."} or suffix not in allowed:
        raise LocalVideoValidationError("unsupported_file_type")
    return name


def safe_display_filename(filename: str, fallback: str = "video.mp4") -> str:
    name = Path(str(filename or "").replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" ._")[:120]
    return name or fallback


def find_ffmpeg(explicit: str = "") -> str:
    candidates = [
        explicit,
        os.getenv("LOCAL_FFMPEG_PATH", ""),
        os.getenv("FFMPEG_PATH", ""),
        shutil.which("ffmpeg") or "",
    ]
    for candidate in candidates:
        clean = str(candidate or "").strip()
        if clean and (Path(clean).is_file() or shutil.which(clean)):
            return clean
    return ""


def find_ffprobe(explicit: str = "", *, ffmpeg_path: str = "") -> str:
    candidates = [explicit, os.getenv("FFPROBE_PATH", "")]
    ffmpeg = str(ffmpeg_path or find_ffmpeg()).strip()
    if ffmpeg:
        ffmpeg_file = Path(ffmpeg)
        candidates.append(str(ffmpeg_file.with_name("ffprobe.exe" if ffmpeg_file.suffix.lower() == ".exe" else "ffprobe")))
    candidates.append(shutil.which("ffprobe") or "")
    for candidate in candidates:
        clean = str(candidate or "").strip()
        if clean and (Path(clean).is_file() or shutil.which(clean)):
            return clean
    return ""


def _fps(value: str) -> float:
    text = str(value or "0").strip()
    try:
        if "/" in text:
            numerator, denominator = text.split("/", 1)
            denominator_value = float(denominator or 0)
            return float(numerator or 0) / denominator_value if denominator_value else 0.0
        return float(text or 0)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def probe_video_file(path: str | os.PathLike[str], *, ffprobe_path: str = "", timeout: int = 45) -> dict[str, Any]:
    target = _resolve(path)
    if not target.is_file():
        return {"ok": False, "reason": "input_missing"}
    size = target.stat().st_size
    if size <= 0:
        return {"ok": False, "reason": "input_zero_bytes", "bytes": size}
    probe = find_ffprobe(ffprobe_path)
    if not probe:
        return {"ok": False, "reason": "ffprobe_missing", "bytes": size}
    command = [
        probe,
        "-v", "error",
        "-show_entries", "format=duration,format_name,size:stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate",
        "-of", "json",
        str(target),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=max(1, int(timeout)), check=False)
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "ffprobe_timeout", "bytes": size}
    except (OSError, ValueError) as exc:
        return {"ok": False, "reason": f"ffprobe_exec_failed:{type(exc).__name__}", "bytes": size}
    if result.returncode != 0:
        return {"ok": False, "reason": "ffprobe_failed", "bytes": size}
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "reason": "ffprobe_invalid_json", "bytes": size}
    streams = [item for item in payload.get("streams") or [] if isinstance(item, dict)]
    video_stream = next((item for item in streams if str(item.get("codec_type") or "") == "video"), {})
    audio_stream_count = sum(1 for item in streams if str(item.get("codec_type") or "") == "audio")
    has_audio = audio_stream_count > 0
    format_data = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    try:
        duration = float(format_data.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    fps = _fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") or "0")
    return {
        "ok": bool(video_stream and duration > 0 and width > 0 and height > 0),
        "reason": "" if video_stream and duration > 0 and width > 0 and height > 0 else "invalid_video_metadata",
        "bytes": int(size),
        "duration": duration,
        "duration_ms": int(round(duration * 1000)),
        "width": width,
        "height": height,
        "fps": fps,
        "has_video": bool(video_stream),
        "has_audio": has_audio,
        "audio_stream_count": audio_stream_count,
        "format_name": str(format_data.get("format_name") or ""),
        "video_codec": str(video_stream.get("codec_name") or ""),
    }


def validate_source_metadata(metadata: dict[str, Any], *, file_size: int = 0) -> dict[str, Any]:
    data = dict(metadata or {})
    size = int(file_size or data.get("bytes") or 0)
    duration = float(data.get("duration") or 0)
    if size > MAX_UPLOAD_BYTES:
        return {**data, "ok": False, "reason": "video_too_large"}
    if duration > MAX_DURATION_SECONDS:
        return {**data, "ok": False, "reason": "duration_too_long"}
    if not data.get("ok"):
        return {**data, "ok": False, "reason": str(data.get("reason") or "invalid_video")}
    return {**data, "ok": True, "reason": ""}


def validate_mp4_output(
    path: str | os.PathLike[str],
    *,
    expected_duration_ms: int = 0,
    tolerance_ms: int | None = None,
    require_audio: bool = False,
    ffprobe_path: str = "",
) -> dict[str, Any]:
    target = _resolve(path)
    if target.suffix.lower() != ".mp4":
        return {"ok": False, "reason": "output_not_mp4"}
    if not target.is_file():
        return {"ok": False, "reason": "output_missing"}
    size = target.stat().st_size
    if size < MIN_OUTPUT_BYTES:
        return {"ok": False, "reason": "output_too_small", "bytes": size}
    probe = probe_video_file(target, ffprobe_path=ffprobe_path)
    if not probe.get("ok"):
        return {**probe, "ok": False}
    if "mp4" not in str(probe.get("format_name") or "").lower() and "mov" not in str(probe.get("format_name") or "").lower():
        return {**probe, "ok": False, "reason": "output_container_invalid"}
    if int(probe.get("width") or 0) <= 0 or int(probe.get("height") or 0) <= 0:
        return {**probe, "ok": False, "reason": "output_resolution_invalid"}
    if int(probe.get("width") or 0) > MAX_OUTPUT_WIDTH or int(probe.get("height") or 0) > MAX_OUTPUT_HEIGHT:
        return {**probe, "ok": False, "reason": "output_resolution_exceeded"}
    if require_audio and not probe.get("has_audio"):
        return {**probe, "ok": False, "reason": "output_audio_missing"}
    expected = max(0, int(expected_duration_ms or 0))
    actual = int(probe.get("duration_ms") or 0)
    if expected:
        tolerance = int(tolerance_ms if tolerance_ms is not None else max(750, round(expected * 0.08)))
        if abs(actual - expected) > tolerance:
            return {
                **probe,
                "ok": False,
                "reason": "output_duration_mismatch",
                "expected_duration_ms": expected,
                "duration_delta_ms": actual - expected,
                "tolerance_ms": tolerance,
            }
    return {**probe, "ok": True, "reason": "", "expected_duration_ms": expected}


def validate_srt_file(path: str | os.PathLike[str], *, workspace: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    target = _resolve(path)
    if workspace is not None:
        try:
            require_path_within(target, workspace)
        except LocalVideoValidationError as exc:
            return {"ok": False, "reason": exc.reason}
    if target.suffix.lower() != ".srt" or not target.is_file():
        return {"ok": False, "reason": "subtitle_not_srt"}
    if target.stat().st_size <= 0 or target.stat().st_size > 5 * 1024 * 1024:
        return {"ok": False, "reason": "subtitle_size_invalid"}
    try:
        text = target.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return {"ok": False, "reason": "subtitle_read_failed"}
    if not _SRT_TIME.search(text) or not re.search(r"(?m)^\s*\d+\s*$", text):
        return {"ok": False, "reason": "subtitle_format_invalid"}
    return {"ok": True, "reason": "", "cue_count": len(_SRT_TIME.findall(text))}


def delivery_file_allowed(path: str | os.PathLike[str], *, workspace: str | os.PathLike[str]) -> bool:
    try:
        target = require_path_within(path, workspace)
    except LocalVideoValidationError:
        return False
    return bool(
        target.is_file()
        and target.suffix.lower() in ALLOWED_OUTPUT_EXTENSIONS
        and target.suffix.lower() not in FORBIDDEN_DELIVERY_EXTENSIONS
        and not target.is_symlink()
    )


def build_safe_mp4_zip(
    output_path: str | os.PathLike[str],
    parts: Iterable[str | os.PathLike[str]],
    *,
    workspace: str | os.PathLike[str],
) -> str:
    target = require_path_within(output_path, workspace)
    if target.suffix.lower() != ".zip":
        raise LocalVideoValidationError("zip_extension_invalid")
    clean_parts = []
    for item in parts:
        part = require_path_within(item, workspace)
        if not delivery_file_allowed(part, workspace=workspace):
            raise LocalVideoValidationError("zip_contains_forbidden_artifact")
        clean_parts.append(part)
    if not clean_parts:
        raise LocalVideoValidationError("zip_empty")
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for part in clean_parts:
            archive.write(part, arcname=part.name)
    return str(target)


def local_video_limits() -> dict[str, Any]:
    return {
        "upload_limit_bytes": MAX_UPLOAD_BYTES,
        "duration_limit_seconds": MAX_DURATION_SECONDS,
        "split_part_limit": MAX_SPLIT_PARTS,
        "minimum_segment_seconds": 2,
        "maximum_output": "1080p",
        "maximum_active_jobs_per_user": MAX_ACTIVE_JOBS_PER_USER,
        "maximum_active_ffmpeg": MAX_ACTIVE_FFMPEG,
        "ffmpeg_timeout_seconds": FFMPEG_TIMEOUT_SECONDS,
        "workspace_limit_bytes": MAX_WORKSPACE_BYTES,
        "price_xu": 0,
    }
