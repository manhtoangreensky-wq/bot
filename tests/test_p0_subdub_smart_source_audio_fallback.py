import importlib
from pathlib import Path
import subprocess

import pytest

from test_p0_subdub_smart_bounded_audio_recovery import _probe,media_bot,timeline_bot
from test_p0_subdub_canonical_receipt_presentation import _receipt_text


def _module():return importlib.import_module('services.subdub_smart_source_audio')


def _source(tmp_path):
    source=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=black:s=320x180:r=25',
                    '-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','4',
                    '-c:v','libx264','-c:a','aac',str(source)],check=True)
    return source


def test_only_unfit_cue_replaced_by_exact_source_window_without_speedup(tmp_path):
    source=_source(tmp_path);chunks=[
        {'cue_id':'c1','speaker_id':'s1','start':0.,'end':1.,'text':'target1','audio_duration':.8,'audio_bytes':b'untouched','duration_aware_timing':True},
        {'cue_id':'c2','speaker_id':'s2','start':1.,'end':1.88,'text':'target2','audio_duration':2.285469,'audio_bytes':b'unfit','duration_aware_timing':True},
    ]
    original=dict(chunks[0])
    result=_module().replace_unfit_smart_cues(chunks,source_file=str(source))
    assert chunks[0]==original
    assert result['smart_source_audio_cue_ids']==['c2']
    assert chunks[1]['smart_audio_source']=='source'
    assert chunks[1]['audio_duration']==pytest.approx(.88)
    assert chunks[1]['fit_audio_duration']==pytest.approx(.88)
    assert chunks[1]['trim_start']==0
    assert chunks[1]['trim_end']==pytest.approx(.88)
    assert chunks[1]['start']==1 and chunks[1]['end']==1.88
    audio=tmp_path/'fallback.wav';audio.write_bytes(chunks[1]['audio_bytes'])
    assert float(_probe(audio)['format']['duration'])==pytest.approx(.88,abs=.001)
    assert chunks[1]['text']=='target2'


def test_missing_translation_uses_source_even_when_audio_fits(tmp_path):
    source=_source(tmp_path);chunks=[{'cue_id':'missing','start':0.,'end':2.,'text':'source text',
        'audio_duration':1.,'audio_bytes':b'wrong-language','duration_aware_timing':True}]
    result=_module().replace_unfit_smart_cues(chunks,source_file=str(source),missing_translation_cue_ids=['missing'])
    assert result['smart_source_audio_cue_ids']==['missing']
    assert result['smart_source_audio_reasons']=={'missing':'translation_missing'}


def test_helper_never_changes_non_duration_aware_chunks(tmp_path):
    chunks=[{'cue_id':'legacy','start':0.,'end':1.,'audio_duration':4.,'audio_bytes':b'legacy'}]
    old=dict(chunks[0]);result=_module().replace_unfit_smart_cues(chunks,source_file='not-needed.mp4')
    assert chunks==[old]
    assert result['smart_source_audio_cue_ids']==[]


def test_corrupt_source_does_not_substitute_silence_or_fake_success(tmp_path):
    source=tmp_path/'bad.mp4';source.write_bytes(b'corrupt')
    chunks=[{'cue_id':'c1','start':0.,'end':1.,'audio_duration':4.,'audio_bytes':b'unfit','duration_aware_timing':True}]
    old=dict(chunks[0])
    with pytest.raises(RuntimeError,match='smart_source_audio'):
        _module().replace_unfit_smart_cues(chunks,source_file=str(source))
    assert chunks==[old]


def test_all_replacements_are_atomic_if_one_source_window_invalid(tmp_path):
    source=_source(tmp_path);chunks=[
        {'cue_id':'c1','start':0.,'end':1.,'audio_duration':4.,'audio_bytes':b'unfit','duration_aware_timing':True},
        {'cue_id':'c2','start':8.,'end':9.,'audio_duration':4.,'audio_bytes':b'outside','duration_aware_timing':True},
    ]
    old=[dict(c) for c in chunks]
    with pytest.raises(RuntimeError,match='smart_source_audio'):
        _module().replace_unfit_smart_cues(chunks,source_file=str(source))
    assert chunks==old


@pytest.mark.parametrize('lang',['vi','en'])
def test_smart_receipt_discloses_original_cues_and_real_dubbed_voice_count(lang):
    state={'auto_speaker_lane':'auto_smart_multivoice','auto_smart_multivoice_verified':True,
           'auto_detected_speaker_count':2,'auto_effective_speaker_count':2,'auto_distinct_voice_count':2,
           'speaker_voice_map':{'s1':'v1','s2':'v2'},'smart_source_audio_cue_count':3,'smart_dubbed_voice_count':1}
    text=_receipt_text(state,lang)
    assert ('Giữ âm thanh nguồn: <b>3</b>' if lang=='vi' else 'Original audio retained: <b>3</b>') in text
    assert ('Số giọng lồng tiếng đã dùng: <b>1</b>' if lang=='vi' else 'Dubbing voices used: <b>1</b>') in text


def test_missing_flags_survive_production_cue_qc():
    from test_p0_subdub_smart_translation_context import _surface,_cues
    import asyncio
    ns,cv,_requests=_surface()
    async def broken(*_a,**_k):raise RuntimeError('offline translation failure')
    ns['translate_subtitle_text']=broken
    ns['video_dubbing_qc_segments']=lambda cues,**_k:[{key:value for key,value in c.items() if key!='translate_missing'} for c in cues]
    state={'auto_speaker_lane':'auto_smart_multivoice','detected_language':'zh'};token=cv.set(state)
    try:result=asyncio.run(ns['translate_subtitle_segments'](_cues(),'vi',allow_confirmed_product=True))
    finally:cv.reset(token)
    assert result['translation_missing_cue_ids']==['c1','c2','c3']
    assert all(c['translate_missing'] for c in result['segments'])


@pytest.mark.parametrize('smart',[True,False])
def test_only_smart_preparation_continues_after_partial_translation(smart):
    import ast,textwrap
    from types import SimpleNamespace
    source=(Path(__file__).resolve().parents[1]/'bot.py').read_text(encoding='utf-8-sig')
    marker=source.index('            if translation_missing_count > 0 and not auto_smart_multivoice')
    end=source.index('            output_subtitle =',marker)
    block=textwrap.dedent(source[marker:end])
    ns={'translation_missing_count':1,'state':{},'auto_smart_multivoice':SimpleNamespace(is_auto_smart_multivoice_state=lambda _s:smart)}
    if smart:exec(compile(ast.parse(block),'actual_partial_translation_gate','exec'),ns)
    else:
        with pytest.raises(RuntimeError,match='translation_incomplete'):
            exec(compile(ast.parse(block),'actual_partial_translation_gate','exec'),ns)
