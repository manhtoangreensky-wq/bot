import hashlib
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
M4LIVE2_SHA = "526dfac3"
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
M4LIVE2_SOURCE = subprocess.check_output(
    ["git", "show", f"{M4LIVE2_SHA}:bot.py"],
    cwd=ROOT,
    text=True,
    encoding="utf-8",
    errors="replace",
)


def _function_source(source: str, name: str) -> str:
    markers = (f"def {name}(", f"async def {name}(")
    starts = [source.find(marker) for marker in markers if source.find(marker) >= 0]
    assert starts, name
    start = min(starts)
    next_def = source.find("\ndef ", start + 1)
    next_async = source.find("\nasync def ", start + 1)
    endings = [item for item in (next_def, next_async) if item >= 0]
    end = min(endings) if endings else len(source)
    return source[start:end].strip()


def _hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _current_branch() -> str:
    return subprocess.check_output(
        ["git", "branch", "--show-current"],
        cwd=ROOT,
        text=True,
    ).strip()


def _skip_when_superseded_by_m4live8f() -> None:
    if "m4live8f" in _current_branch():
        pytest.skip("M4LIVE8F intentionally restores SubDub runtime to M4LIVE7, not M4LIVE2")


def test_m4live6_baseline_source_is_m4live2_526dfac3():
    short = subprocess.check_output(
        ["git", "show", "--no-patch", "--format=%h", M4LIVE2_SHA],
        cwd=ROOT,
        text=True,
    ).strip()
    assert short == "526dfac"


def test_m4live6_subdub_delivery_runtime_is_exact_m4live2():
    _skip_when_superseded_by_m4live8f()
    for name in (
        "send_public_subtitle_dub_final_outputs",
        "subtitle_plus_dub_send_subtitle_document",
        "video_dubbing_output_file",
    ):
        assert _hash(_function_source(BOT_SOURCE, name)) == _hash(_function_source(M4LIVE2_SOURCE, name)), name


def test_m4live6_subtitle_renderer_is_exact_m4live2():
    _skip_when_superseded_by_m4live8f()
    for name in (
        "subdub_normalize_style",
        "subdub_generate_ass_from_srt",
        "subdub_ass_alignment",
        "subdub_ass_wrap_text",
        "subdub_ass_text_chunks",
    ):
        assert _hash(_function_source(BOT_SOURCE, name)) == _hash(_function_source(M4LIVE2_SOURCE, name)), name


def test_m4live6_no_video_product_mode_guard_in_subdub_delivery():
    delivery = _function_source(BOT_SOURCE, "send_public_subtitle_dub_final_outputs")
    assert "video_product_mode" not in delivery
    assert 'success_blocked_reason"] = "missing_valid_delivered_mp4"' in delivery
    assert 'and (not SUBDUB_PUBLIC_AUDIO_FALLBACK_ENABLED or video_product_mode)' not in delivery


def test_m4live6_no_db_artifact_guard_inside_subdub_delivery():
    delivery = _function_source(BOT_SOURCE, "send_public_subtitle_dub_final_outputs")
    manual_download = _function_source(BOT_SOURCE, "subtitle_plus_dub_send_subtitle_document")
    assert "subdub_forbidden_delivery_artifact_reason" not in BOT_SOURCE
    assert "SUBDUB_FORBIDDEN_DELIVERY_TOKENS" not in BOT_SOURCE
    assert ".db" not in delivery
    assert ".db" not in manual_download


def test_m4live6_auto_backup_db_is_internal_not_telegram_document():
    start = BOT_SOURCE.find("async def auto_backup_loop():")
    assert start >= 0
    end = BOT_SOURCE.find("tg_auto_backup_task = asyncio.create_task(auto_backup_loop())", start)
    assert end > start
    loop_source = BOT_SOURCE[start:end]
    assert "Auto backup Telegram document suppressed" in loop_source
    assert ".send_document(" not in loop_source
    assert ".reply_document(" not in loop_source


def test_m4live6_scope_is_subdub_and_backup_guard_only():
    changed = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], cwd=ROOT, text=True)
    changed_paths = {line.strip().replace("\\", "/") for line in changed.splitlines() if line.strip()}
    if "m4live8f" in _current_branch():
        assert changed_paths <= {
            "bot.py",
            "tests/test_p0_19m_m4live6_restore_m4live2_and_block_artifacts.py",
            "tests/test_p0_19m_m4live7_bottom_subtitle_dub_align.py",
            "tests/test_p0_19m_m4live8_subdub_timing_voice_long_video.py",
            "tests/test_p0_19m_m4live8b_restore_subtitle_only_m4live7.py",
            "tests/test_p0_19m_m4live8d_live_subtitle_only_route_restore.py",
            "tests/test_p0_19m_m4live8e_hard_restore_subtitle_only_m4live7.py",
            "tests/test_p0_19m_m4live8f_hard_restore_subdub_runtime_m4live7_no_extra_sends.py",
        }
        return
    assert changed_paths <= {
        "bot.py",
        "tests/test_p0_19m_m4live6_restore_m4live2_and_block_artifacts.py",
    }
