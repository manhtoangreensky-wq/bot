import inspect
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from services import multiscene_video_pipeline as mvp


def _ffmpeg():
    return os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg")


def _make_clip(path: Path, duration: float = 1.0, color: str = "0x1E88E5") -> str:
    ffmpeg = _ffmpeg()
    assert ffmpeg, "ffmpeg is required for B13 multiscene blackbox tests"
    result = mvp.safe_run_ffmpeg(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=320x568:r=30:d={duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    return mvp.ensure_video_output(str(path))


def _renderer(duration: float = 6.0):
    colors = ["0x1E88E5", "0x43A047", "0xF4511E"]

    def render(scene, output_path):
        return _make_clip(Path(output_path), duration=duration, color=colors[(scene.scene_id - 1) % len(colors)])

    return render


def test_plan_multiscene_video_fallback_3_scenes():
    scenes = mvp.plan_multiscene_video(
        "Hook the user. Show the benefit. End with the brand.",
        max_scenes=3,
        default_scene_duration=6,
        aspect_ratio="9:16",
    )
    assert [scene.scene_id for scene in scenes] == [1, 2, 3]
    assert all(scene.video_prompt for scene in scenes)
    assert all(scene.target_duration_sec == 6 for scene in scenes)


def test_create_workspace_safe_path(monkeypatch, tmp_path):
    monkeypatch.setenv("MULTISCENE_VIDEO_TEMP_ROOT", str(tmp_path))
    workspace = mvp.create_multiscene_workspace("../unsafe job")
    assert Path(workspace).is_dir()
    assert str(Path(workspace).resolve()).startswith(str(tmp_path.resolve()))


def test_process_multiscene_pipeline_no_telegram_imports():
    source = inspect.getsource(mvp)
    assert "from telegram" not in source.lower()
    assert "import telegram" not in source.lower()
    assert "Update" not in source
    assert "ContextTypes" not in source


def test_render_scene_retries_failed_scene_only(monkeypatch, tmp_path):
    monkeypatch.setenv("MULTISCENE_VIDEO_TEMP_ROOT", str(tmp_path))
    workspace = mvp.create_multiscene_workspace("retry")
    scene = mvp.SceneSpec(scene_id=1, title="A", visual_prompt="A", video_prompt="A")
    calls = {"count": 0}

    def flaky(_scene, output_path):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary")
        return _make_clip(Path(output_path), duration=1)

    result = mvp.render_scene(scene, workspace_dir=workspace, render_video_func=flaky, retry=1)
    assert result.ok is True
    assert result.retry_count == 1
    assert calls["count"] == 2
    assert Path(result.raw_video_path).is_file()


def test_normalize_scene_duration_trims_and_extends(monkeypatch, tmp_path):
    monkeypatch.setenv("MULTISCENE_VIDEO_TEMP_ROOT", str(tmp_path))
    long_clip = _make_clip(tmp_path / "long.mp4", duration=8)
    short_clip = _make_clip(tmp_path / "short.mp4", duration=2)
    trimmed = mvp.normalize_scene_duration(long_clip, str(tmp_path / "trimmed.mp4"), 6)
    extended = mvp.normalize_scene_duration(short_clip, str(tmp_path / "extended.mp4"), 6)
    assert 5.7 <= mvp.probe_duration(trimmed) <= 6.4
    assert 5.7 <= mvp.probe_duration(extended) <= 6.4


def test_normalize_scene_duration_relies_on_ffmpeg_default_autorotation(
    monkeypatch, tmp_path
):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    captured = {}

    def fake_run(command, timeout):
        captured["command"] = list(command)
        Path(command[-1]).write_bytes(b"normalized")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(mvp, "_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(mvp, "probe_duration", lambda _path: 8.0)
    monkeypatch.setattr(mvp, "safe_run_ffmpeg", fake_run)

    mvp.normalize_scene_duration(
        str(source),
        str(tmp_path / "normalized.mp4"),
        8,
        target_width=540,
        target_height=960,
    )

    assert "-autorotate" not in captured["command"]


def test_stitch_scenes_concat_outputs_mp4(tmp_path):
    clips = [_make_clip(tmp_path / f"scene_{idx}.mp4", duration=1, color=color) for idx, color in enumerate(["0x1E88E5", "0x43A047", "0xF4511E"], start=1)]
    output = mvp.stitch_scenes(clips, str(tmp_path / "stitched.mp4"))
    assert Path(output).is_file()
    assert mvp.probe_duration(output) >= 2.8


def test_build_scene_subtitle_timestamps(tmp_path):
    scenes = [
        mvp.SceneSpec(scene_id=1, title="One", visual_prompt="A", video_prompt="A", narration_text="Line one"),
        mvp.SceneSpec(scene_id=2, title="Two", visual_prompt="B", video_prompt="B", narration_text="Line two"),
    ]
    path = mvp.build_scene_subtitle(scenes, [6, 6], str(tmp_path / "out.srt"))
    text = Path(path).read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:06,000" in text
    assert "00:00:06,000 --> 00:00:12,000" in text


def test_process_multiscene_pipeline_3_scenes_final_mp4(monkeypatch, tmp_path):
    monkeypatch.setenv("MULTISCENE_VIDEO_TEMP_ROOT", str(tmp_path))
    workspace = mvp.create_multiscene_workspace("pipeline")
    result = mvp.process_multiscene_video_pipeline(
        user_id="u1",
        job_id="pipeline",
        user_prompt="Open. Benefit. Finish.",
        workspace_dir=workspace,
        render_video_func=_renderer(6),
        max_scenes=3,
        aspect_ratio="9:16",
        enable_voice=False,
        enable_subtitle=True,
    )
    assert result["ok"] is True
    assert result["scene_count"] == 3
    assert Path(result["final_video_path"]).is_file()
    assert 17.0 <= mvp.probe_duration(result["final_video_path"]) <= 19.5
    assert Path(result["manifest_path"]).is_file()
    assert all("scene_" not in Path(path).name or Path(path).is_file() for path in result["created_files"])


def test_cleanup_multiscene_workspace_safe(monkeypatch, tmp_path):
    monkeypatch.setenv("MULTISCENE_VIDEO_TEMP_ROOT", str(tmp_path))
    workspace = mvp.create_multiscene_workspace("cleanup")
    Path(workspace, "file.txt").write_text("x", encoding="utf-8")
    mvp.cleanup_multiscene_workspace(workspace)
    assert not Path(workspace).exists()
    with pytest.raises(ValueError):
        mvp.cleanup_multiscene_workspace(str(tmp_path.parent))


def test_smoke_script_requires_fake_renderer_no_charge():
    script = Path("tools/smoke_multiscene_blackbox.py")
    result = subprocess.run([sys.executable, str(script), "--scenes", "3", "--duration", "6"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 2
    assert "--no-charge" in result.stdout or "fake renderer" in result.stdout
