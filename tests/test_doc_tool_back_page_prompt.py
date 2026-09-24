import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace


def test_back_to_received_releases_page_prompt_but_keeps_files():
    source = (Path(__file__).resolve().parents[1] / 'bot.py').read_text(encoding='utf-8')
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.AsyncFunctionDef)
                and n.name == 'handle_doc_tool_callback')
    state = {'doc_tool_current': 'split_pdf', 'awaiting_page_spec': '1',
             'doc_tool_files': [{'file_id': 'keep'}], 'doc_tool_options': {'page_spec':'1-3'}}
    async def noop(*args, **kwargs): pass
    scope = {'Update': object, 'ContextTypes': SimpleNamespace(DEFAULT_TYPE=object),
             'get_user_language': lambda uid: 'vi', 'get_doc_tool_pending': lambda uid: state,
             'safe_edit_or_send': noop, 'doc_tool_received_text': lambda *a: 'received',
             'doc_tool_after_file_keyboard': lambda *a: [],
             'doc_tool_pending_key': lambda uid: 'doc42', 'USER_PENDING': {'doc42':state}}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'actual-doc-handler', 'exec'), scope)
    query = SimpleNamespace(answer=noop, data='doc|back_received', from_user=SimpleNamespace(id=42))
    asyncio.run(scope[node.name](SimpleNamespace(callback_query=query), SimpleNamespace()))
    assert state.get('awaiting_page_spec', '0') == '0'
    assert state['doc_tool_files'] == [{'file_id':'keep'}]
    assert state['doc_tool_options'] == {'page_spec':'1-3'}
    assert scope['USER_PENDING']['doc42']['awaiting_page_spec'] == '0'
