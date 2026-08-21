from __future__ import annotations

import asyncio
from pathlib import Path

import providers.key4u_provider as key4u_module
from providers.key4u_provider import Key4UConfig, Key4UProvider
from services import public_chat_runtime


class _Response:
    status_code = 200
    headers: dict[str, str] = {}

    def json(self):
        return {
            "choices": [{"message": {"content": "Xin chào"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3},
        }


class _Client:
    calls: list[dict] = []

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return _Response()


def test_key4u_success_without_server_id_keeps_client_correlation_id(monkeypatch):
    _Client.calls = []
    monkeypatch.setattr(key4u_module.httpx, "AsyncClient", _Client)
    provider = Key4UProvider(
        Key4UConfig(enabled=True, public_enabled=True, api_key="test-key")
    )

    result = asyncio.run(
        provider.public_chat_completion([{"role": "user", "content": "alo"}])
    )

    assert result["ok"] is True
    assert result["provider_request_id"].startswith("client-")
    assert _Client.calls[0]["headers"]["X-Client-Request-Id"] == result["provider_request_id"]


def test_free_has_full_output_budget_without_increasing_pro_reserve_budget(monkeypatch):
    seen: dict[str, int] = {}

    async def free_call(_client, **kwargs):
        seen["free"] = kwargs["max_output_tokens"]
        return {"ok": True, "text": "ok"}

    class Pro:
        async def public_chat_completion(self, messages, *, max_tokens, **_kwargs):
            seen["pro"] = max_tokens
            return {"ok": True, "text": "ok"}

    monkeypatch.setattr(public_chat_runtime, "generate_public_chat_text", free_call)
    common = {
        "system_prompt": "system",
        "messages": [{"role": "user", "content": "alo"}],
        "attachments": (),
    }
    asyncio.run(
        public_chat_runtime._call_provider(
            mode="free", gemini_client=object(), key4u_provider=None, **common
        )
    )
    asyncio.run(
        public_chat_runtime._call_provider(
            mode="pro", gemini_client=None, key4u_provider=Pro(), **common
        )
    )

    assert seen == {"free": 4096, "pro": 1200}


def test_system_prompt_prioritizes_latest_message_and_complete_answer():
    prompt = public_chat_runtime.public_chat_system_prompt("vi").lower()
    assert "latest user message" in prompt
    assert "complete" in prompt


def test_long_text_is_split_without_loss_and_prefers_readable_boundaries():
    text = ("đây là một câu trả lời dài. " * 400).strip()
    chunks = public_chat_runtime.split_public_chat_text(text, limit=300)

    assert len(chunks) > 1
    assert all(len(chunk) <= 300 for chunk in chunks)
    assert "".join(chunks) == text
    assert all(not chunk.startswith(" ") for chunk in chunks[1:])


def test_public_chat_chunks_are_sent_as_plain_text():
    source = (Path(__file__).parents[1] / "bot.py").read_text(encoding="utf-8")
    block = source[
        source.index("async def send_public_chat_text") : source.index(
            "async def handle_public_chat_text"
        )
    ]
    assert "reply_text(chunk, parse_mode=None)" in block
