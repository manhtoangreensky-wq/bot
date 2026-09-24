import ast
from pathlib import Path


def test_start_clears_non_producer_pending_flows():
    source = (Path(__file__).resolve().parents[1] / 'bot.py').read_text(encoding='utf-8')
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.AsyncFunctionDef)
                and n.name == 'cmd_start')
    calls = {n.func.id for n in ast.walk(node) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name)}
    expected = {'clear_support_ticket_pending', 'clear_broadcast_lite_pending',
                'clear_memory_guided_pending', 'clear_storage_addon_pending',
                'clear_translation_menu_pending', 'clear_translation_session'}
    assert expected <= calls
