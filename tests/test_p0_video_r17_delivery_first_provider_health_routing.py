import json
from pathlib import Path

from services import video_project_queue
from services import video_real_render_connector as connector


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _row(payload: dict) -> dict:
    return {
        "result_json": json.dumps(payload, ensure_ascii=False),
        "status": payload.get("status") or "processing",
        "updated_at": "2026-07-09 10:00:00",
        "created_at": "2026-07-09 09:55:00",
        "completed_at": payload.get("completed_at") or "",
    }


def _not_start_payload(provider: str = "shopaikey_video", scenes: int = 2) -> dict:
    return {
        "source": "product_video",
        "selected_provider": provider,
        "provider_scene_tasks": [
            {
                "scene_index": index,
                "provider": provider,
                "provider_task_id": f"{provider}-task-{index}",
                "status": "NOT_START",
                "provider_status_raw": "NOT_START",
                "provider_progress_raw": 0,
                "result_url_valid": False,
                "download_url_present": False,
            }
            for index in range(1, scenes + 1)
        ],
    }


def _success_payload(provider: str = "key4u_video") -> dict:
    return {
        "source": "product_video",
        "selected_provider": provider,
        "final_mp4_valid": True,
        "final_delivered": True,
        "delivery_state": "delivered",
        "provider_scene_tasks": [
            {
                "scene_index": 1,
                "provider": provider,
                "status": "clip_downloaded",
                "download_url_present": True,
                "result_url_valid": True,
            }
        ],
    }


def _job() -> dict:
    return {"id": 77, "job_id": 77}


def _project(scene_count: int = 1) -> dict:
    invoice = {"source": "product_video", "render_mode": "real", "provider_call": True, "scene_count": scene_count}
    asset_pack = {"source": "product_video", "render_mode": "real", "provider_call": True}
    return {
        "project_id": 700,
        "scene_count": scene_count,
        "invoice_json": json.dumps(invoice, ensure_ascii=False),
        "asset_pack_json": json.dumps(asset_pack, ensure_ascii=False),
    }


def test_shopaikey_repeated_not_start_is_degraded_and_key4u_becomes_primary(monkeypatch):
    monkeypatch.delenv("PRODUCT_VIDEO_PROVIDER_NOT_START_DEGRADE_COUNT", raising=False)
    health = video_project_queue.product_video_provider_health_from_rows(
        [_row(_not_start_payload("shopaikey_video", scenes=2))],
        provider_chain=["shopaikey_video", "key4u_video"],
    )

    assert health["providers"]["shopaikey_video"]["degraded"] is True
    assert "recent_not_start_without_result" in health["providers"]["shopaikey_video"]["degraded_reason"]
    assert health["selected_primary_provider"] == "key4u_video"
    assert health["healthy_provider_order"][0] == "key4u_video"
    assert health["delivery_first_routing"] is True


def test_delivery_first_kickoff_uses_healthy_provider_order_for_one_scene():
    health = video_project_queue.product_video_provider_health_from_rows(
        [_row(_not_start_payload("shopaikey_video", scenes=2))],
        provider_chain=["shopaikey_video", "key4u_video"],
    )
    payload = video_project_queue.build_product_video_confirm_kickoff_payload(
        _job(),
        _project(scene_count=1),
        provider_chain=["shopaikey_video", "key4u_video"],
        provider_health=health,
    )

    assert payload["provider_chain_resolved"] is True
    assert payload["provider_order"][0] == "key4u_video"
    assert payload["selected_primary_provider"] == "key4u_video"
    assert payload["provider_submit_called"] is False
    assert payload["provider_primary_selected_by_health"] is True


def test_all_degraded_blocks_before_submit_no_charge():
    health = video_project_queue.product_video_provider_health_from_rows(
        [
            _row(_not_start_payload("shopaikey_video", scenes=2)),
            _row(_not_start_payload("key4u_video", scenes=2)),
        ],
        provider_chain=["shopaikey_video", "key4u_video"],
    )
    payload = video_project_queue.build_product_video_confirm_kickoff_payload(
        _job(),
        _project(scene_count=1),
        provider_chain=["shopaikey_video", "key4u_video"],
        provider_health=health,
    )

    assert payload["provider_chain_resolved"] is False
    assert payload["worker_dispatch_success"] is False
    assert payload["worker_dispatch_blocker"] == "all_video_providers_degraded_or_missing"
    assert payload["provider_health_blocked_before_submit"] is True
    assert payload["provider_submit_called"] is False
    assert payload["charge"] == 0
    assert payload["charged_xu"] == 0


def test_multiscene_not_live_ready_blocks_two_scene_sale_before_provider_submit():
    health = video_project_queue.product_video_provider_health_from_rows(
        [],
        provider_chain=["shopaikey_video", "key4u_video"],
    )
    payload = video_project_queue.build_product_video_confirm_kickoff_payload(
        _job(),
        _project(scene_count=2),
        provider_chain=["shopaikey_video", "key4u_video"],
        provider_health=health,
    )

    assert health["multiscene_live_ready"] is False
    assert payload["provider_chain_resolved"] is False
    assert payload["safe_live_scene_count"] == 1
    assert payload["worker_dispatch_blocker"] == "multiscene_live_not_ready_no_charge"
    assert payload["provider_submit_called"] is False


def test_multiscene_live_success_allows_two_scene_kickoff():
    health = video_project_queue.product_video_provider_health_from_rows(
        [_row(_success_payload("key4u_video"))],
        provider_chain=["shopaikey_video", "key4u_video"],
    )
    payload = video_project_queue.build_product_video_confirm_kickoff_payload(
        _job(),
        _project(scene_count=2),
        provider_chain=["shopaikey_video", "key4u_video"],
        provider_health=health,
    )

    assert health["multiscene_live_ready"] is True
    assert payload["provider_chain_resolved"] is True
    assert payload["scene_count"] == 2
    assert payload["worker_dispatch_blocker"] == ""


def test_not_start_over_90_seconds_falls_back_once_to_healthy_provider():
    task = {
        "scene_index": 1,
        "provider": "shopaikey_video",
        "provider_task_id": "task-1",
        "status": "NOT_START",
        "provider_status_raw": "NOT_START",
        "provider_wait_elapsed_seconds": 91,
        "fallback_count": 0,
    }
    job = {
        "source": "product_video",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_order": ["shopaikey_video", "key4u_video"],
    }

    policy = connector.product_video_scene_stall_policy(job, task, 1)

    assert policy["provider_stalled_not_start"] is True
    assert policy["fallback_allowed"] is True
    assert policy["fallback_provider_order"][0] == "key4u_video"


def test_r17_debug_status_tokens_are_registered():
    for token in (
        "provider health",
        "selected primary provider",
        "delivery-first routing",
        "multiscene live ready",
        "safe live scene count",
        "provider health gate reason",
        "scene provider status by scene",
        "fallback submit source by scene",
        "final action",
    ):
        assert token in BOT_SOURCE


def test_codex_tests_use_fixtures_only_without_paid_provider_calls():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "submit_url" + "_thật",
        "provider" + "_smoke",
    )
    assert all(token not in source for token in forbidden)
