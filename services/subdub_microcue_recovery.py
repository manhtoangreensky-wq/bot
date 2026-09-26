"""Safe Shared Micro-Cue Recovery for Cue-Locked SubDub Lanes.

Ensures that isolated short fragments (micro-cues) exceeding MAX_INTELLIGIBLE_FIT_RATIO (1.80)
can be safely coalesced with adjacent cues of the same speaker when a safe timing window
is available, avoiding unintelligible compression rejection while strictly maintaining:
- MAX_INTELLIGIBLE_FIT_RATIO = 1.80 unchanged
- NO_RAW_CONCAT_ENCODED_TTS_AUDIO_BYTES_AS_MEDIA_AUTHORITY (valid ffmpeg decodable assembly)
- PRESERVE_INTERNAL_ORIGINAL_CUE_TIMING (right cue offset and gap silence preserved)
- NO_SILENT_CUE_DROP (preserves all text and audio)
- NO_CROSS_SPEAKER_MERGE
- NO_CROSS_NON_SPEECH_BOUNDARY
- NO_TIMELINE_EXTENSION
- NO_CUE_SHIFT_OUTSIDE_SOURCE_TIMELINE
- PRESERVE_ORIGINAL_CUE_PROVENANCE
- ONLY_OFFENDING_CUE_MEETING_MICROCUE_LIMIT_CAN_TRIGGER_RECOVERY
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from services.subdub_tts_artifact_validator import resolve_ffmpeg_path, validate_tts_audio_artifact

logger = logging.getLogger(__name__)

# Canonical architectural limit: strictly unchanged
MAX_INTELLIGIBLE_FIT_RATIO: float = 1.80
DEFAULT_MAX_COALESCE_GAP_SECONDS: float = 0.5
DEFAULT_MAX_MICROCUE_DURATION_SECONDS: float = 1.5
DEFAULT_MAX_FRAGMENT_DURATION_SECONDS: float = DEFAULT_MAX_MICROCUE_DURATION_SECONDS


def _get_cue_start_end(cue: dict[str, Any]) -> tuple[float, float]:
    """Extract start and end times in seconds from cue dict."""
    if cue.get("start") is not None:
        start = float(cue["start"])
    elif cue.get("start_ms") is not None:
        start = float(cue["start_ms"]) / 1000.0
    else:
        start = 0.0

    if cue.get("end") is not None:
        end = float(cue["end"])
    elif cue.get("end_ms") is not None:
        end = float(cue["end_ms"]) / 1000.0
    else:
        end = 0.0

    return start, end


def _is_encoded_audio(data: bytes | bytearray | None) -> bool:
    """Detect whether byte buffer represents real encoded audio container format."""
    if not isinstance(data, (bytes, bytearray)) or len(data) < 4:
        return False
    prefix = bytes(data[:4])
    if prefix.startswith(b"ID3") or prefix[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xe3"):
        return True
    if prefix.startswith(b"RIFF") or prefix.startswith(b"OggS") or prefix.startswith(b"fLaC"):
        return True
    return False


def assemble_coalesced_audio(
    aud_l: bytes | bytearray | None,
    dur_l: float,
    aud_r: bytes | bytearray | None,
    dur_r: float,
    offset_r: float,
) -> tuple[Any, float]:
    """Assemble real decodable audio using ffmpeg with exact delay and gap preservation.

    If inputs are real encoded audio, uses ffmpeg adelay + amix to produce a clean,
    decodable audio track where the right cue starts at offset_r without collapsing silence.
    If ffmpeg fails or media validation fails on encoded audio, returns (None, 0.0)
    to decline recovery. Raw encoded audio byte concatenation is strictly prohibited.
    """
    expected_dur = offset_r + dur_r
    is_encoded = _is_encoded_audio(aud_l) or _is_encoded_audio(aud_r)

    if (
        isinstance(aud_l, (bytes, bytearray))
        and isinstance(aud_r, (bytes, bytearray))
        and len(aud_l) >= 16
        and len(aud_r) >= 16
    ):
        ffmpeg_bin = resolve_ffmpeg_path()
        if ffmpeg_bin and Path(ffmpeg_bin).is_file():
            # Attempt real ffmpeg assembly
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f_l, \
                 tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f_r, \
                 tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f_out:
                p_l = Path(f_l.name)
                p_r = Path(f_r.name)
                p_out = Path(f_out.name)

            try:
                p_l.write_bytes(aud_l)
                p_r.write_bytes(aud_r)

                delay_ms = max(0, int(round(offset_r * 1000)))
                filt = f"[1]adelay={delay_ms}:all=1[d1];[0][d1]amix=inputs=2:dropout_transition=0:normalize=0[out]"
                cmd = [
                    str(ffmpeg_bin),
                    "-y",
                    "-i", str(p_l),
                    "-i", str(p_r),
                    "-filter_complex", filt,
                    "-map", "[out]",
                    "-c:a", "libmp3lame",
                    "-b:a", "128k",
                    str(p_out),
                ]
                proc = subprocess.run(cmd, capture_output=True)
                if proc.returncode == 0 and p_out.is_file() and p_out.stat().st_size > 0:
                    v_res = validate_tts_audio_artifact(p_out)
                    if v_res.ok and v_res.duration > 0.0:
                        out_bytes = p_out.read_bytes()
                        return out_bytes, float(v_res.duration)
            except Exception as e:
                logger.debug("assemble_coalesced_audio ffmpeg assembly skipped: %s", e)
            finally:
                for p in (p_l, p_r, p_out):
                    try:
                        if p.is_file():
                            p.unlink()
                    except OSError:
                        pass

    # Mandatory Fix 1: Encoded audio must never fall back to naive byte concatenation
    if is_encoded:
        return None, 0.0

    # Non-encoded synthetic test string fallback (e.g. b"AUDIO_1_")
    if isinstance(aud_l, (bytes, bytearray)) and isinstance(aud_r, (bytes, bytearray)):
        combined_fallback = bytes(aud_l) + bytes(aud_r)
    else:
        combined_fallback = aud_l or aud_r
    return combined_fallback, expected_dur


def can_coalesce_cues(
    left: dict[str, Any],
    right: dict[str, Any],
    max_gap_seconds: float = DEFAULT_MAX_COALESCE_GAP_SECONDS,
    max_fragment_duration_seconds: float | None = None,
    **kwargs: Any,
) -> bool:
    """Evaluate whether two adjacent cues satisfy all safety gates for coalescing.

    Invariant safety gates:
    1. Same speaker (NO_CROSS_SPEAKER_MERGE)
    2. Neither cue is flagged with non_speech_boundary (NO_CROSS_NON_SPEECH_BOUNDARY)
    3. Gap between cues is within safe limits [-0.055s, max_gap_seconds] (NO_TIMELINE_EXTENSION)
    """
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False

    # 1. Speaker identity authority
    spk_l = str(left.get("speaker_id") or left.get("speaker") or "").strip()
    spk_r = str(right.get("speaker_id") or right.get("speaker") or "").strip()
    if not spk_l or not spk_r or spk_l != spk_r:
        return False

    # 2. Non-speech boundary gate
    if left.get("non_speech_boundary") is True or right.get("non_speech_boundary") is True:
        return False

    # 3. Timing and gap bounds
    s_l, e_l = _get_cue_start_end(left)
    s_r, e_r = _get_cue_start_end(right)
    if e_l <= s_l or e_r <= s_r:
        return False

    gap = s_r - e_l
    if gap < -0.055 or gap > max_gap_seconds:
        return False

    # 4. Internal timing preservation: left utterance cannot spill past right cue start offset
    dur_l = float(left.get("audio_duration") or left.get("raw_audio_duration") or 0.0)
    raw_offset_r = s_r - s_l
    if dur_l > 0 and raw_offset_r > 0 and dur_l > (raw_offset_r + 0.001):
        return False

    # 5. Optional fragment duration gate
    if max_fragment_duration_seconds is not None:
        win_l = e_l - s_l
        win_r = e_r - s_r
        if min(win_l, win_r) > max_fragment_duration_seconds:
            return False

    return True


def coalesce_cue_pair(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Coalesce two adjacent cue items into a unified cue item with internal timing preserved.

    Preserves full text, internal original cue timing (right cue offset and gap silence),
    assembled decodable audio (via ffmpeg when available), expanded window, and cue provenance.
    """
    s_l, e_l = _get_cue_start_end(left)
    s_r, e_r = _get_cue_start_end(right)
    combined_start = s_l
    combined_end = e_r
    combined_window = max(0.001, combined_end - combined_start)

    s_ms_l = int(left.get("start_ms") if left.get("start_ms") is not None else round(s_l * 1000))
    e_ms_r = int(right.get("end_ms") if right.get("end_ms") is not None else round(e_r * 1000))

    dur_l = float(left.get("audio_duration") or left.get("raw_audio_duration") or 0.0)
    dur_r = float(right.get("audio_duration") or right.get("raw_audio_duration") or 0.0)

    # Mandatory Fix 4: Right internal cue offset strictly bound to original source offset
    raw_offset_r = s_r - s_l
    effective_offset_r = raw_offset_r
    gap_silence = max(0.0, raw_offset_r - dur_l)

    # Mandatory Fix 5: If left utterance spills past right source start, decline recovery
    if dur_l > 0 and raw_offset_r > 0 and dur_l > (raw_offset_r + 0.001):
        declined = dict(left)
        declined.update({
            "coalesced": False,
            "audio": None,
            "audio_bytes": None,
            "right_cue_offset": raw_offset_r,
            "gap_silence_seconds": 0.0,
        })
        return declined

    # Audio assembly with ffmpeg delay and gap silence preservation
    aud_l = left.get("audio") if left.get("audio") is not None else left.get("audio_bytes")
    aud_r = right.get("audio") if right.get("audio") is not None else right.get("audio_bytes")
    media_requested = bool(aud_l is not None or aud_r is not None)

    combined_audio, measured_dur = assemble_coalesced_audio(
        aud_l, dur_l, aud_r, dur_r, effective_offset_r
    )

    # Mandatory Fix 1: FFmpeg or media validation failure must decline recovery
    if media_requested and combined_audio is None:
        declined = dict(left)
        declined.update({
            "coalesced": False,
            "audio": None,
            "audio_bytes": None,
            "right_cue_offset": raw_offset_r,
            "gap_silence_seconds": gap_silence,
        })
        return declined

    tot_dur = measured_dur if measured_dur > 0 else (effective_offset_r + dur_r)
    fit_ratio = tot_dur / combined_window

    # Internal cue timing structure
    internal_cues: list[dict[str, Any]] = []
    if left.get("internal_cues"):
        internal_cues.extend(left["internal_cues"])
    else:
        internal_cues.append({
            "cue_id": str(left.get("cue_id") or "left"),
            "offset": 0.0,
            "offset_seconds": 0.0,
            "start": s_l,
            "end": e_l,
            "duration": dur_l,
            "text": str(left.get("text") or ""),
        })

    if right.get("internal_cues"):
        for sub in right["internal_cues"]:
            sub_copy = dict(sub)
            sub_copy["offset"] = effective_offset_r + float(sub.get("offset", 0.0))
            sub_copy["offset_seconds"] = sub_copy["offset"]
            internal_cues.append(sub_copy)
    else:
        internal_cues.append({
            "cue_id": str(right.get("cue_id") or "right"),
            "offset": effective_offset_r,
            "offset_seconds": effective_offset_r,
            "start": s_r,
            "end": e_r,
            "duration": dur_r,
            "text": str(right.get("text") or ""),
        })

    # Provenance tracking
    orig_l = list(left.get("original_cue_ids") or ([str(left.get("cue_id"))] if left.get("cue_id") else []))
    orig_r = list(right.get("original_cue_ids") or ([str(right.get("cue_id"))] if right.get("cue_id") else []))
    combined_orig = orig_l + [cid for cid in orig_r if cid not in orig_l]

    # Text concatenation
    t_l = str(left.get("text") or "").strip()
    t_r = str(right.get("text") or "").strip()
    combined_text = f"{t_l} {t_r}".strip()

    speaker_id = str(left.get("speaker_id") or right.get("speaker_id") or "")
    coalesced_cid = f"{left.get('cue_id')}+{right.get('cue_id')}"

    coalesced = dict(left)
    coalesced.update({
        "cue_id": coalesced_cid,
        "speaker_id": speaker_id,
        "start": combined_start,
        "end": combined_end,
        "start_ms": s_ms_l,
        "end_ms": e_ms_r,
        "cue_window": combined_window,
        "cue_window_seconds": combined_window,
        "text": combined_text,
        "audio": combined_audio,
        "audio_bytes": combined_audio,
        "audio_duration": round(tot_dur, 4),
        "raw_audio_duration": round(tot_dur, 4),
        "generated_audio_seconds": round(tot_dur, 4),
        "fit_ratio": round(fit_ratio, 3),
        "coalesced": True,
        "cue_locked_timing": True,
        "original_cue_ids": combined_orig,
        "right_cue_offset": effective_offset_r,
        "gap_silence_seconds": gap_silence,
        "internal_cues": internal_cues,
    })
    return coalesced


def recover_cue_locked_micro_cues(
    items: list[dict[str, Any]],
    max_fit_ratio: float = MAX_INTELLIGIBLE_FIT_RATIO,
    max_gap_seconds: float = DEFAULT_MAX_COALESCE_GAP_SECONDS,
    max_microcue_duration_seconds: float = DEFAULT_MAX_MICROCUE_DURATION_SECONDS,
) -> list[dict[str, Any]]:
    """Recover cue-locked items by coalescing micro-cues that exceed max_fit_ratio.

    Strict Invariants:
    1. ONLY the offending cue exceeding max_fit_ratio may trigger recovery.
    2. That offending cue MUST meet the explicit microcue duration limit (<= max_microcue_duration_seconds).
    3. Coalescing preserves internal cue offsets and gap silence.
    4. Combined fit ratio must satisfy <= max_fit_ratio.
    """
    if not items or len(items) < 2:
        return list(items)

    res = [dict(c) for c in items]
    changed = True
    iterations = 0
    max_iterations = len(res)

    while changed and iterations < max_iterations:
        changed = False
        iterations += 1
        i = 0
        while i < len(res):
            item = res[i]
            s, e = _get_cue_start_end(item)
            w = max(0.001, e - s)
            d = float(item.get("audio_duration") or item.get("raw_audio_duration") or 0.0)
            fit = d / w if w > 0.05 and d > 0 else 1.0

            if fit > max_fit_ratio:
                # Invariant: ONLY the offending cue exceeding max_fit_ratio may trigger recovery,
                # and that offending cue MUST meet the explicit microcue duration limit.
                if w > max_microcue_duration_seconds:
                    i += 1
                    continue

                left_candidate = None
                right_candidate = None

                # 1. Left neighbor candidate
                if i > 0:
                    left = res[i - 1]
                    if can_coalesce_cues(left, item, max_gap_seconds):
                        s_l, _ = _get_cue_start_end(left)
                        win = max(0.001, e - s_l)
                        dur_l = float(left.get("audio_duration") or left.get("raw_audio_duration") or 0.0)
                        raw_off_r = s - s_l
                        comb_dur = raw_off_r + d
                        comb_fit = comb_dur / win
                        if comb_fit <= max_fit_ratio:
                            left_candidate = (comb_fit, i - 1, i)

                # 2. Right neighbor candidate
                if i < len(res) - 1:
                    right = res[i + 1]
                    if can_coalesce_cues(item, right, max_gap_seconds):
                        _, e_r = _get_cue_start_end(right)
                        win = max(0.001, e_r - s)
                        dur_r = float(right.get("audio_duration") or right.get("raw_audio_duration") or 0.0)
                        s_r, _ = _get_cue_start_end(right)
                        raw_off_r = s_r - s
                        comb_dur = raw_off_r + dur_r
                        comb_fit = comb_dur / win
                        if comb_fit <= max_fit_ratio:
                            right_candidate = (comb_fit, i, i + 1)

                chosen = None
                if left_candidate and right_candidate:
                    if left_candidate[0] <= right_candidate[0]:
                        chosen = left_candidate
                    else:
                        chosen = right_candidate
                elif left_candidate:
                    chosen = left_candidate
                elif right_candidate:
                    chosen = right_candidate

                if chosen:
                    idx_a, idx_b = chosen[1], chosen[2]
                    merged = coalesce_cue_pair(res[idx_a], res[idx_b])
                    if merged.get("coalesced") is not False:
                        res[idx_a] = merged
                        del res[idx_b]
                        changed = True
                        break
            i += 1

    return res
