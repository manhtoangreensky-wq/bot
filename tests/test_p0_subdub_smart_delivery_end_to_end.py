"""Offline acceptance: real cached render, actual guards, production send boundary."""
import asyncio
import hashlib
import logging
import os
import subprocess
from pathlib import Path
import time
import types

import pytest

from services.subdub_blackboxes import auto_smart_multivoice as smart
from test_p0_subdub_smart_bounded_audio_recovery import _load_bot_functions, _probe, _run_cached_mp4, media_bot, timeline_bot
from test_p0_subdub_smart_exact_gate_handoff import _production_gate_with_offline_storage, actual_outer_exact_price_guard
from test_p0_subdub_smart_posttts_mp4_delivery import _cached_inputs, _outer_audio_guard


def _delivery_surface(media):
    module=types.ModuleType('offline_production_delivery')
    _load_bot_functions(Path(__file__).resolve().parents[1]/'bot.py',{
        'send_public_subtitle_dub_final_outputs','subdub_begin_delivery_once',
        'subdub_delivery_timeout_seconds_for_duration',
    },module)
    module.__dict__.update(
        hashlib=hashlib,time=time,logger=logging.getLogger(__name__),
        normalize_video_translate_mode=lambda value:value,
        subdub_video_requires_final_mp4=lambda *_a:True,
        VIDEO_SUBTITLE_MODE_DUB='dub',VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB='subtitle_plus_dub',
        VIDEO_SUBTITLE_MODE_CREATE='subtitle',VIDEO_SUBTITLE_MODE_TRANSLATE='translate',
        VIDEO_DUBBING_FLOW_TRANSCRIPT='transcript',VIDEO_DUBBING_FLOW_SUBTITLE_FILE_TRANSLATE='file_translate',
        SUBDUB_PUBLIC_AUDIO_FALLBACK_ENABLED=False,SUBDUB_ENABLE_DOCUMENT_FALLBACK=True,
        GENERATED_MEDIA_MAX_MB=100,SUBDUB_COMPRESS_IF_OVER_MB=100,SUBDUB_TELEGRAM_SEND_VIDEO_MAX_MB=100,
        SUBDUB_LONG_VIDEO_DELIVERY_TIMEOUT_SECONDS=1800,
        subdub_output_delivery_limit_mb=lambda *_a:100,
        video_dubbing_final_video_label=lambda *_a:('fixture.mp4','offline test',''),
        subdub_validate_video_output=media.subdub_validate_video_output,
        sanitize_log_text=str,SUBTITLE_DUB_PIPELINE_JOBS={},
        update_subtitle_dub_pipeline_job=lambda *_a,**_k:pytest.fail('no real persistence in offline test'),
        subdub_terminal_blocks_late_delivery=lambda job:job.get('terminal_state')=='delivered',
        subdub_progress_percent_for_lifecycle=lambda *_a:95,
        subdub_completed_steps_for_lifecycle=lambda *_a:[],
    )
    return module


@pytest.mark.parametrize('fixture,expected_cues,expected_voices',[
    ('806a998ec7fa6a3df38f',5,1),('53b6e00fc9113899224e',23,5),
])
def test_actual_smart_gate_render_outer_guards_and_send_ack(tmp_path,monkeypatch,media_bot,fixture,expected_cues,expected_voices):
    root,chunks,voices,_registers=_cached_inputs(fixture)
    real_run=smart.run_auto_smart_multivoice_blackbox
    gate_events=[]
    production_gate,_stored=_production_gate_with_offline_storage()

    def with_production_gate(**kwargs):
        original_prepare=kwargs['prepare_subtitles']
        async def prepare(*args,**options):
            prepared=await original_prepare(*args,**options)
            prepared['source_segments']=[dict(c) for c in prepared['output_segments']]
            return prepared
        async def gate(prepared,state):
            gate_events.append('gate')
            return await production_gate(prepared,state)
        kwargs['prepare_subtitles']=prepare
        kwargs['post_prepare_gate']=gate
        kwargs['state'].update(voice_kind='auto_speaker_gender',voice_selection_mode='auto_speaker',
            _pipeline_job_key='offline-only',_pipeline_job_id='offline-replay',
            _pipeline_is_admin=True,subdub_final_confirmed=True)
        return real_run(**kwargs)

    monkeypatch.setattr(smart,'run_auto_smart_multivoice_blackbox',with_production_gate)
    source=root/'normalized_source.mp4'
    duration=float(_probe(source)['format']['duration'])
    result,_observed,output=_run_cached_mp4(tmp_path,monkeypatch,media_bot,source,chunks,duration,voices)
    assert gate_events==['gate']
    assert result['tts_expected_segments']==result['tts_generated_segments']==expected_cues
    assert len(set(result['speaker_voice_map'].values()))==expected_voices
    assert _outer_audio_guard(result) is None
    assert actual_outer_exact_price_guard(result['state']) is None
    assert result['state']['auto_exact_actual_total_xu']==123 # Storage/quote stub, not a production price.
    sent=[]
    delivery=_delivery_surface(media_bot)
    async def record_send(_message,payload,**_kwargs):
        sent.append(bytes(payload))
        return {'sent':True,'delivery_method':'video','telegram_message_id':'offline-ack','file_id':'offline-file'}
    delivery.send_generated_video_bytes_for_delivery=record_send
    outcome=asyncio.run(delivery.send_public_subtitle_dub_final_outputs(
        object(),mode='subtitle_plus_dub',canonical_video_path=str(output),
        strict_validation=True,expected_duration_seconds=duration,require_final_audio=True,
    ))
    assert len(sent)==1
    assert sent[0]==output.read_bytes()
    assert outcome['video_delivery_sha256']==hashlib.sha256(sent[0]).hexdigest()
    assert outcome['video_delivery_message_id']=='offline-ack'
    assert outcome['final_mp4_validated'] is True
    assert outcome['final_mp4_delivered'] is True
    assert outcome['charged_xu']==0


def _two_voice_cached_path():
    root=os.environ.get('SMART_POSTTTS_REPLAY_DIR')
    if not root:pytest.skip('Owner cached media not supplied')
    path=Path(root)/'verified-s2-two-voice/n2-smart.mp4'
    assert hashlib.sha256(path.read_bytes()).hexdigest()=='f537be4869c095a7f0a463da0dff2593cf50e1c54e6380b5e906d1ad02e72b5f'
    return path


def test_actual_two_voice_mp4_send_failure_never_becomes_success(media_bot):
    delivery=_delivery_surface(media_bot)
    calls=[]
    async def fail_send(*_a,**_k):
        calls.append('send')
        return {'sent':False,'delivery_reason':'offline_transport_failure'}
    delivery.send_generated_video_bytes_for_delivery=fail_send
    outcome=asyncio.run(delivery.send_public_subtitle_dub_final_outputs(
        object(),mode='subtitle_plus_dub',canonical_video_path=str(_two_voice_cached_path()),
        strict_validation=True,expected_duration_seconds=4,require_final_audio=True,
    ))
    assert calls==['send']
    assert outcome['final_mp4_validated'] is True
    assert outcome['final_mp4_delivered'] is False
    assert outcome['full_video_failed'] is True
    assert outcome['charged_xu']==0


def test_missing_mp4_never_calls_send(tmp_path,media_bot):
    delivery=_delivery_surface(media_bot)
    async def forbidden(*_a,**_k):pytest.fail('no artifact, no send')
    delivery.send_generated_video_bytes_for_delivery=forbidden
    outcome=asyncio.run(delivery.send_public_subtitle_dub_final_outputs(
        object(),mode='subtitle_plus_dub',canonical_video_path=str(tmp_path/'missing.mp4'),
        strict_validation=True,expected_duration_seconds=4,require_final_audio=True,
    ))
    assert outcome['final_mp4_delivered'] is False
    assert outcome['charged_xu']==0


def test_actual_delivery_lock_prevents_duplicate_attempt(media_bot):
    delivery=_delivery_surface(media_bot)
    delivery.SUBTITLE_DUB_PIPELINE_JOBS['offline']={'job_id':'fixture'}
    assert delivery.subdub_begin_delivery_once('offline') is True
    assert delivery.subdub_begin_delivery_once('offline') is False
    assert delivery.SUBTITLE_DUB_PIPELINE_JOBS['offline']['delivery_attempt_count']==1


def test_missing_receipt_blocks_before_delivery():
    assert actual_outer_exact_price_guard({'auto_exact_receipt_confirmed':False})=='auto_exact_price_missing'


def test_actual_invalid_audio_track_stops_before_send(tmp_path,media_bot):
    path=tmp_path/'no_audio.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',
                    'color=c=black:s=320x180:r=25','-t','2','-an','-c:v','libx264',str(path)],check=True)
    delivery=_delivery_surface(media_bot)
    async def forbidden(*_a,**_k):pytest.fail('invalid output must not be sent')
    delivery.send_generated_video_bytes_for_delivery=forbidden
    outcome=asyncio.run(delivery.send_public_subtitle_dub_final_outputs(
        object(),mode='subtitle_plus_dub',canonical_video_path=str(path),
        strict_validation=True,expected_duration_seconds=2,require_final_audio=True,
    ))
    assert outcome['final_mp4_validated'] is False
    assert outcome['final_mp4_delivered'] is False
    assert outcome['charged_xu']==0
