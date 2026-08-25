from __future__ import annotations

import json
import sqlite3

from services import remote_worker_api
from services import video_project_queue as queue


def test_recovery_completion_keeps_durable_scene_ledger_when_worker_sends_empty_placeholders(
    monkeypatch,
    tmp_path,
):
    conn = sqlite3.connect(tmp_path / "recovery-completion-ledger.db")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    project = queue.create_video_project(
        conn,
        user_id=919_019,
        profile_id="video_ai_prompt",
        topic="two-scene recovery completion",
        asset_pack={
            "source": "product_video",
            "product_type": "video_ai_prompt",
            "render_mode": "real",
            "public_user": True,
        },
    )
    project_id = int(project["project_id"])
    queue.update_video_project(
        conn,
        project_id,
        status="processing",
        is_confirmed=1,
        scene_count=2,
        invoice_json={"scene_count": 2, "duration_seconds": 16},
    )
    job = queue.enqueue_video_render_job(
        conn,
        project_id=project_id,
        user_id=919_019,
        max_attempts=3,
    )
    job_id = int(job["id"])
    durable_scenes = [
        {
            "scene_index": index,
            "provider_task_id": f"task-scene-{index}",
            "winning_task_id": f"task-scene-{index}",
            "status": "scene_clip_validated",
            "clip_valid": True,
            "clip_bytes": 1024 * index,
        }
        for index in (1, 2)
    ]
    persisted = {
        "source": "product_video",
        "product_video": True,
        "public_user": True,
        "render_mode": "real",
        "scene_count": 2,
        "recovery_existing_tasks_only": True,
        "provider_submit_allowed": False,
        "scene_tasks": durable_scenes,
        "provider_scene_tasks": durable_scenes,
        "scene_tasks_total": 2,
        "scene_tasks_completed": 2,
        "scenes_total": 2,
        "scenes_done": 2,
        "charged_xu": 0,
    }
    conn.execute(
        """UPDATE video_jobs
              SET status='processing',locked_by='vps-toanaas-01',attempts=3,
                  result_json=?,progress_percent=90,progress_message='uploading final video'
            WHERE id=?""",
        (json.dumps(persisted), job_id),
    )
    conn.commit()

    monkeypatch.setattr(
        queue.video_final_output,
        "validate_final_video_output",
        lambda **_kwargs: {
            "ok": True,
            "bytes": 4096,
            "duration": 16.0,
            "has_video": True,
            "has_audio": False,
        },
    )
    monkeypatch.setattr(
        queue,
        "product_video_duration_contract",
        lambda *_args, **_kwargs: {
            "ok": True,
            "reason": "",
            "expected_duration_seconds": 16.0,
            "actual_duration_seconds": 16.0,
        },
    )
    final_path = tmp_path / "final_output.mp4"
    final_path.write_bytes(b"real-two-scene-product-video")

    completed = remote_worker_api.complete_remote_worker_job(
        conn,
        worker_id="vps-toanaas-01",
        job_id=job_id,
        final_video_path=str(final_path),
        result={
            "ok": True,
            "source": "product_video",
            "product_video": True,
            "render_mode": "real",
            "renderer": "remote_worker_real_render_route",
            "connector_renderer": "provider_scene_video",
            "visual_classification": "final_ai_video",
            "visual_source": "provider_mp4",
            "final_mp4_valid": True,
            "concat_attempted": True,
            "concat_output_valid": True,
            "scene_tasks": [],
            "provider_scene_tasks": [],
            "scene_tasks_total": 0,
            "scene_tasks_completed": 0,
            "scenes_total": 0,
            "scenes_done": 0,
        },
    )

    assert completed["ok"] is True, completed
    stored = json.loads(completed["job"]["result_json"])
    assert stored["completed_scene_count"] == 2
    assert stored["unresolved_scene_indexes"] == []
    assert [item["scene_index"] for item in stored["scene_tasks"]] == [1, 2]
    assert stored["recovery_existing_tasks_only"] is True
    assert stored["provider_submit_allowed"] is False
    assert stored["charged_xu"] == 0
    conn.close()
