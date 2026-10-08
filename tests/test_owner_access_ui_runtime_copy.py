"""Owner setup guidance reflects the project's current VPS runtime."""

import asyncio
import html
import re
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _function_source(name):
    start = re.search(rf"(?m)^async def {re.escape(name)}\s*\(|^def {re.escape(name)}\s*\(", BOT_SOURCE)
    assert start is not None, f"missing source function: {name}"
    boundary = re.search(
        r"(?m)^(?:async\s+)?def\s+\w+\s*\(|^class\s+\w+|^[A-Z][A-Z0-9_]*\s*=",
        BOT_SOURCE[start.end():],
    )
    end = start.end() + boundary.start() if boundary else len(BOT_SOURCE)
    return BOT_SOURCE[start.start():end].rstrip()


def _load(name, **dependencies):
    namespace = {"html": html, "__builtins__": __builtins__, **dependencies}
    source = "from __future__ import annotations\n\n" + _function_source(name)
    exec(compile(source, f"bot.py:{name}", "exec"), namespace)
    return namespace[name]


def test_owner_required_text_points_to_vps_not_railway():
    render = _load("owner_required_text")

    text = render(991200)

    assert "OWNER_IDS</code> trên VPS" in text
    assert "Railway" not in text
    assert "<code>991200</code>" in text


def test_admin_whoami_warnings_point_to_vps_without_changing_role_report():
    replies = []

    async def reply_text(text, **kwargs):
        replies.append((text, kwargs))

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=991201, username="owner", first_name="Owner"),
        message=SimpleNamespace(reply_text=reply_text),
    )
    handler = _load(
        "cmd_admin_whoami",
        get_system_role=lambda _uid: "admin",
        OWNER_IDS=[],
        ADMIN_IDS=["42"],
        is_owner_user=lambda _uid: False,
        is_admin_user=lambda _uid: True,
    )

    asyncio.run(handler(update, SimpleNamespace()))

    assert len(replies) == 1
    text, options = replies[0]
    assert "OWNER_IDS đang rỗng, hãy cấu hình OWNER_IDS trên VPS." in text
    assert "thêm ID này vào OWNER_IDS trên VPS." in text
    assert "Railway" not in text
    assert "Effective role: <code>admin</code>" in text
    assert "Can set_vip: <code>yes</code>" in text
    assert options == {"parse_mode": "HTML"}
