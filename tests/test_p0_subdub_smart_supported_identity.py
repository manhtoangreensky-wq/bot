import os
import json
from pathlib import Path
import time

import numpy as np
import pytest

from services import subdub_smart_speech_identity as recovery
from services import subdub_multi_speaker_embedding_onnx as engine
from services import subdub_speaker_cast as cast
from services.subdub_blackboxes import auto_smart_multivoice as smart
from test_p0_subdub_smart_speech_view_recovery import _views


@pytest.mark.parametrize('count', [2, 3, 5, 8])
def test_isolated_bad_view_cannot_discard_supported_people(count):
    views, probs = _views(count)
    # At least 95% reliable windows; one noisy view is not a new speaker.
    for key in ('base_embeddings', 'shifted_embeddings'):
        views[key] = np.repeat(views[key], 2, axis=0)
        views[key] = np.concatenate((views[key], views[key][-1:]), axis=0)
    views['source_positions'] = np.arange(len(views['base_embeddings']))*.75
    views['speech_seconds'] = np.full(len(views['base_embeddings']), 1.5)
    probs = np.repeat(probs, 2).tolist() + [probs[-1]]
    views['shifted_embeddings'][0] = 0
    views['shifted_embeddings'][0, 20] = 1
    result = recovery.build_speech_identity_authority(views, probs)
    assert result['speaker_count'] == count
    assert len(result['labels']) == len(probs)
    assert result['labels'] == [i for i in range(count) for _ in range(24)] + [count-1]
    assert result['supported_window_recovery'] is True
    assert result['view_cosine_min'] >= engine.MIN_FIXED_VOCAL_VIEW_COSINE
    assert result['unreliable_view_window_count'] == 1


@pytest.mark.parametrize('registers', [['low','high'], ['high','high'], ['low','low'], ['high','low','low','high','low']])
def test_ambiguous_register_windows_do_not_recount_supported_people(registers):
    views, probs = _views(len(registers), registers)
    for i in range(len(probs)):
        if i % 12 < 4: probs[i] = .5
    result = recovery.build_speech_identity_authority(views, probs)
    assert result['speaker_count'] == len(registers)
    assert result['speaker_registers'] == registers
    assert len(result['labels']) == len(probs)


def test_many_bad_views_still_cannot_claim_recovery():
    views, probs = _views(2)
    views['shifted_embeddings'][:6] = 0
    views['shifted_embeddings'][:6, 20] = 1
    with pytest.raises(cast.AutoCastManualRequired):
        recovery.build_speech_identity_authority(views, probs)


def test_lost_speaker_support_does_not_invent_two_voices():
    views, probs = _views(2)
    probs[:12] = [.5]*12
    with pytest.raises(cast.AutoCastManualRequired):
        recovery.build_speech_identity_authority(views, probs)


def test_supported_retry_failure_remains_recognized_smart_uncertainty(monkeypatch):
    views, probs = _views(2)
    views['shifted_embeddings'][0] = 0
    views['shifted_embeddings'][0,20] = 1
    def unsupported(*_a, **_k):
        raise cast.AutoCastManualRequired() from ValueError('acoustic_cluster_unsupported')
    monkeypatch.setattr(engine, '_stable_cluster_view', unsupported)
    with pytest.raises(cast.AutoCastManualRequired) as error:
        recovery.build_speech_identity_authority(views, probs)
    assert str(error.value.__cause__) == 'fixed_vocal_smart_speech_partition_unstable'


def test_normalized_source_keeps_two_registers_with_full_window_coverage():
    folder = os.environ.get('SMART_SPEAKER_RECOVERY_EVIDENCE')
    if not folder: pytest.skip('Private source evidence not supplied')
    data = np.load(Path(folder)/'normalized_speech_evidence.npz')
    views = {'base_embeddings': data['base'], 'shifted_embeddings': data['shifted'],
             'source_positions': data['positions'], 'speech_seconds': data['speech']}
    result = recovery.build_speech_identity_authority(views, data['probabilities'].tolist())
    assert result['speaker_count'] == 2
    assert result['speaker_registers'] == ['low', 'high']
    assert len(result['labels']) == len(data['probabilities']) == 28
    assert result['speaker_count_views'] == [2,2,2]


@pytest.mark.parametrize('field', ['base_embeddings', 'shifted_embeddings', 'speech_seconds'])
def test_corrupt_evidence_cannot_enter_supported_recovery(field):
    views, probs = _views(2)
    views[field].flat[0] = np.nan
    with pytest.raises(cast.AutoCastManualRequired):
        recovery.build_speech_identity_authority(views, probs)


def test_normalized_real_word_mapping_routes_two_distinct_tts_casts_without_shift():
    folder = os.environ.get('SMART_SPEAKER_RECOVERY_EVIDENCE')
    if not folder: pytest.skip('Private source evidence not supplied')
    root = Path(folder)
    response = json.loads((root.parent/'subdub-posttts-20261003/response.json').read_text())
    words = [{'index': i, 'word': w.get('punctuated_word') or w['word'], 'start': w['start'], 'end': w['end']}
             for i,w in enumerate(response['results']['channels'][0]['alternatives'][0]['words'])]
    result = recovery.recover_speech_identity(np.load(root/'normalized_vocal16.npy'),
        str(root/'normalized44.pcm'), words, duration_seconds=(root/'normalized44.pcm').stat().st_size/(44100*4),
        deadline_monotonic=time.monotonic()+180, stop_requested=lambda:False)
    decision = smart.decide_smart_multivoice(result['segments'],
        validated_pools={'low':['male-approved'], 'high':['female-approved']},
        acoustic_classifications=result['smart_acoustic_classifications'])
    assert result['word_coverage_count'] == len(words) == 70
    assert result['detected_speaker_count'] == 2
    assert ' '.join(c['text'] for c in result['segments']) == ' '.join(w['word'] for w in words)
    assert set(decision.speaker_voice_map.values()) == {'male-approved', 'female-approved'}
    for c in result['segments']:
        assert any(abs(c['start']-w['start']) < .001 for w in words)
        assert any(abs(c['end']-w['end']) < .001 for w in words)
