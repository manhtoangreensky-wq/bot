from __future__ import annotations

import asyncio
import inspect
import http.server
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import local_worker
import pytest
from services import frame_video_commercial, frame_video_public_seam as seam


REPO_ROOT = Path(__file__).resolve().parents[1]


def _function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    starts = [f"async def {name}", f"def {name}"]
    start = min(
        (source.find(marker) for marker in starts if source.find(marker) >= 0),
        default=-1,
    )
    if start < 0:
        raise AssertionError(f"function not found: {name}")
    next_positions = [
        position
        for marker in ("\nasync def ", "\ndef ", "\nclass ", "\n@")
        for position in [source.find(marker, start + 1)]
        if position >= 0
    ]
    return source[start : min(next_positions) if next_positions else len(source)]


def _compile_bot_function(name: str, namespace: dict):
    source = (
        "from __future__ import annotations\n\n"
        + _function_source(REPO_ROOT / "bot.py", name)
    )
    exec(compile(source, filename="bot.py", mode="exec"), namespace)
    return namespace[name]


def _compile_worker_function(name: str, namespace: dict):
    helpers = ""
    for helper_name in ("_video_edit_bounded_json_response", "safe_display_filename", "telegram_delivery_error_chain_safe_message"):
        try:
            helpers += "\n\n" + _function_source(REPO_ROOT / "local_worker.py", helper_name)
        except AssertionError:
            pass
    source = (
        "from __future__ import annotations\n\nimport time\n_VIDEO_EDIT_TELEGRAM_JSON_MAX_BYTES = 20 * 1024 * 1024\n\n"
        + helpers
        + "\n\n"
        + _function_source(REPO_ROOT / "local_worker.py", name)
    )
    exec(compile(source, filename="local_worker.py", mode="exec"), namespace)
    return namespace[name]


def test_29o_failed_worker_transition_requires_claimed_worker_identity() -> None:
    previous = {
        "job_type": "frame_video_render",
        "status": "running",
        "worker_id": "frame-worker-29o",
    }

    assert (
        seam.frame_video_worker_transition_blocker(previous, "failed", "")
        == "frame_worker_identity_missing"
    )
    assert (
        seam.frame_video_worker_transition_blocker(
            previous,
            "failed",
            "different-worker",
        )
        == "frame_worker_identity_mismatch"
    )


def test_29o_storage_cas_rejects_receipt_race_after_stale_read() -> None:
    original_receipt = json.dumps(
        {
            "frame_job_id": "fv-terminal-cas-race",
            "local_worker_job_id": "29011",
            "delivery_message_id": "29011",
            "delivery_file_id": "frame-file-original",
        },
        sort_keys=True,
    )
    initial_job = {
        "id": 29011,
        "job_type": "frame_video_render",
        "status": "running",
        "worker_id": "frame-worker-29o",
        "output_url": "",
        "output_file_id": "",
        "started_at": "2026-08-02 13:00:00",
        "finished_at": "",
    }
    terminal_job = {
        **initial_job,
        "status": "succeeded",
        "output_url": original_receipt,
        "output_file_id": "frame-file-original",
        "finished_at": "2026-08-02 13:00:01",
    }
    reads = iter((initial_job, terminal_job))

    class Cursor:
        rowcount = 0

    class Connection:
        def execute(self, sql, _params):
            normalized = " ".join(str(sql).split()).lower()
            assert "where id=? and status=? and worker_id=?" in normalized
            return Cursor()

        def commit(self) -> None:
            return None

        def close(self) -> None:
            return None

    updater = _compile_bot_function(
        "update_local_worker_job",
        {
            "LOCAL_WORKER_JOB_STATUSES": {
                "queued",
                "running",
                "succeeded",
                "failed",
                "cancelled",
            },
            "get_local_worker_job": lambda _job_id: dict(next(reads)),
            "frame_video_public_seam": seam,
            "now_text": lambda: "2026-08-02 13:00:02",
            "db_connect": lambda: Connection(),
            "save_tool_test_result": lambda *_args, **_kwargs: None,
        },
    )

    with pytest.raises(ValueError, match="frame_terminal_receipt_conflict"):
        updater(
            29011,
            status="succeeded",
            worker_id="frame-worker-29o",
            output_url=json.dumps(
                {
                    "frame_job_id": "fv-terminal-cas-race",
                    "local_worker_job_id": "29011",
                    "delivery_message_id": "29012",
                    "delivery_file_id": "frame-file-overwrite",
                },
                sort_keys=True,
            ),
            output_file_id="frame-file-overwrite",
        )


def test_29o_frame_resource_guard_has_no_arbitrary_duration_or_size_cap() -> None:
    runtime = SimpleNamespace(
        FRAME_VIDEO_MIN_IMAGES=2,
        validate_plan=lambda _state, **_kwargs: {
            "ok": True,
            "manifest": [{}, {}],
        },
    )
    public_seam = SimpleNamespace(
        frame_video_public_seam_enabled=lambda: True,
        frame_video_public_minimum_images=lambda: 1,
        frame_video_media_lane=seam.frame_video_media_lane,
        frame_video_public_seam_blocker=lambda: "",
        frame_video_worker_queue_admission=lambda *_args, **_kwargs: {
            "ok": True,
            "blocker": "",
        },
    )
    guard = _compile_bot_function(
        "frame_video_runtime_guard",
        {
            "FRAME_VIDEO_ENABLED": True,
            "FRAME_VIDEO_PUBLIC_ENABLED": True,
            "FRAME_VIDEO_MAX_IMAGES": 20,
            "FRAME_VIDEO_MAX_INPUT_MB": 0,
            "FRAME_VIDEO_PROCESSING_MAX_INPUT_MB": 1000,
            "FRAME_VIDEO_MAX_OUTPUT_SECONDS": 0,
            "FRAME_VIDEO_MAX_CONCURRENT_JOBS": 1,
            "frame_video_runtime": runtime,
            "frame_video_public_seam": public_seam,
            "frame_video_total_input_mb": lambda _state: 620.0,
            "frame_video_estimated_output_seconds": lambda _state: 900.0,
            "frame_video_worker_connected": lambda: True,
            "frame_video_active_jobs_count": lambda: 0,
            "frame_video_commercial_preflight": lambda *_args: {
                "ok": True,
                "execution_owner": "local_ffmpeg",
                "ffmpeg_path": "ffmpeg",
                "ffprobe_path": "ffprobe",
            },
            "frame_video_maintenance_text": lambda: "maintenance",
            "local_worker_status_payload": lambda: {},
            "is_railway_runtime": lambda: False,
            "APP_BUILD_SHA": "a" * 40,
            "APP_BUILD": "a" * 40,
            "os": os,
            "is_admin_user": lambda _user_id: False,
            "_safe_int": lambda value, fallback=0: int(value or fallback),
        },
    )

    result = guard(
        {
            "photos": [
                {"file_size": 310 * 1024 * 1024},
                {"file_size": 310 * 1024 * 1024},
            ]
        },
        user_id=29001,
    )

    assert result["ok"] is True
    assert result["action"] == "worker_queue"
    assert result["reason"] == "large_media_worker_ready"
    assert result["media_lane"]["lane"] == "large_media"


def test_29o_frame_stage_timeout_scales_with_duration_and_stays_bounded() -> None:
    timeout_for = getattr(seam, "frame_video_stage_timeout_seconds", None)
    assert callable(timeout_for)

    short = timeout_for(30, ceiling_seconds=7200)
    long = timeout_for(900, ceiling_seconds=7200)
    bounded = timeout_for(10000, ceiling_seconds=7200)
    misconfigured = timeout_for(10000, ceiling_seconds=99999)
    large_input = timeout_for(
        30,
        input_bytes=500 * 1024 * 1024,
        large_media=True,
        ceiling_seconds=7200,
    )
    unknown_large = timeout_for(
        30,
        input_bytes=0,
        large_media=True,
        ceiling_seconds=7200,
    )

    assert 180 <= short < long
    assert long > 180
    assert large_input > short
    assert unknown_large >= 1800
    assert bounded == 7200
    assert misconfigured == 7200
    assert "timeout_seconds" in inspect.signature(
        seam.frame_video_engine.execute_frame_video_local
    ).parameters
    bot_timeout_source = _function_source(
        REPO_ROOT / "bot.py",
        "frame_video_stage_timeout_for_state",
    )
    worker_source = _function_source(
        REPO_ROOT / "local_worker.py",
        "run_frame_video_render",
    )
    assert "frame_video_declared_input_bytes" in bot_timeout_source
    assert "large_media=" in bot_timeout_source
    assert "input_bytes=downloaded_input_bytes" in worker_source


def test_29o_bot_stage_timeout_uses_declared_bytes_and_large_lane() -> None:
    observed: dict[str, object] = {}
    state = {
        "photos": [
            {
                "file_id": "frame-timeout",
                "file_unique_id": "frame-timeout-unique",
                "file_size": 500 * 1024 * 1024,
            }
        ],
        "seconds_per_image": 30.0,
    }

    def timeout_for(
        duration,
        *,
        input_bytes,
        large_media,
        ceiling_seconds,
    ) -> int:
        observed.update(
            {
                "duration": duration,
                "input_bytes": input_bytes,
                "large_media": large_media,
                "ceiling_seconds": ceiling_seconds,
            }
        )
        return 2902

    timeout = _compile_bot_function(
        "frame_video_stage_timeout_for_state",
        {
            "frame_video_public_seam": SimpleNamespace(
                frame_video_stage_timeout_seconds=timeout_for,
                frame_video_media_lane=lambda _state: {"lane": "large_media"},
            ),
            "frame_video_estimated_output_seconds": lambda _state: 30.0,
            "frame_video_declared_input_bytes": lambda _state: 500
            * 1024
            * 1024,
            "FRAME_VIDEO_STAGE_TIMEOUT_MAX_SECONDS": 7200,
        },
    )

    assert timeout(state) == 2902
    assert observed == {
        "duration": 30.0,
        "input_bytes": 500 * 1024 * 1024,
        "large_media": True,
        "ceiling_seconds": 7200,
    }


def test_29o_worker_stage_timeout_uses_downloaded_bytes_and_route_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeout_calls: list[dict] = []
    render_timeouts: list[int] = []
    updates: list[dict] = []

    def download(_file_id: str, destination: str, **_kwargs) -> None:
        Path(destination).write_bytes(b"downloaded-frame-bytes")

    def timeout_for(
        duration,
        *,
        input_bytes,
        large_media,
        ceiling_seconds,
    ) -> int:
        timeout_calls.append(
            {
                "duration": duration,
                "input_bytes": input_bytes,
                "large_media": large_media,
                "ceiling_seconds": ceiling_seconds,
            }
        )
        return 2903

    def render(**kwargs) -> dict:
        render_timeouts.append(int(kwargs["timeout_seconds"]))
        artifact = b"frame-video"
        Path(kwargs["output_path"]).write_bytes(artifact)
        return {
            "enabled": True,
            "ok": True,
            "output_sha256": "c" * 64,
            "probe": {
                "ok": True,
                "full_decode": True,
                "duration_seconds": 30.0,
                "size_bytes": len(artifact),
                "video_stream_count": 1,
                "video_codec": "h264",
                "width": 640,
                "height": 480,
                "artifact_sha256": "c" * 64,
            },
        }

    def update(job_id, status, error_short="", **kwargs) -> None:
        updates.append(
            {
                "job_id": job_id,
                "status": status,
                "error_short": error_short,
                **kwargs,
            }
        )

    monkeypatch.setattr(local_worker, "telegram_download_file", download)
    monkeypatch.setattr(local_worker, "update_job", update)
    monkeypatch.setattr(local_worker, "env_int", lambda _name, default: default)
    monkeypatch.setattr(local_worker, "local_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(local_worker, "find_ffprobe", lambda **_kwargs: "ffprobe")
    monkeypatch.setattr(local_worker, "local_worker_runtime_sha", lambda: "a" * 40)
    monkeypatch.setattr(
        local_worker.frame_video_public_seam,
        "frame_video_stage_timeout_seconds",
        timeout_for,
    )
    monkeypatch.setattr(
        local_worker.frame_video_public_seam,
        "render_frame_video_public",
        render,
    )
    monkeypatch.setattr(
        local_worker.frame_video_public_seam,
        "frame_video_telegram_output_limit_bytes",
        lambda: 500 * 1024 * 1024,
    )
    monkeypatch.setattr(
        local_worker,
        "telegram_send_video_receipt",
        lambda *_args, **_kwargs: {
            "sent": True,
            "message_id": "29028",
            "file_id": "frame-file-29028",
        },
    )
    payload = {
        "chat_id": "29028",
        "user_id": 29028,
        "photos": [
            {
                "file_id": "frame-29028",
                "file_unique_id": "frame-29028-unique",
                "file_size": 0,
            }
        ],
        "state": {
            "photos": [
                {
                    "file_id": "frame-29028",
                    "file_unique_id": "frame-29028-unique",
                    "file_size": 0,
                }
            ],
            "seconds_per_image": 30.0,
            "transition": "none",
        },
        "media_lane": "large_media",
        "frame_video_durable_public_seam": True,
        "frame_video_runtime_sha": "a" * 40,
        "frame_video_expected_worker_sha": "a" * 40,
        "frame_job_id": "fv-timeout-29028",
        "max_render_seconds": 7200,
    }

    local_worker.run_frame_video_render(
        {"id": 29028, "input_file_id": json.dumps(payload)}
    )

    assert timeout_calls == [
        {
            "duration": 30.0,
            "input_bytes": len(b"downloaded-frame-bytes"),
            "large_media": True,
            "ceiling_seconds": 7200,
        }
    ]
    assert render_timeouts == [2903]
    assert updates[-1]["status"] == "succeeded"


@pytest.mark.parametrize(
    ("lease_expires_at", "expected_failed"),
    (
        ("2026-08-02 12:59:59", 1),
        ("2026-08-02 13:05:00", 0),
    ),
)
def test_29o_frame_watchdog_obeys_each_job_lease(
    lease_expires_at: str,
    expected_failed: int,
) -> None:
    updates: list[dict] = []

    class Cursor:
        def fetchall(self):
            return [
                (
                    "fv-adaptive-lease-29o",
                    "railway_ffmpeg",
                    0,
                    "rendering",
                    "2026-08-02 12:00:00",
                    lease_expires_at,
                )
            ]

    class Connection:
        def execute(self, sql, *_args):
            assert "lease_expires_at" in str(sql)
            return Cursor()

        def close(self) -> None:
            return None

    reconcile = _compile_bot_function(
        "reconcile_frame_video_jobs_once",
        {
            "datetime": datetime,
            "db_connect": lambda: Connection(),
            "FRAME_VIDEO_MAX_RENDER_SECONDS": 7200,
            "parse_now_text": lambda value: datetime.strptime(
                value,
                "%Y-%m-%d %H:%M:%S",
            ),
            "sanitize_log_text": lambda value: str(value),
            "get_local_worker_job": lambda _job_id: {},
            "handle_frame_video_worker_job_update": lambda *_args: None,
            "update_frame_video_job": lambda _job_id, **fields: updates.append(fields),
            "now_text": lambda: "2026-08-02 13:00:00",
        },
    )

    result = reconcile(datetime(2026, 8, 2, 13, 0, 0))

    assert result["failed"] == expected_failed
    if expected_failed:
        assert updates[-1]["status"] == "failed_no_charge"
        assert updates[-1]["error_code"] == "frame_video_watchdog_timeout"
    else:
        assert updates == []


def test_29o_frame_processing_capacity_uses_actual_asset_bytes(tmp_path: Path) -> None:
    first = tmp_path / "first-frame.bin"
    second = tmp_path / "second-frame.bin"
    first.write_bytes(b"a" * (700 * 1024))
    second.write_bytes(b"b" * (700 * 1024))

    assert seam.frame_video_input_capacity_blocker(
        [str(first)],
        {"FRAME_VIDEO_PROCESSING_MAX_INPUT_MB": "1"},
    ) == ""
    assert seam.frame_video_input_capacity_blocker(
        [str(first), str(second)],
        {"FRAME_VIDEO_PROCESSING_MAX_INPUT_MB": "1"},
    ) == "frame_video_processing_capacity_exceeded"

    worker_source = _function_source(REPO_ROOT / "local_worker.py", "run_frame_video_render")
    assert "downloaded_input_bytes" in worker_source
    assert "frame_video_processing_capacity_exceeded" in worker_source


def test_29o_worker_downloads_only_within_remaining_processing_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    download_limits: list[int] = []
    updates: list[dict] = []
    render_calls: list[str] = []

    def download(_file_id: str, destination: str, *, max_bytes: int) -> None:
        download_limits.append(int(max_bytes))
        Path(destination).write_bytes(b"x" * 6)

    def update(job_id, status, error_short="", **kwargs) -> None:
        updates.append(
            {
                "job_id": job_id,
                "status": status,
                "error_short": error_short,
                **kwargs,
            }
        )

    monkeypatch.setattr(local_worker, "telegram_download_file", download)
    monkeypatch.setattr(local_worker, "update_job", update)
    monkeypatch.setattr(
        local_worker,
        "frame_video_telegram_input_limit_bytes",
        lambda: 100,
    )
    monkeypatch.setattr(
        local_worker.frame_video_public_seam,
        "frame_video_processing_input_limit_bytes",
        lambda: 10,
    )
    monkeypatch.setattr(
        local_worker.frame_video_public_seam,
        "render_frame_video_public",
        lambda **_kwargs: render_calls.append("rendered") or {"ok": True},
    )

    payload = {
        "chat_id": "29029",
        "user_id": 29029,
        "photos": [
            {
                "file_id": f"frame-29029-{index}",
                "file_unique_id": f"frame-29029-{index}-unique",
                "file_size": 0,
            }
            for index in (1, 2)
        ],
        "state": {
            "photos": [
                {
                    "file_id": f"frame-29029-{index}",
                    "file_unique_id": f"frame-29029-{index}-unique",
                    "file_size": 0,
                }
                for index in (1, 2)
            ],
            "seconds_per_image": 3.0,
            "transition": "none",
        },
        "media_lane": "large_media",
        "frame_video_durable_public_seam": True,
        "frame_video_runtime_sha": "a" * 40,
        "frame_video_expected_worker_sha": "a" * 40,
        "frame_job_id": "fv-capacity-29029",
        "max_render_seconds": 1800,
    }

    local_worker.run_frame_video_render(
        {"id": 29029, "input_file_id": json.dumps(payload)}
    )

    assert download_limits == [10, 4]
    assert render_calls == []
    assert updates[-1]["status"] == "failed"
    assert "frame_video_processing_capacity_exceeded" in str(
        updates[-1]["error_short"]
    )


def test_29o_declared_capacity_counts_optional_assets_before_dispatch() -> None:
    declared_input_bytes = _compile_bot_function(
        "frame_video_declared_input_bytes",
        {"frame_video_public_seam": seam},
    )
    state = {
        "photos": [
            {
                "file_id": "frame-capacity-photo",
                "file_unique_id": "frame-capacity-photo-unique",
                "file_size": 1,
            }
        ],
        "seconds_per_image": 3.0,
        "logo_file_id": "frame-capacity-logo",
        "logo_file_size": 400 * 1024 * 1024,
        "music_file_id": "frame-capacity-music",
        "music_file_size": 300 * 1024 * 1024,
        "voice_file_id": "frame-capacity-voice",
        "voice_file_size": 300 * 1024 * 1024,
    }

    assert declared_input_bytes(state) == 1000 * 1024 * 1024 + 1


def test_29o_declared_capacity_guard_is_exact_at_limit_plus_one() -> None:
    declared_input_bytes = _compile_bot_function(
        "frame_video_declared_input_bytes",
        {"frame_video_public_seam": seam},
    )
    limit = 1000 * 1024 * 1024
    at_limit = {
        "photos": [
            {
                "file_id": "frame-capacity-photo",
                "file_unique_id": "frame-capacity-photo-unique",
                "file_size": 1,
            }
        ],
        "seconds_per_image": 3.0,
        "logo_file_id": "frame-capacity-logo",
        "logo_file_size": 400 * 1024 * 1024,
        "music_file_id": "frame-capacity-music",
        "music_file_size": 300 * 1024 * 1024,
        "voice_file_id": "frame-capacity-voice",
        "voice_file_size": 300 * 1024 * 1024 - 1,
    }
    public_seam = SimpleNamespace(
        frame_video_public_seam_enabled=lambda: True,
        frame_video_public_minimum_images=lambda: 1,
        frame_video_media_lane=seam.frame_video_media_lane,
        frame_video_public_seam_blocker=lambda: "",
        frame_video_worker_queue_admission=lambda *_args, **_kwargs: {
            "ok": True,
            "blocker": "",
        },
    )
    guard = _compile_bot_function(
        "frame_video_runtime_guard",
        {
            "FRAME_VIDEO_ENABLED": True,
            "FRAME_VIDEO_PUBLIC_ENABLED": True,
            "FRAME_VIDEO_MAX_IMAGES": 20,
            "FRAME_VIDEO_MAX_INPUT_MB": 0,
            "FRAME_VIDEO_PROCESSING_MAX_INPUT_MB": 1000,
            "FRAME_VIDEO_MAX_OUTPUT_SECONDS": 0,
            "FRAME_VIDEO_MAX_CONCURRENT_JOBS": 1,
            "frame_video_runtime": SimpleNamespace(
                FRAME_VIDEO_MIN_IMAGES=2,
                validate_plan=lambda _state, **_kwargs: {
                    "ok": True,
                    "manifest": [{}],
                },
            ),
            "frame_video_public_seam": public_seam,
            "frame_video_declared_input_bytes": declared_input_bytes,
            # Deliberately preserve the legacy rounded view for both states.
            # Only an exact declared-byte check can distinguish limit+1.
            "frame_video_total_input_mb": lambda _value: 1000.0,
            "frame_video_estimated_output_seconds": lambda _state: 3.0,
            "frame_video_worker_connected": lambda: True,
            "frame_video_active_jobs_count": lambda: 0,
            "frame_video_commercial_preflight": lambda *_args: {
                "ok": True,
                "execution_owner": "local_ffmpeg",
                "ffmpeg_path": "ffmpeg",
                "ffprobe_path": "ffprobe",
            },
            "frame_video_maintenance_text": lambda: "maintenance",
            "local_worker_status_payload": lambda: {},
            "is_railway_runtime": lambda: False,
            "APP_BUILD_SHA": "a" * 40,
            "APP_BUILD": "a" * 40,
            "os": os,
            "is_admin_user": lambda _user_id: False,
            "_safe_int": lambda value, fallback=0: int(value or fallback),
        },
    )

    assert declared_input_bytes(at_limit) == limit
    assert guard(at_limit, user_id=29002)["ok"] is True
    over_limit = {
        **at_limit,
        "voice_file_size": int(at_limit["voice_file_size"]) + 1,
    }
    blocked = guard(over_limit, user_id=29002)
    assert declared_input_bytes(over_limit) == limit + 1
    assert blocked["ok"] is False
    assert blocked["reason"] == "input_resource_capacity_exceeded"


@pytest.mark.parametrize(
    ("target", "media_kind", "size_key"),
    (
        ("logo_upload", "image", "logo_file_size"),
        ("music_upload", "audio", "music_file_size"),
        ("voice_upload", "audio", "voice_file_size"),
    ),
)
def test_29o_frame_media_intake_persists_optional_asset_sizes(
    target: str,
    media_kind: str,
    size_key: str,
) -> None:
    stored: list[dict] = []
    replies: list[str] = []
    file_size = 29021
    state = {
        "type": "frame_video",
        "pending_input": target,
        "step": "addons",
        "photos": [],
    }
    media = SimpleNamespace(
        file_id=f"{target}-file",
        file_unique_id=f"{target}-unique",
        file_size=file_size,
        mime_type="image/png" if media_kind == "image" else "audio/mpeg",
    )

    class Message:
        message_id = 29021

        async def reply_text(self, text, **_kwargs):
            replies.append(str(text))
            return SimpleNamespace(message_id=29022)

    handler = _compile_bot_function(
        "handle_frame_video_pending_media",
        {
            "normalize_frame_video_state": lambda value: dict(value or {}),
            "get_frame_video_state": lambda _uid: dict(state),
            "frame_video_flow": SimpleNamespace(
                mark_media_message_processed=lambda value, _message_id: (
                    dict(value),
                    True,
                ),
            ),
            "frame_video_message_media": lambda _update: (media_kind, media),
            "set_frame_video_state": lambda _uid, value: (
                stored.append(dict(value)) or dict(value)
            ),
            "is_frame_video3_state": lambda _state: False,
            "frame_video_position_keyboard": lambda *_args, **_kwargs: None,
            "frame_video_music_menu_text": lambda _state: "music",
            "frame_video_music_menu_keyboard": lambda *_args, **_kwargs: None,
            "frame_video_volume_keyboard": lambda *_args, **_kwargs: None,
        },
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=29021),
        message=Message(),
    )

    assert asyncio.run(handler(update, SimpleNamespace())) is True
    assert replies
    assert stored[-1][size_key] == file_size
    assert stored[-1][f"{target.removesuffix('_upload')}_file_id"] == media.file_id



def test_29o_frame_60_seconds_20_mib_are_routing_thresholds_only() -> None:
    boundary = {
        "photos": [
            {
                "file_id": f"frame-boundary-{index}",
                "file_unique_id": f"frame-boundary-unique-{index}",
                "file_size": 10 * 1024 * 1024,
            }
            for index in (1, 2)
        ],
        "seconds_per_image": 30.0,
        "transition": "none",
    }

    assert seam.frame_video_media_lane(boundary)["lane"] == "short_media"
    assert seam.frame_video_media_lane(
        {
            **boundary,
            "photos": [
                {
                    "file_id": f"frame-duration-{index}",
                    "file_unique_id": f"frame-duration-unique-{index}",
                    "file_size": 1024,
                }
                for index in (1, 2, 3)
            ],
            "seconds_per_image": 20.001,
        }
    )["lane"] == "large_media"
    assert seam.frame_video_media_lane(
        {
            **boundary,
            "photos": [
                {**boundary["photos"][0], "file_size": 10 * 1024 * 1024},
                {**boundary["photos"][1], "file_size": 10 * 1024 * 1024 + 1},
            ],
        }
    )["lane"] == "large_media"
    unknown = seam.frame_video_media_lane(
        {
            **boundary,
            "photos": [
                {**boundary["photos"][0], "file_size": 0},
                boundary["photos"][1],
            ],
        }
    )
    assert unknown["lane"] == "large_media"
    assert unknown["reason"] == "metadata_unknown"


def test_29o_public_frame_seam_accepts_one_frame_single_scene(tmp_path: Path) -> None:
    frame_path = tmp_path / "single-frame.png"
    frame_path.write_bytes(b"single-frame-content")
    state = {
        "photos": [
            {
                "file_id": "single-frame",
                "file_unique_id": "single-frame-unique",
                "file_size": frame_path.stat().st_size,
            }
        ],
        "seconds_per_image": 3.0,
        "transition": "none",
        "ratio": "9x16",
    }

    plan = seam.build_frame_video_public_plan(state, [str(frame_path)])

    assert plan.mode == "single_scene"
    assert len(plan.frames) == 1
    assert plan.frames[0].source_sha256

    bot_guard_source = _function_source(REPO_ROOT / "bot.py", "frame_video_runtime_guard")
    final_confirm_source = _function_source(
        REPO_ROOT / "bot.py",
        "handle_frame_video_final_confirm",
    )
    worker_payload_source = _function_source(
        REPO_ROOT / "bot.py",
        "frame_video_worker_payload",
    )
    worker_source = _function_source(REPO_ROOT / "local_worker.py", "run_frame_video_render")
    assert "frame_video_public_minimum_images" in bot_guard_source
    assert "frame_video_public_minimum_images" in final_confirm_source
    assert "frame_video_public_minimum_images" in worker_payload_source
    assert "min_images=minimum_images" in worker_payload_source
    assert "frame_video_public_minimum_images" in worker_source


def test_29o_public_frame_commercial_preflight_accepts_one_frame() -> None:
    result = frame_video_commercial.preflight(
        {
            "photos": [
                {
                    "file_id": "single-frame",
                    "file_unique_id": "single-frame-unique",
                }
            ],
            "seconds_per_image": 3.0,
            "transition": "none",
        },
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        worker_connected=False,
        output_writable=True,
        package_available=True,
        min_images=1,
    )

    assert result["ok"] is True
    assert result["asset_manifest_count"] == 1


def test_29o_single_frame_motion_changes_real_output_frames(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg/ffprobe are required")

    width = height = 96
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            pixels.extend(
                (
                    (x * 5 + y * 2) % 256,
                    (y * 7 + (255 if x > width // 2 else 0)) % 256,
                    ((x // 8 + y // 8) % 2) * 255,
                )
            )
    frame_path = tmp_path / "single-motion.ppm"
    frame_path.write_bytes(
        f"P6\n{width} {height}\n255\n".encode("ascii") + bytes(pixels)
    )
    runtime_sha = "a" * 40
    environ = {
        "FRAME_VIDEO_DURABLE_PUBLIC_SEAM_ENABLED": "1",
        "FRAME_VIDEO_ENGINE_ENABLED": "1",
        "FRAME_VIDEO_PUBLIC_ALLOWED": "1",
        "FRAME_VIDEO_AUTO_RETRY": "0",
        "FRAME_VIDEO_AUTO_FALLBACK": "0",
    }
    def render(motion: str, name: str) -> Path:
        output_path = tmp_path / name
        result = seam.render_frame_video_public(
            state={
                "photos": [
                    {
                        "file_id": "single-motion",
                        "file_unique_id": "single-motion-unique",
                        "file_size": frame_path.stat().st_size,
                    }
                ],
                "seconds_per_image": 2.0,
                "transition": "none",
                "motion": motion,
                "ratio": "custom",
                "custom_width": 160,
                "custom_height": 160,
                "quality": "fast",
            },
            image_paths=[str(frame_path)],
            output_path=str(output_path),
            user_id=29019,
            confirmation_id=f"frame-motion-{motion}-29o",
            language="vi",
            runtime_sha=runtime_sha,
            expected_worker_sha=runtime_sha,
            worker_sha=runtime_sha,
            ffmpeg_path=ffmpeg,
            ffprobe_path=ffprobe,
            timeout_seconds=180,
            environ=environ,
        )
        assert result["ok"] is True, json.dumps(
            result,
            ensure_ascii=True,
            default=str,
        )
        assert result["provider_calls"] == 0
        return output_path

    static_output = render("none", "single-static.mp4")
    motion_output = render("ken_burns", "single-motion.mp4")

    def decoded_frame(path: Path, timestamp: float) -> bytes:
        sampled = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-",
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
        assert sampled.returncode == 0, sampled.stderr[-1000:]
        assert len(sampled.stdout) == 160 * 160 * 3
        return sampled.stdout

    def mean_pixel_delta(first: bytes, second: bytes) -> float:
        assert len(first) == len(second)
        return sum(abs(left - right) for left, right in zip(first, second)) / len(
            first
        )

    static_delta = mean_pixel_delta(
        decoded_frame(static_output, 0.25),
        decoded_frame(static_output, 1.5),
    )
    motion_delta = mean_pixel_delta(
        decoded_frame(motion_output, 0.25),
        decoded_frame(motion_output, 1.5),
    )
    assert motion_delta >= max(2.0, static_delta * 2.0 + 0.5)


def test_29o_frame_transport_uses_configured_local_bot_api() -> None:
    environ = {
        "TELEGRAM_API_BASE_URL": "https://tg.toanaas.vn",
        "TELEGRAM_API_PROXY_SECRET": "proxy-secret",
        "TELEGRAM_API_PROXY_SECRET_HEADER": "X-Toanaas-Proxy-Secret",
        "TELEGRAM_LOCAL_API_FILE_ROOT": "/var/lib/telegram-bot-api",
        "TELEGRAM_LOCAL_API_MEDIA_PATH": "localfile",
        "FRAME_VIDEO_TELEGRAM_MAX_INPUT_MB": "500",
    }

    assert seam.frame_video_telegram_api_root(environ) == "https://tg.toanaas.vn"
    assert seam.frame_video_telegram_api_method_url(
        "getFile",
        token="test-token",
        environ=environ,
    ) == "https://tg.toanaas.vn/bottest-token/getFile"
    assert seam.frame_video_telegram_api_proxy_headers(environ) == {
        "X-Toanaas-Proxy-Secret": "proxy-secret"
    }
    with pytest.raises(ValueError, match="telegram_proxy_secret_missing"):
        seam.frame_video_telegram_api_proxy_headers(
            {"TELEGRAM_API_BASE_URL": "https://tg.toanaas.vn"}
        )
    assert seam.frame_video_telegram_api_proxy_headers(
        {"TELEGRAM_API_BASE_URL": "http://127.0.0.1:8081"}
    ) == {}
    assert seam.frame_video_telegram_file_download_url(
        "/var/lib/telegram-bot-api/test-token/photos/frame.jpg",
        token="test-token",
        environ=environ,
    ) == "https://tg.toanaas.vn/localfile/test-token/photos/frame.jpg"
    assert seam.frame_video_telegram_input_limit_bytes(environ) == 500 * 1024 * 1024

    cloud = {}
    assert seam.frame_video_telegram_api_root(cloud) == "https://api.telegram.org"
    assert seam.frame_video_telegram_api_proxy_headers(cloud) == {}
    assert seam.frame_video_telegram_input_limit_bytes(cloud) == 20 * 1024 * 1024

    worker_source = (REPO_ROOT / "local_worker.py").read_text(encoding="utf-8")
    telegram_json_source = _function_source(REPO_ROOT / "local_worker.py", "telegram_json")
    method_url_source = _function_source(
        REPO_ROOT / "local_worker.py",
        "telegram_api_method_url",
    )
    download_source = _function_source(REPO_ROOT / "local_worker.py", "telegram_download_file")
    send_source = _function_source(REPO_ROOT / "local_worker.py", "telegram_send_video_receipt")
    assert "frame_video_telegram_api_method_url" in method_url_source
    assert "telegram_api_method_url" in telegram_json_source
    assert "telegram_file_download_url" in download_source
    assert "telegram_api_method_url" in send_source
    assert "asset_limit = min(frame_input_limit, remaining_bytes)" in worker_source
    assert "max_bytes=asset_limit" in worker_source
    assert "prefer_document=" in worker_source


def test_29o_local_media_path_fails_closed_outside_current_bot_root() -> None:
    environ = {
        "TELEGRAM_API_BASE_URL": "https://tg.toanaas.vn",
        "TELEGRAM_API_PROXY_SECRET": "proxy-secret",
        "TELEGRAM_LOCAL_API_FILE_ROOT": "/var/lib/telegram-bot-api",
        "TELEGRAM_LOCAL_API_MEDIA_PATH": "localfile",
    }

    for file_path in (
        "photos/frame.jpg",
        "/srv/telegram-bot-api/test-token/photos/frame.jpg",
        "/tmp/var/lib/telegram-bot-api/test-token/photos/frame.jpg",
        "/var/lib/telegram-bot-api/other-token/photos/frame.jpg",
        "/var/lib/telegram-bot-api/test-token-other/photos/frame.jpg",
        "/var/lib/telegram-bot-api/test-token/../other-token/photos/frame.jpg",
        "/var/lib/telegram-bot-api/test-token\\photos\\frame.jpg",
    ):
        with pytest.raises(ValueError, match="telegram_file_path_invalid"):
            seam.frame_video_telegram_file_download_url(
                file_path,
                token="test-token",
                environ=environ,
            )


@pytest.mark.parametrize(
    "secret",
    (
        "secret\r\nX-Injected: yes",
        "secret\rX-Injected: yes",
        "secret\nX-Injected: yes",
        "prefix\r\nX-Injected: yes\r\nsuffix",
        "\rsecret",
        "\nsecret",
        "secret\r",
        "secret\n",
    ),
)
def test_29o_local_proxy_secret_rejects_header_injection(secret: str) -> None:
    with pytest.raises(ValueError, match="telegram_proxy_secret_invalid"):
        seam.frame_video_telegram_api_proxy_headers(
            {
                "TELEGRAM_API_BASE_URL": "https://tg.toanaas.vn",
                "TELEGRAM_API_PROXY_SECRET": secret,
            }
        )


def test_29o_worker_credential_transport_rejects_redirects() -> None:
    open_no_redirect = _compile_worker_function(
        "telegram_open_no_redirect",
        {"urllib": SimpleNamespace(request=urllib.request, error=urllib.error)},
    )
    target_requests: list[str] = []

    class TargetHandler(http.server.BaseHTTPRequestHandler):
        def _capture(self) -> None:
            target_requests.append(self.path)
            self.send_response(200)
            self.end_headers()

        do_GET = _capture
        do_POST = _capture

        def log_message(self, _format: str, *_args) -> None:
            return None

    target = http.server.ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)
    target_port = int(target.server_address[1])

    class RedirectHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_response(302)
            self.send_header(
                "Location",
                f"http://127.0.0.1:{target_port}/credential-capture",
            )
            self.end_headers()

        def log_message(self, _format: str, *_args) -> None:
            return None

    redirect = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    threads = [
        threading.Thread(target=server.serve_forever, daemon=True)
        for server in (target, redirect)
    ]
    for thread in threads:
        thread.start()
    try:
        request = urllib.request.Request(
            (
                f"http://127.0.0.1:{int(redirect.server_address[1])}/"
                "botTEST-TOKEN/getFile"
            ),
            data=b"{}",
            headers={"X-Toanaas-Proxy-Secret": "proxy-secret"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            open_no_redirect(request, timeout=2)
        assert exc_info.value.code == 302
        assert target_requests == []
    finally:
        for server in (redirect, target):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)


def test_29o_worker_credential_callers_use_no_redirect_transport() -> None:
    for function_name in (
        "telegram_json",
        "telegram_download_file",
        "telegram_send_video_receipt",
    ):
        source = _function_source(REPO_ROOT / "local_worker.py", function_name)
        assert "telegram_open_no_redirect" in source
        assert "urllib.request.urlopen" not in source


def test_29o_worker_credential_callers_invoke_no_redirect_transport(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, int]] = []

    class Response:
        def __init__(self, body: bytes) -> None:
            self.body = body
            self.offset = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            if self.offset >= len(self.body):
                return b""
            if size is None or size < 0:
                chunk = self.body[self.offset :]
                self.offset = len(self.body)
                return chunk
            chunk = self.body[self.offset : self.offset + size]
            self.offset += len(chunk)
            return chunk

    def open_no_redirect(request, timeout):
        url = str(request.full_url)
        calls.append((url, int(timeout)))
        if url.endswith("/getFile"):
            return Response(
                json.dumps(
                    {
                        "ok": True,
                        "result": {
                            "file_path": (
                                "/var/lib/telegram-bot-api/test-token/"
                                "photos/frame.jpg"
                            )
                        },
                    }
                ).encode("utf-8")
            )
        if "/localfile/" in url:
            return Response(b"frame-download")
        if url.endswith("/sendVideo"):
            return Response(
                json.dumps(
                    {
                        "ok": True,
                        "result": {
                            "message_id": 29020,
                            "video": {"file_id": "frame-file-29020"},
                        },
                    }
                ).encode("utf-8")
            )
        raise AssertionError(f"unexpected Telegram URL: {url}")

    forbidden_urlopen = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("credential caller bypassed no-redirect transport")
    )
    fake_urllib = SimpleNamespace(
        request=SimpleNamespace(
            Request=urllib.request.Request,
            urlopen=forbidden_urlopen,
        ),
        error=urllib.error,
    )
    telegram_json = _compile_worker_function(
        "telegram_json",
        {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "json": json,
            "socket": socket,
            "urllib": fake_urllib,
            "telegram_api_proxy_headers": lambda: {},
            "telegram_api_method_url": lambda method: (
                f"https://tg.toanaas.vn/bottest-token/{method}"
            ),
            "telegram_open_no_redirect": open_no_redirect,
        },
    )
    assert telegram_json("getFile", {"file_id": "frame"})["ok"] is True

    destination = tmp_path / "downloaded-frame.jpg"
    telegram_download_file = _compile_worker_function(
        "telegram_download_file",
        {
            "telegram_json": lambda *_args, **_kwargs: {
                "ok": True,
                "result": {
                    "file_path": (
                        "/var/lib/telegram-bot-api/test-token/photos/frame.jpg"
                    )
                },
            },
            "telegram_file_download_url": lambda _path: (
                "https://tg.toanaas.vn/localfile/test-token/photos/frame.jpg"
            ),
            "telegram_api_proxy_headers": lambda: {},
            "frame_video_telegram_input_limit_bytes": lambda: 20 * 1024 * 1024,
            "telegram_open_no_redirect": open_no_redirect,
            "env_int": lambda _name, default: default,
            "os": os,
            "socket": socket,
            "urllib": fake_urllib,
        },
    )
    telegram_download_file("frame", str(destination))
    assert destination.read_bytes() == b"frame-download"

    output = tmp_path / "frame-output.mp4"
    output.write_bytes(b"frame-video")
    telegram_send_video_receipt = _compile_worker_function(
        "telegram_send_video_receipt",
        {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "os": os,
            "json": json,
            "socket": socket,
            "urllib": fake_urllib,
            "safe_display_filename": lambda value, _fallback: str(value),
            "telegram_api_proxy_headers": lambda: {},
            "telegram_api_method_url": lambda method: (
                f"https://tg.toanaas.vn/bottest-token/{method}"
            ),
            "telegram_open_no_redirect": open_no_redirect,
            "env_int": lambda _name, default: default,
        },
    )
    receipt = telegram_send_video_receipt("29020", str(output), "frame")
    assert receipt == {
        "sent": True,
        "file_id": "frame-file-29020",
        "message_id": "29020",
        "delivery_method": "sendVideo",
    }
    assert [url.rsplit("/", 1)[-1] for url, _timeout in calls] == [
        "getFile",
        "frame.jpg",
        "sendVideo",
    ]


def test_29o_large_frame_delivery_streams_mp4_instead_of_buffering_it() -> None:
    send_source = _function_source(
        REPO_ROOT / "local_worker.py",
        "telegram_send_video_receipt",
    )

    assert "video_bytes = handle.read()" not in send_source
    assert "Content-Length" in send_source
    assert "multipart_body_chunks" in send_source


def test_29o_large_frame_delivery_streams_bounded_chunks(tmp_path: Path) -> None:
    video_path = tmp_path / "large-frame.mp4"
    video_bytes = b"frame-video" * (300 * 1024)
    video_path.write_bytes(video_bytes)
    observed: dict[str, object] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ok": True,
                    "result": {
                        "message_id": 29015,
                        "video": {"file_id": "frame-large-file"},
                    },
                }
            ).encode("utf-8")

    def urlopen(request, timeout):
        chunks = list(request.data)
        observed["timeout"] = timeout
        observed["chunks"] = chunks
        observed["headers"] = dict(request.header_items())
        observed["body"] = b"".join(chunks)
        return Response()

    fake_urllib = SimpleNamespace(
        request=SimpleNamespace(Request=urllib.request.Request, urlopen=urlopen),
        error=urllib.error,
    )
    sender = _compile_worker_function(
        "telegram_send_video_receipt",
        {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "os": os,
            "json": json,
            "socket": socket,
            "urllib": fake_urllib,
            "safe_display_filename": lambda value, _fallback: str(value),
            "frame_video_public_seam": SimpleNamespace(
                frame_video_telegram_output_limit_bytes=lambda: 500 * 1024 * 1024,
            ),
            "telegram_api_proxy_headers": lambda: {
                "X-Toanaas-Proxy-Secret": "secret"
            },
            "telegram_api_method_url": lambda method: f"https://tg.toanaas.vn/bottest-token/{method}",
            "telegram_open_no_redirect": urlopen,
            "env_int": lambda _name, default: default,
        },
    )

    result = sender("29015", str(video_path), "frame")

    assert result["sent"] is True
    assert result["file_id"] == "frame-large-file"
    chunks = observed["chunks"]
    assert isinstance(chunks, list)
    assert max(len(chunk) for chunk in chunks) <= 1024 * 1024
    assert video_bytes in observed["body"]
    headers = {str(key).lower(): value for key, value in observed["headers"].items()}
    assert int(headers["content-length"]) == len(observed["body"])
    assert headers["x-toanaas-proxy-secret"] == "secret"


def test_29o_large_frame_delivery_selects_document_before_upload(tmp_path: Path) -> None:
    video_path = tmp_path / "large-frame-route.mp4"
    video_path.write_bytes(b"frame-video")
    calls: list[str] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "ok": True,
                    "result": {
                        "message_id": 29017,
                        "document": {"file_id": "frame-document-file"},
                    },
                }
            ).encode("utf-8")

    def urlopen(request, timeout):
        calls.append(str(request.full_url))
        return Response()

    fake_urllib = SimpleNamespace(
        request=SimpleNamespace(Request=urllib.request.Request, urlopen=urlopen),
        error=urllib.error,
    )
    sender = _compile_worker_function(
        "telegram_send_video_receipt",
        {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "os": os,
            "json": json,
            "socket": socket,
            "urllib": fake_urllib,
            "safe_display_filename": lambda value, _fallback: str(value),
            "telegram_api_proxy_headers": lambda: {},
            "telegram_api_method_url": lambda method: (
                f"https://tg.toanaas.vn/bottest-token/{method}"
            ),
            "telegram_open_no_redirect": urlopen,
            "env_int": lambda _name, default: default,
        },
    )

    result = sender(
        "29017",
        str(video_path),
        "frame",
        prefer_document=True,
    )

    assert result["sent"] is True
    assert result["delivery_method"] == "sendDocument"
    assert result["file_id"] == "frame-document-file"
    assert [url.rsplit("/", 1)[-1] for url in calls] == ["sendDocument"]


def test_29o_direct_and_worker_choose_large_delivery_before_upload() -> None:
    delivery_method = getattr(seam, "frame_video_telegram_delivery_method", None)
    assert callable(delivery_method)
    assert delivery_method(20 * 1024 * 1024) == "video"
    assert delivery_method(20 * 1024 * 1024 + 1) == "document"

    direct_source = _function_source(
        REPO_ROOT / "bot.py",
        "handle_frame_video_final_confirm",
    )
    worker_source = _function_source(
        REPO_ROOT / "local_worker.py",
        "run_frame_video_render",
    )
    assert "frame_video_telegram_delivery_method" in direct_source
    assert "send_document" in direct_source
    assert "frame_video_telegram_delivery_method" in worker_source


def test_29o_worker_selects_document_before_threshold_plus_one_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivery_calls: list[dict] = []
    updates: list[dict] = []
    output_size = 20 * 1024 * 1024 + 1

    def download(_file_id: str, destination: str, **_kwargs) -> None:
        Path(destination).write_bytes(b"frame")

    def render(**kwargs) -> dict:
        with open(kwargs["output_path"], "wb") as handle:
            handle.seek(output_size - 1)
            handle.write(b"x")
        return {
            "enabled": True,
            "ok": True,
            "output_sha256": "d" * 64,
            "probe": {
                "ok": True,
                "full_decode": True,
                "duration_seconds": 3.0,
                "size_bytes": output_size,
                "video_stream_count": 1,
                "video_codec": "h264",
                "width": 640,
                "height": 480,
                "artifact_sha256": "d" * 64,
            },
        }

    def send(*_args, **kwargs) -> dict:
        delivery_calls.append(dict(kwargs))
        return {
            "sent": True,
            "message_id": "29029",
            "file_id": "frame-file-29029",
        }

    def update(job_id, status, error_short="", **kwargs) -> None:
        updates.append(
            {
                "job_id": job_id,
                "status": status,
                "error_short": error_short,
                **kwargs,
            }
        )

    monkeypatch.setattr(local_worker, "telegram_download_file", download)
    monkeypatch.setattr(local_worker, "telegram_send_video_receipt", send)
    monkeypatch.setattr(local_worker, "update_job", update)
    monkeypatch.setattr(local_worker, "env_int", lambda _name, default: default)
    monkeypatch.setattr(local_worker, "local_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(local_worker, "find_ffprobe", lambda **_kwargs: "ffprobe")
    monkeypatch.setattr(local_worker, "local_worker_runtime_sha", lambda: "a" * 40)
    monkeypatch.setattr(
        local_worker.frame_video_public_seam,
        "render_frame_video_public",
        render,
    )
    monkeypatch.setattr(
        local_worker.frame_video_public_seam,
        "frame_video_telegram_output_limit_bytes",
        lambda: 500 * 1024 * 1024,
    )
    payload = {
        "chat_id": "29029",
        "user_id": 29029,
        "photos": [
            {
                "file_id": "frame-29029",
                "file_unique_id": "frame-29029-unique",
                "file_size": 5,
            }
        ],
        "state": {
            "photos": [
                {
                    "file_id": "frame-29029",
                    "file_unique_id": "frame-29029-unique",
                    "file_size": 5,
                }
            ],
            "seconds_per_image": 3.0,
            "transition": "none",
        },
        "media_lane": "large_media",
        "frame_video_durable_public_seam": True,
        "frame_video_runtime_sha": "a" * 40,
        "frame_video_expected_worker_sha": "a" * 40,
        "frame_job_id": "fv-document-29029",
        "max_render_seconds": 1800,
    }

    local_worker.run_frame_video_render(
        {"id": 29029, "input_file_id": json.dumps(payload)}
    )

    assert len(delivery_calls) == 1
    assert delivery_calls[0]["prefer_document"] is True
    assert delivery_calls[0]["max_bytes"] >= output_size
    assert updates[-1]["status"] == "succeeded"


@pytest.mark.parametrize(
    "response_body",
    (
        b"{not-json",
        b"[]",
        OSError("response stream reset"),
        json.dumps(
            {
                "ok": True,
                "result": {
                    "message_id": 29018,
                    "video": {},
                },
            }
        ).encode("utf-8"),
        json.dumps(
            {
                "ok": True,
                "result": {
                    "message_id": 0,
                    "video": {"file_id": "frame-file-without-message"},
                },
            }
        ).encode("utf-8"),
    ),
)
def test_29o_upload_without_parseable_complete_receipt_is_uncertain_no_retry(
    tmp_path: Path,
    response_body: bytes | Exception,
) -> None:
    video_path = tmp_path / "frame-ambiguous-receipt.mp4"
    video_path.write_bytes(b"frame-video")
    calls = 0

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self) -> bytes:
            if isinstance(response_body, Exception):
                raise response_body
            return response_body

    def urlopen(_request, timeout):
        nonlocal calls
        calls += 1
        return Response()

    fake_urllib = SimpleNamespace(
        request=SimpleNamespace(Request=urllib.request.Request, urlopen=urlopen),
        error=urllib.error,
    )
    sender = _compile_worker_function(
        "telegram_send_video_receipt",
        {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "os": os,
            "json": json,
            "socket": socket,
            "urllib": fake_urllib,
            "safe_display_filename": lambda value, _fallback: str(value),
            "telegram_api_proxy_headers": lambda: {},
            "telegram_api_method_url": lambda method: (
                f"https://tg.toanaas.vn/bottest-token/{method}"
            ),
            "telegram_open_no_redirect": urlopen,
            "env_int": lambda _name, default: default,
        },
    )

    with pytest.raises(
        RuntimeError,
        match="^telegram_delivery_outcome_uncertain$",
    ) as exc_info:
        sender("29018", str(video_path), "frame")

    assert calls == 1
    assert exc_info.value.__cause__ is None


def test_29o_worker_telegram_json_never_surfaces_token_url() -> None:
    source = _function_source(REPO_ROOT / "local_worker.py", "telegram_json")

    assert "telegram_api_http_" in source
    assert "telegram_api_network" in source
    assert "from None" in source

    def urlopen(_request, timeout):
        assert timeout == 30
        raise urllib.error.HTTPError(
            "https://tg.toanaas.vn/botREAL-TOKEN/getFile",
            403,
            "forbidden",
            None,
            None,
        )

    fake_urllib = SimpleNamespace(
        request=SimpleNamespace(Request=urllib.request.Request, urlopen=urlopen),
        error=urllib.error,
    )
    telegram_json = _compile_worker_function(
        "telegram_json",
        {
            "TELEGRAM_BOT_TOKEN": "REAL-TOKEN",
            "json": json,
            "urllib": fake_urllib,
            "telegram_api_proxy_headers": lambda: {},
            "telegram_api_method_url": lambda _method: (
                "https://tg.toanaas.vn/botREAL-TOKEN/getFile"
            ),
            "telegram_open_no_redirect": urlopen,
        },
    )

    with pytest.raises(RuntimeError, match="^telegram_api_http_403$") as exc_info:
        telegram_json("getFile", {"file_id": "frame"})

    assert "REAL-TOKEN" not in str(exc_info.value)


def test_29o_worker_telegram_json_rejects_non_object_payload() -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self) -> bytes:
            return b"[]"

    def urlopen(_request, timeout):
        assert timeout == 30
        return Response()

    fake_urllib = SimpleNamespace(
        request=SimpleNamespace(Request=urllib.request.Request, urlopen=urlopen),
        error=urllib.error,
    )
    telegram_json = _compile_worker_function(
        "telegram_json",
        {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "json": json,
            "socket": socket,
            "urllib": fake_urllib,
            "telegram_api_proxy_headers": lambda: {},
            "telegram_api_method_url": lambda _method: (
                "https://tg.toanaas.vn/bottest-token/getFile"
            ),
            "telegram_open_no_redirect": urlopen,
        },
    )

    with pytest.raises(RuntimeError, match="^telegram_api_invalid_json$") as exc_info:
        telegram_json("getFile", {"file_id": "frame"})

    assert exc_info.value.__cause__ is None


def test_29o_worker_telegram_json_normalizes_response_stream_oserror() -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self) -> bytes:
            raise OSError("response stream reset at private path")

    def urlopen(_request, timeout):
        assert timeout == 30
        return Response()

    fake_urllib = SimpleNamespace(
        request=SimpleNamespace(Request=urllib.request.Request, urlopen=urlopen),
        error=urllib.error,
    )
    telegram_json = _compile_worker_function(
        "telegram_json",
        {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "json": json,
            "socket": socket,
            "urllib": fake_urllib,
            "telegram_api_proxy_headers": lambda: {},
            "telegram_api_method_url": lambda _method: (
                "https://tg.toanaas.vn/bottest-token/getFile"
            ),
            "telegram_open_no_redirect": urlopen,
        },
    )

    with pytest.raises(RuntimeError, match="^telegram_api_network$") as exc_info:
        telegram_json("getFile", {"file_id": "frame"})

    assert exc_info.value.__cause__ is None
    assert "private path" not in str(exc_info.value)


def test_29o_worker_download_rejects_malformed_getfile_shape(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "malformed-getfile.partial"
    downloader = _compile_worker_function(
        "telegram_download_file",
        {
            "telegram_json": lambda *_args, **_kwargs: {
                "ok": True,
                "result": [],
            },
            "telegram_file_download_url": lambda _path: (
                "https://tg.toanaas.vn/localfile/test-token/frame.jpg"
            ),
            "telegram_api_proxy_headers": lambda: {},
            "telegram_open_no_redirect": lambda *_args, **_kwargs: None,
            "frame_video_telegram_input_limit_bytes": lambda: 500 * 1024 * 1024,
            "env_int": lambda _name, default: default,
            "urllib": SimpleNamespace(
                request=SimpleNamespace(Request=urllib.request.Request),
                error=urllib.error,
            ),
            "socket": socket,
            "os": os,
        },
    )

    with pytest.raises(RuntimeError, match="^telegram_get_file_failed$") as exc_info:
        downloader("frame", str(destination))

    assert exc_info.value.__cause__ is None
    assert not destination.exists()


def test_29o_worker_download_cleans_partial_after_stream_oserror(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "stream-reset.partial"

    class Response:
        reads = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self, _size: int) -> bytes:
            self.reads += 1
            if self.reads == 1:
                return b"partial-frame"
            raise OSError("response stream reset at private path")

    def urlopen(_request, timeout):
        assert timeout == 1800
        return Response()

    downloader = _compile_worker_function(
        "telegram_download_file",
        {
            "telegram_json": lambda *_args, **_kwargs: {
                "ok": True,
                "result": {"file_path": "/safe/frame.jpg"},
            },
            "telegram_file_download_url": lambda _path: (
                "https://tg.toanaas.vn/localfile/test-token/frame.jpg"
            ),
            "telegram_api_proxy_headers": lambda: {},
            "telegram_open_no_redirect": urlopen,
            "frame_video_telegram_input_limit_bytes": lambda: 500 * 1024 * 1024,
            "env_int": lambda _name, default: default,
            "urllib": SimpleNamespace(
                request=SimpleNamespace(Request=urllib.request.Request),
                error=urllib.error,
            ),
            "socket": socket,
            "os": os,
        },
    )

    with pytest.raises(RuntimeError, match="^telegram_download_io$") as exc_info:
        downloader("frame", str(destination))

    assert exc_info.value.__cause__ is None
    assert "private path" not in str(exc_info.value)
    assert not destination.exists()


def test_29o_worker_delivery_error_never_chains_token_url(tmp_path: Path) -> None:
    video_path = tmp_path / "frame-delivery.mp4"
    video_path.write_bytes(b"frame-video")

    def urlopen(request, timeout):
        raise urllib.error.HTTPError(
            "https://tg.toanaas.vn/botREAL-TOKEN/sendVideo",
            500,
            "server error",
            None,
            None,
        )

    fake_urllib = SimpleNamespace(
        request=SimpleNamespace(Request=urllib.request.Request, urlopen=urlopen),
        error=urllib.error,
    )
    sender = _compile_worker_function(
        "telegram_send_video_receipt",
        {
            "TELEGRAM_BOT_TOKEN": "REAL-TOKEN",
            "os": os,
            "json": json,
            "socket": socket,
            "urllib": fake_urllib,
            "safe_display_filename": lambda value, _fallback: str(value),
            "telegram_api_proxy_headers": lambda: {},
            "telegram_api_method_url": lambda method: (
                f"https://tg.toanaas.vn/botREAL-TOKEN/{method}"
            ),
            "telegram_open_no_redirect": urlopen,
            "env_int": lambda _name, default: default,
        },
    )

    with pytest.raises(
        RuntimeError,
        match="^telegram_delivery_outcome_uncertain$",
    ) as exc_info:
        sender("29016", str(video_path), "frame")

    assert exc_info.value.__cause__ is None
    assert "REAL-TOKEN" not in str(exc_info.value)


def test_29o_ambiguous_delivery_is_terminal_and_never_retryable() -> None:
    uncertain = getattr(seam, "frame_video_delivery_outcome_uncertain", None)
    assert callable(uncertain)

    class NetworkError(Exception):
        pass

    class TimedOut(NetworkError):
        pass

    class BadRequest(Exception):
        pass

    for error in (
        TimeoutError("timed out"),
        socket.timeout("read timeout"),
        OSError("response stream reset"),
        NetworkError("connection reset"),
        TimedOut("Timed out"),
        RuntimeError("telegram_delivery_outcome_uncertain"),
        RuntimeError("telegram_delivery_receipt_missing"),
    ):
        assert uncertain(error) is True
    assert uncertain(BadRequest("wrong file identifier")) is False
    assert uncertain(RuntimeError("telegram_delivery_rejected")) is False

    direct_source = _function_source(
        REPO_ROOT / "bot.py",
        "handle_frame_video_final_confirm",
    )
    worker_source = _function_source(
        REPO_ROOT / "bot.py",
        "handle_frame_video_worker_job_update",
    )
    status_source = _function_source(
        REPO_ROOT / "bot.py",
        "frame_video_job_status_text",
    )

    for source in (direct_source, worker_source):
        assert "frame_video_delivery_outcome_uncertain" in source
        assert 'status="delivery_unknown"' in source
        assert 'delivery_status="unverified"' in source
    assert '"delivery_unknown"' in direct_source
    assert 'status == "delivery_unknown"' in status_source


@pytest.mark.parametrize(
    "delivery_result",
    (
        RuntimeError("telegram_delivery_outcome_uncertain"),
        None,
        {},
        {"sent": True, "message_id": "29023", "file_id": ""},
    ),
    ids=("transport-error", "missing-receipt", "empty-receipt", "partial-receipt"),
)
def test_29o_worker_delivery_uncertainty_persists_terminal_unknown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    delivery_result: object,
) -> None:
    updates: list[dict] = []
    delivery_calls = 0

    def download(_file_id: str, destination: str, **_kwargs) -> None:
        Path(destination).write_bytes(b"frame")

    def render(**kwargs) -> dict:
        artifact = b"frame-video"
        Path(kwargs["output_path"]).write_bytes(artifact)
        return {
            "enabled": True,
            "ok": True,
            "output_sha256": "a" * 64,
            "probe": {
                "ok": True,
                "full_decode": True,
                "duration_seconds": 3.0,
                "size_bytes": len(artifact),
                "video_stream_count": 1,
                "video_codec": "h264",
                "width": 640,
                "height": 480,
                "artifact_sha256": "a" * 64,
            },
        }

    def send(*_args, **_kwargs):
        nonlocal delivery_calls
        delivery_calls += 1
        if isinstance(delivery_result, BaseException):
            raise delivery_result
        return delivery_result

    def update(job_id, status, error_short="", **kwargs) -> None:
        updates.append(
            {
                "job_id": job_id,
                "status": status,
                "error_short": error_short,
                **kwargs,
            }
        )

    monkeypatch.setattr(local_worker, "telegram_download_file", download)
    monkeypatch.setattr(local_worker, "telegram_send_video_receipt", send)
    monkeypatch.setattr(local_worker, "update_job", update)
    monkeypatch.setattr(local_worker, "env_int", lambda _name, default: default)
    monkeypatch.setattr(local_worker, "local_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(local_worker, "find_ffprobe", lambda **_kwargs: "ffprobe")
    monkeypatch.setattr(local_worker, "local_worker_runtime_sha", lambda: "a" * 40)
    monkeypatch.setattr(
        local_worker.frame_video_public_seam,
        "render_frame_video_public",
        render,
    )

    payload = {
        "chat_id": "29023",
        "user_id": 29023,
        "photos": [
            {
                "file_id": "frame-29023",
                "file_unique_id": "frame-29023-unique",
                "file_size": 5,
            }
        ],
        "state": {
            "photos": [
                {
                    "file_id": "frame-29023",
                    "file_unique_id": "frame-29023-unique",
                    "file_size": 5,
                }
            ],
            "seconds_per_image": 3.0,
            "transition": "none",
        },
        "frame_video_durable_public_seam": True,
        "frame_video_runtime_sha": "a" * 40,
        "frame_video_expected_worker_sha": "a" * 40,
        "frame_job_id": "fv-delivery-unknown-29023",
        "max_render_seconds": 1800,
    }

    local_worker.run_frame_video_render(
        {"id": 29023, "input_file_id": json.dumps(payload)}
    )

    assert delivery_calls == 1
    assert updates[-1]["status"] == "failed"
    assert str(updates[-1]["error_short"]).startswith("{")
    detail = json.loads(updates[-1]["error_short"])
    assert detail["stage"] == "delivery_unknown"
    assert detail["reason"] == "telegram_delivery_outcome_uncertain"
    assert detail["charge"] == 0


def test_29o_bot_maps_worker_delivery_uncertainty_without_charge_or_retry() -> None:
    frame_updates: list[dict] = []
    charges: list[str] = []
    clears: list[str] = []
    payload = {
        "frame_job_id": "fv-delivery-unknown-29024",
        "user_id": "29024",
        "state": {},
        "frame_video_durable_public_seam": True,
    }
    previous = {
        "id": 29024,
        "job_type": "frame_video_render",
        "status": "running",
        "worker_id": "frame-worker-29o",
        "input_file_id": json.dumps(payload),
    }
    updated = {
        **previous,
        "status": "failed",
        "error_short": json.dumps(
            {
                "stage": "delivery_unknown",
                "reason": "telegram_delivery_outcome_uncertain",
                "charge": 0,
            },
            separators=(",", ":"),
        ),
    }
    handler = _compile_bot_function(
        "handle_frame_video_worker_job_update",
        {
            "json": json,
            "frame_video_public_seam": seam,
            "update_frame_video_job": lambda _job_id, **fields: (
                frame_updates.append(dict(fields))
            ),
            "update_frame_video_job_config": lambda *_args, **_kwargs: None,
            "now_text": lambda: "2026-08-02 13:00:00",
            "frame_video_job_for_user": lambda *_args, **_kwargs: {},
            "save_tool_test_result": lambda *_args, **_kwargs: None,
            "frame_video_charge_after_delivery": lambda *_args, **_kwargs: (
                charges.append("called") or {"ok": True}
            ),
            "clear_frame_video_state": lambda value: clears.append(str(value)),
            "sanitize_log_text": lambda value: str(value),
            "set_frame_video_last_error": lambda *_args, **_kwargs: None,
        },
    )

    handler(previous, updated)

    assert charges == []
    assert clears == []
    assert frame_updates[-1]["status"] == "delivery_unknown"
    assert frame_updates[-1]["delivery_status"] == "unverified"
    assert frame_updates[-1]["charge_state"] == "not_charged"
    assert frame_updates[-1]["wallet_charge_amount_xu"] == 0
    assert frame_updates[-1]["lease_owner"] == ""
    assert frame_updates[-1]["lease_expires_at"] == ""


def test_29o_existing_delivery_unknown_job_cannot_reconfirm_or_resend() -> None:
    rendered: list[str] = []
    edited: list[str] = []
    job = {
        "job_id": "fv-delivery-unknown-29025",
        "status": "delivery_unknown",
        "delivery_status": "unverified",
    }

    async def safe_edit(_query, text, **_kwargs):
        edited.append(str(text))
        return "status-message"

    handler = _compile_bot_function(
        "handle_frame_video_final_confirm",
        {
            "FRAME_VIDEO_CONFIRM_LOCKS": {},
            "asyncio": asyncio,
            "normalize_frame_video_state": lambda value: dict(value or {}),
            "get_frame_video_state": lambda _uid: {
                "frame_video_job_id": job["job_id"]
            },
            "frame_video_job_for_user": lambda *_args, **_kwargs: dict(job),
            "safe_edit_or_send": safe_edit,
            "frame_video_job_status_text": lambda value: (
                f"status:{value['status']}"
            ),
            "frame_video_job_status_keyboard": lambda _job_id: None,
            "frame_video_flow": SimpleNamespace(
                sync_render_overlays=lambda _state: (
                    rendered.append("retried")
                    or (_ for _ in ()).throw(
                        AssertionError("delivery_unknown job was retried")
                    )
                )
            ),
        },
    )
    query = SimpleNamespace(
        from_user=SimpleNamespace(first_name="Owner", username="owner"),
        message=SimpleNamespace(chat_id=29025),
    )

    result = asyncio.run(
        handler(
            query,
            SimpleNamespace(),
            29025,
            {"frame_video_job_id": job["job_id"]},
            "vi",
        )
    )

    assert result == "status-message"
    assert edited == ["status:delivery_unknown"]
    assert rendered == []


def test_29o_direct_large_delivery_uncertainty_is_terminal_and_single_send() -> None:
    output_size = 20 * 1024 * 1024 + 1
    job_id = "fv-direct-delivery-unknown-29026"
    state_store = {
        "type": "frame_video",
        "photos": [
            {
                "file_id": "frame-direct-29026",
                "file_unique_id": "frame-direct-29026-unique",
                "file_size": 1024,
            }
        ],
        "seconds_per_image": 3.0,
        "transition": "none",
    }
    job_updates: list[dict] = []
    media_calls: list[str] = []
    charges: list[str] = []
    cleared: list[str] = []
    public_messages: list[str] = []

    class Waiting:
        async def edit_text(self, text, **_kwargs):
            public_messages.append(str(text))
            return None

    async def safe_edit_or_send(*_args, **_kwargs):
        return Waiting()

    async def render(
        _context,
        _state,
        output_path,
        _tmpdir,
        **_kwargs,
    ) -> dict:
        Path(output_path).write_bytes(b"validated-mp4")
        return {
            "ok": True,
            "output_size_bytes": output_size,
            "output_sha256": "b" * 64,
            "probe": {
                "ok": True,
                "full_decode": True,
                "duration_seconds": 3.0,
                "size_bytes": output_size,
                "video_stream_count": 1,
                "video_codec": "h264",
                "width": 640,
                "height": 480,
            },
        }

    class Bot:
        async def send_video(self, **_kwargs):
            media_calls.append("send_video")
            raise TimeoutError("upload receipt timed out")

        async def send_document(self, **_kwargs):
            media_calls.append("send_document")
            raise TimeoutError("upload receipt timed out")

        async def send_message(self, **kwargs):
            public_messages.append(str(kwargs.get("text") or ""))
            return SimpleNamespace(message_id=29027)

    def set_state(_uid, value):
        state_store.clear()
        state_store.update(dict(value or {}))
        return dict(state_store)

    def update_job(_job_id, **fields):
        job_updates.append(dict(fields))
        return {"job_id": job_id, **fields}

    public_seam = SimpleNamespace(
        frame_video_public_seam_enabled=lambda: True,
        frame_video_public_minimum_images=lambda: 1,
        compact_frame_video_probe=lambda value: dict(value or {}),
        frame_video_telegram_delivery_method=lambda size: (
            "document" if int(size or 0) > 20 * 1024 * 1024 else "video"
        ),
        frame_video_delivery_outcome_uncertain=lambda error: isinstance(
            error,
            TimeoutError,
        ),
        frame_video_delivery_receipt_blocker=lambda *_args: "",
    )
    os_proxy = SimpleNamespace(
        path=SimpleNamespace(
            join=os.path.join,
            getsize=lambda _path: output_size,
        )
    )
    handler = _compile_bot_function(
        "handle_frame_video_final_confirm",
        {
            "FRAME_VIDEO_CONFIRM_LOCKS": {},
            "asyncio": asyncio,
            "normalize_frame_video_state": lambda value: dict(value or {}),
            "get_frame_video_state": lambda _uid: dict(state_store),
            "frame_video_job_for_user": lambda *_args, **_kwargs: {},
            "safe_edit_or_send": safe_edit_or_send,
            "frame_video_job_status_text": lambda _job: "status",
            "frame_video_job_status_keyboard": lambda _job_id: None,
            "frame_video_flow": SimpleNamespace(
                sync_render_overlays=lambda value: dict(value or {})
            ),
            "frame_video_stage_timeout_for_state": lambda _state: 1800,
            "frame_video_public_seam": public_seam,
            "frame_video_runtime": SimpleNamespace(
                FRAME_VIDEO_MIN_IMAGES=2,
                validate_plan=lambda _state, **_kwargs: {
                    "ok": True,
                    "manifest": [{}],
                },
            ),
            "set_frame_video_state": set_state,
            "frame_video_collect_keyboard": lambda *_args, **_kwargs: None,
            "is_frame_video3_state": lambda _state: False,
            "frame_video_review_keyboard": lambda *_args, **_kwargs: None,
            "frame_video_panel_keyboard": lambda: None,
            "frame_video_runtime_guard": lambda *_args, **_kwargs: {
                "ok": True,
                "action": "direct_render",
            },
            "set_frame_video_last_error": lambda *_args, **_kwargs: None,
            "frame_video_maintenance_text": lambda: "maintenance",
            "frame_video_planned_charge_xu": lambda *_args: 0,
            "get_user": lambda *_args: (1000, None, None),
            "is_admin_user": lambda _uid: True,
            "edit_insufficient_credits": lambda *_args, **_kwargs: None,
            "create_frame_video_job": lambda *_args, **_kwargs: job_id,
            "sanitize_log_text": lambda value: str(value),
            "update_frame_video_job": update_job,
            "datetime": datetime,
            "VN_TZ": None,
            "timedelta": timedelta,
            "is_railway_runtime": lambda: False,
            "now_text": lambda: "2026-08-02 13:00:00",
            "product_progress_status_text": lambda *_args, **_kwargs: "progress",
            "progress_auto_refresh_register_message": lambda *_args, **_kwargs: None,
            "tempfile": tempfile,
            "os": os_proxy,
            "render_frame_video_canonical_from_state": render,
            "frame_video_success_keyboard": lambda: None,
            "frame_video_charge_after_delivery": lambda *_args, **_kwargs: (
                charges.append("called") or {"ok": True, "charged": 0}
            ),
            "save_tool_test_result": lambda *_args, **_kwargs: None,
            "record_usage_event": lambda *_args, **_kwargs: None,
            "clear_frame_video_state": lambda value: cleared.append(str(value)),
            "json": json,
        },
    )
    query = SimpleNamespace(
        from_user=SimpleNamespace(
            first_name="Owner",
            username="owner",
        ),
        message=SimpleNamespace(chat_id=29026),
    )

    asyncio.run(
        handler(
            query,
            SimpleNamespace(bot=Bot()),
            29026,
            dict(state_store),
            "vi",
        )
    )

    assert media_calls == ["send_document"]
    assert charges == []
    assert cleared == []
    assert state_store["frame_video_job_id"] == job_id
    assert job_updates[-1]["status"] == "delivery_unknown"
    assert job_updates[-1]["delivery_status"] == "unverified"
    assert all(
        update.get("status") != "failed_no_charge" for update in job_updates
    )
    assert public_messages
