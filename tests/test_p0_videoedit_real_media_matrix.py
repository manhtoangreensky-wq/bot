"""Bounded real-media verification for the local Video Edit runtime.

These tests deliberately invoke the repository's FFmpeg/ffprobe binaries and
inspect produced media rather than asserting command strings alone.
"""

from __future__ import annotations

import re
import subprocess
from array import array
from math import cos, isfinite, pi, sin, sqrt
from pathlib import Path

import pytest

from services import video_edit_capabilities as capabilities
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


def _make_filtered_clip(
    path: Path,
    *,
    video_filter: str,
    audio_filter: str = "anull",
    duration: float = 2.0,
) -> None:
    ffmpeg, _ = _require_tools()
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            video_filter,
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            f"{duration:.3f}",
            "-af",
            audio_filter,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
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


def _region_mean_rgb(
    path: Path,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    at_seconds: float = 0.0,
) -> tuple[float, float, float]:
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
            (
                "format=rgb24,"
                f"crop=w={width}:h={height}:x={x}:y={y}:exact=1,"
                "select=eq(n\\,0)"
            ),
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
    assert len(pixels) == width * height * 3
    count = width * height
    return tuple(sum(pixels[channel::3]) / count for channel in range(3))


def _audio_rms(path: Path, *, at_seconds: float, duration: float = 0.3) -> float:
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
            "-t",
            f"{duration:.3f}",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
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
    assert samples
    return sqrt(sum(float(sample) ** 2 for sample in samples) / len(samples))


def _tone_amplitude(
    path: Path,
    *,
    frequency: float,
    at_seconds: float,
    duration: float = 0.25,
    sample_rate: int = 16_000,
) -> float:
    """Measure one generated fixture tone from decoded PCM."""

    ffmpeg, _ = _require_tools()
    completed = subprocess.run(
        [
            ffmpeg,
            "-v", "error",
            "-ss", f"{at_seconds:.3f}",
            "-i", str(path),
            "-t", f"{duration:.3f}",
            "-vn", "-ac", "1", "-ar", str(sample_rate),
            "-f", "s16le", "pipe:1",
        ],
        capture_output=True,
        timeout=45,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")[-1200:]
    samples = array("h")
    samples.frombytes(completed.stdout)
    assert samples
    angular = 2.0 * pi * float(frequency) / float(sample_rate)
    real = sum(float(sample) * cos(angular * index) for index, sample in enumerate(samples))
    imag = sum(float(sample) * sin(angular * index) for index, sample in enumerate(samples))
    return 2.0 * sqrt(real * real + imag * imag) / len(samples)


def _gray_region_pixels(
    path: Path,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    at_seconds: float = 0.6,
) -> list[int]:
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
            (
                "format=gray,"
                f"crop=w={width}:h={height}:x={x}:y={y}:exact=1,"
                "select=eq(n\\,0)"
            ),
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
    assert len(completed.stdout) == width * height
    return list(completed.stdout)


def _pixel_variance(values: list[int]) -> float:
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def _horizontal_edge_score(values: list[int], *, width: int) -> float:
    differences = [
        abs(values[index] - values[index - 1])
        for index in range(1, len(values))
        if index % width
    ]
    return sum(differences) / len(differences)


def _sine_frequency(
    path: Path,
    *,
    at_seconds: float,
    duration: float = 0.4,
) -> float:
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
            f"{duration:.3f}",
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
    assert len(samples) > max(80, int(sample_rate * duration * 0.6))
    crossings = sum(1 for left, right in zip(samples, samples[1:]) if left <= 0 < right)
    return crossings * sample_rate / len(samples)


def _loudness_stats(path: Path) -> dict[str, float]:
    ffmpeg, _ = _require_tools()
    completed = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-vn",
            "-af",
            "loudnorm=I=-16:LRA=11:TP=-1.5:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-1600:]

    def metric(name: str) -> float:
        # loudnorm reports the supplied file as input_* before discarding the
        # analysis output, so these are measurements rather than expectations.
        matches = re.findall(rf'"{name}"\s*:\s*"([^"]+)"', completed.stderr)
        assert matches, completed.stderr[-1600:]
        value = float(matches[-1])
        assert isfinite(value)
        return value

    return {
        "integrated_lufs": metric("input_i"),
        "true_peak_dbtp": metric("input_tp"),
    }


@pytest.fixture()
def source_clip(tmp_path: Path) -> Path:
    source = tmp_path / "source-red.mp4"
    _make_clip(source, color="red", frequency=440)
    return source


def test_videoedit_numeric_goal_executes_observable_brightness_and_volume(
    source_clip: Path,
    tmp_path: Path,
) -> None:
    compiled = capabilities.compile_local_intent(
        "Làm sáng video lên 120% và tăng âm lượng lên 110%"
    )
    assert compiled["ok"] is True
    assert compiled["manual_edit_plan"] == {
        "brightness_percent": 120,
        "volume": 1.1,
    }

    baseline = tmp_path / "numeric-goal-baseline.mp4"
    output = tmp_path / "numeric-goal-output.mp4"
    _run_edit(
        source_clip,
        baseline,
        tmp_path,
        trim={"start_ms": 0, "end_ms": 1_500},
    )
    result = _run_edit(
        source_clip,
        output,
        tmp_path,
        trim={"start_ms": 0, "end_ms": 1_500},
        **compiled["manual_edit_plan"],
    )

    assert result["validation"]["full_decode"] is True
    baseline_light = sum(_frame_mean_rgb(baseline, at_seconds=0.7))
    edited_light = sum(_frame_mean_rgb(output, at_seconds=0.7))
    assert edited_light > baseline_light * 1.10
    volume_ratio = _audio_rms(output, at_seconds=0.7) / _audio_rms(
        baseline,
        at_seconds=0.7,
    )
    assert 1.04 <= volume_ratio <= 1.16


def test_videoedit_trim_preserves_audio_with_local_fade_effect(source_clip: Path, tmp_path: Path) -> None:
    baseline = tmp_path / "trim-no-fade.mp4"
    output = tmp_path / "trim-fade.mp4"
    _run_edit(
        source_clip,
        baseline,
        tmp_path,
        trim={"start_ms": 250, "end_ms": 1_750},
    )
    result = _run_edit(
        source_clip,
        output,
        tmp_path,
        trim={"start_ms": 250, "end_ms": 1_750},
        local_effects={"fade_in_ms": 300, "fade_out_ms": 300, "vignette": False, "slow_zoom": False},
    )
    assert result["validation"]["ok"] is True
    assert result["validation"]["has_audio"] is True
    assert abs(int(result["validation"]["duration_ms"]) - 1_500) <= 750
    faded_early = _audio_rms(output, at_seconds=0.03, duration=0.08)
    faded_middle = _audio_rms(output, at_seconds=0.65, duration=0.2)
    faded_late = _audio_rms(output, at_seconds=1.40, duration=0.07)
    assert faded_early < _audio_rms(baseline, at_seconds=0.03, duration=0.08) * 0.65
    assert faded_late < _audio_rms(baseline, at_seconds=1.40, duration=0.07) * 0.65
    assert faded_middle > _audio_rms(baseline, at_seconds=0.65, duration=0.2) * 0.85
    baseline_early = sum(_frame_mean_rgb(baseline, at_seconds=0.03))
    baseline_middle = sum(_frame_mean_rgb(baseline, at_seconds=0.65))
    baseline_late = sum(_frame_mean_rgb(baseline, at_seconds=1.40))
    assert sum(_frame_mean_rgb(output, at_seconds=0.03)) < baseline_early * 0.70
    assert sum(_frame_mean_rgb(output, at_seconds=1.40)) < baseline_late * 0.70
    assert sum(_frame_mean_rgb(output, at_seconds=0.65)) > baseline_middle * 0.90


def test_videoedit_fade_out_uses_the_post_speed_audio_timeline(
    source_clip: Path,
    tmp_path: Path,
) -> None:
    baseline = tmp_path / "speed-fade-baseline.mp4"
    output = tmp_path / "speed-fade-out.mp4"
    _run_edit(source_clip, baseline, tmp_path, speed=2.0)
    result = _run_edit(
        source_clip,
        output,
        tmp_path,
        speed=2.0,
        local_effects={
            "fade_in_ms": 0,
            "fade_out_ms": 300,
            "vignette": False,
            "slow_zoom": False,
        },
    )
    assert abs(int(result["validation"]["duration_ms"]) - 1_000) <= 300
    assert _audio_rms(output, at_seconds=0.52, duration=0.10) > (
        _audio_rms(baseline, at_seconds=0.52, duration=0.10) * 0.88
    )
    assert _audio_rms(output, at_seconds=0.88, duration=0.08) < (
        _audio_rms(baseline, at_seconds=0.88, duration=0.08) * 0.50
    )


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
def test_videoedit_every_public_speed_preserves_audio_and_expected_duration(
    source_clip: Path,
    tmp_path: Path,
    speed: float,
    expected_duration_ms: int,
) -> None:
    result = _run_edit(source_clip, tmp_path / f"speed-{speed:g}.mp4", tmp_path, speed=speed)
    assert result["validation"]["ok"] is True
    assert result["validation"]["has_audio"] is True
    assert abs(int(result["validation"]["duration_ms"]) - expected_duration_ms) <= 750


@pytest.mark.parametrize("speed", [0.5, 2.0])
def test_videoedit_speed_keeps_one_shared_visual_audio_marker_aligned(
    tmp_path: Path,
    speed: float,
) -> None:
    first = tmp_path / f"sync-first-{speed:g}.mp4"
    second = tmp_path / f"sync-second-{speed:g}.mp4"
    joined = tmp_path / f"sync-joined-{speed:g}.mp4"
    output = tmp_path / f"sync-speed-{speed:g}.mp4"
    _make_clip(first, color="red", frequency=440, duration=2.2)
    _make_clip(second, color="blue", frequency=880, duration=2.2)
    _run_edit(first, joined, tmp_path, concat_inputs=[str(second)])
    result = _run_edit(joined, output, tmp_path, speed=speed)
    assert result["validation"]["has_audio"] is True

    # The clip boundary is one shared marker: red/440 Hz before it and
    # blue/880 Hz after it. Both sides must move to the same post-speed time.
    transition_seconds = 2.2 / speed
    before_seconds = transition_seconds - 0.18
    after_seconds = transition_seconds + 0.18
    before_red, _, before_blue = _frame_mean_rgb(output, at_seconds=before_seconds)
    after_red, _, after_blue = _frame_mean_rgb(output, at_seconds=after_seconds)
    assert before_red > before_blue
    assert after_blue > after_red
    assert 340 <= _sine_frequency(
        output,
        at_seconds=before_seconds,
        duration=0.10,
    ) <= 540
    assert 780 <= _sine_frequency(
        output,
        at_seconds=after_seconds,
        duration=0.10,
    ) <= 980


@pytest.mark.parametrize("speed", [0.5, 2.0])
def test_videoedit_speed_and_slow_zoom_keep_visual_audio_timeline_aligned(
    tmp_path: Path,
    speed: float,
) -> None:
    first = tmp_path / f"zoom-sync-first-{speed:g}.mp4"
    second = tmp_path / f"zoom-sync-second-{speed:g}.mp4"
    joined = tmp_path / f"zoom-sync-joined-{speed:g}.mp4"
    output = tmp_path / f"zoom-sync-output-{speed:g}.mp4"
    _make_clip(first, color="red", frequency=440, duration=2.2)
    _make_clip(second, color="blue", frequency=880, duration=2.2)
    _run_edit(first, joined, tmp_path, concat_inputs=[str(second)])
    result = _run_edit(
        joined,
        output,
        tmp_path,
        speed=speed,
        local_effects={
            "fade_in_ms": 0,
            "fade_out_ms": 0,
            "vignette": False,
            "slow_zoom": True,
        },
    )

    expected_seconds = 4.4 / speed
    transition_seconds = 2.2 / speed
    before_seconds = transition_seconds - 0.18
    after_seconds = transition_seconds + 0.18
    before_red, _, before_blue = _frame_mean_rgb(output, at_seconds=before_seconds)
    after_red, _, after_blue = _frame_mean_rgb(output, at_seconds=after_seconds)
    final_red, _, final_blue = _frame_mean_rgb(
        output,
        at_seconds=expected_seconds - 0.25,
    )

    assert result["validation"]["has_audio"] is True
    assert abs(int(result["validation"]["duration_ms"]) - round(expected_seconds * 1000)) <= 750
    assert before_red > before_blue
    assert after_blue > after_red
    assert final_blue > final_red
    assert 340 <= _sine_frequency(output, at_seconds=before_seconds, duration=0.10) <= 540
    assert 780 <= _sine_frequency(output, at_seconds=after_seconds, duration=0.10) <= 980
    assert 780 <= _sine_frequency(
        output,
        at_seconds=expected_seconds - 0.35,
        duration=0.10,
    ) <= 980


def test_videoedit_volume_mute_and_loudnorm_enforce_audio_policy(source_clip: Path, tmp_path: Path) -> None:
    baseline_path = tmp_path / "volume-baseline.mp4"
    lowered_path = tmp_path / "volume-half.mp4"
    amplified_path = tmp_path / "volume-150.mp4"
    _run_edit(source_clip, baseline_path, tmp_path, volume=1.0)
    lowered = _run_edit(source_clip, lowered_path, tmp_path, volume=0.5)
    amplified = _run_edit(source_clip, amplified_path, tmp_path, volume=1.5)
    assert lowered["validation"]["has_audio"] is True
    assert amplified["validation"]["has_audio"] is True
    assert abs(int(lowered["validation"]["duration_ms"]) - 2_000) <= 750
    rms_ratio = _audio_rms(lowered_path, at_seconds=0.6) / _audio_rms(
        baseline_path,
        at_seconds=0.6,
    )
    assert 0.47 <= rms_ratio <= 0.53
    amplified_ratio = _audio_rms(amplified_path, at_seconds=0.6) / _audio_rms(
        baseline_path,
        at_seconds=0.6,
    )
    assert 1.42 <= amplified_ratio <= 1.58

    muted = _run_edit(source_clip, tmp_path / "muted.mp4", tmp_path, volume=0.0)
    assert muted["validation"]["has_audio"] is False

    normalized = _run_edit(source_clip, tmp_path / "loudnorm.mp4", tmp_path, audio_normalization="loudnorm")
    assert normalized["validation"]["has_audio"] is True


def test_videoedit_loudnorm_hits_a_measurable_target_after_manual_volume(
    tmp_path: Path,
) -> None:
    quiet_source = tmp_path / "quiet-source.mp4"
    baseline = tmp_path / "quiet-baseline.mp4"
    normalized = tmp_path / "quiet-loudnorm.mp4"
    combined = tmp_path / "quiet-volume-half-loudnorm.mp4"
    _make_filtered_clip(
        quiet_source,
        video_filter="color=c=gray:s=320x180:r=24",
        audio_filter="volume=0.05",
    )
    _run_edit(quiet_source, baseline, tmp_path)
    _run_edit(quiet_source, normalized, tmp_path, audio_normalization="loudnorm")
    combined_result = _run_edit(
        quiet_source,
        combined,
        tmp_path,
        volume=0.5,
        audio_normalization="loudnorm",
    )
    assert combined_result["validation"]["has_audio"] is True

    baseline_rms = _audio_rms(baseline, at_seconds=0.6, duration=0.5)
    normalized_rms = _audio_rms(normalized, at_seconds=0.6, duration=0.5)
    assert baseline_rms > 0
    assert normalized_rms > baseline_rms * 2.0

    baseline_stats = _loudness_stats(baseline)
    normalized_stats = _loudness_stats(normalized)
    combined_stats = _loudness_stats(combined)
    assert baseline_stats["integrated_lufs"] < -30.0
    assert -18.0 <= normalized_stats["integrated_lufs"] <= -14.0
    assert normalized_stats["integrated_lufs"] > (
        baseline_stats["integrated_lufs"] + 12.0
    )
    assert normalized_stats["true_peak_dbtp"] > (
        baseline_stats["true_peak_dbtp"] + 12.0
    )
    assert normalized_stats["true_peak_dbtp"] <= -1.0

    # Runtime contract: manual volume is pre-normalization gain; loudnorm owns
    # the final target when both controls are selected.
    assert -18.0 <= combined_stats["integrated_lufs"] <= -14.0
    assert abs(
        combined_stats["integrated_lufs"]
        - normalized_stats["integrated_lufs"]
    ) <= 1.0
    assert combined_stats["true_peak_dbtp"] <= -1.0


def test_videoedit_sharpen_and_denoise_have_observable_pixel_evidence(
    tmp_path: Path,
) -> None:
    blurred_source = tmp_path / "blurred-pattern-source.mp4"
    blurred_baseline = tmp_path / "blurred-pattern-baseline.mp4"
    sharpened = tmp_path / "sharpened-pattern.mp4"
    _make_filtered_clip(
        blurred_source,
        video_filter="testsrc2=size=320x180:rate=24,boxblur=2:1",
    )
    _run_edit(blurred_source, blurred_baseline, tmp_path)
    _run_edit(
        blurred_source,
        sharpened,
        tmp_path,
        quality_filters={"sharpen": True, "denoise": False},
    )
    baseline_edges = _horizontal_edge_score(
        _gray_region_pixels(
            blurred_baseline,
            x=20,
            y=20,
            width=280,
            height=140,
        ),
        width=280,
    )
    sharpened_edges = _horizontal_edge_score(
        _gray_region_pixels(
            sharpened,
            x=20,
            y=20,
            width=280,
            height=140,
        ),
        width=280,
    )
    assert sharpened_edges > baseline_edges * 1.03

    noisy_source = tmp_path / "noisy-source.mp4"
    noisy_baseline = tmp_path / "noisy-baseline.mp4"
    denoised = tmp_path / "denoised.mp4"
    _make_filtered_clip(
        noisy_source,
        video_filter="color=c=gray:s=320x180:r=24,noise=alls=30:allf=t+u",
    )
    _run_edit(noisy_source, noisy_baseline, tmp_path)
    _run_edit(
        noisy_source,
        denoised,
        tmp_path,
        quality_filters={"sharpen": False, "denoise": True},
    )
    baseline_variance = _pixel_variance(
        _gray_region_pixels(
            noisy_baseline,
            x=60,
            y=40,
            width=200,
            height=100,
        )
    )
    denoised_variance = _pixel_variance(
        _gray_region_pixels(
            denoised,
            x=60,
            y=40,
            width=200,
            height=100,
        )
    )
    assert denoised_variance < baseline_variance * 0.90


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


def test_videoedit_color_temperature_and_vignette_have_observable_pixel_evidence(
    source_clip: Path,
    tmp_path: Path,
) -> None:
    warm = tmp_path / "observable-warm.mp4"
    cool = tmp_path / "observable-cool.mp4"
    vignette = tmp_path / "observable-vignette.mp4"
    _run_edit(source_clip, warm, tmp_path, color_preset="warm")
    _run_edit(source_clip, cool, tmp_path, color_preset="cool")
    _run_edit(
        source_clip,
        vignette,
        tmp_path,
        local_effects={
            "fade_in_ms": 0,
            "fade_out_ms": 0,
            "vignette": True,
            "slow_zoom": False,
        },
    )
    warm_rgb = _frame_mean_rgb(warm, at_seconds=0.6)
    cool_rgb = _frame_mean_rgb(cool, at_seconds=0.6)
    assert (warm_rgb[0] - warm_rgb[2]) - (cool_rgb[0] - cool_rgb[2]) > 8

    center = _region_mean_rgb(
        vignette,
        x=130,
        y=70,
        width=60,
        height=40,
        at_seconds=0.6,
    )
    edge = _region_mean_rgb(
        vignette,
        x=264,
        y=5,
        width=44,
        height=30,
        at_seconds=0.6,
    )
    assert sum(edge) < sum(center) * 0.8


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


@pytest.mark.parametrize("rotation", [90, 270])
def test_videoedit_rotated_slow_zoom_keeps_portrait_output(
    source_clip: Path,
    tmp_path: Path,
    rotation: int,
) -> None:
    result = _run_edit(
        source_clip,
        tmp_path / f"rotated-slow-zoom-{rotation}.mp4",
        tmp_path,
        rotation=rotation,
        local_effects={
            "fade_in_ms": 0,
            "fade_out_ms": 0,
            "vignette": False,
            "slow_zoom": True,
        },
    )
    assert result["validation"]["ok"] is True
    assert (
        int(result["validation"]["width"]),
        int(result["validation"]["height"]),
    ) == (180, 320)


def test_videoedit_logo_watermark_position_and_opacity_are_visible(
    source_clip: Path,
    tmp_path: Path,
) -> None:
    ffmpeg, _ = _require_tools()
    logo = tmp_path / "blue-logo.png"
    created = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=80x40",
            "-frames:v",
            "1",
            "-update",
            "1",
            str(logo),
        ],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert created.returncode == 0, created.stderr[-1200:]

    baseline = tmp_path / "logo-baseline.mp4"
    half = tmp_path / "logo-half.mp4"
    full = tmp_path / "logo-full.mp4"
    _run_edit(source_clip, baseline, tmp_path, trim={"start_ms": 0, "end_ms": 1_500})
    _run_edit(
        source_clip,
        half,
        tmp_path,
        trim={"start_ms": 0, "end_ms": 1_500},
        logo_overlay={
            "path": str(logo),
            "position": "top_left",
            "scale": 0.12,
            "opacity": 0.5,
        },
    )
    _run_edit(
        source_clip,
        full,
        tmp_path,
        trim={"start_ms": 0, "end_ms": 1_500},
        logo_overlay={
            "path": str(logo),
            "position": "top_left",
            "scale": 0.12,
            "opacity": 1.0,
        },
    )
    base_rgb = _region_mean_rgb(
        baseline,
        x=12,
        y=5,
        width=44,
        height=24,
        at_seconds=0.6,
    )
    half_rgb = _region_mean_rgb(half, x=12, y=5, width=44, height=24, at_seconds=0.6)
    full_rgb = _region_mean_rgb(full, x=12, y=5, width=44, height=24, at_seconds=0.6)
    full_delta = sum(abs(full_value - base_value) for full_value, base_value in zip(full_rgb, base_rgb))
    half_delta = sum(abs(half_value - base_value) for half_value, base_value in zip(half_rgb, base_rgb))
    assert full_delta > 40
    assert 0.35 <= half_delta / full_delta <= 0.70

    baseline_top_right = _region_mean_rgb(
        baseline,
        x=264,
        y=5,
        width=44,
        height=24,
        at_seconds=0.6,
    )
    full_top_right = _region_mean_rgb(
        full,
        x=264,
        y=5,
        width=44,
        height=24,
        at_seconds=0.6,
    )
    assert sum(
        abs(rendered - baseline_value)
        for rendered, baseline_value in zip(full_top_right, baseline_top_right)
    ) < 6


def test_videoedit_real_audio_tracks_are_downloaded_inputs_and_mixed_into_mp4(
    source_clip: Path,
    tmp_path: Path,
) -> None:
    ffmpeg, _ = _require_tools()
    music = tmp_path / "music.mp3"
    voice = tmp_path / "voice.m4a"
    for target, frequency, codec in ((music, 880, "libmp3lame"), (voice, 1320, "aac")):
        created = subprocess.run(
            [
                ffmpeg, "-y", "-f", "lavfi", "-i",
                f"sine=frequency={frequency}:sample_rate=48000",
                "-t", "1.5", "-vn", "-c:a", codec, str(target),
            ],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        assert created.returncode == 0, created.stderr[-1200:]
    output = tmp_path / "mixed-audio.mp4"
    result = _run_edit(
        source_clip,
        output,
        tmp_path,
        audio_tracks=[
            {"path": str(music), "kind": "music", "volume": 0.35, "start_ms": 0},
            {"path": str(voice), "kind": "voice", "volume": 0.8, "start_ms": 700},
        ],
    )
    assert result["validation"]["has_audio"] is True
    assert abs(int(result["validation"]["duration_ms"]) - 2_000) <= 700
    assert _audio_rms(output, at_seconds=0.3, duration=0.15) > 0.001
    assert _audio_rms(output, at_seconds=1.1, duration=0.15) > 0.001
    music_early = _tone_amplitude(output, frequency=880, at_seconds=0.25)
    voice_early = _tone_amplitude(output, frequency=1320, at_seconds=0.25)
    voice_late = _tone_amplitude(output, frequency=1320, at_seconds=0.95)
    assert music_early > 100
    assert voice_late > 100
    assert voice_early < voice_late * 0.25


def test_videoedit_master_mute_silences_source_and_every_added_track(
    source_clip: Path,
    tmp_path: Path,
) -> None:
    ffmpeg, _ = _require_tools()
    music = tmp_path / "mute-music.wav"
    created = subprocess.run(
        [
            ffmpeg, "-y", "-f", "lavfi", "-i",
            "sine=frequency=880:sample_rate=48000",
            "-t", "2", "-vn", "-c:a", "pcm_s16le", str(music),
        ],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert created.returncode == 0, created.stderr[-1200:]
    output = tmp_path / "master-muted.mp4"
    result = _run_edit(
        source_clip,
        output,
        tmp_path,
        volume=0.0,
        audio_tracks=[
            {"path": str(music), "kind": "music", "volume": 1.0, "start_ms": 0},
        ],
    )
    assert result["validation"]["has_audio"] is True
    assert _audio_rms(output, at_seconds=0.5, duration=0.4) < 5


def test_videoedit_text_watermark_and_logo_coexist_on_the_real_final_timeline(
    source_clip: Path,
    tmp_path: Path,
) -> None:
    ffmpeg, _ = _require_tools()
    appended = tmp_path / "branding-appended.mp4"
    _make_clip(appended, color="yellow", frequency=660, duration=1.0)
    logo = tmp_path / "branding-logo.png"
    created = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=magenta:s=80x40",
            "-frames:v",
            "1",
            "-update",
            "1",
            str(logo),
        ],
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert created.returncode == 0, created.stderr[-1200:]

    baseline = tmp_path / "branding-baseline.mp4"
    branded = tmp_path / "branding-all-three.mp4"
    watermark_full = tmp_path / "branding-watermark-full.mp4"
    common = {
        "trim": {"start_ms": 0, "end_ms": 2_000},
        "concat_inputs": [str(appended)],
    }
    _run_edit(source_clip, baseline, tmp_path, **common)
    result = _run_edit(
        source_clip,
        branded,
        tmp_path,
        **common,
        text_overlay={
            "content": "TITLE",
            "position": "top_center",
            "start_ms": 100,
            "end_ms": 900,
            "font_size": 36,
            "outline": 2,
        },
        watermark_overlay={
            "content": "TOAN AAS",
            "position": "bottom_right",
            "start_ms": 0,
            "end_ms": 3_000,
            "font_size": 28,
            "outline": 2,
            "opacity": 0.45,
        },
        logo_overlay={
            "path": str(logo),
            "position": "top_left",
            "scale": 0.12,
            "opacity": 0.75,
        },
    )
    _run_edit(
        source_clip,
        watermark_full,
        tmp_path,
        **common,
        watermark_overlay={
            "content": "TOAN AAS",
            "position": "bottom_right",
            "start_ms": 0,
            "end_ms": 3_000,
            "font_size": 28,
            "outline": 2,
            "opacity": 1.0,
        },
    )

    assert result["validation"]["ok"] is True
    assert result["validation"]["has_audio"] is True
    assert abs(int(result["validation"]["duration_ms"]) - 3_000) <= 900

    title_active = _region_mean_rgb(
        branded, x=75, y=4, width=170, height=50, at_seconds=0.5
    )
    title_baseline = _region_mean_rgb(
        baseline, x=75, y=4, width=170, height=50, at_seconds=0.5
    )
    title_after = _region_mean_rgb(
        branded, x=75, y=4, width=170, height=50, at_seconds=2.5
    )
    title_after_baseline = _region_mean_rgb(
        baseline, x=75, y=4, width=170, height=50, at_seconds=2.5
    )
    assert sum(abs(a - b) for a, b in zip(title_active, title_baseline)) > 10
    assert sum(abs(a - b) for a, b in zip(title_after, title_after_baseline)) < 8

    for at_seconds in (0.5, 2.5):
        watermark = _region_mean_rgb(
            branded, x=175, y=122, width=140, height=52, at_seconds=at_seconds
        )
        watermark_baseline = _region_mean_rgb(
            baseline, x=175, y=122, width=140, height=52, at_seconds=at_seconds
        )
        logo_region = _region_mean_rgb(
            branded, x=10, y=4, width=50, height=28, at_seconds=at_seconds
        )
        logo_baseline = _region_mean_rgb(
            baseline, x=10, y=4, width=50, height=28, at_seconds=at_seconds
        )
        assert sum(abs(a - b) for a, b in zip(watermark, watermark_baseline)) > 5
        assert sum(abs(a - b) for a, b in zip(logo_region, logo_baseline)) > 20

    half_watermark = _region_mean_rgb(
        branded, x=175, y=122, width=140, height=52, at_seconds=2.5
    )
    full_watermark = _region_mean_rgb(
        watermark_full, x=175, y=122, width=140, height=52, at_seconds=2.5
    )
    watermark_baseline = _region_mean_rgb(
        baseline, x=175, y=122, width=140, height=52, at_seconds=2.5
    )
    half_delta = sum(
        abs(value - base)
        for value, base in zip(half_watermark, watermark_baseline)
    )
    full_delta = sum(
        abs(value - base)
        for value, base in zip(full_watermark, watermark_baseline)
    )
    assert full_delta > 10
    assert 0.25 <= half_delta / full_delta <= 0.70


def test_videoedit_default_watermark_covers_remove_concat_and_speed_timeline(
    source_clip: Path,
    tmp_path: Path,
) -> None:
    appended = tmp_path / "watermark-default-appended.mp4"
    _make_clip(appended, color="yellow", frequency=660, duration=1.0)
    baseline = tmp_path / "watermark-default-baseline.mp4"
    branded = tmp_path / "watermark-default-branded.mp4"
    common = {
        "trim": {"start_ms": 0, "end_ms": 2_000},
        "remove_middle": {"start_ms": 500, "end_ms": 1_000},
        "concat_inputs": [str(appended)],
        "speed": 0.5,
    }
    _run_edit(source_clip, baseline, tmp_path, **common)
    result = _run_edit(
        source_clip,
        branded,
        tmp_path,
        **common,
        watermark_overlay={
            "content": "TOAN AAS",
            "position": "bottom_right",
            "start_ms": 0,
            "font_size": 28,
            "outline": 2,
            "opacity": 0.55,
        },
    )

    assert result["validation"]["ok"] is True
    assert result["validation"]["has_audio"] is True
    assert abs(int(result["validation"]["duration_ms"]) - 5_000) <= 1_000
    watermark = _region_mean_rgb(
        branded, x=175, y=122, width=140, height=52, at_seconds=4.2
    )
    watermark_baseline = _region_mean_rgb(
        baseline, x=175, y=122, width=140, height=52, at_seconds=4.2
    )
    assert sum(abs(a - b) for a, b in zip(watermark, watermark_baseline)) > 5


def test_videoedit_text_and_srt_are_visible_only_during_the_requested_window(
    source_clip: Path,
    tmp_path: Path,
) -> None:
    text_output = tmp_path / "timed-text.mp4"
    _run_edit(
        source_clip,
        text_output,
        tmp_path,
        text_overlay={
            "content": "TOAN AAS",
            "position": "bottom",
            "start_ms": 200,
            "end_ms": 800,
            "font_size": 42,
            "outline": 2,
        },
    )
    text_active = _region_mean_rgb(
        text_output,
        x=70,
        y=118,
        width=180,
        height=54,
        at_seconds=0.5,
    )
    text_before = _region_mean_rgb(
        text_output,
        x=70,
        y=118,
        width=180,
        height=54,
        at_seconds=0.05,
    )
    text_inactive = _region_mean_rgb(
        text_output,
        x=70,
        y=118,
        width=180,
        height=54,
        at_seconds=1.3,
    )
    assert sum(abs(active - before) for active, before in zip(text_active, text_before)) > 18
    assert sum(abs(active - inactive) for active, inactive in zip(text_active, text_inactive)) > 18
    assert sum(abs(before - inactive) for before, inactive in zip(text_before, text_inactive)) < 5

    subtitle = tmp_path / "timed.srt"
    subtitle.write_text(
        "1\n00:00:00,200 --> 00:00:00,800\nPHU DE TOAN AAS\n",
        encoding="utf-8",
    )
    subtitle_output = tmp_path / "timed-subtitle.mp4"
    _run_edit(source_clip, subtitle_output, tmp_path, subtitle_file=str(subtitle))
    subtitle_active = _region_mean_rgb(
        subtitle_output,
        x=50,
        y=118,
        width=220,
        height=58,
        at_seconds=0.5,
    )
    subtitle_before = _region_mean_rgb(
        subtitle_output,
        x=50,
        y=118,
        width=220,
        height=58,
        at_seconds=0.05,
    )
    subtitle_inactive = _region_mean_rgb(
        subtitle_output,
        x=50,
        y=118,
        width=220,
        height=58,
        at_seconds=1.3,
    )
    assert sum(
        abs(active - before)
        for active, before in zip(subtitle_active, subtitle_before)
    ) > 12
    assert sum(
        abs(active - inactive)
        for active, inactive in zip(subtitle_active, subtitle_inactive)
    ) > 12
    assert sum(
        abs(before - inactive)
        for before, inactive in zip(subtitle_before, subtitle_inactive)
    ) < 5


@pytest.mark.parametrize(
    ("timeline_updates", "srt_timing", "expected_at", "stale_at"),
    [
        pytest.param(
            {"trim": {"start_ms": 1_000, "end_ms": 3_000}},
            "00:00:00,800 --> 00:00:01,400",
            0.2,
            1.1,
            id="trim_rebases_source_cue",
        ),
        pytest.param(
            {
                "trim": {"start_ms": 0, "end_ms": 4_000},
                "remove_middle": {"start_ms": 1_000, "end_ms": 2_000},
            },
            "00:00:01,800 --> 00:00:02,400",
            1.2,
            2.1,
            id="remove_middle_shifts_later_cue",
        ),
        pytest.param(
            {"trim": {"start_ms": 0, "end_ms": 4_000}, "speed": 2.0},
            "00:00:01,000 --> 00:00:02,000",
            0.75,
            1.5,
            id="speed_rebases_cue_to_post_speed_clock",
        ),
    ],
)
def test_videoedit_srt_is_intersected_and_rebased_after_trim_remove_and_speed(
    tmp_path: Path,
    timeline_updates: dict,
    srt_timing: str,
    expected_at: float,
    stale_at: float,
) -> None:
    """Subtitle timestamps must follow the final edited timeline, not source PTS."""

    source = tmp_path / "srt-timeline-source.mp4"
    _make_clip(source, color="red", frequency=440, duration=4.0)
    subtitle = tmp_path / "srt-timeline.srt"
    subtitle.write_text(
        f"1\n{srt_timing}\nSRT RETIME\n",
        encoding="utf-8",
    )
    baseline = tmp_path / "srt-timeline-baseline.mp4"
    output = tmp_path / "srt-timeline-output.mp4"
    _run_edit(source, baseline, tmp_path, **timeline_updates)
    result = _run_edit(
        source,
        output,
        tmp_path,
        **timeline_updates,
        subtitle_file=str(subtitle),
    )

    assert result["validation"]["ok"] is True

    def subtitle_delta(at_seconds: float) -> float:
        with_subtitle = _region_mean_rgb(
            output,
            x=50,
            y=118,
            width=220,
            height=58,
            at_seconds=at_seconds,
        )
        without_subtitle = _region_mean_rgb(
            baseline,
            x=50,
            y=118,
            width=220,
            height=58,
            at_seconds=at_seconds,
        )
        return sum(
            abs(active - plain)
            for active, plain in zip(with_subtitle, without_subtitle)
        )

    assert subtitle_delta(expected_at) > 12
    assert subtitle_delta(stale_at) < 8


def test_videoedit_srt_in_appended_timeline_is_retained_after_concat(
    tmp_path: Path,
) -> None:
    """A cue in an appended clip must use the combined timeline, not vanish."""

    primary = tmp_path / "srt-concat-primary.mp4"
    appended = tmp_path / "srt-concat-appended.mp4"
    _make_clip(primary, color="red", frequency=440, duration=2.0)
    _make_clip(appended, color="blue", frequency=660, duration=2.0)
    subtitle = tmp_path / "srt-concat.srt"
    subtitle.write_text(
        "1\n00:00:02,200 --> 00:00:02,800\nSRT APPENDED\n",
        encoding="utf-8",
    )

    baseline = tmp_path / "srt-concat-baseline.mp4"
    output = tmp_path / "srt-concat-output.mp4"
    _run_edit(primary, baseline, tmp_path, concat_inputs=[str(appended)])
    result = _run_edit(
        primary,
        output,
        tmp_path,
        concat_inputs=[str(appended)],
        subtitle_file=str(subtitle),
    )

    assert result["validation"]["ok"] is True
    with_subtitle = _region_mean_rgb(
        output,
        x=50,
        y=118,
        width=220,
        height=58,
        at_seconds=2.5,
    )
    without_subtitle = _region_mean_rgb(
        baseline,
        x=50,
        y=118,
        width=220,
        height=58,
        at_seconds=2.5,
    )
    assert sum(
        abs(active - plain)
        for active, plain in zip(with_subtitle, without_subtitle)
    ) > 12


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

    for label, ranges in (("fixed", fixed), ("exact", exact), ("custom", custom)):
        result = editing.execute_split_plan(
            str(source),
            ranges,
            workspace=tmp_path,
            coverage_required=True,
            ffmpeg_path=ffmpeg,
            ffprobe_path=ffprobe,
            timeout=90,
        )
        assert result["ok"] is True, label
        assert result["part_count"] == 3, label
        assert result["coverage"]["ok"] is True, label
        assert all(item["validation"]["ok"] for item in result["outputs"]), label
        for expected, rendered in zip(ranges, result["outputs"]):
            assert abs(
                int(rendered["validation"]["duration_ms"]) - expected.duration_ms
            ) <= 750, label


def test_videoedit_gapped_split_outputs_only_the_selected_distinguishable_boundaries(
    tmp_path: Path,
) -> None:
    red = tmp_path / "gap-red.mp4"
    green = tmp_path / "gap-green.mp4"
    blue = tmp_path / "gap-blue.mp4"
    selected_ms = max(2_200, splitter.MIN_SEGMENT_MS + 200)
    scene_seconds = selected_ms / 1_000 + 0.3
    _make_clip(red, color="red", frequency=440, duration=scene_seconds)
    _make_clip(green, color="green", frequency=660, duration=scene_seconds)
    _make_clip(blue, color="blue", frequency=880, duration=scene_seconds)
    source = tmp_path / "gap-source.mp4"
    source_result = _run_edit(red, source, tmp_path, concat_inputs=[str(green), str(blue)])
    duration_ms = int(source_result["validation"]["duration_ms"])
    ranges = [
        splitter.SplitRange(index=1, start_ms=0, end_ms=selected_ms),
        splitter.SplitRange(
            index=2,
            start_ms=duration_ms - selected_ms,
            end_ms=duration_ms,
        ),
    ]
    assert all(item.duration_ms >= splitter.MIN_SEGMENT_MS for item in ranges)
    ffmpeg, ffprobe = _require_tools()
    result = editing.execute_split_plan(
        str(source),
        ranges,
        workspace=tmp_path,
        coverage_required=False,
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        timeout=90,
    )
    assert result["ok"] is True
    assert result["part_count"] == 2
    for expected, rendered in zip(ranges, result["outputs"]):
        assert abs(
            int(rendered["validation"]["duration_ms"]) - expected.duration_ms
        ) <= 750
    first = Path(result["outputs"][0]["path"])
    second = Path(result["outputs"][1]["path"])
    first_red, first_green, first_blue = _frame_mean_rgb(first, at_seconds=0.3)
    second_red, second_green, second_blue = _frame_mean_rgb(second, at_seconds=0.3)
    end_sample_seconds = selected_ms / 1_000 - 0.3
    first_end_red, first_end_green, first_end_blue = _frame_mean_rgb(
        first,
        at_seconds=end_sample_seconds,
    )
    second_end_red, second_end_green, second_end_blue = _frame_mean_rgb(
        second,
        at_seconds=end_sample_seconds,
    )
    assert first_red > first_green and first_red > first_blue
    assert second_blue > second_red and second_blue > second_green
    assert first_end_red > first_end_green and first_end_red > first_end_blue
    assert second_end_blue > second_end_red and second_end_blue > second_end_green
    assert 340 <= _sine_frequency(first, at_seconds=0.3) <= 540
    assert 780 <= _sine_frequency(second, at_seconds=0.3) <= 980
