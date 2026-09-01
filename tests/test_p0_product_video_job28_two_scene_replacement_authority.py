from __future__ import annotations

import copy
import asyncio
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from providers.video_generic_http_provider import GenericHttpVideoProvider
from services import (
    remote_worker_api,
    video_provider_router,
    video_real_render_connector as connector,
    video_project_queue,
)


AUTHORIZATION_ID = "pv2-r01-job28-key4u-replacements-v2"
LEGACY_RECEIPT = {
    "scene_index": 1,
    "provider": "key4u_video",
    "submit_source": "worker_poll_existing_task",
    "idempotency_key": "legacy-job28-scene1-key4u-once",
    "submit_called": True,
    "provider_http_request_sent": False,
    "http_status": 0,
    "submit_accepted": False,
    "task_id_present": False,
    "provider_task_id": "",
    "fallback_count_before_submit": 0,
    "fallback_count_after_submit": 1,
    "authorization_state": "consumed",
    "submit_evidence_state": "ambiguous_submit_called_without_transport_receipt",
    "blocker": "all_video_providers_submit_failed",
    "recorded_at": "2026-09-01 02:27:07",
}


def _authorization() -> dict:
    return {
        "authorization_id": AUTHORIZATION_ID,
        "authorization_version": 2,
        "state": "active",
        "provider": "key4u_video",
        "job_id": 28,
        "project_id": 32,
        "outbox_id": 27,
        "request_id": "VID-20260829-D78AA3",
        "allowed_scene_indexes": [1, 2],
        "per_scene_call_cap": 1,
        "global_call_cap": 2,
        "consumed_scene_indexes": [],
        "calls_consumed": 0,
        "user_visible_price_xu": 144,
        "persisted_quoted_price_xu": 144,
        "customer_charge_planned_xu": 144,
        "provider_budget_xu": 212,
        "fallback_provider_cost_xu": 212,
        "owner_charged_xu": 0,
    }


def _scene(scene_index: int, *, fallback_count: int) -> dict:
    return {
        "scene_index": scene_index,
        "provider": "shopaikey_video",
        "provider_task_id": f"old-shopaikey-scene-{scene_index}",
        "provider_video_id": f"old-shopaikey-scene-{scene_index}",
        "active_task_id": f"old-shopaikey-scene-{scene_index}",
        "status": "provider_not_start",
        "actual_provider_payload_status": "NOT_START",
        "provider_status_raw": "NOT_START",
        "provider_stalled_not_start": True,
        "provider_scene_stalled": True,
        "scene_not_start_elapsed": 900,
        "provider_wait_elapsed_seconds": 900,
        "provider_progress_normalized": 0,
        "submit_accepted": True,
        "task_pollable": True,
        "fallback_count": fallback_count,
        "provider_fallback_count": fallback_count,
        "fallback_count_before_submit": fallback_count,
        "fallback_allowed": False,
        "controlled_fallback_allowed": False,
        "fallback_provider_candidate": "",
        "fallback_provider_order": [],
    }


def _job28_payload() -> dict:
    scenes = [_scene(1, fallback_count=1), _scene(2, fallback_count=0)]
    return {
        "id": 28,
        "job_id": 28,
        "project_id": 32,
        "outbox_id": 27,
        "request_id": "VID-20260829-D78AA3",
        "source": "product_video",
        "product_video": True,
        "recovery_existing_tasks_only": True,
        "original_submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "provider_submit_accepted_before": True,
        "automatic_fallback_allowed": False,
        "automatic_resubmit_allowed": False,
        "automatic_retry_allowed": False,
        "user_visible_price_xu": 144,
        "persisted_quoted_price_xu": 144,
        "customer_charge_planned_xu": 144,
        "provider_budget_xu": 212,
        "fallback_provider_cost_xu": 212,
        "quote_consistent": True,
        "charged_xu": 0,
        "charge": 0,
        "wallet_charge_recorded": False,
        "delivered": False,
        "configured_provider_chain": ["shopaikey_video", "key4u_video"],
        "provider_order": ["shopaikey_video", "key4u_video"],
        "provider_stalled_not_start": True,
        "scene_not_start_elapsed": 900,
        "fallback_scene_index": 1,
        "fallback_count": 1,
        "fallback_count_before_submit": 1,
        "fallback_count_by_scene": {"1": 1, "2": 0},
        "controlled_fallback_submit_receipts_by_scene": {
            "1": copy.deepcopy(LEGACY_RECEIPT)
        },
        "controlled_fallback_authorization_state": "consumed",
        "controlled_fallback_retry_blocked": True,
        "controlled_fallback_replacement_authorization": _authorization(),
        "scene_tasks": scenes,
        "provider_scene_tasks": copy.deepcopy(scenes),
    }


def _replacement_context(payload: dict, scene_index: int) -> dict:
    assert hasattr(
        video_provider_router,
        "product_video_controlled_replacement_authorization_context",
    ), "replacement authorization parser is missing"
    return video_provider_router.product_video_controlled_replacement_authorization_context(
        payload,
        scene_index=scene_index,
    )


def _replacement_submit_diagnostics(
    payload: dict,
    *,
    scene_index: int,
    task_id: str,
) -> dict:
    current = copy.deepcopy(payload)
    current.update(
        {
            "fallback_scene_index": scene_index,
            "fallback_idempotency_key": (
                f"{AUTHORIZATION_ID}-scene-{scene_index}-key4u"
            ),
            "fallback_submit_attempted": True,
            "submit_source": "public_confirmed_scene_fallback_once",
            "provider_submit_source": "public_confirmed_scene_fallback_once",
            "fallback_submit_source": "public_confirmed_scene_fallback_once",
            "provider_submit_called": True,
            "provider_http_request_sent": bool(task_id),
            "provider_submit_http_status": 200 if task_id else 0,
            "submit_accepted": bool(task_id),
            "provider_task_id_saved": bool(task_id),
            "provider_task_ids": [task_id] if task_id else [],
            "provider_video_ids": [task_id] if task_id else [],
            "provider_error": (
                "provider_in_progress"
                if task_id
                else "all_video_providers_submit_failed"
            ),
            "blocker": (
                "provider_in_progress"
                if task_id
                else "all_video_providers_submit_failed"
            ),
            "provider_attempts": [
                {
                    "provider": "key4u_video",
                    "phase": "submit",
                    "submit_called": True,
                    "provider_http_request_sent": bool(task_id),
                    "provider_http_status": 200 if task_id else 0,
                    "submit_http_status": 200 if task_id else 0,
                    "submit_accepted": bool(task_id),
                    "task_id_present": bool(task_id),
                    "task_pollable": bool(task_id),
                    "provider_task_id": task_id,
                    "blocker": "" if task_id else "all_video_providers_submit_failed",
                }
            ],
        }
    )
    current["scene_tasks"] = [
        {
            **item,
            **(
                {
                    "provider": "key4u_video",
                    "selected_provider": "key4u_video",
                    "provider_task_id": task_id,
                    "provider_video_id": task_id,
                    "active_task_id": task_id,
                    "status": "provider_running" if task_id else "failed",
                    "actual_provider_payload_status": "queued" if task_id else "",
                    "fallback_submit_attempted": True,
                    "submit_accepted": bool(task_id),
                    "task_pollable": bool(task_id),
                    "failure_reason": "" if task_id else "all_video_providers_submit_failed",
                }
                if int(item.get("scene_index") or 0) == scene_index
                else {}
            ),
        }
        for item in current["scene_tasks"]
    ]
    current["provider_scene_tasks"] = copy.deepcopy(current["scene_tasks"])
    return current


def test_replacement_authorization_ignores_legacy_receipt_but_enforces_scene_and_finance_scope() -> None:
    payload = _job28_payload()

    scene_one = _replacement_context(payload, 1)
    scene_two = _replacement_context(payload, 2)
    scene_three = _replacement_context(payload, 3)

    assert scene_one["valid"] is True
    assert scene_one["authorization_id"] == AUTHORIZATION_ID
    assert scene_one["authorization_version"] == 2
    assert scene_one["allowed_scene_indexes"] == [1, 2]
    assert scene_one["consumed_scene_indexes"] == []
    assert scene_one["calls_consumed"] == 0
    assert scene_one["calls_remaining"] == 2
    assert scene_one["scene_authorized"] is True
    assert scene_two["scene_authorized"] is True
    assert scene_three["scene_authorized"] is False
    assert scene_three["block_reason"] == "replacement_scene_not_authorized"
    assert payload["controlled_fallback_submit_receipts_by_scene"]["1"] == LEGACY_RECEIPT

    price_mismatch = copy.deepcopy(payload)
    price_mismatch["customer_charge_planned_xu"] = 145
    mismatch = _replacement_context(price_mismatch, 1)
    assert mismatch["valid"] is False
    assert mismatch["block_reason"] == "replacement_finance_scope_mismatch"

    wrong_job = copy.deepcopy(payload)
    wrong_job["job_id"] = 29
    identity_mismatch = _replacement_context(wrong_job, 1)
    assert identity_mismatch["valid"] is False
    assert (
        identity_mismatch["block_reason"]
        == "replacement_identity_scope_mismatch"
    )

    inconsistent_counter = copy.deepcopy(payload)
    inconsistent_counter["controlled_fallback_replacement_authorization"][
        "calls_consumed"
    ] = 1
    inconsistent = _replacement_context(inconsistent_counter, 1)
    assert inconsistent["valid"] is False
    assert inconsistent["block_reason"] == "replacement_authorization_invalid"


def test_replacement_policy_allows_each_scene_once_and_never_exceeds_two_calls() -> None:
    payload = _job28_payload()
    payload["scene_index"] = 1

    first = video_provider_router.product_video_controlled_fallback_policy(
        "provider_timeout",
        payload,
    )
    assert first["fallback_submit_allowed"] is True
    assert first["replacement_authorization_id"] == AUTHORIZATION_ID

    payload["controlled_fallback_replacement_submit_receipts_by_authorization"] = {
        AUTHORIZATION_ID: {
            "1": {
                "authorization_id": AUTHORIZATION_ID,
                "scene_index": 1,
                "authorization_state": "consumed",
                "task_id_present": True,
                "provider_task_id": "key4u-replacement-scene-1",
            }
        }
    }
    payload["controlled_fallback_replacement_authorization"].update(
        {
            "consumed_scene_indexes": [1],
            "calls_consumed": 1,
        }
    )
    payload["fallback_scene_index"] = 1
    scene_one_again = video_provider_router.product_video_controlled_fallback_policy(
        "provider_timeout",
        payload,
    )
    assert scene_one_again["fallback_submit_allowed"] is False
    assert (
        scene_one_again["fallback_block_reason"]
        == "replacement_scene_call_cap_reached"
    )

    for item in payload["scene_tasks"]:
        if int(item.get("scene_index") or 0) == 1:
            item.update(
                {
                    "status": "completed",
                    "actual_provider_payload_status": "SUCCESS",
                    "clip_valid": True,
                    "result_url_valid": True,
                    "artifact_bytes": 1024,
                }
            )
    payload["provider_scene_tasks"] = copy.deepcopy(payload["scene_tasks"])
    payload["fallback_scene_index"] = 2
    scene_two = video_provider_router.product_video_controlled_fallback_policy(
        "provider_timeout",
        payload,
    )
    assert scene_two["fallback_submit_allowed"] is True

    payload[
        "controlled_fallback_replacement_submit_receipts_by_authorization"
    ][AUTHORIZATION_ID]["2"] = {
        "authorization_id": AUTHORIZATION_ID,
        "scene_index": 2,
        "authorization_state": "consumed",
        "task_id_present": False,
    }
    payload["controlled_fallback_replacement_authorization"].update(
        {
            "consumed_scene_indexes": [1, 2],
            "calls_consumed": 2,
        }
    )
    capped = _replacement_context(payload, 2)
    assert capped["calls_consumed"] == 2
    assert capped["calls_remaining"] == 0
    assert capped["scene_authorized"] is False
    assert capped["block_reason"] == "replacement_global_call_cap_reached"


def test_claim_selects_only_next_authorized_scene_and_keeps_accepted_task_poll_only() -> None:
    payload = _job28_payload()
    eligibility = {
        "worker_local_ready_provider_keys": ["key4u_video"],
        "contract_valid_provider_chain": ["shopaikey_video", "key4u_video"],
    }

    first = remote_worker_api.product_video_controlled_fallback_claim_payload(
        {"id": 28, "project_id": 32},
        payload,
        {"project_id": 32},
        eligibility,
    )
    assert first["applied"] is True
    assert first["eligible_scene_indexes"] == [1]
    assert first["result"]["fallback_scene_index"] == 1
    assert first["result"]["replacement_authorization_id"] == AUTHORIZATION_ID
    assert [
        bool(item.get("controlled_fallback_allowed"))
        for item in first["result"]["scene_tasks"]
    ] == [True, False]

    pending = _replacement_submit_diagnostics(
        payload,
        scene_index=1,
        task_id="key4u-replacement-scene-1",
    )
    pending, _ = remote_worker_api._controlled_fallback_submit_receipt(pending)
    pending_claim = remote_worker_api.product_video_controlled_fallback_claim_payload(
        {"id": 28, "project_id": 32},
        pending,
        {"project_id": 32},
        eligibility,
    )
    assert pending_claim["applied"] is False
    assert pending_claim["poll_only_scene_indexes"] == [1]
    assert pending_claim["eligible_scene_indexes"] == []

    completed = copy.deepcopy(pending)
    for item in completed["scene_tasks"]:
        if int(item.get("scene_index") or 0) == 1:
            item.update(
                {
                    "status": "completed",
                    "actual_provider_payload_status": "SUCCESS",
                    "clip_valid": True,
                    "result_url_valid": True,
                    "artifact_bytes": 1024,
                }
            )
    completed["provider_scene_tasks"] = copy.deepcopy(completed["scene_tasks"])
    completed["provider_stalled_not_start"] = True
    next_claim = remote_worker_api.product_video_controlled_fallback_claim_payload(
        {"id": 28, "project_id": 32},
        completed,
        {"project_id": 32},
        eligibility,
    )
    assert next_claim["applied"] is True
    assert next_claim["eligible_scene_indexes"] == [2]
    assert next_claim["result"]["fallback_scene_index"] == 2
    assert [
        bool(item.get("controlled_fallback_allowed"))
        for item in next_claim["result"]["scene_tasks"]
    ] == [False, True]


def test_replacement_receipts_archive_legacy_and_are_immutable_per_authorization() -> None:
    payload = _job28_payload()
    scene_one_submit = _replacement_submit_diagnostics(
        payload,
        scene_index=1,
        task_id="key4u-replacement-scene-1",
    )

    first, first_state = remote_worker_api._controlled_fallback_submit_receipt(
        scene_one_submit
    )
    legacy = first["controlled_fallback_submit_receipts_by_scene"]["1"]
    active_receipt = first[
        "controlled_fallback_replacement_submit_receipts_by_authorization"
    ][AUTHORIZATION_ID]["1"]

    assert legacy == LEGACY_RECEIPT
    assert first["controlled_fallback_submit_receipt_history"] == [
        {**LEGACY_RECEIPT, "archived_authorization_id": "legacy-scene-1-v1"}
    ]
    assert active_receipt["authorization_id"] == AUTHORIZATION_ID
    assert active_receipt["authorization_version"] == 2
    assert active_receipt["scene_index"] == 1
    assert active_receipt["task_id_present"] is True
    assert active_receipt["provider_task_id"] == "key4u-replacement-scene-1"
    assert first_state["replacement_authorization_id"] == AUTHORIZATION_ID
    assert first_state["replacement_scene_index"] == 1
    assert first["controlled_fallback_replacement_authorization"][
        "consumed_scene_indexes"
    ] == [1]
    assert first["controlled_fallback_replacement_authorization"][
        "calls_consumed"
    ] == 1
    assert first["controlled_fallback_replacement_authorization"]["state"] == "active"
    assert first["fallback_count_by_scene"] == {"1": 2, "2": 0}
    assert first["charged_xu"] == 0

    later_primary_poll = copy.deepcopy(first)
    later_primary_poll.update(
        {
            "fallback_scene_index": 0,
            "fallback_submit_attempted": False,
            "provider_submit_called": False,
            "provider_attempts": [],
            "submit_source": "worker_poll_existing_task",
            "provider_submit_source": "worker_poll_existing_task",
        }
    )
    stabilized, _ = remote_worker_api._controlled_fallback_submit_receipt(
        later_primary_poll
    )
    assert stabilized[
        "controlled_fallback_replacement_submit_receipts_by_authorization"
    ][AUTHORIZATION_ID]["1"] == active_receipt
    assert stabilized["controlled_fallback_submit_receipts_by_scene"]["1"] == LEGACY_RECEIPT

    for item in stabilized["scene_tasks"]:
        if int(item.get("scene_index") or 0) == 1:
            item.update(
                {
                    "status": "completed",
                    "actual_provider_payload_status": "SUCCESS",
                    "clip_valid": True,
                    "result_url_valid": True,
                    "artifact_bytes": 1024,
                }
            )
    stabilized["provider_scene_tasks"] = copy.deepcopy(stabilized["scene_tasks"])
    scene_two_submit = _replacement_submit_diagnostics(
        stabilized,
        scene_index=2,
        task_id="key4u-replacement-scene-2",
    )
    second, _ = remote_worker_api._controlled_fallback_submit_receipt(
        scene_two_submit
    )
    active_receipts = second[
        "controlled_fallback_replacement_submit_receipts_by_authorization"
    ][AUTHORIZATION_ID]
    assert sorted(active_receipts) == ["1", "2"]
    assert active_receipts["1"] == active_receipt
    assert active_receipts["2"]["provider_task_id"] == "key4u-replacement-scene-2"
    assert second["controlled_fallback_replacement_authorization"][
        "consumed_scene_indexes"
    ] == [1, 2]
    assert second["controlled_fallback_replacement_authorization"][
        "calls_consumed"
    ] == 2
    assert second["controlled_fallback_replacement_authorization"]["state"] == "consumed"
    assert second["fallback_count_by_scene"] == {"1": 2, "2": 1}
    assert second["charged_xu"] == 0

    replayed, _ = remote_worker_api._controlled_fallback_submit_receipt(
        copy.deepcopy(second)
    )
    assert replayed[
        "controlled_fallback_replacement_submit_receipts_by_authorization"
    ] == second["controlled_fallback_replacement_submit_receipts_by_authorization"]
    assert replayed["controlled_fallback_submit_receipt_history"] == second[
        "controlled_fallback_submit_receipt_history"
    ]


def test_failed_replacement_without_task_consumes_scene_slot_and_fails_no_charge() -> None:
    payload = _job28_payload()
    failed_submit = _replacement_submit_diagnostics(
        payload,
        scene_index=2,
        task_id="",
    )

    normalized, state = remote_worker_api._controlled_fallback_submit_receipt(
        failed_submit
    )
    receipt = normalized[
        "controlled_fallback_replacement_submit_receipts_by_authorization"
    ][AUTHORIZATION_ID]["2"]

    assert state["failed_without_task"] is True
    assert receipt["authorization_state"] == "consumed"
    assert receipt["task_id_present"] is False
    assert normalized["controlled_fallback_replacement_authorization"][
        "consumed_scene_indexes"
    ] == [2]
    assert normalized["terminal_state"] == "failed_no_charge"
    assert normalized["continue_polling"] is False
    assert normalized["charged_xu"] == 0
    assert normalized["wallet_charge_recorded"] is False


def test_terminal_accepted_task_blocks_all_remaining_calls_and_fails_no_charge() -> None:
    payload = _job28_payload()
    scene_one_submit = _replacement_submit_diagnostics(
        payload,
        scene_index=1,
        task_id="key4u-replacement-scene-1",
    )
    persisted, _ = remote_worker_api._controlled_fallback_submit_receipt(
        scene_one_submit
    )
    for item in persisted["scene_tasks"]:
        if int(item.get("scene_index") or 0) == 1:
            item.update(
                {
                    "status": "failed",
                    "actual_provider_payload_status": "FAILURE",
                    "failure_reason": "provider_failed",
                    "clip_valid": False,
                    "result_url_valid": False,
                    "artifact_bytes": 0,
                }
            )
    persisted["provider_scene_tasks"] = copy.deepcopy(persisted["scene_tasks"])

    scene_one = _replacement_context(persisted, 1)
    scene_two = _replacement_context(persisted, 2)

    assert scene_one["pending_poll_scene_indexes"] == []
    assert scene_one["terminal_failed_scene_indexes"] == [1]
    assert scene_one["scene_authorized"] is False
    assert scene_one["block_reason"] == "replacement_scene_call_cap_reached"
    assert scene_two["scene_authorized"] is False
    assert (
        scene_two["block_reason"]
        == "replacement_consumed_task_terminal_failed"
    )

    normalized, state = remote_worker_api._controlled_fallback_submit_receipt(
        persisted
    )
    assert state["task_terminal_failed"] is True
    assert normalized["terminal_state"] == "failed_no_charge"
    assert normalized["continue_polling"] is False
    assert normalized["charged_xu"] == 0


def test_completed_scene_result_unlocks_next_scene_in_same_worker_tick(tmp_path) -> None:
    payload = _job28_payload()
    scene_one_submit = _replacement_submit_diagnostics(
        payload,
        scene_index=1,
        task_id="key4u-replacement-scene-1",
    )
    persisted, _ = remote_worker_api._controlled_fallback_submit_receipt(
        scene_one_submit
    )
    output = tmp_path / "scene-1.mp4"
    output.write_bytes(b"scene-one-real-provider-clip")

    connector._record_replacement_scene_result_for_next_scene(
        persisted,
        1,
        {
            "ok": True,
            "provider": "key4u_video",
            "provider_task_ids": ["key4u-replacement-scene-1"],
            "output_path": str(output),
        },
    )
    context = _replacement_context(persisted, 2)

    assert context["pending_poll_scene_indexes"] == []
    assert context["scene_authorized"] is True
    assert persisted["scene_tasks"][0]["clip_valid"] is True
    assert persisted["scene_tasks"][0]["artifact_bytes"] == output.stat().st_size
    assert persisted["fallback_scene_index"] == 2
    assert [
        bool(item.get("controlled_fallback_allowed"))
        for item in persisted["scene_tasks"]
    ] == [False, True]


def test_non_key4u_result_cannot_consume_replacement_authority(tmp_path) -> None:
    payload = _job28_payload()
    output = tmp_path / "unauthorized-primary.mp4"
    output.write_bytes(b"shopaikey-old-task-result")

    connector._record_replacement_scene_result_for_next_scene(
        payload,
        1,
        {
            "ok": True,
            "provider": "shopaikey_video",
            "provider_task_ids": ["old-shopaikey-scene-1"],
            "output_path": str(output),
        },
    )

    assert payload["controlled_fallback_replacement_authorization"][
        "calls_consumed"
    ] == 0
    assert payload.get(
        "controlled_fallback_replacement_submit_receipts_by_authorization"
    ) in (None, {})
    assert payload["fallback_count_by_scene"] == {"1": 1, "2": 0}


def test_persisted_authority_and_receipt_win_over_conflicting_worker_payload() -> None:
    persisted = _job28_payload()
    persisted[
        "controlled_fallback_replacement_submit_receipts_by_authorization"
    ] = {
        AUTHORIZATION_ID: {
            "1": {
                "authorization_id": AUTHORIZATION_ID,
                "authorization_version": 2,
                "authorization_state": "consumed",
                "scene_index": 1,
                "provider": "key4u_video",
                "provider_task_id": "persisted-key4u-task",
                "task_id_present": True,
            }
        }
    }
    incoming = copy.deepcopy(persisted)
    incoming["controlled_fallback_replacement_authorization"][
        "authorization_id"
    ] = "worker-conflicting-authorization"
    incoming[
        "controlled_fallback_replacement_submit_receipts_by_authorization"
    ] = {
        "worker-conflicting-authorization": {
            "1": {
                "authorization_id": "worker-conflicting-authorization",
                "authorization_version": 99,
                "authorization_state": "consumed",
                "scene_index": 1,
                "provider": "key4u_video",
                "provider_task_id": "worker-overwrite-task",
                "task_id_present": True,
            }
        }
    }

    merged = remote_worker_api._merge_controlled_fallback_durable_internal_fields(
        persisted,
        incoming,
    )

    assert merged["controlled_fallback_replacement_authorization"][
        "authorization_id"
    ] == AUTHORIZATION_ID
    assert list(
        merged[
            "controlled_fallback_replacement_submit_receipts_by_authorization"
        ]
    ) == [AUTHORIZATION_ID]
    assert merged[
        "controlled_fallback_replacement_submit_receipts_by_authorization"
    ][AUTHORIZATION_ID]["1"]["provider_task_id"] == "persisted-key4u-task"


def test_real_replacement_dispatch_uses_only_key4u_and_preserves_exact_scope(
    monkeypatch,
    tmp_path,
) -> None:
    payload = _job28_payload()
    eligibility = {
        "worker_local_ready_provider_keys": ["key4u_video"],
        "contract_valid_provider_chain": ["shopaikey_video", "key4u_video"],
    }
    claimed = remote_worker_api.product_video_controlled_fallback_claim_payload(
        {"id": 28, "project_id": 32},
        payload,
        {"project_id": 32},
        eligibility,
    )["result"]
    captured: dict = {}

    def fake_provider_generation(request, *, output_dir, environ, **_kwargs):
        captured["provider_chain"] = environ.get("VIDEO_PROVIDER_CHAIN")
        captured["submit_source"] = request.metadata.get("submit_source")
        captured["authorization"] = request.metadata.get(
            "controlled_fallback_replacement_authorization"
        )
        captured["authorization_id"] = request.metadata.get(
            "replacement_authorization_id"
        )
        captured["scope"] = [
            request.metadata.get("controlled_fallback_replacement_job_id"),
            request.metadata.get("controlled_fallback_replacement_project_id"),
            request.metadata.get("controlled_fallback_replacement_outbox_id"),
            request.metadata.get("controlled_fallback_replacement_request_id"),
        ]
        captured["finance"] = [
            request.metadata.get("user_visible_price_xu"),
            request.metadata.get("persisted_quoted_price_xu"),
            request.metadata.get("customer_charge_planned_xu"),
            request.metadata.get("provider_budget_xu"),
            request.metadata.get("fallback_provider_cost_xu"),
        ]
        output = tmp_path / "key4u-replacement-scene-1.mp4"
        output.write_bytes(b"key4u-replacement-scene-1")
        return {
            "ok": True,
            "output_path": str(output),
            "provider": "key4u_video",
            "provider_task_ids": ["key4u-replacement-scene-1"],
            "provider_video_ids": ["key4u-replacement-scene-1"],
        }

    monkeypatch.setattr(connector, "run_provider_generation", fake_provider_generation)
    scene = SimpleNamespace(
        scene_id=1,
        video_prompt="replacement scene one",
        visual_prompt="replacement scene one",
        aspect_ratio="9:16",
        target_duration_sec=8,
        _toan_aas_job=claimed,
    )

    result = asyncio.run(
        connector._render_scene_async(
            scene,
            str(tmp_path / "rendered-scene-1.mp4"),
            ["shopaikey_video", "key4u_video"],
        )
    )

    assert result["ok"] is True
    assert captured["provider_chain"] == "key4u_video"
    assert captured["submit_source"] == "public_confirmed_scene_fallback_once"
    assert captured["authorization"]["authorization_id"] == AUTHORIZATION_ID
    assert captured["authorization_id"] == AUTHORIZATION_ID
    assert captured["scope"] == [28, 32, 27, "VID-20260829-D78AA3"]
    assert captured["finance"] == [144, 144, 144, 212, 212]
    assert result["provider"] == "key4u_video"


def test_worker_payload_preserves_versioned_replacement_authority() -> None:
    payload = _job28_payload()
    eligibility = {
        "worker_local_ready_provider_keys": ["key4u_video"],
        "contract_valid_provider_chain": ["shopaikey_video", "key4u_video"],
    }
    payload = remote_worker_api.product_video_controlled_fallback_claim_payload(
        {"id": 28, "project_id": 32},
        payload,
        {"project_id": 32},
        eligibility,
    )["result"]
    hydrated = {
        "id": 28,
        "job_id": 28,
        "project_id": 32,
        "user_id": 7126457028,
        "job_type": "video_render",
        "status": "processing",
        "attempts": 40,
        "max_attempts": 3,
        "result_json": json.dumps(payload),
        "project": {
            "project_id": 32,
            "job_id": 28,
            "user_id": 7126457028,
            "profile_id": "video_trend",
            "topic": "PV2-R01",
            "ratio": "9:16",
            "quality_tier": 400,
            "scene_count": 2,
            "total_xu_estimated": 144,
            "is_confirmed": 1,
            "asset_pack_json": json.dumps(
                {
                    "source": "product_video",
                    "product_type": "video_trend",
                    "render_mode": "real",
                    "provider_call": True,
                    "admin_only": True,
                    "no_charge": True,
                    "public_user": False,
                }
            ),
            "invoice_json": json.dumps(
                {
                    "source": "product_video",
                    "product_type": "video_trend",
                    "total_xu": 144,
                    "is_confirmed": True,
                }
            ),
            "addon_plan_json": "{}",
            "scene_cards_json": json.dumps(
                [
                    {"scene_index": 1, "video_prompt": "scene one"},
                    {"scene_index": 2, "video_prompt": "scene two"},
                ]
            ),
        },
        "scenes": [
            {"scene_id": 130, "project_id": 32, "scene_index": 1},
            {"scene_id": 131, "project_id": 32, "scene_index": 2},
        ],
    }

    worker_payload = remote_worker_api.build_worker_job_payload(hydrated)

    assert worker_payload["controlled_fallback_worker_context"] is True
    assert worker_payload[
        "controlled_fallback_replacement_authorization"
    ]["authorization_id"] == AUTHORIZATION_ID
    assert worker_payload["replacement_authorization_id"] == AUTHORIZATION_ID
    assert worker_payload["replacement_authorization_version"] == 2
    assert worker_payload["replacement_calls_consumed"] == 0
    assert worker_payload["replacement_calls_remaining"] == 2
    assert worker_payload["fallback_scene_index"] == 1
    assert worker_payload["provider_order"] == [
        "shopaikey_video",
        "key4u_video",
    ]
    assert worker_payload["charged_xu"] == 0

    malicious = copy.deepcopy(payload)
    malicious["controlled_fallback_replacement_authorization"][
        "api_key"
    ] = "must-not-reach-worker"
    malicious_hydrated = {
        **hydrated,
        "result_json": json.dumps(malicious),
    }
    sanitized_worker_payload = remote_worker_api.build_worker_job_payload(
        malicious_hydrated
    )
    assert "api_key" not in sanitized_worker_payload[
        "controlled_fallback_replacement_authorization"
    ]


def test_fail_api_persists_replacement_receipt_without_new_identity_rows() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        project = video_project_queue.create_video_project(
            conn,
            user_id=28,
            profile_id="video_trend",
            topic="job 28 replacement receipt",
            asset_pack={
                "source": "product_video",
                "render_mode": "real",
                "provider_call": True,
                "product_type": "video_trend",
                "public_user": True,
            },
        )
        project_id = int(project["project_id"])
        video_project_queue.update_video_project(
            conn,
            project_id,
            status="queued_for_worker",
            total_xu_estimated=144,
            is_confirmed=1,
            scene_count=2,
        )
        job = video_project_queue.enqueue_video_render_job(
            conn,
            project_id=project_id,
            user_id=28,
        )
        claimed = video_project_queue.claim_next_video_job(
            conn,
            worker_id="job28-owner-worker",
        )
        persisted_seed = _job28_payload()
        persisted_seed["controlled_fallback_replacement_authorization"][
            "job_id"
        ] = int(job["job_id"])
        persisted_seed["controlled_fallback_replacement_authorization"][
            "project_id"
        ] = project_id
        persisted_seed["job_id"] = int(job["job_id"])
        persisted_seed["id"] = int(job["job_id"])
        persisted_seed["project_id"] = project_id
        conn.execute(
            "UPDATE video_jobs SET result_json=? WHERE id=?",
            (json.dumps(persisted_seed), int(job["job_id"])),
        )
        conn.commit()
        counts_before = [
            conn.execute("SELECT COUNT(*) FROM video_projects").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0],
            conn.execute(
                "SELECT COUNT(*) FROM video_dispatch_outbox"
            ).fetchone()[0],
        ]
        scene_one_diagnostics = _replacement_submit_diagnostics(
            persisted_seed,
            scene_index=1,
            task_id="key4u-replacement-scene-1",
        )
        scene_one_persisted, _ = remote_worker_api._controlled_fallback_submit_receipt(
            scene_one_diagnostics
        )
        for item in scene_one_persisted["scene_tasks"]:
            if int(item.get("scene_index") or 0) == 1:
                item.update(
                    {
                        "status": "completed",
                        "actual_provider_payload_status": "SUCCESS",
                        "clip_valid": True,
                        "result_url_valid": True,
                        "artifact_bytes": 1024,
                    }
                )
        scene_one_persisted["provider_scene_tasks"] = copy.deepcopy(
            scene_one_persisted["scene_tasks"]
        )
        diagnostics = _replacement_submit_diagnostics(
            scene_one_persisted,
            scene_index=2,
            task_id="key4u-replacement-scene-2",
        )

        result = remote_worker_api.fail_remote_worker_job(
            conn,
            worker_id="job28-owner-worker",
            job_id=int(claimed["id"]),
            safe_error="RuntimeError:provider_in_progress",
            retryable=True,
            diagnostics=diagnostics,
        )
        persisted = json.loads(result["job"]["result_json"])
        counts_after = [
            conn.execute("SELECT COUNT(*) FROM video_projects").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM video_jobs").fetchone()[0],
            conn.execute(
                "SELECT COUNT(*) FROM video_dispatch_outbox"
            ).fetchone()[0],
        ]

        assert result["deferred"] is True
        assert result["job"]["status"] == "queued"
        assert counts_after == counts_before == [1, 1, 0]
        assert persisted[
            "controlled_fallback_replacement_submit_receipts_by_authorization"
        ][AUTHORIZATION_ID]["1"]["provider_task_id"] == (
            "key4u-replacement-scene-1"
        )
        assert persisted[
            "controlled_fallback_replacement_submit_receipts_by_authorization"
        ][AUTHORIZATION_ID]["2"]["provider_task_id"] == (
            "key4u-replacement-scene-2"
        )
        assert persisted["controlled_fallback_replacement_authorization"][
            "calls_consumed"
        ] == 2
        assert persisted["controlled_fallback_submit_receipts_by_scene"][
            "1"
        ] == LEGACY_RECEIPT
        assert persisted["charged_xu"] == 0
    finally:
        conn.close()


def test_real_per_scene_orchestrator_advances_replacement_authority_in_same_tick(
    monkeypatch,
    tmp_path,
) -> None:
    payload = _job28_payload()
    payload.update(
        {
            "user_id": 7126457028,
            "product_type": "video_trend",
            "quality_tier": 400,
            "scene_count": 2,
            "scene_duration_seconds": 8,
            "expected_duration_seconds": 16,
            "orchestration_mode": "per_scene_8s",
            "scene_cards": [
                {
                    "scene_index": 1,
                    "video_prompt": "replacement scene one",
                    "target_duration_sec": 8,
                    "aspect_ratio": "9:16",
                },
                {
                    "scene_index": 2,
                    "video_prompt": "replacement scene two",
                    "target_duration_sec": 8,
                    "aspect_ratio": "9:16",
                },
            ],
        }
    )
    eligibility = {
        "worker_local_ready_provider_keys": ["key4u_video"],
        "contract_valid_provider_chain": ["shopaikey_video", "key4u_video"],
    }
    claimed = remote_worker_api.product_video_controlled_fallback_claim_payload(
        {"id": 28, "project_id": 32},
        payload,
        {"project_id": 32},
        eligibility,
    )["result"]
    claimed["scene_cards"] = payload["scene_cards"]
    seen: list[tuple[int, int, int, str]] = []

    def fake_provider_generation(request, *, output_dir, environ, **_kwargs):
        scene_index = int(request.metadata.get("scene_index") or 0)
        seen.append(
            (
                scene_index,
                int(request.metadata.get("fallback_scene_index") or 0),
                int(request.metadata.get("replacement_calls_consumed") or 0),
                str(environ.get("VIDEO_PROVIDER_CHAIN") or ""),
            )
        )
        output = Path(output_dir) / f"key4u-replacement-scene-{scene_index}.mp4"
        output.write_bytes(
            f"key4u-replacement-scene-{scene_index}".encode("ascii")
        )
        return {
            "ok": True,
            "provider": "key4u_video",
            "provider_task_ids": [
                f"key4u-replacement-scene-{scene_index}"
            ],
            "provider_video_ids": [
                f"key4u-replacement-scene-{scene_index}"
            ],
            "output_path": str(output),
            "scene_index": scene_index,
            "result_url_present": True,
        }

    final_path = tmp_path / "final.mp4"

    def fake_finalize(**_kwargs):
        final_path.write_bytes(b"two-scene-final-mp4")
        return {
            "ok": True,
            "final_video_path": str(final_path),
            "duration_sec": 16.0,
            "scene_order": [1, 2],
        }

    monkeypatch.setattr(
        connector,
        "run_provider_generation",
        fake_provider_generation,
    )
    monkeypatch.setattr(
        connector,
        "_canonical_product_video_workspace",
        lambda _job: str(tmp_path / "workspace"),
    )
    monkeypatch.setattr(
        connector.video_final_output,
        "probe_video",
        lambda path: {
            "ok": True,
            "has_video": True,
            "has_audio": False,
            "bytes": Path(path).stat().st_size,
            "duration": 8.0,
        },
    )
    monkeypatch.setattr(connector, "finalize_multiscene_scene_clips", fake_finalize)

    result = connector._run_per_scene_provider_orchestrator(
        claimed,
        str(tmp_path / "discarded"),
        provider_order=["shopaikey_video", "key4u_video"],
        provider_events=[],
        debug_results=[],
    )

    assert result["ok"] is True
    assert seen == [
        (1, 1, 0, "key4u_video"),
        (2, 2, 1, "key4u_video"),
    ]
    receipts = result[
        "controlled_fallback_replacement_submit_receipts_by_authorization"
    ][AUTHORIZATION_ID]
    assert sorted(receipts) == ["1", "2"]
    assert receipts["1"]["submit_evidence_state"] == (
        "task_completed_with_artifact"
    )
    assert receipts["2"]["submit_evidence_state"] == (
        "task_completed_with_artifact"
    )
    assert result["controlled_fallback_replacement_authorization"][
        "calls_consumed"
    ] == 2
    assert result["controlled_fallback_replacement_authorization"][
        "state"
    ] == "consumed"
    assert result["replacement_calls_remaining"] == 0
    assert result["fallback_count_by_scene"] == {"1": 2, "2": 1}
    assert result["charged_xu"] == 0


def test_complete_api_preserves_internal_replacement_receipts(
    monkeypatch,
    tmp_path,
) -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        project = video_project_queue.create_video_project(
            conn,
            user_id=28,
            profile_id="video_trend",
            topic="job 28 replacement completion",
            asset_pack={
                "source": "product_video",
                "render_mode": "real",
                "provider_call": True,
                "product_type": "video_trend",
                "public_user": True,
            },
        )
        project_id = int(project["project_id"])
        video_project_queue.update_video_project(
            conn,
            project_id,
            status="queued_for_worker",
            total_xu_estimated=144,
            is_confirmed=1,
            scene_count=2,
        )
        job = video_project_queue.enqueue_video_render_job(
            conn,
            project_id=project_id,
            user_id=28,
        )
        job_id = int(job["job_id"])
        claimed = video_project_queue.claim_next_video_job(
            conn,
            worker_id="job28-owner-worker",
        )
        assert int(claimed["id"]) == job_id

        payload = _job28_payload()
        payload["job_id"] = job_id
        payload["id"] = job_id
        payload["project_id"] = project_id
        payload["controlled_fallback_replacement_authorization"].update(
            {
                "job_id": job_id,
                "project_id": project_id,
                "consumed_scene_indexes": [1, 2],
                "calls_consumed": 2,
                "state": "consumed",
                "api_key": "must-not-persist",
            }
        )
        payload[
            "controlled_fallback_replacement_submit_receipts_by_authorization"
        ] = {
            AUTHORIZATION_ID: {
                str(index): {
                    "authorization_id": AUTHORIZATION_ID,
                    "authorization_version": 2,
                    "authorization_state": "consumed",
                    "scene_index": index,
                    "provider": "key4u_video",
                    "provider_task_id": f"key4u-replacement-scene-{index}",
                    "task_id_present": True,
                    "submit_evidence_state": "task_completed_with_artifact",
                    "authorization_header": "Bearer must-not-persist",
                }
                for index in (1, 2)
            }
        }
        payload["controlled_fallback_submit_receipt_history"] = [
            {**LEGACY_RECEIPT, "archived_authorization_id": "legacy-scene-1-v1"}
        ]
        payload["replacement_authorization_id"] = AUTHORIZATION_ID
        payload["replacement_authorization_version"] = 2
        payload["replacement_calls_consumed"] = 2
        payload["replacement_calls_remaining"] = 0
        payload["fallback_count_by_scene"] = {"1": 2, "2": 1}
        scene_paths = []
        for index in (1, 2):
            scene_path = tmp_path / f"scene-{index}.mp4"
            scene_path.write_bytes(f"scene-{index}-clip".encode("ascii"))
            scene_paths.append(str(scene_path))
        payload["scene_tasks"] = [
            {
                "scene_index": index,
                "provider": "key4u_video",
                "provider_task_id": f"key4u-replacement-scene-{index}",
                "provider_video_id": f"key4u-replacement-scene-{index}",
                "active_task_id": f"key4u-replacement-scene-{index}",
                "winning_task_id": f"key4u-replacement-scene-{index}",
                "status": "scene_clip_validated",
                "actual_provider_payload_status": "SUCCESS",
                "result_url_valid": True,
                "clip_valid": True,
                "artifact_valid": True,
                "clip_bytes": Path(scene_paths[index - 1]).stat().st_size,
                "artifact_bytes": Path(scene_paths[index - 1]).stat().st_size,
                "clip_path": scene_paths[index - 1],
                "output_path": scene_paths[index - 1],
                "fallback_count": 2 if index == 1 else 1,
                "provider_fallback_count": 2 if index == 1 else 1,
                "fallback_allowed": False,
                "controlled_fallback_allowed": False,
            }
            for index in (1, 2)
        ]
        payload["provider_scene_tasks"] = copy.deepcopy(payload["scene_tasks"])
        payload["scene_coverage_valid_bool"] = True
        payload["scene_coverage_count"] = 2
        payload["completed_scene_count"] = 2
        payload["missing_scene_indexes"] = []
        payload["final_mp4_valid"] = True
        payload["concat_attempted"] = True
        payload["concat_output_valid"] = True
        payload["concat_status"] = "completed"
        payload["expected_duration_seconds"] = 16
        payload["final_duration_seconds"] = 16.0
        payload["output_duration"] = 16.0
        payload["render_mode"] = "real"
        payload["provider_attempted"] = True
        payload["visual_classification"] = "final_ai_video"
        payload["final_classification"] = "final_ai_video"
        payload["final_video_path"] = str(tmp_path / "job28-final.mp4")
        payload["no_charge"] = True
        Path(payload["final_video_path"]).write_bytes(b"job28-final-two-scene-mp4")
        monkeypatch.setattr(
            video_project_queue.video_final_output,
            "validate_final_video_output",
            lambda **_kwargs: {
                "ok": True,
                "bytes": Path(payload["final_video_path"]).stat().st_size,
                "mime": "video/mp4",
                "container": "mp4",
                "duration": 16.0,
                "duration_seconds": 16.0,
            },
        )
        conn.execute(
            "UPDATE video_jobs SET result_json=? WHERE id=?",
            (json.dumps(payload), job_id),
        )
        conn.commit()
        seed_job = video_project_queue.get_video_render_job(conn, job_id)
        seed_payload = json.loads(seed_job["result_json"])
        assert [item["provider"] for item in seed_payload["scene_tasks"]] == [
            "key4u_video",
            "key4u_video",
        ]
        precoverage = video_project_queue.product_video_scene_coverage_state(
            video_project_queue.get_video_project(conn, project_id),
            seed_job,
            seed_payload,
        )
        assert precoverage["completed_scene_count"] == 2, precoverage
        assert precoverage["delivery_blocked_by_scene_coverage"] is False

        completed = remote_worker_api.complete_remote_worker_job(
            conn,
            worker_id="job28-owner-worker",
            job_id=job_id,
            result=payload,
            final_video_path=payload["final_video_path"],
        )
        persisted = json.loads(completed["job"]["result_json"])

        assert completed["ok"] is True, completed
        assert completed["job"]["status"] == "completed", (
            completed.get("reason"),
            completed["job"].get("last_error"),
            completed["project"].get("error_log"),
            persisted.get("blocker"),
            persisted.get("terminal_state"),
        )
        assert persisted["controlled_fallback_replacement_authorization"][
            "authorization_id"
        ] == AUTHORIZATION_ID
        assert "api_key" not in persisted[
            "controlled_fallback_replacement_authorization"
        ]
        assert persisted[
            "controlled_fallback_replacement_submit_receipts_by_authorization"
        ][AUTHORIZATION_ID]["1"]["authorization_state"] == "consumed"
        assert persisted[
            "controlled_fallback_replacement_submit_receipts_by_authorization"
        ][AUTHORIZATION_ID]["2"]["authorization_state"] == "consumed"
        assert "authorization_header" not in persisted[
            "controlled_fallback_replacement_submit_receipts_by_authorization"
        ][AUTHORIZATION_ID]["1"]
        assert persisted["controlled_fallback_submit_receipt_history"] == [
            {**LEGACY_RECEIPT, "archived_authorization_id": "legacy-scene-1-v1"}
        ]
        assert persisted["fallback_count_by_scene"] == {"1": 2, "2": 1}
        assert persisted["charged_xu"] == 0
        assert int(completed["project"].get("total_xu_charged") or 0) == 0
    finally:
        conn.close()


def test_failed_scene1_receipt_cannot_rewrite_scene2_and_terminal_releases_lock() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        project = video_project_queue.create_video_project(
            conn,
            user_id=28,
            profile_id="video_trend",
            topic="job 28 cross-scene receipt isolation",
            asset_pack={
                "source": "product_video",
                "render_mode": "real",
                "provider_call": True,
                "product_type": "video_trend",
                "public_user": True,
            },
        )
        project_id = int(project["project_id"])
        video_project_queue.update_video_project(
            conn,
            project_id,
            status="queued_for_worker",
            total_xu_estimated=144,
            is_confirmed=1,
            scene_count=2,
        )
        job = video_project_queue.enqueue_video_render_job(
            conn,
            project_id=project_id,
            user_id=28,
        )
        claimed = video_project_queue.claim_next_video_job(
            conn,
            worker_id="job28-owner-worker",
        )
        job_id = int(claimed["id"])
        seed = _job28_payload()
        seed.update({"id": job_id, "job_id": job_id, "project_id": project_id})
        seed["controlled_fallback_replacement_authorization"].update(
            {"job_id": job_id, "project_id": project_id}
        )
        conn.execute(
            "UPDATE video_jobs SET result_json=? WHERE id=?",
            (json.dumps(seed), job_id),
        )
        conn.commit()

        diagnostics = _replacement_submit_diagnostics(
            seed,
            scene_index=1,
            task_id="",
        )
        for item in diagnostics["scene_tasks"]:
            if int(item.get("scene_index") or 0) == 2:
                item.update(
                    {
                        "provider": "key4u_video",
                        "selected_provider": "key4u_video",
                        "status": "provider_running",
                        "actual_provider_payload_status": "queued",
                        "failure_reason": "all_video_providers_submit_failed",
                        "fallback_count": 1,
                        "provider_fallback_count": 1,
                        "fallback_count_before_submit": 0,
                        "fallback_allowed": False,
                        "controlled_fallback_allowed": False,
                        "fallback_provider_candidate": "shopaikey_video",
                        "fallback_provider_order": ["shopaikey_video"],
                    }
                )
        diagnostics["provider_scene_tasks"] = copy.deepcopy(
            diagnostics["scene_tasks"]
        )

        failed = remote_worker_api.fail_remote_worker_job(
            conn,
            worker_id="job28-owner-worker",
            job_id=job_id,
            safe_error="RuntimeError:provider_in_progress",
            retryable=True,
            diagnostics=diagnostics,
        )
        persisted = json.loads(failed["job"]["result_json"])
        scene_two = next(
            item
            for item in persisted["scene_tasks"]
            if int(item.get("scene_index") or 0) == 2
        )
        receipts = persisted[
            "controlled_fallback_replacement_submit_receipts_by_authorization"
        ][AUTHORIZATION_ID]

        assert failed["job"]["status"] == "failed"
        assert failed["job"]["locked_by"] == ""
        assert failed["job"]["locked_at"] in (None, "")
        assert failed["job"]["lease_expires_at"] in (None, "")
        assert sorted(receipts) == ["1"]
        assert scene_two["provider"] == "shopaikey_video"
        assert scene_two["provider_task_id"] == "old-shopaikey-scene-2"
        assert scene_two["fallback_count"] == 0
        assert scene_two["controlled_fallback_allowed"] is False
        assert scene_two["fallback_provider_candidate"] == ""
        assert persisted["fallback_count_by_scene"] == {"1": 2, "2": 0}
        assert persisted["controlled_fallback_replacement_authorization"][
            "calls_consumed"
        ] == 1
        assert persisted["replacement_calls_remaining"] == 1
        assert persisted["charged_xu"] == 0
    finally:
        conn.close()


def test_orchestrator_skips_consumed_no_task_scene_and_calls_only_remaining_scene(
    monkeypatch,
    tmp_path,
) -> None:
    payload = _job28_payload()
    payload.update(
        {
            "user_id": 7126457028,
            "product_type": "video_trend",
            "scene_count": 2,
            "orchestration_mode": "per_scene_8s",
            "scene_cards": [
                {
                    "scene_index": 1,
                    "video_prompt": "consumed failed scene one",
                    "target_duration_sec": 8,
                    "aspect_ratio": "9:16",
                },
                {
                    "scene_index": 2,
                    "video_prompt": "remaining replacement scene two",
                    "target_duration_sec": 8,
                    "aspect_ratio": "9:16",
                },
            ],
        }
    )
    scene_one_failed = _replacement_submit_diagnostics(
        payload,
        scene_index=1,
        task_id="",
    )
    scene_one_failed, _ = remote_worker_api._controlled_fallback_submit_receipt(
        scene_one_failed
    )
    for item in scene_one_failed["scene_tasks"]:
        index = int(item.get("scene_index") or 0)
        if index == 1:
            item.update(
                {
                    "status": "failed",
                    "failure_reason": "provider_in_progress",
                    "controlled_fallback_allowed": False,
                    "fallback_provider_candidate": "",
                    "fallback_provider_order": [],
                }
            )
        elif index == 2:
            item.update(
                {
                    "provider": "shopaikey_video",
                    "selected_provider": "shopaikey_video",
                    "status": "provider_not_start",
                    "actual_provider_payload_status": "NOT_START",
                    "failure_reason": "",
                    "fallback_count": 0,
                    "provider_fallback_count": 0,
                    "fallback_count_before_submit": 0,
                    "fallback_allowed": True,
                    "controlled_fallback_allowed": True,
                    "fallback_provider_candidate": "key4u_video",
                    "fallback_provider_order": ["key4u_video"],
                    "fallback_scene_index": 2,
                }
            )
    scene_one_failed["provider_scene_tasks"] = copy.deepcopy(
        scene_one_failed["scene_tasks"]
    )
    scene_one_failed.update(
        {
            "scene_cards": payload["scene_cards"],
            "fallback_scene_index": 2,
            "fallback_allowed": True,
            "controlled_fallback_allowed": True,
            "fallback_provider_candidate": "key4u_video",
            "fallback_provider_order": ["key4u_video"],
            "fallback_count_by_scene": {"1": 2, "2": 0},
            "terminal_state": "final_rendering",
            "final_decision": "continue_polling",
            "continue_polling": True,
        }
    )
    calls: list[int] = []

    def fake_provider_generation(request, *, output_dir, environ, **_kwargs):
        del output_dir
        calls.append(int(request.metadata.get("scene_index") or 0))
        assert environ.get("VIDEO_PROVIDER_CHAIN") == "key4u_video"
        return {
            "ok": False,
            "provider": "key4u_video",
            "selected_provider": "key4u_video",
            "provider_router_called": True,
            "provider_submit_called": True,
            "provider_http_request_sent": True,
            "provider_submit_http_status": 200,
            "provider_task_ids": ["key4u-scene-two-new-task"],
            "provider_video_ids": ["key4u-scene-two-new-task"],
            "provider_task_id_saved": True,
            "task_id_present": True,
            "submit_accepted": True,
            "provider_status": "running",
            "normalized_provider_status": "running",
            "continue_polling": True,
            "provider_error": "provider_in_progress",
            "blocker": "provider_in_progress",
            "no_charge": True,
        }

    monkeypatch.setattr(
        connector,
        "run_provider_generation",
        fake_provider_generation,
    )
    monkeypatch.setattr(
        connector,
        "_canonical_product_video_workspace",
        lambda _job: str(tmp_path / "workspace"),
    )

    result = connector._run_per_scene_provider_orchestrator(
        scene_one_failed,
        str(tmp_path / "discarded"),
        provider_order=["shopaikey_video", "key4u_video"],
        provider_events=[],
        debug_results=[],
    )

    assert calls == [2]
    assert result["continue_polling"] is True
    assert result["terminal_state"] == "final_rendering"
    receipts = result[
        "controlled_fallback_replacement_submit_receipts_by_authorization"
    ][AUTHORIZATION_ID]
    assert sorted(receipts) == ["1"]
    assert result["replacement_calls_consumed"] == 1
    assert result["replacement_calls_remaining"] == 1


def test_remaining_scene_transition_submits_official_key4u_task_then_polls_only_new_id(
    monkeypatch,
    tmp_path,
) -> None:
    payload = _job28_payload()
    scene_one_failed = _replacement_submit_diagnostics(
        payload,
        scene_index=1,
        task_id="",
    )
    job, _ = remote_worker_api._controlled_fallback_submit_receipt(
        scene_one_failed
    )
    for item in job["scene_tasks"]:
        index = int(item.get("scene_index") or 0)
        if index == 1:
            item.update(
                {
                    "status": "failed",
                    "failure_reason": "provider_in_progress",
                    "controlled_fallback_allowed": False,
                    "fallback_provider_candidate": "",
                    "fallback_provider_order": [],
                }
            )
        elif index == 2:
            item.update(
                {
                    "provider": "shopaikey_video",
                    "selected_provider": "shopaikey_video",
                    "status": "provider_not_start",
                    "actual_provider_payload_status": "NOT_START",
                    "provider_status_raw": "NOT_START",
                    "failure_reason": "",
                    "fallback_count": 0,
                    "provider_fallback_count": 0,
                    "fallback_count_before_submit": 0,
                    "fallback_allowed": True,
                    "controlled_fallback_allowed": True,
                    "fallback_provider_candidate": "key4u_video",
                    "fallback_provider_order": ["key4u_video"],
                    "fallback_scene_index": 2,
                    "provider_stalled_not_start": True,
                    "provider_scene_stalled": True,
                    "scene_not_start_elapsed": 900,
                    "provider_wait_elapsed_seconds": 900,
                }
            )
    job["provider_scene_tasks"] = copy.deepcopy(job["scene_tasks"])
    job.update(
        {
            "user_id": 7126457028,
            "product_type": "video_trend",
            "quality_tier": 400,
            "scene_count": 2,
            "scene_duration_seconds": 8,
            "expected_duration_seconds": 16,
            "orchestration_mode": "per_scene_8s",
            "fallback_scene_index": 2,
            "fallback_count_by_scene": {"1": 2, "2": 0},
            "fallback_allowed": True,
            "controlled_fallback_allowed": True,
            "fallback_provider_candidate": "key4u_video",
            "fallback_provider_order": ["key4u_video"],
            "provider_order": ["shopaikey_video", "key4u_video"],
            "configured_provider_chain": ["shopaikey_video", "key4u_video"],
            "contract_valid_provider_chain": ["shopaikey_video", "key4u_video"],
            "runtime_candidate_keys": ["key4u_video"],
            "provider_model_map": {"key4u_video": "veo_3_1-fast"},
            "provider_request_defaults": {
                "key4u_video": {"duration": 8, "resolution": "1080p"}
            },
            "terminal_state": "final_rendering",
            "continue_polling": True,
        }
    )
    for key, value in {
        "PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED": "1",
        "KEY4U_VIDEO_ENABLED": "1",
        "KEY4U_VIDEO_SUBMIT_URL": "https://api.key4u.vn/v1/video/create",
        "KEY4U_VIDEO_POLL_URL": "https://api.key4u.vn/v1/video/query?id={task_id}",
        "KEY4U_VIDEO_AUTH_HEADER_NAME": "Authorization",
        "KEY4U_VIDEO_AUTH_HEADER_VALUE": "Bearer test-key",
        "KEY4U_VIDEO_MODEL": "veo_3_1-fast",
        "KEY4U_VIDEO_CAPABILITIES": "text_to_video,scene_video,multi_scene_video",
        "KEY4U_BASE_URL": "https://api.key4u.vn",
        "VIDEO_PROVIDER_CHAIN": "key4u_video",
        "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
        "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
        "REAL_PROVIDER_SMOKE_ENABLED": "1",
    }.items():
        monkeypatch.setenv(key, value)
    calls: list[tuple[str, str, str]] = []

    def fake_open_json(self, url, payload=None, *, method="POST", **_kwargs):
        calls.append((method, url, str((payload or {}).get("model") or "")))
        if method == "POST":
            return {
                "ok": True,
                "status_code": 200,
                "body": {"id": "key4u_scene2_new_task", "status": "queued"},
                "response_shape": {"type": "dict"},
            }
        assert "old-shopaikey-scene-2" not in url
        assert url.endswith("/v1/videos/key4u_scene2_new_task")
        return {
            "ok": True,
            "status_code": 200,
            "body": {"id": "key4u_scene2_new_task", "status": "pending"},
            "response_shape": {"type": "dict"},
        }

    monkeypatch.setattr(GenericHttpVideoProvider, "_open_json", fake_open_json)
    scene = SimpleNamespace(
        scene_id=2,
        video_prompt="remaining replacement scene two",
        visual_prompt="remaining replacement scene two",
        aspect_ratio="9:16",
        target_duration_sec=8,
        _toan_aas_job=job,
    )

    with pytest.raises(connector.RealVideoRenderError) as exc_info:
        asyncio.run(
            connector._render_scene_async(
                scene,
                str(tmp_path / "scene-2.mp4"),
                ["key4u_video"],
            )
        )

    diagnostics = exc_info.value.diagnostics
    assert str(exc_info.value) == "provider_in_progress"
    assert calls == [
        (
            "POST",
            "https://api.key4u.vn/v1/videos/generations",
            "veo_3_1-fast",
        ),
        (
            "GET",
            "https://api.key4u.vn/v1/videos/key4u_scene2_new_task",
            "",
        ),
    ]
    assert diagnostics["provider_submit_called"] is True
    assert diagnostics["provider_http_request_sent"] is True
    assert diagnostics["provider_submit_http_status"] == 200
    assert diagnostics["provider_task_id_saved"] is True
    assert diagnostics["provider_task_ids"] == ["key4u_scene2_new_task"]
    assert diagnostics["continue_polling"] is True


def test_accepted_replacement_task_resets_primary_stall_clock_before_poll() -> None:
    payload = _job28_payload()
    scene_one_failed = _replacement_submit_diagnostics(
        payload,
        scene_index=1,
        task_id="",
    )
    persisted, _ = remote_worker_api._controlled_fallback_submit_receipt(
        scene_one_failed
    )
    for item in persisted["scene_tasks"]:
        if int(item.get("scene_index") or 0) == 1:
            item.update(
                {
                    "status": "failed",
                    "failure_reason": "provider_in_progress",
                    "exhausted": True,
                    "controlled_fallback_allowed": False,
                    "fallback_provider_candidate": "",
                    "fallback_provider_order": [],
                }
            )
        elif int(item.get("scene_index") or 0) == 2:
            item.update(
                {
                    "provider": "key4u_video",
                    "selected_provider": "key4u_video",
                    "status": "provider_stalled_not_start",
                    "current_scene_status": "provider_stalled_not_start",
                    "actual_provider_payload_status": "queued",
                    "provider_status_raw": "NOT_START",
                    "failure_reason": "all_video_providers_submit_failed",
                    "fallback_count": 1,
                    "provider_fallback_count": 1,
                    "fallback_count_before_submit": 0,
                    "provider_elapsed_seconds": 900,
                    "provider_wait_elapsed_seconds": 900,
                    "scene_not_start_elapsed": 900,
                    "provider_stalled_not_start": True,
                    "provider_scene_stalled": True,
                    "provider_in_progress_stalled": True,
                    "provider_progress_stuck": True,
                    "exhausted": True,
                }
            )
    persisted["provider_scene_tasks"] = copy.deepcopy(persisted["scene_tasks"])
    persisted.update(
        {
            "fallback_scene_index": 2,
            "fallback_allowed": True,
            "controlled_fallback_allowed": True,
            "fallback_provider_candidate": "key4u_video",
            "fallback_provider_order": ["key4u_video"],
            "claim_terminal_suppressed_for_controlled_fallback": True,
            "terminal_state": "final_rendering",
            "continue_polling": True,
        }
    )
    diagnostics = _replacement_submit_diagnostics(
        persisted,
        scene_index=2,
        task_id="key4u-scene-two-new-task",
    )

    normalized, state = remote_worker_api._controlled_fallback_submit_receipt(
        diagnostics
    )
    scene_two = next(
        item
        for item in normalized["scene_tasks"]
        if int(item.get("scene_index") or 0) == 2
    )
    ledger = video_project_queue.product_video_scene_ledger_state(
        {"scene_count": 2},
        {"id": 28, "status": "processing", "attempts": 40},
        normalized,
    )

    assert state["task_id_present"] is True
    assert state["task_terminal_failed"] is False
    assert scene_two["status"] == "provider_running"
    assert scene_two["current_scene_status"] == "provider_running"
    assert scene_two["actual_provider_payload_status"] == "queued"
    assert scene_two["provider_status_raw"] == "queued"
    assert scene_two["provider_elapsed_seconds"] == 0
    assert scene_two["provider_wait_elapsed_seconds"] == 0
    assert scene_two["scene_not_start_elapsed"] == 0
    assert scene_two["provider_stalled_not_start"] is False
    assert scene_two["provider_scene_stalled"] is False
    assert scene_two["provider_in_progress_stalled"] is False
    assert scene_two["provider_progress_stuck"] is False
    assert scene_two["exhausted"] is False
    assert scene_two["failure_reason"] == ""
    assert scene_two["task_pollable"] is True
    assert scene_two["submit_accepted"] is True
    assert normalized["replacement_calls_consumed"] == 2
    assert normalized["replacement_calls_remaining"] == 0
    assert normalized["provider_pending_task_id"] == "key4u-scene-two-new-task"
    assert normalized["continue_polling"] is True
    assert normalized["terminal_state"] == "final_rendering"
    assert ledger["aggregate_job_status"] != "failed_no_charge"
    assert ledger["active_scene_indexes"] == [2]
    assert ledger["continue_polling"] is True


def test_pollable_scene_two_row_overrides_stale_failed_summary_without_reviving_scene_one() -> None:
    task_id = "key4u-existing-scene-two-task"
    scene_tasks = [
        {
            "scene_index": 1,
            "status": "failed",
            "failure_reason": "all_video_providers_submit_failed",
            "task_id_present": False,
            "task_pollable": False,
            "exhausted": True,
        },
        {
            "scene_index": 2,
            "provider": "key4u_video",
            "provider_task_id": task_id,
            "active_task_id": task_id,
            "status": "provider_running",
            "provider_status_raw": "queued",
            "task_id_present": True,
            "task_pollable": True,
            "submit_accepted": True,
            "exhausted": False,
        },
    ]
    result = {
        "scene_count": 2,
        "terminal_state": "failed_no_charge",
        "final_decision": "failed_no_charge",
        "aggregate_job_status": "failed_no_charge",
        "aggregate_reason": "required_scene_exhausted_no_charge",
        "continue_polling": False,
        "provider_submit_allowed": False,
        "replacement_calls_consumed": 2,
        "replacement_calls_remaining": 0,
        "scene_active_task_by_index": {"2": task_id},
        "scene_status_by_index": {"1": "failed", "2": "failed"},
        "scene_status_by_scene": {"1": "failed", "2": "failed"},
        "scene_tasks": scene_tasks,
        "provider_scene_tasks": copy.deepcopy(scene_tasks),
    }

    ledger = video_project_queue.product_video_scene_ledger_state(
        {"scene_count": 2},
        {"id": 28, "status": "failed", "attempts": 40},
        result,
    )
    by_scene = {
        int(item["scene_index"]): item for item in ledger["scene_ledger"]
    }

    assert by_scene[1]["active_task_id"] == ""
    assert by_scene[1]["task_id_present"] is False
    assert by_scene[1]["status"] == "failed"
    assert by_scene[2]["active_task_id"] == task_id
    assert by_scene[2]["task_pollable"] is True
    assert by_scene[2]["status"] == "provider_running"
    assert (
        by_scene[2]["authoritative_status_source"]
        == "current_pollable_scene_task_status"
    )
    assert ledger["scene_status_by_index"] == {
        "1": "failed",
        "2": "provider_running",
    }
    assert ledger["active_scene_indexes"] == [2]
    assert ledger["exhausted_scene_indexes"] == [1]
    assert ledger["aggregate_job_status"] != "failed_no_charge"
    assert ledger["continue_polling"] is True


def test_current_scene_two_terminal_failure_still_overrides_stale_running_summary() -> None:
    task_id = "key4u-existing-scene-two-terminal-task"
    result = {
        "scene_count": 2,
        "scene_active_task_by_index": {"2": task_id},
        "scene_status_by_index": {"1": "failed", "2": "provider_running"},
        "scene_tasks": [
            {
                "scene_index": 1,
                "status": "failed",
                "task_id_present": False,
                "exhausted": True,
            },
            {
                "scene_index": 2,
                "provider": "key4u_video",
                "provider_task_id": task_id,
                "active_task_id": task_id,
                "status": "failed",
                "provider_status_raw": "FAILURE",
                "failure_reason": "provider_terminal_failure",
                "task_id_present": True,
                "task_pollable": True,
                "exhausted": True,
            },
        ],
    }

    ledger = video_project_queue.product_video_scene_ledger_state(
        {"scene_count": 2},
        {"id": 28, "status": "processing", "attempts": 40},
        result,
    )

    assert ledger["scene_status_by_index"] == {"1": "failed", "2": "failed"}
    assert ledger["active_scene_indexes"] == []
    assert ledger["exhausted_scene_indexes"] == [1, 2]
    assert ledger["aggregate_job_status"] == "failed_no_charge"
    assert ledger["continue_polling"] is False


def test_explicit_current_scene_one_no_task_suppresses_stale_task_ownership() -> None:
    stale_scene_one_task = "key4u-stale-scene-one-history-task"
    accepted_scene_two_task = "key4u-current-scene-two-task-value"
    current_scene_tasks = [
        {
            "scene_index": 1,
            "status": "failed",
            "failure_reason": "replacement_scene1_consumed_without_task",
            "provider_task_id": "",
            "active_task_id": "",
            "primary_task_id": "",
            "winning_task_id": "",
            "task_id_present": False,
            "task_pollable": False,
            "submit_accepted": False,
            "exhausted": True,
        },
        {
            "scene_index": 2,
            "provider": "key4u_video",
            "provider_task_id": accepted_scene_two_task,
            "active_task_id": accepted_scene_two_task,
            "primary_task_id": accepted_scene_two_task,
            "status": "provider_running",
            "actual_provider_payload_status": "queued",
            "provider_status_raw": "queued",
            "task_id_present": True,
            "task_pollable": True,
            "submit_accepted": True,
            "exhausted": False,
        },
    ]
    result = {
        "scene_count": 2,
        "terminal_state": "failed_no_charge",
        "final_decision": "failed_no_charge",
        "continue_polling": False,
        "provider_submit_allowed": False,
        "replacement_calls_consumed": 2,
        "replacement_calls_remaining": 0,
        "scene_status_by_index": {"1": "failed", "2": "failed"},
        "scene_active_task_by_index": {
            "1": "",
            "2": accepted_scene_two_task,
        },
        "task_scene_index_map": {accepted_scene_two_task: 2},
        "task_to_scene_index": {accepted_scene_two_task: 2},
        "scene_winner_task_by_index": {
            "1": stale_scene_one_task,
            "2": accepted_scene_two_task,
        },
        "scene_tasks": current_scene_tasks,
        "provider_scene_tasks": copy.deepcopy(current_scene_tasks),
        "scene_ledger": [
            {
                "scene_index": 1,
                "status": "failed",
                "primary_task_id": stale_scene_one_task,
                "active_task_id": stale_scene_one_task,
                "winning_task_id": stale_scene_one_task,
                "task_id_present": True,
                "task_pollable": True,
                "exhausted": True,
            },
            {
                "scene_index": 2,
                "status": "failed",
                "primary_task_id": accepted_scene_two_task,
                "active_task_id": accepted_scene_two_task,
                "winning_task_id": accepted_scene_two_task,
                "task_id_present": True,
                "task_pollable": True,
                "exhausted": True,
            },
        ],
        "provider_events": [
            {
                "scene_index": 1,
                "provider": "key4u_video",
                "provider_task_id": stale_scene_one_task,
                "status": "failed",
                "provider_status_raw": "FAILURE",
            },
            {
                "scene_index": 2,
                "provider": "key4u_video",
                "provider_task_id": accepted_scene_two_task,
                "status": "failed",
                "provider_status_raw": "queued",
            },
        ],
        "canonical_scene_index": 1,
        "canonical_task_selected": stale_scene_one_task,
        "canonical_status": "failed",
        "provider_status_raw": "FAILURE",
    }

    ledger = video_project_queue.product_video_scene_ledger_state(
        {"scene_count": 2},
        {"id": 28, "status": "failed", "attempts": 40},
        result,
    )
    by_scene = {
        int(item["scene_index"]): item for item in ledger["scene_ledger"]
    }

    assert stale_scene_one_task not in ledger["task_to_scene_index"]
    assert ledger["task_to_scene_index"] == {accepted_scene_two_task: 2}
    assert by_scene[1]["active_task_id"] == ""
    assert by_scene[1]["primary_task_id"] == ""
    assert by_scene[1]["winning_task_id"] == ""
    assert by_scene[1]["task_candidates"] == []
    assert by_scene[1]["task_id_present"] is False
    assert by_scene[1]["task_pollable"] is False
    assert by_scene[1]["status"] == "failed"
    assert by_scene[2]["active_task_id"] == accepted_scene_two_task
    assert by_scene[2]["task_pollable"] is True
    assert by_scene[2]["status"] in {"provider_running", "provider_not_start"}
    assert ledger["scene_status_by_index"] == {
        "1": "failed",
        "2": by_scene[2]["status"],
    }
    assert ledger["active_scene_indexes"] == [2]
    assert ledger["exhausted_scene_indexes"] == [1]
    assert ledger["aggregate_job_status"] != "failed_no_charge"
    assert ledger["continue_polling"] is True


def test_disagreeing_current_scene_rows_do_not_suppress_existing_task_ownership() -> None:
    task_id = "key4u-current-scene-one-task-value"
    result = {
        "scene_count": 1,
        "scene_tasks": [
            {
                "scene_index": 1,
                "status": "failed",
                "provider_task_id": "",
                "active_task_id": "",
                "task_id_present": False,
                "task_pollable": False,
                "exhausted": True,
            }
        ],
        "provider_scene_tasks": [
            {
                "scene_index": 1,
                "provider_task_id": "",
                "active_task_id": "",
                "status": "pending_submit",
                "task_id_present": False,
                "task_pollable": False,
                "exhausted": False,
            }
        ],
        "scene_ledger": [
            {
                "scene_index": 1,
                "provider_task_id": task_id,
                "active_task_id": task_id,
                "status": "provider_running",
                "task_id_present": True,
                "task_pollable": True,
            }
        ],
    }

    ledger = video_project_queue.product_video_scene_ledger_state(
        {"scene_count": 1},
        {"id": 28, "status": "processing", "attempts": 40},
        result,
    )

    assert ledger["task_to_scene_index"] == {task_id: 1}
    assert ledger["active_scene_indexes"] == [1]
    assert ledger["scene_ledger"][0]["active_task_id"] == task_id
    assert ledger["scene_ledger"][0]["task_pollable"] is True
