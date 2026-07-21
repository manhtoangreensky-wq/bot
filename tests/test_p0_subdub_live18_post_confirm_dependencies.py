import bot


def test_live18_post_confirm_dependencies_are_defined():
    required = (
        "SUBDUB_MAX_INPUT_MB",
        "SUBDUB_LONG_PROJECT_MAX_PARTS",
        "SUBDUB_LONG_PROJECT_MAX_DURATION_SECONDS",
        "SUBDUB_VISUAL_OCR_ENABLED",
        "SUBDUB_SUBTITLE_SCRIPT_CHARSET",
        "subdub_input_limit_mb",
        "subdub_translation_cache_matches",
        "subdub_duration_validation_allows_success",
        "subdub_resume_generating_voice_from_checkpoint",
    )

    assert all(hasattr(bot, name) for name in required)


def test_live18_generic_message_id_is_not_video_delivery_proof():
    result = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "telegram_message_id": "unrelated-message",
        "delivery_success": True,
    }

    assert bot.subdub_video_delivery_message_id(result) == ""


def test_live18_real_video_message_id_restores_all_four_lanes():
    modes = (
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    )

    for mode in modes:
        restored = bot.subdub_restore_delivered_video_result(
            mode,
            {
                "mode": mode,
                "ok": False,
                "video_delivery_message_id": f"video-{mode}",
                "terminal_artifact_type": "video",
                "final_mp4_delivered": True,
                "duration_coverage_ok": True,
                "expected_duration": 30.0,
                "final_mp4_duration": 30.0,
            },
        )

        assert restored["ok"] is True
        assert restored["terminal_state"] == "delivered"
        assert restored["telegram_artifact_message_id"] == f"video-{mode}"
        assert restored["state"]["panel_final_percent"] == 100


def test_live18_short_video_cannot_be_restored_as_success():
    result = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "ok": False,
        "video_delivery_message_id": "video-short",
        "terminal_artifact_type": "video",
        "final_mp4_delivered": True,
        "duration_coverage_ok": False,
        "expected_duration": 30.0,
        "final_mp4_duration": 2.0,
    }

    restored = bot.subdub_restore_delivered_video_result(
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        result,
    )

    assert restored["ok"] is False
    assert restored.get("terminal_state") != "delivered"
