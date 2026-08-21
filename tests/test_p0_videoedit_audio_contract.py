"""RED contracts for Video Edit audio/add-on identity and admission.

These tests deliberately exercise the service seams that sit between Telegram
intake and the local worker.  They do not call Telegram, providers, FFmpeg, or
the wallet.  The production lane must make each test green after the RED
selector has been run by the owning agent.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path

import pytest

from services import video_edit_long_media, video_editengine1, video_local_editing


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
BOT_MODULE = ast.parse(BOT_SOURCE, filename="bot.py")


def _literal_assignment(name: str):
    for node in BOT_MODULE.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"missing bot assignment: {name}")


def _function_source(name: str) -> str:
    marker = f"def {name}("
    start = BOT_SOURCE.index(marker)
    candidates = [
        BOT_SOURCE.find("\ndef ", start + 1),
        BOT_SOURCE.find("\nasync def ", start + 1),
        BOT_SOURCE.find("\n@", start + 1),
    ]
    ends = [position for position in candidates if position >= 0]
    return BOT_SOURCE[start : min(ends) if ends else len(BOT_SOURCE)]


def _compile_bot_function(name: str, namespace: dict):
    module = ast.parse(
        "from __future__ import annotations\n\n" + _function_source(name),
        filename=f"bot.py::{name}",
    )
    exec(compile(module, filename=f"bot.py::{name}", mode="exec"), namespace)
    return namespace[name]


def _state(*, audio_path: str = "audio-placeholder.mp3") -> dict:
    plan = video_local_editing.default_manual_edit_plan("source.mp4")
    plan["trim"] = {"start_ms": 0, "end_ms": 10_000}
    plan["audio_tracks"] = [
        {
            "path": audio_path,
            "kind": "voice",
            "volume": 0.8,
            "start_ms": 250,
            "end_ms": 2_500,
        }
    ]
    return {
        "source_file_id": "video-file-id",
        "source_file_size": 10_000_000,
        "media_lane": "short_media",
        "inspection_complete": True,
        "source_metadata": {
            "ok": True,
            "has_audio": True,
            "duration": 10.0,
            "duration_ms": 10_000,
            "width": 1280,
            "height": 720,
            "bytes": 10_000_000,
            "actual_bytes": 10_000_000,
            "media_lane": "short_media",
        },
        "selected_tool": "manual",
        "manual_edit_plan": plan,
        "audio_sources": [
            {
                "file_id": "tg-voice-001",
                "file_name": "voice.m4a",
                "file_size": 2_000_000,
                "kind": "voice",
                "volume": 0.8,
                "start_ms": 250,
                "end_ms": 2_500,
            }
        ],
    }


def _runtime(**overrides) -> dict:
    value = {
        "enabled": True,
        "poll_enabled": True,
        "token_configured": True,
        "connected": True,
        "ffmpeg_path_configured": True,
        "ffprobe_path_configured": True,
        "delivery_configured": True,
        "heartbeat_contract_version": 1,
        "worker_owner": video_editengine1.OUTBOX_OWNER,
        "engine_route": video_editengine1.ENGINE_ROUTE,
        "capabilities": [video_editengine1.WORKER_CAPABILITY],
        "heartbeat_age_seconds": 1,
        "worker_id": "worker-audio",
        "video_edit_filter_worker_id": "worker-audio",
        "ffmpeg_path": "C:/ffmpeg/bin/ffmpeg.exe",
        "video_edit_filter_ffmpeg_path": "C:/ffmpeg/bin/ffmpeg.exe",
        "workspace_ready": True,
        "workspace_free_bytes": 10**12,
        "video_edit_max_deadline_seconds": 6 * 60 * 60,
        "worker_token_ready": True,
        "local_bot_api_ready": True,
        "video_edit_filters_known": True,
        # Include the complete expected audio surface so this fixture only
        # fails when the admission contract omits audio requirements/bytes.
        "video_edit_filters": [
            "format",
            "aresample",
            "amix",
            "alimiter",
            "adelay",
            "atrim",
            "asetpts",
            "volume",
        ],
    }
    value.update(overrides)
    return value


@pytest.mark.parametrize("kind", ["music", "voice", "sfx"])
def test_video_editor_audio_pending_kind_survives_sanitizer(kind: str) -> None:
    """Each audio lane must survive the shared pending-state sanitizer."""

    namespace = {
        "VIDEO_EDITOR_TEXT_FIELDS": _literal_assignment("VIDEO_EDITOR_TEXT_FIELDS"),
        "VIDEO_EDITOR_NUMBER_FIELDS": _literal_assignment("VIDEO_EDITOR_NUMBER_FIELDS"),
        "VIDEO_EDITOR_STRUCTURED_FIELDS": _literal_assignment("VIDEO_EDITOR_STRUCTURED_FIELDS"),
        "safe_int": lambda value, default=0: int(value or default),
        "json": json,
        "re": re,
        "time": time,
    }
    builder = _compile_bot_function("build_video_editor_pending_state", namespace)

    state = builder("await_audio_asset", audio_pending_kind=kind)

    assert state["audio_pending_kind"] == kind


@pytest.mark.parametrize("kind", ["music", "voice", "sfx"])
def test_audio_file_id_placeholder_is_admitted_before_worker_materialization(kind: str) -> None:
    """Telegram file IDs may be pending while the worker owns local paths."""

    state = _state(audio_path="")
    state["audio_sources"][0]["kind"] = kind
    state["manual_edit_plan"]["audio_tracks"][0]["kind"] = kind
    result = video_editengine1.preflight(state, _runtime())

    assert result["ok"] is True
    assert result["reason"] == "ok"
    assert result["checks"]["plan"] is True


def _audio_job_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE local_worker_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            command TEXT,
            job_type TEXT,
            status TEXT,
            provider TEXT,
            input_file_id TEXT,
            output_file_id TEXT,
            output_url TEXT,
            error_short TEXT,
            created_at TEXT,
            started_at TEXT,
            finished_at TEXT,
            xu_cost INTEGER,
            admin_only INTEGER,
            worker_id TEXT,
            updated_at TEXT
        )"""
    )
    return conn


def _audio_job_input(audio_file_id: str) -> dict:
    plan = video_local_editing.default_manual_edit_plan("source.mp4")
    plan["trim"] = {"start_ms": 0, "end_ms": 4_000}
    plan["audio_tracks"] = [
        {
            "path": "audio-placeholder.mp3",
            "kind": "music",
            "volume": 0.35,
            "start_ms": 0,
            "end_ms": 0,
        }
    ]
    return {
        "user_id": 701,
        "chat_id": 702,
        "edit_session_id": "audio-idempotency-session",
        "source_file_id": "telegram-source-audio",
        "source_metadata": {
            "ok": True,
            "has_audio": True,
            "duration_ms": 4_000,
            "width": 1_280,
            "height": 720,
        },
        "plan": plan,
        "tail": {},
        "quality_tier_id": "local-free",
        "price_xu": 0,
        "worker_payload": {
            "local1_contract": 1,
            "local1_mode": "manual",
            "plan_schema_version": "video-edit-plan-v1",
            "source_file_id": "telegram-source-audio",
            "source_video_hash": "a" * 64,
            "source_manifest": {"sha256": "a" * 64},
            "audio_sources": [
                {
                    "file_id": audio_file_id,
                    "file_name": "music.mp3",
                    "file_size": 2_000_000,
                    "kind": "music",
                    "volume": 0.35,
                    "start_ms": 0,
                    "end_ms": 0,
                }
            ],
            "provider_call": False,
            "charge_policy": "free_local_tool",
            "price_xu": 0,
            "quoted_price_xu": 0,
            "state_revision": 3,
            "rights_confirmation": {
                "confirmed": True,
                "policy": "video_edit_rights_v1",
                "user_id": "701",
                "review_revision": 3,
                "confirmed_at_unix": 1_750_000_000,
            },
        },
    }


def test_audio_file_identity_is_part_of_stable_idempotency_key() -> None:
    conn = _audio_job_connection()
    first = video_editengine1.create_job(conn, **_audio_job_input("tg-audio-1"))
    conn.commit()

    second = video_editengine1.create_job(conn, **_audio_job_input("tg-audio-2"))

    assert first["created"] is True
    assert second["created"] is True
    assert second["idempotency_key"] != first["idempotency_key"]


def test_split_reset_token_changes_when_the_audio_asset_is_replaced() -> None:
    token_for = _compile_bot_function(
        "video_editor_split_reset_token",
        {
            "hashlib": hashlib,
            "json": json,
            "safe_int": lambda value, default=0: int(value or default),
            "video_editor_state_snapshot": lambda state: json.loads(
                json.dumps(dict(state or {}), ensure_ascii=False)
            ),
        },
    )
    state = {
        "edit_session_id": "audio-reset-session",
        "state_revision": 4,
        "manual_edit_plan": _state()["manual_edit_plan"],
        "audio_sources": [{"file_id": "voice-a", "kind": "voice"}],
    }

    first = token_for(state)
    state["audio_sources"] = [{"file_id": "voice-b", "kind": "voice"}]

    assert token_for(state) != first


def test_audio_filter_admission_includes_mix_timing_and_resampling_filters() -> None:
    plan = _state()["manual_edit_plan"]

    required = video_local_editing.required_optional_filters(plan, has_audio=False)

    assert {
        "aresample",
        "amix",
        "alimiter",
        "adelay",
        "atrim",
        "asetpts",
        "volume",
    } <= required


@pytest.mark.parametrize(
    ("field", "forged_value"),
    (
        ("volume", 0.2),
        ("start_ms", 500),
        ("end_ms", 3_000),
    ),
)
def test_audio_asset_settings_are_bound_to_the_reviewed_plan(
    field: str,
    forged_value,
) -> None:
    state = _state()
    assert video_local_editing.manual_plan_assets_match(
        state["manual_edit_plan"],
        concat_sources=[],
        logo_source={},
        subtitle_source={},
        audio_sources=state["audio_sources"],
    ) is True
    forged_sources = json.loads(json.dumps(state["audio_sources"]))
    forged_sources[0][field] = forged_value

    assert video_local_editing.manual_plan_assets_match(
        state["manual_edit_plan"],
        concat_sources=[],
        logo_source={},
        subtitle_source={},
        audio_sources=forged_sources,
    ) is False


def test_master_audio_controls_are_applied_after_final_mix() -> None:
    plan = _state()["manual_edit_plan"]
    plan["volume"] = 0.4
    plan["audio_normalization"] = "loudnorm"
    plan["local_effects"] = {
        "fade_in_ms": 300,
        "fade_out_ms": 300,
        "vignette": False,
        "slow_zoom": False,
    }
    plan["audio_tracks"][0]["volume"] = 1.0

    command = video_local_editing.build_manual_ffmpeg_command(
        plan,
        output_path="output.mp4",
        source_probe={
            "has_audio": True,
            "width": 1280,
            "height": 720,
            "fps": 30.0,
        },
        ffmpeg_path="ffmpeg",
    )
    graph = command[command.index("-filter_complex") + 1]

    mix = graph.index("amix=")
    master_volume = graph.index("volume=0.4", mix)
    normalize = graph.index("loudnorm=", master_volume)
    fade = graph.index("afade=", normalize)
    limiter = graph.index("alimiter=", fade)
    assert mix < master_volume < normalize < fade < limiter


def test_per_track_zero_volume_remains_muted_in_the_ffmpeg_graph() -> None:
    plan = _state()["manual_edit_plan"]
    plan["audio_tracks"][0]["volume"] = 0.0

    command = video_local_editing.build_manual_ffmpeg_command(
        plan,
        output_path="output.mp4",
        source_probe={
            "has_audio": True,
            "width": 1280,
            "height": 720,
            "fps": 30.0,
        },
        ffmpeg_path="ffmpeg",
    )
    graph = command[command.index("-filter_complex") + 1]
    track_graph = graph[
        graph.index("[1:a:0]") : graph.index("[a_track_0]")
    ]

    assert "volume=0" in track_graph


def test_audio_only_edit_requires_an_audio_bearing_final_artifact() -> None:
    plan = _state()["manual_edit_plan"]

    assert video_local_editing.manual_output_requires_audio(
        plan,
        source_has_audio=False,
    ) is True
    plan["volume"] = 0.0
    assert video_local_editing.manual_output_requires_audio(
        plan,
        source_has_audio=False,
    ) is False


def test_audio_asset_bytes_are_counted_in_preflight_capacity() -> None:
    state = _state()
    source_bytes = state["source_file_size"]
    audio_bytes = state["audio_sources"][0]["file_size"]

    result = video_editengine1.preflight(state, _runtime())

    assert result["ok"] is True
    assert result["declared_input_bytes"] == source_bytes + audio_bytes
    expected = video_edit_long_media.estimate_workspace(
        operation="transcode",
        source_bytes=source_bytes,
        asset_bytes=[audio_bytes],
        output_count=1,
    ).required_bytes
    assert result["workspace_required_bytes"] >= expected
