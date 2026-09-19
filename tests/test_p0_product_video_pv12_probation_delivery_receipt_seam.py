# -*- coding: utf-8 -*-
"""Tests for PV12 Probation Delivery Receipt and Provider Promotion Separation.

Enforces:
1. Customer delivery receipt eligibility is decoupled from provider probation promotion.
2. Missing provider result URL prevents provider promotion, but DOES NOT block recording a valid customer delivery receipt when the final MP4 is physically valid.
3. Local physical MP4 validation (via probe_video_file, non-zero size, sha256 binding) is strictly enforced.
4. Job 28 completion-only reconciliation delivers with final_delivered, progress=100, charge=0, without promoting provider health.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from services import video_project_queue as queue
from services import video_local_validation


JOB28_SHA256 = "1da91adab09303aae98ba6ac899a93471494041c318dc09b5eb686c1d592ca2d"


def _setup_job28_fixture(
    tmp_path: Path,
    *,
    create_valid_file: bool = True,
    corrupt_file: bool = False,
    file_bytes: int = 1024,
    admission_mode: str = queue.PRODUCT_VIDEO_PROBATION_ADMISSION_MODE,
    scene_coverage_complete: bool = True,
    result_url: str = "",
) -> tuple[sqlite3.Connection, int, int, Path]:
    conn = sqlite3.connect(tmp_path / "pv12_probation_delivery.db")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)

    project = queue.create_video_project(
        conn,
        user_id=7126457028,
        asset_pack={
            "source": "product_video",
            "render_mode": "real",
            "recovery_existing_tasks_only": True,
        },
    )
    project_id = int(project["project_id"])
    job = queue.enqueue_video_render_job(
        conn,
        project_id=project_id,
        user_id=7126457028,
    )
    job_id = int(job["id"])

    mp4_path = tmp_path / "final_output.mp4"
    if create_valid_file:
        content = b"\x00" * file_bytes
        mp4_path.write_bytes(content)
        actual_sha = hashlib.sha256(content).hexdigest().lower()
    else:
        actual_sha = JOB28_SHA256

    payload: dict[str, Any] = {
        "admission_mode": admission_mode,
        "completion_only_reconciliation_used": True,
        "completion_only_reconciliation_sha256": actual_sha,
        "recovery_existing_tasks_only": True,
        "no_charge": True,
        "charged_xu": 0,
        "wallet_charge_recorded": False,
        "final_video_path": str(mp4_path) if create_valid_file or corrupt_file else "",
        "scene_tasks": [
            {"scene_index": 1, "clip_valid": True, "result_url": result_url},
            {"scene_index": 2, "clip_valid": True, "result_url": result_url},
        ],
        "scene_coverage_expected": 2,
        "scene_coverage_count": 2 if scene_coverage_complete else 1,
        "scene_clip_coverage_complete": scene_coverage_complete,
        "final_mp4_valid": True,
        "final_mp4_validated": True,
        "output_bytes": file_bytes,
        "result_url": result_url,
        "provider_result_url": result_url,
    }

    conn.execute(
        "UPDATE video_jobs SET status='completed', progress_percent=95, progress_message='final_mp4_ready_waiting_delivery', result_json=? WHERE id=?",
        (json.dumps(payload), job_id),
    )
    conn.execute(
        "UPDATE video_projects SET status='completed', video_terminal_state='final_mp4_ready', final_video_path=?, video_artifact_hash=? WHERE project_id=?",
        (str(mp4_path), actual_sha, project_id),
    )
    conn.commit()
    return conn, job_id, project_id, mp4_path


def test_b_job28_completion_only_probation_delivery_success(monkeypatch, tmp_path):
    """Case B: Job 28 completion-only probation delivery records receipt, final_delivered, progress=100 without provider promotion."""
    conn, job_id, project_id, mp4_path = _setup_job28_fixture(tmp_path, create_valid_file=True)

    monkeypatch.setattr(
        queue.video_uiflow3_execution_contract,
        "validate_execution_contract",
        lambda *_args, **_kwargs: {"ok": True, "applies": False, "blocker": ""},
    )
    monkeypatch.setattr(
        video_local_validation,
        "probe_video_file",
        lambda _p: {"ok": True, "duration": 16.0},
    )

    receipt = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="tg-msg-2801",
        success_message_id="tg-msg-2801",
    )

    assert receipt["ok"] is True
    assert receipt["sent"] is True

    stored_job = queue.get_video_render_job(conn, job_id)
    stored_project = queue.get_video_project(conn, project_id)
    payload = json.loads(stored_job["result_json"])

    assert stored_job["status"] == "completed"
    assert stored_job["progress_percent"] == 100
    assert stored_job["progress_message"] == "delivered"

    assert stored_project["status"] == "completed"
    assert stored_project["video_terminal_state"] == "final_delivered"
    assert stored_project["video_delivered_at"] is not None
    assert stored_project["video_delivery_message_id"] == "tg-msg-2801"

    # Invariants: Provider promotion MUST be False, probation MUST remain pending
    assert payload["provider_health_promotion_eligible"] is False
    assert payload["probation_result"] == "pending"
    assert payload["delivery_succeeded"] is True
    assert payload["final_mp4_delivered"] is True
    assert payload["final_delivered"] is True

    # Billing invariants: strictly 0
    assert payload.get("charged_xu") == 0
    assert payload.get("wallet_charge_recorded") is False
    assert payload.get("recovery_existing_tasks_only") is True
    assert payload.get("no_charge") is True

    conn.close()


def test_c_job28_corrupt_or_missing_local_mp4_fails_closed(monkeypatch, tmp_path):
    """Case C: Job 28 with missing or unprobeable MP4 must fail closed."""
    conn, job_id, project_id, mp4_path = _setup_job28_fixture(tmp_path, create_valid_file=False)

    monkeypatch.setattr(
        queue.video_uiflow3_execution_contract,
        "validate_execution_contract",
        lambda *_args, **_kwargs: {"ok": True, "applies": False, "blocker": ""},
    )
    monkeypatch.setattr(
        video_local_validation,
        "probe_video_file",
        lambda _p: {"ok": False, "error": "file_not_found"},
    )

    receipt = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="tg-msg-2802",
    )

    assert receipt["ok"] is False
    assert receipt["sent"] is False

    stored_project = queue.get_video_project(conn, project_id)
    assert stored_project["video_terminal_state"] != "final_delivered"
    assert stored_project["video_delivered_at"] is None
    assert stored_project["video_delivery_message_id"] is None

    conn.close()


def test_d_probation_with_full_provider_result_promotes_health(monkeypatch, tmp_path):
    """Case D: Probation with full provider result proof preserves existing promotion behavior."""
    conn, job_id, project_id, mp4_path = _setup_job28_fixture(
        tmp_path,
        create_valid_file=True,
        result_url="https://provider.cloud.invalid/clip.mp4",
    )

    monkeypatch.setattr(
        queue.video_uiflow3_execution_contract,
        "validate_execution_contract",
        lambda *_args, **_kwargs: {"ok": True, "applies": False, "blocker": ""},
    )
    monkeypatch.setattr(
        video_local_validation,
        "probe_video_file",
        lambda _p: {"ok": True, "duration": 16.0},
    )

    receipt = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="tg-msg-2803",
    )

    assert receipt["ok"] is True
    assert receipt["sent"] is True

    stored_job = queue.get_video_render_job(conn, job_id)
    payload = json.loads(stored_job["result_json"])

    assert payload["provider_health_promotion_eligible"] is True
    assert payload["probation_result"] == "success"
    conn.close()


def test_e_missing_telegram_message_id_fails_closed(monkeypatch, tmp_path):
    """Case E: Missing delivery_message_id fails closed."""
    conn, job_id, project_id, mp4_path = _setup_job28_fixture(tmp_path, create_valid_file=True)

    monkeypatch.setattr(
        queue.video_uiflow3_execution_contract,
        "validate_execution_contract",
        lambda *_args, **_kwargs: {"ok": True, "applies": False, "blocker": ""},
    )

    receipt = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="",
    )

    assert receipt["ok"] is False
    assert receipt["sent"] is False
    assert receipt["reason"] in ("delivery_receipt_required", "probation_final_delivery_requirements_missing")

    conn.close()


def test_f_scene_coverage_incomplete_fails_closed(monkeypatch, tmp_path):
    """Case F: Incomplete scene coverage fails closed."""
    conn, job_id, project_id, mp4_path = _setup_job28_fixture(
        tmp_path,
        create_valid_file=True,
        scene_coverage_complete=False,
    )

    monkeypatch.setattr(
        queue.video_uiflow3_execution_contract,
        "validate_execution_contract",
        lambda *_args, **_kwargs: {"ok": True, "applies": False, "blocker": ""},
    )

    receipt = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="tg-msg-2804",
    )

    assert receipt["ok"] is False
    assert receipt["sent"] is False
    assert receipt["reason"] in ("scene_coverage_required_before_delivery", "probation_final_delivery_requirements_missing")

    conn.close()


def test_g_repeated_receipt_preserves_duplicate_prevention(monkeypatch, tmp_path):
    """Case G: Duplicate delivery receipt replay preserves duplicate-prevention semantics."""
    conn, job_id, project_id, mp4_path = _setup_job28_fixture(tmp_path, create_valid_file=True)

    monkeypatch.setattr(
        queue.video_uiflow3_execution_contract,
        "validate_execution_contract",
        lambda *_args, **_kwargs: {"ok": True, "applies": False, "blocker": ""},
    )
    monkeypatch.setattr(
        video_local_validation,
        "probe_video_file",
        lambda _p: {"ok": True, "duration": 16.0},
    )

    first = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="tg-msg-2805",
    )
    assert first["ok"] is True

    second = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="tg-msg-2805",
    )
    assert second["ok"] is True
    assert second.get("duplicate_prevented") is True

    conn.close()


def test_h_charge_decision_after_job28_delivery_is_zero(monkeypatch, tmp_path):
    """Case H: Pure charge decision after Job 28 delivery remains 0 with existing_task_recovery_no_charge."""
    conn, job_id, project_id, mp4_path = _setup_job28_fixture(tmp_path, create_valid_file=True)

    monkeypatch.setattr(
        queue.video_uiflow3_execution_contract,
        "validate_execution_contract",
        lambda *_args, **_kwargs: {"ok": True, "applies": False, "blocker": ""},
    )
    monkeypatch.setattr(
        video_local_validation,
        "probe_video_file",
        lambda _p: {"ok": True, "duration": 16.0},
    )

    receipt = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="tg-msg-2806",
    )
    assert receipt["ok"] is True

    job = queue.get_video_render_job(conn, job_id)
    project = queue.get_video_project(conn, project_id)
    result = json.loads(job["result_json"])

    decision = queue.product_video_delivery_charge_decision(project, job, result)

    assert decision["ok"] is False
    assert decision["amount_xu"] == 0
    assert decision["charge_skip_reason"] == "existing_task_recovery_no_charge"

    conn.close()
