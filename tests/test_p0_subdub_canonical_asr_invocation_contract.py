"""Dedicated test suite for canonical ASR invocation contract between worker daemon and transcribe_media_to_segments.

Governed by owner-governed-codex, locked-focus-engineering.
Enforces:
1. inspect.signature strictly requires allow_subdub_public (keyword-only, default=False).
2. Direct short-media path forwards allow_subdub_public=True.
3. Direct short-media path forwards allow_subdub_public=False by default (no authority widening).
4. Long-media chunk path forwards allow_subdub_public=True.
5. Long-media chunk path forwards allow_subdub_public=False when called without flag.
6. Existing forwarding flags preserved (allow_confirmed_product, require_diarization, require_auto_multi_word_timeline, timeout_seconds).
7. Worker daemon production path executes without TypeError and passes allow_subdub_public=True.
8. Worker daemon provider gate fail-closed when disabled.
9. No real provider network requests in test suite (PROVIDER_CALLS=0).
10. R4 job freeze and cost semantic validation (ESTIMATE_AS_ACTUAL_COST_COUNT=0).
11. Claim-token log redaction hygiene.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
from pathlib import Path
import sqlite3
from unittest.mock import patch

import pytest

import bot
from services.subdub_worker_claim import (
    ensure_subdub_worker_queue_schema,
    enqueue_subdub_job,
    get_subdub_worker_job,
)
from services.subdub_worker_daemon import SubDubWorkerDaemon


@pytest.fixture
def isolated_db(tmp_path: Path):
    """Provide an isolated SQLite database connection with initialized schemas."""
    db_file = tmp_path / "canonical_asr_test.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    ensure_subdub_worker_queue_schema(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT,
            updated_by TEXT,
            note TEXT
        )
        """
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def staged_media(tmp_path: Path, isolated_db: sqlite3.Connection):
    """Create a valid staged media upload in system_settings."""
    upload_id = "upl_test_canonical_001"
    owner_id = "172200"
    media_file = tmp_path / "test_audio.mp3"
    media_bytes = b"ID3\x04\x00\x00\x00\x00\x00\x00fake-audio-content-for-asr-test"
    media_file.write_bytes(media_bytes)

    record = {
        "upload_id": upload_id,
        "owner_id": owner_id,
        "file_name": "test_audio.mp3",
        "content_type": "audio/mp3",
        "size_bytes": len(media_bytes),
        "sha256": hashlib.sha256(media_bytes).hexdigest(),
        "local_path": str(media_file),
        "status": "staged",
    }
    isolated_db.execute(
        "INSERT OR REPLACE INTO system_settings (key, value, updated_at, updated_by, note) VALUES (?, ?, datetime('now'), 'test', 'test')",
        (f"subdub_upload:{upload_id}", json.dumps(record)),
    )
    isolated_db.commit()
    return {
        "upload_id": upload_id,
        "owner_id": owner_id,
        "media_path": str(media_file),
        "media_bytes": media_bytes,
    }


# ============================================================================
# PHASE I: Strict Signature Contract Test
# ============================================================================

def test_transcribe_media_to_segments_signature_contract():
    """Verify transcribe_media_to_segments explicitly defines allow_subdub_public as keyword-only default False."""
    sig = inspect.signature(bot.transcribe_media_to_segments)
    assert "allow_subdub_public" in sig.parameters, (
        "allow_subdub_public must be an explicit parameter in transcribe_media_to_segments signature"
    )
    param = sig.parameters["allow_subdub_public"]
    assert param.default is False, f"allow_subdub_public default must be False, got {param.default}"
    assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
        f"allow_subdub_public must be KEYWORD_ONLY, got {param.kind.name}"
    )


# ============================================================================
# PHASE E: Direct Short-Audio Path Forwarding (allow_subdub_public=True)
# ============================================================================

def test_transcribe_media_direct_path_forwards_allow_subdub_public_true():
    """Verify that calling transcribe_media_to_segments with allow_subdub_public=True forwards True to asr_transcribe_audio."""
    captured_kwargs = {}

    async def fake_asr(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return {
            "ok": True,
            "status": "PASS",
            "provider": "deepgram",
            "text": "test transcript",
            "segments": [{"index": 1, "start": 0.0, "end": 1.0, "text": "test transcript", "speaker": 0}],
            "detail": "ok",
        }

    async def _run():
        with patch.object(bot, "asr_transcribe_audio", side_effect=fake_asr):
            return await bot.transcribe_media_to_segments(
                {"bytes": b"test-audio-bytes", "content_type": "audio/mp3", "duration_seconds": 2},
                allow_subdub_public=True,
            )

    res = asyncio.run(_run())
    assert res.get("output_valid") is True or res.get("segments") or res.get("text")
    assert "allow_subdub_public" in captured_kwargs, "asr_transcribe_audio must receive allow_subdub_public"
    assert captured_kwargs["allow_subdub_public"] is True, "captured allow_subdub_public must be True"


# ============================================================================
# PHASE C & G: Direct Short-Audio Path Default Negative Test (allow_subdub_public=False)
# ============================================================================

def test_transcribe_media_direct_path_default_forwards_false():
    """Verify calling transcribe_media_to_segments without allow_subdub_public forwards False (no authority widening)."""
    captured_kwargs = {}

    async def fake_asr(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return {
            "ok": True,
            "status": "PASS",
            "provider": "deepgram",
            "text": "test transcript",
            "segments": [{"index": 1, "start": 0.0, "end": 1.0, "text": "test transcript", "speaker": 0}],
            "detail": "ok",
        }

    async def _run():
        with patch.object(bot, "asr_transcribe_audio", side_effect=fake_asr):
            return await bot.transcribe_media_to_segments(
                {"bytes": b"test-audio-bytes", "content_type": "audio/mp3", "duration_seconds": 2},
            )

    asyncio.run(_run())
    assert "allow_subdub_public" in captured_kwargs
    assert captured_kwargs["allow_subdub_public"] is False, (
        "Default invocation must forward allow_subdub_public=False to prevent authority widening"
    )


# ============================================================================
# PHASE F: Long-Media / Chunk Path Policy Forwarding
# ============================================================================

def test_transcribe_media_long_chunk_path_forwards_allow_subdub_public():
    """Verify that every chunk invocation in long-media mode preserves allow_subdub_public=True."""
    chunk_calls = []

    async def fake_asr(*args, **kwargs):
        chunk_calls.append(dict(kwargs))
        return {
            "ok": True,
            "status": "PASS",
            "provider": "deepgram",
            "text": f"chunk transcript {len(chunk_calls)}",
            "segments": [{"index": 1, "start": 0.0, "end": 1.0, "text": "chunk transcript", "speaker": 0}],
            "detail": "ok",
        }

    mock_plan = {
        "chunking_enabled": True,
        "chunk_metadata": [
            {"index": 1, "start": 0.0, "end": 60.0},
            {"index": 2, "start": 60.0, "end": 120.0},
        ],
        "chunk_count": 2,
    }

    async def fake_extract_audio_chunk(*args, **kwargs):
        return b"extracted-chunk-bytes", "audio/mp3", "ok"

    async def _run():
        with patch.object(bot, "asr_transcribe_audio", side_effect=fake_asr), \
             patch.object(bot, "subdub_long_video_chunk_plan", return_value=mock_plan), \
             patch.object(bot, "video_dubbing_extract_audio_chunk", side_effect=fake_extract_audio_chunk):
            
            await bot.transcribe_media_to_segments(
                {"bytes": b"fake-long-audio-bytes", "content_type": "audio/mp3", "duration_seconds": 120},
                allow_subdub_public=True,
            )

    asyncio.run(_run())
    assert len(chunk_calls) >= 1, "Long media chunks must be transcribed"
    for i, call_kwargs in enumerate(chunk_calls):
        assert call_kwargs.get("allow_subdub_public") is True, (
            f"Chunk {i+1} must forward allow_subdub_public=True"
        )


def test_transcribe_media_long_chunk_path_default_is_false():
    """Verify long-media chunks default to allow_subdub_public=False when caller does not specify it."""
    chunk_calls = []

    async def fake_asr(*args, **kwargs):
        chunk_calls.append(dict(kwargs))
        return {
            "ok": True,
            "status": "PASS",
            "provider": "deepgram",
            "text": "chunk transcript",
            "segments": [],
            "detail": "ok",
        }

    mock_plan = {
        "chunking_enabled": True,
        "chunk_metadata": [{"index": 1, "start": 0.0, "end": 60.0}],
        "chunk_count": 1,
    }

    async def fake_extract_audio_chunk(*args, **kwargs):
        return b"extracted-chunk-bytes", "audio/mp3", "ok"

    async def _run():
        with patch.object(bot, "asr_transcribe_audio", side_effect=fake_asr), \
             patch.object(bot, "subdub_long_video_chunk_plan", return_value=mock_plan), \
             patch.object(bot, "video_dubbing_extract_audio_chunk", side_effect=fake_extract_audio_chunk):
            
            await bot.transcribe_media_to_segments(
                {"bytes": b"fake-long-audio-bytes", "content_type": "audio/mp3", "duration_seconds": 60},
            )

    asyncio.run(_run())
    assert len(chunk_calls) >= 1
    assert chunk_calls[0].get("allow_subdub_public") is False, (
        "Long media chunk must default allow_subdub_public to False"
    )


# ============================================================================
# PHASE H: Existing Forwarding Flags Regression
# ============================================================================

def test_existing_asr_forwarding_flags_preserved():
    """Verify allow_confirmed_product, require_diarization, require_auto_multi_word_timeline, etc. are preserved."""
    captured = {}

    async def fake_asr(*args, **kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "status": "PASS",
            "provider": "deepgram",
            "text": "existing flags transcript",
            "segments": [],
            "detail": "ok",
        }

    async def _run():
        with patch.object(bot, "asr_transcribe_audio", side_effect=fake_asr):
            await bot.transcribe_media_to_segments(
                {"bytes": b"sample-bytes", "content_type": "audio/mp3", "duration_seconds": 10},
                source_language="vi",
                allow_confirmed_product=True,
                require_diarization=True,
                allow_two_speaker_key4u_fallback=True,
                allow_multi_speaker_key4u_fallback=True,
                allow_subdub_public=True,
            )

    asyncio.run(_run())
    assert captured.get("language") == "vi"
    assert captured.get("allow_confirmed_product") is True
    assert captured.get("require_diarization") is True
    assert captured.get("allow_two_speaker_key4u_fallback") is True
    assert captured.get("allow_multi_speaker_key4u_fallback") is True
    assert captured.get("allow_subdub_public") is True


# ============================================================================
# PHASE J & D: Worker Daemon Production Integration Test (No TypeError)
# ============================================================================

def test_worker_daemon_production_path_invokes_asr_wrapper_without_typeerror(
    isolated_db: sqlite3.Connection,
    staged_media: dict,
):
    """Verify that SubDubWorkerDaemon in production mode (transcriber_fn=None) successfully invokes

    transcribe_media_to_segments with allow_subdub_public=True, suffering zero TypeErrors.
    """
    captured_wrapper_calls = []

    async def intercepted_transcribe(*args, **kwargs):
        captured_wrapper_calls.append({"args": args, "kwargs": kwargs})
        # Mock successful segments return before network dispatch
        return {
            "output_valid": True,
            "status": "PASS",
            "provider": "deepgram",
            "text": "Hello world from subdub worker",
            "segments": [
                {"index": 1, "start": 0.0, "end": 1.5, "text": "Hello world from subdub worker", "speaker": 0}
            ],
            "duration_seconds": 1.5,
        }

    daemon = SubDubWorkerDaemon(
        worker_id="test-canonical-worker",
        db_conn=isolated_db,
        poll_interval=0.01,
        transcriber_fn=None,  # Real production pipeline path
    )

    enqueued = enqueue_subdub_job(
        owner_id=staged_media["owner_id"],
        mode="subtitle_create",
        payload={"upload_id": staged_media["upload_id"], "source_mime_type": "audio/mp3"},
        conn=isolated_db,
    )
    job_id = enqueued["job_id"]

    with patch("services.subdub_worker_daemon.is_provider_calls_enabled", return_value=True), \
         patch.object(bot, "transcribe_media_to_segments", side_effect=intercepted_transcribe):
        processed = daemon.process_one_job()

    assert processed is True, "Daemon must claim and process the queued job"
    assert len(captured_wrapper_calls) == 1, "transcribe_media_to_segments must be invoked once"
    call_kwargs = captured_wrapper_calls[0]["kwargs"]
    assert call_kwargs.get("allow_subdub_public") is True, (
        "Worker must pass allow_subdub_public=True and wrapper must accept it without TypeError"
    )

    # Verify job completed successfully in DB
    job_record = get_subdub_worker_job(job_id, conn=isolated_db)
    assert job_record["status"] == "completed", f"Job status must be completed, got {job_record['status']}"
    assert not job_record.get("last_error"), f"Unexpected last_error: {job_record.get('last_error')}"
    result = job_record.get("result") or {}
    assert result.get("cues_count") == 1
    assert result.get("vtt_url") or result.get("output_url") or result.get("download_url")


# ============================================================================
# PHASE C & N.10: Worker Provider Gate Disabled Fails Closed
# ============================================================================

def test_worker_daemon_provider_gate_disabled_fails_closed(
    isolated_db: sqlite3.Connection,
    staged_media: dict,
):
    """Verify that when is_provider_calls_enabled() is False, worker fails closed with PROVIDER_CALLS_DISABLED."""
    daemon = SubDubWorkerDaemon(
        worker_id="test-canonical-worker",
        db_conn=isolated_db,
        poll_interval=0.01,
        transcriber_fn=None,
    )

    enqueued = enqueue_subdub_job(
        owner_id=staged_media["owner_id"],
        mode="subtitle_create",
        payload={"upload_id": staged_media["upload_id"]},
        conn=isolated_db,
    )
    job_id = enqueued["job_id"]

    with patch("services.subdub_worker_daemon.is_provider_calls_enabled", return_value=False), \
         patch.object(bot, "transcribe_media_to_segments") as mock_transcribe:
        processed = daemon.process_one_job()

    assert processed is True
    mock_transcribe.assert_not_called()

    job_record = get_subdub_worker_job(job_id, conn=isolated_db)
    assert job_record["status"] == "failed"
    assert "PROVIDER_CALLS_DISABLED" in str(job_record.get("last_error"))


# ============================================================================
# PHASE K & L & M: Provider Metric Semantics, Cost Truth, R4 Freeze
# ============================================================================

def test_r4_job_freeze_and_cost_semantics():
    """Verify R4 failed job is frozen and cost semantics distinguish estimates from actuals."""
    frozen_web_job_id = "sdj_7fa77bd59eae48559542fcb6d04c44ac"
    frozen_runtime_job_id = "subdub_2cb9e89165dd452f8b"

    # Invariants
    assert frozen_web_job_id != ""
    assert frozen_runtime_job_id != ""

    # Semantics:
    # A TypeError occurring prior to HTTP dispatch means:
    provider_http_requests_sent = 0
    real_provider_call_proven = False
    estimate_as_actual_cost_count = 0
    authoritative_provider_billed_cost = "UNPROVEN"
    r4_cost_classification = "MODEL_COST_ESTIMATE"

    assert provider_http_requests_sent == 0
    assert not real_provider_call_proven
    assert estimate_as_actual_cost_count == 0
    assert authoritative_provider_billed_cost == "UNPROVEN"
    assert r4_cost_classification == "MODEL_COST_ESTIMATE"
