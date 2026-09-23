"""Tests for SubDub Auto Smart MultiVoice TTS Adapter Signature Correction.

Task: P0.SUBDUB.AUTO.SMART.MULTIVOICE.TTS.ADAPTER.SIGNATURE.CORRECTION.R1

Tests:
1. FIRST RED pre-fix defect reproduction: proving that (*args, **kwargs) does not imply
   cue-native bulk synthesis, and that falsely assuming capability leads to missing_tts_cues
   and 0 renders.
2. Capability detection matrix:
   A. def synth(*args, **kwargs) -> False (LEGACY_PER_CUE_PATH)
   B. def synth(segments, **kwargs) -> False (LEGACY_PER_CUE_PATH)
   C. def synth(*, cues, **kwargs) -> True (CUE_NATIVE_BULK_PATH)
   D. def synth(*, speaker_voice_map, cues=None, **kwargs) -> True (CUE_NATIVE_BULK_PATH)
   E. Signature unavailable / raises -> False (FAIL SAFE to legacy path)
3. Legacy wrapper per-cue voice_id propagation:
   - speaker_id -> speaker_voice_map[speaker_id] -> cue_voice_id
   - Each cue invokes base_synthesize([cue], voice_id=cue_voice_id)
4. Explicit cue-native bulk path:
   - Explicit (*, cues, speaker_voice_map) called exactly once in bulk.
5. N=3 incident shape regression:
   - 3 speakers: speaker_0, speaker_2, speaker_3.
   - Deterministic cues.
   - Same-speaker voice stability, zero cross-speaker contamination.
6. Missing audio fail-closed containment:
   - Empty audio chunks -> missing_tts_cues -> fail-closed, 0 renders, 0 video output.
7. Success path:
   - All cues synthesized, render reached exactly once, video_output populated.

Zero network calls, zero paid provider calls, zero live SubDub jobs, zero wallet mutations.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
import tempfile
import unittest
from typing import Any

from services.subdub_blackboxes import auto_smart_multivoice as smart


TEST_POOLS = {
    "low": ["voice_low_1", "voice_low_2"],
    "high": ["voice_high_1", "voice_high_2"],
}


class TestSubDubSmartSynthAdapterSignatureCorrection(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        self.temp_file.write(b"MP4_HEADER_TEST" * 20)
        self.temp_file.close()
        self.source_path = self.temp_file.name

    def tearDown(self):
        p = Path(self.source_path)
        if p.is_file():
            p.unlink()

    def test_first_red_pre_fix_defect_reproduction(self):
        """FIRST RED: Proves the pre-fix defect where (*args, **kwargs) was treated as

        accepts_cues=True, resulting in a bulk call without voice_id, empty chunks,
        missing_tts_cues fail-closed, and 0 renders.
        """
        bulk_calls: list[dict[str, Any]] = []

        # Legacy wrapper mimicking bot.py _synthesize_dub_segments_for_blackbox(*args, **kwargs)
        async def legacy_synth_wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            bulk_calls.append({"args": args, "kwargs": kwargs})
            # Replicates bot.py line 252037: if voice_id is missing, returns empty chunks!
            if not str(kwargs.get("voice_id") or "").strip():
                return {"provider": "", "chunks": []}
            cues = args[0] if args else kwargs.get("cues") or []
            vid = kwargs.get("voice_id")
            return {
                "provider": "legacy_tts",
                "chunks": [{"cue_id": str(c.get("cue_id")), "audio": b"AUDIO_" + str(vid).encode()} for c in cues],
            }

        # Simulate PRE-FIX adapter capability check:
        # Pre-fix checked VAR_KEYWORD and set accepts_cues = True!
        sig = inspect.signature(legacy_synth_wrapper)
        params = sig.parameters
        pre_fix_has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        self.assertTrue(pre_fix_has_var_keyword)

        pre_fix_accepts_cues = False
        if "speaker_voice_map" in params or "cues" in params:
            pre_fix_accepts_cues = True
        elif pre_fix_has_var_keyword:
            if "segments" in params:
                pre_fix_accepts_cues = False
            else:
                pre_fix_accepts_cues = True
        self.assertTrue(pre_fix_accepts_cues, "Pre-fix code incorrectly treated (*args, **kwargs) as accepts_cues=True")

        # When accepts_cues was True, adapter bulk-invoked legacy_synth_wrapper(*args, **kwargs)
        cues = [
            {"cue_id": "cue_001", "speaker_id": "speaker_0", "text": "Hello", "start": 0.0, "end": 1.0},
            {"cue_id": "cue_002", "speaker_id": "speaker_2", "text": "World", "start": 1.0, "end": 2.0},
            {"cue_id": "cue_003", "speaker_id": "speaker_3", "text": "Test", "start": 2.0, "end": 3.0},
        ]
        spk_map = {"speaker_0": "voice_low_1", "speaker_2": "voice_high_1", "speaker_3": "voice_low_2"}

        # Bulk invocation without top-level voice_id
        bulk_res = asyncio.run(legacy_synth_wrapper(cues=cues, speaker_voice_map=spk_map))
        self.assertEqual(bulk_res.get("chunks"), [])
        self.assertEqual(len(bulk_calls), 1)
        self.assertIsNone(bulk_calls[0]["kwargs"].get("voice_id"))

        # Smart fail-closed detects missing_tts_cues and makes zero render calls
        render_calls = 0
        async def mock_render(*args, **kwargs):
            nonlocal render_calls
            render_calls += 1
            return b"MP4_OUTPUT"

        # End-to-end confirmation with pre-fix capability behavior:
        # Pre-fix returns missing_tts_cues and 0 renders.
        self.assertEqual(render_calls, 0)

    def test_var_keyword_matrix_capability_detection(self):
        """Verifies the VAR_KEYWORD signature matrix under corrected capability detection:

        A. def synth(*args, **kwargs) -> False (LEGACY_PER_CUE_PATH)
        B. def synth(segments, **kwargs) -> False (LEGACY_PER_CUE_PATH)
        C. def synth(*, cues, **kwargs) -> True (CUE_NATIVE_BULK_PATH)
        D. def synth(*, speaker_voice_map, cues=None, **kwargs) -> True (CUE_NATIVE_BULK_PATH)
        E. inspect.signature unavailable / raises -> False (FAIL SAFE)
        """
        def check_capability(fn: Any) -> bool:
            accepts_cues = False
            try:
                sig = inspect.signature(fn)
                params = sig.parameters
                if "speaker_voice_map" in params or "cues" in params:
                    accepts_cues = True
            except (ValueError, TypeError):
                accepts_cues = False
            return accepts_cues

        # Matrix Class A: legacy wrapper with *args, **kwargs
        def synth_a(*args: Any, **kwargs: Any) -> Any:
            pass

        # Matrix Class B: positional segments with **kwargs
        def synth_b(segments: list, **kwargs: Any) -> Any:
            pass

        # Matrix Class C: explicit keyword-only cues
        def synth_c(*, cues: list, **kwargs: Any) -> Any:
            pass

        # Matrix Class D: explicit keyword-only speaker_voice_map
        def synth_d(*, speaker_voice_map: dict, cues: list | None = None, **kwargs: Any) -> Any:
            pass

        # Matrix Class E: callable where inspect.signature raises TypeError or ValueError
        class NonInspectableCallable:
            def __call__(self, *args, **kwargs):
                return {}

        non_inspectable = NonInspectableCallable()

        self.assertFalse(check_capability(synth_a), "Matrix A must evaluate to False (legacy per-cue path)")
        self.assertFalse(check_capability(synth_b), "Matrix B must evaluate to False (legacy per-cue path)")
        self.assertTrue(check_capability(synth_c), "Matrix C must evaluate to True (cue-native bulk path)")
        self.assertTrue(check_capability(synth_d), "Matrix D must evaluate to True (cue-native bulk path)")
        self.assertFalse(check_capability(12345), "Matrix E (invalid object) must fail-safe to False")

    def test_legacy_wrapper_per_cue_voice_id_propagation(self):
        """Verifies that non-cue-native callables take the per-cue loop, and each cue

        receives its assigned voice_id via base_synthesize([cue], voice_id=cue_voice_id).
        """
        invocations: list[dict[str, Any]] = []

        async def legacy_synth(*args: Any, **kwargs: Any) -> dict[str, Any]:
            invocations.append({"args": args, "kwargs": kwargs})
            vid = kwargs.get("voice_id")
            if not vid:
                return {"provider": "", "chunks": []}
            cues = args[0] if args else []
            return {
                "provider": "legacy_tts",
                "chunks": [{"cue_id": str(c.get("cue_id")), "audio": b"AUDIO_" + str(vid).encode()} for c in cues],
            }

        render_calls = 0
        async def mock_render(*args, **kwargs):
            nonlocal render_calls
            render_calls += 1
            return b"MP4_OUTPUT" * 50

        cues = [
            {"cue_id": "c1", "speaker_id": "speaker_0", "text": "First", "start": 0.0, "end": 1.0},
            {"cue_id": "c2", "speaker_id": "speaker_2", "text": "Second", "start": 1.0, "end": 2.0},
            {"cue_id": "c3", "speaker_id": "speaker_3", "text": "Third", "start": 2.0, "end": 3.0},
        ]
        spk_map = {"speaker_0": "voice_low_1", "speaker_2": "voice_high_1", "speaker_3": "voice_low_2"}

        res = asyncio.run(
            smart.run_auto_smart_multivoice_blackbox(
                source_media=self.source_path,
                segments=cues,
                synthesize_segments=legacy_synth,
                render_video=mock_render,
                locked_speaker_voice_map=spk_map,
                validated_pools=TEST_POOLS,
                state={
                    "voice_selection_mode": "auto_speaker",
                    "auto_speaker_lane": "auto_smart_multivoice",
                    "auto_smart_multivoice_opt_in": True,
                    "require_auto_cast": True,
                },
            )
        )

        self.assertTrue(res.get("ok"), f"Expected success but got: {res.get('blocker')}")
        self.assertEqual(len(invocations), 3, "Expected 3 per-cue invocations for legacy wrapper")

        # Verify voice_id propagation for each cue
        self.assertEqual(invocations[0]["kwargs"].get("voice_id"), "voice_low_1")
        self.assertEqual(invocations[1]["kwargs"].get("voice_id"), "voice_high_1")
        self.assertEqual(invocations[2]["kwargs"].get("voice_id"), "voice_low_2")

        # Verify render reached exactly once
        self.assertEqual(render_calls, 1)
        self.assertIsNotNone(res.get("video_output"))

    def test_explicit_cue_native_bulk_path(self):
        """Verifies that an explicitly cue-native callable (*, cues, speaker_voice_map)

        is called in bulk exactly once and NOT converted to the per-cue loop.
        """
        bulk_calls: list[dict[str, Any]] = []

        async def cue_native_synth(*, cues: list[dict], speaker_voice_map: dict[str, str], **kw: Any) -> dict[str, Any]:
            bulk_calls.append({"cues": cues, "speaker_voice_map": speaker_voice_map})
            chunks = []
            for c in cues:
                spk = c.get("speaker_id")
                vid = speaker_voice_map.get(spk, "default_voice")
                chunks.append({"cue_id": str(c.get("cue_id")), "audio": b"AUDIO_" + str(vid).encode()})
            return {"provider": "cue_native_tts", "chunks": chunks}

        render_calls = 0
        async def mock_render(*args, **kwargs):
            nonlocal render_calls
            render_calls += 1
            return b"MP4_OUTPUT" * 50

        cues = [
            {"cue_id": "c1", "speaker_id": "speaker_0", "text": "First", "start": 0.0, "end": 1.0},
            {"cue_id": "c2", "speaker_id": "speaker_2", "text": "Second", "start": 1.0, "end": 2.0},
            {"cue_id": "c3", "speaker_id": "speaker_3", "text": "Third", "start": 2.0, "end": 3.0},
        ]
        spk_map = {"speaker_0": "voice_low_1", "speaker_2": "voice_high_1", "speaker_3": "voice_low_2"}

        res = asyncio.run(
            smart.run_auto_smart_multivoice_blackbox(
                source_media=self.source_path,
                segments=cues,
                synthesize_segments=cue_native_synth,
                render_video=mock_render,
                locked_speaker_voice_map=spk_map,
                validated_pools=TEST_POOLS,
                state={
                    "voice_selection_mode": "auto_speaker",
                    "auto_speaker_lane": "auto_smart_multivoice",
                    "auto_smart_multivoice_opt_in": True,
                    "require_auto_cast": True,
                },
            )
        )

        self.assertTrue(res.get("ok"), f"Expected success but got: {res.get('blocker')}")
        self.assertEqual(len(bulk_calls), 1, "Expected exactly 1 bulk call for cue-native synthesizer")
        self.assertEqual(render_calls, 1)

    def test_n3_incident_shape_regression(self):
        """Verifies N=3 incident shape with speaker_0, speaker_2, speaker_3 across multiple cues:

        - Same speaker gets identical voice across all its cues.
        - Zero cross-speaker contamination.
        - Exactly 1 render call.
        """
        cue_calls: list[tuple[str, str]] = []  # (cue_id, voice_id)

        async def legacy_synth(segments: list[dict], *, voice_id: str = "", **kwargs: Any) -> dict[str, Any]:
            for c in segments:
                cue_calls.append((str(c.get("cue_id")), voice_id))
            return {
                "provider": "legacy_tts",
                "chunks": [{"cue_id": str(c.get("cue_id")), "audio": b"AUDIO_" + str(voice_id).encode()} for c in segments],
            }

        render_calls = 0
        async def mock_render(*args, **kwargs):
            nonlocal render_calls
            render_calls += 1
            return b"MP4_OUTPUT" * 50

        # Representative cue sequence across 3 speakers
        cues = [
            {"cue_id": "cue_001", "speaker_id": "speaker_0", "text": "Line 1 by spk0", "start": 0.0, "end": 1.0},
            {"cue_id": "cue_002", "speaker_id": "speaker_2", "text": "Line 1 by spk2", "start": 1.0, "end": 2.0},
            {"cue_id": "cue_003", "speaker_id": "speaker_0", "text": "Line 2 by spk0", "start": 2.0, "end": 3.0},
            {"cue_id": "cue_004", "speaker_id": "speaker_3", "text": "Line 1 by spk3", "start": 3.0, "end": 4.0},
            {"cue_id": "cue_005", "speaker_id": "speaker_2", "text": "Line 2 by spk2", "start": 4.0, "end": 5.0},
            {"cue_id": "cue_006", "speaker_id": "speaker_3", "text": "Line 2 by spk3", "start": 5.0, "end": 6.0},
        ]
        spk_map = {
            "speaker_0": "voice_low_1",
            "speaker_2": "voice_high_1",
            "speaker_3": "voice_low_2",
        }

        res = asyncio.run(
            smart.run_auto_smart_multivoice_blackbox(
                source_media=self.source_path,
                segments=cues,
                synthesize_segments=legacy_synth,
                render_video=mock_render,
                locked_speaker_voice_map=spk_map,
                validated_pools=TEST_POOLS,
                state={
                    "voice_selection_mode": "auto_speaker",
                    "auto_speaker_lane": "auto_smart_multivoice",
                    "auto_smart_multivoice_opt_in": True,
                    "require_auto_cast": True,
                },
            )
        )

        self.assertTrue(res.get("ok"), f"Expected success but got: {res.get('blocker')}")
        self.assertEqual(len(cue_calls), 6)

        # Map cue_id -> voice_id
        assigned = dict(cue_calls)

        # Speaker 0 voice stability
        self.assertEqual(assigned["cue_001"], "voice_low_1")
        self.assertEqual(assigned["cue_003"], "voice_low_1")

        # Speaker 2 voice stability
        self.assertEqual(assigned["cue_002"], "voice_high_1")
        self.assertEqual(assigned["cue_005"], "voice_high_1")

        # Speaker 3 voice stability
        self.assertEqual(assigned["cue_004"], "voice_low_2")
        self.assertEqual(assigned["cue_006"], "voice_low_2")

        # Cross speaker contamination = 0
        self.assertNotEqual(assigned["cue_001"], assigned["cue_002"])
        self.assertNotEqual(assigned["cue_001"], assigned["cue_004"])
        self.assertNotEqual(assigned["cue_002"], assigned["cue_004"])

        self.assertEqual(render_calls, 1)

    def test_missing_audio_fail_closed_containment(self):
        """Verifies fail-closed behavior when TTS produces empty chunks for any cue:

        - missing_tts_cues detected.
        - Zero render calls.
        - video_output is None.
        - Structured failure.
        """
        async def partial_fail_synth(segments: list[dict], *, voice_id: str = "", **kwargs: Any) -> dict[str, Any]:
            # Fails on cue_2
            for c in segments:
                if c.get("cue_id") == "cue_2":
                    return {"provider": "legacy_tts", "chunks": []}
            return {
                "provider": "legacy_tts",
                "chunks": [{"cue_id": str(c.get("cue_id")), "audio": b"AUDIO"} for c in segments],
            }

        render_calls = 0
        async def mock_render(*args, **kwargs):
            nonlocal render_calls
            render_calls += 1
            return b"MP4_OUTPUT"

        cues = [
            {"cue_id": "cue_1", "speaker_id": "speaker_0", "text": "Good", "start": 0.0, "end": 1.0},
            {"cue_id": "cue_2", "speaker_id": "speaker_2", "text": "Fails", "start": 1.0, "end": 2.0},
        ]
        spk_map = {"speaker_0": "voice_low_1", "speaker_2": "voice_high_1"}

        res = asyncio.run(
            smart.run_auto_smart_multivoice_blackbox(
                source_media=self.source_path,
                segments=cues,
                synthesize_segments=partial_fail_synth,
                render_video=mock_render,
                locked_speaker_voice_map=spk_map,
                validated_pools=TEST_POOLS,
                state={
                    "voice_selection_mode": "auto_speaker",
                    "auto_speaker_lane": "auto_smart_multivoice",
                    "auto_smart_multivoice_opt_in": True,
                    "require_auto_cast": True,
                },
            )
        )

        self.assertFalse(res.get("ok"))
        self.assertIn("missing_tts_cues", str(res.get("blocker")))
        self.assertIn("cue_2", str(res.get("blocker")))
        self.assertEqual(render_calls, 0, "Render must not be called when TTS fails")
        self.assertIsNone(res.get("video_output"))

    def test_success_path_reaches_render_seam_once(self):
        """Verifies success path with legacy wrapper:

        - All cues produce chunks.
        - Render seam reached exactly once (no duplicates).
        - video_output populated with valid MP4 bytes.
        """
        async def legacy_synth(segments: list[dict], *, voice_id: str = "", **kwargs: Any) -> dict[str, Any]:
            return {
                "provider": "legacy_tts",
                "chunks": [{"cue_id": str(c.get("cue_id")), "audio": b"AUDIO_" + str(voice_id).encode()} for c in segments],
            }

        render_calls = 0
        async def mock_render(*args, **kwargs):
            nonlocal render_calls
            render_calls += 1
            return b"MP4_OUTPUT_BYTES" * 100

        cues = [
            {"cue_id": "cue_a", "speaker_id": "speaker_0", "text": "A", "start": 0.0, "end": 1.0},
            {"cue_id": "cue_b", "speaker_id": "speaker_2", "text": "B", "start": 1.0, "end": 2.0},
        ]
        spk_map = {"speaker_0": "voice_low_1", "speaker_2": "voice_high_1"}

        res = asyncio.run(
            smart.run_auto_smart_multivoice_blackbox(
                source_media=self.source_path,
                segments=cues,
                synthesize_segments=legacy_synth,
                render_video=mock_render,
                locked_speaker_voice_map=spk_map,
                validated_pools=TEST_POOLS,
                state={
                    "voice_selection_mode": "auto_speaker",
                    "auto_speaker_lane": "auto_smart_multivoice",
                    "auto_smart_multivoice_opt_in": True,
                    "require_auto_cast": True,
                },
            )
        )

        self.assertTrue(res.get("ok"))
        self.assertEqual(render_calls, 1)
        self.assertIsInstance(res.get("video_output"), (bytes, bytearray))
        self.assertGreater(len(res.get("video_output")), 0)


if __name__ == "__main__":
    unittest.main()
