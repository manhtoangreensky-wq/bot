import ast
from pathlib import Path


def test_start_clears_all_small_navigation_pending_states():
    source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
    start = source.index("async def cmd_start(")
    end = source.index("\nasync def cmd_menu(", start)
    node = ast.parse(source[start:end]).body[0]
    assert isinstance(node, ast.AsyncFunctionDef) and node.name == "cmd_start"
    calls = {
        item.func.id
        for item in ast.walk(node)
        if isinstance(item, ast.Call) and isinstance(item.func, ast.Name)
    }
    expected = {
        "clear_support_ticket_pending",
        "clear_broadcast_lite_pending",
        "clear_memory_guided_pending",
        "clear_storage_addon_pending",
        "clear_translation_menu_pending",
        "clear_translation_session",
    }
    assert expected <= calls
