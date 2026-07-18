from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

from services import frame_video_commercial as commercial
from services import frame_video_flow as flow
from services import frame_video_runtime as runtime
from services import video_flow6


ROOT = Path(__file__).resolve().parents[1]
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8")
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
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    row = bytes([0]) + bytes(rgb) * width
    raw = row * height
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _state(paths: list[Path], **overrides) -> dict:
    photos = [
        {
            "image_id": f"frame_{index:02d}",
            "file_id": str(path),
            "file_name": path.name,
            "mime_type": "image/png",
            "source": "telegram",
        }
        for index, path in enumerate(paths, start=1)
    ]
    return flow.normalize_state(
        {
            "photos": photos,
            "seconds_per_image": 0.5,
            "transition": "none",
            "motion": "none",
            "ratio": "1x1",
            "fit_mode": "contain",
            "quality": "fast",
            **overrides,
        }
    )


def test_image_quote_never_falls_back_to_free_and_regeneration_quotes_one_image() -> None:
    tier = {
        "enabled": True,
        "tier": "basic",
        "label": "Cơ bản",
        "model": "image-model",
        "cost": 25,
        "retry_warranty_count": 1,
    }
    batch = commercial.image_quote(tier, count=4, ratio="9x16", prompt="Bộ ảnh sản phẩm")
    assert batch["ok"] is True
    assert batch["image_count"] == 4
    assert batch["unit_price_xu"] == 25
    assert batch["total_price_xu"] == 100
    assert all(value == 0 for value in batch["side_effects"].values())

    regenerate = commercial.image_quote(
        tier,
        count=1,
        minimum_count=1,
        ratio="9x16",
        prompt="Tạo lại đúng ảnh này",
    )
    assert regenerate["image_count"] == 1
    assert regenerate["total_price_xu"] == 25

    for broken in (
        {**tier, "enabled": False},
        {**tier, "model": ""},
        {**tier, "cost": 0},
    ):
        quote = commercial.image_quote(broken, count=4, ratio="9x16", prompt="Ảnh")
        assert quote["ok"] is False
        assert quote["total_price_xu"] == max(0, int(broken.get("cost") or 0)) * 4


def test_image_receipts_require_real_delivery_and_charge_once() -> None:
    state = commercial.record_image_receipt(
        {},
        image_job_id=11,
        model="image-model",
        prompt="Ảnh 1",
        ratio="9:16",
        artifact="telegram:file-1",
        message_id=101,
        charged_xu=0,
        timestamp="now",
    )
    same = commercial.record_image_receipt(
        state,
        image_job_id=11,
        model="image-model",
        prompt="Ảnh 1",
        ratio="9:16",
        artifact="telegram:file-1",
        message_id=101,
        charged_xu=0,
        timestamp="later",
    )
    assert same == state
    with pytest.raises(ValueError, match="image_delivery_message_id_required"):
        commercial.record_image_receipt(
            {},
            image_job_id=12,
            model="image-model",
            prompt="Ảnh 2",
            ratio="9:16",
            artifact="telegram:file-2",
            message_id=0,
            charged_xu=0,
            timestamp="now",
        )
    with pytest.raises(ValueError, match="duplicate_image_delivery_message_id"):
        commercial.record_image_receipt(
            state,
            image_job_id=12,
            model="image-model",
            prompt="Ảnh 2",
            ratio="9:16",
            artifact="telegram:file-2",
            message_id=101,
            charged_xu=0,
            timestamp="now",
        )

    charged = commercial.apply_single_image_charge(
        state,
        image_job_id=11,
        message_id=101,
        charged_xu=25,
    )
    charged_again = commercial.apply_single_image_charge(
        charged,
        image_job_id=11,
        message_id=101,
        charged_xu=25,
    )
    assert charged["image_generation_charged_amount"] == 25
    assert charged["image_regeneration_charge_count"] == 1
    assert charged_again["image_regeneration_charge_count"] == 1
    assert charged_again["generated_image_receipts"][0]["charge_recorded"] is True


def test_batch_charge_is_idempotent_and_marks_each_delivery_receipt() -> None:
    state: dict = {}
    for job_id, message_id in ((21, 201), (22, 202), (23, 203)):
        state = commercial.record_image_receipt(
            state,
            image_job_id=job_id,
            model="image-model",
            prompt=f"Ảnh {job_id}",
            ratio="1:1",
            artifact=f"telegram:file-{job_id}",
            message_id=message_id,
            charged_xu=0,
            timestamp="now",
        )
    charged = commercial.apply_image_batch_charge(state, charged_xu=76)
    charged_again = commercial.apply_image_batch_charge(charged, charged_xu=999)
    assert sum(row["xu_charged"] for row in charged["generated_image_receipts"]) == 76
    assert all(row["charge_recorded"] for row in charged["generated_image_receipts"])
    assert charged_again["image_generation_charged_amount"] == 76


def test_generated_image_metadata_survives_manifest_normalization_and_replacement() -> None:
    original = runtime.canonical_image_manifest(
        [
            {
                "file_id": "telegram-file",
                "source": "generated",
                "prompt": "Ảnh sản phẩm",
                "model": "image-model",
                "tier": "basic",
                "ratio": "9:16",
                "image_job_id": 41,
                "delivery_message_id": 401,
                "receipt_key": "41:401",
            }
        ]
    )[0]
    assert original["source"] == "generated"
    assert original["prompt"] == "Ảnh sản phẩm"
    assert original["model"] == "image-model"
    assert original["tier"] == "basic"
    assert original["image_job_id"] == 41
    assert original["receipt_key"] == "41:401"

    replaced = runtime.manifest_replace(
        [original],
        original["image_id"],
        {
            "file_id": "replacement",
            "source": "generated",
            "prompt": "Ảnh thay thế",
            "model": "image-model-2",
            "tier": "quality",
            "ratio": "9:16",
            "image_job_id": 42,
            "delivery_message_id": 402,
            "receipt_key": "42:402",
        },
    )[0]
    assert replaced["image_id"] == original["image_id"]
    assert replaced["is_cover"] is True
    assert replaced["receipt_key"] == "42:402"
    assert replaced["model"] == "image-model-2"


def test_video_quote_and_preflight_are_nonzero_provider_free_and_owner_aware() -> None:
    state = flow.normalize_state(
        {
            "photos": [{"file_id": "one"}, {"file_id": "two"}],
            "seconds_per_image": 3,
            "quality": "balanced",
        }
    )
    quote = commercial.video_quote(
        state,
        {"base": 40, "addon_xu": 10, "music_xu": 5, "total": 55},
    )
    assert quote["ok"] is True
    assert quote["base_xu"] == 100
    assert quote["total_price_xu"] == 115
    assert quote["pricing_source"] == "frame_video_fixed_quality_promo_v1"
    assert quote["public_job_type"] == "frame_video_local"
    assert quote["mapped_job_type"] == "frame_video_render"

    worker = commercial.preflight(
        state,
        ffmpeg_path="",
        ffprobe_path="",
        worker_connected=True,
        output_writable=True,
        package_available=True,
    )
    assert worker["ok"] is True
    assert worker["execution_owner"] == "local_worker"
    assert all(value == 0 for value in worker["side_effects"].values())

    direct = commercial.preflight(
        state,
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        worker_connected=False,
        output_writable=True,
        package_available=True,
    )
    assert direct["ok"] is True
    assert direct["execution_owner"] == "local_ffmpeg"

    blocked = commercial.preflight(
        state,
        ffmpeg_path="",
        ffprobe_path="",
        worker_connected=False,
        output_writable=True,
        package_available=True,
    )
    assert blocked["ok"] is False
    assert "execution_owner_unavailable" in blocked["blockers"]


def test_route_matrix_and_source_lock_side_effects_to_explicit_confirm() -> None:
    required = {
        "image_receipt",
        "image_regenerate",
        "image_regenerate_confirm",
        "duration_menu",
        "addons",
        "audio_menu",
        "quality_menu",
        "continue",
        "confirm",
    }
    assert required <= set(flow.FRAME_VIDEO_ROUTE_MATRIX)
    assert flow.FRAME_VIDEO_ROUTE_MATRIX["image_regenerate_confirm"]["side_effect"] == "explicit_image_regenerate_confirm_only"
    assert video_flow6.EXECUTION_ROUTES["frame_video"]["mapped_job_type"] == "frame_video_render"

    image_confirm = BOT_SOURCE[BOT_SOURCE.index('    if action == "ai_generate_confirm":') :]
    image_confirm = image_confirm[: image_confirm.index('    if action == "ai_stitch_generated":')]
    assert "create_shopaikey_job" in image_confirm
    assert "shopaikey_image_generate" in image_confirm
    fresh_batch = image_confirm[image_confirm.index("quote = frame_video_image_quote(latest)") :]
    assert fresh_batch.index("send_frame_video_generated_image") < fresh_batch.index("spend_fixed_credit_info")
    assert "delivered_charge_pending" in image_confirm
    assert "Không tạo thêm ảnh" in image_confirm

    regeneration = BOT_SOURCE[
        BOT_SOURCE.index("async def handle_frame_video_image_regeneration") :
        BOT_SOURCE.index("async def handle_img2vid_lock1_callback")
    ]
    fresh_regeneration = regeneration[regeneration.index("submit_guard = shopaikey_provider_submit_guard") :]
    assert fresh_regeneration.index("send_frame_video_generated_image") < fresh_regeneration.index("spend_fixed_credit_info")
    assert "image_regeneration_pending" in regeneration
    assert "manifest_replace" in regeneration

    canonical = BOT_SOURCE[
        BOT_SOURCE.index("async def handle_frame_video_canonical_callback") :
        BOT_SOURCE.index("async def handle_frame_video_image_regeneration")
    ]
    before_confirm = canonical[: canonical.index('    if action == "confirm":')]
    assert "create_frame_video_job" not in before_confirm
    assert "spend_fixed_credit_info" not in before_confirm
    assert "shopaikey_image_generate" not in before_confirm


def test_review_and_guard_keep_image_invoice_separate_from_video_invoice() -> None:
    assert "Hóa đơn dựng MP4" in BOT_SOURCE
    assert "Phí ảnh AI đã giao được đối soát riêng và không cộng lại vào hóa đơn video" in BOT_SOURCE
    assert '"reason": "image_charge_pending"' in BOT_SOURCE
    assert "image_generation_unit_price" in BOT_SOURCE
    assert "Bấm lại chỉ thử đối soát, không tạo thêm ảnh" in BOT_SOURCE


def test_worker_contract_claims_canonical_job_and_charges_only_after_delivery() -> None:
    assert 'if job_type == "frame_video_render"' in WORKER_SOURCE
    assert "telegram_send_video_receipt" in WORKER_SOURCE
    assert "frame_video_delivery_receipt_missing" in WORKER_SOURCE
    assert '"charge_policy": "post_delivery"' in BOT_SOURCE
    assert '"mapped_job_type": frame_video_commercial.WORKER_JOB_TYPE' in BOT_SOURCE
    assert "handle_frame_video_worker_job_update" in BOT_SOURCE
    assert "frame_video_reconcile_charge_for_status" in BOT_SOURCE
    assert 'str(current.get("charge_state") or "") in {"not_charged", "charge_pending"}' in BOT_SOURCE

    final_confirm = BOT_SOURCE[
        BOT_SOURCE.index("async def handle_frame_video_final_confirm") :
        BOT_SOURCE.index("async def handle_frame_video_canonical_callback")
    ]
    assert final_confirm.index("context.bot.send_video") < final_confirm.index("frame_video_charge_after_delivery")
    assert "spend_fixed_credit_info" not in final_confirm

    public_callback = BOT_SOURCE[
        BOT_SOURCE.index("async def handle_frame_video_callback") :
        BOT_SOURCE.index("async def cmd_storyboard_video")
    ]
    assert "spend_fixed_credit_info" not in public_callback
    assert "refund_charged_credit" not in public_callback
    assert public_callback.count("return await handle_frame_video_final_confirm") == 1


@pytest.mark.parametrize("image_count", [2, 4, 10, 20])
def test_real_local_ffmpeg_builds_ordered_valid_mp4_for_supported_counts(tmp_path: Path, image_count: int) -> None:
    ffmpeg = _binary("ffmpeg")
    ffprobe = _binary("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg/ffprobe not available locally")

    paths: list[Path] = []
    for index in range(image_count):
        path = tmp_path / f"frame-{index:02d}.png"
        _write_png(path, ((index * 47) % 255, (index * 83) % 255, (index * 131) % 255))
        paths.append(path)
    output = tmp_path / f"frame-video-{image_count}.mp4"
    state = _state(paths)
    command = runtime.build_ffmpeg_command(
        [str(path) for path in paths],
        str(output),
        state,
        ffmpeg_path=ffmpeg,
    )
    ffmpeg_inputs = [command.command[index + 1] for index, token in enumerate(command.command[:-1]) if token == "-i"]
    assert ffmpeg_inputs[:image_count] == [str(path) for path in paths]
    assert "-shortest" not in command.command
    completed = subprocess.run(command.command, capture_output=True, text=True, timeout=180, check=False)
    assert completed.returncode == 0, completed.stderr[-3000:]
    probe = runtime.probe_mp4(str(output), command.expected_duration, False, ffprobe)
    assert probe["ok"], json.dumps(probe, ensure_ascii=False)
    assert probe["duration_delta_seconds"] <= 0.35
    assert probe["video_stream_count"] == 1
    assert probe["size_bytes"] > 0
