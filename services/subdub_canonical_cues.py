from __future__ import annotations

import hashlib
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Iterable, TypedDict


CANONICAL_CUE_VERSION = 1
RENDER_DURATION_TOLERANCE_SECONDS = 0.35


class CanonicalCue(TypedDict, total=False):
    cue_id: str
    start_ms: int
    end_ms: int
    source_start_ms: int
    source_end_ms: int
    source_text: str
    translated_text: str
    cue_source: str
    extraction_source: str
    source_language: str
    target_language: str
    confidence: float


def parse_render_duration_evidence(
    detail: Any,
    *,
    tolerance_seconds: float = RENDER_DURATION_TOLERANCE_SECONDS,
) -> dict:
    """Extract the source/output duration proof emitted by the shared renderer."""
    text = str(detail or "")
    match = re.search(
        r"source_duration_preserved=(\d+(?:\.\d+)?);output_duration=(\d+(?:\.\d+)?)",
        text,
    )
    if not match:
        return {
            "source_duration": 0.0,
            "output_duration": 0.0,
            "duration_delta_seconds": 0.0,
            "duration_evidence_present": False,
            "duration_preserved": False,
        }
    source_duration = float(match.group(1))
    output_duration = float(match.group(2))
    delta = abs(source_duration - output_duration)
    tolerance = max(0.0, float(tolerance_seconds or 0.0))
    return {
        "source_duration": source_duration,
        "output_duration": output_duration,
        "duration_delta_seconds": round(delta, 3),
        "duration_evidence_present": True,
        "duration_preserved": delta <= tolerance + 1e-9,
    }


def normalize_cue_text(value: Any) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    text = text.replace("\x00", "").replace("\ufffd", "")
    text = "".join(char for char in text if char in "\n\t" or unicodedata.category(char) != "Cc")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _cue_id(source_index: int, start_ms: int, end_ms: int, source_text: str) -> str:
    seed = f"{source_index}|{start_ms}|{end_ms}|{normalize_cue_text(source_text)}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"cue-{source_index:04d}-{digest}"


def _milliseconds(value: Any, fallback_seconds: Any = 0) -> int:
    if value not in (None, ""):
        try:
            return max(0, int(round(float(value))))
        except (TypeError, ValueError):
            pass
    try:
        return max(0, int(round(float(fallback_seconds or 0) * 1000)))
    except (TypeError, ValueError):
        return 0


def canonicalize_segments(
    segments: Iterable[dict],
    *,
    extraction_source: str,
    source_language: str = "auto",
    target_language: str = "",
) -> list[dict]:
    canonical: list[dict] = []
    for position, raw in enumerate(segments or [], start=1):
        item = dict(raw or {})
        confidence_available = bool(
            item.get("confidence_available")
            if "confidence_available" in item
            else "confidence" in item and item.get("confidence") not in (None, "")
        )
        source_text = normalize_cue_text(item.get("source_text") or item.get("text"))
        if not source_text:
            continue
        source_index = int(item.get("source_index") or item.get("index") or position)
        start_ms = _milliseconds(item.get("source_start_ms"), item.get("start"))
        end_ms = _milliseconds(item.get("source_end_ms"), item.get("end"))
        if end_ms <= start_ms:
            end_ms = start_ms + 1000
        translated_text = normalize_cue_text(item.get("translated_text"))
        cue_id = str(item.get("cue_id") or _cue_id(source_index, start_ms, end_ms, source_text))
        canonical.append({
            **item,
            "cue_id": cue_id,
            "source_index": source_index,
            "index": source_index,
            "source_start_ms": start_ms,
            "source_end_ms": end_ms,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "start": round(start_ms / 1000.0, 3),
            "end": round(end_ms / 1000.0, 3),
            "source_text": source_text,
            "source_language": str(item.get("source_language") or source_language or "auto"),
            "extraction_source": str(item.get("extraction_source") or extraction_source or "unknown"),
            "cue_source": str(
                item.get("cue_source")
                or item.get("extraction_source")
                or extraction_source
                or "unknown"
            ),
            "translated_text": translated_text,
            "target_language": str(item.get("target_language") or target_language or ""),
            "text": translated_text or source_text,
            "confidence": float(item.get("confidence") or 0.0),
            "confidence_available": confidence_available,
            "frame_first_seen": item.get("frame_first_seen"),
            "frame_last_seen": item.get("frame_last_seen"),
            "version": int(item.get("version") or CANONICAL_CUE_VERSION),
        })
    return canonical


def detect_text_script(value: Any) -> str:
    text = normalize_cue_text(value)
    counters = {
        "cjk": len(re.findall(r"[\u3400-\u9fff]", text)),
        "japanese": len(re.findall(r"[\u3040-\u30ff]", text)),
        "korean": len(re.findall(r"[\uac00-\ud7af]", text)),
        "thai": len(re.findall(r"[\u0e00-\u0e7f]", text)),
        "arabic": len(re.findall(r"[\u0600-\u06ff]", text)),
        "devanagari": len(re.findall(r"[\u0900-\u097f]", text)),
        "cyrillic": len(re.findall(r"[\u0400-\u04ff]", text)),
        "latin": len(re.findall(r"[A-Za-z\u00c0-\u024f]", text)),
    }
    script, count = max(counters.items(), key=lambda item: item[1])
    return script if count > 0 else "unknown"


def evaluate_ocr_quality(
    segments: Iterable[dict],
    *,
    source_language: str = "auto",
    language_spec: str = "",
) -> dict:
    cues = canonicalize_segments(
        segments,
        extraction_source="burned_in_ocr",
        source_language=source_language,
    )
    if not cues:
        return {
            "accepted": False,
            "reason": "ocr_cues_empty",
            "detected_script": "unknown",
            "confidence": 0.0,
        }
    text = " ".join(str(cue.get("source_text") or "") for cue in cues)
    normalized = normalize_cue_text(text)
    visible = [char for char in normalized if not char.isspace()]
    letters = [char for char in visible if char.isalpha()]
    digits = [char for char in visible if char.isdigit()]
    detected_script = detect_text_script(normalized)
    confidence_values: list[float] = []
    for cue in cues:
        if not bool(cue.get("confidence_available")):
            continue
        raw_confidence = cue.get("confidence")
        if raw_confidence in (None, ""):
            continue
        try:
            confidence_value = float(raw_confidence)
        except (TypeError, ValueError):
            continue
        if confidence_value > 1.0:
            confidence_value /= 100.0
        confidence_values.append(max(0.0, min(1.0, confidence_value)))
    confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
    letter_ratio = len(letters) / max(1, len(visible))
    digit_ratio = len(digits) / max(1, len(visible))
    language = str(source_language or "auto").strip().lower().replace("_", "-").split("-", 1)[0]
    expected_scripts = {
        "vi": {"latin"},
        "en": {"latin"},
        "zh": {"cjk"},
        "ja": {"japanese", "cjk"},
        "ko": {"korean"},
        "th": {"thai"},
        "ar": {"arabic"},
        "hi": {"devanagari"},
        "ru": {"cyrillic"},
    }
    reason = ""
    if len(letters) < 2 or letter_ratio < 0.45:
        reason = "ocr_low_letter_ratio"
    elif digit_ratio > 0.32:
        reason = "ocr_numeric_noise"
    elif confidence_values and confidence < 0.28:
        reason = "ocr_low_confidence"
    elif language in expected_scripts and detected_script not in expected_scripts[language]:
        reason = "ocr_wrong_script_for_source_language"
    elif language == "auto" and language_spec and set(language_spec.split("+")) <= {"eng", "osd"}:
        reason = "ocr_auto_language_pack_incomplete"
    elif detected_script == "latin":
        tokens = re.findall(r"[A-Za-z\u00c0-\u024f]+", normalized)
        isolated_ratio = sum(1 for token in tokens if len(token) == 1) / max(1, len(tokens))
        uppercase_ratio = sum(1 for token in tokens if len(token) > 1 and token.isupper()) / max(1, len(tokens))
        if isolated_ratio > 0.40 or (len(tokens) >= 6 and uppercase_ratio > 0.70):
            reason = "ocr_latin_gibberish"
    return {
        "accepted": not bool(reason),
        "reason": reason or "accepted",
        "detected_script": detected_script,
        "confidence": round(confidence, 4),
        "confidence_available": bool(confidence_values),
        "letter_ratio": round(letter_ratio, 4),
        "digit_ratio": round(digit_ratio, 4),
        "cue_count": len(cues),
    }


def _comparison_key(text: str) -> str:
    normalized = normalize_cue_text(text).casefold().replace("\n", "")
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


def _text_similarity(left: str, right: str) -> float:
    left_key = _comparison_key(left)
    right_key = _comparison_key(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    if left_key in right_key or right_key in left_key:
        shorter = min(len(left_key), len(right_key))
        longer = max(len(left_key), len(right_key))
        if shorter >= 3:
            return shorter / max(1, longer)
    return SequenceMatcher(None, left_key, right_key).ratio()


def _looks_like_subtitle(text: str) -> bool:
    key = _comparison_key(text)
    if len(key) < 2:
        return False
    useful = sum(1 for char in key if char.isalnum() or "\u3400" <= char <= "\u9fff")
    return useful >= 2


def group_ocr_observations(
    observations: Iterable[dict],
    *,
    frame_interval_ms: int,
    duration_ms: int = 0,
    source_language: str = "auto",
    similarity_threshold: float = 0.72,
) -> list[dict]:
    interval_ms = max(100, int(frame_interval_ms or 500))
    max_gap_ms = max(interval_ms * 3, 1200)
    ordered = sorted(
        (dict(item or {}) for item in observations or []),
        key=lambda item: int(item.get("timestamp_ms") or 0),
    )
    grouped: list[dict] = []
    active: dict | None = None
    for item in ordered:
        text = normalize_cue_text(item.get("text"))
        if not _looks_like_subtitle(text):
            continue
        timestamp_ms = max(0, int(item.get("timestamp_ms") or 0))
        frame_index = int(item.get("frame_index") or 0)
        confidence = max(0.0, min(1.0, float(item.get("confidence") or 0.0)))
        same_active = bool(
            active
            and timestamp_ms - int(active["last_seen_ms"]) <= max_gap_ms
            and _text_similarity(str(active["source_text"]), text) >= similarity_threshold
        )
        if same_active:
            active["last_seen_ms"] = timestamp_ms
            active["frame_last_seen"] = frame_index
            active["observation_count"] = int(active.get("observation_count") or 1) + 1
            if confidence >= float(active.get("confidence") or 0.0) or len(text) > len(str(active["source_text"])):
                active["source_text"] = text
                active["confidence"] = confidence
            continue
        if active:
            grouped.append(active)
        active = {
            "source_text": text,
            "first_seen_ms": timestamp_ms,
            "last_seen_ms": timestamp_ms,
            "frame_first_seen": frame_index,
            "frame_last_seen": frame_index,
            "confidence": confidence,
            "observation_count": 1,
        }
    if active:
        grouped.append(active)

    raw_segments: list[dict] = []
    filtered_groups = []
    for item in grouped:
        visible_duration = int(item["last_seen_ms"]) - int(item["first_seen_ms"]) + interval_ms
        static_overlay = bool(duration_ms > 0 and visible_duration >= max(8000, int(duration_ms * 0.60)))
        weak_single_frame = bool(
            int(item.get("observation_count") or 0) <= 1
            and float(item.get("confidence") or 0.0) < 0.18
        )
        if static_overlay or weak_single_frame:
            continue
        filtered_groups.append(item)
    for position, item in enumerate(filtered_groups, start=1):
        start_ms = int(item["first_seen_ms"])
        end_ms = int(item["last_seen_ms"]) + interval_ms
        if position < len(filtered_groups):
            end_ms = min(end_ms, int(filtered_groups[position]["first_seen_ms"]))
        if duration_ms > 0:
            end_ms = min(end_ms, int(duration_ms))
        end_ms = max(start_ms + min(400, interval_ms), end_ms)
        raw_segments.append({
            "index": position,
            "source_start_ms": start_ms,
            "source_end_ms": end_ms,
            "source_text": item["source_text"],
            "confidence": item["confidence"],
            "frame_first_seen": item["frame_first_seen"],
            "frame_last_seen": item["frame_last_seen"],
        })
    return canonicalize_segments(
        raw_segments,
        extraction_source="burned_in_ocr",
        source_language=source_language,
    )


def _contains_wide_script(text: str) -> bool:
    return any(
        ("\u3040" <= char <= "\u30ff")
        or ("\u3400" <= char <= "\u9fff")
        or ("\uac00" <= char <= "\ud7af")
        for char in str(text or "")
    )


def _clamp_line(text: str, max_chars: int) -> str:
    clean = str(text or "").strip()
    if len(clean) <= max_chars:
        return clean
    if max_chars <= 3:
        return clean[:max_chars]
    return clean[: max_chars - 3].rstrip() + "..."


def wrap_cue_text(text: str, *, max_chars: int = 42, max_lines: int = 2) -> str:
    clean = normalize_cue_text(text).replace("\n", " ")
    if not clean:
        return ""
    max_chars = max(8, int(max_chars or 42))
    max_lines = max(1, int(max_lines or 2))
    if _contains_wide_script(clean):
        max_chars = min(max_chars, 24)
    words = clean.split()
    if len(words) <= 1 and len(clean) > max_chars:
        lines = [clean[index:index + max_chars] for index in range(0, len(clean), max_chars)]
    else:
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > max_chars and len(lines) < max_lines - 1:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
    if len(lines) > max_lines:
        lines = [*lines[:max_lines - 1], _clamp_line(" ".join(lines[max_lines - 1:]), max_chars)]
    lines = [_clamp_line(line, max_chars) for line in lines[:max_lines]]
    return "\n".join(line for line in lines if line).strip()


def _balanced_two_line_text(text: str, max_chars_per_line: int) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean or len(clean) <= max_chars_per_line:
        return clean
    words = clean.split(" ")
    if len(words) <= 1:
        midpoint = max(1, (len(clean) + 1) // 2)
        return f"{clean[:midpoint]}\n{clean[midpoint:]}".strip()
    best_index = 1
    best_score = float("inf")
    for index in range(1, len(words)):
        left = " ".join(words[:index])
        right = " ".join(words[index:])
        overflow = max(0, len(left) - max_chars_per_line) + max(
            0, len(right) - max_chars_per_line
        )
        score = (overflow * 1000) + abs(len(left) - len(right))
        if score < best_score:
            best_score = score
            best_index = index
    return f"{' '.join(words[:best_index])}\n{' '.join(words[best_index:])}".strip()


def _cue_text_chunks(
    text: str,
    *,
    max_event_chars: int,
    max_chars_per_line: int,
    max_lines: int,
) -> list[str]:
    clean = normalize_cue_text(text).replace("\n", " ")
    if not clean:
        return []
    line_limit = min(max_chars_per_line, 24) if _contains_wide_script(clean) else max_chars_per_line
    event_limit = max(line_limit, min(max_event_chars, line_limit * max_lines))
    separator = " " if " " in clean else ""
    source_tokens = clean.split() if separator else [clean]
    tokens: list[str] = []
    for token in source_tokens:
        if len(token) <= line_limit:
            tokens.append(token)
            continue
        tokens.extend(
            token[index:index + line_limit]
            for index in range(0, len(token), line_limit)
        )

    chunks: list[str] = []
    current = ""
    for token in tokens:
        candidate = token if not current else f"{current}{separator}{token}"
        candidate_lines = wrap_cue_text(
            candidate,
            max_chars=line_limit,
            max_lines=max_lines,
        ).splitlines()
        candidate_fits = bool(
            len(candidate) <= event_limit
            and len(candidate_lines) <= max_lines
            and all(len(line) <= line_limit for line in candidate_lines)
            and "..." not in candidate_lines[-1]
        )
        if current and not candidate_fits:
            chunks.append(current)
            current = token
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def fit_timed_subtitle_segments(
    segments: Iterable[dict],
    *,
    preserve_timestamps: bool = False,
    max_chars_per_line: int = 42,
    max_lines: int = 2,
    metadata_fields: Iterable[str] = (),
    strict_frame_fit: bool = False,
) -> list[dict]:
    """Fit timed text with the canonical SubDub cue rules.

    Synthetic text may be split inside its source window. Source/ASR timing
    stays one-to-one and is only wrapped, matching the Translation SubDub path.
    """

    fitted: list[dict] = []
    selected_fields = tuple(str(field) for field in metadata_fields or ())
    line_chars = max(8, int(max_chars_per_line or 42))
    line_count = max(1, min(2, int(max_lines or 2)))
    for raw in segments or []:
        source = dict(raw or {})
        text = re.sub(r"\s+", " ", str(source.get("text") or source.get("source_text") or "")).strip()
        if not text:
            continue
        start = max(
            0.0,
            float(
                source.get("start")
                if source.get("start") not in (None, "")
                else float(source.get("start_ms") or 0) / 1000.0
            ),
        )
        end = float(
            source.get("end")
            if source.get("end") not in (None, "")
            else float(source.get("end_ms") or 0) / 1000.0
        )
        if end <= start:
            end = start + 1.0
        duration = max(0.1, end - start)
        metadata = {field: source[field] for field in selected_fields if field in source}
        if preserve_timestamps:
            fitted.append(
                {
                    **metadata,
                    "index": int(source.get("index") or len(fitted) + 1),
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "text": _balanced_two_line_text(text, line_chars),
                    "confidence": source.get("confidence"),
                    "translate_missing": bool(source.get("translate_missing")),
                }
            )
            continue

        max_event_chars = max(
            24,
            min(line_chars * line_count, int(duration * 20)),
        )
        if strict_frame_fit:
            chunks = _cue_text_chunks(
                text,
                max_event_chars=max_event_chars,
                max_chars_per_line=line_chars,
                max_lines=line_count,
            ) or [text]
        else:
            chunks: list[str] = []
            current: list[str] = []
            for word in text.split():
                candidate = " ".join([*current, word])
                if current and len(candidate) > max_event_chars:
                    chunks.append(" ".join(current))
                    current = [word]
                else:
                    current.append(word)
            if current:
                chunks.append(" ".join(current))
            chunks = chunks or [text]
        slot = duration / len(chunks)
        for chunk_index, chunk in enumerate(chunks):
            chunk_start = start + (chunk_index * slot)
            natural_end = end if chunk_index == len(chunks) - 1 else start + ((chunk_index + 1) * slot)
            if strict_frame_fit:
                chunk_end = min(
                    end,
                    max(chunk_start + 0.1, min(chunk_start + 7.0, natural_end)),
                )
                wrapped = wrap_cue_text(
                    chunk,
                    max_chars=line_chars,
                    max_lines=line_count,
                )
            else:
                chunk_end = max(
                    chunk_start + 1.0,
                    min(chunk_start + 7.0, natural_end),
                )
                lines: list[str] = []
                line = ""
                for word in chunk.split():
                    candidate = f"{line} {word}".strip()
                    if line and len(candidate) > line_chars and len(lines) < line_count - 1:
                        lines.append(line)
                        line = word
                    else:
                        line = candidate
                if line:
                    lines.append(line)
                wrapped = "\n".join(lines[:line_count]).strip()
            fitted.append(
                {
                    **metadata,
                    "index": len(fitted) + 1,
                    "start": round(chunk_start, 3),
                    "end": round(chunk_end, 3),
                    "text": wrapped,
                    "confidence": source.get("confidence"),
                }
            )
    return fitted


def _srt_timestamp_ms(value: str) -> int:
    text = str(value or "").strip().replace(",", ".")
    try:
        hours, minutes, seconds = text.split(":", 2)
        return max(
            0,
            int(round(((int(hours) * 3600) + (int(minutes) * 60) + float(seconds)) * 1000)),
        )
    except (TypeError, ValueError):
        return -1


def parse_srt_segments(srt_text: str) -> list[dict]:
    """Parse a timed SRT into canonical-input segments without retiming it."""

    body = str(srt_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not body:
        return []
    segments: list[dict] = []
    for raw_block in re.split(r"\n\s*\n", body):
        lines = [line.strip() for line in raw_block.splitlines() if line.strip()]
        timing_index = next((index for index, line in enumerate(lines) if "-->" in line), -1)
        if timing_index < 0:
            continue
        start_text, end_text = [
            part.strip().split()[0]
            for part in lines[timing_index].split("-->", 1)
        ]
        start_ms = _srt_timestamp_ms(start_text)
        end_ms = _srt_timestamp_ms(end_text)
        text = normalize_cue_text("\n".join(lines[timing_index + 1 :]))
        if start_ms < 0 or end_ms <= start_ms or not text:
            continue
        segments.append(
            {
                "index": len(segments) + 1,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "text": text,
            }
        )
    return segments


def apply_translations(
    source_cues: Iterable[dict],
    translations: Iterable[dict],
    *,
    target_language: str,
    max_chars: int = 42,
    max_lines: int = 2,
) -> list[dict]:
    source = canonicalize_segments(
        source_cues,
        extraction_source="canonical",
        source_language="auto",
    )
    translated_items = [dict(item or {}) for item in translations or []]
    by_cue_id = {
        str(item.get("cue_id")): item
        for item in translated_items
        if str(item.get("cue_id") or "").strip()
    }
    by_index = {
        int(item.get("source_index") or item.get("index") or position): item
        for position, item in enumerate(translated_items, start=1)
    }
    output: list[dict] = []
    for cue in source:
        translated = by_cue_id.get(str(cue["cue_id"])) or by_index.get(int(cue["source_index"]))
        translated_text = normalize_cue_text(
            (translated or {}).get("translated_text") or (translated or {}).get("text")
        )
        missing = not bool(translated_text)
        if missing:
            translated_text = str(cue["source_text"])
        translated_text = wrap_cue_text(translated_text, max_chars=max_chars, max_lines=max_lines)
        output.append({
            **cue,
            "translated_text": translated_text,
            "target_language": str(target_language or ""),
            "text": translated_text,
            "translate_missing": missing,
            "start": round(int(cue["source_start_ms"]) / 1000.0, 3),
            "end": round(int(cue["source_end_ms"]) / 1000.0, 3),
        })
    return output


def timeline_signature(cues: Iterable[dict]) -> list[tuple[str, int, int]]:
    canonical = canonicalize_segments(cues, extraction_source="canonical")
    return [
        (str(cue["cue_id"]), int(cue["source_start_ms"]), int(cue["source_end_ms"]))
        for cue in canonical
    ]


def same_timeline(left: Iterable[dict], right: Iterable[dict]) -> bool:
    return timeline_signature(left) == timeline_signature(right)


def duration_matches_source(
    source_duration: Any,
    output_duration: Any,
    *,
    minimum_tolerance: float = 0.35,
    relative_tolerance: float = 0.0,
) -> dict:
    try:
        source = max(0.0, float(source_duration or 0.0))
        output = max(0.0, float(output_duration or 0.0))
    except (TypeError, ValueError):
        return {"ok": False, "source_duration": 0.0, "output_duration": 0.0, "tolerance": 0.0}
    tolerance = max(float(minimum_tolerance), source * float(relative_tolerance))
    delta = abs(output - source)
    return {
        "ok": bool(source > 0 and output > 0 and delta <= tolerance + 1e-9),
        "source_duration": source,
        "output_duration": output,
        "tolerance": tolerance,
        "delta": delta,
    }
