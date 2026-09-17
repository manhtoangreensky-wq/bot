from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import bot


def _make_session(user_id: int) -> dict:
    return {
        "user_id": user_id,
        "draft": {
            "script_topic": "Gốm Bát Tràng thủ công",
            "script_duration_seconds": 30,
            "script_entry_scene_count": 5,
            "script_ai_revision": 1,
        },
    }


@pytest.mark.anyio
async def test_video_script_generate_ai_exception_fail_closed():
    user_id = 999111
    session = _make_session(user_id)
    query = MagicMock()

    with (
        patch("bot.generate_video_script_pack", new_callable=AsyncMock) as mock_gen,
        patch("bot.task3d_session_step") as mock_step,
        patch("bot.safe_edit_or_send", new_callable=AsyncMock) as mock_send,
        patch("bot.video_script_duration_keyboard", return_value=MagicMock()),
    ):
        mock_gen.side_effect = RuntimeError("AI Provider timeout")
        mock_step.return_value = {"user_id": user_id}

        await bot.video_script_generate_ai(query, user_id, session, "vi")

        mock_step.assert_called_once()
        kwargs = mock_step.call_args[1]
        assert kwargs.get("script_text") == ""
        assert kwargs.get("manual_script_raw") == ""
        assert kwargs.get("provider_called") is True
        assert kwargs.get("script_provider_error") == "RuntimeError"
        assert kwargs.get("job_created") is False
        assert kwargs.get("outbox_created") is False
        assert kwargs.get("xu_charged") == 0

        assert mock_send.call_count >= 1
        last_send_call = mock_send.call_args[0][1]
        assert "Chưa tạo được kịch bản từ nguồn AI" in last_send_call
        assert "Chưa tạo video và chưa trừ Xu" in last_send_call


@pytest.mark.anyio
async def test_video_script_generate_ai_empty_script_fail_closed():
    user_id = 999112
    session = _make_session(user_id)
    query = MagicMock()

    with (
        patch("bot.generate_video_script_pack", new_callable=AsyncMock) as mock_gen,
        patch("bot.task3d_session_step") as mock_step,
        patch("bot.safe_edit_or_send", new_callable=AsyncMock) as mock_send,
        patch("bot.video_script_duration_keyboard", return_value=MagicMock()),
    ):
        mock_gen.return_value = "   "
        mock_step.return_value = {"user_id": user_id}

        await bot.video_script_generate_ai(query, user_id, session, "vi")

        mock_step.assert_called_once()
        kwargs = mock_step.call_args[1]
        assert kwargs.get("script_text") == ""
        assert kwargs.get("manual_script_raw") == ""
        assert kwargs.get("provider_called") is True
        assert kwargs.get("script_provider_error") == "empty_script"
        assert kwargs.get("job_created") is False
        assert kwargs.get("outbox_created") is False
        assert kwargs.get("xu_charged") == 0

        assert mock_send.call_count >= 1
        last_send_call = mock_send.call_args[0][1]
        assert "Nguồn AI chưa trả về kịch bản có nội dung" in last_send_call
        assert "Chưa tạo video và chưa trừ Xu" in last_send_call


@pytest.mark.anyio
async def test_video_script_generate_ai_invalid_proposal_fail_closed():
    user_id = 999113
    session = _make_session(user_id)
    query = MagicMock()

    with (
        patch("bot.generate_video_script_pack", new_callable=AsyncMock) as mock_gen,
        patch("bot.video_flow7_store_script_proposal") as mock_store,
        patch("bot.task3d_session_step") as mock_step,
        patch("bot.safe_edit_or_send", new_callable=AsyncMock) as mock_send,
        patch("bot.video_script_duration_keyboard", return_value=MagicMock()),
    ):
        mock_gen.return_value = "Some unparseable text without scene structure"
        mock_store.return_value = (False, {})  # No scenes parsed
        mock_step.return_value = {"user_id": user_id}

        await bot.video_script_generate_ai(query, user_id, session, "vi")

        mock_step.assert_called_once()
        kwargs = mock_step.call_args[1]
        assert kwargs.get("script_text") == ""
        assert kwargs.get("manual_script_raw") == ""
        assert kwargs.get("provider_called") is True
        assert kwargs.get("script_provider_error") == "invalid_proposal"
        assert kwargs.get("job_created") is False
        assert kwargs.get("outbox_created") is False
        assert kwargs.get("xu_charged") == 0

        assert mock_send.call_count >= 1
        last_send_call = mock_send.call_args[0][1]
        assert "Kịch bản AI chưa đạt chuẩn cấu trúc cảnh" in last_send_call
        assert "Chưa tạo video và chưa trừ Xu" in last_send_call


@pytest.mark.anyio
async def test_video_script_generate_ai_success():
    user_id = 999114
    session = _make_session(user_id)
    query = MagicMock()
    valid_script = "Cảnh 1: Mở đầu ấn tượng. Cảnh 2: Trình bày sản phẩm."

    with (
        patch("bot.generate_video_script_pack", new_callable=AsyncMock) as mock_gen,
        patch("bot.video_flow7_store_script_proposal") as mock_store,
        patch("bot.task3d_session_step") as mock_step,
        patch("bot.safe_edit_or_send", new_callable=AsyncMock) as mock_send,
        patch("bot.video_script_render_step", new_callable=AsyncMock) as mock_render,
    ):
        mock_gen.return_value = valid_script
        mock_store.return_value = (True, {"scenes": ["Cảnh 1: Mở đầu", "Cảnh 2: Trình bày"]})
        mock_step.return_value = {"user_id": user_id, "current_step": "script_ai_review"}

        await bot.video_script_generate_ai(query, user_id, session, "vi")

        mock_step.assert_called_once()
        step_name = mock_step.call_args[0][1]
        assert step_name == "script_ai_review"
        kwargs = mock_step.call_args[1]
        assert kwargs.get("script_text") == valid_script
        assert kwargs.get("script_source") == "ai"
        mock_render.assert_called_once()
