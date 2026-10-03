"""Actual request/loop boundaries; no paid client or bot bootstrap."""
import ast
import asyncio
from contextvars import ContextVar
from pathlib import Path
from types import SimpleNamespace
import os
import subprocess

import pytest

SOURCE=Path(__file__).resolve().parents[1]/'bot.py'


def _surface():
    source=(subprocess.check_output(['git','show',os.environ['SMART_CONTEXT_BASELINE']+':bot.py'],text=True,encoding='utf-8')
            if os.environ.get('SMART_CONTEXT_BASELINE') else SOURCE.read_text(encoding='utf-8-sig'))
    snippets=[]
    for name,end_name in [('translate_with_deepl','translate_with_gemini'),('translate_subtitle_segments','subdub_emit_progress_callback')]:
        start=source.index('async def '+name+'(')
        end=source.index('\nasync def '+end_name+'(',start)
        snippets.append(source[start:end])
    tree=ast.parse('\n'.join(snippets))
    names={'translate_with_deepl','translate_subtitle_segments'}
    selected=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names]
    cv=ContextVar('fixture',default=None)
    requests=[]
    class Client:
        def __init__(self,**_kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*_args):pass
        async def post(self,*args,**kwargs):
            requests.append(kwargs['json'])
            return SimpleNamespace(status_code=200,json=lambda:{'translations':[{'text':'translated cue'}]})
    ns={
        'DEEPL_API_KEY':'offline-test','DEEPL_API_URL':'https://api-free.deepl.com/v2/translate',
        'httpx':SimpleNamespace(AsyncClient=Client),'normalize_translate_target':lambda s:s,
        'TRANSLATE_LANGUAGE_OPTIONS':{'vi':{'deepl':'VI'}},'sanitize_log_text':str,
        'get_subdub_active_pipeline_state':lambda:cv.get(),
        'auto_smart_multivoice':SimpleNamespace(is_auto_smart_multivoice_state=lambda s:isinstance(s,dict) and s.get('auto_speaker_lane')=='auto_smart_multivoice'),
        'subdub_speaker_cue_metadata':lambda c:{k:c[k] for k in ('cue_id','speaker_id') if k in c},
        'subdub_retime_translated_segments_to_source':lambda _src,dst:dst,
        'video_dubbing_qc_segments':lambda s,**_kwargs:s,
        'subdub_validate_cue_locked_timing':lambda src,dst:{'ok':[(c['start'],c['end']) for c in src]==[(c['start'],c['end']) for c in dst]},
        'video_dubbing_srt_from_segments':lambda s:'fixture srt',
    }
    exec(compile(ast.Module(body=selected,type_ignores=[]),'actual_translation_boundaries','exec'),ns)
    async def translate(text,target,**_kwargs):
        return {'text':await ns['translate_with_deepl'](text,target),'provider':'deepl'}
    ns['translate_subtitle_text']=translate
    return ns,cv,requests


def _cues():
    return [{'cue_id':'c1','speaker_id':'s1','start':20.,'end':23.,'text':'source before'},
            {'cue_id':'c2','speaker_id':'s2','start':25.,'end':27.,'text':'short fragment'},
            {'cue_id':'c3','speaker_id':'s1','start':30.,'end':33.,'text':'source after'}]


def test_smart_cues_get_original_context_and_explicit_source_with_same_call_count():
    ns,cv,requests=_surface()
    state={'auto_speaker_lane':'auto_smart_multivoice','detected_language':'zh','_smart_translation_cue':{'old':'keep'}}
    token=cv.set(state)
    try:result=asyncio.run(ns['translate_subtitle_segments'](_cues(),'vi',allow_confirmed_product=True))
    finally:cv.reset(token)
    assert len(requests)==3
    assert requests[1]['source_lang']=='ZH'
    assert 'source before' in requests[1]['context']
    assert 'source after' in requests[1]['context']
    assert requests[1]['text']==['short fragment']
    assert state['_smart_translation_cue']=={'old':'keep'}
    assert [c['cue_id'] for c in result['segments']]==['c1','c2','c3']
    assert [(c['start'],c['end']) for c in result['segments']]==[(c['start'],c['end']) for c in _cues()]


@pytest.mark.parametrize('state',[None,{}, {'auto_speaker_lane':'auto_speaker'}, {'auto_speaker_lane':'auto_multi_speaker'}])
def test_non_smart_deepl_request_unchanged(state):
    ns,cv,requests=_surface();token=cv.set(state)
    try:asyncio.run(ns['translate_with_deepl']('original','vi'))
    finally:cv.reset(token)
    assert requests==[{'text':['original'],'target_lang':'VI'}]


def test_unknown_source_never_forces_guess_into_translation():
    ns,cv,requests=_surface();state={'auto_speaker_lane':'auto_smart_multivoice','detected_language':'auto'}
    token=cv.set(state)
    try:asyncio.run(ns['translate_subtitle_segments'](_cues(),'vi',allow_confirmed_product=True))
    finally:cv.reset(token)
    assert 'source_lang' not in requests[1]
    assert 'context' in requests[1]
    assert '_smart_translation_cue' not in state


def test_failure_restores_context_and_does_not_retry_or_drop_cue():
    ns,cv,requests=_surface();calls=[]
    async def broken(*args,**kwargs):
        calls.append(args);raise RuntimeError('offline_failure')
    ns['translate_subtitle_text']=broken
    state={'auto_speaker_lane':'auto_smart_multivoice','detected_language':'zh'};token=cv.set(state)
    try:result=asyncio.run(ns['translate_subtitle_segments'](_cues(),'vi',allow_confirmed_product=True))
    finally:cv.reset(token)
    assert len(calls)==3
    assert result['translation_missing_count']==3
    assert [c['text'] for c in result['segments']]==[c['text'] for c in _cues()]
    assert '_smart_translation_cue' not in state


def test_parallel_jobs_cannot_share_language_or_source_context():
    ns,cv,requests=_surface()
    async def job(language,word):
        state={'auto_speaker_lane':'auto_smart_multivoice','detected_language':language}
        token=cv.set(state)
        try:
            cues=[{**c,'text':word} for c in _cues()]
            await ns['translate_subtitle_segments'](cues,'vi',allow_confirmed_product=True)
        finally:cv.reset(token)
    async def run():await asyncio.gather(job('zh','Chinese job'),job('es','Spanish job'))
    asyncio.run(run())
    for request in requests:
        assert request['source_lang']==('ZH' if request['text']==['Chinese job'] else 'ES')
        assert ('Spanish job' not in request['context']) if request['source_lang']=='ZH' else ('Chinese job' not in request['context'])
