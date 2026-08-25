from pathlib import Path


def test_video_status_panel_joins_lines_with_real_newlines():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
    rendering_block = source[
        source.index("def video_b14_provider_rendering_block("):
        source.index("def video_b14_primary_alive_attempt(")
    ]
    status_block = source[
        source.index("def video_b14_queue_status_text("):
        source.index("def video_b14_queue_status_keyboard(")
    ]

    for block in (rendering_block, status_block):
        assert '"\\\\n".join(lines)' not in block
        assert '"\\n".join(lines)' in block
