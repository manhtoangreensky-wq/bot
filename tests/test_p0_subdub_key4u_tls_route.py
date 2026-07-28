import inspect
from pathlib import Path

from providers.key4u_provider import Key4UProvider, config_from_env


def test_key4u_minimax_tts_uses_tls_valid_canonical_host(monkeypatch):
    monkeypatch.setenv("KEY4U_BASE_URL", "https://api.key4u.shop")
    monkeypatch.delenv("KEY4U_MINIMAX_BASE", raising=False)
    monkeypatch.delenv("KEY4U_MINIMAX_TTS_BASE", raising=False)

    config = config_from_env()
    provider = Key4UProvider(config)

    assert config.base_url == "https://api.key4u.shop"
    assert config.minimax_base_url == "https://api.key4u.shop/minimax"
    assert config.minimax_tts_base_url == "https://api.key4u.vn/minimax"
    assert provider._tts_url(config.tts_endpoint) == "https://api.key4u.vn/minimax/v1/t2a_v2"
    assert provider.get_status()["minimax_tts_final_url"] == "https://api.key4u.vn/minimax/v1/t2a_v2"


def test_key4u_minimax_tts_has_no_tls_bypass_or_paid_fallback():
    submit_source = inspect.getsource(Key4UProvider.tts)

    assert "verify=False" not in submit_source
    assert "voice_tts_fallback" not in submit_source


def test_bot_wires_the_tts_specific_key4u_minimax_base():
    source = Path("bot.py").read_text(encoding="utf-8")

    assert 'KEY4U_MINIMAX_TTS_BASE_URL = _env("KEY4U_MINIMAX_TTS_BASE", "https://api.key4u.vn/minimax")' in source
    assert "minimax_tts_base_url=KEY4U_MINIMAX_TTS_BASE_URL" in source
