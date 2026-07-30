from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from services import video_local_editing as editing
from services import video_local_validation as validation


def _source_plan(tmp_path: Path, *, duration_ms: int = 4_000) -> dict:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    plan = editing.default_manual_edit_plan(str(source))
    plan["trim"] = {"start_ms": 0, "end_ms": duration_ms}
    return plan


def _probe(*, duration_ms: int = 4_000, audio: bool = True) -> dict:
    return {
        "ok": True,
        "duration": duration_ms / 1000,
        "duration_ms": duration_ms,
        "width": 320,
        "height": 180,
        "fps": 24.0,
        "has_video": True,
        "has_audio": audio,
        "format_name": "mp4",
        "bytes": 4096,
    }


def test_videoedit_unknown_requested_plan_field_fails_closed(tmp_path: Path) -> None:
    plan = _source_plan(tmp_path)
    plan["provider_magic_effect"] = True
    with pytest.raises(editing.LocalVideoEditError, match="unknown_edit_plan_field"):
        editing.normalize_manual_edit_plan(plan, source_duration_ms=4_000, workspace=tmp_path)


def test_videoedit_optional_local_fields_survive_normalization(tmp_path: Path) -> None:
    plan = _source_plan(tmp_path)
    plan.update(
        {
            "audio_normalization": "loudnorm",
            "quality_filters": {"sharpen": True, "denoise": True},
            "local_effects": {
                "fade_in_ms": 300,
                "fade_out_ms": 400,
                "vignette": True,
                "slow_zoom": True,
            },
            "remove_middle": {"start_ms": 1_500, "end_ms": 2_500},
        }
    )
    normalized = editing.normalize_manual_edit_plan(plan, source_duration_ms=4_000, workspace=tmp_path)
    assert normalized["audio_normalization"] == "loudnorm"
    assert normalized["quality_filters"] == {"sharpen": True, "denoise": True}
    assert normalized["local_effects"] == {
        "fade_in_ms": 300,
        "fade_out_ms": 400,
        "vignette": True,
        "slow_zoom": True,
    }
    assert normalized["remove_middle"] == {"start_ms": 1_500, "end_ms": 2_500}


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("audio_normalization", "magic", "audio_normalization_invalid"),
        ("quality_filters", {"sharpen": True, "unknown": True}, "quality_filter_invalid"),
        ("local_effects", {"fade_in_ms": 4_000}, "local_effect_duration_invalid"),
        ("remove_middle", {"start_ms": 0, "end_ms": 1_000}, "remove_middle_invalid"),
        ("remove_middle", {"start_ms": 1_000, "end_ms": 4_000}, "remove_middle_invalid"),
    ],
)
def test_videoedit_optional_local_fields_are_bounded(
    tmp_path: Path,
    field: str,
    value,
    reason: str,
) -> None:
    plan = _source_plan(tmp_path)
    plan[field] = value
    with pytest.raises(editing.LocalVideoEditError, match=reason):
        editing.normalize_manual_edit_plan(plan, source_duration_ms=4_000, workspace=tmp_path)


def test_videoedit_required_filter_matrix_is_exact(tmp_path: Path) -> None:
    plan = _source_plan(tmp_path)
    plan.update(
        {
            "audio_normalization": "loudnorm",
            "quality_filters": {"sharpen": True, "denoise": True},
            "local_effects": {
                "fade_in_ms": 300,
                "fade_out_ms": 400,
                "vignette": True,
                "slow_zoom": True,
            },
        }
    )
    normalized = editing.normalize_manual_edit_plan(plan, source_duration_ms=4_000, workspace=tmp_path)
    assert editing.required_optional_filters(normalized, has_audio=True) == {
        "afade",
        "fade",
        "hqdn3d",
        "loudnorm",
        "unsharp",
        "vignette",
        "zoompan",
    }


def test_videoedit_requested_unavailable_filter_fails_before_ffmpeg(tmp_path: Path) -> None:
    plan = _source_plan(tmp_path)
    plan["quality_filters"] = {"sharpen": True, "denoise": False}
    normalized = editing.normalize_manual_edit_plan(plan, source_duration_ms=4_000, workspace=tmp_path)
    with pytest.raises(editing.LocalVideoEditError, match="ffmpeg_filter_unavailable:unsharp"):
        editing.validate_required_optional_filters(normalized, available_filters=set(), has_audio=True)


def test_videoedit_command_contains_only_selected_optional_filters(tmp_path: Path) -> None:
    plan = _source_plan(tmp_path)
    plan.update(
        {
            "audio_normalization": "loudnorm",
            "quality_filters": {"sharpen": True, "denoise": True},
            "local_effects": {
                "fade_in_ms": 300,
                "fade_out_ms": 400,
                "vignette": True,
                "slow_zoom": True,
            },
        }
    )
    normalized = editing.normalize_manual_edit_plan(plan, source_duration_ms=4_000, workspace=tmp_path)
    command = editing.build_manual_ffmpeg_command(
        normalized,
        output_path=str(tmp_path / "output.mp4"),
        source_probe=_probe(),
        ffmpeg_path="ffmpeg",
    )
    joined = " ".join(command)
    for token in ("unsharp", "hqdn3d", "fade=t=in", "fade=t=out", "vignette", "zoompan", "loudnorm", "afade=t=in", "afade=t=out"):
        assert token in joined


def _real_fixture(path: Path, *, duration_seconds: int = 4) -> tuple[str, str]:
    ffmpeg = validation.find_ffmpeg()
    ffprobe = validation.find_ffprobe(ffmpeg_path=ffmpeg)
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg/ffprobe unavailable")
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            str(duration_seconds),
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
    assert completed.returncode == 0, completed.stderr[-1200:]
    return ffmpeg, ffprobe


def test_videoedit_real_quality_audio_and_effects_return_valid_mp4(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    ffmpeg, ffprobe = _real_fixture(source)
    plan = editing.default_manual_edit_plan(str(source))
    plan["trim"] = {"start_ms": 0, "end_ms": 4_000}
    plan.update(
        {
            "audio_normalization": "loudnorm",
            "quality_filters": {"sharpen": True, "denoise": True},
            "local_effects": {
                "fade_in_ms": 250,
                "fade_out_ms": 250,
                "vignette": True,
                "slow_zoom": False,
            },
        }
    )
    output = tmp_path / "quality-effects.mp4"
    result = editing.execute_manual_edit(
        plan,
        output_path=str(output),
        workspace=tmp_path,
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        timeout=90,
    )
    assert result["ok"] is True
    assert result["provider_called"] is False
    assert result["xu_charged"] == 0
    assert result["validation"]["video_codec"] == "h264"
    assert result["validation"]["has_audio"] is True
    assert abs(int(result["validation"]["duration_ms"]) - 4_000) <= 900


def test_videoedit_real_remove_middle_returns_one_valid_mp4(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    ffmpeg, ffprobe = _real_fixture(source)
    plan = editing.default_manual_edit_plan(str(source))
    plan["trim"] = {"start_ms": 0, "end_ms": 4_000}
    plan["remove_middle"] = {"start_ms": 1_500, "end_ms": 2_500}
    output = tmp_path / "removed-middle.mp4"
    result = editing.execute_manual_edit(
        plan,
        output_path=str(output),
        workspace=tmp_path,
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        timeout=90,
    )
    assert result["ok"] is True
    assert result["validation"]["ok"] is True
    assert abs(int(result["validation"]["duration_ms"]) - 3_000) <= 900
    assert output.is_file() and output.stat().st_size > 0
    assert not list(tmp_path.glob("*.partial.mp4"))


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("aspect", "magic"),
        ("aspect_mode", "blur"),
        ("resolution", "8k"),
        ("rotation", "abc"),
        ("rotation", "45"),
        ("flip", "diagonal"),
        ("speed", "nan"),
        ("speed", "inf"),
        ("volume", "-inf"),
        ("color_preset", "provider_magic"),
        ("logo_opacity", "nan"),
        ("logo_position", "outside"),
    ],
)
def test_videoedit_malformed_callback_choices_fail_closed(kind: str, value: str) -> None:
    with pytest.raises(editing.LocalVideoEditError, match="callback_choice_invalid"):
        editing.normalize_callback_plan_choice(kind, value)


def test_videoedit_callback_choices_return_bounded_typed_values() -> None:
    assert editing.normalize_callback_plan_choice("aspect", "9x16") == ("aspect", "9:16")
    assert editing.normalize_callback_plan_choice("aspect_mode", "fit") == ("aspect_mode", "fit")
    assert editing.normalize_callback_plan_choice("rotation", "90") == ("rotation", 90)
    assert editing.normalize_callback_plan_choice("speed", "1.25") == ("speed", 1.25)
    assert editing.normalize_callback_plan_choice("logo_opacity", "0.75") == ("logo_opacity", 0.75)
