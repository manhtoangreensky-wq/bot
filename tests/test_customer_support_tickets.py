"""Unit and contract tests for Bot Core canonical customer support tickets endpoints.

Task: SPEC-P0.BOT.INTERNAL.SUPPORT.TICKETS.ENDPOINT.R1
Verifies:
- GET /internal/v1/support/tickets (authentication, actor-scoped read, pagination limit/offset)
- POST /internal/v1/support/tickets (HMAC auth, schema persistence, idempotency replay, 409 conflict)
- Security: Client authority field rejection (status, priority, admin_note, refund, xu, etc.)
- Normalization: telegram-{uid} canonical prefix handling
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
import pytest
from fastapi.testclient import TestClient

import bot
from services.admin_wallet_service import compute_internal_admin_wallet_signature


TEST_TOKEN = "test-support-bridge-token"
TEST_SECRET = "test-support-hmac-secret"


@pytest.fixture(autouse=True)
def setup_isolated_test_db(tmp_path: Path, monkeypatch):
    """Setup isolated test database and bridge credentials for each test."""
    db_file = tmp_path / "test_support_tickets.db"
    monkeypatch.setattr(bot, "DB_FILE", str(db_file))
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", TEST_SECRET)
    bot.init_db()
    return str(db_file)


def make_auth_headers(
    method: str,
    path: str,
    body: bytes = b"",
    actor_id: str = "",
    token: str = TEST_TOKEN,
    secret: str = TEST_SECRET,
    timestamp: str | None = None,
    request_id: str | None = None,
) -> dict[str, str]:
    """Helper to compute valid canonical HMAC authentication headers."""
    ts = timestamp if timestamp is not None else str(int(time.time()))
    req_id = request_id if request_id is not None else f"req-test-{time.time_ns()}"
    sig = compute_internal_admin_wallet_signature(
        secret=secret,
        timestamp=ts,
        request_id=req_id,
        method=method,
        path=path,
        body_bytes=body,
        actor_id=actor_id,
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "X-TOAN-AAS-Signature": sig,
        "X-TOAN-AAS-Timestamp": ts,
        "X-TOAN-AAS-Request-ID": req_id,
        "Content-Type": "application/json",
    }
    if actor_id:
        headers["X-TOAN-AAS-Actor-ID"] = actor_id
    return headers


# ---------------------------------------------------------------------------
# Section 1: Authentication & Authorization Tests
# ---------------------------------------------------------------------------

def test_support_tickets_unauthenticated_requests():
    client = TestClient(bot.fastapi_app)

    # Missing all auth on GET
    res_get = client.get("/internal/v1/support/tickets?user_id=10001")
    assert res_get.status_code == 401

    # Missing all auth on POST
    res_post = client.post(
        "/internal/v1/support/tickets",
        json={"subject": "Valid Subject", "detail": "Valid detail text", "idempotency_key": "idemp-key-auth-001"},
    )
    assert res_post.status_code == 401


def test_support_tickets_invalid_token_or_signature():
    client = TestClient(bot.fastapi_app)

    # Invalid Bearer Token
    bad_token_headers = make_auth_headers("GET", "/internal/v1/support/tickets", actor_id="10001", token="wrong-token")
    res1 = client.get("/internal/v1/support/tickets?user_id=10001", headers=bad_token_headers)
    assert res1.status_code == 401
    assert res1.json()["error_code"] == "AUTH_INVALID"

    # Invalid HMAC Signature
    headers = make_auth_headers("GET", "/internal/v1/support/tickets", actor_id="10001")
    headers["X-TOAN-AAS-Signature"] = "0" * 64
    res2 = client.get("/internal/v1/support/tickets?user_id=10001", headers=headers)
    assert res2.status_code == 401
    assert res2.json()["error_code"] == "SIGNATURE_INVALID"


def test_support_tickets_missing_or_mismatched_actor_id():
    client = TestClient(bot.fastapi_app)

    # Missing actor_id in headers and query
    headers = make_auth_headers("GET", "/internal/v1/support/tickets", actor_id="")
    res1 = client.get("/internal/v1/support/tickets", headers=headers)
    assert res1.status_code == 401
    assert res1.json()["error_code"] == "ACTOR_ID_REQUIRED"

    # Actor mismatch in GET (header 10001 vs query 10002)
    headers2 = make_auth_headers("GET", "/internal/v1/support/tickets", actor_id="10001")
    res2 = client.get("/internal/v1/support/tickets?user_id=10002", headers=headers2)
    assert res2.status_code == 401
    assert res2.json()["error_code"] == "ACTOR_ID_MISMATCH"

    # Actor mismatch in POST (header 10001 vs body user_id 10002)
    payload = {
        "user_id": "10002",
        "subject": "Mismatch Test",
        "detail": "Detail for mismatch test",
        "idempotency_key": "idemp-key-mismatch-001",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers3 = make_auth_headers("POST", "/internal/v1/support/tickets", body=body_bytes, actor_id="10001")
    res3 = client.post("/internal/v1/support/tickets", content=body_bytes, headers=headers3)
    assert res3.status_code == 401
    assert res3.json()["error_code"] == "ACTOR_ID_MISMATCH"


# ---------------------------------------------------------------------------
# Section 2: POST Support Ticket Creation & Idempotency
# ---------------------------------------------------------------------------

def test_post_support_ticket_success_and_fields():
    client = TestClient(bot.fastapi_app)
    actor_id = "10001"
    payload = {
        "user_id": "10001",
        "subject": "Lỗi trừ xu khi tạo video",
        "detail": "Tôi bị trừ 50 xu nhưng tác vụ video bị thất bại, xin vui lòng kiểm tra lại.",
        "idempotency_key": "idemp-create-valid-001",
        "category": "payment_topup",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/support/tickets", body=body_bytes, actor_id=actor_id)

    res = client.post("/internal/v1/support/tickets", content=body_bytes, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["replayed"] is False

    ticket = data["ticket"]
    assert ticket["id"] > 0
    assert ticket["ticket_code"].startswith("TA-") or ticket["ticket_code"].startswith("TMP-")
    assert ticket["user_id"] == "10001"
    assert ticket["category"] == "payment_topup"
    assert ticket["status"] == "new"
    assert ticket["subject"] == payload["subject"]
    assert ticket["detail"] == payload["detail"]
    assert ticket["idempotency_key"] == payload["idempotency_key"]

    expected_hash = hashlib.sha256(f"{payload['subject']}|{payload['detail']}".encode("utf-8")).hexdigest()
    assert ticket["payload_hash"] == expected_hash
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == ticket["id"]


def test_post_support_ticket_idempotency_replay():
    client = TestClient(bot.fastapi_app)
    actor_id = "10001"
    payload = {
        "subject": "Vấn đề tài khoản VIP",
        "detail": "Gói VIP chưa được kích hoạt sau khi chuyển khoản thành công.",
        "idempotency_key": "idemp-replay-key-001",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers1 = make_auth_headers("POST", "/internal/v1/support/tickets", body=body_bytes, actor_id=actor_id)

    # 1. Initial creation
    res1 = client.post("/internal/v1/support/tickets", content=body_bytes, headers=headers1)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["replayed"] is False
    created_id = data1["ticket"]["id"]
    created_code = data1["ticket"]["ticket_code"]

    # 2. Replay with identical payload & idempotency key
    headers2 = make_auth_headers("POST", "/internal/v1/support/tickets", body=body_bytes, actor_id=actor_id)
    res2 = client.post("/internal/v1/support/tickets", content=body_bytes, headers=headers2)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["ok"] is True
    assert data2["replayed"] is True
    assert data2["ticket"]["id"] == created_id
    assert data2["ticket"]["ticket_code"] == created_code

    # Verify only 1 ticket row exists in database
    tickets = bot.list_support_tickets(user_id=actor_id)
    assert len(tickets) == 1
    assert tickets[0]["id"] == created_id


def test_post_support_ticket_idempotency_conflict_409():
    client = TestClient(bot.fastapi_app)
    actor_id = "10001"
    idempotency_key = "idemp-conflict-test-001"

    # First request
    payload1 = {
        "subject": "Yêu cầu hỗ trợ nạp tiền",
        "detail": "Nạp 50k chưa thấy cộng xu.",
        "idempotency_key": idempotency_key,
    }
    body_bytes1 = json.dumps(payload1).encode("utf-8")
    headers1 = make_auth_headers("POST", "/internal/v1/support/tickets", body=body_bytes1, actor_id=actor_id)
    res1 = client.post("/internal/v1/support/tickets", content=body_bytes1, headers=headers1)
    assert res1.status_code == 200

    # Second request with same key but DIFFERENT subject
    payload2 = {
        "subject": "Yêu cầu hỗ trợ kỹ thuật video",
        "detail": "Nạp 50k chưa thấy cộng xu.",
        "idempotency_key": idempotency_key,
    }
    body_bytes2 = json.dumps(payload2).encode("utf-8")
    headers2 = make_auth_headers("POST", "/internal/v1/support/tickets", body=body_bytes2, actor_id=actor_id)
    res2 = client.post("/internal/v1/support/tickets", content=body_bytes2, headers=headers2)
    assert res2.status_code == 409
    assert res2.json()["error_code"] == "IDEMPOTENCY_CONFLICT"

    # Third request with same key but DIFFERENT detail
    payload3 = {
        "subject": "Yêu cầu hỗ trợ nạp tiền",
        "detail": "Khác nội dung chi tiết hoàn toàn.",
        "idempotency_key": idempotency_key,
    }
    body_bytes3 = json.dumps(payload3).encode("utf-8")
    headers3 = make_auth_headers("POST", "/internal/v1/support/tickets", body=body_bytes3, actor_id=actor_id)
    res3 = client.post("/internal/v1/support/tickets", content=body_bytes3, headers=headers3)
    assert res3.status_code == 409
    assert res3.json()["error_code"] == "IDEMPOTENCY_CONFLICT"


# ---------------------------------------------------------------------------
# Section 3: Forbidden Authority Field Enforcement
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("forbidden_field,forbidden_value", [
    ("status", "resolved"),
    ("priority", "urgent"),
    ("assigned_admin", "admin_root"),
    ("assigned_admin_id", "admin_root"),
    ("admin_note", "Self-approved"),
    ("suggested_reply", "OK"),
    ("refund", True),
    ("refund_status", "approved"),
    ("amount", 100000),
    ("credits", 9999),
    ("xu", 9999),
    ("closed_at", "2026-09-23 10:00:00"),
    ("ticket_code", "TK-FORGED-001"),
    ("created_at", "2026-01-01 00:00:00"),
    ("updated_at", "2026-01-01 00:00:00"),
    ("id", 99999),
    ("delta", 500),
    ("balance_after", 1000),
])
def test_post_support_ticket_rejects_forbidden_fields(forbidden_field, forbidden_value):
    client = TestClient(bot.fastapi_app)
    actor_id = "10001"
    payload = {
        "subject": "Normal Subject",
        "detail": "Normal detail content for ticket.",
        "idempotency_key": f"idemp-forbid-{forbidden_field}-01",
        forbidden_field: forbidden_value,
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/support/tickets", body=body_bytes, actor_id=actor_id)

    res = client.post("/internal/v1/support/tickets", content=body_bytes, headers=headers)
    assert res.status_code == 400
    assert res.json()["error_code"] == "CLIENT_AUTHORITY_FIELD_NOT_ALLOWED"


# ---------------------------------------------------------------------------
# Section 4: Input Validation
# ---------------------------------------------------------------------------

def test_post_support_ticket_validation_failures():
    client = TestClient(bot.fastapi_app)
    actor_id = "10001"

    # Subject too short (<3 chars)
    p1 = {"subject": "ab", "detail": "Valid detail", "idempotency_key": "idemp-valid-key-01"}
    b1 = json.dumps(p1).encode("utf-8")
    h1 = make_auth_headers("POST", "/internal/v1/support/tickets", body=b1, actor_id=actor_id)
    r1 = client.post("/internal/v1/support/tickets", content=b1, headers=h1)
    assert r1.status_code == 400
    assert r1.json()["error_code"] == "INVALID_SUBJECT_LENGTH"

    # Detail too short (<3 chars)
    p2 = {"subject": "Valid subject", "detail": "ab", "idempotency_key": "idemp-valid-key-02"}
    b2 = json.dumps(p2).encode("utf-8")
    h2 = make_auth_headers("POST", "/internal/v1/support/tickets", body=b2, actor_id=actor_id)
    r2 = client.post("/internal/v1/support/tickets", content=b2, headers=h2)
    assert r2.status_code == 400
    assert r2.json()["error_code"] == "INVALID_DETAIL_LENGTH"

    # Idempotency key too short (<12 chars)
    p3 = {"subject": "Valid subject", "detail": "Valid detail", "idempotency_key": "short_key"}
    b3 = json.dumps(p3).encode("utf-8")
    h3 = make_auth_headers("POST", "/internal/v1/support/tickets", body=b3, actor_id=actor_id)
    r3 = client.post("/internal/v1/support/tickets", content=b3, headers=h3)
    assert r3.status_code == 400
    assert r3.json()["error_code"] == "INVALID_IDEMPOTENCY_KEY_LENGTH"


# ---------------------------------------------------------------------------
# Section 5: GET Support Tickets List & Scoping & Pagination
# ---------------------------------------------------------------------------

def test_get_support_tickets_scoping_and_pagination():
    client = TestClient(bot.fastapi_app)
    user_a = "20001"
    user_b = "20002"

    # Create 3 tickets for user_a
    for i in range(1, 4):
        p = {
            "subject": f"User A Ticket {i}",
            "detail": f"User A detail description number {i}",
            "idempotency_key": f"idemp-user-a-ticket-{i:03d}",
        }
        b = json.dumps(p).encode("utf-8")
        h = make_auth_headers("POST", "/internal/v1/support/tickets", body=b, actor_id=user_a)
        res = client.post("/internal/v1/support/tickets", content=b, headers=h)
        assert res.status_code == 200

    # Create 2 tickets for user_b
    for i in range(1, 3):
        p = {
            "subject": f"User B Ticket {i}",
            "detail": f"User B detail description number {i}",
            "idempotency_key": f"idemp-user-b-ticket-{i:03d}",
        }
        b = json.dumps(p).encode("utf-8")
        h = make_auth_headers("POST", "/internal/v1/support/tickets", body=b, actor_id=user_b)
        res = client.post("/internal/v1/support/tickets", content=b, headers=h)
        assert res.status_code == 200

    # GET user_a tickets - should return all 3, scoped strictly to user_a
    h_get_a = make_auth_headers("GET", "/internal/v1/support/tickets", actor_id=user_a)
    res_a = client.get(f"/internal/v1/support/tickets?user_id={user_a}", headers=h_get_a)
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert data_a["ok"] is True
    assert len(data_a["items"]) == 3
    for item in data_a["items"]:
        assert item["user_id"] == user_a

    # Pagination: limit=2
    res_a_page1 = client.get(f"/internal/v1/support/tickets?user_id={user_a}&limit=2&offset=0", headers=h_get_a)
    assert res_a_page1.status_code == 200
    assert len(res_a_page1.json()["items"]) == 2

    # Pagination: limit=2, offset=2
    res_a_page2 = client.get(f"/internal/v1/support/tickets?user_id={user_a}&limit=2&offset=2", headers=h_get_a)
    assert res_a_page2.status_code == 200
    assert len(res_a_page2.json()["items"]) == 1

    # GET user_b tickets - should return 2
    h_get_b = make_auth_headers("GET", "/internal/v1/support/tickets", actor_id=user_b)
    res_b = client.get(f"/internal/v1/support/tickets?user_id={user_b}", headers=h_get_b)
    assert res_b.status_code == 200
    assert len(res_b.json()["items"]) == 2
    for item in res_b.json()["items"]:
        assert item["user_id"] == user_b


# ---------------------------------------------------------------------------
# Section 6: Canonical User ID Prefix Normalization (telegram-{uid})
# ---------------------------------------------------------------------------

def test_support_tickets_canonical_telegram_prefix_normalization():
    client = TestClient(bot.fastapi_app)
    raw_uid = "30001"
    prefixed_actor = f"telegram-{raw_uid}"

    # POST ticket using telegram-30001 actor_id
    payload = {
        "user_id": raw_uid,
        "subject": "Telegram Prefix Test",
        "detail": "Testing prefix normalization on ticket creation",
        "idempotency_key": "idemp-telegram-prefix-001",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    # Headers bound to raw_uid ("30001")
    headers = make_auth_headers("POST", "/internal/v1/support/tickets", body=body_bytes, actor_id=raw_uid)
    headers["X-TOAN-AAS-Actor-ID"] = prefixed_actor

    res = client.post("/internal/v1/support/tickets", content=body_bytes, headers=headers)
    assert res.status_code == 200
    ticket = res.json()["ticket"]
    assert ticket["user_id"] == raw_uid

    # GET ticket using query param canonical_user_id=telegram-30001
    headers_get = make_auth_headers("GET", "/internal/v1/support/tickets", actor_id=raw_uid)
    headers_get["X-TOAN-AAS-Actor-ID"] = prefixed_actor
    res_get = client.get(f"/internal/v1/support/tickets?canonical_user_id={prefixed_actor}", headers=headers_get)
    assert res_get.status_code == 200
    items = res_get.json()["items"]
    assert len(items) == 1
    assert items[0]["user_id"] == raw_uid
