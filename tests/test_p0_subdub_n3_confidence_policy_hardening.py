"""Dedicated test suite for N>=3 confidence policy hardening and contract restore (Issue #1178, R4.2).

Proves:
1. MIN_PANN_SCORE_MARGIN == 0.08 constant
2. median_margin = 0.079999 fails closed via margin gate (< 0.08)
3. exact median_margin = 0.080000 + dominance = 2/3 passes (confidence = 0.750000 >= 0.75)
4. median_margin = 0.080001 + dominance = 2/3 passes (confidence = 0.750000)
5. True mathematical median for even-count cues (mean of two middle values, e.g. [0.08, 0.10, 0.14, 0.20] -> 0.12, not 0.14)
6. High margin with low dominance (< 2/3) fails closed via dominance gate
7. Near-zero margin with high dominance (1.0) fails closed via margin gate
8. No artificial confidence floor (max(0.75, ...))
9. No margin multiplier or margin-derived scaling in confidence formula
10. pann_score_margin output matches true mathematical median
"""

import inspect
import pytest

from services import subdub_multi_speaker_gender_onnx as multi_onnx
from services import subdub_speaker_cast as speaker_cast


def test_constant_min_pann_score_margin_is_008():
    """Verify frozen constant values."""
    assert multi_onnx.MIN_PANN_SCORE_MARGIN == 0.08
    assert multi_onnx.MIN_ACOUSTIC_SCORE_MARGIN == 0.08
    assert multi_onnx.MIN_VOTE_DOMINANCE == pytest.approx(2.0 / 3.0, abs=1e-6)
    assert speaker_cast.MIN_REGISTER_CONFIDENCE == 0.75


def test_median_margin_0_079999_fails_closed_via_margin_gate():
    """Boundary Case A: dominance >= 2/3, median_margin = 0.079999 -> FAIL_CLOSED (Gate 2 blocks)."""
    # 3 cues, all male votes (dominance = 1.0 >= 2/3)
    # per-cue margin = |0.5399995 - 0.4600005| / 1.0 = 0.079999
    cues = [
        {"start": 0.0, "end": 1.0, "male_score": 0.5399995, "female_score": 0.4600005},
        {"start": 1.0, "end": 2.0, "male_score": 0.5399995, "female_score": 0.4600005},
        {"start": 2.0, "end": 3.0, "male_score": 0.5399995, "female_score": 0.4600005},
    ]
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        multi_onnx._aggregate_one_gender_result("spk_margin_0_079999", cues)


def test_exact_median_margin_0_080000_and_dominance_two_thirds_passes():
    """Boundary Case B: dominance = 2/3, median_margin = 0.080000 -> PASS.

    Gate 1: dominance = 2/3 >= 2/3 -> PASS
    Gate 2: median_margin = 0.080000 >= 0.08 -> PASS
    Confidence = clamp(0.25 + 0.75 * (2/3), 0.0, 1.0) = 0.750000 >= 0.75 -> ELIGIBLE / PASS.
    """
    # 3 cues: 2 male votes, 1 female vote -> dominance = 2/3
    # All 3 cues have per-cue margin = 0.08:
    cues = [
        {"start": 0.0, "end": 1.0, "male_score": 0.5400000, "female_score": 0.4600000},
        {"start": 1.0, "end": 2.0, "male_score": 0.5400000, "female_score": 0.4600000},
        {"start": 2.0, "end": 3.0, "male_score": 0.4600000, "female_score": 0.5400000},
    ]
    res, rows = multi_onnx._aggregate_one_gender_result("spk_exact_0_080000", cues)
    assert res["voice_gender"] == "male"
    assert res["voice_register"] == "low"
    assert res["confidence"] == 0.75
    assert res["confidence"] >= speaker_cast.MIN_REGISTER_CONFIDENCE
    assert res["pann_score_margin"] == pytest.approx(0.08, abs=1e-6)
    assert len(rows) == 3


def test_median_margin_0_080001_and_dominance_two_thirds_passes():
    """Boundary Case C: dominance = 2/3, median_margin = 0.080001 -> PASS (confidence = 0.750000)."""
    cues = [
        {"start": 0.0, "end": 1.0, "male_score": 0.5400005, "female_score": 0.4599995},
        {"start": 1.0, "end": 2.0, "male_score": 0.5400005, "female_score": 0.4599995},
        {"start": 2.0, "end": 3.0, "male_score": 0.4599995, "female_score": 0.5400005},
    ]
    res, rows = multi_onnx._aggregate_one_gender_result("spk_0_080001", cues)
    assert res["voice_gender"] == "male"
    assert res["confidence"] == 0.75
    assert res["confidence"] >= speaker_cast.MIN_REGISTER_CONFIDENCE
    assert res["pann_score_margin"] == pytest.approx(0.080001, abs=1e-6)


def test_true_even_count_median_mathematical_mean():
    """Prove true mathematical median for even-count cues (mean of two middle values).

    Given sorted margins: [0.08, 0.10, 0.14, 0.20]
    True median = (0.10 + 0.14) / 2 = 0.12.
    Old buggy code picked index 4//2 = 2 -> 0.14.
    """
    # 4 cues, all male votes (dominance = 4/4 = 1.0)
    cues = [
        {"start": 0.0, "end": 1.0, "male_score": 0.54, "female_score": 0.46},  # margin = 0.08
        {"start": 1.0, "end": 2.0, "male_score": 0.55, "female_score": 0.45},  # margin = 0.10
        {"start": 2.0, "end": 3.0, "male_score": 0.57, "female_score": 0.43},  # margin = 0.14
        {"start": 3.0, "end": 4.0, "male_score": 0.60, "female_score": 0.40},  # margin = 0.20
    ]
    res, rows = multi_onnx._aggregate_one_gender_result("spk_even_median", cues)
    assert res["pann_score_margin"] == pytest.approx(0.12, abs=1e-6)
    assert res["pann_score_margin"] != 0.14  # MUST NOT be upper-middle
    assert res["confidence"] == 1.0
    assert len(rows) == 4


def test_true_odd_count_median():
    """Verify odd-count cues select the exact middle element."""
    # 3 cues with margins [0.08, 0.12, 0.18] -> median = 0.12
    cues = [
        {"start": 0.0, "end": 1.0, "male_score": 0.54, "female_score": 0.46},  # margin = 0.08
        {"start": 1.0, "end": 2.0, "male_score": 0.56, "female_score": 0.44},  # margin = 0.12
        {"start": 2.0, "end": 3.0, "male_score": 0.59, "female_score": 0.41},  # margin = 0.18
    ]
    res, rows = multi_onnx._aggregate_one_gender_result("spk_odd_median", cues)
    assert res["pann_score_margin"] == pytest.approx(0.12, abs=1e-6)


def test_high_margin_low_dominance_fails_closed():
    """Boundary Case D: high acoustic margin but dominance < 2/3 -> FAIL_CLOSED via Gate 1."""
    # 4 cues: 2 male votes, 2 female votes -> dominance = 2/4 = 0.50 < 2/3
    # Margins are very strong (0.60)
    cues = [
        {"start": 0.0, "end": 1.0, "male_score": 0.80, "female_score": 0.20},
        {"start": 1.0, "end": 2.0, "male_score": 0.80, "female_score": 0.20},
        {"start": 2.0, "end": 3.0, "male_score": 0.20, "female_score": 0.80},
        {"start": 3.0, "end": 4.0, "male_score": 0.20, "female_score": 0.80},
    ]
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        multi_onnx._aggregate_one_gender_result("spk_low_dominance", cues)


def test_near_zero_margin_high_dominance_fails_closed():
    """Boundary Case E: near-zero margin, dominance = 1.0 -> FAIL_CLOSED via Gate 2."""
    # 3 cues, all male votes (dominance = 1.0), but margin = |0.51 - 0.49| / 1.0 = 0.02 < 0.08
    cues = [
        {"start": 0.0, "end": 1.0, "male_score": 0.51, "female_score": 0.49},
        {"start": 1.0, "end": 2.0, "male_score": 0.51, "female_score": 0.49},
        {"start": 2.0, "end": 3.0, "male_score": 0.51, "female_score": 0.49},
    ]
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        multi_onnx._aggregate_one_gender_result("spk_near_zero_margin", cues)


def test_no_artificial_confidence_floor():
    """Verify confidence has no artificial floor (no max(0.75, ...))."""
    src = inspect.getsource(multi_onnx._aggregate_one_gender_result)
    assert "max(0.75" not in src, "Artificial confidence floor max(0.75, ...) found in source!"


def test_no_margin_multiplier_in_confidence():
    """Verify confidence does NOT multiply or scale by acoustic margin."""
    src = inspect.getsource(multi_onnx._aggregate_one_gender_result)
    assert "median_margin" not in src.split("confidence =")[1].split("return")[0], (
        "median_margin must NOT be used in confidence formula!"
    )

    # Prove empirically: varying margin from 0.08 to 0.70 at fixed dominance (2/3) yields identical confidence (0.75)
    cues_m08 = [
        {"start": 0.0, "end": 1.0, "male_score": 0.54, "female_score": 0.46},  # margin 0.08
        {"start": 1.0, "end": 2.0, "male_score": 0.54, "female_score": 0.46},  # margin 0.08
        {"start": 2.0, "end": 3.0, "male_score": 0.46, "female_score": 0.54},  # margin 0.08
    ]
    res_m08, _ = multi_onnx._aggregate_one_gender_result("spk_m08", cues_m08)

    cues_m70 = [
        {"start": 0.0, "end": 1.0, "male_score": 0.85, "female_score": 0.15},  # margin 0.70
        {"start": 1.0, "end": 2.0, "male_score": 0.85, "female_score": 0.15},  # margin 0.70
        {"start": 2.0, "end": 3.0, "male_score": 0.15, "female_score": 0.85},  # margin 0.70
    ]
    res_m70, _ = multi_onnx._aggregate_one_gender_result("spk_m70", cues_m70)

    assert res_m08["confidence"] == 0.75
    assert res_m70["confidence"] == 0.75
    assert res_m08["confidence"] == res_m70["confidence"]
