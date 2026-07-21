import asyncio
import subprocess
from pathlib import Path

import bot
from services import audio_postprocess, voice_clone_pipeline


def _fake_boost_result(input_path, output_path, *, volume_factor=2.0, **_kwargs):
    source = Path(input_path)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"boosted:" + source.read_bytes())
    return audio_postprocess.AudioBoostResult(
        ok=True,
        input_path=str(source),
        output_path=str(target),
        output_bytes=target.stat().st_size,
        boosted=True,
        fallback_original=False,
        factor=volume_factor,
        detail="ok",
    )


async def _run_custom_voice_preview(tmp_path):
    sample = tmp_path / "sample.mp3"
    sample.write_bytes(b"sample-audio")

    async def upload_call(_audio_bytes):
        return "PASS", "file-1", "ok", 200

    async def clone_call(_file_id, _voice_id):
        return "PASS", {}, "ok", 200

    async def tts_call(_text, voice_id="", **_kwargs):
        assert voice_id == "toanaas-voice-user1-20260628"
        return "PASS", b"preview-audio", "ok", 200

    async def route_attempts_func(_readiness, admin_access=False):
        return [("shopaikey_minimax", upload_call, clone_call, tts_call)]

    return await voice_clone_pipeline.process_custom_voice_create(
        user_id=1,
        sample_path=sample,
        display_name="Voice boost",
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        profile_id=9,
        readiness={"ready": True},
        output_dir=str(tmp_path),
        route_attempts_func=route_attempts_func,
        access_allowed_func=lambda *_args, **_kwargs: True,
        ready_for_processing_func=lambda *_args, **_kwargs: True,
        make_provider_voice_id_func=lambda *_args, **_kwargs: "toanaas-voice-user1-20260628",
        finalize_profile_func=lambda **_kwargs: {"ok": True},
    )


def test_voice_preview_audio_boosted_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(voice_clone_pipeline.audio_postprocess, "boost_voice_audio", _fake_boost_result)

    result = asyncio.run(_run_custom_voice_preview(tmp_path))

    assert result.ok is True
    assert result.preview_audio_path.endswith("_boosted.mp3")
    assert Path(result.preview_audio_path).read_bytes().startswith(b"boosted:")
    assert result.metadata["voice_volume_boosted"] is True
    assert result.metadata["voice_volume_factor"] == 2.0


def test_voice_tts_audio_boosted_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(voice_clone_pipeline.audio_postprocess, "boost_voice_audio", _fake_boost_result)

    async def fake_tts(_text, provider_voice_id="", **_kwargs):
        assert provider_voice_id == "provider-saved-voice"
        return {"ok": True, "output_bytes": b"saved-voice-audio"}

    result = asyncio.run(voice_clone_pipeline.process_voice_tts(
        user_id=2,
        text="Xin chao TOAN AAS",
        selected_voice_option={"id": 5, "display_name": "Saved", "provider_voice_id": "provider-saved-voice"},
        product_context=bot.PRODUCT_CONTEXT_SHOWROOM,
        output_path=str(tmp_path / "saved_voice.mp3"),
        execute_tts_func=fake_tts,
    ))

    assert result.ok is True
    assert result.audio_path.endswith("_boosted.mp3")
    assert Path(result.audio_path).read_bytes().startswith(b"boosted:")
    assert result.metadata["voice_volume_boosted"] is True


def test_voice_audio_boost_uses_factor_two(tmp_path):
    source = tmp_path / "voice.mp3"
    target = tmp_path / "voice_boosted.mp3"
    source.write_bytes(b"audio")
    seen = {}

    def fake_runner(command):
        seen["command"] = list(command)
        target.write_bytes(b"boosted-audio")
        return subprocess.CompletedProcess(command, 0)

    result = audio_postprocess.boost_voice_audio(str(source), str(target), ffmpeg_path="ffmpeg", run_command_func=fake_runner)

    assert result.ok is True
    assert result.boosted is True
    assert result.factor == 2.0
    assert "volume=2.000,alimiter=limit=0.95" in seen["command"]


def test_voice_audio_boost_fallback_original_when_ffmpeg_missing(monkeypatch, tmp_path):
    source = tmp_path / "voice.mp3"
    target = tmp_path / "voice_boosted.mp3"
    source.write_bytes(b"original-audio")
    monkeypatch.setattr(audio_postprocess, "_find_ffmpeg", lambda *_args, **_kwargs: "")

    result = audio_postprocess.boost_voice_audio(str(source), str(target))

    assert result.ok is True
    assert result.fallback_original is True
    assert target.read_bytes() == b"original-audio"


def test_voice_audio_boost_does_not_break_successful_clone(monkeypatch, tmp_path):
    def fallback_boost(input_path, output_path, *, volume_factor=2.0, **_kwargs):
        source = Path(input_path)
        target = Path(output_path)
        target.write_bytes(source.read_bytes())
        return audio_postprocess.AudioBoostResult(
            ok=True,
            input_path=str(source),
            output_path=str(target),
            output_bytes=target.stat().st_size,
            boosted=False,
            fallback_original=True,
            factor=volume_factor,
            detail="ffmpeg_unavailable",
        )

    monkeypatch.setattr(voice_clone_pipeline.audio_postprocess, "boost_voice_audio", fallback_boost)

    result = asyncio.run(_run_custom_voice_preview(tmp_path))

    assert result.ok is True
    assert result.provider_voice_id == "toanaas-voice-user1-20260628"
    assert result.preview_audio_bytes > 0
    assert result.metadata["voice_volume_fallback_original"] is True


def test_voice_audio_boost_does_not_double_boost(tmp_path):
    source = tmp_path / "voice_boosted.mp3"
    target = tmp_path / "voice_twice_boosted.mp3"
    source.write_bytes(b"already-boosted")

    result = audio_postprocess.boost_voice_audio(
        str(source),
        str(target),
        ffmpeg_path="ffmpeg",
        run_command_func=lambda _command: (_ for _ in ()).throw(AssertionError("must not run ffmpeg twice")),
    )

    assert result.ok is True
    assert result.skipped_double_boost is True
    assert target.read_bytes() == b"already-boosted"


def test_voice_audio_boost_output_bytes_nonzero(monkeypatch, tmp_path):
    source = tmp_path / "voice.mp3"
    target = tmp_path / "voice_boosted.mp3"
    source.write_bytes(b"audio")
    monkeypatch.setattr(audio_postprocess, "_find_ffmpeg", lambda *_args, **_kwargs: "")

    result = audio_postprocess.boost_voice_audio(str(source), str(target))

    assert result.ok is True
    assert result.output_bytes > 0
    assert target.stat().st_size > 0


def test_voice_audio_boost_no_product_ui_change(monkeypatch):
    monkeypatch.setattr(bot, "count_successful_custom_voice_profiles", lambda *_args, **_kwargs: 0)
    labels = [button.text for row in bot.voice_clone_quote_keyboard(1, "vi", bot.PRODUCT_CONTEXT_SHOWROOM).inline_keyboard for button in row]
    text = bot.voice_clone_quote_text({"id": 1, "user_id": 1}, "vi")

    assert "✅ Tạo voice miễn phí" in labels
    assert all("âm lượng" not in label.lower() and "volume" not in label.lower() for label in labels)
    assert "âm lượng" not in text.lower()


def test_voice_product_ui_still_no_admin_tech_words():
    text = bot.voice_clone_product_failure_text("vi", "provider=shopaikey http_status=500 route_errors")
    folded = text.lower()

    for term in ("admin", "provider", "http_status", "route_errors", "shopaikey", "minimax", "api", "debug"):
        assert term not in folded
