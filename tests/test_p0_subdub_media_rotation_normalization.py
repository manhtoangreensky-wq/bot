"""Tests for SubDub media normalization with rotation metadata."""

import asyncio
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pytest

import bot
from services import subdub_media_preflight


def _resolve_test_ffmpeg() -> str:
    candidates = [
        shutil.which("ffmpeg"),
        shutil.which("ffmpeg.exe"),
        str(Path(sys.executable).with_name("ffmpeg")),
        str(Path(sys.executable).with_name("ffmpeg.exe")),
    ]
    for cand in candidates:
        if cand and Path(cand).is_file():
            return cand
    raise RuntimeError("ffmpeg executable unavailable for rotation normalization tests")


def _create_rotated_mp4(target_path: Path, rotation: int, width: int = 848, height: int = 480) -> bytes:
    ffmpeg_bin = _resolve_test_ffmpeg()
    cmd = [ffmpeg_bin, "-y"]
    if rotation:
        cmd.extend(["-noautorotate", "-display_rotation:v:0", str(rotation)])
    cmd.extend([
        "-f", "lavfi",
        "-i", f"color=c=blue:s={width}x{height}:d=1,format=yuv420p",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        str(target_path),
    ])
    subprocess.run(cmd, check=True, capture_output=True)
    return target_path.read_bytes()


def test_rotation_270_first_red_and_fix(tmp_path: Path):
    """Test A: rotation 270 input preserves display geometry and canonicalizes rotation to 0."""
    fixture_path = tmp_path / "rot270.mp4"
    source_bytes = _create_rotated_mp4(fixture_path, rotation=270, width=848, height=480)

    source_probe = asyncio.run(bot.subdub_probe_video_bytes(source_bytes))
    assert source_probe.get("ok") is True
    assert source_probe.get("rotation") == 270
    assert source_probe.get("coded_width") == 848
    assert source_probe.get("coded_height") == 480
    assert source_probe.get("display_width") == 480
    assert source_probe.get("display_height") == 848
    assert source_probe.get("coded_width") != source_probe.get("display_width")
    assert source_probe.get("coded_height") != source_probe.get("display_height")

    norm_res = asyncio.run(bot.subdub_normalize_video_bytes_if_needed(source_bytes, content_type="video/mp4"))
    assert norm_res.get("ok") is True, f"Normalization failed: {norm_res.get('blocker')}"
    assert norm_res.get("geometry_preserved") is True
    assert norm_res.get("duration_preserved") is True

    norm_probe = norm_res.get("normalized_probe") or {}
    assert norm_probe.get("rotation") == 0
    assert norm_probe.get("display_width") == 480
    assert norm_probe.get("display_height") == 848
    assert norm_probe.get("coded_width") == 480
    assert norm_probe.get("coded_height") == 848


def test_rotation_90_symmetry(tmp_path: Path):
    """Test B: rotation 90 symmetry test."""
    fixture_path = tmp_path / "rot90.mp4"
    source_bytes = _create_rotated_mp4(fixture_path, rotation=90, width=848, height=480)

    source_probe = asyncio.run(bot.subdub_probe_video_bytes(source_bytes))
    assert source_probe.get("ok") is True
    assert source_probe.get("rotation") == 90
    assert source_probe.get("coded_width") == 848
    assert source_probe.get("coded_height") == 480
    assert source_probe.get("display_width") == 480
    assert source_probe.get("display_height") == 848

    norm_res = asyncio.run(bot.subdub_normalize_video_bytes_if_needed(source_bytes, content_type="video/mp4"))
    assert norm_res.get("ok") is True, f"Normalization failed: {norm_res.get('blocker')}"
    assert norm_res.get("geometry_preserved") is True
    assert norm_res.get("duration_preserved") is True

    norm_probe = norm_res.get("normalized_probe") or {}
    assert norm_probe.get("rotation") == 0
    assert norm_probe.get("display_width") == 480
    assert norm_probe.get("display_height") == 848
    assert norm_probe.get("coded_width") == 480
    assert norm_probe.get("coded_height") == 848


def test_rotation_0_no_regression(tmp_path: Path):
    """Test C: unrotated MP4 (rotation 0) remains unchanged in orientation."""
    fixture_path = tmp_path / "rot0.mp4"
    source_bytes = _create_rotated_mp4(fixture_path, rotation=0, width=848, height=480)

    source_probe = asyncio.run(bot.subdub_probe_video_bytes(source_bytes))
    assert source_probe.get("ok") is True
    assert source_probe.get("rotation") == 0
    assert source_probe.get("coded_width") == 848
    assert source_probe.get("coded_height") == 480
    assert source_probe.get("display_width") == 848
    assert source_probe.get("display_height") == 480

    norm_res = asyncio.run(bot.subdub_normalize_video_bytes_if_needed(source_bytes, content_type="video/mp4"))
    if norm_res.get("normalized"):
        assert norm_res.get("ok") is True
        assert norm_res.get("geometry_preserved") is True
        norm_probe = norm_res.get("normalized_probe") or {}
        assert norm_probe.get("rotation") == 0
        assert norm_probe.get("display_width") == 848
        assert norm_probe.get("display_height") == 480
    else:
        assert norm_res.get("ok") is True


def test_duration_preserved():
    """Test D: duration preservation contract."""
    assert subdub_media_preflight.duration_matches_source(10.0, 10.0) is True
    assert subdub_media_preflight.duration_matches_source(10.0, 10.2) is True
    assert subdub_media_preflight.duration_matches_source(10.0, 10.35) is True
    assert subdub_media_preflight.duration_matches_source(10.0, 10.5) is False
    assert subdub_media_preflight.duration_matches_source(0.0, 10.0) is False


def test_fail_closed_on_real_geometry_change(monkeypatch):
    """Test E: genuinely geometry-changing output must fail closed with geometry mismatch."""
    dummy_bytes = b"fake_video_bytes"

    async def fake_run_ffmpeg(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"dummy_normalized_mp4")
        return True, "ok"

    monkeypatch.setattr(bot, "run_subdub_ffmpeg_command", fake_run_ffmpeg)

    call_count = 0

    async def mock_probe_sequence(b):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # source probe: 1920x1080
            return {
                "ok": True,
                "detail": "ok",
                "duration": 5.0,
                "rotation": 0,
                "coded_width": 1920,
                "coded_height": 1080,
                "display_width": 1920,
                "display_height": 1080,
                "normalization_required": True,
            }
        else:
            # corrupted normalized probe: 1280x720 (genuine geometry change!)
            return {
                "ok": True,
                "detail": "ok",
                "duration": 5.0,
                "rotation": 0,
                "coded_width": 1280,
                "coded_height": 720,
                "display_width": 1280,
                "display_height": 720,
                "normalization_required": False,
            }

    monkeypatch.setattr(bot, "subdub_probe_video_bytes", mock_probe_sequence)

    res = asyncio.run(bot.subdub_normalize_video_bytes_if_needed(dummy_bytes, content_type="video/mp4"))
    assert res.get("ok") is False
    assert res.get("blocker") == "media_normalization_geometry_mismatch"
    assert res.get("geometry_preserved") is False


def test_r2_command_construction_display_rotation_override():
    """R2 Command Contract: non-zero rotation must place -display_rotation:v:0 0 before -i."""
    # Case A: rotation 270
    cmd270 = subdub_media_preflight.build_normalization_command(
        "/usr/bin/ffmpeg", "/tmp/in270.mp4", "/tmp/out270.mp4",
        {"duration": 10.0, "rotation": 270, "has_video": True},
    )
    idx_i_270 = cmd270.index("-i")
    prefix270 = cmd270[:idx_i_270]
    assert "-noautorotate" in prefix270
    assert "-display_rotation:v:0" in prefix270
    rot_flag_idx270 = prefix270.index("-display_rotation:v:0")
    assert prefix270[rot_flag_idx270 + 1] == "0"
    vf_idx270 = cmd270.index("-vf")
    vf_str270 = cmd270[vf_idx270 + 1]
    assert "transpose=cclock" in vf_str270
    assert "sidedata=mode=delete:type=DISPLAYMATRIX" in vf_str270

    # Case B: rotation 90
    cmd90 = subdub_media_preflight.build_normalization_command(
        "/usr/bin/ffmpeg", "/tmp/in90.mp4", "/tmp/out90.mp4",
        {"duration": 10.0, "rotation": 90, "has_video": True},
    )
    idx_i_90 = cmd90.index("-i")
    prefix90 = cmd90[:idx_i_90]
    assert "-noautorotate" in prefix90
    assert "-display_rotation:v:0" in prefix90
    rot_flag_idx90 = prefix90.index("-display_rotation:v:0")
    assert prefix90[rot_flag_idx90 + 1] == "0"
    vf_idx90 = cmd90.index("-vf")
    vf_str90 = cmd90[vf_idx90 + 1]
    assert "transpose=clock" in vf_str90
    assert "sidedata=mode=delete:type=DISPLAYMATRIX" in vf_str90

    # Case C: rotation 180
    cmd180 = subdub_media_preflight.build_normalization_command(
        "/usr/bin/ffmpeg", "/tmp/in180.mp4", "/tmp/out180.mp4",
        {"duration": 10.0, "rotation": 180, "has_video": True},
    )
    idx_i_180 = cmd180.index("-i")
    prefix180 = cmd180[:idx_i_180]
    assert "-noautorotate" in prefix180
    assert "-display_rotation:v:0" in prefix180
    rot_flag_idx180 = prefix180.index("-display_rotation:v:0")
    assert prefix180[rot_flag_idx180 + 1] == "0"
    vf_idx180 = cmd180.index("-vf")
    vf_str180 = cmd180[vf_idx180 + 1]
    assert "hflip" in vf_str180 and "vflip" in vf_str180
    assert "sidedata=mode=delete:type=DISPLAYMATRIX" in vf_str180

    # Case D: rotation 0
    cmd0 = subdub_media_preflight.build_normalization_command(
        "/usr/bin/ffmpeg", "/tmp/in0.mp4", "/tmp/out0.mp4",
        {"duration": 10.0, "rotation": 0, "has_video": True},
    )
    assert "-display_rotation:v:0" not in cmd0
    assert "-noautorotate" not in cmd0

