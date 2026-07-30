from __future__ import annotations

import inspect
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable


SYSTEM_DEFAULT_VOICE_ID = "female-shaonv"
SYSTEM_DEFAULT_MALE_VOICE_ID = "male-qn-qingse"
INVALID_REQUESTED_VOICE_IDS = {
    "",
    "-",
    "none",
    "null",
    "default",
    "default_female",
    "default_male",
    "default_neutral",
    "female",
    "male",
    "neutral",
}


class DubbingPipelineError(RuntimeError):
    """Clean internal exception for blackbox dubbing pipeline failures."""


def _validate_existing_file(path: str | os.PathLike[str], label: str) -> Path:
    value = Path(str(path or "")).expanduser()
    if not value.exists() or not value.is_file() or value.stat().st_size <= 0:
        raise DubbingPipelineError(f"{label}_missing_or_empty")
    return value.resolve()


def _ffmpeg_binary() -> str:
    for key in ("FFMPEG_PATH", "LOCAL_FFMPEG_PATH"):
        configured = str(os.getenv(key) or "").strip()
        if configured and Path(configured).exists():
            return configured
    discovered = shutil.which("ffmpeg")
    if discovered:
        return discovered
    raise DubbingPipelineError("ffmpeg_missing")


def _run_ffmpeg(command: list[str], *, cwd: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise DubbingPipelineError("ffmpeg_timeout") from exc
    except OSError as exc:
        raise DubbingPipelineError("ffmpeg_exec_failed") from exc


def _first_error_line(value: str) -> str:
    for line in str(value or "").replace("\r", "\n").split("\n"):
        clean = line.strip()
        if clean:
            return clean[:240]
    return ""


def _safe_audio_name(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in {".aac", ".m4a", ".mp3", ".wav", ".ogg", ".flac"}:
        suffix = ".mp3"
    return f"dub_audio{suffix}"


def mux_final_video(
    video_path: str,
    audio_path: str,
    output_path: str,
    srt_path: str | None = None,
    burn_subtitles: bool = False,
    replace_audio: bool = True,
) -> str:
    """Mux dubbed audio into a video, optionally burning subtitles, and return the MP4 path."""
    source_video = _validate_existing_file(video_path, "video")
    source_audio = _validate_existing_file(audio_path, "audio")
    subtitle_source: Path | None = None
    if srt_path and burn_subtitles:
        subtitle_source = _validate_existing_file(srt_path, "subtitle")
    output = Path(str(output_path or "")).expanduser()
    if not output.name:
        raise DubbingPipelineError("output_path_missing")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg_binary()
    staging_root = output.parent if output.parent.exists() else Path(tempfile.gettempdir())
    staging = Path(tempfile.mkdtemp(prefix="toanaas_mux_", dir=str(staging_root)))
    try:
        safe_video = staging / "input.mp4"
        safe_audio_name = _safe_audio_name(source_audio)
        safe_audio = staging / safe_audio_name
        safe_output = staging / "final.mp4"
        shutil.copyfile(source_video, safe_video)
        shutil.copyfile(source_audio, safe_audio)
        subtitle_filter = ""
        if subtitle_source:
            safe_subtitle = staging / "subtitle.srt"
            shutil.copyfile(subtitle_source, safe_subtitle)
            subtitle_filter = "subtitles=subtitle.srt"

        def build_command(video_codec: str) -> list[str]:
            command = [ffmpeg, "-y", "-i", "input.mp4", "-i", safe_audio_name]
            if subtitle_filter:
                command.extend(["-vf", subtitle_filter])
            command.extend(["-map", "0:v:0", "-map", "1:a:0"])
            if not replace_audio:
                command.extend(["-map", "0:a?", "-disposition:a:0", "default"])
            # The audio timeline is already bounded by the source video.  Let
            # the explicit stream maps and the source-duration contract decide
            # the boundary; shortest-stream truncation can cut a valid video.
            command.extend(["-c:v", video_codec, "-c:a", "aac", "-movflags", "+faststart", "final.mp4"])
            return command

        first_codec = "libx264" if subtitle_filter else "copy"
        result = _run_ffmpeg(build_command(first_codec), cwd=str(staging))
        if result.returncode != 0 and first_codec == "copy":
            result = _run_ffmpeg(build_command("libx264"), cwd=str(staging))
        if result.returncode != 0:
            detail = _first_error_line(result.stderr or result.stdout) or "ffmpeg_failed"
            raise DubbingPipelineError(f"ffmpeg_failed:{detail}")
        if not safe_output.exists() or safe_output.stat().st_size <= 0:
            raise DubbingPipelineError("mux_output_empty")
        shutil.copyfile(safe_output, output)
        if not output.exists() or output.stat().st_size <= 0:
            raise DubbingPipelineError("mux_output_verify_failed")
        return str(output)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def render_subtitled_video(
    source_video_path: str,
    subtitle_path: str,
    output_path: str,
    style_options: dict[str, Any] | None = None,
) -> str:
    """Burn subtitles into a source video and return the MP4 path."""
    source_video = _validate_existing_file(source_video_path, "video")
    subtitle_source = _validate_existing_file(subtitle_path, "subtitle")
    output = Path(str(output_path or "")).expanduser()
    if not output.name:
        raise DubbingPipelineError("output_path_missing")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg_binary()
    staging_root = output.parent if output.parent.exists() else Path(tempfile.gettempdir())
    staging = Path(tempfile.mkdtemp(prefix="toanaas_subtitle_video_", dir=str(staging_root)))
    try:
        safe_video = staging / "input.mp4"
        safe_subtitle = staging / "subtitle.srt"
        safe_output = staging / "final.mp4"
        shutil.copyfile(source_video, safe_video)
        shutil.copyfile(subtitle_source, safe_subtitle)
        style = dict(style_options or {})
        force_style = str(style.get("force_style") or "").strip()
        subtitle_filter = "subtitles=subtitle.srt"
        if force_style:
            subtitle_filter += f":force_style='{force_style}'"
        command = [
            ffmpeg,
            "-y",
            "-i",
            "input.mp4",
            "-vf",
            subtitle_filter,
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            "final.mp4",
        ]
        result = _run_ffmpeg(command, cwd=str(staging))
        if result.returncode != 0:
            detail = _first_error_line(result.stderr or result.stdout) or "ffmpeg_failed"
            raise DubbingPipelineError(f"ffmpeg_failed:{detail}")
        if not safe_output.exists() or safe_output.stat().st_size <= 0:
            raise DubbingPipelineError("subtitle_video_output_empty")
        shutil.copyfile(safe_output, output)
        if not output.exists() or output.stat().st_size <= 0:
            raise DubbingPipelineError("subtitle_video_verify_failed")
        return str(output)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def mux_dubbed_video(
    source_video_path: str,
    dub_audio_path: str,
    output_path: str,
    subtitle_path: str | None = None,
    burn_subtitle: bool = False,
) -> str:
    """Replace source audio with dubbed audio and optionally burn subtitles."""
    return mux_final_video(
        source_video_path,
        dub_audio_path,
        output_path,
        srt_path=subtitle_path,
        burn_subtitles=burn_subtitle,
        replace_audio=True,
    )


def process_final_video_product(
    *,
    mode: str,
    source_video_path: str,
    original_subtitle_path: str | None = None,
    translated_subtitle_path: str | None = None,
    dub_audio_path: str | None = None,
    logo_path: str | None = None,
    bgm_path: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Blackbox final-product file processor. It never imports chat framework code or charges Xu."""
    del logo_path, bgm_path
    selected_mode = str(mode or "").strip().lower()
    source_video = _validate_existing_file(source_video_path, "video")
    output = Path(str(output_path or source_video.with_name("toan_aas_final.mp4"))).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    subtitle_path = str(translated_subtitle_path or original_subtitle_path or "").strip()
    try:
        if selected_mode == "auto_subtitle_video":
            final_path = render_subtitled_video(str(source_video), str(original_subtitle_path or ""), str(output))
        elif selected_mode == "translated_subtitle_video":
            final_path = render_subtitled_video(str(source_video), str(translated_subtitle_path or ""), str(output))
        elif selected_mode == "dubbed_video":
            final_path = mux_dubbed_video(
                str(source_video),
                str(dub_audio_path or ""),
                str(output),
                subtitle_path=subtitle_path or None,
                burn_subtitle=False,
            )
        elif selected_mode == "subtitle_plus_dub_video":
            final_path = mux_dubbed_video(
                str(source_video),
                str(dub_audio_path or ""),
                str(output),
                subtitle_path=subtitle_path or None,
                burn_subtitle=bool(subtitle_path),
            )
        else:
            raise DubbingPipelineError("unknown_final_video_mode")
        return {
            "ok": True,
            "result_type": "mp4",
            "video_path": final_path,
            "audio_path": str(dub_audio_path or "") or None,
            "subtitle_path": subtitle_path or None,
            "fallback_reason": None,
        }
    except Exception as exc:
        if dub_audio_path and Path(str(dub_audio_path)).exists() and Path(str(dub_audio_path)).stat().st_size > 0:
            return {
                "ok": True,
                "result_type": "audio_fallback",
                "video_path": None,
                "audio_path": str(Path(str(dub_audio_path)).resolve()),
                "subtitle_path": subtitle_path or None,
                "fallback_reason": str(exc)[:240] or "mux_failed",
            }
        return {
            "ok": False,
            "result_type": "guard",
            "video_path": None,
            "audio_path": None,
            "subtitle_path": subtitle_path or None,
            "fallback_reason": str(exc)[:240] or type(exc).__name__,
        }


def _requested_voice_is_valid(value: str | None) -> bool:
    normalized = str(value or "").strip()
    if normalized.lower() in INVALID_REQUESTED_VOICE_IDS:
        return False
    return bool(re.search(r"[A-Za-z0-9]", normalized))


def get_user_voice_id(
    user_id: str,
    db_connection,
    requested_voice_id: str | None = None,
    default_voice_id: str | None = None,
) -> str:
    """Resolve a real provider voice id without creating or mutating profiles."""
    if _requested_voice_is_valid(requested_voice_id):
        return str(requested_voice_id or "").strip()
    fallback = str(default_voice_id or SYSTEM_DEFAULT_VOICE_ID or SYSTEM_DEFAULT_MALE_VOICE_ID).strip()
    try:
        cursor = db_connection.execute(
            """
            SELECT provider_voice_id FROM voice_profiles
            WHERE user_id=? AND is_default=1 AND status='active'
            ORDER BY id DESC
            LIMIT 1
            """,
            (str(user_id),),
        )
        row = cursor.fetchone()
        provider_voice_id = ""
        if row is not None:
            provider_voice_id = str(row[0] if not isinstance(row, dict) else row.get("provider_voice_id") or "").strip()
        if provider_voice_id:
            return provider_voice_id
    except Exception:
        return fallback
    return fallback


def _segment_seconds(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except Exception:
        return 0.0


def _srt_timestamp(seconds: float) -> str:
    millis = max(0, int(float(seconds or 0.0) * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _segment_text(segment: dict[str, Any]) -> str:
    for key in ("text", "translated_text", "caption", "content"):
        value = str(segment.get(key) or "").strip()
        if value:
            return value
    return ""


def _segments_to_srt(segments: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    cursor = 0.0
    for index, segment in enumerate(segments, start=1):
        text = _segment_text(segment)
        if not text:
            continue
        start = _segment_seconds(segment.get("start"))
        if start <= 0 and cursor > 0:
            start = cursor
        end = _segment_seconds(segment.get("end"))
        if end <= start:
            end = start + max(1.0, min(6.0, len(text.split()) / 2.5))
        cursor = end
        blocks.append(f"{index}\n{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n{text}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _bytes_from_tts_result(result: Any) -> bytes:
    if result is None:
        return b""
    if isinstance(result, (bytes, bytearray)):
        return bytes(result)
    if isinstance(result, dict):
        for key in ("audio_bytes", "bytes", "data", "audio"):
            value = result.get(key)
            if isinstance(value, (bytes, bytearray)):
                return bytes(value)
        chunks = result.get("chunks")
        if chunks:
            return b"".join(_bytes_from_tts_result(item) for item in chunks)
    if isinstance(result, (list, tuple)):
        return b"".join(_bytes_from_tts_result(item) for item in result)
    return b""


def _call_tts_func(tts_func: Callable[..., Any], segments: list[dict[str, Any]], voice_id: str, workspace_dir: str) -> bytes:
    if not callable(tts_func):
        raise DubbingPipelineError("tts_func_missing")
    attempts = (
        lambda: tts_func(segments, voice_id=voice_id, workspace_dir=workspace_dir),
        lambda: tts_func(segments, voice_id=voice_id),
        lambda: tts_func(segments, voice_id),
    )
    last_error: Exception | None = None
    result: Any = None
    for attempt in attempts:
        try:
            result = attempt()
            break
        except TypeError as exc:
            last_error = exc
    else:
        raise DubbingPipelineError("tts_call_failed") from last_error
    if inspect.isawaitable(result):
        raise DubbingPipelineError("tts_func_must_be_sync")
    audio = _bytes_from_tts_result(result)
    if audio:
        return audio
    chunks: list[bytes] = []
    for segment in segments:
        text = _segment_text(segment)
        if not text:
            continue
        for attempt in (
            lambda: tts_func(text, voice_id=voice_id),
            lambda: tts_func(text, voice_id),
            lambda: tts_func(text),
        ):
            try:
                item = attempt()
                if inspect.isawaitable(item):
                    raise DubbingPipelineError("tts_func_must_be_sync")
                chunk = _bytes_from_tts_result(item)
                if chunk:
                    chunks.append(chunk)
                    break
            except TypeError:
                continue
    return b"".join(chunks)


def _safe_workspace(workspace_dir: str) -> Path:
    workspace = Path(str(workspace_dir or "")).expanduser().resolve()
    if not workspace.name:
        raise DubbingPipelineError("workspace_missing")
    anchors = {Path(workspace.anchor).resolve()} if workspace.anchor else set()
    protected = {Path.home().resolve(), Path.cwd().resolve(), Path(tempfile.gettempdir()).resolve(), *anchors}
    if workspace in protected:
        raise DubbingPipelineError("unsafe_workspace")
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def process_dubbing_pipeline(
    *,
    source_video_path: str | None,
    subtitle_segments: list[dict],
    voice_id: str,
    workspace_dir: str,
    tts_func,
    burn_subtitles: bool = False,
    final_only: bool = True,
) -> dict:
    workspace = _safe_workspace(workspace_dir)
    created_files: list[str] = []
    audio_path: str | None = None
    subtitle_path: str | None = None
    video_path: str | None = None
    mux_attempted = False
    mux_ok = False
    fallback_reason: str | None = None
    try:
        segments = [dict(item or {}) for item in (subtitle_segments or [])]
        if not segments:
            return {
                "ok": False,
                "result_type": "guard",
                "video_path": None,
                "audio_path": None,
                "subtitle_path": None,
                "mux_attempted": False,
                "mux_ok": False,
                "fallback_reason": "subtitle_segments_missing",
                "created_files": [],
            }
        srt_text = _segments_to_srt(segments)
        subtitle_file = workspace / "subtitle.srt"
        subtitle_file.write_text(srt_text, encoding="utf-8")
        subtitle_path = str(subtitle_file)
        created_files.append(subtitle_path)
        audio_bytes = _call_tts_func(tts_func, segments, str(voice_id or SYSTEM_DEFAULT_VOICE_ID), str(workspace))
        if not audio_bytes:
            return {
                "ok": False,
                "result_type": "guard",
                "video_path": None,
                "audio_path": None,
                "subtitle_path": subtitle_path,
                "mux_attempted": False,
                "mux_ok": False,
                "fallback_reason": "tts_audio_empty",
                "created_files": created_files,
            }
        audio_file = workspace / "dub_audio.mp3"
        audio_file.write_bytes(audio_bytes)
        audio_path = str(audio_file)
        created_files.append(audio_path)
        if source_video_path and Path(str(source_video_path)).exists():
            mux_attempted = True
            try:
                output_file = workspace / "final.mp4"
                video_path = mux_final_video(
                    str(source_video_path),
                    audio_path,
                    str(output_file),
                    srt_path=subtitle_path,
                    burn_subtitles=burn_subtitles,
                    replace_audio=True,
                )
                mux_ok = True
                created_files.append(video_path)
                return {
                    "ok": True,
                    "result_type": "mp4",
                    "video_path": video_path,
                    "audio_path": audio_path,
                    "subtitle_path": subtitle_path,
                    "mux_attempted": True,
                    "mux_ok": True,
                    "fallback_reason": None,
                    "created_files": created_files,
                }
            except Exception as exc:
                fallback_reason = str(exc)[:240] or "mux_failed"
        return {
            "ok": True,
            "result_type": "audio_fallback",
            "video_path": None,
            "audio_path": audio_path,
            "subtitle_path": subtitle_path,
            "mux_attempted": mux_attempted,
            "mux_ok": mux_ok,
            "fallback_reason": fallback_reason,
            "created_files": created_files,
        }
    except DubbingPipelineError as exc:
        return {
            "ok": False,
            "result_type": "guard",
            "video_path": video_path,
            "audio_path": audio_path,
            "subtitle_path": subtitle_path,
            "mux_attempted": mux_attempted,
            "mux_ok": mux_ok,
            "fallback_reason": str(exc),
            "created_files": created_files,
        }
    except Exception as exc:
        return {
            "ok": False,
            "result_type": "error",
            "video_path": video_path,
            "audio_path": audio_path,
            "subtitle_path": subtitle_path,
            "mux_attempted": mux_attempted,
            "mux_ok": mux_ok,
            "fallback_reason": type(exc).__name__,
            "created_files": created_files,
        }


def cleanup_workspace(workspace_dir: str) -> None:
    workspace = _safe_workspace(workspace_dir)
    if not workspace.exists():
        return
    for child in list(workspace.iterdir()):
        resolved = child.resolve()
        if workspace not in resolved.parents and resolved != workspace:
            raise DubbingPipelineError("unsafe_workspace_child")
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except FileNotFoundError:
                pass
    try:
        workspace.rmdir()
    except OSError:
        pass
