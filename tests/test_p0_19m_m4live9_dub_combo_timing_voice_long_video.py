import asyncio
import inspect

import bot
from services import subtitle_dub_product_pipeline as pipeline


def test_m4live9_subtitle_only_path_does_not_call_combo_timing_helper():
    source = inspect.getsource(bot.video_dubbing_prepare_subtitles)
    helper_call = "subdub_preserve_subtitle_plus_dub_cue_timing(source_segments, output_segments)"
    assert helper_call in source
    assert "mode == VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB" in source
    before_helper = source[: source.index(helper_call)]
    assert "mode == VIDEO_SUBTITLE_MODE_TRANSLATE" not in before_helper.rsplit("\n", 12)[-1]


def test_m4live9_combo_timing_preserves_original_cue_start_end():
    source_segments = [
        {"index": 1, "start": 0.0, "end": 2.0, "text": "a"},
        {"index": 2, "start": 2.0, "end": 5.0, "text": "b"},
        {"index": 3, "start": 5.0, "end": 7.0, "text": "c"},
        {"index": 4, "start": 7.0, "end": 10.0, "text": "d"},
        {"index": 5, "start": 10.0, "end": 13.0, "text": "e"},
    ]
    translated_segments = [
        {"index": 1, "start": 0.0, "end": 2.0, "text": "Dong mot"},
        {"index": 2, "start": 2.0, "end": 3.5, "text": "Dong hai phan mot"},
        {"index": 3, "start": 3.5, "end": 5.0, "text": "Dong hai phan hai"},
        {"index": 4, "start": 5.0, "end": 7.0, "text": "Dong ba"},
        {"index": 5, "start": 7.0, "end": 10.0, "text": "Dong bon"},
        {"index": 6, "start": 10.0, "end": 13.0, "text": "Dong nam"},
    ]

    aligned = bot.subdub_preserve_subtitle_plus_dub_cue_timing(source_segments, translated_segments)

    assert len(aligned) == len(source_segments)
    assert [(item["start"], item["end"]) for item in aligned] == [
        (item["start"], item["end"]) for item in source_segments
    ]
    assert "Dong hai phan mot" in aligned[1]["text"]
    assert "Dong hai phan hai" in aligned[1]["text"]
    assert aligned[-1]["end"] == 13.0
    assert all(len(str(item["text"]).splitlines()) <= 2 for item in aligned)


def test_m4live9_dub_service_does_not_force_135_speed():
    source = inspect.getsource(pipeline.process_subtitle_dub_job)
    assert "max(1.35, speed)" not in source
    assert "safe_max_speed" in source


def test_m4live9_synthesize_dub_chunks_preserves_text_and_slow_speed(monkeypatch):
    calls = []

    async def fake_tts(text, _voice_style, _voice_id, speed, **_kwargs):
        calls.append((text, float(speed)))
        return "mock-tts", b"audio", "ok"

    async def fake_duration(_audio_bytes):
        return 8.0

    monkeypatch.setattr(bot, "video_dubbing_tts_bytes", fake_tts)
    monkeypatch.setattr(bot, "video_dubbing_audio_duration_seconds", fake_duration)

    text = "Mot cau noi dai can doc tu ton va khong duoc cat bot noi dung"
    result = asyncio.run(
        bot.synthesize_dub_segment_chunks(
            [{"index": 1, "start": 0.0, "end": 2.0, "text": text}],
            voice_id="female-real-voice",
            base_speed=0.9,
            max_speed=1.02,
            preserve_cue_text=True,
            allow_compact_text=False,
        )
    )

    assert result["chunks"][0]["text"] == text
    assert max(speed for _text, speed in calls) <= 1.02
    assert all(call_text == text for call_text, _speed in calls)
    assert result["chunks"][0]["audio_aligned_to_cues"] is True


def test_m4live9_dub_active_or_delivered_suppresses_generic_fail_text():
    active = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "status": "running",
        "terminal_state": "",
        "progress_stage": "generating_voice",
        "progress_percent": 65,
    }
    delivered = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "status": "running",
        "terminal_state": "",
        "progress_stage": "delivering",
        "progress_percent": 90,
        "video_delivery_message_id": "123",
    }

    assert bot.subdub_should_suppress_generic_fail_for_active_job(active, {"status": "NO_OUTPUT_BYTES"})
    assert bot.subdub_should_suppress_generic_fail_for_active_job(delivered, {"status": "NO_OUTPUT_BYTES"})


def test_m4live9_female_voice_uses_female_default_not_stale_male(monkeypatch):
    monkeypatch.setattr(bot.minimax_voice_adapter, "validate_provider_voice_id", lambda value: bool(value))
    monkeypatch.setattr(bot, "DEFAULT_TTS_FEMALE_VOICE", "female-real-voice")
    monkeypatch.setattr(bot, "MINIMAX_DEFAULT_FEMALE_VOICE_ID", "female-real-voice")
    monkeypatch.setattr(bot, "DEFAULT_TTS_MALE_VOICE", "male-real-voice")
    monkeypatch.setattr(bot, "MINIMAX_DEFAULT_MALE_VOICE_ID", "male-real-voice")
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "voice_kind": "default_female",
        "voice_style": "Giọng nữ mặc định",
        "selected_voice_gender": "female",
        "requested_voice_gender": "female",
        "voice_id": "male-real-voice",
    }

    resolution = bot.resolve_video_dub_tts_voice(19660, state)

    assert resolution["ok"] is True
    assert resolution["provider_voice_id"] == "female-real-voice"
    assert resolution["resolved_gender"] == "female"
    assert resolution["fallback_used"] is False


def test_m4live9_long_video_43s_75s_has_chunk_plan_without_short_video_block():
    short = bot.subdub_duration_gate_payload({"duration": 25}, {}, is_admin=False)
    forty_three = bot.subdub_duration_gate_payload({"duration": 43}, {}, is_admin=False)
    seventy_five = bot.subdub_duration_gate_payload({"duration": 75}, {}, is_admin=False)

    assert short["duration_gate_result"] == "pass"
    assert forty_three["duration_gate_result"] == "pass_long"
    assert forty_three["chunk_count"] == 2
    assert seventy_five["duration_gate_result"] == "pass_long"
    assert seventy_five["chunk_count"] == 3
    assert seventy_five["concat_required"] is True


def test_m4live9_process_pipeline_passes_safe_tts_speed():
    captured = {}

    async def prepare(_state):
        return {
            "state": {"voice_speed": "0.9", "dub_max_speech_rate": 1.02, "source_duration": 2},
            "source_bytes": b"video",
            "content_type": "video/mp4",
            "output_script": "hello",
            "output_segments": [{"index": 1, "start": 0.0, "end": 2.0, "text": "hello"}],
        }

    async def synthesize_segments(*_args, **kwargs):
        captured.update(kwargs)
        return {
            "provider": "mock",
            "dub_timing_mode": "cue_aligned",
            "audio_aligned_to_cues": True,
            "chunks": [{
                "index": 1,
                "start": 0.0,
                "end": 2.0,
                "text": "hello",
                "audio_bytes": b"audio",
                "audio_duration": 2.0,
                "speed": kwargs["base_speed"],
                "tts_speed_ratio": kwargs["base_speed"],
                "max_speed_adjustment": kwargs["max_speed"] - kwargs["base_speed"],
            }],
        }

    async def build_timeline_audio(_chunks, _duration):
        return b"raw-audio", "ok"

    async def normalize_audio(_audio):
        return b"normalized-audio", "ok"

    async def render_video(*_args, **_kwargs):
        return b"mp4", "ok"

    result = asyncio.run(
        pipeline.process_subtitle_dub_job(
            mode=pipeline.VIDEO_SUBTITLE_MODE_DUB,
            state={},
            user_id=19660,
            prepare_subtitles=prepare,
            srt_from_text=lambda _text, _duration: "",
            segments_from_text=lambda _text, _duration: [],
            segments_from_subtitle=lambda _text: [],
            subtitle_output_items=lambda *_args: [],
            resolve_voice_id=lambda _user_id, _state: "female-real-voice",
            parse_voice_speed=lambda value: float(value),
            synthesize_segments=synthesize_segments,
            build_timeline_audio=build_timeline_audio,
            normalize_audio=normalize_audio,
            render_video=render_video,
            video_render_ready=lambda _output_type: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
        )
    )

    assert result["ok"] is True
    assert captured["max_speed"] <= 1.02
    assert result["dub_timing_mode"] == "cue_aligned"
    assert result["audio_aligned_to_cues"] is True
