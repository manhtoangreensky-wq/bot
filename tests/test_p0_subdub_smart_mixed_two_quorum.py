import os
from pathlib import Path

import numpy as np
import pytest

from services import subdub_multi_speaker_embedding_onnx as engine
from services import subdub_smart_speech_identity as recovery
from services import subdub_speaker_cast as cast
from services.subdub_blackboxes import auto_smart_multivoice as smart
from test_p0_subdub_smart_speech_view_recovery import _views


def _collapsed_count_view(monkeypatch, collapsed=0, counts=None, disagree=False):
    original = engine._stable_cluster_view
    calls = []

    def measure(matrix, positions, **kwargs):
        index = len(calls) % 3
        calls.append(index)
        count, labels, eigenvalues = original(matrix, positions, **kwargs)
        requested = counts[index] if counts is not None else (1 if index == collapsed else count)
        if requested == 1:
            labels = np.zeros(len(labels), dtype=np.int64)
        if disagree and index == 2:
            labels = labels.copy()
            labels[:4] = 1 - labels[:4]
        return requested, labels, eigenvalues

    monkeypatch.setattr(engine, '_stable_cluster_view', measure)


@pytest.mark.parametrize('collapsed', [0, 1, 2])
def test_two_supported_views_and_opposite_registers_survive_one_collapsed_count(monkeypatch, collapsed):
    views, probabilities = _views(2)
    _collapsed_count_view(monkeypatch, collapsed)
    result = recovery.build_speech_identity_authority(views, probabilities)
    assert result['speaker_count'] == 2
    assert result['speaker_registers'] == ['low', 'high']
    assert result['labels'] == [0]*12 + [1]*12
    assert result['speaker_count_views'].count(2) == 2
    assert result['mixed_two_count_recovery'] is True
    assert min(result[k] for k in ('base_shift_agreement', 'base_aggregate_agreement', 'shift_aggregate_agreement')) >= .95


@pytest.mark.parametrize('registers', [['low', 'low'], ['high', 'high']])
def test_count_disagreement_without_opposite_registers_still_rejects(monkeypatch, registers):
    views, probabilities = _views(2, registers)
    _collapsed_count_view(monkeypatch)
    with pytest.raises(cast.AutoCastManualRequired):
        recovery.build_speech_identity_authority(views, probabilities)


@pytest.mark.parametrize('counts', [[1, 1, 2], [1, 1, 1], [2, 2, 3], [3, 2, 3]])
def test_non_two_quorum_cannot_force_mixed_two_people(monkeypatch, counts):
    views, probabilities = _views(2)
    _collapsed_count_view(monkeypatch, counts=counts)
    with pytest.raises(cast.AutoCastManualRequired):
        recovery.build_speech_identity_authority(views, probabilities)


def test_two_count_views_must_agree_on_partition_not_just_count(monkeypatch):
    views, probabilities = _views(2)
    _collapsed_count_view(monkeypatch, disagree=True)
    with pytest.raises(cast.AutoCastManualRequired):
        recovery.build_speech_identity_authority(views, probabilities)


def test_three_opposite_votes_are_not_enough_for_exact_two_recovery(monkeypatch):
    views, probabilities = _views(2)
    probabilities[:12] = [.01]*3 + [.5]*9
    _collapsed_count_view(monkeypatch)
    with pytest.raises(cast.AutoCastManualRequired):
        recovery.build_speech_identity_authority(views, probabilities)


def test_unreliable_view_fraction_still_rejects_before_count_quorum(monkeypatch):
    views, probabilities = _views(2)
    views['shifted_embeddings'][:3] = 0
    views['shifted_embeddings'][:3, 20] = 1
    _collapsed_count_view(monkeypatch)
    with pytest.raises(cast.AutoCastManualRequired):
        recovery.build_speech_identity_authority(views, probabilities)
    assert engine.MIN_FIXED_VOCAL_VIEW_COSINE == .98


def test_fresh_live_original_audio_keeps_two_distinct_cast_routes():
    folder = os.environ.get('SMART_FRESH_IDENTITY_EVIDENCE')
    if not folder:
        pytest.skip('Private fresh live evidence not supplied')
    data = np.load(Path(folder)/'source_fresh_speech.npz')
    views = {'base_embeddings': data['base'], 'shifted_embeddings': data['shifted'],
             'source_positions': data['positions'], 'speech_seconds': data['speech']}
    result = recovery.build_speech_identity_authority(views, data['probabilities'].tolist())
    assert result['speaker_count'] == 2
    assert result['speaker_registers'] == ['low', 'high']
    assert result['speaker_count_views'] == [1, 2, 2]
    assert len(result['labels']) == 28
    assert result['mixed_two_count_recovery'] is True
    classes = {cast.normalized_speaker_key(0, i): {'voice_register': register,
               'confidence': result['speaker_register_confidences'][i]}
               for i, register in enumerate(result['speaker_registers'])}
    cues = [{'cue_id': 'cue-'+str(i), 'speaker_id': label, 'start': i*2., 'end': i*2.+1., 'text': 'fixture'}
            for i, label in enumerate(classes)]
    decision = smart.decide_smart_multivoice(cues, validated_pools={'low': ['male-approved'], 'high': ['female-approved']},
                                            acoustic_classifications=classes)
    assert set(decision.speaker_voice_map.values()) == {'male-approved', 'female-approved'}
