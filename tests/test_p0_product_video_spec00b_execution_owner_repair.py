from __future__ import annotations

import pytest
from bot import (
    video_tail9_runtime_only_blocker,
    video_tail9_deferred_runtime_blocker,
    video_tail9_commercial_preflight,
)


STRUCTURAL_TOKENS = (
    "source_video_missing",
    "source_segment_missing",
    "transformation_timeline_missing",
    "subject_selection_missing",
    "subject_description_missing",
    "mandatory_layer_lock_missing",
    "subject_track_missing",
    "face_identity_track_missing",
    "object_track_missing",
    "pet_track_missing",
    "person_object_tracks_missing",
    "multiple_subject_tracks_missing",
    "interaction_lock_missing",
    "scene_count_not_supported",
    "single_scene_not_supported",
    "ratio_not_supported",
    "input_not_ready",
    "assets_not_ready",
    "trend_source",
    "storyboard",
    "scene_image",
    "probe_missing",
    "execution_owner",
    "execution_route",
)

DEFERRED_RUNTIME_TOKENS = (
    "runtime_unavailable",
    "not_server_renderable",
    "renderer_missing",
    "worker_unavailable",
    "provider_unavailable",
)


@pytest.mark.parametrize("token", STRUCTURAL_TOKENS)
def test_structural_tokens_are_not_runtime_only_blockers(token: str) -> None:
    assert video_tail9_runtime_only_blocker(token) is False
    assert video_tail9_runtime_only_blocker(f"preflight_{token}_failure") is False


@pytest.mark.parametrize("token", STRUCTURAL_TOKENS)
def test_structural_tokens_are_not_deferred_runtime_blockers(token: str) -> None:
    assert video_tail9_deferred_runtime_blocker(token) is False


@pytest.mark.parametrize("token", DEFERRED_RUNTIME_TOKENS)
def test_deferred_runtime_tokens_are_recognized(token: str) -> None:
    assert video_tail9_deferred_runtime_blocker(token) is True
    assert video_tail9_deferred_runtime_blocker(f"upstream_{token}_error") is True


def test_structural_blocker_fails_commercial_preflight() -> None:
    class DummyContext:
        pass

    tail = {
        "video_product_type": "video_ai_real",
        "scene_count": 2,
        "ratio": "9:16",
        "required_capability": "text_to_video",
    }
    host = {}

    report = video_tail9_commercial_preflight(
        user_id=123,
        context=DummyContext(),
        tail=tail,
        owner="uiflow3",
        host=host,
        quality=400,
    )
    assert report["ok"] is True
