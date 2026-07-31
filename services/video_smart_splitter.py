"""Deterministic split planning for local video editing.

All boundaries use integer milliseconds.  This module never invokes FFmpeg,
creates provider jobs, or mutates billing state.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import Iterable


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


MAX_SPLIT_PARTS = _env_int("VIDEO_LOCAL_MAX_SPLIT_PARTS", 30, 1, 100)
MIN_SEGMENT_MS = _env_int("VIDEO_LOCAL_MIN_SEGMENT_MS", 2_000, 250, 60_000)


class SplitPlanError(ValueError):
    """Raised when a requested split cannot be represented safely."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class SplitRange:
    index: int
    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def to_dict(self) -> dict[str, int]:
        return {
            "index": self.index,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
        }


_TIME_TOKEN = re.compile(r"^\d+(?::\d{1,2}){0,2}(?:[.,]\d{1,3})?$")


def parse_time_ms(value: str | int | float) -> int:
    """Parse seconds, MM:SS or HH:MM:SS.mmm into integer milliseconds."""

    if isinstance(value, bool):
        raise SplitPlanError("invalid_time_format")
    if isinstance(value, (int, float)):
        if float(value) < 0:
            raise SplitPlanError("invalid_time_format")
        return int(round(float(value) * 1_000))
    text = str(value or "").strip().replace(",", ".")
    if not text or not _TIME_TOKEN.fullmatch(text):
        raise SplitPlanError("invalid_time_format")
    parts = text.split(":")
    try:
        if len(parts) == 1:
            seconds = float(parts[0])
        elif len(parts) == 2:
            minutes, second_text = parts
            seconds_value = float(second_text)
            if seconds_value >= 60:
                raise SplitPlanError("invalid_time_format")
            seconds = int(minutes) * 60 + seconds_value
        elif len(parts) == 3:
            hours, minutes, second_text = parts
            seconds_value = float(second_text)
            if int(minutes) >= 60 or seconds_value >= 60:
                raise SplitPlanError("invalid_time_format")
            seconds = int(hours) * 3_600 + int(minutes) * 60 + seconds_value
        else:
            raise SplitPlanError("invalid_time_format")
    except (TypeError, ValueError) as exc:
        raise SplitPlanError("invalid_time_format") from exc
    if seconds < 0:
        raise SplitPlanError("invalid_time_format")
    return int(round(seconds * 1_000))


def format_time_ms(value: int) -> str:
    value = max(0, int(value or 0))
    total_seconds, milliseconds = divmod(value, 1_000)
    hours, remainder = divmod(total_seconds, 3_600)
    minutes, seconds = divmod(remainder, 60)
    if milliseconds:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _validate_duration(source_duration_ms: int) -> int:
    duration = int(source_duration_ms or 0)
    if duration <= 0:
        raise SplitPlanError("source_duration_invalid")
    return duration


def _validate_part_count(count: int, *, maximum: int = MAX_SPLIT_PARTS) -> int:
    count = int(count or 0)
    if count < 2:
        raise SplitPlanError("part_count_invalid")
    if count > int(maximum):
        raise SplitPlanError("too_many_parts")
    return count


def split_fixed_duration(
    source_duration_ms: int,
    segment_duration_ms: int,
    *,
    maximum_parts: int = MAX_SPLIT_PARTS,
    minimum_segment_ms: int = MIN_SEGMENT_MS,
) -> list[SplitRange]:
    duration = _validate_duration(source_duration_ms)
    segment = int(segment_duration_ms or 0)
    if segment < int(minimum_segment_ms):
        raise SplitPlanError("segment_too_short")
    count = _validate_part_count(math.ceil(duration / segment), maximum=maximum_parts)
    ranges = [
        SplitRange(index=index + 1, start_ms=index * segment, end_ms=min((index + 1) * segment, duration))
        for index in range(count)
    ]
    if len(ranges) > 1 and ranges[-1].duration_ms < int(minimum_segment_ms):
        previous = ranges[-2]
        ranges[-2] = SplitRange(
            index=previous.index,
            start_ms=previous.start_ms,
            end_ms=ranges[-1].end_ms,
        )
        ranges.pop()
    return ranges


def split_exact_count(
    source_duration_ms: int,
    part_count: int,
    *,
    maximum_parts: int = MAX_SPLIT_PARTS,
    minimum_segment_ms: int = MIN_SEGMENT_MS,
) -> list[SplitRange]:
    duration = _validate_duration(source_duration_ms)
    count = _validate_part_count(part_count, maximum=maximum_parts)
    if count > 1 and duration // count < int(minimum_segment_ms):
        raise SplitPlanError("segment_too_short")
    boundaries = [(duration * index + count // 2) // count for index in range(count + 1)]
    boundaries[0] = 0
    boundaries[-1] = duration
    ranges = [
        SplitRange(index=index + 1, start_ms=boundaries[index], end_ms=boundaries[index + 1])
        for index in range(count)
    ]
    if any(item.duration_ms <= 0 for item in ranges):
        raise SplitPlanError("segment_too_short")
    return ranges


def _parse_custom_line(line: str) -> tuple[int, int]:
    text = str(line or "").strip()
    if not text or "-" not in text:
        raise SplitPlanError("invalid_range")
    start_text, end_text = (part.strip() for part in text.split("-", 1))
    return parse_time_ms(start_text), parse_time_ms(end_text)


def split_custom_ranges(
    source_duration_ms: int,
    ranges: str | Iterable[str | tuple[int, int] | list[int]],
    *,
    allow_gaps: bool = False,
    sort_ranges: bool = False,
    maximum_parts: int = MAX_SPLIT_PARTS,
    minimum_segment_ms: int = MIN_SEGMENT_MS,
) -> list[SplitRange]:
    duration = _validate_duration(source_duration_ms)
    raw_items: list[str | tuple[int, int] | list[int]]
    if isinstance(ranges, str):
        raw_items = [line.strip() for line in re.split(r"[\r\n;]+", ranges) if line.strip()]
    else:
        raw_items = list(ranges or [])
    if not raw_items:
        _validate_part_count(0, maximum=maximum_parts)
    if len(raw_items) > int(maximum_parts):
        raise SplitPlanError("too_many_parts")
    parsed: list[tuple[int, int]] = []
    for item in raw_items:
        if isinstance(item, (tuple, list)) and len(item) == 2:
            start_ms, end_ms = int(item[0]), int(item[1])
        else:
            start_ms, end_ms = _parse_custom_line(str(item))
        if start_ms < 0 or start_ms >= end_ms:
            raise SplitPlanError("invalid_range")
        if end_ms > duration:
            raise SplitPlanError("range_after_duration")
        if end_ms - start_ms < int(minimum_segment_ms):
            raise SplitPlanError("segment_too_short")
        parsed.append((start_ms, end_ms))
    _validate_part_count(len(parsed), maximum=maximum_parts)
    if len(set(parsed)) != len(parsed):
        raise SplitPlanError("duplicate_range")
    if sort_ranges:
        parsed = sorted(parsed, key=lambda item: (item[0], item[1]))
    for index, (start_ms, end_ms) in enumerate(parsed):
        if index == 0:
            if not allow_gaps and start_ms != 0:
                raise SplitPlanError("range_gap")
            continue
        previous_end = parsed[index - 1][1]
        if start_ms < previous_end:
            raise SplitPlanError("range_overlap")
        if not allow_gaps and start_ms != previous_end:
            raise SplitPlanError("range_gap")
    if not allow_gaps and parsed[-1][1] != duration:
        raise SplitPlanError("range_gap")
    return [SplitRange(index=index + 1, start_ms=start, end_ms=end) for index, (start, end) in enumerate(parsed)]


def validate_exact_coverage(ranges: Iterable[SplitRange], source_duration_ms: int) -> dict[str, object]:
    items = list(ranges or [])
    duration = int(source_duration_ms or 0)
    no_gap = bool(items) and items[0].start_ms == 0 and items[-1].end_ms == duration
    no_overlap = True
    for index in range(1, len(items)):
        if items[index].start_ms != items[index - 1].end_ms:
            no_gap = False
        if items[index].start_ms < items[index - 1].end_ms:
            no_overlap = False
    covered_ms = sum(max(0, item.duration_ms) for item in items)
    return {
        "ok": bool(items and no_gap and no_overlap and covered_ms == duration),
        "no_gap": no_gap,
        "no_overlap": no_overlap,
        "covered_ms": covered_ms,
        "source_duration_ms": duration,
        "part_count": len(items),
    }


def split_output_name(index: int, total: int) -> str:
    index = max(1, int(index or 1))
    total = max(index, int(total or index))
    return f"toan_aas_part_{index:03d}_of_{total:03d}.mp4"
