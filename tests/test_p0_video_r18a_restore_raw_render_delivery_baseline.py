import json
import sqlite3
from pathlib import Path

from services import remote_worker_api
from services import video_project_queue as queue
from services import video_real_render_connector as connector


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
QUEUE_SOURCE = (ROOT / "services" / "video_project_queue.py").read_text(encoding="utf-8")
REMOTE_WORKER_API_SOURCE = (ROOT / "services" / "remote_worker_api.py").read_text(encoding="utf-8")
CONNECTOR_SOURCE = (ROOT / "services" / "video_real_render_connector.py").read_text(encoding="utf-8")


def _conn(tmp_path):
    conn = sqlite3.connect(tmp_path / "r18a_video_queue.db")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _product_project(conn, *, user_id=1818, scene_count=2, total_xu=400, orchestration_mode=""):
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
    if orchestration_mode:
        asset_pack["orchestration_mode"] = orchestration_mode
        asset_pack["provider_orchestration_mode"] = orchestration_mode
        invoice["orchestration_mode"] = orchestration_mode
        invoice["provider_orchestration_mode"] = orchestration_mode
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


def _hydrated_job(*, scene_count=2, persisted_result=None, orchestration_mode=""):
    asset_pack = {
        "source": "product_video",
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "product_type": "video_trend",
        "video_product_type": "video_trend",
        "original_user_prompt": "video theo trend ve san pham",
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
        "provider_order": "shopaikey_video,key4u_video",
    }
    invoice = {
        "source": "product_video",
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "scene_count": scene_count,
        "scene_duration_seconds": 8,
        "duration_seconds": scene_count * 8,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
    }
    if orchestration_mode:
        asset_pack["orchestration_mode"] = orchestration_mode
        asset_pack["provider_orchestration_mode"] = orchestration_mode
        invoice["orchestration_mode"] = orchestration_mode
        invoice["provider_orchestration_mode"] = orchestration_mode
    return {
        "id": 180,
        "job_id": 180,
        "job_type": "video_render",
        "status": "queued",
        "quality_tier": 300,
        "result_json": json.dumps(persisted_result or {}, ensure_ascii=False),
        "project": {
            "project_id": 1180,
            "user_id": 123,
            "profile_id": "video_trend",
            "topic": "trend product",
            "prompt_text": "make a product trend video",
            "ratio": "9:16",
            "scene_count": scene_count,
            "quality_tier": 300,
            "asset_pack_json": json.dumps(asset_pack, ensure_ascii=False),
            "invoice_json": json.dumps(invoice, ensure_ascii=False),
            "addon_plan_json": "{}",
            "total_xu_estimated": 400,
        },
    }


def test_public_confirm_defaults_to_historical_multiclip_concat_for_multiscene(tmp_path):
    conn = _conn(tmp_path)
    project = _product_project(conn, scene_count=2)

    result = queue.confirm_video_project_invoice(conn, project_id=int(project["project_id"]), user_id=int(project["user_id"]))

    assert result["ok"] is True
    payload = _payload(result["job"])
    assert payload["orchestration_mode"] == "per_scene_8s"
    assert payload["provider_orchestration_mode"] == "per_scene_8s"
    assert payload["render_pipeline_mode"] == "historical_multi_clip_concat"
    assert payload["raw_render_delivery_baseline"] is False
    assert payload["scene_count"] == 2
    assert payload["duration_seconds"] == 16
    assert len(payload["scene_tasks"]) == 2
    assert len(payload["provider_scene_tasks"]) == 2
    assert payload["scene_tasks_created_count"] == 2
    assert payload["clip_count"] == 2
    assert payload["clip_duration_seconds"] == 8
    assert payload["final_concat_required"] is True
    assert payload["provider_submit_called"] is False
    assert payload["charge"] == 0


def test_worker_payload_defaults_to_historical_multiclip_concat_for_multiscene():
    payload = remote_worker_api.build_worker_job_payload(_hydrated_job(scene_count=2))

    assert payload["source"] == "product_video"
    assert payload["orchestration_mode"] == "per_scene_8s"
    assert payload["provider_orchestration_mode"] == "per_scene_8s"
    assert payload["render_pipeline_mode"] == "historical_multi_clip_concat"
    assert payload["raw_render_delivery_baseline"] is False
    assert payload["scene_count"] == 2
    assert payload["duration_seconds"] == 16
    assert len(payload["provider_scene_tasks"]) == 2
    assert payload["scene_tasks_created_count"] == 2
    assert payload["clip_count"] == 2
    assert payload["final_concat_required"] is True


def test_explicit_per_scene_opt_in_still_creates_scene_records(tmp_path):
    conn = _conn(tmp_path)
    project = _product_project(conn, scene_count=2, orchestration_mode="per_scene_8s")

    result = queue.confirm_video_project_invoice(conn, project_id=int(project["project_id"]), user_id=int(project["user_id"]))
    payload = _payload(result["job"])

    assert payload["orchestration_mode"] == "per_scene_8s"
    assert payload["scene_tasks_created_count"] == 2
    assert len(payload["provider_scene_tasks"]) == 2
    worker_payload = remote_worker_api.build_worker_job_payload(_hydrated_job(scene_count=2, orchestration_mode="per_scene_8s"))
    assert worker_payload["orchestration_mode"] == "per_scene_8s"
    assert len(worker_payload["provider_scene_tasks"]) == 2


def test_connector_default_multiscene_but_existing_legacy_task_remains_single_task():
    assert connector.product_video_orchestration_mode({"source": "product_video", "scene_count": 2}) == "per_scene_8s"
    assert (
        connector.product_video_orchestration_mode(
            {
                "source": "product_video",
                "scene_count": 2,
                "provider_pending_task_id": "single-task",
                "provider_pending_request_job_id": "180",
            }
        )
        == "single_task_legacy"
    )
    assert (
        connector.product_video_orchestration_mode(
            {
                "source": "product_video",
                "scene_count": 2,
                "provider_scene_tasks": [{"scene_index": 1, "request_job_id": "180-1"}],
            }
        )
        == "per_scene_8s"
    )


def test_r17_multiscene_downgrade_copy_and_gate_removed():
    combined = "\n".join([BOT_SOURCE, QUEUE_SOURCE, REMOTE_WORKER_API_SOURCE, CONNECTOR_SOURCE])
    assert "safe_live_scene_count" not in combined
    assert "chỉ mở 1 cảnh" not in combined
    assert "hệ thống chỉ mở 1 cảnh" not in combined
    assert "multiscene_live_ready" not in combined


def test_no_real_provider_usage_in_r18a_tests():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "video_provider" + "_smoke",
        "run_provider" + "_generation(",
        "submit_video" + "_job(",
    )
    assert all(token not in source for token in forbidden)
