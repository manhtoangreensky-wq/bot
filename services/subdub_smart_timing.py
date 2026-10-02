"""Small, source-locked timing helpers for Smart Multi audio fitting."""

from __future__ import annotations

from collections.abc import Iterable, MutableMapping
import re
from typing import Any

from services.subdub_canonical_cues import parse_srt_segments


SMART_TAIL_EXTENSION_MAX_SECONDS = 2.0


def _cue_seconds(item: dict[str, Any], key: str) -> float:
    milliseconds = item.get(f"{key}_ms")
    return float(milliseconds) / 1000.0 if milliseconds is not None else float(item.get(key) or 0.0)


def extend_smart_tail_windows(
    chunks: list[dict[str, Any]],
    *,
    companion_segments: Iterable[MutableMapping[str, Any]] = (),
    source_duration: float = 0.0,
    max_extension_seconds: float = SMART_TAIL_EXTENSION_MAX_SECONDS,
) -> list[str]:
    """Extend Smart cue ends into an empty following gap, bounded at two seconds.

    The cue start and every later cue remain unchanged. The helper only acts on
    duration-aware Smart chunks whose measured audio exceeds their source cue;
    it returns the cue IDs changed so subtitle text can be regenerated once.
    """

    ordered = sorted(
        [item for item in chunks if isinstance(item, MutableMapping)],
        key=lambda item: (_cue_seconds(item, "start"), str(item.get("cue_id") or "")),
    )
    companions = [
        item
        for item in companion_segments
        if isinstance(item, MutableMapping)
    ]
    speech_windows = [
        (
            str(item.get("cue_id") or item.get("id") or "").strip(),
            _cue_seconds(item, "start"),
            _cue_seconds(item, "end"),
        )
        for item in [*ordered, *companions]
    ]
    max_extension = max(
        0.0, min(SMART_TAIL_EXTENSION_MAX_SECONDS, float(max_extension_seconds or 0.0)),
    )
    duration = max(0.0, float(source_duration or 0.0))
    changed: list[str] = []

    for item in ordered:
        if not item.get("duration_aware_timing"):
            continue
        cue_id = str(item.get("cue_id") or item.get("id") or "").strip()
        start = max(0.0, _cue_seconds(item, "start"))
        end = max(start, _cue_seconds(item, "end"))
        audio_duration = max(
            0.0,
            float(item.get("audio_duration") or item.get("raw_audio_duration") or 0.0),
        )
        cue_window = max(0.001, end - start)
        if not cue_id or audio_duration <= cue_window + 0.001:
            continue

        original_end = float(item.get("smart_source_end") or end)
        if not start < original_end <= end:
            original_end = end
        remaining_extension = max(0.0, max_extension - (end - original_end))
        boundary = duration if duration > 0.0 else end
        # Preserved cues and earlier overlapping speakers also occupy the gap.
        for other_id, other_start, other_end in speech_windows:
            if other_id == cue_id:
                continue
            if other_start < end < other_end:
                boundary = end
                break
            if other_start >= end:
                boundary = min(boundary, other_start)
        available_gap = max(0.0, boundary - end)
        extension = min(remaining_extension, available_gap, audio_duration - cue_window)
        if extension <= 0.001:
            continue

        new_end = end + extension
        item["end"] = new_end
        item["cue_window"] = new_end - start
        item["cue_window_seconds"] = new_end - start
        item["fit_ratio"] = audio_duration / (new_end - start)
        item["smart_source_end"] = original_end
        item["tail_extension_seconds"] = new_end - original_end
        if "end_ms" in item:
            item["end_ms"] = int(round(new_end * 1000))
        for companion in companions:
            if str(companion.get("cue_id") or companion.get("id") or "").strip() != cue_id:
                continue
            companion["end"] = new_end
            companion["smart_source_end"] = original_end
            companion["tail_extension_seconds"] = new_end - original_end
            if "end_ms" in companion:
                companion["end_ms"] = int(round(new_end * 1000))
        changed.append(cue_id)

    return changed


def retime_smart_subtitle_tails(srt_text: str, segments: Iterable[dict]) -> str:
    """Retain SRT text and starts; replace only identity-matched approved ends."""

    extended = [
        (position, segment)
        for position, segment in enumerate(segments)
        if float(segment.get("tail_extension_seconds") or 0.0) > 0.001
    ]
    if not extended:
        return srt_text
    normalized = str(srt_text or "").replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", normalized.strip())
    parsed = parse_srt_segments(normalized)
    if len(blocks) != len(parsed):
        raise ValueError("smart_tail_subtitle_cue_mismatch")
    for position, segment in extended:
        if position >= len(parsed):
            raise ValueError("smart_tail_subtitle_cue_mismatch")
        start_ms = int(round(_cue_seconds(segment, "start") * 1000))
        end_ms = int(round(_cue_seconds(segment, "end") * 1000))
        original_end_ms = int(round(float(segment["smart_source_end"]) * 1000))
        if (
            parsed[position]["start_ms"] != start_ms
            or parsed[position]["end_ms"] not in {original_end_ms, end_ms}
        ):
            raise ValueError("smart_tail_subtitle_cue_mismatch")
        hours, remainder = divmod(end_ms, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        seconds, millis = divmod(remainder, 1000)
        lines = blocks[position].splitlines()
        timing_index = next(index for index, line in enumerate(lines) if "-->" in line)
        left, right = lines[timing_index].split("-->", 1)
        suffix = right.strip().split(maxsplit=1)
        settings = f" {suffix[1]}" if len(suffix) > 1 else ""
        lines[timing_index] = (
            f"{left.rstrip()} --> {hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}{settings}"
        )
        blocks[position] = "\n".join(lines)
    return "\n\n".join(blocks) + ("\n" if normalized.endswith("\n") else "")
