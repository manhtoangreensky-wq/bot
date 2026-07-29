import asyncio
import inspect

import bot
import pytest
from services import subtitle_dub_product_pipeline


LANES = (
    bot.VIDEO_SUBTITLE_MODE_CREATE,
    bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
    bot.VIDEO_SUBTITLE_MODE_DUB,
    bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
)

SOURCE_VIDEO = b"\x00\x00\x00\x18ftypmp42-source" + b"s" * 1024
PROCESSED_VIDEO = b"\x00\x00\x00\x18ftypmp42-processed" + b"p" * 4096
SOURCE_SEGMENTS = [
    {"index": 1, "start": 0.0, "end": 1.4, "text": "Xin chao"},
    {"index": 2, "start": 1.6, "end": 3.0, "text": "Day la TOAN AAS"},
]
SOURCE_SRT = (
    "1\n00:00:00,000 --> 00:00:01,400\nXin chao\n\n"
    "2\n00:00:01,600 --> 00:00:03,000\nDay la TOAN AAS\n"
)


def _state(mode: str) -> dict:
    return {
        "active_flow": "subdub",
        "mode": mode,
        "process_type": mode,
        "video_processing_mode": mode,
        "source_file_name": "fixture.mp4",
        "source_mime_type": "video/mp4",
        "media_kind": "video",
        "target_language": "vi",
        "translate_requested": "1" if mode != bot.VIDEO_SUBTITLE_MODE_CREATE else "0",
        "voice_id": "Vietnamese_female_4_v1",
        "voice_style": "female",
        "voice_speed": "0.95",
    }


def _patch_configured_runtime(monkeypatch) -> None:
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE", True)
    monkeypatch.setattr(bot, "PROVIDER_FREEZE_ENABLED", True)
    monkeypatch.setattr(bot, "TRANSLATION_DUB_MAINTENANCE", False)
    monkeypatch.setattr(bot, "ASR_PROVIDER", "deepgram")
    monkeypatch.setattr(bot, "TRANSLATE_PROVIDER", "deepl")
    monkeypatch.setattr(bot, "TTS_PROVIDER", "key4u_minimax")
    monkeypatch.setattr(bot, "DEEPGRAM_API_KEY", "configured")
    monkeypatch.setattr(bot, "DEEPL_API_KEY", "configured")
    monkeypatch.setattr(bot, "KEY4U_ENABLED", True)
    monkeypatch.setattr(bot, "KEY4U_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "KEY4U_API_KEY", "configured")
    monkeypatch.setattr(bot, "KEY4U_TTS_ENDPOINT", "/v1/t2a_v2")
    monkeypatch.setattr(bot, "KEY4U_TTS_MODEL", "speech-02-hd")
    monkeypatch.setattr(bot, "VIDEO_ASR_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_DUB_TTS_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_TRANSLATE_SUBTITLE_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_DUB_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_SUBTITLE_PLUS_DUB_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "subdub_public_force_override_active", lambda: False)
    monkeypatch.setattr(bot, "subdub_public_freeze_override_active", lambda: False)
    monkeypatch.setattr(bot, "subdub_public_override_value", lambda _name: "")
    monkeypatch.setattr(
        bot,
        "subdub_provider_smoke_result",
        lambda _kind, _provider: {
            "status": "STALE",
            "tested_at": "before-deploy",
            "detail": "runtime_sha=old",
        },
    )
    monkeypatch.setattr(
        bot,
        "subdub_runtime_status_payload",
        lambda: {
            "ffmpeg_ready": True,
            "ffprobe_ready": True,
            "subtitle_rendering_ready": True,
            "media_preprocessing_ready": True,
        },
    )
    monkeypatch.setattr(
        bot,
        "get_asr_adapter_readiness",
        lambda public=False, audio_extract_ready=None: {
            "configured": True,
            "ready": True,
            "supports_audio": True,
            "supports_video": True,
        },
    )
    monkeypatch.setattr(
        bot,
        "resolve_media_binary",
        lambda name: {
            "resolved_path": f"/usr/bin/{name}",
            "version_probe_ok": True,
            "source": "fixture",
        },
    )


def _confirmed_context(user_id: int = 29001) -> dict:
    return {
        "user_id": user_id,
        "entry_source": bot.ENGINE_ENTRY_SOURCE_PRODUCT,
        "confirm_paid": True,
        "is_paid_job": True,
    }


def test_final_confirm_admits_all_four_configured_lanes_despite_stale_smoke_and_public_flags(monkeypatch):
    _patch_configured_runtime(monkeypatch)

    for mode in LANES:
        gate = bot.evaluate_engine_gate(
            bot.video_dubbing_product_area_for_mode(mode),
            {"mode": mode, "state": _state(mode)},
            _confirmed_context(),
        )
        assert gate["allowed"] is True, (mode, gate)
        assert gate["readiness"]["configured"] is True


def test_final_confirm_does_not_bypass_missing_selected_provider(monkeypatch):
    _patch_configured_runtime(monkeypatch)
    monkeypatch.setattr(bot, "key4u_minimax_tts_configured", lambda require_public=False: False)

    gate = bot.evaluate_engine_gate(
        "video_dub",
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "state": _state(bot.VIDEO_SUBTITLE_MODE_DUB)},
        _confirmed_context(),
    )

    assert gate["allowed"] is False
    assert "tts" in ",".join(gate["readiness"].get("technical_missing") or []).lower()


def test_draft_without_final_confirm_cannot_use_confirmed_product_admission(monkeypatch):
    _patch_configured_runtime(monkeypatch)
    context = {**_confirmed_context(), "confirm_paid": False}

    gate = bot.evaluate_engine_gate(
        "video_dub",
        {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "state": _state(bot.VIDEO_SUBTITLE_MODE_DUB)},
        context,
    )

    assert gate["allowed"] is False


def test_confirmed_key4u_tts_uses_only_selected_route_when_global_public_flag_is_off(monkeypatch):
    calls = {"key4u": 0, "shopaikey": 0, "direct": 0}
    monkeypatch.setattr(bot, "TTS_PROVIDER", "key4u_minimax")
    monkeypatch.setattr(bot, "KEY4U_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "VIDEO_DUB_TTS_ENABLED", False)
    monkeypatch.setattr(bot, "subdub_public_force_override_active", lambda: False)
    monkeypatch.setattr(bot, "key4u_minimax_tts_configured", lambda require_public=False: True)
    monkeypatch.setattr(bot, "shopaikey_minimax_tts_configured", lambda: True)
    monkeypatch.setattr(bot, "direct_minimax_tts_configured", lambda: True)

    async def key4u(*_args, **_kwargs):
        calls["key4u"] += 1
        return "PASS", b"processed-audio", "fixture", 200

    async def shopaikey(*_args, **_kwargs):
        calls["shopaikey"] += 1
        return "PASS", b"wrong-route", "fixture", 200

    async def direct(*_args, **_kwargs):
        calls["direct"] += 1
        return "PASS", b"wrong-route", "fixture", 200

    monkeypatch.setattr(bot, "call_key4u_minimax_tts_bytes_with_speed", key4u)
    monkeypatch.setattr(bot, "call_shopaikey_minimax_tts_bytes_with_speed", shopaikey)
    monkeypatch.setattr(bot, "call_direct_minimax_tts_bytes_with_speed", direct)

    provider, audio, _detail = asyncio.run(
        bot.video_dubbing_tts_bytes(
            "Xin chao",
            voice_id="Vietnamese_female_4_v1",
            voice_speed="0.95",
            allow_confirmed_product=True,
        )
    )

    assert provider == "Key4U MiniMax"
    assert audio == b"processed-audio"
    assert calls == {"key4u": 1, "shopaikey": 0, "direct": 0}


def test_confirmed_product_marker_reaches_pipeline_gate_after_saved_input(monkeypatch, tmp_path):
    _patch_configured_runtime(monkeypatch)
    source = tmp_path / "fixture.mp4"
    source.write_bytes(b"source-video")
    state = {**_state(bot.VIDEO_SUBTITLE_MODE_DUB), "subdub_final_confirmed": True}

    access = bot.video_dubbing_engine_access_decision(
        29001,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        state,
        is_paid_job=True,
        confirm_paid=True,
    )
    matrix = bot.video_dubbing_product_gate_matrix(
        29001,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        state,
        access=access,
        input_save={
            "ok": True,
            "file_saved": True,
            "exists": True,
            "size": source.stat().st_size,
            "path": str(source),
            "content_type": "video/mp4",
        },
    )

    assert access["allowed"] is True, access
    assert matrix["product_config_ready"] is True, matrix
    assert bot.video_dubbing_product_gate_allows_pipeline(access, matrix) is True


def test_final_callback_is_the_only_confirm_edge_that_sets_product_admission():
    source = inspect.getsource(bot.handle_video_dubbing_callback)
    final_edge = source.split('if action in confirm_modes or action == "final":', 1)[1]

    assert 'confirmed_product = bool(action == "final")' in final_edge
    assert "subdub_final_confirmed=True" in final_edge
    assert "subdub_confirmation_source=SUBDUB_FINAL_CONFIRM_SOURCE" in final_edge
    assert "subdub_confirmed_at_ts=int(time.time())" in final_edge
    assert source.index('confirmed_product = bool(action == "final")') < source.index("execute_engine(")


def test_confirmed_key4u_asr_uses_selected_route_without_fallback(monkeypatch):
    calls = {"key4u": 0, "deepgram": 0}
    monkeypatch.setattr(bot, "ASR_PROVIDER", "key4u")
    monkeypatch.setattr(bot, "KEY4U_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "key4u_asr_configured", lambda: True)
    monkeypatch.setattr(bot, "save_provider_attempt", lambda *_args, **_kwargs: None)

    async def key4u(*_args, **_kwargs):
        calls["key4u"] += 1
        return {"ok": True, "status": "PASS", "text": "xin chao", "detail": "fixture"}

    async def deepgram(*_args, **_kwargs):
        calls["deepgram"] += 1
        return {"ok": True, "status": "PASS", "transcript": "wrong route"}

    monkeypatch.setattr(bot, "openai_compatible_asr_transcribe", key4u)
    monkeypatch.setattr(bot, "deepgram_asr_adapter", deepgram)

    result = asyncio.run(
        bot.asr_transcribe_audio(
            b"fixture-audio",
            "audio/mpeg",
            allow_subdub_public=True,
            allow_confirmed_product=True,
        )
    )

    assert result["ok"] is True
    assert result["provider"] == "key4u_audio"
    assert calls == {"key4u": 1, "deepgram": 0}


def test_confirmed_key4u_translation_uses_selected_route_without_fallback(monkeypatch):
    calls = {"key4u": 0}
    monkeypatch.setattr(bot, "TRANSLATE_PROVIDER", "key4u")
    monkeypatch.setattr(bot, "KEY4U_PUBLIC_ENABLED", False)
    monkeypatch.setattr(bot, "key4u_subtitle_translation_configured", lambda: True)
    monkeypatch.setattr(bot, "save_tool_test_result", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(bot, "save_provider_attempt", lambda *_args, **_kwargs: None)

    class Provider:
        async def translate(self, *_args, **_kwargs):
            calls["key4u"] += 1
            return {"ok": True, "status": "PASS", "text": "Hello"}

    monkeypatch.setattr(bot, "key4u_provider_instance", lambda: Provider())

    result = asyncio.run(
        bot.translate_subtitle_text(
            "Xin chao",
            "en",
            allow_confirmed_product=True,
        )
    )

    assert result["provider"] == "key4u"
    assert result["text"] == "Hello"
    assert calls == {"key4u": 1}


async def _run_offline_lane(mode: str) -> tuple[dict, dict]:
    calls = {
        "prepare": 0,
        "tts": [],
        "render": 0,
        "subtitle_payloads": [],
        "wallet": 0,
        "telegram": 0,
        "provider": 0,
    }

    async def prepare(state):
        calls["prepare"] += 1
        return {
            "state": dict(state),
            "source_bytes": SOURCE_VIDEO,
            "content_type": "video/mp4",
            "source_subtitle": SOURCE_SRT,
            "source_segments": list(SOURCE_SEGMENTS),
            "output_subtitle": SOURCE_SRT,
            "output_script": "Xin chao\nDay la TOAN AAS",
            "output_segments": list(SOURCE_SEGMENTS),
            "asr_provider": "fixture-asr",
            "translation_provider": "fixture-translation" if mode != bot.VIDEO_SUBTITLE_MODE_CREATE else "",
        }

    async def synthesize(segments, **_kwargs):
        chunks = []
        for segment in segments:
            calls["tts"].append(int(segment["index"]))
            chunks.append({
                "index": int(segment["index"]),
                "start": float(segment["start"]),
                "end": float(segment["end"]),
                "audio_bytes": f"cue-{segment['index']}".encode("ascii"),
                "audio_duration": float(segment["end"]) - float(segment["start"]),
            })
        return {"provider": "fixture-tts", "chunks": chunks}

    async def timeline(chunks, _duration):
        assert [chunk["index"] for chunk in chunks] == calls["tts"]
        return b"fixture-timeline-audio", "fixture-timeline"

    async def normalize(audio):
        return bytes(audio), "fixture-normalized"

    async def render(source, **kwargs):
        calls["render"] += 1
        calls["subtitle_payloads"].append(bytes(kwargs.get("subtitle_bytes") or b""))
        assert source == SOURCE_VIDEO
        return PROCESSED_VIDEO, "fixture-rendered"

    output_type = {
        bot.VIDEO_SUBTITLE_MODE_CREATE: "burn",
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE: "burn",
        bot.VIDEO_SUBTITLE_MODE_DUB: "video",
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB: "video_subtitle",
    }[mode]
    state = {
        **_state(mode),
        "output_type": output_type,
        "output_format": output_type,
        "video_duration": "3",
        "source_duration": "3",
        "subdub_final_confirmed": True,
    }
    result = await subtitle_dub_product_pipeline.run_subdub_pipeline(
        job_id=f"offline-{mode}",
        mode=mode,
        state=state,
        user_id=29001,
        prepare_subtitles=prepare,
        srt_from_text=bot.video_dubbing_srt_from_text,
        segments_from_text=bot.video_dubbing_segments_from_text,
        segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
        subtitle_output_items=bot.video_dubbing_subtitle_output_items,
        resolve_voice_id=lambda _uid, _state: "Vietnamese_female_4_v1",
        parse_voice_speed=lambda _value: 0.95,
        synthesize_segments=synthesize,
        build_timeline_audio=timeline,
        normalize_audio=normalize,
        render_video=render,
        video_render_ready=lambda _output_type: True,
        ffmpeg_ready=lambda: True,
        dub_mux_enabled=True,
    )
    return result, calls


@pytest.mark.parametrize("mode", LANES)
def test_all_four_lanes_render_processed_mp4_offline_without_side_effects(mode):
    result, calls = asyncio.run(_run_offline_lane(mode))

    assert result["ok"] is True, result
    assert result["video_output"] == PROCESSED_VIDEO
    assert result["video_output"] != SOURCE_VIDEO
    assert result["video_output"].startswith(b"\x00\x00\x00\x18ftypmp42")
    assert calls["prepare"] == 1
    assert calls["render"] == 1
    assert calls["provider"] == 0
    assert calls["wallet"] == 0
    assert calls["telegram"] == 0

    needs_dub = mode in {bot.VIDEO_SUBTITLE_MODE_DUB, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB}
    needs_subtitle = mode in {
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    }
    assert calls["tts"] == ([1, 2] if needs_dub else [])
    assert bool(calls["subtitle_payloads"][-1]) is needs_subtitle
