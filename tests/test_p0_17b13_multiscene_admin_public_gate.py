import asyncio
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import bot
from services import multiscene_video_pipeline as mvp


def _ffmpeg():
    return os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg")


def _make_clip(path: Path, duration: float = 0.5) -> str:
    ffmpeg = _ffmpeg()
    assert ffmpeg
    result = mvp.safe_run_ffmpeg(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x1E88E5:s=320x568:r=30:d={duration:.3f}",
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


def _renderer(duration=0.5):
    def render(_scene, output_path):
        return _make_clip(Path(output_path), duration=duration)

    return render


async def _fake_sender(_bot_client, _chat_id, _job, result):
    return {"sent": bool(result.get("final_video_path")), "output_file_id": "final-file-id"}


def test_blackbox_smoke_public_user_locked_even_if_flags_ready(monkeypatch):
    calls = {"render": 0}

    def forbidden(_scene, _output_path):
        calls["render"] += 1
        raise AssertionError("public user must not render multiscene")

    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "video_multiscene_public_ready", lambda _count: True)
    result = asyncio.run(
        bot.run_multiscene_blackbox_job(
            {"user_id": 2002, "chat_id": 2002, "scene_count": 3, "scene_duration": 6, "fake_renderer": True},
            wait_for_completion=True,
            render_video_func=forbidden,
            sender=_fake_sender,
        )
    )
    assert result["status"] == "PUBLIC_GUARDED"
    assert "chưa xử lý" in result["message"]
    assert "chưa trừ Xu" in result["message"]
    assert calls["render"] == 0


def test_admin_multiscene_blackbox_runs_and_sends_final_only(monkeypatch, tmp_path):
    monkeypatch.setenv("MULTISCENE_VIDEO_TEMP_ROOT", str(tmp_path))
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    saved = []
    monkeypatch.setattr(bot, "save_multiscene_job_record", lambda job: saved.append(dict(job)) or job)
    result = asyncio.run(
        bot.run_multiscene_blackbox_job(
            {
                "user_id": 1,
                "chat_id": 1,
                "scene_count": 3,
                "scene_duration": 1,
                "fake_renderer": True,
                "admin_test": True,
                "bot_client": SimpleNamespace(),
                "cleanup": False,
            },
            wait_for_completion=True,
            render_video_func=_renderer(1),
            sender=_fake_sender,
        )
    )
    assert result["status"] == "SENT"
    assert result["result_sent"] is True
    final_path = result["final_output"]
    assert Path(final_path).is_file()
    assert 2.7 <= mvp.probe_duration(final_path) <= 3.6
    assert any(job.get("status") == "PENDING" for job in saved)
    assert not any(str(job.get("status")) == "SCENE_SENT" for job in saved)


def test_multiscene_long_video_guard_for_user_and_admin(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    result = asyncio.run(
        bot.run_multiscene_blackbox_job(
            {"user_id": 1, "scene_count": 4, "scene_duration": 6, "fake_renderer": True, "admin_test": True},
            wait_for_completion=True,
            render_video_func=_renderer(0.2),
            sender=_fake_sender,
        )
    )
    assert result["status"] == "LONG_VIDEO_GUARDED"
    assert "Phim AI nhiều cảnh" in result["message"]
    assert "chưa trừ Xu" in result["message"]


def test_video_multiscene_public_ready_follows_existing_runtime_flags(monkeypatch):
    monkeypatch.setattr(bot, "video_multiscene_public_enabled", lambda: True)
    monkeypatch.setattr(bot, "video_multiscene_stitching_ready", lambda: True)
    monkeypatch.setattr(bot, "video_multiscene_scene_tested", lambda _count: True)
    assert bot.video_multiscene_public_ready(1) is True
    assert bot.video_multiscene_public_ready(3) is True


def test_long_multiscene_film_public_guard_is_product_specific():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert 'if action == "b14_confirm":' in source
    assert "video_b14_public_render_guard(uid)" in source
    assert "MULTISCENE_LONG_VIDEO_GUARD_TEXT" in source
    assert "return bool(video_multiscene_public_enabled() and video_multiscene_stitching_ready() and video_multiscene_scene_tested(count))" in source


def test_multiscene_blackbox_admin_command_registered():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    assert 'CommandHandler("tool_test_multiscene_blackbox", cmd_tool_test_multiscene_blackbox)' in source
