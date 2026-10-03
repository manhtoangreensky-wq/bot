"""Authoritative video reference packaging service for reference-guided I2V hybrid execution.

Converts a customer source video reference into a validated, deterministic package
of reference frames for Image-to-Video providers (Google Veo / ShopAIKey / Key4U),
ensuring zero local filesystem paths or raw MP4 files leak to remote provider wires.

Enforces:
1. Strict real video validation via ffprobe (stream count >= 1, codec present, width/height > 0, duration > 0).
2. Fail-closed on corrupt or unprobeable video (no synthetic/mock bypass).
3. Deterministic start/end or nearest-valid real frame extraction with local decode validation.
4. Exactly 2 reference frames: start_reference and end_reference.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Mapping

try:
    from PIL import Image
except ImportError:
    Image = None

logger = logging.getLogger(__name__)

ALLOWED_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm"})


class VideoReferencePackageError(Exception):
    """Base error for video reference packaging."""


class VideoReferenceValidationError(VideoReferencePackageError):
    """Raised when source video validation fails."""


class VideoReferenceExtractionError(VideoReferencePackageError):
    """Raised when frame extraction fails."""


def compute_file_sha256(path: Path | str) -> str:
    """Computes SHA-256 digest of a file in streaming chunks."""
    target = Path(path)
    digest = hashlib.sha256()
    with open(target, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_source_video_metadata(source_video_path: str | Path) -> dict[str, Any]:
    """Probes source video stream using ffprobe.
    
    Fails closed if ffprobe is absent, fails, has no video stream,
    or has invalid dimensions/duration.
    """
    target = Path(source_video_path)
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        raise VideoReferenceValidationError(
            f"FFPROBE_NOT_AVAILABLE: ffprobe executable required to probe {target.name}"
        )

    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,duration",
        "-show_entries", "format=duration",
        "-of", "json",
        str(target.resolve()),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except Exception as exc:
        raise VideoReferenceValidationError(
            f"FFPROBE_EXECUTION_ERROR: {exc}"
        ) from exc

    if res.returncode != 0:
        err_msg = res.stderr.strip() or "ffprobe process failed"
        raise VideoReferenceValidationError(f"FFPROBE_FAILED: {err_msg}")

    try:
        data = json.loads(res.stdout)
    except Exception as exc:
        raise VideoReferenceValidationError(
            f"FFPROBE_JSON_PARSE_ERROR: {exc}"
        ) from exc

    streams = data.get("streams") or []
    if not streams:
        raise VideoReferenceValidationError(
            f"NO_VIDEO_STREAM: No video stream found in {target.name}"
        )

    vstream = streams[0]
    codec = str(vstream.get("codec_name") or "").strip()
    if not codec:
        raise VideoReferenceValidationError(
            f"NO_VIDEO_CODEC: Video stream in {target.name} has no recognized codec"
        )

    try:
        width = int(vstream.get("width") or 0)
        height = int(vstream.get("height") or 0)
    except (ValueError, TypeError):
        width, height = 0, 0
    if width <= 0 or height <= 0:
        raise VideoReferenceValidationError(
            f"INVALID_VIDEO_DIMENSIONS: {width}x{height} in {target.name}"
        )

    dur_val = vstream.get("duration") or (data.get("format") or {}).get("duration")
    try:
        duration_sec = float(dur_val or 0.0)
    except (ValueError, TypeError):
        duration_sec = 0.0

    if duration_sec <= 0.0:
        raise VideoReferenceValidationError(
            f"INVALID_VIDEO_DURATION: Probed duration {duration_sec}s must be > 0"
        )

    return {
        "codec": codec,
        "width": width,
        "height": height,
        "duration_seconds": round(duration_sec, 3),
    }


def validate_source_video(source_video_path: str | Path) -> dict[str, Any]:
    """Strictly validates source video existence, non-emptiness, extension, and real decodable stream."""
    if not source_video_path:
        raise VideoReferenceValidationError("MISSING_SOURCE_VIDEO_PATH: source_video_path is required")

    target = Path(source_video_path)
    if not target.exists():
        raise VideoReferenceValidationError(f"SOURCE_VIDEO_NOT_FOUND: {target}")
    if not target.is_file():
        raise VideoReferenceValidationError(f"SOURCE_VIDEO_NOT_A_FILE: {target}")

    ext = target.suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise VideoReferenceValidationError(
            f"INVALID_VIDEO_EXTENSION: {ext} not in {sorted(ALLOWED_VIDEO_EXTENSIONS)}"
        )

    file_size = target.stat().st_size
    if file_size <= 0:
        raise VideoReferenceValidationError(f"SOURCE_VIDEO_EMPTY: {target}")

    source_sha256 = compute_file_sha256(target)
    probe_info = probe_source_video_metadata(target)

    return {
        "ok": True,
        "source_video_path": str(target.resolve()),
        "source_video_name": target.name,
        "source_video_sha256": source_sha256,
        "file_size": file_size,
        "duration_seconds": probe_info["duration_seconds"],
        "width": probe_info["width"],
        "height": probe_info["height"],
        "codec": probe_info["codec"],
        "extension": ext,
    }


def probe_video_duration(source_video_path: str | Path) -> float:
    """Convenience probe returning probed duration in seconds or raising VideoReferenceValidationError."""
    meta = validate_source_video(source_video_path)
    return float(meta["duration_seconds"])


def is_valid_decoded_image(frame_path: Path) -> tuple[bool, int, int]:
    """Validates that extracted image file decodes cleanly and is not blank/empty."""
    if not frame_path.exists() or frame_path.stat().st_size <= 0:
        return False, 0, 0

    if Image is not None:
        try:
            with Image.open(frame_path) as img:
                img.verify()
            with Image.open(frame_path) as img:
                w, h = img.size
                if w <= 0 or h <= 0:
                    return False, 0, 0
                extrema = img.getextrema()
                if isinstance(extrema[0], tuple):
                    max_val = max(band[1] for band in extrema)
                else:
                    max_val = extrema[1]
                if max_val < 8:  # Effectively pure black / corrupt
                    return False, w, h
                return True, w, h
        except Exception as exc:
            logger.debug("Image validation failed for %s: %s", frame_path, exc)
            return False, 0, 0

    # Fallback to ffprobe if PIL is not installed
    ffprobe_bin = shutil.which("ffprobe")
    if ffprobe_bin:
        try:
            cmd = [
                ffprobe_bin,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json",
                str(frame_path.resolve()),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                streams = data.get("streams") or []
                if streams:
                    w = int(streams[0].get("width") or 0)
                    h = int(streams[0].get("height") or 0)
                    if w > 0 and h > 0:
                        return True, w, h
        except Exception:
            pass

    return False, 0, 0


def extract_deterministic_reference_frames(
    source_video_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    duration: float | None = None,
) -> list[dict[str, Any]]:
    """Extracts exactly 2 deterministic reference frames using start/end-or-nearest-valid policy.

    Role 1: start_reference (canonical 0.0s, with nearest fallback: 0.05s, 0.1s, 0.2s, 0.5s, 1.0s)
    Role 2: end_reference (canonical duration-0.1s, with nearest fallback: -0.05s, -0.1s, -0.2s, -0.5s)

    Fails closed if no real decoded frame can be extracted. Zero synthetic fallback.
    """
    target = Path(source_video_path)
    val_info = validate_source_video(target)
    source_dur = float(val_info["duration_seconds"])
    dur = min(float(duration), source_dur) if (duration is not None and duration > 0.0) else source_dur

    if output_dir is not None:
        out_root = Path(output_dir)
        out_root.mkdir(parents=True, exist_ok=True)
    else:
        out_root = Path(tempfile.mkdtemp(prefix="toanaas_ref_frames_"))

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise VideoReferenceExtractionError("FFMPEG_NOT_AVAILABLE: ffmpeg is required for frame extraction")

    # Roles and deterministic candidate timestamp search lists
    start_candidates = [0.0, 0.05, 0.1, 0.2, 0.5, 1.0]
    start_candidates = [ts for ts in start_candidates if ts < dur]
    if not start_candidates:
        start_candidates = [0.0]

    canonical_end = max(0.1, round(dur - 0.1, 3))
    end_candidates = [
        canonical_end,
        round(canonical_end - 0.05, 3),
        round(canonical_end - 0.1, 3),
        round(canonical_end - 0.2, 3),
        round(canonical_end - 0.5, 3),
    ]
    end_candidates = sorted(list({ts for ts in end_candidates if ts >= 0.05}), reverse=True)
    if not end_candidates:
        end_candidates = [canonical_end]

    role_specs = [
        (1, "start_reference", start_candidates),
        (2, "end_reference", end_candidates),
    ]

    extracted_frames: list[dict[str, Any]] = []

    for idx, role, candidates in role_specs:
        valid_frame = None
        for cand_ts in candidates:
            frame_filename = f"frame_{idx}_{role}_{cand_ts:.3f}s.jpg"
            frame_path = out_root / frame_filename

            cmd = [
                ffmpeg_bin,
                "-y",
                "-ss", f"{cand_ts:.3f}",
                "-i", str(target.resolve()),
                "-update", "1",
                "-frames:v", "1",
                "-q:v", "2",
                str(frame_path.resolve()),
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                if res.returncode == 0:
                    ok, w, h = is_valid_decoded_image(frame_path)
                    if ok:
                        valid_frame = {
                            "frame_index": idx,
                            "role": role,
                            "timestamp_seconds": cand_ts,
                            "frame_path": str(frame_path.resolve()),
                            "frame_filename": frame_filename,
                            "frame_sha256": compute_file_sha256(frame_path),
                            "file_size": frame_path.stat().st_size,
                            "width": w,
                            "height": h,
                        }
                        break
            except Exception as exc:
                logger.debug("ffmpeg extraction error for %s at %.3fs: %s", target, cand_ts, exc)

        if not valid_frame:
            raise VideoReferenceExtractionError(
                f"FAIL_CLOSED_REFERENCE_EXTRACTION: Unable to extract real valid frame for {role} from {target.name}"
            )

        extracted_frames.append(valid_frame)

    return extracted_frames


def build_reference_prompt_context(
    user_prompt: str,
    *,
    reference_package: Mapping[str, Any] | None = None,
) -> tuple[str, str]:
    """Preserves user prompt authority and generates deterministic prompt SHA256."""
    clean_prompt = str(user_prompt or "").strip()
    prompt_sha256 = hashlib.sha256(clean_prompt.encode("utf-8")).hexdigest()
    return clean_prompt, prompt_sha256


def create_video_reference_package(
    source_video_path: str | Path,
    user_prompt: str,
    *,
    output_dir: str | Path | None = None,
    duration: float | None = None,
) -> dict[str, Any]:
    """Authoritative builder for video reference guided I2V hybrid package."""
    video_meta = validate_source_video(source_video_path)
    source_dur = float(video_meta["duration_seconds"])
    package_dur = float(duration if duration is not None and duration > 0.0 else source_dur)

    frames = extract_deterministic_reference_frames(
        source_video_path=video_meta["source_video_path"],
        output_dir=output_dir,
        duration=source_dur,
    )

    clean_prompt, prompt_sha256 = build_reference_prompt_context(user_prompt)

    return {
        "execution_mode": "video_reference_guided_i2v",
        "source_input_kind": "video",
        "source_video_path": video_meta["source_video_path"],
        "source_video_name": video_meta["source_video_name"],
        "source_video_sha256": video_meta["source_video_sha256"],
        "duration_seconds": package_dur,
        "source_duration_seconds": source_dur,
        "width": video_meta["width"],
        "height": video_meta["height"],
        "codec": video_meta["codec"],
        "frames": frames,
        "frame_paths": [f["frame_path"] for f in frames],
        "frame_count": len(frames),
        "frame_1_sha256": frames[0]["frame_sha256"],
        "frame_1_timestamp": frames[0]["timestamp_seconds"],
        "frame_2_sha256": frames[1]["frame_sha256"],
        "frame_2_timestamp": frames[1]["timestamp_seconds"],
        "user_prompt": clean_prompt,
        "prompt_sha256": prompt_sha256,
        "effective_prompt": clean_prompt,
        "native_v2v": False,
        "native_v2v_enabled": False,
    }
