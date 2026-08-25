from __future__ import annotations

import asyncio
import json
import sqlite3
from types import SimpleNamespace

import bot
from fastapi.testclient import TestClient
from services import remote_worker_api
from services import video_project_queue as queue


def _duplicate_result(final_path, *, delivered: bool = False):
    return {
        "ok": True,
        "duplicate": True,
        "job": {
            "id": 19,
            "job_type": queue.VIDEO_RENDER_JOB_TYPE,
            "result_json": json.dumps(
                {
                    "render_mode": "real",
                    "renderer": "remote_worker_real_render_route",
                    "visual_classification": "final_ai_video",
                }
            ),
        },
        "project": {
            "project_id": 23,
            "user_id": "7126457028",
            "final_video_path": str(final_path),
            "video_delivered_at": "2026-08-23 16:40:00" if delivered else None,
            "video_delivery_message_id": "901" if delivered else None,
            "asset_pack_json": json.dumps(
                {
                    "source": "product_video",
                    "render_mode": "real",
                    "provider_call": True,
                    "public_user": True,
                }
            ),
        },
    }


def test_completed_duplicate_returns_project_for_delivery_retry(tmp_path):
    conn = sqlite3.connect(tmp_path / "duplicate-completion.db")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    project = queue.create_video_project(
        conn,
        user_id=7126457028,
        asset_pack={"source": "product_video", "render_mode": "real"},
    )
    job = queue.enqueue_video_render_job(
        conn,
        project_id=int(project["project_id"]),
        user_id=7126457028,
    )
    conn.execute(
        "UPDATE video_jobs SET status='completed',locked_by='vps-toanaas-01' WHERE id=?",
        (int(job["id"]),),
    )
    conn.commit()

    duplicate = remote_worker_api.complete_remote_worker_job(
        conn,
        worker_id="vps-toanaas-01",
        job_id=int(job["id"]),
    )

    assert duplicate["ok"] is True
    assert duplicate["duplicate"] is True
    assert duplicate["project"]["project_id"] == project["project_id"]
    conn.close()


def test_duplicate_completion_without_receipt_retries_delivery(monkeypatch, tmp_path):
    final_path = tmp_path / "final.mp4"
    final_path.write_bytes(b"real-product-video")
    sent = []

    async def deliver(_bot, chat_id, path, _artifact_meta, **_kwargs):
        sent.append((chat_id, path))
        return {"sent": True, "telegram_message_id": "902"}

    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=object()))
    monkeypatch.setattr(bot, "send_generated_video_artifact_for_delivery", deliver)

    delivery = asyncio.run(
        bot.maybe_send_remote_worker_final_video(_duplicate_result(final_path))
    )

    assert delivery["sent"] is True
    assert delivery["telegram_message_id"] == "902"
    assert sent == [(7126457028, str(final_path))]


def test_duplicate_completion_with_receipt_does_not_send_again(monkeypatch, tmp_path):
    final_path = tmp_path / "final.mp4"
    final_path.write_bytes(b"real-product-video")

    async def unexpected_delivery(*_args, **_kwargs):
        raise AssertionError("delivered completion must not send twice")

    monkeypatch.setattr(bot, "tg_app", SimpleNamespace(bot=object()))
    monkeypatch.setattr(
        bot,
        "send_generated_video_artifact_for_delivery",
        unexpected_delivery,
    )

    delivery = asyncio.run(
        bot.maybe_send_remote_worker_final_video(
            _duplicate_result(final_path, delivered=True)
        )
    )

    assert delivery["sent"] is False
    assert delivery["reason"] == "already_delivered"
    assert delivery["duplicate_prevented"] is True


def test_duplicate_delivery_retry_persists_receipt_and_settlement(monkeypatch, tmp_path):
    final_path = tmp_path / "final.mp4"
    final_path.write_bytes(b"real-product-video")
    completion = _duplicate_result(final_path)
    calls = []

    class FakeConn:
        def close(self):
            return None

    async def deliver(_result):
        return {"sent": True, "telegram_message_id": "903"}

    def note_delivery(_conn, **kwargs):
        calls.append(("delivery", kwargs))
        return {"ok": True, "sent": True}

    def settle(_job_id, **kwargs):
        calls.append(("settlement", kwargs))
        return {"ok": True, "charged_xu": 0, "charge_status": "admin_free"}

    monkeypatch.setattr(bot, "verify_remote_worker_api_access", lambda _request: None)
    monkeypatch.setattr(
        bot,
        "_record_owner_product_video_worker_identity",
        lambda *_args, **_kwargs: {"owner_heartbeat_request_received": False},
    )
    monkeypatch.setattr(bot, "db_connect", lambda: FakeConn())
    monkeypatch.setattr(
        bot.remote_worker_api,
        "complete_remote_worker_job",
        lambda *_args, **_kwargs: completion,
    )
    monkeypatch.setattr(bot, "maybe_send_remote_worker_final_video", deliver)
    monkeypatch.setattr(
        bot.video_project_queue,
        "note_video_delivery_result",
        note_delivery,
    )
    monkeypatch.setattr(
        bot,
        "product_video_charge_after_final_delivery",
        settle,
    )

    response = TestClient(bot.fastapi_app).post(
        "/api/v1/worker/complete",
        json={"worker_id": "vps-toanaas-01", "job_id": 19, "result": {}},
    )

    assert response.status_code == 200
    assert [name for name, _payload in calls] == ["delivery", "settlement"]
    assert calls[0][1]["delivery_message_id"] == "903"
    assert response.json()["delivery_receipt"]["sent"] is True


def test_delivery_settlement_waits_for_durable_receipt(monkeypatch, tmp_path):
    final_path = tmp_path / "final.mp4"
    final_path.write_bytes(b"real-product-video")
    completion = _duplicate_result(final_path)
    settlement_calls = []

    class FakeConn:
        def close(self):
            return None

    async def deliver(_result):
        return {"sent": True, "telegram_message_id": "904"}

    monkeypatch.setattr(bot, "verify_remote_worker_api_access", lambda _request: None)
    monkeypatch.setattr(
        bot,
        "_record_owner_product_video_worker_identity",
        lambda *_args, **_kwargs: {"owner_heartbeat_request_received": False},
    )
    monkeypatch.setattr(bot, "db_connect", lambda: FakeConn())
    monkeypatch.setattr(
        bot.remote_worker_api,
        "complete_remote_worker_job",
        lambda *_args, **_kwargs: completion,
    )
    monkeypatch.setattr(bot, "maybe_send_remote_worker_final_video", deliver)
    monkeypatch.setattr(
        bot.video_project_queue,
        "note_video_delivery_result",
        lambda *_args, **_kwargs: {
            "ok": False,
            "sent": False,
            "reason": "receipt_not_persisted",
        },
    )
    monkeypatch.setattr(
        bot,
        "product_video_charge_after_final_delivery",
        lambda *_args, **_kwargs: settlement_calls.append(True),
    )

    response = TestClient(bot.fastapi_app).post(
        "/api/v1/worker/complete",
        json={"worker_id": "vps-toanaas-01", "job_id": 19, "result": {}},
    )

    assert response.status_code == 200
    assert response.json()["delivery_receipt"]["reason"] == "receipt_not_persisted"
    assert settlement_calls == []


def test_probation_delivery_records_receipt_without_promoting_provider(
    monkeypatch,
    tmp_path,
):
    conn = sqlite3.connect(tmp_path / "probation-delivery.db")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    project = queue.create_video_project(
        conn,
        user_id=7126457028,
        asset_pack={"source": "product_video", "render_mode": "real"},
    )
    project_id = int(project["project_id"])
    job = queue.enqueue_video_render_job(
        conn,
        project_id=project_id,
        user_id=7126457028,
    )
    job_id = int(job["id"])
    payload = {
        "admission_mode": queue.PRODUCT_VIDEO_PROBATION_ADMISSION_MODE,
        "scene_tasks": [
            {"scene_index": 1, "clip_valid": True},
            {"scene_index": 2, "clip_valid": True},
        ],
        "scene_coverage_expected": 2,
        "scene_coverage_count": 2,
        "scene_clip_coverage_complete": True,
        "final_mp4_valid": True,
        "final_mp4_validated": True,
        "output_bytes": 1191503,
        "result_url": "",
        "provider_result_url": "",
    }
    conn.execute(
        "UPDATE video_jobs SET status='completed',result_json=? WHERE id=?",
        (json.dumps(payload), job_id),
    )
    conn.execute(
        "UPDATE video_projects SET status='completed' WHERE project_id=?",
        (project_id,),
    )
    conn.commit()
    monkeypatch.setattr(
        queue.video_uiflow3_execution_contract,
        "validate_execution_contract",
        lambda *_args, **_kwargs: {"ok": True, "applies": False, "blocker": ""},
    )

    receipt = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="905",
        success_message_id="905",
    )

    assert receipt["ok"] is True
    assert receipt["sent"] is True
    stored_job = queue.get_video_render_job(conn, job_id)
    stored_project = queue.get_video_project(conn, project_id)
    stored = json.loads(stored_job["result_json"])
    assert stored_project["video_delivery_message_id"] == "905"
    assert stored["delivery_succeeded"] is True
    assert stored["final_mp4_delivered"] is True
    assert stored["provider_health_promotion_eligible"] is False
    assert stored["probation_result"] == "pending"
    assert stored["probation_result_validation_blocker"]
    conn.close()
