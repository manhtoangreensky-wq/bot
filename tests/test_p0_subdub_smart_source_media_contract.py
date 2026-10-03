import io
import json
import os
from pathlib import Path
import subprocess
import wave

import pytest

from services import subdub_smart_source_audio as helper


@pytest.fixture
def source_media(tmp_path):
    path=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=black:s=160x90:r=25',
                    '-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','4',
                    '-c:v','libx264','-c:a','aac',str(path)],check=True)
    return path


def _unfit(**fields):
    return {'cue_id':'unfit','start':1.,'end':2.,'audio_duration':3.,'audio_bytes':b'existing-tts',
            'duration_aware_timing':True,'tts_voice_id':'male-approved',**fields}


@pytest.mark.parametrize('suffix',['.srt','.VTT','.ass','.ssa','.sub','.txt','.json'])
def test_subtitle_path_cannot_override_valid_media_bytes(tmp_path,source_media,suffix):
    subtitle=tmp_path/('source'+suffix)
    subtitle.write_text('1\n00:00:01,000 --> 00:00:02,000\nsubtitle\n',encoding='utf-8')
    chunk=_unfit()
    result=helper.replace_unfit_smart_cues([chunk],source_file=str(subtitle),source_bytes=source_media.read_bytes())
    assert result['smart_source_audio_cue_ids']==['unfit']
    assert chunk['audio_duration']==pytest.approx(1.)
    assert chunk['tts_voice_id']=='male-approved'


def test_subtitle_without_media_fails_truthfully_before_decode(tmp_path):
    subtitle=tmp_path/'source.srt';subtitle.write_text('subtitle',encoding='utf-8')
    chunk=_unfit();before=dict(chunk)
    with pytest.raises(RuntimeError,match='smart_source_audio_source_missing'):
        helper.replace_unfit_smart_cues([chunk],source_file=str(subtitle))
    assert chunk==before


@pytest.mark.parametrize('file_source',[True,False])
def test_borrowed_tail_does_not_require_nonexistent_source_audio(source_media,file_source):
    chunk=_unfit(start=3.,end=5.,smart_source_end=3.9,tail_extension_seconds=1.1,audio_duration=6.)
    result=helper.replace_unfit_smart_cues([chunk],source_file=str(source_media)if file_source else'',
        source_bytes=b''if file_source else source_media.read_bytes())
    assert result['smart_source_audio_cue_ids']==['unfit']
    assert (chunk['start'],chunk['end'])==(3.,5.)
    assert chunk['audio_duration']==pytest.approx(.9)
    assert chunk['trim_end']==pytest.approx(.9)
    with wave.open(io.BytesIO(chunk['audio_bytes']),'rb')as audio:
        frames=audio.readframes(audio.getnframes())
        assert len(frames)/(audio.getsampwidth()*audio.getnchannels()*audio.getframerate())==pytest.approx(.9,abs=.001)
    assert chunk['tts_voice_id']=='male-approved'


@pytest.mark.parametrize('source_end',[.5,6.,float('nan')])
def test_invalid_original_window_cannot_hide_bad_source(source_media,source_end):
    chunk=_unfit(smart_source_end=source_end,tail_extension_seconds=1.)
    before=dict(chunk)
    with pytest.raises(RuntimeError,match='smart_source_audio_invalid_window'):
        helper.replace_unfit_smart_cues([chunk],source_file=str(source_media))
    assert chunk==before


def test_exact_failed_job_last_cue_decodes_its_original_source_window():
    value=os.environ.get('SMART_7D_REPLAY_DIR')
    if not value:pytest.skip('Private failed-job artifacts not supplied')
    root=Path(value);manifest=json.loads((root/'subdub_tts_manifest.json').read_text())
    entry=next(e for e in manifest['entries'].values()if e['cue_id']=='cue-0006-d46123ceb6ae')
    chunk={**entry['chunks_meta'][0],'end':60.,'smart_source_end':58.085,'tail_extension_seconds':1.915,
           'tts_voice_id':entry['voice_id']}
    result=helper.replace_unfit_smart_cues([chunk],source_file=str(root/'auto_exact_source.srt'),
        source_bytes=(root/'normalized_source.mp4').read_bytes())
    assert result['smart_source_audio_cue_count']==1
    assert chunk['audio_duration']==pytest.approx(3.06)
    assert chunk['tts_voice_id']=='English_PassionateWarrior'


def test_original_source_fallback_keeps_natural_tempo_after_borrowing(source_media):
    from test_p0_subdub_smart_bounded_audio_recovery import timeline_bot as fixture
    timeline=fixture.__wrapped__()
    chunk=_unfit(start=3.,end=5.,smart_source_end=3.9,tail_extension_seconds=1.1,audio_duration=6.)
    helper.replace_unfit_smart_cues([chunk],source_file=str(source_media))
    chunk['cue_locked_timing']=True
    plan=timeline.subdub_plan_dub_timeline([chunk],5.)
    assert plan['scheduled'][0]['tempo_ratio']==pytest.approx(1.)
    assert plan['scheduled'][0]['scheduled_start']==3.
