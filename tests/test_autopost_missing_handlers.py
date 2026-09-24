import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace


def test_unimplemented_buttons_do_not_fall_through_to_hub():
    source = (Path(__file__).resolve().parents[1] / 'bot.py').read_text(encoding='utf-8')
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'autopost_engine_code' for t in n.targets))
    captured = []
    alerts = []
    async def edit(query, text, **kwargs): captured.append(str(text))
    scope = {'Update': object, 'ContextTypes': SimpleNamespace(DEFAULT_TYPE=object),
             'InlineKeyboardMarkup': lambda rows: rows,
             'InlineKeyboardButton': lambda *a, **kw: None,
             'get_user_language': lambda uid:'vi', 'public_hub_copy': lambda lang:{'main_menu':'Home'},
             'safe_edit_query_message': edit}
    engine = ast.literal_eval(node.value)
    for n in ast.walk(ast.parse(engine)):
        if isinstance(n, ast.Name) and n.id.startswith('autopost_'):
            scope[n.id] = lambda *a, **kw:'rendered'
    exec(compile(engine, 'actual-autopost-handler', 'exec'), scope)
    async def run():
        for action in ('draft_rewrite', 'brand_logo_prompt', 'draft_change_aff'):
            context = SimpleNamespace(user_data={'current_draft': {'caption':'keep'}})
            async def answer(*a, **k): alerts.append((a,k))
            query = SimpleNamespace(answer=answer, from_user=SimpleNamespace(id=42),
                                    data=f'autopost|{action}|0')
            await scope['handle_autopost_callback'](SimpleNamespace(callback_query=query), context)
            assert context.user_data['current_draft']['caption'] == 'keep'
    asyncio.run(run())
    assert captured == [], 'Unavailable action must leave the current screen untouched'
    assert len(alerts) == 3
    assert all('chưa khả dụng' in args[0].lower() and kwargs.get('show_alert') is True
               for args, kwargs in alerts)


def test_no_top_level_function_outside_autopost_changed():
    import subprocess
    root = Path(__file__).resolve().parents[1]
    original = subprocess.check_output(['git', 'show', 'e99226ff:bot.py'], cwd=root).decode('utf-8')
    current = (root / 'bot.py').read_text(encoding='utf-8')
    def functions(source):
        return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(source).body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    old, new = functions(original), functions(current)
    assert {k for k in old if old[k] != new.get(k)} == {
        'handle_message', 'cmd_start', 'handle_menu_callback', 'handle_doc_tool_callback'}
    # Only the explicit caption-input seam and draft message binding may differ.
    import difflib
    changed = list(difflib.unified_diff(original.splitlines(), current.splitlines(), n=0))
    assert not any(line.startswith(('+', '-')) and any(term in line for term in
                   ('def video_', 'def subdub_', 'def music_', 'def voice_')) for line in changed)
    old_nodes = {n.name:n for n in ast.parse(original).body if isinstance(n, ast.AsyncFunctionDef)}
    new_nodes = {n.name:n for n in ast.parse(current).body if isinstance(n, ast.AsyncFunctionDef)}
    doc = new_nodes['handle_doc_tool_callback']
    back = next(n for n in doc.body if isinstance(n, ast.If)
                and ast.unparse(n.test) == "action == 'back_received'")
    assert [ast.unparse(n) for n in back.body[:2]] == [
        "state['awaiting_page_spec'] = '0'", 'USER_PENDING[doc_tool_pending_key(uid)] = state']
    back.body = back.body[2:]
    assert ast.dump(doc, include_attributes=False) == ast.dump(
        old_nodes['handle_doc_tool_callback'], include_attributes=False)
    # For shared menu/start handlers, the entire original body must survive verbatim
    # as AST after exactly the two-line AutoPost cleanup seam.
    for name in ('cmd_start', 'handle_menu_callback'):
        node = new_nodes[name]
        assert isinstance(node.body[0], ast.ImportFrom)
        assert node.body[0].module == 'services.autopost_draft_edit'
        assert isinstance(node.body[1], ast.Expr)
        assert ast.unparse(node.body[1]) == 'clear_autopost_pending(context)'
        assert [ast.dump(n, include_attributes=False) for n in node.body[2:]] == [
            ast.dump(n, include_attributes=False) for n in old_nodes[name].body]
