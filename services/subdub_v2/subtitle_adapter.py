"""Profile-driven subtitle copy derivation with source-locked timing."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from .contracts import finalize_artifact
from .fingerprints import sha256_hex, short_id
from .profiles import display_width, get_subtitle_profile, subtitle_text_qc, wrap_subtitle_text
from .translation_master import translation_entry_for_segment


def _timecode_srt(milliseconds: int) -> str:
    milliseconds = max(0, int(milliseconds))
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _timecode_vtt(milliseconds: int) -> str:
    return _timecode_srt(milliseconds).replace(",", ".")


def build_subtitle_copy(
    source_master: dict[str, Any],
    translation_master: dict[str, Any] | None = None,
    profile: str | Any | None = None,
    profile_name: str | None = None,
    glyph_checker: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    selected_profile = get_subtitle_profile(profile_name or profile or source_master.get("source_language"))
    cues: list[dict[str, Any]] = []
    blocking_failures: list[str] = []
    translated = translation_master is not None
    for position, segment in enumerate(source_master.get("segments", []), 1):
        entry = translation_entry_for_segment(translation_master, segment["segment_id"]) if translation_master else None
        if translated and entry is None:
            blocking_failures.append(f"missing_translation:{segment['segment_id']}")
            continue
        text = str(
            (entry or {}).get("semantic_translation")
            or segment.get("source_text_normalized")
            or segment.get("source_text_raw")
            or ""
        ).strip()
        if not text:
            blocking_failures.append(f"empty_text:{segment['segment_id']}")
            continue
        lines = wrap_subtitle_text(text, selected_profile)
        text_qc = subtitle_text_qc(text, lines, segment["end_ms"] - segment["start_ms"], selected_profile, glyph_checker)
        for key in ("max_lines_pass", "cpl_pass", "cps_pass", "unicode_pass", "rendered_glyph_pass"):
            if not text_qc[key]:
                blocking_failures.append(f"{key}:{segment['segment_id']}")
        meaning_id = (entry or {}).get("meaning_id") or f"source_meaning:{segment['segment_id']}"
        cue = {
            "derived_id": short_id("subtitle", {"segment_id": segment["segment_id"], "profile": selected_profile.name, "text": text}, 16),
            "segment_id": segment["segment_id"],
            "meaning_id": meaning_id,
            "start_ms": int(segment["start_ms"]),
            "end_ms": int(segment["end_ms"]),
            "subtitle_text": text,
            "lines": lines,
            "cpl": [display_width(line, selected_profile.language) for line in lines],
            "cps": text_qc["cps"],
            "adaptation": "translated_condense" if translated else "source_copy",
            "qc": text_qc,
        }
        cues.append(cue)
    cues.sort(key=lambda item: (item["start_ms"], item["end_ms"], item["segment_id"]))
    srt = "\n\n".join(
        f"{index}\n{_timecode_srt(cue['start_ms'])} --> {_timecode_srt(cue['end_ms'])}\n{chr(10).join(cue['lines'])}"
        for index, cue in enumerate(cues, 1)
    )
    vtt = "WEBVTT\n\n" + "\n\n".join(
        f"{_timecode_vtt(cue['start_ms'])} --> {_timecode_vtt(cue['end_ms'])}\n{chr(10).join(cue['lines'])}"
        for cue in cues
    )
    output_srt_id = short_id("srt", srt, 16)
    output_vtt_id = short_id("vtt", vtt, 16)
    source_bounds = [(item["start_ms"], item["end_ms"]) for item in source_master.get("segments", [])]
    copy_bounds = [(item["start_ms"], item["end_ms"]) for item in cues]
    timeline_equal = source_bounds == copy_bounds and not blocking_failures
    artifact = {
        "schema_name": "subtitle_copy",
        "source_master_artifact_id": source_master["artifact_id"],
        "translation_master_artifact_id": translation_master["artifact_id"] if translation_master else "none",
        "subtitle_profile": selected_profile.name,
        "cues": cues,
        "outputs": {
            "srt_artifact_id": output_srt_id,
            "vtt_artifact_id": output_vtt_id,
            "ass_artifact_id": "none",
            "srt_text": srt,
            "vtt_text": vtt,
        },
        "qc_summary": {
            "status": "PASS" if timeline_equal and not blocking_failures else "FAIL",
            "timeline_equal_to_source": timeline_equal,
            "max_lines_pass": not any(item.startswith("max_lines_pass:") for item in blocking_failures),
            "cpl_pass": not any(item.startswith("cpl_pass:") for item in blocking_failures),
            "cps_pass": not any(item.startswith("cps_pass:") for item in blocking_failures),
            "unicode_pass": not any(item.startswith("unicode_pass:") for item in blocking_failures),
            "rendered_glyph_pass": not any(item.startswith("rendered_glyph_pass:") for item in blocking_failures),
            "blocking_failures": blocking_failures,
            "warnings": [],
        },
        "input_fingerprint": sha256_hex({"source": source_master["artifact_id"], "translation": (translation_master or {}).get("artifact_id", "none"), "profile": selected_profile.name}),
        "retention_class": "subdub_semantic_72h",
    }
    parents = [translation_master["artifact_id"]] if translation_master else []
    return finalize_artifact(
        artifact,
        scope_id=source_master["scope_id"],
        root_source_id=source_master["root_source_id"],
        parent_artifact_ids=parents,
        source_segment_ids=[item["segment_id"] for item in cues],
        derived_meaning_ids=[item["meaning_id"] for item in cues],
        upstream_fingerprints=[source_master["output_fingerprint"], (translation_master or {}).get("output_fingerprint", "none")],
    )


def render_srt(subtitle_copy: dict[str, Any]) -> str:
    return str(subtitle_copy.get("outputs", {}).get("srt_text", ""))


def render_vtt(subtitle_copy: dict[str, Any]) -> str:
    return str(subtitle_copy.get("outputs", {}).get("vtt_text", ""))


build_source_subtitle_copy = build_subtitle_copy
adapt_subtitle_copy = build_subtitle_copy

__all__ = ["adapt_subtitle_copy", "build_source_subtitle_copy", "build_subtitle_copy", "render_srt", "render_vtt"]
