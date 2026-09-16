from __future__ import annotations

import asyncio

import bot
import pytest
from services.subdub_blackboxes import auto_multi_speaker_v2


def _source_segments(cue_count: int = 67, speaker_count: int = 3) -> list[dict]:
    return [
        {
            "cue_id": f"cue-{index + 1:04d}-fixture",
            "index": index + 1,
            "start": float(index * 2),
            "end": float(index * 2 + 1.8),
            "text": f"source cue {index + 1}",
            "speaker": index % speaker_count,
            "speaker_id": f"chunk_00:speaker_{index % speaker_count}",
            "speaker_confidence": 0.95,
            "chunk_index": 0,
            "voice_register": "high" if index % speaker_count == 0 else "low",
        }
        for index in range(cue_count)
    ]


@pytest.mark.parametrize(
    ("cue_count", "speaker_count"),
    ((3, 3), (25, 5), (67, 3), (70, 8)),
)
def test_v2_post_prepare_restores_lost_translated_segments_before_exact_gate(
    monkeypatch,
    cue_count,
    speaker_count,
):
    source_segments = _source_segments(cue_count, speaker_count)
    translated_segments = [
        {**segment, "text": f"translated cue {index + 1}"}
        for index, segment in enumerate(source_segments)
    ]
    state = {
        "subdub_engine_selected": "auto_multi_speaker_v2",
        "mode": "subtitle_plus_dub",
        "video_processing_mode": "subtitle_plus_dub",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "auto_speaker_lane": "multi",
        "target_language": "English",
        "translate_requested": "1",
        "dub_text_source": "translated",
        "subdub_final_confirmed": True,
        "_pipeline_is_admin": True,
        "_pipeline_job_id": "v2-post-prepare-fixture",
        "_pipeline_job_key": "v2-post-prepare-fixture-key",
        "_pipeline_owner_user_id": "admin-fixture",
        "_pipeline_chat_id": "admin-fixture",
        "auto_exact_session_nonce": "v2-post-prepare-nonce",
    }
    prepared = {
        "state": dict(state),
        "source_subtitle": bot.video_dubbing_srt_from_segments(source_segments),
        "source_segments": source_segments,
        "output_subtitle": bot.video_dubbing_srt_from_segments(translated_segments),
        # Reproduce the observed post-prepare loss: the translated artifact
        # survived, but the in-memory segment list did not.
        "output_segments": [],
        "source_bytes": b"provider-free-source-bytes",
    }

    before = bot.subtitle_dub_product_pipeline.resolve_subdub_dub_audio_policy(
        prepared["state"],
        prepared,
    )
    assert before["dub_text_source"] == "translated"
    assert before["tts_segments"] == []
    assert bot._subdub_auto_selected_text(before["tts_segments"]) == ""

    captured: dict = {}
    monkeypatch.setattr(bot, "subdub_auto_speaker_route_enabled", lambda _state: True)
    monkeypatch.setattr(
        bot,
        "_subdub_auto_actual_components",
        lambda _prepared, _state, selected_text: (
            len(selected_text.split()),
            100,
            50,
        ),
    )
    monkeypatch.setattr(
        bot.subdub_auto_word_pricing,
        "auto_exact_confirmation_state",
        lambda **_kwargs: {"exact_confirmation_required": True},
    )

    def build_receipt(
        received_prepared,
        _state,
        *,
        policy,
        selected_segments,
        selected_text,
        **_kwargs,
    ):
        captured.update(
            {
                "prepared": received_prepared,
                "policy": policy,
                "selected_segments": list(selected_segments),
                "selected_text": selected_text,
            }
        )
        return {
            "ok": True,
            "receipt": {
                "session_nonce": "v2-post-prepare-nonce",
                "consumed": False,
                "claim_state": "unconsumed",
            },
            "cache": {},
            "resume_state": {},
        }

    monkeypatch.setattr(bot, "_subdub_auto_build_exact_receipt", build_receipt)
    monkeypatch.setattr(
        bot,
        "update_subtitle_dub_pipeline_job",
        lambda job_key, **fields: {"job_key": job_key, **fields},
    )
    monkeypatch.setattr(
        bot,
        "persist_subtitle_dub_pipeline_job_snapshot",
        lambda *_args, **_kwargs: True,
    )

    result = asyncio.run(bot._subdub_auto_post_prepare_gate(prepared, state))

    assert result == {"continue": True}
    assert len(prepared["output_segments"]) == cue_count
    assert len(captured["selected_segments"]) == cue_count
    assert [segment["text"] for segment in captured["selected_segments"]] == [
        segment["text"] for segment in translated_segments
    ]
    assert "source cue" not in captured["selected_text"]
    assert [
        (
            segment["cue_id"],
            segment["speaker_id"],
            segment["start"],
            segment["end"],
        )
        for segment in captured["selected_segments"]
    ] == [
        (
            segment["cue_id"],
            segment["speaker_id"],
            segment["start"],
            segment["end"],
        )
        for segment in source_segments
    ]
    casts = {
        f"chunk_00:speaker_{speaker_index}": {
            "speaker_id": f"chunk_00:speaker_{speaker_index}",
            "voice_register": "high" if speaker_index == 0 else "low",
            "voice_id": f"fixture-voice-{speaker_index}",
        }
        for speaker_index in range(speaker_count)
    }
    annotated, assignments = (
        auto_multi_speaker_v2._annotate_multi_v2_prepared_assignments(
            prepared,
            casts,
        )
    )
    downstream_selected = (
        auto_multi_speaker_v2._validated_multi_v2_policy_segments(
            prepared["state"],
            annotated,
            assignments,
        )
    )
    assert [segment["text"] for segment in downstream_selected] == [
        segment["text"] for segment in translated_segments
    ]


def test_v2_post_prepare_uses_outer_route_and_srt_when_inner_segments_are_stale(
    monkeypatch,
):
    source_segments = _source_segments(69, 3)
    translated_segments = [
        {**segment, "text": f"translated live cue {index + 1}"}
        for index, segment in enumerate(source_segments)
    ]
    state = {
        "subdub_engine_selected": "auto_multi_speaker_v2",
        "mode": "subtitle_plus_dub",
        "video_processing_mode": "subtitle_plus_dub",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "auto_speaker_lane": "multi",
        "target_language": "English",
        "translate_requested": "1",
        "dub_text_source": "translated",
        "subdub_final_confirmed": True,
        "_pipeline_is_admin": True,
        "_pipeline_job_id": "4b6751d819-live-shape",
        "_pipeline_job_key": "4b6751d819-live-shape-key",
        "_pipeline_owner_user_id": "admin-live-shape",
        "_pipeline_chat_id": "admin-live-shape",
        "auto_exact_session_nonce": "4b6751d819-nonce",
    }
    inner_state = {
        key: value
        for key, value in state.items()
        if key != "subdub_engine_selected"
    }
    prepared = {
        "state": inner_state,
        "source_subtitle": bot.video_dubbing_srt_from_segments(source_segments),
        "source_segments": source_segments,
        "output_subtitle": bot.video_dubbing_srt_from_segments(translated_segments),
        "output_segments": [
            {**segment, "text": ""}
            for segment in source_segments
        ],
        "source_bytes": b"provider-free-live-shape-source",
    }
    captured: dict = {}

    monkeypatch.setattr(bot, "subdub_auto_speaker_route_enabled", lambda _state: True)
    monkeypatch.setattr(
        bot,
        "_subdub_auto_actual_components",
        lambda _prepared, _state, selected_text: (
            len(selected_text.split()),
            100,
            50,
        ),
    )
    monkeypatch.setattr(
        bot.subdub_auto_word_pricing,
        "auto_exact_confirmation_state",
        lambda **_kwargs: {"exact_confirmation_required": True},
    )

    def build_receipt(
        received_prepared,
        _state,
        *,
        selected_segments,
        selected_text,
        **_kwargs,
    ):
        captured["prepared"] = received_prepared
        captured["selected_segments"] = list(selected_segments)
        captured["selected_text"] = selected_text
        return {
            "ok": True,
            "receipt": {
                "session_nonce": "4b6751d819-nonce",
                "consumed": False,
                "claim_state": "unconsumed",
            },
            "cache": {},
            "resume_state": {},
        }

    monkeypatch.setattr(bot, "_subdub_auto_build_exact_receipt", build_receipt)
    monkeypatch.setattr(
        bot,
        "update_subtitle_dub_pipeline_job",
        lambda job_key, **fields: {"job_key": job_key, **fields},
    )
    monkeypatch.setattr(
        bot,
        "persist_subtitle_dub_pipeline_job_snapshot",
        lambda *_args, **_kwargs: True,
    )

    result = asyncio.run(bot._subdub_auto_post_prepare_gate(prepared, state))

    assert result == {"continue": True}
    assert len(captured["selected_segments"]) == 69
    assert [item["text"] for item in captured["selected_segments"]] == [
        item["text"] for item in translated_segments
    ]
    assert prepared["state"]["subdub_engine_selected"] == "auto_multi_speaker_v2"


@pytest.mark.parametrize("corruption", ("truncated", "extra", "blank"))
def test_v2_post_prepare_recovery_fails_closed_on_incomplete_translation(
    corruption,
):
    source_segments = _source_segments(3, 3)
    translated_segments = [
        {**segment, "text": f"translated cue {index + 1}"}
        for index, segment in enumerate(source_segments)
    ]
    if corruption == "truncated":
        translated_segments.pop()
    elif corruption == "extra":
        translated_segments.append(
            {
                **source_segments[-1],
                "index": 4,
                "start": 6.0,
                "end": 7.8,
                "text": "unexpected extra translated cue",
            }
        )
    else:
        translated_segments[1] = {**translated_segments[1], "text": ""}
    state = {"subdub_engine_selected": "auto_multi_speaker_v2"}
    prepared = {
        "source_segments": source_segments,
        "output_segments": [],
        "output_subtitle": bot.video_dubbing_srt_from_segments(translated_segments),
    }

    restored = bot._subdub_auto_v2_restore_prepared_selection(prepared, state)

    assert restored["output_segments"] == []
