import asyncio
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = Path("bot.py").read_text(encoding="utf-8")


def _load_video_renderer():
    start = BOT_SOURCE.index("async def video_dubbing_render_video(")
    end = BOT_SOURCE.index("\nasync def build_subtitle_dubbed_video_pipeline(", start)
    timeouts = []

    async def probe(_payload):
        return {
            "duration": 97.729333,
            "has_audio": True,
            "width": 1280,
            "height": 720,
        }

    async def run_ffmpeg(command, timeout=120.0):
        timeouts.append(float(timeout))
        Path(command[-1]).write_bytes(b"validated-auto-mp4")
        return True, "ok"

    async def validate(_payload, **_kwargs):
        return {"ok": True, "detail": "valid", "duration": 124.752}

    namespace = {
        "asyncio": asyncio,
        "os": os,
        "tempfile": tempfile,
        "SimpleNamespace": SimpleNamespace,
        "frame_video_ffmpeg_path": lambda: "ffmpeg",
        "SUBDUB_VOLUME_MIX_UI_ENABLED": True,
        "SUBDUB_ORIGINAL_AUDIO_DEFAULT_VOLUME_PERCENT": 20,
        "SUBDUB_DUBBED_VOICE_DEFAULT_VOLUME_PERCENT": 100,
        "SUBDUB_STAGE_TIMEOUT_MAX_SECONDS": 7200,
        "subdub_probe_video_bytes": probe,
        "subdub_normalize_style": lambda state: {**dict(state or {}), "show_subtitles": False},
        "subdub_original_audio_volume": lambda *_args: 0.0,
        "subdub_percent_value": lambda value, default, *_args: float(default if value is None else value),
        "subdub_video_fit_filters": lambda _style: [],
        "subdub_media_preflight": SimpleNamespace(timeout_for_stage=lambda *_args, **_kwargs: 900),
        "run_subdub_ffmpeg_command": run_ffmpeg,
        "subdub_validate_video_output": validate,
        "sanitize_log_text": str,
    }
    exec(compile(BOT_SOURCE[start:end], "bot.py", "exec"), namespace)
    return namespace["video_dubbing_render_video"], timeouts


def test_auto_mux_can_use_isolated_thirty_minute_deadline():
    renderer, timeouts = _load_video_renderer()

    output, detail = asyncio.run(
        renderer(
            b"source-video",
            dubbed_audio=b"two-speaker-dub",
            subtitle_style={"show_subtitles": False},
            target_duration_seconds=124.752,
            require_audio=True,
            render_timeout_seconds=30 * 60,
        )
    )

    assert output == b"validated-auto-mp4"
    assert "ffmpeg_video_render_basic" in detail
    assert timeouts == [1800.0]


def test_default_mux_keeps_existing_deadline():
    renderer, timeouts = _load_video_renderer()

    output, _detail = asyncio.run(
        renderer(
            b"source-video",
            dubbed_audio=b"default-dub",
            subtitle_style={"show_subtitles": False},
            target_duration_seconds=124.752,
            require_audio=True,
        )
    )

    assert output == b"validated-auto-mp4"
    assert timeouts == [900.0]


def test_auto_mux_deadline_is_wired_only_from_auto_speaker_route():
    assert "SUBDUB_AUTO_RENDER_TIMEOUT_SECONDS = 30 * 60" in BOT_SOURCE
    assert (
        "if subdub_auto_speaker_route_enabled(state):\n"
        "            kwargs.setdefault(\"render_timeout_seconds\", SUBDUB_AUTO_RENDER_TIMEOUT_SECONDS)"
    ) in BOT_SOURCE
