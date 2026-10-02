import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from services.subdub_blackboxes import auto_smart_multivoice as smart
from test_p0_subdub_smart_bounded_audio_recovery import _probe, media_bot, timeline_bot
from test_p0_subdub_smart_exact_gate_handoff import _production_gate_with_offline_storage, actual_outer_exact_price_guard
from test_p0_subdub_smart_posttts_mp4_delivery import _outer_audio_guard


POOLS = {"low": ["voice_low_1", "voice_low_2", "voice_low_3"],
         "high": ["voice_high_1", "voice_high_2", "voice_high_3"]}


def _run(tmp_path, *, state=None, pools=None, count=2, locked=None, classes=None):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"contract-only-source")
    cues = [{"cue_id": f"c{i}", "speaker_id": f"chunk_00:speaker_{i}",
             "start": float(i * 2), "end": float(i * 2 + 2), "text": f"full sentence {i}"}
            for i in range(count)]
    observed = {"strict_calls": 0, "chunks": []}

    def strict(*_args, **_kwargs):
        observed["strict_calls"] += 1
        return classes

    async def synthesize(**kwargs):
        observed["chunks"] = kwargs["cues"]
        return [{"cue_id": c["cue_id"], "audio": b"fixture", "audio_duration": 1.0}
                for c in kwargs["cues"]]

    async def render(**kwargs):
        Path(kwargs["output_path"]).write_bytes(b"contract-only-output" * 100)

    result = asyncio.run(smart.run_auto_smart_multivoice(
        source_media=source, segments=cues, output_path=tmp_path / "result.mp4",
        state=state if state is not None else {"auto_speaker_lane": "auto_smart_multivoice", "input_duration": count*2},
        validated_pools=pools if pools is not None else POOLS,
        assignment_seed="same-source-seed", strict_two_classifier=strict,
        acoustic_classifications=classes if count != 2 else None,
        synthesize_segments=synthesize, render_pipeline=render,
        locked_speaker_voice_map=locked, probe_fn=lambda _path: {"ok": True},
    ))
    return result, observed, cues


def test_explicit_smart_n2_uncertainty_uses_existing_two_voice_fallback(tmp_path):
    result, observed, cues = _run(tmp_path)
    assert result["ok"], result
    assert observed["strict_calls"] == 1
    assert result["strategy"] == "STABLE_FALLBACK"
    assert result["fallback_reason"] == "n2_strict_ambiguity_fallback"
    assert result["effective_speaker_count"] == result["effective_voice_count"] == 2
    assert len(set(result["speaker_voice_map"].values())) == 2
    assert [c["cue_id"] for c in observed["chunks"]] == [c["cue_id"] for c in cues]
    assert [c["text"] for c in result["output_segments"]] == [c["text"] for c in cues]


def test_n2_fallback_map_is_identical_for_same_input_and_seed(tmp_path):
    first, _, _ = _run(tmp_path)
    second, _, _ = _run(tmp_path)
    assert first["ok"] and second["ok"]
    assert first["speaker_voice_map"] == second["speaker_voice_map"]


def test_n2_one_voice_pool_discloses_single_effective_voice(tmp_path):
    result, _, _ = _run(tmp_path, pools={"low": ["voice_only"], "high": []})
    assert result["ok"], result
    assert result["effective_speaker_count"] == 2
    assert result["effective_voice_count"] == 1
    assert result["fallback_reason"] == "n2_pool_single_voice_fallback"


@pytest.mark.parametrize("registers", [("low", "high"), ("low", "low"), ("high", "high")])
def test_successful_strict_two_authority_is_not_downgraded(tmp_path, registers):
    classes = {f"chunk_00:speaker_{i}": {"voice_register": r, "confidence": 1.0}
               for i, r in enumerate(registers)}
    result, observed, _ = _run(tmp_path, classes=classes)
    assert result["ok"], result
    assert observed["strict_calls"] == 1
    assert result["strategy"] == "STRICT_TWO"
    assert result["fallback_reason"] is None
    assert result["effective_voice_count"] == 2


def test_state_less_caller_keeps_strict_uncertainty_failure(tmp_path):
    result, observed, _ = _run(tmp_path, state={})
    assert result["ok"] is False
    assert result["blocker"] == "AUTO_CAST_MANUAL_REQUIRED"
    assert not observed["chunks"]


def test_conflicting_locked_map_is_still_fail_closed(tmp_path):
    result, observed, _ = _run(tmp_path, locked={"chunk_00:speaker_0": "voice_low_1"})
    assert result["ok"] is False
    assert "LOCKED_SPEAKER_VOICE_MAP_CONFLICT" in result["blocker"]
    assert not observed["chunks"]


def test_valid_locked_map_remains_unchanged(tmp_path):
    locked = {"chunk_00:speaker_0": "voice_low_1", "chunk_00:speaker_1": "voice_high_1"}
    result, observed, _ = _run(tmp_path, locked=locked)
    assert result["ok"]
    assert result["speaker_voice_map"] == locked
    assert observed["strict_calls"] == 0


@pytest.mark.parametrize("count", [1, 3, 5])
def test_other_proved_speaker_counts_keep_their_voice_count(tmp_path, count):
    classes = {f"chunk_00:speaker_{i}": {"voice_register": "low" if i % 2 else "high", "confidence": 1.0}
               for i in range(count)}
    result, _, _ = _run(tmp_path, count=count, classes=classes)
    assert result["ok"], result
    assert result["effective_speaker_count"] == result["effective_voice_count"] == count


def test_n3_unknown_classification_does_not_gain_n2_blind_fallback(tmp_path):
    result, observed, _ = _run(tmp_path, count=3)
    assert result["ok"] is False
    assert not observed["chunks"]


def test_n2_uncertainty_renders_real_cached_two_voice_mp4(tmp_path, monkeypatch, media_bot):
    roots = [os.environ.get("SMART_TAIL_REPLAY_DIR"), os.environ.get("SMART_POSTTTS_REPLAY_DIR")]
    if not all(roots):
        pytest.skip("two cached voice samples not supplied")
    directories = [Path(roots[0]), Path(roots[1]) / "806a998ec7fa6a3df38f"]
    samples = {}
    for directory in directories:
        manifest = json.loads((directory / "subdub_tts_manifest.json").read_text(encoding="utf-8"))
        entry = min(manifest["entries"].values(), key=lambda e: e["chunks_meta"][0]["index"])
        assert entry["state"] == "SUCCEEDED"
        data = (directory / "tts_artifacts" / Path(entry["artifact_path"]).name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["artifact_sha256"]
        samples[entry["voice_id"]] = {**entry["chunks_meta"][0], "audio_bytes": data}
    assert len(samples) == 2
    texts = {s["text"] for s in samples.values()}
    assert len(texts) == 1  # Same complete utterance, two already-paid distinct voices.
    source = tmp_path / "two-scene-fixture.mp4"
    subprocess.run([
        shutil.which("ffmpeg"), "-y", "-f", "lavfi", "-i", "color=blue:s=320x240:r=25:d=2",
        "-f", "lavfi", "-i", "color=red:s=320x240:r=25:d=2",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[out]", "-map", "[out]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
    ], capture_output=True, check=True)
    cues = [{"cue_id": f"c{i}", "speaker_id": f"chunk_00:speaker_{i}",
             "start": float(i*2), "end": float(i*2+2), "text": next(iter(texts))} for i in range(2)]
    monkeypatch.setitem(sys.modules, "bot", media_bot)
    observed = {"strict": 0, "voices": []}

    def strict(*_args, **_kwargs):
        observed["strict"] += 1
        return None

    async def synthesize(segments, *, voice_id="", **_kwargs):
        observed["voices"].append(voice_id)
        return {"provider": "cached_offline", "chunks": [
            {**samples[voice_id], **cue} for cue in segments
        ]}

    gate, stored = _production_gate_with_offline_storage()
    output = tmp_path / "n2-smart.mp4"
    result = asyncio.run(smart.run_auto_smart_multivoice_blackbox(
        state={"auto_speaker_lane": "auto_smart_multivoice", "mode": "subtitle_plus_dub",
               "input_duration": 4.0, "voice_kind": "auto_speaker_gender", "voice_selection_mode": "auto_speaker",
               "_pipeline_job_key": "fixture-n2", "_pipeline_is_admin": True, "subdub_final_confirmed": True},
        prepare_subtitles=lambda *_args, **_kwargs: {
            "source_file": str(source), "source_bytes": source.read_bytes(),
            "source_segments": cues, "output_segments": cues,
            "output_subtitle": media_bot.video_dubbing_srt_from_segments(cues),
            "state": {"auto_smart_generic_acoustic": True, "input_duration": 4.0},
        },
        post_prepare_gate=gate, synthesize_segments=synthesize, strict_two_classifier=strict,
        build_timeline_audio=media_bot.build_dub_timeline_audio,
        render_video=media_bot.video_dubbing_render_video,
        validated_pools={"low": [], "high": list(samples)},
        output_path=str(output), job_id="fixture-n2", checkpoint_workspace=str(tmp_path / "checkpoint"),
    ))
    assert result["ok"], result
    assert result["fallback_reason"] == "n2_strict_ambiguity_fallback"
    assert observed["strict"] == 1
    assert len(set(observed["voices"])) == 2
    assert len(stored) == 1
    assert _outer_audio_guard(result) is None
    assert actual_outer_exact_price_guard(result["state"]) is None
    probe = _probe(output)
    assert {s["codec_type"] for s in probe["streams"]} >= {"video", "audio"}
    assert float(probe["format"]["duration"]) == pytest.approx(4.0, abs=0.15)
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-i", str(output), "-f", "null", "-"], capture_output=True, check=True)
    assert len(result["output_segments"]) == 2
    assert result["effective_voice_count"] == 2
