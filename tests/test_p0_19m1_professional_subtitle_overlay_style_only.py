import inspect

import bot
from services import subtitle_dub_product_pipeline


VALID_SRT = "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n"


def _style(**extra):
    return bot.subdub_normalize_style({"subtitle_style_preset": "cover_original", **extra})


def test_subtitle_font_size_increased_responsive():
    default_style = _style()
    style_720 = _style(video_height=720, video_width=1280)
    style_1080 = _style(video_height=1080, video_width=1920)
    style_vertical = _style(video_height=1280, video_width=720)

    assert default_style["size"] >= 50
    assert 44 <= style_720["size"] <= 48
    assert 50 <= style_1080["size"] <= 58
    assert 52 <= style_vertical["size"] <= 58


def test_subtitle_style_has_outline_or_box():
    style = _style()
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, style)

    assert style["outline"] >= 2
    assert style["shadow"] >= 1
    assert style["boxed_background"] is True
    assert "BorderStyle" in ass
    assert ",3," in ass
    assert "&H" in ass


def test_cover_bar_bottom_safe_area_only():
    style = _style()
    drawbox = bot.subdub_cover_filter(style)
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, style)

    assert style["cover_y_ratio"] >= 0.90
    assert style["cover_height_ratio"] <= 0.06
    assert drawbox == "" or "y=ih*0.90" in drawbox or "y=ih*0.91" in drawbox
    assert drawbox == "" or "h=ih*0.05" in drawbox or "h=ih*0.06" in drawbox
    assert ",3," in ass


def test_cover_bar_not_mid_screen():
    style = _style(cover_y_ratio=0.62, cover_height_ratio=0.22)

    assert style["cover_y_ratio"] >= 0.90
    assert "y=ih*0.62" not in bot.subdub_cover_filter(style)


def test_cover_height_not_too_large():
    style = _style(cover_height_ratio=0.24)

    assert style["cover_height_ratio"] <= 0.06
    assert "h=ih*0.24" not in bot.subdub_cover_filter(style)


def test_translated_subtitle_position_readable():
    ass = bot.subdub_generate_ass_from_srt(VALID_SRT, _style())

    assert "Style: Default" in ass
    assert "Dialogue: 0" in ass
    assert "Xin chao" in ass


def test_subtitle_only_pipeline_unchanged():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert "subtitle_dub_product_pipeline.run_subdub_pipeline" in source
    assert "subdub_output_style_state" in source
    assert "spend_fixed_credit_info" in source


def test_subtitle_dub_pipeline_unchanged():
    source = inspect.getsource(subtitle_dub_product_pipeline.process_subtitle_dub_job)

    assert "synthesize_segments" in source
    assert "render_video" in source
    assert "partial_result" in source


def test_no_music_video_payos_changes():
    style_source = "\n".join(
        [
            inspect.getsource(bot.subdub_normalize_style),
            inspect.getsource(bot.subdub_generate_ass_from_srt),
            inspect.getsource(bot.subdub_cover_filter),
        ]
    ).lower()

    assert "music" not in style_source
    assert "payos" not in style_source
    assert "wallet" not in style_source
    assert "pricing" not in style_source
