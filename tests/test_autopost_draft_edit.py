import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

from services.autopost_draft_edit import handle_callback, handle_text
import ast
from pathlib import Path


def setup():
    draft = {'owner_user_id': 42, 'caption': 'Original', 'asset': {'id': 7}}
    context = SimpleNamespace(user_data={'current_draft': draft, 'autopost_draft_message_id': 9,
                                        'autopost_draft_chat_id': 42})
    message = SimpleNamespace(message_id=9, chat_id=42,
        reply_text=AsyncMock(return_value=SimpleNamespace(message_id=10, chat_id=42)))
    query = SimpleNamespace(data='autopost|draft_edit|0', from_user=SimpleNamespace(id=42),
                            message=message, answer=AsyncMock())
    update = SimpleNamespace(callback_query=query, message=message, effective_user=query.from_user)
    return context, update


def test_edit_preview_save_escapes_plain_text_and_preserves_asset():
    ctx, upd = setup()
    original = deepcopy(ctx.user_data['current_draft'])
    async def scenario():
        assert await handle_callback(upd, ctx)
        token = ctx.user_data['autopost_caption_edit']['token']
        upd.message.text = '<new> & content'
        assert await handle_text(upd, ctx)
        token = ctx.user_data['autopost_caption_edit']['token']
        assert ctx.user_data['current_draft'] == original
        upd.callback_query.data = 'autopost|draft_edit_save|' + token
        assert await handle_callback(upd, ctx)
        assert ctx.user_data['current_draft']['caption'] == '&lt;new&gt; &amp; content'
        assert ctx.user_data['current_draft']['asset'] == {'id': 7}
        assert 'autopost_caption_edit' not in ctx.user_data
        saved = deepcopy(ctx.user_data['current_draft'])
        await handle_callback(upd, ctx)
        assert ctx.user_data['current_draft'] == saved
    asyncio.run(scenario())


def test_cancel_and_changed_draft_never_overwrite():
    for change in [False, True]:
        ctx, upd = setup()
        async def scenario():
            await handle_callback(upd, ctx)
            token = ctx.user_data['autopost_caption_edit']['token']
            upd.message.text = 'replacement'
            await handle_text(upd, ctx)
            token = ctx.user_data['autopost_caption_edit']['token']
            if change:
                ctx.user_data['current_draft'] = {'owner_user_id':42, 'caption':'Different'}
            expected = deepcopy(ctx.user_data['current_draft'])
            action = 'draft_edit_save' if change else 'draft_edit_cancel'
            upd.callback_query.data = f'autopost|{action}|{token}'
            await handle_callback(upd, ctx)
            assert ctx.user_data['current_draft'] == expected
        asyncio.run(scenario())


def test_old_message_and_foreign_owner_do_not_open_edit():
    for mismatch in ['message', 'owner']:
        ctx, upd = setup()
        if mismatch == 'message': upd.callback_query.message.message_id = 8
        else: ctx.user_data['current_draft']['owner_user_id'] = 43
        asyncio.run(handle_callback(upd, ctx))
        assert 'autopost_caption_edit' not in ctx.user_data
        upd.message.reply_text.assert_not_awaited()


def test_real_callback_and_message_entry_reach_editor():
    source = (Path(__file__).resolve().parents[1] / 'bot.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    assignment = next(n for n in tree.body if isinstance(n, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == 'autopost_engine_code' for t in n.targets))
    scope = {'Update': object, 'ContextTypes': SimpleNamespace(DEFAULT_TYPE=object),
             'InlineKeyboardMarkup': object}
    exec(compile(ast.literal_eval(assignment.value), 'actual-callback', 'exec'), scope)
    handler = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'handle_message')
    # Exercise the actual entry through the caption handler; legacy handlers beyond it are out of scope.
    end = next(i for i,n in enumerate(handler.body) if isinstance(n, ast.If)
               and isinstance(n.test, ast.Await) and isinstance(n.test.value, ast.Call)
               and isinstance(n.test.value.func, ast.Name) and n.test.value.func.id == 'handle_caption_text')
    handler.body = handler.body[:end + 1]
    handler.decorator_list = []
    scope['handle_state_reset_slash_command'] = AsyncMock(return_value=False)
    exec(compile(ast.Module(body=[handler], type_ignores=[]), 'actual-message-entry', 'exec'), scope)
    ctx, upd = setup()
    async def run():
        await scope['handle_autopost_callback'](upd, ctx)
        token = ctx.user_data['autopost_caption_edit']['token']
        upd.message.text = 'Edited through real message handler'
        await scope['handle_message'](upd, ctx)
        token = ctx.user_data['autopost_caption_edit']['token']
        upd.callback_query.data = 'autopost|draft_edit_save|' + token
        await scope['handle_autopost_callback'](upd, ctx)
        assert ctx.user_data['current_draft']['caption'] == 'Edited through real message handler'
    asyncio.run(run())


def test_old_preview_save_cannot_save_newer_candidate():
    ctx, upd = setup()
    async def run():
        await handle_callback(upd, ctx)
        upd.message.text = 'First'
        await handle_text(upd, ctx)
        old_token = ctx.user_data['autopost_caption_edit']['token']
        upd.message.text = 'Second'
        await handle_text(upd, ctx)
        upd.callback_query.data = 'autopost|draft_edit_save|' + old_token
        await handle_callback(upd, ctx)
        assert ctx.user_data['current_draft']['caption'] == 'Original'
        assert ctx.user_data['autopost_caption_edit']['candidate'] == 'Second'
    asyncio.run(run())


def test_same_message_id_from_different_chat_cannot_open_editor():
    ctx, upd = setup()
    upd.callback_query.message.chat_id = -100999
    asyncio.run(handle_callback(upd, ctx))
    assert 'autopost_caption_edit' not in ctx.user_data


def test_other_chat_cannot_submit_or_save_edit():
    ctx, upd = setup()
    async def run():
        await handle_callback(upd, ctx)
        token = ctx.user_data['autopost_caption_edit']['token']
        upd.message.chat_id = -100999
        upd.message.text = 'wrong chat'
        assert await handle_text(upd, ctx) is False
        assert 'candidate' not in ctx.user_data['autopost_caption_edit']
        upd.callback_query.data = 'autopost|draft_edit_cancel|' + token
        await handle_callback(upd, ctx)
        assert 'autopost_caption_edit' in ctx.user_data
    asyncio.run(run())
