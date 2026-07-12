from __future__ import annotations

from pathlib import Path

import pytest

from services import remote_worker_api
from services import video_project_queue as queue
from services import video_provider_router as router
from services.video_provider_base import VideoGenerationRequest, VideoPollResult, VideoSubmitResult


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
WORKER_SOURCE = (ROOT / "services" / "remote_worker_api.py").read_text(encoding="utf-8")
ROUTER_SOURCE = (ROOT / "services" / "video_provider_router.py").read_text(encoding="utf-8")


class _Adapter:
    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    def capabilities(self) -> dict:
        return {
            "provider": self.provider_name,
            "configured": True,
            "capabilities": ["text_to_video", "scene_video", "multi_scene_video"],
        }


class _DispatchAdapter(_Adapter):
    def __init__(self, provider_name: str) -> None:
        super().__init__(provider_name)
        self.submit_calls = 0
        self.poll_calls = 0

    def capabilities(self) -> dict:
        return {
            **super().capabilities(),
            "submit_url_configured": True,
            "poll_url_configured": True,
            "auth_configured": True,
            "provider_auth_value_present": True,
            "provider_model_present": True,
            "provider_payload_model": "fixture-model",
        }

    def submit_video_job(self, _request) -> VideoSubmitResult:
        self.submit_calls += 1
        return VideoSubmitResult(
            ok=True,
            provider_name=self.provider_name,
            provider_task_id="fixture-task-r18s13",
            provider_status="in_progress",
            raw={"submit_http_status": 200, "provider_task_id_present": True},
        )

    def poll_video_job(self, provider_task_id: str) -> VideoPollResult:
        self.poll_calls += 1
        return VideoPollResult(
            ok=True,
            provider_name=self.provider_name,
            provider_task_id=provider_task_id,
            status="in_progress",
            raw_status="IN_PROGRESS",
            raw={"poll_http_status": 200, "data": {"status": "IN_PROGRESS"}},
        )

    def materialize_result(self, _result, _job_id):
        raise AssertionError("pending fixture must not download an artifact")


@pytest.fixture(autouse=True)
def _fixture_adapters(monkeypatch):
    monkeypatch.setattr(
        router,
        "load_video_provider_adapters",
        lambda _env=None: [_Adapter("shopaikey_video"), _Adapter("key4u_video")],
    )


def _runtime_context(**overrides) -> dict:
    payload = {
        "provider_freeze": True,
        "provider_freeze_enabled": True,
        "hidden_video_freeze": True,
        "public_submit_enabled": True,
        "provider_configured": True,
        "worker_available": True,
        "worker_compatible": True,
        "payment_freeze": False,
        "tool_freeze": False,
        "security_block": False,
        "hard_public_cost_block": False,
        "public_maintenance": False,
    }
    payload.update(overrides)
    return payload


def _status() -> dict:
    providers = [
        {
            "provider": provider,
            "enabled": True,
            "configured": True,
            "credit_ok": True,
            "submit_url_configured": True,
            "poll_url_configured": True,
            "auth_configured": True,
            "model_present": True,
        }
        for provider in ("shopaikey_video", "key4u_video")
    ]
    return {
        "provider_chain": ["shopaikey_video", "key4u_video"],
        "effective_provider_chain": ["shopaikey_video", "key4u_video"],
        "providers": providers,
    }


def _health() -> dict:
    return {
        "shopaikey_video": {
            "route_ready": True,
            "live_healthy": False,
            "provider_health_state": "degraded",
            "provider_degraded_for_product_video_public": True,
        },
        "key4u_video": {
            "route_ready": True,
            "live_healthy": False,
            "provider_health_state": "unknown",
        },
    }


def _eligibility(truth: dict, *, source: str = "public_user_final_confirm", confirmed: bool = True) -> dict:
    return router.product_video_provider_eligibility_snapshot(
        status=_status(),
        chain=["shopaikey_video", "key4u_video"],
        provider_health=_health(),
        contract_valid_provider_chain=["shopaikey_video", "key4u_video"],
        scene_count=2,
        require_live_health=True,
        allow_public_confirmed_probation=True,
        allow_operational_degradation_probation=True,
        admission_source=source,
        public_user_confirmed=confirmed,
        public_submit_enabled=bool(truth.get("public_live_allowed")),
        worker_compatible=True,
        probation_lock_clear=True,
        global_hard_block_reason=str(truth.get("blocker_code") or ""),
        environ={},
    )


def _worker_result(source: str, confirmed: bool) -> dict:
    truth = router.product_video_freeze_truth(
        source,
        _runtime_context(),
        environ={"PROVIDER_FREEZE_ENABLED": "1"},
    )
    return {
        "product_video": True,
        "admission_enforced": True,
        "provider_eligibility_snapshot_id": "r18s13-worker",
        "provider_eligibility_snapshot": {
            "provider_eligibility_snapshot_id": "r18s13-worker",
            "configured_provider_keys": ["shopaikey_video", "key4u_video"],
            "contract_valid_provider_chain": ["shopaikey_video", "key4u_video"],
        },
        "configured_provider_chain": ["shopaikey_video", "key4u_video"],
        "contract_valid_provider_chain": ["shopaikey_video", "key4u_video"],
        "provider_health_at_submit": _health(),
        "provider_hard_block_reason_by_provider": {},
        "product_video_freeze_truth": truth,
        "provider_freeze": True,
        "public_provider_freeze": False,
        "hidden_submit_freeze": True,
        "background_submit_freeze": True,
        "smoke_freeze": True,
        "submit_source": source,
        "provider_submit_source": source,
        "public_user_confirmed": confirmed,
        "worker_compatible": True,
        "probation_lock_clear": False,
        "probation_job_id": 135,
        "scene_count": 2,
    }


def test_r18s13_hidden_freeze_does_not_set_public_provider_freeze():
    truth = router.product_video_freeze_truth(
        "public_user_final_confirm",
        _runtime_context(),
        environ={"PROVIDER_FREEZE_ENABLED": "1"},
    )
    assert truth["provider_freeze"] is True
    assert truth["hidden_video_freeze"] is True
    assert truth["hidden_submit_freeze"] is True
    assert truth["public_provider_freeze"] is False
    assert truth["public_live_allowed"] is True


def test_r18s13_spend_freeze_does_not_set_public_provider_freeze():
    truth = router.product_video_freeze_truth(
        "public_user_final_confirm",
        _runtime_context(provider_freeze=False, provider_freeze_enabled=False),
        environ={"PROVIDER_SPEND_FREEZE": "1"},
    )
    assert truth["provider_spend_freeze"] is True
    assert truth["hidden_submit_freeze"] is True
    assert truth["public_provider_freeze"] is False
    assert truth["public_live_allowed"] is True


def test_r18s13_smoke_disabled_does_not_set_public_provider_freeze():
    truth = router.product_video_freeze_truth(
        "public_preflight",
        _runtime_context(provider_freeze=False, provider_freeze_enabled=False, hidden_video_freeze=False),
        environ={"REAL_PROVIDER_SMOKE_ENABLED": "0"},
    )
    assert truth["smoke_freeze"] is True
    assert truth["public_provider_freeze"] is False
    assert truth["public_preflight_allowed"] is True


def test_r18s13_explicit_public_freeze_blocks():
    truth = router.product_video_freeze_truth(
        "public_user_final_confirm",
        _runtime_context(provider_freeze=False, provider_freeze_enabled=False, hidden_video_freeze=False),
        environ={"PUBLIC_VIDEO_PROVIDER_FREEZE": "1"},
    )
    assert truth["public_provider_freeze"] is True
    assert truth["public_live_allowed"] is False
    assert truth["blocker_code"] == "public_provider_freeze_active"
    assert truth["blocker_source"] == "env:PUBLIC_VIDEO_PROVIDER_FREEZE"


@pytest.mark.parametrize(
    ("override", "blocker"),
    [
        ({"payment_freeze": True}, "payment_freeze_active"),
        ({"tool_freeze": True}, "tool_freeze_active"),
        ({"security_block": True}, "security_block_active"),
        ({"hard_public_cost_block": True}, "hard_public_cost_block_active"),
    ],
)
def test_r18s13_payment_tool_security_cost_blocks(override, blocker):
    truth = router.product_video_freeze_truth(
        "public_user_final_confirm",
        _runtime_context(**override),
        environ={},
    )
    assert truth["public_live_allowed"] is False
    assert truth["blocker_code"] == blocker


@pytest.mark.parametrize("source", ["debug", "status", "recover", "smoke", "background_retry"])
def test_r18s13_hidden_background_smoke_debug_remain_blocked(source):
    truth = router.product_video_freeze_truth(source, _runtime_context(), environ={})
    assert truth["public_live_allowed"] is True
    assert truth["blocker_code"]
    assert truth["blocker_source"].startswith("source:")
    policy = router.product_video_provider_submit_source_policy(
        {"submit_source": source, "public_user_confirmed": False},
        public_submit_enabled=True,
    )
    assert policy["provider_submit_allowed"] is False


def test_r18s13_live_fixture_public_preflight_reopens():
    truth = router.product_video_freeze_truth(
        "public_preflight",
        _runtime_context(),
        environ={"PROVIDER_FREEZE_ENABLED": "1", "PROVIDER_SPEND_FREEZE": "1"},
    )
    assert truth["public_provider_freeze"] is False
    assert truth["hidden_submit_freeze"] is True
    assert truth["public_live_allowed"] is True
    assert truth["public_preflight_allowed"] is True


def test_r18s13_live_fixture_invoice_present():
    callback = BOT_SOURCE[BOT_SOURCE.index('if action == "b14_scene_count":'):BOT_SOURCE.index('if action == "b14_confirm":')]
    text_input = BOT_SOURCE[BOT_SOURCE.index('if str(session.get("current_step") or "") in {"b14_scene_custom", "waiting_scene_count"}'):]
    assert "video_b14_prepare_project_for_invoice" in callback
    assert "video_b14_invoice_text" in callback
    assert "video_b14_invoice_text" in text_input[:7000]


def test_r18s13_live_fixture_final_confirm_present():
    keyboard = BOT_SOURCE[BOT_SOURCE.index("def video_b14_invoice_keyboard"):BOT_SOURCE.index("def video_b14_eta_seconds")]
    assert 'callback_data="vproduct|b14_confirm"' in keyboard
    assert "Xác nhận tạo video" in keyboard


def test_r18s13_no_records_before_final_confirm():
    preflight = BOT_SOURCE[BOT_SOURCE.index("def product_video_public_preflight_evaluation"):BOT_SOURCE.index("def product_video_public_preflight_panel_text")]
    for marker in ("create_video_project(", "enqueue_video_render_job(", "ensure_product_video_dispatch_outbox("):
        assert marker not in preflight


def test_r18s13_no_provider_call_before_final_confirm():
    preflight = BOT_SOURCE[BOT_SOURCE.index("def product_video_public_preflight_evaluation"):BOT_SOURCE.index("def product_video_public_preflight_panel_text")]
    for marker in (
        "run_provider_generation(",
        "submit" + "_video_job(",
        "requests" + ".post(",
    ):
        assert marker not in preflight


def test_r18s13_no_charge_before_valid_delivery():
    decision = queue.product_video_delivery_charge_decision(
        {"invoice_json": '{"user_visible_price_xu":300,"persisted_quoted_price_xu":300,"customer_charge_planned_xu":300}'},
        {"id": 135},
        {"scene_count": 2, "final_delivered": False, "final_mp4_valid": False},
    )
    assert decision["ok"] is False
    assert decision["amount_xu"] == 0


def test_r18s13_status_has_no_public_freeze_contradiction():
    status = BOT_SOURCE[BOT_SOURCE.index("def video_public_status_payload"):BOT_SOURCE.index("def video_public_status_text")]
    assert 'public_provider_freeze = bool(ops.get("provider_freeze") or PROVIDER_FREEZE_ENABLED)' not in status
    assert 'product_video_freeze_truth = dict(' in status
    assert '"provider_freeze": bool(product_video_freeze_truth.get("provider_freeze"))' in status


def test_r18s13_status_hidden_freeze_consistent():
    truth = router.product_video_freeze_truth("public_user_final_confirm", _runtime_context(), environ={})
    assert truth["hidden_video_freeze"] is truth["hidden_submit_freeze"] is True
    status = BOT_SOURCE[BOT_SOURCE.index("def video_public_status_payload"):BOT_SOURCE.index("def video_public_status_text")]
    assert '"hidden_video_freeze": hidden_video_freeze' in status
    assert '"hidden_submit_freeze": bool(product_video_freeze_truth.get("hidden_submit_freeze"))' in status


def test_r18s13_status_reports_exact_blocker_source():
    truth = router.product_video_freeze_truth(
        "public_user_final_confirm",
        _runtime_context(),
        environ={"PUBLIC_VIDEO_PROVIDER_FREEZE": "1"},
    )
    assert truth["blocker_source"] == "env:PUBLIC_VIDEO_PROVIDER_FREEZE"
    assert "Product Video freeze blocker source" in BOT_SOURCE


def test_r18s13_status_public_allowed_under_hidden_freeze():
    truth = router.product_video_freeze_truth("public_user_final_confirm", _runtime_context(), environ={})
    assert truth["hidden_submit_freeze"] is True
    assert truth["public_live_allowed"] is True
    assert truth["blocker_code"] == ""


def test_r18s13_r18s12_probation_preserved():
    truth = router.product_video_freeze_truth("public_user_final_confirm", _runtime_context(), environ={})
    result = _eligibility(truth)
    assert result["probation_candidate_keys"] == ["shopaikey_video", "key4u_video"]
    assert result["eligible_provider_keys"] == ["shopaikey_video"]


def test_r18s13_exactly_one_probation_candidate():
    result = _eligibility(
        router.product_video_freeze_truth("public_user_final_confirm", _runtime_context(), environ={})
    )
    assert result["candidate_count"] == 1
    assert result["probation_candidate_selected"] == "shopaikey_video"


def test_r18s13_router_runs_after_public_final_confirm():
    truth = router.product_video_freeze_truth("public_user_final_confirm", _runtime_context(), environ={})
    result = _eligibility(truth)
    policy = router.product_video_provider_submit_source_policy(
        {"submit_source": "public_user_final_confirm", "public_user_confirmed": True},
        public_submit_enabled=truth["public_live_allowed"],
    )
    assert result["eligible_provider_keys"] == ["shopaikey_video"]
    assert policy["provider_submit_allowed"] is True
    assert "product_video_freeze_truth(" in WORKER_SOURCE
    assert "product_video_freeze_truth(" in ROUTER_SOURCE


def test_r18s13_public_confirm_hidden_freeze_dispatches_once_with_fixture(monkeypatch, tmp_path):
    adapter = _DispatchAdapter("shopaikey_video")
    monkeypatch.setattr(router, "provider_status_payload", lambda _env=None: _status())
    monkeypatch.setattr(
        router,
        "provider_candidate_adapters",
        lambda _capability, _env, _status_payload: [adapter],
    )
    request = VideoGenerationRequest(
        job_id="r18s13-scene-1",
        product_type="video_ai_prompt",
        video_flow_type="video_ai_prompt",
        prompt="fixture only",
        duration_seconds=8,
        required_capability="text_to_video",
        metadata={
            "product_video": True,
            "allow_provider_pending": True,
            "submit_source": "public_user_final_confirm",
            "public_user_confirmed": True,
            "worker_compatible": True,
        },
    )

    result = router.run_provider_generation(
        request,
        output_dir=str(tmp_path),
        environ={
            "PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED": "1",
            "PROVIDER_FREEZE_ENABLED": "1",
            "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
            "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
        },
        sleep_func=lambda _seconds: None,
    )

    assert adapter.submit_calls == 1
    assert adapter.poll_calls == 1
    assert result["provider_submit_called"] is True
    assert result["continue_polling"] is True
    assert result["public_provider_freeze"] is False
    assert result["hidden_submit_freeze"] is True
    assert result["public_live_provider_allowed"] is True
    assert result["no_charge"] is True


def test_r18s13_explicit_public_freeze_blocks_fixture_before_submit(monkeypatch, tmp_path):
    adapter = _DispatchAdapter("shopaikey_video")
    monkeypatch.setattr(router, "provider_status_payload", lambda _env=None: _status())
    monkeypatch.setattr(
        router,
        "provider_candidate_adapters",
        lambda _capability, _env, _status_payload: [adapter],
    )
    request = VideoGenerationRequest(
        job_id="r18s13-blocked-scene-1",
        product_type="video_ai_prompt",
        video_flow_type="video_ai_prompt",
        prompt="fixture only",
        duration_seconds=8,
        required_capability="text_to_video",
        metadata={
            "product_video": True,
            "allow_provider_pending": True,
            "submit_source": "public_user_final_confirm",
            "public_user_confirmed": True,
            "worker_compatible": True,
        },
    )

    result = router.run_provider_generation(
        request,
        output_dir=str(tmp_path),
        environ={
            "PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED": "1",
            "PUBLIC_VIDEO_PROVIDER_FREEZE": "1",
        },
        sleep_func=lambda _seconds: None,
    )

    assert adapter.submit_calls == 0
    assert adapter.poll_calls == 0
    assert result["provider_submit_called"] is False
    assert result["public_provider_freeze"] is True
    assert result["blocker"] == "public_provider_freeze_active"
    assert result["freeze_blocker_source"] == "env:PUBLIC_VIDEO_PROVIDER_FREEZE"
    assert result["no_charge"] is True


def test_r18s13_no_scene_prefail():
    claim = WORKER_SOURCE[WORKER_SOURCE.index("def _product_video_runtime_eligibility"):WORKER_SOURCE.index("def claim_remote_worker_canary_job")]
    assert '"router_called": False' in claim
    assert "terminal_failed" not in claim


def test_r18s13_public_hard_freeze_still_blocks():
    truth = router.product_video_freeze_truth(
        "public_user_final_confirm",
        _runtime_context(),
        environ={"PUBLIC_VIDEO_PROVIDER_FREEZE": "1"},
    )
    result = _eligibility(truth)
    assert result["eligible_provider_keys"] == []
    assert result["blocker"] == "public_provider_freeze_active"


def test_r18s13_generic_provider_freeze_policy_is_hidden_only():
    policy = router.product_video_provider_freeze_probation_policy(
        provider="shopaikey_video",
        provider_frozen=True,
        provider_freeze_reason="ENV_PROVIDER_FREEZE",
        explicit_public_final_confirm=True,
    )
    assert policy["hidden_submit_freeze"] is True
    assert policy["hidden_only_freeze"] is True
    assert policy["hard_block_reason"] == ""


def test_r18s13_worker_revalidation_uses_canonical_truth():
    runtime = WORKER_SOURCE[WORKER_SOURCE.index("def _product_video_runtime_eligibility"):WORKER_SOURCE.index("def claim_remote_worker_canary_job")]
    assert "runtime_freeze_truth = video_provider_router.product_video_freeze_truth(" in runtime
    assert 'global_hard_block_reason=str(runtime_freeze_truth.get("blocker_code") or "")' in runtime


def test_r18s13_worker_public_confirm_survives_hidden_freeze(monkeypatch):
    monkeypatch.setattr(router, "provider_status_payload", lambda _env=None: _status())
    monkeypatch.setattr(
        router,
        "product_video_submit_switch_detail",
        lambda _env=None: {"resolved": True, "source": "fixture"},
    )
    result = remote_worker_api._product_video_runtime_eligibility(
        {"id": 135},
        _worker_result("public_user_final_confirm", True),
        {"project_id": 135},
    )
    assert result["public_provider_freeze"] is False
    assert result["hidden_submit_freeze"] is True
    assert result["public_live_provider_allowed"] is True
    assert result["runtime_candidate_keys"] == ["shopaikey_video"]
    assert result["provider_submit_allowed"] is True


def test_r18s13_worker_hidden_status_stays_blocked(monkeypatch):
    monkeypatch.setattr(router, "provider_status_payload", lambda _env=None: _status())
    monkeypatch.setattr(
        router,
        "product_video_submit_switch_detail",
        lambda _env=None: {"resolved": True, "source": "fixture"},
    )
    result = remote_worker_api._product_video_runtime_eligibility(
        {"id": 135},
        _worker_result("status", False),
        {"project_id": 135},
    )
    assert result["runtime_candidate_keys"] == []
    assert result["provider_submit_allowed"] is False
    assert result["provider_submit_block_reason"] == "hidden_submit_source_blocked"


def test_r18s13_tests_make_no_real_provider_calls():
    source = Path(__file__).read_text(encoding="utf-8")
    for marker in (
        "requests" + ".post",
        "urllib.request." + "urlopen",
        "GenericHttp" + "VideoProvider(",
    ):
        assert marker not in source
