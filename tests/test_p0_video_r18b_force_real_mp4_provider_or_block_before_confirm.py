import asyncio
import json
from pathlib import Path

from services import video_project_queue, video_provider_router
from services import video_real_render_connector as connector


BOT_SOURCE = Path("bot.py").read_text(encoding="utf-8")


def _status_payload(*, key4u_configured=True):
    return {
        "provider_chain": ["shopaikey_video", "key4u_video"],
        "effective_provider_chain": ["shopaikey_video", "key4u_video"],
        "providers": [
            {
                "provider": "shopaikey_video",
                "configured": True,
                "credit_ok": True,
                "credit_status": "ok",
            },
            {
                "provider": "key4u_video",
                "configured": bool(key4u_configured),
                "credit_ok": True,
                "credit_status": "ok",
            },
        ],
    }


def _stuck_attempts():
    return [
        {
            "provider": "shopaikey_video",
            "provider_status_raw": "NOT_START",
            "result_url": "",
            "artifact_size": 0,
            "delivered": False,
        },
        {
            "provider": "shopaikey_video",
            "provider_status_raw": "NOT_START",
            "result_url": "",
            "artifact_size": 0,
            "delivered": False,
        },
    ]


def test_shopaikey_not_start_no_result_url_degrades_public_provider(monkeypatch):
    monkeypatch.delenv("PRODUCT_VIDEO_SHOPAIKEY_VIDEO_PUBLIC_DEGRADED", raising=False)

    result = video_provider_router.product_video_provider_public_degradation(
        "shopaikey_video",
        _stuck_attempts(),
        environ={},
    )

    assert result["provider_degraded_for_product_video_public"] is True
    assert result["last_not_start_count"] == 2
    assert result["last_result_url_empty_count"] == 2
    assert result["last_artifact_size_zero_count"] == 2
    assert "not_start_repeated" in result["degrade_reason"]


def test_shopaikey_degraded_key4u_configured_selects_key4u_primary():
    degraded = video_provider_router.product_video_provider_public_degradation(
        "shopaikey_video",
        _stuck_attempts(),
        environ={},
    )

    decision = video_provider_router.product_video_public_provider_route_decision(
        status=_status_payload(key4u_configured=True),
        degraded_providers={"shopaikey_video": degraded},
    )

    assert decision["ok"] is True
    assert decision["selected_provider"] == "key4u_video"
    assert decision["effective_provider_chain"][0] == "key4u_video"
    assert decision["skipped_providers"][0]["reason"] == "provider_degraded_for_product_video_public"


def test_shopaikey_degraded_key4u_missing_blocks_before_invoice():
    degraded = video_provider_router.product_video_provider_public_degradation(
        "shopaikey_video",
        _stuck_attempts(),
        environ={},
    )

    decision = video_provider_router.product_video_public_provider_route_decision(
        status=_status_payload(key4u_configured=False),
        degraded_providers={"shopaikey_video": degraded},
    )

    assert decision["ok"] is False
    assert decision["selected_provider"] == ""
    assert decision["blocker"] == "product_video_no_public_mp4_provider"


def test_product_video_preflight_reads_recent_jobs_and_provider_status_source_contract():
    assert "def _product_video_recent_provider_attempt_evidence" in BOT_SOURCE
    assert "FROM video_jobs j" in BOT_SOURCE
    assert "LEFT JOIN video_projects p" in BOT_SOURCE
    assert "video_provider_router.product_video_provider_public_degradation" in BOT_SOURCE
    assert "video_provider_router.product_video_public_provider_route_decision" in BOT_SOURCE
    assert "product_video_no_public_mp4_provider" in BOT_SOURCE


def test_product_video_blocks_before_invoice_when_preflight_fails_source_contract():
    scene_count_start = BOT_SOURCE.index('if action == "b14_scene_count":')
    scene_count_end = BOT_SOURCE.index('if action == "b14_confirm":', scene_count_start)
    scene_count_source = BOT_SOURCE[scene_count_start:scene_count_end]

    assert "product_video_provider_availability_preflight()" in scene_count_source
    assert scene_count_source.index("product_video_provider_availability_preflight()") < scene_count_source.index("video_b14_prepare_project_for_invoice")
    assert "PRODUCT_VIDEO_PROVIDER_BUSY_COPY_VI" in scene_count_source


def test_product_video_confirm_blocks_before_submit_when_preflight_fails_source_contract():
    confirm_start = BOT_SOURCE.index('if action == "b14_confirm":')
    confirm_end = BOT_SOURCE.index('if action == "b14_job_status":', confirm_start)
    confirm_source = BOT_SOURCE[confirm_start:confirm_end]

    assert "product_video_provider_availability_preflight()" in confirm_source
    assert confirm_source.index("product_video_provider_availability_preflight()") < confirm_source.index("confirm_video_project_invoice")
    assert "job_creation_blocked_by_provider_availability" not in confirm_source
    assert "PRODUCT_VIDEO_PROVIDER_BUSY_COPY_VI" in confirm_source


def test_confirm_kickoff_uses_preflight_provider_chain_from_project():
    job = {"id": 55}
    project = {
        "scene_count": 2,
        "asset_pack_json": json.dumps(
            {
                "source": "product_video",
                "provider_chain": ["key4u_video"],
                "provider_order": "key4u_video",
            }
        ),
        "invoice_json": json.dumps({"provider_chain": ["key4u_video"]}),
    }

    payload = video_project_queue.build_product_video_confirm_kickoff_payload(job, project)

    assert payload["configured_provider_chain"] == ["key4u_video"]
    assert payload["effective_provider_chain"] == ["key4u_video"]
    assert payload["provider_chain_resolved"] is True


def test_connector_sets_video_provider_chain_from_job_order(monkeypatch, tmp_path):
    captured = {}

    def fake_run_provider_generation(request, *, output_dir, environ):
        output_path = Path(output_dir) / "provider.mp4"
        output_path.write_bytes(b"fake-mp4-fixture")
        captured["chain"] = environ.get("VIDEO_PROVIDER_CHAIN")
        return {
            "ok": True,
            "provider": "key4u_video",
            "provider_status": "provider_in_progress",
            "continue_polling": True,
            "provider_task_id": "task-fixture",
            "output_path": str(output_path),
        }

    monkeypatch.setattr(connector, "run_provider_generation", fake_run_provider_generation)

    class Scene:
        scene_id = 1
        video_prompt = "demo product video"
        visual_prompt = "demo product video"
        aspect_ratio = "9:16"
        target_duration_sec = 8
        _toan_aas_job = {
            "source": "product_video",
            "product_video": True,
            "product_type": "video_trend",
            "render_mode": "real",
            "provider_order": ["key4u_video"],
            "public_user_confirmed": True,
            "invoice_confirmed": True,
            "submit_source": "public_user_final_confirm",
        }

    result = asyncio.run(connector._render_scene_async(Scene(), str(tmp_path / "raw.mp4"), ["key4u_video"]))

    assert captured["chain"] == "key4u_video"
    assert result["provider"] == "key4u_video"


def test_video_provider_canary_registered_as_admin_smoke_alias():
    smoke_start = BOT_SOURCE.index("async def cmd_video_provider_smoke")
    smoke_end = BOT_SOURCE.index("async def prepare_remove_bg_from_cached_image", smoke_start)
    handler_source = BOT_SOURCE[smoke_start:smoke_end]

    assert 'CommandHandler("video_provider_canary", cmd_video_provider_smoke)' in BOT_SOURCE
    assert "is_admin_user" in handler_source
    assert "run_provider_generation" in handler_source


def test_debug_status_recover_do_not_submit_new_provider_tasks():
    for name in ("cmd_video_provider_job_debug", "cmd_video_render_debug", "cmd_progress_status_debug"):
        marker = f"async def {name}"
        assert marker in BOT_SOURCE
        start = BOT_SOURCE.index(marker)
        next_def = BOT_SOURCE.find("\nasync def ", start + 1)
        next_sync_def = BOT_SOURCE.find("\ndef ", start + 1)
        candidates = [idx for idx in (next_def, next_sync_def) if idx != -1]
        end = min(candidates) if candidates else len(BOT_SOURCE)
        source = BOT_SOURCE[start:end]
        assert "run_provider_generation(" not in source
        assert "submit_video_job(" not in source
