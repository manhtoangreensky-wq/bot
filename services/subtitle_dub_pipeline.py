from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


SRT_TS_RE = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}$")
PUBLIC_PARTIAL_MESSAGE = "Video chưa ghép được tự động, nhưng TOAN AAS đã tạo xong file phụ đề/voice để anh/chị tải về."
PUBLIC_SAFE_ERROR = "TOAN AAS chưa xử lý được file này. Anh/chị thử lại với video rõ tiếng hơn hoặc nhận file đã tạo nếu có."


@dataclass(frozen=True)
class PipelineArtifact:
    ok: bool
    result_type: str
    video_path: str = ""
    audio_path: str = ""
    subtitle_path: str = ""
    transcript_path: str = ""
    translated_subtitle_path: str = ""
    public_message: str = ""
    reason: str = ""
    created_files: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "result_type": self.result_type,
            "video_path": self.video_path or None,
            "audio_path": self.audio_path or None,
            "subtitle_path": self.subtitle_path or None,
            "transcript_path": self.transcript_path or None,
            "translated_subtitle_path": self.translated_subtitle_path or None,
            "public_message": self.public_message,
            "reason": self.reason,
            "created_files": list(self.created_files),
        }


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _artifact_ok(path_value: str | os.PathLike[str] | None) -> bool:
    if not path_value:
        return False
    try:
        path = Path(str(path_value)).expanduser()
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _timestamp(seconds: float) -> str:
    millis = max(0, int(round(float(seconds or 0.0) * 1000)))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _seconds_from_timestamp(value: str) -> float:
    hh, mm, rest = str(value).split(":", 2)
    ss, ms = rest.split(",", 1)
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0


def build_transcript_from_storyboard(
    storyboard: dict | None = None,
    *,
    narration_text: str = "",
    scene_duration: int = 6,
) -> list[dict[str, Any]]:
    duration = max(1, int(scene_duration or 6))
    manual = str(narration_text or "").strip()
    if manual:
        lines = [_clean_text(line) for line in manual.replace("\r", "\n").split("\n") if _clean_text(line)]
        return [
            {"index": index, "start": (index - 1) * duration, "end": index * duration, "text": line}
            for index, line in enumerate(lines, start=1)
        ]
    plan = dict(storyboard or {})
    raw_cards = plan.get("scene_cards") or plan.get("scenes") or []
    segments: list[dict[str, Any]] = []
    for fallback_index, card in enumerate(raw_cards, start=1):
        item = dict(card or {})
        text = _clean_text(
            item.get("narration_line")
            or item.get("subtitle_line")
            or item.get("script_text")
            or item.get("summary")
            or item.get("visual_goal")
        )
        if not text:
            continue
        index = int(item.get("scene_index") or fallback_index)
        start = float(item.get("start") or (index - 1) * duration)
        end = float(item.get("end") or start + duration)
        if end <= start:
            end = start + duration
        segments.append({"index": index, "start": start, "end": end, "text": text})
    return segments


def generate_srt_from_transcript(
    transcript: list[dict[str, Any]] | None,
    output_path: str | os.PathLike[str] | None = None,
) -> str:
    blocks: list[str] = []
    cursor = 0.0
    for fallback_index, segment in enumerate(list(transcript or []), start=1):
        item = dict(segment or {})
        text = _clean_text(item.get("text") or item.get("translated_text") or item.get("caption"))
        if not text:
            continue
        start = float(item.get("start") or cursor)
        end = float(item.get("end") or 0)
        if end <= start:
            end = start + max(1.0, min(6.0, len(text.split()) / 2.5))
        cursor = end
        index = len(blocks) + 1
        blocks.append(f"{index}\n{_timestamp(start)} --> {_timestamp(end)}\n{text}")
    srt_text = "\n\n".join(blocks) + ("\n" if blocks else "")
    if output_path:
        path = Path(str(output_path)).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(srt_text, encoding="utf-8")
    return srt_text


def validate_srt(srt_or_path: str | os.PathLike[str] | None) -> bool:
    raw = str(srt_or_path or "")
    text = raw
    if raw and "\n" not in raw and "\r" not in raw and len(raw) < 260:
        try:
            path = Path(raw)
            if path.exists() and path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = raw
    blocks = [block.strip() for block in text.replace("\r\n", "\n").replace("\r", "\n").split("\n\n") if block.strip()]
    if not blocks:
        return False
    for expected, block in enumerate(blocks, start=1):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if len(lines) < 3:
            return False
        if not lines[0].isdigit():
            return False
        if int(lines[0]) != expected:
            return False
        if not SRT_TS_RE.match(lines[1]):
            return False
        start, end = [item.strip() for item in lines[1].split("-->", 1)]
        if _seconds_from_timestamp(end) <= _seconds_from_timestamp(start):
            return False
    return True


def _translate_line(text: str, target_language: str, translate_func: Callable[[str, str], str] | None = None) -> str:
    if callable(translate_func):
        return _clean_text(translate_func(text, target_language))
    lang = _clean_text(target_language) or "ngôn ngữ đích"
    return f"[{lang}] {text}"


def translate_srt(
    srt_text: str,
    target_language: str,
    *,
    translate_func: Callable[[str, str], str] | None = None,
    output_path: str | os.PathLike[str] | None = None,
) -> str:
    if not validate_srt(srt_text):
        raise ValueError("invalid_srt")
    blocks = []
    for block in str(srt_text or "").replace("\r\n", "\n").replace("\r", "\n").strip().split("\n\n"):
        lines = block.split("\n")
        if len(lines) < 3:
            continue
        text = "\n".join(_translate_line(line, target_language, translate_func) for line in lines[2:] if _clean_text(line))
        blocks.append("\n".join([lines[0], lines[1], text]))
    translated = "\n\n".join(blocks) + ("\n" if blocks else "")
    if output_path:
        path = Path(str(output_path)).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(translated, encoding="utf-8")
    return translated


def _srt_timestamp_lines(srt_text: str) -> list[str]:
    return [
        line.strip()
        for line in str(srt_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if SRT_TS_RE.match(line.strip())
    ]


def translate_srt_preserve_timestamps(
    srt_text: str,
    target_language: str,
    *,
    translate_func: Callable[[str, str], str] | None = None,
    output_path: str | os.PathLike[str] | None = None,
) -> str:
    source_timestamps = _srt_timestamp_lines(srt_text)
    translated = translate_srt(
        srt_text,
        target_language,
        translate_func=translate_func,
        output_path=None,
    )
    if not validate_srt(translated):
        raise ValueError("translated_srt_invalid")
    if _srt_timestamp_lines(translated) != source_timestamps:
        raise ValueError("translated_srt_timestamps_changed")
    if output_path:
        path = Path(str(output_path)).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(translated, encoding="utf-8")
    return translated


def synthesize_dub_audio(
    transcript: list[dict[str, Any]] | None,
    *,
    output_dir: str | os.PathLike[str],
    provider_voice_id: str = "",
    tts_func: Callable[..., Any] | None = None,
    filename_prefix: str = "dub_segment",
) -> list[str]:
    if not callable(tts_func):
        raise ValueError("tts_func_missing")
    output_root = Path(str(output_dir)).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    audio_paths: list[str] = []
    for fallback_index, segment in enumerate(list(transcript or []), start=1):
        item = dict(segment or {})
        text = _clean_text(item.get("text") or item.get("translated_text") or item.get("caption"))
        if not text:
            continue
        index = int(item.get("index") or fallback_index)
        output_path = output_root / f"{filename_prefix}_{index:03d}.mp3"
        result = tts_func(text, voice_id=str(provider_voice_id or ""), output_path=str(output_path))
        audio_bytes = b""
        if isinstance(result, (bytes, bytearray)):
            audio_bytes = bytes(result)
        elif isinstance(result, dict):
            for key in ("audio_bytes", "bytes", "data", "audio"):
                value = result.get(key)
                if isinstance(value, (bytes, bytearray)):
                    audio_bytes = bytes(value)
                    break
        if audio_bytes and not _artifact_ok(output_path):
            output_path.write_bytes(audio_bytes)
        if not _artifact_ok(output_path):
            raise ValueError("dub_audio_segment_empty")
        audio_paths.append(str(output_path.resolve()))
    if not audio_paths:
        raise ValueError("dub_audio_segments_missing")
    return audio_paths


def combine_dub_audio(
    audio_paths: list[str] | tuple[str, ...] | None,
    output_path: str | os.PathLike[str],
    *,
    combine_func: Callable[..., Any] | None = None,
) -> str:
    paths = [Path(str(item)).expanduser() for item in list(audio_paths or []) if str(item or "").strip()]
    if not paths or any(not _artifact_ok(path) for path in paths):
        raise ValueError("dub_audio_input_missing")
    output = Path(str(output_path)).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    if callable(combine_func):
        produced = combine_func([str(path) for path in paths], str(output))
        final_path = Path(str(produced or output)).expanduser()
    else:
        with output.open("wb") as handle:
            for index, path in enumerate(paths):
                if index:
                    handle.write(b"\n")
                handle.write(path.read_bytes())
        final_path = output
    if not _artifact_ok(final_path):
        raise ValueError("dub_audio_combined_empty")
    return str(final_path.resolve())


def partial_result_on_mux_fail(
    *,
    audio_path: str = "",
    subtitle_path: str = "",
    transcript_path: str = "",
    translated_subtitle_path: str = "",
    reason: str = "mux_failed",
) -> PipelineArtifact:
    audio_ok = _artifact_ok(audio_path)
    subtitle_ok = _artifact_ok(subtitle_path) and validate_srt(subtitle_path)
    if not (audio_ok or subtitle_ok):
        return PipelineArtifact(False, "guard", reason="partial_artifacts_missing", public_message=PUBLIC_SAFE_ERROR)
    created = tuple(
        str(Path(item).expanduser().resolve())
        for item in (audio_path, subtitle_path, transcript_path, translated_subtitle_path)
        if _artifact_ok(item)
    )
    return PipelineArtifact(
        True,
        "partial",
        audio_path=str(Path(audio_path).expanduser().resolve()) if audio_ok else "",
        subtitle_path=str(Path(subtitle_path).expanduser().resolve()) if subtitle_ok else "",
        transcript_path=str(Path(transcript_path).expanduser().resolve()) if _artifact_ok(transcript_path) else "",
        translated_subtitle_path=str(Path(translated_subtitle_path).expanduser().resolve()) if _artifact_ok(translated_subtitle_path) else "",
        reason=str(reason or "mux_failed"),
        public_message=PUBLIC_PARTIAL_MESSAGE,
        created_files=created,
    )


def mux_subtitle_or_dub_video(
    *,
    source_video_path: str,
    output_path: str,
    audio_path: str = "",
    subtitle_path: str = "",
    mux_func: Callable[..., Any] | None = None,
) -> PipelineArtifact:
    video = Path(str(source_video_path or "")).expanduser()
    subtitle = Path(str(subtitle_path or "")).expanduser() if subtitle_path else Path("")
    audio = Path(str(audio_path or "")).expanduser() if audio_path else Path("")
    output = Path(str(output_path or "")).expanduser()
    if not _artifact_ok(video):
        return PipelineArtifact(False, "guard", reason="video_missing", public_message=PUBLIC_SAFE_ERROR)
    if audio_path and not _artifact_ok(audio):
        return PipelineArtifact(False, "guard", reason="audio_missing", public_message=PUBLIC_SAFE_ERROR)
    if subtitle_path and (not _artifact_ok(subtitle) or not validate_srt(subtitle)):
        return PipelineArtifact(False, "guard", audio_path=str(audio.resolve()) if _artifact_ok(audio) else "", reason="subtitle_missing_or_invalid", public_message=PUBLIC_SAFE_ERROR)
    if not (audio_path or subtitle_path):
        return PipelineArtifact(False, "guard", reason="mux_input_missing", public_message=PUBLIC_SAFE_ERROR)
    if not callable(mux_func):
        return partial_result_on_mux_fail(audio_path=str(audio) if audio_path else "", subtitle_path=str(subtitle) if subtitle_path else "", reason="mux_func_missing")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        try:
            produced = mux_func(str(video), str(audio) if audio_path else "", str(output), str(subtitle) if subtitle_path else "")
        except TypeError:
            if audio_path:
                produced = mux_func(str(video), str(audio), str(output))
            else:
                produced = mux_func(str(video), str(subtitle), str(output))
        final = Path(str(produced or output)).expanduser()
        if not _artifact_ok(final):
            return partial_result_on_mux_fail(audio_path=str(audio) if audio_path else "", subtitle_path=str(subtitle) if subtitle_path else "", reason="mux_output_empty")
        return PipelineArtifact(
            True,
            "mp4",
            video_path=str(final.resolve()),
            audio_path=str(audio.resolve()) if audio_path and _artifact_ok(audio) else "",
            subtitle_path=str(subtitle.resolve()) if subtitle_path and _artifact_ok(subtitle) else "",
            created_files=(str(final.resolve()),),
        )
    except Exception as exc:
        return partial_result_on_mux_fail(audio_path=str(audio) if audio_path else "", subtitle_path=str(subtitle) if subtitle_path else "", reason=type(exc).__name__)


def burn_or_mux_subtitle(
    *,
    source_video_path: str,
    subtitle_path: str,
    output_path: str,
    mux_func: Callable[..., Any] | None = None,
) -> PipelineArtifact:
    video = Path(str(source_video_path or "")).expanduser()
    subtitle = Path(str(subtitle_path or "")).expanduser()
    output = Path(str(output_path or "")).expanduser()
    if not video.exists() or video.stat().st_size <= 0:
        return PipelineArtifact(False, "guard", subtitle_path=str(subtitle) if subtitle.exists() else "", reason="video_missing", public_message=PUBLIC_SAFE_ERROR)
    if not subtitle.exists() or subtitle.stat().st_size <= 0 or not validate_srt(subtitle):
        return PipelineArtifact(False, "guard", reason="subtitle_missing_or_invalid", public_message=PUBLIC_SAFE_ERROR)
    if not callable(mux_func):
        return partial_result_on_mux_fail(subtitle_path=str(subtitle.resolve()), reason="mux_func_missing")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = mux_func(str(video), str(subtitle), str(output))
        produced = str(result or output)
        final = Path(produced).expanduser()
        if not final.exists() or final.stat().st_size <= 0:
            return PipelineArtifact(False, "guard", subtitle_path=str(subtitle.resolve()), reason="video_output_empty", public_message=PUBLIC_SAFE_ERROR)
        return PipelineArtifact(True, "mp4", video_path=str(final.resolve()), subtitle_path=str(subtitle.resolve()), created_files=(str(final.resolve()),))
    except Exception as exc:
        return partial_result_on_mux_fail(subtitle_path=str(subtitle.resolve()), reason=type(exc).__name__)


def _segments_from_srt(srt_text: str) -> list[dict[str, Any]]:
    segments = []
    for block in str(srt_text or "").replace("\r\n", "\n").replace("\r", "\n").strip().split("\n\n"):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if len(lines) < 3 or not SRT_TS_RE.match(lines[1]):
            continue
        start_raw, end_raw = [item.strip() for item in lines[1].split("-->", 1)]
        segments.append({
            "index": len(segments) + 1,
            "start": _seconds_from_timestamp(start_raw),
            "end": _seconds_from_timestamp(end_raw),
            "text": " ".join(lines[2:]),
        })
    return segments


def run_dub_pipeline(
    *,
    workspace_dir: str,
    source_video_path: str | None = None,
    transcript: list[dict[str, Any]] | None = None,
    source_srt: str = "",
    target_language: str = "",
    provider_voice_id: str = "",
    tts_func: Callable[..., Any] | None = None,
    mux_func: Callable[..., Any] | None = None,
    translate_func: Callable[[str, str], str] | None = None,
) -> PipelineArtifact:
    workspace = Path(str(workspace_dir or "")).expanduser().resolve()
    if not workspace.name:
        return PipelineArtifact(False, "guard", reason="workspace_missing", public_message=PUBLIC_SAFE_ERROR)
    workspace.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    segments = list(transcript or [])
    if source_srt and not segments:
        if not validate_srt(source_srt):
            return PipelineArtifact(False, "guard", reason="invalid_srt", public_message=PUBLIC_SAFE_ERROR)
        segments = _segments_from_srt(source_srt)
    if not segments:
        return PipelineArtifact(False, "guard", reason="transcript_missing", public_message="TOAN AAS cần lời thoại/phụ đề trước khi lồng tiếng.")

    transcript_path = workspace / "transcript.json"
    transcript_path.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
    created.append(str(transcript_path))

    source_srt_path = workspace / "source.srt"
    source_srt_text = source_srt if source_srt else generate_srt_from_transcript(segments)
    source_srt_path.write_text(source_srt_text, encoding="utf-8")
    created.append(str(source_srt_path))
    if not validate_srt(source_srt_path):
        return PipelineArtifact(False, "guard", transcript_path=str(transcript_path), subtitle_path=str(source_srt_path), reason="invalid_source_srt", public_message=PUBLIC_SAFE_ERROR, created_files=tuple(created))

    selected_srt_path = source_srt_path
    selected_srt_text = source_srt_text
    translated_path = Path("")
    if _clean_text(target_language):
        translated_path = workspace / "translated.srt"
        selected_srt_text = translate_srt_preserve_timestamps(source_srt_text, target_language, translate_func=translate_func, output_path=translated_path)
        selected_srt_path = translated_path
        created.append(str(translated_path))

    tts_segments = _segments_from_srt(selected_srt_text) or segments
    plain_text = " ".join(segment.get("text") or "" for segment in tts_segments).strip()
    if not plain_text:
        return PipelineArtifact(False, "guard", transcript_path=str(transcript_path), subtitle_path=str(source_srt_path), reason="empty_script", public_message="TOAN AAS cần lời đọc trước khi tạo giọng.", created_files=tuple(created))
    if not callable(tts_func):
        return PipelineArtifact(False, "guard", transcript_path=str(transcript_path), subtitle_path=str(source_srt_path), translated_subtitle_path=str(translated_path) if translated_path else "", reason="tts_func_missing", public_message=PUBLIC_SAFE_ERROR, created_files=tuple(created))
    audio_path = workspace / "dub_audio.mp3"
    try:
        segment_paths = synthesize_dub_audio(
            tts_segments,
            output_dir=workspace / "tts_segments",
            provider_voice_id=str(provider_voice_id or ""),
            tts_func=tts_func,
        )
        created.extend(segment_paths)
        combine_dub_audio(segment_paths, audio_path)
    except Exception as exc:
        return PipelineArtifact(False, "guard", transcript_path=str(transcript_path), subtitle_path=str(source_srt_path), translated_subtitle_path=str(translated_path) if translated_path else "", reason=type(exc).__name__, public_message=PUBLIC_SAFE_ERROR, created_files=tuple(created))
    if not audio_path.exists() or audio_path.stat().st_size <= 0:
        return PipelineArtifact(False, "guard", transcript_path=str(transcript_path), subtitle_path=str(source_srt_path), translated_subtitle_path=str(translated_path) if translated_path else "", reason="audio_empty", public_message=PUBLIC_SAFE_ERROR, created_files=tuple(created))
    created.append(str(audio_path))

    video_path = Path(str(source_video_path or "")).expanduser() if source_video_path else Path("")
    if source_video_path and _artifact_ok(video_path):
        output_video = workspace / "final_dubbed.mp4"
        mux_result = mux_subtitle_or_dub_video(
            source_video_path=str(video_path),
            audio_path=str(audio_path),
            subtitle_path=str(selected_srt_path),
            output_path=str(output_video),
            mux_func=mux_func,
        )
        if mux_result.ok and mux_result.result_type == "mp4" and mux_result.video_path:
            created.extend(item for item in mux_result.created_files if item not in created)
            return PipelineArtifact(
                True,
                "mp4",
                video_path=mux_result.video_path,
                audio_path=str(audio_path.resolve()),
                subtitle_path=str(source_srt_path.resolve()),
                transcript_path=str(transcript_path.resolve()),
                translated_subtitle_path=str(translated_path.resolve()) if translated_path else "",
                created_files=tuple(created),
            )
        if mux_result.ok and mux_result.result_type == "partial":
            return PipelineArtifact(
                True,
                "partial",
                audio_path=str(audio_path.resolve()),
                subtitle_path=str(source_srt_path.resolve()),
                transcript_path=str(transcript_path.resolve()),
                translated_subtitle_path=str(translated_path.resolve()) if translated_path else "",
                reason=mux_result.reason,
                public_message=PUBLIC_PARTIAL_MESSAGE,
                created_files=tuple(created),
            )
    return PipelineArtifact(
        True,
        "audio_subtitle",
        audio_path=str(audio_path.resolve()),
        subtitle_path=str(source_srt_path.resolve()),
        transcript_path=str(transcript_path.resolve()),
        translated_subtitle_path=str(translated_path.resolve()) if translated_path else "",
        public_message=PUBLIC_PARTIAL_MESSAGE,
        created_files=tuple(created),
    )
