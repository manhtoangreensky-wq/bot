import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace


def test_consult_type_releases_old_support_input_state():
    source = (Path(__file__).resolve().parents[1] / 'bot.py').read_text(encoding='utf-8')
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.AsyncFunctionDef)
                and n.name == 'handle_human_support_callback')
    state = {'pending_action':'support_ticket','step':'awaiting_message','support_pending_input':'1'}
    captured = []
    async def answer(*a, **kw): pass
    async def render(*args, **kwargs): captured.append((args, kwargs))
    scope = {'get_user_language': lambda uid:'vi', 'normalize_user_language':lambda x:x,
             'clear_support_ticket_pending': lambda uid: state.clear(),
             'set_support_ticket_pending': lambda *a, **kw: state.update(kw),
             'support_consult_detail_text': lambda *a: 'detail',
             'support_consult_detail_keyboard': lambda *a: [],
             'safe_edit_or_send': render, 'public_hub_copy': lambda lang:{},
             'support_consult_choice_labels':lambda *a:[], 'support_consult_public_label':lambda *a:'',
             'SUPPORT_CONSULT_DETAILS': {'video': ('Video', [], None)},
             'Update': object, 'ContextTypes': SimpleNamespace(DEFAULT_TYPE=object)}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'support-callback', 'exec'), scope)
    query = SimpleNamespace(answer=answer, from_user=SimpleNamespace(id=42),
                            data='support|consult_type|video')
    asyncio.run(scope[node.name](SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert state == {}
