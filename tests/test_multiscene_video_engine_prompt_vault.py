import asyncio
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import bot
import video_multiscene_engine as engine


def _session(scene_count=3, **overrides):
    value = {
        "prompt": "Quảng cáo TikTok cho máy xay mini: người bận rộn cần bữa sáng nhanh",
        "product_name": "máy xay mini TOAN AAS",
        "selected_scene_count": scene_count,
        "estimated_scene_seconds": 6,
        "aspect_ratio": "9:16",
        "language": "vi",
        "platform": "TikTok/Reels/Shorts",
        "selected_video_tier": "basic",
    }
    value.update(overrides)
    return value


class _Message:
    chat_id = 987654

    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


def _prepare_orchestrator(monkeypatch):
    created = []
    updates = []
    snapshots = []

    def create_job(*args, **kwargs):
        created.append((args, kwargs))
        return len(created)

    monkeypatch.setattr(bot, "create_shopaikey_job", create_job)
    monkeypatch.setattr(bot, "update_shopaikey_job", lambda *args, **kwargs: updates.append((args, kwargs)))
    monkeypatch.setattr(bot, "save_multiscene_job_record", lambda job: snapshots.append(json.loads(json.dumps(job))) or job)
    monkeypatch.setattr(bot, "save_tool_test_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "set_system_setting", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "spend_fixed_credit_info", lambda *args, **kwargs: {"ok": True, "final_cost": int(args[1])})
    monkeypatch.setattr(bot, "refund_charged_credit", lambda *args, **kwargs: True)
    return created, updates, snapshots


def _run_job(monkeypatch, tmp_path, *, scene_count=3, poller=None, submitter=None, stitcher=None, sender=None, **order_overrides):
    created, updates, snapshots = _prepare_orchestrator(monkeypatch)
    events = []
    submit_calls = []
    poll_calls = []
    send_calls = []

    async def default_submit(child):
        submit_calls.append(child["scene_index"])
        events.append(f"submit:{child['scene_index']}")
        return {"status": "PASS_SUBMITTED", "task_id": f"task-{child['scene_index']}", "provider_route": "shopaikey"}

    async def default_poll(child):
        poll_calls.append(child["scene_index"])
        events.append(f"poll:{child['scene_index']}")
        return {"status": "SUCCESS", "result_url": f"https://example.test/{child['scene_index']}.mp4"}

    async def download(_url, destination):
        Path(destination).write_bytes(b"scene")
        return destination

    def default_stitch(scene_files, output_path, _aspect, _settings):
        events.append("stitch")
        assert len(scene_files) == scene_count
        Path(output_path).write_bytes(b"final")
        return {"status": "COMPLETED", "output_path": output_path}

    async def default_send(_bot_client, _chat_id, job, output_path):
        events.append("send")
        send_calls.append((job["parent_task_id"], output_path))
        return {"sent": True}

    order = {
        "session": _session(scene_count),
        "user_id": 123,
        "chat_id": 456,
        "video_tier": "basic",
        "total_xu": 810,
        "admin_test": True,
        "confirm_paid": True,
        "charge_xu": False,
        "poll_max_attempts": 1,
        "poll_interval_seconds": 0,
    }
    order.update(order_overrides)
    result = asyncio.run(bot.run_multiscene_video_job(
        order,
        submitter=submitter or default_submit,
        poller=poller or default_poll,
        downloader=download,
        stitcher=stitcher or default_stitch,
        sender=sender or default_send,
    ))
    return result, {
        "created": created, "updates": updates, "snapshots": snapshots,
        "events": events, "submit_calls": submit_calls,
        "poll_calls": poll_calls, "send_calls": send_calls,
    }


def test_prompt_vault_loads():
    vault = engine.load_prompt_vault()
    assert set(engine.VAULT_FILES).issubset(vault)
    assert all(vault[name] for name in engine.VAULT_FILES)


def test_prompt_vault_has_default_context():
    status = engine.prompt_vault_status()
    assert status["default_fallback_available"] is True


def test_context_bundle_selected_for_video_session():
    bundle = bot.select_video_context_bundle(_session())
    assert bundle["style_pack"]["id"]
    assert bundle["scene_template"]["id"]
    assert bundle["product_context"]["id"]


def test_context_bundle_language_vi():
    bundle = bot.select_video_context_bundle(_session(language="vi"))
    assert bundle["language"] == "vi"
    assert bundle["localization_rules"]["id"] == "locale_vi"


def test_context_bundle_no_secret():
    assert engine.prompt_vault_has_no_secret(bot.select_video_context_bundle(_session()))


def test_build_multiscene_prompt_plan_3_scenes():
    plan = bot.build_detailed_multiscene_prompt_plan(_session(3), bot.select_video_context_bundle(_session(3)))
    assert len(plan["scenes"]) == 3
    assert plan["project"]["estimated_total_seconds"] == 18


def test_each_scene_has_unique_prompt():
    plan = bot.build_detailed_multiscene_prompt_plan(_session(20), bot.select_video_context_bundle(_session(20)))
    prompts = [scene["provider_prompt"] for scene in plan["scenes"]]
    purposes = [scene["purpose"] for scene in plan["scenes"]]
    assert len(prompts) == len(set(prompts)) == 20
    assert len(purposes) == len(set(purposes)) == 20


def test_consistency_bible_present():
    plan = bot.build_detailed_multiscene_prompt_plan(_session())
    assert plan["consistency_bible"]["main_subject"]
    assert plan["consistency_bible"]["do_not_change"]


def test_logo_watermark_included_if_selected():
    plan = bot.build_detailed_multiscene_prompt_plan(_session(3, logo_watermark="TOAN AAS góc phải dưới"))
    assert plan["project"]["logo_watermark"] == "TOAN AAS góc phải dưới"
    assert all("TOAN AAS góc phải dưới" in scene["provider_prompt"] for scene in plan["scenes"])


def test_aspect_ratio_in_prompt_plan():
    plan = bot.build_detailed_multiscene_prompt_plan(_session(5, aspect_ratio="16:9"))
    assert plan["project"]["aspect_ratio"] == "16:9"
    assert all("16:9" in scene["provider_prompt"] for scene in plan["scenes"])


def test_scene_durations_sum_correct():
    for count in (1, 3, 5, 10, 20):
        plan = bot.build_detailed_multiscene_prompt_plan(_session(count))
        assert sum(scene["duration_seconds"] for scene in plan["scenes"]) == count * 6
        assert plan["project"]["estimated_total_seconds"] == count * 6


def test_single_scene_export_path_unchanged(monkeypatch):
    async def forbidden(_child):
        raise AssertionError("single-scene must not enter multi-scene provider path")
    result = asyncio.run(bot.run_multiscene_video_job({"session": _session(1)}, submitter=forbidden))
    assert result == {"status": "SINGLE_SCENE_UNCHANGED", "scene_count": 1}


def test_multiscene_public_guard_when_disabled(monkeypatch):
    monkeypatch.setattr(bot, "video_multiscene_public_ready", lambda _count: False)
    result = asyncio.run(bot.run_multiscene_video_job({"session": _session(3), "final_invoice_confirmed": True}))
    assert result["status"] == "PUBLIC_GUARDED"
    assert result["message"] == bot.VIDEO_MULTISCENE_PUBLIC_GUARD_TEXT


def test_multiscene_no_provider_call_when_public_disabled(monkeypatch):
    monkeypatch.setattr(bot, "video_multiscene_public_ready", lambda _count: False)
    calls = []
    async def forbidden(child):
        calls.append(child)
    asyncio.run(bot.run_multiscene_video_job({"session": _session(3), "final_invoice_confirmed": True}, submitter=forbidden))
    assert calls == []


def test_multiscene_admin_confirm_required(monkeypatch):
    calls = []
    async def forbidden(child):
        calls.append(child)
    result = asyncio.run(bot.run_multiscene_video_job({"session": _session(3), "admin_test": True}, submitter=forbidden))
    assert result["status"] == "CONFIRM_PAID_REQUIRED"
    assert calls == []


def test_multiscene_parent_child_jobs_created(monkeypatch, tmp_path):
    result, trace = _run_job(monkeypatch, tmp_path, scene_count=3)
    assert result["status"] == "SENT"
    assert len(trace["created"]) == 4
    assert len(result["scene_jobs"]) == 3
    assert [child["scene_index"] for child in result["scene_jobs"]] == [1, 2, 3]


def test_multiscene_scene_prompts_ordered():
    plan = bot.build_detailed_multiscene_prompt_plan(_session(5))
    assert [scene["scene_index"] for scene in plan["scenes"]] == [1, 2, 3, 4, 5]
    assert [f"Cảnh {idx}/5" in scene["provider_prompt"] for idx, scene in enumerate(plan["scenes"], 1)] == [True] * 5


def test_pass_submitted_not_final_success(monkeypatch, tmp_path):
    result, trace = _run_job(monkeypatch, tmp_path, scene_count=3)
    assert trace["submit_calls"] == [1, 2, 3]
    assert sorted(trace["poll_calls"]) == [1, 2, 3]
    assert any(any(child["status"] == "SUBMITTED" for child in snapshot.get("scene_jobs", [])) for snapshot in trace["snapshots"])
    assert result["status"] == "SENT"


def test_pass_submitted_test_status_does_not_enable_public(monkeypatch):
    monkeypatch.setattr(bot, "get_tool_test_result", lambda _name: {"status": "PASS_SUBMITTED"})
    monkeypatch.setattr(bot, "get_system_setting", lambda *args, **kwargs: "")
    assert bot.video_multiscene_scene_tested(3) is False


def test_ambiguous_timeout_no_duplicate_fallback(monkeypatch, tmp_path):
    submit_calls = []
    send_calls = []
    async def submit(child):
        submit_calls.append(child["scene_index"])
        return {"status": "PASS_SUBMITTED", "task_id": f"ambiguous-{child['scene_index']}"}
    async def pending(_child):
        return {"status": "IN_PROGRESS"}
    async def forbidden_send(*args):
        send_calls.append(args)
        return {"sent": True}
    result, _ = _run_job(monkeypatch, tmp_path, scene_count=3, submitter=submit, poller=pending, sender=forbidden_send, poll_max_attempts=2)
    assert submit_calls == [1, 2, 3]
    assert result["status"] == "PARTIAL_FAILED"
    assert result["error"] == "AMBIGUOUS_POLL_TIMEOUT_NO_RESUBMIT"
    assert send_calls == []


def test_stitching_called_after_all_scenes_complete(monkeypatch, tmp_path):
    result, trace = _run_job(monkeypatch, tmp_path, scene_count=5)
    assert result["status"] == "SENT"
    assert trace["events"].index("stitch") > max(trace["events"].index(f"poll:{index}") for index in range(1, 6))


def test_partial_failure_no_fake_final(monkeypatch, tmp_path):
    send_calls = []
    async def poll(child):
        if child["scene_index"] == 2:
            return {"status": "FAILED", "fail_reason": "scene failed"}
        return {"status": "SUCCESS", "result_url": f"https://example.test/{child['scene_index']}.mp4"}
    async def forbidden_send(*args):
        send_calls.append(args)
        return {"sent": True}
    result, trace = _run_job(monkeypatch, tmp_path, scene_count=3, poller=poll, sender=forbidden_send)
    assert result["status"] == "PARTIAL_FAILED"
    assert "stitch" not in trace["events"]
    assert send_calls == []


def test_final_result_sent_once(monkeypatch, tmp_path):
    result, trace = _run_job(monkeypatch, tmp_path, scene_count=3)
    assert result["result_sent"] is True
    assert len(trace["send_calls"]) == 1


def test_public_no_provider_debug_text():
    text = bot._multiscene_public_failure_text({"xu_deducted": 0})
    assert all(term not in text.lower() for term in ("provider", "http 200", "task_id", "shopaikey", "key4u", "api key"))


def test_tool_test_video_multiscene_admin_only(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    message = _Message()
    asyncio.run(bot.cmd_tool_test_video_multiscene(SimpleNamespace(effective_user=SimpleNamespace(id=1), message=message), SimpleNamespace(args=[])))
    assert "chỉ dành cho admin" in message.replies[-1][0]


def test_video_multiscene_status_admin_only(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    message = _Message()
    asyncio.run(bot.cmd_video_multiscene_status(SimpleNamespace(effective_user=SimpleNamespace(id=1), message=message), SimpleNamespace()))
    assert "chỉ dành cho admin" in message.replies[-1][0]


def test_video_prompt_vault_status_admin_only(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    message = _Message()
    asyncio.run(bot.cmd_video_prompt_vault_status(SimpleNamespace(effective_user=SimpleNamespace(id=1), message=message), SimpleNamespace()))
    assert "chỉ dành cho admin" in message.replies[-1][0]


def test_video_prompt_plan_preview_no_provider_call(monkeypatch):
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "video_multiscene_session_snapshot", lambda _uid: _session(3))
    monkeypatch.setattr(bot, "submit_public_video_with_key4u_fallback", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider called")))
    message = _Message()
    asyncio.run(bot.cmd_video_prompt_plan_preview(SimpleNamespace(effective_user=SimpleNamespace(id=1), message=message), SimpleNamespace()))
    assert "Provider call: <code>NO</code>" in message.replies[-1][0]
    assert "Xu charge: <code>NO</code>" in message.replies[-1][0]


def test_no_payos_touched():
    source = inspect.getsource(engine).lower()
    assert "payos" not in source


def test_no_wallet_touched():
    source = inspect.getsource(engine).lower()
    assert all(term not in source for term in ("deduct_credits", "charge_user", "wallet", "spend_fixed_credit_info"))


def test_no_provider_internals_rewritten():
    source = inspect.getsource(engine)
    assert "key4u_provider" not in source
    assert "shopaikey_video_create_for_model" not in source


def test_no_paid_provider_job_without_confirm(monkeypatch):
    _prepare_orchestrator(monkeypatch)
    calls = []
    async def forbidden(child):
        calls.append(child)
    result = asyncio.run(bot.run_multiscene_video_job({"session": _session(3), "admin_test": True, "confirm_paid": False}, submitter=forbidden))
    assert result["status"] == "CONFIRM_PAID_REQUIRED"
    assert calls == []
