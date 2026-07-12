from pathlib import Path

import pytest

from services import video_project_queue as queue
from services import video_provider_router as router


ROOT = Path(__file__).resolve().parents[1]


def _preflight(
    *,
    eligibility_state="healthy",
    healthy=None,
    probation=None,
    hard_blocked=None,
    worker_compatible=True,
    worker_reason="",
    lock_clear=True,
    lock_status="clear",
    hard_reason="",
    no_charge_reason="",
):
    healthy = list(healthy or [])
    probation = list(probation or [])
    hard_blocked = list(hard_blocked or [])
    return {
        "worker_compatible": worker_compatible,
        "worker_admission_block_reason": worker_reason,
        "probation_lock_clear": lock_clear,
        "probation_lock_status": lock_status,
        "eligibility_state": eligibility_state,
        "admission_mode": (
            "healthy"
            if eligibility_state == "healthy"
            else "probation_pending_final_confirm"
            if eligibility_state == "probation"
            else "blocked"
        ),
        "healthy_candidate_keys": healthy,
        "probation_candidate_keys": probation,
        "hard_blocked_candidate_keys": hard_blocked,
        "preflight_ready_for_final_confirm": bool(healthy or probation),
        "provider_hard_block_reason": hard_reason,
        "no_charge_reason": no_charge_reason,
    }


def _gate(preflight, *, ok=False, blocker=""):
    return {
        "ok": ok,
        "preflight_ready_for_final_confirm": bool(
            preflight.get("healthy_candidate_keys") or preflight.get("probation_candidate_keys")
        ),
        "eligibility_state": preflight.get("eligibility_state"),
        "admission_mode": preflight.get("admission_mode"),
        "healthy_candidate_keys": list(preflight.get("healthy_candidate_keys") or []),
        "probation_candidate_keys": list(preflight.get("probation_candidate_keys") or []),
        "hard_blocked_candidate_keys": list(preflight.get("hard_blocked_candidate_keys") or []),
        "blocker": blocker,
    }


def test_healthy_worker_and_provider_resolve_ready_healthy():
    preflight = _preflight(healthy=["shopaikey_video"])
    result = router.resolve_product_video_public_preflight_state(
        preflight,
        _gate(preflight, ok=True),
    )

    assert result["preflight_resolved_state"] == "ready_healthy"
    assert result["final_confirm_enabled"] is True
    assert result["selected_admission_mode"] == "healthy"
    assert result["healthy_candidate_count"] == 1


def test_probation_candidate_survives_soft_preconfirm_blocker_and_enables_confirm():
    preflight = _preflight(
        eligibility_state="probation",
        probation=["shopaikey_video"],
    )
    result = router.resolve_product_video_public_preflight_state(
        preflight,
        _gate(preflight, blocker="probation_requires_public_final_confirm"),
    )

    assert result["preflight_resolved_state"] == "ready_probation"
    assert result["final_confirm_enabled"] is True
    assert result["selected_admission_mode"] == queue.PRODUCT_VIDEO_PROBATION_ADMISSION_MODE
    assert result["probation_candidate_count"] == 1
    assert result["preflight_blocker_code"] == ""


def test_zero_candidate_resolves_blocked_provider_without_indefinite_state():
    preflight = _preflight(eligibility_state="blocked")
    result = router.resolve_product_video_public_preflight_state(
        preflight,
        _gate(preflight, blocker="no_eligible_product_video_provider"),
    )

    assert result["preflight_resolved_state"] == "blocked_provider"
    assert result["final_confirm_enabled"] is False
    assert result["final_confirm_disabled_reason"] == "no_eligible_product_video_provider"


@pytest.mark.parametrize(
    ("preflight", "expected"),
    [
        (
            _preflight(
                eligibility_state="blocked",
                worker_compatible=False,
                worker_reason="worker_heartbeat_stale",
            ),
            "blocked_worker",
        ),
        (
            _preflight(
                eligibility_state="blocked",
                lock_clear=False,
                lock_status="cooldown",
                hard_reason="provider_preflight_all_unavailable",
            ),
            "blocked_cooldown",
        ),
        (
            _preflight(
                eligibility_state="blocked",
                hard_blocked=["shopaikey_video"],
                hard_reason="submit_route_missing",
            ),
            "blocked_configuration",
        ),
        (
            {
                **_preflight(eligibility_state="blocked", lock_clear=False),
                "probation_active": True,
                "active_probation_job_id": 88,
            },
            "blocked_concurrency",
        ),
        (
            _preflight(
                eligibility_state="blocked",
                hard_reason="public_provider_submit_disabled",
            ),
            "blocked_security_cost",
        ),
    ],
)
def test_hard_blocks_resolve_to_actionable_final_states(preflight, expected):
    result = router.resolve_product_video_public_preflight_state(
        preflight,
        _gate(preflight, blocker=str(preflight.get("provider_hard_block_reason") or "")),
    )

    assert result["preflight_resolved_state"] == expected
    assert result["final_confirm_enabled"] is False
    assert result["preflight_resolution_final"] is True


def test_expired_and_internal_error_are_final_states():
    expired = router.resolve_product_video_public_preflight_state(
        {},
        {},
        context_valid=False,
    )
    failed = router.resolve_product_video_public_preflight_state(
        {},
        {},
        internal_error="preflight_evaluation_error:RuntimeError",
    )

    assert expired["preflight_resolved_state"] == "expired_context"
    assert failed["preflight_resolved_state"] == "internal_error"
    assert expired["final_confirm_enabled"] is False
    assert failed["final_confirm_enabled"] is False


def test_all_resolver_outputs_exclude_transient_final_states():
    samples = [
        router.resolve_product_video_public_preflight_state(
            _preflight(healthy=["shopaikey_video"]),
            _gate(_preflight(healthy=["shopaikey_video"]), ok=True),
        ),
        router.resolve_product_video_public_preflight_state(
            _preflight(eligibility_state="blocked"),
            {},
        ),
        router.resolve_product_video_public_preflight_state({}, {}, context_valid=False),
        router.resolve_product_video_public_preflight_state({}, {}, internal_error="fixture_error"),
    ]
    transient = {"checking", "unknown", "pending", "evaluating"}

    assert router.PRODUCT_VIDEO_PUBLIC_PREFLIGHT_RESOLVED_STATES.isdisjoint(transient)
    assert all(item["preflight_resolved_state"] not in transient for item in samples)
    assert all(item["preflight_resolution_final"] is True for item in samples)


def _source() -> str:
    return (ROOT / "bot.py").read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    start_at = source.index(start)
    return source[start_at : source.index(end, start_at)]


def test_public_panels_have_final_copy_and_correct_confirm_refresh_buttons():
    source = _source()
    text = _between(
        source,
        "def product_video_public_preflight_panel_text",
        "def product_video_public_preflight_panel_keyboard",
    )
    keyboard = _between(
        source,
        "def product_video_public_preflight_panel_keyboard",
        "def product_video_store_public_preflight_context",
    )

    assert "Hệ thống đã sẵn sàng" in text
    assert "Có thể bắt đầu thử tạo" in text
    assert "Hệ thống dựng video: Tạm thời chưa sẵn sàng" in text
    assert "Đang kiểm tra" not in text
    assert 'callback_data="vproduct|b14_confirm"' in keyboard
    assert 'callback_data="vproduct|b14_preflight_refresh"' in keyboard
    assert 'panel_kind in {"ready", "ready_try"}' in keyboard
    assert 'panel_kind in {"ready_try", "blocked", "error"}' in keyboard


def test_refresh_rereads_authoritative_state_and_edits_same_message_without_records():
    source = _source()
    refresh = _between(
        source,
        'if action == "b14_preflight_refresh":',
        'if action == "b14_scene_count":',
    )
    panel = _between(
        source,
        "async def product_video_show_public_preflight_panel",
        "def product_video_bot_watchdog_eligibility",
    )

    assert "product_video_show_public_preflight_panel" in refresh
    assert "product_video_public_preflight_evaluation(scene_count)" in panel
    assert "safe_edit_or_send" in panel
    assert "evaluation or product_video_public_preflight_evaluation" in panel
    for forbidden in (
        "create_video_project",
        "confirm_video_project_invoice",
        "create_video_job",
        "video_dispatch_outbox",
        "acquire_product_video_probation",
        "spend_fixed_credit",
    ):
        assert forbidden not in refresh
        assert forbidden not in panel


def test_scene_button_custom_text_and_owner_follow_same_current_evaluator():
    source = _source()
    scene_button = _between(
        source,
        'if action == "b14_scene_count":',
        'if action == "b14_confirm":',
    )
    custom_text = _between(
        source,
        'if str(session.get("current_step") or "") in {"b14_scene_custom", "waiting_scene_count"}:',
        'current_step = str(session.get("current_step") or "")',
    )

    assert "scene_evaluation = product_video_public_preflight_evaluation(" in scene_button
    assert "preflight_snapshot=provider_preflight" in scene_button
    assert "custom_evaluation = product_video_public_preflight_evaluation(count)" in custom_text
    assert "if not video_b14_is_admin_or_owner(uid)" not in scene_button
    assert "if not video_b14_is_admin_or_owner(uid)" not in custom_text
    assert "video_b14_public_render_guard" not in scene_button
    assert "video_b14_public_render_guard" not in custom_text


def test_only_explicit_final_confirm_uses_signed_admission_and_creates_runtime_records():
    source = _source()
    confirm = _between(
        source,
        'if action == "b14_confirm":',
        'if action == "b14_job_status":',
    )

    assert "explicit_public_final_confirm=True" in confirm
    assert "video_b14_public_render_guard" not in confirm
    assert "build_product_video_public_final_admission" in confirm
    assert "require_provider_admission=True" in confirm
    assert '"submit_source": "public_user_final_confirm"' in confirm
    assert "confirm_video_project_invoice" in confirm


def test_admin_status_exposes_final_resolution_truth_without_secrets():
    source = _source()
    payload = _between(source, "def video_public_status_payload", "def video_public_status_text")
    status = _between(source, "def video_public_status_text", "def video_public_status_chunks")

    assert '"product_video_public_preflight_resolution"' in payload
    for field in (
        "preflight_resolved_state",
        "preflight_blocker_code",
        "worker_eligible",
        "healthy_candidate_count",
        "probation_candidate_count",
        "hard_blocked_candidate_count",
        "selected_admission_mode",
        "final_confirm_enabled",
        "final_confirm_disabled_reason",
    ):
        assert field in payload or field in status
    assert "AUTH_HEADER_VALUE" not in status
    assert "API_KEY" not in status


def test_r18s7_r18s8_b13_r18c_and_pr370_remain_in_place_without_real_calls():
    bot_source = _source()
    queue_source = (ROOT / "services" / "video_project_queue.py").read_text(encoding="utf-8")
    test_source = Path(__file__).read_text(encoding="utf-8")

    assert queue.PRODUCT_VIDEO_CANONICAL_ENGINE_ENTRY == "b13_r18c"
    assert "product_video_assert_final_admission" in queue_source
    assert "product_video_probation_lock_state" in queue_source
    assert "def can_cleanup_workspace" in bot_source
    assert "def cleanup_subtitle_dub_pipeline_workspace_result" in bot_source
    for marker in (
        "requests" + ".post",
        "url" + "open",
        "run_provider" + "_generation",
        "submit" + "_video",
    ):
        assert marker not in test_source
