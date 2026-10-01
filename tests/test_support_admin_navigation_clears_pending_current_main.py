import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace


def test_admin_ticket_navigation_clears_stale_search_state():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
    node = next(
        item for item in ast.parse(source).body
        if isinstance(item, ast.AsyncFunctionDef) and item.name == "handle_ticket_callback"
    )
    pending = {"pending_action": "support_ticket", "step": "admin_search"}

    async def answer(*args, **kwargs):
        return None

    async def render(*args, **kwargs):
        return None

    scope = {
        "normalize_user_language": lambda value: value,
        "get_user_language": lambda uid: "vi",
        "public_hub_copy": lambda lang: {"support_ticket_admin_only": "admin only"},
        "clear_support_ticket_pending": lambda uid: pending.clear(),
        "is_admin_user": lambda uid: True,
        "support_admin_list_payload": lambda *args: ("list", []),
        "support_ticket_stats_text": lambda: "stats",
        "support_reply_templates_text": lambda: "templates",
        "support_admin_menu_keyboard": lambda: [],
        "support_admin_menu_text": lambda: "admin",
        "safe_edit_or_send": render,
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), "ticket-handler", "exec"), scope)

    for callback_data in ("ticket|al|new|0", "ticket|stats", "ticket|templates"):
        pending.update({"pending_action": "support_ticket", "step": "admin_search"})
        query = SimpleNamespace(answer=answer, data=callback_data, from_user=SimpleNamespace(id=42))
        asyncio.run(scope[node.name](SimpleNamespace(callback_query=query), SimpleNamespace()))
        assert pending == {}, callback_data
