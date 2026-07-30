from __future__ import annotations

import local_worker


def test_videoedit_heartbeat_reports_sanitized_filter_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(
        local_worker,
        "available_ffmpeg_filters",
        lambda _path: frozenset({"zoompan", "loudnorm", "hqdn3d", "bad-name", "", "A" * 90}),
        raising=False,
    )

    payload = local_worker.local_worker_heartbeat_payload(queue_depth=2)

    assert payload["video_edit_filters_known"] is True
    assert payload["video_edit_filters"] == ["hqdn3d", "loudnorm", "zoompan"]
    assert payload["video_edit_filter_worker_id"] == local_worker.LOCAL_WORKER_ID
    assert payload["video_edit_filter_ffmpeg_path"] == local_worker.LOCAL_FFMPEG_PATH
    assert payload["timestamp_utc"]


def test_videoedit_heartbeat_fails_closed_when_filter_discovery_fails(monkeypatch) -> None:
    def fail(_path: str):
        raise RuntimeError("no ffmpeg")

    monkeypatch.setattr(local_worker, "available_ffmpeg_filters", fail, raising=False)

    payload = local_worker.local_worker_heartbeat_payload()

    assert payload["video_edit_filters_known"] is False
    assert payload["video_edit_filters"] == []
    assert payload["video_edit_filter_worker_id"] == local_worker.LOCAL_WORKER_ID

