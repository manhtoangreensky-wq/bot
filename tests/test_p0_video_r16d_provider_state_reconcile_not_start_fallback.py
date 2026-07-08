import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace

from services import video_project_queue
from services.video_provider_router import product_video_provider_submit_source_policy
from services import video_real_render_connector as connector


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
TMP_ROOT = ROOT / ".pytest_tmp"
TMP_ROOT.mkdir(exist_ok=True)


def _not_start_task(index: int, *, elapsed: int = 0, fallback_count: int = 0, provider: str = "shopaikey_video") -> dict:
    return {
        "scene_index": index,
        "request_job_id": f"job-r16d-{index}",
        "provider": provider,
        "provider_task_id": f"task-{index}",
        "provider_video_id": f"video-{index}",
        "status": "NOT_START",
        "provider_status_raw": "NOT_START",
        "provider_progress_raw": 0,
        "provider_progress_normalized": 0,
        "provider_wait_elapsed_seconds": elapsed,
        "fallback_count": fallback_count,
    }


def _job(*, scene_tasks=None, provider_order="shopaikey_video,key4u_video", elapsed=666, **extra) -> dict:
    data = {
        "job_id": "job-r16d",
        "source": "product_video",
        "product_video": True,
        "render_mode": "real",
        "provider_call": True,
        "product_type": "video_trend",
        "scene_count": 2,
        "orchestration_mode": "per_scene_8s",
        "provider_order": provider_order,
        "public_user_confirmed": True,
        "invoice_confirmed": True,
        "submit_source": "public_user_final_confirm",
        "provider_submit_source": "public_user_final_confirm",
        "original_submit_source": "public_user_final_confirm",
        "provider_elapsed_seconds": elapsed,
    }
    if scene_tasks is not None:
        data["scene_tasks"] = scene_tasks
        data["provider_scene_tasks"] = scene_tasks
    data.update(extra)
    return data


def test_job_101_not_start_elapsed_inherits_provider_elapsed_and_fallbackable():
    tasks = [_not_start_task(1, elapsed=0), _not_start_task(2, elapsed=0)]
    debug = connector.product_video_scene_tasks_debug(_job(scene_tasks=tasks, elapsed=666), scene_count=2)

    assert len(debug) == 2
    assert all(item["scene_not_start_elapsed"] >= 666 for item in debug)
    assert all(item["provider_stalled_not_start"] is True for item in debug)
    assert all(item["fallbackable_blocker"] is True for item in debug)
    assert all(item["fallback_allowed"] is True for item in debug)
    assert debug[0]["fallback_provider_order"][0] == "key4u_video"
    assert debug[0]["fallback_eligibility_reason"] == "eligible"
    assert debug[0]["source_of_truth"] == "scene_not_start_stalled"


def test_not_start_under_grace_waits_without_terminal_failure():
    task = _not_start_task(1, elapsed=30)
    policy = connector.product_video_scene_stall_policy(_job(scene_tasks=[task], elapsed=30), task, 1)

    assert policy["provider_stalled_not_start"] is False
    assert policy["fallback_allowed"] is False
    assert policy["fallback_block_reason"] == "scene_not_stalled"


def test_not_start_over_grace_without_fallback_provider_fails_no_charge_consistently():
    tasks = [_not_start_task(1, elapsed=666), _not_start_task(2, elapsed=666)]
    events: list[dict] = []
    debug_results: list[dict] = []

    with tempfile.TemporaryDirectory(dir=TMP_ROOT) as tmp_dir:
        result = connector._run_per_scene_provider_orchestrator(
            _job(scene_tasks=tasks, provider_order="shopaikey_video", elapsed=666),
            tmp_dir,
            provider_order=["shopaikey_video"],
            provider_events=events,
            debug_results=debug_results,
        )

    assert result["ok"] is False
    assert result["terminal_state"] == "failed_no_charge"
    assert result["final_decision"] == "failed_no_charge"
    assert result["continue_polling"] is False
    assert result["status"] == "failed"
    assert result["provider_error"] == "provider_stalled_not_start"
    assert result["blocker"] == "provider_stalled_not_start"
    assert result["fallback_allowed"] is False
    assert result["fallback_block_reason"] == "no_fallback_provider"
    assert result["no_charge"] is True


def test_stalled_scene_fallback_submit_source_and_chain_are_preserved(monkeypatch):
    captured: dict = {}

    def fake_run_provider_generation(request, *, output_dir, environ):
        captured["metadata"] = dict(request.metadata)
        captured["chain"] = environ.get("VIDEO_PROVIDER_CHAIN")
        return {
            "ok": False,
            "provider": "key4u_video",
            "selected_provider": "key4u_video",
            "provider_task_ids": ["fallback-task-1"],
            "provider_video_ids": ["fallback-video-1"],
            "provider_task_id_saved": True,
            "provider_submit_called": True,
            "provider_poll_called": True,
            "submit_accepted": True,
            "continue_polling": True,
            "provider_error": "provider_in_progress",
            "blocker": "provider_in_progress",
            "provider_status": "running",
            "normalized_provider_status": "running",
            "scene_index": 1,
            "request_job_id": request.job_id,
            "provider_progress_raw": 0,
        }

    monkeypatch.setattr(connector, "run_provider_generation", fake_run_provider_generation)
    stalled_task = _not_start_task(1, elapsed=666)
    scene = SimpleNamespace(
        scene_id=1,
        video_prompt="Scene 1 prompt",
        visual_prompt="Scene 1 prompt",
        aspect_ratio="9:16",
        target_duration_sec=8,
        _toan_aas_job=_job(scene_tasks=[stalled_task], elapsed=666),
    )

    with tempfile.TemporaryDirectory(dir=TMP_ROOT) as tmp_dir:
        try:
            asyncio.run(connector._render_scene_async(scene, str(Path(tmp_dir) / "raw_scene_1.mp4"), []))
        except connector.RealVideoRenderError as exc:
            diagnostics = dict(exc.diagnostics)
        else:
            raise AssertionError("fallback in-progress fixture must raise deferred provider error")

    assert captured["metadata"]["submit_source"] == "public_confirmed_scene_fallback_once"
    assert captured["metadata"]["fallback_count"] == 1
    assert captured["metadata"]["fallback_scene_index"] == 1
    assert captured["chain"].split(",")[0] == "key4u_video"
    assert diagnostics["continue_polling"] is True
    assert diagnostics["fallback_used"] is True
    assert diagnostics["fallback_submit_source"] == "public_confirmed_scene_fallback_once"


def test_failed_no_charge_never_coexists_with_continue_polling_or_provider_alive():
    payload = {
        "terminal_state": "failed_no_charge",
        "final_decision": "failed_no_charge",
        "continue_polling": True,
        "provider_task_ids": ["task-primary"],
        "provider_error": "provider_in_progress",
        "provider_stalled_not_start": True,
        "fallback_allowed": False,
        "fallback_block_reason": "no_fallback_provider",
    }

    assert video_project_queue.provider_task_alive(payload) is False
    fixed = connector._apply_pending_provider_dominance(dict(payload), job=_job())
    assert fixed["terminal_state"] == "failed_no_charge"
    assert fixed["final_decision"] == "failed_no_charge"
    assert fixed["continue_polling"] is False
    assert fixed["provider_status"] == "failed"


def test_debug_and_finance_fields_are_registered_for_r16d():
    for token in (
        "scenes total/done/running/stalled",
        "fallbackable blocker",
        "fallback eligibility reason",
        "fallback provider",
        "source of truth",
        "provider state source",
        "scenes stalled count",
        "fallback count by scene",
    ):
        assert token in BOT_SOURCE


def test_codex_tests_use_fixtures_only_without_paid_provider_calls():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden = (
        "SHOPAIKEY" + "_API_KEY",
        "KEY4U" + "_API_KEY",
        "provider" + "_smoke",
        "submit_url" + "_thật",
    )
    assert all(token not in source for token in forbidden)


def test_scene_fallback_submit_source_is_allowed_without_breaking_legacy_alias():
    scene_policy = product_video_provider_submit_source_policy(
        {"submit_source": "public_confirmed_scene_fallback_once", "public_user_confirmed": True},
        public_submit_enabled=True,
    )
    legacy_policy = product_video_provider_submit_source_policy(
        {"submit_source": "public_confirmed_fallback_once", "public_user_confirmed": True},
        public_submit_enabled=True,
    )

    assert scene_policy["submit_source"] == "public_confirmed_scene_fallback_once"
    assert scene_policy["provider_submit_allowed"] is True
    assert legacy_policy["submit_source"] == "public_confirmed_fallback_once"
    assert legacy_policy["provider_submit_allowed"] is True
