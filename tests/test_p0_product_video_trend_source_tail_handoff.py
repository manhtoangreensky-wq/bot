from __future__ import annotations

import asyncio
from types import SimpleNamespace

import bot
from services import video_flow6, video_tail9


def _trend_state() -> dict:
    source = {
        "file_id": "trend-video-file-id",
        "file_unique_id": "trend-video-unique-id",
        "source_hash": "784FBE5BBD7B8D59",
        "file_name": "PV-L05-self-shot-typing-source.mp4",
        "mime_type": "video/mp4",
        "duration_seconds": 79.4667,
        "width": 1280,
        "height": 720,
    }
    analysis = {
        "analysis_revision": 1,
        "tracking_source": "local_opencv",
        "visual_context": {"orientation": "horizontal"},
        "motion_summary": "Chuyen dong vua",
        "camera_summary": "Camera di chuyen ro",
    }
    trend = {
        "intake_lane": "video_upload",
        "trend_id": "trend_video_784fbe5b",
        "title": "Trend tu video da gui",
        "summary": "PV2-R01 electric coffee cart with reusable cups",
        "source_video_id": source["file_id"],
        "source_video_hash": source["source_hash"],
        "source_video": source,
        "source_analysis": analysis,
        "analysis_revision": 1,
        "analysis_provenance": "local_opencv",
    }
    return {
        "selected_trend": trend,
        "source_video": source,
        "source_analysis": analysis,
        "analysis_revision": 1,
        "scene_count": 2,
        "aspect_ratio": "9:16",
    }


def _bridge(context, *, return_to_review: bool) -> dict:
    profile = bot.video_trend2_canonical_state(context, _trend_state())
    return bot.video_trend_prepare_entity_bridge(
        SimpleNamespace(message=None),
        7126457028,
        context,
        profile,
        return_to_review=return_to_review,
    )


def test_trend_entity_finish_hands_uploaded_source_to_scene3_tail(monkeypatch) -> None:
    context = SimpleNamespace(user_data={})
    bridge = _bridge(context, return_to_review=False)

    async def capture_profile(_target, state, _lang):
        return state

    monkeypatch.setattr(bot, "video_profile_scene1_render", capture_profile)

    profile = asyncio.run(
        bot.video_trend_finish_entity_bridge(
            SimpleNamespace(),
            7126457028,
            context,
            bridge,
        )
    )

    items = list((profile.get("reference_assets") or {}).get("items") or [])
    assert [item.get("file_id") for item in items] == ["trend-video-file-id"]
    assert list((profile.get("reference_assets") or {}).get("source_media_refs") or []) == [
        "trend-video-file-id"
    ]


def test_trend_review_refreshes_embedded_tail_source_ids(monkeypatch) -> None:
    context = SimpleNamespace(user_data={})
    bridge = _bridge(context, return_to_review=True)
    profile = bot.video_profile_studio_state(context)
    profile[bot.VIDEO_TAIL9_STATE_KEY] = video_tail9.new_state(
        product_type="video_trend",
        session_id="trend-live-review",
        scene_count=2,
        ratio="9:16",
        source_asset_ids=[],
    )
    bot.save_video_profile_studio_state(context, profile)

    async def capture_tail(_target, _user_id, current_context, _screen):
        current = bot.video_profile_studio_state(current_context)
        return dict(current.get(bot.VIDEO_TAIL9_STATE_KEY) or {})

    monkeypatch.setattr(bot, "video_tail9_render", capture_tail)

    tail = asyncio.run(
        bot.video_trend_finish_entity_bridge(
            SimpleNamespace(),
            7126457028,
            context,
            bridge,
        )
    )

    assert tail["source_asset_ids"] == ["trend-video-file-id"]


def test_flow6_accepts_the_same_uploaded_trend_source_as_flow7() -> None:
    context = video_flow6.context_from_scene_state(
        {
            "source_product_id": "video_trend",
            "content_mode": "suggestions",
            "scene_count": 2,
            "aspect_ratio": "9:16",
            "primary_profile_key": "social_creator_trend",
            "content_choice": {"id": "pv2-r01", "title": "Coffee cart"},
            "trend_source": _trend_state()["selected_trend"],
        }
    )

    result = video_flow6.preflight(
        context,
        package_available=True,
        engine_ready=True,
        worker_ready=True,
        capability_ready=True,
    )

    assert result["ok"] is True
    assert "trend_source_or_sample_missing" not in result["blockers"]
