from __future__ import annotations

import json
import os
import re
import shutil
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
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        if callable(mux_func):
            result = mux_func(str(video), str(subtitle), str(output))
            produced = str(result or output)
        else:
            shutil.copyfile(video, output)
            produced = str(output)
        final = Path(produced).expanduser()
        if not final.exists() or final.stat().st_size <= 0:
            return PipelineArtifact(False, "guard", subtitle_path=str(subtitle.resolve()), reason="video_output_empty", public_message=PUBLIC_SAFE_ERROR)
        return PipelineArtifact(True, "mp4", video_path=str(final.resolve()), subtitle_path=str(subtitle.resolve()), created_files=(str(final.resolve()),))
    except Exception as exc:
        return PipelineArtifact(False, "partial", subtitle_path=str(subtitle.resolve()), reason=type(exc).__name__, public_message=PUBLIC_PARTIAL_MESSAGE, created_files=(str(subtitle.resolve()),))


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
    translated_path = Path("")
    if _clean_text(target_language):
        translated_path = workspace / "translated.srt"
        translate_srt(source_srt_text, target_language, translate_func=translate_func, output_path=translated_path)
        selected_srt_path = translated_path
        created.append(str(translated_path))

    plain_text = " ".join(segment.get("text") or "" for segment in segments).strip()
    if not plain_text:
        return PipelineArtifact(False, "guard", transcript_path=str(transcript_path), subtitle_path=str(source_srt_path), reason="empty_script", public_message="TOAN AAS cần lời đọc trước khi tạo giọng.", created_files=tuple(created))
    if not callable(tts_func):
        return PipelineArtifact(False, "guard", transcript_path=str(transcript_path), subtitle_path=str(source_srt_path), translated_subtitle_path=str(translated_path) if translated_path else "", reason="tts_func_missing", public_message=PUBLIC_SAFE_ERROR, created_files=tuple(created))
    audio_path = workspace / "dub_audio.mp3"
    try:
        result = tts_func(plain_text, voice_id=str(provider_voice_id or ""), output_path=str(audio_path))
        audio_bytes = b""
        if isinstance(result, (bytes, bytearray)):
            audio_bytes = bytes(result)
        elif isinstance(result, dict):
            for key in ("audio_bytes", "bytes", "data", "audio"):
                value = result.get(key)
                if isinstance(value, (bytes, bytearray)):
                    audio_bytes = bytes(value)
                    break
        if audio_bytes:
            audio_path.write_bytes(audio_bytes)
    except Exception as exc:
        return PipelineArtifact(False, "guard", transcript_path=str(transcript_path), subtitle_path=str(source_srt_path), translated_subtitle_path=str(translated_path) if translated_path else "", reason=type(exc).__name__, public_message=PUBLIC_SAFE_ERROR, created_files=tuple(created))
    if not audio_path.exists() or audio_path.stat().st_size <= 0:
        return PipelineArtifact(False, "guard", transcript_path=str(transcript_path), subtitle_path=str(source_srt_path), translated_subtitle_path=str(translated_path) if translated_path else "", reason="audio_empty", public_message=PUBLIC_SAFE_ERROR, created_files=tuple(created))
    created.append(str(audio_path))

    video_path = Path(str(source_video_path or "")).expanduser() if source_video_path else Path("")
    if video_path and str(video_path) and video_path.exists() and video_path.stat().st_size > 0:
        output_video = workspace / "final_dubbed.mp4"
        try:
            if callable(mux_func):
                result = mux_func(str(video_path), str(audio_path), str(output_video), str(selected_srt_path))
                produced = Path(str(result or output_video)).expanduser()
            else:
                shutil.copyfile(video_path, output_video)
                produced = output_video
            if produced.exists() and produced.stat().st_size > 0:
                created.append(str(produced))
                return PipelineArtifact(
                    True,
                    "mp4",
                    video_path=str(produced.resolve()),
                    audio_path=str(audio_path.resolve()),
                    subtitle_path=str(source_srt_path.resolve()),
                    transcript_path=str(transcript_path.resolve()),
                    translated_subtitle_path=str(translated_path.resolve()) if translated_path else "",
                    created_files=tuple(created),
                )
        except Exception as exc:
            return PipelineArtifact(
                True,
                "partial",
                audio_path=str(audio_path.resolve()),
                subtitle_path=str(source_srt_path.resolve()),
                transcript_path=str(transcript_path.resolve()),
                translated_subtitle_path=str(translated_path.resolve()) if translated_path else "",
                reason=type(exc).__name__,
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
