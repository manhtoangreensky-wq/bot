from pathlib import Path


BOT_PATH = Path(__file__).resolve().parents[1] / "bot.py"


def _bot_source() -> str:
    return BOT_PATH.read_text(encoding="utf-8")


def test_pr400_direct_runner_is_still_the_subdub_execution_path():
    source = _bot_source()

    assert "subdub_blackboxes.run_subdub_lane_blackbox(" in source
    assert "runner=subtitle_dub_product_pipeline.run_subdub_pipeline" in source


def test_status_refresh_reads_persisted_job_without_removed_recovery_layer():
    source = _bot_source()
    start = source.index("async def handle_product_progress_callback(")
    end = source.index("\n\nasync def", start + 1)
    callback = source[start:end]

    assert "subdub_progress_job_for_user(" in callback
    assert "subdub_persist_recovery_fields(" not in callback
    assert "subdub_recover_persisted_job(" not in callback
    assert "subdub_recover_persisted_jobs" not in source
    assert "subdub_recovery_watchdog_loop" not in source


def test_all_subdub_modes_reach_the_same_direct_lane_adapter():
    source = _bot_source()

    for mode in (
        "VIDEO_SUBTITLE_MODE_CREATE",
        "VIDEO_SUBTITLE_MODE_TRANSLATE",
        "VIDEO_SUBTITLE_MODE_DUB",
        "VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB",
    ):
        assert mode in source

    assert source.count("subdub_blackboxes.run_subdub_lane_blackbox(") == 1
