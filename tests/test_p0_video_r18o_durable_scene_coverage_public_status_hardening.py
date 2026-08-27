from __future__ import annotations

import sqlite3
from pathlib import Path

from services import video_project_queue as queue


ROOT = Path(__file__).resolve().parents[1]


def _memory_conn():
    conn = sqlite3.connect(":memory:")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _product_project_and_job(conn, *, scene_count: int = 2, result: dict | None = None):
    project = queue.create_video_project(
        conn,
        user_id=12345,
        topic="demo product video",
        asset_pack={"source": "product_video", "real_renderer_required": True, "provider_call": True},
    )
    invoice = {
        "scene_count": scene_count,
        "user_visible_price_xu": 300,
        "persisted_quoted_price_xu": 300,
        "customer_charge_planned_xu": 300,
        "wallet_charge_amount_xu": 300,
        "orchestration_mode": "per_scene_8s" if scene_count > 1 else "single_task_legacy",
    }
    project = queue.update_video_project(
        conn,
        project["project_id"],
        status="queued_for_worker",
        invoice_json=queue._json_dumps(invoice),
        total_xu_estimated=300,
        scene_count=scene_count,
        is_confirmed=1,
    )
    job = queue.enqueue_video_render_job(conn, project_id=project["project_id"], user_id=project["user_id"])
    if result:
        conn.execute(
            "UPDATE video_jobs SET result_json=?, progress_percent=? WHERE id=?",
            (queue._json_dumps(result), int(result.get("progress_percent") or 85), int(job["id"])),
        )
        conn.commit()
        job = queue.get_video_render_job(conn, int(job["id"]))
    return queue.get_video_project(conn, int(project["project_id"])), job


def _job117_one_clip_result(mp4: Path) -> dict:
    mp4.write_bytes(b"valid-single-clip")
    return {
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "final_video_path": str(mp4),
        "final_mp4_valid": True,
        "result_url_present": True,
        "artifact_size": mp4.stat().st_size,
        "concat_attempted": False,
        "concat_duration_seconds": 8.0,
        "scene_result_urls_by_index": {},
        "scene_clip_validation_by_index": {},
        "provider_task_ids": ["task-scene-unknown"],
        "progress_percent": 85,
    }


def test_video_public_status_source_has_chunk_and_section_guards():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    block = source[source.index("def video_public_status_payload") : source.index("VIDEO_GATE_FEATURES")]

    assert "video_public_status_section_errors" in block
    assert "def video_public_status_chunks" in block
    assert "video_public_status_chunked" in block
    assert "video_public_status_section_error=send" in source
    assert "3900" in block


def test_job117_one_clip_does_not_satisfy_multiscene_coverage(tmp_path):
    mp4 = tmp_path / "scene1.mp4"
    project = {
        "scene_count": 2,
        "invoice_json": queue._json_dumps({"scene_count": 2, "orchestration_mode": "per_scene_8s"}),
    }
    result = _job117_one_clip_result(mp4)

    coverage = queue.product_video_scene_coverage_state(project, {"id": 117}, result)

    assert coverage["scene_coverage_expected"] == 2
    assert coverage["scene_coverage_count"] == 0
    assert coverage["scene_coverage_valid"] is False
    assert coverage["delivery_blocked_by_scene_coverage"] is True
    assert coverage["artifact_valid_for_charge_after_coverage"] is False
    assert coverage["unknown_scene_task_ignored_for_coverage"] is True
    assert coverage["missing_scene_indexes"] == [1, 2]


def test_reused_valid_multiscene_manifest_is_ready_for_delivery(tmp_path):
    final = tmp_path / "final_output.mp4"
    final.write_bytes(b"reused-valid-two-scene-final")
    result = {
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "final_video_path": str(final),
        "final_mp4_valid": True,
        "final_reused_from_manifest": True,
        "concat_attempted": False,
        "concat_output_valid": True,
        "concat_status": "completed",
        "scene_tasks": [
            {"scene_index": 1, "status": "scene_clip_validated", "clip_valid": True, "clip_bytes": 123},
            {"scene_index": 2, "status": "scene_clip_validated", "clip_valid": True, "clip_bytes": 456},
        ],
    }

    coverage = queue.product_video_scene_coverage_state(
        {"scene_count": 2},
        {"id": 25, "status": "processing"},
        result,
    )

    assert coverage["concat_attempted"] is False
    assert coverage["concat_output_valid"] is True
    assert coverage["scene_coverage_valid_bool"] is True
    assert coverage["final_mp4_valid"] is True
    assert coverage["delivery_blocked_by_scene_coverage"] is False
    assert coverage["aggregate_job_status"] == "ready_for_delivery"
    assert coverage["final_duration_coverage_reason"] == ""


def test_complete_job_blocks_delivery_when_multiscene_coverage_missing(tmp_path):
    conn = _memory_conn()
    mp4 = tmp_path / "scene1.mp4"
    project, job = _product_project_and_job(conn, scene_count=2)
    result = _job117_one_clip_result(mp4)

    completed = queue.complete_video_job(conn, job_id=int(job["id"]), final_video_path=str(mp4), result=result)
    updated_job = completed["job"]
    updated_project = completed["project"]
    payload = queue._json_loads(updated_job["result_json"], {})

    assert completed["reason"] == "missing_scene_coverage_waiting"
    assert updated_job["status"] == "processing"
    assert updated_project["video_terminal_state"] == "final_rendering"
    assert payload["delivery_blocked_by_scene_coverage"] is True
    assert payload["artifact_valid_for_charge_after_coverage"] is False
    assert payload["continue_polling"] is True
    assert payload["terminal_state"] == "final_rendering"


def test_note_delivery_result_does_not_mark_telegram_failed_for_missing_coverage(tmp_path):
    conn = _memory_conn()
    mp4 = tmp_path / "scene1.mp4"
    _project, job = _product_project_and_job(conn, scene_count=2, result=_job117_one_clip_result(mp4))

    noted = queue.note_video_delivery_result(
        conn,
        job_id=int(job["id"]),
        sent=False,
        reason="final_duration_short_scene_coverage_missing",
    )
    payload = queue._json_loads(noted["job"]["result_json"], {})

    assert noted["delivery_blocked_by_scene_coverage"] is True
    assert noted["job"]["status"] == "processing"
    assert noted["project"]["video_terminal_state"] == "final_rendering"
    assert payload["telegram_delivery_status"] == "delivery_blocked_by_scene_coverage"
    assert payload["terminal_state"] == "final_rendering"
    assert payload["continue_polling"] is True


def test_missing_scene_timeout_fails_no_charge_without_telegram_delivery_failed(tmp_path):
    conn = _memory_conn()
    mp4 = tmp_path / "scene1.mp4"
    result = _job117_one_clip_result(mp4) | {
        "scene_coverage_elapsed_seconds": 1300,
        "missing_scene_timeout_seconds": 60,
    }
    _project, job = _product_project_and_job(conn, scene_count=2, result=result)

    noted = queue.note_video_delivery_result(conn, job_id=int(job["id"]), sent=False, reason="missing_scene_coverage_timeout")
    payload = queue._json_loads(noted["job"]["result_json"], {})

    assert noted["project"]["video_terminal_state"] == "failed_no_charge"
    assert noted["job"]["status"] == "failed"
    assert payload["terminal_state"] == "failed_no_charge"
    assert payload["provider_error"] == "missing_scene_coverage_timeout"
    assert payload["telegram_delivery_status"] == "delivery_blocked_by_scene_coverage"
    assert payload["continue_polling"] is False


def test_multiscene_both_scene_clips_valid_allows_charge_after_delivery(tmp_path):
    final = tmp_path / "final.mp4"
    final.write_bytes(b"valid-final-mp4")
    result = {
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "final_video_path": str(final),
        "final_mp4_valid": True,
        "final_delivered": True,
        "concat_attempted": True,
        "concat_output_valid": True,
        "concat_status": "completed",
        "scene_clip_validation_by_index": {
            "1": {"ok": True, "bytes": 123},
            "2": {"ok": True, "bytes": 456},
        },
    }

    decision = queue.product_video_delivery_charge_decision(
        {
            "scene_count": 2,
            "video_delivered_at": "2026-07-10 10:00:00",
            "final_video_path": str(final),
            "invoice_json": queue._json_dumps(
                {
                    "scene_count": 2,
                    "user_visible_price_xu": 300,
                    "persisted_quoted_price_xu": 300,
                    "customer_charge_planned_xu": 300,
                }
            ),
        },
        {"id": 117},
        result,
    )

    assert decision["ok"] is True
    assert decision["amount_xu"] == 300
    assert decision["charge_idempotency_key"] == "product_video_final_delivery:117:300"


def test_single_scene_late_success_preserved(tmp_path):
    final = tmp_path / "final.mp4"
    final.write_bytes(b"valid-one-scene")
    decision = queue.product_video_delivery_charge_decision(
        {
            "scene_count": 1,
            "video_delivered_at": "2026-07-10 10:00:00",
            "final_video_path": str(final),
            "invoice_json": queue._json_dumps(
                {
                    "scene_count": 1,
                    "user_visible_price_xu": 300,
                    "persisted_quoted_price_xu": 300,
                    "customer_charge_planned_xu": 300,
                }
            ),
        },
        {"id": 116},
        {"final_video_path": str(final), "final_mp4_valid": True, "final_delivered": True},
    )

    assert decision["ok"] is True
    assert decision["amount_xu"] == 300


def test_no_real_provider_calls_in_r18o_tests():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "url" + "open",
        "provider" + "_smoke",
    )
    assert all(token not in source for token in forbidden)
