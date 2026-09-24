"""Execute actual AutoPost callback without provider, DB or full bot import."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import pytest


@pytest.fixture(scope='module')
def callback():
    source = (Path(__file__).resolve().parents[1] / 'bot.py').read_text(encoding='utf-8')
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'autopost_engine_code' for t in n.targets))
    async def noop(*a, **kw): pass
    scope = {'Update': object, 'ContextTypes': SimpleNamespace(DEFAULT_TYPE=object),
             'InlineKeyboardMarkup': lambda rows: rows,
             'InlineKeyboardButton': lambda *a, **kw: None,
             'get_user_language': lambda uid:'vi', 'public_hub_copy': lambda lang:{'main_menu':'Home'},
             'safe_edit_query_message': noop, 'get_effective_brand_profile': lambda uid:{}}
    engine = ast.literal_eval(node.value)
    for n in ast.walk(ast.parse(engine)):
        if isinstance(n, ast.Name) and n.id.startswith('autopost_'):
            scope[n.id] = lambda *a, **kw:'rendered'
    exec(compile(engine, 'actual-autopost-handler', 'exec'), scope)
    return scope['handle_autopost_callback']


@pytest.mark.parametrize('enter,leave,key', [
    ('input|topic','content_input_menu','awaiting_content_input_type'),
    ('conn|telegram','channels','awaiting_telegram_channel_id'),
    ('brand_edit_prompt','brands','awaiting_brand_edit'),
    ('input|topic','main','awaiting_content_input_type'),
    ('conn|telegram','main','awaiting_telegram_channel_id'),
    ('brand_edit_prompt','main','awaiting_brand_edit'),
])
def test_back_clears_only_its_input_and_preserves_draft_job(callback, enter, leave, key):
    async def noop(*a, **kw): pass
    draft = {'caption':'keep'}
    state = {'current_draft':draft, 'other_flow':{'job_id':7}}
    context = SimpleNamespace(user_data=dict(state))
    query = SimpleNamespace(answer=noop, from_user=SimpleNamespace(id=42), data='autopost|'+enter)
    update = SimpleNamespace(callback_query=query)
    async def run():
        await callback(update, context)
        assert key in context.user_data
        query.data='autopost|'+leave
        await callback(update, context)
    asyncio.run(run())
    assert key not in context.user_data
    assert context.user_data == state


@pytest.mark.parametrize('enter,key', [
    ('input|topic', 'awaiting_content_input_type'),
    ('conn|telegram', 'awaiting_telegram_channel_id'),
    ('brand_edit_prompt', 'awaiting_brand_edit'),
])
def test_switching_input_releases_old_autopost_prompt(callback, enter, key):
    async def noop(*args, **kwargs): pass
    keys = {'awaiting_content_input_type', 'awaiting_telegram_channel_id', 'awaiting_brand_edit'}
    state = {name: True for name in keys}
    state['current_draft'] = {'caption': 'keep'}
    state['other_flow'] = {'job_id': 7}
    context = SimpleNamespace(user_data=state)
    query = SimpleNamespace(answer=noop, from_user=SimpleNamespace(id=42), data='autopost|' + enter)
    asyncio.run(callback(SimpleNamespace(callback_query=query), context))
    assert keys.intersection(state) == {key}
    assert state['current_draft'] == {'caption': 'keep'}
    assert state['other_flow'] == {'job_id': 7}
