"""Validation, limits, and workspace safety for local video tools."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import time
import zipfile
import zlib
from pathlib import Path
from typing import Any, Callable, Iterable

from PIL import Image, UnidentifiedImageError


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
ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_LOGO_BYTES = 10 * 1024 * 1024
MAX_LOGO_DIMENSION = 8_192
MAX_LOGO_PIXELS = 40_000_000
ALLOWED_SUBTITLE_EXTENSIONS = {".srt"}
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac", ".opus"}
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


def validate_workspace_root(
    root: str | os.PathLike[str] | None = None,
) -> Path:
    base = _resolve(root or VIDEO_LOCAL_WORKSPACE_ROOT)
    if base == Path(base.anchor) or base == REPO_ROOT.resolve(strict=False):
        raise LocalVideoValidationError("unsafe_workspace_root")
    return base


def create_job_workspace(job_id: str | int, *, root: str | os.PathLike[str] | None = None) -> Path:
    clean_id = str(job_id or "").strip()
    if not _SAFE_JOB_ID.fullmatch(clean_id):
        raise LocalVideoValidationError("unsafe_job_id")
    base = validate_workspace_root(root)
    base.mkdir(parents=True, exist_ok=True)
    workspace = base / clean_id
    require_path_within(workspace, base)
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def create_video_edit_claim_workspace(
    job_id: int,
    claim_attempt: int,
    *,
    root: str | os.PathLike[str] | None = None,
) -> tuple[Path, Path]:
    """Create one stable server-derived project root and isolated claim child."""

    if (
        isinstance(job_id, bool)
        or not isinstance(job_id, int)
        or job_id <= 0
        or isinstance(claim_attempt, bool)
        or not isinstance(claim_attempt, int)
        or claim_attempt <= 0
    ):
        raise LocalVideoValidationError("unsafe_job_id")
    base = validate_workspace_root(root)
    project = create_job_workspace(f"job_{job_id}", root=base)
    claim = project / f"claim_{claim_attempt}"
    require_path_within(claim, project)
    if claim.exists() and (claim.is_symlink() or not claim.is_dir()):
        raise LocalVideoValidationError("unsafe_job_id")
    claim.mkdir(parents=False, exist_ok=True)
    return project, require_path_within(claim, project)


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


def _png_dimensions(payload: bytes) -> tuple[int, int] | None:
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    offset = 8
    dimensions: tuple[int, int] | None = None
    saw_idat = False
    saw_iend = False
    while offset + 12 <= len(payload):
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        chunk_type = payload[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if data_end < data_start or crc_end > len(payload):
            return None
        expected_crc = struct.unpack(">I", payload[data_end:crc_end])[0]
        if zlib.crc32(chunk_type + payload[data_start:data_end]) & 0xFFFFFFFF != expected_crc:
            return None
        if dimensions is None:
            if chunk_type != b"IHDR" or length != 13:
                return None
            width, height = struct.unpack(">II", payload[data_start : data_start + 8])
            bit_depth = payload[data_start + 8]
            color_type = payload[data_start + 9]
            if (
                width <= 0
                or height <= 0
                or bit_depth not in {1, 2, 4, 8, 16}
                or color_type not in {0, 2, 3, 4, 6}
                or payload[data_start + 10] != 0
                or payload[data_start + 11] != 0
                or payload[data_start + 12] not in {0, 1}
            ):
                return None
            dimensions = (width, height)
        elif chunk_type == b"IDAT":
            saw_idat = True
        elif chunk_type == b"IEND":
            if length != 0:
                return None
            saw_iend = True
            offset = crc_end
            break
        offset = crc_end
    if not dimensions or not saw_idat or not saw_iend or offset != len(payload):
        return None
    return dimensions


def _jpeg_dimensions(payload: bytes) -> tuple[int, int] | None:
    if len(payload) < 12 or not payload.startswith(b"\xff\xd8") or not payload.endswith(b"\xff\xd9"):
        return None
    offset = 2
    dimensions: tuple[int, int] | None = None
    saw_scan = False
    sof_markers = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
    }
    standalone = {0x01, *range(0xD0, 0xD8)}
    while offset < len(payload) - 2:
        if payload[offset] != 0xFF:
            return None
        while offset < len(payload) and payload[offset] == 0xFF:
            offset += 1
        if offset >= len(payload):
            return None
        marker = payload[offset]
        offset += 1
        if marker == 0xDA:
            saw_scan = True
            break
        if marker == 0xD9:
            break
        if marker in standalone:
            continue
        if offset + 2 > len(payload):
            return None
        segment_length = struct.unpack(">H", payload[offset : offset + 2])[0]
        if segment_length < 2 or offset + segment_length > len(payload):
            return None
        if marker in sof_markers:
            if segment_length < 8:
                return None
            height = struct.unpack(">H", payload[offset + 3 : offset + 5])[0]
            width = struct.unpack(">H", payload[offset + 5 : offset + 7])[0]
            if width <= 0 or height <= 0:
                return None
            dimensions = (width, height)
        offset += segment_length
    return dimensions if dimensions and saw_scan else None


def _webp_dimensions(payload: bytes) -> tuple[int, int] | None:
    if (
        len(payload) < 30
        or payload[:4] != b"RIFF"
        or payload[8:12] != b"WEBP"
        or struct.unpack("<I", payload[4:8])[0] + 8 != len(payload)
    ):
        return None
    offset = 12
    dimensions: tuple[int, int] | None = None
    while offset + 8 <= len(payload):
        chunk_type = payload[offset : offset + 4]
        chunk_size = struct.unpack("<I", payload[offset + 4 : offset + 8])[0]
        data_start = offset + 8
        data_end = data_start + chunk_size
        padded_end = data_end + (chunk_size & 1)
        if data_end < data_start or padded_end > len(payload):
            return None
        chunk = payload[data_start:data_end]
        if chunk_type == b"VP8X" and len(chunk) >= 10:
            width = 1 + int.from_bytes(chunk[4:7], "little")
            height = 1 + int.from_bytes(chunk[7:10], "little")
            dimensions = (width, height)
        elif chunk_type == b"VP8L" and len(chunk) >= 5 and chunk[0] == 0x2F:
            packed = int.from_bytes(chunk[1:5], "little")
            dimensions = ((packed & 0x3FFF) + 1, ((packed >> 14) & 0x3FFF) + 1)
        elif (
            chunk_type == b"VP8 "
            and len(chunk) >= 10
            and chunk[3:6] == b"\x9d\x01\x2a"
        ):
            dimensions = (
                int.from_bytes(chunk[6:8], "little") & 0x3FFF,
                int.from_bytes(chunk[8:10], "little") & 0x3FFF,
            )
        offset = padded_end
    return dimensions if dimensions and offset == len(payload) else None


def validate_static_image_file(
    path: str | os.PathLike[str],
    *,
    expected_filename: str = "",
    maximum_bytes: int = MAX_LOGO_BYTES,
) -> dict[str, Any]:
    """Validate one static logo from its bytes, not Telegram metadata."""

    target = _resolve(path)
    if not target.is_file() or target.is_symlink():
        return {"ok": False, "reason": "logo_file_missing"}
    try:
        size = int(target.stat().st_size)
    except OSError:
        return {"ok": False, "reason": "logo_read_failed"}
    if size <= 0 or size > max(1, min(int(maximum_bytes), MAX_LOGO_BYTES)):
        return {"ok": False, "reason": "logo_size_invalid"}
    try:
        chunks: list[bytes] = []
        remaining = size
        with target.open("rb") as handle:
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    return {"ok": False, "reason": "logo_read_failed"}
                chunks.append(chunk)
                remaining -= len(chunk)
            if handle.read(1):
                return {"ok": False, "reason": "logo_size_invalid"}
        payload = b"".join(chunks)
    except OSError:
        return {"ok": False, "reason": "logo_read_failed"}
    if len(payload) != size:
        return {"ok": False, "reason": "logo_read_failed"}

    detected = ""
    dimensions: tuple[int, int] | None = None
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "png"
        dimensions = _png_dimensions(payload)
    elif payload.startswith(b"\xff\xd8"):
        detected = "jpeg"
        dimensions = _jpeg_dimensions(payload)
    elif payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        detected = "webp"
        dimensions = _webp_dimensions(payload)
    if not detected or dimensions is None:
        return {"ok": False, "reason": "logo_format_invalid"}

    filename = safe_display_filename(expected_filename or target.name, target.name)
    suffix = Path(filename).suffix.lower()
    expected_formats = {
        ".png": {"png"},
        ".jpg": {"jpeg"},
        ".jpeg": {"jpeg"},
        ".webp": {"webp"},
    }
    if detected not in expected_formats.get(suffix, set()):
        return {"ok": False, "reason": "logo_extension_content_mismatch"}
    width, height = dimensions
    if (
        width <= 0
        or height <= 0
        or width > MAX_LOGO_DIMENSION
        or height > MAX_LOGO_DIMENSION
        or width * height > MAX_LOGO_PIXELS
    ):
        return {"ok": False, "reason": "logo_dimensions_invalid"}
    try:
        with Image.open(io.BytesIO(payload)) as image:
            decoded_format = {
                "PNG": "png",
                "JPEG": "jpeg",
                "WEBP": "webp",
            }.get(str(image.format or "").upper(), "")
            decoded_dimensions = tuple(int(value) for value in image.size)
            animated = bool(getattr(image, "is_animated", False)) or int(
                getattr(image, "n_frames", 1) or 1
            ) != 1
            image.load()
    except (
        Image.DecompressionBombError,
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        ValueError,
    ):
        return {"ok": False, "reason": "logo_decode_invalid"}
    if animated:
        return {"ok": False, "reason": "logo_animation_invalid"}
    if decoded_format != detected or decoded_dimensions != dimensions:
        return {"ok": False, "reason": "logo_decode_invalid"}
    return {
        "ok": True,
        "reason": "",
        "format": detected,
        "width": width,
        "height": height,
        "bytes": size,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


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


def probe_video_file(
    path: str | os.PathLike[str],
    *,
    ffprobe_path: str = "",
    timeout: int = 45,
    deadline_monotonic: float | None = None,
    monotonic: Callable[[], float] | None = None,
) -> dict[str, Any]:
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
    probe_timeout = float(max(1, int(timeout)))
    if deadline_monotonic is not None:
        clock = monotonic or time.monotonic
        try:
            remaining = float(deadline_monotonic) - float(clock())
        except (TypeError, ValueError, OverflowError):
            return {"ok": False, "reason": "ffprobe_timeout", "bytes": size}
        if remaining <= 0:
            return {"ok": False, "reason": "ffprobe_timeout", "bytes": size}
        probe_timeout = min(probe_timeout, remaining)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=probe_timeout,
            check=False,
        )
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


def full_decode_video_file(
    path: str | os.PathLike[str],
    *,
    ffmpeg_path: str = "",
    timeout: int = 45,
    deadline_monotonic: float | None = None,
    monotonic: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Decode every video/audio packet before an artifact becomes terminal."""

    target = _resolve(path)
    if not target.is_file() or target.stat().st_size <= 0:
        return {"ok": False, "full_decode": False, "reason": "output_missing"}
    ffmpeg = find_ffmpeg(ffmpeg_path)
    if not ffmpeg:
        return {"ok": False, "full_decode": False, "reason": "ffmpeg_missing"}
    command = [
        ffmpeg,
        "-v", "error",
        "-xerror",
        "-i", str(target),
        "-map", "0:v:0",
        "-map", "0:a:0?",
        "-f", "null",
        "-",
    ]
    decode_timeout = float(max(1, int(timeout or 1)))
    if deadline_monotonic is not None:
        clock = monotonic or time.monotonic
        remaining = float(deadline_monotonic) - float(clock())
        if remaining <= 0:
            return {
                "ok": False,
                "full_decode": False,
                "reason": "output_full_decode_timeout",
            }
        decode_timeout = min(decode_timeout, remaining)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=decode_timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "full_decode": False, "reason": "output_full_decode_timeout"}
    except (OSError, ValueError) as exc:
        return {
            "ok": False,
            "full_decode": False,
            "reason": f"output_full_decode_exec_failed:{type(exc).__name__}",
        }
    if int(getattr(result, "returncode", 1)) != 0:
        return {"ok": False, "full_decode": False, "reason": "output_full_decode_failed"}
    return {"ok": True, "full_decode": True, "reason": ""}


def validate_source_metadata(
    metadata: dict[str, Any],
    *,
    file_size: int = 0,
    maximum_bytes: int = MAX_UPLOAD_BYTES,
    maximum_duration_seconds: int = MAX_DURATION_SECONDS,
) -> dict[str, Any]:
    data = dict(metadata or {})
    size = int(file_size or data.get("bytes") or 0)
    duration = float(data.get("duration") or 0)
    if int(maximum_bytes or 0) > 0 and size > int(maximum_bytes):
        return {**data, "ok": False, "reason": "video_too_large"}
    if int(maximum_duration_seconds or 0) > 0 and duration > int(maximum_duration_seconds):
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
    require_full_decode: bool = False,
    ffmpeg_path: str = "",
    decode_timeout: int = 45,
    deadline_monotonic: float | None = None,
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
    result = {**probe, "ok": True, "reason": "", "expected_duration_ms": expected}
    if require_full_decode:
        decoded = full_decode_video_file(
            target,
            ffmpeg_path=ffmpeg_path,
            timeout=decode_timeout,
            deadline_monotonic=deadline_monotonic,
        )
        if not decoded.get("ok"):
            return {
                **result,
                "ok": False,
                "full_decode": False,
                "reason": str(decoded.get("reason") or "output_full_decode_failed"),
            }
        result["full_decode"] = True
    return result


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
    blocks = [
        block
        for block in re.split(r"\r?\n\s*\r?\n", text.strip())
        if block.strip()
    ]
    timing_lines: list[str] = []
    for block in blocks:
        lines = block.splitlines()
        if (
            len(lines) < 3
            or not lines[0].strip().isdigit()
            or _SRT_TIME.fullmatch(lines[1].strip()) is None
            or not "\n".join(lines[2:]).strip()
        ):
            return {"ok": False, "reason": "subtitle_format_invalid"}
        timing_lines.append(lines[1].strip())
    if not timing_lines:
        return {"ok": False, "reason": "subtitle_format_invalid"}

    def timestamp_ms(value: str) -> int:
        hours, minutes, seconds_and_ms = value.strip().split(":", 2)
        seconds, milliseconds = seconds_and_ms.split(",", 1)
        minute_value = int(minutes)
        second_value = int(seconds)
        if minute_value >= 60 or second_value >= 60:
            raise ValueError("subtitle_timestamp_invalid")
        return (
            int(hours) * 3_600_000
            + minute_value * 60_000
            + second_value * 1_000
            + int(milliseconds)
        )

    cue_windows: list[dict[str, int]] = []
    try:
        for timing in timing_lines:
            start_text, end_text = re.split(r"\s+-->\s+", timing.strip(), maxsplit=1)
            start_ms = timestamp_ms(start_text)
            end_ms = timestamp_ms(end_text)
            if end_ms <= start_ms:
                return {"ok": False, "reason": "subtitle_timing_invalid"}
            cue_windows.append({"start_ms": start_ms, "end_ms": end_ms})
    except (TypeError, ValueError):
        return {"ok": False, "reason": "subtitle_timing_invalid"}
    return {
        "ok": True,
        "reason": "",
        "cue_count": len(cue_windows),
        "cue_windows": cue_windows,
    }


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
