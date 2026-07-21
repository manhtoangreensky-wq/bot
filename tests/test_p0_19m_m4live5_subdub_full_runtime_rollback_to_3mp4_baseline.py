import hashlib
import re
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.skip(
    reason="Superseded by P0.19M.M4LIVE6: exact SubDub runtime restore baseline is M4LIVE2/526dfac3, not M4LIVE1/974d264."
)


ROOT = Path(__file__).resolve().parents[1]
BOT = (ROOT / "bot.py").read_text(encoding="utf-8")
ROLLBACK_SOURCE_SHA = "974d264dfc03ab0b051e0782fd99e1950da6ee55"
ROLLBACK_BOT = subprocess.check_output(
    ["git", "show", f"{ROLLBACK_SOURCE_SHA}:bot.py"],
    cwd=ROOT,
    text=True,
    encoding="utf-8",
    errors="replace",
)


def function_source(source: str, name: str, *, async_def: bool = False) -> str:
    marker = f"{'async ' if async_def else ''}def {name}("
    start = source.find(marker)
    assert start >= 0, name
    next_def = source.find("\ndef ", start + 1)
    next_async = source.find("\nasync def ", start + 1)
    endings = [item for item in (next_def, next_async) if item >= 0]
    return source[start : min(endings) if endings else len(source)]


def source_hash(text: str) -> str:
    return hashlib.sha1(text.strip().encode("utf-8")).hexdigest()


def changed_paths_from_main() -> set[str]:
    output = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], cwd=ROOT, text=True)
    return {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}


def changed_bot_diff() -> str:
    return subprocess.check_output(["git", "diff", "--unified=0", "origin/main", "--", "bot.py"], cwd=ROOT, text=True)


ROLLBACK_FUNCTIONS = {
    "video_dubbing_receipt_text": False,
    "subdub_job_video_delivery_succeeded": False,
    "update_subtitle_dub_pipeline_job": False,
    "subdub_normalize_style": False,
    "subdub_generate_ass_from_srt": False,
    "handle_video_dubbing_callback": True,
}


def test_m4live5_runtime_functions_restored_from_m4live1_baseline():
    for name, async_def in ROLLBACK_FUNCTIONS.items():
        current = function_source(BOT, name, async_def=async_def)
        baseline = function_source(ROLLBACK_BOT, name, async_def=async_def)
        assert source_hash(current) == source_hash(baseline), name


def test_m4live5_removed_m4live4_terminal_marker_patch():
    assert "def subdub_final_mp4_delivery_marker_present(" not in BOT
    assert "subdub_final_mp4_delivery_marker_present(" not in BOT


def test_m4live5_restores_subtitle_only_mp4_path_from_m4live1():
    receipt = function_source(BOT, "video_dubbing_receipt_text")
    delivery = function_source(BOT, "send_public_subtitle_dub_final_outputs", async_def=True)
    assert 'VIDEO_SUBTITLE_MODE_TRANSLATE: "Video phụ đề dịch"' in receipt
    assert "delivered_video = bool(result.get(\"video_delivered\")" in receipt
    assert "subdub_mode_fail_text(mode, lang)" in receipt
    assert 'sent["final_mp4_delivered"] = True' in delivery
    assert 'requires_final_mp4 and not sent.get("final_mp4_delivered")' in delivery


def test_m4live5_restores_dub_only_mp4_path_from_m4live1():
    receipt = function_source(BOT, "video_dubbing_receipt_text")
    callback = function_source(BOT, "handle_video_dubbing_callback", async_def=True)
    assert 'VIDEO_SUBTITLE_MODE_DUB: "Video lồng tiếng"' in receipt
    assert "mode=VIDEO_SUBTITLE_MODE_DUB" in callback
    assert "large_telegram_download_unsupported" in callback


def test_m4live5_restores_subtitle_dub_mp4_path_from_m4live1():
    receipt = function_source(BOT, "video_dubbing_receipt_text")
    callback = function_source(BOT, "handle_video_dubbing_callback", async_def=True)
    assert 'VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB: "Video phụ đề + lồng tiếng"' in receipt
    assert "mode=VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB" in callback
    assert "subdub_should_suppress_late_public_failure(latest_failure_job)" in callback


def test_m4live5_does_not_keep_current_srt_only_success_for_subtitle():
    delivery = function_source(BOT, "send_public_subtitle_dub_final_outputs", async_def=True)
    assert 'sent["srt_delivery_message_id"]' in delivery
    assert '"success_blocked_reason"] = "missing_valid_delivered_mp4"' in delivery
    assert 'sent["terminal_public_outcome_type"] = "failure"' in delivery


def test_m4live5_does_not_send_preview_then_failure_for_dub():
    receipt = function_source(BOT, "video_dubbing_receipt_text")
    update = function_source(BOT, "update_subtitle_dub_pipeline_job")
    assert "delivered_video" in receipt
    assert "subdub_terminal_state_allows_transition" in update
    assert "incoming_failure_after_mp4" not in update


def test_m4live5_no_ass_renderer_style_change():
    for name in ("subdub_normalize_style", "subdub_generate_ass_from_srt"):
        current = function_source(BOT, name)
        baseline = function_source(ROLLBACK_BOT, name)
        assert source_hash(current) == source_hash(baseline), name


def test_m4live5_no_new_subtitle_position_patch():
    diff = changed_bot_diff()
    assert "subtitle_margin_v_after" in diff
    assert "max(0, min(2" not in function_source(BOT, "subdub_normalize_style")


def test_m4live5_srt_attachment_does_not_replace_mp4():
    delivery = function_source(BOT, "send_public_subtitle_dub_final_outputs", async_def=True)
    assert 'sent["final_mp4_delivered"] = True' in delivery
    assert '"missing_valid_delivered_mp4"' in delivery


def test_m4live5_no_chua_dich_duoc_after_valid_mp4():
    receipt = function_source(BOT, "video_dubbing_receipt_text")
    baseline = function_source(ROLLBACK_BOT, "video_dubbing_receipt_text")
    assert source_hash(receipt) == source_hash(baseline)
    assert "delivered_video = bool" in receipt


def test_m4live5_screenshot_subtitle_srt_only_failure_regression():
    delivery = function_source(BOT, "send_public_subtitle_dub_final_outputs", async_def=True)
    assert 'if requires_final_mp4 and not sent.get("final_mp4_delivered")' in delivery
    assert "SRT" not in function_source(BOT, "video_dubbing_flow_failure_text")


def test_m4live5_screenshot_dub_preview_then_failure_regression():
    callback = function_source(BOT, "handle_video_dubbing_callback", async_def=True)
    assert "success_after_public_failure_video_message_id" in callback
    assert source_hash(callback) == source_hash(function_source(ROLLBACK_BOT, "handle_video_dubbing_callback", async_def=True))


def test_m4live5_does_not_touch_pipeline_core_or_provider_code():
    diff = changed_bot_diff()
    forbidden = (
        "_execute_video_dubbing_pipeline_core",
        "async def video_dubbing_tts_bytes",
        "async def video_dubbing_render_video",
        "run_subdub_pipeline",
        "subtitle_dub_product_pipeline.run_subdub_pipeline",
    )
    assert not any(item in diff for item in forbidden)


def test_m4live5_no_non_subdub_runtime_files_changed():
    changed = changed_paths_from_main()
    allowed = {
        "bot.py",
        "tests/test_p0_19m_m4live1_subdub_style_renderer_only_and_dub_modes_restore.py",
        "tests/test_p0_19m_m4live5_subdub_full_runtime_rollback_to_3mp4_baseline.py",
        "tests/test_p0_19m_m4live4_subdub_mode_specific_restore.py",
    }
    assert changed <= allowed


def test_m4live5_no_music_product_video_voice_payos_db_provider_changes():
    changed = changed_paths_from_main()
    forbidden_patterns = (
        "music",
        "suno",
        "services/video_",
        "providers/",
        "payos",
        "wallet",
        "payment",
        "pricing",
        "db",
        "webhook",
        "cskh",
    )
    non_test_changed = [path.lower() for path in changed if not path.startswith("tests/")]
    assert not any(any(pattern in path for pattern in forbidden_patterns) for path in non_test_changed)


def test_m4live5_no_provider_call_test_code():
    test_source = Path(__file__).read_text(encoding="utf-8")
    assert ("requests" + ".post") not in test_source
    assert ("httpx" + ".post") not in test_source
    assert ("provider" + "_submit") not in test_source
