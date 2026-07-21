from pathlib import Path

import pytest

from services import video_provider_router as router


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    start_at = source.index(start)
    return source[start_at : source.index(end, start_at)]


@pytest.mark.parametrize(
    "source",
    (
        "public_user_final_confirm",
        "public_confirm",
        "final_confirm",
        "user_final_confirm",
        "b14_confirm",
        "public_confirmed_fallback_once",
        "public_confirmed_scene_fallback_once",
    ),
)
def test_every_explicit_public_product_video_confirm_source_is_allowed(source):
    decision = router.product_video_provider_submit_source_policy(
        {
            "submit_source": source,
            "public_user_confirmed": True,
        },
        public_submit_enabled=True,
    )

    assert decision["provider_submit_allowed"] is True
    assert decision["provider_submit_block_reason"] == ""
    assert decision["public_user_confirmed"] is True


@pytest.mark.parametrize(
    "source",
    ("codex_test", "smoke", "debug", "recover", "status", "background_retry", "fallback"),
)
def test_every_hidden_source_remains_blocked_before_provider_submit(source):
    decision = router.product_video_provider_submit_source_policy(
        {"submit_source": source},
        public_submit_enabled=True,
    )

    assert decision["provider_submit_allowed"] is False
    assert decision["provider_submit_block_reason"] == "hidden_submit_source_blocked"
    assert decision["poll_existing_task_allowed"] is False


def test_worker_existing_task_is_poll_only_and_cannot_submit_again():
    decision = router.product_video_provider_submit_source_policy(
        {"submit_source": "worker_poll_existing_task"},
        public_submit_enabled=True,
        poll_existing_task=True,
    )

    assert decision["provider_submit_allowed"] is False
    assert decision["provider_submit_block_reason"] == "worker_poll_existing_task_read_only"
    assert decision["poll_existing_task_allowed"] is True


def test_public_submit_flag_is_still_required_for_explicit_confirm():
    decision = router.product_video_provider_submit_source_policy(
        {
            "submit_source": "public_user_final_confirm",
            "public_user_confirmed": True,
        },
        public_submit_enabled=False,
    )

    assert decision["provider_submit_allowed"] is False
    assert decision["provider_submit_block_reason"] == "public_provider_submit_disabled"


def _degraded_status():
    return {
        "provider_chain": ["shopaikey_video"],
        "effective_provider_chain": ["shopaikey_video"],
        "providers": [
            {
                "provider": "shopaikey_video",
                "enabled": True,
                "configured": True,
                "credit_ok": True,
            }
        ],
    }


def _degraded_health():
    return {
        "shopaikey_video": {
            "route_ready": True,
            "live_healthy": False,
            "provider_health_state": "degraded",
            "provider_degraded_for_product_video_public": True,
        }
    }


def test_explicit_public_confirm_can_use_degraded_provider_as_single_probation(monkeypatch):
    monkeypatch.setattr(router, "load_video_provider_adapters", lambda _env=None: [])
    result = router.product_video_provider_eligibility_snapshot(
        status=_degraded_status(),
        chain=["shopaikey_video"],
        provider_health=_degraded_health(),
        contract_valid_provider_chain=["shopaikey_video"],
        scene_count=2,
        require_live_health=True,
        allow_public_confirmed_probation=True,
        admission_source="public_user_final_confirm",
        public_user_confirmed=True,
        public_submit_enabled=True,
        worker_compatible=True,
        probation_lock_clear=True,
    )

    assert result["eligibility_state"] == "probation"
    assert result["admission_mode"] == "public_confirmed_probation"
    assert result["eligible_provider_keys"] == ["shopaikey_video"]
    assert result["probation_admission_allowed"] is True


def test_same_degraded_provider_is_not_opened_for_non_public_source(monkeypatch):
    monkeypatch.setattr(router, "load_video_provider_adapters", lambda _env=None: [])
    result = router.product_video_provider_eligibility_snapshot(
        status=_degraded_status(),
        chain=["shopaikey_video"],
        provider_health=_degraded_health(),
        contract_valid_provider_chain=["shopaikey_video"],
        scene_count=2,
        require_live_health=True,
        allow_public_confirmed_probation=True,
        admission_source="background_retry",
        public_user_confirmed=False,
        public_submit_enabled=True,
        worker_compatible=True,
        probation_lock_clear=True,
    )

    assert result["eligibility_state"] == "blocked"
    assert result["eligible_provider_keys"] == []
    assert "provider_health_degraded" in result["hard_block_reason_by_provider"]["shopaikey_video"]


def test_explicit_public_confirm_opens_multiscene_when_provider_candidate_is_valid():
    snapshot = {
        "eligible_provider_keys": ["shopaikey_video"],
        "runtime_candidate_keys": ["shopaikey_video"],
    }
    blocked_before_confirm = router.product_video_multi_scene_public_gate(
        2,
        effective_provider_chain=["shopaikey_video"],
        contract_valid_provider_chain=["shopaikey_video"],
        eligibility_snapshot=snapshot,
        public_user_final_confirm=False,
        environ={"PRODUCT_VIDEO_MULTI_SCENE_PUBLIC_ENABLED": "false"},
    )
    allowed_after_confirm = router.product_video_multi_scene_public_gate(
        2,
        effective_provider_chain=["shopaikey_video"],
        contract_valid_provider_chain=["shopaikey_video"],
        eligibility_snapshot=snapshot,
        public_user_final_confirm=True,
        environ={"PRODUCT_VIDEO_MULTI_SCENE_PUBLIC_ENABLED": "false"},
    )

    assert blocked_before_confirm["ok"] is False
    assert allowed_after_confirm["ok"] is True
    assert allowed_after_confirm["multi_scene_public_confirm_override"] is True


def test_scene_selection_and_custom_scene_always_reach_invoice_before_admission():
    scene_button = _between(
        BOT_SOURCE,
        'if action == "b14_scene_count":',
        'if action == "b14_confirm":',
    )
    custom_scene = _between(
        BOT_SOURCE,
        'if str(session.get("current_step") or "") in {"b14_scene_custom", "waiting_scene_count"}:',
        'current_step = str(session.get("current_step") or "")',
    )

    for block in (scene_button, custom_scene):
        assert "video_b14_prepare_project_for_invoice" in block
        assert 'task3d_session_step(uid, "b14_invoice"' in block
        assert "product_video_public_preflight_evaluation" not in block
        assert "product_video_show_public_preflight_panel" not in block


def test_only_final_confirm_evaluates_admission_and_persists_public_source():
    confirm = _between(
        BOT_SOURCE,
        'if action == "b14_confirm":',
        'if action == "b14_job_status":',
    )

    assert "product_video_public_preflight_evaluation(" in confirm
    assert "explicit_public_final_confirm=True" in confirm
    assert '"submit_source": "public_user_final_confirm"' in confirm
    assert '"public_user_confirmed": True' in confirm
    assert "confirm_video_project_invoice" in confirm


def test_runtime_revalidation_preserves_public_confirm_probation_context():
    router_source = (ROOT / "services" / "video_provider_router.py").read_text(encoding="utf-8")
    run_provider = router_source[router_source.index("def run_provider_generation(") :]
    runtime_recheck = _between(
        run_provider,
        "runtime_eligibility_snapshot = product_video_provider_eligibility_snapshot(",
        "runtime_candidates = list(runtime_eligibility_snapshot.get",
    )

    assert "runtime_submit_source_policy = product_video_provider_submit_source_policy(" in run_provider
    assert "poll_existing_task=False" in run_provider
    assert "allow_public_confirmed_probation=runtime_public_confirmed_submit" in runtime_recheck
    assert 'admission_source=str(runtime_submit_source_policy.get("submit_source") or "")' in runtime_recheck
    assert 'public_user_confirmed=bool(runtime_submit_source_policy.get("public_user_confirmed"))' in runtime_recheck
    assert "public_submit_enabled=submit_enabled" in runtime_recheck
    assert "worker_compatible=runtime_worker_compatible" in runtime_recheck
    assert "probation_lock_clear=runtime_probation_lock_clear" in runtime_recheck
    assert "provider_submit_block_reason" in run_provider


def test_public_final_confirm_ignores_non_public_freeze_and_stale_cooldown_only():
    route = _between(
        BOT_SOURCE,
        "def product_video_provider_public_route_preflight",
        "def product_video_multi_scene_health_gate",
    )

    assert "explicit_public_final_confirm = bool(" in route
    assert "and not explicit_public_final_confirm" in route
    assert "product_video_provider_freeze_admission_snapshot(" in route
    assert 'provider_hard_blocks = dict(freeze_admission.get("hard_block_reason_by_provider") or {})' in route
    assert "public_provider_submit_disabled" in route
    assert "product_video_public_maintenance" in route
    assert "worker_incompatible" in route


def test_r18s10_tests_use_no_real_provider_transport():
    source = Path(__file__).read_text(encoding="utf-8")
    for marker in ("requests" + ".post", "url" + "open", "submit" + "_video_job("):
        assert marker not in source
