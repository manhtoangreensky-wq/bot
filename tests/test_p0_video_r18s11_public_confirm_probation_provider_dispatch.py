from __future__ import annotations

from datetime import datetime
from pathlib import Path

from services import remote_worker_api
from services import video_provider_router as router


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


def _status_payload() -> dict:
    return {
        "provider_chain": ["shopaikey_video", "key4u_video"],
        "effective_provider_chain": ["shopaikey_video", "key4u_video"],
        "providers": [
            {
                "provider": "shopaikey_video",
                "enabled": True,
                "configured": True,
                "credit_ok": True,
                "submit_url_configured": True,
                "poll_url_configured": True,
                "auth_configured": True,
                "model_present": True,
            },
            {
                "provider": "key4u_video",
                "enabled": True,
                "configured": True,
                "credit_ok": True,
                "submit_url_configured": True,
                "poll_url_configured": True,
                "auth_configured": True,
                "model_present": True,
            },
        ],
    }


def _route_ready_unhealthy(provider: str) -> dict:
    return {
        "provider": provider,
        "route_ready": True,
        "live_healthy": False,
        "multi_scene_eligible": False,
        "provider_health_state": "unknown",
        "health_status": "unknown",
        "provider_degraded_for_product_video_public": False,
        "health_transition_reason": "fresh_validated_clip_required",
    }


def _job133_result(*, source: str = "public_user_final_confirm", public_confirmed: bool = True) -> dict:
    snapshot = {
        "provider_eligibility_snapshot_id": "job-133-snapshot",
        "configured_provider_keys": ["shopaikey_video", "key4u_video"],
        "eligible_provider_keys": ["shopaikey_video"],
        "runtime_candidate_keys": ["shopaikey_video"],
        "preconfirm_candidate_keys": ["shopaikey_video"],
        "contract_valid_provider_chain": ["shopaikey_video", "key4u_video"],
        "scene_count": 2,
    }
    return {
        "source": "product_video",
        "product_video": True,
        "admission_enforced": True,
        "admission_snapshot_id": "job-133-snapshot",
        "provider_eligibility_snapshot": snapshot,
        "provider_eligibility_snapshot_id": "job-133-snapshot",
        "configured_provider_chain": ["shopaikey_video", "key4u_video"],
        "runtime_candidate_keys": ["shopaikey_video"],
        "preconfirm_candidate_keys": ["shopaikey_video"],
        "contract_valid_provider_chain": ["shopaikey_video", "key4u_video"],
        "provider_health_at_submit": {
            "shopaikey_video": _route_ready_unhealthy("shopaikey_video"),
            "key4u_video": _route_ready_unhealthy("key4u_video"),
        },
        "scene_count": 2,
        "scenes_total": 2,
        "orchestration_mode": "per_scene_8s",
        "submit_source": source,
        "provider_submit_source": source,
        "original_submit_source": "public_user_final_confirm",
        "public_confirm_submit_source": "public_user_final_confirm",
        "public_user_confirmed": public_confirmed,
        "worker_compatible": True,
        "worker_connected": True,
        "probation_lock_clear": False,
        "probation_job_id": 133,
        "charge": 0,
        "charged_xu": 0,
    }


def _patch_router(monkeypatch) -> None:
    monkeypatch.setattr(router, "provider_status_payload", lambda _env=None: _status_payload())
    monkeypatch.setattr(router, "load_video_provider_adapters", lambda _env=None: [_FixtureAdapter("shopaikey_video"), _FixtureAdapter("key4u_video")])
    monkeypatch.setattr(
        router,
        "product_video_submit_switch_detail",
        lambda _env=None: {"resolved": True, "raw": "1", "source": "test"},
    )


def test_r18s11_job133_candidate_resolver_regression(monkeypatch):
    _patch_router(monkeypatch)

    result = remote_worker_api._product_video_runtime_eligibility(
        {"id": 133},
        _job133_result(),
        {"project_id": 130},
        now=datetime(2026, 7, 12, 8, 30, 0),
    )

    assert result["candidate_filter_stage"] == "worker_runtime_eligibility"
    assert result["candidate_resolver_source"] == "public_user_final_confirm"
    assert result["provider_submit_allowed_at_candidate_resolver"] is True
    assert result["probation_lock_clear_at_candidate_resolver"] is True
    assert result["eligibility_state"] == "probation"
    assert result["runtime_candidate_keys"] == ["shopaikey_video"]
    assert result["probation_candidate_selected"] == "shopaikey_video"


def test_r18s11_source_not_reclassified_as_worker_background(monkeypatch):
    _patch_router(monkeypatch)

    result = remote_worker_api._product_video_runtime_eligibility(
        {"id": 133},
        _job133_result(source="background_retry", public_confirmed=False),
        {"project_id": 130},
        now=datetime(2026, 7, 12, 8, 30, 0),
    )

    assert result["candidate_resolver_source"] == "background_retry"
    assert result["provider_submit_allowed_at_candidate_resolver"] is False
    assert result["provider_submit_block_reason_at_candidate_resolver"] == "hidden_submit_source_blocked"
    assert result["runtime_candidate_keys"] == []
    assert result["probation_admission_allowed"] is False


def test_r18s11_hidden_freeze_does_not_remove_public_probation_candidate(monkeypatch):
    _patch_router(monkeypatch)

    public_result = router.product_video_provider_eligibility_snapshot(
        status=_status_payload(),
        chain=["shopaikey_video"],
        provider_health={"shopaikey_video": _route_ready_unhealthy("shopaikey_video")},
        contract_valid_provider_chain=["shopaikey_video"],
        scene_count=2,
        require_live_health=True,
        allow_public_confirmed_probation=True,
        admission_source="public_user_final_confirm",
        public_user_confirmed=True,
        public_submit_enabled=True,
        worker_compatible=True,
        probation_lock_clear=True,
        hard_block_reason_by_provider={},
    )
    hidden_result = router.product_video_provider_eligibility_snapshot(
        status=_status_payload(),
        chain=["shopaikey_video"],
        provider_health={"shopaikey_video": _route_ready_unhealthy("shopaikey_video")},
        contract_valid_provider_chain=["shopaikey_video"],
        scene_count=2,
        require_live_health=True,
        allow_public_confirmed_probation=True,
        admission_source="background_retry",
        public_user_confirmed=False,
        public_submit_enabled=True,
        worker_compatible=True,
        probation_lock_clear=True,
        hard_block_reason_by_provider={"shopaikey_video": "provider_freeze_active"},
    )

    assert public_result["runtime_candidate_keys"] == ["shopaikey_video"]
    assert public_result["probation_candidate_selected"] == "shopaikey_video"
    assert "provider_freeze_active" not in public_result["candidate_rejection_reason_by_provider"]["shopaikey_video"]
    assert hidden_result["runtime_candidate_keys"] == []
    assert "provider_freeze_active" in hidden_result["candidate_rejection_reason_by_provider"]["shopaikey_video"]


def test_r18s11_provider_submit_guard_allows_public_confirm_and_blocks_hidden():
    live = router.product_video_provider_submit_source_policy(
        {"submit_source": "public_user_final_confirm", "public_user_confirmed": True},
        public_submit_enabled=True,
    )
    hidden = router.product_video_provider_submit_source_policy(
        {"submit_source": "status", "public_user_confirmed": False},
        public_submit_enabled=True,
    )

    assert live["provider_submit_allowed"] is True
    assert live["provider_submit_block_reason"] == ""
    assert hidden["provider_submit_allowed"] is False
    assert hidden["provider_submit_block_reason"] == "hidden_submit_source_blocked"


def test_r18s11_scene_not_terminal_failed_before_candidate_routing_source_contract():
    worker_source = (ROOT / "services" / "remote_worker_api.py").read_text(encoding="utf-8")
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
    runtime = worker_source[
        worker_source.index("def _product_video_runtime_eligibility"):
        worker_source.index("def claim_remote_worker_canary_job")
    ]
    claim = worker_source[
        worker_source.index("if result_payload.get(\"admission_enforced\"):"):
        worker_source.index("claim_state = video_project_queue.product_video_processing_scene_claim_state")
    ]

    assert "allow_public_confirmed_probation=public_confirmed_submit" in runtime
    assert "admission_source=str(submit_policy.get(\"submit_source\") or \"\")" in runtime
    assert "provider_submit_block_reason" in claim
    assert "router_skipped_reason" in claim
    assert "no_eligible_provider_before_scene_dispatch" in claim
    assert "explicit_public_final_confirm = bool(" in bot_source
    assert "hard_block_reason_by_provider={} if explicit_public_final_confirm else {" in bot_source


def test_r18s11_tests_use_no_real_provider_transport():
    source = Path(__file__).read_text(encoding="utf-8")
    for marker in ("requests" + ".post", "url" + "open", "submit" + "_video_job("):
        assert marker not in source
