from pathlib import Path
import re


BOT_SOURCE = Path(__file__).resolve().parents[1] / "bot.py"


def test_manual_content_context_field_does_not_collide_with_handler_context():
    source = BOT_SOURCE.read_text(encoding="utf-8")
    signature = re.search(
        r"def video_scene3_return_to_parent\((\w+), state: dict, parent: str, \*\*fields\)",
        source,
    )
    handler = source.split("async def handle_video_profile_studio_pending_text", 1)[1].split(
        "async def handle_video_editor_callback", 1
    )[0]

    assert signature is not None
    assert signature.group(1) == "handler_context"
    assert "context=user_text[:1600]" in handler
