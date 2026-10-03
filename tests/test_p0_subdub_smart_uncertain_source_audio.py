import asyncio
import json
import sys

import pytest

from services.subdub_blackboxes import auto_smart_multivoice as smart
from services.subdub_smart_source_audio import replace_unfit_smart_cues
from test_p0_subdub_smart_source_audio_fallback import _source
from test_p0_subdub_smart_partial_translation_resume import _resume_surface
from test_p0_subdub_canonical_receipt_presentation import _receipt_text
from test_p0_subdub_smart_bounded_audio_recovery import media_bot, timeline_bot, _probe
from test_p0_subdub_smart_standard_pipeline_orchestrator import SAMPLE_VALID_MP3


def test_uncertain_identity_retains_source_even_when_generated_audio_fits(tmp_path):
    source = _source(tmp_path)
    chunks = [{'cue_id': 'c1', 'start': 0., 'end': 1., 'audio_duration': .8,
               'audio_bytes': b'wrong-voice', 'tts_voice_id': 'female',
               'duration_aware_timing': True, 'smart_attribution_uncertain': True}]
    evidence = replace_unfit_smart_cues(chunks, source_file=str(source))
    assert evidence['smart_source_audio_reasons'] == {'c1': 'speaker_attribution_uncertain'}
    assert evidence['smart_dubbed_voice_count'] == 0
    assert chunks[0]['audio_duration'] == 1.
    assert chunks[0]['smart_audio_source'] == 'source'


def test_uncertain_ids_survive_resume_without_mutating_quote():
    state = {'auto_speaker_lane': 'auto_smart_multivoice',
             'smart_attribution_uncertain_cue_ids': ['c1', 'c3'],
             'auto_exact_actual_total_xu': 123}
    restored = json.loads(json.dumps(_resume_surface()(state)))
    assert restored['smart_attribution_uncertain_cue_ids'] == ['c1', 'c3']
    assert restored['auto_exact_actual_total_xu'] == 123


@pytest.mark.parametrize('ids', [['c1', 'c1'], [''], [2], 'c1'])
def test_invalid_uncertain_ids_do_not_authorize_source_replacement(ids):
    result = _resume_surface()({'auto_speaker_lane': 'auto_smart_multivoice',
                                'smart_attribution_uncertain_cue_ids': ids})
    assert 'smart_attribution_uncertain_cue_ids' not in result


@pytest.mark.parametrize('lang', ['vi', 'en'])
def test_unproven_identity_receipt_does_not_claim_one_proven_female(lang):
    state = {'auto_speaker_lane': 'auto_smart_multivoice',
             'auto_smart_multivoice_verified': True, 'auto_smart_degraded_single_voice': True,
             'auto_detected_speaker_count': 1, 'auto_effective_speaker_count': 1,
             'auto_distinct_voice_count': 1, 'speaker_voice_map': {'s1': 'female'},
             'smart_source_audio_cue_count': 2, 'smart_dubbed_voice_count': 0,
             'smart_source_audio_reasons': {'c1': 'speaker_attribution_uncertain', 'c2': 'speaker_attribution_uncertain'}}
    text = _receipt_text(state, lang)
    assert ('chưa xác định chắc chắn' if lang == 'vi' else 'not reliably determined') in text
    assert ('Số nhãn người nói nguồn: <b>1</b>' if lang == 'vi' else 'Source speaker labels: <b>1</b>') not in text
    assert ('Số giọng lồng tiếng đã dùng: <b>0</b>' if lang == 'vi' else 'Dubbing voices used: <b>0</b>') in text


def test_generic_smart_uncertain_cue_renders_real_mp4_without_changing_known_cue(tmp_path, monkeypatch, media_bot):
    source = _source(tmp_path)
    cues = [{'cue_id': f'c{i}', 'speaker_id': f's{i}', 'start': float(i),
             'end': float(i+1), 'text': f'target sentence {i}'} for i in range(2)]
    observed = {}
    async def prepare(*_a, **_k):
        return {'source_file': str(source), 'source_bytes': source.read_bytes(),
                'content_type': 'video/mp4', 'source_segments': cues, 'output_segments': cues,
                'output_subtitle': media_bot.video_dubbing_srt_from_segments(cues),
                'state': {'auto_smart_generic_acoustic': True, 'smart_attribution_uncertain_cue_ids': ['c0']}}
    async def synthesize(segments, **_k):
        return {'provider': 'offline', 'chunks': [{'cue_id': c['cue_id'], 'audio_bytes': SAMPLE_VALID_MP3,
                'audio_duration': .9, 'duration_aware_timing': True} for c in segments]}
    async def timeline(chunks, seconds):
        observed['chunks'] = chunks
        observed['plan'] = media_bot.subdub_plan_dub_timeline(chunks, seconds)
        return await media_bot.build_dub_timeline_audio(chunks, seconds)
    monkeypatch.setitem(sys.modules, 'bot', media_bot)
    output = tmp_path / 'final.mp4'
    result = asyncio.run(smart.run_auto_smart_multivoice_blackbox(
        state={'auto_speaker_lane': 'auto_smart_multivoice', 'mode': 'subtitle_plus_dub', 'input_duration': 4.},
        prepare_subtitles=prepare, synthesize_segments=synthesize, build_timeline_audio=timeline,
        post_prepare_gate=lambda *_a: {'continue': True},
        render_video=media_bot.video_dubbing_render_video, validated_pools={'low': ['male'], 'high': ['female']},
        locked_speaker_voice_map={'s0': 'male', 's1': 'female'},
        output_path=str(output), job_id='offline-uncertain', checkpoint_workspace=str(tmp_path/'checkpoint')))
    assert result['ok'], result
    assert result['smart_source_audio_reasons'] == {'c0': 'speaker_attribution_uncertain'}
    assert result['state']['smart_dubbed_voice_count'] == 1
    assert observed['chunks'][0]['smart_audio_source'] == 'source'
    assert observed['chunks'][1].get('smart_audio_source') != 'source'
    assert observed['plan']['shifted_cue_count'] == 0
    assert all(c['tempo_ratio'] <= 1.001 for c in observed['plan']['scheduled'])
    assert {s['codec_type'] for s in _probe(output)['streams']} >= {'audio', 'video'}
