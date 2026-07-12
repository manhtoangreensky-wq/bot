import asyncio

import bot


class _DeliveredMessage:
    message_id = 701

    @property
    def video(self):
        raise RuntimeError("optional_video_metadata_unavailable")


class _VideoReply:
    async def reply_video(self, **_kwargs):
        return _DeliveredMessage()


def _delivered_job(mode: str) -> dict:
    return {
        "mode": mode,
        "video_delivery_message_id": "701",
        "delivery_message_id": "701",
        "delivery_success": True,
        "delivery_succeeded": True,
        "final_mp4_delivered": True,
        "terminal_state": "delivered",
        "terminal_public_outcome_sent": True,
        "terminal_public_outcome_type": "success",
    }


def test_real_telegram_message_id_survives_optional_file_metadata_failure():
    result = asyncio.run(
        bot.send_generated_video_bytes_for_delivery(
            _VideoReply(),
            b"real-mp4-bytes",
            filename="result.mp4",
            caption="done",
            preview_max_mb=45,
            document_max_mb=50,
            generated_max_mb=50,
        )
    )

    assert result["sent"] is True
    assert result["delivery_method"] == "video"
    assert result["telegram_message_id"] == "701"
    assert result["file_id"] == ""


def test_subtitle_and_dub_standalone_modes_recover_terminal_receipt_from_real_video():
    for mode in (
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
    ):
        recovered = bot.subdub_restore_delivered_video_result(
            mode,
            {"ok": False, "status": "LATE_RUNTIME_ERROR"},
            _delivered_job(mode),
            {"mode": mode, "video_processing_mode": mode},
        )

        assert recovered["ok"] is True
        assert recovered["video_delivery_message_id"] == "701"
        assert recovered["state"]["panel_final_percent"] == 100
        assert "Đã gửi video" in bot.video_dubbing_receipt_text(recovered["state"], recovered, "vi")


def test_standalone_terminal_recovery_never_fakes_success_without_message_id():
    for mode in (
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
    ):
        original = {"ok": False, "status": "RENDER_FAILED"}
        recovered = bot.subdub_restore_delivered_video_result(
            mode,
            original,
            {"mode": mode, "terminal_state": "delivered", "final_mp4_delivered": True},
            {"mode": mode},
        )
        assert recovered == original


def test_combo_terminal_contract_remains_supported():
    mode = bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
    recovered = bot.subdub_restore_delivered_video_result(
        mode,
        {"ok": False, "status": "LATE_RUNTIME_ERROR"},
        _delivered_job(mode),
        {"mode": mode},
    )
    assert recovered["ok"] is True
    assert recovered["video_delivery_message_id"] == "701"
