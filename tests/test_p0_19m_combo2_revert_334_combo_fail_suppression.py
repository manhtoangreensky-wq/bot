import bot


def test_combo2_suppresses_active_combo_public_failure():
    job = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "mapped_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "status": "running",
        "progress_stage": "muxing_subtitle_dub_video",
        "lifecycle_state": "muxing_subtitle_dub_video",
        "progress_percent": 65,
        "in_progress": True,
    }
    result = {"ok": False, "status": "VIDEO_RENDER_PENDING"}

    assert bot.subtitle_plus_dub_should_suppress_public_failure(result, job) is True


def test_combo2_suppresses_combo_failure_after_video_delivered():
    job = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "terminal_state": "delivered",
        "final_mp4_delivered": True,
        "video_delivery_message_id": "99",
    }
    result = {"ok": False, "status": "late_error"}

    assert bot.subtitle_plus_dub_should_suppress_public_failure(result, job) is True


def test_combo2_does_not_suppress_real_early_combo_failure():
    job = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "status": "failed",
        "terminal_state": "failed_no_charge",
        "progress_percent": 5,
    }
    result = {"ok": False, "status": "INPUT_SAVE_FAILED"}

    assert bot.subtitle_plus_dub_should_suppress_public_failure(result, job) is False


def test_combo2_does_not_apply_to_dub_only_or_subtitle_only():
    active = {
        "status": "running",
        "progress_stage": "muxing_video",
        "progress_percent": 65,
        "in_progress": True,
    }

    assert bot.subtitle_plus_dub_should_suppress_public_failure(
        {"ok": False},
        {**active, "mode": bot.VIDEO_SUBTITLE_MODE_DUB},
    ) is False
    assert bot.subtitle_plus_dub_should_suppress_public_failure(
        {"ok": False},
        {**active, "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE},
    ) is False
