from __future__ import annotations

import importlib

import pytest

from services import video_local_validation


MIB = 1024 * 1024


def _media_transport():
    return importlib.import_module("services.video_edit_media_transport")


def test_video_edit_lane_uses_both_short_media_boundaries() -> None:
    media_transport = _media_transport()

    assert media_transport.select_media_lane(duration_seconds=60, size_bytes=20 * MIB) == "short_media"
    assert media_transport.select_media_lane(duration_seconds=61, size_bytes=20 * MIB) == "large_media"
    assert media_transport.select_media_lane(duration_seconds=60, size_bytes=20 * MIB + 1) == "large_media"


@pytest.mark.parametrize(
    ("duration_seconds", "size_bytes"),
    [
        (None, 10 * MIB),
        (0, 10 * MIB),
        (-1, 10 * MIB),
        (30, None),
        (30, 0),
        (30, -1),
    ],
)
def test_video_edit_lane_routes_unknown_or_nonpositive_metadata_to_large(
    duration_seconds: float | None,
    size_bytes: int | None,
) -> None:
    media_transport = _media_transport()

    assert (
        media_transport.select_media_lane(
            duration_seconds=duration_seconds,
            size_bytes=size_bytes,
        )
        == "large_media"
    )


def test_video_edit_can_disable_product_size_and_duration_rejection_only_explicitly() -> None:
    metadata = {
        "ok": True,
        "bytes": 300 * MIB,
        "duration": 7_200,
        "width": 1920,
        "height": 1080,
    }

    size_only = {
        **metadata,
        "bytes": video_local_validation.MAX_UPLOAD_BYTES + 1,
        "duration": 1,
    }
    rejected_by_default = video_local_validation.validate_source_metadata(
        size_only,
        file_size=video_local_validation.MAX_UPLOAD_BYTES + 1,
    )
    assert rejected_by_default["ok"] is False
    assert rejected_by_default["reason"] == "video_too_large"

    duration_only = {
        **metadata,
        "bytes": 1,
        "duration": video_local_validation.MAX_DURATION_SECONDS + 1,
    }
    rejected_duration_by_default = video_local_validation.validate_source_metadata(
        duration_only,
        file_size=1,
    )
    assert rejected_duration_by_default["ok"] is False
    assert rejected_duration_by_default["reason"] == "duration_too_long"

    accepted = video_local_validation.validate_source_metadata(
        metadata,
        file_size=300 * MIB,
        maximum_bytes=0,
        maximum_duration_seconds=0,
    )
    assert accepted["ok"] is True
    assert accepted["reason"] == ""

    invalid_metadata = {**metadata, "ok": False, "reason": "invalid_video_metadata"}
    still_invalid = video_local_validation.validate_source_metadata(
        invalid_metadata,
        file_size=300 * MIB,
        maximum_bytes=0,
        maximum_duration_seconds=0,
    )
    assert still_invalid["ok"] is False
    assert still_invalid["reason"] == "invalid_video_metadata"
