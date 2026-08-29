from __future__ import annotations

from array import array
import asyncio
import importlib
import importlib.util
import inspect
from pathlib import Path
import sys
import time

import pytest

import bot
from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_speaker


EXACT_AUTO_STATE = {
    "voice_kind": "auto_speaker_gender",
    "voice_selection_mode": "auto_speaker",
}


def _multi_module():
    spec = importlib.util.find_spec(
        "services.subdub_blackboxes.auto_multi_speaker"
    )
    assert spec is not None, "multi-speaker blackbox module is missing"
    return importlib.import_module(
        "services.subdub_blackboxes.auto_multi_speaker"
    )


def _callbacks(markup) -> list[str]:
    return [
        str(button.callback_data or "")
        for row in markup.inline_keyboard
        for button in row
    ]


def _patch_one_frame_evidence(monkeypatch) -> None:
    frame_estimates = iter(((220.0, 0.74), None, None, None))
    monkeypatch.setattr(
        speaker_cast,
        "_estimate_frame_pitch_yin",
        lambda *_args, **_kwargs: next(frame_estimates),
    )
    monkeypatch.setattr(
        speaker_cast,
        "_frame_competing_pitch",
        lambda *_args, **_kwargs: (0.0, 0.0),
    )
    monkeypatch.setattr(
        speaker_cast,
        "_refine_full_rate_pitch",
        lambda _samples, estimated_hz, **_kwargs: estimated_hz,
    )
    monkeypatch.setattr(
        speaker_cast,
        "_pitch_spectrum_metrics",
        lambda *_args, **_kwargs: (1.0, 1.0),
    )


def test_auto_choices_set_and_clear_only_the_multi_marker(monkeypatch):
    monkeypatch.setattr(
        bot,
        "subdub_auto_provider_capacity_ready",
        lambda *_args, **_kwargs: True,
    )

    old = bot.subdub_apply_voice_choice(
        {},
        "auto_speaker_gender",
        activation_enabled=True,
    )
    multi = bot.subdub_apply_voice_choice(
        {},
        "auto_multi_speaker",
        activation_enabled=True,
    )
    manual = bot.subdub_apply_voice_choice(
        multi,
        "default_female",
        activation_enabled=True,
    )

    assert old == EXACT_AUTO_STATE
    assert multi["voice_kind"] == old["voice_kind"]
    assert multi["voice_selection_mode"] == old["voice_selection_mode"]
    assert multi["auto_speaker_lane"] == "multi"
    assert "auto_speaker_lane" not in manual
    assert "voice_selection_mode" not in manual


def test_switching_auto_profiles_clears_the_previous_profile_cache():
    stale_fields = {
        "speaker_sidecar_path": "C:/job/speaker_cast.sidecar.json",
        "speaker_sidecar_sha256": "a" * 64,
        "speaker_classifications": {"old": True},
        "speaker_casts": {"old": True},
        "per_cue_voice_assignments": [{"old": True}],
        "auto_exact_receipt": {"claim_state": "resuming"},
        "auto_exact_cache": {"prepared": "old"},
        "auto_exact_resume_state": {"mode": "dub"},
        "auto_exact_claim_token": "old-claim",
        "auto_exact_receipt_confirmed": True,
        "auto_quote_billable_words": 42,
    }
    multi = bot.subdub_apply_voice_choice(
        {**EXACT_AUTO_STATE, **stale_fields},
        "auto_multi_speaker",
        activation_enabled=True,
    )

    assert multi["auto_speaker_lane"] == "multi"
    assert not (set(stale_fields) & set(multi))

    old = bot.subdub_apply_voice_choice(
        {**multi, **stale_fields},
        "auto_speaker_gender",
        activation_enabled=True,
    )

    assert old["voice_kind"] == "auto_speaker_gender"
    assert old["voice_selection_mode"] == "auto_speaker"
    assert "auto_speaker_lane" not in old
    assert not (set(stale_fields) & set(old))


@pytest.mark.parametrize(
    "state",
    (
        {"mode": "dub"},
        {
            "mode": "subtitle_plus_dub",
            "active_flow": "subtitle_plus_dub",
            "requested_mode": "subtitle_plus_dub",
        },
    ),
)
def test_voice_menus_place_named_two_and_multi_auto_choices_on_one_row(
    monkeypatch,
    state,
):
    monkeypatch.setattr(
        bot,
        "subdub_auto_provider_capacity_ready",
        lambda *_args, **_kwargs: True,
    )

    markup = bot.video_dubbing_voice_keyboard("vi", state)
    callbacks = _callbacks(markup)
    auto_row = next(
        row
        for row in markup.inline_keyboard
        if any(
            button.callback_data == "videodub|voice|auto_speaker_gender"
            for button in row
        )
    )

    assert callbacks.count("videodub|voice|auto_speaker_gender") == 1
    assert callbacks.count("videodub|voice|auto_multi_speaker") == 1
    assert [button.callback_data for button in auto_row] == [
        "videodub|voice|auto_speaker_gender",
        "videodub|voice|auto_multi_speaker",
    ]
    assert [button.text for button in auto_row] == [
        "👥 Tự động 2 giọng",
        "👥 Tự động nhiều giọng",
    ]


def test_old_and_multi_states_select_different_blackboxes(monkeypatch):
    multi_module = _multi_module()
    monkeypatch.setattr(
        bot,
        "subdub_auto_provider_capacity_ready",
        lambda *_args, **_kwargs: True,
    )
    selector = getattr(bot, "subdub_auto_blackbox_runner", None)
    multi_route = getattr(
        bot,
        "subdub_auto_multi_speaker_route_enabled",
        None,
    )

    assert callable(selector)
    assert callable(multi_route)
    assert selector(EXACT_AUTO_STATE) is auto_speaker.run_auto_speaker_blackbox
    assert selector(
        {**EXACT_AUTO_STATE, "auto_speaker_lane": "multi"}
    ) is multi_module.run_auto_multi_speaker_blackbox
    assert multi_route(EXACT_AUTO_STATE) is False
    assert multi_route(
        {**EXACT_AUTO_STATE, "auto_speaker_lane": "multi"}
    ) is True


@pytest.mark.parametrize(
    ("state", "expected_label"),
    (
        (EXACT_AUTO_STATE, "👥 Tự động 2 giọng"),
        (
            {**EXACT_AUTO_STATE, "auto_speaker_lane": "multi"},
            "👥 Tự động nhiều giọng",
        ),
    ),
)
def test_auto_confirmation_names_the_selected_lane(
    monkeypatch,
    state,
    expected_label,
):
    monkeypatch.setattr(
        bot,
        "subdub_auto_provider_capacity_ready",
        lambda *_args, **_kwargs: True,
    )

    text = bot.video_dubbing_confirm_text(
        {**state, "mode": "dub"},
        "vi",
    )

    assert f"<b>{expected_label}</b>" in text


def test_multi_adapter_preserves_exact_price_fields_created_by_preflight(
    monkeypatch,
):
    multi_module = _multi_module()

    async def copied_lane_state_before_preflight(**payload):
        payload["state"].update({
            "auto_exact_receipt_confirmed": True,
            "auto_exact_actual_billable_words": 181,
            "auto_exact_actual_auto_xu": 91,
            "auto_exact_actual_subtitle_xu": 0,
            "auto_exact_actual_total_xu": 91,
            "auto_exact_claim_token": "claimed-once",
        })
        return {
            "ok": True,
            "state": {
                **EXACT_AUTO_STATE,
                "auto_speaker_lane": "multi",
                "protected_lane_state": "kept",
            },
        }

    monkeypatch.setattr(
        multi_module,
        "_run_isolated_multi_speaker_blackbox",
        copied_lane_state_before_preflight,
    )
    result = asyncio.run(
        multi_module.run_auto_multi_speaker_blackbox(
            extract_pcm=lambda *_args, **_kwargs: "unused.pcm",
            state={**EXACT_AUTO_STATE, "auto_speaker_lane": "multi"},
        )
    )

    assert result["state"]["protected_lane_state"] == "kept"
    assert result["state"]["auto_exact_receipt_confirmed"] is True
    assert result["state"]["auto_exact_actual_billable_words"] == 181
    assert result["state"]["auto_exact_actual_auto_xu"] == 91
    assert result["state"]["auto_exact_actual_subtitle_xu"] == 0
    assert result["state"]["auto_exact_actual_total_xu"] == 91
    assert result["state"]["auto_exact_claim_token"] == "claimed-once"


def test_old_and_multi_jobs_have_separate_retry_leases(monkeypatch):
    monkeypatch.setattr(
        bot,
        "subdub_auto_provider_capacity_ready",
        lambda *_args, **_kwargs: True,
    )
    base = {
        "source_file_unique_id": "same-source",
        "mode": "dub",
        "active_flow": "dub_audio",
    }

    old_key = bot.subtitle_dub_pipeline_job_key(
        7,
        8,
        {**base, **EXACT_AUTO_STATE},
    )
    multi_key = bot.subtitle_dub_pipeline_job_key(
        7,
        8,
        {
            **base,
            **EXACT_AUTO_STATE,
            "auto_speaker_lane": "multi",
        },
    )

    assert old_key.endswith("|auto_speaker")
    assert multi_key.endswith("|auto_multi_speaker")
    assert old_key != multi_key


def test_multi_marker_does_not_change_auto_pricing(monkeypatch):
    monkeypatch.setattr(
        bot,
        "subdub_auto_provider_capacity_ready",
        lambda *_args, **_kwargs: True,
    )
    priced = {
        "mode": "dub",
        "billing_chars": 120,
        "auto_quote_billable_words": 24,
        "auto_quote_exact_known": True,
    }
    old = {**priced, **EXACT_AUTO_STATE}
    multi = {
        **priced,
        **EXACT_AUTO_STATE,
        "auto_speaker_lane": "multi",
    }

    assert auto_speaker.is_auto_speaker_state(old)
    assert auto_speaker.is_auto_speaker_state(multi)
    assert bot.video_dubbing_invoice_breakdown(old) == (
        bot.video_dubbing_invoice_breakdown(multi)
    )


def test_shared_classifier_rejects_one_frame_without_multi_relaxation(monkeypatch):
    raw = b"\0" * speaker_cast.PCM_WINDOW_BYTES
    _patch_one_frame_evidence(monkeypatch)
    result = speaker_cast._estimate_window_pitch(
        raw,
        deadline_monotonic=time.monotonic() + 10.0,
        stop_requested=lambda: False,
    )

    assert result is None
    assert speaker_cast._MIN_PITCH_FRAMES == 2
    assert "allow_single_pitch_frame" not in inspect.signature(
        speaker_cast._estimate_window_pitch
    ).parameters


def test_multi_adapter_rediarizes_one_underclustered_provider_label_before_gate(
    tmp_path,
    monkeypatch,
):
    multi_module = _multi_module()
    labels = ["chunk_00:speaker_0", "chunk_00:speaker_1"]
    cue_speakers = [0, 1, 0, 1, 1, 1]
    source_segments = bot.subdub_canonical_auto_speaker_segments(
        [
            {
                "index": index + 1,
                "start": float(index),
                "end": float(index + 1),
                "text": f"cue {index + 1}",
                "speaker": speaker,
                "speaker_confidence": 0.9,
                "speaker_id": labels[speaker],
                "chunk_index": 0,
            }
            for index, speaker in enumerate(cue_speakers)
        ],
        extraction_source="asr",
    )
    sidecar = speaker_cast.build_sidecar(
        source_segments,
        media_sha256="a" * 64,
        subtitle_sha256="b" * 64,
    )
    receipt = speaker_cast.persist_sidecar(
        sidecar,
        workspace=str(tmp_path),
    )
    prepared = {
        "source_segments": source_segments,
        "output_segments": [dict(item) for item in source_segments],
        "media_sha256": "a" * 64,
        "subtitle_sha256": "b" * 64,
        "state": {
            "_pipeline_workspace": str(tmp_path),
            "speaker_sidecar_path": receipt["path"],
            "speaker_sidecar_sha256": receipt["sha256"],
        },
    }

    pcm_path = tmp_path / "underclustered.pcm"
    pcm_path.write_bytes(b"\0" * 64)
    captured = {"extract_calls": 0}

    async def base_prepare(_state, *, require_auto_cast):
        assert require_auto_cast is True
        return prepared

    async def base_extract(_prepared, _state, **kwargs):
        captured["extract_calls"] += 1
        captured["extract_kwargs"] = kwargs
        return str(pcm_path)

    async def provider_rediarize(segments, **kwargs):
        captured["rediarize_calls"] = captured.get("rediarize_calls", 0) + 1
        captured["rediarize_pcm"] = kwargs.get("pcm_path")
        captured["provider_call_allowed"] = kwargs.get("provider_call_allowed")
        speaker_ids = [0, 1, 0, 1, 2, 2]
        return {
            "ok": True,
            "status": "PASS",
            "provider": "gemini_transcribe_multi_diarization",
            "detected_speaker_count": 3,
            "segments": [
                {
                    **segment,
                    "speaker": speaker,
                    "speaker_id": f"chunk_00:speaker_{speaker}",
                    "speaker_confidence": 0.95,
                }
                for segment, speaker in zip(segments, speaker_ids, strict=True)
            ],
        }

    async def fake_old_blackbox(**kwargs):
        refined = await kwargs["prepare_subtitles"](
            kwargs["state"],
            require_auto_cast=True,
        )
        return {"ok": True, "status": "fixture", "prepared": refined}

    monkeypatch.setattr(
        multi_module,
        "_run_isolated_multi_speaker_blackbox",
        fake_old_blackbox,
    )
    result = asyncio.run(
        multi_module.run_auto_multi_speaker_blackbox(
            lane_mode="subtitle_plus_dub",
            extract_pcm=base_extract,
            prepare_subtitles=base_prepare,
            rediarize_underclustered=provider_rediarize,
            state={
                **EXACT_AUTO_STATE,
                "auto_speaker_lane": "multi",
                "subdub_final_confirmed": "1",
            },
        )
    )

    refined = result["prepared"]
    assert [item["speaker_id"] for item in refined["source_segments"]] == [
        "chunk_00:speaker_0",
        "chunk_00:speaker_1",
        "chunk_00:speaker_0",
        "chunk_00:speaker_1",
        "chunk_00:speaker_2",
        "chunk_00:speaker_2",
    ]
    assert [item["speaker_id"] for item in refined["output_segments"]] == [
        item["speaker_id"] for item in refined["source_segments"]
    ]
    refined_state = refined["state"]
    assert refined_state["multi_diarization_attempted"] is True
    assert refined_state["multi_diarization_provider"] == (
        "gemini_transcribe_multi_diarization"
    )
    assert refined_state["multi_diarization_status"] == "PASS"
    assert refined_state["multi_diarization_speaker_count"] == 3
    refined_sidecar = speaker_cast.load_sidecar(
        refined_state["speaker_sidecar_path"],
        expected_sha256=refined_state["speaker_sidecar_sha256"],
        workspace=str(tmp_path),
    )
    assert speaker_cast.ordered_auto_speaker_labels(
        refined_sidecar["cues"]
    ) == [
        "chunk_00:speaker_0",
        "chunk_00:speaker_1",
        "chunk_00:speaker_2",
    ]
    assert captured == {
        "extract_calls": 1,
        "extract_kwargs": {
            "channels": 2,
            "sample_rate": 44_100,
            "sample_format": "s16le",
        },
        "rediarize_calls": 1,
        "rediarize_pcm": str(pcm_path),
        "provider_call_allowed": True,
    }


def test_multi_classifier_preserves_three_provider_labels_without_invention(
    monkeypatch,
):
    multi_module = _multi_module()
    labels = [f"chunk_00:speaker_{index}" for index in range(3)]
    ranges = {
        label: [(float(index), float(index + 1))]
        for index, label in enumerate(labels)
    }
    captured = {}

    def fake_classifier(
        pcm_path,
        ranges_by_speaker,
        *,
        deadline_monotonic,
        stop_requested,
    ):
        captured.update(
            {
                "pcm_path": pcm_path,
                "labels": list(ranges_by_speaker),
                "deadline": deadline_monotonic,
                "stopped": stop_requested(),
            }
        )
        return {
            label: {
                "speaker_id": label,
                "voice_register": "low" if index < 2 else "high",
                "confidence": 0.9,
            }
            for index, label in enumerate(ranges_by_speaker)
        }

    monkeypatch.setattr(
        multi_module.subdub_multi_speaker_gender_onnx,
        "classify_multi_speaker_genders",
        fake_classifier,
    )
    result = multi_module.classify_multi_speaker_registers(
        "fixture.pcm",
        ranges,
        deadline_monotonic=10**12,
        stop_requested=lambda: False,
    )

    assert list(result) == labels
    assert captured == {
        "pcm_path": "fixture.pcm",
        "labels": labels,
        "deadline": 10**12,
        "stopped": False,
    }
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        multi_module.classify_multi_speaker_registers(
            "fixture.pcm",
            {labels[0]: ranges[labels[0]]},
            deadline_monotonic=10**12,
            stop_requested=lambda: False,
        )
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        multi_module.classify_multi_speaker_registers(
            "fixture.pcm",
            {label: ranges[label] for label in labels[:2]},
            deadline_monotonic=10**12,
            stop_requested=lambda: False,
        )
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        multi_module.classify_multi_speaker_registers(
            "fixture.pcm",
            {
                f"chunk_00:speaker_{index}": [(0.0, 1.0)]
                for index in range(17)
            },
            deadline_monotonic=10**12,
            stop_requested=lambda: False,
        )


def test_multi_gender_classifier_rejects_single_cue_labels_before_inference(
    tmp_path,
    monkeypatch,
):
    multi_module = _multi_module()
    pcm_path = tmp_path / "multi-stereo.pcm"
    pcm_path.write_bytes(b"\0" * 64)
    called = []
    monkeypatch.setattr(
        multi_module.subdub_multi_speaker_gender_onnx.exact_gender,
        "_infer_selected_cues",
        lambda *_args, **_kwargs: called.append(True),
    )

    with pytest.raises(speaker_cast.AutoCastManualRequired):
        multi_module.classify_multi_speaker_registers(
            str(pcm_path),
            {
                "chunk_00:speaker_0": [(0.0, 0.5), (0.6, 1.1)],
                "chunk_00:speaker_1": [(2.0, 2.5)],
                "chunk_00:speaker_2": [(3.0, 3.5)],
            },
            deadline_monotonic=10**12,
            stop_requested=lambda: False,
        )
    assert called == []


def test_multi_gender_selection_keeps_short_cues_beside_a_long_cue():
    multi_module = _multi_module()
    selected = multi_module.subdub_multi_speaker_gender_onnx._select_bounded_cues(
        {
            "chunk_00:speaker_0": [
                (0.0, 0.5),
                (0.6, 1.1),
                (2.0, 12.0),
            ],
            "chunk_00:speaker_1": [(13.0, 13.5), (13.6, 14.1)],
            "chunk_00:speaker_2": [(14.2, 14.7), (14.8, 15.3)],
        }
    )

    assert selected["chunk_00:speaker_0"] == [
        {"start": 0.0, "end": 0.5},
        {"start": 0.6, "end": 1.1},
        {"start": 2.0, "end": 12.0},
    ]
    assert len(selected["chunk_00:speaker_1"]) == 2
    assert len(selected["chunk_00:speaker_2"]) == 2


def test_three_provider_labels_keep_distinct_validated_voices():
    labels = [f"chunk_00:speaker_{index}" for index in range(3)]
    classifications = {
        labels[0]: {
            "speaker_id": labels[0],
            "voice_register": "low",
            "confidence": 0.91,
        },
        labels[1]: {
            "speaker_id": labels[1],
            "voice_register": "low",
            "confidence": 0.92,
        },
        labels[2]: {
            "speaker_id": labels[2],
            "voice_register": "high",
            "confidence": 0.93,
        },
    }
    casts = speaker_cast.assign_stable_voices(
        classifications,
        speaker_order=labels,
        validated_pools={
            "low": ["low-a", "low-b", "low-c"],
            "high": ["high-a", "high-b", "high-c"],
        },
        assignment_seed="a" * 64,
    )

    assert list(casts) == labels
    assert {item["speaker_id"] for item in casts.values()} == set(labels)
    assert len({item["voice_id"] for item in casts.values()}) == 3


def test_multi_adapter_persists_three_distinct_voices_used_by_tts(monkeypatch):
    multi_module = _multi_module()
    labels = [f"chunk_00:speaker_{index}" for index in range(3)]
    voices = [f"voice-{index}" for index in range(3)]

    async def base_synthesize(segments, *_args, **_kwargs):
        return {
            "chunks": [{"index": 0, "audio": b"audio"}],
            "provider": "fixture",
        }

    async def fake_old_blackbox(**kwargs):
        for label, voice_id in zip(labels, voices, strict=True):
            await kwargs["synthesize_segments"](
                [{"speaker_id": label, "tts_voice_id": voice_id}],
                voice_id=voice_id,
            )
        return {
            "ok": True,
            "state": {
                **EXACT_AUTO_STATE,
                "auto_speaker_lane": "multi",
            },
        }

    monkeypatch.setattr(
        multi_module,
        "_run_isolated_multi_speaker_blackbox",
        fake_old_blackbox,
    )
    result = asyncio.run(
        multi_module.run_auto_multi_speaker_blackbox(
            extract_pcm=lambda *_args, **_kwargs: "fixture.pcm",
            synthesize_segments=base_synthesize,
            state={**EXACT_AUTO_STATE, "auto_speaker_lane": "multi"},
        )
    )

    assert result["ok"] is True
    assert result["state"]["auto_speaker_lane"] == "multi"
    assert result["state"]["auto_detected_speaker_count"] == 3
    assert result["state"]["auto_distinct_voice_count"] == 3
    assert result["state"]["auto_multi_voice_verified"] is True
    assert len(result["state"]["auto_multi_cast_sha256"]) == 64


def test_multi_adapter_fails_closed_when_tts_reuses_one_voice(monkeypatch):
    multi_module = _multi_module()

    async def base_synthesize(segments, *_args, **_kwargs):
        return {
            "chunks": [{"index": 0, "audio": b"audio"}],
            "provider": "fixture",
        }

    async def fake_old_blackbox(**kwargs):
        for index in range(3):
            await kwargs["synthesize_segments"](
                [{
                    "speaker_id": f"chunk_00:speaker_{index}",
                    "tts_voice_id": "same-voice",
                }],
                voice_id="same-voice",
            )
        return {
            "ok": True,
            "state": {
                **EXACT_AUTO_STATE,
                "auto_speaker_lane": "multi",
            },
        }

    monkeypatch.setattr(
        multi_module,
        "_run_isolated_multi_speaker_blackbox",
        fake_old_blackbox,
    )
    result = asyncio.run(
        multi_module.run_auto_multi_speaker_blackbox(
            extract_pcm=lambda *_args, **_kwargs: "fixture.pcm",
            synthesize_segments=base_synthesize,
            state={**EXACT_AUTO_STATE, "auto_speaker_lane": "multi"},
        )
    )

    assert result["ok"] is False
    assert result["status"] == speaker_cast.AUTO_CAST_MANUAL_REQUIRED
    assert result["public_copy_key"] == "voice_auto_manual_required"


def test_multi_completion_receipt_names_fixture_lane_casts_and_component_prices():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "terminal_state": "delivered",
        "target_language": "Tiếng Việt",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "auto_speaker_lane": "multi",
        "source_file_name": "test nhiều giọng.mp4",
        "auto_detected_speaker_count": 4,
        "auto_distinct_voice_count": 4,
        "auto_multi_voice_verified": True,
        "auto_multi_cast_sha256": "c" * 64,
        "auto_exact_actual_auto_xu": 205,
        "auto_exact_actual_subtitle_xu": 161,
        "auto_exact_actual_total_xu": 366,
    }
    result = {
        **state,
        "terminal_public_outcome_type": "success",
        "final_mp4_delivered": True,
        "video_delivered": True,
        "video_delivery_message_id": "multi-video-1",
        "canonical_final_artifact_duration": 133.375,
        "duration_coverage_ok": True,
        "public_job_id": "MULTI-RECEIPT-1",
        "final_price_xu": 366,
        "charged_xu": 0,
        "account_balance_xu": 200,
    }

    text = bot.video_dubbing_receipt_text(state, result, "vi")

    assert "Tệp nguồn: <b>test nhiều giọng.mp4</b>" in text
    assert "Loại lồng tiếng: <b>Tự động nhiều giọng</b>" in text
    assert "Số người nói nhận diện: <b>4</b>" in text
    assert "Số giọng lồng tiếng đã dùng: <b>4</b>" in text
    assert "Giá phụ đề: <b>161 Xu</b>" in text
    assert "Giá lồng tiếng: <b>205 Xu</b>" in text
    assert "Giá: <b>366 Xu</b>" in text


def test_multi_terminal_job_persists_proof_without_touching_default_auto_lane():
    state = {
        **EXACT_AUTO_STATE,
        "auto_speaker_lane": "multi",
        "source_file_name": "test nhiều giọng.mp4",
        "auto_detected_speaker_count": 4,
        "auto_distinct_voice_count": 4,
        "auto_multi_voice_verified": True,
        "auto_multi_cast_sha256": "c" * 64,
        "auto_exact_actual_auto_xu": 205,
        "auto_exact_actual_subtitle_xu": 161,
        "auto_exact_actual_total_xu": 366,
    }
    expected = {
        "auto_speaker_lane": "multi",
        "source_file_name": "test nhiều giọng.mp4",
        "auto_detected_speaker_count": 4,
        "auto_distinct_voice_count": 4,
        "auto_multi_voice_verified": True,
        "auto_multi_cast_sha256": "c" * 64,
        "auto_exact_actual_auto_xu": 205,
        "auto_exact_actual_subtitle_xu": 161,
        "auto_exact_actual_total_xu": 366,
    }

    assert bot.subdub_auto_multi_terminal_proof_fields(state) == expected
    assert bot.subdub_auto_multi_terminal_proof_fields(EXACT_AUTO_STATE) == {}
    assert bot.subdub_auto_multi_terminal_proof_fields(
        {**state, "auto_distinct_voice_count": 2}
    ) == {}
    pipeline_source = inspect.getsource(
        bot._execute_video_dubbing_pipeline_core
    )
    assert pipeline_source.count(
        "**subdub_auto_multi_terminal_proof_fields(state)"
    ) == 1


def test_multi_adapter_owns_classifier_without_touching_protected_lane(monkeypatch):
    multi_module = _multi_module()
    captured = {"delegate": 0, "extract": 0}

    async def base_extract(
        prepared,
        state,
        *,
        channels,
        sample_rate,
        sample_format,
        **extract_kwargs,
    ):
        del prepared, state, channels, sample_rate, sample_format
        captured["extract"] += 1
        captured["extract_kwargs"] = extract_kwargs
        return "fixture.pcm"

    async def fake_old_blackbox(**kwargs):
        captured["delegate"] += 1
        captured["classifier"] = kwargs.get("classify_speakers")
        extracted = kwargs["extract_pcm"](
            {},
            kwargs["state"],
            channels=1,
            sample_rate=speaker_cast.PCM_SAMPLE_RATE,
            sample_format="s16le",
        )
        if inspect.isawaitable(extracted):
            extracted = await extracted
        captured["pcm"] = extracted
        return {"ok": True, "status": "fixture"}

    monkeypatch.setattr(
        multi_module,
        "_run_isolated_multi_speaker_blackbox",
        fake_old_blackbox,
    )
    monkeypatch.setattr(
        auto_speaker,
        "run_auto_speaker_blackbox",
        lambda **_kwargs: pytest.fail("multi called protected two-speaker runner"),
    )
    result = asyncio.run(
        multi_module.run_auto_multi_speaker_blackbox(
            lane_mode="dub",
            extract_pcm=base_extract,
            state={
                **EXACT_AUTO_STATE,
                "auto_speaker_lane": "multi",
            },
        )
    )

    assert result == {"ok": True, "status": "fixture"}
    assert captured == {
        "delegate": 1,
        "extract": 1,
        "extract_kwargs": {},
        "classifier": multi_module.classify_multi_speaker_registers,
        "pcm": "fixture.pcm",
    }


def test_isolated_multi_runner_assigns_and_synthesizes_three_voices(monkeypatch):
    multi_module = _multi_module()
    labels = [f"chunk_00:speaker_{index}" for index in range(3)]
    state = {
        **EXACT_AUTO_STATE,
        "auto_speaker_lane": "multi",
        "mode": "dub",
        "dub_text_source": "source",
    }
    source_segments = [
        {
            "cue_id": f"cue-{index}",
            "index": index + 1,
            "start": float(index),
            "end": float(index + 1),
            "text": f"speaker {index}",
            "speaker_id": label,
        }
        for index, label in enumerate(labels)
    ]
    prepared = {
        "state": {**state, "speaker_sidecar_sha256": "a" * 64},
        "source_segments": source_segments,
        "output_segments": [dict(item) for item in source_segments],
    }
    classifications = {
        label: {
            "speaker_id": label,
            "voice_register": "low" if index < 2 else "high",
            "confidence": 0.9,
        }
        for index, label in enumerate(labels)
    }

    async def fake_preflight(_state, **_kwargs):
        return {
            "ok": True,
            "status": auto_speaker.AUTO_SPEAKER_PREFLIGHT_READY,
            "prepared": prepared,
            "speaker_labels": labels,
            "classifications": classifications,
        }

    monkeypatch.setattr(
        multi_module,
        "_run_multi_speaker_preflight",
        fake_preflight,
    )
    monkeypatch.setattr(
        auto_speaker,
        "run_auto_speaker_blackbox",
        lambda **_kwargs: pytest.fail("isolated multi called protected runner"),
    )
    synthesized_voices = []

    async def synthesize_segments(segments, **kwargs):
        cue = segments[0]
        synthesized_voices.append(kwargs["voice_id"])
        return {
            "chunks": [{
                "start": cue["start"],
                "end": cue["end"],
                "audio_bytes": b"audio",
            }],
            "provider": "fixture",
        }

    async def run_lane_blackbox(*, lane_mode, runner, **payload):
        assert lane_mode == "dub"
        assert runner is runner_token
        annotated = await payload["prepare_subtitles"](payload["state"])
        compatibility_voice = payload["resolve_voice_id"](
            7,
            payload["state"],
        )
        aggregate = await payload["synthesize_segments"](
            annotated["source_segments"],
            voice_id=compatibility_voice,
        )
        return {"ok": True, "aggregate": aggregate}

    async def runner_token(**_kwargs):
        raise AssertionError("focused lane stub owns the runner seam")

    result = asyncio.run(
        multi_module._run_isolated_multi_speaker_blackbox(
            lane_mode="dub",
            run_lane_blackbox=run_lane_blackbox,
            runner=runner_token,
            prepare_subtitles=lambda *_args, **_kwargs: prepared,
            resolve_voice_id=lambda *_args, **_kwargs: "forbidden",
            synthesize_segments=synthesize_segments,
            post_prepare_gate=lambda *_args, **_kwargs: {"continue": True},
            extract_pcm=lambda *_args, **_kwargs: "unused.pcm",
            validated_pools={
                "low": ["low-a", "low-b", "low-c"],
                "high": ["high-a", "high-b", "high-c"],
            },
            classify_speakers=multi_module.classify_multi_speaker_registers,
            required_pool_capacity=3,
            state=state,
            mode="dub",
        )
    )

    assert result["ok"] is True
    assert len(synthesized_voices) == 3
    assert len(set(synthesized_voices)) == 3


@pytest.mark.parametrize("target_language", ("vi", "ja", "en", "ko", "zh"))
def test_multi_adapter_preserves_translation_target_language(
    monkeypatch,
    target_language,
):
    multi_module = _multi_module()
    captured = {}

    async def fake_old_blackbox(**kwargs):
        captured["state"] = dict(kwargs["state"])
        return {"ok": True, "status": "fixture"}

    monkeypatch.setattr(
        multi_module,
        "_run_isolated_multi_speaker_blackbox",
        fake_old_blackbox,
    )
    state = bot.subdub_apply_voice_choice(
        {
            "mode": "subtitle_plus_dub",
            "active_flow": "subtitle_plus_dub",
            "target_language": target_language,
            "translate_requested": "1",
        },
        "auto_multi_speaker",
        activation_enabled=True,
    )

    result = asyncio.run(
        multi_module.run_auto_multi_speaker_blackbox(
            extract_pcm=lambda *_args, **_kwargs: "fixture.pcm",
            state=state,
        )
    )

    assert result == {"ok": True, "status": "fixture"}
    assert captured["state"]["target_language"] == target_language
    assert captured["state"]["translate_requested"] == "1"
    assert captured["state"]["auto_speaker_lane"] == "multi"


def test_multi_pcm_contract_reuses_stereo_onnx_source_without_filter_grid(
    tmp_path,
    monkeypatch,
):
    multi_module = _multi_module()
    assert multi_module.subdub_two_speaker_gender_onnx.PCM_CHANNELS == 2
    assert multi_module.subdub_two_speaker_gender_onnx.PCM_SAMPLE_RATE == 44_100
    assert "AUTO_SPEAKER_PCM_AUDIO_FILTER" not in vars(auto_speaker)
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"source")
    calls = []

    monkeypatch.setattr(
        bot,
        "subtitle_dub_workspace_path_safety",
        lambda _workspace: {"allowed": True},
    )
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(
        bot.subdub_media_preflight,
        "timeout_for_stage",
        lambda *_args, **_kwargs: 77.0,
    )

    async def fake_run(command, timeout):
        calls.append((list(command), timeout))
        Path(command[-1]).write_bytes(b"\0\0" * 8_000)
        return True, "ok"

    monkeypatch.setattr(bot, "run_subdub_ffmpeg_command", fake_run)
    result = asyncio.run(
        bot._extract_subdub_auto_pcm(
            {
                "state": {
                    "_pipeline_workspace": str(tmp_path),
                    "_pipeline_saved_source_path": str(source_path),
                },
                "duration_seconds": 12,
            },
            {},
            channels=2,
            sample_rate=44_100,
            sample_format="s16le",
        )
    )

    assert result == str(tmp_path / "auto_speaker_44100_stereo_s16le.pcm")
    assert calls == [
        (
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source_path),
                "-t",
                "12",
                "-vn",
                "-ac",
                "2",
                "-ar",
                "44100",
                "-f",
                "s16le",
                str(tmp_path / "auto_speaker_44100_stereo_s16le.pcm"),
            ],
            77.0,
        )
    ]
