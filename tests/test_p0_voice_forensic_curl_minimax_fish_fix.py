import asyncio
import inspect
import json
from pathlib import Path

import bot


def test_shopaikey_audio_speech_uses_v1_base_without_double_v1(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_BASE_URL", "https://api.shopaikey.com/v1")
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_BASE_URL", "https://api.shopaikey.com")
    assert bot.shopaikey_tts_final_url("/audio/speech") == "https://api.shopaikey.com/v1/audio/speech"
    assert bot.shopaikey_tts_final_url("/v1/audio/speech") == "https://api.shopaikey.com/v1/audio/speech"
    assert not bot.voice_route_has_duplicate_v1(bot.shopaikey_tts_final_url("/v1/audio/speech"))


def test_shopaikey_minimax_tts_stays_on_media_base(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_BASE_URL", "https://api.shopaikey.com/v1")
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_BASE_URL", "https://api.shopaikey.com")
    assert bot.shopaikey_tts_final_url("/tts/minimax/t2a_v2") == "https://api.shopaikey.com/tts/minimax/t2a_v2"


def test_voice_route_result_requires_audio_bytes_for_audio_pass():
    empty = bot.voice_route_result(
        "ShopAIKey",
        "/audio/speech",
        status="PASS",
        http_status=200,
        output_bytes=0,
        requires_audio=True,
    )
    assert empty["status"] == "FAIL_EMPTY_AUDIO"
    assert empty["pass"] is False

    real = bot.voice_route_result(
        "ShopAIKey",
        "/audio/speech",
        status="PASS",
        http_status=200,
        output_bytes=128,
        requires_audio=True,
    )
    assert real["status"] == "PASS"
    assert real["pass"] is True


def test_voice_route_result_detects_bad_double_v1_url():
    result = bot.voice_route_result(
        "ShopAIKey",
        "base /models",
        url="https://api.shopaikey.com/v1/v1/models",
        status="PASS",
        http_status=200,
    )
    assert result["status"] == "FAIL_BAD_URL"
    assert result["pass"] is False
    assert result["reason"] == "duplicate_v1_in_route"


def test_minimax_voice_id_is_hyphen_only_and_deterministic():
    voice_id = bot.make_minimax_voice_id("admin_123", profile_id="profile_42", timestamp_text="20260623010101")
    assert voice_id.startswith("toanaas-voice-admin123-20260623010101-profile-42")
    assert "_" not in voice_id
    assert len(voice_id) <= 128


def test_minimax_clone_parser_prefers_returned_provider_voice_id():
    payload = {"data": {"voice": {"voice_id": "provider-returned-voice-123"}}}
    assert bot.extract_minimax_returned_voice_id(payload, "requested-voice") == "provider-returned-voice-123"
    assert bot.extract_minimax_returned_voice_id({}, "requested-voice") == "requested-voice"


def test_voice_curl_audit_skip_does_not_call_paid_routes(monkeypatch):
    monkeypatch.setattr(bot, "SHOPAIKEY_API_KEY", "sk-secret-shopaikey")
    monkeypatch.setattr(bot, "SHOPAIKEY_ENABLED", True)
    monkeypatch.setattr(bot, "SHOPAIKEY_TTS_ENABLED", True)
    results = asyncio.run(bot.run_voice_curl_audit(confirm_paid=False, user_id=1))
    assert results
    assert all(item["called"] is False for item in results)
    assert any(item["status"] == "NO_CONFIRM" for item in results)
    text = "\n".join(bot.voice_curl_audit_text(results, confirm_paid=False))
    assert "sk-secret-shopaikey" not in text
    assert "--confirm-paid" in text


def test_voice_curl_audit_records_audio_pass_only_with_bytes():
    results = [
        bot.voice_route_result("Edge TTS", "edge fallback", status="PASS", output_bytes=0, requires_audio=True),
        bot.voice_route_result("Fish Audio", "/v1/tts", status="PASS", http_status=200, output_bytes=777, requires_audio=True),
    ]
    summary = bot.voice_curl_audit_summary(results)
    assert summary["status"] == "PASS"
    assert summary["audio_pass"] is True


def test_voice_curl_audit_command_admin_only_and_registered():
    source = inspect.getsource(bot.cmd_voice_curl_audit)
    assert "is_admin_user" in source
    assert "has_admin_paid_confirmation" in source
    assert "resolve_stt_test_media" in source
    assert 'CommandHandler("voice_curl_audit", cmd_voice_curl_audit)' in inspect.getsource(bot.lifespan)


def test_voice_provider_status_reports_adapter_missing_without_secret(monkeypatch):
    monkeypatch.setattr(bot, "FISH_AUDIO_KEY", "fish-secret-value")
    monkeypatch.setattr(bot, "tts_fish_audio_bytes", None)
    deps = bot.voice_provider_dependency_status()
    assert deps["fish_audio"]["status"] == "adapter_missing"
    fish_routes = [item for item in bot.voice_curl_audit_skip_results() if item["provider"] == "Fish Audio"]
    assert fish_routes[0]["status"] == "ADAPTER_MISSING"
    status_text = "\n".join(bot.voice_engine_status_lines())
    assert "fish-secret-value" not in status_text


def test_saved_cloned_voice_does_not_claim_edge_fallback():
    source = inspect.getsource(bot.synthesize_standalone_tts_audio)
    edge_index = source.index("tts_edge_bytes")
    default_gate_index = source.index("if is_default_female or is_default_male")
    assert default_gate_index < edge_index
    assert "profile.get(\"provider_voice_id\")" in inspect.getsource(bot.send_paid_saved_voice_tts_result)


def test_prompt_vault_contains_tiktok_viral_seed_prompts():
    data = json.loads((Path(bot.__file__).parent / "data" / "prompt_vault" / "prompts.json").read_text(encoding="utf-8"))
    ids = {item["id"] for item in data["prompts"]}
    assert {
        "viral_hook_0_3s_001",
        "viral_short_script_8_20s_001",
        "viral_light_controversy_001",
        "viral_caption_hashtag_001",
        "viral_series_ideas_001",
        "viral_post_analysis_001",
    }.issubset(ids)
