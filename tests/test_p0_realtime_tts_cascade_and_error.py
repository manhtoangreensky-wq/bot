"""Unit tests for Realtime TTS provider forwarding and error propagation."""

from __future__ import annotations

import asyncio
import base64
import sys
from types import ModuleType

from services.realtime_tts_adapter import (
    RealtimeTTSAdapter,
    get_canonical_tts_primitive,
    set_canonical_tts_primitive,
)
from services.realtime_voice_resolution import ResolvedVoice


def test_realtime_tts_adapter_forwards_voice_metadata_and_propagates_error(monkeypatch):
    calls = []

    async def rich_primitive(text, *, voice_id="", gender="male", language_code="vi", voice_vault_id="", speed=1.0):
        calls.append((text, voice_id, gender, language_code, voice_vault_id, speed))
        if text == "fail":
            return ("FAIL", b"", "upstream_403", 403)
        return ("PASS", b"MP3AUDIOBYTES", "shopaikey_minimax", 200)

    fake_bot = ModuleType("bot")
    fake_bot.realtime_dub_tts_bytes = rich_primitive
    monkeypatch.setitem(sys.modules, "bot", fake_bot)
    set_canonical_tts_primitive(None)

    async def _run():
        assert get_canonical_tts_primitive() is rich_primitive
        voice = ResolvedVoice(
            voice_id="vault-voice-123",
            provider="voice_vault",
            gender="female",
            language_code="vi",
            voice_vault_id="vp_01",
            speed=1.1,
        )
        adapter = RealtimeTTSAdapter()
        ok_res = await adapter.synthesize("Xin chào", voice=voice)
        assert ok_res.ok is True
        assert base64.b64decode(ok_res.audio_base64 or "") == b"MP3AUDIOBYTES"
        assert calls[0] == ("Xin chào", "vault-voice-123", "female", "vi", "vp_01", 1.1)

        bad_res = await adapter.synthesize("fail", voice=voice)
        assert bad_res.ok is False
        assert bad_res.audio_base64 is None
        assert bad_res.error == "upstream_403"

    try:
        asyncio.run(_run())
    finally:
        set_canonical_tts_primitive(None)
