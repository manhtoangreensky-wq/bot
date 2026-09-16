import pytest
import math
import hashlib
import json
import os
import bot
from services import subtitle_dub_product_pipeline
from services import subdub_auto_word_pricing
from services.subdub_blackboxes import auto_multi_speaker_v2, auto_multi_speaker, auto_speaker
from services import subdub_speaker_cast as speaker_cast


def _generate_fixture_cues(count: int = 68):
    cues = []
    source_segments = []
    output_segments = []
    for i in range(1, count + 1):
        cid = f"cue-{i:04d}-fixture"
        st = float(i - 1) * 2.5
        et = st + 2.0
        spk = (i % 3)
        spk_id = f"chunk_00:speaker_{spk}"
        reg = "high" if spk == 0 else "low"
        cues.append({
            "chunk_index": 0,
            "cue_id": cid,
            "start_ms": int(st * 1000),
            "end_ms": int(et * 1000),
            "speaker": spk,
            "speaker_id": spk_id,
            "voice_register": reg,
        })
        source_segments.append({
            "index": i,
            "id": cid,
            "cue_id": cid,
            "start": st,
            "end": et,
            "text": f"Source spoken text for cue {i}",
            "speaker": spk,
            "speaker_id": spk_id,
        })
        output_segments.append({
            "index": i,
            "id": cid,
            "cue_id": cid,
            "start": st,
            "end": et,
            "text": f"Lời thoại tiếng Việt dịch cho cue {i}",
            "speaker": spk,
            "speaker_id": spk_id,
        })
    return cues, source_segments, output_segments


def _sample_casts():
    return {
        "chunk_00:speaker_0": {"speaker_id": "chunk_00:speaker_0", "voice_register": "high", "voice_id": "voice_high_0"},
        "chunk_00:speaker_1": {"speaker_id": "chunk_00:speaker_1", "voice_register": "low", "voice_id": "voice_low_1"},
        "chunk_00:speaker_2": {"speaker_id": "chunk_00:speaker_2", "voice_register": "low", "voice_id": "voice_low_2"},
    }


def test_spec02_source_cue_count_and_uniqueness():
    cues, source_segs, _ = _generate_fixture_cues(68)
    assert len(cues) == 68
    assert len(source_segs) == 68
    cue_ids = [c["cue_id"] for c in cues]
    assert len(set(cue_ids)) == 68
    speakers = set(c["speaker"] for c in cues)
    assert speakers == {0, 1, 2}


def test_spec02_cue_bijection_and_identity_contract():
    _, source_segs, output_segs = _generate_fixture_cues(68)
    casts = _sample_casts()
    prepared = {
        "source_segments": source_segs,
        "output_segments": output_segs,
    }
    annotated, assignments = auto_multi_speaker_v2._annotate_multi_v2_prepared_assignments(
        prepared, casts
    )
    assert len(annotated["source_segments"]) == 68
    assert len(annotated["output_segments"]) == 68
    assert len(assignments) == 68

    expected_voice_ids = {c["voice_id"] for c in casts.values()}
    for cid, (register, v_id, st, et) in assignments.items():
        assert cid.startswith("cue-")
        assert register in ("high", "low")
        assert v_id in expected_voice_ids


def test_spec02_rounding_drift_tolerance():
    _, source_segs, output_segs = _generate_fixture_cues(68)
    casts = _sample_casts()
    drifted_segs = [
        {**s, "start": s["start"] + 0.0008, "end": s["end"] + 0.0008}
        for s in output_segs
    ]
    _, assignments = auto_multi_speaker_v2._annotate_multi_v2_prepared_assignments(
        {"source_segments": source_segs, "output_segments": drifted_segs}, casts
    )
    assert len(assignments) == 68

    excess_drift_segs = [
        {**s, "start": s["start"] + 0.0015, "end": s["end"] + 0.0015}
        for s in output_segs
    ]
    with pytest.raises(speaker_cast.AutoCastUnavailable):
        auto_multi_speaker_v2._annotate_multi_v2_prepared_assignments(
            {"source_segments": source_segs, "output_segments": excess_drift_segs}, casts
        )


def test_spec02_target_language_semantics_and_policy():
    _, source_segs, output_segs = _generate_fixture_cues(68)
    state_none = {"target_language": None, "mode": "subtitle_plus_dub"}
    prepared_none = {"source_segments": source_segs, "output_segments": []}
    policy_none = subtitle_dub_product_pipeline.resolve_subdub_dub_audio_policy(
        state_none, prepared_none
    )
    assert policy_none["dub_text_source"] == "source"
    assert len(policy_none["tts_segments"]) == 68

    state_vi = {"target_language": "vi", "mode": "subtitle_plus_dub"}
    prepared_vi = {"source_segments": source_segs, "output_segments": output_segs}
    policy_vi = subtitle_dub_product_pipeline.resolve_subdub_dub_audio_policy(
        state_vi, prepared_vi
    )
    assert policy_vi["dub_text_source"] == "translated"
    assert len(policy_vi["tts_segments"]) == 68


def test_spec02_post_prepare_balance_and_quote_no_mutation(monkeypatch):
    _, source_segs, output_segs = _generate_fixture_cues(68)
    monkeypatch.setattr(bot, "SUBDUB_AUTO_SPEAKER_ACTIVATION_ENABLED", True)
    monkeypatch.setattr(bot, "subdub_auto_provider_capacity_ready", lambda *a, **kw: True)
    monkeypatch.setattr(bot, "_subdub_auto_read_balance_xu", lambda uid: 1352)

    state = {
        "job_id": "50bff8620870539176fa",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "auto_speaker_lane": "multi",
        "mode": "subtitle_plus_dub",
        "_pipeline_owner_user_id": 7714990570,
        "target_language": "vi",
        "input_save": {"original_filename": "test mới multi.mp4"},
    }
    prepared = {
        "source_segments": source_segs,
        "output_segments": output_segs,
        "state": state,
    }
    policy = subtitle_dub_product_pipeline.resolve_subdub_dub_audio_policy(state, prepared)
    tts_segments = policy["tts_segments"]
    selected_text = bot._subdub_auto_selected_text(tts_segments)
    actual_words, actual_auto_xu, actual_subtitle_xu = bot._subdub_auto_actual_components(
        prepared, state, selected_text
    )
    total_xu = actual_auto_xu + actual_subtitle_xu
    assert actual_words > 0
    assert total_xu > 0
    assert 1352 >= total_xu
