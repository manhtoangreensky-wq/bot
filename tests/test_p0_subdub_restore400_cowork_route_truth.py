"""P0.SUBDUB.RESTORE400 (COWORK) — four-lane route truth.

Covers: readiness gate truth at explicit interactive confirm, clean public
guard copy (no internal diagnostics, no factory/cURL buttons), blocker→copy
mapping truth, and the two 11-second Chinese fixtures (A soft-sub /
B hardsub-only) generated at test time by tests/fixtures.
"""

import asyncio
import inspect
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import bot

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))
from generate_subdub_restore400_fixtures import generate_fixture  # noqa: E402

ALL_LANES = (
    bot.VIDEO_SUBTITLE_MODE_CREATE,
    bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    bot.VIDEO_SUBTITLE_MODE_DUB,
    bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
)

FFMPEG_AVAILABLE = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _lane_state(mode):
    return {
        "mode": mode,
        "process_type": mode,
        "video_processing_mode": mode,
        "source_mime_type": "video/mp4",
        "source_file_name": "fixture.mp4",
        "target_language": "vi",
        "translate_requested": "1" if mode != bot.VIDEO_SUBTITLE_MODE_CREATE else "0",
    }


def _patch_ready_runtime(monkeypatch):
    monkeypatch.setattr(bot, "APP_BUILD_SHA", "restore400-runtime-sha")
    monkeypatch.setattr(bot, "PROVIDER_FREEZE", False)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE_ENABLED", False)
    monkeypatch.setattr(bot, "TRANSLATION_DUB_MAINTENANCE", False)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_TRANSLATE_SUBTITLE_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_DUB_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PLUS_DUB_PUBLIC_ENABLED", True)
    monkeypatch.setattr(bot, "ASR_PROVIDER", "deepgram")
    monkeypatch.setattr(bot, "TRANSLATE_PROVIDER", "deepl")
    monkeypatch.setattr(bot, "TTS_PROVIDER", "direct_minimax")
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "configured")
    monkeypatch.setattr(bot, "DEEPL_API_KEY", "configured")
    monkeypatch.setattr(bot, "MINIMAX_API_KEY", "configured")
    monkeypatch.setattr(bot, "MINIMAX_GROUP_ID", "configured")
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", True)
    monkeypatch.setattr(bot, "VIDEO_DUB_TTS_ENABLED", True)
    monkeypatch.setattr(
        bot,
        "subdub_runtime_status_payload",
        lambda: {
            "media_preprocessing_ready": True,
            "subtitle_rendering_ready": True,
            "ffmpeg_ready": True,
            "ffprobe_ready": True,
        },
    )
    smoke = {
        "asr:deepgram": {"status": "PASS", "tested_at": "now", "detail": "runtime_sha=restore400-runtime-sha"},
        "translation:deepl": {"status": "PASS", "tested_at": "now", "detail": "runtime_sha=restore400-runtime-sha"},
        "tts:direct_minimax": {"status": "PASS", "tested_at": "now", "detail": "runtime_sha=restore400-runtime-sha"},
    }
    monkeypatch.setattr(
        bot,
        "get_tool_test_result",
        lambda name: dict(smoke.get(name) or {"status": "NOT_TESTED", "tested_at": "", "detail": ""}),
    )
    return smoke


NOT_TESTED = {"status": "NOT_TESTED", "tested_at": "", "detail": ""}


def test_interactive_confirm_context_clears_freeze_and_smoke_blockers(monkeypatch):
    smoke = _patch_ready_runtime(monkeypatch)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE", True)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE_ENABLED", True)
    smoke["asr:deepgram"] = dict(NOT_TESTED)
    smoke["translation:deepl"] = dict(NOT_TESTED)
    smoke["tts:direct_minimax"] = dict(NOT_TESTED)
    for mode in ALL_LANES:
        readiness = bot.get_subdub_lane_readiness(
            mode, _lane_state(mode), public=False, admin_interactive_confirm=True
        )
        assert readiness["effective_ready"] is True, (mode, readiness["blockers"])


def test_interactive_confirm_context_cannot_bypass_real_configuration(monkeypatch):
    _patch_ready_runtime(monkeypatch)
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "")
    readiness = bot.get_subdub_lane_readiness(
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        _lane_state(bot.VIDEO_SUBTITLE_MODE_CREATE),
        public=False,
        admin_interactive_confirm=True,
    )
    assert readiness["effective_ready"] is False
    assert "asr_not_configured" in readiness["blockers"]


def test_public_readiness_ignores_interactive_confirm_context(monkeypatch):
    _patch_ready_runtime(monkeypatch)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE", True)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE_ENABLED", True)
    for name in (
        "VIDEO_SUBTITLE_PUBLIC_ENABLED",
        "VIDEO_TRANSLATE_SUBTITLE_PUBLIC_ENABLED",
        "VIDEO_DUB_PUBLIC_ENABLED",
        "VIDEO_SUBTITLE_PLUS_DUB_PUBLIC_ENABLED",
    ):
        monkeypatch.setattr(bot, name, False)
    for mode in ALL_LANES:
        readiness = bot.get_subdub_lane_readiness(
            mode, _lane_state(mode), public=True, admin_interactive_confirm=True
        )
        assert readiness["effective_ready"] is False
        assert "public_flag_off" in readiness["blockers"]
        assert "provider_freeze" in readiness["blockers"]


def test_confirm_handler_wires_interactive_confirm_context():
    source = inspect.getsource(bot.handle_video_dubbing_callback)
    assert "admin_interactive_confirm=bool(is_admin_user(uid))" in source


def test_no_blocker_confirm_path_reaches_engine_execution():
    source = inspect.getsource(bot.handle_video_dubbing_callback)
    gate_index = source.index('confirm_readiness.get("effective_ready")')
    engine_index = source.index("execute_engine(", gate_index)
    assert engine_index > gate_index


def test_guard_text_never_exposes_internal_diagnostics(monkeypatch):
    smoke = _patch_ready_runtime(monkeypatch)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE", True)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE_ENABLED", True)
    smoke["asr:deepgram"] = dict(NOT_TESTED)
    for mode in ALL_LANES:
        for admin in (False, True):
            text = bot.video_dubbing_guard_text(mode, _lane_state(mode), "vi", admin=admin)
            lowered = text.lower()
            for needle in (
                "admin blocker",
                "no static blocker",
                "factory",
                "curl",
                "smoke",
                "deepgram",
                "deepl",
                "minimax",
                "provider_freeze",
                "env",
            ):
                assert needle not in lowered, (mode, admin, needle, text)
            assert "chưa trừ Xu" in text


def test_guard_keyboard_contains_only_navigation_buttons():
    for admin in (False, True):
        markup = bot.video_dubbing_guard_keyboard("vi", admin=admin)
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        labels = " ".join(button.text for row in markup.inline_keyboard for button in row)
        assert callbacks == ["videodub|guard_back", "menu|main"], callbacks
        for needle in ("factory", "cURL", "Trạng thái dịch"):
            assert needle not in labels


def test_smoke_blocker_shows_lane_closed_copy_not_asr_capability_copy(monkeypatch):
    smoke = _patch_ready_runtime(monkeypatch)
    smoke["asr:deepgram"] = dict(NOT_TESTED)
    text = bot.video_dubbing_guard_text(
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        _lane_state(bot.VIDEO_SUBTITLE_MODE_CREATE),
        "vi",
        admin=False,
    )
    assert "tạm ngưng" in text
    assert "bóc lời" not in text
    assert "chưa trừ Xu" in text


def test_true_asr_not_configured_still_shows_asr_capability_copy(monkeypatch):
    _patch_ready_runtime(monkeypatch)
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "")
    text = bot.video_dubbing_guard_text(
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        _lane_state(bot.VIDEO_SUBTITLE_MODE_CREATE),
        "vi",
        admin=False,
    )
    assert "bóc lời" in text


def test_provider_freeze_blocker_shows_lane_closed_copy(monkeypatch):
    _patch_ready_runtime(monkeypatch)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE", True)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE_ENABLED", True)
    text = bot.video_dubbing_guard_text(
        bot.VIDEO_SUBTITLE_MODE_DUB,
        _lane_state(bot.VIDEO_SUBTITLE_MODE_DUB),
        "vi",
        admin=False,
    )
    assert "tạm ngưng" in text
    assert "giọng lồng tiếng" not in text


def _probe_streams(path: str) -> list[dict]:
    import json

    raw = subprocess.run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_streams", "-show_format", str(path),
        ],
        capture_output=True,
        check=True,
        timeout=120,
    ).stdout
    return json.loads(raw)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not on PATH")
def test_fixture_variant_a_softsub_properties(tmp_path):
    path = generate_fixture("a", str(tmp_path / "fixture_a.mp4"))
    probe = _probe_streams(path)
    codec_types = [stream.get("codec_type") for stream in probe["streams"]]
    assert "video" in codec_types
    assert "audio" in codec_types
    assert "subtitle" in codec_types
    duration = float(probe["format"]["duration"])
    assert abs(duration - 11.0) <= max(1.0, 11.0 * 0.02)
    video = next(s for s in probe["streams"] if s.get("codec_type") == "video")
    assert video.get("codec_name") == "h264"
    assert video.get("pix_fmt") == "yuv420p"
    assert int(probe["format"]["size"]) < 20 * 1024 * 1024


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not on PATH")
def test_fixture_variant_b_hardsub_has_no_extractable_subtitle_stream(tmp_path):
    path = generate_fixture("b", str(tmp_path / "fixture_b.mp4"))
    probe = _probe_streams(path)
    codec_types = [stream.get("codec_type") for stream in probe["streams"]]
    assert "video" in codec_types
    assert "audio" in codec_types
    assert "subtitle" not in codec_types
    duration = float(probe["format"]["duration"])
    assert abs(duration - 11.0) <= max(1.0, 11.0 * 0.02)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not on PATH")
def test_lane2_routing_precondition_soft_vs_hardsub(tmp_path):
    """Variant A must expose extractable subtitle text; variant B must not,
    which forces Lane 2 (translate) through the audio → ASR path."""
    path_a = generate_fixture("a", str(tmp_path / "route_a.mp4"))
    path_b = generate_fixture("b", str(tmp_path / "route_b.mp4"))
    text_a, _fmt_a = asyncio.run(
        bot.video_dubbing_extract_embedded_subtitle(Path(path_a).read_bytes())
    )
    text_b, _fmt_b = asyncio.run(
        bot.video_dubbing_extract_embedded_subtitle(Path(path_b).read_bytes())
    )
    assert "测试" in text_a or "你好" in text_a
    assert not str(text_b or "").strip()


def test_subdub_ffmpeg_base_reference_is_defined():
    """Regression: _SUBDUB_BASE_RUN_FFMPEG_COMMAND was referenced but never
    defined, so every SubDub ffmpeg call (audio extract, subtitle extract,
    burn, mux) crashed with NameError before this fix."""
    assert hasattr(bot, "_SUBDUB_BASE_RUN_FFMPEG_COMMAND")
    assert bot._SUBDUB_BASE_RUN_FFMPEG_COMMAND is not None


def test_run_subdub_ffmpeg_command_delegates_to_patched_seam(monkeypatch):
    calls = []

    async def fake_run(cmd, timeout=120.0):
        calls.append(list(cmd))
        return True, "ok"

    monkeypatch.setattr(bot, "run_ffmpeg_command", fake_run)
    ok, detail = asyncio.run(bot.run_subdub_ffmpeg_command(["ffmpeg", "-version"], timeout=5))
    assert ok is True
    assert detail == "ok"
    assert calls == [["ffmpeg", "-version"]]
