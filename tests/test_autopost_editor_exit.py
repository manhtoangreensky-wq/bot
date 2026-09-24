import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture(scope='module')
def source_tree():
    return ast.parse((Path(__file__).resolve().parents[1] / 'bot.py').read_text(encoding='utf-8'))


@pytest.mark.parametrize('name', ['cmd_start', 'handle_menu_callback'])
def test_real_exit_entry_releases_autopost_only(source_tree, name):
    node = next(n for n in source_tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    class DownstreamReached(Exception): pass
    def stop(*args, **kwargs): raise DownstreamReached()
    async def answer(): pass
    scope = {'Update': object, 'ContextTypes': SimpleNamespace(DEFAULT_TYPE=object),
             'log_command_received': stop, 'is_admin_user': stop,
             'VIDEO_TAIL9_TEXT_INPUT_KEY': 'existing_cleanup_key'}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'actual-exit-entry', 'exec'), scope)
    retained = {'current_draft': {'caption': 'old'}, 'other_flow': {'job_id': 7}}
    ctx = SimpleNamespace(user_data={**retained, 'autopost_caption_edit': {'candidate':'new'},
        'awaiting_content_input_type':'topic', 'awaiting_brand_edit':True, 'awaiting_telegram_channel_id':True})
    query = SimpleNamespace(answer=answer, data='menu|main', from_user=SimpleNamespace(id=42))
    with pytest.raises(DownstreamReached):
        asyncio.run(scope[name](SimpleNamespace(callback_query=query), ctx))
    assert ctx.user_data == retained


def test_clearing_editor_invalidates_old_save_without_losing_draft():
    from services.autopost_draft_edit import clear_pending, handle_callback
    from unittest.mock import AsyncMock
    draft = {'owner_user_id':42, 'caption':'old'}
    ctx = SimpleNamespace(user_data={'current_draft': draft, 'autopost_caption_edit': {
        'owner':42, 'token':'expired', 'candidate':'new'}})
    clear_pending(ctx)
    query = SimpleNamespace(data='autopost|draft_edit_save|expired',
                            from_user=SimpleNamespace(id=42), answer=AsyncMock())
    assert asyncio.run(handle_callback(SimpleNamespace(callback_query=query), ctx)) is True
    assert ctx.user_data == {'current_draft':draft}
    assert query.answer.await_args.kwargs['show_alert'] is True
