import inspect

import bot


def _style_line(ass_text: str) -> list[str]:
    line = next(item for item in ass_text.splitlines() if item.startswith("Style: Default,"))
    return line.split(",")


def test_m4live2_hotfix_restores_dub_runtime_to_m4live1_path():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert not hasattr(bot, "subdub_dub_speech_config")
    assert "subdub_dub_speech_config" not in source
    assert 'kwargs["base_speed"]' not in source
    assert 'kwargs["max_speed"]' not in source
    assert "synthesize_dub_segment_chunks(*args, allow_admin=is_admin_user(uid), **kwargs)" in source


def test_m4live2_hotfix_subtitle_style_is_bottom_center_without_safe_gap():
    style = bot.subdub_normalize_style({
        "m4live1_style_renderer_only": True,
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "video_width": 1280,
        "video_height": 720,
    })

    assert style["m4live1_style_renderer_only"] is True
    assert style["subtitle_pipeline_untouched"] is True
    assert style["subtitle_alignment"] == "bottom_center"
    assert style["subtitle_max_lines"] == 2
    assert 0 <= int(style["subtitle_margin_v_after"]) <= 2


def test_m4live2_hotfix_ass_margin_v_sits_on_bottom_edge():
    ass = bot.subdub_generate_ass_from_srt(
        "1\n00:00:00,000 --> 00:00:02,000\nXin chao, day la phu de dich.\n",
        {
            "m4live1_style_renderer_only": True,
            "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            "video_width": 1280,
            "video_height": 720,
        },
    )
    style_fields = _style_line(ass)

    assert style_fields[18] == "2"
    assert int(style_fields[21]) <= 2
    assert "Xin chao" in ass


def test_m4live2_hotfix_keeps_three_subdub_modes_video_capable():
    assert bot.subdub_has_subtitle_video_output(
        {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "output_type": "video"},
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    ) is True
    assert bot.subdub_video_requires_final_mp4(bot.VIDEO_SUBTITLE_MODE_DUB) is True
    assert bot.subdub_video_requires_final_mp4(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB) is True
