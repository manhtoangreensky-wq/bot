import asyncio
from types import SimpleNamespace

import bot


MIB = 1024 * 1024


def _successful_input_save(size: int = 75 * MIB) -> dict:
    return {
        "ok": True,
        "file_saved": True,
        "exists": True,
        "size": size,
        "telegram_file_size": size,
        "telegram_download_method": "bot_api_direct",
        "telegram_api_source": "local_bot_api",
        "telegram_download_limit_hit": False,
        "large_media_intake_supported": True,
        "large_media_intake_source": "local_bot_api",
        "input_save_blocker": "",
        "input_save_public_action": "",
        "no_charge_reason": "",
    }


def test_successful_media_over_50_mib_is_detected_without_a_limit_failure():
    fields = bot.subdub_input_save_debug_fields(
        _successful_input_save(50 * MIB + 1),
        {"_pipeline_is_admin": True},
    )

    assert fields["input_save_success"] is True
    assert fields["large_telegram_media_detected"] is True
    assert fields["telegram_download_limit_hit"] is False
    assert fields["large_media_intake_supported"] is True


def test_delivered_video_receipt_keeps_historical_mp4_truth():
    key = "production-receipt-mp4-truth"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    acquired, _job = bot.acquire_subtitle_dub_pipeline_job(
        key,
        user_id=7070,
        chat_id=7070,
        mode=bot.VIDEO_SUBTITLE_MODE_DUB,
    )
    assert acquired is True

    assert bot.mark_subtitle_dub_pipeline_output_sent(
        key,
        terminal_state="delivered",
        delivery_message_id="telegram-video-8181",
        terminal_artifact_type="video",
        video_delivery_message_id="telegram-video-8181",
    ) is True

    stored = bot.SUBTITLE_DUB_PIPELINE_JOBS[key]
    assert stored["final_mp4_exists"] is True
    assert stored["final_mp4_validated"] is True
    assert stored["final_mp4_delivered"] is True
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)


def test_legacy_delivered_job_is_normalized_from_nested_receipt_truth():
    merged = bot.subdub_merge_debug_job({
        "feature": "subtitle_dub",
        "internal_job_id": "legacy-production-job",
        "status": "completed",
        "terminal_state": "delivered",
        "input_save": _successful_input_save(),
        "input_save_success": False,
        "large_telegram_media_detected": False,
        "video_delivery_message_id": "telegram-video-9191",
        "final_mp4_exists": False,
        "final_mp4_delivered": True,
    })

    assert merged["input_save_success"] is True
    assert merged["large_telegram_media_detected"] is True
    assert merged["telegram_download_limit_hit"] is False
    assert merged["final_mp4_exists"] is True
    assert merged["final_mp4_validated"] is True
    text = bot.subdub_job_debug_text(merged, "legacy-production-job")
    assert "input_save_success: <code>yes</code>" in text
    assert "large_media_detected: <code>yes</code>" in text
    assert "final_mp4_exists: <code>yes</code>" in text


def test_explicit_input_failure_root_is_not_overwritten_by_stale_nested_success():
    merged = bot.subdub_merge_debug_job({
        "feature": "subtitle_dub",
        "internal_job_id": "failed-production-job",
        "status": "failed_no_charge",
        "terminal_state": "failed_no_charge",
        "input_save": _successful_input_save(),
        "input_save_success": False,
        "input_save_blocker": "telegram_api_base_unreachable",
        "no_charge_reason": "telegram_api_base_unreachable",
        "telegram_download_limit_hit": False,
    })

    assert merged["input_save_success"] is False
    assert merged["input_save_blocker"] == "telegram_api_base_unreachable"
    assert merged["no_charge_reason"] == "telegram_api_base_unreachable"


def test_execute_pipeline_promotes_successful_input_save_to_registry_root(monkeypatch, tmp_path):
    updates = []

    async def no_progress(*_args, **_kwargs):
        return None

    async def successful_core(*_args, **_kwargs):
        return {
            "ok": True,
            "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
            "terminal_state": "delivered",
            "input_save": _successful_input_save(),
            "state": {
                "_pipeline_job_id": "production-wrapper-job",
                "_pipeline_is_admin": True,
            },
            "debug_job": {},
            "gate_matrix": {},
            "workspace_artifacts": {},
            "video_delivery_message_id": "telegram-video-9292",
            "telegram_message_id": "telegram-video-9292",
            "terminal_artifact_type": "video",
            "final_mp4_exists": True,
            "final_mp4_validated": True,
            "final_mp4_delivered": True,
            "has_video": True,
            "sent_video": 1,
            "charged": 0,
        }

    def capture_update(_job_key, **fields):
        updates.append(dict(fields))
        return dict(fields)

    monkeypatch.setattr(
        bot.subdub_blackboxes,
        "normalize_standalone_video_lane_entry_state",
        lambda state: dict(state),
    )
    monkeypatch.setattr(bot, "subtitle_dub_pipeline_job_key", lambda *_args, **_kwargs: "production-wrapper-key")
    monkeypatch.setattr(
        bot,
        "acquire_subtitle_dub_pipeline_job",
        lambda *_args, **_kwargs: (True, {"job_id": "production-wrapper-job", "terminal_state": ""}),
    )
    monkeypatch.setattr(bot, "create_subtitle_dub_pipeline_workspace", lambda *_args: str(tmp_path))
    monkeypatch.setattr(bot, "update_subtitle_dub_pipeline_job", capture_update)
    monkeypatch.setattr(bot, "subdub_send_progress_update", no_progress)
    monkeypatch.setattr(bot, "_execute_video_dubbing_pipeline_core", successful_core)
    monkeypatch.setattr(bot, "write_subtitle_dub_pipeline_manifest", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bot, "mark_subtitle_dub_pipeline_output_sent", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "cleanup_subtitle_dub_pipeline_workspace", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)

    query = SimpleNamespace(
        from_user=SimpleNamespace(id=7070),
        message=SimpleNamespace(chat_id=7070),
    )
    result = asyncio.run(bot.execute_video_dubbing_pipeline(
        query,
        SimpleNamespace(),
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB},
        "vi",
        admin_interactive_confirm=True,
    ))

    assert result["ok"] is True
    terminal_update = next(item for item in reversed(updates) if item.get("terminal_state") == "delivered")
    assert terminal_update["input_save_success"] is True
    assert terminal_update["telegram_file_size"] == 75 * MIB
    assert terminal_update["telegram_download_method"] == "bot_api_direct"
    assert terminal_update["large_telegram_media_detected"] is True
    assert terminal_update["telegram_download_limit_hit"] is False
    assert terminal_update["final_mp4_exists"] is True


def test_subtitle_dub_debug_command_chunks_oversized_html(monkeypatch):
    class StrictMessage:
        def __init__(self):
            self.parts = []

        async def reply_text(self, text, **kwargs):
            if kwargs.get("parse_mode") == "HTML" or len(str(text)) > 3600:
                raise RuntimeError("BadRequest: Message is too long")
            self.parts.append(str(text))
            return SimpleNamespace(message_id=len(self.parts))

    message = StrictMessage()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=7070), message=message)
    context = SimpleNamespace(args=["#899F3D4DF6"])
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: True)
    monkeypatch.setattr(bot, "subtitle_dub_debug_lookup_job", lambda *_args, **_kwargs: {"job_id": "fixture"})
    monkeypatch.setattr(bot, "subtitle_dub_debug_text", lambda _job: "<b>production debug & receipt</b>\n" * 500)

    asyncio.run(bot.cmd_subtitle_dub_debug(update, context))

    assert len(message.parts) > 1
    assert all(len(part) <= 3600 for part in message.parts)
    assert all("<b>" not in part for part in message.parts)
