import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT = (ROOT / "bot.py").read_text(encoding="utf-8")

VIDEO_SUBTITLE_MODE_TRANSLATE = "VIDEO_SUBTITLE_MODE_TRANSLATE"
VIDEO_SUBTITLE_MODE_DUB = "VIDEO_SUBTITLE_MODE_DUB"
VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB = "VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB"


def function_source(name: str, *, async_def: bool = False) -> str:
    marker = f"{'async ' if async_def else ''}def {name}("
    start = BOT.find(marker)
    assert start >= 0, name
    next_def = BOT.find("\ndef ", start + 1)
    next_async = BOT.find("\nasync def ", start + 1)
    endings = [item for item in (next_def, next_async) if item >= 0]
    return BOT[start : min(endings) if endings else len(BOT)]


def test_m4live4_subtitle_only_uses_subtitle_lane_not_dub_lane():
    receipt = function_source("video_dubbing_receipt_text")
    assert 'VIDEO_SUBTITLE_MODE_TRANSLATE: "Video phụ đề dịch"' in receipt
    assert "subdub_final_video_failed_text(lang) if subdub_video_requires_final_mp4(mode)" in receipt
    assert "subdub_video_requires_final_mp4(mode)" in receipt


def test_m4live4_subtitle_only_restored_to_last_mp4_delivery_path():
    receipt = function_source("video_dubbing_receipt_text")
    delivery = function_source("send_public_subtitle_dub_final_outputs", async_def=True)
    assert "subdub_final_mp4_delivery_marker_present" not in BOT
    assert "video_delivery_message_id" in receipt
    assert 'sent["final_mp4_delivered"] = True' in delivery


def test_m4live4_subtitle_only_no_late_chua_dich_duoc_after_mp4():
    receipt = function_source("video_dubbing_receipt_text")
    assert "delivered_video = bool" in receipt
    assert "return subdub_mode_fail_text" in receipt


def test_m4live4_subtitle_only_sends_mp4():
    delivery = function_source("send_public_subtitle_dub_final_outputs", async_def=True)
    assert 'sent["final_mp4_delivered"] = True' in delivery
    assert 'sent["video"] = 1' in delivery
    assert 'sent["video_document"] = 1' in delivery


def test_m4live4_subtitle_only_does_not_touch_dub_lane():
    callback = function_source("handle_video_dubbing_callback", async_def=True)
    assert "mode=VIDEO_SUBTITLE_MODE_TRANSLATE" in callback
    assert "mode=VIDEO_SUBTITLE_MODE_DUB" in callback
    assert "mode=VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB" in callback


def test_m4live4_dub_only_restored_independent_lane():
    receipt = function_source("video_dubbing_receipt_text")
    assert 'VIDEO_SUBTITLE_MODE_DUB: "Video lồng tiếng"' in receipt
    assert 'VIDEO_SUBTITLE_MODE_DUB: "Lồng tiếng"' in receipt


def test_m4live4_dub_only_no_preview_then_failure():
    update = function_source("update_subtitle_dub_pipeline_job")
    assert "incoming_failure_after_mp4" not in update
    assert "recovered_failure_after_mp4" not in update
    assert "subdub_terminal_state_allows_transition" in update


def test_m4live4_dub_only_no_late_incomplete_video_after_mp4():
    receipt = function_source("video_dubbing_receipt_text")
    assert "delivered_video = bool" in receipt
    assert "terminal_delivered" in receipt


def test_m4live4_dub_only_sends_mp4_or_clean_pre_delivery_failure():
    delivery = function_source("send_public_subtitle_dub_final_outputs", async_def=True)
    assert "requires_final_mp4 and not sent.get(\"final_mp4_delivered\")" in delivery
    assert '"success_blocked_reason"] = "missing_valid_delivered_mp4"' in delivery
    assert 'sent["terminal_public_outcome_type"] = "failure"' in delivery


def test_m4live4_dub_only_does_not_touch_subtitle_lane():
    changed = _changed_paths_from_main()
    assert "services/subtitle_dub_product_pipeline.py" not in changed


def test_m4live4_subtitle_dub_restored_independent_lane():
    receipt = function_source("video_dubbing_receipt_text")
    assert 'VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB: "Video phụ đề + lồng tiếng"' in receipt
    assert 'VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB: "Phụ đề + lồng tiếng"' in receipt


def test_m4live4_subtitle_dub_no_false_file_too_large_after_mp4():
    callback = function_source("handle_video_dubbing_callback", async_def=True)
    large_file_branch = callback.find('large_telegram_download_unsupported')
    suppress_branch = callback.find("subdub_should_suppress_late_public_failure(latest_failure_job)")
    assert suppress_branch >= 0
    assert large_file_branch >= 0
    assert suppress_branch < large_file_branch


def test_m4live4_subtitle_dub_no_late_failure_after_mp4():
    update = function_source("update_subtitle_dub_pipeline_job")
    assert "incoming_failure_after_mp4" not in update
    assert "subdub_final_mp4_delivery_marker_present" not in update
    assert "persist_subtitle_dub_pipeline_job_snapshot" in update


def test_m4live4_subtitle_dub_uses_bottom_renderer():
    style = function_source("subdub_normalize_style")
    ass = function_source("subdub_generate_ass_from_srt")
    assert 'style["subtitle_margin_v_after"] = max(4, min(14' in style
    assert "margin_v = int(style.get(\"subtitle_margin_v_after\")" in ass


def test_m4live4_subtitle_dub_does_not_touch_subtitle_only_lane():
    changed = _changed_paths_from_main()
    assert changed <= {
        "bot.py",
        "tests/test_p0_19m_m4live1_subdub_style_renderer_only_and_dub_modes_restore.py",
        "tests/test_p0_19m_m4live4_subdub_mode_specific_restore.py",
        "tests/test_p0_19m_m4live5_subdub_full_runtime_rollback_to_3mp4_baseline.py",
    }


def test_m4live4_ass_alignment_bottom_center():
    ass = function_source("subdub_generate_ass_from_srt")
    assert "subdub_ass_alignment" in ass
    assert "Style: Default" in ass
    assert "f\"{alignment},{margin_l},{margin_r},{margin_v},1\"" in ass


def test_m4live4_ass_margin_v_zero_to_three():
    style = function_source("subdub_normalize_style")
    assert 'style["subtitle_margin_v_after"] = max(4, min(14' in style


def test_m4live4_no_high_pos_or_move_override():
    ass = function_source("subdub_generate_ass_from_srt")
    assert "\\pos" not in ass
    assert "\\move" not in ass
    assert "\\an" not in ass


def test_m4live4_vietnamese_box_covers_original_subtitle_band():
    style = function_source("subdub_normalize_style")
    cover = function_source("subdub_cover_filter")
    assert 'style["subtitle_alignment"] = "bottom_center"' in style
    assert 'style["boxed_background"]' in style
    assert "return \"\"" in cover


def test_m4live4_max_two_visible_lines():
    wrap = function_source("subdub_ass_wrap_text")
    chunks = function_source("subdub_ass_text_chunks")
    assert "limit = max(1, int(max_lines or 2))" in wrap
    assert "line_limit = max(1, min(2, int(max_lines or 2)))" in chunks


def test_m4live4_three_subdub_modes_have_separate_terminal_outcomes():
    receipt = function_source("video_dubbing_receipt_text")
    for mode in (VIDEO_SUBTITLE_MODE_TRANSLATE, VIDEO_SUBTITLE_MODE_DUB, VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB):
        assert mode in receipt


def test_m4live4_subtitle_only_failure_text_not_used_after_mp4():
    receipt = function_source("video_dubbing_receipt_text")
    assert "delivered_video = bool" in receipt
    assert "if delivered_video or terminal_delivered:" in receipt


def test_m4live4_dub_failure_text_not_used_after_mp4():
    receipt = function_source("video_dubbing_receipt_text")
    assert "delivered_video = bool" in receipt
    assert "return subdub_mode_fail_text" in receipt


def test_m4live4_combined_failure_text_not_used_after_mp4():
    update = function_source("update_subtitle_dub_pipeline_job")
    assert "incoming_failure_after_mp4" not in update
    assert "fields.pop(blocked_key, None)" not in update


def test_m4live4_no_broad_subdub_rollback_marker():
    assert "NO_SAFE_MODE_SPECIFIC_RESTORE" not in BOT
    assert "git revert" not in BOT
    assert "_execute_video_dubbing_pipeline_core" not in "\n".join(_changed_hunks())


def _changed_paths_from_main() -> set[str]:
    output = subprocess.check_output(["git", "diff", "--name-only", "origin/main"], cwd=ROOT, text=True)
    return {line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}


def _changed_hunks() -> list[str]:
    output = subprocess.check_output(["git", "diff", "--unified=0", "origin/main", "--", "bot.py"], cwd=ROOT, text=True)
    return output.splitlines()


def test_m4live4_no_music_changes():
    changed = _changed_paths_from_main()
    assert not any("music" in path.lower() or "suno" in path.lower() for path in changed if not path.startswith("tests/"))


def test_m4live4_no_product_video_changes():
    changed = _changed_paths_from_main()
    forbidden = ("services/video_", "providers/video_", "remote_worker.py", "local_worker.py")
    assert not any(path.startswith(forbidden) for path in changed)


def test_m4live4_no_img2vid_changes():
    changed = _changed_paths_from_main()
    assert not any("img2vid" in path.lower() or "storyboard" in path.lower() for path in changed)


def test_m4live4_no_voice_standalone_changes():
    changed = _changed_paths_from_main()
    assert not any(path.startswith("providers/") and "voice" in path.lower() for path in changed)


def test_m4live4_no_payos_pricing_db_webhook_changes():
    changed = _changed_paths_from_main()
    forbidden = ("payos", "pricing", "finance", "migration", "webhook")
    assert not any(any(token in path.lower() for token in forbidden) for path in changed)


def test_m4live4_no_provider_paid_calls():
    changed = _changed_paths_from_main()
    assert not any(path.startswith("providers/") for path in changed)
