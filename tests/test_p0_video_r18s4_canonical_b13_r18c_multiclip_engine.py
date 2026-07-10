from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from services import multiscene_video_pipeline as mvp
from services import video_project_queue as queue
from services import video_real_render_connector as connector


ROOT = Path(__file__).resolve().parents[1]


def _ffmpeg() -> str | None:
    return os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg")


def _make_clip(path: Path, *, scene_index: int, duration: float = 0.16) -> str:
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        pytest.skip("ffmpeg is required for the canonical multiscene smoke")
    colors = ["0x1E88E5", "0x43A047", "0xF4511E", "0x8E24AA", "0xFDD835", "0x00ACC1", "0xE53935", "0x3949AB"]
    result = mvp.safe_run_ffmpeg(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={colors[(scene_index - 1) % len(colors)]}:s=96x160:r=24:d={duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "30",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return mvp.ensure_video_output(str(path))


def _job(job_id: int, scene_count: int) -> dict:
    return {
        "id": job_id,
        "job_id": job_id,
        "user_id": 1818,
        "source": "product_video",
        "product_video": True,
        "product_type": "video_trend",
        "scene_count": scene_count,
        "scene_duration_seconds": 8,
        "expected_duration_seconds": scene_count * 8,
        "orchestration_mode": "per_scene_8s",
        "provider_orchestration_mode": "per_scene_8s",
        "render_pipeline_mode": "historical_multi_clip_concat",
        "render_mode": "real",
        "provider_call": True,
        "public_user": True,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "prompt": "A coherent product story with a clear opening, benefit, proof, and closing shot.",
        "original_user_prompt": "A coherent product story with a clear opening, benefit, proof, and closing shot.",
        "provider_order": ["fixture_video"],
        "user_visible_price_xu": 300,
        "persisted_quoted_price_xu": 300,
        "customer_charge_planned_xu": 300,
    }


def _success_payload(scene_index: int, path: str) -> dict:
    task_id = f"fixture-task-{scene_index}"
    return {
        "ok": True,
        "scene_index": scene_index,
        "scene_id": scene_index,
        "provider": "fixture_video",
        "selected_provider": "fixture_video",
        "provider_task_ids": [task_id],
        "provider_task_id_saved": True,
        "task_id_present": True,
        "submit_accepted": True,
        "provider_submit_called": True,
        "provider_poll_called": True,
        "status": "SUCCESS",
        "provider_status": "SUCCESS",
        "normalized_provider_status": "success",
        "result_url": f"fixture://scene/{scene_index}",
        "result_url_present": True,
        "provider_result_url_present": True,
        "output_path": path,
        "local_path": path,
        "output_bytes": os.path.getsize(path),
        "clip_valid": True,
        "validation_passed": True,
        "dispatch_attempted": True,
        "dispatch_attempts": 1,
        "scene_dispatch_idempotency_key": f"dispatch-{scene_index}",
        "scene_winner_task": task_id,
        "winning_task_id": task_id,
        "no_charge": True,
    }


def _pending_payload(scene_index: int) -> dict:
    task_id = f"fixture-task-{scene_index}"
    return {
        "ok": False,
        "scene_index": scene_index,
        "scene_id": scene_index,
        "provider": "fixture_video",
        "selected_provider": "fixture_video",
        "provider_task_ids": [task_id],
        "provider_task_id_saved": True,
        "task_id_present": True,
        "submit_accepted": True,
        "provider_submit_called": True,
        "status": "provider_running",
        "provider_status": "IN_PROGRESS",
        "normalized_provider_status": "running",
        "continue_polling": True,
        "provider_error": "provider_in_progress",
        "blocker": "provider_in_progress",
        "dispatch_attempted": True,
        "dispatch_attempts": 1,
        "scene_dispatch_idempotency_key": f"dispatch-{scene_index}",
        "no_charge": True,
    }


@pytest.mark.parametrize("scene_count", [2, 4, 8])
def test_local_smoke_and_mocked_provider_e2e_produce_ordered_8s_scene_final(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scene_count: int,
):
    monkeypatch.setenv("MULTISCENE_VIDEO_TEMP_ROOT", str(tmp_path / f"root-{scene_count}"))
    calls: list[int] = []

    async def fake_provider(scene, raw_path, _provider_order):
        index = int(scene.scene_id)
        calls.append(index)
        output = _make_clip(Path(raw_path), scene_index=index)
        return _success_payload(index, output)

    monkeypatch.setattr(connector, "_render_scene_async", fake_provider)
    result = connector._run_per_scene_provider_orchestrator(
        _job(1800 + scene_count, scene_count),
        str(tmp_path / "disposable-worker-dir"),
        provider_order=["fixture_video"],
        provider_events=[],
        debug_results=[],
    )

    assert result["ok"] is True
    assert result["canonical_multiscene_engine"] == "b13_r18c"
    assert calls == list(range(1, scene_count + 1))
    assert result["scene_coverage_count"] == scene_count
    assert result["missing_scene_indexes"] == []
    assert result["concat_output_valid"] is True
    assert result["scene_order"] == list(range(1, scene_count + 1))
    assert Path(result["final_video_path"]).is_file()
    assert Path(result["final_video_path"]).stat().st_size > 0
    duration = mvp.probe_duration(result["final_video_path"])
    assert abs(duration - scene_count * 8) <= max(1.0, scene_count * 0.2)
    assert len(set(result["raw_scene_paths"])) == scene_count
    assert len(set(result["normalized_scene_paths"])) == scene_count
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["required_scene_indexes"] == list(range(1, scene_count + 1))
    assert manifest["scene_order"] == list(range(1, scene_count + 1))
    assert manifest["concat_state"] == "completed"
    assert manifest["delivery_state"] == "pending"
    assert manifest["charge_state"] == "pending"
    concat_lines = (Path(result["master_video_path"]).parent / "concat_scenes.txt").read_text(encoding="utf-8").splitlines()
    assert [f"scene_{index:03d}_normalized.mp4" in concat_lines[index - 1] for index in range(1, scene_count + 1)] == [True] * scene_count


def test_partial_coverage_persists_tasks_but_never_concats_delivers_or_charges(tmp_path, monkeypatch):
    monkeypatch.setenv("MULTISCENE_VIDEO_TEMP_ROOT", str(tmp_path / "partial-root"))

    async def partial_provider(scene, raw_path, _provider_order):
        index = int(scene.scene_id)
        if index == 1:
            return _success_payload(index, _make_clip(Path(raw_path), scene_index=index))
        raise connector.RealVideoRenderError("provider_in_progress", diagnostics=_pending_payload(index))

    monkeypatch.setattr(connector, "_render_scene_async", partial_provider)
    result = connector._run_per_scene_provider_orchestrator(
        _job(1819, 2),
        str(tmp_path / "discarded"),
        provider_order=["fixture_video"],
        provider_events=[],
        debug_results=[],
    )

    assert result["ok"] is False
    assert result["continue_polling"] is True
    assert result["scene_coverage_count"] == 1
    assert result["missing_scene_indexes"] == [2]
    assert result["concat_attempted"] is False
    assert result["final_mp4_valid"] is False
    assert result["final_delivered"] is False
    assert result["no_charge"] is True
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["task_ids_by_scene"]["1"] == ["fixture-task-1"]
    assert manifest["task_ids_by_scene"]["2"] == ["fixture-task-2"]
    assert manifest["concat_state"] != "completed"


def test_restart_recovers_completed_clips_and_runs_only_unresolved_scenes(tmp_path, monkeypatch):
    monkeypatch.setenv("MULTISCENE_VIDEO_TEMP_ROOT", str(tmp_path / "restart-root"))
    first_calls: list[int] = []

    async def first_worker(scene, raw_path, _provider_order):
        index = int(scene.scene_id)
        first_calls.append(index)
        if index <= 2:
            return _success_payload(index, _make_clip(Path(raw_path), scene_index=index))
        raise connector.RealVideoRenderError("provider_in_progress", diagnostics=_pending_payload(index))

    monkeypatch.setattr(connector, "_render_scene_async", first_worker)
    first = connector._run_per_scene_provider_orchestrator(
        _job(1824, 4),
        str(tmp_path / "first-disposable"),
        provider_order=["fixture_video"],
        provider_events=[],
        debug_results=[],
    )
    assert first["scene_coverage_count"] == 2
    assert first["concat_attempted"] is False

    resumed_calls: list[int] = []

    async def resumed_worker(scene, raw_path, _provider_order):
        index = int(scene.scene_id)
        resumed_calls.append(index)
        recovered = connector.product_video_scene_task_for_index(getattr(scene, "_toan_aas_job", {}), index)
        assert recovered["provider_task_id"] == f"fixture-task-{index}"
        return _success_payload(index, _make_clip(Path(raw_path), scene_index=index))

    monkeypatch.setattr(connector, "_render_scene_async", resumed_worker)
    resumed = connector._run_per_scene_provider_orchestrator(
        _job(1824, 4),
        str(tmp_path / "second-disposable"),
        provider_order=["fixture_video"],
        provider_events=[],
        debug_results=[],
    )

    assert first_calls == [1, 2, 3, 4]
    assert resumed_calls == [3, 4]
    assert resumed["manifest_recovered"] is True
    assert resumed["scene_coverage_count"] == 4
    assert resumed["concat_output_valid"] is True
    manifest = json.loads(Path(resumed["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["dispatch_attempts_by_scene"] == {"1": 1, "2": 1, "3": 1, "4": 1}


def test_failed_scene_retry_isolated_to_that_scene(tmp_path, monkeypatch):
    monkeypatch.setenv("MULTISCENE_VIDEO_TEMP_ROOT", str(tmp_path / "retry-root"))
    job = _job(1825, 4)
    workspace = connector._canonical_product_video_workspace(job)
    plan = connector.real_video_scene_plan(job)
    manifest = mvp.load_multiscene_manifest(workspace, job_id="1825", user_id="1818")
    existing_paths = {
        index: _make_clip(Path(workspace) / f"persisted-{index}.mp4", scene_index=index)
        for index in (1, 2, 4)
    }
    mvp.sync_multiscene_manifest(
        manifest,
        scene_specs=plan["scenes"],
        scene_tasks=[
            _success_payload(index, path) for index, path in existing_paths.items()
        ] + [{"scene_index": 3, "status": "failed", "retry_count": 1, "error": "fixture_failed"}],
        scene_clip_paths=existing_paths,
        status="waiting_for_scene_clips",
    )
    calls: list[int] = []

    async def retry_worker(scene, raw_path, _provider_order):
        index = int(scene.scene_id)
        calls.append(index)
        return _success_payload(index, _make_clip(Path(raw_path), scene_index=index))

    monkeypatch.setattr(connector, "_render_scene_async", retry_worker)
    result = connector._run_per_scene_provider_orchestrator(
        job,
        str(tmp_path / "retry-disposable"),
        provider_order=["fixture_video"],
        provider_events=[],
        debug_results=[],
    )

    assert calls == [3]
    assert result["scene_coverage_count"] == 4
    assert result["concat_output_valid"] is True


def test_manifest_final_is_reused_without_duplicate_concat(tmp_path, monkeypatch):
    monkeypatch.setenv("MULTISCENE_VIDEO_TEMP_ROOT", str(tmp_path / "reuse-root"))
    calls: list[int] = []

    async def fake_provider(scene, raw_path, _provider_order):
        index = int(scene.scene_id)
        calls.append(index)
        return _success_payload(index, _make_clip(Path(raw_path), scene_index=index))

    monkeypatch.setattr(connector, "_render_scene_async", fake_provider)
    job = _job(1826, 2)
    first = connector._run_per_scene_provider_orchestrator(
        job,
        str(tmp_path / "first"),
        provider_order=["fixture_video"],
        provider_events=[],
        debug_results=[],
    )
    second = connector._run_per_scene_provider_orchestrator(
        job,
        str(tmp_path / "second"),
        provider_order=["fixture_video"],
        provider_events=[],
        debug_results=[],
    )

    assert calls == [1, 2]
    assert second["final_video_path"] == first["final_video_path"]
    assert second["final_reused_from_manifest"] is True
    assert second["concat_attempted"] is False


def test_delivery_failure_is_no_charge_and_success_charge_is_idempotent(tmp_path):
    final_path = _make_clip(tmp_path / "final.mp4", scene_index=1)
    project = {
        "invoice_json": json.dumps(
            {
                "user_visible_price_xu": 300,
                "persisted_quoted_price_xu": 300,
                "customer_charge_planned_xu": 300,
            }
        ),
    }
    job = {"id": 1827, "job_id": 1827, "scene_count": 2}
    final_result = {
        "job_id": 1827,
        "scene_count": 2,
        "scene_coverage_count": 2,
        "scene_coverage_valid": True,
        "scene_coverage_valid_bool": True,
        "concat_attempted": True,
        "concat_output_valid": True,
        "final_video_path": final_path,
        "final_mp4_valid": True,
        "final_delivered": False,
        "scene_tasks": [
            {"scene_index": 1, "status": "clip_downloaded", "clip_valid": True, "clip_path": final_path},
            {"scene_index": 2, "status": "clip_downloaded", "clip_valid": True, "clip_path": final_path},
        ],
    }

    failed_delivery = queue.product_video_delivery_charge_decision(project, job, final_result)
    delivered = queue.product_video_delivery_charge_decision(project, job, {**final_result, "final_delivered": True})
    duplicate = queue.product_video_delivery_charge_decision(
        project,
        job,
        {
            **final_result,
            "final_delivered": True,
            "wallet_charge_recorded": True,
            "charge_tx_id": "fixture-charge",
            "charged_xu": 300,
        },
    )

    assert failed_delivery["ok"] is False
    assert failed_delivery["amount_xu"] == 0
    assert failed_delivery["charge_skip_reason"] == "delivery_required_before_charge"
    assert delivered["ok"] is True
    assert delivered["amount_xu"] == 300
    assert duplicate["ok"] is True
    assert duplicate["already_charged"] is True
    assert duplicate["amount_xu"] == 300


def test_cleanup_removes_only_workspace_after_final_was_preserved(tmp_path, monkeypatch):
    monkeypatch.setenv("MULTISCENE_VIDEO_TEMP_ROOT", str(tmp_path / "cleanup-root"))
    workspace = mvp.create_multiscene_workspace("cleanup-r18s4")
    final_inside = _make_clip(Path(workspace) / "final_output.mp4", scene_index=1)
    preserved = tmp_path / "canonical-delivered.mp4"
    shutil.copyfile(final_inside, preserved)

    mvp.cleanup_multiscene_workspace(workspace)

    assert not Path(workspace).exists()
    assert preserved.is_file()
    assert preserved.stat().st_size > 0


def test_r18s4_contains_no_real_provider_or_public_intermediate_delivery_calls():
    source = Path(__file__).read_text(encoding="utf-8")
    connector_source = (ROOT / "services" / "video_real_render_connector.py").read_text(encoding="utf-8")
    assert "finalize_multiscene_scene_clips(" in connector_source
    assert "_cached_scene_renderer" not in connector_source
    for forbidden in (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "video_provider" + "_smoke",
        "send_intermediate" + "_scene_clip",
    ):
        assert forbidden not in source
