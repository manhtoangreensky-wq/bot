import inspect
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import bot
import local_worker
from services import video_project_queue as queue


def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "video_queue.db")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _invoice_project(conn, user_id=101, total=200):
    project = queue.create_video_project(conn, user_id=user_id, profile_id="product_review", topic="demo sản phẩm")
    queue.advance_video_project_state(conn, project["project_id"], "draft_assets")
    queue.advance_video_project_state(conn, project["project_id"], "draft_prompt")
    queue.handle_video_project_text(conn, project["project_id"], "Hook, demo, lợi ích, CTA")
    queue.advance_video_project_state(conn, project["project_id"], "draft_addons")
    queue.advance_video_project_state(conn, project["project_id"], "draft_quality")
    queue.advance_video_project_state(conn, project["project_id"], "draft_scene_count")
    return queue.advance_video_project_state(conn, project["project_id"], "draft_invoice", strict=True) | {
        "project_id": project["project_id"],
        "user_id": user_id,
        "total": total,
    }


def test_video_project_created_at_planning(tmp_path):
    conn = _conn(tmp_path)
    project = queue.create_video_project(conn, user_id=1001, profile_id="storytelling", topic="câu chuyện thương hiệu")
    assert project["status"] == "draft_planning"
    assert project["project_uuid"].startswith("vprj_")
    assert project["created_at"]


def test_video_project_state_advances_in_order(tmp_path):
    conn = _conn(tmp_path)
    project = queue.create_video_project(conn, user_id=1002)
    updated = queue.advance_video_project_state(conn, project["project_id"], "draft_assets")
    assert updated["status"] == "draft_assets"
    try:
        queue.advance_video_project_state(conn, project["project_id"], "draft_quality")
    except ValueError as exc:
        assert "invalid_project_state_transition" in str(exc)
    else:
        raise AssertionError("state machine allowed a skipped public step")


def test_video_project_random_text_does_not_corrupt_state(tmp_path):
    conn = _conn(tmp_path)
    project = queue.create_video_project(conn, user_id=1003)
    queue.advance_video_project_state(conn, project["project_id"], "draft_assets")
    result = queue.handle_video_project_text(conn, project["project_id"], "random text in wrong step")
    assert result["changed"] is False
    unchanged = queue.get_video_project(conn, project["project_id"])
    assert unchanged["prompt_text"] in {"", None}
    assert unchanged["status"] == "draft_assets"


def test_video_project_menu_main_does_not_delete_draft(tmp_path):
    conn = _conn(tmp_path)
    project = queue.create_video_project(conn, user_id=1004)
    result = queue.menu_main_keeps_video_draft(conn, 1004)
    assert result["deleted"] is False
    assert result["active_project"]["project_id"] == project["project_id"]
    assert queue.get_video_project(conn, project["project_id"])


def test_video_project_continue_active_draft(tmp_path):
    conn = _conn(tmp_path)
    first = queue.create_video_project(conn, user_id=1005, topic="old")
    second = queue.create_video_project(conn, user_id=1005, topic="new")
    active = queue.get_active_video_project(conn, 1005)
    assert active["project_id"] == second["project_id"]
    assert active["project_id"] != first["project_id"]


def test_video_invoice_confirm_creates_video_job(tmp_path):
    conn = _conn(tmp_path)
    project = _invoice_project(conn, 1006, 200)
    queue.update_video_project(conn, project["project_id"], total_xu_estimated=200, invoice_json={"total_xu": 200})
    charged = []
    result = queue.confirm_video_project_invoice(
        conn,
        project_id=project["project_id"],
        user_id=1006,
        balance_xu=500,
        deduct_func=lambda uid, amount: charged.append((uid, amount)) or {"ok": True},
    )
    assert result["ok"] is True
    assert charged == [(1006, 200)]
    assert result["project"]["status"] == "queued_for_worker"
    assert result["job"]["status"] == "queued"
    assert result["job"]["job_type"] == "video_render"


def test_video_invoice_confirm_does_not_create_duplicate_job(tmp_path):
    conn = _conn(tmp_path)
    project = _invoice_project(conn, 1007, 200)
    queue.update_video_project(conn, project["project_id"], total_xu_estimated=200)
    first = queue.confirm_video_project_invoice(conn, project_id=project["project_id"], user_id=1007, balance_xu=500, deduct_func=lambda *_: {"ok": True})
    second = queue.confirm_video_project_invoice(conn, project_id=project["project_id"], user_id=1007, balance_xu=500, deduct_func=lambda *_: {"ok": True})
    assert first["job"]["id"] == second["job"]["id"]
    assert second["duplicate_prevented"] is True
    count = conn.execute("SELECT COUNT(*) FROM video_jobs WHERE project_id=?", (project["project_id"],)).fetchone()[0]
    assert count == 1


def test_video_job_claim_is_atomic(tmp_path):
    conn = _conn(tmp_path)
    project = _invoice_project(conn, 1008, 200)
    queue.update_video_project(conn, project["project_id"], total_xu_estimated=200)
    queue.confirm_video_project_invoice(conn, project_id=project["project_id"], user_id=1008, balance_xu=500, deduct_func=lambda *_: {"ok": True})
    first = queue.claim_next_video_job(conn, worker_id="worker-a")
    second = queue.claim_next_video_job(conn, worker_id="worker-b")
    assert first["status"] == "processing"
    assert first["locked_by"] == "worker-a"
    assert second == {}


def test_video_job_stale_processing_requeues_after_lease(tmp_path):
    conn = _conn(tmp_path)
    project = _invoice_project(conn, 1009, 200)
    queue.update_video_project(conn, project["project_id"], total_xu_estimated=200)
    queue.confirm_video_project_invoice(conn, project_id=project["project_id"], user_id=1009, balance_xu=500, deduct_func=lambda *_: {"ok": True})
    job = queue.claim_next_video_job(conn, worker_id="worker-a", now=datetime(2026, 1, 1, 0, 0, 0), lease_seconds=60)
    requeued = queue.requeue_stale_video_jobs(conn, now=datetime(2026, 1, 1, 0, 2, 0))
    assert requeued == 1
    refreshed = queue.get_video_render_job(conn, job["id"])
    assert refreshed["status"] == "queued"


def test_video_job_completed_not_reprocessed(tmp_path):
    conn = _conn(tmp_path)
    project = _invoice_project(conn, 1010, 200)
    queue.update_video_project(conn, project["project_id"], total_xu_estimated=200)
    queue.confirm_video_project_invoice(conn, project_id=project["project_id"], user_id=1010, balance_xu=500, deduct_func=lambda *_: {"ok": True})
    job = queue.claim_next_video_job(conn, worker_id="worker-a")
    queue.complete_video_job(conn, job_id=job["id"], final_video_path="final.mp4")
    assert queue.claim_next_video_job(conn, worker_id="worker-a") == {}


def test_video_worker_polls_queued_jobs(tmp_path):
    conn = _conn(tmp_path)
    project = _invoice_project(conn, 1011, 200)
    queue.update_video_project(conn, project["project_id"], total_xu_estimated=200)
    queue.confirm_video_project_invoice(conn, project_id=project["project_id"], user_id=1011, balance_xu=500, deduct_func=lambda *_: {"ok": True})
    job = queue.video_worker_poll_queued_job(conn, worker_id="worker-poll")
    assert job["status"] == "processing"
    assert inspect.getsource(local_worker.poll_video_render_job).count("/internal/video_worker/poll") == 1


def test_video_worker_updates_project_completed(tmp_path):
    conn = _conn(tmp_path)
    project = _invoice_project(conn, 1012, 200)
    queue.update_video_project(conn, project["project_id"], total_xu_estimated=200)
    queue.confirm_video_project_invoice(conn, project_id=project["project_id"], user_id=1012, balance_xu=500, deduct_func=lambda *_: {"ok": True})
    job = queue.claim_next_video_job(conn, worker_id="worker-a")
    result = queue.process_claimed_video_job(
        conn,
        job,
        lambda _project, _scenes: {"ok": True, "final_video_path": "final.mp4", "final_video_file_id": "tg-file"},
    )
    assert result["project"]["status"] == "completed"
    assert result["project"]["final_video_file_id"] == "tg-file"


def test_video_worker_failure_marks_failed_after_max_attempts(tmp_path):
    conn = _conn(tmp_path)
    project = _invoice_project(conn, 1013, 200)
    queue.update_video_project(conn, project["project_id"], total_xu_estimated=200)
    queue.confirm_video_project_invoice(conn, project_id=project["project_id"], user_id=1013, balance_xu=500, deduct_func=lambda *_: {"ok": True})
    conn.execute("UPDATE video_jobs SET max_attempts=1 WHERE project_id=?", (project["project_id"],))
    conn.commit()
    job = queue.claim_next_video_job(conn, worker_id="worker-a")
    result = queue.fail_video_job(conn, job_id=job["id"], error="renderer failed")
    assert result["status"] == "failed"
    assert result["project"]["status"] == "failed"


def test_no_fastapi_backgroundtasks_for_video_render():
    source = Path("bot.py").read_text(encoding="utf-8")
    video_worker_source = source[source.index("internal_video_worker_poll") : source.index("# ─── HEALTH CHECK")]
    assert "BackgroundTasks" not in video_worker_source
    assert "process_multiscene_video_pipeline" not in video_worker_source


def test_no_celery_or_rq_dependency_added():
    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in [Path("requirements.txt"), Path("pyproject.toml")]
        if path.exists()
    ).lower()
    assert "celery" not in combined
    assert "redis" not in combined
    assert "\nrq" not in combined
    assert "django-rq" not in combined


def test_no_public_render_before_confirm():
    source = inspect.getsource(bot.handle_video_product_callback)
    assert "process_multiscene_video_pipeline" not in source
    assert "create_local_worker_job" not in source
    assert "spend_fixed_credit_info" not in source
    assert "provider_called=False, xu_charged=0" in Path("bot.py").read_text(encoding="utf-8")
