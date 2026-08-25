from pathlib import Path
import subprocess

from services import multiscene_video_pipeline as pipeline


def test_final_mux_allows_slow_vps_encode_beyond_five_minutes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    master = tmp_path / "master.mp4"
    voice = tmp_path / "voice.mp3"
    subtitle = tmp_path / "subtitle.ass"
    output = tmp_path / "final.mp4"
    for path in (master, voice, subtitle):
        path.write_bytes(b"fixture")

    captured: dict[str, int] = {}

    def fake_run(command: list[str], *, timeout: int = 180):
        captured["timeout"] = timeout
        Path(command[-1]).write_bytes(b"final-video")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(pipeline, "_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(pipeline, "probe_duration", lambda _path: 16.0)
    monkeypatch.setattr(pipeline, "safe_run_ffmpeg", fake_run)

    result = pipeline.mux_final_multiscene_video(
        master_video_path=str(master),
        output_path=str(output),
        voice_audio_path=str(voice),
        subtitle_path=str(subtitle),
        preserve_master_audio=True,
    )

    assert result == str(output)
    assert captured["timeout"] >= 600


def test_final_mux_caps_infinite_audio_padding_to_master_duration(
    monkeypatch,
    tmp_path: Path,
) -> None:
    master = tmp_path / "master.mp4"
    voice = tmp_path / "voice.mp3"
    subtitle = tmp_path / "subtitle.ass"
    output = tmp_path / "final.mp4"
    for path in (master, voice, subtitle):
        path.write_bytes(b"fixture")

    captured: dict[str, list[str]] = {}

    def fake_run(command: list[str], *, timeout: int = 180):
        del timeout
        captured["command"] = command
        Path(command[-1]).write_bytes(b"final-video")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(pipeline, "_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(pipeline, "probe_duration", lambda _path: 16.0)
    monkeypatch.setattr(pipeline, "safe_run_ffmpeg", fake_run)

    result = pipeline.mux_final_multiscene_video(
        master_video_path=str(master),
        output_path=str(output),
        voice_audio_path=str(voice),
        subtitle_path=str(subtitle),
        preserve_master_audio=True,
    )

    command = captured["command"]
    assert result == str(output)
    assert "apad[aout]" in " ".join(command)
    assert command[command.index("-t") + 1] == "16.000000"
