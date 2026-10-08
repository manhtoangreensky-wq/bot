import asyncio
import re
from pathlib import Path
from types import SimpleNamespace
import unittest


class MemoryEmptyDeleteStateTests(unittest.TestCase):
    def test_empty_delete_list_clears_old_memory_pending_state(self):
        source = (Path(__file__).resolve().parents[1] / 'bot.py').read_text(encoding='utf-8')
        match = re.search(
            r'(?ms)^async def handle_memory_callback\(.*?(?=^(?:async\s+)?def\s|^class\s|\Z)',
            source,
        )
        self.assertIsNotNone(match, 'memory callback handler is missing')
        pending = {'pending_action':'delete_id'}

        async def answer(*args, **kwargs): pass
        async def render(*args, **kwargs): pass

        scope = {'get_user_language':lambda uid:'vi', 'normalize_user_language':lambda x:x,
                 'memory_can_use_full':lambda uid:True, 'clear_memory_guided_pending':lambda uid:pending.clear(),
                 'memory_list_notes':lambda *a,**kw:[],
                 'memory_notes_list_text':lambda *a,**kw:'empty', 'memory_main_keyboard':lambda *a:[],
                 'memory_notes_list_keyboard':lambda *a,**kw:[], 'safe_edit_or_send':render,
                 'memory_access_message':lambda:'denied', 'main_memory_keyboard':lambda *a:[],
                 'Update':object, 'ContextTypes':SimpleNamespace(DEFAULT_TYPE=object)}
        exec(compile(match.group(0), 'bot.py:handle_memory_callback', 'exec'), scope)
        query=SimpleNamespace(answer=answer,data='memory|delete_start',from_user=SimpleNamespace(id=42))
        asyncio.run(scope['handle_memory_callback'](SimpleNamespace(callback_query=query),SimpleNamespace()))
        self.assertEqual(pending, {})
