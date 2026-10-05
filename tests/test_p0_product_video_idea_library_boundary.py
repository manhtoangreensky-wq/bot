"""Test suite for S02: Enforcing video_idea as a shared content library only.

SPEC_ID: PRODUCT-VIDEO-S02-IDEA-LIBRARY-BOUNDARY
Governed by: owner-governed-codex, locked-focus-engineering

Invariants:
1. STANDALONE_IDEA_JOB_CREATION=0
2. STANDALONE_IDEA_PROVIDER_CALL=0
3. STANDALONE_IDEA_QUOTE_OR_CHARGE=0
4. Root browse/detail/select/back/cancel creates zero standalone paid/render side effects.
5. Catalog rows, categories, presets, and compatibility aliases are preserved.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import bot
from services import video_idea_catalog, video_idea_store


@pytest.fixture(autouse=True)
def setup_idea_env(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_idea_boundary.db")
    monkeypatch.setenv("DB_FILE", test_db)
    monkeypatch.setattr(bot, "DB_FILE", test_db)
    bot.init_db()


def test_idea_catalog_data_preserved():
    """Verify catalog seeds, categories, and presets exist and are not deleted."""
    categories = video_idea_catalog.dynamic_category_seeds()
    assert len(categories) > 0, "Idea categories must not be empty"

    presets = video_idea_catalog.dynamic_preset_seeds()
    assert len(presets) > 0, "Idea presets must not be empty"

    category_keys = {cat["category_key"] for cat in categories}
    assert "sales" in category_keys or "commercial" in category_keys or "business" in category_keys


def test_root_browse_creates_zero_standalone_job_or_charge():
    """Prove that browsing video_idea root creates zero jobs, zero provider calls, zero charges."""
    mock_update = MagicMock()
    mock_query = MagicMock()
    mock_query.data = "videoidea|start"
    mock_query.from_user.id = 99999
    mock_query.message.chat_id = 99999
    mock_query.answer = AsyncMock()
    mock_query.edit_message_text = AsyncMock()
    mock_update.callback_query = mock_query

    mock_context = MagicMock()
    mock_context.user_data = {}

    with patch.object(bot, "create_video_job", return_value=1) as mock_job, \
         patch.object(bot, "spend_fixed_credit", return_value=True) as mock_spend, \
         patch.object(bot, "execute_engine", new_callable=AsyncMock) as mock_engine, \
         patch.object(bot, "safe_edit_or_send", new_callable=AsyncMock) as mock_send:

        asyncio.run(bot.handle_video_idea_callback(mock_update, mock_context))

        assert mock_job.call_count == 0, "Root browse must not create video job"
        assert mock_spend.call_count == 0, "Root browse must not charge wallet"
        assert mock_engine.call_count == 0, "Root browse must not call provider engine"


def test_category_and_preset_view_zero_side_effects():
    """Prove that navigating categories and presets creates zero standalone jobs or debits."""
    mock_update = MagicMock()
    mock_query = MagicMock()
    mock_query.data = "videoidea|cat|sales"
    mock_query.from_user.id = 99999
    mock_query.message.chat_id = 99999
    mock_query.answer = AsyncMock()
    mock_query.edit_message_text = AsyncMock()
    mock_update.callback_query = mock_query

    mock_context = MagicMock()
    mock_context.user_data = {}

    with patch.object(bot, "create_video_job") as mock_job, \
         patch.object(bot, "spend_fixed_credit") as mock_spend, \
         patch.object(bot, "execute_engine", new_callable=AsyncMock) as mock_engine, \
         patch.object(bot, "safe_edit_or_send_long_html", new_callable=AsyncMock):

        asyncio.run(bot.handle_video_idea_callback(mock_update, mock_context))

        assert mock_job.call_count == 0
        assert mock_spend.call_count == 0
        assert mock_engine.call_count == 0


def test_uiflow3_entry_rejects_standalone_video_idea_execution():
    """Prove that UIFLOW3 explicitly blocks video_idea as a standalone execution target."""
    mock_update = MagicMock()
    mock_query = MagicMock()
    mock_query.data = "vid3|entry|video_idea"
    mock_query.from_user.id = 99999
    mock_query.message.chat_id = 99999
    mock_query.answer = AsyncMock()
    mock_update.callback_query = mock_query

    mock_context = MagicMock()
    mock_context.user_data = {}

    with patch.object(bot, "start_video_uiflow3_state") as mock_start:
        asyncio.run(bot.handle_video_uiflow3_callback(mock_update, mock_context))

        mock_query.answer.assert_called_once()
        alert_msg = mock_query.answer.call_args[0][0]
        assert "quy trình riêng" in alert_msg or "không sửa nội dung gốc trong kho" in alert_msg
        assert mock_start.call_count == 0, "video_idea must not start standalone UIFLOW3 state"
