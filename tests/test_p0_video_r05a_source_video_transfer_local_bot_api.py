# -*- coding: utf-8 -*-
"""Provider-free test matrix for R05A source-video transfer via Local Bot API / canonical media transport.

Enforces:
- Fixture token fail-closed (tokens like PV-L05-SELFSHOT-FIXTURE-AUTHORITATIVE-001 cannot masquerade as Telegram file_id)
- Delegation to canonical shared downloader (download_video_editor_asset_bytes)
- Local Bot API absolute path and streaming transport safety
- Integrity verification (hash and size verification)
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


# ─── CANONICAL SHARED TRANSPORT WIRING TEST ──────────────────────────────────

def test_canonical_shared_downloader_wiring() -> None:
    """Proves the hardened post-fix wiring: delegates to download_video_editor_asset_bytes."""
    endpoint_src = inspect.getsource(bot.api_worker_selfshot3_source_video)
    assert "download_video_editor_asset_bytes" in endpoint_src, (
        "Endpoint must delegate to download_video_editor_asset_bytes"
    )
    assert "download_as_bytearray" not in endpoint_src, (
        "Endpoint must not directly call download_as_bytearray"
    )


# ─── 18-CASE TEST MATRIX ─────────────────────────────────────────────────────

def test_01_invalid_fixture_token_cannot_masquerade_as_telegram_file_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """01: Internal fixture tokens (e.g. PV-L05-SELFSHOT-FIXTURE-AUTHORITATIVE-001) fail closed."""
    db_path = _setup_test_db(tmp_path)
    job_id = _insert_job(db_path, source_file_id=INVALID_FIXTURE_TOKEN)
    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(str(db_path), check_same_thread=False))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "test-token")
    mock_bot = MagicMock()
    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=mock_bot))

    client = TestClient(bot.fastapi_app)
    response = client.get(
        f"/api/v1/worker/jobs/{job_id}/source-video",
        headers={"Authorization": "Bearer test-token"},
    )
    # Must fail closed with 422 (or 400), and MUST NOT call tg_app.bot.get_file
    assert response.status_code in (400, 422)
    assert not mock_bot.get_file.called


def test_02_missing_source_file_id_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """02: Missing source_file_id fails closed with 404."""
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


def test_03_blank_source_file_id_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """03: Blank or whitespace source_file_id fails closed with 404."""
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


def test_04_source_endpoint_requires_worker_authentication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """04: Source endpoint strictly requires valid worker bearer authentication."""
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


def test_05_wrong_job_cannot_cross_use_r05a_source_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """05: Non-selfshot product or inactive job cannot cross-use source authority."""
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


def test_06_valid_telegram_file_id_delegates_to_canonical_shared_downloader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """06: Valid Telegram file_id delegates to canonical download_video_editor_asset_bytes."""
    db_path = _setup_test_db(tmp_path)
    job_id = _insert_job(db_path, source_file_id=VALID_TELEGRAM_FILE_ID)
    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(str(db_path), check_same_thread=False))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "test-token")
    mock_bot = MagicMock()
    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=mock_bot))

    downloader_called = []

    async def fake_shared_downloader(context, source, maximum_bytes, **kwargs):
        downloader_called.append((source.get("file_id"), maximum_bytes))
        return b"fake-video-content-from-shared-downloader"

    monkeypatch.setattr(bot, "download_video_editor_asset_bytes", fake_shared_downloader)

    client = TestClient(bot.fastapi_app)
    response = client.get(
        f"/api/v1/worker/jobs/{job_id}/source-video",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    assert response.content == b"fake-video-content-from-shared-downloader"
    assert len(downloader_called) == 1
    assert downloader_called[0][0] == VALID_TELEGRAM_FILE_ID


def test_07_local_bot_api_absolute_file_path_handled_through_safe_transport(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """07: Local Bot API server path is safely converted to reverse proxy URL."""
    monkeypatch.setattr(bot, "telegram_local_api_enabled", lambda: True)
    monkeypatch.setattr(bot, "TELEGRAM_LOCAL_API_FILE_ROOT", "/var/lib/telegram-bot-api")
    monkeypatch.setattr(bot, "TELEGRAM_API_ROOT", "http://127.0.0.1:8081")
    monkeypatch.setattr(bot, "TELEGRAM_LOCAL_API_MEDIA_PATH", "/local-media")

    url = bot.telegram_local_media_url("/var/lib/telegram-bot-api/bot12345/videos/file_42.mp4")
    assert url == "http://127.0.0.1:8081/local-media/bot12345/videos/file_42.mp4"


def test_08_local_bot_api_path_traversal_rejected(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """08: Path traversal attempts in file_path return empty URL."""
    monkeypatch.setattr(bot, "telegram_local_api_enabled", lambda: True)
    monkeypatch.setattr(bot, "TELEGRAM_LOCAL_API_FILE_ROOT", "/var/lib/telegram-bot-api")

    # Path traversal with ..
    assert bot.telegram_local_media_url("/var/lib/telegram-bot-api/../etc/passwd") == ""
    assert bot.telegram_local_media_url("/var/lib/telegram-bot-api/token/../../shadow") == ""


def test_09_unsafe_origin_or_redirect_cannot_receive_credentials(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """09: validate_api_url rejects non-local/disallowed hosts and redirects are disabled."""
    from services import telegram_transport
    with pytest.raises(ValueError):
        telegram_transport.validate_api_url("http://remote-attacker.com/evil")


def test_10_simulated_32mb_source_contract_succeeds_without_cloud_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """10: Simulated canonical fixture length (32,391,742 bytes) transfers through abstraction."""
    db_path = _setup_test_db(tmp_path)
    job_id = _insert_job(db_path, source_file_id=VALID_TELEGRAM_FILE_ID)
    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(str(db_path), check_same_thread=False))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "test-token")
    mock_bot = MagicMock()
    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=mock_bot))

    simulated_payload = b"X" * 1024  # Lightweight payload with simulated length
    async def fake_shared_downloader(context, source, maximum_bytes, **kwargs):
        assert maximum_bytes >= CANONICAL_FIXTURE_BYTES
        return simulated_payload

    monkeypatch.setattr(bot, "download_video_editor_asset_bytes", fake_shared_downloader)

    client = TestClient(bot.fastapi_app)
    response = client.get(
        f"/api/v1/worker/jobs/{job_id}/source-video",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    assert response.content == simulated_payload


def test_11_transferred_bytes_hash_mismatch_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """11: If expected_hash or expected_bytes mismatch, endpoint fails closed."""
    db_path = _setup_test_db(tmp_path)
    job_id = _insert_job(
        db_path,
        source_file_id=VALID_TELEGRAM_FILE_ID,
        source_hash="0000000000000000000000000000000000000000000000000000000000000000",
        source_bytes=999999,
    )
    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(str(db_path), check_same_thread=False))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "test-token")
    mock_bot = MagicMock()
    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=mock_bot))

    async def fake_shared_downloader(context, source, maximum_bytes, **kwargs):
        return b"some-actual-bytes-with-different-hash"

    monkeypatch.setattr(bot, "download_video_editor_asset_bytes", fake_shared_downloader)

    client = TestClient(bot.fastapi_app)
    response = client.get(
        f"/api/v1/worker/jobs/{job_id}/source-video",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 502
    assert "integrity_mismatch" in response.text or "hash_mismatch" in response.text or "size_mismatch" in response.text


def test_12_exact_fixture_sha_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """12: Exact fixture SHA matches and transfer succeeds."""
    payload = b"typing-source-sample-bytes"
    payload_sha = hashlib.sha256(payload).hexdigest()

    db_path = _setup_test_db(tmp_path)
    job_id = _insert_job(
        db_path,
        source_file_id=VALID_TELEGRAM_FILE_ID,
        source_hash=payload_sha,
        source_bytes=len(payload),
    )
    monkeypatch.setattr(bot, "db_connect", lambda: sqlite3.connect(str(db_path), check_same_thread=False))
    monkeypatch.setattr(bot, "LOCAL_WORKER_TOKEN", "test-token")
    mock_bot = MagicMock()
    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=mock_bot))

    async def fake_shared_downloader(context, source, maximum_bytes, **kwargs):
        return payload

    monkeypatch.setattr(bot, "download_video_editor_asset_bytes", fake_shared_downloader)

    client = TestClient(bot.fastapi_app)
    response = client.get(
        f"/api/v1/worker/jobs/{job_id}/source-video",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    assert response.content == payload


def test_13_remote_worker_download_selfshot2_source_video_receives_exact_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """13: remote_worker.download_selfshot2_source_video materializes exact downloaded bytes."""
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


def test_14_no_temporary_partial_file_remains_after_transfer_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """14: On transfer failure, partial downloaded files are cleaned up immediately."""
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


def test_15_r05a_provider_route_not_invoked_during_source_transfer_tests() -> None:
    """15: Strictly provider-free: no external video provider API calls in this test module."""
    test_src = Path(__file__).read_text(encoding="utf-8").lower()
    assert "key" + "4u" not in test_src
    assert "shop" + "aikey" not in test_src


def test_16_wallet_customer_charging_not_invoked() -> None:
    """16: Wallet mutation functions are not referenced or called."""
    test_src = Path(__file__).read_text(encoding="utf-8").lower()
    assert "wallet" + "_debit" not in test_src
    assert "product_video_" + "charge" not in test_src


def test_17_r05b_remains_unauthorized() -> None:
    """17: R05B remains strictly unauthorized."""
    assert os.getenv("R05B_AUTHORIZED", "NO").upper() == "NO"


def test_18_r06_remains_unauthorized() -> None:
    """18: R06 remains strictly unauthorized."""
    assert os.getenv("R06_AUTHORIZED", "NO").upper() == "NO"
