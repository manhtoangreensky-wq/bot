import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace


def test_broadcast_back_releases_pending_owner_without_deleting_draft():
    source = (Path(__file__).resolve().parents[1] / 'bot.py').read_text(encoding='utf-8')
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.AsyncFunctionDef)
                and n.name == 'handle_broadcast_lite_callback')
    pending = {'draft_id': 9, 'state': 'awaiting_content'}
    calls = []
    async def answer(*a, **kw): pass
    async def edit(*a, **kw): calls.append((a,kw))
    scope = {'is_admin_user': lambda uid: True, 'clear_broadcast_lite_pending': lambda uid: pending.clear(),
             'broadcast_lite_admin_menu_text': lambda:'menu',
             'broadcast_lite_admin_menu_keyboard': lambda:[],
             '_broadcast_lite_answer_callback': answer, '_broadcast_lite_edit': edit,
             'Update': object, 'ContextTypes': SimpleNamespace(DEFAULT_TYPE=object)}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'actual-broadcast-handler', 'exec'), scope)
    query = SimpleNamespace(answer=answer, data='broadcast_lite|back', from_user=SimpleNamespace(id=1))
    asyncio.run(scope[node.name](SimpleNamespace(callback_query=query, effective_user=query.from_user), SimpleNamespace()))
    assert pending == {}
    assert calls
