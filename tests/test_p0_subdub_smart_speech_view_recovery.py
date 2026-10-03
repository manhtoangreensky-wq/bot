import asyncio
import importlib
import os
from pathlib import Path
import time

import numpy as np
import pytest

from services import subdub_multi_speaker_embedding_onnx as engine
from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_smart_multivoice as smart


def _module():return importlib.import_module('services.subdub_smart_speech_identity')


def _views(count,registers=None):
    identities=[i for i in range(count) for _ in range(12)]
    rows=np.zeros((len(identities),engine.EMBEDDING_DIM),dtype=np.float32)
    for pos,identity in enumerate(identities):rows[pos,identity]=1.
    regs=registers or ['high' if i%2 else 'low' for i in range(count)]
    return {'base_embeddings':rows,'shifted_embeddings':rows.copy(),
            'source_positions':np.arange(len(rows),dtype=np.float64)*.75,
            'speech_seconds':np.full(len(rows),1.5)}, [ .99 if regs[i]=='high' else .01 for i in identities ]


@pytest.mark.parametrize('count',[1,2,3,5,8])
def test_signal_selects_count_not_filename_or_forced_two(count):
    views,probabilities=_views(count)
    result=_module().build_speech_identity_authority(views,probabilities)
    assert result['speaker_count']==count
    assert len(set(result['labels']))==count
    assert result['speaker_count_views']==[count,count,count]
    assert min(result[k] for k in ('base_shift_agreement','base_aggregate_agreement','shift_aggregate_agreement'))>=engine.SPEECH_PARTITION_MIN_AGREEMENT


@pytest.mark.parametrize('registers',[['high','high'],['low','low'],['high','high','low']])
def test_same_register_people_do_not_collapse_into_one(registers):
    views,p=_views(len(registers),registers)
    result=_module().build_speech_identity_authority(views,p)
    assert result['speaker_count']==len(registers)
    assert result['speaker_registers']==registers


def test_one_noisy_register_window_does_not_split_a_stable_person():
    views,p=_views(3,['high','high','low'])
    p[3]=.01
    p[15]=.01
    result=_module().build_speech_identity_authority(views,p)
    assert result['labels']==[0]*12+[1]*12+[2]*12
    assert result['speaker_registers']==['high','high','low']


def test_evenly_split_register_evidence_does_not_invent_a_voice():
    views,p=_views(2,['high','low'])
    p[:12]=[.99]*6+[.01]*6
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        _module().build_speech_identity_authority(views,p)


def test_bad_view_is_not_fixed_by_lowering_threshold():
    views,p=_views(2)
    views['shifted_embeddings'][:3]=0
    views['shifted_embeddings'][:3,10]=1.
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        _module().build_speech_identity_authority(views,p)
    assert engine.MIN_FIXED_VOCAL_VIEW_COSINE==.98


def test_disagreeing_counts_cannot_claim_recovery(monkeypatch):
    views,p=_views(2);calls=[]
    original=engine._stable_cluster_view
    def counts(matrix,positions,**kw):
        calls.append('count');result=original(matrix,positions,**kw)
        return ((3,result[1],result[2]) if len(calls)==2 else result)
    monkeypatch.setattr(engine,'_stable_cluster_view',counts)
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        _module().build_speech_identity_authority(views,p)


def test_real_captured_speech_views_restore_two_registers_and_distinct_casts():
    root=os.environ.get('SMART_SPEAKER_RECOVERY_EVIDENCE')
    if not root:pytest.skip('Owner source evidence not supplied')
    data=np.load(Path(root)/'speech_evidence.npz')
    views={'base_embeddings':data['base'],'shifted_embeddings':data['shifted'],
           'source_positions':data['positions'],'speech_seconds':data['speech']}
    result=_module().build_speech_identity_authority(views,data['probabilities'].tolist())
    assert result['speaker_count']==2 and result['speaker_registers']==['low','high']
    labels={speaker_cast.normalized_speaker_key(0,i):{'voice_register':reg,'confidence':result['speaker_register_confidences'][i]} for i,reg in enumerate(result['speaker_registers'])}
    cues=[{'cue_id':'fixture-'+str(i),'speaker_id':label,'start':float(i*2),'end':float(i*2+1),'text':'fixture utterance'} for i,label in enumerate(labels)]
    decision=smart.decide_smart_multivoice(cues,validated_pools={'low':['male-approved'],'high':['female-approved']},acoustic_classifications=labels)
    assert decision.speaker_voice_map=={list(labels)[0]:'male-approved',list(labels)[1]:'female-approved'}


def test_smart_raw_view_failure_tries_speech_recovery_once_without_redemix(monkeypatch,tmp_path):
    module=_module();calls=[]
    words=[{'index':i,'word':'fixture','start':float(i),'end':float(i)+.7} for i in range(24)]
    pcm=tmp_path/'source.pcm';np.ones(24*44100*2,dtype=np.int16).tofile(pcm)
    def load(*_a,**_k):calls.append('demix');return np.ones(24*16000,dtype=np.int16)
    def raw(*_a,**_k):raise speaker_cast.AutoCastManualRequired() from ValueError('fixed_vocal_view_unstable')
    def recovered(_vocal,path,observed_words,**kwargs):
        calls.append('recover');assert path==str(pcm);assert len(observed_words)==24
        return {'ok':True,'smart_acoustic_generic':True,'detected_speaker_count':2,'word_coverage_count':24}
    monkeypatch.setattr(engine,'_load_fixed_vocal_pcm16',load)
    monkeypatch.setattr(engine,'_fixed_vocal_window_views',lambda *_a,**_k:{'base_embeddings':[],'shifted_embeddings':[],'window_energy':[],'source_positions':[]})
    monkeypatch.setattr(engine,'build_fixed_vocal_authority',raw)
    monkeypatch.setattr(module,'recover_speech_identity',recovered)
    result=engine._diarize_fixed_vocal_word_timeline_owned(str(pcm),words,duration_seconds=24,
        deadline_monotonic=time.monotonic()+30,stop_requested=lambda:False,minimum_speakers=1,gender_source_original=True)
    assert result['detected_speaker_count']==2
    assert calls==['demix','recover']


def test_non_smart_raw_view_error_stays_strict(monkeypatch,tmp_path):
    module=_module()
    words=[{'index':i,'word':'fixture','start':float(i),'end':float(i)+.7} for i in range(24)]
    monkeypatch.setattr(engine,'_load_fixed_vocal_pcm16',lambda *_a,**_k:np.ones(24*16000,dtype=np.int16))
    monkeypatch.setattr(engine,'_fixed_vocal_window_views',lambda *_a,**_k:{'base_embeddings':[],'shifted_embeddings':[],'window_energy':[],'source_positions':[]})
    def raw(*_a,**_k):raise speaker_cast.AutoCastManualRequired() from ValueError('fixed_vocal_view_unstable')
    monkeypatch.setattr(engine,'build_fixed_vocal_authority',raw)
    monkeypatch.setattr(module,'recover_speech_identity',lambda *_a,**_k:pytest.fail('strict lane must not use Smart recovery'))
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        engine._diarize_fixed_vocal_word_timeline_owned('unused.pcm',words,duration_seconds=24,
            deadline_monotonic=time.monotonic()+30,stop_requested=lambda:False)
