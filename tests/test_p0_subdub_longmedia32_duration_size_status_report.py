import asyncio
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import bot
from services import subdub_long_media, subtitle_dub_product_pipeline


MIB = 1024 * 1024


def _preflight_module():
    try:
        return importlib.import_module("services.subdub_media_preflight")
    except ModuleNotFoundError:
        pytest.fail("LONGMEDIA32 canonical media preflight module is missing")


def _canonical_probe_payload(*, duration: float = 61.0) -> dict:
    return {
        "format": {
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "duration": str(duration),
            "start_time": "0.000000",
            "size": "2048",
        },
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "profile": "High",
                "pix_fmt": "yuv420p",
                "width": 720,
                "height": 1280,
                "avg_frame_rate": "25/1",
                "r_frame_rate": "25/1",
                "time_base": "1/12800",
                "start_time": "0.000000",
                "duration": str(duration),
                "tags": {},
                "side_data_list": [],
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
                "channel_layout": "stereo",
                "time_base": "1/48000",
                "start_time": "0.000000",
                "duration": str(duration),
            },
        ],
    }


def _unfamiliar_probe_payload() -> dict:
    return {
        "format": {
            "format_name": "matroska,webm",
            "duration": "90.250",
            "start_time": "1.500000",
            "size": str(24 * MIB),
        },
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "vp9",
                "profile": "Profile 2",
                "pix_fmt": "yuv420p10le",
                "width": 1080,
                "height": 1920,
                "avg_frame_rate": "24000/1001",
                "r_frame_rate": "30/1",
                "time_base": "1/1000",
                "start_time": "1.500000",
                "duration": "90.250",
                "tags": {"rotate": "90"},
                "side_data_list": [{"rotation": 90}],
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "opus",
                "sample_rate": "44100",
                "channels": 6,
                "channel_layout": "5.1",
                "time_base": "1/1000",
                "start_time": "1.500000",
                "duration": "90.000",
            },
            {
                "index": 2,
                "codec_type": "audio",
                "codec_name": "opus",
                "sample_rate": "48000",
                "channels": 2,
                "channel_layout": "stereo",
                "time_base": "1/1000",
                "start_time": "1.500000",
                "duration": "90.000",
            },
        ],
    }


def test_longmedia32_limit_policy_is_bound_to_intake_method(monkeypatch):
    bot_source = Path(bot.__file__).read_text(encoding="utf-8")
    processing_assignment = next(
        line
        for line in bot_source.splitlines()
        if line.startswith("SUBDUB_PROCESSING_MAX_INPUT_MB =")
    )
    assert "min(500," not in processing_assignment
    assert (
        'env_int("SUBDUB_PROCESSING_MAX_INPUT_MB", '
        "SUBDUB_LOCAL_API_MAX_INPUT_MB_DEFAULT)"
    ) in processing_assignment

    monkeypatch.setattr(bot, "SUBDUB_MAX_INPUT_MB", 2000)
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_DOWNLOAD_LIMIT_MB", 2000)
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_CLOUD_DOWNLOAD_LIMIT_MB", 20)
    monkeypatch.setattr(bot, "SUBDUB_PROCESSING_MAX_INPUT_MB", 750, raising=False)
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_SEND_VIDEO_MAX_MB", 45)
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_DOCUMENT_MAX_MB", 49)
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_LOCAL_DOWNLOAD_LIMIT_MAX_MB", 2000)

    assert bot.subdub_input_limit_mb(False, intake_method="cloud_bot_api") == 20
    assert bot.subdub_input_limit_mb(False, intake_method="bot_api_direct", local_api=True) == 750
    assert bot.subdub_input_limit_mb(False, intake_method="local_path_override") == 750
    assert bot.subdub_input_limit_mb(False, intake_method="source_bytes_override") == 750
    assert bot.subdub_output_delivery_limit_mb("video", local_api=True) == 750
    assert bot.subdub_output_delivery_limit_mb("document", local_api=True) == 750
    assert bot.subdub_output_delivery_limit_mb("video", local_api=False) == 45
    assert bot.subdub_output_delivery_limit_mb("document", local_api=False) == 49


def test_longmedia32_post_normalization_size_uses_processing_not_cloud_transport_limit(
    tmp_path,
    monkeypatch,
):
    source_path = tmp_path / "saved-source.mp4"
    source_path.write_bytes(b"saved")
    monkeypatch.setattr(bot, "SUBDUB_PROCESSING_MAX_INPUT_MB", 750, raising=False)
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_CLOUD_DOWNLOAD_LIMIT_MB", 20)
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_DOWNLOAD_LIMIT_MB", 20)
    monkeypatch.setattr(bot, "telegram_local_api_enabled", lambda: False)

    normalized = bot.subdub_validate_saved_input_for_pipeline(
        {
            "ok": True,
            "path": str(source_path),
            "size": 25 * MIB,
            "transport_input_size": 19 * MIB,
            "telegram_file_size": 19 * MIB,
            "duration": 61,
            "content_type": "video/mp4",
            "telegram_download_method": "bot_api_direct",
            "media_normalized": True,
        },
        {},
    )
    processing_overflow = bot.subdub_validate_saved_input_for_pipeline(
        {
            "ok": True,
            "path": str(source_path),
            "size": 751 * MIB,
            "transport_input_size": 19 * MIB,
            "telegram_file_size": 19 * MIB,
            "duration": 61,
            "content_type": "video/mp4",
            "telegram_download_method": "bot_api_direct",
            "media_normalized": True,
        },
        {},
    )

    assert normalized["ok"] is True
    assert processing_overflow["ok"] is False
    assert processing_overflow["blocker"] == "video_too_large"


def test_longmedia32_59_direct_61_chunked_and_unconfigured_duration_is_not_rejected(monkeypatch):
    bot_source = Path(bot.__file__).read_text(encoding="utf-8")
    assert "SUBDUB_PRODUCT_MAX_DURATION_SECONDS" not in bot_source
    assert (
        'SUBDUB_MAX_DURATION_SECONDS = max(0, env_int("SUBDUB_MAX_DURATION_SECONDS", 0))'
        in bot_source
    )

    monkeypatch.setattr(bot, "SUBDUB_MAX_DURATION_SECONDS", 0)
    monkeypatch.setattr(bot, "SUBDUB_LONG_PROJECT_MAX_DURATION_SECONDS", 0)
    monkeypatch.setattr(bot, "SUBDUB_DIRECT_ASR_MAX_SECONDS", 60, raising=False)
    monkeypatch.setattr(bot, "SUBDUB_LONG_CHUNK_SECONDS", 30)

    at_59 = bot.subdub_duration_gate_payload({"duration": 59}, {})
    at_61 = bot.subdub_duration_gate_payload({"duration": 61}, {})
    at_hour = bot.subdub_duration_gate_payload({"duration": 3600}, {})
    beyond_hour = bot.subdub_duration_gate_payload({"duration": 3601}, {})

    assert at_59["duration_gate_result"] == "pass"
    assert at_59["chunking_enabled"] is False
    assert at_59["chunk_strategy"] == "whole_file"
    assert at_61["duration_gate_result"] == "pass_long"
    assert at_61["chunking_enabled"] is True
    assert at_61["chunk_strategy"] == "checkpointed_audio_chunks"
    assert at_hour["duration_gate_result"] == "pass_long"
    assert at_hour["long_media_allowed"] is True
    assert beyond_hour["duration_gate_result"] == "pass_long"
    assert beyond_hour["long_media_allowed"] is True
    assert beyond_hour["duration_limit_seconds"] == 0
    assert bot.subtitle_plus_dub_exceeds_limits({"video_duration": 3601}) is False
    assert "tối đa 0 giây" not in bot.subdub_media_limits_notice("vi")
    monkeypatch.setattr(bot, "telegram_local_api_enabled", lambda: False)
    monkeypatch.setattr(bot, "SUBDUB_TELEGRAM_CLOUD_DOWNLOAD_LIMIT_MB", 20)
    cloud_notice = bot.subdub_media_limits_notice("en")
    assert "Cloud Bot API transport limit: 20 MiB" in cloud_notice
    assert "File limit: 20" not in cloud_notice


def test_longmedia32_legacy_part_planner_has_no_implicit_hour_or_part_cap(monkeypatch):
    bot_source = Path(bot.__file__).read_text(encoding="utf-8")
    assert (
        'SUBDUB_LONG_PROJECT_MAX_PARTS = max(0, env_int("SUBDUB_LONG_PROJECT_MAX_PARTS", 0))'
        in bot_source
    )
    monkeypatch.setattr(bot, "SUBDUB_LONG_PROJECT_MAX_PARTS", 0)
    monkeypatch.setattr(bot, "SUBDUB_LONG_PROJECT_MAX_DURATION_SECONDS", 0)
    assert "1 phút" not in bot.subdub_long_project_over_limit_text("vi")

    unbounded = subdub_long_media.build_long_project_plan(
        7201,
        part_seconds=300,
        max_parts=0,
        max_duration_seconds=0,
    )
    bounded = subdub_long_media.build_long_project_plan(
        601,
        part_seconds=300,
        max_parts=2,
        max_duration_seconds=600,
    )

    assert unbounded["project_supported"] is True
    assert unbounded["project_blocker"] == ""
    assert unbounded["project_max_parts"] == 0
    assert unbounded["project_max_duration_seconds"] == 0
    assert bounded["project_supported"] is False
    assert bounded["project_blocker"] == "project_duration_limit_exceeded"

    monkeypatch.setattr(bot, "SUBDUB_LONG_PROJECT_MAX_PARTS", 2)
    parts_only = bot.subdub_long_project_over_limit_text("vi")
    assert "2 phần" in parts_only
    assert "1 phút" not in parts_only

    monkeypatch.setattr(bot, "SUBDUB_LONG_PROJECT_MAX_PARTS", 0)
    monkeypatch.setattr(bot, "SUBDUB_LONG_PROJECT_MAX_DURATION_SECONDS", 600)
    duration_only = bot.subdub_long_project_over_limit_text("en")
    assert "10 minutes" in duration_only
    assert "0 parts" not in duration_only


def test_longmedia32_fractional_duration_boundaries_never_create_product_cap(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_DIRECT_ASR_MAX_SECONDS", 60, raising=False)
    monkeypatch.setattr(bot, "SUBDUB_MAX_DURATION_SECONDS", 7200)

    over_direct = bot.subdub_duration_gate_payload(
        {"ffprobe_duration": 60.001},
        {},
        ffprobe_duration=60.001,
    )
    beyond_legacy_setting = bot.subdub_duration_gate_payload(
        {"ffprobe_duration": 7200.001},
        {},
        ffprobe_duration=7200.001,
    )

    assert over_direct["input_duration_seconds"] == 61
    assert over_direct["is_long_media"] is True
    assert over_direct["chunking_enabled"] is True
    assert beyond_legacy_setting["input_duration_seconds"] == 7201
    assert beyond_legacy_setting["duration_gate_result"] == "pass_long"
    assert beyond_legacy_setting["duration_limit_seconds"] == 0
    assert bot.subtitle_plus_dub_exceeds_limits({"video_duration": 7201}) is False


def test_longmedia32_saved_input_gate_keeps_fractional_ffprobe_duration(monkeypatch):
    measured_duration = {"value": 60.001}

    async def probe(_payload):
        return {
            "ok": True,
            "duration": measured_duration["value"],
            "has_video": True,
            "has_audio": True,
        }

    monkeypatch.setattr(bot, "subdub_probe_video_bytes", probe)
    monkeypatch.setattr(bot, "SUBDUB_DIRECT_ASR_MAX_SECONDS", 60, raising=False)
    monkeypatch.setattr(bot, "SUBDUB_MAX_DURATION_SECONDS", 0)
    monkeypatch.setattr(bot, "SUBDUB_LONG_PROJECT_MAX_DURATION_SECONDS", 0)
    saved_input = {
        "ok": True,
        "source_bytes": b"fixture",
        "content_type": "video/mp4",
    }

    over_direct = asyncio.run(
        bot.subdub_duration_gate_payload_for_saved_input(saved_input, {})
    )
    measured_duration["value"] = 3600.001
    beyond_hour = asyncio.run(
        bot.subdub_duration_gate_payload_for_saved_input(saved_input, {})
    )

    class FakeTelegramFile:
        file_size = len(b"fixture-video")
        file_path = ""

        async def download_as_bytearray(self, **_kwargs):
            return bytearray(b"fixture-video")

    class FakeBot:
        async def get_file(self, *_args, **_kwargs):
            return FakeTelegramFile()

    class FakeContext:
        bot = FakeBot()

    monkeypatch.setattr(bot, "telegram_local_api_enabled", lambda: False)
    monkeypatch.setattr(bot, "SUBDUB_MAX_DURATION_SECONDS", 180)
    downloaded, content_type = asyncio.run(
        bot.video_dubbing_download_source(
            FakeContext(),
            {
                "video_file_id": "fixture-file",
                "video_file_size": len(b"fixture-video"),
                "video_duration": 3601,
                "source_mime_type": "video/mp4",
            },
        )
    )

    assert over_direct["input_duration_seconds"] == 61
    assert over_direct["chunking_enabled"] is True
    assert beyond_hour["input_duration_seconds"] == 3601
    assert beyond_hour["duration_gate_result"] == "pass_long"
    assert downloaded == b"fixture-video"
    assert content_type == "video/mp4"


def test_longmedia32_public_core_advances_beyond_five_before_slow_preflight(
    tmp_path,
    monkeypatch,
):
    source_path = tmp_path / "source-181s.mp4"
    source_path.write_bytes(b"fixture-video")
    progress_stages = []
    stages_seen_before_preflight = []

    async def save_input(_context, _state, _workspace):
        return {
            "ok": True,
            "source_bytes": b"fixture-video",
            "content_type": "video/mp4",
            "path": str(source_path),
            "exists": True,
            "file_saved": True,
            "size": len(b"fixture-video"),
            "duration": 181,
        }

    async def progress(_query, _job_key, _job_id, stage, _lang):
        progress_stages.append(stage)

    async def slow_preflight(_source, *, content_type):
        assert content_type == "video/mp4"
        stages_seen_before_preflight.extend(progress_stages)
        raise RuntimeError("stop_after_progress_probe")

    monkeypatch.setattr(bot, "video_dubbing_save_input_for_pipeline", save_input)
    monkeypatch.setattr(bot, "subdub_send_progress_update", progress)
    monkeypatch.setattr(bot, "subdub_normalize_video_bytes_if_needed", slow_preflight)
    monkeypatch.setattr(bot, "is_admin_user", lambda _uid: False)

    query = SimpleNamespace(
        from_user=SimpleNamespace(id=32181),
        message=SimpleNamespace(chat_id=32181),
    )
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
        "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_CREATE,
        "video_duration": 181,
        "_pipeline_workspace": str(tmp_path),
        "_pipeline_job_key": "longmedia32-progress-181",
        "_pipeline_job_id": "LONGMEDIA32-181",
    }

    with pytest.raises(RuntimeError, match="stop_after_progress_probe"):
        asyncio.run(bot._execute_video_dubbing_pipeline_core(query, SimpleNamespace(), state))

    assert stages_seen_before_preflight == ["received_video", "saved_input"]
    assert bot.subdub_progress_percent_for_lifecycle(stages_seen_before_preflight[0]) > 5


def test_longmedia32_public_core_never_delivers_split_video_parts():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    assert "execute_subdub_long_project_parts(" not in source
    assert "pass_project_split" not in source


def test_longmedia32_public_core_rejects_any_failed_media_preflight():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert 'elif not media_preflight.get("ok"):' in source
    assert 'elif source_probe.get("normalization_required"):' not in source


def test_longmedia32_canonical_probe_accepts_familiar_mp4_without_normalizing():
    preflight = _preflight_module()
    result = preflight.parse_ffprobe_payload(_canonical_probe_payload(), size_bytes=2048)

    assert result["ok"] is True
    assert result["duration"] == pytest.approx(61.0)
    assert result["container"] == "mp4"
    assert result["video_codec"] == "h264"
    assert result["pixel_format"] == "yuv420p"
    assert result["frame_rate_mode"] == "cfr"
    assert result["display_width"] == 720
    assert result["display_height"] == 1280
    assert result["audio_stream_count"] == 1
    assert result["normalization_required"] is False
    assert result["normalization_reasons"] == []


def test_longmedia32_canonical_probe_classifies_unfamiliar_media_truthfully():
    preflight = _preflight_module()
    result = preflight.parse_ffprobe_payload(_unfamiliar_probe_payload(), size_bytes=24 * MIB)

    assert result["ok"] is True
    assert result["container"] == "webm"
    assert result["video_codec"] == "vp9"
    assert result["bit_depth"] == 10
    assert result["frame_rate_mode"] == "vfr"
    assert result["rotation"] == 90
    assert result["display_width"] == 1920
    assert result["display_height"] == 1080
    assert result["audio_stream_count"] == 2
    assert result["normalization_required"] is True
    assert {
        "container_not_mp4",
        "video_codec_not_h264",
        "pixel_format_not_yuv420p",
        "variable_frame_rate",
        "rotation_metadata",
        "non_zero_start_time",
        "multiple_audio_streams",
        "audio_codec_not_aac",
        "audio_sample_rate_not_48000",
        "audio_layout_not_mono_or_stereo",
    } <= set(result["normalization_reasons"])


def test_longmedia32_normalization_command_preserves_duration_and_has_no_shortest():
    preflight = _preflight_module()
    probe = preflight.parse_ffprobe_payload(_unfamiliar_probe_payload(), size_bytes=24 * MIB)
    command = preflight.build_normalization_command(
        "ffmpeg",
        "input.webm",
        "normalized.mp4",
        probe,
    )

    assert "-shortest" not in command
    assert command[command.index("-t") + 1] == "90.250"
    assert command.count("-map") == 2
    assert "0:v:0" in command
    assert "0:a:0?" in command
    assert "libx264" in command
    assert "yuv420p" in command
    assert "aac" in command
    filter_value = command[command.index("-vf") + 1]
    assert "pad=ceil(iw/2)*2:ceil(ih/2)*2" in filter_value
    assert "setpts=PTS-STARTPTS" in filter_value


def test_longmedia32_unfamiliar_input_is_normalized_once_and_revalidated(monkeypatch):
    preflight = _preflight_module()
    original_probe = preflight.parse_ffprobe_payload(
        _unfamiliar_probe_payload(),
        size_bytes=24 * MIB,
    )
    normalized_payload = _canonical_probe_payload(duration=90.25)
    normalized_payload["streams"][0].update({"width": 1920, "height": 1080})
    normalized_probe = preflight.parse_ffprobe_payload(normalized_payload, size_bytes=4096)
    calls = []

    async def probe(payload):
        return original_probe if payload == b"unfamiliar" else normalized_probe

    async def run(command, timeout=0):
        calls.append((list(command), timeout))
        Path(command[-1]).write_bytes(b"normalized")
        return True, "ok"

    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot, "subdub_probe_video_bytes", probe)
    monkeypatch.setattr(bot, "run_subdub_ffmpeg_command", run)

    result = asyncio.run(
        bot.subdub_normalize_video_bytes_if_needed(
            b"unfamiliar",
            content_type="video/webm",
        )
    )

    assert result["ok"] is True
    assert result["normalized"] is True
    assert result["source_bytes"] == b"normalized"
    assert result["source_sha256"] != result["normalized_sha256"]
    assert result["source_duration"] == pytest.approx(90.25)
    assert result["normalized_duration"] == pytest.approx(90.25)
    assert result["duration_preserved"] is True
    assert result["geometry_preserved"] is True
    assert len(calls) == 1
    assert "-shortest" not in calls[0][0]


@pytest.mark.parametrize(
    ("stage", "duration", "minimum"),
    [
        ("probe", 300.0, 60),
        ("extract", 300.0, 300),
        ("normalize", 300.0, 600),
        ("render", 300.0, 900),
        ("compress", 300.0, 900),
    ],
)
def test_longmedia32_timeouts_are_derived_from_measured_duration(stage, duration, minimum):
    preflight = _preflight_module()
    timeout = preflight.timeout_for_stage(
        stage,
        duration_seconds=duration,
        size_bytes=75 * MIB,
        max_timeout_seconds=10_800,
    )
    assert timeout >= minimum
    assert timeout <= 10_800
    if stage == "render":
        assert preflight.timeout_for_stage(
            stage,
            duration_seconds=1800,
            size_bytes=75 * MIB,
            max_timeout_seconds=10_800,
        ) > 7200


def test_longmedia32_chunk_plan_has_stable_ids_overlap_and_global_ownership(monkeypatch):
    monkeypatch.setattr(bot, "SUBDUB_DIRECT_ASR_MAX_SECONDS", 60, raising=False)
    plan = bot.subdub_long_video_chunk_plan(
        90,
        chunk_seconds=30,
        source_hash="a" * 64,
        overlap_ms=1500,
    )

    metadata = plan["chunk_metadata"]
    assert plan["chunk_count"] == 3
    assert len({item["chunk_id"] for item in metadata}) == 3
    assert all(item["source_hash"] == "a" * 64 for item in metadata)
    assert metadata[0]["ownership_start_ms"] == 0
    assert metadata[0]["ownership_end_ms"] == 30_000
    assert metadata[0]["extract_end_ms"] == 31_500
    assert metadata[1]["extract_start_ms"] == 28_500
    assert metadata[1]["ownership_start_ms"] == 30_000
    assert metadata[1]["ownership_end_ms"] == 60_000
    assert metadata[-1]["extract_end_ms"] == 90_000
    assert plan["global_timing_preserved"] is True


def test_longmedia32_asr_checkpoint_reuses_chunks_and_deduplicates_overlap(tmp_path):
    calls = []
    ranges = [
        {
            "index": 1,
            "chunk_id": "chunk-one",
            "start": 0.0,
            "end": 31.5,
            "extract_start_ms": 0,
            "extract_end_ms": 31_500,
            "ownership_start_ms": 0,
            "ownership_end_ms": 30_000,
            "source_hash": "source-hash",
        },
        {
            "index": 2,
            "chunk_id": "chunk-two",
            "start": 28.5,
            "end": 61.0,
            "extract_start_ms": 28_500,
            "extract_end_ms": 61_000,
            "ownership_start_ms": 30_000,
            "ownership_end_ms": 61_000,
            "source_hash": "source-hash",
        },
    ]

    async def extract(_source, _content_type, start, _duration):
        return (b"chunk-1" if start == 0 else b"chunk-2"), "audio/mpeg", "fixture"

    async def transcribe(payload, _content_type):
        calls.append(payload)
        if payload == b"chunk-1":
            return {
                "ok": True,
                "status": "PASS",
                "provider": "fixture",
                "text": "intro boundary",
                "segments": [
                    {"start": 1.0, "end": 2.0, "text": "intro"},
                    {"start": 29.0, "end": 31.0, "text": "boundary"},
                ],
            }
        return {
            "ok": True,
            "status": "PASS",
            "provider": "fixture",
            "text": "boundary outro",
            "segments": [
                {"start": 0.5, "end": 2.5, "text": "boundary"},
                {"start": 3.0, "end": 5.0, "text": "outro"},
            ],
        }

    checkpoint = tmp_path / "asr_chunks.json"
    first = asyncio.run(
        subdub_long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            ranges,
            extract_chunk=extract,
            transcribe_chunk=transcribe,
            input_duration_seconds=61,
            source_hash="source-hash",
            checkpoint_path=str(checkpoint),
        )
    )

    assert first["ok"] is True
    assert calls == [b"chunk-1", b"chunk-2"]
    assert [item["text"] for item in first["segments"]] == ["intro", "boundary", "outro"]
    assert first["overlap_duplicate_count"] == 1
    assert checkpoint.is_file()

    async def no_extract(*_args, **_kwargs):
        raise AssertionError("completed ASR chunk was extracted again")

    async def no_submit(*_args, **_kwargs):
        raise AssertionError("completed ASR chunk was resubmitted")

    second = asyncio.run(
        subdub_long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            ranges,
            extract_chunk=no_extract,
            transcribe_chunk=no_submit,
            input_duration_seconds=61,
            source_hash="source-hash",
            checkpoint_path=str(checkpoint),
        )
    )

    assert second["ok"] is True
    assert second["checkpoint_reused_count"] == 2
    assert [item["text"] for item in second["segments"]] == ["intro", "boundary", "outro"]

    text_only_checkpoint = tmp_path / "asr_text_only_chunks.json"

    async def transcribe_text_only(payload, _content_type):
        if payload == b"chunk-1":
            return {"ok": True, "status": "PASS", "text": "intro shared boundary"}
        return {"ok": True, "status": "PASS", "text": "shared boundary outro"}

    text_only = asyncio.run(
        subdub_long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            ranges,
            extract_chunk=extract,
            transcribe_chunk=transcribe_text_only,
            input_duration_seconds=61,
            source_hash="source-hash-text-only",
            checkpoint_path=str(text_only_checkpoint),
        )
    )

    assert text_only["ok"] is True
    assert [item["text"] for item in text_only["segments"]] == [
        "intro shared boundary",
        "outro",
    ]
    assert text_only["segments"][0]["end"] <= text_only["segments"][1]["start"]
    assert text_only["text"].casefold().split().count("shared") == 1
    assert text_only["text"].casefold().split().count("boundary") == 1


def test_longmedia32_overlap_jitter_cannot_drop_both_boundary_copies():
    ranges = [
        {
            "index": 1,
            "chunk_id": "jitter-one",
            "extract_start_ms": 0,
            "extract_end_ms": 31_500,
            "ownership_start_ms": 0,
            "ownership_end_ms": 30_000,
        },
        {
            "index": 2,
            "chunk_id": "jitter-two",
            "extract_start_ms": 28_500,
            "extract_end_ms": 61_500,
            "ownership_start_ms": 30_000,
            "ownership_end_ms": 60_000,
        },
        {
            "index": 3,
            "chunk_id": "jitter-three",
            "extract_start_ms": 58_500,
            "extract_end_ms": 90_000,
            "ownership_start_ms": 60_000,
            "ownership_end_ms": 90_000,
        },
    ]

    async def extract(_source, _content_type, start, _duration):
        payload = b"jitter-1" if start == 0 else b"jitter-2" if start == 28.5 else b"jitter-3"
        return payload, "audio/mpeg", "fixture"

    async def transcribe(payload, _content_type):
        if payload == b"jitter-1":
            return {
                "ok": True,
                "status": "PASS",
                "text": "intro boundary",
                "segments": [
                    {"start": 1.0, "end": 2.0, "text": "intro"},
                    {"start": 29.8, "end": 30.8, "text": "boundary"},
                ],
            }
        if payload == b"jitter-2":
            return {
                "ok": True,
                "status": "PASS",
                "text": "boundary outro",
                "segments": [
                    {"start": 0.7, "end": 1.7, "text": "boundary"},
                    {"start": 3.0, "end": 4.0, "text": "outro"},
                ],
            }
        return {
            "ok": True,
            "status": "PASS",
            "text": "finish",
            "segments": [
                {"start": 3.0, "end": 4.0, "text": "finish"},
            ],
        }

    result = asyncio.run(
        subdub_long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            ranges,
            extract_chunk=extract,
            transcribe_chunk=transcribe,
            input_duration_seconds=90,
            source_hash="source-hash",
        )
    )

    assert result["ok"] is True
    assert [item["text"] for item in result["segments"]] == ["intro", "boundary", "outro", "finish"]
    assert result["overlap_duplicate_count"] == 1


def test_longmedia32_acceptance_unknown_never_resubmits_chunk(tmp_path):
    ranges = [
        {
            "index": 1,
            "chunk_id": "unknown-chunk",
            "start": 0.0,
            "end": 30.0,
            "extract_start_ms": 0,
            "extract_end_ms": 30_000,
            "ownership_start_ms": 0,
            "ownership_end_ms": 30_000,
            "source_hash": "source-hash",
        }
    ]
    attempts = []

    async def extract(*_args):
        return b"audio", "audio/mpeg", "fixture"

    async def timeout_submit(*_args):
        attempts.append("submit")
        raise asyncio.TimeoutError()

    checkpoint = tmp_path / "unknown.json"
    first = asyncio.run(
        subdub_long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            ranges,
            extract_chunk=extract,
            transcribe_chunk=timeout_submit,
            input_duration_seconds=30,
            source_hash="source-hash",
            checkpoint_path=str(checkpoint),
        )
    )
    assert first["status"] == "ACCEPTANCE_UNKNOWN"
    assert attempts == ["submit"]

    async def must_not_submit(*_args):
        raise AssertionError("ACCEPTANCE_UNKNOWN was resubmitted")

    second = asyncio.run(
        subdub_long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            ranges,
            extract_chunk=extract,
            transcribe_chunk=must_not_submit,
            input_duration_seconds=30,
            source_hash="source-hash",
            checkpoint_path=str(checkpoint),
        )
    )
    assert second["status"] == "ACCEPTANCE_UNKNOWN"
    assert second["provider_submit_count"] == 0


def test_longmedia32_returned_provider_timeout_is_checkpointed_without_resubmit(tmp_path):
    ranges = [
        {
            "index": 1,
            "chunk_id": "returned-timeout",
            "start": 0.0,
            "end": 30.0,
            "extract_start_ms": 0,
            "extract_end_ms": 30_000,
            "ownership_start_ms": 0,
            "ownership_end_ms": 30_000,
        }
    ]
    attempts = []

    async def extract(*_args):
        return b"audio", "audio/mpeg", "fixture"

    async def returned_timeout(*_args):
        attempts.append("submit")
        return {
            "ok": False,
            "status": "FAIL_TIMEOUT",
            "text": "",
            "segments": [],
            "detail": "request timed out after submit",
        }

    checkpoint = tmp_path / "returned-timeout.json"
    first = asyncio.run(
        subdub_long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            ranges,
            extract_chunk=extract,
            transcribe_chunk=returned_timeout,
            input_duration_seconds=30,
            source_hash="source-hash",
            checkpoint_path=str(checkpoint),
        )
    )

    async def must_not_submit(*_args):
        raise AssertionError("returned provider timeout was resubmitted")

    second = asyncio.run(
        subdub_long_media.transcribe_long_media_chunks(
            b"source",
            "video/mp4",
            ranges,
            extract_chunk=extract,
            transcribe_chunk=must_not_submit,
            input_duration_seconds=30,
            source_hash="source-hash",
            checkpoint_path=str(checkpoint),
        )
    )

    assert attempts == ["submit"]
    assert first["status"] == "ACCEPTANCE_UNKNOWN"
    assert second["status"] == "ACCEPTANCE_UNKNOWN"
    assert second["provider_submit_count"] == 0


def test_longmedia32_pr606_tts_timeline_preserves_full_speech_without_overlap():
    plan = bot.subdub_plan_dub_timeline(
        [
            {"cue_id": "one", "start": 0.0, "end": 1.0, "audio_duration": 1.4},
            {"cue_id": "two", "start": 1.0, "end": 2.0, "audio_duration": 1.2},
        ],
        2.0,
        max_output_duration=3600,
    )
    assert plan["ok"] is True
    assert plan["timeline_duration"] >= 2.0
    assert plan["timeline_extended"] is True
    assert plan["overlap_count"] == 0
    assert plan["final_audio_end"] <= plan["timeline_duration"]


def test_longmedia32_public_product_contract_never_truncates_pr606_tts():
    render_calls = []

    async def prepare(state):
        return {
            "state": state,
            "source_bytes": b"source-video",
            "content_type": "video/mp4",
            "source_segments": [{"index": 1, "start": 0.0, "end": 2.0, "text": "hello"}],
            "output_segments": [{"index": 1, "start": 0.0, "end": 2.0, "text": "hello"}],
            "output_subtitle": "1\n00:00:00,000 --> 00:00:02,000\nhello\n",
            "output_script": "hello",
            "asr_provider": "fixture",
        }

    async def synthesize(*_args, **_kwargs):
        return {
            "provider": "fixture-tts",
            "chunks": [
                {
                    "index": 1,
                    "start": 0.0,
                    "end": 2.0,
                    "audio_duration": 3.0,
                    "audio_bytes": b"speech",
                }
            ],
        }

    async def timeline(_chunks, total_duration):
        assert total_duration == pytest.approx(2.0)
        return b"complete-sequential-audio", "duration=3.000;sequential=yes"

    async def normalize(payload):
        return payload, "ok"

    async def validate_audio(_payload):
        return {"ok": True, "duration": 3.0, "active_duration": 1.5}

    async def render(_source, **kwargs):
        render_calls.append(dict(kwargs))
        return b"final-mp4", "source_duration_preserved=2.000;output_duration=2.000"

    result = asyncio.run(
        subtitle_dub_product_pipeline.process_subtitle_dub_job(
            mode=bot.VIDEO_SUBTITLE_MODE_DUB,
            state={
                "video_duration": 2.0,
                "input_duration_seconds": 2.0,
                "output_type": "video",
            },
            user_id=32,
            prepare_subtitles=prepare,
            srt_from_text=bot.video_dubbing_srt_from_text,
            segments_from_text=bot.video_dubbing_segments_from_text,
            segments_from_subtitle=bot.video_dubbing_segments_from_subtitle,
            subtitle_output_items=bot.video_dubbing_subtitle_output_items,
            resolve_voice_id=lambda *_args: "fixture-voice",
            parse_voice_speed=lambda *_args: 1.0,
            synthesize_segments=synthesize,
            build_timeline_audio=timeline,
            normalize_audio=normalize,
            validate_audio=validate_audio,
            render_video=render,
            video_render_ready=lambda _output: True,
            ffmpeg_ready=lambda: True,
            dub_mux_enabled=True,
        )
    )

    assert result["ok"] is True
    assert result["final_video_expected_duration"] == pytest.approx(3.0)
    assert render_calls[0]["target_duration_seconds"] == pytest.approx(3.0)


def test_longmedia32_renderer_keeps_source_and_extends_for_complete_pr606_tts(monkeypatch):
    commands = []

    async def probe(_payload):
        return {"ok": True, "duration": 2.0, "has_audio": True, "width": 320, "height": 568}

    async def run(command, timeout=0):
        commands.append((list(command), timeout))
        Path(command[-1]).write_bytes(b"valid-mp4")
        return True, "ok"

    async def validate(_payload, **kwargs):
        assert kwargs["expected_duration"] == pytest.approx(4.348)
        return {
            "ok": True,
            "detail": "ok",
            "duration": 4.348,
            "actual_duration": 4.348,
            "has_video": True,
            "has_audio": True,
            "duration_coverage_ok": True,
        }

    monkeypatch.setattr(bot, "frame_video_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(bot, "subdub_probe_video_bytes", probe)
    monkeypatch.setattr(bot, "run_subdub_ffmpeg_command", run)
    monkeypatch.setattr(bot, "subdub_validate_video_output", validate)

    output, detail = asyncio.run(
        bot.video_dubbing_render_video(
            b"source",
            dubbed_audio=b"audio",
            subtitle_style={"show_subtitles": False},
            target_duration_seconds=4.348,
            preserve_source_duration=True,
            require_audio=True,
        )
    )

    assert output == b"valid-mp4"
    command = commands[-1][0]
    assert "-shortest" not in command
    assert command[command.index("-t") + 1] == "4.348"
    assert any("tpad=stop_mode=clone:stop_duration=2.348" in item for item in command)
    assert "render_duration=4.348" in detail
    assert "video_extended_by=2.348" in detail


def test_longmedia32_output_validation_rejects_absolute_long_video_truncation(monkeypatch):
    async def probe(_payload):
        return {
            "ok": True,
            "detail": "ok",
            "duration": 292.0,
            "has_video": True,
            "has_audio": True,
            "size": 2048,
        }

    monkeypatch.setattr(bot, "subdub_probe_video_bytes", probe)
    result = asyncio.run(
        bot.subdub_validate_video_output(
            b"x" * 2048,
            require_audio=True,
            min_bytes=16,
            expected_duration=300.0,
        )
    )

    assert result["ok"] is False
    assert result["detail"] == "video_duration_coverage_failed"
    assert result["duration_min_required"] >= 299.0

    async def unavailable_probe(_payload):
        return {
            "ok": False,
            "detail": "ffprobe_unavailable",
            "duration": 0.0,
            "has_video": False,
            "has_audio": False,
            "size": 2048,
        }

    monkeypatch.setattr(bot, "subdub_probe_video_bytes", unavailable_probe)
    monkeypatch.setattr(bot, "SUBDUB_VALIDATE_ALLOW_FFPROBE_MISSING", True)
    marker_payload = b"\x00\x00\x00\x18ftypmp42" + (b"x" * 2048)
    unproven = asyncio.run(
        bot.subdub_validate_video_output(
            marker_payload,
            require_audio=True,
            min_bytes=16,
            expected_duration=300.0,
        )
    )
    assert unproven["ok"] is False
    assert unproven["detail"] == "ffprobe_required_for_duration_or_audio_validation"


def test_longmedia32_translated_artifact_identity_rejects_source_and_missing_srt(tmp_path):
    source_path = tmp_path / "source.mp4"
    final_path = tmp_path / "final.mp4"
    source_path.write_bytes(b"source-video")
    final_path.write_bytes(b"translated-video")
    valid_srt = b"1\n00:00:00,000 --> 00:00:01,000\nXin chao\n"

    same = bot.subdub_validate_transformed_artifact_identity(
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        source_bytes=b"source-video",
        final_bytes=b"source-video",
        source_path=str(source_path),
        final_path=str(source_path),
        subtitle_bytes=valid_srt,
        target_language="vi",
        cue_count=1,
    )
    assert same["ok"] is False
    assert same["blocker"] in {"output_path_is_source_path", "output_hash_matches_source"}

    missing_srt = bot.subdub_validate_transformed_artifact_identity(
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        source_bytes=b"source-video",
        final_bytes=b"translated-video",
        source_path=str(source_path),
        final_path=str(final_path),
        subtitle_bytes=b"",
        target_language="vi",
        cue_count=0,
    )
    assert missing_srt["ok"] is False
    assert missing_srt["blocker"] == "translated_subtitle_artifact_missing"

    incomplete = bot.subdub_validate_transformed_artifact_identity(
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        source_bytes=b"source-video",
        final_bytes=b"translated-video",
        subtitle_bytes=valid_srt,
        source_subtitle_bytes=valid_srt,
        source_language="en",
        target_language="vi",
        cue_count=1,
        translation_missing_count=1,
    )
    assert incomplete["ok"] is False
    assert incomplete["blocker"] == "translation_incomplete"

    unchanged_translation = bot.subdub_validate_transformed_artifact_identity(
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        source_bytes=b"source-video",
        final_bytes=b"translated-video",
        subtitle_bytes=valid_srt,
        source_subtitle_bytes=valid_srt,
        source_language="en",
        target_language="vi",
        cue_count=1,
    )
    assert unchanged_translation["ok"] is False
    assert unchanged_translation["blocker"] == "translated_subtitle_matches_source"

    valid = bot.subdub_validate_transformed_artifact_identity(
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        source_bytes=b"source-video",
        final_bytes=b"translated-video",
        source_path=str(source_path),
        final_path=str(final_path),
        subtitle_bytes=valid_srt,
        source_language="en",
        target_language="vi",
        cue_count=1,
    )
    assert valid["ok"] is True
    assert valid["source_sha256"] != valid["output_sha256"]
    assert valid["subtitle_sha256"]


def test_longmedia32_progress_is_monotonic_and_delivery_forces_100(monkeypatch):
    key = "longmedia32-progress"
    bot.SUBTITLE_DUB_PIPELINE_JOBS.pop(key, None)
    monkeypatch.setattr(bot, "persist_subtitle_dub_pipeline_job_snapshot", lambda *_args, **_kwargs: True)
    bot.SUBTITLE_DUB_PIPELINE_JOBS[key] = {
        "job_id": "longmedia32-progress",
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "progress_stage": "translating",
        "progress_percent": 55,
        "terminal_state": "",
    }

    regressed = bot.update_subtitle_dub_pipeline_job(
        key,
        progress_stage="extracting_audio",
        progress_percent=25,
    )
    assert regressed["progress_percent"] == 55
    assert regressed["progress_stage"] == "translating"

    delivered = bot.update_subtitle_dub_pipeline_job(
        key,
        terminal_state="delivered",
        video_delivery_message_id="32001",
    )
    assert delivered["progress_percent"] == 100
    assert delivered["progress_stage"] == "delivered"


@pytest.mark.parametrize(
    "mode",
    [
        bot.VIDEO_SUBTITLE_MODE_CREATE,
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        bot.VIDEO_SUBTITLE_MODE_DUB,
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
    ],
)
def test_longmedia32_four_lanes_share_one_canonical_final_report(mode):
    state = {
        "mode": mode,
        "video_processing_mode": mode,
        "terminal_state": "delivered",
        "source_language": "English",
        "target_language": "Tiếng Việt" if mode != bot.VIDEO_SUBTITLE_MODE_CREATE else "",
        "source_duration": 90.0,
        "input_duration_seconds": 90.0,
    }
    result = {
        **state,
        "final_mp4_delivered": True,
        "video_delivered": True,
        "video_delivery_message_id": "32032",
        "terminal_public_outcome_type": "success",
        "canonical_final_artifact_duration": 90.0,
        "final_mp4_duration": 90.0,
        "duration_coverage_ok": True,
        "artifact_validation_result": "ok",
        "original_cue_count": 4,
        "translated_cue_count": 4 if mode != bot.VIDEO_SUBTITLE_MODE_CREATE else 0,
        "tts_expected_segments": 4 if mode in {bot.VIDEO_SUBTITLE_MODE_DUB, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB} else 0,
        "tts_generated_segments": 4 if mode in {bot.VIDEO_SUBTITLE_MODE_DUB, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB} else 0,
        "tts_mixed_segments": 4 if mode in {bot.VIDEO_SUBTITLE_MODE_DUB, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB} else 0,
        "tts_dropped_segments": 0,
        "audio_active_duration": 8.5 if mode in {bot.VIDEO_SUBTITLE_MODE_DUB, bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB} else 0.0,
        "final_price_xu": 12,
        "charged_xu": 10,
        "account_balance_xu": 990,
        "public_job_id": "LONGMEDIA32",
    }

    text = bot.video_dubbing_receipt_text(state, result, "vi")

    for label in (
        "Mã xử lý:",
        "Kết quả:",
        "Ngôn ngữ dịch:",
        "Loại dịch vụ:",
        "Thời lượng:",
        "Giá:",
        "Đã trừ:",
        "Tài khoản còn:",
        "Trạng thái:",
    ):
        assert label in text
    for removed_label in (
        "Ngôn ngữ nguồn:",
        "Thời lượng nguồn:",
        "Thời lượng kết quả:",
        "Số câu phụ đề:",
        "TTS dự kiến/tạo/ghép/bỏ:",
        "Âm thanh hoạt động:",
        "Kiểm tra file:",
    ):
        assert removed_label not in text
    assert "Kết quả đã gửi phía trên" not in text
    assert text.count("Mã xử lý:") == 1
    if mode == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB:
        staged_combo = bot.video_dubbing_receipt_text(
            {
                **state,
                "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
                "video_processing_mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
                "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            },
            {
                **result,
                "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
                "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            },
            "vi",
        )
        assert "Loại dịch vụ: <b>Combo phụ đề - lồng tiếng</b>" in staged_combo
        assert "Loại dịch vụ: <b>Phụ đề dịch</b>" not in staged_combo


def test_longmedia32_international_report_uses_same_canonical_fields():
    text = bot.video_dubbing_receipt_text(
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "terminal_state": "delivered",
            "source_language": "Japanese",
            "target_language": "English",
            "source_duration": 61.0,
        },
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "terminal_state": "delivered",
            "final_mp4_delivered": True,
            "video_delivered": True,
            "video_delivery_message_id": "32033",
            "canonical_final_artifact_duration": 61.0,
            "duration_coverage_ok": True,
            "artifact_validation_result": "ok",
            "original_cue_count": 3,
            "translated_cue_count": 3,
            "tts_expected_segments": 3,
            "tts_generated_segments": 3,
            "tts_mixed_segments": 3,
            "tts_dropped_segments": 0,
            "audio_active_duration": 7.0,
            "final_price_xu": 40,
            "charged_xu": 36,
            "account_balance_xu": 964,
            "public_job_id": "LONGMEDIA32-EN",
        },
        "en",
    )

    for label in (
        "Support code:",
        "Result:",
        "Translation language:",
        "Service type:",
        "Duration:",
        "Price:",
        "Charged:",
        "Account balance:",
        "Status:",
    ):
        assert label in text
    assert "The result was sent above" not in text


def test_longmedia32_delivery_report_does_not_expose_internal_validation_detail():
    text = bot.video_dubbing_receipt_text(
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "terminal_state": "delivered",
            "source_duration": 61.0,
        },
        {
            "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
            "terminal_state": "delivered",
            "final_mp4_delivered": True,
            "video_delivered": True,
            "video_delivery_message_id": "32034",
            "canonical_final_artifact_duration": 61.0,
            "public_job_id": "LONGMEDIA32-UNKNOWN-QC",
        },
        "en",
    )

    assert "File validation:" not in text
    assert "Kiểm tra file:" not in text
