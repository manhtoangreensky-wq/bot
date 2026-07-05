import inspect

import bot


VALID_VI_SRT = (
    "1\n"
    "00:00:00,000 --> 00:00:02,000\n"
    "Xin chào, tôi đang dùng phụ đề tiếng Việt rõ ràng.\n\n"
    "2\n"
    "00:00:02,100 --> 00:00:04,000\n"
    "Nội dung mới che phụ đề cũ và vẫn đọc được.\n"
)


def _callbacks(markup):
    return [
        button.callback_data
        for row in getattr(markup, "inline_keyboard", []) or []
        for button in row
    ]


def _labels(markup):
    return [
        button.text
        for row in getattr(markup, "inline_keyboard", []) or []
        for button in row
    ]


def test_subdub_ass_written_utf8():
    ass = bot.subdub_generate_ass_from_srt(VALID_VI_SRT, {"subtitle_style_preset": "cover_original"})
    encoded = ass.encode("utf-8")

    assert encoded.decode("utf-8") == ass
    assert not encoded.startswith(b"\xef\xbb\xbf")
    assert "Xin chào" in ass


def test_subdub_translated_vietnamese_renders_without_broken_glyphs():
    ass = bot.subdub_generate_ass_from_srt(VALID_VI_SRT, {"subtitle_style_preset": "cover_original"})
    validation = bot.subdub_validate_subtitle_text_for_delivery(VALID_VI_SRT)

    assert validation["ok"] is True
    assert validation["broken_glyph_ratio"] < 0.05
    assert "□" not in ass
    assert "\ufffd" not in ass


def test_subdub_chinese_source_vietnamese_target_uses_supported_font(tmp_path):
    font_path = tmp_path / "NotoSansCJK-Regular.ttc"
    font_path.write_bytes(b"fake-font-presence")

    resolved = bot.resolve_subdub_subtitle_font(
        {"font": "Noto Sans CJK SC", "source_language": "中文", "target_language": "Tiếng Việt"},
        candidates=(
            {
                "family": "Noto Sans CJK SC",
                "paths": (str(font_path),),
                "vietnamese": True,
                "cjk": True,
            },
        ),
    )

    assert resolved["ok"] is True
    assert resolved["supports_vietnamese"] is True
    assert resolved["supports_cjk"] is True
    assert resolved["family"] == "Noto Sans CJK SC"


def test_subdub_resolve_subtitle_font_has_vietnamese_support_or_blocks_clean(tmp_path):
    font_path = tmp_path / "DejaVuSans.ttf"
    font_path.write_bytes(b"fake-font-presence")

    available = bot.resolve_subdub_subtitle_font(
        {"font": "DejaVu Sans"},
        candidates=(
            {"family": "DejaVu Sans", "paths": (str(font_path),), "vietnamese": True, "cjk": False},
        ),
    )
    missing = bot.resolve_subdub_subtitle_font({"font": ""}, candidates=())

    assert available["ok"] is True
    assert available["supports_vietnamese"] is True
    assert missing["ok"] is False
    assert missing["blocker"] == "subtitle_font_missing"


def test_subdub_broken_glyph_ratio_blocks_success():
    broken = "1\n00:00:00,000 --> 00:00:02,000\n□□□□□□ 000000 □□□□□□\n"
    validation = bot.subdub_validate_subtitle_text_for_delivery(broken)

    assert validation["ok"] is False
    assert validation["blocker"] == "broken_glyphs"
    assert validation["broken_glyph_ratio"] > 0.18


def test_subdub_empty_translation_blocks_success():
    empty = "1\n00:00:00,000 --> 00:00:02,000\n\n"
    validation = bot.subdub_validate_subtitle_text_for_delivery(empty)

    assert validation["ok"] is False
    assert validation["blocker"] == "empty_translation"


def test_subtitle_only_success_requires_readable_subtitle_text():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert bot.subdub_validate_subtitle_text_for_delivery(VALID_VI_SRT)["ok"] is True
    assert "SUBTITLE_TEXT_UNREADABLE" in source
    assert "subdub_validate_subtitle_text_for_delivery" in source


def test_subtitle_dub_success_requires_readable_subtitle_text():
    source = inspect.getsource(bot.video_dubbing_render_video)

    assert "subtitle_text_unreadable" in source
    assert "subtitle_font_missing" in source
    assert "subdub_generate_ass_from_srt" in source


def test_subdub_confirm_back_returns_previous_option_screen():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "target_language": "Tiếng Việt",
        "source_file_id": "file-video",
        "source_mime_type": "video/mp4",
    }
    markup = bot.video_dubbing_confirm_keyboard("vi", state)

    assert "videodub|back_language" in _callbacks(markup)
    assert "menu|main" in _callbacks(markup)
    assert bot.video_dubbing_back_route(state, "back_confirm") == "language"


def test_subdub_language_confirm_back_not_root_menu():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "active_flow": bot.VIDEO_DUBBING_FLOW_SUBTITLE_PLUS_DUB,
        "flow_type": bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE,
        "combo_subpath": bot.VIDEO_DUBBING_NO_SUBTITLE_DIRECT_DUB,
    }
    markup = bot.video_dubbing_language_keyboard("vi", state)
    callbacks = _callbacks(markup)

    assert f"videodub|path|{bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE}" in callbacks
    assert callbacks[-2] == f"videodub|path|{bot.VIDEO_DUBBING_FLOW_NO_SUBTITLE}"
    assert callbacks[-1] == "menu|main"


def test_subdub_missing_origin_fallbacks_to_subdub_menu_not_main_menu():
    assert bot.subdub_missing_origin_back_callback({}) == "videodub|back_type"

    markup = bot.video_dubbing_job_progress_keyboard(123, "vi")
    callbacks = _callbacks(markup)
    labels = _labels(markup)

    assert "videodub|back_type" in callbacks
    assert "menu|main" in callbacks
    assert "⬅️ Phụ đề / Lồng tiếng" in labels
    assert "⬅️ Quay lại" not in labels


def test_public_subdub_screens_no_debug_terms():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "target_language": "Tiếng Việt",
        "source_file_id": "file-video",
        "source_mime_type": "video/mp4",
    }
    public_text = "\n".join(
        [
            bot.video_dubbing_confirm_text(state, "vi"),
            bot.video_dubbing_language_text(state, "vi"),
            bot.video_dubbing_job_progress_text("subtitle", 123, "vi"),
            "\n".join(_labels(bot.video_dubbing_confirm_keyboard("vi", state))),
            "\n".join(_labels(bot.video_dubbing_job_progress_keyboard(123, "vi"))),
        ]
    ).lower()

    for forbidden in ("provider", "api", "handler", "callback", "ffmpeg", "asr", "tts", "mux", "debug"):
        assert forbidden not in public_text
