from __future__ import annotations

import local_worker


def test_videoedit_heartbeat_reports_sanitized_filter_snapshot(monkeypatch) -> None:
    discoveries: list[tuple[str, bool]] = []
    probes: list[str] = []
    resolved_ffmpeg = "C:/resolved/ffmpeg.exe"
    monkeypatch.setattr(local_worker, "local_ffmpeg_path", lambda: resolved_ffmpeg)
    monkeypatch.setattr(
        local_worker,
        "available_ffmpeg_filters",
        lambda path, *, refresh=False: (
            discoveries.append((path, refresh))
            or frozenset({"zoompan", "loudnorm", "hqdn3d", "bad-name", "", "A" * 90})
        ),
        raising=False,
    )
    monkeypatch.setattr(
        local_worker,
        "find_ffprobe",
        lambda ffmpeg_path="": probes.append(ffmpeg_path) or "C:/resolved/ffprobe.exe",
    )

    payload = local_worker.local_worker_heartbeat_payload(queue_depth=2)

    assert payload["video_edit_filters_known"] is True
    assert payload["video_edit_filters"] == ["hqdn3d", "loudnorm", "zoompan"]
    assert payload["video_edit_filter_worker_id"] == local_worker.LOCAL_WORKER_ID
    assert payload["ffmpeg_path"] == resolved_ffmpeg
    assert payload["ffprobe_path"] == "C:/resolved/ffprobe.exe"
    assert payload["video_edit_filter_ffmpeg_path"] == resolved_ffmpeg
    assert discoveries == [(resolved_ffmpeg, True)]
    assert probes == [resolved_ffmpeg]
    assert payload["timestamp_utc"]


def test_videoedit_heartbeat_fails_closed_when_filter_discovery_fails(monkeypatch) -> None:
    def fail(_path: str, *, refresh: bool = False):
        raise RuntimeError("no ffmpeg")

    monkeypatch.setattr(local_worker, "available_ffmpeg_filters", fail, raising=False)

    payload = local_worker.local_worker_heartbeat_payload()

    assert payload["video_edit_filters_known"] is False
    assert payload["video_edit_filters"] == []
    assert payload["video_edit_filter_worker_id"] == local_worker.LOCAL_WORKER_ID
