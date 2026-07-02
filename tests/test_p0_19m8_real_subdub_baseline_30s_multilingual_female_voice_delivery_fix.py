import asyncio
import inspect
import re

import bot


def test_subdub_allows_50mb_and_300s_baseline():
    ok = bot.subdub_media_limit_validation(
        size_bytes=49 * 1024 * 1024,
        duration_seconds=300,
        is_admin=False,
    )
    assert ok["ok"] is True
    assert bot.subdub_input_limit_mb(False) >= 50
    assert bot.subdub_duration_limit_seconds(False) >= 300


def test_subdub_asr_chunk_windows_cover_long_duration():
    windows = bot.subdub_asr_chunk_windows(90, chunk_seconds=25, overlap_seconds=2)

    assert len(windows) >= 4
    assert windows[0][0] == 0.0
    assert windows[-1][1] == 90.0
    assert all(end > start for start, end in windows)


def test_subdub_transcribe_audio_chunks_combines_segments(monkeypatch):
    calls = []

    async def fake_slice(audio_bytes, content_type, start, end):
        return b"chunk", f"slice:{start}-{end}"

    async def fake_asr(audio_bytes, content_type, **kwargs):
        calls.append(kwargs)
        index = len(calls)
        return {
            "ok": True,
            "status": "PASS",
            "provider": "fake_asr",
            "text": "你好世界" if index == 1 else "hello world",
            "language": "zh" if index == 1 else "en",
            "segments": [{"start": 0.0, "end": 2.0, "text": f"segment {index}"}],
        }

    monkeypatch.setattr(bot, "subdub_slice_audio_for_asr", fake_slice)
    monkeypatch.setattr(bot, "asr_transcribe_audio", fake_asr)

    result = asyncio.run(
        bot.subdub_transcribe_audio_chunks(
            b"audio",
            "audio/mpeg",
            duration_seconds=60,
            language="auto",
        )
    )

    assert result["ok"] is True
    assert result["asr_chunked"] is True
    assert result["asr_chunk_count"] >= 2
    assert len(result["segments"]) == result["asr_chunk_count"]
    assert result["segments"][-1]["start"] > 20
    assert result["language"] in {"zh", "en"}


def test_subdub_detects_supported_source_languages():
    assert bot.subdub_detect_language_from_text("你好世界") == "zh"
    assert bot.subdub_detect_language_from_text("Hello world") == "en"
    assert bot.subdub_detect_language_from_text("こんにちは") == "ja"
    assert bot.subdub_detect_language_from_text("안녕하세요") == "ko"
    assert bot.subdub_detect_language_from_text("สวัสดี") == "th"
    assert bot.subdub_detect_language_from_text("Tôi đang thử phụ đề") == "vi"


def test_subdub_debug_lookup_accepts_public_hash_and_lowercase():
    key = "p019m8-job-lookup"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    job = bot.subdub_attach_job_lookup_fields(
        {
            "job_key": key,
            "job_id": "ABCDEF1234567890ABCD",
            "internal_job_id": "subdub_internal_123",
            "public_job_id": "7388DD5899",
            "user_id": "42",
            "status": "running",
        }
    )
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = job

    assert bot.subtitle_dub_debug_lookup_job("7388DD5899")["job_key"] == key
    assert bot.subtitle_dub_debug_lookup_job("#7388DD5899")["job_key"] == key
    assert bot.subtitle_dub_debug_lookup_job("7388dd5899")["job_key"] == key
    assert bot.subtitle_dub_find_pipeline_job_for_user(42, "#7388DD5899")["job_key"] == key


def test_required_subdub_admin_debug_commands_registered_and_short():
    source = inspect.getsource(bot)
    required = [
        "subdub_status_debug",
        "subdub_language_debug",
        "subdub_voice_debug",
        "subdub_delivery_debug",
        "subdub_duration_audit",
    ]

    for command in required:
        assert f'CommandHandler("{command}"' in source
        assert len(command) <= 32


def test_public_status_callback_does_not_throw_generic_missing_job_alert():
    source = inspect.getsource(bot.handle_video_dubbing_callback)

    assert 'query.answer("Chưa tìm thấy trạng thái xử lý."' not in source
    assert "subdub_clean_failure_text" in source


def test_female_voice_does_not_silently_fallback_to_male(monkeypatch):
    monkeypatch.setattr(bot.minimax_voice_adapter, "validate_provider_voice_id", lambda value: bool(value))
    state = {
        "selected_voice_id": "male-qn-qingse",
        "selected_voice_gender": "female",
        "voice_style": "Giọng nữ",
    }

    resolution = bot.resolve_video_dub_tts_voice(1, state)

    assert resolution["ok"] is False
    assert resolution["requested_voice_gender"] == "female"
    assert resolution["fallback_used"] is False
    assert "gender" in resolution["reason"] or "gender" in resolution["fallback_reason"]
    assert "giọng nữ" in bot.subdub_selected_female_voice_unavailable_text("vi")


def test_tts_segments_split_long_dialogue():
    text = " ".join(f"word{i}" for i in range(160))
    segments = [{"index": 1, "start": 0.0, "end": 70.0, "text": text}]

    split = bot.subdub_split_tts_segments(segments, max_seconds=20, max_chars=260)

    assert len(split) > 1
    assert split[0]["start"] == 0.0
    assert split[-1]["end"] == 70.0
    assert all(len(item["text"]) <= 300 for item in split)


def test_charge_occurs_after_delivery_attempt_in_core_source():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    delivery_index = source.index("send_public_subtitle_dub_final_outputs")
    charge_index = source.index("spend_fixed_credit_info")
    assert delivery_index < charge_index
    assert "pending_charge_xu" in source


def test_debug_language_text_includes_chunk_and_route_fields():
    text = bot.subdub_language_debug_text(
        {
            "internal_job_id": "job1",
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "detected_language": "zh",
            "target_language": "vi",
            "source_segment_count": 4,
            "translated_segment_count": 4,
            "asr_chunked": True,
            "asr_chunk_count": 3,
            "provider_route": {"asr": "deepgram", "translation": "deepl"},
        }
    )

    assert "detected language" in text
    assert "ASR chunk count" in text
    assert "translation route" in text
    assert "provider/API/FFmpeg" not in re.sub(r"<[^>]+>", "", text)
