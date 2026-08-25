from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def _runtime_namespace() -> dict:
    tree = ast.parse((ROOT / "bot.py").read_text(encoding="utf-8"))
    names = {
        "split_telegram_html_text",
        "safe_reply_text",
        "safe_reply_long_html",
        "video_uiflow3_reply",
    }
    selected = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in names
    ]
    assert {node.name for node in selected} == names
    namespace = {
        "logger": SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        "sanitize_log_text": str,
        "html_message_to_plain_text": str,
        "save_video_uiflow3_state": lambda _context, state: state,
        "video_uiflow3_canonical_screen_state": lambda state: state,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), "bot.py", "exec"), namespace)
    return namespace


def test_video_uiflow3_reply_splits_long_screen_and_keeps_keyboard_on_last_chunk() -> None:
    runtime = _runtime_namespace()
    long_text = "A" * 4500
    keyboard = object()
    runtime["video_uiflow3_screen_payload"] = lambda _state: (long_text, keyboard)

    class FakeMessage:
        def __init__(self) -> None:
            self.replies: list[dict] = []

        async def reply_text(self, text: str, **kwargs) -> None:
            self.replies.append({"text": text, "kwargs": kwargs})

    message = FakeMessage()
    asyncio.run(runtime["video_uiflow3_reply"](message, object(), {}))

    assert len(message.replies) == 2
    assert "".join(item["text"] for item in message.replies) == long_text
    assert all(len(item["text"]) <= 3600 for item in message.replies)
    assert message.replies[0]["kwargs"].get("reply_markup") is None
    assert message.replies[-1]["kwargs"].get("reply_markup") is keyboard
