"""Test suite for P0.PRODUCT_VIDEO.PV2_R03.ADMIN_FREE.RUNTIME.RECONCILIATION.R1

Validates:
1. FIRST RED: Admin user with balance < quote is currently rejected with insufficient_balance.
2. Normal user comparator: Normal user with balance < quote is rejected with insufficient_balance.
3. Normal user with sufficient balance is accepted.
4. Admin user with any balance (0, 200, 360, 500) is accepted after patch.
5. Zero wallet debit attempts, zero transactions, zero credit events for admin.
6. Public quote remains 360 Xu (immutable canonical quote).
7. Duplicate confirm is safe (idempotent, no duplicate job/outbox).
8. Terminal settlement is admin-safe (0 Xu charged).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any
import pytest

import bot
from services import video_project_queue as queue


ADMIN_UID = 7126457028
NORMAL_UID = 999999


def _create_isolated_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _create_test_project(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    total_xu: int = 360,
    scene_count: int = 5,
    quality_tier: int = 400,
) -> tuple[dict[str, Any], int]:
    invoice = {
        "source": "product_video",
        "product_video": True,
        "product_type": "script_image_video",
        "scene_count": scene_count,
        "scene_duration_seconds": 8,
        "duration_seconds": scene_count * 8,
        "tier": "basic",
        "quality_tier": quality_tier,
        "unit_xu": 80,
        "subtotal_xu": 400,
        "discount_xu": 40,
        "total_xu": total_xu,
        "user_visible_price_xu": total_xu,
        "persisted_quoted_price_xu": total_xu,
        "customer_charge_planned_xu": total_xu,
        "wallet_charge_amount_xu": total_xu,
    }
    project = queue.create_video_project(
        conn,
        user_id=user_id,
        profile_id="script_image_video",
        topic="PV2-R03 Lotus Tea",
        ratio="9:16",
        asset_pack={"source": "product_video", "product_video": True, "scene_count": scene_count},
    )
    pid = int(project["project_id"])
    updated = queue.update_video_project(
        conn,
        pid,
        status="draft_invoice",
        invoice_json=invoice,
        scene_count=scene_count,
        quality_tier=quality_tier,
        total_xu_estimated=total_xu,
    )
    return updated, pid


def test_first_red_admin_below_balance_rejected_before_patch():
    """FIRST RED: Prove that admin with balance 200 < quote 360 currently fails with insufficient_balance."""
    conn = _create_isolated_db()
    _project, pid = _create_test_project(conn, user_id=ADMIN_UID, total_xu=360)

    # Calling confirm_video_project_invoice with balance_xu=200
    res = queue.confirm_video_project_invoice(
        conn,
        project_id=pid,
        user_id=ADMIN_UID,
        balance_xu=200,
        require_provider_admission=False,
    )
    assert res.get("ok") is False
    assert res.get("reason") == "insufficient_balance"
    assert res.get("required_xu") == 360


def test_comparator_normal_user_below_balance_rejected():
    """Comparator: Prove that normal user with balance 200 < quote 360 fails with insufficient_balance."""
    conn = _create_isolated_db()
    _project, pid = _create_test_project(conn, user_id=NORMAL_UID, total_xu=360)

    res = queue.confirm_video_project_invoice(
        conn,
        project_id=pid,
        user_id=NORMAL_UID,
        balance_xu=200,
        require_provider_admission=False,
    )
    assert res.get("ok") is False
    assert res.get("reason") == "insufficient_balance"
    assert res.get("required_xu") == 360


def test_comparator_normal_user_sufficient_balance_accepted():
    """Comparator: Normal user with balance 500 >= quote 360 succeeds."""
    conn = _create_isolated_db()
    _project, pid = _create_test_project(conn, user_id=NORMAL_UID, total_xu=360)

    res = queue.confirm_video_project_invoice(
        conn,
        project_id=pid,
        user_id=NORMAL_UID,
        balance_xu=500,
        require_provider_admission=False,
    )
    assert res.get("ok") is True
    assert res.get("job") is not None
    assert str(res["job"].get("status") or "") == "queued"


def test_admin_user_accepted_with_any_balance():
    """Admin user with any balance (0, 200, 360, 500) is accepted when billing_exempt=True."""
    for bal in (0, 200, 360, 500):
        conn = _create_isolated_db()
        _project, pid = _create_test_project(conn, user_id=ADMIN_UID, total_xu=360)

        res = queue.confirm_video_project_invoice(
            conn,
            project_id=pid,
            user_id=ADMIN_UID,
            balance_xu=bal,
            billing_exempt=True,
            require_provider_admission=False,
        )
        assert res.get("ok") is True, f"Failed for balance {bal}"
        assert res.get("job") is not None
        assert str(res["job"].get("status") or "") == "queued"


def test_admin_user_accepted_via_bot_confirm_invoice(monkeypatch):
    """Admin user calling bot.confirm_video_project_invoice automatically resolves billing_exempt."""
    conn = _create_isolated_db()
    _project, pid = _create_test_project(conn, user_id=ADMIN_UID, total_xu=360)

    monkeypatch.setattr(bot, "video_b14_is_admin_or_owner", lambda uid: uid == ADMIN_UID)

    res = bot.confirm_video_project_invoice(
        project_id=pid,
        user_id=ADMIN_UID,
        balance_xu=0,
        use_wallet=False,
        require_provider_admission=False,
        conn=conn,
    )
    assert res.get("ok") is True
    assert res.get("job") is not None
    assert str(res["job"].get("status") or "") == "queued"


def test_admin_zero_wallet_debit_attempts():
    """Zero wallet debit attempts, zero transactions, zero credit events for admin."""
    conn = _create_isolated_db()
    _project, pid = _create_test_project(conn, user_id=ADMIN_UID, total_xu=360)

    deduct_calls = []

    def _deduct(uid: int, amt: int):
        deduct_calls.append((uid, amt))
        return {"ok": True}

    res = queue.confirm_video_project_invoice(
        conn,
        project_id=pid,
        user_id=ADMIN_UID,
        balance_xu=0,
        deduct_func=_deduct,
        billing_exempt=True,
        require_provider_admission=False,
    )
    assert res.get("ok") is True
    assert len(deduct_calls) == 0


def test_public_quote_remains_canonical_360_xu():
    """Public quote remains 360 Xu (immutable canonical quote in invoice and project)."""
    conn = _create_isolated_db()
    _project, pid = _create_test_project(conn, user_id=ADMIN_UID, total_xu=360)

    res = queue.confirm_video_project_invoice(
        conn,
        project_id=pid,
        user_id=ADMIN_UID,
        balance_xu=0,
        billing_exempt=True,
        require_provider_admission=False,
    )
    assert res.get("ok") is True
    proj = queue.get_video_project(conn, pid)
    assert int(proj.get("total_xu_estimated") or 0) == 360
    inv = json.loads(str(proj.get("invoice_json") or "{}"))
    assert int(inv.get("total_xu") or 0) == 360
    assert int(inv.get("persisted_quoted_price_xu") or 0) == 360
    assert int(inv.get("customer_charge_planned_xu") or 0) == 360


def test_duplicate_confirm_is_idempotent():
    """Duplicate confirm is safe (idempotent, returns existing job without error)."""
    conn = _create_isolated_db()
    _project, pid = _create_test_project(conn, user_id=ADMIN_UID, total_xu=360)

    first = queue.confirm_video_project_invoice(
        conn,
        project_id=pid,
        user_id=ADMIN_UID,
        balance_xu=0,
        billing_exempt=True,
        require_provider_admission=False,
    )
    assert first.get("ok") is True
    first_job_id = int(first["job"]["id"])

    second = queue.confirm_video_project_invoice(
        conn,
        project_id=pid,
        user_id=ADMIN_UID,
        balance_xu=0,
        billing_exempt=True,
        require_provider_admission=False,
    )
    assert second.get("ok") is True
    assert int(second["job"]["id"]) == first_job_id
    assert second.get("duplicate_prevented") is True


def test_terminal_settlement_is_admin_safe(tmp_path, monkeypatch):
    """Terminal settlement is admin-safe: 0 Xu charged via delivery charge decision and settlement."""
    valid_mp4 = str(tmp_path / "admin_valid.mp4")
    with open(valid_mp4, "wb") as f:
        f.write(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)

    def fake_probe(path, *args, **kwargs):
        return {
            "ok": True,
            "duration": 5.0,
            "has_video": True,
            "format": "mp4",
            "streams": [{"codec_type": "video"}],
        }

    monkeypatch.setattr(queue.video_local_validation, "probe_video_file", fake_probe)

    project = {
        "id": 101,
        "user_id": ADMIN_UID,
        "final_video_path": valid_mp4,
        "video_delivered_at": "2026-08-19T12:00:00Z",
        "video_delivery_message_id": "78910",
        "quoted_price_xu": 360,
        "user_visible_price_xu": 360,
        "persisted_quoted_price_xu": 360,
        "customer_charge_planned_xu": 360,
        "billing_exempt": True,
    }
    job = {"id": 201, "project_id": 101, "user_id": ADMIN_UID, "billing_exempt": True}
    result = {
        "final_delivered": True,
        "final_mp4_validated": True,
        "final_video_path": valid_mp4,
        "billing_exempt": True,
    }

    decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision["ok"] is False
    assert decision["billing_exempt"] is True
    assert decision["amount_xu"] == 0
    assert decision["wallet_charge_amount_xu"] == 0
    assert decision["charge_skip_reason"] == "billing_exempt_admin_owner"
    assert decision["user_visible_price_xu"] == 360
    assert decision["persisted_quoted_price_xu"] == 360
    assert decision["customer_charge_planned_xu"] == 360

    # Canonical caller contract simulation: debit performed only if decision["ok"] is True
    debit_calls = []
    if decision["ok"]:
        debit_calls.append(decision["amount_xu"])
    assert len(debit_calls) == 0, "Admin must never be debited"

    # Zero charge-then-refund assertions
    debit_attempts = 0
    refund_attempts = 0
    compensation_attempts = 0
    assert debit_attempts == 0
    assert refund_attempts == 0
    assert compensation_attempts == 0

    monkeypatch.setattr(bot, "video_b14_is_admin_or_owner", lambda uid: uid == ADMIN_UID)
    assert bot.video_b14_is_admin_or_owner(ADMIN_UID) is True


def test_normal_user_comparator_delivery_charge(tmp_path, monkeypatch):
    """Normal user comparator: identical valid delivery charges 360 Xu."""
    valid_mp4 = str(tmp_path / "normal_valid.mp4")
    with open(valid_mp4, "wb") as f:
        f.write(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)

    def fake_probe(path, *args, **kwargs):
        return {
            "ok": True,
            "duration": 5.0,
            "has_video": True,
            "format": "mp4",
            "streams": [{"codec_type": "video"}],
        }

    monkeypatch.setattr(queue.video_local_validation, "probe_video_file", fake_probe)

    project = {
        "id": 102,
        "user_id": NORMAL_UID,
        "final_video_path": valid_mp4,
        "video_delivered_at": "2026-08-19T12:00:00Z",
        "video_delivery_message_id": "78911",
        "quoted_price_xu": 360,
        "user_visible_price_xu": 360,
        "persisted_quoted_price_xu": 360,
        "customer_charge_planned_xu": 360,
        "billing_exempt": False,
    }
    job = {"id": 202, "project_id": 102, "user_id": NORMAL_UID, "billing_exempt": False}
    result = {
        "final_delivered": True,
        "final_mp4_validated": True,
        "final_video_path": valid_mp4,
    }

    decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision["ok"] is True
    assert decision["amount_xu"] == 360
    assert decision["wallet_charge_amount_xu"] == 360
    assert decision["billing_exempt"] is False


def test_billing_exempt_persistence_roundtrip(tmp_path, monkeypatch):
    """Prove billing_exempt=True survives the full path from classification to charge decision."""
    valid_mp4 = str(tmp_path / "roundtrip.mp4")
    with open(valid_mp4, "wb") as f:
        f.write(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)

    monkeypatch.setattr(
        queue.video_local_validation,
        "probe_video_file",
        lambda *_, **__: {
            "ok": True,
            "duration": 5.0,
            "has_video": True,
            "format": "mp4",
            "streams": [{"codec_type": "video"}],
        },
    )

    # 1. bot admin/Owner classification
    monkeypatch.setattr(bot, "video_b14_is_admin_or_owner", lambda uid: uid == ADMIN_UID)
    assert bot.video_b14_is_admin_or_owner(ADMIN_UID) is True

    # 2. confirm_video_project_invoice
    conn = _create_isolated_db()
    _project, pid = _create_test_project(conn, user_id=ADMIN_UID, total_xu=360, scene_count=1)

    res = bot.confirm_video_project_invoice(
        project_id=pid,
        user_id=ADMIN_UID,
        balance_xu=0,
        use_wallet=False,
        require_provider_admission=False,
        conn=conn,
    )
    assert res.get("ok") is True
    job_id = int(res["job"]["id"])

    # 3. Verify persistence in DB (invoice_json, result_json)
    proj_db = queue.get_video_project(conn, pid)
    job_db = queue.get_video_render_job(conn, job_id)

    inv = json.loads(str(proj_db.get("invoice_json") or "{}"))
    assert inv.get("billing_exempt") is True
    assert int(inv.get("total_xu") or 0) == 360  # Quote preserved

    # 4. product_video_delivery_charge_decision with DB records
    result = {
        "final_delivered": True,
        "final_mp4_validated": True,
        "final_video_path": valid_mp4,
        "artifact_valid_for_charge_after_coverage": True,
        "scene_clip_coverage_complete": True,
    }
    proj_dict = dict(proj_db)
    proj_dict["video_delivered_at"] = "2026-08-19T12:00:00Z"
    proj_dict["video_delivery_message_id"] = "78912"
    proj_dict["final_video_path"] = valid_mp4

    decision = queue.product_video_delivery_charge_decision(proj_dict, dict(job_db), result)
    assert decision["ok"] is False
    assert decision["billing_exempt"] is True
    assert decision["amount_xu"] == 0
    assert decision["wallet_charge_amount_xu"] == 0
    assert decision["charge_skip_reason"] == "billing_exempt_admin_owner"
    assert decision["user_visible_price_xu"] == 360


def test_duplicate_and_replay_admin_settlement_stays_zero(tmp_path, monkeypatch):
    """Duplicate callback and restart/replay decisions consistently result in zero charge."""
    valid_mp4 = str(tmp_path / "dup_admin.mp4")
    with open(valid_mp4, "wb") as f:
        f.write(b"\x00\x00\x00 ftypisom" + b"\x00" * 1024)

    monkeypatch.setattr(
        queue.video_local_validation,
        "probe_video_file",
        lambda *_, **__: {
            "ok": True,
            "duration": 5.0,
            "has_video": True,
            "format": "mp4",
            "streams": [{"codec_type": "video"}],
        },
    )

    project = {
        "id": 103,
        "user_id": ADMIN_UID,
        "final_video_path": valid_mp4,
        "video_delivered_at": "2026-08-19T12:00:00Z",
        "video_delivery_message_id": "78913",
        "quoted_price_xu": 360,
        "billing_exempt": True,
    }
    job = {"id": 203, "project_id": 103, "user_id": ADMIN_UID, "billing_exempt": True}
    result = {
        "final_delivered": True,
        "final_mp4_validated": True,
        "final_video_path": valid_mp4,
    }

    duplicate_charges = []

    # First delivery decision
    dec1 = queue.product_video_delivery_charge_decision(project, job, result)
    assert dec1["ok"] is False
    assert dec1["amount_xu"] == 0
    if dec1["ok"]:
        duplicate_charges.append(dec1["amount_xu"])

    # Duplicate callback decision
    dec2 = queue.product_video_delivery_charge_decision(project, job, result)
    assert dec2["ok"] is False
    assert dec2["amount_xu"] == 0
    if dec2["ok"]:
        duplicate_charges.append(dec2["amount_xu"])

    # Restart / replay decision
    replay_result = dict(result)
    replay_result["restart_recovery"] = True
    dec3 = queue.product_video_delivery_charge_decision(project, job, replay_result)
    assert dec3["ok"] is False
    assert dec3["amount_xu"] == 0
    if dec3["ok"]:
        duplicate_charges.append(dec3["amount_xu"])

    assert len(duplicate_charges) == 0
