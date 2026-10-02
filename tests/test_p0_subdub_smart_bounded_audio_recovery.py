"""Smart source-rate and source-locked MP4 contracts; no runtime/DB setup."""

import ast
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import types

import pytest

from services.subdub_blackboxes import auto_smart_multivoice as smart
from test_p0_subdub_smart_standard_pipeline_orchestrator import SAMPLE_VALID_MP3


@pytest.fixture(autouse=True)
def legacy_dubbing_flow_tests_keep_engine_routes_open():
    # This suite exercises isolated post-TTS functions, never runtime bootstrap.
    pass


@pytest.fixture(scope="module")
def timeline_bot():
    source = Path(__file__).resolve().parents[1] / "bot.py"
    names = {
        "subdub_plan_dub_timeline", "subdub_atempo_filters", "build_dub_timeline_audio",
        "video_dubbing_srt_from_segments", "video_dubbing_srt_timestamp",
        "run_subdub_ffmpeg_command",
        "synthesize_dub_segment_chunks", "subdub_speech_unit_count",
    }
    module = types.ModuleType("bot")
    _load_bot_functions(source, names, module)
    module.__dict__.update(
        asyncio=asyncio, os=os, tempfile=tempfile,
        frame_video_ffmpeg_path=lambda: shutil.which("ffmpeg"),
        SUBDUB_LONG_PROJECT_MAX_DURATION_SECONDS=1800,
        SUBDUB_DUB_CUE_MAX_PROVIDER_SPEED=1.8, re=re, sanitize_log_text=str,
        run_ffmpeg_command=None, _SUBDUB_BASE_RUN_FFMPEG_COMMAND=None,
    )
    return module


def _load_bot_functions(source, names, module):
    selected = []
    lines = source.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    for index, line in enumerate(lines):
        if not any(line.startswith(f"def {name}(") or line.startswith(f"async def {name}(") for name in names):
            continue
        end = index + 1
        while end < len(lines):
            current = lines[end]
            if current.strip() and not current[0].isspace() and not current.startswith(("#", ")")):
                break
            end += 1
        selected.extend(ast.parse("".join(lines[index:end])).body)
    assert {node.name for node in selected} == names
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), "exec"), module.__dict__)


@pytest.mark.parametrize("source_case", ["matching", "reordered", "unknown", "duplicate"])
def test_smart_retains_original_text_for_provider_rate_without_timeline_shift(tmp_path, monkeypatch, timeline_bot, source_case):
    monkeypatch.setitem(sys.modules, "bot", timeline_bot)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"contract-source" * 100)
    cues = [
        {"cue_id": "c1", "speaker_id": "speaker_0", "start": 1.0, "end": 2.0, "text": "First whole complete sentence"},
        {"cue_id": "c2", "speaker_id": "speaker_1", "start": 2.1, "end": 3.1, "text": "Second whole complete sentence"},
    ]
    observed = {}
    requested_speeds = []
    received_source_text = []
    originals = [{**cues[0], "text": "go now"}, {**cues[1], "text": "stay here"}]
    if source_case == "reordered":
        originals.reverse()
    elif source_case == "unknown":
        originals = [{**c, "cue_id": "unknown" + c["cue_id"]} for c in originals]
    elif source_case == "duplicate":
        originals[1]["cue_id"] = "c1"

    async def prepare(*args, **kwargs):
        return {"source_bytes": source.read_bytes(), "source_file": str(source), "output_segments": cues,
                "source_segments": originals,
                "output_subtitle": timeline_bot.video_dubbing_srt_from_segments(cues), "content_type": "video/mp4"}

    async def provider(text, voice_style, voice_id, speed, **kwargs):
        requested_speeds.append(float(speed))
        return "offline_contract", SAMPLE_VALID_MP3, "not a real provider call"

    async def qc(*args, **kwargs):
        return {"ok": True, "duration": 1.0, "leading_silence_seconds": 0.14}

    monkeypatch.setattr(timeline_bot, "video_dubbing_tts_bytes", provider, raising=False)
    monkeypatch.setattr(timeline_bot, "subdub_validate_tts_audio_bytes", qc, raising=False)

    async def synthesize(segments, **kwargs):
        received_source_text.extend(c.get("source_text") for c in segments)
        return await timeline_bot.synthesize_dub_segment_chunks(segments, base_speed=0.95, max_speed=1.8, **kwargs)

    async def timeline(chunks, duration):
        observed["plan"] = timeline_bot.subdub_plan_dub_timeline(chunks, duration)
        return b"contract-timeline", "contract-only"

    async def render(source_bytes, **kwargs):
        observed.update(kwargs)
        return b"contract-output" * 100, "contract-only"

    result = asyncio.run(smart.run_auto_smart_multivoice_blackbox(
        state={"auto_speaker_lane": "auto_smart_multivoice", "mode": "subtitle_plus_dub", "input_duration": 10.0},
        prepare_subtitles=prepare, synthesize_segments=synthesize, build_timeline_audio=timeline,
        render_video=render, validated_pools={"low": ["male"], "high": ["female"]},
        acoustic_classifications={"speaker_0": {"voice_register": "high", "confidence": 1.0},
                                  "speaker_1": {"voice_register": "low", "confidence": 1.0}},
        output_path=str(tmp_path / "result.mp4"),
        job_id="contract-fit", checkpoint_workspace=str(tmp_path / "checkpoint"),
        probe_fn=lambda path: {"ok": True},  # This test is a contract, not artifact proof.
    ))
    assert result["ok"], result
    plan = observed["plan"]
    assert requested_speeds == ([1.8, 1.8] if source_case in {"matching", "reordered"} else [0.95, 0.95])
    if source_case in {"matching", "reordered"}:
        assert received_source_text == ["go now", "stay here"]
    else:
        assert received_source_text == [None, None]
    assert plan["cue_locked_timing"] is True
    assert plan["shifted_cue_count"] == 0
    assert plan["scheduled"][0]["raw_audio_duration"] == 1.0
    assert plan["scheduled"][0]["audio_duration"] == pytest.approx(0.9)
    assert plan["scheduled"][1]["scheduled_start"] == pytest.approx(2.1)
    assert result["speaker_voice_map"] == {"speaker_0": "female", "speaker_1": "male"}
    assert result["output_segments"][1]["start"] == pytest.approx(2.1)
    assert b"00:00:02,100 --> 00:00:03,100" in observed["subtitle_bytes"]
    assert result["srt_bytes"] == observed["subtitle_bytes"]


def test_recovery_cannot_turn_audio_qc_failure_into_mp4_success(tmp_path, monkeypatch, timeline_bot):
    # The same adapter must honor QC's result, not just await the callback.
    monkeypatch.setitem(sys.modules, "bot", timeline_bot)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source" * 100)

    async def prepare(*args, **kwargs):
        return {"source_bytes": b"source", "source_file": str(source), "content_type": "video/mp4",
                "output_segments": [{"cue_id": "c1", "speaker_id": "s1", "start": 0.0, "end": 1.0, "text": "Complete sentence"}]}

    async def synthesize(segments, **kwargs):
        return {"chunks": [{"cue_id": "c1", "audio_bytes": SAMPLE_VALID_MP3, "audio_duration": 0.8}]}

    async def timeline(*args):
        return b"bad-audio", "built"

    async def qc(*args):
        return {"ok": False, "detail": "speech_activity_missing"}

    async def forbidden_render(*args, **kwargs):
        pytest.fail("render must not run after failed audio QC")

    result = asyncio.run(smart.run_auto_smart_multivoice_blackbox(
        state={"auto_speaker_lane": "auto_smart_multivoice", "mode": "dub", "input_duration": 5.0},
        prepare_subtitles=prepare, synthesize_segments=synthesize, build_timeline_audio=timeline,
        validate_audio=qc, render_video=forbidden_render,
        validated_pools={"low": ["male"], "high": ["female"]},
        output_path=str(tmp_path / "result.mp4"),
        job_id="contract-qc", checkpoint_workspace=str(tmp_path / "checkpoint"),
    ))
    assert result["ok"] is False
    assert "speech_activity_missing" in result["blocker"]
    assert not (tmp_path / "result.mp4").exists()


def _probe(path):
    result = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                            capture_output=True, check=True)
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def media_bot(timeline_bot):
    """Real production timeline/mux/ASS functions with controlled local font/style.

    Only hardware/config adapters are supplied here. Provider/runtime/DB startup
    is deliberately excluded; media bytes and validation always use FFmpeg.
    """
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg/FFprobe required for artifact proof")
    from services import ffmpeg_text, subdub_media_preflight
    module = timeline_bot
    module.__dict__.update(re=re, ffmpeg_text=ffmpeg_text, subdub_media_preflight=subdub_media_preflight)
    _load_bot_functions(Path(__file__).resolve().parents[1] / "bot.py", {
        "video_dubbing_render_video", "subdub_generate_ass_from_srt", "subdub_srt_blocks",
        "subdub_parse_srt_timestamp", "subdub_ass_timestamp", "subdub_ass_alignment",
        "subdub_ass_color", "subdub_ass_back_color", "subdub_ffmpeg_filter_path", "subdub_subtitle_filter_for_file",
    }, module)

    async def probe_bytes(data):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "probe.mp4"
            path.write_bytes(data)
            p = _probe(path)
        video = next(s for s in p["streams"] if s["codec_type"] == "video")
        return {"duration": float(p["format"]["duration"]), "has_audio": any(s["codec_type"] == "audio" for s in p["streams"]),
                "width": video["width"], "height": video["height"]}

    async def validate_output(data, require_audio, expected_duration):
        p = await probe_bytes(data)
        return {**p, "ok": bool(data) and (not require_audio or p["has_audio"]) and abs(p["duration"] - expected_duration) < 0.15,
                "detail": "real_ffprobe"}

    def style(state=None):
        state = state or {}
        return {"show_subtitles": True, "subtitle_font_resolution_ok": True,
                "font": "Arial", "render_size": 24, "play_res_x": int(state.get("video_width") or 1280),
                "play_res_y": int(state.get("video_height") or 720), "max_lines": 2,
                "m4live2_subtitle_bottom_lock": True, "position": "bottom", "align": "center", "outline": 1}

    module.__dict__.update(
        subdub_probe_video_bytes=probe_bytes, subdub_validate_video_output=validate_output,
        subdub_normalize_style=style, subdub_normalize_subtitle_text=lambda text: text.decode("utf-8") if isinstance(text, bytes) else str(text),
        subdub_validate_subtitle_text_for_delivery=lambda text: {"ok": bool(text) and "-->" in text, "normalized_text": text},
        subdub_visible_subtitle_text=lambda text: text,
        subdub_ass_wrap_text=lambda text, style, max_lines: text.replace("\n", r"\N"),
        subdub_advanced_style_enabled=lambda style: False, subdub_video_fit_filters=lambda style: [],
        subdub_original_audio_volume=lambda mode, keep: 0.0,
        subdub_percent_value=lambda value, default, minimum, maximum: float(default if value is None else value),
        sanitize_log_text=str, SUBDUB_VOLUME_MIX_UI_ENABLED=False,
        SUBDUB_ORIGINAL_AUDIO_DEFAULT_VOLUME_PERCENT=30, SUBDUB_DUBBED_VOICE_DEFAULT_VOLUME_PERCENT=100,
        SUBDUB_STAGE_TIMEOUT_MAX_SECONDS=600, SUBDUB_HARDSUB_COVER_OPACITY=0.3,
    )
    return module


def _run_cached_mp4(tmp_path, monkeypatch, media_bot, source, chunks, duration, voice_map):
    monkeypatch.setitem(sys.modules, "bot", media_bot)
    cues = [{"cue_id": c["cue_id"], "speaker_id": c["speaker_id"], "text": c["text"],
             "start": c["start"], "end": c["end"]} for c in chunks]
    indexed = {c["cue_id"]: c for c in chunks}
    observed = {}

    async def prepare(*args, **kwargs):
        return {"source_bytes": source.read_bytes(), "source_file": str(source), "content_type": "video/mp4",
                "output_segments": cues, "output_subtitle": media_bot.video_dubbing_srt_from_segments(cues),
                "state": {"auto_smart_generic_acoustic": True, "input_duration": duration}}

    async def cached_tts(segments, **kwargs):
        # Replay only already-paid artifacts; any requested voice change is a failure.
        result = []
        for c in segments:
            old = indexed[c["cue_id"]]
            assert kwargs["voice_id"] == voice_map[old["speaker_id"]]
            result.append(dict(old))
        return {"chunks": result, "provider": "cached_offline"}

    async def timeline(chunks, seconds):
        observed["plan"] = media_bot.subdub_plan_dub_timeline(chunks, seconds)
        return await media_bot.build_dub_timeline_audio(chunks, seconds)

    async def audio_qc(data):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "audio.mp3"
            path.write_bytes(data)
            p = _probe(path)
        return {"ok": bool(data), "duration": float(p["format"]["duration"]), "detail": "real_ffprobe"}

    async def render(*args, **kwargs):
        observed["subtitles"] = kwargs["subtitle_bytes"]
        value = await media_bot.video_dubbing_render_video(*args, **kwargs)
        observed["render_detail"] = value[1]
        return value

    output = tmp_path / "smart_complete.mp4"
    result = asyncio.run(smart.run_auto_smart_multivoice_blackbox(
        state={"auto_speaker_lane": "auto_smart_multivoice", "mode": "subtitle_plus_dub", "input_duration": duration,
               "locked_speaker_voice_map": voice_map},
        prepare_subtitles=prepare, synthesize_segments=cached_tts,
        build_timeline_audio=timeline, validate_audio=audio_qc, render_video=render,
        validated_pools={"low": list(voice_map.values()), "high": list(voice_map.values())},
        locked_speaker_voice_map=voice_map,
        acoustic_classifications={s: {"voice_register": "low", "confidence": 1.0} for s in voice_map},
        output_path=str(output), job_id="offline-replay", checkpoint_workspace=str(tmp_path / "checkpoint"),
    ))
    assert result["ok"], {k: v for k, v in result.items() if k in {"blocker", "error_code", "status"}}
    assert output.is_file() and output.stat().st_size > 1024
    probe = _probe(output)
    assert {s["codec_type"] for s in probe["streams"]} >= {"video", "audio"}
    assert next(s for s in probe["streams"] if s["codec_type"] == "video")["codec_name"] == "h264"
    assert abs(float(probe["format"]["duration"]) - observed["plan"]["timeline_duration"]) < 0.15
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-i", str(output), "-f", "null", "-"], capture_output=True, check=True)
    assert observed["plan"]["cue_locked_timing"] is True
    assert observed["plan"]["shifted_cue_count"] == 0
    assert result["speaker_voice_map"] == voice_map
    assert len(result["output_segments"]) == len(chunks)
    assert result["srt_bytes"] == observed["subtitles"]
    assert [c["text"] for c in result["output_segments"]] == [c["text"] for c in cues]
    assert all(a["end"] <= b["start"] + 0.001 for a, b in zip(result["output_segments"], result["output_segments"][1:]))
    return result, observed, output


def test_real_mp4_keeps_original_cue_and_video_timing(tmp_path, monkeypatch, media_bot):
    source = tmp_path / "source.mp4"
    subprocess.run([shutil.which("ffmpeg"), "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:r=25", "-t", "3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)], capture_output=True, check=True)
    audio = tmp_path / "cue.mp3"
    subprocess.run([shutil.which("ffmpeg"), "-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=32000", "-t", "0.8",
                    "-c:a", "libmp3lame", str(audio)], capture_output=True, check=True)
    chunks = [{"cue_id": f"c{i}", "speaker_id": f"s{i}", "text": f"Complete sentence {i}",
               "start": float(i), "end": float(i + 1), "audio_duration": 0.8, "audio_bytes": audio.read_bytes()} for i in range(2)]
    result, observed, output = _run_cached_mp4(tmp_path, monkeypatch, media_bot, source, chunks, 3.0, {"s0": "v0", "s1": "v1"})
    assert float(_probe(output)["format"]["duration"]) == pytest.approx(3.0, abs=0.1)
    assert len(result["output_segments"]) == 2
    assert "video_extended_by=0.000" in observed["render_detail"]
    assert [(c["start"], c["end"]) for c in result["output_segments"]] == [(0.0, 1.0), (1.0, 2.0)]
    frame = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-ss", "0.5", "-i", str(output), "-frames:v", "1",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    assert len(frame) == 320 * 240 * 3 and max(frame) > 100  # Burned subtitles on the black source.


def test_cached_overfit_job_cannot_be_reported_as_source_synced_mp4(tmp_path, monkeypatch, media_bot):
    artifact_dir = os.environ.get("SMART_CACHED_MP4_REPLAY_DIR")
    manifest_path = os.environ.get("SMART_CACHED_TTS_MANIFEST")
    if not artifact_dir or not manifest_path:
        pytest.skip("Owner artifact replay inputs not provided")
    root = Path(artifact_dir)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    chunks, voices = [], {}
    for entry in manifest["entries"].values():
        assert entry["state"] == "SUCCEEDED"
        audio = root / "tts_artifacts" / Path(entry["artifact_path"]).name
        data = audio.read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["artifact_sha256"]
        chunk = {**entry["chunks_meta"][0], "audio_bytes": data, "voice_id": entry["voice_id"]}
        chunks.append(chunk)
        voices[entry["speaker_id"]] = entry["voice_id"]
    assert len(chunks) == 25 and len(voices) == 5
    async def cached_tts(cues, **kwargs):
        return {"chunks": chunks}

    async def forbidden_render(**kwargs):
        pytest.fail("must not bypass compression by shifting source cues")

    cues = [{"cue_id": c["cue_id"], "speaker_id": c["speaker_id"], "text": c["text"],
             "start": c["start"], "end": c["end"]} for c in chunks]
    output = tmp_path / "must_not_exist.mp4"
    result = asyncio.run(smart.run_auto_smart_multivoice(
        source_media=root / "normalized_source.mp4", segments=cues, output_path=output,
        synthesize_segments=cached_tts, render_pipeline=forbidden_render,
        validated_pools={"low": list(voices.values()), "high": list(voices.values())},
        locked_speaker_voice_map=voices,
    ))
    assert result["ok"] is False
    assert result["error_code"] == "extreme_audio_compression_unintelligible"
    assert not output.exists()
