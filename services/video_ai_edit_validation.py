"""Input preprocessing and final artifact safety for AI Video Editing."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from services import video_local_validation


AI_EDIT_ALLOWED_INPUTS = frozenset({".mp4", ".mov", ".mkv", ".webm"})
AI_EDIT_ALLOWED_OUTPUTS = frozenset({".mp4"})
AI_EDIT_FORBIDDEN = frozenset({".db", ".sqlite", ".sqlite3", ".env", ".log", ".bak"})
DEFAULT_GENERATIVE_DURATION_SECONDS = 8
MAX_GENERATIVE_DURATION_SECONDS = 120


class AiEditValidationError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _env_int(env: dict[str, str] | os._Environ[str], name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(env.get(name, default) or default).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def ai_edit_limits(env: dict[str, str] | os._Environ[str] | None = None) -> dict[str, Any]:
    source = env if env is not None else os.environ
    return {
        "upload_limit_bytes": _env_int(source, "VIDEO_AI_EDIT_MAX_UPLOAD_BYTES", video_local_validation.MAX_UPLOAD_BYTES, 1024 * 1024, 2 * 1024 * 1024 * 1024),
        "local_duration_limit_seconds": _env_int(source, "VIDEO_AI_EDIT_LOCAL_MAX_DURATION_SECONDS", video_local_validation.MAX_DURATION_SECONDS, 10, 12 * 60 * 60),
        "generative_duration_limit_seconds": _env_int(source, "VIDEO_AI_EDIT_GENERATIVE_MAX_DURATION_SECONDS", DEFAULT_GENERATIVE_DURATION_SECONDS, 1, MAX_GENERATIVE_DURATION_SECONDS),
        "max_width": _env_int(source, "VIDEO_AI_EDIT_MAX_WIDTH", 1920, 320, 3840),
        "max_height": _env_int(source, "VIDEO_AI_EDIT_MAX_HEIGHT", 1920, 320, 3840),
        "target_fps": _env_int(source, "VIDEO_AI_EDIT_TARGET_FPS", 30, 12, 60),
    }


def safe_output_name(job_id: Any) -> str:
    clean = re.sub(r"[^A-Za-z0-9_-]+", "-", str(job_id or "").strip())[:80].strip("-")
    if not clean:
        raise AiEditValidationError("job_id_required")
    return f"toan_aas_ai_edit_{clean}.mp4"


def artifact_delivery_allowed(path: str | os.PathLike[str], *, workspace: str | os.PathLike[str]) -> bool:
    target = Path(path).resolve(strict=False)
    base = Path(workspace).resolve(strict=False)
    suffix = target.suffix.lower()
    return bool(
        target != base
        and base in target.parents
        and target.is_file()
        and not target.is_symlink()
        and suffix in AI_EDIT_ALLOWED_OUTPUTS
        and suffix not in AI_EDIT_FORBIDDEN
        and "backup" not in target.name.lower()
    )


def validate_input_metadata(
    metadata: dict[str, Any],
    *,
    file_size: int = 0,
    lane: str = "local",
    target_duration_seconds: int = 0,
    env: dict[str, str] | os._Environ[str] | None = None,
) -> dict[str, Any]:
    values = dict(metadata or {})
    limits = ai_edit_limits(env)
    size = int(file_size or values.get("bytes") or 0)
    duration = float(values.get("duration") or 0)
    if size <= 0:
        return {**values, "ok": False, "reason": "input_zero_bytes"}
    if size > limits["upload_limit_bytes"]:
        return {**values, "ok": False, "reason": "video_too_large", "limit_bytes": limits["upload_limit_bytes"]}
    if not values.get("ok") or not values.get("has_video"):
        return {**values, "ok": False, "reason": str(values.get("reason") or "invalid_video")}
    if lane == "generative":
        requested = int(target_duration_seconds or round(duration) or 0)
        maximum = int(limits["generative_duration_limit_seconds"])
        if requested > maximum or duration > maximum + 0.25:
            return {
                **values,
                "ok": False,
                "reason": "duration_limit_action_required",
                "duration_limit_seconds": maximum,
                "action": f"shorten_to_{maximum}_seconds_or_choose_local",
            }
    elif duration > int(limits["local_duration_limit_seconds"]):
        return {**values, "ok": False, "reason": "duration_too_long", "duration_limit_seconds": limits["local_duration_limit_seconds"]}
    return {**values, "ok": True, "reason": "", "limits": limits}


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _scale_filter(max_width: int, max_height: int) -> str:
    return (
        f"scale='min(iw,{max_width})':'min(ih,{max_height})':force_original_aspect_ratio=decrease,"
        "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1"
    )


def build_preprocess_command(
    source_path: str,
    output_path: str,
    *,
    ffmpeg_path: str,
    target_duration_seconds: int,
    preserve_audio: bool,
    max_width: int,
    max_height: int,
    target_fps: int,
) -> list[str]:
    command = [ffmpeg_path, "-y", "-i", source_path]
    if target_duration_seconds > 0:
        command.extend(["-t", str(int(target_duration_seconds))])
    command.extend([
        "-vf", _scale_filter(max_width, max_height),
        "-r", str(int(target_fps)),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
    ])
    if preserve_audio:
        command.extend(["-c:a", "aac", "-b:a", "160k"])
    else:
        command.append("-an")
    command.extend(["-movflags", "+faststart", output_path])
    return command


def preprocess_source_video(
    source_path: str,
    output_path: str,
    *,
    workspace: str | os.PathLike[str],
    ffmpeg_path: str,
    ffprobe_path: str,
    target_duration_seconds: int,
    preserve_audio: bool,
    env: dict[str, str] | os._Environ[str] | None = None,
    timeout: int = 600,
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    base = Path(workspace).resolve(strict=False)
    source = Path(source_path).resolve(strict=False)
    output = Path(output_path).resolve(strict=False)
    if source == base or base not in source.parents or output == base or base not in output.parents:
        raise AiEditValidationError("path_outside_workspace")
    if source.suffix.lower() not in AI_EDIT_ALLOWED_INPUTS or output.suffix.lower() != ".mp4":
        raise AiEditValidationError("unsupported_file_type")
    probe = video_local_validation.probe_video_file(source, ffprobe_path=ffprobe_path)
    validation = validate_input_metadata(
        probe,
        file_size=source.stat().st_size if source.is_file() else 0,
        lane="generative",
        target_duration_seconds=target_duration_seconds,
        env=env,
    )
    if not validation.get("ok"):
        raise AiEditValidationError(str(validation.get("reason") or "invalid_video"))
    limits = ai_edit_limits(env)
    command = build_preprocess_command(
        str(source), str(output), ffmpeg_path=ffmpeg_path,
        target_duration_seconds=target_duration_seconds,
        preserve_audio=preserve_audio,
        max_width=int(limits["max_width"]), max_height=int(limits["max_height"]),
        target_fps=int(limits["target_fps"]),
    )
    try:
        result = runner(command, capture_output=True, text=True, timeout=max(30, int(timeout)), check=False)
    except subprocess.TimeoutExpired as exc:
        raise AiEditValidationError("preprocess_timeout") from exc
    except (OSError, ValueError) as exc:
        raise AiEditValidationError(f"preprocess_exec_failed:{type(exc).__name__}") from exc
    if int(getattr(result, "returncode", 1)) != 0:
        raise AiEditValidationError("preprocess_failed")
    expected_ms = int(target_duration_seconds or round(float(probe.get("duration") or 0))) * 1000
    output_validation = video_local_validation.validate_mp4_output(
        output,
        expected_duration_ms=expected_ms,
        tolerance_ms=max(1500, int(expected_ms * 0.15)) if expected_ms else None,
        require_audio=bool(preserve_audio and probe.get("has_audio")),
        ffprobe_path=ffprobe_path,
    )
    if not output_validation.get("ok"):
        raise AiEditValidationError(str(output_validation.get("reason") or "preprocessed_input_invalid"))
    video_local_validation.enforce_workspace_limit(base)
    return {
        "ok": True,
        "path": str(output),
        "metadata": output_validation,
        "command_uses_shell": False,
        "source_hash": sha256_file(source),
        "preprocessed_hash": sha256_file(output),
    }


def validate_final_edited_mp4(
    output_path: str | os.PathLike[str],
    *,
    source_path: str | os.PathLike[str],
    workspace: str | os.PathLike[str],
    requested_duration_seconds: int = 0,
    ffprobe_path: str = "",
) -> dict[str, Any]:
    if not artifact_delivery_allowed(output_path, workspace=workspace):
        return {"ok": False, "reason": "forbidden_delivery_artifact"}
    expected_ms = max(0, int(requested_duration_seconds or 0) * 1000)
    validation = video_local_validation.validate_mp4_output(
        output_path,
        expected_duration_ms=expected_ms,
        tolerance_ms=max(2000, int(expected_ms * 0.25)) if expected_ms else None,
        ffprobe_path=ffprobe_path,
    )
    if not validation.get("ok"):
        return validation
    try:
        source_hash = sha256_file(source_path)
        output_hash = sha256_file(output_path)
    except OSError as exc:
        return {**validation, "ok": False, "reason": f"hash_failed:{type(exc).__name__}"}
    if source_hash == output_hash:
        return {
            **validation,
            "ok": False,
            "reason": "original_input_returned_as_edit",
            "source_hash": source_hash,
            "output_hash": output_hash,
        }
    return {
        **validation,
        "ok": True,
        "reason": "",
        "source_hash": source_hash,
        "output_hash": output_hash,
        "artifact_size": Path(output_path).stat().st_size,
    }


__all__ = [
    "AiEditValidationError", "ai_edit_limits", "artifact_delivery_allowed",
    "build_preprocess_command", "preprocess_source_video", "safe_output_name",
    "sha256_file", "validate_final_edited_mp4", "validate_input_metadata",
]
