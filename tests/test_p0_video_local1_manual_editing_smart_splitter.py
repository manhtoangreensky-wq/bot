from __future__ import annotations

import inspect
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from services import video_local_editing as editing
from services import video_local_validation as validation
from services import video_smart_splitter as splitter


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
WORKER_SOURCE = (ROOT / "local_worker.py").read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    assert start in source and end in source
    return source.split(start, 1)[1].split(end, 1)[0]


def _plan(tmp_path: Path, duration_ms: int = 60_000) -> dict:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    plan = editing.default_manual_edit_plan(str(source))
    plan["trim"] = {"start_ms": 0, "end_ms": duration_ms}
    return plan


def _probe(duration_ms: int = 60_000, *, audio: bool = True, width: int = 1920, height: int = 1080) -> dict:
    return {
        "ok": True,
        "duration": duration_ms / 1000,
        "duration_ms": duration_ms,
        "width": width,
        "height": height,
        "fps": 30.0,
        "has_video": True,
        "has_audio": audio,
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "bytes": 4096,
    }


def _manual_command(tmp_path: Path, plan: dict | None = None, probe: dict | None = None) -> list[str]:
    selected = plan or _plan(tmp_path)
    return editing.build_manual_ffmpeg_command(
        selected,
        output_path=str(tmp_path / "output.mp4"),
        source_probe=probe or _probe(),
        ffmpeg_path="ffmpeg",
    )


def _joined(command: list[str]) -> str:
    return " ".join(command)


def _valid_probe(duration_ms: int = 10_000, *, audio: bool = True) -> dict:
    return {**_probe(duration_ms, audio=audio), "bytes": 4096}


def _real_ffmpeg_fixture(path: Path, *, duration_seconds: int = 5, audio: bool = True) -> tuple[str, str]:
    ffmpeg = validation.find_ffmpeg()
    ffprobe = validation.find_ffprobe(ffmpeg_path=ffmpeg)
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg/ffprobe unavailable for local-only integration check")
    command = [
        ffmpeg,
        "-y",
        "-f", "lavfi",
        "-i", "testsrc2=size=320x180:rate=24",
    ]
    if audio:
        command.extend(["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"])
    command.extend(["-t", str(duration_seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p"])
    if audio:
        command.extend(["-c:a", "aac", "-b:a", "96k", "-shortest"])
    else:
        command.append("-an")
    command.append(str(path))
    completed = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
    assert completed.returncode == 0, completed.stderr[-1200:]
    return ffmpeg, ffprobe


def test_local1_video_edit_menu_present() -> None:
    assert '"label_vi": "🛠️ Chỉnh sửa / Nâng cấp video"' in BOT_SOURCE
    assert '"entry_callback": "videoedit|hub"' in BOT_SOURCE


def test_local1_manual_edit_entry_present() -> None:
    hub = _between(BOT_SOURCE, "def video_edit_hub_keyboard", "def video_edit_info_text")
    assert "✂️ Chỉnh sửa thủ công" in hub
    assert '"videoedit|manual"' in hub


def test_local1_split_entry_present() -> None:
    hub = _between(BOT_SOURCE, "def video_edit_hub_keyboard", "def video_edit_info_text")
    assert "🎞️ Cắt, ghép & sắp xếp" not in hub
    assert '"videoedit|timeline"' not in hub
    assert "videoedit|split" not in hub
    manual = _between(BOT_SOURCE, "def video_local_manual_options_keyboard", "def video_local_split_options_text")
    assert "🧩 Chia thành nhiều đoạn" in manual
    assert '"videoedit|split_from_manual"' in manual


def test_local1_exact_back_from_upload() -> None:
    source = _between(BOT_SOURCE, "def video_local_upload_keyboard", "def _video_local_duration_text")
    assert 'f"videoedit|{tool}"' in source


def test_local1_exact_back_from_options() -> None:
    manual = _between(BOT_SOURCE, "def video_local_manual_options_keyboard", "def video_local_split_options_text")
    split = _between(BOT_SOURCE, "def video_local_split_options_keyboard", "def video_local_choice_keyboard")
    assert '"videoedit|source_summary"' in manual
    assert 'safe_parent = getattr(state_machine, "safe_parent_callback"' in split
    assert "back_target = safe_parent(" in split
    assert '(state or {}).get("parent_callback") or "videoedit|cut"' in split


def test_local1_exact_back_from_confirmation() -> None:
    source = _between(BOT_SOURCE, "def video_local_review_keyboard", "def video_editor_menu_text")
    assert '"videoedit|workspace"' in source
    assert '"videoedit|review"' in source
    assert 'f"videoedit|options|{tool}"' not in source


def test_local1_no_processing_before_confirm() -> None:
    callback = _between(BOT_SOURCE, "async def handle_video_editor_callback", "async def handle_video_upload_callback")
    assert callback.count("submit_local_video_editor_job(") == 0
    assert callback.count("submit_video_edit_local_free_job(update, context, state)") == 1
    confirm_start = callback.index('if action == "confirm_local":')
    confirm_end = callback.find('\n    if action == "', confirm_start + 1)
    confirm_block = callback[confirm_start:confirm_end if confirm_end >= 0 else len(callback)]
    assert "submit_video_edit_local_free_job(update, context, state)" in confirm_block
    for action in ("ai_confirm", "start"):
        action_start = callback.index(f'if action == "{action}":')
        next_action = callback.find('\n    if action == "', action_start + 1)
        action_block = callback[action_start:next_action if next_action >= 0 else len(callback)]
        assert "submit_video_edit_local_free_job(update, context, state)" not in action_block
        assert "video_local_confirmation_text" in action_block
        assert "video_local_confirmation_keyboard" in action_block
    assert "video_tail9_render" not in callback[callback.index('if action == "review"'):]
    assert "subprocess.run" not in callback
    submit = _between(BOT_SOURCE, "async def submit_local_video_editor_job", "async def handle_video_editor_pending_upload")
    assert submit.count("video_editengine1.create_job(") == 1
    assert "create_local_worker_job(" not in submit


def test_local1_no_provider_submit() -> None:
    callback = _between(BOT_SOURCE, "async def handle_video_editor_callback", "async def handle_video_upload_callback")
    worker = _between(WORKER_SOURCE, "def run_video_local_edit", "def _aiedit_progress")
    for forbidden in ("ShopAIKey", "Key4U", "video_provider_router", "provider.submit", "submit_provider"):
        assert forbidden not in callback
        assert forbidden not in worker
    assert '"provider_call": False' in BOT_SOURCE


def test_local1_trim_start_end(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["trim"] = {"start_ms": 5_000, "end_ms": 55_000}
    command = _manual_command(tmp_path, plan)
    assert command[command.index("-ss") + 1] == "5.000"
    assert command[command.index("-t") + 1] == "50.000"


def test_local1_trim_time_range(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["trim"] = {"start_ms": 12_345, "end_ms": 45_678}
    command = _manual_command(tmp_path, plan)
    assert command[command.index("-ss") + 1] == "12.345"
    assert command[command.index("-t") + 1] == "33.333"


def test_local1_concat_multiple_videos() -> None:
    source = inspect.getsource(editing._normalize_concat_inputs)
    assert "concat_normalized_" in source
    assert '"-f", "concat", "-safe", "0"' in source
    assert "target_width" in source and "target_height" in source
    assert "scale=1280:720" not in source
    assert "anullsrc" in source


def test_local1_concat_manifest_is_python311_safe_and_escapes_paths() -> None:
    runtime_bytes = (ROOT / "runtime.txt").read_bytes()
    runtime_text = (
        runtime_bytes.decode("utf-16")
        if runtime_bytes.startswith((b"\xff\xfe", b"\xfe\xff"))
        else runtime_bytes.decode("utf-8-sig")
    )
    assert runtime_text.strip().startswith("python-3.11")
    entry = editing._ffconcat_manifest_entry(Path("C:/work/O'Brien/clip.mp4"))
    assert entry == "file 'C:/work/O'\\''Brien/clip.mp4'\n"

    source = inspect.getsource(editing._normalize_concat_inputs)
    assert "_ffconcat_manifest_entry(item)" in source
    assert "replace(chr(39)" not in source


@pytest.mark.parametrize(
    ("ranges", "duration_ms", "reason"),
    [
        (
            [splitter.SplitRange(index=1, start_ms=0, end_ms=10_000)],
            10_000,
            "split_part_count_invalid",
        ),
        (
            [splitter.SplitRange(index=1, start_ms=0, end_ms=5_000), splitter.SplitRange(index=1, start_ms=5_000, end_ms=10_000)],
            10_000,
            "split_index_invalid",
        ),
        (
            [splitter.SplitRange(index=1, start_ms=0, end_ms=1_000), splitter.SplitRange(index=2, start_ms=1_000, end_ms=10_000)],
            10_000,
            "split_part_too_short",
        ),
        (
            [splitter.SplitRange(index=index, start_ms=(index - 1) * 2_000, end_ms=index * 2_000) for index in range(1, 32)],
            62_000,
            "split_part_count_invalid",
        ),
    ],
)
def test_worker_split_contract_rejects_unsafe_ranges_before_ffmpeg(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    ranges: list[splitter.SplitRange],
    duration_ms: int,
    reason: str,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    monkeypatch.setattr(editing, "find_ffmpeg", lambda _path="": "ffmpeg")
    monkeypatch.setattr(editing, "find_ffprobe", lambda _path="", ffmpeg_path="": "ffprobe")
    monkeypatch.setattr(editing, "probe_video_file", lambda *_args, **_kwargs: _probe(duration_ms))
    monkeypatch.setattr(
        editing,
        "_run_checked",
        lambda *_args, **_kwargs: pytest.fail("FFmpeg must not run for an invalid split contract"),
    )

    with pytest.raises(editing.LocalVideoEditError, match=reason):
        editing.execute_split_plan(
            str(source),
            ranges,
            workspace=tmp_path,
            coverage_required=True,
            ffmpeg_path="ffmpeg",
            ffprobe_path="ffprobe",
        )


def test_local1_aspect_ratio_9_16(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["crop_or_fit"] = {"aspect_ratio": "9:16", "mode": "crop"}
    command = _manual_command(tmp_path, plan)
    assert "scale=608:1080" in _joined(command)
    assert "crop=608:1080" in _joined(command)


def test_local1_aspect_ratio_16_9(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["crop_or_fit"] = {"aspect_ratio": "16:9", "mode": "fit"}
    command = _manual_command(tmp_path, plan)
    assert "scale=1920:1080" in _joined(command)
    assert "pad=1920:1080" in _joined(command)


@pytest.mark.parametrize(
    ("aspect", "resolution", "mode", "width", "height"),
    [
        ("16:9", "keep", "fit", 1920, 1080),
        ("16:9", "720p", "crop", 1280, 720),
        ("16:9", "1080p", "fit", 1920, 1080),
        ("9:16", "keep", "fit", 608, 1080),
        ("9:16", "720p", "crop", 720, 1280),
        ("9:16", "1080p", "fit", 1080, 1920),
        ("1:1", "keep", "fit", 1080, 1080),
        ("1:1", "720p", "crop", 720, 720),
        ("1:1", "1080p", "fit", 1080, 1080),
        ("4:5", "keep", "fit", 864, 1080),
        ("4:5", "720p", "crop", 720, 900),
        ("4:5", "1080p", "fit", 1080, 1350),
    ],
)
def test_local1_all_public_aspects_cover_keep_720p_and_1080p(
    tmp_path: Path,
    aspect: str,
    resolution: str,
    mode: str,
    width: int,
    height: int,
) -> None:
    plan = _plan(tmp_path)
    plan["crop_or_fit"] = {"aspect_ratio": aspect, "mode": mode}
    plan["resolution"] = resolution
    command = _joined(_manual_command(tmp_path, plan))
    geometry_filter = "crop" if mode == "crop" else "pad"
    assert f"scale={width}:{height}" in command
    assert f"{geometry_filter}={width}:{height}" in command


def test_local1_keep_resolution_never_upscales_a_small_source_for_new_aspect(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["crop_or_fit"] = {"aspect_ratio": "9:16", "mode": "fit"}
    plan["resolution"] = "keep"
    command = _joined(_manual_command(tmp_path, plan, probe=_probe(width=640, height=360)))

    assert "scale=202:360" in command
    assert "pad=202:360" in command
    assert "1080:1920" not in command


def test_local1_resize_720p(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["resolution"] = "720p"
    assert "scale=1280:720" in _joined(_manual_command(tmp_path, plan))


def test_local1_resize_1080p(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["resolution"] = "1080p"
    assert "scale=1920:1080" in _joined(_manual_command(tmp_path, plan))


def test_local1_rotate(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["rotation"] = 90
    assert "transpose=1" in _joined(_manual_command(tmp_path, plan))


@pytest.mark.parametrize(
    ("rotation", "expected_filters"),
    [(90, ("transpose=1",)), (180, ("hflip", "vflip")), (270, ("transpose=2",))],
)
def test_local1_every_public_rotation_compiles(
    tmp_path: Path,
    rotation: int,
    expected_filters: tuple[str, ...],
) -> None:
    plan = _plan(tmp_path)
    plan["rotation"] = rotation
    command = _joined(_manual_command(tmp_path, plan))
    assert all(item in command for item in expected_filters)


def test_local1_flip(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["flip"] = "horizontal"
    assert "hflip" in _joined(_manual_command(tmp_path, plan))


@pytest.mark.parametrize(("flip", "expected_filter"), [("horizontal", "hflip"), ("vertical", "vflip")])
def test_local1_every_public_flip_compiles(tmp_path: Path, flip: str, expected_filter: str) -> None:
    plan = _plan(tmp_path)
    plan["flip"] = flip
    assert expected_filter in _joined(_manual_command(tmp_path, plan))


def test_local1_speed_video_and_audio_sync(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["speed"] = 1.5
    command = _manual_command(tmp_path, plan)
    assert "setpts=PTS/1.5" in _joined(command)
    assert command[command.index("-af") + 1] == "atempo=1.5"
    assert command[command.index("-t") + 1] == "40.000"


def test_local1_mute(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["volume"] = 0
    assert "-an" in _manual_command(tmp_path, plan)


def test_local1_volume_adjustment(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["volume"] = 1.5
    command = _manual_command(tmp_path, plan)
    assert command[command.index("-af") + 1] == "volume=1.5"


def test_local1_text_overlay(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["text_overlay"] = {"content": "Xin chao", "position": "bottom", "start_ms": 0, "end_ms": 10_000, "font_size": 42, "outline": 2}
    joined = _joined(_manual_command(tmp_path, plan))
    assert "drawtext=" in joined
    assert "bordercolor=black@0.9" in joined


def test_local1_logo_overlay(tmp_path: Path) -> None:
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"logo")
    plan = _plan(tmp_path)
    plan["logo_overlay"] = {"path": str(logo), "position": "top_right", "scale": 0.12, "opacity": 0.75}
    joined = _joined(_manual_command(tmp_path, plan))
    assert "scale=w=230:h=-2" in joined and "overlay=" in joined
    assert "scale2ref" not in joined
    assert "aa=0.750" in joined


def test_local1_logo_scale_uses_final_rotated_frame_width(tmp_path: Path) -> None:
    logo = tmp_path / "logo.webp"
    logo.write_bytes(b"logo")
    plan = _plan(tmp_path)
    plan["rotation"] = 90
    plan["logo_overlay"] = {
        "path": str(logo),
        "position": "bottom_left",
        "scale": 0.12,
        "opacity": 1.0,
    }

    joined = _joined(_manual_command(tmp_path, plan, _probe(width=1920, height=1080)))

    # Rotation swaps the final frame to 1080x1920, so 12% width rounds to 130px.
    assert "scale=w=130:h=-2" in joined
    assert "scale2ref" not in joined


def test_local1_webp_logo_is_accepted_by_intake_and_worker_contract() -> None:
    assert ".webp" in validation.ALLOWED_LOGO_EXTENSIONS
    assert validation.validate_extension("brand.webp", validation.ALLOWED_LOGO_EXTENSIONS) == "brand.webp"


def test_local1_burn_srt(tmp_path: Path) -> None:
    srt = tmp_path / "subtitle.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nXin chao\n", encoding="utf-8")
    plan = _plan(tmp_path)
    plan["subtitle_file"] = str(srt)
    joined = _joined(_manual_command(tmp_path, plan))
    assert "subtitles=" in joined
    assert "Outline=2" in joined and "MarginV=42" in joined
    assert "drawbox" not in joined


def test_local1_color_preset(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["color_preset"] = "warm"
    assert "colorbalance=" in _joined(_manual_command(tmp_path, plan))


@pytest.mark.parametrize(
    ("preset", "expected_filter"),
    [
        ("bright_clear", "eq=brightness=0.025"),
        ("light_cinematic", "eq=brightness=-0.01"),
        ("warm", "colorbalance=rs=0.06"),
        ("cool", "colorbalance=rs=-0.04"),
        ("high_contrast", "eq=contrast=1.25"),
        ("black_white", "hue=s=0"),
    ],
)
def test_local1_every_public_color_preset_compiles_to_ffmpeg(
    tmp_path: Path,
    preset: str,
    expected_filter: str,
) -> None:
    plan = _plan(tmp_path)
    plan["color_preset"] = preset
    assert expected_filter in _joined(_manual_command(tmp_path, plan))


def test_local1_no_shell_true() -> None:
    source = (ROOT / "services" / "video_local_editing.py").read_text(encoding="utf-8")
    assert "shell=True" not in source
    assert "subprocess.run(command" in source


def test_local1_path_traversal_blocked(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    with pytest.raises(validation.LocalVideoValidationError, match="path_outside_workspace"):
        validation.require_path_within(tmp_path / "outside.mp4", root)


def test_local1_split_fixed_duration_exact_coverage() -> None:
    ranges = splitter.split_fixed_duration(3_600_000, 600_000)
    coverage = splitter.validate_exact_coverage(ranges, 3_600_000)
    assert len(ranges) == 6 and coverage["ok"] is True


def test_local1_split_fixed_duration_last_part_shorter() -> None:
    ranges = splitter.split_fixed_duration(95_000, 30_000)
    assert [item.duration_ms for item in ranges] == [30_000, 30_000, 30_000, 5_000]


def test_local1_split_fixed_duration_merges_a_remainder_below_the_minimum() -> None:
    ranges = splitter.split_fixed_duration(5_000, 2_000)
    assert [item.duration_ms for item in ranges] == [2_000, 3_000]
    assert splitter.validate_exact_coverage(ranges, 5_000)["ok"] is True


def test_local1_split_exact_part_count() -> None:
    ranges = splitter.split_exact_count(3_600_000, 8)
    assert len(ranges) == 8
    assert all(item.duration_ms == 450_000 for item in ranges)


def test_local1_split_exact_count_no_gap() -> None:
    ranges = splitter.split_exact_count(100_000, 3)
    assert all(ranges[index].end_ms == ranges[index + 1].start_ms for index in range(2))


def test_local1_split_exact_count_no_overlap() -> None:
    ranges = splitter.split_exact_count(100_001, 3)
    assert splitter.validate_exact_coverage(ranges, 100_001)["no_overlap"] is True


def test_local1_split_exact_count_final_end_matches_source() -> None:
    assert splitter.split_exact_count(100_001, 3)[-1].end_ms == 100_001


def test_local1_split_custom_ranges() -> None:
    ranges = splitter.split_custom_ranges(315_000, "00:00-01:30\n01:30-03:00\n03:00-05:15")
    assert [(item.start_ms, item.end_ms) for item in ranges] == [(0, 90_000), (90_000, 180_000), (180_000, 315_000)]


def test_local1_split_reject_invalid_range() -> None:
    with pytest.raises(splitter.SplitPlanError, match="invalid_range"):
        splitter.split_custom_ranges(60_000, "00:20-00:10", allow_gaps=True)


def test_local1_split_reject_overlap() -> None:
    with pytest.raises(splitter.SplitPlanError, match="range_overlap"):
        splitter.split_custom_ranges(60_000, "00:00-00:40\n00:30-01:00")


def test_local1_split_reject_end_after_duration() -> None:
    with pytest.raises(splitter.SplitPlanError, match="range_after_duration"):
        splitter.split_custom_ranges(60_000, "00:00-01:01")


def test_local1_split_short_video() -> None:
    with pytest.raises(splitter.SplitPlanError, match="part_count_invalid"):
        splitter.split_fixed_duration(3_000, 10_000)


def test_local1_split_one_part() -> None:
    with pytest.raises(splitter.SplitPlanError, match="part_count_invalid"):
        splitter.split_exact_count(60_000, 1)


def test_local1_full_source_single_range_is_not_an_effective_edit() -> None:
    assert editing.plan_has_effective_operation(
        {},
        source_duration_ms=60_000,
        split_ranges=[{"index": 1, "start_ms": 0, "end_ms": 60_000}],
    ) is False


def test_local1_outputs_named_in_order() -> None:
    assert [splitter.split_output_name(index, 6) for index in range(1, 4)] == [
        "toan_aas_part_001_of_006.mp4",
        "toan_aas_part_002_of_006.mp4",
        "toan_aas_part_003_of_006.mp4",
    ]


def test_local1_parts_delivered_in_order() -> None:
    worker = _between(WORKER_SOURCE, "def run_video_local_edit", "def _aiedit_progress")
    assert "for index, item in enumerate(outputs, start=1)" in worker
    assert "Phần {index}/{total}" in worker


def test_local1_only_mp4_delivered() -> None:
    worker = _between(WORKER_SOURCE, "def run_video_local_edit", "def _aiedit_progress")
    assert "delivery_file_allowed(output_path, workspace=workspace)" in worker
    assert "toan_aas_video_edit_{job_id}.mp4" in worker


def test_local1_zip_contains_only_mp4(tmp_path: Path) -> None:
    workspace = validation.create_job_workspace("zip_test", root=tmp_path / "video_local")
    parts = []
    for index in range(1, 3):
        part = workspace / splitter.split_output_name(index, 2)
        part.write_bytes(b"x" * 2048)
        parts.append(part)
    archive_path = validation.build_safe_mp4_zip(workspace / "parts.zip", parts, workspace=workspace)
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.namelist() == [item.name for item in parts]


def test_local1_database_artifact_blocked(tmp_path: Path) -> None:
    workspace = validation.create_job_workspace("db_test", root=tmp_path / "video_local")
    database = workspace / "secret.db"
    database.write_bytes(b"x" * 2048)
    assert validation.delivery_file_allowed(database, workspace=workspace) is False
    with pytest.raises(validation.LocalVideoValidationError, match="zip_contains_forbidden_artifact"):
        validation.build_safe_mp4_zip(workspace / "parts.zip", [database], workspace=workspace)


def test_local1_internal_path_not_exposed() -> None:
    public = _between(BOT_SOURCE, "def video_editor_job_status_text", "VIDEO_PUBLIC_ROUTE_FORBIDDEN_WORDS")
    for forbidden in ("VIDEO_LOCAL_WORKSPACE_ROOT", "absolute", "input_file_id", "output_url"):
        assert forbidden not in public


def test_local1_invalid_mp4_not_delivered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "invalid.mp4"
    output.write_bytes(b"x" * 2048)
    monkeypatch.setattr(validation, "probe_video_file", lambda *args, **kwargs: {"ok": False, "reason": "invalid_video_metadata"})
    assert validation.validate_mp4_output(output)["ok"] is False


def test_local1_zero_byte_output_failed(tmp_path: Path) -> None:
    output = tmp_path / "zero.mp4"
    output.write_bytes(b"")
    assert validation.validate_mp4_output(output)["reason"] == "output_too_small"


def test_local1_missing_video_stream_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "audio.mp4"
    output.write_bytes(b"x" * 2048)
    monkeypatch.setattr(validation, "probe_video_file", lambda *args, **kwargs: {"ok": False, "reason": "invalid_video_metadata", "has_video": False})
    assert validation.validate_mp4_output(output)["ok"] is False


def test_local1_trim_duration_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "trim.mp4"
    output.write_bytes(b"x" * 2048)
    monkeypatch.setattr(validation, "probe_video_file", lambda *args, **kwargs: _valid_probe(10_000))
    assert validation.validate_mp4_output(output, expected_duration_ms=10_000)["ok"] is True
    assert validation.validate_mp4_output(output, expected_duration_ms=20_000)["reason"] == "output_duration_mismatch"


def test_local1_speed_duration_validation(tmp_path: Path) -> None:
    plan = _plan(tmp_path, 60_000)
    plan["speed"] = 2.0
    assert editing.expected_manual_duration_ms(plan) == 30_000


def test_local1_split_part_duration_validation() -> None:
    item = splitter.SplitRange(index=1, start_ms=12_000, end_ms=42_000)
    command = editing.build_split_ffmpeg_command("source.mp4", item, "part.mp4", ffmpeg_path="ffmpeg", has_audio=True)
    assert command[command.index("-t") + 1] == "30.000"


def test_local1_split_total_duration_coverage() -> None:
    ranges = splitter.split_fixed_duration(95_000, 30_000)
    assert sum(item.duration_ms for item in ranges) == 95_000


def test_local1_trim_preserves_audio(tmp_path: Path) -> None:
    command = _manual_command(tmp_path)
    assert "0:a:0?" in command and "-c:a" in command


def test_local1_split_preserves_audio() -> None:
    item = splitter.SplitRange(1, 0, 10_000)
    command = editing.build_split_ffmpeg_command("source.mp4", item, "part.mp4", ffmpeg_path="ffmpeg", has_audio=True)
    assert "0:a:0?" in command and "aac" in command


def test_local1_speed_preserves_av_sync(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["speed"] = 0.75
    command = _manual_command(tmp_path, plan)
    assert "setpts=PTS/0.75" in _joined(command)
    assert "atempo=0.75" in _joined(command)


def test_local1_no_audio_input_supported(tmp_path: Path) -> None:
    command = _manual_command(tmp_path, probe=_probe(audio=False))
    assert "-an" in command


def test_local1_mute_removes_audio_stream(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    plan["volume"] = 0
    command = _manual_command(tmp_path, plan)
    assert "-an" in command and "-c:a" not in command


def test_local1_progress_monotonic() -> None:
    worker = _between(WORKER_SOURCE, "def run_video_local_edit", "def _aiedit_progress")
    positions = [worker.index(f'"{stage}"') for stage in ("inspecting_input", "delivering", "delivered")]
    assert positions == sorted(positions)
    assert "percentage" not in _between(BOT_SOURCE, "def video_editor_job_status_text", "VIDEO_PUBLIC_ROUTE_FORBIDDEN_WORDS")


def test_local1_split_progress_part_count() -> None:
    worker = _between(WORKER_SOURCE, "def run_video_local_edit", "def _aiedit_progress")
    assert 'processed=int(status.get("processed") or 0)' in worker
    assert 'total=int(status.get("total") or len(ranges) or 1)' in worker


def test_local1_no_success_before_delivery() -> None:
    worker = _between(WORKER_SOURCE, "def run_video_local_edit", "def _aiedit_progress")
    assert worker.rindex("send_video_edit_artifact(") < worker.index('terminal_status = "succeeded"')
    assert worker.index("telegram_delivery_identity(delivery)") < worker.index('terminal_status = "succeeded"')
    assert worker.index('if delivery.get("sent") is True') < worker.index('terminal_status = "succeeded"')


def test_local1_single_terminal_outcome() -> None:
    worker = _between(WORKER_SOURCE, "def run_video_local_edit", "def _aiedit_progress")
    finally_block = worker.split("finally:", 1)[1]
    assert finally_block.count("update_job(") == 1


def test_local1_cleanup_failure_does_not_reverse_completed_delivery() -> None:
    worker = _between(WORKER_SOURCE, "def run_video_local_edit", "def _aiedit_progress")
    finally_block = worker.split("finally:", 1)[1]
    helper = _between(WORKER_SOURCE, "def finalize_video_local_cleanup_state", "def run_video_local_edit")
    assert "finalize_video_local_cleanup_state(" in finally_block
    assert "if delivery_receipts or delivery_was_uncertain:" in helper
    assert 'if str(detail.get("stage") or "").lower() != "delivered"' in helper
    assert 'detail["cleanup"] = "failed"' in helper
    assert 'return str(terminal_status or "failed"), detail' in helper


def test_local1_no_duplicate_delivery() -> None:
    worker = _between(WORKER_SOURCE, "def run_video_local_edit", "def _aiedit_progress")
    assert "retry" not in worker.lower()
    assert worker.count("for index, item in enumerate(outputs, start=1)") == 1


def test_local1_failure_reports_no_charge() -> None:
    worker = _between(WORKER_SOURCE, "def run_video_local_edit", "def _aiedit_progress")
    assert '"stage": "failed_no_charge"' in worker
    assert worker.count('"charge": 0') >= 3


def test_local1_split_part_limit() -> None:
    with pytest.raises(splitter.SplitPlanError, match="too_many_parts"):
        splitter.split_exact_count(120_000, validation.MAX_SPLIT_PARTS + 1)


def test_local1_minimum_segment_limit() -> None:
    with pytest.raises(splitter.SplitPlanError, match="segment_too_short"):
        splitter.split_fixed_duration(10_000, 1_000)


def test_local1_one_active_job_per_user() -> None:
    source = _between(BOT_SOURCE, "def count_active_video_local_jobs", "async def submit_local_video_editor_job")
    assert "status IN ('queued','running')" in source
    assert validation.MAX_ACTIVE_JOBS_PER_USER == 1


def test_local1_ffmpeg_timeout_failed_no_charge(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("ffmpeg", 1)

    monkeypatch.setattr(editing.subprocess, "run", timeout)
    with pytest.raises(editing.LocalVideoEditError, match="ffmpeg_timeout"):
        editing._run(["ffmpeg", "-version"], timeout=1)


def test_local1_workspace_limit(tmp_path: Path) -> None:
    workspace = validation.create_job_workspace("limit", root=tmp_path / "video_local")
    (workspace / "large.bin").write_bytes(b"x" * 32)
    with pytest.raises(validation.LocalVideoValidationError, match="workspace_limit_exceeded"):
        validation.enforce_workspace_limit(workspace, maximum_bytes=16)


def test_local1_cleanup_after_success(tmp_path: Path) -> None:
    workspace = validation.create_job_workspace("success", root=tmp_path / "video_local")
    (workspace / "output.mp4").write_bytes(b"x")
    result = validation.cleanup_job_workspace(workspace, root=tmp_path / "video_local")
    assert result["ok"] is True and not workspace.exists()


def test_local1_cleanup_after_failure(tmp_path: Path) -> None:
    workspace = validation.create_job_workspace("failure", root=tmp_path / "video_local")
    (workspace / "partial.mp4").write_bytes(b"x")
    assert validation.cleanup_job_workspace(workspace, root=tmp_path / "video_local")["removed"] is True


def test_local1_cleanup_does_not_delete_database(tmp_path: Path) -> None:
    database = tmp_path / "bot.db"
    database.write_bytes(b"database")
    workspace = validation.create_job_workspace("safe", root=tmp_path / "video_local")
    validation.cleanup_job_workspace(workspace, root=tmp_path / "video_local")
    assert database.read_bytes() == b"database"


def test_local1_cleanup_is_scoped_to_job_workspace(tmp_path: Path) -> None:
    root = tmp_path / "video_local"
    first = validation.create_job_workspace("first", root=root)
    second = validation.create_job_workspace("second", root=root)
    validation.cleanup_job_workspace(first, root=root)
    assert not first.exists() and second.exists()
    blocked = validation.cleanup_job_workspace(tmp_path, root=root)
    assert blocked["ok"] is False


def test_local1_status_masks_paths_and_secrets() -> None:
    command = _between(BOT_SOURCE, "async def cmd_video_local_status", "def _video_local_safe_failure_reason")
    for forbidden in ("ffmpeg_path_seen", "VIDEO_LOCAL_WORKSPACE_ROOT", "TELEGRAM_BOT_TOKEN", "API_KEY"):
        assert forbidden not in command


def test_local1_job_debug_reports_split_truth() -> None:
    command = _between(BOT_SOURCE, "async def cmd_video_local_job_debug", "async def cmd_local_jobs")
    assert "split_ranges" in command
    assert "Processed" in command and "Delivery count" in command
    assert "Cleanup" in command and "Charged amount" in command


def test_local1_job_debug_reports_validation_failure() -> None:
    command = _between(BOT_SOURCE, "async def cmd_video_local_job_debug", "async def cmd_local_jobs")
    assert "Output validation" in command and "Failure reason" in command
    assert "_video_local_safe_failure_reason" in command


def test_local1_no_new_pricing_created() -> None:
    files = [
        ROOT / "services" / "video_local_editing.py",
        ROOT / "services" / "video_smart_splitter.py",
        ROOT / "services" / "video_local_validation.py",
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert "price_xu" in source
    assert '"price_xu": 0' in source
    for forbidden in ("pricing_table", "package_price", "wallet_debit"):
        assert forbidden not in source


def test_local1_no_charge_before_delivery() -> None:
    submit = _between(BOT_SOURCE, "async def submit_local_video_editor_job", "async def handle_video_editor_pending_upload")
    assert '"xu_cost": 0' not in submit
    assert '"charge_policy": "after_valid_mp4_delivery"' in submit
    assert "video_editengine1.create_job(" in submit
    for forbidden in ("spend_fixed_credit_info", "deduct_dynamic_credit", "charge_user"):
        assert forbidden not in submit


def test_local1_failure_charge_zero() -> None:
    worker = _between(WORKER_SOURCE, "def run_video_local_edit", "def _aiedit_progress")
    assert '"charge": 0' in worker
    assert "refund" not in worker.lower()


def test_local1_no_payos_changes() -> None:
    changed = subprocess.run(["git", "diff", "--name-only", "origin/main"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.lower()
    assert "payos" not in changed and "payment" not in changed


def test_local1_no_wallet_business_rule_changes() -> None:
    changed = subprocess.run(["git", "diff", "--name-only", "origin/main"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.lower()
    assert "wallet" not in changed


def test_local1_services_do_not_call_real_providers() -> None:
    source = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "services/video_local_editing.py",
            "services/video_smart_splitter.py",
            "services/video_local_validation.py",
        )
    )
    for forbidden in ("ShopAIKey", "Key4U", "httpx", "requests.", "urllib.request", "provider.submit"):
        assert forbidden not in source


def test_local1_route_matrix_is_canonical() -> None:
    route = _between(BOT_SOURCE, '"video_local_edit": {', "def video_public_route_for_tool")
    assert '"expected_children": ("videoedit|ai", "videoedit|manual", "videoedit|restore", "videoedit|guide", "videoedit|latest_status")' in route
    assert '"back_target": "menu|main_video"' in route
    assert '"job_reachable": True' in route


def test_local1_admin_commands_registered() -> None:
    assert 'CommandHandler("video_local_status", admin_internal_command(cmd_video_local_status))' in BOT_SOURCE
    assert 'CommandHandler("video_local_job_debug", admin_internal_command(cmd_video_local_job_debug))' in BOT_SOURCE


def test_local1_output_resolution_is_capped_for_4k(tmp_path: Path) -> None:
    command = _manual_command(tmp_path, probe=_probe(width=3840, height=2160))
    assert "scale=1920:1080:force_original_aspect_ratio=decrease" in _joined(command)
    split_command = editing.build_split_ffmpeg_command(
        "source.mp4", splitter.SplitRange(1, 0, 10_000), "part.mp4", ffmpeg_path="ffmpeg", has_audio=True
    )
    assert "min(iw,1920)" in _joined(split_command)


def test_local1_keep_aspect_4k_preserves_geometry(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    command = _joined(_manual_command(tmp_path, plan, _probe(width=3840, height=2160)))
    assert "scale=1920:1080" in command
    assert "pad=1920:1080" in command


def test_local1_vietnamese_font_resolution_uses_existing_unicode_font(tmp_path: Path) -> None:
    font = tmp_path / "NotoSans-Regular.ttf"
    font.write_bytes(b"font")
    assert editing.resolve_vietnamese_font_path(str(font)) == str(font)


def test_local1_worker_ready_requires_ffmpeg_and_ffprobe() -> None:
    source = _between(BOT_SOURCE, "def video_editor_worker_ready", "def main_video_keyboard")
    assert 'status.get("ffprobe_path_configured")' in source
    assert 'local_worker:ffmpeg_path_seen' in source


def test_local1_real_ffmpeg_trim_speed_preserves_audio(tmp_path: Path) -> None:
    workspace = validation.create_job_workspace("real_manual", root=tmp_path / "video_local")
    source = workspace / "source.mp4"
    ffmpeg, ffprobe = _real_ffmpeg_fixture(source)
    plan = editing.default_manual_edit_plan(str(source))
    plan["trim"] = {"start_ms": 500, "end_ms": 4_500}
    plan["speed"] = 1.25
    output = workspace / "toan_aas_video_edit_real.mp4"
    result = editing.execute_manual_edit(
        plan,
        output_path=str(output),
        workspace=workspace,
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        timeout=45,
    )
    assert result["ok"] is True
    assert result["validation"]["has_audio"] is True
    assert abs(int(result["validation"]["duration_ms"]) - 3_200) <= 900


def test_local1_real_ffmpeg_split_outputs_valid_ordered_mp4(tmp_path: Path) -> None:
    workspace = validation.create_job_workspace("real_split", root=tmp_path / "video_local")
    source = workspace / "source.mp4"
    ffmpeg, ffprobe = _real_ffmpeg_fixture(source)
    source_probe = validation.probe_video_file(source, ffprobe_path=ffprobe)
    ranges = splitter.split_fixed_duration(int(source_probe["duration_ms"]), 2_000)
    result = editing.execute_split_plan(
        str(source),
        ranges,
        workspace=workspace,
        coverage_required=True,
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        timeout=45,
    )
    assert result["ok"] is True
    assert [Path(item["path"]).name for item in result["outputs"]] == [
        "toan_aas_part_001_of_002.mp4",
        "toan_aas_part_002_of_002.mp4",
    ]
    assert all(item["validation"]["ok"] and item["validation"]["has_audio"] for item in result["outputs"])
    assert abs(int(result["actual_total_duration_ms"]) - int(result["source_duration_ms"])) <= 2_500


def test_local1_real_ffmpeg_concat_normalizes_missing_audio(tmp_path: Path) -> None:
    workspace = validation.create_job_workspace("real_concat", root=tmp_path / "video_local")
    first = workspace / "first.mp4"
    second = workspace / "second.mp4"
    ffmpeg, ffprobe = _real_ffmpeg_fixture(first, duration_seconds=3, audio=True)
    _real_ffmpeg_fixture(second, duration_seconds=3, audio=False)
    plan = editing.default_manual_edit_plan(str(first))
    plan["trim"] = {"start_ms": 0, "end_ms": 3_000}
    plan["concat_inputs"] = [str(second)]
    output = workspace / "toan_aas_video_edit_concat.mp4"
    result = editing.execute_manual_edit(
        plan,
        output_path=str(output),
        workspace=workspace,
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        timeout=60,
    )
    assert result["ok"] is True
    assert result["validation"]["has_audio"] is True
    assert abs(int(result["validation"]["duration_ms"]) - 6_000) <= 1_200


def test_local1_real_ffmpeg_vietnamese_text_logo_and_srt(tmp_path: Path) -> None:
    workspace = validation.create_job_workspace("real_overlay", root=tmp_path / "video_local")
    source = workspace / "source.mp4"
    ffmpeg, ffprobe = _real_ffmpeg_fixture(source, duration_seconds=3, audio=True)
    logo = workspace / "logo.png"
    logo_result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f", "lavfi",
            "-i", "color=c=red@0.8:s=80x40",
            "-frames:v", "1",
            "-update", "1",
            str(logo),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert logo_result.returncode == 0, logo_result.stderr[-1200:]
    subtitle = workspace / "subtitle.srt"
    subtitle.write_text(
        "1\n00:00:00,200 --> 00:00:02,600\nPhụ đề tiếng Việt rõ ràng\n",
        encoding="utf-8",
    )
    plan = editing.default_manual_edit_plan(str(source))
    plan["trim"] = {"start_ms": 0, "end_ms": 3_000}
    plan["text_overlay"] = {
        "content": "Chữ tiếng Việt",
        "position": "top",
        "start_ms": 0,
        "end_ms": 2_800,
        "font_size": 28,
        "outline": 2,
    }
    plan["logo_overlay"] = {
        "path": str(logo),
        "position": "top_right",
        "scale": 0.12,
        "opacity": 0.75,
    }
    plan["subtitle_file"] = str(subtitle)
    output = workspace / "toan_aas_video_edit_overlay.mp4"
    result = editing.execute_manual_edit(
        plan,
        output_path=str(output),
        workspace=workspace,
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        timeout=60,
    )
    assert result["ok"] is True
    assert result["validation"]["has_audio"] is True
