from pathlib import Path

from services import subdub_provider_contract as contract


def _source_between(source: str, start: str, end: str) -> str:
    start_index = source.index(start)
    end_index = source.index(end, start_index)
    return source[start_index:end_index]


def test_key4u_contract_urls_are_exact():
    assert contract.key4u_asr("whisper-1").final_url == "https://api.key4u.shop/v1/audio/transcriptions"
    assert contract.key4u_openai_tts("gpt-4o-mini-tts").final_url == "https://api.key4u.shop/v1/audio/speech"
    assert contract.key4u_minimax_tts("speech-02-hd").final_url == "https://api.key4u.shop/minimax/v1/t2a_v2"
    assert contract.key4u_minimax_async("speech-02-hd").final_url == "https://api.key4u.shop/minimax/v1/t2a_async_v2"
    assert contract.key4u_minimax_query("speech-02-hd").final_url == "https://api.key4u.shop/minimax/v1/query/t2a_async_query_v2"
    assert contract.key4u_minimax_retrieve("speech-02-hd").final_url == "https://api.key4u.shop/minimax/v1/files/retrieve"


def test_shopaikey_contract_urls_keep_custom_tts_outside_v1():
    assert contract.shopaikey_asr("whisper-1").final_url == "https://api.shopaikey.com/v1/audio/transcriptions"
    assert contract.shopaikey_openai_tts("tts-1").final_url == "https://api.shopaikey.com/v1/audio/speech"
    assert contract.shopaikey_openai_custom_tts("tts-1").final_url == "https://api.shopaikey.com/tts/openai/speech"
    assert contract.shopaikey_minimax_tts("speech-02-hd").final_url == "https://api.shopaikey.com/tts/minimax/t2a_v2"
    assert contract.shopaikey_minimax_async("speech-02-hd").final_url == "https://api.shopaikey.com/tts/minimax/t2a_async_v2"
    assert contract.shopaikey_minimax_query("speech-02-hd").final_url == "https://api.shopaikey.com/tts/minimax/query/t2a_async_query_v2"
    assert contract.shopaikey_minimax_retrieve("speech-02-hd").final_url == "https://api.shopaikey.com/tts/minimax/files/retrieve"


def test_minimax_voice_id_preserves_underscores():
    voice_id = "Vietnamese_Cute_Girl_v1"

    assert contract.normalize_minimax_voice_id(voice_id) == voice_id
    assert contract.is_valid_minimax_voice_id(voice_id)


def test_legacy_minimax_default_maps_only_when_shopaikey_default_is_requested():
    chosen = contract.resolve_shopaikey_minimax_voice_id(
        requested_voice_id="female-shaonv",
        configured_default_voice="Vietnamese_Cute_Girl_v1",
        configured_female_voice="Vietnamese_Cute_Girl_v1",
        configured_male_voice="Vietnamese_Male_Narrator_v1",
        generic_legacy_voice_ids={"female-shaonv", "male-qn-qingse"},
    )

    assert chosen == "Vietnamese_Cute_Girl_v1"


def test_explicit_shopaikey_catalog_voice_is_never_rewritten():
    chosen = contract.resolve_shopaikey_minimax_voice_id(
        requested_voice_id="Vietnamese_Male_Narrator_v1",
        configured_default_voice="Vietnamese_Cute_Girl_v1",
        configured_female_voice="Vietnamese_Cute_Girl_v1",
        configured_male_voice="Vietnamese_Male_Narrator_v1",
        generic_legacy_voice_ids={"female-shaonv", "male-qn-qingse"},
    )

    assert chosen == "Vietnamese_Male_Narrator_v1"


def test_auto_remains_a_policy_state_not_a_paid_provider_choice():
    assert contract.normalize_subdub_provider_name("auto", capability="asr") == "auto"
    assert contract.normalize_subdub_provider_name("auto", capability="tts") == "auto"


def test_shopaikey_adapter_uses_its_own_endpoint_and_model_contract():
    source = Path("bot.py").read_text(encoding="utf-8")
    configured = _source_between(source, "def shopaikey_minimax_tts_configured", "def key4u_minimax_tts_configured")
    submit = _source_between(source, "async def shopaikey_minimax_tts_bytes", "async def direct_minimax_tts_bytes")

    assert "SHOPAIKEY_TTS_BASE_URL" in configured
    assert "SHOPAIKEY_TTS_ENDPOINT" in configured
    assert "SHOPAIKEY_TTS_MODEL" in configured
    assert "MINIMAX_TTS_ENDPOINT" not in configured
    assert "MINIMAX_TTS_MODEL" not in configured
    assert "shopaikey_tts_final_url(SHOPAIKEY_TTS_ENDPOINT)" in submit


def test_shopaikey_minimax_never_falls_back_to_direct_minimax():
    source = Path("bot.py").read_text(encoding="utf-8")
    submit = _source_between(source, "async def shopaikey_minimax_tts_bytes", "async def direct_minimax_tts_bytes")

    assert "direct_minimax_tts_configured" not in submit
    assert "call_direct_minimax_tts_bytes_with_speed" not in submit


def test_shopaikey_minimax_audit_uses_the_shopaikey_endpoint():
    source = Path("bot.py").read_text(encoding="utf-8")
    audit = _source_between(source, "def voice_curl_audit_route_plan", "async def voice_curl_audit_get_json")

    assert '"shopaikey_minimax_tts": shopaikey_tts_final_url(SHOPAIKEY_TTS_ENDPOINT)' in audit
    assert '"shopaikey_minimax_tts": shopaikey_tts_final_url(MINIMAX_TTS_ENDPOINT)' not in audit


def test_voice_adapter_does_not_rewrite_underscore_ids():
    source = Path("services/minimax_voice_adapter.py").read_text(encoding="utf-8")

    assert 'raw.replace("_", "-")' not in source
