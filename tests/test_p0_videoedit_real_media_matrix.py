"""Bounded real-media verification for the local Video Edit runtime.

These tests deliberately invoke the repository's FFmpeg/ffprobe binaries and
inspect produced media rather than asserting command strings alone.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from services import video_local_editing as editing
from services import video_local_validation as validation


def _require_tools() -> tuple[str, str]:
    ffmpeg = validation.find_ffmpeg()
    ffprobe = validation.find_ffprobe(ffmpeg_path=ffmpeg)
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg/ffprobe unavailable")
    return ffmpeg, ffprobe


def _make_clip(path: Path, *, color: str, frequency: int, duration: float = 2.0) -> None:
    ffmpeg, _ = _require_tools()
    command = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s=320x180:r=24,drawbox=x=0:y=0:w=80:h=180:color=green:t=fill",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={frequency}:sample_rate=48000",
        "-t",
        f"{duration:.3f}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
    assert completed.returncode == 0, completed.stderr[-1600:]


def _run_edit(source: Path, output: Path, workspace: Path, **updates) -> dict:
    ffmpeg, ffprobe = _require_tools()
    plan = editing.default_manual_edit_plan(str(source))
    plan.update(updates)
    result = editing.execute_manual_edit(
        plan,
        output_path=str(output),
        workspace=workspace,
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        timeout=90,
    )
    assert result["ok"] is True
    assert result["provider_called"] is False
    assert result["xu_charged"] == 0
    assert output.is_file() and output.stat().st_size > 0
    return result


def _frame_mean_rgb(path: Path, *, at_seconds: float = 0.0) -> tuple[float, float, float]:
    ffmpeg, _ = _require_tools()
    completed = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-ss",
            f"{at_seconds:.3f}",
            "-i",
            str(path),
            "-vf",
            "select=eq(n\\,0),format=rgb24",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        capture_output=True,
        timeout=45,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")[-1200:]
    pixels = completed.stdout
    assert len(pixels) >= 3
    count = len(pixels) // 3
    return tuple(sum(pixels[channel::3]) / count for channel in range(3))


@pytest.fixture()
def source_clip(tmp_path: Path) -> Path:
    source = tmp_path / "source-red.mp4"
    _make_clip(source, color="red", frequency=440)
    return source


def test_videoedit_trim_preserves_audio_with_local_fade_effect(source_clip: Path, tmp_path: Path) -> None:
    result = _run_edit(
        source_clip,
        tmp_path / "trim-fade.mp4",
        tmp_path,
        trim={"start_ms": 250, "end_ms": 1_750},
        local_effects={"fade_in_ms": 200, "fade_out_ms": 200, "vignette": False, "slow_zoom": False},
    )
    assert result["validation"]["ok"] is True
    assert result["validation"]["has_audio"] is True
    assert abs(int(result["validation"]["duration_ms"]) - 1_500) <= 750


def test_videoedit_geometry_rotation_and_flip_produce_real_transformed_mp4(source_clip: Path, tmp_path: Path) -> None:
    transformed = tmp_path / "geometry.mp4"
    result = _run_edit(
        source_clip,
        transformed,
        tmp_path,
        crop_or_fit={"aspect_ratio": "1:1", "mode": "crop"},
        resolution="720p",
        rotation=90,
        flip="horizontal",
    )
    validation_data = result["validation"]
    assert validation_data["ok"] is True
    assert (int(validation_data["width"]), int(validation_data["height"])) == (720, 720)
    baseline = tmp_path / "geometry-baseline.mp4"
    _run_edit(source_clip, baseline, tmp_path, crop_or_fit={"aspect_ratio": "1:1", "mode": "crop"}, resolution="720p")
    assert transformed.read_bytes() != baseline.read_bytes()


def test_videoedit_speed_changes_video_and_audio_duration(source_clip: Path, tmp_path: Path) -> None:
    result = _run_edit(source_clip, tmp_path / "fast.mp4", tmp_path, speed=2.0)
    assert result["validation"]["ok"] is True
    assert result["validation"]["has_audio"] is True
    assert abs(int(result["validation"]["duration_ms"]) - 1_000) <= 750


def test_videoedit_volume_mute_and_loudnorm_enforce_audio_policy(source_clip: Path, tmp_path: Path) -> None:
    lowered = _run_edit(source_clip, tmp_path / "volume-half.mp4", tmp_path, volume=0.5)
    assert lowered["validation"]["has_audio"] is True
    assert abs(int(lowered["validation"]["duration_ms"]) - 2_000) <= 750

    muted = _run_edit(source_clip, tmp_path / "muted.mp4", tmp_path, volume=0.0)
    assert muted["validation"]["has_audio"] is False

    normalized = _run_edit(source_clip, tmp_path / "loudnorm.mp4", tmp_path, audio_normalization="loudnorm")
    assert normalized["validation"]["has_audio"] is True


def test_videoedit_concat_reorders_distinguishable_color_clips(tmp_path: Path) -> None:
    first = tmp_path / "first-red.mp4"
    second = tmp_path / "second-blue.mp4"
    _make_clip(first, color="red", frequency=440, duration=1.5)
    _make_clip(second, color="blue", frequency=880, duration=1.5)
    output = tmp_path / "reordered.mp4"
    result = _run_edit(second, output, tmp_path, concat_inputs=[str(first)])
    assert result["validation"]["ok"] is True
    assert result["validation"]["has_audio"] is True
    assert abs(int(result["validation"]["duration_ms"]) - 3_000) <= 900
    red, _, blue = _frame_mean_rgb(output)
    assert red < blue, "reordered output should begin with the requested blue primary clip"
    red_late, _, blue_late = _frame_mean_rgb(output, at_seconds=2.2)
    assert red_late > blue_late, "reordered output should end with the appended red clip"
