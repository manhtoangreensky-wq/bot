import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from services import remote_worker_api
from services import video_project_queue as queue
from services import video_provider_router as router


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SHA = "4f710061ce1806d3fc625495d13efbec7d2180fd"


def _status(*providers: str) -> dict:
    chain = list(providers or ("shopaikey_video",))
    return {
        "provider_chain": chain,
        "effective_provider_chain": chain,
        "providers": [
            {
                "provider": provider,
                "enabled": True,
                "configured": True,
                "credit_ok": True,
            }
            for provider in chain
        ],
    }


def _health(*providers: str, state: str = "unknown") -> dict:
    live_healthy = state == "healthy"
    degraded = state == "degraded"
    return {
        provider: {
            "provider": provider,
            "route_ready": True,
            "live_healthy": live_healthy,
            "recent_valid_output": live_healthy,
            "multi_scene_eligible": live_healthy,
            "health_status": state,
            "provider_health_state": state,
            "probation": state == "probation",
            "provider_degraded_for_product_video_public": degraded,
        }
        for provider in (providers or ("shopaikey_video",))
    }


def _eligibility(*, providers=("shopaikey_video",), state="unknown", **kwargs) -> dict:
    return router.product_video_provider_eligibility_snapshot(
        status=_status(*providers),
        chain=list(providers),
        provider_health=_health(*providers, state=state),
        contract_valid_provider_chain=list(providers),
        scene_count=2,
        require_live_health=True,
        **kwargs,
    )


def test_route_ready_stale_health_is_probation_not_permanent_zero_candidate_deadlock():
    snapshot = _eligibility()

    assert snapshot["eligibility_state"] == "probation"
    assert snapshot["probation_candidate_keys"] == ["shopaikey_video"]
    assert snapshot["eligible_provider_keys"] == []
    assert snapshot["admission_mode"] == "probation_pending_final_confirm"
    assert snapshot["blocker"] == "probation_requires_public_final_confirm"


def test_explicit_public_final_confirm_admits_exactly_one_probation_candidate():
    snapshot = _eligibility(
        providers=("shopaikey_video", "key4u_video"),
        allow_public_confirmed_probation=True,
        admission_source="public_user_final_confirm",
        public_user_confirmed=True,
        public_submit_enabled=True,
        worker_compatible=True,
        probation_lock_clear=True,
    )

    assert snapshot["eligibility_state"] == "probation"
    assert snapshot["probation_candidate_keys"] == ["shopaikey_video", "key4u_video"]
    assert snapshot["eligible_provider_keys"] == ["shopaikey_video"]
    assert snapshot["candidate_count"] == 1
    assert snapshot["admission_mode"] == queue.PRODUCT_VIDEO_PROBATION_ADMISSION_MODE
    assert snapshot["probation_admission_allowed"] is True


def test_hidden_debug_watchdog_and_status_sources_cannot_admit_probation():
    for source in ("debug", "status", "watchdog", "recover", "smoke", "codex_test", "background_retry"):
        snapshot = _eligibility(
            allow_public_confirmed_probation=True,
            admission_source=source,
            public_user_confirmed=True,
            public_submit_enabled=True,
            worker_compatible=True,
            probation_lock_clear=True,
        )
        assert snapshot["eligible_provider_keys"] == []
        assert snapshot["probation_admission_allowed"] is False
        assert snapshot["admission_mode"] == "probation_pending_final_confirm"


def test_hard_block_and_active_cooldown_never_become_probation():
    disabled = _eligibility(global_hard_block_reason="public_provider_submit_disabled")
    cooldown = _eligibility(state="degraded")
    unavailable_health = _health("shopaikey_video", state="unavailable")
    unavailable_health["shopaikey_video"]["route_ready"] = False
    unavailable = router.product_video_provider_eligibility_snapshot(
        status=_status("shopaikey_video"),
        chain=["shopaikey_video"],
        provider_health=unavailable_health,
        contract_valid_provider_chain=["shopaikey_video"],
    )

    assert disabled["eligibility_state"] == "blocked"
    assert disabled["probation_candidate_keys"] == []
    assert disabled["hard_block_reason"] == "public_provider_submit_disabled"
    assert cooldown["eligibility_state"] == "blocked"
    assert cooldown["hard_blocked_candidate_keys"] == ["shopaikey_video"]
    assert "provider_health_degraded" in cooldown["hard_block_reason_by_provider"]["shopaikey_video"]
    assert unavailable["eligibility_state"] == "blocked"
    assert "provider_route_not_ready" in unavailable["hard_block_reason_by_provider"]["shopaikey_video"]


def test_fresh_valid_delivery_health_remains_normal_healthy_admission():
    snapshot = _eligibility(state="healthy")

    assert snapshot["eligibility_state"] == "healthy"
    assert snapshot["admission_mode"] == "healthy"
    assert snapshot["eligible_provider_keys"] == ["shopaikey_video"]


def test_probation_provider_is_not_promoted_by_artifact_before_telegram_delivery():
    now_epoch = datetime(2030, 1, 2, 3, 4, 5).timestamp()
    base_attempt = {
        "provider": "shopaikey_video",
        "job_id": 808,
        "scene_index": 1,
        "provider_task_id": "task-r18s8",
        "provider_status": "SUCCESS",
        "result_url": "https://fixture.invalid/video.mp4",
        "artifact_size": 1024,
        "artifact_valid": True,
        "scene_coverage_expected": 1,
        "scene_coverage_count": 1,
        "scene_clip_coverage_complete": True,
        "final_mp4_valid": True,
        "admission_mode": queue.PRODUCT_VIDEO_PROBATION_ADMISSION_MODE,
        "updated_at": "2030-01-02 03:03:55",
    }
    before = router.product_video_provider_public_degradation(
        "shopaikey_video",
        [base_attempt],
        route_ready=True,
        now_epoch=now_epoch,
    )
    after = router.product_video_provider_public_degradation(
        "shopaikey_video",
        [{**base_attempt, "final_delivered": True, "delivery_succeeded": True}],
        route_ready=True,
        now_epoch=now_epoch,
    )

    assert before["live_healthy"] is False
    assert before["recent_valid_output"] is False
    assert after["live_healthy"] is True
    assert after["recent_valid_output"] is True


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "r18s8.db")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _project(conn: sqlite3.Connection, *, user_id: int, scene_count: int = 2) -> dict:
    shared = {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "product_type": "video_ai_prompt",
        "engine_adapter": "text_to_video",
        "orchestration_mode": "per_scene_8s",
        "provider_orchestration_mode": "per_scene_8s",
        "provider_chain": ["shopaikey_video"],
        "scene_count": scene_count,
    }
    invoice = {
        **shared,
        "tier": "basic",
        "package_xu": 300,
        "quality_tier": 300,
        "duration_seconds": scene_count * 8,
        "scene_duration_seconds": 8,
        "user_visible_price_xu": 300,
        "persisted_quoted_price_xu": 300,
        "customer_charge_planned_xu": 300,
        "wallet_charge_amount_xu": 300,
        "list_price_xu": 400,
        "provider_budget_xu": 400,
    }
    project = queue.create_video_project(
        conn,
        user_id=user_id,
        profile_id="video_ai_prompt",
        topic=f"R18S8 probation {user_id}",
        ratio="9:16",
        asset_pack=shared,
    )
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="draft_invoice",
        invoice_json=invoice,
        scene_count=scene_count,
        prompt_text="R18S8 public-confirmed probation",
        quality_tier=300,
        total_xu_estimated=300,
    )
    return queue.get_video_project(conn, int(project["project_id"]))


def _probation_admission(project: dict, *, snapshot_id: str) -> dict:
    checked_at = queue.now_text()
    candidate = "shopaikey_video"
    quote = queue.product_video_admission_quote_fingerprint(project, int(project["user_id"]))
    snapshot = {
        "provider_eligibility_snapshot_id": snapshot_id,
        "admission_snapshot_id": snapshot_id,
        "admission_checked_at": checked_at,
        "admission_user_id": int(project["user_id"]),
        "admission_project_id": int(project["project_id"]),
        "admission_quote_fingerprint": quote,
        "admission_callback_handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "admission_callback_data": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK,
        "eligible_provider_keys": [candidate],
        "runtime_candidate_keys": [candidate],
        "final_eligible_provider_count": 1,
    }
    return queue.sign_product_video_final_admission_context(
        {
            "ok": True,
            "provider_eligibility_snapshot": snapshot,
            "provider_eligibility_snapshot_id": snapshot_id,
            "admission_snapshot_id": snapshot_id,
            "admission_checked_at": checked_at,
            "admission_ttl_seconds": 60,
            "admission_candidate_keys": [candidate],
            "admission_candidate_count": 1,
            "admission_result": "PASS",
            "admission_block_reason": "",
            "admission_user_id": int(project["user_id"]),
            "admission_project_id": int(project["project_id"]),
            "admission_quote_fingerprint": quote,
            "admission_callback_handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
            "admission_callback_data": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK,
            "admission_provider_health_gate_pass": True,
            "admission_worker_runtime_sha": RUNTIME_SHA,
            "admission_worker_sha": RUNTIME_SHA,
            "admission_worker_version_compatible": True,
            "admission_route_requires_provider": True,
            "worker_generation_id": "generation-r18s8",
            "worker_git_sha": RUNTIME_SHA,
            "runtime_sha": RUNTIME_SHA,
            "worker_compatible": True,
            "worker_connected": True,
            "worker_heartbeat_fresh": True,
            "worker_lease_valid": True,
            "worker_sha_match": True,
            "worker_capability_match": True,
            "worker_identity_conflict": False,
            "route_requires_provider": True,
            "handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
            "duplicate_confirm_handler_detected": False,
            "admission_mode": queue.PRODUCT_VIDEO_PROBATION_ADMISSION_MODE,
            "probation_candidate_key": candidate,
            "probation_reason": "provider_fresh_validated_success_required",
            "probation_lock_clear": True,
            "submit_source": "public_user_final_confirm",
            "public_user_confirmed": True,
        }
    )


def _confirm(conn: sqlite3.Connection, project: dict, admission: dict) -> dict:
    return queue.confirm_public_product_video_invoice(
        conn,
        project_id=int(project["project_id"]),
        user_id=int(project["user_id"]),
        balance_xu=300,
        provider_admission=admission,
    )


def test_two_simultaneous_probation_admissions_create_only_one_active_job(tmp_path):
    conn = _conn(tmp_path)
    first_project = _project(conn, user_id=801)
    second_project = _project(conn, user_id=802)

    first = _confirm(conn, first_project, _probation_admission(first_project, snapshot_id="r18s8-first"))
    second = _confirm(conn, second_project, _probation_admission(second_project, snapshot_id="r18s8-second"))

    assert first["ok"] is True
    assert second["ok"] is False
    assert second["reason"] == "product_video_probation_lock_active"
    assert second["job_created"] is False
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM video_dispatch_outbox").fetchone()[0] == 1
    lock = queue.product_video_probation_lock_state(conn)
    assert lock["probation_active"] is True
    assert lock["active_probation_job_id"] == int(first["job"]["id"])


def test_probation_signature_cannot_be_changed_to_hidden_source(tmp_path):
    conn = _conn(tmp_path)
    project = _project(conn, user_id=803)
    admission = _probation_admission(project, snapshot_id="r18s8-tamper")
    admission["submit_source"] = "debug"

    result = _confirm(conn, project, admission)

    assert result["ok"] is False
    assert result["reason"] == "admission_context_missing_or_invalid"
    assert conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0] == 0


def test_probation_failure_is_terminal_no_charge_and_starts_cooldown(tmp_path):
    conn = _conn(tmp_path)
    project = _project(conn, user_id=804)
    created = _confirm(conn, project, _probation_admission(project, snapshot_id="r18s8-fail"))
    job_id = int(created["job"]["id"])

    failed = queue.fail_video_job(conn, job_id=job_id, error="provider_no_output", retry=True)
    payload = json.loads(failed["job"]["result_json"])
    lock = queue.product_video_probation_lock_state(conn)

    assert failed["status"] == "failed"
    assert payload["probation_result"] == "failed"
    assert payload["continue_polling"] is False
    assert payload["charged_xu"] == 0
    assert payload["provider_health_promotion_eligible"] is False
    assert lock["probation_active"] is False
    assert lock["probation_cooldown_active"] is True
    assert lock["probation_lock_clear"] is False


def test_probation_health_promotion_metadata_appears_only_after_delivery(tmp_path):
    conn = _conn(tmp_path)
    project = _project(conn, user_id=805)
    created = _confirm(conn, project, _probation_admission(project, snapshot_id="r18s8-success"))
    job_id = int(created["job"]["id"])
    before = json.loads(created["job"]["result_json"])

    assert before["probation_result"] == "pending"
    assert before.get("provider_health_promotion_eligible") is not True
    scene_tasks = [
        {
            **item,
            "result_url": f"https://fixture.invalid/scene-{item['scene_index']}.mp4",
            "clip_valid": True,
        }
        for item in before["scene_tasks"]
    ]
    before.update(
        {
            "scene_tasks": scene_tasks,
            "artifact_valid": True,
            "final_mp4_valid": True,
            "output_bytes": 2048,
            "scene_coverage_expected": 2,
            "scene_coverage_count": 2,
            "scene_clip_coverage_complete": True,
        }
    )
    conn.execute(
        "UPDATE video_jobs SET status='completed',result_json=?,progress_percent=95 WHERE id=?",
        (json.dumps(before), job_id),
    )
    conn.commit()
    waiting_delivery = queue.product_video_probation_lock_state(conn)
    assert waiting_delivery["probation_active"] is True
    assert waiting_delivery["probation_lock_clear"] is False

    delivered = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="telegram-video-r18s8",
    )
    after = json.loads(delivered["job"]["result_json"])

    assert after["probation_result"] == "success"
    assert after["provider_health_promotion_eligible"] is True
    assert after["final_delivered"] is True
    assert after["charged_xu"] == 0
    assert queue.product_video_probation_lock_state(conn)["probation_lock_clear"] is True


def test_probation_delivery_marker_without_valid_final_mp4_does_not_promote_health(tmp_path):
    conn = _conn(tmp_path)
    project = _project(conn, user_id=806)
    created = _confirm(conn, project, _probation_admission(project, snapshot_id="r18s8-invalid-delivery"))
    job_id = int(created["job"]["id"])

    delivered = queue.note_video_delivery_result(
        conn,
        job_id=job_id,
        sent=True,
        delivery_message_id="invalid-fixture-marker",
    )
    payload = json.loads(delivered["job"]["result_json"])

    assert delivered["ok"] is False
    assert delivered["sent"] is False
    assert delivered["reason"] == "probation_final_delivery_requirements_missing"
    assert payload["probation_result"] == "pending"
    assert payload["provider_health_promotion_eligible"] is False
    assert payload["charged_xu"] == 0
    assert delivered["project"].get("video_delivered_at") in (None, "")
    assert queue.product_video_probation_lock_state(conn)["probation_active"] is True


def _heartbeat_record(now: datetime) -> dict:
    capability = queue.PRODUCT_VIDEO_CANONICAL_WORKER_CAPABILITY
    return {
        "worker_id": "owner-product-video",
        "worker_instance_id": "owner-product-video:instance",
        "generation_id": "generation-r18s8",
        "git_sha": RUNTIME_SHA,
        "runtime_target_sha": RUNTIME_SHA,
        "service_mode": "owner_product_video",
        "capability_version": capability,
        "capabilities": ["owner_product_video", capability],
        "heartbeat_at": queue.now_text(now - timedelta(seconds=20)),
        "lease_expires_at": queue.now_text(now + timedelta(seconds=70)),
        "heartbeat_refresh_source": "claim_idle",
    }


def test_idle_claim_heartbeat_lease_and_generation_flow_is_preserved():
    now = datetime(2030, 1, 2, 3, 4, 5)
    capability = queue.PRODUCT_VIDEO_CANONICAL_WORKER_CAPABILITY
    decision = remote_worker_api.owner_product_video_heartbeat_update_decision(
        [_heartbeat_record(now)],
        {
            "worker_id": "owner-product-video",
            "worker_instance_id": "owner-product-video:instance",
            "generation_id": "generation-r18s8",
            "git_sha": RUNTIME_SHA,
            "runtime_target_sha": RUNTIME_SHA,
            "service_mode": "owner_product_video",
            "capability_version": capability,
            "capabilities": ["owner_product_video", capability],
        },
        runtime_sha=RUNTIME_SHA,
        now=now,
        heartbeat_ttl_seconds=90,
    )

    assert decision["heartbeat_accepted"] is True
    assert decision["authoritative_generation_id"] == "generation-r18s8"
    assert decision["lease_expires_at"] == queue.now_text(now + timedelta(seconds=90))


def test_public_preflight_panel_and_refresh_are_non_job_same_message_source_contracts():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    panel = source[
        source.index("def product_video_public_preflight_panel_text"):
        source.index("def product_video_bot_watchdog_eligibility")
    ]
    callback = source[
        source.index('if action == "b14_preflight_refresh":'):
        source.index('if action == "b14_scene_count":', source.index('if action == "b14_preflight_refresh":'))
    ]

    assert "🎬 <b>Trạng thái tạo video</b>" in panel
    assert "⚠️ <b>Chưa thể bắt đầu</b>" in panel
    assert "Hệ thống chưa trừ Xu" in panel
    assert 'callback_data="vproduct|b14_preflight_refresh"' in panel
    assert 'callback_data="vproduct|b14_confirm"' in panel
    assert "safe_edit_or_send" in panel
    for field in (
        "user_id",
        "project_draft_reference",
        "selected_scene_count",
        "preflight_message_id",
        "created_at",
        "expires_at",
    ):
        assert field in panel
    for forbidden in (
        "create_video_project",
        "confirm_video_project_invoice",
        "video_dispatch_outbox",
        "provider_submit",
        "spend_fixed_credit",
    ):
        assert forbidden not in callback


def test_blocked_preflight_returns_before_any_project_job_scene_or_outbox_insert():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    callback_scene = source[
        source.index('if action == "b14_scene_count":'):
        source.index('if action == "b14_confirm":')
    ]
    custom_scene = source[
        source.index('if str(session.get("current_step") or "") in {"b14_scene_custom", "waiting_scene_count"}:'):
        source.index("current_step = str(session.get(\"current_step\") or \"\")", source.index('if str(session.get("current_step") or "") in {"b14_scene_custom", "waiting_scene_count"}:'))
    ]
    panel_helpers = source[
        source.index("def product_video_public_preflight_evaluation"):
        source.index("def product_video_bot_watchdog_eligibility")
    ]

    callback_block = callback_scene.index("if not scene_preflight_ready:")
    callback_return = callback_scene.index("return await product_video_show_public_preflight_panel", callback_block)
    callback_prepare = callback_scene.index("video_b14_prepare_project_for_invoice", callback_return)
    assert callback_block < callback_return < callback_prepare

    custom_block = custom_scene.index("if not custom_preflight_ready:")
    custom_return = custom_scene.index("return True", custom_block)
    custom_prepare = custom_scene.index("video_b14_prepare_project_for_invoice", custom_return)
    assert custom_block < custom_return < custom_prepare

    for forbidden in (
        "create_video_project",
        "video_b14_prepare_project_for_invoice",
        "confirm_video_project_invoice",
        "create_video_job",
        "video_scenes",
        "video_dispatch_outbox",
        "provider_submit",
        "spend_fixed_credit",
    ):
        assert forbidden not in panel_helpers


def test_public_panel_hides_technical_terms_and_status_keeps_admin_diagnostics():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    text_helper = source[
        source.index("def product_video_public_preflight_panel_text"):
        source.index("def product_video_public_preflight_panel_keyboard")
    ].lower()

    for forbidden in ("provider", "worker", "heartbeat", "sha", "lease", "candidate", "probation"):
        assert forbidden not in text_helper
    for diagnostic in (
        "Product Video provider eligibility state",
        "Product Video healthy candidates",
        "Product Video probation candidates",
        "Product Video hard-blocked candidates",
        "Product Video probation active job",
        "Product Video probation lock",
        "Product Video probation last result",
        "Product Video final admission mode",
    ):
        assert diagnostic in source


def test_r18s7_signed_gate_b13_r18c_and_pr370_are_preserved_without_real_provider_calls():
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
    queue_source = (ROOT / "services" / "video_project_queue.py").read_text(encoding="utf-8")
    target_source = Path(__file__).read_text(encoding="utf-8")

    confirm = bot_source[
        bot_source.index('if action == "b14_confirm":'):
        bot_source.index('if action == "b14_job_status":')
    ]
    assert "build_product_video_public_final_admission" in confirm
    assert "require_provider_admission=True" in confirm
    assert "product_video_assert_final_admission" in queue_source
    assert queue.PRODUCT_VIDEO_CANONICAL_ENGINE_ENTRY == "b13_r18c"
    assert "def can_cleanup_workspace" in bot_source
    assert "def cleanup_subtitle_dub_pipeline_workspace_result" in bot_source
    for marker in ("requests" + ".post", "url" + "open", "submit" + "_video", "run_provider" + "_generation"):
        assert marker not in target_source
