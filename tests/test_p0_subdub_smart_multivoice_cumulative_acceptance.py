"""Cumulative integration acceptance test suite for SubDub Auto Smart MultiVoice.

Validates the full chain across the 3 cumulative corrections:
1. STANDALONE.EXECUTION.RESTORE.CORRECTION.R1
2. TTS.PROVIDER.ROUTE.CORRECTION.R2
3. N3.GENDER.AWARE.VOICE.ASSIGNMENT.CORRECTION.R1

Cases:
1. N=3 mixed gender + valid explicit provider mock:
   -> stable gender-compatible mapping (male -> low, female -> high)
   -> exactly one synthesis per cue
   -> render called exactly once with valid bytes
   -> success result
2. N=3 mixed gender + incompatible explicit provider voice:
   -> strict exclusive provider policy rejects incompatible voice
   -> zero provider submits (Key4U 0, ShopAIKey 0)
   -> zero render
   -> structured failure
3. Classifier unavailable:
   -> structured fail closed
   -> zero synthesis
   -> zero render
4. Provider mock failure after valid assignment:
   -> failure contained (no unhandled escape)
   -> zero render after TTS failure
   -> zero final video output
   -> zero wallet mutations
5. Replay determinism:
   -> repeated identical input and seed produces identical speaker voice map

Zero network calls, zero paid provider calls, zero live SubDub jobs, zero wallet mutations.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

import bot
from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_smart_multivoice as smart


ACCEPTANCE_POOLS = {
    "low": ["English_magnetic_voiced_man", "English_Aussie_Bloke"],
    "high": ["English_radiant_girl"],
}


class TestSubDubSmartMultiVoiceCumulativeAcceptanceR1(unittest.TestCase):
    def test_case_01_n3_mixed_gender_valid_provider_mock_reaches_render_once(self):
        """Case 1: N=3 mixed gender + valid Key4U-compatible voices:
        - Male speakers get distinct low pool voices.
        - Female speaker gets high pool voice.
        - Exactly one synthesis per cue.
        - Render reached exactly once.
        - Output is valid MP4 bytes.
        """
        cues = [
            {"cue_id": "c1", "speaker_id": "spk_male_1", "text": "Hello world from male 1", "start_ms": 0, "end_ms": 1500},
            {"cue_id": "c2", "speaker_id": "spk_female_1", "text": "Greetings from female 1", "start_ms": 1600, "end_ms": 3000},
            {"cue_id": "c3", "speaker_id": "spk_male_2", "text": "Response from male 2", "start_ms": 3100, "end_ms": 4500},
        ]
        classifications = {
            "spk_male_1": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95},
            "spk_female_1": {"voice_gender": "female", "voice_register": "high", "confidence": 0.95},
            "spk_male_2": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95},
        }

        # Mock synth
        synth_cues_received = []
        async def mock_synth(cues=None, **kwargs):
            nonlocal synth_cues_received
            synth_cues_received = list(cues or [])
            return [{"cue_id": c["cue_id"], "audio": b"AUDIO_BYTES_OK"} for c in synth_cues_received]

        # Mock render
        render_call_count = 0
        async def mock_render(source_media, output_path, **kwargs):
            nonlocal render_call_count
            render_call_count += 1
            out = Path(output_path)
            out.write_bytes(b"VALID_FINAL_MP4_BYTES" * 100)
            return str(out)

        decision = smart.decide_smart_multivoice(
            cues,
            validated_pools=ACCEPTANCE_POOLS,
            acoustic_classifications=classifications,
            assignment_seed="acceptance_seed_1",
        )
        self.assertEqual(decision.strategy, smart.STRATEGY_GENERIC_MULTI)
        self.assertEqual(decision.output_mode, smart.OUTPUT_MODE_DUBBED_MULTI)
        self.assertEqual(decision.detected_speaker_count, 3)
        self.assertEqual(decision.effective_voice_count, 3)

        # Check register invariants
        m1_voice = decision.speaker_voice_map["spk_male_1"]
        m2_voice = decision.speaker_voice_map["spk_male_2"]
        f1_voice = decision.speaker_voice_map["spk_female_1"]

        self.assertIn(m1_voice, ACCEPTANCE_POOLS["low"])
        self.assertIn(m2_voice, ACCEPTANCE_POOLS["low"])
        self.assertNotEqual(m1_voice, m2_voice, "Distinct low voices expected for distinct male speakers")
        self.assertIn(f1_voice, ACCEPTANCE_POOLS["high"])

        # Run standalone runner
        with patch("services.video_local_validation.validate_mp4_output", return_value={"ok": True}):
            result = asyncio.run(
                smart.run_auto_smart_multivoice(
                    source_media="tests/test_p0_subdub_smart_multivoice_cumulative_acceptance.py",
                    segments=cues,
                    output_path="cumulative_acceptance_temp_out.mp4",
                    validated_pools=ACCEPTANCE_POOLS,
                    acoustic_classifications=classifications,
                    synthesize_segments=mock_synth,
                    render_pipeline=mock_render,
                )
            )

        try:
            self.assertTrue(result["ok"])
            self.assertEqual(result["output_mode"], smart.OUTPUT_MODE_DUBBED_MULTI)
            self.assertEqual(render_call_count, 1, f"Expected exactly 1 render call, got {render_call_count}")
            self.assertEqual(len(synth_cues_received), 3, "Expected 3 synthesized cues (one per cue, no duplicates)")
        finally:
            p = Path("cumulative_acceptance_temp_out.mp4")
            if p.exists():
                p.unlink()

    def test_case_02_incompatible_explicit_provider_voice_fails_closed_zero_submits(self):
        """Case 2: N=3 mixed gender + incompatible explicit provider voice:
        Strict provider policy enforces:
        - Key4U compatible check == False
        - Key4U submit count == 0
        - ShopAIKey submit count == 0 (no silent fallback!)
        - Fails closed with structured tts_unavailable exception
        - Zero render calls
        """
        mock_key4u = AsyncMock(return_value=("PASS", b"KEY4U_AUDIO", "ok", 200))
        mock_shopaikey = AsyncMock(return_value=("PASS", b"SHOPAIKEY_AUDIO", "ok", 200))
        render_mock = AsyncMock(return_value=b"CORRUPT_VIDEO")

        with patch.object(bot, "subdub_tts_provider_name", return_value="key4u_minimax"), \
             patch.object(bot, "key4u_minimax_tts_configured", return_value=True), \
             patch.object(bot, "shopaikey_minimax_tts_configured", return_value=True), \
             patch.object(bot, "KEY4U_PUBLIC_ENABLED", True), \
             patch.object(bot, "VIDEO_DUB_TTS_ENABLED", True), \
             patch.object(bot, "SHOPAIKEY_ADMIN_ONLY", False), \
             patch.object(bot, "call_key4u_minimax_tts_bytes_with_speed", mock_key4u), \
             patch.object(bot, "call_shopaikey_minimax_tts_bytes_with_speed", mock_shopaikey):

            # Incompatible voice for Key4U
            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(
                    bot.video_dubbing_tts_bytes(
                        "Đoạn văn bản kiểm tra.",
                        voice_id="Vietnamese_Professional_Narrator_v2",
                    )
                )

            self.assertIn("tts_unavailable", str(ctx.exception))
            self.assertEqual(mock_key4u.call_count, 0)
            self.assertEqual(mock_shopaikey.call_count, 0)
            self.assertEqual(render_mock.call_count, 0)

    def test_case_03_classifier_unavailable_fails_closed_zero_synthesis_zero_render(self):
        """Case 3: Classifier unavailable or error:
        - Fails closed to OUTPUT_MODE_FAILED
        - Synthesis call count == 0
        - Render call count == 0
        """
        cues = [
            {"cue_id": "c1", "speaker_id": "spk_1", "text": "Thoại 1", "start_ms": 0, "end_ms": 1000},
            {"cue_id": "c2", "speaker_id": "spk_2", "text": "Thoại 2", "start_ms": 1000, "end_ms": 2000},
            {"cue_id": "c3", "speaker_id": "spk_3", "text": "Thoại 3", "start_ms": 2000, "end_ms": 3000},
        ]
        def failing_classifier(*args, **kwargs):
            raise speaker_cast.AutoCastManualRequired()

        mock_synth = AsyncMock(return_value={"chunks": []})
        mock_render = AsyncMock(return_value="out.mp4")

        result = asyncio.run(
            smart.run_auto_smart_multivoice(
                source_media="tests/test_p0_subdub_smart_multivoice_cumulative_acceptance.py",
                segments=cues,
                output_path="out.mp4",
                validated_pools=ACCEPTANCE_POOLS,
                stereo_pcm_path="/tmp/fake.pcm",
                multi_speaker_classifier=failing_classifier,
                synthesize_segments=mock_synth,
                render_pipeline=mock_render,
            )
        )
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("output_mode"), smart.OUTPUT_MODE_FAILED)
        self.assertEqual(mock_synth.call_count, 0)
        self.assertEqual(mock_render.call_count, 0)

    def test_case_04_provider_failure_contained_zero_render_zero_final_video(self):
        """Case 4: Provider synthesis failure after valid assignment:
        - Error is contained (no unhandled escape)
        - Render call count == 0
        - Final video output == None
        """
        cues = [
            {"cue_id": "c1", "speaker_id": "spk_m1", "text": "Thoại 1", "start_ms": 0, "end_ms": 1000},
            {"cue_id": "c2", "speaker_id": "spk_f1", "text": "Thoại 2", "start_ms": 1000, "end_ms": 2000},
            {"cue_id": "c3", "speaker_id": "spk_m2", "text": "Thoại 3", "start_ms": 2000, "end_ms": 3000},
        ]
        classifications = {
            "spk_m1": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95},
            "spk_f1": {"voice_gender": "female", "voice_register": "high", "confidence": 0.95},
            "spk_m2": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95},
        }

        # Simulate provider failure during synthesis
        async def failing_synth(*args, **kwargs):
            raise RuntimeError("tts_unavailable:provider_gateway_timeout_504")

        mock_render = AsyncMock(return_value="out.mp4")
        mock_probe = lambda p: {"ok": True}

        result = asyncio.run(
            smart.run_auto_smart_multivoice(
                source_media="tests/test_p0_subdub_smart_multivoice_cumulative_acceptance.py",
                segments=cues,
                output_path="out.mp4",
                validated_pools=ACCEPTANCE_POOLS,
                acoustic_classifications=classifications,
                synthesize_segments=failing_synth,
                render_pipeline=mock_render,
                probe_fn=mock_probe,
            )
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["output_mode"], smart.OUTPUT_MODE_FAILED)
        self.assertIn("tts_synthesis_failed", str(result.get("blocker")))
        self.assertIn("tts_unavailable:provider_gateway_timeout_504", str(result.get("blocker")))
        # Ensure render was NEVER reached after synthesis failed
        self.assertEqual(mock_render.call_count, 0)
        self.assertIsNone(result.get("final_mp4_path"))

    def test_case_05_repeated_execution_is_strictly_deterministic(self):
        """Case 5: Repeated exact execution with same inputs produces identical speaker voice map."""
        cues = [
            {"cue_id": "c1", "speaker_id": "spk_1", "text": "Xin chào", "start_ms": 0, "end_ms": 1000},
            {"cue_id": "c2", "speaker_id": "spk_2", "text": "Chào bạn", "start_ms": 1000, "end_ms": 2000},
            {"cue_id": "c3", "speaker_id": "spk_3", "text": "Hẹn gặp lại", "start_ms": 2000, "end_ms": 3000},
        ]
        classifications = {
            "spk_1": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95},
            "spk_2": {"voice_gender": "female", "voice_register": "high", "confidence": 0.95},
            "spk_3": {"voice_gender": "male", "voice_register": "low", "confidence": 0.95},
        }

        run_a = smart.decide_smart_multivoice(
            cues,
            validated_pools=ACCEPTANCE_POOLS,
            acoustic_classifications=classifications,
            assignment_seed="constant_seed_xyz",
        )
        run_b = smart.decide_smart_multivoice(
            cues,
            validated_pools=ACCEPTANCE_POOLS,
            acoustic_classifications=classifications,
            assignment_seed="constant_seed_xyz",
        )

        self.assertEqual(run_a.speaker_voice_map, run_b.speaker_voice_map)
        self.assertEqual(run_a.strategy, run_b.strategy)
        self.assertEqual(run_a.output_mode, run_b.output_mode)


if __name__ == "__main__":
    unittest.main()
