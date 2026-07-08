import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from services import remote_worker_api
from services import video_project_queue as queue


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
REMOTE_WORKER_SOURCE = (ROOT / "remote_worker.py").read_text(encoding="utf-8")
REMOTE_WORKER_API_SOURCE = (ROOT / "services" / "remote_worker_api.py").read_text(encoding="utf-8")
QUEUE_SOURCE = (ROOT / "services" / "video_project_queue.py").read_text(encoding="utf-8")


def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "r16c_video_queue.db")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _product_project(conn, *, user_id=9090, scene_count=2, total_xu=400):
    asset_pack = {
        "source": "product_video",
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "product_type": "video_trend",
        "video_product_type": "video_trend",
        "original_user_prompt": "Video theo trend cho san pham",
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
        "provider_order": "shopaikey_video,key4u_video",
    }
    invoice = {
        **asset_pack,
        "scene_count": scene_count,
        "scene_duration_seconds": 8,
        "duration_seconds": scene_count * 8,
        "total_xu": total_xu,
    }
    project = queue.create_video_project(
        conn,
        user_id=user_id,
        profile_id="video_trend",
        topic="trend product",
        ratio="9:16",
        asset_pack=asset_pack,
    )
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="draft_invoice",
        invoice_json=invoice,
        scene_count=scene_count,
        prompt_text="make a trend product video",
        total_xu_estimated=total_xu,
    )
    return queue.get_video_project(conn, int(project["project_id"]))


def _payload(job):
    return json.loads(str(job.get("result_json") or "{}"))


def test_public_final_confirm_creates_scene_records_and_dispatch_metadata(tmp_path):
    conn = _conn(tmp_path)
    project = _product_project(conn, scene_count=2)

    result = queue.confirm_video_project_invoice(conn, project_id=int(project["project_id"]), user_id=int(project["user_id"]))

    assert result["ok"] is True
    job = result["job"]
    payload = _payload(job)
    assert job["status"] == "queued"
    assert job["progress_percent"] == 10
    assert payload["public_confirm_kickoff_attempted"] is True
    assert payload["public_confirm_kickoff_success"] is True
    assert payload["orchestration_mode"] == "per_scene_8s"
    assert payload["scene_duration_seconds"] == 8
    assert payload["scene_count"] == 2
    assert payload["scene_tasks_created_count"] == 2
    assert len(payload["scene_tasks"]) == 2
    assert payload["scene_tasks"][0]["request_job_id"] == f"{job['id']}-1"
    assert payload["scene_tasks"][1]["request_job_id"] == f"{job['id']}-2"
    assert payload["worker_dispatch_attempted"] is True
    assert payload["worker_dispatch_success"] is True
    assert payload["actual_processor"] == "remote_worker"
    assert payload["worker_service_mode"] == "owner_product_video"
    assert payload["provider_chain_resolved"] is True
    assert payload["configured_provider_chain"][:2] == ["shopaikey_video", "key4u_video"]
    assert payload["next_poll_scheduled"] is True
    assert payload["charge"] == 0
    assert payload["provider_submit_called"] is False


def test_owner_product_worker_claims_public_confirmed_product_video(tmp_path):
    conn = _conn(tmp_path)
    project = _product_project(conn, scene_count=2)
    queue.confirm_video_project_invoice(conn, project_id=int(project["project_id"]), user_id=int(project["user_id"]))

    claim = remote_worker_api.claim_remote_worker_job(
        conn,
        worker_id="vps-toanaas-01",
        capabilities=["owner_product_video", "product_video", "ffmpeg"],
        owner_product_video_only=True,
    )

    assert claim["ok"] is True
    job = claim["job"]
    assert job
    assert job["actual_processor"] == "remote_worker"
    assert job["worker_service_mode"] == "owner_product_video"
    assert job["public_user_confirmed"] is True
    assert job["original_submit_source"] == "public_user_final_confirm"
    assert job["orchestration_mode"] == "per_scene_8s"
    assert job["scene_count"] == 2
    assert job["scene_duration_seconds"] == 8
    assert job["scene_tasks_created_count"] == 2
    assert len(job["scene_tasks"]) == 2
    assert job["configured_provider_chain"][:2] == ["shopaikey_video", "key4u_video"]


def test_provider_chain_missing_fails_clean_no_charge(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_CHAIN", ",")
    conn = _conn(tmp_path)
    project = _product_project(conn, scene_count=2)

    result = queue.confirm_video_project_invoice(conn, project_id=int(project["project_id"]), user_id=int(project["user_id"]))

    assert result["ok"] is True
    job = result["job"]
    payload = _payload(job)
    assert job["status"] == "failed"
    assert payload["provider_chain_resolved"] is False
    assert payload["worker_dispatch_attempted"] is True
    assert payload["worker_dispatch_success"] is False
    assert payload["worker_dispatch_blocker"] == "provider_chain_missing_no_charge"
    assert payload["provider_error"] == "provider_chain_missing_no_charge"
    assert payload["charge"] == 0
    assert payload["provider_submit_called"] is False


def test_registry_missing_db_payload_still_hydrates_scene_tasks_for_worker(tmp_path):
    conn = _conn(tmp_path)
    project = _product_project(conn, scene_count=2)
    result = queue.confirm_video_project_invoice(conn, project_id=int(project["project_id"]), user_id=int(project["user_id"]))
    conn.execute("UPDATE video_jobs SET result_json='' WHERE id=?", (int(result["job"]["id"]),))
    conn.commit()

    raw_job = queue.get_video_render_job(conn, int(result["job"]["id"]))
    hydrated = queue.hydrate_video_job_payload(conn, raw_job)
    payload = remote_worker_api.build_worker_job_payload(hydrated)

    assert payload["scene_tasks_created_count"] == 2
    assert len(payload["scene_tasks"]) == 2
    assert payload["provider_chain_resolved"] is True
    assert payload["configured_provider_chain"]
    assert payload["provider_submit_called"] is not True


def test_unclaimed_confirmed_job_fails_dispatch_clean_no_charge(tmp_path):
    conn = _conn(tmp_path)
    project = _product_project(conn, scene_count=2)
    result = queue.confirm_video_project_invoice(conn, project_id=int(project["project_id"]), user_id=int(project["user_id"]))
    job_id = int(result["job"]["id"])
    stale_time = queue.now_text(datetime.now() - timedelta(minutes=10))
    conn.execute("UPDATE video_jobs SET created_at=?, updated_at=? WHERE id=?", (stale_time, stale_time, job_id))
    conn.commit()

    failed = remote_worker_api.fail_stale_product_video_jobs(
        conn,
        max_wait_seconds=60,
        now=datetime.now(),
        job_id=job_id,
    )

    assert failed == 1
    job = queue.get_video_render_job(conn, job_id)
    payload = _payload(job)
    assert job["status"] == "failed"
    assert payload["worker_dispatch_blocker"] == "queued_dispatch_failed_no_charge"
    assert payload["provider_submit_called"] is False
    assert payload["provider_task_id_saved"] is False
    assert payload["charge"] == 0
    assert payload["charged_xu"] == 0


def test_debug_status_and_worker_sources_include_r16c_contract():
    assert "public_confirm_kickoff_attempted" in BOT_SOURCE
    assert "worker_dispatch_attempted" in BOT_SOURCE
    assert "dispatch_status" in BOT_SOURCE
    assert "provider_chain_resolved" in BOT_SOURCE
    assert "public_confirm_kickoff_success" in QUEUE_SOURCE
    assert "owner_product_video" in REMOTE_WORKER_SOURCE
    assert "_product_video_public_confirmed_for_owner_worker" in REMOTE_WORKER_API_SOURCE


def test_no_real_provider_calls_in_r16c_tests():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "provider" + "_smoke",
        "run_provider" + "_generation(",
        "submit_video" + "_job(",
    )
    assert all(token not in source for token in forbidden)
