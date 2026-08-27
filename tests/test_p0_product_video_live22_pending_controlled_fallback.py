import asyncio
import time
from types import SimpleNamespace

import pytest

import remote_worker
from services import video_real_render_connector as connector


def _confirmed_exact_quote_job(**overrides):
    job = {
        "id": 22,
        "job_id": 22,
        "source": "product_video",
        "product_video": True,
        "admin_only": True,
        "no_charge": True,
        "original_submit_source": "public_user_final_confirm",
        "submit_source": "worker_poll_existing_task",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "provider_order": ["shopaikey_video", "key4u_video"],
        "product_video_durable_public_seam": True,
        "automatic_fallback_allowed": False,
        "user_visible_price_xu": 144,
        "persisted_quoted_price_xu": 144,
        "customer_charge_planned_xu": 144,
        "provider_budget_xu": 144,
        "quote_consistent": True,
        "charged_xu": 0,
    }
    job.update(overrides)
    return job


def _stalled_primary_scene():
    return {
        "scene_index": 1,
        "provider": "shopaikey_video",
        "provider_task_id": "shop-task-live22",
        "provider_video_id": "shop-task-live22",
        "provider_status": "NOT_START",
        "provider_status_raw": "NOT_START",
        "provider_elapsed_seconds": 90,
        "provider_wait_elapsed_seconds": 90,
        "provider_progress_raw": 0,
        "fallback_count": 0,
        "result_url_valid": False,
    }


def test_live22_worker_preserves_provider_not_start_pending_reason(monkeypatch, tmp_path):
    pending = {
        "ok": False,
        "continue_polling": True,
        "terminal_state": "final_rendering",
        "provider_error": "provider_not_start",
        "blocker": "provider_not_start",
        "provider_task_ids": ["shop-task-live22"],
        "no_charge": True,
    }
    monkeypatch.setattr(connector, "render_real_video_job", lambda _job, _work_dir: dict(pending))

    with pytest.raises(RuntimeError, match="^provider_not_start$"):
        remote_worker.render_real_video(_confirmed_exact_quote_job(), str(tmp_path))

    assert remote_worker.LAST_REAL_VIDEO_RENDER_RESULT["continue_polling"] is True
    assert remote_worker.LAST_REAL_VIDEO_RENDER_RESULT["provider_error"] == "provider_not_start"


def test_live22_exact_quote_authorizes_one_controlled_scene_fallback(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "60")

    policy = connector.product_video_scene_stall_policy(
        _confirmed_exact_quote_job(),
        _stalled_primary_scene(),
        1,
    )

    assert policy["automatic_fallback_forbidden"] is True
    assert policy["controlled_fallback_allowed"] is True
    assert policy["fallback_allowed"] is True
    assert policy["fallback_provider_order"] == ["key4u_video"]
    assert policy["fallback_count"] == 0
    assert policy["fallback_idempotency_key"]
    assert policy["fallback_authorization_source"] == "persisted_exact_quote_final_confirm"


def test_live22_controlled_fallback_stays_blocked_without_exact_quote(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "60")

    policy = connector.product_video_scene_stall_policy(
        _confirmed_exact_quote_job(customer_charge_planned_xu=145, quote_consistent=False),
        _stalled_primary_scene(),
        1,
    )

    assert policy["controlled_fallback_allowed"] is False
    assert policy["fallback_allowed"] is False
    assert policy["fallback_block_reason"] == "automatic_fallback_forbidden"


def test_live22_controlled_fallback_stays_blocked_without_final_confirm(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "60")

    policy = connector.product_video_scene_stall_policy(
        _confirmed_exact_quote_job(
            original_submit_source="",
            public_user_confirmed=False,
            invoice_confirmed=False,
        ),
        _stalled_primary_scene(),
        1,
    )

    assert policy["controlled_fallback_allowed"] is False
    assert policy["fallback_allowed"] is False
    assert policy["fallback_block_reason"] == "automatic_fallback_forbidden"


def test_live22_started_at_text_drives_not_start_elapsed(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "60")
    now_epoch = time.mktime(time.strptime("2026-08-27 16:34:28", "%Y-%m-%d %H:%M:%S"))
    monkeypatch.setattr(connector.time, "time", lambda: now_epoch)
    scene = {
        **_stalled_primary_scene(),
        "provider_elapsed_seconds": 0,
        "provider_wait_elapsed_seconds": 0,
        "started_at": "2026-08-27 16:32:58",
    }

    policy = connector.product_video_scene_stall_policy(
        _confirmed_exact_quote_job(),
        scene,
        1,
    )

    assert policy["scene_not_start_elapsed"] == 90
    assert policy["provider_stalled_not_start"] is True
    assert policy["fallback_allowed"] is True


def test_live22_controlled_scene_fallback_uses_key4u_once(monkeypatch, tmp_path):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "60")
    stalled_scene = {
        **_stalled_primary_scene(),
        "request_job_id": "22-1",
    }
    job = _confirmed_exact_quote_job(
        scene_count=2,
        scenes=[{"scene_index": 1}, {"scene_index": 2}],
        scene_tasks=[stalled_scene],
    )
    captured = {}

    def fake_provider_generation(request, *, output_dir, environ, **_kwargs):
        captured["provider_chain"] = environ.get("VIDEO_PROVIDER_CHAIN")
        captured["submit_source"] = request.metadata.get("submit_source")
        output = tmp_path / "key4u-scene-1.mp4"
        output.write_bytes(b"key4u-live22-scene")
        return {
            "ok": True,
            "output_path": str(output),
            "provider": "key4u_video",
            "provider_task_ids": ["key4u-task-live22"],
            "provider_video_ids": ["key4u-task-live22"],
        }

    monkeypatch.setattr(connector, "run_provider_generation", fake_provider_generation)
    scene = SimpleNamespace(
        scene_id=1,
        video_prompt="approved Product Video prompt",
        visual_prompt="approved Product Video prompt",
        aspect_ratio="9:16",
        target_duration_sec=8,
        _toan_aas_job=job,
    )

    result = asyncio.run(
        connector._render_scene_async(
            scene,
            str(tmp_path / "rendered-scene-1.mp4"),
            ["shopaikey_video", "key4u_video"],
        )
    )

    assert result["ok"] is True
    assert captured["provider_chain"].split(",")[0] == "key4u_video"
    assert captured["submit_source"] == "public_confirmed_scene_fallback_once"
    assert result["fallback_count"] == 1
    assert result["fallback_idempotency_key"]


def test_live23_collapsed_primary_chain_recovers_ready_key4u_candidate(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_NOT_START_STALL_SECONDS", "60")
    monkeypatch.setattr(
        connector,
        "real_video_provider_readiness",
        lambda *_args, **_kwargs: {
            "ok": True,
            "ready_provider_order": ["shopaikey_video", "key4u_video"],
            "providers": [],
        },
    )

    policy = connector.product_video_scene_stall_policy(
        _confirmed_exact_quote_job(
            provider_order=["shopaikey_video"],
            configured_provider_chain=["shopaikey_video", "key4u_video"],
            required_capability="text_to_video_or_scene_video",
            product_video_durable_public_seam=None,
            product_video_route_decision=None,
        ),
        _stalled_primary_scene(),
        1,
    )

    assert policy["runtime_fallback_candidate_recovered"] is True
    assert policy["automatic_fallback_forbidden"] is True
    assert policy["fallback_provider_order"] == ["key4u_video"]
    assert policy["controlled_fallback_allowed"] is True
    assert policy["fallback_allowed"] is True
    assert policy["fallback_authorization_source"] == "persisted_exact_quote_final_confirm"
