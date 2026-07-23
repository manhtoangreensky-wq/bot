from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import struct
import subprocess
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import local_worker
from services import frame_video_commercial as commercial
from services import frame_video_flow as flow
from services import frame_video_runtime as runtime


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
FLOW_UI_SOURCE = (ROOT / "video_image_to_video_flow.py").read_text(encoding="utf-8")
WORKER_SOURCE = (ROOT / "local_worker.py").read_text(encoding="utf-8")


def _binary(name: str) -> str:
    configured = os.environ.get(f"FRAME_VIDEO_{name.upper()}") or shutil.which(name)
    if configured:
        return configured
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    matches = list(root.glob(f"**/{name}.exe"))
    return str(matches[0]) if matches else ""


def _write_png(path: Path, rgb: tuple[int, int, int], width: int = 48, height: int = 32) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    raw = (bytes([0]) + bytes(rgb) * width) * height
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _state(paths: list[Path] | None = None, count: int = 0, **overrides) -> dict:
    photos = [
        {
            "image_id": f"frame_{index:02d}",
            "file_id": str(path),
            "file_name": path.name,
            "mime_type": "image/png",
            "source": "telegram",
        }
        for index, path in enumerate(paths or [], start=1)
    ]
    image_count = count or len(photos)
    return flow.normalize_state(
        {
            "commercial_flow_version": "framevideo3",
            "image_count": image_count,
            "ai_image_count": image_count or 2,
            "photos": photos,
            "seconds_per_image": 0.5,
            "duration_confirmed": True,
            "transition": "none",
            "motion": "none",
            "ratio": "1x1",
            "fit_mode": "contain",
            "quality": "fast",
            **overrides,
        }
    )


def _function_source(start_marker: str, end_marker: str) -> str:
    start = BOT_SOURCE.index(start_marker)
    end = BOT_SOURCE.index(end_marker, start)
    return BOT_SOURCE[start:end]


def test_public_entry_is_image_count_only_and_keeps_exact_source_order() -> None:
    assert "Sản phẩm này tính theo <b>số ảnh</b>, không dùng số cảnh" in FLOW_UI_SOURCE
    assert "📎 Gửi ảnh có sẵn" in FLOW_UI_SOURCE
    assert "✨ Tạo ảnh AI" in FLOW_UI_SOURCE
    assert "🗂️ Dùng ảnh đã lưu" in FLOW_UI_SOURCE
    assert "ℹ️ Cách hoạt động" in FLOW_UI_SOURCE
    assert 'callback_data="framevideo|source|uploaded"' in FLOW_UI_SOURCE
    assert 'callback_data="framevideo|source|ai"' in FLOW_UI_SOURCE
    assert 'callback_data="framevideo|source|saved"' in FLOW_UI_SOURCE
    assert "scene_count" not in FLOW_UI_SOURCE
    assert "profile" not in FLOW_UI_SOURCE.lower()


def test_count_ratio_and_ai_suggestion_keyboards_match_framevideo3_contract() -> None:
    for left, right in (("2 ảnh", "3 ảnh"), ("4 ảnh", "5 ảnh"), ("8 ảnh", "10 ảnh")):
        assert left in FLOW_UI_SOURCE and right in FLOW_UI_SOURCE
    assert "20 ảnh" in FLOW_UI_SOURCE
    assert "Dọc 9:16" in FLOW_UI_SOURCE
    assert "Ngang 16:9" in FLOW_UI_SOURCE
    assert "Vuông 1:1" in FLOW_UI_SOURCE
    assert "Dọc 4:5" in FLOW_UI_SOURCE
    assert "✍️ Tự nhập" in FLOW_UI_SOURCE
    assert "💡 Gợi ý phù hợp" not in FLOW_UI_SOURCE
    assert "for index in range(1, 6)" in FLOW_UI_SOURCE
    suggestion_bank = BOT_SOURCE[
        BOT_SOURCE.index("def quick_image_suggestion_bank") : BOT_SOURCE.index("def quick_image_prompt_from_topic")
    ]
    assert suggestion_bank.count('        "') >= 40


def test_ai_invoice_keeps_initial_image_count_and_video_price_cannot_fall_to_zero() -> None:
    keyboard_source = BOT_SOURCE[
        BOT_SOURCE.index("def img2vid_ai_confirm_keyboard") : BOT_SOURCE.index("def img2vid_generated_images_keyboard")
    ]
    assert 'framevideo3 = str((state or {}).get("commercial_flow_version")' in keyboard_source
    assert 'InlineKeyboardButton("🖼️ Prompt từng ảnh", callback_data="framevideo|ai_prompt_set")' in keyboard_source
    assert "if framevideo3" in keyboard_source

    state = _state(count=2)
    state["photos"] = runtime.canonical_image_manifest(
        [{"file_id": "local-image-1"}, {"file_id": "local-image-2"}]
    )
    fixed_package = commercial.video_quote(
        state,
        {"base": 0, "addon_xu": 0, "music_xu": 0, "total": 0, "free_trial_eligible": True},
    )
    assert fixed_package["ok"] is True
    assert fixed_package["base_xu"] == 50
    assert fixed_package["total_price_xu"] == 50
    assert fixed_package["pricing_source"] == "frame_video_fixed_quality_promo_v1"
    assert "free_trial_eligible" not in fixed_package

    ai_handler = BOT_SOURCE[
        BOT_SOURCE.index("async def handle_img2vid_lock1_callback") :
        BOT_SOURCE.index("async def handle_frame_video_callback")
    ]
    for action in ("ai_count_menu", "ai_count", "ai_count_custom"):
        branch = ai_handler[ai_handler.index(f'if action == "{action}"') :]
        assert "if is_frame_video3_state(state):" in branch[:1800]
    assert flow.FRAME_VIDEO_ROUTE_MATRIX["ai_first"]["owner"] == "handle_frame_video_callback"


def test_every_ai_image_has_one_editable_prompt_and_restore_is_scoped() -> None:
    state = _state(count=4, ai_prompt="Bộ ảnh nước hoa cao cấp")
    prompts = [f"Ảnh {index}/4: nội dung riêng {index}" for index in range(1, 5)]
    state = flow.set_ai_image_prompts(state, prompts)
    assert flow.ai_image_prompt_values(state) == prompts
    assert len(state["ai_image_prompts"]) == state["image_count"] == 4

    state = flow.update_ai_image_prompt(state, 3, "Ảnh 3/4: cận cảnh chai nước hoa")
    assert flow.ai_image_prompt_values(state)[2] == "Ảnh 3/4: cận cảnh chai nước hoa"
    assert flow.ai_image_prompt_values(state)[1] == prompts[1]
    state = flow.restore_ai_image_prompt(state, 3)
    assert flow.ai_image_prompt_values(state) == prompts
    with pytest.raises(ValueError, match="ai_image_prompt_count_mismatch"):
        flow.set_ai_image_prompts(state, prompts[:3])


def test_route_matrix_has_one_owner_and_exact_ai_back_stack() -> None:
    expected = {
        "ai_prompt",
        "ai_suggest",
        "ai_refresh",
        "ai_pick",
        "ai_prepared",
        "ai_prompt_set",
        "ai_prompt_image",
        "ai_prompt_image_edit",
        "ai_prompt_image_restore",
        "ai_prompt_regenerate",
        "ai_tier_menu",
        "ai_tier",
        "ai_generate_confirm",
    }
    assert expected <= set(flow.FRAME_VIDEO_ROUTE_MATRIX)
    for action in expected:
        route = flow.FRAME_VIDEO_ROUTE_MATRIX[action]
        assert route["owner"] == "handle_img2vid_lock1_callback"
        assert route["screen"]
        assert route["back"]
    assert flow.FRAME_VIDEO_ROUTE_MATRIX["ai_generate_confirm"]["side_effect"] == "explicit_image_confirm_only"
    assert flow.FRAME_VIDEO_ROUTE_MATRIX["duration_done"]["screen"] == "transition"
    assert flow.FRAME_VIDEO_ROUTE_MATRIX["motion_set"]["screen"] == "addons"
    assert flow.FRAME_VIDEO_ROUTE_MATRIX["continue"]["screen"] == "invoice"
    assert flow.FRAME_VIDEO_ROUTE_MATRIX["status"]["back"] == "invoice_or_review"
    assert flow.FRAME_VIDEO_ROUTE_MATRIX["status_back"]["screen"] == "invoice_or_review"


def test_all_public_framevideo_callbacks_are_catalogued_once_without_generic_x() -> None:
    callback_actions = set(
        re.findall(
            r"framevideo[|]([A-Za-z0-9_]+)",
            BOT_SOURCE + "\n" + FLOW_UI_SOURCE,
        )
    )
    canonical = set(flow.FRAME_VIDEO_ROUTE_MATRIX)
    legacy = set(flow.FRAME_VIDEO_LEGACY_ROUTE_MATRIX)
    assert canonical.isdisjoint(legacy)
    assert callback_actions <= canonical | legacy | {"hub", "menu", "main"}
    assert all(route.get("owner") and route.get("screen") and route.get("back") for route in flow.FRAME_VIDEO_ROUTE_MATRIX.values())
    assert BOT_SOURCE.count("CallbackQueryHandler(handle_frame_video_callback") == 1

    handler_source = _function_source(
        "async def handle_frame_video_callback",
        "async def cmd_storyboard_video",
    )
    assert "Có lỗi khi xử lý lệnh" not in handler_source
    assert '"assets_done", "panel"' in BOT_SOURCE
    assert "FRAME_VIDEO_IMG2VID_ACTIONS" in BOT_SOURCE
    assert "elif is_frame_video3_state(state):" in handler_source
    assert "frame_video3_current_screen(state, lang)" in handler_source


def test_assets_done_outer_callback_has_one_owner_and_opens_duration_once() -> None:
    handler_source = _function_source(
        "async def handle_frame_video_callback",
        "async def cmd_storyboard_video",
    )
    events: list[tuple[str, object]] = []

    async def fake_assets_done(query, context, uid, lang, state):
        events.append(("assets_done", {"uid": uid, "lang": lang, "state": dict(state)}))
        return "duration-panel"

    class Query:
        data = "framevideo|assets_done"
        from_user = SimpleNamespace(id=881)

        async def answer(self):
            events.append(("answer", None))

    namespace = {
        "get_user_language": lambda _uid: "vi",
        "get_frame_video_state": lambda _uid: {"commercial_flow_version": "framevideo3", "image_count": 2},
        "handle_frame_video_assets_done": fake_assets_done,
        "sanitize_log_text": str,
        "logger": SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    }
    exec("from __future__ import annotations\n" + handler_source, namespace)
    result = asyncio.run(namespace["handle_frame_video_callback"](SimpleNamespace(callback_query=Query()), SimpleNamespace()))
    assert result == "duration-panel"
    assert [event[0] for event in events] == ["answer", "assets_done"]


def test_assets_done_persists_duration_without_legacy_fallback() -> None:
    handler_source = _function_source(
        "async def handle_frame_video_assets_done",
        "def frame_video3_current_screen",
    )
    saved: list[dict] = []
    sent: list[dict] = []

    async def fake_edit(_query, text, **kwargs):
        sent.append({"text": text, **kwargs})
        return "duration-panel"

    namespace = {
        "normalize_frame_video_state": lambda state: dict(state),
        "_safe_int": lambda value, default=0: int(value or default),
        "frame_video_duration_menu_text": lambda _state: "duration",
        "frame_video_duration_menu_keyboard": lambda _single, _state: "duration-keyboard",
        "frame_video_collect_keyboard": lambda *_args, **_kwargs: "collect-keyboard",
        "set_frame_video_state": lambda _uid, state: saved.append(dict(state)),
        "safe_edit_or_send": fake_edit,
        "ivf": SimpleNamespace(
            frame_video_image_count_text=lambda *_args: "count",
            frame_video_image_count_keyboard=lambda *_args: "count-keyboard",
        ),
        "logger": SimpleNamespace(error=lambda *_args, **_kwargs: None, warning=lambda *_args, **_kwargs: None),
        "sanitize_log_text": str,
        "html": __import__("html"),
        "re": re,
    }
    exec("from __future__ import annotations\n" + handler_source, namespace)
    state = {"commercial_flow_version": "framevideo3", "image_count": 2, "photos": [{}, {}]}
    result = asyncio.run(
        namespace["handle_frame_video_assets_done"](
            SimpleNamespace(message=SimpleNamespace(chat_id=22)),
            SimpleNamespace(),
            881,
            "vi",
            state,
        )
    )
    assert result == "duration-panel"
    assert saved[-1]["step"] == "duration"
    assert len(sent) == 1
    assert sent[0]["text"] == "duration"
    assert sent[0]["reply_markup"] == "duration-keyboard"


def test_exact_image_count_blocks_partial_batch_and_builds_n_minus_one_transitions() -> None:
    partial = _state(count=4)
    partial["photos"] = runtime.canonical_image_manifest([{"file_id": "one"}, {"file_id": "two"}, {"file_id": "three"}])
    invalid = runtime.validate_plan(partial)
    assert invalid["ok"] is False
    assert "image_count_mismatch" in invalid["errors"]

    exact = _state(count=4)
    exact["photos"] = runtime.canonical_image_manifest([{"file_id": f"image-{index}"} for index in range(4)])
    exact["transition"] = "fade"
    valid = runtime.validate_plan(exact)
    assert valid["ok"] is True
    assert len(valid["config"]["transition_manifest"]) == 3
    assert [row["from_image_id"] for row in valid["config"]["transition_manifest"]] == [
        row["image_id"] for row in valid["manifest"][:-1]
    ]
    assert valid["manifest"][-1]["image_id"] not in {
        row["from_image_id"] for row in valid["config"]["transition_manifest"]
    }


def test_image_manager_preserves_stable_ids_order_cover_caption_and_duration() -> None:
    state = _state(count=4)
    state["photos"] = runtime.canonical_image_manifest([{"file_id": f"file-{index}"} for index in range(4)])
    ids = [row["image_id"] for row in state["photos"]]
    state = flow.apply_image_action(state, "select", ids[2])
    state = flow.apply_image_action(state, "up")
    assert [row["image_id"] for row in state["photos"]] == [ids[0], ids[2], ids[1], ids[3]]
    state = flow.update_selected_image(state, caption="Ảnh sản phẩm chính")
    assert flow.selected_image(state)["caption"] == "Ảnh sản phẩm chính"
    state = flow.set_selected_duration(state, 4.0)
    assert state["image_durations"][ids[2]] == 4.0
    state = flow.apply_image_action(state, "cover")
    assert next(row for row in state["photos"] if row["image_id"] == ids[2])["is_cover"] is True
    replacement = runtime.manifest_replace(state["photos"], ids[2], {"file_id": "replacement"})
    assert next(row for row in replacement if row["image_id"] == ids[2])["file_id"] == "replacement"


def test_receipt_and_charge_are_idempotent_and_follow_real_telegram_delivery() -> None:
    state = commercial.record_image_receipt(
        {},
        image_job_id=101,
        model="image-model",
        prompt="Ảnh 1/2",
        ratio="9:16",
        artifact="telegram:file-101",
        message_id=1001,
        charged_xu=0,
        timestamp="now",
    )
    same = commercial.record_image_receipt(
        state,
        image_job_id=101,
        model="image-model",
        prompt="Ảnh 1/2",
        ratio="9:16",
        artifact="telegram:file-101",
        message_id=1001,
        charged_xu=0,
        timestamp="later",
    )
    assert same == state
    charged = commercial.apply_image_batch_charge(state, charged_xu=25)
    charged_again = commercial.apply_image_batch_charge(charged, charged_xu=99)
    assert charged["image_generation_charged_amount"] == 25
    assert charged_again["image_generation_charged_amount"] == 25

    confirm = BOT_SOURCE[
        BOT_SOURCE.index("async def handle_frame_video_final_confirm") :
        BOT_SOURCE.index("async def handle_frame_video_canonical_callback")
    ]
    assert confirm.index("context.bot.send_video") < confirm.index("frame_video_charge_after_delivery")
    assert "delivery_message_id" in confirm
    assert '"charge_policy": "post_delivery"' in BOT_SOURCE


def test_provider_side_effects_exist_only_after_explicit_image_or_video_confirm() -> None:
    ai_handler = BOT_SOURCE[
        BOT_SOURCE.index("async def handle_img2vid_lock1_callback") :
        BOT_SOURCE.index("async def handle_frame_video_callback")
    ]
    before_image_confirm = ai_handler[: ai_handler.index('    if action == "ai_generate_confirm":')]
    assert "shopaikey_image_generate" not in before_image_confirm
    assert "create_shopaikey_job" not in before_image_confirm
    image_confirm = ai_handler[ai_handler.index('    if action == "ai_generate_confirm":') :]
    assert "prompts = frame_video_flow.ai_image_prompt_values(latest)" in image_confirm
    fresh_batch = image_confirm[image_confirm.index("quote = frame_video_image_quote(latest)") :]
    assert fresh_batch.index("send_frame_video_generated_image") < fresh_batch.index("spend_fixed_credit_info")

    canonical = BOT_SOURCE[
        BOT_SOURCE.index("async def handle_frame_video_canonical_callback") :
        BOT_SOURCE.index("async def handle_frame_video_image_regeneration")
    ]
    before_video_confirm = canonical[: canonical.index('    if action == "confirm":')]
    assert "create_frame_video_job" not in before_video_confirm
    assert "create_local_worker_job" not in before_video_confirm
    assert "shopaikey_image_generate" not in before_video_confirm
    assert 'if job_type == "frame_video_render"' in WORKER_SOURCE
    assert 'update_job(job_id, "failed", "image_count_mismatch")' in WORKER_SOURCE
    assert "image_count_mismatch_downloaded" in WORKER_SOURCE


def test_quality_screen_exposes_codec_route_price_eta_and_preflight_truth() -> None:
    quality_source = BOT_SOURCE[
        BOT_SOURCE.index("def frame_video_quality_text") : BOT_SOURCE.index("def frame_video_review_text")
    ]
    for token in ("Codec", "Tuyến dựng", "Trạng thái", "Giá dự kiến", "Thời gian", "preflight"):
        assert token in quality_source
    assert "So sánh các gói" not in quality_source
    state = _state(count=2)
    state["photos"] = runtime.canonical_image_manifest(
        [{"file_id": "local-image-1"}, {"file_id": "local-image-2"}]
    )
    quote = commercial.video_quote(state, {"base": 40, "addon_xu": 0, "music_xu": 0, "total": 40})
    assert quote["ok"] is True
    assert quote["mapped_job_type"] == "frame_video_render"
    preflight = commercial.preflight(
        state,
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        worker_connected=False,
        output_writable=True,
        package_available=True,
    )
    assert preflight["ok"] is True
    assert preflight["execution_owner"] == "local_ffmpeg"
    assert all(value == 0 for value in preflight["side_effects"].values())


def test_local_worker_renders_valid_mp4_and_records_one_delivery_receipt(tmp_path: Path, monkeypatch) -> None:
    ffmpeg = _binary("ffmpeg")
    ffprobe = _binary("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg/ffprobe not available locally")

    inputs = []
    for index, color in enumerate(((20, 80, 180), (180, 80, 20)), start=1):
        path = tmp_path / f"worker-input-{index}.png"
        _write_png(path, color)
        inputs.append(path)
    state = _state(inputs)
    updates: list[dict] = []
    deliveries: list[dict] = []
    real_probe = runtime.probe_mp4

    def fake_download(file_id: str, destination: str, **_kwargs) -> None:
        shutil.copyfile(file_id, destination)

    def fake_delivery(chat_id: str, output_path: str, caption: str, **_kwargs) -> dict:
        probe = real_probe(output_path, 1.0, False, ffprobe)
        assert probe["ok"], json.dumps(probe, ensure_ascii=False)
        deliveries.append({"chat_id": chat_id, "caption": caption, "probe": probe})
        return {"sent": True, "message_id": 19001, "file_id": "telegram-framevideo-mp4"}

    def fake_update(job_id, status, error_short="", output_url="", output_file_id="", **_kwargs) -> None:
        updates.append(
            {
                "job_id": job_id,
                "status": status,
                "error_short": error_short,
                "output_url": output_url,
                "output_file_id": output_file_id,
            }
        )

    monkeypatch.setattr(local_worker, "telegram_download_file", fake_download)
    monkeypatch.setattr(local_worker, "telegram_send_video_receipt", fake_delivery)
    monkeypatch.setattr(local_worker, "update_job", fake_update)
    monkeypatch.setattr(local_worker, "local_ffmpeg_path", lambda: ffmpeg)
    monkeypatch.setattr(
        local_worker.frame_video_runtime,
        "probe_mp4",
        lambda path, expected_duration, expects_audio: real_probe(path, expected_duration, expects_audio, ffprobe),
    )

    payload = {
        "chat_id": "test-chat",
        "photos": [{"file_id": str(path)} for path in inputs],
        "state": state,
        "image_count": 2,
        "caption": "FrameVideo worker smoke",
        "max_render_seconds": 120,
    }
    local_worker.run_frame_video_render({"id": 551, "input_file_id": json.dumps(payload)})

    assert len(deliveries) == 1
    assert updates[-1]["status"] == "succeeded"
    receipt = json.loads(updates[-1]["output_url"])
    assert receipt["delivery_message_id"] == "19001"
    assert receipt["charge_policy"] == "post_delivery"
    assert receipt["wallet_charge_amount_xu"] == 0
    assert receipt["ffprobe"]["ok"] is True
    assert receipt["ffprobe"]["video_stream_count"] == 1


@pytest.mark.parametrize("image_count", [2, 4, 10, 20])
def test_real_local_mp4_for_every_supported_count(tmp_path: Path, image_count: int) -> None:
    ffmpeg = _binary("ffmpeg")
    ffprobe = _binary("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg/ffprobe not available locally")

    paths: list[Path] = []
    for index in range(image_count):
        path = tmp_path / f"frame-{index:02d}.png"
        _write_png(path, ((index * 43) % 255, (index * 79) % 255, (index * 127) % 255))
        paths.append(path)
    output = tmp_path / f"framevideo3-{image_count}.mp4"
    state = _state(paths)
    command = runtime.build_ffmpeg_command([str(path) for path in paths], str(output), state, ffmpeg_path=ffmpeg)
    inputs = [command.command[index + 1] for index, token in enumerate(command.command[:-1]) if token == "-i"]
    assert inputs[:image_count] == [str(path) for path in paths]
    completed = subprocess.run(command.command, capture_output=True, text=True, timeout=180, check=False)
    assert completed.returncode == 0, completed.stderr[-3000:]
    probe = runtime.probe_mp4(str(output), command.expected_duration, False, ffprobe)
    assert probe["ok"], json.dumps(probe, ensure_ascii=False)
    assert probe["duration_delta_seconds"] <= 0.35
    assert probe["video_stream_count"] == 1
    assert probe["size_bytes"] > 0
