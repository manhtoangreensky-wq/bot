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

from services import summary_video_engine as engine
from services import video_engine_contract


RUNTIME_SHA = "c" * 40


def _binary(name: str) -> str:
    return str(os.environ.get(f"SUMMARY_VIDEO_{name.upper()}") or shutil.which(name) or "")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_png(path: Path, rgb: tuple[int, int, int], width: int = 160, height: int = 100) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    rows: list[bytes] = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            delta = 25 if (x // 16 + y // 16) % 2 else 0
            row.extend(min(255, value + delta) for value in rgb)
        rows.append(bytes(row))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + chunk(b"IEND", b"")
    )


def _text_source() -> dict:
    return {
        "source_id": "summary-source-29j",
        "source_type": "text",
        "text": (
            "Solar panels convert sunlight into electricity.\n\n"
            "Battery storage keeps surplus energy for use after sunset.\n\n"
            "A monitored installation can reveal production and consumption trends."
        ),
        "language": "en",
        "rights_approved": True,
        "rights_receipt_id": "source-rights-29j",
    }


def _summary_units() -> list[dict]:
    return [
        {
            "summary_id": f"summary-{index}",
            "claim": claim,
            "source_unit_ids": [f"source-unit-{index:03d}"],
        }
        for index, claim in enumerate(
            (
                "Solar panels convert sunlight into electricity.",
                "Battery storage keeps surplus energy for use after sunset.",
                "A monitored installation can reveal production and consumption trends.",
            ),
            start=1,
        )
    ]


def _scenes(paths: list[Path]) -> list[dict]:
    return [
        {
            "scene_id": f"scene-{index}",
            "scene_index": index,
            "summary_unit_ids": [f"summary-{index}"],
            "visual_prompt": f"Approved grounded summary visual {index}",
            "asset_id": f"summary-asset-{index}",
            "asset_path": str(path),
            "asset_sha256": _sha256(path),
            "asset_rights_approved": True,
            "asset_rights_receipt_id": "visual-rights-29j",
            "duration_seconds": 1.2,
            "motion": "ken_burns" if len(paths) == 1 else "pan_horizontal",
        }
        for index, path in enumerate(paths, start=1)
    ]


def _flags(**overrides: str) -> dict[str, str]:
    values = dict(engine.SUMMARY_VIDEO_ENGINE_FLAG_DEFAULTS)
    values.update(overrides)
    return values


def _manifest(**overrides) -> dict:
    values = video_engine_contract.build_worker_manifest(
        worker_sha=RUNTIME_SHA,
        worker_instance_id="fixture-worker-29j",
        supported_products=["summary_video"],
        supported_modes=["single_scene", "multi_scene"],
        renderer_name="local-ffmpeg-summary-engine",
        renderer_version="29j-test",
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


def _plan(paths: list[Path], **overrides):
    source = overrides.pop("source", _text_source())
    extraction = overrides.pop("extraction", engine.build_text_extraction(source))
    units = overrides.pop("summary_units", _summary_units()[: len(paths)])
    return engine.compile_summary_video_plan(
        source=source,
        extraction=extraction,
        summary_units=units,
        scenes=overrides.pop("scenes", _scenes(paths)),
        mode=overrides.pop("mode", "single_scene" if len(paths) == 1 else "multi_scene"),
        aspect_ratio=overrides.pop("aspect_ratio", "1:1"),
        transition=overrides.pop("transition", "cut"),
        transition_seconds=overrides.pop("transition_seconds", 0.0),
        audio_policy=overrides.pop("audio_policy", {}),
        voice_policy=overrides.pop("voice_policy", {}),
        final_assets=overrides.pop("final_assets", {}),
        **overrides,
    )


def _request(plan: engine.SummaryVideoPlan, **overrides):
    return engine.build_summary_video_request(
        user_id=172203,
        confirmation_id="confirm-29j",
        language="vi",
        plan=plan,
        explicit_confirmation_receipt={"confirmation_id": "confirm-29j"},
        runtime_sha=RUNTIME_SHA,
        expected_worker_sha=RUNTIME_SHA,
        admin_no_charge=True,
        **overrides,
    )


def test_29j_default_off_route_and_exact_locked_source_contract() -> None:
    assert engine.ALLOWED_SOURCE_TYPES == ("video", "audio", "document", "text", "link")
    assert engine.summary_video_engine_flags({}) == {
        name: False for name in engine.SUMMARY_VIDEO_ENGINE_FLAG_DEFAULTS
    }
    profile = video_engine_contract.product_route_contract("summary_video")
    assert profile["state"] == "PROFILE_ONLY"
    assert profile["connected"] is False
    route = video_engine_contract.product_route_contract(
        "summary_video",
        mode="single_scene",
        environ=_flags(SUMMARY_VIDEO_ENGINE_ENABLED="1"),
    )
    assert route == engine.shared_summary_video_engine_route()
    contract = engine.summary_video_engine_contract()
    assert contract["local_extraction"] == {"text": True}
    assert set(contract["external_extraction_required"]) == {"video", "audio", "document", "link"}
    assert route["provider_enabled"] is False


def test_29j_direct_text_extraction_has_stable_fingerprint_units_and_locators() -> None:
    source = _text_source()
    first = engine.build_text_extraction(source)
    second = engine.build_text_extraction(source)
    assert first == second
    assert first["status"] == "completed"
    assert first["source_fingerprint"] == engine.summary_source_fingerprint(source)
    assert [item["unit_id"] for item in first["units"]] == [
        "source-unit-001",
        "source-unit-002",
        "source-unit-003",
    ]
    assert first["units"][0]["locator"]["paragraph_index"] == 1
    assert first["units"][0]["locator"]["char_start"] == 0


def test_29j_plan_freezes_grounded_claims_source_map_assets_and_scene_order(tmp_path: Path) -> None:
    images = [tmp_path / "one.png", tmp_path / "two.png", tmp_path / "three.png"]
    for path, color in zip(images, ((220, 80, 60), (60, 180, 90), (60, 90, 220))):
        _write_png(path, color)
    plan = _plan(images)
    assert plan.mode == "multi_scene"
    assert plan.source_type == "text"
    assert plan.source_fingerprint == engine.summary_source_fingerprint(_text_source())
    assert plan.extractor == "local_text_extractor_v1"
    assert len(plan.extraction_sha256) == 64
    assert [scene.scene_index for scene in plan.scenes] == [1, 2, 3]
    assert plan.scenes[0].claim == "Solar panels convert sunlight into electricity."
    assert plan.scenes[0].source_unit_ids == ("source-unit-001",)
    assert plan.scenes[0].asset_sha256 == _sha256(images[0])
    assert plan.source_map_sha256
    assert engine.validate_summary_video_plan(plan)["ok"] is True

    combined_source = {
        **_text_source(),
        "source_id": "summary-source-combined-29j",
        "text": (
            "Solar panels convert sunlight into electricity. Extra installation context follows.\n\n"
            "Battery storage keeps surplus energy for use after sunset."
        ),
    }
    combined_extraction = engine.build_text_extraction(combined_source)
    combined_scene = {
        **_scenes([images[0]])[0],
        "summary_unit_ids": ["summary-1", "summary-2"],
    }
    combined = _plan(
        [images[0]],
        source=combined_source,
        extraction=combined_extraction,
        summary_units=_summary_units()[:2],
        scenes=[combined_scene],
    )
    assert combined.scenes[0].source_unit_ids == (
        "source-unit-001",
        "source-unit-002",
    )
    assert engine.validate_summary_video_plan(combined)["ok"] is True


def test_29j_rejects_unknown_source_failed_extraction_mismatch_and_ungrounded_claim(tmp_path: Path) -> None:
    image = tmp_path / "one.png"
    _write_png(image, (220, 80, 60))
    source = _text_source()
    extraction = engine.build_text_extraction(source)

    with pytest.raises(ValueError, match="summary_source_type_unsupported"):
        engine.summary_source_fingerprint({**source, "source_type": "image"})
    with pytest.raises(ValueError, match="summary_source_extraction_required"):
        _plan([image], extraction={**extraction, "status": "failed", "units": []})
    with pytest.raises(ValueError, match="summary_source_fingerprint_mismatch"):
        _plan([image], extraction={**extraction, "source_fingerprint": "f" * 64})
    with pytest.raises(ValueError, match="summary_aspect_ratio_unsupported"):
        _plan([image], aspect_ratio="3:2")
    with pytest.raises(ValueError, match="summary_claim_not_grounded"):
        _plan(
            [image],
            summary_units=[
                {
                    "summary_id": "summary-1",
                    "claim": "This claim does not occur in the approved source.",
                    "source_unit_ids": ["source-unit-001"],
                }
            ],
        )


@pytest.mark.parametrize("source_type", ("video", "audio", "document", "link"))
def test_29j_non_text_sources_require_completed_external_extraction(source_type: str, tmp_path: Path) -> None:
    source = {
        "source_id": f"source-{source_type}",
        "source_type": source_type,
        "rights_approved": True,
        "rights_receipt_id": "source-rights-29j",
    }
    if source_type == "link":
        source.update(
            {
                "canonical_url": "https://example.com/approved-summary-source",
                "snapshot_sha256": "d" * 64,
            }
        )
    else:
        path = tmp_path / f"source.{ {'video': 'mp4', 'audio': 'wav', 'document': 'txt'}[source_type] }"
        path.write_bytes(f"approved {source_type} fixture".encode("utf-8"))
        source["path"] = str(path)
        source["sha256"] = _sha256(path)
    fingerprint = engine.summary_source_fingerprint(source)
    extraction = {
        "status": "completed",
        "source_fingerprint": fingerprint,
        "extractor": "approved-external-fixture",
        "units": [
            {
                "unit_id": "source-unit-001",
                "text": "Approved extracted source statement.",
                "locator": (
                    {"start_seconds": 0.0, "end_seconds": 1.0}
                    if source_type in {"video", "audio"}
                    else {"page_start": 1, "page_end": 1}
                    if source_type == "document"
                    else {"canonical_url": source["canonical_url"], "section": "main"}
                ),
            }
        ],
    }
    assert engine.validate_summary_extraction(source, extraction)["ok"] is True
    with pytest.raises(ValueError, match="summary_extractor_required"):
        engine.validate_summary_extraction(source, {**extraction, "extractor": ""})
    with pytest.raises(ValueError, match="summary_source_extraction_required"):
        engine.validate_summary_extraction(source, {})


def test_29j_default_off_dispatch_has_zero_side_effects(tmp_path: Path) -> None:
    image = tmp_path / "one.png"
    _write_png(image, (220, 80, 60))
    plan = _plan([image])
    request = _request(plan)
    ledger = engine.SummaryVideoEngineLedger()
    result = engine.dispatch_summary_video(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        environ={},
    )
    assert result["blocker"] == "summary_video_engine_disabled"
    assert result["submitted"] is False
    assert ledger.provider_calls == ledger.delivery_count == 0


def test_29j_single_scene_renders_real_grounded_mp4_and_admin_source_map(tmp_path: Path) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    image = tmp_path / "one.png"
    _write_png(image, (220, 80, 60))
    plan = _plan([image])
    request = _request(plan)
    ledger = engine.SummaryVideoEngineLedger()
    result = engine.execute_summary_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(SUMMARY_VIDEO_ENGINE_ENABLED="1"),
        asset_paths={plan.scenes[0].asset_id: str(image)},
    )
    assert result["ok"] is True
    assert result["validation"]["full_decode"] is True
    assert result["validation"]["grounding_complete"] is True
    assert result["validation"]["scene_order"] == [1]
    assert Path(result["output_path"]).stat().st_size > 1000
    source_map_path = Path(result["evidence_dir"]) / "admin_source_map.json"
    source_map = json.loads(source_map_path.read_text(encoding="utf-8"))
    assert source_map["source_fingerprint"] == plan.source_fingerprint
    assert source_map["extraction_sha256"] == plan.extraction_sha256
    assert source_map["scenes"][0]["claim"] == plan.scenes[0].claim
    assert source_map["scenes"][0]["source_references"][0]["locator"]["paragraph_index"] == 1
    replay = engine.execute_summary_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(SUMMARY_VIDEO_ENGINE_ENABLED="1"),
        asset_paths={plan.scenes[0].asset_id: str(image)},
    )
    assert replay["idempotent_replay"] is True
    assert ledger.render_count == 1
    assert ledger.compose_count == 1


def test_29j_multiscene_renders_ordered_claims_without_missing_scene(tmp_path: Path) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    images = [tmp_path / "one.png", tmp_path / "two.png", tmp_path / "three.png"]
    for path, color in zip(images, ((220, 80, 60), (60, 180, 90), (60, 90, 220))):
        _write_png(path, color)
    plan = _plan(images)
    request = _request(plan)
    ledger = engine.SummaryVideoEngineLedger()
    result = engine.execute_summary_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(SUMMARY_VIDEO_ENGINE_ENABLED="1"),
        asset_paths={scene.asset_id: scene.asset_path for scene in plan.scenes},
    )
    assert result["ok"] is True
    assert result["validation"]["scene_order"] == [1, 2, 3]
    assert result["validation"]["scene_coverage_complete"] is True
    assert result["validation"]["motion_valid"] is True
    assert result["validation"]["source_map_scene_count"] == 3
    assert ledger.render_count == 3
    assert ledger.compose_count == 1


def test_29j_promised_audio_is_fingerprinted_and_present(tmp_path: Path) -> None:
    ffmpeg = _binary("ffmpeg")
    if not ffmpeg or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    image = tmp_path / "one.png"
    audio = tmp_path / "summary.wav"
    _write_png(image, (220, 80, 60))
    rendered = subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.2", str(audio)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert rendered.returncode == 0, rendered.stderr
    plan = _plan(
        [image],
        audio_policy={"promised": True, "kind": "approved_audio", "sha256": _sha256(audio)},
    )
    request = _request(plan)
    ledger = engine.SummaryVideoEngineLedger()
    result = engine.execute_summary_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(SUMMARY_VIDEO_ENGINE_ENABLED="1"),
        asset_paths={plan.scenes[0].asset_id: str(image)},
        audio_path=str(audio),
    )
    assert result["ok"] is True
    assert result["validation"]["audio_stream_count"] == 1
    assert ledger.provider_calls == 0


def test_29j_logo_watermark_and_subtitle_are_applied_with_independent_positions(tmp_path: Path) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    image = tmp_path / "one.png"
    logo = tmp_path / "logo.png"
    _write_png(image, (220, 80, 60))
    _write_png(logo, (30, 210, 220), width=48, height=48)
    final_assets = {
        "enable_subtitle": True,
        "logo_enabled": True,
        "logo_asset_id": "summary-logo",
        "logo_path": str(logo),
        "logo_sha256": _sha256(logo),
        "logo_position": "top_left",
        "watermark_text": "SUMMARY 29J",
        "watermark_position": "bottom_right",
    }
    plan = _plan([image], final_assets=final_assets)
    request = _request(plan)
    ledger = engine.SummaryVideoEngineLedger()
    result = engine.execute_summary_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(SUMMARY_VIDEO_ENGINE_ENABLED="1"),
        asset_paths={plan.scenes[0].asset_id: str(image)},
        final_asset_paths={"summary-logo": str(logo)},
    )
    assert result["ok"] is True
    assert result["validation"]["subtitle_applied"] is True
    assert result["validation"]["logo_applied"] is True
    assert result["validation"]["watermark_applied"] is True
    scene_manifest = json.loads(
        (Path(result["evidence_dir"]) / "scene_001_manifest.json").read_text(encoding="utf-8")
    )
    assert scene_manifest["logo_position"] == "top_left"
    assert scene_manifest["watermark_position"] == "bottom_right"


def test_29j_finalization_is_exactly_once_and_admin_is_free(tmp_path: Path) -> None:
    if not _binary("ffmpeg") or not _binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe are required")
    image = tmp_path / "one.png"
    _write_png(image, (220, 80, 60))
    plan = _plan([image])
    request = _request(plan)
    ledger = engine.SummaryVideoEngineLedger()
    rendered = engine.execute_summary_video_local(
        request,
        plan=plan,
        manifest=_manifest(),
        runtime_sha=RUNTIME_SHA,
        ledger=ledger,
        output_root=tmp_path / "jobs",
        environ=_flags(SUMMARY_VIDEO_ENGINE_ENABLED="1"),
        asset_paths={plan.scenes[0].asset_id: str(image)},
    )
    calls: list[str] = []

    def deliver(_payload: dict) -> dict:
        calls.append("delivery")
        return {"accepted": True, "message_id": "fixture-message-29j", "production": False}

    def receipt(_payload: dict) -> dict:
        calls.append("receipt")
        return {"persisted": True, "receipt_id": "fixture-receipt-29j"}

    def charge(_payload: dict) -> dict:
        calls.append("charge")
        return {"recorded": True, "amount_xu": 0, "wallet_mutated": False}

    def report(_payload: dict) -> dict:
        calls.append("report")
        return {"emitted": True, "report_id": "fixture-report-29j"}

    first = engine.finalize_summary_video(
        ledger=ledger,
        job_id=rendered["job_id"],
        deliverer=deliver,
        receipt_persister=receipt,
        charger=charge,
        terminal_reporter=report,
    )
    second = engine.finalize_summary_video(
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
    assert ledger.paid_provider_calls == 0
    assert ledger.wallet_mutations == 0


def test_29j_finalization_rejects_production_delivery_and_wallet_mutation(tmp_path: Path) -> None:
    image = tmp_path / "one.png"
    artifact = tmp_path / "final.mp4"
    _write_png(image, (220, 80, 60))
    artifact.write_bytes(b"validated-local-summary-artifact")
    plan = _plan([image])
    request = _request(plan)
    base_record = {
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
    production = engine.SummaryVideoEngineLedger()
    production.records_by_job_id["production-job"] = {**base_record, "job_id": "production-job"}
    blocked = engine.finalize_summary_video(
        ledger=production,
        job_id="production-job",
        deliverer=lambda _payload: {"accepted": True, "message_id": "prod", "production": True},
        receipt_persister=lambda _payload: {"persisted": True, "receipt_id": "forbidden"},
        charger=lambda _payload: {"recorded": True, "amount_xu": 0, "wallet_mutated": False},
        terminal_reporter=lambda _payload: {"emitted": True},
    )
    assert blocked["blocker"] == "production_telegram_delivery_forbidden"
    assert production.receipt_count == 0

    wallet = engine.SummaryVideoEngineLedger()
    wallet.records_by_job_id["wallet-job"] = {
        **base_record,
        "job_id": "wallet-job",
        "delivery": {"accepted": True, "message_id": "fixture"},
        "receipt": {"persisted": True, "receipt_id": "fixture"},
    }
    wallet_blocked = engine.finalize_summary_video(
        ledger=wallet,
        job_id="wallet-job",
        deliverer=lambda _payload: {"accepted": True, "message_id": "duplicate"},
        receipt_persister=lambda _payload: {"persisted": True, "receipt_id": "duplicate"},
        charger=lambda _payload: {"recorded": True, "amount_xu": 0, "wallet_mutated": True},
        terminal_reporter=lambda _payload: {"emitted": True},
    )
    assert wallet_blocked["blocker"] == "charge_not_recorded"
    assert wallet.terminal_report_count == 0
