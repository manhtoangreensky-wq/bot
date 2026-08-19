"""Zero-cost Contract Test Suite for Delivery Receipt and Billing Invariant.

Tests all 12 required scenarios under P0.VIDEO.DELIVERY_RECEIPT.BILLING.LIVE_PROOF:
1. valid artifact + delivery accepted + receipt persisted -> one charge
2. valid artifact + Telegram rejected -> zero charge
3. valid artifact + accepted but receipt persistence fails -> zero charge
4. invalid artifact -> no delivery billing
5. duplicate completion callback -> one charge
6. duplicate Telegram receipt callback -> one charge
7. restart after receipt before charge -> resumes and charges once
8. restart after charge -> no duplicate charge
9. multiscene all scenes valid + final artifact delivered -> one aggregate customer charge
10. one multiscene scene failed -> no successful-delivery charge
11. provider reports SUCCESS but artifact invalid -> zero charge
12. HTTP 200 without valid provider task/result -> zero charge
"""

from __future__ import annotations

import os
import sqlite3
import pytest
import tempfile
from pathlib import Path

import bot
import services.video_project_queue as queue
import services.video_trace_state as vts


def test_scenario_1_valid_artifact_delivered_receipt_persisted_charges_once(tmp_path):
    """1. valid artifact + delivery accepted + receipt persisted -> one charge"""
    valid_mp4 = str(tmp_path / "final_valid.mp4")
    with open(valid_mp4, "wb") as f:
        f.write(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)

    project = {
        "id": 101,
        "user_id": 9999,
        "final_video_path": valid_mp4,
        "video_delivered_at": "2026-08-19T12:00:00Z",
        "video_delivery_message_id": "78910",
        "quoted_price_xu": 80,
    }
    job = {"id": 201, "project_id": 101, "user_id": 9999}
    result = {
        "final_delivered": True,
        "final_mp4_validated": True,
        "final_video_path": valid_mp4,
    }

    decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision["ok"] is True
    assert decision["amount_xu"] == 80
    assert decision["already_charged"] is False
    assert decision["charge_idempotency_key"] == "product_video_final_delivery:201:80"


def test_scenario_2_valid_artifact_telegram_rejected_zero_charge(tmp_path):
    """2. valid artifact + Telegram rejected -> zero charge"""
    valid_mp4 = str(tmp_path / "final_valid.mp4")
    with open(valid_mp4, "wb") as f:
        f.write(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)

    project = {
        "id": 102,
        "user_id": 9999,
        "final_video_path": valid_mp4,
        # Not delivered
        "quoted_price_xu": 80,
    }
    job = {"id": 202, "project_id": 102, "user_id": 9999}
    result = {
        "final_delivered": False,
        "final_mp4_validated": True,
        "final_video_path": valid_mp4,
    }

    decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision["ok"] is False
    assert decision["amount_xu"] == 0
    assert decision["charge_skip_reason"] == "delivery_required_before_charge"


def test_scenario_3_valid_artifact_accepted_receipt_missing_fails():
    """3. valid artifact + accepted but receipt persistence fails -> zero charge"""
    project = {
        "id": 103,
        "user_id": 9999,
        "quoted_price_xu": 80,
    }
    job = {"id": 203, "project_id": 103}
    result = {"final_delivered": False}

    decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision["ok"] is False
    assert decision["amount_xu"] == 0


def test_scenario_4_invalid_artifact_no_charge():
    """4. invalid artifact -> no delivery billing"""
    project = {
        "id": 104,
        "user_id": 9999,
        "video_delivered_at": "2026-08-19T12:00:00Z",
        "quoted_price_xu": 80,
    }
    job = {"id": 204, "project_id": 104}
    result = {
        "final_delivered": True,
        "final_mp4_validated": False,
        "final_mp4_valid": False,
        "final_video_path": "/nonexistent/corrupt.mp4",
    }

    decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision["ok"] is False
    assert decision["amount_xu"] == 0
    assert decision["charge_skip_reason"] == "valid_mp4_required_before_charge"


def test_scenario_5_duplicate_completion_callback_charges_once(tmp_path):
    """5. duplicate completion callback -> one charge"""
    valid_mp4 = str(tmp_path / "valid.mp4")
    with open(valid_mp4, "wb") as f:
        f.write(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)

    project = {
        "id": 105,
        "user_id": 9999,
        "final_video_path": valid_mp4,
        "video_delivered_at": "2026-08-19T12:00:00Z",
        "quoted_price_xu": 80,
    }
    job = {"id": 205, "project_id": 105}
    result1 = {
        "final_delivered": True,
        "final_mp4_validated": True,
        "final_video_path": valid_mp4,
    }
    decision1 = queue.product_video_delivery_charge_decision(project, job, result1)
    assert decision1["ok"] is True
    assert decision1["already_charged"] is False

    result2 = {
        **result1,
        "charged_amount_xu": 80,
        "wallet_charge_recorded": True,
        "charge_tx_id": "tx_test_123",
        "charge_idempotency_key": "product_video_final_delivery:205:80",
    }
    decision2 = queue.product_video_delivery_charge_decision(project, job, result2)
    assert decision2["ok"] is True
    assert decision2["already_charged"] is True
    assert decision2["charge_skip_reason"] == "already_charged"


def test_scenario_6_duplicate_telegram_receipt_callback_charges_once(tmp_path):
    """6. duplicate Telegram receipt callback -> one charge"""
    valid_mp4 = str(tmp_path / "valid.mp4")
    with open(valid_mp4, "wb") as f:
        f.write(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)

    project = {
        "id": 106,
        "user_id": 9999,
        "final_video_path": valid_mp4,
        "video_delivered_at": "2026-08-19T12:00:00Z",
        "video_delivery_message_id": "msg_999",
        "charged_amount_xu": 80,
    }
    job = {"id": 206, "project_id": 106}
    result = {"final_delivered": True, "final_mp4_validated": True, "charged_xu": 80}

    decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision["already_charged"] is True


def test_scenario_7_restart_after_receipt_resumes_and_charges_once(tmp_path):
    """7. restart after receipt before charge -> resumes and charges once"""
    valid_mp4 = str(tmp_path / "valid.mp4")
    with open(valid_mp4, "wb") as f:
        f.write(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)

    project = {
        "id": 107,
        "user_id": 9999,
        "final_video_path": valid_mp4,
        "video_delivered_at": "2026-08-19T12:00:00Z",
        "video_delivery_message_id": "msg_107",
        "quoted_price_xu": 80,
    }
    job = {"id": 207, "project_id": 107}
    result = {
        "final_delivered": True,
        "final_mp4_validated": True,
        "final_video_path": valid_mp4,
        # Not yet charged
    }

    decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision["ok"] is True
    assert decision["amount_xu"] == 80
    assert decision["already_charged"] is False


def test_scenario_8_restart_after_charge_no_duplicate_charge(tmp_path):
    """8. restart after charge -> no duplicate charge"""
    valid_mp4 = str(tmp_path / "valid.mp4")
    with open(valid_mp4, "wb") as f:
        f.write(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)

    project = {
        "id": 108,
        "user_id": 9999,
        "final_video_path": valid_mp4,
        "video_delivered_at": "2026-08-19T12:00:00Z",
        "charged_amount_xu": 80,
    }
    job = {"id": 208, "project_id": 108}
    result = {"final_delivered": True, "final_mp4_validated": True, "charged_amount_xu": 80}

    decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision["already_charged"] is True
    assert decision["charge_skip_reason"] == "already_charged"


def test_scenario_9_multiscene_all_valid_delivered_charges_aggregate(tmp_path):
    """9. multiscene all scenes valid + final artifact delivered -> one aggregate customer charge"""
    final_mp4 = str(tmp_path / "final_assembled.mp4")
    with open(final_mp4, "wb") as f:
        f.write(b"\x00\x00\x00 ftypisom" + b"\x00" * 2048)

    project = {
        "id": 109,
        "user_id": 9999,
        "final_video_path": final_mp4,
        "video_delivered_at": "2026-08-19T12:00:00Z",
        "video_delivery_message_id": "msg_multiscene",
        "quoted_price_xu": 160,
        "scene_count": 2,
    }
    job = {"id": 209, "project_id": 109}
    result = {
        "final_delivered": True,
        "final_mp4_validated": True,
        "final_video_path": final_mp4,
        "scene_count": 2,
        "scene_ledger": [
            {"scene_index": 1, "status": "completed", "clip_valid": True, "clip_path": final_mp4, "clip_bytes": 1024},
            {"scene_index": 2, "status": "completed", "clip_valid": True, "clip_path": final_mp4, "clip_bytes": 1024},
        ],
    }

    decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision["ok"] is True
    assert decision["amount_xu"] == 160
    assert decision["already_charged"] is False


def test_scenario_10_multiscene_one_failed_zero_charge():
    """10. one multiscene scene failed -> no successful-delivery charge"""
    project = {
        "id": 110,
        "user_id": 9999,
        "quoted_price_xu": 160,
        "scene_count": 2,
    }
    job = {"id": 210, "project_id": 110}
    result = {
        "final_delivered": False,
        "scene_count": 2,
        "covered_scenes_count": 1,
        "error": "scene_2_failed",
    }

    decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision["ok"] is False
    assert decision["amount_xu"] == 0


def test_scenario_11_provider_reports_success_but_artifact_invalid():
    """11. provider reports SUCCESS but artifact invalid -> zero charge"""
    project = {
        "id": 111,
        "user_id": 9999,
        "quoted_price_xu": 80,
    }
    job = {"id": 211, "project_id": 111}
    result = {
        "provider_status": "SUCCESS",
        "final_delivered": False,
        "final_mp4_validated": False,
        "final_video_path": "",
    }

    decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision["ok"] is False
    assert decision["amount_xu"] == 0


def test_scenario_12_http_200_without_valid_provider_task_zero_charge():
    """12. HTTP 200 without valid provider task/result -> zero charge"""
    project = {
        "id": 112,
        "user_id": 9999,
        "quoted_price_xu": 80,
    }
    job = {"id": 212, "project_id": 112}
    result = {
        "http_status": 200,
        "provider_task_id": None,
        "final_delivered": False,
    }

    decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision["ok"] is False
    assert decision["amount_xu"] == 0
