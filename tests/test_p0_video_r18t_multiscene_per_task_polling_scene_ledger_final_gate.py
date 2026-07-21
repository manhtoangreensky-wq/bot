from __future__ import annotations

from pathlib import Path

from services import product_progress_status
from services import video_project_queue as queue
from services import video_real_render_connector as connector


ROOT = Path(__file__).resolve().parents[1]


def _job124_result() -> dict:
    return {
        "job_id": 124,
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "provider_order": "shopaikey_video,key4u_video",
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "progress_percent": 95,
        "canonical_scene_index": 2,
        "canonical_task_selected": "task-scene-2-YczE",
        "canonical_status": "succeeded",
        "canonical_result_url": "https://fixture.invalid/scene-2.mp4",
        "canonical_result_url_present": True,
        "provider_status": "succeeded",
        "normalized_provider_status": "succeeded",
        "result_url": "https://fixture.invalid/scene-2.mp4",
        "result_url_present": True,
        "provider_result_url_present": True,
        "output_bytes": 12_407_476,
        "concat_attempted": True,
        "concat_attempt_count": 1,
        "concat_duration_seconds": 8.0,
        "final_mp4_valid": False,
        "final_delivered": False,
        "charged_xu": 0,
        "scene_tasks": [
            {
                "scene_index": 1,
                "required": True,
                "provider": "shopaikey_video",
                "provider_task_id": "task-scene-1-p6fM",
                "active_task_id": "task-scene-1-p6fM",
                "status": "provider_running",
                "provider_status_raw": "IN_PROGRESS",
                "provider_progress_raw": "30",
                "provider_elapsed_seconds": 608,
                "started_at_epoch": 1_800_000_000,
                "continue_polling": True,
            },
            {
                "scene_index": 2,
                "required": True,
                "provider": "shopaikey_video",
                "provider_task_id": "task-scene-2-YczE",
                "active_task_id": "task-scene-2-YczE",
                "winning_task_id": "task-scene-2-YczE",
                "status": "scene_clip_validated",
                "provider_status_raw": "SUCCESS",
                "provider_progress_raw": "100",
                "result_url": "https://fixture.invalid/scene-2.mp4",
                "result_url_valid": True,
                "clip_valid": True,
                "clip_bytes": 12_407_476,
                "completed_at": "2026-07-10 12:00:00",
            },
        ],
        "scene_clip_validation_by_index": {
            "1": {"ok": False, "bytes": 0},
            "2": {"ok": True, "bytes": 12_407_476},
        },
        "scene_result_urls_by_index": {"1": "no", "2": "yes"},
    }


def test_job124_fixture_scene_ledger_is_authoritative():
    result = _job124_result()
    ledger = queue.product_video_scene_ledger_state(
        {"scene_count": 2},
        {"id": 124, "status": "processing", "progress_percent": 95},
        result,
    )

    assert ledger["required_scene_count"] == 2
    assert ledger["completed_scene_count"] == 1
    assert ledger["unresolved_scene_indexes"] == [1]
    assert ledger["scene_status_by_index"] == {"1": "provider_running", "2": "scene_clip_validated"}
    assert ledger["scene_active_task_by_index"]["1"] == "task-scene-1-p6fM"
    assert ledger["scene_winner_task_by_index"]["2"] == "task-scene-2-YczE"
    assert ledger["scene_clip_valid_by_index"] == {"1": False, "2": True}
    assert ledger["aggregate_job_status"] == "processing_partial_scene_success"
    assert ledger["provider_status"] == "processing"
    assert ledger["canonical_scope"] == "job_summary"
    assert ledger["canonical_does_not_imply_job_success"] is True
    assert ledger["unresolved_scenes_preserved"] is True


def test_job124_scene_clip_is_not_final_and_partial_progress_is_capped():
    result = _job124_result()
    telemetry = queue.reconcile_provider_progress_telemetry(
        {"id": 124, "status": "processing", "progress_percent": 95},
        result,
        refresh_source="r18t_job124_fixture",
    )

    assert telemetry["final_status_after_reconcile"] == "processing"
    assert telemetry["aggregate_job_status"] == "processing_partial_scene_success"
    assert telemetry["final_progress_after_reconcile"] <= 70
    assert telemetry["public_progress_cap"] == 70
    assert telemetry["progress_cap_correction"] is True
    assert telemetry["render_progress_source"] == "partial_scene_coverage"
    assert telemetry["final_mp4_valid"] is False
    assert telemetry["result_url_present"] is False
    assert telemetry["provider_result_url_present"] is False
    assert telemetry["final_delivered"] is False


def test_job124_public_panel_shows_one_of_two_without_technical_copy():
    result = _job124_result()
    telemetry = queue.reconcile_provider_progress_telemetry(
        {"id": 124, "status": "processing", "progress_percent": 95},
        result,
        refresh_source="r18t_public_panel",
    )
    text = product_progress_status.video_per_scene_progress_board_text({**result, **telemetry})

    assert "Cảnh 1/2: Đang tạo" in text
    assert "Cảnh 2/2: Đã xong" in text
    assert "Hoàn tất: 1/2 cảnh" in text
    assert "Ghép video: Chờ cảnh còn lại" in text
    assert "Gửi kết quả: Chưa bắt đầu" in text
    assert "Hệ thống sẽ tự kiểm tra lại sau 10 giây" in text
    for forbidden in ("ShopAIKey", "Key4U", "provider", "task-scene", "result_url", "artifact", "canonical"):
        assert forbidden.lower() not in text.lower()


def test_job124_partial_coverage_hard_blocks_concat_delivery_and_charge(tmp_path):
    result = _job124_result()
    result.update(
        {
            "final_video_path": str(tmp_path / "scene-only.mp4"),
            "final_mp4_valid": True,
            "final_delivered": True,
        }
    )
    Path(result["final_video_path"]).write_bytes(b"one-scene-only")

    coverage = queue.product_video_scene_coverage_state({"scene_count": 2}, {"id": 124}, result)
    charge = queue.product_video_delivery_charge_decision(
        {
            "scene_count": 2,
            "video_delivered_at": "2026-07-10 12:01:00",
            "invoice_json": queue._json_dumps(
                {
                    "scene_count": 2,
                    "user_visible_price_xu": 300,
                    "persisted_quoted_price_xu": 300,
                    "customer_charge_planned_xu": 300,
                }
            ),
        },
        {"id": 124},
        result,
    )

    assert coverage["scene_coverage_count"] == 1
    assert coverage["concat_ready"] is False
    assert coverage["concat_attempted"] is False
    assert coverage["concat_waiting_for_scene_coverage"] is True
    assert coverage["concat_duration_seconds"] == 0
    assert coverage["final_duration_coverage_reason"] == "waiting_for_required_scenes"
    assert coverage["final_mp4_valid"] is False
    assert coverage["final_delivered"] is False
    assert charge["ok"] is False
    assert charge["amount_xu"] == 0


def test_scene_task_mapping_survives_restart_and_input_reordering():
    first = _job124_result()
    second = {**first, "scene_tasks": list(reversed(first["scene_tasks"]))}

    before = queue.product_video_scene_ledger_state({"scene_count": 2}, {"id": 124}, first)
    after = queue.product_video_scene_ledger_state({"scene_count": 2}, {"id": 124}, second)

    assert before["scene_active_task_by_index"] == after["scene_active_task_by_index"]
    assert before["scene_winner_task_by_index"] == after["scene_winner_task_by_index"]
    assert after["task_scene_index_map"]["task-scene-1-p6fM"] == 1
    assert after["task_scene_index_map"]["task-scene-2-YczE"] == 2


def test_worker_orchestrator_polls_both_scenes_and_does_not_concat_partial(monkeypatch, tmp_path):
    calls: list[int] = []
    concat_calls: list[int] = []

    monkeypatch.setattr(
        connector,
        "real_video_scene_plan",
        lambda _job: {
            "scenes": [
                {"scene_id": 1, "video_prompt": "scene one", "aspect_ratio": "9:16"},
                {"scene_id": 2, "video_prompt": "scene two", "aspect_ratio": "9:16"},
            ]
        },
    )

    async def fake_render(scene, raw_path, _provider_order):
        scene_index = int(scene.scene_id)
        calls.append(scene_index)
        if scene_index == 1:
            raise connector.RealVideoRenderError(
                "provider_in_progress",
                diagnostics={
                    "scene_index": 1,
                    "provider": "shopaikey_video",
                    "provider_task_ids": ["task-scene-1-p6fM"],
                    "provider_status": "provider_running",
                    "provider_status_raw": "IN_PROGRESS",
                    "provider_progress_raw": "30",
                    "continue_polling": True,
                },
            )
        Path(raw_path).write_bytes(b"validated-scene-two")
        return {
            "ok": True,
            "scene_index": 2,
            "provider": "shopaikey_video",
            "task_id": "task-scene-2-YczE",
            "provider_task_ids": ["task-scene-2-YczE"],
            "status": "SUCCESS",
            "output_path": raw_path,
            "artifact_size": Path(raw_path).stat().st_size,
            "result_url_present": True,
            "result_url": "https://fixture.invalid/scene-2.mp4",
        }

    monkeypatch.setattr(connector, "_render_scene_async", fake_render)
    monkeypatch.setattr(connector, "_run_multiscene_render", lambda *_args, **_kwargs: concat_calls.append(1) or {})

    result = connector._run_per_scene_provider_orchestrator(
        {
            "id": 124,
            "job_id": 124,
            "source": "product_video",
            "product_video": True,
            "scene_count": 2,
            "orchestration_mode": "per_scene_8s",
            "provider_order": "shopaikey_video,key4u_video",
            "public_user_confirmed": True,
            "invoice_confirmed": True,
        },
        str(tmp_path),
        provider_order=["shopaikey_video", "key4u_video"],
        provider_events=[],
        debug_results=[],
    )

    assert calls == [1, 2]
    assert concat_calls == []
    assert result["completed_scene_count"] == 1
    assert result["unresolved_scene_indexes"] == [1]
    assert result["aggregate_job_status"] == "processing_partial_scene_success"
    assert result["concat_attempted"] is False
    assert result["concat_duration_seconds"] == 0
    assert result["final_mp4_valid"] is False
    assert result["continue_polling"] is True


def test_full_scene_coverage_invokes_concat_exactly_once(monkeypatch, tmp_path):
    concat_calls: list[int] = []
    monkeypatch.setattr(
        connector,
        "real_video_scene_plan",
        lambda _job: {
            "scenes": [
                {"scene_id": 1, "video_prompt": "scene one", "aspect_ratio": "9:16"},
                {"scene_id": 2, "video_prompt": "scene two", "aspect_ratio": "9:16"},
            ]
        },
    )

    async def fake_render(scene, raw_path, _provider_order):
        Path(raw_path).write_bytes(f"scene-{scene.scene_id}".encode())
        return {
            "ok": True,
            "scene_index": int(scene.scene_id),
            "provider": "shopaikey_video",
            "task_id": f"task-{scene.scene_id}",
            "provider_task_ids": [f"task-{scene.scene_id}"],
            "status": "SUCCESS",
            "output_path": raw_path,
            "artifact_size": Path(raw_path).stat().st_size,
            "result_url_present": True,
            "result_url": f"https://fixture.invalid/scene-{scene.scene_id}.mp4",
        }

    def fake_concat(**kwargs):
        concat_calls.append(1)
        final_path = Path(kwargs["workspace_dir"]) / "final.mp4"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(b"joined-scenes")
        return {"ok": True, "final_video_path": str(final_path), "duration_sec": 16.0, "scene_order": [1, 2]}

    monkeypatch.setattr(connector, "_render_scene_async", fake_render)
    monkeypatch.setattr(connector, "finalize_multiscene_scene_clips", fake_concat)

    result = connector._run_per_scene_provider_orchestrator(
        {
            "id": 125,
            "job_id": 125,
            "source": "product_video",
            "product_video": True,
            "scene_count": 2,
            "orchestration_mode": "per_scene_8s",
        },
        str(tmp_path),
        provider_order=["shopaikey_video"],
        provider_events=[],
        debug_results=[],
    )

    assert concat_calls == [1]
    assert result["scene_coverage_count"] == 2
    assert result["concat_attempted"] is True
    assert result["concat_attempt_count"] == 1
    assert result["concat_duration_seconds"] == 16.0
    assert result["final_mp4_valid"] is True
    assert result["aggregate_job_status"] == "ready_for_delivery"


def test_success_scene_is_not_fallback_eligible_but_remaining_stalled_scene_is(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER_IN_PROGRESS_STALL_SECONDS", "300")
    job = {
        "id": 124,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "provider_order": "shopaikey_video,key4u_video",
    }
    success = _job124_result()["scene_tasks"][1]
    stalled = {
        **_job124_result()["scene_tasks"][0],
        "provider_elapsed_seconds": 608,
        "provider_progress_last_changed_elapsed_seconds": 608,
    }

    success_policy = connector.product_video_scene_stall_policy(job, success, 2)
    stalled_policy = connector.product_video_scene_stall_policy(job, stalled, 1)

    assert success_policy["fallback_allowed"] is False
    assert success_policy["fallback_block_reason"] == "scene_already_has_valid_clip"
    assert stalled_policy["fallback_allowed"] is True
    assert stalled_policy["fallback_scene_index"] == 1


def test_debug_raw_status_source_enumerates_scene_tasks_without_submit():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    candidate_block = source[source.index("def _video_provider_task_candidates") : source.index("def video_b14_result_url_validation")]
    raw_block = source[source.index("def video_provider_raw_status_text") : source.index("async def cmd_video_provider_raw_status")]

    assert '"scene_ledger"' in candidate_block
    assert '"scene_tasks"' in candidate_block
    assert "scene_index_explicit" in candidate_block
    assert "candidate.get(\"scene_index_explicit\")" in candidate_block
    assert "poll_candidates=True" in raw_block
    assert "Per-scene tasks" in raw_block
    assert "all unresolved tasks polled" in raw_block
    assert "submit_video_job(" not in raw_block
    assert "run_provider_generation(" not in raw_block


def test_all_product_video_debug_views_use_reconciled_scene_ledger_source_contract():
    source = (ROOT / "bot.py").read_text(encoding="utf-8")

    assert "def _video_scene_ledger_debug_lines" in source
    for function_name in (
        "video_render_debug_text",
        "video_provider_job_debug_text",
        "video_job_finance_debug_text",
        "product_progress_debug_text",
    ):
        start = source.index(f"def {function_name}")
        end = source.find("\ndef ", start + 1)
        block = source[start : end if end != -1 else len(source)]
        assert "_video_scene_ledger_debug_lines" in block or "video_b14_reconciled_provider_debug" in block
    assert "panel_scene_ledger_source" in (ROOT / "services" / "product_progress_status.py").read_text(encoding="utf-8")


def test_no_real_provider_calls_in_r18t_tests():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "urllib.request." + "urlopen",
        "provider" + "_smoke",
    )
    assert all(token not in source for token in forbidden)
