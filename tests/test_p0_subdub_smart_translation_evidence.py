import copy
import asyncio
from pathlib import Path

import pytest

from services.subdub_blackboxes import auto_smart_multivoice as smart
from test_p0_subdub_canonical_receipt_presentation import _receipt_text
from test_p0_subdub_smart_standard_pipeline_orchestrator import SAMPLE_VALID_MP3


def _prepared():
    return {
        "source_segments": [{"cue_id": "c1", "text": "source sentence"},
                            {"cue_id": "c2", "text": "unchanged phrase"}],
        "output_segments": [{"cue_id": "c1", "text": "target sentence"},
                            {"cue_id": "c2", "text": "unchanged phrase"}],
    }


def test_unchanged_unknown_source_cue_is_exposed_without_mutating_text():
    prepared = _prepared()
    original = copy.deepcopy(prepared)
    evidence = smart._smart_translation_evidence(prepared, {"source_language": "auto", "target_language": "vi"})
    assert evidence["translation_source_cue_count"] == evidence["translation_output_cue_count"] == 2
    assert evidence["translation_missing_cue_ids"] == []
    assert evidence["translation_unchanged_cue_ids"] == ["c2"]
    assert evidence["translation_needs_review"] is True
    assert evidence["translation_quality_reason"] == "unchanged_source_text_uncertain"
    assert prepared == original


@pytest.mark.parametrize("state", [
    {"source_language": "vi", "target_language": "vi"},
    {"source_language": "en", "target_language": "source"},
    {"source_language": "en", "target_language": "vi", "dub_text_source": "source"},
])
def test_no_translation_request_does_not_create_equality_error(state):
    evidence = smart._smart_translation_evidence(_prepared(), state)
    assert evidence["translation_needs_review"] is False
    assert evidence["translation_quality_reason"] == "not_requested"


def test_missing_empty_and_duplicate_cues_have_explicit_evidence():
    prepared = _prepared()
    prepared["output_segments"] = [{"cue_id": "c1", "text": ""}, {"cue_id": "c1", "text": "duplicate"}]
    evidence = smart._smart_translation_evidence(prepared, {"target_language": "vi"})
    assert evidence["translation_missing_cue_ids"] == ["c1", "c2"]
    assert evidence["translation_invalid_identity_count"] == 1
    assert evidence["translation_needs_review"] is True


def test_unchanged_proper_name_is_uncertain_not_an_invented_translation():
    prepared = {"source_segments": [{"cue_id": "name", "text": "Santiago"}],
                "output_segments": [{"cue_id": "name", "text": "Santiago"}]}
    evidence = smart._smart_translation_evidence(prepared, {"source_language": "es", "target_language": "vi"})
    assert evidence["translation_unchanged_cue_ids"] == ["name"]
    assert evidence["translation_missing_cue_ids"] == []
    assert prepared["output_segments"][0]["text"] == "Santiago"


@pytest.mark.parametrize("lang", ["vi", "en"])
def test_smart_receipt_displays_generic_voice_counts_and_translation_review(lang):
    state = {
        "auto_speaker_lane": "auto_smart_multivoice", "auto_smart_multivoice_verified": True,
        "auto_detected_speaker_count": 2, "auto_effective_speaker_count": 2,
        "auto_distinct_voice_count": 2,
        "speaker_voice_map": {"s1": "voice_1", "s2": "voice_2"},
        "auto_smart_fallback_reason": "n2_strict_ambiguity_fallback",
        "translation_source_cue_count": 5, "translation_output_cue_count": 5,
        "translation_missing_cue_ids": [], "translation_unchanged_cue_ids": ["c5"],
        "translation_needs_review": True, "final_price_xu": 123,
    }
    text = _receipt_text(state, lang)
    voice_label = "Số giọng lồng tiếng đã dùng" if lang == "vi" else "Dubbing voices used"
    assert f"{voice_label}: <b>2</b>" in text
    assert "<b>5/5</b>" in text
    assert "<b>1</b>" in text
    assert ("cần kiểm tra" if lang == "vi" else "needs review") in text
    assert ("dự phòng" if lang == "vi" else "fallback") in text
    assert "<b>123 Xu</b>" in text


def test_manual_receipt_remains_identical_when_smart_evidence_is_present():
    fields = {"translation_needs_review": True, "translation_unchanged_cue_ids": ["c1"],
              "translation_source_cue_count": 1, "translation_output_cue_count": 1}
    assert _receipt_text(fields, "en") == _receipt_text({}, "en")


def test_unverified_generic_voice_count_is_not_reported_as_proof():
    text = _receipt_text({"auto_speaker_lane": "auto_smart_multivoice",
                          "auto_smart_multivoice_verified": False,
                          "auto_distinct_voice_count": 2, "auto_detected_speaker_count": 2}, "en")
    assert "Dubbing voices used: <b>2</b>" not in text


def test_evidence_survives_generic_blackbox_result_and_state(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"contract-source" * 100)
    prepared = _prepared()
    for collection in ("source_segments", "output_segments"):
        prepared[collection] = [{**c, "speaker_id": "chunk_00:speaker_0",
                                "start": float(i*2), "end": float(i*2+2)}
                               for i, c in enumerate(prepared[collection])]
    prepared.update(source_file=str(source), state={"auto_smart_generic_acoustic": True},
                    output_subtitle="1\n00:00:00,000 --> 00:00:02,000\ntarget sentence\n\n2\n00:00:02,000 --> 00:00:04,000\nunchanged phrase\n")

    async def synthesize(segments, **_kwargs):
        return {"provider": "offline", "chunks": [{"cue_id": c["cue_id"],
            "audio_bytes": SAMPLE_VALID_MP3, "audio_duration": 1.0} for c in segments]}

    result = asyncio.run(smart.run_auto_smart_multivoice_blackbox(
        state={"auto_speaker_lane": "auto_smart_multivoice", "mode": "subtitle_plus_dub",
               "target_language": "vi", "source_language": "auto", "input_duration": 4.0},
        prepare_subtitles=lambda *_args, **_kwargs: prepared,
        synthesize_segments=synthesize, build_timeline_audio=lambda *_args: (SAMPLE_VALID_MP3, "fixture"),
        render_video=lambda *_args, **_kwargs: (b"contract-video" * 100, "fixture"),
        validated_pools={"low": ["voice_1"], "high": ["voice_2"]},
        locked_speaker_voice_map={"chunk_00:speaker_0": "voice_1"},
        output_path=str(tmp_path / "result.mp4"), job_id="translation-fixture",
        checkpoint_workspace=str(tmp_path / "checkpoint"),
    ))
    assert result["ok"], result
    assert result["translation_unchanged_cue_ids"] == result["state"]["translation_unchanged_cue_ids"] == ["c2"]
    assert result["state"]["translation_needs_review"] is True
    assert result["output_segments"][1]["text"] == "unchanged phrase"
