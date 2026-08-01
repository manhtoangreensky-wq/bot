"""Bounded real-media proof for P0.SUBDUB.LONGMEDIA32.

Fixtures are generated locally with FFmpeg and never call providers, Telegram,
wallet code, Railway, or a remote worker.
"""

from __future__ import annotations

import asyncio
import struct
import subprocess
from pathlib import Path

import pytest

import bot
from services import video_local_validation as media_validation


MIB = 1024 * 1024


def _require_tools() -> tuple[str, str]:
    ffmpeg = media_validation.find_ffmpeg()
    ffprobe = media_validation.find_ffprobe(ffmpeg_path=ffmpeg)
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg/ffprobe unavailable for LONGMEDIA32 real-media proof")
    return ffmpeg, ffprobe


def _run(command: list[str], *, timeout: int = 180) -> None:
    completed = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]


def _make_familiar_mp4(path: Path, duration: int) -> tuple[str, str]:
    ffmpeg, ffprobe = _require_tools()
    if path.is_file() and path.stat().st_size > 0:
        return ffmpeg, ffprobe
    _run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x203040:s=96x160:r=2:d={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=48000:duration={duration}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "35",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "24k",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(path),
        ],
        timeout=max(180, duration * 2),
    )
    assert path.is_file() and path.stat().st_size > 0
    return ffmpeg, ffprobe


def _make_unfamiliar_mkv(path: Path) -> tuple[str, str]:
    ffmpeg, ffprobe = _require_tools()
    _run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=96x160:rate=7:duration=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100:duration=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=660:sample_rate=48000:duration=3",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-map",
            "2:a:0",
            "-c:v",
            "ffv1",
            "-c:a",
            "pcm_s16le",
            str(path),
        ]
    )
    assert path.is_file() and path.stat().st_size > 0
    return ffmpeg, ffprobe


def _patch_media_tools(monkeypatch: pytest.MonkeyPatch, ffmpeg: str, ffprobe: str) -> None:
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: ffmpeg)
    monkeypatch.setattr(bot, "ffprobe_path_for_ffmpeg", lambda: ffprobe)


def _full_decode(path: Path, ffmpeg: str) -> None:
    _run(
        [
            ffmpeg,
            "-v",
            "error",
            "-xerror",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-f",
            "null",
            "-",
        ],
        timeout=300,
    )


def _append_free_box(path: Path, target_size: int) -> None:
    current = path.stat().st_size
    box_size = int(target_size) - int(current)
    assert box_size >= 8
    with path.open("r+b") as handle:
        handle.seek(0, 2)
        handle.write(struct.pack(">I4s", box_size, b"free"))
        handle.seek(box_size - 9, 1)
        handle.write(b"\0")
    assert path.stat().st_size == target_size


@pytest.mark.parametrize("duration", [59, 61, 90, 180, 300])
def test_longmedia32_real_duration_matrix_probes_decodes_and_routes(
    duration: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / f"source-{duration}.mp4"
    ffmpeg, ffprobe = _make_familiar_mp4(source, duration)
    _patch_media_tools(monkeypatch, ffmpeg, ffprobe)

    payload = source.read_bytes()
    probe = asyncio.run(bot.subdub_probe_video_bytes(payload))
    assert probe["ok"] is True
    assert probe["has_video"] is True
    assert probe["has_audio"] is True
    assert probe["width"] == 96
    assert probe["height"] == 160
    assert abs(float(probe["duration"]) - duration) <= 0.35

    gate = bot.subdub_duration_gate_payload(
        {
            "size": len(payload),
            "ffprobe_duration": float(probe["duration"]),
            "telegram_download_method": "local_path_override",
        },
        {},
        ffprobe_duration=float(probe["duration"]),
    )
    assert gate["duration_gate_result"] in {"pass", "pass_long"}
    assert gate["chunking_enabled"] is (duration > 60)
    assert gate["chunk_strategy"] == (
        "checkpointed_audio_chunks" if duration > 60 else "whole_file"
    )
    _full_decode(source, ffmpeg)


@pytest.mark.parametrize("duration", [61, 300])
def test_longmedia32_real_subtitle_render_preserves_portrait_timeline(
    duration: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / f"render-source-{duration}.mp4"
    ffmpeg, ffprobe = _make_familiar_mp4(source, duration)
    _patch_media_tools(monkeypatch, ffmpeg, ffprobe)
    cue_start = bot.video_dubbing_srt_timestamp(duration - 2)
    cue_end = bot.video_dubbing_srt_timestamp(duration - 0.25)
    subtitle = (
        "1\n00:00:00,500 --> 00:00:02,000\nTOAN AAS LONGMEDIA32\n\n"
        f"2\n{cue_start} --> {cue_end}\nFINAL CUE\n"
    )

    output, detail = asyncio.run(
        bot.video_dubbing_render_video(
            source.read_bytes(),
            subtitle_bytes=subtitle.encode("utf-8"),
            subtitle_style={"show_subtitles": True},
            target_duration_seconds=duration,
            preserve_source_duration=True,
            require_audio=True,
        )
    )
    assert output, detail
    result_path = tmp_path / f"rendered-{duration}.mp4"
    result_path.write_bytes(output)
    probe = asyncio.run(bot.subdub_probe_video_bytes(output))
    assert probe["ok"] is True
    assert probe["has_audio"] is True
    assert (probe["width"], probe["height"]) == (96, 160)
    assert abs(float(probe["duration"]) - duration) <= 1.0
    assert "shortest_used=no" in detail
    _full_decode(result_path, ffmpeg)


def test_longmedia32_real_unfamiliar_mkv_normalizes_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "unfamiliar.mkv"
    ffmpeg, ffprobe = _make_unfamiliar_mkv(source)
    _patch_media_tools(monkeypatch, ffmpeg, ffprobe)

    normalized = asyncio.run(
        bot.subdub_normalize_video_bytes_if_needed(
            source.read_bytes(),
            content_type="video/x-matroska",
        )
    )
    assert normalized["ok"] is True
    assert normalized["normalized"] is True
    assert normalized["normalization_count"] == 1
    assert normalized["duration_preserved"] is True
    assert normalized["geometry_preserved"] is True
    assert "container_not_mp4" in normalized["normalization_reasons"]
    assert "multiple_audio_streams" in normalized["normalization_reasons"]

    probe = normalized["normalized_probe"]
    assert probe["container"] == "mp4"
    assert probe["video_codec"] == "h264"
    assert probe["pixel_format"] == "yuv420p"
    assert probe["audio_codec"] == "aac"
    assert probe["audio_sample_rate"] == 48000
    assert probe["audio_stream_count"] == 1
    result_path = tmp_path / "normalized.mp4"
    result_path.write_bytes(normalized["source_bytes"])
    _full_decode(result_path, ffmpeg)


@pytest.mark.parametrize("target_mib", [21, 75])
def test_longmedia32_real_large_mp4_remains_probeable_by_capability(
    target_mib: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / f"large-{target_mib}.mp4"
    ffmpeg, ffprobe = _make_familiar_mp4(source, 3)
    _patch_media_tools(monkeypatch, ffmpeg, ffprobe)
    _append_free_box(source, target_mib * MIB)

    payload = source.read_bytes()
    assert len(payload) == target_mib * MIB
    probe = asyncio.run(bot.subdub_probe_video_bytes(payload))
    assert probe["ok"] is True
    assert abs(float(probe["duration"]) - 3.0) <= 0.35
    saved_input = bot.subdub_validate_saved_input_for_pipeline(
        {
            "ok": True,
            "path": str(source),
            "size": len(payload),
            "transport_input_size": len(payload),
            "duration": 3,
            "content_type": "video/mp4",
            "telegram_download_method": "local_path_override",
        },
        {},
    )
    assert saved_input["ok"] is True
    assert bot.subdub_input_limit_mb(
        False,
        intake_method="cloud_bot_api",
        local_api=False,
    ) == 20
    assert bot.subdub_input_limit_mb(
        False,
        intake_method="local_path_override",
        local_api=True,
    ) == 500
    _full_decode(source, ffmpeg)
