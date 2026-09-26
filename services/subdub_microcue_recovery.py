"""Safe Shared Micro-Cue Recovery for Cue-Locked SubDub Lanes.

Ensures that isolated short fragments (micro-cues) exceeding MAX_INTELLIGIBLE_FIT_RATIO (1.80)
can be safely coalesced with adjacent cues of the same speaker when a safe timing window
is available, avoiding unintelligible compression rejection while strictly maintaining:
- MAX_INTELLIGIBLE_FIT_RATIO = 1.80 unchanged
- NO_SILENT_CUE_DROP (preserves all text and audio)
- NO_CROSS_SPEAKER_MERGE
- NO_CROSS_NON_SPEECH_BOUNDARY
- NO_TIMELINE_EXTENSION
- NO_CUE_SHIFT_OUTSIDE_SOURCE_TIMELINE
- PRESERVE_ORIGINAL_CUE_PROVENANCE
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Canonical architectural limit: strictly unchanged
MAX_INTELLIGIBLE_FIT_RATIO: float = 1.80
DEFAULT_MAX_COALESCE_GAP_SECONDS: float = 0.5
DEFAULT_MAX_FRAGMENT_DURATION_SECONDS: float = 3.0


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


def can_coalesce_cues(
    left: dict[str, Any],
    right: dict[str, Any],
    max_gap_seconds: float = DEFAULT_MAX_COALESCE_GAP_SECONDS,
    max_fragment_duration_seconds: float = DEFAULT_MAX_FRAGMENT_DURATION_SECONDS,
) -> bool:
    """Evaluate whether two adjacent cues satisfy all safety gates for coalescing.

    Invariant safety gates:
    1. Same speaker (NO_CROSS_SPEAKER_MERGE)
    2. Neither cue is flagged with non_speech_boundary (NO_CROSS_NON_SPEECH_BOUNDARY)
    3. Gap between cues is within safe limits [-0.055s, max_gap_seconds] (NO_TIMELINE_EXTENSION)
    4. At least one cue is a short fragment eligible for recovery
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

    # 4. Short fragment candidate
    win_l = e_l - s_l
    win_r = e_r - s_r
    if min(win_l, win_r) > max_fragment_duration_seconds:
        return False

    return True


def coalesce_cue_pair(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Coalesce two adjacent cue items into a unified cue item.

    Preserves full text, concatenated audio, cumulative duration, expanded window,
    and original cue provenance.
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
    tot_dur = dur_l + dur_r
    fit_ratio = tot_dur / combined_window

    # Concatenate audio bytes if present
    aud_l = left.get("audio") if left.get("audio") is not None else left.get("audio_bytes")
    aud_r = right.get("audio") if right.get("audio") is not None else right.get("audio_bytes")
    if isinstance(aud_l, (bytes, bytearray)) and isinstance(aud_r, (bytes, bytearray)):
        combined_audio: Any = bytes(aud_l) + bytes(aud_r)
    else:
        combined_audio = aud_l or aud_r

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
        "audio_duration": tot_dur,
        "raw_audio_duration": tot_dur,
        "generated_audio_seconds": tot_dur,
        "fit_ratio": round(fit_ratio, 3),
        "coalesced": True,
        "cue_locked_timing": True,
        "original_cue_ids": combined_orig,
    })
    return coalesced


def recover_cue_locked_micro_cues(
    items: list[dict[str, Any]],
    max_fit_ratio: float = MAX_INTELLIGIBLE_FIT_RATIO,
    max_gap_seconds: float = DEFAULT_MAX_COALESCE_GAP_SECONDS,
    max_fragment_duration_seconds: float = DEFAULT_MAX_FRAGMENT_DURATION_SECONDS,
) -> list[dict[str, Any]]:
    """Recover cue-locked items by coalescing micro-cues that exceed max_fit_ratio.

    Operates iteratively:
    If an item has fit_ratio > max_fit_ratio, examines adjacent left and right same-speaker
    neighbors. If coalescing yields a combined fit_ratio <= max_fit_ratio, performs the coalescing.
    Prefers the neighbor that yields the lower combined fit_ratio (or left neighbor on tie).
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
                left_candidate = None
                right_candidate = None

                # 1. Left neighbor candidate
                if i > 0:
                    left = res[i - 1]
                    if can_coalesce_cues(left, item, max_gap_seconds, max_fragment_duration_seconds):
                        s_l, _ = _get_cue_start_end(left)
                        win = max(0.001, e - s_l)
                        dur = float(left.get("audio_duration") or left.get("raw_audio_duration") or 0.0) + d
                        comb_fit = dur / win
                        if comb_fit <= max_fit_ratio:
                            left_candidate = (comb_fit, i - 1, i)

                # 2. Right neighbor candidate
                if i < len(res) - 1:
                    right = res[i + 1]
                    if can_coalesce_cues(item, right, max_gap_seconds, max_fragment_duration_seconds):
                        _, e_r = _get_cue_start_end(right)
                        win = max(0.001, e_r - s)
                        dur = d + float(right.get("audio_duration") or right.get("raw_audio_duration") or 0.0)
                        comb_fit = dur / win
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
                    res[idx_a] = merged
                    del res[idx_b]
                    changed = True
                    break
            i += 1

    return res
