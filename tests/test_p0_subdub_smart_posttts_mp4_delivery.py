import ast
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import textwrap

import pytest

from services.subdub_blackboxes import auto_smart_multivoice as smart
from services.subtitle_dub_product_pipeline import process_subtitle_dub_job
from services.subdub_smart_timing import retime_smart_subtitle_tails
from test_p0_subdub_smart_bounded_audio_recovery import (
    _probe, _run_cached_mp4, media_bot, timeline_bot,
)


def _outer_audio_guard(result):
    # Execute the actual production guard, without bootstrapping the bot.
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8-sig")
    error_pos = source.rindex('"generated_tts_audio_missing"')
    start = source.rindex('    if mode in {VIDEO_SUBTITLE_MODE_DUB, VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB} and (', 0, error_pos)
    end = source.index('\n    if mode ', error_pos)
    block = textwrap.dedent(source[start:end])
    tree = ast.parse("def guard():\n" + textwrap.indent(block, "    "))
    namespace = {
        "mode": "subtitle_plus_dub", "VIDEO_SUBTITLE_MODE_DUB": "dub",
        "VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB": "subtitle_plus_dub",
        "audio_bytes": result.get("audio_bytes") or b"",
        "output_audio_source": result.get("output_audio_source") or (
            "generated_tts" if result.get("audio_bytes") and result.get("tts_provider") else ""
        ),
        "_failed_product_result": lambda *_args, **_kwargs: "generated_tts_audio_missing",
        "subdub_voice_not_ready_text": lambda *_args: "missing", "lang": "vi",
    }
    exec(compile(tree, "production_outer_audio_guard", "exec"), namespace)
    return namespace["guard"]()


def _cached_inputs(job_id):
    value = os.environ.get("SMART_POSTTTS_REPLAY_DIR")
    if not value:
        pytest.skip("Owner cached job artifacts not provided")
    root = Path(value) / job_id
    manifest = json.loads((root / "subdub_tts_manifest.json").read_text(encoding="utf-8"))
    sidecar = json.loads((root / "speaker_cast.sidecar.json").read_text(encoding="utf-8"))
    registers = {c["speaker_id"]: c.get("voice_register", "unknown") for c in sidecar["cues"]}
    chunks, voices = [], {}
    for entry in manifest["entries"].values():
        assert entry["state"] == "SUCCEEDED"
        data = (root / "tts_artifacts" / Path(entry["artifact_path"]).name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["artifact_sha256"]
        chunks.append({**entry["chunks_meta"][0], "audio_bytes": data,
                       "voice_id": entry["voice_id"]})
        voices[entry["speaker_id"]] = entry["voice_id"]
    chunks.sort(key=lambda c: c["start"])
    return root, chunks, voices, registers


def test_806_cached_mp4_passes_real_outer_audio_guard(tmp_path, monkeypatch, media_bot):
    root, chunks, voices, _registers = _cached_inputs("806a998ec7fa6a3df38f")
    assert len(chunks) == 5 and len(voices) == 1
    source = root / "normalized_source.mp4"
    duration = float(_probe(source)["format"]["duration"])
    result, _observed, _output = _run_cached_mp4(
        tmp_path, monkeypatch, media_bot, source, chunks, duration, voices,
    )
    assert _outer_audio_guard(result) is None
    assert result["tts_provider"] == "cached_offline"
    assert result["output_audio_source"] == "generated_tts"
    assert result["tts_audio_qc"]["ok"] is True
    assert result["tts_expected_segments"] == result["tts_generated_segments"] == 5


def _shared_contract(lane, *, smart_dispatch=False, duration=2.6, video_end=2.0):
    cues = [{"cue_id": "c1", "speaker_id": "s1", "start": 1.0, "end": 2.0,
             "text": "full speech", "tts_voice_id": "voice"}]
    state = {"auto_speaker_lane": lane, "cue_locked_timing": True,
             "input_duration": video_end, "target_language": "vi"}
    if smart_dispatch:
        state.update(auto_smart_multivoice_opt_in=True, auto_smart_dispatch="n3_plus_proven_v2")
    observed = {}

    async def prepare(_state):
        return {"source_bytes": b"source", "content_type": "video/mp4",
                "source_segments": cues, "output_segments": cues,
                "output_subtitle": "1\n00:00:01,000 --> 00:00:02,000\nfull speech\n"}

    async def synthesize(*_args, **_kwargs):
        return {"provider": "offline", "chunks": [{**cues[0], "audio_duration": duration,
                                                     "duration_aware_timing": True}]}

    async def timeline(chunks, duration):
        observed.update(chunks=chunks, duration=duration)
        return b"audio", "contract"

    result = asyncio.run(process_subtitle_dub_job(
        mode="subtitle_plus_dub", state=state, user_id=1,
        prepare_subtitles=prepare, srt_from_text=lambda *_args: "",
        segments_from_text=lambda *_args: [], segments_from_subtitle=lambda *_args: [],
        subtitle_output_items=lambda *_args: [], resolve_voice_id=lambda *_args: "voice",
        parse_voice_speed=float, synthesize_segments=synthesize,
        build_timeline_audio=timeline, normalize_audio=lambda b: (b, "contract"),
        render_video=lambda *_args, **_kwargs: (b"video", "contract"),
        video_render_ready=lambda *_args: True, ffmpeg_ready=lambda: True, dub_mux_enabled=True,
    ))
    return result, observed


def test_smart_v2_borrows_gap_while_plain_multi_does_not():
    smart_result, smart_observed = _shared_contract("multi", smart_dispatch=True, duration=1.5, video_end=5.0)
    plain_result, plain_observed = _shared_contract("multi", duration=1.5, video_end=5.0)
    assert smart_result["ok"] and plain_result["ok"]
    assert smart_observed["chunks"][0]["end"] == 2.5
    assert plain_observed["chunks"][0]["end"] == 2.0


@pytest.mark.parametrize("duration", [2.6, 6.0])
def test_owner_smart_quality_warning_does_not_abort_valid_render(duration):
    result, observed = _shared_contract("multi", smart_dispatch=True, duration=duration)
    assert result["ok"], result
    assert result["smart_audio_fit_degraded"] is True
    assert result["smart_audio_fit_warnings"][0]["fit_ratio"] == duration
    assert observed["chunks"][0]["start"] == 1.0
    assert observed["chunks"][0]["end"] == 2.0
    assert observed["duration"] == 2.0


def test_plain_multi_explicit_timing_keeps_existing_quality_failure():
    result, observed = _shared_contract("multi", duration=2.6)
    assert result["ok"] is False
    assert result["error_code"] == "duration_aware_fit_exceeds_hard_cap"
    assert not observed


def test_tail_retime_accepts_one_millisecond_generator_rounding_only():
    srt = "1\n00:00:15,355 --> 00:00:16,254\nfull speech\n"
    cue = {"start": 15.355, "end": 17.115, "smart_source_end": 16.255,
           "tail_extension_seconds": 0.86}
    assert retime_smart_subtitle_tails(srt, [cue]) == srt.replace("16,254", "17,115")
    with pytest.raises(ValueError, match="smart_tail_subtitle_cue_mismatch"):
        retime_smart_subtitle_tails(srt.replace("16,254", "16,250"), [cue])


def _run_shared_cached_mp4(root, chunks, voices, registers, output, media_bot):
    from shutil import which
    source = root / "normalized_source.mp4"
    duration = float(_probe(source)["format"]["duration"])
    original_cues = [{k: c[k] for k in ("cue_id", "speaker_id", "start", "end", "text")} for c in chunks]
    annotated = [{**c, "tts_voice_id": voices[c["speaker_id"]]} for c in original_cues]
    prepared = {"source_segments": annotated, "output_segments": annotated}
    prepared.update(source_bytes=source.read_bytes(), content_type="video/mp4",
                    output_subtitle=media_bot.video_dubbing_srt_from_segments(original_cues))
    observed = {}

    async def synthesize(segments, **_kwargs):
        assert [(c["cue_id"], c["tts_voice_id"]) for c in segments] == [
            (c["cue_id"], voices[c["speaker_id"]]) for c in chunks
        ]
        return {"provider": "cached_offline", "chunks": [dict(c) for c in chunks]}

    async def timeline(items, seconds):
        observed["plan"] = media_bot.subdub_plan_dub_timeline(items, seconds)
        return await media_bot.build_dub_timeline_audio(items, seconds)

    async def render(*args, **kwargs):
        observed["subtitles"] = kwargs["subtitle_bytes"]
        return await media_bot.video_dubbing_render_video(*args, **kwargs)

    result = asyncio.run(process_subtitle_dub_job(
        mode="subtitle_plus_dub", user_id=1,
        state={"auto_speaker_lane": "multi", "auto_smart_multivoice_opt_in": True,
               "auto_smart_dispatch": "n3_plus_proven_v2", "cue_locked_timing": True,
               "input_duration_seconds": duration, "target_language": "vi"},
        prepare_subtitles=lambda _state: prepared,
        srt_from_text=lambda *_args: "", segments_from_text=lambda *_args: [],
        segments_from_subtitle=lambda *_args: [], subtitle_output_items=lambda *_args: [],
        resolve_voice_id=lambda *_args: next(iter(voices.values())), parse_voice_speed=float,
        synthesize_segments=synthesize, build_timeline_audio=timeline,
        normalize_audio=lambda data: (data, "already decoded in real FFmpeg timeline"),
        render_video=render, video_render_ready=lambda *_args: True,
        ffmpeg_ready=lambda: True, dub_mux_enabled=True,
    ))
    assert result["ok"], {k: result.get(k) for k in ("status", "error_code", "cue_id")}
    assert _outer_audio_guard(result) is None
    output.write_bytes(result["video_output"])
    probe = _probe(output)
    assert {s["codec_type"] for s in probe["streams"]} >= {"video", "audio"}
    assert next(s for s in probe["streams"] if s["codec_type"] == "video")["codec_name"] == "h264"
    assert float(probe["format"]["duration"]) == pytest.approx(duration, abs=0.15)
    subprocess.run([which("ffmpeg"), "-v", "error", "-i", str(output), "-f", "null", "-"], capture_output=True, check=True)
    assert [c["start"] for c in result["output_segments"]] == [c["start"] for c in original_cues]
    assert [c["text"] for c in result["output_segments"]] == [c["text"] for c in original_cues]
    assert result["srt_bytes"] == observed["subtitles"]
    assert observed["plan"]["shifted_cue_count"] == 0
    assert all(a["end"] <= b["start"] + 0.001 for a, b in zip(result["output_segments"], result["output_segments"][1:]))
    return result, observed


def test_53b6_all_23_cues_and_five_voices_render_through_shared_posttts_path(tmp_path, media_bot):
    root, chunks, voices, registers = _cached_inputs("53b6e00fc9113899224e")
    assert len(chunks) == 23 and len(voices) == len(set(voices.values())) == 5
    result, observed = _run_shared_cached_mp4(root, chunks, voices, registers, tmp_path / "five_voice.mp4", media_bot)
    assert result["tts_expected_segments"] == result["tts_generated_segments"] == 23
    assert result["smart_audio_fit_degraded"] is True
    warning_ids = {c["cue_id"] for c in result["smart_audio_fit_warnings"]}
    assert chunks[13]["cue_id"] in warning_ids
    assert result["output_segments"][13]["end"] == 37.3
    assert observed["plan"]["scheduled"][13]["tempo_ratio"] == pytest.approx(2.59712386)
    assert result["output_segments"][21]["end"] > chunks[21]["end"]
    assert result["output_segments"][22]["end"] > chunks[22]["end"]


def test_53b6_actual_generic_route_renders_all_cues_with_quality_warning(tmp_path, monkeypatch, media_bot):
    root, chunks, voices, _registers = _cached_inputs("53b6e00fc9113899224e")
    source = root / "normalized_source.mp4"
    duration = float(_probe(source)["format"]["duration"])
    result, observed, _output = _run_cached_mp4(
        tmp_path, monkeypatch, media_bot, source, chunks, duration, voices,
    )
    assert _outer_audio_guard(result) is None
    assert result["smart_audio_fit_degraded"] is True
    assert result["tts_expected_segments"] == result["tts_generated_segments"] == 23
    assert result["speaker_voice_map"] == voices
    assert observed["plan"]["shifted_cue_count"] == 0
    assert result["output_segments"][13]["end"] == 37.3
