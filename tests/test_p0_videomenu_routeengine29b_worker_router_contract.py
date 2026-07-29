from __future__ import annotations

import inspect
from dataclasses import asdict, is_dataclass

import pytest

from services import video_engine_contract


FULL_SHA = "2622328872800abc08ec44372d49e05e8433618a"


def _manifest(**overrides):
    values = {
        "worker_sha": FULL_SHA,
        "worker_instance_id": "worker-generation-a",
        "supported_products": ["frame_video", "video_editing"],
        "supported_modes": ["multi_asset_edit", "single_asset_edit"],
        "renderer_name": "local_ffmpeg",
        "renderer_version": "1",
        "ffmpeg_version": "6.1.1",
        "provider_enabled": False,
        "local_enabled": True,
        "queue_ready": True,
        "worker_connected": True,
        "heartbeat_fresh": True,
        "health_ok": True,
        "worker_status": "healthy",
        "capabilities": ["frame_video_render", "video_edit"],
    }
    values.update(overrides)
    return video_engine_contract.build_worker_manifest(**values)


def _request(
    *,
    product: str = "frame_video",
    mode: str = "multi_asset_edit",
    confirmation_id: str = "confirm-29b",
):
    payload = {"asset_ids": ["image-1", "image-2"], "scene_count": 1}
    contract = {
        "user_id": 172203,
        "language": "vi",
        "approved_plan": {"scene_count": 1, "approved": True},
        "input_assets": ("image-1", "image-2"),
        "aspect_ratio": "16:9",
        "duration_profile": {"duration_seconds": 5, "profile": "standard"},
        "audio_policy": {"enabled": False},
        "voice_policy": {"enabled": False},
        "provider_selection": "local",
        "runtime_sha": FULL_SHA,
        "expected_worker_sha": FULL_SHA,
    }
    return video_engine_contract.VideoEngineRequest(
        request_id="request-29b",
        confirmation_id=confirmation_id,
        idempotency_key=video_engine_contract.stable_request_idempotency_key(
            confirmation_id=confirmation_id,
            product_type=product,
            mode=mode,
            payload=payload,
            **contract,
        ),
        product_type=product,
        mode=mode,
        explicit_confirmation_receipt={"confirmation_id": confirmation_id},
        confirmed=True,
        payload=payload,
        **contract,
    )


def test_29b_exact_product_and_mode_enums() -> None:
    assert {item.value for item in video_engine_contract.VideoProduct} == {
        "animated_video",
        "human_ai_video",
        "product_video",
        "summary_video",
        "podcast_video",
        "frame_video",
        "video_editing",
    }
    assert {item.value for item in video_engine_contract.VideoEngineMode} == {
        "single_scene",
        "multi_scene",
        "single_asset_edit",
        "multi_asset_edit",
    }


def test_29b_required_dataclasses_are_serializable_contract_values() -> None:
    request = _request()
    job = video_engine_contract.VideoEngineJob(
        job_id="frame-job-1",
        request_id=request.request_id,
        idempotency_key=request.idempotency_key,
        product_type=request.product_type,
        mode=request.mode,
        user_id=request.user_id,
        runtime_sha=request.runtime_sha,
        expected_worker_sha=request.expected_worker_sha,
        worker_job_type="frame_video_render",
        engine_route="frame_video_render",
        worker_owner="frame_video",
        status="queued",
    )
    result = video_engine_contract.VideoEngineResult(
        job_id=job.job_id,
        ok=True,
        status="completed",
        output_path="output.mp4",
        output_bytes=1024,
        mime_type="video/mp4",
    )
    receipt = video_engine_contract.VideoDeliveryReceipt(
        job_id=job.job_id,
        delivered=True,
        delivery_idempotency_key=f"delivery:{job.idempotency_key}",
        receipt_id="receipt-1",
        delivery_message_id="message-1",
        output_sha256="a" * 64,
        output_bytes=1024,
        delivered_at="2026-07-29T00:00:00Z",
    )

    assert all(is_dataclass(item) for item in (request, job, result, receipt))
    assert {
        "user_id",
        "product_type",
        "mode",
        "language",
        "approved_plan",
        "input_assets",
        "aspect_ratio",
        "duration_profile",
        "audio_policy",
        "voice_policy",
        "provider_selection",
        "explicit_confirmation_receipt",
        "idempotency_key",
        "runtime_sha",
        "expected_worker_sha",
    } <= set(asdict(request))
    assert asdict(request)["product_type"] == video_engine_contract.VideoProduct.FRAME_VIDEO
    assert "product" not in asdict(request)
    assert request.product == video_engine_contract.VideoProduct.FRAME_VIDEO
    assert asdict(job)["product_type"] == video_engine_contract.VideoProduct.FRAME_VIDEO
    assert asdict(request)["mode"] == video_engine_contract.VideoEngineMode.MULTI_ASSET_EDIT
    assert result.artifact_valid is True
    assert asdict(receipt)["delivered"] is True
    assert receipt.valid is True


def test_29b_route_inventory_uses_only_proven_independent_engine_routes() -> None:
    frame = video_engine_contract.product_route_contract("frame_video")
    editing = video_engine_contract.product_route_contract("video_editing")

    assert frame == {
        "product": "frame_video",
        "state": "CONNECTED",
        "connected": True,
        "public_product_type": "frame_video_local",
        "worker_job_type": "frame_video_render",
        "engine_route": "frame_video_render",
        "worker_owner": "frame_video",
        "required_capability": "frame_video_render",
        "supported_modes": ("multi_asset_edit",),
        "provider_enabled": False,
        "local_enabled": True,
        "blocker": "",
    }
    assert editing == {
        "product": "video_editing",
        "state": "CONNECTED",
        "connected": True,
        "public_product_type": "video_local_edit",
        "worker_job_type": "video_local_edit",
        "engine_route": "local_worker_ffmpeg",
        "worker_owner": "local_video_edit",
        "required_capability": "video_edit",
        "supported_modes": ("single_asset_edit", "multi_asset_edit"),
        "provider_enabled": False,
        "local_enabled": True,
        "blocker": "",
    }


@pytest.mark.parametrize(
    "product",
    (
        "animated_video",
        "human_ai_video",
        "product_video",
        "summary_video",
        "podcast_video",
    ),
)
def test_29b_profile_categories_never_claim_a_connected_engine(product: str) -> None:
    route = video_engine_contract.product_route_contract(product)
    assert route["state"] in {"PROFILE_ONLY", "ENGINE_MISSING"}
    assert route["connected"] is False
    assert route["engine_route"] == ""
    assert route["worker_job_type"] == ""
    assert route["supported_modes"] == ()
    assert route["blocker"] == "independent_product_contract_missing"


def test_29b_manifest_exposes_worker_renderer_flags_and_queue_truth() -> None:
    manifest = _manifest()
    assert {
        "worker_sha",
        "engine_contract_version",
        "supported_products",
        "supported_modes",
        "renderer_version",
        "ffmpeg_version",
        "provider_availability",
        "local_capabilities",
        "queue_ready",
    } <= set(manifest)
    assert manifest["contract_version"] == video_engine_contract.CONTRACT_VERSION
    assert manifest["worker_sha"] == FULL_SHA
    assert manifest["supported_products"] == ("frame_video", "video_editing")
    assert manifest["supported_modes"] == ("single_asset_edit", "multi_asset_edit")
    assert manifest["renderer_name"] == "local_ffmpeg"
    assert manifest["renderer_version"] == "1"
    assert manifest["ffmpeg_version"] == "6.1.1"
    assert manifest["provider_enabled"] is False
    assert manifest["local_enabled"] is True
    assert manifest["queue_ready"] is True
    assert manifest["health_ok"] is True
    assert manifest["worker_status"] == "healthy"


def test_29b_manifest_requires_explicit_health_and_status_truth() -> None:
    parameters = inspect.signature(video_engine_contract.build_worker_manifest).parameters
    assert parameters["health_ok"].default is inspect.Parameter.empty
    assert parameters["worker_status"].default is inspect.Parameter.empty


@pytest.mark.parametrize(
    ("overrides", "blocker"),
    (
        ({"worker_sha": "f" * 40}, "worker_sha_mismatch"),
        ({"capabilities": []}, "worker_capability_mismatch"),
        ({"queue_ready": False}, "worker_queue_not_ready"),
        ({"worker_connected": False}, "worker_disconnected"),
        ({"heartbeat_fresh": False}, "worker_heartbeat_stale"),
        ({"health_ok": False}, "worker_unhealthy"),
        ({"worker_status": "maintenance"}, "worker_status_not_ready"),
        ({"local_enabled": False}, "local_engine_disabled"),
        ({"supported_products": ["video_editing"]}, "worker_product_unsupported"),
        ({"supported_modes": ["single_asset_edit"]}, "worker_mode_unsupported"),
    ),
)
def test_29b_readiness_fails_closed_and_never_submits(overrides: dict, blocker: str) -> None:
    calls: list[object] = []

    decision = video_engine_contract.guarded_submit(
        _request(),
        manifest=_manifest(**overrides),
        runtime_sha=FULL_SHA,
        jobs_by_idempotency={},
        submitter=lambda request, route: calls.append((request, route)),
    )

    assert decision["submitted"] is False
    assert decision["submit_allowed"] is False
    assert decision["blocker"] == blocker
    assert calls == []


def test_29b_profile_only_remains_blocked_even_if_worker_advertises_it() -> None:
    calls: list[object] = []
    request = _request(product="animated_video", mode="single_scene")

    decision = video_engine_contract.guarded_submit(
        request,
        manifest=_manifest(
            supported_products=["animated_video"],
            supported_modes=["single_scene"],
            capabilities=["text_to_video"],
            provider_enabled=True,
        ),
        runtime_sha=FULL_SHA,
        jobs_by_idempotency={},
        submitter=lambda request, route: calls.append((request, route)),
    )

    assert decision["submitted"] is False
    assert decision["blocker"] == "independent_product_contract_missing"
    assert calls == []


def test_29b_confirmation_job_and_worker_restart_are_idempotent() -> None:
    request = _request()
    same_confirmation = _request()
    assert same_confirmation.idempotency_key == request.idempotency_key

    jobs: dict[str, video_engine_contract.VideoEngineJob] = {}
    calls: list[str] = []

    def submitter(item, route):
        calls.append(item.idempotency_key)
        return video_engine_contract.VideoEngineJob(
            job_id="frame-job-1",
            request_id=item.request_id,
            idempotency_key=item.idempotency_key,
            product_type=item.product_type,
            mode=item.mode,
            user_id=item.user_id,
            runtime_sha=item.runtime_sha,
            expected_worker_sha=item.expected_worker_sha,
            worker_job_type=route["worker_job_type"],
            engine_route=route["engine_route"],
            worker_owner=route["worker_owner"],
            status="queued",
        )

    first = video_engine_contract.guarded_submit(
        request,
        manifest=_manifest(worker_instance_id="worker-generation-a"),
        runtime_sha=FULL_SHA,
        jobs_by_idempotency=jobs,
        submitter=submitter,
    )
    after_restart = video_engine_contract.guarded_submit(
        same_confirmation,
        manifest=_manifest(worker_instance_id="worker-generation-b"),
        runtime_sha=FULL_SHA,
        jobs_by_idempotency=jobs,
        submitter=submitter,
    )

    assert first["submitted"] is True
    assert after_restart["submitted"] is False
    assert after_restart["idempotent_replay"] is True
    assert after_restart["job"].job_id == first["job"].job_id
    assert calls == [request.idempotency_key]


def test_29b_unconfirmed_request_is_a_zero_submit_health_guard() -> None:
    request = _request()
    request = video_engine_contract.VideoEngineRequest(
        request_id=request.request_id,
        confirmation_id=request.confirmation_id,
        idempotency_key=request.idempotency_key,
        product_type=request.product_type,
        mode=request.mode,
        user_id=request.user_id,
        language=request.language,
        approved_plan=request.approved_plan,
        input_assets=request.input_assets,
        aspect_ratio=request.aspect_ratio,
        duration_profile=request.duration_profile,
        audio_policy=request.audio_policy,
        voice_policy=request.voice_policy,
        provider_selection=request.provider_selection,
        explicit_confirmation_receipt=request.explicit_confirmation_receipt,
        runtime_sha=request.runtime_sha,
        expected_worker_sha=request.expected_worker_sha,
        confirmed=False,
        payload=request.payload,
    )
    calls: list[object] = []

    decision = video_engine_contract.guarded_submit(
        request,
        manifest=_manifest(),
        runtime_sha=FULL_SHA,
        jobs_by_idempotency={},
        submitter=lambda item, route: calls.append((item, route)),
    )

    assert decision["blocker"] == "confirmation_required"
    assert decision["submitted"] is False
    assert calls == []


def test_29b_request_rejects_an_idempotency_key_from_different_confirmation_payload() -> None:
    request = _request()
    with pytest.raises(ValueError, match="video_engine_idempotency_key_mismatch"):
        video_engine_contract.VideoEngineRequest(
            request_id=request.request_id,
            confirmation_id=request.confirmation_id,
            idempotency_key="not-the-stable-key",
            product_type=request.product_type,
            mode=request.mode,
            user_id=request.user_id,
            language=request.language,
            approved_plan=request.approved_plan,
            input_assets=request.input_assets,
            aspect_ratio=request.aspect_ratio,
            duration_profile=request.duration_profile,
            audio_policy=request.audio_policy,
            voice_policy=request.voice_policy,
            provider_selection=request.provider_selection,
            explicit_confirmation_receipt=request.explicit_confirmation_receipt,
            runtime_sha=request.runtime_sha,
            expected_worker_sha=request.expected_worker_sha,
            confirmed=True,
            payload=request.payload,
        )


def test_29b_existing_job_with_same_key_but_different_route_fails_closed() -> None:
    request = _request()
    existing = video_engine_contract.VideoEngineJob(
        job_id="wrong-route-job",
        request_id=request.request_id,
        idempotency_key=request.idempotency_key,
        product_type="video_editing",
        mode="multi_asset_edit",
        user_id=request.user_id,
        runtime_sha=request.runtime_sha,
        expected_worker_sha=request.expected_worker_sha,
        worker_job_type="video_local_edit",
        engine_route="local_worker_ffmpeg",
        worker_owner="local_video_edit",
        status="queued",
    )

    with pytest.raises(ValueError, match="video_engine_existing_job_request_mismatch"):
        video_engine_contract.guarded_submit(
            request,
            manifest=_manifest(),
            runtime_sha=FULL_SHA,
            jobs_by_idempotency={request.idempotency_key: existing},
            submitter=lambda item, route: pytest.fail("must not submit"),
        )


def test_29b_contract_version_mismatch_is_zero_submit() -> None:
    manifest = _manifest()
    manifest["engine_contract_version"] = "obsolete-contract"
    calls: list[object] = []

    decision = video_engine_contract.guarded_submit(
        _request(),
        manifest=manifest,
        runtime_sha=FULL_SHA,
        jobs_by_idempotency={},
        submitter=lambda item, route: calls.append((item, route)),
    )

    assert decision["blocker"] == "worker_contract_version_mismatch"
    assert decision["submitted"] is False
    assert calls == []


def test_29b_string_false_confirmation_and_health_flags_fail_closed() -> None:
    confirmed = _request()
    unconfirmed = video_engine_contract.VideoEngineRequest(
        request_id=confirmed.request_id,
        confirmation_id=confirmed.confirmation_id,
        idempotency_key=confirmed.idempotency_key,
        product_type=confirmed.product_type,
        mode=confirmed.mode,
        user_id=confirmed.user_id,
        language=confirmed.language,
        approved_plan=confirmed.approved_plan,
        input_assets=confirmed.input_assets,
        aspect_ratio=confirmed.aspect_ratio,
        duration_profile=confirmed.duration_profile,
        audio_policy=confirmed.audio_policy,
        voice_policy=confirmed.voice_policy,
        provider_selection=confirmed.provider_selection,
        explicit_confirmation_receipt=confirmed.explicit_confirmation_receipt,
        runtime_sha=confirmed.runtime_sha,
        expected_worker_sha=confirmed.expected_worker_sha,
        confirmed="false",  # type: ignore[arg-type]
        payload=confirmed.payload,
    )
    calls: list[object] = []

    confirmation_decision = video_engine_contract.guarded_submit(
        unconfirmed,
        manifest=_manifest(),
        runtime_sha=FULL_SHA,
        jobs_by_idempotency={},
        submitter=lambda item, route: calls.append((item, route)),
    )
    queue_decision = video_engine_contract.guarded_submit(
        confirmed,
        manifest=_manifest(queue_ready="false"),
        runtime_sha=FULL_SHA,
        jobs_by_idempotency={},
        submitter=lambda item, route: calls.append((item, route)),
    )

    assert confirmation_decision["blocker"] == "confirmation_required"
    assert queue_decision["blocker"] == "worker_queue_not_ready"
    assert calls == []


def test_29b_request_rejects_missing_required_execution_contract_fields() -> None:
    request = _request()

    with pytest.raises(ValueError, match="video_engine_user_id_required"):
        video_engine_contract.VideoEngineRequest(
            request_id=request.request_id,
            confirmation_id=request.confirmation_id,
            idempotency_key=request.idempotency_key,
            product_type=request.product_type,
            mode=request.mode,
            user_id=0,
            language=request.language,
            approved_plan=request.approved_plan,
            input_assets=request.input_assets,
            aspect_ratio=request.aspect_ratio,
            duration_profile=request.duration_profile,
            audio_policy=request.audio_policy,
            voice_policy=request.voice_policy,
            provider_selection=request.provider_selection,
            explicit_confirmation_receipt=request.explicit_confirmation_receipt,
            runtime_sha=request.runtime_sha,
            expected_worker_sha=request.expected_worker_sha,
            confirmed=True,
            payload=request.payload,
        )


def test_29b_manifest_exposes_exact_engine_contract_and_capability_flags() -> None:
    manifest = _manifest()

    assert manifest["engine_contract_version"] == video_engine_contract.CONTRACT_VERSION
    assert manifest["provider_availability"] == {}
    assert manifest["local_capabilities"] == {"video_edit": True, "frame_video_render": True}


def test_29b_confirmed_request_requires_an_explicit_confirmation_receipt() -> None:
    request = _request()

    with pytest.raises(ValueError, match="video_engine_confirmation_receipt_required"):
        video_engine_contract.VideoEngineRequest(
            request_id=request.request_id,
            confirmation_id=request.confirmation_id,
            idempotency_key=request.idempotency_key,
            product_type=request.product_type,
            mode=request.mode,
            confirmed=True,
            payload=request.payload,
            user_id=172203,
            language="vi",
            approved_plan={"scene_count": 1},
            input_assets=("image-1", "image-2"),
            aspect_ratio="16:9",
            duration_profile={"duration_seconds": 5},
            audio_policy={"enabled": False},
            voice_policy={"enabled": False},
            provider_selection="local",
            explicit_confirmation_receipt={},
            runtime_sha=FULL_SHA,
            expected_worker_sha=FULL_SHA,
        )


def test_29b_auto_product_or_provider_selection_is_rejected() -> None:
    request = _request()

    with pytest.raises(ValueError, match="video_engine_auto_selection_forbidden"):
        video_engine_contract.VideoEngineRequest(
            request_id=request.request_id,
            confirmation_id=request.confirmation_id,
            idempotency_key=request.idempotency_key,
            product_type=request.product_type,
            mode=request.mode,
            confirmed=False,
            payload=request.payload,
            user_id=172203,
            language="vi",
            approved_plan={"scene_count": 1},
            input_assets=("image-1", "image-2"),
            aspect_ratio="16:9",
            duration_profile={"duration_seconds": 5},
            audio_policy={"enabled": False},
            voice_policy={"enabled": False},
            provider_selection="auto_provider",
            explicit_confirmation_receipt={},
            runtime_sha=FULL_SHA,
            expected_worker_sha=FULL_SHA,
        )


def test_29b_confirmed_request_cannot_bypass_stable_confirmation_identity() -> None:
    request = _request()

    with pytest.raises(ValueError, match="video_engine_confirmation_id_required"):
        video_engine_contract.VideoEngineRequest(
            request_id=request.request_id,
            confirmation_id="",
            idempotency_key="arbitrary-key",
            product_type=request.product_type,
            mode=request.mode,
            user_id=request.user_id,
            language=request.language,
            approved_plan=request.approved_plan,
            input_assets=request.input_assets,
            aspect_ratio=request.aspect_ratio,
            duration_profile=request.duration_profile,
            audio_policy=request.audio_policy,
            voice_policy=request.voice_policy,
            provider_selection=request.provider_selection,
            explicit_confirmation_receipt={"confirmation_id": "receipt-without-owner"},
            runtime_sha=request.runtime_sha,
            expected_worker_sha=request.expected_worker_sha,
            confirmed=True,
            payload=request.payload,
        )


def test_29b_profile_only_existing_job_never_claims_an_engine_connection() -> None:
    request = _request(product="animated_video", mode="single_scene")
    existing = video_engine_contract.VideoEngineJob(
        job_id="legacy-profile-only-job",
        request_id=request.request_id,
        idempotency_key=request.idempotency_key,
        product_type=request.product_type,
        mode=request.mode,
        user_id=request.user_id,
        runtime_sha=request.runtime_sha,
        expected_worker_sha=request.expected_worker_sha,
        worker_job_type="",
        engine_route="",
        worker_owner="",
        status="queued",
    )

    decision = video_engine_contract.guarded_submit(
        request,
        manifest=_manifest(
            supported_products=["animated_video"],
            supported_modes=["single_scene"],
            capabilities=["text_to_video"],
        ),
        runtime_sha=FULL_SHA,
        jobs_by_idempotency={request.idempotency_key: existing},
        submitter=lambda item, route: pytest.fail("must not submit"),
    )

    assert decision["submitted"] is False
    assert decision["idempotent_replay"] is False
    assert decision["blocker"] == "independent_product_contract_missing"
    assert decision["job"] is None


def test_29b_malformed_capability_flags_fail_closed_without_submit() -> None:
    manifest = _manifest()
    manifest["local_capabilities"] = "false"
    calls: list[object] = []

    decision = video_engine_contract.guarded_submit(
        _request(),
        manifest=manifest,
        runtime_sha=FULL_SHA,
        jobs_by_idempotency={},
        submitter=lambda item, route: calls.append((item, route)),
    )

    assert decision["blocker"] == "local_capability_disabled"
    assert decision["submitted"] is False
    assert calls == []


def test_29b_worker_job_requires_the_originating_request_identity() -> None:
    request = _request()

    with pytest.raises(ValueError, match="video_engine_request_id_required"):
        video_engine_contract.VideoEngineJob(
            job_id="job-without-request",
            request_id="",
            idempotency_key=request.idempotency_key,
            product_type=request.product_type,
            mode=request.mode,
            user_id=request.user_id,
            runtime_sha=request.runtime_sha,
            expected_worker_sha=request.expected_worker_sha,
            worker_job_type="frame_video_render",
            engine_route="frame_video_render",
            worker_owner="frame_video",
            status="queued",
        )


def test_29b_result_without_job_identity_is_not_a_valid_artifact() -> None:
    result = video_engine_contract.VideoEngineResult(
        job_id="",
        ok=True,
        status="completed",
        output_path="output.mp4",
        output_bytes=1024,
        mime_type="video/mp4",
    )

    assert result.artifact_valid is False


def test_29b_delivery_receipt_without_job_identity_is_invalid() -> None:
    receipt = video_engine_contract.VideoDeliveryReceipt(
        job_id="",
        delivered=True,
        delivery_idempotency_key="delivery:missing-job",
        receipt_id="receipt-1",
        delivery_message_id="message-1",
        output_sha256="a" * 64,
        output_bytes=1024,
        delivered_at="2026-07-29T00:00:00Z",
    )

    assert receipt.valid is False


def test_29b_empty_approved_plan_is_rejected_before_dispatch() -> None:
    request = _request()

    with pytest.raises(ValueError, match="video_engine_approved_plan_required"):
        video_engine_contract.VideoEngineRequest(
            request_id=request.request_id,
            confirmation_id=request.confirmation_id,
            idempotency_key=request.idempotency_key,
            product_type=request.product_type,
            mode=request.mode,
            user_id=request.user_id,
            language=request.language,
            approved_plan={},
            input_assets=request.input_assets,
            aspect_ratio=request.aspect_ratio,
            duration_profile=request.duration_profile,
            audio_policy=request.audio_policy,
            voice_policy=request.voice_policy,
            provider_selection=request.provider_selection,
            explicit_confirmation_receipt=request.explicit_confirmation_receipt,
            runtime_sha=request.runtime_sha,
            expected_worker_sha=request.expected_worker_sha,
            confirmed=True,
            payload=request.payload,
        )


def test_29b_existing_job_with_different_idempotency_identity_is_rejected() -> None:
    request = _request()
    existing = video_engine_contract.VideoEngineJob(
        job_id="wrong-idempotency-job",
        request_id=request.request_id,
        idempotency_key="different-key",
        product_type=request.product_type,
        mode=request.mode,
        user_id=request.user_id,
        runtime_sha=request.runtime_sha,
        expected_worker_sha=request.expected_worker_sha,
        worker_job_type="frame_video_render",
        engine_route="frame_video_render",
        worker_owner="frame_video",
        status="queued",
    )

    with pytest.raises(ValueError, match="video_engine_existing_job_request_mismatch"):
        video_engine_contract.guarded_submit(
            request,
            manifest=_manifest(),
            runtime_sha=FULL_SHA,
            jobs_by_idempotency={request.idempotency_key: existing},
            submitter=lambda item, route: pytest.fail("must not submit"),
        )


def test_29b_runtime_sha_mismatch_is_zero_submit() -> None:
    calls: list[object] = []

    decision = video_engine_contract.guarded_submit(
        _request(),
        manifest=_manifest(),
        runtime_sha="f" * 40,
        jobs_by_idempotency={},
        submitter=lambda item, route: calls.append((item, route)),
    )

    assert decision["blocker"] == "runtime_sha_mismatch"
    assert decision["submitted"] is False
    assert calls == []
