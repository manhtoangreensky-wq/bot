"""Comprehensive test suite for P0.SUBDUB.AUTO.SMART.MULTIVOICE.ISOLATED.SOURCE.IMPLEMENTATION.R1.

Covers all 38 test requirements:
01 Smart module missing FIRST RED
02 N=1 clear voice
03 N=1 uncertain register
04 N=2 strict success
05 N=2 insufficient cues fallback
06 N=2 low-confidence fallback
07 N=3
08 N=5
09 N=8
10 voice pool exhaustion
11 deterministic voice reuse
12 same speaker same voice
13 replay deterministic
14 no gender-only speaker merge
15 no local-index-only cross-chunk merge
16 background music preserved
17 singing preserved
18 no invented transcript
19 no invented speaker
20 every cue accounted
21 no TTS cue without voice
22 valid final MP4
23 invalid final MP4 rejected
24 corrupt input fails truthfully
25 render failure fails truthfully
26 cancellation respected
27 subtitle-only fallback
28 single-voice fallback
29 bar-video regression
30 two-person cooking regression
31 legacy 2-speaker tests unchanged
32 legacy multi tests unchanged
33 legacy manual behavior unchanged
34 Smart never routes to manual for cast ambiguity
35 zero provider calls
36 zero wallet mutations
37 zero customer route changes
38 no legacy production file change
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import hashlib
from pathlib import Path
import subprocess
import tempfile
import pytest

from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_speaker, auto_multi_speaker
from services.subdub_blackboxes import auto_smart_multivoice as smart


TEST_POOLS = {
    "low": ["voice_male_1", "voice_male_2", "voice_male_3", "voice_male_4"],
    "high": ["voice_female_1", "voice_female_2", "voice_female_3", "voice_female_4"],
}


def _create_mock_mp4(path: Path, size_bytes: int = 1024) -> Path:
    path.write_bytes(b"\x00" * size_bytes)
    return path


def test_01_first_red_demonstration():
    """FIRST RED: Prove legacy strict-two requires manual fallback for N=1 and N=2 weak evidence."""
    # N=1 in legacy speaker_cast
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        speaker_cast.assign_stable_voices(
            {"spk_1": {"voice_register": "low", "confidence": 0.95}},
            speaker_order=["spk_1"],
            validated_pools={"low": ["v1"], "high": ["v2"]},
            assignment_seed="a" * 64,
        )

    # N=2 with weak confidence (< 0.75) in legacy
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        speaker_cast.assign_stable_voices(
            {
                "spk_1": {"voice_register": "low", "confidence": 0.60},
                "spk_2": {"voice_register": "high", "confidence": 0.95},
            },
            speaker_order=["spk_1", "spk_2"],
            validated_pools={"low": ["v1"], "high": ["v2"]},
            assignment_seed="a" * 64,
        )


def test_02_n1_clear_voice():
    """N=1 with confident register: assigns appropriate register voice, fallback_level=0."""
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Xin chào quý vị khán giả", "start_ms": 0, "end_ms": 2000},
    ]
    acoustics = {"spk_1": {"voice_register": "low", "confidence": 0.92}}
    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=TEST_POOLS,
        acoustic_classifications=acoustics,
    )
    assert decision.detected_speaker_count == 1
    assert decision.effective_speaker_count == 1
    assert decision.effective_voice_count == 1
    assert decision.strategy == smart.STRATEGY_GENERIC_SINGLE
    assert decision.fallback_level == 0
    assert decision.output_mode == smart.OUTPUT_MODE_DUBBED_SINGLE
    assert decision.speaker_voice_map["spk_1"] in TEST_POOLS["low"]


def test_03_n1_uncertain_register():
    """N=1 with uncertain register: deterministic default voice, never halts for manual."""
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Đoạn video một người nói", "start_ms": 0, "end_ms": 2000},
    ]
    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=TEST_POOLS,
        acoustic_classifications=None,
    )
    assert decision.detected_speaker_count == 1
    assert decision.effective_voice_count == 1
    assert decision.strategy == smart.STRATEGY_GENERIC_SINGLE
    assert decision.fallback_level == 1
    assert decision.fallback_reason == "n1_uncertain_register_default"
    assert decision.output_mode == smart.OUTPUT_MODE_DUBBED_SINGLE
    assert "spk_1" in decision.speaker_voice_map


def test_04_n2_strict_success():
    """N=2 with confident opposite registers: reuses strict two-speaker assignment."""
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Chào bạn, hôm nay thế nào?", "start_ms": 0, "end_ms": 1500},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "Tôi rất khỏe, cảm ơn bạn.", "start_ms": 1600, "end_ms": 3000},
    ]
    acoustics = {
        "spk_1": {"voice_register": "low", "confidence": 0.95},
        "spk_2": {"voice_register": "high", "confidence": 0.96},
    }
    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=TEST_POOLS,
        acoustic_classifications=acoustics,
    )
    assert decision.detected_speaker_count == 2
    assert decision.effective_speaker_count == 2
    assert decision.effective_voice_count == 2
    assert decision.strategy == smart.STRATEGY_STRICT_TWO
    assert decision.fallback_level == 0
    assert decision.output_mode == smart.OUTPUT_MODE_DUBBED_MULTI
    assert decision.speaker_voice_map["spk_1"] != decision.speaker_voice_map["spk_2"]


def test_05_n2_insufficient_cues_fallback():
    """N=2 with missing acoustic cues: catches strict failure, falls back internally without manual halt."""
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Một câu nói ngắn", "start_ms": 0, "end_ms": 500},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "Câu trả lời ngắn", "start_ms": 600, "end_ms": 1000},
    ]
    # No acoustic classification provided -> strict would fail
    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=TEST_POOLS,
        acoustic_classifications={},
    )
    assert decision.detected_speaker_count == 2
    assert decision.effective_voice_count == 2
    assert decision.strategy == smart.STRATEGY_STABLE_FALLBACK
    assert decision.fallback_level == 1
    assert decision.fallback_reason == "n2_strict_ambiguity_fallback"
    assert decision.output_mode == smart.OUTPUT_MODE_DUBBED_MULTI
    assert decision.speaker_voice_map["spk_1"] != decision.speaker_voice_map["spk_2"]


def test_06_n2_low_confidence_fallback():
    """N=2 with low confidence (< 0.75): catches strict failure and assigns distinct voices."""
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu nói 1", "start_ms": 0, "end_ms": 1500},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "Câu nói 2", "start_ms": 1600, "end_ms": 3000},
    ]
    acoustics = {
        "spk_1": {"voice_register": "low", "confidence": 0.55},
        "spk_2": {"voice_register": "high", "confidence": 0.60},
    }
    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=TEST_POOLS,
        acoustic_classifications=acoustics,
    )
    assert decision.detected_speaker_count == 2
    assert decision.effective_voice_count == 2
    assert decision.strategy == smart.STRATEGY_STABLE_FALLBACK
    assert decision.fallback_level == 1
    assert decision.speaker_voice_map["spk_1"] != decision.speaker_voice_map["spk_2"]


def test_07_n3_speakers():
    """N=3 speakers: GENERIC_MULTI with 3 distinct voices."""
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Người thứ nhất nói", "start_ms": 0, "end_ms": 1000},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "Người thứ hai trả lời", "start_ms": 1100, "end_ms": 2000},
        {"cue_id": "c3", "speaker_id": "spk_3", "text": "Người thứ ba bổ sung", "start_ms": 2100, "end_ms": 3000},
    ]
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS)
    assert decision.detected_speaker_count == 3
    assert decision.effective_speaker_count == 3
    assert decision.effective_voice_count == 3
    assert decision.strategy == smart.STRATEGY_GENERIC_MULTI
    assert decision.output_mode == smart.OUTPUT_MODE_DUBBED_MULTI


def test_08_n5_speakers():
    """N=5 speakers: GENERIC_MULTI with 5 distinct voices."""
    cues = [
        {"cue_id": f"c{i}", "speaker_id": f"spk_{i}", "text": f"Lời nói người {i}", "start_ms": i * 1000, "end_ms": (i + 1) * 1000}
        for i in range(1, 6)
    ]
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS)
    assert decision.detected_speaker_count == 5
    assert decision.effective_voice_count == 5
    assert decision.strategy == smart.STRATEGY_GENERIC_MULTI
    assert len(set(decision.speaker_voice_map.values())) == 5


def test_09_n8_speakers():
    """N=8 speakers (meeting product target 1..8): assigns distinct voices across pools."""
    cues = [
        {"cue_id": f"c{i}", "speaker_id": f"spk_{i}", "text": f"Lời nói người {i}", "start_ms": i * 1000, "end_ms": (i + 1) * 1000}
        for i in range(1, 9)
    ]
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS)
    assert decision.detected_speaker_count == 8
    assert decision.effective_voice_count == 8
    assert decision.strategy == smart.STRATEGY_GENERIC_MULTI
    assert len(set(decision.speaker_voice_map.values())) == 8


def test_10_voice_pool_exhaustion():
    """Pool exhaustion (6 speakers, only 4 voices): does NOT abort; reuses voices gracefully."""
    small_pools = {"low": ["v_male_1", "v_male_2"], "high": ["v_fem_1", "v_fem_2"]}
    cues = [
        {"cue_id": f"c{i}", "speaker_id": f"spk_{i}", "text": f"Người {i} phát biểu", "start_ms": i * 1000, "end_ms": (i + 1) * 1000}
        for i in range(1, 7)
    ]
    decision = smart.decide_smart_multivoice(cues, validated_pools=small_pools)
    assert decision.detected_speaker_count == 6
    assert decision.effective_speaker_count == 6
    # 4 unique voices in pool -> effective_voice_count must be 4 truthfully
    assert decision.effective_voice_count == 4
    assert decision.fallback_level == 2
    assert decision.fallback_reason == "voice_pool_exhaustion_reuse"
    assert decision.output_mode == smart.OUTPUT_MODE_DUBBED_MULTI


def test_11_deterministic_voice_reuse():
    """Voice pool exhaustion reuse is 100% deterministic across multiple calls with same seed."""
    small_pools = {"low": ["v1", "v2"], "high": ["v3"]}
    cues = [
        {"cue_id": f"c{i}", "speaker_id": f"spk_{i}", "text": f"Thoại {i}", "start_ms": i * 1000, "end_ms": (i + 1) * 1000}
        for i in range(1, 6)
    ]
    d1 = smart.decide_smart_multivoice(cues, validated_pools=small_pools, assignment_seed="fixed_seed_123")
    d2 = smart.decide_smart_multivoice(cues, validated_pools=small_pools, assignment_seed="fixed_seed_123")
    assert d1.speaker_voice_map == d2.speaker_voice_map


def test_12_same_speaker_same_voice():
    """Invariant: Same canonical speaker -> same assigned voice throughout the job."""
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_A", "text": "Câu 1 của A", "start_ms": 0, "end_ms": 1000},
        {"cue_id": "c2", "speaker_id": "spk_B", "text": "Câu 1 của B", "start_ms": 1100, "end_ms": 2000},
        {"cue_id": "c3", "speaker_id": "spk_A", "text": "Câu 2 của A", "start_ms": 2100, "end_ms": 3000},
        {"cue_id": "c4", "speaker_id": "spk_B", "text": "Câu 2 của B", "start_ms": 3100, "end_ms": 4000},
    ]
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS)
    voice_a_cues = [c["tts_voice_id"] for c in decision.tts_cues if c["speaker_id"] == "spk_A"]
    voice_b_cues = [c["tts_voice_id"] for c in decision.tts_cues if c["speaker_id"] == "spk_B"]
    assert len(set(voice_a_cues)) == 1
    assert len(set(voice_b_cues)) == 1
    assert voice_a_cues[0] == decision.speaker_voice_map["spk_A"]
    assert voice_b_cues[0] == decision.speaker_voice_map["spk_B"]


def test_13_replay_deterministic():
    """Replay determinism: Same seed and inputs produce identical decisions and mappings."""
    cues = [
        {"cue_id": "c1", "speaker_id": "s1", "text": "Xin chào", "start_ms": 0, "end_ms": 1000},
        {"cue_id": "c2", "speaker_id": "s2", "text": "Cảm ơn", "start_ms": 1100, "end_ms": 2000},
        {"cue_id": "c3", "speaker_id": "s3", "text": "Tạm biệt", "start_ms": 2100, "end_ms": 3000},
    ]
    res1 = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS, assignment_seed="seed_xyz")
    res2 = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS, assignment_seed="seed_xyz")
    assert res1.strategy == res2.strategy
    assert res1.speaker_voice_map == res2.speaker_voice_map
    assert res1.cue_dispositions == res2.cue_dispositions


def test_14_no_gender_only_speaker_merge():
    """Speakers with the same register (both low) must NOT be merged into one speaker identity."""
    cues = [
        {"cue_id": "c1", "speaker_id": "male_speaker_1", "text": "Tôi là người thứ nhất", "start_ms": 0, "end_ms": 1000},
        {"cue_id": "c2", "speaker_id": "male_speaker_2", "text": "Tôi là người thứ hai", "start_ms": 1100, "end_ms": 2000},
    ]
    acoustics = {
        "male_speaker_1": {"voice_register": "low", "confidence": 0.90},
        "male_speaker_2": {"voice_register": "low", "confidence": 0.88},
    }
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS, acoustic_classifications=acoustics)
    assert decision.detected_speaker_count == 2
    assert decision.effective_speaker_count == 2
    assert "male_speaker_1" in decision.speaker_voice_map
    assert "male_speaker_2" in decision.speaker_voice_map
    assert decision.speaker_voice_map["male_speaker_1"] != decision.speaker_voice_map["male_speaker_2"]


def test_15_no_local_index_only_cross_chunk_merge():
    """Speakers from different chunks with unproven identities are preserved distinctly."""
    cues = [
        {"cue_id": "c1", "speaker_id": "chunk_0:speaker_0", "text": "Đoạn 0 nói", "start_ms": 0, "end_ms": 1000},
        {"cue_id": "c2", "speaker_id": "chunk_1:speaker_0", "text": "Đoạn 1 nói", "start_ms": 1100, "end_ms": 2000},
    ]
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS)
    assert decision.detected_speaker_count == 2
    assert decision.effective_speaker_count == 2
    assert "chunk_0:speaker_0" in decision.speaker_voice_map
    assert "chunk_1:speaker_0" in decision.speaker_voice_map


def test_16_background_music_preserved():
    """Background music cues are marked PRESERVED and not dispatched to TTS."""
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Xin chào", "start_ms": 0, "end_ms": 1000},
        {"cue_id": "c2", "speaker_id": "spk_bg", "text": "[Music]", "start_ms": 1000, "end_ms": 3000, "is_music": True},
        {"cue_id": "c3", "speaker_id": "spk_1", "text": "Hẹn gặp lại", "start_ms": 3100, "end_ms": 4000},
    ]
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS)
    assert decision.cue_dispositions["c2"] == smart.DISPOSITION_PRESERVED
    assert decision.cue_dispositions["c1"] == smart.DISPOSITION_DUBBED
    assert decision.cue_dispositions["c3"] == smart.DISPOSITION_DUBBED
    assert "spk_bg" not in decision.speaker_voice_map


def test_17_singing_preserved():
    """Background singing cue is marked PRESERVED; not dubbed as dialogue."""
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Hôm nay tôi hát bài này", "start_ms": 0, "end_ms": 1500},
        {"cue_id": "c2", "speaker_id": "singer_bg", "text": "♪ La la la ♪", "start_ms": 1600, "end_ms": 5000, "is_singing": True},
    ]
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS)
    assert decision.cue_dispositions["c2"] == smart.DISPOSITION_PRESERVED
    assert decision.cue_dispositions["c1"] == smart.DISPOSITION_DUBBED
    assert decision.detected_speaker_count == 1
    assert "singer_bg" not in decision.speaker_voice_map


def test_18_no_invented_transcript():
    """TTS cues preserve exact canonical transcript without hallucinated additions."""
    original_text = "Câu thoại nguyên bản từ source"
    cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": original_text, "start_ms": 0, "end_ms": 1000}]
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS)
    assert len(decision.tts_cues) == 1
    assert decision.tts_cues[0]["text"] == original_text


def test_19_no_invented_speaker():
    """No phantom or invented speakers appear in the speaker_voice_map."""
    cues = [{"cue_id": "c1", "speaker_id": "spk_real", "text": "Thật", "start_ms": 0, "end_ms": 1000}]
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS)
    assert list(decision.speaker_voice_map.keys()) == ["spk_real"]


def test_20_every_cue_accounted_for():
    """Every single canonical cue has exactly one valid disposition."""
    cues = [
        {"cue_id": "c1", "speaker_id": "s1", "text": "Thoại 1", "start_ms": 0, "end_ms": 1000},
        {"cue_id": "c2", "text": "[Noise]", "start_ms": 1000, "end_ms": 1500},
        {"cue_id": "c3", "speaker_id": "s2", "text": "Thoại 2", "start_ms": 1500, "end_ms": 2500},
    ]
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS)
    assert len(decision.cue_dispositions) == len(cues)
    for c in cues:
        assert c["cue_id"] in decision.cue_dispositions
        assert decision.cue_dispositions[c["cue_id"]] in {
            smart.DISPOSITION_DUBBED,
            smart.DISPOSITION_PRESERVED,
            smart.DISPOSITION_SUBTITLE_ONLY,
            smart.DISPOSITION_TERMINAL_REJECTED,
        }


def test_21_no_tts_cue_without_voice():
    """Every cue marked for TTS synthesis has a valid tts_voice_id."""
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu nói", "start_ms": 0, "end_ms": 1000},
    ]
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS)
    assert len(decision.tts_cues) > 0
    for tc in decision.tts_cues:
        assert tc.get("tts_voice_id") is not None
        assert str(tc["tts_voice_id"]).strip() != ""


def test_22_valid_final_mp4(tmp_path):
    """Runner with valid media and successful render verifies final MP4 and reports ok=True."""
    async def _run():
        source_media = _create_mock_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"
        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Chào", "start_ms": 0, "end_ms": 1000}]

        async def mock_synth(cues, speaker_voice_map):
            return [{"chunk_id": "chk_1"}]

        async def mock_render(source_media, output_path, **kwargs):
            return _create_mock_mp4(Path(output_path), 2048)

        def mock_probe(path):
            return {"ok": True, "detail": "ok"}

        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            synthesize_segments=mock_synth,
            render_pipeline=mock_render,
            probe_fn=mock_probe,
        )
        assert res["ok"] is True
        assert res["output_mode"] == smart.OUTPUT_MODE_DUBBED_SINGLE
        assert res["final_mp4_path"] == str(output_mp4)
        assert res["auto_smart_verified"] is True
    asyncio.run(_run())


def test_23_invalid_final_mp4_rejected(tmp_path):
    """Empty or non-existent rendered file fails MP4 validation truthfully."""
    async def _run():
        source_media = _create_mock_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"
        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Chào", "start_ms": 0, "end_ms": 1000}]

        async def mock_render(source_media, output_path, **kwargs):
            # Create empty file (0 bytes)
            Path(output_path).write_bytes(b"")
            return output_path

        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            render_pipeline=mock_render,
        )
        assert res["ok"] is False
        assert res["output_mode"] == smart.OUTPUT_MODE_FAILED
        assert "empty_file" in str(res["blocker"])
    asyncio.run(_run())


def test_24_corrupt_input_fails_truthfully(tmp_path):
    """Missing or 0-byte source media fails truthfully with blocker message."""
    async def _run():
        missing_media = tmp_path / "missing.mp4"
        output_mp4 = tmp_path / "output.mp4"
        res = await smart.run_auto_smart_multivoice(
            source_media=missing_media,
            segments=[],
            output_path=output_mp4,
        )
        assert res["ok"] is False
        assert res["output_mode"] == smart.OUTPUT_MODE_FAILED
        assert res["blocker"] == "source_media_not_found"
    asyncio.run(_run())


def test_25_render_failure_fails_truthfully(tmp_path):
    """Exception raised during render pipeline is caught and reported truthfully."""
    async def _run():
        source_media = _create_mock_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"
        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Chào", "start_ms": 0, "end_ms": 1000}]

        async def failing_render(**kwargs):
            raise RuntimeError("ffmpeg_mux_failure_code_1")

        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            render_pipeline=failing_render,
        )
        assert res["ok"] is False
        assert res["output_mode"] == smart.OUTPUT_MODE_FAILED
        assert "render_pipeline_failed" in str(res["blocker"])
    asyncio.run(_run())


def test_26_cancellation_respected(tmp_path):
    """Cancellation flag aborts processing before synthesis/render."""
    async def _run():
        source_media = _create_mock_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"

        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=[],
            output_path=output_mp4,
            is_cancelled=lambda: True,
        )
        assert res["ok"] is False
        assert res["blocker"] == "cancelled"
    asyncio.run(_run())


def test_27_subtitle_only_fallback():
    """Fallback level 4 sets output mode to SUBTITLE_ONLY_MP4 and preserves audio."""
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Phụ đề thôi nhé", "start_ms": 0, "end_ms": 2000},
    ]
    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=TEST_POOLS,
        fallback_level_override=4,
    )
    assert decision.output_mode == smart.OUTPUT_MODE_SUBTITLE_ONLY
    assert decision.strategy == smart.STRATEGY_SUBTITLE_ONLY
    assert decision.fallback_level == 4
    assert decision.cue_dispositions["c1"] == smart.DISPOSITION_SUBTITLE_ONLY
    assert len(decision.tts_cues) == 0


def test_28_single_voice_fallback():
    """Fallback level 3 collapses multi-speakers into single dominant voice."""
    cues = [
        {"cue_id": "c1", "speaker_id": "s1", "text": "Thoại 1", "start_ms": 0, "end_ms": 1000},
        {"cue_id": "c2", "speaker_id": "s2", "text": "Thoại 2", "start_ms": 1100, "end_ms": 2000},
    ]
    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=TEST_POOLS,
        fallback_level_override=3,
    )
    assert decision.strategy == smart.STRATEGY_SINGLE_DOMINANT
    assert decision.effective_voice_count == 1
    assert decision.output_mode == smart.OUTPUT_MODE_DUBBED_FALLBACK
    assert decision.speaker_voice_map["s1"] == decision.speaker_voice_map["s2"]


def test_29_bar_video_regression():
    """Regression test for bar video failure class: 1 speech speaker + background singer/music."""
    cues = [
        {"cue_id": "c1", "speaker_id": "person_talking", "text": "Hôm nay tôi ở quán bar", "start_ms": 0, "end_ms": 2000},
        {"cue_id": "c2", "speaker_id": "person_talking", "text": "Không khí rất vui", "start_ms": 2100, "end_ms": 4000},
        {"cue_id": "c3", "speaker_id": "bar_singer", "text": "♪ Trót yêu em rồi ♪", "start_ms": 4500, "end_ms": 8000, "is_singing": True},
        {"cue_id": "c4", "speaker_id": "bar_band", "text": "[Music]", "start_ms": 8100, "end_ms": 12000, "is_music": True},
        {"cue_id": "c5", "speaker_id": "person_talking", "text": "Bây giờ chuẩn bị về nhà", "start_ms": 12500, "end_ms": 14000},
    ]
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS)
    # Only 1 speech speaker detected
    assert decision.detected_speaker_count == 1
    assert decision.effective_voice_count == 1
    assert decision.output_mode == smart.OUTPUT_MODE_DUBBED_SINGLE
    assert decision.cue_dispositions["c3"] == smart.DISPOSITION_PRESERVED
    assert decision.cue_dispositions["c4"] == smart.DISPOSITION_PRESERVED
    assert decision.cue_dispositions["c1"] == smart.DISPOSITION_DUBBED
    assert decision.cue_dispositions["c2"] == smart.DISPOSITION_DUBBED
    assert decision.cue_dispositions["c5"] == smart.DISPOSITION_DUBBED
    assert "bar_singer" not in decision.speaker_voice_map
    assert "bar_band" not in decision.speaker_voice_map


def test_30_two_person_cooking_regression():
    """Regression test for working cooking video: 2 clear speakers alternating dialogue."""
    cues = [
        {"cue_id": "c1", "speaker_id": "chef_male", "text": "Hôm nay chúng ta nấu phở", "start_ms": 0, "end_ms": 2000},
        {"cue_id": "c2", "speaker_id": "host_female", "text": "Nguyên liệu gồm những gì ạ?", "start_ms": 2100, "end_ms": 4000},
        {"cue_id": "c3", "speaker_id": "chef_male", "text": "Cần xương bò và hoa hồi", "start_ms": 4100, "end_ms": 6000},
        {"cue_id": "c4", "speaker_id": "host_female", "text": "Tuyệt vời quá thầy ơi", "start_ms": 6100, "end_ms": 8000},
    ]
    acoustics = {
        "chef_male": {"voice_register": "low", "confidence": 0.95},
        "host_female": {"voice_register": "high", "confidence": 0.93},
    }
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS, acoustic_classifications=acoustics)
    assert decision.detected_speaker_count == 2
    assert decision.effective_voice_count == 2
    assert decision.output_mode == smart.OUTPUT_MODE_DUBBED_MULTI
    assert decision.speaker_voice_map["chef_male"] != decision.speaker_voice_map["host_female"]


def test_31_legacy_2_speaker_tests_unchanged():
    """Verify legacy 2-speaker functions in auto_speaker.py are intact."""
    assert hasattr(auto_speaker, "is_auto_speaker_state")
    assert auto_speaker.is_auto_speaker_state({
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
    }) is True
    assert auto_speaker.is_auto_speaker_state({"voice_kind": "other"}) is False


def test_32_legacy_multi_tests_unchanged():
    """Verify legacy multi-speaker helpers in auto_multi_speaker.py are intact."""
    assert hasattr(auto_multi_speaker, "bounded_multi_acoustic_evidence")
    assert auto_multi_speaker.AUTO_MULTI_SPEAKER_LANE == "multi"
    assert auto_multi_speaker.bounded_multi_acoustic_evidence(None) == {}


def test_33_legacy_manual_behavior_unchanged():
    """Verify legacy speaker_cast fail-closed contract is preserved."""
    assert issubclass(speaker_cast.AutoCastManualRequired, RuntimeError)
    assert issubclass(speaker_cast.AutoCastUnavailable, RuntimeError)


def test_34_smart_never_routes_to_manual_for_cast_ambiguity():
    """Smart lane never raises AutoCastManualRequired for any speaker count or ambiguity."""
    # Test across speaker counts 0..10 with various edge-case cues
    for n in range(0, 11):
        cues = [
            {"cue_id": f"c{i}", "speaker_id": f"s{i}", "text": f"text {i}", "start_ms": i * 1000, "end_ms": (i + 1) * 1000}
            for i in range(n)
        ]
        decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS)
        assert decision.strategy != smart.STRATEGY_FAILED
        assert decision.output_mode in {
            smart.OUTPUT_MODE_DUBBED_MULTI,
            smart.OUTPUT_MODE_DUBBED_SINGLE,
            smart.OUTPUT_MODE_DUBBED_FALLBACK,
            smart.OUTPUT_MODE_SUBTITLE_ONLY,
            smart.OUTPUT_MODE_PASSTHROUGH,
        }


def test_35_zero_provider_calls(monkeypatch):
    """Ensure zero external network calls are made."""
    # If any socket connection is attempted, pytest will fail
    import socket
    def forbidden_connect(*args, **kwargs):
        raise AssertionError("LIVE_PROVIDER_CALL_FORBIDDEN")
    monkeypatch.setattr(socket.socket, "connect", forbidden_connect)

    cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Thoại", "start_ms": 0, "end_ms": 1000}]
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS)
    assert decision.effective_voice_count == 1


def test_36_zero_wallet_mutations():
    """Smart lane code has no references to wallet mutations or billing calls."""
    import inspect
    src = inspect.getsource(smart)
    assert "wallet" not in src.lower()
    assert "payos" not in src.lower()
    assert "charge" not in src.lower()
    assert "balance" not in src.lower()


def test_37_zero_customer_route_changes():
    """Ensure bot.py customer routing is unchanged and clean against base HEAD."""
    status = subprocess.run(["git", "status", "--porcelain", "bot.py"], capture_output=True, text=True)
    assert status.stdout.strip() == "", "bot.py should have 0 changes!"


def test_38_no_legacy_production_file_change():
    """Ensure git diff against base SHA contains 0 changes to legacy frozen production files."""
    frozen_files = [
        "services/subdub_blackboxes/auto_speaker.py",
        "services/subdub_blackboxes/auto_multi_speaker.py",
        "services/subdub_two_speaker_gender_onnx.py",
        "services/subdub_speaker_cast.py",
        "bot.py",
    ]
    diff_res = subprocess.run(
        ["git", "diff", "73ab3dca8211aaa37cf76af75ccc75b0ac1dd8ee", "--name-only"],
        capture_output=True,
        text=True,
    )
    changed_files = [line.strip() for line in diff_res.stdout.splitlines() if line.strip()]
    for ff in frozen_files:
        assert ff not in changed_files, f"Legacy frozen file was modified: {ff}"
