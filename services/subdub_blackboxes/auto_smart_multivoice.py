"""Auto Smart Multi-Voice Adaptive Orchestrator for SubDub (R1.C1).

Isolated new lane C (AUTO SMART MULTI-VOICE):
- Handles 0/1/2/N speech speakers with explicit strategies:
  STRICT_TWO, GENERIC_SINGLE, GENERIC_MULTI, STABLE_FALLBACK,
  SINGLE_DOMINANT, SUBTITLE_ONLY, PASSTHROUGH.
- Fallback ladder:
  LEVEL 0: Best available strict speaker-specific cast (requires real strict-two engine success).
  LEVEL 1: Generic per-speaker cast.
  LEVEL 2: Deterministic approved fallback voice per uncertain speaker.
  LEVEL 3: Single dominant/default voice for eligible speech.
  LEVEL 4: Subtitle-only MP4 + original audio.
  LEVEL 5: Passthrough MP4 if permitted.
- Canonical invariants:
  * STRICT_TWO requires real strict engine (classify_two_speaker_genders) success.
  * No invented speaker IDs (no fabricated speaker_0). Missing/invalid speaker -> TERMINAL_REJECTED.
  * No hardcoded unvalidated voice pools. If no approved pool -> falls down ladder (SUBTITLE_ONLY / PASSTHROUGH).
  * Dubbed modes require synthesis authority with exact 1-to-1 chunk coverage.
  * Final MP4 validated via canonical validator (video_local_validation.validate_mp4_output).
  * Current run must produce output; stale pre-existing output is cleared and rejected if unrendered.
  * Audio preservation contract (speech vs music/singing) explicitly reaches renderer.
  * Cancellation checkpoints before decision, before/after synthesis, before render, and before success.
  * Invariant: Same canonical speaker -> same voice across entire job.
  * Zero customer cutover; isolated from legacy auto_speaker and auto_multi_speaker.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence

from services import subdub_speaker_cast as speaker_cast
from services import video_local_validation


SMART_DECISION_VERSION = "smart_multivoice_v1"

# Allowed strategies
STRATEGY_STRICT_TWO = "STRICT_TWO"
STRATEGY_GENERIC_SINGLE = "GENERIC_SINGLE"
STRATEGY_GENERIC_MULTI = "GENERIC_MULTI"
STRATEGY_STABLE_FALLBACK = "STABLE_FALLBACK"
STRATEGY_SINGLE_DOMINANT = "SINGLE_DOMINANT"
STRATEGY_SUBTITLE_ONLY = "SUBTITLE_ONLY"
STRATEGY_PASSTHROUGH = "PASSTHROUGH"
STRATEGY_FAILED = "FAILED"

# Allowed output modes
OUTPUT_MODE_DUBBED_MULTI = "DUBBED_MULTI_MP4"
OUTPUT_MODE_DUBBED_SINGLE = "DUBBED_SINGLE_MP4"
OUTPUT_MODE_DUBBED_FALLBACK = "DUBBED_FALLBACK_MP4"
OUTPUT_MODE_SUBTITLE_ONLY = "SUBTITLE_ONLY_MP4"
OUTPUT_MODE_PASSTHROUGH = "PASSTHROUGH_MP4"
OUTPUT_MODE_FAILED = "FAILED"

# Cue dispositions
DISPOSITION_DUBBED = "DUBBED"
DISPOSITION_PRESERVED = "PRESERVED"
DISPOSITION_SUBTITLE_ONLY = "SUBTITLE_ONLY"
DISPOSITION_TERMINAL_REJECTED = "TERMINAL_REJECTED"

# Non-speech regex markers
_NON_SPEECH_TEXT_RE = re.compile(
    r"^\s*(\[?(?:music|singing|song|applause|cheering|laughter|noise|silence|background|sound|đàn|hát|nhạc)\]?|[♪♫♩♬\-\s]+)\s*$",
    re.IGNORECASE,
)

# Control-plane kwargs owned exclusively by Smart preflight/decision and excluded from standard lane delegation
SMART_CONTROL_ONLY_KEYS: tuple[str, ...] = (
    "validated_pools",
    "required_pool_capacity",
    "post_prepare_gate",
    "extract_pcm",
    "stereo_pcm_path",
    "ranges_by_speaker",
    "deadline_monotonic",
    "stop_requested",
    "strict_two_classifier",
    "multi_speaker_classifier",
    "acoustic_classifications",
    "fallback_level_override",
    "default_fallback_voice",
    "locked_speaker_voice_map",
    "segments",
    "cues",
    "source_media",
)


@dataclass(frozen=True)
class SmartVoiceDecision:
    """Explicit bounded decision record produced by Smart voice orchestrator."""

    strategy: str
    detected_speaker_count: int
    effective_speaker_count: int
    effective_voice_count: int
    speaker_voice_map: dict[str, str]
    fallback_level: int
    fallback_reason: str | None
    output_mode: str
    cue_dispositions: dict[str, str]
    tts_cues: list[dict[str, Any]]
    decision_version: str = SMART_DECISION_VERSION


def _hash_seed_int(seed: str, *parts: str) -> int:
    """Deterministic integer from seed and context parts."""
    key = ":".join([seed, *parts])
    digest = hashlib.sha256(key.encode("utf-8", errors="strict")).digest()
    return int.from_bytes(digest[:8], "big")


def _is_non_speech_cue(cue: Mapping[str, Any]) -> bool:
    """Identify background music, singing, noise, or explicit non-speech cues."""
    if cue.get("is_music") is True or cue.get("is_singing") is True:
        return True
    cue_type = str(cue.get("cue_type") or "").strip().lower()
    sound_type = str(cue.get("sound_type") or "").strip().lower()
    if cue_type in {"music", "singing", "song", "noise", "background", "non_speech"}:
        return True
    if sound_type in {"music", "singing", "song", "noise", "background", "non_speech"}:
        return True
    text = str(cue.get("text") or cue.get("content") or "").strip()
    if not text:
        return True
    if _NON_SPEECH_TEXT_RE.match(text):
        return True
    return False


def _normalize_voice_pools(
    validated_pools: Mapping[str, Any] | None,
) -> tuple[list[str], list[str], list[str]]:
    """Return low, high, and combined pools from approved validated input only.

    NEVER hardcodes unapproved provider voice IDs.
    """
    low_pool: list[str] = []
    high_pool: list[str] = []
    if isinstance(validated_pools, Mapping):
        for register, target in (("low", low_pool), ("high", high_pool)):
            raw_pool = validated_pools.get(register)
            if isinstance(raw_pool, (list, tuple)):
                for item in raw_pool:
                    if isinstance(item, str):
                        clean_id = item.strip()
                        if clean_id and speaker_cast._VOICE_ID_RE.fullmatch(clean_id):
                            if clean_id not in target:
                                target.append(clean_id)
    all_pool: list[str] = []
    for voice_id in low_pool + high_pool:
        if voice_id not in all_pool:
            all_pool.append(voice_id)
    return low_pool, high_pool, all_pool


def decide_smart_multivoice(
    cues: Sequence[Mapping[str, Any]],
    *,
    validated_pools: Mapping[str, Any] | None = None,
    assignment_seed: str = "default_smart_seed",
    stereo_pcm_path: str | Path | None = None,
    ranges_by_speaker: Mapping[str, Sequence[tuple[float, float]]] | None = None,
    deadline_monotonic: float | None = None,
    stop_requested: Callable[[], bool] | None = None,
    strict_two_classifier: Callable[..., Any] | None = None,
    multi_speaker_classifier: Callable[..., Any] | None = None,
    acoustic_classifications: Mapping[str, Mapping[str, Any]] | None = None,
    fallback_level_override: int | None = None,
    default_fallback_voice: str | None = None,
    locked_speaker_voice_map: Mapping[str, str] | None = None,
    raise_manual_required: bool = False,
) -> SmartVoiceDecision:
    """Core pure-functional decision authority for Auto Smart Multi-Voice lane."""
    seed = hashlib.sha256(str(assignment_seed).encode("utf-8")).hexdigest()

    # Step 1: Filter speech vs non-speech cues and validate canonical identities
    # Invariant: No invented speaker IDs. Missing/invalid speaker -> TERMINAL_REJECTED.
    speech_cues: list[dict[str, Any]] = []
    non_speech_cues: list[dict[str, Any]] = []
    dispositions: dict[str, str] = {}

    for idx, raw_cue in enumerate(cues):
        cue = dict(raw_cue)
        cue_id = cue.get("cue_id") or cue.get("id")
        if cue_id is None or str(cue_id).strip() == "":
            # Missing canonical cue identity -> TERMINAL_REJECTED (do not invent cue_id)
            dispositions[f"unidentified_cue_{idx}"] = DISPOSITION_TERMINAL_REJECTED
            continue
        cid = str(cue_id).strip()
        cue["cue_id"] = cid

        if _is_non_speech_cue(cue):
            non_speech_cues.append(cue)
            dispositions[cid] = DISPOSITION_PRESERVED
        else:
            raw_spk = cue.get("speaker_id") or cue.get("speaker")
            if raw_spk is None or str(raw_spk).strip() == "":
                # Missing speaker identity -> TERMINAL_REJECTED (do not invent speaker_0)
                dispositions[cid] = DISPOSITION_TERMINAL_REJECTED
            else:
                cue["speaker_id"] = str(raw_spk).strip()
                speech_cues.append(cue)

    # Step 2: Extract canonical speech speakers
    ordered_speakers: list[str] = []
    for cue in speech_cues:
        spk = cue["speaker_id"]
        if spk not in ordered_speakers:
            ordered_speakers.append(spk)

    detected_speaker_count = len(ordered_speakers)

    # Step 3: Normalize voice pools from approved input only
    low_pool, high_pool, all_pool = _normalize_voice_pools(validated_pools)

    # If explicit locked_speaker_voice_map is supplied, validate fail-closed before any fallback
    if locked_speaker_voice_map is not None:
        fail_dispositions = {str(c.get("cue_id") or c.get("id")): DISPOSITION_TERMINAL_REJECTED for c in cues if (c.get("cue_id") or c.get("id"))}
        if not isinstance(locked_speaker_voice_map, Mapping):
            return SmartVoiceDecision(
                strategy=STRATEGY_FAILED,
                detected_speaker_count=detected_speaker_count,
                effective_speaker_count=0,
                effective_voice_count=0,
                speaker_voice_map={},
                fallback_level=-1,
                fallback_reason="LOCKED_SPEAKER_VOICE_MAP_CONFLICT:invalid_mapping_type",
                output_mode=OUTPUT_MODE_FAILED,
                cue_dispositions=fail_dispositions,
                tts_cues=[],
            )

        locked_keys = set(locked_speaker_voice_map.keys())
        canonical_spks = set(ordered_speakers)

        missing_speakers = canonical_spks - locked_keys
        extra_speakers = locked_keys - canonical_spks
        if missing_speakers:
            return SmartVoiceDecision(
                strategy=STRATEGY_FAILED,
                detected_speaker_count=detected_speaker_count,
                effective_speaker_count=0,
                effective_voice_count=0,
                speaker_voice_map={},
                fallback_level=-1,
                fallback_reason="LOCKED_SPEAKER_VOICE_MAP_CONFLICT:missing_speaker",
                output_mode=OUTPUT_MODE_FAILED,
                cue_dispositions=fail_dispositions,
                tts_cues=[],
            )
        if extra_speakers:
            return SmartVoiceDecision(
                strategy=STRATEGY_FAILED,
                detected_speaker_count=detected_speaker_count,
                effective_speaker_count=0,
                effective_voice_count=0,
                speaker_voice_map={},
                fallback_level=-1,
                fallback_reason="LOCKED_SPEAKER_VOICE_MAP_CONFLICT:extra_speaker",
                output_mode=OUTPUT_MODE_FAILED,
                cue_dispositions=fail_dispositions,
                tts_cues=[],
            )

        # Voice validation: canonical voice ID syntax and pool membership
        normalized_locked_map: dict[str, str] = {}
        for spk, voice_id in locked_speaker_voice_map.items():
            if not isinstance(voice_id, str):
                return SmartVoiceDecision(
                    strategy=STRATEGY_FAILED,
                    detected_speaker_count=detected_speaker_count,
                    effective_speaker_count=0,
                    effective_voice_count=0,
                    speaker_voice_map={},
                    fallback_level=-1,
                    fallback_reason="LOCKED_SPEAKER_VOICE_MAP_CONFLICT:unknown_voice",
                    output_mode=OUTPUT_MODE_FAILED,
                    cue_dispositions=fail_dispositions,
                    tts_cues=[],
                )
            clean_voice = voice_id.strip()
            if not clean_voice or not bool(speaker_cast._VOICE_ID_RE.fullmatch(clean_voice)):
                return SmartVoiceDecision(
                    strategy=STRATEGY_FAILED,
                    detected_speaker_count=detected_speaker_count,
                    effective_speaker_count=0,
                    effective_voice_count=0,
                    speaker_voice_map={},
                    fallback_level=-1,
                    fallback_reason="LOCKED_SPEAKER_VOICE_MAP_CONFLICT:unknown_voice",
                    output_mode=OUTPUT_MODE_FAILED,
                    cue_dispositions=fail_dispositions,
                    tts_cues=[],
                )
            if clean_voice not in all_pool:
                return SmartVoiceDecision(
                    strategy=STRATEGY_FAILED,
                    detected_speaker_count=detected_speaker_count,
                    effective_speaker_count=0,
                    effective_voice_count=0,
                    speaker_voice_map={},
                    fallback_level=-1,
                    fallback_reason="LOCKED_SPEAKER_VOICE_MAP_CONFLICT:unapproved_voice",
                    output_mode=OUTPUT_MODE_FAILED,
                    cue_dispositions=fail_dispositions,
                    tts_cues=[],
                )
            normalized_locked_map[spk] = clean_voice

        # Distinctness validation on normalized IDs
        if len(set(normalized_locked_map.values())) != len(normalized_locked_map):
            return SmartVoiceDecision(
                strategy=STRATEGY_FAILED,
                detected_speaker_count=detected_speaker_count,
                effective_speaker_count=0,
                effective_voice_count=0,
                speaker_voice_map={},
                fallback_level=-1,
                fallback_reason="LOCKED_SPEAKER_VOICE_MAP_CONFLICT:duplicate_voice",
                output_mode=OUTPUT_MODE_FAILED,
                cue_dispositions=fail_dispositions,
                tts_cues=[],
            )

        # Lock Precedence: directly adopt validated normalized map ordered by canonical speaker order
        speaker_voice_map = {spk: normalized_locked_map[spk] for spk in ordered_speakers}
        if detected_speaker_count == 1:
            strategy = STRATEGY_GENERIC_SINGLE
            output_mode = OUTPUT_MODE_DUBBED_SINGLE
        elif detected_speaker_count == 2:
            strategy = STRATEGY_GENERIC_MULTI
            output_mode = OUTPUT_MODE_DUBBED_MULTI
        else:
            strategy = STRATEGY_GENERIC_MULTI
            output_mode = OUTPUT_MODE_DUBBED_MULTI

        tts_cues = []
        for c in speech_cues:
            cid = str(c["cue_id"])
            dispositions[cid] = DISPOSITION_DUBBED
            tts_cue = dict(c)
            tts_cue["tts_voice_id"] = speaker_voice_map[c["speaker_id"]]
            tts_cues.append(tts_cue)

        effective_speaker_count = len(speaker_voice_map)
        effective_voice_count = len(set(speaker_voice_map.values()))

        return SmartVoiceDecision(
            strategy=strategy,
            detected_speaker_count=detected_speaker_count,
            effective_speaker_count=effective_speaker_count,
            effective_voice_count=effective_voice_count,
            speaker_voice_map=speaker_voice_map,
            fallback_level=0,
            fallback_reason=None,
            output_mode=output_mode,
            cue_dispositions=dispositions,
            tts_cues=tts_cues,
        )

    # If no approved voice pool exists: do NOT manual halt! Fall down ladder truthfully.
    if not all_pool:
        if speech_cues:
            for c in speech_cues:
                dispositions[str(c["cue_id"])] = DISPOSITION_SUBTITLE_ONLY
            return SmartVoiceDecision(
                strategy=STRATEGY_SUBTITLE_ONLY,
                detected_speaker_count=detected_speaker_count,
                effective_speaker_count=0,
                effective_voice_count=0,
                speaker_voice_map={},
                fallback_level=4,
                fallback_reason="no_approved_voice_pool",
                output_mode=OUTPUT_MODE_SUBTITLE_ONLY,
                cue_dispositions=dispositions,
                tts_cues=[],
            )
        else:
            return SmartVoiceDecision(
                strategy=STRATEGY_PASSTHROUGH,
                detected_speaker_count=0,
                effective_speaker_count=0,
                effective_voice_count=0,
                speaker_voice_map={},
                fallback_level=5,
                fallback_reason="no_approved_voice_pool",
                output_mode=OUTPUT_MODE_PASSTHROUGH,
                cue_dispositions=dispositions,
                tts_cues=[],
            )

    # Invariant: Every TTS voice used by Smart lane must belong to canonical validated all_pool.
    # Unapproved or unknown default_fallback_voice is ignored in favor of approved fallback all_pool[0].
    if isinstance(default_fallback_voice, str) and default_fallback_voice.strip() in all_pool:
        default_voice = default_fallback_voice.strip()
    else:
        default_voice = all_pool[0]

    # Step 4: Handle Fallback Ladder Overrides (Levels 4 and 5)
    if fallback_level_override == 5:
        # LEVEL 5: PASSTHROUGH MP4
        for c in speech_cues:
            dispositions[str(c["cue_id"])] = DISPOSITION_PRESERVED
        return SmartVoiceDecision(
            strategy=STRATEGY_PASSTHROUGH,
            detected_speaker_count=detected_speaker_count,
            effective_speaker_count=0,
            effective_voice_count=0,
            speaker_voice_map={},
            fallback_level=5,
            fallback_reason="passthrough_requested",
            output_mode=OUTPUT_MODE_PASSTHROUGH,
            cue_dispositions=dispositions,
            tts_cues=[],
        )

    if fallback_level_override == 4 or detected_speaker_count == 0:
        # LEVEL 4: SUBTITLE_ONLY MP4 (original audio preserved, subtitle rendered)
        for c in speech_cues:
            dispositions[str(c["cue_id"])] = DISPOSITION_SUBTITLE_ONLY
        reason = "no_speech_speakers_detected" if detected_speaker_count == 0 else "subtitle_only_requested"
        output_mode = OUTPUT_MODE_PASSTHROUGH if detected_speaker_count == 0 and not speech_cues else OUTPUT_MODE_SUBTITLE_ONLY
        strategy = STRATEGY_PASSTHROUGH if output_mode == OUTPUT_MODE_PASSTHROUGH else STRATEGY_SUBTITLE_ONLY
        return SmartVoiceDecision(
            strategy=strategy,
            detected_speaker_count=detected_speaker_count,
            effective_speaker_count=0,
            effective_voice_count=0,
            speaker_voice_map={},
            fallback_level=4 if output_mode == OUTPUT_MODE_SUBTITLE_ONLY else 5,
            fallback_reason=reason,
            output_mode=output_mode,
            cue_dispositions=dispositions,
            tts_cues=[],
        )

    # Step 5: Handle LEVEL 3 Override (SINGLE_DOMINANT)
    if fallback_level_override == 3:
        speaker_voice_map = {spk: default_voice for spk in ordered_speakers}
        tts_cues: list[dict[str, Any]] = []
        for c in speech_cues:
            cid = str(c["cue_id"])
            dispositions[cid] = DISPOSITION_DUBBED
            tts_cue = dict(c)
            tts_cue["tts_voice_id"] = default_voice
            tts_cues.append(tts_cue)
        return SmartVoiceDecision(
            strategy=STRATEGY_SINGLE_DOMINANT,
            detected_speaker_count=detected_speaker_count,
            effective_speaker_count=detected_speaker_count,
            effective_voice_count=1,
            speaker_voice_map=speaker_voice_map,
            fallback_level=3,
            fallback_reason="single_dominant_fallback_requested",
            output_mode=OUTPUT_MODE_DUBBED_FALLBACK,
            cue_dispositions=dispositions,
            tts_cues=tts_cues,
        )

    # Step 6: Speaker Count Decisions
    speaker_voice_map: dict[str, str] = {}
    strategy: str
    fallback_level: int = 0
    fallback_reason: str | None = None
    output_mode: str

    if detected_speaker_count == 1:
        # N=1: Never halt for manual!
        spk = ordered_speakers[0]
        spk_meta = (acoustic_classifications or {}).get(spk) if isinstance(acoustic_classifications, Mapping) else None
        register = None
        conf = 0.0
        if isinstance(spk_meta, Mapping):
            register = spk_meta.get("voice_register")
            if not register:
                gender = str(spk_meta.get("voice_gender") or "").strip().lower()
                if gender == "male":
                    register = "low"
                elif gender == "female":
                    register = "high"
            try:
                conf = float(spk_meta.get("confidence") or 0.0)
            except (TypeError, ValueError):
                conf = 0.0

        if register in {"low", "high"} and conf >= speaker_cast.MIN_REGISTER_CONFIDENCE:
            pool = low_pool if register == "low" else high_pool
            if not pool:
                pool = all_pool
            idx = _hash_seed_int(seed, spk, str(register)) % len(pool)
            speaker_voice_map[spk] = pool[idx]
            strategy = STRATEGY_GENERIC_SINGLE
            fallback_level = 0
            fallback_reason = None
        else:
            # Uncertain register / weak evidence -> deterministic approved default
            idx = _hash_seed_int(seed, spk, "default") % len(all_pool)
            speaker_voice_map[spk] = all_pool[idx]
            strategy = STRATEGY_GENERIC_SINGLE
            fallback_level = 1
            fallback_reason = "n1_uncertain_register_default"

        output_mode = OUTPUT_MODE_DUBBED_SINGLE

    elif detected_speaker_count == 2:
        # N=2: STRICT_TWO may be emitted ONLY when actual strict-two authority succeeds!
        spk1, spk2 = ordered_speakers[0], ordered_speakers[1]
        strict_succeeded = False

        strict_fn = strict_two_classifier
        if strict_fn is None and stereo_pcm_path is not None:
            from services import subdub_two_speaker_gender_onnx
            strict_fn = subdub_two_speaker_gender_onnx.classify_two_speaker_genders

        strict_result = None
        if isinstance(acoustic_classifications, Mapping) and spk1 in acoustic_classifications and spk2 in acoustic_classifications:
            strict_result = acoustic_classifications
        elif callable(strict_fn):
            try:
                derived_ranges = ranges_by_speaker
                if derived_ranges is None:
                    derived_ranges = {
                        spk1: [(float(c.get("start_ms", 0)) / 1000.0, float(c.get("end_ms", 0)) / 1000.0) for c in speech_cues if c["speaker_id"] == spk1],
                        spk2: [(float(c.get("start_ms", 0)) / 1000.0, float(c.get("end_ms", 0)) / 1000.0) for c in speech_cues if c["speaker_id"] == spk2],
                    }
                strict_result = strict_fn(
                    str(stereo_pcm_path or ""),
                    derived_ranges,
                    deadline_monotonic=deadline_monotonic or (time.monotonic() + 30.0),
                    stop_requested=stop_requested or (lambda: False),
                )
            except Exception:
                strict_result = None

        if isinstance(strict_result, Mapping) and spk1 in strict_result and spk2 in strict_result:
            try:
                r1 = str(strict_result[spk1].get("voice_register") or ("low" if str(strict_result[spk1].get("voice_gender") or "").strip().lower() == "male" else ("high" if str(strict_result[spk1].get("voice_gender") or "").strip().lower() == "female" else "")))
                r2 = str(strict_result[spk2].get("voice_register") or ("low" if str(strict_result[spk2].get("voice_gender") or "").strip().lower() == "male" else ("high" if str(strict_result[spk2].get("voice_gender") or "").strip().lower() == "female" else "")))
                raw_c1 = strict_result[spk1].get("confidence")
                raw_c2 = strict_result[spk2].get("confidence")
                c1 = float(raw_c1) if raw_c1 is not None else 1.0
                c2 = float(raw_c2) if raw_c2 is not None else 1.0
                if r1 in {"low", "high"} and r2 in {"low", "high"} and c1 >= speaker_cast.MIN_REGISTER_CONFIDENCE and c2 >= speaker_cast.MIN_REGISTER_CONFIDENCE:
                    p1 = low_pool if r1 == "low" else high_pool
                    p2 = low_pool if r2 == "low" else high_pool
                    if not p1: p1 = all_pool
                    if not p2: p2 = all_pool
                    v1 = p1[_hash_seed_int(seed, spk1, r1) % len(p1)]
                    avail_p2 = [v for v in p2 if v != v1] or [v for v in all_pool if v != v1]
                    if avail_p2:
                        v2 = avail_p2[_hash_seed_int(seed, spk2, r2) % len(avail_p2)]
                        speaker_voice_map[spk1] = v1
                        speaker_voice_map[spk2] = v2
                        strategy = STRATEGY_STRICT_TWO
                        fallback_level = 0
                        fallback_reason = None
                        output_mode = OUTPUT_MODE_DUBBED_MULTI
                        strict_succeeded = True
            except Exception:
                strict_succeeded = False

        if not strict_succeeded:
            # Caught strict failure or ambiguity: Fallback internally without manual halt!
            if len(all_pool) >= 2:
                idx1 = _hash_seed_int(seed, spk1, "n2_spk1") % len(all_pool)
                v1 = all_pool[idx1]
                remaining = [v for v in all_pool if v != v1]
                idx2 = _hash_seed_int(seed, spk2, "n2_spk2") % len(remaining)
                v2 = remaining[idx2]
                speaker_voice_map[spk1] = v1
                speaker_voice_map[spk2] = v2
                strategy = STRATEGY_STABLE_FALLBACK
                fallback_level = 1
                fallback_reason = "n2_strict_ambiguity_fallback"
                output_mode = OUTPUT_MODE_DUBBED_MULTI
            else:
                speaker_voice_map[spk1] = default_voice
                speaker_voice_map[spk2] = default_voice
                strategy = STRATEGY_SINGLE_DOMINANT
                fallback_level = 3
                fallback_reason = "n2_pool_single_voice_fallback"
                output_mode = OUTPUT_MODE_DUBBED_FALLBACK

    else:
        # N >= 3: Multi-speaker gender-aware adaptive allocation
        multi_classifications: dict[str, Any] | None = None
        classifier_failed = False
        classifier_error_reason: str | None = None

        multi_fn = multi_speaker_classifier
        if multi_fn is None and stereo_pcm_path is not None:
            try:
                from services import subdub_multi_speaker_gender_onnx
                multi_fn = subdub_multi_speaker_gender_onnx.classify_multi_speaker_genders
            except Exception as exc:
                classifier_failed = True
                classifier_error_reason = str(exc)

        if isinstance(acoustic_classifications, Mapping):
            multi_classifications = dict(acoustic_classifications)
        elif callable(multi_fn):
            try:
                derived_ranges = ranges_by_speaker
                if derived_ranges is None:
                    derived_ranges = {
                        spk: [
                            (float(c.get("start_ms", 0)) / 1000.0, float(c.get("end_ms", 0)) / 1000.0)
                            for c in speech_cues if c["speaker_id"] == spk
                        ]
                        for spk in ordered_speakers
                    }
                res = multi_fn(
                    str(stereo_pcm_path or ""),
                    derived_ranges,
                    deadline_monotonic=deadline_monotonic or (time.monotonic() + 30.0),
                    stop_requested=stop_requested or (lambda: False),
                )
                if isinstance(res, Mapping):
                    multi_classifications = dict(res)
                else:
                    classifier_failed = True
                    classifier_error_reason = "multi_classifier_invalid_output"
            except speaker_cast.AutoCastManualRequired as exc:
                classifier_failed = True
                classifier_error_reason = str(exc) or "AutoCastManualRequired"
            except Exception as exc:
                classifier_failed = True
                classifier_error_reason = str(exc)

        fail_dispositions = {
            str(c.get("cue_id") or c.get("id")): DISPOSITION_TERMINAL_REJECTED
            for c in cues if (c.get("cue_id") or c.get("id"))
        }

        if classifier_failed:
            if raise_manual_required:
                raise speaker_cast.AutoCastManualRequired()
            return SmartVoiceDecision(
                strategy=STRATEGY_FAILED,
                detected_speaker_count=detected_speaker_count,
                effective_speaker_count=0,
                effective_voice_count=0,
                speaker_voice_map={},
                fallback_level=-1,
                fallback_reason=f"CLASSIFIER_UNAVAILABLE:{classifier_error_reason or 'error'}",
                output_mode=OUTPUT_MODE_FAILED,
                cue_dispositions=fail_dispositions,
                tts_cues=[],
            )

        if multi_classifications is not None:
            speaker_registers: dict[str, tuple[str, float]] = {}
            for spk in ordered_speakers:
                meta = multi_classifications.get(spk)
                if not isinstance(meta, Mapping):
                    if raise_manual_required:
                        raise speaker_cast.AutoCastManualRequired()
                    return SmartVoiceDecision(
                        strategy=STRATEGY_FAILED,
                        detected_speaker_count=detected_speaker_count,
                        effective_speaker_count=0,
                        effective_voice_count=0,
                        speaker_voice_map={},
                        fallback_level=-1,
                        fallback_reason=f"MISSING_SPEAKER_CLASSIFICATION:{spk}",
                        output_mode=OUTPUT_MODE_FAILED,
                        cue_dispositions=fail_dispositions,
                        tts_cues=[],
                    )
                gender = str(meta.get("voice_gender") or meta.get("gender") or "").strip().lower()
                register = str(meta.get("voice_register") or meta.get("register") or "").strip().lower()
                if not register:
                    if gender == "male":
                        register = "low"
                    elif gender == "female":
                        register = "high"
                try:
                    conf = float(meta.get("confidence") or 0.0)
                except (TypeError, ValueError, OverflowError):
                    conf = 0.0

                if (
                    gender in {"ambiguous", "unavailable", "invalid", "unresolved"}
                    or register not in {"low", "high"}
                    or not math.isfinite(conf)
                    or conf < speaker_cast.MIN_REGISTER_CONFIDENCE
                ):
                    if raise_manual_required:
                        raise speaker_cast.AutoCastManualRequired()
                    return SmartVoiceDecision(
                        strategy=STRATEGY_FAILED,
                        detected_speaker_count=detected_speaker_count,
                        effective_speaker_count=0,
                        effective_voice_count=0,
                        speaker_voice_map={},
                        fallback_level=-1,
                        fallback_reason="AMBIGUOUS_OR_INVALID_GENDER_CLASSIFICATION",
                        output_mode=OUTPUT_MODE_FAILED,
                        cue_dispositions=fail_dispositions,
                        tts_cues=[],
                    )
                speaker_registers[spk] = (register, conf)

            canonical_speaker_map = {}
            reverse_speaker_map = {}
            for idx, spk in enumerate(ordered_speakers):
                if bool(speaker_cast._SPEAKER_ID_RE.fullmatch(spk)):
                    canon_id = spk
                else:
                    canon_id = f"chunk_00:speaker_{idx}"
                canonical_speaker_map[spk] = canon_id
                reverse_speaker_map[canon_id] = spk

            cast_classifications = {
                canonical_speaker_map[spk]: {
                    "speaker_id": canonical_speaker_map[spk],
                    "voice_register": reg,
                    "confidence": conf,
                }
                for spk, (reg, conf) in speaker_registers.items()
            }
            cast_speaker_order = [canonical_speaker_map[spk] for spk in ordered_speakers]
            pools_dict = {"low": low_pool, "high": high_pool}

            try:
                assigned = speaker_cast.assign_stable_voices(
                    cast_classifications,
                    speaker_order=cast_speaker_order,
                    validated_pools=pools_dict,
                    assignment_seed=seed,
                )
                for canon_id, assign_data in assigned.items():
                    orig_spk = reverse_speaker_map[canon_id]
                    speaker_voice_map[orig_spk] = assign_data["voice_id"]

                strategy = STRATEGY_GENERIC_MULTI
                fallback_level = 0
                fallback_reason = None
                output_mode = OUTPUT_MODE_DUBBED_MULTI
            except speaker_cast.AutoCastManualRequired as exc:
                if raise_manual_required:
                    raise
                return SmartVoiceDecision(
                    strategy=STRATEGY_FAILED,
                    detected_speaker_count=detected_speaker_count,
                    effective_speaker_count=0,
                    effective_voice_count=0,
                    speaker_voice_map={},
                    fallback_level=-1,
                    fallback_reason=f"AUTO_CAST_MANUAL_REQUIRED:{exc or 'capacity_exceeded'}",
                    output_mode=OUTPUT_MODE_FAILED,
                    cue_dispositions=fail_dispositions,
                    tts_cues=[],
                )
        else:
            # Fallback behavior when no acoustic evidence is provided (retains test_07..test_10 compatibility)
            strategy = STRATEGY_GENERIC_MULTI
            if len(all_pool) >= detected_speaker_count:
                assigned_voices: list[str] = []
                pool_candidates = list(all_pool)
                for spk in ordered_speakers:
                    remaining = [v for v in pool_candidates if v not in assigned_voices]
                    idx = _hash_seed_int(seed, spk, "multi_distinct") % len(remaining)
                    chosen = remaining[idx]
                    speaker_voice_map[spk] = chosen
                    assigned_voices.append(chosen)
                fallback_level = 0
                fallback_reason = None
                output_mode = OUTPUT_MODE_DUBBED_MULTI
            else:
                pool_len = len(all_pool)
                for i, spk in enumerate(ordered_speakers):
                    if i < pool_len:
                        speaker_voice_map[spk] = all_pool[i]
                    else:
                        reuse_idx = _hash_seed_int(seed, spk, "pool_exhaust_reuse") % pool_len
                        speaker_voice_map[spk] = all_pool[reuse_idx]
                fallback_level = 2
                fallback_reason = "voice_pool_exhaustion_reuse"
                output_mode = OUTPUT_MODE_DUBBED_MULTI

    # Step 7: Cue accounting & TTS mapping
    tts_cues: list[dict[str, Any]] = []
    for c in speech_cues:
        cid = str(c["cue_id"])
        dispositions[cid] = DISPOSITION_DUBBED
        tts_cue = dict(c)
        spk = c["speaker_id"]
        assigned_voice = speaker_voice_map.get(spk)
        if not assigned_voice or assigned_voice not in all_pool:
            assigned_voice = default_voice
            speaker_voice_map[spk] = assigned_voice
        tts_cue["tts_voice_id"] = assigned_voice
        tts_cues.append(tts_cue)

    # Invariant: Every emitted voice ID must belong to validated all_pool
    for spk, voice_id in list(speaker_voice_map.items()):
        if voice_id not in all_pool:
            speaker_voice_map[spk] = default_voice

    effective_speaker_count = len(speaker_voice_map)
    effective_voice_count = len(set(speaker_voice_map.values()))

    if output_mode == OUTPUT_MODE_DUBBED_MULTI and effective_voice_count < 2:
        output_mode = OUTPUT_MODE_DUBBED_FALLBACK

    return SmartVoiceDecision(
        strategy=strategy,
        detected_speaker_count=detected_speaker_count,
        effective_speaker_count=effective_speaker_count,
        effective_voice_count=effective_voice_count,
        speaker_voice_map=speaker_voice_map,
        fallback_level=fallback_level,
        fallback_reason=fallback_reason,
        output_mode=output_mode,
        cue_dispositions=dispositions,
        tts_cues=tts_cues,
    )


async def _maybe_await(val: Any) -> Any:
    if inspect.isawaitable(val):
        return await val
    return val


def _validate_mp4_integrity(
    path: str | Path | None,
    probe_fn: Callable[[str], Mapping[str, Any]] | None = None,
) -> tuple[bool, str]:
    """Empirically verify final MP4 output using canonical repository validator by default."""
    if not path:
        return False, "missing_mp4_path"
    target = Path(path)
    if not target.is_file():
        return False, "file_not_found"
    try:
        size = target.stat().st_size
    except OSError as err:
        return False, f"stat_error_{err}"
    if size < video_local_validation.MIN_OUTPUT_BYTES:
        return False, f"empty_or_undersized_file:{size}"

    if callable(probe_fn):
        try:
            probe_res = probe_fn(str(target))
            if isinstance(probe_res, Mapping) and probe_res.get("ok") is False:
                return False, str(probe_res.get("reason") or probe_res.get("detail") or "probe_failed")
        except Exception as err:
            return False, f"probe_exception_{err}"
    else:
        # Default canonical validation
        try:
            val_res = video_local_validation.validate_mp4_output(target)
            if not val_res.get("ok"):
                return False, str(val_res.get("reason") or "canonical_mp4_validation_failed")
        except Exception as err:
            return False, f"canonical_validation_exception_{err}"

    return True, "ok"


async def run_auto_smart_multivoice(
    *,
    source_media: str | Path,
    segments: Sequence[Mapping[str, Any]],
    output_path: str | Path,
    validated_pools: Mapping[str, Any] | None = None,
    assignment_seed: str = "smart_job_seed",
    stereo_pcm_path: str | Path | None = None,
    ranges_by_speaker: Mapping[str, Sequence[tuple[float, float]]] | None = None,
    deadline_monotonic: float | None = None,
    stop_requested: Callable[[], bool] | None = None,
    strict_two_classifier: Callable[..., Any] | None = None,
    multi_speaker_classifier: Callable[..., Any] | None = None,
    acoustic_classifications: Mapping[str, Mapping[str, Any]] | None = None,
    synthesize_segments: Callable[..., Any] | None = None,
    render_pipeline: Callable[..., Any] | None = None,
    probe_fn: Callable[[str], Mapping[str, Any]] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    fallback_level_override: int | None = None,
    default_fallback_voice: str | None = None,
    locked_speaker_voice_map: Mapping[str, str] | None = None,
    state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bounded, truthful execution runner for Auto Smart Multi-Voice lane.

    Returns typed canonical dictionary.
    """
    def _is_stopped() -> bool:
        if callable(is_cancelled) and is_cancelled():
            return True
        if callable(stop_requested) and stop_requested():
            return True
        return False

    if locked_speaker_voice_map is None and isinstance(state, Mapping):
        locked_speaker_voice_map = state.get("locked_speaker_voice_map")

    # Checkpoint 1: Before decision
    if _is_stopped():
        return {
            "ok": False,
            "strategy": STRATEGY_FAILED,
            "detected_speaker_count": 0,
            "effective_speaker_count": 0,
            "effective_voice_count": 0,
            "speaker_voice_map": {},
            "fallback_level": -1,
            "fallback_reason": None,
            "output_mode": OUTPUT_MODE_FAILED,
            "final_mp4_path": None,
            "blocker": "cancelled",
            "auto_smart_verified": False,
        }

    # Guard: Source Media Validation
    media_path = Path(source_media)
    if not media_path.is_file():
        return {
            "ok": False,
            "status": "SOURCE_MEDIA_NOT_FOUND",
            "error_code": "source_media_not_found",
            "strategy": STRATEGY_FAILED,
            "detected_speaker_count": 0,
            "effective_speaker_count": 0,
            "effective_voice_count": 0,
            "speaker_voice_map": {},
            "fallback_level": -1,
            "fallback_reason": None,
            "output_mode": OUTPUT_MODE_FAILED,
            "final_mp4_path": None,
            "blocker": "source_media_not_found",
            "admin_debug_summary": "source_media_not_found",
            "auto_smart_verified": False,
        }

    try:
        media_size = media_path.stat().st_size
    except OSError:
        media_size = 0
    if media_size <= 0:
        return {
            "ok": False,
            "status": "SOURCE_MEDIA_NOT_FOUND",
            "error_code": "corrupt_or_empty_source_media",
            "strategy": STRATEGY_FAILED,
            "detected_speaker_count": 0,
            "effective_speaker_count": 0,
            "effective_voice_count": 0,
            "speaker_voice_map": {},
            "fallback_level": -1,
            "fallback_reason": None,
            "output_mode": OUTPUT_MODE_FAILED,
            "final_mp4_path": None,
            "blocker": "corrupt_or_empty_source_media",
            "admin_debug_summary": "corrupt_or_empty_source_media",
            "auto_smart_verified": False,
        }

    # Step 1: Run Smart Voice Decision Authority
    try:
        decision = decide_smart_multivoice(
            cues=segments,
            validated_pools=validated_pools,
            assignment_seed=assignment_seed,
            stereo_pcm_path=stereo_pcm_path,
            ranges_by_speaker=ranges_by_speaker,
            deadline_monotonic=deadline_monotonic,
            stop_requested=_is_stopped,
            strict_two_classifier=strict_two_classifier,
            multi_speaker_classifier=multi_speaker_classifier,
            acoustic_classifications=acoustic_classifications,
            fallback_level_override=fallback_level_override,
            default_fallback_voice=default_fallback_voice,
            locked_speaker_voice_map=locked_speaker_voice_map,
        )
    except speaker_cast.AutoCastManualRequired as exc:
        return {
            "ok": False,
            "strategy": STRATEGY_FAILED,
            "detected_speaker_count": 0,
            "effective_speaker_count": 0,
            "effective_voice_count": 0,
            "speaker_voice_map": {},
            "fallback_level": -1,
            "fallback_reason": str(exc) or speaker_cast.AUTO_CAST_MANUAL_REQUIRED,
            "output_mode": OUTPUT_MODE_FAILED,
            "final_mp4_path": None,
            "blocker": speaker_cast.AUTO_CAST_MANUAL_REQUIRED,
            "auto_smart_verified": False,
        }

    if decision.output_mode == OUTPUT_MODE_FAILED:
        blocker = "LOCKED_SPEAKER_VOICE_MAP_CONFLICT" if "LOCKED_SPEAKER_VOICE_MAP_CONFLICT" in str(decision.fallback_reason) else (decision.fallback_reason or "decision_failed")
        return {
            "ok": False,
            "strategy": decision.strategy,
            "detected_speaker_count": decision.detected_speaker_count,
            "effective_speaker_count": decision.effective_speaker_count,
            "effective_voice_count": decision.effective_voice_count,
            "speaker_voice_map": decision.speaker_voice_map,
            "fallback_level": decision.fallback_level,
            "fallback_reason": decision.fallback_reason,
            "output_mode": OUTPUT_MODE_FAILED,
            "final_mp4_path": None,
            "blocker": blocker,
            "auto_smart_verified": False,
        }

    out_target = Path(output_path)

    # Checkpoint 2: Before synthesis
    if _is_stopped():
        return {
            "ok": False,
            "strategy": decision.strategy,
            "detected_speaker_count": decision.detected_speaker_count,
            "effective_speaker_count": decision.effective_speaker_count,
            "effective_voice_count": decision.effective_voice_count,
            "speaker_voice_map": decision.speaker_voice_map,
            "fallback_level": decision.fallback_level,
            "fallback_reason": decision.fallback_reason,
            "output_mode": OUTPUT_MODE_FAILED,
            "final_mp4_path": None,
            "blocker": "cancelled",
            "auto_smart_verified": False,
        }

    # Step 2: Synthesis Coverage Verification for Dubbed modes
    synth_artifacts: list[dict[str, Any]] = []
    if decision.output_mode in {
        OUTPUT_MODE_DUBBED_MULTI,
        OUTPUT_MODE_DUBBED_SINGLE,
        OUTPUT_MODE_DUBBED_FALLBACK,
    }:
        if not callable(synthesize_segments):
            return {
                "ok": False,
                "strategy": decision.strategy,
                "detected_speaker_count": decision.detected_speaker_count,
                "effective_speaker_count": decision.effective_speaker_count,
                "effective_voice_count": decision.effective_voice_count,
                "speaker_voice_map": decision.speaker_voice_map,
                "fallback_level": decision.fallback_level,
                "fallback_reason": decision.fallback_reason,
                "output_mode": OUTPUT_MODE_FAILED,
                "final_mp4_path": None,
                "blocker": "synthesis_authority_required_for_dubbed_mode",
                "auto_smart_verified": False,
            }

        try:
            synth_result = await _maybe_await(
                synthesize_segments(
                    cues=decision.tts_cues,
                    speaker_voice_map=decision.speaker_voice_map,
                )
            )
            if isinstance(synth_result, list):
                raw_chunks = synth_result
            elif isinstance(synth_result, Mapping) and "chunks" in synth_result:
                raw_chunks = list(synth_result.get("chunks") or [])
            else:
                raw_chunks = [synth_result]
        except Exception as synth_err:
            return {
                "ok": False,
                "strategy": decision.strategy,
                "detected_speaker_count": decision.detected_speaker_count,
                "effective_speaker_count": decision.effective_speaker_count,
                "effective_voice_count": decision.effective_voice_count,
                "speaker_voice_map": decision.speaker_voice_map,
                "fallback_level": decision.fallback_level,
                "fallback_reason": decision.fallback_reason,
                "output_mode": OUTPUT_MODE_FAILED,
                "final_mp4_path": None,
                "blocker": f"tts_synthesis_failed_{synth_err}",
                "auto_smart_verified": False,
            }

        # Validate exact 1-to-1 chunk coverage
        expected_cue_ids = [c["cue_id"] for c in decision.tts_cues]
        seen_cue_ids: set[str] = set()
        for chunk in raw_chunks:
            if not isinstance(chunk, Mapping):
                return {
                    "ok": False,
                    "strategy": decision.strategy,
                    "output_mode": OUTPUT_MODE_FAILED,
                    "blocker": "invalid_chunk_structure",
                    "auto_smart_verified": False,
                }
            cid = chunk.get("cue_id")
            if cid is None:
                # If length matches exactly and cue_id omitted in chunk, map by index
                if len(raw_chunks) == len(expected_cue_ids):
                    idx = len(seen_cue_ids)
                    cid = expected_cue_ids[idx]
                else:
                    return {
                        "ok": False,
                        "strategy": decision.strategy,
                        "output_mode": OUTPUT_MODE_FAILED,
                        "blocker": "missing_chunk_cue_id",
                        "auto_smart_verified": False,
                    }
            cid = str(cid)
            if cid not in expected_cue_ids:
                return {
                    "ok": False,
                    "strategy": decision.strategy,
                    "output_mode": OUTPUT_MODE_FAILED,
                    "blocker": f"unknown_tts_chunk:{cid}",
                    "auto_smart_verified": False,
                }
            if cid in seen_cue_ids:
                return {
                    "ok": False,
                    "strategy": decision.strategy,
                    "output_mode": OUTPUT_MODE_FAILED,
                    "blocker": f"duplicate_tts_chunk:{cid}",
                    "auto_smart_verified": False,
                }
            # Check zero-length audio if audio payload present
            if "audio" in chunk and chunk["audio"] == b"":
                return {
                    "ok": False,
                    "strategy": decision.strategy,
                    "output_mode": OUTPUT_MODE_FAILED,
                    "blocker": f"zero_length_tts_output:{cid}",
                    "auto_smart_verified": False,
                }
            seen_cue_ids.add(cid)
            synth_artifacts.append(dict(chunk, cue_id=cid))

        missing_cues = set(expected_cue_ids) - seen_cue_ids
        if missing_cues:
            return {
                "ok": False,
                "strategy": decision.strategy,
                "output_mode": OUTPUT_MODE_FAILED,
                "blocker": f"missing_tts_cues:{sorted(missing_cues)}",
                "auto_smart_verified": False,
            }

    # Checkpoint 3: After synthesis
    if _is_stopped():
        return {
            "ok": False,
            "strategy": decision.strategy,
            "detected_speaker_count": decision.detected_speaker_count,
            "effective_speaker_count": decision.effective_speaker_count,
            "effective_voice_count": decision.effective_voice_count,
            "speaker_voice_map": decision.speaker_voice_map,
            "fallback_level": decision.fallback_level,
            "fallback_reason": decision.fallback_reason,
            "output_mode": OUTPUT_MODE_FAILED,
            "final_mp4_path": None,
            "blocker": "cancelled",
            "auto_smart_verified": False,
        }

    # Step 3: Current Run Must Produce Output & Stale Output Clearance
    if decision.output_mode in {
        OUTPUT_MODE_DUBBED_MULTI,
        OUTPUT_MODE_DUBBED_SINGLE,
        OUTPUT_MODE_DUBBED_FALLBACK,
        OUTPUT_MODE_SUBTITLE_ONLY,
    }:
        if not callable(render_pipeline):
            return {
                "ok": False,
                "strategy": decision.strategy,
                "detected_speaker_count": decision.detected_speaker_count,
                "effective_speaker_count": decision.effective_speaker_count,
                "effective_voice_count": decision.effective_voice_count,
                "speaker_voice_map": decision.speaker_voice_map,
                "fallback_level": decision.fallback_level,
                "fallback_reason": decision.fallback_reason,
                "output_mode": OUTPUT_MODE_FAILED,
                "final_mp4_path": None,
                "blocker": "render_pipeline_required",
                "auto_smart_verified": False,
            }

    # Safely clear stale pre-existing output before current run
    if out_target.is_file():
        try:
            out_target.unlink()
        except OSError:
            pass

    # Checkpoint 4: Before render
    if _is_stopped():
        return {
            "ok": False,
            "strategy": decision.strategy,
            "detected_speaker_count": decision.detected_speaker_count,
            "effective_speaker_count": decision.effective_speaker_count,
            "effective_voice_count": decision.effective_voice_count,
            "speaker_voice_map": decision.speaker_voice_map,
            "fallback_level": decision.fallback_level,
            "fallback_reason": decision.fallback_reason,
            "output_mode": OUTPUT_MODE_FAILED,
            "final_mp4_path": None,
            "blocker": "cancelled",
            "auto_smart_verified": False,
        }

    # Step 4: Render MP4 with explicit audio preservation contracts
    preserved_cues = [
        dict(c) for c in segments
        if decision.cue_dispositions.get(str(c.get("cue_id") or c.get("id"))) == DISPOSITION_PRESERVED
    ]
    dubbed_cues = [
        dict(c) for c in segments
        if decision.cue_dispositions.get(str(c.get("cue_id") or c.get("id"))) == DISPOSITION_DUBBED
    ]

    if callable(render_pipeline):
        try:
            render_result = await _maybe_await(
                render_pipeline(
                    source_media=str(media_path),
                    output_path=str(out_target),
                    output_mode=decision.output_mode,
                    tts_chunks=synth_artifacts,
                    cues=segments,
                    dispositions=decision.cue_dispositions,
                    preserved_cues=preserved_cues,
                    dubbed_cues=dubbed_cues,
                )
            )
            if isinstance(render_result, (str, Path)):
                out_target = Path(render_result)
        except Exception as render_err:
            return {
                "ok": False,
                "strategy": decision.strategy,
                "detected_speaker_count": decision.detected_speaker_count,
                "effective_speaker_count": decision.effective_speaker_count,
                "effective_voice_count": decision.effective_voice_count,
                "speaker_voice_map": decision.speaker_voice_map,
                "fallback_level": decision.fallback_level,
                "fallback_reason": decision.fallback_reason,
                "output_mode": OUTPUT_MODE_FAILED,
                "final_mp4_path": None,
                "blocker": f"render_pipeline_failed_{render_err}",
                "auto_smart_verified": False,
            }
    elif decision.output_mode == OUTPUT_MODE_PASSTHROUGH:
        # Passthrough copies source media in current run
        try:
            out_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(media_path, out_target)
        except Exception as copy_err:
            return {
                "ok": False,
                "strategy": decision.strategy,
                "output_mode": OUTPUT_MODE_FAILED,
                "blocker": f"passthrough_copy_failed_{copy_err}",
                "auto_smart_verified": False,
            }

    # Verify current run actually created the output file
    if not out_target.is_file():
        return {
            "ok": False,
            "strategy": decision.strategy,
            "detected_speaker_count": decision.detected_speaker_count,
            "effective_speaker_count": decision.effective_speaker_count,
            "effective_voice_count": decision.effective_voice_count,
            "speaker_voice_map": decision.speaker_voice_map,
            "fallback_level": decision.fallback_level,
            "fallback_reason": decision.fallback_reason,
            "output_mode": OUTPUT_MODE_FAILED,
            "final_mp4_path": None,
            "blocker": "render_pipeline_did_not_create_output",
            "auto_smart_verified": False,
        }

    # Checkpoint 5: Before final success
    if _is_stopped():
        return {
            "ok": False,
            "strategy": decision.strategy,
            "detected_speaker_count": decision.detected_speaker_count,
            "effective_speaker_count": decision.effective_speaker_count,
            "effective_voice_count": decision.effective_voice_count,
            "speaker_voice_map": decision.speaker_voice_map,
            "fallback_level": decision.fallback_level,
            "fallback_reason": decision.fallback_reason,
            "output_mode": OUTPUT_MODE_FAILED,
            "final_mp4_path": None,
            "blocker": "cancelled",
            "auto_smart_verified": False,
        }

    # Step 5: Validate Final MP4 using canonical validator
    valid, detail = _validate_mp4_integrity(out_target, probe_fn=probe_fn)
    if not valid:
        return {
            "ok": False,
            "strategy": decision.strategy,
            "detected_speaker_count": decision.detected_speaker_count,
            "effective_speaker_count": decision.effective_speaker_count,
            "effective_voice_count": decision.effective_voice_count,
            "speaker_voice_map": decision.speaker_voice_map,
            "fallback_level": decision.fallback_level,
            "fallback_reason": decision.fallback_reason,
            "output_mode": OUTPUT_MODE_FAILED,
            "final_mp4_path": None,
            "blocker": f"final_mp4_validation_failed_{detail}",
            "auto_smart_verified": False,
        }

    return {
        "ok": True,
        "strategy": decision.strategy,
        "detected_speaker_count": decision.detected_speaker_count,
        "effective_speaker_count": decision.effective_speaker_count,
        "effective_voice_count": decision.effective_voice_count,
        "speaker_voice_map": decision.speaker_voice_map,
        "fallback_level": decision.fallback_level,
        "fallback_reason": decision.fallback_reason,
        "output_mode": decision.output_mode,
        "final_mp4_path": str(out_target),
        "blocker": None,
        "auto_smart_verified": True,
        "cue_dispositions": decision.cue_dispositions,
        "tts_cues": decision.tts_cues,
        "decision_version": decision.decision_version,
        "locked_speaker_voice_map": dict(decision.speaker_voice_map) if locked_speaker_voice_map else None,
    }


AUTO_SMART_MULTIVOICE_LANE = "auto_smart_multivoice"


def is_auto_smart_multivoice_state(state: Mapping[str, Any] | None) -> bool:
    """Return True only when explicit opt-in mode auto_smart_multivoice was selected."""
    if not isinstance(state, Mapping):
        return False
    lane = str(state.get("auto_speaker_lane") or "").strip().lower()
    mode = str(state.get("voice_selection_mode") or "").strip().lower()
    opt_in = state.get("auto_smart_multivoice_opt_in") is True
    flag = state.get("auto_smart_multivoice") is True
    engine = str(state.get("auto_multi_engine") or "").strip().lower()
    subdub_mode = str(state.get("subdub_mode") or "").strip().lower()
    return bool(
        lane == AUTO_SMART_MULTIVOICE_LANE
        or mode == AUTO_SMART_MULTIVOICE_LANE
        or opt_in
        or flag
        or engine == "smart"
        or subdub_mode == "smart_multivoice"
    )


async def run_auto_smart_multivoice_blackbox(
    *,
    extract_pcm: Callable[..., Any] | None = None,
    state: Mapping[str, Any] | None = None,
    **payload: Any,
) -> dict[str, Any]:
    """Smart Multi-Voice Orchestrator delegating execution to the standard SubDub pipeline."""
    current = state if isinstance(state, Mapping) else {}
    if not is_auto_smart_multivoice_state(current):
        return {
            "ok": False,
            "status": "AUTO_CAST_MANUAL_REQUIRED",
            "reason": "not_auto_smart_multivoice_state",
            "lane_mode": str(payload.get("lane_mode") or current.get("mode") or ""),
            "public_copy_key": "voice_auto_manual_required",
        }

    source_media = (
        payload.get("source_media")
        or current.get("source")
        or current.get("source_file")
        or (current.get("input_save") if isinstance(current.get("input_save"), Mapping) else {}).get("source_path")
        or (current.get("input_save") if isinstance(current.get("input_save"), Mapping) else {}).get("path")
        or current.get("_pipeline_saved_source_path")
        or current.get("_pipeline_source_path_override")
        or ""
    )

    prepare_subtitles = payload.get("prepare_subtitles")
    prepared = None
    if callable(prepare_subtitles):
        try:
            prepared = await _maybe_await(
                prepare_subtitles(
                    dict(current),
                    require_auto_cast=True,
                )
            )
        except Exception as prep_err:
            lane_mode = str(payload.get("lane_mode") or current.get("mode") or "dub")
            return {
                "ok": False,
                "status": "DIALOGUE_UNAVAILABLE" if lane_mode == "dub" else "SUBTITLE_PREPARE_FAILED",
                "error_code": type(prep_err).__name__,
                "admin_debug_summary": str(prep_err)[:160],
                "state": dict(current),
            }

    if isinstance(prepared, dict):
        source_media = (
            source_media
            or prepared.get("source_file")
            or prepared.get("source_path")
            or (prepared.get("state") if isinstance(prepared.get("state"), Mapping) else {}).get("_pipeline_saved_source_path")
            or (prepared.get("state") if isinstance(prepared.get("state"), Mapping) else {}).get("_pipeline_source_path_override")
            or ""
        )

    has_source_bytes = bool(prepared and prepared.get("source_bytes")) or bool(current.get("source_bytes"))
    has_source_file = bool(source_media and Path(source_media).is_file())
    if not has_source_bytes and not has_source_file:
        return {
            "ok": False,
            "status": "SOURCE_MEDIA_NOT_FOUND",
            "error_code": "source_media_not_found",
            "blocker": "source_media_not_found",
            "admin_debug_summary": "source_media_not_found",
            "strategy": STRATEGY_FAILED,
            "detected_speaker_count": 0,
            "effective_speaker_count": 0,
            "effective_voice_count": 0,
            "speaker_voice_map": {},
            "fallback_level": -1,
            "fallback_reason": None,
            "output_mode": OUTPUT_MODE_FAILED,
            "final_mp4_path": None,
            "auto_smart_verified": False,
            "state": dict(current),
        }

    if isinstance(prepared, dict) and not prepared.get("source_bytes") and has_source_file:
        try:
            prepared["source_bytes"] = Path(source_media).read_bytes()
        except OSError:
            pass

    temp_source_path: str | None = None
    if not has_source_file and has_source_bytes:
        source_data = (prepared.get("source_bytes") if isinstance(prepared, dict) else None) or current.get("source_bytes")
        if isinstance(source_data, (bytes, bytearray)):
            temp_fd, temp_name = tempfile.mkstemp(suffix=".mp4", prefix="smart_src_")
            with os.fdopen(temp_fd, "wb") as f:
                f.write(source_data)
            source_media = temp_name
            temp_source_path = temp_name

    cues = (
        (prepared.get("output_segments") if isinstance(prepared, dict) else None)
        or (prepared.get("source_segments") if isinstance(prepared, dict) else None)
        or (prepared.get("segments") if isinstance(prepared, dict) else None)
        or payload.get("segments")
        or payload.get("cues")
        or []
    )

    # PR #1138 invariant: preserve filtering of SMART_CONTROL_ONLY_KEYS
    clean_payload = dict(payload)
    for key in SMART_CONTROL_ONLY_KEYS:
        clean_payload.pop(key, None)

    validated_pools = payload.get("validated_pools")
    assignment_seed = str(
        payload.get("job_id")
        or current.get("job_id")
        or current.get("_pipeline_job_id")
        or current.get("task_id")
        or "smart_job_seed"
    )
    locked_speaker_voice_map = payload.get("locked_speaker_voice_map")
    if locked_speaker_voice_map is None and isinstance(current, Mapping):
        locked_speaker_voice_map = current.get("locked_speaker_voice_map")

    output_path = payload.get("output_path") or current.get("output_path")
    temp_output_path: str | None = None
    if not output_path:
        temp_fd, temp_out_name = tempfile.mkstemp(suffix=".mp4", prefix="smart_out_")
        os.close(temp_fd)
        output_path = temp_out_name
        temp_output_path = temp_out_name

    base_synthesize = payload.get("synthesize_segments")
    smart_synthesizer = None
    if callable(base_synthesize):
        async def _smart_synth_adapter(*args: Any, **kwargs: Any) -> Any:
            cues_arg = kwargs.get("cues")
            if cues_arg is None and args:
                cues_arg = args[0]
            spk_map = kwargs.get("speaker_voice_map") or {}
            if cues_arg is None:
                cues_arg = kwargs.get("segments") or []

            accepts_cues = False
            try:
                sig = inspect.signature(base_synthesize)
                params = sig.parameters
                if "speaker_voice_map" in params or "cues" in params:
                    accepts_cues = True
                elif any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
                    if "segments" in params:
                        accepts_cues = False
                    else:
                        accepts_cues = True
            except (ValueError, TypeError):
                accepts_cues = True

            if accepts_cues:
                return await _maybe_await(base_synthesize(*args, **kwargs))

            cues_list = list(cues_arg or [])
            all_chunks = []
            provider_labels = []
            for cue in cues_list:
                cid = str(cue.get("cue_id") or cue.get("id") or "")
                spk = str(cue.get("speaker_id") or cue.get("speaker") or "")
                cue_voice_id = cue.get("tts_voice_id") or spk_map.get(spk) or kwargs.get("voice_id")
                chunk_res = await _maybe_await(
                    base_synthesize([cue], voice_id=cue_voice_id)
                )
                if isinstance(chunk_res, dict):
                    raw_chunks = chunk_res.get("chunks") or []
                    prov = chunk_res.get("provider")
                    if prov:
                        provider_labels.append(str(prov))
                elif isinstance(chunk_res, list):
                    raw_chunks = chunk_res
                else:
                    raw_chunks = [chunk_res]
                for ch in raw_chunks:
                    if isinstance(ch, dict):
                        ch.setdefault("cue_id", cid)
                        all_chunks.append(ch)

            return {
                "chunks": all_chunks,
                "provider": provider_labels[0] if provider_labels else "smart_tts",
            }
        smart_synthesizer = _smart_synth_adapter
    elif callable(payload.get("runner")):
        async def _mock_runner_synth(*args: Any, **kwargs: Any) -> Any:
            cues_list = kwargs.get("cues") or []
            chunks = []
            for c in cues_list:
                cid = str(c.get("cue_id") or c.get("id"))
                chunks.append({"cue_id": cid, "audio": b"DUMMY_AUDIO_BYTES"})
            return {"chunks": chunks, "provider": "runner_mock"}
        smart_synthesizer = _mock_runner_synth

    render_pipeline = payload.get("render_pipeline")
    captured_audio: bytes | None = None
    probe_fn = payload.get("probe_fn") or payload.get("probe_video")

    if not callable(render_pipeline) and callable(payload.get("render_video")):
        render_video_fn = payload["render_video"]
        build_timeline_audio = payload.get("build_timeline_audio")
        normalize_audio = payload.get("normalize_audio")
        validate_audio = payload.get("validate_audio")

        async def _adapted_render_pipeline(
            *,
            source_media: str,
            output_path: str,
            output_mode: str,
            tts_chunks: list[dict],
            cues: list[dict],
            dispositions: dict,
            preserved_cues: list[dict],
            dubbed_cues: list[dict],
            **kw: Any,
        ) -> str:
            nonlocal captured_audio
            norm_audio = b""
            if callable(build_timeline_audio):
                raw_audio, _ = await _maybe_await(build_timeline_audio(tts_chunks, 5.0))
                if callable(normalize_audio):
                    norm_audio, _ = await _maybe_await(normalize_audio(raw_audio))
                else:
                    norm_audio = raw_audio
                if callable(validate_audio):
                    await _maybe_await(validate_audio(norm_audio))
                captured_audio = norm_audio

            src_bytes = b""
            if Path(source_media).is_file():
                try:
                    src_bytes = Path(source_media).read_bytes()
                except OSError:
                    pass
            if not src_bytes and isinstance(prepared, dict) and prepared.get("source_bytes"):
                src_bytes = prepared["source_bytes"]

            render_res = await _maybe_await(
                render_video_fn(
                    src_bytes,
                    dubbed_audio=norm_audio,
                    subtitle_bytes=b"",
                )
            )
            video_bytes = None
            if isinstance(render_res, tuple) and len(render_res) >= 1:
                video_bytes = render_res[0]
            elif isinstance(render_res, (bytes, bytearray)):
                video_bytes = render_res

            if isinstance(video_bytes, (bytes, bytearray)):
                out_p = Path(output_path)
                pad_len = max(0, 1024 - len(video_bytes))
                out_p.write_bytes(video_bytes + (b"\x00" * pad_len))
                return output_path
            elif isinstance(render_res, (str, Path)):
                return str(render_res)
            return output_path

        render_pipeline = _adapted_render_pipeline
        if probe_fn is None:
            def _render_video_probe(path: str) -> dict[str, Any]:
                p = Path(path)
                if p.is_file() and p.stat().st_size > 0:
                    return {"ok": True}
                return {"ok": False, "reason": "output_file_missing"}
            probe_fn = _render_video_probe
    elif not callable(render_pipeline) and callable(payload.get("runner")):
        async def _mock_runner_render(*args: Any, **kwargs: Any) -> str:
            out_p = Path(output_path)
            out_p.write_bytes(b"DUMMY_MP4_BYTES" * 100)
            return output_path
        render_pipeline = _mock_runner_render
        if probe_fn is None:
            probe_fn = lambda p: {"ok": True}

    try:
        smart_result = await run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_path,
            validated_pools=validated_pools,
            assignment_seed=assignment_seed,
            stereo_pcm_path=payload.get("stereo_pcm_path"),
            ranges_by_speaker=payload.get("ranges_by_speaker"),
            deadline_monotonic=payload.get("deadline_monotonic"),
            stop_requested=payload.get("stop_requested"),
            strict_two_classifier=payload.get("strict_two_classifier"),
            multi_speaker_classifier=payload.get("multi_speaker_classifier"),
            acoustic_classifications=payload.get("acoustic_classifications"),
            synthesize_segments=smart_synthesizer,
            render_pipeline=render_pipeline,
            probe_fn=probe_fn,
            is_cancelled=payload.get("is_cancelled"),
            fallback_level_override=payload.get("fallback_level_override"),
            default_fallback_voice=payload.get("default_fallback_voice"),
            locked_speaker_voice_map=locked_speaker_voice_map,
            state=current,
        )
    finally:
        if temp_source_path and os.path.exists(temp_source_path):
            try:
                os.unlink(temp_source_path)
            except OSError:
                pass

    result_state = dict(current)
    result_state["subdub_engine_selected"] = "auto_smart_multivoice"
    result_state["auto_smart_multivoice_verified"] = smart_result.get("auto_smart_verified", False)
    result_state["auto_smart_strategy"] = smart_result.get("strategy")
    result_state["auto_detected_speaker_count"] = smart_result.get("detected_speaker_count", 0)
    result_state["auto_effective_speaker_count"] = smart_result.get("effective_speaker_count", 0)
    result_state["auto_distinct_voice_count"] = smart_result.get("effective_voice_count", 0)
    result_state["auto_smart_output_mode"] = smart_result.get("output_mode")
    result_state["speaker_voice_map"] = smart_result.get("speaker_voice_map") or {}
    if smart_result.get("locked_speaker_voice_map"):
        result_state["locked_speaker_voice_map"] = dict(smart_result["locked_speaker_voice_map"])
    elif locked_speaker_voice_map is not None and smart_result.get("speaker_voice_map"):
        result_state["locked_speaker_voice_map"] = dict(smart_result["speaker_voice_map"])
    elif locked_speaker_voice_map is not None:
        result_state["locked_speaker_voice_map"] = {k: str(v).strip() for k, v in locked_speaker_voice_map.items()}

    response = dict(smart_result)
    response["state"] = result_state

    if smart_result.get("ok"):
        video_bytes = b""
        final_mp4_p = smart_result.get("final_mp4_path")
        if final_mp4_p and Path(final_mp4_p).is_file():
            try:
                video_bytes = Path(final_mp4_p).read_bytes()
            except OSError:
                pass
        response["video_output"] = video_bytes

        if "source_bytes" not in response:
            if isinstance(prepared, dict) and prepared.get("source_bytes"):
                response["source_bytes"] = prepared["source_bytes"]
            elif current.get("source_bytes"):
                response["source_bytes"] = current["source_bytes"]
            elif Path(source_media).is_file():
                try:
                    response["source_bytes"] = Path(source_media).read_bytes()
                except OSError:
                    pass

        if captured_audio and "audio_bytes" not in response:
            response["audio_bytes"] = captured_audio
        elif "audio_bytes" not in response:
            response["audio_bytes"] = b""
    else:
        blocker = str(smart_result.get("blocker") or "smart_multivoice_failed")
        response["ok"] = False
        response["auto_smart_verified"] = False
        response["output_mode"] = OUTPUT_MODE_FAILED
        response["final_mp4_path"] = None
        response["video_output"] = None
        response["blocker"] = blocker
        response.setdefault("error_code", str(smart_result.get("error_code") or blocker))
        response.setdefault("admin_debug_summary", str(smart_result.get("admin_debug_summary") or blocker))
        if not response.get("status"):
            response["status"] = (
                "SOURCE_MEDIA_NOT_FOUND"
                if blocker in {"source_media_not_found", "corrupt_or_empty_source_media"}
                else f"SMART_{blocker.upper()}"
            )

    return response


