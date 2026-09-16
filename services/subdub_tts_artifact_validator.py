from __future__ import annotations

import glob
import json
import math
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


STATUS_VALID = "VALID"
STATUS_INVALID_CONTAINER = "INVALID_CONTAINER"
STATUS_DECODE_FAILED = "DECODE_FAILED"
STATUS_ZERO_OR_INVALID_DURATION = "ZERO_OR_INVALID_DURATION"
STATUS_EMPTY_AUDIO = "EMPTY_AUDIO"
STATUS_CONTRACT_MISMATCH = "CONTRACT_MISMATCH"


@dataclass(frozen=True)
class TTSArtifactValidationResult:
    ok: bool
    status: str
    detail: str = ""
    duration: float = 0.0
    size_bytes: int = 0
    container: str = ""
    codec: str = ""
    channels: int = 0
    sample_rate: int = 0


def resolve_ffmpeg_path(configured: str = "") -> str:
    env_path = str(configured or os.environ.get("FFMPEG_PATH") or os.environ.get("LOCAL_FFMPEG_PATH") or "").strip()
    if env_path and (os.path.isfile(env_path) or shutil.which(env_path)):
        return env_path
    direct = shutil.which("ffmpeg")
    if direct:
        return direct
    standard_linux = ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg"]
    for p in standard_linux:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    # Windows winget / common paths
    app_data = os.environ.get("LOCALAPPDATA", "")
    if app_data:
        matches = glob.glob(os.path.join(app_data, "Microsoft", "WinGet", "Packages", "**", "ffmpeg.exe"), recursive=True)
        if matches:
            return matches[0]
    return ""


def resolve_ffprobe_path(configured: str = "", ffmpeg_path: str = "") -> str:
    env_path = str(configured or os.environ.get("FFPROBE_PATH") or os.environ.get("LOCAL_FFPROBE_PATH") or "").strip()
    if env_path and (os.path.isfile(env_path) or shutil.which(env_path)):
        return env_path
    f_path = ffmpeg_path or resolve_ffmpeg_path()
    if f_path:
        ffmpeg_file = Path(f_path)
        probe_name = "ffprobe.exe" if ffmpeg_file.suffix.lower() == ".exe" else "ffprobe"
        sibling = ffmpeg_file.with_name(probe_name)
        if sibling.is_file():
            return str(sibling)
    direct = shutil.which("ffprobe")
    if direct:
        return direct
    standard_linux = ["/usr/bin/ffprobe", "/usr/local/bin/ffprobe"]
    for p in standard_linux:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    app_data = os.environ.get("LOCALAPPDATA", "")
    if app_data:
        matches = glob.glob(os.path.join(app_data, "Microsoft", "WinGet", "Packages", "**", "ffprobe.exe"), recursive=True)
        if matches:
            return matches[0]
    return ""


def validate_tts_audio_artifact(
    artifact_path: str | os.PathLike[str],
    *,
    expected_container: str = "mp3",
    expected_codec: str = "mp3",
    min_duration: float = 0.01,
    max_duration: float = 3600.0,
    min_bytes: int = 16,
    ffmpeg_bin: str = "",
    ffprobe_bin: str = "",
) -> TTSArtifactValidationResult:
    target_path = Path(str(artifact_path or "")).expanduser()
    if not target_path.exists() or not target_path.is_file():
        return TTSArtifactValidationResult(
            ok=False,
            status=STATUS_EMPTY_AUDIO,
            detail=f"file_missing_or_not_file:{target_path}",
        )

    try:
        size = target_path.stat().st_size
    except OSError as exc:
        return TTSArtifactValidationResult(
            ok=False,
            status=STATUS_EMPTY_AUDIO,
            detail=f"stat_failed:{type(exc).__name__}",
        )

    if size < max(1, int(min_bytes or 1)):
        return TTSArtifactValidationResult(
            ok=False,
            status=STATUS_EMPTY_AUDIO,
            size_bytes=size,
            detail=f"size_{size}_less_than_{min_bytes}",
        )

    # Inspect initial bytes to reject non-audio payloads immediately
    try:
        with open(target_path, "rb") as f:
            header_sample = f.read(96).lstrip().lower()
            if header_sample.startswith((b"{", b"[", b"<html", b"<!doctype")):
                return TTSArtifactValidationResult(
                    ok=False,
                    status=STATUS_INVALID_CONTAINER,
                    size_bytes=size,
                    detail="text_or_json_payload_instead_of_audio",
                )
    except OSError as exc:
        return TTSArtifactValidationResult(
            ok=False,
            status=STATUS_EMPTY_AUDIO,
            size_bytes=size,
            detail=f"read_failed:{type(exc).__name__}",
        )

    probe_path = resolve_ffprobe_path(ffprobe_bin)
    f_path = resolve_ffmpeg_path(ffmpeg_bin)
    if not probe_path or not f_path:
        raise RuntimeError(
            f"media_validation_binaries_unavailable: ffprobe={probe_path!r}, ffmpeg={f_path!r}"
        )

    # Step 1: Probe container and audio stream with ffprobe
    probe_cmd = [
        probe_path,
        "-v", "error",
        "-show_entries", "stream=codec_name,codec_type,channels,sample_rate,duration",
        "-show_entries", "format=format_name,duration",
        "-of", "json",
        str(target_path),
    ]
    try:
        probe_proc = subprocess.run(
            probe_cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return TTSArtifactValidationResult(
            ok=False,
            status=STATUS_INVALID_CONTAINER,
            size_bytes=size,
            detail="ffprobe_timeout",
        )
    except Exception as exc:
        return TTSArtifactValidationResult(
            ok=False,
            status=STATUS_INVALID_CONTAINER,
            size_bytes=size,
            detail=f"ffprobe_exec_error:{type(exc).__name__}:{exc}",
        )

    if probe_proc.returncode != 0:
        err_msg = probe_proc.stderr.decode("utf-8", errors="ignore").strip()[:200]
        return TTSArtifactValidationResult(
            ok=False,
            status=STATUS_INVALID_CONTAINER,
            size_bytes=size,
            detail=f"ffprobe_probe_failed:{err_msg}",
        )

    try:
        probe_data = json.loads(probe_proc.stdout.decode("utf-8", errors="ignore"))
    except Exception as exc:
        return TTSArtifactValidationResult(
            ok=False,
            status=STATUS_INVALID_CONTAINER,
            size_bytes=size,
            detail=f"ffprobe_json_parse_error:{type(exc).__name__}",
        )

    fmt_info = probe_data.get("format") or {}
    format_name = str(fmt_info.get("format_name") or "").lower()

    if expected_container:
        exp_c = expected_container.lower().strip(".")
        format_tokens = [t.strip() for t in format_name.split(",") if t.strip()]
        if exp_c not in format_tokens and exp_c not in format_name:
            return TTSArtifactValidationResult(
                ok=False,
                status=STATUS_INVALID_CONTAINER,
                size_bytes=size,
                container=format_name,
                detail=f"container_mismatch:{format_name}!={expected_container}",
            )

    streams = probe_data.get("streams") or []
    audio_stream = None
    for st in streams:
        if str(st.get("codec_type") or "").lower() == "audio":
            audio_stream = st
            break

    if not audio_stream:
        return TTSArtifactValidationResult(
            ok=False,
            status=STATUS_CONTRACT_MISMATCH,
            size_bytes=size,
            container=format_name,
            detail="no_audio_stream_found",
        )

    codec_name = str(audio_stream.get("codec_name") or "").lower()
    channels = int(audio_stream.get("channels") or 0)
    sample_rate = int(audio_stream.get("sample_rate") or 0)

    if expected_codec:
        exp_codec = expected_codec.lower().strip()
        acceptable = {exp_codec}
        if exp_codec == "mp3":
            acceptable.add("mp3float")
        if codec_name not in acceptable:
            return TTSArtifactValidationResult(
                ok=False,
                status=STATUS_CONTRACT_MISMATCH,
                size_bytes=size,
                container=format_name,
                codec=codec_name,
                channels=channels,
                sample_rate=sample_rate,
                detail=f"codec_mismatch:{codec_name}!={expected_codec}",
            )

    # Step 2: Full decode to null with ffmpeg
    decode_cmd = [
        f_path,
        "-v", "error",
        "-xerror",
        "-i", str(target_path),
        "-f", "null",
        "-",
    ]
    try:
        decode_proc = subprocess.run(
            decode_cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return TTSArtifactValidationResult(
            ok=False,
            status=STATUS_DECODE_FAILED,
            size_bytes=size,
            container=format_name,
            codec=codec_name,
            channels=channels,
            sample_rate=sample_rate,
            detail="decode_timeout",
        )
    except Exception as exc:
        return TTSArtifactValidationResult(
            ok=False,
            status=STATUS_DECODE_FAILED,
            size_bytes=size,
            container=format_name,
            codec=codec_name,
            channels=channels,
            sample_rate=sample_rate,
            detail=f"decode_exec_error:{type(exc).__name__}",
        )

    if decode_proc.returncode != 0:
        decode_err = decode_proc.stderr.decode("utf-8", errors="ignore").strip()[:240]
        return TTSArtifactValidationResult(
            ok=False,
            status=STATUS_DECODE_FAILED,
            size_bytes=size,
            container=format_name,
            codec=codec_name,
            channels=channels,
            sample_rate=sample_rate,
            detail=f"decode_failed:{decode_err}",
        )

    # Step 3: Bitstream duration validation
    dur_raw = audio_stream.get("duration") or fmt_info.get("duration")
    try:
        duration_val = float(dur_raw or 0.0)
    except (ValueError, TypeError):
        duration_val = 0.0

    if (
        math.isnan(duration_val)
        or math.isinf(duration_val)
        or duration_val < min_duration
        or duration_val > max_duration
    ):
        return TTSArtifactValidationResult(
            ok=False,
            status=STATUS_ZERO_OR_INVALID_DURATION,
            size_bytes=size,
            duration=duration_val,
            container=format_name,
            codec=codec_name,
            channels=channels,
            sample_rate=sample_rate,
            detail=f"invalid_duration:{duration_val}",
        )

    return TTSArtifactValidationResult(
        ok=True,
        status=STATUS_VALID,
        detail="validated",
        duration=round(duration_val, 4),
        size_bytes=size,
        container=format_name,
        codec=codec_name,
        channels=channels,
        sample_rate=sample_rate,
    )
