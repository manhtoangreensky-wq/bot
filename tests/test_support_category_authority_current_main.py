import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import bot
from services.admin_wallet_service import compute_internal_admin_wallet_signature


TEST_TOKEN = "test-support-bridge-token"
TEST_SECRET = "test-support-hmac-secret"


@pytest.fixture(autouse=True)
def isolated_support_db(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(bot, "DB_FILE", str(tmp_path / "support.db"))
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", TEST_SECRET)
    bot.init_db()


def _headers(body: bytes, actor_id: str = "10001"):
    timestamp = str(int(time.time()))
    request_id = f"category-authority-{time.time_ns()}"
    signature = compute_internal_admin_wallet_signature(
        secret=TEST_SECRET,
        timestamp=timestamp,
        request_id=request_id,
        method="POST",
        path="/internal/v1/support/tickets",
        body_bytes=body,
        actor_id=actor_id,
    )
    return {
        "Authorization": f"Bearer {TEST_TOKEN}",
        "X-TOAN-AAS-Signature": signature,
        "X-TOAN-AAS-Timestamp": timestamp,
        "X-TOAN-AAS-Request-ID": request_id,
        "X-TOAN-AAS-Actor-ID": actor_id,
        "Content-Type": "application/json",
    }


@pytest.mark.parametrize("category", ["payment_topup", "refund", "general_support", "other", "billing"])
def test_client_category_is_rejected_by_actual_support_endpoint(category):
    payload = {
        "subject": "Client category authority",
        "detail": "The client must not choose the support category.",
        "idempotency_key": f"category-authority-{category}",
        "category": category,
    }
    body = json.dumps(payload).encode("utf-8")
    response = TestClient(bot.fastapi_app).post(
        "/internal/v1/support/tickets", content=body, headers=_headers(body)
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "CLIENT_AUTHORITY_FIELD_NOT_ALLOWED"


def test_category_is_defaulted_when_client_omits_it():
    payload = {
        "subject": "Default category authority",
        "detail": "The server chooses the category.",
        "idempotency_key": "category-authority-default-001",
    }
    body = json.dumps(payload).encode("utf-8")
    response = TestClient(bot.fastapi_app).post(
        "/internal/v1/support/tickets", content=body, headers=_headers(body)
    )
    assert response.status_code == 200
    assert response.json()["ticket"]["category"] == bot.DEFAULT_SUPPORT_CATEGORY
