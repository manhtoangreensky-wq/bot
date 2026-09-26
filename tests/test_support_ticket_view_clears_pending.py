import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace


def test_opening_ticket_view_clears_stale_text_input():
    source=(Path(__file__).resolve().parents[1]/'bot.py').read_text(encoding='utf-8')
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.AsyncFunctionDef) and n.name=='handle_ticket_callback')
    pending={'pending_action':'support_ticket','step':'awaiting_message'}
    async def answer(*a,**k): pass
    async def render(*a,**k): pass
    scope={'normalize_user_language':lambda x:x,'get_user_language':lambda uid:'vi',
           'public_hub_copy':lambda lang:{'support_ticket_not_found':'missing'},
           'clear_support_ticket_pending':lambda uid:pending.clear(),
           'is_admin_user':lambda uid:True,
           'get_support_ticket':lambda ticket_id,uid:{'id':int(ticket_id),'status':'open'},
           'public_support_ticket_text':lambda *a:'ticket',
           'support_ticket_detail_keyboard':lambda *a:[],
           'safe_edit_or_send':render,'Update':object,'ContextTypes':SimpleNamespace(DEFAULT_TYPE=object)}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'actual-ticket-callback','exec'),scope)
    query=SimpleNamespace(answer=answer,data='ticket|pv|27',from_user=SimpleNamespace(id=42))
    asyncio.run(scope[node.name](SimpleNamespace(callback_query=query),SimpleNamespace()))
    assert pending == {}


def test_admin_ticket_navigation_releases_old_search_or_reply_state():
    source=(Path(__file__).resolve().parents[1]/'bot.py').read_text(encoding='utf-8')
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.AsyncFunctionDef) and n.name=='handle_ticket_callback')
    pending={'pending_action':'support_ticket','step':'admin_search'}
    async def answer(*a,**k): pass
    async def render(*a,**k): pass
    scope={'normalize_user_language':lambda x:x,'get_user_language':lambda uid:'vi',
           'public_hub_copy':lambda lang:{'support_ticket_not_found':'missing'},
           'clear_support_ticket_pending':lambda uid:pending.clear(),'is_admin_user':lambda uid:True,
           'support_admin_list_payload':lambda *a:('list',[]),
           'support_ticket_stats_text':lambda:'stats','support_reply_templates_text':lambda:'templates',
           'support_admin_menu_text':lambda:'admin','support_admin_menu_keyboard':lambda:[],
           'get_support_ticket':lambda *a:{'id':7,'status':'open'},
           'support_ticket_admin_text':lambda *a:'ticket','support_ticket_admin_keyboard':lambda *a:[],
           'safe_edit_or_send':render,'Update':object,'ContextTypes':SimpleNamespace(DEFAULT_TYPE=object)}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'actual-admin-ticket-callback','exec'),scope)
    for data in ('ticket|al|new|0','ticket|stats','ticket|templates','ticket|av|7|new','ticket|admin'):
        pending.update({'pending_action':'support_ticket','step':'admin_search'})
        query=SimpleNamespace(answer=answer,data=data,from_user=SimpleNamespace(id=99))
        asyncio.run(scope[node.name](SimpleNamespace(callback_query=query),SimpleNamespace()))
        assert pending == {},data
