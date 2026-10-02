import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

import pytest


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


class _Query:
    def __init__(self, data: str) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=81001)
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def _load_handler(events):
    match = re.search(
        r"(?ms)^async def handle_video_dubbing_callback\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert match, "SubDub callback handler is missing"

    async def _open_postdelivery(_query, _context, **kwargs):
        events.append(("open", kwargs))
        return True

    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "get_user_language": lambda _uid: "vi",
        "open_subdub_postdelivery_video_edit": _open_postdelivery,
        "logger": SimpleNamespace(warning=lambda *args, **kwargs: None),
    }
    exec(compile(match.group(0), "bot.py:handle_video_dubbing_callback", "exec"), namespace)
    return namespace["handle_video_dubbing_callback"]


def _load_postdelivery_error_handler(edits):
    match = re.search(
        r"(?ms)^async def open_subdub_postdelivery_video_edit\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)",
        BOT_SOURCE,
    )
    assert match, "post-delivery SubDub editor handoff is missing"

    async def _safe_edit_or_send(_query, text, **kwargs):
        edits.append((text, kwargs))

    namespace = {
        "subdub_resolve_postdelivery_video_edit_artifact": lambda *_args, **_kwargs: {},
        "safe_edit_or_send": _safe_edit_or_send,
        "VideoEditorStateUnavailableError": RuntimeError,
        "VideoEditorStateCommitError": RuntimeError,
    }
    exec(
        compile(match.group(0), "bot.py:open_subdub_postdelivery_video_edit", "exec"),
        namespace,
    )
    return namespace["open_subdub_postdelivery_video_edit"]


@pytest.mark.parametrize("action", ["edit", "branding"])
def test_postdelivery_edit_callbacks_ack_before_editor_state_work(action):
    events = []
    handler = _load_handler(events)
    query = _Query(f"videodub|{action}|0123456789abcdef")

    asyncio.run(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

    assert query.answers == [((), {})]
    assert [event[0] for event in events] == ["open"]
    assert events[0][1]["callback_acknowledged"] is True


def test_postdelivery_error_does_not_try_a_second_ack_after_early_ack():
    edits = []
    handler = _load_postdelivery_error_handler(edits)
    query = _Query("videodub|edit|0123456789abcdef")

    asyncio.run(
        handler(
            query,
            SimpleNamespace(),
            user_id=81001,
            token="0123456789abcdef",
            target="edit",
            lang="vi",
            callback_acknowledged=True,
        )
    )

    assert query.answers == []
    assert edits and "Không còn mở được đúng video" in edits[0][0]
