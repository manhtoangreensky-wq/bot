from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import remote_worker_api
from services import video_project_queue as queue
from services import video_provider_router as router
from services import video_real_render_connector as connector


ROOT = Path(__file__).resolve().parents[1]


class _FixtureAdapter:
    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    def capabilities(self) -> dict:
        return {
            "provider": self.provider_name,
            "configured": True,
            "capabilities": ["text_to_video", "scene_video", "multi_scene_video"],
        }


@pytest.fixture(autouse=True)
def _fixture_provider_adapters(monkeypatch):
    monkeypatch.setattr(
        router,
        "load_video_provider_adapters",
        lambda _env=None: [_FixtureAdapter("shopaikey_video"), _FixtureAdapter("key4u_video")],
    )


def _status(*, missing_auth: str = "") -> dict:
    providers = []
    for provider in ("shopaikey_video", "key4u_video"):
        providers.append(
            {
                "provider": provider,
                "enabled": True,
                "configured": True,
                "credit_ok": True,
                "submit_url_configured": True,
                "poll_url_configured": True,
                "auth_configured": provider != missing_auth,
                "model_present": True,
            }
        )
    return {
        "provider_chain": ["shopaikey_video", "key4u_video"],
        "effective_provider_chain": ["shopaikey_video", "key4u_video"],
        "providers": providers,
    }


def _health() -> dict:
    return {
        "shopaikey_video": {
            "provider": "shopaikey_video",
            "route_ready": True,
            "live_healthy": False,
            "multi_scene_eligible": False,
            "provider_health_state": "degraded",
            "health_status": "degraded",
            "provider_degraded_for_product_video_public": True,
            "degraded_reason": (
                "in_progress_stall_repeated,result_url_empty_repeated,"
                "artifact_size_zero_repeated,terminal_failure_repeated"
            ),
            "degraded_until_epoch": 2_000_000_000,
        },
        "key4u_video": {
            "provider": "key4u_video",
            "route_ready": True,
            "live_healthy": False,
            "multi_scene_eligible": False,
            "provider_health_state": "unknown",
            "health_status": "unknown",
            "provider_degraded_for_product_video_public": False,
        },
    }


def _patch_router(monkeypatch, *, missing_auth: str = "") -> None:
    monkeypatch.setattr(router, "provider_status_payload", lambda _env=None: _status(missing_auth=missing_auth))
    monkeypatch.setattr(
        router,
        "load_video_provider_adapters",
        lambda _env=None: [_FixtureAdapter("shopaikey_video"), _FixtureAdapter("key4u_video")],
    )
    monkeypatch.setattr(
        router,
        "product_video_submit_switch_detail",
        lambda _env=None: {"resolved": True, "raw": "1", "source": "fixture"},
    )


def _eligibility(
    *,
    source: str = "public_user_final_confirm",
    confirmed: bool = True,
    lock_clear: bool = True,
    missing_auth: str = "",
    hard_blocks: dict | None = None,
) -> dict:
    return router.product_video_provider_eligibility_snapshot(
        status=_status(missing_auth=missing_auth),
        chain=["shopaikey_video", "key4u_video"],
        provider_health=_health(),
        contract_valid_provider_chain=["shopaikey_video", "key4u_video"],
        scene_count=2,
        require_live_health=True,
        allow_public_confirmed_probation=True,
        allow_operational_degradation_probation=True,
        admission_source=source,
        public_user_confirmed=confirmed,
        public_submit_enabled=True,
        worker_compatible=True,
        probation_lock_clear=lock_clear,
        hard_block_reason_by_provider=hard_blocks or {},
    )


def _job134_result(*, source: str = "public_user_final_confirm", confirmed: bool = True) -> dict:
    return {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "product_type": "video_ai_prompt",
        "engine_adapter": "text_to_video",
        "orchestration_mode": "per_scene_8s",
        "scene_count": 2,
        "scenes_total": 2,
        "admission_enforced": True,
        "admission_snapshot_id": "job-134-admission",
        "provider_eligibility_snapshot_id": "job-134-admission",
        "provider_eligibility_snapshot": {
            "provider_eligibility_snapshot_id": "job-134-admission",
            "configured_provider_keys": ["shopaikey_video", "key4u_video"],
            "contract_valid_provider_chain": ["shopaikey_video", "key4u_video"],
            "scene_count": 2,
        },
        "configured_provider_chain": ["shopaikey_video", "key4u_video"],
        "contract_valid_provider_chain": ["shopaikey_video", "key4u_video"],
        "runtime_candidate_keys": [],
        "preconfirm_candidate_keys": [],
        "provider_health_at_submit": _health(),
        "provider_hard_block_reason_by_provider": {},
        "global_hard_block_reason": "",
        "submit_source": source,
        "provider_submit_source": source,
        "original_submit_source": "public_user_final_confirm",
        "public_user_confirmed": confirmed,
        "worker_compatible": True,
        "worker_connected": True,
        "probation_lock_clear": False,
        "probation_job_id": 134,
        "admission_mode": queue.PRODUCT_VIDEO_PROBATION_ADMISSION_MODE,
        "probation_candidate_key": "shopaikey_video",
        "charge_policy": "after_valid_mp4_delivery",
        "charge": 0,
        "charged_xu": 0,
    }


def test_r18s12_degraded_route_ready_provider_is_probation_not_hard_block():
    result = _eligibility()

    assert result["hard_blocked_candidate_keys"] == []
    assert result["probation_candidate_keys"] == ["shopaikey_video", "key4u_video"]
    assert result["eligible_provider_keys"] == ["shopaikey_video"]
    assert result["probation_candidate_selected"] == "shopaikey_video"
    assert result["healthy_candidate_keys"] == []


def test_r18s12_unknown_route_ready_provider_is_probation_not_hard_block():
    result = _eligibility(hard_blocks={"shopaikey_video": "provider_cost_lock_active"})

    assert result["eligible_provider_keys"] == ["key4u_video"]
    assert result["probation_candidate_selected"] == "key4u_video"
    assert "key4u_video" not in result["hard_blocked_candidate_keys"]


def test_r18s12_missing_credentials_still_hard_blocks():
    result = _eligibility(missing_auth="shopaikey_video")

    assert "shopaikey_video" in result["hard_blocked_candidate_keys"]
    assert "provider_credentials_missing" in result["hard_block_reason_by_provider"]["shopaikey_video"]
    assert result["eligible_provider_keys"] == ["key4u_video"]


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"public_provider_freeze": True}, "public_provider_freeze_active"),
        ({"public_maintenance": True}, "product_video_public_maintenance"),
        ({"payment_freeze": True}, "payment_freeze_active"),
        ({"tool_freeze": True}, "tool_freeze_active"),
        ({"security_block": True}, "security_block_active"),
        ({"provider_frozen": True, "provider_freeze_reason": "CREDIT_LOW_OR_EMPTY"}, "provider_cost_lock_active"),
    ],
)
def test_r18s12_public_payment_tool_security_cost_blocks_still_hard_block(kwargs, reason):
    policy = router.product_video_provider_freeze_probation_policy(
        provider="shopaikey_video",
        explicit_public_final_confirm=True,
        **kwargs,
    )

    assert policy["hard_block_reason"] == reason
    assert policy["probation_eligible"] is False


def test_r18s12_operational_hidden_freeze_is_controlled_probation_only():
    confirmed = router.product_video_provider_freeze_probation_policy(
        provider="shopaikey_video",
        provider_frozen=True,
        provider_freeze_reason="VIDEO_ERROR_THRESHOLD_SHORT",
        explicit_public_final_confirm=True,
    )
    hidden = router.product_video_provider_freeze_probation_policy(
        provider="shopaikey_video",
        provider_frozen=True,
        provider_freeze_reason="VIDEO_ERROR_THRESHOLD_SHORT",
        explicit_public_final_confirm=False,
    )

    assert confirmed["hard_block_reason"] == ""
    assert confirmed["probation_eligible"] is True
    assert confirmed["hidden_submit_freeze"] is True
    assert hidden["hard_block_reason"] == ""
    assert hidden["probation_eligible"] is False


def test_r18s12_selects_exactly_one_probation_candidate_in_chain_order():
    result = _eligibility()

    assert result["candidates_before_filter"] == ["shopaikey_video", "key4u_video"]
    assert result["candidates_after_route_filter"] == ["shopaikey_video", "key4u_video"]
    assert result["candidate_count"] == 1
    assert result["eligible_provider_keys"] == ["shopaikey_video"]


def test_r18s12_active_probation_lock_for_another_job_blocks_with_reason():
    result = _eligibility(lock_clear=False)

    assert result["eligible_provider_keys"] == []
    assert result["probation_reject_reason"] == "probation_lock_not_clear"
    assert result["blocker"] == "probation_lock_not_clear"


@pytest.mark.parametrize("source", ["debug", "status", "recover", "smoke", "codex_test", "background_retry"])
def test_r18s12_no_background_smoke_debug_recover_probation(source):
    result = _eligibility(source=source, confirmed=False)

    assert result["probation_candidate_keys"] == ["shopaikey_video", "key4u_video"]
    assert result["eligible_provider_keys"] == []
    assert result["probation_admission_allowed"] is False
    assert result["probation_submit_block_reason"] == "hidden_submit_source_blocked"


def test_r18s12_job134_degraded_provider_probation_regression(monkeypatch):
    _patch_router(monkeypatch)

    result = remote_worker_api._product_video_runtime_eligibility(
        {"id": 134},
        _job134_result(),
        {"project_id": 131},
        now=datetime(2026, 7, 13, 8, 15, 0),
    )

    assert result["configured_chain_at_runtime"] == ["shopaikey_video", "key4u_video"]
    assert result["contract_valid_chain_at_runtime"] == ["shopaikey_video", "key4u_video"]
    assert result["runtime_candidate_keys"] == ["shopaikey_video"]
    assert result["probation_candidate_selected"] == "shopaikey_video"
    assert result["provider_submit_allowed"] is True
    assert result["provider_submit_block_reason"] == ""
    assert result["router_skip_reason"] == ""
    assert result["probation_lock_clear_at_candidate_resolver"] is True
    assert _job134_result()["charge"] == 0


def test_r18s12_job134_hidden_source_stays_blocked_with_explicit_reason(monkeypatch):
    _patch_router(monkeypatch)

    result = remote_worker_api._product_video_runtime_eligibility(
        {"id": 134},
        _job134_result(source="status", confirmed=False),
        {"project_id": 131},
    )

    assert result["runtime_candidate_keys"] == []
    assert result["provider_submit_allowed"] is False
    assert result["provider_submit_block_reason"] == "hidden_submit_source_blocked"
    assert result["router_skip_reason"] == "hidden_submit_source_blocked"


def _claim_fixture(tmp_path: Path) -> tuple[sqlite3.Connection, dict, dict]:
    conn = sqlite3.connect(tmp_path / "r18s12.db")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    shared = {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "product_type": "video_ai_prompt",
        "engine_adapter": "text_to_video",
        "orchestration_mode": "per_scene_8s",
        "scene_count": 2,
        "duration_seconds": 16,
    }
    project = queue.create_video_project(
        conn,
        user_id=134,
        profile_id="video_ai_prompt",
        topic="job #134 fixture",
        ratio="9:16",
        asset_pack=shared,
    )
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="queued_for_worker",
        invoice_json={
            **shared,
            "package_xu": 300,
            "user_visible_price_xu": 300,
            "persisted_quoted_price_xu": 300,
            "customer_charge_planned_xu": 300,
            "wallet_charge_amount_xu": 300,
        },
        scene_count=2,
        total_xu_estimated=300,
        is_confirmed=1,
    )
    job = queue.enqueue_video_render_job(
        conn,
        project_id=int(project["project_id"]),
        user_id=134,
    )
    payload = _job134_result()
    payload["probation_job_id"] = int(job["id"])
    payload["scene_tasks"] = queue.product_video_initial_scene_tasks(int(job["id"]), 2)
    conn.execute(
        "UPDATE video_jobs SET result_json=?,status='queued',locked_by='',locked_at=NULL,lease_expires_at=NULL WHERE id=?",
        (json.dumps(payload), int(job["id"])),
    )
    queue.ensure_product_video_dispatch_outbox(
        conn,
        job_id=int(job["id"]),
        project_id=int(project["project_id"]),
        scene_indexes=[1, 2],
    )
    conn.commit()
    return conn, queue.get_video_render_job(conn, int(job["id"])), queue.get_video_project(conn, int(project["project_id"]))


def test_r18s12_job134_scenes_not_prefailed_and_claim_is_idempotent(tmp_path, monkeypatch):
    _patch_router(monkeypatch)
    conn, job, _project = _claim_fixture(tmp_path)

    claimed = remote_worker_api.claim_remote_worker_product_video_job(
        conn,
        worker_id="owner-r18s12",
        owner_only=True,
    )
    duplicate = remote_worker_api.claim_remote_worker_product_video_job(
        conn,
        worker_id="owner-r18s12-duplicate",
        owner_only=True,
    )

    assert claimed["id"] == job["id"]
    payload = json.loads(str(claimed["result_json"] or "{}"))
    assert payload["runtime_candidate_keys"] == ["shopaikey_video"]
    assert payload["provider_submit_allowed"] is True
    assert payload["router_skip_reason"] == ""
    assert payload.get("terminal_state") != "failed_no_charge"
    assert all(
        str(item.get("status") or "") != "terminal_failed"
        for item in payload.get("scene_tasks") or []
    )
    assert duplicate == {}
    assert payload.get("charge", 0) == 0
    assert payload.get("charged_xu", 0) == 0


def test_r18s12_two_scene_probation_dispatch_calls_router_fixture(monkeypatch):
    calls = []

    def fake_run_provider_generation(request, *, output_dir, environ):
        calls.append(
            {
                "job_id": request.job_id,
                "duration_seconds": request.duration_seconds,
                "metadata": dict(request.metadata),
            }
        )
        path = Path(output_dir) / "scene.mp4"
        path.write_bytes(b"fixture-mp4")
        return {
            "ok": True,
            "provider": "shopaikey_video",
            "output_path": str(path),
            "provider_task_ids": ["fixture-task"],
            "result_url_present": True,
            "output_duration": 8,
        }

    monkeypatch.setattr(connector, "run_provider_generation", fake_run_provider_generation)
    monkeypatch.setattr(connector, "ensure_video_output", lambda path: str(path))
    job = {
        "job_id": "134",
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "product_type": "video_ai_prompt",
        "engine_adapter": "text_to_video",
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "runtime_candidate_keys": ["shopaikey_video"],
        "provider_chain": ["shopaikey_video"],
        "public_user_confirmed": True,
        "submit_source": "public_user_final_confirm",
    }
    scenes = [
        SimpleNamespace(
            scene_id=index,
            video_prompt=f"Cảnh {index} nối tiếp",
            visual_prompt=f"Cảnh {index} nối tiếp",
            aspect_ratio="9:16",
            target_duration_sec=8,
            _toan_aas_job=job,
        )
        for index in (1, 2)
    ]
    temp_root = ROOT / ".pytest_tmp"
    temp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temp_root) as tmp_dir:
        results = [
            asyncio.run(
                connector._render_scene_async(
                    scene,
                    str(Path(tmp_dir) / f"raw_scene_{scene.scene_id}.mp4"),
                    [],
                )
            )
            for scene in scenes
        ]

    assert all(result["ok"] is True for result in results)
    assert [call["job_id"] for call in calls] == ["134-1", "134-2"]
    assert all(call["duration_seconds"] == 8 for call in calls)
    assert all(call["metadata"]["scene_count"] == 2 for call in calls)
    assert all(call["metadata"]["submit_source"] == "public_user_final_confirm" for call in calls)


def test_r18s12_no_charge_before_valid_final_mp4_and_delivery(tmp_path):
    before = queue.product_video_delivery_charge_decision(
        {"invoice_json": json.dumps({"user_visible_price_xu": 300, "persisted_quoted_price_xu": 300, "customer_charge_planned_xu": 300})},
        {"id": 134},
        {"scene_count": 2, "final_delivered": False},
    )
    mp4 = tmp_path / "final.mp4"
    mp4.write_bytes(b"valid-final-fixture")
    after = queue.product_video_delivery_charge_decision(
        {
            "video_delivered_at": "2026-07-13 08:30:00",
            "video_delivery_message_id": "tg-134",
            "invoice_json": json.dumps({"user_visible_price_xu": 300, "persisted_quoted_price_xu": 300, "customer_charge_planned_xu": 300}),
            "scene_count": 2,
        },
        {"id": 134},
        {
            "scene_count": 2,
            "scene_tasks": [
                {"scene_index": 1, "clip_valid": True, "winning_task_id": "s1"},
                {"scene_index": 2, "clip_valid": True, "winning_task_id": "s2"},
            ],
            "scene_clip_coverage_complete": True,
            "concat_output_valid": True,
            "final_video_path": str(mp4),
            "final_mp4_valid": True,
            "final_delivered": True,
        },
    )

    assert before["ok"] is False
    assert before["amount_xu"] == 0
    assert before["charge_skip_reason"] == "delivery_required_before_charge"
    assert after["ok"] is True
    assert after["amount_xu"] == 300
    assert after["charge_idempotency_key"] == "product_video_final_delivery:134:300"


def test_r18s12_status_and_watchdog_source_contract():
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
    worker_source = (ROOT / "services" / "remote_worker_api.py").read_text(encoding="utf-8")
    queue_source = (ROOT / "services" / "video_project_queue.py").read_text(encoding="utf-8")

    for marker in (
        '"public_provider_freeze"',
        '"hidden_submit_freeze"',
        '"operational_health_state"',
        '"probation_eligible"',
        '"probation_reject_reason"',
        '"candidates_before_filter"',
        '"candidates_after_route_filter"',
        '"candidates_after_hard_block_filter"',
        '"submit_block_reason"',
    ):
        assert marker in bot_source
    assert "current_probation_job_id=safe_int(job.get(\"id\"), 0)" in bot_source
    assert "contract_valid_chain_at_runtime" in worker_source
    assert 'or result.get("contract_valid_provider_chain")' in worker_source
    assert '"provider_submit_block_reason": terminal_reason' in queue_source


def test_r18s12_tests_make_no_real_provider_calls():
    source = Path(__file__).read_text(encoding="utf-8")
    for marker in (
        "requests" + ".post",
        "requests" + ".get",
        "url" + "open",
        "submit_video" + "_job(",
        "video_provider" + "_smoke",
    ):
        assert marker not in source
