import asyncio
import hashlib
import json
import os
from pathlib import Path

import pytest

from services.subdub_blackboxes import auto_smart_multivoice as smart
from services.subdub_smart_timing import extend_smart_tail_windows
from services.subdub_smart_timing import retime_smart_subtitle_tails
from services.subtitle_dub_product_pipeline import process_subtitle_dub_job
from test_p0_subdub_smart_bounded_audio_recovery import (
    _probe, _run_cached_mp4, media_bot, timeline_bot,
)


def _chunk(cue_id, start, end, duration, smart=True):
    return {
        "cue_id": cue_id,
        "start": start,
        "end": end,
        "audio_duration": duration,
        "duration_aware_timing": smart,
    }


def test_final_smart_cue_extends_into_empty_video_tail_with_two_second_cap():
    chunks = [_chunk("last", 39.92, 41.94, 5.143)]
    subtitles = {"cue_id": "last", "start": 39.92, "end": 41.94, "text": "translated"}
    tts_segments = {"cue_id": "last", "start": 39.92, "end": 41.94}

    changed = extend_smart_tail_windows(
        chunks,
        companion_segments=[tts_segments, subtitles],
        source_duration=59.60,
    )

    assert changed == ["last"]
    assert chunks[0]["end"] == 43.94
    assert abs(chunks[0]["cue_window"] - 4.02) < 1e-9
    assert subtitles["end"] == 43.94
    assert tts_segments["end"] == 43.94
    assert chunks[0]["tail_extension_seconds"] == 2.0


def test_smart_tail_extension_stops_before_next_cue():
    chunks = [
        _chunk("first", 1.0, 2.0, 3.0),
        _chunk("next", 3.0, 4.0, 1.0),
    ]
    changed = extend_smart_tail_windows(chunks, source_duration=10.0)

    assert changed == ["first"]
    assert chunks[0]["end"] == 3.0
    assert chunks[1]["start"] == 3.0


def test_tail_extension_respects_preserved_speech_without_a_tts_chunk():
    chunks = [_chunk("dubbed", 1.0, 2.0, 4.0)]
    cues = [
        {"cue_id": "dubbed", "start": 1.0, "end": 2.0},
        {"cue_id": "preserved", "start": 2.5, "end": 4.0},
    ]
    extend_smart_tail_windows(chunks, companion_segments=cues, source_duration=10.0)
    assert chunks[0]["end"] == 2.5
    assert cues[1]["start"] == 2.5


def test_tail_extension_does_not_enter_an_earlier_overlapping_speaker():
    chunks = [
        _chunk("earlier", 0.0, 6.0, 6.0),
        _chunk("inside", 1.0, 2.0, 4.0),
    ]
    assert extend_smart_tail_windows(chunks, source_duration=10.0) == []
    assert chunks[1]["end"] == 2.0


def test_tail_extension_honors_canonical_millisecond_subtitle_boundaries():
    chunks = [_chunk("dubbed", 1.0, 2.0, 4.0)]
    cues = [
        {"cue_id": "dubbed", "start_ms": 1000, "end_ms": 2000},
        {"cue_id": "preserved", "start_ms": 2500, "end_ms": 4000},
    ]
    extend_smart_tail_windows(chunks, companion_segments=cues, source_duration=10.0)
    assert chunks[0]["end"] == 2.5
    assert cues[0]["start_ms"] == 1000
    assert cues[0]["end_ms"] == 2500
    srt = "1\n00:00:01,000 --> 00:00:02,000\nspeech\n\n2\n00:00:02,500 --> 00:00:04,000\noriginal\n"
    assert retime_smart_subtitle_tails(srt, cues) == srt.replace(
        "00:00:01,000 --> 00:00:02,000", "00:00:01,000 --> 00:00:02,500",
    )


def test_non_smart_cue_is_unchanged():
    chunks = [_chunk("legacy", 1.0, 2.0, 3.0, smart=False)]
    assert extend_smart_tail_windows(chunks, source_duration=10.0) == []
    assert chunks[0]["end"] == 2.0


def test_existing_source_overlap_does_not_allow_extension_into_next_cue():
    chunks = [
        _chunk("first", 1.0, 2.0, 4.0),
        _chunk("overlap", 1.9, 2.5, 0.6),
        _chunk("later", 6.0, 7.0, 1.0),
    ]
    assert extend_smart_tail_windows(chunks, source_duration=10.0) == []
    assert chunks[0]["end"] == 2.0


def test_tail_extension_never_exceeds_video_end_or_accumulates_on_retry():
    chunks = [_chunk("last", 39.92, 41.94, 10.0)]
    assert extend_smart_tail_windows(chunks, source_duration=60.0) == ["last"]
    assert extend_smart_tail_windows(chunks, source_duration=60.0) == []
    assert chunks[0]["end"] == 43.94
    chunks = [_chunk("last", 39.92, 41.94, 5.143)]
    assert extend_smart_tail_windows(chunks, source_duration=42.5) == ["last"]
    assert chunks[0]["end"] == 42.5


def test_smart_tail_extension_updates_subtitle_end_time():
    srt = "1\n00:00:39,920 --> 00:00:41,940\ntranslated\n"
    result = retime_smart_subtitle_tails(
        srt,
        [{"start": 39.92, "end": 43.94, "smart_source_end": 41.94,
          "tail_extension_seconds": 2.0}],
    )
    assert "00:00:39,920 --> 00:00:43,940" in result


def test_subtitle_tail_rejects_mismatched_source_timeline():
    srt = "1\n00:00:39,900 --> 00:00:41,940\ntranslated\n"
    with pytest.raises(ValueError, match="smart_tail_subtitle_cue_mismatch"):
        retime_smart_subtitle_tails(srt, [{
            "start": 39.92, "end": 43.94, "smart_source_end": 41.94,
            "tail_extension_seconds": 2.0,
        }])


def test_tail_update_keeps_source_cues_immutable_in_runner(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"contract-source" * 100)
    cues = [{"cue_id": "c1", "speaker_id": "s1", "start": 1.0,
             "end": 2.0, "text": "complete speech"}]
    observed = {}

    async def synthesize(**_kwargs):
        return {"chunks": [_chunk("c1", 1.0, 2.0, 2.0)]}

    async def render(**kwargs):
        observed.update(kwargs)
        Path(kwargs["output_path"]).write_bytes(b"contract-only" * 100)

    result = asyncio.run(smart.run_auto_smart_multivoice(
        source_media=source, segments=cues, output_path=tmp_path / "result.mp4",
        state={"input_duration": 5.0}, synthesize_segments=synthesize,
        render_pipeline=render, probe_fn=lambda _path: {"ok": True},
        validated_pools={"low": ["voice"], "high": ["voice"]},
        locked_speaker_voice_map={"s1": "voice"},
    ))
    assert result["ok"], result
    assert cues[0]["end"] == 2.0
    assert observed["cues"][0]["end"] == 3.0
    assert result["output_segments"][0]["end"] == 3.0


@pytest.mark.parametrize("lane", ["auto_smart_multivoice", "multi", "auto_speaker"])
def test_shared_pipeline_extends_only_smart_and_keeps_source_cues(lane):
    cues = [{"cue_id": "c1", "speaker_id": "s1", "start": 1.0,
             "end": 2.0, "text": "complete speech"}]
    observed = {}
    source_srt = "1\n00:00:01,000 --> 00:00:02,000\ncomplete speech\n"

    async def prepare(_state):
        return {"source_bytes": b"source", "content_type": "video/mp4",
                "source_segments": cues, "output_segments": cues,
                "output_subtitle": source_srt}

    async def synthesize(*_args, **_kwargs):
        return {"chunks": [_chunk("c1", 1.0, 2.0, 1.5)], "provider": "offline"}

    async def timeline(chunks, duration):
        observed["chunks"] = chunks
        observed["duration"] = duration
        return b"audio", "contract-only"

    async def render(*_args, **kwargs):
        observed["subtitles"] = kwargs["subtitle_bytes"]
        return b"video", "contract-only"

    result = asyncio.run(process_subtitle_dub_job(
        mode="subtitle_plus_dub", user_id=1,
        state={"auto_speaker_lane": lane, "cue_locked_timing": True,
               "target_language": "vi", "input_duration": 5.0},
        prepare_subtitles=prepare, srt_from_text=lambda *_args: "",
        segments_from_text=lambda *_args: [], segments_from_subtitle=lambda *_args: [],
        subtitle_output_items=lambda text, *_args: [{"text": text}],
        resolve_voice_id=lambda *_args: "voice", parse_voice_speed=float,
        synthesize_segments=synthesize, build_timeline_audio=timeline,
        normalize_audio=lambda audio: (audio, "contract-only"),
        render_video=render, video_render_ready=lambda *_args: True,
        ffmpeg_ready=lambda: True, dub_mux_enabled=True,
    ))
    assert result["ok"], result
    expected_end = 2.5 if lane == "auto_smart_multivoice" else 2.0
    assert result["output_segments"][0]["end"] == expected_end
    assert observed["chunks"][0]["end"] == expected_end
    assert observed["duration"] == 5.0
    assert cues[0]["end"] == 2.0
    expected_srt = source_srt.replace("00:00:02,000", "00:00:02,500") if lane == "auto_smart_multivoice" else source_srt.strip()
    assert observed["subtitles"].decode().strip() == expected_srt.strip()


def _cached_job():
    replay_dir = os.environ.get("SMART_TAIL_REPLAY_DIR")
    if not replay_dir:
        pytest.skip("cached paid artifacts not provided")
    root = Path(replay_dir)
    manifest = json.loads((root / "subdub_tts_manifest.json").read_text(encoding="utf-8"))
    chunks, voices = [], {}
    for entry in manifest["entries"].values():
        assert entry["state"] == "SUCCEEDED"
        audio = (root / "tts_artifacts" / Path(entry["artifact_path"]).name).read_bytes()
        assert hashlib.sha256(audio).hexdigest() == entry["artifact_sha256"]
        chunks.append({**entry["chunks_meta"][0], "cue_id": entry["cue_id"],
                       "speaker_id": entry["speaker_id"], "audio_bytes": audio})
        voices[entry["speaker_id"]] = entry["voice_id"]
    chunks.sort(key=lambda item: item["start"])
    return root, chunks, voices


def test_bbdd_cached_audio_reproduces_original_gate_before_extension(tmp_path, monkeypatch):
    root, chunks, voices = _cached_job()
    monkeypatch.setattr(smart, "extend_smart_tail_windows", lambda *_args, **_kwargs: [])
    cues = [{k: chunk[k] for k in ["cue_id", "speaker_id", "start", "end", "text"]}
            for chunk in chunks]

    async def synthesize(**_kwargs):
        return {"chunks": chunks}

    async def forbidden_render(**_kwargs):
        pytest.fail("the previous hard-cap failure must happen before rendering")

    result = asyncio.run(smart.run_auto_smart_multivoice(
        source_media=root / "source.mp4", segments=cues,
        output_path=tmp_path / "must-not-exist.mp4", state={"input_duration": 60.0},
        synthesize_segments=synthesize, render_pipeline=forbidden_render,
        validated_pools={"low": list(voices.values()), "high": list(voices.values())},
        locked_speaker_voice_map=voices,
    ))
    assert result["error_code"] == "duration_aware_fit_exceeds_hard_cap"
    assert result["fit_ratio"] == pytest.approx(2.546, abs=0.001)


def test_bbdd_cached_audio_renders_real_mp4_with_matching_subtitle_tail(tmp_path, monkeypatch, media_bot):
    root, chunks, voices = _cached_job()
    original_starts = [chunk["start"] for chunk in chunks]
    original_texts = [chunk["text"] for chunk in chunks]
    duration = float(_probe(root / "source.mp4")["format"]["duration"])
    result, observed, output = _run_cached_mp4(
        tmp_path, monkeypatch, media_bot, root / "source.mp4", chunks, duration, voices,
    )
    assert len(result["output_segments"]) == 5
    assert [cue["start"] for cue in result["output_segments"]] == original_starts
    assert [cue["text"] for cue in result["output_segments"]] == original_texts
    assert result["output_segments"][-1]["end"] == 43.94
    assert b"00:00:39,920 --> 00:00:43,940" in result["srt_bytes"]
    assert observed["plan"]["scheduled"][-1]["tempo_ratio"] == pytest.approx(1.279338, abs=0.00001)
    assert float(_probe(output)["format"]["duration"]) == pytest.approx(duration, abs=0.15)
