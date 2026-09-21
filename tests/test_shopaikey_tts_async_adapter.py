from __future__ import annotations

import json
from unittest.mock import MagicMock
import pytest
import httpx

from services import shopaikey_tts_async_adapter as async_adapter
from services import subdub_tts_checkpoint


def test_build_shopaikey_async_payload():
    payload = async_adapter.build_shopaikey_async_payload(
        text="Hola.",
        voice_id="Vietnamese_patient_Instructor_v1",
        model="speech-02-hd",
        speed=1.0,
        tts_language_boost="auto",
    )
    assert payload["model"] == "speech-02-hd"
    assert payload["text"] == "Hola."
    assert payload["voice_setting"]["voice_id"] == "Vietnamese_patient_Instructor_v1"
    assert payload["audio_setting"]["format"] == "mp3"
    assert payload["language_boost"] == "auto"


def test_parse_shopaikey_task_id():
    assert async_adapter.parse_shopaikey_task_id({"task_id": "t-123"}) == "t-123"
    assert async_adapter.parse_shopaikey_task_id({"data": {"task_id": "t-456"}}) == "t-456"
    assert async_adapter.parse_shopaikey_task_id({"taskId": "t-789"}) == "t-789"
    assert async_adapter.parse_shopaikey_task_id({}) == ""
    assert async_adapter.parse_shopaikey_task_id(None) == ""


def test_parse_shopaikey_file_id_and_url():
    f_id, url = async_adapter.parse_shopaikey_file_id_and_url({"file_id": "f-1", "download_url": "https://example.com/audio.mp3"})
    assert f_id == "f-1"
    assert url == "https://example.com/audio.mp3"

    f_id2, url2 = async_adapter.parse_shopaikey_file_id_and_url({"data": {"file_id": "f-2", "download_url": "https://example.com/audio2.mp3"}})
    assert f_id2 == "f-2"
    assert url2 == "https://example.com/audio2.mp3"

    f_id3, url3 = async_adapter.parse_shopaikey_file_id_and_url({"file": {"download_url": "https://example.com/file_obj.mp3"}})
    assert f_id3 == ""
    assert url3 == "https://example.com/file_obj.mp3"


def test_parse_shopaikey_task_status():
    assert async_adapter.parse_shopaikey_task_status({"status": "Processing"}, 200) == "PROCESSING"
    assert async_adapter.parse_shopaikey_task_status({"status": "Success"}, 200) == "SUCCESS"
    assert async_adapter.parse_shopaikey_task_status({"status": "Failed"}, 200) == "FAIL"
    assert async_adapter.parse_shopaikey_task_status({}, 502) == "FAIL"


@pytest.mark.anyio
async def test_shopaikey_minimax_tts_async_submit_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "/tts/minimax/t2a_async_v2" in str(request.url)
        assert request.headers.get("authorization") == "Bearer fake_key"
        return httpx.Response(200, json={"task_id": "async_task_001", "base_resp": {"status_code": 0}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        status, task_id, detail, http_status = await async_adapter.shopaikey_minimax_tts_async_submit(
            text="Hola.",
            voice_id="Vietnamese_patient_Instructor_v1",
            api_key="fake_key",
            client=client,
        )

    assert status == "PASS"
    assert task_id == "async_task_001"
    assert http_status == 200


@pytest.mark.anyio
async def test_shopaikey_minimax_tts_async_submit_502():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text='{"error":{"code":"service_unavailable"}}')

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        status, task_id, detail, http_status = await async_adapter.shopaikey_minimax_tts_async_submit(
            text="Hola.",
            voice_id="Vietnamese_patient_Instructor_v1",
            api_key="fake_key",
            client=client,
        )

    assert status == "FAIL_HTTP_STATUS"
    assert task_id == ""
    assert http_status == 502
    assert "service_unavailable" in detail


@pytest.mark.anyio
async def test_shopaikey_minimax_tts_async_query_and_retrieve():
    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "query" in url_str:
            assert "task_id=task_999" in url_str
            return httpx.Response(200, json={"status": "Success", "file_id": "file_888"})
        if "retrieve" in url_str:
            assert "file_id=file_888" in url_str
            return httpx.Response(200, json={"file": {"download_url": "https://direct.shopaikey.com/storage/audio.mp3"}})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        q_status, identifier, q_detail, q_http = await async_adapter.shopaikey_minimax_tts_async_query(
            task_id="task_999",
            api_key="fake_key",
            client=client,
        )
        assert q_status == "SUCCESS"
        assert identifier == "file_888"

        r_status, download_url, r_detail, r_http = await async_adapter.shopaikey_minimax_tts_async_retrieve(
            file_id=identifier,
            api_key="fake_key",
            client=client,
        )
        assert r_status == "PASS"
        assert download_url == "https://direct.shopaikey.com/storage/audio.mp3"


@pytest.mark.anyio
async def test_shopaikey_minimax_tts_async_bytes_full_flow():
    query_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal query_count
        url_str = str(request.url)
        if "/t2a_async_v2" in url_str:
            return httpx.Response(200, json={"task_id": "task_full_flow"})
        if "query" in url_str:
            query_count += 1
            if query_count == 1:
                return httpx.Response(200, json={"status": "Processing"})
            return httpx.Response(200, json={"status": "Success", "file_id": "file_full_flow"})
        if "retrieve" in url_str:
            return httpx.Response(200, json={"download_url": "https://direct.shopaikey.com/dl/test.mp3"})
        return httpx.Response(404)

    async def mock_downloader(url: str):
        assert url == "https://direct.shopaikey.com/dl/test.mp3"
        return b"ID3" + b"\x00" * 200, "http=200; bytes=203", 200

    hook_calls = []

    def hook(tid: str):
        hook_calls.append(tid)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        status, audio_bytes, detail, http_status, task_id = await async_adapter.shopaikey_minimax_tts_async_bytes(
            text="Hola.",
            voice_id="Vietnamese_patient_Instructor_v1",
            poll_interval_seconds=0.01,
            max_poll_seconds=5.0,
            client=client,
            api_key="fake_key",
            on_submit_hook=hook,
            audio_downloader=mock_downloader,
        )

    assert status == "PASS"
    assert len(audio_bytes) == 203
    assert task_id == "task_full_flow"
    assert hook_calls == ["task_full_flow"]


@pytest.mark.anyio
async def test_shopaikey_minimax_tts_async_bytes_resume_skips_submit():
    submit_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submit_called
        url_str = str(request.url)
        if "/t2a_async_v2" in url_str:
            submit_called = True
            return httpx.Response(500, text="Should not be called")
        if "query" in url_str:
            return httpx.Response(200, json={"status": "Success", "download_url": "https://direct.shopaikey.com/dl/direct.mp3"})
        return httpx.Response(404)

    async def mock_downloader(url: str):
        return b"ID3" + b"\x00" * 150, "http=200", 200

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        status, audio_bytes, detail, http_status, task_id = await async_adapter.shopaikey_minimax_tts_async_bytes(
            text="Hola.",
            voice_id="Vietnamese_patient_Instructor_v1",
            existing_task_id="pre_existing_task_123",
            poll_interval_seconds=0.01,
            max_poll_seconds=5.0,
            client=client,
            audio_downloader=mock_downloader,
        )

    assert not submit_called, "Submit must NEVER be called when existing_task_id is provided"
    assert status == "PASS"
    assert task_id == "pre_existing_task_123"
    assert len(audio_bytes) == 153


def test_subdub_checkpoint_async_submitted_lifecycle(tmp_path):
    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=str(tmp_path),
        job_id="test_job",
        target_language="vi",
    )
    cue = {"cue_id": "cue-0001", "speaker_id": "spk_0", "text": "Hola."}
    voice_id = "Vietnamese_patient_Instructor_v1"

    # Step 1: Initial prepare
    reused, path, data, entry = mgr.prepare_cue_intent(cue, voice_id)
    assert not reused
    assert entry is None
    unit_key = mgr.compute_key(cue, voice_id)
    assert mgr.entries[unit_key]["state"] == subdub_tts_checkpoint.STATE_SUBMITTING

    # Step 2: Record async submitted
    mgr.record_cue_async_submitted(cue, voice_id, task_id="task_async_abc123", provider_request_id="req_999")
    assert mgr.entries[unit_key]["state"] == subdub_tts_checkpoint.STATE_ASYNC_SUBMITTED
    assert mgr.entries[unit_key]["task_id"] == "task_async_abc123"

    # Step 3: Re-instantiate manager (simulating restart during polling)
    mgr2 = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=str(tmp_path),
        job_id="test_job",
        target_language="vi",
    )
    # Does NOT raise SubdubTTSAmbiguousSubmissionError!
    reused2, path2, data2, entry2 = mgr2.prepare_cue_intent(cue, voice_id)
    assert not reused2
    assert entry2 is not None
    assert entry2.get("state") == subdub_tts_checkpoint.STATE_ASYNC_SUBMITTED
    assert entry2.get("task_id") == "task_async_abc123"
