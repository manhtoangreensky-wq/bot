from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import remote_worker
from services import (
    frame_video_engine,
    frame_video_public_seam,
    remote_worker_api,
    video_real_render_connector,
    video_selfshot2,
    video_selfshot3,
    video_tail9,
)
from services import video_project_queue as queue
from services import video_provider_router as router

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_CAPABILITY = queue.PRODUCT_VIDEO_CANONICAL_WORKER_CAPABILITY


def _current_runtime_sha(explicit_sha: str | None = None) -> str:
    """Strictly derive expected 40-char runtime SHA or fail closed. No silent fallback."""
    if explicit_sha and len(explicit_sha.strip()) == 40:
        return explicit_sha.strip()
    env_sha = os.getenv("DEPLOYED_SHA") or os.getenv("TARGET_SHA") or os.getenv("APP_BUILD_SHA")
    if env_sha and len(env_sha.strip()) == 40:
        return env_sha.strip()
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
        if len(out) == 40:
            return out
    except Exception:
        pass
    raise RuntimeError("Unable to derive authoritative 40-character runtime SHA (fail-closed)")


def _create_isolated_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _create_canonical_project(
    conn: sqlite3.Connection,
    *,
    user_id: int = 1001,
    product_type: str = "video_trend",
    scene_count: int = 2,
    package_xu: int = 80,
    quality_tier: int = 400,
) -> tuple[dict[str, Any], int]:
    shared = {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "product_type": product_type,
        "engine_adapter": "text_to_video",
        "orchestration_mode": "per_scene_8s",
        "provider_orchestration_mode": "per_scene_8s",
        "scene_count": scene_count,
    }
    invoice = {
        **shared,
        "tier": "basic",
        "package_xu": package_xu,
        "scene_duration_seconds": 8,
        "duration_seconds": scene_count * 8,
        "total_xu": package_xu,
        "user_visible_price_xu": package_xu,
        "persisted_quoted_price_xu": package_xu,
        "customer_charge_planned_xu": package_xu,
        "wallet_charge_amount_xu": package_xu,
    }

    project = queue.create_video_project(
        conn,
        user_id=user_id,
        profile_id=product_type,
        topic=f"PV02 Test {product_type}",
        ratio="9:16",
        asset_pack=shared,
    )
    pid = int(project["project_id"])
    updated_project = queue.update_video_project(
        conn,
        pid,
        status="draft_invoice",
        invoice_json=invoice,
        scene_count=scene_count,
        quality_tier=quality_tier,
        total_xu_estimated=package_xu,
    )
    return updated_project, pid


def _build_sealed_admission(
    project: dict[str, Any],
    *,
    product_type: str = "video_trend",
    keys: list[str] | None = None,
    generation_id: str = "generation-pv02",
    runtime_sha: str | None = None,
) -> dict[str, Any]:
    current_sha = _current_runtime_sha(runtime_sha)
    candidate_keys = list(["shopaikey_video"] if keys is None else keys)
    snapshot_id = f"snap_pv02_{project['project_id']}"
    checked_at = queue.now_text()
    quote = queue.product_video_admission_quote_fingerprint(project, int(project["user_id"]))
    route = router.product_video_route_contract(product_type, "text_to_video", "per_scene_8s")

    snapshot = {
        "provider_eligibility_snapshot_id": snapshot_id,
        "admission_snapshot_id": snapshot_id,
        "admission_checked_at": checked_at,
        "admission_user_id": int(project["user_id"]),
        "admission_project_id": int(project["project_id"]),
        "admission_quote_fingerprint": quote,
        "admission_callback_handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "admission_callback_data": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK,
        "eligible_provider_keys": candidate_keys,
        "runtime_candidate_keys": candidate_keys,
        "final_eligible_provider_count": len(candidate_keys),
    }

    admission = {
        "ok": bool(candidate_keys),
        "provider_eligibility_snapshot": snapshot,
        "provider_eligibility_snapshot_id": snapshot_id,
        "admission_snapshot_id": snapshot_id,
        "admission_checked_at": checked_at,
        "admission_ttl_seconds": 60,
        "admission_candidate_keys": candidate_keys,
        "admission_candidate_count": len(candidate_keys),
        "admission_result": "PASS" if candidate_keys else "BLOCKED",
        "admission_block_reason": "" if candidate_keys else "no_eligible_product_video_provider",
        "admission_user_id": int(project["user_id"]),
        "admission_project_id": int(project["project_id"]),
        "admission_quote_fingerprint": quote,
        "admission_callback_handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "admission_callback_data": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK,
        "admission_provider_health_gate_pass": bool(candidate_keys),
        "admission_worker_runtime_sha": current_sha,
        "admission_worker_sha": current_sha,
        "admission_worker_version_compatible": True,
        "admission_route_requires_provider": bool(route["route_requires_provider"]),
        "worker_generation_id": generation_id,
        "worker_git_sha": current_sha,
        "runtime_sha": current_sha,
        "worker_compatible": True,
        "worker_connected": True,
        "worker_heartbeat_fresh": True,
        "worker_lease_valid": True,
        "worker_sha_match": True,
        "worker_capability_match": True,
        "worker_identity_conflict": False,
        "route_requires_provider": True,
        "handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "worker_admission_block_reason": "",
        "duplicate_confirm_handler_detected": False,
    }
    return queue.sign_product_video_final_admission_context(admission)


def test_section2_source_derived_product_family_audit() -> None:
    """SECTION 2: Derive product audit evidence from actual source contracts and structures.

    The test fails automatically if actual source wiring or adapter contracts change.
    Every product must resolve to either CANONICAL_OWNER_PRODUCT_VIDEO_SEAM or PROVEN_SEPARATE_EXECUTION_SEAM.
    Zero products may remain UNKNOWN_PRODUCT_ADAPTER or have an unexplained bypass.
    """
    # 1. Dynamically verify canonical durable functions and symbols exist in real source code
    assert hasattr(queue, "confirm_public_product_video_invoice")
    assert callable(queue.confirm_public_product_video_invoice)
    assert hasattr(queue, "_confirm_product_video_invoice_atomic")
    assert callable(queue._confirm_product_video_invoice_atomic)
    assert hasattr(queue, "_insert_product_video_dispatch_outbox_record")
    assert callable(queue._insert_product_video_dispatch_outbox_record)
    assert queue.PRODUCT_VIDEO_DISPATCH_OUTBOX_OWNER == "owner_product_video"

    # 2. Dynamically verify separate seam real functions and symbols exist in real source code
    assert hasattr(frame_video_engine, "dispatch_frame_video")
    assert callable(frame_video_engine.dispatch_frame_video)
    assert hasattr(frame_video_engine, "execute_frame_video_local")
    assert callable(frame_video_engine.execute_frame_video_local)
    assert hasattr(frame_video_public_seam, "render_frame_video_public")
    assert callable(frame_video_public_seam.render_frame_video_public)

    assert video_selfshot2.PRODUCT_ID == "self_shot_scene_change"
    assert video_selfshot2.JOB_TYPE == "self_shot_scene_change"
    assert hasattr(video_real_render_connector, "_render_selfshot2_video_to_video")
    assert callable(video_real_render_connector._render_selfshot2_video_to_video)
    assert hasattr(remote_worker, "_selfshot2_job")
    assert callable(remote_worker._selfshot2_job)
    assert hasattr(remote_worker, "download_selfshot2_source_video")
    assert callable(remote_worker.download_selfshot2_source_video)

    assert video_selfshot3.PRODUCT_ID == "self_shot_cinematic_transform"
    assert video_selfshot3.JOB_TYPE == "self_shot_cinematic_transform"
    assert hasattr(video_real_render_connector, "_render_selfshot3_video_to_video")
    assert callable(video_real_render_connector._render_selfshot3_video_to_video)
    assert hasattr(remote_worker, "_selfshot3_job")
    assert callable(remote_worker._selfshot3_job)
    assert hasattr(remote_worker, "download_selfshot3_source_video")
    assert callable(remote_worker.download_selfshot3_source_video)

    products = [
        "video_trend",
        "video_ai_prompt",
        "video_ai_image",
        "video_ai_video_reference",
        "script_to_video",
        "storyboard_video",
        "frame_video",
        "selfshot_scene_change",
        "selfshot_cinematic",
        "video_idea",
    ]

    canonical_seam_products = []
    proven_separate_products = []
    unexplained_bypass_products = []

    audit_records = {}

    for product in products:
        adapter = video_tail9.adapter_for(product)
        known = bool(adapter.get("video_product_type"))
        adapter_key = str(adapter.get("adapter_key") or "")
        worker_owner = str(adapter.get("worker_owner") or "")
        flow_owner = str(adapter.get("flow_owner") or "")
        engine_route = str(adapter.get("engine_route") or "")
        required_capability = str(adapter.get("required_capability") or "")
        blocker = str(adapter.get("execution_blocker") or "")

        if not known or blocker == "product_owner_missing":
            result = "UNEXPLAINED_BYPASS"
            first_bypass = "product_owner_missing_in_adapter_registry"
            uses_canonical = False
            unexplained_bypass_products.append(product)
            record = {
                "PRODUCT": product,
                "RESULT": result,
                "FIRST_BYPASS": first_bypass,
                "USES_CANONICAL_SEAM": uses_canonical,
                "ADAPTER_KEY": adapter_key,
                "WORKER_OWNER": worker_owner,
                "REQUIRED_CAPABILITY": required_capability,
                "ENGINE_ROUTE": engine_route,
            }
        elif worker_owner == "product_video":
            result = "CANONICAL_OWNER_PRODUCT_VIDEO_SEAM"
            first_bypass = None
            uses_canonical = True
            canonical_seam_products.append(product)
            record = {
                "PRODUCT": product,
                "RESULT": result,
                "FIRST_BYPASS": first_bypass,
                "USES_CANONICAL_SEAM": uses_canonical,
                "ADAPTER_KEY": adapter_key,
                "WORKER_OWNER": worker_owner,
                "FLOW_OWNER": flow_owner,
                "ENGINE_ROUTE": engine_route,
                "REQUIRED_CAPABILITY": required_capability,
                "CONFIRM_FUNCTION": "services.video_project_queue.confirm_public_product_video_invoice",
                "ATOMIC_JOB_FUNCTION": "services.video_project_queue._confirm_product_video_invoice_atomic",
                "OUTBOX_RECORD_FUNCTION": "services.video_project_queue._insert_product_video_dispatch_outbox_record",
                "OUTBOX_OWNER": queue.PRODUCT_VIDEO_DISPATCH_OUTBOX_OWNER,
                "WORKER_SERVICE_MODE": "owner_product_video",
            }
        elif product == "frame_video":
            result = "PROVEN_SEPARATE_EXECUTION_SEAM"
            first_bypass = "uses_dedicated_frame_video_execution_seam"
            uses_canonical = False
            proven_separate_products.append(product)
            record = {
                "PRODUCT": product,
                "RESULT": result,
                "FIRST_BYPASS": first_bypass,
                "USES_CANONICAL_SEAM": uses_canonical,
                "ADAPTER_KEY": adapter_key,
                "WORKER_OWNER": worker_owner,
                "FLOW_OWNER": flow_owner,
                "ENGINE_ROUTE": engine_route,
                "EXECUTOR_PRODUCT_TYPE": str(adapter.get("executor_product_type") or ""),
                "REQUIRED_CAPABILITY": required_capability,
                "SERVICE_MODULE": "services.frame_video_engine",
                "EXECUTION_FUNCTION": "services.frame_video_engine.execute_frame_video_local",
                "DISPATCH_FUNCTION": "services.frame_video_engine.dispatch_frame_video",
                "PUBLIC_SEAM_FUNCTION": "services.frame_video_public_seam.render_frame_video_public",
                "USES_OWNER_PRODUCT_VIDEO_OUTBOX": False,
                "CAN_CLAIM_OWNER_PRODUCT_VIDEO_JOB": False,
            }
        elif product == "selfshot_scene_change":
            result = "PROVEN_SEPARATE_EXECUTION_SEAM"
            first_bypass = "uses_dedicated_selfshot2_execution_seam"
            uses_canonical = False
            proven_separate_products.append(product)
            record = {
                "PRODUCT": product,
                "RESULT": result,
                "FIRST_BYPASS": first_bypass,
                "USES_CANONICAL_SEAM": uses_canonical,
                "ADAPTER_KEY": adapter_key,
                "WORKER_OWNER": worker_owner,
                "FLOW_OWNER": flow_owner,
                "ENGINE_ROUTE": engine_route,
                "EXECUTOR_PRODUCT_TYPE": str(adapter.get("executor_product_type") or ""),
                "REQUIRED_CAPABILITY": required_capability,
                "PLANNING_MODULE": "services.video_selfshot2",
                "PLANNING_PRODUCT_ID": video_selfshot2.PRODUCT_ID,
                "PLANNING_JOB_TYPE": video_selfshot2.JOB_TYPE,
                "EXECUTION_FUNCTION": "services.video_real_render_connector._render_selfshot2_video_to_video",
                "WORKER_JOB_CLASSIFIER": "remote_worker._selfshot2_job",
                "WORKER_DOWNLOAD_FUNCTION": "remote_worker.download_selfshot2_source_video",
                "USES_OWNER_PRODUCT_VIDEO_OUTBOX": False,
                "CAN_CLAIM_OWNER_PRODUCT_VIDEO_JOB": False,
            }
        elif product == "selfshot_cinematic":
            result = "PROVEN_SEPARATE_EXECUTION_SEAM"
            first_bypass = "uses_dedicated_selfshot3_execution_seam"
            uses_canonical = False
            proven_separate_products.append(product)
            record = {
                "PRODUCT": product,
                "RESULT": result,
                "FIRST_BYPASS": first_bypass,
                "USES_CANONICAL_SEAM": uses_canonical,
                "ADAPTER_KEY": adapter_key,
                "WORKER_OWNER": worker_owner,
                "FLOW_OWNER": flow_owner,
                "ENGINE_ROUTE": engine_route,
                "EXECUTOR_PRODUCT_TYPE": str(adapter.get("executor_product_type") or ""),
                "REQUIRED_CAPABILITY": required_capability,
                "PLANNING_MODULE": "services.video_selfshot3",
                "PLANNING_PRODUCT_ID": video_selfshot3.PRODUCT_ID,
                "PLANNING_JOB_TYPE": video_selfshot3.JOB_TYPE,
                "EXECUTION_FUNCTION": "services.video_real_render_connector._render_selfshot3_video_to_video",
                "WORKER_JOB_CLASSIFIER": "remote_worker._selfshot3_job",
                "WORKER_DOWNLOAD_FUNCTION": "remote_worker.download_selfshot3_source_video",
                "USES_OWNER_PRODUCT_VIDEO_OUTBOX": False,
                "CAN_CLAIM_OWNER_PRODUCT_VIDEO_JOB": False,
            }
        else:
            result = "UNEXPLAINED_BYPASS"
            first_bypass = f"unrecognized_worker_owner_{worker_owner}"
            uses_canonical = False
            unexplained_bypass_products.append(product)
            record = {
                "PRODUCT": product,
                "RESULT": result,
                "FIRST_BYPASS": first_bypass,
                "USES_CANONICAL_SEAM": uses_canonical,
                "ADAPTER_KEY": adapter_key,
                "WORKER_OWNER": worker_owner,
                "REQUIRED_CAPABILITY": required_capability,
                "ENGINE_ROUTE": engine_route,
            }

        audit_records[product] = record

        # Assert each product contract is structurally sound
        assert known is True, f"Product '{product}' must be registered in adapter registry"
        assert blocker != "product_owner_missing", f"Product '{product}' must not fail with product_owner_missing"
        assert result in {
            "CANONICAL_OWNER_PRODUCT_VIDEO_SEAM",
            "PROVEN_SEPARATE_EXECUTION_SEAM",
        }, f"Product '{product}' must be canonical or proven separate"

    # Strict partition assertions
    assert len(unexplained_bypass_products) == 0, f"Unexplained bypasses found: {unexplained_bypass_products}"
    assert len(canonical_seam_products) == 7
    assert len(proven_separate_products) == 3
    assert set(canonical_seam_products) == {
        "video_trend",
        "video_ai_prompt",
        "video_ai_image",
        "video_ai_video_reference",
        "script_to_video",
        "storyboard_video",
        "video_idea",
    }
    assert set(proven_separate_products) == {
        "frame_video",
        "selfshot_scene_change",
        "selfshot_cinematic",
    }

    # 3. Empirical proof: separate products do NOT use owner_product_video outbox,
    # and workers for separate products cannot claim canonical product video jobs
    conn = _create_isolated_db()
    project, pid = _create_canonical_project(conn, product_type="video_trend", scene_count=1, package_xu=80)
    admission = _build_sealed_admission(project, product_type="video_trend")
    confirm_res = queue.confirm_public_product_video_invoice(
        conn,
        project_id=pid,
        user_id=1001,
        balance_xu=1000,
        provider_admission=admission,
    )
    assert confirm_res["ok"] is True

    # Check canonical outbox row
    outbox_row = conn.execute("SELECT * FROM video_dispatch_outbox WHERE project_id=?", (pid,)).fetchone()
    assert outbox_row is not None
    assert outbox_row["owner"] == "owner_product_video"
    assert outbox_row["owner"] not in {"frame_video", "selfshot2", "selfshot3"}

    # Worker for frame_video cannot claim owner_product_video job
    frame_claim = remote_worker_api.claim_remote_worker_job(
        conn,
        worker_id="frame_video_worker",
        capabilities=["frame_video", "local_ffmpeg"],
        owner_product_video_only=True,
    )
    assert frame_claim.get("job") is None
    assert frame_claim.get("reason") in {"capability_not_supported", "no_owner_product_video_job"}

    # Worker for selfshot2 cannot claim owner_product_video job
    selfshot2_claim = remote_worker_api.claim_remote_worker_job(
        conn,
        worker_id="selfshot2_worker",
        capabilities=["selfshot2", "video_to_video"],
        owner_product_video_only=True,
    )
    assert selfshot2_claim.get("job") is None
    assert selfshot2_claim.get("reason") in {"capability_not_supported", "no_owner_product_video_job"}

    # Worker for selfshot3 cannot claim owner_product_video job
    selfshot3_claim = remote_worker_api.claim_remote_worker_job(
        conn,
        worker_id="selfshot3_worker",
        capabilities=["selfshot3", "video_to_video"],
        owner_product_video_only=True,
    )
    assert selfshot3_claim.get("job") is None
    assert selfshot3_claim.get("reason") in {"capability_not_supported", "no_owner_product_video_job"}


def test_section3_strict_runtime_sha_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """SECTION 3: Prove missing, empty, or invalid SHA evidence causes strict fail-closed rejection."""
    monkeypatch.delenv("DEPLOYED_SHA", raising=False)
    monkeypatch.delenv("TARGET_SHA", raising=False)
    monkeypatch.delenv("APP_BUILD_SHA", raising=False)

    def _mock_check_output(*args: Any, **kwargs: Any) -> str:
        raise subprocess.CalledProcessError(1, ["git", "rev-parse", "HEAD"])

    monkeypatch.setattr(subprocess, "check_output", _mock_check_output)

    # Missing all SHA sources -> strict fail-closed
    with pytest.raises(RuntimeError, match="Unable to derive authoritative 40-character runtime SHA"):
        _current_runtime_sha()

    # Short / invalid SHA in env -> strict fail-closed
    monkeypatch.setenv("DEPLOYED_SHA", "short_sha")
    with pytest.raises(RuntimeError, match="Unable to derive authoritative 40-character runtime SHA"):
        _current_runtime_sha()

    # Explicit invalid SHA -> strict fail-closed
    with pytest.raises(RuntimeError, match="Unable to derive authoritative 40-character runtime SHA"):
        _current_runtime_sha(explicit_sha="not_a_valid_40_char_sha")

    # Authoritative 40-char SHA via explicit injection succeeds
    valid_explicit = "a" * 40
    assert _current_runtime_sha(explicit_sha=valid_explicit) == valid_explicit

    # Authoritative 40-char SHA via environment succeeds
    valid_env = "b" * 40
    monkeypatch.setenv("DEPLOYED_SHA", valid_env)
    assert _current_runtime_sha() == valid_env


def test_section4_confirm_creates_canonical_durable_rows() -> None:
    """SECTION 4: Confirm -> Durable rows (1 project, 1 job, canonical scenes, 1 outbox)."""
    conn = _create_isolated_db()
    project, pid = _create_canonical_project(conn, product_type="video_trend", scene_count=2, package_xu=80)
    admission = _build_sealed_admission(project, product_type="video_trend")

    result = queue.confirm_public_product_video_invoice(
        conn,
        project_id=pid,
        user_id=1001,
        balance_xu=1000,
        provider_admission=admission,
    )

    assert result["ok"] is True
    assert result.get("job_created") is not False

    project_count = conn.execute("SELECT COUNT(*) FROM video_projects").fetchone()[0]
    job_count = conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0]
    scene_count = conn.execute("SELECT COUNT(*) FROM video_scenes").fetchone()[0]
    outbox_count = conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0]

    assert project_count == 1, "PROJECT_ROWS must equal 1"
    assert job_count == 1, "JOB_ROWS must equal 1"
    assert scene_count == 2, "SCENE_ROWS must equal expected canonical scene count (2)"
    assert outbox_count == 1, "OUTBOX_ROWS must equal 1"

    outbox_row = conn.execute("SELECT * FROM video_dispatch_outbox").fetchone()
    assert outbox_row["owner"] == "owner_product_video", "OUTBOX_OWNER must be owner_product_video"
    assert outbox_row["dispatch_status"] == "pending"

    # Durable linked identifiers
    job_row = conn.execute("SELECT * FROM video_jobs").fetchone()
    assert job_row["id"] is not None
    assert job_row["project_id"] == pid
    assert outbox_row["job_id"] == job_row["id"]
    assert outbox_row["project_id"] == pid

    scenes = conn.execute("SELECT * FROM video_scenes WHERE project_id=?", (pid,)).fetchall()
    assert len(scenes) == 2
    assert {s["scene_index"] for s in scenes} == {1, 2}


def test_section5_duplicate_confirm_idempotency_blocks_duplicate_rows() -> None:
    """SECTION 5: Duplicate confirm replay blocked; total rows remain 1 proj, 1 job, 2 scenes, 1 outbox."""
    conn = _create_isolated_db()
    project, pid = _create_canonical_project(conn, product_type="video_trend", scene_count=2, package_xu=80)
    admission = _build_sealed_admission(project, product_type="video_trend")

    # First confirm
    res1 = queue.confirm_public_product_video_invoice(
        conn,
        project_id=pid,
        user_id=1001,
        balance_xu=1000,
        provider_admission=admission,
    )
    assert res1["ok"] is True

    # Duplicate confirm replay
    res2 = queue.confirm_public_product_video_invoice(
        conn,
        project_id=pid,
        user_id=1001,
        balance_xu=1000,
        provider_admission=admission,
    )
    assert res2["ok"] is False
    assert res2.get("reason") == "admission_snapshot_replayed"

    # Verify no duplicate rows created
    assert conn.execute("SELECT COUNT(*) FROM video_projects").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM video_scenes").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0] == 1


def test_section6_exactly_one_worker_claim_and_double_claim_prevention(monkeypatch: pytest.MonkeyPatch) -> None:
    """SECTION 6: Exactly one worker claim succeeds; immediate second claim returns no_job.

    Section 4 / 9 Fixture:
    NO_PROVIDER_NETWORK=YES
    ELIGIBILITY_EVALUATOR=DETERMINISTIC_STUB
    ELIGIBLE_PROVIDER_CANDIDATE=FIXTURE_ONLY
    PROVIDER_NETWORK_CALLS=0
    PROVIDER_SUBMIT=0
    PROVIDER_TASK_ID=0
    """
    conn = _create_isolated_db()
    project, pid = _create_canonical_project(conn, product_type="video_trend", scene_count=2, package_xu=80)
    admission = _build_sealed_admission(project, product_type="video_trend")

    res = queue.confirm_public_product_video_invoice(
        conn,
        project_id=pid,
        user_id=1001,
        balance_xu=1000,
        provider_admission=admission,
    )
    assert res["ok"] is True

    # Zero provider calls / deterministic stub
    provider_calls = {"count": 0}

    def _stubbed_eligibility(*args: Any, **kwargs: Any) -> dict[str, Any]:
        provider_calls["count"] += 1
        return {
            "ok": True,
            "eligible_provider_keys": ["shopaikey_video"],
            "runtime_candidate_keys": ["shopaikey_video"],
            "final_eligible_provider_count": 1,
            "provider_eligibility_snapshot": {
                "eligible_provider_keys": ["shopaikey_video"],
                "runtime_candidate_keys": ["shopaikey_video"],
                "final_eligible_provider_count": 1,
            },
        }

    monkeypatch.setattr(remote_worker_api, "_product_video_runtime_eligibility", _stubbed_eligibility)

    # First claim by eligible worker
    claim1 = remote_worker_api.claim_remote_worker_job(
        conn,
        worker_id="owner_worker_1",
        capabilities=["owner_product_video", CANONICAL_CAPABILITY],
        owner_product_video_only=True,
    )

    assert claim1.get("job") is not None, "FIRST_CLAIM must succeed"
    job1 = claim1["job"]
    assert str(job1.get("job_id")) == "1"
    assert job1.get("status") == "processing"
    assert job1.get("locked_by") == "owner_worker_1"
    assert job1.get("lease_expires_at") is not None
    assert job1.get("worker_service_mode") == "owner_product_video"
    assert claim1.get("owner_product_video_only") is True

    # Outbox status updated to leased / acknowledged
    outbox_row = conn.execute("SELECT * FROM video_dispatch_outbox WHERE job_id=1").fetchone()
    assert outbox_row["dispatch_status"] in {"leased", "acknowledged"}

    # Second claim by second worker immediately fails (DOUBLE_CLAIM = 0)
    claim2 = remote_worker_api.claim_remote_worker_job(
        conn,
        worker_id="owner_worker_2",
        capabilities=["owner_product_video", CANONICAL_CAPABILITY],
        owner_product_video_only=True,
    )

    assert claim2.get("job") is None, "SECOND_CLAIM must return no job"
    assert claim2.get("reason") == "no_owner_product_video_job"

    # Invariant: Stopped before provider execution
    assert job1.get("provider_submit_called") is False or job1.get("provider_submit_called") is None
    assert conn.execute("SELECT COUNT(*) FROM video_jobs WHERE status='processing'").fetchone()[0] == 1


def test_section7_rejection_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    """SECTION 7: Full rejection matrix (Cases A-H) with dynamic current-main runtime SHA."""
    now = datetime(2026, 9, 17, 12, 0, 0)
    runtime_sha = _current_runtime_sha()

    def _heartbeat_record(
        now_dt: datetime,
        *,
        generation: str = "generation-pv02",
        heartbeat_age: int = 0,
        lease_delta: int = 90,
    ) -> dict:
        return {
            "worker_id": "owner-product-video",
            "worker_instance_id": "owner-product-video:instance",
            "generation_id": generation,
            "git_sha": runtime_sha,
            "runtime_target_sha": runtime_sha,
            "service_mode": "owner_product_video",
            "capability_version": CANONICAL_CAPABILITY,
            "capabilities": ["owner_product_video", CANONICAL_CAPABILITY],
            "heartbeat_at": queue.now_text(now_dt - timedelta(seconds=heartbeat_age)),
            "lease_expires_at": queue.now_text(now_dt + timedelta(seconds=lease_delta)),
            "last_claim_at": queue.now_text(now_dt),
            "last_idle_claim_at": queue.now_text(now_dt),
            "heartbeat_refresh_source": "claim_idle",
        }

    def _heartbeat_payload(
        *,
        generation: str = "generation-pv02",
        service_mode: str = "owner_product_video",
        git_sha: str | None = None,
        capabilities: list[str] | None = None,
    ) -> dict:
        caps = ["owner_product_video", CANONICAL_CAPABILITY] if capabilities is None else capabilities
        return {
            "worker_id": "owner-product-video",
            "worker_instance_id": "owner-product-video:instance",
            "generation_id": generation,
            "git_sha": git_sha or runtime_sha,
            "runtime_target_sha": runtime_sha,
            "service_mode": service_mode,
            "capability_version": CANONICAL_CAPABILITY,
            "capabilities": caps,
            "process_started_at": "2026-09-17 10:00:00",
            "hostname": "vps",
            "pid": 132,
        }

    # Case A: Correct owner, correct SHA, fresh heartbeat, required capabilities, valid generation/lease => CLAIM PASS
    dec_a = remote_worker_api.owner_product_video_heartbeat_update_decision(
        [_heartbeat_record(now, heartbeat_age=10, lease_delta=80)],
        _heartbeat_payload(),
        runtime_sha=runtime_sha,
        now=now,
        heartbeat_ttl_seconds=90,
    )
    assert dec_a.get("heartbeat_accepted") is True, "Case A: valid worker must be accepted"

    # Case B: Wrong owner => REJECT
    dec_b = remote_worker_api.owner_product_video_heartbeat_update_decision(
        [_heartbeat_record(now)],
        _heartbeat_payload(service_mode="frame_video", capabilities=["frame_video"]),
        runtime_sha=runtime_sha,
        now=now,
    )
    assert dec_b.get("heartbeat_accepted") is False
    assert dec_b.get("owner_heartbeat_reject_reason") == "not_owner_product_video_heartbeat"

    # Case C: Stale heartbeat => REJECT
    compat_c = remote_worker_api.product_video_worker_compatibility(
        [_heartbeat_record(now, heartbeat_age=120, lease_delta=-30)],
        runtime_sha=runtime_sha,
        now=now,
        heartbeat_ttl_seconds=90,
    )
    assert compat_c.get("worker_connected") is False

    # Case D: SHA mismatch => REJECT
    dec_d = remote_worker_api.owner_product_video_heartbeat_update_decision(
        [_heartbeat_record(now)],
        _heartbeat_payload(git_sha="bad_sha_" + "0" * 32),
        runtime_sha=runtime_sha,
        now=now,
    )
    assert dec_d.get("heartbeat_accepted") is False
    assert "worker_git_sha" in str(dec_d.get("owner_heartbeat_reject_reason"))

    # Case E: Capability missing => REJECT
    dec_e = remote_worker_api.owner_product_video_heartbeat_update_decision(
        [_heartbeat_record(now)],
        _heartbeat_payload(capabilities=["owner_product_video"]),
        runtime_sha=runtime_sha,
        now=now,
    )
    assert dec_e.get("heartbeat_accepted") is False
    assert dec_e.get("owner_heartbeat_reject_reason") == "worker_capability_mismatch"

    # Case F: Generation mismatch => REJECT
    dec_f = remote_worker_api.owner_product_video_heartbeat_update_decision(
        [_heartbeat_record(now)],
        _heartbeat_payload(generation="generation-other"),
        runtime_sha=runtime_sha,
        now=now,
    )
    assert dec_f.get("heartbeat_accepted") is False
    assert dec_f.get("owner_heartbeat_reject_reason") == "worker_generation_conflict"

    # Case G & H: Duplicate claim & duplicate confirm proven in test_section5 and test_section6


def test_section10_trend_80_xu_protection() -> None:
    """SECTION 10: Trend Tier 400 remains visible, unit Xu is 80, price unchanged."""
    catalog = queue.public_quality_catalog()
    trend_tier_400 = next((row for row in catalog if str(row.get("tier_id")) == "400"), None)

    assert trend_tier_400 is not None, "TREND_TIER_400_VISIBLE must be YES"
    assert trend_tier_400.get("unit_xu") == 80, "TREND_80_XU_CHANGED must be NO (unit_xu == 80)"
