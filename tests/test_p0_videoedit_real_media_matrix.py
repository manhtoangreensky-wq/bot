"""Bounded real-media verification for the local Video Edit runtime.

These tests deliberately invoke the repository's FFmpeg/ffprobe binaries and
inspect produced media rather than asserting command strings alone.
"""

from __future__ import annotations

import subprocess
from array import array
from pathlib import Path

import pytest

from services import video_local_editing as editing
from services import video_local_validation as validation
from services import video_smart_splitter as splitter


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


def _sine_frequency(path: Path, *, at_seconds: float) -> float:
    ffmpeg, _ = _require_tools()
    sample_rate = 8_000
    completed = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-ss",
            f"{at_seconds:.3f}",
            "-i",
            str(path),
            "-t",
            "0.400",
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-f",
            "s16le",
            "pipe:1",
        ],
        capture_output=True,
        timeout=45,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")[-1200:]
    samples = array("h")
    samples.frombytes(completed.stdout)
    assert len(samples) > sample_rate // 5
    crossings = sum(1 for left, right in zip(samples, samples[1:]) if left <= 0 < right)
    return crossings * sample_rate / len(samples)


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


def test_videoedit_four_by_five_fit_produces_real_720p_portrait_mp4(source_clip: Path, tmp_path: Path) -> None:
    result = _run_edit(
        source_clip,
        tmp_path / "fit-4x5.mp4",
        tmp_path,
        crop_or_fit={"aspect_ratio": "4:5", "mode": "fit"},
        resolution="720p",
    )
    validation_data = result["validation"]
    assert validation_data["ok"] is True
    assert validation_data["has_audio"] is True
    assert (int(validation_data["width"]), int(validation_data["height"])) == (720, 900)


@pytest.mark.parametrize(
    ("speed", "expected_duration_ms"),
    [(0.5, 4_000), (0.75, 2_667), (1.25, 1_600), (1.5, 1_333), (2.0, 1_000)],
)
def test_videoedit_every_public_speed_keeps_audio_in_sync(
    source_clip: Path,
    tmp_path: Path,
    speed: float,
    expected_duration_ms: int,
) -> None:
    result = _run_edit(source_clip, tmp_path / f"speed-{speed:g}.mp4", tmp_path, speed=speed)
    assert result["validation"]["ok"] is True
    assert result["validation"]["has_audio"] is True
    assert abs(int(result["validation"]["duration_ms"]) - expected_duration_ms) <= 750


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
    assert 780 <= _sine_frequency(output, at_seconds=0.4) <= 980
    assert 340 <= _sine_frequency(output, at_seconds=2.0) <= 540


@pytest.mark.parametrize(
    ("aspect", "resolution", "expected_size"),
    [
        ("keep", "keep", (320, 180)),
        ("16:9", "1080p", (1920, 1080)),
        ("9:16", "720p", (720, 1280)),
        ("1:1", "1080p", (1080, 1080)),
        ("4:5", "keep", (144, 180)),
    ],
)
def test_videoedit_representative_aspect_resolution_matrix_produces_exact_geometry(
    source_clip: Path,
    tmp_path: Path,
    aspect: str,
    resolution: str,
    expected_size: tuple[int, int],
) -> None:
    result = _run_edit(
        source_clip,
        tmp_path / f"geometry-{aspect.replace(':', 'x')}-{resolution}.mp4",
        tmp_path,
        crop_or_fit={"aspect_ratio": aspect, "mode": "fit"},
        resolution=resolution,
    )
    assert (int(result["validation"]["width"]), int(result["validation"]["height"])) == expected_size


@pytest.mark.parametrize(
    ("rotation", "flip"),
    [(180, "none"), (270, "none"), (0, "vertical")],
)
def test_videoedit_remaining_rotation_and_flip_controls_render_real_mp4(
    source_clip: Path,
    tmp_path: Path,
    rotation: int,
    flip: str,
) -> None:
    output = tmp_path / f"orientation-{rotation}-{flip}.mp4"
    result = _run_edit(source_clip, output, tmp_path, rotation=rotation, flip=flip)
    assert result["validation"]["ok"] is True
    if rotation == 270:
        assert (int(result["validation"]["width"]), int(result["validation"]["height"])) == (180, 320)


@pytest.mark.parametrize(
    "color_preset",
    ["bright_clear", "light_cinematic", "warm", "cool", "high_contrast", "black_white", "soft_clean"],
)
def test_videoedit_every_public_color_preset_renders_a_valid_local_mp4(
    source_clip: Path,
    tmp_path: Path,
    color_preset: str,
) -> None:
    result = _run_edit(
        source_clip,
        tmp_path / f"color-{color_preset}.mp4",
        tmp_path,
        color_preset=color_preset,
    )
    assert result["validation"]["ok"] is True
    assert result["validation"]["video_codec"] == "h264"


def test_videoedit_brightness_and_slow_zoom_are_observable_real_edits(source_clip: Path, tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.mp4"
    bright = tmp_path / "brightness-140.mp4"
    zoomed = tmp_path / "slow-zoom.mp4"
    _run_edit(source_clip, baseline, tmp_path, trim={"start_ms": 0, "end_ms": 1_500})
    _run_edit(source_clip, bright, tmp_path, trim={"start_ms": 0, "end_ms": 1_500}, brightness_percent=140)
    zoom_result = _run_edit(
        source_clip,
        zoomed,
        tmp_path,
        trim={"start_ms": 0, "end_ms": 1_500},
        local_effects={"fade_in_ms": 0, "fade_out_ms": 0, "vignette": False, "slow_zoom": True},
    )
    assert sum(_frame_mean_rgb(bright, at_seconds=0.7)) > sum(_frame_mean_rgb(baseline, at_seconds=0.7))
    assert zoom_result["validation"]["ok"] is True
    assert zoomed.read_bytes() != baseline.read_bytes()


def test_videoedit_remove_middle_discards_distinguishable_center_scene(tmp_path: Path) -> None:
    red = tmp_path / "remove-red.mp4"
    green = tmp_path / "remove-green.mp4"
    blue = tmp_path / "remove-blue.mp4"
    _make_clip(red, color="red", frequency=440, duration=1.0)
    _make_clip(green, color="green", frequency=660, duration=1.0)
    _make_clip(blue, color="blue", frequency=880, duration=1.0)
    source = tmp_path / "remove-source.mp4"
    source_result = _run_edit(red, source, tmp_path, concat_inputs=[str(green), str(blue)])
    source_duration = int(source_result["validation"]["duration_ms"])

    output = tmp_path / "remove-middle-distinguishable.mp4"
    result = _run_edit(
        source,
        output,
        tmp_path,
        trim={"start_ms": 0, "end_ms": source_duration},
        remove_middle={"start_ms": 1_000, "end_ms": 2_000},
    )
    assert abs(int(result["validation"]["duration_ms"]) - (source_duration - 1_000)) <= 900
    first_red, first_green, first_blue = _frame_mean_rgb(output, at_seconds=0.35)
    last_red, last_green, last_blue = _frame_mean_rgb(output, at_seconds=max(1.1, (source_duration - 1_000) / 1000 - 0.35))
    assert first_red > first_green and first_red > first_blue
    assert last_blue > last_red and last_blue > last_green
    assert 340 <= _sine_frequency(output, at_seconds=0.3) <= 540
    assert 780 <= _sine_frequency(output, at_seconds=max(1.1, (source_duration - 1_000) / 1000 - 0.4)) <= 980


def test_videoedit_fixed_exact_and_custom_split_plans_share_one_real_execution_contract(tmp_path: Path) -> None:
    source = tmp_path / "split-six-seconds.mp4"
    _make_clip(source, color="purple", frequency=500, duration=6.0)
    ffmpeg, ffprobe = _require_tools()
    probe = validation.probe_video_file(source, ffprobe_path=ffprobe)
    duration_ms = int(probe["duration_ms"])
    fixed = splitter.split_fixed_duration(duration_ms, 2_000)
    exact = splitter.split_exact_count(duration_ms, 3)
    custom = splitter.split_custom_ranges(
        duration_ms,
        [(item.start_ms, item.end_ms) for item in exact],
    )
    assert len(fixed) == len(exact) == 3
    assert splitter.validate_exact_coverage(fixed, duration_ms)["ok"] is True
    assert splitter.validate_exact_coverage(exact, duration_ms)["ok"] is True
    assert [item.to_dict() for item in custom] == [item.to_dict() for item in exact]

    result = editing.execute_split_plan(
        str(source),
        custom,
        workspace=tmp_path,
        coverage_required=True,
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        timeout=90,
    )
    assert result["ok"] is True
    assert result["part_count"] == 3
    assert result["coverage"]["ok"] is True
    assert all(item["validation"]["ok"] for item in result["outputs"])
