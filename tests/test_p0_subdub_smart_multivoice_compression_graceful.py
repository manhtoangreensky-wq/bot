"""Unit test for Smart MultiVoice compression graceful degradation.

Ensures:
1. MAX_INTELLIGIBLE_FIT_RATIO is unchanged (1.80).
2. HARD_CAP_FIT_RATIO (5.0) and MAX_OVERFIT_CUE_RATIO (0.30) are correctly defined.
3. Cues with fit_ratio between 1.8 and 5.0 gracefully degrade when <= 30% of total cues.
4. Jobs fail with extreme_audio_compression_unintelligible if any cue exceeds HARD_CAP_FIT_RATIO (5.0).
5. Jobs fail if > 30% of cues exceed MAX_INTELLIGIBLE_FIT_RATIO.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

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


def test_bb7bf97d7c_shape_reaches_production_render(tmp_path):
    """Replay the measured 12/71 compression shape through the production runner."""
    measured_overfit = [
        (0.400, 1.730312),
        (0.960, 2.678562),
        (1.040, 2.473250),
        (1.735, 3.967594),
        (1.520, 3.470125),
        (0.640, 1.448469),
        (3.600, 7.619250),
        (2.000, 3.938813),
        (0.480, 0.914906),
        (0.400, 0.753938),
        (0.720, 1.318156),
        (2.796, 5.0650625),
    ]

    cues = []
    durations = {}
    cursor = 0.0
    for index in range(71):
        if index < len(measured_overfit):
            window, duration = measured_overfit[index]
        else:
            window, duration = 2.0, 2.0
        cue_id = f"cue-{index + 1:04d}"
        speaker_id = f"speaker_{index % 3}"
        cues.append(
            {
                "cue_id": cue_id,
                "speaker_id": speaker_id,
                "text": f"cue {index + 1}",
                "start_ms": round(cursor * 1000),
                "end_ms": round((cursor + window) * 1000),
            }
        )
        durations[cue_id] = duration
        cursor += window + 1.0  # Keep recovery from changing the measured ratio set.

    source_media = tmp_path / "bb7bf97d7c-source.mp4"
    source_media.write_bytes(b"source")
    output_mp4 = tmp_path / "bb7bf97d7c-output.mp4"
    render_calls = []

    async def synthesize(cues, speaker_voice_map, **kwargs):
        del speaker_voice_map, kwargs
        return [
            {
                "cue_id": cue["cue_id"],
                "audio": b"audio",
                "audio_duration": durations[cue["cue_id"]],
            }
            for cue in cues
        ]

    async def render(**kwargs):
        render_calls.append(kwargs)
        Path(kwargs["output_path"]).write_bytes(
            b"0" * (smart.video_local_validation.MIN_OUTPUT_BYTES + 1)
        )
        return kwargs["output_path"]

    result = asyncio.run(
        smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools={
                "low": ["low_1", "low_2", "low_3"],
                "high": ["high_1", "high_2", "high_3"],
            },
            acoustic_classifications={
                "speaker_0": {"voice_register": "high", "confidence": 0.999966},
                "speaker_1": {"voice_register": "low", "confidence": 0.994067},
                "speaker_2": {"voice_register": "low", "confidence": 0.999731},
            },
            synthesize_segments=synthesize,
            render_pipeline=render,
            probe_fn=lambda path: {"ok": Path(path).is_file()},
        )
    )

    assert len(measured_overfit) / len(cues) == pytest.approx(12 / 71)
    assert round(max(duration / window for window, duration in measured_overfit), 3) == 4.326
    assert result["ok"] is True, result
    assert result["blocker"] is None
    assert len(render_calls) == 1
    assert len(render_calls[0]["tts_chunks"]) == 71


def test_arbitrary_renderer_cannot_bypass_smart_compression_gate(tmp_path):
    """A callable alone does not prove bounded scheduling or valid MP4 output."""
    cues = []
    durations = {}
    for index in range(25):
        start = float(index * 3)
        cue_id = f"cue-{index:04d}"
        cues.append({
            "cue_id": cue_id,
            "speaker_id": f"speaker_{index % 5}",
            "text": f"cue {index}",
            "start_ms": int(start * 1000),
            "end_ms": int((start + 1.0) * 1000),
        })
        durations[cue_id] = 2.5 if index < 16 else 1.0

    source_media = tmp_path / "smart-fit-source.mp4"
    source_media.write_bytes(b"source")
    output_mp4 = tmp_path / "smart-fit-output.mp4"
    render_calls = []

    async def synthesize(cues, speaker_voice_map, **kwargs):
        del speaker_voice_map, kwargs
        return [
            {"cue_id": cue["cue_id"], "audio": b"audio", "audio_duration": durations[cue["cue_id"]]}
            for cue in cues
        ]

    async def render(**kwargs):
        render_calls.append(kwargs)
        Path(kwargs["output_path"]).write_bytes(
            b"0" * (smart.video_local_validation.MIN_OUTPUT_BYTES + 1)
        )
        return kwargs["output_path"]

    result = asyncio.run(
        smart.run_auto_smart_multivoice(
            source_media=source_media,
            segments=cues,
            output_path=output_mp4,
            validated_pools={"low": [f"low_{i}" for i in range(8)], "high": [f"high_{i}" for i in range(8)]},
            acoustic_classifications={
                f"speaker_{i}": {"voice_register": "high" if i == 0 else "low", "confidence": 0.99}
                for i in range(5)
            },
            synthesize_segments=synthesize,
            render_pipeline=render,
            probe_fn=lambda path: {"ok": Path(path).is_file()},
        )
    )

    assert result["ok"] is False, result
    assert result["error_code"] == "extreme_audio_compression_unintelligible"
    assert not render_calls
    assert not output_mp4.exists()
