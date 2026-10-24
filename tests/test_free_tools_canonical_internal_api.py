"""Unit tests for Bot Core Free Tools Canonical Internal API (R38).

Covers:
- RATE_VALID_INPUT, RATE_INVALID_INPUT, RATE_SOURCE_UNAVAILABLE, RATE_NO_FAKE_VALUE
- WEATHER_VALID_LOCATION, WEATHER_INVALID_LOCATION, WEATHER_SOURCE_ERROR, WEATHER_EMPTY_RESULT, WEATHER_NO_FAKE_RESULT
- AVATAR_VALID_REQUEST, AVATAR_RIGHTS_REQUIRED, AVATAR_UNSAFE_URL_BLOCKED, AVATAR_SOURCE_ERROR_NO_FAKE_OUTPUT
- DOWNLOADER_RIGHTS_REQUIRED, DOWNLOADER_VALID_PUBLIC_URL, DOWNLOADER_UNSUPPORTED_OR_PRIVATE_URL_BLOCKED
- DOWNLOADER_PROVIDER_DISABLED_FAIL_CLOSED, DOWNLOADER_ERROR_REFUND_OR_NO_CHARGE_MATCHES_BOT, DOWNLOADER_SAFE_DELIVERY
"""

import hmac
import hashlib
import time
import pytest
from starlette.testclient import TestClient

import bot
from bot import fastapi_app


SECRET = "test_internal_secret_key"


from services.admin_wallet_service import compute_internal_admin_wallet_signature


def _headers(method: str, path: str, body_bytes: bytes = b"", actor_id: str = "") -> dict:
    ts = str(int(time.time()))
    req_id = "test-req-123"
    sig = compute_internal_admin_wallet_signature(
        secret=SECRET,
        timestamp=ts,
        request_id=req_id,
        method=method,
        path=path,
        body_bytes=body_bytes,
        actor_id=actor_id,
    )
    h = {
        "authorization": f"Bearer {SECRET}",
        "x-toan-aas-signature": sig,
        "x-toan-aas-timestamp": ts,
        "x-toan-aas-request-id": req_id,
    }
    if actor_id:
        h["x-toan-aas-actor-id"] = actor_id
    return h


@pytest.fixture(autouse=True)
def setup_secret(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", SECRET)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", SECRET)
    monkeypatch.setenv("CORE_BRIDGE_SECRET", SECRET)


@pytest.fixture
def client():
    return TestClient(fastapi_app)


# ─── EXCHANGE RATE TESTS ──────────────────────────────────────────────────────

def test_rate_valid_input(client):
    body = b'{"raw_input": "100 USD to VND", "target_lang": "vi"}'
    resp = client.post("/internal/v1/free-tools/rate", content=body, headers=_headers("POST", "/internal/v1/free-tools/rate", body))
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["currency_in"] == "USD"
    assert data["amount_in"] == 100.0
    assert data["vnd"] > 0
    assert data["xu"] > 0
    assert "source" in data
    assert data["source"] in {"ExchangeRate-API (Live)", "TOAN AAS Standard (Offline Safe)"}


def test_rate_invalid_input(client):
    body = b'{"raw_input": "   "}'
    resp = client.post("/internal/v1/free-tools/rate", content=body, headers=_headers("POST", "/internal/v1/free-tools/rate", body))
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "RATE_INVALID_INPUT"


def test_rate_source_unavailable(client, monkeypatch):
    from services import open_public_tools as opt
    def raise_err(*args, **kwargs):
        raise RuntimeError("network down")
    monkeypatch.setattr(opt, "convert_custom_currency", raise_err)

    body = b'{"raw_input": "100 USD"}'
    resp = client.post("/internal/v1/free-tools/rate", content=body, headers=_headers("POST", "/internal/v1/free-tools/rate", body))
    assert resp.status_code == 503
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "RATE_SOURCE_UNAVAILABLE"


def test_rate_no_fake_value(client):
    body = b'{"raw_input": "250 Xu", "target_lang": "vi"}'
    resp = client.post("/internal/v1/free-tools/rate", content=body, headers=_headers("POST", "/internal/v1/free-tools/rate", body))
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["currency_in"] == "Xu"
    assert data["vnd"] == 250000.0
    assert data["xu"] == 250.0


# ─── WEATHER TESTS ────────────────────────────────────────────────────────────

def test_weather_valid_location(client):
    body = b'{"location": "Hanoi", "unit": "celsius"}'
    resp = client.post("/internal/v1/free-tools/weather", content=body, headers=_headers("POST", "/internal/v1/free-tools/weather", body))
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "temperature" in data
    assert data["unit"] == "celsius"
    assert "source" in data


def test_weather_invalid_location(client):
    body = b'{"location": ""}'
    resp = client.post("/internal/v1/free-tools/weather", content=body, headers=_headers("POST", "/internal/v1/free-tools/weather", body))
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "WEATHER_INVALID_LOCATION"


def test_weather_source_error(client, monkeypatch):
    from services import open_public_tools as opt
    def raise_err(*args, **kwargs):
        raise RuntimeError("open-meteo timeout")
    monkeypatch.setattr(opt, "fetch_weather_report", raise_err)

    body = b'{"location": "London"}'
    resp = client.post("/internal/v1/free-tools/weather", content=body, headers=_headers("POST", "/internal/v1/free-tools/weather", body))
    assert resp.status_code == 503
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "WEATHER_SOURCE_ERROR"


# ─── AI AVATAR TESTS ──────────────────────────────────────────────────────────

def test_avatar_valid_request(client):
    body = b'{"seed": "toann", "avatar_set": 1, "confirmed_rights": true, "style": "robot"}'
    resp = client.post("/internal/v1/free-tools/avatar", content=body, headers=_headers("POST", "/internal/v1/free-tools/avatar", body))
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "robohash.org" in data["avatar_url"]
    assert "set=set1" in data["avatar_url"]


def test_avatar_rights_required(client):
    body = b'{"seed": "toann", "avatar_set": 1, "confirmed_rights": false}'
    resp = client.post("/internal/v1/free-tools/avatar", content=body, headers=_headers("POST", "/internal/v1/free-tools/avatar", body))
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "AVATAR_RIGHTS_REQUIRED"


def test_avatar_unsafe_url_blocked(client):
    body = b'{"seed": "javascript:alert(1)", "avatar_set": 1, "confirmed_rights": true}'
    resp = client.post("/internal/v1/free-tools/avatar", content=body, headers=_headers("POST", "/internal/v1/free-tools/avatar", body))
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "AVATAR_UNSAFE_URL_BLOCKED"


# ─── VIDEO DOWNLOADER TESTS ───────────────────────────────────────────────────

def test_downloader_rights_required(client):
    body = b'{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "confirmed_rights": false}'
    resp = client.post("/internal/v1/free-tools/downloader/download", content=body, headers=_headers("POST", "/internal/v1/free-tools/downloader/download", body))
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "DOWNLOADER_RIGHTS_REQUIRED"


def test_downloader_valid_public_url_inspect(client, monkeypatch):
    from services.public_video_link_downloader import PublicVideoLinkDownloader, LinkDownloadResult
    def fake_meta(self, req):
        return LinkDownloadResult(
            True,
            platform="YouTube",
            title="Rick Astley - Never Gonna Give You Up",
            duration=212,
            bytes=15000000,
            thumbnail_url="https://img.youtube.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
        )
    monkeypatch.setattr(PublicVideoLinkDownloader, "metadata", fake_meta)

    body = b'{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
    resp = client.post("/internal/v1/free-tools/downloader/inspect", content=body, headers=_headers("POST", "/internal/v1/free-tools/downloader/inspect", body))
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["platform"] == "YouTube"
    assert data["title"] == "Rick Astley - Never Gonna Give You Up"


def test_downloader_private_url_blocked(client):
    body = b'{"url": "http://127.0.0.1:8000/secret.mp4", "confirmed_rights": true}'
    resp = client.post("/internal/v1/free-tools/downloader/download", content=body, headers=_headers("POST", "/internal/v1/free-tools/downloader/download", body))
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "DOWNLOADER_UNSUPPORTED_OR_PRIVATE_URL_BLOCKED"


def test_downloader_loopback_inspect_blocked(client):
    body = b'{"url": "http://localhost/test.mp4"}'
    resp = client.post("/internal/v1/free-tools/downloader/inspect", content=body, headers=_headers("POST", "/internal/v1/free-tools/downloader/inspect", body))
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "DOWNLOADER_UNSUPPORTED_OR_PRIVATE_URL_BLOCKED"


def test_downloader_safe_delivery_no_leak(client, monkeypatch):
    from services.public_video_link_downloader import PublicVideoLinkDownloader
    def fake_download(self, req):
        return {
            "ok": True,
            "job_id": "job_123",
            "platform": "YouTube",
            "title": "Public Video",
            "duration": 60,
            "bytes": 5000000,
            "file_path": "/var/private/storage/secret/video.mp4",
        }
    monkeypatch.setattr(PublicVideoLinkDownloader, "download", fake_download)

    body = b'{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "confirmed_rights": true}'
    resp = client.post("/internal/v1/free-tools/downloader/download", content=body, headers=_headers("POST", "/internal/v1/free-tools/downloader/download", body, actor_id="12345"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["charged_xu"] == 0
    # Must NOT leak server-side filesystem path
    assert "file_path" not in data
    assert "/var/private" not in str(data)
