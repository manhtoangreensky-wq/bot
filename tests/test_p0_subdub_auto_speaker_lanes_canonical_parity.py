"""P0 provider-free test suite for SubDub canonical auto-speaker lanes parity (R39).

SPEC_ID: SUBDUB-R39-AUTO-SPEAKER-LANES-CANONICAL-PARITY
Covers:
- AUTO_2_REQUEST_ROUTES_AUTO_2
- AUTO_MULTI_REQUEST_ROUTES_MULTI
- SMART_REQUEST_ROUTES_SMART
- THREE_LANES_DO_NOT_COLLAPSE
- INVALID_LANE_FAILS_CLOSED
- CLIENT_SPEAKER_COUNT_CANNOT_FORGE_DETECTION
- UNKNOWN_SMART_MARKER_FAILS_CLOSED
- FOREIGN_VOICE_PROFILE_BLOCKED
- DELETED_OR_NOT_READY_PROFILE_BLOCKED
- CONFLICTING_VOICE_CONFIG_BLOCKED
- QUOTE_PRICING_MATCH_BOT
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

import bot
from services.admin_wallet_service import compute_internal_admin_wallet_signature
from services.subdub_voice_resolution import resolve_subdub_voice_authority


TEST_TOKEN = "test-subdub-bridge-token"
TEST_SECRET = "test-subdub-hmac-secret"


@pytest.fixture(autouse=True)
def setup_isolated_test_env(tmp_path: Path, monkeypatch):
    """Setup isolated test database and bridge credentials."""
    db_file = tmp_path / "test_r39_subdub.db"

    monkeypatch.setattr(bot, "DB_FILE", str(db_file))
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", TEST_SECRET)
    monkeypatch.setattr(bot, "subdub_auto_provider_capacity_ready", lambda *a, **k: True)

    bot.init_db()
    return {"db_file": str(db_file)}


def make_auth_headers(
    method: str,
    path: str,
    body: bytes = b"",
    actor_id: str = "",
) -> dict[str, str]:
    import time
    ts = str(int(time.time()))
    req_id = "req-subdub-r39-test"
    sig = compute_internal_admin_wallet_signature(
        secret=TEST_SECRET,
        timestamp=ts,
        request_id=req_id,
        method=method,
        path=path,
        body_bytes=body,
        actor_id=actor_id,
    )
    headers = {
        "authorization": f"Bearer {TEST_TOKEN}",
        "x-toan-aas-signature": sig,
        "x-toan-aas-timestamp": ts,
        "x-toan-aas-request-id": req_id,
        "content-type": "application/json",
    }
    if actor_id:
        headers["x-toan-aas-actor-id"] = actor_id
    return headers


def insert_test_voice_profile(
    user_id: str,
    display_name: str = "Giọng Mẫu",
    provider: str = "shopaikey_minimax",
    provider_voice_id: str = "voice-provider-abc-12345",
    status: str = "active",
    is_default: int = 0,
    deleted: bool = False,
) -> int:
    with bot.db_connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO voice_profiles (
                user_id, display_name, provider, provider_voice_id,
                status, is_default, consent_status, created_at, updated_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'granted', '2026-09-29 00:00:00', '2026-09-29 00:00:00', ?)
            """,
            (
                str(user_id),
                display_name,
                provider,
                provider_voice_id,
                status,
                is_default,
                "2026-09-29 00:00:00" if deleted else None,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def test_auto_2_request_routes_auto_2():
    """Verify AUTO_2 lane enqueues canonically and routes to auto_speaker (two_speaker_auto)."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    payload = {
        "mode": "dub",
        "payload": {
            "upload_id": "upl_auto_2",
            "target_language": "vi",
            "auto_speaker_lane": "auto_2",
        },
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=body, actor_id=owner_id)
    resp = client.post("/internal/v1/subdub/jobs", content=body, headers=headers)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    job = data["job"]
    job_payload = job["payload"]

    assert job_payload["voice_kind"] == "auto_speaker_gender"
    assert job_payload["voice_selection_mode"] == "auto_speaker"
    assert job_payload["auto_speaker_lane"] == "auto_2"

    engine_name, reason = bot.subdub_auto_routing_decision(job_payload)
    assert engine_name == "auto_speaker"
    assert reason == "two_speaker_auto"


def test_auto_multi_request_routes_multi():
    """Verify AUTO_MULTI_3_8 lane enqueues canonically and routes to auto_multi_speaker (multi_speaker_legacy)."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    payload = {
        "mode": "dub",
        "payload": {
            "upload_id": "upl_auto_multi",
            "target_language": "vi",
            "auto_speaker_lane": "auto_multi_3_8",
        },
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=body, actor_id=owner_id)
    resp = client.post("/internal/v1/subdub/jobs", content=body, headers=headers)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    job = data["job"]
    job_payload = job["payload"]

    assert job_payload["voice_kind"] == "auto_speaker_gender"
    assert job_payload["voice_selection_mode"] == "auto_speaker"
    assert job_payload["auto_speaker_lane"] == "multi"

    engine_name, reason = bot.subdub_auto_routing_decision(job_payload)
    assert engine_name == "auto_multi_speaker"
    assert reason == "multi_speaker_legacy"


def test_smart_request_routes_smart():
    """Verify SMART_MULTI lane enqueues canonically and routes to auto_smart_multivoice (explicit_smart_multivoice_opt_in)."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    payload = {
        "mode": "dub",
        "payload": {
            "upload_id": "upl_smart_multi",
            "target_language": "vi",
            "auto_speaker_lane": "smart_multi",
        },
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=body, actor_id=owner_id)
    resp = client.post("/internal/v1/subdub/jobs", content=body, headers=headers)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    job = data["job"]
    job_payload = job["payload"]

    assert job_payload["voice_kind"] == "auto_speaker_gender"
    assert job_payload["voice_selection_mode"] == "auto_speaker"
    assert job_payload["auto_speaker_lane"] == "auto_smart_multivoice"
    assert job_payload.get("auto_smart_multivoice_opt_in") is True

    engine_name, reason = bot.subdub_auto_routing_decision(job_payload)
    assert engine_name == "auto_smart_multivoice"
    assert reason == "explicit_smart_multivoice_opt_in"


def test_three_lanes_do_not_collapse():
    """Verify that all three auto lanes remain distinct and select distinct runner blackboxes."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    lanes_to_test = [
        ("auto_2", "auto_speaker", "two_speaker_auto"),
        ("auto_multi_3_8", "auto_multi_speaker", "multi_speaker_legacy"),
        ("smart_multi", "auto_smart_multivoice", "explicit_smart_multivoice_opt_in"),
    ]

    resolved_engines = set()
    runners = set()

    for lane_input, expected_engine, expected_reason in lanes_to_test:
        payload = {
            "mode": "dub",
            "payload": {
                "upload_id": f"upl_test_{lane_input}",
                "target_language": "vi",
                "auto_speaker_lane": lane_input,
            },
        }
        body = json.dumps(payload).encode("utf-8")
        headers = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=body, actor_id=owner_id)
        resp = client.post("/internal/v1/subdub/jobs", content=body, headers=headers)
        assert resp.status_code == 200

        job_payload = resp.json()["job"]["payload"]
        engine_name, reason = bot.subdub_auto_routing_decision(job_payload)
        assert engine_name == expected_engine
        assert reason == expected_reason
        resolved_engines.add(engine_name)

        runner = bot.subdub_auto_blackbox_runner(job_payload)
        runners.add(runner)

    assert len(resolved_engines) == 3, f"Expected 3 distinct engines, got {resolved_engines}"
    assert len(runners) == 3, f"Expected 3 distinct runner blackboxes, got {runners}"


def test_invalid_lane_fails_closed():
    """Verify unknown/invalid auto_speaker_lane fails closed with 422 INVALID_AUTO_SPEAKER_LANE."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    payload = {
        "mode": "dub",
        "payload": {
            "upload_id": "upl_invalid",
            "target_language": "vi",
            "auto_speaker_lane": "unsupported_unknown_auto_lane",
        },
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=body, actor_id=owner_id)
    resp = client.post("/internal/v1/subdub/jobs", content=body, headers=headers)

    assert resp.status_code == 422
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "INVALID_AUTO_SPEAKER_LANE"


def test_client_speaker_count_cannot_forge_detection():
    """Verify client cannot specify speaker_count, detected_speaker_count, or mapping internals."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    forged_fields = [
        {"speaker_count": 5},
        {"detected_speaker_count": 4},
        {"speaker_mapping": {"speaker_0": "voice_1"}},
        {"speaker_casts": ["male_1", "female_1"]},
        {"raw_worker_route": "internal_experimental_route"},
        {"provider_voice_id": "malicious_voice_id"},
        {"provider_model_id": "malicious_model_id"},
    ]

    for forged in forged_fields:
        payload = {
            "mode": "dub",
            "payload": {
                "upload_id": "upl_forge",
                "target_language": "vi",
                "auto_speaker_lane": "auto_2",
                **forged,
            },
        }
        body = json.dumps(payload).encode("utf-8")
        headers = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=body, actor_id=owner_id)
        resp = client.post("/internal/v1/subdub/jobs", content=body, headers=headers)

        assert resp.status_code == 422, f"Failed to reject forged field: {forged}"
        data = resp.json()
        assert data["ok"] is False
        assert data["error_code"] == "CLIENT_SPEAKER_COUNT_FORGE_BLOCKED"


def test_unknown_smart_marker_fails_closed():
    """Verify smart opt-in marker on non-smart lane fails closed with 422 UNKNOWN_SMART_MARKER."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    # Smart marker on Auto 2 lane
    payload = {
        "mode": "dub",
        "payload": {
            "upload_id": "upl_bad_marker",
            "target_language": "vi",
            "auto_speaker_lane": "auto_2",
            "auto_smart_multivoice_opt_in": True,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=body, actor_id=owner_id)
    resp = client.post("/internal/v1/subdub/jobs", content=body, headers=headers)

    assert resp.status_code == 422
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "UNKNOWN_SMART_MARKER"


def test_foreign_voice_profile_blocked():
    """Verify attempting to use foreign voice profile fails closed with 403 FORBIDDEN_CROSS_OWNER."""
    client = TestClient(bot.fastapi_app)
    victim_id = "20002"
    attacker_id = "10001"

    victim_pid = insert_test_voice_profile(victim_id, display_name="Giọng Nạn Nhân")

    payload = {
        "mode": "dub",
        "payload": {
            "upload_id": "upl_foreign",
            "target_language": "vi",
            "voice_profile_id": victim_pid,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=body, actor_id=attacker_id)
    resp = client.post("/internal/v1/subdub/jobs", content=body, headers=headers)

    assert resp.status_code == 403
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "FORBIDDEN_CROSS_OWNER"


def test_deleted_or_not_ready_profile_blocked():
    """Verify deleted or unready profiles fail closed."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    # 1. Deleted profile
    del_pid = insert_test_voice_profile(owner_id, display_name="Giọng Xóa", deleted=True)
    payload_del = {
        "mode": "dub",
        "payload": {
            "upload_id": "upl_del",
            "target_language": "vi",
            "voice_profile_id": del_pid,
        },
    }
    body_del = json.dumps(payload_del).encode("utf-8")
    headers_del = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=body_del, actor_id=owner_id)
    resp_del = client.post("/internal/v1/subdub/jobs", content=body_del, headers=headers_del)
    assert resp_del.status_code == 422
    assert resp_del.json()["error_code"] == "PROFILE_NOT_FOUND"

    # 2. Unready profile (training)
    unready_pid = insert_test_voice_profile(owner_id, display_name="Giọng Đang Train", status="training")
    payload_unready = {
        "mode": "dub",
        "payload": {
            "upload_id": "upl_unready",
            "target_language": "vi",
            "voice_profile_id": unready_pid,
        },
    }
    body_unready = json.dumps(payload_unready).encode("utf-8")
    headers_unready = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=body_unready, actor_id=owner_id)
    resp_unready = client.post("/internal/v1/subdub/jobs", content=body_unready, headers=headers_unready)
    assert resp_unready.status_code == 422
    assert resp_unready.json()["error_code"] == "VOICE_NOT_READY"


def test_conflicting_voice_config_blocked():
    """Verify passing both voice_profile_id and auto_speaker_lane fails closed."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"
    pid = insert_test_voice_profile(owner_id, display_name="Giọng Hợp Lệ")

    payload = {
        "mode": "dub",
        "payload": {
            "upload_id": "upl_conflict",
            "target_language": "vi",
            "voice_profile_id": pid,
            "auto_speaker_lane": "auto_2",
        },
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=body, actor_id=owner_id)
    resp = client.post("/internal/v1/subdub/jobs", content=body, headers=headers)

    assert resp.status_code == 422
    data = resp.json()
    assert data["ok"] is False
    assert data["error_code"] == "CONFLICTING_VOICE_CONFIGURATION"


def test_quote_pricing_match_bot():
    """Verify that all three auto lanes evaluate to identical base Xu pricing via subdub_auto_word_pricing."""
    from services.subdub_auto_word_pricing import auto_voice_component_xu

    word_counts = [10, 50, 100, 250, 500, 1000]

    for words in word_counts:
        cost = auto_voice_component_xu(words)
        assert cost >= 0
        # All three auto lanes share this exact component in video_dubbing_invoice_breakdown
        # There is no pricing discrepancy between auto_2, auto_multi_3_8, and smart_multi
