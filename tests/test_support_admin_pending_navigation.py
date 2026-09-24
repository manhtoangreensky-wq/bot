import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace


def test_admin_navigation_releases_search_input_state():
    source = (Path(__file__).resolve().parents[1] / 'bot.py').read_text(encoding='utf-8')
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.AsyncFunctionDef)
                and n.name == 'handle_ticket_callback')
    state = {'pending_action':'support_ticket','step':'admin_search'}
    async def answer(*args, **kwargs): pass
    async def render(*args, **kwargs): pass
    scope = {'normalize_user_language':lambda x:x, 'get_user_language':lambda uid:'vi',
             'public_hub_copy':lambda lang:{}, 'clear_support_ticket_pending':lambda uid:state.clear(),
             'is_admin_user':lambda uid:True, 'support_ticket_stats_text':lambda:'stats',
             'support_reply_templates_text':lambda:'templates', 'support_admin_menu_keyboard':lambda:[],
             'support_admin_menu_text':lambda:'admin', 'support_admin_list_payload':lambda *a:('list',[]),
             'safe_edit_or_send':render, 'Update':object, 'ContextTypes':SimpleNamespace(DEFAULT_TYPE=object)}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'ticket-handler', 'exec'), scope)
    for action in ('stats','templates','admin','al|new|0'):
        state['pending_action']='support_ticket'; state['step']='admin_search'
        query=SimpleNamespace(answer=answer,data='ticket|'+action,from_user=SimpleNamespace(id=42))
        asyncio.run(scope[node.name](SimpleNamespace(callback_query=query),SimpleNamespace()))
        assert state == {}, action
