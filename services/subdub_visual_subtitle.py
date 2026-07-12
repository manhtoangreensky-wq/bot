"""Local visual-subtitle cue extraction helpers for SubDub.

This module is provider-neutral. It groups timestamped OCR observations into
subtitle cues and leaves video rendering, translation, TTS, and delivery to
their existing lanes.
"""

from __future__ import annotations

import inspect
import re
from difflib import SequenceMatcher
from typing import Any, Awaitable, Callable, Iterable


FrameExtractor = Callable[[bytes, float, int], Awaitable[list[str]] | list[str]]
FrameOcr = Callable[[str, str], Awaitable[dict[str, Any] | str] | dict[str, Any] | str]


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def normalize_ocr_text(value: Any) -> str:
    text = str(value or "").replace("\x00", " ").replace("\r", "\n")
    lines = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip(" |_-~")
        if line and not re.fullmatch(r"[\W_]+", line, flags=re.UNICODE):
            lines.append(line)
    return " ".join(lines).strip()


def _comparison_text(value: Any) -> str:
    text = normalize_ocr_text(value).casefold()
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def visual_text_similarity(left: Any, right: Any) -> float:
    left_key = _comparison_text(left)
    right_key = _comparison_text(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    return SequenceMatcher(None, left_key, right_key).ratio()


def observations_to_cues(
    observations: Iterable[dict[str, Any]],
    *,
    frame_interval: float = 0.5,
    source_duration: float = 0.0,
    similarity_threshold: float = 0.82,
    minimum_text_chars: int = 2,
) -> list[dict[str, Any]]:
    """Group sequential OCR observations while preserving frame timestamps."""
    interval = max(0.1, float(frame_interval or 0.5))
    duration = max(0.0, float(source_duration or 0.0))
    samples = sorted(
        (dict(item or {}) for item in (observations or [])),
        key=lambda item: float(item.get("timestamp") or 0.0),
    )
    cues: list[dict[str, Any]] = []
    active: dict[str, Any] | None = None

    def finish(end_time: float) -> None:
        nonlocal active
        if not active:
            return
        start = max(0.0, float(active.get("start") or 0.0))
        end = max(start + 0.1, float(end_time or 0.0))
        if duration > 0:
            end = min(duration, end)
        if end > start:
            cues.append(
                {
                    "index": len(cues) + 1,
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "text": str(active.get("text") or "").strip(),
                    "confidence": float(active.get("confidence") or 0.0),
                    "ocr_hits": int(active.get("hits") or 1),
                    "timing_source": "visual_hardsub_ocr",
                }
            )
        active = None

    for sample in samples:
        timestamp = max(0.0, float(sample.get("timestamp") or 0.0))
        text = normalize_ocr_text(sample.get("text"))
        confidence = float(sample.get("confidence") or 0.0)
        if len(_comparison_text(text)) < max(1, int(minimum_text_chars or 1)):
            finish(timestamp)
            continue
        if active is None:
            active = {
                "start": timestamp,
                "last_seen": timestamp,
                "text": text,
                "confidence": confidence,
                "hits": 1,
            }
            continue
        similarity = visual_text_similarity(active.get("text"), text)
        if similarity >= float(similarity_threshold or 0.82):
            active["last_seen"] = timestamp
            active["hits"] = int(active.get("hits") or 1) + 1
            if confidence >= float(active.get("confidence") or 0.0) or len(text) > len(str(active.get("text") or "")):
                active["text"] = text
                active["confidence"] = confidence
            continue
        finish(timestamp)
        active = {
            "start": timestamp,
            "last_seen": timestamp,
            "text": text,
            "confidence": confidence,
            "hits": 1,
        }

    if active:
        last_seen = float(active.get("last_seen") or active.get("start") or 0.0)
        finish(duration if duration > 0 else last_seen + interval)

    normalized: list[dict[str, Any]] = []
    for cue in cues:
        start = max(0.0, float(cue.get("start") or 0.0))
        end = max(start + 0.1, float(cue.get("end") or 0.0))
        if normalized and start < float(normalized[-1]["end"]):
            start = float(normalized[-1]["end"])
        if duration > 0:
            end = min(duration, end)
        if end <= start:
            continue
        normalized.append({**cue, "index": len(normalized) + 1, "start": round(start, 3), "end": round(end, 3)})
    return normalized


async def extract_visual_subtitle_cues(
    source_bytes: bytes,
    *,
    source_duration: float,
    source_language: str,
    frames_per_second: float,
    max_frames: int,
    extract_frames: FrameExtractor,
    ocr_frame: FrameOcr,
) -> dict[str, Any]:
    """Run injected local frame extraction/OCR and return cue-locked results."""
    fps = max(0.5, float(frames_per_second or 2.0))
    try:
        frame_paths = list(await _maybe_await(extract_frames(bytes(source_bytes or b""), fps, int(max_frames or 0))) or [])
    except Exception as exc:
        return {"ok": False, "status": "visual_ocr_frame_extract_failed", "detail": type(exc).__name__, "segments": []}
    if not frame_paths:
        return {"ok": False, "status": "visual_ocr_frames_empty", "detail": "no_frames", "segments": []}

    observations = []
    language_used = ""
    for index, frame_path in enumerate(frame_paths):
        try:
            raw_result = await _maybe_await(ocr_frame(str(frame_path), str(source_language or "auto")))
        except Exception:
            raw_result = {"text": "", "confidence": 0.0}
        if isinstance(raw_result, dict):
            text = raw_result.get("text") or ""
            confidence = float(raw_result.get("confidence") or 0.0)
            language_used = str(raw_result.get("language") or language_used)
        else:
            text = raw_result
            confidence = 0.0
        observations.append(
            {
                "timestamp": round(index / fps, 3),
                "text": normalize_ocr_text(text),
                "confidence": confidence,
            }
        )

    cues = observations_to_cues(
        observations,
        frame_interval=1.0 / fps,
        source_duration=source_duration,
    )
    return {
        "ok": bool(cues),
        "status": "PASS" if cues else "visual_ocr_text_empty",
        "detail": f"frames={len(frame_paths)}; cues={len(cues)}",
        "segments": cues,
        "frame_count": len(frame_paths),
        "cue_count": len(cues),
        "frames_per_second": fps,
        "language": language_used or str(source_language or "auto"),
        "subtitle_timing_source": "visual_hardsub_ocr",
        "global_timing_preserved": True,
    }
