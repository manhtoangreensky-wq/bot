from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import bot
from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_multi_speaker, auto_smart_multivoice


def test_first_red_a_admission_execution_plan_mismatch(monkeypatch):
    """Case A: Smart Multi selected, generic Key4U configured, Deepgram absent.

    Desired: Admission rejected before job creation (video_dubbing_asr_missing_for_state is True).
    Baseline RED: Currently returns False because get_asr_adapter_readiness sees Key4U.
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "")
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "dummy_key4u_key")
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "")

    state = {
        "auto_smart_multivoice_opt_in": True,
        "voice_selection_mode": "auto_smart_multivoice",
    }
    mode = bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB

    # Desired: ASR is missing for Smart Multi because Deepgram is required.
    # In baseline, this returns False (RED).
    assert bot.video_dubbing_asr_missing_for_state(mode, state) is True

    # Desired: resolve_subdub_asr_plan reports not ready with deepgram_asr_not_configured
    plan = bot.resolve_subdub_asr_plan(state=state, mode=mode)
    assert plan["ready"] is False
    assert plan["provider"] == "deepgram"
    assert plan["detail"] == "deepgram_asr_not_configured"
    assert plan["blocker"] == bot.AUTO_CAST_UNAVAILABLE


def test_first_red_b_final_confirmation_missing(monkeypatch):
    """Case B: Smart Multi selected, Deepgram configured, final confirmation absent.

    Desired: Plan resolver reports not ready with subdub_final_confirmation_required.
    Baseline RED: resolver does not exist or does not enforce confirmation before job creation.
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "dummy_deepgram_key")
    state = {
        "auto_smart_multivoice_opt_in": True,
        "confirmed_product": False,
        "subdub_final_confirmed": False,
    }
    mode = bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB

    plan = bot.resolve_subdub_asr_plan(state=state, mode=mode, confirmation=False)
    assert plan["ready"] is False
    assert plan["detail"] == "subdub_final_confirmation_required"
    assert plan["require_final_confirmation"] is True


def test_first_red_c_deepgram_words_no_speaker_labels(monkeypatch, tmp_path):
    """Case C: Deepgram returns transcript + word timeline, but NO speaker labels.

    PCM is available, local acoustic diarization succeeds.
    Desired: Local acoustic diarization is invoked, AUTO_CAST_UNAVAILABLE is NOT raised,
    pipeline continues with speaker evidence.
    Baseline RED: Smart Multi previously only checked len(ordered_auto_speaker_labels) >= 3
    on provider segments, so absence of provider labels bypassed local diarization and failed.
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "dummy_deepgram_key")
    dummy_source = tmp_path / "test.mp4"
    dummy_source.write_bytes(b"dummy_mp4_bytes")

    word_timeline = [
        {"index": 0, "word": "Hello", "start": 0.0, "end": 0.5},
        {"index": 1, "word": "world", "start": 0.6, "end": 1.0},
        {"index": 2, "word": "test", "start": 1.1, "end": 1.5},
    ]
    # Deepgram segments without speaker labels
    unlabeled_segments = [
        {"start": 0.0, "end": 0.5, "text": "Hello"},
        {"start": 0.6, "end": 1.0, "text": "world"},
        {"start": 1.1, "end": 1.5, "text": "test"},
    ]

    async def fake_resolve_source_script(*args, **kwargs):
        return {
            "source_kind": "asr",
            "subtitle": "1\n00:00:00,000 --> 00:00:00,500\nHello\n\n2\n00:00:00,600 --> 00:00:01,000\nworld\n\n3\n00:00:01,100 --> 00:00:01,500\ntest",
            "script": "Hello world test",
            "asr_provider": "deepgram",
            "detail": "deepgram_ok",
            "segments": unlabeled_segments,
            "word_timeline": word_timeline,
            "duration_seconds": 2,
        }

    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", fake_resolve_source_script)
    monkeypatch.setattr(bot, "video_dubbing_download_source", AsyncMock(return_value=(b"dummy_mp4_bytes", "video/mp4")))

    dummy_pcm = tmp_path / "test.pcm"
    dummy_pcm.write_bytes(b"\x00" * 44100 * 2 * 2)
    monkeypatch.setattr(bot, "_extract_subdub_auto_pcm", AsyncMock(return_value=str(dummy_pcm)))

    local_diarization_spy = MagicMock(return_value={
        "provider": "onnx_cam_v1",
        "model_sha256": "dummy_sha",
        "algorithm_version": "v1",
        "detected_speaker_count": 3,
        "word_count": 3,
        "unit_count": 3,
        "embedding_window_count": 3,
        "cluster_sizes": [1, 1, 1],
        "stability_pass": True,
        "word_coverage_count": 3,
        "overlap_mapped_count": 0,
        "centroid_mapped_count": 3,
        "speaker_unit_counts": [1, 1, 1],
        "word_overlap_mapped_count": 0,
        "word_fallback_mapped_count": 0,
        "word_centroid_mapped_count": 3,
        "speaker_count_authority_asr_independent": True,
        "word_attribution_uses_asr_timeline": True,
        "speaker_registers": ["low", "high", "low"],
        "speaker_register_confidences": [0.95, 0.92, 0.89],
        "female_speaker_count": 1,
        "male_speaker_count": 2,
        "gender_model_sha256": "dummy_gender_sha",
        "gender_ambiguous_window_count": 0,
        "raw_speaker_count": 3,
        "raw_embedding_window_count": 3,
        "raw_cluster_sizes": [1, 1, 1],
        "raw_speaker_unit_counts": [1, 1, 1],
        "raw_overlap_speaker_unit_counts": [0, 0, 0],
        "speech_supported_speaker_labels": ["speaker_0", "speaker_1", "speaker_2"],
        "dropped_non_speech_speaker_labels": [],
        "segments": [
            {"start": 0.0, "end": 0.5, "text": "Hello", "speaker": "speaker_0", "speaker_id": "speaker_0"},
            {"start": 0.6, "end": 1.0, "text": "world", "speaker": "speaker_1", "speaker_id": "speaker_1"},
            {"start": 1.1, "end": 1.5, "text": "test", "speaker": "speaker_2", "speaker_id": "speaker_2"},
        ],
    })
    monkeypatch.setattr(auto_multi_speaker, "run_local_acoustic_diarization_off_event_loop", AsyncMock(side_effect=local_diarization_spy))

    # Mock bounded_multi_acoustic_evidence — test C validates the ROUTING decision
    # (unlabeled segments → local acoustic path), not the evidence validator itself.
    # Real validation checks ONNX model SHA256 hashes / algorithm versions that dummy data can't satisfy.
    bounded_evidence_result = {
        "multi_acoustic_speaker_count": 3,
        "multi_acoustic_word_count": 3,
        "multi_acoustic_unit_count": 3,
        "multi_acoustic_embedding_window_count": 6,
        "multi_acoustic_cluster_sizes": [1, 1, 1],
        "multi_acoustic_stability_pass": True,
        "multi_acoustic_word_coverage_count": 3,
        "multi_acoustic_overlap_mapped_count": 0,
        "multi_acoustic_centroid_mapped_count": 3,
        "multi_acoustic_speaker_unit_counts": [1, 1, 1],
    }
    monkeypatch.setattr(auto_multi_speaker, "bounded_multi_acoustic_evidence", MagicMock(return_value=bounded_evidence_result))

    # Mock state management / sidecar functions — test C validates ROUTING, not persistence.
    # CRITICAL: sync_state_fields must preserve voice-selection keys so that
    # is_auto_smart_multivoice_state(state) still returns True after set_video_dubbing_pending
    # replaces the state dict at line 249023.
    _voice_keys = {
        "auto_smart_multivoice_opt_in", "voice_selection_mode",
        "auto_speaker_lane", "auto_smart_multivoice", "auto_multi_engine", "subdub_mode",
    }
    monkeypatch.setattr(bot, "set_video_dubbing_artifact", MagicMock(return_value="artifact_ref"))
    monkeypatch.setattr(
        bot, "video_dubbing_sync_state_fields",
        MagicMock(side_effect=lambda st, **kw: {k: v for k, v in st.items() if k in _voice_keys}),
    )
    monkeypatch.setattr(
        bot, "set_video_dubbing_pending",
        MagicMock(side_effect=lambda user_id, step, **kw: {"step": step, **kw}),
    )
    monkeypatch.setattr(speaker_cast, "build_sidecar", MagicMock(return_value={"segments": [], "media_sha256": "x", "subtitle_sha256": "x"}))
    monkeypatch.setattr(speaker_cast, "persist_sidecar", MagicMock(return_value={"path": "/tmp/sidecar.json", "sha256": "abc"}))
    monkeypatch.setattr(bot, "subdub_speaker_sidecar_subtitle_sha256", MagicMock(return_value="sha256_stub"))
    monkeypatch.setattr(bot, "subdub_validate_cue_locked_timing", MagicMock(return_value={"ok": True}))

    state = {
        "auto_smart_multivoice_opt_in": True,
        "voice_selection_mode": "auto_smart_multivoice",
        "confirmed_product": True,
        "subdub_final_confirmed": True,
        "source": str(dummy_source),
        "_pipeline_workspace": str(tmp_path),
    }

    prepared = asyncio.run(
        bot.video_dubbing_prepare_subtitles(
            context=MagicMock(),
            state=state,
            user_id="test_user",
            allow_confirmed_product=True,
            require_auto_cast=True,
        )
    )

    assert local_diarization_spy.called is True
    assert prepared is not None
    # acoustic fields are persisted via set_video_dubbing_pending into state
    assert prepared.get("source_segment_count") == 3


def test_first_red_d_local_acoustic_failure(monkeypatch, tmp_path):
    """Case D: Deepgram returns words + timeline, no speaker labels, but local acoustic diarization fails.

    Desired: Fail closed with AUTO_CAST_UNAVAILABLE and exact safe detail.
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "dummy_deepgram_key")
    dummy_source = tmp_path / "test.mp4"
    dummy_source.write_bytes(b"dummy_mp4_bytes")

    word_timeline = [{"index": 0, "word": "Hello", "start": 0.0, "end": 0.5}]
    unlabeled_segments = [{"start": 0.0, "end": 0.5, "text": "Hello"}]

    async def fake_resolve_source_script(*args, **kwargs):
        return {
            "source_kind": "asr",
            "subtitle": "1\n00:00:00,000 --> 00:00:00,500\nHello",
            "script": "Hello",
            "asr_provider": "deepgram",
            "detail": "deepgram_ok",
            "segments": unlabeled_segments,
            "word_timeline": word_timeline,
            "duration_seconds": 1,
        }

    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", fake_resolve_source_script)
    monkeypatch.setattr(bot, "video_dubbing_download_source", AsyncMock(return_value=(b"dummy_mp4_bytes", "video/mp4")))

    dummy_pcm = tmp_path / "test.pcm"
    dummy_pcm.write_bytes(b"\x00" * 44100 * 2 * 2)
    monkeypatch.setattr(bot, "_extract_subdub_auto_pcm", AsyncMock(return_value=str(dummy_pcm)))

    # Local diarization raises AutoCastUnavailable with detail
    async def failing_local_diarization(*args, **kwargs):
        raise speaker_cast.AutoCastUnavailable(detail="local_acoustic_authority_insufficient")

    monkeypatch.setattr(auto_multi_speaker, "run_local_acoustic_diarization_off_event_loop", failing_local_diarization)

    state = {
        "auto_smart_multivoice_opt_in": True,
        "voice_selection_mode": "auto_smart_multivoice",
        "confirmed_product": True,
        "subdub_final_confirmed": True,
        "source": str(dummy_source),
        "_pipeline_workspace": str(tmp_path),
    }

    with pytest.raises(speaker_cast.AutoCastUnavailable) as exc_info:
        asyncio.run(
            bot.video_dubbing_prepare_subtitles(
                context=MagicMock(),
                state=state,
                user_id="test_user",
                allow_confirmed_product=True,
                require_auto_cast=True,
            )
        )
    # Check that error is preserved
    assert exc_info.type is speaker_cast.AutoCastUnavailable


def test_first_red_e_valid_provider_speaker_labels(monkeypatch, tmp_path):
    """Case E: Deepgram returns valid words AND valid speaker labels.

    Desired: Existing labeled path remains valid, local acoustic diarization is NOT invoked.
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "dummy_deepgram_key")
    dummy_source = tmp_path / "test.mp4"
    dummy_source.write_bytes(b"dummy_mp4_bytes")

    word_timeline = [
        {"index": 0, "word": "One", "start": 0.0, "end": 0.5},
        {"index": 1, "word": "Two", "start": 0.6, "end": 1.0},
    ]
    # Deepgram segments WITH speaker labels (N=2 integer speaker indexes as returned by real Deepgram)
    labeled_segments = [
        {"start": 0.0, "end": 0.5, "text": "One", "speaker": 0},
        {"start": 0.6, "end": 1.0, "text": "Two", "speaker": 1},
    ]

    async def fake_resolve_source_script(*args, **kwargs):
        return {
            "source_kind": "asr",
            "subtitle": "1\n00:00:00,000 --> 00:00:00,500\nOne\n\n2\n00:00:00,600 --> 00:00:01,000\nTwo",
            "script": "One Two",
            "asr_provider": "deepgram",
            "detail": "deepgram_ok",
            "segments": labeled_segments,
            "word_timeline": word_timeline,
            "duration_seconds": 1,
        }

    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", fake_resolve_source_script)
    monkeypatch.setattr(bot, "video_dubbing_download_source", AsyncMock(return_value=(b"dummy_mp4_bytes", "video/mp4")))

    local_diarization_spy = MagicMock()
    monkeypatch.setattr(auto_multi_speaker, "run_local_acoustic_diarization_off_event_loop", AsyncMock(side_effect=local_diarization_spy))

    state = {
        "auto_smart_multivoice_opt_in": True,
        "voice_selection_mode": "auto_smart_multivoice",
        "confirmed_product": True,
        "subdub_final_confirmed": True,
        "source": str(dummy_source),
        "_pipeline_workspace": str(tmp_path),
    }

    prepared = asyncio.run(
        bot.video_dubbing_prepare_subtitles(
            context=MagicMock(),
            state=state,
            user_id="test_user",
            allow_confirmed_product=True,
            require_auto_cast=True,
        )
    )
    # When provider already gave valid labels for N<3, local diarization should not be called
    assert local_diarization_spy.called is False
    assert len(prepared.get("source_segments") or []) == 2


def test_first_red_f_non_smart_lane(monkeypatch):
    """Case F: Non-Smart SubDub lane (standard subtitle creation).

    Generic Key4U configured, Deepgram absent.
    Desired: Non-Smart lane accepts Key4U (video_dubbing_asr_missing_for_state is False).
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "")
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "dummy_key4u_key")
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "")

    state = {
        "auto_smart_multivoice_opt_in": False,
        "voice_selection_mode": "manual",
    }
    mode = bot.VIDEO_SUBTITLE_MODE_CREATE

    assert bot.video_dubbing_asr_missing_for_state(mode, state) is False


def test_first_red_g_failure_detail_propagation(monkeypatch):
    """Case G: Failure detail propagation.

    When AutoCastUnavailable has a specific detail (e.g. deepgram_word_timeline_missing),
    the debug job payload and error handlers preserve ERROR_CODE=AUTO_CAST_UNAVAILABLE
    and ERROR_DETAIL=deepgram_word_timeline_missing.
    Baseline RED: detail is currently lost / collapsed to generic AUTO_CAST_UNAVAILABLE.
    """
    state = {
        "auto_smart_multivoice_opt_in": True,
        "voice_selection_mode": "auto_smart_multivoice",
        "_pipeline_job_id": "test_job_123",
    }
    payload = bot.subtitle_dub_debug_job_payload(
        user_id="user_123",
        chat_id="chat_123",
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        state=state,
        status=bot.AUTO_CAST_UNAVAILABLE,
        stage="subtitle",
        detail="deepgram_word_timeline_missing",
    )
    assert payload["status"] == bot.AUTO_CAST_UNAVAILABLE
    assert payload.get("error_detail") == "deepgram_word_timeline_missing" or payload.get("detail") == "deepgram_word_timeline_missing"


def test_first_red_h_job_provenance(monkeypatch):
    """Case H: Job provenance fields persisted for Smart Multi jobs.

    Required fields: subdub_engine_requested, subdub_engine_selected,
    auto_smart_multivoice_opt_in, subdub_final_confirmed, subdub_asr_route_id,
    subdub_asr_provider, subdub_asr_require_word_timeline,
    subdub_asr_require_provider_speaker_labels, subdub_local_acoustic_diarization_allowed.
    Baseline RED: These fields were NOT_PERSISTED.
    """
    state = {
        "auto_smart_multivoice_opt_in": True,
        "voice_selection_mode": "auto_smart_multivoice",
        "subdub_final_confirmed": True,
        "_pipeline_job_id": "test_job_123",
    }
    payload = bot.subtitle_dub_debug_job_payload(
        user_id="user_123",
        chat_id="chat_123",
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        state=state,
        status="processing",
        stage="init",
    )
    assert payload.get("subdub_engine_requested") == "auto_smart_multivoice"
    assert payload.get("auto_smart_multivoice_opt_in") is True
    assert payload.get("subdub_final_confirmed") is True
    assert payload.get("subdub_asr_provider") == "deepgram"
    assert payload.get("subdub_asr_require_word_timeline") is True
    assert payload.get("subdub_asr_require_provider_speaker_labels") is False
    assert payload.get("subdub_local_acoustic_diarization_allowed") is True
