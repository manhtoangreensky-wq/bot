from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import wave
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from services import product_video_one_scene_engine as one_scene
from services import video_engine_contract


RUNTIME_SHA = "518532bc9ecf9c3819a150859ff8587382be1c37"


def _enabled_flags(**overrides: str) -> dict[str, str]:
    values = {
        "PRODUCT_VIDEO_ONE_SCENE_ENGINE_ENABLED": "1",
        "PRODUCT_VIDEO_ONE_SCENE_PUBLIC_ALLOWED": "0",
        "PRODUCT_VIDEO_ONE_SCENE_REAL_PROVIDER_ENABLED": "0",
        "PRODUCT_VIDEO_ONE_SCENE_AUTO_RETRY": "0",
        "PRODUCT_VIDEO_ONE_SCENE_AUTO_FALLBACK": "0",
    }
    values.update(overrides)
    return values


def _prompt() -> one_scene.ProductVideoPromptContract:
    return one_scene.compile_product_video_prompt(
        original_user_prompt="Quay chai nuoc Aurora tren ban da, anh sang ban mai.",
        product_name="Aurora",
        required_visual_attributes=("chai thuy tinh trong", "nhan xanh la"),
        forbidden_claims=("khong tuyen bo chua benh",),
        language="vi",
        aspect_ratio="9:16",
        duration_seconds=2,
        scene_count=1,
    )


def _addons(**overrides: dict) -> tuple[one_scene.ProductVideoAddonState, ...]:
    values = {
        name: {
            "requested": False,
            "approved": False,
            "supported": name in {"subtitle", "logo"},
            "required": False,
            "materialized": False,
            "handoff_status": "not_requested",
            "blocker_reason": "",
            "artifact_path": "",
            "artifact_kind": "",
        }
        for name in one_scene.ADDON_NAMES
    }
    values.update(overrides)
    return one_scene.normalize_product_video_addons(values)


def _manifest(**overrides) -> dict:
    values = video_engine_contract.build_worker_manifest(
        worker_sha=RUNTIME_SHA,
        worker_instance_id="fixture-worker-29c",
        supported_products=["product_video"],
        supported_modes=["single_scene"],
        renderer_name="fixture-real-mp4",
        renderer_version="1",
        ffmpeg_version="6.1",
        provider_enabled=True,
        local_enabled=False,
        queue_ready=True,
        worker_connected=True,
        heartbeat_fresh=True,
        health_ok=True,
        worker_status="healthy",
        capabilities=list(one_scene.REQUIRED_WORKER_CAPABILITIES),
        provider_availability={"fake_provider": True, "paid_provider": True},
    )
    values.update(
        {
            "artifact_ready": True,
            "engine_adapters": [one_scene.ENGINE_ADAPTER],
            "provider_routes": ["fake_provider", "paid_provider"],
            "offline_fixture": True,
        }
    )
    values.update(overrides)
    return values


def _request(
    *,
    provider: str = "fake_provider",
    prompt: one_scene.ProductVideoPromptContract | None = None,
    addons: tuple[one_scene.ProductVideoAddonState, ...] | None = None,
    scene_count: int = 1,
    admin_no_charge: bool = True,
) -> video_engine_contract.VideoEngineRequest:
    return one_scene.build_product_video_one_scene_request(
        user_id=172203,
        confirmation_id="confirm-29c",
        language="vi",
        prompt_contract=prompt or _prompt(),
        addons=addons or _addons(),
        input_assets=("fixture-product-reference",),
        aspect_ratio="9:16",
        duration_seconds=2,
        audio_policy={"enabled": False, "promised": False},
        voice_policy={"enabled": False, "promised": False},
        provider_selection=provider,
        explicit_confirmation_receipt={"confirmation_id": "confirm-29c"},
        runtime_sha=RUNTIME_SHA,
        expected_worker_sha=RUNTIME_SHA,
        scene_count=scene_count,
        admin_no_charge=admin_no_charge,
    )


def _write_ppm_sequence(root: Path, *, frames: int = 16, moving: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    width, height = 160, 96
    for index in range(frames):
        x0 = 15 + (index * 5 if moving else 0)
        rows = bytearray()
        for y in range(height):
            for x in range(width):
                base = (
                    (x * 13 + y * 7) % 256,
                    (x * 5 + y * 17) % 256,
                    (x * 19 + y * 3) % 256,
                )
                if x0 <= x < x0 + 28 and 28 <= y < 68:
                    base = (32, 190, 112)
                rows.extend(bytes(min(255, item) for item in base))
        (root / f"frame_{index:03d}.ppm").write_bytes(
            f"P6\n{width} {height}\n255\n".encode("ascii") + bytes(rows)
        )
    return root


def _write_wav(path: Path, *, seconds: float = 2.0, frequency: float = 440.0) -> Path:
    sample_rate = 16000
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        samples = bytearray()
        for index in range(int(sample_rate * seconds)):
            value = int(12000 * math.sin(2 * math.pi * frequency * index / sample_rate))
            samples.extend(int(value).to_bytes(2, byteorder="little", signed=True))
        stream.writeframes(bytes(samples))
    return path


def _render_fixture_mp4(
    root: Path,
    *,
    moving: bool = True,
    with_audio: bool = False,
) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is required for the zero-cost 29C rehearsal")
    frames = _write_ppm_sequence(root / "frames", moving=moving)
    output = root / "fixture.mp4"
    command = [
        ffmpeg,
        "-y",
        "-v",
        "error",
        "-framerate",
        "8",
        "-i",
        str(frames / "frame_%03d.ppm"),
    ]
    if with_audio:
        audio = _write_wav(root / "audio.wav")
        command.extend(["-i", str(audio), "-shortest"])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
        ]
    )
    if with_audio:
        command.extend(["-c:a", "aac"])
    command.append(str(output))
    completed = subprocess.run(command, capture_output=True, text=True, timeout=90)
    assert completed.returncode == 0, completed.stderr
    return output


def test_29c_flags_are_default_off_and_product_route_stays_profile_only() -> None:
    assert one_scene.product_video_one_scene_flags({}) == {
        name: False for name in one_scene.FEATURE_FLAG_DEFAULTS
    }
    route = video_engine_contract.product_route_contract("product_video")
    assert route["state"] == "PROFILE_ONLY"
    assert route["connected"] is False


def test_29c_enabled_route_is_independent_and_single_scene_only() -> None:
    route = video_engine_contract.product_route_contract(
        "product_video", environ=_enabled_flags()
    )
    assert route == one_scene.shared_product_video_one_scene_route()
    assert route["connected"] is True
    assert route["supported_modes"] == ("single_scene",)
    assert "multi_scene" not in route["supported_modes"]
    assert route["worker_owner"] == "owner_product_video"


def test_29c_product_contract_declares_required_truth_boundaries() -> None:
    contract = one_scene.product_video_one_scene_contract(_enabled_flags())
    assert contract["route_id"] == "product_video_one_scene_v1"
    assert contract["product_family"] == "product_video"
    assert contract["mode"] == "one_scene"
    assert contract["engine_adapter"] == one_scene.ENGINE_ADAPTER
    assert contract["provider_requirements"]["explicit_route"] is True
    assert contract["artifact_promise"]["container"] == "mp4"
    assert contract["delivery_billing_contract"] == (
        "validate_mp4",
        "delivery_accepted",
        "receipt_persisted",
        "charge_once",
        "terminal_report_once",
    )


def test_29c_request_uses_29b_contract_and_persists_both_prompt_hashes() -> None:
    prompt = _prompt()
    request = _request(prompt=prompt)
    assert request.product_type is video_engine_contract.VideoProduct.PRODUCT_VIDEO
    assert request.mode is video_engine_contract.VideoEngineMode.SINGLE_SCENE
    assert request.payload["original_user_prompt"] == prompt.original_user_prompt
    assert request.payload["compiled_engine_prompt"] == prompt.compiled_engine_prompt
    assert request.payload["original_prompt_sha256"] == prompt.original_prompt_sha256
    assert request.payload["compiled_prompt_sha256"] == prompt.compiled_prompt_sha256
    assert request.approved_plan["scene_count"] == 1
    assert request.explicit_confirmation_receipt["confirmation_id"] == request.confirmation_id


def test_29c_default_off_dispatch_has_zero_side_effects() -> None:
    calls: list[str] = []
    ledger = one_scene.ProductVideoOneSceneLedger()
    result = one_scene.dispatch_product_video_one_scene(
        _request(),
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        prompt_contract=_prompt(),
        addons=_addons(),
        environ={},
        ledger=ledger,
        submitter=lambda _payload: calls.append("provider"),
    )
    assert result["blocker"] == "one_scene_engine_disabled"
    assert result["job_count"] == 0
    assert result["provider_submit_intents"] == 0
    assert result["offline_provider_calls"] == 0
    assert result["paid_provider_calls"] == 0
    assert result["delivery_count"] == 0
    assert result["wallet_mutations"] == 0
    assert calls == []


def test_29c_prompt_contract_is_immutable_and_preserves_all_approved_facts() -> None:
    prompt = _prompt()
    assert one_scene.validate_product_video_prompt(prompt)["ok"] is True
    assert prompt.original_prompt_sha256 == hashlib.sha256(
        prompt.original_user_prompt.encode("utf-8")
    ).hexdigest()
    assert prompt.compiled_prompt_sha256 == hashlib.sha256(
        prompt.compiled_engine_prompt.encode("utf-8")
    ).hexdigest()
    for required in (
        prompt.product_name,
        *prompt.required_visual_attributes,
        *prompt.forbidden_claims,
        prompt.language,
        prompt.aspect_ratio,
        str(prompt.duration_seconds),
        "scene_count=1",
    ):
        assert required.casefold() in prompt.compiled_engine_prompt.casefold()
    with pytest.raises(FrozenInstanceError):
        prompt.original_user_prompt = "mutated"  # type: ignore[misc]


def test_29c_semantic_loss_blocks_before_provider_or_wallet() -> None:
    prompt = _prompt()
    lossy = replace(
        prompt,
        compiled_engine_prompt="Aurora, scene_count=1",
        compiled_prompt_sha256=hashlib.sha256(b"Aurora, scene_count=1").hexdigest(),
    )
    calls: list[str] = []
    result = one_scene.dispatch_product_video_one_scene(
        _request(prompt=lossy),
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        prompt_contract=lossy,
        addons=_addons(),
        environ=_enabled_flags(),
        ledger=one_scene.ProductVideoOneSceneLedger(),
        submitter=lambda _payload: calls.append("provider"),
    )
    assert result["submitted"] is False
    assert result["blocker"] == "compiled_prompt_semantic_loss"
    assert calls == []
    assert result["wallet_mutations"] == 0


@pytest.mark.parametrize(
    ("addon_name", "payload", "blocker"),
    (
        (
            "logo",
            {
                "requested": True,
                "approved": True,
                "supported": True,
                "required": True,
                "materialized": False,
                "handoff_status": "missing",
            },
            "addon_material_missing:logo",
        ),
        (
            "voice",
            {
                "requested": True,
                "approved": True,
                "supported": False,
                "required": False,
                "materialized": False,
                "handoff_status": "blocked",
            },
            "addon_unsupported:voice",
        ),
        (
            "music",
            {
                "requested": True,
                "approved": True,
                "supported": True,
                "required": False,
                "materialized": True,
                "handoff_status": "ready",
                "artifact_path": "fixture-sine-220hz.wav",
                "artifact_kind": "sine_220hz",
            },
            "music_material_not_valid_music",
        ),
    ),
)
def test_29c_addons_fail_truthfully_without_silent_drop(
    addon_name: str, payload: dict, blocker: str
) -> None:
    addons = _addons(**{addon_name: payload})
    decision = one_scene.validate_product_video_addons(addons)
    assert decision["ok"] is False
    assert decision["blocker"] == blocker


def test_29c_materialized_logo_has_explicit_handoff() -> None:
    addons = _addons(
        logo={
            "requested": True,
            "approved": True,
            "supported": True,
            "required": True,
            "materialized": True,
            "handoff_status": "ready",
            "artifact_path": "legal-logo.png",
            "artifact_kind": "image",
        }
    )
    assert one_scene.validate_product_video_addons(addons)["ok"] is True


@pytest.mark.parametrize(
    ("manifest_patch", "flags_patch", "public_request", "blocker"),
    (
        ({"worker_sha": "f" * 40}, {}, False, "worker_sha_mismatch"),
        ({"heartbeat_fresh": False}, {}, False, "worker_heartbeat_stale"),
        ({"queue_ready": False}, {}, False, "worker_queue_not_ready"),
        ({"artifact_ready": False}, {}, False, "worker_artifact_not_ready"),
        ({"engine_adapters": []}, {}, False, "worker_adapter_missing"),
        ({"provider_routes": []}, {}, False, "explicit_provider_route_missing"),
        ({"supported_products": ()}, {}, False, "worker_product_unsupported"),
        ({"supported_modes": ()}, {}, False, "worker_mode_unsupported"),
        ({}, {"PRODUCT_VIDEO_ONE_SCENE_ENGINE_ENABLED": "0"}, False, "one_scene_engine_disabled"),
        ({}, {"PRODUCT_VIDEO_ONE_SCENE_PUBLIC_ALLOWED": "0"}, True, "one_scene_public_disabled"),
        ({}, {"PRODUCT_VIDEO_ONE_SCENE_AUTO_RETRY": "1"}, False, "automatic_retry_forbidden"),
        ({}, {"PRODUCT_VIDEO_ONE_SCENE_AUTO_FALLBACK": "1"}, False, "automatic_fallback_forbidden"),
    ),
)
def test_29c_worker_and_feature_gates_fail_closed(
    manifest_patch: dict,
    flags_patch: dict,
    public_request: bool,
    blocker: str,
) -> None:
    manifest = _manifest(**manifest_patch)
    flags = _enabled_flags(**flags_patch)
    decision = one_scene.product_video_one_scene_readiness(
        _request(),
        manifest=manifest,
        runtime_sha=RUNTIME_SHA,
        prompt_contract=_prompt(),
        addons=_addons(),
        environ=flags,
        public_request=public_request,
    )
    assert decision["ready"] is False
    assert decision["blocker"] == blocker


def test_29c_paid_provider_requires_a_separate_real_provider_flag() -> None:
    decision = one_scene.product_video_one_scene_readiness(
        _request(provider="paid_provider"),
        manifest=_manifest(offline_fixture=False),
        runtime_sha=RUNTIME_SHA,
        prompt_contract=_prompt(),
        addons=_addons(),
        environ=_enabled_flags(),
    )
    assert decision["ready"] is False
    assert decision["blocker"] == "real_provider_disabled"


def test_29c_multi_scene_is_rejected_without_job_or_submit() -> None:
    calls: list[str] = []
    result = one_scene.dispatch_product_video_one_scene(
        _request(scene_count=2),
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        prompt_contract=_prompt(),
        addons=_addons(),
        environ=_enabled_flags(),
        ledger=one_scene.ProductVideoOneSceneLedger(),
        submitter=lambda _payload: calls.append("provider"),
    )
    assert result["submitted"] is False
    assert result["blocker"] == "one_scene_required"
    assert result["job_count"] == 0
    assert calls == []


def test_29c_double_confirmation_and_restart_reuse_one_job_and_submit_intent() -> None:
    ledger = one_scene.ProductVideoOneSceneLedger()
    calls: list[dict] = []

    def submitter(payload: dict) -> dict:
        calls.append(payload)
        return {
            "state": "ACCEPTED",
            "provider_task_id": "fake-task-29c",
            "provider": "fake_provider",
            "paid": False,
            "scene_count": 1,
        }

    kwargs = {
        "manifest": _manifest(),
        "runtime_sha": RUNTIME_SHA,
        "prompt_contract": _prompt(),
        "addons": _addons(),
        "environ": _enabled_flags(),
        "ledger": ledger,
        "submitter": submitter,
    }
    first = one_scene.dispatch_product_video_one_scene(_request(), **kwargs)
    second = one_scene.dispatch_product_video_one_scene(_request(), **kwargs)
    assert first["submitted"] is True
    assert second["submitted"] is False
    assert second["idempotent_replay"] is True
    assert first["job_id"] == second["job_id"]
    assert len(ledger.jobs_by_idempotency) == 1
    assert ledger.provider_submit_intents == 1
    assert len(calls) == 1


def test_29c_acceptance_unknown_never_auto_resubmits() -> None:
    ledger = one_scene.ProductVideoOneSceneLedger()
    calls: list[str] = []

    def ambiguous(_payload: dict) -> dict:
        calls.append("submit")
        raise one_scene.ProviderAcceptanceUnknown("timeout_after_submit")

    kwargs = {
        "manifest": _manifest(),
        "runtime_sha": RUNTIME_SHA,
        "prompt_contract": _prompt(),
        "addons": _addons(),
        "environ": _enabled_flags(),
        "ledger": ledger,
        "submitter": ambiguous,
    }
    first = one_scene.dispatch_product_video_one_scene(_request(), **kwargs)
    second = one_scene.dispatch_product_video_one_scene(_request(), **kwargs)
    assert first["provider_state"] == "ACCEPTANCE_UNKNOWN"
    assert second["provider_state"] == "ACCEPTANCE_UNKNOWN"
    assert second["submitted"] is False
    assert len(calls) == 1
    assert ledger.provider_submit_intents == 1
    assert ledger.offline_provider_calls == 1


@pytest.mark.parametrize("returned_state", ("FAILED", "NOT_SUBMITTED"))
def test_29c_failed_or_ambiguous_submit_never_becomes_success_or_resubmits(
    returned_state: str,
) -> None:
    ledger = one_scene.ProductVideoOneSceneLedger()
    calls: list[str] = []

    def submitter(_payload: dict) -> dict:
        calls.append("submit")
        return {
            "state": returned_state,
            "provider_task_id": "" if returned_state == "NOT_SUBMITTED" else "failed-task",
            "provider": "fake_provider",
            "paid": False,
            "scene_count": 1,
        }

    kwargs = {
        "manifest": _manifest(),
        "runtime_sha": RUNTIME_SHA,
        "prompt_contract": _prompt(),
        "addons": _addons(),
        "environ": _enabled_flags(),
        "ledger": ledger,
        "submitter": submitter,
    }
    first = one_scene.dispatch_product_video_one_scene(_request(), **kwargs)
    second = one_scene.dispatch_product_video_one_scene(_request(), **kwargs)
    assert first["ok"] is False
    assert first["terminal_state"] in {"failed_no_charge", ""}
    assert first["provider_state"] in {"FAILED", "ACCEPTANCE_UNKNOWN"}
    assert second["submitted"] is False
    assert second["idempotent_replay"] is True
    assert calls == ["submit"]


def test_29c_artifact_validation_rejects_placeholder_static_and_missing_audio(
    tmp_path: Path,
) -> None:
    moving = _render_fixture_mp4(tmp_path / "moving", moving=True)
    static = _render_fixture_mp4(tmp_path / "static", moving=False)
    placeholder = one_scene.validate_product_video_one_scene_artifact(
        str(moving),
        expected_duration_seconds=2,
        motion_promised=True,
        audio_promised=False,
        result={"renderer": "test_pattern"},
    )
    static_result = one_scene.validate_product_video_one_scene_artifact(
        str(static),
        expected_duration_seconds=2,
        motion_promised=True,
        audio_promised=False,
        result={"renderer": "fake_provider_fixture", "visual_classification": "final_ai_video"},
    )
    no_audio = one_scene.validate_product_video_one_scene_artifact(
        str(moving),
        expected_duration_seconds=2,
        motion_promised=True,
        audio_promised=True,
        result={"renderer": "fake_provider_fixture", "visual_classification": "final_ai_video"},
    )
    assert placeholder["reason"] == "placeholder_not_final_video"
    assert static_result["reason"] == "motion_promised_but_static"
    assert no_audio["reason"] == "output_no_audio_stream"


def test_29c_non_silent_approved_audio_and_motion_are_measured_from_mp4(
    tmp_path: Path,
) -> None:
    artifact = _render_fixture_mp4(tmp_path / "audio", moving=True, with_audio=True)
    validation = one_scene.validate_product_video_one_scene_artifact(
        str(artifact),
        expected_duration_seconds=2,
        motion_promised=True,
        audio_promised=True,
        result={"renderer": "fake_provider_fixture", "visual_classification": "final_ai_video"},
    )
    assert validation["ok"] is True
    assert validation["full_decode"] is True
    assert validation["motion_valid"] is True
    assert validation["unique_frames"] > 1
    assert validation["has_audio"] is True
    assert validation["audio_non_silent"] is True
    assert validation["bytes"] >= one_scene.MINIMUM_ARTIFACT_BYTES


def test_29c_local_legal_fixture_runs_full_receipt_charge_report_once(
    tmp_path: Path,
) -> None:
    artifact = _render_fixture_mp4(tmp_path / "provider", moving=True, with_audio=False)
    ledger = one_scene.ProductVideoOneSceneLedger()
    provider_calls: list[dict] = []
    delivery_calls: list[dict] = []
    receipt_calls: list[dict] = []
    charge_calls: list[dict] = []
    report_calls: list[dict] = []
    side_effect_order: list[str] = []

    def submitter(payload: dict) -> dict:
        provider_calls.append(payload)
        return {
            "state": "COMPLETED",
            "provider_task_id": "fixture-task-29c",
            "provider": "fake_provider",
            "paid": False,
            "scene_count": 1,
            "render_count": 1,
            "compose_count": 1,
            "artifact_path": str(artifact),
        }

    dispatched = one_scene.dispatch_product_video_one_scene(
        _request(),
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        prompt_contract=_prompt(),
        addons=_addons(),
        environ=_enabled_flags(),
        ledger=ledger,
        submitter=submitter,
    )

    def deliverer(payload: dict) -> dict:
        delivery_calls.append(payload)
        side_effect_order.append("delivery")
        return {"accepted": True, "message_id": "fixture-message-29c"}

    def persist_receipt(payload: dict) -> dict:
        receipt_calls.append(payload)
        side_effect_order.append("receipt")
        return {"persisted": True, "receipt_id": "fixture-receipt-29c"}

    def charge(payload: dict) -> dict:
        charge_calls.append(payload)
        side_effect_order.append("charge")
        return {"ok": True, "amount_xu": 0, "wallet_mutated": False, "tx_id": "admin-zero"}

    def report(payload: dict) -> dict:
        report_calls.append(payload)
        side_effect_order.append("report")
        return {"emitted": True, "report_id": "fixture-report-29c"}

    kwargs = {
        "ledger": ledger,
        "job_id": dispatched["job_id"],
        "expected_duration_seconds": 2,
        "motion_promised": True,
        "audio_promised": False,
        "deliverer": deliverer,
        "receipt_persister": persist_receipt,
        "charger": charge,
        "terminal_reporter": report,
        "evidence_dir": tmp_path / "evidence",
    }
    first = one_scene.finalize_product_video_one_scene(**kwargs)
    second = one_scene.finalize_product_video_one_scene(**kwargs)

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["idempotent_replay"] is True
    assert len(provider_calls) == 1
    assert len(delivery_calls) == 1
    assert len(receipt_calls) == 1
    assert len(charge_calls) == 1
    assert len(report_calls) == 1
    assert side_effect_order == ["delivery", "receipt", "charge", "report"]
    assert first["wallet_mutations"] == 0
    assert first["paid_provider_calls"] == 0
    assert first["production_telegram_deliveries"] == 0
    evidence = tmp_path / "evidence"
    for name in (
        "job_manifest.json",
        "scene_001_manifest.json",
        "final.mp4",
        "validation_report.json",
        "delivery_receipt.json",
        "terminal_report.json",
    ):
        assert (evidence / name).is_file(), name
    assert json.loads((evidence / "validation_report.json").read_text(encoding="utf-8"))["ok"] is True


def test_29c_invalid_mp4_never_delivers_charges_or_reports(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.mp4"
    invalid.write_bytes(b"not-an-mp4")
    ledger = one_scene.ProductVideoOneSceneLedger()
    dispatched = one_scene.dispatch_product_video_one_scene(
        _request(),
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        prompt_contract=_prompt(),
        addons=_addons(),
        environ=_enabled_flags(),
        ledger=ledger,
        submitter=lambda _payload: {
            "state": "COMPLETED",
            "provider_task_id": "fixture-invalid",
            "provider": "fake_provider",
            "paid": False,
            "scene_count": 1,
            "render_count": 1,
            "compose_count": 1,
            "artifact_path": str(invalid),
        },
    )
    calls: list[str] = []
    result = one_scene.finalize_product_video_one_scene(
        ledger=ledger,
        job_id=dispatched["job_id"],
        expected_duration_seconds=2,
        motion_promised=True,
        audio_promised=False,
        deliverer=lambda _payload: calls.append("delivery"),
        receipt_persister=lambda _payload: calls.append("receipt"),
        charger=lambda _payload: calls.append("charge"),
        terminal_reporter=lambda _payload: calls.append("report"),
        evidence_dir=tmp_path / "invalid-evidence",
    )
    assert result["ok"] is False
    assert result["terminal_state"] == "failed_no_charge"
    assert calls == []
    assert result["delivery_count"] == 0
    assert result["wallet_mutations"] == 0
    assert result["success_report_count"] == 0


def test_29c_scope_keeps_locked_ui_and_runtime_files_untouched() -> None:
    source = Path(one_scene.__file__).read_text(encoding="utf-8")
    assert "telegram.ext" not in source.casefold()
    assert "send_video(" not in source
    assert "requests.post" not in source
    assert "httpx" not in source
    assert "deduct_xu" not in source
    assert "wallet." not in source.casefold()
    assert "PRODUCT_VIDEO_ONE_SCENE_REAL_PROVIDER_ENABLED" in source
