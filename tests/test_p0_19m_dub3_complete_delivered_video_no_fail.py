import bot


def test_dub3_dub_only_not_ok_with_delivered_video_completes():
    result = {
        "ok": False,
        "has_video": True,
        "video_delivery_message_id": "456",
        "status": "VIDEO_RENDER_FAILED",
    }

    assert bot.subdub_dub_only_result_should_complete_after_delivery(bot.VIDEO_SUBTITLE_MODE_DUB, result)


def test_dub3_does_not_touch_subtitle_only_or_combo():
    result = {
        "ok": False,
        "has_video": True,
        "video_delivery_message_id": "456",
    }

    assert not bot.subdub_dub_only_result_should_complete_after_delivery(bot.VIDEO_SUBTITLE_MODE_TRANSLATE, result)
    assert not bot.subdub_dub_only_result_should_complete_after_delivery(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB, result)


def test_dub3_dub_only_without_video_still_fails_clean():
    result = {
        "ok": False,
        "status": "VIDEO_RENDER_FAILED",
    }

    assert not bot.subdub_dub_only_result_should_complete_after_delivery(bot.VIDEO_SUBTITLE_MODE_DUB, result)
