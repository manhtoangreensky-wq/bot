"""SECFIX B2: user text cannot escape the FFmpeg filtergraph that renders it.

Watermark, logo and overlay text is typed by the customer and ends up inside a
drawtext filter, quoted with single quotes. The previous escapers turned a
quote into `\\'`. Inside a single-quoted FFmpeg value a backslash is not an
escape character, so that reads as a literal backslash followed by a quote
which *closes the value* — everything after it is parsed as filtergraph syntax
again. Two of the escapers also left `,` and `[` `]` alone, so a whole extra
filter could be chained on.

The fix is not a better escape: a quote cannot be represented inside a
single-quoted value at all, so it is replaced before it ever gets there, at
capture and again when the filter is built.
"""

import re

import pytest

from services import ffmpeg_text
from services import video_local_editing

# Each entry is something a customer could type into the watermark box.
HOSTILE_INPUTS = [
    "normal watermark",
    "TOAN AAS",
    "quote' here",
    "close':drawtext=textfile=/etc/passwd:x=0",
    "chain',movie=/app/bot.py[v]",
    "bracket [0:v] label",
    "comma,separated,filters",
    "percent %{eif:n:d} expansion",
    "backslash \\ mid",
    "double\\\\backslash",
    "newline\nsecond line",
    "carriage\rreturn",
    "tab\tinside",
    "null\x00byte",
    'double "quote" inside',
    "'; rm -rf /; '",
    "semi;colon",
    "equals=sign",
    "'''",
    "\\'",
]


@pytest.mark.parametrize("raw", HOSTILE_INPUTS)
def test_escaped_text_can_never_carry_a_quote_or_backslash(raw):
    escaped = ffmpeg_text.escape_filter_text(raw)
    assert "'" not in escaped, "a quote would close the filter value"
    assert "\\" not in escaped, "a backslash is not an escape inside quotes"
    assert '"' not in escaped
    assert not re.search(r"[\x00-\x1f\x7f]", escaped), "a newline ends the value"


@pytest.mark.parametrize("raw", HOSTILE_INPUTS)
def test_quoted_value_stays_balanced(raw):
    fragment = f"drawtext=text={ffmpeg_text.quote_filter_value(raw)}:fontcolor=white"
    assert ffmpeg_text.drawtext_is_safe(fragment), fragment
    # Exactly one opening and one closing quote: the value cannot break out.
    assert fragment.count("'") == 2, fragment


@pytest.mark.parametrize("raw", HOSTILE_INPUTS)
def test_capture_layer_also_removes_the_breakout_characters(raw):
    cleaned = ffmpeg_text.sanitize_overlay_text(raw)
    assert "'" not in cleaned
    assert "\\" not in cleaned
    assert '"' not in cleaned
    assert "\n" not in cleaned and "\r" not in cleaned


def test_the_known_breakout_payloads_lose_their_teeth():
    for payload in (
        "x':drawtext=textfile=/proc/self/environ:x=0:y=0'",
        "x',movie=/app/bot.py[bg]'",
        "x'[0:v]concat'",
    ):
        fragment = f"drawtext=text={ffmpeg_text.quote_filter_value(payload)}"
        assert fragment.count("'") == 2
        assert "textfile=" not in fragment.split("'")[0]
        assert ffmpeg_text.drawtext_is_safe(fragment)


def test_ordinary_vietnamese_captions_survive_intact():
    # The whole point is to keep captions readable, so normal punctuation and
    # diacritics must not be collateral damage.
    for text in (
        "Giảm giá 50% hôm nay",
        "TOAN AAS - dịch vụ AI",
        "Liên hệ: 0900 000 000",
        "Ảnh đẹp, video nhanh",
        "Khuyến mãi (chỉ hôm nay)",
    ):
        cleaned = ffmpeg_text.sanitize_overlay_text(text)
        assert cleaned == text, "readable punctuation must be preserved"


def test_apostrophes_become_readable_rather_than_vanishing():
    cleaned = ffmpeg_text.sanitize_overlay_text("Toan's studio")
    assert "'" not in cleaned
    assert cleaned == "Toan’s studio", "substitute, do not silently delete"


def test_whitespace_is_collapsed_and_length_is_capped():
    assert ffmpeg_text.sanitize_overlay_text("  a\t\t b \n c  ") == "a b c"
    assert len(ffmpeg_text.sanitize_overlay_text("x" * 5000, 300)) == 300


def test_paths_lose_quotes_and_keep_a_windows_drive_usable():
    assert "'" not in ffmpeg_text.escape_filter_path("/tmp/it's here/sub.srt")
    windows = ffmpeg_text.escape_filter_path("C:/tmp/sub.srt", resolve=False)
    assert windows.startswith("C\\:"), "the option parser splits on a bare colon"
    assert "\\\\" not in windows


def _source(relative):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    return (root / relative).read_text(encoding="utf-8", errors="replace")


def test_every_former_escaper_now_routes_to_the_shared_module():
    for path, function in (
        ("services/video_local_editing.py", "_escape_filter_text"),
        ("services/video_local_editing.py", "_escape_filter_path"),
        ("services/frame_video_runtime.py", "_escape_drawtext"),
        ("services/multiscene_video_pipeline.py", "_drawtext_escape"),
        ("services/video_postprocess_pipeline.py", "_filter_path"),
    ):
        source = _source(path)
        body = source.split(f"def {function}(", 1)[1].split("\ndef ", 1)[0]
        assert "ffmpeg_text." in body, f"{path}:{function} still escapes locally"
        assert "\\\\'" not in body, f"{path}:{function} still tries to escape a quote"


def test_no_module_still_hand_escapes_a_quote_for_a_filter():
    for path in (
        "services/video_local_editing.py",
        "services/frame_video_runtime.py",
        "services/multiscene_video_pipeline.py",
        "services/video_postprocess_pipeline.py",
    ):
        assert '.replace("\'", "\\\\\'")' not in _source(path), path


def test_drawtext_builders_disable_text_expansion():
    # `%` and `{}` are expanded by drawtext at render time; expansion=none is
    # the supported way to make them literal.
    for path in ("services/frame_video_runtime.py", "services/multiscene_video_pipeline.py"):
        source = _source(path)
        for fragment in re.findall(r"drawtext=text='\{[^']*?'", source):
            pass
        assert "DRAWTEXT_NO_EXPANSION" in source, f"{path} does not disable expansion"


def test_manual_editor_drawtext_disables_text_expansion():
    fragment = video_local_editing._text_filter(
        {
            "content": "%{n}",
            "position": "bottom_center",
            "font_size": 42,
            "outline": 2,
            "start_ms": 0,
            "end_ms": 1000,
        }
    )
    assert ffmpeg_text.DRAWTEXT_NO_EXPANSION in fragment


def test_subtitle_path_site_that_had_no_quote_handling_is_fixed():
    source = _source("services/multiscene_video_pipeline.py")
    assert 'os.path.abspath(subtitle_path).replace("\\\\", "\\\\\\\\")' not in source
    assert "ffmpeg_text.escape_filter_path(subtitle_path)" in source
