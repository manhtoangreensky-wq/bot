from __future__ import annotations

import subprocess
import threading
from collections import deque
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


def test_public_plan_summary_uses_vietnamese_labels_not_internal_tokens() -> None:
    summary = editing.public_plan_summary(
        {
            "crop_or_fit": {"aspect_ratio": "9:16", "mode": "fit"},
            "resolution": "1080p",
            "color_preset": "bright_clear",
            "audio_normalization": "loudnorm",
            "local_effects": {"slow_zoom": True},
        }
    )
    rendered = " | ".join(summary)
    assert "bright_clear" not in rendered
    assert "loudnorm" not in rendered
    assert "Sáng rõ" in rendered
    assert "Cân bằng âm lượng tự động" in rendered
    assert "Giữ toàn cảnh có viền" in rendered
    assert "Phóng chậm nhẹ" in rendered
    assert "Zoom chậm" not in rendered


def test_public_plan_summary_includes_an_explicit_mute() -> None:
    plan = editing.default_manual_edit_plan("")
    plan["volume"] = 0.0
    assert "Tắt tiếng" in editing.public_plan_summary(plan)


def test_full_source_trim_is_not_advertised_as_an_explicit_cut() -> None:
    plan = editing.default_manual_edit_plan("")
    plan["trim"] = {"start_ms": 0, "end_ms": 10_000}
    assert "Cắt theo khoảng đã chọn" not in editing.public_plan_summary(
        plan,
        source_duration_ms=10_000,
    )
    plan["trim"] = {"start_ms": 1_000, "end_ms": 9_000}
    assert "Cắt theo khoảng đã chọn" in editing.public_plan_summary(
        plan,
        source_duration_ms=10_000,
    )


def test_all_default_manual_plan_is_not_an_executable_edit() -> None:
    plan = editing.default_manual_edit_plan("")
    plan["trim"] = {"start_ms": 0, "end_ms": 10_000}
    assert editing.manual_plan_has_effect(plan, source_duration_ms=10_000) is False

    plan["brightness_percent"] = 110
    assert editing.manual_plan_has_effect(plan, source_duration_ms=10_000) is True


def test_changed_trim_is_an_executable_edit() -> None:
    plan = editing.default_manual_edit_plan("")
    plan["trim"] = {"start_ms": 1_000, "end_ms": 9_000}
    assert editing.manual_plan_has_effect(plan, source_duration_ms=10_000) is True


def test_split_plan_requires_one_duration_independent_canonical_neutral_plan() -> None:
    plan = editing.neutral_split_manual_plan()
    assert plan["trim"] == {"start_ms": 0, "end_ms": 0}
    assert editing.split_plan_has_manual_conflict(
        plan,
        source_duration_ms=10_000,
    ) is False
    assert editing.split_plan_has_manual_conflict(
        plan,
        source_duration_ms=10_137,
    ) is False

    intake_duration_plan = editing.default_manual_edit_plan("")
    intake_duration_plan["trim"] = {"start_ms": 0, "end_ms": 10_000}
    assert editing.split_plan_has_manual_conflict(
        intake_duration_plan,
        source_duration_ms=10_000,
    ) is True

    changed = dict(plan)
    changed["brightness_percent"] = 120
    assert editing.split_plan_has_manual_conflict(
        changed,
        source_duration_ms=10_000,
    ) is True
    assert editing.split_plan_has_manual_conflict(
        plan,
        source_duration_ms=10_000,
        concat_sources=[{"file_id": "concat"}],
    ) is True
    assert editing.split_plan_has_manual_conflict(
        plan,
        source_duration_ms=10_000,
        concat_sources=[None],
    ) is True
    assert editing.split_plan_has_manual_conflict(
        plan,
        source_duration_ms=10_000,
        logo_source={"file_id": "logo"},
    ) is True
    assert editing.split_plan_has_manual_conflict(
        plan,
        source_duration_ms=10_000,
        subtitle_source={"file_id": "srt"},
    ) is True

    unknown = dict(plan)
    unknown["provider_magic_effect"] = True
    assert editing.split_plan_has_manual_conflict(
        unknown,
        source_duration_ms=10_000,
    ) is True

    nested_unknown = dict(plan)
    nested_unknown["trim"] = {
        **dict(plan["trim"]),
        "provider_hint": True,
    }
    assert editing.split_plan_has_manual_conflict(
        nested_unknown,
        source_duration_ms=10_000,
    ) is True
    assert editing.manual_plan_requires_split_reset(
        nested_unknown,
        source_duration_ms=10_000,
    ) is True


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


def test_videoedit_fades_are_validated_against_post_speed_duration(tmp_path: Path) -> None:
    plan = _source_plan(tmp_path)
    plan["speed"] = 2.0
    plan["local_effects"] = {
        "fade_in_ms": 1_500,
        "fade_out_ms": 600,
        "vignette": False,
        "slow_zoom": False,
    }
    with pytest.raises(editing.LocalVideoEditError, match="local_effect_duration_invalid"):
        editing.normalize_manual_edit_plan(plan, source_duration_ms=4_000, workspace=tmp_path)


def test_videoedit_text_wholly_after_post_speed_output_fails_closed(tmp_path: Path) -> None:
    plan = _source_plan(tmp_path)
    plan["speed"] = 2.0
    plan["text_overlay"] = {
        "content": "Chữ phải xuất hiện",
        "position": "bottom",
        "start_ms": 2_500,
        "end_ms": 3_000,
        "font_size": 42,
        "outline": 2,
    }
    with pytest.raises(editing.LocalVideoEditError, match="text_overlay_outside_output"):
        editing.normalize_manual_edit_plan(plan, source_duration_ms=4_000, workspace=tmp_path)


def test_videoedit_srt_with_every_cue_after_output_fails_closed(tmp_path: Path) -> None:
    subtitle = tmp_path / "late.srt"
    subtitle.write_text(
        "1\n00:00:03,000 --> 00:00:03,800\nPhụ đề quá muộn\n",
        encoding="utf-8",
    )
    plan = _source_plan(tmp_path)
    plan["speed"] = 2.0
    plan["subtitle_file"] = str(subtitle)
    with pytest.raises(editing.LocalVideoEditError, match="subtitle_outside_output"):
        editing.normalize_manual_edit_plan(plan, source_duration_ms=4_000, workspace=tmp_path)


def test_videoedit_srt_cue_uses_a_non_empty_output_intersection_contract(
    tmp_path: Path,
) -> None:
    subtitle = tmp_path / "partial-overlap.srt"
    subtitle.write_text(
        (
            "1\n00:00:01,800 --> 00:00:02,400\nPhụ đề giao biên\n\n"
            "2\n00:00:03,000 --> 00:00:03,800\nPhụ đề ngoài đầu ra\n"
        ),
        encoding="utf-8",
    )
    plan = _source_plan(tmp_path)
    plan["speed"] = 2.0
    plan["subtitle_file"] = str(subtitle)

    output_start_ms = 0
    output_end_ms = 2_000
    validation_result = validation.validate_srt_file(subtitle, workspace=tmp_path)
    assert validation_result["ok"] is True
    intersections = [
        {
            "start_ms": max(output_start_ms, cue["start_ms"]),
            "end_ms": min(output_end_ms, cue["end_ms"]),
        }
        for cue in validation_result["cue_windows"]
        if max(output_start_ms, cue["start_ms"])
        < min(output_end_ms, cue["end_ms"])
    ]
    assert intersections == [{"start_ms": 1_800, "end_ms": 2_000}]

    normalized = editing.normalize_manual_edit_plan(
        plan,
        source_duration_ms=4_000,
        workspace=tmp_path,
    )
    assert normalized["subtitle_file"] == str(subtitle)


def test_videoedit_srt_validation_returns_exact_positive_cue_windows(
    tmp_path: Path,
) -> None:
    subtitle = tmp_path / "windows.srt"
    subtitle.write_text(
        (
            "1\n00:00:00,200 --> 00:00:00,800\nMở đầu\n\n"
            "2\n00:00:01,250 --> 00:00:02,500\nKết thúc\n"
        ),
        encoding="utf-8",
    )
    result = validation.validate_srt_file(subtitle, workspace=tmp_path)
    assert result["ok"] is True
    assert result["cue_windows"] == [
        {"start_ms": 200, "end_ms": 800},
        {"start_ms": 1_250, "end_ms": 2_500},
    ]


@pytest.mark.parametrize(
    "timing",
    [
        "00:00:01,000 --> 00:00:01,000",
        "00:00:02,000 --> 00:00:01,000",
    ],
)
def test_videoedit_srt_validation_rejects_non_positive_cue_windows(
    tmp_path: Path,
    timing: str,
) -> None:
    subtitle = tmp_path / "invalid-window.srt"
    subtitle.write_text(f"1\n{timing}\nKhông hợp lệ\n", encoding="utf-8")
    result = validation.validate_srt_file(subtitle, workspace=tmp_path)
    assert result == {"ok": False, "reason": "subtitle_timing_invalid"}


def test_videoedit_concat_timing_is_validated_on_the_final_post_speed_timeline(
    tmp_path: Path,
) -> None:
    subtitle = tmp_path / "concat-window.srt"
    subtitle.write_text(
        "1\n00:00:02,500 --> 00:00:03,200\nNằm trong phần ghép\n",
        encoding="utf-8",
    )
    plan = _source_plan(tmp_path)
    plan["concat_inputs"] = [str(tmp_path / "append.mp4")]
    plan["speed"] = 2.0
    plan["local_effects"] = {
        "fade_in_ms": 2_500,
        "fade_out_ms": 500,
        "vignette": False,
        "slow_zoom": False,
    }
    plan["text_overlay"] = {
        "content": "Chữ ở phần ghép",
        "position": "bottom",
        "start_ms": 2_500,
        "end_ms": 3_200,
        "font_size": 42,
        "outline": 2,
    }
    plan["subtitle_file"] = str(subtitle)

    deferred = editing.normalize_manual_edit_plan(
        plan,
        source_duration_ms=4_000,
        workspace=tmp_path,
    )
    final_plan = dict(deferred)
    final_plan["concat_inputs"] = []
    final_plan["trim"] = {"start_ms": 0, "end_ms": 8_000}
    normalized = editing.normalize_manual_edit_plan(
        final_plan,
        source_duration_ms=8_000,
        workspace=tmp_path,
    )
    assert normalized["local_effects"]["fade_in_ms"] == 2_500
    assert normalized["text_overlay"]["start_ms"] == 2_500
    assert normalized["subtitle_file"] == str(subtitle)


def test_videoedit_execute_revalidates_timing_after_concat_establishes_final_timeline(
    tmp_path: Path,
) -> None:
    source = tmp_path / "concat-primary.mp4"
    appended = tmp_path / "concat-appended.mp4"
    ffmpeg, ffprobe = _real_fixture(source, duration_seconds=2)
    _real_fixture(appended, duration_seconds=2)
    plan = editing.default_manual_edit_plan(str(source))
    plan["trim"] = {"start_ms": 0, "end_ms": 2_000}
    plan["concat_inputs"] = [str(appended)]
    plan["speed"] = 2.0
    plan["text_overlay"] = {
        "content": "Nằm ngoài timeline cuối",
        "position": "bottom",
        "start_ms": 2_200,
        "end_ms": 2_600,
        "font_size": 42,
        "outline": 2,
    }

    with pytest.raises(editing.LocalVideoEditError, match="text_overlay_outside_output"):
        editing.execute_manual_edit(
            plan,
            output_path=str(tmp_path / "concat-invalid-timing.mp4"),
            workspace=tmp_path,
            ffmpeg_path=ffmpeg,
            ffprobe_path=ffprobe,
            timeout=90,
        )


@pytest.mark.parametrize(
    ("rotation", "expected_size"),
    [(90, "s=180x320"), (270, "s=180x320")],
)
def test_videoedit_slow_zoom_keeps_post_rotation_dimensions(
    tmp_path: Path,
    rotation: int,
    expected_size: str,
) -> None:
    plan = _source_plan(tmp_path)
    plan["rotation"] = rotation
    plan["local_effects"] = {
        "fade_in_ms": 0,
        "fade_out_ms": 0,
        "vignette": False,
        "slow_zoom": True,
    }
    normalized = editing.normalize_manual_edit_plan(
        plan,
        source_duration_ms=4_000,
        workspace=tmp_path,
    )
    command = editing.build_manual_ffmpeg_command(
        normalized,
        output_path=str(tmp_path / f"rotated-{rotation}.mp4"),
        source_probe=_probe(),
        ffmpeg_path="ffmpeg",
    )
    assert expected_size in " ".join(command)


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


@pytest.mark.parametrize(
    ("patch", "reason"),
    [
        ({"rotation": "bad"}, "rotation_invalid"),
        ({"rotation": 90.5}, "rotation_invalid"),
        ({"speed": "nan"}, "speed_invalid"),
        ({"volume": "inf"}, "volume_invalid"),
        ({"brightness_percent": "bad"}, "brightness_invalid"),
        ({"trim": {"start_ms": 0, "end_ms": 3_000, "provider_hint": True}}, "trim_range_invalid"),
        ({"crop_or_fit": {"aspect_ratio": "9:16", "mode": "fit", "tracking": True}}, "crop_mode_invalid"),
    ],
)
def test_videoedit_malformed_requested_scalars_and_nested_fields_never_fall_back_to_defaults(
    tmp_path: Path,
    patch: dict,
    reason: str,
) -> None:
    plan = _source_plan(tmp_path)
    plan.update(patch)
    with pytest.raises(editing.LocalVideoEditError, match=reason):
        editing.normalize_manual_edit_plan(plan, source_duration_ms=4_000, workspace=tmp_path)


@pytest.mark.parametrize(
    ("patch", "reason"),
    [
        (
            {"remove_middle": {"start_ms": True, "end_ms": 2_500}},
            "remove_middle_invalid",
        ),
        (
            {"remove_middle": {"start_ms": 1_500, "end_ms": True}},
            "remove_middle_invalid",
        ),
        (
            {
                "text_overlay": {
                    "content": "Xin chào",
                    "position": "bottom",
                    "start_ms": True,
                    "end_ms": 2_000,
                }
            },
            "text_overlay_invalid",
        ),
        (
            {
                "text_overlay": {
                    "content": "Xin chào",
                    "position": "bottom",
                    "start_ms": 0,
                    "end_ms": True,
                }
            },
            "text_overlay_invalid",
        ),
        (
            {
                "text_overlay": {
                    "content": "Xin chào",
                    "position": "bottom",
                    "start_ms": 0,
                    "end_ms": 2_000,
                    "font_size": True,
                }
            },
            "text_overlay_invalid",
        ),
        (
            {
                "text_overlay": {
                    "content": "Xin chào",
                    "position": "bottom",
                    "start_ms": 0,
                    "end_ms": 2_000,
                    "outline": True,
                }
            },
            "text_overlay_invalid",
        ),
    ],
)
def test_videoedit_boolean_numeric_plan_fields_fail_closed(
    tmp_path: Path,
    patch: dict,
    reason: str,
) -> None:
    plan = _source_plan(tmp_path)
    plan.update(patch)

    with pytest.raises(editing.LocalVideoEditError, match=reason):
        editing.normalize_manual_edit_plan(
            plan,
            source_duration_ms=4_000,
            workspace=tmp_path,
        )


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
        "format",
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
        editing.validate_required_optional_filters(normalized, available_filters={"format"}, has_audio=True)


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


def test_videoedit_final_timeline_duration_includes_concat_remove_and_speed() -> None:
    plan = editing.default_manual_edit_plan("")
    plan.update(
        {
            "trim": {"start_ms": 1_000, "end_ms": 9_000},
            "remove_middle": {"start_ms": 3_000, "end_ms": 5_000},
            "speed": 0.5,
        }
    )

    assert editing.expected_final_timeline_duration_ms(
        plan,
        concat_sources=[
            {"metadata": {"duration_ms": 3_000}},
            {"source_metadata": {"duration_ms": 750}},
            {"duration": 0.25},
        ],
    ) == 20_000


@pytest.mark.parametrize(
    "concat_source",
    [
        pytest.param({"duration_seconds": 2}, id="top-level"),
        pytest.param(
            {"metadata": {"duration_seconds": 2}},
            id="metadata",
        ),
        pytest.param(
            {"source_metadata": {"duration_seconds": 2}},
            id="source-metadata",
        ),
    ],
)
def test_videoedit_final_timeline_accepts_concat_duration_seconds(
    concat_source: dict,
) -> None:
    plan = editing.default_manual_edit_plan("")
    plan["speed"] = 0.5

    assert editing.expected_final_timeline_duration_ms(
        plan,
        concat_sources=[concat_source],
        source_duration_ms=10_000,
    ) == 24_000


def test_videoedit_speed_timestamp_runs_after_slow_zoom_before_timed_filters(
    tmp_path: Path,
) -> None:
    plan = _source_plan(tmp_path)
    plan.update(
        {
            "speed": 2.0,
            "text_overlay": {
                "content": "Mốc",
                "position": "bottom",
                "start_ms": 100,
                "end_ms": 900,
                "font_size": 42,
                "outline": 2,
            },
            "local_effects": {
                "fade_in_ms": 200,
                "fade_out_ms": 200,
                "vignette": False,
                "slow_zoom": True,
            },
        }
    )
    normalized = editing.normalize_manual_edit_plan(
        plan,
        source_duration_ms=4_000,
        workspace=tmp_path,
    )
    command = editing.build_manual_ffmpeg_command(
        normalized,
        output_path=str(tmp_path / "output.mp4"),
        source_probe=_probe(),
        ffmpeg_path="ffmpeg",
    )
    video_filter = command[command.index("-vf") + 1]

    assert video_filter.index("zoompan=") < video_filter.index("setpts=PTS/2")
    assert video_filter.index("setpts=PTS/2") < video_filter.index("fade=t=in")
    assert video_filter.index("setpts=PTS/2") < video_filter.index("drawtext=")


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


class _ChunkPipe:
    def __init__(self, chunks: list[bytes], *, rendezvous: threading.Barrier | None = None) -> None:
        self._chunks = list(chunks)
        self._rendezvous = rendezvous
        self.read_sizes: list[int] = []
        self.closed = False

    def read(self, size: int) -> bytes:
        self.read_sizes.append(size)
        if self._rendezvous is not None and len(self.read_sizes) == 1:
            self._rendezvous.wait(timeout=1)
        return self._chunks.pop(0) if self._chunks else b""

    def close(self) -> None:
        self.closed = True


class _FakePopen:
    def __init__(
        self,
        command: list[str],
        *,
        stdout_chunks: list[bytes],
        stderr_chunks: list[bytes],
        returncode: int = 0,
        rendezvous: threading.Barrier | None = None,
    ) -> None:
        self.args = command
        self.stdout = _ChunkPipe(stdout_chunks, rendezvous=rendezvous)
        self.stderr = _ChunkPipe(stderr_chunks, rendezvous=rendezvous)
        self.returncode = returncode
        self.wait_timeouts: list[float] = []
        self.terminated = False
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        assert timeout is not None
        self.wait_timeouts.append(timeout)
        return self.returncode

    def poll(self) -> int:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


def test_videoedit_run_uses_exact_remaining_deadline_without_rounding_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, float] = {}

    monkeypatch.setattr(editing.time, "monotonic", lambda: 100.75)

    def fake_popen(command, **kwargs):
        assert kwargs == {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
        process = _FakePopen(command, stdout_chunks=[], stderr_chunks=[])
        observed["process"] = process
        return process

    monkeypatch.setattr(editing.subprocess, "Popen", fake_popen)

    editing._run(["ffmpeg", "-version"], timeout=20, deadline_monotonic=101.0)

    assert observed["process"].wait_timeouts == [pytest.approx(0.25)]


def test_videoedit_run_rejects_an_expired_deadline_before_spawning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(editing.time, "monotonic", lambda: 50.0)

    def unexpected_popen(*args, **kwargs):
        raise AssertionError("expired work must not spawn FFmpeg")

    monkeypatch.setattr(editing.subprocess, "Popen", unexpected_popen)

    with pytest.raises(editing.LocalVideoEditError) as exc_info:
        editing._run(["ffmpeg", "-version"], timeout=20, deadline_monotonic=50.0)

    assert exc_info.value.reason == "ffmpeg_timeout"


def test_videoedit_run_concurrently_drains_pipes_and_returns_only_bounded_tails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostic_limit = 256 * 1024

    rendezvous = threading.Barrier(2)

    def fake_popen(command, **kwargs):
        assert kwargs == {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
        return _FakePopen(
            command,
            stdout_chunks=[b"ffmpeg-", b"probe\n"],
            stderr_chunks=[b"prefix\n", b"x" * (diagnostic_limit + 37)],
            returncode=1,
            rendezvous=rendezvous,
        )

    monkeypatch.setattr(editing.subprocess, "Popen", fake_popen)

    result = editing._run(["ffmpeg", "-version"], timeout=20)

    assert isinstance(result, subprocess.CompletedProcess)
    assert isinstance(result.stdout, str)
    assert result.stdout == "ffmpeg-probe\n"
    assert isinstance(result.stderr, str)
    assert len(result.stderr.encode("utf-8")) == diagnostic_limit
    assert result.stderr == "x" * diagnostic_limit


def test_videoedit_bounded_capture_does_not_use_run_capture_output_or_communicate() -> None:
    source = Path(editing.__file__).read_text(encoding="utf-8")

    assert "subprocess.run(" not in source
    assert "capture_output=" not in source
    assert ".communicate(" not in source


def test_videoedit_bounded_capture_kills_and_reaps_when_terminate_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TerminateFailurePopen(_FakePopen):
        def __init__(self, command, **kwargs) -> None:
            assert kwargs == {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
            super().__init__(command, stdout_chunks=[], stderr_chunks=[])
            self.wait_calls = 0
            self._running = True

        def wait(self, timeout=None):
            self.wait_calls += 1
            self.wait_timeouts.append(timeout)
            if self.wait_calls == 1:
                raise subprocess.TimeoutExpired(self.args, timeout)
            self._running = False
            self.returncode = -9
            return self.returncode

        def poll(self):
            return None if self._running else self.returncode

        def terminate(self):
            self.terminated = True
            raise OSError("terminate unavailable")

        def kill(self):
            self.killed = True

    created: list[TerminateFailurePopen] = []

    def fake_popen(command, **kwargs):
        process = TerminateFailurePopen(command, **kwargs)
        created.append(process)
        return process

    monkeypatch.setattr(editing.subprocess, "Popen", fake_popen)

    with pytest.raises(subprocess.TimeoutExpired):
        editing._capture_bounded_subprocess(
            ["ffmpeg", "-version"],
            timeout=0.01,
            stdout_limit=128,
            stderr_limit=128,
        )

    process = created[0]
    assert process.terminated is True
    assert process.killed is True
    assert process.wait_calls == 2
    assert process.wait_timeouts[0] == pytest.approx(0.01)
    assert 0.0 <= process.wait_timeouts[1] <= process.wait_timeouts[0]
    assert process.stdout.closed is True
    assert process.stderr.closed is True


def test_videoedit_bounded_capture_fails_closed_when_a_reader_never_reaches_eof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BlockingPipe:
        def __init__(self) -> None:
            self.release = threading.Event()
            self.closed = False

        def read(self, _size: int) -> bytes:
            self.release.wait(timeout=0.2)
            return b""

        def close(self) -> None:
            self.closed = True
            self.release.set()

    class BlockingPopen:
        def __init__(self, command, **kwargs) -> None:
            assert kwargs == {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
            self.args = command
            self.returncode = 0
            self.stdout = BlockingPipe()
            self.stderr = BlockingPipe()

        def wait(self, timeout=None):
            assert timeout is not None
            return self.returncode

        def poll(self):
            return self.returncode

        def terminate(self):
            raise AssertionError("completed child must not be terminated")

        def kill(self):
            raise AssertionError("completed child must not be killed")

    created: list[BlockingPopen] = []

    def fake_popen(command, **kwargs):
        process = BlockingPopen(command, **kwargs)
        created.append(process)
        return process

    monkeypatch.setattr(editing.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(editing, "_FFMPEG_PIPE_JOIN_SECONDS", 0.01, raising=False)

    with pytest.raises(OSError, match="ffmpeg_pipe_read_timeout"):
        editing._capture_bounded_subprocess(
            ["ffmpeg", "-version"],
            timeout=1.0,
            stdout_limit=128,
            stderr_limit=128,
        )

    process = created[0]
    assert process.stdout.release.wait(timeout=0.5) is True
    assert process.stderr.release.wait(timeout=0.5) is True
    assert process.stdout.closed is True
    assert process.stderr.closed is True


def test_videoedit_bounded_capture_closes_child_when_reader_start_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[_FakePopen] = []

    def fake_popen(command, **kwargs):
        assert kwargs == {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
        process = _FakePopen(command, stdout_chunks=[], stderr_chunks=[])
        created.append(process)
        return process

    real_thread = threading.Thread
    thread_count = 0

    class FailingThread:
        def start(self) -> None:
            raise RuntimeError("reader start unavailable")

    def thread_factory(*args, **kwargs):
        nonlocal thread_count
        thread_count += 1
        if thread_count == 2:
            return FailingThread()
        return real_thread(*args, **kwargs)

    monkeypatch.setattr(editing.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(editing.threading, "Thread", thread_factory)

    with pytest.raises(RuntimeError, match="reader start unavailable"):
        editing._capture_bounded_subprocess(
            ["ffmpeg", "-version"],
            timeout=1.0,
            stdout_limit=128,
            stderr_limit=128,
        )

    process = created[0]
    assert process.stdout.closed is True
    assert process.stderr.closed is True


def test_videoedit_bounded_tail_uses_a_fixed_chunk_ring() -> None:
    limit = 1024
    chunks = [bytes([65 + index % 26]) * 64 for index in range(80)]
    tail = editing._BoundedByteTail(limit)

    for chunk in chunks:
        tail.append(chunk)

    assert isinstance(tail._chunks, deque)
    assert sum(len(chunk) for chunk in tail._chunks) == limit
    assert len(tail._chunks) <= limit // 64 + 1
    assert tail.text().encode("utf-8") == b"".join(chunks)[-limit:]
    assert tail.overflowed is True


def test_videoedit_bounded_capture_absolute_deadline_includes_reader_joins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 100.0}
    created: list[_FakePopen] = []
    join_timeouts: list[float] = []

    class DeadlinePopen(_FakePopen):
        def wait(self, timeout=None):
            assert timeout is not None
            self.wait_timeouts.append(timeout)
            clock["now"] = 100.9
            return self.returncode

    class ImmediateThread:
        def __init__(self, *, target, args, daemon) -> None:
            assert daemon is True
            self._target = target
            self._args = args
            self._alive = False

        def start(self) -> None:
            self._alive = True
            self._target(*self._args)
            self._alive = False

        def join(self, timeout=None) -> None:
            assert timeout is not None
            join_timeouts.append(timeout)

        def is_alive(self) -> bool:
            return self._alive

    def fake_popen(command, **kwargs):
        assert kwargs == {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
        process = DeadlinePopen(command, stdout_chunks=[], stderr_chunks=[])
        created.append(process)
        return process

    monkeypatch.setattr(editing.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(editing.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(editing.threading, "Thread", ImmediateThread)

    result, _stdout_overflow, _stderr_overflow = editing._capture_bounded_subprocess(
        ["ffmpeg", "-version"],
        timeout=20.0,
        deadline_monotonic=101.0,
        stdout_limit=128,
        stderr_limit=128,
    )

    assert result.returncode == 0
    assert created[0].wait_timeouts == [pytest.approx(1.0)]
    assert join_timeouts
    assert sum(join_timeouts) <= 0.100001


def test_videoedit_bounded_capture_cancels_blocked_reader_before_pipe_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CancellablePipe:
        def __init__(self) -> None:
            self.release = threading.Event()
            self.closed = False
            self.close_before_cancel = False

        def read(self, _size: int) -> bytes:
            self.release.wait(timeout=0.2)
            return b""

        def close(self) -> None:
            if not self.release.is_set():
                self.close_before_cancel = True
                raise OSError("blocked buffered read")
            self.closed = True

    class CancellablePopen:
        def __init__(self, command, **kwargs) -> None:
            assert kwargs == {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
            self.args = command
            self.returncode = 0
            self.stdout = CancellablePipe()
            self.stderr = CancellablePipe()

        def wait(self, timeout=None):
            assert timeout is not None
            return self.returncode

        def poll(self):
            return self.returncode

        def terminate(self):
            raise AssertionError("completed child must not be terminated")

        def kill(self):
            raise AssertionError("completed child must not be killed")

    created: list[CancellablePopen] = []
    cancelled_threads: list[threading.Thread] = []

    def fake_popen(command, **kwargs):
        process = CancellablePopen(command, **kwargs)
        created.append(process)
        return process

    def cancel_reader(reader) -> bool:
        cancelled_threads.append(reader)
        process = created[0]
        process.stdout.release.set()
        process.stderr.release.set()
        return True

    monkeypatch.setattr(editing.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(editing, "_FFMPEG_PIPE_JOIN_SECONDS", 0.01)
    monkeypatch.setattr(
        editing,
        "_cancel_windows_reader_io",
        cancel_reader,
        raising=False,
    )

    with pytest.raises(OSError, match="ffmpeg_pipe_read_timeout"):
        editing._capture_bounded_subprocess(
            ["ffmpeg", "-version"],
            timeout=1.0,
            stdout_limit=128,
            stderr_limit=128,
        )

    process = created[0]
    assert len(cancelled_threads) == 2
    assert process.stdout.close_before_cancel is False
    assert process.stderr.close_before_cancel is False
    assert process.stdout.closed is True
    assert process.stderr.closed is True


def test_videoedit_filter_discovery_honors_deadline_and_cache_key_stays_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"fake")
    observed: list[float] = []
    editing._FFMPEG_FILTER_CACHE.clear()
    monkeypatch.setattr(editing.time, "monotonic", lambda: 10.6)

    def fake_popen(command, **kwargs):
        assert kwargs == {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
        process = _FakePopen(
            command,
            stdout_chunks=[b" .. scale V->V Scale\n"],
            stderr_chunks=[],
        )
        original_wait = process.wait

        def wait(timeout: float | None = None) -> int:
            assert timeout is not None
            observed.append(timeout)
            return original_wait(timeout)

        process.wait = wait  # type: ignore[method-assign]
        return process

    monkeypatch.setattr(editing.subprocess, "Popen", fake_popen)
    first = editing.available_ffmpeg_filters(
        str(ffmpeg),
        deadline_monotonic=11.0,
    )

    def unexpected_popen(*args, **kwargs):
        raise AssertionError("a deadline must not create a distinct cache entry")

    monkeypatch.setattr(editing.subprocess, "Popen", unexpected_popen)
    second = editing.available_ffmpeg_filters(
        str(ffmpeg),
        deadline_monotonic=-1.0,
    )

    assert first == second == frozenset({"scale"})
    assert observed == [pytest.approx(0.4)]
    assert len(editing._FFMPEG_FILTER_CACHE) == 1


def test_videoedit_filter_discovery_deadline_timeout_has_canonical_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ffmpeg = tmp_path / "ffmpeg-timeout.exe"
    ffmpeg.write_bytes(b"fake")
    editing._FFMPEG_FILTER_CACHE.clear()
    monkeypatch.setattr(editing.time, "monotonic", lambda: 20.0)

    def fake_popen(command, **kwargs):
        process = _FakePopen(command, stdout_chunks=[], stderr_chunks=[])

        def wait(timeout: float | None = None) -> int:
            raise subprocess.TimeoutExpired(command, timeout)

        process.wait = wait  # type: ignore[method-assign]
        return process

    monkeypatch.setattr(editing.subprocess, "Popen", fake_popen)

    with pytest.raises(editing.LocalVideoEditError) as exc_info:
        editing.available_ffmpeg_filters(
            str(ffmpeg),
            refresh=True,
            deadline_monotonic=21.0,
        )

    assert exc_info.value.reason == "ffmpeg_timeout"


def test_videoedit_concat_intermediates_share_deadline_and_admitted_workspace_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deadlines: list[float | None] = []
    budgets: list[int] = []
    monkeypatch.setattr(editing, "probe_video_file", lambda *args, **kwargs: _probe())
    monkeypatch.setattr(
        editing,
        "_run_checked",
        lambda command, *, timeout, deadline_monotonic=None: deadlines.append(deadline_monotonic),
    )
    monkeypatch.setattr(
        editing,
        "enforce_workspace_limit",
        lambda workspace, *, maximum_bytes: budgets.append(maximum_bytes),
    )

    editing._normalize_concat_inputs(
        ["one.mp4", "two.mp4"],
        workspace=tmp_path,
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        timeout=20,
        deadline_monotonic=123.5,
        workspace_budget_bytes=777,
    )

    assert deadlines == [123.5, 123.5, 123.5]
    assert budgets == [777, 777, 777]


def test_videoedit_primary_intermediate_shares_deadline_and_workspace_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    plan = _source_plan(tmp_path)
    plan["trim"] = {"start_ms": 500, "end_ms": 3_500}
    observed: dict[str, float | int | None] = {}

    def fake_run(command, *, timeout, deadline_monotonic=None):
        observed["deadline"] = deadline_monotonic
        Path(command[-1]).write_bytes(b"prepared")

    monkeypatch.setattr(editing, "_run_checked", fake_run)
    monkeypatch.setattr(editing, "validate_mp4_output", lambda *args, **kwargs: _probe(duration_ms=3_000))
    monkeypatch.setattr(editing, "probe_video_file", lambda *args, **kwargs: _probe(duration_ms=3_000))
    monkeypatch.setattr(
        editing,
        "enforce_workspace_limit",
        lambda workspace, *, maximum_bytes: observed.update(budget=maximum_bytes),
    )

    editing._prepare_primary_timeline(
        plan,
        source_probe=_probe(),
        workspace=tmp_path,
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        timeout=20,
        deadline_monotonic=123.5,
        workspace_budget_bytes=888,
    )

    assert observed == {"deadline": 123.5, "budget": 888}


def test_videoedit_manual_executor_propagates_deadline_and_custom_workspace_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _source_plan(tmp_path)
    observed: dict[str, float | int | None] = {}
    monkeypatch.setattr(editing, "find_ffmpeg", lambda value="": "ffmpeg")
    monkeypatch.setattr(editing, "find_ffprobe", lambda value="", **kwargs: "ffprobe")
    monkeypatch.setattr(editing, "probe_video_file", lambda *args, **kwargs: _probe())
    monkeypatch.setattr(editing, "validate_mp4_output", lambda *args, **kwargs: _probe())
    monkeypatch.setattr(
        editing,
        "available_ffmpeg_filters",
        lambda ffmpeg, *, refresh=False, deadline_monotonic=None: (
            observed.update(filter_deadline=deadline_monotonic)
            or frozenset({"format", "scale", "setsar"})
        ),
    )

    def fake_run(command, *, timeout, deadline_monotonic=None):
        observed["deadline"] = deadline_monotonic
        Path(command[-1]).write_bytes(b"output")

    monkeypatch.setattr(editing, "_run_checked", fake_run)
    monkeypatch.setattr(
        editing,
        "enforce_workspace_limit",
        lambda workspace, *, maximum_bytes: observed.update(budget=maximum_bytes),
    )

    result = editing.execute_manual_edit(
        plan,
        output_path=str(tmp_path / "output.mp4"),
        workspace=tmp_path,
        deadline_monotonic=200.0,
        workspace_budget_bytes=999,
    )

    assert result["ok"] is True
    assert observed == {
        "filter_deadline": 200.0,
        "deadline": 200.0,
        "budget": 999,
    }


def test_videoedit_split_executor_propagates_deadline_and_preserves_legacy_workspace_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    observed: dict[str, list] = {"filter_deadlines": [], "run_deadlines": [], "budgets": []}
    monkeypatch.setattr(editing, "find_ffmpeg", lambda value="": "ffmpeg")
    monkeypatch.setattr(editing, "find_ffprobe", lambda value="", **kwargs: "ffprobe")
    monkeypatch.setattr(editing, "probe_video_file", lambda *args, **kwargs: _probe())
    monkeypatch.setattr(editing, "validate_mp4_output", lambda *args, **kwargs: _probe(duration_ms=2_000))
    monkeypatch.setattr(
        editing,
        "available_ffmpeg_filters",
        lambda ffmpeg, *, refresh=False, deadline_monotonic=None: (
            observed["filter_deadlines"].append(deadline_monotonic)
            or frozenset({"format", "scale", "setsar"})
        ),
    )
    monkeypatch.setattr(
        editing,
        "_run_checked",
        lambda command, *, timeout, deadline_monotonic=None: observed["run_deadlines"].append(deadline_monotonic),
    )
    monkeypatch.setattr(
        editing,
        "enforce_workspace_limit",
        lambda workspace, **kwargs: observed["budgets"].append(kwargs),
    )

    result = editing.execute_split_plan(
        str(source),
        [editing.SplitRange(index=1, start_ms=0, end_ms=2_000)],
        workspace=tmp_path,
        coverage_required=False,
        deadline_monotonic=300.0,
    )

    assert result["ok"] is True
    assert observed == {
        "filter_deadlines": [300.0],
        "run_deadlines": [300.0],
        "budgets": [{}],
    }
