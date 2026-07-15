from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from services import remote_worker_api
from services import video_idea_catalog
from services import video_project_queue as queue
from services import video_scene3_flow


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "idea3ux7.db")
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _scene3_state(scene_count: int) -> dict:
    plan = video_idea_catalog.build_plan(video_idea_catalog.IDEAS[0], scene_count=scene_count)
    state = video_idea_catalog.build_scene3_handoff_state(
        plan,
        product_id_override="video_ai_real",
    )
    assert state["scene_count"] == scene_count
    return state


def _scene_cards(state: dict) -> list[dict]:
    cards: list[dict] = []
    plan_scenes = {
        int(item.get("scene_index") or 0): dict(item)
        for item in (state.get("plan") or {}).get("scenes") or []
        if isinstance(item, dict)
    }
    for index in range(1, int(state["scene_count"]) + 1):
        scene = plan_scenes[index]
        video_prompt = video_scene3_flow.active_prompt(
            (state.get("video_prompt_versions") or {}).get(str(index))
        )
        image_prompt = video_scene3_flow.active_prompt(
            (state.get("image_prompt_versions") or {}).get(str(index))
        )
        cards.append(
            {
                "scene_index": index,
                "role": str(scene.get("role") or f"Cảnh {index}"),
                "narration_line": str(scene.get("dialogue_or_voiceover") or ""),
                "image_prompt": str(image_prompt.get("prompt") or ""),
                "provider_prompt": str(
                    video_prompt.get("provider_prompt") or video_prompt.get("prompt") or ""
                ),
            }
        )
    return cards


def _confirmed_worker_payload(
    tmp_path: Path,
    scene_count: int,
    *,
    clear_job_result: bool = False,
) -> tuple[dict, dict]:
    state = _scene3_state(scene_count)
    cards = _scene_cards(state)
    conn = _conn(tmp_path)
    asset_pack = {
        "source": "product_video",
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "product_type": "video_ai_prompt",
        "video_product_type": "video_ai_prompt",
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
        "provider_order": "shopaikey_video,key4u_video",
        "orchestration_mode": "per_scene_8s",
        "provider_orchestration_mode": "per_scene_8s",
    }
    invoice = {
        **asset_pack,
        "scene_count": scene_count,
        "scene_duration_seconds": 8,
        "duration_seconds": scene_count * 8,
        "total_xu": 300,
        "user_visible_price_xu": 300,
        "persisted_quoted_price_xu": 300,
        "customer_charge_planned_xu": 300,
    }
    project = queue.create_video_project(
        conn,
        user_id=9307,
        profile_id="video_ai_real",
        topic=str(state.get("subject") or "Video nhiều cảnh"),
        ratio="9:16",
        asset_pack=asset_pack,
    )
    queue.save_video_project_storyboard(
        conn,
        int(project["project_id"]),
        {"scene_cards": cards},
    )
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="draft_invoice",
        invoice_json=invoice,
        scene_count=scene_count,
        prompt_text=str(state.get("subject") or "Video nhiều cảnh"),
        total_xu_estimated=300,
    )
    result = queue.confirm_video_project_invoice(
        conn,
        project_id=int(project["project_id"]),
        user_id=9307,
    )
    assert result["ok"] is True
    job = dict(result["job"])
    original_result = json.loads(str(job.get("result_json") or "{}"))
    if clear_job_result:
        conn.execute(
            "UPDATE video_jobs SET result_json='' WHERE id=?",
            (int(job["id"]),),
        )
        conn.commit()
        job = queue.get_video_render_job(conn, int(job["id"]))
    worker_payload = remote_worker_api.build_worker_job_payload(
        queue.hydrate_video_job_payload(conn, job)
    )
    conn.close()
    return original_result, worker_payload


@pytest.mark.parametrize("scene_count", [2, 5, 20])
def test_reference_idea_final_confirm_keeps_exact_scene_prompts_and_8s_tasks(
    tmp_path: Path,
    scene_count: int,
) -> None:
    result, worker = _confirmed_worker_payload(tmp_path, scene_count)

    assert result["orchestration_mode"] == "per_scene_8s"
    assert result["scene_count"] == scene_count
    assert result["scene_tasks_created_count"] == scene_count
    assert len(result["scene_tasks"]) == scene_count
    assert len(worker["scene_cards"]) == scene_count
    assert len(worker["scene_tasks"]) == scene_count
    assert worker["expected_duration_seconds"] == scene_count * 8
    assert all(item["scene_duration_seconds"] == 8 for item in worker["scene_tasks"])
    assert [item["scene_index"] for item in worker["scene_tasks"]] == list(
        range(1, scene_count + 1)
    )
    assert all(item["scene_prompt_source"] == "video_project_scene" for item in worker["scene_tasks"])
    assert all(str(item["provider_prompt"]).strip() for item in worker["scene_tasks"])
    assert [item["provider_prompt"] for item in worker["scene_tasks"]] == [
        item.get("provider_prompt") or item.get("video_prompt") or ""
        for item in worker["scene_cards"]
    ]
    assert len({item["provider_prompt"] for item in worker["scene_tasks"]}) == scene_count
    assert result["charge"] == 0
    assert result["provider_submit_called"] is False


@pytest.mark.parametrize("scene_count", [2, 5, 20])
def test_worker_recovers_every_scene_prompt_when_job_result_json_is_missing(
    tmp_path: Path,
    scene_count: int,
) -> None:
    _, worker = _confirmed_worker_payload(
        tmp_path,
        scene_count,
        clear_job_result=True,
    )

    expected_prompts = [
        item.get("provider_prompt") or item.get("video_prompt") or ""
        for item in worker["scene_cards"]
    ]
    assert len(worker["scene_tasks"]) == scene_count
    assert [item["provider_prompt"] for item in worker["scene_tasks"]] == expected_prompts
    assert all(item["scene_prompt_source"] == "video_project_scene" for item in worker["scene_tasks"])
    assert all(item["provider_task_id"] == "" for item in worker["scene_tasks"])


def test_scene3_public_handoff_and_confirm_handler_are_single_and_connected() -> None:
    assert '"b14_scene_count": count' in BOT_SOURCE
    assert '"b14_scene_count_selected": True' in BOT_SOURCE
    assert '"b14_storyboard_plan": storyboard' in BOT_SOURCE
    assert '"video_prompt_versions": dict(state.get("video_prompt_versions") or {})' in BOT_SOURCE
    assert 'if action == "b14_confirm":' in BOT_SOURCE
    assert 'explicit_public_final_confirm=True' in BOT_SOURCE
    assert '"submit_source": "public_user_final_confirm"' in BOT_SOURCE


def test_no_real_provider_call_in_multiscene_route_test() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "submit_video" + "_job(",
        "run_provider" + "_generation(",
    )
    assert all(token not in source for token in forbidden)
