import asyncio
import inspect

import pytest

import bot
from services import subdub_blackboxes
from services.subdub_blackboxes import base, dub_only, subtitle_dub, subtitle_only


def test_each_subdub_mode_has_one_owned_lane_and_preserves_runner_payload():
    cases = {
        bot.VIDEO_SUBTITLE_MODE_CREATE: "subtitle_only",
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE: "subtitle_only",
        bot.VIDEO_SUBTITLE_MODE_DUB: "dub_only",
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB: "subtitle_dub",
    }
    for mode, expected_lane in cases.items():
        calls = []
        state = {"mode": mode, "source_file_id": "fixture-video"}

        async def fake_runner(**payload):
            calls.append(payload)
            return {"ok": True, "mode": payload["mode"], "state": payload["state"]}

        result = asyncio.run(
            subdub_blackboxes.run_subdub_lane_blackbox(
                lane_mode=mode,
                runner=fake_runner,
                job_id="fixture-job",
                mode=mode,
                state=state,
            )
        )

        assert subdub_blackboxes.subdub_lane_name(mode) == expected_lane
        assert len(calls) == 1
        assert calls[0] == {"job_id": "fixture-job", "mode": mode, "state": state}
        assert calls[0]["state"] is state
        assert result == {"ok": True, "mode": mode, "state": state}


def test_subtitle_video_lane_restores_mp4_output_without_touching_file_flow():
    video_state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "video_file_id": "video-fixture",
        "source_mime_type": "video/mp4",
        "output_type": "srt",
    }
    subtitle_file_state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "source_file_id": "subtitle-fixture",
        "source_mime_type": "application/x-subrip",
        "output_type": "srt",
    }

    normalized_video = base.normalize_video_lane_state(
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        video_state,
    )
    normalized_file = base.normalize_video_lane_state(
        bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        subtitle_file_state,
    )

    assert normalized_video["output_type"] == "burn"
    assert normalized_video["_subdub_delivery_active_flow"] == "subdub_video"
    assert video_state["output_type"] == "srt"
    assert normalized_file == subtitle_file_state


def test_combo_video_lane_restores_subtitle_video_output_contract():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "video_file_id": "video-fixture",
        "source_mime_type": "video/mp4",
        "output_type": "srt",
    }

    normalized = base.normalize_video_lane_state(
        bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        state,
    )

    assert normalized["output_type"] == "video_subtitle"
    assert normalized["output_format"] == "video_subtitle"
    assert normalized["_subdub_delivery_active_flow"] == "subdub_video"
    assert state["output_type"] == "srt"


def test_video_lane_carries_delivery_marker_out_of_blackbox():
    async def fake_runner(**kwargs):
        return {"ok": True, "output_type": kwargs["state"].get("output_type")}

    result = asyncio.run(
        subdub_blackboxes.run_subdub_lane_blackbox(
            lane_mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            runner=fake_runner,
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            state={
                "video_file_id": "video-fixture",
                "source_mime_type": "video/mp4",
                "output_type": "srt",
            },
        )
    )

    assert result["output_type"] == "burn"
    assert result["_subdub_delivery_active_flow"] == "subdub_video"


def test_dub_lane_state_is_unchanged():
    state = {
        "mode": bot.VIDEO_SUBTITLE_MODE_DUB,
        "video_file_id": "video-fixture",
        "source_mime_type": "video/mp4",
        "output_type": "video",
    }

    assert base.normalize_video_lane_state(bot.VIDEO_SUBTITLE_MODE_DUB, state) == state


def test_core_resolves_stale_combo_state_before_blackbox_dispatch():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    stale_combo = {
        "mode": bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
        "requested_mode": bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB,
        "active_flow": "subtitle_plus_dub",
    }

    assert bot.subdub_resolved_route_mode("", stale_combo) == bot.VIDEO_SUBTITLE_MODE_SUBTITLE_PLUS_DUB
    assert "mode = subdub_resolved_route_mode(\"\", state)" in source


def test_video_delivery_marker_prevents_auto_srt_after_mp4(monkeypatch):
    calls = []

    async def fake_video_delivery(*_args, **_kwargs):
        calls.append("video")
        return {
            "sent": True,
            "delivery_method": "video",
            "telegram_message_id": "telegram-mp4",
            "file_size_mb": 1.0,
            "size_limit_used": 45.0,
        }

    class Message:
        async def reply_document(self, **_kwargs):
            raise AssertionError("SRT must not be sent after a valid video delivery")

    monkeypatch.setattr(bot, "send_generated_video_bytes_for_delivery", fake_video_delivery)
    result = asyncio.run(
        bot.send_public_subtitle_dub_final_outputs(
            Message(),
            mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            active_flow="subdub_video",
            srt_text="1\n00:00:00,000 --> 00:00:01,000\nTranslated",
            subtitle_items=[{"output_type": "srt", "bytes": b"srt", "filename": "translated.srt"}],
            video_bytes=b"fixture-mp4",
        )
    )

    assert calls == ["video"]
    assert result["final_mp4_delivered"] is True
    assert result["srt_auto_send_suppressed"] is True
    assert result["documents"] == 0


def test_core_passes_lane_delivery_marker_to_existing_delivery_function():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)

    assert 'product_result.get("_subdub_delivery_active_flow")' in source


def test_unknown_or_cross_lane_mode_never_calls_runner():
    calls = []

    async def fake_runner(**payload):
        calls.append(payload)
        return {"ok": True}

    with pytest.raises(ValueError, match="unsupported_subdub_lane_mode"):
        asyncio.run(
            subdub_blackboxes.run_subdub_lane_blackbox(
                lane_mode="unknown",
                runner=fake_runner,
                mode="unknown",
            )
        )
    with pytest.raises(ValueError, match="payload_mode_mismatch"):
        asyncio.run(
            subdub_blackboxes.run_subdub_lane_blackbox(
                lane_mode=bot.VIDEO_SUBTITLE_MODE_DUB,
                runner=fake_runner,
                mode=bot.VIDEO_SUBTITLE_MODE_TRANSLATE,
            )
        )
    assert calls == []


def test_bot_routes_existing_product_runner_through_one_lane_dispatch():
    source = inspect.getsource(bot._execute_video_dubbing_pipeline_core)
    dispatch = source.index("subdub_blackboxes.run_subdub_lane_blackbox(")
    existing_runner = source.index(
        "runner=subtitle_dub_product_pipeline.run_subdub_pipeline,",
        dispatch,
    )

    assert dispatch < existing_runner
    assert "lane_mode=mode" in source[dispatch:existing_runner]
    assert "await subtitle_dub_product_pipeline.run_subdub_pipeline(" not in source


def test_lane_modules_do_not_own_pipeline_provider_mux_or_delivery_logic():
    for module in (base, subtitle_only, dub_only, subtitle_dub, subdub_blackboxes):
        source = inspect.getsource(module).lower()
        for forbidden in (
            "subtitle_dub_product_pipeline",
            "ffmpeg",
            "shopaikey",
            "key4u",
            "send_video",
            "send_document",
            "charge_xu",
        ):
            assert forbidden not in source
