from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import wave
import zlib
from pathlib import Path

import pytest

from services import podcast_video_engine as engine
from services import video_engine_contract


RUNTIME_SHA = "d" * 40


def _binary(name: str) -> str:
    return str(os.environ.get(f"PODCAST_VIDEO_{name.upper()}") or shutil.which(name) or "")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_png(path: Path, rgb: tuple[int, int, int], width: int = 160, height: int = 100) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    rows: list[bytes] = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            delta = 25 if (x // 16 + y // 16) % 2 else 0
            row.extend(min(255, value + delta) for value in rgb)
        rows.append(bytes(row))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + chunk(b"IEND", b"")
    )


def _write_wav(
    path: Path,
    duration_seconds: float = 3.0,
    sample_rate: int = 16_000,
    frequencies: tuple[float, float] = (330.0, 550.0),
) -> None:
    frame_count = int(duration_seconds * sample_rate)
    frames = bytearray()
    for index in range(frame_count):
        second = index / sample_rate
        frequency = frequencies[0] if second < duration_seconds / 2 else frequencies[1]
        sample = int(0.28 * 32767 * math.sin(2 * math.pi * frequency * second))
        frames.extend(struct.pack("<h", sample))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(bytes(frames))


def _write_video_with_audio(path: Path, duration_seconds: float = 3.0) -> None:
    ffmpeg = _binary("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is required")
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x334455:s=160x100:r=24:d={duration_seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=16000:duration={duration_seconds}",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def _source(path: Path, source_type: str = "audio") -> dict:
    return {
        "source_id": f"podcast-source-{source_type}-29k",
        "source_type": source_type,
        "path": str(path),
        "sha256": _sha256(path),
        "rights_approved": True,
        "rights_receipt_id": "podcast-source-rights-29k",
    }


def _transcript(source: dict, *, speaker_count: int = 1, diarization: dict | None = None) -> dict:
    speaker_ids = ["speaker-1", "speaker-2", "speaker-1"] if speaker_count > 1 else ["", "", ""]
    return {
        "status": "completed",
        "source_fingerprint": engine.podcast_source_fingerprint(source),
        "transcriber": "approved_fixture_transcript_v1",
        "language": "en",
        "speaker_count": speaker_count,
        "diarization": dict(diarization or {}),
        "segments": [
            {
                "segment_id": f"segment-{index}",
                "start_seconds": float(index - 1),
                "end_seconds": float(index),
                "text": text,
                "speaker_id": speaker_ids[index - 1],
            }
            for index, text in enumerate(
                (
                    "Welcome to the approved local podcast fixture.",
                    "The middle segment explains the grounded topic.",
                    "The final segment closes without clipped speech.",
                ),
                start=1,
            )
        ],
    }


def _scenes(paths: list[Path]) -> list[dict]:
    count = len(paths)
    if count == 1:
        ranges = [(0.0, 3.0, ["segment-1", "segment-2", "segment-3"])]
    else:
        ranges = [
            (float(index - 1), float(index), [f"segment-{index}"])
            for index in range(1, count + 1)
        ]
    return [
        {
            "scene_id": f"scene-{index}",
            "scene_index": index,
            "start_seconds": start,
            "end_seconds": end,
            "transcript_segment_ids": segment_ids,
            "speaker_ids": ["speaker-1"],
            "visual_prompt": f"Approved podcast visual {index}",
            "asset_id": f"podcast-asset-{index}",
            "asset_path": str(path),
            "asset_sha256": _sha256(path),
            "asset_rights_approved": True,
            "asset_rights_receipt_id": "podcast-visual-rights-29k",
            "motion": "ken_burns" if count == 1 else "pan_horizontal",
        }
        for index, (path, (start, end, segment_ids)) in enumerate(
            zip(paths, ranges),
            start=1,
        )
    ]


def _flags(**overrides: str) -> dict[str, str]:
    values = dict(engine.PODCAST_VIDEO_ENGINE_FLAG_DEFAULTS)
    values.update(overrides)
    return values


def _manifest(**overrides) -> dict:
    values = video_engine_contract.build_worker_manifest(
        worker_sha=RUNTIME_SHA,
        worker_instance_id="fixture-worker-29k",
        supported_products=["podcast_video"],
        supported_modes=["single_scene", "multi_scene"],
        renderer_name="local-ffmpeg-podcast-engine",
        renderer_version="29k-test",
        ffmpeg_version="fixture-local",
        provider_enabled=False,
        local_enabled=True,
        queue_ready=True,
        worker_connected=True,
        heartbeat_fresh=True,
        health_ok=True,
        worker_status="healthy",
        capabilities=[engine.CANONICAL_WORKER_CAPABILITY],
        local_capabilities={engine.CANONICAL_WORKER_CAPABILITY: True},
        provider_availability={},
    )
    values.update({"engine_adapters": [engine.ENGINE_ADAPTER], "artifact_ready": True})
    values.update(overrides)
    return values


def _plan(source_path: Path, images: list[Path], **overrides):
    source = overrides.pop("source", _source(source_path))
    transcript = overrides.pop("transcript", _transcript(source))
    return engine.compile_podcast_video_plan(
        source=source,
        transcript=transcript,
        scenes=overrides.pop("scenes", _scenes(images)),
        mode=overrides.pop("mode", "single_scene" if len(images) == 1 else "multi_scene"),
        layout_mode=overrides.pop(
            "layout_mode",
            "single_visual" if len(images) == 1 else "scene_visuals",
        ),
        aspect_ratio=overrides.pop("aspect_ratio", "1:1"),
        captions_enabled=overrides.pop("captions_enabled", True),
        waveform_enabled=overrides.pop("waveform_enabled", False),
        final_assets=overrides.pop("final_assets", {}),
        ffprobe_path=_binary("ffprobe"),
        **overrides,
    )


def _request(plan: engine.PodcastVideoPlan, **overrides):
    return engine.build_podcast_video_request(
        user_id=172203,
        confirmation_id="confirm-29k",
        language="vi",
        plan=plan,
        explicit_confirmation_receipt={"confirmation_id": "confirm-29k"},
        runtime_sha=RUNTIME_SHA,
        expected_worker_sha=RUNTIME_SHA,
        admin_no_charge=True,
        **overrides,
    )


def test_29k_default_off_route_and_exact_local_contract() -> None:
    assert engine.ALLOWED_SOURCE_TYPES == ("audio", "video")
    assert engine.SUPPORTED_LAYOUTS == ("single_visual", "scene_visuals", "speaker_layout")
    assert engine.podcast_video_engine_flags({}) == {
        name: False for name in engine.PODCAST_VIDEO_ENGINE_FLAG_DEFAULTS
    }
    profile = video_engine_contract.product_route_contract("podcast_video")
    assert profile["state"] == "PROFILE_ONLY"
    assert profile["connected"] is False
    blocked_route = video_engine_contract.product_route_contract(
        "podcast_video",
        mode="single_scene",
        environ=_flags(PODCAST_VIDEO_ENGINE_ENABLED="1"),
    )
    assert blocked_route["state"] == "ENGINE_MISSING"
    assert blocked_route["connected"] is False
    assert blocked_route["blocker"] == "podcast_runtime_entrypoint_missing"
    route = video_engine_contract.product_route_contract(
        "podcast_video",
        mode="single_scene",
        environ=_flags(
            PODCAST_VIDEO_ENGINE_ENABLED="1",
            PODCAST_VIDEO_RUNTIME_REGISTERED="1",
        ),
    )
    assert route == engine.shared_podcast_video_engine_route()
    contract = engine.podcast_video_engine_contract()
    assert contract["provider_required"] is False
    assert contract["automatic_asr"] is False
    assert contract["automatic_diarization"] is False
    assert contract["music_generation"] is False
    assert contract["production_finalizer_ready"] is False
    assert contract["durable_exactly_once"] is False
    assert contract["production_finalizer_blocker"] == "podcast_production_finalizer_missing"
    assert "suno" not in json.dumps(contract).lower()


def test_29k_audio_and_video_sources_require_real_speech_audio_and_stable_fingerprints(tmp_path: Path) -> None:
    if not _binary("ffprobe"):
        pytest.skip("ffprobe is required")
    audio = tmp_path / "podcast.wav"
    video = tmp_path / "podcast.mp4"
    silent_video = tmp_path / "silent.mp4"
    _write_wav(audio)
    _write_video_with_audio(video)
    ffmpeg = _binary("ffmpeg")
    completed = subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=s=160x100:r=24:d=3", "-an", str(silent_video)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    audio_source = _source(audio, "audio")
    video_source = _source(video, "video")
    first = engine.probe_podcast_source(audio_source, ffprobe_path=_binary("ffprobe"))
    second = engine.probe_podcast_source(audio_source, ffprobe_path=_binary("ffprobe"))
    assert first == second
    assert first["audio_stream_count"] == 1
    assert first["audio_stream_indexes"] == (0,)
    assert first["selected_audio_stream_index"] == 0
    assert first["duration_seconds"] == pytest.approx(3.0, abs=0.08)
    assert first["source_fingerprint"] == engine.podcast_source_fingerprint(audio_source)
    assert engine.probe_podcast_source(video_source, ffprobe_path=_binary("ffprobe"))["video_stream_count"] == 1
    with pytest.raises(ValueError, match="podcast_source_audio_required"):
        engine.probe_podcast_source(_source(silent_video, "video"), ffprobe_path=_binary("ffprobe"))


def test_29k_one_speaker_allows_no_diarization_but_multispeaker_fails_closed(tmp_path: Path) -> None:
    if not _binary("ffprobe"):
        pytest.skip("ffprobe is required")
    audio = tmp_path / "podcast.wav"
    image = tmp_path / "visual.png"
    _write_wav(audio)
    _write_png(image, (90, 140, 210))
    plan = _plan(audio, [image])
    assert plan.speaker_count == 1
    assert plan.diarization["required"] is False
    assert plan.active_speaker_accuracy_claimed is False
    source = _source(audio)
    with pytest.raises(ValueError, match="podcast_diarization_required"):
        _plan(
            audio,
            [image],
            source=source,
            transcript=_transcript(source, speaker_count=2),
        )


def test_29k_speaker_layout_requires_confident_diarization_and_explicit_qc(tmp_path: Path) -> None:
    if not _binary("ffprobe"):
        pytest.skip("ffprobe is required")
    audio = tmp_path / "podcast.wav"
    image = tmp_path / "speakers.png"
    _write_wav(audio)
    _write_png(image, (120, 90, 190))
    source = _source(audio)
    base_diarization = {
        "status": "completed",
        "model": "approved_fixture_diarizer_v1",
        "confidence": 0.95,
        "active_speaker_qc_passed": False,
    }
    with pytest.raises(ValueError, match="podcast_active_speaker_qc_required"):
        _plan(
            audio,
            [image],
            source=source,
            transcript=_transcript(source, speaker_count=2, diarization=base_diarization),
            layout_mode="speaker_layout",
        )
    accepted = _plan(
        audio,
        [image],
        source=source,
        transcript=_transcript(
            source,
            speaker_count=2,
            diarization={**base_diarization, "active_speaker_qc_passed": True},
        ),
        layout_mode="speaker_layout",
        scenes=[{**_scenes([image])[0], "speaker_ids": ["speaker-1", "speaker-2"]}],
    )
    assert accepted.active_speaker_accuracy_claimed is True
    assert accepted.diarization["confidence"] == pytest.approx(0.95)


def test_29k_plan_freezes_timeline_transcript_assets_and_rights(tmp_path: Path) -> None:
    if not _binary("ffprobe"):
        pytest.skip("ffprobe is required")
    audio = tmp_path / "podcast.wav"
    images = [tmp_path / f"scene-{index}.png" for index in range(1, 4)]
    _write_wav(audio)
    for path, color in zip(images, ((210, 90, 80), (70, 180, 100), (70, 100, 210))):
        _write_png(path, color)
    plan = _plan(audio, images, waveform_enabled=True)
    assert plan.mode == "multi_scene"
    assert plan.layout_mode == "scene_visuals"
    assert plan.source_sha256 == _sha256(audio)
    assert plan.source_audio_stream_index == 0
    assert plan.source_rights_receipt_id == "podcast-source-rights-29k"
    request = _request(plan)
    assert request.approved_plan["source_rights_receipt_id"] == "podcast-source-rights-29k"
    assert request.input_assets[0]["rights_receipt_id"] == "podcast-source-rights-29k"
    assert request.audio_policy["selected_audio_stream_index"] == 0
    assert len(plan.transcript_sha256) == 64
    assert [scene.scene_index for scene in plan.scenes] == [1, 2, 3]
    assert [scene.start_seconds for scene in plan.scenes] == [0.0, 1.0, 2.0]
    assert [scene.end_seconds for scene in plan.scenes] == [1.0, 2.0, 3.0]
    assert plan.scenes[0].asset_sha256 == _sha256(images[0])
    assert plan.transcript_coverage_sha256
    assert engine.validate_podcast_video_plan(plan)["ok"] is True


def test_29k_rejects_timeline_gap_duplicate_segment_invalid_ratio_and_missing_asset(tmp_path: Path) -> None:
    if not _binary("ffprobe"):
        pytest.skip("ffprobe is required")
    audio = tmp_path / "podcast.wav"
    images = [tmp_path / f"scene-{index}.png" for index in range(1, 4)]
    _write_wav(audio)
    for path, color in zip(images, ((210, 90, 80), (70, 180, 100), (70, 100, 210))):
        _write_png(path, color)
    scenes = _scenes(images)
    with pytest.raises(ValueError, match="podcast_scene_timeline_gap"):
        _plan(audio, images, scenes=[scenes[0], {**scenes[1], "start_seconds": 1.2}, scenes[2]])
    with pytest.raises(ValueError, match="podcast_transcript_segment_coverage_invalid"):
        _plan(
            audio,
            images,
            scenes=[scenes[0], {**scenes[1], "transcript_segment_ids": ["segment-1"]}, scenes[2]],
        )
    with pytest.raises(ValueError, match="podcast_aspect_ratio_unsupported"):
        _plan(audio, [images[0]], aspect_ratio="3:2")
    with pytest.raises(ValueError, match="podcast_scene_asset_missing"):
        _plan(audio, [images[0]], scenes=[{**_scenes([images[0]])[0], "asset_path": str(tmp_path / "missing.png")}])


def test_29k_rejects_subsecond_scene_before_compositor_clamp(tmp_path: Path) -> None:
    if not _binary("ffprobe"):
        pytest.skip("ffprobe is required")
    audio = tmp_path / "podcast.wav"
    images = [tmp_path / f"scene-{index}.png" for index in range(1, 4)]
    _write_wav(audio)
    for path, color in zip(images, ((210, 90, 80), (70, 180, 100), (70, 100, 210))):
        _write_png(path, color)
    source = _source(audio)
    transcript = _transcript(source)
    transcript["segments"] = [
        {**transcript["segments"][0], "start_seconds": 0.0, "end_seconds": 0.75},
        {**transcript["segments"][1], "start_seconds": 0.75, "end_seconds": 1.75},
        {**transcript["segments"][2], "start_seconds": 1.75, "end_seconds": 3.0},
    ]
    scenes = _scenes(images)
    scenes = [
        {**scenes[0], "start_seconds": 0.0, "end_seconds": 0.75},
        {**scenes[1], "start_seconds": 0.75, "end_seconds": 1.75},
        {**scenes[2], "start_seconds": 1.75, "end_seconds": 3.0},
    ]
    with pytest.raises(ValueError, match="podcast_scene_timeline_invalid"):
        _plan(audio, images, source=source, transcript=transcript, scenes=scenes)


def test_29k_string_false_remains_false_in_plan_and_request(tmp_path: Path) -> None:
    if not _binary("ffprobe"):
        pytest.skip("ffprobe is required")
    audio = tmp_path / "podcast.wav"
    image = tmp_path / "visual.png"
    _write_wav(audio)
    _write_png(image, (90, 140, 210))
    plan = _plan(
        audio,
        [image],
        captions_enabled="false",
        waveform_enabled="false",
    )
    request = engine.build_podcast_video_request(
        user_id=172203,
        confirmation_id="confirm-strict-bool-29k",
        language="vi",
        plan=plan,
        explicit_confirmation_receipt={"confirmation_id": "confirm-strict-bool-29k"},
        runtime_sha=RUNTIME_SHA,
        expected_worker_sha=RUNTIME_SHA,
        admin_no_charge="false",
    )
    assert plan.captions_enabled is False
    assert plan.waveform_enabled is False
    assert request.payload["admin_no_charge"] is False


def test_29k_srt_writer_neutralizes_timing_and_style_injection(tmp_path: Path) -> None:
    if not _binary("ffprobe"):
        pytest.skip("ffprobe is required")
    audio = tmp_path / "podcast.wav"
    image = tmp_path / "visual.png"
    _write_wav(audio)
    _write_png(image, (90, 140, 210))
    source = _source(audio)
    transcript = _transcript(source)
    transcript["segments"][1]["text"] = (
        "Safe line\n9\n00:00:00,000 --> 99:59:59,999\n"
        "{\\an8}<font color='red'>Injected style</font>"
    )
    plan = _plan(audio, [image], source=source, transcript=transcript)
    srt_path = tmp_path / "podcast.srt"
    engine._write_transcript_srt(plan, srt_path)
    rendered = srt_path.read_text(encoding="utf-8")
    assert rendered.count("-->") == len(plan.transcript_segments)
    assert "{\\an8}" not in rendered
    assert "<font" not in rendered
    assert "Injected style" in rendered


def test_29k_default_off_dispatch_and_forbidden_automatic_policy_have_zero_side_effects(tmp_path: Path) -> None:
    if not _binary("ffprobe"):
        pytest.skip("ffprobe is required")
    audio = tmp_path / "podcast.wav"
    image = tmp_path / "visual.png"
    _write_wav(audio)
    _write_png(image, (90, 140, 210))
    plan = _plan(audio, [image])
    request = _request(plan)
    ledger = engine.PodcastVideoEngineLedger()
    disabled = engine.dispatch_podcast_video(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        environ={},
    )
    assert disabled["blocker"] == "podcast_video_engine_disabled"
    assert disabled["submitted"] is False
    for flag_name, blocker in (
        ("PODCAST_VIDEO_AUTO_RETRY", "automatic_retry_forbidden"),
        ("PODCAST_VIDEO_AUTO_FALLBACK", "automatic_fallback_forbidden"),
    ):
        result = engine.dispatch_podcast_video(
            request,
            plan=plan,
            manifest=_manifest(),
            runtime_sha=RUNTIME_SHA,
            ledger=ledger,
            environ=_flags(PODCAST_VIDEO_ENGINE_ENABLED="1", **{flag_name: "1"}),
        )
        assert result["blocker"] == blocker
    assert ledger.provider_calls == 0
    assert ledger.delivery_count == 0


def test_29k_local_executor_does_not_self_register_without_fixture_mode(
    tmp_path: Path,
) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    audio = tmp_path / "podcast.wav"
    image = tmp_path / "visual.png"
    _write_wav(audio)
    _write_png(image, (90, 140, 210))
    plan = _plan(audio, [image])
    ledger = engine.PodcastVideoEngineLedger()
    result = engine.execute_podcast_video_local(
        _request(plan),
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(PODCAST_VIDEO_ENGINE_ENABLED="1"),
        source_path=str(audio),
        asset_paths={plan.scenes[0].asset_id: str(image)},
        ffmpeg_path=_binary("ffmpeg"),
        ffprobe_path=_binary("ffprobe"),
    )
    assert result["ok"] is False
    assert result["blocker"] == "podcast_runtime_entrypoint_missing"
    assert ledger.render_count == 0
    assert ledger.compose_count == 0


def test_29k_single_scene_renders_real_captioned_waveform_mp4_without_clipped_speech(tmp_path: Path) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    audio = tmp_path / "podcast.wav"
    image = tmp_path / "visual.png"
    _write_wav(audio)
    _write_png(image, (90, 140, 210))
    plan = _plan(audio, [image], waveform_enabled=True, captions_enabled=True)
    request = _request(plan)
    ledger = engine.PodcastVideoEngineLedger()
    result = engine.execute_podcast_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(PODCAST_VIDEO_ENGINE_ENABLED="1"),
        fixture_mode=True,
        source_path=str(audio),
        asset_paths={plan.scenes[0].asset_id: str(image)},
        ffmpeg_path=_binary("ffmpeg"),
        ffprobe_path=_binary("ffprobe"),
    )
    assert result["ok"] is True, json.dumps(result["validation"], indent=2)
    assert result["validation"]["full_decode"] is True
    assert result["validation"]["audio_stream_count"] == 1
    assert result["validation"]["speech_audio_continuity"] is True
    assert result["validation"]["speech_content_match"] is True
    assert result["validation"]["speech_content_similarity"] >= engine.SPEECH_CONTENT_SIMILARITY_MIN
    assert result["validation"]["selected_source_audio_stream_index"] == 0
    assert len(result["validation"]["source_speech_pcm_sha256"]) == 64
    assert len(result["validation"]["output_speech_pcm_sha256"]) == 64
    assert len(result["validation"]["source_speech_feature_sha256"]) == 64
    assert len(result["validation"]["output_speech_feature_sha256"]) == 64
    assert result["validation"]["speech_clipped"] is False
    assert result["validation"]["captions_applied"] is True
    assert result["validation"]["waveform_applied"] is True
    assert result["validation"]["caption_visual_evidence"]["changed"] is True
    assert result["validation"]["waveform_visual_evidence"]["changed"] is True
    assert result["validation"]["transcript_coverage_complete"] is True
    assert Path(result["output_path"]).stat().st_size > 1000
    evidence_dir = Path(result["evidence_dir"])
    source_manifest = json.loads((evidence_dir / "podcast_source_manifest.json").read_text(encoding="utf-8"))
    assert source_manifest["source_sha256"] == _sha256(audio)
    assert source_manifest["source_audio_stream_index"] == 0
    assert source_manifest["source_rights_receipt_id"] == "podcast-source-rights-29k"
    assert (evidence_dir / "source_speech_pcm.wav").is_file()
    assert (evidence_dir / "output_speech_pcm.wav").is_file()
    subtitle_text = (evidence_dir / "podcast_transcript.srt").read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,000" in subtitle_text
    assert "without clipped speech" in subtitle_text
    replay = engine.execute_podcast_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(PODCAST_VIDEO_ENGINE_ENABLED="1"),
        fixture_mode=True,
        source_path=str(audio),
        asset_paths={plan.scenes[0].asset_id: str(image)},
        ffmpeg_path=_binary("ffmpeg"),
        ffprobe_path=_binary("ffprobe"),
    )
    assert replay["idempotent_replay"] is True
    assert ledger.render_count == 1
    assert ledger.compose_count == 1


def test_29k_multiscene_renders_every_scene_once_with_original_audio_continuity(tmp_path: Path) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    audio = tmp_path / "podcast.wav"
    images = [tmp_path / f"scene-{index}.png" for index in range(1, 4)]
    _write_wav(audio)
    for path, color in zip(images, ((210, 90, 80), (70, 180, 100), (70, 100, 210))):
        _write_png(path, color)
    plan = _plan(audio, images, captions_enabled=True)
    ledger = engine.PodcastVideoEngineLedger()
    result = engine.execute_podcast_video_local(
        _request(plan),
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(PODCAST_VIDEO_ENGINE_ENABLED="1"),
        fixture_mode=True,
        source_path=str(audio),
        asset_paths={scene.asset_id: scene.asset_path for scene in plan.scenes},
        ffmpeg_path=_binary("ffmpeg"),
        ffprobe_path=_binary("ffprobe"),
    )
    assert result["ok"] is True
    assert result["validation"]["scene_order"] == [1, 2, 3]
    assert result["validation"]["compositor_scene_order"] == [1, 2, 3]
    assert result["validation"]["compositor_scene_coverage_valid"] is True
    assert result["validation"]["scene_coverage_complete"] is True
    assert result["validation"]["transcript_segment_count"] == 3
    assert result["validation"]["speech_audio_continuity"] is True
    assert result["validation"]["output_duration_seconds"] == pytest.approx(3.0, abs=0.18)
    assert ledger.render_count == 3
    assert ledger.compose_count == 1
    assert ledger.provider_calls == 0


def test_29k_compositor_exception_fails_closed_without_escaping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    audio = tmp_path / "podcast.wav"
    image = tmp_path / "visual.png"
    _write_wav(audio)
    _write_png(image, (90, 140, 210))
    plan = _plan(audio, [image])

    def explode(**_kwargs):
        raise RuntimeError("fixture compositor failure")

    monkeypatch.setattr(engine.pipeline, "finalize_multiscene_scene_clips", explode)
    result = engine.execute_podcast_video_local(
        _request(plan),
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=engine.PodcastVideoEngineLedger(),
        output_root=tmp_path / "jobs",
        environ=_flags(PODCAST_VIDEO_ENGINE_ENABLED="1"),
        fixture_mode=True,
        source_path=str(audio),
        asset_paths={plan.scenes[0].asset_id: str(image)},
        ffmpeg_path=_binary("ffmpeg"),
        ffprobe_path=_binary("ffprobe"),
    )
    assert result["ok"] is False
    assert result["blocker"] == "podcast_composition_failed"
    assert result["terminal_state"] == "failed_no_charge"


def test_29k_rejects_compositor_scene_order_self_attestation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    audio = tmp_path / "podcast.wav"
    image = tmp_path / "visual.png"
    _write_wav(audio)
    _write_png(image, (90, 140, 210))
    plan = _plan(audio, [image])

    def wrong_order(**kwargs):
        return {
            "ok": True,
            "final_video_path": kwargs["scene_clip_paths"][1],
            "scene_order": [2],
            "scene_coverage_count": 1,
            "scene_coverage_expected": 1,
            "scene_coverage_valid_bool": True,
            "missing_scene_indexes": [],
            "concat_output_valid": True,
            "final_mp4_valid": True,
        }

    monkeypatch.setattr(
        engine.pipeline,
        "finalize_multiscene_scene_clips",
        wrong_order,
    )
    result = engine.execute_podcast_video_local(
        _request(plan),
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=engine.PodcastVideoEngineLedger(),
        output_root=tmp_path / "jobs",
        environ=_flags(PODCAST_VIDEO_ENGINE_ENABLED="1"),
        fixture_mode=True,
        source_path=str(audio),
        asset_paths={plan.scenes[0].asset_id: str(image)},
        ffmpeg_path=_binary("ffmpeg"),
        ffprobe_path=_binary("ffprobe"),
    )
    assert result["ok"] is False
    assert result["blocker"] == "podcast_composition_scene_coverage_invalid"


def test_29k_compositor_uses_the_explicit_selected_ffmpeg_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    audio = tmp_path / "podcast.wav"
    image = tmp_path / "visual.png"
    fake_ffmpeg = tmp_path / "fake-ffmpeg.exe"
    _write_wav(audio)
    _write_png(image, (90, 140, 210))
    fake_ffmpeg.write_bytes(b"not-an-ffmpeg-binary")
    monkeypatch.setenv("FFMPEG_PATH", str(fake_ffmpeg))
    plan = _plan(audio, [image])
    captured: dict[str, str] = {}

    def inspect_binary(**kwargs):
        captured["ffmpeg"] = engine.pipeline._ffmpeg_path()
        return {
            "ok": True,
            "final_video_path": kwargs["scene_clip_paths"][1],
            "scene_count": 1,
            "scene_order": [2],
            "scene_coverage_count": 1,
            "scene_coverage_expected": 1,
            "scene_coverage_valid_bool": True,
            "missing_scene_indexes": [],
            "concat_output_valid": True,
            "final_mp4_valid": True,
        }

    monkeypatch.setattr(
        engine.pipeline,
        "finalize_multiscene_scene_clips",
        inspect_binary,
    )
    result = engine.execute_podcast_video_local(
        _request(plan),
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=engine.PodcastVideoEngineLedger(),
        output_root=tmp_path / "jobs",
        environ=_flags(PODCAST_VIDEO_ENGINE_ENABLED="1"),
        fixture_mode=True,
        source_path=str(audio),
        asset_paths={plan.scenes[0].asset_id: str(image)},
        ffmpeg_path=_binary("ffmpeg"),
        ffprobe_path=_binary("ffprobe"),
    )
    assert Path(captured["ffmpeg"]).resolve() == Path(_binary("ffmpeg")).resolve()
    assert result["blocker"] == "podcast_composition_scene_coverage_invalid"


def test_29k_full_decode_uses_xerror(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(command, **_kwargs):
        captured["command"] = list(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(engine.subprocess, "run", fake_run)
    result = engine._full_decode("fixture.mp4", "ffmpeg")
    assert result["ok"] is True
    assert "-xerror" in captured["command"]
    assert captured["command"].index("-xerror") < captured["command"].index("-i")


def test_29k_overlay_visual_evidence_rejects_unchanged_region(tmp_path: Path) -> None:
    if not _binary("ffmpeg"):
        pytest.skip("ffmpeg is required")
    video = tmp_path / "unchanged.mp4"
    _write_video_with_audio(video)
    evidence = engine._overlay_visual_evidence(
        baseline_path=video,
        output_path=video,
        ffmpeg=_binary("ffmpeg"),
        timestamp_seconds=0.5,
        width=160,
        height=100,
        position="center",
        width_ratio=0.5,
        height_ratio=0.5,
    )
    assert evidence["changed"] is False
    assert evidence["mean_absolute_difference"] == 0.0
    assert evidence["baseline_frame_sha256"] == evidence["output_frame_sha256"]


def test_29k_speech_content_proof_rejects_unrelated_pcm(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    matching = tmp_path / "matching.wav"
    unrelated = tmp_path / "unrelated.wav"
    _write_wav(source, frequencies=(330.0, 550.0))
    _write_wav(matching, frequencies=(330.0, 550.0))
    _write_wav(unrelated, frequencies=(880.0, 990.0))
    accepted = engine.compare_speech_pcm_content(source, matching)
    rejected = engine.compare_speech_pcm_content(source, unrelated)
    assert accepted["content_match"] is True
    assert accepted["similarity"] == pytest.approx(1.0)
    assert rejected["content_match"] is False
    assert rejected["similarity"] < engine.SPEECH_CONTENT_SIMILARITY_MIN
    assert accepted["source_feature_sha256"]
    assert accepted["output_feature_sha256"]


def test_29k_logo_watermark_and_caption_positions_remain_independent(tmp_path: Path) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    audio = tmp_path / "podcast.wav"
    image = tmp_path / "visual.png"
    logo = tmp_path / "logo.png"
    _write_wav(audio)
    _write_png(image, (90, 140, 210))
    _write_png(logo, (30, 210, 220), width=48, height=48)
    plan = _plan(
        audio,
        [image],
        final_assets={
            "logo_enabled": True,
            "logo_asset_id": "podcast-logo",
            "logo_path": str(logo),
            "logo_sha256": _sha256(logo),
            "logo_rights_approved": True,
            "logo_rights_receipt_id": "podcast-logo-rights-29k",
            "logo_position": "top_left",
            "watermark_text": "PODCAST 29K",
            "watermark_position": "bottom_right",
            "caption_position": "bottom_center",
        },
    )
    request = _request(plan)
    logo_assets = [
        asset for asset in request.input_assets if asset.get("asset_id") == "podcast-logo"
    ]
    assert logo_assets == [
        {
            "asset_id": "podcast-logo",
            "asset_type": "image",
            "asset_sha256": _sha256(logo),
            "asset_bytes": logo.stat().st_size,
            "rights_receipt_id": "podcast-logo-rights-29k",
        }
    ]
    result = engine.execute_podcast_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=engine.PodcastVideoEngineLedger(),
        output_root=tmp_path / "jobs",
        environ=_flags(PODCAST_VIDEO_ENGINE_ENABLED="1"),
        fixture_mode=True,
        source_path=str(audio),
        asset_paths={plan.scenes[0].asset_id: str(image)},
        final_asset_paths={"podcast-logo": str(logo)},
        ffmpeg_path=_binary("ffmpeg"),
        ffprobe_path=_binary("ffprobe"),
    )
    assert result["ok"] is True
    assert result["validation"]["logo_applied"] is True
    assert result["validation"]["watermark_applied"] is True
    assert result["validation"]["logo_visual_evidence"]["changed"] is True
    assert result["validation"]["caption_visual_evidence"]["changed"] is True
    assert result["validation"]["watermark_visual_evidence"]["changed"] is True
    job_manifest = json.loads(
        (Path(result["evidence_dir"]) / "job_manifest.json").read_text(encoding="utf-8")
    )
    assert job_manifest["final_assets"]["logo_position"] == "top_left"
    assert job_manifest["final_assets"]["logo_rights_receipt_id"] == "podcast-logo-rights-29k"
    assert job_manifest["final_assets"]["watermark_position"] == "bottom_right"
    assert job_manifest["final_assets"]["caption_position"] == "bottom_center"


def test_29k_logo_requires_explicit_rights_receipt(tmp_path: Path) -> None:
    if not _binary("ffprobe"):
        pytest.skip("ffprobe is required")
    audio = tmp_path / "podcast.wav"
    image = tmp_path / "visual.png"
    logo = tmp_path / "logo.png"
    _write_wav(audio)
    _write_png(image, (90, 140, 210))
    _write_png(logo, (30, 210, 220), width=48, height=48)
    with pytest.raises(ValueError, match="podcast_logo_asset_rights_required"):
        _plan(
            audio,
            [image],
            final_assets={
                "logo_enabled": True,
                "logo_asset_id": "podcast-logo",
                "logo_path": str(logo),
                "logo_sha256": _sha256(logo),
            },
        )


def test_29k_finalization_is_exactly_once_and_admin_is_free(tmp_path: Path) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    audio = tmp_path / "podcast.wav"
    image = tmp_path / "visual.png"
    _write_wav(audio)
    _write_png(image, (90, 140, 210))
    plan = _plan(audio, [image])
    ledger = engine.PodcastVideoEngineLedger()
    rendered = engine.execute_podcast_video_local(
        _request(plan),
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(PODCAST_VIDEO_ENGINE_ENABLED="1"),
        fixture_mode=True,
        source_path=str(audio),
        asset_paths={plan.scenes[0].asset_id: str(image)},
        ffmpeg_path=_binary("ffmpeg"),
        ffprobe_path=_binary("ffprobe"),
    )
    calls: list[str] = []

    def deliver(_payload: dict) -> dict:
        calls.append("delivery")
        return {"accepted": True, "message_id": "fixture-message-29k", "production": False}

    def receipt(_payload: dict) -> dict:
        calls.append("receipt")
        return {"persisted": True, "receipt_id": "fixture-receipt-29k"}

    def report(_payload: dict) -> dict:
        calls.append("report")
        return {"emitted": True, "report_id": "fixture-report-29k"}

    first = engine.finalize_podcast_video_fixture(
        ledger=ledger,
        job_id=rendered["job_id"],
        deliverer=deliver,
        receipt_persister=receipt,
        terminal_reporter=report,
    )
    second = engine.finalize_podcast_video_fixture(
        ledger=ledger,
        job_id=rendered["job_id"],
        deliverer=deliver,
        receipt_persister=receipt,
        terminal_reporter=report,
    )
    assert first["ok"] is True
    assert second["idempotent_replay"] is True
    assert calls == ["delivery", "receipt", "report"]
    assert first["charge"] == {
        "recorded": True,
        "amount_xu": 0,
        "wallet_mutated": False,
        "fixture_only": True,
    }
    assert ledger.charge_attempts == 0
    assert ledger.provider_calls == 0
    assert ledger.paid_provider_calls == 0
    assert ledger.wallet_mutations == 0


def test_29k_production_finalizer_is_missing_and_invokes_no_callbacks(tmp_path: Path) -> None:
    artifact = tmp_path / "final.mp4"
    artifact.write_bytes(b"validated-local-podcast-artifact")
    base_record = {
        "job_id": "podcast-job",
        "artifact_path": str(artifact),
        "artifact_sha256": _sha256(artifact),
        "output_bytes": artifact.stat().st_size,
        "evidence_dir": str(tmp_path),
        "terminal_state": "rendered_validated",
        "validation": {"ok": True},
        "delivery": {},
        "receipt": {},
        "charge": {},
        "terminal_report": {},
        "admin_no_charge": True,
    }
    ledger = engine.PodcastVideoEngineLedger()
    ledger.records_by_job_id["production-job"] = {
        **base_record,
        "job_id": "production-job",
    }
    calls: list[str] = []

    def callback(name: str, result: dict):
        def invoke(_payload: dict) -> dict:
            calls.append(name)
            return result

        return invoke

    blocked = engine.finalize_podcast_video(
        ledger=ledger,
        job_id="production-job",
        deliverer=callback(
            "delivery",
            {"accepted": True, "message_id": "prod", "production": True},
        ),
        receipt_persister=callback(
            "receipt",
            {"persisted": True, "receipt_id": "forbidden"},
        ),
        charger=callback(
            "wallet",
            {"recorded": True, "amount_xu": 0, "wallet_mutated": True},
        ),
        terminal_reporter=callback("report", {"emitted": True}),
    )
    assert blocked["blocker"] == "podcast_production_finalizer_missing"
    assert blocked["ok"] is False
    assert calls == []
    assert ledger.delivery_count == 0
    assert ledger.receipt_count == 0
    assert ledger.charge_attempts == 0
    assert ledger.wallet_mutations == 0
    assert ledger.terminal_report_count == 0


def test_29k_fixture_finalizer_preflights_fixture_admin_and_wallet_before_callbacks(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "final.mp4"
    artifact.write_bytes(b"validated-local-podcast-artifact")
    base_record = {
        "job_id": "fixture-job",
        "artifact_path": str(artifact),
        "artifact_sha256": _sha256(artifact),
        "output_bytes": artifact.stat().st_size,
        "evidence_dir": str(tmp_path),
        "terminal_state": "rendered_validated",
        "validation": {"ok": True},
        "delivery": {},
        "receipt": {},
        "charge": {},
        "terminal_report": {},
    }
    scenarios = (
        (
            {**base_record, "fixture_only": "false", "admin_no_charge": True},
            "podcast_fixture_finalizer_forbidden",
        ),
        (
            {**base_record, "fixture_only": True, "admin_no_charge": False},
            "podcast_fixture_admin_no_charge_required",
        ),
        (
            {
                **base_record,
                "fixture_only": True,
                "admin_no_charge": True,
                "charge": {
                    "recorded": True,
                    "amount_xu": 1,
                    "wallet_mutated": True,
                },
            },
            "podcast_fixture_wallet_forbidden",
        ),
    )
    for index, (record, expected_blocker) in enumerate(scenarios, start=1):
        ledger = engine.PodcastVideoEngineLedger()
        job_id = f"fixture-job-{index}"
        ledger.records_by_job_id[job_id] = {**record, "job_id": job_id}
        calls: list[str] = []

        def called(name: str, response: dict):
            def invoke(_payload: dict) -> dict:
                calls.append(name)
                return response

            return invoke

        result = engine.finalize_podcast_video_fixture(
            ledger=ledger,
            job_id=job_id,
            deliverer=called(
                "delivery",
                {"accepted": True, "message_id": "fixture", "production": False},
            ),
            receipt_persister=called(
                "receipt",
                {"persisted": True, "receipt_id": "fixture"},
            ),
            terminal_reporter=called("report", {"emitted": True}),
        )
        assert result["blocker"] == expected_blocker
        assert calls == []
        assert ledger.delivery_count == 0
        assert ledger.receipt_count == 0
        assert ledger.wallet_mutations == 0
        assert ledger.terminal_report_count == 0
