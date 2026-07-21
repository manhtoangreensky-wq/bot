import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

import bot
from services import subtitle_dub_product_pipeline


SOURCE_SRT = (
    "1\n00:00:00,000 --> 00:00:02,000\nXin chao\n\n"
    "2\n00:00:02,000 --> 00:00:04,000\nBan khoe khong\n"
)
SOURCE_SEGMENTS = [
    {"index": 1, "start": 0.0, "end": 2.0, "text": "Xin chao"},
    {"index": 2, "start": 2.0, "end": 4.0, "text": "Ban khoe khong"},
]


def test_all_subdub_video_modes_preserve_source_duration():
    assert bot.subdub_mode_preserves_source_duration(bot.VIDEO_SUBTITLE_MODE_CREATE)
    assert bot.subdub_mode_preserves_source_duration(bot.VIDEO_SUBTITLE_MODE_TRANSLATE)
    assert bot.subdub_mode_preserves_source_duration(bot.VIDEO_SUBTITLE_MODE_DUB)
    assert bot.subdub_mode_preserves_source_duration(bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB)


def test_rendered_dub_video_does_not_use_shortest(monkeypatch):
    commands = []

    async def fake_probe(_payload):
        return {"ok": True, "duration": 30.0, "has_audio": True, "width": 720, "height": 1280}

    async def fake_run(command, timeout=0):
        del timeout
        commands.append(list(command))
        Path(command[-1]).write_bytes(b"rendered-mp4")
        return True, "ok"

    async def fake_validate(_payload, require_audio=False):
        assert require_audio is True
        return {"ok": True, "duration": 30.0, "detail": "valid"}

    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot, "subdub_probe_video_bytes", fake_probe)
    monkeypatch.setattr(bot, "run_ffmpeg_command", fake_run)
    monkeypatch.setattr(bot, "subdub_validate_video_output", fake_validate)

    output, detail = asyncio.run(
        bot.video_dubbing_render_video(
            b"source-video",
            dubbed_audio=b"short-dub-audio",
            require_audio=True,
            preserve_source_duration=True,
        )
    )

    assert output == b"rendered-mp4"
    assert "source_duration_preserved=30.000" in detail
    assert commands
    assert "-shortest" not in commands[-1]
    assert commands[-1][commands[-1].index("-t") + 1] == "30.000"


def test_combo_canonical_timeline_schedules_tts_sequentially_without_overlap(monkeypatch):
    commands = []

    async def fake_run(command, timeout=0):
        del timeout
        commands.append(list(command))
        Path(command[-1]).write_bytes(b"timeline-audio")
        return True, "ok"

    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot, "run_ffmpeg_command", fake_run)
    chunks = [
        {"start": 0.0, "end": 2.0, "audio_duration": 2.2, "audio_bytes": b"one"},
        {"start": 2.0, "end": 4.0, "audio_duration": 2.1, "audio_bytes": b"two"},
    ]

    output, detail = asyncio.run(bot.build_canonical_dub_timeline_audio(chunks, 4.0))

    assert output == b"timeline-audio"
    assert "ffmpeg_canonical_timeline_audio" in detail
    assert "overlap_count=0" in detail
    assert "sequential=yes" in detail
    filter_value = commands[-1][commands[-1].index("-filter_complex") + 1]
    assert "atempo=" in filter_value
    assert filter_value.count("apad") == 1
    assert "adelay=0|0" in filter_value
    delays = [int(value) for value in re.findall(r"adelay=(\d+)\|", filter_value)]
    assert len(delays) == 2
    assert delays[1] >= 2000
    assert commands[-1][commands[-1].index("-t") + 1] == "4.000"


def test_canonical_timeline_rejects_tts_that_cannot_fit_source_duration(monkeypatch):
    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    output, detail = asyncio.run(
        bot.build_canonical_dub_timeline_audio(
            [{"cue_id": "cue-1", "start": 0.0, "end": 2.0, "audio_duration": 5.0, "audio_bytes": b"one"}],
            2.0,
        )
    )

    assert output == b""
    assert "canonical_tts_timeline_exceeds_source" in detail
    assert "max_tempo=1.150" in detail


def test_canonical_timeline_keeps_natural_speed_when_source_duration_has_room():
    plan = bot.subdub_plan_canonical_tts_timeline(
        [
            {"cue_id": "cue-1", "start": 0.0, "end": 1.0, "audio_duration": 1.8},
            {"cue_id": "cue-2", "start": 1.0, "end": 2.0, "audio_duration": 1.5},
        ],
        4.0,
    )

    assert plan["ok"] is True
    assert plan["tempo_ratio"] == 1.0
    assert plan["overlap_count"] == 0
    assert plan["shifted_cue_count"] == 1
    assert plan["scheduled"][0]["scheduled_start"] == 0.0
    assert plan["scheduled"][0]["scheduled_end"] == 1.8
    assert plan["scheduled"][1]["scheduled_start"] == 1.8
    assert plan["scheduled"][1]["scheduled_end"] == 3.3


def test_long_video_asr_chunks_keep_absolute_timestamps(monkeypatch):
    calls = []

    async def fake_extract(_source, _content_type, max_seconds=0):
        assert max_seconds == 0
        return b"full-audio", "audio/mpeg", "fixture_extract"

    async def fake_split(_audio, _content_type, duration_seconds, chunk_seconds=None):
        assert duration_seconds == 60
        assert chunk_seconds == 30
        return [
            {"index": 1, "start": 0.0, "end": 30.0, "audio_bytes": b"chunk-1", "content_type": "audio/mpeg"},
            {"index": 2, "start": 30.0, "end": 60.0, "audio_bytes": b"chunk-2", "content_type": "audio/mpeg"},
        ], "fixture_chunks"

    async def fake_asr(payload, _content_type, **_kwargs):
        calls.append(payload)
        text = "Cau mot" if payload == b"chunk-1" else "Cau hai"
        return {
            "ok": True,
            "status": "PASS",
            "provider": "fixture-asr",
            "text": text,
            "segments": [{"index": 1, "start": 1.0, "end": 3.0, "text": text}],
            "language": "vi",
            "detail": "fixture",
        }

    monkeypatch.setattr(bot, "video_dubbing_audio_extract_ready", lambda: True)
    monkeypatch.setattr(bot, "video_dubbing_extract_audio", fake_extract)
    monkeypatch.setattr(bot, "subdub_split_audio_for_asr", fake_split)
    monkeypatch.setattr(bot, "asr_transcribe_audio", fake_asr)

    result = asyncio.run(
        bot.transcribe_media_to_segments(
            {"bytes": b"video", "content_type": "video/mp4", "media_kind": "video"},
            source_language="auto",
            duration_seconds=60,
            preserve_timestamps=True,
        )
    )

    assert result["output_valid"] is True
    assert result["chunk_count"] == 2
    assert result["chunk_strategy"] == "fixed_duration_audio"
    assert result["global_timing_preserved"] is True
    assert calls == [b"chunk-1", b"chunk-2"]
    assert [(item["start"], item["end"]) for item in result["segments"]] == [(1.0, 3.0), (31.0, 33.0)]


def test_subdub_accepts_and_chunks_exactly_300_seconds(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_MAX_DURATION_SECONDS", 300)
    monkeypatch.setattr(bot, "SUBDUB_PREVIEW_DURATION_SECONDS", 30)
    monkeypatch.setattr(bot, "SUBDUB_LONG_CHUNK_SECONDS", 30)

    gate = bot.subdub_duration_gate_payload(
        {"duration": 300, "telegram_duration": 300},
        {},
        is_admin=False,
    )

    assert gate["duration_gate_result"] == "pass_long"
    assert gate["long_media_allowed"] is True
    assert gate["over_30_supported"] is True
    assert gate["chunking_enabled"] is True
    assert gate["chunk_count"] == 10
    assert gate["chunk_ranges"][0] == {"index": 1, "start": 0, "end": 30}
    assert gate["chunk_ranges"][-1] == {"index": 10, "start": 270, "end": 300}
    assert gate["global_timing_preserved"] is True


def test_auto_subtitle_uses_audio_asr_original_language_only(monkeypatch):
    captured = {}
    initial_state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
        "source_file_name": "input.mp4",
        "source_mime_type": "video/mp4",
        "media_kind": "video",
        "video_duration": 4,
        "_pipeline_source_bytes_override": b"video-bytes",
        "subtitle_ref": "stale-subtitle",
        "translated_subtitle_ref": "stale-translation",
        "translate_requested": "1",
        "target_language": "en",
        "voice_style": "female",
    }

    async def fake_resolve(_source, _content_type, _context, **kwargs):
        captured.update(kwargs)
        return {
            "source_kind": "asr",
            "extraction_source": "audio_asr",
            "source_priority": "audio_asr",
            "subtitle": SOURCE_SRT,
            "script": "Xin chao Ban khoe khong",
            "segments": SOURCE_SEGMENTS,
            "asr_provider": "fixture-asr",
            "detected_language": "vi",
            "duration_seconds": 4,
        }

    async def translation_must_not_run(*_args, **_kwargs):
        raise AssertionError("auto subtitle must not translate")

    monkeypatch.setattr(bot, "video_dubbing_resolve_auto_subtitle_script", fake_resolve)
    monkeypatch.setattr(bot, "translate_subtitle_segments", translation_must_not_run)
    monkeypatch.setattr(bot, "set_video_dubbing_artifact", lambda *_args, **_kwargs: "source-ref")
    monkeypatch.setattr(
        bot,
        "set_video_dubbing_pending",
        lambda _user_id, _step, **kwargs: {**initial_state, **kwargs},
    )

    prepared = asyncio.run(
        bot.video_dubbing_prepare_subtitles(SimpleNamespace(), initial_state, 991001)
    )

    assert captured["source_language"] == "auto"
    assert prepared["source_subtitle"].strip() == SOURCE_SRT.strip()
    assert prepared["output_subtitle"].strip() == SOURCE_SRT.strip()
    assert [(cue["start"], cue["end"], cue["source_text"]) for cue in prepared["output_segments"]] == [
        (item["start"], item["end"], item["text"]) for item in SOURCE_SEGMENTS
    ]
    assert all(cue["cue_id"] for cue in prepared["output_segments"])
    assert prepared["detected_language"] == "vi"
    assert prepared["translation_provider"] == ""
    assert prepared["translated_segment_count"] == 0
    assert prepared["auto_subtitle_only"] is True
    assert prepared["auto_subtitle_source"] == "audio_asr"
    assert prepared["auto_subtitle_translation_requested"] is False
    assert prepared["auto_subtitle_tts_requested"] is False
    assert prepared["auto_subtitle_dub_requested"] is False


def test_auto_subtitle_product_flow_never_calls_tts(monkeypatch):
    calls = []

    async def fake_prepare(state):
        return {
            "state": state,
            "source_bytes": b"video",
            "content_type": "video/mp4",
            "source_subtitle": SOURCE_SRT,
            "output_subtitle": SOURCE_SRT,
            "output_script": "Xin chao Ban khoe khong",
            "output_segments": SOURCE_SEGMENTS,
            "asr_provider": "fixture-asr",
        }

    async def tts_must_not_run(*_args, **_kwargs):
        raise AssertionError("auto subtitle must not call TTS")

    async def fake_render(*_args, **kwargs):
        calls.append(kwargs)
        return b"final-mp4", "rendered"

    result = asyncio.run(
        subtitle_dub_product_pipeline.process_subtitle_dub_job(
            mode=bot.VIDEO_SUBTITLE_MODE_CREATE,
            state={"video_duration": 4, "output_type": "burn"},
            user_id=991001,
            prepare_subtitles=fake_prepare,
            srt_from_text=bot.video_dubbing_srt_from_text,
            segments_from_text=bot.video_dubbing_segments_from_text,
            segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
            subtitle_output_items=lambda *_args: [],
            resolve_voice_id=lambda *_args: "must-not-be-used",
            parse_voice_speed=lambda *_args: 1.0,
            synthesize_segments=tts_must_not_run,
            build_timeline_audio=tts_must_not_run,
            normalize_audio=tts_must_not_run,
            render_video=fake_render,
            video_render_ready=lambda _output: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
        )
    )

    assert result["ok"] is True
    assert result["video_output"] == b"final-mp4"
    assert len(calls) == 1
    assert calls[0].get("dubbed_audio", b"") == b""


def test_auto_subtitle_srt_delivery_requires_telegram_message_id():
    sent = []

    class Message:
        async def reply_document(self, **kwargs):
            sent.append(kwargs)
            return SimpleNamespace(message_id=731)

    delivery = asyncio.run(
        bot.send_public_auto_subtitle_result(
            Message(),
            srt_text=SOURCE_SRT,
            lang="vi",
        )
    )

    assert len(sent) == 1
    assert delivery["documents"] == 1
    assert delivery["srt_delivery_message_id"] == "731"
    assert delivery["terminal_artifact_type"] == "subtitle"
    assert delivery["terminal_public_outcome_type"] == "success"
    assert bot.subdub_auto_subtitle_delivery_succeeded(
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        delivery,
        video_output=b"",
    )
    assert not bot.subdub_auto_subtitle_delivery_succeeded(
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        delivery,
        video_output=b"",
    )


def test_auto_subtitle_srt_receipt_and_keyboard_do_not_claim_video_delivery():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
        "video_duration": 30,
        "detected_language": "Tiếng Việt",
        "final_subtitle_available": "1",
        "final_video_available": "0",
    }
    result = {
        "ok": True,
        "terminal_state": "delivered",
        "terminal_public_outcome_type": "success",
        "terminal_artifact_type": "subtitle",
        "telegram_message_id": "731",
        "srt_delivery_message_id": "731",
        "has_subtitle": True,
        "has_video": False,
        "final_mp4_delivered": False,
        "charged": 0,
        "state": state,
    }

    receipt = bot.video_dubbing_receipt_text(state, result, "vi")
    keyboard = bot.video_dubbing_receipt_keyboard("vi", "translation", state)
    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert "Đã tạo phụ đề gốc thành công" in receipt
    assert "Đã gửi file SRT" in receipt
    assert "Đã gửi video" not in receipt
    assert "📄 Tải SRT" in labels
    assert not any("video" in label.lower() for label in labels)
