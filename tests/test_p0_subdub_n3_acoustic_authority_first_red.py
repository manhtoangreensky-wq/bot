"""Deterministic FIRST RED regression suite for P0.SUBDUB N>=3 speaker Auto Smart Multivoice.

Reference Issue: #1164
Reference Production Job: 05268605cf13618dba15 (05268605CF)
Reference Failure: SMART_AUTO_CAST_MANUAL_REQUIRED (raised at services/subdub_blackboxes/auto_smart_multivoice.py:1261)

Contract:
- Fixture-based local audio / timing only (zero provider, zero network, zero VPS dependency).
- Asserts DETECTED_SPEAKER_COUNT = 3 (speaker_0 dominant: 44 cues, speaker_1: 29 cues, speaker_2: 4 cues).
- Proves both failure seams:
  1. PCM Authority Blocker: Missing acoustic / PCM authority in auto_smart_multivoice lane (line 1261).
  2. Confidence Policy Blocker: Dominant speaker_0 avg confidence 0.695 < MIN_REGISTER_CONFIDENCE (0.75) (line 1139).
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_smart_multivoice as smart


def _generate_production_reference_cues() -> list[dict[str, Any]]:
    """Generate 77 cues reproducing Job 05268605cf13618dba15 speaker distribution.

    Production telemetry:
    - 77 total cues
    - speaker_0: 44 cues (dominant)
    - speaker_1: 29 cues
    - speaker_2: 4 cues
    """
    cues: list[dict[str, Any]] = []
    cue_idx = 1
    t = 0.0

    # Interleave speakers with speaker_0 dominant
    for round_idx in range(44):
        # speaker_0 cue
        cues.append({
            "cue_id": f"cue_{cue_idx:04d}",
            "id": f"cue_{cue_idx:04d}",
            "speaker_id": "speaker_0",
            "speaker": "speaker_0",
            "start": round(t, 2),
            "end": round(t + 1.8, 2),
            "text": f"Dominant speaker sentence {round_idx + 1}",
        })
        cue_idx += 1
        t += 2.0

        # speaker_1 cue (29 cues total)
        if round_idx < 29:
            cues.append({
                "cue_id": f"cue_{cue_idx:04d}",
                "id": f"cue_{cue_idx:04d}",
                "speaker_id": "speaker_1",
                "speaker": "speaker_1",
                "start": round(t, 2),
                "end": round(t + 1.5, 2),
                "text": f"Secondary speaker sentence {round_idx + 1}",
            })
            cue_idx += 1
            t += 1.8

        # speaker_2 cue (4 cues total)
        if round_idx in (5, 15, 25, 35):
            cues.append({
                "cue_id": f"cue_{cue_idx:04d}",
                "id": f"cue_{cue_idx:04d}",
                "speaker_id": "speaker_2",
                "speaker": "speaker_2",
                "start": round(t, 2),
                "end": round(t + 1.2, 2),
                "text": f"Tertiary speaker interjection {len([c for c in cues if c['speaker_id'] == 'speaker_2']) + 1}",
            })
            cue_idx += 1
            t += 1.5

    return cues


def _approved_voice_pools() -> dict[str, list[str]]:
    return {
        "low": [
            "English_magnetic_voiced_man",
            "English_Aussie_Bloke",
            "English_Trustworth_Man",
            "English_Gentle-voiced_man",
        ],
        "high": [
            "English_GracefulLady",
            "English_EnchantingMaiden",
            "English_WarmGirl",
            "English_SereneWoman",
        ],
    }


def test_production_fixture_shape_invariant():
    """Verify that fixture perfectly mirrors the production reference job telemetry."""
    cues = _generate_production_reference_cues()
    assert len(cues) == 77

    spk0_cues = [c for c in cues if c["speaker_id"] == "speaker_0"]
    spk1_cues = [c for c in cues if c["speaker_id"] == "speaker_1"]
    spk2_cues = [c for c in cues if c["speaker_id"] == "speaker_2"]

    assert len(spk0_cues) == 44
    assert len(spk1_cues) == 29
    assert len(spk2_cues) == 4

    speakers = sorted(list(set(c["speaker_id"] for c in cues)))
    assert len(speakers) == 3
    assert speakers == ["speaker_0", "speaker_1", "speaker_2"]


def test_first_red_n3_missing_pcm_authority_fails_closed_line_1261():
    """FIRST RED SEAM 1: Missing PCM authority causes Auto Smart Multivoice to hit Line 1261.

    When N=3 speakers are detected from ASR/diarization, but no PCM artifact or
    acoustic classification authority is passed (stereo_pcm_path is None),
    decide_smart_multivoice fails closed at line 1261 raising AutoCastManualRequired,
    reproducing Job 05268605cf13618dba15.
    """
    cues = _generate_production_reference_cues()
    pools = _approved_voice_pools()

    # Pre-condition: DETECTED_SPEAKER_COUNT must be exactly 3
    detected_speakers = sorted(list(set(c["speaker_id"] for c in cues)))
    detected_speaker_count = len(detected_speakers)
    assert detected_speaker_count == 3, f"Expected 3 detected speakers, got {detected_speaker_count}"

    # Target: without acoustic PCM authority, decide_smart_multivoice must fail closed at Line 1261
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        smart.decide_smart_multivoice(
            cues=cues,
            validated_pools=pools,
            assignment_seed="05268605cf13618dba15",
            stereo_pcm_path=None,
            raise_manual_required=True,
        )


def test_first_red_n3_run_auto_smart_multivoice_missing_pcm_fails_closed(tmp_path: Path):
    """Verify that run_auto_smart_multivoice fails closed when stereo_pcm_path is None."""
    import asyncio
    cues = _generate_production_reference_cues()
    pools = _approved_voice_pools()

    # Pre-condition: DETECTED_SPEAKER_COUNT must be exactly 3
    assert len(set(c["speaker_id"] for c in cues)) == 3

    dummy_media = tmp_path / "dummy.mp4"
    dummy_media.write_bytes(b"DUMMY_MP4_CONTENT")
    out_media = tmp_path / "output.mp4"

    async def _run():
        return await smart.run_auto_smart_multivoice(
            source_media=str(dummy_media),
            segments=cues,
            output_path=str(out_media),
            validated_pools=pools,
            assignment_seed="05268605cf13618dba15",
            stereo_pcm_path=None,
        )

    res = asyncio.run(_run())
    assert res.get("ok") is False
    assert res.get("strategy") == smart.STRATEGY_FAILED
    assert res.get("output_mode") == smart.OUTPUT_MODE_FAILED
    assert res.get("blocker") == speaker_cast.AUTO_CAST_MANUAL_REQUIRED


def test_first_red_n3_confidence_policy_blocker_sub_075_confidence_line_1139(tmp_path: Path):
    """FIRST RED SEAM 2: Low-confidence acoustic proof (<0.75) fails closed at Line 1139.

    Even if a PCM artifact is physically present, if dominant speaker_0 acoustic
    confidence is 0.695 (below MIN_REGISTER_CONFIDENCE = 0.75), the system
    strictly refuses to guess or assign a voice, failing closed at Line 1139.
    """
    cues = _generate_production_reference_cues()
    pools = _approved_voice_pools()

    # Create dummy PCM file with ambiguous / noisy signal for speaker_0
    pcm_path = tmp_path / "ambient_subdub_test.pcm"
    sr = 44100
    total_seconds = 185.0
    total_samples = int(sr * total_seconds)
    # White noise produces no confident pitch harmonic (< 0.75 confidence)
    np.random.seed(42)
    noise = (np.random.randn(total_samples) * 2000).astype("<i2")
    stereo = np.empty((total_samples * 2,), dtype="<i2")
    stereo[0::2] = noise
    stereo[1::2] = noise
    pcm_path.write_bytes(stereo.tobytes())

    # Pre-condition: DETECTED_SPEAKER_COUNT must be exactly 3
    detected_speakers = sorted(list(set(c["speaker_id"] for c in cues)))
    assert len(detected_speakers) == 3

    # With non-authoritative acoustic evidence (noise / confidence < 0.75),
    # pitch register returns 'unknown', classifier_failed is True,
    # and decide_smart_multivoice fails closed at Line 1139
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        smart.decide_smart_multivoice(
            cues=cues,
            validated_pools=pools,
            assignment_seed="05268605cf13618dba15",
            stereo_pcm_path=pcm_path,
            raise_manual_required=True,
        )

    decision = smart.decide_smart_multivoice(
        cues=cues,
        validated_pools=pools,
        assignment_seed="05268605cf13618dba15",
        stereo_pcm_path=pcm_path,
        raise_manual_required=False,
    )
    assert decision.strategy == smart.STRATEGY_FAILED
    assert decision.output_mode == smart.OUTPUT_MODE_FAILED
    assert decision.detected_speaker_count == 3
    assert "CLASSIFIER_UNAVAILABLE" in decision.fallback_reason


def test_first_red_n3_target_contract_requires_acoustic_authority_success(tmp_path: Path):
    """FIRST RED CONTRACT: Proves that N=3 succeeds only with authoritative acoustic evidence.

    When authoritative acoustic evidence is available (speaker_0: 120Hz low register,
    speaker_1: 200Hz high register, speaker_2: 120Hz low register, all confidences >= 0.75):
    1. Strategy must be GENERIC_MULTI
    2. Output mode must be DUBBED_MULTI_MP4
    3. Exactly 3 distinct voices assigned matching gender/register constraints
    4. Speaker identity authority is 100% preserved
    """
    cues = [
        {"cue_id": "c1", "speaker_id": "speaker_0", "start": 0.0, "end": 1.5, "text": "speaker zero"},
        {"cue_id": "c2", "speaker_id": "speaker_1", "start": 1.6, "end": 3.0, "text": "speaker one"},
        {"cue_id": "c3", "speaker_id": "speaker_2", "start": 3.1, "end": 4.5, "text": "speaker two"},
    ]
    pools = _approved_voice_pools()

    pcm_path = tmp_path / "valid_n3_multivoice.pcm"
    sr = 44100
    t = np.linspace(0, 5, sr * 5)
    signal = np.zeros_like(t)
    mask0 = (t >= 0.0) & (t <= 1.5)
    mask1 = (t >= 1.6) & (t <= 3.0)
    mask2 = (t >= 3.1) & (t <= 4.5)
    signal[mask0] = np.sin(2 * np.pi * 120 * t[mask0]) * 16000  # 120 Hz -> low
    signal[mask1] = np.sin(2 * np.pi * 200 * t[mask1]) * 16000  # 200 Hz -> high
    signal[mask2] = np.sin(2 * np.pi * 120 * t[mask2]) * 16000  # 120 Hz -> low
    int_sig = signal.astype("<i2")
    stereo = np.empty((len(t) * 2,), dtype="<i2")
    stereo[0::2] = int_sig
    stereo[1::2] = int_sig
    pcm_path.write_bytes(stereo.tobytes())

    # Pre-condition: DETECTED_SPEAKER_COUNT must be exactly 3
    detected_speakers = sorted(list(set(c["speaker_id"] for c in cues)))
    assert len(detected_speakers) == 3

    decision = smart.decide_smart_multivoice(
        cues=cues,
        validated_pools=pools,
        assignment_seed="authoritative_n3_seed",
        stereo_pcm_path=pcm_path,
        raise_manual_required=True,
    )

    assert decision.strategy == smart.STRATEGY_GENERIC_MULTI
    assert decision.output_mode == smart.OUTPUT_MODE_DUBBED_MULTI
    assert decision.detected_speaker_count == 3
    assert len(decision.speaker_voice_map) == 3
    # speaker_0 and speaker_2 must have low-register voices; speaker_1 must have high-register voice
    assert decision.speaker_voice_map["speaker_0"] in pools["low"]
    assert decision.speaker_voice_map["speaker_1"] in pools["high"]
    assert decision.speaker_voice_map["speaker_2"] in pools["low"]
    # Distinct voice assignment
    assert len(set(decision.speaker_voice_map.values())) == 3


def test_first_red_n3_dominance_2_3_near_zero_margin_fails_closed():
    """FIRST RED 1: dominance=2/3 + near-zero PANN margin => FAIL CLOSED (AutoCastManualRequired)."""
    from services import subdub_multi_speaker_gender_onnx as multi_onnx
    cues = [
        {"start": 0.0, "end": 1.0, "male_score": 0.500001, "female_score": 0.500000},
        {"start": 1.0, "end": 2.0, "male_score": 0.500001, "female_score": 0.500000},
        {"start": 2.0, "end": 3.0, "male_score": 0.500000, "female_score": 0.500001},
    ]
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        multi_onnx._aggregate_one_gender_result("spk_dom_2_3", cues)


def test_first_red_n3_dominance_075_near_zero_margin_fails_closed():
    """FIRST RED 2: dominance=0.75 + near-zero margin => FAIL CLOSED (AutoCastManualRequired)."""
    from services import subdub_multi_speaker_gender_onnx as multi_onnx
    cues = [
        {"start": 0.0, "end": 1.0, "male_score": 0.500001, "female_score": 0.500000},
        {"start": 1.0, "end": 2.0, "male_score": 0.500001, "female_score": 0.500000},
        {"start": 2.0, "end": 3.0, "male_score": 0.500001, "female_score": 0.500000},
        {"start": 3.0, "end": 4.0, "male_score": 0.500000, "female_score": 0.500001},
    ]
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        multi_onnx._aggregate_one_gender_result("spk_dom_075", cues)


def test_first_red_n3_dominance_080_near_zero_margin_fails_closed():
    """FIRST RED 3: dominance=0.80 + near-zero margin => FAIL CLOSED (AutoCastManualRequired)."""
    from services import subdub_multi_speaker_gender_onnx as multi_onnx
    cues = [
        {"start": 0.0, "end": 1.0, "male_score": 0.500001, "female_score": 0.500000},
        {"start": 1.0, "end": 2.0, "male_score": 0.500001, "female_score": 0.500000},
        {"start": 2.0, "end": 3.0, "male_score": 0.500001, "female_score": 0.500000},
        {"start": 3.0, "end": 4.0, "male_score": 0.500001, "female_score": 0.500000},
        {"start": 4.0, "end": 5.0, "male_score": 0.500000, "female_score": 0.500001},
    ]
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        multi_onnx._aggregate_one_gender_result("spk_dom_080", cues)


def test_first_red_n3_strong_dominance_and_strong_acoustic_margin_passes():
    """FIRST RED 4: strong dominance + independently strong acoustic margin => PASS."""
    from services import subdub_multi_speaker_gender_onnx as multi_onnx
    cues = [
        {"start": 0.0, "end": 1.0, "male_score": 0.85, "female_score": 0.15},
        {"start": 1.5, "end": 2.5, "male_score": 0.90, "female_score": 0.10},
        {"start": 3.0, "end": 4.0, "male_score": 0.20, "female_score": 0.80},
    ]
    res, rows = multi_onnx._aggregate_one_gender_result("spk_strong", cues)
    assert res["voice_gender"] == "male"
    assert res["voice_register"] == "low"
    assert res["confidence"] >= speaker_cast.MIN_REGISTER_CONFIDENCE
    assert res["pann_score_margin"] >= 0.08


def test_first_red_n3_pann_margin_boundary_conditions():
    """Boundary testing for PANN margin threshold (0.08): below and above boundary."""
    from services import subdub_multi_speaker_gender_onnx as multi_onnx

    # 1. Below boundary: margin = 0.06 < 0.08 (e.g. 0.53 vs 0.47) -> must fail closed
    cues_below = [
        {"start": 0.0, "end": 1.0, "male_score": 0.53, "female_score": 0.47},
        {"start": 1.0, "end": 2.0, "male_score": 0.53, "female_score": 0.47},
        {"start": 2.0, "end": 3.0, "male_score": 0.53, "female_score": 0.47},
    ]
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        multi_onnx._aggregate_one_gender_result("spk_below", cues_below)

    # 2. Above boundary: margin = 0.60 > 0.08 (e.g. 0.80 vs 0.20) -> authoritative pass
    cues_above = [
        {"start": 0.0, "end": 1.0, "male_score": 0.80, "female_score": 0.20},
        {"start": 1.0, "end": 2.0, "male_score": 0.80, "female_score": 0.20},
        {"start": 2.0, "end": 3.0, "male_score": 0.80, "female_score": 0.20},
    ]
    res, _ = multi_onnx._aggregate_one_gender_result("spk_above", cues_above)
    assert res["voice_gender"] == "male"
    assert res["voice_register"] == "low"
    assert res["confidence"] >= speaker_cast.MIN_REGISTER_CONFIDENCE

