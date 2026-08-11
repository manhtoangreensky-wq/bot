import asyncio
import inspect
import json
from types import SimpleNamespace

import pytest

import bot


USER_ID = 187001
JOB_ID = 987201
PROJECT_ID = 9901


class FakeConnection:
    def close(self):
        return None


class FakeBot:
    def __init__(self):
        self.edits = []
        self.sent = []
        self.videos = []

    async def edit_message_text(self, **kwargs):
        self.edits.append(kwargs)
        return SimpleNamespace(
            chat_id=kwargs.get("chat_id"),
            message_id=kwargs.get("message_id"),
        )

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(chat_id=kwargs.get("chat_id"), message_id=999)

    async def send_video(self, **kwargs):
        self.videos.append(kwargs)
        return SimpleNamespace(chat_id=kwargs.get("chat_id"), message_id=998)


class FakeQuery:
    def __init__(self):
        self.message = SimpleNamespace(chat_id=USER_ID, message_id=4401)
        self.edits = []

    async def edit_message_text(self, text, **kwargs):
        self.edits.append({"text": text, **kwargs})
        return self.message


@pytest.fixture(autouse=True)
def _clear_refresh_registry():
    bot.VIDEO_STATUS_AUTO_REFRESH_JOBS.clear()
    bot.VIDEO_STATUS_AUTO_REFRESH_TASKS.clear()
    yield
    bot.VIDEO_STATUS_AUTO_REFRESH_JOBS.clear()
    bot.VIDEO_STATUS_AUTO_REFRESH_TASKS.clear()


def _job(*, status="processing", progress=40, owner=USER_ID, payload=None):
    result = {
        "product_video": True,
        "source": "product_video",
        "chat_id": owner,
        "user_id": owner,
        "job_id": JOB_ID,
        "scene_count": 1,
        "provider_task_alive": status == "processing",
    }
    result.update(dict(payload or {}))
    return {
        "id": JOB_ID,
        "project_id": PROJECT_ID,
        "user_id": owner,
        "job_type": bot.video_project_queue.VIDEO_RENDER_JOB_TYPE,
        "status": status,
        "progress_percent": progress,
        "result_json": json.dumps(result),
    }


def _project(*, status="processing", owner=USER_ID):
    return {
        "project_id": PROJECT_ID,
        "user_id": owner,
        "status": status,
        "scene_count": 1,
        "invoice_json": json.dumps(
            {
                "scene_count": 1,
                "duration_seconds": 8,
                "quality_xu": 220,
                "package_label": "Tiêu chuẩn có âm thanh",
            }
        ),
        "addon_plan_json": "{}",
    }


def _session(job, project):
    return bot.video_b14_auto_refresh_session_from_status(
        job,
        project,
        user_id=USER_ID,
    )


def _record():
    key = bot.video_b14_auto_refresh_key(JOB_ID)
    record = {
        "key": key,
        "job_id": str(JOB_ID),
        "project_id": PROJECT_ID,
        "chat_id": USER_ID,
        "message_id": 4401,
        "user_id": USER_ID,
        "lang": "vi",
        "interval_seconds": 10,
        "max_updates": 20,
        "min_delta_percent": 1,
        "update_count": 0,
        "last_render_hash": "stale",
        "task_alive": True,
        "stopped": False,
    }
    bot.VIDEO_STATUS_AUTO_REFRESH_JOBS[key] = record
    return key


def _observe_forbidden_refresh_effects(monkeypatch, live):
    calls = {
        "provider_poll": 0,
        "recovery": 0,
        "db_execution_mutation": 0,
        "artifact_finalize": 0,
        "delivery": 0,
        "receipt": 0,
        "wallet": 0,
    }

    monkeypatch.setattr(bot, "video_b14_render_job_by_id", lambda _job_id: dict(live["job"]))
    monkeypatch.setattr(bot, "get_video_project", lambda _project_id: dict(live["project"]))
    monkeypatch.setattr(bot, "db_connect", lambda: FakeConnection())
    monkeypatch.setattr(
        bot.video_project_queue,
        "product_video_dispatch_outbox_diagnostic",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(bot, "product_video_worker_admission_status", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        bot,
        "video_b14_provider_telemetry",
        lambda job, payload, **_kwargs: {
            "provider_task_alive": str(job.get("status") or "") == "processing",
            "final_progress_after_reconcile": int(job.get("progress_percent") or 0),
            "render_video_progress_percent": int(job.get("progress_percent") or 0),
        },
    )

    def canonical(*_args, **kwargs):
        if kwargs.get("poll_candidates"):
            calls["provider_poll"] += 1
        return {}

    def stale(*_args, **_kwargs):
        calls["db_execution_mutation"] += 1
        return 0

    def persist(*_args, **_kwargs):
        calls["db_execution_mutation"] += 1
        return {}

    async def recovery(*_args, **_kwargs):
        calls["recovery"] += 1
        return {"ok": False, "waiting": True, "sent": False}

    async def delivery(*_args, **_kwargs):
        calls["delivery"] += 1
        return {"sent": False}

    def receipt(*_args, **_kwargs):
        calls["receipt"] += 1
        return {}

    def wallet(*_args, **_kwargs):
        calls["wallet"] += 1
        return {}

    monkeypatch.setattr(bot, "resolve_canonical_video_provider_task", canonical)
    monkeypatch.setattr(bot, "video_b14_fail_stale_product_job_for_status", stale)
    monkeypatch.setattr(bot, "video_b14_persist_auto_refresh_metadata", persist)
    monkeypatch.setattr(bot, "video_b14_autonomous_materialize_and_deliver", recovery)
    monkeypatch.setattr(bot, "maybe_send_remote_worker_final_video", delivery)
    monkeypatch.setattr(bot.video_project_queue, "note_video_delivery_result", receipt)
    monkeypatch.setattr(bot, "product_video_charge_after_final_delivery", wallet)
    return calls


def _assert_no_refresh_effects(calls):
    assert calls == {
        "provider_poll": 0,
        "recovery": 0,
        "db_execution_mutation": 0,
        "artifact_finalize": 0,
        "delivery": 0,
        "receipt": 0,
        "wallet": 0,
    }


def test_manual_refresh_running_is_read_only_and_renders_status(monkeypatch):
    live = {"job": _job(), "project": _project()}
    calls = _observe_forbidden_refresh_effects(monkeypatch, live)
    query = FakeQuery()
    context = SimpleNamespace(bot=FakeBot(), application=None)

    source = inspect.getsource(bot.handle_video_product_callback)
    manual = source.split('if action == "b14_job_status":', 1)[1].split(
        'if action == "b14_download_video":', 1
    )[0]
    assert "video_b14_autonomous_materialize_and_deliver" not in manual
    assert "safe_edit_or_send" not in manual
    assert "video_b14_edit_existing_status_message" in manual
    assert "register_auto_refresh=False" in manual
    assert "edit_existing_only=True" in manual

    asyncio.run(
        bot.video_b14_send_or_edit_status_panel(
            query,
            context,
            _session(live["job"], live["project"]),
            {"job": live["job"], "project": live["project"]},
            USER_ID,
            "vi",
            register_auto_refresh=False,
            edit_existing_only=True,
        )
    )

    assert len(query.edits) == 1
    assert "Trạng thái tạo video" in query.edits[0]["text"]
    _assert_no_refresh_effects(calls)


def test_auto_refresh_running_is_read_only_and_edits_only(monkeypatch):
    live = {"job": _job(), "project": _project()}
    calls = _observe_forbidden_refresh_effects(monkeypatch, live)
    key = _record()
    fake_bot = FakeBot()

    result = asyncio.run(
        bot.video_b14_auto_refresh_tick(
            SimpleNamespace(bot=fake_bot, application=None),
            key,
        )
    )

    assert result["status"] == "updated"
    assert len(fake_bot.edits) == 1
    assert fake_bot.sent == []
    assert fake_bot.videos == []
    _assert_no_refresh_effects(calls)


def test_delivery_pending_refresh_never_delivers_receipts_or_settles(monkeypatch):
    live = {
        "job": _job(
            status="completed",
            progress=100,
            payload={"result_url_present": True},
        ),
        "project": _project(status="completed"),
    }
    calls = _observe_forbidden_refresh_effects(monkeypatch, live)
    key = _record()
    fake_bot = FakeBot()

    result = asyncio.run(
        bot.video_b14_auto_refresh_tick(
            SimpleNamespace(bot=fake_bot, application=None),
            key,
        )
    )

    assert result["snapshot"]["delivery_done"] is False
    assert fake_bot.videos == []
    _assert_no_refresh_effects(calls)


def test_refresh_observes_executor_state_change_without_creating_transition(monkeypatch):
    live = {"job": _job(progress=20), "project": _project()}
    calls = _observe_forbidden_refresh_effects(monkeypatch, live)
    key = _record()
    context = SimpleNamespace(bot=FakeBot(), application=None)

    first = asyncio.run(bot.video_b14_auto_refresh_tick(context, key))
    bot.VIDEO_STATUS_AUTO_REFRESH_JOBS[key]["auto_refresh_lease_until_epoch"] = 0
    live["job"] = _job(progress=70)
    second = asyncio.run(bot.video_b14_auto_refresh_tick(context, key))

    assert first["snapshot"]["percent"] < second["snapshot"]["percent"]
    assert second["snapshot"]["job"]["progress_percent"] == 70
    _assert_no_refresh_effects(calls)


def test_refresh_wrong_owner_or_chat_fails_closed_without_side_effects(monkeypatch):
    live = {"job": _job(owner=USER_ID + 1), "project": _project(owner=USER_ID + 1)}
    calls = _observe_forbidden_refresh_effects(monkeypatch, live)
    key = _record()

    owner_bundle = bot.video_b14_auto_refresh_status_bundle(
        JOB_ID,
        user_id=USER_ID,
        chat_id=USER_ID,
        project_id=PROJECT_ID,
    )
    live.update({"job": _job(), "project": _project()})
    chat_bundle = bot.video_b14_auto_refresh_status_bundle(
        JOB_ID,
        user_id=USER_ID,
        chat_id=USER_ID + 1,
        project_id=PROJECT_ID,
    )
    wrong_job = _job()
    wrong_job["id"] = JOB_ID + 1
    wrong_job_payload = json.loads(wrong_job["result_json"])
    wrong_job_payload["job_id"] = JOB_ID + 1
    wrong_job["result_json"] = json.dumps(wrong_job_payload)
    live.update({"job": wrong_job, "project": _project()})
    job_bundle = bot.video_b14_auto_refresh_status_bundle(
        JOB_ID,
        user_id=USER_ID,
        chat_id=USER_ID,
        project_id=PROJECT_ID,
    )
    live.update(
        {
            "job": _job(owner=USER_ID + 1),
            "project": _project(owner=USER_ID + 1),
        }
    )
    result = asyncio.run(
        bot.video_b14_auto_refresh_tick(
            SimpleNamespace(bot=FakeBot(), application=None),
            key,
        )
    )

    assert owner_bundle["job"] == {}
    assert owner_bundle["project"] == {}
    assert chat_bundle["job"] == {}
    assert chat_bundle["project"] == {}
    assert job_bundle["job"] == {}
    assert job_bundle["project"] == {}
    assert result["status"] == "stopped"
    assert result["reason"] == "status_identity_mismatch"
    _assert_no_refresh_effects(calls)


def test_worker_execution_owner_still_owns_recovery_delivery_and_settlement():
    claim = inspect.getsource(bot.api_worker_claim)
    complete = inspect.getsource(bot.api_worker_complete)
    rehydrate = inspect.getsource(bot.video_b14_rehydrate_auto_refresh_registry)

    assert "video_b14_recover_existing_tasks_for_worker_claim" in claim
    assert 'heartbeat.get("heartbeat_accepted")' in claim
    assert "recover_product_video_existing_tasks" not in rehydrate
    assert "maybe_send_remote_worker_final_video" in complete
    assert "note_video_delivery_result" in complete
    assert "product_video_charge_after_final_delivery" in complete
