"""Provider-free test suite for P0.SUBDUB.AUTO.SMART.MULTIVOICE.N3.GENDER.AWARE.VOICE.ASSIGNMENT.CORRECTION.R1.

Enforces gender/register-aware voice assignment for Smart MultiVoice (N >= 3 and N >= 1):
- Case 1: 1 male -> low voice
- Case 2: 1 female -> high voice
- Case 3: male + female -> low/high respectively
- Case 4: male + male + female -> two compatible low assignments + one high
- Case 5: female + female + male -> two compatible high assignments + one low
- Case 6: 3+ mixed speakers -> zero cross-register assignment
- Case 7: same speaker across multiple cues -> one stable voice
- Case 8: repeat exact input -> deterministic same mapping
- Case 9: ambiguous classification -> fail closed / manual policy -> no random all-pool voice
- Case 10: classifier unavailable/error -> structured failure -> no render if voice assignment is required
- Case 11: same-register pool capacity exceeded -> canonical bounded behavior -> never opposite-register fallback
- Case 12: TTS route compatibility remains unchanged from R2

Zero network calls, zero paid provider calls, zero render calls.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

import bot
from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_smart_multivoice as smart


TEST_POOLS = {
    "low": ["voice_male_alpha", "voice_male_beta", "voice_male_gamma"],
    "high": ["voice_female_alpha", "voice_female_beta", "voice_female_gamma"],
}


class TestN3GenderAwareVoiceAssignmentR1(unittest.TestCase):
    def test_case_01_single_male_to_low_voice(self):
        """Case 1: 1 male -> low voice."""
        cues = [
            {"cue_id": "c1", "speaker_id": "speaker_m1", "text": "Lời nói nam", "start_ms": 0, "end_ms": 1500},
        ]
        classifications = {
            "speaker_m1": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95},
        }
        decision = smart.decide_smart_multivoice(
            cues,
            validated_pools=TEST_POOLS,
            acoustic_classifications=classifications,
        )
        self.assertEqual(decision.detected_speaker_count, 1)
        self.assertEqual(decision.effective_voice_count, 1)
        self.assertIn(decision.speaker_voice_map["speaker_m1"], TEST_POOLS["low"])

    def test_case_02_single_female_to_high_voice(self):
        """Case 2: 1 female -> high voice."""
        cues = [
            {"cue_id": "c1", "speaker_id": "speaker_f1", "text": "Lời nói nữ", "start_ms": 0, "end_ms": 1500},
        ]
        classifications = {
            "speaker_f1": {"voice_gender": "female", "voice_register": "high", "confidence": 0.95},
        }
        decision = smart.decide_smart_multivoice(
            cues,
            validated_pools=TEST_POOLS,
            acoustic_classifications=classifications,
        )
        self.assertEqual(decision.detected_speaker_count, 1)
        self.assertEqual(decision.effective_voice_count, 1)
        self.assertIn(decision.speaker_voice_map["speaker_f1"], TEST_POOLS["high"])

    def test_case_03_male_and_female_to_low_high_respectively(self):
        """Case 3: male + female -> low/high respectively."""
        cues = [
            {"cue_id": "c1", "speaker_id": "spk_m", "text": "Nam", "start_ms": 0, "end_ms": 1000},
            {"cue_id": "c2", "speaker_id": "spk_f", "text": "Nữ", "start_ms": 1000, "end_ms": 2000},
        ]
        classifications = {
            "spk_m": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95},
            "spk_f": {"voice_gender": "female", "voice_register": "high", "confidence": 0.95},
        }
        decision = smart.decide_smart_multivoice(
            cues,
            validated_pools=TEST_POOLS,
            acoustic_classifications=classifications,
        )
        self.assertEqual(decision.detected_speaker_count, 2)
        self.assertIn(decision.speaker_voice_map["spk_m"], TEST_POOLS["low"])
        self.assertIn(decision.speaker_voice_map["spk_f"], TEST_POOLS["high"])

    def test_case_04_male_male_female_two_low_one_high(self):
        """Case 4: male + male + female (N=3) -> two compatible low assignments + one high."""
        cues = [
            {"cue_id": "c1", "speaker_id": "spk_m1", "text": "Nam 1", "start_ms": 0, "end_ms": 1000},
            {"cue_id": "c2", "speaker_id": "spk_m2", "text": "Nam 2", "start_ms": 1000, "end_ms": 2000},
            {"cue_id": "c3", "speaker_id": "spk_f1", "text": "Nữ 1", "start_ms": 2000, "end_ms": 3000},
        ]
        classifications = {
            "spk_m1": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95},
            "spk_m2": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95},
            "spk_f1": {"voice_gender": "female", "voice_register": "high", "confidence": 0.95},
        }
        decision = smart.decide_smart_multivoice(
            cues,
            validated_pools=TEST_POOLS,
            acoustic_classifications=classifications,
            assignment_seed="fixed_seed_case4",
        )
        self.assertEqual(decision.detected_speaker_count, 3)
        self.assertEqual(decision.output_mode, smart.OUTPUT_MODE_DUBBED_MULTI)
        # Both male speakers must receive LOW pool voices
        self.assertIn(decision.speaker_voice_map["spk_m1"], TEST_POOLS["low"])
        self.assertIn(decision.speaker_voice_map["spk_m2"], TEST_POOLS["low"])
        # Same-gender distinctness
        self.assertNotEqual(decision.speaker_voice_map["spk_m1"], decision.speaker_voice_map["spk_m2"])
        # Female speaker must receive HIGH pool voice
        self.assertIn(decision.speaker_voice_map["spk_f1"], TEST_POOLS["high"])

    def test_case_05_female_female_male_two_high_one_low(self):
        """Case 5: female + female + male (N=3) -> two compatible high assignments + one low."""
        cues = [
            {"cue_id": "c1", "speaker_id": "spk_f1", "text": "Nữ 1", "start_ms": 0, "end_ms": 1000},
            {"cue_id": "c2", "speaker_id": "spk_f2", "text": "Nữ 2", "start_ms": 1000, "end_ms": 2000},
            {"cue_id": "c3", "speaker_id": "spk_m1", "text": "Nam 1", "start_ms": 2000, "end_ms": 3000},
        ]
        classifications = {
            "spk_f1": {"voice_gender": "female", "voice_register": "high", "confidence": 0.95},
            "spk_f2": {"voice_gender": "female", "voice_register": "high", "confidence": 0.95},
            "spk_m1": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95},
        }
        decision = smart.decide_smart_multivoice(
            cues,
            validated_pools=TEST_POOLS,
            acoustic_classifications=classifications,
            assignment_seed="default_smart_seed",
        )
        self.assertEqual(decision.detected_speaker_count, 3)
        self.assertEqual(decision.output_mode, smart.OUTPUT_MODE_DUBBED_MULTI)
        # Both female speakers must receive HIGH pool voices
        self.assertIn(decision.speaker_voice_map["spk_f1"], TEST_POOLS["high"])
        self.assertIn(decision.speaker_voice_map["spk_f2"], TEST_POOLS["high"])
        # Same-gender distinctness
        self.assertNotEqual(decision.speaker_voice_map["spk_f1"], decision.speaker_voice_map["spk_f2"])
        # Male speaker must receive LOW pool voice
        self.assertIn(decision.speaker_voice_map["spk_m1"], TEST_POOLS["low"])

    def test_case_06_three_plus_mixed_speakers_zero_cross_register(self):
        """Case 6: 4 mixed speakers (2 male, 2 female) -> zero cross-register assignment."""
        cues = [
            {"cue_id": "c1", "speaker_id": "m_1", "text": "Nam 1", "start_ms": 0, "end_ms": 1000},
            {"cue_id": "c2", "speaker_id": "f_1", "text": "Nữ 1", "start_ms": 1000, "end_ms": 2000},
            {"cue_id": "c3", "speaker_id": "m_2", "text": "Nam 2", "start_ms": 2000, "end_ms": 3000},
            {"cue_id": "c4", "speaker_id": "f_2", "text": "Nữ 2", "start_ms": 3000, "end_ms": 4000},
        ]
        classifications = {
            "m_1": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95},
            "f_1": {"voice_gender": "female", "voice_register": "high", "confidence": 0.95},
            "m_2": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95},
            "f_2": {"voice_gender": "female", "voice_register": "high", "confidence": 0.95},
        }
        decision = smart.decide_smart_multivoice(
            cues,
            validated_pools=TEST_POOLS,
            acoustic_classifications=classifications,
            assignment_seed="mixed_seed_4spk",
        )
        cross_register_count = 0
        for spk, (expected_reg, _) in [("m_1", ("low", 0)), ("m_2", ("low", 0)), ("f_1", ("high", 0)), ("f_2", ("high", 0))]:
            voice = decision.speaker_voice_map[spk]
            actual_reg = "low" if voice in TEST_POOLS["low"] else ("high" if voice in TEST_POOLS["high"] else "unknown")
            if actual_reg != expected_reg:
                cross_register_count += 1
        self.assertEqual(cross_register_count, 0, f"Expected 0 cross-register assignments, got {cross_register_count}")

    def test_case_07_same_speaker_multiple_cues_one_stable_voice(self):
        """Case 7: same speaker across multiple cues -> one stable voice."""
        cues = [
            {"cue_id": "c1", "speaker_id": "spk_m1", "text": "Câu 1 của M1", "start_ms": 0, "end_ms": 1000},
            {"cue_id": "c2", "speaker_id": "spk_f1", "text": "Câu 1 của F1", "start_ms": 1000, "end_ms": 2000},
            {"cue_id": "c3", "speaker_id": "spk_m1", "text": "Câu 2 của M1", "start_ms": 2000, "end_ms": 3000},
            {"cue_id": "c4", "speaker_id": "spk_m2", "text": "Câu 1 của M2", "start_ms": 3000, "end_ms": 4000},
            {"cue_id": "c5", "speaker_id": "spk_f1", "text": "Câu 2 của F1", "start_ms": 4000, "end_ms": 5000},
        ]
        classifications = {
            "spk_m1": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95},
            "spk_m2": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95},
            "spk_f1": {"voice_gender": "female", "voice_register": "high", "confidence": 0.95},
        }
        decision = smart.decide_smart_multivoice(
            cues,
            validated_pools=TEST_POOLS,
            acoustic_classifications=classifications,
        )
        # Verify cue propagation
        m1_cues = [c["tts_voice_id"] for c in decision.tts_cues if c["speaker_id"] == "spk_m1"]
        f1_cues = [c["tts_voice_id"] for c in decision.tts_cues if c["speaker_id"] == "spk_f1"]
        self.assertEqual(len(set(m1_cues)), 1)
        self.assertEqual(len(set(f1_cues)), 1)
        self.assertEqual(m1_cues[0], decision.speaker_voice_map["spk_m1"])
        self.assertEqual(f1_cues[0], decision.speaker_voice_map["spk_f1"])

    def test_case_08_repeat_exact_input_deterministic_same_mapping(self):
        """Case 8: repeat exact input -> deterministic same mapping."""
        cues = [
            {"cue_id": "c1", "speaker_id": "spk_m1", "text": "A", "start_ms": 0, "end_ms": 1000},
            {"cue_id": "c2", "speaker_id": "spk_m2", "text": "B", "start_ms": 1000, "end_ms": 2000},
            {"cue_id": "c3", "speaker_id": "spk_f1", "text": "C", "start_ms": 2000, "end_ms": 3000},
        ]
        classifications = {
            "spk_m1": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95},
            "spk_m2": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95},
            "spk_f1": {"voice_gender": "female", "voice_register": "high", "confidence": 0.95},
        }
        d1 = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS, acoustic_classifications=classifications, assignment_seed="determinism_seed_777")
        d2 = smart.decide_smart_multivoice(cues, validated_pools=TEST_POOLS, acoustic_classifications=classifications, assignment_seed="determinism_seed_777")
        self.assertEqual(d1.speaker_voice_map, d2.speaker_voice_map)

    def test_case_09_ambiguous_classification_fails_closed(self):
        """Case 9: ambiguous classification (e.g. low confidence < 0.75 or ambiguous label) -> fail closed."""
        cues = [
            {"cue_id": "c1", "speaker_id": "spk_1", "text": "A", "start_ms": 0, "end_ms": 1000},
            {"cue_id": "c2", "speaker_id": "spk_2", "text": "B", "start_ms": 1000, "end_ms": 2000},
            {"cue_id": "c3", "speaker_id": "spk_3", "text": "C", "start_ms": 2000, "end_ms": 3000},
        ]
        ambiguous_classifications = {
            "spk_1": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95},
            "spk_2": {"voice_gender": "ambiguous", "voice_register": "unresolved", "confidence": 0.50},
            "spk_3": {"voice_gender": "female", "voice_register": "high", "confidence": 0.95},
        }
        decision = smart.decide_smart_multivoice(
            cues,
            validated_pools=TEST_POOLS,
            acoustic_classifications=ambiguous_classifications,
        )
        self.assertEqual(decision.output_mode, smart.OUTPUT_MODE_FAILED)
        self.assertEqual(decision.strategy, smart.STRATEGY_FAILED)
        self.assertEqual(decision.tts_cues, [])

    def test_case_10_classifier_unavailable_or_error_fails_closed_no_render(self):
        """Case 10: classifier unavailable or error -> structured failure, no render."""
        cues = [
            {"cue_id": "c1", "speaker_id": "spk_1", "text": "A", "start_ms": 0, "end_ms": 1000},
            {"cue_id": "c2", "speaker_id": "spk_2", "text": "B", "start_ms": 1000, "end_ms": 2000},
            {"cue_id": "c3", "speaker_id": "spk_3", "text": "C", "start_ms": 2000, "end_ms": 3000},
        ]
        def failing_classifier(*args, **kwargs):
            raise speaker_cast.AutoCastManualRequired()

        mock_synth = AsyncMock(return_value={"chunks": []})
        mock_render = AsyncMock(return_value=(b"MP4", "ok"))

        result = asyncio.run(
            smart.run_auto_smart_multivoice(
                source_media="/nonexistent/source.mp4",
                segments=cues,
                output_path="/tmp/output.mp4",
                validated_pools=TEST_POOLS,
                stereo_pcm_path="/tmp/fake.pcm",
                multi_speaker_classifier=failing_classifier,
                synthesize_segments=mock_synth,
                render_pipeline=mock_render,
            )
        )
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("output_mode"), smart.OUTPUT_MODE_FAILED)
        self.assertIsNone(result.get("final_mp4_path"))
        # Verify zero synthesis and zero render calls
        self.assertEqual(mock_synth.call_count, 0)
        self.assertEqual(mock_render.call_count, 0)

    def test_case_11_same_register_pool_capacity_exceeded_fails_closed(self):
        """Case 11: 4 male speakers with only 3 low pool voices -> canonical fail-closed, never opposite-register fallback."""
        cues = [
            {"cue_id": "c1", "speaker_id": "m1", "text": "A", "start_ms": 0, "end_ms": 1000},
            {"cue_id": "c2", "speaker_id": "m2", "text": "B", "start_ms": 1000, "end_ms": 2000},
            {"cue_id": "c3", "speaker_id": "m3", "text": "C", "start_ms": 2000, "end_ms": 3000},
            {"cue_id": "c4", "speaker_id": "m4", "text": "D", "start_ms": 3000, "end_ms": 4000},
        ]
        classifications = {
            f"m{i}": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95}
            for i in range(1, 5)
        }
        # TEST_POOLS only has 3 low voices: male_alpha, male_beta, male_gamma
        decision = smart.decide_smart_multivoice(
            cues,
            validated_pools=TEST_POOLS,
            acoustic_classifications=classifications,
        )
        self.assertEqual(decision.output_mode, smart.OUTPUT_MODE_FAILED)
        self.assertEqual(decision.strategy, smart.STRATEGY_FAILED)
        self.assertEqual(decision.tts_cues, [])
        # None of the male speakers may be assigned a high voice!
        for spk, voice in decision.speaker_voice_map.items():
            self.assertNotIn(voice, TEST_POOLS["high"], f"Male speaker {spk} must NEVER receive high voice {voice}!")

    def test_case_12_tts_route_compatibility_preserved(self):
        """Case 12: TTS route compatibility remains strictly enforced (Key4U incompatible fails closed)."""
        mock_key4u = AsyncMock(return_value=("PASS", b"KEY4U_AUDIO", "ok", 200))
        mock_shopaikey = AsyncMock(return_value=("PASS", b"SHOPAIKEY_AUDIO", "ok", 200))

        with patch.object(bot, "subdub_tts_provider_name", return_value="key4u_minimax"), \
             patch.object(bot, "key4u_minimax_tts_configured", return_value=True), \
             patch.object(bot, "shopaikey_minimax_tts_configured", return_value=True), \
             patch.object(bot, "KEY4U_PUBLIC_ENABLED", True), \
             patch.object(bot, "VIDEO_DUB_TTS_ENABLED", True), \
             patch.object(bot, "SHOPAIKEY_ADMIN_ONLY", False), \
             patch.object(bot, "call_key4u_minimax_tts_bytes_with_speed", mock_key4u), \
             patch.object(bot, "call_shopaikey_minimax_tts_bytes_with_speed", mock_shopaikey):

            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(
                    bot.video_dubbing_tts_bytes(
                        "Test preservation of route R2.",
                        voice_id="Vietnamese_Professional_Narrator_v2",
                    )
                )

            self.assertEqual(mock_key4u.call_count, 0)
            self.assertEqual(mock_shopaikey.call_count, 0)
            self.assertIn("tts_unavailable", str(ctx.exception))

    def test_case_13_smart_multivoice_pipeline_source_override(self):
        """Case 13: _pipeline_source_path_override propagated for auto_smart_multivoice in pipeline state."""
        state = {
            "auto_smart_multivoice": True,
            "input_save": {
                "original_source_path": "/fake/workspace/original.mp4",
                "path": "/fake/workspace/normalized.mp4",
            },
        }
        self.assertTrue(smart.is_auto_smart_multivoice_state(state))
        override = (
            {"_pipeline_source_path_override": str(state["input_save"].get("original_source_path") or state["input_save"].get("path") or "")}
            if smart.is_auto_smart_multivoice_state(state)
            and str(state["input_save"].get("original_source_path") or state["input_save"].get("path") or "")
            else {}
        )
        self.assertEqual(override["_pipeline_source_path_override"], "/fake/workspace/original.mp4")

    def test_case_14_multi_speaker_gender_onnx_dominance_and_confidence(self):
        """Case 14: multi speaker gender onnx accepts 2/3 dominance and calculates confidence."""
        from services import subdub_multi_speaker_gender_onnx as multi_onnx
        self.assertAlmostEqual(multi_onnx.MIN_VOTE_DOMINANCE, 2.0 / 3.0, places=4)
        cues_male_dominant = [
            {"start": 0.0, "end": 1.0, "male_score": 0.8, "female_score": 0.2},
            {"start": 1.5, "end": 2.5, "male_score": 0.9, "female_score": 0.1},
            {"start": 3.0, "end": 4.0, "male_score": 0.3, "female_score": 0.7},
        ]
        res, rows = multi_onnx._aggregate_one_gender_result("spk_test", cues_male_dominant)
        self.assertEqual(res["voice_gender"], "male")
        self.assertEqual(res["voice_register"], "low")
        self.assertGreaterEqual(res["confidence"], 0.75)


if __name__ == "__main__":
    unittest.main()
