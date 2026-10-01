import asyncio
from types import SimpleNamespace

import bot


def test_doc_split_back_releases_page_prompt_and_keeps_files_and_options(monkeypatch):
    monkeypatch.setattr(bot, "USER_PENDING", {})
    user_id = 941130
    files = [{"file_id": "keep-file", "file_name": "input.pdf"}]
    options = {"preserved_option": "value"}
    bot.set_doc_tool_pending(
        user_id,
        "split_pdf",
        doc_tool_files=files,
        doc_tool_options=options,
        awaiting_page_spec="1",
    )
    monkeypatch.setattr(bot, "get_user_language", lambda _uid: "vi")

    async def answer(*_args, **_kwargs):
        return None

    async def edit(*_args, **_kwargs):
        return None

    async def reply_text(*_args, **_kwargs):
        return None

    monkeypatch.setattr(bot, "safe_edit_or_send", edit)
    monkeypatch.setattr(bot, "doc_tool_received_text", lambda *_args: "received files")
    monkeypatch.setattr(bot, "doc_tool_after_file_keyboard", lambda *_args: object())
    monkeypatch.setattr(bot, "doc_tool_confirm_text", lambda *_args: "confirm")
    monkeypatch.setattr(bot, "doc_tool_confirm_keyboard", lambda *_args: object())
    query = SimpleNamespace(
        data="docflow|back_received",
        from_user=SimpleNamespace(id=user_id),
        answer=answer,
    )
    asyncio.run(bot.handle_doc_tool_callback(
        SimpleNamespace(callback_query=query),
        SimpleNamespace(),
    ))

    ordinary_message = SimpleNamespace(text="nội dung bình thường", reply_text=reply_text)
    consumed = asyncio.run(bot.handle_doc_tool_pending_text(
        SimpleNamespace(effective_user=SimpleNamespace(id=user_id), message=ordinary_message),
        SimpleNamespace(),
    ))
    state = bot.get_doc_tool_pending(user_id)

    assert consumed is False
    assert state.get("awaiting_page_spec") != "1"
    assert state["doc_tool_files"] == files
    assert state["doc_tool_options"] == options
