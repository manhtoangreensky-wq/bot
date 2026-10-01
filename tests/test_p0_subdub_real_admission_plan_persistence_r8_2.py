import asyncio
import json
import time

import bot
from services import subdub_multi_speaker_gender_onnx as multi_onnx
from services import subdub_speaker_cast
from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_multi_speaker
from services.subdub_blackboxes import auto_smart_multivoice
import pytest


@pytest.fixture(autouse=True)
def clean_subdub_jobs():
    original_jobs = dict(bot.SUBTITLE_DUB_PIPELINE_JOBS)
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    yield
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.SUBTITLE_DUB_PIPELINE_JOBS.update(original_jobs)


def test_first_red_a_real_admission_deepgram_missing(monkeypatch):
    """
    §12 Real Admission First Red A:
    Deepgram absent.
    Spy real DB insert (save_engine_async_job) and in-memory registry.
    Require: DB_INSERT_CALLS=0, OUTBOX_CALLS=0, DISPATCH_CALLS=0, detail=deepgram_asr_not_configured
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "")
    saved_jobs = []
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: (saved_jobs.append(payload), payload)[1])

    job_key = "test_subdub_job_key_a"
    state = {
        "auto_smart_multivoice_opt_in": True,
        "subdub_final_confirmed": True,
        "subdub_engine_requested": "auto_smart_multivoice",
        "mode": "dub",
        "user_id": 9901,
        "chat_id": 9901,
    }

    acquired, result = bot.acquire_subtitle_dub_pipeline_job(job_key, **state)

    assert acquired is False
    assert len(saved_jobs) == 0, "Real DB insert must NOT occur when Deepgram is absent"
    assert job_key not in bot.SUBTITLE_DUB_PIPELINE_JOBS, "Job must NOT be in in-memory registry"
    assert result.get("admitted") is False
    assert result.get("detail") == "deepgram_asr_not_configured"


def test_first_red_b_real_admission_final_confirm_missing(monkeypatch):
    """
    §13 Real Admission First Red B:
    Deepgram configured. Final confirmation absent.
    Require: DB_INSERT_CALLS=0, OUTBOX_CALLS=0, DISPATCH_CALLS=0, blocker=FINAL_CONFIRMATION_MISSING
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-active")
    saved_jobs = []
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: (saved_jobs.append(payload), payload)[1])

    job_key = "test_subdub_job_key_b"
    state = {
        "auto_smart_multivoice_opt_in": True,
        "subdub_final_confirmed": False,
        "subdub_engine_requested": "auto_smart_multivoice",
        "mode": "dub",
        "user_id": 9902,
        "chat_id": 9902,
    }

    acquired, result = bot.acquire_subtitle_dub_pipeline_job(job_key, **state)

    assert acquired is False
    assert len(saved_jobs) == 0, "Real DB insert must NOT occur when final confirmation is missing"
    assert job_key not in bot.SUBTITLE_DUB_PIPELINE_JOBS
    assert result.get("admitted") is False
    assert result.get("blocker_class") == "FINAL_CONFIRMATION_MISSING"
    assert result.get("detail") == "subdub_final_confirmation_required"


def test_first_red_c_real_admission_ready_job_insert(monkeypatch):
    """
    §14 Real Admission First Red C:
    Deepgram configured. Final confirmation valid.
    Require: DB_INSERT_CALLS=1.
    Exact persisted job payload contains immutable plan snapshot fields.
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-active")
    saved_jobs = []
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: (saved_jobs.append(payload), payload)[1])

    job_key = "test_subdub_job_key_c"
    state = {
        "auto_smart_multivoice_opt_in": True,
        "subdub_final_confirmed": True,
        "subdub_engine_requested": "auto_smart_multivoice",
        "mode": "dub",
        "user_id": 9903,
        "chat_id": 9903,
    }

    acquired, job = bot.acquire_subtitle_dub_pipeline_job(job_key, **state)

    assert acquired is True
    assert len(saved_jobs) == 1, "Exactly 1 real DB insert must occur on ready admission"
    assert job_key in bot.SUBTITLE_DUB_PIPELINE_JOBS

    persisted = saved_jobs[0]
    assert persisted.get("subdub_asr_plan_version") == "r8_2"
    assert persisted.get("subdub_asr_route_id") == "deepgram_word_timeline"
    assert persisted.get("subdub_asr_provider") == "deepgram"
    assert persisted.get("subdub_asr_require_word_timeline") is True
    assert persisted.get("subdub_asr_require_provider_speaker_labels") is False
    assert persisted.get("subdub_local_acoustic_diarization_allowed") is True
    assert persisted.get("subdub_engine_requested") == "auto_smart_multivoice"
    assert persisted.get("auto_smart_multivoice_opt_in") is True
    assert persisted.get("subdub_final_confirmed") is True
    assert persisted.get("subdub_engine_selected") == ""
    assert persisted.get("asr_route_called") is False


def test_worker_reload_snapshot_survival(monkeypatch):
    """
    §15 Worker Reload First Red:
    Serialize inserted job (JSON) and reload through worker read authority.
    Snapshot survives intact and execution helper consumes it.
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-active")
    saved_jobs = []
    monkeypatch.setattr(bot, "save_engine_async_job", lambda payload: (saved_jobs.append(payload), payload)[1])

    job_key = "test_subdub_job_key_reload"
    state = {
        "auto_smart_multivoice_opt_in": True,
        "subdub_final_confirmed": True,
        "subdub_engine_requested": "auto_smart_multivoice",
        "mode": "dub",
        "user_id": 9904,
        "chat_id": 9904,
    }

    acquired, job = bot.acquire_subtitle_dub_pipeline_job(job_key, **state)
    assert acquired is True

    # Simulate DB serialization and deserialization
    serialized = json.dumps(saved_jobs[0])
    reloaded_job = json.loads(serialized)

    assert reloaded_job.get("subdub_asr_plan_version") == "r8_2"
    assert reloaded_job.get("subdub_asr_route_id") == "deepgram_word_timeline"
    assert reloaded_job.get("subdub_asr_provider") == "deepgram"
    assert reloaded_job.get("subdub_asr_require_word_timeline") is True
    assert reloaded_job.get("subdub_asr_require_provider_speaker_labels") is False
    assert reloaded_job.get("subdub_local_acoustic_diarization_allowed") is True

    exec_kwargs = bot.resolve_subdub_execution_asr_kwargs(reloaded_job)
    assert exec_kwargs.get("require_auto_multi_word_timeline") is True
    assert exec_kwargs.get("require_diarization") is False


def test_execution_plan_first_red_no_recompute(monkeypatch):
    """
    §16 Execution Plan First Red:
    For current-version jobs, resolve_subdub_asr_plan must NOT be recomputed.
    Legacy jobs without plan version still permit compatibility resolution.
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-active")

    resolver_called = []
    original_resolver = bot.resolve_subdub_asr_plan

    def spy_resolver(*args, **kwargs):
        resolver_called.append((args, kwargs))
        return original_resolver(*args, **kwargs)

    monkeypatch.setattr(bot, "resolve_subdub_asr_plan", spy_resolver)

    versioned_job = {
        "subdub_asr_plan_version": "r8_2",
        "subdub_asr_route_id": "deepgram_word_timeline",
        "subdub_asr_provider": "deepgram",
        "subdub_asr_require_word_timeline": True,
        "subdub_asr_require_provider_speaker_labels": False,
        "subdub_local_acoustic_diarization_allowed": True,
    }

    kwargs = bot.resolve_subdub_execution_asr_kwargs(versioned_job)
    assert len(resolver_called) == 0, "Must NOT recompute ASR plan for current-version jobs"
    assert kwargs.get("require_auto_multi_word_timeline") is True
    assert kwargs.get("require_diarization") is False

    # Legacy job without subdub_asr_plan_version
    legacy_job = {
        "auto_smart_multivoice_opt_in": True,
        "mode": "dub",
        "subdub_final_confirmed": True,
    }
    legacy_kwargs = bot.resolve_subdub_execution_asr_kwargs(legacy_job)
    assert len(resolver_called) == 1, "Legacy jobs without version must allow compatibility resolution"
    assert legacy_kwargs.get("require_auto_multi_word_timeline") is True


def test_execution_fail_closed_on_incomplete_snapshot():
    """
    §8 Plan Version Fail-Closed:
    Current-version job missing required snapshot field must fail closed with subdub_asr_plan_snapshot_incomplete.
    """
    incomplete_job = {
        "subdub_asr_plan_version": "r8_2",
        "subdub_asr_route_id": "deepgram_word_timeline",
        "subdub_asr_provider": "deepgram",
        # missing subdub_asr_require_word_timeline
        "subdub_asr_require_provider_speaker_labels": False,
        "subdub_local_acoustic_diarization_allowed": True,
    }

    with pytest.raises(RuntimeError) as exc_info:
        bot.resolve_subdub_execution_asr_kwargs(incomplete_job)
    assert "subdub_asr_plan_snapshot_incomplete" in str(exc_info.value)


def test_execution_runtime_dependency_drift(monkeypatch):
    """
    §9 Config Drift After Job Create:
    Admission occurred with Deepgram. At execution time DEEPGRAM_API_KEY is missing.
    Must fail explicitly with subdub_asr_runtime_dependency_unavailable.
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "")

    job = {
        "subdub_asr_plan_version": "r8_2",
        "subdub_asr_route_id": "deepgram_word_timeline",
        "subdub_asr_provider": "deepgram",
        "subdub_asr_require_word_timeline": True,
        "subdub_asr_require_provider_speaker_labels": False,
        "subdub_local_acoustic_diarization_allowed": True,
    }

    with pytest.raises(RuntimeError) as exc_info:
        bot.resolve_subdub_execution_asr_kwargs(job)
    assert "subdub_asr_runtime_dependency_unavailable" in str(exc_info.value)


def test_physical_asr_event_case1_resolver_without_provider(monkeypatch):
    """
    §17 Physical ASR Event Case 1:
    Resolver called, but provider adapter never invoked (e.g. embedded subtitle).
    require: asr_route_called=false
    """
    state = {
        "subdub_asr_plan_version": "r8_2",
        "asr_route_called": False,
        "mode": "dub",
        "_pipeline_workspace": "dummy_ws",
    }

    async def mock_extract_embedded(source_bytes, content_type):
        return ("1\n00:00:01,000 --> 00:00:02,000\nHello", "embedded_ok")

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", mock_extract_embedded)

    # Provider adapter spy
    adapter_called = []
    async def mock_adapter(*args, **kwargs):
        adapter_called.append(True)
        return {"ok": True}
    monkeypatch.setattr(bot, "deepgram_asr_adapter", mock_adapter)

    # Resolve without requiring auto-cast/speaker evidence
    result = asyncio.run(
        bot.video_dubbing_resolve_source_script(
            b"dummy_bytes",
            "video/mp4",
            None,
            require_diarization=False,
            require_auto_multi_word_timeline=False,
        )
    )

    assert result.get("source_kind") == "embedded_subtitle"
    assert len(adapter_called) == 0
    assert state.get("asr_route_called") is False


def test_physical_asr_event_case2_adapter_invoked_then_errors(monkeypatch):
    """
    §17 Physical ASR Event Case 2:
    Deepgram adapter invoked, then errors.
    require: asr_route_called=true, subdub_asr_provider_called=deepgram
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key")

    active_state = {
        "subdub_asr_plan_version": "r8_2",
        "asr_route_called": False,
        "mode": "dub",
    }
    bot.set_subdub_active_pipeline_state(active_state)

    async def mock_agent_diagnostic(*args, **kwargs):
        return {"ok": False, "http_status": 500, "error": "Internal Deepgram Error"}

    monkeypatch.setattr(bot.AgentDeepgram, "diagnostic", mock_agent_diagnostic)

    res = asyncio.run(bot.deepgram_asr_adapter(b"fake_audio_bytes", require_diarization=False))

    assert res.get("ok") is False
    assert active_state.get("asr_route_called") is True
    assert active_state.get("subdub_asr_provider_called") == "deepgram"
    assert active_state.get("subdub_asr_called_at", 0) > 0


def test_physical_asr_event_case3_and_failure_persistence(monkeypatch):
    """
    §17 Case 3 & §18 Persist Event Truth After Downstream Failure:
    Deepgram invoked successfully, but downstream auto_smart_multivoice raises AUTO_CAST_UNAVAILABLE.
    require: asr_route_called=true, subdub_asr_provider_called=deepgram, ERROR_CODE=AUTO_CAST_UNAVAILABLE
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key")

    current_state = {
        "subdub_asr_plan_version": "r8_2",
        "asr_route_called": False,
        "mode": "dub",
        "_pipeline_workspace": "dummy_ws",
    }

    async def mock_prepare_subtitles(state, require_auto_cast=False):
        # Simulate physical adapter was called
        state["asr_route_called"] = True
        state["subdub_asr_provider_called"] = "deepgram"
        state["subdub_asr_called_at"] = int(time.time())
        # Then downstream raises AutoCastUnavailable
        err = subdub_speaker_cast.AutoCastUnavailable()
        err.detail = "deepgram_word_timeline_missing"
        raise err

    payload = {
        "state": current_state,
        "prepare_subtitles": mock_prepare_subtitles,
        "lane_mode": "dub",
    }

    result = asyncio.run(auto_smart_multivoice.execute_smart_multivoice_lane(payload))

    assert result.get("ok") is False
    assert result.get("status") == "AUTO_CAST_UNAVAILABLE"
    assert result.get("error_code") == "AUTO_CAST_UNAVAILABLE"
    assert result.get("detail") == "deepgram_word_timeline_missing"

    # Crucial: Event truth must NOT be lost during exception handling
    res_state = result.get("state") or {}
    assert res_state.get("asr_route_called") is True, "asr_route_called MUST survive exception"
    assert res_state.get("subdub_asr_provider_called") == "deepgram", "provider MUST survive exception"


def test_engine_provenance_and_acoustic_invariants():
    """
    §19 & §25 Engine Provenance and Acoustic Invariants:
    Verify constants and N>=3 engine provenance.
    """
    assert speaker_cast.MIN_REGISTER_CONFIDENCE == 0.75
    assert multi_onnx.MIN_PANN_SCORE_MARGIN == 0.08
    assert auto_smart_multivoice.MAX_INTELLIGIBLE_FIT_RATIO == 1.8

    # N>=3 strong dispatch constants
    assert hasattr(auto_smart_multivoice, "AUTO_SMART_N3_PLUS_DISPATCH_STRATEGY")
    assert auto_smart_multivoice.AUTO_SMART_N3_PLUS_DISPATCH_STRATEGY == "n3_plus_proven_v2"
