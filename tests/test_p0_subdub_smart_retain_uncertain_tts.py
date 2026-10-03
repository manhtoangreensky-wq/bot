"""Uncertainty is not permission to discard fitting translated TTS."""
import asyncio
import sys

import pytest

from services.subdub_blackboxes import auto_smart_multivoice as smart
from services.subdub_smart_source_audio import replace_unfit_smart_cues
from test_p0_subdub_smart_bounded_audio_recovery import _probe, _run_cached_mp4, media_bot, timeline_bot
from test_p0_subdub_smart_posttts_mp4_delivery import _cached_inputs
from test_p0_subdub_smart_source_audio_fallback import _source
from test_p0_subdub_smart_standard_pipeline_orchestrator import SAMPLE_VALID_MP3


def test_all_eight_uncertain_fit_tts_chunks_remain_untouched():
    chunks = [{'cue_id': f'c{i}', 'start': float(i), 'end': float(i+1),
               'audio_duration': .8, 'audio_bytes': b'unchanged-test-payload',
               'duration_aware_timing': True, 'tts_voice_id': 'fallback-voice',
               'smart_attribution_uncertain': True} for i in range(8)]
    original = [dict(c) for c in chunks]
    result = replace_unfit_smart_cues(chunks, source_file='source-not-needed')
    assert chunks == original
    assert result['smart_source_audio_cue_count'] == 0
    assert result['smart_dubbed_voice_count'] == 1


def test_uncertain_missing_or_unfit_still_use_source_only_for_real_reason(tmp_path):
    source = _source(tmp_path)
    chunks = [{'cue_id': f'c{i}', 'start': float(i), 'end': float(i+1),
               'audio_duration': 2. if i == 1 else .8, 'audio_bytes': b'fixture',
               'duration_aware_timing': True, 'tts_voice_id': f'voice-{i}',
               'smart_attribution_uncertain': True} for i in range(3)]
    original = dict(chunks[0])
    result = replace_unfit_smart_cues(chunks, source_file=str(source), missing_translation_cue_ids=['c2'])
    assert chunks[0] == original
    assert result['smart_source_audio_reasons'] == {'c1': 'natural_audio_exceeds_window', 'c2': 'translation_missing'}
    assert result['smart_dubbed_voice_count'] == 1


def test_generic_smart_all_eight_uncertain_cues_render_actual_dubbed_mp4(tmp_path, monkeypatch, media_bot):
    source = _source(tmp_path)
    cues = [{'cue_id': f'c{i}', 'speaker_id': 's0', 'start': float(i*.5),
             'end': float((i+1)*.5), 'text': f'target {i}'} for i in range(8)]
    observed = {}
    async def prepare(*_a, **_k):
        return {'source_file': str(source), 'source_bytes': source.read_bytes(), 'content_type': 'video/mp4',
                'source_segments': cues, 'output_segments': cues,
                'output_subtitle': media_bot.video_dubbing_srt_from_segments(cues),
                'state': {'auto_smart_generic_acoustic': False, 'auto_smart_degraded_single_voice': True,
                          'smart_attribution_uncertain_cue_ids': [c['cue_id'] for c in cues]}}
    async def synthesize(segments, **_k):
        return {'provider': 'offline', 'chunks': [{'cue_id': c['cue_id'], 'audio_bytes': SAMPLE_VALID_MP3,
                'audio_duration': .4, 'duration_aware_timing': True} for c in segments]}
    async def timeline(chunks, seconds):
        observed['chunks'] = chunks
        observed['plan'] = media_bot.subdub_plan_dub_timeline(chunks, seconds)
        return await media_bot.build_dub_timeline_audio(chunks, seconds)
    monkeypatch.setitem(sys.modules, 'bot', media_bot)
    output = tmp_path/'final.mp4'
    result = asyncio.run(smart.run_auto_smart_multivoice_blackbox(
        state={'auto_speaker_lane': 'auto_smart_multivoice', 'mode': 'subtitle_plus_dub', 'input_duration': 4.},
        prepare_subtitles=prepare, post_prepare_gate=lambda *_a: {'continue': True}, synthesize_segments=synthesize,
        build_timeline_audio=timeline, render_video=media_bot.video_dubbing_render_video,
        validated_pools={'low': ['male'], 'high': ['female']}, locked_speaker_voice_map={'s0': 'female'},
        output_path=str(output), job_id='offline-eight-cues', checkpoint_workspace=str(tmp_path/'checkpoint')))
    assert result['ok'], result
    assert result['smart_source_audio_cue_count'] == 0
    assert result['smart_dubbed_voice_count'] == result['state']['smart_dubbed_voice_count'] == 1
    assert len(observed['chunks']) == 8
    assert all(c.get('smart_audio_source') != 'source' and c['audio_bytes'] == SAMPLE_VALID_MP3 for c in observed['chunks'])
    assert observed['plan']['shifted_cue_count'] == 0
    assert all(c['tempo_ratio'] <= 1.001 for c in observed['plan']['scheduled'])
    assert {s['codec_type'] for s in _probe(output)['streams']} >= {'audio', 'video'}


def test_existing_paid_source_cache_retains_fit_tts_despite_whole_identity_degradation(tmp_path, monkeypatch, media_bot):
    root, chunks, voices, _registers = _cached_inputs('806a998ec7fa6a3df38f')
    real_runner = smart.run_auto_smart_multivoice_blackbox
    def with_uncertainty(**kwargs):
        original_prepare = kwargs['prepare_subtitles']
        async def prepare(*args, **options):
            prepared = await original_prepare(*args, **options)
            prepared['state'].update(auto_smart_degraded_single_voice=True,
                smart_attribution_uncertain_cue_ids=[c['cue_id'] for c in prepared['output_segments']])
            return prepared
        kwargs.update(prepare_subtitles=prepare, post_prepare_gate=lambda *_a: {'continue': True})
        return real_runner(**kwargs)
    monkeypatch.setattr(smart, 'run_auto_smart_multivoice_blackbox', with_uncertainty)
    source = root/'normalized_source.mp4'
    result, observed, _output = _run_cached_mp4(tmp_path, monkeypatch, media_bot, source, chunks,
                                            float(_probe(source)['format']['duration']), voices)
    assert result['smart_dubbed_voice_count'] == 1
    assert result['smart_source_audio_cue_count'] == 1
    assert len(result['output_segments']) == 5
    assert observed['plan']['shifted_cue_count'] == 0
