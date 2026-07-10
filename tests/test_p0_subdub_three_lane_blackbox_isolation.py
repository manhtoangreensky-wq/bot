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
