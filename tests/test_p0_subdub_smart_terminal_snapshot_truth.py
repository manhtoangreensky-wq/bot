import ast
from pathlib import Path
from types import SimpleNamespace
import textwrap
import os

import pytest


SOURCE = Path(__file__).resolve().parents[1] / 'bot.py'


def _failure(state, product, artifacts, latest=None):
    source = SOURCE.read_text(encoding='utf-8-sig')
    start = source.index('    def _failed_product_result(', source.index('async def _execute_video_dubbing_pipeline_core('))
    end = source.index('    if str(product_result.get("status")', start)
    ns = {
        'state': state, 'product_result': product, 'workspace_artifacts': artifacts,
        'route_attempts': {}, 'render_debug': {}, 'mode': 'subtitle_plus_dub',
        'uid': 123, 'chat_id': 456, 'input_save': {}, 'gate_matrix': {}, 'os': os,
        'VIDEO_SUBTITLE_MODE_TRANSLATE': 'translate', 'SUBDUB_PUBLIC_AUDIO_FALLBACK_ENABLED': False,
        'sanitize_log_text': str, 'subdub_video_requires_final_mp4': lambda *_a: True,
        'subdub_product_type_from_mode': lambda *_a: 'subtitle_plus_dub',
        'subtitle_dub_debug_job_payload': lambda **kwargs: {**kwargs['state'], 'progress_percent': 5},
        'auto_smart_multivoice': SimpleNamespace(is_auto_smart_multivoice_state=lambda s: s.get('auto_speaker_lane')=='auto_smart_multivoice'),
        'get_engine_async_job': lambda _id: dict(latest or {}),
        'subdub_progress_percent_for_lifecycle': lambda stage, *_a: {'generating_voice':65,'validating_output':90,'delivering':95}.get(stage,5),
        'SUBDUB_PROGRESS_STAGES': {'generating_voice':(65,), 'validating_output':(90,), 'delivering':(95,)},
    }
    exec(compile(textwrap.dedent(source[start:end]), 'actual_failure_boundary', 'exec'), ns)
    return ns['_failed_product_result']('FAILED', 'safe failure', 'auto_exact_price_missing', stage='pricing')


def _state():
    return {'auto_speaker_lane':'auto_smart_multivoice','_pipeline_job_id':'same-job','user_id':123,
            'progress_percent':5, 'charge_status':'not_charged'}


def test_pricing_failure_preserves_validated_artifact_and_counts(tmp_path):
    final=tmp_path/'final.mp4'
    final.write_bytes(b'metadata-fixture-not-render-proof')
    state={**_state(), '_subdub_output_validation':{'ok':True}}
    product={'state':{'auto_smart_multivoice_verified':True,'auto_distinct_voice_count':5,
                      'auto_detected_speaker_count':5, 'translation_needs_review':True}}
    result=_failure(state,product,{'final_mp4':str(final)})
    job=result['debug_job']
    assert job['last_error_stage']=='pricing'
    assert job['progress_percent']==90
    assert job['last_completed_step']=='validating_output'
    assert job['progress_stage']=='validating_output'
    assert job['current_stage']=='validating_output'
    assert job['final_mp4_validated'] is True
    assert job['final_mp4_delivered'] is False
    assert job['auto_distinct_voice_count']==5
    assert job['translation_needs_review'] is True
    assert result['state']['auto_distinct_voice_count']==5
    assert result['ok'] is False
    assert job['charge_status']=='not_charged'


def test_same_job_progress_does_not_rewind_to_five():
    latest={'job_id':'same-job','user_id':123,'progress_stage':'generating_voice',
            'progress_percent':65,'last_completed_step':'translating'}
    result=_failure(_state(),{}, {},latest)
    assert result['debug_job']['progress_percent']==65
    assert result['debug_job']['progress_stage']=='generating_voice'
    assert result['debug_job']['last_completed_step']=='translating'
    assert result['debug_job']['final_mp4_validated'] is False


@pytest.mark.parametrize('latest', [
    {'job_id':'other-job','user_id':123,'progress_stage':'delivering','progress_percent':95},
    {'job_id':'same-job','user_id':999,'progress_stage':'delivering','progress_percent':95},
    {'job_id':'same-job','user_id':123,'progress_stage':'delivered','progress_percent':100},
])
def test_foreign_or_delivered_snapshot_cannot_create_fake_failure_progress(latest):
    result=_failure(_state(),{}, {},latest)
    assert result['debug_job']['progress_percent']==5
    assert result['debug_job']['final_mp4_validated'] is False


def test_validation_flag_without_real_artifact_cannot_create_output_proof():
    state={**_state(),'_subdub_output_validation':{'ok':True}}
    result=_failure(state,{}, {'final_mp4':'missing.mp4'})
    assert result['debug_job']['progress_percent']==5
    assert result['debug_job']['final_mp4_validated'] is False


def test_legacy_failure_snapshot_is_unchanged(tmp_path):
    state={**_state(),'auto_speaker_lane':'auto_speaker'}
    result=_failure(state,{'state':{'auto_distinct_voice_count':5}}, {})
    assert result['state']==state
    assert 'auto_distinct_voice_count' not in result['debug_job']
    assert result['debug_job']['progress_percent']==5


def _pause(state, product):
    source=SOURCE.read_text(encoding='utf-8-sig')
    start=source.index('    if str(product_result.get("status") or "") == "AUTO_EXACT_CONFIRMATION_REQUIRED":', source.index('async def _execute_video_dubbing_pipeline_core('))
    end=source.index('    if not product_result.get("ok"):',start)
    tree=ast.parse('def pause():\n'+textwrap.indent(textwrap.dedent(source[start:end]),'    '))
    ns={'state':state,'product_result':product,'workspace_artifacts':{},'input_save':{},'gate_matrix':{},
        'auto_smart_multivoice':SimpleNamespace(is_auto_smart_multivoice_state=lambda s:s.get('auto_speaker_lane')=='auto_smart_multivoice')}
    exec(compile(tree,'actual_confirmation_boundary','exec'),ns)
    return ns['pause']()


def test_smart_confirmation_pause_keeps_gate_receipt_without_confirming():
    state=_state()
    gate={'auto_exact_receipt':{'actual_total_xu':123},'auto_exact_receipt_confirmed':False}
    result=_pause(state,{'status':'AUTO_EXACT_CONFIRMATION_REQUIRED','state':gate})
    assert result['state']['auto_exact_receipt']==gate['auto_exact_receipt']
    assert result['state']['auto_exact_receipt_confirmed'] is False
    assert result['state']['_pipeline_job_id']=='same-job'
    assert result['charge_status']=='not_charged'


def test_public_failed_status_keeps_completed_progress(tmp_path):
    from services import product_progress_status
    final=tmp_path/'final.mp4'
    final.write_bytes(b'metadata-fixture-not-render-proof')
    result=_failure({**_state(),'_subdub_output_validation':{'ok':True}}, {}, {'final_mp4':str(final)})
    snapshot=product_progress_status.product_progress_stage_from_job('subdub',{
        **result['debug_job'],'status':'failed_no_charge','terminal_state':'failed_no_charge',
    })
    assert snapshot['percent']==90
    assert snapshot['terminal_state']=='failed_no_charge'


def test_legacy_confirmation_pause_remains_unchanged():
    state={**_state(),'auto_speaker_lane':'auto_speaker'}
    result=_pause(state,{'status':'AUTO_EXACT_CONFIRMATION_REQUIRED','state':{'auto_exact_receipt':{'actual_total_xu':123}}})
    assert result['state']==state
