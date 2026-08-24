from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import remote_worker_api
from services import video_provider_router as router
from services import video_real_render_connector as connector
from services.video_provider_base import (
    VideoArtifactResult,
    VideoGenerationRequest,
    VideoPollResult,
    VideoSubmitResult,
)
from services import multiscene_video_pipeline as mvp


JOB_ID = 901
PROVIDER = "shopaikey_video"


def _same_job_probation_result(scene_count: int = 2) -> dict:
    return {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "product_type": "video_ai_prompt",
        "engine_adapter": "text_to_video",
        "required_capability": "text_to_video_or_scene_video",
        "orchestration_mode": "per_scene_8s",
        "scene_count": scene_count,
        "admission_enforced": True,
        "admission_mode": "public_confirmed_probation",
        "worker_compatible": True,
        "worker_connected": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "probation_lock_clear": False,
        "probation_lock_clear_at_candidate_resolver": True,
        "probation_lock_owner_job": JOB_ID,
        "current_probation_job_id": JOB_ID,
        "current_job_matches_lock": True,
        "same_job_lock_reentry_allowed": True,
        "probation_lock_owned_by_other_job": False,
        "provider_eligibility_snapshot": {
            "provider_eligibility_snapshot_id": "job-901-admission",
            "configured_provider_keys": [PROVIDER],
            "contract_valid_provider_chain": [PROVIDER],
            "eligible_provider_keys": [PROVIDER],
        },
        "provider_eligibility_snapshot_id": "job-901-admission",
        "configured_provider_chain": [PROVIDER],
        "contract_valid_provider_chain": [PROVIDER],
        "preconfirm_candidate_keys": [PROVIDER],
        "runtime_candidate_keys": [PROVIDER],
        "provider_health_at_submit": {
            PROVIDER: {
                "route_ready": True,
                "live_healthy": False,
                "provider_health_state": "degraded",
                "provider_degraded_for_product_video_public": True,
            }
        },
        "selected_provider": PROVIDER,
        "selected_model": "veo3.1-fast",
        "charge_policy": "after_valid_mp4_delivery",
        "charge": 0,
        "charged_xu": 0,
    }


def _hydrated_worker_job(scene_count: int = 2) -> dict:
    result = _same_job_probation_result(scene_count)
    asset_pack = {
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "public_user_confirmed": True,
        "product_type": "video_ai_prompt",
        "engine_adapter": "text_to_video",
        "scene_count": scene_count,
        "submit_source": "public_user_final_confirm",
    }
    project = {
        "project_id": 801,
        "user_id": 701,
        "profile_id": "video_ai_prompt",
        "topic": "single and multiscene fixture",
        "ratio": "9:16",
        "scene_count": scene_count,
        "asset_pack_json": json.dumps(asset_pack),
        "invoice_json": json.dumps(
            {
                **asset_pack,
                "package_xu": 300,
                "user_visible_price_xu": 300,
                "persisted_quoted_price_xu": 300,
                "customer_charge_planned_xu": 300,
            }
        ),
        "addon_plan_json": "{}",
        "scene_cards_json": json.dumps(
            [
                {
                    "scene_index": index,
                    "video_prompt": f"Cinematic scene {index}",
                }
                for index in range(1, scene_count + 1)
            ]
        ),
    }
    return {
        "id": JOB_ID,
        "job_id": JOB_ID,
        "project_id": 801,
        "user_id": 701,
        "job_type": "video_render",
        "status": "processing",
        "result_json": json.dumps(result),
        "project": project,
        "scenes": [],
    }


def test_worker_payload_preserves_same_job_probation_authority():
    payload = remote_worker_api.build_worker_job_payload(_hydrated_worker_job())

    assert payload["admission_enforced"] is True
    assert payload["worker_compatible"] is True
    assert payload["probation_lock_clear_for_current_job"] is True
    assert payload["probation_lock_owner_job"] == JOB_ID
    assert payload["current_probation_job_id"] == JOB_ID
    assert payload["current_job_matches_lock"] is True
    assert payload["same_job_lock_reentry_allowed"] is True


def test_scene_request_forwards_same_job_probation_authority(monkeypatch, tmp_path):
    captured: dict = {}
    output = tmp_path / "provider-scene.mp4"
    output.write_bytes(b"fixture-mp4")

    def fake_generation(request, *, output_dir, environ):
        del output_dir, environ
        captured.update(request.metadata)
        return {
            "ok": True,
            "provider": PROVIDER,
            "output_path": str(output),
            "provider_task_ids": ["task-901-1"],
            "provider_task_id_saved": True,
            "provider_router_called": True,
        }

    monkeypatch.setattr(connector, "run_provider_generation", fake_generation)
    monkeypatch.setattr(connector, "ensure_video_output", lambda path: str(path))
    job = remote_worker_api.build_worker_job_payload(_hydrated_worker_job())
    scene = SimpleNamespace(
        scene_id=1,
        video_prompt="Cinematic scene 1",
        visual_prompt="Cinematic scene 1",
        aspect_ratio="9:16",
        target_duration_sec=8,
        _toan_aas_job=job,
    )

    asyncio.run(connector._render_scene_async(scene, str(tmp_path / "scene-1.mp4"), [PROVIDER]))

    assert captured["admission_enforced"] is True
    assert captured["worker_compatible"] is True
    assert captured["probation_lock_clear_for_current_job"] is True
    assert captured["probation_lock_owner_job"] == JOB_ID
    assert captured["current_job_id"] == JOB_ID
    assert captured["same_job_lock_reentry_allowed"] is True


class _PendingAdapter:
    provider_name = PROVIDER

    def __init__(self) -> None:
        self.submit_calls = 0
        self.poll_calls = 0

    def capabilities(self) -> dict:
        return {
            "provider": self.provider_name,
            "configured": True,
            "capabilities": ["text_to_video", "scene_video", "multi_scene_video"],
            "submit_url_configured": True,
            "poll_url_configured": True,
            "auth_configured": True,
            "provider_auth_value_present": True,
            "provider_model_present": True,
            "provider_payload_model": "veo3.1-fast",
        }

    def submit_video_job(self, request: VideoGenerationRequest) -> VideoSubmitResult:
        self.submit_calls += 1
        return VideoSubmitResult(
            ok=True,
            provider_name=self.provider_name,
            provider_task_id=f"task-{request.job_id}",
            provider_status="submitted",
            raw={"submit_http_status": 200},
        )

    def poll_video_job(self, provider_task_id: str) -> VideoPollResult:
        self.poll_calls += 1
        return VideoPollResult(
            ok=True,
            status="running",
            provider_name=self.provider_name,
            provider_task_id=provider_task_id,
            raw_status="IN_PROGRESS",
        )

    def materialize_result(self, result, job_id):
        raise AssertionError("pending task must not download")


def _provider_status() -> dict:
    return {
        "effective_provider_chain": [PROVIDER],
        "provider_chain": [PROVIDER],
        "providers": [
            {
                "provider": PROVIDER,
                "enabled": True,
                "configured": True,
                "credit_ok": True,
                "submit_url_configured": True,
                "poll_url_configured": True,
                "auth_configured": True,
                "model_present": True,
            }
        ],
    }


class _CompletedAdapter(_PendingAdapter):
    def __init__(self, source_path: Path, *, duration: float = 0.16) -> None:
        super().__init__()
        self.source_path = source_path
        self.duration = duration

    def poll_video_job(self, provider_task_id: str) -> VideoPollResult:
        self.poll_calls += 1
        return VideoPollResult(
            ok=True,
            status="succeeded",
            provider_name=self.provider_name,
            provider_task_id=provider_task_id,
            result_url="https://fixture.invalid/video.mp4",
            raw_status="SUCCEEDED",
        )

    def materialize_result(self, result, job_id):
        target = self.source_path.parent / f"materialized-{job_id}.mp4"
        target.write_bytes(self.source_path.read_bytes())
        return VideoArtifactResult(
            ok=True,
            local_path=str(target),
            bytes=target.stat().st_size,
            duration=self.duration,
            has_video_stream=True,
            has_audio_stream=False,
            content_type="video/mp4",
        )


def test_integrated_scene_router_creates_valid_one_scene_mp4_without_network(
    monkeypatch,
    tmp_path,
):
    source = tmp_path / "provider-fixture.mp4"
    ffmpeg = connector.video_final_output.ffmpeg_path()
    if not ffmpeg:
        pytest.skip("ffmpeg is required for the integrated engine fixture")
    rendered = mvp.safe_run_ffmpeg(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x1E88E5:s=96x160:r=24:d=0.160",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        timeout=60,
    )
    assert rendered.returncode == 0, rendered.stderr
    adapter = _CompletedAdapter(source)
    monkeypatch.setattr(router, "provider_status_payload", lambda _env=None: _provider_status())
    monkeypatch.setattr(router, "load_video_provider_adapters", lambda _env=None: [adapter])
    monkeypatch.setattr(
        router,
        "provider_candidate_adapters",
        lambda _capability, _env, _status_payload: [adapter],
    )
    monkeypatch.setattr(
        router,
        "product_video_submit_switch_detail",
        lambda _env=None: {"resolved": True, "raw": "1", "source": "fixture"},
    )
    job = remote_worker_api.build_worker_job_payload(_hydrated_worker_job(scene_count=1))
    job["orchestration_mode"] = "per_scene_8s"
    scene = SimpleNamespace(
        scene_id=1,
        video_prompt="Cinematic scene 1",
        visual_prompt="Cinematic scene 1",
        aspect_ratio="9:16",
        target_duration_sec=8,
        _toan_aas_job=job,
    )

    result = asyncio.run(
        connector._render_scene_async(scene, str(tmp_path / "scene-1.mp4"), [PROVIDER])
    )

    assert adapter.submit_calls == 1
    assert adapter.poll_calls == 1
    assert result["provider_router_called"] is True
    assert result["provider_submit_called"] is True
    assert result["provider_task_id_saved"] is True
    output = Path(result["output_path"])
    assert output.is_file()
    assert output.stat().st_size > 0
    probe = connector.video_final_output.probe_video(str(output))
    assert probe["ok"] is True
    assert probe["has_video"] is True


@pytest.mark.parametrize("scene_count", [1, 2])
def test_integrated_product_render_outputs_one_or_multiscene_mp4_without_network(
    monkeypatch,
    tmp_path,
    scene_count,
):
    source = tmp_path / "provider-long-fixture.mp4"
    ffmpeg = connector.video_final_output.ffmpeg_path()
    if not ffmpeg:
        pytest.skip("ffmpeg is required for the integrated engine fixture")
    rendered = mvp.safe_run_ffmpeg(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x43A047:s=96x160:r=24:d=8.000",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        timeout=60,
    )
    assert rendered.returncode == 0, rendered.stderr
    adapter = _CompletedAdapter(source, duration=8)
    monkeypatch.setattr(
        connector,
        "real_video_provider_readiness",
        lambda *_args, **_kwargs: {
            "ok": True,
            "ready_provider_order": [PROVIDER],
            "configured_providers": [PROVIDER],
            "enabled_providers": [PROVIDER],
            "providers": _provider_status()["providers"],
        },
    )
    monkeypatch.setattr(router, "provider_status_payload", lambda _env=None: _provider_status())
    monkeypatch.setattr(router, "load_video_provider_adapters", lambda _env=None: [adapter])
    monkeypatch.setattr(
        router,
        "provider_candidate_adapters",
        lambda _capability, _env, _status_payload: [adapter],
    )
    monkeypatch.setattr(
        router,
        "product_video_submit_switch_detail",
        lambda _env=None: {"resolved": True, "raw": "1", "source": "fixture"},
    )
    monkeypatch.setenv("MULTISCENE_VIDEO_TEMP_ROOT", str(tmp_path / "canonical-root"))
    job = remote_worker_api.build_worker_job_payload(
        _hydrated_worker_job(scene_count=scene_count)
    )
    job.update(
        {
            "orchestration_mode": "per_scene_8s",
            "provider_orchestration_mode": "per_scene_8s",
            "render_pipeline_mode": "historical_multi_clip_concat",
            "scene_count": scene_count,
            "expected_duration_seconds": scene_count * 8,
        }
    )

    result = connector.render_real_video_job(job, str(tmp_path / "worker-disposable"))

    assert result["ok"] is True
    assert adapter.submit_calls == scene_count
    assert result["scene_tasks_completed"] == scene_count
    assert result["scene_coverage_valid_bool"] is True
    assert result["final_mp4_valid"] is True
    output = Path(result["final_video_path"])
    assert output.is_file()
    assert output.stat().st_size > 0
    validation = connector.video_final_output.validate_final_video_output(
        path=str(output),
        result=result,
    )
    assert validation["ok"] is True


def test_orchestrator_preserves_provider_audio_when_every_scene_has_audio(
    monkeypatch,
    tmp_path,
):
    probe_calls: list[str] = []
    captured: dict = {}

    async def fake_render(scene, raw_path, _provider_order):
        Path(raw_path).write_bytes(f"scene-{scene.scene_id}".encode("utf-8"))
        return {
            "ok": True,
            "output_path": raw_path,
            "scene_index": int(scene.scene_id),
            "result_url_present": True,
        }

    def fake_probe(path):
        probe_calls.append(str(path))
        return {
            "ok": True,
            "has_video": True,
            "has_audio": True,
            "bytes": Path(path).stat().st_size,
            "duration": 8.0,
        }

    final_path = tmp_path / "final-with-provider-audio.mp4"

    def fake_finalize(**kwargs):
        captured.update(kwargs)
        final_path.write_bytes(b"final-provider-audio")
        return {
            "ok": True,
            "final_video_path": str(final_path),
            "duration_sec": 16.0,
            "scene_order": [1, 2],
        }

    monkeypatch.setattr(connector, "_render_scene_async", fake_render)
    monkeypatch.setattr(
        connector,
        "_canonical_product_video_workspace",
        lambda _job: str(tmp_path / "provider-audio-workspace"),
    )
    monkeypatch.setattr(connector.video_final_output, "probe_video", fake_probe)
    monkeypatch.setattr(connector, "finalize_multiscene_scene_clips", fake_finalize)

    result = connector._run_per_scene_provider_orchestrator(
        {
            "id": 902,
            "job_id": 902,
            "source": "product_video",
            "product_video": True,
            "scene_count": 2,
            "orchestration_mode": "per_scene_8s",
            "public_user_confirmed": True,
            "invoice_confirmed": True,
        },
        str(tmp_path / "discarded-worker-dir"),
        provider_order=[PROVIDER],
        provider_events=[],
        debug_results=[],
    )

    assert result["ok"] is True
    assert len(probe_calls) == 2
    assert captured.get("preserve_scene_audio") is True


def test_same_job_probation_dispatches_provider_once(monkeypatch, tmp_path):
    adapter = _PendingAdapter()
    monkeypatch.setattr(router, "provider_status_payload", lambda _env=None: _provider_status())
    monkeypatch.setattr(router, "load_video_provider_adapters", lambda _env=None: [adapter])
    monkeypatch.setattr(
        router,
        "provider_candidate_adapters",
        lambda _capability, _env, _status_payload: [adapter],
    )
    monkeypatch.setattr(
        router,
        "product_video_submit_switch_detail",
        lambda _env=None: {"resolved": True, "raw": "1", "source": "fixture"},
    )
    metadata = _same_job_probation_result()
    metadata["current_job_id"] = JOB_ID
    metadata["probation_lock_clear_for_current_job"] = True
    request = VideoGenerationRequest(
        job_id=f"{JOB_ID}-1",
        product_type="video_ai_prompt",
        video_flow_type="video_ai_prompt",
        prompt="Cinematic scene 1",
        duration_seconds=8,
        required_capability="text_to_video_or_scene_video",
        metadata={**metadata, "allow_provider_pending": True},
    )

    result = router.run_provider_generation(
        request,
        output_dir=str(tmp_path),
        environ={
            "PRODUCT_VIDEO_PROVIDER_SUBMIT_ENABLED": "1",
            "VIDEO_PROVIDER_MAX_POLL_ATTEMPTS": "1",
            "VIDEO_PROVIDER_POLL_INTERVAL_SECONDS": "0",
            "REAL_PROVIDER_SMOKE_ENABLED": "1",
        },
        sleep_func=lambda _seconds: None,
    )

    assert adapter.submit_calls == 1
    assert adapter.poll_calls == 1
    assert result["provider_router_called"] is True
    assert result["provider_submit_called"] is True
    assert result["provider_task_id_saved"] is True
    assert result["continue_polling"] is True
    assert result["no_charge"] is True


@pytest.mark.parametrize("scene_count", [1, 2])
def test_orchestrator_dispatches_every_scene_once_without_premature_terminal(
    monkeypatch,
    tmp_path,
    scene_count,
):
    calls: list[str] = []

    def pending_generation(request, *, output_dir, environ):
        del output_dir, environ
        calls.append(str(request.job_id))
        return {
            "ok": False,
            "provider": PROVIDER,
            "selected_provider": PROVIDER,
            "provider_router_called": True,
            "provider_submit_called": True,
            "provider_task_ids": [f"task-{request.job_id}"],
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

    monkeypatch.setattr(connector, "run_provider_generation", pending_generation)
    monkeypatch.setattr(
        connector,
        "_canonical_product_video_workspace",
        lambda _job: str(tmp_path / f"job-{scene_count}"),
    )
    job = remote_worker_api.build_worker_job_payload(_hydrated_worker_job(scene_count))
    job["orchestration_mode"] = "per_scene_8s"
    result = connector._run_per_scene_provider_orchestrator(
        job,
        str(tmp_path / "discarded-worker-dir"),
        provider_order=[PROVIDER],
        provider_events=[],
        debug_results=[],
    )

    assert calls == [f"{JOB_ID}-{index}" for index in range(1, scene_count + 1)]
    assert result["scene_tasks_submitted"] == scene_count
    assert result["continue_polling"] is True
    assert result["terminal_state"] == "final_rendering"
    assert result["final_decision"] == "continue_polling"
    assert result["no_charge"] is True


def test_queued_scenes_are_not_terminal_before_dispatch_attempt():
    tasks = [
        {
            "scene_index": index,
            "status": "queued_waiting_for_dispatch",
            "dispatch_state": "queued_waiting_for_dispatch",
            "dispatch_attempted": False,
            "provider_submit_called": False,
        }
        for index in (1, 2)
    ]

    audit = connector.product_video_scene_execution_audit(
        {"job_id": JOB_ID, "scene_count": 2},
        tasks,
    )

    assert audit["missing_task_count"] == 2
    assert audit["terminal_reason"] == ""
    assert audit["continue_polling"] is True


def test_missing_task_after_real_submit_attempt_remains_terminal():
    audit = connector.product_video_scene_execution_audit(
        {"job_id": JOB_ID, "scene_count": 1},
        [
            {
                "scene_index": 1,
                "status": "failed",
                "dispatch_attempted": True,
                "provider_submit_called": True,
                "submit_accepted": False,
            }
        ],
    )

    assert audit["terminal_reason"] == "scene_submit_missing_no_charge"
    assert audit["continue_polling"] is False
