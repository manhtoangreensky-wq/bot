from __future__ import annotations

import ast
import asyncio
import copy
import html
import importlib
import inspect
import json
import sqlite3
import subprocess
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOT_PATH = ROOT / 'bot.py'
PUBLIC_PATH = ROOT / 'services' / 'local_video_studio_public.py'
PREVIEW_PATH = ROOT / 'services' / 'local_video_studio_preview.py'
INDEX_PATH = ROOT / 'skills' / 'video' / 'local-video-codex-index' / 'capability_index.json'

PREFIX = 'lvs27b'
STATE_KEY = 'local_video_studio27b_public'
ENTRY_LABEL = '🧭 Lập kế hoạch dựng video'
ENTRY_CALLBACK = 'lvs27b|open'
PUBLIC_READINESS = {'CONTRACT_ONLY', 'LOCAL_PLANNING_READY', 'REQUIRES_RUNTIME', 'REQUIRES_PLANNED_SHOOT', 'NOT_SUPPORTED'}
GOAL_IDS = {'cut_pacing', 'reframe', 'transition_motion', 'sound_post'}

def service():
    assert PUBLIC_PATH.is_file(), '27B public adapter is missing'
    return importlib.import_module('services.local_video_studio_public')

def canonical():
    return importlib.import_module('services.local_video_studio_preview')

def index():
    return json.loads(INDEX_PATH.read_text(encoding='utf-8'))

def apply(svc, state, callback, **kwargs):
    result = svc.apply_callback(state, callback, **kwargs)
    assert 'session' in result and 'feedback' in result
    return result

def callback(svc, state, verb, *args):
    return svc.callback_data(state['session_id'], verb, *args)

def visible_callbacks(svc, view):
    result = []
    for row in view['rows']:
        assert 1 <= len(row) <= 2
        for label, value in row:
            assert label.strip()
            assert isinstance(value, str)
            assert len(value.encode('utf-8')) <= 64
            if value.startswith(PREFIX + '|'):
                svc.parse_callback(value)
            result.append(value)
    return result


def compile_public_adapter(svc, enabled):
    source = BOT_PATH.read_text(encoding='utf-8')
    start = source.index('# --- LOCAL VIDEO STUDIO 27B PUBLIC ---')
    end = source.index('# --- END LOCAL VIDEO STUDIO 27B PUBLIC ---')

    class FakeButton:
        def __init__(self, text, callback_data):
            self.text = text
            self.callback_data = callback_data

    class FakeMarkup:
        def __init__(self, rows):
            self.inline_keyboard = rows

    namespace = {
        'InlineKeyboardButton': FakeButton,
        'InlineKeyboardMarkup': FakeMarkup,
        'Update': object,
        'ContextTypes': SimpleNamespace(DEFAULT_TYPE=object),
        'local_video_studio_public': svc,
        'local_video_studio_public_enabled': lambda: enabled['value'],
        'menu_text_main_video_i18n': lambda _lang: 'MAIN VIDEO',
        'main_video_keyboard': lambda _lang: FakeMarkup([]),
        'video_edit_hub_text': lambda _lang: 'VIDEO EDIT HUB',
        'video_edit_hub_keyboard': lambda _lang: FakeMarkup([]),
        'get_user_language': lambda _user_id: 'vi',
        'normalize_user_language': lambda _lang: 'vi',
        'time': __import__('time'),
    }
    exec(compile(source[start:end], '<lvs27b_adapter>', 'exec'), namespace)
    return namespace

def test_public_module_contract_and_isolated_state_schema():
    svc = service()
    assert svc.CALLBACK_PREFIX == PREFIX
    assert svc.STATE_KEY == STATE_KEY
    assert svc.PREVIEW_VERSION == '27B'
    assert svc.SESSION_TTL_SECONDS > 0
    state = svc.new_session('session-a', now=100)
    assert state['screen'] == 'goal'
    assert state['session_id'] == 'session-a'
    assert state['created_at'] == 100
    assert state['updated_at'] == 100
    assert state['history'] == []
    assert state['selected_ids'] == []
    assert state['processed_callback_ids'] == []
    assert svc.session_store_key(7, 8, 'session-a') == '7:8:session-a'
    assert svc.new_store() == {'sessions': {}, 'active_by_chat': {}}
    assert canonical().STATE_KEY != svc.STATE_KEY

def test_entry_view_is_vietnamese_planning_only_and_returns_to_edit_parent():
    svc = service()
    state = svc.new_session('sid001')
    view = svc.render_view(state, index())
    assert view['screen'] == 'goal'
    assert 'Đây là công cụ lập kế hoạch dựng video.' in view['text']
    assert 'Công cụ chưa tạo hoặc render video.' in view['text']
    callbacks = visible_callbacks(svc, view)
    assert callback(svc, state, 'back') in callbacks
    assert 'videoedit|hub' not in callbacks
    assert not any(value.startswith(('vproduct|', 'videodub|', 'framevideo|')) for value in callbacks)
    assert all('render' not in value.lower() for value in callbacks)

def test_flag_off_row_is_empty_and_flag_on_adds_exactly_one_secondary_action():
    svc = service()
    assert svc.public_entry_rows(False) == ()
    assert svc.public_entry_rows('0') == ()
    assert svc.public_entry_rows('invalid') == ()
    assert svc.public_entry_rows(True) == ((ENTRY_LABEL, ENTRY_CALLBACK),)
    assert svc.public_entry_rows('1') == ((ENTRY_LABEL, ENTRY_CALLBACK),)
    source = BOT_PATH.read_text(encoding='utf-8')
    assert 'LOCAL_VIDEO_STUDIO_PUBLIC_ENABLED' in source
    assert '🧭 Lên kế hoạch chỉnh sửa' in source
    assert ENTRY_CALLBACK in source
    assert source.count(ENTRY_CALLBACK) >= 1
    assert 'videoedit|ai' in source and 'videoedit|manual' in source


def test_video_edit_hub_runtime_shape_excludes_detached_status_and_planning():
    source = BOT_PATH.read_text(encoding='utf-8')
    start = source.index('def video_edit_hub_keyboard(')
    end = source.index('\ndef video_edit_info_text(', start)
    function_source = source[start:end]
    enabled = {'value': False}

    class FakeButton:
        def __init__(self, text, callback_data):
            self.text = text
            self.callback_data = callback_data

    class FakeMarkup:
        def __init__(self, rows):
            self.inline_keyboard = rows

    namespace = {
        'InlineKeyboardButton': FakeButton,
        'InlineKeyboardMarkup': FakeMarkup,
        'normalize_user_language': lambda _lang: 'vi',
        'public_video_deep_copy': lambda _lang: {
            'video_edit_ai': 'Chỉnh sửa AI',
            'video_edit_manual': 'Chỉnh sửa thủ công',
            'video_edit_restore': 'Nâng chất lượng',
            'video_edit_guide': 'Hướng dẫn',
        },
        'video_scene3_flow': importlib.import_module('services.video_scene3_flow'),
        'ui_text': lambda _lang, key: {'common.back': '⬅️ Quay lại', 'common.main_menu': '🏠 Menu chính'}[key],
        'local_video_studio_public_enabled': lambda: enabled['value'],
    }
    exec(compile(function_source, '<video_edit_hub_keyboard>', 'exec'), namespace)
    keyboard = namespace['video_edit_hub_keyboard']
    off_rows = keyboard('vi').inline_keyboard
    assert [[button.callback_data for button in row] for row in off_rows] == [
        ['videoedit|ai', 'videoedit|manual'],
        ['videoedit|restore', 'videoedit|guide'],
        ['menu|main_video', 'menu|main'],
    ]
    enabled['value'] = True
    on_rows = keyboard('vi').inline_keyboard
    assert [[button.callback_data for button in row] for row in on_rows] == [
        ['videoedit|ai', 'videoedit|manual'],
        ['videoedit|restore', 'videoedit|guide'],
        ['menu|main_video', 'menu|main'],
    ]
    callbacks = [button.callback_data for row in on_rows for button in row]
    assert 'videoedit|latest_status' not in callbacks
    assert ENTRY_CALLBACK not in callbacks

def test_canonical_index_is_reused_without_public_capability_data_copy():
    svc = service()
    canonical_service = canonical()
    assert svc.catalog_source is canonical_service
    payload = svc.load_capability_index()
    assert svc.validate_capability_index(payload)['capability_count'] == 14
    assert tuple(svc.LOCAL_RECORD_IDS) == tuple(canonical_service.LOCAL_RECORD_IDS)
    assert tuple(svc.QA_CAPABILITY_IDS) == tuple(canonical_service.QA_CAPABILITY_IDS)
    coverage = svc.capability_coverage(payload)
    assert len(coverage['local']) == 248
    assert len(coverage['all']) == 251
    assert len(coverage['qa']) == 19
    public_source = PUBLIC_PATH.read_text(encoding='utf-8')
    assert 'capability_index.json' not in public_source
    assert 'provider_router' not in public_source

def test_public_locks_readiness_and_qa_contract_fail_closed():
    svc = service()
    payload = svc.validate_capability_index(index())
    assert svc.PUBLIC_READINESS_STATES == tuple(('CONTRACT_ONLY', 'LOCAL_PLANNING_READY', 'REQUIRES_RUNTIME', 'REQUIRES_PLANNED_SHOOT', 'NOT_SUPPORTED'))
    assert svc.PLANNING_LOCKS == {
        'planning_only': True,
        'runtime_registered': False,
        'provider_executable': False,
        'public_ui': False,
    }
    for key in ('planning_only', 'runtime_registered', 'provider_executable', 'public_ui'):
        assert payload[key] in (True, False)
    assert payload['planning_only'] is True
    assert payload['runtime_registered'] is False
    assert payload['provider_executable'] is False
    assert payload['public_ui'] is False
    for record in payload['capabilities']:
        assert svc.public_readiness(record) in PUBLIC_READINESS
    broken = copy.deepcopy(payload)
    broken['capabilities'][0]['public_ui'] = True
    with pytest.raises(svc.PreviewDataError):
        svc.validate_capability_index(broken)


def test_public_record_labels_are_exact_fail_closed_and_safe_on_every_view(monkeypatch):
    svc = service()
    payload = svc.load_capability_index()
    records = {record['capability_id']: record for record in payload['capabilities']}
    assert tuple(svc.PUBLIC_RECORD_LABELS_VI) == tuple(svc.LOCAL_RECORD_IDS)
    assert len(svc.PUBLIC_RECORD_LABELS_VI) == 11

    forbidden = (
        '26c', '26d', '26e', '26f', '26g', '26h', 'đã pin',
        'version_or_sha', 'sha:', 'c:/', 'd:/', 'provider', 'debug',
    )

    def assert_public_safe(view):
        visible = '\n'.join((
            str(view['text']),
            *(str(label) for row in view['rows'] for label, _callback in row),
        ))
        lowered = visible.lower()
        for record_id in svc.LOCAL_RECORD_IDS:
            assert record_id.lower() not in lowered
            assert records[record_id]['display_name_vi'].lower() not in lowered
        assert not [term for term in forbidden if term in lowered]
        return visible

    state = svc.new_session('labels01')
    state = apply(svc, state, callback(svc, state, 'goal', 'transition_motion'))['session']
    _visible, _page, catalog_pages = svc.paginate(
        svc.LOCAL_RECORD_IDS, 0, svc.CATALOG_PAGE_SIZE
    )
    seen_labels = set()
    for page in range(catalog_pages):
        state = apply(svc, state, callback(svc, state, 'catalog', str(page)))['session']
        view = svc.render_view(state, payload)
        assert_public_safe(view)
        seen_labels.update(label for row in view['rows'] for label, _callback in row)
    assert set(svc.PUBLIC_RECORD_LABELS_VI.values()).issubset(seen_labels)

    for record_id in svc.LOCAL_RECORD_IDS:
        detail = apply(svc, state, callback(svc, state, 'detail', record_id, '0'))['session']
        detail_view = svc.render_view(detail, payload)
        detail_surface = assert_public_safe(detail_view)
        assert svc.PUBLIC_RECORD_LABELS_VI[record_id] in detail_surface
        selected = apply(
            svc,
            detail,
            callback(svc, detail, 'select', record_id, '0'),
        )['session']
        safety = apply(svc, selected, callback(svc, selected, 'safety'))['session']
        safety_surface = assert_public_safe(svc.render_view(safety, payload))
        assert svc.PUBLIC_RECORD_LABELS_VI[record_id] in safety_surface
        state = apply(svc, detail, callback(svc, detail, 'back'))['session']

    broken_labels = dict(svc.PUBLIC_RECORD_LABELS_VI)
    broken_labels.pop(svc.LOCAL_RECORD_IDS[-1])
    monkeypatch.setattr(svc, 'PUBLIC_RECORD_LABELS_VI', broken_labels)
    with pytest.raises(svc.PreviewDataError):
        svc.render_view(state, payload)

    public_source = PUBLIC_PATH.read_text(encoding='utf-8')
    assert 'openmontage.pipeline_manifests' not in public_source


def test_detail_buttons_identify_each_contract_without_exposing_group_keys():
    svc = service()
    state = svc.new_session('labels02')
    state = apply(svc, state, callback(svc, state, 'goal', 'sound_post'))['session']
    state = apply(
        svc,
        state,
        callback(svc, state, 'detail', 'sound_design_pack', '0'),
    )['session']
    labels = [label for row in svc.render_view(state)['rows'] for label, _callback in row]
    assert any('dialogue or narration' in label.lower() for label in labels)
    assert not any('sound_design_pack' in label.lower() for label in labels)

def test_forward_flow_requires_each_step_and_back_is_exact():
    svc = service()
    state = svc.new_session('sid002', now=100)
    with pytest.raises(svc.PreviewActionError):
        svc.apply_callback(state, callback(svc, state, 'catalog', '0'))
    state = apply(svc, state, svc.callback_data('', 'open'))['session']
    assert state['screen'] == 'goal'
    state = apply(svc, state, callback(svc, state, 'goal', 'cut_pacing'))['session']
    assert state['screen'] == 'catalog' and state['history'] == ['goal']
    with pytest.raises(svc.PreviewActionError):
        svc.apply_callback(state, callback(svc, state, 'summary'))
    record_id = svc.LOCAL_RECORD_IDS[0]
    state = apply(svc, state, callback(svc, state, 'detail', record_id, '0'))['session']
    assert state['screen'] == 'detail' and state['history'] == ['goal', 'catalog']
    with pytest.raises(svc.PreviewActionError):
        svc.apply_callback(state, callback(svc, state, 'safety'))
    state = apply(svc, state, callback(svc, state, 'select', record_id, '0'))['session']
    assert state['selected_ids']
    state = apply(svc, state, callback(svc, state, 'safety'))['session']
    assert state['screen'] == 'safety' and state['history'][-1] == 'detail'
    state = apply(svc, state, callback(svc, state, 'summary'))['session']
    assert state['screen'] == 'summary' and state['history'][-1] == 'safety'
    state = apply(svc, state, callback(svc, state, 'back'))['session']
    assert state['screen'] == 'safety'
    state = apply(svc, state, callback(svc, state, 'back'))['session']
    assert state['screen'] == 'detail'
    state = apply(svc, state, callback(svc, state, 'back'))['session']
    assert state['screen'] == 'catalog' and state['selected_ids'] == []
    state = apply(svc, state, callback(svc, state, 'back'))['session']
    assert state['screen'] == 'goal'
    result = apply(svc, state, callback(svc, state, 'back'))
    assert result['exit_parent'] is True

def test_all_local_groups_and_detail_pages_are_reachable_and_clamped():
    svc = service()
    payload = svc.load_capability_index()
    state = apply(svc, svc.new_session('sid003'), svc.callback_data('', 'open'))['session']
    state = apply(svc, state, callback(svc, state, 'goal', 'transition_motion'))['session']
    catalog_view = svc.render_view(state, payload)
    assert '11 nhóm' in catalog_view['text'] or '11' in catalog_view['text']
    state = apply(svc, state, callback(svc, state, 'catalog', '999'))['session']
    assert state['catalog_page'] == svc.paginate(svc.LOCAL_RECORD_IDS, 999, svc.CATALOG_PAGE_SIZE)[1]
    for record_id in svc.LOCAL_RECORD_IDS:
        detail = apply(svc, state, callback(svc, state, 'detail', record_id, '999'))['session']
        assert detail['screen'] == 'detail'
        record = next(r for r in payload['capabilities'] if r['capability_id'] == record_id)
        assert detail['detail_page'] == svc.paginate(tuple(record['capability_ids']), 999, svc.DETAIL_PAGE_SIZE)[1]
        view = svc.render_view(detail, payload)
        visible_callbacks(svc, view)
        state = apply(svc, detail, callback(svc, detail, 'back'))['session']

def test_selection_summary_contains_goal_ids_rights_and_next_step_without_private_data():
    svc = service()
    state = apply(svc, svc.new_session('sid004'), svc.callback_data('', 'open'))['session']
    state = apply(svc, state, callback(svc, state, 'goal', 'sound_post'))['session']
    record_id = 'sound_design_pack'
    state = apply(svc, state, callback(svc, state, 'detail', record_id, '0'))['session']
    state = apply(svc, state, callback(svc, state, 'select', record_id, '0'))['session']
    state = apply(svc, state, callback(svc, state, 'safety'))['session']
    state = apply(svc, state, callback(svc, state, 'summary'))['session']
    view = svc.render_view(state)
    assert view['screen'] == 'summary'
    assert state['selected_ids'][0] in view['text']
    assert 'Quyền' in view['text'] and 'Bước tiếp theo' in view['text']
    assert 'Công cụ chưa tạo hoặc render video.' in view['text']
    for forbidden in ('C:/Users', 'D:/', 'provider_task', 'secret', 'render command', 'job_id', 'Mosaic', 'Higgsfield', 'Suno'):
        assert forbidden.lower() not in view['text'].lower()
    save_callbacks = [c for c in visible_callbacks(svc, view) if '|save' in c]
    assert save_callbacks
    saved = apply(svc, state, save_callbacks[0])
    assert saved['saved_text'] and saved['session'] == state


def test_summary_save_is_semantically_idempotent_across_new_callback_ids():
    svc = service()
    state = apply(svc, svc.new_session('save-idem'), svc.callback_data('', 'open'))['session']
    state = apply(svc, state, callback(svc, state, 'goal', 'sound_post'))['session']
    state = apply(svc, state, callback(svc, state, 'detail', 'sound_design_pack', '0'))['session']
    state = apply(svc, state, callback(svc, state, 'select', 'sound_design_pack', '0'))['session']
    state = apply(svc, state, callback(svc, state, 'safety'))['session']
    state = apply(svc, state, callback(svc, state, 'summary'))['session']
    save_callback = callback(svc, state, 'save')
    base = state['updated_at']

    first = apply(svc, state, save_callback, callback_id='save-1', now=base)
    assert first['saved_text']
    assert first['saved_fingerprint']

    # A failed delivery must not reserve the summary; a retry may still send it.
    retry_before_commit = apply(svc, state, save_callback, callback_id='save-2', now=base + 1)
    assert retry_before_commit['saved_text'] == first['saved_text']

    committed = svc.commit_saved_summary_delivery(
        first['session'],
        'save-1',
        first['saved_fingerprint'],
        now=base + 2,
    )
    duplicate = apply(
        svc,
        committed,
        save_callback,
        callback_id='save-2',
        now=base + 3,
    )
    assert duplicate['duplicate'] is True
    assert duplicate['saved_text'] == ''


def test_public_adapter_replies_with_same_summary_only_once_across_new_callback_ids():
    svc = service()
    handler = compile_public_adapter(svc, {'value': True})['handle_local_video_studio_public_callback']
    state = svc.new_session('save-live')
    state = apply(svc, state, callback(svc, state, 'goal', 'sound_post'))['session']
    state = apply(svc, state, callback(svc, state, 'detail', 'sound_design_pack', '0'))['session']
    state = apply(svc, state, callback(svc, state, 'select', 'sound_design_pack', '0'))['session']
    state = apply(svc, state, callback(svc, state, 'safety'))['session']
    state = apply(svc, state, callback(svc, state, 'summary'))['session']
    store = svc.new_store()
    svc.put_session(store, 11, 22, state)
    context = SimpleNamespace(user_data={STATE_KEY: store})
    events = []

    class FakeMessage:
        chat = SimpleNamespace(id=22)
        chat_id = 22

        async def reply_text(self, text, **_kwargs):
            events.append(('reply', text))
            return True

    class FakeQuery:
        def __init__(self, query_id):
            self.id = query_id
            self.data = callback(svc, state, 'save')
            self.message = FakeMessage()
            self.bot = None

        async def edit_message_text(self, *_args, **_kwargs):
            events.append(('edit', None))
            return True

        async def answer(self, text='', **_kwargs):
            events.append(('answer', text))
            return True

    def update_for(query):
        return SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=11, language_code='vi'),
            effective_chat=SimpleNamespace(id=22),
        )

    assert asyncio.run(handler(update_for(FakeQuery('save-live-1')), context)) is True
    assert [event[0] for event in events] == ['reply', 'answer']

    events.clear()
    assert asyncio.run(handler(update_for(FakeQuery('save-live-2')), context)) is True
    assert [event[0] for event in events] == ['answer']


def _run_concurrent_open_race(svc, callback_ids):
    handler = compile_public_adapter(svc, {'value': True})['handle_local_video_studio_public_callback']
    context = SimpleNamespace(user_data={})
    edits = []
    answers = []

    async def run_race():
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        second_started = asyncio.Event()

        class FakeMessage:
            chat = SimpleNamespace(id=22)
            chat_id = 22

        class FakeQuery:
            def __init__(self, query_id, label):
                self.id = query_id
                self.data = svc.callback_data('', 'open')
                self.message = FakeMessage()
                self.bot = None
                self.label = label

            async def edit_message_text(self, *_args, **_kwargs):
                edits.append(self.label)
                if self.label == 'first':
                    first_started.set()
                    await release_first.wait()
                else:
                    second_started.set()
                return True

            async def answer(self, text='', **_kwargs):
                answers.append((self.label, text))
                return True

        def update_for(query):
            return SimpleNamespace(
                callback_query=query,
                effective_user=SimpleNamespace(id=11, language_code='vi'),
                effective_chat=SimpleNamespace(id=22),
            )

        first = asyncio.create_task(handler(
            update_for(FakeQuery(callback_ids[0], 'first')),
            context,
        ))
        await first_started.wait()
        second = asyncio.create_task(handler(
            update_for(FakeQuery(callback_ids[1], 'second')),
            context,
        ))
        second_entered_while_first_pending = False
        try:
            await asyncio.wait_for(second_started.wait(), timeout=0.1)
            second_entered_while_first_pending = True
        except asyncio.TimeoutError:
            pass
        release_first.set()
        assert await first is True
        assert await second is True
        return second_entered_while_first_pending

    entered_early = asyncio.run(run_race())
    store = context.user_data[STATE_KEY]
    return entered_early, edits, answers, store


def test_public_adapter_serializes_same_callback_concurrent_open_once():
    svc = service()
    entered_early, edits, answers, store = _run_concurrent_open_race(
        svc,
        ('open-race-same', 'open-race-same'),
    )

    assert entered_early is False
    assert edits == ['first']
    assert len(store['sessions']) == 1
    assert any(label == 'second' and 'đã được nhận' in text for label, text in answers)


def test_public_adapter_serializes_distinct_concurrent_opens_without_store_loss():
    svc = service()
    entered_early, edits, _answers, store = _run_concurrent_open_race(
        svc,
        ('open-race-1', 'open-race-2'),
    )

    assert entered_early is False
    assert edits == ['first', 'second']
    assert len(store['sessions']) == 2


def test_public_adapter_serializes_concurrent_summary_saves():
    svc = service()
    handler = compile_public_adapter(svc, {'value': True})['handle_local_video_studio_public_callback']
    state = svc.new_session('save-race')
    state = apply(svc, state, callback(svc, state, 'goal', 'sound_post'))['session']
    state = apply(svc, state, callback(svc, state, 'detail', 'sound_design_pack', '0'))['session']
    state = apply(svc, state, callback(svc, state, 'select', 'sound_design_pack', '0'))['session']
    state = apply(svc, state, callback(svc, state, 'safety'))['session']
    state = apply(svc, state, callback(svc, state, 'summary'))['session']
    store = svc.new_store()
    svc.put_session(store, 11, 22, state)
    context = SimpleNamespace(user_data={STATE_KEY: store})
    replies = []

    async def run_race():
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        second_started = asyncio.Event()

        class FakeMessage:
            chat = SimpleNamespace(id=22)
            chat_id = 22

            def __init__(self, label):
                self.label = label

            async def reply_text(self, _text, **_kwargs):
                replies.append(self.label)
                if self.label == 'first':
                    first_started.set()
                    await release_first.wait()
                else:
                    second_started.set()
                return True

        class FakeQuery:
            def __init__(self, query_id, label):
                self.id = query_id
                self.data = callback(svc, state, 'save')
                self.message = FakeMessage(label)
                self.bot = None

            async def edit_message_text(self, *_args, **_kwargs):
                return True

            async def answer(self, _text='', **_kwargs):
                return True

        def update_for(query):
            return SimpleNamespace(
                callback_query=query,
                effective_user=SimpleNamespace(id=11, language_code='vi'),
                effective_chat=SimpleNamespace(id=22),
            )

        first = asyncio.create_task(handler(update_for(FakeQuery('save-race-1', 'first')), context))
        await first_started.wait()
        second = asyncio.create_task(handler(update_for(FakeQuery('save-race-2', 'second')), context))
        second_entered_while_first_pending = False
        try:
            await asyncio.wait_for(second_started.wait(), timeout=0.1)
            second_entered_while_first_pending = True
        except asyncio.TimeoutError:
            pass
        release_first.set()
        assert await first is True
        assert await second is True
        return second_entered_while_first_pending

    assert asyncio.run(run_race()) is False
    assert replies == ['first']


def test_public_adapter_serializes_summary_save_and_back_without_stale_resurrection():
    svc = service()
    handler = compile_public_adapter(svc, {'value': True})['handle_local_video_studio_public_callback']
    state = svc.new_session('save-back')
    state = apply(svc, state, callback(svc, state, 'goal', 'sound_post'))['session']
    state = apply(svc, state, callback(svc, state, 'detail', 'sound_design_pack', '0'))['session']
    state = apply(svc, state, callback(svc, state, 'select', 'sound_design_pack', '0'))['session']
    state = apply(svc, state, callback(svc, state, 'safety'))['session']
    state = apply(svc, state, callback(svc, state, 'summary'))['session']
    store = svc.new_store()
    svc.put_session(store, 11, 22, state)
    context = SimpleNamespace(user_data={STATE_KEY: store})

    async def run_race():
        save_started = asyncio.Event()
        release_save = asyncio.Event()
        back_edited = asyncio.Event()

        class FakeMessage:
            chat = SimpleNamespace(id=22)
            chat_id = 22

            def __init__(self, label):
                self.label = label

            async def reply_text(self, _text, **_kwargs):
                if self.label == 'save':
                    save_started.set()
                    await release_save.wait()
                return True

        class FakeQuery:
            def __init__(self, query_id, data, label):
                self.id = query_id
                self.data = data
                self.message = FakeMessage(label)
                self.bot = None
                self.label = label

            async def edit_message_text(self, *_args, **_kwargs):
                if self.label == 'back':
                    back_edited.set()
                return True

            async def answer(self, _text='', **_kwargs):
                return True

        def update_for(query):
            return SimpleNamespace(
                callback_query=query,
                effective_user=SimpleNamespace(id=11, language_code='vi'),
                effective_chat=SimpleNamespace(id=22),
            )

        save_task = asyncio.create_task(handler(update_for(FakeQuery(
            'save-back-1', callback(svc, state, 'save'), 'save'
        )), context))
        await save_started.wait()
        back_task = asyncio.create_task(handler(update_for(FakeQuery(
            'save-back-2', callback(svc, state, 'back'), 'back'
        )), context))
        back_entered_while_save_pending = False
        try:
            await asyncio.wait_for(back_edited.wait(), timeout=0.1)
            back_entered_while_save_pending = True
        except asyncio.TimeoutError:
            pass
        release_save.set()
        assert await save_task is True
        assert await back_task is True
        return back_entered_while_save_pending

    assert asyncio.run(run_race()) is False
    final = svc.get_session(store, 11, 22, state['session_id'])
    assert final is not None
    assert final['screen'] == 'safety'
    assert final['saved_summary_fingerprint']


def test_public_adapter_failed_summary_delivery_does_not_block_successful_retry():
    svc = service()
    handler = compile_public_adapter(svc, {'value': True})['handle_local_video_studio_public_callback']
    state = svc.new_session('save-retry')
    state = apply(svc, state, callback(svc, state, 'goal', 'sound_post'))['session']
    state = apply(svc, state, callback(svc, state, 'detail', 'sound_design_pack', '0'))['session']
    state = apply(svc, state, callback(svc, state, 'select', 'sound_design_pack', '0'))['session']
    state = apply(svc, state, callback(svc, state, 'safety'))['session']
    state = apply(svc, state, callback(svc, state, 'summary'))['session']
    store = svc.new_store()
    svc.put_session(store, 11, 22, state)
    context = SimpleNamespace(user_data={STATE_KEY: store})
    replies = []

    class FakeMessage:
        chat = SimpleNamespace(id=22)
        chat_id = 22

        def __init__(self, fail):
            self.fail = fail

        async def reply_text(self, _text, **_kwargs):
            replies.append(self.fail)
            if self.fail:
                raise RuntimeError('reply failed')
            return True

    class FakeQuery:
        def __init__(self, query_id, fail):
            self.id = query_id
            self.data = callback(svc, state, 'save')
            self.message = FakeMessage(fail)
            self.bot = None

        async def edit_message_text(self, *_args, **_kwargs):
            return True

        async def answer(self, _text='', **_kwargs):
            return True

    def update_for(query):
        return SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=11, language_code='vi'),
            effective_chat=SimpleNamespace(id=22),
        )

    assert asyncio.run(handler(update_for(FakeQuery('save-retry-1', True)), context)) is False
    after_failure = svc.get_session(store, 11, 22, state['session_id'])
    assert after_failure is not None
    assert after_failure['saved_summary_fingerprint'] == ''
    assert 'save-retry-1' not in after_failure['processed_callback_ids']

    assert asyncio.run(handler(update_for(FakeQuery('save-retry-2', False)), context)) is True
    after_retry = svc.get_session(store, 11, 22, state['session_id'])
    assert after_retry is not None and after_retry['saved_summary_fingerprint']
    assert replies == [True, False]


def test_legacy_summary_session_migrates_and_malformed_fingerprint_fails_closed():
    svc = service()
    legacy = svc.new_session('legacy27b')
    legacy.pop('saved_summary_fingerprint')
    assert svc.normalize_session(legacy)['saved_summary_fingerprint'] == ''

    malformed = svc.new_session('bad-hash')
    malformed['saved_summary_fingerprint'] = 'not-a-sha256'
    with pytest.raises(svc.PreviewActionError, match='fingerprint_invalid'):
        svc.normalize_session(malformed)


def test_public_copy_is_vietnamese_and_hides_runtime_delivery_telemetry():
    svc = service()
    assert dict(svc.GOAL_OPTIONS) == {
        'cut_pacing': '✂️ Cắt dựng và nhịp',
        'reframe': '🎯 Điều chỉnh khung hình và bố cục',
        'transition_motion': '✨ Chuyển cảnh và đồ họa chuyển động',
        'sound_post': '🎧 Âm thanh và hậu kỳ',
    }
    state = svc.new_session('copy001')
    state = apply(svc, state, callback(svc, state, 'goal', 'sound_post'))['session']
    record_id = 'sound_design_pack'
    state = apply(svc, state, callback(svc, state, 'detail', record_id, '0'))['session']
    state = apply(svc, state, callback(svc, state, 'select', record_id, '0'))['session']
    state = apply(svc, state, callback(svc, state, 'safety'))['session']
    state = apply(svc, state, callback(svc, state, 'summary'))['session']
    text = svc.render_view(state)['text']
    assert 'Đây là công cụ lập kế hoạch dựng video.' in text
    assert 'Công cụ chưa tạo hoặc render video.' in text
    for forbidden in (
        'task runtime', 'blocker runtime', 'media deliveries', 'delivery',
        'credit mutations', 'execution calls', 'execution lock',
        'production changes', 'infrastructure changes', 'invoice', 'status',
        'rights evidence', 'planning summary · local video studio',
    ):
        assert forbidden not in text.lower()

def test_malformed_stale_deleted_and_cross_namespace_callbacks_fail_closed():
    svc = service()
    state = svc.new_session('sid005', now=100)
    original = copy.deepcopy(state)
    for value in ('lvs27a|open', 'menu|main', 'lvs27b', 'lvs27b|bad|open', 'lvs27b|sid005|unknown'):
        with pytest.raises(svc.PreviewActionError):
            svc.apply_callback(state, value, now=100)
        assert state == original
    with pytest.raises(svc.PreviewActionError):
        svc.apply_callback(state, svc.callback_data('other', 'goal', 'cut_pacing'), now=100)
    with pytest.raises(svc.PreviewActionError):
        svc.apply_callback(state, svc.callback_data('sid005', 'goal', 'cut_pacing'), now=100 + svc.SESSION_TTL_SECONDS + 1)
    with pytest.raises(svc.PreviewActionError):
        svc.normalize_session(None)
    extra = copy.deepcopy(state)
    extra['unexpected'] = True
    with pytest.raises(svc.PreviewActionError):
        svc.normalize_session(extra)
    reversed_time = copy.deepcopy(state)
    reversed_time['updated_at'] = 99
    with pytest.raises(svc.PreviewActionError):
        svc.normalize_session(reversed_time)


def test_negative_and_high_pages_clamp_and_stale_store_does_not_resurrect():
    svc = service()
    state = svc.new_session('sid009', now=100)
    state = apply(svc, state, callback(svc, state, 'goal', 'reframe'), now=100)['session']
    state = apply(svc, state, callback(svc, state, 'catalog', '-1'), now=100)['session']
    assert state['catalog_page'] == 0
    state['catalog_page'] = 999
    assert svc.normalize_session(state)['catalog_page'] == svc.paginate(
        svc.LOCAL_RECORD_IDS, 999, svc.CATALOG_PAGE_SIZE
    )[1]
    store = svc.new_store()
    svc.put_session(store, 7, 8, state)
    store['active_by_chat']['7:8'] = state['session_id']
    assert svc.get_session(store, 7, 8, state['session_id'], now=100 + svc.SESSION_TTL_SECONDS + 1) is None
    assert store['sessions'] == {}
    assert store['active_by_chat'] == {}


def test_store_prune_removes_all_stale_malformed_and_dangling_state():
    svc = service()
    now = 50_000
    store = svc.new_store()
    for index_value in range(100):
        sid = f'stale{index_value:03d}'
        state = svc.new_session(sid, now=now - svc.SESSION_TTL_SECONDS - 1)
        owner_id = index_value + 1
        store['sessions'][svc.session_store_key(owner_id, owner_id, sid)] = state
        store['active_by_chat'][f'{owner_id}:{owner_id}'] = sid

    malformed = svc.new_session('malformed', now=now)
    malformed['unexpected'] = True
    store['sessions'][svc.session_store_key(90_001, 90_001, 'malformed')] = malformed
    store['active_by_chat']['90001:90001'] = 'malformed'

    shared_sid = 'shared01'
    first = svc.new_session(shared_sid, now=now)
    second = svc.new_session(shared_sid, now=now)
    first_key = svc.session_store_key(101, 201, shared_sid)
    second_key = svc.session_store_key(102, 202, shared_sid)
    store['sessions'][first_key] = first
    store['sessions'][second_key] = second
    store['active_by_chat']['101:201'] = shared_sid
    store['active_by_chat']['102:202'] = shared_sid
    store['active_by_chat']['101:202'] = shared_sid

    assert svc.store_has_callback_id(store, 'not-seen', now=now) is False
    assert set(store['sessions']) == {first_key, second_key}
    assert store['active_by_chat'] == {
        '101:201': shared_sid,
        '102:202': shared_sid,
    }


def test_store_cap_keeps_latest_session_retrievable():
    svc = service()
    assert svc.MAX_STORED_SESSIONS == 32
    store = svc.new_store()
    base = 80_000
    newest = None
    for index_value in range(svc.MAX_STORED_SESSIONS + 12):
        sid = f'valid{index_value:03d}'
        newest = svc.new_session(sid, now=base + index_value)
        svc.put_session(store, 700, 800 + index_value, newest)
        assert len(store['sessions']) <= svc.MAX_STORED_SESSIONS
    assert newest is not None
    assert svc.get_session(
        store,
        700,
        800 + svc.MAX_STORED_SESSIONS + 11,
        newest['session_id'],
        now=base + svc.MAX_STORED_SESSIONS + 11,
    ) == newest


def test_selection_limit_rejects_twenty_fifth_without_mutation_across_pages():
    svc = service()
    assert svc.MAX_SELECTED_CAPABILITIES == 24
    record_id = 'transition_motion_pack'
    state = svc.new_session('select24')
    state = apply(svc, state, callback(svc, state, 'goal', 'transition_motion'))['session']
    state = apply(svc, state, callback(svc, state, 'detail', record_id, '0'))['session']
    for index_value in range(svc.MAX_SELECTED_CAPABILITIES):
        page = index_value // svc.DETAIL_PAGE_SIZE
        state = apply(
            svc,
            state,
            callback(svc, state, 'detail', record_id, str(page)),
        )['session']
        state = apply(
            svc,
            state,
            callback(svc, state, 'select', record_id, str(index_value)),
        )['session']
    assert len(state['selected_ids']) == svc.MAX_SELECTED_CAPABILITIES

    original = copy.deepcopy(state)
    with pytest.raises(svc.PreviewActionError, match='selection_limit'):
        svc.apply_callback(
            state,
            callback(svc, state, 'select', record_id, str(svc.MAX_SELECTED_CAPABILITIES)),
        )
    assert state == original

    duplicate = apply(
        svc,
        state,
        callback(svc, state, 'select', record_id, '0'),
    )
    assert duplicate['session'] == original
    assert len(duplicate['session']['selected_ids']) == svc.MAX_SELECTED_CAPABILITIES

def test_duplicate_callback_id_is_idempotent_and_commit_marks_only_after_success():
    svc = service()
    state = svc.new_session('sid006', now=100)
    open_result = svc.apply_callback(state, svc.callback_data('', 'open'), now=100, callback_id='q-open')
    opened = open_result['session']
    committed = svc.commit_callback_id(opened, 'q-open', now=101)
    duplicate = svc.apply_callback(committed, svc.callback_data(committed['session_id'], 'goal', 'cut_pacing'), now=101, callback_id='q-goal')
    next_state = svc.commit_callback_id(duplicate['session'], 'q-goal', now=102)
    again = svc.apply_callback(next_state, svc.callback_data(next_state['session_id'], 'goal', 'cut_pacing'), now=102, callback_id='q-goal')
    assert again['duplicate'] is True
    assert again['session'] == next_state

def test_deliver_then_commit_orders_edit_fallback_commit_and_answer():
    svc = service()
    events = []
    async def edit_ok():
        events.append('edit')
        return True
    async def reply_never():
        events.append('reply')
        return True
    def commit():
        events.append('commit')
    async def answer():
        events.append('answer')
    assert asyncio.run(svc.deliver_then_commit(edit_ok, reply_never, commit, answer)) is True
    assert events == ['edit', 'commit', 'answer']
    events.clear()
    async def edit_fail():
        events.append('edit')
        raise RuntimeError('edit failed')
    assert asyncio.run(svc.deliver_then_commit(edit_fail, reply_never, commit, answer)) is True
    assert events == ['edit', 'reply', 'commit', 'answer']
    events.clear()
    async def reply_fail():
        events.append('reply')
        raise RuntimeError('reply failed')
    assert asyncio.run(svc.deliver_then_commit(edit_fail, reply_fail, commit, answer)) is False
    assert events == ['edit', 'reply']


def test_fake_public_adapter_transactions_sessions_duplicate_and_root_back(monkeypatch):
    svc = service()
    source = BOT_PATH.read_text(encoding='utf-8')
    start = source.index('# --- LOCAL VIDEO STUDIO 27B PUBLIC ---')
    end = source.index('# --- END LOCAL VIDEO STUDIO 27B PUBLIC ---')
    public_block = source[start:end]

    class FakeButton:
        def __init__(self, text, callback_data):
            self.text = text
            self.callback_data = callback_data

    class FakeMarkup:
        def __init__(self, rows):
            self.inline_keyboard = rows

    namespace = {
        'InlineKeyboardButton': FakeButton,
        'InlineKeyboardMarkup': FakeMarkup,
        'Update': object,
        'ContextTypes': SimpleNamespace(DEFAULT_TYPE=object),
        'local_video_studio_public': svc,
        'local_video_studio_public_enabled': lambda: True,
        'menu_text_main_video_i18n': lambda _lang: 'MAIN VIDEO',
        'main_video_keyboard': lambda _lang: FakeMarkup([]),
        'video_edit_hub_text': lambda _lang: 'VIDEO EDIT HUB',
        'video_edit_hub_keyboard': lambda _lang: FakeMarkup([]),
        'get_user_language': lambda _user_id: 'vi',
        'normalize_user_language': lambda _lang: 'vi',
        'time': __import__('time'),
    }
    exec(compile(public_block, '<lvs27b_adapter>', 'exec'), namespace)
    handler = namespace['handle_local_video_studio_public_callback']

    events = []
    original_put = svc.put_session
    original_delete = svc.delete_session

    def tracked_put(*args, **kwargs):
        events.append('commit')
        return original_put(*args, **kwargs)

    def tracked_delete(*args, **kwargs):
        events.append('delete')
        return original_delete(*args, **kwargs)

    monkeypatch.setattr(svc, 'put_session', tracked_put)
    monkeypatch.setattr(svc, 'delete_session', tracked_delete)

    class FakeMessage:
        def __init__(self, *, fail_reply=False):
            self.chat = SimpleNamespace(id=22)
            self.chat_id = 22
            self.fail_reply = fail_reply

        async def reply_text(self, _text, **_kwargs):
            events.append('reply')
            if self.fail_reply:
                raise RuntimeError('reply failed')
            return object()

    class FakeQuery:
        def __init__(self, query_id, data, *, fail_edit=False, fail_reply=False):
            self.id = query_id
            self.data = data
            self.fail_edit = fail_edit
            self.message = FakeMessage(fail_reply=fail_reply)
            self.bot = None

        async def edit_message_text(self, _text, **_kwargs):
            events.append('edit')
            if self.fail_edit:
                raise RuntimeError('edit failed')
            return object()

        async def answer(self, _text='', **_kwargs):
            events.append('answer')
            return True

    def update_for(query, *, user_id=11):
        return SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=user_id, language_code='vi') if user_id else None,
            effective_chat=SimpleNamespace(id=22),
        )

    context = SimpleNamespace(user_data={})
    first = FakeQuery('q-open-1', ENTRY_CALLBACK)
    assert asyncio.run(handler(update_for(first), context)) is True
    assert events == ['edit', 'commit', 'answer']
    store = context.user_data[STATE_KEY]
    assert len(store['sessions']) == 1
    first_state = next(iter(store['sessions'].values()))
    first_sid = first_state['session_id']

    events.clear()
    duplicate = FakeQuery('q-open-1', ENTRY_CALLBACK)
    asyncio.run(handler(update_for(duplicate), context))
    assert events == ['answer']
    assert len(store['sessions']) == 1

    events.clear()
    second = FakeQuery('q-open-2', ENTRY_CALLBACK)
    asyncio.run(handler(update_for(second), context))
    assert events == ['edit', 'commit', 'answer']
    assert len(store['sessions']) == 2

    events.clear()
    root_back = FakeQuery('q-back-1', svc.callback_data(first_sid, 'back'))
    asyncio.run(handler(update_for(root_back), context))
    assert events == ['edit', 'delete', 'answer']
    assert len(store['sessions']) == 1

    events.clear()
    fallback_context = SimpleNamespace(user_data={})
    fallback = FakeQuery('q-open-fallback', ENTRY_CALLBACK, fail_edit=True)
    asyncio.run(handler(update_for(fallback), fallback_context))
    assert events == ['edit', 'reply', 'commit', 'answer']
    assert STATE_KEY in fallback_context.user_data

    events.clear()
    failed_context = SimpleNamespace(user_data={})
    failed = FakeQuery('q-open-failed', ENTRY_CALLBACK, fail_edit=True, fail_reply=True)
    assert asyncio.run(handler(update_for(failed), failed_context)) is False
    assert events == ['edit', 'reply']
    assert STATE_KEY not in failed_context.user_data

    events.clear()
    identity_invalid_context = SimpleNamespace(user_data={})
    identity_invalid = FakeQuery('q-identity-invalid', ENTRY_CALLBACK)
    asyncio.run(handler(update_for(identity_invalid, user_id=0), identity_invalid_context))
    assert events == ['answer']
    assert STATE_KEY not in identity_invalid_context.user_data


def test_corrupt_canonical_index_alerts_safely_without_state_mutation(monkeypatch):
    svc = service()
    enabled = {'value': True}
    handler = compile_public_adapter(svc, enabled)['handle_local_video_studio_public_callback']
    store = svc.new_store()
    state = svc.new_session('corrupt1')
    svc.put_session(store, 11, 22, state)
    context = SimpleNamespace(user_data={STATE_KEY: store})
    before = json.dumps(context.user_data, ensure_ascii=False, separators=(',', ':'))
    operations = []
    original_put = svc.put_session
    original_delete = svc.delete_session

    def tracked_put(*args, **kwargs):
        operations.append('commit')
        return original_put(*args, **kwargs)

    def tracked_delete(*args, **kwargs):
        operations.append('delete')
        return original_delete(*args, **kwargs)

    monkeypatch.setattr(svc, 'put_session', tracked_put)
    monkeypatch.setattr(svc, 'delete_session', tracked_delete)

    class FakeQuery:
        id = 'q-corrupt'
        data = svc.callback_data(state['session_id'], 'goal', 'cut_pacing')
        message = SimpleNamespace(chat=SimpleNamespace(id=22), chat_id=22)

        async def edit_message_text(self, *_args, **_kwargs):
            operations.append('edit')
            return True

        async def answer(self, text='', **kwargs):
            operations.append(('answer', text, kwargs))
            return True

    update = SimpleNamespace(
        callback_query=FakeQuery(),
        effective_user=SimpleNamespace(id=11, language_code='vi'),
        effective_chat=SimpleNamespace(id=22),
    )

    def corrupt_index():
        raise svc.PreviewDataError('canonical_index_corrupt')

    monkeypatch.setattr(svc, 'load_capability_index', corrupt_index)
    assert asyncio.run(handler(update, context)) is True
    assert len(operations) == 1 and operations[0][0] == 'answer'
    assert operations[0][2].get('show_alert') is True
    assert json.dumps(context.user_data, ensure_ascii=False, separators=(',', ':')) == before

    operations.clear()

    def unexpected_failure():
        raise RuntimeError('unexpected programmer error')

    monkeypatch.setattr(svc, 'load_capability_index', unexpected_failure)
    with pytest.raises(RuntimeError, match='unexpected programmer error'):
        asyncio.run(handler(update, context))
    assert operations == []
    assert json.dumps(context.user_data, ensure_ascii=False, separators=(',', ':')) == before


def test_flag_off_mid_session_allows_back_and_close_but_denies_forward(monkeypatch):
    svc = service()
    enabled = {'value': True}
    handler = compile_public_adapter(svc, enabled)['handle_local_video_studio_public_callback']
    events = []
    original_delete = svc.delete_session

    def tracked_delete(*args, **kwargs):
        events.append('delete')
        return original_delete(*args, **kwargs)

    monkeypatch.setattr(svc, 'delete_session', tracked_delete)

    class FakeMessage:
        def __init__(self, *, fail_reply=False):
            self.chat = SimpleNamespace(id=22)
            self.chat_id = 22
            self.fail_reply = fail_reply

        async def reply_text(self, text, **kwargs):
            events.append(('reply', text, kwargs))
            if self.fail_reply:
                raise RuntimeError('reply failed')
            return True

    class FakeQuery:
        def __init__(self, query_id, data, *, fail_edit=False, fail_reply=False):
            self.id = query_id
            self.data = data
            self.fail_edit = fail_edit
            self.message = FakeMessage(fail_reply=fail_reply)
            self.bot = None

        async def edit_message_text(self, text, **kwargs):
            events.append(('edit', text, kwargs))
            if self.fail_edit:
                raise RuntimeError('edit failed')
            return True

        async def answer(self, text='', **kwargs):
            events.append(('answer', text, kwargs))
            return True

    def update_for(query):
        return SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=11, language_code='vi'),
            effective_chat=SimpleNamespace(id=22),
        )

    def open_session(context, query_id):
        enabled['value'] = True
        assert asyncio.run(handler(update_for(FakeQuery(query_id, ENTRY_CALLBACK)), context)) is True
        store = context.user_data[STATE_KEY]
        return next(reversed(store['sessions'].values()))

    context = SimpleNamespace(user_data={})
    opened = open_session(context, 'q-open-flag-back')
    events.clear()
    next_step = FakeQuery(
        'q-next-after-open',
        svc.callback_data(opened['session_id'], 'goal', 'cut_pacing'),
    )
    assert asyncio.run(handler(update_for(next_step), context)) is True
    assert [event[0] if isinstance(event, tuple) else event for event in events] == [
        'edit', 'answer'
    ]
    opened = svc.get_session(
        context.user_data[STATE_KEY], 11, 22, opened['session_id']
    )
    assert opened is not None and opened['screen'] == 'catalog'

    events.clear()
    enabled['value'] = False
    before = copy.deepcopy(context.user_data)
    forward = FakeQuery(
        'q-forward-off',
        svc.callback_data(opened['session_id'], 'catalog', '1'),
    )
    assert asyncio.run(handler(update_for(forward), context)) is True
    assert len(events) == 1 and events[0][0] == 'answer'
    assert events[0][2].get('show_alert') is True
    assert context.user_data == before

    events.clear()
    back = FakeQuery('q-back-off', svc.callback_data(opened['session_id'], 'back'))
    assert asyncio.run(handler(update_for(back), context)) is True
    assert events[0][0:2] == ('edit', 'MAIN VIDEO')
    assert events[1:] == [
        'delete',
        ('answer', 'Đã quay lại Menu Video.', {}),
    ]
    assert STATE_KEY not in context.user_data

    close_context = SimpleNamespace(user_data={})
    opened = open_session(close_context, 'q-open-flag-close')
    events.clear()
    enabled['value'] = False
    close = FakeQuery('q-close-off', svc.callback_data(opened['session_id'], 'close'))
    assert asyncio.run(handler(update_for(close), close_context)) is True
    assert events[0][0] == 'edit' and 'Đã đóng bản lập kế hoạch' in events[0][1]
    assert events[1:] == ['delete', ('answer', 'Đã đóng bản lập kế hoạch.', {})]
    assert STATE_KEY not in close_context.user_data

    failed_context = SimpleNamespace(user_data={})
    opened = open_session(failed_context, 'q-open-flag-failed-back')
    events.clear()
    enabled['value'] = False
    failed_back = FakeQuery(
        'q-failed-back-off',
        svc.callback_data(opened['session_id'], 'back'),
        fail_edit=True,
        fail_reply=True,
    )
    assert asyncio.run(handler(update_for(failed_back), failed_context)) is False
    assert [event[0] for event in events] == ['edit', 'reply']
    assert STATE_KEY in failed_context.user_data

    events.clear()
    off_context = SimpleNamespace(user_data={})
    assert asyncio.run(handler(update_for(FakeQuery('q-open-off', ENTRY_CALLBACK)), off_context)) is True
    assert len(events) == 1 and events[0][0] == 'answer'
    assert STATE_KEY not in off_context.user_data


def test_existing_dispatch_guards_precede_and_stop_lvs27b_without_duplicate_auth():
    source = BOT_PATH.read_text(encoding='utf-8')
    throttle_registration = 'CallbackQueryHandler(dispatch_throttle_callback_guard), group=-11)'
    safe_mode_registration = 'CallbackQueryHandler(safe_mode_callback_guard), group=-10)'
    public_registration = (
        'CallbackQueryHandler(handle_local_video_studio_public_callback, pattern=r"^lvs27b\\|")'
    )
    assert source.index(throttle_registration) < source.index(safe_mode_registration)
    assert source.index(safe_mode_registration) < source.index(public_registration)

    block_start = source.index('# --- LOCAL VIDEO STUDIO 27B PUBLIC ---')
    block_end = source.index('# --- END LOCAL VIDEO STUDIO 27B PUBLIC ---')
    public_block = source[block_start:block_end].lower()
    assert 'is_banned' not in public_block
    assert 'blocked_user' not in public_block
    assert 'unauthorized' not in public_block

    guard_start = source.index('async def dispatch_throttle_callback_guard(')
    guard_end = source.index('\n\nasync def safe_mode_message_guard(', guard_start)
    guard_source = source[guard_start:guard_end]
    calls = []

    class HandlerStop(Exception):
        pass

    namespace = {
        'Update': object,
        'ContextTypes': SimpleNamespace(DEFAULT_TYPE=object),
        'dispatch_throttle_allow': lambda _user_id: False,
        'DISPATCH_THROTTLE_TEXT_VI': 'rate limited',
        'ApplicationHandlerStop': HandlerStop,
        'logger': SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    }
    exec(compile(guard_source, '<dispatch_throttle_callback_guard>', 'exec'), namespace)

    class FakeQuery:
        from_user = SimpleNamespace(id=11)

        async def answer(self, text):
            calls.append(('guard_answer', text))

    update = SimpleNamespace(callback_query=FakeQuery())

    async def public_handler():
        calls.append(('lvs27b_handler', None))

    async def dispatch_in_group_order():
        try:
            await namespace['dispatch_throttle_callback_guard'](update, SimpleNamespace())
            await public_handler()
        except HandlerStop:
            return

    asyncio.run(dispatch_in_group_order())
    assert calls == [('guard_answer', 'rate limited')]

def test_bot_integration_is_narrow_and_keeps_27a_separate():
    source = BOT_PATH.read_text(encoding='utf-8')
    start = source.index('# --- LOCAL VIDEO STUDIO 27B PUBLIC ---')
    end = source.index('# --- END LOCAL VIDEO STUDIO 27B PUBLIC ---')
    public_block = source[start:end]
    tree = ast.parse(textwrap.dedent(public_block))
    names = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert 'handle_local_video_studio_public_callback' in names
    assert 'local_video_studio_public_keyboard' in names
    assert 'pattern=r"^lvs27a\\|"' in source
    assert 'pattern=r"^lvs27b\\|"' in source
    assert 'from services import local_video_studio_preview' in source
    assert 'LOCAL_VIDEO_STUDIO_PUBLIC_ENABLED' in source
    assert 'CallbackQueryHandler(handle_local_video_studio_public_callback' in source
    assert 'getattr(context, "user_data", None)' in public_block
    assert 'local_video_studio_preview.STATE_KEY' not in public_block


def test_pr589_receipt_truth_source_and_test_are_untouched_by_27b():
    merge_base = subprocess.run(
        ['git', 'merge-base', 'HEAD', 'origin/main'],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert merge_base
    diff = subprocess.run(
        ['git', 'diff', '--unified=0', merge_base, '--', 'bot.py'],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    for protected_symbol in (
        'subdub_merge_debug_job',
        'subdub_admin_debug_chunks',
        'mark_subtitle_dub_pipeline_output_sent',
        'subdub_input_save_debug_fields',
        'execute_video_dubbing_pipeline',
    ):
        assert protected_symbol not in diff
    test_diff = subprocess.run(
        ['git', 'diff', '--exit-code', merge_base, '--', 'tests/test_p0_subdub_production_receipt_truth.py'],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert test_diff.returncode == 0 and not test_diff.stdout and not test_diff.stderr
    source = BOT_PATH.read_text(encoding='utf-8')
    for accepted_receipt_lock in (
        'SUBDUB_LARGE_MEDIA_DETECTED_THRESHOLD_BYTES = 50 * 1024 * 1024',
        'or file_size > SUBDUB_LARGE_MEDIA_DETECTED_THRESHOLD_BYTES',
        'delivered_video_receipt = bool(',
        'for chunk in subdub_admin_debug_chunks(text):',
        'input_save_fields = subdub_input_save_debug_fields(input_save, result_state or state)',
        'job["final_mp4_exists"] = True',
    ):
        assert accepted_receipt_lock in source

def test_public_adapter_has_no_runtime_or_secret_path():
    source = PUBLIC_PATH.read_text(encoding='utf-8').lower()
    forbidden = ('requests', 'httpx', 'subprocess', 'telegram', 'provider_router', 'worker', 'payos', 'wallet', 'xu', 'ffmpeg', 'send_video', 'send_document', 'download')
    assert not [word for word in forbidden if word in source]
    assert 'planning_only' in source and 'provider_executable' in source and 'public_ui' in source
    assert 'runtime_registered' in source
    assert inspect.iscoroutinefunction(service().deliver_then_commit)


# Option C adapter contract.  The capability adapter above remains as legacy
# evidence, while the public bot route is now owned by video_planning_assistant.
def planning_service():
    return importlib.import_module('services.video_planning_assistant')


def planning_store_module():
    return importlib.import_module('services.local_video_planning_store')


def planning_summary_session(svc, session_id='plan001'):
    state = svc.new_session(session_id, now=int(time.time()))

    def choose(verb, *args):
        nonlocal state
        state = svc.apply_callback(
            state,
            svc.callback_data(state['session_id'], verb, *args),
        )['session']

    choose('goal', 'cut_pacing')
    state = svc.apply_text_input(
        state,
        'Video bán hàng cần nhanh, sáng, rõ lời nói và logo không che sản phẩm.',
    )['session']
    choose('platform', 'tiktok_9x16')
    choose('source', '60_120')
    choose('target', '30')
    choose('asset', 'video')
    choose('asset', 'logo')
    choose('assets_done')
    choose('priority', 'pace')
    choose('priority', 'product_focus')
    choose('priorities_done')
    choose('operations_done')
    choose('safety_done')
    assert state['screen'] == 'summary'
    return state


class PlanningStoreProbe:
    def __init__(self, module, events):
        self._module = module
        self._events = events

    def __getattr__(self, name):
        return getattr(self._module, name)

    def save_plan_from_session(self, *args, **kwargs):
        saved = self._module.save_plan_from_session(*args, **kwargs)
        self._events.append(('persist', saved['plan_key'], saved['version']))
        return saved

    def soft_delete_plan(self, *args, **kwargs):
        deleted = self._module.soft_delete_plan(*args, **kwargs)
        self._events.append(('delete_commit', kwargs.get('plan_key'), deleted))
        return deleted


class PlanningFakeButton:
    def __init__(self, text, callback_data):
        self.text = text
        self.callback_data = callback_data


class PlanningFakeMarkup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class PlanningFakeMessage:
    def __init__(self, events, *, chat_id=70, fail_reply=False):
        self.events = events
        self.chat_id = chat_id
        self.chat = SimpleNamespace(id=chat_id)
        self.fail_reply = fail_reply
        self.replies = []

    async def reply_text(self, text, **kwargs):
        if self.fail_reply:
            self.events.append(('reply_failed', text))
            raise RuntimeError('reply failed')
        self.events.append(('reply', text))
        self.replies.append((text, kwargs.get('reply_markup')))
        return True


class PlanningFakeQuery:
    def __init__(self, data, callback_id, events, *, chat_id=70, fail_edit=False, fail_reply=False):
        self.data = data
        self.id = callback_id
        self.events = events
        self.message = PlanningFakeMessage(events, chat_id=chat_id, fail_reply=fail_reply)
        self.fail_edit = fail_edit
        self.edits = []
        self.answers = []

    async def edit_message_text(self, text, **kwargs):
        if self.fail_edit:
            self.events.append(('edit_failed', text))
            raise RuntimeError('edit failed')
        self.events.append(('edit', text))
        self.edits.append((text, kwargs.get('reply_markup')))
        return True

    async def answer(self, text='', **kwargs):
        self.events.append(('answer', text))
        self.answers.append((text, kwargs))
        return True


def compile_option_c_adapter(db_path, events, enabled=None):
    source = BOT_PATH.read_text(encoding='utf-8')
    start = source.index('# --- LOCAL VIDEO STUDIO 27B PUBLIC ---')
    end = source.index('# --- END LOCAL VIDEO STUDIO 27B PUBLIC ---')
    svc = planning_service()
    store = planning_store_module()
    enabled = enabled if isinstance(enabled, dict) else {'value': True}
    namespace = {
        'InlineKeyboardButton': PlanningFakeButton,
        'InlineKeyboardMarkup': PlanningFakeMarkup,
        'Update': object,
        'ContextTypes': SimpleNamespace(DEFAULT_TYPE=object),
        'local_video_studio_public': svc,
        'local_video_planning_store': PlanningStoreProbe(store, events),
        'local_video_studio_public_enabled': lambda: enabled['value'],
        '_planning_enabled': enabled,
        'menu_text_main_video_i18n': lambda _lang: 'MAIN VIDEO',
        'main_video_keyboard': lambda _lang: PlanningFakeMarkup([]),
        'get_user_language': lambda _user_id: 'vi',
        'normalize_user_language': lambda _lang: 'vi',
        'db_connect': lambda: sqlite3.connect(str(db_path)),
        'copy': copy,
        'html': html,
        'sqlite3': sqlite3,
        'time': time,
    }
    exec(compile(source[start:end], '<option_c_adapter>', 'exec'), namespace)
    return namespace


def planning_update(query=None, *, user_id=7, chat_id=70, message=None):
    return SimpleNamespace(
        callback_query=query,
        message=message,
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=chat_id),
    )


def planning_context_with_session(svc, state, *, user_id=7, chat_id=70):
    store = svc.new_store()
    svc.put_session(store, str(user_id), str(chat_id), state)
    return SimpleNamespace(user_data={svc.STATE_KEY: store, 'video_edit_sentinel': {'unchanged': True}})


def markup_callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_option_c_bot_wiring_uses_new_service_schema_and_public_route_copy():
    source = BOT_PATH.read_text(encoding='utf-8')
    assert 'from services import video_planning_assistant as local_video_studio_public' in source
    assert 'from services import local_video_planning_store' in source
    init_start = source.index('def init_db():')
    init_end = source.index('\ndef now_text():', init_start)
    init_source = source[init_start:init_end]
    assert 'local_video_planning_store.ensure_schema(conn)' in init_source
    public_start = source.index('# --- LOCAL VIDEO STUDIO 27B PUBLIC ---')
    public_end = source.index('# --- END LOCAL VIDEO STUDIO 27B PUBLIC ---')
    public_source = source[public_start:public_end]
    assert 'conn.row_factory = sqlite3.Row' in public_source
    route_start = source.index('"video_edit_planning": {')
    route_end = source.index('\n    "video_guide": {', route_start)
    route_source = source[route_start:route_end]
    assert '"label_vi": "🧭 Lên kế hoạch chỉnh sửa"' in route_source
    assert '"invoice_reachable": False' in route_source
    assert '"job_reachable": False' in route_source
    assert source.count('CallbackQueryHandler(handle_local_video_studio_public_callback, pattern=r"^lvs27b\\|")') == 1


def test_option_c_persist_precedes_success_copy_and_failed_confirmation_is_idempotent(tmp_path):
    svc = planning_service()
    store = planning_store_module()
    db_path = tmp_path / 'plans.sqlite3'
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        store.ensure_schema(conn)
    state = planning_summary_session(svc)
    context = planning_context_with_session(svc, state)
    callback = svc.callback_data(state['session_id'], 'persist')

    failed_events = []
    failed_ns = compile_option_c_adapter(db_path, failed_events)
    failed_query = PlanningFakeQuery(
        callback,
        'persist-failed',
        failed_events,
        fail_edit=True,
        fail_reply=True,
    )
    assert asyncio.run(failed_ns['handle_local_video_studio_public_callback'](
        planning_update(failed_query), context,
    )) is False
    assert failed_events and failed_events[0][0] == 'persist'
    assert not any('Đã lưu' in event[1] for event in failed_events if event[0] in {'edit', 'reply'})
    with sqlite3.connect(db_path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM local_video_plans').fetchone()[0] == 1

    retry_events = []
    retry_ns = compile_option_c_adapter(db_path, retry_events)
    retry_query = PlanningFakeQuery(callback, 'persist-retry', retry_events)
    assert asyncio.run(retry_ns['handle_local_video_studio_public_callback'](
        planning_update(retry_query), context,
    )) is True
    assert retry_events[0][0] == 'persist'
    assert retry_events[0][1:] == failed_events[0][1:]
    assert retry_events[1][0] == 'edit' and 'Đã lưu' in retry_events[1][1]
    with sqlite3.connect(db_path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM local_video_plans').fetchone()[0] == 1


def test_option_c_library_view_and_confirmed_delete_are_owner_chat_scoped(tmp_path):
    svc = planning_service()
    store = planning_store_module()
    db_path = tmp_path / 'plans.sqlite3'
    state = planning_summary_session(svc, 'plan002')
    foreign_owner_state = planning_summary_session(svc, 'plan003')
    foreign_chat_state = planning_summary_session(svc, 'plan005')
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        store.ensure_schema(conn)
        saved = store.save_plan_from_session(
            conn,
            owner_id='7',
            chat_id='70',
            source_session_id=state['session_id'],
            plan=svc.serialize_plan(state),
            summary_text=svc.planning_summary_text(state),
        )
        foreign_owner_saved = store.save_plan_from_session(
            conn,
            owner_id='8',
            chat_id='70',
            source_session_id=foreign_owner_state['session_id'],
            plan=svc.serialize_plan(foreign_owner_state),
            summary_text=svc.planning_summary_text(foreign_owner_state),
        )
        foreign_chat_saved = store.save_plan_from_session(
            conn,
            owner_id='7',
            chat_id='71',
            source_session_id=foreign_chat_state['session_id'],
            plan=svc.serialize_plan(foreign_chat_state),
            summary_text=svc.planning_summary_text(foreign_chat_state),
        )
    plan_key = saved['plan_key']
    events = []
    namespace = compile_option_c_adapter(db_path, events)
    context = planning_context_with_session(svc, state)
    handler = namespace['handle_local_video_studio_public_callback']

    list_query = PlanningFakeQuery(svc.callback_data(state['session_id'], 'plans'), 'plans-1', events)
    assert asyncio.run(handler(planning_update(list_query), context)) is True
    listed_callbacks = markup_callbacks(list_query.edits[-1][1])
    assert svc.callback_data(state['session_id'], 'view', plan_key) in listed_callbacks
    assert not any(foreign_owner_saved['plan_key'] in callback for callback in listed_callbacks)
    assert not any(foreign_chat_saved['plan_key'] in callback for callback in listed_callbacks)

    view_query = PlanningFakeQuery(
        svc.callback_data(state['session_id'], 'view', plan_key),
        'view-owner',
        events,
    )
    assert asyncio.run(handler(planning_update(view_query), context)) is True
    assert saved['summary_text'] in view_query.edits[-1][0]
    owner_view_callbacks = markup_callbacks(view_query.edits[-1][1])
    assert svc.callback_data(state['session_id'], 'edit', plan_key) in owner_view_callbacks
    assert svc.callback_data(state['session_id'], 'delete', plan_key) in owner_view_callbacks
    assert svc.callback_data(state['session_id'], 'library') in owner_view_callbacks

    library_back_query = PlanningFakeQuery(
        svc.callback_data(state['session_id'], 'library'),
        'library-back',
        events,
    )
    assert asyncio.run(handler(planning_update(library_back_query), context)) is True
    assert svc.callback_data(state['session_id'], 'view', plan_key) in markup_callbacks(library_back_query.edits[-1][1])
    current_callback = svc.callback_data(state['session_id'], 'current')
    assert current_callback in markup_callbacks(library_back_query.edits[-1][1])
    current_query = PlanningFakeQuery(current_callback, 'library-current', events)
    assert asyncio.run(handler(planning_update(current_query), context)) is True
    assert 'KẾ HOẠCH CHỈNH SỬA' in current_query.edits[-1][0]

    edit_query = PlanningFakeQuery(
        svc.callback_data(state['session_id'], 'edit', plan_key),
        'edit-owner',
        events,
    )
    assert asyncio.run(handler(planning_update(edit_query), context)) is True
    reopened = svc.get_session(context.user_data[svc.STATE_KEY], '7', '70', state['session_id'])
    assert reopened['screen'] == 'summary' and reopened['plan_id'] == plan_key

    for callback_id, verb, args in (
        ('edit-back-safety', 'back', ()),
        ('edit-back-operations', 'back', ()),
        ('edit-toggle-watermark', 'op', ('watermark',)),
        ('edit-operations-done', 'operations_done', ()),
        ('edit-safety-done', 'safety_done', ()),
        ('edit-persist', 'persist', ()),
    ):
        current = svc.get_session(context.user_data[svc.STATE_KEY], '7', '70', state['session_id'])
        query = PlanningFakeQuery(
            svc.callback_data(current['session_id'], verb, *args),
            callback_id,
            events,
        )
        assert asyncio.run(handler(planning_update(query), context)) is True
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        updated_saved = store.get_plan(conn, owner_id='7', chat_id='70', plan_key=plan_key)
        assert updated_saved['version'] == 2
        assert 'watermark' in updated_saved['plan']['selected_operations']
        assert conn.execute(
            "SELECT COUNT(*) FROM local_video_plans WHERE owner_id='7' AND chat_id='70' AND deleted_at=''"
        ).fetchone()[0] == 1

    foreign_context = planning_context_with_session(svc, foreign_owner_state, user_id=8, chat_id=70)
    foreign_query = PlanningFakeQuery(
        svc.callback_data(foreign_owner_state['session_id'], 'view', plan_key),
        'view-foreign',
        events,
    )
    asyncio.run(handler(planning_update(foreign_query, user_id=8), foreign_context))
    assert not foreign_query.edits

    foreign_chat_context = planning_context_with_session(svc, foreign_chat_state, user_id=7, chat_id=71)
    foreign_chat_query = PlanningFakeQuery(
        svc.callback_data(foreign_chat_state['session_id'], 'view', plan_key),
        'view-foreign-chat',
        events,
        chat_id=71,
    )
    asyncio.run(handler(planning_update(foreign_chat_query, user_id=7, chat_id=71), foreign_chat_context))
    assert not foreign_chat_query.edits
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        assert store.get_plan(conn, owner_id='7', chat_id='70', plan_key=plan_key) is not None

    delete_query = PlanningFakeQuery(
        svc.callback_data(state['session_id'], 'delete', plan_key),
        'delete-ask',
        events,
    )
    assert asyncio.run(handler(planning_update(delete_query), context)) is True
    assert svc.callback_data(state['session_id'], 'delete_confirm', plan_key) in markup_callbacks(delete_query.edits[-1][1])
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        assert store.get_plan(conn, owner_id='7', chat_id='70', plan_key=plan_key) is not None

    failed_delete_events_start = len(events)
    failed_confirm_query = PlanningFakeQuery(
        svc.callback_data(state['session_id'], 'delete_confirm', plan_key),
        'delete-confirm-failed',
        events,
        fail_edit=True,
        fail_reply=True,
    )
    assert asyncio.run(handler(planning_update(failed_confirm_query), context)) is False
    assert not any(event[0] == 'delete_commit' for event in events[failed_delete_events_start:])
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        assert store.get_plan(conn, owner_id='7', chat_id='70', plan_key=plan_key) is not None

    success_events_start = len(events)
    confirm_query = PlanningFakeQuery(
        svc.callback_data(state['session_id'], 'delete_confirm', plan_key),
        'delete-confirm',
        events,
    )
    assert asyncio.run(handler(planning_update(confirm_query), context)) is True
    success_events = events[success_events_start:]
    assert next(i for i, event in enumerate(success_events) if event[0] == 'edit') < next(
        i for i, event in enumerate(success_events) if event[0] == 'delete_commit'
    )
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        assert store.get_plan(conn, owner_id='7', chat_id='70', plan_key=plan_key) is None
    active_sid = context.user_data[svc.STATE_KEY]['active_by_chat']['7:70']
    assert active_sid == state['session_id']
    after_delete = svc.get_session(context.user_data[svc.STATE_KEY], '7', '70', active_sid)
    assert after_delete['plan_id'] == ''

    current_after_delete = PlanningFakeQuery(
        svc.callback_data(active_sid, 'current'),
        'current-after-delete',
        events,
    )
    assert asyncio.run(handler(planning_update(current_after_delete), context)) is True
    save_again = PlanningFakeQuery(
        svc.callback_data(active_sid, 'persist'),
        'save-after-delete',
        events,
    )
    assert asyncio.run(handler(planning_update(save_again), context)) is True
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        assert len(store.list_plans(conn, owner_id='7', chat_id='70')) == 1


def test_option_c_pending_brief_is_exact_session_scoped_and_precedes_generic_routing(tmp_path):
    svc = planning_service()
    events = []
    namespace = compile_option_c_adapter(tmp_path / 'plans.sqlite3', events)
    assert 'handle_local_video_planning_pending_text' in namespace
    state = svc.new_session('plan004')
    context = planning_context_with_session(svc, state)
    goal_query = PlanningFakeQuery(
        svc.callback_data(state['session_id'], 'goal', 'cut_pacing'),
        'goal-1',
        events,
    )
    handler = namespace['handle_local_video_studio_public_callback']
    assert asyncio.run(handler(planning_update(goal_query), context)) is True
    stored = svc.get_session(context.user_data[svc.STATE_KEY], '7', '70', state['session_id'])
    assert stored['screen'] == 'brief'

    other_message = PlanningFakeMessage(events, chat_id=71)
    other_message.text = 'Không được lấy nhầm chat này.'
    assert asyncio.run(namespace['handle_local_video_planning_pending_text'](
        planning_update(user_id=7, chat_id=71, message=other_message), context,
    )) is False
    assert svc.get_session(context.user_data[svc.STATE_KEY], '7', '70', state['session_id'])['screen'] == 'brief'

    other_user_message = PlanningFakeMessage(events, chat_id=70)
    other_user_message.text = 'Không được lấy nhầm người dùng này.'
    assert asyncio.run(namespace['handle_local_video_planning_pending_text'](
        planning_update(user_id=8, chat_id=70, message=other_user_message), context,
    )) is False
    assert svc.get_session(context.user_data[svc.STATE_KEY], '7', '70', state['session_id'])['screen'] == 'brief'

    namespace['_planning_enabled']['value'] = False
    disabled_message = PlanningFakeMessage(events, chat_id=70)
    disabled_message.text = 'Không được nhận nội dung khi tính năng đang tắt.'
    assert asyncio.run(namespace['handle_local_video_planning_pending_text'](
        planning_update(user_id=7, chat_id=70, message=disabled_message), context,
    )) is True
    disabled_state = svc.get_session(context.user_data[svc.STATE_KEY], '7', '70', state['session_id'])
    assert disabled_state['screen'] == 'brief' and disabled_state['editing_brief'] == ''
    namespace['_planning_enabled']['value'] = True

    message = PlanningFakeMessage(events, chat_id=70)
    message.text = 'Giữ đoạn 00:08–00:28, tăng sáng nhẹ và logo không che sản phẩm.'
    assert asyncio.run(namespace['handle_local_video_planning_pending_text'](
        planning_update(user_id=7, chat_id=70, message=message), context,
    )) is True
    updated = svc.get_session(context.user_data[svc.STATE_KEY], '7', '70', state['session_id'])
    assert updated['screen'] == 'platform'
    assert updated['editing_brief'] == message.text
    assert context.user_data['video_edit_sentinel'] == {'unchanged': True}

    source = BOT_PATH.read_text(encoding='utf-8')
    start = source.index('async def handle_message(')
    end = source.index('\n    normalized_music_command', start)
    message_source = source[start:end]
    planning_index = message_source.index('handle_local_video_planning_pending_text')
    assert message_source.index('get_video_editor_pending') < planning_index
    assert message_source.index('handle_manual_topup_pending_text') < planning_index
    assert planning_index < message_source.index('handle_video_product_pending_text')
    assert planning_index < message_source.index('handle_aichat_message')


def test_option_c_expired_pending_brief_is_released_even_when_feature_is_off(tmp_path):
    svc = planning_service()
    events = []
    enabled = {'value': False}
    namespace = compile_option_c_adapter(tmp_path / 'plans.sqlite3', events, enabled=enabled)
    state = svc.new_session('plan006')
    state = svc.apply_callback(
        state,
        svc.callback_data(state['session_id'], 'goal', 'cut_pacing'),
    )['session']
    context = planning_context_with_session(svc, state)
    marker_key = namespace['_LOCAL_VIDEO_PLANNING_PENDING_KEY']
    context.user_data[marker_key] = {
        'user_id': '7',
        'chat_id': '70',
        'session_id': state['session_id'],
        'expires_at': int(time.time()) - 1,
    }
    message = PlanningFakeMessage(events, chat_id=70)
    message.text = 'Tin nhắn này không còn thuộc phiên planner.'

    consumed = asyncio.run(namespace['handle_local_video_planning_pending_text'](
        planning_update(user_id=7, chat_id=70, message=message), context,
    ))

    assert consumed is False
    assert marker_key not in context.user_data
    assert not message.replies


def test_deleting_opened_plan_then_saving_never_overwrites_another_source_plan(tmp_path):
    svc = planning_service()
    store = planning_store_module()
    db_path = tmp_path / 'plans.sqlite3'
    state_a = planning_summary_session(svc, 'plan101')
    state_a['editing_brief'] = 'Nội dung riêng của kế hoạch A.'
    state_a = svc.normalize_session(state_a)
    state_b = planning_summary_session(svc, 'plan102')
    state_b['editing_brief'] = 'Nội dung riêng của kế hoạch B.'
    state_b = svc.normalize_session(state_b)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        store.ensure_schema(conn)
        saved_a = store.save_plan_from_session(
            conn,
            owner_id='7',
            chat_id='70',
            source_session_id=state_a['session_id'],
            plan=svc.serialize_plan(state_a),
            summary_text=svc.planning_summary_text(state_a),
        )
        saved_b = store.save_plan_from_session(
            conn,
            owner_id='7',
            chat_id='70',
            source_session_id=state_b['session_id'],
            plan=svc.serialize_plan(state_b),
            summary_text=svc.planning_summary_text(state_b),
        )

    events = []
    namespace = compile_option_c_adapter(db_path, events)
    context = planning_context_with_session(svc, state_a)
    handler = namespace['handle_local_video_studio_public_callback']

    edit_query = PlanningFakeQuery(
        svc.callback_data(state_a['session_id'], 'edit', saved_b['plan_key']),
        'identity-edit-b',
        events,
    )
    assert asyncio.run(handler(planning_update(edit_query), context)) is True
    delete_query = PlanningFakeQuery(
        svc.callback_data(state_a['session_id'], 'delete_confirm', saved_b['plan_key']),
        'identity-delete-b',
        events,
    )
    assert asyncio.run(handler(planning_update(delete_query), context)) is True

    active_sid = context.user_data[svc.STATE_KEY]['active_by_chat']['7:70']
    persist_query = PlanningFakeQuery(
        svc.callback_data(active_sid, 'persist'),
        'identity-save-detached-b',
        events,
    )
    assert asyncio.run(handler(planning_update(persist_query), context)) is True

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        preserved_a = store.get_plan(
            conn, owner_id='7', chat_id='70', plan_key=saved_a['plan_key']
        )
        active = store.list_plans(conn, owner_id='7', chat_id='70')
    assert preserved_a['plan']['editing_brief'] == state_a['editing_brief']
    assert len(active) == 2
    assert any(item['plan']['editing_brief'] == state_b['editing_brief'] for item in active)


def test_delete_commit_failure_keeps_the_existing_session_and_callbacks_usable(tmp_path):
    svc = planning_service()
    store = planning_store_module()
    db_path = tmp_path / 'plans.sqlite3'
    state = planning_summary_session(svc, 'plan201')
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        store.ensure_schema(conn)
        saved = store.save_plan_from_session(
            conn,
            owner_id='7',
            chat_id='70',
            source_session_id=state['session_id'],
            plan=svc.serialize_plan(state),
            summary_text=svc.planning_summary_text(state),
        )
    events = []
    namespace = compile_option_c_adapter(db_path, events)
    context = planning_context_with_session(svc, state)
    handler = namespace['handle_local_video_studio_public_callback']
    edit_query = PlanningFakeQuery(
        svc.callback_data(state['session_id'], 'edit', saved['plan_key']),
        'delete-failure-edit',
        events,
    )
    assert asyncio.run(handler(planning_update(edit_query), context)) is True

    def fail_delete(*_args, **_kwargs):
        raise sqlite3.OperationalError('forced delete failure')

    namespace['local_video_planning_store'].soft_delete_plan = fail_delete
    delete_query = PlanningFakeQuery(
        svc.callback_data(state['session_id'], 'delete_confirm', saved['plan_key']),
        'delete-failure-confirm',
        events,
    )
    assert asyncio.run(handler(planning_update(delete_query), context)) is False

    active_sid = context.user_data[svc.STATE_KEY]['active_by_chat']['7:70']
    assert active_sid == state['session_id']
    retained = svc.get_session(context.user_data[svc.STATE_KEY], '7', '70', active_sid)
    assert retained['plan_id'] == saved['plan_key']
    assert all(callback.startswith(f"lvs27b|{active_sid}|") for callback in markup_callbacks(delete_query.edits[-1][1]))


def test_deleting_another_plan_preserves_current_plan_optimistic_version(tmp_path):
    svc = planning_service()
    store = planning_store_module()
    db_path = tmp_path / 'plans.sqlite3'
    state_a = planning_summary_session(svc, 'plan301')
    state_b = planning_summary_session(svc, 'plan302')
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        store.ensure_schema(conn)
        saved_a = store.save_plan_from_session(
            conn,
            owner_id='7', chat_id='70', source_session_id=state_a['session_id'],
            plan=svc.serialize_plan(state_a), summary_text=svc.planning_summary_text(state_a),
        )
        saved_b = store.save_plan_from_session(
            conn,
            owner_id='7', chat_id='70', source_session_id=state_b['session_id'],
            plan=svc.serialize_plan(state_b), summary_text=svc.planning_summary_text(state_b),
        )
    events = []
    namespace = compile_option_c_adapter(db_path, events)
    context = planning_context_with_session(svc, state_a)
    handler = namespace['handle_local_video_studio_public_callback']
    edit_a = PlanningFakeQuery(
        svc.callback_data(state_a['session_id'], 'edit', saved_a['plan_key']),
        'version-edit-a', events,
    )
    assert asyncio.run(handler(planning_update(edit_a), context)) is True
    delete_b = PlanningFakeQuery(
        svc.callback_data(state_a['session_id'], 'delete_confirm', saved_b['plan_key']),
        'version-delete-b', events,
    )
    assert asyncio.run(handler(planning_update(delete_b), context)) is True
    persist_a = PlanningFakeQuery(
        svc.callback_data(state_a['session_id'], 'persist'),
        'version-persist-a', events,
    )
    assert asyncio.run(handler(planning_update(persist_a), context)) is True
    assert persist_a.edits and 'Đã lưu kế hoạch' in persist_a.edits[-1][0]
