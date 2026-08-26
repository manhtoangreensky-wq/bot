import asyncio
from types import SimpleNamespace

from telegram.error import TimedOut
import pytest

import bot


@pytest.mark.parametrize(
    "replacement_fails",
    (False, True),
    ids=("replacement-status-sent", "replacement-status-also-times-out"),
)
def test_background_initial_status_timeout_continues_pipeline_once(
    monkeypatch,
    replacement_fails,
):
    user_id = 98_401
    task_key = "98401|98401|two-speaker|subtitle_plus_dub|auto_speaker"
    current_state = {
        "pending_action": "video_dubbing",
        "step": "confirm",
        "current_step": "confirm",
        "mode": "subtitle_plus_dub",
        "process_type": "subtitle_plus_dub",
        "video_processing_mode": "subtitle_plus_dub",
        "requested_mode": "subtitle_plus_dub",
        "active_flow": "subtitle_plus_dub",
        "origin": "video",
        "source_file_id": "two-speaker",
        "target_language": "en",
        "voice_kind": "auto_speaker_gender",
        "voice_selection_mode": "auto_speaker",
        "voice_speed": "1.0",
        "processing": "0",
    }
    status_attempts = []
    replacement_statuses = []
    pipeline_states = []
    terminalized = []
    event_order = []

    def get_pending(_user_id):
        return dict(current_state)

    def set_pending(_user_id, step, **fields):
        current_state.update(fields)
        current_state["step"] = step
        current_state["current_step"] = step
        return dict(current_state)

    async def safe_edit(_query, text, **_kwargs):
        status_attempts.append(str(text))
        if len(status_attempts) == 1:
            raise TimedOut("initial status edit timed out")
        return SimpleNamespace(message_id=98_402)

    async def execute_pipeline(
        _query,
        _context,
        state,
        _lang,
        *,
        admin_interactive_confirm=False,
    ):
        event_order.append("pipeline")
        pipeline_states.append(
            {
                "state": dict(state),
                "admin_interactive_confirm": admin_interactive_confirm,
            }
        )
        return {
            "ok": False,
            "in_progress": True,
            "job_id": "status-timeout-resilient",
            "text": "pipeline is running",
        }

    async def execute_engine(_feature, payload, _engine_context):
        return {"ok": True, "runner_result": await payload["runner"]()}

    async def terminalize(_update, **fields):
        terminalized.append(dict(fields))

    class Message:
        chat_id = user_id

        async def reply_text(self, text, **kwargs):
            event_order.append("replacement_status")
            replacement_statuses.append({"text": text, **kwargs})
            if replacement_fails:
                raise TimedOut("replacement status also timed out")
            return SimpleNamespace(message_id=98_402, chat_id=user_id)

    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")
    monkeypatch.setattr(bot, "get_video_dubbing_pending", get_pending)
    monkeypatch.setattr(bot, "set_video_dubbing_pending", set_pending)
    monkeypatch.setattr(bot, "enter_product_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bot, "subdub_auto_speaker_route_enabled", lambda _state: True)
    monkeypatch.setattr(bot, "subdub_auto_quote_fields", lambda _uid, _state: {})
    monkeypatch.setattr(
        bot,
        "video_dubbing_engine_access_decision",
        lambda *_args, **_kwargs: {"allowed": True},
    )
    monkeypatch.setattr(
        bot,
        "get_subdub_lane_readiness",
        lambda *_args, **_kwargs: {"effective_ready": True},
    )
    monkeypatch.setattr(
        bot,
        "video_dubbing_asr_missing_for_state",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(bot, "safe_edit_or_send", safe_edit)
    monkeypatch.setattr(bot, "execute_video_dubbing_pipeline", execute_pipeline)
    monkeypatch.setattr(bot, "execute_engine", execute_engine)
    monkeypatch.setattr(bot, "subtitle_dub_pipeline_job_key", lambda *_args: task_key)
    monkeypatch.setattr(bot, "_terminalize_subdub_background_failure", terminalize)

    query = SimpleNamespace(
        data="videodub|final",
        from_user=SimpleNamespace(id=user_id),
        message=Message(),
    )
    update = SimpleNamespace(callback_query=query)

    asyncio.run(
        bot._run_subdub_public_final_background(
            update,
            SimpleNamespace(),
            task_key,
        )
    )

    assert len(pipeline_states) == 1
    assert pipeline_states[0]["admin_interactive_confirm"] is True
    assert pipeline_states[0]["state"]["subdub_final_confirmed"] is True
    if replacement_fails:
        assert "status_panel_message_id" not in pipeline_states[0]["state"]
    else:
        assert pipeline_states[0]["state"]["status_panel_message_id"] == "98402"
        assert pipeline_states[0]["state"]["status_panel_replacement_sent"] is True
    assert terminalized == []
    assert len(status_attempts) == 2
    assert len(replacement_statuses) == (2 if replacement_fails else 1)
    assert "TOAN AAS đang xử lý video" in replacement_statuses[0]["text"]
    assert event_order[-1] == "pipeline"
    assert all(event == "replacement_status" for event in event_order[:-1])
    assert current_state["step"] == "processing"
    assert current_state.get("terminal_state") != "failed_no_charge"
