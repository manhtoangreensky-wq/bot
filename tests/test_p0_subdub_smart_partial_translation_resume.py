import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def _resume_surface():
    source=(Path(__file__).resolve().parents[1]/'bot.py').read_text(encoding='utf-8-sig')
    start=source.index('def _subdub_auto_resume_state(')
    end=source.index('\ndef _subdub_auto_persist_prepared_cache(',start)
    ns={
        'video_dubbing_sync_state_fields':lambda state,**_k:dict(state),
        'auto_multi_speaker':SimpleNamespace(is_auto_multi_speaker_state=lambda _s:False,bounded_multi_acoustic_evidence=lambda _s:{}),
        'auto_smart_multivoice':SimpleNamespace(is_auto_smart_multivoice_state=lambda s:s.get('auto_speaker_lane')=='auto_smart_multivoice'),
    }
    exec(compile(source[start:end],'actual_resume_serializer','exec'),ns)
    return ns['_subdub_auto_resume_state']


def test_partial_smart_ids_survive_json_roundtrip_without_changing_quote():
    resume=_resume_surface()
    state={'auto_speaker_lane':'auto_smart_multivoice','smart_translation_missing_cue_ids':['c2','c4'],
           'auto_exact_actual_total_xu':123,'auto_exact_receipt_confirmed':False}
    restored=json.loads(json.dumps(resume(state)))
    assert restored['smart_translation_missing_cue_ids']==['c2','c4']
    assert restored['auto_exact_actual_total_xu']==123
    assert restored['auto_exact_receipt_confirmed'] is False
    restored['smart_translation_missing_cue_ids'].append('different')
    assert state['smart_translation_missing_cue_ids']==['c2','c4']


@pytest.mark.parametrize('ids',[None,'c2',[2],['c2','c2'],[''],['x'*161]])
def test_invalid_resume_cue_list_cannot_create_render_authority(ids):
    state={'auto_speaker_lane':'auto_smart_multivoice','smart_translation_missing_cue_ids':ids}
    result=_resume_surface()(state)
    assert 'smart_translation_missing_cue_ids' not in result


def test_non_smart_list_handling_unchanged():
    state={'auto_speaker_lane':'auto_speaker','smart_translation_missing_cue_ids':['c2']}
    assert 'smart_translation_missing_cue_ids' not in _resume_surface()(state)


def test_resumed_missing_cue_still_uses_actual_source_audio_when_tts_would_fit(tmp_path):
    from test_p0_subdub_smart_source_audio_fallback import _source
    from services.subdub_smart_source_audio import replace_unfit_smart_cues
    source=_source(tmp_path)
    state=json.loads(json.dumps(_resume_surface()({'auto_speaker_lane':'auto_smart_multivoice',
        'smart_translation_missing_cue_ids':['c2'],'auto_exact_actual_total_xu':123})))
    chunks=[{'cue_id':'c2','start':1.,'end':2.,'audio_duration':.5,
             'audio_bytes':b'wrong-language-tts','duration_aware_timing':True}]
    result=replace_unfit_smart_cues(chunks,source_file=str(source),
        missing_translation_cue_ids=state['smart_translation_missing_cue_ids'])
    assert result['smart_source_audio_reasons']=={'c2':'translation_missing'}
    assert chunks[0]['smart_audio_source']=='source'
    assert chunks[0]['audio_duration']==1.
    assert state['auto_exact_actual_total_xu']==123
