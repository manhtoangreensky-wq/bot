import asyncio
import json
import os
from pathlib import Path

import numpy as np
import pytest

from services import subdub_smart_speech_identity as recovery
from services import subdub_multi_speaker_embedding_onnx as engine


def _authority(registers, labels):
    return {'speaker_count': len(registers), 'speaker_registers': registers,
            'speaker_register_confidences': [.99]*len(registers),
            'labels': labels, 'unit_confidences': [.99]*len(labels)}


def _evidence(register, rows=3, opposite=0):
    return [{'start': float(i), 'end': float(i)+1.5,
             'male_score': .9 if (register == 'low') != (i < opposite) else .1,
             'female_score': .9 if (register == 'high') != (i < opposite) else .1}
            for i in range(rows)]


def _views(labels):
    matrix = np.zeros((len(labels), engine.EMBEDDING_DIM), dtype=np.float32)
    for i, label in enumerate(labels):
        matrix[i, label] = 1
    return {'base_embeddings': matrix, 'shifted_embeddings': matrix.copy(),
            'speech_seconds': np.full(len(labels), 1.5),
            'plan': {'windows': [{'window_index': i, 'run_index': i//4} for i in range(len(labels))]}}


def test_source_gender_fixes_wrong_register_without_recounting_people():
    authority = _authority(['low', 'high'], [0,0,1,1,1,1,0,0])
    result = recovery._apply_source_gender_evidence(authority, _views(authority['labels']),
        {0: {'full': _evidence('high', 1)[0], 'windows': _evidence('high', 4)},
         1: {'full': _evidence('low', 1)[0], 'windows': _evidence('low', 4)}})
    assert result['speaker_count'] == 2
    assert result['speaker_registers'] == ['low','high']
    assert result['labels'] == [1]*4+[0]*4
    assert result['source_gender_corrected_window_count'] == 4
    assert authority['labels'] == [0,0,1,1,1,1,0,0]


def test_same_gender_people_are_not_merged_by_source_gender():
    authority = _authority(['high','high'], [0]*4+[1]*4)
    result = recovery._apply_source_gender_evidence(authority, _views(authority['labels']),
        {i: {'full': _evidence('high',1)[0], 'windows': _evidence('high',4)} for i in [0,1]})
    assert result['labels'] == authority['labels']
    assert result['speaker_count'] == 2


@pytest.mark.parametrize('register', ['low','high'])
def test_single_person_source_register_can_be_corrected_without_forcing_pair(register):
    opposite = 'high' if register == 'low' else 'low'
    authority = _authority([opposite], [0]*8)
    result = recovery._apply_source_gender_evidence(authority,_views(authority['labels']),
        {i: {'full': _evidence(register,1)[0], 'windows': _evidence(register,4)} for i in [0,1]})
    assert result['speaker_count'] == 1
    assert result['labels'] == [0]*8
    assert result['speaker_registers'] == [register]


def test_strong_opposite_source_window_is_not_smoothed_over_real_turn():
    authority = _authority(['low','high'], [0,0,1,0,1,1,1,1])
    rows = _evidence('low', 4)
    rows[2].update(male_score=.001,female_score=.99)
    result = recovery._apply_source_gender_evidence(authority,_views(authority['labels']),
        {0: {'full': _evidence('low',1)[0], 'windows': rows}})
    assert result['labels'][2] == 1


@pytest.mark.parametrize('kind', ['weak','tie','full_disagrees','nan','insufficient'])
def test_unproven_source_register_cannot_rewrite_identity(kind):
    authority = _authority(['low','high'], [0]*4+[1]*4)
    rows = _evidence('high',4)
    full = _evidence('high',1)[0]
    if kind == 'weak':
        for row in rows: row.update(male_score=.49,female_score=.5)
        full.update(male_score=.49,female_score=.5)
    elif kind == 'tie': rows = _evidence('high',4,opposite=2)
    elif kind == 'full_disagrees': full = _evidence('low',1)[0]
    elif kind == 'nan': rows[0]['female_score'] = float('nan')
    else: rows=[]
    result = recovery._apply_source_gender_evidence(authority,_views(authority['labels']),
        {0: {'full':full,'windows':rows}})
    assert result['labels'] == authority['labels']


def test_fresh_source_reference_has_no_gender_flip_inside_supported_run():
    root = os.environ.get('SMART_SOURCE_GENDER_EVIDENCE')
    if not root: pytest.skip('Private source gender evidence not supplied')
    root = Path(root)
    data = np.load(root.parent/'live1338/source_fresh_speech.npz')
    plan = json.loads((root.parent/'live1338/source_fresh_plan.json').read_text())
    views = {'base_embeddings':data['base'], 'shifted_embeddings':data['shifted'],
             'source_positions':data['positions'], 'speech_seconds':data['speech'], 'plan':plan}
    authority = recovery.build_speech_identity_authority(views,data['probabilities'].tolist())
    windows = json.loads((root/'window-pann.json').read_text())
    runs = json.loads((root/'source-run-pann.json').read_text())
    evidence = {run['run_index']:{'full':runs['run-'+str(run['run_index'])][0],
        'windows':[{'start':w['position'],'end':w['position']+1.5,
                    'male_score':w['male_score'],'female_score':w['female_score']}
                   for w in windows if w['run_index']==run['run_index']]} for run in plan['runs']}
    result = recovery._apply_source_gender_evidence(authority,views,evidence)
    assert result['speaker_count'] == 2
    assert result['source_gender_corrected_window_count'] > 0
    for run in [0,1,2,3,5,6,8,9]:
        expected = 'low' if runs['run-'+str(run)][0]['male_score'] > runs['run-'+str(run)][0]['female_score'] else 'high'
        indexes = [w['window_index'] for w in plan['windows'] if w['run_index']==run]
        assert {result['speaker_registers'][result['labels'][i]] for i in indexes} == {expected}


@pytest.mark.parametrize('count',[1,2,3,5,8])
def test_source_gender_keeps_all_supported_people_for_general_counts(count):
    registers = ['high' if i%2 else 'low' for i in range(count)]
    labels = [i for i in range(count) for _ in range(4)]
    authority = _authority(registers, labels)
    evidence = {i:{'full':_evidence(register,1)[0],'windows':_evidence(register,4)}
                for i,register in enumerate(registers)}
    result = recovery._apply_source_gender_evidence(authority,_views(labels),evidence)
    assert result['speaker_count'] == count
    assert result['speaker_registers'] == registers
    assert result['labels'] == labels


@pytest.mark.parametrize('count',[2,3,5,8])
def test_stable_person_wrong_gender_is_reclassified_not_merged_into_another_person(count):
    expected = ['high' if i%2 else 'low' for i in range(count)]
    wrong = expected.copy()
    wrong[0] = 'high'
    labels = [i for i in range(count) for _ in range(4)]
    authority = _authority(wrong,labels)
    evidence = {i:{'full':_evidence(register,1)[0],'windows':_evidence(register,4)}
                for i,register in enumerate(expected)}
    result = recovery._apply_source_gender_evidence(authority,_views(labels),evidence)
    assert result['labels'] == labels
    assert result['speaker_count'] == count
    assert result['speaker_registers'] == expected


def test_optional_pann_missing_model_returns_no_rewrite_or_fail(monkeypatch):
    def missing(): raise OSError('model unavailable')
    monkeypatch.setattr(recovery.stereo, '_validated_model_paths', missing)
    result = recovery._pann_source_run_evidence(np.ones(32000,dtype=np.int16),{},
        stereo_pcm_path='missing.pcm',
        deadline_monotonic=__import__('time').monotonic()+20,stop_requested=lambda:False)
    assert result == {}
    assert recovery.stereo._CLASSIFIER_LOCK.acquire(blocking=False)
    recovery.stereo._CLASSIFIER_LOCK.release()


def test_optional_pann_busy_returns_without_blocking_other_lane():
    assert recovery.stereo._CLASSIFIER_LOCK.acquire(blocking=False)
    try:
        assert recovery._pann_source_run_evidence(np.ones(32000,dtype=np.int16),{},
            stereo_pcm_path='missing.pcm',
            deadline_monotonic=__import__('time').monotonic()+20,stop_requested=lambda:False) == {}
    finally:
        recovery.stereo._CLASSIFIER_LOCK.release()


def test_pann_adapter_uses_existing_model_and_speech_singing_class_indices(monkeypatch):
    observed = []
    class Session:
        def run(self, names, values):
            observed.append((names,values['input_values'].shape))
            scores=np.zeros((1,527),dtype=np.float32)
            scores[0,1]=.2; scores[0,2]=.1; scores[0,32]=.8; scores[0,33]=.05
            return [scores]
    monkeypatch.setattr(recovery.stereo,'_validated_model_paths',lambda:('locked-uvr','locked-pann'))
    monkeypatch.setattr(recovery.stereo,'_session',lambda _ort,path: Session() if path=='locked-pann' else pytest.fail('wrong model'))
    def infer_source(path, selected, models, **kwargs):
        assert str(path)=='source.pcm' and models==('locked-uvr','locked-pann')
        return {key:[{**rows[0],'male_score':.8,'female_score':.1}] for key,rows in selected.items()}
    monkeypatch.setattr(recovery.stereo,'_infer_selected_cues',infer_source)
    plan={'regions':[{'index':0,'start':0.,'end':2.}],
          'runs':[{'run_index':0,'region_indexes':[0],'speech_seconds':2.}],
          'windows':[{'run_index':0,'window_index':0,'source_position':0.,'speech_start_seconds':0.,'speech_end_seconds':1.5}]}
    result=recovery._pann_source_run_evidence(np.ones(32000,dtype=np.int16),plan,
        stereo_pcm_path='source.pcm',
        deadline_monotonic=__import__('time').monotonic()+20,stop_requested=lambda:False)
    assert result[0]['full']['male_score'] == pytest.approx(.8)
    assert result[0]['windows'][0]['female_score'] == pytest.approx(.1)
    assert observed == [(['clipwise_output'],(1,48000))]


def test_corrected_gender_reaches_actual_smart_synth_voice_boundary(tmp_path):
    from services.subdub_blackboxes import auto_smart_multivoice as smart
    from services import subdub_speaker_cast as cast
    from test_p0_subdub_smart_standard_pipeline_orchestrator import SAMPLE_VALID_MP3
    authority=_authority(['low','high'],[0,0,1,1,1,1,0,0])
    result=recovery._apply_source_gender_evidence(authority,_views(authority['labels']),
        {0:{'full':_evidence('high',1)[0],'windows':_evidence('high',4)},
         1:{'full':_evidence('low',1)[0],'windows':_evidence('low',4)}})
    classes={cast.normalized_speaker_key(0,i):{'voice_register':reg,'confidence':.99}
             for i,reg in enumerate(result['speaker_registers'])}
    cues=[{'cue_id':'cue-'+str(i),'speaker_id':cast.normalized_speaker_key(0,label),
           'start':float(i*3),'end':float(i*3+2),'text':'fixture'} for i,label in enumerate(result['labels'])]
    decision=smart.decide_smart_multivoice(cues,validated_pools={'low':['male-approved'],'high':['female-approved']},
        acoustic_classifications=classes)
    captured=[]
    async def synth(segments,*,voice_id,**kwargs):
        captured.append((segments[0]['cue_id'],voice_id))
        return {'provider':'offline-fixture','chunks':[{'cue_id':segments[0]['cue_id'],
                'audio':SAMPLE_VALID_MP3,'audio_duration':.2}]}
    adapter=smart.create_smart_synth_adapter(synth,workspace=str(tmp_path),job_id='offline-gender-cast',quote_fingerprint='fixture')
    asyncio.run(adapter(cues=cues,speaker_voice_map=decision.speaker_voice_map))
    assert [voice for _,voice in captured] == ['female-approved']*4+['male-approved']*4
    asyncio.run(adapter(cues=cues,speaker_voice_map=decision.speaker_voice_map))
    assert len(captured)==8
