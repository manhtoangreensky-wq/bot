"""Deterministic duration planning and safe TTS transport chunking."""

from __future__ import annotations

from copy import deepcopy
import unicodedata
from typing import Any, Callable, Iterable

from .contracts import finalize_artifact
from .fingerprints import sha256_hex, short_id
from .profiles import get_audio_profile


_BREAK_AFTER = set(".!?;:。！？；：\n")


def _grapheme_boundaries(text: str) -> list[int]:
    boundaries = [0]
    for index, char in enumerate(str(text), 1):
        if index == 1 or not (unicodedata.combining(char) or char in "\ufe0e\ufe0f"):
            boundaries.append(index)
        else:
            boundaries[-1] = index
    if boundaries[-1] != len(text):
        boundaries.append(len(text))
    return sorted(set(boundaries))


def _largest_boundary(text: str, start: int, max_codepoints: int, max_bytes: int) -> int:
    limit = min(len(text), start + max(1, int(max_codepoints)))
    candidates = [item for item in _grapheme_boundaries(text) if start < item <= limit and len(text[start:item].encode("utf-8")) <= max_bytes]
    if not candidates:
        raise ValueError("tts_transport_limit_smaller_than_grapheme")
    end = max(candidates)
    tail = text[start:end]
    tag_start = tail.rfind("<")
    if tag_start >= 0 and tail.rfind(">") < tag_start and start + tag_start > start:
        end = start + tag_start
    entity_start = tail.rfind("&")
    if entity_start >= 0 and tail.rfind(";") < entity_start and start + entity_start > start:
        end = start + entity_start
    return end


def split_tts_transport_chunks(
    text: str,
    *,
    max_codepoints: int = 4000,
    max_bytes: int = 64 * 1024,
    segment_id: str = "segment-transport",
) -> list[dict[str, Any]]:
    """Split only transport payloads while preserving the exact source text."""
    value = unicodedata.normalize("NFC", str(text or ""))
    if not value:
        return []
    if max_codepoints <= 0 or max_bytes <= 0:
        raise ValueError("invalid_tts_transport_limits")
    pieces: list[tuple[int, int]] = []
    start = 0
    while start < len(value):
        hard_end = _largest_boundary(value, start, max_codepoints, max_bytes)
        if hard_end < len(value):
            preferred: list[int] = []
            for boundary in _grapheme_boundaries(value):
                if start < boundary <= hard_end:
                    previous = value[boundary - 1]
                    next_char = value[boundary] if boundary < len(value) else ""
                    # Break before whitespace, or after punctuation. Breaking
                    # before whitespace keeps the whitespace in the next
                    # fragment and makes concatenation lossless without a
                    # trailing space in the prior fragment.
                    if next_char.isspace() or previous in _BREAK_AFTER:
                        preferred.append(boundary)
            if preferred:
                hard_end = max(preferred)
            while hard_end > start and value[hard_end - 1].isspace():
                hard_end -= 1
            if hard_end == start:
                hard_end = _largest_boundary(value, start, max_codepoints, max_bytes)
        pieces.append((start, hard_end))
        start = hard_end
    group_id = short_id("ttsgrp", {"segment_id": segment_id, "text": value}, 20)
    total = len(pieces)
    source_hash = sha256_hex(value)
    result: list[dict[str, Any]] = []
    for sequence, (start, end) in enumerate(pieces, 1):
        fragment = value[start:end]
        result.append(
            {
                "segment_id": segment_id,
                "transport_group_id": group_id,
                "transport_sequence": sequence,
                "transport_total": total,
                "text": fragment,
                "text_utf8_sha256": sha256_hex(fragment),
                "source_text_utf8_sha256": source_hash,
                "text_start_codepoint": start,
                "text_end_codepoint": end,
                "max_payload_bytes": max_bytes,
                "provider_speed": 1.0,
                "idempotency_key": sha256_hex({"provider_alias": "fixture_tts", "group": group_id, "sequence": sequence, "text": fragment}),
            }
        )
    if "".join(item["text"] for item in result) != value:
        raise AssertionError("tts_transport_reassembly_mismatch")
    return result


def _candidate_duration(candidate: dict[str, Any], text: str) -> int:
    value = candidate.get("measured_duration_ms", candidate.get("predicted_duration_ms"))
    if value is not None:
        return max(1, int(value))
    return max(1, int(len(text) * 55))


def _candidate_text(candidate: Any, fallback: str) -> str:
    if isinstance(candidate, dict):
        return str(candidate.get("text", candidate.get("spoken_text", fallback)) or "").strip()
    return str(candidate or fallback).strip()


def _pick_candidate(entry: dict[str, Any], window_ms: int) -> tuple[dict[str, Any], str]:
    fallback = str(entry.get("semantic_translation") or "").strip()
    raw_candidates = entry.get("dub_candidates") or [{"text": fallback}]
    candidates: list[dict[str, Any]] = []
    for position, raw in enumerate(raw_candidates, 1):
        item = dict(raw) if isinstance(raw, dict) else {"text": raw}
        text = _candidate_text(item, fallback)
        if not text:
            continue
        item["text"] = text
        item["measured_duration_ms"] = _candidate_duration(item, text)
        item["candidate_id"] = str(item.get("candidate_id") or short_id("candidate", {"entry": entry.get("meaning_id"), "position": position, "text": text}, 16))
        candidates.append(item)
    fitting = [item for item in candidates if item["measured_duration_ms"] <= window_ms]
    if fitting:
        selected = min(fitting, key=lambda item: (window_ms - item["measured_duration_ms"], item["candidate_id"]))
        return selected, "candidate_select" if len(candidates) > 1 else "pass"
    rewrite = [item for item in candidates if item.get("fit_strategy") == "semantic_rewrite" or item.get("rewritten")]
    if rewrite:
        selected = min(rewrite, key=lambda item: item["measured_duration_ms"])
        if selected["measured_duration_ms"] <= window_ms:
            return selected, "semantic_rewrite"
    if candidates:
        selected = min(candidates, key=lambda item: item["measured_duration_ms"])
        return selected, "waiting_review"
    return {"candidate_id": "none", "text": fallback, "measured_duration_ms": 0}, "waiting_review"


def build_dub_script(
    source_master: dict[str, Any],
    translation_master: dict[str, Any],
    *,
    audio_profile: str | Any | None = None,
    candidates_by_segment: dict[str, Iterable[dict[str, Any]]] | None = None,
    rewrite_candidate: Callable[[dict[str, Any], int], Iterable[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    profile = get_audio_profile(audio_profile or translation_master.get("target_language"))
    translation_entries = {item["segment_id"]: item for item in translation_master.get("entries", [])}
    entries: list[dict[str, Any]] = []
    overlap_count = 0
    truncation_count = 0
    speed_1x_count = 0
    previous_end = -1
    for segment in source_master.get("segments", []):
        translation = translation_entries.get(segment["segment_id"])
        if translation is None:
            truncation_count += 1
            continue
        window_start = int(segment["start_ms"])
        window_end = int(segment["end_ms"])
        window_ms = window_end - window_start
        item = deepcopy(translation)
        if candidates_by_segment and segment["segment_id"] in candidates_by_segment:
            item["dub_candidates"] = list(candidates_by_segment[segment["segment_id"]])
        if rewrite_candidate is not None:
            item["dub_candidates"] = list(item.get("dub_candidates") or []) + list(rewrite_candidate(item, window_ms) or [])
        selected, strategy = _pick_candidate(item, window_ms)
        measured = int(selected.get("measured_duration_ms", 0) or 0)
        if window_start < previous_end:
            overlap_count += 1
        if strategy == "waiting_review" or measured <= 0 or measured > window_ms:
            truncation_count += 1
        else:
            speed_1x_count += 1
        entries.append(
            {
                "derived_id": short_id("dub", {"segment_id": segment["segment_id"], "meaning_id": translation["meaning_id"], "profile": profile.name}, 16),
                "segment_id": segment["segment_id"],
                "meaning_id": translation["meaning_id"],
                "speaker_id": segment.get("speaker_id", "speaker_01"),
                "window_start_ms": window_start,
                "window_end_ms": window_end,
                "candidate_ids": [str(candidate.get("candidate_id")) for candidate in item.get("dub_candidates", []) if isinstance(candidate, dict)],
                "selected_candidate_id": selected["candidate_id"],
                "spoken_text": selected["text"],
                "predicted_duration_ms": int(selected.get("predicted_duration_ms", measured) or measured),
                "measured_duration_ms": measured,
                "provider_speech_rate": profile.provider_speech_rate,
                "post_tempo": profile.post_tempo,
                "fit_strategy": strategy,
                "complete_utterance_required": True,
                "overlap_allowed": False,
                "emotion": segment.get("emotion", "neutral"),
                "pause_after_ms": int(segment.get("pause_after_ms", 0) or 0),
            }
        )
        previous_end = max(previous_end, window_end)
    status = "PASS" if entries and overlap_count == 0 and truncation_count == 0 else "FAIL"
    artifact = {
        "schema_name": "dub_script",
        "source_master_artifact_id": source_master["artifact_id"],
        "translation_master_artifact_id": translation_master["artifact_id"],
        "duration_fit_profile": profile.name,
        "entries": entries,
        "qc_summary": {
            "status": status,
            "all_segments_generated": len(entries) == len(source_master.get("segments", [])),
            "all_utterances_complete": truncation_count == 0,
            "overlap_count": overlap_count,
            "truncated_count": truncation_count,
            "speed_1x_count": speed_1x_count,
            "meaning_consistency_pass": {item["meaning_id"] for item in entries} == {item["meaning_id"] for item in translation_master.get("entries", [])},
            "blocking_failures": (["duration_or_overlap"] if status != "PASS" else []),
        },
        "input_fingerprint": sha256_hex({"source": source_master["artifact_id"], "translation": translation_master["artifact_id"], "profile": profile.name}),
        "retention_class": "subdub_semantic_72h",
    }
    return finalize_artifact(
        artifact,
        scope_id=source_master["scope_id"],
        root_source_id=source_master["root_source_id"],
        parent_artifact_ids=[translation_master["artifact_id"]],
        source_segment_ids=[item["segment_id"] for item in entries],
        derived_meaning_ids=[item["meaning_id"] for item in entries],
        upstream_fingerprints=[source_master["output_fingerprint"], translation_master["output_fingerprint"]],
    )


def duration_fit_metrics(dub_script: dict[str, Any]) -> dict[str, Any]:
    entries = dub_script.get("entries", [])
    overlap = 0
    previous_end = -1
    for item in entries:
        if item["window_start_ms"] < previous_end:
            overlap += 1
        previous_end = max(previous_end, item["window_end_ms"])
    return {
        "dub_complete_utterance_rate": sum(item["fit_strategy"] != "waiting_review" for item in entries) / len(entries) if entries else 0.0,
        "dub_overlap_count": overlap,
        "dub_truncation_count": sum(item["measured_duration_ms"] > item["window_end_ms"] - item["window_start_ms"] for item in entries),
        "dub_speed_deviation_max": max((abs(float(item["post_tempo"]) - 1.0) for item in entries), default=0.0),
    }


plan_duration_fit = build_dub_script
build_transport_chunks = split_tts_transport_chunks

__all__ = ["build_dub_script", "build_transport_chunks", "duration_fit_metrics", "plan_duration_fit", "split_tts_transport_chunks"]
