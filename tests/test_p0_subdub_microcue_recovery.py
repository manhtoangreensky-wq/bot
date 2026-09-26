"""Unit tests for services/subdub_microcue_recovery.py.

Verifies:
1. Invariant safety gates (same speaker, non-speech boundary, gap limits, fragment threshold)
2. Zero data loss coalescence (text, audio bytes, provenance, expanded window)
3. Iterative recovery logic with fit ratio preference
4. Strictly unchanged MAX_INTELLIGIBLE_FIT_RATIO = 1.80
"""

from pathlib import Path
import pytest
from services.subdub_microcue_recovery import (
    MAX_INTELLIGIBLE_FIT_RATIO,
    DEFAULT_MAX_COALESCE_GAP_SECONDS,
    DEFAULT_MAX_FRAGMENT_DURATION_SECONDS,
    can_coalesce_cues,
    coalesce_cue_pair,
    recover_cue_locked_micro_cues,
)


def test_fit_ratio_constant_invariant():
    """MAX_INTELLIGIBLE_FIT_RATIO must remain strictly 1.80."""
    assert MAX_INTELLIGIBLE_FIT_RATIO == 1.80


def test_can_coalesce_speaker_mismatch():
    """Cross-speaker cues must not coalesce."""
    c1 = {"cue_id": "c1", "speaker_id": "spk_1", "start": 0.0, "end": 2.0}
    c2 = {"cue_id": "c2", "speaker_id": "spk_2", "start": 2.0, "end": 2.5}
    assert can_coalesce_cues(c1, c2) is False


def test_can_coalesce_non_speech_boundary():
    """Cues separated by non-speech boundary must not coalesce."""
    c1 = {"cue_id": "c1", "speaker_id": "spk_1", "start": 0.0, "end": 2.0, "non_speech_boundary": True}
    c2 = {"cue_id": "c2", "speaker_id": "spk_1", "start": 2.0, "end": 2.5}
    assert can_coalesce_cues(c1, c2) is False

    c3 = {"cue_id": "c3", "speaker_id": "spk_1", "start": 0.0, "end": 2.0}
    c4 = {"cue_id": "c4", "speaker_id": "spk_1", "start": 2.0, "end": 2.5, "non_speech_boundary": True}
    assert can_coalesce_cues(c3, c4) is False


def test_can_coalesce_gap_limits():
    """Gap exceeding max_gap_seconds or backward beyond 55ms must not coalesce."""
    # Gap > 0.5s
    c1 = {"cue_id": "c1", "speaker_id": "spk_1", "start": 0.0, "end": 2.0}
    c2 = {"cue_id": "c2", "speaker_id": "spk_1", "start": 2.6, "end": 3.0}  # gap = 0.6s
    assert can_coalesce_cues(c1, c2, max_gap_seconds=0.5) is False

    # Gap = 0.5s -> Allowed
    c3 = {"cue_id": "c3", "speaker_id": "spk_1", "start": 2.5, "end": 3.0}  # gap = 0.5s
    assert can_coalesce_cues(c1, c3, max_gap_seconds=0.5) is True

    # Overlap > 55ms -> Rejected
    c4 = {"cue_id": "c4", "speaker_id": "spk_1", "start": 1.9, "end": 2.5}  # gap = -0.1s
    assert can_coalesce_cues(c1, c4) is False


def test_can_coalesce_fragment_threshold():
    """If neither cue is a short fragment (<= 3.0s), they must not coalesce."""
    c1 = {"cue_id": "c1", "speaker_id": "spk_1", "start": 0.0, "end": 5.0}  # window = 5.0s
    c2 = {"cue_id": "c2", "speaker_id": "spk_1", "start": 5.0, "end": 9.0}  # window = 4.0s
    assert can_coalesce_cues(c1, c2, max_fragment_duration_seconds=3.0) is False

    # One cue is a fragment (0.8s) -> Allowed
    c3 = {"cue_id": "c3", "speaker_id": "spk_1", "start": 5.0, "end": 5.8}  # window = 0.8s
    assert can_coalesce_cues(c1, c3, max_fragment_duration_seconds=3.0) is True


def test_coalesce_cue_pair_preservation():
    """Coalescing preserves text, audio, provenance, timing window."""
    c1 = {
        "cue_id": "c1",
        "speaker_id": "spk_1",
        "start": 10.0,
        "end": 15.0,
        "text": "Hello world",
        "audio": b"AUDIO_1_",
        "audio_duration": 4.5,
        "original_cue_ids": ["c1"],
    }
    c2 = {
        "cue_id": "c2",
        "speaker_id": "spk_1",
        "start": 15.0,
        "end": 15.6,
        "text": "again",
        "audio": b"AUDIO_2",
        "audio_duration": 1.1,
        "original_cue_ids": ["c2"],
    }
    merged = coalesce_cue_pair(c1, c2)
    assert merged["cue_id"] == "c1+c2"
    assert merged["speaker_id"] == "spk_1"
    assert merged["start"] == 10.0
    assert merged["end"] == 15.6
    assert merged["cue_window"] == pytest.approx(5.6)
    assert merged["text"] == "Hello world again"
    assert merged["audio"] == b"AUDIO_1_AUDIO_2"
    assert merged["audio_duration"] == pytest.approx(6.1)
    assert merged["fit_ratio"] == pytest.approx(6.1 / 5.6, abs=0.01)
    assert merged["right_cue_offset"] == pytest.approx(5.0)
    assert merged["gap_silence_seconds"] == pytest.approx(0.5)
    assert merged["coalesced"] is True
    assert merged["cue_locked_timing"] is True
    assert merged["original_cue_ids"] == ["c1", "c2"]


def test_recover_empty_and_single():
    """Edge cases: empty list and single item return unchanged."""
    assert recover_cue_locked_micro_cues([]) == []
    single = [{"cue_id": "c1", "start": 0, "end": 1, "fit_ratio": 2.0}]
    assert recover_cue_locked_micro_cues(single) == single


def test_recover_no_exceeding_ratio_unchanged():
    """Cues that all satisfy <= 1.80 remain untouched."""
    items = [
        {"cue_id": "c1", "speaker_id": "spk_1", "start": 0.0, "end": 2.0, "audio_duration": 2.0},
        {"cue_id": "c2", "speaker_id": "spk_1", "start": 2.0, "end": 4.0, "audio_duration": 2.5},
    ]
    recovered = recover_cue_locked_micro_cues(items)
    assert len(recovered) == 2
    assert recovered[0]["cue_id"] == "c1"
    assert recovered[1]["cue_id"] == "c2"


def test_recover_prefers_lower_fit_ratio():
    """When both left and right are valid candidates, pick the one with lower combined fit ratio."""
    # Left neighbor: 10s window, 5s audio -> combined: 11s win, 7.5s aud -> fit = 0.68
    # Middle microcue: 1s window, 2.5s audio -> fit = 2.5 (needs recovery)
    # Right neighbor: 2s window, 3s audio -> combined: 3s win, 5.5s aud -> fit = 1.83 (would exceed)
    c_left = {"cue_id": "left", "speaker_id": "spk_1", "start": 0.0, "end": 10.0, "audio_duration": 5.0}
    c_mid = {"cue_id": "mid", "speaker_id": "spk_1", "start": 10.0, "end": 11.0, "audio_duration": 2.5}
    c_right = {"cue_id": "right", "speaker_id": "spk_1", "start": 11.0, "end": 13.0, "audio_duration": 3.0}

    recovered = recover_cue_locked_micro_cues([c_left, c_mid, c_right])
    assert len(recovered) == 2
    # c_left and c_mid must coalesce
    assert recovered[0]["original_cue_ids"] == ["left", "mid"]
    assert recovered[1]["cue_id"] == "right"


def _generate_test_mp3(path, duration_sec: float, freq: int = 1000) -> bytes:
    from services.subdub_tts_artifact_validator import resolve_ffmpeg_path
    import subprocess
    ffmpeg_bin = resolve_ffmpeg_path()
    assert ffmpeg_bin and Path(ffmpeg_bin).is_file()
    cmd = [
        ffmpeg_bin, "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency={freq}:duration={duration_sec}",
        "-c:a", "libmp3lame",
        "-b:a", "128k",
        str(path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return Path(path).read_bytes()


def test_real_decodable_mp3_pair_recovery_and_full_decode(tmp_path):
    """MANDATORY FIRST RED: Coalescing real MP3s produces valid ffmpeg-decodable audio."""
    from services.subdub_tts_artifact_validator import validate_tts_audio_artifact, resolve_ffmpeg_path
    import subprocess

    p1 = tmp_path / "c1.mp3"
    p2 = tmp_path / "c2.mp3"
    b1 = _generate_test_mp3(p1, 1.0, 440)
    b2 = _generate_test_mp3(p2, 0.5, 880)

    c1 = {
        "cue_id": "c1",
        "speaker_id": "spk_1",
        "start": 0.0,
        "end": 2.0,
        "audio": b1,
        "audio_duration": 1.0,
        "text": "First phrase",
    }
    c2 = {
        "cue_id": "c2",
        "speaker_id": "spk_1",
        "start": 2.0,
        "end": 2.5,
        "audio": b2,
        "audio_duration": 0.5,
        "text": "micro",
    }
    merged = coalesce_cue_pair(c1, c2)
    assert merged["coalesced"] is True
    assert merged["right_cue_offset"] == pytest.approx(2.0)
    assert merged["gap_silence_seconds"] == pytest.approx(1.0)
    assert merged["audio_duration"] == pytest.approx(2.5, abs=0.08)

    # Output MUST NOT be raw byte concatenation (e.g. b1 + b2)
    assert merged["audio"] != b1 + b2

    out_p = tmp_path / "recovered.mp3"
    out_p.write_bytes(merged["audio"])

    v_res = validate_tts_audio_artifact(out_p)
    assert v_res.ok is True, f"Decodable audio validation failed: {v_res.detail}"
    assert v_res.status == "VALID"
    assert v_res.duration == pytest.approx(2.5, abs=0.1)

    # Full ffmpeg decode check
    ffmpeg_bin = resolve_ffmpeg_path()
    dec_cmd = [ffmpeg_bin, "-v", "error", "-i", str(out_p), "-f", "null", "-"]
    res = subprocess.run(dec_cmd, capture_output=True)
    assert res.returncode == 0, f"FFmpeg decode failed: {res.stderr.decode()}"


def test_gap_silence_and_offset_preserved_no_early_second_utterance(tmp_path):
    """MANDATORY FIRST RED: Silence gap is not collapsed, right cue starts at correct offset."""
    from services.subdub_tts_artifact_validator import resolve_ffmpeg_path
    import subprocess
    import struct

    p1 = tmp_path / "c1_silence.mp3"
    p2 = tmp_path / "c2_silence.mp3"
    b1 = _generate_test_mp3(p1, 1.0, 440)
    b2 = _generate_test_mp3(p2, 0.5, 880)

    c1 = {
        "cue_id": "c1",
        "speaker_id": "spk_1",
        "start": 0.0,
        "end": 2.0,
        "audio": b1,
        "audio_duration": 1.0,
        "text": "First",
    }
    c2 = {
        "cue_id": "c2",
        "speaker_id": "spk_1",
        "start": 2.0,
        "end": 2.5,
        "audio": b2,
        "audio_duration": 0.5,
        "text": "Second",
    }
    merged = coalesce_cue_pair(c1, c2)
    out_p = tmp_path / "merged_pcm.mp3"
    out_p.write_bytes(merged["audio"])

    # Decode to raw PCM s16le 16000Hz mono
    ffmpeg_bin = resolve_ffmpeg_path()
    dec_cmd = [
        ffmpeg_bin, "-y", "-i", str(out_p),
        "-f", "s16le", "-ac", "1", "-ar", "16000",
        "-"
    ]
    res = subprocess.run(dec_cmd, capture_output=True, check=True)
    pcm_bytes = res.stdout
    num_samples = len(pcm_bytes) // 2
    samples = struct.unpack(f"<{num_samples}h", pcm_bytes)

    # First utterance (0.0 to 1.0s = samples 0 to 16000): active sound
    max_part1 = max(abs(s) for s in samples[1600:14400])
    assert max_part1 > 1000, "Part 1 should have audible sound"

    # Gap silence (1.05s to 1.95s = samples 16800 to 31200): must be silence!
    max_silence = max(abs(s) for s in samples[17600:30400])
    assert max_silence < 100, f"Gap should be silent but got amplitude {max_silence}"

    # Second utterance (2.05s to 2.45s = samples 32800 to 39200): active sound
    max_part2 = max(abs(s) for s in samples[32800:39200])
    assert max_part2 > 1000, "Part 2 should have audible sound at offset 2.0s"


def test_incident_shape_7_36_plus_0_72_recovers_without_early_second_utterance():
    """MANDATORY FIRST RED: Incident shape 7.36s + 0.72s preserves 7.36s right cue offset."""
    c1 = {
        "cue_id": "c1",
        "speaker_id": "spk_1",
        "start": 30.24,
        "end": 37.60,
        "audio_duration": 6.17,
        "text": "Chiếc khóa này còn mới",
    }
    c2 = {
        "cue_id": "c2",
        "speaker_id": "spk_1",
        "start": 37.60,
        "end": 38.32,
        "audio_duration": 1.56,
        "text": "càng",
    }
    recovered = recover_cue_locked_micro_cues([c1, c2])
    assert len(recovered) == 1
    merged = recovered[0]
    assert merged["coalesced"] is True
    assert merged["right_cue_offset"] == pytest.approx(7.36)
    assert merged["gap_silence_seconds"] == pytest.approx(1.19, abs=0.01)
    assert merged["audio_duration"] == pytest.approx(8.92, abs=0.01)
    assert merged["cue_window"] == pytest.approx(8.08, abs=0.01)
    assert merged["fit_ratio"] == pytest.approx(1.104, abs=0.01)
    assert merged["fit_ratio"] <= 1.80


def test_long_offending_cue_with_short_neighbor_must_not_recover():
    """MANDATORY FIRST RED: A long offending cue (> 1.5s) must NOT recover with a short neighbor."""
    # c1 is offending (2.0s window, 4.0s audio -> fit_ratio = 2.0 > 1.80)
    # c2 is non-offending (0.5s window, 0.4s audio -> fit_ratio = 0.8 <= 1.80)
    c1 = {
        "cue_id": "c1_long",
        "speaker_id": "spk_1",
        "start": 0.0,
        "end": 2.0,
        "audio_duration": 4.0,
        "text": "Offending speech longer than microcue limit",
    }
    c2 = {
        "cue_id": "c2_short",
        "speaker_id": "spk_1",
        "start": 2.0,
        "end": 2.5,
        "audio_duration": 0.4,
        "text": "short",
    }
    recovered = recover_cue_locked_micro_cues([c1, c2])
    assert len(recovered) == 2, "Long offending cue must not trigger recovery!"
    assert recovered[0]["cue_id"] == "c1_long"
    assert recovered[1]["cue_id"] == "c2_short"
    assert "coalesced" not in recovered[0]


def test_shared_pipeline_post_recovery_gt_1_80_must_fail(tmp_path):
    """MANDATORY FIRST RED: Subtitle dub product pipeline must fail closed when post-recovery fit ratio > 1.80."""
    import asyncio
    from services.subtitle_dub_product_pipeline import process_subtitle_dub_job

    async def _run():
        source_media = tmp_path / "src.mp4"
        source_media.write_bytes(b"dummy")

        state = {
            "mode": "dub",
            "cue_locked_timing": True,
            "input_file": str(source_media),
            "source_path": str(source_media),
            "media_path": str(source_media),
            "segments": [
                {"start": 0.0, "end": 1.0, "text": "Sentence 1", "speaker": "spk_1"},
            ],
            "input_duration_seconds": 1.0,
        }

        async def fake_tts(*args, **kwargs):
            return {
                "ok": True,
                "provider": "mock",
                "chunks": [
                    {"start": 0.0, "end": 1.0, "audio_duration": 2.5, "audio_bytes": b"mock_audio"},
                ]
            }

        res = await process_subtitle_dub_job(
            mode="dub",
            state=state,
            user_id=1,
            prepare_subtitles=lambda s: {
                "state": s,
                "source_bytes": b"src",
                "content_type": "video/mp4",
                "source_segments": s["segments"],
                "output_segments": s["segments"],
                "output_script": "Sentence 1",
                "output_subtitle": "1\n00:00:00,000 --> 00:00:01,000\nSentence 1\n",
            },
            srt_from_text=lambda *a: "",
            segments_from_text=lambda *a: [],
            segments_from_subtitle=lambda *a: [],
            subtitle_output_items=lambda *a: [],
            resolve_voice_id=lambda *a: "v1",
            parse_voice_speed=lambda *a: 1.0,
            synthesize_segments=fake_tts,
            build_timeline_audio=lambda *args, **kwargs: (b"timeline", "ok"),
            normalize_audio=lambda a, *args: (a, "ok"),
            validate_audio=lambda a, *args: {"ok": True},
            render_video=lambda *args, **kwargs: (b"mp4", "ok"),
            video_render_ready=lambda *a: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
        )
        assert res["ok"] is False
        assert res["status"] == "TTS_EXTREME_COMPRESSION_FAILED"
        assert res["error_code"] == "extreme_audio_compression_unintelligible"

    asyncio.run(_run())


def test_exact_1_80_shared_pipeline_must_pass(tmp_path):
    """MANDATORY FIRST RED: Subtitle dub product pipeline with exact 1.800 fit ratio must pass."""
    import asyncio
    from services.subtitle_dub_product_pipeline import process_subtitle_dub_job

    async def _run():
        source_media = tmp_path / "src2.mp4"
        source_media.write_bytes(b"dummy")

        state = {
            "mode": "dub",
            "cue_locked_timing": True,
            "input_file": str(source_media),
            "source_path": str(source_media),
            "media_path": str(source_media),
            "segments": [
                {"start": 0.0, "end": 1.0, "text": "Sentence 1", "speaker": "spk_1"},
            ],
            "input_duration_seconds": 1.0,
        }

        async def fake_tts(*args, **kwargs):
            return {
                "ok": True,
                "provider": "mock",
                "chunks": [
                    {"start": 0.0, "end": 1.0, "audio_duration": 1.800, "audio_bytes": b"mock_audio"},
                ]
            }

        res = await process_subtitle_dub_job(
            mode="dub",
            state=state,
            user_id=1,
            prepare_subtitles=lambda s: {
                "state": s,
                "source_bytes": b"src",
                "content_type": "video/mp4",
                "source_segments": s["segments"],
                "output_segments": s["segments"],
                "output_script": "Sentence 1",
                "output_subtitle": "1\n00:00:00,000 --> 00:00:01,000\nSentence 1\n",
            },
            srt_from_text=lambda *a: "",
            segments_from_text=lambda *a: [],
            segments_from_subtitle=lambda *a: [],
            subtitle_output_items=lambda *a: [],
            resolve_voice_id=lambda *a: "v1",
            parse_voice_speed=lambda *a: 1.0,
            synthesize_segments=fake_tts,
            build_timeline_audio=lambda *args, **kwargs: (b"timeline", "ok"),
            normalize_audio=lambda a, *args: (a, "ok"),
            validate_audio=lambda a, *args: {"ok": True},
            render_video=lambda *args, **kwargs: (b"mp4", "ok"),
            video_render_ready=lambda *a: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
        )
        assert res.get("status") != "TTS_EXTREME_COMPRESSION_FAILED"

    asyncio.run(_run())


def test_ffmpeg_failure_cannot_return_raw_concat_media(monkeypatch, tmp_path):
    """MANDATORY FIRST RED: FFmpeg failure cannot fall back to raw concat media."""
    import subprocess
    from services.subdub_microcue_recovery import coalesce_cue_pair

    p1 = tmp_path / "c1.mp3"
    p2 = tmp_path / "c2.mp3"
    b1 = _generate_test_mp3(p1, 0.8, 440)
    b2 = _generate_test_mp3(p2, 0.4, 880)

    c1 = {"cue_id": "c1", "speaker_id": "s1", "start": 0.0, "end": 1.0, "audio": b1, "audio_duration": 0.8, "text": "one"}
    c2 = {"cue_id": "c2", "speaker_id": "s1", "start": 1.0, "end": 1.5, "audio": b2, "audio_duration": 0.4, "text": "two"}

    # Simulate ffmpeg failure
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=1, stdout=b"", stderr=b"ffmpeg error")

    monkeypatch.setattr(subprocess, "run", fake_run)

    merged = coalesce_cue_pair(c1, c2)
    # Must decline recovery and must NEVER return raw concat bytes
    assert merged.get("coalesced") is False or merged.get("audio") is None, "FFmpeg failure must decline recovery"
    assert merged.get("audio") != b1 + b2, "FFmpeg failure must never return raw byte concatenation"


def test_media_validation_failure_cannot_return_raw_concat_media(monkeypatch, tmp_path):
    """MANDATORY FIRST RED: Media validation failure cannot return raw concat media."""
    from types import SimpleNamespace
    import services.subdub_microcue_recovery as smr

    p1 = tmp_path / "c1.mp3"
    p2 = tmp_path / "c2.mp3"
    b1 = _generate_test_mp3(p1, 0.8, 440)
    b2 = _generate_test_mp3(p2, 0.4, 880)

    c1 = {"cue_id": "c1", "speaker_id": "s1", "start": 0.0, "end": 1.0, "audio": b1, "audio_duration": 0.8, "text": "one"}
    c2 = {"cue_id": "c2", "speaker_id": "s1", "start": 1.0, "end": 1.5, "audio": b2, "audio_duration": 0.4, "text": "two"}

    # Simulate validator rejecting output
    monkeypatch.setattr(
        smr,
        "validate_tts_audio_artifact",
        lambda *args, **kwargs: SimpleNamespace(ok=False, duration=0.0, status="INVALID", detail="corrupt audio"),
    )

    merged = smr.coalesce_cue_pair(c1, c2)
    assert merged.get("coalesced") is False or merged.get("audio") is None, "Validation failure must decline recovery"
    assert merged.get("audio") != b1 + b2, "Validation failure must never return raw byte concatenation"


def test_auto_speaker_gender_without_explicit_cue_lock_flag_gt_1_80_fails(tmp_path):
    """MANDATORY FIRST RED: auto_speaker_gender without explicit cue_locked_timing fails closed on > 1.80."""
    import asyncio
    from services.subtitle_dub_product_pipeline import process_subtitle_dub_job

    async def _run():
        source_media = tmp_path / "src_asg.mp4"
        source_media.write_bytes(b"dummy")

        state = {
            "mode": "dub",
            "voice_kind": "auto_speaker_gender",
            "voice_selection_mode": "auto_speaker",
            "input_file": str(source_media),
            "source_path": str(source_media),
            "media_path": str(source_media),
            "segments": [{"start": 0.0, "end": 1.0, "text": "Test"}],
            "input_duration_seconds": 1.0,
        }

        async def fake_tts(*args, **kwargs):
            return {
                "ok": True,
                "provider": "mock",
                "chunks": [{"start": 0.0, "end": 1.0, "audio_duration": 2.2, "audio_bytes": b"mock_audio"}],
            }

        res = await process_subtitle_dub_job(
            mode="dub",
            state=state,
            user_id=1,
            prepare_subtitles=lambda s: {
                "state": s,
                "source_bytes": b"src",
                "content_type": "video/mp4",
                "source_segments": s["segments"],
                "output_segments": s["segments"],
                "output_script": "Test",
                "output_subtitle": "1\n00:00:00,000 --> 00:00:01,000\nTest\n",
            },
            srt_from_text=lambda *a: "",
            segments_from_text=lambda *a: [],
            segments_from_subtitle=lambda *a: [],
            subtitle_output_items=lambda *a: [],
            resolve_voice_id=lambda *a: "v1",
            parse_voice_speed=lambda *a: 1.0,
            synthesize_segments=fake_tts,
            build_timeline_audio=lambda *args, **kwargs: (b"timeline", "ok"),
            normalize_audio=lambda a, *args: (a, "ok"),
            validate_audio=lambda a, *args: {"ok": True},
            render_video=lambda *args, **kwargs: (b"mp4", "ok"),
            video_render_ready=lambda *a: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
        )
        assert res["ok"] is False
        assert res["status"] == "TTS_EXTREME_COMPRESSION_FAILED"
        assert res["error_code"] == "extreme_audio_compression_unintelligible"

    asyncio.run(_run())


def test_smart_multivoice_without_explicit_cue_lock_flag_gt_1_80_fails(tmp_path):
    """MANDATORY FIRST RED: smart_multivoice without explicit cue_locked_timing fails closed on > 1.80."""
    import asyncio
    from services.subtitle_dub_product_pipeline import process_subtitle_dub_job

    async def _run():
        source_media = tmp_path / "src_smv.mp4"
        source_media.write_bytes(b"dummy")

        state = {
            "mode": "dub",
            "subdub_engine_selected": "smart_multivoice",
            "input_file": str(source_media),
            "source_path": str(source_media),
            "media_path": str(source_media),
            "segments": [{"start": 0.0, "end": 1.0, "text": "Test"}],
            "input_duration_seconds": 1.0,
        }

        async def fake_tts(*args, **kwargs):
            return {
                "ok": True,
                "provider": "mock",
                "chunks": [{"start": 0.0, "end": 1.0, "audio_duration": 2.2, "audio_bytes": b"mock_audio"}],
            }

        res = await process_subtitle_dub_job(
            mode="dub",
            state=state,
            user_id=1,
            prepare_subtitles=lambda s: {
                "state": s,
                "source_bytes": b"src",
                "content_type": "video/mp4",
                "source_segments": s["segments"],
                "output_segments": s["segments"],
                "output_script": "Test",
                "output_subtitle": "1\n00:00:00,000 --> 00:00:01,000\nTest\n",
            },
            srt_from_text=lambda *a: "",
            segments_from_text=lambda *a: [],
            segments_from_subtitle=lambda *a: [],
            subtitle_output_items=lambda *a: [],
            resolve_voice_id=lambda *a: "v1",
            parse_voice_speed=lambda *a: 1.0,
            synthesize_segments=fake_tts,
            build_timeline_audio=lambda *args, **kwargs: (b"timeline", "ok"),
            normalize_audio=lambda a, *args: (a, "ok"),
            validate_audio=lambda a, *args: {"ok": True},
            render_video=lambda *args, **kwargs: (b"mp4", "ok"),
            video_render_ready=lambda *a: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
        )
        assert res["ok"] is False
        assert res["status"] == "TTS_EXTREME_COMPRESSION_FAILED"
        assert res["error_code"] == "extreme_audio_compression_unintelligible"

    asyncio.run(_run())


def test_left_tts_longer_than_right_source_offset_must_not_shift_right_cue():
    """MANDATORY FIRST RED: Left TTS longer than right cue offset must NOT shift right cue, declines recovery."""
    from services.subdub_microcue_recovery import can_coalesce_cues, coalesce_cue_pair

    c1 = {
        "cue_id": "c1",
        "speaker_id": "s1",
        "start": 0.0,
        "end": 1.0,
        "audio_duration": 1.5,  # 1.5s > 1.0s (exceeds right cue start)
        "text": "left is too long",
    }
    c2 = {
        "cue_id": "c2",
        "speaker_id": "s1",
        "start": 1.0,
        "end": 1.5,
        "audio_duration": 0.4,
        "text": "right",
    }
    assert can_coalesce_cues(c1, c2) is False, "Overlapping left TTS must decline coalescing"

    merged = coalesce_cue_pair(c1, c2)
    assert merged.get("coalesced") is False or merged.get("right_cue_offset") == pytest.approx(1.0), (
        "Right cue offset must remain bound to original source offset 1.0s, not delayed to 1.5s"
    )


def test_unpreservable_internal_timing_must_decline_recovery():
    """MANDATORY FIRST RED: Unpreservable internal timing must decline recovery."""
    from services.subdub_microcue_recovery import recover_cue_locked_micro_cues

    c1 = {
        "cue_id": "c1",
        "speaker_id": "s1",
        "start": 0.0,
        "end": 0.8,
        "audio_duration": 1.2,  # Left TTS exceeds offset 0.8s
        "text": "Long left speech",
    }
    c2 = {
        "cue_id": "c2",
        "speaker_id": "s1",
        "start": 0.8,
        "end": 1.5,
        "audio_duration": 0.5,
        "text": "micro right",
    }
    recovered = recover_cue_locked_micro_cues([c1, c2])
    assert len(recovered) == 2, "Unpreservable timing must decline recovery"
    assert recovered[0]["cue_id"] == "c1"
    assert recovered[1]["cue_id"] == "c2"


def test_auto_smart_multivoice_without_explicit_cue_lock_flag_gt_1_80_fails(tmp_path):
    """MANDATORY FIRST RED: auto_smart_multivoice without explicit cue_locked_timing fails closed on > 1.80."""
    import asyncio
    from services.subtitle_dub_product_pipeline import process_subtitle_dub_job

    async def _run():
        source_media = tmp_path / "src_asmv.mp4"
        source_media.write_bytes(b"dummy")

        state = {
            "mode": "dub",
            "auto_speaker_lane": "auto_smart_multivoice",
            "input_file": str(source_media),
            "source_path": str(source_media),
            "media_path": str(source_media),
            "segments": [{"start": 0.0, "end": 1.0, "text": "Test"}],
            "input_duration_seconds": 1.0,
        }

        async def fake_tts(*args, **kwargs):
            return {
                "ok": True,
                "provider": "mock",
                "chunks": [{"start": 0.0, "end": 1.0, "audio_duration": 2.2, "audio_bytes": b"mock_audio"}],
            }

        res = await process_subtitle_dub_job(
            mode="dub",
            state=state,
            user_id=1,
            prepare_subtitles=lambda s: {
                "state": s,
                "source_bytes": b"src",
                "content_type": "video/mp4",
                "source_segments": s["segments"],
                "output_segments": s["segments"],
                "output_script": "Test",
                "output_subtitle": "1\n00:00:00,000 --> 00:00:01,000\nTest\n",
            },
            srt_from_text=lambda *a: "",
            segments_from_text=lambda *a: [],
            segments_from_subtitle=lambda *a: [],
            subtitle_output_items=lambda *a: [],
            resolve_voice_id=lambda *a: "v1",
            parse_voice_speed=lambda *a: 1.0,
            synthesize_segments=fake_tts,
            build_timeline_audio=lambda *args, **kwargs: (b"timeline", "ok"),
            normalize_audio=lambda a, *args: (a, "ok"),
            validate_audio=lambda a, *args: {"ok": True},
            render_video=lambda *args, **kwargs: (b"mp4", "ok"),
            video_render_ready=lambda *a: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
        )
        assert res["ok"] is False
        assert res["status"] == "TTS_EXTREME_COMPRESSION_FAILED"
        assert res["error_code"] == "extreme_audio_compression_unintelligible"

    asyncio.run(_run())


