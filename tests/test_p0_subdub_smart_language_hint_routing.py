"""Verify production request construction without bootstrapping paid clients."""
import asyncio
import copy
from types import SimpleNamespace

import pytest

from test_p0_subdub_auto_asr_timeout_boundary import (
    _FakeAsyncClient, _load_asr_forwarding_surface, _load_deepgram_timeout_surface,
)


@pytest.mark.parametrize("language", ["zh", "es", "fr", "vi", "en-US"])
def test_explicit_language_reaches_request_and_disables_detection(language):
    ns = _load_deepgram_timeout_surface()
    before = copy.deepcopy(ns["AgentDeepgram"].REQUEST_PARAMS)
    params = ns["subdub_deepgram_request_params"](language=language)
    assert params["language"] == language
    assert "detect_language" not in params
    assert ns["AgentDeepgram"].REQUEST_PARAMS == before


@pytest.mark.parametrize("language", ["", "auto", None])
def test_auto_request_remains_byte_for_byte_equivalent(language):
    ns = _load_deepgram_timeout_surface()
    assert ns["subdub_deepgram_request_params"](language=language) == ns["AgentDeepgram"].REQUEST_PARAMS


def test_diarization_and_timeout_still_forward_with_explicit_language():
    ns = _load_deepgram_timeout_surface()
    requests = []

    class Client(_FakeAsyncClient):
        should_timeout = False

        async def post(self, *args, **kwargs):
            requests.append(kwargs)
            return await super().post(*args, **kwargs)

    ns["httpx"].AsyncClient = Client
    ns["deepgram_word_items"] = lambda _data: [{"speaker": 0}]
    result = asyncio.run(ns["deepgram_asr_adapter"](
        b"fixture", "audio/wav", language="zh", require_diarization=True, timeout_seconds=123,
    ))
    assert result["ok"], result
    assert len(requests) == 1
    assert requests[0]["params"]["language"] == "zh"
    assert "detect_language" not in requests[0]["params"]
    assert requests[0]["params"]["diarize_model"] == "latest"
    assert requests[0]["timeout"] == 123


@pytest.mark.parametrize("flags", [{}, {"require_diarization": True}, {"require_auto_multi_word_timeline": True}])
def test_asr_forwards_explicit_language_in_each_deepgram_route(flags):
    asr, _ = _load_asr_forwarding_surface()
    calls = []

    async def adapter(*_args, **kwargs):
        calls.append(kwargs)
        return {"ok": False, "status": "deepgram_timeout", "transcript": "", "transcript_json": {}}

    asr.__globals__["ASR_PROVIDER"] = "deepgram"
    asr.__globals__["deepgram_asr_adapter"] = adapter
    asyncio.run(asr(b"fixture", language="zh", allow_confirmed_product=True, **flags))
    assert len(calls) == 1
    assert calls[0]["language"] == "zh"


def test_default_call_does_not_break_existing_two_argument_adapter():
    asr, _ = _load_asr_forwarding_surface()
    calls = []

    async def old_adapter(audio, content_type):
        calls.append((audio, content_type))
        return {"ok": False, "status": "deepgram_timeout", "transcript": "", "transcript_json": {}}

    asr.__globals__["ASR_PROVIDER"] = "deepgram"
    asr.__globals__["deepgram_asr_adapter"] = old_adapter
    asyncio.run(asr(b"fixture"))
    assert len(calls) == 1
