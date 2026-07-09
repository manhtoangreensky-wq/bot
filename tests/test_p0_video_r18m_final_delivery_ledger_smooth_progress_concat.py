import asyncio
import sqlite3
from pathlib import Path

from services import product_progress_status
from services import video_project_queue as queue
from services import video_real_render_connector as connector


ROOT = Path(__file__).resolve().parents[1]


def _memory_conn():
    conn = sqlite3.connect(":memory:")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _product_project_and_job(conn, *, invoice=None, result=None):
    project = queue.create_video_project(
        conn,
        user_id=12345,
        topic="demo product video",
        asset_pack={"source": "product_video", "real_renderer_required": True},
    )
    invoice = invoice or {
        "scene_count": 1,
        "total_xu": 300,
        "user_visible_price_xu": 300,
        "persisted_quoted_price_xu": 300,
        "customer_charge_planned_xu": 300,
        "wallet_charge_amount_xu": 300,
    }
    project = queue.update_video_project(
        conn,
        project["project_id"],
        status="queued_for_worker",
        invoice_json=queue._json_dumps(invoice),
        total_xu_estimated=300,
        is_confirmed=1,
    )
    job = queue.enqueue_video_render_job(conn, project_id=project["project_id"], user_id=project["user_id"])
    if result:
        conn.execute(
            "UPDATE video_jobs SET result_json=?, progress_percent=? WHERE id=?",
            (queue._json_dumps(result), int(result.get("progress_percent") or 39), int(job["id"])),
        )
        conn.commit()
        job = queue.get_video_render_job(conn, int(job["id"]))
    return queue.get_video_project(conn, int(project["project_id"])), job


def test_job_114_delivered_single_scene_charge_decision_and_progress(tmp_path):
    mp4 = tmp_path / "final.mp4"
    mp4.write_bytes(b"valid-mp4-fixture")
    project = {
        "video_delivered_at": "2026-07-09 12:00:00",
        "video_delivery_message_id": "tg-114",
        "final_video_path": str(mp4),
        "invoice_json": queue._json_dumps(
            {
                "user_visible_price_xu": 300,
                "persisted_quoted_price_xu": 300,
                "customer_charge_planned_xu": 300,
                "wallet_charge_amount_xu": 300,
            }
        ),
    }
    job = {"id": 114, "progress_percent": 39}
    result = {
        "final_video_path": str(mp4),
        "final_mp4_valid": True,
        "final_delivered": True,
        "artifact_valid_for_charge": True,
    }

    decision = queue.product_video_delivery_charge_decision(project, job, result)
    assert decision["ok"] is True
    assert decision["amount_xu"] == 300
    assert decision["charge_idempotency_key"] == "product_video_final_delivery:114:300"

    progress = queue.reconcile_provider_progress_telemetry(
        {"status": "completed", "progress_percent": 39},
        {**result, "delivery_succeeded": True, "progress_percent": 39},
        refresh_source="r18m_job_114",
    )
    assert progress["final_status_after_reconcile"] == "completed"
    assert progress["final_progress_after_reconcile"] == 100


def test_charge_decision_is_idempotent(tmp_path):
    mp4 = tmp_path / "final.mp4"
    mp4.write_bytes(b"valid-mp4-fixture")
    decision = queue.product_video_delivery_charge_decision(
        {"video_delivered_at": "2026-07-09 12:00:00", "final_video_path": str(mp4)},
        {"id": 114},
        {
            "final_video_path": str(mp4),
            "final_mp4_valid": True,
            "wallet_charge_recorded": True,
            "charged_amount_xu": 300,
            "charge_tx_id": "product_video_final_delivery:114:300",
        },
    )
    assert decision["ok"] is True
    assert decision["already_charged"] is True
    assert decision["amount_xu"] == 300


def test_delivery_failed_keeps_charge_blocked(tmp_path):
    mp4 = tmp_path / "final.mp4"
    mp4.write_bytes(b"valid-mp4-fixture")
    decision = queue.product_video_delivery_charge_decision(
        {"final_video_path": str(mp4)},
        {"id": 115},
        {
            "final_video_path": str(mp4),
            "final_mp4_valid": True,
            "final_delivered": False,
            "telegram_delivery_status": "telegram_delivery_failed",
        },
    )
    assert decision["ok"] is False
    assert decision["amount_xu"] == 0
    assert decision["charge_skip_reason"] == "delivery_required_before_charge"


def test_note_delivery_result_persists_completed_progress_100(tmp_path):
    conn = _memory_conn()
    mp4 = tmp_path / "final.mp4"
    mp4.write_bytes(b"valid-mp4-fixture")
    _project, job = _product_project_and_job(
        conn,
        result={"final_video_path": str(mp4), "final_mp4_valid": True, "progress_percent": 39},
    )

    noted = queue.note_video_delivery_result(conn, job_id=int(job["id"]), sent=True, delivery_message_id="tg-114")

    updated_job = noted["job"]
    updated_result = queue._json_loads(updated_job["result_json"], {})
    assert updated_job["status"] == "completed"
    assert updated_job["progress_percent"] == 100
    assert updated_result["final_delivered"] is True
    assert updated_result["telegram_delivery_status"] == "sent"


def test_progress_does_not_mark_completed_until_delivery(tmp_path):
    mp4 = tmp_path / "final.mp4"
    mp4.write_bytes(b"valid-mp4-fixture")
    waiting = product_progress_status.product_progress_debug_payload(
        "multiscene_video",
        "115",
        {
            "status": "completed",
            "progress_percent": 39,
            "final_video_path": str(mp4),
            "final_mp4_valid": True,
        },
    )
    assert waiting["terminal_state"] != "delivered"
    assert 85 <= waiting["percent"] <= 95

    delivered = product_progress_status.product_progress_debug_payload(
        "multiscene_video",
        "114",
        {
            "status": "completed",
            "progress_percent": 39,
            "final_video_path": str(mp4),
            "final_mp4_valid": True,
            "final_delivered": True,
        },
    )
    assert delivered["terminal_state"] == "delivered"
    assert delivered["percent"] == 100


def test_job_115_single_scene_result_does_not_complete_multiscene(monkeypatch, tmp_path):
    async def fake_render(scene, raw_path, provider_order):
        if int(scene.scene_id) == 1:
            Path(raw_path).write_bytes(b"scene-1")
            return {"ok": True, "output_path": raw_path, "scene_index": 1, "result_url_present": True}
        raise connector.RealVideoRenderError(
            "provider_in_progress",
            diagnostics={"scene_index": 2, "continue_polling": True, "provider_error": "provider_in_progress"},
        )

    monkeypatch.setattr(connector, "_render_scene_async", fake_render)
    result = connector._run_per_scene_provider_orchestrator(
        {
            "id": 115,
            "job_id": 115,
            "source": "product_video",
            "product_video": True,
            "scene_count": 2,
            "orchestration_mode": "per_scene_8s",
            "public_user_confirmed": True,
            "invoice_confirmed": True,
        },
        str(tmp_path),
        provider_order=["shopaikey_video"],
        provider_events=[],
        debug_results=[],
    )

    assert result["continue_polling"] is True
    assert result["terminal_state"] == "final_rendering"
    assert result["scene_coverage_expected"] == 2
    assert result["scene_coverage_valid"] == 1
    assert result["concat_attempted"] is False
    assert result["concat_status"] == "waiting_for_clips"


def test_job_115_two_scene_outputs_attempt_concat(monkeypatch, tmp_path):
    async def fake_render(scene, raw_path, provider_order):
        Path(raw_path).write_bytes(f"scene-{scene.scene_id}".encode("utf-8"))
        return {"ok": True, "output_path": raw_path, "scene_index": int(scene.scene_id), "result_url_present": True}

    final_path = tmp_path / "final.mp4"

    def fake_concat(job, workspace, *, render_video_func, bgm_audio_path=None):
        final_path.write_bytes(b"final-16s")
        return {"ok": True, "final_video_path": str(final_path), "duration_sec": 16.0, "created_files": [str(final_path)]}

    monkeypatch.setattr(connector, "_render_scene_async", fake_render)
    monkeypatch.setattr(connector, "_run_multiscene_render", fake_concat)

    result = connector._run_per_scene_provider_orchestrator(
        {
            "id": 115,
            "job_id": 115,
            "source": "product_video",
            "product_video": True,
            "scene_count": 2,
            "orchestration_mode": "per_scene_8s",
            "public_user_confirmed": True,
            "invoice_confirmed": True,
        },
        str(tmp_path / "work"),
        provider_order=["shopaikey_video"],
        provider_events=[],
        debug_results=[],
    )

    assert result["ok"] is True
    assert result["concat_attempted"] is True
    assert result["concat_output_valid"] is True
    assert result["scene_coverage_valid"] == 2
    assert result["final_video_path"] == str(final_path)


def test_public_status_source_contract_handles_missing_health_fields():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    block = source[source.index("def video_public_status_text") : source.index("VIDEO_GATE_FEATURES")]
    assert "isinstance(payload.get(\"product_video_provider_health\"), dict)" in block
    assert "health_summary.get(\"shopaikey_video\")" in block
    assert "shopaikey_health.get('health_status')" in block
    assert "payload['frame_gate']" not in block


def test_multiscene_uses_per_scene_without_legacy_single_task_marker():
    mode = connector.product_video_orchestration_mode(
        {
            "source": "product_video",
            "product_video": True,
            "scene_count": 2,
        }
    )
    assert mode == connector.PRODUCT_VIDEO_ORCHESTRATION_MODE_PER_SCENE_8S


def test_no_real_provider_calls_in_r18m_tests():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "urllib.request." + "urlopen",
        "provider" + "_smoke",
    )
    assert all(token not in source for token in forbidden)
