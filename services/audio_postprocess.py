from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence


@dataclass(frozen=True)
class AudioBoostResult:
    ok: bool
    input_path: str = ""
    output_path: str = ""
    output_bytes: int = 0
    boosted: bool = False
    fallback_original: bool = False
    skipped_double_boost: bool = False
    factor: float = 2.0
    detail: str = ""


def boosted_output_path(path: str | Path) -> Path:
    target = Path(path)
    if target.stem.endswith("_boosted"):
        return target
    return target.with_name(f"{target.stem}_boosted{target.suffix or '.mp3'}")


def audio_is_marked_boosted(path: str | Path) -> bool:
    return Path(path).stem.endswith("_boosted")


def _find_ffmpeg(explicit_path: str | None = None) -> str:
    for candidate in (explicit_path, os.getenv("FFMPEG_PATH"), os.getenv("FFMPEG_BINARY"), shutil.which("ffmpeg")):
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


def _copy_original(input_path: Path, output_path: Path, *, detail: str, skipped_double_boost: bool = False, factor: float = 2.0) -> AudioBoostResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if input_path.resolve() != output_path.resolve():
        shutil.copyfile(input_path, output_path)
    output_bytes = int(output_path.stat().st_size if output_path.exists() else input_path.stat().st_size)
    return AudioBoostResult(
        ok=output_bytes > 0,
        input_path=str(input_path),
        output_path=str(output_path),
        output_bytes=output_bytes,
        boosted=False,
        fallback_original=True,
        skipped_double_boost=skipped_double_boost,
        factor=float(factor),
        detail=detail,
    )


def _return_code(result: Any) -> int:
    if result is True or result is None:
        return 0
    if result is False:
        return 1
    try:
        return int(getattr(result, "returncode"))
    except Exception:
        return 1


def boost_voice_audio(
    input_path: str,
    output_path: str,
    *,
    volume_factor: float = 2.0,
    limiter: bool = True,
    ffmpeg_path: str | None = None,
    run_command_func: Callable[[Sequence[str]], Any] | None = None,
) -> AudioBoostResult:
    source = Path(str(input_path or ""))
    target = Path(str(output_path or ""))
    try:
        requested_factor = float(volume_factor)
    except Exception:
        requested_factor = 2.0
    factor = max(0.0, min(8.0, requested_factor))
    if not source.exists() or not source.is_file() or int(source.stat().st_size or 0) <= 0:
        return AudioBoostResult(False, input_path=str(source), output_path=str(target), factor=factor, detail="input_missing_or_empty")
    if not str(target):
        target = boosted_output_path(source)
    if audio_is_marked_boosted(source):
        return _copy_original(source, target, detail="already_boosted", skipped_double_boost=True, factor=factor)
    ffmpeg = _find_ffmpeg(ffmpeg_path)
    if not ffmpeg:
        return _copy_original(source, target, detail="ffmpeg_unavailable", factor=factor)
    target.parent.mkdir(parents=True, exist_ok=True)
    actual_target = target
    temp_target = None
    if source.resolve() == target.resolve():
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=target.suffix or ".mp3")
        temp_target = Path(handle.name)
        handle.close()
        actual_target = temp_target
    audio_filter = f"volume={factor:.3f}"
    if limiter:
        audio_filter += ",alimiter=limit=0.95"
    command: list[str] = [ffmpeg, "-y", "-i", str(source), "-af", audio_filter, "-vn"]
    if (actual_target.suffix or target.suffix).lower() == ".mp3":
        command.extend(["-c:a", "libmp3lame", "-b:a", "128k"])
    command.append(str(actual_target))
    try:
        if callable(run_command_func):
            completed = run_command_func(command)
        else:
            completed = subprocess.run(command, capture_output=True, timeout=45, check=False)
        if _return_code(completed) == 0 and actual_target.exists() and int(actual_target.stat().st_size or 0) > 0:
            if temp_target:
                shutil.move(str(actual_target), str(target))
            return AudioBoostResult(
                True,
                input_path=str(source),
                output_path=str(target),
                output_bytes=int(target.stat().st_size or 0),
                boosted=True,
                fallback_original=False,
                skipped_double_boost=False,
                factor=factor,
                detail="ok",
            )
    except Exception:
        pass
    finally:
        if temp_target and temp_target.exists():
            try:
                temp_target.unlink()
            except Exception:
                pass
    return _copy_original(source, target, detail="boost_failed_fallback_original", factor=factor)
