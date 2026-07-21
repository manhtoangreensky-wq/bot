import inspect
import io
import sys
import time
import wave

import bot
from providers.voxcpm2_tts_provider import VoxCPM2Config, VoxCPM2TTSProvider


def _wav_bytes(seconds=0.08, sample_rate=16000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * max(1, int(sample_rate * seconds)))
    return buffer.getvalue()


class StubVoxModel:
    def __init__(self):
        self.calls = []

    def synthesize_to_file(self, **kwargs):
        self.calls.append(kwargs)
        output_path = kwargs["output_path"]
        with open(output_path, "wb") as handle:
            handle.write(_wav_bytes())


class BytesVoxModel:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def synthesize(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


def _enabled_config(**overrides):
    data = {
        "enabled": True,
        "model_path": "stub-model",
        "timeout_seconds": 3,
        "admin_only": True,
        "supported_genders": ("female", "male", "neutral"),
    }
    data.update(overrides)
    return VoxCPM2Config(**data)


def test_voxcpm2_disabled_does_not_import_heavy_model(monkeypatch):
    sys.modules.pop("voxcpm", None)
    provider = VoxCPM2TTSProvider(VoxCPM2Config(enabled=False), model_loader=lambda _cfg: (_ for _ in ()).throw(AssertionError("must not load")))
    result = provider.synthesize("Xin chao", admin=True)
    assert result.ok is False
    assert result.error_code == "adapter_disabled"
    assert "voxcpm" not in sys.modules
    assert provider.lazy_loaded is False


def test_voxcpm2_missing_model_clean_unavailable(tmp_path):
    missing = tmp_path / "missing-model"
    provider = VoxCPM2TTSProvider(VoxCPM2Config(enabled=True, model_path=str(missing), admin_only=True))
    result = provider.synthesize("Xin chao", admin=True)
    assert result.ok is False
    assert result.error_code == "adapter_unavailable"
    assert result.public_message
    assert str(missing) not in result.public_message
    assert provider.lazy_loaded is False


def test_voxcpm2_lazy_load_only_when_used():
    calls = []
    model = StubVoxModel()
    provider = VoxCPM2TTSProvider(_enabled_config(), model_loader=lambda _cfg: calls.append("load") or model)
    assert provider.status()["lazy_loaded"] is False
    assert calls == []

    first = provider.synthesize("Xin chao", gender="female", admin=True)
    second = provider.synthesize("Xin chao lan nua", gender="female", admin=True)

    assert first.ok is True
    assert second.ok is True
    assert calls == ["load"]
    assert provider.lazy_loaded is True


def test_voxcpm2_synthesize_returns_valid_artifact_with_stub():
    model = StubVoxModel()
    provider = VoxCPM2TTSProvider(_enabled_config(), model_loader=lambda _cfg: model)
    result = provider.synthesize("Xin chao TOAN AAS", language="vi", gender="female", voice_id="exact-female-voice", admin=True)
    assert result.ok is True
    assert result.audio_path
    assert result.bytes > 16
    assert result.duration > 0
    assert result.sample_rate == 16000
    assert result.provider_name == "voxcpm2_local"
    assert model.calls[-1]["voice_id"] == "exact-female-voice"


def test_voxcpm2_validates_bytes_duration():
    provider = VoxCPM2TTSProvider(_enabled_config(), model_loader=lambda _cfg: BytesVoxModel(b"not-a-valid-wave-but-long-enough"))
    result = provider.synthesize("Xin chao", gender="female", admin=True)
    assert result.ok is False
    assert result.error_code == "duration_missing"


def test_voxcpm2_timeout_returns_clean_error():
    class SlowModel:
        def synthesize_to_file(self, **kwargs):
            time.sleep(1.2)
            with open(kwargs["output_path"], "wb") as handle:
                handle.write(_wav_bytes())

    provider = VoxCPM2TTSProvider(_enabled_config(timeout_seconds=1), model_loader=lambda _cfg: SlowModel())
    started = time.time()
    result = provider.synthesize("Xin chao", gender="female", admin=True)
    assert result.ok is False
    assert result.error_code == "timeout"
    assert time.time() - started < 1.5


def test_voxcpm2_no_startup_crash_when_deps_missing(monkeypatch):
    sys.modules.pop("voxcpm", None)
    provider = VoxCPM2TTSProvider(VoxCPM2Config(enabled=False))
    status = provider.status()
    assert status["enabled"] is False
    assert status["lazy_loaded"] is False


def test_tts_provider_selection_uses_exact_voice_id_first():
    model = StubVoxModel()
    provider = VoxCPM2TTSProvider(_enabled_config(), model_loader=lambda _cfg: model)
    result = provider.synthesize("Xin chao", gender="female", voice_id="exact-provider-voice", admin=True)
    assert result.ok is True
    assert result.resolved_voice_id == "exact-provider-voice"
    assert model.calls[-1]["voice_id"] == "exact-provider-voice"


def test_subdub_female_does_not_silently_resolve_male():
    provider = VoxCPM2TTSProvider(
        _enabled_config(supported_genders=("male",)),
        model_loader=lambda _cfg: StubVoxModel(),
    )
    result = provider.synthesize("Xin chao", gender="female", admin=True)
    assert result.ok is False
    assert result.error_code == "gender_unavailable"
    assert result.fallback_used is False
    assert result.resolved_gender == ""


def test_subdub_can_fallback_to_voxcpm2_when_enabled():
    provider = VoxCPM2TTSProvider(_enabled_config(), model_loader=lambda _cfg: StubVoxModel())
    result = provider.synthesize("Fallback local voice", language="vi", gender="male", admin=True)
    assert result.ok is True
    assert result.resolved_gender == "male"
    assert result.bytes > 0


def test_voice_debug_records_provider_internal_only():
    text = bot.subdub_voice_debug_text({
        "internal_job_id": "subdub-vox",
        "selected_voice_gender": "female",
        "resolved_gender": "female",
        "tts_backend": "voxcpm2_local",
        "voxcpm2_enabled": True,
        "voxcpm2_lazy_loaded": True,
        "voxcpm2_fallback_used": True,
        "voxcpm2_fallback_reason": "paid_provider_unavailable",
        "audio_bytes": 1234,
    })
    assert "voxcpm2_local" in text
    assert "voxcpm2_fallback_reason" in text


def test_public_copy_does_not_leak_voxcpm2_model_path():
    secret_path = r"C:\secret\models\voxcpm2"
    provider = VoxCPM2TTSProvider(VoxCPM2Config(enabled=True, model_path=secret_path, admin_only=True))
    result = provider.synthesize("Xin chao", gender="female", admin=True)
    assert result.ok is False
    assert secret_path not in result.public_message
    assert "model" not in result.public_message.lower()


def test_no_charge_before_valid_tts_artifact():
    status_text = bot.tts_backend_status_text()
    assert "no_charge_before_valid_audio" in status_text
    assert "spend_fixed_credit_info" not in inspect.getsource(bot.call_voxcpm2_tts_bytes)


def test_voxcpm2_commands_registered_and_under_32_chars():
    source = inspect.getsource(bot.lifespan)
    for command in ("tts_backend_status", "voxcpm2_status", "voxcpm2_test_tts"):
        assert len(command) <= 32
        assert f'CommandHandler("{command}"' in source
