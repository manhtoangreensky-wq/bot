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

from services import animated_video_engine as engine
from services import video_engine_contract


RUNTIME_SHA = "a" * 40


def _binary(name: str) -> str:
    return str(os.environ.get(f"ANIMATED_VIDEO_{name.upper()}") or shutil.which(name) or "")


def _write_png(path: Path, rgb: tuple[int, int, int], width: int = 96, height: int = 64) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    rows: list[bytes] = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            delta = 28 if (x // 12 + y // 12) % 2 else 0
            row.extend(min(255, channel + delta) for channel in rgb)
        rows.append(bytes(row))
    raw = b"".join(rows)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sample_center_rgb(ffmpeg: str, path: str, timestamp: float) -> tuple[int, int, int]:
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
            "crop=2:2:(iw-2)/2:(ih-2)/2,scale=1:1",
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
    values = dict(engine.ANIMATED_VIDEO_ENGINE_FLAG_DEFAULTS)
    values.update(overrides)
    return values


def _manifest(**overrides) -> dict:
    values = video_engine_contract.build_worker_manifest(
        worker_sha=RUNTIME_SHA,
        worker_instance_id="fixture-worker-29h",
        supported_products=["animated_video"],
        supported_modes=["single_scene", "multi_scene"],
        renderer_name="local-ffmpeg-animated-engine",
        renderer_version="29h-test",
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
    values.update({"engine_adapters": [engine.ENGINE_ADAPTER], "artifact_ready": True})
    values.update(overrides)
    return values


def _plan(paths: list[Path], *, mode: str | None = None, **overrides):
    prompt_prefix = overrides.pop("prompt_prefix", "approved visual prompt")
    style_prompt = overrides.pop("style_prompt", "flat 2D storybook with consistent character")
    character_id = overrides.pop("character_id", "character-main")
    style_id = overrides.pop("style_id", "storybook-2d")
    scenes = [
        {
            "scene_id": f"scene-{index}",
            "scene_index": index,
            "visual_prompt": f"{prompt_prefix} {index}",
            "style_prompt": style_prompt,
            "character_id": character_id,
            "style_id": style_id,
            "asset_id": f"character-asset-{index}",
            "asset_path": str(path),
            "rights_approved": True,
            "rights_receipt_id": "rights-fixture-29h",
            "duration_seconds": 1.2,
            "motion": "ken_burns" if len(paths) == 1 else "pan_horizontal",
            "caption": f"Scene {index}",
        }
        for index, path in enumerate(paths, start=1)
    ]
    return engine.compile_animated_video_plan(
        scenes=scenes,
        mode=mode or ("single_scene" if len(paths) == 1 else "multi_scene"),
        aspect_ratio=overrides.pop("aspect_ratio", "1:1"),
        transition=overrides.pop("transition", "fade"),
        transition_seconds=overrides.pop("transition_seconds", 0.1),
        audio_policy=overrides.pop("audio_policy", {}),
        voice_policy=overrides.pop("voice_policy", {}),
        final_assets=overrides.pop("final_assets", {}),
        **overrides,
    )


def _request(plan: engine.AnimatedVideoPlan, **overrides):
    return engine.build_animated_video_request(
        user_id=172203,
        confirmation_id="confirm-29h",
        language="vi",
        plan=plan,
        explicit_confirmation_receipt={"confirmation_id": "confirm-29h"},
        runtime_sha=RUNTIME_SHA,
        expected_worker_sha=RUNTIME_SHA,
        admin_no_charge=True,
        **overrides,
    )


def test_29h_flags_are_default_off_and_route_requires_explicit_mode_gate() -> None:
    assert engine.animated_video_engine_flags({}) == {
        name: False for name in engine.ANIMATED_VIDEO_ENGINE_FLAG_DEFAULTS
    }
    profile = video_engine_contract.product_route_contract("animated_video")
    assert profile["state"] == "PROFILE_ONLY"
    assert profile["connected"] is False
    route = video_engine_contract.product_route_contract(
        "animated_video", mode="single_scene", environ=_flags(ANIMATED_VIDEO_ENGINE_ENABLED="1")
    )
    assert route == engine.shared_animated_video_engine_route()
    assert route["provider_enabled"] is False


def test_29h_plan_freezes_prompt_style_character_rights_and_asset_identity(tmp_path: Path) -> None:
    image = tmp_path / "character.png"
    _write_png(image, (220, 80, 60))
    plan = _plan([image])
    assert plan.scenes[0].visual_prompt == "approved visual prompt 1"
    assert plan.scenes[0].style_id == "storybook-2d"
    assert plan.scenes[0].character_id == "character-main"
    assert plan.scenes[0].rights_receipt_id == "rights-fixture-29h"
    assert plan.scenes[0].asset_sha256 == _sha256(image)
    assert engine.validate_animated_video_plan(plan)["ok"] is True


def test_29h_plan_rejects_missing_rights_and_unsupported_generated_claim(tmp_path: Path) -> None:
    image = tmp_path / "character.png"
    _write_png(image, (220, 80, 60))
    missing_rights = {
        "scene_id": "scene-1",
        "scene_index": 1,
        "visual_prompt": "approved visual prompt",
        "style_prompt": "storybook",
        "character_id": "character-main",
        "style_id": "storybook-2d",
        "asset_id": "asset-1",
        "asset_path": str(image),
        "rights_approved": False,
        "rights_receipt_id": "",
        "duration_seconds": 1.2,
        "motion": "none",
    }
    with pytest.raises(ValueError, match="rights_receipt_required"):
        engine.compile_animated_video_plan(scenes=[missing_rights], mode="single_scene")

    raw = {
        "scene_id": "scene-1",
        "scene_index": 1,
        "visual_prompt": "make a true 3D orbit",
        "style_prompt": "storybook",
        "character_id": "character-main",
        "style_id": "storybook-2d",
        "asset_id": "asset-1",
        "asset_path": str(image),
        "rights_approved": True,
        "rights_receipt_id": "rights-fixture-29h",
        "duration_seconds": 1.2,
        "motion": "3d_orbit",
    }
    with pytest.raises(ValueError, match="animated_motion_unsupported"):
        engine.compile_animated_video_plan(scenes=[raw], mode="single_scene")
    with pytest.raises(ValueError, match="animated_watermark_position_invalid"):
        _plan(
            [image],
            final_assets={"watermark_text": "BRAND", "watermark_position": "outside"},
        )


def test_29h_default_off_dispatch_has_zero_side_effects(tmp_path: Path) -> None:
    image = tmp_path / "character.png"
    _write_png(image, (220, 80, 60))
    plan = _plan([image])
    request = _request(plan)
    ledger = engine.AnimatedVideoEngineLedger()
    result = engine.dispatch_animated_video(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        environ={},
    )
    assert result["blocker"] == "animated_video_engine_disabled"
    assert result["submitted"] is False
    assert ledger.provider_calls == ledger.delivery_count == 0


def test_29h_plan_identity_and_dispatch_survive_a_safe_asset_path_move(tmp_path: Path) -> None:
    original = tmp_path / "upload-a.png"
    moved = tmp_path / "durable-store.png"
    _write_png(original, (220, 80, 60))
    first = _plan([original])
    moved.write_bytes(original.read_bytes())
    second = _plan([moved])
    assert first.plan_sha256 == second.plan_sha256
    assert _request(first).idempotency_key == _request(second).idempotency_key
    changed_prompt = _plan([moved], prompt_prefix="different approved visual prompt")
    assert changed_prompt.plan_sha256 != first.plan_sha256
    assert _request(changed_prompt).idempotency_key != _request(first).idempotency_key

    request = _request(first)
    original.unlink()
    ledger = engine.AnimatedVideoEngineLedger()
    dispatched = engine.dispatch_animated_video(
        request,
        plan=first,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        environ=_flags(ANIMATED_VIDEO_ENGINE_ENABLED="1"),
    )
    assert dispatched["ok"] is True
    assert dispatched["submitted"] is True


def test_29h_single_scene_renders_real_mp4_with_motion_and_evidence(tmp_path: Path) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    image = tmp_path / "character.png"
    _write_png(image, (220, 80, 60), width=160, height=100)
    plan = _plan([image])
    request = _request(plan)
    ledger = engine.AnimatedVideoEngineLedger()
    result = engine.execute_animated_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(ANIMATED_VIDEO_ENGINE_ENABLED="1"),
        asset_paths={plan.scenes[0].asset_id: str(image)},
    )
    assert result["ok"] is True
    assert result["validation"]["full_decode"] is True
    assert result["validation"]["motion_valid"] is True
    assert result["validation"]["scene_count"] == 1
    assert Path(result["output_path"]).suffix == ".mp4"
    assert Path(result["output_path"]).stat().st_size > 1000
    scene_manifest_path = Path(result["evidence_dir"]) / "scene_001_manifest.json"
    assert scene_manifest_path.is_file()
    scene_manifest = json.loads(scene_manifest_path.read_text(encoding="utf-8"))
    assert scene_manifest["visual_prompt"] == "approved visual prompt 1"
    assert scene_manifest["style_prompt"] == "flat 2D storybook with consistent character"
    assert scene_manifest["rights_receipt_id"] == "rights-fixture-29h"
    replay = engine.execute_animated_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(ANIMATED_VIDEO_ENGINE_ENABLED="1"),
        asset_paths={plan.scenes[0].asset_id: str(image)},
    )
    assert replay["idempotent_replay"] is True
    assert ledger.render_count == 1
    assert ledger.compose_count == 1


def test_29h_multi_scene_renders_ordered_real_mp4_once(tmp_path: Path) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    images = [tmp_path / "one.png", tmp_path / "two.png", tmp_path / "three.png"]
    for path, color in zip(images, ((220, 80, 60), (60, 180, 90), (60, 90, 220))):
        _write_png(path, color, width=160, height=100)
    plan = _plan(images, transition="fade")
    request = _request(plan)
    ledger = engine.AnimatedVideoEngineLedger()
    result = engine.execute_animated_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(ANIMATED_VIDEO_ENGINE_ENABLED="1"),
        asset_paths={scene.asset_id: scene.asset_path for scene in plan.scenes},
    )
    assert result["ok"] is True
    assert result["validation"]["scene_order"] == [1, 2, 3]
    assert result["validation"]["compose_count"] == 1
    assert result["validation"]["full_decode"] is True
    assert result["validation"]["motion_valid"] is True
    assert ledger.render_count == 3
    assert ledger.compose_count == 1
    sampled = [
        _sample_center_rgb(_binary("ffmpeg"), result["output_path"], timestamp)
        for timestamp in (0.5, 1.6, 2.7)
    ]
    assert sampled[0][0] > sampled[0][1] and sampled[0][0] > sampled[0][2]
    assert sampled[1][1] > sampled[1][0] and sampled[1][1] > sampled[1][2]
    assert sampled[2][2] > sampled[2][0] and sampled[2][2] > sampled[2][1]


def test_29h_promised_audio_is_fingerprinted_and_present(tmp_path: Path) -> None:
    ffmpeg = _binary("ffmpeg")
    if not ffmpeg or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    image = tmp_path / "character.png"
    audio = tmp_path / "voice.wav"
    _write_png(image, (220, 80, 60))
    rendered_audio = subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.2", str(audio)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert rendered_audio.returncode == 0, rendered_audio.stderr
    plan = _plan(
        [image],
        audio_policy={"promised": True, "sha256": _sha256(audio), "kind": "approved_audio"},
    )
    request = _request(plan)
    ledger = engine.AnimatedVideoEngineLedger()
    result = engine.execute_animated_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(ANIMATED_VIDEO_ENGINE_ENABLED="1"),
        asset_paths={plan.scenes[0].asset_id: str(image)},
        audio_path=str(audio),
    )
    assert result["ok"] is True
    assert result["validation"]["audio_stream_count"] == 1
    assert ledger.provider_calls == 0


def test_29h_selected_subtitle_logo_and_watermark_are_frozen_and_applied(tmp_path: Path) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    image = tmp_path / "character.png"
    logo = tmp_path / "logo.png"
    _write_png(image, (220, 80, 60), width=160, height=100)
    _write_png(logo, (30, 210, 220), width=48, height=48)
    final_assets = {
        "enable_subtitle": True,
        "logo_enabled": True,
        "logo_asset_id": "brand-logo",
        "logo_path": str(logo),
        "logo_sha256": _sha256(logo),
        "logo_position": "top_left",
        "watermark_text": "BRAND 29H",
        "watermark_position": "bottom_right",
    }
    plan = _plan([image], final_assets=final_assets)
    assert plan.final_assets["logo_sha256"] == _sha256(logo)
    assert plan.final_assets["logo_position"] == "top_left"
    assert plan.final_assets["watermark_position"] == "bottom_right"
    request = _request(plan)
    ledger = engine.AnimatedVideoEngineLedger()
    result = engine.execute_animated_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(ANIMATED_VIDEO_ENGINE_ENABLED="1"),
        asset_paths={plan.scenes[0].asset_id: str(image)},
        final_asset_paths={"brand-logo": str(logo)},
    )
    assert result["ok"] is True
    assert result["validation"]["subtitle_applied"] is True
    assert result["validation"]["logo_applied"] is True
    assert result["validation"]["watermark_applied"] is True
    assert result["validation"]["final_assets_applied"] is True
    assert Path(result["validation"]["subtitle_path"]).is_file()
    scene_manifest = json.loads(
        (Path(result["evidence_dir"]) / "scene_001_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert [item["content"] for item in scene_manifest["text_overlays"]] == [
        "Scene 1",
        "BRAND 29H",
    ]


def test_29h_finalization_is_exactly_once_and_admin_is_free(tmp_path: Path) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    image = tmp_path / "character.png"
    _write_png(image, (220, 80, 60))
    plan = _plan([image])
    request = _request(plan)
    ledger = engine.AnimatedVideoEngineLedger()
    rendered = engine.execute_animated_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(ANIMATED_VIDEO_ENGINE_ENABLED="1"),
        asset_paths={plan.scenes[0].asset_id: str(image)},
    )
    calls: list[str] = []

    def deliver(payload: dict) -> dict:
        calls.append("delivery")
        return {"accepted": True, "message_id": "fixture-message-29h", "production": False}

    def receipt(payload: dict) -> dict:
        calls.append("receipt")
        return {"persisted": True, "receipt_id": "fixture-receipt-29h"}

    def charge(payload: dict) -> dict:
        calls.append("charge")
        return {"recorded": True, "amount_xu": 0, "wallet_mutated": False}

    def report(payload: dict) -> dict:
        calls.append("report")
        return {"emitted": True, "report_id": "fixture-report-29h"}

    first = engine.finalize_animated_video(
        ledger=ledger,
        job_id=rendered["job_id"],
        deliverer=deliver,
        receipt_persister=receipt,
        charger=charge,
        terminal_reporter=report,
    )
    second = engine.finalize_animated_video(
        ledger=ledger,
        job_id=rendered["job_id"],
        deliverer=deliver,
        receipt_persister=receipt,
        charger=charge,
        terminal_reporter=report,
    )
    assert first["ok"] is True
    assert second["idempotent_replay"] is True
    assert calls == ["delivery", "receipt", "charge", "report"]
    assert ledger.provider_calls == 0
    assert ledger.wallet_mutations == 0


def test_29h_missing_required_scene_fails_without_final_or_delivery(tmp_path: Path) -> None:
    image = tmp_path / "character.png"
    missing = tmp_path / "missing.png"
    _write_png(image, (220, 80, 60))
    _write_png(missing, (60, 80, 220))
    plan = _plan([image, missing], transition="cut")
    request = _request(plan)
    missing.unlink()
    ledger = engine.AnimatedVideoEngineLedger()
    result = engine.execute_animated_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(ANIMATED_VIDEO_ENGINE_ENABLED="1"),
        asset_paths={plan.scenes[0].asset_id: str(image)},
    )
    assert result["ok"] is False
    assert result["blocker"] == "animated_scene_asset_missing"
    assert ledger.delivery_count == 0
    assert ledger.compose_count == 0


def test_29h_finalization_rejects_production_delivery_and_admin_wallet_mutation(tmp_path: Path) -> None:
    image = tmp_path / "character.png"
    artifact = tmp_path / "final.mp4"
    _write_png(image, (220, 80, 60))
    artifact.write_bytes(b"validated-local-artifact")
    plan = _plan([image])
    request = _request(plan)

    production_ledger = engine.AnimatedVideoEngineLedger()
    production_ledger.records_by_job_id["production-job"] = {
        "job_id": "production-job",
        "request": request,
        "artifact_path": str(artifact),
        "artifact_sha256": _sha256(artifact),
        "output_bytes": artifact.stat().st_size,
        "evidence_dir": str(tmp_path),
        "terminal_state": "rendered_validated",
        "validation": {"ok": True},
        "delivery": {},
        "receipt": {},
        "charge": {},
        "terminal_report": {},
    }
    blocked = engine.finalize_animated_video(
        ledger=production_ledger,
        job_id="production-job",
        deliverer=lambda _payload: {
            "accepted": True,
            "message_id": "prod-message",
            "production": True,
        },
        receipt_persister=lambda _payload: {"persisted": True, "receipt_id": "should-not-run"},
        charger=lambda _payload: {"recorded": True, "amount_xu": 0, "wallet_mutated": False},
        terminal_reporter=lambda _payload: {"emitted": True},
    )
    assert blocked["blocker"] == "production_telegram_delivery_forbidden"
    assert production_ledger.receipt_count == 0

    wallet_ledger = engine.AnimatedVideoEngineLedger()
    wallet_ledger.records_by_job_id["wallet-job"] = {
        "job_id": "wallet-job",
        "request": request,
        "artifact_path": str(artifact),
        "artifact_sha256": _sha256(artifact),
        "output_bytes": artifact.stat().st_size,
        "evidence_dir": str(tmp_path),
        "terminal_state": "rendered_validated",
        "validation": {"ok": True},
        "delivery": {"accepted": True, "message_id": "fixture-message"},
        "receipt": {"persisted": True, "receipt_id": "fixture-receipt"},
        "charge": {},
        "terminal_report": {},
    }
    wallet_blocked = engine.finalize_animated_video(
        ledger=wallet_ledger,
        job_id="wallet-job",
        deliverer=lambda _payload: {"accepted": True, "message_id": "duplicate"},
        receipt_persister=lambda _payload: {"persisted": True, "receipt_id": "duplicate"},
        charger=lambda _payload: {"recorded": True, "amount_xu": 0, "wallet_mutated": True},
        terminal_reporter=lambda _payload: {"emitted": True},
    )
    assert wallet_blocked["blocker"] == "charge_not_recorded"
    assert wallet_ledger.terminal_report_count == 0
