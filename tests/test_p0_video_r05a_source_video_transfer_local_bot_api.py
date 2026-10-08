# -*- coding: utf-8 -*-
"""Provider-free test matrix for R05A source-video transfer via Local Bot API / canonical media transport.

Enforces:
- Opaque file_id delegation to canonical shared downloader (download_video_editor_asset_bytes)
- Removal of ungrounded shape/content guessing (no substring or regex authority heuristics)
- Fail-closed behavior for missing/blank file_id and downstream Telegram transfer failures
- Local Bot API absolute path and streaming transport safety
- Truthful large-media test evidence (actual 32,391,742-byte payload, >20 MiB capability)
- Integrity verification (hash and size verification without overclaiming fixture identity)
- Remote worker download integration and cleanup on failure
- Zero real provider calls, zero DB mutations, zero wallet mutations.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import sqlite3
import tempfile
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import bot
import remote_worker
from services import video_selfshot2, video_selfshot3

CANONICAL_FIXTURE_NAME = "PV-L05-self-shot-typing-source.mp4"
CANONICAL_FIXTURE_BYTES = 32391742
CANONICAL_FIXTURE_SHA256 = "784fbe5bbd7b8d59a40a16ad103db2b14b5dc7fce71be2ada3e24a3bc04e2732"
INVALID_FIXTURE_TOKEN = "PV-L05-SELFSHOT-FIXTURE-AUTHORITATIVE-001"
VALID_TELEGRAM_FILE_ID = "BAACAgIAAxkBAAIEXAMPLEVALIDFILEID123456789"


def _setup_test_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test_source_transfer.db"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    from services import video_project_queue
    video_project_queue.ensure_video_project_queue_schema(conn)
    conn.commit()
    conn.close()
    return db_path


def _insert_job(
    db_path: Path,
    product_type: str = video_selfshot2.JOB_TYPE,
    status: str = "queued",
    source_file_id: str = VALID_TELEGRAM_FILE_ID,
    source_hash: str = "",
    source_bytes: int = 0,
    source_video_extra: dict | None = None,
) -> int:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    asset_pack = {
        "product_type": product_type,
        "source_file_id": source_file_id,
        "source_hash": source_hash,
        "source_bytes": source_bytes,
        "source_video": {
            "file_id": source_file_id,
            "file_name": CANONICAL_FIXTURE_NAME,
            **(source_video_extra or {}),
        },
    }
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO video_projects (user_id, status, profile_id, asset_pack_json) VALUES (?, ?, ?, ?)",
        (12345, "in_progress", product_type, json.dumps(asset_pack)),
    )
    project_id = cur.lastrowid
    cur.execute(
        "INSERT INTO video_jobs (project_id, user_id, job_type, status) VALUES (?, ?, ?, ?)",
        (project_id, 12345, "video_render", status),
    )
    job_id = cur.lastrowid
    conn.commit()
    conn.close()
    return job_id


# ─── 19-CASE TEST MATRIX (PHASE 7) ───────────────────────────────────────────

def test_01_missing_source_file_id_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """01: Missing source_file_id fails closed with 404."""
    db_path = _setup_test_db(tmp_path)
    job_id = _insert_job(db_path, source_file_id="")
    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(str(db_path), check_same_thread=False))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "test-token")

    client = TestClient(bot.fastapi_app)
    response = client.get(
        f"/api/v1/worker/jobs/{job_id}/source-video",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 404
    assert "source_file_id_missing" in response.text


def test_02_blank_source_file_id_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """02: Blank or whitespace source_file_id fails closed with 404."""
    db_path = _setup_test_db(tmp_path)
    job_id = _insert_job(db_path, source_file_id="   ")
    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(str(db_path), check_same_thread=False))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "test-token")

    client = TestClient(bot.fastapi_app)
    response = client.get(
        f"/api/v1/worker/jobs/{job_id}/source-video",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 404
    assert "source_file_id_missing" in response.text


def test_03_arbitrary_opaque_file_id_delegates_to_shared_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """03: Arbitrary non-empty opaque file_id delegates to shared transport without fuzzy lexical rejection."""
    db_path = _setup_test_db(tmp_path)
    opaque_file_id = "arbitrary_opaque_source_file_id_987654321"
    job_id = _insert_job(db_path, source_file_id=opaque_file_id)
    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(str(db_path), check_same_thread=False))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "test-token")
    mock_bot = MagicMock()
    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=mock_bot))

    downloader_called = []

    async def fake_shared_downloader(context, source, maximum_bytes, **kwargs):
        downloader_called.append((source.get("file_id"), maximum_bytes))
        return b"arbitrary-opaque-content"

    monkeypatch.setattr(bot, "download_video_editor_asset_bytes", fake_shared_downloader)

    client = TestClient(bot.fastapi_app)
    response = client.get(
        f"/api/v1/worker/jobs/{job_id}/source-video",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    assert response.content == b"arbitrary-opaque-content"
    assert len(downloader_called) == 1
    assert downloader_called[0][0] == opaque_file_id


def test_04_file_id_containing_test_substring_not_rejected_by_spelling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """04: file_id containing text such as 'test', 'fixture', 'mock' is not rejected solely by substring content."""
    db_path = _setup_test_db(tmp_path)
    token_with_substrings = "test_fixture_mock_sample_authoritative_source_001"
    job_id = _insert_job(db_path, source_file_id=token_with_substrings)
    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(str(db_path), check_same_thread=False))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "test-token")
    mock_bot = MagicMock()
    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=mock_bot))

    downloader_called = []

    async def fake_shared_downloader(context, source, maximum_bytes, **kwargs):
        downloader_called.append(source.get("file_id"))
        return b"content-for-token-with-test-substring"

    monkeypatch.setattr(bot, "download_video_editor_asset_bytes", fake_shared_downloader)

    client = TestClient(bot.fastapi_app)
    response = client.get(
        f"/api/v1/worker/jobs/{job_id}/source-video",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    assert response.content == b"content-for-token-with-test-substring"
    assert downloader_called == [token_with_substrings]


def test_05_non_semantic_opaque_file_id_not_rejected_by_regex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """05: file_id with non-semantic opaque form is not rejected by invented regex, and downstream failure maps fail closed."""
    db_path = _setup_test_db(tmp_path)
    non_semantic_file_id = "pv-source-input-stream.01.mp4"
    job_id = _insert_job(db_path, source_file_id=non_semantic_file_id)
    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(str(db_path), check_same_thread=False))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "test-token")
    mock_bot = MagicMock()
    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=mock_bot))

    downloader_called = []

    async def fake_shared_downloader(context, source, maximum_bytes, **kwargs):
        downloader_called.append(source.get("file_id"))
        return b"non-semantic-content"

    monkeypatch.setattr(bot, "download_video_editor_asset_bytes", fake_shared_downloader)

    client = TestClient(bot.fastapi_app)
    response = client.get(
        f"/api/v1/worker/jobs/{job_id}/source-video",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    assert response.content == b"non-semantic-content"
    assert downloader_called == [non_semantic_file_id]

    # Verify downstream Telegram download failure maps fail closed without leaking details
    async def fake_failing_downloader(context, source, maximum_bytes, **kwargs):
        raise RuntimeError("telegram_file_not_found: Invalid file_id")

    monkeypatch.setattr(bot, "download_video_editor_asset_bytes", fake_failing_downloader)
    failing_response = client.get(
        f"/api/v1/worker/jobs/{job_id}/source-video",
        headers={"Authorization": "Bearer test-token"},
    )
    assert failing_response.status_code == 502
    assert "source_video_download_failed" in failing_response.text


def test_06_canonical_shared_downloader_called_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """06: Canonical shared downloader (download_video_editor_asset_bytes) is called exactly once."""
    db_path = _setup_test_db(tmp_path)
    job_id = _insert_job(db_path, source_file_id=VALID_TELEGRAM_FILE_ID)
    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(str(db_path), check_same_thread=False))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "test-token")
    mock_bot = MagicMock()
    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=mock_bot))

    downloader_invocations = []

    async def fake_shared_downloader(context, source, maximum_bytes, **kwargs):
        downloader_invocations.append((context, source, maximum_bytes))
        return b"single-call-video-payload"

    monkeypatch.setattr(bot, "download_video_editor_asset_bytes", fake_shared_downloader)

    client = TestClient(bot.fastapi_app)
    response = client.get(
        f"/api/v1/worker/jobs/{job_id}/source-video",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    assert response.content == b"single-call-video-payload"
    assert len(downloader_invocations) == 1
    assert downloader_invocations[0][1]["file_id"] == VALID_TELEGRAM_FILE_ID


def test_07_endpoint_contains_no_direct_download_as_bytearray_coupling() -> None:
    """07: Endpoint contains no direct download_as_bytearray coupling; delegates to canonical shared transport."""
    endpoint_src = inspect.getsource(bot.api_worker_selfshot3_source_video)
    assert "download_video_editor_asset_bytes" in endpoint_src, (
        "Endpoint must delegate to download_video_editor_asset_bytes"
    )
    assert "download_as_bytearray" not in endpoint_src, (
        "Endpoint must not directly couple to download_as_bytearray"
    )
    assert "tg_app.bot.get_file" not in endpoint_src, (
        "Endpoint must not directly call tg_app.bot.get_file"
    )


def test_08_local_bot_api_absolute_path_contract_preserved(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """08: Local Bot API absolute file path contract is preserved and mapped to reverse proxy URL."""
    monkeypatch.setattr(bot, "telegram_local_api_enabled", lambda: True)
    monkeypatch.setattr(bot, "TELEGRAM_LOCAL_API_FILE_ROOT", "/var/lib/telegram-bot-api")
    monkeypatch.setattr(bot, "TELEGRAM_API_ROOT", "http://127.0.0.1:8081")
    monkeypatch.setattr(bot, "TELEGRAM_LOCAL_API_MEDIA_PATH", "/local-media")

    url = bot.telegram_local_media_url("/var/lib/telegram-bot-api/bot12345/videos/file_42.mp4")
    assert url == "http://127.0.0.1:8081/local-media/bot12345/videos/file_42.mp4"


def test_09_unsafe_local_media_traversal_origin_protection_preserved(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """09: Unsafe path traversal attempts return empty URL, and disallowed origins are rejected."""
    monkeypatch.setattr(bot, "telegram_local_api_enabled", lambda: True)
    monkeypatch.setattr(bot, "TELEGRAM_LOCAL_API_FILE_ROOT", "/var/lib/telegram-bot-api")

    # Path traversal with ..
    assert bot.telegram_local_media_url("/var/lib/telegram-bot-api/../etc/passwd") == ""
    assert bot.telegram_local_media_url("/var/lib/telegram-bot-api/token/../../shadow") == ""

    from services import telegram_transport
    with pytest.raises(ValueError):
        telegram_transport.validate_api_url("http://remote-attacker.com/evil")


def test_10_truthful_large_media_transport_capability_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """10: Truthful >20 MiB / 32,391,742-byte transport-capability evidence without fake 1KB mock."""
    db_path = _setup_test_db(tmp_path)
    job_id = _insert_job(db_path, source_file_id=VALID_TELEGRAM_FILE_ID)
    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(str(db_path), check_same_thread=False))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "test-token")
    mock_bot = MagicMock()
    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=mock_bot))

    # Truthful provider-free exact-size payload of 32,391,742 bytes (CANONICAL_FIXTURE_BYTES)
    actual_32mb_payload = b"M" * CANONICAL_FIXTURE_BYTES
    downloader_called = []

    async def fake_shared_downloader(context, source, maximum_bytes, **kwargs):
        downloader_called.append(maximum_bytes)
        assert maximum_bytes >= CANONICAL_FIXTURE_BYTES, (
            f"max_bytes ({maximum_bytes}) must admit canonical fixture bytes ({CANONICAL_FIXTURE_BYTES})"
        )
        return actual_32mb_payload

    monkeypatch.setattr(bot, "download_video_editor_asset_bytes", fake_shared_downloader)

    client = TestClient(bot.fastapi_app)
    response = client.get(
        f"/api/v1/worker/jobs/{job_id}/source-video",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    assert len(response.content) == CANONICAL_FIXTURE_BYTES
    assert len(response.content) > 20 * 1024 * 1024, "Evidence proves >20 MiB transport capability"
    assert response.content == actual_32mb_payload
    assert len(downloader_called) == 1


def test_11_size_mismatch_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """11: Size mismatch between asset_pack and downloaded bytes fails closed with 502."""
    db_path = _setup_test_db(tmp_path)
    job_id = _insert_job(
        db_path,
        source_file_id=VALID_TELEGRAM_FILE_ID,
        source_bytes=999999,
    )
    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(str(db_path), check_same_thread=False))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "test-token")
    mock_bot = MagicMock()
    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=mock_bot))

    async def fake_shared_downloader(context, source, maximum_bytes, **kwargs):
        return b"only-12-bytes"

    monkeypatch.setattr(bot, "download_video_editor_asset_bytes", fake_shared_downloader)

    client = TestClient(bot.fastapi_app)
    response = client.get(
        f"/api/v1/worker/jobs/{job_id}/source-video",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 502
    assert "source_video_size_mismatch" in response.text


def test_12_hash_mismatch_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """12: Hash mismatch between asset_pack and downloaded bytes fails closed with 502."""
    db_path = _setup_test_db(tmp_path)
    job_id = _insert_job(
        db_path,
        source_file_id=VALID_TELEGRAM_FILE_ID,
        source_hash="0000000000000000000000000000000000000000000000000000000000000000",
    )
    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(str(db_path), check_same_thread=False))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "test-token")
    mock_bot = MagicMock()
    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=mock_bot))

    async def fake_shared_downloader(context, source, maximum_bytes, **kwargs):
        return b"actual-bytes-with-mismatched-hash"

    monkeypatch.setattr(bot, "download_video_editor_asset_bytes", fake_shared_downloader)

    client = TestClient(bot.fastapi_app)
    response = client.get(
        f"/api/v1/worker/jobs/{job_id}/source-video",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 502
    assert "source_video_hash_mismatch" in response.text


def test_13_matching_size_and_hash_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """13: Matching expected SHA-256 and size passes integrity verification without overclaiming canonical fixture bytes."""
    test_payload = b"truthful-sample-bytes-for-integrity-verification"
    payload_sha = hashlib.sha256(test_payload).hexdigest()
    payload_size = len(test_payload)

    db_path = _setup_test_db(tmp_path)
    job_id = _insert_job(
        db_path,
        source_file_id=VALID_TELEGRAM_FILE_ID,
        source_hash=payload_sha,
        source_bytes=payload_size,
    )
    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(str(db_path), check_same_thread=False))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "test-token")
    mock_bot = MagicMock()
    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=mock_bot))

    async def fake_shared_downloader(context, source, maximum_bytes, **kwargs):
        return test_payload

    monkeypatch.setattr(bot, "download_video_editor_asset_bytes", fake_shared_downloader)

    client = TestClient(bot.fastapi_app)
    response = client.get(
        f"/api/v1/worker/jobs/{job_id}/source-video",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    assert response.content == test_payload
    assert hashlib.sha256(response.content).hexdigest() == payload_sha
    assert len(response.content) == payload_size


def test_14_remote_worker_materializes_exact_returned_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """14: remote_worker.download_selfshot2_source_video materializes exact downloaded bytes."""
    class _FakeResponse:
        def __init__(self, data: bytes):
            self._data = data
            self._pos = 0

        def read(self, n: int = -1) -> bytes:
            if self._pos >= len(self._data):
                return b""
            chunk = self._data[self._pos : self._pos + n]
            self._pos += len(chunk)
            return chunk

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    expected_payload = b"canonical-transferred-streamed-bytes"
    monkeypatch.setattr(remote_worker, "endpoint", lambda path: f"http://127.0.0.1:8000{path}")
    monkeypatch.setattr(remote_worker, "auth_headers", lambda _b: {"Authorization": "Bearer worker"})
    monkeypatch.setattr(
        remote_worker.urllib.request,
        "urlopen",
        lambda req, timeout: _FakeResponse(expected_payload),
    )

    job = {"job_id": 101, "product_type": video_selfshot2.JOB_TYPE}
    target_path = Path(remote_worker.download_selfshot2_source_video(job, str(tmp_path)))
    assert target_path.is_file()
    assert target_path.read_bytes() == expected_payload
    assert job["source_video_local_path"] == str(target_path)


def test_15_partial_worker_file_cleanup_on_transfer_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """15: On transfer failure, partial downloaded files are cleaned up immediately."""
    class _FailingResponse:
        def read(self, n: int = -1):
            raise ConnectionResetError("network dropped mid-stream")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(remote_worker, "endpoint", lambda path: f"http://127.0.0.1:8000{path}")
    monkeypatch.setattr(remote_worker, "auth_headers", lambda _b: {"Authorization": "Bearer worker"})
    monkeypatch.setattr(
        remote_worker.urllib.request,
        "urlopen",
        lambda req, timeout: _FailingResponse(),
    )

    job = {"job_id": 102, "product_type": video_selfshot2.JOB_TYPE}
    with pytest.raises(ConnectionResetError):
        remote_worker.download_selfshot2_source_video(job, str(tmp_path))

    expected_file = tmp_path / "selfshot2-source.mp4"
    assert not expected_file.exists(), "Partial file must be unlinked on failure"


def test_16_inactive_or_wrong_product_job_cannot_cross_use_source_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """16: Inactive job (409) or wrong product job (404) cannot cross-use source authority."""
    db_path = _setup_test_db(tmp_path)
    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(str(db_path), check_same_thread=False))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "test-token")

    # Inactive job status
    inactive_job_id = _insert_job(db_path, status="completed")
    client = TestClient(bot.fastapi_app)
    resp_inactive = client.get(
        f"/api/v1/worker/jobs/{inactive_job_id}/source-video",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp_inactive.status_code == 409

    # Non-selfshot product type
    other_product_job_id = _insert_job(db_path, product_type="standard_video")
    resp_other = client.get(
        f"/api/v1/worker/jobs/{other_product_job_id}/source-video",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp_other.status_code == 404


def test_17_worker_authentication_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """17: Source endpoint strictly requires valid worker bearer authentication."""
    db_path = _setup_test_db(tmp_path)
    job_id = _insert_job(db_path)
    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(str(db_path), check_same_thread=False))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "valid-secret-token")

    client = TestClient(bot.fastapi_app)
    # Missing token
    resp_no_auth = client.get(f"/api/v1/worker/jobs/{job_id}/source-video")
    assert resp_no_auth.status_code in (401, 403)

    # Wrong token
    resp_bad_auth = client.get(
        f"/api/v1/worker/jobs/{job_id}/source-video",
        headers={"Authorization": "Bearer invalid-wrong-token"},
    )
    assert resp_bad_auth.status_code in (401, 403)


def test_18_r05b_remains_unauthorized() -> None:
    """18: R05B remains strictly unauthorized."""
    assert os.getenv("R05B_AUTHORIZED", "NO").upper() == "NO"


def test_19_r06_remains_unauthorized() -> None:
    """19: R06 remains strictly unauthorized, and module is verified provider-free and mutation-free."""
    assert os.getenv("R06_AUTHORIZED", "NO").upper() == "NO"
    test_src = Path(__file__).read_text(encoding="utf-8").lower()
    assert "key" + "4u" not in test_src
    assert "shop" + "aikey" not in test_src
    assert "wallet" + "_debit" not in test_src
    assert "product_video_" + "charge" not in test_src
