from pathlib import Path


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def test_combo_full_dub_restores_existing_status_panel_renderer():
    block = BOT_SOURCE.split('if action == "combo_full_dub":', 1)[1].split(
        'if action == "combo_redub_voice":', 1
    )[0]

    assert 'subdub_progress_text("received_file", "", lang)' in block
    assert 'subdub_progress_keyboard("", lang)' in block
    assert '"TOAN AAS đang tạo video phụ đề + lồng tiếng hoàn chỉnh..."' not in block


def test_combo_failure_never_reuses_delivered_job_from_another_video():
    block = BOT_SOURCE.split(
        "def subtitle_dub_find_latest_dub_job_for_user_mode", 1
    )[1].split("def subdub_job_public_status_text", 1)[0]

    assert "token[:160] in haystack" in block
    assert (
        "if source_tokens:\n"
        "        candidates = [item for item in candidates if _source_score(item)]"
    ) in block


def test_final_confirmed_raw_combo_uses_configured_asr_instead_of_stale_flag():
    block = BOT_SOURCE.split("def _product_engine_readiness", 1)[1].split(
        "def can_user_access_product_engine", 1
    )[0]
    guard = block.split("if (\n            admin_real_test", 1)[1].split(
        'technical_missing.append("asr_adapter_missing")', 1
    )[0]

    assert "and not video_dubbing_state_has_subtitle_or_transcript(state)" in guard
    assert "and not subdub_final_confirmed_state(state)" in guard
    assert guard.index("not subdub_final_confirmed_state") < guard.index(
        'not subdub_public_flag_with_override("VIDEO_ASR_ENABLED"'
    )
