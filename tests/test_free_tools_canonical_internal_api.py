"""Unit tests for Bot Core Free Tools Canonical Internal API (R38).

Covers:
- RATE_VALID_INPUT, RATE_INVALID_INPUT, RATE_LIVE_SOURCE, RATE_OFFLINE_SAFE_FALLBACK, RATE_NO_FAKE_VALUE
- WEATHER_VALID_LOCATION, WEATHER_INVALID_LOCATION, WEATHER_LIVE_SOURCE, WEATHER_OFFLINE_SAFE_FALLBACK
- AVATAR_VALID_REQUEST, AVATAR_RIGHTS_REQUIRED, AVATAR_UNSAFE_URL_BLOCKED
- DOWNLOADER_RIGHTS_REQUIRED, DOWNLOADER_VALID_PUBLIC_URL, DOWNLOADER_UNSUPPORTED_OR_PRIVATE_URL_BLOCKED
- DOWNLOADER_DOWNLOAD_TO_DELIVERY, DOWNLOADER_OWNER_SAFE_DELIVERY, DOWNLOADER_FOREIGN_OWNER_BLOCKED
- DOWNLOADER_STALE_ARTIFACT_TRUTH, DOWNLOADER_SAFE_DELIVERY_NO_LEAK
"""

import hashlib
import hmac
import os
import tempfile
import time
from pathlib import Path
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


def test_rate_invalid_input(client):
    body = b'{"raw_input": "   "}'
    resp = client.post("/internal/v1/free-tools/rate", content=body, headers=_headers("POST", "/internal/v1/free-tools/rate", body))
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "RATE_INVALID_INPUT"


def test_rate_live_source_parity(client, monkeypatch):
    """RATE_LIVE_SOURCE: Validates source is live when live API answers."""
    from services import open_public_tools as opt
    monkeypatch.setattr(opt, "fetch_all_exchange_rates", lambda: ({"VND": 26127.0, "EUR": 0.858}, "ExchangeRate-API (Live)"))

    body = b'{"raw_input": "50 USD", "target_lang": "vi"}'
    resp = client.post("/internal/v1/free-tools/rate", content=body, headers=_headers("POST", "/internal/v1/free-tools/rate", body))
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["source"] == "ExchangeRate-API (Live)"
    assert data["amount_in"] == 50.0


def test_rate_offline_safe_fallback_parity(client, monkeypatch):
    """RATE_OFFLINE_SAFE_FALLBACK: Truthfully marks offline safe fallback when live rate is down."""
    from services import open_public_tools as opt
    monkeypatch.setattr(opt, "fetch_all_exchange_rates", lambda: (opt.FALLBACK_RATES_USD, "TOAN AAS Standard (Offline Safe)"))

    body = b'{"raw_input": "100 USD", "target_lang": "vi"}'
    resp = client.post("/internal/v1/free-tools/rate", content=body, headers=_headers("POST", "/internal/v1/free-tools/rate", body))
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["source"] == "TOAN AAS Standard (Offline Safe)"
    assert data["amount_in"] == 100.0
    assert data["vnd"] > 0


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


def test_weather_live_source_parity(client, monkeypatch):
    """WEATHER_LIVE_SOURCE: Validates live source string when live weather API answers."""
    from services import open_public_tools as opt
    fake_report = {
        "ok": True,
        "city": "Đà Nẵng",
        "country": "Việt Nam",
        "temperature": 27.5,
        "windspeed": 8.0,
        "weathercode": 1,
        "description": "Chủ yếu quang đãng 🌤",
        "source": "Open-Meteo Live API",
    }
    monkeypatch.setattr(opt, "fetch_weather_report", lambda loc: fake_report)

    body = b'{"location": "Danang", "unit": "celsius"}'
    resp = client.post("/internal/v1/free-tools/weather", content=body, headers=_headers("POST", "/internal/v1/free-tools/weather", body))
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["source"] == "Open-Meteo Live API"
    assert data["temperature"] == 27.5


def test_weather_offline_safe_fallback_parity(client, monkeypatch):
    """WEATHER_OFFLINE_SAFE_FALLBACK: Validates truthful fallback marker when upstream weather is offline."""
    from services import open_public_tools as opt
    fake_fallback = {
        "ok": True,
        "city": "Hà Nội",
        "country": "Việt Nam",
        "temperature": 29.0,
        "windspeed": 12.0,
        "weathercode": 0,
        "description": "Thời tiết đẹp, nắng nhẹ ☀️",
        "source": "Dự báo chuẩn (Offline Safe)",
    }
    monkeypatch.setattr(opt, "fetch_weather_report", lambda loc: fake_fallback)

    body = b'{"location": "Hanoi", "unit": "celsius"}'
    resp = client.post("/internal/v1/free-tools/weather", content=body, headers=_headers("POST", "/internal/v1/free-tools/weather", body))
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["source"] == "Dự báo chuẩn (Offline Safe)"
    assert data["city"] == "Hà Nội"


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
            title="Sample Public Video",
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
    assert data["title"] == "Sample Public Video"


def test_downloader_private_url_blocked(client):
    body = b'{"url": "http://127.0.0.1:8000/secret.mp4", "confirmed_rights": true}'
    resp = client.post("/internal/v1/free-tools/downloader/download", content=body, headers=_headers("POST", "/internal/v1/free-tools/downloader/download", body))
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "DOWNLOADER_UNSUPPORTED_OR_PRIVATE_URL_BLOCKED"


def test_downloader_download_to_delivery_contract(client, monkeypatch, tmp_path):
    from services.public_video_link_downloader import PublicVideoLinkDownloader

    fake_file = tmp_path / "sample_video.mp4"
    fake_file.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512)

    def fake_download(self, req):
        job = {
            "job_id": "LDLTEST12345",
            "user_id": "1001",
            "platform": "YouTube",
            "title": "Rick Astley - Never Gonna Give You Up",
            "duration": 212,
            "bytes": len(fake_file.read_bytes()),
            "video_path": str(fake_file),
            "requested_asset": "video",
        }
        self._save_job(job)
        return {
            "ok": True,
            "job_id": "LDLTEST12345",
            "platform": "YouTube",
            "title": "Rick Astley - Never Gonna Give You Up",
            "duration": 212,
            "bytes": len(fake_file.read_bytes()),
            "video_path": str(fake_file),
        }
    monkeypatch.setattr(PublicVideoLinkDownloader, "download", fake_download)

    body = b'{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "confirmed_rights": true, "requested_asset": "video"}'
    resp = client.post(
        "/internal/v1/free-tools/downloader/download",
        content=body,
        headers=_headers("POST", "/internal/v1/free-tools/downloader/download", body, actor_id="1001"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["job_id"] == "LDLTEST12345"
    assert data["status"] == "ready"
    assert data["delivery_ready"] is True
    assert "/api/v1/tools/downloader/delivery/LDLTEST12345?kind=video" in data["delivery_url"]
    assert data["charged_xu"] == 0
    assert "file_path" not in data
    assert str(tmp_path) not in str(data)

    # 1. Owner Stream Delivery
    deliv_path = "/internal/v1/free-tools/downloader/delivery/LDLTEST12345"
    resp_stream = client.get(
        f"{deliv_path}?kind=video",
        headers=_headers("GET", deliv_path, b"", actor_id="1001"),
    )
    assert resp_stream.status_code == 200
    assert resp_stream.headers["content-type"] == "video/mp4"
    assert b"ftypmp42" in resp_stream.content

    # 2. Mode=meta JSON Delivery
    resp_meta = client.get(
        f"{deliv_path}?kind=video&mode=meta",
        headers=_headers("GET", deliv_path, b"", actor_id="1001"),
    )
    assert resp_meta.status_code == 200
    meta_json = resp_meta.json()
    assert meta_json["ok"] is True
    assert meta_json["job_id"] == "LDLTEST12345"
    assert meta_json["content_type"] == "video/mp4"
    assert meta_json["delivery_ready"] is True
    assert str(tmp_path) not in str(meta_json)

    # 3. Missing Actor Stream Blocked (DELIVERY_ACTOR_REQUIRED)
    resp_missing_stream = client.get(
        f"{deliv_path}?kind=video",
        headers=_headers("GET", deliv_path, b"", actor_id=""),
    )
    assert resp_missing_stream.status_code == 401
    assert resp_missing_stream.json()["error_code"] == "DELIVERY_ACTOR_REQUIRED"

    # 4. Missing Actor Meta Blocked (DELIVERY_ACTOR_REQUIRED)
    resp_missing_meta = client.get(
        f"{deliv_path}?kind=video&mode=meta",
        headers=_headers("GET", deliv_path, b"", actor_id=""),
    )
    assert resp_missing_meta.status_code == 401
    assert resp_missing_meta.json()["error_code"] == "DELIVERY_ACTOR_REQUIRED"

    # 5. Foreign Owner Blocked
    resp_foreign = client.get(
        f"{deliv_path}?kind=video",
        headers=_headers("GET", deliv_path, b"", actor_id="9999"),
    )
    assert resp_foreign.status_code == 403
    assert resp_foreign.json()["error_code"] == "DOWNLOADER_FOREIGN_OWNER_BLOCKED"

    # 6. Stale Artifact Truth (file removed)
    fake_file.unlink()
    resp_stale = client.get(
        f"{deliv_path}?kind=video",
        headers=_headers("GET", deliv_path, b"", actor_id="1001"),
    )
    assert resp_stale.status_code == 404
    assert resp_stale.json()["error_code"] == "DOWNLOADER_STALE_ARTIFACT_TRUTH"


def test_downloader_delivery_missing_actor_stream_blocked(client, tmp_path):
    from services.public_video_link_downloader import PublicVideoLinkDownloader
    fake_file = tmp_path / "stream_actorless.mp4"
    fake_file.write_bytes(b"\x00\x00\x00ftypmp42" + b"\x00" * 64)
    downloader = PublicVideoLinkDownloader()
    downloader._save_job({
        "job_id": "LDLACTORLESS01",
        "user_id": "valid_user_42",
        "video_path": str(fake_file),
        "requested_asset": "video",
    })

    deliv_path = "/internal/v1/free-tools/downloader/delivery/LDLACTORLESS01"
    # Calling with valid HMAC secret but NO actor header/param
    resp = client.get(deliv_path, headers=_headers("GET", deliv_path, b"", actor_id=""))
    assert resp.status_code == 401
    payload = resp.json()
    assert payload["ok"] is False
    assert payload["error_code"] == "DELIVERY_ACTOR_REQUIRED"


def test_downloader_delivery_missing_actor_meta_blocked(client, tmp_path):
    from services.public_video_link_downloader import PublicVideoLinkDownloader
    fake_file = tmp_path / "meta_actorless.mp4"
    fake_file.write_bytes(b"\x00\x00\x00ftypmp42" + b"\x00" * 64)
    downloader = PublicVideoLinkDownloader()
    downloader._save_job({
        "job_id": "LDLACTORLESS02",
        "user_id": "valid_user_42",
        "video_path": str(fake_file),
        "requested_asset": "video",
    })

    deliv_path = "/internal/v1/free-tools/downloader/delivery/LDLACTORLESS02"
    # Calling mode=meta with valid HMAC secret but NO actor header/param
    resp = client.get(f"{deliv_path}?mode=meta", headers=_headers("GET", deliv_path, b"", actor_id=""))
    assert resp.status_code == 401
    payload = resp.json()
    assert payload["ok"] is False
    assert payload["error_code"] == "DELIVERY_ACTOR_REQUIRED"


def test_downloader_handle_delivery_service_isolation(tmp_path):
    from services.free_tools_service import handle_downloader_delivery
    from services.public_video_link_downloader import PublicVideoLinkDownloader

    fake_file = tmp_path / "service_isolation.mp4"
    fake_file.write_bytes(b"content")
    downloader = PublicVideoLinkDownloader()
    job = {
        "job_id": "TEST_ISOLATION_SVC",
        "user_id": "owner_123",
        "video_path": str(fake_file),
        "requested_asset": "video",
    }
    downloader._save_job(job)

    # Missing actor -> 401 DELIVERY_ACTOR_REQUIRED
    ok, res, code = handle_downloader_delivery("TEST_ISOLATION_SVC", actor_id="")
    assert not ok
    assert code == 401
    assert res["error_code"] == "DELIVERY_ACTOR_REQUIRED"

    # Foreign actor -> 403 DOWNLOADER_FOREIGN_OWNER_BLOCKED
    ok, res, code = handle_downloader_delivery("TEST_ISOLATION_SVC", actor_id="foreign_456")
    assert not ok
    assert code == 403
    assert res["error_code"] == "DOWNLOADER_FOREIGN_OWNER_BLOCKED"

    # Matching owner -> 200 meta
    ok, res, code = handle_downloader_delivery("TEST_ISOLATION_SVC", actor_id="owner_123", mode="meta")
    assert ok
    assert code == 200
    assert res["job_id"] == "TEST_ISOLATION_SVC"
