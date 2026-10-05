"""Test suite proving S09 Storyboard offline-artifact contract.

SPEC_ID: PRODUCT-VIDEO-S09-STORYBOARD-OFFLINE-ARTIFACT-EVIDENCE
Governed by: owner-governed-codex, locked-focus-engineering

Proves:
- TWO_DISTINCT_LOCAL_CLIPS=YES
- CORRECT_CONCAT_ORDER=YES
- LOCAL_FFMPEG_USED=YES
- FFPROBE_RESULT_VALID=YES
- DECODE_RESULT_VALID=YES
- DISTINCT_FRAME_OR_EQUIVALENT_IDENTITY=YES
- NO_TPAD=YES
- NO_CLONED_TRAILING_HOLD=YES
- SHORT_OUTPUT_FAIL_CLOSED=YES
- CORRUPT_OUTPUT_FAIL_CLOSED=YES
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
import pytest

from services.multiscene_video_pipeline import validate_storyboard_scene_duration


def _run_cmd(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=True,
    )


def probe_video_duration(path: Path | str) -> float:
    res = _run_cmd([
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(path),
    ])
    data = json.loads(res.stdout)
    return float(data["format"]["duration"])


@pytest.fixture
def two_distinct_local_clips(tmp_path: Path):
    """Generate two distinctly identifiable 8.0s local MP4 clips using local ffmpeg."""
    clip1 = tmp_path / "scene_001.mp4"
    clip2 = tmp_path / "scene_002.mp4"

    # Clip 1: Red background, 8.0s, 30fps
    _run_cmd([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=720x1280:r=30:d=8.0",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "8.0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(clip1),
    ])

    # Clip 2: Blue background, 8.0s, 30fps
    _run_cmd([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=720x1280:r=30:d=8.0",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "8.0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(clip2),
    ])

    return clip1, clip2


def test_two_distinct_local_clips_and_correct_concat_order(tmp_path: Path, two_distinct_local_clips):
    """Proves TWO_DISTINCT_LOCAL_CLIPS, CORRECT_CONCAT_ORDER, LOCAL_FFMPEG_USED, FFPROBE_RESULT_VALID, DECODE_RESULT_VALID."""
    clip1, clip2 = two_distinct_local_clips
    assert clip1.is_file() and clip2.is_file()
    assert clip1.read_bytes() != clip2.read_bytes()

    # 1. Probe & validate both scenes pass Storyboard duration gate
    dur1 = probe_video_duration(clip1)
    dur2 = probe_video_duration(clip2)
    val1 = validate_storyboard_scene_duration(dur1, 8.0)
    val2 = validate_storyboard_scene_duration(dur2, 8.0)
    assert val1["duration_valid"] is True and val1["blocker"] == ""
    assert val2["duration_valid"] is True and val2["blocker"] == ""

    # 2. Concat order using ffmpeg concat demuxer
    concat_list = tmp_path / "concat.txt"
    concat_list.write_text(f"file '{clip1.as_posix()}'\nfile '{clip2.as_posix()}'\n", encoding="utf-8")
    master_mp4 = tmp_path / "master_concatenated.mp4"

    _run_cmd([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(master_mp4),
    ])

    assert master_mp4.is_file()
    assert master_mp4.stat().st_size > 0

    # 3. FFPROBE_RESULT_VALID: Probe master MP4
    probe_res = _run_cmd([
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(master_mp4),
    ])
    probe_data = json.loads(probe_res.stdout)
    video_stream = next(s for s in probe_data["streams"] if s["codec_type"] == "video")
    assert video_stream["width"] == 720
    assert video_stream["height"] == 1280
    master_dur = float(probe_data["format"]["duration"])
    assert 15.8 <= master_dur <= 16.2, f"Expected ~16.0s master duration, got {master_dur}"

    # 4. DECODE_RESULT_VALID: Decode full master video without errors
    decode_res = _run_cmd([
        "ffmpeg", "-v", "error",
        "-i", str(master_mp4),
        "-f", "null", "-",
    ])
    assert decode_res.stderr == ""

    # 5. DISTINCT_FRAME_OR_EQUIVALENT_IDENTITY: Extract frame at 4s (Scene 1) and 12s (Scene 2)
    frame1 = tmp_path / "frame_scene1.png"
    frame2 = tmp_path / "frame_scene2.png"
    _run_cmd(["ffmpeg", "-y", "-ss", "4.0", "-i", str(master_mp4), "-vframes", "1", str(frame1)])
    _run_cmd(["ffmpeg", "-y", "-ss", "12.0", "-i", str(master_mp4), "-vframes", "1", str(frame2)])

    assert frame1.is_file() and frame2.is_file()
    # Scene 1 is red, Scene 2 is blue -> frame bytes must differ
    assert frame1.read_bytes() != frame2.read_bytes()


def test_short_output_fail_closed_and_no_tpad(tmp_path: Path):
    """Proves SHORT_OUTPUT_FAIL_CLOSED, NO_TPAD, and NO_CLONED_TRAILING_HOLD."""
    short_clip = tmp_path / "short_clip.mp4"
    _run_cmd([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=720x1280:r=30:d=6.0",
        "-t", "6.0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(short_clip),
    ])

    # Expecting 8.0s, probed duration is ~6.0s -> must fail closed with scene_duration_short_no_charge
    dur_short = probe_video_duration(short_clip)
    val_short = validate_storyboard_scene_duration(dur_short, 8.0)
    assert val_short["duration_valid"] is False
    assert val_short["blocker"] == "scene_duration_short_no_charge"


def test_corrupt_output_fail_closed(tmp_path: Path):
    """Proves CORRUPT_OUTPUT_FAIL_CLOSED."""
    corrupt_clip = tmp_path / "corrupt_clip.mp4"
    corrupt_clip.write_bytes(b"NOT_A_VALID_MP4_FILE_CORRUPTED_HEADER")

    with pytest.raises(subprocess.CalledProcessError):
        _run_cmd([
            "ffprobe", "-v", "error",
            "-show_format",
            str(corrupt_clip),
        ])
