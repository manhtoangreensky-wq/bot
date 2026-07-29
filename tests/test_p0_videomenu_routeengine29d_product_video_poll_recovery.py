from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from services import product_video_one_scene_engine as one_scene
from services import product_video_poll_recovery as recovery


WORKER_SHA = "0a67763783620820a62dbd2328ea174b9703d12a"
NOW = 1_785_300_000.0


def _prompt() -> one_scene.ProductVideoPromptContract:
    return one_scene.compile_product_video_prompt(
        original_user_prompt="Quay chai Aurora tren ban da, anh sang ban mai.",
        product_name="Aurora",
        required_visual_attributes=("chai thuy tinh trong", "nhan xanh la"),
        forbidden_claims=("khong tuyen bo chua benh",),
        language="vi",
        aspect_ratio="9:16",
        duration_seconds=2,
        scene_count=1,
    )


def _request(*, scene_count: int = 1):
    addons = one_scene.normalize_product_video_addons(
        {
            name: {
                "requested": False,
                "approved": False,
                "supported": name in one_scene.SUPPORTED_ADDONS,
                "required": False,
                "materialized": False,
                "handoff_status": "not_requested",
                "blocker_reason": "",
                "artifact_path": "",
                "artifact_kind": "",
            }
            for name in one_scene.ADDON_NAMES
        }
    )
    return one_scene.build_product_video_one_scene_request(
        user_id=172203,
        confirmation_id="confirm-29d",
        language="vi",
        prompt_contract=_prompt(),
        addons=addons,
        input_assets=("fixture-product-reference",),
        aspect_ratio="9:16",
        duration_seconds=2,
        audio_policy={"enabled": False, "promised": False},
        voice_policy={"enabled": False, "promised": False},
        provider_selection="fake_provider",
        explicit_confirmation_receipt={"confirmation_id": "confirm-29d"},
        runtime_sha=WORKER_SHA,
        expected_worker_sha=WORKER_SHA,
        scene_count=scene_count,
        admin_no_charge=True,
    )


def _record(
    *,
    provider_state: str = "ACCEPTED",
    provider_task_id: str = "fixture-task-29d",
    artifact_path: str = "",
    scene_count: int = 1,
) -> dict:
    return {
        "job_id": "p29d-fixture-job",
        "request": _request(scene_count=scene_count),
        "provider_state": provider_state,
        "provider_task_id": provider_task_id,
        "provider": "fake_provider",
        "artifact_path": artifact_path,
        "accepted_provider_tasks": 1 if provider_task_id else 0,
        "render_count": 1 if provider_state == "COMPLETED" else 0,
        "compose_count": 1 if provider_state == "COMPLETED" else 0,
        "terminal_state": "",
        "validation": {},
        "delivery": {},
        "receipt": {},
        "charge": {},
        "terminal_report": {},
    }


def _flags(**overrides: str) -> dict[str, str]:
    values = {
        "PRODUCT_VIDEO_POLL_RECOVERY_ENABLED": "1",
        "PRODUCT_VIDEO_POLL_RECOVERY_PUBLIC_ALLOWED": "0",
        "PRODUCT_VIDEO_POLL_RECOVERY_AUTO_RESUBMIT": "0",
        "PRODUCT_VIDEO_POLL_RECOVERY_AUTO_FALLBACK": "0",
    }
    values.update(overrides)
    return values


def _store(tmp_path: Path) -> recovery.ProductVideoPollRecoveryStore:
    return recovery.ProductVideoPollRecoveryStore(tmp_path / "durable-recovery")


def _persist(
    store: recovery.ProductVideoPollRecoveryStore,
    *,
    record: dict | None = None,
    now_epoch: float = NOW,
) -> dict:
    return recovery.persist_product_video_poll_checkpoint(
        store=store,
        record=record or _record(),
        expected_duration_seconds=2,
        motion_promised=True,
        audio_promised=False,
        now_epoch=now_epoch,
    )


def _unexpected(name: str):
    def fail(*_args, **_kwargs):
        raise AssertionError(f"unexpected side effect: {name}")

    return fail


def _effects(calls: list[str]) -> dict:
    def deliver(payload: dict) -> dict:
        calls.append("delivery")
        assert payload["production"] is False
        return {"accepted": True, "message_id": "fixture-message-29d", "production": False}

    def receipt(_payload: dict) -> dict:
        calls.append("receipt")
        return {"persisted": True, "receipt_id": "fixture-receipt-29d"}

    def charge(payload: dict) -> dict:
        calls.append("charge")
        assert payload["amount_xu"] == 0
        assert payload["admin_no_charge"] is True
        return {"ok": True, "wallet_mutated": False, "tx_id": "admin-zero-29d"}

    def report(_payload: dict) -> dict:
        calls.append("report")
        return {"emitted": True, "report_id": "fixture-report-29d"}

    return {
        "deliverer": deliver,
        "receipt_persister": receipt,
        "charger": charge,
        "terminal_reporter": report,
    }


def _recover(
    store: recovery.ProductVideoPollRecoveryStore,
    *,
    status_getter=None,
    artifact_fetcher=None,
    artifact_validator=None,
    now_epoch: float = NOW,
    expected_provider_task_id: str = "fixture-task-29d",
    effects: dict | None = None,
    **overrides,
) -> dict:
    calls: list[str] = []
    kwargs = {
        "store": store,
        "job_id": "p29d-fixture-job",
        "lease_owner": "worker-29d-a",
        "actual_worker_sha": WORKER_SHA,
        "expected_provider_task_id": expected_provider_task_id,
        "status_getter": status_getter or _unexpected("status_get"),
        "artifact_fetcher": artifact_fetcher or _unexpected("artifact_fetch"),
        "artifact_validator": artifact_validator or one_scene.validate_product_video_one_scene_artifact,
        "environ": _flags(),
        "now_epoch": now_epoch,
        **(effects or _effects(calls)),
    }
    kwargs.update(overrides)
    return recovery.recover_product_video_one_scene(**kwargs)


def _render_legal_mp4(root: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is required for the zero-cost 29D rehearsal")
    root.mkdir(parents=True, exist_ok=True)
    output = root / "provider-result.mp4"
    command = [
        ffmpeg,
        "-y",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=160x96:rate=8:duration=2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=90)
    assert completed.returncode == 0, completed.stderr
    assert output.stat().st_size >= one_scene.MINIMUM_ARTIFACT_BYTES
    return output


def _mark_validated(
    store: recovery.ProductVideoPollRecoveryStore,
    checkpoint: dict,
    artifact: Path,
) -> dict:
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    checkpoint["provider_state"] = "COMPLETED"
    checkpoint["artifact_path"] = str(artifact)
    checkpoint["validation"] = {"ok": True, "bytes": artifact.stat().st_size}
    checkpoint["stage_fingerprints"]["artifact_validated"] = digest
    return store.save(checkpoint)


def test_29d_flags_default_off_and_contract_has_no_resubmit_or_fallback() -> None:
    assert recovery.product_video_poll_recovery_flags({}) == {
        name: False for name in recovery.POLL_RECOVERY_FLAG_DEFAULTS
    }
    contract = recovery.product_video_poll_recovery_contract({})
    assert contract["enabled"] is False
    assert contract["product_family"] == one_scene.PRODUCT_FAMILY
    assert contract["mode"] == one_scene.MODE
    assert contract["poll_method"] == "GET"
    assert contract["replacement_submit_allowed"] is False
    assert contract["automatic_fallback_allowed"] is False


def test_29d_default_off_has_zero_status_or_terminal_side_effects(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _persist(store)
    result = _recover(
        store,
        environ={},
        status_getter=_unexpected("status_get"),
        effects={
            "deliverer": _unexpected("delivery"),
            "receipt_persister": _unexpected("receipt"),
            "charger": _unexpected("charge"),
            "terminal_reporter": _unexpected("report"),
        },
    )
    assert result["blocker"] == "product_video_poll_recovery_disabled"
    assert result["provider_submit_calls"] == 0
    assert result["provider_status_get_calls"] == 0
    assert result["wallet_mutations"] == 0
    assert result["production_telegram_deliveries"] == 0


@pytest.mark.parametrize(
    ("field", "value", "blocker"),
    (
        ("product_family", "summary_video", "recovery_product_mismatch"),
        ("mode", "multi_scene", "recovery_mode_mismatch"),
        ("scene_count", 2, "one_scene_required"),
    ),
)
def test_29d_rejects_cross_product_or_multiscene_checkpoint(
    tmp_path: Path,
    field: str,
    value,
    blocker: str,
) -> None:
    store = _store(tmp_path)
    checkpoint = _persist(store)
    checkpoint[field] = value
    store.save(checkpoint)
    result = _recover(store)
    assert result["blocker"] == blocker
    assert result["provider_status_get_calls"] == 0


@pytest.mark.parametrize("state", ("NOT_SUBMITTED", "SUBMITTING"))
def test_29d_before_provider_accept_never_polls_or_creates_replacement(
    tmp_path: Path,
    state: str,
) -> None:
    store = _store(tmp_path)
    _persist(store, record=_record(provider_state=state, provider_task_id=""))
    result = _recover(store, expected_provider_task_id="")
    assert result["blocker"] == "provider_task_not_accepted"
    assert result["provider_submit_calls"] == 0
    assert result["provider_status_get_calls"] == 0


def test_29d_acceptance_unknown_is_manual_and_never_polled(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _persist(store, record=_record(provider_state="ACCEPTANCE_UNKNOWN"))
    result = _recover(store)
    assert result["blocker"] == "provider_acceptance_unknown_manual_review"
    assert result["provider_status_get_calls"] == 0


def test_29d_worker_sha_mismatch_blocks_before_lease_or_poll(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _persist(store)
    result = _recover(store, actual_worker_sha="different-worker-sha")
    assert result["blocker"] == "worker_sha_mismatch"
    assert result["provider_status_get_calls"] == 0
    assert not store.lease_path("p29d-fixture-job").exists()


def test_29d_missing_or_stale_provider_identity_never_polls(tmp_path: Path) -> None:
    missing_store = recovery.ProductVideoPollRecoveryStore(tmp_path / "missing")
    _persist(missing_store, record=_record(provider_task_id=""))
    missing = _recover(missing_store, expected_provider_task_id="")
    assert missing["blocker"] == "provider_task_id_missing"

    stale_store = recovery.ProductVideoPollRecoveryStore(tmp_path / "stale")
    _persist(stale_store)
    stale = _recover(stale_store, expected_provider_task_id="old-task-id")
    assert stale["blocker"] == "stale_recovery_identity"
    assert stale["provider_status_get_calls"] == 0


def test_29d_accepted_job_polls_same_task_once_and_persists_due_interval(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    _persist(store)
    payloads: list[dict] = []

    def status_get(payload: dict) -> dict:
        payloads.append(payload)
        return {
            "provider": "fake_provider",
            "provider_task_id": "fixture-task-29d",
            "state": "RUNNING",
        }

    first = _recover(store, status_getter=status_get)
    second = _recover(store, status_getter=_unexpected("duplicate_poll"), now_epoch=NOW + 1)
    assert first["outcome"] == "waiting_provider"
    assert first["provider_state"] == "RUNNING"
    assert payloads == [
        {
            "method": "GET",
            "provider": "fake_provider",
            "provider_task_id": "fixture-task-29d",
            "job_id": "p29d-fixture-job",
        }
    ]
    assert second["blocker"] == "provider_poll_not_due"
    assert second["provider_status_get_calls"] == 1
    assert second["provider_submit_calls"] == 0


def test_29d_provider_response_cannot_switch_task_or_provider(tmp_path: Path) -> None:
    for suffix, response, blocker in (
        (
            "task",
            {"provider": "fake_provider", "provider_task_id": "other-task", "state": "RUNNING"},
            "provider_task_identity_mismatch",
        ),
        (
            "provider",
            {"provider": "other_provider", "provider_task_id": "fixture-task-29d", "state": "RUNNING"},
            "provider_identity_mismatch",
        ),
    ):
        store = recovery.ProductVideoPollRecoveryStore(tmp_path / suffix)
        _persist(store)
        result = _recover(store, status_getter=lambda _payload, response=response: response)
        assert result["blocker"] == blocker
        assert result["provider_submit_calls"] == 0


def test_29d_unknown_provider_task_is_terminal_no_charge(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _persist(store)

    def missing(_payload: dict):
        raise recovery.ProviderTaskUnknown("fixture 404")

    result = _recover(store, status_getter=missing)
    assert result["blocker"] == "provider_task_unknown"
    assert result["terminal_state"] == "failed_no_charge"
    assert result["wallet_mutations"] == 0


def test_29d_provider_failure_is_terminal_without_delivery_or_charge(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _persist(store)
    result = _recover(
        store,
        status_getter=lambda _payload: {
            "provider": "fake_provider",
            "provider_task_id": "fixture-task-29d",
            "state": "FAILED",
        },
    )
    assert result["blocker"] == "provider_failed"
    assert result["terminal_state"] == "failed_no_charge"
    assert result["delivery_calls"] == 0
    assert result["charge_calls"] == 0


def test_29d_active_lease_blocks_and_stale_lease_is_recovered(tmp_path: Path) -> None:
    active_store = recovery.ProductVideoPollRecoveryStore(tmp_path / "active")
    _persist(active_store)
    active_store.lease_path("p29d-fixture-job").write_text(
        json.dumps({"owner": "other-worker", "token": "active", "expires_at_epoch": NOW + 60}),
        encoding="utf-8",
    )
    active = _recover(active_store)
    assert active["blocker"] == "recovery_lease_active"

    stale_store = recovery.ProductVideoPollRecoveryStore(tmp_path / "stale")
    _persist(stale_store)
    stale_store.lease_path("p29d-fixture-job").write_text(
        json.dumps({"owner": "dead-worker", "token": "stale", "expires_at_epoch": NOW - 1}),
        encoding="utf-8",
    )
    stale = _recover(
        stale_store,
        status_getter=lambda _payload: {
            "provider": "fake_provider",
            "provider_task_id": "fixture-task-29d",
            "state": "RUNNING",
        },
    )
    assert stale["outcome"] == "waiting_provider"
    assert stale["stale_lease_recovered"] is True
    assert not stale_store.lease_path("p29d-fixture-job").exists()


def test_29d_rechecks_checkpoint_identity_after_acquiring_lease(tmp_path: Path) -> None:
    class SwappedCheckpointStore(recovery.ProductVideoPollRecoveryStore):
        load_count = 0

        def load(self, job_id: str) -> dict:
            checkpoint = super().load(job_id)
            self.load_count += 1
            if self.load_count == 2:
                checkpoint["expected_worker_sha"] = "sha-swapped-after-precheck"
            return checkpoint

    store = SwappedCheckpointStore(tmp_path / "durable-recovery")
    _persist(store)
    result = _recover(store, status_getter=_unexpected("poll_after_checkpoint_swap"))
    assert result["blocker"] == "worker_sha_mismatch"
    assert result["provider_status_get_calls"] == 0


def test_29d_completed_fixture_validates_and_finalizes_exactly_once(tmp_path: Path) -> None:
    artifact = _render_legal_mp4(tmp_path / "fixture")
    store = _store(tmp_path)
    _persist(store)
    status_calls: list[str] = []
    side_effects: list[str] = []

    def status_get(payload: dict) -> dict:
        status_calls.append(payload["provider_task_id"])
        return {
            "provider": "fake_provider",
            "provider_task_id": "fixture-task-29d",
            "state": "COMPLETED",
            "artifact_path": str(artifact),
        }

    first = _recover(store, status_getter=status_get, effects=_effects(side_effects))
    second = _recover(
        store,
        status_getter=_unexpected("terminal_poll"),
        effects={
            "deliverer": _unexpected("duplicate_delivery"),
            "receipt_persister": _unexpected("duplicate_receipt"),
            "charger": _unexpected("duplicate_charge"),
            "terminal_reporter": _unexpected("duplicate_report"),
        },
    )
    assert first["ok"] is True
    assert first["terminal_state"] == "final_delivered"
    assert second["ok"] is True
    assert second["idempotent_replay"] is True
    assert status_calls == ["fixture-task-29d"]
    assert side_effects == ["delivery", "receipt", "charge", "report"]
    assert first["provider_submit_calls"] == 0
    assert first["fixture_provider_calls"] == 1
    assert first["real_provider_calls"] == 0
    assert first["paid_provider_calls"] == 0
    assert first["wallet_mutations"] == 0
    assert first["production_telegram_deliveries"] == 0
    assert first["delivery_calls"] == 1
    assert first["receipt_calls"] == 1
    assert first["charge_calls"] == 1
    assert first["terminal_report_calls"] == 1


@pytest.mark.parametrize(
    ("completed_stage", "expected_calls"),
    (
        ("validation", ["delivery", "receipt", "charge", "report"]),
        ("delivery", ["receipt", "charge", "report"]),
        ("receipt", ["charge", "report"]),
        ("charge", ["report"]),
        ("report", []),
    ),
)
def test_29d_restart_resumes_after_each_completed_stage_without_replay(
    tmp_path: Path,
    completed_stage: str,
    expected_calls: list[str],
) -> None:
    artifact = tmp_path / completed_stage / "validated.mp4"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"persisted-valid-artifact" * 400)
    store = recovery.ProductVideoPollRecoveryStore(tmp_path / f"store-{completed_stage}")
    checkpoint = _mark_validated(store, _persist(store), artifact)
    digest = checkpoint["stage_fingerprints"]["artifact_validated"]
    if completed_stage in {"delivery", "receipt", "charge", "report"}:
        checkpoint["delivery"] = {
            "state": "ACCEPTED",
            "accepted": True,
            "message_id": "fixture-message-29d",
            "production": False,
            "idempotency_key": f"delivery:p29d-fixture-job:{digest}",
        }
    if completed_stage in {"receipt", "charge", "report"}:
        checkpoint["receipt"] = {
            "state": "PERSISTED",
            "persisted": True,
            "receipt_id": "fixture-receipt-29d",
        }
    if completed_stage in {"charge", "report"}:
        checkpoint["charge"] = {
            "state": "RECORDED",
            "recorded": True,
            "ok": True,
            "amount_xu": 0,
            "wallet_mutated": False,
        }
    if completed_stage == "report":
        checkpoint["terminal_report"] = {
            "state": "EMITTED",
            "emitted": True,
            "report_id": "fixture-report-29d",
        }
        checkpoint["terminal_state"] = "final_delivered"
    store.save(checkpoint)
    calls: list[str] = []
    result = _recover(
        store,
        status_getter=_unexpected("poll_after_completed"),
        artifact_validator=_unexpected("revalidate_fingerprinted_artifact"),
        effects=_effects(calls),
    )
    assert result["ok"] is True
    assert calls == expected_calls
    assert result["provider_submit_calls"] == 0


def test_29d_delivery_acceptance_unknown_never_auto_resends(tmp_path: Path) -> None:
    artifact = tmp_path / "validated.mp4"
    artifact.write_bytes(b"persisted-valid-artifact" * 400)
    store = _store(tmp_path)
    checkpoint = _mark_validated(store, _persist(store), artifact)
    checkpoint["delivery"] = {
        "state": "ACCEPTANCE_UNKNOWN",
        "accepted": False,
        "idempotency_key": "delivery:p29d-fixture-job:unknown",
    }
    store.save(checkpoint)
    result = _recover(
        store,
        status_getter=_unexpected("poll"),
        artifact_validator=_unexpected("validator"),
        effects={
            "deliverer": _unexpected("resend"),
            "receipt_persister": _unexpected("receipt"),
            "charger": _unexpected("charge"),
            "terminal_reporter": _unexpected("report"),
        },
    )
    assert result["blocker"] == "delivery_acceptance_unknown"
    assert result["delivery_calls"] == 0


def test_29d_delivery_timeout_persists_unknown_and_restart_does_not_resend(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "validated.mp4"
    artifact.write_bytes(b"persisted-valid-artifact" * 400)
    store = _store(tmp_path)
    _mark_validated(store, _persist(store), artifact)
    calls: list[str] = []

    def ambiguous(_payload: dict):
        calls.append("delivery")
        raise TimeoutError("response lost after send")

    first = _recover(
        store,
        status_getter=_unexpected("poll"),
        artifact_validator=_unexpected("validator"),
        effects={
            "deliverer": ambiguous,
            "receipt_persister": _unexpected("receipt"),
            "charger": _unexpected("charge"),
            "terminal_reporter": _unexpected("report"),
        },
    )
    second = _recover(
        store,
        status_getter=_unexpected("poll"),
        artifact_validator=_unexpected("validator"),
        effects={
            "deliverer": _unexpected("resend"),
            "receipt_persister": _unexpected("receipt"),
            "charger": _unexpected("charge"),
            "terminal_reporter": _unexpected("report"),
        },
    )
    assert first["blocker"] == "delivery_acceptance_unknown"
    assert second["blocker"] == "delivery_acceptance_unknown"
    assert calls == ["delivery"]


def test_29d_fetches_only_existing_completed_output_with_get_contract(tmp_path: Path) -> None:
    artifact = _render_legal_mp4(tmp_path / "remote-fixture")
    store = _store(tmp_path)
    _persist(store)
    fetches: list[dict] = []

    def fetch(payload: dict) -> dict:
        fetches.append(payload)
        shutil.copy2(artifact, payload["destination_path"])
        return {"ok": True, "artifact_path": payload["destination_path"]}

    result = _recover(
        store,
        status_getter=lambda _payload: {
            "provider": "fake_provider",
            "provider_task_id": "fixture-task-29d",
            "state": "COMPLETED",
            "artifact_url": "fixture://existing-task/result.mp4",
        },
        artifact_fetcher=fetch,
    )
    assert result["ok"] is True
    assert len(fetches) == 1
    assert fetches[0]["method"] == "GET"
    assert fetches[0]["provider_task_id"] == "fixture-task-29d"
    assert result["provider_submit_calls"] == 0
    assert result["artifact_fetch_calls"] == 1


def test_29d_invalid_completed_artifact_never_delivers_or_charges(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.mp4"
    invalid.write_bytes(b"not an mp4")
    store = _store(tmp_path)
    _persist(store)
    result = _recover(
        store,
        status_getter=lambda _payload: {
            "provider": "fake_provider",
            "provider_task_id": "fixture-task-29d",
            "state": "COMPLETED",
            "artifact_path": str(invalid),
        },
    )
    assert result["ok"] is False
    assert result["terminal_state"] == "failed_no_charge"
    assert result["delivery_calls"] == 0
    assert result["charge_calls"] == 0
    assert result["wallet_mutations"] == 0


def test_29d_validator_exception_fails_closed_before_delivery(tmp_path: Path) -> None:
    artifact = tmp_path / "provider-result.mp4"
    artifact.write_bytes(b"provider-output" * 400)
    store = _store(tmp_path)
    _persist(store)

    def broken_validator(*_args, **_kwargs):
        raise RuntimeError("fixture probe crashed")

    result = _recover(
        store,
        status_getter=lambda _payload: {
            "provider": "fake_provider",
            "provider_task_id": "fixture-task-29d",
            "state": "COMPLETED",
            "artifact_path": str(artifact),
        },
        artifact_validator=broken_validator,
    )
    assert result["ok"] is False
    assert result["blocker"] == "artifact_validation_failed"
    assert result["terminal_state"] == "failed_no_charge"
    assert result["delivery_calls"] == 0
    assert result["charge_calls"] == 0


def test_29d_status_timeout_is_persisted_and_does_not_spin(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _persist(store)
    calls: list[str] = []

    def unavailable(_payload: dict):
        calls.append("GET")
        raise TimeoutError("fixture timeout")

    first = _recover(store, status_getter=unavailable)
    second = _recover(store, status_getter=_unexpected("spin"), now_epoch=NOW + 1)
    assert first["blocker"] == "provider_status_unavailable"
    assert second["blocker"] == "provider_poll_not_due"
    assert calls == ["GET"]
    assert second["provider_status_get_calls"] == 1


def test_29d_corrupt_checkpoint_fails_closed_without_side_effects(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.checkpoint_path("p29d-fixture-job").write_text("{broken", encoding="utf-8")
    result = _recover(store)
    assert result["blocker"] == "recovery_checkpoint_invalid"
    assert result["provider_status_get_calls"] == 0


def test_29d_scope_is_transport_free_and_has_no_submit_fallback_ui_or_wallet() -> None:
    source = Path(recovery.__file__).read_text(encoding="utf-8")
    lowered = source.casefold()
    assert "requests." not in lowered
    assert "httpx" not in lowered
    assert "telegram.ext" not in lowered
    assert "send_video(" not in lowered
    assert "bot.py" not in lowered
    assert "deduct_xu" not in lowered
    assert "wallet." not in lowered
    assert "submitter" not in lowered
    assert "fallback_provider" not in lowered
    assert "os.o_creat | os.o_excl" in lowered
    assert "os.replace" in lowered
