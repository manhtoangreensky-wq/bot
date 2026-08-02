from __future__ import annotations

import ast
import asyncio
import copy
import importlib
import inspect
import json
import subprocess
import textwrap
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
STATUS_LABEL = '📊 Trạng thái chỉnh sửa'
STATUS_CALLBACK = 'videoedit|latest_status'
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
    assert ENTRY_LABEL in source
    assert ENTRY_CALLBACK in source
    assert source.count(ENTRY_CALLBACK) == 1
    assert 'videoedit|ai' in source and 'videoedit|manual' in source


def test_video_edit_hub_runtime_shape_keeps_status_between_primary_actions_and_optional_planning():
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
        [STATUS_CALLBACK],
        ['menu|main_video', 'menu|main'],
    ]
    enabled['value'] = True
    on_rows = keyboard('vi').inline_keyboard
    assert [[button.callback_data for button in row] for row in on_rows[:2]] == [
        ['videoedit|ai', 'videoedit|manual'],
        ['videoedit|restore', 'videoedit|guide'],
    ]
    assert [(button.text, button.callback_data) for button in on_rows[2]] == [(STATUS_LABEL, STATUS_CALLBACK)]
    assert [(button.text, button.callback_data) for button in on_rows[3]] == [(ENTRY_LABEL, ENTRY_CALLBACK)]
    assert [button.callback_data for button in on_rows[4]] == ['menu|main_video', 'menu|main']

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
    assert events[0][0:2] == ('edit', 'VIDEO EDIT HUB')
    assert events[1:] == [
        'delete',
        ('answer', 'Đã quay lại Chỉnh sửa video.', {}),
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
