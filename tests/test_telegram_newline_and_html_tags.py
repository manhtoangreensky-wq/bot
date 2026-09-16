import re

import bot


def test_html_message_to_plain_text_newlines_and_tags():
    # 1. <br> and </p> converted to real newlines, not literal \n
    html_input = "<b>Hello</b><br>World<p>Paragraph</p>"
    plain = bot.html_message_to_plain_text(html_input)
    assert "\\n" not in plain
    assert "\n" in plain
    assert "<b>" not in plain
    assert "</b>" not in plain
    assert "Hello" in plain
    assert "World" in plain
    assert "Paragraph" in plain

    # 2. Literal \\n in input is normalized to real newline
    raw_escaped = "Line 1\\nLine 2\\n\\nLine 3"
    plain2 = bot.html_message_to_plain_text(raw_escaped)
    assert "\\n" not in plain2
    assert "Line 1\nLine 2\n\nLine 3" == plain2

    # 3. Trailing truncated tag is stripped cleanly
    truncated = "Some text <b>bold content</b> and <b"
    plain3 = bot.html_message_to_plain_text(truncated)
    assert "<b" not in plain3
    assert plain3.strip() == "Some text bold content and"


def test_split_telegram_html_text_normalizes_literal_newlines():
    raw = "<b>Title</b>\\n\\n• Item 1\\n• Item 2"
    chunks = bot.split_telegram_html_text(raw, limit=3600)
    assert len(chunks) == 1
    assert "\\n" not in chunks[0]
    assert "\n" in chunks[0]
    assert chunks[0] == "<b>Title</b>\n\n• Item 1\n• Item 2"


def test_split_telegram_html_text_balances_b_tags_across_chunks():
    # Create long text wrapped in <b> that exceeds limit
    long_bold = "<b>" + ("word " * 800) + "</b>"
    assert len(long_bold) > 3600
    chunks = bot.split_telegram_html_text(long_bold, limit=1200)
    assert len(chunks) > 1

    for idx, chunk in enumerate(chunks):
        assert len(chunk) <= 1300  # allowing small overhead for closing/reopening tags
        open_b = chunk.count("<b>")
        close_b = chunk.count("</b>")
        assert open_b == close_b, f"Chunk {idx} has unbalanced <b> tags: open={open_b}, close={close_b}"
        assert chunk.startswith("<b>")
        assert chunk.endswith("</b>")


def test_split_telegram_html_text_nested_tags_balance():
    # Test nested <b><i><code> tags
    long_nested = "<b>Important: <i>" + ("code_segment_test " * 400) + "</i> finish</b>"
    chunks = bot.split_telegram_html_text(long_nested, limit=1000)
    assert len(chunks) > 1

    for idx, chunk in enumerate(chunks):
        assert chunk.count("<b>") == chunk.count("</b>"), f"Chunk {idx} unbalanced <b>"
        assert chunk.count("<i>") == chunk.count("</i>"), f"Chunk {idx} unbalanced <i>"


def test_engine_async_waiting_text_real_newlines():
    job = {"internal_job_id": "job_12345"}
    text = bot.engine_async_waiting_text(job, admin=True)
    assert "\\n" not in text
    assert "\n" in text
    assert "Mã xử lý:" in text
    lines = text.split("\n")
    assert len(lines) >= 3


def test_cinematic_ad_concept_text_splits_cleanly():
    concept = bot.cinematic_ad_concept_text("mini blender", "fast fresh smoothie", "cinematic", "en")
    assert "\\n" not in concept
    assert "\n" in concept
    assert "<b>TOAN AAS CINEMATIC AD CONCEPT</b>" in concept
    chunks = bot.split_telegram_html_text(concept, limit=800)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.count("<b>") == chunk.count("</b>")
        assert "\\n" not in chunk
