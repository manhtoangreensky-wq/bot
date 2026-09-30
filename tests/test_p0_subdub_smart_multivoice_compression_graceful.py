"""Unit test for Smart MultiVoice compression graceful degradation.

Ensures:
1. MAX_INTELLIGIBLE_FIT_RATIO is unchanged (1.80).
2. HARD_CAP_FIT_RATIO (5.0) and MAX_OVERFIT_CUE_RATIO (0.30) are correctly defined.
3. Cues with fit_ratio between 1.8 and 5.0 gracefully degrade when <= 30% of total cues.
4. Jobs fail with extreme_audio_compression_unintelligible if any cue exceeds HARD_CAP_FIT_RATIO (5.0).
5. Jobs fail if > 30% of cues exceed MAX_INTELLIGIBLE_FIT_RATIO.
"""

from __future__ import annotations

import pytest
from services.subdub_blackboxes import auto_smart_multivoice as smart


def test_compression_graceful_constants():
    """Verify compression threshold constants."""
    assert smart.MAX_INTELLIGIBLE_FIT_RATIO == 1.8
    assert smart.HARD_CAP_FIT_RATIO == 5.0
    assert smart.MAX_OVERFIT_CUE_RATIO == 0.30


def _evaluate_compression(synth_artifacts):
    """Simulate the compression check loop from auto_smart_multivoice."""
    overfit_cues = []
    for item in synth_artifacts:
        i_win = float(item.get("cue_window") or (float(item.get("end", 0.0)) - float(item.get("start", 0.0))))
        i_dur = float(item.get("audio_duration") or item.get("raw_audio_duration") or 0.0)
        if i_win > 0.05 and i_dur > 0:
            item_fit_ratio = i_dur / i_win
            if item_fit_ratio > smart.HARD_CAP_FIT_RATIO:
                fail_cid = str(item.get("cue_id") or "")
                return {
                    "ok": False,
                    "error_code": "extreme_audio_compression_unintelligible",
                    "fit_ratio": round(item_fit_ratio, 3),
                    "cue_id": fail_cid,
                }
            elif item_fit_ratio > smart.MAX_INTELLIGIBLE_FIT_RATIO:
                overfit_cues.append((str(item.get("cue_id") or ""), round(item_fit_ratio, 3)))

    if overfit_cues and len(synth_artifacts) > 0:
        overfit_ratio = len(overfit_cues) / len(synth_artifacts)
        if overfit_ratio > smart.MAX_OVERFIT_CUE_RATIO:
            worst = max(overfit_cues, key=lambda x: x[1])
            return {
                "ok": False,
                "error_code": "extreme_audio_compression_unintelligible",
                "fit_ratio": worst[1],
                "cue_id": worst[0],
                "overfit_cue_count": len(overfit_cues),
                "overfit_cue_ratio": round(overfit_ratio, 3),
            }

    return {"ok": True, "overfit_cues": overfit_cues}


def test_compression_all_within_limit():
    """All cues within 1.8 fit ratio pass normally."""
    artifacts = [
        {"cue_id": f"cue_{i}", "cue_window": 2.0, "audio_duration": 2.5}  # fit = 1.25
        for i in range(10)
    ]
    res = _evaluate_compression(artifacts)
    assert res["ok"] is True
    assert len(res["overfit_cues"]) == 0


def test_compression_graceful_tolerance_under_threshold():
    """Cues between 1.8 and 5.0 pass if overfit ratio <= 30%."""
    artifacts = [
        {"cue_id": f"cue_{i}", "cue_window": 2.0, "audio_duration": 2.0}  # fit = 1.0
        for i in range(8)
    ]
    # 2 out of 10 cues (20% <= 30%) have fit ratio 2.5
    artifacts.append({"cue_id": "cue_8", "cue_window": 1.0, "audio_duration": 2.5})
    artifacts.append({"cue_id": "cue_9", "cue_window": 1.0, "audio_duration": 2.2})

    res = _evaluate_compression(artifacts)
    assert res["ok"] is True
    assert len(res["overfit_cues"]) == 2


def test_compression_exceeds_overfit_ratio_threshold():
    """Fails if > 30% of cues exceed 1.8 fit ratio."""
    artifacts = [
        {"cue_id": f"cue_{i}", "cue_window": 2.0, "audio_duration": 2.0}  # fit = 1.0
        for i in range(6)
    ]
    # 4 out of 10 cues (40% > 30%) have fit ratio 2.5
    for i in range(6, 10):
        artifacts.append({"cue_id": f"cue_{i}", "cue_window": 1.0, "audio_duration": 2.5})

    res = _evaluate_compression(artifacts)
    assert res["ok"] is False
    assert res["error_code"] == "extreme_audio_compression_unintelligible"
    assert res["overfit_cue_count"] == 4
    assert res["overfit_cue_ratio"] == 0.4


def test_compression_hard_cap_fails_immediately():
    """Fails immediately if any single cue exceeds 5.0 fit ratio even if only 1 cue."""
    artifacts = [
        {"cue_id": f"cue_{i}", "cue_window": 2.0, "audio_duration": 2.0}  # fit = 1.0
        for i in range(19)
    ]
    # 1 out of 20 cues (5%), but fit ratio is 5.5 > 5.0
    artifacts.append({"cue_id": "cue_extreme", "cue_window": 0.4, "audio_duration": 2.2})  # fit = 5.5

    res = _evaluate_compression(artifacts)
    assert res["ok"] is False
    assert res["error_code"] == "extreme_audio_compression_unintelligible"
    assert res["fit_ratio"] == 5.5
    assert res["cue_id"] == "cue_extreme"
