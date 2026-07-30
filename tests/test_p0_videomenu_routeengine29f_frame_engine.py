from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

import pytest

from services import frame_video_engine as engine
from services import frame_video_runtime as runtime
from services import video_engine_contract


RUNTIME_SHA = "f" * 40


def _binary(name: str) -> str:
    configured = os.environ.get(f"FRAME_VIDEO_{name.upper()}") or shutil.which(name)
    return str(configured or "")


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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sample_rgb(ffmpeg: str, path: str, timestamp: float) -> tuple[int, int, int]:
    sampled = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            path,
            "-frames:v",
            "1",
            "-vf",
            "scale=1:1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        capture_output=True,
        timeout=30,
    )
    assert sampled.returncode == 0, sampled.stderr[-1000:]
    assert len(sampled.stdout) == 3
    return tuple(sampled.stdout)


def _flags(**overrides: str) -> dict[str, str]:
    values = {name: "1" for name in engine.FRAME_VIDEO_ENGINE_FLAG_DEFAULTS}
    values.update(
        {
            "FRAME_VIDEO_ENGINE_ENABLED": "1",
            "FRAME_VIDEO_PUBLIC_ALLOWED": "0",
            "FRAME_VIDEO_AUTO_RETRY": "0",
            "FRAME_VIDEO_AUTO_FALLBACK": "0",
        }
    )
    values.update(overrides)
    return values


def _manifest(**overrides) -> dict:
    values = video_engine_contract.build_worker_manifest(
        worker_sha=RUNTIME_SHA,
        worker_instance_id="fixture-worker-29f",
        supported_products=["frame_video"],
        supported_modes=["single_scene", "multi_scene"],
        renderer_name="local-ffmpeg-frame-engine",
        renderer_version="29f-test",
        ffmpeg_version="fixture-local",
        provider_enabled=False,
        local_enabled=True,
        queue_ready=True,
        worker_connected=True,
        heartbeat_fresh=True,
        health_ok=True,
        worker_status="healthy",
        capabilities=[engine.CANONICAL_WORKER_CAPABILITY],
        local_capabilities={engine.CANONICAL_WORKER_CAPABILITY: True},
        provider_availability={},
    )
    values.update(
        {
            "engine_adapters": [engine.ENGINE_ADAPTER],
            "artifact_ready": True,
        }
    )
    values.update(overrides)
    return values


def _plan(paths: list[Path], *, mode: str | None = None, **overrides):
    frames = [
        {
            "asset_id": f"fixture-frame-{index}",
            "source_path": str(path),
            "duration_seconds": 0.6,
            "motion": "ken_burns" if len(paths) == 1 else "none",
        }
        for index, path in enumerate(paths, start=1)
    ]
    return engine.compile_frame_video_plan(
        frames=frames,
        mode=mode or ("single_scene" if len(paths) == 1 else "multi_scene"),
        aspect_ratio=overrides.pop("aspect_ratio", "1:1"),
        transition=overrides.pop("transition", "fade"),
        transition_seconds=overrides.pop("transition_seconds", 0.1),
        text_overlays=overrides.pop("text_overlays", ()),
        audio_policy=overrides.pop("audio_policy", {}),
        voice_policy=overrides.pop("voice_policy", {}),
        **overrides,
    )


def _request(plan: engine.FrameVideoPlan, **overrides):
    return engine.build_frame_video_request(
        user_id=172203,
        confirmation_id="confirm-29f",
        language="vi",
        plan=plan,
        explicit_confirmation_receipt={"confirmation_id": "confirm-29f"},
        runtime_sha=RUNTIME_SHA,
        expected_worker_sha=RUNTIME_SHA,
        admin_no_charge=True,
        **overrides,
    )


def test_29f_flags_are_default_off_and_legacy_route_is_unchanged() -> None:
    assert engine.frame_video_engine_flags({}) == {
        name: False for name in engine.FRAME_VIDEO_ENGINE_FLAG_DEFAULTS
    }
    legacy = video_engine_contract.product_route_contract("frame_video")
    assert legacy == {
        "product": "frame_video",
        "state": "CONNECTED",
        "connected": True,
        "public_product_type": "frame_video_local",
        "worker_job_type": "frame_video_render",
        "engine_route": "frame_video_render",
        "worker_owner": "frame_video",
        "required_capability": "frame_video_render",
        "supported_modes": ("multi_asset_edit",),
        "provider_enabled": False,
        "local_enabled": True,
        "blocker": "",
    }
    route = video_engine_contract.product_route_contract(
        "frame_video", mode="single_scene", environ={}
    )
    assert route == engine.shared_frame_video_engine_route()
    assert route["engine_route"] != legacy["engine_route"]


def test_29f_shared_submit_cannot_bypass_default_off_gate(tmp_path: Path) -> None:
    path = tmp_path / "frame.png"
    _write_png(path, (80, 120, 220))
    plan = _plan([path])
    request = _request(plan)
    readiness = video_engine_contract.evaluate_readiness(
        request,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        environ={},
    )
    assert readiness["ready"] is False
    assert readiness["blocker"] == "frame_video_engine_disabled"
    jobs: dict[str, video_engine_contract.VideoEngineJob] = {}

    def forbidden_submit(*_args, **_kwargs):
        raise AssertionError("default-off shared submit must not create a job")

    result = video_engine_contract.guarded_submit(
        request,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        jobs_by_idempotency=jobs,
        submitter=forbidden_submit,
        environ={},
    )
    assert result["submitted"] is False
    assert result["blocker"] == "frame_video_engine_disabled"
    assert jobs == {}


def test_29f_contract_is_local_only_and_truthful_about_unsupported_claims() -> None:
    contract = engine.frame_video_engine_contract({})
    assert contract["provider_required"] is False
    assert contract["cloud_provider_calls"] == 0
    assert contract["supported_modes"] == ("single_scene", "multi_scene")
    assert "3d_orbit" in contract["unsupported_claims"]
    assert "unseen_content_generation" in contract["unsupported_claims"]
    assert "lip_sync" in contract["unsupported_claims"]
    assert "character_animation" in contract["unsupported_claims"]


def test_29f_plan_supports_one_frame_and_preserves_ordered_multi_frame_truth(tmp_path: Path) -> None:
    paths = []
    for index, color in enumerate(((220, 40, 40), (40, 220, 40), (40, 40, 220)), start=1):
        path = tmp_path / f"frame-{index}.png"
        _write_png(path, color)
        paths.append(path)

    single = _plan(paths[:1])
    assert single.mode == "single_scene"
    assert len(single.frames) == 1
    assert single.frames[0].motion == "ken_burns"
    assert single.expected_duration_seconds == 0.6

    multi = _plan(paths, transition="dissolve")
    assert multi.mode == "multi_scene"
    assert [frame.frame_index for frame in multi.frames] == [1, 2, 3]
    assert [frame.asset_id for frame in multi.frames] == [
        "fixture-frame-1",
        "fixture-frame-2",
        "fixture-frame-3",
    ]
    assert len(multi.transition_manifest) == 2
    assert multi.frame_order_sha256
    assert engine.validate_frame_video_plan(multi)["ok"] is True


def test_29f_plan_rejects_duplicate_assets_bad_order_and_mode_count(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    _write_png(first, (220, 40, 40))
    _write_png(second, (40, 220, 40))
    duplicate = [
        {"asset_id": "one", "source_path": str(first)},
        {"asset_id": "two", "source_path": str(first)},
    ]
    with pytest.raises(ValueError, match="duplicate_frame_fingerprint"):
        engine.compile_frame_video_plan(frames=duplicate, mode="multi_scene")
    with pytest.raises(ValueError, match="frame_order_invalid"):
        engine.compile_frame_video_plan(
            frames=[
                {"asset_id": "one", "source_path": str(first), "frame_index": 2},
                {"asset_id": "two", "source_path": str(second), "frame_index": 1},
            ],
            mode="multi_scene",
        )
    with pytest.raises(ValueError, match="single_frame_mode_requires_one_frame"):
        engine.compile_frame_video_plan(
            frames=[
                {"asset_id": "one", "source_path": str(first)},
                {"asset_id": "two", "source_path": str(second)},
            ],
            mode="single_scene",
        )


def test_29f_request_hash_is_stable_and_plan_tampering_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "frame.png"
    _write_png(path, (80, 120, 220))
    plan = _plan([path])
    first = _request(plan)
    second = _request(plan)
    assert first.idempotency_key == second.idempotency_key
    assert first.payload["plan_sha256"] == plan.plan_sha256
    tampered = engine.replace_plan(plan, transition="none")
    with pytest.raises(ValueError, match="frame_plan_hash_mismatch"):
        _request(tampered)


def test_29f_idempotency_uses_asset_identity_not_temporary_path(
    tmp_path: Path,
) -> None:
    first = tmp_path / "upload-a" / "frame.png"
    second = tmp_path / "upload-b" / "frame.png"
    first.parent.mkdir()
    second.parent.mkdir()
    _write_png(first, (80, 120, 220))
    shutil.copy2(first, second)
    first_plan = _plan([first])
    second_plan = _plan([second])
    assert first_plan.frames[0].source_path != second_plan.frames[0].source_path
    assert first_plan.frames[0].source_sha256 == second_plan.frames[0].source_sha256
    assert first_plan.plan_sha256 == second_plan.plan_sha256
    first_request = _request(first_plan)
    second_request = _request(second_plan)
    assert first_request.idempotency_key == second_request.idempotency_key
    assert "source_path" not in first_request.input_assets[0]


def test_29f_default_off_dispatch_has_zero_side_effects(tmp_path: Path) -> None:
    path = tmp_path / "frame.png"
    _write_png(path, (80, 120, 220))
    plan = _plan([path])
    ledger = engine.FrameVideoEngineLedger()
    result = engine.dispatch_frame_video(
        _request(plan),
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        environ={},
    )
    assert result["submitted"] is False
    assert result["blocker"] == "frame_video_engine_disabled"
    assert result["job_count"] == 0
    assert result["provider_calls"] == 0
    assert result["wallet_mutations"] == 0


@pytest.mark.parametrize(
    ("manifest_overrides", "expected"),
    [
        ({"worker_sha": "0" * 40}, "worker_sha_mismatch"),
        ({"supported_modes": ("multi_scene",)}, "worker_mode_unsupported"),
        ({"engine_adapters": []}, "worker_adapter_missing"),
    ],
)
def test_29f_readiness_fails_closed_without_side_effects(
    tmp_path: Path, manifest_overrides: dict, expected: str
) -> None:
    path = tmp_path / "frame.png"
    _write_png(path, (80, 120, 220))
    plan = _plan([path])
    result = engine.dispatch_frame_video(
        _request(plan),
        plan=plan,
        manifest=_manifest(**manifest_overrides),
        runtime_sha=RUNTIME_SHA,
        ledger=engine.FrameVideoEngineLedger(),
        environ=_flags(),
    )
    assert result["submitted"] is False
    assert result["blocker"] == expected
    assert result["provider_calls"] == 0


def test_29f_legacy_runtime_still_requires_two_images_by_default(tmp_path: Path) -> None:
    ffmpeg = _binary("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is required")
    path = tmp_path / "frame.png"
    _write_png(path, (80, 120, 220))
    state = {"photos": [{"file_id": "one"}], "image_count": 1}
    with pytest.raises(ValueError, match="not_enough_images"):
        runtime.build_ffmpeg_command([str(path)], str(tmp_path / "out.mp4"), state, ffmpeg_path=ffmpeg)


def test_29f_single_frame_local_render_is_real_mp4_and_idempotent(tmp_path: Path) -> None:
    ffmpeg = _binary("ffmpeg")
    ffprobe = _binary("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg/ffprobe are required")
    path = tmp_path / "single.png"
    _write_png(path, (220, 40, 40))
    plan = _plan([path])
    ledger = engine.FrameVideoEngineLedger()
    request = _request(plan)
    first = engine.execute_frame_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "render",
        asset_paths={plan.frames[0].asset_id: str(path)},
        environ=_flags(),
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
    )
    assert first["ok"] is True, json.dumps(first, ensure_ascii=True)
    assert first["validation"]["full_decode"] is True
    assert first["validation"]["frame_order"] == [plan.frames[0].asset_id]
    assert first["output_bytes"] > 0
    assert first["provider_calls"] == 0
    assert first["render_count"] == 1

    replay = engine.execute_frame_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "render",
        asset_paths={plan.frames[0].asset_id: str(path)},
        environ=_flags(),
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
    )
    assert replay["ok"] is True
    assert replay["idempotent_replay"] is True
    assert replay["render_count"] == 1


@pytest.mark.parametrize("count", [2, 3])
def test_29f_multi_frame_local_render_keeps_order_and_one_final_composition(
    tmp_path: Path, count: int
) -> None:
    ffmpeg = _binary("ffmpeg")
    ffprobe = _binary("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg/ffprobe are required")
    paths = []
    for index in range(count):
        path = tmp_path / f"multi-{index}.png"
        _write_png(path, ((index * 70) % 255, 50, 180))
        paths.append(path)
    plan = _plan(paths, transition="fade")
    result = engine.execute_frame_video_local(
        _request(plan),
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=engine.FrameVideoEngineLedger(),
        output_root=tmp_path / "render",
        asset_paths={frame.asset_id: str(path) for frame, path in zip(plan.frames, paths)},
        environ=_flags(),
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
    )
    assert result["ok"] is True, json.dumps(result, ensure_ascii=True)
    assert result["validation"]["frame_order"] == [frame.asset_id for frame in plan.frames]
    assert result["validation"]["transition_count"] == count - 1
    assert result["validation"]["compose_count"] == 1
    assert result["validation"]["full_decode"] is True
    assert result["provider_calls"] == 0
    sampled = [
        _sample_rgb(ffmpeg, result["output_path"], 0.3 + index * 0.5)
        for index in range(count)
    ]
    red_values = [rgb[0] for rgb in sampled]
    assert red_values == sorted(red_values)
    assert all(right - left > 25 for left, right in zip(red_values, red_values[1:]))


def test_29f_promised_audio_is_required_and_present_in_final_mp4(tmp_path: Path) -> None:
    ffmpeg = _binary("ffmpeg")
    ffprobe = _binary("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg/ffprobe are required")
    image = tmp_path / "image.png"
    audio = tmp_path / "voice.wav"
    _write_png(image, (80, 120, 220))
    generated = subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(audio)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert generated.returncode == 0, generated.stderr[-1000:]
    plan = _plan(
        [image],
        audio_policy={
            "promised": True,
            "asset_id": "voice-1",
            "sha256": _sha256(audio),
        },
    )
    result = engine.execute_frame_video_local(
        _request(plan),
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=engine.FrameVideoEngineLedger(),
        output_root=tmp_path / "render",
        asset_paths={plan.frames[0].asset_id: str(image)},
        audio_path=str(audio),
        environ=_flags(),
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
    )
    assert result["ok"] is True, json.dumps(result, ensure_ascii=True)
    assert result["validation"]["audio_stream_count"] == 1


def test_29f_multiple_promised_audio_assets_fail_before_job_creation(
    tmp_path: Path,
) -> None:
    image = tmp_path / "image.png"
    _write_png(image, (80, 120, 220))
    plan = _plan(
        [image],
        audio_policy={
            "promised": True,
            "asset_id": "music-1",
            "sha256": "a" * 64,
        },
        voice_policy={
            "promised": True,
            "asset_id": "voice-1",
            "sha256": "b" * 64,
        },
    )
    ledger = engine.FrameVideoEngineLedger()
    result = engine.dispatch_frame_video(
        _request(plan),
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        environ=_flags(),
    )
    assert result["submitted"] is False
    assert result["blocker"] == "multiple_promised_audio_assets_unsupported"
    assert result["job_count"] == 0
    assert result["provider_calls"] == 0


def test_29f_delivery_receipt_charge_report_are_once_only(tmp_path: Path) -> None:
    ffmpeg = _binary("ffmpeg")
    ffprobe = _binary("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg/ffprobe are required")
    image = tmp_path / "image.png"
    _write_png(image, (80, 120, 220))
    plan = _plan([image])
    ledger = engine.FrameVideoEngineLedger()
    rendered = engine.execute_frame_video_local(
        _request(plan),
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "render",
        asset_paths={plan.frames[0].asset_id: str(image)},
        environ=_flags(),
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
    )
    assert rendered["ok"] is True
    calls: list[str] = []

    def deliver(payload: dict) -> dict:
        calls.append("delivery")
        assert payload["production"] is False
        return {"accepted": True, "message_id": "fixture-message-29f", "production": False}

    def receipt(payload: dict) -> dict:
        calls.append("receipt")
        return {"persisted": True, "receipt_id": "fixture-receipt-29f"}

    def charge(payload: dict) -> dict:
        calls.append("charge")
        assert payload["amount_xu"] == 0
        return {"ok": True, "wallet_mutated": False, "tx_id": "admin-zero-29f"}

    def report(payload: dict) -> dict:
        calls.append("report")
        return {"emitted": True, "report_id": "fixture-report-29f"}

    first = engine.finalize_frame_video(
        ledger=ledger,
        job_id=rendered["job_id"],
        deliverer=deliver,
        receipt_persister=receipt,
        charger=charge,
        terminal_reporter=report,
    )
    replay = engine.finalize_frame_video(
        ledger=ledger,
        job_id=rendered["job_id"],
        deliverer=deliver,
        receipt_persister=receipt,
        charger=charge,
        terminal_reporter=report,
    )
    assert first["ok"] is True
    assert replay["idempotent_replay"] is True
    assert calls == ["delivery", "receipt", "charge", "report"]
    assert ledger.delivery_count == ledger.receipt_count == 1
    assert ledger.charge_attempts == ledger.terminal_report_count == 1
    assert ledger.wallet_mutations == 0
    assert ledger.production_telegram_deliveries == 0


def test_29f_production_telegram_delivery_is_rejected(tmp_path: Path) -> None:
    ffmpeg = _binary("ffmpeg")
    ffprobe = _binary("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg/ffprobe are required")
    image = tmp_path / "image.png"
    _write_png(image, (80, 120, 220))
    plan = _plan([image])
    ledger = engine.FrameVideoEngineLedger()
    rendered = engine.execute_frame_video_local(
        _request(plan),
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "render",
        asset_paths={plan.frames[0].asset_id: str(image)},
        environ=_flags(),
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
    )
    assert rendered["ok"] is True

    def forbidden(*_args, **_kwargs):
        raise AssertionError("finalization must stop at production delivery")

    result = engine.finalize_frame_video(
        ledger=ledger,
        job_id=rendered["job_id"],
        deliverer=lambda _payload: {
            "accepted": True,
            "message_id": "production-message",
            "production": True,
        },
        receipt_persister=forbidden,
        charger=forbidden,
        terminal_reporter=forbidden,
    )
    assert result["ok"] is False
    assert result["blocker"] == "production_telegram_delivery_forbidden"
    assert ledger.production_telegram_deliveries == 1
    assert ledger.receipt_count == 0
    assert ledger.terminal_report_count == 0


def test_29f_admin_wallet_mutation_is_rejected(tmp_path: Path) -> None:
    ffmpeg = _binary("ffmpeg")
    ffprobe = _binary("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg/ffprobe are required")
    image = tmp_path / "image.png"
    _write_png(image, (80, 120, 220))
    plan = _plan([image])
    ledger = engine.FrameVideoEngineLedger()
    rendered = engine.execute_frame_video_local(
        _request(plan),
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "render",
        asset_paths={plan.frames[0].asset_id: str(image)},
        environ=_flags(),
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
    )
    assert rendered["ok"] is True

    def forbidden_report(*_args, **_kwargs):
        raise AssertionError("admin wallet mutation must stop terminal report")

    result = engine.finalize_frame_video(
        ledger=ledger,
        job_id=rendered["job_id"],
        deliverer=lambda _payload: {
            "accepted": True,
            "message_id": "fixture-message",
            "production": False,
        },
        receipt_persister=lambda _payload: {
            "persisted": True,
            "receipt_id": "fixture-receipt",
        },
        charger=lambda _payload: {
            "ok": True,
            "wallet_mutated": True,
            "tx_id": "forbidden-admin-wallet-tx",
        },
        terminal_reporter=forbidden_report,
    )
    assert result["ok"] is False
    assert result["blocker"] == "admin_wallet_mutation_forbidden"
    assert ledger.wallet_mutations == 1
    assert ledger.terminal_report_count == 0


def test_29f_missing_asset_is_truthful_failure_without_delivery(tmp_path: Path) -> None:
    image = tmp_path / "image.png"
    _write_png(image, (80, 120, 220))
    plan = _plan([image])
    ledger = engine.FrameVideoEngineLedger()
    result = engine.execute_frame_video_local(
        _request(plan),
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "render",
        asset_paths={},
        environ=_flags(),
    )
    assert result["ok"] is False
    assert result["blocker"] == "frame_asset_missing"
    assert result["terminal_state"] == "failed_no_charge"
    assert result["provider_calls"] == 0
    assert result["delivery_count"] == 0
