from __future__ import annotations

import asyncio

from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_smart_multivoice as smart


TEST_POOLS = {
    "low": ["voice_male_1", "voice_male_2"],
    "high": ["voice_female_1", "voice_female_2"],
}


def test_c580_runner_preserves_n3_cast_failure_provenance(tmp_path, monkeypatch):
    """Strict N>=3 failure keeps count, stage, and unresolved speaker."""

    async def _run():
        source_media = tmp_path / "c580_source.mp4"
        source_media.write_bytes(b"c580-source-boundary")
        pcm_path = tmp_path / "c580_stereo.pcm"
        pcm_path.write_bytes(b"\x01\x00\x01\x00" * 8)
        cues = [
            {
                "cue_id": "c1",
                "speaker_id": "chunk_00:speaker_0",
                "text": "one",
                "start_ms": 0,
                "end_ms": 1000,
            },
            {
                "cue_id": "c2",
                "speaker_id": "chunk_00:speaker_1",
                "text": "two",
                "start_ms": 1100,
                "end_ms": 2100,
            },
            {
                "cue_id": "c3",
                "speaker_id": "chunk_00:speaker_2",
                "text": "three",
                "start_ms": 2200,
                "end_ms": 3200,
            },
        ]
        ranges = {
            "chunk_00:speaker_0": [(0.0, 1.0)],
            "chunk_00:speaker_1": [(1.1, 2.1)],
            "chunk_00:speaker_2": [(2.2, 3.2)],
        }

        def classifier(*_args, **_kwargs):
            raise speaker_cast.AutoCastManualRequired()

        monkeypatch.setattr(
            smart,
            "estimate_speaker_pitches_from_pcm",
            lambda *_args, **_kwargs: {
                "chunk_00:speaker_0": {
                    "voice_register": "high",
                    "confidence": 0.82,
                },
                "chunk_00:speaker_1": {
                    "voice_register": "high",
                    "confidence": 0.79,
                },
                "chunk_00:speaker_2": {
                    "voice_register": "unknown",
                    "confidence": 0.80,
                },
            },
        )

        result = await smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=tmp_path / "unused.mp4",
            validated_pools=TEST_POOLS,
            stereo_pcm_path=pcm_path,
            ranges_by_speaker=ranges,
            multi_speaker_classifier=classifier,
        )

        assert result["ok"] is False
        assert result["blocker"] == speaker_cast.AUTO_CAST_MANUAL_REQUIRED
        assert result["failure_stage"] == "auto_cast"
        assert result["detected_speaker_count"] == 3
        assert result["classifier_error_reason"] == speaker_cast.AUTO_CAST_MANUAL_REQUIRED
        assert result["unresolved_speaker_ids"] == ["chunk_00:speaker_2"]
        assert result["fallback_reason"] == (
            "CLASSIFIER_UNAVAILABLE:N3_AUTO_CAST_UNRESOLVED:"
            "classifier=AUTO_CAST_MANUAL_REQUIRED;"
            "pitch_unresolved=chunk_00:speaker_2"
        )

    asyncio.run(_run())
