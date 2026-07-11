import asyncio
import inspect
import subprocess

import pytest

import bot
from services import subdub_long_media, subtitle_dub_product_pipeline


def _srt(segments):
    return bot.video_dubbing_srt_from_segments(segments)


def test_29s_video_keeps_single_pass_plan():
    plan = bot.subdub_long_video_chunk_plan(29)
    gate = bot.subdub_duration_gate_payload({"duration": 29}, {}, is_admin=False)

    assert plan["chunking_enabled"] is False
    assert gate["duration_gate_result"] == "pass"
    assert gate["chunk_strategy"] == "single_pass"


def test_subdub_input_is_capped_at_50mb_for_every_user(tmp_path):
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"fixture")
    oversized = 50 * 1024 * 1024 + 1

    assert bot.subdub_input_limit_mb(False) == 50
    assert bot.subdub_input_limit_mb(True) == 50
    result = bot.subdub_validate_saved_input_for_pipeline(
        {
            "ok": True,
            "path": str(source_path),
            "size": oversized,
            "duration": 30,
            "content_type": "video/mp4",
            "source_bytes": b"fixture",
        },
        {"_pipeline_is_admin": True},
    )
    assert result["ok"] is False
    assert result["blocker"] == "video_too_large"


def test_public_upload_copy_explains_50mb_and_300s_part_delivery():
    text = bot.video_dubbing_upload_text(
        {"mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE, "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE},
        "vi",
    )

    assert "50 MB" in text
    assert "300 giây" in text
    assert "chia tối đa 12 phần" in text
    assert "gửi lần lượt" in text


def test_31s_video_is_accepted_with_real_chunk_strategy():
    gate = bot.subdub_duration_gate_payload({"duration": 31}, {}, is_admin=False)

    assert gate["duration_gate_result"] == "pass_long"
    assert gate["chunking_enabled"] is True
    assert gate["chunk_count"] == 2
    assert gate["chunk_strategy"] == "asr_audio_chunks"
    assert gate["input_duration_seconds"] == 31
    assert gate["duration_limit_source"] == "SUBDUB_MAX_DURATION_SECONDS"


def test_500s_video_plans_two_deliverable_mp4_parts():
    plan = bot.subdub_long_project_plan(500)

    assert plan["project_supported"] is True
    assert plan["project_part_count"] == 2
    assert plan["project_part_ranges"] == [
        {"index": 1, "start": 0, "end": 300, "duration": 300},
        {"index": 2, "start": 300, "end": 500, "duration": 200},
    ]


def test_one_hour_video_plans_twelve_parts_and_longer_is_cleanly_blocked():
    one_hour = bot.subdub_long_project_plan(3600)
    too_long = bot.subdub_long_project_plan(3601)

    assert one_hour["project_supported"] is True
    assert one_hour["project_part_count"] == 12
    assert one_hour["project_part_ranges"][-1] == {"index": 12, "start": 3300, "end": 3600, "duration": 300}
    assert too_long["project_supported"] is False
    assert too_long["project_blocker"] == "project_duration_limit_exceeded"


def test_chunk_offsets_preserve_absolute_timing():
    result = subdub_long_media.offset_chunk_segments(
        [{"start": 0.5, "end": 4.0, "text": "second chunk"}],
        chunk_start=30,
        chunk_end=60,
    )

    assert result == [{"start": 30.5, "end": 34.0, "text": "second chunk"}]


def test_external_subtitle_cues_are_clipped_and_reset_for_each_project_part():
    source = [
        {"index": 1, "start": 295, "end": 305, "text": "crosses boundary"},
        {"index": 2, "start": 320, "end": 325, "text": "second part"},
    ]

    first = subdub_long_media.slice_segments_for_project_part(source, part_start=0, part_end=300)
    second = subdub_long_media.slice_segments_for_project_part(source, part_start=300, part_end=500)

    assert first == [{"index": 1, "start": 295.0, "end": 300.0, "text": "crosses boundary"}]
    assert second == [
        {"index": 1, "start": 0.0, "end": 5.0, "text": "crosses boundary"},
        {"index": 2, "start": 20.0, "end": 25.0, "text": "second part"},
    ]


@pytest.mark.parametrize("duration, expected_chunks", [(31, 2), (60, 2)])
def test_long_media_asr_chunks_and_preserves_absolute_timestamps(monkeypatch, duration, expected_chunks):
    extract_calls = []
    asr_calls = []

    async def fake_extract(_source, _content_type, start, chunk_duration):
        extract_calls.append((start, chunk_duration))
        return f"{start}:{chunk_duration}".encode(), "audio/mpeg", "fixture_chunk"

    async def fake_asr(audio_bytes, _content_type, **_kwargs):
        asr_calls.append(bytes(audio_bytes))
        _start, chunk_duration = [float(item) for item in audio_bytes.decode().split(":", 1)]
        return {
            "ok": True,
            "status": "PASS",
            "provider": "fixture_asr",
            "text": f"cue {len(asr_calls)}",
            "segments": [{"start": 0.25, "end": max(0.5, chunk_duration - 0.25), "text": f"cue {len(asr_calls)}"}],
            "language": "en",
        }

    monkeypatch.setattr(bot, "video_dubbing_extract_audio_chunk", fake_extract)
    monkeypatch.setattr(bot, "asr_transcribe_audio", fake_asr)

    result = asyncio.run(
        bot.transcribe_media_to_segments(
            {
                "bytes": b"fixture-video",
                "content_type": "video/mp4",
                "file_name": "fixture.mp4",
                "media_kind": "video",
                "duration_seconds": duration,
            },
            duration_seconds=duration,
        )
    )

    assert result["output_valid"] is True
    assert result["chunk_count"] == expected_chunks
    assert result["chunk_strategy"] == "asr_audio_chunks"
    assert result["global_timing_preserved"] is True
    assert len(extract_calls) == expected_chunks
    assert len(asr_calls) == expected_chunks
    assert result["segments"][0]["start"] == 0.25
    assert result["segments"][1]["start"] == 30.25
    assert result["segments"][-1]["end"] <= duration


def test_29s_transcription_does_not_enter_chunk_path(monkeypatch):
    calls = {"single": 0, "chunk": 0, "asr": 0}

    monkeypatch.setattr(bot, "video_dubbing_audio_extract_ready", lambda: True)

    async def fake_single_extract(_source, _content_type, max_seconds=0):
        calls["single"] += 1
        assert max_seconds == 0
        return b"single-audio", "audio/mpeg", "fixture_single"

    async def fail_chunk(*_args, **_kwargs):
        calls["chunk"] += 1
        raise AssertionError("29s must not use chunk extraction")

    async def fake_asr(_audio, _content_type, **_kwargs):
        calls["asr"] += 1
        return {
            "ok": True,
            "status": "PASS",
            "provider": "fixture_asr",
            "text": "short media",
            "segments": [{"start": 0, "end": 29, "text": "short media"}],
        }

    monkeypatch.setattr(bot, "video_dubbing_extract_audio", fake_single_extract)
    monkeypatch.setattr(bot, "video_dubbing_extract_audio_chunk", fail_chunk)
    monkeypatch.setattr(bot, "asr_transcribe_audio", fake_asr)

    result = asyncio.run(
        bot.transcribe_media_to_segments(
            {"bytes": b"video", "content_type": "video/mp4", "media_kind": "video"},
            duration_seconds=29,
        )
    )

    assert result["output_valid"] is True
    assert result["chunk_strategy"] == "single_pass"
    assert calls == {"single": 1, "chunk": 0, "asr": 1}


def test_long_media_chunk_failure_is_explicit_and_does_not_call_asr(monkeypatch):
    calls = {"asr": 0}

    async def fail_extract(*_args, **_kwargs):
        raise RuntimeError("fixture_extract_failed")

    async def fake_asr(*_args, **_kwargs):
        calls["asr"] += 1
        return {"ok": True, "text": "must not run"}

    monkeypatch.setattr(bot, "video_dubbing_extract_audio_chunk", fail_extract)
    monkeypatch.setattr(bot, "asr_transcribe_audio", fake_asr)

    result = asyncio.run(
        bot.transcribe_media_to_segments(
            {"bytes": b"video", "content_type": "video/mp4", "media_kind": "video"},
            duration_seconds=31,
        )
    )

    assert result["output_valid"] is False
    assert result["status"] == "long_media_chunk_extract_failed"
    assert result["chunk_count"] == 2
    assert calls["asr"] == 0


def test_long_subtitle_pipeline_calls_final_mux_once():
    render_calls = []
    segments = [
        {"index": 1, "start": 0, "end": 30, "text": "first"},
        {"index": 2, "start": 30, "end": 60, "text": "second"},
    ]

    async def prepare(state):
        return {
            "state": dict(state),
            "source_bytes": b"source-video",
            "content_type": "video/mp4",
            "output_subtitle": _srt(segments),
            "output_script": "first second",
            "output_segments": segments,
            "source_segments": segments,
            "asr_provider": "fixture_asr",
        }

    async def render(*_args, **_kwargs):
        render_calls.append(1)
        return b"final-mp4", "fixture_render"

    result = asyncio.run(
        subtitle_dub_product_pipeline.process_subtitle_dub_job(
            mode=subtitle_dub_product_pipeline.VIDEO_SUBTITLE_MODE_TRANSLATE,
            state={"video_duration": 60, "output_type": "burn"},
            user_id=1,
            prepare_subtitles=prepare,
            srt_from_text=lambda text, duration: bot.video_dubbing_srt_from_text(text, duration),
            segments_from_text=bot.video_dubbing_segments_from_text,
            segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
            subtitle_output_items=lambda *_args: [],
            resolve_voice_id=lambda *_args: "",
            parse_voice_speed=lambda _value: 1.0,
            synthesize_segments=lambda *_args, **_kwargs: {},
            build_timeline_audio=lambda *_args, **_kwargs: (b"", ""),
            normalize_audio=lambda audio: (audio, ""),
            render_video=render,
            video_render_ready=lambda _output: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
        )
    )

    assert result["ok"] is True
    assert result["video_output"] == b"final-mp4"
    assert len(render_calls) == 1
    assert result["charged"] is False


def test_500s_project_uses_unique_child_jobs_and_delivers_two_parts(monkeypatch):
    child_states = []
    split_calls = []

    async def fake_split(_source, start, duration):
        split_calls.append((start, duration))
        return f"part:{start}:{duration}".encode()

    async def fake_execute(_query, _context, child_state, _lang, **_kwargs):
        child_states.append(dict(child_state))
        index = int(child_state["long_project_part_index"])
        return {
            "ok": True,
            "video_delivered": True,
            "final_mp4_delivered": True,
            "sent_video": 1,
            "charged": 2,
            "telegram_message_id": str(100 + index),
            "video_delivery_message_id": str(100 + index),
        }

    monkeypatch.setattr(bot, "video_dubbing_extract_video_part", fake_split)
    monkeypatch.setattr(bot, "execute_video_dubbing_pipeline", fake_execute)
    plan = bot.subdub_long_project_plan(500)
    result = asyncio.run(
        bot.execute_subdub_long_project_parts(
            object(),
            object(),
            {
                "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
                "source_file_unique_id": "source-fixture",
                "subtitle_ref": "must-not-leak-to-child",
                "translated_subtitle_ref": "must-not-leak-to-child",
            },
            {"ok": True, "source_bytes": b"full-video", "content_type": "video/mp4"},
            plan,
            "vi",
            admin_interactive_confirm=True,
        )
    )

    assert result["ok"] is True
    assert result["project_part_count"] == 2
    assert result["project_parts_delivered"] == 2
    assert result["sent_video"] == 2
    assert result["charged"] == 4
    assert split_calls == [(0.0, 300.0), (300.0, 200.0)]
    assert len({state["source_file_unique_id"] for state in child_states}) == 2
    assert all("subtitle_ref" not in state for state in child_states)
    assert all("translated_subtitle_ref" not in state for state in child_states)


def test_project_stops_on_failed_part_and_does_not_fake_full_success(monkeypatch):
    calls = []

    async def fake_split(_source, start, duration):
        return f"part:{start}:{duration}".encode()

    async def fake_execute(_query, _context, child_state, _lang, **_kwargs):
        index = int(child_state["long_project_part_index"])
        calls.append(index)
        if index == 1:
            return {
                "ok": True,
                "video_delivered": True,
                "video_delivery_message_id": "201",
                "charged": 3,
                "sent_video": 1,
            }
        return {"ok": False, "status": "PART_FAILED", "detail": "fixture_failure", "charged": 0}

    monkeypatch.setattr(bot, "video_dubbing_extract_video_part", fake_split)
    monkeypatch.setattr(bot, "execute_video_dubbing_pipeline", fake_execute)
    result = asyncio.run(
        bot.execute_subdub_long_project_parts(
            object(),
            object(),
            {"mode": bot.VIDEO_SUBTITLE_MODE_DUB, "source_file_unique_id": "source-fixture"},
            {"ok": True, "source_bytes": b"full-video", "content_type": "video/mp4"},
            bot.subdub_long_project_plan(500),
            "vi",
        )
    )

    assert result["ok"] is False
    assert result["project_parts_delivered"] == 1
    assert result["failed_part_index"] == 2
    assert result["charged"] == 3
    assert result["terminal_state"] == "failed_no_charge"
    assert calls == [1, 2]


def test_one_hour_project_orchestrates_twelve_parts_without_provider_calls():
    processed = []

    async def fake_split(part):
        return f"part-{part['index']}".encode()

    async def fake_process(_part_bytes, part):
        processed.append(int(part["index"]))
        return {
            "ok": True,
            "video_delivered": True,
            "video_delivery_message_id": str(part["index"]),
        }

    result = asyncio.run(
        subdub_long_media.process_long_project_parts(
            bot.subdub_long_project_plan(3600),
            split_part=fake_split,
            process_part=fake_process,
        )
    )

    assert result["ok"] is True
    assert result["project_parts_delivered"] == 12
    assert processed == list(range(1, 13))


@pytest.mark.parametrize(
    "mode",
    [
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    ],
)
def test_all_three_subdub_modes_finish_full_green_with_one_project_receipt_state(monkeypatch, mode):
    async def fake_split(_source, start, duration):
        return f"part:{start}:{duration}".encode()

    async def fake_execute(_query, _context, child_state, _lang, **_kwargs):
        assert bot.normalize_video_translate_mode(child_state["mode"]) == mode
        index = int(child_state["long_project_part_index"])
        return {
            "ok": True,
            "terminal_state": "delivered",
            "video_delivered": True,
            "final_mp4_delivered": True,
            "sent_video": 1,
            "telegram_message_id": str(500 + index),
            "video_delivery_message_id": str(500 + index),
        }

    monkeypatch.setattr(bot, "video_dubbing_extract_video_part", fake_split)
    monkeypatch.setattr(bot, "execute_video_dubbing_pipeline", fake_execute)
    result = asyncio.run(
        bot.execute_subdub_long_project_parts(
            object(),
            object(),
            {"mode": mode, "source_file_unique_id": f"source-{mode}"},
            {"ok": True, "source_bytes": b"full-video", "content_type": "video/mp4"},
            bot.subdub_long_project_plan(500),
            "vi",
        )
    )

    result_state = result["state"]
    assert result["ok"] is True
    assert result["project_parts_delivered"] == 2
    assert result["terminal_state"] == "delivered"
    assert result["video_delivery_message_id"]
    assert result_state["progress_stage"] == "delivered"
    assert result_state["progress_percent"] == 100
    assert result_state["panel_finalized"] is True
    assert result_state["panel_final_percent"] == 100
    assert result_state["status_panel_terminalized"] is True
    assert result_state["terminal_public_outcome_type"] == "success"
    assert result_state["final_mp4_delivered"] is True


def test_long1_debug_fields_are_exposed():
    text = bot.subtitle_dub_debug_text(
        {
            "job_id": "LONG1FIXTURE",
            "input_duration_seconds": 60,
            "duration_limit_source": "SUBDUB_MAX_DURATION_SECONDS",
            "chunk_count": 2,
            "chunk_strategy": "asr_audio_chunks",
            "final_mux_duration": 60,
            "delivery_status": "delivered",
            "project_split_required": True,
            "project_part_count": 2,
            "project_parts_delivered": 2,
            "project_max_duration_seconds": 3600,
        }
    )

    for label in (
        "input duration seconds",
        "duration limit source",
        "chunk strategy",
        "final mux duration",
        "delivery status",
        "project split required",
        "project parts delivered",
        "project max duration",
    ):
        assert label in text


def test_long1_has_no_paid_provider_calls_and_keeps_delivery_route_untouched():
    helper_source = inspect.getsource(subdub_long_media)
    assert "httpx" not in helper_source
    assert "requests." not in helper_source
    assert "shopaikey" not in helper_source.lower()
    assert "key4u" not in helper_source.lower()

    changed = set(
        subprocess.check_output(["git", "diff", "--name-only", "origin/main"], text=True, encoding="utf-8").splitlines()
    )
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], text=True, encoding="utf-8"
    ).strip().lower()
    if (
        "services/subdub_long_media.py" not in changed
        and "subdub-long1" not in branch
        and "subdub_long1" not in branch
    ):
        pytest.skip("LONG1 scope guard only applies while LONG1 is being changed")
    assert changed <= {
        "bot.py",
        "services/subdub_long_media.py",
        "tests/test_p0_subdub_long1_support_over_30_seconds.py",
    }
    assert "services/subtitle_dub_product_pipeline.py" not in changed
    core_source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "execute_subdub_long_project_parts" in core_source
    assert "video_dubbing_deliver_outputs" not in inspect.getsource(bot.execute_subdub_long_project_parts)
