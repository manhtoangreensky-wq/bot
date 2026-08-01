import asyncio
import importlib
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import local_worker
import remote_worker
from services import video_engine_contract
from services import video_project_queue as queue
from services import video_provider_router as provider_router
from services import remote_worker_api
from services import video_real_render_connector as real_connector


def _seam():
    try:
        return importlib.import_module("services.product_video_public_seam")
    except ModuleNotFoundError:
        pytest.fail("services.product_video_public_seam is not implemented")


def _conn(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "routeengine29n.db")
    conn.row_factory = sqlite3.Row
    queue.ensure_video_project_queue_schema(conn)
    return conn


def _project(
    conn: sqlite3.Connection,
    *,
    user_id: int = 2901,
    scene_count: int = 1,
    product_type: str = "video_ai_prompt",
) -> dict:
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
        "product_type": product_type,
        "engine_adapter": "text_to_video",
        "orchestration_mode": "per_scene_8s",
        "provider_orchestration_mode": "per_scene_8s",
        "provider_chain": ["shopaikey_video"],
        "provider_order": "shopaikey_video",
        "scene_count": scene_count,
    }
    invoice = {
        **shared,
        "tier": "basic",
        "package_xu": 300,
        "quality_tier": 300,
        "scene_duration_seconds": 8,
        "duration_seconds": scene_count * 8,
        "total_xu": 300,
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
        profile_id=product_type,
        topic=f"routeengine29n fixture {user_id}",
        ratio="9:16",
        asset_pack=shared,
    )
    cards = [
        {
            "scene_index": index,
            "provider_prompt": f"approved scene {index}",
            "negative_prompt": "identity drift",
        }
        for index in range(1, scene_count + 1)
    ]
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        status="draft_invoice",
        invoice_json=invoice,
        story_bible_json={"primary_profile": "product_showcase"},
        scene_cards_json=cards,
        scene_count=scene_count,
        prompt_text="approved Product Video prompt",
        quality_tier=300,
        total_xu_estimated=300,
    )
    return queue.get_video_project(conn, int(project["project_id"]))


def _admission(project: dict, *, snapshot_id: str = "routeengine29n-snapshot") -> dict:
    candidates = ["shopaikey_video"]
    checked_at = datetime.now()
    user_id = int(project["user_id"])
    project_id = int(project["project_id"])
    quote = queue.product_video_admission_quote_fingerprint(project, user_id)
    route = provider_router.product_video_route_contract(
        "video_ai_prompt",
        "text_to_video",
        "per_scene_8s",
    )
    snapshot = {
        "provider_eligibility_snapshot_id": snapshot_id,
        "admission_snapshot_id": snapshot_id,
        "admission_checked_at": queue.now_text(checked_at),
        "admission_user_id": user_id,
        "admission_project_id": project_id,
        "admission_quote_fingerprint": quote,
        "admission_callback_handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "admission_callback_data": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK,
        "eligible_provider_keys": candidates,
        "runtime_candidate_keys": candidates,
        "final_eligible_provider_count": 1,
    }
    admission = {
        "ok": True,
        "provider_eligibility_snapshot": snapshot,
        "provider_eligibility_snapshot_id": snapshot_id,
        "admission_snapshot_id": snapshot_id,
        "admission_checked_at": queue.now_text(checked_at),
        "admission_ttl_seconds": 60,
        "admission_candidate_keys": candidates,
        "admission_candidate_count": 1,
        "admission_result": "PASS",
        "admission_block_reason": "",
        "admission_user_id": user_id,
        "admission_project_id": project_id,
        "admission_quote_fingerprint": quote,
        "admission_callback_handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "admission_callback_data": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_CALLBACK,
        "admission_worker_runtime_sha": "29n-runtime",
        "admission_worker_sha": "29n-runtime",
        "admission_worker_version_compatible": True,
        "admission_route_requires_provider": bool(route["route_requires_provider"]),
        "admission_provider_health_gate_pass": True,
        "worker_generation_id": "routeengine29n-generation",
        "worker_git_sha": "29n-runtime",
        "runtime_sha": "29n-runtime",
        "worker_compatible": True,
        "worker_connected": True,
        "worker_heartbeat_fresh": True,
        "worker_lease_valid": True,
        "worker_sha_match": True,
        "worker_capability_match": True,
        "worker_identity_conflict": False,
        "route_requires_provider": bool(route["route_requires_provider"]),
        "handler_id": queue.PRODUCT_VIDEO_PUBLIC_CONFIRM_HANDLER_ID,
        "worker_admission_block_reason": "",
        "duplicate_confirm_handler_detected": False,
    }
    return queue.sign_product_video_final_admission_context(admission)


def _confirm(conn: sqlite3.Connection, project: dict, *, snapshot_id: str = "routeengine29n-snapshot") -> dict:
    return queue.confirm_public_product_video_invoice(
        conn,
        project_id=int(project["project_id"]),
        user_id=int(project["user_id"]),
        balance_xu=300,
        provider_admission=_admission(project, snapshot_id=snapshot_id),
    )


def _counts(conn: sqlite3.Connection) -> tuple[int, int, int]:
    return tuple(
        conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("video_jobs", "video_scenes", "video_dispatch_outbox")
    )


def _enabled_env(scene_count: int) -> dict[str, str]:
    values = {
        "PRODUCT_VIDEO_DURABLE_PUBLIC_SEAM_ENABLED": "1",
        "PRODUCT_VIDEO_ONE_SCENE_ENGINE_ENABLED": "0",
        "PRODUCT_VIDEO_ONE_SCENE_PUBLIC_ALLOWED": "0",
        "PRODUCT_VIDEO_ONE_SCENE_REAL_PROVIDER_ENABLED": "0",
        "PRODUCT_VIDEO_ONE_SCENE_AUTO_RETRY": "0",
        "PRODUCT_VIDEO_ONE_SCENE_AUTO_FALLBACK": "0",
        "PRODUCT_VIDEO_MULTISCENE_ENGINE_ENABLED": "0",
        "PRODUCT_VIDEO_MULTISCENE_PUBLIC_ALLOWED": "0",
        "PRODUCT_VIDEO_MULTISCENE_REAL_PROVIDER_ENABLED": "0",
        "PRODUCT_VIDEO_MULTISCENE_AUTO_RESUBMIT": "0",
        "PRODUCT_VIDEO_MULTISCENE_AUTO_FALLBACK": "0",
    }
    prefix = "PRODUCT_VIDEO_ONE_SCENE" if scene_count == 1 else "PRODUCT_VIDEO_MULTISCENE"
    values[f"{prefix}_ENGINE_ENABLED"] = "1"
    values[f"{prefix}_PUBLIC_ALLOWED"] = "1"
    values[f"{prefix}_REAL_PROVIDER_ENABLED"] = "1"
    return values


def _set_env(monkeypatch: pytest.MonkeyPatch, values: dict[str, str]) -> None:
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_default_off_preserves_legacy_public_confirm(tmp_path):
    seam = _seam()
    conn = _conn(tmp_path)
    project = _project(conn, scene_count=2)

    state = seam.evaluate_product_video_public_seam(project, environ={})
    result = _confirm(conn, project)

    assert state == {
        "enabled": False,
        "ready": True,
        "legacy_passthrough": True,
        "blocker": "",
        "route_decision": None,
    }
    assert result["ok"] is True
    payload = json.loads(result["job"]["result_json"])
    assert payload["canonical_engine_entry"] == "b13_r18c"
    assert "product_video_route_decision" not in payload
    assert _counts(conn) == (1, 2, 1)


@pytest.mark.parametrize(
    ("scene_count", "mode", "route_id", "engine_adapter"),
    [
        (1, "single_scene", "product_video_one_scene_v1", "b13_r18c_product_one_scene_v1"),
        (3, "multi_scene", "product_video_multiscene_v1", "b13_r18c_product_multiscene_v1"),
    ],
)
def test_enabled_seam_selects_exact_durable_product_route(
    tmp_path,
    scene_count,
    mode,
    route_id,
    engine_adapter,
):
    seam = _seam()
    conn = _conn(tmp_path)
    project = _project(conn, scene_count=scene_count)
    selection = video_engine_contract.durable_video_product_route_selection(project)

    state = seam.evaluate_product_video_public_seam(
        project,
        environ=_enabled_env(scene_count),
    )

    assert state["enabled"] is True
    assert state["ready"] is True
    assert state["blocker"] == ""
    decision = state["route_decision"]
    assert decision["engine_product"] == "product_video"
    assert decision["mode"] == mode
    assert decision["scene_count"] == scene_count
    assert decision["selection_sha256"] == selection["route_selection_sha256"]
    assert decision["route_id"] == route_id
    assert decision["engine_adapter"] == engine_adapter
    assert decision["worker_job_type"] == "video_render"
    assert decision["worker_owner"] == "owner_product_video"
    assert decision["required_capability"] == "canonical_multiscene_b13_r18c_v1"
    assert decision["automatic_retry_allowed"] is False
    assert decision["automatic_resubmit_allowed"] is False
    assert decision["automatic_fallback_allowed"] is False


@pytest.mark.parametrize(
    "product_type",
    ["frame_video", "self_shot_scene_change", "self_shot_cinematic_transform"],
)
def test_enabled_seam_passes_through_non_product_durable_selection(
    tmp_path,
    product_type,
):
    seam = _seam()
    conn = _conn(tmp_path)
    project = _project(conn, scene_count=2, product_type=product_type)

    state = seam.evaluate_product_video_public_seam(project, environ=_enabled_env(2))

    assert state["enabled"] is False
    assert state["ready"] is True
    assert state["legacy_passthrough"] is True
    assert state["blocker"] == ""
    assert state["route_decision"] is None


def test_worker_executor_routes_explicit_non_product_job_to_legacy_when_enabled():
    seam = _seam()
    calls = []

    result = seam.execute_product_video_worker_route(
        {
            "job_type": "video_render",
            "product_video_public_seam_applicable": False,
        },
        environ=_enabled_env(1),
        one_scene_executor=lambda _prepared: calls.append("one"),
        multiscene_executor=lambda _prepared: calls.append("multi"),
        legacy_executor=lambda prepared: calls.append(
            ("legacy", prepared["product_video_public_seam_applicable"])
        )
        or "legacy-result",
    )

    assert result == "legacy-result"
    assert calls == [("legacy", False)]


@pytest.mark.parametrize(
    ("overrides", "blocker"),
    [
        ({"PRODUCT_VIDEO_ONE_SCENE_ENGINE_ENABLED": "0"}, "product_video_one_scene_engine_disabled"),
        ({"PRODUCT_VIDEO_ONE_SCENE_PUBLIC_ALLOWED": "0"}, "product_video_one_scene_public_disabled"),
        ({"PRODUCT_VIDEO_ONE_SCENE_REAL_PROVIDER_ENABLED": "0"}, "product_video_one_scene_real_provider_disabled"),
        ({"PRODUCT_VIDEO_ONE_SCENE_AUTO_RETRY": "1"}, "product_video_one_scene_automatic_retry_forbidden"),
        ({"PRODUCT_VIDEO_ONE_SCENE_AUTO_FALLBACK": "1"}, "product_video_one_scene_automatic_fallback_forbidden"),
    ],
)
def test_enabled_seam_requires_public_provider_readiness(tmp_path, overrides, blocker):
    seam = _seam()
    conn = _conn(tmp_path)
    project = _project(conn)
    environ = {**_enabled_env(1), **overrides}

    state = seam.evaluate_product_video_public_seam(project, environ=environ)

    assert state["ready"] is False
    assert state["blocker"] == blocker
    assert state["route_decision"] is None


def test_atomic_confirm_blocks_before_any_insert_when_seam_not_ready(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    project = _project(conn)
    original_asset = project["asset_pack_json"]
    original_invoice = project["invoice_json"]
    _set_env(
        monkeypatch,
        {
            **_enabled_env(1),
            "PRODUCT_VIDEO_ONE_SCENE_REAL_PROVIDER_ENABLED": "0",
        },
    )

    result = _confirm(conn, project)

    assert result["ok"] is False
    assert result["reason"] == "product_video_one_scene_real_provider_disabled"
    assert result["charge"] == 0
    assert result["charged_xu"] == 0
    assert _counts(conn) == (0, 0, 0)
    persisted = queue.get_video_project(conn, int(project["project_id"]))
    assert persisted["status"] == "draft_invoice"
    assert persisted["asset_pack_json"] == original_asset
    assert persisted["invoice_json"] == original_invoice


def test_atomic_confirm_uses_locked_story_snapshot_not_stale_caller_copy(
    tmp_path,
    monkeypatch,
):
    conn = _conn(tmp_path)
    stale_project = _project(conn)
    admission = _admission(stale_project)
    _set_env(monkeypatch, _enabled_env(1))
    conn.execute(
        "UPDATE video_projects SET story_bible_json=? WHERE project_id=?",
        (
            json.dumps({"primary_profile": "character_animation_vfx"}),
            int(stale_project["project_id"]),
        ),
    )
    conn.commit()

    result = queue._confirm_product_video_invoice_atomic(
        conn,
        project=stale_project,
        user_id=int(stale_project["user_id"]),
        admission=admission,
        require_provider_admission=True,
        require_authoritative_snapshot=True,
    )

    assert result["ok"] is True
    assert "product_video_route_decision" not in json.loads(
        result["job"]["result_json"]
    )
    assert _counts(conn) == (1, 1, 1)
    hydrated = queue.hydrate_video_job_payload(conn, result["job"])
    local_payload = local_worker.prepare_product_video_public_seam_job(
        hydrated,
        environ=_enabled_env(1),
    )
    remote_payload = remote_worker_api.build_worker_job_payload(hydrated)
    prepared_remote = remote_worker.prepare_product_video_public_seam_job(
        remote_payload,
        environ=_enabled_env(1),
    )
    assert local_payload.get("product_video_route_decision") is None
    assert remote_payload["product_video_public_seam_applicable"] is False
    assert prepared_remote.get("product_video_route_decision") is None


@pytest.mark.parametrize("scene_count", [1, 3])
def test_atomic_confirm_persists_identical_route_decision_everywhere(
    tmp_path,
    monkeypatch,
    scene_count,
):
    seam = _seam()
    conn = _conn(tmp_path)
    project = _project(conn, scene_count=scene_count)
    _set_env(monkeypatch, _enabled_env(scene_count))

    result = _confirm(conn, project)

    assert result["ok"] is True
    payload = json.loads(result["job"]["result_json"])
    persisted = result["project"]
    asset = json.loads(persisted["asset_pack_json"])
    invoice = json.loads(persisted["invoice_json"])
    decision = payload["product_video_route_decision"]
    assert decision == asset["product_video_route_decision"]
    assert decision == invoice["product_video_route_decision"]
    assert payload["product_video_route_decision_sha256"] == decision["route_decision_sha256"]
    assert asset["product_video_route_decision_sha256"] == decision["route_decision_sha256"]
    assert invoice["product_video_route_decision_sha256"] == decision["route_decision_sha256"]
    assert payload["engine_adapter"] == queue.product_video_engine_contract(
        "video_ai_prompt"
    )["engine_adapter"]
    assert payload["product_video_engine_adapter"] == decision["engine_adapter"]
    assert payload["product_video_engine_mode"] == decision["mode"]
    assert payload["required_capability"] == queue.product_video_engine_contract(
        "video_ai_prompt"
    )["required_capability"]
    assert payload["required_worker_capability"] == decision["required_capability"]
    assert payload["scene_count"] == scene_count
    assert seam.validate_persisted_product_video_route_decision(
        payload,
        environ=_enabled_env(scene_count),
    )["ready"] is True
    hydrated = queue.hydrate_video_job_payload(conn, result["job"])
    worker_payload = remote_worker_api.build_worker_job_payload(hydrated)
    assert worker_payload["product_video_route_decision"] == decision
    assert worker_payload["product_video_route_decision_sha256"] == decision["route_decision_sha256"]
    assert worker_payload["engine_adapter"] == queue.product_video_engine_contract(
        "video_ai_prompt"
    )["engine_adapter"]
    assert worker_payload["product_video_engine_adapter"] == decision["engine_adapter"]
    assert worker_payload["required_capability"] == queue.product_video_engine_contract(
        "video_ai_prompt"
    )["required_capability"]
    assert worker_payload["required_worker_capability"] == decision["required_capability"]
    assert seam.validate_persisted_product_video_route_decision(
        worker_payload,
        environ=_enabled_env(scene_count),
    )["ready"] is True
    assert _counts(conn) == (1, scene_count, 1)


def test_duplicate_confirm_never_creates_a_second_job(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    project = _project(conn, scene_count=2)
    _set_env(monkeypatch, _enabled_env(2))

    first = _confirm(conn, project)
    second = _confirm(
        conn,
        queue.get_video_project(conn, int(project["project_id"])),
        snapshot_id="routeengine29n-second-snapshot",
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["duplicate_prevented"] is True
    assert _counts(conn) == (1, 2, 1)


def test_duplicate_confirm_cannot_replace_an_active_route_decision(
    tmp_path,
    monkeypatch,
):
    conn = _conn(tmp_path)
    project = _project(conn)
    _set_env(monkeypatch, _enabled_env(1))
    first = _confirm(conn, project)
    first_payload = json.loads(first["job"]["result_json"])
    first_hash = first_payload["product_video_route_decision_sha256"]
    queue.update_video_project(
        conn,
        int(project["project_id"]),
        story_bible_json={"primary_profile": "product_advertorial"},
    )
    changed = queue.get_video_project(conn, int(project["project_id"]))

    second = _confirm(
        conn,
        changed,
        snapshot_id="routeengine29n-conflicting-snapshot",
    )

    assert second["ok"] is False
    assert second["reason"] == "product_video_route_decision_conflict"
    assert _counts(conn) == (1, 1, 1)
    persisted_job = queue.get_video_render_job(conn, int(first["job"]["id"]))
    persisted_payload = json.loads(persisted_job["result_json"])
    assert persisted_payload["product_video_route_decision_sha256"] == first_hash


def test_persisted_decision_validates_without_keyword_or_project_reselection(tmp_path):
    seam = _seam()
    conn = _conn(tmp_path)
    project = _project(conn)
    state = seam.evaluate_product_video_public_seam(project, environ=_enabled_env(1))
    payload = {
        **seam.product_video_route_decision_payload(state["route_decision"]),
        "scene_count": 1,
        "prompt": "podcast summary animated frame editing keywords must not reroute",
        "project": {"product_type": "summary_video", "scene_count": 1},
    }

    validation = seam.validate_persisted_product_video_route_decision(
        payload,
        environ=_enabled_env(1),
    )

    assert validation["ready"] is True
    assert validation["decision"]["engine_product"] == "product_video"
    assert validation["decision"]["engine_adapter"] == "b13_r18c_product_one_scene_v1"


def test_persisted_marker_forces_validation_when_worker_seam_flag_is_missing(tmp_path):
    seam = _seam()
    conn = _conn(tmp_path)
    project = _project(conn)
    state = seam.evaluate_product_video_public_seam(project, environ=_enabled_env(1))
    payload = {
        "job_type": "video_render",
        "scene_count": 1,
        **seam.product_video_route_decision_payload(state["route_decision"]),
    }
    worker_env = _enabled_env(1)
    worker_env.pop("PRODUCT_VIDEO_DURABLE_PUBLIC_SEAM_ENABLED")

    valid = seam.validate_persisted_product_video_route_decision(
        payload,
        environ=worker_env,
    )
    tampered = json.loads(json.dumps(payload))
    tampered["product_video_route_decision"]["route_id"] = "tampered"
    invalid = seam.validate_persisted_product_video_route_decision(
        tampered,
        environ=worker_env,
    )

    assert valid["ready"] is True
    assert valid["legacy_passthrough"] is False
    assert invalid["ready"] is False
    assert invalid["blocker"] == "product_video_route_decision_hash_mismatch"


def test_malformed_worker_scene_count_fails_with_stable_blocker(tmp_path):
    seam = _seam()
    conn = _conn(tmp_path)
    project = _project(conn)
    state = seam.evaluate_product_video_public_seam(project, environ=_enabled_env(1))
    payload = {
        "job_id": "29n-malformed-count",
        "job_type": "video_render",
        "source": "product_video",
        **seam.product_video_route_decision_payload(state["route_decision"]),
        "scene_count": "not-an-integer",
    }

    with pytest.raises(RuntimeError, match="product_video_route_decision_scene_count_mismatch"):
        remote_worker.prepare_product_video_public_seam_job(
            payload,
            environ=_enabled_env(1),
        )


@pytest.mark.parametrize("worker_module", [remote_worker, local_worker])
def test_worker_guard_rejects_missing_and_tampered_decision_before_execution(
    tmp_path,
    worker_module,
):
    seam = _seam()
    conn = _conn(tmp_path)
    project = _project(conn)
    state = seam.evaluate_product_video_public_seam(project, environ=_enabled_env(1))
    valid = {
        "job_id": "29n-worker",
        "job_type": "video_render",
        "source": "product_video",
        "product_video": True,
        "scene_count": 1,
        **seam.product_video_route_decision_payload(state["route_decision"]),
    }

    with pytest.raises(RuntimeError, match="product_video_route_decision_missing"):
        worker_module.prepare_product_video_public_seam_job(
            {
                "job_id": "missing",
                "job_type": "video_render",
                "scene_count": 1,
            },
            environ=_enabled_env(1),
        )

    tampered = json.loads(json.dumps(valid))
    tampered["product_video_route_decision"]["engine_adapter"] = "tampered_adapter"
    with pytest.raises(RuntimeError, match="product_video_route_decision_hash_mismatch"):
        worker_module.prepare_product_video_public_seam_job(
            tampered,
            environ=_enabled_env(1),
        )

    wrong_job_type = json.loads(json.dumps(valid))
    wrong_job_type["job_type"] = "frame_video_render"
    with pytest.raises(RuntimeError, match="product_video_route_decision_worker_job_type_mismatch"):
        worker_module.prepare_product_video_public_seam_job(
            wrong_job_type,
            environ=_enabled_env(1),
        )

    normalized = worker_module.prepare_product_video_public_seam_job(
        valid,
        environ=_enabled_env(1),
    )
    assert normalized["scene_count"] == 1
    assert normalized["engine_adapter"] == "b13_r18c_product_one_scene_v1"
    assert normalized["product_video_engine_adapter"] == "b13_r18c_product_one_scene_v1"
    assert normalized["product_video_engine_mode"] == "single_scene"


def test_remote_worker_missing_decision_blocks_before_render_or_delivery(monkeypatch):
    calls = {"heartbeat": 0, "render": 0, "complete": 0}
    _set_env(monkeypatch, _enabled_env(1))
    monkeypatch.setattr(remote_worker, "send_heartbeat", lambda *_args, **_kwargs: calls.__setitem__("heartbeat", calls["heartbeat"] + 1))
    monkeypatch.setattr(remote_worker, "render_real_video", lambda *_args, **_kwargs: calls.__setitem__("render", calls["render"] + 1))
    monkeypatch.setattr(remote_worker, "complete_job", lambda *_args, **_kwargs: calls.__setitem__("complete", calls["complete"] + 1))

    with pytest.raises(RuntimeError, match="product_video_route_decision_missing"):
        remote_worker.process_claimed_job(
            {
                "job_id": "29n-remote-missing",
                "job_type": "video_render",
                "source": "product_video",
                "product_video": True,
                "scene_count": 1,
            }
        )

    assert calls == {"heartbeat": 0, "render": 0, "complete": 0}


def test_local_worker_missing_decision_blocks_before_render_or_delivery(monkeypatch):
    updates = []
    calls = {"render": 0, "delivery": 0}
    _set_env(monkeypatch, _enabled_env(1))
    monkeypatch.setattr(local_worker, "update_video_render_job", lambda *args, **kwargs: updates.append((args, kwargs)))
    monkeypatch.setattr(local_worker, "video_project_real_scene_renderer", lambda *_args, **_kwargs: calls.__setitem__("render", calls["render"] + 1))
    monkeypatch.setattr(local_worker, "telegram_send_video_receipt", lambda *_args, **_kwargs: calls.__setitem__("delivery", calls["delivery"] + 1))

    local_worker.run_video_render_job(
        {
            "id": 2902,
            "job_id": 2902,
            "job_type": "video_render",
            "source": "product_video",
            "product_video": True,
            "scene_count": 1,
            "project": {"user_id": 2902, "scene_count": 1},
        }
    )

    assert calls == {"render": 0, "delivery": 0}
    assert updates
    assert "product_video_route_decision_missing" in str(updates[0])


def test_local_poll_hydration_promotes_persisted_route_decision(
    tmp_path,
    monkeypatch,
):
    conn = _conn(tmp_path)
    project = _project(conn)
    _set_env(monkeypatch, _enabled_env(1))
    confirmed = _confirm(conn, project)
    persisted = json.loads(confirmed["job"]["result_json"])

    hydrated = queue.hydrate_video_job_payload(conn, confirmed["job"])

    assert hydrated["product_video_durable_public_seam"] is True
    assert hydrated["product_video_route_decision"] == persisted[
        "product_video_route_decision"
    ]
    assert hydrated["product_video_route_decision_sha256"] == persisted[
        "product_video_route_decision_sha256"
    ]
    worker_env = _enabled_env(1)
    worker_env.pop("PRODUCT_VIDEO_DURABLE_PUBLIC_SEAM_ENABLED")
    prepared = local_worker.prepare_product_video_public_seam_job(
        hydrated,
        environ=worker_env,
    )
    assert prepared["engine_adapter"] == "b13_r18c_product_one_scene_v1"


@pytest.mark.parametrize(
    ("scene_count", "expected_mode", "expected_adapter"),
    [
        (1, "single_scene", "b13_r18c_product_one_scene_v1"),
        (3, "multi_scene", "b13_r18c_product_multiscene_v1"),
    ],
)
def test_persisted_route_selects_exact_worker_executor(
    tmp_path,
    scene_count,
    expected_mode,
    expected_adapter,
):
    seam = _seam()
    conn = _conn(tmp_path)
    project = _project(conn, scene_count=scene_count)
    state = seam.evaluate_product_video_public_seam(
        project,
        environ=_enabled_env(scene_count),
    )
    job = {
        "job_type": "video_render",
        "orchestration_mode": (
            "per_scene_8s" if scene_count == 1 else "single_task_legacy"
        ),
        "provider_orchestration_mode": (
            "per_scene_8s" if scene_count == 1 else "single_task_legacy"
        ),
        **seam.product_video_route_decision_payload(state["route_decision"]),
    }
    calls = []

    result = seam.execute_product_video_worker_route(
        job,
        environ=_enabled_env(scene_count),
        one_scene_executor=lambda prepared: calls.append(
            (
                "one",
                prepared["engine_adapter"],
                prepared["orchestration_mode"],
                prepared["provider_orchestration_mode"],
            )
        )
        or "one-result",
        multiscene_executor=lambda prepared: calls.append(
            (
                "multi",
                prepared["engine_adapter"],
                prepared["orchestration_mode"],
                prepared["provider_orchestration_mode"],
            )
        )
        or "multi-result",
    )

    expected_lane = "one" if scene_count == 1 else "multi"
    expected_orchestration = (
        "single_task_legacy" if scene_count == 1 else "per_scene_8s"
    )
    assert calls == [
        (
            expected_lane,
            expected_adapter,
            expected_orchestration,
            expected_orchestration,
        )
    ]
    assert result == f"{expected_lane}-result"
    assert state["route_decision"]["mode"] == expected_mode


def test_local_worker_builds_renderer_from_forced_persisted_orchestration(
    tmp_path,
    monkeypatch,
):
    seam = _seam()
    state = seam.evaluate_product_video_public_seam(
        _project(_conn(tmp_path), scene_count=2),
        environ=_enabled_env(2),
    )
    job = {
        "id": 2910,
        "job_id": 2910,
        "job_type": "video_render",
        "source": "product_video",
        "product_video": True,
        "scene_count": 2,
        "orchestration_mode": "single_task_legacy",
        "provider_orchestration_mode": "single_task_legacy",
        "render_mode": local_worker.RENDER_MODE_REAL,
        "project": {"user_id": 2910, "scene_count": 2, "ratio": "9:16"},
        **seam.product_video_route_decision_payload(state["route_decision"]),
    }
    renderer_inputs = []
    updates = []
    final_path = tmp_path / "final.mp4"

    def fake_renderer(prepared):
        renderer_inputs.append(
            (
                prepared.get("orchestration_mode"),
                prepared.get("provider_orchestration_mode"),
                prepared.get("product_video_runtime_lane"),
            )
        )
        return object()

    _set_env(monkeypatch, _enabled_env(2))
    monkeypatch.setattr(local_worker, "TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(local_worker, "video_project_real_scene_renderer", fake_renderer)
    monkeypatch.setattr(local_worker, "create_multiscene_workspace", lambda *_args: str(tmp_path))
    monkeypatch.setattr(local_worker, "product_video_logo_material", lambda *_args: {})
    monkeypatch.setattr(local_worker, "real_video_llm_func_from_job", lambda *_args: None)
    monkeypatch.setattr(
        local_worker,
        "process_multiscene_video_pipeline",
        lambda **_kwargs: {"ok": True, "final_video_path": str(final_path)},
    )
    monkeypatch.setattr(
        local_worker,
        "telegram_send_video_receipt",
        lambda *_args, **_kwargs: {
            "sent": True,
            "message_id": "2910-message",
            "file_id": "2910-file",
        },
    )
    monkeypatch.setattr(
        local_worker,
        "update_video_render_job",
        lambda *args, **kwargs: updates.append((args, kwargs)),
    )

    local_worker.run_video_render_job(job)

    assert renderer_inputs == [("per_scene_8s", "per_scene_8s", "multi_scene")]
    assert updates[-1][0][1] == "completed"


def test_persisted_route_disables_retry_and_stale_requeue(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    project = _project(conn)
    _set_env(monkeypatch, _enabled_env(1))
    confirmed = _confirm(conn, project)
    started_at = datetime(2026, 8, 1, 1, 0, 0)

    assert confirmed["job"]["max_attempts"] == 1
    claimed = queue.claim_next_video_job(
        conn,
        worker_id="routeengine29n-worker",
        lease_seconds=30,
        now=started_at,
    )
    assert claimed["attempts"] == 1
    assert queue.requeue_stale_video_jobs(
        conn,
        now=started_at + timedelta(minutes=2),
    ) == 0
    assert queue.get_video_render_job(conn, int(claimed["id"]))["status"] == "processing"

    failed = queue.fail_video_job(
        conn,
        job_id=int(claimed["id"]),
        error="routeengine29n-test-failure",
        retry=True,
    )
    assert failed["status"] == "failed"


def test_remote_failure_cannot_override_persisted_no_retry(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    project = _project(conn)
    _set_env(monkeypatch, _enabled_env(1))
    confirmed = _confirm(conn, project)
    claimed = queue.claim_next_video_job(
        conn,
        worker_id="routeengine29n-remote",
    )

    result = remote_worker_api.fail_remote_worker_job(
        conn,
        worker_id="routeengine29n-remote",
        job_id=int(confirmed["job"]["id"]),
        safe_error="worker_failed_after_submit",
        retryable=True,
    )

    assert claimed["id"] == confirmed["job"]["id"]
    assert result["status"] == "failed"
    assert result["job"]["status"] == "failed"


def test_watchdog_cannot_recover_persisted_no_retry_job(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    project = _project(conn)
    _set_env(monkeypatch, _enabled_env(1))
    confirmed = _confirm(conn, project)
    job_id = int(confirmed["job"]["id"])
    payload = json.loads(confirmed["job"]["result_json"])
    reason = "dispatch_not_started_dispatch_outbox_job_not_claimable"
    payload.update(
        {
            "worker_compatible": True,
            "public_user_confirmed": True,
            "invoice_confirmed": True,
            "submit_source": "public_user_final_confirm",
            "provider_submit_called": False,
            "provider_http_request_sent": False,
            "provider_task_ids": [],
            "provider_video_ids": [],
        }
    )
    conn.execute(
        "UPDATE video_jobs SET status='failed',last_error=?,result_json=? WHERE id=?",
        (reason, json.dumps(payload), job_id),
    )
    conn.execute(
        "UPDATE video_projects SET status='failed' WHERE project_id=?",
        (int(project["project_id"]),),
    )
    conn.execute(
        """UPDATE video_dispatch_outbox
              SET dispatch_status='terminal_failed',last_error=?,terminal_reason=?
            WHERE job_id=?""",
        (reason, reason, job_id),
    )
    conn.commit()

    recovery = queue.recover_product_video_premature_dispatch_failure(
        conn,
        job_id=job_id,
        worker_compatible=True,
    )
    watchdog = queue.sweep_product_video_zero_task_watchdog(
        conn,
        job_id=job_id,
    )

    assert recovery["premature_dispatch_recovered"] is False
    assert recovery["premature_dispatch_recovery_block_reason"] == (
        "automatic_retry_forbidden"
    )
    assert watchdog["recovered"] == 0
    assert queue.get_video_render_job(conn, job_id)["status"] == "failed"
    outbox = queue.get_product_video_dispatch_outbox(conn, job_id=job_id)
    assert outbox["dispatch_status"] == "terminal_failed"


def test_persisted_route_forbids_scene_fallback_and_provider_chain_fallback(
    tmp_path,
    monkeypatch,
):
    seam = _seam()
    conn = _conn(tmp_path)
    project = _project(conn)
    state = seam.evaluate_product_video_public_seam(
        project,
        environ=_enabled_env(1),
    )
    job = {
        "id": 2903,
        "job_id": 2903,
        "job_type": "video_render",
        "source": "product_video",
        "product_video": True,
        "product_type": "video_ai_prompt",
        "provider_order": ["shopaikey_video", "key4u_video"],
        "selected_provider": "shopaikey_video",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        **seam.product_video_route_decision_payload(state["route_decision"]),
    }
    stalled_scene = {
        "scene_index": 1,
        "provider": "shopaikey_video",
        "provider_task_id": "provider-task-1",
        "provider_status": "NOT_START",
        "provider_started_at_epoch": 1,
    }

    policy = real_connector.product_video_scene_stall_policy(job, stalled_scene, 1)

    assert policy["provider_scene_stalled"] is True
    assert policy["fallback_allowed"] is False
    assert policy["fallback_block_reason"] == "automatic_fallback_forbidden"

    captured = {}

    def fake_provider_generation(_request, *, output_dir, environ, **_kwargs):
        captured["provider_chain"] = environ.get("VIDEO_PROVIDER_CHAIN")
        output = Path(output_dir) / "scene-1.mp4"
        output.write_bytes(b"routeengine29n-provider-fixture")
        return {
            "ok": True,
            "output_path": str(output),
            "provider": "shopaikey_video",
        }

    monkeypatch.setattr(real_connector, "run_provider_generation", fake_provider_generation)
    raw_path = tmp_path / "rendered-scene.mp4"
    scene = SimpleNamespace(
        scene_id=1,
        video_prompt="approved Product Video prompt",
        visual_prompt="approved Product Video prompt",
        aspect_ratio="9:16",
        target_duration_sec=8,
        _toan_aas_job=job,
    )

    rendered = asyncio.run(
        real_connector._render_scene_async(
            scene,
            str(raw_path),
            ["shopaikey_video", "key4u_video"],
        )
    )

    assert rendered["ok"] is True
    assert captured["provider_chain"] == "shopaikey_video"


def test_persisted_route_blocks_missing_dispatch_resubmit_before_provider_call(
    tmp_path,
    monkeypatch,
):
    seam = _seam()
    conn = _conn(tmp_path)
    project = _project(conn)
    state = seam.evaluate_product_video_public_seam(
        project,
        environ=_enabled_env(1),
    )
    job = {
        "id": 2904,
        "job_id": 2904,
        "job_type": "video_render",
        "source": "product_video",
        "product_video": True,
        "product_type": "video_ai_prompt",
        "provider_order": ["shopaikey_video"],
        "selected_provider": "shopaikey_video",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "scene_tasks": [
            {
                "scene_index": 1,
                "status": "dispatch_missing",
                "scene_dispatch_attempted": True,
            }
        ],
        **seam.product_video_route_decision_payload(state["route_decision"]),
    }
    scene = SimpleNamespace(
        scene_id=1,
        video_prompt="approved Product Video prompt",
        visual_prompt="approved Product Video prompt",
        aspect_ratio="9:16",
        target_duration_sec=8,
        _toan_aas_job=job,
    )
    provider_calls = []
    monkeypatch.setattr(
        real_connector,
        "run_provider_generation",
        lambda *_args, **_kwargs: provider_calls.append(True),
    )

    with pytest.raises(
        real_connector.RealVideoRenderError,
        match="product_video_automatic_resubmit_forbidden",
    ):
        asyncio.run(
            real_connector._render_scene_async(
                scene,
                str(tmp_path / "must-not-render.mp4"),
                ["shopaikey_video"],
            )
        )

    assert provider_calls == []


def test_initial_placeholder_scene_is_not_misclassified_as_resubmit(
    tmp_path,
    monkeypatch,
):
    seam = _seam()
    conn = _conn(tmp_path)
    project = _project(conn, scene_count=2)
    state = seam.evaluate_product_video_public_seam(
        project,
        environ=_enabled_env(2),
    )
    job = {
        "id": 2905,
        "job_id": 2905,
        "job_type": "video_render",
        "source": "product_video",
        "product_video": True,
        "product_type": "video_ai_prompt",
        "provider_order": ["shopaikey_video"],
        "selected_provider": "shopaikey_video",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "scene_tasks": [
            {
                "scene_index": 1,
                "status": "queued_waiting_for_dispatch",
                "current_scene_status": "queued_waiting_for_dispatch",
            },
            {
                "scene_index": 2,
                "status": "queued_waiting_for_dispatch",
                "current_scene_status": "queued_waiting_for_dispatch",
            },
        ],
        **seam.product_video_route_decision_payload(state["route_decision"]),
    }
    scene = SimpleNamespace(
        scene_id=1,
        video_prompt="approved Product Video scene one",
        visual_prompt="approved Product Video scene one",
        aspect_ratio="9:16",
        target_duration_sec=8,
        _toan_aas_job=job,
    )
    provider_calls = []

    def fake_provider_generation(_request, *, output_dir, **_kwargs):
        provider_calls.append(True)
        output = Path(output_dir) / "initial-scene.mp4"
        output.write_bytes(b"routeengine29n-initial-scene")
        return {"ok": True, "output_path": str(output)}

    monkeypatch.setattr(
        real_connector,
        "run_provider_generation",
        fake_provider_generation,
    )

    result = asyncio.run(
        real_connector._render_scene_async(
            scene,
            str(tmp_path / "scene-one.mp4"),
            ["shopaikey_video"],
        )
    )

    assert result["ok"] is True
    assert provider_calls == [True]


def test_initial_scene_two_dispatch_ignores_scene_one_dispatch_evidence(
    tmp_path,
    monkeypatch,
):
    seam = _seam()
    conn = _conn(tmp_path)
    project = _project(conn, scene_count=2)
    state = seam.evaluate_product_video_public_seam(
        project,
        environ=_enabled_env(2),
    )
    job = {
        "id": 2911,
        "job_id": 2911,
        "job_type": "video_render",
        "source": "product_video",
        "product_video": True,
        "product_type": "video_ai_prompt",
        "provider_order": ["shopaikey_video"],
        "selected_provider": "shopaikey_video",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "scene_tasks": [
            {
                "scene_index": 1,
                "status": "processing",
                "provider_task_id": "scene-one-provider-task",
                "scene_dispatch_attempted": True,
            },
            {
                "scene_index": 2,
                "status": "queued_waiting_for_dispatch",
                "current_scene_status": "queued_waiting_for_dispatch",
            },
        ],
        **seam.product_video_route_decision_payload(state["route_decision"]),
    }
    scene = SimpleNamespace(
        scene_id=2,
        video_prompt="approved Product Video scene two",
        visual_prompt="approved Product Video scene two",
        aspect_ratio="9:16",
        target_duration_sec=8,
        _toan_aas_job=job,
    )
    provider_calls = []

    def fake_provider_generation(_request, *, output_dir, **_kwargs):
        provider_calls.append(True)
        output = Path(output_dir) / "initial-scene-two.mp4"
        output.write_bytes(b"routeengine29n-initial-scene-two")
        return {"ok": True, "output_path": str(output)}

    monkeypatch.setattr(
        real_connector,
        "run_provider_generation",
        fake_provider_generation,
    )

    result = asyncio.run(
        real_connector._render_scene_async(
            scene,
            str(tmp_path / "scene-two.mp4"),
            ["shopaikey_video"],
        )
    )

    assert result["ok"] is True
    assert result["missing_scene_dispatch_recovered"] is False
    assert provider_calls == [True]


@pytest.mark.parametrize(
    ("malformed_decision", "persisted_marker"),
    [
        (None, True),
        ("not-a-mapping", True),
        ("not-a-mapping", False),
    ],
)
def test_remote_payload_preserves_marker_when_decision_is_missing_or_malformed(
    tmp_path,
    monkeypatch,
    malformed_decision,
    persisted_marker,
):
    conn = _conn(tmp_path)
    project = _project(conn)
    _set_env(monkeypatch, _enabled_env(1))
    confirmed = _confirm(conn, project)
    job_id = int(confirmed["job"]["id"])
    payload = json.loads(confirmed["job"]["result_json"])
    if malformed_decision is None:
        payload.pop("product_video_route_decision", None)
    else:
        payload["product_video_route_decision"] = malformed_decision
    payload["product_video_durable_public_seam"] = persisted_marker
    conn.execute(
        "UPDATE video_jobs SET result_json=? WHERE id=?",
        (json.dumps(payload), job_id),
    )
    conn.commit()
    job = queue.get_video_render_job(conn, job_id)

    remote_payload = remote_worker_api.build_worker_job_payload(
        queue.hydrate_video_job_payload(conn, job)
    )

    assert remote_payload["product_video_durable_public_seam"] is True
    worker_env = _enabled_env(1)
    worker_env.pop("PRODUCT_VIDEO_DURABLE_PUBLIC_SEAM_ENABLED")
    with pytest.raises(RuntimeError, match="product_video_route_decision_missing"):
        remote_worker.prepare_product_video_public_seam_job(
            remote_payload,
            environ=worker_env,
        )


def _stub_final_output_validation(monkeypatch):
    monkeypatch.setattr(
        queue,
        "product_video_scene_coverage_state",
        lambda *_args, **_kwargs: {
            "delivery_blocked_by_scene_coverage": False,
            "scene_clip_coverage_complete": True,
            "scene_coverage_expected": 1,
            "scene_coverage_count": 1,
        },
    )
    monkeypatch.setattr(
        queue.video_final_output,
        "validate_final_video_output",
        lambda **_kwargs: {
            "ok": True,
            "bytes": 1024,
            "duration": 8.0,
            "has_video": True,
            "has_audio": False,
        },
    )
    monkeypatch.setattr(
        queue,
        "product_video_duration_contract",
        lambda *_args, **_kwargs: {
            "ok": True,
            "reason": "",
            "expected_duration_seconds": 8.0,
            "actual_duration_seconds": 8.0,
        },
    )


def test_completion_and_delivery_preserve_route_decision_hash(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    project = _project(conn)
    _set_env(monkeypatch, _enabled_env(1))
    confirmed = _confirm(conn, project)
    before = json.loads(confirmed["job"]["result_json"])
    _stub_final_output_validation(monkeypatch)

    completed = queue.complete_video_job(
        conn,
        job_id=int(confirmed["job"]["id"]),
        final_video_path=str(tmp_path / "final.mp4"),
        result={"ok": True, "renderer": "routeengine29n-fixture"},
    )
    completed_payload = json.loads(completed["job"]["result_json"])
    delivered = queue.note_video_delivery_result(
        conn,
        job_id=int(confirmed["job"]["id"]),
        sent=True,
        delivery_message_id="29n-message",
    )
    delivered_payload = json.loads(delivered["job"]["result_json"])

    assert completed_payload["product_video_route_decision"] == before[
        "product_video_route_decision"
    ]
    assert completed_payload["product_video_route_decision_sha256"] == before[
        "product_video_route_decision_sha256"
    ]
    assert delivered["ok"] is True
    assert delivered_payload["product_video_route_decision_sha256"] == before[
        "product_video_route_decision_sha256"
    ]


def test_delivery_rejects_tampered_route_decision_before_mutation(
    tmp_path,
    monkeypatch,
):
    conn = _conn(tmp_path)
    project = _project(conn)
    _set_env(monkeypatch, _enabled_env(1))
    confirmed = _confirm(conn, project)
    _stub_final_output_validation(monkeypatch)
    completed = queue.complete_video_job(
        conn,
        job_id=int(confirmed["job"]["id"]),
        final_video_path=str(tmp_path / "final.mp4"),
        result={"ok": True},
    )
    tampered = json.loads(completed["job"]["result_json"])
    tampered["product_video_route_decision"]["route_id"] = "tampered-route"
    conn.execute(
        "UPDATE video_jobs SET result_json=? WHERE id=?",
        (json.dumps(tampered), int(confirmed["job"]["id"])),
    )
    conn.commit()

    result = queue.note_video_delivery_result(
        conn,
        job_id=int(confirmed["job"]["id"]),
        sent=True,
        delivery_message_id="must-not-be-recorded",
    )

    assert result["ok"] is False
    assert result["reason"] == "product_video_route_decision_hash_mismatch"
    persisted_project = queue.get_video_project(conn, int(project["project_id"]))
    assert not persisted_project.get("video_delivered_at")
    assert not persisted_project.get("video_delivery_message_id")


def test_completion_does_not_resurrect_stale_failure_telemetry(
    tmp_path,
    monkeypatch,
):
    conn = _conn(tmp_path)
    project = _project(conn)
    _set_env(monkeypatch, _enabled_env(1))
    confirmed = _confirm(conn, project)
    stale = json.loads(confirmed["job"]["result_json"])
    stale.update(
        {
            "continue_polling": True,
            "blocker": "stale_provider_failure",
            "provider_error": "stale_provider_failure",
        }
    )
    conn.execute(
        "UPDATE video_jobs SET result_json=? WHERE id=?",
        (json.dumps(stale), int(confirmed["job"]["id"])),
    )
    conn.commit()
    _stub_final_output_validation(monkeypatch)

    completed = queue.complete_video_job(
        conn,
        job_id=int(confirmed["job"]["id"]),
        final_video_path=str(tmp_path / "final.mp4"),
        result={"ok": True},
    )
    payload = json.loads(completed["job"]["result_json"])

    assert payload.get("continue_polling") is not True
    assert payload.get("blocker") != "stale_provider_failure"
    assert payload.get("provider_error") != "stale_provider_failure"
    assert payload["product_video_route_decision_sha256"] == stale[
        "product_video_route_decision_sha256"
    ]
