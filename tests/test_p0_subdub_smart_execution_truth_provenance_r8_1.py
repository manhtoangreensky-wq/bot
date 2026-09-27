from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import bot
from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_multi_speaker, auto_multi_speaker_v2, auto_smart_multivoice


def test_first_red_a_real_admission_deepgram_missing(monkeypatch):
    """Case A: Smart selected, generic Key4U configured, Deepgram absent, final confirmation valid.

    Desired:
    - resolve_subdub_asr_plan reports not ready with deepgram_asr_not_configured
    - blocker class is ASR_CONFIG_MISSING
    - video_dubbing_asr_missing_for_state is True
    - admission seam rejects: 0 job inserts, 0 outbox inserts, 0 worker dispatches
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "")
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "dummy_key4u_key")
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "")

    state = {
        "auto_smart_multivoice_opt_in": True,
        "voice_selection_mode": "auto_smart_multivoice",
        "confirmed_product": True,
        "subdub_final_confirmed": True,
    }
    mode = bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB

    plan = bot.resolve_subdub_asr_plan(state=state, mode=mode)
    assert plan["ready"] is False
    assert plan["provider"] == "deepgram"
    assert plan["detail"] == "deepgram_asr_not_configured"
    assert plan["blocker_class"] == "ASR_CONFIG_MISSING"

    assert bot.video_dubbing_asr_missing_for_state(mode, state) is True

    # Real admission seam check
    admit_result = bot.subdub_admission_preflight(state=state, mode=mode)
    assert admit_result["admitted"] is False
    assert admit_result["blocker_class"] == "ASR_CONFIG_MISSING"
    assert admit_result["detail"] == "deepgram_asr_not_configured"
    assert admit_result.get("job_inserted") is False


def test_first_red_b_real_admission_final_confirm_missing(monkeypatch):
    """Case B: Smart selected, Deepgram configured, final confirmation absent.

    Desired:
    - resolve_subdub_asr_plan reports not ready with subdub_final_confirmation_required
    - blocker class is FINAL_CONFIRMATION_MISSING
    - CRITICAL: video_dubbing_asr_missing_for_state is False (do NOT call confirmation failure ASR missing!)
    - admission seam rejects: 0 job inserts
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "dummy_deepgram_key")
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "")
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "")

    state = {
        "auto_smart_multivoice_opt_in": True,
        "voice_selection_mode": "auto_smart_multivoice",
        "confirmed_product": False,
        "subdub_final_confirmed": False,
    }
    mode = bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB

    plan = bot.resolve_subdub_asr_plan(state=state, mode=mode, confirmation=False)
    assert plan["ready"] is False
    assert plan["detail"] == "subdub_final_confirmation_required"
    assert plan["blocker_class"] == "FINAL_CONFIRMATION_MISSING"

    # Invariant §11: Do NOT call confirmation failure "ASR missing"
    assert bot.video_dubbing_asr_missing_for_state(mode, state) is False

    admit_result = bot.subdub_admission_preflight(state=state, mode=mode)
    assert admit_result["admitted"] is False
    assert admit_result["blocker_class"] == "FINAL_CONFIRMATION_MISSING"
    assert admit_result["detail"] == "subdub_final_confirmation_required"
    assert admit_result.get("job_inserted") is False


def test_first_red_c_real_admission_ready_job_insert(monkeypatch):
    """Case C: Smart selected, Deepgram configured, confirmation valid.

    Desired:
    - Plan is ready
    - video_dubbing_asr_missing_for_state is False
    - Admission admits and creates exactly 1 job insert
    - Persisted ASR plan snapshot in job matches resolved plan exactly
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "dummy_deepgram_key")

    state = {
        "auto_smart_multivoice_opt_in": True,
        "voice_selection_mode": "auto_smart_multivoice",
        "confirmed_product": True,
        "subdub_final_confirmed": True,
    }
    mode = bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB

    plan = bot.resolve_subdub_asr_plan(state=state, mode=mode, confirmation=True)
    assert plan["ready"] is True
    assert bot.video_dubbing_asr_missing_for_state(mode, state) is False

    admit_result = bot.subdub_admission_preflight(state=state, mode=mode)
    assert admit_result["admitted"] is True
    assert admit_result.get("job_inserted") is True

    snapshot = admit_result.get("asr_plan_snapshot") or {}
    assert snapshot.get("subdub_asr_route_id") == "smart_multivoice_deepgram"
    assert snapshot.get("subdub_asr_provider") == "deepgram"
    assert snapshot.get("subdub_asr_require_word_timeline") is True
    assert snapshot.get("subdub_asr_require_provider_speaker_labels") is False
    assert snapshot.get("subdub_local_acoustic_diarization_allowed") is True
    assert snapshot.get("subdub_engine_requested") == "auto_smart_multivoice"
    assert snapshot.get("subdub_engine_selected") == ""  # NOT fabricated yet
    assert snapshot.get("asr_route_called") is False  # NOT called yet


def test_first_red_d_shared_plan_admission_to_execution(monkeypatch, tmp_path):
    """Case D: Execution consumes the persisted plan snapshot from admission.

    Desired:
    - Execution does NOT independently derive ASR requirements from kwargs
    - It reads subdub_asr_require_word_timeline and subdub_asr_require_provider_speaker_labels
      from state snapshot, passing require_auto_multi_word_timeline=True to resolver
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "dummy_deepgram_key")
    dummy_source = tmp_path / "test.mp4"
    dummy_source.write_bytes(b"dummy_mp4_bytes")

    resolve_spy = AsyncMock(return_value={
        "source_kind": "asr",
        "subtitle": "1\n00:00:00,000 --> 00:00:01,000\nHello",
        "script": "Hello",
        "asr_provider": "deepgram",
        "detail": "ok",
        "segments": [{"start": 0.0, "end": 1.0, "text": "Hello"}],
        "word_timeline": [{"index": 0, "word": "Hello", "start": 0.0, "end": 1.0}],
        "duration_seconds": 1,
    })
    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", resolve_spy)
    monkeypatch.setattr(bot, "video_dubbing_download_source", AsyncMock(return_value=(b"dummy_mp4_bytes", "video/mp4")))

    # Prepare state containing the persisted plan snapshot
    state = {
        "auto_smart_multivoice_opt_in": True,
        "voice_selection_mode": "auto_smart_multivoice",
        "confirmed_product": True,
        "subdub_final_confirmed": True,
        "subdub_asr_route_id": "smart_multivoice_deepgram",
        "subdub_asr_provider": "deepgram",
        "subdub_asr_require_word_timeline": True,
        "subdub_asr_require_provider_speaker_labels": False,
        "subdub_local_acoustic_diarization_allowed": True,
        "subdub_engine_requested": "auto_smart_multivoice",
        "source": str(dummy_source),
        "_pipeline_workspace": str(tmp_path),
    }

    # Verify that video_dubbing_resolve_source_script kwargs are driven by the snapshot
    # require_auto_multi_word_timeline=True, require_diarization=False
    call_kwargs = bot.resolve_subdub_execution_asr_kwargs(state)
    assert call_kwargs.get("require_auto_multi_word_timeline") is True
    assert call_kwargs.get("require_diarization") is False


def test_first_red_e_asr_route_called_on_success(monkeypatch, tmp_path):
    """Case E: ASR called and succeeds -> asr_route_called is recorded as True."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "dummy_deepgram_key")
    dummy_source = tmp_path / "test.mp4"
    dummy_source.write_bytes(b"dummy_mp4_bytes")

    async def fake_resolve(*args, **kwargs):
        return {
            "source_kind": "asr",
            "subtitle": "1\n00:00:00,000 --> 00:00:01,000\nHello",
            "script": "Hello",
            "asr_provider": "deepgram",
            "detail": "ok",
            "segments": [{"start": 0.0, "end": 1.0, "text": "Hello", "speaker": 0}],
            "word_timeline": [{"index": 0, "word": "Hello", "start": 0.0, "end": 1.0}],
            "duration_seconds": 1,
        }

    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", fake_resolve)
    monkeypatch.setattr(bot, "video_dubbing_download_source", AsyncMock(return_value=(b"dummy_mp4_bytes", "video/mp4")))

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
    assert prepared.get("state", {}).get("asr_route_called") is True or state.get("asr_route_called") is True


def test_first_red_f_asr_route_called_on_post_asr_failure(monkeypatch, tmp_path):
    """Case F: ASR called, but downstream fails -> asr_route_called is STILL True (event truth)."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "dummy_deepgram_key")
    dummy_source = tmp_path / "test.mp4"
    dummy_source.write_bytes(b"dummy_mp4_bytes")

    # Deepgram returns valid transcript but missing word timeline
    async def fake_resolve(*args, **kwargs):
        return {
            "source_kind": "asr",
            "subtitle": "1\n00:00:00,000 --> 00:00:01,000\nHello",
            "script": "Hello",
            "asr_provider": "deepgram",
            "detail": "ok",
            "segments": [{"start": 0.0, "end": 1.0, "text": "Hello"}],
            "word_timeline": [],  # Missing word timeline!
            "duration_seconds": 1,
        }

    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", fake_resolve)
    monkeypatch.setattr(bot, "video_dubbing_download_source", AsyncMock(return_value=(b"dummy_mp4_bytes", "video/mp4")))

    state = {
        "auto_smart_multivoice_opt_in": True,
        "voice_selection_mode": "auto_smart_multivoice",
        "confirmed_product": True,
        "subdub_final_confirmed": True,
        "source": str(dummy_source),
        "_pipeline_workspace": str(tmp_path),
    }

    with pytest.raises(speaker_cast.AutoCastUnavailable):
        asyncio.run(
            bot.video_dubbing_prepare_subtitles(
                context=MagicMock(),
                state=state,
                user_id="test_user",
                allow_confirmed_product=True,
                require_auto_cast=True,
            )
        )
    # Event truth: ASR was actually invoked
    assert state.get("asr_route_called") is True


def test_first_red_g_engine_selected_n3_v2(monkeypatch):
    """Case G: Smart N>=3 strong acoustic dispatch dispatches to V2 with provenance set BEFORE invoking V2."""
    cues = [
        {"cue_id": 1, "start": 0.0, "end": 1.0, "text": "One", "speaker": 0, "chunk_index": 0, "speaker_id": "chunk_00:speaker_0", "voice_register": "low"},
        {"cue_id": 2, "start": 1.1, "end": 2.0, "text": "Two", "speaker": 1, "chunk_index": 0, "speaker_id": "chunk_00:speaker_1", "voice_register": "high"},
        {"cue_id": 3, "start": 2.1, "end": 3.0, "text": "Three", "speaker": 2, "chunk_index": 0, "speaker_id": "chunk_00:speaker_2", "voice_register": "low"},
    ]
    prepared = {
        "ok": True,
        "source_bytes": b"dummy_mp4_bytes",
        "source_segments": cues,
        "cues": cues,
        "speaker_registers": ["low", "high", "low"],
        "speaker_register_confidences": [0.95, 0.92, 0.89],
        "state": {
            "subdub_engine_requested": "auto_smart_multivoice",
            "auto_smart_multivoice_opt_in": True,
        },
    }

    v2_state_spy = {}

    async def mock_v2_blackbox(*args, **kwargs):
        nonlocal v2_state_spy
        v2_state_spy = dict(kwargs.get("state") or {})
        return {
            "ok": True,
            "status": "completed",
            "state": v2_state_spy,
        }

    monkeypatch.setattr(auto_multi_speaker_v2, "run_auto_multi_speaker_v2_blackbox", mock_v2_blackbox)

    current_state = {
        "auto_smart_multivoice_opt_in": True,
        "voice_selection_mode": "auto_smart_multivoice",
        "subdub_engine_requested": "auto_smart_multivoice",
    }

    async def dummy_prepare(state, require_auto_cast=True):
        return prepared

    payload = {
        "prepare_subtitles": dummy_prepare,
        "cues": cues,
    }

    result = asyncio.run(
        auto_smart_multivoice.run_auto_smart_multivoice_blackbox(
            lane_mode="dub",
            runner=MagicMock(),
            state=current_state,
            **payload,
        )
    )

    # Invariant §6: subdub_engine_selected and auto_smart_dispatch must be set in state BEFORE invoking V2
    assert v2_state_spy.get("subdub_engine_selected") == "auto_multi_speaker_v2"
    assert v2_state_spy.get("auto_smart_dispatch") == "n3_plus_proven_v2"
    assert result.get("state", {}).get("subdub_engine_selected") == "auto_multi_speaker_v2"


def test_first_red_h_no_selected_engine_fabrication():
    """Case H: Before dispatch, subdub_engine_selected is empty; no fallback to engine_requested."""
    state = {
        "auto_smart_multivoice_opt_in": True,
        "voice_selection_mode": "auto_smart_multivoice",
        "subdub_engine_requested": "auto_smart_multivoice",
        "subdub_engine_selected": "",  # Empty!
    }
    payload = bot.subtitle_dub_debug_job_payload(
        user_id="u1",
        chat_id="c1",
        mode=bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        state=state,
        status="running",
        stage="init",
    )
    # Must NOT fallback to auto_smart_multivoice
    assert payload.get("subdub_engine_selected") == ""


def test_first_red_i_e2e_word_timeline_detail(monkeypatch, tmp_path):
    """Case I: Deepgram transcript ok, timeline missing -> AutoCastUnavailable with deepgram_word_timeline_missing."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "dummy_deepgram_key")
    dummy_source = tmp_path / "test.mp4"
    dummy_source.write_bytes(b"dummy_mp4_bytes")

    async def fake_resolve(*args, **kwargs):
        return {
            "source_kind": "asr",
            "subtitle": "1\n00:00:00,000 --> 00:00:01,000\nHello",
            "script": "Hello",
            "asr_provider": "deepgram",
            "detail": "ok",
            "segments": [{"start": 0.0, "end": 1.0, "text": "Hello"}],
            "word_timeline": [],  # Missing timeline!
            "duration_seconds": 1,
        }

    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", fake_resolve)
    monkeypatch.setattr(bot, "video_dubbing_download_source", AsyncMock(return_value=(b"dummy_mp4_bytes", "video/mp4")))

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
    assert exc_info.value.detail == "deepgram_word_timeline_missing"


def test_first_red_j_e2e_local_acoustic_failure_detail(monkeypatch, tmp_path):
    """Case J: Provider labels absent, local acoustic fails -> exact detail local_acoustic_authority_insufficient."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "dummy_deepgram_key")
    dummy_source = tmp_path / "test.mp4"
    dummy_source.write_bytes(b"dummy_mp4_bytes")

    word_timeline = [{"index": 0, "word": "Hello", "start": 0.0, "end": 0.5}]
    unlabeled_segments = [{"start": 0.0, "end": 0.5, "text": "Hello"}]

    async def fake_resolve(*args, **kwargs):
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

    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", fake_resolve)
    monkeypatch.setattr(bot, "video_dubbing_download_source", AsyncMock(return_value=(b"dummy_mp4_bytes", "video/mp4")))

    dummy_pcm = tmp_path / "test.pcm"
    dummy_pcm.write_bytes(b"\x00" * 44100 * 2 * 2)
    monkeypatch.setattr(bot, "_extract_subdub_auto_pcm", AsyncMock(return_value=str(dummy_pcm)))

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
    assert exc_info.value.detail == "local_acoustic_authority_insufficient"


def test_first_red_k_provider_labels_present_no_local_diarization(monkeypatch, tmp_path):
    """Case K: Provider labels present -> labeled path used, local acoustic diarization NOT called."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "dummy_deepgram_key")
    dummy_source = tmp_path / "test.mp4"
    dummy_source.write_bytes(b"dummy_mp4_bytes")

    word_timeline = [
        {"index": 0, "word": "One", "start": 0.0, "end": 0.5},
        {"index": 1, "word": "Two", "start": 0.6, "end": 1.0},
    ]
    labeled_segments = [
        {"start": 0.0, "end": 0.5, "text": "One", "speaker": 0},
        {"start": 0.6, "end": 1.0, "text": "Two", "speaker": 1},
    ]

    async def fake_resolve(*args, **kwargs):
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

    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", fake_resolve)
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
    assert local_diarization_spy.called is False
    assert len(prepared.get("source_segments") or []) == 2


def test_first_red_l_provider_labels_absent_local_diarization(monkeypatch, tmp_path):
    """Case L: Provider labels absent -> local acoustic diarization IS called."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "dummy_deepgram_key")
    dummy_source = tmp_path / "test.mp4"
    dummy_source.write_bytes(b"dummy_mp4_bytes")

    word_timeline = [{"index": 0, "word": "Hello", "start": 0.0, "end": 0.5}]
    unlabeled_segments = [{"start": 0.0, "end": 0.5, "text": "Hello"}]

    async def fake_resolve(*args, **kwargs):
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

    monkeypatch.setattr(bot, "video_dubbing_resolve_source_script", fake_resolve)
    monkeypatch.setattr(bot, "video_dubbing_download_source", AsyncMock(return_value=(b"dummy_mp4_bytes", "video/mp4")))

    dummy_pcm = tmp_path / "test.pcm"
    dummy_pcm.write_bytes(b"\x00" * 44100 * 2 * 2)
    monkeypatch.setattr(bot, "_extract_subdub_auto_pcm", AsyncMock(return_value=str(dummy_pcm)))

    local_diarization_spy = MagicMock(return_value={
        "provider": "onnx_cam_v1",
        "model_sha256": "dummy_sha",
        "algorithm_version": "v1",
        "detected_speaker_count": 3,
        "word_count": 1,
        "unit_count": 1,
        "embedding_window_count": 2,
        "cluster_sizes": [1],
        "stability_pass": True,
        "word_coverage_count": 1,
        "overlap_mapped_count": 0,
        "centroid_mapped_count": 1,
        "speaker_unit_counts": [1],
        "word_overlap_mapped_count": 0,
        "word_fallback_mapped_count": 0,
        "word_centroid_mapped_count": 1,
        "speaker_count_authority_asr_independent": True,
        "word_attribution_uses_asr_timeline": True,
        "speaker_registers": ["low"],
        "speaker_register_confidences": [0.95],
        "female_speaker_count": 0,
        "male_speaker_count": 1,
        "gender_model_sha256": "dummy_gender_sha",
        "gender_ambiguous_window_count": 0,
        "raw_speaker_count": 1,
        "raw_embedding_window_count": 2,
        "raw_cluster_sizes": [1],
        "raw_speaker_unit_counts": [1],
        "raw_overlap_speaker_unit_counts": [0],
        "speech_supported_speaker_labels": ["speaker_0"],
        "dropped_non_speech_speaker_labels": [],
        "segments": [{"start": 0.0, "end": 0.5, "text": "Hello", "speaker": "speaker_0", "speaker_id": "speaker_0"}],
    })
    monkeypatch.setattr(auto_multi_speaker, "run_local_acoustic_diarization_off_event_loop", AsyncMock(side_effect=local_diarization_spy))
    monkeypatch.setattr(auto_multi_speaker, "bounded_multi_acoustic_evidence", MagicMock(return_value={"multi_acoustic_speaker_count": 3}))

    _voice_keys = {
        "auto_smart_multivoice_opt_in", "voice_selection_mode",
        "auto_speaker_lane", "auto_smart_multivoice", "auto_multi_engine", "subdub_mode",
    }
    monkeypatch.setattr(bot, "set_video_dubbing_artifact", MagicMock(return_value="artifact_ref"))
    monkeypatch.setattr(
        bot, "video_dubbing_sync_state_fields",
        MagicMock(side_effect=lambda st, **kw: {k: v for k, v in st.items() if k in _voice_keys}),
    )
    monkeypatch.setattr(bot, "set_video_dubbing_pending", MagicMock(side_effect=lambda user_id, step, **kw: {"step": step, **kw}))
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

    asyncio.run(
        bot.video_dubbing_prepare_subtitles(
            context=MagicMock(),
            state=state,
            user_id="test_user",
            allow_confirmed_product=True,
            require_auto_cast=True,
        )
    )
    assert local_diarization_spy.called is True


def test_first_red_m_non_smart_regression(monkeypatch):
    """Case M: Non-Smart SubDub lane (standard subtitle creation).

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
