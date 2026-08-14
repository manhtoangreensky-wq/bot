"""Pure source semantic master construction for offline replay."""

from __future__ import annotations

from copy import deepcopy
import re
import unicodedata
from typing import Any, Iterable

from .contracts import finalize_artifact
from .fingerprints import sha256_hex, short_id, source_fingerprint


ALIGNMENT_TRUTHS = {"word_aligned", "segment_timed", "alignment_unavailable"}


def _text(value: Any) -> str:
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", str(value or "")).strip())


def _offset_for_segment(item: dict[str, Any]) -> int:
    for key in ("chunk_offset_ms", "original_start_ms", "timeline_offset_ms"):
        if item.get(key) is not None:
            return int(item.get(key) or 0)
    chunk = item.get("chunk")
    if isinstance(chunk, dict):
        for key in ("original_start_ms", "start_ms", "offset_ms"):
            if chunk.get(key) is not None:
                return int(chunk.get(key) or 0)
    return 0


def _absolute_bounds(item: dict[str, Any]) -> tuple[int, int]:
    if item.get("local_start_ms") is not None or item.get("local_end_ms") is not None:
        offset = _offset_for_segment(item)
        start = int(item.get("local_start_ms") or 0) + offset
        end = int(item.get("local_end_ms") or 0) + offset
    else:
        start = int(item.get("start_ms") or 0)
        end = int(item.get("end_ms") or 0)
    return start, end


def _normalise_selection(selection: Any) -> dict[str, Any]:
    if isinstance(selection, dict):
        result = {str(key): deepcopy(value) for key, value in selection.items()}
        result.setdefault("selected", "asr")
        result.setdefault("reason", "fixture_or_injected_source")
        result.setdefault("timed_source_validated", result.get("selected") != "asr")
        return result
    selected = str(selection or "asr")
    return {
        "selected": selected,
        "reason": "fixture_or_injected_source",
        "timed_source_validated": selected in {"user_timed_subtitle", "embedded_subtitle"},
    }


def _valid_word_timing(words: Any, start: int, end: int) -> bool:
    if not isinstance(words, list) or not words:
        return False
    previous = start
    for word in words:
        if not isinstance(word, dict):
            return False
        word_start = int(word.get("start_ms", -1))
        word_end = int(word.get("end_ms", -1))
        if word_start < start or word_end > end or word_end <= word_start or word_start < previous:
            return False
        previous = word_end
    return True


def _normalise_segment(item: dict[str, Any], source_id: str, position: int) -> dict[str, Any]:
    start, end = _absolute_bounds(item)
    if start < 0 or end <= start:
        raise ValueError("invalid_segment_timeline")
    raw = _text(item.get("source_text_raw", item.get("text", "")))
    if not raw:
        raise ValueError("empty_source_segment")
    supplied_id = str(item.get("segment_id") or "")
    segment_id = supplied_id if supplied_id.startswith("seg-") else short_id(
        "seg",
        {"source_id": source_id, "position": position, "start_ms": start, "end_ms": end, "text": raw},
        16,
    )
    words = deepcopy(item.get("words") or [])
    normalized = {
        "segment_id": segment_id,
        "source_index": int(item.get("source_index", position)),
        "start_ms": start,
        "end_ms": end,
        "speaker_id": str(item.get("speaker_id") or "speaker_01"),
        "source_text_raw": raw,
        "source_text_normalized": raw,
        "words": words,
        "confidence": float(item.get("confidence", 0.0) or 0.0),
        "pause_before_ms": max(0, int(item.get("pause_before_ms", 0) or 0)),
        "pause_after_ms": max(0, int(item.get("pause_after_ms", 0) or 0)),
        "proper_nouns": list(item.get("proper_nouns") or []),
        "numbers": list(item.get("numbers") or []),
        "emotion": str(item.get("emotion") or "neutral"),
    }
    return normalized


def _normalise_media(media: dict[str, Any] | None) -> dict[str, Any]:
    supplied = dict(media or {})
    result = {
        "container": str(supplied.get("container") or "mp4"),
        "duration_ms": int(supplied.get("duration_ms", 0) or 0),
        "width": int(supplied.get("width", 0) or 0),
        "height": int(supplied.get("height", 0) or 0),
        "frame_rate": str(supplied.get("frame_rate") or "0/1"),
        "rotation": int(supplied.get("rotation", 0) or 0),
        "video_stream_present": bool(supplied.get("video_stream_present", supplied.get("has_video", True))),
        "audio_streams": deepcopy(supplied.get("audio_streams") or ([{"language": "und"}] if supplied.get("has_audio") else [])),
        "embedded_subtitle_streams": deepcopy(supplied.get("embedded_subtitle_streams") or []),
        "input_size_bytes": int(supplied.get("input_size_bytes", supplied.get("bytes", 0)) or 0),
        "full_decode": bool(supplied.get("full_decode", True)),
    }
    if supplied.get("path"):
        # A relative fixture reference is safe and useful for replay; absolute
        # host paths never enter the public artifact identity.
        result["fixture_ref"] = str(supplied["path"])
    return result


def _normalise_regions(regions: Iterable[dict[str, Any]] | None, segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if regions is None:
        return [
            {
                "speech_region_id": short_id("region", {"segment_id": item["segment_id"]}, 16),
                "local_start_ms": item["start_ms"],
                "local_end_ms": item["end_ms"],
                "original_start_ms": item["start_ms"],
                "original_end_ms": item["end_ms"],
            }
            for item in segments
        ]
    result = []
    for position, item in enumerate(regions, 1):
        item = dict(item)
        offset = _offset_for_segment(item)
        local_start = int(item.get("local_start_ms", item.get("start_ms", 0)) or 0)
        local_end = int(item.get("local_end_ms", item.get("end_ms", 0)) or 0)
        original_start = int(item.get("original_start_ms", local_start + offset) or 0)
        original_end = int(item.get("original_end_ms", local_end + offset) or 0)
        if original_start < 0 or original_end <= original_start:
            raise ValueError("invalid_speech_region")
        result.append(
            {
                "speech_region_id": str(item.get("speech_region_id") or short_id("region", {"position": position, "start": original_start, "end": original_end}, 16)),
                "local_start_ms": local_start,
                "local_end_ms": local_end,
                "original_start_ms": original_start,
                "original_end_ms": original_end,
            }
        )
    return result


def build_source_semantic_master(
    *,
    scope_id: str,
    source_id: str,
    source_language: str,
    source_selection: Any,
    alignment_truth: str,
    media: dict[str, Any],
    segments: Iterable[dict[str, Any]],
    job_id: str | None = None,
    speech_regions: Iterable[dict[str, Any]] | None = None,
    request_contract_fingerprint: str | None = None,
    created_at: str = "1970-01-01T00:00:00Z",
) -> dict[str, Any]:
    source_id = str(source_id or "").strip()
    scope_id = str(scope_id or "").strip()
    if not source_id or not scope_id:
        raise ValueError("source_and_scope_required")
    normalised_segments = [
        _normalise_segment(dict(item), source_id, position)
        for position, item in enumerate(segments, 1)
    ]
    normalised_segments.sort(key=lambda item: (item["start_ms"], item["end_ms"], item["source_index"]))
    for previous, current in zip(normalised_segments, normalised_segments[1:]):
        if current["start_ms"] < previous["start_ms"]:
            raise ValueError("segments_not_monotonic")
    media_value = _normalise_media(media)
    requested_alignment = str(alignment_truth or "alignment_unavailable")
    if requested_alignment not in ALIGNMENT_TRUTHS:
        raise ValueError("invalid_alignment_truth")
    if requested_alignment == "word_aligned" and not all(
        _valid_word_timing(item["words"], item["start_ms"], item["end_ms"]) for item in normalised_segments
    ):
        requested_alignment = "segment_timed" if normalised_segments else "alignment_unavailable"
    if requested_alignment == "segment_timed" and not normalised_segments:
        requested_alignment = "alignment_unavailable"
    selection = _normalise_selection(source_selection)
    source_identity = {
        "source_id": source_id,
        "source_language": str(source_language or "auto"),
        "media": media_value,
        "segments": normalised_segments,
        "selection": selection,
    }
    source_hash = source_fingerprint(source_id, {**media_value, "segments": normalised_segments, "selection": selection})
    request_hash = str(request_contract_fingerprint or sha256_hex({"scope_id": scope_id, "source": source_identity}))
    job_id = str(job_id or short_id("job", {"scope_id": scope_id, "source_hash": source_hash, "request_hash": request_hash}, 20))
    artifact = {
        "schema_name": "source_semantic_master",
        "job_id": job_id,
        "source_id": source_id,
        "source_language": str(source_language or "auto"),
        "source_fingerprint": source_hash,
        "input_fingerprint": source_hash,
        "request_contract_fingerprint": request_hash,
        "media": media_value,
        "source_selection": selection,
        "alignment_truth": requested_alignment,
        "speech_regions": _normalise_regions(speech_regions, normalised_segments),
        "segments": normalised_segments,
        "qc_summary": {
            "status": "PASS" if normalised_segments else "FAIL",
            "blocking_failures": [] if normalised_segments else ["empty_segments"],
            "warnings": [] if requested_alignment != "alignment_unavailable" else ["alignment_unavailable"],
        },
        "request_fingerprint": request_hash,
        "created_at": str(created_at),
        "retention_class": "subdub_semantic_72h",
    }
    return finalize_artifact(
        artifact,
        scope_id=scope_id,
        root_source_id=source_id,
        source_segment_ids=[item["segment_id"] for item in normalised_segments],
        upstream_fingerprints=[source_hash, request_hash],
    )


build_source_master = build_source_semantic_master


def validate_source_master(artifact: dict[str, Any]) -> bool:
    return artifact.get("qc_summary", {}).get("status") == "PASS" and artifact.get("alignment_truth") in ALIGNMENT_TRUTHS


__all__ = ["ALIGNMENT_TRUTHS", "build_source_master", "build_source_semantic_master", "validate_source_master"]
