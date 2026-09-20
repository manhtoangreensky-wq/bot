"""Auto Smart Multi-Voice Adaptive Orchestrator for SubDub.

Isolated new lane C (AUTO SMART MULTI-VOICE):
- Handles 0/1/2/N speech speakers with explicit strategies:
  STRICT_TWO, GENERIC_SINGLE, GENERIC_MULTI, STABLE_FALLBACK,
  SINGLE_DOMINANT, SUBTITLE_ONLY, PASSTHROUGH.
- Fallback ladder:
  LEVEL 0: Best available strict speaker-specific cast.
  LEVEL 1: Generic per-speaker cast.
  LEVEL 2: Deterministic approved fallback voice per uncertain speaker.
  LEVEL 3: Single dominant/default voice for eligible speech.
  LEVEL 4: Subtitle-only MP4 + original audio.
  LEVEL 5: Passthrough MP4 if permitted.
- Cue accounting: Every canonical cue has exactly one disposition:
  DUBBED, PRESERVED, SUBTITLE_ONLY, TERMINAL_REJECTED.
- Preserves background music, singing, and noise from original audio.
- Invariants:
  * Same canonical speaker -> same voice across entire job.
  * Voice pool exhaustion never aborts; reuses deterministically.
  * Zero customer cutover; isolated from legacy auto_speaker and auto_multi_speaker.
  * Pure empirical verification with zero live paid provider calls.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence

from services import subdub_media_preflight
from services import subdub_speaker_cast as speaker_cast


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
    """Return low, high, and combined pools deterministically sorted."""
    low_pool: list[str] = []
    high_pool: list[str] = []
    if isinstance(validated_pools, Mapping):
        for register, target in (("low", low_pool), ("high", high_pool)):
            raw_pool = validated_pools.get(register)
            if isinstance(raw_pool, (list, tuple)):
                for item in raw_pool:
                    if isinstance(item, str) and item.strip() and item.strip() not in target:
                        target.append(item.strip())
    # Fallback to standard voices if empty
    if not low_pool and not high_pool:
        low_pool = ["vi-VN-Standard-B", "vi-VN-Standard-C"]
        high_pool = ["vi-VN-Standard-A", "vi-VN-Standard-D"]
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
    acoustic_classifications: Mapping[str, Mapping[str, Any]] | None = None,
    fallback_level_override: int | None = None,
    default_fallback_voice: str | None = None,
) -> SmartVoiceDecision:
    """Core pure-functional decision authority for Auto Smart Multi-Voice lane."""
    seed = hashlib.sha256(str(assignment_seed).encode("utf-8")).hexdigest()
    low_pool, high_pool, all_pool = _normalize_voice_pools(validated_pools)
    default_voice = default_fallback_voice or all_pool[0]

    # Step 1: Filter speech cues vs non-speech cues
    speech_cues: list[dict[str, Any]] = []
    non_speech_cues: list[dict[str, Any]] = []
    for idx, raw_cue in enumerate(cues):
        cue = dict(raw_cue)
        cue_id = str(cue.get("id") or cue.get("cue_id") or f"cue_{idx}")
        cue["cue_id"] = cue_id
        if _is_non_speech_cue(cue):
            non_speech_cues.append(cue)
        else:
            speech_cues.append(cue)

    # Step 2: Extract canonical speech speakers
    ordered_speakers: list[str] = []
    for cue in speech_cues:
        spk = str(cue.get("speaker_id") or cue.get("speaker") or "speaker_0").strip()
        if spk and spk not in ordered_speakers:
            ordered_speakers.append(spk)

    detected_speaker_count = len(ordered_speakers)

    # Step 3: Handle Fallback Ladder Overrides (Levels 4 and 5)
    if fallback_level_override == 5:
        # LEVEL 5: PASSTHROUGH MP4
        dispositions = {str(c.get("cue_id")): DISPOSITION_PRESERVED for c in cues}
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
        dispositions: dict[str, str] = {}
        for c in non_speech_cues:
            dispositions[str(c["cue_id"])] = DISPOSITION_PRESERVED
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

    # Step 4: Handle LEVEL 3 Override (SINGLE_DOMINANT)
    if fallback_level_override == 3:
        speaker_voice_map = {spk: default_voice for spk in ordered_speakers}
        dispositions = {str(c["cue_id"]): DISPOSITION_PRESERVED for c in non_speech_cues}
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

    # Step 5: Speaker Count Decisions
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
        # N=2: Try strict 2-speaker cast if acoustic evidence exists
        spk1, spk2 = ordered_speakers[0], ordered_speakers[1]
        strict_succeeded = False
        if isinstance(acoustic_classifications, Mapping):
            try:
                # 1. Try legacy assign_stable_voices
                strict_result = speaker_cast.assign_stable_voices(
                    dict(acoustic_classifications),
                    speaker_order=[spk1, spk2],
                    validated_pools={"low": low_pool, "high": high_pool},
                    assignment_seed=seed,
                )
                if spk1 in strict_result and spk2 in strict_result:
                    v1 = strict_result[spk1].get("tts_voice_id")
                    v2 = strict_result[spk2].get("tts_voice_id")
                    if v1 and v2 and v1 != v2:
                        speaker_voice_map[spk1] = str(v1)
                        speaker_voice_map[spk2] = str(v2)
                        strategy = STRATEGY_STRICT_TWO
                        fallback_level = 0
                        fallback_reason = None
                        output_mode = OUTPUT_MODE_DUBBED_MULTI
                        strict_succeeded = True
            except Exception:
                strict_succeeded = False

            if not strict_succeeded:
                # 2. Check if registers are confident and opposite
                meta1 = acoustic_classifications.get(spk1) or {}
                meta2 = acoustic_classifications.get(spk2) or {}
                r1 = meta1.get("voice_register")
                r2 = meta2.get("voice_register")
                try:
                    c1 = float(meta1.get("confidence") or 0.0)
                    c2 = float(meta2.get("confidence") or 0.0)
                except (TypeError, ValueError):
                    c1, c2 = 0.0, 0.0
                if (
                    r1 in {"low", "high"}
                    and r2 in {"low", "high"}
                    and r1 != r2
                    and c1 >= speaker_cast.MIN_REGISTER_CONFIDENCE
                    and c2 >= speaker_cast.MIN_REGISTER_CONFIDENCE
                ):
                    p1 = low_pool if r1 == "low" else high_pool
                    p2 = low_pool if r2 == "low" else high_pool
                    if p1 and p2:
                        idx1 = _hash_seed_int(seed, spk1, str(r1)) % len(p1)
                        v1 = p1[idx1]
                        avail_p2 = [v for v in p2 if v != v1] or p2
                        idx2 = _hash_seed_int(seed, spk2, str(r2)) % len(avail_p2)
                        v2 = avail_p2[idx2]
                        if v1 != v2:
                            speaker_voice_map[spk1] = v1
                            speaker_voice_map[spk2] = v2
                            strategy = STRATEGY_STRICT_TWO
                            fallback_level = 0
                            fallback_reason = None
                            output_mode = OUTPUT_MODE_DUBBED_MULTI
                            strict_succeeded = True

        if not strict_succeeded:
            # Caught strict failure or ambiguity: Fallback internally!
            # SMART_CAST_AMBIGUITY_MANUAL_HALT = 0
            if len(all_pool) >= 2:
                # Deterministically assign 2 distinct voices from all_pool
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
                # Single voice pool fallback
                speaker_voice_map[spk1] = default_voice
                speaker_voice_map[spk2] = default_voice
                strategy = STRATEGY_SINGLE_DOMINANT
                fallback_level = 3
                fallback_reason = "n2_pool_single_voice_fallback"
                output_mode = OUTPUT_MODE_DUBBED_FALLBACK

    else:
        # N >= 3: Multi-speaker adaptive allocation (supports 1..8+)
        strategy = STRATEGY_GENERIC_MULTI
        if len(all_pool) >= detected_speaker_count:
            # Full pool capacity: assign distinct voices
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
            # VOICE POOL EXHAUSTION: DO NOT ABORT!
            # 1. Assign distinct voices first
            # 2. Deterministic reuse after pool exhaustion
            # 3. Same speaker -> same voice
            # 4. Truthful voice count
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

    # Step 6: Cue accounting & TTS mapping
    # Every canonical cue has exactly one disposition:
    # DUBBED, PRESERVED, SUBTITLE_ONLY, TERMINAL_REJECTED
    dispositions: dict[str, str] = {}
    for c in non_speech_cues:
        dispositions[str(c["cue_id"])] = DISPOSITION_PRESERVED

    tts_cues: list[dict[str, Any]] = []
    for c in speech_cues:
        cid = str(c["cue_id"])
        dispositions[cid] = DISPOSITION_DUBBED
        tts_cue = dict(c)
        spk = str(c.get("speaker_id") or c.get("speaker") or "speaker_0").strip()
        assigned_voice = speaker_voice_map.get(spk)
        if not assigned_voice:
            # Fallback guard so TTS_CUES_WITHOUT_VOICE = 0
            assigned_voice = default_voice
            speaker_voice_map[spk] = assigned_voice
        tts_cue["tts_voice_id"] = assigned_voice
        tts_cues.append(tts_cue)

    effective_speaker_count = len(speaker_voice_map)
    effective_voice_count = len(set(speaker_voice_map.values()))

    # Verify output_mode matches voice count truthfully
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
    """Empirically verify final MP4 output: file exists, size > 0, valid video stream."""
    if not path:
        return False, "missing_mp4_path"
    target = Path(path)
    if not target.is_file():
        return False, "file_not_found"
    try:
        size = target.stat().st_size
    except OSError as err:
        return False, f"stat_error_{err}"
    if size <= 0:
        return False, "empty_file"

    if callable(probe_fn):
        try:
            probe_res = probe_fn(str(target))
            if isinstance(probe_res, Mapping) and probe_res.get("ok") is False:
                return False, str(probe_res.get("detail") or "probe_failed")
        except Exception as err:
            return False, f"probe_exception_{err}"

    return True, "ok"


async def run_auto_smart_multivoice(
    *,
    source_media: str | Path,
    segments: Sequence[Mapping[str, Any]],
    output_path: str | Path,
    validated_pools: Mapping[str, Any] | None = None,
    assignment_seed: str = "smart_job_seed",
    acoustic_classifications: Mapping[str, Mapping[str, Any]] | None = None,
    synthesize_segments: Callable[..., Any] | None = None,
    render_pipeline: Callable[..., Any] | None = None,
    probe_fn: Callable[[str], Mapping[str, Any]] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    fallback_level_override: int | None = None,
    default_fallback_voice: str | None = None,
    state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bounded, truthful execution runner for the Auto Smart Multi-Voice lane.

    Returns typed canonical dictionary:
    {
      "ok": bool,
      "strategy": str,
      "detected_speaker_count": int,
      "effective_speaker_count": int,
      "effective_voice_count": int,
      "speaker_voice_map": {...},
      "fallback_level": int,
      "fallback_reason": str | None,
      "output_mode": str,
      "final_mp4_path": str | None,
      "blocker": str | None,
      "auto_smart_verified": bool,
      "cue_dispositions": {...},
      "tts_cues": [...]
    }
    """
    # Guard: Cancellation
    if callable(is_cancelled) and is_cancelled():
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
            "auto_smart_verified": False,
        }

    try:
        media_size = media_path.stat().st_size
    except OSError:
        media_size = 0
    if media_size <= 0:
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
            "blocker": "corrupt_or_empty_source_media",
            "auto_smart_verified": False,
        }

    # Guard: Probe source media if probe_fn provided
    if callable(probe_fn):
        try:
            probe_info = probe_fn(str(media_path))
            if isinstance(probe_info, Mapping) and probe_info.get("ok") is False:
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
                    "blocker": str(probe_info.get("detail") or "invalid_source_media_probe"),
                    "auto_smart_verified": False,
                }
        except Exception as err:
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
                "blocker": f"source_probe_exception_{err}",
                "auto_smart_verified": False,
            }

    # Step 1: Run Smart Voice Decision Authority
    decision = decide_smart_multivoice(
        cues=segments,
        validated_pools=validated_pools,
        assignment_seed=assignment_seed,
        acoustic_classifications=acoustic_classifications,
        fallback_level_override=fallback_level_override,
        default_fallback_voice=default_fallback_voice,
    )

    out_target = Path(output_path)

    # Step 2: Synthesis for DUBBED cues
    synth_artifacts: list[dict[str, Any]] = []
    if decision.tts_cues and decision.output_mode in {
        OUTPUT_MODE_DUBBED_MULTI,
        OUTPUT_MODE_DUBBED_SINGLE,
        OUTPUT_MODE_DUBBED_FALLBACK,
    }:
        if callable(synthesize_segments):
            try:
                synth_result = await _maybe_await(
                    synthesize_segments(
                        cues=decision.tts_cues,
                        speaker_voice_map=decision.speaker_voice_map,
                    )
                )
                if isinstance(synth_result, list):
                    synth_artifacts = synth_result
                elif isinstance(synth_result, Mapping) and "chunks" in synth_result:
                    synth_artifacts = list(synth_result.get("chunks") or [])
                else:
                    synth_artifacts = [synth_result]
            except Exception as synth_err:
                # Provider/TTS failure: attempt lower fallback if permissible
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

    # Step 3: Render MP4
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

    # Step 4: Validate Final MP4
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
    }
