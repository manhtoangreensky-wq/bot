import inspect
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import dubbing_pipeline as dp


def _write(path: Path, data: bytes = b"x") -> str:
    path.write_bytes(data)
    return str(path)


def test_mux_final_video_replaces_audio(monkeypatch, tmp_path):
    video = _write(tmp_path / "source.mp4", b"video")
    audio = _write(tmp_path / "audio.mp3", b"audio")
    output = tmp_path / "out.mp4"
    calls = []

    def fake_run(command, *, cwd):
        calls.append(command)
        Path(cwd, "final.mp4").write_bytes(b"mp4")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(dp, "_ffmpeg_binary", lambda: "ffmpeg")
    monkeypatch.setattr(dp, "_run_ffmpeg", fake_run)

    assert dp.mux_final_video(video, audio, str(output)) == str(output.resolve())
    assert output.read_bytes() == b"mp4"
    command = calls[0]
    assert ["-map", "0:v:0"] == command[command.index("-map"):command.index("-map") + 2]
    assert "1:a:0" in command
    assert command[command.index("-c:v") + 1] == "copy"
    assert command[command.index("-c:a") + 1] == "aac"


def test_mux_final_video_with_subtitle_burn(monkeypatch, tmp_path):
    video = _write(tmp_path / "source.mp4", b"video")
    audio = _write(tmp_path / "audio.mp3", b"audio")
    srt = _write(tmp_path / "sub.srt", b"1\n00:00:00,000 --> 00:00:01,000\nXin chao\n")
    output = tmp_path / "burned.mp4"
    calls = []

    def fake_run(command, *, cwd):
        calls.append(command)
        Path(cwd, "final.mp4").write_bytes(b"mp4")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(dp, "_ffmpeg_binary", lambda: "ffmpeg")
    monkeypatch.setattr(dp, "_run_ffmpeg", fake_run)

    dp.mux_final_video(video, audio, str(output), srt_path=srt, burn_subtitles=True)
    command = calls[0]
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-vf") + 1] == "subtitles=subtitle.srt"


def test_mux_final_video_missing_input_raises(tmp_path):
    audio = _write(tmp_path / "audio.mp3", b"audio")
    with pytest.raises(dp.DubbingPipelineError, match="video_missing_or_empty"):
        dp.mux_final_video(str(tmp_path / "missing.mp4"), audio, str(tmp_path / "out.mp4"))


def test_mux_final_video_validates_output(monkeypatch, tmp_path):
    video = _write(tmp_path / "source.mp4", b"video")
    audio = _write(tmp_path / "audio.mp3", b"audio")

    monkeypatch.setattr(dp, "_ffmpeg_binary", lambda: "ffmpeg")
    monkeypatch.setattr(dp, "_run_ffmpeg", lambda command, *, cwd: SimpleNamespace(returncode=0, stderr="", stdout=""))

    with pytest.raises(dp.DubbingPipelineError, match="mux_output_empty"):
        dp.mux_final_video(video, audio, str(tmp_path / "out.mp4"))


def test_process_dubbing_pipeline_returns_mp4_when_video_and_mux_success(monkeypatch, tmp_path):
    source_video = _write(tmp_path / "source.mp4", b"video")
    workspace = tmp_path / "workspace"
    seen = {}

    def fake_tts(segments, voice_id="", workspace_dir=""):
        seen["voice_id"] = voice_id
        seen["segments"] = segments
        return b"audio"

    def fake_mux(_video, _audio, output, **_kwargs):
        Path(output).write_bytes(b"mp4")
        return str(Path(output).resolve())

    monkeypatch.setattr(dp, "mux_final_video", fake_mux)

    result = dp.process_dubbing_pipeline(
        source_video_path=source_video,
        subtitle_segments=[{"start": 0, "end": 1, "text": "Xin chao"}],
        voice_id="voice-active",
        workspace_dir=str(workspace),
        tts_func=fake_tts,
    )

    assert result["ok"] is True
    assert result["result_type"] == "mp4"
    assert result["mux_attempted"] is True
    assert result["mux_ok"] is True
    assert Path(result["video_path"]).exists()
    assert seen["voice_id"] == "voice-active"


def test_process_dubbing_pipeline_audio_fallback_when_mux_fails(monkeypatch, tmp_path):
    source_video = _write(tmp_path / "source.mp4", b"video")

    def fake_tts(*_args, **_kwargs):
        return b"audio"

    def fail_mux(*_args, **_kwargs):
        raise dp.DubbingPipelineError("mux_failed")

    monkeypatch.setattr(dp, "mux_final_video", fail_mux)

    result = dp.process_dubbing_pipeline(
        source_video_path=source_video,
        subtitle_segments=[{"start": 0, "end": 1, "text": "Xin chao"}],
        voice_id="voice-active",
        workspace_dir=str(tmp_path / "workspace"),
        tts_func=fake_tts,
    )

    assert result["ok"] is True
    assert result["result_type"] == "audio_fallback"
    assert result["mux_attempted"] is True
    assert result["mux_ok"] is False
    assert Path(result["audio_path"]).exists()


def test_process_dubbing_pipeline_no_telegram_imports():
    source = inspect.getsource(dp).lower()
    assert "telegram" not in source
    assert "update" not in source
    assert "contexttypes" not in source


def test_cleanup_workspace_removes_only_workspace_files(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    inside = workspace / "temp.txt"
    outside = tmp_path / "keep.txt"
    inside.write_text("delete", encoding="utf-8")
    outside.write_text("keep", encoding="utf-8")

    dp.cleanup_workspace(str(workspace))

    assert not workspace.exists()
    assert outside.exists()
    assert outside.read_text(encoding="utf-8") == "keep"


def _voice_conn(with_table=True):
    conn = sqlite3.connect(":memory:")
    if with_table:
        conn.execute(
            """
            CREATE TABLE voice_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                provider_voice_id TEXT,
                is_default INTEGER,
                status TEXT
            )
            """
        )
    return conn


def test_get_user_voice_id_prefers_active_default_profile():
    conn = _voice_conn()
    conn.execute(
        "INSERT INTO voice_profiles (user_id, provider_voice_id, is_default, status) VALUES (?, ?, 1, 'active')",
        ("42", "minimax-user-voice"),
    )

    assert dp.get_user_voice_id("42", conn, default_voice_id="female-default") == "minimax-user-voice"


def test_get_user_voice_id_fallbacks_to_default():
    conn = _voice_conn()
    assert dp.get_user_voice_id("42", conn, default_voice_id="female-default") == "female-default"
    assert dp.get_user_voice_id("42", conn, requested_voice_id="default_female", default_voice_id="female-default") == "female-default"


def test_get_user_voice_id_handles_missing_table():
    conn = _voice_conn(with_table=False)
    assert dp.get_user_voice_id("42", conn, default_voice_id="female-default") == "female-default"


def test_get_user_voice_id_no_fake_profile():
    conn = _voice_conn()
    before = conn.execute("SELECT COUNT(1) FROM voice_profiles").fetchone()[0]
    assert dp.get_user_voice_id("42", conn, default_voice_id="female-default") == "female-default"
    after = conn.execute("SELECT COUNT(1) FROM voice_profiles").fetchone()[0]
    assert before == after == 0


def test_dubbing_pipeline_uses_user_voice_id(monkeypatch, tmp_path):
    conn = _voice_conn()
    conn.execute(
        "INSERT INTO voice_profiles (user_id, provider_voice_id, is_default, status) VALUES (?, ?, 1, 'active')",
        ("42", "minimax-user-voice"),
    )
    captured = {}

    def fake_tts(_segments, voice_id="", workspace_dir=""):
        captured["voice_id"] = voice_id
        return b"audio"

    voice_id = dp.get_user_voice_id("42", conn, default_voice_id="female-default")
    result = dp.process_dubbing_pipeline(
        source_video_path=None,
        subtitle_segments=[{"start": 0, "end": 1, "text": "Xin chao"}],
        voice_id=voice_id,
        workspace_dir=str(tmp_path / "workspace"),
        tts_func=fake_tts,
    )

    assert result["ok"] is True
    assert result["result_type"] == "audio_fallback"
    assert captured["voice_id"] == "minimax-user-voice"
