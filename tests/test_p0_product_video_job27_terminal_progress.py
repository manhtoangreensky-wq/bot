from __future__ import annotations

import hashlib
import inspect

import bot
import remote_worker
from services import video_final_output, video_real_render_connector


LOCKED_ENGINE_ROUTE_HASHES = {
    "video_engine_product_type_for_session": (
        bot.video_engine_product_type_for_session,
        "fe15dcc7242d5c9cd2c0499b758897210d1878deaf0d5bc16307464c55b8a9fb",
    ),
    "video_uiflow3_prepare_project_for_invoice": (
        bot.video_uiflow3_prepare_project_for_invoice,
        "854d5d4eef17877c1c4ba81b9654e968c4129386d418bfd599e7f139da35052f",
    ),
    "video_b14_prepare_project_for_invoice": (
        bot.video_b14_prepare_project_for_invoice,
        "3d57b674b7779bdd6a67ba9d8071eb660081996adb067c584ded2de7892565dc",
    ),
    "video_final_output.route_for_product_type": (
        video_final_output.route_for_product_type,
        "f74b940d62b2491e9c06ec3b07d23453e437e3c51898d8c15dbb5fb409134efd",
    ),
    "video_real_render_connector._run_per_scene_provider_orchestrator": (
        video_real_render_connector._run_per_scene_provider_orchestrator,
        "2d40e64b9910c0cae95e79b33bde77f73c0a23a24f1b8ee5a56099d09302df40",
    ),
}


def test_job27_all_scene_provider_exhaustion_overrides_stale_polling(
    monkeypatch,
) -> None:
    captured: dict = {}
    job = {
        "job_id": "27",
        "job_type": "video_render",
        "product_video": True,
        "provider_call": True,
    }

    monkeypatch.setattr(
        remote_worker,
        "claim_job",
        lambda **_kwargs: dict(job),
    )
    monkeypatch.setattr(
        remote_worker,
        "product_video_job_allowed",
        lambda _job: True,
    )

    def exhaust_provider(_job):
        remote_worker.LAST_REAL_VIDEO_RENDER_RESULT = {
            "continue_polling": True,
            "terminal_state": "final_rendering",
            "final_decision": "continue_polling",
            "provider_error": "provider_in_progress",
            "blocker": "provider_in_progress",
            "provider_task_ids": ["existing-task-1", "existing-task-2"],
            "provider_submit_called": False,
            "task_created_count": 0,
            "wallet_charge": 0,
        }
        raise RuntimeError("all_scene_providers_exhausted_no_charge")

    def capture_failure(job_id, safe_error, retryable=True, partial_artifacts=None):
        captured.update(
            {
                "job_id": job_id,
                "safe_error": safe_error,
                "retryable": retryable,
                "partial_artifacts": partial_artifacts,
                "diagnostics": dict(remote_worker.LAST_REAL_VIDEO_RENDER_RESULT),
            }
        )
        return {"ok": True, "status": "failed"}

    monkeypatch.setattr(remote_worker, "process_claimed_job", exhaust_provider)
    monkeypatch.setattr(remote_worker, "fail_job", capture_failure)

    result = remote_worker.run_once(owner_product_video_only=True)

    assert result == "failed"
    assert captured["job_id"] == "27"
    assert captured["retryable"] is False
    assert "all_scene_providers_exhausted_no_charge" in captured["safe_error"]
    assert captured["diagnostics"]["continue_polling"] is False
    assert captured["diagnostics"]["terminal_state"] == "failed_no_charge"
    assert captured["diagnostics"]["final_decision"] == "failed_no_charge"
    assert captured["diagnostics"]["provider_error"] == (
        "all_scene_providers_exhausted_no_charge"
    )
    assert captured["diagnostics"]["blocker"] == (
        "all_scene_providers_exhausted_no_charge"
    )
    assert captured["diagnostics"]["no_charge"] is True
    assert captured["diagnostics"]["wallet_charge"] == 0
    assert captured["diagnostics"]["provider_submit_called"] is False
    assert captured["diagnostics"]["task_created_count"] == 0


def test_product_video_status_adds_subdub_style_percent_tree_without_route_change(
    monkeypatch,
) -> None:
    job = {
        "id": 27,
        "user_id": 7126457028,
        "project_id": 31,
        "status": "processing",
        "progress_percent": 55,
        "result_json": "{}",
    }
    session = {
        "product_id": "video_ai_real",
        "draft": {
            "b14_queue_job": dict(job),
            "b14_queue_job_id": 27,
            "b14_project_id": 31,
            "b14_invoice": {
                "scene_count": 2,
                "duration_seconds": 16,
                "routing_quality_tier": 400,
                "package_label": "Nhanh gọn · 8 giây/cảnh · 80 Xu/cảnh",
            },
            "b14_addon_plan": {},
        },
    }
    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: dict(job))
    monkeypatch.setattr(bot, "get_video_project", lambda _project_id: {})

    text = bot.video_b14_queue_status_text(
        session,
        {"job": dict(job), "project": {}},
        user_id=7126457028,
        lang="vi",
    )

    assert "Tiến độ: <b>55%</b>" in text
    assert "0% 🟩🟩🟩🟩🟩🟨⬜⬜⬜⬜ 100%" in text
    assert text.index("Tiến độ: <b>55%</b>") < text.index(
        "0% 🟩🟩🟩🟩🟩🟨⬜⬜⬜⬜ 100%"
    )


def test_product_video_progress_tree_keeps_engine_routes_byte_locked() -> None:
    for name, (function, expected_hash) in LOCKED_ENGINE_ROUTE_HASHES.items():
        source = inspect.getsource(function).rstrip()
        actual_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        assert actual_hash == expected_hash, name
