import inspect
from pathlib import Path

import bot
from services import minimax_voice_adapter as voice_adapter
from services import provider_gate


def _labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_voice_default_female_resolves_provider_id():
    result = bot.video_b14_voice_resolution("default_female")
    assert result.ok is True
    assert result.provider_voice_id
    assert result.provider_voice_id != "default_female"
    assert voice_adapter.validate_provider_voice_id(result.provider_voice_id)


def test_voice_default_male_resolves_provider_id():
    result = bot.video_b14_voice_resolution("default_male")
    assert result.ok is True
    assert result.provider_voice_id
    assert result.provider_voice_id != "default_male"
    assert voice_adapter.validate_provider_voice_id(result.provider_voice_id)


def test_voice_saved_lists_friendly_names(monkeypatch):
    profile = {"id": 11, "display_name": "Voice ban hang", "provider_voice_id": "real-provider-voice-11", "status": "active"}
    monkeypatch.setattr(bot, "user_voice_profile_rows", lambda *_args, **_kwargs: [profile])
    monkeypatch.setattr(bot, "voice_profile_can_generate_tts", lambda row: bool(row.get("provider_voice_id")))

    labels = _labels(bot.video_b14_voice_select_keyboard(123, "vi"))
    callbacks = _callbacks(bot.video_b14_voice_select_keyboard(123, "vi"))
    entries = bot.voice_core_vault_lookup(123, source="saved", limit=5)

    assert any("Voice ban hang" in label for label in labels)
    assert "vproduct|b14_voice_saved_pick|11" in callbacks
    assert entries[0]["display_name"] == "Voice ban hang"


def test_voice_uploaded_missing_provider_id_safe():
    result = voice_adapter.resolve_provider_voice_id(
        voice_source="uploaded",
        uploaded_profile={"id": 9, "display_name": "Uploaded sample", "provider_voice_id": ""},
    )
    assert result.ok is False
    assert result.reason == "missing_provider_voice_id"
    assert "Voice này chưa sẵn sàng" in result.public_message
    assert not provider_gate.public_copy_has_technical_terms(result.public_message)


def test_voice_adapter_rejects_missing_provider_voice_id():
    result = voice_adapter.resolve_provider_voice_id(
        voice_source="saved",
        profile={"id": 7, "display_name": "Local only", "provider_voice_id": ""},
    )
    assert result.ok is False
    assert result.reason == "missing_provider_voice_id"

    local_id_result = voice_adapter.resolve_provider_voice_id(
        voice_source="saved",
        profile={"id": 7, "display_name": "Local id leaked", "provider_voice_id": "7"},
    )
    assert local_id_result.ok is False
    assert local_id_result.reason == "missing_provider_voice_id"


def test_voice_adapter_uses_provider_voice_id_not_local_id(tmp_path):
    calls = []
    profile = {"id": 55, "display_name": "Sales voice", "provider_voice_id": "real-provider-voice-55"}
    resolved = voice_adapter.resolve_provider_voice_id(voice_source="saved", profile=profile)

    def fake_tts(text, voice_id="", output_path="", **_kwargs):
        calls.append({"text": text, "voice_id": voice_id})
        payload = f"VOICE-PROVIDER:{voice_id}:{text}".encode("utf-8")
        Path(output_path).write_bytes(payload)
        return payload

    artifact = voice_adapter.synthesize_text_to_audio(
        text="Xin chao TOAN AAS",
        provider_voice_id=resolved.provider_voice_id,
        output_path=tmp_path / "saved.mp3",
        tts_func=fake_tts,
    )

    assert artifact.ok is True
    assert calls[0]["voice_id"] == "real-provider-voice-55"
    assert calls[0]["voice_id"] != str(profile["id"])


def test_voice_adapter_validates_nonzero_audio(tmp_path):
    output = tmp_path / "voice.mp3"
    artifact = voice_adapter.synthesize_text_to_audio(
        text="Xin chao",
        provider_voice_id="voice-ready-1",
        output_path=output,
        tts_func=lambda *_args, **_kwargs: b"VOICE-AUDIO-BYTES-READY",
    )
    assert artifact.ok is True
    assert artifact.size_bytes > 0
    assert voice_adapter.validate_audio_artifact(output).ok is True

    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")
    assert voice_adapter.validate_audio_artifact(empty).ok is False


def test_voice_preview_no_silent_charge():
    silent = bot.voice_core_preview_policy(explicit=False, max_seconds=6)
    explicit = bot.voice_core_preview_policy(explicit=True, max_seconds=6)
    gate = provider_gate.evaluate_provider_gate(
        context=provider_gate.PREVIEW_CONFIRMED,
        configured=True,
        public_ready=True,
        preview_confirmed=False,
        preview_no_charge=False,
    )

    assert silent.allowed is False
    assert "không trừ Xu âm thầm" in silent.public_message
    assert gate.allowed is False
    assert explicit.allowed is True
    assert explicit.no_charge is True
    assert explicit.max_seconds <= 6


def test_custom_voice_locked_has_fallback():
    state = bot.custom_voice_core_state(
        {"ready": False, "public_enabled": False, "provider_permission_blocker": "clone_permission_forbidden"},
        public=True,
    )
    assert state.ready is False
    assert state.locked is True
    assert state.fallback_available is True
    assert "giọng nữ/nam mặc định" in state.public_message
    assert not provider_gate.public_copy_has_technical_terms(state.public_message)


def test_custom_voice_no_fake_success():
    locked = bot.custom_voice_core_state({"ready": False, "public_enabled": False, "reason": "fake_locked"}, public=True)
    assert locked.ready is False
    assert locked.locked is True

    failed_artifact = voice_adapter.synthesize_text_to_audio(
        text="Xin chao",
        provider_voice_id="voice-ready-1",
        output_path="",
        tts_func=lambda *_args, **_kwargs: b"",
    )
    assert failed_artifact.ok is False


def test_p0_19a_admin_voice_commands_registered():
    source = Path(bot.__file__).read_text(encoding="utf-8")
    for command in (
        "tool_test_voice_gate",
        "tool_test_minimax_adapter",
        "tool_test_voice_vault_lookup",
        "tool_test_voice_default_tts",
        "tool_test_voice_preview_policy",
        "tool_test_custom_voice_flow",
    ):
        assert f'CommandHandler("{command}"' in source
    assert "--fake" in inspect.getsource(bot.cmd_tool_test_voice_default_tts)
    assert "--fake" in inspect.getsource(bot.cmd_tool_test_voice_preview_policy)
    assert "--fake" in inspect.getsource(bot.cmd_tool_test_custom_voice_flow)
