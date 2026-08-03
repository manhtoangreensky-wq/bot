from __future__ import annotations

import asyncio
import inspect
import importlib.util
import json
import os
import re
import shutil
import struct
import zlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import local_worker
import pytest
from services import frame_video_public_seam as seam
from services import product_progress_status as progress


REPO_ROOT = Path(__file__).resolve().parents[1]


def _function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    starts = [f"async def {name}", f"def {name}"]
    start = min((source.find(marker) for marker in starts if source.find(marker) >= 0), default=-1)
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


def _write_png(path: Path, rgb: tuple[int, int, int]) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    width, height = 48, 32
    raw = (bytes([0]) + bytes(rgb) * width) * height
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def test_29o_frame_public_seam_module_exists() -> None:
    assert importlib.util.find_spec("services.frame_video_public_seam") is not None


def _delivered_frame_progress_job() -> dict:
    return {
        "job_id": "fv17857497320001",
        "status": "completed",
        "progress_percent": 100,
        "image_count": 8,
        "output_size_bytes": 1_303_632,
        "output_sha256": "a" * 64,
        "delivery_status": "sent",
        "delivery_message_id": "29001",
        "delivery_file_id": "frame-file-id-must-not-leak",
        "receipt_recorded": 1,
        "charge_state": "charged",
        "charge_amount_planned_xu": 0,
        "wallet_charge_amount_xu": 0,
        "delivered_at": "2026-08-03 09:35:58",
        "ffprobe": {
            "ok": True,
            "full_decode": True,
            "duration_seconds": 40.52,
            "size_bytes": 1_303_632,
            "video_stream_count": 1,
            "audio_stream_count": 0,
            "video_codec": "h264",
            "width": 1080,
            "height": 1920,
            "artifact_sha256": "a" * 64,
        },
    }


def test_29o_delivered_worker_receipt_renders_full_green_terminal() -> None:
    state = progress.product_progress_stage_from_job(
        "frame_video",
        _delivered_frame_progress_job(),
    )

    assert state["terminal_state"] == "delivered"
    assert state["current_stage"] == "delivered"
    assert state["percent"] == 100


def test_29o_delivered_frame_panel_has_safe_complete_receipt() -> None:
    renderer = getattr(progress, "frame_video_terminal_receipt_summary", None)
    assert callable(renderer)

    text = renderer(
        _delivered_frame_progress_job(),
        lang="vi",
        account_balance_xu=9_876,
    )
    assert "🧾 <b>Chi tiết kết quả</b>" in text
    assert "8 ảnh" in text
    assert "41 giây" in text
    assert "1080 × 1920" in text
    assert "1.2 MB" in text
    assert "MP4 · H.264" in text
    assert "9.876 Xu" in text
    assert "Đã gửi video" in text
    assert "frame-file-id-must-not-leak" not in text
    assert "worker" not in text.lower()
    status_source = _function_source(
        REPO_ROOT / "bot.py",
        "product_progress_status_from_job_text",
    )
    assert "frame_video_terminal_receipt_summary" in status_source


def test_29o_terminal_receipt_balance_lookup_is_read_only() -> None:
    status_source = _function_source(
        REPO_ROOT / "bot.py",
        "product_progress_status_from_job_text",
    )

    assert "db_connect_readonly()" in status_source
    assert "get_user(" not in status_source


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("receipt_recorded", 0),
        ("delivery_file_id", ""),
        ("charge_state", "charge_pending"),
        ("output_size_bytes", 1_303_633),
        ("output_sha256", "b" * 64),
        ("ffprobe.full_decode", False),
    ),
)
def test_29o_frame_terminal_panel_fails_closed_without_complete_receipt(
    field: str,
    value: object,
) -> None:
    job = _delivered_frame_progress_job()
    if field.startswith("ffprobe."):
        job["ffprobe"][field.split(".", 1)[1]] = value
    else:
        job[field] = value

    state = progress.product_progress_stage_from_job("frame_video", job)
    assert state["terminal_state"] != "delivered"
    assert progress.frame_video_terminal_receipt_summary(job) == ""


def test_29o_public_seam_is_default_off_and_final_only() -> None:
    assert seam.FRAME_VIDEO_PUBLIC_SEAM_FLAG == "FRAME_VIDEO_DURABLE_PUBLIC_SEAM_ENABLED"
    assert seam.frame_video_public_seam_enabled({}) is False
    assert seam.frame_video_public_seam_enabled(
        {seam.FRAME_VIDEO_PUBLIC_SEAM_FLAG: "1"}
    ) is True
    assert seam.frame_video_public_seam_applies_to_worker_job({"paid_preview": True}) is False
    assert seam.frame_video_public_seam_applies_to_worker_job(
        {"frame_video_durable_public_seam": True, "paid_preview": True}
    ) is False
    assert seam.frame_video_public_seam_applies_to_worker_job(
        {"frame_video_durable_public_seam": True}
    ) is True


def test_29o_worker_queue_admission_requires_exact_sha_and_flag_snapshot() -> None:
    admission = getattr(seam, "frame_video_worker_queue_admission", None)
    assert callable(admission)
    environ = {
        seam.FRAME_VIDEO_PUBLIC_SEAM_FLAG: "1",
        "FRAME_VIDEO_ENGINE_ENABLED": "1",
        "FRAME_VIDEO_PUBLIC_ALLOWED": "1",
        "FRAME_VIDEO_AUTO_RETRY": "0",
        "FRAME_VIDEO_AUTO_FALLBACK": "0",
    }
    expected_flags = {
        seam.FRAME_VIDEO_PUBLIC_SEAM_FLAG: True,
        "FRAME_VIDEO_ENGINE_ENABLED": True,
        "FRAME_VIDEO_PUBLIC_ALLOWED": True,
        "FRAME_VIDEO_AUTO_RETRY": False,
        "FRAME_VIDEO_AUTO_FALLBACK": False,
    }
    worker = {
        "worker_sha": "a" * 40,
        "frame_video_engine_flags": expected_flags,
    }

    assert admission(worker, expected_worker_sha="a" * 40, environ=environ)["ok"] is True
    assert admission(
        {**worker, "worker_sha": "b" * 40},
        expected_worker_sha="a" * 40,
        environ=environ,
    )["blocker"] == "worker_sha_mismatch"
    assert admission(
        {
            **worker,
            "frame_video_engine_flags": {
                **expected_flags,
                "FRAME_VIDEO_PUBLIC_ALLOWED": False,
            },
        },
        expected_worker_sha="a" * 40,
        environ=environ,
    )["blocker"] == "worker_engine_flags_mismatch"


def test_29o_frame_worker_transition_binds_to_claimed_worker() -> None:
    transition = getattr(seam, "frame_video_worker_transition_blocker", None)
    assert callable(transition)
    previous = {
        "job_type": "frame_video_render",
        "status": "running",
        "worker_id": "frame-worker-29o",
    }
    assert transition(previous, "succeeded", "frame-worker-29o") == ""
    assert (
        transition(previous, "succeeded", "different-worker")
        == "frame_worker_identity_mismatch"
    )
    assert (
        transition({**previous, "status": "queued"}, "succeeded", "frame-worker-29o")
        == "frame_worker_transition_invalid"
    )


def test_29o_terminal_attestation_requires_worker_and_artifact_truth() -> None:
    validator = getattr(seam, "validate_frame_video_worker_terminal", None)
    assert callable(validator)
    assert "expected_local_worker_job_id" in inspect.signature(validator).parameters
    expected_sha = "a" * 40
    payload = {
        "frame_video_durable_public_seam": True,
        "frame_video_expected_worker_sha": expected_sha,
        "frame_job_id": "fv-attested-29o",
    }
    receipt = {
        "frame_job_id": "fv-attested-29o",
        "local_worker_job_id": "29001",
        "worker_id": "frame-worker-29o",
        "worker_sha": expected_sha,
        "delivery_message_id": "29001",
        "delivery_file_id": "frame-file",
        "output_size_bytes": 4096,
        "output_sha256": "b" * 64,
        "ffprobe": {
            "ok": True,
            "full_decode": True,
            "reason": "ok",
            "duration_seconds": 1.2,
            "size_bytes": 4096,
            "video_stream_count": 1,
            "audio_stream_count": 0,
            "video_codec": "h264",
            "width": 640,
            "height": 480,
            "artifact_sha256": "b" * 64,
        },
    }

    valid = validator(
        payload,
        receipt,
        admitted_worker_id="frame-worker-29o",
        reported_worker_id="frame-worker-29o",
        expected_local_worker_job_id="29001",
    )
    assert valid["ok"] is True
    assert validator(
        payload,
        {**receipt, "worker_sha": "c" * 40},
        admitted_worker_id="frame-worker-29o",
        reported_worker_id="frame-worker-29o",
        expected_local_worker_job_id="29001",
    )["blocker"] == "worker_sha_mismatch"
    assert validator(
        payload,
        {**receipt, "output_sha256": "not-a-digest"},
        admitted_worker_id="frame-worker-29o",
        reported_worker_id="frame-worker-29o",
        expected_local_worker_job_id="29001",
    )["blocker"] == "frame_output_digest_invalid"
    assert validator(
        payload,
        {**receipt, "ffprobe": {**receipt["ffprobe"], "full_decode": False}},
        admitted_worker_id="frame-worker-29o",
        reported_worker_id="frame-worker-29o",
        expected_local_worker_job_id="29001",
    )["blocker"] == "frame_full_decode_missing"
    assert validator(
        payload,
        {**receipt, "frame_job_id": "fv-replayed-from-other-job"},
        admitted_worker_id="frame-worker-29o",
        reported_worker_id="frame-worker-29o",
        expected_local_worker_job_id="29001",
    )["blocker"] == "frame_job_id_mismatch"
    assert validator(
        payload,
        {key: value for key, value in receipt.items() if key != "frame_job_id"},
        admitted_worker_id="frame-worker-29o",
        reported_worker_id="frame-worker-29o",
        expected_local_worker_job_id="29001",
    )["blocker"] == "frame_job_id_mismatch"
    assert validator(
        payload,
        {**receipt, "local_worker_job_id": "29002"},
        admitted_worker_id="frame-worker-29o",
        reported_worker_id="frame-worker-29o",
        expected_local_worker_job_id="29001",
    )["blocker"] == "local_worker_job_id_mismatch"
    assert validator(
        payload,
        {key: value for key, value in receipt.items() if key != "local_worker_job_id"},
        admitted_worker_id="frame-worker-29o",
        reported_worker_id="frame-worker-29o",
        expected_local_worker_job_id="29001",
    )["blocker"] == "local_worker_job_id_mismatch"
    assert validator(
        payload,
        {**receipt, "delivery_message_id": "not-a-message-id"},
        admitted_worker_id="frame-worker-29o",
        reported_worker_id="frame-worker-29o",
        expected_local_worker_job_id="29001",
    )["blocker"] == "delivery_message_id_invalid"
    assert validator(
        payload,
        {key: value for key, value in receipt.items() if key != "delivery_file_id"},
        admitted_worker_id="frame-worker-29o",
        reported_worker_id="frame-worker-29o",
        expected_local_worker_job_id="29001",
    )["blocker"] == "delivery_file_id_missing"


def test_29o_terminal_attestation_rejects_non_finite_probe_metrics() -> None:
    expected_sha = "a" * 40
    payload = {
        "frame_video_durable_public_seam": True,
        "frame_video_expected_worker_sha": expected_sha,
        "frame_job_id": "fv-finite-probe-29o",
    }
    receipt = {
        "frame_job_id": "fv-finite-probe-29o",
        "local_worker_job_id": "29001",
        "worker_id": "frame-worker-29o",
        "worker_sha": expected_sha,
        "delivery_message_id": "29001",
        "delivery_file_id": "frame-file",
        "output_size_bytes": 4096,
        "output_sha256": "b" * 64,
        "ffprobe": {
            "ok": True,
            "full_decode": True,
            "duration_seconds": float("inf"),
            "size_bytes": 4096,
            "video_stream_count": 1,
            "audio_stream_count": 0,
            "video_codec": "h264",
            "width": 640,
            "height": 480,
            "artifact_sha256": "b" * 64,
        },
    }

    result = seam.validate_frame_video_worker_terminal(
        payload,
        receipt,
        admitted_worker_id="frame-worker-29o",
        reported_worker_id="frame-worker-29o",
        expected_local_worker_job_id="29001",
    )

    assert result["ok"] is False
    assert result["blocker"] == "frame_duration_invalid"


def test_29o_delivery_receipt_contract_is_shared_by_direct_and_worker_paths() -> None:
    validator = getattr(seam, "frame_video_delivery_receipt_blocker", None)
    assert callable(validator)
    assert validator("29001", "frame-file") == ""
    assert validator("0", "frame-file") == "delivery_message_id_invalid"
    assert validator("not-a-number", "frame-file") == "delivery_message_id_invalid"
    assert validator("29001", "") == "delivery_file_id_missing"

    confirm_source = _function_source(
        REPO_ROOT / "bot.py", "handle_frame_video_final_confirm"
    )
    assert "frame_video_delivery_receipt_blocker" in confirm_source
    worker_source = _function_source(
        REPO_ROOT / "local_worker.py", "run_frame_video_render"
    )
    assert "frame_video_delivery_receipt_blocker" in worker_source


def test_29o_worker_terminal_receipt_is_compact_and_not_path_bearing() -> None:
    builder = getattr(seam, "build_frame_video_worker_terminal_receipt", None)
    assert callable(builder)
    builder_parameters = inspect.signature(builder).parameters
    assert "frame_job_id" in builder_parameters
    assert "local_worker_job_id" in builder_parameters
    receipt = builder(
        frame_job_id="fv-attested-29o",
        local_worker_job_id="29001",
        delivery_message_id="29001",
        delivery_file_id="frame-file",
        output_size_bytes=4096,
        output_sha256="d" * 64,
        worker_id="frame-worker-29o",
        worker_sha="a" * 40,
        probe={
            "ok": True,
            "full_decode": True,
            "reason": "C:/private/reason/output.mp4",
            "duration_seconds": 1.2,
            "expected_duration_seconds": 1.2,
            "duration_delta_seconds": 0.0,
            "size_bytes": 4096,
            "video_stream_count": 1,
            "audio_stream_count": 0,
            "video_codec": "h264",
            "width": 640,
            "height": 480,
            "artifact_sha256": "d" * 64,
            "frame_fingerprints": [str(index) * 64 for index in range(1, 21)],
            "ffprobe_command": ["C:/private/ffprobe.exe", "private-output.mp4"],
        },
    )
    encoded = json.dumps(receipt, ensure_ascii=True, separators=(",", ":"))

    assert len(encoded.encode("utf-8")) < 1000
    assert "frame_fingerprints" not in encoded
    assert "ffprobe_command" not in encoded
    assert "private-output" not in encoded
    assert "private/reason" not in encoded


def test_29o_direct_terminal_receipt_probe_storage_is_path_free() -> None:
    compactor = getattr(seam, "compact_frame_video_probe", None)
    assert callable(compactor)
    compact = compactor(
        {
            "ok": True,
            "full_decode": True,
            "reason": "C:/private/reason/output.mp4",
            "duration_seconds": 1.2,
            "expected_duration_seconds": 1.2,
            "duration_delta_seconds": 0.0,
            "size_bytes": 4096,
            "video_stream_count": 1,
            "audio_stream_count": 0,
            "video_codec": "h264",
            "width": 640,
            "height": 480,
            "artifact_sha256": "e" * 64,
            "frame_fingerprints": ["f" * 64],
            "ffprobe_command": ["C:/private/ffprobe.exe", "C:/private/output.mp4"],
        }
    )
    encoded = json.dumps(compact, ensure_ascii=True, separators=(",", ":"))

    assert compact["ok"] is True
    assert compact["full_decode"] is True
    assert "frame_fingerprints" not in encoded
    assert "ffprobe_command" not in encoded
    assert "C:/private" not in encoded

    confirm_source = _function_source(
        REPO_ROOT / "bot.py", "handle_frame_video_final_confirm"
    )
    assert "compact_frame_video_probe" in confirm_source


@pytest.mark.parametrize(
    "field",
    ("duration_seconds", "expected_duration_seconds", "duration_delta_seconds"),
)
def test_29o_compact_probe_never_persists_non_finite_numbers(field: str) -> None:
    compactor = getattr(seam, "compact_frame_video_probe", None)
    assert callable(compactor)
    probe = {
        "ok": True,
        "full_decode": True,
        "reason": "ok",
        "duration_seconds": 1.2,
        "expected_duration_seconds": 1.2,
        "duration_delta_seconds": 0.0,
        "size_bytes": 4096,
        "video_stream_count": 1,
        "audio_stream_count": 0,
        "video_codec": "h264",
        "width": 640,
        "height": 480,
        "artifact_sha256": "e" * 64,
        field: float("inf"),
    }

    compact = compactor(probe)

    assert compact[field] == 0.0
    json.dumps(compact, ensure_ascii=True, allow_nan=False)


def test_29o_public_plan_preserves_order_and_audio_logo_identity(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    music = tmp_path / "music.wav"
    voice = tmp_path / "voice.wav"
    logo = tmp_path / "logo.png"
    _write_png(first, (220, 40, 40))
    _write_png(second, (40, 220, 40))
    music.write_bytes(b"music-fixture")
    voice.write_bytes(b"voice-fixture")
    _write_png(logo, (20, 20, 20),)
    state = {
        "photos": [
            {"image_id": "fvimg_frame_a", "file_id": "one"},
            {"image_id": "fvimg_frame_b", "file_id": "two"},
        ],
        "image_durations": {"fvimg_frame_a": 0.8, "fvimg_frame_b": 0.8},
        "seconds_per_image": 0.8,
        "image_motions": {"fvimg_frame_a": "zoom_in", "fvimg_frame_b": "none"},
        "ratio": "16x9",
        "transition": "fade",
        "transition_seconds": 0.1,
        "quality": "fast",
        "fit_mode": "crop",
        "watermark_text": "demo",
        "logo_position": "top_right",
    }
    plan = seam.build_frame_video_public_plan(
        state,
        [str(first), str(second)],
        music_path=str(music),
        voice_path=str(voice),
        logo_path=str(logo),
    )
    assert plan.mode == "multi_scene"
    assert [frame.asset_id for frame in plan.frames] == ["fvimg_frame_a", "fvimg_frame_b"]
    assert [frame.frame_index for frame in plan.frames] == [1, 2]
    assert [frame.duration_seconds for frame in plan.frames] == [0.8, 0.8]
    assert plan.aspect_ratio == "16:9"
    assert len(plan.transition_manifest) == 1
    assert plan.plan_sha256
    assert plan.audio_policy["promised"] is True
    assert {item["kind"] for item in plan.audio_policy["components"]} == {"music", "voice"}
    metadata = [item for item in plan.text_overlays if item.get("kind") == "frame_public_runtime_contract"]
    assert len(metadata) == 1
    assert metadata[0]["logo_sha256"]


def test_29o_public_plan_preserves_custom_dimensions(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    _write_png(first, (220, 40, 40))
    _write_png(second, (40, 220, 40))
    state = {
        "photos": [
            {"image_id": "fvimg_frame_a", "file_id": "one"},
            {"image_id": "fvimg_frame_b", "file_id": "two"},
        ],
        "seconds_per_image": 0.6,
        "transition": "none",
        "ratio": "custom",
        "custom_width": 640,
        "custom_height": 480,
    }
    plan = seam.build_frame_video_public_plan(
        state,
        [str(first), str(second)],
    )
    assert plan.aspect_ratio == "custom"
    assert plan.custom_width == 640
    assert plan.custom_height == 480


@pytest.mark.parametrize("field", ["custom_width", "custom_height"])
def test_29o_public_plan_rejects_non_finite_custom_dimensions(
    tmp_path: Path,
    field: str,
) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    _write_png(first, (220, 40, 40))
    _write_png(second, (40, 220, 40))
    state = {
        "photos": [
            {"image_id": "fvimg_frame_a", "file_id": "one"},
            {"image_id": "fvimg_frame_b", "file_id": "two"},
        ],
        "seconds_per_image": 0.6,
        "transition": "none",
        "ratio": "custom",
        "custom_width": 640,
        "custom_height": 480,
        field: float("inf"),
    }

    with pytest.raises(ValueError, match="frame_custom_dimensions_invalid"):
        seam.build_frame_video_public_plan(
            state,
            [str(first), str(second)],
        )


@pytest.mark.parametrize(
    ("field", "value", "blocker"),
    [
        ("seconds_per_image", float("nan"), "frame_duration_invalid"),
        ("seconds_per_image", float("inf"), "frame_duration_invalid"),
        ("transition_seconds", float("nan"), "frame_transition_duration_invalid"),
        ("transition_seconds", float("inf"), "frame_transition_duration_invalid"),
    ],
)
def test_29o_public_plan_rejects_non_finite_timeline_state(
    tmp_path: Path,
    field: str,
    value: float,
    blocker: str,
) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    _write_png(first, (220, 40, 40))
    _write_png(second, (40, 220, 40))
    state = {
        "photos": [
            {"image_id": "fvimg_frame_a", "file_id": "one"},
            {"image_id": "fvimg_frame_b", "file_id": "two"},
        ],
        "seconds_per_image": 0.8,
        "transition": "fade",
        "transition_seconds": 0.1,
        "ratio": "16x9",
        field: value,
    }

    with pytest.raises(ValueError, match=blocker):
        seam.build_frame_video_public_plan(
            state,
            [str(first), str(second)],
        )


def test_29o_public_plan_rejects_non_finite_per_frame_duration(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    _write_png(first, (220, 40, 40))
    _write_png(second, (40, 220, 40))
    state = {
        "photos": [
            {"image_id": "fvimg_frame_a", "file_id": "one"},
            {"image_id": "fvimg_frame_b", "file_id": "two"},
        ],
        "image_durations": {"fvimg_frame_a": float("inf")},
        "seconds_per_image": 0.8,
        "transition": "none",
        "ratio": "16x9",
    }

    with pytest.raises(ValueError, match="frame_duration_invalid"):
        seam.build_frame_video_public_plan(
            state,
            [str(first), str(second)],
        )


@pytest.mark.parametrize(
    ("field", "value", "blocker"),
    [
        ("frame_duration", float("nan"), "frame_duration_invalid"),
        ("frame_duration", float("inf"), "frame_duration_invalid"),
        ("frame_index", float("inf"), "frame_order_invalid"),
        ("transition_seconds", float("nan"), "frame_transition_duration_invalid"),
        ("transition_seconds", float("inf"), "frame_transition_duration_invalid"),
    ],
)
def test_29o_engine_rejects_non_finite_plan_numbers(
    tmp_path: Path,
    field: str,
    value: float,
    blocker: str,
) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    _write_png(first, (220, 40, 40))
    _write_png(second, (40, 220, 40))
    frames = [
        {
            "frame_index": 1,
            "asset_id": "fvimg_frame_a",
            "source_path": str(first),
            "duration_seconds": 0.8,
            "motion": "none",
        },
        {
            "frame_index": 2,
            "asset_id": "fvimg_frame_b",
            "source_path": str(second),
            "duration_seconds": 0.8,
            "motion": "none",
        },
    ]
    transition_seconds = 0.1
    if field == "frame_duration":
        frames[0]["duration_seconds"] = value
    elif field == "frame_index":
        frames[0]["frame_index"] = value
    else:
        transition_seconds = value

    with pytest.raises(ValueError, match=blocker):
        seam.frame_video_engine.compile_frame_video_plan(
            frames=frames,
            mode="multi_scene",
            transition="fade",
            transition_seconds=transition_seconds,
        )


@pytest.mark.parametrize(
    ("field", "value", "blocker"),
    [
        ("music_volume_percent", float("nan"), "music_volume_invalid"),
        ("music_volume_percent", float("inf"), "music_volume_invalid"),
        ("music_fade_seconds", float("nan"), "music_fade_invalid"),
        ("music_fade_seconds", float("inf"), "music_fade_invalid"),
    ],
)
def test_29o_public_plan_rejects_non_finite_audio_policy(
    tmp_path: Path,
    field: str,
    value: float,
    blocker: str,
) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    music = tmp_path / "music.wav"
    _write_png(first, (220, 40, 40))
    _write_png(second, (40, 220, 40))
    music.write_bytes(b"music-fixture")
    state = {
        "photos": [
            {"image_id": "fvimg_frame_a", "file_id": "one"},
            {"image_id": "fvimg_frame_b", "file_id": "two"},
        ],
        "seconds_per_image": 0.8,
        "transition": "none",
        "ratio": "16x9",
        field: value,
    }

    with pytest.raises(ValueError, match=blocker):
        seam.build_frame_video_public_plan(
            state,
            [str(first), str(second)],
            music_path=str(music),
        )


def test_29o_public_plan_rejects_missing_promised_audio_asset(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    _write_png(first, (220, 40, 40))
    _write_png(second, (40, 220, 40))
    state = {
        "photos": [
            {"image_id": "fvimg_frame_a", "file_id": "one"},
            {"image_id": "fvimg_frame_b", "file_id": "two"},
        ],
        "voice_enabled": True,
        "voice_file_id": "voice-file",
        "seconds_per_image": 0.6,
        "transition": "none",
        "ratio": "1x1",
    }
    import pytest

    with pytest.raises(ValueError, match="voice_asset_missing"):
        seam.build_frame_video_public_plan(state, [str(first), str(second)])


def test_29o_render_default_off_is_legacy_passthrough_without_side_effect(tmp_path: Path) -> None:
    result = seam.render_frame_video_public(
        state={},
        image_paths=[],
        output_path=str(tmp_path / "out.mp4"),
        user_id=172203,
        confirmation_id="frame-job-off",
        language="vi",
        runtime_sha="a" * 40,
        expected_worker_sha="a" * 40,
        environ={},
    )
    assert result["enabled"] is False
    assert result["legacy_passthrough"] is True
    assert result["engine_jobs"] == 0
    assert result["provider_calls"] == 0
    assert result["wallet_mutations"] == 0
    assert not (tmp_path / "out.mp4").exists()


def test_29o_enabled_render_fails_closed_on_worker_sha_mismatch(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    _write_png(first, (220, 40, 40))
    _write_png(second, (40, 220, 40))
    state = {
        "photos": [
            {"image_id": "fvimg_frame_a", "file_id": "one"},
            {"image_id": "fvimg_frame_b", "file_id": "two"},
        ],
        "seconds_per_image": 0.6,
        "transition": "none",
        "ratio": "1x1",
    }
    environ = {
        seam.FRAME_VIDEO_PUBLIC_SEAM_FLAG: "1",
        "FRAME_VIDEO_ENGINE_ENABLED": "1",
        "FRAME_VIDEO_PUBLIC_ALLOWED": "1",
        "FRAME_VIDEO_AUTO_RETRY": "0",
        "FRAME_VIDEO_AUTO_FALLBACK": "0",
    }
    result = seam.render_frame_video_public(
        state=state,
        image_paths=[str(first), str(second)],
        output_path=str(tmp_path / "out.mp4"),
        user_id=172203,
        confirmation_id="frame-job-sha",
        language="vi",
        runtime_sha="a" * 40,
        expected_worker_sha="a" * 40,
        worker_sha="b" * 40,
        environ=environ,
    )
    assert result["ok"] is False
    assert result["blocker"] == "worker_sha_mismatch"
    assert result["engine_jobs"] == 0
    assert result["provider_calls"] == 0
    assert result["wallet_mutations"] == 0
    assert not (tmp_path / "out.mp4").exists()


def test_29o_enabled_render_returns_truthful_failure_for_invalid_plan(tmp_path: Path) -> None:
    environ = {
        seam.FRAME_VIDEO_PUBLIC_SEAM_FLAG: "1",
        "FRAME_VIDEO_ENGINE_ENABLED": "1",
        "FRAME_VIDEO_PUBLIC_ALLOWED": "1",
        "FRAME_VIDEO_AUTO_RETRY": "0",
        "FRAME_VIDEO_AUTO_FALLBACK": "0",
    }
    result = seam.render_frame_video_public(
        state={},
        image_paths=[],
        output_path=str(tmp_path / "out.mp4"),
        user_id=172203,
        confirmation_id="frame-job-invalid-plan",
        language="vi",
        runtime_sha="a" * 40,
        expected_worker_sha="a" * 40,
        environ=environ,
    )
    assert result["ok"] is False
    assert result["blocker"] == "not_enough_images"
    assert result["engine_jobs"] == 0
    assert result["provider_calls"] == 0
    assert result["wallet_mutations"] == 0
    assert not (tmp_path / "out.mp4").exists()


def test_29o_enabled_render_creates_one_valid_mp4_without_provider(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        import pytest

        pytest.skip("ffmpeg/ffprobe are required")
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    _write_png(first, (220, 40, 40))
    _write_png(second, (40, 220, 40))
    state = {
        "photos": [
            {"image_id": "fvimg_frame_a", "file_id": "one"},
            {"image_id": "fvimg_frame_b", "file_id": "two"},
        ],
        "seconds_per_image": 0.7,
        "transition": "fade",
        "transition_seconds": 0.1,
        "ratio": "1x1",
        "quality": "fast",
    }
    sha = "c" * 40
    environ = {
        seam.FRAME_VIDEO_PUBLIC_SEAM_FLAG: "1",
        "FRAME_VIDEO_ENGINE_ENABLED": "1",
        "FRAME_VIDEO_PUBLIC_ALLOWED": "1",
        "FRAME_VIDEO_AUTO_RETRY": "0",
        "FRAME_VIDEO_AUTO_FALLBACK": "0",
    }
    result = seam.render_frame_video_public(
        state=state,
        image_paths=[str(first), str(second)],
        output_path=str(tmp_path / "out.mp4"),
        user_id=172203,
        confirmation_id="frame-job-real",
        language="vi",
        runtime_sha=sha,
        expected_worker_sha=sha,
        worker_sha=sha,
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        environ=environ,
    )
    assert result["ok"] is True, result
    assert result["engine_jobs"] == 1
    assert result["provider_calls"] == 0
    assert result["wallet_mutations"] == 0
    assert result["output_size_bytes"] > 0
    assert result["probe"]["ok"] is True
    assert result["probe"]["full_decode"] is True
    assert result["probe"]["frame_order"] == ["fvimg_frame_a", "fvimg_frame_b"]
    assert os.path.exists(tmp_path / "out.mp4")


def test_29o_real_render_preserves_mixed_audio_and_logo(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        import pytest

        pytest.skip("ffmpeg/ffprobe are required")
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    logo = tmp_path / "logo.png"
    music = tmp_path / "music.wav"
    voice = tmp_path / "voice.wav"
    _write_png(first, (220, 40, 40))
    _write_png(second, (40, 220, 40))
    _write_png(logo, (20, 20, 20),)
    for path, frequency in ((music, 330), (voice, 660)):
        generated = __import__("subprocess").run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration=1", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert generated.returncode == 0, generated.stderr[-1000:]
    state = {
        "photos": [
            {"image_id": "fvimg_frame_a", "file_id": "one"},
            {"image_id": "fvimg_frame_b", "file_id": "two"},
        ],
        "seconds_per_image": 0.7,
        "transition": "none",
        "ratio": "1x1",
        "music_volume_percent": 20,
        "voice_volume_percent": 80,
        "logo_position": "top_left",
    }
    sha = "d" * 40
    environ = {
        seam.FRAME_VIDEO_PUBLIC_SEAM_FLAG: "1",
        "FRAME_VIDEO_ENGINE_ENABLED": "1",
        "FRAME_VIDEO_PUBLIC_ALLOWED": "1",
        "FRAME_VIDEO_AUTO_RETRY": "0",
        "FRAME_VIDEO_AUTO_FALLBACK": "0",
    }
    result = seam.render_frame_video_public(
        state=state,
        image_paths=[str(first), str(second)],
        output_path=str(tmp_path / "out.mp4"),
        user_id=172203,
        confirmation_id="frame-job-audio-logo",
        language="vi",
        runtime_sha=sha,
        expected_worker_sha=sha,
        worker_sha=sha,
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        music_path=str(music),
        voice_path=str(voice),
        logo_path=str(logo),
        environ=environ,
    )
    assert result["ok"] is True, result
    assert result["probe"]["audio_stream_count"] == 1
    assert result["plan"].audio_policy["components"]
    assert "overlay" in " ".join(result["command"])
    assert result["provider_calls"] == 0


def test_29o_custom_output_dimensions_are_real_artifact_dimensions(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg/ffprobe are required")
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    _write_png(first, (220, 40, 40))
    _write_png(second, (40, 220, 40))
    state = {
        "photos": [
            {"image_id": "fvimg_frame_a", "file_id": "one"},
            {"image_id": "fvimg_frame_b", "file_id": "two"},
        ],
        "seconds_per_image": 0.6,
        "transition": "none",
        "ratio": "custom",
        "custom_width": 640,
        "custom_height": 480,
        "quality": "fast",
    }
    sha = "f" * 40
    result = seam.render_frame_video_public(
        state=state,
        image_paths=[str(first), str(second)],
        output_path=str(tmp_path / "out.mp4"),
        user_id=172203,
        confirmation_id="frame-job-custom-dimensions",
        language="vi",
        runtime_sha=sha,
        expected_worker_sha=sha,
        worker_sha=sha,
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        environ={
            seam.FRAME_VIDEO_PUBLIC_SEAM_FLAG: "1",
            "FRAME_VIDEO_ENGINE_ENABLED": "1",
            "FRAME_VIDEO_PUBLIC_ALLOWED": "1",
            "FRAME_VIDEO_AUTO_RETRY": "0",
            "FRAME_VIDEO_AUTO_FALLBACK": "0",
        },
    )

    assert result["ok"] is True, result
    assert result["probe"]["width"] == 640
    assert result["probe"]["height"] == 480


@pytest.mark.parametrize(
    ("asset_kind", "expected_blocker"),
    [
        ("music", "promised_music_fingerprint_mismatch"),
        ("logo", "promised_logo_fingerprint_mismatch"),
    ],
)
def test_29o_tampered_promised_audio_or_logo_fails_closed(
    tmp_path: Path,
    monkeypatch,
    asset_kind: str,
    expected_blocker: str,
) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    music = tmp_path / "music.wav"
    logo = tmp_path / "logo.png"
    _write_png(first, (220, 40, 40))
    _write_png(second, (40, 220, 40))
    music.write_bytes(b"trusted-music")
    _write_png(logo, (20, 20, 20))
    state = {
        "photos": [
            {"image_id": "fvimg_frame_a", "file_id": "one"},
            {"image_id": "fvimg_frame_b", "file_id": "two"},
        ],
        "seconds_per_image": 0.6,
        "transition": "none",
        "ratio": "1x1",
        "music_enabled": asset_kind == "music",
        "logo_enabled": asset_kind == "logo",
    }
    original_execute = seam.frame_video_engine.execute_frame_video_local

    def mutate_before_execute(*args, **kwargs):
        target = music if asset_kind == "music" else logo
        target.write_bytes(b"tampered")
        return original_execute(*args, **kwargs)

    monkeypatch.setattr(
        seam.frame_video_engine,
        "execute_frame_video_local",
        mutate_before_execute,
    )
    sha = "1" * 40
    result = seam.render_frame_video_public(
        state=state,
        image_paths=[str(first), str(second)],
        output_path=str(tmp_path / "out.mp4"),
        user_id=172203,
        confirmation_id=f"frame-job-tamper-{asset_kind}",
        language="vi",
        runtime_sha=sha,
        expected_worker_sha=sha,
        worker_sha=sha,
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        music_path=str(music) if asset_kind == "music" else "",
        logo_path=str(logo) if asset_kind == "logo" else "",
        environ={
            seam.FRAME_VIDEO_PUBLIC_SEAM_FLAG: "1",
            "FRAME_VIDEO_ENGINE_ENABLED": "1",
            "FRAME_VIDEO_PUBLIC_ALLOWED": "1",
            "FRAME_VIDEO_AUTO_RETRY": "0",
            "FRAME_VIDEO_AUTO_FALLBACK": "0",
        },
    )

    assert result["ok"] is False, result
    assert result["blocker"] == expected_blocker
    assert result["provider_calls"] == 0
    assert result["wallet_mutations"] == 0


def test_29o_same_confirmation_replays_without_second_render(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        import pytest

        pytest.skip("ffmpeg/ffprobe are required")
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    _write_png(first, (220, 40, 40))
    _write_png(second, (40, 220, 40))
    state = {
        "photos": [
            {"image_id": "fvimg_frame_a", "file_id": "one"},
            {"image_id": "fvimg_frame_b", "file_id": "two"},
        ],
        "seconds_per_image": 0.6,
        "transition": "none",
        "ratio": "1x1",
    }
    sha = "e" * 40
    environ = {
        seam.FRAME_VIDEO_PUBLIC_SEAM_FLAG: "1",
        "FRAME_VIDEO_ENGINE_ENABLED": "1",
        "FRAME_VIDEO_PUBLIC_ALLOWED": "1",
        "FRAME_VIDEO_AUTO_RETRY": "0",
        "FRAME_VIDEO_AUTO_FALLBACK": "0",
    }
    ledger = None
    kwargs = {
        "state": state,
        "image_paths": [str(first), str(second)],
        "output_path": str(tmp_path / "out.mp4"),
        "user_id": 172203,
        "confirmation_id": "frame-job-replay",
        "language": "vi",
        "runtime_sha": sha,
        "expected_worker_sha": sha,
        "worker_sha": sha,
        "ffmpeg_path": ffmpeg,
        "ffprobe_path": ffprobe,
        "environ": environ,
    }
    first_result = seam.render_frame_video_public(**kwargs)
    assert first_result["ok"] is True, first_result
    assert first_result["output_sha256"]
    ledger = first_result["ledger"]
    second_result = seam.render_frame_video_public(**kwargs, ledger=ledger)
    assert second_result["ok"] is True, second_result
    assert second_result["output_sha256"] == first_result["output_sha256"]
    assert second_result["idempotent_replay"] is True
    Path(kwargs["output_path"]).write_bytes(b"corrupted-after-validation")
    third_result = seam.render_frame_video_public(**kwargs, ledger=ledger)
    assert third_result["ok"] is False, third_result
    assert third_result["blocker"] == "frame_artifact_changed_after_validation"
    assert third_result["idempotent_replay"] is True
    assert ledger.render_count == 1
    assert ledger.compose_count == 1


def test_29o_bot_final_renderer_calls_shared_seam_off_event_loop() -> None:
    source = _function_source(REPO_ROOT / "bot.py", "render_frame_video_canonical_from_state")
    assert "frame_video_public_seam.render_frame_video_public" in source
    assert "asyncio.to_thread" in source
    assert "frame_video_runtime.build_ffmpeg_command" not in source
    confirm_source = _function_source(REPO_ROOT / "bot.py", "handle_frame_video_final_confirm")
    assert "result.get(\"blocker\")" in confirm_source
    guard_source = _function_source(REPO_ROOT / "bot.py", "frame_video_runtime_guard")
    assert "frame_video_public_seam_blocker" in guard_source


def test_29o_worker_final_renderer_calls_same_shared_seam() -> None:
    source = _function_source(REPO_ROOT / "local_worker.py", "run_frame_video_render")
    assert "frame_video_public_seam.render_frame_video_public" in source
    assert "frame_video_public_seam_applies_to_worker_job" in source
    assert "worker_sha" in source


def test_29o_seam_uses_shared_29f_executor() -> None:
    source = (REPO_ROOT / "services" / "frame_video_public_seam.py").read_text(encoding="utf-8")
    assert "frame_video_engine.execute_frame_video_local" in source


def test_29o_worker_sha_prefers_authoritative_git_revision(monkeypatch) -> None:
    class Result:
        returncode = 0
        stdout = "git-authoritative-sha\n"

    monkeypatch.setenv("GIT_COMMIT_SHA", "stale-environment-sha")
    monkeypatch.setattr(local_worker.subprocess, "run", lambda *args, **kwargs: Result())
    assert local_worker.local_worker_runtime_sha() == "git-authoritative-sha"


def test_29o_worker_heartbeat_advertises_sha_and_frame_engine_flags(
    monkeypatch,
) -> None:
    expected_sha = "a" * 40
    monkeypatch.setattr(local_worker, "local_worker_runtime_sha", lambda: expected_sha)
    flag_values = {
        seam.FRAME_VIDEO_PUBLIC_SEAM_FLAG: "1",
        "FRAME_VIDEO_ENGINE_ENABLED": "1",
        "FRAME_VIDEO_PUBLIC_ALLOWED": "1",
        "FRAME_VIDEO_AUTO_RETRY": "0",
        "FRAME_VIDEO_AUTO_FALLBACK": "0",
    }
    for name, value in flag_values.items():
        monkeypatch.setenv(name, value)

    payload = local_worker.local_worker_heartbeat_payload()

    assert payload["worker_sha"] == expected_sha
    assert payload["frame_video_engine_flags"] == {
        seam.FRAME_VIDEO_PUBLIC_SEAM_FLAG: True,
        "FRAME_VIDEO_ENGINE_ENABLED": True,
        "FRAME_VIDEO_PUBLIC_ALLOWED": True,
        "FRAME_VIDEO_AUTO_RETRY": False,
        "FRAME_VIDEO_AUTO_FALLBACK": False,
    }


def test_29o_heartbeat_endpoint_persists_sanitized_sha_and_flags() -> None:
    settings: dict[str, str] = {}
    payload = {
        "heartbeat_contract_version": 1,
        "worker_id": "frame-worker-29o",
        "worker_sha": "A" * 40,
        "frame_video_engine_flags": {
            seam.FRAME_VIDEO_PUBLIC_SEAM_FLAG: True,
            "FRAME_VIDEO_ENGINE_ENABLED": True,
            "FRAME_VIDEO_PUBLIC_ALLOWED": True,
            "FRAME_VIDEO_AUTO_RETRY": False,
            "FRAME_VIDEO_AUTO_FALLBACK": False,
        },
    }

    async def read_body(_request) -> dict:
        return payload

    def save_setting(key, value, *_args) -> None:
        settings[str(key)] = str(value)

    endpoint = _compile_bot_function(
        "internal_worker_heartbeat",
        {
            "Request": object,
            "verify_local_worker_access": lambda _request: None,
            "read_json_body": read_body,
            "set_system_setting": save_setting,
            "now_text": lambda: "2026-08-02 13:00:00",
            "datetime": datetime,
            "timezone": timezone,
            "safe_int": lambda value, default=0: int(value or default),
            "json": json,
            "re": re,
            "frame_video_public_seam": seam,
        },
    )
    request = SimpleNamespace(headers={})

    result = asyncio.run(endpoint(request))

    assert result["ok"] is True
    assert settings["local_worker:worker_sha"] == "a" * 40
    assert json.loads(settings["local_worker:frame_video_engine_flags_json"]) == payload[
        "frame_video_engine_flags"
    ]


def test_29o_local_worker_status_exposes_persisted_sha_and_frame_flags() -> None:
    expected_flags = {
        seam.FRAME_VIDEO_PUBLIC_SEAM_FLAG: True,
        "FRAME_VIDEO_ENGINE_ENABLED": True,
        "FRAME_VIDEO_PUBLIC_ALLOWED": True,
        "FRAME_VIDEO_AUTO_RETRY": False,
        "FRAME_VIDEO_AUTO_FALLBACK": False,
    }
    settings = {
        "local_worker:worker_sha": "b" * 40,
        "local_worker:frame_video_engine_flags_json": json.dumps(expected_flags),
        "local_worker:ffprobe_configured": "1",
    }
    status_payload = _compile_bot_function(
        "local_worker_status_payload",
        {
            "local_worker_last_heartbeat": lambda: {
                "connected": True,
                "worker_id": "frame-worker-29o",
                "last_heartbeat": "2026-08-02 13:00:00",
                "age_seconds": 1,
            },
            "count_local_worker_jobs": lambda: {},
            "get_tool_test_result": lambda _name: {},
            "get_system_setting": lambda key, default="": settings.get(key, default),
            "LOCAL_WORKER_ENABLED": True,
            "LOCAL_WORKER_POLL_ENABLED": True,
            "LOCAL_WORKER_TOKEN": "configured",
            "LOCAL_FFMPEG_PATH": "ffmpeg",
            "TELEGRAM_TOKEN": "configured",
            "LOCAL_COMFY_URL": "",
            "LOCAL_COMFY_ENABLED": False,
            "json": json,
            "frame_video_public_seam": seam,
        },
    )

    status = status_payload()

    assert status["worker_sha"] == "b" * 40
    assert status["frame_video_engine_flags"] == expected_flags


def _compile_29o_runtime_guard(*, execution_owner: str, admission) -> object:
    preflight = {
        "ok": True,
        "execution_owner": execution_owner,
        "ffmpeg_path": "ffmpeg" if execution_owner == "local_ffmpeg" else "",
        "ffprobe_path": "ffprobe" if execution_owner == "local_ffmpeg" else "",
    }
    seam_proxy = SimpleNamespace(
        frame_video_public_seam_enabled=lambda: True,
        frame_video_public_minimum_images=lambda: 1,
        frame_video_media_lane=lambda _state: {
            "lane": "short_media",
            "reason": "within_short_thresholds",
        },
        frame_video_public_seam_blocker=lambda: "",
        frame_video_worker_queue_admission=admission,
    )
    return _compile_bot_function(
        "frame_video_runtime_guard",
        {
            "frame_video_total_input_mb": lambda _state: 0,
            "frame_video_estimated_output_seconds": lambda _state: 1.2,
            "frame_video_worker_connected": lambda: True,
            "frame_video_active_jobs_count": lambda: 0,
            "FRAME_VIDEO_ENABLED": True,
            "FRAME_VIDEO_PUBLIC_ENABLED": True,
            "is_admin_user": lambda _user_id: False,
            "frame_video_runtime": SimpleNamespace(
                FRAME_VIDEO_MIN_IMAGES=2,
                validate_plan=lambda _state, **_kwargs: {"ok": True},
            ),
            "FRAME_VIDEO_MAX_IMAGES": 20,
            "FRAME_VIDEO_MAX_INPUT_MB": 50,
            "FRAME_VIDEO_PROCESSING_MAX_INPUT_MB": 1000,
            "FRAME_VIDEO_MAX_OUTPUT_SECONDS": 160,
            "FRAME_VIDEO_MAX_CONCURRENT_JOBS": 1,
            "_safe_int": lambda value, default=0: int(value or default),
            "frame_video_maintenance_text": lambda: "maintenance",
            "frame_video_public_seam": seam_proxy,
            "frame_video_commercial_preflight": lambda _state, _user_id: preflight,
            "is_railway_runtime": lambda: False,
            "local_worker_status_payload": lambda: {
                "worker_sha": "b" * 40,
                "frame_video_engine_flags": {},
            },
            "APP_BUILD_SHA": "a" * 40,
            "APP_BUILD": "",
            "os": os,
        },
    )


@pytest.mark.parametrize(
    "blocker",
    ["worker_sha_mismatch", "worker_engine_flags_mismatch"],
)
def test_29o_worker_queue_guard_fails_closed_before_job_creation(blocker: str) -> None:
    guard = _compile_29o_runtime_guard(
        execution_owner="local_worker",
        admission=lambda *_args, **_kwargs: {"ok": False, "blocker": blocker},
    )

    result = guard({"photos": [{}, {}]}, 172203)

    assert result["ok"] is False
    assert result["action"] == "blocked"
    assert result["reason"] == blocker


def test_29o_direct_render_does_not_depend_on_worker_sha_or_flags() -> None:
    def forbidden_admission(*_args, **_kwargs):
        raise AssertionError("direct render must not inspect worker admission")

    guard = _compile_29o_runtime_guard(
        execution_owner="local_ffmpeg",
        admission=forbidden_admission,
    )

    result = guard({"photos": [{}, {}]}, 172203)

    assert result["ok"] is True
    assert result["action"] == "direct_render"


def test_29o_frame_job_update_enforces_transition_contract() -> None:
    source = _function_source(REPO_ROOT / "bot.py", "update_local_worker_job")
    assert "frame_video_worker_transition_blocker" in source
    handler_source = _function_source(
        REPO_ROOT / "bot.py", "handle_frame_video_worker_job_update"
    )
    endpoint_source = _function_source(REPO_ROOT / "bot.py", "internal_worker_job_update")
    worker_source = _function_source(REPO_ROOT / "local_worker.py", "run_frame_video_render")
    assert "expected_local_worker_job_id" in handler_source
    assert "expected_local_worker_job_id" in endpoint_source
    assert "frame_job_id=" in worker_source
    assert "local_worker_job_id=" in worker_source


def test_29o_frame_job_update_endpoint_rejects_receipt_from_another_queue_job() -> None:
    expected_sha = "a" * 40
    frame_payload = {
        "frame_job_id": "fv-terminal-attestation",
        "user_id": "172203",
        "state": {},
        "frame_video_durable_public_seam": True,
        "frame_video_expected_worker_sha": expected_sha,
    }
    frame_receipt = {
        "frame_job_id": "fv-terminal-attestation",
        "local_worker_job_id": "29002",
        "worker_id": "frame-worker-29o",
        "worker_sha": expected_sha,
        "delivery_message_id": "29001",
        "delivery_file_id": "frame-file",
        "output_size_bytes": 4096,
        "output_sha256": "c" * 64,
        "ffprobe": {
            "ok": True,
            "full_decode": True,
            "duration_seconds": 1.2,
            "size_bytes": 4096,
            "video_stream_count": 1,
            "video_codec": "h264",
            "width": 640,
            "height": 480,
            "artifact_sha256": "c" * 64,
        },
    }
    previous_job = {
        "id": 29001,
        "job_type": "frame_video_render",
        "status": "running",
        "worker_id": "frame-worker-29o",
        "input_file_id": json.dumps(frame_payload),
    }

    class EndpointError(Exception):
        def __init__(self, *, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    async def read_body(_request) -> dict:
        return {
            "id": 29001,
            "status": "succeeded",
            "worker_id": "frame-worker-29o",
            "output_url": json.dumps(frame_receipt),
        }

    endpoint = _compile_bot_function(
        "internal_worker_job_update",
        {
            "verify_local_worker_access": lambda _request: None,
            "read_json_body": read_body,
            "get_local_worker_job": lambda _job_id: previous_job,
            "video_editengine1": SimpleNamespace(WORKER_JOB_TYPE="video_local_edit"),
            "frame_video_public_seam": seam,
            "HTTPException": EndpointError,
            "json": json,
            "update_local_worker_job": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("mismatched receipt must not reach storage")
            ),
            "handle_frame_video_worker_job_update": lambda *_args: None,
            "handle_paid_video_preview_worker_job_update": lambda *_args: None,
            "handle_video_ai_edit_worker_job_update": lambda *_args: None,
            "handle_video_local_edit_worker_job_update": lambda *_args: None,
            "handle_social_link_import_worker_job_update": lambda *_args: None,
        },
    )

    with pytest.raises(EndpointError) as exc_info:
        asyncio.run(endpoint(SimpleNamespace(headers={})))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "local_worker_job_id_mismatch"


def test_29o_frame_job_update_uses_attested_delivery_file_id() -> None:
    expected_sha = "a" * 40
    frame_payload = {
        "frame_job_id": "fv-terminal-canonical-file",
        "user_id": "172203",
        "state": {},
        "frame_video_durable_public_seam": True,
        "frame_video_expected_worker_sha": expected_sha,
    }
    frame_receipt = {
        "frame_job_id": "fv-terminal-canonical-file",
        "local_worker_job_id": "29001",
        "worker_id": "frame-worker-29o",
        "worker_sha": expected_sha,
        "delivery_message_id": "29001",
        "delivery_file_id": "frame-file-attested",
        "output_size_bytes": 4096,
        "output_sha256": "c" * 64,
        "ffprobe": {
            "ok": True,
            "full_decode": True,
            "duration_seconds": 1.2,
            "size_bytes": 4096,
            "video_stream_count": 1,
            "audio_stream_count": 0,
            "video_codec": "h264",
            "width": 640,
            "height": 480,
            "artifact_sha256": "c" * 64,
        },
    }
    previous_job = {
        "id": 29001,
        "job_type": "frame_video_render",
        "status": "running",
        "worker_id": "frame-worker-29o",
        "input_file_id": json.dumps(frame_payload),
    }
    updates: list[dict] = []

    class EndpointError(Exception):
        def __init__(self, *, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    async def read_body(_request) -> dict:
        return {
            "id": 29001,
            "status": "succeeded",
            "worker_id": "frame-worker-29o",
            "output_url": json.dumps(frame_receipt),
            "output_file_id": "frame-file-unattested",
        }

    def update_job(_job_id, **fields) -> dict:
        updates.append(dict(fields))
        return {**previous_job, **fields}

    endpoint = _compile_bot_function(
        "internal_worker_job_update",
        {
            "verify_local_worker_access": lambda _request: None,
            "read_json_body": read_body,
            "get_local_worker_job": lambda _job_id: previous_job,
            "video_editengine1": SimpleNamespace(WORKER_JOB_TYPE="video_local_edit"),
            "frame_video_public_seam": seam,
            "HTTPException": EndpointError,
            "json": json,
            "update_local_worker_job": update_job,
            "handle_frame_video_worker_job_update": lambda *_args: None,
            "handle_paid_video_preview_worker_job_update": lambda *_args: None,
            "handle_video_ai_edit_worker_job_update": lambda *_args: None,
            "handle_video_local_edit_worker_job_update": lambda *_args: None,
            "handle_social_link_import_worker_job_update": lambda *_args: None,
        },
    )

    result = asyncio.run(endpoint(SimpleNamespace(headers={})))

    assert result["ok"] is True
    assert updates[0]["output_file_id"] == "frame-file-attested"


def test_29o_frame_job_update_rejects_terminal_receipt_overwrite() -> None:
    expected_sha = "a" * 40
    frame_payload = {
        "frame_job_id": "fv-terminal-immutable",
        "user_id": "172203",
        "state": {},
        "frame_video_durable_public_seam": True,
        "frame_video_expected_worker_sha": expected_sha,
    }
    stored_receipt = {
        "terminal_contract_version": 1,
        "frame_job_id": "fv-terminal-immutable",
        "local_worker_job_id": "29001",
        "worker_id": "frame-worker-29o",
        "worker_sha": expected_sha,
        "delivery_message_id": "29001",
        "delivery_file_id": "frame-file-original",
        "output_size_bytes": 4096,
        "output_sha256": "c" * 64,
        "ffprobe": {
            "ok": True,
            "full_decode": True,
            "reason": "ok",
            "duration_seconds": 1.2,
            "expected_duration_seconds": 1.2,
            "duration_delta_seconds": 0.0,
            "size_bytes": 4096,
            "video_stream_count": 1,
            "audio_stream_count": 0,
            "video_codec": "h264",
            "width": 640,
            "height": 480,
            "artifact_sha256": "c" * 64,
        },
        "charge_policy": "post_delivery",
        "wallet_charge_amount_xu": 0,
    }
    replayed_receipt = {
        **stored_receipt,
        "delivery_message_id": "29002",
        "delivery_file_id": "frame-file-overwrite",
    }
    previous_job = {
        "id": 29001,
        "job_type": "frame_video_render",
        "status": "succeeded",
        "worker_id": "frame-worker-29o",
        "input_file_id": json.dumps(frame_payload),
        "output_url": json.dumps(stored_receipt),
        "output_file_id": "frame-file-original",
    }
    incoming_receipt = replayed_receipt
    updates: list[dict] = []

    class EndpointError(Exception):
        def __init__(self, *, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    async def read_body(_request) -> dict:
        return {
            "id": 29001,
            "status": "succeeded",
            "worker_id": "frame-worker-29o",
            "output_url": json.dumps(incoming_receipt),
            "output_file_id": "frame-file-overwrite",
        }

    namespace = {
        "verify_local_worker_access": lambda _request: None,
        "read_json_body": read_body,
        "get_local_worker_job": lambda _job_id: previous_job,
        "video_editengine1": SimpleNamespace(WORKER_JOB_TYPE="video_local_edit"),
        "frame_video_public_seam": seam,
        "HTTPException": EndpointError,
        "json": json,
        "update_local_worker_job": lambda *_args, **kwargs: (
            updates.append(dict(kwargs)) or dict(previous_job)
        ),
        "handle_frame_video_worker_job_update": lambda *_args: None,
        "handle_paid_video_preview_worker_job_update": lambda *_args: None,
        "handle_video_ai_edit_worker_job_update": lambda *_args: None,
        "handle_video_local_edit_worker_job_update": lambda *_args: None,
        "handle_social_link_import_worker_job_update": lambda *_args: None,
    }
    endpoint = _compile_bot_function(
        "internal_worker_job_update",
        namespace,
    )

    with pytest.raises(EndpointError) as exc_info:
        asyncio.run(endpoint(SimpleNamespace(headers={})))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "frame_terminal_receipt_conflict"
    assert updates == []

    incoming_receipt = stored_receipt
    result = asyncio.run(endpoint(SimpleNamespace(headers={})))

    assert result["ok"] is True
    assert len(updates) == 1
    assert json.loads(updates[0]["output_url"]) == stored_receipt
    assert updates[0]["output_file_id"] == "frame-file-original"

    for invalid_stored_receipt in ("", "{not-json"):
        previous_job["output_url"] = invalid_stored_receipt
        updates.clear()
        with pytest.raises(EndpointError) as invalid_receipt_exc:
            asyncio.run(endpoint(SimpleNamespace(headers={})))
        assert invalid_receipt_exc.value.status_code == 409
        assert invalid_receipt_exc.value.detail == "frame_terminal_receipt_conflict"
        assert updates == []


def test_29o_storage_boundary_rejects_racing_terminal_receipt_overwrite() -> None:
    stored_receipt = json.dumps(
        {
            "frame_job_id": "fv-terminal-race",
            "local_worker_job_id": "29001",
            "delivery_message_id": "29001",
            "delivery_file_id": "frame-file-original",
        },
        sort_keys=True,
    )
    terminal_job = {
        "id": 29001,
        "job_type": "frame_video_render",
        "status": "succeeded",
        "worker_id": "frame-worker-29o",
        "output_url": stored_receipt,
        "output_file_id": "frame-file-original",
        "started_at": "2026-08-02 13:00:00",
        "finished_at": "2026-08-02 13:00:01",
    }
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
            "get_local_worker_job": lambda _job_id: dict(terminal_job),
            "frame_video_public_seam": seam,
            "now_text": lambda: "2026-08-02 13:00:02",
            "db_connect": lambda: (_ for _ in ()).throw(
                AssertionError("conflicting terminal receipt must not reach storage")
            ),
            "save_tool_test_result": lambda *_args, **_kwargs: None,
        },
    )

    with pytest.raises(ValueError, match="frame_terminal_receipt_conflict"):
        updater(
            29001,
            status="succeeded",
            worker_id="frame-worker-29o",
            output_url=json.dumps(
                {
                    "frame_job_id": "fv-terminal-race",
                    "local_worker_job_id": "29001",
                    "delivery_message_id": "29002",
                    "delivery_file_id": "frame-file-overwrite",
                },
                sort_keys=True,
            ),
            output_file_id="frame-file-overwrite",
        )


def test_29o_frame_job_update_replayed_terminal_never_reaches_charge() -> None:
    expected_sha = "a" * 40
    payload = {
        "frame_job_id": "fv-terminal-attestation",
        "user_id": "172203",
        "state": {},
        "frame_video_durable_public_seam": True,
        "frame_video_expected_worker_sha": expected_sha,
    }
    invalid_receipt = {
        "frame_job_id": "fv-terminal-attestation",
        "local_worker_job_id": "29002",
        "worker_id": "frame-worker-29o",
        "worker_sha": expected_sha,
        "delivery_message_id": "29001",
        "delivery_file_id": "frame-file",
        "output_size_bytes": 4096,
        "output_sha256": "c" * 64,
        "ffprobe": {
            "ok": True,
            "full_decode": True,
            "duration_seconds": 1.2,
            "size_bytes": 4096,
            "video_stream_count": 1,
            "video_codec": "h264",
            "width": 640,
            "height": 480,
            "artifact_sha256": "c" * 64,
        },
    }
    frame_updates: list[dict] = []
    charges: list[str] = []

    def update_frame(_job_id, **fields) -> None:
        frame_updates.append(fields)

    def charge(*_args, **_kwargs) -> dict:
        charges.append("called")
        return {"ok": True}

    handler = _compile_bot_function(
        "handle_frame_video_worker_job_update",
        {
            "json": json,
            "frame_video_public_seam": seam,
            "update_frame_video_job": update_frame,
            "update_frame_video_job_config": lambda *_args, **_kwargs: None,
            "now_text": lambda: "2026-08-02 13:00:00",
            "frame_video_job_for_user": lambda *_args, **_kwargs: {},
            "save_tool_test_result": lambda *_args, **_kwargs: None,
            "frame_video_charge_after_delivery": charge,
            "clear_frame_video_state": lambda *_args, **_kwargs: None,
            "sanitize_log_text": lambda value: str(value),
            "set_frame_video_last_error": lambda *_args, **_kwargs: None,
        },
    )
    previous_job = {
        "id": 29001,
        "job_type": "frame_video_render",
        "status": "running",
        "worker_id": "frame-worker-29o",
        "input_file_id": json.dumps(payload),
    }
    updated_job = {
        **previous_job,
        "status": "succeeded",
        "output_file_id": "frame-file",
        "output_url": json.dumps(invalid_receipt),
    }

    handler(previous_job, updated_job)

    assert charges == []
    assert frame_updates[-1]["status"] == "failed_no_charge"
    assert frame_updates[-1]["blocker"] == "worker_terminal_attestation_failed"
    assert frame_updates[-1]["error_code"] == "local_worker_job_id_mismatch"
    assert frame_updates[-1]["wallet_charge_amount_xu"] == 0


def test_29o_frame_job_update_recovery_preserves_claimed_worker_identity() -> None:
    worker_job = {
        "id": 29001,
        "job_type": "frame_video_render",
        "status": "succeeded",
        "worker_id": "frame-worker-29o",
        "input_file_id": json.dumps({"frame_job_id": "fv-recovery-29o"}),
        "updated_at": "2026-08-02 12:59:59",
    }
    calls: list[tuple[dict, dict]] = []

    class Cursor:
        def fetchall(self):
            return [
                (
                    "fv-recovery-29o",
                    "local_worker",
                    29001,
                    "rendering",
                    "2026-08-02 12:59:58",
                )
            ]

    class Connection:
        def execute(self, *_args, **_kwargs):
            return Cursor()

        def close(self) -> None:
            return None

    reconcile = _compile_bot_function(
        "reconcile_frame_video_jobs_once",
        {
            "datetime": datetime,
            "db_connect": lambda: Connection(),
            "FRAME_VIDEO_MAX_RENDER_SECONDS": 180,
            "parse_now_text": lambda value: datetime.strptime(
                value, "%Y-%m-%d %H:%M:%S"
            ),
            "sanitize_log_text": lambda value: str(value),
            "get_local_worker_job": lambda _job_id: dict(worker_job),
            "handle_frame_video_worker_job_update": lambda previous, updated: calls.append(
                (dict(previous), dict(updated))
            ),
            "update_frame_video_job": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("terminal recovery must not enter the timeout path")
            ),
            "now_text": lambda: "2026-08-02 13:00:00",
        },
    )

    result = reconcile(datetime(2026, 8, 2, 13, 0, 0))

    assert result == {
        "ok": True,
        "checked": 1,
        "recovered": 1,
        "failed": 0,
        "reason": "",
    }
    assert calls == [({**worker_job, "status": "running"}, worker_job)]


def test_29o_worker_payload_marks_final_only_and_keeps_preview_legacy() -> None:
    source = (REPO_ROOT / "bot.py").read_text(encoding="utf-8")
    assert "frame_video_durable_public_seam" in source
    preview_source = _function_source(REPO_ROOT / "bot.py", "frame_video_preview_worker_payload")
    assert "frame_video_durable_public_seam" in preview_source


def test_29o_worker_terminal_payload_persists_public_seam_sha_string(
    monkeypatch,
) -> None:
    updates: list[dict] = []

    def fake_download(_file_id: str, destination: str, **_kwargs) -> None:
        Path(destination).write_bytes(b"frame")

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

    def fake_render(**kwargs) -> dict:
        artifact = b"valid-frame-video"
        Path(kwargs["output_path"]).write_bytes(artifact)
        return {
            "enabled": True,
            "ok": True,
            "output_sha256": digest,
            "probe": {
                "ok": True,
                "full_decode": True,
                "reason": "ok",
                "duration_seconds": 1.2,
                "expected_duration_seconds": 1.2,
                "duration_delta_seconds": 0.0,
                "size_bytes": len(artifact),
                "video_stream_count": 1,
                "audio_stream_count": 0,
                "video_codec": "h264",
                "width": 640,
                "height": 480,
                "artifact_sha256": digest,
            },
        }

    digest = "7" * 64
    monkeypatch.setattr(local_worker, "telegram_download_file", fake_download)
    monkeypatch.setattr(
        local_worker,
        "telegram_send_video_receipt",
        lambda *_args, **_kwargs: {
            "sent": True,
            "message_id": 29001,
            "file_id": "frame-public-file",
        },
    )
    monkeypatch.setattr(local_worker, "update_job", fake_update)
    monkeypatch.setattr(local_worker, "local_ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(local_worker, "find_ffprobe", lambda **_kwargs: "ffprobe")
    monkeypatch.setattr(local_worker, "local_worker_runtime_sha", lambda: "a" * 40)
    monkeypatch.setattr(
        local_worker.frame_video_public_seam,
        "render_frame_video_public",
        fake_render,
    )

    payload = {
        "chat_id": "test-chat",
        "user_id": 172203,
        "photos": [{"file_id": "first"}, {"file_id": "second"}],
        "state": {},
        "frame_video_durable_public_seam": True,
        "frame_video_runtime_sha": "a" * 40,
        "frame_video_expected_worker_sha": "a" * 40,
        "frame_job_id": "frame-job-terminal-sha",
    }
    local_worker.run_frame_video_render(
        {"id": 29001, "input_file_id": json.dumps(payload)}
    )

    assert updates[-1]["status"] == "succeeded", updates[-1]
    terminal = json.loads(updates[-1]["output_url"])
    assert terminal["output_sha256"] == digest
    assert terminal["terminal_contract_version"] == 1
    assert terminal["frame_job_id"] == "frame-job-terminal-sha"
    assert terminal["local_worker_job_id"] == "29001"
    assert terminal["worker_id"] == local_worker.LOCAL_WORKER_ID
    assert terminal["ffprobe"]["full_decode"] is True
    assert len(updates[-1]["output_url"].encode("utf-8")) < 1000
