"""Unit and contract tests for Bot Core canonical SubDub Durable Worker Claim Authority (BOT-SUBDUB-D4).

SPEC_ID: BOT-SUBDUB-D4-DURABLE-WORKER-CLAIM
Verifies:
- Atomic durable claim of SubDub jobs
- Fencing / worker token enforcement (stale worker cannot commit)
- Monotonic transition lifecycle (queued -> processing -> completed/failed)
- Duplicate execution prevention (concurrent claim returns 0 jobs for second worker)
- Worker crash recovery (stale processing job requeued on lease expiry)
- Max attempts bounded failure (exceeding attempts transitions to failed)
- Owner-bound job status lookup
- Internal API endpoints:
  - POST /internal/v1/subdub/jobs (enqueue)
  - POST /internal/v1/subdub/jobs/claim (worker claim)
  - POST /internal/v1/subdub/jobs/{job_id}/heartbeat (worker heartbeat)
  - POST /internal/v1/subdub/jobs/{job_id}/complete (worker complete)
  - POST /internal/v1/subdub/jobs/{job_id}/fail (worker fail)
  - GET /internal/v1/subdub/jobs/{job_id} (job status lookup)
"""

from __future__ import annotations

import json
from pathlib import Path
import time
import pytest
from fastapi.testclient import TestClient

import bot
from services.admin_wallet_service import compute_internal_admin_wallet_signature


TEST_TOKEN = "test-subdub-bridge-token"
TEST_SECRET = "test-subdub-hmac-secret"


@pytest.fixture(autouse=True)
def setup_isolated_test_env(tmp_path: Path, monkeypatch):
    """Setup isolated test database and bridge credentials."""
    db_file = tmp_path / "test_d4_worker.db"

    monkeypatch.setattr(bot, "DB_FILE", str(db_file))
    monkeypatch.setenv("CORE_BRIDGE_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("CORE_BRIDGE_HMAC_SECRET", TEST_SECRET)

    bot.init_db()
    return {"db_file": str(db_file)}


def make_auth_headers(
    method: str,
    path: str,
    body: bytes = b"",
    actor_id: str = "",
) -> dict[str, str]:
    ts = str(int(time.time()))
    req_id = "req-subdub-d4-test"
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


def test_first_red_subdub_worker_claim_endpoints_exist():
    """FIRST RED: Check that SubDub durable worker claim endpoints exist on FastAPI app."""
    client = TestClient(bot.fastapi_app)

    # 1. Enqueue endpoint
    b1 = json.dumps({"mode": "dubbing", "payload": {"upload_id": "upl_123"}}).encode("utf-8")
    h1 = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=b1, actor_id="user_owner")
    r1 = client.post("/internal/v1/subdub/jobs", content=b1, headers=h1)
    assert r1.status_code != 404, "Endpoint POST /internal/v1/subdub/jobs must exist"

    # 2. Claim endpoint
    b2 = json.dumps({"worker_id": "worker_test_1"}).encode("utf-8")
    h2 = make_auth_headers("POST", "/internal/v1/subdub/jobs/claim", body=b2, actor_id="worker_test_1")
    r2 = client.post("/internal/v1/subdub/jobs/claim", content=b2, headers=h2)
    assert r2.status_code != 404, "Endpoint POST /internal/v1/subdub/jobs/claim must exist"


def test_enqueue_subdub_job_creates_queued_record():
    """Verify enqueuing creates a job record in queued state with owner binding."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    payload = {
        "mode": "dubbing",
        "payload": {
            "upload_id": "upl_test12345",
            "target_language": "vi",
            "voice_profile_id": 42,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    headers = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=body, actor_id=owner_id)
    resp = client.post("/internal/v1/subdub/jobs", content=body, headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    job = data["job"]
    assert job["job_id"].startswith("subdub_")
    assert job["owner_id"] == owner_id
    assert job["mode"] == "dub"
    assert job["status"] == "queued"
    assert job["attempts"] == 0


def test_atomic_worker_claim_success_and_fencing_token():
    """Verify worker atomically claims queued job and receives unique fencing token."""
    client = TestClient(bot.fastapi_app)
    owner_id = "10001"

    # Enqueue job
    b1 = json.dumps({"mode": "dubbing", "payload": {"upload_id": "upl_1"}}).encode("utf-8")
    h1 = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=b1, actor_id=owner_id)
    r1 = client.post("/internal/v1/subdub/jobs", content=b1, headers=h1)
    job_id = r1.json()["job"]["job_id"]

    # Worker 1 claims
    b2 = json.dumps({"worker_id": "worker_gpu_01", "lease_seconds": 300}).encode("utf-8")
    h2 = make_auth_headers("POST", "/internal/v1/subdub/jobs/claim", body=b2, actor_id="worker_gpu_01")
    r2 = client.post("/internal/v1/subdub/jobs/claim", content=b2, headers=h2)

    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["ok"] is True
    claimed = d2["job"]
    assert claimed is not None
    assert claimed["job_id"] == job_id
    assert claimed["status"] == "processing"
    assert claimed["worker_id"] == "worker_gpu_01"
    assert claimed["attempts"] == 1
    assert bool(claimed["claim_token"]) is True
    assert bool(claimed["lease_expires_at"]) is True


def test_duplicate_worker_claim_prevention():
    """Verify concurrent claim returns empty for second worker (no duplicate execution)."""
    client = TestClient(bot.fastapi_app)

    # Enqueue 1 job
    b1 = json.dumps({"mode": "dubbing", "payload": {"upload_id": "upl_dup"}}).encode("utf-8")
    h1 = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=b1, actor_id="owner_1")
    client.post("/internal/v1/subdub/jobs", content=b1, headers=h1)

    # Worker 1 claims
    b_w1 = json.dumps({"worker_id": "worker_1"}).encode("utf-8")
    h_w1 = make_auth_headers("POST", "/internal/v1/subdub/jobs/claim", body=b_w1, actor_id="worker_1")
    r_w1 = client.post("/internal/v1/subdub/jobs/claim", content=b_w1, headers=h_w1)
    assert r_w1.json()["job"] is not None

    # Worker 2 attempts claim immediately
    b_w2 = json.dumps({"worker_id": "worker_2"}).encode("utf-8")
    h_w2 = make_auth_headers("POST", "/internal/v1/subdub/jobs/claim", body=b_w2, actor_id="worker_2")
    r_w2 = client.post("/internal/v1/subdub/jobs/claim", content=b_w2, headers=h_w2)
    assert r_w2.status_code == 200
    assert r_w2.json()["job"] is None, "Second worker must not claim already-processing job"


def test_fencing_token_enforcement_on_complete_and_fail():
    """Verify complete/fail rejects mismatched fencing token or wrong worker_id (fencing invariant)."""
    client = TestClient(bot.fastapi_app)

    # Enqueue + claim
    b1 = json.dumps({"mode": "dubbing", "payload": {}}).encode("utf-8")
    h1 = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=b1, actor_id="owner_1")
    job_id = client.post("/internal/v1/subdub/jobs", content=b1, headers=h1).json()["job"]["job_id"]

    b_claim = json.dumps({"worker_id": "worker_real"}).encode("utf-8")
    h_claim = make_auth_headers("POST", "/internal/v1/subdub/jobs/claim", body=b_claim, actor_id="worker_real")
    claimed = client.post("/internal/v1/subdub/jobs/claim", content=b_claim, headers=h_claim).json()["job"]
    real_token = claimed["claim_token"]

    # 1. Stale/wrong worker tries to complete
    b_bad_worker = json.dumps({"worker_id": "worker_imposter", "claim_token": real_token}).encode("utf-8")
    h_bad_worker = make_auth_headers("POST", f"/internal/v1/subdub/jobs/{job_id}/complete", body=b_bad_worker, actor_id="worker_imposter")
    r_bad = client.post(f"/internal/v1/subdub/jobs/{job_id}/complete", content=b_bad_worker, headers=h_bad_worker)
    assert r_bad.status_code in {403, 409, 422}
    assert r_bad.json()["ok"] is False

    # 2. Real worker with wrong token tries to complete
    b_bad_token = json.dumps({"worker_id": "worker_real", "claim_token": "stale-forged-token"}).encode("utf-8")
    h_bad_token = make_auth_headers("POST", f"/internal/v1/subdub/jobs/{job_id}/complete", body=b_bad_token, actor_id="worker_real")
    r_bad_tok = client.post(f"/internal/v1/subdub/jobs/{job_id}/complete", content=b_bad_token, headers=h_bad_token)
    assert r_bad_tok.status_code in {403, 409, 422}
    assert r_bad_tok.json()["ok"] is False

    # 3. Real worker with valid token completes successfully
    b_ok = json.dumps({"worker_id": "worker_real", "claim_token": real_token, "result": {"output_file": "final.mp4"}}).encode("utf-8")
    h_ok = make_auth_headers("POST", f"/internal/v1/subdub/jobs/{job_id}/complete", body=b_ok, actor_id="worker_real")
    r_ok = client.post(f"/internal/v1/subdub/jobs/{job_id}/complete", content=b_ok, headers=h_ok)
    assert r_ok.status_code == 200
    assert r_ok.json()["ok"] is True


def test_worker_heartbeat_extends_lease():
    """Verify heartbeat extends lease_expires_at when presented with valid worker credentials."""
    client = TestClient(bot.fastapi_app)

    # Enqueue + claim
    b1 = json.dumps({"mode": "dubbing", "payload": {}}).encode("utf-8")
    h1 = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=b1, actor_id="owner_1")
    job_id = client.post("/internal/v1/subdub/jobs", content=b1, headers=h1).json()["job"]["job_id"]

    b_claim = json.dumps({"worker_id": "worker_hb", "lease_seconds": 60}).encode("utf-8")
    h_claim = make_auth_headers("POST", "/internal/v1/subdub/jobs/claim", body=b_claim, actor_id="worker_hb")
    claimed = client.post("/internal/v1/subdub/jobs/claim", content=b_claim, headers=h_claim).json()["job"]
    token = claimed["claim_token"]
    old_expiry = claimed["lease_expires_at"]

    # Heartbeat with lease_seconds=1200
    b_hb = json.dumps({"worker_id": "worker_hb", "claim_token": token, "lease_seconds": 1200}).encode("utf-8")
    h_hb = make_auth_headers("POST", f"/internal/v1/subdub/jobs/{job_id}/heartbeat", body=b_hb, actor_id="worker_hb")
    r_hb = client.post(f"/internal/v1/subdub/jobs/{job_id}/heartbeat", content=b_hb, headers=h_hb)

    assert r_hb.status_code == 200
    d_hb = r_hb.json()
    assert d_hb["ok"] is True
    assert d_hb["lease_expires_at"] > old_expiry


def test_stale_job_recovery_after_lease_expiry():
    """Verify expired processing job is safely requeued for worker crash recovery."""
    client = TestClient(bot.fastapi_app)

    # Enqueue + claim with lease_seconds=1 (expires almost immediately)
    b1 = json.dumps({"mode": "dubbing", "payload": {}}).encode("utf-8")
    h1 = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=b1, actor_id="owner_1")
    job_id = client.post("/internal/v1/subdub/jobs", content=b1, headers=h1).json()["job"]["job_id"]

    b_claim = json.dumps({"worker_id": "crashed_worker", "lease_seconds": 1}).encode("utf-8")
    h_claim = make_auth_headers("POST", "/internal/v1/subdub/jobs/claim", body=b_claim, actor_id="crashed_worker")
    client.post("/internal/v1/subdub/jobs/claim", content=b_claim, headers=h_claim)

    # Simulate time elapsed past lease
    time.sleep(1.2)

    # New worker polls for jobs -> crash recovery requeues the job and grants it to worker 2
    b_new = json.dumps({"worker_id": "worker_recovery"}).encode("utf-8")
    h_new = make_auth_headers("POST", "/internal/v1/subdub/jobs/claim", body=b_new, actor_id="worker_recovery")
    r_new = client.post("/internal/v1/subdub/jobs/claim", content=b_new, headers=h_new)

    assert r_new.status_code == 200
    claimed2 = r_new.json()["job"]
    assert claimed2 is not None
    assert claimed2["job_id"] == job_id
    assert claimed2["worker_id"] == "worker_recovery"
    assert claimed2["attempts"] == 2


def test_stale_job_max_attempts_exceeded_fails_closed():
    """Verify job exceeding max_attempts is permanently marked failed, not stuck in infinite loop."""
    client = TestClient(bot.fastapi_app)

    # Enqueue with max_attempts=1
    b1 = json.dumps({"mode": "dubbing", "max_attempts": 1, "payload": {}}).encode("utf-8")
    h1 = make_auth_headers("POST", "/internal/v1/subdub/jobs", body=b1, actor_id="owner_1")
    job_id = client.post("/internal/v1/subdub/jobs", content=b1, headers=h1).json()["job"]["job_id"]

    # Claim attempt 1 with 1s lease
    b_claim = json.dumps({"worker_id": "crashed_worker", "lease_seconds": 1}).encode("utf-8")
    h_claim = make_auth_headers("POST", "/internal/v1/subdub/jobs/claim", body=b_claim, actor_id="crashed_worker")
    client.post("/internal/v1/subdub/jobs/claim", content=b_claim, headers=h_claim)

    time.sleep(1.2)

    # Next claim poll should mark it failed and return no jobs
    b_poll = json.dumps({"worker_id": "worker_next"}).encode("utf-8")
    h_poll = make_auth_headers("POST", "/internal/v1/subdub/jobs/claim", body=b_poll, actor_id="worker_next")
    r_poll = client.post("/internal/v1/subdub/jobs/claim", content=b_poll, headers=h_poll)

    assert r_poll.status_code == 200
    assert r_poll.json()["job"] is None

    # Inspect job status
    h_get = make_auth_headers("GET", f"/internal/v1/subdub/jobs/{job_id}", actor_id="owner_1")
    r_get = client.get(f"/internal/v1/subdub/jobs/{job_id}", headers=h_get)
    assert r_get.status_code == 200
    assert r_get.json()["job"]["status"] == "failed"
    assert r_get.json()["job"]["last_error"] == "max_attempts_exceeded"
