from __future__ import annotations

import subprocess
from pathlib import Path

from services import multiscene_video_pipeline as pipeline
from services import video_real_render_connector as connector


def _capture_normalize(monkeypatch, tmp_path: Path, *, frame_fit_mode: str = "") -> str:
    captured: dict[str, list[str]] = {}
    source = tmp_path / "landscape-source.mp4"
    source.write_bytes(b"landscape")

    def fake_run(command, timeout):
        del timeout
        captured["command"] = list(command)
        Path(command[-1]).write_bytes(b"vertical-output")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(pipeline, "_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(pipeline, "probe_duration", lambda _path: 8.0)
    monkeypatch.setattr(pipeline, "safe_run_ffmpeg", fake_run)
    kwargs = {
        "target_width": 540,
        "target_height": 960,
    }
    if frame_fit_mode:
        kwargs["frame_fit_mode"] = frame_fit_mode
    pipeline.normalize_scene_duration(
        str(source),
        str(tmp_path / f"normalized-{frame_fit_mode or 'default'}.mp4"),
        8,
        **kwargs,
    )
    command = captured["command"]
    return command[command.index("-vf") + 1]


def test_product_video_vertical_cover_crops_instead_of_black_padding(monkeypatch, tmp_path) -> None:
    filters = _capture_normalize(
        monkeypatch,
        tmp_path,
        frame_fit_mode="cover",
    )

    assert "scale=540:960:force_original_aspect_ratio=increase" in filters
    assert "crop=540:960:(iw-ow)/2:(ih-oh)/2" in filters
    assert "pad=" not in filters


def test_shared_normalizer_default_remains_contain_for_locked_non_product_lanes(monkeypatch, tmp_path) -> None:
    filters = _capture_normalize(monkeypatch, tmp_path)

    assert "scale=540:960:force_original_aspect_ratio=decrease" in filters
    assert "pad=540:960:(ow-iw)/2:(oh-ih)/2:color=black" in filters
    assert "crop=" not in filters


def test_product_video_connector_selects_cover_mode_only_at_its_boundary() -> None:
    kwargs = connector._product_video_addon_render_kwargs({}, {"strict": False})

    assert kwargs["frame_fit_mode"] == "cover"
