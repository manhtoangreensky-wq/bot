from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from services import frame_video_flow as flow
from services import frame_video_runtime as runtime


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")


def _state(count: int = 2, **overrides) -> dict:
    photos = [
        {
            "image_id": f"img_{index}",
            "file_id": f"file_{index}",
            "file_name": f"image_{index}.png",
        }
        for index in range(count)
    ]
    return flow.normalize_state({"photos": photos, **overrides})


def _binary(name: str) -> str:
    configured = os.environ.get(f"FRAME_VIDEO_{name.upper()}") or shutil.which(name)
    if configured:
        return configured
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    matches = list(root.glob(f"**/{name}.exe"))
    return str(matches[0]) if matches else ""


def _run(command: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def _make_png(ffmpeg: str, path: Path, color: str) -> None:
    result = _run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=160x100:d=0.1",
            "-frames:v",
            "1",
            str(path),
        ]
    )
    assert result.returncode == 0, result.stderr[-1000:]


def _callback_literals(source: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(r'callback_data="(framevideo[^"]*)"', source)
    }


def _function_source(name: str) -> str:
    start = BOT_SOURCE.index(f"def {name}(")
    next_def = re.search(r"\n(?:async )?def [A-Za-z_]", BOT_SOURCE[start + 1 :])
    end = start + 1 + next_def.start() if next_def else len(BOT_SOURCE)
    return BOT_SOURCE[start:end]


def test_route_matrix_covers_every_public_frame_video_action() -> None:
    expected = {
        "start",
        "done",
        "ai_stitch_generated",
        "panel",
        "upload",
        "images",
        "sort",
        "image_select",
        "image_action",
        "image_duration",
        "duration_menu",
        "duration_set",
        "duration_custom",
        "ratio_menu",
        "ratio_set",
        "ratio_custom",
        "fit_menu",
        "fit_set",
        "transition_menu",
        "transition_set",
        "transition_time",
        "motion_menu",
        "motion_set",
        "music_menu",
        "music_upload",
        "music_off",
        "volume_menu",
        "volume",
        "volume_custom",
        "audio_fade",
        "addons",
        "addon",
        "position_menu",
        "position_set",
        "text_list",
        "text_select",
        "text_editor",
        "text_action",
        "text_edit",
        "text_scope_menu",
        "text_scope_set",
        "text_timing",
        "text_animation_menu",
        "text_animation_set",
        "text_style_menu",
        "text_style_set",
        "quality_menu",
        "quality_set",
        "quality_info",
        "review",
        "continue",
        "confirm",
        "status",
    }
    assert expected <= set(flow.FRAME_VIDEO_ROUTE_MATRIX)
    for action, route in flow.FRAME_VIDEO_ROUTE_MATRIX.items():
        assert route["owner"]
        assert route["screen"]
        assert route["back"]


def test_legacy_routes_are_read_only_redirects() -> None:
    assert flow.FRAME_VIDEO_LEGACY_ROUTE_MATRIX
    for route in flow.FRAME_VIDEO_LEGACY_ROUTE_MATRIX.values():
        assert route["owner"] == "handle_frame_video_canonical_callback"
        assert route["mutation"] == "read_only_redirect"
        assert route["back"] == "hub"


def test_canonical_registration_and_intake_have_one_owner() -> None:
    assert len(re.findall(r'CallbackQueryHandler\(handle_frame_video_callback,\s*pattern=r"\^framevideo\\\|"\)', BOT_SOURCE)) == 1
    assert len(re.findall(r"^async def handle_frame_video_pending_media\(", BOT_SOURCE, re.MULTILINE)) == 1
    assert "processed_media_message_ids" in BOT_SOURCE
    assert "delivery_receipt_missing" in BOT_SOURCE


def test_frame_video_render_contract_has_no_shortest_or_provider_call() -> None:
    runtime_source = (ROOT / "services" / "frame_video_runtime.py").read_text(encoding="utf-8")
    worker_source = (ROOT / "local_worker.py").read_text(encoding="utf-8")
    assert "-shortest" not in runtime_source
    assert "-shortest" not in worker_source
    assert "shopaikey_video" not in runtime_source.lower()
    assert "key4u" not in runtime_source.lower()
    assert "Suno" not in runtime_source
    assert '"-t"' in runtime_source


def test_delivery_receipt_precedes_charge_and_missing_receipt_is_no_charge() -> None:
    confirm_start = BOT_SOURCE.index("async def handle_frame_video_final_confirm")
    confirm_source = BOT_SOURCE[confirm_start : confirm_start + 30000]
    assert confirm_source.index("delivery_message_id =") < confirm_source.index("frame_video_charge_after_delivery(job_id")
    assert "receipt_recorded=1" in confirm_source
    assert "status=\"failed_no_charge\"" in confirm_source
    assert "telegram_message_id_missing" in confirm_source


def test_planning_and_public_callbacks_do_not_create_side_effects_before_confirm() -> None:
    canonical_start = BOT_SOURCE.index("async def handle_frame_video_canonical_callback")
    confirm_marker = BOT_SOURCE.index('    if action == "confirm":', canonical_start)
    planning_source = BOT_SOURCE[canonical_start:confirm_marker]
    assert "create_frame_video_job" not in planning_source
    assert "create_local_worker_job" not in planning_source
    assert "spend_fixed_credit_info" not in planning_source
    assert "send_video" not in planning_source
    assert "SCENE3" not in planning_source
    assert "handle_storyboard" not in planning_source


def test_worker_fallback_dispatch_and_terminal_no_charge_contract_are_present() -> None:
    worker_source = (ROOT / "local_worker.py").read_text(encoding="utf-8")
    assert 'if job_type == "frame_video_render"' in worker_source
    assert "telegram_send_video_receipt" in worker_source
    assert "frame_video_delivery_receipt_missing" in worker_source
    assert "frame_video_render_timeout" in worker_source


def test_public_entry_uses_local_ffmpeg_first_and_worker_only_as_fallback() -> None:
    intro_start = BOT_SOURCE.index("def frame_video_intro_ready")
    intro_source = BOT_SOURCE[intro_start : BOT_SOURCE.index("def video_frame_intro_text", intro_start)]
    assert "frame_video_ffmpeg_path() or frame_video_worker_connected()" in intro_source
    assert "FRAME_VIDEO_DIRECT_RENDER_ENABLED" not in intro_source
    public_gate_start = BOT_SOURCE.index("def frame_video_public_gate")
    public_gate_source = BOT_SOURCE[public_gate_start : BOT_SOURCE.index("def video_billing_public_gate", public_gate_start)]
    assert '"execution_route": "local_ffmpeg"' in public_gate_source
    assert "no local FFmpeg execution route" in public_gate_source
    assert "FRAME_VIDEO_REQUIRE_LOCAL_WORKER=false" not in public_gate_source
    assert "Railway direct render is not safe" not in public_gate_source


def test_manifest_management_preserves_stable_ids_and_order() -> None:
    state = _state(3)
    original_ids = [row["image_id"] for row in state["photos"]]
    state = flow.apply_image_action(state, "select", original_ids[1])
    state = flow.apply_image_action(state, "up")
    assert [row["image_id"] for row in state["photos"]] == [original_ids[1], original_ids[0], original_ids[2]]
    state = flow.apply_image_action(state, "duplicate")
    assert len(state["photos"]) == 4
    assert len({row["image_id"] for row in state["photos"]}) == 4
    state = flow.apply_image_action(state, "cover")
    assert state["photos"][0]["is_cover"] is True
    state = flow.apply_image_action(state, "delete")
    assert len(state["photos"]) == 3


def test_supported_image_counts_and_replace_keep_a_valid_plan() -> None:
    for count in (2, 4, 10, 20):
        state = _state(count)
        assert len(state["photos"]) == count
        assert runtime.validate_plan(state)["ok"] is True
    state = _state(2)
    selected = state["photos"][0]["image_id"]
    replaced = runtime.manifest_replace(
        state["photos"],
        selected,
        {"file_id": "replacement-file", "file_name": "replacement.png", "mime_type": "image/png"},
    )
    assert len(replaced) == 2
    assert replaced[0]["image_id"] == selected
    assert replaced[0]["file_id"] == "replacement-file"


def test_duplicate_media_message_is_idempotent() -> None:
    state, first = flow.mark_media_message_processed(_state(), "telegram-42")
    state, second = flow.mark_media_message_processed(state, "telegram-42")
    assert first is True
    assert second is False
    assert state["processed_media_message_ids"] == ["telegram-42"]


def test_duration_transition_and_volume_contract() -> None:
    state = _state(3, seconds_per_image=4, transition="fade", transition_seconds=0.5)
    assert runtime.expected_duration_seconds(state) == pytest.approx(11.0)
    state = flow.set_global_duration(state, 7)
    assert runtime.expected_duration_seconds(state) == pytest.approx(20.0)
    state = flow.set_volume(state, "music", 999)
    state = flow.set_volume(state, "voice", -10)
    assert state["music_volume_percent"] == 200
    assert state["voice_volume_percent"] == 0
    assert len(runtime.canonical_config(state)["transition_manifest"]) == 2


def test_overlay_sync_keeps_one_subtitle_and_local_text() -> None:
    state = flow.add_text_overlay(_state(2), "Tiêu đề mở đầu")
    state.update({"subtitle_enabled": True, "subtitle_text": "Lời thoại"})
    synced = flow.sync_render_overlays(state)
    synced = flow.sync_render_overlays(synced)
    assert len([row for row in synced["text_overlays"] if row.get("kind") == "subtitle"]) == 1
    assert len([row for row in synced["text_overlays"] if row.get("kind") != "subtitle"]) == 1
    assert next(row for row in synced["text_overlays"] if row.get("kind") == "subtitle")["position"] == "bottom_center"


def test_all_local_render_options_are_normalized_without_side_effects() -> None:
    for ratio in runtime.RATIOS:
        for fit in runtime.FIT_MODES:
            state = _state(2, ratio=ratio, fit_mode=fit, background_color="not-a-color")
            for transition in runtime.TRANSITIONS:
                for motion in runtime.MOTIONS:
                    state.update({"transition": transition, "motion": motion})
                    config = runtime.canonical_config(state)
                    assert config["ratio"] == ratio
                    assert config["fit_mode"] == fit
                    assert config["transition"] == transition
                    assert config["motion"] == motion
                    assert config["background_color"] == "#111111"
    assert runtime.validate_plan(_state(2))["ok"] is True


def test_public_keyboard_literals_use_frame_video_owner() -> None:
    literals = _callback_literals(BOT_SOURCE)
    assert "framevideo|main" in literals
    assert "framevideo|hub" in literals
    assert "framevideo|panel" in literals
    assert "framevideo|addons" in literals
    assert "framevideo|review" in literals
    assert "framevideo|confirm" in literals
    assert "menu|main" not in {
        value for value in literals if value.startswith("framevideo|")
    }


def test_public_panel_and_submenus_have_canonical_rows_and_exact_back() -> None:
    panel = _function_source("frame_video_panel_keyboard")
    expected_rows = [
        ("framevideo|upload", "framevideo|images"),
        ("framevideo|sort", "framevideo|duration_menu"),
        ("framevideo|ratio_menu", "framevideo|transition_menu"),
        ("framevideo|motion_menu", "framevideo|music_menu"),
        ("framevideo|addons", "framevideo|quality_menu"),
        ("framevideo|review", "framevideo|continue"),
        ("framevideo|hub", "framevideo|main"),
    ]
    positions = []
    for left, right in expected_rows:
        assert left in panel
        assert right in panel
        positions.append((panel.index(left), panel.index(right)))
    assert all(left < right for left, right in positions)
    assert [left for left, _ in positions] == sorted(left for left, _ in positions)

    exact_back = {
        "frame_video_collect_keyboard": "framevideo|hub",
        "frame_video_images_keyboard": "framevideo|panel",
        "frame_video_ratio_menu_keyboard": "framevideo|panel",
        "frame_video_fit_keyboard": "framevideo|ratio_menu",
        "frame_video_transition_keyboard": "framevideo|panel",
        "frame_video_motion_keyboard": "framevideo|panel",
        "frame_video_music_menu_keyboard": "framevideo|panel",
        "frame_video_addons_keyboard": "framevideo|panel",
        "frame_video_text_list_keyboard": "framevideo|addons",
        "frame_video_text_editor_keyboard": "framevideo|text_list",
        "frame_video_text_scope_keyboard": "framevideo|text_editor",
        "frame_video_text_animation_keyboard": "framevideo|text_editor",
        "frame_video_text_style_keyboard": "framevideo|text_editor",
        "frame_video_quality_keyboard": "framevideo|panel",
    }
    for function_name, callback in exact_back.items():
        source = _function_source(function_name)
        assert callback in source, function_name
        assert "framevideo|main" in source, function_name


def test_every_canonical_public_action_is_owned_by_route_matrix() -> None:
    canonical_start = BOT_SOURCE.index("FRAME_VIDEO_CANONICAL_ACTIONS = {")
    canonical_end = BOT_SOURCE.index("}\nFRAME_VIDEO_LEGACY_REDIRECT_ACTIONS", canonical_start)
    canonical_actions = set(re.findall(r'"([a-z0-9_]+)"', BOT_SOURCE[canonical_start:canonical_end]))
    assert canonical_actions <= set(flow.FRAME_VIDEO_ROUTE_MATRIX)


def test_ffmpeg_builds_real_mp4_with_valid_duration_and_audio(tmp_path: Path) -> None:
    ffmpeg = _binary("ffmpeg")
    ffprobe = _binary("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg/ffprobe not available locally")

    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    music = tmp_path / "music.wav"
    output = tmp_path / "frame-video.mp4"
    _make_png(ffmpeg, first, "red")
    _make_png(ffmpeg, second, "blue")
    audio = _run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-c:a",
            "pcm_s16le",
            str(music),
        ]
    )
    assert audio.returncode == 0, audio.stderr[-1000:]

    state = _state(
        2,
        photos=[
            {"image_id": "first", "file_id": str(first), "file_name": first.name},
            {"image_id": "second", "file_id": str(second), "file_name": second.name},
        ],
        seconds_per_image=0.8,
        ratio="1x1",
        fit_mode="crop",
        transition="fade",
        transition_seconds=0.2,
        motion="none",
        quality="fast",
        music_enabled=True,
        music_file_id="local-music",
        music_volume_percent=45,
    )
    command = runtime.build_ffmpeg_command(
        [str(first), str(second)],
        str(output),
        state,
        ffmpeg_path=ffmpeg,
        music_path=str(music),
    )
    assert "-shortest" not in command.command
    result = _run(command.command, timeout=90)
    assert result.returncode == 0, result.stderr[-2000:]
    probe = runtime.probe_mp4(str(output), command.expected_duration, command.expects_audio, ffprobe)
    assert probe["ok"], json.dumps(probe, ensure_ascii=False)
    assert probe["duration_delta_seconds"] <= 0.35
    assert probe["audio_stream_count"] == 1
    assert probe["width"] == probe["height"]
