import bot


SRT_TEXT = (
    "1\n"
    "00:00:01,000 --> 00:00:03,500\n"
    "Xin chao the gioi\n\n"
    "2\n"
    "00:00:04,000 --> 00:00:06,250\n"
    "Dong thu hai duoc giu dung thoi gian\n"
)


def _state(mode: str) -> dict:
    return {
        "mode": mode,
        "output_type": "burn",
        "video_width": 1920,
        "video_height": 1080,
        "m4live1_style_renderer_only": True,
        "subdub_canonical_product_contract": True,
    }


def _style_fields(ass_text: str) -> list[str]:
    style_line = next(line for line in ass_text.splitlines() if line.startswith("Style: Default"))
    return style_line.split(",")


def _dialogues(ass_text: str) -> list[str]:
    return [line for line in ass_text.splitlines() if line.startswith("Dialogue:")]


def test_style1_caption_box_is_semitransparent_bold_and_not_full_width(monkeypatch):
    monkeypatch.setattr(
        bot,
        "resolve_subdub_subtitle_font",
        lambda _style: {"ok": True, "family": "Arial", "path": "fixture.ttf", "blocker": ""},
    )
    state = _state(bot.VIDEO_SUBTITLE_MODE_TRANSLATE)
    style = bot.subdub_normalize_style(state)
    ass_text = bot.subdub_generate_ass_from_srt(SRT_TEXT, state)
    fields = _style_fields(ass_text)

    assert style["background"] == "box"
    assert style["boxed_background"] is True
    assert fields[7] == "-1"
    assert fields[15] == "3"
    assert fields[6].startswith("&H") and fields[6] != "&HFF000000"
    assert bot.subdub_cover_filter(state) == ""
    assert "drawbox" not in ass_text


def test_style1_uppercase_preserves_cue_timing_and_two_line_limit(monkeypatch):
    monkeypatch.setattr(
        bot,
        "resolve_subdub_subtitle_font",
        lambda _style: {"ok": True, "family": "Arial", "path": "fixture.ttf", "blocker": ""},
    )
    ass_text = bot.subdub_generate_ass_from_srt(SRT_TEXT, _state(bot.VIDEO_SUBTITLE_MODE_TRANSLATE))
    dialogues = _dialogues(ass_text)

    assert len(dialogues) == 2
    assert ",0:00:01.00,0:00:03.50," in dialogues[0]
    assert ",0:00:04.00,0:00:06.25," in dialogues[1]
    assert "XIN CHAO THE GIOI" in dialogues[0]
    assert "DONG THU HAI DUOC GIU DUNG THOI GIAN" in dialogues[1].replace(r"\N", " ")
    assert all(line.count(r"\N") <= 1 for line in dialogues)


def test_style1_subtitle_and_combo_share_the_same_style_helper(monkeypatch):
    monkeypatch.setattr(
        bot,
        "resolve_subdub_subtitle_font",
        lambda _style: {"ok": True, "family": "Arial", "path": "fixture.ttf", "blocker": ""},
    )
    subtitle_state = _state(bot.VIDEO_SUBTITLE_MODE_TRANSLATE)
    combo_state = _state(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB)
    subtitle_style = bot.subdub_normalize_style(subtitle_state)
    combo_style = bot.subdub_normalize_style(combo_state)

    for key in ("background", "boxed_background", "uppercase_text", "bold_text", "max_lines"):
        assert subtitle_style[key] == combo_style[key]
    assert _style_fields(bot.subdub_generate_ass_from_srt(SRT_TEXT, subtitle_state))[15] == "3"
    assert _style_fields(bot.subdub_generate_ass_from_srt(SRT_TEXT, combo_state))[15] == "3"
