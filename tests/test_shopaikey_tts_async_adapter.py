from __future__ import annotations

import base64
import io
import json
import os
import tarfile
from unittest.mock import MagicMock
import pytest
import httpx

from services import shopaikey_tts_async_adapter as async_adapter
from services import subdub_tts_checkpoint
from services import subdub_tts_artifact_validator

# Deterministic 358-byte valid MP3 from repository fixture (duration ~0.0783s, 44.1kHz mono, LAME encoder)
SAMPLE_VALID_MP3 = base64.b64decode(
    "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjYyLjEyLjEwMQAAAAAAAAAAAAAA//sQxAAABHQTVVSQgDCmCa83GiACAAGtOUAAAVk6PVBQCAYJAfB8HwfKAgCAYRB8H9QIOxOH+INwBJP2wGA4HA4AAAAAACiJKpkUZAjpAkgWo/eFAfATG/AilC+oGhL8JA0qCgAYMAD/+xLEAoPFWB0gHeAAKKSDpIK8AAXMCQC8QASGAOB4Z+72pmMDlmHEESYMAH5gQgYGBSBMYF4DxZq0lflI8wEwETAAA2MDYIQzblDTLrF3ML8H0wWQHTALAtMCUB8wIwG0T59JA5JIAAr/+xDEAoAEtENSuZKAEJcGpuuYMARhEdKhTBbpmtFc+iKq+RLMu79/N5ZP4GFfx4sXwMd+FVAMXYXAAAAmEoRic8ySQagdXkkSQpUtPJRJFBQFYxhTvEt0qC3EqkxBTUUzLjEwMKqqqg=="
)


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
        return SAMPLE_VALID_MP3, f"http=200; bytes={len(SAMPLE_VALID_MP3)}", 200

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
    assert len(audio_bytes) == len(SAMPLE_VALID_MP3)
    assert audio_bytes == SAMPLE_VALID_MP3
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
        return SAMPLE_VALID_MP3, "http=200", 200

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
    assert len(audio_bytes) == len(SAMPLE_VALID_MP3)
    assert audio_bytes == SAMPLE_VALID_MP3


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


def make_test_tar(
    members: dict[str, bytes],
    *,
    symlinks: dict[str, str] | None = None,
    hardlinks: dict[str, str] | None = None,
) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in members.items():
            ti = tarfile.TarInfo(name=name)
            ti.size = len(data)
            ti.mtime = 1700000000
            ti.type = tarfile.REGTYPE
            tf.addfile(ti, io.BytesIO(data))
        if symlinks:
            for link_name, target in symlinks.items():
                ti = tarfile.TarInfo(name=link_name)
                ti.type = tarfile.SYMTYPE
                ti.linkname = target
                tf.addfile(ti)
        if hardlinks:
            for link_name, target in hardlinks.items():
                ti = tarfile.TarInfo(name=link_name)
                ti.type = tarfile.LNKTYPE
                ti.linkname = target
                tf.addfile(ti)
    return buf.getvalue()


def test_normalize_shopaikey_direct_mp3_real_passes():
    status, audio, detail = async_adapter.normalize_shopaikey_tts_audio_payload(SAMPLE_VALID_MP3, "audio/mpeg")
    assert status == "PASS"
    assert audio == SAMPLE_VALID_MP3
    assert "direct_mp3" in detail
    assert "VALID" in detail


def test_normalize_shopaikey_direct_fake_id3_rejected():
    fake_id3 = b"ID3" + b"\x00" * 100
    status, audio, detail = async_adapter.normalize_shopaikey_tts_audio_payload(fake_id3, "audio/mpeg")
    assert status == "FAIL_INVALID_AUDIO"
    assert audio == b""
    assert "invalid_audio" in detail.lower()


def test_normalize_shopaikey_direct_fake_mpeg_sync_rejected():
    fake_sync = b"\xff\xfb\x90\x44" + b"\x00" * 100
    status, audio, detail = async_adapter.normalize_shopaikey_tts_audio_payload(fake_sync)
    assert status == "FAIL_INVALID_AUDIO"
    assert audio == b""
    assert "invalid_audio" in detail.lower()


def test_normalize_shopaikey_tar_single_mp3_with_sidecars():
    tar_bytes = make_test_tar({
        "content-123456.titles": b"titles metadata text",
        "content-123456.mp3": SAMPLE_VALID_MP3,
        "content-123456.extra": b"extra metadata json",
    })
    status, audio, detail = async_adapter.normalize_shopaikey_tts_audio_payload(tar_bytes, "application/octet-stream")
    assert status == "PASS"
    assert audio == SAMPLE_VALID_MP3
    assert "tar_extracted" in detail
    assert "content-123456.mp3" in detail


def test_normalize_shopaikey_tar_fake_id3_member_rejected():
    tar_bytes = make_test_tar({
        "content-123456.titles": b"titles metadata",
        "content-123456.mp3": b"ID3" + b"\x00" * 120,
    })
    status, audio, detail = async_adapter.normalize_shopaikey_tts_audio_payload(tar_bytes)
    assert status == "FAIL_INVALID_AUDIO"
    assert audio == b""
    assert "invalid_audio" in detail.lower()


def test_normalize_shopaikey_tar_corrupt_mp3_fails():
    tar_bytes = make_test_tar({
        "content-123456.mp3": b"\xff\xfb\x00\x00" + b"corrupt_mp3_stream_data" * 10,
    })
    status, audio, detail = async_adapter.normalize_shopaikey_tts_audio_payload(tar_bytes)
    assert status == "FAIL_INVALID_AUDIO"
    assert audio == b""


def test_normalize_shopaikey_tar_multiple_mp3_fails():
    tar_bytes = make_test_tar({
        "track1.mp3": SAMPLE_VALID_MP3,
        "track2.mp3": SAMPLE_VALID_MP3,
    })
    status, audio, detail = async_adapter.normalize_shopaikey_tts_audio_payload(tar_bytes)
    assert status.startswith("FAIL")
    assert audio == b""
    assert "multiple" in detail.lower()


def test_normalize_shopaikey_tar_no_mp3_fails():
    tar_bytes = make_test_tar({
        "content-123456.titles": b"titles metadata",
        "content-123456.extra": b"extra metadata",
    })
    status, audio, detail = async_adapter.normalize_shopaikey_tts_audio_payload(tar_bytes)
    assert status.startswith("FAIL")
    assert audio == b""
    assert "no mp3" in detail.lower() or "not found" in detail.lower()


def test_normalize_shopaikey_tar_unsafe_path_traversal_fails():
    tar_bytes = make_test_tar({
        "../../etc/evil.mp3": SAMPLE_VALID_MP3,
    })
    status, audio, detail = async_adapter.normalize_shopaikey_tts_audio_payload(tar_bytes)
    assert status == "FAIL_UNSAFE_TAR"
    assert audio == b""
    assert "traversal" in detail.lower() or "unsafe" in detail.lower()


def test_normalize_shopaikey_tar_absolute_path_fails():
    tar_bytes = make_test_tar({
        "/absolute/audio.mp3": SAMPLE_VALID_MP3,
    })
    status, audio, detail = async_adapter.normalize_shopaikey_tts_audio_payload(tar_bytes)
    assert status == "FAIL_UNSAFE_TAR"
    assert audio == b""
    assert "traversal" in detail.lower() or "unsafe" in detail.lower()


def test_normalize_shopaikey_tar_symlink_fails():
    tar_bytes = make_test_tar(
        {"real.mp3": SAMPLE_VALID_MP3},
        symlinks={"link.mp3": "real.mp3"},
    )
    status, audio, detail = async_adapter.normalize_shopaikey_tts_audio_payload(tar_bytes)
    assert status == "FAIL_UNSAFE_TAR"
    assert audio == b""
    assert "unsafe" in detail.lower() or "link" in detail.lower()


def test_normalize_shopaikey_tar_hardlink_fails():
    tar_bytes = make_test_tar(
        {"real.mp3": SAMPLE_VALID_MP3},
        hardlinks={"hardlink.mp3": "real.mp3"},
    )
    status, audio, detail = async_adapter.normalize_shopaikey_tts_audio_payload(tar_bytes)
    assert status == "FAIL_UNSAFE_TAR"
    assert audio == b""
    assert "unsafe" in detail.lower() or "link" in detail.lower()


def test_normalize_shopaikey_random_payload_fails():
    random_junk = b"\x01\x02\x03\x04" * 200  # 800 bytes of non-audio non-tar
    status, audio, detail = async_adapter.normalize_shopaikey_tts_audio_payload(random_junk)
    assert status.startswith("FAIL")
    assert audio == b""


@pytest.mark.anyio
async def test_download_audio_from_url_normalizes_tar():
    tar_bytes = make_test_tar({
        "audio.titles": b"titles",
        "audio.mp3": SAMPLE_VALID_MP3,
    })

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=tar_bytes, headers={"content-type": "application/octet-stream"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        audio, detail, http_status = await async_adapter.download_audio_from_url("https://example.com/audio", client=client)

    assert http_status == 200
    assert audio == SAMPLE_VALID_MP3
    assert "tar_extracted" in detail


@pytest.mark.anyio
async def test_download_audio_from_url_rejects_tar_with_fake_id3():
    tar_bytes = make_test_tar({
        "audio.titles": b"titles",
        "audio.mp3": b"ID3" + b"\x00" * 100,
    })

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=tar_bytes, headers={"content-type": "application/octet-stream"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        audio, detail, http_status = await async_adapter.download_audio_from_url("https://example.com/audio", client=client)

    assert http_status == 200
    assert audio == b""
    assert "normalization_failed" in detail


@pytest.mark.anyio
async def test_download_audio_from_url_rejects_random_payload():
    random_junk = b"NON_AUDIO_PAYLOAD" * 50  # > 512 bytes

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=random_junk, headers={"content-type": "application/octet-stream"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        audio, detail, http_status = await async_adapter.download_audio_from_url("https://example.com/junk", client=client)

    assert http_status == 200
    assert audio == b""
    assert "normalization_failed" in detail


@pytest.mark.anyio
async def test_shopaikey_minimax_tts_async_bytes_extracts_tar_via_download():
    tar_bytes = make_test_tar({
        "audio.titles": b"titles",
        "audio.mp3": SAMPLE_VALID_MP3,
    })

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "/t2a_async_v2" in url_str:
            return httpx.Response(200, json={"task_id": "task_tar_norm"})
        if "query" in url_str:
            return httpx.Response(200, json={"status": "Success", "download_url": "https://direct.shopaikey.com/dl/archive.tar"})
        if "archive.tar" in url_str:
            return httpx.Response(200, content=tar_bytes, headers={"content-type": "application/octet-stream"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        status, audio_bytes, detail, http_status, task_id = await async_adapter.shopaikey_minimax_tts_async_bytes(
            text="Testing tar normalizer.",
            voice_id="Vietnamese_patient_Instructor_v1",
            poll_interval_seconds=0.01,
            max_poll_seconds=5.0,
            client=client,
            api_key="fake_key",
        )

    assert status == "PASS"
    assert audio_bytes == SAMPLE_VALID_MP3
    assert task_id == "task_tar_norm"


def test_subdub_checkpoint_receives_only_validated_mp3(tmp_path):
    mgr = subdub_tts_checkpoint.SubdubTTSCheckpointManager(
        workspace=str(tmp_path),
        job_id="checkpoint_test_job",
        target_language="vi",
    )
    cue = {"cue_id": "cue_valid", "speaker_id": "spk_1", "text": "Valid MP3 test"}
    voice_id = "Vietnamese_patient_Instructor_v1"

    # Valid MP3 passes record_cue_success and persists to disk
    entry = mgr.record_cue_success(
        cue=cue,
        voice_id=voice_id,
        audio_bytes=SAMPLE_VALID_MP3,
        duration=0.0783,
        provider_label="shopaikey_minimax",
    )
    assert entry["state"] == subdub_tts_checkpoint.STATE_SUCCEEDED
    artifact_path = entry["artifact_path"]
    assert os.path.exists(artifact_path)
    val = subdub_tts_artifact_validator.validate_tts_audio_artifact(artifact_path)
    assert val.ok is True
    assert val.status == "VALID"

    # Fake ID3 audio fails record_cue_success with SubdubTTSArtifactCorruptionError
    cue_fake = {"cue_id": "cue_fake", "speaker_id": "spk_1", "text": "Fake MP3 test"}
    with pytest.raises(subdub_tts_checkpoint.SubdubTTSArtifactCorruptionError):
        mgr.record_cue_success(
            cue=cue_fake,
            voice_id=voice_id,
            audio_bytes=b"ID3" + b"\x00" * 100,
            duration=1.0,
            provider_label="shopaikey_minimax",
        )

    # Outer TAR archive fails record_cue_success with SubdubTTSArtifactCorruptionError
    tar_bytes = make_test_tar({"inner.mp3": SAMPLE_VALID_MP3})
    cue_tar = {"cue_id": "cue_tar", "speaker_id": "spk_1", "text": "TAR outer test"}
    with pytest.raises(subdub_tts_checkpoint.SubdubTTSArtifactCorruptionError):
        mgr.record_cue_success(
            cue=cue_tar,
            voice_id=voice_id,
            audio_bytes=tar_bytes,
            duration=1.0,
            provider_label="shopaikey_minimax",
        )
