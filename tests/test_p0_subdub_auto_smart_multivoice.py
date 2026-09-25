"""Comprehensive test suite for P0.SUBDUB.AUTO.SMART.MULTIVOICE.ISOLATED.SOURCE.IMPLEMENTATION.R1.C1.

Covers all 58 test requirements:
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
39 STRICT_TWO cannot be emitted without strict engine success
40 strict engine spy is actually called
41 strict AutoCastManualRequired falls back without manual halt
42 missing speaker ID does not invent speaker_0
43 missing canonical cue identity does not invent current canonical ID
44 validated_pools=None does not invent provider voices
45 malformed/unapproved pool rejected/falls lower truthfully
46 DUBBED mode without synth authority cannot succeed
47 partial TTS coverage cannot succeed as DUBBED
48 duplicate TTS artifact rejected
49 unknown TTS artifact rejected
50 non-empty garbage MP4 rejected without caller probe
51 stale pre-existing output rejected
52 render_pipeline absent cannot claim current-run output
53 bar fixture full runner -> valid MP4
54 bar singing/music never sent to TTS
55 preserved bar cues reach renderer
56 cooking fixture full runner -> valid MP4
57 cancellation after synthesis cannot succeed
58 cancellation before render cannot succeed
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import pytest

from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_speaker, auto_multi_speaker
from services.subdub_blackboxes import auto_smart_multivoice as smart


TEST_POOLS = {
    "low": ["voice_male_1", "voice_male_2", "voice_male_3", "voice_male_4"],
    "high": ["voice_female_1", "voice_female_2", "voice_female_3", "voice_female_4"],
}


def _resolve_test_ffmpeg() -> str:
    """Deterministically resolve ffmpeg executable across Windows and Linux environments."""
    candidates = [
        shutil.which("ffmpeg"),
        shutil.which("ffmpeg.exe"),
        str(Path(sys.executable).with_name("ffmpeg")),
        str(Path(sys.executable).with_name("ffmpeg.exe")),
    ]
    for cand in candidates:
        if cand and Path(cand).is_file():
            return cand
    raise RuntimeError("ffmpeg executable unavailable for SubDub MP4 fixture")


def _create_real_valid_mp4(target_path: Path) -> Path:
    """Generate deterministic 1-second valid MP4 via local ffmpeg."""
    ffmpeg_bin = _resolve_test_ffmpeg()
    cmd = [
        ffmpeg_bin,
        "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "1",
        "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p",
        "-y", str(target_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return target_path


def _create_mock_file(path: Path, size_bytes: int = 1024) -> Path:
    path.write_bytes(b"\x00" * size_bytes)
    return path


def test_01_first_red_demonstration():
    """FIRST RED: Prove legacy strict-two requires manual fallback for N=1 and N=2 weak evidence."""
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        speaker_cast.assign_stable_voices(
            {"spk_1": {"voice_register": "low", "confidence": 0.95}},
            speaker_order=["spk_1"],
            validated_pools={"low": ["v1"], "high": ["v2"]},
            assignment_seed="a" * 64,
        )

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
    """N=2 with strict engine success: STRICT_TWO emitted when real strict engine succeeds."""
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Chào bạn, hôm nay thế nào?", "start_ms": 0, "end_ms": 1500},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "Tôi rất khỏe, cảm ơn bạn.", "start_ms": 1600, "end_ms": 3000},
    ]
    calls = []
    def strict_spy(pcm_path, ranges, **kwargs):
        calls.append((pcm_path, ranges))
        return {
            "spk_1": {"voice_register": "low", "confidence": 0.95},
            "spk_2": {"voice_register": "high", "confidence": 0.96},
        }

    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=TEST_POOLS,
        strict_two_classifier=strict_spy,
    )
    assert len(calls) == 1
    assert decision.detected_speaker_count == 2
    assert decision.effective_speaker_count == 2
    assert decision.effective_voice_count == 2
    assert decision.strategy == smart.STRATEGY_STRICT_TWO
    assert decision.fallback_level == 0
    assert decision.output_mode == smart.OUTPUT_MODE_DUBBED_MULTI
    assert decision.speaker_voice_map["spk_1"] != decision.speaker_voice_map["spk_2"]


def test_05_n2_insufficient_cues_fallback():
    """N=2 where strict classifier fails: catches strict failure, falls back internally without manual halt."""
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Một câu nói ngắn", "start_ms": 0, "end_ms": 500},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "Câu trả lời ngắn", "start_ms": 600, "end_ms": 1000},
    ]
    def failing_strict(*args, **kwargs):
        raise speaker_cast.AutoCastManualRequired()

    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=TEST_POOLS,
        strict_two_classifier=failing_strict,
    )
    assert decision.detected_speaker_count == 2
    assert decision.effective_voice_count == 2
    assert decision.strategy == smart.STRATEGY_STABLE_FALLBACK
    assert decision.fallback_level == 1
    assert decision.fallback_reason == "n2_strict_ambiguity_fallback"
    assert decision.output_mode == smart.OUTPUT_MODE_DUBBED_MULTI
    assert decision.speaker_voice_map["spk_1"] != decision.speaker_voice_map["spk_2"]


def test_06_n2_low_confidence_fallback():
    """N=2 with low confidence (< 0.75): strict engine fails, Smart falls back internally."""
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu nói 1", "start_ms": 0, "end_ms": 1500},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "Câu nói 2", "start_ms": 1600, "end_ms": 3000},
    ]
    def low_conf_strict(*args, **kwargs):
        raise speaker_cast.AutoCastManualRequired()

    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=TEST_POOLS,
        strict_two_classifier=low_conf_strict,
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
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS)
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
        source_media = _create_real_valid_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"
        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Chào", "start_ms": 0, "end_ms": 1000}]

        async def mock_synth(cues, speaker_voice_map):
            return [{"cue_id": "c1", "audio": b"dummy_pcm_bytes"}]

        async def mock_render(source_media, output_path, **kwargs):
            return _create_real_valid_mp4(Path(output_path))

        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            synthesize_segments=mock_synth,
            render_pipeline=mock_render,
        )
        assert res["ok"] is True
        assert res["output_mode"] == smart.OUTPUT_MODE_DUBBED_SINGLE
        assert res["final_mp4_path"] == str(output_mp4)
        assert res["auto_smart_verified"] is True
    asyncio.run(_run())


def test_23_invalid_final_mp4_rejected(tmp_path):
    """Empty or non-existent rendered file fails MP4 validation truthfully."""
    async def _run():
        source_media = _create_real_valid_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"
        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Chào", "start_ms": 0, "end_ms": 1000}]

        async def mock_synth(cues, speaker_voice_map):
            return [{"cue_id": "c1", "audio": b"dummy"}]

        async def mock_render(source_media, output_path, **kwargs):
            Path(output_path).write_bytes(b"")
            return output_path

        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            synthesize_segments=mock_synth,
            render_pipeline=mock_render,
        )
        assert res["ok"] is False
        assert res["output_mode"] == smart.OUTPUT_MODE_FAILED
        assert "empty_or_undersized_file" in str(res["blocker"])
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
        source_media = _create_real_valid_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"
        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Chào", "start_ms": 0, "end_ms": 1000}]

        async def mock_synth(cues, speaker_voice_map):
            return [{"cue_id": "c1", "audio": b"dummy"}]

        async def failing_render(**kwargs):
            raise RuntimeError("ffmpeg_mux_failure_code_1")

        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            synthesize_segments=mock_synth,
            render_pipeline=failing_render,
        )
        assert res["ok"] is False
        assert res["output_mode"] == smart.OUTPUT_MODE_FAILED
        assert "render_pipeline_failed" in str(res["blocker"])
    asyncio.run(_run())


def test_26_cancellation_respected(tmp_path):
    """Cancellation flag aborts processing before synthesis/render."""
    async def _run():
        source_media = _create_real_valid_mp4(tmp_path / "source.mp4")
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
    def cooking_strict_engine(*args, **kwargs):
        return {
            "chef_male": {"voice_register": "low", "confidence": 0.95},
            "host_female": {"voice_register": "high", "confidence": 0.93},
        }

    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=TEST_POOLS,
        strict_two_classifier=cooking_strict_engine,
    )
    assert decision.detected_speaker_count == 2
    assert decision.effective_voice_count == 2
    assert decision.output_mode == smart.OUTPUT_MODE_DUBBED_MULTI
    assert decision.strategy == smart.STRATEGY_STRICT_TWO
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
    """Ensure legacy routes are unchanged, unselected traffic never routes to Smart, and Smart requires explicit opt-in."""
    import bot
    from unittest.mock import patch

    with patch("bot.subdub_auto_provider_capacity_ready", return_value=True):
        # 1. Unselected / Default traffic must never route to Smart (UNSELECTED_TRAFFIC_TO_SMART=0)
        default_state = {"mode": "dub"}
        default_decision, _ = bot.subdub_auto_routing_decision(default_state)
        assert default_decision != "auto_smart_multivoice", "Unselected traffic routed to Smart!"
        assert default_decision == "manual"

        # 2. AUTO2 behavior unchanged: selecting auto_speaker_gender without smart opt-in routes to auto_speaker
        auto2_state = {
            "mode": "dub",
            "voice_kind": "auto_speaker_gender",
            "voice_selection_mode": "auto_speaker",
        }
        auto2_decision, _ = bot.subdub_auto_routing_decision(auto2_state)
        assert auto2_decision == "auto_speaker"

        # 3. AUTOMULTI behavior unchanged: selecting auto_multi_speaker routes to auto_multi
        automulti_state = bot.subdub_apply_voice_choice(
            {"mode": "dub"}, "auto_multi_speaker", activation_enabled=True
        )
        automulti_decision, _ = bot.subdub_auto_routing_decision(automulti_state)
        assert automulti_decision in {"auto_multi_speaker", "auto_multi_speaker_v2"}
        assert automulti_decision != "auto_smart_multivoice"

        # 4. SMART requires explicit opt-in
        smart_state = {
            "mode": "dub",
            "voice_kind": "auto_speaker_gender",
            "voice_selection_mode": "auto_speaker",
            "auto_speaker_lane": "auto_smart_multivoice",
            "auto_smart_multivoice_opt_in": True,
        }
        smart_decision, reason = bot.subdub_auto_routing_decision(smart_state)
        assert smart_decision == "auto_smart_multivoice"
        assert reason == "explicit_smart_multivoice_opt_in"


def test_38_no_legacy_production_file_change():
    """Ensure git diff against base SHA contains 0 changes to legacy frozen production files."""
    frozen_files = [
        "services/subdub_blackboxes/auto_speaker.py",
        "services/subdub_two_speaker_gender_onnx.py",
        "services/subdub_speaker_cast.py",
    ]
    diff_res = subprocess.run(
        ["git", "diff", "73ab3dca8211aaa37cf76af75ccc75b0ac1dd8ee", "--name-only"],
        capture_output=True,
        text=True,
    )
    changed_files = [line.strip() for line in diff_res.stdout.splitlines() if line.strip()]
    for ff in frozen_files:
        assert ff not in changed_files, f"Legacy frozen file was modified: {ff}"


# ============================================================
# C1 TESTS (39 - 58)
# ============================================================

def test_39_strict_two_cannot_be_emitted_without_strict_engine_success():
    """GAP 1: Emitting STRICT_TWO is forbidden without real strict engine execution/success."""
    cues = [
        {"cue_id": "c1", "speaker_id": "s1", "text": "Thoại 1", "start_ms": 0, "end_ms": 1000},
        {"cue_id": "c2", "speaker_id": "s2", "text": "Thoại 2", "start_ms": 1100, "end_ms": 2000},
    ]
    # No strict engine provided -> MUST NOT emit STRICT_TWO
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS, strict_two_classifier=None)
    assert decision.strategy != smart.STRATEGY_STRICT_TWO
    assert decision.strategy == smart.STRATEGY_STABLE_FALLBACK


def test_40_strict_engine_spy_is_actually_called():
    """GAP 1: Strict classifier spy is executed exactly once for N=2."""
    cues = [
        {"cue_id": "c1", "speaker_id": "s1", "text": "Thoại 1", "start_ms": 0, "end_ms": 1000},
        {"cue_id": "c2", "speaker_id": "s2", "text": "Thoại 2", "start_ms": 1100, "end_ms": 2000},
    ]
    call_count = 0
    def strict_spy(pcm, ranges, **kwargs):
        nonlocal call_count
        call_count += 1
        return {
            "s1": {"voice_register": "low"},
            "s2": {"voice_register": "high"},
        }

    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS, strict_two_classifier=strict_spy)
    assert call_count == 1
    assert decision.strategy == smart.STRATEGY_STRICT_TWO


def test_41_strict_manual_required_falls_back_without_manual_halt():
    """GAP 1: If strict engine raises AutoCastManualRequired, Smart catches it and falls back."""
    cues = [
        {"cue_id": "c1", "speaker_id": "s1", "text": "Thoại 1", "start_ms": 0, "end_ms": 1000},
        {"cue_id": "c2", "speaker_id": "s2", "text": "Thoại 2", "start_ms": 1100, "end_ms": 2000},
    ]
    def strict_manual_err(*args, **kwargs):
        raise speaker_cast.AutoCastManualRequired()

    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS, strict_two_classifier=strict_manual_err)
    assert decision.strategy == smart.STRATEGY_STABLE_FALLBACK
    assert decision.fallback_level == 1
    assert decision.effective_voice_count == 2


def test_42_missing_speaker_id_does_not_invent_speaker_0():
    """GAP 2: Missing speaker identity on speech cue must NOT invent speaker_0."""
    cues = [
        {"cue_id": "c1", "text": "Câu nói không có speaker_id", "start_ms": 0, "end_ms": 1000},
    ]
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS)
    assert "speaker_0" not in decision.speaker_voice_map
    assert decision.cue_dispositions["c1"] == smart.DISPOSITION_TERMINAL_REJECTED
    assert len(decision.tts_cues) == 0


def test_43_missing_canonical_cue_identity_does_not_invent_current_canonical_id():
    """GAP 2: Cue with missing cue_id is marked TERMINAL_REJECTED, no fabricated canonical ID."""
    cues = [
        {"speaker_id": "spk_1", "text": "Câu nói không có cue_id", "start_ms": 0, "end_ms": 1000},
    ]
    decision = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS)
    assert len(decision.tts_cues) == 0
    assert any(disp == smart.DISPOSITION_TERMINAL_REJECTED for disp in decision.cue_dispositions.values())


def test_44_validated_pools_none_does_not_invent_provider_voices():
    """GAP 3: validated_pools=None must NOT invent vi-VN-Standard-A/B/C/D provider voices."""
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Xin chào", "start_ms": 0, "end_ms": 1000},
    ]
    decision = smart.decide_smart_multivoice(cues, validated_pools=None)
    for v in decision.speaker_voice_map.values():
        assert "vi-VN-Standard" not in v
    assert decision.fallback_level in {4, 5}
    assert decision.output_mode == smart.OUTPUT_MODE_SUBTITLE_ONLY


def test_45_malformed_unapproved_pool_rejected_falls_lower_truthfully():
    """GAP 3: Malformed pool falls down ladder truthfully without manual halt."""
    malformed_pools = {"low": ["invalid space voice id!"], "high": []}
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Thoại", "start_ms": 0, "end_ms": 1000},
    ]
    decision = smart.decide_smart_multivoice(cues, validated_pools=malformed_pools)
    assert decision.strategy == smart.STRATEGY_SUBTITLE_ONLY
    assert decision.fallback_level == 4
    assert decision.fallback_reason == "no_approved_voice_pool"


def test_46_dubbed_mode_without_synth_authority_cannot_succeed(tmp_path):
    """GAP 4: DUBBED mode without synthesize_segments cannot succeed."""
    async def _run():
        source_media = _create_real_valid_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"
        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Chào", "start_ms": 0, "end_ms": 1000}]

        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            synthesize_segments=None,
        )
        assert res["ok"] is False
        assert res["output_mode"] == smart.OUTPUT_MODE_FAILED
        assert "synthesis_authority_required" in res["blocker"]
    asyncio.run(_run())


def test_47_partial_tts_coverage_cannot_succeed_as_dubbed(tmp_path):
    """GAP 4: Missing chunk for one of the TTS cues must fail."""
    async def _run():
        source_media = _create_real_valid_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"
        cues = [
            {"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu 1", "start_ms": 0, "end_ms": 1000},
            {"cue_id": "c2", "speaker_id": "spk_1", "text": "Câu 2", "start_ms": 1100, "end_ms": 2000},
        ]
        # Synthesizer only returns c1, omitting c2
        async def partial_synth(cues, speaker_voice_map):
            return [{"cue_id": "c1", "audio": b"chunk1_data"}]

        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            synthesize_segments=partial_synth,
        )
        assert res["ok"] is False
        assert "missing_tts_cues" in res["blocker"]
    asyncio.run(_run())


def test_48_duplicate_tts_artifact_rejected(tmp_path):
    """GAP 4: Duplicate chunks for the same cue must be rejected."""
    async def _run():
        source_media = _create_real_valid_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"
        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu 1", "start_ms": 0, "end_ms": 1000}]

        async def dup_synth(cues, speaker_voice_map):
            return [
                {"cue_id": "c1", "audio": b"chunk1_a"},
                {"cue_id": "c1", "audio": b"chunk1_b"},
            ]

        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            synthesize_segments=dup_synth,
        )
        assert res["ok"] is False
        assert "duplicate_tts_chunk" in res["blocker"]
    asyncio.run(_run())


def test_49_unknown_tts_artifact_rejected(tmp_path):
    """GAP 4: Chunk with unrecognized cue_id must be rejected."""
    async def _run():
        source_media = _create_real_valid_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"
        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Câu 1", "start_ms": 0, "end_ms": 1000}]

        async def unknown_synth(cues, speaker_voice_map):
            return [
                {"cue_id": "c1", "audio": b"chunk1"},
                {"cue_id": "c_unknown_99", "audio": b"chunk99"},
            ]

        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            synthesize_segments=unknown_synth,
        )
        assert res["ok"] is False
        assert "unknown_tts_chunk" in res["blocker"]
    asyncio.run(_run())


def test_50_non_empty_garbage_mp4_rejected_without_caller_probe(tmp_path):
    """GAP 5: Non-empty garbage file rejected by canonical validator when probe_fn is absent."""
    async def _run():
        source_media = _create_real_valid_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"
        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Thoại", "start_ms": 0, "end_ms": 1000}]

        async def mock_synth(cues, speaker_voice_map):
            return [{"cue_id": "c1", "audio": b"data"}]

        async def garbage_render(source_media, output_path, **kwargs):
            # Write 4KB of garbage non-mp4 bytes
            Path(output_path).write_bytes(b"\x00" * 4096)
            return output_path

        # probe_fn is absent -> default canonical video_local_validation must reject it!
        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            synthesize_segments=mock_synth,
            render_pipeline=garbage_render,
            probe_fn=None,
        )
        assert res["ok"] is False
        assert res["output_mode"] == smart.OUTPUT_MODE_FAILED
        assert any(term in str(res["blocker"]) for term in ("canonical_mp4_validation_failed", "output_container_invalid", "ffprobe_failed"))
    asyncio.run(_run())


def test_51_stale_pre_existing_output_rejected(tmp_path):
    """GAP 6: Stale output from previous runs must be cleared and not accepted if render fails."""
    async def _run():
        source_media = _create_real_valid_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"
        # Pre-create stale file on disk
        _create_real_valid_mp4(output_mp4)
        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Thoại", "start_ms": 0, "end_ms": 1000}]

        async def mock_synth(cues, speaker_voice_map):
            return [{"cue_id": "c1", "audio": b"data"}]

        # Render pipeline fails to create any file
        async def failing_render(source_media, output_path, **kwargs):
            return output_path

        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            synthesize_segments=mock_synth,
            render_pipeline=failing_render,
        )
        assert res["ok"] is False
        assert "did_not_create_output" in res["blocker"]
    asyncio.run(_run())


def test_52_render_pipeline_absent_cannot_claim_current_run_output(tmp_path):
    """GAP 6: render_pipeline absent cannot claim current run output for dubbed mode."""
    async def _run():
        source_media = _create_real_valid_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"
        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Thoại", "start_ms": 0, "end_ms": 1000}]

        async def mock_synth(cues, speaker_voice_map):
            return [{"cue_id": "c1", "audio": b"data"}]

        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            synthesize_segments=mock_synth,
            render_pipeline=None,
        )
        assert res["ok"] is False
        assert "render_pipeline_required" in res["blocker"]
    asyncio.run(_run())


def test_53_bar_fixture_full_runner(tmp_path):
    """GAP 7: BAR fixture full runner produces valid MP4."""
    async def _run():
        source_media = _create_real_valid_mp4(tmp_path / "bar_source.mp4")
        output_mp4 = tmp_path / "bar_output.mp4"
        cues = [
            {"cue_id": "c1", "speaker_id": "person", "text": "Chào bạn ở quán bar", "start_ms": 0, "end_ms": 1000},
            {"cue_id": "c2", "speaker_id": "singer", "text": "♪ Trót yêu em ♪", "start_ms": 1000, "end_ms": 3000, "is_singing": True},
            {"cue_id": "c3", "text": "[Music]", "start_ms": 3000, "end_ms": 5000, "is_music": True},
        ]
        synth_cues_called = []
        async def mock_synth(cues, speaker_voice_map):
            synth_cues_called.extend(cues)
            return [{"cue_id": c["cue_id"], "audio": b"data"} for c in cues]

        async def mock_render(source_media, output_path, **kwargs):
            return _create_real_valid_mp4(Path(output_path))

        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            synthesize_segments=mock_synth,
            render_pipeline=mock_render,
        )
        assert res["ok"] is True
        assert res["detected_speaker_count"] == 1
        assert res["output_mode"] == smart.OUTPUT_MODE_DUBBED_SINGLE
        assert len(synth_cues_called) == 1
        assert synth_cues_called[0]["cue_id"] == "c1"
    asyncio.run(_run())


def test_54_bar_singing_music_never_sent_to_tts(tmp_path):
    """GAP 7/8: Bar singing and music cues are NEVER dispatched to TTS synthesizer."""
    async def _run():
        source_media = _create_real_valid_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"
        cues = [
            {"cue_id": "c1", "speaker_id": "person", "text": "Nói chuyện", "start_ms": 0, "end_ms": 1000},
            {"cue_id": "c2", "text": "♪ Hát bài này ♪", "start_ms": 1000, "end_ms": 2000, "is_singing": True},
            {"cue_id": "c3", "text": "[Music]", "start_ms": 2000, "end_ms": 3000, "is_music": True},
        ]
        tts_received_ids = []
        async def mock_synth(cues, speaker_voice_map):
            for c in cues:
                tts_received_ids.append(c["cue_id"])
            return [{"cue_id": c["cue_id"], "audio": b"data"} for c in cues]

        async def mock_render(source_media, output_path, **kwargs):
            return _create_real_valid_mp4(Path(output_path))

        await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            synthesize_segments=mock_synth,
            render_pipeline=mock_render,
        )
        assert tts_received_ids == ["c1"]
        assert "c2" not in tts_received_ids
        assert "c3" not in tts_received_ids
    asyncio.run(_run())


def test_55_preserved_bar_cues_reach_renderer(tmp_path):
    """GAP 8: Audio preservation directives explicitly reach render pipeline."""
    async def _run():
        source_media = _create_real_valid_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"
        cues = [
            {"cue_id": "c1", "speaker_id": "person", "text": "Nói", "start_ms": 0, "end_ms": 1000},
            {"cue_id": "c2", "text": "♪ Hát ♪", "start_ms": 1000, "end_ms": 2000, "is_singing": True},
            {"cue_id": "c3", "text": "[Music]", "start_ms": 2000, "end_ms": 3000, "is_music": True},
        ]
        render_spy_kwargs = {}
        async def mock_synth(cues, speaker_voice_map):
            return [{"cue_id": "c1", "audio": b"data"}]

        async def mock_render(source_media, output_path, **kwargs):
            render_spy_kwargs.update(kwargs)
            return _create_real_valid_mp4(Path(output_path))

        await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            synthesize_segments=mock_synth,
            render_pipeline=mock_render,
        )
        assert "preserved_cues" in render_spy_kwargs
        preserved_ids = [c["cue_id"] for c in render_spy_kwargs["preserved_cues"]]
        assert "c2" in preserved_ids
        assert "c3" in preserved_ids
        assert "c1" not in preserved_ids
    asyncio.run(_run())


def test_56_cooking_fixture_full_runner(tmp_path):
    """GAP 7: Two-person cooking fixture full runner produces valid MP4 with distinct voices."""
    async def _run():
        source_media = _create_real_valid_mp4(tmp_path / "cooking_source.mp4")
        output_mp4 = tmp_path / "cooking_output.mp4"
        cues = [
            {"cue_id": "c1", "speaker_id": "chef", "text": "Nấu phở", "start_ms": 0, "end_ms": 1500},
            {"cue_id": "c2", "speaker_id": "host", "text": "Ngon quá", "start_ms": 1600, "end_ms": 3000},
        ]
        def mock_strict(*args, **kwargs):
            return {
                "chef": {"voice_register": "low"},
                "host": {"voice_register": "high"},
            }

        async def mock_synth(cues, speaker_voice_map):
            return [{"cue_id": c["cue_id"], "audio": b"data"} for c in cues]

        async def mock_render(source_media, output_path, **kwargs):
            return _create_real_valid_mp4(Path(output_path))

        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            strict_two_classifier=mock_strict,
            synthesize_segments=mock_synth,
            render_pipeline=mock_render,
        )
        assert res["ok"] is True
        assert res["strategy"] == smart.STRATEGY_STRICT_TWO
        assert res["output_mode"] == smart.OUTPUT_MODE_DUBBED_MULTI
        assert res["effective_voice_count"] == 2
    asyncio.run(_run())


def test_57_cancellation_after_synthesis_cannot_succeed(tmp_path):
    """Checkpoint: Cancellation occurring after synthesis must not succeed."""
    async def _run():
        source_media = _create_real_valid_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"
        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Thoại", "start_ms": 0, "end_ms": 1000}]

        cancelled_state = False
        async def mock_synth(cues, speaker_voice_map):
            nonlocal cancelled_state
            cancelled_state = True # Trigger cancel during/after synth
            return [{"cue_id": "c1", "audio": b"data"}]

        async def mock_render(source_media, output_path, **kwargs):
            return _create_real_valid_mp4(Path(output_path))

        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            synthesize_segments=mock_synth,
            render_pipeline=mock_render,
            is_cancelled=lambda: cancelled_state,
        )
        assert res["ok"] is False
        assert res["blocker"] == "cancelled"
    asyncio.run(_run())


def test_58_cancellation_before_render_cannot_succeed(tmp_path):
    """Checkpoint: Cancellation occurring before render must not succeed."""
    async def _run():
        source_media = _create_real_valid_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"
        cues = [{"cue_id": "c1", "speaker_id": "spk_1", "text": "Thoại", "start_ms": 0, "end_ms": 1000}]

        cancel_flag = False
        async def mock_synth(cues, speaker_voice_map):
            nonlocal cancel_flag
            cancel_flag = True
            return [{"cue_id": "c1", "audio": b"data"}]

        render_called = False
        async def mock_render(source_media, output_path, **kwargs):
            nonlocal render_called
            render_called = True
            return _create_real_valid_mp4(Path(output_path))

        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            synthesize_segments=mock_synth,
            render_pipeline=mock_render,
            is_cancelled=lambda: cancel_flag,
        )
        assert res["ok"] is False
        assert res["blocker"] == "cancelled"
        assert render_called is False
    asyncio.run(_run())


def test_59_unapproved_default_fallback_voice_bypassed_to_approved_pool_root():
    """Invariant: Unapproved default_fallback_voice cannot enter speaker map or tts_cues."""
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Thoại", "start_ms": 0, "end_ms": 1000},
    ]
    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=TEST_POOLS,
        default_fallback_voice="unapproved_foreign_voice_999",
    )
    all_approved = TEST_POOLS["low"] + TEST_POOLS["high"]
    assert "unapproved_foreign_voice_999" not in decision.speaker_voice_map.values()
    assert decision.speaker_voice_map["spk_1"] in all_approved
    assert decision.tts_cues[0]["tts_voice_id"] in all_approved


def test_60_level3_override_with_unapproved_default_uses_approved_pool_deterministic():
    """Invariant: Level 3 override with unapproved default uses all_pool[0] deterministically."""
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "Thoại", "start_ms": 0, "end_ms": 1000},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "Thoại 2", "start_ms": 1100, "end_ms": 2000},
    ]
    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=TEST_POOLS,
        default_fallback_voice="rogue_unvalidated_voice",
        fallback_level_override=3,
    )
    expected_default = (TEST_POOLS["low"] + TEST_POOLS["high"])[0]
    assert decision.strategy == smart.STRATEGY_SINGLE_DOMINANT
    assert decision.fallback_level == 3
    assert decision.speaker_voice_map["spk_1"] == expected_default
    assert decision.speaker_voice_map["spk_2"] == expected_default
    for tts_c in decision.tts_cues:
        assert tts_c["tts_voice_id"] == expected_default


def test_61_n2_single_voice_fallback_cannot_use_unapproved_default_override():
    """Invariant: N=2 single-voice pool fallback uses approved pool voice, not unapproved default."""
    single_pool = {"low": ["approved_only_voice_low"], "high": []}
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "A", "start_ms": 0, "end_ms": 1000},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "B", "start_ms": 1100, "end_ms": 2000},
    ]
    def failing_strict(*args, **kwargs):
        raise ValueError("strict failed")

    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=single_pool,
        default_fallback_voice="unapproved_external_voice",
        strict_two_classifier=failing_strict,
    )
    assert decision.strategy == smart.STRATEGY_SINGLE_DOMINANT
    assert decision.fallback_level == 3
    assert decision.speaker_voice_map["spk_1"] == "approved_only_voice_low"
    assert decision.speaker_voice_map["spk_2"] == "approved_only_voice_low"
    assert "unapproved_external_voice" not in decision.speaker_voice_map.values()


def test_62_explicit_approved_default_fallback_voice_accepted():
    """Invariant: When default_fallback_voice is an approved pool member, it is accepted."""
    approved_high = TEST_POOLS["high"][0]
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_1", "text": "A", "start_ms": 0, "end_ms": 1000},
        {"cue_id": "c2", "speaker_id": "spk_2", "text": "B", "start_ms": 1100, "end_ms": 2000},
    ]
    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=TEST_POOLS,
        default_fallback_voice=approved_high,
        fallback_level_override=3,
    )
    assert decision.speaker_voice_map["spk_1"] == approved_high
    assert decision.speaker_voice_map["spk_2"] == approved_high


def test_63_property_all_emitted_voices_subset_of_validated_pool():
    """Property Invariant: Every emitted voice in speaker_voice_map and tts_cues is a subset of all_pool."""
    all_approved = set(TEST_POOLS["low"] + TEST_POOLS["high"])

    # Test across multiple speaker counts and various default_fallback_voice values
    for spk_count in [1, 2, 3, 5, 8]:
        cues = [
            {"cue_id": f"c_{i}", "speaker_id": f"spk_{i}", "text": f"text {i}", "start_ms": i*1000, "end_ms": (i+1)*1000}
            for i in range(spk_count)
        ]
        for bad_fallback in [None, "", "   ", "unapproved_random_voice", "another_unknown"]:
            decision = smart.decide_smart_multivoice(
                cues,
                validated_pools=TEST_POOLS,
                default_fallback_voice=bad_fallback,
            )
            emitted = set(decision.speaker_voice_map.values())
            assert emitted.issubset(all_approved), f"Emitted unapproved voice: {emitted - all_approved}"
            for tts_c in decision.tts_cues:
                assert tts_c["tts_voice_id"] in all_approved


# ---------------------------------------------------------------------------
# Tests for P0.SUBDUB.AUTO.SMART.MULTIVOICE.5VOICE.EXACT_MAP.RUNTIME.WIRING.R1
# ---------------------------------------------------------------------------

APPROVED_5VOICE_MAP = {
    "person_1": "Vietnamese_Professional_Narrator_v2",
    "person_2": "Vietnamese_Cute_Girl_v1",
    "person_3": "Vietnamese_Cheerful_Instructor_v1",
    "person_4": "Vietnamese_crisp_announcer_v2",
    "person_5": "Vietnamese_Steady_Instructor_v1",
}

FIVEVOICE_APPROVED_POOLS = {
    "low": [
        "Vietnamese_Professional_Narrator_v2",
        "Vietnamese_crisp_announcer_v2",
        "Vietnamese_Steady_Instructor_v1",
    ],
    "high": [
        "Vietnamese_Cute_Girl_v1",
        "Vietnamese_Cheerful_Instructor_v1",
    ],
}

MANIFEST_36_SPEAKER_SEQUENCE = [
    ("turn_001", "person_1"), ("turn_002", "person_2"), ("turn_003", "person_1"),
    ("turn_004", "person_2"), ("turn_005", "person_3"), ("turn_006", "person_4"),
    ("turn_007", "person_2"), ("turn_008", "person_1"), ("turn_009", "person_2"),
    ("turn_010", "person_3"), ("turn_011", "person_2"), ("turn_012", "person_1"),
    ("turn_013", "person_2"), ("turn_014", "person_1"), ("turn_015", "person_2"),
    ("turn_016", "person_1"), ("turn_017", "person_2"), ("turn_018", "person_1"),
    ("turn_019", "person_2"), ("turn_020", "person_2"), ("turn_021", "person_1"),
    ("turn_022", "person_2"), ("turn_023", "person_1"), ("turn_024", "person_5"),
    ("turn_025", "person_1"), ("turn_026", "person_2"), ("turn_027", "person_5"),
    ("turn_028", "person_2"), ("turn_029", "person_5"), ("turn_030", "person_2"),
    ("turn_031", "person_5"), ("turn_032", "person_2"), ("turn_033", "person_1"),
    ("turn_034", "person_2"), ("turn_035", "person_1"), ("turn_036", "person_1"),
]


def _build_36_cues() -> list[dict[str, Any]]:
    return [
        {
            "cue_id": turn_id,
            "speaker_id": spk_id,
            "text": f"Canonical turn {turn_id} by {spk_id}",
            "start_ms": i * 1000,
            "end_ms": (i + 1) * 1000,
        }
        for i, (turn_id, spk_id) in enumerate(MANIFEST_36_SPEAKER_SEQUENCE)
    ]


def test_64_n5_exact_map_honored():
    """N5_EXACT_MAP_HONORED=PASS: Verify locked 5-voice map is adopted exactly."""
    cues = _build_36_cues()
    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=FIVEVOICE_APPROVED_POOLS,
        locked_speaker_voice_map=APPROVED_5VOICE_MAP,
    )
    assert decision.output_mode == smart.OUTPUT_MODE_DUBBED_MULTI
    assert decision.strategy == smart.STRATEGY_GENERIC_MULTI
    assert decision.fallback_level == 0
    assert decision.fallback_reason is None
    assert decision.detected_speaker_count == 5
    assert decision.effective_speaker_count == 5
    assert decision.effective_voice_count == 5
    assert decision.speaker_voice_map == APPROVED_5VOICE_MAP


def test_65_seed_independent_exact_map():
    """SEED_A_EXACT_MAP=PASS, SEED_B_EXACT_MAP=PASS, SEED_INDEPENDENT_EXACT_MAP=YES.

    Proves that two different assignment seeds yield the identical approved map.
    """
    cues = _build_36_cues()
    decision_a = smart.decide_smart_multivoice(
        cues,
        validated_pools=FIVEVOICE_APPROVED_POOLS,
        assignment_seed="seed_acceptance_alpha",
        locked_speaker_voice_map=APPROVED_5VOICE_MAP,
    )
    decision_b = smart.decide_smart_multivoice(
        cues,
        validated_pools=FIVEVOICE_APPROVED_POOLS,
        assignment_seed="seed_acceptance_beta",
        locked_speaker_voice_map=APPROVED_5VOICE_MAP,
    )
    assert decision_a.speaker_voice_map == APPROVED_5VOICE_MAP
    assert decision_b.speaker_voice_map == APPROVED_5VOICE_MAP
    assert decision_a.speaker_voice_map == decision_b.speaker_voice_map


def test_66_all_36_cues_use_canonical_speaker_voice():
    """ALL_36_CUES_USE_CANONICAL_SPEAKER_VOICE=YES: Every emitted cue has tts_voice_id == locked_map[speaker_id]."""
    cues = _build_36_cues()
    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=FIVEVOICE_APPROVED_POOLS,
        locked_speaker_voice_map=APPROVED_5VOICE_MAP,
    )
    assert len(decision.tts_cues) == 36
    for tts_cue in decision.tts_cues:
        cid = tts_cue["cue_id"]
        spk = tts_cue["speaker_id"]
        expected_voice = APPROVED_5VOICE_MAP[spk]
        assert tts_cue["tts_voice_id"] == expected_voice, f"Cue {cid} for speaker {spk} had unexpected voice {tts_cue['tts_voice_id']}"


def test_67_missing_speaker_fail_closed():
    """MISSING_SPEAKER_FAIL_CLOSED=YES: Missing speaker in locked map fails closed before synthesis."""
    cues = _build_36_cues()
    partial_map = dict(APPROVED_5VOICE_MAP)
    del partial_map["person_5"]

    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=FIVEVOICE_APPROVED_POOLS,
        locked_speaker_voice_map=partial_map,
    )
    assert decision.output_mode == smart.OUTPUT_MODE_FAILED
    assert decision.strategy == smart.STRATEGY_FAILED
    assert "LOCKED_SPEAKER_VOICE_MAP_CONFLICT" in str(decision.fallback_reason)
    assert "missing_speaker" in str(decision.fallback_reason)
    assert decision.tts_cues == []


def test_68_extra_speaker_fail_closed():
    """EXTRA_SPEAKER_FAIL_CLOSED=YES: Extra speaker in locked map fails closed."""
    cues = _build_36_cues()
    extra_map = dict(APPROVED_5VOICE_MAP)
    extra_map["person_6"] = "Vietnamese_Professional_Narrator_v2"

    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=FIVEVOICE_APPROVED_POOLS,
        locked_speaker_voice_map=extra_map,
    )
    assert decision.output_mode == smart.OUTPUT_MODE_FAILED
    assert decision.strategy == smart.STRATEGY_FAILED
    assert "LOCKED_SPEAKER_VOICE_MAP_CONFLICT" in str(decision.fallback_reason)
    assert "extra_speaker" in str(decision.fallback_reason)
    assert decision.tts_cues == []


def test_69_duplicate_voice_fail_closed():
    """DUPLICATE_VOICE_FAIL_CLOSED=YES: Duplicate voice allocation fails closed."""
    cues = _build_36_cues()
    dup_map = dict(APPROVED_5VOICE_MAP)
    dup_map["person_5"] = dup_map["person_1"]

    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=FIVEVOICE_APPROVED_POOLS,
        locked_speaker_voice_map=dup_map,
    )
    assert decision.output_mode == smart.OUTPUT_MODE_FAILED
    assert decision.strategy == smart.STRATEGY_FAILED
    assert "LOCKED_SPEAKER_VOICE_MAP_CONFLICT" in str(decision.fallback_reason)
    assert "duplicate_voice" in str(decision.fallback_reason)
    assert decision.tts_cues == []


def test_69b_normalized_duplicate_voice_fail_closed():
    """NORMALIZED_DUPLICATE_VOICE_FAIL_CLOSED=YES: Equivalent voice IDs differing only by whitespace fail closed."""
    cues = _build_36_cues()
    dup_map = dict(APPROVED_5VOICE_MAP)
    # Assign person_5 the same voice as person_1 with surrounding whitespace
    dup_map["person_5"] = f"  {dup_map['person_1']}  "

    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=FIVEVOICE_APPROVED_POOLS,
        locked_speaker_voice_map=dup_map,
    )
    assert decision.output_mode == smart.OUTPUT_MODE_FAILED
    assert decision.strategy == smart.STRATEGY_FAILED
    assert "LOCKED_SPEAKER_VOICE_MAP_CONFLICT:duplicate_voice" in str(decision.fallback_reason)
    assert decision.tts_cues == []


def test_70_unknown_voice_fail_closed():
    """UNKNOWN_VOICE_FAIL_CLOSED=YES: Malformed/illegal voice ID fails closed."""
    cues = _build_36_cues()
    bad_map = dict(APPROVED_5VOICE_MAP)
    bad_map["person_1"] = "invalid voice id with spaces!"

    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=FIVEVOICE_APPROVED_POOLS,
        locked_speaker_voice_map=bad_map,
    )
    assert decision.output_mode == smart.OUTPUT_MODE_FAILED
    assert decision.strategy == smart.STRATEGY_FAILED
    assert "LOCKED_SPEAKER_VOICE_MAP_CONFLICT" in str(decision.fallback_reason)
    assert "unknown_voice" in str(decision.fallback_reason)
    assert decision.tts_cues == []


def test_71_unapproved_voice_fail_closed():
    """UNAPPROVED_VOICE_FAIL_CLOSED=YES: Voice not in validated all_pool fails closed."""
    cues = _build_36_cues()
    unapproved_map = dict(APPROVED_5VOICE_MAP)
    unapproved_map["person_1"] = "Vietnamese_Unapproved_Voice_v99"

    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=FIVEVOICE_APPROVED_POOLS,
        locked_speaker_voice_map=unapproved_map,
    )
    assert decision.output_mode == smart.OUTPUT_MODE_FAILED
    assert decision.strategy == smart.STRATEGY_FAILED
    assert "LOCKED_SPEAKER_VOICE_MAP_CONFLICT" in str(decision.fallback_reason)
    assert "unapproved_voice" in str(decision.fallback_reason)
    assert decision.tts_cues == []


def test_72_resume_map_immutable(tmp_path):
    """RESUME_MAP_IMMUTABLE=YES: Resume through blackbox state retains exact map without recomputing from seed."""
    async def _run():
        media_file = tmp_path / "source.mp4"
        _create_mock_file(media_file)
        cues = _build_36_cues()

        synth_called = False

        async def mock_synth(cues, speaker_voice_map):
            nonlocal synth_called
            synth_called = True
            return [{"cue_id": c["cue_id"], "audio": b"dummy_mp3_data"} for c in cues]

        def mock_render(**kwargs):
            out = Path(kwargs["output_path"])
            _create_real_valid_mp4(out)
            return out

        # Initial run with raw whitespace in locked map: proves normalization on persist
        raw_whitespace_map = {k: f"  {v}  " for k, v in APPROVED_5VOICE_MAP.items()}
        initial_state = {
            "auto_smart_multivoice": True,
            "job_id": "seed_initial_run",
            "locked_speaker_voice_map": raw_whitespace_map,
        }
        out1 = await smart.run_auto_smart_multivoice(
            source_media=str(media_file),
            segments=cues,
            output_path=str(tmp_path / "out1.mp4"),
            validated_pools=FIVEVOICE_APPROVED_POOLS,
            synthesize_segments=mock_synth,
            render_pipeline=mock_render,
            locked_speaker_voice_map=raw_whitespace_map,
            state=initial_state,
        )
        assert out1["ok"] is True
        assert out1["speaker_voice_map"] == APPROVED_5VOICE_MAP
        assert out1["locked_speaker_voice_map"] == APPROVED_5VOICE_MAP

        # Resumed run: completely new job_id / seed, locked_speaker_voice_map in persisted state
        resumed_state = {
            "job_id": "completely_different_resumed_seed_9999",
            "locked_speaker_voice_map": out1["locked_speaker_voice_map"],
        }

        out2 = await smart.run_auto_smart_multivoice(
            source_media=str(media_file),
            segments=cues,
            output_path=str(tmp_path / "out2.mp4"),
            validated_pools=FIVEVOICE_APPROVED_POOLS,
            synthesize_segments=mock_synth,
            render_pipeline=mock_render,
            state=resumed_state,
        )
        assert out2["ok"] is True
        assert out2["speaker_voice_map"] == APPROVED_5VOICE_MAP, "Resumed run must retain exact map, not recompute from seed"
        assert out2["locked_speaker_voice_map"] == APPROVED_5VOICE_MAP

    asyncio.run(_run())


def test_73_no_lock_existing_auto_behavior_unchanged():
    """NO_LOCK_EXISTING_AUTO_BEHAVIOR_UNCHANGED=YES: Without locked map, existing automatic allocation runs unchanged."""
    cues = _build_36_cues()
    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=TEST_POOLS,
        assignment_seed="fixed_auto_seed",
    )
    assert decision.output_mode == smart.OUTPUT_MODE_DUBBED_MULTI
    assert decision.strategy == smart.STRATEGY_GENERIC_MULTI
    assert decision.effective_speaker_count == 5
    assert decision.effective_voice_count == 5
    all_test_voices = set(TEST_POOLS["low"] + TEST_POOLS["high"])
    for spk, v in decision.speaker_voice_map.items():
        assert v in all_test_voices


def test_74_locked_map_conflict_aborts_before_synthesis(tmp_path):
    """Conflicted locked map fails closed with BLOCKER=LOCKED_SPEAKER_VOICE_MAP_CONFLICT and 0 synth calls."""
    async def _run():
        media_file = tmp_path / "source.mp4"
        _create_mock_file(media_file)
        cues = _build_36_cues()

        synth_called = False

        async def spy_synth(cues, speaker_voice_map):
            nonlocal synth_called
            synth_called = True
            return []

        conflicted_map = dict(APPROVED_5VOICE_MAP)
        conflicted_map["person_1"] = "Vietnamese_Unapproved_Voice_v99"

        res = await smart.run_auto_smart_multivoice(
            source_media=str(media_file),
            segments=cues,
            output_path=str(tmp_path / "out.mp4"),
            validated_pools=FIVEVOICE_APPROVED_POOLS,
            synthesize_segments=spy_synth,
            locked_speaker_voice_map=conflicted_map,
        )
        assert res["ok"] is False
        assert res["output_mode"] == smart.OUTPUT_MODE_FAILED
        assert res["blocker"] == "LOCKED_SPEAKER_VOICE_MAP_CONFLICT"
        assert synth_called is False, "No synthesis authority may be invoked on map conflict"

    asyncio.run(_run())


def test_74b_normalized_duplicate_aborts_synthesis(tmp_path):
    """Normalized duplicate map aborts before synthesis with 0 synthesis calls."""
    async def _run():
        media_file = tmp_path / "source.mp4"
        _create_mock_file(media_file)
        cues = _build_36_cues()

        synth_called = False

        async def spy_synth(cues, speaker_voice_map):
            nonlocal synth_called
            synth_called = True
            return []

        dup_map = dict(APPROVED_5VOICE_MAP)
        dup_map["person_5"] = f"  {dup_map['person_1']}  "

        res = await smart.run_auto_smart_multivoice(
            source_media=str(media_file),
            segments=cues,
            output_path=str(tmp_path / "out.mp4"),
            validated_pools=FIVEVOICE_APPROVED_POOLS,
            synthesize_segments=spy_synth,
            locked_speaker_voice_map=dup_map,
        )
        assert res["ok"] is False
        assert res["output_mode"] == smart.OUTPUT_MODE_FAILED
        assert res["blocker"] == "LOCKED_SPEAKER_VOICE_MAP_CONFLICT"
        assert "LOCKED_SPEAKER_VOICE_MAP_CONFLICT:duplicate_voice" in str(res["fallback_reason"])
        assert res.get("tts_cues", []) == []
        assert synth_called is False, "No synthesis authority may be invoked on duplicate map conflict"

    asyncio.run(_run())


def test_75_smart_multivoice_prepare_subtitles_missing_require_auto_cast_regression(tmp_path):
    """REGRESSION: prepare_subtitles must be called with require_auto_cast=True.

    When require_auto_cast is False, ASR does not attach canonical speaker_id,
    causing speech cues to fail with SMART_CUE_TERMINAL_REJECTED (#FC3A0CAADB).
    """
    async def _run():
        dummy_media = tmp_path / "source.mp4"
        dummy_media.write_bytes(b"dummy video data 12345678")

        state = {
            "auto_speaker_lane": "auto_smart_multivoice",
            "voice_selection_mode": "auto_speaker",
            "mode": "subtitle_plus_dub",
            "_pipeline_saved_source_path": str(dummy_media),
        }

        observed: dict[str, Any] = {}

        async def prepare_subtitles_seam(st, *, require_auto_cast=False):
            observed["require_auto_cast"] = require_auto_cast
            if require_auto_cast:
                return {
                    "source_bytes": b"dummy video data 12345678",
                    "content_type": "video/mp4",
                    "source_segments": [
                        {"id": "cue_1", "cue_id": "cue_1", "speaker_id": "chunk_00:speaker_0", "start": 0.0, "end": 2.0, "text": "Hello"},
                    ],
                    "output_segments": [
                        {"id": "cue_1", "cue_id": "cue_1", "speaker_id": "chunk_00:speaker_0", "start": 0.0, "end": 2.0, "text": "Xin chao"},
                    ],
                }
            return {
                "source_bytes": b"dummy video data 12345678",
                "content_type": "video/mp4",
                "source_segments": [
                    {"id": "cue_1", "cue_id": "cue_1", "start": 0.0, "end": 2.0, "text": "Hello"},
                ],
                "output_segments": [
                    {"id": "cue_1", "cue_id": "cue_1", "start": 0.0, "end": 2.0, "text": "Xin chao"},
                ],
            }

        async def _mock_run_lane(*, lane_mode: str, runner: Any, **lane_payload: Any):
            return await runner(lane_mode=lane_mode, **lane_payload)

        async def _mock_runner(**kwargs: Any):
            prep_fn = kwargs.get("prepare_subtitles")
            prep = await prep_fn(kwargs.get("state") or {}) if callable(prep_fn) else {}
            return {
                "ok": True,
                "status": "SUCCESS",
                "source_bytes": prep.get("source_bytes") or b"dummy video data 12345678",
                "audio_bytes": b"dummy audio",
                "video_output": b"dummy mp4 bytes",
                "state": kwargs.get("state") or {},
            }

        result = await smart.run_auto_smart_multivoice_blackbox(
            state=state,
            prepare_subtitles=prepare_subtitles_seam,
            validated_pools={"low": ["v1", "v2"], "high": ["v3", "v4"]},
            run_lane_blackbox=_mock_run_lane,
            runner=_mock_runner,
        )

        assert observed.get("require_auto_cast") is True, (
            f"Expected prepare_subtitles to receive require_auto_cast=True, observed: {observed.get('require_auto_cast')}"
        )
        assert result.get("ok") is True, (
            f"Expected ok=True when require_auto_cast=True, got status={result.get('status')}, blocker={result.get('blocker')}"
        )

    asyncio.run(_run())


def test_78_anti_flapping_sandwich_smoothing():
    """Anti-flapping smoother corrects short-cue diarization bleeds sandwiched between same speaker."""
    cues = [
        {"cue_id": "c1", "speaker_id": "spk_female", "start_ms": 1000, "end_ms": 3000, "text": "Câu đầu"},
        # 0.3s cue sandwiched between spk_female cues, misattributed as spk_male
        {"cue_id": "c2", "speaker_id": "spk_male", "start_ms": 3000, "end_ms": 3300, "text": "Nếu tôi"},
        {"cue_id": "c3", "speaker_id": "spk_female", "start_ms": 3400, "end_ms": 5000, "text": "Câu tiếp"},
    ]
    smoothed = smart.smooth_smart_multivoice_cues(cues)
    assert len(smoothed) == 3
    assert smoothed[0]["speaker_id"] == "spk_female"
    assert smoothed[1]["speaker_id"] == "spk_female", "Sandwiched cue c2 must inherit spk_female"
    assert smoothed[1].get("anti_flapping_smoothed") is True
    assert smoothed[2]["speaker_id"] == "spk_female"


def test_79_gender_fidelity_matching():
    """Decide smart multivoice strictly assigns low register to male and high register to female voices."""
    cues = [
        {"cue_id": "c1", "speaker_id": "speaker_female_1", "start_ms": 0, "end_ms": 2000, "text": "Hello"},
        {"cue_id": "c2", "speaker_id": "speaker_male_1", "start_ms": 2500, "end_ms": 4000, "text": "Hi"},
        {"cue_id": "c3", "speaker_id": "speaker_female_2", "start_ms": 4500, "end_ms": 6000, "text": "How are you"},
    ]
    acoustic_classifications = {
        "speaker_female_1": {"voice_register": "high", "voice_gender": "female", "confidence": 0.95},
        "speaker_male_1": {"voice_register": "low", "voice_gender": "male", "confidence": 0.98},
        "speaker_female_2": {"voice_register": "high", "voice_gender": "female", "confidence": 0.90},
    }
    decision = smart.decide_smart_multivoice(
        cues,
        validated_pools=TEST_POOLS,
        acoustic_classifications=acoustic_classifications,
        assignment_seed="test_seed_79",
    )
    assert decision.output_mode == smart.OUTPUT_MODE_DUBBED_MULTI
    spk_map = decision.speaker_voice_map
    assert spk_map["speaker_male_1"] in TEST_POOLS["low"], "Male speaker must receive voice from low_pool"
    assert spk_map["speaker_female_1"] in TEST_POOLS["high"], "Female speaker 1 must receive voice from high_pool"
    assert spk_map["speaker_female_2"] in TEST_POOLS["high"], "Female speaker 2 must receive voice from high_pool"
    assert spk_map["speaker_female_1"] != spk_map["speaker_female_2"], "Female speakers must receive distinct voices"


def test_80_cue_locked_timing_propagation(tmp_path):
    """Runner forwards cue_locked_timing to synthesis and sets cue_locked_timing=True on chunks."""
    async def _run():
        source_media = _create_real_valid_mp4(tmp_path / "source.mp4")
        output_mp4 = tmp_path / "output.mp4"
        cues = [
            {"cue_id": "c1", "speaker_id": "spk_1", "text": "Xin chào", "start_ms": 0, "end_ms": 1000},
            {"cue_id": "c2", "speaker_id": "spk_2", "text": "Tạm biệt", "start_ms": 1500, "end_ms": 3000},
        ]
        observed_call_kw = {}

        async def spy_synth(cues, speaker_voice_map, **kwargs):
            observed_call_kw.update(kwargs)
            return [
                {"cue_id": "c1", "audio": b"audio_c1", "cue_locked_timing": True},
                {"cue_id": "c2", "audio": b"audio_c2", "cue_locked_timing": True},
            ]

        async def mock_render(source_media, output_path, **kwargs):
            tts_chunks = kwargs.get("tts_chunks") or []
            assert all(ch.get("cue_locked_timing") is True for ch in tts_chunks), "All tts_chunks must have cue_locked_timing=True"
            return _create_real_valid_mp4(Path(output_path))

        res = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools=TEST_POOLS,
            synthesize_segments=spy_synth,
            render_pipeline=mock_render,
        )
        assert res["ok"] is True
        assert observed_call_kw.get("cue_locked_timing") is True, "synthesize_segments must receive cue_locked_timing=True"

    asyncio.run(_run())


