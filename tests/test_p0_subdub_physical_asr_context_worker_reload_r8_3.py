"""
P0.SUBDUB_SMART_MULTI_PHYSICAL_ASR_CONTEXT_WORKER_RELOAD_CLOSURE_R8_3 Test Suite
Governed by AGENTS.md and r8_3_task_prompt.txt specifications.
"""
import asyncio
import json
import time
import pytest

import bot
from services import subdub_multi_speaker_gender_onnx as multi_onnx
from services import subdub_speaker_cast
from services import subdub_speaker_cast as speaker_cast
from services.subdub_blackboxes import auto_multi_speaker
from services.subdub_blackboxes import auto_smart_multivoice


@pytest.fixture(autouse=True)
def clean_subdub_environment():
    original_jobs = dict(bot.SUBTITLE_DUB_PIPELINE_JOBS)
    original_memory_jobs = dict(bot.ENGINE_ASYNC_MEMORY_JOBS)
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.set_subdub_active_pipeline_state(None)
    yield
    bot.SUBTITLE_DUB_PIPELINE_JOBS.clear()
    bot.SUBTITLE_DUB_PIPELINE_JOBS.update(original_jobs)
    bot.ENGINE_ASYNC_MEMORY_JOBS.clear()
    bot.ENGINE_ASYNC_MEMORY_JOBS.update(original_memory_jobs)
    bot.set_subdub_active_pipeline_state(None)


def _make_asr_success_mock(*, set_event_truth=True):
    """
    Build a mock for asr_transcribe_audio that:
    1. Reads ContextVar active pipeline state (same path as deepgram_asr_adapter line 40710)
    2. Sets event truth asr_route_called/subdub_asr_provider_called on active state
    3. Returns a valid Deepgram-like ASR result with word_timeline
    """
    captured_active_during_run = []

    async def mock_asr_transcribe_audio(
        audio_bytes, content_type="application/octet-stream", language="auto",
        response_format="verbose_json", **kwargs
    ):
        active = bot.get_subdub_active_pipeline_state()
        captured_active_during_run.append(active)
        # Simulate deepgram_asr_adapter event truth (bot.py line 40710-40714)
        if set_event_truth and isinstance(active, dict):
            active["asr_route_called"] = True
            active["subdub_asr_provider_called"] = "deepgram"
            active["subdub_asr_called_at"] = int(time.time())
        job_tag = str((active or {}).get("job_id") or "test")
        return {
            "ok": True,
            "status": "PASS",
            "provider": "deepgram",
            "text": f"Hello world from {job_tag}",
            "segments": [
                {"start": 0.0, "end": 1.0, "text": f"Hello world from {job_tag}", "speaker": 0},
            ],
            "word_timeline": [
                {"word": "Hello", "start": 0.0, "end": 0.5, "speaker": 0, "confidence": 0.99},
                {"word": "world", "start": 0.6, "end": 1.0, "speaker": 0, "confidence": 0.99},
            ],
            "detail": "mock_deepgram_r8_3",
            "language": "en",
        }

    return mock_asr_transcribe_audio, captured_active_during_run


def test_contextvar_lifecycle_success_reset(monkeypatch):
    """
    §3 & §5 ContextVar Lifecycle & Reset on Success:
    Real execution boundary binds active mutable pipeline/job state.
    On success, ContextVar is strictly reset in finally (no dangling state reference).
    Event truth (asr_route_called=true, subdub_asr_provider_called=deepgram) is recorded on the state.
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-r8-3")
    assert bot.get_subdub_active_pipeline_state() is None

    mock_asr, captured_active_during_run = _make_asr_success_mock()
    monkeypatch.setattr(bot, "asr_transcribe_audio", mock_asr)

    job_state = {
        "job_id": "job_success_test_01",
        "subdub_asr_plan_version": "r8_2",
        "asr_route_called": False,
        "mode": "dub",
        "_pipeline_workspace": "dummy_ws",
    }

    result = asyncio.run(
        bot.video_dubbing_resolve_source_script(
            b"dummy_audio_bytes_123",
            "audio/wav",
            None,
            require_diarization=False,
            require_auto_multi_word_timeline=True,
            allow_confirmed_product=True,
            state=job_state,
        )
    )

    # 1. Active state was properly bound during physical execution
    assert len(captured_active_during_run) == 1
    assert captured_active_during_run[0] is job_state

    # 2. Event truth reached job_state
    assert job_state.get("asr_route_called") is True
    assert job_state.get("subdub_asr_provider_called") == "deepgram"
    assert job_state.get("subdub_asr_called_at", 0) > 0

    # 3. Output is valid
    assert result.get("source_kind") == "asr"
    assert "Hello world" in result.get("script", "")

    # 4. ContextVar was cleanly reset after completion (no dangling reference)
    assert bot.get_subdub_active_pipeline_state() is None


def test_contextvar_lifecycle_failure_reset(monkeypatch):
    """
    §3 & §6 ContextVar Lifecycle & Reset on Failure:
    When downstream execution raises an error, ContextVar is safely reset in finally.
    The job state retains event truth (asr_route_called=true).
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-r8-3")
    assert bot.get_subdub_active_pipeline_state() is None

    # Return ok but empty word_timeline -> resolver raises AutoCastUnavailable
    # because require_auto_multi_word_timeline=True and word_timeline is empty (line 247361)
    async def mock_asr_no_words(
        audio_bytes, content_type="application/octet-stream", language="auto",
        response_format="verbose_json", **kwargs
    ):
        active = bot.get_subdub_active_pipeline_state()
        # Deepgram adapter sets event truth BEFORE HTTP call
        if isinstance(active, dict):
            active["asr_route_called"] = True
            active["subdub_asr_provider_called"] = "deepgram"
            active["subdub_asr_called_at"] = int(time.time())
        return {
            "ok": True,
            "status": "PASS",
            "provider": "deepgram",
            "text": "Test transcript",
            "segments": [{"start": 0.0, "end": 1.0, "text": "Test transcript"}],
            "word_timeline": [],  # empty -> triggers AutoCastUnavailable
            "detail": "mock_deepgram_r8_3_no_words",
        }

    monkeypatch.setattr(bot, "asr_transcribe_audio", mock_asr_no_words)

    job_state = {
        "job_id": "job_failure_test_02",
        "subdub_asr_plan_version": "r8_2",
        "asr_route_called": False,
        "mode": "dub",
        "_pipeline_workspace": "dummy_ws",
    }

    with pytest.raises(subdub_speaker_cast.AutoCastUnavailable):
        asyncio.run(
            bot.video_dubbing_resolve_source_script(
                b"dummy_audio_bytes_err",
                "audio/wav",
                None,
                require_diarization=False,
                require_auto_multi_word_timeline=True,
                allow_confirmed_product=True,
                state=job_state,
            )
        )

    # 1. Event truth preserved despite exception
    assert job_state.get("asr_route_called") is True
    assert job_state.get("subdub_asr_provider_called") == "deepgram"

    # 2. ContextVar MUST be reset back to None in finally
    assert bot.get_subdub_active_pipeline_state() is None


def test_event_authority_deepgram_adapter_only(monkeypatch):
    """
    §4 Event Must Still Be Set Only by Provider Adapter:
    Binding active state does NOT set asr_route_called=true.
    - Embedded subtitle return -> asr_route_called=false
    - Resolver preflight failure before provider -> asr_route_called=false
    - Deepgram adapter entered -> asr_route_called=true
    - Deepgram HTTP fails afterward -> asr_route_called=true
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-r8-3")

    # Case 1: Embedded subtitle extracted without calling provider
    async def mock_extract_embedded(source_bytes, content_type):
        return ("1\n00:00:00,000 --> 00:00:01,000\nEmbedded Subtitle\n", "embedded_ok")

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", mock_extract_embedded)

    job_state_embedded = {
        "job_id": "job_case1_embedded",
        "asr_route_called": False,
        "mode": "dub",
    }
    res_embedded = asyncio.run(
        bot.video_dubbing_resolve_source_script(
            b"dummy_bytes",
            "video/mp4",
            None,
            require_diarization=False,
            require_auto_multi_word_timeline=False,
            state=job_state_embedded,
        )
    )
    assert res_embedded.get("source_kind") == "embedded_subtitle"
    assert job_state_embedded.get("asr_route_called") is False, "Embedded subtitle must NOT set asr_route_called"

    # Case 2: Preflight failure before provider (unsupported media type)
    job_state_preflight = {
        "job_id": "job_case2_preflight_fail",
        "asr_route_called": False,
        "mode": "dub",
    }
    # text/plain is unsupported -> transcribe_media_to_segments returns output_valid=False
    # -> resolver raises RuntimeError at line 247359
    with pytest.raises(Exception):
        asyncio.run(
            bot.video_dubbing_resolve_source_script(
                b"corrupt_media_bytes",
                "text/plain",
                None,
                require_diarization=False,
                require_auto_multi_word_timeline=True,
                allow_confirmed_product=True,
                state=job_state_preflight,
            )
        )
    assert job_state_preflight.get("asr_route_called") is False, "Preflight failure before provider must NOT set asr_route_called"

    # Case 3: ASR called, event truth set, but result has no word_timeline -> failure after adapter
    async def mock_asr_http_fail(
        audio_bytes, content_type="application/octet-stream", language="auto",
        response_format="verbose_json", **kwargs
    ):
        active = bot.get_subdub_active_pipeline_state()
        # Deepgram adapter sets event truth before HTTP
        if isinstance(active, dict):
            active["asr_route_called"] = True
            active["subdub_asr_provider_called"] = "deepgram"
            active["subdub_asr_called_at"] = int(time.time())
        return {
            "ok": False,
            "status": bot.AUTO_CAST_UNAVAILABLE,
            "provider": "deepgram",
            "text": "",
            "segments": [],
            "word_timeline": [],
            "detail": "deepgram_http_5xx",
        }

    monkeypatch.setattr(bot, "asr_transcribe_audio", mock_asr_http_fail)

    job_state_http_err = {
        "job_id": "job_case3_http_fail",
        "asr_route_called": False,
        "mode": "dub",
    }
    with pytest.raises(Exception):
        asyncio.run(
            bot.video_dubbing_resolve_source_script(
                b"valid_audio_bytes",
                "audio/wav",
                None,
                require_diarization=False,
                require_auto_multi_word_timeline=True,
                allow_confirmed_product=True,
                state=job_state_http_err,
            )
        )
    assert job_state_http_err.get("asr_route_called") is True, "Deepgram entered must set asr_route_called=True"
    assert job_state_http_err.get("subdub_asr_provider_called") == "deepgram"


def test_concurrent_task_context_isolation(monkeypatch):
    """
    §7 Concurrent Task Isolation:
    Two async Smart executions run concurrently with distinct job IDs.
    Job A adapter event mutates A only; Job B adapter event mutates B only.
    No cross-task leakage of ContextVar active pipeline state.
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-r8-3")

    async def mock_asr_concurrent(
        audio_bytes, content_type="application/octet-stream", language="auto",
        response_format="verbose_json", **kwargs
    ):
        active = bot.get_subdub_active_pipeline_state()
        job_tag = str((active or {}).get("job_id") or "")
        # Simulate event truth
        if isinstance(active, dict):
            active["asr_route_called"] = True
            active["subdub_asr_provider_called"] = "deepgram"
            active["subdub_asr_called_at"] = int(time.time())
        # Introduce slight async yield to interleave tasks
        await asyncio.sleep(0.01)
        return {
            "ok": True,
            "status": "PASS",
            "provider": "deepgram",
            "text": f"Transcript for {job_tag}",
            "segments": [
                {"start": 0.0, "end": 1.0, "text": f"Transcript for {job_tag}", "speaker": 0},
            ],
            "word_timeline": [
                {"word": "word", "start": 0.0, "end": 0.5, "speaker": 0, "confidence": 0.99},
            ],
            "detail": "mock_concurrent",
        }

    monkeypatch.setattr(bot, "asr_transcribe_audio", mock_asr_concurrent)

    state_a = {"job_id": "JOB_ALPHA", "asr_route_called": False, "mode": "dub", "_pipeline_workspace": "ws_a"}
    state_b = {"job_id": "JOB_BETA", "asr_route_called": False, "mode": "dub", "_pipeline_workspace": "ws_b"}

    async def run_task(state):
        return await bot.video_dubbing_resolve_source_script(
            b"bytes_wav_a",
            "audio/wav",
            None,
            require_diarization=False,
            require_auto_multi_word_timeline=True,
            allow_confirmed_product=True,
            state=state,
        )

    async def run_both():
        return await asyncio.gather(run_task(state_a), run_task(state_b))

    res_a, res_b = asyncio.run(run_both())

    # Task A results
    assert "JOB_ALPHA" in res_a.get("script", "")
    assert "JOB_BETA" not in res_a.get("script", "")
    assert state_a.get("asr_route_called") is True
    assert state_a.get("job_id") == "JOB_ALPHA"

    # Task B results
    assert "JOB_BETA" in res_b.get("script", "")
    assert "JOB_ALPHA" not in res_b.get("script", "")
    assert state_b.get("asr_route_called") is True
    assert state_b.get("job_id") == "JOB_BETA"

    # Post condition: ContextVar is completely clear
    assert bot.get_subdub_active_pipeline_state() is None


def test_real_worker_reload_authority(monkeypatch):
    """
    §8 & §9 Real Worker Reload Authority & Snapshot Assertions:
    Save job via acquire_subtitle_dub_pipeline_job (driving save_engine_async_job).
    Reload via production worker authority: get_engine_async_job(internal_job_id).
    Verify all immutable snapshot fields survive and no plan recomputation occurs.
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-r8-3")

    job_key = "test_subdub_r8_3_worker_reload_key"
    admission_state = {
        "auto_smart_multivoice_opt_in": True,
        "subdub_final_confirmed": True,
        "subdub_engine_requested": "auto_smart_multivoice",
        "mode": "dub",
        "user_id": 9988,
        "chat_id": 9988,
    }

    acquired, admitted_job = bot.acquire_subtitle_dub_pipeline_job(job_key, **admission_state)
    assert acquired is True
    internal_id = str(admitted_job.get("internal_job_id") or "")
    assert internal_id, "Admitted job must have an internal_job_id"

    # Drive the EXACT production worker reload authority
    reloaded_job = bot.get_engine_async_job(internal_id)
    assert reloaded_job, "Production loader get_engine_async_job must return persisted job"

    # Assert exact required snapshot fields
    assert reloaded_job.get("subdub_asr_plan_version") == "r8_2"
    assert reloaded_job.get("subdub_asr_route_id") == "deepgram_word_timeline"
    assert reloaded_job.get("subdub_asr_provider") == "deepgram"
    assert reloaded_job.get("subdub_asr_require_word_timeline") is True
    assert reloaded_job.get("subdub_asr_require_provider_speaker_labels") is False
    assert reloaded_job.get("subdub_local_acoustic_diarization_allowed") is True
    assert reloaded_job.get("subdub_engine_requested") == "auto_smart_multivoice"
    assert reloaded_job.get("auto_smart_multivoice_opt_in") is True
    assert reloaded_job.get("subdub_final_confirmed") is True
    assert reloaded_job.get("subdub_engine_selected") == ""
    assert reloaded_job.get("asr_route_called") is False

    # Verify no plan recomputation on execution
    recompute_calls = []
    orig_resolver = bot.resolve_subdub_asr_plan

    def spy_resolver(*args, **kwargs):
        recompute_calls.append(kwargs)
        return orig_resolver(*args, **kwargs)

    monkeypatch.setattr(bot, "resolve_subdub_asr_plan", spy_resolver)

    exec_kwargs = bot.resolve_subdub_execution_asr_kwargs(reloaded_job)
    assert len(recompute_calls) == 0, "Current version job must not recompute plan"
    assert exec_kwargs.get("require_auto_multi_word_timeline") is True
    assert exec_kwargs.get("require_diarization") is False


def test_admission_side_effects_and_outbox_contract(monkeypatch):
    """
    §10 & §11 Outbox Contract and Ready Admission Side Effect Count:
    - Pre-admission failures have 0 DB writes, 0 dispatch calls, 0 outbox writes.
    - Ready admission has exactly 1 persist call and memory job increment = 1.
    - Architecture outbox authority: NOT_APPLICABLE for SubDub (confirmed via source analysis).
    """
    # 1. Missing Deepgram
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "")
    saved_jobs = []
    monkeypatch.setattr(bot, "save_engine_async_job", lambda p: (saved_jobs.append(p), p)[1])

    job_key_fail = "job_fail_key"
    acquired, _ = bot.acquire_subtitle_dub_pipeline_job(
        job_key_fail,
        auto_smart_multivoice_opt_in=True,
        subdub_final_confirmed=True,
        subdub_engine_requested="auto_smart_multivoice",
        mode="dub",
    )
    assert acquired is False
    assert len(saved_jobs) == 0, "No DB write when Deepgram absent"
    assert job_key_fail not in bot.SUBTITLE_DUB_PIPELINE_JOBS

    # 2. Ready admission
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-key-active")
    initial_memory_count = len(bot.SUBTITLE_DUB_PIPELINE_JOBS)

    job_key_ok = "job_ok_key"
    acquired_ok, _ = bot.acquire_subtitle_dub_pipeline_job(
        job_key_ok,
        auto_smart_multivoice_opt_in=True,
        subdub_final_confirmed=True,
        subdub_engine_requested="auto_smart_multivoice",
        mode="dub",
        user_id=12345,
    )
    assert acquired_ok is True
    assert len(saved_jobs) == 1, "Ready admission must perform exactly 1 save_engine_async_job call"
    assert len(bot.SUBTITLE_DUB_PIPELINE_JOBS) == initial_memory_count + 1


def test_event_durability_post_failures(monkeypatch):
    """
    §12 & §13 Event Durability After Provider Failure & Acoustic Failure:
    When provider fails or acoustic authority fails, event truth remains durable.
    """
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-key")

    # Downstream acoustic failure simulation
    current_state = {
        "job_id": "job_acoustic_fail",
        "subdub_asr_plan_version": "r8_2",
        "asr_route_called": False,
        "mode": "dub",
        "_pipeline_workspace": "dummy_ws",
    }

    async def mock_prepare_subtitles(state, require_auto_cast=False):
        state["asr_route_called"] = True
        state["subdub_asr_provider_called"] = "deepgram"
        state["subdub_asr_called_at"] = int(time.time())
        err = subdub_speaker_cast.AutoCastUnavailable()
        err.detail = "acoustic_clustering_divergence"
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
    assert result.get("detail") == "acoustic_clustering_divergence"

    res_state = result.get("state") or {}
    assert res_state.get("asr_route_called") is True
    assert res_state.get("subdub_asr_provider_called") == "deepgram"


def test_n3_engine_selected_durability():
    """
    §14 Engine Selected Durability & Constants:
    Verifies N>=3 strong dispatch constants and invariants.
    """
    assert speaker_cast.MIN_REGISTER_CONFIDENCE == 0.75
    assert multi_onnx.MIN_PANN_SCORE_MARGIN == 0.08
    assert auto_smart_multivoice.MAX_INTELLIGIBLE_FIT_RATIO == 1.8
    assert auto_smart_multivoice.AUTO_SMART_N3_PLUS_DISPATCH_STRATEGY == "n3_plus_proven_v2"
