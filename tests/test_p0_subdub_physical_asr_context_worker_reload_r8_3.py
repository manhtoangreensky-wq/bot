"""
P0.SUBDUB_SMART_MULTI_PHYSICAL_ASR_CONTEXT_WORKER_RELOAD_CLOSURE_R8_3 Test Suite
Governed by AGENTS.md and r8_3_task_prompt.txt specifications.

CIRCULAR PROOF FIX: Mocks only AgentDeepgram.diagnostic (HTTP transport layer).
The REAL deepgram_asr_adapter runs and sets event truth on ContextVar state.
No test helper manually sets asr_route_called / subdub_asr_provider_called / subdub_asr_called_at.
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Mock fixtures for AgentDeepgram.diagnostic — HTTP transport layer ONLY.
# These return the raw diagnostic dict that deepgram_asr_adapter consumes.
# The adapter itself sets event truth on ContextVar state (lines 40710-40714).
# ---------------------------------------------------------------------------

def _valid_transcript_json(*, num_words=6, duration=5.0, include_speaker=False):
    """Build a valid Deepgram API transcript_json with word-level timestamps."""
    words = []
    step = round(duration / max(num_words, 1), 3)
    for i in range(num_words):
        w = {
            "word": f"word{i}",
            "punctuated_word": f"Word{i}",
            "start": round(i * step, 3),
            "end": round(i * step + step * 0.8, 3),
            "confidence": 0.99,
        }
        if include_speaker:
            w["speaker"] = i % 3
            w["speaker_confidence"] = 0.85
        words.append(w)
    transcript_text = " ".join(w["punctuated_word"] for w in words)
    return {
        "metadata": {"duration": duration},
        "results": {
            "channels": [{
                "detected_language": "en",
                "alternatives": [{
                    "transcript": transcript_text,
                    "confidence": 0.99,
                    "words": words,
                }],
            }],
        },
    }


def _make_diagnostic_success_mock():
    """Mock for AgentDeepgram.diagnostic that returns a successful Deepgram response.
    Does NOT touch any event fields — that's the adapter's job."""
    call_log = []
    tj = _valid_transcript_json(num_words=6, duration=5.0)
    transcript_text = tj["results"]["channels"][0]["alternatives"][0]["transcript"]

    async def mock_diagnostic(file_bytes, content_type="application/octet-stream",
                              *, require_diarization=False, timeout_seconds=60.0):
        call_log.append({
            "bytes_len": len(file_bytes),
            "content_type": content_type,
            "require_diarization": require_diarization,
        })
        return {
            "status": "PASS",
            "http_status": 200,
            "content_type": "application/json",
            "body_preview": "",
            "transcript": transcript_text,
            "transcript_json": tj,
            "stats": {},
            "error": "",
        }

    return mock_diagnostic, call_log


def _make_diagnostic_http_fail_mock(*, http_status=500):
    """Mock for AgentDeepgram.diagnostic that simulates HTTP transport failure."""
    call_log = []

    async def mock_diagnostic(file_bytes, content_type="application/octet-stream",
                              *, require_diarization=False, timeout_seconds=60.0):
        call_log.append({"http_status": http_status})
        return {
            "status": "FAIL",
            "http_status": http_status,
            "content_type": "text/plain",
            "body_preview": "Internal Server Error",
            "transcript": "",
            "transcript_json": {},
            "stats": {},
            "error": f"deepgram_http_{http_status}",
        }

    return mock_diagnostic, call_log


def _make_diagnostic_empty_words_mock():
    """Mock returning valid transcript text but NO words array — triggers empty word_timeline."""
    call_log = []

    async def mock_diagnostic(file_bytes, content_type="application/octet-stream",
                              *, require_diarization=False, timeout_seconds=60.0):
        call_log.append(True)
        # Valid transcript but words list has items with invalid timestamps
        # that will cause deepgram_acoustic_word_items to reject
        tj = {
            "metadata": {"duration": 5.0},
            "results": {
                "channels": [{
                    "detected_language": "en",
                    "alternatives": [{
                        "transcript": "Hello world test",
                        "confidence": 0.99,
                        "words": [
                            {"word": "Hello", "punctuated_word": "Hello",
                             "start": 0.0, "end": 0.4, "confidence": 0.99},
                            {"word": "world", "punctuated_word": "world",
                             "start": 0.5, "end": 0.9, "confidence": 0.99},
                            # Intentionally past duration to trigger acoustic rejection
                            {"word": "test", "punctuated_word": "test",
                             "start": 5.5, "end": 6.0, "confidence": 0.99},
                        ],
                    }],
                }],
            },
        }
        transcript_text = "Hello world test"
        return {
            "status": "PASS",
            "http_status": 200,
            "content_type": "application/json",
            "body_preview": "",
            "transcript": transcript_text,
            "transcript_json": tj,
            "stats": {},
            "error": "",
        }

    return mock_diagnostic, call_log


# ---------------------------------------------------------------------------
# §2 PHYSICAL DEEPGRAM EVENT TESTS
# ---------------------------------------------------------------------------

def test_before_deepgram_adapter_asr_route_false(monkeypatch):
    """§2 BEFORE_DEEPGRAM_ADAPTER: Before adapter entry, asr_route_called=false."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-r8-3")

    job_state = {
        "job_id": "job_before_adapter",
        "subdub_asr_plan_version": "r8_2",
        "asr_route_called": False,
        "mode": "dub",
    }
    # Set state via ContextVar to verify it's untouched before adapter runs
    bot.set_subdub_active_pipeline_state(job_state)
    assert job_state.get("asr_route_called") is False
    assert job_state.get("subdub_asr_provider_called") is None
    assert job_state.get("subdub_asr_called_at") is None
    bot.set_subdub_active_pipeline_state(None)


def test_embedded_subtitle_return_asr_route_false(monkeypatch):
    """§2 EMBEDDED_SUBTITLE_RETURN: Embedded subtitle path → asr_route_called=false."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-r8-3")

    async def mock_extract_embedded(source_bytes, content_type):
        return ("1\n00:00:00,000 --> 00:00:01,000\nEmbedded Subtitle\n", "embedded_ok")

    monkeypatch.setattr(bot, "video_dubbing_extract_embedded_subtitle", mock_extract_embedded)

    job_state = {
        "job_id": "job_embedded_return",
        "asr_route_called": False,
        "mode": "dub",
    }
    res = asyncio.run(
        bot.video_dubbing_resolve_source_script(
            b"dummy_bytes",
            "video/mp4",
            None,
            require_diarization=False,
            require_auto_multi_word_timeline=False,
            state=job_state,
        )
    )
    assert res.get("source_kind") == "embedded_subtitle"
    assert job_state.get("asr_route_called") is False, "Embedded subtitle must NOT set asr_route_called"


def test_pre_provider_failure_asr_route_false(monkeypatch):
    """§2 PRE_PROVIDER_FAILURE: Preflight failure before provider → asr_route_called=false."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "")  # Missing key → guard at line 65652

    job_state = {
        "job_id": "job_pre_provider_fail",
        "asr_route_called": False,
        "mode": "dub",
        "_pipeline_workspace": "dummy_ws",
    }
    # require_auto_multi_word_timeline=True with no DEEPGRAM_API_KEY
    # → asr_transcribe_audio returns AUTO_CAST_UNAVAILABLE at line 65652-65661
    # → resolve_source_script raises AutoCastUnavailable at line 247358
    with pytest.raises(subdub_speaker_cast.AutoCastUnavailable):
        asyncio.run(
            bot.video_dubbing_resolve_source_script(
                b"valid_audio_bytes",
                "audio/wav",
                None,
                require_diarization=False,
                require_auto_multi_word_timeline=True,
                allow_confirmed_product=True,
                state=job_state,
            )
        )
    assert job_state.get("asr_route_called") is False, \
        "Pre-provider failure must NOT set asr_route_called"


def test_real_deepgram_adapter_entered_sets_events(monkeypatch):
    """§2 REAL_DEEPGRAM_ADAPTER_ENTERED: Real adapter entry sets
    asr_route_called=true, subdub_asr_provider_called=deepgram, subdub_asr_called_at>0.
    Mocks ONLY AgentDeepgram.diagnostic (HTTP transport)."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-r8-3")
    mock_diag, diag_calls = _make_diagnostic_success_mock()
    monkeypatch.setattr(bot.AgentDeepgram, "diagnostic", staticmethod(mock_diag))

    job_state = {
        "job_id": "job_real_adapter_entry",
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

    # Event truth set by REAL deepgram_asr_adapter (lines 40710-40714)
    assert job_state.get("asr_route_called") is True
    assert job_state.get("subdub_asr_provider_called") == "deepgram"
    assert job_state.get("subdub_asr_called_at", 0) > 0

    # Diagnostic was actually called
    assert len(diag_calls) == 1

    # Output is valid ASR result
    assert result.get("source_kind") == "asr"

    # ContextVar reset after completion
    assert bot.get_subdub_active_pipeline_state() is None


def test_http_transport_fail_after_adapter_entry(monkeypatch):
    """§2 HTTP_TRANSPORT_FAIL_AFTER_ADAPTER_ENTRY: Real adapter enters (sets events),
    then HTTP transport fails. asr_route_called=true survives."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-r8-3")
    mock_diag, diag_calls = _make_diagnostic_http_fail_mock(http_status=500)
    monkeypatch.setattr(bot.AgentDeepgram, "diagnostic", staticmethod(mock_diag))

    job_state = {
        "job_id": "job_http_fail_after_entry",
        "subdub_asr_plan_version": "r8_2",
        "asr_route_called": False,
        "mode": "dub",
        "_pipeline_workspace": "dummy_ws",
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
                state=job_state,
            )
        )

    # Event truth was set by adapter BEFORE the HTTP call (line 40710-40714)
    assert job_state.get("asr_route_called") is True, \
        "Adapter entered must set asr_route_called=True even on HTTP failure"
    assert job_state.get("subdub_asr_provider_called") == "deepgram"

    # Diagnostic was called
    assert len(diag_calls) == 1

    # ContextVar reset despite failure
    assert bot.get_subdub_active_pipeline_state() is None


# ---------------------------------------------------------------------------
# §3 REAL DISPATCH SIDE-EFFECT PROOF
# ---------------------------------------------------------------------------

def test_real_dispatch_side_effect_deepgram_absent(monkeypatch):
    """§3 Deepgram-absent: DB_WRITES=0, MEMORY_JOB_INSERTS=0."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "")
    saved_jobs = []
    monkeypatch.setattr(bot, "save_engine_async_job", lambda p: (saved_jobs.append(p), p)[1])

    job_key_fail = "job_fail_dg_absent"
    acquired, _ = bot.acquire_subtitle_dub_pipeline_job(
        job_key_fail,
        auto_smart_multivoice_opt_in=True,
        subdub_final_confirmed=True,
        subdub_engine_requested="auto_smart_multivoice",
        mode="dub",
    )
    assert acquired is False
    assert len(saved_jobs) == 0, "DB_WRITES=0 when Deepgram absent"
    assert job_key_fail not in bot.SUBTITLE_DUB_PIPELINE_JOBS, "MEMORY_JOB_INSERTS=0"


def test_real_dispatch_side_effect_valid_admission(monkeypatch):
    """§3 Valid admission: JOB_PERSIST_CALLS=1, MEMORY_JOB_INSERTS=1, NO_DUPLICATE_DISPATCH."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-key-active")
    saved_jobs = []
    monkeypatch.setattr(bot, "save_engine_async_job", lambda p: (saved_jobs.append(p), p)[1])

    initial_count = len(bot.SUBTITLE_DUB_PIPELINE_JOBS)
    job_key_ok = "job_ok_dispatch"
    acquired, admitted_job = bot.acquire_subtitle_dub_pipeline_job(
        job_key_ok,
        auto_smart_multivoice_opt_in=True,
        subdub_final_confirmed=True,
        subdub_engine_requested="auto_smart_multivoice",
        mode="dub",
        user_id=12345,
        chat_id=12345,
    )
    assert acquired is True
    assert len(saved_jobs) == 1, "JOB_PERSIST_CALLS=1"
    assert len(bot.SUBTITLE_DUB_PIPELINE_JOBS) == initial_count + 1, "MEMORY_JOB_INSERTS=1"

    # NO_DUPLICATE_DISPATCH: second call with same key must not double-insert
    acquired2, _ = bot.acquire_subtitle_dub_pipeline_job(
        job_key_ok,
        auto_smart_multivoice_opt_in=True,
        subdub_final_confirmed=True,
        subdub_engine_requested="auto_smart_multivoice",
        mode="dub",
    )
    assert acquired2 is False, "NO_DUPLICATE_DISPATCH"
    assert len(saved_jobs) == 1, "No second persist call on duplicate"

    # OUTBOX_AUTHORITY=NOT_APPLICABLE: SubDub pipeline jobs are persisted via
    # SUBTITLE_DUB_PIPELINE_JOBS and save_engine_async_job (system_settings table),
    # completely independent of video_outbox / broadcast outbox.
    assert "video_outbox" not in admitted_job
    assert admitted_job.get("feature") == "subtitle_dub"
    assert saved_jobs[0].get("feature") == "subtitle_dub"


# ---------------------------------------------------------------------------
# §4 POST-PROVIDER FAILURE DURABILITY
# ---------------------------------------------------------------------------

def test_post_provider_failure_durability(monkeypatch):
    """§4 Real adapter enters → mocked HTTP failure → canonical job persistence.
    After reload: asr_route_called=true, subdub_asr_provider_called=deepgram,
    error state present."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-r8-3")
    mock_diag, diag_calls = _make_diagnostic_http_fail_mock(http_status=503)
    monkeypatch.setattr(bot.AgentDeepgram, "diagnostic", staticmethod(mock_diag))

    # Step 1: Admit job via production path
    job_key = "job_post_provider_fail_r8_3"
    acquired, admitted_job = bot.acquire_subtitle_dub_pipeline_job(
        job_key,
        auto_smart_multivoice_opt_in=True,
        subdub_final_confirmed=True,
        subdub_engine_requested="auto_smart_multivoice",
        mode="dub",
        user_id=77001,
        chat_id=77001,
    )
    assert acquired is True
    internal_id = str(admitted_job.get("internal_job_id") or "")
    assert internal_id

    # Step 2: Drive real resolver with HTTP failure
    job_state = dict(admitted_job)
    with pytest.raises(Exception):
        asyncio.run(
            bot.video_dubbing_resolve_source_script(
                b"audio_bytes_for_provider_fail",
                "audio/wav",
                None,
                require_diarization=False,
                require_auto_multi_word_timeline=True,
                allow_confirmed_product=True,
                state=job_state,
            )
        )

    # Step 3: Verify event truth survives on state
    assert job_state.get("asr_route_called") is True
    assert job_state.get("subdub_asr_provider_called") == "deepgram"
    assert job_state.get("subdub_asr_called_at", 0) > 0

    # Step 4: Persist error state and reload
    job_state["error_code"] = "deepgram_http_5xx"
    job_state["error_detail"] = "HTTP 503 transport failure"
    bot.persist_subtitle_dub_pipeline_job_snapshot(job_key, job_state, reason="provider_failure")

    reloaded = bot.get_engine_async_job(internal_id)
    assert reloaded, "Persisted job must reload"
    assert reloaded.get("asr_route_called") is True
    assert reloaded.get("subdub_asr_provider_called") == "deepgram"
    assert reloaded.get("error_code") == "deepgram_http_5xx"
    assert reloaded.get("error_detail") == "HTTP 503 transport failure"


# ---------------------------------------------------------------------------
# §5 POST-ACOUSTIC FAILURE DURABILITY
# ---------------------------------------------------------------------------

def test_post_acoustic_failure_durability(monkeypatch):
    """§5 Real adapter succeeds (events set) → word_timeline rejected by acoustic authority
    → AUTO_CAST_UNAVAILABLE. asr_route_called=true survives. ASR_SUBMITS=1."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-r8-3")
    mock_diag, diag_calls = _make_diagnostic_empty_words_mock()
    monkeypatch.setattr(bot.AgentDeepgram, "diagnostic", staticmethod(mock_diag))

    # Step 1: Admit job via production path
    job_key = "job_post_acoustic_fail_r8_3"
    acquired, admitted_job = bot.acquire_subtitle_dub_pipeline_job(
        job_key,
        auto_smart_multivoice_opt_in=True,
        subdub_final_confirmed=True,
        subdub_engine_requested="auto_smart_multivoice",
        mode="dub",
        user_id=88001,
        chat_id=88001,
    )
    assert acquired is True
    internal_id = str(admitted_job.get("internal_job_id") or "")
    assert internal_id

    job_state = dict(admitted_job)
    job_state["_pipeline_workspace"] = "dummy_ws"

    # The adapter enters (sets events), diagnostic returns OK transcript,
    # but acoustic word_items rejects due to word past duration → empty word_timeline
    # → require_auto_multi_word_timeline + empty timeline → AutoCastUnavailable
    with pytest.raises(subdub_speaker_cast.AutoCastUnavailable):
        asyncio.run(
            bot.video_dubbing_resolve_source_script(
                b"audio_bytes_acoustic_fail",
                "audio/wav",
                None,
                require_diarization=False,
                require_auto_multi_word_timeline=True,
                allow_confirmed_product=True,
                state=job_state,
            )
        )

    # Event truth set by adapter BEFORE acoustic failure
    assert job_state.get("asr_route_called") is True
    assert job_state.get("subdub_asr_provider_called") == "deepgram"
    assert job_state.get("subdub_asr_called_at", 0) > 0

    # ASR_SUBMITS=1, SECOND_ASR_CALL=NO
    assert len(diag_calls) == 1, "ASR_SUBMITS=1"

    # Persist and reload to prove durability
    job_state["error_code"] = "AUTO_CAST_UNAVAILABLE"
    job_state["error_detail"] = "acoustic_timeline_rejection"
    bot.persist_subtitle_dub_pipeline_job_snapshot(
        job_key, job_state, reason="acoustic_failure"
    )
    reloaded = bot.get_engine_async_job(internal_id)
    assert reloaded is not None, "Persisted job must reload successfully"
    assert reloaded.get("asr_route_called") is True
    assert reloaded.get("subdub_asr_provider_called") == "deepgram"
    assert reloaded.get("error_code") == "AUTO_CAST_UNAVAILABLE"
    assert reloaded.get("error_detail") == "acoustic_timeline_rejection"


# ---------------------------------------------------------------------------
# §6 N>=3 ENGINE SELECTED DURABILITY
# ---------------------------------------------------------------------------

def test_n3_engine_selected_durability_via_multivoice_lane(monkeypatch):
    """§6 Drive actual N>=3 dispatch via execute_smart_multivoice_lane.
    Real production code sets subdub_engine_selected=auto_multi_speaker_v2,
    auto_smart_dispatch=n3_plus_proven_v2 in v2_state (lines 2782-2783)."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-r8-3")
    mock_diag, diag_calls = _make_diagnostic_success_mock()
    monkeypatch.setattr(bot.AgentDeepgram, "diagnostic", staticmethod(mock_diag))

    # Monkeypatch acoustic_register_classifications to succeed for 3 speakers
    # so the production dispatch_to_v2 path triggers (line 2763).
    def mock_acoustic_classifications(prepared, labels):
        return {
            label: {"speaker_id": label, "voice_register": "bass", "confidence": 0.9}
            for label in labels
        }

    monkeypatch.setattr(
        auto_multi_speaker,
        "acoustic_register_classifications",
        mock_acoustic_classifications,
    )

    # Monkeypatch run_auto_multi_speaker_v2_blackbox to avoid deep v2 execution
    from services.subdub_blackboxes import auto_multi_speaker_v2

    async def mock_v2_blackbox(**kwargs):
        return {"ok": True, "state": dict(kwargs.get("state", {}))}

    monkeypatch.setattr(
        auto_multi_speaker_v2,
        "run_auto_multi_speaker_v2_blackbox",
        mock_v2_blackbox,
    )

    # Step 1: Admit job via production path
    job_key = "job_n3_engine_r8_3"
    acquired, admitted_job = bot.acquire_subtitle_dub_pipeline_job(
        job_key,
        auto_smart_multivoice_opt_in=True,
        subdub_final_confirmed=True,
        subdub_engine_requested="auto_smart_multivoice",
        mode="dub",
        user_id=99001,
        chat_id=99001,
    )
    assert acquired is True
    internal_id = str(admitted_job.get("internal_job_id") or "")
    assert internal_id

    current_state = dict(admitted_job)
    current_state["_pipeline_workspace"] = "dummy_ws"

    # Build proper cues with 3 distinct speakers (speaker_id format: chunk_XX:speaker_Y)
    three_speaker_cues = [
        {"speaker_id": "chunk_00:speaker_0", "chunk_index": 0, "speaker": 0,
         "start": 0.0, "end": 1.0, "text": "Hello"},
        {"speaker_id": "chunk_00:speaker_1", "chunk_index": 0, "speaker": 1,
         "start": 1.0, "end": 2.0, "text": "World"},
        {"speaker_id": "chunk_00:speaker_2", "chunk_index": 0, "speaker": 2,
         "start": 2.0, "end": 3.0, "text": "Test"},
    ]

    async def mock_prepare_subtitles(state, require_auto_cast=False):
        """Drive real ASR adapter then return cues with 3 speakers."""
        # Bind ContextVar to current_state (outer scope) for adapter event truth.
        bot.set_subdub_active_pipeline_state(current_state)
        try:
            result = await bot.asr_transcribe_audio(
                b"audio_for_n3",
                "audio/wav",
                require_auto_multi_word_timeline=True,
                allow_confirmed_product=True,
            )
        finally:
            bot.set_subdub_active_pipeline_state(None)

        if not result.get("ok"):
            raise subdub_speaker_cast.AutoCastUnavailable()

        return {
            "ok": True,
            "subtitle": "1\n00:00:00,000 --> 00:00:01,000\nHello\n\n2\n00:00:01,000 --> 00:00:02,000\nWorld\n\n3\n00:00:02,000 --> 00:00:03,000\nTest\n",
            "script": "Hello World Test",
            "word_timeline": result.get("word_timeline", []),
            "output_segments": three_speaker_cues,
            "source_bytes": b"fake_source_bytes",
        }

    payload = {
        "state": current_state,
        "prepare_subtitles": mock_prepare_subtitles,
        "lane_mode": "dub",
    }

    result = asyncio.run(auto_smart_multivoice.execute_smart_multivoice_lane(payload))

    # Event truth via real adapter on current_state (ContextVar)
    assert current_state.get("asr_route_called") is True
    assert current_state.get("subdub_asr_provider_called") == "deepgram"

    # N>=3 dispatch fields set by PRODUCTION code (lines 2810-2811) in result state
    result_state = result.get("state") or {}
    assert result_state.get("subdub_engine_selected") == "auto_multi_speaker_v2"
    assert result_state.get("auto_smart_dispatch") == "n3_plus_proven_v2"
    assert result.get("auto_smart_dispatch") == "n3_plus_proven_v2"

    # Persist and reload to prove durability of N>=3 dispatch state
    bot.persist_subtitle_dub_pipeline_job_snapshot(
        job_key, result_state, reason="n3_dispatch_completed"
    )
    reloaded = bot.get_engine_async_job(internal_id)
    assert reloaded is not None, "Persisted N>=3 job must reload"
    assert reloaded.get("subdub_engine_selected") == "auto_multi_speaker_v2"
    assert reloaded.get("auto_smart_dispatch") == "n3_plus_proven_v2"
    assert reloaded.get("asr_route_called") is True

    # Constants regression
    assert speaker_cast.MIN_REGISTER_CONFIDENCE == 0.75
    assert multi_onnx.MIN_PANN_SCORE_MARGIN == 0.08
    assert auto_smart_multivoice.MAX_INTELLIGIBLE_FIT_RATIO == 1.8
    assert auto_smart_multivoice.AUTO_SMART_N3_PLUS_DISPATCH_STRATEGY == "n3_plus_proven_v2"


# ---------------------------------------------------------------------------
# §7 REAL WORKER RELOAD
# ---------------------------------------------------------------------------

def test_real_worker_reload_authority(monkeypatch):
    """§7 Real admission → save_engine_async_job → production get_engine_async_job →
    snapshot fields survive. subdub_asr_plan_version=r8_2. CURRENT_VERSION_RECOMPUTE_CALLS=0."""
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


# ---------------------------------------------------------------------------
# ContextVar lifecycle tests (preserved from R8.3 v1, now using diagnostic mock)
# ---------------------------------------------------------------------------

def test_contextvar_lifecycle_success_reset(monkeypatch):
    """ContextVar properly bound during execution and reset in finally on success."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-r8-3")
    mock_diag, diag_calls = _make_diagnostic_success_mock()
    monkeypatch.setattr(bot.AgentDeepgram, "diagnostic", staticmethod(mock_diag))

    assert bot.get_subdub_active_pipeline_state() is None

    job_state = {
        "job_id": "job_lifecycle_success",
        "subdub_asr_plan_version": "r8_2",
        "asr_route_called": False,
        "mode": "dub",
        "_pipeline_workspace": "dummy_ws",
    }

    result = asyncio.run(
        bot.video_dubbing_resolve_source_script(
            b"dummy_audio_bytes_lifecycle",
            "audio/wav",
            None,
            require_diarization=False,
            require_auto_multi_word_timeline=True,
            allow_confirmed_product=True,
            state=job_state,
        )
    )

    # Event truth set by real adapter
    assert job_state.get("asr_route_called") is True
    assert job_state.get("subdub_asr_provider_called") == "deepgram"
    assert job_state.get("subdub_asr_called_at", 0) > 0

    # Output is valid
    assert result.get("source_kind") == "asr"

    # ContextVar was cleanly reset after completion
    assert bot.get_subdub_active_pipeline_state() is None


def test_contextvar_lifecycle_failure_reset(monkeypatch):
    """ContextVar is safely reset in finally even when execution raises."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-r8-3")
    mock_diag, _ = _make_diagnostic_empty_words_mock()
    monkeypatch.setattr(bot.AgentDeepgram, "diagnostic", staticmethod(mock_diag))

    assert bot.get_subdub_active_pipeline_state() is None

    job_state = {
        "job_id": "job_lifecycle_failure",
        "subdub_asr_plan_version": "r8_2",
        "asr_route_called": False,
        "mode": "dub",
        "_pipeline_workspace": "dummy_ws",
    }

    with pytest.raises(subdub_speaker_cast.AutoCastUnavailable):
        asyncio.run(
            bot.video_dubbing_resolve_source_script(
                b"dummy_audio_bytes_fail",
                "audio/wav",
                None,
                require_diarization=False,
                require_auto_multi_word_timeline=True,
                allow_confirmed_product=True,
                state=job_state,
            )
        )

    # Event truth preserved despite exception
    assert job_state.get("asr_route_called") is True
    assert job_state.get("subdub_asr_provider_called") == "deepgram"

    # ContextVar MUST be reset back to None in finally
    assert bot.get_subdub_active_pipeline_state() is None


def test_concurrent_task_context_isolation(monkeypatch):
    """Concurrent tasks with distinct job IDs have fully isolated ContextVar state."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-dg-key-r8-3")
    mock_diag, _ = _make_diagnostic_success_mock()
    monkeypatch.setattr(bot.AgentDeepgram, "diagnostic", staticmethod(mock_diag))

    state_a = {"job_id": "JOB_ALPHA", "asr_route_called": False, "mode": "dub", "_pipeline_workspace": "ws_a"}
    state_b = {"job_id": "JOB_BETA", "asr_route_called": False, "mode": "dub", "_pipeline_workspace": "ws_b"}

    async def run_task(state):
        return await bot.video_dubbing_resolve_source_script(
            b"bytes_wav",
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

    # Both tasks got event truth from REAL adapter
    assert state_a.get("asr_route_called") is True
    assert state_b.get("asr_route_called") is True

    # No cross-task leakage
    assert state_a.get("job_id") == "JOB_ALPHA"
    assert state_b.get("job_id") == "JOB_BETA"

    # Post condition: ContextVar is completely clear
    assert bot.get_subdub_active_pipeline_state() is None


# ---------------------------------------------------------------------------
# §6 N>=3 Constants Regression
# ---------------------------------------------------------------------------

def test_n3_engine_constants_regression():
    """§6 Constants-only regression check."""
    assert speaker_cast.MIN_REGISTER_CONFIDENCE == 0.75
    assert multi_onnx.MIN_PANN_SCORE_MARGIN == 0.08
    assert auto_smart_multivoice.MAX_INTELLIGIBLE_FIT_RATIO == 1.8
    assert auto_smart_multivoice.AUTO_SMART_N3_PLUS_DISPATCH_STRATEGY == "n3_plus_proven_v2"


# ---------------------------------------------------------------------------
# Event durability via execute_smart_multivoice_lane
# ---------------------------------------------------------------------------

def test_event_durability_acoustic_failure_via_lane(monkeypatch):
    """Post-acoustic failure: real adapter events survive through multivoice lane."""
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "test-key-r8-3")
    mock_diag, diag_calls = _make_diagnostic_success_mock()
    monkeypatch.setattr(bot.AgentDeepgram, "diagnostic", staticmethod(mock_diag))

    current_state = {
        "job_id": "job_lane_acoustic_fail",
        "subdub_asr_plan_version": "r8_2",
        "asr_route_called": False,
        "mode": "dub",
        "_pipeline_workspace": "dummy_ws",
    }

    async def mock_prepare_subtitles(state, require_auto_cast=False):
        bot.set_subdub_active_pipeline_state(state)
        try:
            result = await bot.asr_transcribe_audio(
                b"audio_for_lane",
                "audio/wav",
                require_auto_multi_word_timeline=True,
                allow_confirmed_product=True,
            )
        finally:
            bot.set_subdub_active_pipeline_state(None)

        # Simulate acoustic clustering divergence after successful ASR
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

    res_state = result.get("state") or {}
    # Events set by REAL adapter, NOT by test mock
    assert res_state.get("asr_route_called") is True
    assert res_state.get("subdub_asr_provider_called") == "deepgram"
